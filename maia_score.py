"""Add Maia-2 human-likeness to each error in data/analysis.json.

maia_played: probability a beginner (Maia's lowest band, <1100) plays the move I played.
maia_best:   probability they find the engine's best move.
High maia_played = a common beginner trap; low = a personal slip.
"""
import json
from pathlib import Path
from maia2 import model, inference

DATA = Path(__file__).parent / "data"
ELO = 1000  # Maia's lowest bucket is "<1100"


def main():
    games = json.loads((DATA / "analysis.json").read_text())
    todo = [e for g in games for e in g["errors"] if "maia_played" not in e]
    if not todo:
        print("maia: nothing new")
        return
    m = model.from_pretrained(type="rapid", device="cpu", save_root=str(DATA / "maia2_models"))
    prep = inference.prepare()
    for e in todo:
        probs, _ = inference.inference_each(m, prep, e["fen"], ELO, ELO)
        e["maia_played"] = round(probs.get(e["played"], 0.0), 3)
        e["maia_best"] = round(probs.get(e["best"], 0.0), 3)
        e["maia_top"] = max(probs, key=probs.get)
    (DATA / "analysis.json").write_text(json.dumps(games))
    print(f"maia: scored {len(todo)} errors")


if __name__ == "__main__":
    main()
