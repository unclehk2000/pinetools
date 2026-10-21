"""Stop TradingView from embedding long constant strings at every use (the main cause of CE10117 "too many tokens").

A global string that holds a constant (`X = "..."`, `var string X = PW + "..."`, never reassigned) is folded into every
expression that uses it: a 1,000-character tooltip used in 9 places is counted 9 times. This rewrites each such string,
when it is long and used more than once, into a slot of one runtime array:

    var array<string> TXA = array.new<string>()          (added once, before the first converted string)
    txAdd(string s) =>                                    (added with it)
        TXA.push(s)
        TXA.size() - 1
    var int VZT_WGP = txAdd(PW + "...")                   (was: var string VZT_WGP = PW + "...")
    ... TXA.get(VZT_WGP) ...                              (every use)

Array elements are runtime values, so each text is embedded once. Declarations keep their place, so declaration order
and anything they refer to is unchanged.

A string also used where Pine needs a const (input titles / tooltips / options / groups, indicator(), function
parameter defaults) keeps its const for those uses; its other uses read a slot added right after it:
    VZT_LV = "..."                                        (unchanged, still used by the inputs)
    var int VZT_LV_tx = txAdd(VZT_LV)                     (added)

Usage: python3 pine_tips.py in.pine out.pine [--min-save 300] [--dry]
"""
import re
import sys

sys.path.insert(0, __file__.rsplit('/', 1)[0])
from pine_size import STR, FN, logical, string_consts, report  # noqa: E402

CONST_CALL = re.compile(r'\b(input(?:\.\w+)?|indicator|strategy|library)\s*\(')
DECL = re.compile(r'^(?:var\s+)?(?:const\s+)?(?:string\s+)?([A-Za-z_]\w*)\s*=(?!=)')


def code_spans(line):
    """(code, comment) of a physical line; strings kept in code."""
    q = None
    for k, c in enumerate(line):
        if q:
            if c == q and line[k - 1] != '\\':
                q = None
        elif c in '"\'':
            q = c
        elif line.startswith('//', k):
            return line[:k], line[k:]
    return line, ''


def const_ranges(lines):
    """For each physical line, the character ranges that sit inside input()/indicator() calls or a function header."""
    ranges = [[] for _ in lines]
    depth_carry = 0          # an input( ... ) call still open from an earlier line
    for i, raw in enumerate(lines):
        code, _ = code_spans(raw)
        bare = STR.sub(lambda m: '"' + ' ' * (len(m.group(0)) - 2) + '"', code)
        if depth_carry:
            d, k = depth_carry, 0
            while k < len(bare) and d:
                d += {'(': 1, ')': -1}.get(bare[k], 0)
                k += 1
            ranges[i].append((0, k))
            depth_carry = d
        for m in CONST_CALL.finditer(bare):
            k, d = m.end(), 1
            while k < len(bare) and d:
                d += {'(': 1, ')': -1}.get(bare[k], 0)
                k += 1
            ranges[i].append((m.start(), k))
            if d:
                depth_carry = d
        if not raw.startswith(' ') and FN.match(bare):
            ranges[i].append((0, bare.index('=>')))
    return ranges


def convert(src, min_save=300, verbose=True):
    L = logical(src)
    consts = string_consts(L)
    lines = src.split('\n')
    cr = const_ranges(lines)
    # count uses per name: in const positions, and elsewhere; uses inside another constant's declaration don't count
    decl_lines = set()
    for i, raw in enumerate(lines):
        m = DECL.match(raw)
        if m and m.group(1) in consts:
            decl_lines.add(i)
            j = i
            while j + 1 < len(lines) and lines[j + 1].startswith(' ') and (len(lines[j + 1]) - len(lines[j + 1].lstrip(' '))) % 4:
                j += 1
                decl_lines.add(j)
    use_c = {k: 0 for k in consts}
    use_r = {k: 0 for k in consts}
    name_re = re.compile(r'(?<![.\w])(' + '|'.join(map(re.escape, sorted(consts, key=len, reverse=True))) + r')\b(?!\s*(?:\(|:=|=[^=>]))') if consts else None
    for i, raw in enumerate(lines):
        if i in decl_lines or not name_re:
            continue
        code, _ = code_spans(raw)
        bare = STR.sub(lambda m: '"' + ' ' * (len(m.group(0)) - 2) + '"', code)
        for m in name_re.finditer(bare):
            inside = any(a <= m.start() < b for a, b in cr[i])
            (use_c if inside else use_r)[m.group(1)] += 1
    pick, split = [], []
    for k, n in consts.items():
        if use_c[k] == 0 and use_r[k] >= 2 and n * (use_r[k] - 1) - 25 * use_r[k] >= min_save:
            pick.append(k)
        elif use_c[k] > 0 and use_r[k] >= 2 and n * (use_r[k] - 1) - 25 * use_r[k] >= min_save:
            split.append(k)
    if verbose:
        print('array slots for %d strings: %s' % (len(pick), ', '.join('%s(%dBx%d)' % (k, consts[k], use_r[k]) for k in sorted(pick, key=lambda k: -consts[k] * use_r[k]))))
        if split:
            print('  kept const for inputs, slot for the other uses: ' + ', '.join('%s(%dBx%d+%d)' % (k, consts[k], use_r[k], use_c[k]) for k in split))
    if not pick and not split:
        return src
    target = {k: k for k in pick}
    target.update({k: k + '_tx' for k in split})
    use_re = re.compile(r'(?<![.\w])(' + '|'.join(map(re.escape, sorted(target, key=len, reverse=True))) + r')\b(?!\s*(?:\(|:=|=[^=>]))')
    out = []
    first = None
    i = 0
    while i < len(lines):
        raw = lines[i]
        m = DECL.match(raw)
        if m and m.group(1) in target and i in decl_lines:
            name = m.group(1)
            j = i
            while j + 1 < len(lines) and lines[j + 1].startswith(' ') and (len(lines[j + 1]) - len(lines[j + 1].lstrip(' '))) % 4:
                j += 1
            block = lines[i:j + 1]
            if first is None:
                first = len(out)
            if name in pick:
                rhs = re.sub(r'^(?:var\s+)?(?:const\s+)?(?:string\s+)?' + re.escape(name) + r'\s*=\s*', '', block[0])
                block = ['var int %s = txAdd(%s' % (name, rewrite(rhs, use_re, target, []))] + [rewrite(b, use_re, target, []) for b in block[1:]]
                block[-1] += ')'
                out.extend(block)
            else:
                out.extend(block)
                out.append('var int %s_tx = txAdd(%s)' % (name, name))
            i = j + 1
            continue
        out.append(rewrite(raw, use_re, target, cr[i]) if i not in decl_lines else rewrite(raw, use_re, target, cr[i], decl=True))
        i += 1
    helper = ['// long texts live in one runtime array, so each is embedded once (Pine folds a constant string into every use)',
              'var array<string> TXA = array.new<string>()',
              'txAdd(string s) =>',
              '    TXA.push(s)',
              '    TXA.size() - 1']
    out[first:first] = helper
    return '\n'.join(out)


def rewrite(raw, use_re, target, ranges, decl=False):
    """Replace uses outside strings, comments and const positions with TXA.get(slot)."""
    code, comment = code_spans(raw)
    res, last = [], 0
    for m in STR.finditer(code):
        res.append(('c', last, code[last:m.start()]))
        res.append(('s', m.start(), m.group(0)))
        last = m.end()
    res.append(('c', last, code[last:]))
    out = []
    for kind, off, seg in res:
        if kind == 's':
            out.append(seg)
            continue

        def rep(mm):
            pos = off + mm.start()
            if any(a <= pos < b for a, b in ranges):
                return mm.group(0)
            if decl and mm.group(1) == raw.lstrip().split('=')[0].split()[-1]:
                return mm.group(0)
            return 'TXA.get(%s)' % target[mm.group(1)]
        out.append(use_re.sub(rep, seg))
    return ''.join(out) + comment


if __name__ == '__main__':
    a = [x for x in sys.argv[1:] if not x.startswith('--')]
    ms = 300
    if '--min-save' in sys.argv:
        ms = int(sys.argv[sys.argv.index('--min-save') + 1])
        a = [x for x in a if x != str(ms)]
    src = open(a[0], encoding='utf-8').read()
    out = convert(src, ms)
    if '--dry' not in sys.argv:
        open(a[1], 'w', encoding='utf-8').write(out)
        report(a[0])
        report(a[1])
