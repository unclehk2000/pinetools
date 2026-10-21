"""checklib: a library must not read any of the source indicator's globals except through hmS / hmC / hmF.
For every function in the generated library, any identifier that names a State, Cfg or Feed field of the source but is
not declared in that function (or a parameter), and is not a field access or a named argument, is reported.
Also reports input.* / request.* calls, and plot / bgcolor / fill inside functions.
Usage: python3 checklib.py spec.json"""
import re, sys, json
sys.argv_saved = sys.argv
import os
HERE = os.path.dirname(os.path.abspath(__file__))
exec(open(os.path.join(HERE, 'pine2lib.py')).read().split("if __name__ == '__main__':")[0])

spec = json.load(open(sys.argv_saved[1]))
L = Lib(spec)
L.build()
G = set(L.state) | set(L.inputs) | set(L.feed)
txt = open(_out(spec['out']), encoding='utf-8').read().split('\n')
bad = 0
fn, params, local = None, set(), set()
for no, ln in enumerate(txt, 1):
    if not ln.strip() or ln.lstrip().startswith('//'):
        continue
    if indent(ln) == 0:
        m = re.match(r'^(?:export\s+)?([A-Za-z_]\w*)\s*\((.*)\)\s*=>', code_of(ln))
        if m:
            fn = m.group(1)
            params = set(params_of(m.group(2)))
            local = set()
        elif not ln.startswith(' '):
            fn = None
    if re.search(r'\binput\.\w+\(|\brequest\.\w+\(', code_of(ln)):
        print('%d: input/request in library: %s' % (no, ln.strip()[:100])); bad += 1
    if fn and re.match(r'^\s+(plot|bgcolor|fill|plotshape|hline)\(', code_of(ln)):
        print('%d: plot in a function: %s' % (no, ln.strip()[:100])); bad += 1
    if fn is None:
        continue
    c = code_of(ln)
    d = decl_of(c)
    if d and d[3] == '=':
        local.update(d[0])
    m = FOR_EQ.match(c)
    if m:
        local.add(m.group(1))
    m = FOR_IN.match(c)
    if m:
        local.update(x.strip() for x in (m.group(1) or m.group(2)).split(','))
    toks = tokenize(ln)
    depth = 0
    for i, (k, t) in enumerate(toks):
        if k == 'o':
            depth += t in '(['
            depth -= t in ')]'
        if k != 'i' or t not in G or t in params or t in local:
            continue
        prev = next((toks[j] for j in range(i - 1, -1, -1) if toks[j][1].strip()), None)
        if prev and prev[1] == '.':
            continue
        nxt = [toks[j] for j in range(i + 1, min(i + 4, len(toks))) if toks[j][1].strip()]
        if depth > 0 and nxt and nxt[0][1] == '=' and not (len(nxt) > 1 and nxt[1][1] == '='):
            continue
        print('%d: %s reads global %s: %s' % (no, fn, t, ln.strip()[:110])); bad += 1
# CE10237 (full compile only): every argument of an exported function must be used
for i, ln in enumerate(txt):
    m = re.match(r'^export\s+(\w+)\(([^)]*)\)\s*=>(.*)$', ln)
    if not m:
        continue
    j = i + 1
    while j < len(txt) and (txt[j].startswith(' ') or not txt[j].strip()):
        j += 1
    body = m.group(3) + '\n' + '\n'.join(code_of(l) for l in txt[i + 1:j])
    for p_ in [x.strip().split()[-1] for x in m.group(2).split(',') if x.strip()]:
        if not re.search(r'(?<![.\w])' + p_ + r'\b', body):
            print('%d: exported %s() never uses its argument %s (CE10237)' % (i + 1, m.group(1), p_)); bad += 1
print('checklib', spec['lib'], 'problems', bad)
