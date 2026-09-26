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
"""Regression suite: run solve.py over a fixed position list and judge the answer.

Two rules govern this file, both learned the hard way.

**It must not pass ``--quick``.** ``--quick`` drops the search to MultiPV 1, and
the stopping bugs this suite exists to catch only appear with two lines: with one
line there is no incomplete iteration to stop on. A suite that runs green under
``--quick`` proves nothing about the mode the skill actually uses. ``--scan off``
is the right flag -- it skips the defence enumeration, which is what costs the
time, and leaves the search itself alone.

**It checks the version before it checks anything else.** A suite that runs green
against a build nobody can name is worth very little, and this skill has already
lost a correctness fix to a build that never reached the installed copy. If
SKILL.md, solve.py and CHANGELOG.md disagree about the version, this refuses to
run at all.

Usage:

    python3 scripts/selftest.py                 # the whole list
    python3 scripts/selftest.py -v              # print every row, not just failures
    python3 scripts/selftest.py --file other.tsv
"""

import argparse
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SOLVE = os.path.join(HERE, "solve.py")
POSITIONS = os.path.join(ROOT, "tests", "positions.tsv")


# --- version agreement -------------------------------------------------------

def stray_versions():
    """Version numbers stated as the current one anywhere except the three
    declaration sites.

    This exists because the number was once written twice in SKILL.md -- once in
    the frontmatter and once in the prose below it -- and only the frontmatter
    was ever read. The prose copy sat two releases out of date through several
    packaged builds. Checking the three known sites against each other cannot
    catch a fourth site nobody registered, so the rule here is the other way
    round: find anything that claims to be the version, and require it to be.

    Historical references are fine and are the normal way this file talks --
    "since 2.10.0", "removed in 2.7.0". Only a bare declaration is a claim about
    the present.
    """
    claim = re.compile(r"(?i)\bversion\b[\s:*]*\**(\d+\.\d+\.\d+)")
    out = []
    names = ["SKILL.md", "README.md", "FAQ.md", "readme_for_nontechs.md"]
    refs = os.path.join(ROOT, "references")
    if os.path.isdir(refs):
        # Since 2.23.0 most of the prose lives here, so this is where a stale
        # declaration would now go unnoticed.
        names += [os.path.join("references", f) for f in sorted(os.listdir(refs))
                  if f.endswith(".md")]
    for name in names:
        path = os.path.join(ROOT, name)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            text = f.read()
        if name == "SKILL.md":                  # the frontmatter is a real site
            text = text.split("---", 2)[-1]
        for m in claim.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            out.append((name, line, m.group(1)))
    return out


def declared_versions():
    """The version as stated in each of the three places that must agree."""
    sys.path.insert(0, HERE)
    from solve import VERSION                                    # noqa: E402
    found = {"solve.py": VERSION}

    skill = os.path.join(ROOT, "SKILL.md")
    if os.path.exists(skill):
        with open(skill, encoding="utf-8") as f:
            # `metadata.version` since 2.29.1: the Agent Skills spec rejects a
            # root-level `version` key, so the declaration moved one level in.
            m = re.search(r'(?m)^\s*version:\s*"?([0-9][^"\s]*)"?\s*$',
                          f.read().split("---", 2)[1])
        found["SKILL.md"] = m.group(1) if m else None

    log = os.path.join(ROOT, "CHANGELOG.md")
    if os.path.exists(log):
        with open(log, encoding="utf-8") as f:
            m = re.search(r"(?m)^##\s+(\d+\.\d+\.\d+)", f.read())
        found["CHANGELOG.md"] = m.group(1) if m else None
    return found


def check_versions():
    """Stop before running anything if the declarations disagree."""
    found = declared_versions()
    if len(set(found.values())) > 1:
        print("version mismatch, refusing to run:")
        for where, what in found.items():
            print(f"  {where:14} {what}")
        sys.exit(2)
    current = found["solve.py"]

    stray = [s for s in stray_versions() if s[2] != current]
    if stray:
        print(f"a version is declared outside the three sites and it is not "
              f"{current}, refusing to run:")
        for name, line, what in stray:
            print(f"  {name}:{line}  says {what}")
        print("  Either update it or, better, stop restating the number there.")
        sys.exit(2)
    return current


# --- the description field ---------------------------------------------------

HARD_LIMIT = 1024       # the Agent Skills spec; over this the skill is dropped
CARD_WIDTH = 500        # what the claude.ai skill card shows before it cuts


def frontmatter_description():
    """The description as a reader gets it: folded scalar, whitespace collapsed."""
    with open(os.path.join(ROOT, "SKILL.md"), encoding="utf-8") as f:
        head = f.read().split("\n---\n")[0]
    m = re.search(r"(?m)^description: >-\n(.*)", head, re.S)
    return " ".join(m.group(1).split()) if m else None


def check_description():
    """Two failures this catches, one fatal and one merely embarrassing.

    Over 1024 characters the spec says the skill is invalid, and at least one
    loader drops it during frontmatter parse with no warning on stderr and no
    error -- it simply stops appearing in the skill list. That failure is silent
    in exactly the way this suite exists to prevent.

    The second is cosmetic but real: the claude.ai skill card renders the first
    500 characters and stops, mid-word, without an ellipsis. The text past the
    cut still reaches the model, so triggering is unaffected -- but a human
    reading the card in Settings sees a sentence break off. Requiring the 500th
    character to end a sentence costs nothing and keeps the visible half whole.
    """
    d = frontmatter_description()
    if d is None:
        print("no folded description in SKILL.md frontmatter, refusing to run")
        sys.exit(2)
    if len(d) > HARD_LIMIT:
        print(f"description is {len(d)} characters, over the {HARD_LIMIT} the "
              f"spec allows -- loaders drop it silently. Refusing to run.")
        sys.exit(2)
    if len(d) > CARD_WIDTH and d[CARD_WIDTH - 1] not in ".!?":
        print(f"description is {len(d)} characters and the claude.ai card cuts "
              f"at {CARD_WIDTH}, mid-sentence:")
        print(f"  ...{d[CARD_WIDTH - 40:CARD_WIDTH]}|{d[CARD_WIDTH:CARD_WIDTH + 20]}...")
        print("  Reorder so a sentence ends on the 500th character.")
        sys.exit(2)
    return len(d)


# --- reading the position list ----------------------------------------------

def rows(path):
    """Tab-separated: FEN, expectations, note, extra flags.

    The fourth column is optional and is split the way a shell would, so a row
    can exercise a flag rather than only a position -- ``--line`` needs this,
    since what it is asked to check is a refusal on a move, not an evaluation
    of a placement. Blank lines and # are ignored.
    """
    out = []
    with open(path, encoding="utf-8") as f:
        for n, raw in enumerate(f, 1):
            line = raw.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            parts = [p.strip() for p in line.split("\t")]
            while parts and not parts[-1]:
                parts.pop()
            if len(parts) < 2 or not parts[0] or not parts[1]:
                sys.exit(f"{path}:{n}: expected at least FEN and expectations")
            note = parts[2] if len(parts) > 2 else ""
            extra = shlex.split(parts[3]) if len(parts) > 3 else []
            out.append((parts[0], parts[1], note, extra))
    return out


# --- reading solve.py's answer ----------------------------------------------

#: Since 2.22.0 the brackets hold either a measured depth or the words that say
#: the line came off the mate ladder, which has none. Both shapes have to parse,
#: or every mate the ladder proves reads as "no answer line in the output".
BEST = re.compile(
    r"^Best move: (\S+)\s+evaluation (.+?)\s+\((?:depth (\d+)|proved\b)")


def parse_output(text):
    """Pull the verdict out of solve.py's prose.

    Returns a dict with ``san``, ``depth`` and one of ``mate`` (positive: mate
    delivered in n; negative: mate received) or ``cp`` (centipawns, from the
    point of view of the side to move). Returns None when there is no answer
    line at all -- an illegal FEN or a crash.
    """
    for line in text.splitlines():
        m = BEST.match(line.strip())
        if not m:
            continue
        san, score = m.group(1), m.group(2).strip()
        depth = int(m.group(3)) if m.group(3) else None
        out = {"san": san, "depth": depth, "cp": None, "mate": None,
               "mate_given": None}
        # Not 0 and -0: those are the same integer in Python, so the two
        # opposite outcomes used to be indistinguishable and both read as
        # "no mate delivered". A separate key says which end of the board it is.
        if score == "mate delivered":
            out["mate"], out["mate_given"] = 0, True
        elif score == "mate received":
            out["mate"], out["mate_given"] = 0, False
        elif score.startswith("mate in ") and score.endswith(" against"):
            out["mate"] = -int(score[len("mate in "):-len(" against")])
        elif score.startswith("mate in "):
            out["mate"] = int(score[len("mate in "):])
        else:
            out["cp"] = int(round(float(score) * 100))
        return out
    return None


# --- judging -----------------------------------------------------------------

def judge(expect, got, out=""):
    """Check one row's expectations. Returns a list of failure descriptions.

    Expectations are separated by ``;``:

      ``move=Nxc2+``   the best move, in SAN as solve.py prints it
      ``mate=4``       mate delivered in exactly 4
      ``mate<=4``      mate delivered in 4 or fewer -- the usual form, because a
                       shorter mate than the published one is still a solution
      ``nomate``       no mate either way
      ``cp>=400``      evaluation at least this many centipawns
      ``cp<=50``       evaluation at most this many centipawns
      ``|cp|<=50``     evaluation within this range of equality
      ``says=phrase``  the output contains this phrase
      ``refuses=why``  the run stops on an illegal position, gives that reason,
                       and produces no answer line
      ``rejects=why``  the run stops for any other reason -- a bad move in
                       ``--line`` is the case it was added for -- gives that
                       reason, and produces no answer line

    ``says=`` and ``refuses=`` exist because 2.16.0 made the answer to an
    illegal position an output in its own right rather than a bare exit. A
    refusal that stops naming its reason, or an unreachable position that
    starts being refused instead of analysed, is a regression this file could
    not previously see.

    ``rejects=`` is separate from ``refuses=`` on purpose, and the distinction
    is the whole point of 2.17.0: an illegal *position* and an impossible
    *move* are different failures. The move case produces a position that is
    perfectly legal, so a check keyed on ``ILLEGAL POSITION`` would pass a
    build that had stopped checking moves altogether.

    ``A || B`` passes when either set of expectations holds. It exists for one
    row, and for engine versions rather than for vagueness: Stockfish 19 exits
    on a position with nine pawns a side that Stockfish 16 analyses, so that
    row accepts the analysis or a clean refusal -- and still fails on the
    traceback 2.29.2 printed, which is neither.
    """
    if "||" in expect:
        tried = [judge(alt, got, out) for alt in expect.split("||")]
        if any(not b for b in tried):
            return []
        return [f"no alternative held; {' / '.join('; '.join(b) for b in tried)}"]

    bad = []
    terms = [term.strip() for term in expect.split(";") if term.strip()]
    text = [term for term in terms
            if term.startswith(("says=", "refuses=", "rejects="))]

    for term in text:
        key, _, phrase = term.partition("=")
        if phrase.lower() not in out.lower():
            bad.append(f"output does not say {phrase!r}")
        if key == "refuses" and "ILLEGAL POSITION" not in out:
            bad.append("no ILLEGAL POSITION line")
        if key in ("refuses", "rejects") and got is not None:
            bad.append(f"answered {got['san']} where it should have refused")

    rest = [term for term in terms if term not in text]
    if not rest:
        return bad
    if got is None:
        return bad + ["no answer line in the output"]

    for term in rest:
        if term.startswith("move="):
            want = term[5:]
            if got["san"] != want:
                bad.append(f"move {got['san']}, wanted {want}")

        elif term == "nomate":
            if got["mate"] is not None:
                bad.append(f"mate in {got['mate']}, wanted no mate")

        elif term.startswith("mate"):
            m = re.fullmatch(r"mate(<=|=)(\d+)", term)
            if not m:
                bad.append(f"cannot read expectation {term!r}")
                continue
            op, want = m.group(1), int(m.group(2))
            if got["mate_given"] is True and want >= 0:
                continue                    # mate is already on the board
            if got["mate"] is None or got["mate"] <= 0:
                bad.append(f"no mate delivered, wanted {term}")
            elif op == "=" and got["mate"] != want:
                bad.append(f"mate in {got['mate']}, wanted exactly {want}")
            elif op == "<=" and got["mate"] > want:
                bad.append(f"mate in {got['mate']}, wanted at most {want}")

        elif term.startswith("|cp|"):
            m = re.fullmatch(r"\|cp\|<=(\d+)", term)
            if not m:
                bad.append(f"cannot read expectation {term!r}")
            elif got["cp"] is None:
                bad.append(f"mate in {got['mate']}, wanted a quiet evaluation")
            elif abs(got["cp"]) > int(m.group(1)):
                bad.append(f"evaluation {got['cp']}, wanted within "
                           f"{m.group(1)} of equality")

        elif term.startswith("cp"):
            m = re.fullmatch(r"cp(>=|<=)(-?\d+)", term)
            if not m:
                bad.append(f"cannot read expectation {term!r}")
                continue
            op, want = m.group(1), int(m.group(2))
            if got["cp"] is None:
                # A mate is better than any centipawn floor, worse than any
                # ceiling: judge it on that basis rather than refusing.
                if op == ">=" and got["mate"] is not None and got["mate"] > 0:
                    continue
                bad.append(f"mate in {got['mate']}, wanted {term}")
            elif op == ">=" and got["cp"] < want:
                bad.append(f"evaluation {got['cp']}, wanted at least {want}")
            elif op == "<=" and got["cp"] > want:
                bad.append(f"evaluation {got['cp']}, wanted at most {want}")

        else:
            bad.append(f"cannot read expectation {term!r}")
    return bad


def _judge_selfcheck():
    """The judge must be able to fail, or a green suite means nothing.

    Written after adding ``refuses=``: an expectation form that silently
    matches everything looks exactly like a passing row.
    """
    illegal = "ILLEGAL POSITION: both kings are attacked at once. No analysis"
    answered = {"san": "e4", "mate": None, "cp": 40}
    cases = [
        ("refuses=both kings are attacked at once", None, illegal, 0),
        ("refuses=both kings are attacked at once", answered, illegal, 1),
        ("refuses=White has no king", None, illegal, 1),
        ("refuses=both kings are attacked at once", None, "Best move: e4", 2),
        ("says=unreachable", answered, "the position is unreachable", 0),
        ("says=unreachable", answered, "Best move: e4", 1),
        ("says=unreachable; cp>=400", answered, "unreachable", 1),
        # rejects= must not be satisfied by the illegal-position wording, and
        # must not accept a run that answered anyway.
        ("rejects=not legal here", None,
         "STOPPED AT MOVE 1 OF THE LINE ('g2h3'): not legal here.", 0),
        ("rejects=not legal here", answered,
         "STOPPED AT MOVE 1 OF THE LINE ('g2h3'): not legal here.", 1),
        ("rejects=not legal here", None, illegal, 1),
        ("refuses=not legal here", None,
         "STOPPED AT MOVE 1 OF THE LINE ('g2h3'): not legal here.", 1),
        # an alternative passes on either branch, and fails as a whole only
        # when neither holds -- a crash with no reason satisfies no branch
        ("says=unreachable; cp>=400 || rejects=STOCKFISH STOPPED", answered,
         "unreachable", 1),
        ("says=unreachable; cp>=400 || rejects=STOCKFISH STOPPED",
         {"san": "a5", "mate": None, "cp": 900}, "unreachable", 0),
        ("says=unreachable; cp>=400 || rejects=STOCKFISH STOPPED", None,
         "STOCKFISH STOPPED ON THIS POSITION", 0),
        ("says=unreachable; cp>=400 || rejects=STOCKFISH STOPPED", None,
         "Traceback (most recent call last)", 1),
    ]
    for expect, got, out, want in cases:
        n = len(judge(expect, got, out))
        assert n == want, f"{expect!r} on {out!r}: {n} failures, wanted {want}"


# --- running -----------------------------------------------------------------

def solve(fen, budget, extra=()):
    """One solve.py run. --scan off, never --quick: see the module docstring."""
    cmd = [sys.executable, SOLVE, fen, "--scan", "off",
           "--budget", str(budget), *extra]
    # The suite runs solve.py outside the stage.py wrapper, and solve.py journals
    # its internal stages regardless. Pointed at the default path, ten suite
    # positions land in whatever journal the session is keeping -- as an
    # unlabelled "not wrapped by stage.py" block with sixty stage rows under it,
    # which is what happened the first time this was run mid-analysis. Give the
    # suite its own file.
    env = dict(os.environ, CHESS_TIMELINE=os.path.join(
        tempfile.gettempdir(), "chess-verdict-selftest.tsv"))
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          timeout=budget + 30, env=env)
    return proc.stdout + proc.stderr


def main(argv=None):
    p = argparse.ArgumentParser(description="Run the regression suite")
    p.add_argument("--file", default=POSITIONS, help="position list to run")
    p.add_argument("--budget", type=float, default=20.0,
                   help="per-position budget in seconds")
    p.add_argument("-v", "--verbose", action="store_true",
                   help="print every row, not only the failures")
    args = p.parse_args(argv)

    _judge_selfcheck()
    version = check_versions()
    desc_len = check_description()
    print(f"chess-verdict {version}  (description {desc_len}/{HARD_LIMIT})\n")

    cases = rows(args.file)
    passed = failed = 0
    started = time.time()

    for fen, expect, note, extra in cases:
        t0 = time.time()
        try:
            out = solve(fen, args.budget, extra)
        except subprocess.TimeoutExpired:
            out = ""
        bad = judge(expect, parse_output(out), out)
        dt = time.time() - t0
        label = note or fen

        if bad:
            failed += 1
            print(f"FAIL  {label}  ({dt:.1f} s)")
            print(f"      {fen}")
            for b in bad:
                print(f"      {b}")
        else:
            passed += 1
            if args.verbose:
                print(f"ok    {label}  ({dt:.1f} s)")

    total = time.time() - started
    print(f"\n{passed} passed, {failed} failed, {total:.0f} s")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
