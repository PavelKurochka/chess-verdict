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
"""Tests for scripts/setup.py and for what solve.py and img2fen.py print last.

Run directly; no framework, no network, a few seconds:

    python3 tests/test_setup.py

Nothing here installs anything. Where the engine, python-chess and a rasteriser
are already present -- CI installs them first -- setup.py must skip every step
and say Ready. The failure path runs against a stub apt-get put first on PATH,
which answers `update` with the sandbox's 403 and `install` with the error the
claude.ai container gave on 2026-10-01; that part needs a POSIX shell and is
skipped on Windows.

Both behaviours exist because models rewrote the setup lines they were given
(2026-10-02: Opus and Sonnet piped them through tail, Haiku dropped one), and
because a diagram written to disk is not shown to the user unless it is sent.
"""

import os
import shutil
import stat
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, os.pardir, "scripts")
SETUP = os.path.join(SCRIPTS, "setup.py")
SOLVE = os.path.join(SCRIPTS, "solve.py")
sys.path.insert(0, SCRIPTS)

import setup  # noqa: E402

ENGINE = os.environ.get("STOCKFISH", "/usr/games/stockfish")
FEN = "6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1"    # back-rank mate in one

failures = []


def check(name, condition, detail=""):
    print(f"{'ok  ' if condition else 'FAIL'}  {name}{'   ' + detail if detail else ''}")
    if not condition:
        failures.append(name)


def run_setup(tmp, *args, env_extra=None):
    env = dict(os.environ, CHESS_TIMELINE=os.path.join(tmp, "tl.tsv"))
    env.update(env_extra or {})
    r = subprocess.run([sys.executable, SETUP, *args], capture_output=True,
                       text=True, env=env)
    return r.returncode, r.stdout + r.stderr, env["CHESS_TIMELINE"]


def test_refused_hosts():
    out = ("Ign:2 https://download.docker.com/linux/ubuntu noble InRelease\n"
           "W: Failed to fetch https://download.docker.com/linux/ubuntu/dists/"
           "noble/InRelease  Invalid response from proxy: HTTP/1.1 403 "
           "Forbidden\n"
           "Get:1 http://archive.ubuntu.com/ubuntu noble InRelease [256 kB]\n")
    check("the 403 host is named, the working mirror is not",
          setup.refused_hosts(out) == ["download.docker.com"],
          str(setup.refused_hosts(out)))


def test_unknown_option():
    with tempfile.TemporaryDirectory() as tmp:
        code, out, _ = run_setup(tmp, "--imgae")
    check("a misspelt option is refused, not ignored", code == 2, f"exit {code}")


def test_all_present():
    if not (setup.have_engine() and setup.have_module("chess")
            and setup.have_rasteriser()):
        print("skip  everything present: engine, python-chess or rasteriser "
              "missing on this machine")
        return
    with tempfile.TemporaryDirectory() as tmp:
        code, out, journal = run_setup(tmp)
        with open(journal, encoding="utf-8") as f:
            rows = f.read()
    check("nothing to install: exit 0 and Ready", code == 0 and "Ready:" in out,
          f"exit {code}")
    check("... every step skipped, no apt-get update",
          out.count("skip  ") == 3 and "update package lists" not in out)
    check("... and the journal is started with a row per step",
          rows.startswith("#start") and rows.count("already installed") == 3)


def stub_apt(tmp):
    bindir = os.path.join(tmp, "bin")
    os.mkdir(bindir)
    path = os.path.join(bindir, "apt-get")
    with open(path, "w", encoding="utf-8") as f:
        f.write('#!/bin/sh\n'
                'if [ "$1" = update ]; then\n'
                '  echo "W: Failed to fetch https://download.docker.com/linux/'
                'ubuntu/dists/noble/InRelease  Invalid response from proxy: '
                'HTTP/1.1 403 Forbidden"\n'
                '  exit 0\n'
                'fi\n'
                'echo "E: Unable to locate package stockfish" >&2\n'
                'exit 100\n')
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
    return bindir


def test_engine_fails():
    if os.name == "nt":
        print("skip  failure path: needs a POSIX shell for the apt-get stub")
        return
    with tempfile.TemporaryDirectory() as tmp:
        bindir = stub_apt(tmp)
        code, out, journal = run_setup(tmp, env_extra={
            "STOCKFISH": os.path.join(tmp, "no-such-engine"),
            "PATH": bindir + os.pathsep + os.environ.get("PATH", "")})
        with open(journal, encoding="utf-8") as f:
            rows = f.read()
    check("engine missing: exit 1 and NOT READY",
          code == 1 and "NOT READY" in out, f"exit {code}")
    check("... the failing step shows apt's own reason",
          "FAIL  install engine" in out
          and "Unable to locate package stockfish" in out)
    check("... the 403 during update is called harmless, not a failure",
          "ok    update package lists" in out and "harmless" in out)
    check("... and the exit code is in the journal", "exit code 100" in rows)


def solve_tail(*extra):
    r = subprocess.run([sys.executable, SOLVE, FEN, "--quick", *extra],
                       capture_output=True, text=True)
    return r.returncode, r.stdout.strip().splitlines()


def test_handoff_is_last():
    if not setup.have_engine():
        print(f"skip  diagram hand-off: no engine at {ENGINE}")
        return
    with tempfile.TemporaryDirectory() as tmp:
        target = os.path.join(tmp, "board.png" if setup.have_rasteriser()
                              else "board.svg")
        code, lines = solve_tail("--diagram-path", target)
        check("solve.py ends by asking for the diagram to be sent",
              code == 0 and len(lines) >= 3
              and lines[-3].startswith("Last step before answering")
              and lines[-2].strip() == target,
              " | ".join(lines[-3:-1]))
        check("... and the very last line keeps the notation as printed",
              lines[-1].startswith("Write moves as printed here (Ra8#)"),
              lines[-1][:60])
        code, lines = solve_tail("--diagram", "none")
        check("... and says nothing of the kind when no diagram was written",
              code == 0 and not any("Last step" in x for x in lines))


def test_source_builds_the_sheet():
    """--source replaces the separate compare.py step neither model ran."""
    if not (setup.have_engine() and setup.have_rasteriser()
            and setup.have_module("PIL") and setup.have_module("numpy")):
        print("skip  comparison sheet: needs the engine, a rasteriser, "
              "Pillow and NumPy")
        return
    import chess
    import chess.svg
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "source.png")
        svg = chess.svg.board(chess.Board(FEN), size=480, coordinates=True)
        subprocess.run(["rsvg-convert", "-o", src], input=svg.encode(),
                       check=True)
        target = os.path.join(tmp, "board.png")
        sheet = os.path.join(tmp, "compare.png")
        code, lines = solve_tail("--diagram-path", target, "--source", src)
        check("--source writes compare.png beside the diagram",
              code == 0 and os.path.isfile(sheet))
        check("... and the hand-off names the sheet, not the bare diagram",
              len(lines) >= 3 and "comparison sheet" in lines[-3]
              and lines[-2].strip() == sheet, " | ".join(lines[-3:-1]))
        code, lines = solve_tail("--diagram-path", target, "--source",
                                 os.path.join(tmp, "missing.png"))
        check("a missing source costs the sheet, not the analysis",
              code == 0 and any("sheet was not built" in x for x in lines)
              and lines[-2].strip() == target)


def test_img2fen_asks_for_a_second_reading():
    if not (setup.have_module("onnxruntime") and setup.have_module("PIL")
            and setup.have_rasteriser()):
        print("skip  img2fen reminder: needs onnxruntime, Pillow, rasteriser")
        return
    import chess
    import chess.svg
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "source.png")
        svg = chess.svg.board(chess.Board(FEN), size=480, coordinates=True)
        subprocess.run(["rsvg-convert", "-o", src], input=svg.encode(),
                       check=True)
        r = subprocess.run([sys.executable, os.path.join(SCRIPTS, "img2fen.py"),
                            src, "w"], capture_output=True, text=True)
    check("img2fen.py asks for a reading by eye and for --source",
          "This is one reading" in r.stdout and f"--source {src}" in r.stdout,
          r.stdout.strip().splitlines()[-1][:60] if r.stdout.strip() else "")


for fn in (test_refused_hosts, test_unknown_option, test_all_present,
           test_engine_fails, test_handoff_is_last, test_source_builds_the_sheet,
           test_img2fen_asks_for_a_second_reading):
    fn()

print()
if failures:
    print(f"{len(failures)} failed: {', '.join(failures)}")
    sys.exit(1)
print("all passed")
