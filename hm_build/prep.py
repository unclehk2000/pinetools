"""Prepare the four calendar modules for pine2lib (5 Nov 2026).

Each standalone module places its own cards with a corner rule (cornerOf: a card set to a corner another card already
uses moves to the first free one), and its position settings are named crdPosI, ckPosI, ... Hueco Mundo places every
card itself with the same rule across all four modules, so the modules' own rule is taken out and the position settings
get their plain names back (crdPosI -> crdPos), which is what the specs and make_hm.py expect.

  python3 prep.py modules_dir prepared_dir        (make_hm.py runs this itself before building)
"""
import os, re, sys

MODULES = ('Gran_Rey_Cero', 'Vizard', 'Desgarron', 'Hollow')

def prepare_text(t):
    s = t.split('\n')
    o, i = [], 0
    while i < len(s):
        l = s[i]
        if l.startswith('// ── card corners'):                   # the rule's comment block
            while i < len(s) and s[i].startswith('//'):
                i += 1
            continue
        if l.startswith('cornerOf('):                            # the function and its body
            i += 1
            while i < len(s) and s[i].startswith(' '):
                i += 1
            continue
        if re.match(r'^var array<string> cUsed[PI] = ', l) or re.match(r'^var string \w+Pos = cornerOf\(', l):
            i += 1
            continue
        m = re.match(r'^(\w+Pos)I(\s*)= input\.', l)             # crdPosI = input.string(...) -> crdPos  = input.string(...)
        if m:
            l = m.group(1) + m.group(2) + ' = input.' + l[m.end():]
            l = re.sub(r'^(\w+Pos)(\s*) =  ', r'\1\2 = ', l)
        o.append(l)
        i += 1
    out = '\n'.join(o)
    assert 'cornerOf' not in out and not re.search(r'\w+PosI\b', out), 'corner rule not fully removed'
    return out

def prepare(src_dir, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    for n in MODULES:
        p = os.path.join(src_dir, n + '.pine')
        t = open(p, encoding='utf-8').read()
        open(os.path.join(out_dir, n + '.pine'), 'w', encoding='utf-8').write(prepare_text(t))
    return out_dir

if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    print(prepare(sys.argv[1], sys.argv[2]))
