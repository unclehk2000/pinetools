"""Checks the Pine limits that only TradingView's full compile (Save / Add to chart) enforces and that the light
checker (translate_light) does not:

  CE10116  a function (including a type's .new(), which takes one parameter per field) uses at most 254
           "external elements": int / float / bool / color count 2, any other type 1
  CE10237  an exported library function must use every argument it declares
  plot counts (max 64), request.*() calls in the source (max 40 unique), tables (max 9 shown)

Usage: python3 pine_limits.py file.pine [more.pine ...]
"""
import re
import sys

sys.path.insert(0, __file__.rsplit('/', 1)[0])
from pine_size import STR, logical  # noqa: E402

TWO = ('int', 'float', 'bool', 'color')
LIMIT_EL = 254


def elements(types):
    return sum(2 if t in TWO else 1 for t in types)


def check(path):
    src = open(path, encoding='utf-8').read()
    lines = src.split('\n')
    probs = []
    # types and their fields
    i = 0
    while i < len(lines):
        m = re.match(r'^(?:export\s+)?type\s+(\w+)', lines[i])
        if m:
            name, tys = m.group(1), []
            j = i + 1
            while j < len(lines) and lines[j].startswith(' '):
                f = lines[j].split('//')[0].split()
                if f:
                    tys.append(f[1] if f[0] == 'varip' else f[0])
                j += 1
            el = elements(tys)
            if el > LIMIT_EL:
                probs.append('L%d type %s: %s.new() has %d fields = %d elements (limit %d, CE10116)' % (i + 1, name, name, len(tys), el, LIMIT_EL))
            i = j
            continue
        i += 1
    # functions: typed parameters (untyped count as 1; their type is unknown here)
    for ind, l, n in logical(src):
        if ind:
            continue
        bare = STR.sub('""', l)
        m = re.match(r'^(export\s+)?(?:method\s+)?(\w+)\s*\(([^)]*)\)\s*=>', bare)
        if not m:
            continue
        ps = [p.strip() for p in m.group(3).split(',') if p.strip()]
        tys = []
        for p in ps:
            w = re.sub(r'\s*=.*$', '', p).split()
            w = [x for x in w if x not in ('simple', 'series', 'const')]
            tys.append(w[0] if len(w) > 1 else '?')
        el = elements(tys)
        if el > LIMIT_EL:
            probs.append('L%d %s(): %d parameters = %d elements (limit %d, CE10116)' % (n, m.group(2), len(ps), el, LIMIT_EL))
    # exported functions: every argument used (CE10237)
    for i, ln in enumerate(lines):
        m = re.match(r'^export\s+(\w+)\(([^)]*)\)\s*=>(.*)$', ln)
        if not m:
            continue
        j = i + 1
        while j < len(lines) and (lines[j].startswith(' ') or not lines[j].strip()):
            j += 1
        body = STR.sub('""', m.group(3) + '\n' + '\n'.join(re.sub(r'//.*$', '', l) for l in lines[i + 1:j]))
        for p in [x.strip() for x in m.group(2).split(',') if x.strip()]:
            pn = re.sub(r'\s*=.*$', '', p).split()[-1]
            if not re.search(r'(?<![.\w])' + pn + r'\b', body):
                probs.append('L%d exported %s() never uses its argument %s (CE10237)' % (i + 1, m.group(1), pn))
    code = '\n'.join(STR.sub('""', re.sub(r'//.*$', '', l)) for l in lines)
    nplot = len(re.findall(r'(?<![.\w])(plot|plotshape|plotchar|plotarrow|plotbar|plotcandle|bgcolor|barcolor|fill|hline)\s*\(', code))
    nreq = len(re.findall(r'\brequest\.\w+\s*\(', code))
    ntab = len(re.findall(r'\btable\.new\s*\(', code))
    if nplot > 64:
        probs.append('%d plot calls (limit 64)' % nplot)
    print('%-26s %s  | plot calls %d, request calls in source %d (loops count once per symbol), table.new %d' % (
        path.split('/')[-1], 'OK' if not probs else '%d problem(s)' % len(probs), nplot, nreq, ntab))
    for p in probs:
        print('    ' + p)
    return probs


if __name__ == '__main__':
    bad = 0
    for p in sys.argv[1:]:
        bad += len(check(p))
    sys.exit(1 if bad else 0)
