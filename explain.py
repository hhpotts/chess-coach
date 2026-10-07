"""Plain-English "why the better move is better", built from cached engine data (no engine runs here)."""
import re
import chess

VAL = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0}


def parse_line(board, san_line, n=8):
    """SAN line like '30. Qd2 Qa7 31. Bc6' or '30...Qd3+ 31. Ke1' -> legal moves from `board`."""
    b, moves = board.copy(), []
    for tok in san_line.split():
        tok = re.sub(r"^\d+\.+", "", tok)
        if not tok:
            continue
        try:
            mv = b.parse_san(tok)
        except ValueError:
            break
        moves.append(mv)
        b.push(mv)
        if len(moves) >= n:
            break
    return moves


def material(board, me):
    return sum(VAL[p.piece_type] * (1 if p.color == me else -1) for p in board.piece_map().values())


def amount(points):
    return {1: "a pawn", 2: "two pawns", 3: "a piece", 4: "a piece and a pawn", 5: "a rook's worth",
            6: "a rook and a pawn's worth", 9: "a queen's worth"}.get(points, f"{points} points of material")


def mate_in(cp):
    if cp is None or abs(cp) < 9000:
        return None
    return (10000 - cp) if cp > 0 else -(10000 + cp)


def standing(cp):
    m = mate_in(cp)
    if m is not None:
        return f"you have checkmate in {m}" if m > 0 else ("you get checkmated" if m == 0 else f"you get checkmated in {-m}")
    if cp is None:
        return "game over"
    s = f"{cp / 100:+.1f}"
    if cp >= 300:
        return f"winning ({s})"
    if cp >= 100:
        return f"better for you ({s})"
    if cp > -100:
        return f"about level ({s})" if abs(cp) > 15 else "a draw (0.0)"
    if cp > -300:
        return f"worse for you ({s})"
    return f"losing ({s})"


def why_best(e, deep):
    """One short paragraph explaining why the engine's move beats the move played."""
    board = chess.Board(e["fen"])
    me = board.turn
    top = (deep.get("best_moves") or [{}])[0]
    pv = parse_line(board, top.get("line", "")) or [chess.Move.from_uci(e["best"])]
    best = pv[0]
    best_san = board.san(best)
    after = board.copy()
    after.push(best)
    best_eval = top.get("eval", e["eval_before"])
    played_eval = (deep.get("played") or {}).get("eval", e["eval_after"])
    parts = []

    m = mate_in(best_eval)
    if m is not None and m > 0:
        line = board.variation_san(pv[:2 * m - 1])
        return f"{best_san} starts a forced checkmate: {line}. Your move lets them escape, and it's only {standing(played_eval)}."

    # what the move does directly
    moved = board.piece_at(best.from_square)
    if board.is_capture(best):
        cap = board.piece_at(best.to_square)
        cap_name = chess.piece_name(cap.piece_type) if cap else "pawn"
        recaptured = len(pv) > 1 and pv[1].to_square == best.to_square and after.is_capture(pv[1])
        text = f"{best_san} takes their {cap_name}" + ("" if recaptured else " for free")
        if recaptured:
            b1 = after.copy()
            san1 = b1.san(pv[1])
            b1.push(pv[1])
            if len(pv) > 2 and pv[2].to_square == best.to_square and b1.is_capture(pv[2]):
                rec = b1.piece_at(pv[2].from_square)
                text += (f"; if they take back with {san1}, your {chess.piece_name(rec.piece_type)} on "
                         f"{chess.square_name(pv[2].from_square)} recaptures ({b1.san(pv[2])})")
                if best.from_square in chess.SquareSet(chess.between(pv[2].from_square, best.to_square)):
                    line = "diagonal" if shape(board, pv[2].from_square, best.to_square) == "diagonal" else "line"
                    text += f" - it was lined up behind your {chess.piece_name(moved.piece_type)} on the same {line}"
            elif len(pv) > 2 and b1.is_capture(pv[2]):
                got = b1.piece_at(pv[2].to_square)
                text += (f"; if they take back with {san1}, you take their "
                         f"{chess.piece_name(got.piece_type) if got else 'pawn'} with {b1.san(pv[2])}")
            else:
                text += ", and the trade comes out in your favour"
        parts.append(text)
    danger = [(n, chess.parse_square(sq)) for n, sq in re.findall(r"^(\w+) on ([a-h][1-8])", "\n".join(deep.get("my_pieces_in_danger", [])), re.M)]
    for name, sq in danger:
        if best.from_square == sq:
            parts.append(f"{best_san} moves your {name} out of danger")
            break
        if after.piece_at(sq) and after.is_attacked_by(me, sq) and not board.is_attacked_by(me, sq):
            parts.append(f"{best_san} protects your {name} on {chess.square_name(sq)}")
            break

    # their threat
    threat = deep.get("threat") or {}
    now = deep.get("eval_now", e["eval_before"])
    if threat.get("line") and threat.get("eval_if_i_pass") is not None and now - threat["eval_if_i_pass"] >= 150 and best_eval >= now - 100:
        toks = [re.sub(r"^\d+\.+", "", t) for t in threat["line"].split()]
        tmove = next((t for t in toks if t), "")
        if tmove and not any(tmove in p for p in parts):
            parts.append(f"it stops their threat of {tmove}")

    # pressure it creates
    if after.is_check():
        parts.append("it gives check, so they must answer it before doing anything else")
    else:
        hits = [after.piece_at(s) for s in after.attacks(best.to_square)
                if after.piece_at(s) and after.piece_at(s).color != me and after.piece_at(s).piece_type != chess.PAWN
                and VAL[after.piece_at(s).piece_type] >= VAL[moved.piece_type]]
        if hits and not board.is_capture(best):
            names = " and ".join(sorted({chess.piece_name(h.piece_type) for h in hits}, key=len))
            parts.append(f"it attacks their {names}, so they have to respond to that first")

    # queen trade when ahead
    b = board.copy()
    queens_off = False
    for mv in pv[:4]:
        cap = b.piece_at(mv.to_square)
        if cap and cap.piece_type == chess.QUEEN:
            queens_off = True
        b.push(mv)
    if queens_off and material(board, me) >= 3 and not any("queen" in p and "takes" in p for p in parts):
        parts.append("it heads for a queen trade, which suits you when you're ahead because their attack disappears")

    # how the material ends up along each line
    def net(line_moves):
        bb = board.copy()
        start = material(bb, me)
        for mv in line_moves[:6]:
            bb.push(mv)
        return material(bb, me) - start
    gain = net(pv)
    played_pv = parse_line(board, (deep.get("played") or {}).get("line", ""))
    loss = net(played_pv) if played_pv else None

    if not parts:
        why = e.get("why", "").rstrip(".")
        parts.append(f"{best_san} is a calm, safe move - the point is avoiding {e['played_san']}" +
                     (f": {why[0].lower() + why[1:]}" if why else ""))
    text = best_san + parts[0][2:] if parts[0].startswith("it ") else parts[0]
    if len(parts) > 1:
        text += "; " + "; ".join(parts[1:])
    text += "."
    if gain >= 1 and gain * 100 >= best_eval - 250:
        text += f" Along the engine line you come out {amount(gain)} up."
    if loss is not None and loss <= -1:
        text += f" After your move you'd lose {amount(-loss)}."
    text += f" Overall: {standing(best_eval)} instead of {standing(played_eval)}."
    return text + branch_summary(branches(e, deep))


def describe(board, mv, whose="their"):
    """Short phrase for what a move does, e.g. 'taking their knight', 'with check'. `whose` = owner of the target pieces."""
    after = board.copy()
    after.push(mv)
    if after.is_checkmate():
        return "checkmate"
    bits = []
    if board.is_capture(mv):
        cap = board.piece_at(mv.to_square)
        bits.append(f"taking {whose} {chess.piece_name(cap.piece_type) if cap else 'pawn'}")
    if after.is_check():
        bits.append("with check")
    elif not bits:
        me, moved = board.turn, board.piece_at(mv.from_square)
        hits = [after.piece_at(s) for s in after.attacks(mv.to_square)
                if after.piece_at(s) and after.piece_at(s).color != me and after.piece_at(s).piece_type != chess.PAWN
                and VAL[after.piece_at(s).piece_type] >= VAL[moved.piece_type]]
        if hits:
            bits.append(f"attacking {whose} " + " and ".join(sorted({chess.piece_name(h.piece_type) for h in hits})))
    return " ".join(bits)


def branches(e, deep):
    """Their main replies to the better move: [{reply, answer, text, line, eval, uci}]."""
    if not deep.get("replies") or not deep.get("replies_after"):
        return []
    board = chess.Board(e["fen"])
    board.push(chess.Move.from_uci(deep["replies_after"]))
    out = []
    for r in deep["replies"]:
        moves = [chess.Move.from_uci(u) for u in r["uci"]]
        b = board.copy()
        reply_san = b.san(moves[0])
        reply_does = describe(b, moves[0], "your")
        b.push(moves[0])
        if len(moves) > 1:
            answer_san, answer_does = b.san(moves[1]), describe(b, moves[1])
            text = (f"If they play {reply_san}" + (f" ({reply_does})" if reply_does else "") +
                    f", you answer {answer_san}" + (f", {answer_does}" if answer_does and answer_does != "checkmate" else "") +
                    (" - checkmate" if answer_does == "checkmate" else "") + f". Result: {standing(r['eval'])}.")
        else:
            text = f"If they play {reply_san}: {standing(r['eval'])}."
        out.append(dict(reply=reply_san, text=text, line=r["line"], eval=r["eval"], uci=r["uci"]))
    return out


def branch_summary(br):
    if not br:
        return ""
    evals = [b["eval"] for b in br]
    worst = min(evals)
    if all(mate_in(v) and mate_in(v) > 0 for v in evals):
        return " Every reply they have still gets checkmated."
    if worst >= 300:
        return f" Whatever they try ({', '.join(b['reply'] for b in br)}), you stay winning."
    if worst >= 100:
        return f" Against their best tries you stay better (worst case {worst / 100:+.1f})."
    return f" Their best defence is {br[evals.index(worst)]['reply']}, which keeps it {standing(worst)}."


def shape(board, frm, to):
    """How the piece on `frm` attacks `to`: knight, diagonal (incl. pawns), straight, king."""
    t = board.piece_at(frm).piece_type
    if t == chess.KNIGHT:
        return "knight"
    if t == chess.KING:
        return "king"
    if t == chess.PAWN:
        return "diagonal"
    same_line = chess.square_file(frm) == chess.square_file(to) or chess.square_rank(frm) == chess.square_rank(to)
    return "straight" if same_line else "diagonal"


def punish_shape(e):
    """Shape of their punishing reply after my move, for mistakes where they attack/capture/check."""
    if not e.get("refute") or e["category"] in ("missed-capture", "missed-mate"):
        return None
    b = chess.Board(e["fen"])
    b.push(chess.Move.from_uci(e["played"]))
    r = chess.Move.from_uci(e["refute"][0])
    if b.piece_at(r.from_square) is None:
        return None
    if b.is_capture(r) or b.gives_check(r):
        return shape(b, r.from_square, r.to_square)
    # quiet reply (e.g. a fork): shape of the attack it creates on my most valuable piece
    a = b.copy()
    a.push(r)
    them = a.piece_at(r.to_square).color
    targets = [s for s in a.attacks(r.to_square) if a.piece_at(s) and a.piece_at(s).color != them and a.piece_at(s).piece_type != chess.PAWN]
    if not targets:
        return None
    best = max(targets, key=lambda s: VAL[a.piece_at(s).piece_type] or 100)
    return shape(a, r.to_square, best)


def can_take(board, frm, to):
    """An attacker pinned to its own king can only capture along the pin line."""
    color = board.piece_at(frm).color
    return not board.is_pinned(color, frm) or to in board.pin(color, frm)


def danger(board):
    """Side-to-move's pieces that are attacked and undefended or attacked by something cheaper."""
    me, out = board.turn, []
    for sq, pc in board.piece_map().items():
        if pc.color != me or pc.piece_type == chess.KING:
            continue
        att = [a for a in board.attackers(not me, sq) if can_take(board, a, sq)]
        if not att:
            continue
        defended = bool(board.attackers(me, sq))
        cheapest = min(VAL[board.piece_at(a).piece_type] or 100 for a in att)
        if defended and cheapest >= VAL[pc.piece_type]:
            continue
        out.append(dict(sq=chess.square_name(sq), piece=chess.piece_name(pc.piece_type), defended=defended,
                        attackers=[dict(sq=chess.square_name(a), piece=chess.piece_name(board.piece_at(a).piece_type),
                                        shape=shape(board, a, sq)) for a in att]))
    return out
