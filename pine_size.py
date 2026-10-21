"""Estimate how big TradingView's compiler will find a Pine v6 script, before you paste it.

TradingView checks three size limits that it does not publish formulas for:
  CE10117  "Compiled code contains too many tokens"   whole script's IL, limit 100,256 tokens
  CE10295  "The main body of the script is too long"  the global scope
  CE10205  "The if statement is too long"             one if block (seen inside functions)

Model (fitted 14 Oct 2026 from TradingView results, see CALIBRATION):
  IL tokens ~= c x source tokens (identifiers, numbers, operators, punctuation; no strings or comments)
              + s x string bytes (UTF-8), where a string variable holding a constant (const, or a var / plain global
                initialised from literals and never reassigned) is embedded again at EVERY place it is used.
  The results pin c and s to a line: c = 0.3 .. 1.2 with s = 1.45 .. 1.23 (strings cost more than code).
  The estimate is reported at both ends (lo / hi); judge by the higher one.
That second rule is the big one: a 1,000-character tooltip held in `var string X = "..."` and used in 9 cardRow calls
costs about 12,000 tokens. Keep long text in a runtime array (pine_tips.py does the conversion): each text is
embedded once.

CALIBRATION (TradingView, 14 Oct 2026)
  Hollow v3 (1542 lines)                CE10117 at 137,244 tokens   (the fit point)
  Desgarron v3                          compiles   (sets the upper end of c)
  Vizard (14 Oct)                       compiles
  Gran Rey Cero (13 Oct, before CPI DR) compiles; main body OK
  Gran Rey Cero v5 (14 Oct)             CE10295 main body too long
  Day of Week Profile                   compiles
  Hollow v3 pre-split, drawSh's if      CE10205 if statement too long (drawSg's if, slightly smaller, passed)
Targets: total (hi) <= 90k; main body <= 62.4k (13 Oct Gran Rey Cero, ok; v5 at 68.1k failed);
if blocks <= 37k (drawSg's 41.2k passed, drawSh's 47.2k failed). Main and if figures use the higher end.

Usage: python3 pine_size.py file.pine [more.pine ...] [--top N] [--ifs N] [--fns N]
  --top N  the N string variables costing most (length x uses)
  --ifs N  the N largest if blocks (estimated IL)
  --fns N  the N largest functions (estimated IL)
"""
import re
import sys

ENDS = ((0.30, 1.445), (1.21, 1.228))      # (c, s) at the two ends of the fitted line, s per UTF-8 byte
C_CODE, C_STR = ENDS[1]
LIMIT_TOTAL, TARGET_TOTAL = 100256, 90000
# main body and if block: TradingView's limits are unpublished; these are the estimates (hi end) of the largest
# that compiled and the smallest that failed
MAIN_OK, MAIN_FAIL = 62400, 68100     # Gran Rey Cero 13 Oct (ok) / 14 Oct v5 (CE10295)
IF_OK, IF_FAIL = 41200, 47200         # Hollow pre-split drawSg's if (ok) / drawSh's if (CE10205)

STR = re.compile(r'"(?:[^"\\\n]|\\.)*"|\'(?:[^\'\\\n]|\\.)*\'')
TOK = re.compile(r'[A-Za-z_]\w*|\d+\.?\d*(?:[eE][-+]?\d+)?|==|!=|<=|>=|:=|\+=|-=|\*=|/=|=>|\S')
FN = re.compile(r'^(?:export\s+)?(?:method\s+)?([A-Za-z_]\w*)\s*\(([^)]*)\)\s*=>')


def strip_comments(line):
    out, i, q = [], 0, None
    while i < len(line):
        c = line[i]
        if q:
            out.append(c)
            if c == '\\':
                out.append(line[i + 1:i + 2])
                i += 2
                continue
            if c == q:
                q = None
        elif c in '"\'':
            q = c
            out.append(c)
        elif line.startswith('//', i):
            break
        else:
            out.append(c)
        i += 1
    return ''.join(out)


def logical(src):
    """Logical lines as (indent, text, first physical line number); continuation lines are joined."""
    out, cur, depth = [], None, 0
    for n, raw in enumerate(src.split('\n'), 1):
        l = strip_comments(raw).rstrip()
        if not l.strip():
            continue
        ind = len(l) - len(l.lstrip(' '))
        body = STR.sub('""', l)
        if cur is not None and (depth > 0 or ind % 4 != 0):
            cur[1] += ' ' + l.strip()
        else:
            if cur is not None:
                out.append(tuple(cur))
            cur = [ind, l.strip(), n]
        depth = max(depth + body.count('(') + body.count('[') - body.count(')') - body.count(']'), 0)
    if cur is not None:
        out.append(tuple(cur))
    return out


def blen(lit):
    """UTF-8 bytes inside a string literal (quotes excluded)."""
    return len(lit[1:-1].encode('utf-8'))


def string_consts(L):
    """Global names that hold a constant string, and their size in bytes after folding."""
    consts, reassigned = {}, set()
    for ind, l, _ in L:
        for m in re.finditer(r'\b([A-Za-z_]\w*)\s*:=', STR.sub('""', l)):
            reassigned.add(m.group(1))
    for ind, l, _ in L:
        if ind:
            continue
        m = re.match(r'^(?:var\s+)?(?:const\s+)?(?:string\s+)?([A-Za-z_]\w*)\s*=\s*(.+)$', l)
        if not m or FN.match(STR.sub('""', l)):
            continue
        name, rhs = m.groups()
        parts = re.split(r'\s*\+\s*', STR.sub(lambda x: '\0%d\0' % blen(x.group(0)), rhs))
        n, ok = 0, True
        for p in parts:
            if re.fullmatch(r'\0(\d+)\0', p):
                n += int(p.strip('\0'))
            elif p in consts:
                n += consts[p]
            else:
                ok = False
                break
        if ok and n > 0:
            consts[name] = n
    return {k: v for k, v in consts.items() if k not in reassigned}


def line_cost(l, consts, declname=None):
    """(source tokens, string bytes, string-variable uses) of one logical line."""
    bare = STR.sub('""', l)
    toks = len(TOK.findall(bare))
    lit = sum(blen(x) for x in STR.findall(l))
    uses = {}
    names = re.findall(r'(?<![.\w])([A-Za-z_]\w*)\b(?!\s*\()', bare)
    for i, t in enumerate(names):
        if t in consts and not (declname == t and i == 0):
            uses[t] = uses.get(t, 0) + 1
    return toks, lit, uses


def analyse(src):
    L = logical(src)
    consts = string_consts(L)
    lines = []
    fname = None
    for ind, l, n in L:
        bare = STR.sub('""', l)
        if ind == 0:
            m = FN.match(bare)
            fname = m.group(1) if m else ('<type>' if bare.startswith('type ') else None)
        decl = re.match(r'^(?:var\s+)?(?:const\s+)?(?:string\s+)?([A-Za-z_]\w*)\s*=(?!=)', l) if ind == 0 else None
        toks, lit, uses = line_cost(l, consts, decl.group(1) if decl else None)
        if decl and decl.group(1) in consts:
            lit, uses = 0, {}          # a constant's text is counted where it is used
        eff = lit + sum(consts[k] * v for k, v in uses.items())
        lines.append(dict(ind=ind, text=l, n=n, fn=fname, toks=toks, eff=eff, uses=uses))
    return L, consts, lines


def il(toks, eff, end=1):
    c, s = ENDS[end]
    return c * toks + s * eff


def if_blocks(lines):
    out = []
    for i, x in enumerate(lines):
        if not re.match(r'^if\b', x['text']):
            continue
        k, t, e, j = x['ind'], 0, 0, i + 1
        while j < len(lines) and (lines[j]['ind'] > k or (lines[j]['ind'] == k and re.match(r'^else\b', lines[j]['text']))):
            t += lines[j]['toks']
            e += lines[j]['eff']
            j += 1
        out.append((il(t, e), x['n'], x['fn'] or 'main', t, e, x['text'][:60]))
    return sorted(out, reverse=True)


def measure(src):
    L, consts, lines = analyse(src)
    t = sum(x['toks'] for x in lines)
    e = sum(x['eff'] for x in lines)
    mt = sum(x['toks'] for x in lines if x['fn'] is None)
    me = sum(x['eff'] for x in lines if x['fn'] is None)
    ifs = if_blocks(lines)
    return dict(lo=il(t, e, 0), hi=il(t, e, 1), main=max(il(mt, me, 0), il(mt, me, 1)),
                maxif=max([max(il(b[3], b[4], 0), il(b[3], b[4], 1)) for b in ifs] or [0]),
                code=t, strings=e, consts=consts, lines=lines, ifs=ifs)


def verdict(m):
    v = []
    v.append('total ' + ('FAIL' if m['hi'] > LIMIT_TOTAL * 0.98 else 'RISK' if m['hi'] > TARGET_TOTAL else 'ok'))
    v.append('main ' + ('FAIL' if m['main'] >= MAIN_FAIL * 0.97 else 'RISK' if m['main'] > MAIN_OK else 'ok'))
    v.append('if ' + ('FAIL' if m['maxif'] >= IF_FAIL * 0.97 else 'RISK' if m['maxif'] > IF_OK * 0.9 else 'ok'))
    return v


def report(path, top=0, nifs=0, nfns=0):
    m = measure(open(path, encoding='utf-8').read())
    print('%-30s IL %6.0f-%6.0f  main %6.0f  max if %6.0f  [%s]  code %6d  strings %6d B' % (
        path.split('/')[-1], m['lo'], m['hi'], m['main'], m['maxif'], ', '.join(verdict(m)), m['code'], m['strings']))
    lines, consts = m['lines'], m['consts']
    if top:
        u = {}
        for x in lines:
            for k, v in x['uses'].items():
                u[k] = u.get(k, 0) + v
        for r in sorted(((consts[k] * u.get(k, 0), k, consts[k], u.get(k, 0)) for k in consts), reverse=True)[:top]:
            print('      %7d  %-14s %5d bytes x %d uses' % r)
    if nfns:
        fns = {}
        for x in lines:
            if x['fn'] and x['fn'] != '<type>':
                f = fns.setdefault(x['fn'], [0, 0])
                f[0] += x['toks']
                f[1] += x['eff']
        for k, (t, e) in sorted(fns.items(), key=lambda kv: -il(*kv[1]))[:nfns]:
            print('      fn %-16s IL %6.0f  (code %5d, strings %6d)' % (k, il(t, e), t, e))
    for b in m['ifs'][:nifs]:
        print('      if L%-5d in %-12s IL %6.0f  (code %5d, strings %6d)  %s' % (b[1], b[2], b[0], b[3], b[4], b[5]))
    return m


if __name__ == '__main__':
    args = sys.argv[1:]
    opt = {}
    for k in ('--top', '--ifs', '--fns'):
        if k in args:
            i = args.index(k)
            opt[k] = int(args[i + 1])
            del args[i:i + 2]
    for p in args:
        report(p, opt.get('--top', 0), opt.get('--ifs', 0), opt.get('--fns', 0))
