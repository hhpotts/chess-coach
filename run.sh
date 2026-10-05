#!/bin/zsh
# Pull latest chess.com games, analyse new ones, rebuild and open the coach page.
set -e
cd "${0:A:h}"
PY=.venv/bin/python
quiet() { grep -vE 'blake2|hashlib|Traceback \(most recent|globals\(\)|return __get|raise ValueError|ValueError: unsupported hash|^\s+\^+$|hashlib.py|null moves to UCI' || true; }
$PY fetch.py 2>&1 | quiet
$PY analyse.py 2>&1 | quiet
$PY maia_score.py 2>&1 | quiet | grep -v '%|'
$PY deep.py 2>&1 | quiet
[ -f data/puzzles.json ] || $PY puzzles.py 2>&1 | quiet
$PY report.py 2>&1 | quiet
[ "$1" = "--no-open" ] || open coach.html
