#!/usr/bin/env python3
"""End-to-end validation: convert the example decks and actually run them in CalculiX.

This is the proof that the converter produces *runnable, correct* CalculiX input — not
just structurally-valid text.  It auto-detects a ``ccx`` binary (including the one
bundled with FreeCAD) and checks results against reference values: the NAFEMS LE10
stress (also with the pressure carried by surface elements, which ccx does not have),
the tip deflections of circular-, pipe- and box-section cantilevers against beam
theory, a shell plate rigidly coupled to a loaded reference point against the same plate
built from solids, coupled bars whose coupled nodes also carry BCs against the same
constraints written without a coupling, a bar whose rigid end cap carries BCs on its nodes
against the same BCs written on its reference point, circular-section beams with a held
twist and a prescribed rotation against beam theory, a circular-section beam in an explicit
dynamic step against its static deflection, the natural frequencies and buckling loads of
planar (B21) beams with a rectangular and a circular section, per-element *DISTRIBUTION
orientations (a C3D8 plate and a composite S8R panel) against the same models written with
one orientation per element, a clamped beam and plate after a later step's *BOUNDARY,
OP=NEW, the thermal strains of isotropic materials with an orthotropic / anisotropic
expansion (including the engineering shear coefficients of an anisotropic one), a heated
cube and circular-section beam with no initial temperatures, and the loads ccx has no card
for — surface tractions (Cook's membrane, Lame's cylinder) and beam line loads (cantilevers
against beam theory) — applied as consistent nodal forces, also on nodes with a *TRANSFORM
(local axes), which must match the same models without one, *MPC joints, levers and links
against statics, connector elements (JOIN, WELD, BEAM, LINK, HINGE) against those, beam
theory and exact statics — also on nodes with a *TRANSFORM, against the same models without
it (linear and NLGEOM) — velocity / acceleration boundary conditions against their
time integral and the wave they send through a bar, displacement boundary conditions without
an amplitude ramped as Abaqus/Standard ramps them (implicit dynamics, *VISCO, a transient
coupled step) and held as Abaqus/Explicit holds them, while loads keep their procedure's
default (a stepped load overshoots), field and history output requested at
beam nodes (the .frd and .dat values against beam theory), and the field output Abaqus
preselects: a bar in tension with only Abaqus/CAE's *Output, variable=PRESELECT requests,
and a bar impact in an explicit step without any output request (20 output frames, the
free end against 1-D wave theory), CPS4I / CPE4I cantilevers written as C3D8I slabs under
an end couple against beam theory (deflection and stresses), shell pressure on the SPOS and
SNEG faces and element-based against the Navier plate solution (the sign of each), a bare
*KINEMATIC (all DOFs) against *RIGID BODY, and an assembly with a turned instance against
the same model written flat.

    python validate_with_ccx.py

Exits 0 if every available check passes (or ccx is not installed — then it skips with
a clear message), 1 if a check fails.  Requires CalculiX; install it or FreeCAD.
"""

import glob
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
import abq2ccx as A  # noqa: E402

EXAMPLES = os.path.join(ROOT, "examples")


def find_ccx():
    """Return (ccx_path, extra_env) or (None, {})."""
    for name in ("ccx", "ccx_2.23", "ccx_2.22", "ccx_2.21", "ccx_2.20", "CalculiX"):
        p = shutil.which(name)
        if p:
            return p, {}
    candidates = (
        glob.glob("/Applications/FreeCAD*.app/Contents/Resources/bin/ccx")
        + glob.glob("/usr/local/bin/ccx*") + glob.glob("/opt/homebrew/bin/ccx*")
        + glob.glob("/opt/local/bin/ccx*")
    )
    for c in candidates:
        if os.path.isfile(c) and os.access(c, os.X_OK):
            env = {}
            libdir = os.path.join(os.path.dirname(os.path.dirname(c)), "lib")
            if os.path.isdir(libdir):  # FreeCAD bundle: its .dylib/.so live in ../lib
                env["DYLD_FALLBACK_LIBRARY_PATH"] = libdir
                env["LD_LIBRARY_PATH"] = libdir
            return c, env
    return None, {}


def convert(path, out_inp):
    rep = A.Report()
    blocks = A.read_blocks(path, rep)
    conv = A.Converter(rep, type("O", (), {"solid_dof": False})())
    body = conv.convert(blocks)                     # convert first: the header lists warnings
    text = "\n".join(rep.header_comment_lines() + body) + "\n"
    with open(out_inp, "w") as fh:
        fh.write(text)


def run_ccx(ccx, env, inp_path):
    """Run ccx; return (workdir, status, combined output) with status from
    abq2ccx.classify_ccx_run ("solved" / "nonfinite" / "accepted" / "failed")."""
    d = tempfile.mkdtemp(prefix="ccxval_")
    shutil.copy(inp_path, os.path.join(d, "job.inp"))
    full_env = dict(os.environ)
    full_env.update(env)
    try:
        r = subprocess.run([ccx, "job"], cwd=d, env=full_env,
                           capture_output=True, text=True, timeout=600)
        status = A.classify_ccx_run(r.returncode, r.stdout, r.stderr, os.path.join(d, "job"))
        return d, status, r.stdout + r.stderr
    except Exception as exc:  # noqa: BLE001
        return d, "failed", f"failed to launch ccx: {exc}"


def frd_stress(frd_path, node):
    """Extrapolated nodal stress vector at ``node`` from a ccx .frd file, or None."""
    inblock = False
    for ln in open(frd_path):
        if "STRESS" in ln and ln.lstrip().startswith("-4"):
            inblock = True
            continue
        if inblock:
            if ln.startswith(" -3"):
                break
            if ln.startswith(" -1") and int(ln[3:13]) == node:
                return [float(ln[13 + i * 12:13 + (i + 1) * 12]) for i in range(6)]
    return None


def frd_displacement_history(frd_path, node):
    """[(time, (ux, uy, uz))] of every DISP block of a ccx .frd file that lists ``node``,
    and the number of DISP blocks that list no node at all."""
    found, empty, time, inblock, rows = [], 0, None, False, 0
    if not os.path.exists(frd_path):
        return found, empty
    for ln in open(frd_path):
        if ln.startswith("  100C"):
            time = float(ln.split()[2])
        elif ln.startswith(" -4") and ln[5:13].strip() == "DISP":
            inblock, rows = True, 0
        elif inblock and ln.startswith(" -1"):
            rows += 1
            if int(ln[3:13]) == node:
                found.append((time, tuple(float(ln[13 + i * 12:25 + i * 12]) for i in range(3))))
        elif inblock and ln.startswith(" -3"):
            empty += rows == 0
            inblock = False
    return found, empty


def frd_blocks(frd_path, name):
    """[(time, {node: values})] of every .frd result block called ``name`` (DISP, FORC,
    STRESS, TOSTRAIN, VELO ...)."""
    found, time, cur = [], None, None
    if not os.path.exists(frd_path):
        return found
    for ln in open(frd_path):
        if ln.startswith("  100C"):
            time = float(ln[12:24])
        elif ln.startswith(" -4"):
            cur = {} if ln[5:13].strip() == name else None
            if cur is not None:
                found.append((time, cur))
        elif cur is not None and ln.startswith(" -1"):
            n = (len(ln.rstrip()) - 13) // 12
            cur[int(ln[3:13])] = [float(ln[13 + i * 12:25 + i * 12]) for i in range(n)]
        elif ln.startswith(" -3"):
            cur = None
    return found


def dat_displacements(dat_path):
    """{node: [ux, uy, uz]}: the last displacement *NODE PRINT wrote for each node in a ccx
    .dat file (empty if none; a transformed node counts only if printed with GLOBAL=YES)."""
    found, inblock = {}, False
    if not os.path.exists(dat_path):
        return found
    for ln in open(dat_path):
        if ln.strip().startswith("displacements"):
            inblock = True
            continue
        f = ln.split()
        if inblock and len(f) == 4 and f[0].isdigit():
            found[int(f[0])] = [float(x) for x in f[1:]]
        elif inblock and f and not f[0].isdigit():
            inblock = False
    return found


def dat_displacement_history(dat_path, node):
    """Every displacement (ux, uy, uz) printed for ``node`` by *NODE PRINT in a ccx .dat
    file, in order (one per printed increment)."""
    found, inblock = [], False
    if not os.path.exists(dat_path):
        return found
    for ln in open(dat_path):
        if ln.strip().startswith("displacements"):
            inblock = True
            continue
        f = ln.split()
        if inblock and len(f) == 4 and f[0] == str(node):
            found.append([float(x) for x in f[1:]])
        elif inblock and f and not f[0].isdigit():
            inblock = False
    return found


def dat_el_stress(dat_path, elem):
    """Mean stress (sxx, syy, szz, sxy, sxz, syz) over the integration points of ``elem`` in
    the last *EL PRINT stress table of a ccx .dat file, or None."""
    rows, inblock = [], False
    if not os.path.exists(dat_path):
        return None
    for ln in open(dat_path):
        if ln.strip().startswith("stresses"):
            rows, inblock = [], True
            continue
        f = ln.split()
        if inblock and len(f) == 8 and f[0] == str(elem):
            rows.append([float(x) for x in f[2:]])
        elif inblock and f and not f[0].isdigit():
            inblock = False
    return [sum(r[k] for r in rows) / len(rows) for k in range(6)] if rows else None


def dat_eigen_table(dat_path, title):
    """The rows of the first eigenvalue table titled ``title`` in a ccx .dat file: the
    frequencies (cycles/time) under "E I G E N V A L U E   O U T P U T", or the factors
    under "B U C K L I N G   F A C T O R   O U T P U T"."""
    if not os.path.exists(dat_path):
        return []
    rows, inblock = [], False
    for ln in open(dat_path):
        if title in ln:
            inblock = True
            continue
        f = ln.split()
        if not inblock or not f:
            continue
        if f[0].isdigit() and len(f) in (2, 5):
            rows.append(float(f[3] if len(f) == 5 else f[1]))
        elif rows:
            break
    return rows


def dat_displacement(dat_path, node):
    """Last displacement (ux, uy, uz) printed for ``node`` by *NODE PRINT in a ccx .dat
    file, or None."""
    return dat_displacements(dat_path).get(node)


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _unit(a):
    n = math.sqrt(_dot(a, a))
    return tuple(x / n for x in a)


def _rotate(v, e, phi):
    """``v`` turned by ``phi`` about the unit axis ``e`` (Rodrigues)."""
    c, s, ev = math.cos(phi), math.sin(phi), _dot(e, v)
    return tuple(x * c + y * s + z * ev * (1 - c) for x, y, z in zip(v, _cross(e, v), e))


def _solve(a, b):
    """Gaussian elimination with partial pivoting (small dense systems)."""
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(m[r][c]))
        m[c], m[p] = m[p], m[c]
        for r in range(n):
            if r != c and m[r][c]:
                f = m[r][c] / m[c][c]
                m[r] = [x - f * y for x, y in zip(m[r], m[c])]
    return [m[i][n] / m[i][i] for i in range(n)]


def hinge_bodies_reference():
    """Exact small-displacement solution of examples/connector_hinge_bodies.inp: the
    displacements of every node, from the 12 rigid-body unknowns (u, theta of reference
    points 1 and 3), the springs, the loads and the 5 hinge constraints (Lagrange
    multipliers)."""
    x = {1: (0., 0., 0.), 3: (0.2, 0.5, -0.1), 11: (1., 0., 0.), 12: (0., 1.5, 0.),
         13: (0., 0., 2.), 21: (1., 1., 1.), 22: (0.5, -1., 0.7), 23: (-0.4, 0.8, 1.3)}
    ref = {1: 1, 11: 1, 12: 1, 13: 1, 3: 3, 21: 3, 22: 3, 23: 3}
    off = {1: 0, 3: 6}                       # unknowns: u1, theta1, u3, theta3
    axes = [tuple(float(i == k) for i in range(3)) for k in range(3)]

    def row(n, d):                           # u_n,d over the unknowns (rigid-body motion)
        t = [0.0] * 12
        o = off[ref[n]]
        t[o + d] = 1.0
        r = [a - b for a, b in zip(x[n], x[ref[n]])]
        for k in range(3):
            t[o + 3 + k] = _cross(axes[k], r)[d]
        return t
    springs = [(11, 0, 50.), (11, 1, 70.), (11, 2, 30.), (12, 0, 40.), (12, 1, 90.),
               (12, 2, 60.), (13, 0, 80.), (13, 1, 20.), (13, 2, 55.), (21, 1, 25.)]
    stiff = [[0.0] * 12 for _ in range(12)]
    for n, d, k in springs:
        t = row(n, d)
        stiff = [[s + k * ti * tj for s, tj in zip(srow, t)] for srow, ti in zip(stiff, t)]
    force = [0.0] * 12
    for n, d, v in ((22, 0, 1.5), (22, 1, -2.), (22, 2, 0.7), (12, 2, -0.9)):
        force = [f + v * t for f, t in zip(force, row(n, d))]
    for k, m in enumerate((0.3, -0.8, 1.1)):            # moment on reference point 3
        force[9 + k] += m
    a, b = (1., 2., 0.5), (-1., 0.3, 1.)                # orientation AXES
    e1 = _unit(a)
    e3 = _unit(_cross(a, b))
    e2 = _cross(e3, e1)
    cons = []
    for d in range(3):                       # u3 - u1 - theta1 x d = 0
        c = [0.0] * 12
        c[6 + d], c[d] = 1.0, -1.0
        for k in range(3):
            c[3 + k] = -_cross(axes[k], x[3])[d]
        cons.append(c)
    for e in (e2, e3):                       # (theta3 - theta1) . e2 = . e3 = 0
        cons.append([0.0] * 3 + [-v for v in e] + [0.0] * 3 + list(e))
    nc = len(cons)
    q = _solve([stiff[i] + [c[i] for c in cons] for i in range(12)] +
               [c + [0.0] * nc for c in cons], force + [0.0] * nc)
    return {n: tuple(_dot(row(n, d), q[:12]) for d in range(3)) for n in x}


def ground_hinge_reference():
    """(axis, turning angle) of examples/connector_ground_hinge.inp: the angle at which
    the spring's moment about the fixed axis balances M = 6 (bisection)."""
    e1 = _unit((1., 2., 0.5))
    r0 = (0.8, 0.5, 1.1)                     # node 21 from node 3

    def residual(phi):
        r = _rotate(r0, e1, phi)
        force = (0.0, -25.0 * (r[1] - r0[1]), 0.0)
        return 6.0 + _dot(_cross(r, force), e1)
    lo, hi = 0.0, 3.0
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if residual(mid) > 0 else (lo, mid)
    return e1, 0.5 * (lo + hi)


def global_twin(deck):
    """examples/transform_spherical_rigid.inp written without *TRANSFORM: its local loads in
    global components, its partial supports as *EQUATION (e . u = 0) and its rigid body with an
    explicit ROT NODE 101 whose rotation is held about the reference point's local 1 and 2.
    The local axes follow the Abaqus manual ("Transformed coordinate systems"), computed here
    independently of the converter: spherical — 1 radial from the centre a through the node, 2
    = (b - a) x 1 (circumferential), 3 = 1 x 2 (meridional, towards the pole b); cylindrical —
    3 along the axis from a to b, 1 radial from it through the node, 2 = 3 x 1."""
    def unit(v):
        s = math.sqrt(sum(x * x for x in v))
        return [x / s for x in v]

    def cross(p, q):
        return [p[1] * q[2] - p[2] * q[1], p[2] * q[0] - p[0] * q[2], p[0] * q[1] - p[1] * q[0]]

    def spherical(a, b, p):
        e1 = unit([x - y for x, y in zip(p, a)])
        e2 = unit(cross([x - y for x, y in zip(b, a)], e1))
        return e1, e2, cross(e1, e2)

    def cylindrical(a, b, p):
        e3 = unit([x - y for x, y in zip(b, a)])
        q = [x - y for x, y in zip(p, a)]
        e1 = unit([x - sum(s * t for s, t in zip(q, e3)) * z for x, z in zip(q, e3)])
        return e1, cross(e3, e1), e3

    def equation(node, e, taken=()):
        """e . (DOFs 1-3 of node) = 0; the dependent (first) DOF is the one with the largest
        coefficient that another equation on the node has not taken."""
        order = sorted(range(3), key=lambda k: (k + 1 in taken, -abs(e[k])))
        return ["*Equation", "3", ", ".join(f"{node}, {k + 1}, {e[k]!r}" for k in order)]

    xyz = {}
    for ln in deck.split("*Node, nset=ALLN\n")[1].split("*")[0].splitlines():
        f = [float(x) for x in ln.split(",")]
        xyz[int(f[0])] = f[1:]
    sph = lambda n: spherical((2., .5, -1.), (2.3, .7, 2.), xyz[n])        # noqa: E731
    rp = cylindrical((0., -1., -1.), (.4, 1., 0.), xyz[100])
    held = equation(101, rp[0])
    eqs = equation(37, sph(37)[0]) + equation(43, sph(43)[1]) + held + \
        equation(101, rp[1], taken=(int(held[2].split(",")[1]),))
    loads = {33: [-0.5, 0.3, 0.], 39: [0., 0., 0.4], 44: [0.2, -0.1, 0.25]}
    cload = []
    for n, f in loads.items():
        e = sph(n)
        cload += [f"{n}, {k + 1}, {sum(f[i] * e[i][k] for i in range(3))!r}" for k in range(3)]
    cload += [f"RP, {k + 1}, {0.2 * rp[0][k] - 0.15 * rp[2][k]!r}" for k in range(3)]
    cload += [f"RP, {k + 4}, {0.05 * rp[2][k]!r}" for k in range(3)]
    out = re.sub(r"(?m)^\*Transform.*\n.*\n", "", deck)
    out = out.replace("*Rigid Body, ref node=RP, tie nset=FAR\n",
                      "*Node\n101, 3.5, 0.5, 0.5\n*Rigid Body, ref node=RP, rot node=101, tie nset=FAR\n"
                      + "\n".join(eqs) + "\n")
    step = out[out.index("*Boundary\n"):out.index("*Node Print")]
    return out.replace(step, "*Boundary\nCLAMP, 1, 3\n*Cload\n" + "\n".join(cload) + "\n")


def dat_history(dat_path, what, nset):
    """[(time, rows)] of every ``what`` block ("displacements", "total force") that *NODE
    PRINT wrote for ``nset`` in a ccx .dat file; rows are lists of floats (node id dropped)."""
    out, rows = [], None
    for ln in open(dat_path) if os.path.exists(dat_path) else []:
        s = ln.strip()
        if s.startswith(what) and f"for set {nset.upper()} " in s:
            rows = []
            out.append((float(s.split()[-1]), rows))
        elif rows is not None and s:
            f = s.split()
            try:
                vals = [float(x) for x in f]
            except ValueError:
                rows = None
                continue
            rows.append(vals[1:] if len(vals) == 4 and what != "total force" else vals)
    return out


def frd_last(frd_path, name):
    """{node: values} of the last ``name`` block (DISP, STRESS, ...) in a ccx .frd file."""
    last, cur = {}, None
    for ln in open(frd_path) if os.path.exists(frd_path) else []:
        if ln.startswith(" -4"):
            cur = {} if ln.split()[1] == name else None
        elif ln.startswith(" -1") and cur is not None:
            n = (len(ln.rstrip()) - 13) // 12
            cur[int(ln[3:13])] = [float(ln[13 + 12 * i:25 + 12 * i]) for i in range(n)]
        elif ln.startswith(" -3") and cur is not None:
            last, cur = cur, None
    return last


def main():
    ccx, env = find_ccx()
    if not ccx:
        print("CalculiX (ccx) not found — skipping end-to-end validation.")
        print("Install CalculiX or FreeCAD to enable it.")
        return 0
    print(f"Using ccx: {ccx}\n")

    tmp = tempfile.mkdtemp(prefix="ccxconv_")
    failures = 0

    # --- NAFEMS LE10: run and check the benchmark stress -----------------------
    inp = os.path.join(tmp, "le10.inp")
    convert(os.path.join(EXAMPLES, "nle10_thickplate.inp"), inp)
    d, status, out = run_ccx(ccx, env, inp)
    syy = None
    if status != "solved":
        print(f"FAIL  nle10_thickplate did not solve cleanly ({status})")
        print("\n".join(l for l in out.splitlines() if "ERROR" in l or "convergence" in l.lower()))
        failures += 1
    else:
        s = frd_stress(os.path.join(d, "job.frd"), 4013)            # point D = (2,0,0.6)
        syy = s[1] / 1e6 if s else None
        ref = -5.38
        if syy is None:
            print("FAIL  nle10_thickplate: no stress result at point D (node 4013) in the .frd")
            failures += 1
        else:
            ok = abs(syy - ref) / abs(ref) < 0.10
            print(f"{'PASS' if ok else 'FAIL'}  nle10_thickplate (NAFEMS LE10): SYY at point D = "
                  f"{syy:+.3f} MPa (reference {ref:+.2f} MPa, {abs(syy-ref)/abs(ref)*100:.1f}% diff)")
            failures += 0 if ok else 1
    shutil.rmtree(d, ignore_errors=True)

    # --- the same plate, its pressure carried by SFM3D8 surface elements -------------
    # ccx has no surface element: the converter leaves the skin out and applies its load as
    # consistent nodal forces.  The skin's normal points out of the plate, so the pressure on
    # its SPOS side, an element-based P = -p (Abaqus: positive along the element normal) and
    # a TRVEC into the plate are all the face pressure above, which they must reproduce.
    deck = open(os.path.join(EXAMPLES, "nle10_surface_elements.inp")).read()
    face = syy
    for how, load in (("*DSLOAD P on SPOS", "*DSLOAD\n TOP,P,  1.0E6\n"),
                      ("*DLOAD P, element normal", "*DLOAD\n SKIN,P,  -1.0E6\n"),
                      ("*DLOAD TRVEC", "*DLOAD\n SKIN,TRVEC,  1.0E6, 0., 0., -1.\n")):
        src = os.path.join(tmp, "skin_src.inp")
        with open(src, "w") as fh:
            fh.write(deck.replace("*DSLOAD\n TOP,P,  1.0E6\n", load))
        inp = os.path.join(tmp, "skin.inp")
        convert(src, inp)
        d, status, out = run_ccx(ccx, env, inp)
        s = frd_stress(os.path.join(d, "job.frd"), 4013) if status == "solved" else None
        shutil.rmtree(d, ignore_errors=True)
        if s is None or face is None:
            print(f"FAIL  nle10_surface_elements ({how}): no stress at point D ({status})")
            print("\n".join(l for l in out.splitlines() if "ERROR" in l))
            failures += 1
            continue
        ok = abs(s[1] / 1e6 - face) <= 1e-5 * abs(face)
        print(f"{'PASS' if ok else 'FAIL'}  nle10_surface_elements (SFM3D8 skin, {how}): SYY at D = "
              f"{s[1] / 1e6:+.6f} MPa (face pressure {face:+.6f} MPa)")
        failures += 0 if ok else 1

    # --- circular-section cantilever on linear beams: tip deflection vs beam theory --
    # ccx 2.23 rejects linear beams with a circular section, so this checks the B31 -> B32
    # upgrade (midside nodes, node order) and the radius -> diameter conversion together.
    inp = os.path.join(tmp, "beam.inp")
    convert(os.path.join(EXAMPLES, "beam_circ_cantilever.inp"), inp)
    d, status, out = run_ccx(ccx, env, inp)
    ref = -1.0 * 100.0 ** 3 / (3 * 1.0e5 * math.pi / 4)          # -P L^3 / (3 E I), r = 1
    u = dat_displacement(os.path.join(d, "job.dat"), 21) if status == "solved" else None
    if u is None:
        print(f"FAIL  beam_circ_cantilever: no tip displacement ({status})")
        print("\n".join(l for l in out.splitlines() if "ERROR" in l))
        failures += 1
    else:
        ok = abs(u[1] - ref) / abs(ref) < 0.02
        print(f"{'PASS' if ok else 'FAIL'}  beam_circ_cantilever (B31 + CIRC): tip deflection = "
              f"{u[1]:+.4f} (beam theory {ref:+.4f}, {abs(u[1]-ref)/abs(ref)*100:.1f}% diff)")
        failures += 0 if ok else 1
    shutil.rmtree(d, ignore_errors=True)

    # --- pipe and box cantilevers: tip deflections vs beam theory ---------------------
    # ccx 2.23 runs PIPE and BOX sections only on B32R, so this checks the PIPE31 -> B32R
    # (midside nodes) and B32 -> B32R upgrades, and that both codes read the PIPE (outer
    # radius, wall) and BOX (a, b, t1..t4) data alike: the box has a != b and unequal wall
    # pairs and is loaded along y and z, so a swapped a/b or wall pair misses by >= 18 %.
    inp = os.path.join(tmp, "pipebox.inp")
    convert(os.path.join(EXAMPLES, "beam_pipe_box_cantilever.inp"), inp)
    d, status, out = run_ccx(ccx, env, inp)
    pl3_3e = 1.0 * 100.0 ** 3 / (3 * 1.0e5)                     # P L^3 / (3 E)
    i_pipe = math.pi / 4 * (1 - 0.8 ** 4)                        # outer radius 1, wall 0.2
    i11 = (2 * 3 ** 3 - 1.8 * 2.6 ** 3) / 12                     # box bending along local 2 (y)
    i22 = (3 * 2 ** 3 - 2.6 * 1.8 ** 3) / 12                     # box bending along local 1 (z)
    for label, node, cases in (("PIPE31 + PIPE", 21, [("y", 1, i_pipe)]),
                               ("B32 + BOX", 141, [("y", 1, i11), ("z", 2, i22)])):
        u = dat_displacement(os.path.join(d, "job.dat"), node) if status == "solved" else None
        if u is None:
            print(f"FAIL  beam_pipe_box_cantilever ({label}): no tip displacement ({status})")
            print("\n".join(l for l in out.splitlines() if "ERROR" in l))
            failures += 1
            continue
        res = [(axis, u[k], -pl3_3e / inertia) for axis, k, inertia in cases]
        ok = all(abs(v - ref) / abs(ref) < 0.02 for _, v, ref in res)
        print(f"{'PASS' if ok else 'FAIL'}  beam_pipe_box_cantilever ({label}): tip deflection "
              + ", ".join(f"{axis} = {v:+.4f} (beam theory {ref:+.4f}, "
                          f"{abs(v - ref) / abs(ref) * 100:.1f}% diff)" for axis, v, ref in res))
        failures += 0 if ok else 1
    shutil.rmtree(d, ignore_errors=True)

    # --- rigid coupling on shell nodes vs the same plate as solids under *Rigid Body --
    # ccx 2.23 rejects a rigid coupling on shell nodes that are not knots, so this checks the
    # knot beams and the rotation ties together (without the ties a moment about the edge
    # line finds the edge hinged) against a model ccx accepts unchanged.
    u = {}
    for name in ("coupling_shell_plate", "coupling_solid_plate"):
        inp = os.path.join(tmp, name + ".inp")
        convert(os.path.join(EXAMPLES, name + ".inp"), inp)
        d, status, out = run_ccx(ccx, env, inp)
        u[name] = dat_displacement(os.path.join(d, "job.dat"), 9001) if status == "solved" else None
        shutil.rmtree(d, ignore_errors=True)
        if u[name] is None:
            print(f"FAIL  {name}: no reference-point displacement ({status})")
            print("\n".join(l for l in out.splitlines() if "ERROR" in l))
            failures += 1
    if all(u.values()):
        us, ur = u["coupling_shell_plate"], u["coupling_solid_plate"]
        err = max(abs(a - b) for a, b in zip(us, ur)) / max(abs(b) for b in ur)
        ok = err < 0.005
        print(f"{'PASS' if ok else 'FAIL'}  coupling_shell_plate (rigid coupling on S8R nodes): RP "
              f"displacement ({us[0]:+.4f}, {us[1]:+.4f}, {us[2]:+.4f}) vs the solid *Rigid Body "
              f"({ur[0]:+.4f}, {ur[1]:+.4f}, {ur[2]:+.4f}), {err * 100:.3f}% of |u|")
        failures += 0 if ok else 1

    # --- BCs on rigid-coupling members that the reference node's BCs impose -----------
    # ccx stops on a DOF that is both a coupled DOF of a coupling member and under a
    # *BOUNDARY, so the converter takes such redundant BCs off. Bar A (coupling + redundant
    # member BCs) must match bar B (the same constraints as BCs and *EQUATIONs, no coupling)
    # exactly, and bar C's dropped u3 = 0 must still hold as its end face turns about z
    # (NLGEOM).
    inp = os.path.join(tmp, "coupling_bc_bars.inp")
    convert(os.path.join(EXAMPLES, "coupling_bc_bars.inp"), inp)
    d, status, out = run_ccx(ccx, env, inp)
    u = (dat_displacements(os.path.join(d, "job.dat")) if status == "solved" else None) or {}
    shutil.rmtree(d, ignore_errors=True)
    a = [u.get(n) for n in range(1, 82)]                        # bar A; bar B is A + 100
    b = [u.get(n + 100) for n in range(1, 82)]
    c = [u.get(n) for n in range(273, 282)]                     # bar C's end face
    if not all(a + b + c):
        print(f"FAIL  coupling_bc_bars: no displacements ({status})")
        print("\n".join(l for l in out.splitlines() if "ERROR" in l))
        failures += 1
    else:
        err = max(abs(x - y) for p, q in zip(a, b) for x, y in zip(p, q))
        scale = max(abs(y) for q in b for y in q)
        moved = max(abs(x) for p in c for x in p)
        u3 = max(abs(p[2]) for p in c)
        ok = err <= 1e-9 * scale and moved > 0.1 and u3 <= 1e-9 * moved
        print(f"{'PASS' if ok else 'FAIL'}  coupling_bc_bars (BCs on coupled nodes): bar A vs the "
              f"same constraints without a coupling, max |du| = {err:.1e} of |u| {scale:.4f}; bar "
              f"C's end face |u3| <= {u3:.1e} as it moves {moved:.3f} (NLGEOM)")
        failures += 0 if ok else 1

    # --- circular-section beams with rotational BCs: deflections vs beam theory --------------
    # Under any rotational BC ccx 2.23 ties a B32 end node's circular section to its corners,
    # locking the rotations the BC leaves free (beam A, twist held at its pinned ends, then
    # deflects 0.31 of beam theory; beam B, tip turned by a prescribed rotation, 0.76): this
    # checks the knot beams abq2ccx gives such nodes.
    inp = os.path.join(tmp, "circrot.inp")
    convert(os.path.join(EXAMPLES, "beam_circ_rotation_bcs.inp"), inp)
    d, status, out = run_ccx(ccx, env, inp)
    ei, length = 210000.0 * math.pi * 10.0 ** 4 / 4, 1000.0
    for label, node, ref in (("A: pinned, twist held", 11, -1000.0 * length ** 3 / (48 * ei)),
                             ("B: tip turned 0.001 rad", 121, 0.001 * length / 2)):
        u = dat_displacement(os.path.join(d, "job.dat"), node) if status == "solved" else None
        if u is None:
            print(f"FAIL  beam_circ_rotation_bcs ({label}): no displacement ({status})")
            print("\n".join(l for l in out.splitlines() if "ERROR" in l))
            failures += 1
            continue
        ok = abs(u[1] - ref) / abs(ref) < 0.02
        print(f"{'PASS' if ok else 'FAIL'}  beam_circ_rotation_bcs ({label}): deflection = "
              f"{u[1]:+.4f} (beam theory {ref:+.4f}, {abs(u[1] - ref) / abs(ref) * 100:.1f}% diff)")
        failures += 0 if ok else 1
    shutil.rmtree(d, ignore_errors=True)

    # --- circular-section beam in an explicit dynamic step: end deflection vs beam theory ---
    # ccx 2.23 sizes a circular-section beam's explicit increment as if the section were the
    # box around the circle, about 1.3x its stable limit (the displacements turn NaN): this
    # checks the maximum increment abq2ccx caps the step with.  The load rises smoothly over
    # about three periods and is then held, so the beam ends near its static deflection;
    # L / d = 12, so the reference includes shear (Timoshenko).
    inp = os.path.join(tmp, "circexpl.inp")
    convert(os.path.join(EXAMPLES, "beam_circ_explicit.inp"), inp)
    d, status, out = run_ccx(ccx, env, inp)
    e_mod, nu, r, length = 210000.0, 0.3, 10.0, 240.0
    kappa = 6 * (1 + nu) / (7 + 6 * nu)
    ref = -1000.0 * (length ** 3 / (48 * e_mod * math.pi * r ** 4 / 4)
                     + length / (4 * kappa * e_mod / (2 * (1 + nu)) * math.pi * r ** 2))
    u = dat_displacement(os.path.join(d, "job.dat"), 4) if status == "solved" else None
    if u is None or not math.isfinite(u[1]):
        print(f"FAIL  beam_circ_explicit: no finite mid-span deflection ({status}"
              f"{', ' + str(u[1]) if u else ''})")
        print("\n".join(l for l in out.splitlines() if "ERROR" in l))
        failures += 1
    else:
        ok = abs(u[1] - ref) / abs(ref) < 0.03
        print(f"{'PASS' if ok else 'FAIL'}  beam_circ_explicit (B31 + CIRC, *DYNAMIC, EXPLICIT): "
              f"end deflection = {u[1]:+.4f} (beam theory {ref:+.4f}, "
              f"{abs(u[1] - ref) / abs(ref) * 100:.1f}% diff)")
        failures += 0 if ok else 1
    shutil.rmtree(d, ignore_errors=True)

    # --- planar beams on pinned supports: frequencies and buckling vs beam theory ---------
    # ccx runs B21 as a 3-D B31, so this checks the planar constraint: DOF 3 fixed on every
    # node (otherwise nothing holds the beam in its plane) and DOFs 4-5 at one node
    # (otherwise the free twist is a 0 Hz mode and the buckling factor meaningless): at the
    # pinned end, and on the circular section (a B32 in ccx) at the first element's middle
    # node — at the end node ccx 2.23 would lock the bending rotation as well (f1 1.46x).
    for name, label, ei, rho_a in (
            ("planar_pinned_beam", "B21", 210000.0 * 20.0 * 40.0 ** 3 / 12, 7.85e-9 * 20.0 * 40.0),
            ("planar_pinned_circ_beam", "B21 + CIRC", 210000.0 * math.pi * 10.0 ** 4 / 4,
             7.85e-9 * math.pi * 10.0 ** 2)):
        inp = os.path.join(tmp, name + ".inp")
        convert(os.path.join(EXAMPLES, name + ".inp"), inp)
        d, status, out = run_ccx(ccx, env, inp)
        length = 1000.0
        c = math.sqrt(ei / rho_a) * math.pi / (2 * length ** 2)            # in-plane E I
        refs = [c, 4 * c, math.pi ** 2 * ei / length ** 2]                 # f1, f2, Euler load
        dat = os.path.join(d, "job.dat")
        got = (dat_eigen_table(dat, "E I G E N V A L U E   O U T P U T")[:2]
               + dat_eigen_table(dat, "B U C K L I N G   F A C T O R   O U T P U T")[:1]) \
            if status == "solved" else []
        if len(got) < 3:
            print(f"FAIL  {name}: no frequencies / buckling factor ({status})")
            print("\n".join(l for l in out.splitlines() if "ERROR" in l))
            failures += 1
        else:
            diffs = [abs(g - r) / r for g, r in zip(got, refs)]
            ok = max(diffs) < 0.02
            print(f"{'PASS' if ok else 'FAIL'}  {name} ({label}): f1, f2 = {got[0]:.2f}, "
                  f"{got[1]:.2f} Hz (beam theory {refs[0]:.2f}, {refs[1]:.2f}), buckling load "
                  f"{got[2]:.0f} (Euler {refs[2]:.0f}); max {max(diffs) * 100:.1f}% diff")
            failures += 0 if ok else 1
        shutil.rmtree(d, ignore_errors=True)

    # --- per-element *DISTRIBUTION orientations vs one *ORIENTATION per element ---------
    # ccx 2.23 gives each element its own distribution line only under a *SOLID SECTION
    # (and there turns only the first line by the rotation line), and gives every element
    # of a *SHELL SECTION the first line.  So abq2ccx resolves a solid distribution per
    # element and splits a shell section per direction: the C3D8 plate (two instances, one
    # rotated) and the composite S8R variable-angle-tow panel (a rotated instance) must move
    # exactly like the same models written with one orientation and section per element.
    for name, label in (("distribution_solid_plate", "C3D8 *SOLID SECTION"),
                        ("distribution_shell_plate", "composite S8R *SHELL SECTION")):
        res = {}
        for deck in (name, name + "_explicit"):
            inp = os.path.join(tmp, deck + ".inp")
            convert(os.path.join(EXAMPLES, deck + ".inp"), inp)
            d, status, out = run_ccx(ccx, env, inp)
            res[deck] = dat_displacements(os.path.join(d, "job.dat")) if status == "solved" else None
            shutil.rmtree(d, ignore_errors=True)
            if not res[deck]:
                print(f"FAIL  {deck}: no displacements ({status})")
                print("\n".join(l for l in out.splitlines() if "ERROR" in l))
                failures += 1
        if all(res.values()):
            ud, ue = res[name], res[name + "_explicit"]
            if set(ud) != set(ue):
                print(f"FAIL  {name}: the two models printed different nodes")
                failures += 1
                continue
            scale = max(abs(x) for v in ue.values() for x in v)
            err = max(abs(a - b) for n in ue for a, b in zip(ud[n], ue[n])) / scale
            ok = err < 1e-6
            print(f"{'PASS' if ok else 'FAIL'}  {name} ({label}, per-element *DISTRIBUTION "
                  f"orientation): {len(ue)} node displacements vs one *ORIENTATION per element, "
                  f"max difference {err:.1e} of max |u|")
            failures += 0 if ok else 1
    # --- *MPC: a rigid lever (BEAM), joints (PIN / TIE) and a rigid link (LINK) -------
    # BEAM -> *RIGID BODY on the beam's tip node (a knot whose ROT NODE follows its
    # rotation); PIN / TIE -> *EQUATION (a TIE between knots, so the rotations take part);
    # LINK -> its linearised *EQUATION, or ccx's *MPC BEAM under NLGEOM.
    def solve(name, subs=(), nodes=()):
        """Convert an example (optionally with text substitutions), run it and return the
        last printed displacement of each node, or None."""
        src = os.path.join(EXAMPLES, name + ".inp")
        text = open(src).read()
        for a, b in subs:
            text = text.replace(a, b)
        tmp_src = os.path.join(tmp, f"{name}_{len(subs)}_src.inp")
        with open(tmp_src, "w") as fh:
            fh.write(text)
        inp = os.path.join(tmp, f"{name}_{len(subs)}.inp")
        convert(tmp_src, inp)
        d, status, out = run_ccx(ccx, env, inp)
        u = {n: dat_displacement(os.path.join(d, "job.dat"), n) for n in nodes} \
            if status == "solved" else {}
        shutil.rmtree(d, ignore_errors=True)
        if status != "solved" or any(v is None for v in u.values()):
            print(f"FAIL  {name}{' (variant)' if subs else ''}: did not solve ({status})")
            print("\n".join(l for l in out.splitlines() if "ERROR" in l)[:400])
            return None
        return u

    def rel(a, b):
        return abs(a - b) / abs(b)

    ei = 1.0e5 * 4.0 / 3.0                                      # E I of the 2 x 2 section
    u = solve("mpc_beam_lever", nodes=(21, 100, 221, 400))
    if u:
        tip = 1e6 / (3 * ei) + 20 * 1e4 / (2 * ei)              # P = 1, M = P e, L = 100
        lever = tip + (1e4 / (2 * ei) + 20 * 100 / ei) * 20
        errs = [rel(-u[21][1], tip), rel(-u[100][1], lever), rel(u[21][1], u[221][1]),
                rel(u[100][1], u[400][1])]
        ok = max(errs[:2]) < 0.01 and max(errs[2:]) < 1e-4
        print(f"{'PASS' if ok else 'FAIL'}  mpc_beam_lever (*MPC BEAM -> *RIGID BODY): tip "
              f"{u[21][1]:+.4f} / lever end {u[100][1]:+.4f} (statics {-tip:+.4f} / {-lever:+.4f}, "
              f"{max(errs[:2]) * 100:.2f}% diff); vs the equivalent tip load and a stiff-beam "
              f"lever {max(errs[2:]):.1e}")
        failures += 0 if ok else 1
    else:
        failures += 1
    # the same lever at 10x the load under NLGEOM (about 27 degrees at the tip)
    u = solve("mpc_beam_lever", subs=[("*Step\n*Static\n",
                                       "*Step, nlgeom=YES\n*Static\n0.05, 1., 1e-5, 0.25\n"),
                                      ("100, 2, -1.", "100, 2, -10."),
                                      ("400, 2, -1.", "400, 2, -10.")],
              nodes=(21, 100, 400))
    if u:
        length = math.dist((100 + u[21][0], u[21][1], u[21][2]),
                           (120 + u[100][0], u[100][1], u[100][2]))
        err = rel(u[100][1], u[400][1])
        ok = err < 1e-4 and rel(length, 20.0) < 1e-6
        print(f"{'PASS' if ok else 'FAIL'}  mpc_beam_lever, NLGEOM x10: lever end {u[100][1]:+.3f} "
              f"vs a stiff-beam lever {u[400][1]:+.3f} ({err:.1e}); lever length {length:.7f} "
              f"(20)")
        failures += 0 if ok else 1
    else:
        failures += 1
    u = solve("mpc_pin_tie_joints", nodes=(21, 101, 111, 221, 301, 311))
    if u:
        pin = (0.5e6 / (3 * ei), 0.25e6 / (3 * ei) + 1e6 / (48 * ei))    # w(100), w(150)
        rb = 150.0 ** 2 * (3 * 200 - 150) / (2 * 200.0 ** 3)           # roller reaction
        tie = tuple((1.0 * x * x * (3 * 150 - x) - rb * x * x * (3 * 200 - x)) / (6 * ei)
                    for x in (100.0, 150.0))
        errs = [rel(-u[21][1], pin[0]), rel(-u[111][1], pin[1]),
                rel(-u[221][1], tie[0]), rel(-u[311][1], tie[1])]
        same = max(abs(a - b) for x, y in ((21, 101), (221, 301)) for a, b in zip(u[x], u[y]))
        ok = max(errs) < 0.02 and same < 1e-9
        print(f"{'PASS' if ok else 'FAIL'}  mpc_pin_tie_joints: PIN hinge w = {u[21][1]:+.4f} "
              f"(beam theory {-pin[0]:+.4f}), TIE joint w = {u[221][1]:+.4f} (propped cantilever "
              f"{-tie[0]:+.4f}); worst {max(errs) * 100:.2f}% diff over both spans")
        failures += 0 if ok else 1
    else:
        failures += 1
    u = solve("mpc_link", nodes=(2,))
    if u:
        ref = (0.0064, -0.0048, 0.0)                             # (P.n / k) n
        err = max(abs(a - b) for a, b in zip(u[2], ref))
        ok = err < 1e-9
        print(f"{'PASS' if ok else 'FAIL'}  mpc_link (linearised *EQUATION): u = ({u[2][0]:+.5f}, "
              f"{u[2][1]:+.5f}) (statics (+0.00640, -0.00480), {err:.1e} off)")
        failures += 0 if ok else 1
    else:
        failures += 1
    # NLGEOM and a large load: ccx's *MPC BEAM keeps the length while the link turns ~25 deg
    # (it turns away from the 45-degree diagonal, where ccx would have to switch the MPC's
    # dependent DOF)
    u = solve("mpc_link", subs=[("*Step\n*Static\n",
                                 "*Step, nlgeom=YES\n*Static\n0.05, 1., 1e-5, 0.25\n"),
                                ("2, 1, 10.", "2, 1, -2000.")], nodes=(2,))
    if u:
        length = math.dist((3 + u[2][0], 4 + u[2][1], u[2][2]), (0.0, 0.0, 0.0))
        turn = math.degrees(math.atan2(4 + u[2][1], 3 + u[2][0]) - math.atan2(4, 3))
        ok = rel(length, 5.0) < 1e-6 and turn > 10
        print(f"{'PASS' if ok else 'FAIL'}  mpc_link, NLGEOM (*MPC BEAM): length {length:.7f} (5) "
              f"after turning {turn:.1f} degrees")
        failures += 0 if ok else 1
    else:
        failures += 1
    # --- connector elements (CONN3D2): ccx has no connector element; abq2ccx writes each
    # connector's kinematic constraint as *EQUATION / *BOUNDARY / *RIGID BODY / *MPC -------
    # the same joints, lever and link as above, written as connectors, must give the same
    # answers: JOIN = PIN, WELD = TIE (a rigid body on knots), BEAM = *MPC BEAM, LINK = LINK
    joints = [("*MPC\nPIN, 101, 21\nTIE, 301, 221\n",
               "*Element, type=CONN3D2, elset=J\n9001, 21, 101\n*Element, type=CONN3D2, elset=W\n"
               "9002, 221, 301\n*Connector Section, elset=J\nJoin,\n*Connector Section, elset=W\n"
               "Weld,\n")]
    lever = [("*MPC\nBEAM, 100, 21\n",
              "*Element, type=CONN3D2, elset=W\n9001, 21, 100\n*Connector Section, elset=W\nBeam,\n")]
    link = [("*MPC\nLINK, 2, 1\n",
             "*Element, type=CONN3D2, elset=W\n9001, 1, 2\n*Connector Section, elset=W\nLink,\n")]
    nl_lever = [("*Step\n*Static\n", "*Step, nlgeom=YES\n*Static\n0.05, 1., 1e-5, 0.25\n"),
                ("100, 2, -1.", "100, 2, -10."), ("400, 2, -1.", "400, 2, -10.")]
    nl_link = [("*Step\n*Static\n", "*Step, nlgeom=YES\n*Static\n0.05, 1., 1e-5, 0.25\n"),
               ("2, 1, 10.", "2, 1, -2000.")]
    for name, subs, nodes, label in (
            ("mpc_pin_tie_joints", [], (21, 101, 111, 221, 301, 311), "JOIN / WELD"),
            ("mpc_beam_lever", [], (21, 100), "BEAM"),
            ("mpc_beam_lever", nl_lever, (21, 100), "BEAM, NLGEOM x10"),
            ("mpc_link", [], (2,), "LINK"),
            ("mpc_link", nl_link, (2,), "LINK, NLGEOM")):
        conn = {"mpc_pin_tie_joints": joints, "mpc_beam_lever": lever, "mpc_link": link}[name]
        ref, got = solve(name, subs, nodes), solve(name, conn + subs, nodes)
        if ref and got:
            err = max(abs(a - b) for n in nodes for a, b in zip(ref[n], got[n])) / \
                max(abs(a) for n in nodes for a in ref[n])
            ok = err < 1e-6
            print(f"{'PASS' if ok else 'FAIL'}  {name} as connectors ({label}): matches the *MPC "
                  f"version to {err:.1e} of |u|")
            failures += 0 if ok else 1
        else:
            failures += 1
    # HINGE (axis z) between beam ends: it releases bending about z and transmits it about y
    u = solve("connector_hinge_beams", nodes=(21, 101, 111, 221, 301, 311))
    if u:
        pin = (0.5e6 / (3 * ei), 0.25e6 / (3 * ei) + 1e6 / (48 * ei))    # w(100), w(150)
        rb = 150.0 ** 2 * (3 * 200 - 150) / (2 * 200.0 ** 3)
        tie = tuple((1.0 * x * x * (3 * 150 - x) - rb * x * x * (3 * 200 - x)) / (6 * ei)
                    for x in (100.0, 150.0))
        errs = [rel(-u[21][1], pin[0]), rel(-u[111][1], pin[1]),
                rel(-u[221][2], tie[0]), rel(-u[311][2], tie[1])]
        same = max(abs(a - b) for x, y in ((21, 101), (221, 301)) for a, b in zip(u[x], u[y]))
        ok = max(errs) < 0.02 and same < 1e-9
        print(f"{'PASS' if ok else 'FAIL'}  connector_hinge_beams (HINGE about z): in-plane w = "
              f"{u[21][1]:+.4f} (released: {-pin[0]:+.4f}), out-of-plane w = {u[221][2]:+.4f} "
              f"(transmitted: {-tie[0]:+.4f}); worst {max(errs) * 100:.2f}% diff over both spans")
        failures += 0 if ok else 1
    else:
        failures += 1
    # the hood-hinge construct: two *MPC BEAM bodies on springs, an oblique hinge axis and a
    # joint offset, against the exact small-displacement solution
    out = (1, 3, 11, 12, 13, 21, 22, 23)
    u = solve("connector_hinge_bodies", nodes=out)
    if u:
        ref = hinge_bodies_reference()
        err = max(abs(a - b) for n in out for a, b in zip(u[n], ref[n])) / \
            max(abs(a) for n in out for a in ref[n])
        ok = err < 1e-5
        print(f"{'PASS' if ok else 'FAIL'}  connector_hinge_bodies (HINGE between rigid bodies): "
              f"member 22 u = ({u[22][0]:+.5f}, {u[22][1]:+.5f}, {u[22][2]:+.5f}), exact "
              f"({ref[22][0]:+.5f}, {ref[22][1]:+.5f}, {ref[22][2]:+.5f}); {err:.1e} of |u| off")
        failures += 0 if ok else 1
    else:
        failures += 1
    # a body hinged to ground under NLGEOM turns ~138 degrees about the fixed oblique axis:
    # every member must follow that rotation exactly, at the angle that balances the moment
    u = solve("connector_ground_hinge", nodes=(3, 21, 22, 23))
    if u:
        e1, phi_ref = ground_hinge_reference()
        x3 = (0.2, 0.5, -0.1)
        pts = {21: (1., 1., 1.), 22: (0.5, -1., 0.7), 23: (-0.4, 0.8, 1.3)}
        r0 = [p - q for p, q in zip(pts[21], x3)]
        r1 = [p + d - q for p, d, q in zip(pts[21], u[21], x3)]
        p0 = [a - _dot(r0, e1) * e for a, e in zip(r0, e1)]
        p1 = [a - _dot(r1, e1) * e for a, e in zip(r1, e1)]
        phi = math.atan2(_dot(e1, _cross(p0, p1)), _dot(p0, p1))
        # (ccx converges the rigid-body MPCs to ~1e-5 of |u|; a linearised hinge would be off
        # by the order of |u| at this angle)
        miss = max(abs(q + a - b - c) for n, x in pts.items()
                   for q, a, b, c in zip(x3, _rotate([p - q for p, q in zip(x, x3)], e1, phi),
                                         x, u[n])) / max(abs(c) for n in pts for c in u[n])
        ok = miss < 1e-4 and max(abs(c) for c in u[3]) < 1e-12 and rel(phi, phi_ref) < 0.005
        print(f"{'PASS' if ok else 'FAIL'}  connector_ground_hinge, NLGEOM (HINGE to ground): body "
              f"turned {math.degrees(phi):.2f} deg about the axis (statics {math.degrees(phi_ref):.2f}),"
              f" members {miss:.1e} of |u| off that rigid rotation")
        failures += 0 if ok else 1
    else:
        failures += 1
    # an *EQUATION whose first DOF has a BC: the terms are swapped, the duplicate dropped;
    # a loop of ties loses its closing equation (ccx would hold the loop at zero)
    u = solve("equation_overconstraint", nodes=(2, 3, 6, 7))
    if u:
        loop = [u[n][0] for n in (3, 6, 7)]
        ok = abs(u[2][0]) < 1e-12 and min(loop) > 0.01 and max(loop) - min(loop) < 1e-12
        print(f"{'PASS' if ok else 'FAIL'}  equation_overconstraint: solves (ccx rejects the deck "
              f"as written); tied node u_x = {u[2][0]:+.1e}, loop u_x = {loop[0]:+.4f} "
              f"({loop[1]:+.4f}, {loop[2]:+.4f})")
        failures += 0 if ok else 1
    else:
        failures += 1

    # --- *BOUNDARY, OP=NEW in a later step on a clamped beam and plate --------------------
    # ccx 2.23 does not rebuild re-specified rotational BCs on shell/beam nodes after OP=NEW:
    # converted as they are, these decks' clamped roots become hinges in step 2 (tip
    # deflections of 1e5 to 1e9) and the plate's prescribed tip z comes out 0.  This checks
    # both repairs: an OP=NEW that removes nothing is dropped, and where it removes a BC (the
    # prop) the clamped nodes become knots, which stiffens the beam clamp by ~0.7 %.
    pl3_3ei = 10.0 * 1000.0 ** 3 / (3 * 210000.0 * 40.0 * 20.0 ** 3 / 12)      # P L^3 / (3 E I)
    for name in ("op_new_respecify", "op_new_remove"):
        inp = os.path.join(tmp, name + ".inp")
        convert(os.path.join(EXAMPLES, name + ".inp"), inp)
        d, status, out = run_ccx(ccx, env, inp)
        dat = os.path.join(d, "job.dat")
        beam = [u[2] for u in dat_displacement_history(dat, 21)] if status == "solved" else []
        plate = [u[2] for u in dat_displacement_history(dat, 1221)] if status == "solved" else []
        shutil.rmtree(d, ignore_errors=True)
        if len(beam) < 2 or len(plate) < 2:
            print(f"FAIL  {name}: no step-2 tip displacements ({status})")
            print("\n".join(l for l in out.splitlines() if "ERROR" in l))
            failures += 1
            continue
        if name == "op_new_respecify":      # step 2: twice the load, the plate tip z set to 2
            refs = [("beam tip", beam[1], 2 * pl3_3ei), ("plate tip (prescribed)", plate[1], 2.0)]
        else:                               # step 2: the prop removed, the plate as in step 1
            refs = [("beam tip", beam[1], pl3_3ei), ("plate tip (step 1)", plate[1], plate[0])]
        diffs = [abs(v - ref) / abs(ref) for _, v, ref in refs]
        ok = diffs[0] < 0.02 and diffs[1] < 1e-4
        print(f"{'PASS' if ok else 'FAIL'}  {name}: step 2 " + ", ".join(
            f"{label} {v:+.4f} (expected {ref:+.4f}, {diff * 100:.2f}% diff)"
            for (label, v, ref), diff in zip(refs, diffs)))
        failures += 0 if ok else 1

    # --- isotropic *Elastic beside an orthotropic / anisotropic *Expansion -----------------
    # ccx 2.23 uses a wrong stiffness for this combination in linear steps once the deck has
    # temperatures (a free heated cube shrinks), so the converter writes such *Elastic cards
    # as ENGINEERING CONSTANTS or ANISO.  Four heated unit cubes: three free ones against
    # alpha dT (one with its material system turned 30 deg about z, one with an ANISO
    # expansion whose shear coefficients are Abaqus' engineering ones, gamma_ij = alpha_ij dT,
    # which ccx reads as tensor components once halved), and one held in x whose E and nu
    # depend on temperature, read between the given rows (without the added rows ccx is
    # 0.6 % / 1.4 % off there).
    inp = os.path.join(tmp, "thermal.inp")
    convert(os.path.join(EXAMPLES, "thermal_expansion_cubes.inp"), inp)
    d, status, out = run_ccx(ccx, env, inp)
    dat = os.path.join(d, "job.dat")
    a1, a2, a3, dt = 1e-5, 2e-5, 4e-5, 90.0
    a12, a13, a23 = 1.2e-5, -0.8e-5, 0.6e-5                          # engineering, as given
    c, s = math.cos(math.radians(30.0)), math.sin(math.radians(30.0))
    e_hot, nu_hot = 1900.0, 0.245                                    # E, nu at T = 90
    expect = {1: [(a1 * c * c + a2 * s * s) * dt, (a1 * s * s + a2 * c * c) * dt, a3 * dt,
                  (a1 - a2) * s * c * dt, 0.0, 0.0],
              11: [a1 * dt, a2 * dt, a3 * dt, 0.0, 0.0, 0.0],
              21: [0.0, (a2 + nu_hot * a1) * dt, (a3 + nu_hot * a1) * dt, 0.0, 0.0, 0.0],
              31: [a1 * dt, a2 * dt, a3 * dt, a12 * dt / 2, a13 * dt / 2, a23 * dt / 2]}
    errs = []
    for base, ref in expect.items():
        # homogeneous strain from the corner displacements (nodes at unit offsets x, y, z)
        u = [dat_displacement(dat, base + k) if status == "solved" else None for k in (0, 1, 3, 4)]
        if any(v is None for v in u):
            errs = None
            break
        h = [[u[j + 1][i] - u[0][i] for j in range(3)] for i in range(3)]      # du_i / dx_j
        eps = [h[0][0], h[1][1], h[2][2], (h[0][1] + h[1][0]) / 2, (h[0][2] + h[2][0]) / 2,
               (h[1][2] + h[2][1]) / 2]
        errs.append(max(abs(x - y) for x, y in zip(eps, ref)) / max(abs(y) for y in ref))
    sig = dat_el_stress(dat, 3) if status == "solved" else None
    if errs is None or sig is None:
        print(f"FAIL  thermal_expansion_cubes: no displacements / stresses ({status})")
        print("\n".join(l for l in out.splitlines() if "ERROR" in l))
        failures += 1
    else:
        sxx_ref = -e_hot * a1 * dt
        errs.append(abs(sig[0] - sxx_ref) / abs(sxx_ref))
        ok = max(errs) < 1e-3
        print(f"{'PASS' if ok else 'FAIL'}  thermal_expansion_cubes (isotropic *Elastic + ORTHO/ANISO "
              f"*Expansion): free strains {errs[0] * 100:.4f}% / {errs[1] * 100:.4f}% off alpha dT, "
              f"ANISO with shear terms {errs[3] * 100:.4f}% off (alpha_ij dT / 2 for i /= j); "
              f"held cube at T = 90: strains {errs[2] * 100:.4f}% off, sigma_xx = {sig[0]:+.5f} "
              f"(analytic {sxx_ref:+.5f})")
        failures += 0 if ok else 1
    shutil.rmtree(d, ignore_errors=True)

    # --- BCs on *RIGID BODY nodes, moved to the reference node -----------------------
    # Abaqus moves identical BCs on rigid-body nodes to the reference node, adding zero
    # rotations about the other axes; ccx stops on a BC on a rigid-body node, so the converter
    # moves them where the BC'd nodes hold the same DOFs. Bar A (far-face u1 = 0 on its rigid
    # cap: implied in step 1, moved in step 2 once the reference point is released) must match
    # bar B (the same BCs on its reference point by hand) exactly, and A's far face must keep
    # u1 = 0 while the cap twists about x (NLGEOM).
    inp = os.path.join(tmp, "rigid_body_bc_bars.inp")
    convert(os.path.join(EXAMPLES, "rigid_body_bc_bars.inp"), inp)
    d, status, out = run_ccx(ccx, env, inp)
    u = dat_displacements(os.path.join(d, "job.dat")) if status == "solved" else {}
    shutil.rmtree(d, ignore_errors=True)
    a = [u.get(n) for n in range(1, 100)]                       # bar A; bar B is A + 1000
    b = [u.get(n + 1000) for n in range(1, 100)]
    far = [u.get(n) for n in range(11, 100, 11)]                # bar A's far face (x = 5)
    if not all(a + b):
        print(f"FAIL  rigid_body_bc_bars: no displacements ({status})")
        print("\n".join(l for l in out.splitlines() if "ERROR" in l))
        failures += 1
    else:
        err = max(abs(x - y) for p, q in zip(a, b) for x, y in zip(p, q))
        scale = max(abs(y) for q in b for y in q)
        moved = max(abs(p[1]) + abs(p[2]) for p in far)
        u1 = max(abs(p[0]) for p in far)
        ok = err <= 1e-9 * scale and moved > 0.1 and u1 <= 1e-9 * moved
        print(f"{'PASS' if ok else 'FAIL'}  rigid_body_bc_bars (BCs on *RIGID BODY nodes moved to "
              f"the reference node): bar A vs the same BCs on the reference point by hand, max "
              f"|du| = {err:.1e} of |u| {scale:.4f}; A's far face |u1| <= {u1:.1e} as it moves "
              f"{moved:.3f} (NLGEOM)")
        failures += 0 if ok else 1

    # --- distributed loads ccx has no card for, applied as consistent nodal forces ------
    # Cook's membrane: a shear traction (*DSLOAD TRVEC) on plane-stress CPS8 edges, against
    # the published displacement of the loaded edge's midpoint.
    inp = os.path.join(tmp, "cook.inp")
    convert(os.path.join(EXAMPLES, "cook_membrane_traction.inp"), inp)
    d, status, out = run_ccx(ccx, env, inp)
    u = dat_displacement(os.path.join(d, "job.dat"), 3217) if status == "solved" else None
    ref = 23.96                                           # Bergan & Felippa (1985)
    if u is None:
        print(f"FAIL  cook_membrane_traction: no displacement at C ({status})")
        print("\n".join(l for l in out.splitlines() if "ERROR" in l))
        failures += 1
    else:
        ok = abs(u[1] - ref) / ref < 0.01
        print(f"{'PASS' if ok else 'FAIL'}  cook_membrane_traction (TRVEC on CPS8 edges): v_C = "
              f"{u[1]:.3f} (reference {ref:.2f}, {abs(u[1] - ref) / ref * 100:.2f}% diff)")
        failures += 0 if ok else 1
    shutil.rmtree(d, ignore_errors=True)

    # Beam line loads (*DLOAD PY / local P2 / PZ) on B31, B32 and a CIRC B31 run as B32 with
    # midside nodes: the applied resultants are q L, the tip deflections q L^4 / (8 E I).
    inp = os.path.join(tmp, "lineload.inp")
    convert(os.path.join(EXAMPLES, "beam_line_load_cantilever.inp"), inp)
    applied = {"A": [0.0] * 3, "B": [0.0] * 3, "C": [0.0] * 3}
    in_cload = False
    for ln in open(inp):
        if ln.startswith("*"):
            in_cload = ln.startswith("*CLOAD")
        elif in_cload:
            node, dof, val = (x.strip() for x in ln.split(","))
            beam = "A" if int(node) <= 21 else "B" if int(node) <= 121 else "C"
            applied[beam][int(dof) - 1] += float(val)
    d, status, out = run_ccx(ccx, env, inp)
    e_mod, iy_rect, i_circ = 1.0e7, 2 * 4 ** 3 / 12, math.pi / 4
    for beam, node, axis, q, inertia in (("A", 21, 1, -0.01, iy_rect), ("B", 121, 2, 0.01, iy_rect),
                                         ("C", 221, 2, -0.001, i_circ)):
        u = dat_displacement(os.path.join(d, "job.dat"), node) if status == "solved" else None
        ref = q * 100.0 ** 4 / (8 * e_mod * inertia)
        if u is None:
            print(f"FAIL  beam_line_load_cantilever ({beam}): no tip displacement ({status})")
            print("\n".join(l for l in out.splitlines() if "ERROR" in l))
            failures += 1
            continue
        force = applied[beam][axis]
        ok = abs(u[axis] - ref) / abs(ref) < 0.02 and abs(force - q * 100.0) < 1e-9
        print(f"{'PASS' if ok else 'FAIL'}  beam_line_load_cantilever ({beam}): applied {force:+.4g} "
              f"(q L = {q * 100.0:+.4g}), tip deflection {u[axis]:+.6f} (beam theory {ref:+.6f}, "
              f"{abs(u[axis] - ref) / abs(ref) * 100:.1f}% diff)")
        failures += 0 if ok else 1
    shutil.rmtree(d, ignore_errors=True)

    # An axisymmetric surface traction (radial TRVEC on CAX8): Lame's open-ended cylinder.
    inp = os.path.join(tmp, "cylinder.inp")
    convert(os.path.join(EXAMPLES, "cylinder_traction_cax.inp"), inp)
    d, status, out = run_ccx(ccx, env, inp)
    a, b, e_mod, nu = 10.0, 20.0, 1000.0, 0.3
    for node, r in ((101, a), (121, b)):
        u = dat_displacement(os.path.join(d, "job.dat"), node) if status == "solved" else None
        ref = a * a / (e_mod * (b * b - a * a)) * ((1 - nu) * r + (1 + nu) * b * b / r)
        if u is None:
            print(f"FAIL  cylinder_traction_cax: no displacement at r = {r:g} ({status})")
            print("\n".join(l for l in out.splitlines() if "ERROR" in l))
            failures += 1
            continue
        ok = abs(u[0] - ref) / ref < 0.01
        print(f"{'PASS' if ok else 'FAIL'}  cylinder_traction_cax (TRVEC on CAX8): u_r({r:g}) = "
              f"{u[0]:.6f} (Lame {ref:.6f}, {abs(u[0] - ref) / ref * 100:.2f}% diff)")
        failures += 0 if ok else 1
    shutil.rmtree(d, ignore_errors=True)

    # Tractions on nodes with local axes: ccx, like Abaqus, reads a *CLOAD on a node with a
    # *TRANSFORM in its local axes, so the converted forces are given in them.  A block whose
    # loaded face carries a rectangular and a cylindrical transform, and Cook's membrane with
    # in-plane ones on its loaded edge (local 3 = -z; a cylinder about z), must match the same
    # models without the transforms (forces left in global components miss by 149 % / 88 %).
    cs, sn = math.cos(0.5), math.sin(0.5)
    cook = open(os.path.join(EXAMPLES, "cook_membrane_traction.inp")).read().replace(
        "*NODE PRINT, NSET=C\nU\n", "*NODE PRINT, NSET=RIGHT, GLOBAL=YES\nU\n")
    edge = ("*NSET, NSET=RIGHT_LOW, GENERATE\n3201, 3216, 1\n*NSET, NSET=RIGHT_UP, GENERATE\n"
            f"3217, 3233, 1\n*TRANSFORM, NSET=RIGHT_LOW, TYPE=R\n{cs!r}, {sn!r}, 0., {sn!r}, {-cs!r}, 0.\n"
            "*TRANSFORM, NSET=RIGHT_UP, TYPE=C\n10., 20., 0., 10., 20., 1.\n")
    block = open(os.path.join(EXAMPLES, "traction_transformed_face.inp")).read()
    for name, how, decks in (
            ("traction_transformed_face", "C3D20R face, rectangular + cylindrical",
             (block, re.sub(r"(?m)^\*TRANSFORM.*\n.*\n", "", block))),
            ("cook_membrane_traction", "CPS8 edge, in-plane rectangular + cylindrical",
             (cook.replace("*MATERIAL", edge + "*MATERIAL", 1), cook))):
        u, bad = [], ""
        for text in decks:
            src, inp = os.path.join(tmp, "transform_src.inp"), os.path.join(tmp, "transform.inp")
            with open(src, "w") as fh:
                fh.write(text)
            convert(src, inp)
            d, status, out = run_ccx(ccx, env, inp)
            u.append(dat_displacements(os.path.join(d, "job.dat")) if status == "solved" else {})
            if status != "solved" and not bad:
                bad = " / ".join([status] + [l.strip() for l in out.splitlines() if "ERROR" in l])
            shutil.rmtree(d, ignore_errors=True)
        if not u[0] or u[0].keys() != u[1].keys():
            print(f"FAIL  {name} with *TRANSFORM ({how}): no displacements to compare "
                  f"({bad or 'different nodes printed'})")
            failures += 1
            continue
        scale = max(abs(x) for v in u[1].values() for x in v)
        err = max(abs(a - b) for n in u[1] for a, b in zip(u[0][n], u[1][n])) / scale
        ok = err <= 1e-6
        print(f"{'PASS' if ok else 'FAIL'}  {name} with *TRANSFORM ({how}): u at {len(u[1])} nodes "
              f"differs from the model without it by {err:.1e} of max |u| ({scale:.4g})")
        failures += 0 if ok else 1

    # --- *Temperature without initial temperatures ------------------------------------------
    # Abaqus starts every node at 0 when a deck gives no initial temperatures; ccx stops on
    # *TEMPERATURE unless thermal *INITIAL CONDITIONS precede it, so the converter adds them
    # at 0 for every node — also the free node of the knot beam at the circular-section
    # beam's pinned end.  A free cube heated to T = 100 must strain alpha T, the beam's far
    # end move alpha T L.
    inp = os.path.join(tmp, "no_initial_temperature.inp")
    convert(os.path.join(EXAMPLES, "thermal_no_initial_temperature.inp"), inp)
    d, status, out = run_ccx(ccx, env, inp)
    u = dat_displacements(os.path.join(d, "job.dat")) if status == "solved" else None
    shutil.rmtree(d, ignore_errors=True)
    alpha_t = 1.2e-5 * 100.0
    if not u or any(n not in u for n in (1, 2, 4, 5, 13)):
        print(f"FAIL  thermal_no_initial_temperature: no displacements ({status})")
        print("\n".join(l for l in out.splitlines() if "ERROR" in l))
        failures += 1
    else:
        # the cube's homogeneous strain from the corners at unit offsets x, y, z of node 1
        h = [[u[n][i] - u[1][i] for n in (2, 4, 5)] for i in range(3)]       # du_i / dx_j
        eps = [h[0][0], h[1][1], h[2][2], (h[0][1] + h[1][0]) / 2, (h[0][2] + h[2][0]) / 2,
               (h[1][2] + h[2][1]) / 2]
        err_cube = max(abs(x - y) for x, y in zip(eps, [alpha_t] * 3 + [0.0] * 3)) / alpha_t
        err_beam = abs(u[13][0] - alpha_t * 100.0) / (alpha_t * 100.0)
        ok = err_cube < 1e-6 and err_beam < 1e-4
        print(f"{'PASS' if ok else 'FAIL'}  thermal_no_initial_temperature (*Temperature, no initial "
              f"temperatures): cube strain {eps[0]:.6e} / {eps[1]:.6e} / {eps[2]:.6e} (alpha T = "
              f"{alpha_t:.6e}, {err_cube:.1e} off); CIRC beam end u_x = {u[13][0]:+.6f} (alpha T L "
              f"= {alpha_t * 100.0:+.6f}, {err_beam * 100:.4f}% diff)")
        failures += 0 if ok else 1

    # Local axes ccx lacks or does not carry over: a spherical *TRANSFORM (ccx has none; each
    # node gets a rectangular one with its spherical axes) and a rigid body whose reference
    # point has a cylindrical one (ccx carries the body's rotations on its ROT NODE, which gets
    # the same axes).  The example's local loads, radial roller, circumferential support and
    # held rotations must act as in the same model written in global components.
    deck = open(os.path.join(EXAMPLES, "transform_spherical_rigid.inp")).read()
    u, bad = [], ""
    for text in (deck, global_twin(deck)):
        src, inp = os.path.join(tmp, "local_src.inp"), os.path.join(tmp, "local.inp")
        with open(src, "w") as fh:
            fh.write(text)
        convert(src, inp)
        d, status, out = run_ccx(ccx, env, inp)
        u.append(dat_displacements(os.path.join(d, "job.dat")) if status == "solved" else {})
        if status != "solved" and not bad:
            bad = " / ".join([status] + [l.strip() for l in out.splitlines() if "ERROR" in l])
        shutil.rmtree(d, ignore_errors=True)
    if not u[0] or u[0].keys() != u[1].keys():
        print(f"FAIL  transform_spherical_rigid: no displacements to compare "
              f"({bad or 'different nodes printed'})")
        failures += 1
    else:
        scale = max(abs(x) for v in u[1].values() for x in v)
        err = max(abs(a - b) for n in u[1] for a, b in zip(u[0][n], u[1][n])) / scale
        ok = err <= 1e-6
        print(f"{'PASS' if ok else 'FAIL'}  transform_spherical_rigid (spherical *TRANSFORM, rigid body "
              f"with a cylindrical one on its reference point): u at {len(u[1])} nodes differs from "
              f"the model in global components by {err:.1e} of max |u| ({scale:.4g})")
        failures += 0 if ok else 1

    # --- connector elements on nodes with a *TRANSFORM ------------------------------------
    # ccx, like Abaqus, reads *EQUATION terms and BCs on a transformed node in its local axes,
    # so abq2ccx writes the connector rows there — a rotation on its rotation node, which gets
    # the reference node's axes.  Each model must match the same model without the *TRANSFORM
    # (its local loads in global components): a rigid plate joined to a face with a cylindrical
    # transform, where ccx's own choice of eliminated DOFs fails in the plain order, and a LINK
    # (linear); a JOIN to a transformed face (linear and NLGEOM); the HINGE between rigid bodies
    # with a transform on either reference point; the hinge to ground under NLGEOM with one on
    # its reference point.  Rows in global components (abq2ccx before this) miss by 7-76 % of
    # max |u| — with no warning on the JOINs and on reference point 1 — or ccx stops.
    def local_axes(typ, a, b, x):
        """Abaqus' local axes of a rectangular / cylindrical *TRANSFORM at point ``x``,
        computed independently of abq2ccx."""
        if typ == "R":
            e1, e3 = _unit(a), _unit(_cross(a, b))
            return e1, _cross(e3, e1), e3
        e3 = _unit([q - p for p, q in zip(a, b)])
        r = [xi - ai for xi, ai in zip(x, a)]
        e1 = _unit([ri - _dot(r, e3) * e for ri, e in zip(r, e3)])
        return e1, _cross(e3, e1), e3

    def with_transform(deck, node, typ, a, b, x):
        """``deck`` with a *TRANSFORM on ``node`` (at ``x``) and its *CLOAD lines (forces and
        moments) given in the local axes."""
        ax = local_axes(typ, a, b, x)
        head, cload = deck.split("*Cload\n", 1)
        lines, rest = cload.split("*", 1)
        keep, own = [], {}
        for ln in lines.strip().splitlines():
            n, d, v = (f.strip() for f in ln.split(","))
            if n == str(node):
                own[int(d)] = float(v)
            else:
                keep.append(ln)
        for base in (0, 3):
            g = [own.get(base + k + 1, 0.0) for k in range(3)]
            if any(g):
                keep += [f"{node}, {base + j + 1}, {_dot(g, e):.14g}" for j, e in enumerate(ax)]
        card = (f"*Nset, nset=LOCAL\n{node}\n*Transform, nset=LOCAL, type={typ}\n"
                + ", ".join(repr(float(v)) for v in list(a) + list(b)) + "\n")
        return head.replace("*Step", card + "*Step", 1) + "*Cload\n" + "\n".join(keep) + "\n*" + rest

    def same_as(label, text, twin):
        """Run ``text`` and ``twin`` (the same model in global components) and compare every
        printed displacement; 1 on failure."""
        u, bad = [], ""
        for i, t in enumerate((text, twin)):
            src, inp = os.path.join(tmp, f"ct{i}_src.inp"), os.path.join(tmp, f"ct{i}.inp")
            with open(src, "w") as fh:
                fh.write(t)
            convert(src, inp)
            d, status, out = run_ccx(ccx, env, inp)
            u.append(dat_displacements(os.path.join(d, "job.dat")) if status == "solved" else {})
            if status != "solved" and not bad:
                bad = " / ".join([status] + [l.strip() for l in out.splitlines() if "ERROR" in l])
            shutil.rmtree(d, ignore_errors=True)
        if not u[0] or u[0].keys() != u[1].keys():
            print(f"FAIL  {label}: no displacements to compare ({bad or 'different nodes printed'})")
            return 1
        scale = max(abs(x) for v in u[1].values() for x in v)
        err = max(abs(p - q) for n in u[1] for p, q in zip(u[0][n], u[1][n])) / scale
        ok = err <= 1e-6
        print(f"{'PASS' if ok else 'FAIL'}  {label}: u at {len(u[1])} nodes differs from the model "
              f"without the *TRANSFORM by {err:.1e} of max |u| ({scale:.4g})")
        return 0 if ok else 1
    untransformed = lambda t: re.sub(r"(?mi)^\*Transform.*\n.*\n", "", t)  # noqa: E731
    plate = open(os.path.join(EXAMPLES, "connector_transform_plate.inp")).read()
    failures += same_as("connector_transform_plate (JOIN to a rigid plate on a cylindrically "
                        "transformed face, LINK to a transformed node)", plate, untransformed(plate))
    join = open(os.path.join(EXAMPLES, "connector_transform_join.inp")).read()
    failures += same_as("connector_transform_join (JOIN to a transformed face)", join,
                        untransformed(join))
    nl_join = join.replace("*Step\n*Static\n", "*Step, nlgeom=YES\n*Static\n0.1, 1., 1e-6, 0.2\n") \
        .replace("TIP, 1, 1.\nTIP, 2, -2.\nTIP, 3, 0.5", "TIP, 1, 40.\nTIP, 2, -80.\nTIP, 3, 20.")
    failures += same_as("connector_transform_join, NLGEOM x40 (max |u| 2.8 on a unit block)",
                        nl_join, untransformed(nl_join))
    hinge = open(os.path.join(EXAMPLES, "connector_hinge_bodies.inp")).read().replace(
        "*Node Print, nset=OUT", "*Node Print, nset=OUT, global=YES")
    rect, cyl = ("R", (1., 2., 0.5), (-1., 0.3, 1.)), ("C", (0.3, -0.2, -0.4), (1.1, 0.9, 1.6))
    failures += same_as("connector_hinge_bodies with a rectangular *TRANSFORM on reference point 1",
                        with_transform(hinge, 1, *rect, (0., 0., 0.)), hinge)
    failures += same_as("connector_hinge_bodies with a cylindrical *TRANSFORM on reference point 3 "
                        "(its moment in the local axes)",
                        with_transform(hinge, 3, *cyl, (0.2, 0.5, -0.1)), hinge)
    ground = open(os.path.join(EXAMPLES, "connector_ground_hinge.inp")).read().replace(
        "*Node Print, nset=OUT", "*Node Print, nset=OUT, global=YES")
    failures += same_as("connector_ground_hinge, NLGEOM, with a rectangular *TRANSFORM on its "
                        "reference point (moments in the local axes)",
                        with_transform(ground, 3, *rect, (0.2, 0.5, -0.1)), ground)

    # --- *BOUNDARY, TYPE=VELOCITY / ACCELERATION -> integrated displacement BCs ----------
    # A column pulled through a rigid reference point: the velocity ramps in by a SMOOTH
    # STEP (the corpus' davidmorin pattern) and stays in force in a second step, where a ccx
    # BC would freeze; every increment must sit on the integral of the velocity.
    inp = os.path.join(tmp, "velocity_bc_column.inp")
    convert(os.path.join(EXAMPLES, "velocity_bc_column.inp"), inp)
    d, status, out = run_ccx(ccx, env, inp)
    top = dat_history(os.path.join(d, "job.dat"), "displacements", "TOP")
    rf = dat_history(os.path.join(d, "job.dat"), "total force", "BOTTOM")
    shutil.rmtree(d, ignore_errors=True)

    def pulled(t):                       # velocity 1 with a SMOOTH STEP over the first 0.001
        s = min(t / 0.001, 1.0)
        return 0.001 * s ** 4 * (2.5 - 3 * s + s * s) + max(t - 0.001, 0.0)
    if status != "solved" or not top or not rf:
        print(f"FAIL  velocity_bc_column: did not solve ({status})")
        print("\n".join(l for l in out.splitlines() if "ERROR" in l)[:400])
        failures += 1
    else:
        dev = max(abs(r[2] - pulled(t)) for t, rows in top for r in rows) / pulled(0.015)
        ends = [rows[0][2] for t, rows in top if abs(t - 0.01) < 1e-9 or abs(t - 0.015) < 1e-9]
        force = -rf[-1][1][0][2] / (1000.0 * pulled(0.015) / 4.0)       # vs E A u / L
        ok = dev < 1e-4 and len(ends) == 2 and abs(ends[0] - 0.0095) < 1e-9 and \
            abs(ends[1] - 0.0145) < 1e-9 and abs(force - 1.0) < 0.01
        print(f"{'PASS' if ok else 'FAIL'}  velocity_bc_column (TYPE=VELOCITY, SMOOTH STEP, kept "
              f"into a 2nd step): top at {ends[0] if ends else float('nan'):.6f} / "
              f"{ends[1] if len(ends) > 1 else float('nan'):.6f} (integral 0.009500 / 0.014500), "
              f"{len(top)} increments within {dev:.1e} of the travel; reaction {force:.4f} x E A u/L")
        failures += 0 if ok else 1
    # A bar driven at one end, explicit: a constant velocity v sends a wave with stress
    # -rho c v behind its front (on average: without Abaqus' bulk viscosity the explicit
    # solution rings behind the step front); as an implicit variant a constant acceleration
    # a, whose wave stress grows linearly behind the front, -rho c a (t - z / c).
    src = open(os.path.join(EXAMPLES, "velocity_bc_bar.inp")).read()
    accel = src.replace("nlgeom=YES\n*Dynamic, Explicit\n , 0.5",
                        "nlgeom=YES, inc=1000\n*Dynamic, direct\n 0.002, 0.5") \
        .replace("type=VELOCITY\n DRIVEN, 3, 3, 0.01", "type=ACCELERATION\n DRIVEN, 3, 3, 0.04")
    for label, text, ref, mean_only in (
            ("explicit, TYPE=VELOCITY", src, lambda z: -0.01 if z < 0.5 else 0.0, True),
            ("implicit, TYPE=ACCELERATION", accel, lambda z: -0.04 * (0.5 - z) if z < 0.5 else 0.0,
             False)):
        tmp_src = os.path.join(tmp, "velocity_bc_bar_src.inp")
        with open(tmp_src, "w") as fh:
            fh.write(text)
        inp = os.path.join(tmp, "velocity_bc_bar.inp")
        convert(tmp_src, inp)
        d, status, out = run_ccx(ccx, env, inp)
        s = frd_last(os.path.join(d, "job.frd"), "STRESS")
        u = frd_last(os.path.join(d, "job.frd"), "DISP")
        shutil.rmtree(d, ignore_errors=True)
        if status != "solved" or not s or 1 not in u:
            print(f"FAIL  velocity_bc_bar ({label}): did not solve ({status})")
            print("\n".join(l for l in out.splitlines() if "ERROR" in l)[:400])
            failures += 1
            continue
        line = [(k / 100.0, s[4 * k + 1][2]) for k in range(101)]     # S33 along the edge x=y=0
        peak = abs(ref(0.0))
        diff = [v - ref(z) for z, v in line if 0.1 <= z <= 0.4]
        mean, worst = abs(sum(diff) / len(diff)) / peak, max(abs(x) for x in diff) / peak
        ahead = max(abs(v) for z, v in line if z >= 0.6) / peak
        ok = (mean < 0.02 if mean_only else worst < 0.05) and ahead < 0.01 and \
            abs(u[1][2] - 0.005) < 1e-9
        print(f"{'PASS' if ok else 'FAIL'}  velocity_bc_bar ({label}): driven end u = "
              f"{u[1][2]:.6f} (0.005); wave stress behind the front {mean * 100:.1f}% off on "
              f"average ({worst * 100:.1f}% at worst), {ahead * 100:.2f}% ahead of it")
        failures += 0 if ok else 1

    # --- displacement BCs without AMPLITUDE: Abaqus' default amplitude --------------------
    # Abaqus/Standard ramps a displacement BC without an amplitude in every procedure, where
    # ccx steps it in dynamics, *VISCO and transient coupled steps; loads keep the
    # procedure's default (STEP there) in both.  One bar is driven at its top by such a BC
    # (0.01, then 0.03 in a second step), the other loaded at its top by a *CLOAD without an
    # amplitude: the driven top must follow the ramps at every increment, the loaded one
    # take its load at once - in *DYNAMIC overshooting to about twice its static extension
    # 0.004, in *VISCO sitting there from the first increment, in the coupled step (which
    # ccx 2.23 solves with inertia) well above the 0.0004 a ramp would give at t = 0.1.
    # Abaqus/Explicit ignores the value of such a BC and holds the DOF (zero velocity): the
    # driven top stays at 0, and the loaded top, held by one in the second step, stays where
    # the first step left it.
    src = open(os.path.join(EXAMPLES, "default_amplitude_bars.inp")).read()
    dyn = "*Dynamic, direct\n 0.005, 1."
    visco = src.replace(dyn, "*Visco, cetol=0.001\n 0.1, 1.").replace(
        "*Density\n 0.15625\n", "*Density\n 0.15625\n*Creep, law=TIME\n 1e-30, 1., 0.\n")
    coupled = src.replace(dyn, "*Coupled Temperature-displacement\n 0.1, 1.") \
        .replace("type=C3D8,", "type=C3D8T,") \
        .replace("*Density\n 0.15625\n", "*Density\n 0.15625\n*Conductivity\n 1.\n*Specific Heat\n 1.\n") \
        .replace("**\n*Step, name=PULL", "*Nset, nset=ALL, generate\n 1, 120, 1\n*Initial Conditions, "
                 "type=TEMPERATURE\n ALL, 0.\n**\n*Step, name=PULL")
    explicit = src.replace(dyn, "*Dynamic, explicit\n , 1.").replace(
        "DRIVEN_TOP, 3, 3, 0.03\n", "DRIVEN_TOP, 3, 3, 0.03\n LOADED_TOP, 3, 3\n")
    for label, text in (("*DYNAMIC", src), ("*VISCO", visco),
                        ("*COUPLED TEMPERATURE-DISPLACEMENT", coupled), ("*DYNAMIC, EXPLICIT", explicit)):
        tmp_src = os.path.join(tmp, "default_amplitude_bars_src.inp")
        with open(tmp_src, "w") as fh:
            fh.write(text)
        inp = os.path.join(tmp, "default_amplitude_bars.inp")
        convert(tmp_src, inp)
        d, status, out = run_ccx(ccx, env, inp)
        driven = dat_history(os.path.join(d, "job.dat"), "displacements", "DRIVEN_TOP")
        loaded = [(t, rows[0][2]) for t, rows in
                  dat_history(os.path.join(d, "job.dat"), "displacements", "LOADED_TOP")]
        shutil.rmtree(d, ignore_errors=True)
        first = [u for t, u in loaded if t <= 1.0 + 1e-9]
        second = [u for t, u in loaded if t > 1.0 + 1e-9]
        if status != "solved" or not driven or abs(driven[-1][0] - 2.0) > 1e-6 or not first or \
                not second:
            print(f"FAIL  default_amplitude_bars ({label}): did not solve ({status})")
            print("\n".join(l for l in out.splitlines() if "ERROR" in l)[:400])
            failures += 1
            continue
        if label.endswith("EXPLICIT"):
            ref = lambda t: 0.0                                              # noqa: E731
            spread = max(second) - min(second)
            load_ok = spread <= 1e-12 * abs(second[0]) and abs(second[0] - first[-1]) <= \
                1e-12 * abs(first[-1]) and abs(first[-1]) > 1e-5
            what = (f"loaded top held at {second[0]:.6g} through step 2 (spread {spread:.1e}; step 1 "
                    f"ended at {first[-1]:.6g})")
        else:
            ref = lambda t: 0.01 * t if t <= 1.0 + 1e-9 else 0.01 + 0.02 * (t - 1.0)  # noqa: E731
            if label == "*DYNAMIC":
                load_ok, what = max(first) > 1.6 * 0.004, f"loaded top peaks at {max(first) / 0.004:.2f} x static"
            elif label == "*VISCO":
                load_ok = abs(first[0] - 0.004) < 1e-3 * 0.004
                what = f"loaded top {first[0]:.6g} at the first increment (static 0.004)"
            else:
                load_ok = first[0] > 0.5 * 0.004
                what = f"loaded top {first[0]:.6g} at t = 0.1 (a ramp: about 0.0004)"
        dev = max(abs(r[2] - ref(t)) for t, rows in driven for r in rows)
        ok = dev < 1e-9 and load_ok
        print(f"{'PASS' if ok else 'FAIL'}  default_amplitude_bars ({label}): driven top within "
              f"{dev:.1e} of {'0' if label.endswith('EXPLICIT') else 'the ramps 0 -> 0.01 -> 0.03'} "
              f"at {len(driven)} increments; {what}")
        failures += 0 if ok else 1

    # --- output requests at beam nodes: field output for a node set, history at a node ----
    # ccx 2.23 writes a model with beams to the .frd expanded to 3-D, without the original
    # beam nodes, so a *NODE FILE for a set of them writes empty blocks (shown below without
    # OUTPUT=2D).  This checks the tip displacements the .frd gets with the OUTPUT=2D abq2ccx
    # adds, the mid-span history in the .dat (*NODE PRINT), and that both follow the
    # *TIME POINTS the deck's NUMBER INTERVAL = 4 became.
    inp = os.path.join(tmp, "beam_output.inp")
    convert(os.path.join(EXAMPLES, "beam_output_requests.inp"), inp)
    e, nu, p, length = 210000.0, 0.3, 1000.0, 240.0
    inertia, area = 10.0 * 20.0 ** 3 / 12, 200.0
    shear = p / (10 * (1 + nu) / (12 + 11 * nu) * e / (2 * (1 + nu)) * area)  # 1 / (k G A) * P
    ref_tip = -(p * length ** 3 / (3 * e * inertia) + shear * length)
    ref_mid = -(p * (length / 2) ** 2 * 2.5 * length / (6 * e * inertia) + shear * length / 2)
    d, status, out = run_ccx(ccx, env, inp)
    tip, _ = frd_displacement_history(os.path.join(d, "job.frd"), 25) if status == "solved" else ([], 0)
    mid = dat_displacement_history(os.path.join(d, "job.dat"), 13) if status == "solved" else []
    shutil.rmtree(d, ignore_errors=True)
    bare = os.path.join(tmp, "beam_output_3d.inp")
    with open(inp) as fi, open(bare, "w") as fo:
        fo.write(fi.read().replace(", OUTPUT=2D", ""))
    d, status3d, _ = run_ccx(ccx, env, bare)
    tip3d, empty3d = frd_displacement_history(os.path.join(d, "job.frd"), 25)
    shutil.rmtree(d, ignore_errors=True)
    if len(tip) != 4 or len(mid) != 4:
        print(f"FAIL  beam_output_requests: {len(tip)} tip displacements in the .frd and "
              f"{len(mid)} mid-span ones in the .dat, expected 4 each ({status})")
        print("\n".join(l for l in out.splitlines() if "ERROR" in l))
        failures += 1
    else:
        times = [t for t, _ in tip]
        d_tip, d_mid = abs(tip[-1][1][1] - ref_tip) / abs(ref_tip), abs(mid[-1][1] - ref_mid) / abs(ref_mid)
        ok = (all(abs(t - k / 4) < 1e-9 for k, t in enumerate(times, 1)) and d_tip < 0.02 and
              d_mid < 0.02 and status3d == "solved" and not tip3d and empty3d == 4)
        print(f"{'PASS' if ok else 'FAIL'}  beam_output_requests (*NODE OUTPUT at B32 nodes): .frd tip "
              f"deflection {tip[-1][1][1]:+.4f} (beam theory {ref_tip:+.4f}, {d_tip * 100:.1f}% diff) "
              f"at t = {', '.join(f'{t:g}' for t in times)}; .dat mid-span {mid[-1][1]:+.4f} (beam "
              f"theory {ref_mid:+.4f}, {d_mid * 100:.1f}% diff); without OUTPUT=2D {empty3d} empty "
              f".frd blocks")
        failures += 0 if ok else 1

    # --- Abaqus' preselected and default field output ---------------------------------
    # A bar in tension with only the two requests Abaqus/CAE writes (*Output, field / history,
    # variable=PRESELECT): ccx has no preselected output and wrote the mesh only; abq2ccx
    # writes *NODE FILE U, RF and *EL FILE S, E.  Uniform stress: u_x = P L / (E A), S11 =
    # P / A, E11 = S11 / E, and the reactions at x = 0 sum to -P.
    inp = os.path.join(tmp, "preselect_output_bar.inp")
    convert(os.path.join(EXAMPLES, "preselect_output_bar.inp"), inp)
    d, status, out = run_ccx(ccx, env, inp)
    frd = os.path.join(d, "job.frd")
    disp, forc = frd_blocks(frd, "DISP"), frd_blocks(frd, "FORC")
    stress, strain = frd_blocks(frd, "STRESS"), frd_blocks(frd, "TOSTRAIN")
    shutil.rmtree(d, ignore_errors=True)
    if status != "solved" or not (len(disp) == len(forc) == len(stress) == len(strain) == 1):
        print(f"FAIL  preselect_output_bar: {status}; .frd blocks DISP {len(disp)}, FORC "
              f"{len(forc)}, STRESS {len(stress)}, TOSTRAIN {len(strain)} (expected one each)")
        failures += 1
    else:
        ref_u, ref_s = 1000.0 * 100.0 / (210000.0 * 100.0), 10.0
        tip_u = [disp[0][1][n][0] for n in (41, 42, 43, 44)]
        rf = sum(forc[0][1][n][0] for n in (1, 2, 3, 4))
        s11 = [v[0] for v in stress[0][1].values()]
        e11 = [v[0] for v in strain[0][1].values()]
        worst = max([abs(u / ref_u - 1) for u in tip_u] + [abs(x / ref_s - 1) for x in s11] +
                    [abs(x * 210000.0 / ref_s - 1) for x in e11] + [abs(rf / -1000.0 - 1)])
        ok = worst < 1e-3
        print(f"{'PASS' if ok else 'FAIL'}  preselect_output_bar (*Output, field, variable=PRESELECT):"
              f" .frd u_x = {tip_u[0]:.7f} (P L / E A = {ref_u:.7f}), S11 = {min(s11):.4f}..."
              f"{max(s11):.4f} (10), sum RF_x = {rf:+.1f} (-1000); worst {worst * 100:.3f}% off")
        failures += 0 if ok else 1

    # An explicit step without any output request: Abaqus writes its preselected output at 20
    # intervals; ccx ignores *TIME POINTS in explicit dynamics, so abq2ccx sets a FREQUENCY
    # from ccx's own stable increment.  The bar moves at v0 towards its support when the step
    # starts: the free end keeps v0 until the support's wave arrives at L / c (c = sqrt(E /
    # rho)), then moves back to 0 at 2 L / c, the end of the step.
    inp = os.path.join(tmp, "explicit_default_output_bar.inp")
    convert(os.path.join(EXAMPLES, "explicit_default_output_bar.inp"), inp)
    with open(inp) as fh:
        freq = re.search(r"\*NODE FILE, FREQUENCY=(\d+)", fh.read())
    d, status, out = run_ccx(ccx, env, inp)
    disp, velo = frd_blocks(os.path.join(d, "job.frd"), "DISP"), frd_blocks(os.path.join(d, "job.frd"), "VELO")
    shutil.rmtree(d, ignore_errors=True)
    v0, length, c = -1000.0, 200.0, math.sqrt(210000.0 / 7.85e-9)
    if status != "solved" or not freq or not 20 <= len(disp) <= 23 or len(velo) != len(disp):
        print(f"FAIL  explicit_default_output_bar: {status}, {len(disp)} DISP / {len(velo)} VELO "
              f"blocks (expected 20-23 each), FREQUENCY {freq.group(1) if freq else 'none'}")
        failures += 1
    else:
        tip = [(t, sum(v[n][0] for n in (81, 82, 83, 84)) / 4) for t, v in disp]
        early = [abs(u / (v0 * t) - 1) for t, u in tip if t < 0.8 * length / c]
        peak, last = min(u for _, u in tip), tip[-1][1]
        ref = v0 * length / c
        ok = (max(early) < 1e-3 and abs(peak / ref - 1) < 0.05 and abs(last) < 0.02 * abs(ref)
              and abs(tip[-1][0] - 2 * length / c) < 1e-9)
        print(f"{'PASS' if ok else 'FAIL'}  explicit_default_output_bar (no *Output request, "
              f"*DYNAMIC, EXPLICIT): FREQUENCY={freq.group(1)}, {len(disp)} .frd frames for "
              f"Abaqus' 20 intervals; tip u = v0 t to {max(early) * 100:.2f}% before the wave "
              f"arrives, peak {peak:+.5f} (v0 L / c = {ref:+.5f}, {abs(peak / ref - 1) * 100:.1f}% "
              f"off), {last:+.6f} at 2 L / c (0)")
        failures += 0 if ok else 1

    # Abaqus' preselected contact output: two steel blocks pressed together through a
    # frictionless face-to-face pair, on symmetry planes (uniaxial stress), with the CAE
    # requests in step 1 and none in step 2, which carries them over.  ccx gets *CONTACT FILE
    # CDIS, CSTR in both steps; the contact pressure at the upper block's nine bottom nodes
    # must be the applied pressure, 10 and then 20, and zero everywhere else.
    inp = os.path.join(tmp, "preselect_contact_blocks.inp")
    convert(os.path.join(EXAMPLES, "preselect_contact_blocks.inp"), inp)
    d, status, out = run_ccx(ccx, env, inp)
    cont = frd_blocks(os.path.join(d, "job.frd"), "CONTACT")
    shutil.rmtree(d, ignore_errors=True)
    ends = [vals for t, vals in cont if min(abs(t - 1.0), abs(t - 2.0)) < 1e-9]
    pressed = [{n: v for n, v in vals.items() if any(v)} for vals in ends]
    if status != "solved" or len(cont) != 4 or len(ends) != 2 or not all(pressed):
        print(f"FAIL  preselect_contact_blocks: {status}, {len(cont)} CONTACT blocks (expected 4, "
              f"two increments in each step), {[len(p) for p in pressed]} nodes in contact at the "
              f"ends of the steps (expected 9 each)")
        failures += 1
    else:
        cpress = [[v[3] for v in p.values()] for p in pressed]
        worst = max(abs(x / ref - 1) for ref, xs in zip((10.0, 20.0), cpress) for x in xs)
        ok = all(set(p) == set(range(101, 110)) for p in pressed) and worst < 1e-3
        print(f"{'PASS' if ok else 'FAIL'}  preselect_contact_blocks (*Output, field, "
              f"variable=PRESELECT with *CONTACT PAIR): .frd CPRESS at the {len(pressed[0])} slave "
              f"nodes {min(cpress[0]):.4f}...{max(cpress[0]):.4f} (10), then {min(cpress[1]):.4f}..."
              f"{max(cpress[1]):.4f} (20) in the carried step; worst {worst * 100:.3f}% off")
        failures += 0 if ok else 1

    # --- CPS4I / CPE4I as C3D8I slabs: pure bending, exactly -----------------------
    # ccx has no incompatible-mode plane element; abq2ccx writes each as a one-element-thick
    # C3D8I slab (top nodes tied in plane, thickness DOF held; plane stress through an ORTHO
    # material with no thickness coupling).  Abaqus' four-mode CPS4I represents pure bending
    # on rectangles exactly, so the 5 x 2 cantilever under an end couple must give beam
    # theory: tip u_y = M L^2 / (2 E' I) (E' = E plane stress, E / (1 - nu^2) plane strain),
    # sigma_xx = -M y / I at every integration point, sigma_zz = 0 / nu sigma_xx.
    for kind, ep in (("CPS4I", 1000.0), ("CPE4I", 1000.0 / (1 - 0.3 ** 2))):
        src = os.path.join(tmp, f"slab_{kind}_src.inp")
        with open(src, "w") as fh:
            fh.write(open(os.path.join(EXAMPLES, "cps4i_slab_bending.inp")).read().replace("CPS4I", kind))
        inp = os.path.join(tmp, f"slab_{kind}.inp")
        convert(src, inp)
        d, status, out = run_ccx(ccx, env, inp)
        tip = dat_displacement(os.path.join(d, "job.dat"), 12)
        s10 = dat_el_stress(os.path.join(d, "job.dat"), 10)        # top layer, y from 0 to 0.5
        shutil.rmtree(d, ignore_errors=True)
        if status != "solved" or tip is None or s10 is None:
            print(f"FAIL  cps4i_slab ({kind}): did not solve ({status})")
            failures += 1
            continue
        eye = 0.5 / 12.0                                       # t h^3 / 12, t = 0.5, h = 1
        ref_u = 1.0 * 10.0 ** 2 / (2 * ep * eye)
        ref_s = -1.0 * 0.25 / eye                              # element centroid y = 0.25
        ref_z = 0.0 if kind == "CPS4I" else 0.3 * ref_s
        err = max(abs(tip[1] / ref_u - 1), abs(s10[0] / ref_s - 1), abs(s10[2] - ref_z) / abs(ref_s),
                  abs(s10[1]) / abs(ref_s), abs(s10[3]) / abs(ref_s))
        ok = err < 1e-5
        print(f"{'PASS' if ok else 'FAIL'}  cps4i_slab ({kind} -> C3D8I slab, end couple): tip u_y "
              f"{tip[1]:.6f} (beam theory {ref_u:.6f}), sigma_xx {s10[0]:.5f} (-M y / I = {ref_s:.5f}), "
              f"sigma_zz {s10[2]:.5f}; max deviation {err:.1e}"
              + (" (a plain CPS4 gives 39 % of the deflection)" if kind == "CPS4I" else ""))
        failures += 0 if ok else 1

    # --- shell pressure on SPOS / SNEG faces and element-based P, against Navier --------
    # Abaqus pushes a surface pressure against the surface normal (SPOS along -n, SNEG along
    # +n) and an element-based *DLOAD P along +n (Abaqus 2017 shell element library); ccx's
    # *DLOAD P on a shell pushes along +n, so abq2ccx flips the sign on SPOS.  Simply
    # supported square S8R plate, a = 1, t = 0.01, p = 1: centre deflection 0.00406 p a^4 / D.
    dee = 1.0e7 * 0.01 ** 3 / (12 * (1 - 0.3 ** 2))
    ref = 0.00406235 / dee
    for variant, subs, sign in (("*DSLOAD on SPOS", (), -1.0),
                                ("*DSLOAD on SNEG", (("PLATE, SPOS", "PLATE, SNEG"),), 1.0),
                                ("*DLOAD P", (("*DSLOAD\nLOADED, P, 1.", "*DLOAD\nPLATE, P, 1."),), 1.0)):
        u = solve("shell_pressure_sides", subs=subs, nodes=(145,))
        if not u:
            failures += 1
            continue
        w = u[145][2]
        ok = abs(w / (sign * ref) - 1) < 0.02
        print(f"{'PASS' if ok else 'FAIL'}  shell_pressure_sides ({variant}): centre w {w:+.5e} "
              f"(Navier {sign * ref:+.5e}, {abs(w / (sign * ref) - 1) * 100:.1f}% off)")
        failures += 0 if ok else 1

    # --- *KINEMATIC without DOF lines: all DOFs, like a rigid body ---------------------------
    # Abaqus couples every DOF when *KINEMATIC has no data lines; ccx would couple none, so
    # abq2ccx writes '1, 3', which carries the reference node's rotations too: the coupled end
    # face of a C3D8 cantilever under a reference-node force and two moments must move exactly
    # as with *RIGID BODY on the same face.
    res = {}
    for kind, subs in (("kinematic", ()), ("rigid", (("*COUPLING, CONSTRAINT NAME=CAP, REF NODE=REF, "
                                                      "SURFACE=END\n*KINEMATIC\n",
                                                      "*RIGID BODY, NSET=FACE, REF NODE=REF\n"),))):
        src = os.path.join(tmp, f"kin_{kind}_src.inp")
        text = open(os.path.join(EXAMPLES, "kinematic_all_dofs.inp")).read()
        for a, b in subs:
            text = text.replace(a, b)
        with open(src, "w") as fh:
            fh.write(text)
        inp = os.path.join(tmp, f"kin_{kind}.inp")
        convert(src, inp)
        d, status, out = run_ccx(ccx, env, inp)
        res[kind] = dat_displacements(os.path.join(d, "job.dat")) if status == "solved" else {}
        shutil.rmtree(d, ignore_errors=True)
    nodes = [n for n in range(1, 100) if n in res["kinematic"] and n in res["rigid"]]
    if len(nodes) == 99:
        scale = max(abs(x) for n in nodes for x in res["rigid"][n])
        err = max(abs(a - b) for n in nodes for a, b in zip(res["kinematic"][n], res["rigid"][n])) / scale
        ok = err < 1e-6 and scale > 1e-3
        print(f"{'PASS' if ok else 'FAIL'}  kinematic_all_dofs (bare *KINEMATIC -> '1, 3'): 99 node "
              f"displacements vs *RIGID BODY, max difference {err:.1e} of max |u| {scale:.4f}")
        failures += 0 if ok else 1
    else:
        print(f"FAIL  kinematic_all_dofs: did not solve ({len(nodes)} nodes compared)")
        failures += 1

    # --- assembly flattening: a turned instance against the same model written flat -------
    # Two instances of one part, the second translated and turned 90 degrees about z, with an
    # orthotropic material at 45 degrees (turned with the instance: an unturned orientation
    # moves the nodes by 9 % of max |u|), instance-qualified loads and a surface pressure.
    # The flat twin numbers the instances 1-20 / 21-40 as the converter does and gives the
    # second one's coordinates and orientation turned by hand.
    res, xyz = {}, {}
    for deck in ("assembly_rotated_instances", "assembly_rotated_instances_flat"):
        inp = os.path.join(tmp, deck + ".inp")
        convert(os.path.join(EXAMPLES, deck + ".inp"), inp)
        xyz[deck] = A.convert_file(os.path.join(EXAMPLES, deck + ".inp")).geometry.nodes
        d, status, out = run_ccx(ccx, env, inp)
        res[deck] = dat_displacements(os.path.join(d, "job.dat")) if status == "solved" else {}
        shutil.rmtree(d, ignore_errors=True)
    ua, uf = res["assembly_rotated_instances"], res["assembly_rotated_instances_flat"]
    if len(uf) == 40 and set(ua) == set(uf):
        scale = max(abs(x) for v in uf.values() for x in v)
        err = max(abs(a - b) for n in uf for a, b in zip(ua[n], uf[n])) / scale
        cerr = max(abs(a - b) for n in uf for a, b in zip(xyz["assembly_rotated_instances"][n],
                                                          xyz["assembly_rotated_instances_flat"][n]))
        ok = err < 1e-6 and cerr < 1e-9
        print(f"{'PASS' if ok else 'FAIL'}  assembly_rotated_instances (*PART / *INSTANCE flattening, "
              f"a turned instance): 40 nodes at the hand-flattened coordinates ({cerr:.0e}), "
              f"displacements max difference {err:.1e} of max |u|")
        failures += 0 if ok else 1
    else:
        print(f"FAIL  assembly_rotated_instances: the two models printed different nodes "
              f"({len(ua)} / {len(uf)})")
        failures += 1

    # --- other decks: confirm they are accepted and solve ----------------------
    for name in ("composite_shell", "assembly_two_blocks"):
        inp = os.path.join(tmp, name + ".inp")
        convert(os.path.join(EXAMPLES, name + ".inp"), inp)
        d, status, out = run_ccx(ccx, env, inp)
        shutil.rmtree(d, ignore_errors=True)
        if status == "solved":
            print(f"PASS  {name}: accepted by ccx and solved")
        else:
            print(f"FAIL  {name}: did not solve ({status})")
            print("      " + " / ".join(l.strip() for l in out.splitlines()
                                        if "ERROR" in l or "convergence" in l.lower())[:200])
            failures += 1

    shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{'All checks passed.' if not failures else str(failures) + ' check(s) failed.'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
