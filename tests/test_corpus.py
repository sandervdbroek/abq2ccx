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
                 .frd) — a deck with a matrix generation step must write its matrices
                 instead (``expected_solve``) —, and mesh-only decks marked ``parse_only``
                 must be accepted by ccx; the rest are recorded only.
     ANSWERS   — optional, with ccx: an ``expect_solve`` deck with a ``reference`` (the
                 Abaqus benchmark decks) must give its published answer (see
                 ``reference_check``).
  4. UMAT      — optional: with ABQ2CCX_CCX_SRC naming ccx 2.23's source folder (and the
                 compilers and libraries at hand: docs/testing.md), each deck with a ``umat``
                 recipe, converted with --abaqus-umat, solves in a ccx built with its own UMAT
                 (tools/build_ccx_umat.py, from the sources ``corpus/fetch.py --umat``
                 downloads) under the deck's own loads, and matches its twin or reference.

Usage:
    python corpus/fetch.py          # first, download the decks (network)
    python tests/test_corpus.py     # convert + (if ccx present) solve
    pytest tests/test_corpus.py

If ``corpus/files/`` is empty the corpus checks skip cleanly, so this file is safe to
run without network. The bundled ``examples/`` are exercised by ``test_convert.py``.
"""

import contextlib
import hashlib
import io
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "corpus"))
import abq2ccx as A          # noqa: E402
import validate_with_ccx as V  # noqa: E402  (reuse find_ccx, ccx_job)
from manifest import CORPUS, UMAT_SOURCES  # noqa: E402

FILES = os.path.join(ROOT, "corpus", "files")


def _opt(abaqus_umat=False):
    return type("O", (), {"solid_dof": False, "abaqus_umat": abaqus_umat})()


def present():
    return [e for e in CORPUS if os.path.exists(os.path.join(FILES, e["name"] + ".inp"))]


def convert(name, abaqus_umat=False, path=None):
    """The converted deck text, its report and the converter (for its load audit); ``path``:
    another deck than the corpus deck ``name``."""
    rep = A.Report()
    blocks = A.read_blocks(path or os.path.join(FILES, name + ".inp"), rep)
    conv = A.Converter(rep, _opt(abaqus_umat))
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


def expected_solve(text):
    """The verdict an expect_solve deck's conversion ``text`` must get from ccx: "matrices"
    where it has a matrix generation step (*FREQUENCY, SOLVER=MATRIXSTORAGE: ccx writes the
    matrices and stops, abq2ccx.ccx_matrices), else "solved"."""
    cards = (ln.upper().replace(" ", "") for ln in text.splitlines() if ln.startswith("*"))
    return "matrices" if any(c.startswith("*FREQUENCY,") and "SOLVER=MATRIXSTORAGE" in c
                             for c in cards) else "solved"


def run_ccx(ccx, env, text, read=None, timeout=300):
    """The solve judge's verdict on ``text`` in ccx ("timeout" after ``timeout`` seconds); with
    ``read`` (a function of the job path without its extension, run on the result files before
    they are deleted) the pair (verdict, what it returns): None when the job did not solve, the
    exception when the results do not hold what it reads."""
    d = tempfile.mkdtemp()
    open(os.path.join(d, "job.inp"), "w", encoding="utf-8", newline="\n").write(text)
    try:
        status = V.ccx_job(ccx, env, d, timeout).status(os.path.join(d, "job"))
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


def test_fetch_companions():
    """corpus/fetch.py fetches the files a deck's cards read with INPUT= from next to it (a
    nested one next to its includer if not next to the deck), never outside the corpus
    directory, and reports a name two decks need with different contents (offline: a fake
    download)."""
    import fetch as F
    deck = ('*NODE, NSET=N,\n INPUT=nodes.inp\n*INCLUDE, INPUT="sub/mesh.inp"\n'
            '** *INCLUDE, INPUT=no.inp\n*INCLUDE, INPUT=../up.inp\n')
    assert F.input_names(deck) == ["nodes.inp", "sub/mesh.inp", "../up.inp"]
    files = {"https://x/d/nodes.inp": b"1, 0., 0.\n", "https://x/d/sub/mesh.inp":
             b"*INCLUDE, INPUT=els.inp\n", "https://x/d/sub/els.inp": b"*ELEMENT\n",
             "https://x/e/nodes.inp": b"2, 0., 0.\n"}
    real, F.download = F.download, lambda url: files[url]
    try:
        with tempfile.TemporaryDirectory() as d:
            written = {}
            reserved = {os.path.join(d, "a.inp"), os.path.join(d, "b.inp")}
            got, miss, clash = F.companions({"name": "a", "url": "https://x/d/a.inp"}, deck, d,
                                            written, reserved)
            assert got == ["nodes.inp", os.path.join("sub", "mesh.inp"), os.path.join("sub", "els.inp")]
            assert len(miss) == 1 and miss[0].startswith("../up.inp") and not clash
            assert open(os.path.join(d, "sub", "els.inp"), "rb").read() == b"*ELEMENT\n"
            got, miss, clash = F.companions({"name": "b", "url": "https://x/e/b.inp"},
                                            "*INCLUDE, INPUT=nodes.inp\n", d, written, reserved)
            assert not got and clash == [os.path.join(d, "nodes.inp")]
    finally:
        F.download = real


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

    # *FREQUENCY, SOLVER=MATRIXSTORAGE (a matrix generation step) writes the matrices and stops:
    # exit 0, and through a pipe no "Job finished" (ccx 2.23's C output is lost), so the judge
    # reads the files: fresh, the .dof's rows node.direction, upper-triangle finite entries
    freq = " STEP            1\n\n Frequency analysis was selected\n\n"
    with tempfile.TemporaryDirectory() as d:
        job = os.path.join(d, "job")

        def write(ext, text):
            open(job + ext, "w", encoding="utf-8", newline="\n").write(text)

        write(".inp", "*STEP\n")
        write(".sti", "1 1  2.0e+02\n1 2 -1.0e+02\n2 2  1.0e+02\n")
        write(".mas", "1 1  3.0e+00\n1 2  0.0e+00\n2 2  3.0e+00\n")
        write(".dof", "2.1\n2.2\n")
        assert A.ccx_matrices(job) == "job.sti, job.mas, job.dof (2 rows)"
        assert classify_ccx_run(0, freq, "", job) == "matrices"
        assert classify_ccx_run(0, freq + " Job finished\n", "", job) == "matrices"
        assert classify_ccx_run(0, freq, "") == "failed"                 # no files to read
        assert classify_ccx_run(201, freq, "", job) == "failed"
        assert classify_ccx_run(0, freq + " *ERROR in arpack\n", "", job) == "failed"
        assert classify_ccx_run(0, "", "", job) == "failed"              # no STEP ran
        write(".mas", "1 1  3.0e+00\n2 2  nan\n")
        assert A.ccx_matrices(job) is None and classify_ccx_run(0, freq, "", job) == "failed"
        write(".mas", "1 1  3.0e+00\n2 5  1.0e+00\n")                 # column 5 of 2 (x2: cyclic)
        assert classify_ccx_run(0, freq, "", job) == "failed"
        os.unlink(job + ".mas")
        assert A.ccx_matrices(job) == "job.sti, job.dof (2 rows)"
        write(".dof", "2.1\nx\n")
        assert A.ccx_matrices(job) is None
        write(".dof", "2.1\n2.2\n")
        os.utime(job + ".sti", (1.0, 1.0))                              # an earlier run's
        assert A.ccx_matrices(job) is None and classify_ccx_run(0, freq, "", job) == "failed"


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
            text = convert(e["name"])[0]
            status, want = run_ccx(ccx, env, text), expected_solve(text)
            assert status == want, f"{e['name']}: expected {want!r} from ccx, got {status!r}"
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


# --- the UMAT tier ----------------------------------------------------------------
# A deck's ``umat`` recipe (corpus/manifest.py): its UMAT's pinned sources (UMAT_SOURCES), the
# files to build and how, and a twin or reference its ccx results must match.

UMAT_FILES = os.path.join(FILES, "umat")
UMAT_KEYS = {"repo", "build", "fflags", "patch", "stretch", "uexternaldb", "reduced_physics",
             "twin", "reference"}
UMAT_TIMEOUT = 900          # seconds per ccx run (the crystal-plasticity deck: 160 s here)


def umat_root(repo):
    """The folder corpus/fetch.py --umat saves repository ``repo``'s pinned files in."""
    return os.path.join(UMAT_FILES, repo.replace("/", "__"))


def umat_missing(u):
    """Why the sources of recipe ``u`` cannot be built (a file missing, or not the pinned
    one), or None.  Checked right before they are compiled."""
    for path, sha in UMAT_SOURCES[u["repo"]]["files"].items():
        local = os.path.join(umat_root(u["repo"]), *path.split("/"))
        if not os.path.exists(local):
            return f"{u['repo']}/{path} not fetched (python corpus/fetch.py --umat)"
        with open(local, "rb") as fh:
            if hashlib.sha256(fh.read()).hexdigest() != sha:
                return f"{local}: not the pinned file (its sha256 differs)"
    return None


def umat_twin_text(e):
    """The source text of deck ``e``'s twin: the corpus deck it names, or the deck with its
    ``edit`` replacements, each of whose text occurs once."""
    twin = e["umat"]["twin"]
    name = twin.get("deck", e["name"])
    with open(os.path.join(FILES, name + ".inp"), encoding="latin-1", newline="") as fh:
        text = fh.read().replace("\r\n", "\n")
    for old, new in twin.get("edit", ()):
        if text.count(old) != 1:
            raise ValueError(f"twin edit {old[:40]!r} occurs {text.count(old)} times, not once")
        text = text.replace(old, new)
    return text


def last_results(job):
    """{name: {node: values}} of the last DISP and STRESS blocks of ``job``.frd."""
    last = {name: off for _, _, name, off in A.frd_index(job + ".frd") if name in ("DISP", "STRESS")}
    return {name: dict(A.frd_rows(job + ".frd", off)) for name, off in last.items()}


def twin_difference(got, want):
    """{name: the largest difference over the largest value of ``want``} of the DISP and STRESS
    blocks (last_results) both have, on their common nodes."""
    out = {}
    for name, k in (("DISP", 3), ("STRESS", 6)):
        common = set(got.get(name, ())) & set(want.get(name, ()))
        if common:
            scale = max(abs(x) for n in common for x in want[name][n][:k]) or 1.0
            out[name] = max(abs(x - y) for n in common
                            for x, y in zip(got[name][n][:k], want[name][n][:k])) / scale
    return out


def umat_reference_deviations(job, ref, repo):
    """[(time, relative deviation)] of the total force of set ``ref["set"]`` along
    ``direction`` (*NODE PRINT TOTALS blocks of ``job``.dat, one per increment, interpolated) from
    the ``curve`` (time, force) of source repository ``repo``, at the curve's points ccx covers."""
    with open(os.path.join(umat_root(repo), *ref["curve"].split("/")), encoding="utf-8") as fh:
        curve = [tuple(map(float, ln.split()[:2])) for ln in fh if ln.strip()]
    got = [(0.0, 0.0)] + [(t, rows[0][ref["direction"] - 1]) for _, title, nset, t, rows
                          in A.dat_blocks(job + ".dat") if title == "total force"
                          and nset == ref["set"] and rows]
    out = []
    for x, want in curve:
        if 0 < x <= got[-1][0] + 1e-12:
            i = next(i for i in range(1, len(got)) if got[i][0] >= x - 1e-12)
            (t0, f0), (t1, f1) = got[i - 1], got[i]
            out.append((x, abs(f0 + (f1 - f0) * (x - t0) / (t1 - t0) - want) / abs(want)))
    if not out:
        raise ValueError(f"no total force of set {ref['set']} in the .dat")
    return out


def reference_tolerance(ref, x):
    """The tolerance of ``ref`` at time ``x``: ``tol``, or the ``knee``'s (start, end, tol)."""
    knee = ref.get("knee")
    return knee[2] if knee and knee[0] <= x <= knee[1] else ref["tol"]


def reference_verdict(ref, devs):
    """(line, why) for the deviations ``devs`` (umat_reference_deviations): why is None when
    each is within its tolerance."""
    tols = [reference_tolerance(ref, x) for x, _ in devs]
    groups = {}
    for (x, d), tol in zip(devs, tols):
        groups[tol] = max(groups.get(tol, 0.0), d)
    line = f"the source repository's curve at {len(devs)} points: " + ", ".join(
        f"{d:.2%} off at most{' at the yield knee' if tol != ref['tol'] else ''}"
        for tol, d in groups.items())
    bad = [(x, d, tol) for (x, d), tol in zip(devs, tols) if d > tol]
    return line, (f"{line}; {bad[0][1]:.2%} at time {bad[0][0]:g}, tolerance {bad[0][2]:.1%}"
                  if bad else None)


def umat_tier(echo=print):
    """Build and run the UMAT tier: a list of problems (empty: every deck passed), each deck's
    result echoed as it comes.  None when ABQ2CCX_CCX_SRC is not set."""
    src = os.environ.get("ABQ2CCX_CCX_SRC")
    if not src:
        return None
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import build_ccx_umat as B
    prefix = os.environ.get("CONDA_PREFIX")
    if not prefix:
        return ["ABQ2CCX_CCX_SRC is set, but no conda environment with ccx's libraries is active"]
    env = {"OMP_NUM_THREADS": "1"}      # ccx's threads would overrun with a UMAT's large locals
    problems, built = [], {}
    with tempfile.TemporaryDirectory(prefix="umat-tier-") as bin_dir:
        for e in sorted((e for e in CORPUS if e.get("umat")), key=lambda x: x["name"]):
            u, name = e["umat"], e["name"]
            why = (umat_missing(u) or (None if os.path.exists(os.path.join(FILES, name + ".inp"))
                                       else f"{name}.inp not fetched"))
            if why:
                echo(f"SKIP  {name}: {why}")
                continue
            key = repr([u.get(k) for k in ("repo", "build", "fflags", "patch", "stretch",
                                           "uexternaldb")])
            if key not in built:
                files = [os.path.join(umat_root(u["repo"]), *p.split("/")) for p in u["build"]]
                try:
                    built[key] = B.build(files, os.path.join(bin_dir, f"ccx{len(built)}"), src,
                                         prefix, fflags=u.get("fflags", "").split(),
                                         patches=u.get("patch", ()), stretch=u.get("stretch", False),
                                         uexternaldb=u.get("uexternaldb", False), echo=lambda m: None)
                except B.BuildError as exc:
                    built[key] = exc
            ccx = built[key]
            if isinstance(ccx, Exception):
                problems.append(f"{name}: the build failed: {ccx}")
                echo(f"FAIL  {name}: the build failed")
                continue
            text, _, conv = convert(name, abaqus_umat=True)
            reduced = [x for x in conv.reduced_physics if not x.startswith("*USER MATERIAL")]
            why = load_problem({}, conv) or (
                f"the conversion drops {'; '.join(reduced)}: flag it reduced_physics" if reduced
                and not u.get("reduced_physics") else "reduced_physics is set, but the conversion "
                "drops nothing else" if u.get("reduced_physics") and not reduced else None)
            if why:
                problems.append(f"{name}: {why}")
                echo(f"FAIL  {name}: {why}")
                continue
            ref, line = u.get("reference"), "solved"
            if ref:
                cut = text.upper().index("*END STEP")
                text = text[:cut] + ref["output"] + "\n" + text[cut:]
            status, got = run_ccx(ccx, env, text, last_results if not ref else
                                  lambda job: umat_reference_deviations(job, ref, u["repo"]), UMAT_TIMEOUT)
            if status != "solved" or isinstance(got, Exception):
                why = f"expected 'solved' from ccx, got {status!r}" + (f" ({got})" if got else "")
            elif ref:
                line, why = reference_verdict(ref, got)
            elif u.get("twin"):
                try:
                    tpath = os.path.join(bin_dir, "twin.inp")
                    with open(tpath, "w", encoding="latin-1", newline="\n") as fh:
                        fh.write(umat_twin_text(e))
                    tstatus, want = run_ccx(ccx, env, convert(name, True, tpath)[0], last_results,
                                            UMAT_TIMEOUT)
                except ValueError as exc:
                    tstatus, want = f"not made: {exc}", None
                diff = twin_difference(got, want) if tstatus == "solved" and \
                    not isinstance(want, Exception) else {}
                tol = u["twin"].get("tol", 1e-6)
                line = "twin: " + ", ".join(f"{k} {v:.1e} off" for k, v in diff.items())
                why = (f"its twin did not solve ({tstatus})" if tstatus != "solved" else
                       "no displacements to compare with the twin" if "DISP" not in diff else
                       f"{line}; tolerance {tol:g}" if max(diff.values()) > tol else None)
            else:
                why = None
            if why:
                problems.append(f"{name}: {why}")
            echo(f"{'FAIL' if why else 'PASS'}  {name}: {why or line}")
    return problems


def test_umat_manifest():
    """Every ``umat`` recipe names pinned sources, files among them, known keys and a twin or
    reference that can be read; it sits on a deck that stops on a stock ccx (no expectation
    of its own).  Offline."""
    names = {e["name"] for e in CORPUS}
    for repo, s in UMAT_SOURCES.items():
        assert len(s["sha"]) == 40 and int(s["sha"], 16) >= 0, repo
        for path, sha in s["files"].items():
            assert not path.startswith("/") and ".." not in path.split("/") and ":" not in path, path
            assert len(sha) == 64 and int(sha, 16) >= 0, path
    used = set()
    for e in CORPUS:
        u = e.get("umat")
        if not u:
            continue
        assert set(u) <= UMAT_KEYS, f"{e['name']}: unknown keys {set(u) - UMAT_KEYS}"
        assert not e["expect_solve"] and not e.get("parse_only"), e["name"]
        files = UMAT_SOURCES[u["repo"]]["files"]
        assert u["build"] and all(f in files for f in u["build"]), e["name"]
        assert bool(u.get("twin")) + bool(u.get("reference")) <= 1, e["name"]
        if u.get("twin"):
            assert u["twin"].get("deck", e["name"]) in names, e["name"]
            assert set(u["twin"]) <= {"deck", "edit", "tol"}, e["name"]
        if u.get("reference"):
            assert u["reference"]["curve"] in files, e["name"]
        used.add(u["repo"])
    assert used == set(UMAT_SOURCES), f"sources no recipe uses: {set(UMAT_SOURCES) - used}"


def test_fetch_unknown_option():
    """corpus/fetch.py prints its usage and downloads nothing for an argument it does not
    know (``--help`` once started the full download over corpus/files/)."""
    import fetch as F
    calls = []
    real, F.download = F.download, calls.append
    try:
        for argv in (["--help"], ["-h"], ["--companion"], ["--umat", "--companions"]):
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                assert F.main(argv) == 2, argv
            assert "--companions" in err.getvalue() and not calls, argv
    finally:
        F.download = real


def test_fetch_umat():
    """corpus/fetch.py --umat saves a pinned file at its path, keeps one that is already there,
    and saves no file whose sha256 differs (offline: a fake download)."""
    import fetch as F
    good, bad = b"      SUBROUTINE UMAT\n", b"      SUBROUTINE OTHER\n"
    src = dict(sha="0" * 40, files={"src/umat.f": hashlib.sha256(good).hexdigest(),
                                     "b.f": hashlib.sha256(good).hexdigest(), "../x.f": "0" * 64})
    calls = []

    def fake(url):
        calls.append(url)
        return good if url.endswith("/src/umat.f") else bad
    real, F.download = F.download, fake
    try:
        with tempfile.TemporaryDirectory() as d:
            got, failed = F.umat_files("o/r", src, d)
            assert got == ["src/umat.f"] and len(failed) == 2, (got, failed)
            assert calls[-1] == "https://raw.githubusercontent.com/o/r/" + "0" * 40 + "/src/umat.f"
            assert open(os.path.join(d, "o__r", "src", "umat.f"), "rb").read() == good
            assert not os.path.exists(os.path.join(d, "o__r", "b.f"))
            n = len(calls)
            assert F.umat_files("o/r", dict(src, files={"src/umat.f": src["files"]["src/umat.f"]}),
                                d) == ([], []) and len(calls) == n
    finally:
        F.download = real


def test_build_ccx_umat_errors():
    """tools/build_ccx_umat.py names a --src that is no folder, and checks every --patch regex
    before the base build that takes minutes (both raised tracebacks: code check R2-6)."""
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import build_ccx_umat as B
    with tempfile.TemporaryDirectory() as d:
        umat = os.path.join(d, "u.f")
        with open(umat, "w") as fh:
            fh.write("      SUBROUTINE UMAT\n      END\n")
        for src in (os.path.join(d, "none"), umat):
            try:
                B.build([umat], os.path.join(d, "ccx"), src, d, cache=d)
            except B.BuildError as exc:
                assert "is not ccx's source folder" in str(exc), exc
            else:
                raise AssertionError(src)
        try:
            B.build([umat], os.path.join(d, "ccx"), os.path.join(d, "none"), d, cache=d,
                    patches=[("([", "x")])
        except B.BuildError as exc:
            assert str(exc).startswith("--patch '(['"), exc
        else:
            raise AssertionError("bad regex")
        assert os.listdir(d) == ["u.f"], os.listdir(d)       # nothing built or cached


def test_corpus_umat():
    """The UMAT tier (umat_tier): with ABQ2CCX_CCX_SRC set, each deck with a ``umat`` recipe
    solves in a ccx built with its own UMAT and matches its twin or reference."""
    problems = umat_tier()
    if problems is None:
        print("ABQ2CCX_CCX_SRC not set — skipping the UMAT tier (docs/testing.md).")
        return
    assert not problems, "UMAT tier:\n" + "\n".join(problems)


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
                want = expected_solve(text)
                ccxcol = want.upper() if status == want else status.upper()
                if status != want:
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
                ccxcol = {"solved": "solved+", "accepted": "accepted+", "matrices": "matrices+",
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
    tier = umat_tier(lambda m: print("  " + m))
    if tier is not None:
        print(f"\nUMAT tier: {len(tier)} problem(s)" + "".join(f"\n  {p}" for p in tier))
        failures += len(tier)
    print("All corpus checks passed." if not failures else f"{failures} failure(s).")
    print("\n(the remaining decks are source-deck/analysis limitations — see corpus/manifest.py.)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
