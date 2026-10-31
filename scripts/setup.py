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
"""Set up everything an analysis needs, in one command, and start the journal.

    python3 scripts/setup.py                 # engine, python-chess, rasteriser
    python3 scripts/setup.py --image         # + Pillow and NumPy for compare.py
    python3 scripts/setup.py --recognizer    # + onnxruntime for img2fen.py

Until 2.33.0 setup was five lines in SKILL.md, each wrapped in stage.py. Every
model that ran them rewrote them: Opus and Sonnet piped each line through
`tail -2`, which hides a failure in the middle of the output and replaces the
exit code with tail's; Haiku dropped the rasteriser line altogether, so the
diagram came out as an SVG nobody could look at. A line that is not there
cannot be skipped, and output that is already short gives nothing to trim.

What this prints is one line per step and a verdict at the end. A step that
fails prints the last lines of its own output, which is where apt and pip put
the reason. Anything already installed is skipped, so a second position in the
same conversation costs a fraction of a second rather than twenty.

Exit status: 0 when the engine and python-chess are usable, 1 when either is
not -- in which case no analysis is possible and the answer has to say so. A
missing rasteriser or imaging package is reported but does not fail the run.

Every step is recorded in the timing journal (stage.py), which this starts --
or continues, when it is run again in the middle of the same analysis (see
stage.start_unless_running).

Where apt-get is not there -- Windows, macOS, a bare container -- the script
does not drive other package managers from here: winget can stop on a UAC
prompt no unattended run can answer, and a hung setup is worse than a failed
one with the command on screen. The engine step then fails and prints the
command to run by hand; python-chess still installs through pip, which works
everywhere, and a missing rasteriser degrades to SVG diagrams as before.
"""

import importlib
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import stage  # noqa: E402

def find_engine():
    """Same order as solve.py's find_engine(), which cannot be imported yet:
    python-chess, which solve.py needs, may not be installed. An explicit
    STOCKFISH wins even when it names a file that is not there; then the
    PATH; then the claude.ai container's apt location, /usr/games, which is
    not always on the agent's PATH.
    """
    from_env = os.environ.get("STOCKFISH")
    if from_env:
        return from_env
    return shutil.which("stockfish") or "/usr/games/stockfish"


ENGINE_PATH = find_engine()
PIP = [sys.executable, "-m", "pip", "install", "--break-system-packages", "-q"]
TAIL = 12           # lines of a failed step's output worth showing


def have_module(name):
    importlib.invalidate_caches()
    return importlib.util.find_spec(name) is not None


def have_engine():
    return os.path.isfile(ENGINE_PATH) and os.access(ENGINE_PATH, os.X_OK)


def have_rasteriser():
    if shutil.which("rsvg-convert"):
        return "rsvg-convert"
    # Imported, not located: cairosvg loads libcairo at import time and is
    # useless without it. Same test as solve.py's find_rasteriser().
    try:
        import cairosvg  # noqa: F401
        return "cairosvg"
    except Exception:
        return None


APT = shutil.which("apt-get")


def engine_hint():
    """The command to install Stockfish where apt-get does not run."""
    if shutil.which("winget"):
        return ("winget install --id Stockfish.Stockfish "
                "--accept-package-agreements --accept-source-agreements")
    if shutil.which("brew"):
        return "brew install stockfish"
    return ("install Stockfish from https://stockfishchess.org/download/ and "
            "put it on the PATH, or set the STOCKFISH variable")


def plan(extras):
    """The steps, in order: (label, already-present test or None, command).

    A command of None is a step this script cannot run itself: it exists to
    fail loudly and show the command for a person, not to hang on a package
    manager that may want a UAC answer no unattended run can give (winget).

    An apt package needs fresh package lists -- the claude.ai container has
    started with empty ones since October 2026 -- so `apt-get update` is put
    in front of the apt steps, and only when one of them will actually run.
    Outside apt the rasteriser step is dropped: solve.py and compare.py
    degrade to SVG on their own, and the Ready line says so.
    """
    steps = []
    if APT:
        apt = [
            ("install engine", have_engine,
             ["apt-get", "install", "-y", "-q", "stockfish"]),
            ("install rasteriser", have_rasteriser,
             ["apt-get", "install", "-y", "-q", "librsvg2-bin"]),
        ]
        if not all(present() for _, present, _ in apt):
            steps.append(("update package lists", None,
                          ["apt-get", "update", "-q"]))
        steps.append(apt[0])
        steps.append(("install python-chess", lambda: have_module("chess"),
                      PIP + ["--use-pep517", "chess"]))
        steps.append(apt[1])
    else:
        steps.append(("install engine", have_engine, None))
        steps.append(("install python-chess", lambda: have_module("chess"),
                      PIP + ["--use-pep517", "chess"]))
    if "image" in extras or "recognizer" in extras:
        steps.append(("install imaging",
                      lambda: have_module("PIL") and have_module("numpy"),
                      PIP + ["pillow", "numpy"]))
    if "recognizer" in extras:
        steps.append(("install recognizer", lambda: have_module("onnxruntime"),
                      PIP + ["onnxruntime"]))
    return steps


def refused_hosts(output):
    """Hosts the sandbox proxy answered with 403 during `apt-get update`.

    download.docker.com is one in the claude.ai container: a repository the
    image lists and the proxy refuses. It is harmless, and saying so here stops
    it being read as the reason for a failure that happened somewhere else.
    """
    hosts = re.findall(r"https?://([^/\s]+)\S*[^\n]*403", output)
    return sorted(set(hosts))


def run(cmd):
    """Run one step; return (exit code, combined output). Never raises."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           errors="replace")
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except OSError as exc:            # apt-get or pip not there at all
        return 127, f"{cmd[0]}: {exc}"


def main(argv):
    if argv and argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    extras = {a.lstrip("-") for a in argv}
    unknown = extras - {"image", "recognizer"}
    if unknown:
        print(f"unknown option: {' '.join(sorted(unknown))} "
              f"(known: --image, --recognizer)", file=sys.stderr)
        return 2

    stage.start_unless_running()

    for label, present, cmd in plan(extras):
        if present is not None and present():
            print(f"skip  {label:22} already installed")
            stage.append(0, label, None, "already installed")
            continue
        if cmd is None:
            code, dt = 1, 0.0
            out = f"nothing this script can run -- by hand: {engine_hint()}"
        else:
            started = time.time()
            code, out = run(cmd)
            dt = time.time() - started
        stage.append(0, label, dt, "" if code == 0 else f"exit code {code}")
        note = ""
        if label == "update package lists":
            hosts = refused_hosts(out)
            if hosts:
                note = (f"  ({', '.join(hosts)} refused by the sandbox proxy "
                        f"-- harmless)")
        if code == 0 and (present is None or present()):
            print(f"ok    {label:22} {dt:5.1f} s{note}")
            continue
        print(f"FAIL  {label:22} {dt:5.1f} s, exit code {code}{note}")
        for line in out.strip().splitlines()[-TAIL:]:
            print(f"      | {line}")

    engine, chess_ok, raster = have_engine(), have_module("chess"), have_rasteriser()
    print()
    if engine and chess_ok:
        parts = [f"engine {ENGINE_PATH}", "python-chess"]
        parts.append(f"diagrams as PNG ({raster})" if raster else
                     "diagrams as SVG only -- the rasteriser did not install")
        print("Ready: " + ", ".join(parts) + ".")
        return 0
    missing = [n for n, ok in (("the engine", engine),
                               ("python-chess", chess_ok)) if not ok]
    print(f"NOT READY: {' and '.join(missing)} did not install, so no analysis "
          f"can run. Say so in the answer, with the failing step above, and do "
          f"not analyse the position by hand as if the engine had.")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
