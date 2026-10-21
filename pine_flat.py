"""Flatten a script and the libraries it imports into one script, for a type check before the libraries are published.

TradingView's checker (translate_light) can't resolve `import User/Lib/1 as x` until Lib is published. This writes a
copy where each imported library is pasted in, with its top-level names prefixed by the alias (`des.step1` becomes
`des_step1`), so the importing script and every library are type-checked together. The result is only for checking:
it is far over the size limits and is never published.

Usage: python3 pine_flat.py script.pine out.pine --lib HM_Desgarron=/path/HM_Desgarron.pine [--lib ...]
"""
import re
import sys

TOKEN = re.compile(r'"(?:[^"\\\n]|\\.)*"|\'(?:[^\'\\\n]|\\.)*\'|//.*|[A-Za-z_]\w*|.', re.S)


def top_names(lines):
    names = set()
    for l in lines:
        if not l or l[0] in ' \t/':
            continue
        m = re.match(r'^(?:export\s+)?(?:const\s+)?(?:type\s+)([A-Za-z_]\w*)', l)
        if m:
            names.add(m.group(1))
            continue
        m = re.match(r'^(?:export\s+)?(?:method\s+)?([A-Za-z_]\w*)\s*\([^)]*\)\s*=>', l)
        if m:
            names.add(m.group(1))
            continue
        m = re.match(r'^(?:export\s+)?(?:const\s+)?(?:var\s+)?(?:[A-Za-z_][\w.<>]*\s+)?([A-Za-z_]\w*)\s*=(?!=)', l)
        if m:
            names.add(m.group(1))
    return names


def rename(line, mapping, in_type=False):
    out, prev = [], ''
    toks = TOKEN.findall(line)
    field_at = -1
    if in_type:
        # a field line is `<type> <name> [= default]`: the field name is the last identifier before `=` (or the end)
        code = [i for i, t in enumerate(toks) if t.strip() and not t.startswith('//')]
        eq = next((i for i in code if toks[i] == '='), None)
        idents = [i for i in code if (eq is None or i < eq) and re.fullmatch(r'[A-Za-z_]\w*', toks[i])]
        field_at = idents[-1] if idents else -1
    for k, t in enumerate(toks):
        if t[0] in '"\'' or t.startswith('//'):
            out.append(t)
            continue
        if re.fullmatch(r'[A-Za-z_]\w*', t):
            if t in mapping and prev != '.' and k != field_at:
                t = mapping[t]
        if t.strip():
            prev = t
        out.append(t)
    return ''.join(out)


def flatten(main_src, libs):
    lines = main_src.split('\n')
    imports = {}
    keep = []
    for l in lines:
        m = re.match(r'^import\s+\w+/(\w+)/\d+\s+as\s+(\w+)', l)
        if m:
            imports[m.group(2)] = m.group(1)
            continue
        keep.append(l)
    pasted = []
    for alias, lib in imports.items():
        src = open(libs[lib], encoding='utf-8').read().split('\n')
        body = [l for l in src if not l.startswith('//@version') and not l.startswith('library(')
                and not l.startswith('plot(na, "Hueco Mundo module"')]
        names = top_names(body)
        mapping = {n: alias + '_' + n for n in names}
        in_type = False
        pasted.append('// ════ library %s (as %s), flattened for checking' % (lib, alias))
        for l in body:
            if re.match(r'^(?:export\s+)?type\s', l):
                in_type = True
            elif l and l[0] not in ' \t':
                in_type = False
            l = re.sub(r'^export\s+', '', l)
            pasted.append(rename(l, mapping, in_type and l.startswith(' ')))
    # the importing script: alias.name -> alias_name
    out = []
    ins = False
    for l in keep:
        for alias in imports:
            l = re.sub(r'(?<![\w.])' + alias + r'\.([A-Za-z_]\w*)', alias + r'_\1', l)
        out.append(l)
        if not ins and re.match(r'^(indicator|strategy)\(', l):
            out += pasted
            ins = True
    return '\n'.join(out)


if __name__ == '__main__':
    a = sys.argv[1:]
    libs = {}
    while '--lib' in a:
        i = a.index('--lib')
        k, v = a[i + 1].split('=', 1)
        libs[k] = v
        del a[i:i + 2]
    open(a[1], 'w', encoding='utf-8').write(flatten(open(a[0], encoding='utf-8').read(), libs))
    print('written', a[1])
