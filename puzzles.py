"""Pick beginner-level Lichess puzzles for the themes behind my most common mistakes -> data/puzzles.json.

Lichess puzzle format: FEN is the position *before* the opponent's move; Moves[0] is the
opponent's move, then the solver's and opponent's moves alternate.
"""
import chess, csv, io, json, random, subprocess
from pathlib import Path

DATA = Path(__file__).parent / "data"
SRC = DATA / "lichess_db_puzzle.csv.zst"
PER_THEME = 60
MAX_RATING = 1100
# lichess theme -> label shown in the trainer
THEMES = {
    "knightFork": "Knight forks",
    "hangingPiece": "Take the free piece",
    "pin": "Pins",
    "fork": "Forks",
    "backRankMate": "Back-rank mate",
    "mateIn1": "Mate in 1",
    "mateIn2": "Mate in 2",
    "defensiveMove": "Save your piece / defend",
    "skewer": "Skewers (diagonals and lines)",
    "discoveredAttack": "Discovered attacks",
}


def knight_fork(row):
    """Lichess has no knight-fork theme: a fork puzzle whose first solving move is made by a knight."""
    b = chess.Board(row["FEN"])
    first, solve = row["Moves"].split()[:2]
    b.push(chess.Move.from_uci(first))
    return b.piece_at(chess.Move.from_uci(solve).from_square).piece_type == chess.KNIGHT


def main():
    pools = {t: [] for t in THEMES}
    proc = subprocess.Popen(["zstdcat", str(SRC)], stdout=subprocess.PIPE)
    for row in csv.DictReader(io.TextIOWrapper(proc.stdout)):
        if int(row["Rating"]) > MAX_RATING or int(row["Popularity"]) < 85 or int(row["NbPlays"]) < 500:
            continue
        themes = row["Themes"].split()
        if "fork" in themes and knight_fork(row):
            themes = themes + ["knightFork"]
        for t in THEMES:
            if t in themes:
                pools[t].append(dict(id=row["PuzzleId"], fen=row["FEN"], moves=row["Moves"].split(),
                                     rating=int(row["Rating"]), themes=themes, url=f'https://lichess.org/training/{row["PuzzleId"]}'))
    rng = random.Random(42)
    out = {}
    for t, pool in pools.items():
        pick = rng.sample(pool, min(PER_THEME, len(pool)))
        out[t] = dict(label=THEMES[t], puzzles=sorted(pick, key=lambda p: p["rating"]))
        print(f"{t}: {len(pool)} candidates, picked {len(pick)}")
    (DATA / "puzzles.json").write_text(json.dumps(out))


if __name__ == "__main__":
    main()
