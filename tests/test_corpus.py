#!/usr/bin/env python3
"""Corpus test suite: run the converter against a set of real-world Abaqus decks.

Two layers of checking:
  1. CONVERT   — every deck converts without crashing and the result is referentially
                 consistent (every element node / set member resolves). Always runs.
  2. SOLVE     — optional: if CalculiX (ccx) is found, decks marked ``expect_solve``
                 must solve (ccx exits 0, prints "Job finished" with no *ERROR and no
                 crash, and runs an analysis STEP), and mesh-only decks marked
                 ``parse_only`` must be accepted by ccx; the rest are recorded only.

Usage:
    python corpus/fetch.py          # first, download the decks (network)
    python tests/test_corpus.py     # convert + (if ccx present) solve
    pytest tests/test_corpus.py

If ``corpus/files/`` is empty the corpus checks skip cleanly, so this file is safe to
run without network. The bundled ``examples/`` are exercised by ``test_convert.py``.
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "corpus"))
import abq2ccx as A          # noqa: E402
import validate_with_ccx as V  # noqa: E402  (reuse find_ccx)
from manifest import CORPUS  # noqa: E402

FILES = os.path.join(ROOT, "corpus", "files")


def _opt():
    return type("O", (), {"solid_dof": False})()


def present():
    return [e for e in CORPUS if os.path.exists(os.path.join(FILES, e["name"] + ".inp"))]


def convert(name):
    rep = A.Report()
    blocks = A.read_blocks(os.path.join(FILES, name + ".inp"), rep)
    body = A.Converter(rep, _opt()).convert(blocks)       # convert first: the header
    text = "\n".join(rep.header_comment_lines() + body) + "\n"   # lists its warnings
    return text, rep


def dangling(text):
    rep = A.Report()
    fd, p = tempfile.mkstemp(suffix=".inp")
    os.close(fd)
    open(p, "w").write(text)
    try:
        c = A.Converter(rep, _opt())
        c.build_geometry(A.read_blocks(p, rep))
        g = c.geom
        n = sum(1 for _, (_t, conn) in g.elements.items() for nd in conn if nd not in g.nodes)
        n += sum(1 for ids in g.nsets.values() for i in ids if i not in g.nodes)
        n += sum(1 for ids in g.elsets.values() for i in ids if i not in g.elements)
        return n
    finally:
        os.unlink(p)


# What a crashing ccx prints after (or instead of) a clean finish.  The issue #3 deck
# made unpatched ccx builds print "Job finished" and then abort in glibc's free().
ABORT_SIGNS = ("free(): ", "double free", "malloc(): ", "corrupted size", "Aborted",
               "Segmentation fault")
STEP_RE = re.compile(r"^\s*STEP\s+\d+\s*$", re.M)


def classify_ccx_run(returncode, stdout, stderr):
    """Classify a finished ccx run:

    * ``"solved"``   - exit 0, "Job finished", no ``*ERROR``, no crash/abort, and at
                       least one analysis STEP executed;
    * ``"accepted"`` - the same, but no STEP ran (a mesh-only deck ccx only parsed);
    * ``"failed"``   - anything else, including a crash after "Job finished".

    The per-iteration "no convergence" message is normal in nonlinear solves and is not
    treated as failure; a run that really gives up prints ``*ERROR``."""
    if returncode != 0 or "Job finished" not in stdout:
        return "failed"
    if "*ERROR" in stdout or "*ERROR" in stderr:
        return "failed"
    if any(s in stdout or s in stderr for s in ABORT_SIGNS):
        return "failed"
    return "solved" if STEP_RE.search(stdout) else "accepted"


def run_ccx(ccx, env, text):
    d = tempfile.mkdtemp()
    open(os.path.join(d, "job.inp"), "w").write(text)
    fe = dict(os.environ)
    fe.update(env)
    try:
        p = subprocess.run([ccx, "job"], cwd=d, env=fe, capture_output=True,
                           text=True, timeout=300)
    except subprocess.TimeoutExpired:
        return "failed"
    finally:
        shutil.rmtree(d, ignore_errors=True)
    return classify_ccx_run(p.returncode, p.stdout, p.stderr)


# --- pytest entry points ------------------------------------------------------

def test_corpus_converts():
    """Every present corpus deck converts and is referentially consistent."""
    decks = present()
    if not decks:
        print("corpus/files/ is empty — run 'python corpus/fetch.py' to enable corpus tests.")
        return
    for e in sorted(decks, key=lambda x: x["name"]):
        text, _ = convert(e["name"])                      # must not raise
        assert dangling(text) == 0, f"{e['name']}: dangling references after conversion"


def test_classify_ccx_run():
    """The solve judge itself (no ccx needed)."""
    ok = " STEP            1\n\n Job finished\n"
    assert classify_ccx_run(0, ok, "") == "solved"
    assert classify_ccx_run(0, " Job finished\n", "") == "accepted"     # mesh-only: no STEP ran
    # issue #3: unpatched ccx printed "Job finished", then aborted in glibc's free()
    assert classify_ccx_run(-6, ok, "free(): invalid size\n") == "failed"
    assert classify_ccx_run(134, ok, "") == "failed"
    assert classify_ccx_run(0, ok, "double free or corruption (out)\n") == "failed"
    assert classify_ccx_run(0, " *ERROR reading *NODE\n Job finished\n", "") == "failed"
    assert classify_ccx_run(201, " *ERROR reading *NODE: node number 0 is not positive\n",
                            "") == "failed"
    # per-iteration non-convergence is normal in nonlinear solves, not a failure
    assert classify_ccx_run(0, " STEP 1\n no convergence\n Job finished\n", "") == "solved"


def test_corpus_solves():
    """expect_solve decks must solve and parse_only decks must be accepted by ccx
    (if ccx is available)."""
    decks = present()
    ccx, env = V.find_ccx()
    if not decks or not ccx:
        print("no corpus files or no ccx found — skipping solve checks.")
        return
    for e in sorted(decks, key=lambda x: x["name"]):
        if e["expect_solve"]:
            status = run_ccx(ccx, env, convert(e["name"])[0])
            assert status == "solved", f"{e['name']}: expected to solve in ccx, got {status!r}"
        elif e.get("parse_only"):
            status = run_ccx(ccx, env, convert(e["name"])[0])
            assert status != "failed", f"{e['name']}: mesh-only deck was rejected by ccx"


# --- standalone runner with a summary table -----------------------------------

def main():
    decks = present()
    if not decks:
        print("corpus/files/ is empty. Run:  python corpus/fetch.py")
        return 0
    ccx, env = V.find_ccx()
    print(f"corpus: {len(decks)} deck(s)   ccx: {ccx or 'not found (solve checks skipped)'}\n")
    hdr = f"{'deck':27s} {'conv':>5s} {'W':>3s} {'dangle':>6s} {'ccx':>13s}  result"
    print(hdr)
    print("-" * len(hdr))
    failures = 0
    for e in sorted(decks, key=lambda x: x["name"]):
        name = e["name"]
        try:
            text, rep = convert(name)
        except Exception as exc:  # noqa: BLE001
            print(f"{name:27s} {'CRASH':>5s}  {type(exc).__name__}: {exc}")
            failures += 1
            continue
        d = dangling(text)
        result = "ok"
        if d:
            result = "DANGLING"
            failures += 1
        ccxcol = "-"
        if ccx:
            status = run_ccx(ccx, env, text)
            if e["expect_solve"]:
                ccxcol = "SOLVED" if status == "solved" else status.upper()
                if status != "solved":
                    result = ("UNEXPECTED: no analysis step ran" if status == "accepted"
                              else "UNEXPECTED no-solve")
                    failures += 1
            elif e.get("parse_only"):
                ccxcol = {"accepted": "ACCEPTED", "solved": "solved+"}.get(status, "FAILED")
                if status == "failed":
                    result = "UNEXPECTED: ccx rejected it"
                    failures += 1
            else:
                ccxcol = {"solved": "solved+", "accepted": "accepted+"}.get(status, "no-solve(ok)")
        print(f"{name:27s} {'ok':>5s} {rep.n_warnings:>3d} {d:>6d} {ccxcol:>13s}  {result}")
    n_solve = sum(1 for e in decks if e["expect_solve"])
    n_parse = sum(1 for e in decks if e.get("parse_only"))
    print(f"\n{len(decks)} converted, 0 dangling expected; {n_solve} expected to solve, "
          f"{n_parse} mesh-only (no analysis step) expected to be accepted by ccx.")
    print("All corpus checks passed." if not failures else f"{failures} failure(s).")
    print("\n(the remaining decks are source-deck/analysis limitations — see corpus/manifest.py.)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
