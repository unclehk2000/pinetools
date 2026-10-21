"""Build Hueco Mundo: the four calendar libraries (via pine2lib.py) and the indicator that imports them.
python3 make_hm.py"""
import json, re, subprocess, sys
import os
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.environ.get('HM_SRC', os.path.join(HERE, 'src'))        # folder with Desgarron.pine, Gran_Rey_Cero.pine, Vizard.pine, Hollow.pine
OUTDIR = os.environ.get('HM_OUT', HERE)                          # where the libraries and Hueco_Mundo.pine are written
exec(open(os.path.join(HERE, 'pine2lib.py')).read().split("if __name__ == '__main__':")[0])

USER = 'Unclehk2000'
MODS = [  # key, alias, library, name, spec, pane map, findings-position input, colour of the module switch tooltip
    dict(k='D', a='des', lib='HM_Desgarron', name='Desgarrón', what='NFP day (Model 6)', spec='spec_desgarron.json',
         pane={'Clock + findings': 'Clock + Grimmjow', 'Event clock': 'Event clock', 'Findings': 'Grimmjow', 'Cards only': 'Cards only'},
         fpos='hyPos', plots=dict(T='p1', TC='pc1', E='p2', EC='pc2', H='p3'), bgs=[('bg0', 'NFP release window')]),
    dict(k='G', a='grc', lib='HM_GranRey', name='Gran Rey Cero', what='CPI day and the day after (Models 7–8)', spec='spec_granrey.json',
         pane={'Clock + findings': 'Event clock', 'Event clock': 'Event clock', 'Findings': 'Cards only', 'Cards only': 'Cards only'},
         fpos=None, plots=dict(T='p1', TC='pc1', E='p2', EC='pc2', H='p3'), bgs=[('bg0', '08:30–09:00 window')]),
    dict(k='V', a='viz', lib='HM_Vizard', name='Vizard', what='FOMC day and day 1 (Models 9–10)', spec='spec_vizard.json',
         pane={'Clock + findings': 'Clock + Fed map', 'Event clock': 'Event clock', 'Findings': 'Fed map', 'Cards only': 'Cards only'},
         fpos='mapPos', plots=dict(T='p2', TC='pc2', E='p3', EC='pc3', H='p4'),
         bgs=[('bg0', 'statement and press conference'), ('bg1', 'NY AM, FOMC day')]),
    dict(k='H', a='hol', lib='HM_Hollow', name='Hollow', what='NFP week and the day after FOMC (Models 11–12)', spec='spec_hollow.json',
         pane={'Clock + findings': 'Clock + Shirosaki', 'Event clock': 'Event clock', 'Findings': 'Shirosaki', 'Cards only': 'Cards only'},
         fpos='shPos', plots=dict(T='p2', TC='pc2', E='p3', EC='pc3', H='p4'), extra={'skipNfpMark': 'onD and markEv'},
         bgs=[('bg0', 'settlement window 16:15–17:00'), ('bg1', 'NY AM, the day after FOMC')]),
]
SHARED = ['clkMet', 'themeI', 'layI', 'crdSzI', 'anchorI', 'markEv', 'markD', 'kBands', 'kRef', 'kPast', 'showEv', 'crdPos', 'talN',
          'showCk', 'ckOn', 'ckPos', 'dxySym', 'vixSym', 'ylSym', 'showSg', 'sgOn', 'sgPos', 'fdRoot']
DEFAULT_OVERRIDE = {('G', 'winDays'): '"CPI days and the day after"', ('G', 'txOth'): '""'}
POS8 = '["Top left", "Top center", "Top right", "Middle left", "Middle right", "Bottom left", "Bottom center", "Bottom right"]'

libs = {}
for m in MODS:
    spec = json.load(open(os.path.join(HERE, m['spec'])))
    L = Lib(spec)
    L.build()
    open(_out(spec['out']), 'w', encoding='utf-8').write(L.text())
    libs[m['k']] = L
    r = subprocess.run(['python3', os.path.join(HERE, 'checklib.py'), os.path.join(HERE, m['spec'])], capture_output=True, text=True)
    print(r.stdout.strip().split('\n')[-1])


def module_inputs(m, L):
    """the module's own inputs, renamed and regrouped under the module's name"""
    out, names = [], {}
    pfx = m['k'].lower() + '_'
    for n, (ty, dflt, st) in L.inputs.items():
        if st is None or n in SHARED or n == 'paneI' or n == m['fpos']:
            continue
        raw = '\n'.join(st)
        raw = re.sub(r'^\s*' + re.escape(n) + r'\s*=', pfx + n + ' =', raw, count=1)

        def grp(mm):
            g = mm.group(1)
            title = json.loads(L.consts[g][1][0].split('=', 1)[1].strip()) if g in L.consts else g.strip('"')
            title = re.sub(r'\s*\((indicator pane|price chart)[^)]*\)', '', title)
            return 'group = "%s · %s"' % (m['name'], title)
        raw = re.sub(r'group\s*=\s*(\w+|"[^"]*")', grp, raw)
        raw = re.sub(r'inline\s*=\s*"([^"]*)"', lambda mm: 'inline = "%s%s"' % (pfx, mm.group(1)), raw)
        if (m['k'], n) in DEFAULT_OVERRIDE:
            raw = re.sub(r'(input\.\w+\()([^,]+)', lambda mm: mm.group(1) + DEFAULT_OVERRIDE[(m['k'], n)], raw, count=1)
        out.append(raw)
        names[n] = pfx + n
    return out, names


def cfg_new(m, L, names):
    args = []
    for n in L.inputs:
        if n in ('on', '__ON__'):
            continue
        if n == 'paneI':
            v = 'paneI == "Clock + findings" ? "%s" : paneI == "Findings" ? "%s" : paneI == "Event clock" ? "Event clock" : "Cards only"' % (
                m['pane']['Clock + findings'], m['pane']['Findings'])
        elif n == m['fpos']:
            v = 'fdgPos'
        elif n in m.get('extra', {}):
            v = m['extra'][n]
        elif n in SHARED:
            v = n
        else:
            v = names[n]
        args.append('%s = %s' % (n, v))
    return 'var %s.Cfg c%s = %s.Cfg.new(%s)' % (m['a'], m['k'], m['a'], ', '.join(args))


FEED_SRC = {'dxL_1': 'dxL[1]'}


def sp(k, n):
    """the megazord's path to a module's state field (State is held in parts: sD.s2.KP)"""
    return 's%s.%s' % (k, libs[k].spath.get(n, n))


def call_args(L, fn, k):
    """the arguments an exported function takes after unused ones were dropped (CE10237)"""
    return ', '.join({'hmS': 's', 'hmC': 'c', 'hmF': 'f'}[a] + k for a in L.export_args[fn])
out = []
w = out.append
w('//@version=6')
w('// This Source Code Form is subject to the terms of the Mozilla Public License 2.0 at https://mozilla.org/MPL/2.0/')
w('// © ' + USER)
w('//')
w('// Hueco Mundo (虚圏 · the world of Hollows): the economic-calendar models in one indicator.')
w('// Each model is its own library, imported below, the way NWOG / NDOG imports OpenGaps:')
w('//   Desgarrón: NFP day (Model 6) · Gran Rey Cero: CPI day and the day after (7–8) · Vizard: FOMC day and day 1 (9–10)')
w('//   · Hollow: NFP week and the day after FOMC (11–12).')
w('// Each module draws its structure on its own days. The cards and the indicator pane follow one module at a time: the one')
w('// whose day is today or comes next (TradingView keeps one table per corner), or the one you pin in View.')
w('// The chart data each module needs is requested here once and handed to every module.')
w('// Publish the four libraries first (private is fine), then this script. After a library update, raise its version below.')
w('// Concepts: ICT (Michael J. Huddleston). Written from scratch.')
w('')
w('indicator("Hueco Mundo", "Hueco Mundo", overlay = false, max_boxes_count = 500, max_lines_count = 500, max_labels_count = 500, max_polylines_count = 100)')
w('')
for m in MODS:
    w('import %s/%s/1 as %s' % (USER, m['lib'], m['a']))
w('')
w('TZ = "America/New_York"')
w('')
w('// ═══════════════════════════════════════════════════════════════ Inputs')
w('grpW = "View"')
w('paneI   = input.string("Clock + findings", "Pane", options = ["Clock + findings", "Event clock", "Findings", "Cards only"], group = grpW, tooltip = "What the indicator pane shows for the module the cards follow. Event clock: today\'s running range (or net move) against that module\'s days at the same time of day. Findings: its findings table (Desgarrón\'s Grimmjow, Vizard\'s Fed map, Hollow\'s Shirosaki; Gran Rey Cero has none). Cards only: an empty pane.", display = display.none)')
w('followI = input.string("Next event", "Cards follow", options = ["Next event", "Desgarrón", "Gran Rey Cero", "Vizard", "Hollow"], group = grpW, tooltip = "Next event: the module whose day is today, or else comes next (on a tie: Desgarrón, Gran Rey Cero, Vizard, then Hollow). Or pin one module\'s cards and pane.", display = display.none)')
w('clkMet  = input.string("Range", "Clock measure", options = ["Range", "Net move"], group = grpW, tooltip = "Range: the day\'s high − low so far. Net move: price − the 18:00 open. Both in points, against the same measure on the module\'s days at this time.", display = display.none)')
w('themeI  = input.string("Auto", "Theme", options = ["Auto", "Dark", "Light"], group = grpW, tooltip = "Auto follows the chart background.", display = display.none)')
w('layI    = input.string("Desktop", "Layout", options = ["Desktop", "Mobile"], group = grpW, tooltip = "Desktop: every row. Mobile: narrow cards for a phone screen; the full wording stays in the tooltips.", display = display.none)')
w('crdSzI  = input.string("Small", "Card text", options = ["Tiny", "Small", "Normal"], group = grpW, display = display.none)')
w('')
w('grpO = "Modules"')
for m in MODS:
    w('on%s = input.bool(true, "%s", group = grpO, tooltip = "%s. Off: none of its structure, cards or pane, and it stops running.", display = display.none)' % (m['k'], m['name'], m['what']))
w('')
w('grpE = "Event day"')
w('anchorI  = input.string("Trading day (18:00)", "Day", options = ["Trading day (18:00)", "NY midnight", "RTH (09:30–16:14)"], group = grpE, tooltip = "Which day counts as the event day for the tallies and Gran Rey Cero\'s candles.\\nTrading day: the CME day, 18:00 to 17:00 ET, as the futures settle.\\nNY midnight: 00:00 to 17:00 ET.\\nRTH: 09:30 to 16:14 ET.", display = display.none)')
w('markEv   = input.bool(true, "Mark releases", group = grpE, inline = "g3", display = display.none)')
w('markD    = input.int(90, "and model structure for the last (days)", minval = 5, maxval = 400, group = grpE, inline = "g3", display = display.none)')
w('')
w('grpR = "Cards"')
w('showEv  = input.bool(true, "Event tally", group = grpR, inline = "r1", display = display.none)')
w('crdPos  = input.string("Top right", "", options = %s, group = grpR, inline = "r1", display = display.none)' % POS8)
w('talN    = input.int(12, "last", minval = 3, maxval = 60, group = grpR, inline = "r1", tooltip = "The last N days of the module\'s event: up / down closes and the average RTH gap; where price sits in this week\'s and this month\'s range.", display = display.none)')
w('showSg  = input.bool(true, "Stages card", group = grpR, inline = "v0", display = display.none)')
w('sgOn    = input.string("Price chart", "", options = ["Price chart", "Indicator pane"], group = grpR, inline = "v0", display = display.none)')
w('sgPos   = input.string("Bottom left", "", options = %s, group = grpR, inline = "v0", display = display.none)' % POS8)
w('showCk  = input.bool(true, "Clock card", group = grpR, inline = "r3", display = display.none)')
w('ckOn    = input.string("Indicator pane", "", options = ["Price chart", "Indicator pane"], group = grpR, inline = "r3", display = display.none)')
w('ckPos   = input.string("Top right", "", options = %s, group = grpR, inline = "r3", display = display.none)' % POS8)
w('fdgPos  = input.string("Top left", "Findings table", options = %s, group = grpR, tooltip = "Grimmjow, the Fed map or Shirosaki, in the indicator pane.", display = display.none)' % POS8)
w('')
w('grpK = "Event clock"')
w('kBands = input.bool(true, "10–90 and 25–75 bands", group = grpK, display = display.none)')
w('kRef   = input.bool(true, "Reference path", group = grpK, tooltip = "On the module\'s days: the normal-day median. On other days: the next event\'s median.", display = display.none)')
w('kPast  = input.bool(true, "Earlier days, faded", group = grpK, display = display.none)')
w('')
w('grpM = "Data"')
w('dxySym  = input.symbol("TVC:DXY", "DXY", group = grpM, inline = "m0", display = display.none)')
w('vixSym  = input.symbol("CBOE:VIX", "VIX", group = grpM, inline = "m0", display = display.none)')
w('ylSym   = input.symbol("TVC:US10Y", "10Y", group = grpM, inline = "m1", display = display.none)')
w('fdRoot  = input.string("CBOT:ZQ", "Fed funds", group = grpM, inline = "m1", tooltip = "DXY, VIX and the 10-year yield are read for every module; the 30-day fed funds contracts (17 months, CBOT:ZQZ2026 = Dec 2026) for Vizard\'s Fed card and map.", display = display.none)')
names = {}
for m in MODS:
    ins, nm = module_inputs(m, libs[m['k']])
    names[m['k']] = nm
    w('')
    w('// ── %s' % m['name'])
    out.extend(ins)

w('')
w('// ═══════════════════════════════════════════════════════════════ Chart data, requested once for every module')
for fn in ('dateKey', 'anchorKey', 'inWin', 'winBars'):
    pass
DES = open(SRC + '/Desgarron.pine', encoding='utf-8').read().split('\n')


def fn_src(name, src=DES):
    i = next(k for k, l in enumerate(src) if l.startswith(name + '('))
    o = [src[i]]
    for l in src[i + 1:]:
        if l.startswith(' '):
            o.append(l)
        else:
            break
    return o


for fn in ('dateKey', 'anchorKey', 'inWin', 'winBars', 'adrCalc', 'mtd', 'athD'):
    out.extend(fn_src(fn))
w('AN = anchorI == "Trading day (18:00)" ? 0 : anchorI == "NY midnight" ? 1 : 2')
w('string tfI = timeframe.isintraday ? timeframe.period : "D"')
w('[ADR, ADRtd] = request.security(syminfo.tickerid, "15", [adrCalc(AN), adrCalc(0)])')
w('[wO, wH, wL, wC] = request.security(syminfo.tickerid, "W", [open, high, low, close], lookahead = barmerge.lookahead_on)')
w('[moH, moL] = request.security(syminfo.tickerid, "M", [high, low], lookahead = barmerge.lookahead_on)')
w('[mtH, mtL, mtO] = request.security(syminfo.tickerid, "D", mtd(), lookahead = barmerge.lookahead_on)')
w('[athP, athPT] = request.security(syminfo.tickerid, "D", athD(), lookahead = barmerge.lookahead_on)')
w('float dxL = request.security(dxySym, tfI, close, ignore_invalid_symbol = true)')
w('[dxA, dx20] = request.security(dxySym, "D", [ta.sma(high - low, 20)[1], close[20]], lookahead = barmerge.lookahead_on, ignore_invalid_symbol = true)')
w('[dTC, dA0, dA1] = request.security(dxySym, "D", [time_close, ta.atr(20), ta.atr(20)[1]], lookahead = barmerge.lookahead_on, ignore_invalid_symbol = true)')
w('float dx4 = request.security(dxySym, "W", close[1] / close[5] - 1, lookahead = barmerge.lookahead_on, ignore_invalid_symbol = true)')
w('[vTC, vC0, vC1, vS0, vS1] = request.security(vixSym, "D", [time_close, close, close[1], ta.sma(close, 20), ta.sma(close, 20)[1]], lookahead = barmerge.lookahead_on, ignore_invalid_symbol = true)')
w('float vixL = request.security(vixSym, tfI, close, ignore_invalid_symbol = true)')
w('float vxC = vC1                                            // VIX\'s prior close and its 20-day average (completed days)')
w('float vxA = vS1')
w('[yTC, yC0, yC1] = request.security(ylSym, "D", [time_close, close, close[1]], lookahead = barmerge.lookahead_on, ignore_invalid_symbol = true)')
w('float ylL = request.security(ylSym, tfI, close, ignore_invalid_symbol = true)')
w('// NQ · ES · RTY (or MNQ · MES · M2K) and their week open, for Gran Rey Cero\'s readout under the CPI release')
w('bool   famOk = syminfo.root == "NQ" or syminfo.root == "ES" or syminfo.root == "RTY" or syminfo.root == "MNQ" or syminfo.root == "MES" or syminfo.root == "M2K"')
w('bool   famMc = syminfo.root == "MNQ" or syminfo.root == "MES" or syminfo.root == "M2K"')
w('string famSx = famOk ? str.replace(syminfo.ticker, syminfo.root, "") : "1!"')
w('string famPx = famOk ? syminfo.prefix : "CME_MINI"')
w('idxTk(int i) => famPx + ":" + (famMc ? (i == 0 ? "MNQ" : i == 1 ? "MES" : "M2K") : (i == 0 ? "NQ" : i == 1 ? "ES" : "RTY")) + famSx')
w('wkOpenF() =>')
w('    var float wo = na')
w('    bool nw = ta.change(time("W")) != 0')
w('    if nw or na(wo)')
w('        wo := open')
w('    [open, wo]')
w('[nqO, nqW] = request.security(idxTk(0), timeframe.period, wkOpenF(), ignore_invalid_symbol = true)')
w('[esO, esW] = request.security(idxTk(1), timeframe.period, wkOpenF(), ignore_invalid_symbol = true)')
w('[ryO, ryW] = request.security(idxTk(2), timeframe.period, wkOpenF(), ignore_invalid_symbol = true)')
w('// the seventeen fed funds months from the one before the last bar\'s month (Vizard), one dynamic request each')
w('var int zqY = year(last_bar_time, TZ)')
w('var int zqM = month(last_bar_time, TZ)')
w('zqTk(int i) =>')
w('    int t = zqY * 12 + zqM - 2 + i')
w('    int m = t % 12 + 1')
w('    fdRoot + str.substring("FGHJKMNQUVXZ", m - 1, m) + str.tostring(int(math.floor(t / 12)))')
w('var array<float> ZQF = array.new<float>(17, na)')
w('for i = 0 to 16')
w('    ZQF.set(i, request.security(zqTk(i), tfI, close, ignore_invalid_symbol = true))')
w('varip int beat = 0')
w('if barstate.isrealtime')
w('    beat += 1')
w('// drawings placed by bar_index are anchored through `time`; a 1-minute trading day is ~1,380 bars')
w('max_bars_back(time, 5000)')
w('')
w('// ═══════════════════════════════════════════════════════════════ Modules')
for m in MODS:
    L = libs[m['k']]
    w('// ── %s' % m['name'])
    w(cfg_new(m, L, names[m['k']]))
    w('var %s.Feed f%s = %s.Feed.new()' % (m['a'], m['k'], m['a']))
    w('var %s.State s%s = %s.newState()' % (m['a'], m['k'], m['a']))
    w('if on%s' % m['k'])
    for n in L.feed:
        w('    f%s.%s := %s' % (m['k'], n, n))
    for n in sorted(L.hist):
        if n in L.feed:
            w('    f%s.%s_1 := %s' % (m['k'], n, FEED_SRC.get(n + '_1', n + '[1]')))
    w('    %s.step1(%s)' % (m['a'], call_args(L, 'step1', m['k'])))
w('')
w('// which module the cards and the pane follow: the one whose day is today or comes next, or the pinned one')
w('int tdKm = dateKey(time + 6 * 3600000)')
w('pickAct() =>')
w('    int best = 0')
w('    int bk   = 99999999')
for i, m in enumerate(MODS, 1):
    w('    if on%s' % m['k'])
    w('        int k = %s.nextDay(%s)' % (m['a'], call_args(libs[m['k']], 'nextDay', m['k'])))
    w('        if not na(k) and k < bk')
    w('            best := %d' % i)
    w('            bk   := k')
w('    best')
w('var int act = 0')
w('if barstate.isfirst or tdKm != tdKm[1] or barstate.islast')
pin = ' : '.join('followI == "%s" and on%s ? %d' % (m['name'], m['k'], i) for i, m in enumerate(MODS, 1))
w('    act := %s : pickAct()' % pin)
for i, m in enumerate(MODS, 1):
    w('c%s.on := act == %d' % (m['k'], i))
w('')
w('// a module that stops being followed (the day turned) gives up its tables and last-bar drawings')
w('dropT(table t) =>')
w('    if not na(t)')
w('        t.delete()')
w('    table r = na')
w('    r')
w('dropP(array<polyline> a) =>')
w('    if not na(a)')
w('        for x in a')
w('            x.delete()')
w('        a.clear()')
w('dropL(array<line> a) =>')
w('    if not na(a)')
w('        for x in a')
w('            x.delete()')
w('        a.clear()')
w('dropLb(array<label> a) =>')
w('    if not na(a)')
w('        for x in a')
w('            x.delete()')
w('        a.clear()')
w('dropB(array<box> a) =>')
w('    if not na(a)')
w('        for x in a')
w('            x.delete()')
w('        a.clear()')
w('if barstate.islast')
for i, m in enumerate(MODS, 1):
    L = libs[m['k']]
    w('    if act != %d' % i)
    for n, t in L.state.items():
        if t == 'table':
            w('        %s := dropT(%s)' % (sp(m['k'], n), sp(m['k'], n)))
    for n in ('KP',):
        w('        dropP(%s)' % sp(m['k'], n))
    for n in ('KL', 'RL'):
        w('        dropL(%s)' % sp(m['k'], n))
    for n in ('KT', 'RT'):
        w('        dropLb(%s)' % sp(m['k'], n))
    w('        dropB(%s)' % sp(m['k'], 'RB'))
w('')
w('// the rest of each module: structure, clock, cards')
for m in MODS:
    L = libs[m['k']]
    w('if on%s' % m['k'])
    for k in range(2, len(L.steps) + 1):
        w('    %s.step%d(%s)' % (m['a'], k, call_args(L, 'step%d' % k, m['k'])))
w('')
w('// ═══════════════════════════════════════════════════════════════ Event clock (the followed module) and the windows')


def pick(field):
    return ' : '.join('act == %d ? %s' % (i, sp(m['k'], m['plots'][field])) for i, m in enumerate(MODS, 1)) + ' : na'


w('float pT  = %s' % pick('T'))
w('color pTc = %s' % pick('TC'))
w('float pE  = %s' % pick('E'))
w('color pEc = %s' % pick('EC'))
w('float pH  = %s' % pick('H'))
w('plot(pT, "Today", color = pTc, linewidth = 3, style = plot.style_linebr, display = display.all - display.status_line)')
w('plot(pE, "Earlier days", color = pEc, linewidth = 1, style = plot.style_linebr, display = display.all - display.status_line)')
w('// invisible headroom: the scale leaves room above the bands for the cards at the top of the pane')
w('plot(pH, "Headroom", color = #00000000, editable = false, display = display.pane)')
for m in MODS:
    for f, title in m['bgs']:
        w('bgcolor(on%s ? %s : na, title = "%s · %s", force_overlay = true)' % (m['k'], sp(m['k'], f), m['name'], title))
open(os.path.join(OUTDIR, 'Hueco_Mundo.pine'), 'w', encoding='utf-8').write('\n'.join(out) + '\n')
print('Hueco_Mundo.pine', len(out), 'lines')
