"""Stockfish-analyse every game in data/games.pgn; results cached per game in data/analysis.json."""
import chess, chess.pgn, chess.engine, io, json, math, sys
from multiprocessing import Pool
from pathlib import Path

ME = "HarryHPotts"
DEPTH = 14
DATA = Path(__file__).parent / "data"
CACHE = DATA / "analysis.json"
BLUNDER, MISTAKE = 30, 20  # drop in win-probability percentage points
VAL = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 100}
NAME = {chess.PAWN: "pawn", chess.KNIGHT: "knight", chess.BISHOP: "bishop",
        chess.ROOK: "rook", chess.QUEEN: "queen", chess.KING: "king"}


def winp(cp):
    return 50 + 50 * (2 / (1 + math.exp(-0.00368208 * cp)) - 1)


def cp_of(score, pov):
    return score.pov(pov).score(mate_score=10000)


def pinned_to(board, mv):
    """If the moving piece shields a more valuable piece from an enemy slider, return that piece."""
    me, frm = board.turn, mv.from_square
    moving = board.piece_at(frm)
    for sq, pc in board.piece_map().items():
        if pc.color == me or pc.piece_type not in (chess.BISHOP, chess.ROOK, chess.QUEEN):
            continue
        if frm not in board.attacks(sq):
            continue
        after = board.copy()
        after.remove_piece_at(frm)
        for t in after.attacks(sq):
            target = after.piece_at(t)
            if (target and target.color == me and t != mv.to_square
                    and VAL[target.piece_type] > VAL[moving.piece_type]
                    and frm in chess.SquareSet(chess.between(sq, t))):
                return target
    return None


def mate_in(cp):
    """Invert score(mate_score=10000): +n = I mate in n, -n = I get mated in n, None = no mate."""
    if abs(cp) < 9000:
        return None
    return (10000 - cp) if cp > 0 else -(10000 + cp)


def creates_threat(board, mv):
    """Does the moved piece attack the king or an enemy piece worth at least as much as itself?"""
    me, moving = board.turn, board.piece_at(mv.from_square)
    after = board.copy()
    after.push(mv)
    for s in after.attacks(mv.to_square):
        t = after.piece_at(s)
        if t and t.color != me and t.piece_type != chess.PAWN and (
                t.piece_type == chess.KING or VAL[t.piece_type] >= VAL[moving.piece_type]):
            return True
    return False


def classify(board, mv, best, pv, cp_before, cp_after):
    """Plain-English category + explanation for a bad move.

    `board` is the position before mv, `pv` the engine's line after it, scores from the mover's side.
    Works purely from stored data so cached games can be reclassified without re-running the engine.
    """
    me = board.turn
    piece = board.piece_at(mv.from_square)
    mate_before, mate_after = mate_in(cp_before), mate_in(cp_after)
    after = board.copy()
    after.push(mv)
    reply = pv[0] if pv else None

    if mate_before and mate_before > 0 and not (mate_after and mate_after > 0):
        return "missed-mate", f"You had a forced checkmate here (starting {board.san(best)})."
    if mate_after is not None and mate_after < 0:
        n = -mate_after
        return "allowed-mate", f"This lets them force checkmate in {n}." if n > 1 else "This lets them checkmate you immediately."
    if (pin := pinned_to(board, mv)) is not None:
        return "moved-pinned", (f"Your {NAME[piece.piece_type]} was pinned: it was shielding your "
                                f"{NAME[pin.piece_type]}. Moving it exposes the {NAME[pin.piece_type]}.")
    free = board.piece_at(best.to_square) if best is not None and board.is_capture(best) else None
    if best is not None and board.is_capture(best) and (
            not (reply and after.is_capture(reply)) or (free and VAL[free.piece_type] >= 3 and not board.is_capture(mv))):
        cap = board.piece_at(best.to_square)
        what = NAME[cap.piece_type] if cap else "pawn"
        return "missed-capture", f"Their {what} was there for the taking with {board.san(best)}."
    if reply is not None and after.is_capture(reply):
        cap = after.piece_at(reply.to_square)
        what = NAME[cap.piece_type] if cap else "pawn"
        if reply.to_square == mv.to_square:
            # a capture I can recapture is a trade; the real loss is whatever they take next
            b = after.copy()
            s0 = b.san(reply)
            b.push(reply)
            if len(pv) >= 2 and pv[1].to_square == reply.to_square and b.is_capture(pv[1]):
                s1 = b.san(pv[1])
                b.push(pv[1])
                if len(pv) >= 3 and b.is_capture(pv[2]):
                    lost = b.piece_at(pv[2].to_square)
                    lost_name = NAME[lost.piece_type] if lost else "pawn"
                    return "left-hanging", (f"Offering the {what} trade ({s0} {s1}) doesn't solve the real problem: "
                                            f"after it they take your {lost_name} with {b.san(pv[2])}.")
                return "other", f"This allows a trade ({s0} {s1}) that leaves you clearly worse."
            if after.is_check() or board.is_capture(mv) or creates_threat(board, mv):
                kind = "check" if after.is_check() else "capture" if board.is_capture(mv) else "attack"
                return "backfired-tactic", (f"Your {kind} with {board.san(mv)} doesn't work - they take your {what} "
                                            f"({s0}) and you come out behind. Calculate to the end before forcing play.")
            return "hung-moved", f"You moved your {what} to a square where they can take it ({s0})."
        attacker = board.piece_at(reply.from_square)
        if attacker and attacker.color != me and reply.to_square in board.attacks(reply.from_square):
            return "missed-threat", (f"Their {NAME[attacker.piece_type]} was already attacking your {what}. "
                                      f"This move doesn't deal with that, so they take it with {after.san(reply)}.")
        return "left-hanging", f"This leaves your {what} undefended - they take it with {after.san(reply)}."
    if reply is not None:
        b2 = after.copy()
        b2.push(reply)
        hit = [b2.piece_at(s) for s in b2.attacks(reply.to_square)
               if b2.piece_at(s) and b2.piece_at(s).color == me and b2.piece_at(s).piece_type != chess.PAWN]
        if len(hit) >= 2:
            names = " and ".join(NAME[p.piece_type] for p in hit[:2])
            return "fork", f"This walks into a fork: {after.san(reply)} attacks your {names} at once."
    if reply is not None:
        return "other", f"This lets them play {after.san(reply)}, and your position gets much worse."
    return "other", "A tactical or positional mistake."


def analyse_game(pgn_text):
    g = chess.pgn.read_game(io.StringIO(pgn_text))
    h = g.headers
    color = chess.WHITE if h["White"] == ME else chess.BLACK
    eng = chess.engine.SimpleEngine.popen_uci("stockfish")
    eng.configure({"Threads": 1, "Hash": 64})
    board = g.board()
    moves = list(g.mainline_moves())
    lim = chess.engine.Limit(depth=DEPTH)
    info = eng.analyse(board, lim)
    plies, errors = [], []
    for ply, mv in enumerate(moves):
        mover = board.turn
        before = info
        fen = board.fen()
        san = board.san(mv)
        best = before["pv"][0] if before.get("pv") else None
        pre = board.copy()
        board.push(mv)
        if board.is_game_over():
            info = None
            cp_after = (10000 if board.is_checkmate() else 0)
        else:
            info = eng.analyse(board, lim)
            cp_after = cp_of(info["score"], mover)
        cp_before = cp_of(before["score"], mover)
        drop = winp(cp_before) - winp(cp_after)
        plies.append(dict(san=san, uci=mv.uci(), mine=mover == color, drop=round(drop, 1),
                          eval_white=cp_of(info["score"], chess.WHITE) if info else (cp_after if mover == chess.WHITE else -cp_after)))
        if mover == color and drop >= MISTAKE:
            cat, why = classify(pre, mv, best, info["pv"][:4] if info else [], cp_before, cp_after)
            # good alternatives: any move within 5 win-% of the best one
            multi = eng.analyse(pre, lim, multipv=5)
            top = winp(cp_of(multi[0]["score"], mover))
            good = [m["pv"][0].uci() for m in multi if top - winp(cp_of(m["score"], mover)) <= 5]
            best_line = multi[0]["pv"][:3]
            refute = info["pv"][:4] if info and info.get("pv") else []
            nonpawn = sum(VAL[p.piece_type] for p in pre.piece_map().values() if p.piece_type not in (chess.PAWN, chess.KING))
            errors.append(dict(
                ply=ply, move_no=ply // 2 + 1, fen=fen, played=mv.uci(), played_san=san,
                best=best_line[0].uci(), best_san=pre.san(best_line[0]), best_line=pre.variation_san(best_line),
                good=good, refute=[m.uci() for m in refute],
                refute_san=board.variation_san(refute) if refute else "",
                severity="blunder" if drop >= BLUNDER else "mistake", drop=round(drop, 1),
                eval_before=cp_before, eval_after=cp_after, category=cat, why=why,
                piece=pre.piece_at(mv.from_square).symbol().upper(),
                phase="opening" if ply < 20 else ("endgame" if nonpawn <= 26 else "middlegame")))
    eng.quit()
    won = h["Result"] == ("1-0" if color else "0-1")
    return dict(
        id=h.get("Link") or f'{h["Date"]}-{h["White"]}-{h["Black"]}-{h.get("EndTime", "")}',
        link=h.get("Link", ""), date=h["Date"], color="white" if color else "black",
        opponent=h["Black"] if color else h["White"],
        my_elo=int(h["WhiteElo" if color else "BlackElo"]), opp_elo=int(h["BlackElo" if color else "WhiteElo"]),
        result="draw" if h["Result"] == "1/2-1/2" else ("win" if won else "loss"),
        termination=h["Termination"], opening=h.get("ECOUrl", "").rsplit("/", 1)[-1].replace("-", " "),
        time_control=h.get("TimeControl", ""), end=h.get("EndDate", h["Date"]) + " " + h.get("EndTime", ""),
        start_fen=h.get("FEN", chess.STARTING_FEN), plies=plies, errors=errors)


def game_id(pgn_text):
    h = chess.pgn.read_headers(io.StringIO(pgn_text))
    return h.get("Link") or f'{h["Date"]}-{h["White"]}-{h["Black"]}-{h.get("EndTime", "")}'


def split_pgn(text):
    out, fh = [], io.StringIO(text)
    while (g := chess.pgn.read_game(fh)) is not None:
        if g.headers.get("Variant", "Standard") == "Standard" and len(list(g.mainline_moves())) > 0:
            out.append(str(g))
    return out


def main():
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else DATA / "games.pgn"
    cache = {g["id"]: g for g in json.loads(CACHE.read_text())} if CACHE.exists() else {}
    todo = [p for p in split_pgn(src.read_text()) if game_id(p) not in cache]
    print(f"{len(cache)} cached, analysing {len(todo)} new games", file=sys.stderr)
    with Pool(9) as pool:
        for i, g in enumerate(pool.imap_unordered(analyse_game, todo), 1):
            cache[g["id"]] = g
            if i % 10 == 0:
                print(f"  {i}/{len(todo)}", file=sys.stderr)
    games = sorted(cache.values(), key=lambda g: g["end"])
    reclassify(games)
    CACHE.write_text(json.dumps(games))


def reclassify(games):
    """Re-run classify() on cached errors so wording/rule changes apply without re-running Stockfish."""
    for g in games:
        for e in g["errors"]:
            board = chess.Board(e["fen"])
            pv = [chess.Move.from_uci(u) for u in e["refute"]]
            e["category"], e["why"] = classify(board, chess.Move.from_uci(e["played"]),
                                               chess.Move.from_uci(e["best"]), pv, e["eval_before"], e["eval_after"])


if __name__ == "__main__":
    main()
