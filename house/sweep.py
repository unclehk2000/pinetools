#!/usr/bin/env python3
"""5S Sort: remove declarations that are never used (the statement and its indented body or continuation lines).

  python3 sweep.py file.pine NAME [NAME ...]     remove these top-level declarations
  python3 sweep.py --audit file.pine            remove every setting, global and function audit.py reports as unused

Only top-level declarations (column 0) are touched. Run audit.py again afterwards (a removal can leave something else
unused), then the parse, size and limit checks.
"""
import os, re, sys

def remove(lines, name):
    pat = re.compile(r'^(?:var\s+|varip\s+|const\s+)?(?:(?:array|matrix|map)<[^>]+>\s+|color\s+|string\s+|int\s+|float\s+|bool\s+|line\s+|label\s+|box\s+|table\s+)?'
                     + re.escape(name) + r'\s*(=|\()')
    hits = [i for i, l in enumerate(lines) if pat.match(l)]
    if len(hits) != 1:
        raise SystemExit('%s: %d top-level declarations found, expected 1' % (name, len(hits)))
    i = j = hits[0]
    j += 1
    while j < len(lines) and lines[j].startswith((' ', '\t')):      # a function body or a wrapped statement
        j += 1
    return lines[:i] + lines[j:], j - i

def main():
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    if a[0] == '--audit':
        path = a[1]
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import audit
        r = audit.audit(path)
        names = r['unused_inputs'] + r['unused_globals'] + r['unused_fns']
    else:
        path, names = a[0], a[1:]
    lines = open(path, encoding='utf-8').read().split('\n')
    for n in names:
        lines, k = remove(lines, n)
        print('%s: removed %s (%d line%s)' % (os.path.basename(path), n, k, '' if k == 1 else 's'))
    open(path, 'w', encoding='utf-8').write('\n'.join(lines))
    if not names:
        print(os.path.basename(path) + ': nothing unused')

if __name__ == '__main__':
    main()
