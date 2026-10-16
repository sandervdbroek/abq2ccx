#!/usr/bin/env python3
"""Corpus test suite: run the converter against a set of real-world Abaqus decks.

Two layers of checking:
  1. CONVERT   — every deck converts without crashing and the result is referentially
                 consistent (every element node / set member resolves). Always runs.
  2. LOADS     — decks marked ``expect_solve`` must keep a load in every step the Abaqus
                 deck loads (else ccx "solves" that step with no load at all), and
                 ``source_unloaded`` must flag exactly the decks that load no step. Always
                 runs.
  3. SOLVE     — optional: if CalculiX (ccx) is found, decks marked ``expect_solve``
                 must solve (ccx exits 0, prints "Job finished" with no *ERROR and no
                 crash, runs an analysis STEP, and writes no NaN/Inf to the .dat or
                 .frd), and mesh-only decks marked ``parse_only`` must be accepted by
                 ccx; the rest are recorded only.

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
    """The converted deck text, its report and the converter (for its load audit)."""
    rep = A.Report()
    blocks = A.read_blocks(os.path.join(FILES, name + ".inp"), rep)
    conv = A.Converter(rep, _opt())
    body = conv.convert(blocks)                           # convert first: the header
    text = "\n".join(rep.header_comment_lines() + body) + "\n"   # lists its warnings
    return text, rep, conv


def load_problem(e, conv):
    """Why an expect_solve deck's conversion fails the load audit, or None: a step the deck
    loads that keeps no load in ccx, or a source_unloaded flag that does not match."""
    if conv.unloaded_steps:
        return f"step(s) {conv.unloaded_steps} lose every load in the conversion"
    if bool(e.get("source_unloaded")) != conv.source_unloaded:
        return ("source_unloaded=True, but the deck loads a step" if e.get("source_unloaded")
                else "the deck loads no step: flag it source_unloaded=True")
    return None


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


# The solve judge lives in abq2ccx.py so the corpus test, validate_with_ccx.py and the
# CLI's --run all apply the same rules (exit code, crash messages, a STEP must run, the
# results must be finite).
classify_ccx_run = A.classify_ccx_run


def run_ccx(ccx, env, text):
    d = tempfile.mkdtemp()
    open(os.path.join(d, "job.inp"), "w").write(text)
    fe = dict(os.environ)
    fe.update(env)
    try:
        p = subprocess.run([ccx, "job"], cwd=d, env=fe, capture_output=True,
                           text=True, timeout=300)
        return classify_ccx_run(p.returncode, p.stdout, p.stderr, os.path.join(d, "job"))
    except subprocess.TimeoutExpired:
        return "failed"
    finally:
        shutil.rmtree(d, ignore_errors=True)


# --- pytest entry points ------------------------------------------------------

def test_corpus_converts():
    """Every present corpus deck converts and is referentially consistent."""
    decks = present()
    if not decks:
        print("corpus/files/ is empty — run 'python corpus/fetch.py' to enable corpus tests.")
        return
    for e in sorted(decks, key=lambda x: x["name"]):
        text, _, _ = convert(e["name"])                   # must not raise
        assert dangling(text) == 0, f"{e['name']}: dangling references after conversion"


def test_corpus_loads():
    """expect_solve decks keep a load in every step the Abaqus deck loads (a step whose loads
    were all commented out would still 'solve' in ccx, to a zero response), and
    source_unloaded flags exactly the decks that load no step at all."""
    decks = [e for e in present() if e["expect_solve"]]
    if not decks:
        print("corpus/files/ is empty — run 'python corpus/fetch.py' to enable corpus tests.")
        return
    for e in sorted(decks, key=lambda x: x["name"]):
        problem = load_problem(e, convert(e["name"])[2])
        assert problem is None, f"{e['name']}: {problem}"


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

    # A diverged solution also ends with "Job finished" and exit 0 (an explicit step on a
    # circular-section beam whose increment ccx misjudged gave NaN for every value): the
    # judge reads the results, Fortran's NaN/Infinity in the .dat's print blocks and C's
    # NAN/INF in the .frd, but not set names such as NAN in the headings, nor ccx's own
    # tables (an undamped steady-state mode at its eigenfrequency has an infinite
    # participation factor). Lines as ccx 2.23 writes them.
    head = "\n displacements (vx,vy,vz) for set {} and time  0.1668256E-03\n\n"
    ssd = ("P A R T I C I P A T I O N   F A C T O R S   F O R   F R E Q U E N C Y    "
           "0.4147260912592E+02 (CYCLES/TIME)\n\n MODE NO    FREQUENCY               FACTOR\n"
           "           (CYCLES/TIME)      REAL        IMAGINARY\n\n"
           "      1   0.1504584E+02   0.5320239E-02   0.0000000E+00\n"
           "      2   0.4147261E+02        Infinity             NaN\n")
    frd = ("    1C\n  100CL  101 1.66826E-03           2                     1    1           1\n"
           " -4  DISP        4    1\n -5  D1          1    2    1    0\n"
           " -1         1 1.00000E+00-2.00000E+00 0.00000E+00\n -1         2{}\n -3\n")
    with tempfile.TemporaryDirectory() as d:
        job = os.path.join(d, "job")

        def results(dat=None, frd_line=None):
            for ext, text in ((".dat", dat), (".frd", frd.format(frd_line) if frd_line else None)):
                if os.path.exists(job + ext):
                    os.unlink(job + ext)
                if text is not None:
                    open(job + ext, "w").write(text)
            return classify_ccx_run(0, ok, "", job)

        finite = " 1.00000E+00-2.00000E+00 0.00000E+00"
        rows = "         4  1.000000E+00 -2.000000E-01  0.000000E+00\n"
        nan_row = "         4           NaN           NaN           NaN\n"
        assert results() == "solved"                                   # no result files
        assert results(head.format("NAN") + rows, finite) == "solved"
        assert results(head.format("INF") + rows) == "solved"
        assert results(ssd + head.format("MID") + rows, finite) == "solved"
        assert results(head.format("MID") + rows + ssd, finite) == "solved"
        assert results(" statistics for surface set STOP and time  0.1000000E+01\n\n   total surface "
                       "force (fx,fy,fz) and moment about the origin(mx,my,mz)\n\n    1.804112E-16"
                       "  1.110223E-16           NaN  1.549923E+00 -1.549923E+00  0.000000E+00\n",
                       finite) == "nonfinite"                         # *SECTION PRINT
        assert results(ssd + head.format("MID") + rows.replace("0.000000E+00", "         NaN"),
                       finite) == "nonfinite"
        assert results(head.format("MID") + nan_row, finite) == "nonfinite"
        assert results(head.format("MID") + "         4      Infinity     -Infinity  0.000000E+00\n",
                       finite) == "nonfinite"
        assert results(" total force (fx,fy,fz) for set FIX and time  0.1000000E+01\n\n"
                       "      -Infinity  0.000000E+00  0.000000E+00\n", finite) == "nonfinite"
        assert results(head.format("MID") + rows,
                       " 1.00000E+00         NAN-2.00000E+00") == "nonfinite"
        assert results(None, "         INF 0.00000E+00        -INF") == "nonfinite"
        assert A.ccx_nonfinite_result(job) == "job.frd: DISP at 1.66826E-03: 2 INF 0.00000E+00 -INF"
        results(head.format("MID") + nan_row)
        assert A.ccx_nonfinite_result(job) == ("job.dat: displacements (vx,vy,vz) for set MID and "
                                               "time 0.1668256E-03: 4 NaN NaN NaN")
        assert classify_ccx_run(0, " *ERROR in e_c3d\n" + ok, "", job) == "failed"
        assert classify_ccx_run(0, " Job finished\n", "", job) == "accepted"   # no STEP ran


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
            assert status in ("accepted", "solved"), \
                f"{e['name']}: mesh-only deck was rejected by ccx ({status!r})"


def eigenvalues(dat_path):
    """The eigenvalues a ccx *FREQUENCY step printed to its .dat file."""
    vals, on = [], False
    for ln in open(dat_path):
        f = ln.split()
        if "E I G E N V A L U E   O U T P U T" in ln:
            on = True
        elif on and len(f) >= 2 and f[0].isdigit():
            vals.append(float(f[1]))
        elif on and vals and not f:
            break
    return vals


def test_hood_hinge_keeps_one_mechanism_mode():
    """marcello_gori_hood_hinge_mechanism, a free-free *FREQUENCY of two hinge brackets
    joined by a CONN3D2 HINGE: 6 rigid-body modes and the hinge's mechanism mode, then
    elastic ones (without the connector all 10 are zero: two free parts, 12 rigid-body
    modes)."""
    name = "marcello_gori_hood_hinge_mechanism"
    ccx, env = V.find_ccx()
    if not ccx or not os.path.exists(os.path.join(FILES, name + ".inp")):
        print("hood-hinge deck or ccx not found — skipping the mechanism check.")
        return
    d = tempfile.mkdtemp()
    try:
        open(os.path.join(d, "job.inp"), "w").write(convert(name)[0])
        fe = dict(os.environ)
        fe.update(env)
        subprocess.run([ccx, "job"], cwd=d, env=fe, capture_output=True, text=True, timeout=300)
        lam = eigenvalues(os.path.join(d, "job.dat"))
    finally:
        shutil.rmtree(d, ignore_errors=True)
    assert len(lam) == 10 and sum(abs(x) < 1.0 for x in lam) == 7 and lam[7] > 1e6, lam


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
            text, rep, conv = convert(name)
        except Exception as exc:  # noqa: BLE001
            print(f"{name:27s} {'CRASH':>5s}  {type(exc).__name__}: {exc}")
            failures += 1
            continue
        d = dangling(text)
        result = "ok"
        if d:
            result = "DANGLING"
            failures += 1
        problem = load_problem(e, conv) if e["expect_solve"] else None
        if problem:
            result = f"LOADS: {problem}"
            failures += 1
        ccxcol = "-"
        if ccx:
            status = run_ccx(ccx, env, text)
            if e["expect_solve"]:
                ccxcol = "SOLVED" if status == "solved" else status.upper()
                if status != "solved":
                    result = {"accepted": "UNEXPECTED: no analysis step ran",
                              "nonfinite": "UNEXPECTED: NaN/Inf results"}.get(
                                  status, "UNEXPECTED no-solve")
                    failures += 1
            elif e.get("parse_only"):
                ccxcol = {"accepted": "ACCEPTED", "solved": "solved+"}.get(status, status.upper())
                if status not in ("accepted", "solved"):
                    result = "UNEXPECTED: ccx rejected it"
                    failures += 1
            else:
                ccxcol = {"solved": "solved+", "accepted": "accepted+",
                          "nonfinite": "nonfinite(ok)"}.get(status, "no-solve(ok)")
        print(f"{name:27s} {'ok':>5s} {rep.n_warnings:>3d} {d:>6d} {ccxcol:>13s}  {result}")
    n_solve = sum(1 for e in decks if e["expect_solve"])
    n_unloaded = sum(1 for e in decks if e["expect_solve"] and e.get("source_unloaded"))
    n_parse = sum(1 for e in decks if e.get("parse_only"))
    print(f"\n{len(decks)} converted, 0 dangling expected; {n_solve} expected to solve under "
          f"the deck's own loads ({n_unloaded} of them load nothing in the source deck), "
          f"{n_parse} mesh-only (no analysis step) expected to be accepted by ccx.")
    print("All corpus checks passed." if not failures else f"{failures} failure(s).")
    print("\n(the remaining decks are source-deck/analysis limitations — see corpus/manifest.py.)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
