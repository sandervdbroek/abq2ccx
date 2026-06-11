#!/usr/bin/env python3
"""Corpus test suite: run the converter against a set of real-world Abaqus decks.

Two layers of checking:
  1. CONVERT   — every deck converts without crashing and the result is referentially
                 consistent (every element node / set member resolves). Always runs.
  2. SOLVE     — optional: if CalculiX (ccx) is found, decks marked ``expect_solve``
                 are run and must solve; the rest are recorded but not required.

Usage:
    python corpus/fetch.py          # first, download the decks (network)
    python tests/test_corpus.py     # convert + (if ccx present) solve
    pytest tests/test_corpus.py

If ``corpus/files/`` is empty the corpus checks skip cleanly, so this file is safe to
run without network. The bundled ``examples/`` are exercised by ``test_convert.py``.
"""

import os
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
    text = "\n".join(rep.header_comment_lines() + A.Converter(rep, _opt()).convert(blocks)) + "\n"
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


def run_ccx(ccx, env, text):
    d = tempfile.mkdtemp()
    open(os.path.join(d, "job.inp"), "w").write(text)
    fe = dict(os.environ)
    fe.update(env)
    try:
        out = subprocess.run([ccx, "job"], cwd=d, env=fe, capture_output=True,
                             text=True, timeout=300).stdout
    except subprocess.TimeoutExpired:
        out = "TIMEOUT"
    finally:
        shutil.rmtree(d, ignore_errors=True)
    # "Job finished" + no fatal "*ERROR" == success. The per-iteration "no convergence"
    # message is normal in nonlinear solves and must NOT be treated as failure.
    return "Job finished" in out and "*ERROR" not in out


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


def test_corpus_solves():
    """Decks marked expect_solve must solve in ccx (if ccx is available)."""
    decks = present()
    ccx, env = V.find_ccx()
    if not decks or not ccx:
        print("no corpus files or no ccx found — skipping solve checks.")
        return
    for e in sorted(decks, key=lambda x: x["name"]):
        if not e["expect_solve"]:
            continue
        text, _ = convert(e["name"])
        assert run_ccx(ccx, env, text), f"{e['name']}: expected to solve in ccx but did not"


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
            ok = run_ccx(ccx, env, text)
            if e["expect_solve"]:
                ccxcol = "SOLVED" if ok else "FAILED"
                if not ok:
                    result = "UNEXPECTED no-solve"
                    failures += 1
            else:
                ccxcol = "solved+" if ok else "no-solve(ok)"
        print(f"{name:27s} {'ok':>5s} {rep.n_warnings:>3d} {d:>6d} {ccxcol:>13s}  {result}")
    n_solve = sum(1 for e in decks if e["expect_solve"])
    print(f"\n{len(decks)} converted, 0 dangling expected; {n_solve} expected to solve.")
    print("All corpus checks passed." if not failures else f"{failures} failure(s).")
    print("\n(expect_solve=False decks are source-deck/analysis limitations — see corpus/manifest.py.)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
