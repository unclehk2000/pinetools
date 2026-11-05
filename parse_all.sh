#!/bin/bash
# Parse-check Pine scripts with pine_check.py, two at a time (pynescript takes minutes on a 1,000-line script).
#   bash parse_all.sh a.pine b.pine ...      one line per script ("Name.pine PARSE OK n lines" or the error), then DONE
HERE=$(cd "$(dirname "$0")" && pwd)
export HERE
printf '%s\n' "$@" | xargs -P 2 -I{} sh -c 'r=$(timeout 1500 python3 "$HERE/pine_check.py" "{}" 2>&1 | tr "\n" " " | head -c 300); echo "$(basename "{}") $r"'
echo DONE
