"""Build coach.html (overview, mistake viewer, practice, puzzles, openings) from data/*.json."""
import chess, collections, json, re, statistics
from explain import why_best, branches, punish_shape, danger
from pathlib import Path

ROOT = Path(__file__).parent
DATA = ROOT / "data"
RAPID = "900+10"
BLOCK = 20

# (san, note) pairs; a note starting with "!bad " draws the move as a red arrow.
# Groups: "Know these" = plans and traps worth learning; "First reply only" = just the first move or two.
KNOW, FIRST = "Know these", "First reply only"
OPENINGS = [
    (KNOW, "Italian: your standard setup", "white",
     "Learn this as a plan, not exact moves: Bc4, c3, d3, castle, Re1, h3, then Nbd2-f1-g3. It works against almost anything.",
     [("e4", "Grab the centre."), ("e5", ""), ("Nf3", "Develop and attack e5."), ("Nc6", "Defends e5."),
      ("Bc4", "The Italian: the bishop aims at f7, Black's weakest square."), ("Bc5", ""),
      ("c3", "Prepares d4 later, keeps ...Nd4 out, and gives the bishop a retreat to b3."), ("Nf6", "Attacks e4."),
      ("d3", "Calmly protects e4."), ("d6", ""), ("O-O", "Castle early: king safe, rook joins."), ("O-O", ""),
      ("Re1", "Rook behind the e-pawn. Frees f1 for the knight."), ("a6", ""),
      ("h3", "Stops ...Bg4 (the pin) and ...Ng4, and gives your king an escape square on h2."), ("Ba7", ""),
      ("Nbd2", "The knight goes the long way round: d2, f1, g3."), ("Be6", ""), ("Nf1", ""), ("h6", ""),
      ("Ng3", "Plan complete. Later: d4 in the centre or Nf5 on the kingside.")]),
    (KNOW, "Italian vs 3...Nf6 (Two Knights)", "white",
     "Black counter-attacks e4. Same plan: defend with d3 and carry on.",
     [("e4", ""), ("e5", ""), ("Nf3", ""), ("Nc6", ""), ("Bc4", ""), ("Nf6", "Attacks your e4 pawn."),
      ("d3", "Simplest: defend e4. Leave 4.Ng5 until you know the theory."), ("Be7", ""),
      ("O-O", ""), ("O-O", ""), ("Re1", ""), ("d6", ""), ("c3", ""), ("h6", ""),
      ("h3", "Same plan as always: c3, d3, O-O, Re1, h3, then Nbd2-f1-g3.")]),
    (KNOW, "Trap: handling the ...Bg4 pin", "white",
     "A knight pinned to the queen must not move. Ask the bishop with h3 instead.",
     [("e4", ""), ("e5", ""), ("Nf3", ""), ("d6", ""), ("Bc4", ""),
      ("Bg4", "The pin: if your f3 knight moves, the bishop takes your queen on d1."),
      ("h3", "Ask the bishop. Don't move the knight."),
      ("Bxf3", "If it takes..."), ("Qxf3", "...recapture with the queen. Now your queen also eyes f7."),
      ("Nf6", ""), ("d3", "Solid, and you have two bishops vs bishop + knight.")]),
    (KNOW, "The pin trap you fell into", "white",
     "This happened in your games. Watch what happens when the pinned knight moves.",
     [("e4", ""), ("e5", ""), ("Nf3", ""), ("d6", ""), ("Nc3", ""),
      ("Bg4", "Pin: the bishop looks through the knight at your queen."),
      ("Ng5", "!bad The knight jumps away, attacking f7, but it was shielding the queen..."),
      ("Bxd1", "...and the queen falls. Lesson: before moving a piece, check what is behind it.")]),
    (KNOW, "Two Knights Defence vs 4.Ng5", "black",
     "Against the Italian, play 3...Nf6 and counter-attack e4. If they attack f7 with 4.Ng5, know these moves.",
     [("e4", ""), ("e5", ""), ("Nf3", ""), ("Nc6", ""), ("Bc4", ""), ("Nf6", "Two Knights: hit e4."),
      ("Ng5", "White attacks f7 twice."), ("d5", "Block the bishop."), ("exd5", ""),
      ("Na5", "The key move: NOT 5...Nxd5 (the Fried Liver). Move the knight and hit the bishop."),
      ("Bb5+", ""), ("c6", ""), ("dxc6", ""),
      ("bxc6", "You're a pawn down, but you'll develop fast and kick White's pieces around (...h6, ...e4). Good for Black.")]),
    (KNOW, "The Fried Liver: what to avoid", "black",
     "You played 5...Nxd5 and lost. Here's why it's dangerous.",
     [("e4", ""), ("e5", ""), ("Nf3", ""), ("Nc6", ""), ("Bc4", ""), ("Nf6", ""), ("Ng5", ""), ("d5", ""),
      ("exd5", ""), ("Nxd5", "!bad Natural, but this is the move to avoid."),
      ("Nxf7", "White sacrifices the knight..."), ("Kxf7", ""),
      ("Qf3+", "...forking your king and the d5 knight."), ("Ke6", "The king must defend the knight."),
      ("Nc3", "Your king is stuck in the middle of the board, with White pieces all coming at it.")]),
    (KNOW, "Two Knights vs the quiet 4.d3", "black",
     "Most beginners play 4.d3. Mirror your White setup.",
     [("e4", ""), ("e5", ""), ("Nf3", ""), ("Nc6", ""), ("Bc4", ""), ("Nf6", ""), ("d3", ""),
      ("Be7", "Solid development."), ("O-O", ""), ("O-O", "Castle early."), ("Re1", ""), ("d6", ""),
      ("c3", ""), ("Na5", "Chase the bishop: it is White's best piece."), ("Bb5", ""), ("a6", ""),
      ("Ba4", ""), ("b5", ""), ("Bc2", "")]),
    (KNOW, "Trap: against an early queen (2.Qh5)", "black",
     "Beginner opponents love this. Defend f7 first, then chase the queen.",
     [("e4", ""), ("e5", ""), ("Qh5", "Attacks e5 and f7."), ("Nc6", "Defend e5 first."),
      ("Bc4", "Threatens Qxf7#."), ("g6", "Block the queen's line to f7. Never ...Nf6?? here: Qxf7# is mate."),
      ("Qf3", "Still aims at f7."), ("Nf6", "Now f7 is defended AND you develop with tempo."),
      ("Ne2", ""), ("Bg7", "Comfortable. White's queen will keep getting kicked.")]),
    (KNOW, "Against 1.d4: simple setup", "black",
     "Pick one setup and play it every time: ...d5, ...Nf6, ...e6, ...Bd6, castle.",
     [("d4", ""), ("d5", "Claim the centre."), ("Nf3", ""), ("Nf6", ""), ("Bf4", "The London: White's most common setup."),
      ("e6", ""), ("e3", ""), ("Bd6", "Challenge White's bishop."), ("Bd3", ""), ("O-O", ""), ("O-O", ""),
      ("c5", "Hit the centre from the side.")]),
    (FIRST, "vs the Petrov (2...Nf6)", "white",
     "Your second most common reply (7 games). Just know the first move, and the trap if they take back.",
     [("e4", ""), ("e5", ""), ("Nf3", ""), ("Nf6", "The Petrov: attacks e4."),
      ("Nxe5", "Take the pawn."),
      ("d6", "Correct. If 3...Nxe4? then 4.Qe2! hits the pinned knight: after 4...Qe7 5.Qxe4 you end up a pawn up, and if 4...Nf6?? then 5.Nc6+ uncovers check and wins their queen."),
      ("Nf3", "Retreat - the knight was attacked. Then d4, Bd3 and castle.")]),
    (FIRST, "vs the Philidor (2...d6)", "white",
     "Black plays passively (5 games). Take the centre, then develop as normal.",
     [("e4", ""), ("e5", ""), ("Nf3", ""), ("d6", "Solid but passive."),
      ("d4", "Strike the centre. Then Nc3, Bc4 or Be2, and castle.")]),
    (FIRST, "vs 2...f6 (Damiano)", "white",
     "A bad move you've faced 5 times. It weakens Black's king, so punish it.",
     [("e4", ""), ("e5", ""), ("Nf3", ""), ("f6", "Defends e5 but opens the e8-h5 diagonal to Black's king."),
      ("Nxe5", "Take it anyway! If 3...fxe5?? 4.Qh5+ wins (Stockfish: +5). Their best is 3...Qe7 4.Nf3 Qxe4+ 5.Be2, and you're well ahead in development.")]),
    (FIRST, "vs the Scandinavian (1...d5)", "white",
     "Your third most common reply (9 games). Take, then develop with tempo.",
     [("e4", ""), ("d5", "Attacks e4 straight away."), ("exd5", "Take it."),
      ("Qxd5", "Their queen comes out early..."),
      ("Nc3", "...so develop while attacking it. Then d4, Nf3, Bc4 and castle. (If 2...Nf6 instead, play d4 and Nf3.)")]),
]


FRIED_LIVER = "e4 e5 Nf3 Nc6 Bc4 Nf6 Ng5 d5 exd5 Nxd5".split()


def queen_pin(g, e):
    return e["category"] == "moved-pinned" and e["piece"] == "N" and "shielding your queen" in e["why"]


def scholars_mate(g, e):
    return e["category"] == "allowed-mate" and e["refute_san"].split()[1:2] == ["Qxf7#"]


# opening line name -> test for "this happened in one of my games" (an error), or a move-prefix (a whole game)
SEEN_IN = {
    "Trap: handling the ...Bg4 pin": queen_pin,
    "The pin trap you fell into": queen_pin,
    "The Fried Liver: what to avoid": FRIED_LIVER,
    "Trap: against an early queen (2.Qh5)": scholars_mate,
}


def seen_in(name, games):
    """[{ref, date, text}] for games where this line's pattern happened to me, oldest first."""
    test, out = SEEN_IN.get(name), []
    if test is None:
        return out
    for n, g in enumerate(games, 1):
        if callable(test):
            for e in g["errors"]:
                if test(g, e):
                    ref = f'G{n}-{e["move_no"]}{"w" if e["ply"] % 2 == 0 else "b"}'
                    out.append(dict(ref=ref, date=g["date"], text=f'{e["played_san"]} vs {g["opponent"]}'))
        elif [p["san"] for p in g["plies"][:len(test)]] == test:
            out.append(dict(ref=f"G{n}", date=g["date"], text=f'vs {g["opponent"]}', link=g["link"]))
    return out


def build_openings(games=()):
    out = []
    for group, name, side, intro, moves in OPENINGS:
        b = chess.Board()
        ms = []
        for san, note in moves:
            mv = b.parse_san(san)  # raises if the line is illegal
            label = (f"{b.fullmove_number}. " if b.turn else f"{b.fullmove_number}... ") + san
            bad = note.startswith("!bad ")
            ms.append(dict(san=san, uci=mv.uci(), label=label, note=note[5:] if bad else note, bad=bad))
            b.push(mv)
        out.append(dict(group=group, name=name, side=side, intro=intro, moves=ms, seen=seen_in(name, games)))
    return out


def pieces_css():
    css = (ROOT / "assets" / "cburnett.css").read_text()
    out = []
    for kind, color, uri in re.findall(r"piece\.(\w+)\.(\w+)\s*\{\s*background-image:\s*url\('([^']+)'\)", css):
        code = ("w" if color == "white" else "b") + {"pawn": "P", "knight": "N", "bishop": "B", "rook": "R", "queen": "Q", "king": "K"}[kind]
        out.append(f".board .pc.{code}{{background-image:url('{uri}')}}")
    assert len(out) == 12, "piece set incomplete"
    return "\n".join(out)


def overview(games):
    res = collections.Counter(g["result"] for g in games)
    rapid = [g for g in games if g["time_control"] == RAPID]
    blunders = [e for g in games for e in g["errors"] if e["severity"] == "blunder"]
    opp, unpunished = 0, 0
    for g in games:
        ps = g["plies"]
        for i, p in enumerate(ps[:-1]):
            if not p["mine"] and p["drop"] >= 30:
                opp += 1
                if ps[i + 1]["drop"] >= 15:
                    unpunished += 1
    per_game = [sum(e["severity"] == "blunder" for e in g["errors"]) for g in games]
    firsts = [next((e["move_no"] for e in g["errors"] if e["severity"] == "blunder"), None) for g in games]
    firsts = [f for f in firsts if f]
    blocks = []
    for i in range(0, len(games), BLOCK):
        chunk = per_game[i:i + BLOCK]
        if len(chunk) >= BLOCK // 2:
            blocks.append([f"{i + 1}-{i + len(chunk)}", round(sum(chunk) / len(chunk), 1)])

    def openings(color):
        c, w = collections.Counter(), collections.Counter()
        for g in games:
            if g["color"] != color or len(g["plies"]) < 4:
                continue
            b = chess.Board()
            line = b.variation_san([chess.Move.from_uci(p["uci"]) for p in g["plies"][:4]])
            c[line] += 1
            w[line] += g["result"] == "win"
        return [[k, n, w[k]] for k, n in c.most_common(6)]

    phases = collections.Counter(e["phase"] for e in blunders)
    return dict(
        games=len(games), w=res["win"], l=res["loss"], d=res["draw"],
        span=f'{games[0]["date"].replace(".", "-")} to {games[-1]["date"].replace(".", "-")}',
        rating_start=rapid[0]["my_elo"] if rapid else "-", rating_now=rapid[-1]["my_elo"] if rapid else "-",
        rating_max=max(g["my_elo"] for g in rapid) if rapid else "-",
        rating_series=[[g["date"], g["my_elo"]] for g in rapid],
        bpg_first=round(statistics.mean(per_game[:BLOCK]), 1), bpg_recent=round(statistics.mean(per_game[-BLOCK:]), 1),
        bpg_blocks=blocks, block=BLOCK,
        opp_blunders=opp, unpunished=unpunished, unpunished_pct=round(100 * unpunished / max(opp, 1)),
        categories=collections.Counter(e["category"] for e in blunders).most_common(),
        trend=trend(games),
        phases=[[k, phases[k]] for k in ("opening", "middlegame", "endgame")],
        first_blunder_median=statistics.median(firsts) if firsts else "-",
        open_white=openings("white"), open_black=openings("black"))


def trend(games):
    """Blunders per 10 games of each type: first third of my games vs the most recent third."""
    k = len(games) // 3
    early, recent = games[:k], games[-k:]
    rate = lambda gs, c: round(10 * sum(e["category"] == c and e["severity"] == "blunder" for g in gs for e in g["errors"]) / len(gs), 1)
    cats = {e["category"] for g in games for e in g["errors"]}
    return dict(early=[early[0]["date"], early[-1]["date"]], recent=[recent[0]["date"], recent[-1]["date"]],
                rates={c: [rate(early, c), rate(recent, c)] for c in cats})


def main():
    games = json.loads((DATA / "analysis.json").read_text())
    errors = []
    deep = json.loads((DATA / "deep.json").read_text()) if (DATA / "deep.json").exists() else {}
    # G<n> = game number in chronological order; stable because new games are appended at the end
    for n, g in enumerate(games, 1):
        for e in g["errors"]:
            prev = g["plies"][e["ply"] - 1] if e["ply"] > 0 else None
            ref = f'G{n}-{e["move_no"]}{"w" if e["ply"] % 2 == 0 else "b"}'
            d = deep.get(f'{g["id"]}#{e["ply"]}', {})
            e = dict(e, best_why=why_best(e, d) if d else "", branches=branches(e, d) if d else [],
                     best_deep=d.get("replies_after") or e["best"], shape=punish_shape(e))
            errors.append(dict(e, ref=ref, game_no=n, game_id=g["id"], link=g["link"], date=g["date"], color=g["color"],
                               opponent=g["opponent"], opp_elo=g["opp_elo"], result=g["result"],
                               prev=prev["uci"] if prev else None, prev_san=prev["san"] if prev else None))
    ov = overview(games)
    # how many of my moves fall in each phase, for the "when they happen" rates
    moves_by_phase = collections.Counter()
    for g in games:
        b = chess.Board(g["start_fen"])
        for i, p in enumerate(g["plies"]):
            if p["mine"]:
                nonpawn = sum({2: 3, 3: 3, 4: 5, 5: 9}.get(pc.piece_type, 0) for pc in b.piece_map().values())
                moves_by_phase["opening" if i < 20 else ("endgame" if nonpawn <= 26 else "middlegame")] += 1
            b.push(chess.Move.from_uci(p["uci"]))
    ov["phases"] = [[k, n, moves_by_phase[k]] for k, n in ov["phases"]]
    # Spot the danger: positions before my mistakes where something of mine was already loose
    spot, seen = [], set()
    for e in errors:
        if e["fen"] in seen:
            continue
        dl = danger(chess.Board(e["fen"]))
        if dl:
            seen.add(e["fen"])
            shapes = sorted({a["shape"] for x in dl for a in x["attackers"]})
            spot.append(dict(ref=e["ref"], fen=e["fen"], color=e["color"], date=e["date"], opponent=e["opponent"],
                             move_no=e["move_no"], prev=e["prev"], prev_san=e["prev_san"], danger=dl, shapes=shapes))
    payload = dict(overview=ov, errors=errors, spot=spot, puzzles=json.loads((DATA / "puzzles.json").read_text()),
                   openings=build_openings(games))
    html = (ROOT / "coach_template.html").read_text()
    html = html.replace("/*PIECES*/", pieces_css()).replace("/*DATA*/null", json.dumps(payload).replace("</", "<\\/"))
    (ROOT / "coach.html").write_text(html)
    print(f"coach.html: {len(games)} games, {len(errors)} errors, "
          f"{sum(len(t['puzzles']) for t in payload['puzzles'].values())} puzzles, {len(payload['openings'])} opening lines")


if __name__ == "__main__":
    main()
