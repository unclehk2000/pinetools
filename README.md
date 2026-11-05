# pinetools

Size and limit checks, fixes and a compile check for TradingView **Pine Script v6**, built while shipping the Hueco Mundo indicator set (16 indicators, several over 100k characters). Every script was run through `pine_size.py`, `pine_limits.py` and the light compile below before it was published.

## Quick start

```bash
python3 pine_size.py MyIndicator.pine            # the three size limits, ok / RISK / FAIL
python3 pine_size.py MyIndicator.pine --top 10   # the costliest string variables
python3 pine_limits.py MyIndicator.pine          # CE10116, CE10237, plots, request calls
python3 pine_tips.py in.pine out.pine            # fix CE10117 (too many tokens)
python3 pine_hoist.py in.pine out.pine           # fix CE10295 (main body too long)
python3 pine_main.py MyIndicator.pine 10         # the heaviest global statements
python3 pine_funcs.py MyIndicator.pine           # per-function size and state
python3 pine_calls.py MyIndicator.pine           # call and argument counts
python3 pine_flat.py main.pine flat.pine --lib MyLib=MyLib.pine   # paste libraries in for a type check before publishing them
./parse_all.sh *.pine                            # syntax check, two scripts at a time (needs pynescript)
python3 house/audit.py folder/                   # the house standard: settings, text colour, unused code, candles, structure
python3 house/audit.py --check folder/           # the same, exits 1 if anything is off (a gate before delivery)
python3 house/sweep.py --audit MyIndicator.pine  # remove what the audit reports as unused
```

Python 3.9+, standard library only (`pine_check.py` needs `pip install pynescript`). For type and scope errors, paste `tv_check.js` into the browser console on any tradingview.com page (see the file).

## Why these exist

TradingView checks three size limits only at full compile ("Add to chart"). It doesn't publish how it counts any of them:

| Error | Message | What it measures |
|---|---|---|
| CE10117 | Compiled code contains too many tokens (limit 100,256) | the whole script's compiled form |
| CE10295 | The main body of the script is too long | the global scope |
| CE10205 | The if statement is too long | one `if` block |

## What we measured (14 Oct 2026)

- **Hollow v3** failed at **137,244** tokens. Desgarrón v3, Vizard, Gran Rey Cero (13 Oct) and Day of Week Profile compile.
- **Strings cost more than code.** About **1.2–1.45 tokens per string byte (UTF-8)**, against 0.3–1.2 per source token.
- **A string variable that holds a constant is copied into every use.** That covers `const`, `var` and plain globals built only from literals and never reassigned. Hollow's 20 pool tooltips (≈ 0.4–1.1k bytes each, used 2–10 times) were counted ≈ 45k bytes extra. That is the entire overflow.
- **Function calls are not inlined** (TradingView docs), and **library code doesn't count** toward the importing script.
- **Main body:** Gran Rey Cero v5 failed at an estimated 68k in its global scope; the 13 Oct version passed at 62k.
- **If block:** the pre-split Hollow `drawSh` block failed at an estimated 47k, while `drawSg` (≈ 41k) passed.

## Tools

| File | Use |
|---|---|
| `pine_size.py` | Estimates all three sizes and flags `ok` / `RISK` / `FAIL`. `--top N` lists the costliest string variables, `--ifs N` the largest if blocks, `--fns N` the largest functions. Run it before sending any script. |
| `pine_tips.py` | Fixes CE10117. It moves long constant strings used more than once into one runtime array: `var int X = txAdd("...")`, read with `TXA.get(X)`. Strings also used in `input()` keep a const for those uses. |
| `pine_hoist.py` | Fixes CE10295. It moves heavy one-off global work into functions: `var` loaders such as `var array<float> CK = parseMilli(...)` and `if barstate.isfirst/islast` blocks that don't reassign globals. |
| `pine_main.py` | Lists the global scope's heaviest statements. |
| `pine_funcs.py`, `pine_calls.py` | Per-function size and state, and call/argument counts. |
| `parse_all.sh` | Runs `pine_check.py` (pynescript) on each file, two at a time, one result line each, then `DONE`. pynescript takes minutes on a 1,000-line script, so run it in the background. |
| `pine_flat.py` | For checking only. Pastes imported libraries into the importing script, prefixing their names by alias (`des.step1` becomes `des_step1`), so TradingView's checker can type-check Hueco Mundo and all four libraries together before they're published. |

In the original build (see the how-we-got-here repo):
- Hollow's build script ended with `pine_tips.convert`.
- Gran Rey Cero's CPI-structure patch ended with `pine_hoist.hoist(S, 5000)`.
- Desgarrón had `pine_tips` applied to its finished file.

## House standard and audit (5 Nov 2026)

`house/STANDARD.md` is the standard every indicator follows:
- the View group first, with a *Text colour* setting (Auto (theme) / Custom);
- higher-timeframe and PO3 candles on Hadō 99's candle system;
- market structure drawn one way in every script (MSS dashed and named at the swing, BOS dotted with ▲ / ▼, flip dotted to the right edge);
- no setting, global or function that does nothing.

`house/audit.py` measures the parts that can be measured. On the 31 scripts (26 indicators, 5 libraries) the clean-house pass of 5 Nov 2026 took it from:

| Check | Before | After |
|---|---|---|
| Settings open with View | 31 / 31 | 31 / 31 |
| Text colour setting, where text follows the chart theme | 9 / 25 | 25 / 25 |
| Unused settings, globals and functions | 28 | 0 |
| Higher-timeframe / PO3 candles on Hadō 99's system | 4 / 7 | 7 / 7 |
| Market structure in the house style | 0 / 4 | 4 / 4 |

The audit reads the source only: names that are never read again, the settings' titles and groups, and a few fixed patterns for the candle and structure checks. The scripts it treats as candle and structure scripts are listed at the top of `audit.py` (`CANDLE`, `STRUCT`); add a new indicator there when it draws either. A clean audit still needs `parse_all.sh`, `pine_size.py` and `pine_limits.py`.

| File | Use |
|---|---|
| `house/audit.py` | The table above, per script and in total. `--detail NAME` lists what is behind a row; `--check` exits 1 when any total is above 0. |
| `house/sweep.py` | Removes top-level declarations, named or (`--audit`) everything the audit reports as unused, with their bodies. Run the audit again afterwards. |
| `house/txt.py` | Adds the *Text colour* setting to a script's View group and wires it into the card palette and, where the script has one, the chart text that follows the theme. `CFG` holds the 15 scripts it was run on; add a row for another. `TXT_SRC=folder python3 house/txt.py Name`. |
| `house/STANDARD.md` | The standard itself. |

Re-run against the scripts delivered on 5 Nov 2026, `txt.py` followed by `sweep.py --audit` reproduces Vizard, Desgarrón and Hollow line for line.

## Semantic check without an account

The editor's light compile, `POST https://pine-facade.tradingview.com/pine-facade/translate_light?user_name=Guest&pine_id=00000000-0000-0000-0000-000000000000` with a form field `source`, returns type and scope errors. It runs fine as Guest. It does not check the three size limits.

`tv_check.js` does exactly that from a browser tab on tradingview.com: load the files through a file input and `fetch` them with `credentials: 'omit'`.

## Hueco Mundo (14 Oct 2026, rebuilt 5 Nov 2026)

The build scripts are in `hm_build/`:
- `pine2lib.py` turns a module into a library.
- `make_hm.py` builds the four libraries and the megazord.
- `checklib.py` and the `spec_*.json` files go with them.

Rebuild after any module change: `HM_SRC=folder/with/the/four/indicators HM_OUT=output/folder python3 hm_build/make_hm.py`, then `pine_size.py` on each `HM_*.pine`. A new data feed in a module stops the build ("feed type missing") until it is added to that module's spec.

The libraries are generated and never edited by hand. Until 5 Nov 2026 they had been: they were last built on 14 Oct, and the modules' changes after that (the daily-bars ADR20, Gran Rey Cero's ±0.25 range lines, their own updates) never reached them. The build now carries everything those hand edits did, so a rebuild loses nothing:
- `prep.py` runs first and takes each module's own card-corner rule out (Hueco Mundo places every card itself), giving the position settings their plain names back (`crdPosI` becomes `crdPos`). The prepared copies go to `HM_OUT/pre`.
- `make_hm.py` writes Hueco Mundo's own corner rule and passes the placed corners (`crdPosE` and so on) to each module.
- It requests the daily-bars ADR20 (`adrD`, now in all four specs) once and feeds it to every module.
- The *Text colour* setting (`txtM`, `txtCh`, `txtCd`) is shared: set once in Hueco Mundo's View group.
- Gran Rey Cero's live PO3 objects (`LVB`, `LVL`, `LVT`) are deleted with the rest of its drawings when it stops being the followed module.

Built from the modules delivered on 5 Nov 2026, it reproduces the four libraries and `Hueco_Mundo.pine` line for line, and `checklib.py` reports 0 problems in each. When you republish, publish the libraries first and raise each version in Hueco Mundo's import lines.

TradingView found five bugs in the earlier libraries. They would have stopped them publishing, and `pine2lib.py` now handles each one:
- **CE10133:** a UDT field default must be a literal. Cfg defaults like `color.new(#f23645, 85)` are now written as `#f2364526` (alpha = 255 × (100 − t) / 100).
- **CE10085 / CE10088:** a global that is reassigned anywhere (`:=`, `+=`, ...) can't become a library `const`. It goes into State.
- **CE10123:** one-line functions (`f() => ...idxNm(0)...`) now get `hmS` / `hmC` / `hmF` injected into the calls in their body too.
- **CE10237** (seen only at full compile, after Save): an exported function must use every argument it declares. `pine2lib.py` now drops `hmS` / `hmC` / `hmF` from each step that doesn't use it. It records what each step takes in `export_args`, and `make_hm.py` calls each step with exactly those. `checklib.py` flags any exported argument that is never used.

- **CE10116** (full compile only): a function can use at most 254 "external elements". A type's `.new()` takes one parameter per field, and int, float, bool and color count 2, anything else 1. That matches TradingView's counts exactly: Desgarrón's State was 449, Gran Rey Cero's 446, Vizard's 329 and Hollow's 440. `pine2lib.py` now splits State into `StatePart1..n` of at most 200 elements each. State holds the parts (`hmS.s2.KP`), `newState()` builds one, and `make_hm.py` reaches state fields through `spath`.
- `pine_limits.py` checks CE10116 (types and function parameters), CE10237, plot counts and the number of request calls. Run it with `pine_size.py` before sending anything.

After that, all four libraries type-check with no errors, and so does the flattened Hueco Mundo (megazord plus the four libraries).

Limits checked against TradingView's published ones:
- request calls: 33 unique (max 40) and 53 tuple elements (max 127);
- plot counts: 9 (max 64);
- tables: one module's at a time, at most 7 (max 9);
- global variables: about 220 (max 1,000 per scope).

The one unknown is execution time (20 s on basic plans, 40 s otherwise, over all bars). Hueco Mundo runs four modules per bar. If it times out on a long 1-minute history, switching modules off is the lever.

Open question: the CE10116 message counts a script's inputs and request results as external elements too, so the main script may have the same 254 cap. Hueco Mundo's inputs and requests come to about 357 (147 inputs = 251, plus 53 request values = 106). `HM_probe.pine` holds exactly those inputs and requests and no libraries, so saving it in TradingView answers the question.

## Licence

Mozilla Public License 2.0, see [LICENSE](LICENSE). © Unclehk2000.
