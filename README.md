# Chess Coach

Personal chess training built from my chess.com games: Stockfish analysis, Maia-2 "how human is this mistake" scores, themed Lichess puzzles and a small opening repertoire, all in one local page (`coach.html`).

## Setup

```sh
brew install stockfish zstd
python3.11 -m venv .venv && .venv/bin/pip install chess maia2
mkdir -p data && curl -L -o data/lichess_db_puzzle.csv.zst https://database.lichess.org/lichess_db_puzzle.csv.zst
```

## Use

```sh
./run.sh            # fetch new games, analyse, rebuild coach.html and open it
./run.sh --no-open  # same, without opening a browser tab
./lookup G47-11w    # print the cached briefing for a reference copied from the page
```

Pipeline: `fetch.py` (chess.com API) → `analyse.py` (Stockfish, cached per game) → `maia_score.py` → `deep.py` (deeper per-mistake briefings) → `puzzles.py` (once) → `report.py` (fills `coach_template.html`).

Set the chess.com username in `fetch.py` (`USER`) and `analyse.py` (`ME`).
