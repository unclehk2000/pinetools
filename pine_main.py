"""The global scope's biggest top-level statements (with their indented blocks), by estimated IL, to pick what to
move into functions when TradingView says "The main body of the script is too long" (CE10295).
Usage: python3 pine_main.py file.pine [N]"""
import re, sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pine_size import analyse, il

src = open(sys.argv[1], encoding='utf-8').read()
N = int(sys.argv[2]) if len(sys.argv) > 2 else 25
L, consts, lines = analyse(src)
stmts, cur = [], None
for x in lines:
    if x['fn'] is not None:
        cur = None
        continue
    if x['ind'] == 0 and not re.match(r'^else\b', x['text']):
        cur = dict(n=x['n'], text=x['text'][:70], toks=0, eff=0, nlines=0)
        stmts.append(cur)
    if cur is not None:
        cur['toks'] += x['toks']
        cur['eff'] += x['eff']
        cur['nlines'] += 1
tot = sum(il(s['toks'], s['eff']) for s in stmts)
print('main body est IL %.0f in %d top-level statements' % (tot, len(stmts)))
for s in sorted(stmts, key=lambda s: -il(s['toks'], s['eff']))[:N]:
    print('  L%-5d %6.0f  (%3d lines, code %5d, str %5d)  %s' % (s['n'], il(s['toks'], s['eff']), s['nlines'], s['toks'], s['eff'], s['text']))
# runs of consecutive small statements (input blocks, var declarations)
