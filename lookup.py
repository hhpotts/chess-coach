"""Print a precomputed briefing for a Chess Coach reference, e.g. `./lookup G47-11w` or `./lookup P-cAm5X`.

Accepts a bare ref or a whole pasted "Copy for Claude" block (the [ref] on its first line is used).
No engine runs here: everything comes from data/analysis.json, data/deep.json and data/puzzles.json.
"""
import chess, json, re, sys
from pathlib import Path

DATA = Path(__file__).parent / "data"


def ev(cp):
    if cp is None:
        return "-"
    if abs(cp) >= 9000:
        n = 10000 - abs(cp)
        return f"M{n}" if cp > 0 else f"-M{n}"
    return f"{cp / 100:+.2f}"


def diagram(board, white_bottom=True):
    """Labelled ASCII board; uppercase = White, '.' = empty."""
    ranks = range(7, -1, -1) if white_bottom else range(8)
    files = range(8) if white_bottom else range(7, -1, -1)
    rows = [f"{r + 1} " + " ".join((board.piece_at(chess.square(f, r)) or ".").__str__() for f in files) for r in ranks]
    return "\n".join(rows + ["  " + " ".join("abcdefgh"[f] for f in files)])


def game_ref(n, move_no, side, extra):
    games = json.loads((DATA / "analysis.json").read_text())
    if not 1 <= n <= len(games):
        return f"No game {n} (have {len(games)})."
    g = games[n - 1]
    ply = (move_no - 1) * 2 + (side == "b")
    e = next((x for x in g["errors"] if x["ply"] == ply), None)
    if e is None:
        return f"Game {n} has no recorded mistake at {move_no}{side}."
    deep = json.loads((DATA / "deep.json").read_text()).get(f'{g["id"]}#{ply}', {}) if (DATA / "deep.json").exists() else {}
    me = g["color"]
    b = chess.Board(g["start_fen"])
    moves = [chess.Move.from_uci(p["uci"]) for p in g["plies"]]
    before = b.variation_san(moves[:ply]) if ply else "(start)"
    b2 = chess.Board(e["fen"])
    after = b2.variation_san(moves[ply:ply + 8])
    board = chess.Board(e["fen"])

    out = [f"## G{n}-{move_no}{side}{(' ' + extra) if extra else ''} - game {n} vs {g['opponent']} ({g['opp_elo']}), "
           f"{g['date']}, I was {me}, {g['result']} ({g['termination']})",
           g["link"],
           f"Moves before: {before}",
           f"Game continued: {after}",
           f"Board before my move ({me} at bottom; uppercase = White):", diagram(board, me == "white"), f"FEN: {e['fen']}", ""]
    if deep:
        if deep.get("in_check"):
            out.append("I was in check.")
        else:
            out.append(f"Eval before my move (my side): {ev(deep['eval_now'])}")
        prev = g["plies"][ply - 1]["san"] if ply else None
        if prev:
            atk = deep.get("their_last_move_attacks") or ["nothing new"]
            out.append(f"Their last move {prev} newly attacks: " + "; ".join(atk))
        if "threat" in deep:
            out.append(f"Their threat if I passed: {deep['threat']['line']} (eval would be {ev(deep['threat']['eval_if_i_pass'])})")
        out.append("My pieces in danger: " + ("; ".join(deep["my_pieces_in_danger"]) or "none"))
        p = deep["played"]
        out.append(f"I played {p['move']}: eval {ev(p['eval'])}. Line: {p['line']}")
    else:
        out.append(f"I played {e['played_san']}: eval {ev(e['eval_before'])} -> {ev(e['eval_after'])}. Line after: {e['refute_san']}")
    out.append(f"Category: {e['category']} ({e['severity']}, win% drop {e['drop']}) - {e['why']}")
    if deep:
        out.append("Best moves:")
        out += [f"  {m['move']:<7} {ev(m['eval']):>7}  {m['line']}" for m in deep["best_moves"]]
    else:
        out.append(f"Best: {e['best_line']} (also fine: {' '.join(e['good'])})")
    if "maia_played" in e:
        top = board.san(chess.Move.from_uci(e["maia_top"])) if e.get("maia_top") else "?"
        out.append(f"Maia (<1100 humans): {e['maia_played']:.0%} play my move, {e['maia_best']:.0%} find {e['best_san']}, most likely human move: {top}")
    if not deep:
        out.append("(No deep analysis cached for this one yet - run ./run.sh.)")
    return "\n".join(out)


def puzzle_ref(pid, extra):
    for theme, t in json.loads((DATA / "puzzles.json").read_text()).items():
        for p in t["puzzles"]:
            if p["id"] == pid:
                b = chess.Board(p["fen"])
                sans = b.variation_san([chess.Move.from_uci(u) for u in p["moves"]])
                b.push(chess.Move.from_uci(p["moves"][0]))
                return "\n".join([f"## P-{pid}{(' ' + extra) if extra else ''} - {t['label']}, rated {p['rating']}", p["url"],
                                  f"Themes: {', '.join(p['themes'])}",
                                  f"Full sequence (first move is the opponent's): {sans}",
                                  f"Puzzle position after their move ({'White' if b.turn else 'Black'} to solve):", diagram(b, b.turn), f"FEN: {b.fen()}"])
    return f"Puzzle {pid} not in the current set."


def opening_ref(li, k):
    from report import build_openings
    lines = build_openings()
    if not 1 <= li <= len(lines):
        return f"No opening line {li}."
    L = lines[li - 1]
    b = chess.Board()
    for m in L["moves"][:k]:
        b.push(chess.Move.from_uci(m["uci"]))
    notes = [f"  {m['label']}: {m['note']}" for m in L["moves"] if m["note"]]
    return "\n".join([f"## O{li}.{k} - {L['name']} ({L['group']})", L["intro"],
                      f"Full line: {chess.Board().variation_san([chess.Move.from_uci(m['uci']) for m in L['moves']])}",
                      f"Position after {k} moves:", diagram(b, L["side"] == "white"), f"FEN: {b.fen()}", "Notes:"] + notes)


def main():
    text = " ".join(sys.argv[1:]) or sys.stdin.read()
    m = re.search(r"\[?\s*(G(\d+)-(\d+)([wb])|P-([A-Za-z0-9]+)|O(\d+)\.(\d+)|OV-[\w-]+)\s*([^\]\n]*)", text)
    if not m:
        sys.exit("No reference found (expected e.g. G47-11w, P-cAm5X, O7.10).")
    extra = m.group(8).strip()
    if m.group(2):
        print(game_ref(int(m.group(2)), int(m.group(3)), m.group(4), extra))
    elif m.group(5):
        print(puzzle_ref(m.group(5), extra))
    elif m.group(6):
        print(opening_ref(int(m.group(6)), int(m.group(7))))
    else:
        print("Overview refs are self-contained - the pasted text has everything.")


if __name__ == "__main__":
    main()
