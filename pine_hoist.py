"""Shrink the global scope for CE10295 "The main body of the script is too long" by moving its heaviest one-off work
into functions (function bodies don't count toward the main body; calls are not inlined):

  var array<float> CK = parseMilli(isES ? CK_ES : CK_NQ)     ->   _ld_CK() => parseMilli(isES ? CK_ES : CK_NQ)
                                                                    var array<float> CK = _ld_CK()
  if barstate.isfirst                                         ->   _first_1() =>
      <block that only pushes / sets, no := to globals>               <block>
                                                                    if barstate.isfirst
                                                                        _first_1()

Only `var` declarations (evaluated once) and `if barstate.isfirst` / `if barstate.islast` blocks are moved, and a block
is moved only when it does not reassign (:=) a global variable, which Pine forbids inside functions. Local variables
declared inside the block move with it. The wrapper function is placed right before the statement, so everything it
reads is already declared.

Usage: python3 pine_hoist.py in.pine out.pine [--min 1500]   (min = estimated IL a statement must carry to be moved)
"""
import re
import sys

sys.path.insert(0, __file__.rsplit('/', 1)[0])
from pine_size import STR, FN, analyse, il, report  # noqa: E402


def globals_assigned(block_lines):
    """Names reassigned with := in the block that are not declared inside the block."""
    local, assigned = set(), set()
    for l in block_lines:
        bare = STR.sub('""', l)
        m = re.match(r'^\s*(?:var\s+)?(?:[A-Za-z_][\w.<>]*\s+)?([A-Za-z_]\w*)\s*=(?!=)', bare)
        if m:
            local.add(m.group(1))
        m = re.match(r'^\s*\[([^\]]+)\]\s*=(?!=)', bare)
        if m:
            local |= {x.strip() for x in m.group(1).split(',')}
        m = re.match(r'^\s*for\s+([A-Za-z_]\w*)\s', bare)
        if m:
            local.add(m.group(1))
        m = re.match(r'^\s*for\s+\[?\s*([A-Za-z_]\w*)\s*(?:,\s*([A-Za-z_]\w*))?\s*\]?\s+in\b', bare)
        if m:
            local |= {x for x in m.groups() if x}
        for a in re.finditer(r'(?<![.\w])([A-Za-z_]\w*)\s*(?::=|\+=|-=|\*=|/=)', bare):
            assigned.add(a.group(1))
    return assigned - local


def hoist(src, min_il=1500, verbose=True):
    L, consts, lines = analyse(src)
    phys = src.split('\n')
    # top-level statements in the main body: (first physical line index, last physical line index, est IL)
    stmts, cur = [], None
    for k, x in enumerate(lines):
        if x['fn'] is not None:
            cur = None
            continue
        if x['ind'] == 0 and not re.match(r'^else\b', x['text']):
            cur = dict(start=x['n'] - 1, text=x['text'], toks=0, eff=0, nxt=None)
            stmts.append(cur)
        if cur is not None:
            cur['toks'] += x['toks']
            cur['eff'] += x['eff']
    # end of each statement = line before the next logical line at indent 0
    starts = sorted(x['n'] - 1 for x in lines if x['ind'] == 0)
    for s in stmts:
        nxt = [p for p in starts if p > s['start']]
        e = (nxt[0] if nxt else len(phys)) - 1
        while e > s['start'] and (not phys[e].strip() or phys[e].lstrip().startswith('//')):
            e -= 1
        s['end'] = e
    edits = []
    n_first = 0
    for s in stmts:
        cost = il(s['toks'], s['eff'])
        if cost < min_il:
            continue
        t = s['text']
        m = re.match(r'^var\s+([A-Za-z_][\w.<>]*\s+)?([A-Za-z_]\w*)\s*=\s*(.+)$', t)
        if m and s['end'] == s['start']:
            typ, name, rhs = (m.group(1) or '').strip(), m.group(2), m.group(3)
            fn = '_ld_' + name
            edits.append((s['start'], s['end'], ['%s() => %s' % (fn, rhs), 'var %s%s = %s()' % (typ + ' ' if typ else '', name, fn)], cost, name))
            continue
        if re.match(r'^if\s+barstate\.(isfirst|islast)\s*$', t) and s['end'] > s['start']:
            body = phys[s['start'] + 1:s['end'] + 1]
            if any(re.match(r'^else\b', b) for b in body):
                continue
            bad = globals_assigned(body)
            if bad:
                if verbose:
                    print('  kept L%d in main (reassigns %s)' % (s['start'] + 1, ', '.join(sorted(bad))[:80]))
                continue
            n_first += 1
            fn = '_%s_%d' % (t.split('.')[-1].strip(), n_first)
            edits.append((s['start'], s['end'], ['%s() =>' % fn] + body + [t, '    %s()' % fn], cost, fn))
    out = phys[:]
    for a, b, new, cost, name in sorted(edits, reverse=True):
        out[a:b + 1] = new
        if verbose:
            print('  moved L%-5d %-16s est IL %6.0f' % (a + 1, name, cost))
    return '\n'.join(out)


if __name__ == '__main__':
    a = [x for x in sys.argv[1:] if not x.startswith('--')]
    mi = 1500
    if '--min' in sys.argv:
        mi = int(sys.argv[sys.argv.index('--min') + 1])
        a = [x for x in a if x != str(mi)]
    out = hoist(open(a[0], encoding='utf-8').read(), mi)
    open(a[1], 'w', encoding='utf-8').write(out)
    report(a[0])
    report(a[1])
