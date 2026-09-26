#!/usr/bin/env python3
#
# chess-verdict -- a Stockfish verdict on a chess position
# Copyright (C) 2026  Pavel Kurochka <https://github.com/PavelKurochka>
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option)
# any later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public License for
# more details.
#
# You should have received a copy of the GNU General Public License along
# with this program.  If not, see <https://www.gnu.org/licenses/>.
"""Analyse a chess position: legality, best move, and the opponent's defences.

Speed rests on three decisions:

  * the search stops on convergence, not on the clock. The engine reports after
    every iteration; once the best move stops changing and a working depth has
    been reached, calculating further refines the number, not the answer. The
    time limit stays as a backstop rather than the normal exit;
  * defences come from one MultiPV search in the position after the best move,
    not from a separate search per reply. The evaluation after the best move
    already assumes the defender's best answer, so enumerating every reply adds
    nothing to the verdict -- it is worth doing only where the replies are few
    and the list itself is the proof;
  * the whole analysis is one engine process with one shared hash table and one
    command: running the script twice recomputes everything from cold.

Move notation is international (K Q R B N) regardless of the language the
answer itself is written in.
"""

import time

_STARTED = time.time()          # before the heavy imports: they count too

import argparse
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile

try:
    import chess
    import chess.engine
    import chess.svg
except ImportError as exc:
    # A missing python-chess used to end in a bare ModuleNotFoundError. The
    # setup line can fail for reasons that have nothing to do with the network
    # -- on images whose Debian setuptools rejects legacy builds it dies with
    # `AttributeError: install_layout` -- so the message names the fix.
    sys.exit("python-chess is not installed ({exc}). Install it with:\n"
             "  pip install chess --break-system-packages --use-pep517 -q\n"
             "--use-pep517 is not optional decoration: python-chess 1.11 ships "
             "as source only, and without it some images fail to build it. "
             "Nothing was analysed.".format(exc=exc))

ENGINE_PATH = os.environ.get("STOCKFISH", "/usr/games/stockfish")
GAME_KEY = "chess-verdict"  # shared key: no ucinewgame, the hash survives

#: Build identity. Must match `metadata.version` in SKILL.md's frontmatter and
#: the top entry of CHANGELOG.md. A fixed build that never reached the installed
#: copy is how this skill lost a mate-detection fix once already, with nothing in
#: the output to show for it.
VERSION = "2.29.1"


def banner(parser, args, tool, subject=None, pinned=(), skip=(),
           effective=None):
    """One line of build identity and the settings this run actually used.

    Printed before anything else, so the transcript says which build answered
    and with what. The web interface labels an activated skill with its name
    alone -- no version, no arguments, and one identical line per file the skill
    opens. A run with an explicit `--mate-probe 11` looked exactly like a run
    without it, and an installed copy two releases behind looked exactly like a
    current one. Neither is recoverable from the label; this is the line that
    carries it.

    Only settings that differ from their defaults are listed. A dump of every
    flag would bury the one or two that were actually chosen, which is the whole
    point of printing them. Names in `pinned` are listed either way, for
    settings that decide the answer and must never be inferred from silence;
    `skip` drops positional arguments, whose values belong in `subject`.

    `effective` overrides what counts as a default, for flags whose declared
    default is a sentinel resolved after parsing. `--mate-probe` defaults to
    None so that passing it can be told from not passing it, and is then set to
    5; compared against None, an untouched run advertised `--mate-probe 5` as a
    choice the user had made. A line that invents settings is worse than no
    line, since it reads exactly like one that reports them.
    """
    values, shown, done = vars(args), [], set(skip)
    for name in list(pinned) + sorted(values):
        if name in done or name not in values:
            continue
        done.add(name)
        value = values[name]
        default = effective.get(name, parser.get_default(name)) if effective \
            else parser.get_default(name)
        if name not in pinned and value == default:
            continue
        flag = "--" + name.replace("_", "-")
        if value is True:
            shown.append(flag)
        else:
            # `--probe-step 4` comes back as 4.0 through argparse's float type,
            # and a line meant to be pasted back into a command should read as
            # what was typed.
            shown.append(f"{flag} {value:g}" if isinstance(value, float)
                         else f"{flag} {value}")
    head = f"chess-verdict {VERSION} | {tool}"
    if subject:
        head += f" {subject}"
    return f"{head}  {' '.join(shown)}" if shown else f"{head}  (defaults)"


# --- output strings ----------------------------------------------------------

TEXT = {
    "mate_given": "mate delivered",
    "mate_taken": "mate received",
    "mate_in": "mate in {n}",
    "mate_against": "mate in {n} against",
    "white": "White", "black": "Black",
    "illegal": "ILLEGAL POSITION: {why}. No analysis follows -- there is "
               "nothing for the engine to answer. If this is the position on "
               "the board, it is a composed or generated one; if it is not, "
               "the reading is wrong.",
    "unreachable": "The position is unreachable from the starting position "
                   "({why}), but play from here is ordinary chess, so the "
                   "analysis below stands.",
    "over": "The game is already over: {result}",
    "line_applied": "Line applied to the FEN given: {san}\nPosition after the "
                    "line: {fen}\n(this position was reached by playing the "
                    "moves out, not by typing a placement)",
    "line_bad_move": "STOPPED AT MOVE {n} OF THE LINE ({token!r}): {why}.\n"
                     "  Position at that point: {fen}\n"
                     "  {side} to move, {count} legal {word}: {legal}\n"
                     "Nothing was analysed. Fix the line -- do not work around "
                     "this by typing the placement you expected: a placement "
                     "reached by a move that does not exist is usually still a "
                     "legal FEN, and the analysis of it is an answer to a "
                     "different position.",
    "line_empty": "--line was given but contains no moves once move numbers "
                  "and result markers are removed.",
    "line_unparsable": "not a move this program can read, in SAN or in UCI",
    "line_illegal": "not legal here",
    "line_ambiguous": "ambiguous -- more than one move is written this way; "
                      "give it in UCI instead",
    "line_over": "STOPPED AT MOVE {n} OF THE LINE: the game ended before it "
                 "({result}) at {fen}. Nothing was analysed.",
    "legal": "Position is legal. {side} to move. Legal moves: {n}",
    "playable": "{side} to move. Legal moves: {n}",
    "clock": "Halfmove clock: {hm} of 100. {note}",
    "clock_fresh": "The fifty-move counter is assumed to have just reset -- if "
                   "this position came from a game, check the real count.",
    "clock_late": "Fewer than {plies} plies remain before a draw by the "
                  "fifty-move rule.",
    "tb_link": "Seven pieces or fewer -- the exact answer is a tablebase "
               "query, not a search. For the user: the Lichess link above "
               "shows it in the analysis board's explorer panel. The same "
               "data as JSON: {url}",
    "st_fifty": "50-move probe at halfmove clock {hm}: {outcome}",
    "fifty_held": "advantage holds ({score})",
    "fifty_collapsed": "collapses to {score}",
    "fifty_note_held": "50-move probe: with the halfmove clock at {hm} the "
                       "evaluation is still {score}, so the advantage can be "
                       "converted with captures or pawn moves and the number "
                       "above means what it says.",
    "fifty_note_collapsed": "50-move probe: with the halfmove clock at {hm} "
                            "this position evaluates {score} instead of "
                            "{score0}. The advantage needs more than {plies} "
                            "plies without a capture or a pawn move, so it is "
                            "either a fortress, or a win long enough that the "
                            "fifty-move rule decides it. This is a reason to "
                            "look further -- a won rook ending fails the same "
                            "test -- not a verdict of draw. --playout 60 "
                            "separates the two.",
    "fifty_note_collapsed_forced": "50-move probe: with the halfmove clock at "
                                   "{hm} this position evaluates {score} "
                                   "instead of {score0}. This does NOT weigh "
                                   "against the verdict above: every reply was "
                                   "enumerated and every one of them is mated, "
                                   "which is a proof, while the probe is a "
                                   "ten-ply search that has only failed to "
                                   "show progress. Read the two together as "
                                   "the second case the probe names -- a win "
                                   "long enough that the fifty-move rule could "
                                   "decide it. --playout 60 will show where "
                                   "the clock first resets.",
    "st_playout": "playout of {plies} plies, {step:.1f} s a move",
    "playout_header": "\nPlayout ({plies} plies, {step:.1f} s a move, both "
                      "sides by the same engine):",
    "playout_reset": "  the halfmove clock first reset at ply {ply} ({san}) -- "
                     "progress is real, the position is not a fortress.",
    "playout_no_reset": "  {plies} plies with no capture and no pawn move; the "
                        "clock reached {hm}. Nothing was converted, which is "
                        "what a fortress looks like.",
    "playout_cut": "  NOTE: the playout stopped at {plies} of the {asked} "
                   "plies asked for, because the budget ran out -- raise "
                   "--budget for the full run before drawing a conclusion.",
    "playout_over": "  the game ended after {ply} plies: {result}.",
    "playout_claimable": "  after {ply} plies a draw can be claimed -- "
                         "repetition or the fifty-move rule -- which is how a "
                         "fortress ends when nobody deviates.",
    "playout_evals": "  evaluation at the start {first}, at the end {last}.",
    "playout_limit": "  NOTE: the run reached its {asked}-ply limit with no reset "
                     "and no repetition. A win whose first capture or pawn "
                     "move comes later looks exactly the same, and the "
                     "fifty-move rule allows 100 plies -- rerun with "
                     "--playout 100 before calling it a fortress.",
    "playout_limit_full": "  The run used all {asked} plies with no reset: from "
                          "a fresh clock the fifty-move rule would have ended "
                          "the game by now, whatever the evaluation says.",
    "playout_error": "  NOTE: the playout stopped at {plies} of the {asked} "
                     "plies because the engine returned no move -- nothing "
                     "can be concluded from it.",
    "ladder_off": "NOTE: the mate ladder is off (--fast), so a composed mate "
                  "can come back as a plain evaluation.",
    "fast_conflict": "--mate-probe cannot be combined with --fast: --fast "
                     "switches the ladder off. Drop one of the two.",
    "quick_conflict": "{flags} cannot be combined with {mode}: {mode} switches "
                      "the defence analysis off altogether, so those settings "
                      "would decide nothing. Drop one side.",
    "warn_flip": "WARNING: White's pawns sit on average higher than Black's -- "
                 "the diagram was probably read from the wrong side and the "
                 "whole placement is rotated 180 degrees. Check the file and "
                 "rank labels.",
    "board_link": "Board to verify: ",
    "board_ascii": "\nPosition as read (shown from {side}'s side) -- "
                   "compare against the diagram before trusting the answer:",
    "board_counts": "Material: White {w} -- Black {b}",
    "board_svg": "\nPosition as read, rendered from {side}'s side -- open this "
                 "diagram, compare it against the original, and show it to the "
                 "user before trusting the answer:\n  {path}",
    "board_svg_failed": "WARNING: could not write the diagram to {path} ({err}) "
                        "-- falling back to the letter grid below; the analysis "
                        "is unaffected",
    "st_render": "rendering the diagram ({fmt} via {tool})",
    "render_builtin": "chess.svg",
    "png_unavailable": "NOTE: --diagram png was asked for but no rasteriser is "
                       "installed (rsvg-convert or cairosvg) -- writing an SVG "
                       "instead",
    "st_import": "importing python-chess",
    "st_legal": "legality and game-over check",
    "st_engine": "engine startup: {threads} thread(s), hash {mb} MB",
    "st_main": "main search to depth {depth}, MultiPV {multipv}",
    "st_probe": "mate ladder: {rungs} rung(s) of {step:.1f} s, {outcome}",
    "probe_found": "mate in {n} found",
    "probe_none": "no mate up to {rungs}",
    "probe_cut": "cut short: absence proved only up to {done} of {rungs} rungs",
    "ladder_cut": "NOTE: the mate ladder stopped after proving there is no mate "
                  "in {done}; rungs {first} to {rungs} were never asked, "
                  "because the budget ran out. Nothing below rules a mate out "
                  "-- raise --budget, or lower --mate-probe so the ladder fits "
                  "inside it.",
    "probe_kept": "The mate ladder proved a mate in {n}; the main search did not "
                  "reach it, so the ladder's line is reported instead.",
    "st_reprobe": "shorter-mate probe from {m}, {step:.1f} s a rung: {outcome}",
    "reprobe_found": "shorter mate in {n} found",
    "reprobe_none": "nothing shorter than {m}",
    "reprobe_cut": "cut short: nothing proved about distances below {m}",
    "reprobe_cut_note": "NOTE: the shorter-mate probe never got to ask for a "
                        "mate in {n} -- the budget ran out. The mate in {m} "
                        "below is proved; whether a shorter one exists was not "
                        "asked, so do not report {m} as the fastest win.",
    "reprobe_note": "A mate in {m} was found first. Because a mate exists, the "
                    "shorter distances were re-asked with {step:.1f} s a rung "
                    "instead of {step0:.1f} s, and that proved a mate in {n} -- "
                    "which is what is reported below.",
    "st_full": "enumerating all replies: {n} {word}, of which searched {k}",
    "st_defences": "defences: {k} lines out of {n}, depth {depth}",
    "st_print": "printing the result",
    "st_other": "other: board handling, printing",
    "bad_fen": "NOT A FEN THIS PROGRAM CAN READ: {why}.\nWhat was given: {fen!r}\n"
               "A FEN is six fields: placement, side to move, castling, en "
               "passant, halfmove clock, fullmove number -- for example "
               "'8/8/8/8/8/2k5/8/KBN5 w - - 0 1'. Each of the eight ranks must "
               "add up to eight squares. Nothing was analysed: re-read the "
               "position rather than patching the field that failed, since a "
               "miscount on one rank is evidence the same habit ran on the "
               "others.",
    "fen_no_turn": "THE FEN DOES NOT SAY WHOSE MOVE IT IS: {fen!r}. Nothing "
                   "was analysed. A placement on its own parses -- python-chess "
                   "fills the field in as 'w' -- and everything after that is a "
                   "confident answer to a question nobody asked: a tactic "
                   "solved for the wrong side is the opposite answer, not a "
                   "near miss. Put 'w' or 'b' after the placement.",
    "fen_no_castling": "The FEN stopped after the side to move, so the "
                       "castling field was filled in as '-'. That is an "
                       "assumption, not a reading: where castling is the "
                       "solution it is the whole answer.",
    "no_engine": "STOCKFISH NOT FOUND at {path} ({why}). Install it with "
                 "`apt-get install -y stockfish`, or point the STOCKFISH "
                 "environment variable at the binary. Nothing was analysed; "
                 "the reading above, if any, still stands.",
    "no_line": "The engine returned no line -- raise --time",
    "best": "\nBest move: {san}   evaluation {score}   ({where}, {dt:.1f} s)",
    "second": "Second best: {san}   {score}   ({where}){tail}",
    "depth_at": "depth {depth}",
    "depth_proved": "proved by a mate-only search",
    "main_line": "Main line:",
    "gap_only_mate": "   only this move mates",
    "gap_second_mates": "   the second move mates too",
    "gap_both_lose": "   both moves lose to mate",
    "gap_decisive": "   decisive gap: the second move loses to mate",
    "gap_order": "   the two lines came back out of order (a mate against the "
                 "first, none against the second) -- check both with --line "
                 "before calling either the best move",
    "gap_lead": "   lead {diff:+.2f} (in chances {dw:+.2f})",
    "gap_noise": "   difference {diff:+.2f} (in chances {dw:+.2f}) -- "
                 "within search noise, the moves are equivalent",
    "scan_off": "\n(defence analysis disabled)",
    "no_replies": "\nThe opponent has no moves -- the game is over.",
    "all_replies": "\nAll opponent replies ({n}):",
    "v_incomplete": "Verdict: completeness NOT proved -- {n} replies were left "
                    "unscored, the budget ran out (--budget).",
    "v_holds": "Verdict: the win is not forced; these replies hold: {moves}.",
    "v_branch_mates": "Verdict: {n} of the {total} replies are mated while the "
                      "main line is reported as an evaluation, so the number "
                      "above understates the position. Whether the win is "
                      "forced is NOT established either way -- these replies "
                      "were not resolved: {moves}.",
    "v_tail_mates": "NOTE: most of the defences shown are mated while the main "
                    "line is reported as an evaluation. The number understates "
                    "the position; do not read it as the verdict.",
    "v_forced": "Verdict: the win is forced, every reply loses ({n}).",
    "v_decisive": "Verdict: every reply is decisive by evaluation ({n}), the "
                  "weakest at {floor} -- an evaluation, not a proof "
                  "(centipawn scores: {k} of {n}). A fortress scores "
                  "exactly like that; only a mate or the end of the game "
                  "proves a win. If the 50-move probe below collapses, "
                  "--playout 60 decides.",
    "v_forced_mates": "NOTE: {n} of the {total} replies are mated while the "
                      "toughest ({san}) is scored in centipawns, so the "
                      "DISTANCE is not established -- the win is very likely a "
                      "mate. Re-ask with --mate-probe N --probe-step 3.",
    "def_header": "\nBest defences ({k} of {n}, depth {depth}, {dt:.1f} s) "
                  "-- evaluations from the attacker's point of view:",
    "v_survives": "the advantage survives the best defence",
    "v_not_decisive": "the advantage is not decisive",
    "v_tail": "Verdict: {verdict}. Toughest defence -- {san} ({score}). "
              "The remaining {n} {word} were rated no higher by the engine; "
              "for the full list use --scan full.",
    "r_draw": "draw", "r_mate": "mate", "r_mate_att": "mate against attacker",
    "r_unscored": "not scored",
    "t_header": "\nTime by stage:",
    "t_total": "TOTAL",
    "t_budget": "of a {budget:.0f} s budget",
    "t_short": "\nSearch time: {dt:.1f} s of a {budget:.0f} s budget",
    "budget_warn": "WARNING: the budget is exhausted and part of the analysis "
                   "was cut short -- raise --budget if needed.",
    "unit": "s",
}


def t(key, **kw):
    s = TEXT[key]
    return s.format(**kw) if kw else s


def word_replies(n):
    return "reply" if n == 1 else "replies"


def depth_note(line):
    """What the figure in the brackets after an evaluation actually is."""
    return t("depth_proved") if line.proved else t("depth_at", depth=line.depth)


# --- container resources -----------------------------------------------------

def cpu_count():
    """Cores actually available, not the host's cores."""
    try:
        return max(1, len(os.sched_getaffinity(0)))
    except AttributeError:
        return os.cpu_count() or 1


def hash_size():
    """Engine hash size.

    The engine zeroes the table when a search starts, and on a gigabyte that
    costs about three seconds -- more than the useful calculation. Ten seconds
    on one core visit some ten million positions, for which 64-128 MB is ample;
    taking a share of free memory makes no sense here.
    """
    per_core = 64 * cpu_count()
    try:
        with open("/proc/meminfo") as fh:
            for line in fh:
                if line.startswith("MemAvailable"):
                    free = int(line.split()[1]) // 1024
                    return max(32, min(256, per_core, free // 4))
    except OSError:
        pass
    return min(256, per_core)


# --- evaluations -------------------------------------------------------------

def fmt(score):
    """Evaluation from the point of view of the side being analysed.

    The extremes differ in substance: MateGiven means mate has been delivered,
    Mate(0) that mate has been received. Both return 0 from mate(), so a single
    comparison with zero is not enough.
    """
    if score is chess.engine.MateGiven:
        return t("mate_given")
    if score.is_mate():
        n = score.mate()
        if n == 0:
            return t("mate_taken")
        return t("mate_in", n=n) if n > 0 else t("mate_against", n=abs(n))
    return f"{score.score() / 100:+.2f}"


#: Steepness of the centipawn-to-chances conversion. The constant comes from
#: Lichess's puzzle generator (lichess-puzzler, generator/util.py), where it is
#: calibrated on game outcomes.
CHANCES_K = -0.00368208

#: How far ahead of the second move the best move must be, in chances, before
#: the difference is worth calling a lead. At equality that is about 27
#: centipawns; at a seven-pawn advantage, about 90.
GAP_CHANCES = 0.05


def chances(score):
    """Evaluation converted to winning chances, from -1 to 1.

    A centipawn difference means nothing on its own: 30 centipawns decide the
    game at equality and sit inside search noise at plus seven. The chances
    scale compresses the extremes and makes the two comparable.
    """
    if score.is_mate():
        return 1.0 if score.mate() > 0 or score is chess.engine.MateGiven else -1.0
    cp = score.score()
    return 0.0 if cp is None else 2 / (1 + math.exp(CHANCES_K * cp)) - 1


def gap_note(best_score, alt_score):
    """Explanation of the gap between the best and the second move.

    Mates are handled separately: in chances a mate and a twenty-pawn advantage
    are the same number, but for a puzzle they are not -- the path to mate is
    usually unique.
    """
    best_mates = best_score.is_mate() and (
        best_score is chess.engine.MateGiven or best_score.mate() > 0)
    alt_mates = alt_score.is_mate() and (
        alt_score is chess.engine.MateGiven or alt_score.mate() > 0)
    if best_mates:
        return t("gap_second_mates") if alt_mates else t("gap_only_mate")
    if best_score.is_mate() and not alt_score.is_mate():
        # The best line is mated and the second is not, so the two came back
        # in the wrong order. Stockfish sorts its lines, so this should not
        # happen; if it does, the centipawn arithmetic below would raise
        # TypeError on a mate score, and the honest output is to say so.
        return t("gap_order")
    if alt_score.is_mate():
        # here the mate is on the defender's side: the best move has none
        # (or the branch above would have fired) and the second move allows it
        if best_score.is_mate():
            return t("gap_both_lose")
        return t("gap_decisive")
    diff = (best_score.score() - alt_score.score()) / 100
    dw = chances(best_score) - chances(alt_score)
    if dw >= GAP_CHANCES:
        return t("gap_lead", diff=diff, dw=dw)
    # at this depth the gap is inside search noise: the ordering of these two
    # moves is not stable and neither can be called the only solution
    return t("gap_noise", diff=diff, dw=dw)


def decisive(score, win_cp):
    """The advantage is large enough that deeper calculation is pointless."""
    if score is chess.engine.MateGiven:
        return True
    if score.is_mate():
        return score.mate() > 0        # Mate(0) is mate received, not an advantage
    return score.score() >= win_cp


def winning_mates(scores):
    """The replies among `scores` that are mated by the side to move."""
    return [s for s in scores
            if s is chess.engine.MateGiven
            or (s.is_mate() and s.mate() > 0)]


def headline_understates(best_score, n_mated, n_other):
    """Is the headline evaluation weaker than what the reply list already shows?

    A reply that is mated proves the position mates at least down that branch.
    When the headline is still a centipawn score, the number is not the verdict
    -- it is an unresolved search reported as though it were one.

    The trigger is narrow on purpose. A single losing reply that gets mated is
    ordinary and says nothing about the rest. What is not ordinary is most of
    the replies being mated while the headline stays in centipawns.

    This lives in one place because it did not used to: the full-enumeration
    path and the sampled-defences path each grew their own copy of the rule,
    the two drifted, and a position with eleven mated replies out of twelve
    printed the warning on one path and not on the other.
    """
    return (not best_score.is_mate() and n_mated >= 2 and n_mated > n_other)



def enumeration_verdict(best_score, rows, win):
    """Which verdict lines a full enumeration of replies earns.

    `rows` are ``(san, score, line, note)`` with scores from the attacker's
    point of view. Returns ``[(text_key, fields), ...]``. Pure, so the tests
    call this very function instead of a copy of it.

    What counts as proof changed in 2.27.0. Until then "every reply loses"
    meant every reply scored at `--win` (400 cp) or more, and the line read
    "the win is forced". A centipawn score is an opinion, and a fortress holds
    exactly that opinion: `8/p7/kpP5/qrp1b3/rpP2b2/pP2b3/P7/K7 w` after 1.Kb1,
    a textbook draw, printed "the win is forced, every reply loses (4)" at
    +10.71 -- and SKILL.md told the assistant that this line outranks the
    collapsed 50-move probe and its own reasoning. Now the win is called
    forced only when every reply is mated or ends the game, or when the
    headline itself is a mate; a list that is merely decisive in centipawns
    says so and says it is not a proof.
    """
    unscored = [r for r in rows if r[3] == t("r_unscored")]
    if unscored:
        return [("v_incomplete", dict(n=len(unscored)))]
    holds = [r for r in rows if not decisive(r[1], win)]
    mated = winning_mates([r[1] for r in rows])
    if holds and headline_understates(best_score, len(mated), len(holds)):
        return [("v_branch_mates", dict(
            n=len(mated), total=len(rows),
            moves=", ".join(r[0] for r in holds[:6])))]
    if holds:
        return [("v_holds", dict(moves=", ".join(r[0] for r in holds[:6])))]
    unproved = [r for r in rows if not winning_mates([r[1]])]
    headline_mates = best_score.is_mate() and (
        best_score is chess.engine.MateGiven or best_score.mate() > 0)
    if not unproved or headline_mates:
        return [("v_forced", dict(n=len(rows)))]
    toughest = min(rows, key=lambda r: r[1])
    out = [("v_decisive", dict(n=len(rows), k=len(unproved),
                               floor=fmt(toughest[1])))]
    # Most replies mated, the toughest in centipawns: the distance is the
    # open question, and very likely the win is a mate.
    if headline_understates(best_score, len(mated), len(unproved)):
        out.append(("v_forced_mates", dict(n=len(mated), total=len(rows),
                                           san=toughest[0])))
    return out


def playout_notes(res, asked):
    """The lines a playout earns, in order. Pure, for the tests.

    `playout_cut` only when the budget stopped it. A game that ended, or
    reached a claimable draw, stopped because of the position -- and a
    claimable draw with no reset of the clock is the fortress signature, the
    opposite of an inconclusive run.
    """
    keys = ["playout_reset" if res["first_reset"] is not None
            else "playout_no_reset"]
    if res["over"]:
        keys.append("playout_over")
    elif res["claimable"]:
        keys.append("playout_claimable")
    # A run that simply used up its plies with no reset and no repetition has
    # not seen a fortress; it has seen nothing yet. On the queen-and-pawns win
    # the --line rows are built on, the first reset came at ply 53 of 60.
    if (res["first_reset"] is None and res.get("reason") == "done"
            and not res["over"] and not res["claimable"]):
        keys.append("playout_limit_full" if res["plies"] >= 100
                    else "playout_limit")
    if res.get("reason") == "budget":
        keys.append("playout_cut")
    elif res.get("reason") == "error":
        keys.append("playout_error")
    return keys


def upside_down(board):
    """Does the position look like it was read from the wrong side of the board?

    A diagram drawn from Black's side reads as a normal one and yields the same
    position rotated 180 degrees -- perfectly legal and perfectly wrong. The
    legality check misses this entirely, and the only clue inside the placement
    itself is pawn direction: White's pawns advance up, Black's down, so on
    average White's stand lower. The test is coarse, so it fires only on a clear
    discrepancy and with enough pawns on both sides.
    """
    white = [chess.square_rank(s) for s in board.pieces(chess.PAWN, chess.WHITE)]
    black = [chess.square_rank(s) for s in board.pieces(chess.PAWN, chess.BLACK)]
    if len(white) < 3 or len(black) < 3:
        return False
    return sum(white) / len(white) - sum(black) / len(black) > 0.5


def ascii_board(board, flip):
    """The placement as a labelled 8x8 grid, for comparing against the diagram.

    The Lichess link is the better check but costs a context switch: open a tab,
    compare, come back. Printed here, the board sits in the same view as the
    diagram it came from, which is what makes the comparison actually happen.

    Case carries the colour -- 'K' is White's king, 'k' is Black's -- because the
    error this is meant to catch is positional, and a piece letter that also
    states its side costs nothing extra to read. Files are labelled on both edges
    so a piece can be traced to its file without counting columns: miscounting a
    run of empty squares is the failure mode that produces a file-shifted FEN,
    legal and wrong.

    With `flip` the board is drawn from Black's side, matching a diagram drawn
    that way -- the same orientation the Lichess link uses.

    Since 2.8.0 this is the fallback, not the default: a rendered SVG is
    written on every run and shown instead. The grid still runs when the
    write fails, when `--diagram none` is given, and when `--text-board` asks for
    it explicitly -- a position that cannot be checked at all is worse than
    one checked in plain letters, so the text path is kept rather than
    deleted.

    A boxed grid of Unicode chess glyphs was tried in 2.6.0 and removed in
    2.7.0: box-drawing characters and chess glyphs only line up when the font
    gives both the same advance width, and outside a monospace terminal --
    a chat client, a notebook, a rendered Markdown pane -- they usually do
    not, so the grid arrives visibly skewed. That reasoning is why the
    replacement is a real rendering rather than a prettier text one: plain
    letters survive any font, and an SVG does not depend on fonts at all.
    """
    ranks = range(8) if flip else range(7, -1, -1)
    files = range(7, -1, -1) if flip else range(8)
    head = "  " + " ".join("hgfedcba" if flip else "abcdefgh")
    out = [head]
    for r in ranks:
        row = []
        for f in files:
            piece = board.piece_at(chess.square(f, r))
            row.append(piece.symbol() if piece else ".")
        out.append(f"{r + 1} " + " ".join(row) + f" {r + 1}")
    out.append(head)
    return "\n".join(out)


SVG_SIZE = 390          # the SVG is scalable; this is only its nominal box
PNG_WIDTH = 780         # 390 rasterises legibly but blurs the moment it is zoomed


def find_rasteriser():
    """Which SVG-to-PNG converter this machine has, if any.

    Returns "rsvg-convert", "cairosvg" or None. Both work and both were
    measured on the container this skill runs in: `rsvg-convert` renders in
    about 0.05 s against cairosvg's 0.38 s, and neither is present by default
    (installing them costs 3.2 s via apt and 2.6 s via pip respectively). So
    the faster one is preferred when both are there, and a machine with
    neither simply keeps the SVG.

    ImageMagick is deliberately not in the list even though `convert` *is*
    installed here. It does not rasterise SVG itself -- it delegates to
    `rsvg-convert` and fails with a delegate error when that is missing, so
    trusting it would mean an empty PNG and a confident message about having
    written one.

    cairosvg is imported, not merely located, because it loads libcairo at
    import time: with the Python package present and the C library missing it
    raises OSError rather than ImportError, which is why the except clause is
    broad. A diagram is a convenience; nothing here may take down the run.
    """
    if shutil.which("rsvg-convert"):
        return "rsvg-convert"
    try:
        import cairosvg  # noqa: F401
        return "cairosvg"
    except Exception:
        return None


def default_diagram_path(fmt):
    """Where the diagram goes when `--diagram-path` is not given.

    The pre-2.8.0 default was `board.svg` in the working directory, which was
    fine for a flag nobody passed and wrong for something that runs on every
    invocation: the working directory is usually the skill's own folder, and a
    read-only or shared install then fails on every run. So the first writable
    of three is used -- the outputs folder this skill runs inside, then the
    working directory, then a temporary directory. A run that can write
    nowhere still answers; it just falls back to the letter grid.
    """
    name = "board." + fmt
    for candidate in ("/mnt/user-data/outputs", os.getcwd(), tempfile.gettempdir()):
        if os.path.isdir(candidate) and os.access(candidate, os.W_OK):
            return os.path.join(candidate, name)
    return os.path.join(tempfile.gettempdir(), name)


def save_diagram(board, flip, path, fmt, tool):
    """Render the position to `path` as a real diagram, not text.

    The SVG comes from `chess.svg`, which ships inside python-chess: no extra
    dependency, about a millisecond, and it needs nothing a working install
    does not already have. Since 2.8.0 it runs on every invocation instead of
    only under a flag. The letter grid it replaced existed to be compared
    against a diagram, and comparing a diagram against another diagram is the
    comparison that actually gets made: a shifted file or a piece read in the
    wrong colour shows up at a glance, where in a grid of letters it has to be
    traced square by square. Coordinates are drawn on so a piece can still be
    named without counting squares -- the check the labelled text grid was
    built around.

    Since 2.9.0 the PNG is preferred when a rasteriser exists, and the reason
    is not that it looks better. An assistant reading this output can open a
    PNG and cannot open an SVG, so the PNG is what restores the second half of
    the reading check: the position gets compared against the source diagram
    by machine as well as by the user. The SVG remains the fallback because it
    costs nothing and always works.
    """
    svg = chess.svg.board(
        board, orientation=chess.BLACK if flip else chess.WHITE, size=SVG_SIZE,
        coordinates=True)
    if fmt == "svg":
        with open(path, "w", encoding="utf-8") as f:
            f.write(svg)
        return
    if tool == "rsvg-convert":
        proc = subprocess.run(
            ["rsvg-convert", "-w", str(PNG_WIDTH), "-o", path],
            input=svg.encode("utf-8"), stderr=subprocess.PIPE)
        if proc.returncode != 0 or not os.path.getsize(path):
            raise OSError(proc.stderr.decode("utf-8", "replace").strip()
                          or "rsvg-convert wrote nothing")
        return
    import cairosvg
    cairosvg.svg2png(bytestring=svg.encode("utf-8"), write_to=path,
                     output_width=PNG_WIDTH)


def material(board, color):
    """Piece counts for one side, in descending value order.

    A per-side count is the only check that catches a piece read in the wrong
    colour, and it also catches a piece dropped from the reading altogether --
    neither of which disturbs legality.
    """
    parts = []
    for kind in (chess.QUEEN, chess.ROOK, chess.BISHOP,
                 chess.KNIGHT, chess.PAWN):
        n = len(board.pieces(kind, color))
        if n:
            parts.append(f"{chess.piece_symbol(kind).upper()}x{n}")
    return " ".join(parts) if parts else "-"


# --- engine session ----------------------------------------------------------

class Timeline:
    """Per-stage timing.

    Not for reporting but for finding the bottleneck: the time almost never
    goes where it is looked for. The sum of stages is reconciled against the
    wall clock, so a forgotten stage shows up in the remainder row.

    Stages are always written to the shared journal when one exists; whether
    they are also printed is a separate decision (--timing).
    """

    def __init__(self, started):
        self.started = started
        self.stages = []
        self._mark = started

    def stage(self, name, note="", seconds=None):
        """Close a stage: from the last mark to now, unless a time is given."""
        now = time.time()
        self.stages.append((name, now - self._mark if seconds is None else seconds, note))
        self._mark = now

    def skip(self):
        """Move the mark without recording a stage (a branch not taken)."""
        self._mark = time.time()

    def rows(self):
        total = time.time() - self.started
        rows = list(self.stages)
        rest = total - sum(sec for _, sec, _ in rows)
        if rest > 0.05:
            rows.append((t("st_other"), rest, ""))
        return rows, total

    def journal(self, rows):
        """Hand the stages to the shared journal (scripts/stage.py --report).

        The journal is created by --start; while it does not exist the script
        writes nothing.
        """
        path = os.environ.get("CHESS_TIMELINE", "/tmp/chess-verdict-timeline.tsv")
        if not os.path.exists(path):
            return
        try:
            with open(path, "a", encoding="utf-8") as f:
                for name, sec, note in rows:
                    note = " ".join(str(note).split())
                    f.write(f"1\t{name}\t{sec:.3f}\t{note}\n")
        except OSError:
            pass

    def finish(self, budget, show):
        rows, total = self.rows()
        self.journal(rows)
        if not show:
            return
        texts = [f"{name}, {note}" if note else name for name, _, note in rows]
        width = max(len(x) for x in texts)
        unit = t("unit")
        print(t("t_header"))
        for text, (_, sec, _) in zip(texts, rows):
            share = f"{sec / total * 100:3.0f}%" if total > 0 else "  -"
            print(f"  {text:<{width}}  {sec:6.1f} {unit}  {share}")
        print(f"  {t('t_total'):<{width}}  {total:6.1f} {unit}        "
              f"{t('t_budget', budget=budget)}")


class Line:
    """One engine line. `proved` marks a line that came out of the mate ladder.

    Such a line has no depth to report. Until 2.22.0 it carried 2n or 2n+2 --
    arithmetic on the rung number, not anything the engine said -- and printed
    it in the same brackets as a measured depth, where nothing distinguished
    the two. The engine does report a depth for `go mate n`, but it is the
    depth the movetime happened to reach (45 for a mate in 4 found in 0.3 s),
    which answers a question nobody asked. Naming what the line actually is
    costs less and claims less.
    """

    __slots__ = ("depth", "score", "pv", "proved")

    def __init__(self, depth, score, pv, proved=False):
        self.depth, self.score, self.pv = depth, score, pv
        self.proved = proved


class Session:
    def __init__(self, budget):
        self.threads, self.hash_mb = cpu_count(), hash_size()
        self.engine = chess.engine.SimpleEngine.popen_uci(ENGINE_PATH)
        self.engine.configure({"Threads": self.threads, "Hash": self.hash_mb})
        self.started = time.time()
        self.deadline = self.started + budget

    def left(self):
        return self.deadline - time.time()

    def close(self):
        self.engine.quit()

    def evaluate_at_clock(self, board, hm=90, seconds=2.0):
        """Re-evaluate the same placement with the fifty-move counter advanced.

        The fifth FEN field is part of the position: the engine applies the
        fifty-move rule inside its search, so setting the counter near its
        limit asks a different question -- can this advantage be converted, or
        even merely be kept alive by a capture or a pawn move, before the game
        is drawn under the rule. An advantage that survives is real. One that
        collapses to zero has failed to show progress in the remaining plies,
        which is what a fortress looks like -- and also what a long theoretical
        win looks like, which is why the caller must not read a collapse as a
        draw. Returns a score from `board`'s point of view, or None.
        """
        probe = board.copy(stack=False)
        probe.halfmove_clock = hm
        try:
            info = self.engine.analyse(
                probe, chess.engine.Limit(time=seconds), game="fifty-probe")
        except chess.engine.EngineError:
            return None
        score = info.get("score")
        return score.pov(board.turn) if score is not None else None

    def playout(self, board, plies=60, step=0.3):
        """Play the position out against itself and watch the halfmove clock.

        This is what separates a fortress from a slow win, which the clock
        probe alone cannot: in a won position the strong side eventually forces
        a capture or a pawn move and the counter resets; in a fortress it never
        does. Self-play is not a proof -- both sides are the same fallible
        engine -- but the burden here is one-sided. The engine has claimed a
        decisive advantage; sixty plies in which it cannot even reset the
        counter against itself is evidence against its own claim.
        """
        b = board.copy(stack=False)
        first_reset, reset_san, evals = None, None, []
        # Why the loop stopped, because the reader is told what to conclude
        # from it. Until 2.27.0 a playout that ended on a claimable repetition
        # was reported as cut short by the budget -- on the fortress in
        # tests/hard.epd, at ply 14 of a 60 s budget -- and SKILL.md says a
        # truncated playout proves nothing, so the one signal that separates a
        # fortress from a slow win was discarded as a timeout.
        played, reason = 0, "done"
        for i in range(plies):
            if b.is_game_over(claim_draw=True):
                reason = "ended"
                break
            if self.left() <= step + 0.5:
                reason = "budget"
                break
            try:
                info = self.engine.analyse(
                    b, chess.engine.Limit(time=step), game="playout")
            except chess.engine.EngineError:
                reason = "error"
                break
            pv, score = info.get("pv"), info.get("score")
            move = pv[0] if pv else next(iter(b.legal_moves), None)
            if move is None:
                reason = "error"
                break
            if score is not None:
                evals.append(score.pov(board.turn))
            san = b.san(move)
            b.push(move)
            played += 1
            if b.halfmove_clock == 0 and first_reset is None:
                first_reset, reset_san = played, san
        outcome = b.outcome()
        return {
            "plies": played, "first_reset": first_reset, "reset_san": reset_san,
            "halfmove_clock": b.halfmove_clock,
            "over": outcome is not None,
            "claimable": outcome is None and b.can_claim_draw(),
            "result": b.result(claim_draw=True),
            "first": evals[0] if evals else None,
            "last": evals[-1] if evals else None,
            "reason": reason,
        }

    def probe_mate(self, board, rungs=5, step=0.3):
        """A ladder of `go mate n` queries, n = 1 upward, before the main search.

        This is a correctness fix, not an optimisation. Ordinary iterative
        deepening prunes a sacrificial mating move as unpromising, so a composed
        mate in three comes back as a plain evaluation and the verdict is wrong
        in kind, not merely in precision. `go mate n` asks a different question
        -- does a mate in at most n exist -- and answers it in milliseconds when
        one does.

        The ladder climbs rather than descends, so the first rung that answers
        gives the shortest mate the ladder can see. Each rung accepts only a mate
        no longer than it asked for: the engine may return a longer mate it
        happened to notice, and that is not what this rung proved.

        The PV that comes back from a mate query is often truncated. A follow-up
        search to depth 2n+2 over the now-warm hash table recovers the full line;
        if it fails to, the short PV is kept rather than discarded.

        Returns ``(n, Line, proved_to)``. `proved_to` is the highest rung that
        actually came back saying there is no mate in at most that many moves.
        A rung the budget cut off, or one the engine answered nothing to, proves
        nothing, and until 2.24.0 the caller could not tell the two apart: a run
        that managed one rung of sixteen reported "no mate up to 16" into the
        timing table and the shared journal. That is the same confusion the
        descending re-probe was built to avoid, left standing in the ladder's
        own report of itself.

        Costs at most ``rungs * step`` seconds on a position with no short
        mate, which is the reason the default ladder is short.
        """
        proved_to = 0
        for n in range(1, rungs + 1):
            if self.left() <= step + 0.2:
                break
            try:
                info = self.engine.analyse(
                    board, chess.engine.Limit(mate=n, time=step), game=GAME_KEY)
            except chess.engine.EngineError:
                break
            score, pv = info.get("score"), info.get("pv")
            if score is None or not pv:
                continue
            pov = score.pov(board.turn)
            if not pov.is_mate() or not (0 < pov.mate() <= n):
                # `go mate n` asks whether a mate in AT MOST n exists, so one
                # definite no settles every distance below it as well -- a gap
                # left by an unanswered rung underneath does not weaken this.
                proved_to = n
                continue

            return n, self._fill_pv(
                board, n, Line(None, score, list(pv), proved=True)), proved_to
        return None, None, proved_to

    def probe_shorter(self, board, m, step):
        """Given a mate in m, ask directly whether anything shorter exists.

        The ladder in ``probe_mate`` climbs from n = 1 because it does not yet
        know whether a mate exists at all. Here one does, so climbing is exactly
        wrong: on a mate in 9 it spends five rungs proving there is no mate in
        1, 2, 3, 4 or 5, which was never the question. Measured on the pinned
        matetrack sample, the ascending version cost 212 s against 70 s and
        converted nothing.

        `go mate n` answers "is there a mate in at most n", so a single rung at
        n = m-1 settles it. The usual outcome is one failed rung and a return;
        the loop only continues when something shorter was actually found, in
        which case it descends again from there.

        Returns ``(n, Line, proved)``. `proved` says whether a rung actually
        came back with "nothing at this distance". A rung the budget never
        reached looks identical from outside and proves nothing -- reporting it
        as "nothing shorter than m" is the error this whole method exists to
        keep out of the ladder.
        """
        found_n, found_line, proved = None, None, False
        n = m - 1
        while n >= 1:
            if self.left() <= step + 0.2:
                break
            try:
                info = self.engine.analyse(
                    board, chess.engine.Limit(mate=n, time=step), game=GAME_KEY)
            except chess.engine.EngineError:
                break
            score, pv = info.get("score"), info.get("pv")
            if score is None or not pv:
                break
            pov = score.pov(board.turn)
            if not pov.is_mate() or not (0 < pov.mate() <= n):
                proved = True
                break
            found_n = pov.mate()
            found_line = self._fill_pv(
                board, found_n, Line(None, score, list(pv), proved=True))
            n = found_n - 1
        # Descending to a mate in 1 needs no rung: nothing is shorter than one.
        return found_n, found_line, proved or n < 1

    def _fill_pv(self, board, n, line):
        """A mate query often returns a truncated PV; a short search over the
        now-warm hash table recovers the full line. The short PV is kept when it
        does not."""
        try:
            full = self.engine.analyse(
                board, chess.engine.Limit(depth=2 * n + 2), game=GAME_KEY)
        except chess.engine.EngineError:
            return line
        fs, fpv = full.get("score"), full.get("pv")
        if fs is not None and fpv and len(fpv) > len(line.pv):
            fpov = fs.pov(board.turn)
            if fpov.is_mate() and 0 < fpov.mate() <= n:
                return Line(None, fs, list(fpv), proved=True)
        return line

    def search(self, board, multipv=1, soft=5.0, hard=None, min_depth=18,
               max_depth=30, stable=5, nodes=None):
        """One search with a convergence stop.

        Iterations are read as they arrive and grouped by depth: a depth counts
        only once it is complete, otherwise the first and second lines come from
        different iterations and cannot be compared.

        The ceilings -- depth and hard time -- are handed to the engine in one
        command (`Limit` combines them into `go depth ... movetime ...`, first
        one wins). The loop keeps only what UCI cannot express:

          * a proven mate -- there is no point going past depth 2n;
          * the best move unchanged for `stable` iterations once `min_depth` is
            reached: further calculation refines the number, not the answer;
          * the soft ceiling `soft`, but never before `min_depth`: the engine can
            stop on time OR on depth, and what is wanted here is AND;
          * what is left of the overall budget, which the engine knows nothing of.

        With `nodes` set, the search is capped by node count and both the time
        and convergence stops are switched off: a mode for testing the skill,
        where the result must reproduce regardless of machine load.
        """
        t0 = time.time()
        if nodes:
            hard = None
        else:
            hard = min(hard if hard is not None else soft * 3, max(0.5, self.left()))
        limit = chess.engine.Limit(depth=max_depth, time=hard, nodes=nodes)

        want = min(multipv, board.legal_moves.count())
        done, cur, cur_depth, reached = {}, {}, 0, 0
        prev_move, streak = None, 0

        with self.engine.analysis(board, limit, multipv=multipv, game=GAME_KEY) as an:
            for info in an:
                depth, pv, score = info.get("depth"), info.get("pv"), info.get("score")
                if not depth or not pv or score is None:
                    continue
                if depth != cur_depth:
                    cur, cur_depth = {}, depth
                cur[info.get("multipv", 1)] = Line(depth, score, list(pv))
                # a depth counts only in full: lines taken from different
                # iterations are not comparable with each other
                if len(cur) >= want:
                    done, reached = dict(cur), depth

                if info.get("multipv", 1) != 1:
                    continue
                top = pv[0]
                streak = streak + 1 if top == prev_move else 0
                prev_move = top

                pov = score.pov(board.turn)
                elapsed = time.time() - t0
                if pov.is_mate() and pov.mate() > 0 and depth >= 2 * pov.mate():
                    # Take line 1 from this depth even though line 2 has not
                    # arrived. The stop fires on line 1, and Stockfish sends
                    # the MultiPV lines of an iteration in order, so line 2 of
                    # the mating depth was always still in flight -- and the
                    # "a depth counts only in full" rule fell back to the depth
                    # before, discarding the mate: +8.92 at depth 12 for a mate
                    # in 6 found at depth 13. A proof outranks comparability;
                    # the second line keeps its own depth, and the gap between
                    # a mate and a centipawn score is labelled, not subtracted.
                    done, reached = {**done, 1: cur[1]}, depth
                    break
                if nodes:
                    continue           # node mode: the engine's limit only
                # the hard time is already in Limit; what is left here is the
                # overall budget, which the engine knows nothing about
                if self.left() <= 0.3:
                    break
                if depth >= min_depth and (streak >= stable or elapsed >= soft):
                    break

        if not done:
            done, reached = cur, cur_depth
        return done, reached, time.time() - t0


# --- full enumeration of replies (only when there are few) -------------------

def enumerate_replies(ses, board, side, args):
    """List every reply. Used where there are only a handful: in a mating net
    the complete list is itself the proof.

    Returns the table rows and how many replies needed a search: mates and
    stalemates follow from the rules and the engine is not started for them.
    """
    rows, searched = [], 0
    for move in board.legal_moves:
        san = board.san(move)
        board.push(move)
        outcome = board.outcome(claim_draw=True)
        if outcome is not None:
            if outcome.winner is None:
                rows.append((san, chess.engine.Cp(0), "", t("r_draw")))
            elif outcome.winner == side:
                rows.append((san, chess.engine.MateGiven, "", t("r_mate")))
            else:
                rows.append((san, chess.engine.Mate(0), "", t("r_mate_att")))
        elif ses.left() < 1.0:
            rows.append((san, chess.engine.Cp(0), "", t("r_unscored")))
        else:
            searched += 1
            lines, depth, _ = ses.search(
                board, soft=args.reply_time, hard=args.reply_time * 2,
                min_depth=args.reply_depth, stable=3, nodes=args.nodes)
            top = lines.get(1)
            line = board.variation_san(top.pv[:args.pv_plies]) if top else ""
            rows.append((san, top.score.pov(side) if top else chess.engine.Cp(0),
                         line, f"d{depth}"))
        board.pop()
    rows.sort(key=lambda r: r[1])
    return rows, searched


# --- legality ----------------------------------------------------------------

#: A status code says which rule was broken; it says it as an integer. The
#: reader of this output wants to know what is wrong with the board.
STATUS_WORDS = {
    chess.STATUS_NO_WHITE_KING: "White has no king",
    chess.STATUS_NO_BLACK_KING: "Black has no king",
    chess.STATUS_TOO_MANY_KINGS: "a side has more than one king",
    chess.STATUS_TOO_MANY_WHITE_PAWNS: "White has more than eight pawns",
    chess.STATUS_TOO_MANY_BLACK_PAWNS: "Black has more than eight pawns",
    chess.STATUS_PAWNS_ON_BACKRANK: "a pawn stands on the first or eighth rank",
    chess.STATUS_TOO_MANY_WHITE_PIECES: "White has more than sixteen pieces",
    chess.STATUS_TOO_MANY_BLACK_PIECES: "Black has more than sixteen pieces",
    chess.STATUS_BAD_CASTLING_RIGHTS: "the castling rights do not match the board",
    chess.STATUS_INVALID_EP_SQUARE: "the en passant square is impossible",
    chess.STATUS_OPPOSITE_CHECK: "both kings are attacked at once",
    chess.STATUS_EMPTY: "the board is empty",
    chess.STATUS_IMPOSSIBLE_CHECK: "the check could not have arisen from a legal move",
}

#: Where the engine has nothing to say. Everything else is merely unreachable.
FATAL_STATUS = (chess.STATUS_NO_WHITE_KING | chess.STATUS_NO_BLACK_KING
                | chess.STATUS_TOO_MANY_KINGS | chess.STATUS_OPPOSITE_CHECK
                | chess.STATUS_EMPTY)


def status_words(status):
    """A status code as a sentence, every flag it carries named."""
    named = [text for flag, text in STATUS_WORDS.items() if status & flag]
    return "; ".join(named) if named else f"status {int(status)}"


# --- playing a line onto the position ----------------------------------------
#
# This exists because of a concrete failure, and the failure is worth stating
# plainly. Asked what happens after a capture, the assistant typed the resulting
# placement into a new FEN by hand and analysed that. The recapture it had in
# mind was a black pawn taking *backwards*, which is not a move -- but the
# placement it produced was a perfectly legal position, the engine evaluated it
# at 0.00 without complaint, and a forced win was reported to the user as a
# draw. Two further hand-typed FENs in the same session dropped a pawn and
# invented one.
#
# Legality is no defence here and never could be: a position reached by an
# impossible move is not an illegal position, it is a legal position that the
# game cannot reach from where the user is standing. The only check that catches
# it is playing the moves, which is what this does.

MOVE_NUMBER = re.compile(r"^\d+\.(\.\.)?")
RESULT_MARKS = ("1-0", "0-1", "1/2-1/2", "1/2", "*")


def line_tokens(text):
    """Moves out of a line as it is normally written or pasted.

    Move numbers, whether glued to the move (``1.Qh8``) or standing apart
    (``1. Qh8``, ``12...Kc2``), and result markers are dropped. Everything
    else is handed to the move parser, which is where a bad token is caught --
    guessing here about what is or is not a move would only move the failure
    somewhere quieter.
    """
    out = []
    for raw in text.replace(",", " ").split():
        tok = MOVE_NUMBER.sub("", raw.strip())
        if not tok or tok in RESULT_MARKS:
            continue
        out.append(tok)
    return out


def line_stop(board, n, token, why):
    """Refuse, naming the move, the reason and what was actually available."""
    legal = [board.san(m) for m in board.legal_moves]
    shown = ", ".join(legal[:12]) + (f", ... ({len(legal)} in all)"
                                     if len(legal) > 12 else "")
    sys.exit(t("line_bad_move", n=n, token=token, why=why, fen=board.fen(),
               side=t("black") if board.turn == chess.BLACK else t("white"),
               count=len(legal), word="move" if len(legal) == 1 else "moves",
               legal=shown or "none"))


def apply_line(board, text):
    """Play `text` onto `board` in place. Every move is checked; a bad one stops
    the run rather than being skipped or approximated."""
    tokens = line_tokens(text)
    if not tokens:
        sys.exit(t("line_empty"))
    start = board.copy(stack=False)
    moves = []
    for n, tok in enumerate(tokens, 1):
        if board.is_game_over(claim_draw=False):
            sys.exit(t("line_over", n=n, result=board.result(),
                       fen=board.fen()))
        move = None
        try:
            move = board.parse_san(tok)
        except chess.AmbiguousMoveError:
            line_stop(board, n, tok, t("line_ambiguous"))
        except chess.IllegalMoveError:
            why = t("line_illegal")
        except (chess.InvalidMoveError, ValueError):
            why = t("line_unparsable")
        if move is None:
            # SAN failed. The token may still be UCI -- which is the form to
            # fall back on, and the form the refusal message recommends.
            try:
                cand = chess.Move.from_uci(tok.lower())
            except ValueError:
                cand = None
            if cand is not None and cand in board.legal_moves:
                move = cand
            elif cand is not None:
                why = t("line_illegal")
        if move is None:
            line_stop(board, n, tok, why)
        moves.append(move)
        board.push(move)
    print(t("line_applied", san=start.variation_san(moves), fen=board.fen()))


# --- main analysis -----------------------------------------------------------

def run(args):
    tl = Timeline(_STARTED)
    tl.stage(t("st_import"))
    # The parse comes before every legality message this file defines, and used
    # to be the one step with no message of its own: a miscounted rank -- the
    # most common error there is in a hand-read FEN -- exited with a traceback.
    # A placement with no second field parses without complaint and comes back
    # as White to move. That is not a lenient default, it is the one guess this
    # skill forbids anywhere else -- SKILL.md step 1 says the turn must never be
    # inferred -- and it arrives with no symptom: the position is legal, the
    # evaluation is real, and it answers the mirror image of the question.
    fields = args.fen.split()
    if len(fields) < 2:
        sys.exit(t("fen_no_turn", fen=args.fen))
    try:
        board = chess.Board(args.fen)
    except ValueError as exc:
        sys.exit(t("bad_fen", why=exc, fen=args.fen))
    # The fatal check runs on the FEN as given, before any moves: there is no
    # sense in playing a line onto a position with a king missing. Everything
    # else is judged on the position the line actually reaches.
    root_fatal = board.status() & FATAL_STATUS
    if root_fatal:
        sys.exit(t("illegal", why=status_words(root_fatal)))
    if args.line:
        apply_line(board, args.line)
    status = board.status()
    if status != chess.STATUS_VALID:
        # Not every illegality is the same kind of illegality, and a single
        # `status != VALID` exit treated them as if they were. Measured against
        # Stockfish over UCI: with both kings attacked at once, or a king
        # missing, the engine returns no bestmove at all -- there is no answer
        # to give. With nine pawns, a pawn on the first rank, or excess
        # material it answers normally and the evaluation is real chess; the
        # position simply cannot be reached from the start. The first group
        # stops the run, the second only annotates it.
        #
        # The fatal branch is checked above, on the FEN before any --line moves
        # are played; a legal move cannot produce one, so reaching it here would
        # be a bug rather than a user error.
        print(t("unreachable", why=status_words(status)))
    if board.is_game_over(claim_draw=True):
        sys.exit(t("over", result=board.outcome(claim_draw=True).result()))

    side = board.turn
    # "Position is legal" would contradict the line above it when the position
    # is merely unreachable, so that claim is only made where it is true.
    print(t("legal" if status == chess.STATUS_VALID else "playable",
            side=t("black") if side == chess.BLACK else t("white"),
            n=board.legal_moves.count()))
    # The fifth FEN field decides games and is never questioned by legality:
    # the same endgame reads +2.57 with 0 here and 0.00 with 90. Diagrams carry
    # no clock and img2fen.py writes 0 unconditionally, so a zero is as often an
    # assumption as a reading -- print it either way and say which it might be.
    remaining = 100 - board.halfmove_clock
    print(t("clock", hm=board.halfmove_clock,
            note=t("clock_fresh") if board.halfmove_clock == 0
            else t("clock_late", plies=remaining) if remaining <= 20 else ""))
    # The clock above always gets a line because it is always an assumption.
    # Castling only does when the field was absent: given one, it is a reading.
    if len(fields) < 3:
        print(t("fen_no_castling"))
    if upside_down(board):
        print(t("warn_flip"))
    # The rendered diagram, the letter grid and the link all face one way. By
    # default that is the side to move, the puzzle-site convention. But the
    # diagram exists to be compared with the source, and books print White at
    # the bottom whoever is to move: a Black-to-move book diagram came out
    # rotated 180 degrees against its source, and the square-by-square check
    # had to be made across the rotation -- the orientation error the whole
    # reading procedure guards against. `--view` names the source's side.
    flip = (args.view == "black") if args.view != "auto" else side == chess.BLACK
    print(t("board_link") + "https://lichess.org/analysis/"
          + board.fen().replace(" ", "_")
          + ("?color=black" if flip else ""))
    # At seven men or fewer the position is solved and the engine is not the
    # tool: no Syzygy files are installed here, so K+B+N against a bare king --
    # a forced mate in at most 33 -- comes back as about +2.6 at any depth. The
    # container cannot reach the tablebase itself (the egress proxy refuses the
    # host), so the URL is for the user to open.
    if chess.popcount(board.occupied) <= 7:
        print(t("tb_link", url="https://tablebase.lichess.ovh/standard?fen="
                + board.fen().replace(" ", "_")))
    side_name = t("black") if flip else t("white")
    # A rendered diagram is the default reading check since 2.8.0, and a PNG
    # when the machine can make one since 2.9.0; the letter grid runs when it
    # is asked for, and automatically when the write fails. A diagram that
    # cannot be written is a lost convenience, not a lost answer: fall back and
    # carry on rather than abort a search the user is waiting for.
    show_text = args.text_board or args.diagram == "none"
    if args.diagram != "none":
        tool = find_rasteriser()
        # Not `fmt`: that name is a scoring helper defined below in this same
        # function, and shadowing it turned every evaluation into a TypeError.
        diagram_fmt = args.diagram
        if diagram_fmt == "auto":
            # An explicit path decides the format when it names one: writing a
            # PNG to a file called board.svg is worse than either format.
            ext = os.path.splitext(args.diagram_path or "")[1].lower()
            diagram_fmt = "svg" if ext == ".svg" else ("png" if tool else "svg")
        if diagram_fmt == "png" and not tool:
            print(t("png_unavailable"))
            diagram_fmt = "svg"
        path = args.diagram_path or default_diagram_path(diagram_fmt)
        try:
            save_diagram(board, flip=flip, path=path, fmt=diagram_fmt, tool=tool)
            print(t("board_svg", side=side_name, path=path))
        except Exception as exc:      # OSError, or a rasteriser misbehaving
            print(t("board_svg_failed", path=path, err=exc))
            show_text = True
        else:
            tl.stage(t("st_render", fmt=diagram_fmt,
                       tool=tool if diagram_fmt == "png" else t("render_builtin")))
    if show_text:
        print(t("board_ascii", side=side_name))
        print(ascii_board(board, flip=flip))
    print(t("board_counts",
            w=material(board, chess.WHITE), b=material(board, chess.BLACK)))

    tl.stage(t("st_legal"))

    try:
        ses = Session(args.budget)
    except (OSError, chess.engine.EngineError) as exc:
        # The setup step SKILL.md describes can fail -- no network, a different
        # distribution, a stale STOCKFISH -- and saying so is the whole answer.
        sys.exit(t("no_engine", path=ENGINE_PATH, why=exc))
    tl.stage(t("st_engine", threads=ses.threads, mb=ses.hash_mb))
    try:
        # 0. Mate ladder. Runs first, because its result changes what the main
        #    search is asked for: with a mate in n proved, there is nothing to
        #    gain past depth 2n+2. Skipped in --fast and in node mode, where
        #    reproducibility matters more than finding a composed mate.
        #
        #    Until 2.10.0 `--quick` skipped it too, which made the flag mean
        #    something its name never said. Measured on a 16-position matetrack
        #    sample: 12 mates found by default, 2 with the ladder off -- and
        #    `--quick` is exactly what SKILL.md recommends for "was this move a
        #    mistake", where a missed mate on either side inverts the answer.
        #    The two questions are now separate flags: `--quick` drops the
        #    second line and the defences, `--fast` also drops the ladder.
        probe_n, probe_line = None, None
        if args.mate_probe > 0 and not args.fast and not args.nodes:
            probe_n, probe_line, proved_to = ses.probe_mate(
                board, rungs=args.mate_probe, step=args.probe_step)
            # "No mate up to N" is a claim about N rungs, and before 2.24.0 it
            # was printed whether or not N rungs had run. A ladder the budget
            # cut off says only how far it got, and says it out loud: a missing
            # mate does not make the answer less precise, it inverts it.
            if probe_n:
                outcome = t("probe_found", n=probe_n)
            elif proved_to >= args.mate_probe:
                outcome = t("probe_none", rungs=args.mate_probe)
            else:
                outcome = t("probe_cut", done=proved_to, rungs=args.mate_probe)
                print(t("ladder_cut", done=proved_to, first=proved_to + 1,
                        rungs=args.mate_probe))
            tl.stage(t("st_probe", rungs=args.mate_probe, step=args.probe_step,
                       outcome=outcome))
        elif args.fast:
            print(t("ladder_off"))

        # 1. Main search. MultiPV=2 gives the second-best move at the same
        #    depth; a separate search excluding the best move would cost twice
        #    as much and return depths that cannot be compared.
        multipv = 1 if (args.no_second or args.quick or args.fast) else 2
        ceiling = min(args.depth, 2 * probe_n + 2) if probe_n else args.depth
        lines, search_depth, _dt = ses.search(
            board, multipv=multipv, soft=args.time, hard=args.time * 3,
            min_depth=args.min_depth, max_depth=ceiling, stable=args.stable,
            nodes=args.nodes)
        top = lines.get(1)
        if top is None and probe_line is not None:
            top = probe_line
        if top is None:
            sys.exit(t("no_line"))
        tl.stage(t("st_main", depth=search_depth, multipv=multipv))
        best, best_score = top.pv[0], top.score.pov(side)

        # The ladder is a proof, the search is a heuristic: when they disagree
        # about whether a mate exists, the proof wins. Without this the ladder
        # would find the mate and the reported answer would still not have it.
        if probe_n is not None and not (
                best_score.is_mate() and 0 < best_score.mate() <= probe_n):
            print(t("probe_kept", n=probe_n))
            top = probe_line
            best, best_score = top.pv[0], top.score.pov(side)
            lines = {1: top}

        # 1b. Re-probe the shorter distances, but only once a mate is known to
        #     exist. The first ladder is deliberately fast -- its cost is paid
        #     by every position, and most positions have no mate at all -- and
        #     a rung that times out is silently indistinguishable from a rung
        #     that proved nothing. That is exactly how a mate in 4 with a quiet
        #     first move came back as a mate in 6: `go mate 4` needed more than
        #     0.3 s, and the ordinary search prunes a non-checking king move.
        #     Here the situation is different: a mate in m is already in hand,
        #     so the question "is there anything shorter" is worth real time,
        #     and it is asked only on the rare positions that have a mate.
        if (args.reprobe_step > 0 and not args.fast and not args.nodes
                and best_score.is_mate() and best_score.mate() > 0):
            m = best_score.mate()
            if m >= 2:
                re_n, re_line, re_proved = ses.probe_shorter(
                    board, m, step=args.reprobe_step)
                if re_n:
                    outcome = t("reprobe_found", n=re_n)
                elif re_proved:
                    outcome = t("reprobe_none", m=m)
                else:
                    outcome = t("reprobe_cut", m=m)
                    print(t("reprobe_cut_note", m=m, n=m - 1))
                tl.stage(t("st_reprobe", m=m, step=args.reprobe_step,
                           outcome=outcome))
                if re_n is not None:
                    print(t("reprobe_note", m=m, n=re_n,
                            step=args.reprobe_step, step0=args.probe_step))
                    # The move the search liked becomes the runner-up: it still
                    # mates, just later, and saying so is more use than dropping
                    # it. Keep it only when it is a different move.
                    previous = top
                    top = re_line
                    best, best_score = top.pv[0], top.score.pov(side)
                    lines = ({1: top, 2: previous}
                             if previous.pv and previous.pv[0] != best
                             else {1: top})

        # The time is the engine's, from startup to here -- the ladder, the
        # main search and the re-probe together. It used to be the main search
        # alone, so a run that spent four seconds proving a mate on the ladder
        # printed "0.0 s" beside the answer and "Search time: 4.5 s" below it.
        print(t("best", san=board.san(best), score=fmt(best_score),
                where=depth_note(top), dt=time.time() - ses.started))

        second = lines.get(2)
        if second is not None and second.pv:
            alt_score = second.score.pov(side)
            print(t("second", san=board.san(second.pv[0]), score=fmt(alt_score),
                    where=depth_note(second),
                    tail=gap_note(best_score, alt_score)))

        print(t("main_line"), board.variation_san(top.pv[:args.pv_plies]))

        # The defence section pushes the best move onto `board` and never pops
        # it, so from here on `board` is the position *after* the best move.
        # Anything that needs the position the user asked about must use this
        # snapshot: taken before the push, it also carries the halfmove clock
        # and the piece count the probe below reasons about. Reading the live
        # board there produced an evaluation with the sign reversed, which is
        # the most plausible-looking wrong number this script can print.
        root = board.copy(stack=False)
        root_pv = list(top.pv)

        # 2. Defences. The evaluation after the best move was already taken
        #    against the best defence -- the reply list explains the win, it
        #    does not establish it.
        forced_verdict = False
        if args.scan == "off" or args.quick or args.fast:
            print(t("scan_off"))
            tl.skip()
        else:
            board.push(best)
            replies = board.legal_moves.count()
            if not replies:
                print(t("no_replies"))
                tl.skip()
            elif args.scan == "full" or replies <= args.full_max or (
                    best_score.is_mate() and best_score.mate() > 0
                    and replies <= args.full_max * 2):
                rows, searched = enumerate_replies(ses, board, side, args)
                tl.stage(t("st_full", n=len(rows), word=word_replies(len(rows)),
                           k=searched))
                print(t("all_replies", n=len(rows)))
                for san, score, line, note in rows:
                    print(f"  {san:7} {fmt(score):>15} [{note}] {line}")
                # What the list proves is decided in one pure function, so the
                # tests exercise the rule itself; see enumeration_verdict().
                verdict = enumeration_verdict(best_score, rows, args.win)
                for key, fields in verdict:
                    print(t(key, **fields))
                # The fifty-move probe below must know whether it faces a
                # proof. Only v_forced is one since 2.27.0.
                forced_verdict = verdict[0][0] == "v_forced"
            else:
                k = min(args.defences, replies)
                dl, dd, ddt = ses.search(
                    board, multipv=k, soft=args.defence_time,
                    hard=args.defence_time * 2, min_depth=args.reply_depth,
                    max_depth=args.depth, stable=args.stable, nodes=args.nodes)
                tl.stage(t("st_defences", k=k, n=replies, depth=dd))
                print(t("def_header", k=k, n=replies, depth=dd, dt=ddt))
                got = [dl[i] for i in sorted(dl) if dl[i].pv]
                for ln in got:
                    print(f"  {board.san(ln.pv[0]):7} "
                          f"{fmt(ln.score.pov(side)):>15} "
                          f"{board.variation_san(ln.pv[:args.pv_plies])}")
                if got:
                    hardest = min(got, key=lambda l: l.score.pov(side))
                    verdict = (t("v_survives")
                               if decisive(hardest.score.pov(side), args.win)
                               else t("v_not_decisive"))
                    rest = replies - k
                    print(t("v_tail", verdict=verdict,
                            san=board.san(hardest.pv[0]),
                            score=fmt(hardest.score.pov(side)),
                            n=rest, word=word_replies(rest)))
                    mated = winning_mates([ln.score.pov(side) for ln in got])
                    if headline_understates(best_score, len(mated),
                                            len(got) - len(mated)):
                        print(t("v_tail_mates"))

        # 3. The fifty-move probe. Runs last, because it wipes the hash table
        #    that everything above depends on. Automatic where the failure it
        #    catches actually lives -- seven men or fewer, where a theoretical
        #    ending can read as a modest edge, and a decisive evaluation, where
        #    a fortress reads as a rout -- and off in node mode, which exists to
        #    reproduce exactly. It cannot fire when the clock is already high,
        #    since then the main search has answered the same question.
        #
        #    A main line that captures or pushes a pawn in its first few plies
        #    resets the counter by itself, so the probe has nothing to say
        #    about it: skipping those is what keeps an ordinary tactic at its
        #    old two seconds instead of four.
        resets_soon = False
        probe_board = root.copy(stack=False)
        for mv in root_pv[:8]:
            if probe_board.is_capture(mv) or probe_board.piece_type_at(
                    mv.from_square) == chess.PAWN:
                resets_soon = True
                break
            probe_board.push(mv)
        want_probe = args.fifty_probe == "on" or (
            args.fifty_probe == "auto" and not args.nodes
            and root.halfmove_clock < 40
            and not best_score.is_mate()
            and not resets_soon
            and (chess.popcount(root.occupied) <= 7
                 # Either side: a fortress is a position where the *other* side
                 # is told it is winning by ten pawns, so testing only the side
                 # to move would miss the case the probe exists for.
                 or abs(best_score.score(mate_score=100000)) >= args.win))
        if want_probe and ses.left() > args.fifty_seconds + 1:
            probed = ses.evaluate_at_clock(
                root, hm=args.fifty_clock, seconds=args.fifty_seconds)
            if probed is not None:
                collapsed = (not probed.is_mate()
                             and abs(probed.score(mate_score=100000)) < 50)
                tl.stage(t("st_fifty", hm=args.fifty_clock,
                           outcome=(t("fifty_collapsed", score=fmt(probed))
                                    if collapsed
                                    else t("fifty_held", score=fmt(probed)))))
                print("")
                if not collapsed:
                    print(t("fifty_note_held", hm=args.fifty_clock,
                            score=fmt(probed)))
                elif forced_verdict:
                    print(t("fifty_note_collapsed_forced", hm=args.fifty_clock,
                            score=fmt(probed), score0=fmt(best_score)))
                else:
                    print(t("fifty_note_collapsed", hm=args.fifty_clock,
                            score=fmt(probed), score0=fmt(best_score),
                            plies=100 - args.fifty_clock))

        # 4. Playout, only when asked. Thirty seconds is too much to spend on
        #    every position, and the question it answers -- fortress or slow
        #    win -- only arises after the probe above has collapsed.
        if args.playout > 0 and ses.left() > 2:
            res = ses.playout(root, plies=args.playout, step=args.playout_step)
            tl.stage(t("st_playout", plies=res["plies"], step=args.playout_step))
            print(t("playout_header", plies=res["plies"],
                    step=args.playout_step))
            for key in playout_notes(res, args.playout):
                if key == "playout_reset":
                    print(t(key, ply=res["first_reset"], san=res["reset_san"]))
                elif key in ("playout_over", "playout_claimable"):
                    print(t(key, ply=res["plies"], result=res["result"]))
                else:
                    print(t(key, plies=res["plies"], hm=res["halfmove_clock"],
                            asked=args.playout))
            if res["first"] is not None:
                print(t("playout_evals", first=fmt(res["first"]),
                        last=fmt(res["last"])))

        tl.stage(t("st_print"))
        tl.finish(args.budget, show=args.timing)
        if not args.timing:
            print(t("t_short", dt=time.time() - ses.started, budget=args.budget))
        if ses.left() < 1:
            print(t("budget_warn"))
    finally:
        ses.close()


def parse_args(argv):
    p = argparse.ArgumentParser(
        description="Analyse a chess position with Stockfish")
    p.add_argument("fen", nargs="?", default=chess.STARTING_FEN)
    p.add_argument("--version", action="version",
                   version=f"chess-verdict {VERSION}",
                   help="print the build identity and exit")
    p.add_argument("--line", default=None, metavar="MOVES",
                   help="play these moves onto the FEN and analyse the "
                        "position they reach. SAN or UCI, move numbers and "
                        "result markers ignored, so a line can be pasted as "
                        "written. Every move is checked and a bad one stops "
                        "the run. This is the only supported way to ask what "
                        "happens after a sequence of moves: a placement typed "
                        "out by hand is not checked against the moves that "
                        "would reach it, and an impossible move usually still "
                        "produces a legal FEN")
    p.add_argument("--depth", type=int, default=int(os.environ.get("DEPTH", 30)),
                   help="depth ceiling (rarely reached: the stop is on convergence)")
    p.add_argument("--min-depth", type=int, default=18,
                   help="depth before which stopping is not considered")
    p.add_argument("--stable", type=int, default=5,
                   help="how many iterations in a row the best move must hold")
    p.add_argument("--time", type=float, default=5.0,
                   help="soft ceiling on the main search, s (hard is three times it)")
    p.add_argument("--budget", type=float, default=float(os.environ.get("BUDGET", 30)),
                   help="overall ceiling for the whole analysis, s")
    p.add_argument("--scan", choices=("auto", "full", "off"), default="auto",
                   help="defences: auto -- best defences in one search, "
                        "full -- enumerate every reply")
    p.add_argument("--defences", type=int, default=4,
                   help="how many best defences to show")
    p.add_argument("--defence-time", type=float, default=4.0,
                   help="soft ceiling on the defence search, s")
    p.add_argument("--full-max", type=int, default=8,
                   help="up to how many replies are enumerated automatically")
    p.add_argument("--reply-depth", type=int, default=16,
                   help="working depth per reply")
    p.add_argument("--reply-time", type=float, default=2.0,
                   help="soft ceiling per reply in a full enumeration, s")
    p.add_argument("--win", type=int, default=400,
                   help="decisive-advantage threshold in centipawns")
    p.add_argument("--mate-probe", type=int, default=None, metavar="N",
                   help="rungs of the `go mate n` ladder run before the main "
                        "search, n from 1 to N (default 5); 0 disables it. "
                        "When the source announces the length -- a problem "
                        "captioned mate in 8, an EPD `bm #9` -- pass it, with "
                        "--probe-step 3: the default ceiling sits below the "
                        "centre of mass of composed problems")
    p.add_argument("--probe-step", type=float, default=0.3, metavar="SEC",
                   help="seconds per rung of the mate ladder")
    p.add_argument("--reprobe-step", type=float, default=3.0, metavar="SEC",
                   help="seconds per rung when the shorter distances are "
                        "re-asked after a mate has been found; 0 disables it")
    p.add_argument("--nodes", type=int, default=None,
                   help="cap the search by node count instead of time: the result "
                        "reproduces exactly, but the convergence stop is switched "
                        "off (a mode for testing the skill, not for answering)")
    p.add_argument("--pv-plies", type=int, default=12,
                   help="how many plies of the line to print")
    p.add_argument("--no-second", action="store_true",
                   help="do not show the second-best move")
    p.add_argument("--timing", action="store_true",
                   help="print the per-stage breakdown (off by default; the stages "
                        "are journalled either way)")
    p.add_argument("--quick", action="store_true",
                   help="evaluation only, no second line and no defence "
                        "analysis. The mate ladder still runs: since 2.10.0 "
                        "this flag no longer makes the run mate-blind")
    p.add_argument("--fast", action="store_true",
                   help="what --quick did before 2.10.0: evaluation only and "
                        "the mate ladder off as well. Roughly a second quicker "
                        "per position, and it misses most composed mates -- do "
                        "not use it where a mate could be on the board")
    p.add_argument("--fifty-probe", choices=("auto", "on", "off"),
                   default="auto",
                   help="re-evaluate the same placement with the halfmove clock "
                        "advanced, to see whether the advantage survives the "
                        "fifty-move rule. auto (default) runs it at seven men "
                        "or fewer and on a decisive evaluation")
    p.add_argument("--fifty-clock", type=int, default=90, metavar="N",
                   help="what the halfmove clock is set to for that probe")
    p.add_argument("--fifty-seconds", type=float, default=2.0, metavar="SEC",
                   help="how long the fifty-move probe searches")
    p.add_argument("--playout", type=int, default=0, metavar="PLIES",
                   help="play the position out against itself for this many "
                        "plies and report the ply at which the halfmove clock "
                        "first resets. This is what separates a fortress from "
                        "a slow win; 60 plies costs about 20 s")
    p.add_argument("--playout-step", type=float, default=0.3, metavar="SEC",
                   help="seconds a move during the playout")
    # `--board-style` is deliberately absent. It existed only to escape the
    # boxed Unicode grid when a font misaligned it; with that grid gone there
    # is one text rendering and nothing to choose between. An unknown-argument
    # error is the right answer for a stale invocation -- silently accepting a
    # flag that no longer does anything is how a caller keeps believing it does.
    #
    # `--diagram-path` takes a value; `--svg` never did, on purpose. As
    # `--svg [PATH]` it swallowed the FEN that followed it -- `solve.py --svg
    # "<fen>"` wrote a file named after the position and analysed the
    # *starting* position instead, silently and with full confidence. The path
    # lives on its own flag, which is rarely used and is never written directly
    # before the FEN.
    #
    # `--svg`, `--no-svg` and `--svg-path` survive as aliases, and that is not
    # the same mistake as the `--board-style` note above. That flag would have
    # gone on being accepted while doing nothing it promised; these three still
    # do exactly what their names say -- ask for a rendering, suppress it,
    # choose where it goes -- and only the current spelling has changed. The
    # help text names the current one.
    p.add_argument("--view", choices=("auto", "white", "black"), default="auto",
                   help="which side the diagram, letter grid and link are drawn "
                        "from. auto (default): the side to move. When the "
                        "position came from an image, pass the image's own "
                        "side, so the rendering can be laid over the source "
                        "without turning it round")
    p.add_argument("--diagram", choices=("auto", "png", "svg", "none"),
                   default="auto",
                   help="auto (default) writes a PNG when a rasteriser is "
                        "installed and an SVG otherwise; none prints the letter "
                        "grid instead of a diagram")
    p.add_argument("--no-svg", dest="diagram", action="store_const", const="none",
                   help="alias for --diagram none")
    p.add_argument("--svg", action="store_true",
                   help="no-op since 2.8.0: a diagram is rendered on every run. "
                        "Kept so existing invocations keep working")
    p.add_argument("--text-board", action="store_true",
                   help="print the letter grid as well as the rendered diagram")
    p.add_argument("--diagram-path", "--svg-path", dest="diagram_path",
                   default=None, metavar="PATH",
                   help="where the diagram is written; defaults to board.png or "
                        "board.svg in the outputs folder, the working directory "
                        "or a temporary directory, whichever is writable first. "
                        "A path ending in .svg selects that format")
    args = p.parse_args(argv)
    # `--mate-probe` defaults to None rather than 5 so that passing it can be
    # told from not passing it. Combined with --fast it was silently ignored,
    # which is how an explicit `--mate-probe 11` ran no ladder at all and the
    # position came back with a plain evaluation and no hint that the flag had
    # been dropped. A flag that does nothing must say so, not be swallowed.
    if args.mate_probe is not None and args.fast:
        p.error(t("fast_conflict"))
    if args.mate_probe is None:
        args.mate_probe = 5
    # The same rule, for the other flag that switches a whole stage off.
    # `--scan full --quick` printed "(defence analysis disabled)" and the banner
    # advertised `--defences 6` as a setting in force -- the invented-settings
    # line the banner exists to prevent, produced by the banner itself.
    if args.quick or args.fast:
        mode = "--fast" if args.fast else "--quick"
        dead = ["--scan full"] if args.scan == "full" else []
        dead += [flag for name, flag in (("defences", "--defences"),
                                         ("defence_time", "--defence-time"),
                                         ("full_max", "--full-max"))
                 if getattr(args, name) != p.get_default(name)]
        if dead:
            p.error(t("quick_conflict", flags=", ".join(dead), mode=mode))
    # Built here because this is where the parser still exists to be asked what
    # a default was. Built after the --fast/--mate-probe resolution above, so
    # the line reports the settings the search will run with rather than the
    # ones typed: a flag that was overridden must not appear as if it held.
    args.banner = banner(p, args, "solve", skip=("fen", "banner"),
                         effective={"mate_probe": 5})
    return args


if __name__ == "__main__":
    # Printed from the entry point, not from run(), so importing this module
    # stays silent for selftest.py and anything else using it as a library.
    args = parse_args(sys.argv[1:])
    print(args.banner)
    run(args)
