#!/usr/bin/env python3
"""House audit for the Pine v6 indicators: the 5S situation analysis and the check in STANDARD.md.

Per script: settings and groups, View group first, text-colour setting, settings never read, globals never read,
functions never called, trailing spaces, and whether the higher-timeframe candles and the market-structure drawing
follow the house standard. Two compiler checks TradingView reports and the parser does not:
  inline  CW10026: a setting with a title that is not the first on its inline row (only the first may carry one);
  ifret   CE10235 risk: a function whose last statement is an if, so its branches must return one type (end the
          function on an explicit value instead).
And one chart check: scale  an overlay script that plots values without scale = scale.right, which TradingView can
          leave on its own scale, so the plots and drawings float apart from price.

  python3 audit.py [folder]              one row per script, then the totals (folder defaults to the current one)
  python3 audit.py --detail NAME [folder] the lists behind one script's row (JSON)
  python3 audit.py --check [folder]       the same table; exits 1 if any total is above 0 (a gate before delivery)

Static checks on the source only: a script that passes still needs the parse, size and limit checks.
"""
import re, sys, os, json, glob, collections

# Scripts that draw higher-timeframe / PO3 candles, and scripts that draw MSS / BOS, by file name (without .pine).
CANDLE = {'Hado_99', 'Wabisuke', 'Mangekyo', 'Hogyoku', 'Getsuga', 'Gran_Rey_Cero', 'Hueco_Mundo', 'Shikai_Bankai'}
STRUCT = {'Benihime_v3', 'Getsuga', 'Sharingan', 'Suzumebachi'}
NO_THEME_TEXT = {'OpenGaps'}   # every label takes a gap colour the user sets; nothing follows the chart theme

def strip_comments_strings(src):
    """each line with its comment removed and string contents blanked, so names inside text don't count as uses"""
    out = []
    for line in src.split('\n'):
        s, i, q = [], 0, None
        while i < len(line):
            c = line[i]
            if q:
                if c == '\\':
                    i += 2; continue
                if c == q:
                    q = None
                s.append(' ')
            else:
                if c in '"\'':
                    q = c; s.append(' ')
                elif line.startswith('//', i):
                    break
                else:
                    s.append(c)
            i += 1
        out.append(''.join(s))
    return out

def split_args(s):
    """top-level comma split of a call's argument text (stops at the closing parenthesis)"""
    out, cur, depth, q, i = [], [], 0, None, 0
    while i < len(s):
        c = s[i]
        if q:
            cur.append(c)
            if c == '\\':
                cur.append(s[i + 1] if i + 1 < len(s) else ''); i += 2; continue
            if c == q:
                q = None
        elif c in '"\'':
            q = c; cur.append(c)
        elif c in '([{':
            depth += 1; cur.append(c)
        elif c in ')]}':
            if depth == 0:
                break
            depth -= 1; cur.append(c)
        elif c == ',' and depth == 0:
            out.append(''.join(cur).strip()); cur = []
        else:
            cur.append(c)
        i += 1
    if ''.join(cur).strip():
        out.append(''.join(cur).strip())
    return out

INPUT_RE = re.compile(r'^(?:var\s+|const\s+|simple\s+)?(?:[\w.<>]+\s+)?(\w+)\s*=\s*input(?:\.(\w+))?\s*\((.*)$')
GROUP_DEF = re.compile(r'^(?:const\s+|var\s+)?(?:string\s+)?(\w+)\s*=\s*"([^"]*)"\s*(?://.*)?$')
TOK_RE = re.compile(r'(?<![\w.])([A-Za-z_]\w*)(?!\w)')
METH_RE = re.compile(r'\.([A-Za-z_]\w*)\s*\(')

def audit(path):
    src = open(path, encoding='utf-8').read()
    lines = src.split('\n')
    code = strip_comments_strings(src)
    name = os.path.basename(path)[:-5]
    is_lib = bool(re.search(r'^library\(', src, re.M))
    gdefs = {}
    for ln in lines:
        m = GROUP_DEF.match(ln.strip())
        if m:
            gdefs[m.group(1)] = m.group(2)
    # settings: name, kind, title (the second argument, or title =), group (resolved through string constants)
    inputs = []
    for i, ln in enumerate(lines):
        if ln.startswith((' ', '\t')):
            continue
        m = INPUT_RE.match(ln)
        if not m:
            continue
        var, kind, rest = m.group(1), m.group(2) or 'auto', m.group(3)
        args = split_args(rest)
        tt = [a for a in args if re.match(r'^title\s*=', a)]
        cand = tt[0].split('=', 1)[1] if tt else (args[1] if len(args) > 1 and '=' not in args[1].split('"')[0] else '')
        title = re.search(r'"([^"]*)"', cand)
        g = re.search(r'group\s*=\s*("([^"]*)"|(\w+))', rest)
        grp = (g.group(2) if g.group(2) is not None else gdefs.get(g.group(3), g.group(3))) if g else None
        il = re.search(r'inline\s*=\s*"([^"]*)"', rest)
        inputs.append(dict(var=var, kind=kind, title=title.group(1) if title else '', group=grp, line=i + 1, inline=il.group(1) if il else None))
    order = []
    for inp in inputs:
        if inp['group'] not in order:
            order.append(inp['group'])
    # uses: every identifier count, less the declaration's own left-hand side
    line_tok = [collections.Counter(TOK_RE.findall(ln)) for ln in code]
    total = collections.Counter()
    for c in line_tok:
        total.update(c)
    meth = collections.Counter(m for ln in code for m in METH_RE.findall(ln))
    def uses(nm, decl_line):
        n = total[nm] - line_tok[decl_line - 1][nm]
        ln = code[decl_line - 1]
        rest = ln.split('=', 1)[1] if '=' in ln else ''
        return n + sum(1 for t in TOK_RE.findall(rest) if t == nm)
    unused_inputs = [x['var'] for x in inputs if uses(x['var'], x['line']) == 0]
    gl = []
    for i, ln in enumerate(code):
        if ln.startswith((' ', '\t')) or not ln.strip():
            continue
        m = re.match(r'^(?:var\s+|varip\s+|const\s+)?(?:(?:array|matrix|map)<[^>]+>\s+|[A-Za-z_][\w.]*\s+)?([A-Za-z_]\w*)\s*=(?!=)', ln)
        if m and not re.match(r'^(if|for|while|switch|export|method|type)\b', ln):
            nm = m.group(1)
            if nm in ('indicator', 'library') or 'input' in ln.split('=', 1)[1][:12]:
                continue
            gl.append((nm, i + 1))
    unused_globals = [n for n, l in gl if uses(n, l) == 0 and n not in gdefs]
    fns = [(m.group(1), i + 1) for i, ln in enumerate(code) for m in [re.match(r'^(?:export\s+)?(?:method\s+)?(\w+)\s*\(([^)]*)\)\s*=>', ln)] if m]
    unused_fns = [] if is_lib else [n for n, l in fns if uses(n, l) + meth[n] == 0]   # methods are called as x.name()
    trailing = sum(1 for ln in lines if ln != ln.rstrip())
    # CW10026: only the first setting on an inline row may carry a title
    seen_row, inline_bad = set(), []
    for x in inputs:
        if x['inline'] is None:
            continue
        key = (x['group'], x['inline'])
        if key in seen_row and x['title']:
            inline_bad.append(f"{x['var']} (line {x['line']})")
        seen_row.add(key)
    # an overlay script that plots values should pin itself to the price scale
    head = re.search(r'^indicator\((.*)$', src, re.M)
    overlay = bool(head and re.search(r'overlay\s*=\s*true', head.group(1)))
    plots = any(re.match(r'^\s*plot(?:candle|bar|shape|char)?\s*\(', ln) for ln in code)
    scale_ok = not (overlay and plots) or bool(head and re.search(r'scale\s*=\s*scale\.(right|left)', head.group(1)))
    # CE10235 risk: a multi-line function whose last top-level statement is an if
    ifret = []
    for i, ln in enumerate(code):
        m = re.match(r'^(?:export\s+)?(?:method\s+)?(\w+)\s*\([^)]*\)\s*=>\s*$', ln)
        if not m:
            continue
        body = []
        for ln2 in code[i + 1:]:
            if ln2.strip() == '':
                continue
            if not ln2.startswith((' ', '\t')):
                break
            body.append(ln2)
        if body:
            base = len(body[0]) - len(body[0].lstrip())
            top = [b for b in body if len(b) - len(b.lstrip()) == base]
            if top and re.match(r'^\s*if\b', top[-1]):
                ifret.append(f"{m.group(1)} (line {i + 1})")
    titles = ' | '.join(x['title'].lower() for x in inputs)
    text_col = bool(re.search(r'text colou?r|label colou?r', titles))
    view_first = bool(order) and (order[0] or '').strip().lower().startswith('view')
    # candles on Hadō 99's system: wick width, countdown, forming candle dashed, an ICT colour option, width / gap
    candle = name in CANDLE
    tl = [x['title'] for x in inputs]
    opts = ' '.join(ln for ln in lines if 'input.string(' in ln and '"Colours"' in ln)
    hado = all(t in tl for t in ('Wick width', 'Countdown')) and ('Forming candle dashed' in tl or 'dashed' in tl) and 'ICT (green / black)' in opts and any('gap' in t.lower() for t in tl)
    if name == 'Hueco_Mundo':   # its candles come from Gran Rey Cero's library, under the g_ prefix
        hado = 'g_pWkW' in src and 'g_pLivI' in src and 'g_pCdI' in src
    # house structure style: no solid MSS, and every BOS label names its direction
    struct = name in STRUCT
    sstd = None
    if struct:
        mss_solid = bool(re.search(r'MSS[^\n]{0,200}style_solid|style = mss \? line\.style_solid', src))
        bos_noarrow = bool(re.search(r'(?:label\.new|[Tt]ag)\([^\n]*"(?:4H |RTH |H |D )?BOS"\s*,', src)) or bool(re.search(r'nm \+ " BOS"', src))
        sstd = not mss_solid and not bos_noarrow
    return dict(name=name, lines=len(lines), lib=is_lib, inputs=len(inputs), inputs_list=inputs, groups=len(order), order=order,
                view_first=view_first, text_col=text_col, unused_inputs=unused_inputs, unused_globals=unused_globals,
                unused_fns=unused_fns, trailing=trailing, candle=candle, hado=hado, struct=struct, sstd=sstd,
                inline_bad=inline_bad, ifret=ifret, scale_ok=scale_ok)

def main():
    args = sys.argv[1:]
    detail = check = None
    if args and args[0] == '--detail':
        detail = args[1]; args = args[2:]
    if args and args[0] == '--check':
        check = True; args = args[1:]
    folder = args[0] if args else os.getcwd()
    rows = [audit(p) for p in sorted(glob.glob(os.path.join(folder, '*.pine')))]
    if detail:
        r = next(x for x in rows if x['name'] == detail)
        print(json.dumps(r, indent=1, ensure_ascii=False)); return 0
    print(f"{'script':18s} {'lines':>5s} {'inp':>4s} {'grp':>3s} view txtcol {'unusedIn':>8s} {'unusedGl':>8s} {'unusedFn':>8s} trail candle struct inline ifret scale")
    tot = dict(ui=0, ug=0, uf=0, tr=0, nv=0, nt=0, il=0, ir=0, sc=0)
    for r in rows:
        txt = 'yes' if r['text_col'] else ('lib' if r['lib'] else ('n/a' if r['name'] in NO_THEME_TEXT else 'no'))
        print(f"{r['name']:18s} {r['lines']:5d} {r['inputs']:4d} {r['groups']:3d} {('yes' if r['view_first'] else ('lib' if r['lib'] else 'NO')):>4s} {txt:>6s} "
              f"{len(r['unused_inputs']):8d} {len(r['unused_globals']):8d} {len(r['unused_fns']):8d} {r['trailing']:5d} "
              f"{(('std' if r['hado'] else 'OLD') if r['candle'] else '-'):>6s} {(('std' if r['sstd'] else 'OLD') if r['struct'] else '-'):>6s} {len(r['inline_bad']):6d} {len(r['ifret']):5d} {('ok' if r['scale_ok'] else 'FLOAT'):>5s}")
        tot['il'] += len(r['inline_bad']); tot['ir'] += len(r['ifret']); tot['sc'] += 0 if r['scale_ok'] else 1
        tot['ui'] += len(r['unused_inputs']); tot['ug'] += len(r['unused_globals']); tot['uf'] += len(r['unused_fns']); tot['tr'] += r['trailing']
        if not r['lib']:
            tot['nv'] += 0 if r['view_first'] else 1
            tot['nt'] += 0 if r['text_col'] or r['name'] in NO_THEME_TEXT else 1
    nc = sum(1 for r in rows if r['candle'] and not r['hado']); ns = sum(1 for r in rows if r['struct'] and not r['sstd'])
    print(f"CANDLES not on the Hadō 99 standard {nc} of {sum(1 for r in rows if r['candle'])} · STRUCTURE not on the house style {ns} of {sum(1 for r in rows if r['struct'])}")
    print(f"TOTAL scripts {len(rows)}  not View-first {tot['nv']}  no text colour {tot['nt']}  unused inputs {tot['ui']}  unused globals {tot['ug']}  unused fns {tot['uf']}  trailing-space lines {tot['tr']}  inline titles {tot['il']}  fns ending on if {tot['ir']}  floating overlay plots {tot['sc']}")
    if check:
        return 1 if (nc or ns or any(tot.values())) else 0
    return 0

if __name__ == '__main__':
    sys.exit(main())
