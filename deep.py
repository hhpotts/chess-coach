"""Precompute a deeper briefing for every error so lookup.py can answer instantly -> data/deep.json.

Keyed by "<game id>#<ply>" (stable across rebuilds). Only new errors are analysed.
"""
import chess, chess.engine, json, sys
from multiprocessing import Pool
from pathlib import Path

DATA = Path(__file__).parent / "data"
OUT = DATA / "deep.json"
DEPTH = 18
DANGER_RULE = 2  # bump when in_danger() changes so cached lists get recomputed
VAL = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 100}


def score(info, pov):
    return info["score"].pov(pov).score(mate_score=10000)


def line(board, pv, n=8):
    return board.variation_san(pv[:n]) if pv else ""


def attacked_pairs(board, by):
    """{(attacker_sq, target_sq)} for pieces of `by` attacking the other side's pieces."""
    out = set()
    for sq, pc in board.piece_map().items():
        if pc.color != by:
            continue
        for t in board.attacks(sq):
            tp = board.piece_at(t)
            if tp and tp.color != by:
                out.add((sq, t))
    return out


def describe(board, sq):
    p = board.piece_at(sq)
    return f"{chess.piece_name(p.piece_type)} on {chess.square_name(sq)}"


def in_danger(board, me):
    """My pieces that are attacked and either undefended or attacked by something cheaper."""
    out = []
    for sq, pc in board.piece_map().items():
        if pc.color != me or pc.piece_type == chess.KING:
            continue
        # a pinned attacker can only take along its pin line
        attackers = [a for a in board.attackers(not me, sq)
                     if not board.is_pinned(not me, a) or sq in board.pin(not me, a)]
        if not attackers:
            continue
        cheapest = min(VAL[board.piece_at(a).piece_type] for a in attackers)
        defended = bool(board.attackers(me, sq))
        if not defended or cheapest < VAL[pc.piece_type]:
            by = ", ".join(describe(board, a) for a in attackers)
            out.append(f"{describe(board, sq)} - attacked by {by}, {'defended' if defended else 'UNDEFENDED'}")
    return out


def brief(job):
    key, fen, prev_fen, played_uci, me_white = job
    me = chess.WHITE if me_white else chess.BLACK
    eng = chess.engine.SimpleEngine.popen_uci("stockfish")
    eng.configure({"Threads": 1, "Hash": 128})
    lim = chess.engine.Limit(depth=DEPTH)
    board = chess.Board(fen)
    d = {}

    # what their last move newly attacks
    if prev_fen:
        before = chess.Board(prev_fen)
        new = attacked_pairs(board, not me) - attacked_pairs(before, not me)
        d["their_last_move_attacks"] = sorted({f"{describe(board, t)} (by {describe(board, a)})" for a, t in new})

    # their threat: what they'd do if I passed
    if not board.is_check():
        null = board.copy()
        null.push(chess.Move.null())
        base = eng.analyse(board, lim)
        t = eng.analyse(null, chess.engine.Limit(depth=14))
        d["eval_now"] = score(base, me)
        d["threat"] = dict(line=line(null, t.get("pv", []), 4), eval_if_i_pass=score(t, me))
    else:
        d["in_check"] = True

    d["my_pieces_in_danger"] = in_danger(board, me)

    alts = eng.analyse(board, lim, multipv=4)
    d["best_moves"] = [dict(move=board.san(a["pv"][0]), eval=score(a, me), line=line(board, a["pv"])) for a in alts]

    played = chess.Move.from_uci(played_uci)
    after = board.copy()
    after.push(played)
    if after.is_game_over():
        d["played"] = dict(move=board.san(played), eval=None, line="game over")
    else:
        r = eng.analyse(after, lim)
        d["played"] = dict(move=board.san(played), eval=score(r, me), line=board.variation_san([played] + r.get("pv", [])[:7]))
    eng.quit()
    return key, d


def replies(job):
    """Their top replies to the better move, each with my best answer and the line that follows."""
    key, fen, best_uci, me_white = job
    me = chess.WHITE if me_white else chess.BLACK
    eng = chess.engine.SimpleEngine.popen_uci("stockfish")
    eng.configure({"Threads": 1, "Hash": 128})
    board = chess.Board(fen)
    after = board.copy()
    after.push(chess.Move.from_uci(best_uci))
    out = []
    if not after.is_game_over():
        for a in eng.analyse(after, chess.engine.Limit(depth=16), multipv=3):
            pv = a.get("pv", [])[:7]
            if pv:
                out.append(dict(uci=[m.uci() for m in pv], line=after.variation_san(pv), eval=score(a, me)))
    eng.quit()
    return key, out


def best_of(d, fen):
    """First move of the deep top line (falls back to None)."""
    from explain import parse_line
    top = (d.get("best_moves") or [{}])[0]
    mv = parse_line(chess.Board(fen), top.get("line", ""), 1)
    return mv[0].uci() if mv else None


def main():
    games = json.loads((DATA / "analysis.json").read_text())
    cache = json.loads(OUT.read_text()) if OUT.exists() else {}
    jobs = []
    for g in games:
        b = chess.Board(g["start_fen"])
        fens = [b.fen()]
        for p in g["plies"]:
            b.push(chess.Move.from_uci(p["uci"]))
            fens.append(b.fen())
        for e in g["errors"]:
            key = f'{g["id"]}#{e["ply"]}'
            if key not in cache:
                prev_fen = fens[e["ply"] - 1] if e["ply"] > 0 else None
                jobs.append((key, e["fen"], prev_fen, e["played"], g["color"] == "white"))
    print(f"deep: {len(cache)} cached, analysing {len(jobs)}", file=sys.stderr)
    with Pool(9) as pool:
        for i, (key, d) in enumerate(pool.imap_unordered(brief, jobs), 1):
            cache[key] = d
            if i % 50 == 0:
                print(f"  {i}/{len(jobs)}", file=sys.stderr)
                OUT.write_text(json.dumps(cache))
        OUT.write_text(json.dumps(cache))
        # refresh the (engine-free) danger lists when the rule changes
        for g in games:
            for e in g["errors"]:
                c = cache.get(f'{g["id"]}#{e["ply"]}')
                if c is not None and c.get("danger_rule") != DANGER_RULE:
                    c["my_pieces_in_danger"] = in_danger(chess.Board(e["fen"]), chess.Board(e["fen"]).turn)
                    c["danger_rule"] = DANGER_RULE
        # branches after the better move, for entries that don't have them yet
        rjobs = []
        for g in games:
            for e in g["errors"]:
                key = f'{g["id"]}#{e["ply"]}'
                d = cache.get(key)
                if d is not None and "replies" not in d:
                    b = best_of(d, e["fen"]) or e["best"]
                    d["replies_after"] = b
                    rjobs.append((key, e["fen"], b, g["color"] == "white"))
        print(f"deep: adding reply branches for {len(rjobs)}", file=sys.stderr)
        for i, (key, r) in enumerate(pool.imap_unordered(replies, rjobs), 1):
            cache[key]["replies"] = r
            if i % 50 == 0:
                print(f"  {i}/{len(rjobs)}", file=sys.stderr)
                OUT.write_text(json.dumps(cache))
    OUT.write_text(json.dumps(cache))


if __name__ == "__main__":
    main()
