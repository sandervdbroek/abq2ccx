#!/usr/bin/env python3
"""Corpus test suite: run the converter against a set of real-world Abaqus decks.

Two layers of checking:
  1. CONVERT   — every deck converts without crashing and the result is referentially
                 consistent (every element node / set member resolves). Always runs.
  2. LOADS     — decks marked ``expect_solve`` must keep a load in every step the Abaqus
                 deck loads (else ccx "solves" that step with no load at all), and
                 ``source_unloaded`` must flag exactly the decks that load no step. Always
                 runs.
     FIDELITY  — ``reduced_physics`` must flag exactly the ``expect_solve`` decks whose
                 conversion drops or replaces part of the Abaqus model (a constitutive
                 behaviour, an element formulation, a constraint, a load ...:
                 ``Converter.reduced_physics``), so no deck counts as a faithful solve while
                 the converter drops its physics; ``solver_differs`` (a ccx solution found
                 not to be the deck's) sits only on ``expect_solve`` decks. Always runs.
  3. SOLVE     — optional: if CalculiX (ccx) is found, decks marked ``expect_solve``
                 must solve (ccx exits 0, prints "Job finished" with no *ERROR and no
                 crash, runs an analysis STEP, and writes no NaN/Inf to the .dat or
                 .frd), and mesh-only decks marked ``parse_only`` must be accepted by
                 ccx; the rest are recorded only.
     ANSWERS   — optional, with ccx: an ``expect_solve`` deck with a ``reference`` (the
                 Abaqus benchmark decks) must give its published answer (see
                 ``reference_check``).

Usage:
    python corpus/fetch.py          # first, download the decks (network)
    python tests/test_corpus.py     # convert + (if ccx present) solve
    pytest tests/test_corpus.py

If ``corpus/files/`` is empty the corpus checks skip cleanly, so this file is safe to
run without network. The bundled ``examples/`` are exercised by ``test_convert.py``.
"""

import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "corpus"))
import abq2ccx as A          # noqa: E402
import validate_with_ccx as V  # noqa: E402  (reuse find_ccx, ccx_job)
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


def fidelity_problem(e, conv):
    """Why an expect_solve deck's ``reduced_physics`` flag disagrees with its conversion, or
    None: a conversion that drops or replaces part of the Abaqus model must be flagged (it is
    then left out of the count of faithful solves), and only such a conversion."""
    if conv.reduced_physics and not e.get("reduced_physics"):
        return (f"the conversion drops or replaces {'; '.join(conv.reduced_physics)}: flag it "
                f"reduced_physics")
    if e.get("reduced_physics") and not conv.reduced_physics:
        return "reduced_physics is set, but the conversion keeps the deck's physics"
    return None


def dangling(text):
    rep = A.Report()
    fd, p = tempfile.mkstemp(suffix=".inp")
    os.close(fd)
    open(p, "w", encoding="utf-8", newline="\n").write(text)
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


def run_ccx(ccx, env, text, read=None):
    """The solve judge's verdict on ``text`` in ccx; with ``read`` (a function of the job path
    without its extension, run on the result files before they are deleted) the pair
    (verdict, what it returns): None when the job did not solve, the exception when the
    results do not hold what it reads."""
    d = tempfile.mkdtemp()
    open(os.path.join(d, "job.inp"), "w", encoding="utf-8", newline="\n").write(text)
    try:
        status = V.ccx_job(ccx, env, d, 300).status(os.path.join(d, "job"))   # "timeout" after 300 s
        if read is None:
            return status
        if status != "solved":
            return status, None
        try:
            return status, read(os.path.join(d, "job"))
        except (OSError, LookupError, ValueError) as exc:
            return status, exc
    finally:
        shutil.rmtree(d, ignore_errors=True)


# --- published answers ----------------------------------------------------------
# A deck's ``reference`` (corpus/manifest.py) names a quantity of the deck's ccx results by
# ``read``, read through the shared .frd / .dat readers (abq2ccx.frd_index / frd_rows /
# dat_blocks, and validate_with_ccx.py's on top of them):
#   ("stress", (dx, dy, dz), node)   normal stress along the direction at a node of the last
#                                    .frd STRESS block (nodal, extrapolated and averaged by
#                                    ccx); the node as a number, or as a point: the nearest
#                                    .frd node (shells and beams are expanded in the .frd)
#   ("temp", node)                   temperature of the last .frd NDTEMP block
#   ("freq", (mode, ...))            eigenfrequencies (cycles/time) of the .dat
#   ("mises", (node, ...), (t, ...)) von Mises stress of the .frd STRESS block at each total
#                                    time, for each node
#   ("ipstress", ((elem, ip, k), ...), (t, ...))   .dat *EL PRINT stress component k (sxx,
#                                    syy, szz, sxy, sxz, syz) at an integration point, at each
#                                    total time
#   ("disp", node, ((dx, dy, dz), ...), (t, ...))   .dat *NODE PRINT displacement of a node
#                                    along each direction, at each total time (a beam's own
#                                    node, which the expanded .frd lacks)

def frd_nodes(frd_path):
    """{node: (x, y, z)} of the node block of a ccx .frd file."""
    for _, _, name, off in A.frd_index(frd_path):
        if name == "NODES":
            return {n: tuple(v[:3]) for n, v in A.frd_rows(frd_path, off)}
    return {}


def dat_ip_stresses(dat_path):
    """[(time, {(element, integration point): [sxx, syy, szz, sxy, sxz, syz]})] of every
    stress table *EL PRINT wrote to a ccx .dat file."""
    return [(t, {(int(r[0]), int(r[1])): r[2:] for r in rows if len(r) == 8})
            for _, title, _, t, rows in A.dat_blocks(dat_path) if title == "stresses"]


def dat_displacements(dat_path):
    """[(time, {node: [ux, uy, uz]})] of every displacement table *NODE PRINT wrote to a ccx
    .dat file."""
    return [(t, {int(r[0]): r[1:4] for r in rows if len(r) >= 4})
            for _, title, _, t, rows in A.dat_blocks(dat_path) if title == "displacements"]


def _at(blocks, t):
    """The last of [(time, data)] at total time ``t``."""
    hit = [b for tb, b in blocks if abs(tb - t) <= 1e-6 * max(1.0, abs(t))]
    if not hit:
        raise KeyError(f"no output at time {t}")
    return hit[-1]


def reference_values(job, read):
    """The values ``read`` names in the ccx results of ``job`` (its path without extension)."""
    kind = read[0]
    if kind == "freq":
        f = V.dat_eigen_table(job + ".dat", "E I G E N V A L U E   O U T P U T")
        return [f[m - 1] for m in read[1]]
    if kind == "temp":
        return [V.frd_blocks(job + ".frd", "NDTEMP")[-1][1][read[1]][0]]
    if kind == "stress":
        d, node = read[1], read[2]
        if not isinstance(node, int):
            xyz = frd_nodes(job + ".frd")
            node = min(xyz, key=lambda n: sum((a - b) ** 2 for a, b in zip(xyz[n], node)))
        sxx, syy, szz, sxy, syz, szx = V.frd_blocks(job + ".frd", "STRESS")[-1][1][node]
        t = [[sxx, sxy, szx], [sxy, syy, syz], [szx, syz, szz]]
        return [sum(d[i] * t[i][j] * d[j] for i in range(3) for j in range(3)) /
                sum(x * x for x in d)]
    if kind == "mises":
        blocks = V.frd_blocks(job + ".frd", "STRESS")
        out = []
        for node in read[1]:
            for tt in read[2]:
                sxx, syy, szz, sxy, syz, szx = _at(blocks, tt)[node]
                out.append((0.5 * ((sxx - syy) ** 2 + (syy - szz) ** 2 + (szz - sxx) ** 2) +
                            3.0 * (sxy ** 2 + syz ** 2 + szx ** 2)) ** 0.5)
        return out
    if kind == "ipstress":
        tables = dat_ip_stresses(job + ".dat")
        return [_at(tables, tt)[(el, ip)][k] for tt in read[2] for el, ip, k in read[1]]
    if kind == "disp":
        node = read[1]
        tables = [(t, u[node]) for t, u in dat_displacements(job + ".dat") if node in u]
        return [sum(a * b for a, b in zip(_at(tables, tt), d)) / sum(x * x for x in d) ** 0.5
                for tt in read[3] for d in read[2]]
    raise ValueError(f"unknown reference read {kind!r}")


def reference_check(e, values):
    """(verdict, line) for a deck's ``reference`` and the values ccx gave (divided by
    ``unit``, as published).  Each value must be within ``tol`` (relative) of its yardstick:
    Abaqus' published result for the deck's mesh (``abaqus``), or ``ccx`` where the manifest
    records that ccx gives another answer, with ``why`` (traced to ccx, not to the conversion;
    the line then also says how far it is from Abaqus).  "PASS", "DIFFERS" (an explained ccx
    difference reproduced) or "MISS"."""
    ref = e["reference"]
    listify = lambda x: list(x) if isinstance(x, (list, tuple)) else [x]
    abaqus, target = listify(ref["abaqus"]), listify(ref["target"])
    yard = listify(ref.get("ccx", ref["abaqus"]))
    tol = ref["tol"]
    if not isinstance(values, list) or len(values) != len(yard):
        return "MISS", f"{e['name']}: {ref['quantity']}: no value read ({values!r})"
    values = [v / ref.get("unit", 1.0) for v in values]          # e.g. Pa -> the MPa published
    dev = lambda got, want: max(abs(g - w) / abs(w) for g, w in zip(got, want))
    fmt = lambda xs: ", ".join(f"{x:.5g}" for x in xs)
    line = (f"{e['name']}: {ref['quantity']}: ccx {fmt(values)}; Abaqus {fmt(abaqus)} "
            f"({dev(values, abaqus):.2%} off); NAFEMS {fmt(target)} ({dev(values, target):.2%} off)")
    if "ccx" in ref and dev(values, abaqus) <= tol:
        return "MISS", line + "; within tolerance of Abaqus now: drop the reference's ccx/why"
    if dev(values, yard) > tol:
        return "MISS", line + (f"; expected ccx {fmt(yard)} within {tol:.1%}"
                               if "ccx" in ref else f"; tolerance {tol:.1%}")
    if "ccx" in ref:
        return "DIFFERS", line + f"; ccx differs: {ref['why']}"
    return "PASS", line


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


def test_corpus_fidelity():
    """expect_solve decks whose conversion drops or replaces part of the Abaqus model (a
    constitutive behaviour, an element formulation, a constraint, a load ...) carry
    ``reduced_physics`` — they still solve, but not the deck's own problem — and no other
    deck does."""
    stray = [e["name"] for e in CORPUS if e.get("solver_differs") and not e["expect_solve"]]
    assert not stray, f"solver_differs on decks that are not expect_solve: {stray}"
    decks = [e for e in present() if e["expect_solve"]]
    if not decks:
        print("corpus/files/ is empty — run 'python corpus/fetch.py' to enable corpus tests.")
        return
    for e in sorted(decks, key=lambda x: x["name"]):
        problem = fidelity_problem(e, convert(e["name"])[2])
        assert problem is None, f"{e['name']}: {problem}"


def test_classify_ccx_run():
    """The solve judge itself (no ccx needed)."""
    ok = (" STEP            1\n\n Static analysis was selected\n\n Determining the structure of "
          "the matrix:\n number of equations\n 24\n\n Job finished\n")
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
    assert classify_ccx_run(0, ok.replace(" Job", " no convergence\n Job"), "") == "solved"

    # A step that sets up no system of equations also ends with "Job finished" and exit 0:
    # ccx 2.23 skips the matrix structure in a *DYNAMIC step whose kinematic couplings chain
    # no MPCs, and every free DOF keeps its initial value.  Each step must show the
    # structure of its matrix or its number of equations.  Lines as ccx 2.23 writes them to
    # a pipe (a *STATIC step, then that *DYNAMIC step), cut down.
    static = (" STEP            1\n\n Static analysis was selected\n\n Decascading the MPC's\n\n"
              " Determining the structure of the matrix:\n Using up to 1 cpu(s) for setting up "
              "the structure of the matrix.\n number of equations\n 13\n number of nonzero lower "
              "triangular matrix elements\n 78\n\n Factoring the system of equations using the "
              "symmetric spooles solver\n\n")
    idle = (" STEP            2\n\n Dynamic analysis was selected\n\n Newton-Raphson iterative "
            "procedure is active\n\n Decascading the MPC's\n\n Using up to 1 cpu(s) for the "
            "stress calculation.\n\n increment 1 attempt 1 \n increment size= 1.000000e-02\n\n"
            " iteration 1\n\n average force= 0.641026\n time avg. forc= 0.641026\n largest "
            "residual force= 0.000000 in node 1 and dof 0\n largest increment of disp= "
            "0.000000e+00\n largest correction to disp= 0.000000e+00\n\n convergence\n\n")
    end = " Job finished\n\n"
    assert classify_ccx_run(0, static + idle + end, "") == "unsolved"
    assert A.ccx_unsolved_steps(static + idle + end) == [2]
    assert classify_ccx_run(0, idle.replace("2\n", "1\n", 1) + end, "") == "unsolved"
    # the same step with its system set up solves
    solved = idle.replace(" Using", " Determining the structure of the matrix:\n number of "
                                    "equations\n 12\n\n Using", 1)
    assert classify_ccx_run(0, static + solved + end, "") == "solved"
    # every DOF prescribed: 0 equations, and the response to the prescribed values
    assert classify_ccx_run(0, ok.replace(" 24\n", " 0\n"), "") == "solved"
    # *GREEN and *SUBSTRUCTURE GENERATE print the number of equations only
    assert classify_ccx_run(0, " STEP            1\n\n Decascading the MPC's\n\n number of "
                               "equations\n 36\n\n" + end, "") == "solved"
    # explicit: the structure of the (mass) matrix; the step that sets up none still prints
    # "Explicit time integration"
    explicit = (" STEP            1\n\n Dynamic analysis was selected\n\n Newton-Raphson iterative "
                "procedure is active\n\n Decascading the MPC's\n\n Determining the structure of "
                "the matrix:\n Using up to 1 cpu(s) for setting up the structure of the matrix.\n"
                "\n Calculating Material Wave Speeds...\n\n Explicit time integration: "
                "Volumetric COURANT initial stable time increment:4.575976e-04\n\n")
    assert classify_ccx_run(0, explicit + end, "") == "solved"
    no_structure = explicit.replace(" Determining the structure of the matrix:\n Using up to 1 "
                                    "cpu(s) for setting up the structure of the matrix.\n", "")
    assert classify_ccx_run(0, no_structure + end, "") == "unsolved"

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
                    open(job + ext, "w", encoding="utf-8", newline="\n").write(text)
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
        # a Windows build whose printf is the UCRT's (conda-forge's): -NAN(IND) for 0/0
        assert results(None, " 1.00000E+00   -NAN(IND) 0.00000E+00") == "nonfinite"
        # a Windows build whose printf is msvcrt's: 1.#QNAN, -1.#IND (0/0), 1.#INF
        assert results(None, " 1.00000E+00 1.#QNANE+000 0.00000E+00") == "nonfinite"
        assert results(None, "-1.#IND0E+000 0.00000E+00 0.00000E+00") == "nonfinite"
        assert A.ccx_nonfinite_result(job) == ("job.frd: DISP at 1.66826E-03: 2-1.#IND0E+000 "
                                               "0.00000E+00 0.00000E+00")
        results(head.format("MID") + nan_row)
        assert A.ccx_nonfinite_result(job) == ("job.dat: displacements (vx,vy,vz) for set MID and "
                                               "time 0.1668256E-03: 4 NaN NaN NaN")
        assert classify_ccx_run(0, " *ERROR in e_c3d\n" + ok, "", job) == "failed"
        assert classify_ccx_run(0, " Job finished\n", "", job) == "accepted"   # no STEP ran
        # a step that solved nothing: its results are no solution, finite or not
        assert classify_ccx_run(0, static + idle + end, "", job) == "unsolved"


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
    for ln in open(dat_path, encoding="utf-8"):
        f = ln.split()
        if "E I G E N V A L U E   O U T P U T" in ln:
            on = True
        elif on and len(f) >= 2 and f[0].isdigit():
            vals.append(float(f[1]))
        elif on and vals and not f:
            break
    return vals


def test_corpus_references():
    """expect_solve decks with a ``reference`` (Abaqus' benchmark decks: NAFEMS LE, T, FV, NL)
    give their published answer in ccx (reference_check)."""
    decks = [e for e in present() if e.get("reference") and e["expect_solve"]]
    ccx, env = V.find_ccx()
    if not decks or not ccx:
        print("no reference decks or no ccx found — skipping the answer checks.")
        return
    misses = []
    for e in sorted(decks, key=lambda x: x["name"]):
        status, values = run_ccx(ccx, env, convert(e["name"])[0],
                                 lambda job: reference_values(job, e["reference"]["read"]))
        verdict, line = reference_check(e, values)
        if verdict == "MISS":
            misses.append(f"{line} [{status}]")
    assert not misses, "published answers missed:\n" + "\n".join(misses)


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
        open(os.path.join(d, "job.inp"), "w", encoding="utf-8", newline="\n").write(convert(name)[0])
        V.ccx_job(ccx, env, d, 300)
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
    answers = []
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
        problem = fidelity_problem(e, conv) if e["expect_solve"] else None
        if problem:
            result = f"FIDELITY: {problem}"
            failures += 1
        ccxcol = "-"
        if ccx:
            if e.get("reference") and e["expect_solve"]:
                status, values = run_ccx(ccx, env, text,
                                         lambda job: reference_values(job, e["reference"]["read"]))
                answers.append(reference_check(e, values))
                if answers[-1][0] == "MISS" and status == "solved":
                    result = "ANSWER MISSED (see below)"
                    failures += 1
            else:
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
    n_reduced = sum(1 for e in decks if e["expect_solve"] and e.get("reduced_physics"))
    n_differs = sum(1 for e in decks if e["expect_solve"] and e.get("solver_differs"))
    n_faithful = sum(1 for e in decks if e["expect_solve"] and not e.get("source_unloaded")
                     and not e.get("reduced_physics") and not e.get("solver_differs"))
    n_parse = sum(1 for e in decks if e.get("parse_only"))
    print(f"\n{len(decks)} converted, 0 dangling expected; {n_solve} expected to solve under "
          f"the deck's own loads ({n_unloaded} of them load nothing in the source deck, "
          f"{n_reduced} solve a model with reduced physics, {n_differs} solve to a solution "
          f"that is not the deck's; {n_faithful} faithful solves), "
          f"{n_parse} mesh-only (no analysis step) expected to be accepted by ccx.")
    if answers:
        print(f"\nPublished answers ({sum(v == 'PASS' for v, _ in answers)} match Abaqus, "
              f"{sum(v == 'DIFFERS' for v, _ in answers)} differ for a reason traced to ccx, "
              f"{sum(v == 'MISS' for v, _ in answers)} missed):")
        for verdict, line in answers:
            print(f"  {verdict:7s} {line}")
    print("All corpus checks passed." if not failures else f"{failures} failure(s).")
    print("\n(the remaining decks are source-deck/analysis limitations — see corpus/manifest.py.)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
