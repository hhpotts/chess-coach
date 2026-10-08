"""Download all of a player's games from the chess.com Published-Data API into data/games.pgn."""
import json, sys, urllib.request
from pathlib import Path

USER = "harryhpotts"
UA = {"User-Agent": "personal-chess-coach/1.0"}
OUT = Path(__file__).parent / "data" / "games.pgn"


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA)) as r:
        return r.read().decode()


def main():
    archives = json.loads(get(f"https://api.chess.com/pub/player/{USER}/games/archives"))["archives"]
    pgns, acc = [], {}
    for a in archives:
        for g in json.loads(get(a))["games"]:
            # chess variants / daily games without standard rules are skipped
            if g.get("rules") == "chess" and g.get("pgn"):
                pgns.append(g["pgn"].strip())
                # chess.com's own Game Review accuracy, when the game has been reviewed
                if "accuracies" in g:
                    me = "white" if g["white"]["username"].lower() == USER else "black"
                    acc[g["url"]] = dict(me=g["accuracies"][me], opp=g["accuracies"]["black" if me == "white" else "white"])
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text("\n\n".join(pgns) + "\n")
    (OUT.parent / "chesscom.json").write_text(json.dumps(acc))
    print(f"{len(pgns)} games from {len(archives)} monthly archives -> {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
