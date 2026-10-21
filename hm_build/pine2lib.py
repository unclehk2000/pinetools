"""pine2lib: turn one of the calendar indicators (Desgarrón, Vizard, Hollow, Gran Rey Cero) into a Pine v6 library that
Hueco Mundo imports.

What it does
- inputs                     → fields of `export type Cfg` (Hueco Mundo passes its own inputs in)
- request.security() results → fields of `export type Feed` (Hueco Mundo makes the requests once, for every module)
- every other global         → fields of `export type State` (Hueco Mundo holds one `var` State per module)
- string / number constants  → `const` globals (exported functions may read consts)
- functions                  → library functions; any that read a global get `hmS` / `hmC` / `hmF` parameters
- the global code            → exported step functions, split at the section markers, run in order on every bar
- plot() / bgcolor()         → their values go into State fields; Hueco Mundo draws them
- x[1] on a global           → a `x_1` field set at the start of each bar
- barstate.islast            → (barstate.islast and hmC.on): only the module Hueco Mundo shows draws its cards

Usage: python3 pine2lib.py spec.json   (see make_libs.py)"""
import re, json, sys
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__)) if '__file__' in globals() else '.'
_SRC = _os.environ.get('HM_SRC', _os.path.join(_HERE, 'src'))
_OUTD = _os.environ.get('HM_OUT', _HERE)
def _src(p): return p if _os.path.isabs(p) else _os.path.join(_SRC, p)
def _out(p): return p if _os.path.isabs(p) else _os.path.join(_OUTD, p)

KW = set('''if else for in to by while switch and or not true false na var varip import export method type const simple series
break continue return enum'''.split())
TYPES = set('int float bool string color line label box table polyline linefill array matrix map chart.point'.split())
IDENT = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')
NUM = re.compile(r'\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|\.\d+')


def tokenize(line):
    """[(kind, text)] with kind in s (string), c (comment), i (identifier), n (number), h (#hex colour), o (other)"""
    out, i, L = [], 0, len(line)
    while i < L:
        ch = line[i]
        if ch in '"\'':
            j = i + 1
            while j < L and line[j] != ch:
                j += 2 if line[j] == '\\' else 1
            out.append(('s', line[i:j + 1])); i = j + 1
        elif line.startswith('//', i):
            out.append(('c', line[i:])); break
        elif ch == '#' and i + 1 < L and re.match(r'[0-9a-fA-F]', line[i + 1]):
            m = re.match(r'#[0-9a-fA-F]+', line[i:]); out.append(('h', m.group(0))); i += len(m.group(0))
        elif ch.isdigit() or (ch == '.' and i + 1 < L and line[i + 1].isdigit()):
            m = NUM.match(line, i); out.append(('n', m.group(0))); i = m.end()
        elif ch.isalpha() or ch == '_':
            m = IDENT.match(line, i); out.append(('i', m.group(0))); i = m.end()
        else:
            out.append(('o', ch)); i += 1
    return out


def code_of(line):
    """the line without its comment, strings blanked"""
    return ''.join('""' if k == 's' else ('' if k == 'c' else t) for k, t in tokenize(line))


def indent(line):
    return len(line) - len(line.lstrip(' '))


def logical_lines(lines):
    """group physical lines into statements: continuation lines (indent not a multiple of 4, or inside open brackets)"""
    out, cur, depth = [], None, 0
    for ln in lines:
        stripped = ln.strip()
        ind = indent(ln)
        cont = cur is not None and stripped != '' and not stripped.startswith('//') and (depth > 0 or ind % 4 != 0)
        if cont:
            cur.append(ln)
        else:
            if cur is not None:
                out.append(cur)
            cur = [ln]
            depth = 0
        c = code_of(ln)
        depth += c.count('(') + c.count('[') - c.count(')') - c.count(']')
        if depth < 0:
            depth = 0
    if cur is not None:
        out.append(cur)
    return out


DECL_T = re.compile(r'^(\s*)(?:(var|varip)\s+)?(?:(?:const|simple|series)\s+)?([A-Za-z_][\w.]*(?:<[\w.,\s]*>)?)\s+([A-Za-z_]\w*)\s*(=)(?!=)')
DECL_U = re.compile(r'^(\s*)(?:(var|varip)\s+)?([A-Za-z_]\w*)\s*(=|:=|\+=|-=|\*=|/=)(?!=)')
TUPLE = re.compile(r'^(\s*)\[([^\]]+)\]\s*=(?!=)')
FOR_EQ = re.compile(r'^\s*for\s+([A-Za-z_]\w*)\s*=')
FOR_IN = re.compile(r'^\s*for\s+(?:\[([^\]]+)\]|([A-Za-z_]\w*))\s+in\b')
FUNC = re.compile(r'^([A-Za-z_]\w*)\s*\((.*)\)\s*=>(.*)$')


def decl_of(code):
    """(name(s), is_var, type or None, op) if the statement declares or assigns; else None"""
    m = TUPLE.match(code)
    if m:
        return ([x.strip() for x in m.group(2).split(',')], False, None, '=')
    m = DECL_T.match(code)
    if m and m.group(3) not in KW:
        return ([m.group(4)], bool(m.group(2)), m.group(3), '=') if m.group(2) != 'varip' else ([m.group(4)], 'varip', m.group(3), '=')
    m = DECL_U.match(code)
    if m and m.group(3) not in KW:
        return ([m.group(3)], bool(m.group(2)) if m.group(2) != 'varip' else 'varip', None, m.group(4))
    return None


def params_of(sig):
    names = []
    depth, cur = 0, ''
    for ch in sig + ',':
        if ch in '(<[':
            depth += 1
        elif ch in ')>]':
            depth -= 1
        if ch == ',' and depth == 0:
            p = cur.split('=')[0].strip()
            if p:
                names.append(p.split()[-1])
            cur = ''
        else:
            cur += ch
    return names


ELEM_MAX = 200     # TradingView's limit is 254 per function; keep headroom


class Lib:
    def __init__(self, spec):
        self.spec = spec
        self.src = open(_src(spec['src']), encoding='utf-8').read()
        self.lines = self.src.split('\n')
        self.inputs = {}          # name → (type, default, line)
        self.consts = {}          # name → (type, statement lines)
        self.state = {}           # name → type
        self.state_default = {}   # name → const default
        self.feed = dict(spec['feed'])   # name → type
        self.hist = set()         # globals used as x[1]
        self.funcs = []           # (name, params, body lines)
        self.types = []           # type blocks
        self.code = []            # (section, [logical lines]) global code
        self.plots = []
        self.unknown = []

    # ── pass 1: classify top-level statements
    def classify(self):
        sp = self.spec
        stmts = logical_lines(self.lines)
        i, section = 0, 'head'
        drop = [re.compile(x) for x in sp.get('drop', [])]
        while i < len(stmts):
            st = stmts[i]
            first = st[0]
            code = code_of(first)
            if first.startswith('// ═══'):
                section = first.strip('/ ═').strip() or section
                self.code.append((section, [st]))
                i += 1; continue
            if first.strip() == '' or first.lstrip().startswith('//'):
                self.code.append((section, [st])); i += 1; continue
            if indent(first) != 0:
                raise SystemExit('unexpected indented top-level line: ' + first)
            if any(d.search(first) for d in drop):
                i += 1
                while i < len(stmts) and stmts[i][0].strip() and indent(stmts[i][0]) > 0:
                    i += 1
                continue
            m = FUNC.match(code)
            if m or code.startswith('method '):
                body = [st]
                i += 1
                while i < len(stmts) and (stmts[i][0].strip() == '' or indent(stmts[i][0]) > 0 or stmts[i][0].startswith('//') and False):
                    if stmts[i][0].strip() == '':
                        # a blank line ends a function only if the next statement is top-level
                        j = i
                        while j < len(stmts) and stmts[j][0].strip() == '':
                            j += 1
                        if j >= len(stmts) or indent(stmts[j][0]) == 0:
                            break
                    body.append(stmts[i]); i += 1
                self.funcs.append((m.group(1), params_of(m.group(2)), body, section))
                continue
            if code.startswith('type '):
                body = [st]; i += 1
                while i < len(stmts) and stmts[i][0].strip() and indent(stmts[i][0]) > 0:
                    body.append(stmts[i]); i += 1
                self.types.append(body); continue
            if code.startswith('indicator(') or code.startswith('max_bars_back('):
                i += 1; continue
            # a whole top-level statement with its indented block
            block = [st]; i += 1
            while i < len(stmts) and (indent(stmts[i][0]) > 0 or stmts[i][0].strip() == '' and i + 1 < len(stmts) and indent(stmts[i + 1][0]) > 0):
                block.append(stmts[i]); i += 1
            full = ' '.join(code_of(l) for l in st)
            if re.match(r'^\w+\s*=\s*input\.', full):
                name = full.split('=')[0].strip()
                kind = re.search(r'input\.(\w+)', full).group(1)
                ty = {'int': 'int', 'float': 'float', 'bool': 'bool', 'string': 'string', 'color': 'color', 'symbol': 'string',
                      'timeframe': 'string', 'session': 'string', 'source': 'float', 'time': 'int', 'price': 'float',
                      'text_area': 'string'}[kind]
                raw = ' '.join(l.strip() for l in st)
                dm = re.search(r'input\.\w+\((.+)$', raw)
                default = self.first_arg(dm.group(1))
                self.inputs[name] = (ty, default, st)
                continue
            if 'request.security' in full or 'request.' in full and re.search(r'request\.\w+\(', full):
                d = decl_of(code)
                for n in d[0]:
                    if n not in self.feed:
                        raise SystemExit('feed type missing for ' + n)
                continue
            if re.match(r'^(plot|bgcolor|fill|plotshape|plotchar|hline)\(', full):
                self.plots.append((section, st))
                self.code.append((section, [['__PLOT__%d' % (len(self.plots) - 1)]]))
                continue
            d = decl_of(code)
            if d and len(block) == 1 and d[1] != 'varip' and d[3] == '=' and len(d[0]) == 1 and d[0][0] not in sp.get('not_const', []) \
                    and d[0][0] not in self.reassigned() \
                    and (not d[1] or d[2] == 'string'):
                rhs = ' '.join(code_of(l) for l in st).split('=', 1)[1].strip()
                parts = [x.strip() for x in rhs.split('+')]
                if all(x == '""' or x in self.consts and self.consts[x][0] == 'string' for x in parts) and '""' in parts + [''] or \
                        all(x == '""' or x in self.consts and self.consts[x][0] == 'string' for x in parts) and len(parts) > 1:
                    self.consts[d[0][0]] = ('string', [st[0].replace('var string ', '', 1).replace('var ', '', 1)] + st[1:])
                    continue
                if not d[1] and re.fullmatch(r'-?\d+(\.\d+)?', rhs):
                    ty = d[2] or ('float' if '.' in rhs else 'int')
                    self.consts[d[0][0]] = (ty, st)
                    continue
            self.code.append((section, block))

    def reassigned(self):
        """names that are ever reassigned (:=, +=, ...) anywhere in the source: these can't be library consts"""
        if not hasattr(self, '_reasg'):
            self._reasg = set(re.findall(r'(?<![.\w])([A-Za-z_]\w*)\s*(?::=|\+=|-=|\*=|/=)', '\n'.join(code_of(l) for l in self.lines)))
        return self._reasg

    @staticmethod
    def first_arg(s):
        depth, out, q = 0, '', None
        for ch in s:
            if q:
                out += ch
                if ch == q:
                    q = None
                continue
            if ch in '"\'':
                q = ch; out += ch; continue
            if ch in '([':
                depth += 1
            elif ch in ')]':
                if depth == 0:
                    break
                depth -= 1
            elif ch == ',' and depth == 0:
                break
            out += ch
        return out.strip()

    # ── pass 2: globals declared by the global code (top level only) and their types
    def collect_state(self):
        sp = self.spec
        tymap = sp.get('types', {})
        for sec, block in self.code:
            st = block[0]
            if st[0].startswith('__PLOT__') or st[0].strip() == '' or st[0].lstrip().startswith('//'):
                continue
            code = code_of(st[0])
            d = decl_of(code)
            if not d or d[3] != '=':
                continue
            for n in d[0]:
                if n in self.inputs or n in self.feed:
                    continue
                if n in self.state:
                    continue
                ty = tymap.get(n) or d[2] or self.infer(' '.join(code_of(l) for l in st).split('=', 1)[1])
                if ty is None or ty == 'na':
                    self.unknown.append((n, st[0][:140]))
                    ty = 'UNKNOWN'
                self.state[n] = ty
                if d[1] in (True, 'varip'):
                    rhs = ' '.join(l.strip() for l in st).split('=', 1)[1]
                    rhs = re.sub(r'\s*//.*$', '', rhs).strip()
                    if self.is_const_expr(rhs):
                        self.state_default[n] = rhs
                    if d[1] == 'varip':
                        self.state_default.setdefault(n, 'na')
                        self.state_default[n] = ('VARIP', self.state_default[n])
        for n, ty in sp.get('extra_state', {}).items():
            self.state[n] = ty

    def is_const_expr(self, rhs):
        if rhs in ('na', 'true', 'false'):
            return True
        if re.fullmatch(r'-?\d+(\.\d+)?', rhs) or re.fullmatch(r'"[^"]*"', rhs) or re.fullmatch(r'#[0-9a-fA-F]{6,8}', rhs):
            return True
        return False

    def infer(self, rhs):
        r = rhs.strip()
        depth, qpos, cpos = 0, -1, -1
        for i, ch in enumerate(r):
            if ch in '([':
                depth += 1
            elif ch in ')]':
                depth -= 1
            elif ch == '?' and depth == 0 and qpos < 0:
                qpos = i
            elif ch == ':' and depth == 0 and qpos >= 0 and cpos < 0 and r[i + 1:i + 2] != '=':
                cpos = i
        if qpos >= 0 and cpos > qpos:
            t = self.infer(r[qpos + 1:cpos])
            if t is None or t == 'na':
                t = self.infer(r[cpos + 1:])
            return t
        if r == 'na':
            return 'na'
        m = re.match(r'array\.new<([\w.]+)>\(|array\.new_(\w+)\(', r)
        if m:
            return 'array<%s>' % (m.group(1) or m.group(2))
        if re.match(r'(\d*\.\d+|\d+)\s*\*\s*color\.[rgb]\(', r):
            return 'float'
        if re.search(r'#[0-9a-fA-F]{6}|color\.(new|rgb|from_gradient)|\bchart\.(fg|bg)_color', r):
            return 'color'
        if re.search(r'^(size|position|text|extend|xloc|yloc|font)\.|^(line|label)\.style_', r):
            return 'string'
        if re.search(r'==|!=|<=|>=|\band\b|\bor\b|^not\b|\bstr\.(startswith|endswith|contains)\(|^na\(|\.includes\(|^(true|false)$|^barstate\.|^timeframe\.is', r):
            return 'bool'
        if re.search(r'(?<![<-])>(?!=)|<(?![\w.]+>)', r) and not re.search(r'array<|matrix<|map<', r):
            return 'bool'
        if re.match(r'(int\(|math\.(floor|ceil|round)\(|\w+\.size\(\)|bar_index\b|time\b|dateKey\(|anchorKey\(|keyAt\(|keyTime\(|addDays\(|last_bar_time\b|timenow\b)', r):
            return 'int'
        if re.match(r'(str\.|")', r):
            return 'string'
        if re.match(r'(-?\d*\.\d+$|float\(|math\.(max|min|abs|sqrt|log|pow|avg|sum)\(|nz\()', r):
            return 'float'
        if re.fullmatch(r'-?\d+', r):
            return 'int'
        if re.fullmatch(r'-?\d+\.\d*', r):
            return 'float'
        if r.startswith('"'):
            return 'string'
        if re.search(r'#[0-9a-fA-F]{6}|color\.(new|rgb|from_gradient)|\bchart\.(fg|bg)_color', r):
            return 'color'
        if re.search(r'\bsize\.|\bposition\.|line\.style_|label\.style_|text\.align_|extend\.|xloc\.', r):
            return 'string'
        return None

    # ── rename identifiers in one logical statement
    def rename(self, st, local, in_func):
        out = []
        for ln in st:
            toks = tokenize(ln)
            res, depth = [], 0
            for idx, (k, t) in enumerate(toks):
                if k == 'o':
                    if t in '([':
                        depth += 1
                    elif t in ')]':
                        depth -= 1
                if k != 'i':
                    res.append(t); continue
                prev = next((toks[j] for j in range(idx - 1, -1, -1) if toks[j][1].strip()), None)
                nxt = [toks[j] for j in range(idx + 1, min(idx + 4, len(toks))) if toks[j][1].strip()]
                if prev and prev[1] == '.':
                    res.append(t); continue
                if depth > 0 and nxt and nxt[0][1] == '=' and not (len(nxt) > 1 and nxt[1][1] == '='):
                    res.append(t); continue            # named argument
                if t in local:
                    res.append(t); continue
                rep = self.ref(t)
                if rep is None:
                    res.append(t); continue
                # history reference x[1]
                j = idx + 1
                if j + 2 < len(toks) and toks[j] == ('o', '[') and toks[j + 1][0] == 'n' and toks[j + 2] == ('o', ']') and \
                        not (prev and prev[1] in ('<',)):
                    nback = toks[j + 1][1]
                    if nback != '1':
                        raise SystemExit('history [%s] on global %s' % (nback, t))
                    self.hist.add(t)
                    res.append(rep + '_1')
                    toks[j] = ('o', ''); toks[j + 1] = ('n', ''); toks[j + 2] = ('o', '')
                    continue
                res.append(rep)
            out.append(''.join(res))
        return out

    def ref(self, t):
        if t == '__ON__':
            return 'hmC.on'
        if t in self.consts:
            return None
        if t in self.inputs:
            return 'hmC.' + t
        if t in self.feed:
            return 'hmF.' + t
        if t in self.state:
            return 'hmS.' + t
        return None

    # ── functions: which need hmS / hmC / hmF
    def func_needs(self):
        need = {}
        calls = {}
        fnames = {f[0] for f in self.funcs}
        for name, params, body, sec in self.funcs:
            local = set(params)
            used = set()
            cl = set()
            for st in body:
                c = code_of(st[0]) if st else ''
                d = decl_of(c)
                if d:
                    local.update(d[0])
                m = FOR_EQ.match(c)
                if m:
                    local.add(m.group(1))
                m = FOR_IN.match(c)
                if m:
                    local.update([x.strip() for x in (m.group(1) or m.group(2)).split(',')])
            for st in body:
                for ln in st:
                    toks = tokenize(ln)
                    for idx, (k, t) in enumerate(toks):
                        if k != 'i' or t in local:
                            continue
                        prev = next((toks[j] for j in range(idx - 1, -1, -1) if toks[j][1].strip()), None)
                        if prev and prev[1] == '.':
                            continue
                        r = self.ref(t)
                        if r:
                            used.add(r.split('.')[0])
                        if t in fnames and t != name:
                            nx = next((toks[j] for j in range(idx + 1, len(toks)) if toks[j][1].strip()), None)
                            if nx and nx[1] == '(':
                                cl.add(t)
            need[name] = used
            calls[name] = cl
        changed = True
        while changed:
            changed = False
            for f in need:
                for g in calls[f]:
                    if not need[g] <= need[f]:
                        need[f] |= need[g]; changed = True
        self.need = need

    def inject_calls(self, text_lines):
        """add hmS / hmC / hmF arguments to calls of functions that need them"""
        fnames = {f for f in self.need if self.need[f]}
        out = []
        for ln in text_lines:
            toks = tokenize(ln)
            res = []
            for idx, (k, t) in enumerate(toks):
                res.append(t)
                if k == 'i' and t in fnames:
                    prev = next((toks[j] for j in range(idx - 1, -1, -1) if toks[j][1].strip()), None)
                    if prev and prev[1] == '.':
                        continue
                    if idx + 1 < len(toks) and toks[idx + 1] == ('o', '('):
                        args = [a for a in ('hmS', 'hmC', 'hmF') if a in self.need[t]]
                        nxt = next((toks[j] for j in range(idx + 2, len(toks)) if toks[j][1].strip()), None)
                        sep = '' if nxt and nxt[1] == ')' else ', '
                        res.append('(' + ', '.join(args) + sep)
                        toks[idx + 1] = ('o', '')
            out.append(''.join(res))
        return out

    # ── emit
    def emit_func(self, name, params, body):
        local = set(params)
        out = []
        scopes = [(0, set(params))]
        for st in body:
            first = st[0]
            ind = indent(first) if first.strip() else None
            if ind is not None:
                while len(scopes) > 1 and ind <= scopes[-1][0] and not first.lstrip().startswith('//'):
                    scopes.pop()
            c = code_of(first)
            loc = set().union(*[s for _, s in scopes])
            d = decl_of(c)
            newn = set()
            if d and d[3] == '=':
                newn.update(d[0])
            m = FOR_EQ.match(c)
            if m:
                newn.add(m.group(1))
            m = FOR_IN.match(c)
            if m:
                newn.update([x.strip() for x in (m.group(1) or m.group(2)).split(',')])
            if st is body[0]:
                # the signature line: rename only the body part after =>
                m = FUNC.match(code_of(first))
                head, tail = first.split('=>', 1)
                args = [a for a in ('hmS', 'hmC', 'hmF') if a in self.need[name]]
                typed = {'hmS': 'State hmS', 'hmC': 'Cfg hmC', 'hmF': 'Feed hmF'}
                h0 = head.rstrip()
                pstart = h0.index('(') + 1
                inner = h0[pstart:h0.rindex(')')]
                new_inner = ', '.join([typed[a] for a in args] + ([inner] if inner.strip() else []))
                head = h0[:pstart] + new_inner + ')'
                tail_r = self.rename([tail], loc | newn, True)[0]
                out.append([head + ' =>' + tail_r])
            else:
                out.append(self.rename(st, loc | newn, True))
            if ind is not None and not first.lstrip().startswith('//'):
                if newn:
                    scopes[-1][1].update(newn)
                # a block opener: the next deeper lines form a new scope
                scopes.append((ind, set()))
        flat = [l for st in out for l in st]
        if len(out[0]) == 1:
            # the signature line: inject into the body after => only (not into the function's own header)
            head, tail = flat[0].split('=>', 1)
            return [head + '=>' + self.inject_calls([tail])[0]] + self.inject_calls(flat[1:])
        return self.inject_calls(flat)

    def emit_code(self, block):
        """one top-level statement (with its block) of the global code → lines inside a step function"""
        out = []
        st0 = block[0]
        c0 = code_of(st0[0])
        d = decl_of(c0)
        scopes = [(0, set())]
        for bi, st in enumerate(block):
            first = st[0]
            if first.startswith('__PLOT__'):
                k = int(first[8:])
                out += self.emit_plot(k)
                continue
            ind = indent(first) if first.strip() else None
            if ind is not None and not first.lstrip().startswith('//'):
                while len(scopes) > 1 and ind <= scopes[-1][0]:
                    scopes.pop()
            c = code_of(first)
            loc = set().union(*[s for _, s in scopes])
            dd = decl_of(c)
            newn = set()
            if bi > 0 and dd and dd[3] == '=':
                newn.update(dd[0])
            m = FOR_EQ.match(c)
            if m:
                newn.add(m.group(1))
            m = FOR_IN.match(c)
            if m:
                newn.update([x.strip() for x in (m.group(1) or m.group(2)).split(',')])
            if bi == 0 and dd and dd[3] == '=' and ind == 0:
                # a global declaration
                names = dd[0]
                if TUPLE.match(c):
                    tmp = ['t_' + n for n in names]
                    rhs = first.split('=', 1)[1]
                    r = self.rename([rhs] + st[1:], loc, False)
                    out.append('[' + ', '.join(tmp) + '] =' + r[0])
                    out += r[1:]
                    for n, t in zip(names, tmp):
                        out.append('hmS.%s := %s' % (n, t))
                else:
                    n = names[0]
                    rhs_lines = [first.split('=', 1)[1]] + st[1:]
                    r = self.rename(rhs_lines, loc, False)
                    if dd[1]:
                        # var: only on the first bar (constant defaults live in the State type)
                        if n in self.state_default:
                            continue
                        if len(block) > 1:
                            raise SystemExit('var with a block initialiser: ' + first[:100])
                        out.append('if barstate.isfirst')
                        out.append('    hmS.%s :=%s' % (n, r[0]))
                        out += ['    ' + x for x in r[1:]]
                        continue
                    out.append('hmS.%s :=%s' % (n, r[0]))
                    out += r[1:]
            else:
                out += self.rename(st, loc | newn, False)
            if ind is not None and not first.lstrip().startswith('//'):
                if newn:
                    scopes[-1][1].update(newn)
                scopes.append((ind, set()))
        return out

    def emit_plot(self, k):
        sec, st = self.plots[k]
        raw = ' '.join(l.strip() for l in st)
        fn = raw.split('(', 1)[0]
        inner = raw[len(fn) + 1:raw.rindex(')')]
        args = self.split_args(inner)
        val = args[0]
        r = self.rename([val], set(), False)[0]
        out = ['hmS.%s%d := %s' % ('p' if fn == 'plot' else 'bg', k, r)]
        self.state['%s%d' % ('p' if fn == 'plot' else 'bg', k)] = 'float' if fn == 'plot' else 'color'
        # a series colour argument
        for a in args[1:]:
            m = re.match(r'color\s*=\s*(.+)$', a)
            if m and fn == 'plot' and not re.fullmatch(r'#[0-9a-fA-F]+', m.group(1).strip()):
                self.state['pc%d' % k] = 'color'
                out.append('hmS.pc%d := %s' % (k, self.rename([m.group(1)], set(), False)[0]))
        return out

    @staticmethod
    def split_fn(src, fname, marker):
        """split a last-bar drawing function `fname() =>` (one if block) at a body-level marker line: the rest becomes
        `fnameB()` under the same if, with the body-level locals it uses copied in (Pine caps the size of one if block)"""
        L = src.split('\n')
        a = L.index(fname + '() =>')
        call = next(k for k in range(a + 1, len(L)) if L[k] == fname + '()')
        be = call - 1
        assert L[be].strip() == 'true', L[be]
        m = next(k for k in range(a + 2, be) if L[k] == marker)
        cond = L[a + 1]
        part1, part2 = L[a:m], L[m:be]
        decl = []
        for ln in part1[2:]:
            if indent(ln) == 8 and not ln.strip().startswith('//'):
                d = decl_of(code_of(ln))
                if d and d[3] == '=':
                    decl.append((d[0], ln))
        used = set(t for ln in part2 for k_, t in tokenize(ln) if k_ == 'i')
        need = set()
        changed = True
        while changed:
            changed = False
            for names, ln in decl:
                if any(n in used for n in names) and not set(names) <= need:
                    need.update(names)
                    used.update(t for k_, t in tokenize(ln) if k_ == 'i')
                    changed = True
        carry = [ln for names, ln in decl if set(names) & need]
        new = part1 + ['    true', fname + '()', fname + 'B() =>', cond] + carry + part2 + ['    true', fname + 'B()']
        return '\n'.join(L[:a] + new + L[call + 1:])

    @staticmethod
    def split_args(s):
        out, depth, cur, q = [], 0, '', None
        for ch in s:
            if q:
                cur += ch
                if ch == q:
                    q = None
                continue
            if ch in '"\'':
                q = ch; cur += ch; continue
            if ch in '([':
                depth += 1
            elif ch in ')]':
                depth -= 1
            if ch == ',' and depth == 0:
                out.append(cur.strip()); cur = ''
            else:
                cur += ch
        if cur.strip():
            out.append(cur.strip())
        return out

    def build(self):
        sp = self.spec
        # barstate.islast → (barstate.islast and hmC.on)
        self.src = self.src.replace('barstate.islast', '(barstate.islast and __ON__)')
        for a, b in sp.get('pre', []):
            n = self.src.count(a)
            if n != 1 and not (isinstance(b, str) and a.startswith('ALL:')):
                raise SystemExit('pre-patch count %d: %s' % (n, a[:100]))
            self.src = self.src.replace(a, b)
        for fname, marker in sp.get('splits', []):
            self.src = self.split_fn(self.src, fname, marker)
        self.lines = self.src.split('\n')
        self.classify()
        self.inputs['on'] = ('bool', 'true', None)
        for n_, (t_, d_) in sp.get('extra_inputs', {}).items():
            self.inputs[n_] = (t_, d_, None)
        self.inputs['__ON__'] = ('bool', 'true', None)
        self.collect_state()
        if self.unknown:
            for u in self.unknown:
                print('UNKNOWN TYPE', u)
            raise SystemExit('add these to "types" in the spec')
        # history references: a first pass to collect them
        for name, params, body, sec in self.funcs:
            pass
        self.func_needs()
        # functions
        fout = []
        for name, params, body, sec in self.funcs:
            fout += self.emit_func(name, params, body)
        # global code → steps
        steps, cur, cur_sec, n_lines = [], [], None, 0
        for sec, block in self.code:
            st0 = block[0][0]
            if st0.startswith('// ═══') and cur and n_lines > 40:
                steps.append((cur_sec, cur)); cur, n_lines = [], 0
            if st0.startswith('// ═══'):
                cur_sec = sec
            if st0.strip() == '' or st0.lstrip().startswith('//'):
                continue                      # comments stay in the source indicator
            lines = self.emit_code(block)
            lines = self.inject_calls(lines)
            if n_lines + len(lines) > sp.get('max_step', 220) and n_lines > 0:
                steps.append((cur_sec, cur)); cur, n_lines = [], 0
            cur += lines
            n_lines += sum(1 for l in lines if l.strip() and not l.lstrip().startswith('//'))
        if cur:
            steps.append((cur_sec, cur))
        self.steps = steps
        self.fout = fout

    def text(self):
        sp = self.spec
        o = ['//@version=6',
             '// This Source Code Form is subject to the terms of the Mozilla Public License 2.0 at https://mozilla.org/MPL/2.0/',
             '// © Unclehk2000']
        o += ['// ' + l for l in sp['header']]
        o.append('library("%s", overlay = false)' % sp['lib'])
        o.append('')
        o.append('// ═══════════════════════════════════════════════════════════════ Constants')
        for n, (ty, st) in self.consts.items():
            first = st[0]
            body = first.split('=', 1)[1]
            o.append('const %s %s =%s' % (ty, n, body))
            o += st[1:]
        o.append('')
        o.append('// ═══════════════════════════════════════════════════════════════ Types')
        for tb in self.types:
            lines = [l for st in tb for l in st]
            lines[0] = 'export ' + lines[0]
            o += lines
        o.append('// @type Settings: Hueco Mundo passes its inputs in. `on` = this module draws its cards (the one shown).')
        o.append('export type Cfg')
        for n, (ty, dflt, _) in self.inputs.items():
            if n == '__ON__':
                continue
            dv = self.type_default(dflt) if dflt and self.is_const_lit(dflt) else None
            o.append('    %s %s%s' % (ty, n, (' = ' + dv) if dv else ''))
        o.append('// @type The chart data Hueco Mundo requests once for every module.')
        o.append('export type Feed')
        for n, ty in self.feed.items():
            o.append('    %s %s' % (ty, n))
        for n in sorted(self.hist):
            if n in self.feed:
                o.append('    %s %s_1' % (self.feed[n], n))
        o.append('// @type Everything the module keeps from bar to bar.')
        # TradingView caps a function at 254 "external elements" (CE10116), and a type's .new() has one parameter per
        # field: int / float / bool / color count 2, anything else 1. State is split into parts of at most ELEM_MAX.
        fields = []
        for n, ty in self.state.items():
            dv = self.state_default.get(n)
            if isinstance(dv, tuple):
                fields.append((n, ty, '    varip %s %s%s' % (ty, n, '' if dv[1] == 'na' else ' = ' + dv[1])))
            else:
                fields.append((n, ty, '    %s %s%s' % (ty, n, '' if dv in (None, 'na') else ' = ' + dv)))
        for n in sorted(self.hist):
            if n in self.state:
                fields.append((n + '_1', self.state[n], '    %s %s_1' % (self.state[n], n)))
        parts, cur, el = [], [], 0
        for f in fields:
            e = 2 if f[1] in ('int', 'float', 'bool', 'color') else 1
            if cur and el + e > ELEM_MAX:
                parts.append(cur)
                cur, el = [], 0
            cur.append(f)
            el += e
        if cur:
            parts.append(cur)
        self.spath = {}
        for k, part in enumerate(parts, 1):
            o.append('// @type Part %d of what the module keeps from bar to bar (State holds the parts).' % k)
            o.append('export type StatePart%d' % k)
            for n, ty, line in part:
                o.append(line)
                self.spath[n] = 's%d.%s' % (k, n)
        o.append('// @type Everything the module keeps from bar to bar, in parts. Make one with newState().')
        o.append('export type State')
        for k in range(1, len(parts) + 1):
            o.append('    StatePart%d s%d' % (k, k))
        o.append('')
        o.append('// ═══════════════════════════════════════════════════════════════ Functions')
        o += self.fout
        o.append('')
        o.append('// ═══════════════════════════════════════════════════════════════ Steps (Hueco Mundo calls them in order on every bar)')
        for k, (sec, lines) in enumerate(self.steps):
            o.append('// @function Step %d: %s' % (k + 1, sec))
            o.append('export step%d(State hmS, Cfg hmC, Feed hmF) =>' % (k + 1))
            if k == 0:
                for n in sorted(self.hist):
                    if n in self.state:
                        o.append('    hmS.%s_1 := hmS.%s' % (n, n))
            for l in lines:
                o.append(('    ' + l) if l.strip() else '')
            o.append('    hmS')
        o += self.inject_calls(sp.get('tail', []))
        o.append('')
        o.append('// @function A new, empty State with all its parts. Hold it with var.')
        o.append('export newState() =>')
        o.append('    State.new(%s)' % ', '.join('StatePart%d.new()' % k for k in range(1, len(set(v.split('.')[0] for v in self.spath.values())) + 1)))
        o.append('')
        o.append('plot(na, "Hueco Mundo module", display = display.none)')
        o = self.route_state(o)
        o = self.trim_exports(o)
        return '\n'.join(o) + '\n'

    def route_state(self, o):
        """hmS.field -> hmS.sK.field (outside strings and comments), now that State is in parts"""
        pat = re.compile(r'(?<![.\w])hmS\.([A-Za-z_]\w*)\b')
        out = []
        for l in o:
            if l.startswith('export type') or l.startswith('// @type'):
                out.append(l)
                continue
            parts = re.split(r'("(?:[^"\\]|\\.)*"|//.*$)', l)
            for i in range(0, len(parts), 2):
                parts[i] = pat.sub(lambda m: 'hmS.' + self.spath.get(m.group(1), m.group(1)), parts[i])
            out.append(''.join(parts))
        return out

    def trim_exports(self, o):
        """TradingView's full compile rejects an exported function with an unused argument (CE10237). Drop hmS / hmC / hmF
        from each exported function that doesn't use it, and record what each one takes (export_args) for the caller."""
        typed = {'hmS': 'State hmS', 'hmC': 'Cfg hmC', 'hmF': 'Feed hmF'}
        self.export_args = {}
        i = 0
        while i < len(o):
            m = re.match(r'^export (\w+)\(([^)]*)\)\s*=>(.*)$', o[i])
            if not m:
                i += 1
                continue
            name, params, rest = m.groups()
            j = i + 1
            while j < len(o) and (o[j].startswith(' ') or o[j].strip() == '' and j + 1 < len(o) and o[j + 1].startswith(' ')):
                j += 1
            body = rest + '\n' + '\n'.join(code_of(l) for l in o[i + 1:j])
            ps = [x.strip() for x in params.split(',') if x.strip()]
            keep = []
            for p_ in ps:
                pn = p_.split()[-1]
                if pn in typed and not re.search(r'(?<![.\w])' + pn + r'\b', body):
                    continue
                keep.append(p_)
            self.export_args[name] = [p_.split()[-1] for p_ in keep]
            o[i] = 'export %s(%s) =>%s' % (name, ', '.join(keep), rest)
            i = j
        return o

    @staticmethod
    def type_default(v):
        """a default a UDT field accepts: color.new(#rrggbb, t) becomes #rrggbbaa (alpha = 255 x (100 - t) / 100)"""
        m = re.fullmatch(r'color\.new\((#[0-9a-fA-F]{6}),\s*(\d+)\)', v.strip())
        if m:
            return '%s%02x' % (m.group(1), int(round(255 * (100 - int(m.group(2))) / 100)))
        return v

    @staticmethod
    def is_const_lit(v):
        return bool(re.fullmatch(r'-?\d+(\.\d+)?|true|false|"[^"]*"|#[0-9a-fA-F]{6,8}|color\.new\(#[0-9a-fA-F]{6}, \d+\)', v.strip()))


if __name__ == '__main__':
    spec = json.load(open(sys.argv[1]))
    L = Lib(spec)
    L.build()
    open(_out(spec['out']), 'w', encoding='utf-8').write(L.text())
    print('inputs', len(L.inputs), 'feed', len(L.feed), 'state', len(L.state), 'consts', len(L.consts), 'funcs', len(L.funcs),
          'steps', len(L.steps), 'hist', sorted(L.hist))
