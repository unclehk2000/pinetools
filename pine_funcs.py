"""Per-function size and call counts for a Pine v6 script: body tokens, string chars, whether it keeps state
(var / history [n] / ta.* / request), and how many places call it. Usage: python3 pine_funcs.py file.pine [N]"""
import re, sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pine_size import logical, STR, TOK


def functions(path):
    L = logical(open(path, encoding='utf-8').read())
    fns, cur = {}, None
    rest = []
    for ind, l, *_ in L:
        bare = STR.sub('""', l)
        m = re.match(r'^(?:export\s+)?(?:method\s+)?([A-Za-z_]\w*)\s*\(([^)]*)\)\s*=>(.*)$', bare) if ind == 0 else None
        if m:
            cur = m.group(1)
            fns[cur] = dict(params=len([p for p in m.group(2).split(',') if p.strip()]), lines=[l], toks=0, strs=0, state=False)
        elif ind == 0:
            cur = None
        if cur:
            if not m:
                fns[cur]['lines'].append(l)
        else:
            rest.append(l)
    allcode = [STR.sub('""', l) for _, l, *_r in L]
    for n, f in fns.items():
        body = '\n'.join(f['lines'])
        bb = STR.sub('""', body)
        f['toks'] = len(TOK.findall(bb))
        f['strs'] = sum(len(s) - 2 for s in STR.findall(body))
        f['state'] = bool(re.search(r'\bvar\b|\bvarip\b|\w\s*\[\s*\d+\s*\]|\)\s*\[\s*\d+\s*\]|\bta\.|request\.', bb.split('=>', 1)[1]))
        f['calls'] = sum(len(re.findall(r'\b' + re.escape(n) + r'\s*\(', c)) for c in allcode) - 1
    return fns


if __name__ == '__main__':
    fns = functions(sys.argv[1])
    top = int(sys.argv[2]) if len(sys.argv) > 2 else 25
    tot = sum(f['toks'] for f in fns.values())
    print('%d functions, %d body tokens' % (len(fns), tot))
    print('stateful functions called from more than one place:')
    for n, f in sorted(fns.items(), key=lambda x: -x[1]['toks'] * max(x[1]['calls'], 1)):
        if f['state'] and f['calls'] > 1:
            print('   %-14s toks %5d  strs %5d  calls %3d  params %d' % (n, f['toks'], f['strs'], f['calls'], f['params']))
    print('largest functions:')
    for n, f in sorted(fns.items(), key=lambda x: -x[1]['toks'])[:top]:
        print('   %-14s toks %5d  strs %5d  calls %3d  params %d %s' % (n, f['toks'], f['strs'], f['calls'], f['params'], 'STATE' if f['state'] else ''))
