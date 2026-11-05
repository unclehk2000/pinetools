"""Add the house text-colour setting to the View group (as Mangekyō v3.1) where a script's text follows the chart theme.
Text colour: Auto (theme) | Custom, with a card colour, and a chart colour where the script draws theme-following text on
the chart. Custom replaces the automatic white / black. Run once; it refuses a script that already has txtM.

  TXT_SRC=folder/with/the/scripts python3 txt.py [Name ...]     (no names = every script in CFG)

CFG is the set it was run on, 5 Nov 2026: the View group's variable, the card palette names (with the transparency each
takes on the custom colour), and the theme-following chart text, per script. Add a script by adding its row."""
import re, sys, os

SRC = os.path.join(os.environ.get('TXT_SRC', os.getcwd()), '')
# card: palette lines (name -> transparency on the custom colour); chart: theme-following chart text (name -> line regex)
CFG = {
    'Desgarron':      dict(view='grpW', module=True,  card={'cTx': 0, 'cSub': 25, 'cMu': 50}),
    'Hollow':         dict(view='grpW', module=True,  card={'cTx': 0, 'cSub': 25, 'cMu': 50}),
    'Vizard':         dict(view='grpW', module=True,  card={'cTx': 0, 'cSub': 25, 'cMu': 50}),
    'Gran_Rey_Cero':  dict(view='grpW', module=True,  card={'cTx': 0, 'cSub': 25, 'cMu': 50}, chart=['fgP']),
    'Genjutsu_Kai':   dict(view='gV',   module=False, card={'cTx': 0, 'cSub': 25, 'cMu': 50}),
    'Kyoka_Suigetsu': dict(view='gV',   module=False, card={'cTx': 0, 'cSub': 25, 'cMu': 50}, chart_fg=True),
    'Sharingan':      dict(view='gV',   module=False, card={'cTx': 0, 'cSub': 25, 'cMu': 50}),
    'Senbonzakura':   dict(view='grpG', module=False, card={'cTx': 0, 'cSub': 25, 'cMu': 50}),
    'Hado_99':        dict(view='g_V',  module=False, card={'cTxt': 0, 'cSub': 25}, chart=['fgAuto']),
    'Hogyoku':        dict(view='gV',   module=False, card={'cTxt': 0, 'cSub': 25}, chart=['fgAuto']),
    'Rinnegan':       dict(view='gV',   module=False, card={'cTxt': 0, 'cSub': 25}),
    'Ryujin_Jakka':   dict(view='gV',   module=False, card={'cTxt': 0, 'cSub': 25}),
    'Sakanade':       dict(view='gV',   module=False, card={'cTxt': 0, 'cSub': 25}),
    'Shinso':         dict(view='gV',   module=False, card={'cTxt': 0, 'cSub': 25}),
    'Suzumebachi':    dict(view='gV',   module=False, card={'cTxt': 0, 'cSub': 25}),
}

def run(name, c):
    p = SRC + name + '.pine'
    L = open(p, encoding='utf-8').read().split('\n')
    if any(l.startswith('txtM') for l in L):
        return name + ': already has txtM'
    chart = bool(c.get('chart') or c.get('chart_fg'))
    # 1) inputs at the end of the View group
    gpat = re.compile(r'^\w+\s*=\s*input\.\w+\(.*group\s*=\s*' + re.escape(c['view']) + r'\b')
    last = max(i for i, l in enumerate(L) if gpat.match(l))
    act = '' if c['module'] else ', active = txtM == "Custom"'
    tip = ('Auto: white text on a dark background, black on a light one. Custom: your own colour' + ('s' if chart else '') +
           ', for backgrounds where the automatic choice clashes' + (': chart = the labels that follow the chart background, card = the card text.' if chart else ' (the card text).'))
    ins = ['txtM   = input.string("Auto (theme)", "Text colour", options = ["Auto (theme)", "Custom"], group = %s, inline = "tx", tooltip = "%s", display = display.none)' % (c['view'], tip)]
    if chart:
        ins.append('txtCh  = input.color(#131722, "chart", group = %s, inline = "tx"%s, display = display.none)' % (c['view'], act))
    ins.append('txtCd  = input.color(#131722, "card", group = %s, inline = "tx"%s, display = display.none)' % (c['view'], act))
    L[last + 1:last + 1] = ins
    # 2) card palette
    first = None
    for nm, tr in c['card'].items():
        pat = re.compile(r'^((?:color\s+)?' + nm + r'\s*=\s*)(.+)$')
        hits = [i for i, l in enumerate(L) if pat.match(l)]
        assert len(hits) == 1, (name, nm, hits)
        i = hits[0]
        m = pat.match(L[i])
        val = 'txtCd' if tr == 0 else 'color.new(txtCd, %d)' % tr
        L[i] = m.group(1) + 'txC ? ' + val + ' : ' + m.group(2)
        first = i if first is None else min(first, i)
    L[first:first] = ['bool txC = txtM == "Custom"                          // View → Text colour: Custom replaces the automatic white / black'] + \
                     (['color cChT = txC ? txtCh : chart.fg_color            // chart text that follows the chart theme'] if c.get('chart_fg') else [])
    # 3) chart text
    for nm in c.get('chart', []):
        pat = re.compile(r'^((?:color\s+)?' + nm + r'\s*=\s*)(.+)$')
        hits = [i for i, l in enumerate(L) if pat.match(l)]
        assert len(hits) == 1, (name, nm, hits)
        m = pat.match(L[hits[0]])
        L[hits[0]] = m.group(1) + 'txC ? txtCh : ' + m.group(2)
    s = '\n'.join(L)
    if c.get('chart_fg'):
        # every other chart.fg_color use reads cChT (the cChT line itself keeps chart.fg_color)
        keep = 'color cChT = txC ? txtCh : chart.fg_color'
        n = s.count('chart.fg_color') - 1
        s = s.replace(keep, '\0KEEP\0').replace('chart.fg_color', 'cChT').replace('\0KEEP\0', keep)
        print(name, 'chart.fg_color uses', n)
    open(p, 'w', encoding='utf-8').write(s)
    return name + ': ok'

if __name__ == '__main__':
    for n in (sys.argv[1:] or CFG):
        print(run(n, CFG[n]))
