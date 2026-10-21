import sys
from pynescript.ast import parse
src = open(sys.argv[1]).read()
try:
    tree = parse(src)
    print('PARSE OK', len(src.splitlines()), 'lines')
except Exception as e:
    print('PARSE ERROR:', type(e).__name__, str(e)[:2000])
