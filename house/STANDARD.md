# House standard for the indicators

*Written 5 Nov 2026 during the clean-house pass. This is the Hadome step (standardise, so the problem cannot come back): every new or changed script meets it, and `audit.py` checks the parts that can be measured.*

## 1. Settings
- **View comes first.** It holds theme, layout, card position, card text size, chart text size and **Text colour**.
- **Text colour** has two modes. *Auto (theme)* uses white text on a dark background and black on a light one. *Custom* takes a **card** colour, plus a **chart** colour where the script draws text that follows the chart background.
  - Scripts whose labels all take colours the user sets (OpenGaps) have no text colour setting.
  - Calendar modules leave out `active =` so that `pine2lib` can build them.
- Every input has a short title. Tooltips carry the tested numbers. On an inline row, the tooltip sits on the row's last input.
- **5S, sort:** no setting does nothing, and no unused global or function is left in. `audit.py` reports 0 of each.

## 2. Higher-timeframe and PO3 candles (Hadō 99's system)
The settings, in this order:
- Show (and how many).
- Offset (bars right of price).
- Width and gap, where 0 = auto by chart timeframe.
- **Colours:** the indicator's own style, *ICT (green / black)* or *Custom* (body, border and wick, each up and down).
  - The own style is Model, Up / down, or Session Map.
  - With ICT, black turns white on a dark chart.
- Wick width.
- Tags, times and countdown, wherever the candles have them.
- Forming candle dashed.

Drawing rules:
- Wicks stop at the body.
- The forming candle has a dashed border.
- The countdown sits over the forming candle or in its chip.

Candles that move while price trades are made once and moved with setters. They are not deleted and redrawn on every tick: that was Mangekyō's lag.

| Script | Candles |
|---|---|
| Hadō 99 | pair candles plus up to 4 more sets (the source of the system) |
| Mangekyō | PO3 of the graded gap |
| Hōgyoku | profile candles, four markets |
| Getsuga | Mon–Fri day candles and the week candle |
| Gran Rey Cero / Hueco Mundo | model candle with today inside it, and the week |
| Shikai / Bankai Session Map | session candles |

## 3. Market structure
**The rules:**
- A break is a candle **close** beyond the swing.
- **MSS** (shift, against the trend):
  - dashed, from the broken swing to the candle that closed beyond it;
  - named at the swing, *TF MSS ▲ / ▼*;
  - the newest is drawn in full and older ones fade to 40%.
- **BOS** (break with the trend):
  - dotted at 35% transparency, from the swing to the break;
  - named at the break, *TF BOS ▲ / ▼*.
- **Flip level**:
  - dotted at 25% transparency, from the swing to the right edge;
  - drawn in the colour of the side it would turn structure to;
  - named on the right, *TF flip ▲ / ▼ price*.
- **Swing marks:** optional, ▼ over highs and ▲ under lows.
- **Labels:** tiny, no background, in the line's colour. Bullish labels sit above the level and bearish ones below. Each has a tooltip with the time and price.
- **TF tag:** *4H*, *RTH*, *D*, *H*, *M15* and so on. It is left out only where structure is on the chart's own timeframe (Suzumebachi).

**Settings, in this order:**
- On/off, with the timeframe in the title.
- Swing size.
- Shifts or swings kept.
- *BOS* and *Flip level* on one row.
- Swing marks.
- *Bullish* and *Bearish* colours on one row.

| Script | Structure |
|---|---|
| Getsuga | 4H |
| Benihime | RTH-only 1H |
| Sharingan | D, and H / M15 / M5 / M1 layers |
| Suzumebachi | chart timeframe; its label adds the scenario and the tested odds |

## 4. Hueco Mundo build
- The libraries are **generated** from the four calendar modules (`hmbuild/make_hm.py`). They are never hand-edited.
- `prep.py` takes out each module's own corner rule; Hueco Mundo places every card itself.
- Rebuild after any module change, then raise the library version in the import lines when publishing.
- Shared settings (View, cards, data, text colour) are set once in Hueco Mundo and handed to every module.

## 5. Before delivery (check)
- Run `python3 audit.py src`.
  - 0 not View-first and 0 without text colour.
  - 0 unused inputs, globals and functions.
  - 0 candles and 0 structure off the standard.
- Run the parse check, `pine_size.py` and `pine_limits.py` on every changed script.
- Render a mock-up of each changed visual.
- Not compiled on TradingView unless the user tests it.
