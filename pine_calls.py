"""Call statistics: number of calls and arguments to user functions and to built-ins (table.cell, label.new, ...).
Usage: python3 pine_calls.py a.pine b.pine ..."""
import re, sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pine_size import logical, STR


def calls(path):
    L = logical(open(path, encoding='utf-8').read())
    user = set()
    for ind, l, *_ in L:
        m = re.match(r'^([A-Za-z_]\w*)\s*\(([^)]*)\)\s*=>', STR.sub('""', l)) if ind == 0 else None
        if m:
            user.add(m.group(1))
    st = dict(ucalls=0, uargs=0, bcalls=0, bargs=0)
    for ind, l, *_ in L:
        s = STR.sub('""', l)
        for m in re.finditer(r'([A-Za-z_][\w.]*)\s*\(', s):
            name = m.group(1)
            if re.match(r'^[A-Za-z_]\w*\s*\([^)]*\)\s*=>', s[m.start():]) and ind == 0 and m.start() == 0:
                continue
            i, d, n = m.end(), 1, 0
            empty = True
            while i < len(s) and d:
                c = s[i]
                if c in '([':
                    d += 1
                elif c in ')]':
                    d -= 1
                elif c == ',' and d == 1:
                    n += 1
                if d and not c.isspace():
                    empty = False
                i += 1
            args = 0 if empty else n + 1
            k = 'u' if name in user else 'b'
            st[k + 'calls'] += 1
            st[k + 'args'] += args
    return st


for p in sys.argv[1:]:
    s = calls(p)
    print('%-22s user calls %5d args %6d | built-in calls %5d args %6d' % (p.split('/')[-1], s['ucalls'], s['uargs'], s['bcalls'], s['bargs']))
