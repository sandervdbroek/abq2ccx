#!/usr/bin/env python3
"""End-to-end validation: convert the example decks and actually run them in CalculiX.

This is the proof that the converter produces *runnable, correct* CalculiX input — not
just structurally-valid text.  It auto-detects a ``ccx`` binary (including the one
bundled with FreeCAD) and checks results against reference values: the NAFEMS LE10
stress (also with the pressure carried by surface elements, which ccx does not have),
the tip deflections of circular-, pipe- and box-section cantilevers against beam
theory, beams under a general or an I section run as ccx's U1 element (cantilevers about
both axes with I12 nonzero, their twist and frequencies, the unsymmetric I and hexagonal
cantilevers of Abaqus' Verification Guide, an I-section portal frame under gravity and line
loads) against beam theory, Abaqus' reference values and a direct-stiffness frame solution,
general beam sections with a ccx profile (a RECT cantilever, NAFEMS NL6 under NLGEOM) against
beam theory and NL6's published answers, a shell plate rigidly coupled to a loaded reference point against the same plate
built from solids, coupled bars whose coupled nodes also carry BCs against the same
constraints written without a coupling, a bar whose rigid end cap carries BCs on its nodes
against the same BCs written on its reference point, circular-section beams with a held
twist and a prescribed rotation against beam theory, a circular-section beam in an explicit
dynamic step against its static deflection (and, without the converter's increment cap, its
NaN results, which the solve judge must find in the .dat and the .frd), the natural
frequencies and buckling loads of planar (B21) beams with a rectangular and a circular
section, per-element *DISTRIBUTION
orientations (a C3D8 plate and a composite S8R panel) against the same models written with
one orientation per element, the material axes of plain shells, membranes and continuum
shells whose orientation leaves their plane or has no rotation line (the ply's stiffness at
Abaqus' direction), of hoop-wound S4 and SC8R cylinders (thin-wall theory), of spheres of
orthotropic S4R and SC8R shells and SC8R plies with a spherical system (membrane theory) and of a
fibre-steered strip whose distribution axes leave the
plate (the same strip with them in it), initial stresses and plastic strains given in a turned
and a cylindrical orientation (a free cube's strains, an annulus' closed-form displacement) and
on a plane-stress element (tau / G), deformation-plasticity bars on oriented sections (the same
bars without an orientation), quadratic membranes (strips in tension, also under NLGEOM, and
a pressurized sphere) against uniaxial stress and thin-wall theory, a clamped beam and plate after a later step's *BOUNDARY,
OP=NEW, the thermal strains of isotropic materials with an orthotropic / anisotropic
expansion (including the engineering shear coefficients of an anisotropic one) and of every
*Elastic form beside an anisotropic one (also under NLGEOM), a heated
cube and circular-section beam with no initial temperatures, and the loads ccx has no card
for — surface tractions (Cook's membrane, Lame's cylinder) and beam line loads (cantilevers
against beam theory) — applied as consistent nodal forces, also on nodes with a *TRANSFORM
(local axes), which must match the same models without one, body loads written with blank
fields (gravity on a column, a spinning disc) against statics and the rotating-disc
solution, *MPC joints, levers and links
against statics — PIN, TIE and LINK also on nodes with a *TRANSFORM, against the same model
without it (linear and NLGEOM) — connector elements (JOIN, WELD, BEAM, LINK, HINGE) against those, beam
theory and exact statics — also on nodes with a *TRANSFORM, against the same models without
it (linear and NLGEOM) — velocity / acceleration boundary conditions against their
time integral and the wave they send through a bar, displacement boundary conditions without
an amplitude ramped as Abaqus/Standard ramps them (implicit dynamics, *VISCO, a transient
coupled step) and held as Abaqus/Explicit holds them, while loads keep their procedure's
default (a stepped load overshoots), transient coupled temperature-displacement steps run
without inertia as in Abaqus/Standard (bars under gravity and point masses, then heated or
loaded at once, against statics and the same model's heat transfer), field and history
output requested at
beam nodes (the .frd and .dat values against beam theory), and the field output Abaqus
preselects: a bar in tension with only Abaqus/CAE's *Output, variable=PRESELECT requests,
and a bar impact in an explicit step without any output request (20 output frames, the
free end against 1-D wave theory), CPS4I / CPE4I cantilevers written as C3D8I slabs under
an end couple against beam theory (deflection and stresses), shell pressure on the SPOS and
SNEG faces and element-based against the Navier plate solution (the sign of each), and on
shell and membrane spheres and a cylinder against the pressure force on the reference surface
and thin-wall theory, a bare
*KINEMATIC (all DOFs) against *RIGID BODY, an assembly with a turned instance against
the same model written flat, bolts whose pre-tension node (or beam cut) a one-member set
names against F L / E A (the card that names them by number), truss, beam and U1 bolts cut
by a pre-tension section (loaded, then held while the joint is pulled) against the bolt and
member in parallel, a cut cantilever against the uncut one, a coupling's REF NODE= forms at
the assembly level against the model written flat, and rigid tools:
a rigid flat punch (rigid elements, and
the same face as an analytical surface) against the penalty contact law and a punch given
the motion node by node, also turned under NLGEOM, a block tied to a turning rigid plate, a
rigid plate's MASS and ROTARYI on springs against its frequencies, (--approximate) a
faceted analytical sphere against Hertz, user materials: renamed so ccx stops rather than
run its own routines, and (--abaqus-umat) through ccx's Abaqus-UMAT interfaces, whose stock
example UMAT gives E eps and E ln(1 + eps); the results digest of --run against the
beam, buckling and statics references above; *EL FILE requests ccx stopped or crashed on
(ENER beside U1 beams, SDV where ccx has no nodal state variables) against beam theory, 100 / E
and the same decks without them; *EL PRINT ELKE in a linear static and a *BUCKLE step against
u0 cos 100 t and the same deck without it, and after a *FREQUENCY step against A cos 100 t and
u0; *CONTACT PRINT CFN for every pair against a rigid punch's reaction; and decks a code review
found converted wrongly:
a planar beam's coupled tip, a velocity BC a coupling implies, amplitude points 1e-4 apart at
time 100, a symmetric layup tied to a rigid plate, --approximate beside a blank Poisson's ratio,
a part's pre-tension section and distributing coupling in turned instances, and a static step
after a linear perturbation step (the state before it again; also a transformed beam joint's
rotations and moments, a zero BC ramped in a *DYNAMIC step and a JOIN off a beam node, against
the same decks without the perturbation step's BC or the *TRANSFORM; and perturbation steps or
*BOUNDARY, FIXED after one with its own BCs or a *BUCKLE step, against the decks without that
step), a coupling's INFLUENCE
RADIUS against the coupling on the nodes within it, rotations coupled in an ORIENTATION's
axes against the model turned into them, and *DLOAD BX / BY / BZ on shells (a strip against
its C3D8 twin and the GRAV and pressure forms, also over steps; the Scordelis-Lo roof against
its published deflection).

Every check reads something ccx must solve for (a free node's motion, a reaction, a stress,
an eigenvalue), and a run counts as solved only if ccx's output shows each step setting up
its system (abq2ccx.classify_ccx_run): a step that sets up none still ends in "Job finished".
A ratio over a scale from ccx's output (ccx_ratio) fails its check when that scale is 0.

    python validate_with_ccx.py

Exits 0 if every available check passes (or ccx is not installed — then it skips with
a clear message), 1 if a check fails.  Requires CalculiX; install it or FreeCAD.
"""

import itertools
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
    """Return (ccx_path, extra_env) or (None, {}), searched as --run searches: $CCX, PATH,
    FreeCAD, PrePoMax and bConverged installs, Homebrew, MacPorts."""
    return A.find_ccx()


def convert(path, out_inp, approximate=False, abaqus_umat=False):
    """Convert ``path`` to ``out_inp``; returns the report and the converter."""
    rep = A.Report()
    blocks = A.read_blocks(path, rep)
    conv = A.Converter(rep, type("O", (), {"solid_dof": False, "approximate": approximate,
                                           "abaqus_umat": abaqus_umat})())
    body = conv.convert(blocks)                     # convert first: the header lists warnings
    text = "\n".join(rep.header_comment_lines() + body) + "\n"
    with open(out_inp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return rep, conv


def run_ccx(ccx, env, inp_path):
    """Run ccx; return (workdir, status, combined output) with status from
    abq2ccx.classify_ccx_run ("solved" / "unsolved" / "nonfinite" / "accepted" / "failed")."""
    d = tempfile.mkdtemp(prefix="ccxval_")
    shutil.copy(inp_path, os.path.join(d, "job.inp"))
    full_env = dict(os.environ)
    full_env.update(env)
    try:
        r = subprocess.run([ccx, "job"], cwd=d, env=full_env, capture_output=True,
                           encoding="utf-8", errors="replace", timeout=600)
        status = A.classify_ccx_run(r.returncode, r.stdout, r.stderr, os.path.join(d, "job"))
        out = r.stdout + r.stderr
        if status == "unsolved":                # the checks print the *ERROR lines of a failure
            idle = ", ".join(map(str, A.ccx_unsolved_steps(r.stdout)))
            out += f"\n*ERROR (validate_with_ccx): step {idle} set up no system of equations\n"
        return d, status, out
    except Exception as exc:  # noqa: BLE001
        return d, "failed", f"failed to launch ccx: {exc}"


def frd_stress(frd_path, node):
    """Extrapolated nodal stress vector at ``node`` from the first STRESS block of a ccx .frd
    file, or None."""
    first = next((off for _, _, name, off in A.frd_index(frd_path) if name == "STRESS"), None)
    vals = dict(A.frd_rows(frd_path, first)).get(node) if first is not None else None
    return vals[:6] if vals else None


def frd_displacement_history(frd_path, node):
    """[(time, (ux, uy, uz))] of every DISP block of a ccx .frd file that lists ``node``,
    and the number of DISP blocks that list no node at all."""
    blocks = frd_blocks(frd_path, "DISP")
    return [(time, tuple(vals[node][:3])) for time, vals in blocks if node in vals], \
        sum(1 for _, vals in blocks if not vals)


def frd_blocks(frd_path, name):
    """[(time, {node: values})] of every .frd result block called ``name`` (DISP, FORC,
    STRESS, TOSTRAIN, VELO ...)."""
    return [(time, dict(A.frd_rows(frd_path, off))) for _, time, n, off in A.frd_index(frd_path)
            if n == name]


def dat_tables(dat_path, title):
    """The rows of every .dat table or print block whose title starts with ``title``."""
    return [rows for _, t, _, _, rows in A.dat_blocks(dat_path) if t.startswith(title)]


def dat_displacements(dat_path):
    """{node: [ux, uy, uz]}: the last displacement *NODE PRINT wrote for each node in a ccx
    .dat file (empty if none; a transformed node counts only if printed with GLOBAL=YES)."""
    return {int(r[0]): r[1:] for rows in dat_tables(dat_path, "displacements") for r in rows
            if len(r) == 4}


def dat_displacement_history(dat_path, node):
    """Every displacement (ux, uy, uz) printed for ``node`` by *NODE PRINT in a ccx .dat
    file, in order (one per printed increment)."""
    return [r[1:] for rows in dat_tables(dat_path, "displacements") for r in rows
            if len(r) == 4 and r[0] == node]


def dat_el_stress(dat_path, elem):
    """Mean stress (sxx, syy, szz, sxy, sxz, syz) over the integration points of ``elem`` in
    the last *EL PRINT stress table of a ccx .dat file, or None."""
    rows = [r[2:] for r in (dat_tables(dat_path, "stresses") or [[]])[-1] if len(r) == 8 and r[0] == elem]
    return [sum(r[k] for r in rows) / len(rows) for k in range(6)] if rows else None


def dat_el_scalar(dat_path, title):
    """{element: value at its first integration point} from the last *EL PRINT table of a
    scalar (PEEQ, DUCT) whose heading starts with ``title`` in a ccx .dat file."""
    found = {}
    for r in (dat_tables(dat_path, title) or [[]])[-1]:
        if len(r) == 3:
            found.setdefault(int(r[0]), r[2])
    return found


def dat_eigen_table(dat_path, title):
    """The rows of the first eigenvalue table titled ``title`` in a ccx .dat file: the
    frequencies (cycles/time) under "E I G E N V A L U E   O U T P U T", or the factors
    under "B U C K L I N G   F A C T O R   O U T P U T"."""
    rows = (dat_tables(dat_path, title) or [[]])[0]
    return [r[3] if len(r) == 5 else r[1] for r in rows if len(r) in (2, 5)]


def dat_displacement(dat_path, node):
    """Last displacement (ux, uy, uz) printed for ``node`` by *NODE PRINT in a ccx .dat
    file, or None."""
    return dat_displacements(dat_path).get(node)


def ccx_ratio(num, den):
    """num / den for a scale taken from ccx's output (a twin's largest |u|, a reference run's
    eigenvalue or reaction).  A zero or non-finite scale, as when a deck's loads were all lost,
    gives inf, which fails the check, and says so, where num / den would stop the script."""
    if den and math.isfinite(den):
        return num / den
    print(f"      no scale from ccx: {num:.3g} / {den:.3g} counts as inf (did nothing move?)")
    return math.inf


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


def dat_node_blocks(dat_path, title="displacements"):
    """Every *NODE PRINT block of ``title`` in a ccx .dat file, in order, as {node: values}
    (all columns: six on a node with rotations, such as a U1 beam's)."""
    blocks, cur = [], None
    if not os.path.exists(dat_path):
        return blocks
    for ln in open(dat_path, encoding="utf-8", errors="replace"):
        if ln.strip().startswith(title):
            cur = {}
            blocks.append(cur)
            continue
        f = ln.split()
        if cur is not None and len(f) >= 4 and f[0].isdigit():
            cur[int(f[0])] = [float(x) for x in f[1:]]
        elif cur is not None and f:
            cur = None
    return blocks


def dat_solve_mode_blocks(dat_path):
    """The displacement *NODE PRINT blocks of a ccx .dat file as {node: values}, in order, split
    into the solves' and the eigenmodes' (those after an EIGENVALUE NUMBER heading in their
    step)."""
    solves, modes, eigen_step = [], [], None
    for step, title, _, _, rows in A.dat_blocks(dat_path):
        if title.startswith("E I G E N V A L U E    N U M B E R"):
            eigen_step = step
        elif title == "displacements":
            (modes if step == eigen_step else solves).append({int(r[0]): r[1:] for r in rows})
    return solves, modes


def frame2d(nodes, elems, fixed, loads, udl=()):
    """A plane Euler-Bernoulli frame by the direct stiffness method, with consistent loads
    (the exact nodal solution of beam theory).  ``nodes`` {id: (x, y)}; ``elems`` [(a, b, E,
    A, I)]; ``fixed`` {(node, dof)} with dof 1, 2 (translations) or 6 (the rotation);
    ``loads`` {(node, dof): value}; ``udl`` [(element index, qx, qy)] global loads per length.
    Returns {(node, dof): displacement}."""
    ids = sorted(nodes)
    idx = {(n, d): 3 * i + k for i, n in enumerate(ids) for k, d in enumerate((1, 2, 6))}
    size = 3 * len(ids)
    stiff = [[0.0] * size for _ in range(size)]
    force = [0.0] * size
    for key, v in loads.items():
        force[idx[key]] += v
    for j, (a, b, e_mod, area, inertia) in enumerate(elems):
        (xa, ya), (xb, yb) = nodes[a], nodes[b]
        length = math.hypot(xb - xa, yb - ya)
        c, s = (xb - xa) / length, (yb - ya) / length
        ea, ei = e_mod * area / length, e_mod * inertia / length ** 3
        local = [[0.0] * 6 for _ in range(6)]
        local[0][0] = local[3][3] = ea
        local[0][3] = local[3][0] = -ea
        bend = [[12, 6 * length, -12, 6 * length],
                [6 * length, 4 * length ** 2, -6 * length, 2 * length ** 2],
                [-12, -6 * length, 12, -6 * length],
                [6 * length, 2 * length ** 2, -6 * length, 4 * length ** 2]]
        at = (1, 2, 4, 5)
        for r in range(4):
            for q in range(4):
                local[at[r]][at[q]] = ei * bend[r][q]
        rot = [[0.0] * 6 for _ in range(6)]
        for o in (0, 3):
            rot[o][o], rot[o][o + 1], rot[o + 1][o], rot[o + 1][o + 1], rot[o + 2][o + 2] = c, s, -s, c, 1.0
        glob = [[sum(rot[p][r] * local[p][t] * rot[t][q] for p in range(6) for t in range(6))
                 for q in range(6)] for r in range(6)]
        dofs = [idx[(a, 1)], idx[(a, 2)], idx[(a, 6)], idx[(b, 1)], idx[(b, 2)], idx[(b, 6)]]
        for r in range(6):
            for q in range(6):
                stiff[dofs[r]][dofs[q]] += glob[r][q]
        for k, qx, qy in udl:
            if k == j:
                qa, qt = qx * c + qy * s, -qx * s + qy * c        # along, across the member
                fl = [qa * length / 2, qt * length / 2, qt * length ** 2 / 12,
                      qa * length / 2, qt * length / 2, -qt * length ** 2 / 12]
                for r in range(6):
                    force[dofs[r]] += sum(rot[p][r] * fl[p] for p in range(6))
    held = {idx[k] for k in fixed}
    free = [i for i in range(size) if i not in held]
    sol = _solve([[stiff[r][q] for q in free] for r in free], [force[r] for r in free])
    u = [0.0] * size
    for i, v in zip(free, sol):
        u[i] = v
    return {k: u[i] for k, i in idx.items()}


def i_profile(h, b, tf, tw):
    """Area, strong-axis and weak-axis second moments and the thin-walled torsion constant
    of a doubly symmetric I profile (the flanges b x tf, the web tw between them, as Abaqus
    takes it for J too)."""
    hw = h - 2 * tf
    return (2 * b * tf + hw * tw, (b * h ** 3 - (b - tw) * hw ** 3) / 12,
            (2 * tf * b ** 3 + hw * tw ** 3) / 12, (2 * b * tf ** 3 + hw * tw ** 3) / 3)


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
    return [(time, [r[1:] if len(r) == 4 and what != "total force" else r for r in rows])
            for _, title, s, time, rows in A.dat_blocks(dat_path)
            if title.startswith(what) and s == nset.upper()]


def pretension_bolt_deck(level="model"):
    """A bolt of two C3D8 along z (1 x 1, length 2, E 210000, nu 0), both ends held, cut at
    mid-length by a *PRE-TENSION SECTION whose node 99 is loaded by 1000: the cut closes
    F L / E A.  NODE= names the one-node set PT.  ``level`` "part" / "assembly": the bolt is a
    part with two instances, the second turned 90 degrees about x (its node 99 is global node
    198), and the card is the part's, or written at the assembly level for each instance,
    naming I1.PT and an assembly set of I2's node 99."""
    part = ["*NODE"] + [f"{1 + i + 2 * j + 4 * k}, {float(i)}, {float(j)}, {float(k)}"
                        for k in range(3) for j in range(2) for i in range(2)]
    part += ["99, 0.5, 0.5, 1.", "*ELEMENT, TYPE=C3D8, ELSET=BOLT", "1, 1, 2, 4, 3, 5, 6, 8, 7",
             "2, 5, 6, 8, 7, 9, 10, 12, 11", "*ELSET, ELSET=LOW", "1", "*NSET, NSET=ENDS",
             "1, 2, 3, 4, 9, 10, 11, 12", "*NSET, NSET=PT", "99", "*SURFACE, NAME=CUT", "LOW, S2",
             "*SOLID SECTION, ELSET=BOLT, MATERIAL=M"]
    card = ["*PRE-TENSION SECTION, SURFACE=CUT, NODE=PT", "0., 0., 1."]
    if level == "model":
        model, pre = part + card, [""]
    else:
        asm = ["*ASSEMBLY, NAME=A", "*INSTANCE, NAME=I1, PART=P", "*END INSTANCE", "*INSTANCE, NAME=I2, PART=P",
               "0., 5., 0.", "0., 5., 0., 1., 5., 0., 90.", "*END INSTANCE"]
        if level == "assembly":
            asm += ["*NSET, NSET=PT2, INSTANCE=I2", "99", "*PRE-TENSION SECTION, SURFACE=I1.CUT, NODE=I1.PT",
                    "0., 0., 1.", "*PRE-TENSION SECTION, SURFACE=I2.CUT, NODE=PT2", "0., -1., 0."]
        model = (["*PART, NAME=P"] + part + (card if level == "part" else []) + ["*END PART"] + asm
                 + ["*END ASSEMBLY"])
        pre = ["I1.", "I2."]
    step = (["*STEP", "*STATIC", "*BOUNDARY"] + [f"{p}ENDS, 1, 3" for p in pre] + ["*CLOAD"]
            + [f"{p}PT, 1, 1000." for p in pre] + [x for p in pre for x in (f"*NODE PRINT, NSET={p}PT", "U")]
            + ["*END STEP"])
    return "\n".join(model + ["*MATERIAL, NAME=M", "*ELASTIC", "210000., 0."] + step) + "\n"


def pretension_beam_deck(element="CUTEL", node="PT"):
    """Two B31 along x (RECT 1 x 1, length 1 each, E 210000), both ends clamped, the first the
    cut of a *PRE-TENSION SECTION (ELEMENT= its number or the one-element set CUTEL) whose
    node 99 (NODE= 99 or the one-node set PT) is loaded by 1000."""
    return "\n".join(["*NODE", "1, 0., 0., 0.", "2, 1., 0., 0.", "3, 2., 0., 0.", "99, 1., 0., 0.",
                      "*ELEMENT, TYPE=B31, ELSET=BOLT", "1, 1, 2", "2, 2, 3", "*ELSET, ELSET=CUTEL", "1",
                      "*NSET, NSET=PT", "99", "*BEAM SECTION, ELSET=BOLT, MATERIAL=M, SECTION=RECT",
                      "1., 1.", "0., 0., 1.", f"*PRE-TENSION SECTION, ELEMENT={element}, NODE={node}",
                      "*MATERIAL, NAME=M", "*ELASTIC", "210000., 0.", "*STEP", "*STATIC", "*BOUNDARY",
                      "1, 1, 6", "3, 1, 6", "*CLOAD", "99, 1, 1000.", "*NODE PRINT, NSET=PT", "U",
                      "*END STEP"]) + "\n"


def pretension_cut_deck(bolt="B31", cut=1, member="spring"):
    """A bolt of two elements along x (length 1 each, area 1, E 210000; node 1 held) beside a
    clamped member from node 1 to its end node 3 (a SPRINGA of stiffness 210000, or a T3D2 of
    area 2: the same), the bolt cut by a *PRE-TENSION SECTION, ELEMENT=``cut``, NODE=99.
    ``bolt``: "B31" (RECT 1 x 1), "U1" (a *BEAM GENERAL SECTION: ccx's U1) or "T3D2".  Step 1
    loads node 99 by 1000; step 2 holds it (*BOUNDARY, FIXED) and pulls node 3 by 3000."""
    beam = bolt != "T3D2"
    lines = ["*NODE", "1, 0., 0., 0.", "2, 1., 0., 0.", "3, 2., 0., 0.", "99, 5., 5., 0.",
             f"*ELEMENT, TYPE={'B31' if beam else 'T3D2'}, ELSET=BOLT", "1, 1, 2", "2, 2, 3",
             f"*ELEMENT, TYPE={'SPRINGA' if member == 'spring' else 'T3D2'}, ELSET=MEMBER", "3, 1, 3",
             "*NSET, NSET=PT", "99", "*NSET, NSET=WATCH", "3, 99", "*ELSET, ELSET=CUT", str(cut)]
    lines += {"B31": ["*BEAM SECTION, ELSET=BOLT, MATERIAL=M, SECTION=RECT", "1., 1.", "0., 0., 1."],
              "U1": ["*BEAM GENERAL SECTION, ELSET=BOLT, SECTION=GENERAL",
                     "1., 0.0833333333, 0., 0.0833333333, 0.1406", "0., 0., 1.", "210000., 105000."],
              "T3D2": ["*SOLID SECTION, ELSET=BOLT, MATERIAL=M", "1."]}[bolt]
    lines += ["*SPRING, ELSET=MEMBER", "", "210000."] if member == "spring" else \
        ["*SOLID SECTION, ELSET=MEMBER, MATERIAL=M", "2."]
    lines += [f"*PRE-TENSION SECTION, ELEMENT={cut}, NODE=PT", "*MATERIAL, NAME=M", "*ELASTIC", "210000., 0."]
    held = ["1, 1, 6", "3, 2, 3"] + (["3, 4, 6"] if member == "spring" and beam else []) + \
        ([] if beam else ["2, 2, 3"])
    out = ["*NODE PRINT, NSET=WATCH", "U", "*EL PRINT, ELSET=CUT", "S"]
    return "\n".join(lines + ["*STEP", "*STATIC", "*BOUNDARY"] + held + ["*CLOAD", "PT, 1, 1000."] + out
                     + ["*END STEP", "*STEP", "*STATIC", "*BOUNDARY, FIXED", "PT, 1, 1", "*CLOAD",
                        "3, 1, 3000."] + out + ["*END STEP"]) + "\n"


def pretension_bending_deck(cut=True):
    """A cantilever of two B31 along x (RECT 0.1 x 0.1, E 210000, nu 0; node 1 clamped) with an
    arm at its tip (node 3 to node 4 along y), the tip loaded across, out of plane and in
    torsion; with ``cut`` the first element is the cut of a *PRE-TENSION SECTION whose
    adjustment (node 99) is held at 0.  (A square section with nu = 0: ccx's knots, which make
    the sections at the cut rigid, then change nothing.)"""
    return "\n".join(["*NODE", "1, 0., 0., 0.", "2, 1., 0., 0.", "3, 2., 0., 0.", "4, 2., 0.2, 0.",
                      "99, 5., 5., 0.", "*ELEMENT, TYPE=B31, ELSET=BOLT", "1, 1, 2", "2, 2, 3", "3, 3, 4",
                      "*NSET, NSET=TIP", "3, 4", "*BEAM SECTION, ELSET=BOLT, MATERIAL=M, SECTION=RECT",
                      "0.1, 0.1", "0., 0., 1."]
                     + (["*PRE-TENSION SECTION, ELEMENT=1, NODE=99"] if cut else [])
                     + ["*MATERIAL, NAME=M", "*ELASTIC", "210000., 0.", "*STEP", "*STATIC", "*BOUNDARY",
                        "1, 1, 6"] + (["99, 1, 1, 0."] if cut else [])
                     + ["*CLOAD", "3, 2, 0.01", "3, 3, 0.005", "3, 4, 0.003", "*NODE PRINT, NSET=TIP", "U",
                        "*END STEP"]) + "\n"


def coupling_ref_deck(form):
    """A C3D8 cube (E 1000, nu 0.3), bottom held, whose top is coupled to reference node 100
    (rotations held) pulled along x by 1.  ``form`` "flat" / "flat_dist": the model written flat
    (*KINEMATIC / *DISTRIBUTING, REF NODE=100); else a part in an instance moved by 5 along x,
    the assembly-level coupling naming its reference node as the instance set (I1.RP), the
    instance node (I1.100), an assembly set of it (RPA), an assembly node numbered 1 as the
    instance's first node is (RPX: Abaqus/CAE's reference point), REF NODE= without the blank,
    a legacy *KINEMATIC COUPLING (I1.RP), or a *DISTRIBUTING one (I1.100)."""
    part = ["*NODE", "1, 0., 0., 0.", "2, 1., 0., 0.", "3, 1., 1., 0.", "4, 0., 1., 0.", "5, 0., 0., 1.",
            "6, 1., 0., 1.", "7, 1., 1., 1.", "8, 0., 1., 1.", "100, 0.5, 0.5, 1.5",
            "*ELEMENT, TYPE=C3D8, ELSET=BODY", "1, 1, 2, 3, 4, 5, 6, 7, 8", "*NSET, NSET=RP", "100",
            "*NSET, NSET=BOT", "1, 2, 3, 4", "*NSET, NSET=TOPN", "5, 6, 7, 8", "*ELSET, ELSET=TOPE", "1",
            "*SURFACE, NAME=TOPS, TYPE=NODE", "TOPN", "*SURFACE, NAME=TOPF", "TOPE, S2",
            "*SOLID SECTION, ELSET=BODY, MATERIAL=M"]
    flat = form.startswith("flat")
    q, rp = ("", "RP") if flat else ("I1.", {"asm_set": "RPA", "asm_point": "RPX"}.get(form, "I1.RP"))
    dist = form in ("flat_dist", "dist_node")
    ref = {"node": "I1.100", "dist_node": "I1.100", "asm_set": "RPA", "asm_point": "1"}.get(
        form, "RP" if flat else "I1.RP")
    card = ([f"*KINEMATIC COUPLING, REF NODE={ref}", f"{q}TOPN, 1, 3"] if form == "legacy" else
            [f"*COUPLING, CONSTRAINT NAME=C, {'REFNODE' if form == 'refnode' else 'REF NODE'}={ref}, "
             f"SURFACE={q}{'TOPF' if dist else 'TOPS'}", "*DISTRIBUTING" if dist else "*KINEMATIC"])
    asm = {"asm_set": ["*NSET, NSET=RPA, INSTANCE=I1", "100"],
           "asm_point": ["*NODE", "1, 5.5, 0.5, 1.5", "*NSET, NSET=RPX", "1"]}.get(form, [])
    model = part + card if flat else (["*PART, NAME=P"] + part + ["*END PART", "*ASSEMBLY, NAME=A",
                                      "*INSTANCE, NAME=I1, PART=P", "5., 0., 0.", "*END INSTANCE"]
                                      + asm + card + ["*END ASSEMBLY"])
    return "\n".join(model + ["*MATERIAL, NAME=M", "*ELASTIC", "1000., 0.3", "*STEP", "*STATIC",
                               "*BOUNDARY", f"{q}BOT, 1, 3"] + ([] if dist else [f"{rp}, 4, 6"])
                      + ["*CLOAD", f"{rp}, 1, 1.", f"*NODE PRINT, NSET={q}TOPN", "U", "*END STEP"]) + "\n"


# --- distributing couplings: a C3D8 block of 3 x 2 x 2 unit cubes (E 1000, nu 0.3), its bottom
# held, its top face (z = 2) coupled to reference node 100 at (1.3, 0.8, 2.5), off the face's
# centroid (1.5, 1, 2) ----------------------------------------------------------------------
DIST_REF = (1.3, 0.8, 2.5)


def distributing_block():
    """({node: xyz}, {element: nodes}, top nodes, top elements, bottom nodes) of the block."""
    nid = lambda i, j, k: 1 + i + 4 * (j + 3 * k)                                # noqa: E731
    xyz = {nid(i, j, k): (float(i), float(j), float(k)) for k in range(3) for j in range(3) for i in range(4)}
    els = {1 + i + 3 * j + 6 * k: [nid(i, j, k), nid(i + 1, j, k), nid(i + 1, j + 1, k), nid(i, j + 1, k),
                                   nid(i, j, k + 1), nid(i + 1, j, k + 1), nid(i + 1, j + 1, k + 1), nid(i, j + 1, k + 1)]
           for k in range(2) for j in range(2) for i in range(3)}
    return (xyz, els, [n for n, p in xyz.items() if p[2] == 2.0], [e for e in els if e > 6],
            [n for n, p in xyz.items() if p[2] == 0.0])


def distributing_deck(coupling, step, extra=()):
    """The block with the ``coupling`` cards (surface TOP: the top faces; node set RP: node 100),
    the ``extra`` model cards and the ``step``'s cards; every node's displacement printed."""
    xyz, els, top, topel, bot = distributing_block()
    return "\n".join(["*NODE, NSET=NALL"] + [f"{n}, {p[0]}, {p[1]}, {p[2]}" for n, p in xyz.items()]
                     + ["*NODE, NSET=RP", "100, " + ", ".join(map(str, DIST_REF)), "*ELEMENT, TYPE=C3D8, ELSET=EALL"]
                     + [f"{e}, " + ", ".join(map(str, c)) for e, c in els.items()]
                     + ["*ELSET, ELSET=ETOP"] + _ids(topel) + ["*NSET, NSET=TOPN"] + _ids(top)
                     + ["*NSET, NSET=BOT"] + _ids(bot) + ["*SURFACE, NAME=TOP", "ETOP, S2"] + list(extra)
                     + list(coupling) + ["*MATERIAL, NAME=M", "*ELASTIC", "1000., 0.3",
                                         "*SOLID SECTION, ELSET=EALL, MATERIAL=M", "*BOUNDARY", "BOT, 1, 3",
                                         "*STEP", "*STATIC"] + list(step)
                     + ["*NODE PRINT, NSET=NALL", "U", "*NODE PRINT, NSET=RP", "U", "*END STEP"]) + "\n"


def distributing_relations(xyz, weights, ref):
    """Abaqus' distributing coupling (Theory Guide, 'Distributing coupling constraints'), written
    out here independently of the converter: with normalized weights w_n, centroid c, r_n = x_n - c,
    r_R = ref - c and T = sum w_n ((r_n . r_n) I - r_n r_n), returns (motion, forces):
    motion(u) = (u_R, theta) of the coupling nodes' displacements u — theta = T^-1 sum w_n r_n x
    u_n, u_R = sum w_n u_n + theta x r_R — and forces(f, m) = {n: F_n}, the distribution of a force
    f and moment m on the reference node, F_n = w_n (f + (T^-1 (m + r_R x f)) x r_n)."""
    total = sum(weights.values())
    w = {n: v / total for n, v in weights.items()}
    c = [sum(w[n] * xyz[n][k] for n in w) for k in range(3)]
    r = {n: [xyz[n][k] - c[k] for k in range(3)] for n in w}
    rr = [ref[k] - c[k] for k in range(3)]
    t = [[sum(w[n] * ((sum(x * x for x in r[n]) if i == j else 0.0) - r[n][i] * r[n][j]) for n in w)
          for j in range(3)] for i in range(3)]
    det = (t[0][0] * (t[1][1] * t[2][2] - t[1][2] * t[2][1]) - t[0][1] * (t[1][0] * t[2][2] - t[1][2] * t[2][0])
           + t[0][2] * (t[1][0] * t[2][1] - t[1][1] * t[2][0]))
    inv = [[(t[(j + 1) % 3][(i + 1) % 3] * t[(j + 2) % 3][(i + 2) % 3]
             - t[(j + 1) % 3][(i + 2) % 3] * t[(j + 2) % 3][(i + 1) % 3]) / det for j in range(3)] for i in range(3)]
    cross = lambda a, b: [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]  # noqa: E731
    tinv = lambda v: [sum(inv[i][k] * v[k] for k in range(3)) for i in range(3)]                       # noqa: E731

    def motion(u):
        s = [sum(w[n] * cross(r[n], u[n])[k] for n in w) for k in range(3)]
        theta = tinv(s)
        tr = cross(theta, rr)
        return [sum(w[n] * u[n][k] for n in w) + tr[k] for k in range(3)], theta

    def forces(f, m):
        a = tinv([m[k] + cross(rr, f)[k] for k in range(3)])
        return {n: [w[n] * (f[k] + cross(a, r[n])[k]) for k in range(3)] for n in w}
    return motion, forces


def truss_below_beams_deck(truss_first, step):
    """A B31 cantilever 1-2-3 along x (unit elements, 0.1 x 0.1, E 210000, nu 0.3), clamped at
    node 1, with a T3D2 from node 2 to the held node 4; the truss is element 1 (numbered below
    the beams) or 3 (after them)."""
    t, ba, bb = (1, 2, 3) if truss_first else (3, 1, 2)
    return "\n".join(["*NODE, NSET=NALL", "1, 0., 0., 0.", "2, 1., 0., 0.", "3, 2., 0., 0.", "4, 1., -1., 0.5",
                      "*ELEMENT, TYPE=T3D2, ELSET=TR", f"{t}, 2, 4", "*ELEMENT, TYPE=B31, ELSET=BM",
                      f"{ba}, 1, 2", f"{bb}, 2, 3", "*MATERIAL, NAME=M", "*ELASTIC", "210000., 0.3",
                      "*BEAM SECTION, ELSET=BM, MATERIAL=M, SECTION=RECT", "0.1, 0.1", "0., 0., 1.",
                      "*SOLID SECTION, ELSET=TR, MATERIAL=M", "0.001", "*BOUNDARY", "1, 1, 6", "4, 1, 3",
                      "*STEP", "*STATIC"] + list(step) + ["*NODE PRINT, NSET=NALL", "U", "*END STEP"]) + "\n"



def shell_truss_deck(typ="S4", plane="xy", d=(0.0, -0.5, -1.0), first=True, spring=False):
    """A 3 x 2 strip of unit S4 / S8R shells (t 0.05, E 210000, nu 0.3) in the x-y or x-z plane,
    clamped along x = 0, its tip nodes loaded by 1 across the plane and 0.3 along x, with a
    T3D2 (area 1e-4) from the inner node at x = 2 to the held node 90 at the offset ``d`` (in-plane
    x, in-plane y, normal), numbered before (``first``) or after the shells; ``spring``: the truss
    as an axial SPRINGA of its stiffness EA / L, which ccx does not expand."""
    quad = typ.startswith("S8")
    sx = 2 if quad else 1
    nid = lambda i, j: 1 + i + (3 * sx + 1) * j                                   # noqa: E731
    put = (lambda u, v, w: (u, v, w)) if plane == "xy" else (lambda u, v, w: (u, w, v))  # noqa: E731
    xyz = {nid(i, j): put(i / sx, j / sx, 0.0) for j in range(2 * sx + 1) for i in range(3 * sx + 1)
           if not (quad and i % 2 and j % 2)}
    els = []
    for j in range(2):
        for i in range(3):
            a, b = sx * i, sx * j
            c = [nid(a, b), nid(a + sx, b), nid(a + sx, b + sx), nid(a, b + sx)]
            els.append(c + ([nid(a + 1, b), nid(a + 2, b + 1), nid(a + 1, b + 2), nid(a, b + 1)] if quad else []))
    n0 = nid(2 * sx, sx)
    xyz[90] = tuple(p + q for p, q in zip(xyz[n0], put(*d)))
    t = 1 if first else 10
    clamp = [n for n, p in xyz.items() if n != 90 and p[0] == 0.0]
    tip = [n for n, p in xyz.items() if n != 90 and p[0] == 3.0]
    across = 3 if plane == "xy" else 2
    return "\n".join(["*NODE, NSET=NALL"] + [f"{n}, {p[0]!r}, {p[1]!r}, {p[2]!r}" for n, p in xyz.items()]
                     + [f"*ELEMENT, TYPE={typ}, ELSET=SH"] + [f"{e + (2 if first else 1)}, " + ", ".join(map(str, c))
                                                         for e, c in enumerate(els)]
                     + [f"*ELEMENT, TYPE={'SPRINGA' if spring else 'T3D2'}, ELSET=TR", f"{t}, {n0}, 90",
                        "*MATERIAL, NAME=M", "*ELASTIC", "210000., 0.3", "*SHELL SECTION, ELSET=SH, MATERIAL=M", "0.05"]
                     + (["*SPRING, ELSET=TR", "", repr(21.0 / math.dist(xyz[n0], xyz[90]))] if spring
                        else ["*SOLID SECTION, ELSET=TR, MATERIAL=M", "0.0001"])
                     + ["*NSET, NSET=CLAMP"] + _ids(clamp) + ["*BOUNDARY", "CLAMP, 1, 6", "90, 1, 3", "*STEP", "*STATIC",
                                                             "*CLOAD"]
                     + [f"{n}, {across}, 1." for n in tip] + [f"{n}, 1, 0.3" for n in tip]
                     + ["*NODE PRINT, NSET=NALL", "U", "*END STEP"]) + "\n"



def plane_two_thickness_deck(coupling, loads):
    """A 4 x 2 strip of unit CPS4 (E 1000, nu 0.3) held along y = 0, its left half of thickness 1
    and its right half 3, with the ``coupling`` cards on its top edges (surface TOP; node set RP:
    node 100 at (1.3, 3.5)) and the step's ``loads``; every node's displacement printed."""
    nid = lambda i, j: 1 + i + 5 * j                                             # noqa: E731
    els = {1 + i + 4 * j: [nid(i, j), nid(i + 1, j), nid(i + 1, j + 1), nid(i, j + 1)] for j in range(2) for i in range(4)}
    return "\n".join(["*NODE, NSET=NALL"] + [f"{nid(i, j)}, {float(i)}, {float(j)}" for j in range(3) for i in range(5)]
                     + ["*NODE, NSET=RP", "100, 1.3, 3.5", "*ELEMENT, TYPE=CPS4, ELSET=EALL"]
                     + [f"{e}, " + ", ".join(map(str, c)) for e, c in els.items()]
                     + ["*ELSET, ELSET=THIN", "1, 2, 5, 6", "*ELSET, ELSET=THICK", "3, 4, 7, 8", "*ELSET, ELSET=ETOP",
                        "5, 6, 7, 8", "*SURFACE, NAME=TOP", "ETOP, S3"] + list(coupling)
                     + ["*MATERIAL, NAME=M", "*ELASTIC", "1000., 0.3", "*SOLID SECTION, ELSET=THIN, MATERIAL=M", "1.",
                        "*SOLID SECTION, ELSET=THICK, MATERIAL=M", "3.", "*BOUNDARY"]
                     + [f"{nid(i, 0)}, 1, 2" for i in range(5)] + ["*STEP", "*STATIC"] + list(loads)
                     + ["*NODE PRINT, NSET=NALL", "U", "*NODE PRINT, NSET=RP", "U", "*END STEP"]) + "\n"

# Abaqus 2017 Verification Guide, "Distributing coupling elements", linear DCOUP3D (exdc3lx1):
# Tables 1-3 (reference node 10's displacements and rotations, coupling node 1's displacements)
# per step, F = 1 and M = 2 on node 10: x and about z, y and about x, z and about y
DCOUP3D_TABLES = {"u10": [(6.67e-3, -1.67e-2, 0.0), (-2.06e-3, 1.35e-2, -2.67e-2), (0.0, 0.0, 8.50e-2)],
                  "r10": [(0.0, 0.0, 1.05e-2), (1.33e-2, -1.33e-2, -7.33e-3), (-2.67e-2, 4.50e-2, 0.0)],
                  "u1": [(1.19e-3, 1.44e-3, 0.0), (2.97e-4, -5.78e-5, 6.67e-3), (0.0, 0.0, -1.83e-2)]}
DCOUP3D_XYZ = {1: (1.0, 1.0, 0.0), 2: (1.0, 0.0, 0.0), 3: (0.0, 1.5, 0.0)}
DCOUP3D_REF = (-1.0, 0.5, 0.0)


def dcoup3d_deck(step):
    """The Verification Guide's linear DCOUP3D problem (exdc3lx1) in its step ``step`` (0-2),
    rebuilt from the text (not the deck itself) and the geometry its tables give back to 3
    digits: coupling nodes 1-3 (DCOUP3D_XYZ) with weights 1, 2, 3, each on SPRING1s of 100 /
    200 / 300 in DOFs 1-3 to ground; reference node 10 (DCOUP3D_REF), its DCOUP3D loaded by
    F = 1 and M = 2."""
    (fd, md) = ((1, 6), (2, 4), (3, 5))[step]
    out = ["*NODE, NSET=NALL"] + [f"{n}, {x!r}, {y!r}, {z!r}" for n, (x, y, z) in
                                  list(DCOUP3D_XYZ.items()) + [(10, DCOUP3D_REF)]]
    out += ["*ELEMENT, TYPE=DCOUP3D, ELSET=DC", "10, 10"]
    for d, k in ((1, 100.0), (2, 200.0), (3, 300.0)):
        out += [f"*ELEMENT, TYPE=SPRING1, ELSET=K{d}"] + [f"{10 * d + n}, {n}" for n in (1, 2, 3)]
        out += [f"*SPRING, ELSET=K{d}", str(d), repr(k)]
    out += ["*DISTRIBUTING COUPLING, ELSET=DC", "1, 1.", "2, 2.", "3, 3.", "*STEP", "*STATIC", "*CLOAD",
            f"10, {fd}, 1.", f"10, {md}, 2.", "*NODE PRINT, NSET=NALL", "U", "*END STEP"]
    return "\n".join(out) + "\n"

# --- rigid tools: Abaqus decks built here, so that each variant differs only in the tool ----
# A rigid flat punch pressed into an elastic block (3-D C3D8, plane-strain CPE4, axisymmetric
# CAX4) under frictionless HARD contact; the tool is rigid elements (R3D4 / R2D2 / RAX2), an
# analytical surface (CYLINDER / SEGMENTS), or a solid punch every node of which is given the
# motion (tool="prescribed") — the reference a rigid body must reproduce.  Reference node 9001.

def _ids(ids, k=16):
    ids = [str(i) for i in ids]
    return [", ".join(ids[i:i + k]) for i in range(0, len(ids), k)]


def rigid_punch_deck(dim="3d", tool="elements", nlgeom=False, d=0.01, theta=0.0,
                     ctype="SURFACE TO SURFACE", n=4, m=3):
    lines = ["*HEADING", f"Rigid flat punch on an elastic block ({dim}, tool: {tool})"]
    ref = (0.5, 0.5, 2.0) if dim == "3d" else (0.5, 2.0)
    tool_nodes = {}
    if dim == "3d":
        nid = lambda i, j, k: 1 + i + (n + 1) * (j + (n + 1) * k)      # noqa: E731
        lines.append("*NODE")
        lines += [f"{nid(i, j, k)}, {i / n:.12g}, {j / n:.12g}, {k / n:.12g}"
                  for k in range(n + 1) for j in range(n + 1) for i in range(n + 1)]
        lines.append("*ELEMENT, TYPE=C3D8, ELSET=BLOCK")
        lines += [f"{1 + i + n * j + n * n * k}, {nid(i, j, k)}, {nid(i + 1, j, k)}, {nid(i + 1, j + 1, k)}, "
                  f"{nid(i, j + 1, k)}, {nid(i, j, k + 1)}, {nid(i + 1, j, k + 1)}, {nid(i + 1, j + 1, k + 1)}, "
                  f"{nid(i, j + 1, k + 1)}" for k in range(n) for j in range(n) for i in range(n)]
        lines += ["*NSET, NSET=BOT"] + _ids(nid(i, j, 0) for j in range(n + 1) for i in range(n + 1))
        lines += ["*NSET, NSET=TOPB"] + _ids(nid(i, j, n) for j in range(n + 1) for i in range(n + 1))
        lines += ["*ELSET, ELSET=TOPE"] + _ids(1 + i + n * j + n * n * (n - 1) for j in range(n) for i in range(n))
        lines += ["*SURFACE, NAME=TOP", "TOPE, S2"]
        fixes = ["BOT, 3, 3", f"{nid(0, 0, 0)}, 1, 2", f"{nid(n, 0, 0)}, 2, 2"]
        pn = lambda i, j: 1000 + i + (m + 1) * j                         # noqa: E731
        if tool == "analytic":
            # point c on the NEGATIVE local z-axis: local y = -Z, so the line's normal
            # (e3 x s, s = +x) points down at the block
            lines += ["*SURFACE, TYPE=CYLINDER, NAME=TOOL", "0., 0., 1., 1., 0., 1.", "0., -1., 1.",
                      "START, -0.25, 0.", "LINE, 1.25, 0."]
        else:
            lines.append("*NODE")
            for lay, z in ((0, 1.0),) + (((1, 1.1),) if tool == "prescribed" else ()):
                for j in range(m + 1):
                    for i in range(m + 1):
                        tool_nodes[500 * lay + pn(i, j)] = (-0.25 + 1.5 * i / m, -0.25 + 1.5 * j / m, z)
            lines += [f"{k}, {p[0]:.12g}, {p[1]:.12g}, {p[2]:.12g}" for k, p in sorted(tool_nodes.items())]
            lines.append(f"*ELEMENT, TYPE={'R3D4' if tool == 'elements' else 'C3D8'}, ELSET=PUNCH")
            for j in range(m):
                for i in range(m):
                    face = [pn(i, j), pn(i, j + 1), pn(i + 1, j + 1), pn(i + 1, j)]   # normal -z
                    conn = face if tool == "elements" else [500 + x for x in face] + face
                    lines.append(f"{2000 + i + m * j}, " + ", ".join(map(str, conn)))
            lines += ["*SURFACE, NAME=TOOL", "PUNCH, SPOS" if tool == "elements" else "PUNCH, S2"]
    else:
        ax = dim == "axisym"
        nid = lambda i, j: 1 + i + (n + 1) * j                            # noqa: E731
        lines.append("*NODE")
        lines += [f"{nid(i, j)}, {i / n:.12g}, {j / n:.12g}" for j in range(n + 1) for i in range(n + 1)]
        lines.append(f"*ELEMENT, TYPE={'CAX4' if ax else 'CPE4'}, ELSET=BLOCK")
        lines += [f"{1 + i + n * j}, {nid(i, j)}, {nid(i + 1, j)}, {nid(i + 1, j + 1)}, {nid(i, j + 1)}"
                  for j in range(n) for i in range(n)]
        lines += ["*NSET, NSET=BOT"] + _ids(nid(i, 0) for i in range(n + 1))
        lines += ["*NSET, NSET=TOPB"] + _ids(nid(i, n) for i in range(n + 1))
        lines += ["*NSET, NSET=AXIS"] + _ids(nid(0, j) for j in range(n + 1))
        lines += ["*ELSET, ELSET=TOPE"] + _ids(1 + i + n * (n - 1) for i in range(n))
        lines += ["*SURFACE, NAME=TOP", "TOPE, S3"]
        fixes = ["BOT, 2, 2", "AXIS, 1, 1" if ax else f"{nid(0, 0)}, 1, 1"]
        x0, x1 = (0.0, 1.25) if ax else (-0.25, 1.25)
        if tool == "analytic":
            # running from x1 to x0 (-x), the profile's normal e3 x s points down (-y)
            lines += ["*SURFACE, TYPE=SEGMENTS, NAME=TOOL", f"START, {x1:g}, 1.", f"LINE, {x0:g}, 1."]
        else:
            lines.append("*NODE")
            xs = [x1 + (x0 - x1) * i / m for i in range(m + 1)]
            for lay, y in ((0, 1.0),) + (((1, 1.1),) if tool == "prescribed" else ()):
                for i, x in enumerate(xs):
                    tool_nodes[1000 + 500 * lay + i] = (x, y)
            lines += [f"{k}, {p[0]:.12g}, {p[1]:.12g}" for k, p in sorted(tool_nodes.items())]
            typ = ("RAX2" if ax else "R2D2") if tool == "elements" else ("CAX4" if ax else "CPE4")
            lines.append(f"*ELEMENT, TYPE={typ}, ELSET=PUNCH")
            for i in range(m):
                conn = [1000 + i, 1001 + i] if tool == "elements" else [1500 + i, 1501 + i, 1001 + i, 1000 + i]
                lines.append(f"{2000 + i}, " + ", ".join(map(str, conn)))
            lines += ["*SURFACE, NAME=TOOL", "PUNCH, SPOS" if tool == "elements" else "PUNCH, S3"]
    lines += ["*NODE, NSET=REF", "9001, " + ", ".join(f"{x:g}" for x in ref)]
    lines += ["*SOLID SECTION, ELSET=BLOCK, MATERIAL=STEEL"] + ([] if dim == "3d" else ["1."])
    lines += ["*MATERIAL, NAME=STEEL", "*ELASTIC", "1000., 0.3"]
    if tool == "prescribed":
        lines += ["*SOLID SECTION, ELSET=PUNCH, MATERIAL=STEEL"] + ([] if dim == "3d" else ["1."])
        lines += ["*NSET, NSET=TOOLN"] + _ids(sorted(tool_nodes))
    else:
        lines += [f"*RIGID BODY, REF NODE=9001, {'ELSET=PUNCH' if tool == 'elements' else 'ANALYTICAL SURFACE=TOOL'}"]
    lines += ["*SURFACE INTERACTION, NAME=SMOOTH", "*SURFACE BEHAVIOR, PRESSURE-OVERCLOSURE=HARD",
              f"*CONTACT PAIR, INTERACTION=SMOOTH, TYPE={ctype}", "TOP, TOOL", "*BOUNDARY"] + fixes
    lines += [f"*STEP{', NLGEOM' if nlgeom else ''}, INC=1000", "*STATIC",
              "0.1, 1., 1e-6, 0.1" if nlgeom else "1., 1.", "*BOUNDARY"]
    if tool == "prescribed":                  # the rigid motion of every punch node
        c, sn = math.cos(theta), math.sin(theta)
        for k, p in sorted(tool_nodes.items()):
            if dim == "3d":                    # turned about x through the reference node
                ry, rz = p[1] - ref[1], p[2] - ref[2]
                u = (0.0, c * ry - sn * rz - ry, sn * ry + c * rz - rz - d)
            else:                              # turned about z
                rx, ry = p[0] - ref[0], p[1] - ref[1]
                u = (c * rx - sn * ry - rx, sn * rx + c * ry - ry - d)
            lines += [f"{k}, {i + 1}, {i + 1}, {x:.15g}" for i, x in enumerate(u)]
    elif dim == "3d":
        lines += ["9001, 1, 2", f"9001, 3, 3, {-d:g}", f"9001, 4, 4, {theta:g}", "9001, 5, 6"]
    else:
        lines += ["9001, 1, 1", f"9001, 2, 2, {-d:g}", f"9001, 6, 6, {theta:g}"]
    lines += ["*NODE PRINT, NSET=REF", "U, RF", "*NODE PRINT, NSET=TOPB", "U"]
    lines += (["*NODE PRINT, NSET=TOOLN", "RF"] if tool == "prescribed" else []) + ["*END STEP"]
    return "\n".join(lines) + "\n"


def rigid_tied_deck(tool="elements", d=0.1, theta=0.05, n=4, m=3):
    """A block whose top face is tied (*TIE) to a rigid plate (R3D4 elements, or a CYLINDER
    surface) that reference node 9001 pushes down and turns about x under NLGEOM; or, with
    tool="prescribed", the block's top nodes given that motion directly."""
    nid = lambda i, j, k: 1 + i + (n + 1) * (j + (n + 1) * k)          # noqa: E731
    lines = ["*HEADING", f"Block tied to a rigid plate that turns (tool: {tool})", "*NODE"]
    lines += [f"{nid(i, j, k)}, {i / n:.12g}, {j / n:.12g}, {k / n:.12g}"
              for k in range(n + 1) for j in range(n + 1) for i in range(n + 1)]
    lines.append("*ELEMENT, TYPE=C3D8, ELSET=BLOCK")
    lines += [f"{1 + i + n * j + n * n * k}, {nid(i, j, k)}, {nid(i + 1, j, k)}, {nid(i + 1, j + 1, k)}, "
              f"{nid(i, j + 1, k)}, {nid(i, j, k + 1)}, {nid(i + 1, j, k + 1)}, {nid(i + 1, j + 1, k + 1)}, "
              f"{nid(i, j + 1, k + 1)}" for k in range(n) for j in range(n) for i in range(n)]
    lines += ["*NSET, NSET=BOT"] + _ids(nid(i, j, 0) for j in range(n + 1) for i in range(n + 1))
    lines += ["*NSET, NSET=MID"] + _ids(nid(i, j, n // 2) for j in range(n + 1) for i in range(n + 1))
    lines += ["*ELSET, ELSET=TOPE"] + _ids(1 + i + n * j + n * n * (n - 1) for j in range(n) for i in range(n))
    lines += ["*SURFACE, NAME=TOP", "TOPE, S2", "*NODE, NSET=REF", "9001, 0.5, 0.5, 2."]
    if tool == "elements":
        pn = lambda i, j: 1000 + i + (m + 1) * j                         # noqa: E731
        lines += ["*NODE"] + [f"{pn(i, j)}, {i / m:.12g}, {j / m:.12g}, 1." for j in range(m + 1) for i in range(m + 1)]
        lines.append("*ELEMENT, TYPE=R3D4, ELSET=PLATE")
        lines += [f"{2000 + i + m * j}, {pn(i, j)}, {pn(i, j + 1)}, {pn(i + 1, j + 1)}, {pn(i + 1, j)}"
                  for j in range(m) for i in range(m)]
        lines += ["*SURFACE, NAME=TOOL", "PLATE, SPOS", "*RIGID BODY, REF NODE=9001, ELSET=PLATE"]
    elif tool == "analytic":
        lines += ["*SURFACE, TYPE=CYLINDER, NAME=TOOL", "0., 0., 1., 1., 0., 1.", "0., -1., 1.",
                  "START, 0., 0.", "LINE, 1., 0.", "*RIGID BODY, REF NODE=9001, ANALYTICAL SURFACE=TOOL"]
    lines += ["*SOLID SECTION, ELSET=BLOCK, MATERIAL=STEEL", "*MATERIAL, NAME=STEEL", "*ELASTIC", "1000., 0.3"]
    lines += ([] if tool == "prescribed" else ["*TIE, NAME=GLUE", "TOP, TOOL"]) + ["*BOUNDARY", "BOT, 1, 3"]
    lines += ["*STEP, NLGEOM, INC=1000", "*STATIC", "0.1, 1., 1e-6, 0.1", "*BOUNDARY"]
    if tool == "prescribed":
        c, sn = math.cos(theta), math.sin(theta)
        for j in range(n + 1):
            ry, rz = j / n - 0.5, 1.0 - 2.0
            u = (0.0, c * ry - sn * rz - ry, sn * ry + c * rz - rz - d)
            lines += [f"{nid(i, j, n)}, {k + 1}, {k + 1}, {u[k]:.15g}" for i in range(n + 1) for k in range(3)]
    else:
        lines += ["9001, 1, 2", f"9001, 3, 3, {-d:g}", f"9001, 4, 4, {theta:g}", "9001, 5, 6"]
    lines += ["*NODE PRINT, NSET=MID", "U", "*END STEP"]
    return "\n".join(lines) + "\n"


def rigid_inertia_deck(mass=6.0, k=96.0, kz=1.0e4, rot=(1.5, 2.0, 1.0)):
    """A rigid plate (R3D4) whose mass (MASS) and rotary inertia (ROTARYI) sit on its reference
    node, on springs: free in y (2 springs k at x = +/-0.75) and about z, plus a stiff z spring."""
    pn = lambda i, j: 1 + i + 3 * j                                      # noqa: E731
    lines = ["*HEADING", "Rigid plate (R3D4) on springs: MASS and ROTARYI on its reference node",
             "*NODE"] + [f"{pn(i, j)}, {-0.75 + 0.75 * i:g}, {-0.75 + 0.75 * j:g}, 0." for j in range(3) for i in range(3)]
    lines += ["100, 0., 0., 0.5", "101, 0.75, 1., 0.", "102, -0.75, 1., 0.", "103, 0., 0., -1.5",
              "*ELEMENT, TYPE=R3D4, ELSET=PLATE"]
    lines += [f"{1 + i + 2 * j}, {pn(i, j)}, {pn(i + 1, j)}, {pn(i + 1, j + 1)}, {pn(i, j + 1)}"
              for j in range(2) for i in range(2)]
    lines += ["*ELEMENT, TYPE=MASS, ELSET=PM", "10, 100", "*MASS, ELSET=PM", f"{mass:g}",
              "*ELEMENT, TYPE=ROTARYI, ELSET=PI", "11, 100", "*ROTARY INERTIA, ELSET=PI",
              f"{rot[0]:g}, {rot[1]:g}, {rot[2]:g}, 0., 0., 0.",
              "*ELEMENT, TYPE=SPRINGA, ELSET=SY", f"20, {pn(2, 1)}, 101", f"21, {pn(0, 1)}, 102",
              "*SPRING, ELSET=SY", "", f"{k:.1f}", "*ELEMENT, TYPE=SPRINGA, ELSET=SZ", "22, 100, 103",
              "*SPRING, ELSET=SZ", "", f"{kz:.1f}", "*RIGID BODY, REF NODE=100, ELSET=PLATE",
              "*BOUNDARY", "101, 1, 3", "102, 1, 3", "103, 1, 3", "100, 1, 1", "100, 4, 5",
              "*STEP", "*FREQUENCY", "2", "*END STEP"]
    return "\n".join(lines) + "\n"


def rigid_hertz_deck(radius=10.0, d=0.1, n=60, size=40.0):
    """A rigid sphere (an axisymmetric SEGMENTS surface: a CIRCL arc) pressed into a half-space
    of CAX4 elements graded towards the contact; reference node 99001 at the centre."""
    nid = lambda i, j: 1 + i + (n + 1) * j                                # noqa: E731
    grade = lambda k: size * (k / n) ** 2                                 # noqa: E731
    lines = ["*HEADING", "Rigid sphere (analytical surface) on an elastic half-space: Hertz", "*NODE"]
    lines += [f"{nid(i, j)}, {grade(i):.12g}, {-grade(n - j):.12g}" for j in range(n + 1) for i in range(n + 1)]
    lines.append("*ELEMENT, TYPE=CAX4, ELSET=BLOCK")
    lines += [f"{1 + i + n * j}, {nid(i, j)}, {nid(i + 1, j)}, {nid(i + 1, j + 1)}, {nid(i, j + 1)}"
              for j in range(n) for i in range(n)]
    lines += ["*NSET, NSET=BOT"] + _ids(nid(i, 0) for i in range(n + 1))
    lines += ["*NSET, NSET=AXIS"] + _ids(nid(0, j) for j in range(n + 1))
    lines += ["*ELSET, ELSET=TOPE"] + _ids(1 + i + n * (n - 1) for i in range(n))
    lines += ["*SURFACE, NAME=TOP", "TOPE, S3", "*NODE, NSET=REF", f"99001, 0., {radius:g}",
              "*SURFACE, TYPE=SEGMENTS, NAME=BALL", f"START, {radius:g}, {radius:g}",
              f"CIRCL, 0., 0., 0., {radius:g}", "*RIGID BODY, REF NODE=99001, ANALYTICAL SURFACE=BALL",
              "*SOLID SECTION, ELSET=BLOCK, MATERIAL=STEEL", "*MATERIAL, NAME=STEEL", "*ELASTIC", "1000., 0.3",
              "*SURFACE INTERACTION, NAME=SMOOTH", "*SURFACE BEHAVIOR, PRESSURE-OVERCLOSURE=HARD",
              "*CONTACT PAIR, INTERACTION=SMOOTH", "TOP, BALL", "*BOUNDARY", "BOT, 1, 2", "AXIS, 1, 1",
              "*STEP, INC=1000", "*STATIC", "0.1, 1., 1e-6, 0.1", "*BOUNDARY", "99001, 1, 1",
              f"99001, 2, 2, {-d:g}", "99001, 6, 6", "*NODE PRINT, NSET=REF", "U, RF", "*END STEP"]
    return "\n".join(lines) + "\n"


def rigid_punch_explicit_deck(tool="elements", dtmax=None, period=0.002):
    """The plane-strain punch of rigid_punch_deck (node-to-surface contact) in explicit
    dynamics: the block gets a density and the motion is ramped over the step; ``dtmax`` is
    the step's maximum increment (4th field of the *DYNAMIC data line)."""
    d = rigid_punch_deck("planar", tool, ctype="NODE TO SURFACE")
    d = d.replace("*ELASTIC\n1000., 0.3", "*ELASTIC\n1000., 0.3\n*DENSITY\n1e-3")
    d = d.replace("*STEP, INC=1000\n", f"*AMPLITUDE, NAME=RAMP\n0., 0., {period:g}, 1.\n*STEP, INC=1000000\n")
    return d.replace("*STATIC\n1., 1.\n*BOUNDARY\n", f"*DYNAMIC, EXPLICIT\n, {period:g}"
                     + (f", , {dtmax:g}" if dtmax else "") + "\n*BOUNDARY, AMPLITUDE=RAMP\n")


def rigid_pressure_deck(kind="R2D2", thick=0.5, p=2.0, k=4.0):
    """A rigid R2D2 segment of length 1 in a plane-strain model whose section is ``thick``
    thick, or an R3D4 unit square, pushed by a pressure P on the element (positive along its
    normal: +y, +z) against a spring k at reference node 9; Abaqus: u = p / k (an R2D2 has no
    section thickness: P acts per unit depth)."""
    if kind == "R2D2":
        lines = ["*HEADING", "Pressure on a rigid R2D2 segment", "*NODE", "1, 0., 0.", "2, 1., 0.",
                 "3, 1., 1.", "4, 0., 1.", "11, 0., 2.", "12, 1., 2.", "9, 0.5, 3.",
                 "*ELEMENT, TYPE=CPE4, ELSET=B", "1, 1, 2, 3, 4", "*ELEMENT, TYPE=R2D2, ELSET=R",
                 "5, 11, 12", f"*SOLID SECTION, ELSET=B, MATERIAL=M", f"{thick:g}"]
        held, dof = ["9, 1, 1", "9, 6, 6"], 2
    else:
        lines = ["*HEADING", "Pressure on a rigid R3D4 facet", "*NODE"]
        lines += [f"{i + 1}, {x:g}, {y:g}, {z:g}" for i, (x, y, z) in enumerate(
            [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)])]
        lines += ["11, 0., 0., 2.", "12, 1., 0., 2.", "13, 1., 1., 2.", "14, 0., 1., 2.", "9, 0.5, 0.5, 3.",
                  "*ELEMENT, TYPE=C3D8, ELSET=B", "1, 1, 2, 3, 4, 5, 6, 7, 8",
                  "*ELEMENT, TYPE=R3D4, ELSET=R", "5, 11, 12, 13, 14", "*SOLID SECTION, ELSET=B, MATERIAL=M"]
        held, dof = ["9, 1, 2", "9, 4, 6"], 3
    lines += ["*MATERIAL, NAME=M", "*ELASTIC", "100., 0.3", "*RIGID BODY, REF NODE=9, ELSET=R",
              "*ELEMENT, TYPE=SPRING1, ELSET=SP", "50, 9", "*SPRING, ELSET=SP", str(dof), f"{k:.6f}",
              "*NSET, NSET=REF", "9", "*NSET, NSET=BN"] + _ids(range(1, 5 if kind == "R2D2" else 9))
    lines += ["*BOUNDARY", f"BN, 1, {2 if kind == 'R2D2' else 3}", "*STEP", "*STATIC", "*BOUNDARY"] + held
    lines += ["*DLOAD", f"R, P, {p:g}", "*NODE PRINT, NSET=REF", "U", "*END STEP"]
    return "\n".join(lines) + "\n"


def umat_cube_deck(name, nlgeom=False):
    """A unit cube stretched 0.001 along z, free to contract, whose material is a *USER
    MATERIAL with the constants of ccx's example Abaqus UMAT (E = 210000, nu = 0.3)."""
    return ("*NODE\n1,0,0,0\n2,1,0,0\n3,1,1,0\n4,0,1,0\n5,0,0,1\n6,1,0,1\n7,1,1,1\n8,0,1,1\n"
            "*ELEMENT, TYPE=C3D8, ELSET=E\n1,1,2,3,4,5,6,7,8\n"
            f"*MATERIAL, NAME={name}\n*USER MATERIAL, CONSTANTS=2\n210000., 0.3\n"
            f"*SOLID SECTION, ELSET=E, MATERIAL={name}\n*NSET, NSET=TOP\n5,6,7,8\n"
            "*BOUNDARY\n1,1,3\n2,2,3\n3,3,3\n4,1,1\n4,3,3\n"
            f"*STEP{', NLGEOM' if nlgeom else ''}\n*STATIC\n0.25, 1.\n*BOUNDARY\nTOP,3,3,0.001\n"
            "*EL PRINT, ELSET=E\nS\n*END STEP\n")


def frd_last(frd_path, name):
    """{node: values} of the last ``name`` block (DISP, STRESS, ...) in a ccx .frd file."""
    blocks = frd_blocks(frd_path, name)
    return blocks[-1][1] if blocks else {}



# --- composite shells: analytic laminate references and the example decks ---------------
# Pagano's cross-ply plate material (E1 = 25 E2, E3 = E2, G12 = G13 = 0.5 E2, G23 = 0.2 E2,
# nu = 0.25): E1, E2, E3, nu12, nu13, nu23, G12, G13, G23
PAGANO_PLY = (250000., 10000., 10000., 0.25, 0.25, 0.25, 5000., 5000., 2000.)
INPLANE_PLY = (140000., 10000., 10000., 0.3, 0.3, 0.45, 5000., 5000., 3450.)
ISO_STEEL = (200000., 200000., 200000., 0.3, 0.3, 0.3, 200000. / 2.6, 200000. / 2.6, 200000. / 2.6)
# INPLANE_PLY's plane-stress constants with other through-thickness ones: a solid ply whose
# material axis 2 or 3 leaves the plate is stiffer or softer in it than t Qbar
SC_PLY = (140000., 10000., 4000., 0.3, 0.2, 0.45, 5000., 3000., 2000.)


def _matmul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(len(b))) for j in range(len(b[0]))]
            for i in range(len(a))]


def _expm(a):
    """exp(a) of a small matrix: scaling and squaring of the Taylor series."""
    n = len(a)
    norm = max(sum(abs(x) for x in row) for row in a)
    s = max(0, int(math.ceil(math.log2(norm))) + 1) if norm > 0.5 else 0
    a = [[x / 2 ** s for x in row] for row in a]
    e = [[float(i == j) for j in range(n)] for i in range(n)]
    term = [row[:] for row in e]
    for k in range(1, 30):
        term = [[x / k for x in row] for row in _matmul(term, a)]
        e = [[e[i][j] + term[i][j] for j in range(n)] for i in range(n)]
    for _ in range(s):
        e = _matmul(e, e)
    return e


def _ply_stiffness(angle, props):
    """3-D stiffness constants of a 0 or 90 degree ply in plate axes (x, y, z)."""
    e1, e2, e3, n12, n13, n23, g12, g13, g23 = props
    s = [[1 / e1, -n12 / e1, -n13 / e1], [-n12 / e1, 1 / e2, -n23 / e2], [-n13 / e1, -n23 / e2, 1 / e3]]
    c = _solve(s, [1.0, 0.0, 0.0]), _solve(s, [0.0, 1.0, 0.0]), _solve(s, [0.0, 0.0, 1.0])
    k = dict(C11=c[0][0], C12=c[0][1], C13=c[0][2], C22=c[1][1], C23=c[1][2], C33=c[2][2],
             C44=g23, C55=g13, C66=g12)
    if angle == 90:
        k = dict(C11=k["C22"], C12=k["C12"], C13=k["C23"], C22=k["C11"], C23=k["C13"],
                 C33=k["C33"], C44=k["C55"], C55=k["C44"], C66=k["C66"])
    return k


def pagano_deflection(plies, a, b, q0, z):
    """Pagano's exact 3-D elasticity solution (J. Compos. Mater. 4, 1970) for a simply
    supported cross-ply plate under q0 sin(pi x / a) sin(pi y / b) on its top face: the
    deflection amplitude at height z above the bottom face.  ``plies``: (thickness, angle 0 or
    90, PAGANO_PLY-like constants), bottom first.  Each ply's 6 state variables (u, v, w,
    tau_xz, tau_yz, sigma_z) follow a linear ODE in z, so the plate is a product of matrix
    exponentials with traction-free faces but for the load."""
    al, be = math.pi / a, math.pi / b
    mats = []
    for t, ang, props in plies:
        k = _ply_stiffness(ang, props)
        wp = [k["C13"] * al / k["C33"], k["C23"] * be / k["C33"], 0, 0, 0, 1 / k["C33"]]
        sx = [-k["C11"] * al + k["C13"] * wp[0], -k["C12"] * be + k["C13"] * wp[1], 0, 0, 0, k["C13"] * wp[5]]
        sy = [-k["C12"] * al + k["C23"] * wp[0], -k["C22"] * be + k["C23"] * wp[1], 0, 0, 0, k["C23"] * wp[5]]
        txy = [k["C66"] * be, k["C66"] * al, 0, 0, 0, 0]
        mats.append((t, [[0, 0, -al, 1 / k["C55"], 0, 0], [0, 0, -be, 0, 1 / k["C44"], 0], wp,
                         [be * p - al * q for p, q in zip(txy, sx)],
                         [al * p - be * q for p, q in zip(txy, sy)], [0, 0, 0, al, be, 0]]))
    tr = [[float(i == j) for j in range(6)] for i in range(6)]
    for t, m in mats:
        tr = _matmul(_expm([[x * t for x in row] for row in m]), tr)
    state = _solve([[tr[r][c] for c in range(3)] for r in (3, 4, 5)], [0.0, 0.0, -q0]) + [0.0] * 3
    z0 = 0.0
    for t, m in mats:
        e = _expm([[x * min(t, z - z0) for x in row] for row in m])
        if z <= z0 + t + 1e-15:
            return sum(e[2][j] * state[j] for j in range(6))
        state = [sum(e[i][j] * state[j] for j in range(6)) for i in range(6)]
        z0 += t
    return state[2]


def reduced_stiffness(angle, props):
    """Classical lamination theory: the plane-stress stiffness Q-bar (Q11, Q22, Q12, Q66, Q16,
    Q26) of a ply turned by ``angle`` degrees about the shell normal."""
    e1, e2, _e3, n12, _n13, _n23, g12, _g13, _g23 = props
    d = 1 - n12 * n12 * e2 / e1
    q11, q22, q12, q66 = e1 / d, e2 / d, n12 * e2 / d, g12
    c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    return (q11 * c ** 4 + 2 * (q12 + 2 * q66) * s * s * c * c + q22 * s ** 4,
            q11 * s ** 4 + 2 * (q12 + 2 * q66) * s * s * c * c + q22 * c ** 4,
            (q11 + q22 - 4 * q66) * s * s * c * c + q12 * (s ** 4 + c ** 4),
            (q11 + q22 - 2 * q12 - 2 * q66) * s * s * c * c + q66 * (s ** 4 + c ** 4),
            (q11 - q12 - 2 * q66) * s * c ** 3 + (q12 - q22 + 2 * q66) * s ** 3 * c,
            (q11 - q12 - 2 * q66) * s ** 3 * c + (q12 - q22 + 2 * q66) * s * c ** 3)


def navier_deflection(plies, a, b, q0):
    """Classical lamination theory (Navier): the centre deflection of a simply supported
    specially orthotropic plate under q0 sin(pi x / a) sin(pi y / b)."""
    h = sum(t for t, _, _ in plies)
    d11 = d12 = d22 = d66 = 0.0
    z = -h / 2
    for t, ang, props in plies:
        q11, q22, q12, q66, _, _ = reduced_stiffness(ang, props)
        w = ((z + t) ** 3 - z ** 3) / 3
        d11, d22, d12, d66 = d11 + q11 * w, d22 + q22 * w, d12 + q12 * w, d66 + q66 * w
        z += t
    al, be = math.pi / a, math.pi / b
    return q0 / (d11 * al ** 4 + 2 * (d12 + 2 * d66) * al ** 2 * be ** 2 + d22 * be ** 4)


def composite_plate_deck(kind="s4r", h=0.01, stack=3, n=8):
    """examples/composite_plate_<kind>.inp: a simply supported [0/90/0] square plate (a = 1,
    quarter model) under q = sin(pi x) sin(pi y), one value per element; S4R composite shells
    or one layer of SC8R continuum shells (thickness parameter h; ``stack`` 1 renumbers the
    SC8R elements so that STACK DIRECTION=1 is their thickness and loads their face P4)."""
    half = 0.5
    head = ["*Heading",
            f"Simply supported [0/90/0] square plate, {kind.upper()} composite, sinusoidal "
            f"pressure (quarter model)",
            "** a = 1, plate 0 <= x, y <= a, this quarter 0 <= x, y <= a/2 with symmetry on x = y = "
            "a/2; q = sin(pi x) sin(pi y),",
            "** one value per element (its centre). validate_with_ccx.py runs a/h = 100 and a/h = 10 "
            "and compares the centre",
            "** deflection with classical laminate theory (Navier) and Pagano's 3-D elasticity "
            "solution."]
    if kind == "s4r":
        head += ["** ccx 2.23 runs composite shells on S8R / S6 only: abq2ccx makes these S8R, with "
                 "a node at the middle of every edge.",
                 "*Parameter", f"h = {h:g}", "t = h / 3.", "*Node"]
    else:
        head += ["** One layer of SC8R continuum shells (z = -h/2 to h/2), relative ply thicknesses. "
                 "ccx has no layered solid",
                 "** section: abq2ccx writes one C3D8I per ply, with the ply interface nodes on the "
                 "stack edges.",
                 "*Parameter", f"h = {h:g}", "zb = -h / 2.", "zt = h / 2.", "*Node"]
    layers = (("0.",) if kind == "s4r" else ("<zb>", "<zt>"))
    nid = lambda i, j, k: 1 + i + (n + 1) * j + (n + 1) ** 2 * k      # noqa: E731
    lines = head
    for k, z in enumerate(layers):
        lines += [f"{nid(i, j, k)}, {half * i / n:g}, {half * j / n:g}, {z}"
                  for j in range(n + 1) for i in range(n + 1)]
    lines.append(f"*Element, type={'S4R' if kind == 's4r' else 'SC8R'}, elset=PLATE")
    load = []
    order = {3: (1, 2, 3, 4, 5, 6, 7, 8), 1: (1, 4, 8, 5, 2, 3, 7, 6)}[stack]
    for j in range(n):
        for i in range(n):
            e = 1 + i + n * j
            c = [nid(i, j, 0), nid(i + 1, j, 0), nid(i + 1, j + 1, 0), nid(i, j + 1, 0)]
            if kind != "s4r":
                c += [nid(i, j, 1), nid(i + 1, j, 1), nid(i + 1, j + 1, 1), nid(i, j + 1, 1)]
                renum = [0] * 8
                for pos, node in zip(order, c):       # restacking ``order`` gives back c
                    renum[pos - 1] = node
                c = renum
            lines.append(f"{e}, " + ", ".join(map(str, c)))
            q = math.sin(math.pi * half * (i + .5) / n) * math.sin(math.pi * half * (j + .5) / n)
            face = "P" if kind == "s4r" else ("P2" if stack == 3 else "P4")
            load.append(f"{e}, {face}, {q:.8f}")
    for name, pick in (("X0", lambda i, j: i == 0), ("Y0", lambda i, j: j == 0),
                       ("XS", lambda i, j: i == n), ("YS", lambda i, j: j == n),
                       ("CENTER", lambda i, j: i == n and j == n)):
        ids = [nid(i, j, k) for k in range(len(layers)) for j in range(n + 1) for i in range(n + 1)
               if pick(i, j)]
        lines += [f"*Nset, nset={name}"] + _ids(ids)
    e1, e2, e3, n12, n13, n23, g12, g13, g23 = PAGANO_PLY
    lines += ["*Material, name=PLY", "*Elastic, type=ENGINEERING CONSTANTS",
              f"{e1:g}, {e2:g}, {e3:g}, {n12:g}, {n13:g}, {n23:g}, {g12:g}, {g13:g},", f"{g23:g}"]
    if kind == "s4r":
        lines += ["*Shell Section, elset=PLATE, composite", "<t>, 3, PLY, 0., Ply-1",
                  "<t>, 3, PLY, 90., Ply-2", "<t>, 3, PLY, 0., Ply-3",
                  "*Step, name=Load", "*Static", "*Boundary", "X0, 2, 4", "Y0, 1, 1", "Y0, 3, 3",
                  "Y0, 5, 5", "XS, XSYMM", "YS, YSYMM"]
    else:
        lines += [f"*Shell Section, elset=PLATE, composite, stack direction={stack}",
                  "1., 3, PLY, 0., Ply-1", "1., 3, PLY, 90., Ply-2", "1., 3, PLY, 0., Ply-3",
                  "*Step, name=Load", "*Static", "*Boundary", "X0, 2, 3", "Y0, 1, 1", "Y0, 3, 3",
                  "XS, 1, 1", "YS, 2, 2"]
    lines += ["*Dload"] + load + ["*Node print, nset=CENTER", "U", "*End Step"]
    return "\n".join(lines) + "\n"


def composite_inplane_deck(kind="s4r", plane="XY", n=2):
    """examples/composite_inplane_<kind>.inp: a 1 x 1 patch of a [30/-60/45]s laminate (S4R
    composite shells, or SC8R / SC6R continuum shells 0.6 thick) whose every node gets the
    in-plane displacements of a uniform strain, eps_x, eps_y and gamma_xy = 1e-3 in turn (one
    step each), the thickness free: the reactions on the edges x = 1 and y = 1 are then the
    laminate's membrane forces, A11 ... A66 of classical lamination theory times 1e-3.  With
    ``plane`` "XZ" the patch is turned by 90 degrees about x into the x-z plane."""
    eps = 1e-3
    layers = 1 if kind == "s4r" else 2
    nid = lambda i, j, k: 1 + i + (n + 1) * j + (n + 1) ** 2 * k      # noqa: E731

    def place(x, y, z):
        return (x, y, z) if plane == "XY" else (x, -z, y)
    lines = ["*Heading",
             f"In-plane stiffness of a [30/-60/45]s laminate, {kind.upper()} composite: three "
             f"uniform strain states",
             "** Every node gets the in-plane displacements of a uniform strain (eps_x, eps_y, "
             "gamma_xy = 1e-3, one step each); the",
             "** thickness is free, so the reactions on the edges x = 1 and y = 1 are the "
             "laminate's A11 ... A66 times 1e-3.", "*Node"]
    for k in range(layers):
        for j in range(n + 1):
            for i in range(n + 1):
                x, y, z = place(i / n, j / n, 0.6 * k)
                lines.append(f"{nid(i, j, k)}, {x:g}, {y:g}, {z:g}")
    typ = {"s4r": "S4R", "sc8r": "SC8R", "sc6r": "SC6R"}[kind]
    lines.append(f"*Element, type={typ}, elset=PATCH")
    e = 0
    for j in range(n):
        for i in range(n):
            b = [nid(i, j, 0), nid(i + 1, j, 0), nid(i + 1, j + 1, 0), nid(i, j + 1, 0)]
            t = [nid(i, j, 1), nid(i + 1, j, 1), nid(i + 1, j + 1, 1), nid(i, j + 1, 1)]
            for conn in ([b] if kind == "s4r" else [b + t] if kind == "sc8r" else
                         [[b[0], b[1], b[2], t[0], t[1], t[2]], [b[0], b[2], b[3], t[0], t[2], t[3]]]):
                e += 1
                lines.append(f"{e}, " + ", ".join(map(str, conn)))
    lines += ["*Nset, nset=XEDGE"] + _ids([nid(n, j, k) for k in range(layers) for j in range(n + 1)])
    lines += ["*Nset, nset=YEDGE"] + _ids([nid(i, n, k) for k in range(layers) for i in range(n + 1)])
    e1, e2, e3, n12, n13, n23, g12, g13, g23 = INPLANE_PLY
    t = "0.1" if kind == "s4r" else "1."
    lines += ["*Material, name=PLY", "*Elastic, type=ENGINEERING CONSTANTS",
              f"{e1:g}, {e2:g}, {e3:g}, {n12:g}, {n13:g}, {n23:g}, {g12:g}, {g13:g},", f"{g23:g}",
              "*Shell Section, elset=PATCH, composite, symmetric",
              f"{t}, 3, PLY, 30.", f"{t}, 3, PLY, -60.", f"{t}, 3, PLY, 45."]
    dof = {1: 1, 2: 2, 3: 3} if plane == "XY" else {1: 1, 2: 3, 3: 2}
    for name, field in (("eps_x", lambda x, y: (eps * x, 0.0)), ("eps_y", lambda x, y: (0.0, eps * y)),
                        ("gamma_xy", lambda x, y: (eps / 2 * y, eps / 2 * x))):
        lines += [f"*Step, name={name}", "*Static", "*Boundary, op=NEW"]
        for k in range(layers):
            for j in range(n + 1):
                for i in range(n + 1):
                    u, v = field(i / n, j / n)
                    lines += [f"{nid(i, j, k)}, {dof[1]}, {dof[1]}, {u:g}",
                              f"{nid(i, j, k)}, {dof[2]}, {dof[2]}, {v:g}"]
        lines += [f"1, {dof[3]}, {dof[3]}, 0.", "*Node print, nset=XEDGE, totals=ONLY", "RF",
                  "*Node print, nset=YEDGE, totals=ONLY", "RF", "*End Step"]
    return "\n".join(lines) + "\n"


def laminate_a_reactions(plane="XY", plies=(30, -60, 45, 45, -60, 30), q=None):
    """The edge reactions composite_inplane_deck's three steps must give (classical lamination
    theory, layers 0.1 thick at the angles ``plies`` in the plate, or one layer of plane-stress
    stiffness ``q``): per step, the totals (fx, fy, fz) on the edges x = 1 and y = 1 in global
    axes."""
    a = [0.0] * 6
    for qs in [q] if q else [reduced_stiffness(ang, INPLANE_PLY) for ang in plies]:
        a = [x + 0.1 * y for x, y in zip(a, qs)]
    a11, a22, a12, a66, a16, a26 = (x * 1e-3 for x in a)
    steps = [((a11, a16), (a16, a12)), ((a12, a26), (a26, a22)), ((a16, a66), (a66, a26))]
    return [plate_place(plane)((fx, fy, 0.0)) for xe, ye in steps for fx, fy in (xe, ye)]


def plate_place(plane):
    """Plate coordinates (x, y in the plate, z along its normal) -> global ones: the plate in
    the x-y plane, turned by 90 degrees about x into the x-z plane, or into the y-z plane
    (x -> y, y -> z)."""
    return {"XY": lambda p: tuple(p), "XZ": lambda p: (p[0], -p[2], p[1]),
            "YZ": lambda p: (p[2], p[0], p[1])}[plane]


# an orientation in plate coordinates whose axis 1 leaves the plate, turned about it: Abaqus
# projects its turned axis 2 onto the plate (ccx 2.23 would project axis 1, the plate's x)
TILTED_AXES = dict(a=(2.0, 0.0, 1.0), b=(0.0, 1.0, 0.0), rot=(1, 30.0))
# the plate's own axes without a rotation line: Abaqus turns them about axis 1 by default
# (2017 "Orientations") and projects axis 2, the plate's y (ccx 2.23: axis 1, x)
PLATE_AXES = dict(a=(1.0, 0.0, 0.0), b=(0.0, 1.0, 0.0), rot=None)


def abaqus_shell_direction(normal, ori=None):
    """Abaqus' material direction 1 on a flat shell with unit ``normal`` (2017 "Orientations"
    and "Conventions"): an orientation dict(a, b, rot=(k, degrees) or None for axis 1, 0) has
    axis 1 along a and 3 along a x b, turned about axis k, and projects axis k + 1 (cyclic)
    onto the shell; without one, the projection of global X, or of Z where X is the normal."""
    if ori is None:
        v = (0.0, 0.0, 1.0) if abs(normal[0]) > math.cos(math.radians(0.1)) else (1.0, 0.0, 0.0)
    else:
        e1, e3 = _unit(ori["a"]), _unit(_cross(ori["a"], ori["b"]))
        axes = [e1, _cross(e3, e1), e3]
        k, deg = ori["rot"] or (1, 0.0)
        v = _rotate(axes[k % 3], axes[k - 1], math.radians(deg))
    return _unit(tuple(x - _dot(v, normal) * c for x, c in zip(v, normal)))


def sheet_mesh(typ, nx, ny, lx=1.0, ly=1.0):
    """(nodes {id: (x, y)}, elements [nodes]) of an lx x ly rectangle of nx x ny cells: 4-node
    quadrilaterals, 8-node ones (M3D8R, M3D8, S8R; M3D9 / M3D9R with their centre node) or two
    6-node triangles per cell (M3D6, S6), node ids row by row on the grid of corner and midside
    points."""
    quad8, tri6 = typ in ("M3D8R", "M3D8", "M3D9R", "M3D9", "S8R"), typ in ("M3D6", "S6")
    mx, my = (2 * nx, 2 * ny) if quad8 or tri6 else (nx, ny)
    nid = lambda i, j: 1 + i + (mx + 1) * j      # noqa: E731
    elems = []
    for b in range(ny):
        for a in range(nx):
            i, j = 2 * a, 2 * b
            if quad8:
                elems.append([nid(i, j), nid(i + 2, j), nid(i + 2, j + 2), nid(i, j + 2), nid(i + 1, j),
                              nid(i + 2, j + 1), nid(i + 1, j + 2), nid(i, j + 1)]
                             + ([nid(i + 1, j + 1)] if typ in ("M3D9R", "M3D9") else []))
            elif tri6:
                elems += [[nid(i, j), nid(i + 2, j), nid(i + 2, j + 2), nid(i + 1, j), nid(i + 2, j + 1),
                           nid(i + 1, j + 1)],
                          [nid(i, j), nid(i + 2, j + 2), nid(i, j + 2), nid(i + 1, j + 1), nid(i + 1, j + 2),
                           nid(i, j + 1)]]
            else:
                elems.append([nid(a, b), nid(a + 1, b), nid(a + 1, b + 1), nid(a, b + 1)])
    used = sorted({x for c in elems for x in c})
    return {k: (lx * ((k - 1) % (mx + 1)) / mx, ly * ((k - 1) // (mx + 1)) / my) for k in used}, elems


def shell_axes_inplane_deck(kind="s4r", plane="XY", orient=True, n=2):
    """A 1 x 1 patch of an orthotropic ply 0.1 thick (INPLANE_PLY): a plain *SHELL SECTION on
    S4R shells or a *MEMBRANE SECTION on M3D4, M3D8R or M3D6 membranes, with the orientation
    TILTED_AXES (or the dict ``orient``, or none), in the x-y, x-z or y-z plane (plate_place,
    the orientation turned with the patch), under composite_inplane_deck's three uniform
    strains, every node's displacement given: the edge reactions are t Qbar(theta) of the ply
    at Abaqus' direction theta."""
    eps, place = 1e-3, plate_place(plane)
    typ, card = {"s4r": ("S4R", "*Shell Section"), "m3d4": ("M3D4", "*Membrane Section"),
                 "m3d8r": ("M3D8R", "*Membrane Section"), "m3d6": ("M3D6", "*Membrane Section")}[kind]
    grid, elems = sheet_mesh(typ, n, n)
    lines = ["*Heading",
             f"In-plane stiffness of an orthotropic ply, plain {typ} {card[1:].lower()} in the "
             f"{plane} plane: three uniform strain states",
             "** Every node gets the displacements of a uniform in-plane strain (eps_x, eps_y, "
             "gamma_xy = 1e-3 of the plate, one step each),",
             "** so the reactions on the edges x = 1 and y = 1 are the ply's t Qbar times 1e-3 at "
             "Abaqus' material direction.", "*Node"]
    for k, (x, y) in grid.items():
        lines.append(f"{k}, " + ", ".join(f"{c:.12g}" for c in place((x, y, 0.0))))
    lines.append(f"*Element, type={typ}, elset=PATCH")
    lines += [f"{e}, " + ", ".join(map(str, c)) for e, c in enumerate(elems, 1)]
    lines += ["*Nset, nset=XEDGE"] + _ids([k for k, (x, y) in grid.items() if x == 1.0])
    lines += ["*Nset, nset=YEDGE"] + _ids([k for k, (x, y) in grid.items() if y == 1.0])
    e1, e2, e3, n12, n13, n23, g12, g13, g23 = INPLANE_PLY
    lines += ["*Material, name=PLY", "*Elastic, type=ENGINEERING CONSTANTS",
              f"{e1:g}, {e2:g}, {e3:g}, {n12:g}, {n13:g}, {n23:g}, {g12:g}, {g13:g},", f"{g23:g}"]
    sec = f"{card}, elset=PATCH, material=PLY"
    if orient:
        axes = TILTED_AXES if orient is True else orient
        a, b = place(axes["a"]), place(axes["b"])
        lines += ["*Orientation, name=TILTED", ", ".join(f"{c:.12g}" for c in (*a, *b))]
        lines += ["{}, {:g}".format(*axes["rot"])] if axes["rot"] else []
        sec += ", orientation=TILTED"
    lines += [sec, "0.1"]
    for name, field in (("eps_x", lambda x, y: (eps * x, 0.0)), ("eps_y", lambda x, y: (0.0, eps * y)),
                        ("gamma_xy", lambda x, y: (eps / 2 * y, eps / 2 * x))):
        lines += [f"*Step, name={name}", "*Static", "*Boundary, op=NEW"]
        for k, (x, y) in grid.items():
            u = place((*field(x, y), 0.0))
            lines += [f"{k}, {d}, {d}, {u[d - 1]:.12g}" for d in (1, 2, 3)]
        lines += ["*Node print, nset=XEDGE, totals=ONLY", "RF", "*Node print, nset=YEDGE, totals=ONLY",
                  "RF", "*End Step"]
    return "\n".join(lines) + "\n"


def quad_membrane_strip_deck(typ, t=0.1, nx=4, ny=2, stretch=None):
    """A 2 x 1 strip of membranes ``typ`` (E t = 1000, thickness t; nu 0.3) held in x on x = 0,
    in y at (2, 0), in z everywhere, its edge x = 2 pulled by the consistent nodal forces of a
    traction 1 per unit length: uniaxial stress, u_x(2) = 2e-3 and u_y(y = 1) = -0.3e-3.  With
    ``stretch`` lam (nu 0, NLGEOM) the dead load per unit length is E t lam (lam^2 - 1) / 2, a
    St. Venant-Kirchhoff bar's at that stretch: u_x(2) = 2 (lam - 1)."""
    grid, elems = sheet_mesh(typ, nx, ny, 2.0, 1.0)
    nu, q = (0.3, 1.0) if stretch is None else (0.0, 1000.0 * stretch * (stretch ** 2 - 1) / 2)
    lines = ["*Heading", f"A {typ} strip in uniaxial tension" + (" (NLGEOM)" if stretch else ""), "*Node"]
    lines += [f"{k}, {x:.12g}, {y:.12g}, 0." for k, (x, y) in grid.items()]
    lines.append(f"*Element, type={typ}, elset=STRIP")
    lines += [f"{e}, " + ", ".join(map(str, c)) for e, c in enumerate(elems, 1)]
    edge = sorted((y, k) for k, (x, y) in grid.items() if x == 2.0)
    lines += ["*Nset, nset=ALL"] + _ids(list(grid))
    lines += ["*Nset, nset=LEFT"] + _ids([k for k, (x, y) in grid.items() if x == 0.0])
    lines += ["*Nset, nset=PROBE", str(edge[-1][1])]
    lines += ["*Material, name=M", "*Elastic", f"{1000.0 / t:.12g}, {nu}",
              "*Membrane Section, elset=STRIP, material=M", f"{t:g}",
              "*Step" + (", nlgeom, inc=100" if stretch else ""), "*Static"] + (["0.1, 1."] if stretch else [])
    lines += ["*Boundary", "LEFT, 1, 1", f"{edge[0][1]}, 2, 2", "ALL, 3, 3", "*Cload"]
    quad = typ != "M3D4"
    step = 2 if quad else 1
    force = {}
    for i in range(0, len(edge) - 1, step):              # consistent forces, edge by edge
        h = edge[i + step][0] - edge[i][0]
        for k, w in zip([edge[i + m][1] for m in range(step + 1)], (1 / 6, 2 / 3, 1 / 6) if quad else (0.5, 0.5)):
            force[k] = force.get(k, 0.0) + w * h * q
    lines += [f"{k}, 1, {f:.12g}" for k, f in force.items()]
    lines += ["*Node print, nset=PROBE", "U", "*End Step"]
    return "\n".join(lines) + "\n"


def sheet_sphere_deck(typ, n=16, t=0.01, p=1.0, load="P", offset=None, nlgeom=False, nu=0.3, sets=1):
    """An octant of a sphere (radius 1 at the nodes, shells or membranes ``typ`` of thickness t,
    E 1e5, Poisson's ratio nu) meshed by projecting three faces of a cube onto it, n x n cells
    each, symmetry on the coordinate planes, internal pressure p on the reference surface: a
    *DLOAD P along the outward element normal, or (``load`` "SNEG" / "SPOS") a *DSLOAD on that
    side, -p on SPOS (a surface pressure pushes against the surface normal); a shell section's
    OFFSET ``offset``; ``sets`` 2: the load given on two element sets (one patch, the other two)
    in one card.  Abaqus: the total force on the x = 0 plane is p times the reference
    surface's projected area (pi / 4) and thin-wall theory gives the radial displacement
    p (1 - nu) / (2 E t)."""
    grid, elems = sheet_mesh(typ, n, n)
    ids, nodes, conn = {}, [], []
    for k in range(3):                                   # the faces x = 1, y = 1, z = 1
        local = {}
        for g, (s_, t_) in grid.items():
            pt = [0.0, 0.0, 0.0]
            pt[k], pt[(k + 1) % 3], pt[(k + 2) % 3] = 1.0, s_, t_
            r = math.sqrt(sum(c * c for c in pt))
            key = tuple(round(c / r, 9) for c in pt)
            if key not in ids:
                ids[key] = len(ids) + 1
                nodes.append((ids[key], tuple(c / r for c in pt)))
            local[g] = ids[key]
        conn += [[local[g] for g in c] for c in elems]
    sec = (f"*Membrane Section, elset=SPHERE, material=M" if typ.startswith("M3D") else
           f"*Shell Section, elset=SPHERE, material=M" + (f", offset={offset}" if offset else ""))
    lines = ["*Heading", f"A sphere octant of {typ} under internal pressure", "*Node"]
    lines += [f"{k}, {x:.12g}, {y:.12g}, {z:.12g}" for k, (x, y, z) in nodes]
    lines.append(f"*Element, type={typ}, elset=SPHERE")
    lines += [f"{e}, " + ", ".join(map(str, c)) for e, c in enumerate(conn, 1)]
    lines += ["*Nset, nset=ALL"] + _ids([k for k, _ in nodes])
    for d in range(3):
        lines += [f"*Nset, nset=SYM{d + 1}"] + _ids([k for k, x in nodes if abs(x[d]) < 1e-9])
    if sets == 2:
        lines += ["*Elset, elset=SPH1"] + _ids(range(1, len(elems) + 1))
        lines += ["*Elset, elset=SPH2"] + _ids(range(len(elems) + 1, len(conn) + 1))
    lines += ["*Material, name=M", "*Elastic", f"100000., {nu:g}", sec, f"{t:g}"]
    lines += [] if load == "P" else ["*Surface, name=INNER", f"SPHERE, {load}"]
    lines += ["*Step" + (", nlgeom, inc=100" if nlgeom else ""), "*Static"] + (["0.1, 1."] if nlgeom else [])
    lines += ["*Boundary", "SYM1, 1, 1", "SYM2, 2, 2", "SYM3, 3, 3"]
    lines += ["*Dload"] + [f"{s}, P, {p:g}" for s in (["SPHERE"] if sets == 1 else ["SPH1", "SPH2"])] \
        if load == "P" else \
        ["*Dsload", f"INNER, P, {-p if load == 'SPOS' else p:g}"]
    lines += ["*Node print, nset=SYM1, totals=ONLY", "RF", "*Node print, nset=ALL", "U", "*End Step"]
    return "\n".join(lines) + "\n"


def sheet_cylinder_deck(typ, n=8, t=0.1, p=1.0, nu=0.3):
    """Half a cylinder (radius 1 at the nodes, length 1 along z; shells or membranes ``typ`` of
    thickness t, E 1e5, Poisson's ratio nu), n x n cells over theta 0..180 deg and z, symmetric
    about y = 0 (u_y and the rotation about z held: ccx's hinge there is nearly singular), held
    in z on z = 0 and in x at (0, 1, 0), open at z = 1, internal pressure p (*DLOAD P along the
    outward normal).  Abaqus: the y-force on the plane y = 0 is p times the projected area
    2 R L = 2 and thin-wall theory gives the radial displacement p R^2 / (E t)."""
    grid, elems = sheet_mesh(typ, n, n, math.pi, 1.0)
    nodes = {k: (math.cos(th), math.sin(th), z) for k, (th, z) in grid.items()}
    top = min(nodes, key=lambda k: abs(nodes[k][0]) + abs(nodes[k][1] - 1) + abs(nodes[k][2]))
    sec = "*Membrane Section" if typ.startswith("M3D") else "*Shell Section"
    lines = ["*Heading", f"Half a cylinder of {typ} under internal pressure", "*Node"]
    lines += [f"{k}, {0.0 if abs(x) < 1e-12 else x:.12g}, {0.0 if abs(y) < 1e-12 else y:.12g}, {z:.12g}"
              for k, (x, y, z) in nodes.items()]
    lines.append(f"*Element, type={typ}, elset=TUBE")
    lines += [f"{e}, " + ", ".join(map(str, c)) for e, c in enumerate(elems, 1)]
    lines += ["*Nset, nset=ALL"] + _ids(list(nodes))
    lines += ["*Nset, nset=FLOOR"] + _ids([k for k, (x, y, z) in nodes.items() if abs(y) < 1e-9])
    lines += ["*Nset, nset=BASE"] + _ids([k for k, (x, y, z) in nodes.items() if z == 0.0])
    lines += ["*Material, name=M", "*Elastic", f"100000., {nu:g}", f"{sec}, elset=TUBE, material=M", f"{t:g}",
              "*Step", "*Static", "*Boundary", "FLOOR, 2, 2"] + (["FLOOR, 6, 6"] if sec[1] == "S" else []) + \
             ["BASE, 3, 3", f"{top}, 1, 1",
              "*Dload", f"TUBE, P, {p:g}", "*Node print, nset=FLOOR, totals=ONLY", "RF",
              "*Node print, nset=ALL", "U", "*End Step"]
    return "\n".join(lines) + "\n"


def tilted_strip_deck(ang, tip, torque=1.0, nlgeom=False, nx=8, ny=2):
    """An S8R strip along z (length 1, width 0.2, thickness 0.01; nx x ny cells) whose normal
    lies in the x-y plane at ``ang`` deg from x, clamped at z = 0; on its tip edge (z = 1) the
    rotational BCs ``tip`` ((DOF, value), ...) and forces -+``torque`` along the normal at the
    two tip corners, which twist it about z."""
    c, s = math.cos(math.radians(ang)), math.sin(math.radians(ang))
    grid, elems = sheet_mesh("S8R", ny, nx, 0.2, 1.0)
    nodes = {k: (-s * (y - 0.1), c * (y - 0.1), z) for k, (y, z) in grid.items()}
    tip_nodes = [k for k, x in nodes.items() if x[2] == 1.0]
    ends = [min(tip_nodes, key=lambda k: grid[k][0]), max(tip_nodes, key=lambda k: grid[k][0])]
    lines = ["*Node, nset=ALLN"] + [f"{k}, {x!r}, {y!r}, {z!r}" for k, (x, y, z) in nodes.items()]
    lines += ["*Element, type=S8R, elset=E"] + [f"{e}, " + ", ".join(map(str, cn)) for e, cn in enumerate(elems, 1)]
    lines += ["*Nset, nset=ROOT"] + _ids([k for k, x in nodes.items() if x[2] == 0.0])
    lines += ["*Nset, nset=TIP"] + _ids(tip_nodes)
    lines += ["*Material, name=M", "*Elastic", "210000., 0.3", "*Shell Section, elset=E, material=M",
              "0.01", "*Boundary", "ROOT, 1, 6", "*Step" + (", nlgeom" if nlgeom else ""), "*Static",
              "*Boundary"] + [f"TIP, {d}, {d}, {v!r}" for d, v in tip]
    lines += ["*Cload"] + [f"{n}, {k + 1}, {sg * torque * v!r}" for n, sg in zip(ends, (-1.0, 1.0))
                           for k, v in enumerate((c, s)) if abs(v) > 1e-15]
    lines += ["*Node Print, nset=ALLN", "U", "*End Step"]
    return "\n".join(lines) + "\n"


def corner_transform_plate_deck(local):
    """A flat S8R plate (2 x 1 in the x-y plane, 4 x 2 cells, thickness 0.05) clamped along
    x = 0.  Corner A (2, 0) moved 0.01 along z and loaded by a force of 5 and a moment of 0.1
    about an in-plane axis 30 deg from x; corner B (2, 1) held in x, y and z.  ``local``: A
    with a rectangular *TRANSFORM turned 30 deg about z (the loads along its local 1), B
    with one tilted out of the plane, each BC and load in those local axes; else all global."""
    grid, elems = sheet_mesh("S8R", 4, 2, 2.0, 1.0)
    a = min(grid, key=lambda k: math.dist(grid[k], (2.0, 0.0)))
    b = min(grid, key=lambda k: math.dist(grid[k], (2.0, 1.0)))
    c, s = math.cos(math.radians(30.0)), math.sin(math.radians(30.0))
    lines = ["*Node, nset=ALLN"] + [f"{k}, {x!r}, {y!r}, 0." for k, (x, y) in grid.items()]
    lines += ["*Element, type=S8R, elset=E"] + [f"{e}, " + ", ".join(map(str, cn)) for e, cn in enumerate(elems, 1)]
    lines += ["*Nset, nset=ROOT"] + _ids([k for k, (x, y) in grid.items() if x == 0.0])
    lines += ["*Material, name=M", "*Elastic", "210000., 0.3", "*Shell Section, elset=E, material=M", "0.05"]
    if local:
        lines += [f"*Nset, nset=TA\n{a}", "*Transform, nset=TA, type=R", f"{c!r}, {s!r}, 0., {-s!r}, {c!r}, 0.",
                  f"*Nset, nset=TB\n{b}", "*Transform, nset=TB, type=R", "1., 0., 1., 0., 1., 0."]
    lines += ["*Boundary", "ROOT, ENCASTRE", f"{b}, 1, 3", "*Step", "*Static", "*Boundary", f"{a}, 3, 3, 0.01",
              "*Cload"] + ([f"{a}, 1, 5.", f"{a}, 4, 0.1"] if local else
                           [f"{a}, 1, {5 * c!r}", f"{a}, 2, {5 * s!r}", f"{a}, 4, {0.1 * c!r}", f"{a}, 5, {0.1 * s!r}"])
    lines += ["*Node Print, nset=ALLN, global=yes", "U", "*End Step"]
    return "\n".join(lines) + "\n"


def folded_strip_deck(turned, procs=("*STATIC", "*DYNAMIC")):
    """An S4 strip 2 long folded 90 deg along its middle line (ccx knots the nodes on the fold),
    clamped at x = 0; the fold's end node 8 moved 0.005 per step in y and 0.01 in z, one step per
    procedure in ``procs``.  ``turned``: node 8 with a rectangular *TRANSFORM turned 90 deg
    about z (local 1 = y), its BCs in those axes.  Both write the node set TR, so the converted
    decks differ only by the *TRANSFORM: ccx 2.23 crashes at random at the *DYNAMIC step's start
    (tempload), and the Windows build crashed on every run of the twin without TR."""
    pts = [(float(i), y, z) for i in range(3) for y, z in ((-0.5, 0.0), (0.0, 0.0), (0.0, 0.5))]
    els = [f"{2 * i + j + 1}, {3 * i + j + 1}, {3 * i + j + 4}, {3 * i + j + 5}, {3 * i + j + 2}"
           for i in range(2) for j in range(2)]
    lines = ["*Node, nset=ALLN"] + [f"{k}, {x!r}, {y!r}, {z!r}" for k, (x, y, z) in enumerate(pts, 1)]
    lines += ["*Element, type=S4, elset=E"] + els + ["*Shell Section, elset=E, material=M", "0.05",
                                                     "*Material, name=M", "*Elastic", "1000., 0.3",
                                                     "*Density", "1e-3", "*Boundary", "1, 1, 6", "2, 1, 6",
                                                     "3, 1, 6"]
    lines += ["*Nset, nset=TR", "8"] + (["*Transform, nset=TR, type=R", "0., 1., 0., -1., 0., 0."]
                                        if turned else [])
    for k, proc in enumerate(procs, 1):
        lines += ["*Step", proc] + (["0.05, 1."] if proc.upper() == "*DYNAMIC" else []) + ["*Boundary"]
        lines += [f"8, {1 if turned else 2}, {1 if turned else 2}, {0.005 * k!r}", f"8, 3, 3, {0.01 * k!r}"]
        lines += ["*Node Print, nset=ALLN, global=yes", "U", "*End Step"]
    return "\n".join(lines) + "\n"


def symmetric_panel_deck(typ, half, p=1.0, nlgeom=False, transform=False):
    """A cylindrical panel (radius 1 about z, 0..60 deg, shells ``typ`` (S8R / S4) of thickness
    0.02, 4 x 8 cells over theta and z 0..2), clamped at both ends, under pressure p; ``half``:
    z 0..1 only (4 x 4 cells, the same node ids), clamped at z = 0 and ZSYMM on z = 1, its
    plane of symmetry; ``transform``: a cylindrical *TRANSFORM about z on all nodes (ZSYMM and
    the clamp then read in its axes).  Prints u at the half's nodes in global components."""
    grid, elems = sheet_mesh(typ, 4, 8, math.pi / 3.0, 2.0)
    nodes = {k: (math.cos(th), math.sin(th), z) for k, (th, z) in grid.items()}
    if half:
        elems = [cn for cn in elems if max(nodes[n][2] for n in cn) <= 1.0 + 1e-12]
    used = sorted({n for cn in elems for n in cn})
    lines = ["*Node"] + [f"{k}, {nodes[k][0]!r}, {nodes[k][1]!r}, {nodes[k][2]!r}" for k in used]
    lines += [f"*Element, type={typ}, elset=E"] + [f"{e}, " + ", ".join(map(str, cn)) for e, cn in enumerate(elems, 1)]
    lines += ["*Nset, nset=HALF"] + _ids([k for k in used if nodes[k][2] <= 1.0 + 1e-12])
    lines += ["*Nset, nset=ENDS"] + _ids([k for k in used if nodes[k][2] in (0.0, 2.0)])
    lines += ["*Nset, nset=SYM"] + _ids([k for k in used if abs(nodes[k][2] - 1.0) < 1e-12])
    lines += ["*Nset, nset=ALLN"] + _ids(used)
    lines += ["*Material, name=M", "*Elastic", "210000., 0.3", "*Shell Section, elset=E, material=M", "0.02"]
    lines += ["*Transform, nset=ALLN, type=C", "0., 0., 0., 0., 0., 1."] if transform else []
    lines += ["*Boundary", "ENDS, ENCASTRE"] + (["SYM, ZSYMM"] if half else [])
    lines += ["*Step" + (", nlgeom" if nlgeom else ""), "*Static", "*Dload", f"E, P, {p!r}",
              "*Node Print, nset=HALF, global=yes", "U", "*End Step"]
    return "\n".join(lines) + "\n"


def membrane_skin_deck(typ, tied=True, flip=False, t=0.02):
    """A membrane skin (thickness t, E t = 2000, nu 0.3) on a 2 x 1 x 0.2 C3D8 block (E 1000)
    clamped at its bottom, every node held in z and the skin's end x = 0 like the block's, its
    edge x = 2 pulled by 1 in x.  ``tied``: the skin on nodes of its own half a thickness above
    the block, its SNEG face (SPOS with ``flip``: the element normal reversed) tied to the
    block's top without a POSITION TOLERANCE; else on the block's top nodes — the same model,
    a tie of coincident meshes.  -> (deck, the node at the middle of the pulled edge)."""
    nx, ny, nz, lx, ly, h = 8, 4, 2, 2.0, 1.0, 0.2
    bid = lambda i, j, k: 1 + i + (nx + 1) * (j + (ny + 1) * k)      # noqa: E731
    sid = (lambda i, j: 1000 + i + (nx + 1) * j) if tied else (lambda i, j: bid(i, j, nz))   # noqa: E731
    lines = ["*Heading", f"A {typ} skin {'tied to' if tied else 'sharing the nodes of'} a block", "*Node"]
    lines += [f"{bid(i, j, k)}, {lx * i / nx:.12g}, {ly * j / ny:.12g}, {h * (k / nz - 1):.12g}"
              for k in range(nz + 1) for j in range(ny + 1) for i in range(nx + 1)]
    if tied:
        lines += [f"{sid(i, j)}, {lx * i / nx:.12g}, {ly * j / ny:.12g}, {t / 2:.12g}"
                  for j in range(ny + 1) for i in range(nx + 1)]
    lines.append("*Element, type=C3D8, elset=BLOCK")
    lines += [f"{1 + i + nx * (j + ny * k)}, " + ", ".join(str(bid(i + a, j + b, k + c)) for c in (0, 1)
                                                         for a, b in ((0, 0), (1, 0), (1, 1), (0, 1)))
              for k in range(nz) for j in range(ny) for i in range(nx)]
    lines.append(f"*Element, type={typ}, elset=SKIN")
    e = 1000
    for j in range(ny):
        for i in range(nx):
            c = [sid(i, j), sid(i + 1, j), sid(i + 1, j + 1), sid(i, j + 1)]
            c = c[::-1] if flip else c
            for cell in ([c[:3], [c[0], c[2], c[3]]] if typ == "M3D3" else [c]):
                e += 1
                lines.append(f"{e}, " + ", ".join(map(str, cell)))
    top = list(range(1 + nx * ny * (nz - 1), 1 + nx * ny * nz))
    lines += ["*Nset, nset=ALL"] + _ids(sorted({bid(i, j, k) for k in range(nz + 1) for j in range(ny + 1)
                                                for i in range(nx + 1)} | {sid(i, j) for j in range(ny + 1)
                                                                            for i in range(nx + 1)}))
    lines += ["*Nset, nset=BOTTOM"] + _ids([bid(i, j, 0) for j in range(ny + 1) for i in range(nx + 1)])
    lines += ["*Nset, nset=END"] + _ids(sorted({bid(0, j, nz) for j in range(ny + 1)} |
                                               {sid(0, j) for j in range(ny + 1)}))
    lines += ["*Nset, nset=PROBE", str(sid(nx, ny // 2))]
    lines += ["*Elset, elset=TOP"] + _ids(top)
    lines += ["*Material, name=BLOCK", "*Elastic", "1000., 0.3", "*Material, name=SKIN", "*Elastic",
              f"{2000.0 / t:.12g}, 0.3", "*Solid Section, elset=BLOCK, material=BLOCK",
              "*Membrane Section, elset=SKIN, material=SKIN", f"{t:g}",
              "*Surface, name=BLOCK_TOP, type=ELEMENT", "TOP, S2"]
    if tied:
        lines += ["*Surface, name=SKIN_FACE, type=ELEMENT", f"SKIN, {'SPOS' if flip else 'SNEG'}",
                  "*Tie, name=GLUE", "SKIN_FACE, BLOCK_TOP"]
    lines += ["*Step", "*Static", "*Boundary", "BOTTOM, 1, 2", "END, 1, 2", "ALL, 3, 3", "*Cload"]
    lines += [f"{sid(nx, j)}, 1, {(0.5 if j in (0, ny) else 1.0) / ny:.12g}" for j in range(ny + 1)]
    lines += ["*Node print, nset=PROBE", "U", "*End Step"]
    return "\n".join(lines) + "\n", sid(nx, ny // 2)


def membrane_mass_deck(typ, rho=7.0, area_mass=2.0, t=0.01):
    """A 2 x 1 membrane strip ``typ`` (thickness t, E 1e5, material density rho, *MEMBRANE
    SECTION DENSITY=area_mass — a mass per unit area added to the material's; none if 0) held
    in-plane at its ends x = 0 and 2 and in z everywhere, its first three frequencies wanted:
    the same model as area_mass 0 with the density rho + area_mass / t."""
    grid, elems = sheet_mesh(typ, 4, 2, 2.0, 1.0)
    lines = ["*Heading", f"A {typ} strip with a section mass: in-plane frequencies", "*Node"]
    lines += [f"{k}, {x:.12g}, {y:.12g}, 0." for k, (x, y) in grid.items()]
    lines.append(f"*Element, type={typ}, elset=SKIN")
    lines += [f"{e}, " + ", ".join(map(str, c)) for e, c in enumerate(elems, 1)]
    lines += ["*Nset, nset=ALL"] + _ids(list(grid))
    lines += ["*Nset, nset=ENDS"] + _ids([k for k, (x, _y) in grid.items() if x in (0.0, 2.0)])
    lines += ["*Material, name=M", "*Elastic", "1e5, 0.3", "*Density", f"{rho:.12g}",
              "*Membrane Section, elset=SKIN, material=M" + (f", density={area_mass:g}" if area_mass else ""),
              f"{t:g}", "*Step", "*Frequency", "3", "*Boundary", "ENDS, 1, 2", "ALL, 3, 3", "*End Step"]
    return "\n".join(lines) + "\n"


def sheet_coupling_deck(typ, face, t=0.02):
    """A 2 x 1 strip of membranes or shells ``typ`` (E t = 2000, nu 0) held in x on x = 0, in y
    at the origin, in z everywhere; its last element column joined by a kinematic coupling of
    the translations on its ``face`` side to a reference node at (2.5, 0.5, 0) pulled by 1 in x:
    the end column moves rigidly, so the strip's end moves (2 - h) / 2000 (h = 0.25, the
    column's width).  -> (deck, the node at the middle of the strip's end)."""
    nx, ny = 8, 4
    nid = lambda i, j: 1 + i + (nx + 1) * j      # noqa: E731
    lines = ["*Heading", f"A {typ} strip with a kinematic coupling on its {face} face", "*Node"]
    lines += [f"{nid(i, j)}, {2.0 * i / nx:.12g}, {1.0 * j / ny:.12g}, 0." for j in range(ny + 1)
              for i in range(nx + 1)] + ["999, 2.5, 0.5, 0."]
    lines.append(f"*Element, type={typ}, elset=STRIP")
    e, last = 0, []
    for j in range(ny):
        for i in range(nx):
            c = [nid(i, j), nid(i + 1, j), nid(i + 1, j + 1), nid(i, j + 1)]
            for cell in ([c[:3], [c[0], c[2], c[3]]] if typ in ("M3D3", "S3") else [c]):
                e += 1
                lines.append(f"{e}, " + ", ".join(map(str, cell)))
                if i == nx - 1:
                    last.append(e)
    lines += ["*Elset, elset=LAST"] + _ids(last)
    lines += ["*Nset, nset=ALL"] + _ids([nid(i, j) for j in range(ny + 1) for i in range(nx + 1)])
    lines += ["*Nset, nset=LEFT"] + _ids([nid(0, j) for j in range(ny + 1)])
    lines += ["*Material, name=M", "*Elastic", f"{2000.0 / t:.12g}, 0.",
              f"*{'Membrane' if typ.startswith('M3D') else 'Shell'} Section, elset=STRIP, material=M", f"{t:g}",
              "*Surface, name=END_FACE, type=ELEMENT", f"LAST, {face}",
              "*Coupling, constraint name=END, ref node=999, surface=END_FACE", "*Kinematic", "1, 3",
              "*Step", "*Static", "*Boundary", "LEFT, 1, 1", f"{nid(0, 0)}, 2, 2", "ALL, 3, 3", "999, 2, 6",
              "*Cload", "999, 1, 1.", "*Node print, nset=END_NODE", "U", "*End Step"]
    lines.insert(lines.index("*Material, name=M"), "*Nset, nset=END_NODE")
    lines.insert(lines.index("*Material, name=M"), str(nid(nx, ny // 2)))
    return "\n".join(lines) + "\n", nid(nx, ny // 2)


def shell_axes_angle(plane, orient=True):
    """The plate angle of Abaqus' material direction 1 in shell_axes_inplane_deck (degrees)."""
    place = plate_place(plane)
    axes = TILTED_AXES if orient is True else orient
    ori = dict(a=place(axes["a"]), b=place(axes["b"]), rot=axes["rot"]) if orient else None
    d = abaqus_shell_direction(place((0.0, 0.0, 1.0)), ori)
    return math.degrees(math.atan2(_dot(d, place((0.0, 1.0, 0.0))), _dot(d, place((1.0, 0.0, 0.0)))))


def sc_axes_inplane_deck(kind="sc8r", plane="XY", orient=True, n=2, dist=False, aniso=False):
    """shell_axes_inplane_deck's patch as continuum shells 0.1 thick (SC8R, or SC6R wedges)
    with a plain *SHELL SECTION of SC_PLY: every node gets the in-plane displacements of the
    three uniform strains and the thickness is free (composite_inplane_deck), so the edge
    reactions are t Qbar of the ply at Abaqus' material direction where its axis 3 is the
    stack direction.  The orientation is TILTED_AXES, the dict ``orient`` or none; ``dist``
    gives it as a *DISTRIBUTION, every other element's line turned half about the plate normal
    (the same directions for the orthotropic ply); ``aniso`` stacks SC8R elements downwards,
    without an orientation, on SC_ANISO (aniso_patch_reactions)."""
    eps, place = 1e-3, plate_place(plane)
    nid = lambda i, j, k: 1 + i + (n + 1) * j + (n + 1) ** 2 * k      # noqa: E731
    typ = {"sc8r": "SC8R", "sc6r": "SC6R"}[kind]
    lines = ["*Heading",
             f"In-plane stiffness of an orthotropic ply, plain {typ} shell section in the {plane} "
             f"plane: three uniform strain states",
             "** Every node gets the in-plane displacements of a uniform strain (eps_x, eps_y, "
             "gamma_xy = 1e-3 of the plate, one step each)",
             "** and the thickness is free, so the reactions on the edges x = 1 and y = 1 are the "
             "ply's t Qbar times 1e-3 at Abaqus' direction.", "*Node"]
    for k in range(2):
        for j in range(n + 1):
            for i in range(n + 1):
                z = 0.1 * (1 - k if aniso else k)
                lines.append(f"{nid(i, j, k)}, " + ", ".join(f"{c:.12g}" for c in place((i / n, j / n, z))))
    lines.append(f"*Element, type={typ}, elset=PATCH")
    e = 0
    for j in range(n):
        for i in range(n):
            q = [(i, j), (i, j + 1), (i + 1, j + 1), (i + 1, j)] if aniso else \
                [(i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)]
            b, t = [nid(*p, 0) for p in q], [nid(*p, 1) for p in q]
            for conn in ([b + t] if kind == "sc8r" else
                         [[b[0], b[1], b[2], t[0], t[1], t[2]], [b[0], b[2], b[3], t[0], t[2], t[3]]]):
                e += 1
                lines.append(f"{e}, " + ", ".join(map(str, conn)))
    lines += ["*Nset, nset=XEDGE"] + _ids([nid(n, j, k) for k in range(2) for j in range(n + 1)])
    lines += ["*Nset, nset=YEDGE"] + _ids([nid(i, n, k) for k in range(2) for i in range(n + 1)])
    lines += ["*Material, name=PLY"]
    if aniso:
        d = SC_ANISO
        vals = [d[r][c] for c in range(6) for r in range(c + 1)]     # D1111, D1122, D2222, ...
        lines += ["*Elastic, type=ANISOTROPIC"] + [", ".join(f"{v:.12g}" for v in vals[i:i + 8])
                                                   for i in range(0, 21, 8)]
    else:
        e1, e2, e3, n12, n13, n23, g12, g13, g23 = SC_PLY
        lines += ["*Elastic, type=ENGINEERING CONSTANTS",
                  f"{e1:g}, {e2:g}, {e3:g}, {n12:g}, {n13:g}, {n23:g}, {g12:g}, {g13:g},", f"{g23:g}"]
    sec = "*Shell Section, elset=PATCH, material=PLY"
    if orient:
        axes = TILTED_AXES if orient is True else orient
        a, b = place(axes["a"]), place(axes["b"])
        if dist:
            half = [place((-x, -y, z)) for x, y, z in (axes["a"], axes["b"])]
            lines += ["*Distribution, name=TILTED_D, location=ELEMENT, table=TILTED_T",
                      ", " + ", ".join(f"{c:.12g}" for c in (*a, *b))]
            lines += [f"{k}, " + ", ".join(f"{c:.12g}" for c in ((*half[0], *half[1]) if k % 2 else (*a, *b)))
                      for k in range(1, e + 1)]
            lines += ["*Distribution Table, name=TILTED_T", "coord3D, coord3D",
                      "*Orientation, name=TILTED", "TILTED_D"]
        else:
            lines += ["*Orientation, name=TILTED", ", ".join(f"{c:.12g}" for c in (*a, *b))]
        lines += ["{}, {:g}".format(*axes["rot"])] if axes["rot"] else []
        sec += ", orientation=TILTED"
    lines += [sec, "0.1"]
    normal = [abs(c) for c in place((0.0, 0.0, 1.0))].index(1.0) + 1
    dofs = [d for d in (1, 2, 3) if d != normal]
    for name, field in (("eps_x", lambda x, y: (eps * x, 0.0)), ("eps_y", lambda x, y: (0.0, eps * y)),
                        ("gamma_xy", lambda x, y: (eps / 2 * y, eps / 2 * x))):
        lines += [f"*Step, name={name}", "*Static", "*Boundary, op=NEW"]
        for k in range(2):
            for j in range(n + 1):
                for i in range(n + 1):
                    u = place((*field(i / n, j / n), 0.0))
                    lines += [f"{nid(i, j, k)}, {d}, {d}, {u[d - 1]:.12g}" for d in dofs]
        lines += [f"1, {normal}, {normal}, 0.", "*Node print, nset=XEDGE, totals=ONLY", "RF",
                  "*Node print, nset=YEDGE, totals=ONLY", "RF", "*End Step"]
    return "\n".join(lines) + "\n"


VOIGT = ((0, 0), (1, 1), (2, 2), (0, 1), (0, 2), (1, 2))    # Abaqus / ccx order 11 22 33 12 13 23


def _ortho_stiffness6(props):
    """The 6 x 6 stiffness (VOIGT order, engineering shear strains) of engineering constants."""
    e1, e2, e3, n12, n13, n23, g12, g13, g23 = props
    s = [[1 / e1, -n12 / e1, -n13 / e1], [-n12 / e1, 1 / e2, -n23 / e2], [-n13 / e1, -n23 / e2, 1 / e3]]
    cols = [_solve(s, [float(i == j) for i in range(3)]) for j in range(3)]
    c = [[0.0] * 6 for _ in range(6)]
    for i in range(3):
        for j in range(3):
            c[i][j] = cols[j][i]
    c[3][3], c[4][4], c[5][5] = g12, g13, g23
    return c


def _turned_stiffness(c6, q):
    """The 6 x 6 stiffness ``c6`` of a material whose axes are the columns of ``q``, in the axes
    those columns are given in."""
    idx = {}
    for k, (i, j) in enumerate(VOIGT):
        idx[(i, j)] = idx[(j, i)] = k
    r = range(3)
    return [[sum(q[i][a] * q[j][b] * q[k][c] * q[m][d] * c6[idx[(a, b)]][idx[(c, d)]]
                 for a in r for b in r for c in r for d in r) for (k, m) in VOIGT] for (i, j) in VOIGT]


def _plane_stress(c6):
    """(Q11, Q22, Q12, Q66, Q16, Q26) of the 6 x 6 stiffness ``c6`` where sigma_33, tau_13 and
    tau_23 vanish (a free thickness)."""
    io, oo = (0, 1, 3), (2, 4, 5)
    q = {}
    for a in io:
        x = _solve([[c6[r][s] for s in oo] for r in oo], [c6[r][a] for r in oo])
        for b in io:
            q[(b, a)] = c6[b][a] - sum(c6[b][r] * xr for r, xr in zip(oo, x))
    return q[(0, 0)], q[(1, 1)], q[(0, 1)], q[(3, 3)], q[(0, 3)], q[(1, 3)]


# SC_PLY with its fibres turned 30 degrees about axis 3 of the material axes: an anisotropic
# (monoclinic) ply whose couplings change sign when axis 2 is reversed
_c30, _s30 = math.cos(math.radians(30.0)), math.sin(math.radians(30.0))
SC_ANISO = _turned_stiffness(_ortho_stiffness6(SC_PLY), [[_c30, -_s30, 0.0], [_s30, _c30, 0.0], [0.0, 0.0, 1.0]])


def aniso_patch_reactions(plane="XY"):
    """The edge reactions of sc_axes_inplane_deck(aniso=True): Abaqus' material axes of the
    downward stack are the plate's x, -y and -z (2017 "Conventions"), so SC_ANISO's in-plane
    couplings act reversed (ccx's global axes would keep them)."""
    c = _turned_stiffness(SC_ANISO, [[1.0, 0.0, 0.0], [0.0, -1.0, 0.0], [0.0, 0.0, -1.0]])
    return laminate_a_reactions(plane, q=_plane_stress(c))


def sc_cylinder_hoop_deck(n=24, m=2, t=0.01):
    """cylinder_hoop_deck's cylinder as one layer of SC8R continuum shells (mean radius 1,
    thickness t, stacked outward) of SC_PLY with the cylindrical *ORIENTATION, internal pressure
    1 on the inner face: Abaqus projects the system's axis 2, the hoop direction, onto the
    mid-surface, so thin-wall theory gives the mid-surface radial displacement r_i / (E1 t)."""
    nid = lambda i, j, k: 1 + i % n + n * j + n * (m + 1) * k      # noqa: E731
    lines = ["*Heading", "Thin open cylinder of a hoop-wound orthotropic ply under internal "
             "pressure: SC8R continuum shells with a cylindrical *Orientation", "*Node"]
    for k, r in enumerate((1.0 - t / 2, 1.0 + t / 2)):
        for j in range(m + 1):
            for i in range(n):
                th = 2 * math.pi * i / n
                lines.append(f"{nid(i, j, k)}, {r * math.cos(th):.12g}, {r * math.sin(th):.12g}, {j / m:.12g}")
    lines.append("*Element, type=SC8R, elset=CYL")
    for j in range(m):
        for i in range(n):
            q = [(i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)]
            lines.append(f"{1 + i + n * j}, " + ", ".join(str(nid(a, c, k)) for k in (0, 1) for a, c in q))
    lines += ["*Nset, nset=BASE"] + _ids([nid(i, 0, k) for k in (0, 1) for i in range(n)])
    lines += ["*Nset, nset=PROBE"] + _ids([nid(n // 8, m // 2, k) for k in (0, 1)])
    e1, e2, e3, n12, n13, n23, g12, g13, g23 = SC_PLY
    lines += ["*Material, name=PLY", "*Elastic, type=ENGINEERING CONSTANTS",
              f"{e1:g}, {e2:g}, {e3:g}, {n12:g}, {n13:g}, {n23:g}, {g12:g}, {g13:g},", f"{g23:g}",
              "*Orientation, name=HOOP, system=CYLINDRICAL", "0., 0., 0., 0., 0., 1.",
              "*Shell Section, elset=CYL, material=PLY, orientation=HOOP", f"{t:g}",
              "*Step", "*Static", "*Boundary", "BASE, 3, 3"]
    for i, d in ((0, 2), (n // 2, 2), (n // 4, 1), (3 * n // 4, 1)):
        lines += [f"{nid(i, 0, k)}, {d}, {d}" for k in (0, 1)]
    lines += ["*Dload"] + [f"{e}, P1, 1." for e in range(1, n * m + 1)]      # the inner face
    lines += ["*Node print, nset=PROBE", "U", "*End Step"]
    return "\n".join(lines) + "\n"


def sc_cylinder_stack_deck(composite=True, n=24, m=2, t=0.01, eps=1e-3):
    """sc_cylinder_hoop_deck's cylinder with its SC8R elements numbered radially along their
    direction 1 and axially along 3, as [0/90/0] plies of SC_PLY or one layer, STACK
    DIRECTION=ORIENTATION with the cylindrical *ORIENTATION without a rotation line, stretched
    by the axial strain ``eps`` prescribed at its ends.  Abaqus stacks along the system's axis
    1, radial (2017 "About shell elements"), so the axial force is the wall's membrane force
    with the hoop free (sc_cylinder_stack_force); stacked along axis 3 the plies would be
    slices of the length, the material's axis 3 axial."""
    nid = lambda i, j, k: 1 + i % n + n * j + n * (m + 1) * k      # noqa: E731
    lines = ["*Heading", "Thin open cylinder stretched along its axis: SC8R continuum shells "
             "stacked by a cylindrical *Orientation", "*Node"]
    for k, r in enumerate((1.0 - t / 2, 1.0 + t / 2)):
        for j in range(m + 1):
            for i in range(n):
                th = 2 * math.pi * i / n
                lines.append(f"{nid(i, j, k)}, {r * math.cos(th):.12g}, {r * math.sin(th):.12g}, {j / m:.12g}")
    lines.append("*Element, type=SC8R, elset=CYL")
    q = [(0, 0), (0, 1), (1, 1), (1, 0)]                  # outward, then around: direction 1 radial
    for j in range(m):
        for i in range(n):
            lines.append(f"{1 + i + n * j}, " + ", ".join(str(nid(i + a, j + c, k)) for c in (0, 1) for a, k in q))
    lines += ["*Nset, nset=BASE"] + _ids([nid(i, 0, k) for k in (0, 1) for i in range(n)])
    lines += ["*Nset, nset=TOP"] + _ids([nid(i, m, k) for k in (0, 1) for i in range(n)])
    e1, e2, e3, n12, n13, n23, g12, g13, g23 = SC_PLY
    lines += ["*Material, name=PLY", "*Elastic, type=ENGINEERING CONSTANTS",
              f"{e1:g}, {e2:g}, {e3:g}, {n12:g}, {n13:g}, {n23:g}, {g12:g}, {g13:g},", f"{g23:g}",
              "*Orientation, name=CYL, system=CYLINDRICAL", "0., 0., 0., 0., 0., 1."]
    if composite:
        lines += ["*Shell Section, elset=CYL, composite, stack direction=ORIENTATION, orientation=CYL",
                  "1., 3, PLY, 0.", "1., 3, PLY, 90.", "1., 3, PLY, 0."]
    else:
        lines += ["*Shell Section, elset=CYL, material=PLY, stack direction=ORIENTATION, orientation=CYL",
                  f"{t:g}"]
    lines += ["*Step", "*Static", "*Boundary", "BASE, 3, 3", f"TOP, 3, 3, {eps:g}"]
    for i, d in ((0, 2), (n // 2, 2), (n // 4, 1), (3 * n // 4, 1)):
        lines += [f"{nid(i, 0, k)}, {d}, {d}" for k in (0, 1)]
    lines += ["*Node print, nset=TOP, totals=ONLY", "RF", "*End Step"]
    return "\n".join(lines) + "\n"


def sc_cylinder_stack_force(composite=True, n=24, t=0.01, eps=1e-3):
    """The axial force sc_cylinder_stack_deck must give: its faceted wall (flat elements, faces
    t cos(pi / n) apart, mid-surface perimeter 2 n sin(pi / n)) under the axial strain ``eps``
    with no hoop force, from the plane-stress stiffness of radial plies whose direction 1 is the
    system's axis 2, the hoop (classical lamination theory, which the faceted model follows to
    about 2e-5: its hoop and thickness contractions do not quite fit at the corners)."""
    plies = (0.0, 90.0, 0.0) if composite else (0.0,)
    a11 = a22 = a12 = 0.0
    for ang in plies:
        q11, q22, q12 = reduced_stiffness(ang, SC_PLY)[:3]
        a11, a22, a12 = a11 + q11 * t / len(plies), a22 + q22 * t / len(plies), a12 + q12 * t / len(plies)
    return n * math.sin(2 * math.pi / n) * (a22 - a12 * a12 / a11) * eps


def cylinder_hoop_deck(rotation="", n=24, m=2, t=0.01):
    """A thin open cylinder (radius 1, length 1, axis z) of S4 shells under internal pressure 1,
    an orthotropic ply (INPLANE_PLY) with a cylindrical *ORIENTATION about the axis and an
    optional rotation line: its axis 1, radial, is the shell normal, so Abaqus projects its
    axis 2 and the fibres follow the hoop (a rotation about axis 3 keeps them there), and
    thin-wall theory gives the radial displacement 1 / (E1 t)."""
    nid = lambda i, j: 1 + i % n + n * j      # noqa: E731
    lines = ["*Heading", "Thin open cylinder of a hoop-wound orthotropic ply under internal "
             "pressure: a cylindrical *Orientation", "*Node"]
    for j in range(m + 1):
        for i in range(n):
            th = 2 * math.pi * i / n
            lines.append(f"{nid(i, j)}, {math.cos(th):.12g}, {math.sin(th):.12g}, {j / m:.12g}")
    lines.append("*Element, type=S4, elset=CYL")
    for j in range(m):
        for i in range(n):
            lines.append(f"{1 + i + n * j}, {nid(i, j)}, {nid(i + 1, j)}, {nid(i + 1, j + 1)}, {nid(i, j + 1)}")
    lines += ["*Nset, nset=BASE"] + _ids([nid(i, 0) for i in range(n)])
    lines += ["*Nset, nset=PROBE", str(nid(n // 8, m // 2))]
    e1, e2, e3, n12, n13, n23, g12, g13, g23 = INPLANE_PLY
    lines += ["*Material, name=PLY", "*Elastic, type=ENGINEERING CONSTANTS",
              f"{e1:g}, {e2:g}, {e3:g}, {n12:g}, {n13:g}, {n23:g}, {g12:g}, {g13:g},", f"{g23:g}",
              "*Orientation, name=HOOP, system=CYLINDRICAL", "0., 0., 0., 0., 0., 1."]
    lines += [rotation] if rotation else []
    lines += ["*Shell Section, elset=CYL, material=PLY, orientation=HOOP", f"{t:g}, 5",
              "*Step", "*Static", "*Boundary", "BASE, 3, 3", f"{nid(0, 0)}, 2, 2", f"{nid(n // 2, 0)}, 2, 2",
              f"{nid(n // 4, 0)}, 1, 1", f"{nid(3 * n // 4, 0)}, 1, 1", "*Dload"]
    lines += [f"{e}, P, 1." for e in range(1, n * m + 1)]       # along the outward normal
    lines += ["*Node print, nset=PROBE", "U", "*End Step"]
    return "\n".join(lines) + "\n"


def sphere_hoop_deck(kind="s4r", rotation="", m=24, n=24, t=0.01):
    """A thin sphere (mean radius 1, centre at the origin, thickness t) under internal pressure
    1, meshed along its parallels and meridians (2 m rings from pole to pole, 4 n elements
    around: S3 / SC6R at the poles, S4R / SC8R elsewhere) and held against rigid-body motion
    only, at four nodes of the equator: a plain section of INPLANE_PLY on S4R shells or SC8R
    continuum shells (stacked outward, the pressure on the inner face), or [0/90/0] SC8R plies
    (``kind`` "s4r", "sc8r", "sc8r_composite"), with a spherical *ORIENTATION about the z axis
    and an optional rotation line; "s4r_iso" and "sc8r_iso" are plain sections of isotropic
    steel, the continuum shells stacked along the orientation (Abaqus' LE3 hemisphere has one),
    with their element stresses printed.  The system's axis 1, radial, is the normal: Abaqus projects
    its axis 2, along the parallels (a rotation about axis 3 keeps it there).  Returns the deck
    and (colatitude, longitude, the node of each layer) of the nodes between colatitudes 30 and
    150 degrees, where sphere_membrane applies."""
    nr, na = 2 * m, 4 * n
    iso = kind.endswith("_iso")
    kind = kind[:-4] if iso else kind
    radii = (1.0,) if kind == "s4r" else (1.0 - t / 2, 1.0 + t / 2)
    per = 2 + (nr - 1) * na                            # nodes per layer: the poles, the rings
    nid = lambda i, j, k=0: (1 if i == 0 else per if i == nr else 2 + (i - 1) * na + j % na) + per * k  # noqa: E731
    lines = ["*Heading", ("Thin isotropic sphere" if iso else "Thin sphere of an orthotropic ply wound "
             "along its parallels") + " under internal pressure: a spherical *Orientation", "*Node"]
    for k, r in enumerate(radii):
        for i in range(nr + 1):
            th = math.pi * i / nr
            for j in range(na) if 0 < i < nr else (0,):
                ph = 2 * math.pi * j / na
                lines.append(f"{nid(i, j, k)}, {r * math.sin(th) * math.cos(ph):.12g}, "
                             f"{r * math.sin(th) * math.sin(ph):.12g}, {r * math.cos(th):.12g}")
    caps = [(nid(0, 0), nid(1, j), nid(1, j + 1)) for j in range(na)] + \
        [(nid(nr, 0), nid(nr - 1, j + 1), nid(nr - 1, j)) for j in range(na)]
    quads = [(nid(i, j), nid(i + 1, j), nid(i + 1, j + 1), nid(i, j + 1)) for i in range(1, nr - 1) for j in range(na)]
    shell = kind == "s4r"
    elems = [(("S3" if shell else "SC6R"), c) for c in caps] + [(("S4R" if shell else "SC8R"), c) for c in quads]
    for typ in dict.fromkeys(ty for ty, _ in elems):
        lines.append(f"*Element, type={typ}, elset=SPHERE")
        lines += [f"{e}, " + ", ".join(str(x) for x in (c if shell else c + tuple(x + per for x in c)))
                  for e, (ty, c) in enumerate(elems, 1) if ty == typ]
    probes = [(math.pi * i / nr, 2 * math.pi * j / na, tuple(nid(i, j, k) for k in range(len(radii))))
              for i in range(nr // 6, nr - nr // 6 + 1) for j in range(na)]
    lines += ["*Nset, nset=PROBE"] + _ids([x for _th, _ph, ks in probes for x in ks])
    e1, e2, e3, n12, n13, n23, g12, g13, g23 = INPLANE_PLY
    lines += ["*Material, name=PLY"] + (["*Elastic", f"{ISO_STEEL[0]:g}, {ISO_STEEL[3]:g}"] if iso else [
        "*Elastic, type=ENGINEERING CONSTANTS",
        f"{e1:g}, {e2:g}, {e3:g}, {n12:g}, {n13:g}, {n23:g}, {g12:g}, {g13:g},", f"{g23:g}"])
    lines += ["*Orientation, name=SPH, system=SPHERICAL", "0., 0., 0., 0., 0., 1."]
    lines += [rotation] if rotation else []
    if kind == "sc8r_composite":
        lines += ["*Shell Section, elset=SPHERE, composite, orientation=SPH",
                  "1., 3, PLY, 0.", "1., 3, PLY, 90.", "1., 3, PLY, 0."]
    else:
        lines += ["*Shell Section, elset=SPHERE, material=PLY, orientation=SPH"
                  + (", stack direction=ORIENTATION" if iso and not shell else ""), f"{t:g}, 5" if shell else f"{t:g}"]
    lines += ["*Step", "*Static", "*Boundary"]
    for k in range(len(radii)):                       # the equator at 0, 90, 180 and 270 degrees
        lines += [f"{nid(m, 0, k)}, 2, 3", f"{nid(m, 2 * n, k)}, 2, 3", f"{nid(m, n, k)}, 1, 1",
                  f"{nid(m, n, k)}, 3, 3", f"{nid(m, 3 * n, k)}, 3, 3"]
    lines += ["*Dload"] + (["SPHERE, P, 1."] if shell else [f"{e}, P1, 1." for e in range(1, len(elems) + 1)])
    lines += ["*Node print, nset=PROBE", "U"] + (["*El print, elset=SPHERE", "S"] if iso else []) + ["*End Step"]
    return "\n".join(lines) + "\n", probes


def sphere_membrane(theta, kind="s4r", t=0.01):
    """Membrane theory for sphere_hoop_deck at colatitude ``theta`` (radians): the radial and the
    meridional displacement (along increasing colatitude).  Equilibrium alone gives both stress
    resultants, p rp^2 / 2 with the pressure on a surface of radius rp: the shells' reference
    surface (rp = 1, as Abaqus loads them), the continuum shells' inner face (1 - t / 2); the
    plies' membrane stiffness, direction 1 along the parallels, gives the strains ec along them
    and em along the meridians.  With the equator a plane of symmetry the meridional
    displacement is (em - ec) sin(theta) ln tan(theta / 2) and the radial one ec - u cot(theta);
    near the poles, where the material directions turn about a point, the shell bends instead.
    An isotropic sphere ("_iso") expands evenly: no meridional displacement."""
    props = ISO_STEEL if kind.endswith("_iso") else INPLANE_PLY
    rp = 1.0 if kind.startswith("s4r") else 1.0 - t / 2
    force = rp * rp / 2
    a11 = a22 = a12 = 0.0
    plies = (0.0, 90.0, 0.0) if kind == "sc8r_composite" else (0.0,)
    for ang in plies:
        q11, q22, q12 = reduced_stiffness(ang, props)[:3]
        a11, a22, a12 = a11 + q11 * t / len(plies), a22 + q22 * t / len(plies), a12 + q12 * t / len(plies)
    det = a11 * a22 - a12 * a12
    ec, em = force * (a22 - a12) / det, force * (a11 - a12) / det
    u = (em - ec) * math.sin(theta) * math.log(math.tan(theta / 2))
    return ec - u / math.tan(theta), u


# a turned rectangular system (points a, b) for the initial-condition and deformation-plasticity
# checks, and the corners of a unit cube in Abaqus' C3D8 order
TURNED_AB = ((0.8, 0.6, 0.0), (-0.36, 0.48, 0.8))
CUBE_CORNERS = ((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1))
IC_STRESS = (100.0, -40.0, 25.0, 30.0, -20.0, 15.0)
IC_STRESS_BLANK = (100.0, 0.0, 25.0, 30.0, -20.0, 15.0)    # written "100, , 25, ...": syy = 0
IC_PLASTIC = (0.004, -0.001, -0.003, 0.002, -0.0015, 0.001)        # engineering shear, as Abaqus


def local_to_global(ab, s):
    """The global components (11, 22, 33, 12, 13, 23) of the symmetric tensor ``s`` given in the
    rectangular system of points ``ab``: R s R^T, R's columns its unit axes."""
    e1 = _unit(ab[0])
    e3 = _unit(_cross(ab[0], ab[1]))
    e2 = _cross(e3, e1)
    r = [[e1[i], e2[i], e3[i]] for i in range(3)]
    g = _matmul(_matmul(r, [[s[0], s[3], s[4]], [s[3], s[1], s[5]], [s[4], s[5], s[2]]]),
                [list(x) for x in zip(*r)])
    return [g[0][0], g[1][1], g[2][2], g[0][1], g[0][2], g[1][2]]


# thermal_expansion_elastic_forms: an orthotropic material's engineering constants, and the
# normal and (Abaqus' engineering) shear coefficients of its ANISO *Expansion
EXP_EC = (150000., 10000., 12000., 0.3, 0.25, 0.4, 5000., 6000., 3500.)
EXP_ALPHA = (1e-5, 2e-5, 3e-5)
EXP_SHEAR = (8e-6, -6e-6, 4e-6)
# (case, *Elastic form, expansion with shear terms, material axes TURNED_AB)
EXP_FORMS_LINEAR = (("EC_SHEAR", "ec", True, False), ("ORTHO_PLAIN", "ortho", False, False),
                    ("EC_TURNED", "ec", False, True), ("ORTHO_TURNED", "ortho", True, True),
                    ("ANISO_TURNED", "aniso", True, True), ("ISO_TURNED", "iso", True, True))
EXP_FORMS_NLGEOM = (("EC_PLAIN", "ec", False, False), ("ORTHO_PLAIN", "ortho", False, False))
# the 21 constants of Abaqus' *Elastic, type=ANISOTROPIC as (row, column) of the VOIGT matrix
ABAQUS_ANISO_ORDER = ((0, 0), (0, 1), (1, 1), (0, 2), (1, 2), (2, 2), (0, 3), (1, 3), (2, 3), (3, 3),
                      (0, 4), (1, 4), (2, 4), (3, 4), (4, 4), (0, 5), (1, 5), (2, 5), (3, 5), (4, 5),
                      (5, 5))


def expansion_form_stiffness(form):
    """The 6 x 6 stiffness (VOIGT order, engineering shear) in its material axes of a
    thermal_expansion_elastic_forms *Elastic form: isotropic, EXP_EC's (as engineering constants
    or orthotropic D's), or EXP_EC's with normal-shear couplings (anisotropic)."""
    if form == "iso":
        return _ortho_stiffness6((200000.,) * 3 + (0.3,) * 3 + (200000. / 2.6,) * 3)
    c = _ortho_stiffness6(EXP_EC)
    if form == "aniso":
        for (i, j), v in (((0, 3), 1500.), ((1, 5), -400.), ((2, 4), 600.), ((3, 4), 300.)):
            c[i][j] = c[j][i] = v
    return c


def expansion_forms_deck(cases, nlgeom=False, dt=100.0):
    """thermal_expansion_elastic_forms: per case k (name, *Elastic form, shear terms, turned) a
    free unit C3D8 cube held 3-2-1 (nodes 100 k + 1-8) and a clamped one (100 k + 11-18), heated
    by ``dt``, of a material with that *Elastic beside an ANISO *Expansion (EXP_ALPHA, with
    EXP_SHEAR or zero shear terms) in TURNED_AB's axes or the global ones.  Returns the deck
    and, per case, (first node of the free cube, of the clamped cube, the global thermal strain,
    the clamped cube's global stress), each (11, 22, 33, 12, 13, 23) with tensor shear."""
    lines = ["*Heading", "*Elastic forms beside an anisotropic *Expansion", "*Node, nset=NALL"]
    model, expect = [], []
    for k, (name, form, shear, turned) in enumerate(cases, 1):
        free, held = 100 * k + 1, 100 * k + 11
        for base, x0 in ((free, 4.0 * k), (held, 4.0 * k + 2.0)):
            lines += [f"{base + i}, {x + x0:g}, {y}., {z}." for i, (x, y, z) in enumerate(CUBE_CORNERS)]
        c = expansion_form_stiffness(form)
        if form == "iso":
            elastic = ["*Elastic", "200000., 0.3"]
        elif form == "ec":
            elastic = ["*Elastic, type=ENGINEERING CONSTANTS", ", ".join(f"{v:g}" for v in EXP_EC[:8]),
                       f"{EXP_EC[8]:g}"]
        else:
            ij = ABAQUS_ANISO_ORDER if form == "aniso" else \
                ((0, 0), (0, 1), (1, 1), (0, 2), (1, 2), (2, 2), (3, 3), (4, 4), (5, 5))
            vals = [f"{c[i][j]:.12g}" for i, j in ij]
            elastic = [f"*Elastic, type={'ANISOTROPIC' if form == 'aniso' else 'ORTHOTROPIC'}"]
            elastic += [", ".join(vals[i:i + 8]) for i in range(0, len(vals), 8)]
        terms = EXP_SHEAR if shear else (0.0, 0.0, 0.0)
        section = f"*Solid Section, elset=E_{name}, material=M_{name}"
        model += [f"*Element, type=C3D8, elset=E_{name}",
                  f"{100 * k + 1}, " + ", ".join(str(free + i) for i in range(8)),
                  f"{100 * k + 2}, " + ", ".join(str(held + i) for i in range(8)),
                  f"*Nset, nset=C_{name}", ", ".join(str(held + i) for i in range(8)),
                  section + (", orientation=TURNED" if turned else ""),
                  ",", f"*Material, name=M_{name}"] + elastic + \
                 ["*Expansion, type=ANISO", ", ".join(f"{a:g}" for a in EXP_ALPHA + terms),
                  "*Boundary", f"{free}, 1, 3", f"{free + 1}, 2, 3", f"{free + 3}, 3, 3", f"C_{name}, 1, 3"]
        eps = [a * dt for a in EXP_ALPHA] + [a * dt / 2 for a in terms]
        eng = eps[:3] + [2 * e for e in eps[3:]]
        sig = [-sum(c[i][j] * eng[j] for j in range(6)) for i in range(6)]
        if turned:
            eps, sig = local_to_global(TURNED_AB, eps), local_to_global(TURNED_AB, sig)
        expect.append((free, held, eps, sig))
    lines += ["*Orientation, name=TURNED", ", ".join(f"{x:g}" for x in TURNED_AB[0] + TURNED_AB[1])]
    lines += model + ["*Initial Conditions, type=TEMPERATURE", "NALL, 0.",
                      "*Step, nlgeom" if nlgeom else "*Step", "*Static"] + (["0.25, 1."] if nlgeom else [])
    lines += ["*Temperature", f"NALL, {dt:g}", "*Node Print, nset=NALL", "U, RF", "*End Step"]
    return "\n".join(lines) + "\n", expect


def expansion_forms_errors(dat, expect):
    """(worst relative error of the free cubes' strains, of the clamped cubes' stresses) of an
    expansion_forms_deck run against its ``expect``; None when results are missing.  The strain
    comes from the corner displacements, the stress from the reaction forces on the clamped
    cube's faces x = 1, y = 1 and z = 1 (their sums are the stress columns of a unit cube)."""
    u = dat_displacements(dat)
    forces = dat_node_blocks(dat, "forces")
    if not forces:
        return None
    rf = forces[-1]
    worst = [0.0, 0.0]
    for free, held, eps_ref, sig_ref in expect:
        corner = [u.get(free + k) for k in (0, 1, 3, 4)]
        if any(v is None for v in corner) or any(held + k not in rf for k in range(8)):
            return None
        h = [[corner[j + 1][i] - corner[0][i] for j in range(3)] for i in range(3)]   # du_i / dx_j
        eps = [h[0][0], h[1][1], h[2][2], (h[0][1] + h[1][0]) / 2, (h[0][2] + h[2][0]) / 2,
               (h[1][2] + h[2][1]) / 2]
        faces = [[k for k, p in enumerate(CUBE_CORNERS) if p[j] == 1] for j in range(3)]
        col = [[sum(rf[held + k][i] for k in faces[j]) for i in range(3)] for j in range(3)]
        sig = [col[0][0], col[1][1], col[2][2], col[1][0], col[2][0], col[2][1]]
        for w, got, ref in ((0, eps, eps_ref), (1, sig, sig_ref)):
            worst[w] = max(worst[w], max(abs(g - r) for g, r in zip(got, ref)) / max(abs(r) for r in ref))
    return worst


def ic_cube_deck(kind, vals=None, blank=False):
    """A free unit C3D8 cube (held against rigid motion only) with an initial stress IC_STRESS
    (``kind`` "stress"; E 1000, nu 0.25) or plastic strain IC_PLASTIC ("plastic"; a *Plastic
    material that stays elastic), or ``vals``, given in TURNED_AB's axes, which Abaqus reads
    them in (2017 Keywords *INITIAL CONDITIONS).  ``blank``: the zeros of the *Orientation line
    and the initial values written as blank fields, which Abaqus reads as 0."""
    num = lambda x: "" if blank and x == 0 else f"{x:g}"     # noqa: E731
    lines = ["*Heading", f"Free cube with an initial {kind} given in a turned *Orientation", "*Node, nset=ALL"]
    lines += [f"{k}, {x}., {y}., {z}." for k, (x, y, z) in enumerate(CUBE_CORNERS, 1)]
    lines += ["*Element, type=C3D8, elset=CUBE", "1, 1, 2, 3, 4, 5, 6, 7, 8",
              "*Orientation, name=TURNED", ", ".join(num(x) for x in TURNED_AB[0] + TURNED_AB[1]),
              "*Material, name=M", "*Elastic", "1000., 0.25"]
    lines += ["*Plastic", "1.e6, 0.", "1.1e6, 1."] if kind == "plastic" else []
    vals = vals or (IC_PLASTIC if kind == "plastic" else IC_STRESS)
    lines += ["*Solid Section, elset=CUBE, material=M, orientation=TURNED",
              f"*Initial Conditions, type={'PLASTIC STRAIN' if kind == 'plastic' else 'STRESS'}",
              "CUBE, " + ", ".join(num(x) for x in vals),
              "*Boundary", "1, 1, 3", "2, 2, 3", "4, 3, 3", "*Step", "*Static",
              "*Node Print, nset=ALL", "U", "*End Step"]
    return "\n".join(lines) + "\n"


def ic_temperature_cards_deck():
    """Two free unit C3D8 cubes (E 1000, alpha 1e-3, held against rigid motion only), A at the
    origin and B at x = 3, with one *INITIAL CONDITIONS, TYPE=TEMPERATURE card per set, as CAE
    writes them: A at 100, B's bottom at 0 (its top, on no card, starts at the Abaqus default
    0); the step heats A to 120 and B to 20, so both expand freely by 20 alpha."""
    corners = CUBE_CORNERS
    lines = ["*Heading", "Two free cubes, initial temperatures on two cards", "*Node, nset=ALLN"]
    lines += [f"{k}, {x}., {y}., {z}." for k, (x, y, z) in enumerate(corners, 1)]
    lines += [f"{k + 10}, {x + 3}., {y}., {z}." for k, (x, y, z) in enumerate(corners, 1)]
    lines += ["*Element, type=C3D8, elset=CUBES", "1, 1, 2, 3, 4, 5, 6, 7, 8",
              "2, 11, 12, 13, 14, 15, 16, 17, 18", "*Nset, nset=A, generate", "1, 8, 1",
              "*Nset, nset=B, generate", "11, 18, 1", "*Nset, nset=BBOT, generate", "11, 14, 1",
              "*Material, name=M", "*Elastic", "1000., 0.3", "*Expansion", "1.e-3",
              "*Solid Section, elset=CUBES, material=M",
              "*Initial Conditions, type=TEMPERATURE", "A, 100.",
              "*Initial Conditions, type=TEMPERATURE", "BBOT, 0.",
              "*Boundary", "1, 1, 3", "2, 2, 3", "4, 3, 3", "11, 1, 3", "12, 2, 3", "14, 3, 3",
              "*Step", "*Static", "*Temperature", "A, 120.", "B, 20.",
              "*Node Print, nset=ALLN", "U", "*End Step"]
    return "\n".join(lines) + "\n"


def mesh_generation_ring_deck(generated=True, nr=4, nt=8, a=1.0, b=2.0, h=0.1, p=1.0, skew=0.0):
    """A quarter annulus a < r < b of C3D8 (nr x nt elements, thickness h; the planes x = 0 and
    y = 0 held normal, every node in z: plane strain; E 1000, nu 0.3) under an internal pressure
    p.  ``generated``: the mesh comes from Abaqus' generation cards with blank (default) fields
    -- the bottom arcs by *NGEN, LINE=C about a centre given by coordinates (fields 5-7; the
    outer one backwards, its normal in 8-10), the radial lines by *NFILL with the default
    increment, the top face by *NCOPY, MULTIPLE (translated once, then turned nt + 1 times
    from a seed line at -90 / nt degrees) and the elements by *ELGEN with blank increments.
    ``skew``: each arc's end nodes at r (1 -/+ skew), which Abaqus moves radially onto one
    circle (their mean distance, r: "Node definition").  Otherwise every node and element is
    listed, at the same places."""
    def bot(k, r):
        return 1 + 10 * k + r

    def top(k, r):
        return 1001 + 10 * k + r

    def xy(k, r, th0=0.0):
        rad, th = a + (b - a) * r / nr, math.radians(90.0 * k / nt + th0)
        return rad * math.cos(th), rad * math.sin(th)
    lines = ["*Heading", "Quarter annulus under internal pressure, plane strain"]
    if generated:
        dth = 90.0 / nt
        lo, hi = 1.0 - skew, 1.0 + skew
        lines += ["*Node", f"{bot(0, 0)}, {a * lo!r}, 0., 0.", f"{bot(nt, 0)}, 0., {a * hi!r}, 0.",
                  f"{bot(0, nr)}, {b * hi!r}, 0., 0.", f"{bot(nt, nr)}, 0., {b * lo!r}, 0.",
                  "*Ngen, line=C, nset=INNER", f"{bot(0, 0)}, {bot(nt, 0)}, 10, , 0., 0., 0.",
                  "*Ngen, line=C, nset=OUTER", f"{bot(nt, nr)}, {bot(0, nr)}, -10, , 0., 0., 0., 0., 0., -1.",
                  "*Nfill, nset=BOT", f"INNER, OUTER, {nr}", "*Node, nset=SEED"]
        lines += [f"{991 + r}, {xy(0, r, -dth)[0]!r}, {xy(0, r, -dth)[1]!r}, 0." for r in range(nr + 1)]
        lines += [f"*Ncopy, old set=SEED, new set=TOP, change number=10, shift, multiple={nt + 1}",
                  f"0., 0., {h}", f"0., 0., 0., 0., 0., 1., {dth!r}", "*Element, type=C3D8, elset=RING",
                  f"1, {bot(0, 0)}, {bot(0, 1)}, {bot(1, 1)}, {bot(1, 0)}, {top(0, 0)}, {top(0, 1)}, "
                  f"{top(1, 1)}, {top(1, 0)}", "*Elgen, elset=RING", f"1, {nr}, , , {nt}, 10, 10"]
    else:
        for name, nid, z in (("BOT", bot, 0.0), ("TOP", top, h)):
            lines += [f"*Node, nset={name}"] + [f"{nid(k, r)}, {xy(k, r)[0]!r}, {xy(k, r)[1]!r}, {z}"
                                                for k in range(nt + 1) for r in range(nr + 1)]
        lines += ["*Element, type=C3D8, elset=RING"] + [
            f"{bot(k, r)}, {bot(k, r)}, {bot(k, r + 1)}, {bot(k + 1, r + 1)}, {bot(k + 1, r)}, "
            f"{top(k, r)}, {top(k, r + 1)}, {top(k + 1, r + 1)}, {top(k + 1, r)}"
            for k in range(nt) for r in range(nr)]
    lines += ["*Nset, nset=MESH", "BOT, TOP",
              "*Nset, nset=Y0", ", ".join(str(f(0, r)) for f in (bot, top) for r in range(nr + 1)),
              "*Nset, nset=X0", ", ".join(str(f(nt, r)) for f in (bot, top) for r in range(nr + 1)),
              "*Elset, elset=INNER, generate", f"1, {bot(nt - 1, 0)}, 10",
              "*Solid Section, elset=RING, material=M", "*Material, name=M", "*Elastic", "1000., 0.3",
              "*Boundary", "MESH, 3, 3", "Y0, 2, 2", "X0, 1, 1", "*Step", "*Static",
              "*Dload", f"INNER, P6, {p}", "*Node Print, nset=MESH", "U", "*End Step"]
    return "\n".join(lines) + "\n"


def ncopy_pole_deck(f=10.0):
    """Three T3D2 bars in a row along x (length 1, area 1, E 1000), fixed at x = 0 and pulled
    along x by ``f`` at x = 3.  The far nodes come from *NCOPY, POLE: node 11 projected from the
    pole node at x = 0, node 21 from a pole given by its coordinates at x = 1 (Abaqus: each
    old node midway between the pole and its copy)."""
    return ("*Heading\nBars in a row whose far nodes *NCOPY, POLE makes\n"
            "*Node\n100, 0., 0., 0.\n*Node, nset=A\n1, 1., 0., 0.\n"
            "*Ncopy, old set=A, new set=B, change number=10, pole\n100\n"
            "*Ncopy, old set=B, new set=C, change number=10, pole\n, 1., 0., 0.\n"
            "*Element, type=T3D2, elset=BARS\n1, 100, 1\n2, 1, 11\n3, 11, 21\n"
            "*Solid Section, elset=BARS, material=M\n1.\n*Material, name=M\n*Elastic\n1000., 0.3\n"
            "*Nset, nset=ALLN\n100, 1, 11, 21\n*Boundary\n100, 1, 3\nALLN, 2, 3\n"
            f"*Step\n*Static\n*Cload\n21, 1, {f!r}\n*Node Print, nset=ALLN\nU\n*End Step\n")


def ic_annulus_deck(nr=8, nt=18, t=0.1, a=1.0, b=2.0, s0=100.0):
    """A quarter annulus a < r < b of C3D20R (nr x nt elements, thickness t; the planes x = 0 and
    y = 0 held normal, every node in z: plane strain; E 1000, nu 0.3) with a uniform initial
    hoop stress s0 in a cylindrical *Orientation about the z axis, whose axis 2 is
    tangential.  Returns the deck and {node: (x, y)}."""
    ids: dict = {}

    def nid(i, j, k):                                  # half steps radially, around, in z
        if (i, j, k) not in ids:
            r, th = a + (b - a) * i / (2 * nr), math.pi / 2 * j / (2 * nt)
            ids[(i, j, k)] = (len(ids) + 1, r * math.cos(th), r * math.sin(th), t * k / 2)
        return ids[(i, j, k)][0]
    lines = ["*Heading", "Quarter annulus with an initial hoop stress in a cylindrical *Orientation"]
    elems = []
    for i in range(0, 2 * nr, 2):
        for j in range(0, 2 * nt, 2):
            pts = [(i, j, 0), (i + 2, j, 0), (i + 2, j + 2, 0), (i, j + 2, 0), (i, j, 2), (i + 2, j, 2),
                   (i + 2, j + 2, 2), (i, j + 2, 2), (i + 1, j, 0), (i + 2, j + 1, 0), (i + 1, j + 2, 0),
                   (i, j + 1, 0), (i + 1, j, 2), (i + 2, j + 1, 2), (i + 1, j + 2, 2), (i, j + 1, 2),
                   (i, j, 1), (i + 2, j, 1), (i + 2, j + 2, 1), (i, j + 2, 1)]
            elems.append([nid(*p) for p in pts])
    nodes = sorted(ids.values())
    lines += ["*Node, nset=ALL"] + [f"{n}, {x:.12f}, {y:.12f}, {z:.12f}" for n, x, y, z in nodes]
    lines += ["*Element, type=C3D20R, elset=RING"]
    for e, conn in enumerate(elems, 1):
        lines += [f"{e}, " + ", ".join(map(str, conn[:15])) + ",", ", ".join(map(str, conn[15:]))]
    lines += ["*Nset, nset=X0"] + _ids([n for n, x, _y, _z in nodes if abs(x) < 1e-9])
    lines += ["*Nset, nset=Y0"] + _ids([n for n, _x, y, _z in nodes if abs(y) < 1e-9])
    lines += ["*Orientation, name=CYL, system=CYLINDRICAL", "0., 0., 0., 0., 0., 1.",
              "*Material, name=M", "*Elastic", "1000., 0.3",
              "*Solid Section, elset=RING, material=M, orientation=CYL",
              "*Initial Conditions, type=STRESS", f"RING, 0., {s0:g}, 0., 0., 0., 0.",
              "*Boundary", "X0, 1, 1", "Y0, 2, 2", "ALL, 3, 3", "*Step", "*Static",
              "*Node Print, nset=ALL", "U", "*End Step"]
    return "\n".join(lines) + "\n", {n: (x, y) for n, x, y, _z in nodes}


def annulus_hoop_displacement(r, s0=100.0, e=1000.0, nu=0.3, a=1.0, b=2.0):
    """The radial displacement at radius r of ic_annulus_deck: with sigma = s0 e_t e_t + C eps
    the plane-strain annulus' radial equilibrium is (lambda + 2 mu)(u'' + u'/r - u/r^2) = s0 / r,
    so u = c r ln r + A r + B / r, c = s0 / (2 (lambda + 2 mu)), with A and B from the free
    surfaces sigma_r(a) = sigma_r(b) = 0, sigma_r = (lambda + 2 mu) u' + lambda u / r."""
    lam, mu = e * nu / ((1 + nu) * (1 - 2 * nu)), e / (2 * (1 + nu))
    big = lam + 2 * mu
    c = s0 / (2 * big)
    bb = (big + lam) * c * math.log(b / a) / ((big - lam) * (1 / b ** 2 - 1 / a ** 2))
    aa = ((big - lam) * bb / a ** 2 - (big + lam) * c * math.log(a) - big * c) / (big + lam)
    return c * r * math.log(r) + aa * r + bb / r


# the continuum-shell initial-condition checks: a plate off the x-y plane (unit normal
# SC_IC_NORMAL, rows along SC_IC_ROW), an orientation whose axes leave it, turned 25 degrees about
# axis 3 (Abaqus projects the turned axis 1), Abaqus' continuum-shell components 11, 22, 12 (2017
# "Continuum shell element library") of a stress and a plastic strain (engineering shear), and an
# in-plane strain the same in any ply's axes
SC_IC_NORMAL = (1.0 / 3.0, 2.0 / 3.0, 2.0 / 3.0)
SC_IC_ROW = (2.0 / math.sqrt(5.0), -1.0 / math.sqrt(5.0), 0.0)
SC_IC_ORIENT = dict(a=(0.3, 0.9, -0.2), b=(-0.8, 0.2, 0.4), rot=(3, 25.0))
SC_IC_STRESS = (100.0, -40.0, 30.0)
SC_IC_PLASTIC = (0.004, -0.001, 0.002)
SC_IC_EPS0 = 1e-3


def sc_ic_ply_relaxed():
    """The initial stress (11, 22, 12) of sc_ic_plate_deck's plies, Q (e, e, 0) with SC_PLY's
    plane-stress stiffness Q and e = SC_IC_EPS0, and the strain (11, 22, 33, 12, 13, 23; tensor
    shear) it relaxes to in a ply's axes: -e in the plane, the free thickness's Poisson strain."""
    e1, e2, _e3, n12, n13, n23 = SC_PLY[:6]
    d = 1.0 - n12 * n12 * e2 / e1
    q11, q22, q12 = e1 / d, e2 / d, n12 * e2 / d
    s11, s22 = (q11 + q12) * SC_IC_EPS0, (q12 + q22) * SC_IC_EPS0
    return (s11, s22, 0.0), (-SC_IC_EPS0, -SC_IC_EPS0, n13 * s11 / e1 + n23 * s22 / e2, 0.0, 0.0, 0.0)


def sc_ic_plate_deck(kind="sc8r", ic="stress", orient=False, plies=None, n=3, t=0.1):
    """A free 1 x 1 continuum-shell plate t thick off the x-y plane (SC_IC_NORMAL; n x n SC8R,
    or two SC6R wedges per cell; held against rigid motion only) with an initial stress
    SC_IC_STRESS (``ic`` "stress"; E 1000, nu 0.25) or plastic strain SC_IC_PLASTIC ("plastic"; a
    *Plastic material that stays elastic) in Abaqus' shell axes: the orientation SC_IC_ORIENT
    projected onto the plate (``orient``), else global X projected.  With ``plies`` (layer
    angles) it is a composite of SC_PLY plies with the initial stress of sc_ic_ply_relaxed in
    each ply's axes, the shell axes turned by its angle: every ply relaxes to the same uniform
    strain only where its values are turned by its own axes.  Returns the deck, {node: xyz} and
    the shell axes (direction 1, 2, the normal)."""
    nrm, row = SC_IC_NORMAL, SC_IC_ROW
    col = _cross(nrm, row)
    nid = lambda i, j, k: 1 + i + (n + 1) * j + (n + 1) ** 2 * k      # noqa: E731
    xyz = {nid(i, j, k): tuple(i / n * a + j / n * b + t * k * c for a, b, c in zip(row, col, nrm))
           for k in range(2) for j in range(n + 1) for i in range(n + 1)}
    typ = kind.upper()
    lines = ["*Heading", f"Free {typ} plate off the x-y plane, an initial {ic} in Abaqus' shell axes",
             "*Node, nset=ALL"] + [f"{k}, " + ", ".join(f"{c:.15g}" for c in p) for k, p in sorted(xyz.items())]
    lines.append(f"*Element, type={typ}, elset=PLATE")
    e = 0
    for j in range(n):
        for i in range(n):
            q = [(i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)]
            b, tp = [nid(*p, 0) for p in q], [nid(*p, 1) for p in q]
            for conn in ([b + tp] if typ == "SC8R" else
                         [[b[0], b[1], b[2], tp[0], tp[1], tp[2]], [b[0], b[2], b[3], tp[0], tp[2], tp[3]]]):
                e += 1
                lines.append(f"{e}, " + ", ".join(map(str, conn)))
    ori = SC_IC_ORIENT if orient else None
    if ori:
        lines += ["*Orientation, name=TILTED", ", ".join(f"{c:g}" for c in (*ori["a"], *ori["b"])),
                  "{}, {:g}".format(*ori["rot"])]
    on = ", orientation=TILTED" if ori else ""
    if plies:
        sig = sc_ic_ply_relaxed()[0]
        e1, e2, e3, n12, n13, n23, g12, g13, g23 = SC_PLY
        lines += ["*Material, name=PLY", "*Elastic, type=ENGINEERING CONSTANTS",
                  f"{e1:g}, {e2:g}, {e3:g}, {n12:g}, {n13:g}, {n23:g}, {g12:g}, {g13:g},", f"{g23:g}",
                  f"*Shell Section, elset=PLATE, composite{on}"] + [f"1., 3, PLY, {ang:g}" for ang in plies]
    else:
        sig = SC_IC_PLASTIC if ic == "plastic" else SC_IC_STRESS
        lines += ["*Material, name=M", "*Elastic", "1000., 0.25"]
        lines += ["*Plastic", "1.e6, 0.", "1.1e6, 1."] if ic == "plastic" else []
        lines += [f"*Shell Section, elset=PLATE, material=M{on}", f"{t:g}"]
    lines += [f"*Initial Conditions, type={'PLASTIC STRAIN' if ic == 'plastic' else 'STRESS'}",
              "PLATE, " + ", ".join(f"{x:.15g}" for x in sig),
              "*Boundary", f"{nid(0, 0, 0)}, 1, 3", f"{nid(n, 0, 0)}, 2, 3", f"{nid(0, n, 0)}, 1, 1",
              "*Step", "*Static", "*Node Print, nset=ALL", "U", "*End Step"]
    d1 = abaqus_shell_direction(nrm, ori)
    return "\n".join(lines) + "\n", xyz, (d1, _cross(nrm, d1), nrm)


def fit_strain(u, xyz):
    """The uniform strain (11, 22, 33, 12, 13, 23; tensor shear) whose displacements, with a rigid
    motion, fit ``u`` at the nodes ``xyz`` best (least squares)."""
    ids = [k for k in xyz if k in u]
    rows = [(1.0,) + tuple(xyz[k]) for k in ids]
    ata = [[sum(r[i] * r[j] for r in rows) for j in range(4)] for i in range(4)]
    h = [_solve(ata, [sum(r[i] * u[k][c] for r, k in zip(rows, ids)) for i in range(4)])[1:] for c in range(3)]
    return [h[0][0], h[1][1], h[2][2], (h[0][1] + h[1][0]) / 2, (h[0][2] + h[2][0]) / 2, (h[1][2] + h[2][1]) / 2]


def dp_bar_deck(typ, ori):
    """A 4 x 1 x 1 bar of *Deformation Plasticity steel (four C3D8 or C3D20R), clamped at x = 0,
    pulled, bent and sheared at its tip past yield (NLGEOM, as ccx runs that law anyway), on no
    orientation, TURNED_AB, a cylindrical system or a spherical one centred at the bar's
    clamped corner (``ori`` "none", "turned", "cylindrical", "spherical")."""
    quad = typ == "C3D20R"
    ids: dict = {}

    def nid(p):                                        # p in half units
        return ids.setdefault(p, len(ids) + 1)
    elems = []
    for i in range(0, 8, 2):
        c = [(i, 0, 0), (i + 2, 0, 0), (i + 2, 2, 0), (i, 2, 0), (i, 0, 2), (i + 2, 0, 2), (i + 2, 2, 2), (i, 2, 2)]
        mid = [tuple((p + q) // 2 for p, q in zip(c[x], c[y])) for x, y in
               ((0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4), (0, 4), (1, 5), (2, 6), (3, 7))]
        elems.append([nid(p) for p in c + (mid if quad else [])])
    lines = ["*Heading", f"Deformation plasticity bar, orientation: {ori}", "*Node, nset=ALL"]
    lines += [f"{n}, " + ", ".join(f"{x / 2:.12g}" for x in p) for p, n in ids.items()]
    lines += [f"*Element, type={typ}, elset=BAR"]
    for e, conn in enumerate(elems, 1):
        lines += [f"{e}, " + ", ".join(map(str, conn[:15])) + ("," if len(conn) > 15 else "")]
        lines += [", ".join(map(str, conn[15:]))] if len(conn) > 15 else []
    clamp = [n for p, n in ids.items() if p[0] == 0]
    tip = [n for p, n in ids.items() if p[0] == 8]
    lines += ["*Nset, nset=CLAMP"] + _ids(clamp) + ["*Nset, nset=TIP"] + _ids(tip)
    lines += {"none": [], "turned": ["*Orientation, name=O", ", ".join(f"{x:g}" for x in TURNED_AB[0] + TURNED_AB[1])],
              "cylindrical": ["*Orientation, name=O, system=CYLINDRICAL", "-3., -2., -1., -3., 5., 2."],
              "spherical": ["*Orientation, name=O, system=SPHERICAL", "0., 0., 0., 0., 0., 1."]}[ori]
    lines += ["*Material, name=STEEL", "*Deformation Plasticity", "210000., 0.3, 250., 5., 0.5",
              "*Solid Section, elset=BAR, material=STEEL" + ("" if ori == "none" else ", orientation=O"),
              "*Boundary", "CLAMP, 1, 3", "*Step, nlgeom, inc=200", "*Static", "0.05, 1., 1e-6, 0.1", "*Cload"]
    lines += [f"{n}, {d}, {f / len(tip):.9g}" for n in tip for d, f in ((1, 280.0), (2, 12.0), (3, 6.0))]
    lines += ["*Node Print, nset=ALL", "U", "*End Step"]
    return "\n".join(lines) + "\n"


def dp_cube_deck(step, p=500.0):
    """A free unit C3D8 cube of the *Deformation Plasticity steel of dp_bar_deck on rollers at
    x = 0, pulled by four equal tip forces (nominal stress ``p``) in an Abaqus step headed by
    ``step`` ("*Step": small strain by default)."""
    lines = ["*Heading", "Deformation plasticity cube in a small-strain step", "*Node, nset=ALL"]
    lines += [f"{k}, {x}., {y}., {z}." for k, (x, y, z) in enumerate(
        ((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)), 1)]
    lines += ["*Element, type=C3D8, elset=CUBE", "1, 1, 2, 3, 4, 5, 6, 7, 8", "*Nset, nset=X0",
              "1, 4, 5, 8", "*Material, name=STEEL", "*Deformation Plasticity", "210000., 0.3, 250., 5., 0.5",
              "*Solid Section, elset=CUBE, material=STEEL", "*Boundary", "X0, 1, 1", "1, 2, 3", "5, 2, 2",
              "4, 3, 3", step, "*Static", "0.1, 1.", "*Cload"]
    lines += [f"{n}, 1, {p / 4:.9g}" for n in (2, 3, 6, 7)]
    lines += ["*Node Print, nset=ALL", "U", "*End Step"]
    return "\n".join(lines) + "\n"


def dp_uniaxial_strains(p, e=210000.0, nu=0.3, s0=250.0, n=5.0, alpha=0.5):
    """The strain of a free bar under nominal stress ``p``: (ccx 2.23's *Deformation Plasticity,
    Ramberg-Osgood in the logarithmic strain and the Cauchy stress p / lateral stretch^2;
    Abaqus' small-strain law, Ramberg-Osgood in the small strain and p)."""
    def plastic(s):
        return alpha * (abs(s) / s0) ** (n - 1)
    s = p
    for _ in range(100):
        s = p * math.exp(2 * (nu + 0.5 * plastic(s)) * s / e)
    return math.expm1(s / e * (1 + plastic(s))), p / e * (1 + plastic(p))


def distribution_panel_deck(plane="XY", tilt=0.0, nx=8, ny=2):
    """A variable-angle-tow S8R composite strip (40 x 10, 0.25-thick layers [0 / 45 / -45 / 90]
    on a per-element *DISTRIBUTION orientation whose fibre angle runs from 0 to 70 degrees
    along it, rotation line "3, 0."), clamped at x = 0 and loaded at the tip, in the x-y plane
    or turned into the x-z / y-z plane (plate_place).  ``tilt`` (degrees) turns each line's b
    out of the plate about a: Abaqus projects the orientation's axis 1 (a, in the plate) and
    turns each layer about the normal, so the strip moves alike whatever the tilt and plane;
    ccx 2.23 would turn the 45-degree layers about the tilted axis 3."""
    place = plate_place(plane)
    gx, gy = 2 * nx + 1, 2 * ny + 1
    nid = lambda i, j: 1 + i + gx * j      # noqa: E731
    used = {(i, j) for j in range(gy) for i in range(gx) if i % 2 == 0 or j % 2 == 0}
    lines = ["*Heading", f"Variable-angle-tow S8R strip in the {plane} plane, its distribution's b "
             f"turned {tilt:g} deg out of the plate", "*Node"]
    for j in range(gy):
        for i in range(gx):
            if (i, j) in used:
                lines.append(f"{nid(i, j)}, " + ", ".join(f"{c:.12g}" for c in place((40.0 * i / (gx - 1),
                                                                                      10.0 * j / (gy - 1), 0.0))))
    lines.append("*Element, type=S8R, elset=PANEL")
    dist = ["*Distribution, name=VAT, location=ELEMENT, table=VAT_T"]
    ct, st = math.cos(math.radians(tilt)), math.sin(math.radians(tilt))
    for b in range(ny):
        for a in range(nx):
            i, j, e = 2 * a, 2 * b, 1 + a + nx * b
            lines.append(f"{e}, " + ", ".join(str(nid(*p)) for p in (
                (i, j), (i + 2, j), (i + 2, j + 2), (i, j + 2), (i + 1, j), (i + 2, j + 1), (i + 1, j + 2), (i, j + 1))))
            th = math.radians(70.0 * (a + 0.5) / nx + 5.0 * b)
            axes = place((math.cos(th), math.sin(th), 0.0)) + place((-math.sin(th) * ct, math.cos(th) * ct, st))
            row = ", ".join(f"{c:.12g}" for c in axes)
            dist += [f", {row}"] if e == 1 else []
            dist.append(f"{e}, {row}")
    lines += ["*Nset, nset=FIX"] + _ids([nid(0, j) for j in range(gy)])
    lines += ["*Nset, nset=TIP"] + _ids([nid(gx - 1, j) for j in range(gy)])
    lines += ["*Nset, nset=NALL"] + _ids(sorted(nid(*p) for p in used))
    force = place((30.0, 10.0, 0.5))
    lines += dist + ["*Distribution Table, name=VAT_T", "coord3D, coord3D",
                     "*Orientation, name=ORI-VAT", "VAT", "3, 0.",
                     "*Material, name=CFRP", "*Elastic, type=ENGINEERING CONSTANTS",
                     "140000., 9000., 9000., 0.3, 0.3, 0.45, 4600., 4600.", "3100.",
                     "*Shell Section, elset=PANEL, composite, orientation=ORI-VAT"]
    lines += [f"0.25, 3, CFRP, {ang}" for ang in ("0.", "45.", "-45.", "90.")]
    lines += ["*Step", "*Static", "*Boundary", "FIX, ENCASTRE", "*Cload"]
    lines += [f"TIP, {d}, {force[d - 1]:.12g}" for d in (1, 2, 3)]
    lines += ["*Node print, nset=NALL", "U", "*End Step"]
    return "\n".join(lines) + "\n"


def dat_totals(dat_path):
    """The (fx, fy, fz) of every 'total force' block a ccx .dat file holds, in order."""
    out, lines = [], (open(dat_path, encoding="utf-8", errors="replace").read().splitlines()
                      if os.path.exists(dat_path) else [])
    for i, ln in enumerate(lines):
        if "total force" in ln:
            nxt = next((x for x in lines[i + 1:] if x.strip()), "")
            out.append(tuple(float(x) for x in nxt.split()[:3]))
    return out


def folding_strip_deck(mode, d=0.25):
    """A C-shaped strip (two arms of 20 C3D8I joined at x = 0, gap 0.2, held in its plane)
    whose top-arm tip is pushed down ``d``, folding it onto the bottom arm, with Abaqus'
    default (node-to-surface) contact: ``mode`` "self", one surface S of both inner arm faces
    and the joint's ('S,', Abaqus' self-contact), or "sym", the symmetric pairs of the two arm
    faces (Abaqus' self-contact acts "similar to symmetric master-slave contact pairs")."""
    nx, ys = 20, [0.0, 1.0, 1.2, 2.2]
    cells = [(i, 0) for i in range(nx)] + [(0, 1)] + [(i, 2) for i in range(nx)]
    nodes = {}

    def nid(i, j, k):
        return nodes.setdefault((i, j, k), len(nodes) + 1)
    conn = [[nid(i, j, 0), nid(i + 1, j, 0), nid(i + 1, j + 1, 0), nid(i, j + 1, 0),
             nid(i, j, 1), nid(i + 1, j, 1), nid(i + 1, j + 1, 1), nid(i, j + 1, 1)] for i, j in cells]
    eid = {c: e for e, c in enumerate(cells, 1)}

    def nset(name, ids):
        ids = sorted(ids)
        return f"*Nset, nset={name}\n" + "\n".join(", ".join(map(str, ids[i:i + 16]))
                                                    for i in range(0, len(ids), 16)) + "\n"
    bot = "".join(f"{eid[(i, 0)]}, S5\n" for i in range(1, nx))
    top = "".join(f"{eid[(i, 2)]}, S3\n" for i in range(1, nx))
    surf = (f"*Surface, name=S\n{bot}{eid[(0, 1)]}, S4\n{top}*Contact Pair, interaction=I\nS,\n"
            if mode == "self" else
            f"*Surface, name=SA\n{top}*Surface, name=SB\n{bot}*Contact Pair, interaction=I\nSA, SB\n"
            f"*Contact Pair, interaction=I\nSB, SA\n")
    return ("*Node\n" + "".join(f"{n}, {0.5 * i}, {ys[j]}, {float(k)}\n"
                                for (i, j, k), n in sorted(nodes.items(), key=lambda t: t[1])) +
            "*Element, type=C3D8I, elset=E\n" +
            "".join(f"{e}, {', '.join(map(str, c))}\n" for e, c in enumerate(conn, 1)) +
            "*Solid Section, elset=E, material=M\n*Material, name=M\n*Elastic\n1000., 0.\n" +
            nset("FIX", [n for (i, j, k), n in nodes.items() if j == 0]) +
            nset("TIP", [n for (i, j, k), n in nodes.items() if i == nx and j in (2, 3)]) +
            nset("NALL", nodes.values()) +
            "*Surface Interaction, name=I\n*Surface Behavior, pressure-overclosure=LINEAR\n1.e5\n" +
            surf + "*Boundary\nFIX, 1, 3\nNALL, 3, 3\n*Step, nlgeom, inc=1000\n*Static\n"
            f"0.05, 1., 1.e-6, 0.05\n*Boundary\nTIP, 2, 2, {-d}\n"
            "*Node Print, nset=TIP, totals=only\nRF\n*End Step\n")


def clearance_deck(roles):
    """Two unit cubes (C3D8) 0.01 apart in z, the lower one held at its base, the upper one's top
    pushed down 0.005, with a surface-to-surface pair (upper base on lower top) and a *CLEARANCE
    of 0 written with ``roles`` = (slave, master) parameter names, or none (``roles`` None):
    contact from the start with the clearance, none without (the gap stays open)."""
    pts = [(0, 0), (1, 0), (1, 1), (0, 1)]
    nodes = "".join(f"{n}, {x}., {y}., {z}\n" for n, (z, (x, y)) in enumerate(
        ((z, p) for z in (0., 1., 1.01, 2.01) for p in pts), 1))
    clr = f"*Clearance, {roles[0]}=UP, {roles[1]}=LOW, value=0.\n" if roles else ""
    return ("*Node\n" + nodes + "*Element, type=C3D8, elset=E\n1, 1,2,3,4,5,6,7,8\n"
            "2, 9,10,11,12,13,14,15,16\n*Solid Section, elset=E, material=M\n*Material, name=M\n"
            "*Elastic\n1000., 0.\n*Nset, nset=BASE\n1, 2, 3, 4\n*Nset, nset=LTOP\n5, 6, 7, 8\n"
            "*Nset, nset=UTOP\n13, 14, 15, 16\n*Surface, name=LOW\n1, S2\n*Surface, name=UP\n2, S1\n"
            "*Surface Interaction, name=I\n*Surface Behavior, pressure-overclosure=LINEAR\n1.e4\n"
            "*Contact Pair, interaction=I, type=SURFACE TO SURFACE\nUP, LOW\n" + clr +
            "*Boundary\nBASE, 1, 3\nUTOP, 1, 2\n*Step\n*Static\n*Boundary\nUTOP, 3, 3, -0.005\n"
            "*Node Print, nset=UTOP, totals=only\nRF\n*Node Print, nset=LTOP\nU\n*End Step\n")


def follower_turning_deck(form, steps=6, step_deg=15.0):
    """A unit cube (C3D8, ``form`` "3d": *DSLOAD TRVEC on its face x = 1) or square (CPE4,
    "2d": element-based *DLOAD TRVEC2 on its edge x = 1) whose face x = 0 is turned about z in
    ``steps`` NLGEOM steps while a unit traction pushes into the far face: a follower load,
    so the reaction turns with the body, (cos, sin) of the angle times the current area."""
    two = form == "2d"
    xy = [(0., 0.), (1., 0.), (1., 1.), (0., 1.)]
    xyz = [p + (0.,) for p in xy] + ([] if two else [p + (1.,) for p in xy])
    left = (1, 4) if two else (1, 4, 5, 8)
    out = ["*NODE"] + [f"{i + 1}, " + ", ".join(repr(c) for c in (x[:2] if two else x))
                       for i, x in enumerate(xyz)]
    out += [f"*ELEMENT, TYPE={'CPE4' if two else 'C3D8'}, ELSET=EALL",
            ", ".join(str(i) for i in range(1, len(xyz) + 1)).join(["1, ", ""]),
            "*MATERIAL, NAME=M", "*ELASTIC", "1000., 0.3", "*SOLID SECTION, ELSET=EALL, MATERIAL=M"]
    out += ["1."] if two else ["*SURFACE, NAME=FAR", "EALL, S4"]
    out += ["*NSET, NSET=LEFT", ", ".join(map(str, left))]
    for k in range(1, steps + 1):
        th = math.radians(k * step_deg)
        out += ["*STEP, NLGEOM", "*STATIC", "1., 1.", "*BOUNDARY"]
        for n in left:
            x, y = xyz[n - 1][0], xyz[n - 1][1]
            out += [f"{n}, 1, 1, {(math.cos(th) - 1) * x - math.sin(th) * y + 0.0!r}",
                    f"{n}, 2, 2, {math.sin(th) * x + (math.cos(th) - 1) * y!r}"]
        out += [] if two else ["1, 3, 3, 0.", "4, 3, 3, 0."]
        if k == 1:
            out += ["*DLOAD", "EALL, TRVEC2, 1., -1., 0., 0."] if two else \
                   ["*DSLOAD", "FAR, TRVEC, 1., -1., 0., 0."]
        out += ["*NODE PRINT, NSET=LEFT, TOTALS=ONLY", "RF", "*NODE PRINT", "U", "*END STEP"]
    return "\n".join(out) + "\n"


# --- decks for the checks of fixes found in the 19 Oct 2026 code review ------------------------

CUBE8 = ("*NODE\n1, 0., 0., 0.\n2, 1., 0., 0.\n3, 1., 1., 0.\n4, 0., 1., 0.\n5, 0., 0., 1.\n"
         "6, 1., 0., 1.\n7, 1., 1., 1.\n8, 0., 1., 1.\n*ELEMENT, TYPE=C3D8, ELSET=EALL\n"
         "1, 1, 2, 3, 4, 5, 6, 7, 8\n*NSET, NSET=TOP\n5, 6, 7, 8\n*NSET, NSET=BOT\n1, 2, 3, 4\n"
         "*SOLID SECTION, ELSET=EALL, MATERIAL=M\n")
# a cube held at its bottom without restraining its lateral contraction
CUBE8_HELD = "*BOUNDARY\n1, 1, 3\n2, 2, 3\n3, 3, 3\n4, 1, 1\n4, 3, 3\n"


def planar_coupled_tip_deck(coupled=True, n=10):
    """A B21 cantilever (length 1000, RECT 20 x 40) loaded at its tip, or through a reference
    node kinematically coupled (*COUPLING, *KINEMATIC) to the tip node."""
    tip = n + 1
    lines = ["*NODE"] + [f"{i + 1}, {100.0 * i:g}, 0." for i in range(n + 1)]
    lines += ["*ELEMENT, TYPE=B21, ELSET=BEAM"] + [f"{i + 1}, {i + 1}, {i + 2}" for i in range(n)]
    lines += ["*BEAM SECTION, ELSET=BEAM, MATERIAL=M, SECTION=RECT", "20., 40.", "*MATERIAL, NAME=M",
              "*ELASTIC", "210000., 0.3"]
    if coupled:
        lines += ["*NODE", f"{tip + 1}, {100.0 * n:g}, 0.", "*NSET, NSET=TIP", str(tip),
                  "*SURFACE, NAME=TIPS, TYPE=NODE", "TIP", f"*COUPLING, REF NODE={tip + 1}, "
                  "SURFACE=TIPS, CONSTRAINT NAME=C", "*KINEMATIC"]
    lines += ["*STEP", "*STATIC", "*BOUNDARY", "1, ENCASTRE", "*CLOAD",
              f"{tip + 1 if coupled else tip}, 2, -100.", "*NODE PRINT", "U", "*END STEP"]
    return "\n".join(lines) + "\n"


def coupled_velocity_deck():
    """A column of two C3D8 held at its bottom, its top face a *RIGID BODY (TIE NSET) on node
    100: one *BOUNDARY, TYPE=VELOCITY moves node 100 at 2 along x (rotations held), a second
    gives the top nodes the same velocity — a BC the rigid constraint implies (ccx stops on it).
    A rigid body, not a kinematic coupling: in a *DYNAMIC step ccx 2.23 sets up no equations
    for a model with *COUPLING, *KINEMATIC (every free DOF stays at 0, and its Windows build
    stops in u_calloc on the size of the empty matrix).  The middle nodes MID are free."""
    return ("*NODE\n1, 0., 0., 0.\n2, 1., 0., 0.\n3, 1., 1., 0.\n4, 0., 1., 0.\n5, 0., 0., 1.\n"
            "6, 1., 0., 1.\n7, 1., 1., 1.\n8, 0., 1., 1.\n9, 0., 0., 2.\n10, 1., 0., 2.\n"
            "11, 1., 1., 2.\n12, 0., 1., 2.\n100, 0.5, 0.5, 2.\n*ELEMENT, TYPE=C3D8, ELSET=EALL\n"
            "1, 1, 2, 3, 4, 5, 6, 7, 8\n2, 5, 6, 7, 8, 9, 10, 11, 12\n*NSET, NSET=TOP\n9, 10, 11, 12\n"
            "*NSET, NSET=MID\n5, 6, 7, 8\n*NSET, NSET=BOT\n1, 2, 3, 4\n"
            "*SOLID SECTION, ELSET=EALL, MATERIAL=M\n*MATERIAL, NAME=M\n*ELASTIC\n1000., 0.3\n"
            "*DENSITY\n1e-3\n*RIGID BODY, REF NODE=100, TIE NSET=TOP\n*STEP\n*DYNAMIC\n0.01, 1.\n"
            "*BOUNDARY\nBOT, 1, 3\n*BOUNDARY, TYPE=VELOCITY\n100, 1, 1, 2.\n100, 4, 6, 0.\n"
            "*BOUNDARY, TYPE=VELOCITY\nTOP, 1, 1, 2.\n*NODE PRINT, NSET=TOP\nU\n"
            "*NODE PRINT, NSET=MID\nU\n*END STEP\n")


def amplitude_close_times_deck(definition="EQUALLY SPACED"):
    """A C3D8 cube (E 1e6) pulled by 1 through an amplitude that rises from total time 100 to
    100.0002 — EQUALLY SPACED points 1e-4 apart, or a SMOOTH STEP — over a step of 100 and
    four fixed increments of an NLGEOM step (ccx runs a linear static step in one increment)."""
    amp = ("*AMPLITUDE, NAME=A, TIME=TOTAL TIME, DEFINITION=EQUALLY SPACED, FIXED INTERVAL=0.0001, "
           "BEGIN=100.\n0., 0.5, 1.\n" if definition == "EQUALLY SPACED" else
           "*AMPLITUDE, NAME=A, TIME=TOTAL TIME, DEFINITION=SMOOTH STEP\n100., 0., 100.0002, 1.\n")
    return (CUBE8 + "*MATERIAL, NAME=M\n*ELASTIC\n1e6, 0.\n" + amp + CUBE8_HELD +
            "*STEP\n*STATIC\n100., 100.\n*CLOAD, AMPLITUDE=A\nTOP, 3, 0.25\n*END STEP\n"
            "*STEP, NLGEOM\n*STATIC, DIRECT\n0.00005, 0.0002\n*NODE PRINT, NSET=TOP\nU\n*END STEP\n")


def kinematic_dynamic_deck(dofs="1, 3", nlgeom=False, proc="dynamic", member_bc=False, ori=False,
                           legacy=False, part=False):
    """A column of two C3D8 held at its bottom, its top face TOP kinematically coupled (DOFs
    ``dofs``) to node 100, which moves 0.4 along x and turns 0.3 about x and 0.2 about z over
    a slow step: ``proc`` dynamic, explicit or static (ccx solves its own coupling there, so
    that deck also runs as it is: the static limit).  The middle nodes MID are free.
    ``member_bc``: a *BOUNDARY on DOF 3 of coupled node 9 too, which Abaqus does not apply
    (the coupling eliminates that DOF).  ``ori``: the DOFs in the axes of an *ORIENTATION,
    e1 = (0.8, 0, 0.6), e2 = y; ``legacy``: the coupling as a *KINEMATIC COUPLING card;
    ``part``: the model a part instanced twice (I2 3 along x, its nodes numbered 100 above
    I1's)."""
    step = {"dynamic": "*DYNAMIC\n0.01, 1.\n", "explicit": "*DYNAMIC, EXPLICIT\n, 1.\n",
            "static": "*STATIC\n0.05, 1.\n"}[proc]
    o = ", ORIENTATION=OR1" if ori else ""
    cpl = (f"*KINEMATIC COUPLING, REF NODE=100{o}\nTOP, {dofs}\n" if legacy else
           "*SURFACE, TYPE=NODE, NAME=ST\nTOP\n*COUPLING, CONSTRAINT NAME=C, "
           f"REF NODE=100, SURFACE=ST{o}\n*KINEMATIC\n{dofs}\n")
    model = ("*NODE\n1, 0., 0., 0.\n2, 1., 0., 0.\n3, 1., 1., 0.\n4, 0., 1., 0.\n5, 0., 0., 1.\n"
             "6, 1., 0., 1.\n7, 1., 1., 1.\n8, 0., 1., 1.\n9, 0., 0., 2.\n10, 1., 0., 2.\n"
             "11, 1., 1., 2.\n12, 0., 1., 2.\n100, 0.5, 0.5, 2.\n*ELEMENT, TYPE=C3D8, ELSET=EALL\n"
             "1, 1, 2, 3, 4, 5, 6, 7, 8\n2, 5, 6, 7, 8, 9, 10, 11, 12\n*NSET, NSET=TOP\n9, 10, 11, 12\n"
             "*NSET, NSET=MID\n5, 6, 7, 8\n*NSET, NSET=BOT\n1, 2, 3, 4\n"
             "*SOLID SECTION, ELSET=EALL, MATERIAL=M\n")
    mat = "*MATERIAL, NAME=M\n*ELASTIC\n1000., 0.3\n*DENSITY\n1e-3\n"
    ori_card = "*ORIENTATION, NAME=OR1\n0.8, 0., 0.6, 0., 1., 0.\n" if ori else ""
    pre, refs = (["I1.", "I2."], ["R1", "R2"]) if part else ([""], ["100"])
    if part:
        model = ("*PART, NAME=P\n" + model + ori_card + cpl + "*END PART\n*ASSEMBLY, NAME=A\n"
                 "*INSTANCE, NAME=I1, PART=P\n*END INSTANCE\n*INSTANCE, NAME=I2, PART=P\n3., 0., 0.\n"
                 "*END INSTANCE\n*NSET, NSET=R1, INSTANCE=I1\n100\n*NSET, NSET=R2, INSTANCE=I2\n100\n"
                 "*END ASSEMBLY\n" + mat)
    else:
        model += mat + ori_card + cpl
    return (model + f"*AMPLITUDE, NAME=R\n0., 0., 1., 1.\n*STEP{', NLGEOM' if nlgeom else ''}, "
            f"INC=1000\n{step}*BOUNDARY\n" + "".join(f"{p}BOT, 1, 3\n" for p in pre) +
            ("9, 3, 3\n" if member_bc else "") +
            "*BOUNDARY, AMPLITUDE=R\n" + "".join(f"{r}, 1, 1, 0.4\n{r}, 2, 3\n{r}, 4, 4, 0.3\n"
                                                 f"{r}, 5, 5\n{r}, 6, 6, 0.2\n" for r in refs) +
            "".join(f"*NODE PRINT, NSET={p}MID\nU\n*NODE PRINT, NSET={p}TOP\nU\n" for p in pre) +
            "*END STEP\n")


def influence_radius_deck(surface="element", proc="static", nodes=None, ref=(2., 2., 1.5), radius="0.8"):
    """A 4 x 4 x 1 block of C3D8 held at its bottom (top face z = 1: nodes 26-50 on a grid of 1),
    its top face coupled (*COUPLING, *KINEMATIC) to node 100 above its centre at (2, 2, 1.5)
    with INFLUENCE RADIUS=0.8, which holds the centre node 38 only: Abaqus couples that node of
    the node surface (``surface`` 'node'), and every node of the four element faces around it
    ('element': INFLUENCE_KEPT).  Node 100 moves -0.1 along z and turns 0.05 about x over a slow
    ``proc`` step (static or dynamic).  ``nodes``: the coupling on a node surface of these nodes,
    without the radius (DOFs 1-3 written out: ccx's empty *KINEMATIC couples nothing).  ``ref``,
    ``radius``: node 100's position and the radius."""
    nid, lines = {}, ["*NODE"]
    for z in (0, 1):
        for j in range(5):
            for i in range(5):
                nid[(i, j, z)] = len(nid) + 1
                lines.append(f"{nid[(i, j, z)]}, {i}., {j}., {z}.")
    lines += ["100, " + ", ".join(f"{x:g}." if x == int(x) else f"{x:g}" for x in ref),
              "*ELEMENT, TYPE=C3D8, ELSET=EALL"]
    for j in range(4):
        for i in range(4):
            lines.append(f"{1 + i + 4 * j}, " + ", ".join(str(nid[(a, b, z)]) for z in (0, 1) for a, b in
                                                         ((i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1))))
    lines += ["*NSET, NSET=BOT, GENERATE", "1, 25, 1", "*NSET, NSET=TOPN, GENERATE", "26, 50, 1",
              "*NSET, NSET=NALL, GENERATE", "1, 50, 1", "*SOLID SECTION, ELSET=EALL, MATERIAL=M",
              "*MATERIAL, NAME=M", "*ELASTIC", "1000., 0.3", "*DENSITY", "1e-3"]
    if nodes:
        lines += ["*SURFACE, NAME=ST, TYPE=NODE"] + [str(n) for n in nodes] + [
                  "*COUPLING, CONSTRAINT NAME=C, REF NODE=100, SURFACE=ST", "*KINEMATIC", "1, 3"]
    else:
        lines += ["*SURFACE, NAME=ST", "EALL, S2"] if surface == "element" else \
            ["*SURFACE, NAME=ST, TYPE=NODE", "TOPN"]
        lines += [f"*COUPLING, CONSTRAINT NAME=C, REF NODE=100, SURFACE=ST, INFLUENCE RADIUS={radius}",
                  "*KINEMATIC"]
    step = {"static": "*STATIC\n0.1, 1.", "dynamic": "*DYNAMIC\n0.01, 1."}[proc]
    lines += ["*AMPLITUDE, NAME=R", "0., 0., 1., 1.", "*STEP, INC=1000", step, "*BOUNDARY",
              "BOT, 1, 3", "*BOUNDARY, AMPLITUDE=R", "100, 1, 2", "100, 3, 3, -0.1", "100, 4, 4, 0.05",
              "100, 5, 6", "*NODE PRINT, NSET=NALL", "U", "*END STEP"]
    return "\n".join(lines) + "\n"


INFLUENCE_KEPT = {"element": (32, 33, 34, 37, 38, 39, 42, 43, 44), "node": (38,)}
# the nodes each reference node of several_refs_deck couples
SEVERAL_KEPT = {100: (26, 27, 31, 32), 101: (44, 45, 49, 50)}


def several_refs_deck(proc="static", twin=False):
    """influence_radius_deck's block, its top face (a node surface) coupled to the two
    reference nodes of one node set, 100 at (0.5, 0.5, 1.5) and 101 at (3.5, 3.5, 1.5), with
    INFLUENCE RADIUS=0.9: Abaqus couples each to the four nodes around it (SEVERAL_KEPT).  Over
    a slow ``proc`` step 100 moves 0.1 along x and turns 0.05 about y, 101 moves -0.1 along z
    and turns 0.05 about x.  ``twin``: a coupling of each reference node on a node surface of
    its nodes, without the radius."""
    deck = influence_radius_deck("node", proc, ref=(0.5, 0.5, 1.5), radius="0.9")
    deck = deck.replace("100, 0.5, 0.5, 1.5\n", "100, 0.5, 0.5, 1.5\n101, 3.5, 3.5, 1.5\n")
    cpl = "*COUPLING, CONSTRAINT NAME=C, REF NODE=100, SURFACE=ST, INFLUENCE RADIUS=0.9\n*KINEMATIC\n"
    new = "".join(f"*SURFACE, NAME=S{r}, TYPE=NODE\n" + "\n".join(map(str, ns)) +
                  f"\n*COUPLING, CONSTRAINT NAME=C{r}, REF NODE={r}, SURFACE=S{r}\n*KINEMATIC\n1, 3\n"
                  for r, ns in SEVERAL_KEPT.items()) if twin else \
        "*NSET, NSET=RS\n100, 101\n" + cpl.replace("REF NODE=100", "REF NODE=RS")
    bcs = "100, 1, 2\n100, 3, 3, -0.1\n100, 4, 4, 0.05\n100, 5, 6\n"
    return deck.replace(cpl, new).replace(bcs, "100, 1, 1, 0.1\n100, 2, 4\n100, 5, 5, 0.05\n100, 6, 6\n"
                                               + bcs.replace("100", "101"))


def oriented_coupling_deck(deg=60., dofs="1, 1", bcs=(), proc="static", ori=True, extra=""):
    """A 2 x 2 x 1 block of C3D8 (node 1 + i + 3 j + 9 z at (i, j, z)) held at its bottom, its
    top face (nodes 10-18) kinematically coupled in DOFs ``dofs`` of *ORIENTATION OR1, turned
    ``deg`` degrees about z, to node 100 at (1, 1, 1.5), which moves (0.01, 0.02, 0) over a slow
    ``proc`` step (static or dynamic), its rotations held.  ``bcs``: *BOUNDARY lines on the
    members (ramped alike); ``ori`` False: coupled in the global DOFs ``dofs``; ``extra``:
    cards after the coupling."""
    lines = ["*NODE"] + [f"{1 + i + 3 * j + 9 * z}, {i}., {j}., {z}." for z in (0, 1) for j in range(3)
                         for i in range(3)] + ["100, 1., 1., 1.5", "*ELEMENT, TYPE=C3D8, ELSET=EALL"]
    lines += [f"{1 + i + 2 * j}, " + ", ".join(str(1 + a + 3 * b + 9 * z) for z in (0, 1) for a, b in
                                              ((i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)))
              for j in range(2) for i in range(2)]
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    lines += ["*NSET, NSET=BOT, GENERATE", "1, 9, 1", "*NSET, NSET=TOPN, GENERATE", "10, 18, 1",
              "*NSET, NSET=NALL", ", ".join(map(str, range(1, 10))), ", ".join(map(str, range(10, 19))) + ", 100",
              "*SOLID SECTION, ELSET=EALL, MATERIAL=M", "*MATERIAL, NAME=M", "*ELASTIC", "1000., 0.3",
              "*DENSITY", "1e-3", "*SURFACE, NAME=ST, TYPE=NODE", "TOPN"]
    if ori:
        lines += ["*ORIENTATION, NAME=OR1", f"{c:.15g}, {s:.15g}, 0., {-s:.15g}, {c:.15g}, 0."]
    lines += ["*COUPLING, CONSTRAINT NAME=C, REF NODE=100, SURFACE=ST" + (", ORIENTATION=OR1" if ori else ""),
              "*KINEMATIC", dofs] + ([extra] if extra else [])
    step = {"static": "*STATIC\n0.1, 1.", "dynamic": "*DYNAMIC\n0.01, 1."}[proc]
    lines += ["*AMPLITUDE, NAME=R", "0., 0., 1., 1.", "*STEP, INC=1000", step, "*BOUNDARY", "BOT, 1, 3",
              "100, 3, 6", "*BOUNDARY, AMPLITUDE=R", "100, 1, 1, 0.01", "100, 2, 2, 0.02"] + list(bcs) + \
        ["*NODE PRINT, NSET=NALL", "U", "*END STEP"]
    return "\n".join(lines) + "\n"
# the axes of a coupling orientation: e1 = (0.6, 0.64, 0.48), e2 = (0, 0.6, -0.8), e3 = e1 x e2
ROT_FRAME = ((0.6, 0.64, 0.48), (0., 0.6, -0.8), (-0.8, 0.48, 0.36))


def coupled_rotations_deck(proc="static", legacy=False, turned=False):
    """A strip of four S4 (x 0..4, y 0..1) clamped at x = 0, its tip edge (nodes 5, 15)
    kinematically coupled to node 100 at (4.5, 0.5, 0) in DOFs 1-5 of *ORIENTATION OR1
    (ROT_FRAME): rotations about its axes 1 and 2 coupled, about 3 free.  Node 100 moves
    (0.02, 0, 0.1) and turns (0.05, -0.04, 0.03) over a slow ``proc`` step (static or dynamic),
    a smooth step.
    ``legacy``: a *KINEMATIC COUPLING card; ``turned``: the model turned into the orientation's
    axes (x' = R x, R's rows ROT_FRAME), coupled in global DOFs 1-5, which are those axes."""
    R = ROT_FRAME if turned else ((1., 0., 0.), (0., 1., 0.), (0., 0., 1.))

    def rot(v):
        return ", ".join(f"{sum(R[i][k] * v[k] for k in range(3)):.15g}" for i in range(3))
    nodes = {n: (float(i), float(y), 0.) for i in range(5) for n, y in ((1 + i, 0), (11 + i, 1))}
    lines = ["*NODE"] + [f"{n}, {rot(x)}" for n, x in sorted(nodes.items())] + ["100, " + rot((4.5, 0.5, 0.))]
    lines += ["*ELEMENT, TYPE=S4, ELSET=EALL"] + [f"{1 + i}, {1 + i}, {2 + i}, {12 + i}, {11 + i}" for i in range(4)]
    lines += ["*NSET, NSET=NALL", ", ".join(map(str, sorted(nodes))), "*NSET, NSET=TIP", "5, 15",
              "*SHELL SECTION, ELSET=EALL, MATERIAL=M", "0.1", "*MATERIAL, NAME=M", "*ELASTIC",
              "1000., 0.3", "*DENSITY", "1e-8"]
    o = "" if turned else ", ORIENTATION=OR1"
    if not turned:
        lines += ["*ORIENTATION, NAME=OR1", "0.6, 0.64, 0.48, 0., 0.6, -0.8"]
    lines += [f"*KINEMATIC COUPLING, REF NODE=100{o}", "TIP, 1, 5"] if legacy else \
        ["*SURFACE, TYPE=NODE, NAME=ST", "TIP", f"*COUPLING, CONSTRAINT NAME=C, REF NODE=100, SURFACE=ST{o}",
         "*KINEMATIC", "1, 5"]
    step = {"static": "*STATIC\n0.1, 1.", "dynamic": "*DYNAMIC\n0.01, 1."}[proc]
    u0, th = rot((0.02, 0., 0.1)).split(", "), rot((0.05, -0.04, 0.03)).split(", ")
    lines += ["*AMPLITUDE, NAME=R, DEFINITION=SMOOTH STEP", "0., 0., 1., 1.", "*STEP, INC=1000", step,
              "*BOUNDARY", "1, 1, 6",
              "11, 1, 6", "*BOUNDARY, AMPLITUDE=R"] + [f"100, {k + 1}, {k + 1}, {u0[k]}" for k in range(3)] + \
        [f"100, {k + 4}, {k + 4}, {th[k]}" for k in range(3)] + ["*NODE PRINT, NSET=NALL", "U", "*END STEP"]
    return "\n".join(lines) + "\n"


# member kind -> (reference node position, its translation, its rotation, free nodes)
RIGID_DYNAMIC = {"solid": ((0.5, 0.5, 2.), (0.4, 0., 0.), (0.3, 0., 0.2), (5, 6, 7, 8)),
                 "shell": ((4.5, 0.5, 0.), (0.025, 0., 0.1), (0.05, -0.05, 0.), (3, 13)),
                 "planar": ((5.5, 0.5, 0.), (0.05, 0.2, 0.), (0., 0., 0.1), (3, 13))}
RIGID_MESH = {"mpc": "solid", "transformed": "solid", "pin": "shell"}     # the others' own


def rigid_dynamic_deck(member="solid", proc="dynamic", before=""):
    """Members moved rigidly by node 100, which moves and turns over a slow step: the top face
    of a column of two C3D8 (``member`` 'solid': a *RIGID BODY; 'mpc': *MPC BEAM lines;
    'transformed': a *RIGID BODY on nodes with an oblique *TRANSFORM), or the tip edge of a
    strip of four S4 ('shell': a *RIGID BODY, so their rotations follow too; 'pin': its PIN
    NSET, rotations free) or CPS4 ('planar') clamped at the other end.  ``proc`` 'dynamic':
    the Abaqus deck, a linear *DYNAMIC step; 'static': the same mesh in a *STATIC step with
    the members' DOFs prescribed to the linear rigid motion u = u_100 + theta x d (shell
    rotations: theta), the answer of Abaqus' linearized rigid body (RIGID_DYNAMIC: the motion
    and the free nodes).  ``before``: steps before the dynamic one."""
    x0, t0, th, _ = RIGID_DYNAMIC[RIGID_MESH.get(member, member)]
    if member in ("solid", "mpc", "transformed"):
        nodes = {1: (0., 0., 0.), 2: (1., 0., 0.), 3: (1., 1., 0.), 4: (0., 1., 0.), 5: (0., 0., 1.),
                 6: (1., 0., 1.), 7: (1., 1., 1.), 8: (0., 1., 1.), 9: (0., 0., 2.), 10: (1., 0., 2.),
                 11: (1., 1., 2.), 12: (0., 1., 2.)}
        mesh = ("*ELEMENT, TYPE=C3D8, ELSET=EALL\n1, 1, 2, 3, 4, 5, 6, 7, 8\n2, 5, 6, 7, 8, 9, 10, 11, 12\n"
                "*NSET, NSET=FIX\n1, 2, 3, 4\n*SOLID SECTION, ELSET=EALL, MATERIAL=M\n*MATERIAL, NAME=M\n"
                "*ELASTIC\n1000., 0.3\n*DENSITY\n1e-3\n")
        fixed, tip, dofs = "FIX, 1, 3\n", (9, 10, 11, 12), (1, 2, 3)
    else:
        planar = member == "planar"
        nodes = {}
        for i in range(5):
            nodes[1 + i] = (i + 1. if planar else float(i), 0., 0.)
            nodes[11 + i] = (i + 1. if planar else float(i), 1., 0.)
        mesh = (f"*ELEMENT, TYPE={'CPS4' if planar else 'S4'}, ELSET=EALL\n"
                + "".join(f"{1 + i}, {1 + i}, {2 + i}, {12 + i}, {11 + i}\n" for i in range(4))
                + ("*SOLID SECTION, ELSET=EALL, MATERIAL=M\n1.\n" if planar else
                   "*SHELL SECTION, ELSET=EALL, MATERIAL=M\n0.1\n")
                + f"*MATERIAL, NAME=M\n*ELASTIC\n1000., 0.3\n*DENSITY\n{'1e-6' if planar else '1e-8'}\n")
        fixed = "1, 1, 2\n11, 1, 2\n" if planar else "1, 1, 6\n11, 1, 6\n"
        tip, dofs = (5, 15), ((1, 2) if planar else (1, 2, 3))
    xyz = (lambda v: v[:2]) if member == "planar" else (lambda v: v)
    deck = "*NODE\n" + "".join(f"{n}, " + ", ".join(map(str, xyz(x))) + "\n" for n, x in nodes.items())
    deck += "*NSET, NSET=NALL\n" + ", ".join(map(str, nodes)) + "\n" + mesh
    deck += "*AMPLITUDE, NAME=R, DEFINITION=SMOOTH STEP\n0., 0., 1., 1.\n" if proc == "dynamic" else ""
    if proc == "dynamic":
        deck += "*NODE\n100, " + ", ".join(map(str, xyz(x0))) + "\n*NSET, NSET=TIP\n"
        deck += ", ".join(map(str, tip)) + ("\n*MPC\nBEAM, TIP, 100\n" if member == "mpc" else
                                            f"\n*RIGID BODY, REF NODE=100, "
                                            f"{'PIN' if member == 'pin' else 'TIE'} NSET=TIP\n")
        if member == "transformed":           # (printed in global axes)
            deck += "*TRANSFORM, NSET=TIP\n0.6, 0., 0.8, 0., 1., 0.\n"
        drive = "".join(f"100, {j + 1}, {j + 1}, {t0[j]}\n" for j in range(len(dofs)))
        drive += "".join(f"100, {k}, {k}, {th[k - 4]}\n" for k in ((6,) if member == "planar" else (4, 5, 6)))
        return (deck + before + "*STEP, INC=1000\n*DYNAMIC\n0.01, 1.\n*BOUNDARY\n" + fixed
                + "*BOUNDARY, AMPLITUDE=R\n" + drive + "*NODE PRINT, NSET=NALL"
                + (", GLOBAL=YES" if member == "transformed" else "") + "\nU\n*END STEP\n")
    bcs = ""
    for m in tip:
        d = [nodes[m][i] - x0[i] for i in range(3)]
        w = (th[1] * d[2] - th[2] * d[1], th[2] * d[0] - th[0] * d[2], th[0] * d[1] - th[1] * d[0])
        bcs += "".join(f"{m}, {j}, {j}, {t0[j - 1] + w[j - 1]:.12g}\n" for j in dofs)
        if member == "shell":
            bcs += "".join(f"{m}, {k}, {k}, {th[k - 4]}\n" for k in (4, 5, 6))
    return (deck + "*STEP\n*STATIC\n*BOUNDARY\n" + fixed + bcs
            + "*NODE PRINT, NSET=NALL\nU\n*END STEP\n")


RIGID_CUBES = ("*NODE, NSET=CUBES\n" + "".join(
    f"{k + i}, {5 + (i % 4 in (1, 2))}., {float(i % 4 > 1)}, {z0 + i // 4}.\n"
    for k, z0 in ((201, 0), (301, 1)) for i in range(8)) +
    "*ELEMENT, TYPE=C3D8, ELSET=EC\n201, 201, 202, 203, 204, 205, 206, 207, 208\n"
    "301, 301, 302, 303, 304, 305, 306, 307, 308\n*SOLID SECTION, ELSET=EC, MATERIAL=M\n"
    "*ELSET, ELSET=EA\n201\n*ELSET, ELSET=EB\n301\n*SURFACE, NAME=SA\nEA, S2\n*SURFACE, NAME=SB\n"
    "EB, S1\n*SURFACE INTERACTION, NAME=SI\n*SURFACE BEHAVIOR, PRESSURE-OVERCLOSURE=LINEAR\n1e4\n"
    "*CONTACT PAIR, INTERACTION=SI\nSB, SA\n")


def rigid_nonlinear_deck(case, ref=False):
    """The rigid_dynamic_deck members driven the same way over a slow step without NLGEOM that
    ccx runs through its nonlinear solver: 'plastic', the column past yield (60, hardening to 90
    at 0.2) in a *STATIC step of fixed increments; 'kinematic', the same with its top face
    kinematically coupled; 'contact', the elastic column beside a *CONTACT PAIR of two held
    cubes; 'coupled', the column of C3D8T heated by 10 (alpha 1e-3) in a *COUPLED
    TEMPERATURE-DISPLACEMENT step; 'heat', the elastic column of C3D8T in a *STATIC step after a
    *HEAT TRANSFER step (ccx iterates it: the RIGID MPC was 7 % off); 'shell' / 'planar', the
    S4 / CPS4 strip of a material with a *PLASTIC it never reaches.  ``ref``: the same step and model with the members' DOFs
    prescribed to the linear rigid motion (shell, planar: in a linear *STATIC step, as ccx's
    own knots under prescribed rotations diverge in its nonlinear solver)."""
    member = case if case in ("shell", "planar") else "solid"
    deck = rigid_dynamic_deck(member, "static" if ref else "dynamic")
    if ref and member != "solid":
        return deck
    if member != "solid":
        deck = deck.replace("*ELASTIC\n1000., 0.3\n", "*ELASTIC\n1000., 0.3\n*PLASTIC\n1e6, 0.\n")
    elif case in ("plastic", "kinematic"):
        deck = deck.replace("*ELASTIC\n1000., 0.3\n", "*ELASTIC\n1000., 0.3\n*PLASTIC\n60., 0.\n90., 0.2\n")
    elif case == "contact":
        deck = deck.replace("*NSET, NSET=NALL", RIGID_CUBES + "*NSET, NSET=NALL").replace(
            "FIX, 1, 3\n", "FIX, 1, 3\nCUBES, 1, 3\n")
    elif case == "coupled":
        deck = deck.replace("*DENSITY\n1e-3\n", "*DENSITY\n1e-3\n*CONDUCTIVITY\n1.\n*SPECIFIC HEAT\n1.\n"
                            "*EXPANSION\n1e-3\n*INITIAL CONDITIONS, TYPE=TEMPERATURE\nNALL, 0.\n").replace(
            "FIX, 1, 3\n", "FIX, 1, 3\nNALL, 11, 11, 10.\n")
        if not ref:
            deck = deck.replace("TYPE=C3D8,", "TYPE=C3D8T,")
    elif case == "heat":
        deck = deck.replace("*DENSITY\n1e-3\n", "*DENSITY\n1e-3\n*CONDUCTIVITY\n1.\n*SPECIFIC HEAT\n1.\n"
                            "*INITIAL CONDITIONS, TYPE=TEMPERATURE\nNALL, 0.\n").replace(
            "TYPE=C3D8,", "TYPE=C3D8T,").replace("*STEP", "*STEP\n*HEAT TRANSFER, STEADY STATE\n1., 1.\n"
                                                 "*BOUNDARY\nFIX, 11, 11, 0.\n*END STEP\n*STEP", 1)
    if case == "kinematic" and not ref:
        deck = deck.replace("*RIGID BODY, REF NODE=100, TIE NSET=TIP\n", "*SURFACE, TYPE=NODE, NAME=ST\n"
                            "TIP\n*COUPLING, CONSTRAINT NAME=C1, REF NODE=100, SURFACE=ST\n*KINEMATIC\n")
    proc = {"coupled": "*COUPLED TEMPERATURE-DISPLACEMENT\n0.1, 1.\n", "plastic": "*STATIC, DIRECT\n0.1, 1.\n",
            "kinematic": "*STATIC, DIRECT\n0.1, 1.\n"}.get(case, "*STATIC\n0.1, 1.\n")
    if case in ("plastic", "kinematic"):
        deck = deck.replace("*NODE PRINT, NSET=NALL\nU\n", "*NODE PRINT, NSET=NALL\nU\n*EL PRINT, ELSET=EALL\nPEEQ\n")
    return (deck.replace("*AMPLITUDE, NAME=R, DEFINITION=SMOOTH STEP\n0., 0., 1., 1.\n", "")
            .replace("*BOUNDARY, AMPLITUDE=R\n", "*BOUNDARY\n")
            .replace("*STEP, INC=1000\n*DYNAMIC\n0.01, 1.\n", "*STEP, INC=1000\n" + proc)
            .replace("*STEP\n*STATIC\n", "*STEP, INC=1000\n" + proc))


RIGID_EXPLICIT_CUBE = {i + 1: (x, y, z) for i, (x, y, z) in enumerate(
    (x, y, z) for z in (-0.5, 0.5) for x, y in ((-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5)))}


def rigid_explicit_deck():
    """A unit C3D8 cube (density 1) as a *RIGID BODY about its centre node 9, turned 0.5 rad
    about z by a velocity BC (2.5 rad/s over 0.2 s) in a *DYNAMIC, EXPLICIT step with
    NLGEOM=NO: Abaqus/Explicit's linear rigid motion u = theta x r."""
    nodes = "".join(f"{n}, {x}, {y}, {z}\n" for n, (x, y, z) in RIGID_EXPLICIT_CUBE.items())
    return (f"*NODE\n{nodes}9, 0., 0., 0.\n*ELEMENT, TYPE=C3D8, ELSET=EALL\n1, 1, 2, 3, 4, 5, 6, 7, 8\n"
            "*NSET, NSET=ALL, GENERATE\n1, 8, 1\n*MATERIAL, NAME=M\n*ELASTIC\n1000., 0.3\n*DENSITY\n1.\n"
            "*SOLID SECTION, ELSET=EALL, MATERIAL=M\n*RIGID BODY, REF NODE=9, ELSET=EALL\n*BOUNDARY\n"
            "9, 1, 5\n*STEP, NLGEOM=NO\n*DYNAMIC, EXPLICIT\n, 0.2\n*BOUNDARY, TYPE=VELOCITY\n9, 6, 6, 2.5\n"
            "*NODE PRINT, NSET=ALL\nU\n*END STEP\n")


TRANSFORM_AXES = ((0.6, 0., 0.8), (0., 1., 0.), (-0.8, 0., 0.6))    # *TRANSFORM 0.6, 0., 0.8, 0., 1., 0.


def rigid_transformed_deck(case, twin=False):
    """rigid_dynamic_deck members driven over a *STATIC step of a material with a *PLASTIC it
    never reaches (ccx's nonlinear solver: abq2ccx writes linear rigid equations): 'ref', the
    column's *RIGID BODY on a reference node with an oblique *TRANSFORM (TRANSFORM_AXES), its
    motion given in those axes; 'some', the column's top face, with that *TRANSFORM, coupled
    in DOFs 1-2 only; 'rotation_line', the S4 strip's tip edge in a *KINEMATIC COUPLING of a
    line of DOFs 1-3 and one of 4-6.  ``twin``: the same model without the *TRANSFORM (the
    motion in global components), or with one line of DOFs 1-6."""
    member = {"ref": "solid", "some": "transformed", "rotation_line": "shell"}[case]
    deck = rigid_dynamic_deck(member).replace(
        "*ELASTIC\n1000., 0.3\n", "*ELASTIC\n1000., 0.3\n*PLASTIC\n1e6, 0.\n").replace(
        "*STEP, INC=1000\n*DYNAMIC\n0.01, 1.\n", "*STEP, INC=1000\n*STATIC\n0.1, 1.\n")
    body = "*RIGID BODY, REF NODE=100, TIE NSET=TIP\n"
    if case == "some":
        deck = deck.replace(body, "*SURFACE, TYPE=NODE, NAME=ST\nTIP\n*COUPLING, CONSTRAINT NAME=C, "
                            "REF NODE=100, SURFACE=ST\n*KINEMATIC\n1, 2\n")
        return deck.replace("*TRANSFORM, NSET=TIP\n0.6, 0., 0.8, 0., 1., 0.\n", "") if twin else deck
    if case == "rotation_line":
        return deck.replace(body, "*KINEMATIC COUPLING, REF NODE=100\n" +
                            ("TIP, 1, 6\n" if twin else "TIP, 1, 3\nTIP, 4, 6\n"))
    if twin:
        return deck
    _, t0, th, _ = RIGID_DYNAMIC["solid"]
    for base, g in ((0, t0), (3, th)):
        for k in range(3):
            loc = sum(TRANSFORM_AXES[k][i] * g[i] for i in range(3))
            deck = deck.replace(f"100, {base + k + 1}, {base + k + 1}, {g[k]}\n",
                                f"100, {base + k + 1}, {base + k + 1}, {loc:.12g}\n")
    return deck.replace(body, body + "*NSET, NSET=RP\n100\n*TRANSFORM, NSET=RP\n0.6, 0., 0.8, 0., 1., 0.\n")


def energy_steps_deck(first=None, second="dynamic"):
    """CUBE8 (E 1000, nu 0) held at its bottom and its top face in x and y: one degree of
    freedom, the top face's z, with stiffness E A / L = 1000 and the top face's consistent mass
    rho A L / 3 = 0.1, so omega = 100.  A *STATIC step pulls it by 4 x 0.25 (u0 = 1e-3), then
    ``second``: 'dynamic' lets it go for one period in 250 fixed increments (u0 cos 100 t),
    'coupled' heats it by 100 in a transient coupled temperature-displacement step (alpha 1e-5:
    2e-3 at the end, its lateral expansion held).  ``first`` 'frequency' puts a *FREQUENCY step
    before them (100 / 2 pi Hz)."""
    coupled = second == "coupled"
    last = ("*STEP\n*COUPLED TEMPERATURE-DISPLACEMENT\n0.1, 1.\n*BOUNDARY\nTOP, 11, 11, 100.\n"
            "BOT, 11, 11, 100.\n" if coupled else "*STEP, INC=1000\n*DYNAMIC, DIRECT\n"
            "2.51327412287E-4, 0.0628318530718\n*CLOAD, OP=NEW\n")
    return ((CUBE8.replace("TYPE=C3D8,", "TYPE=C3D8T,") if coupled else CUBE8) +
            "*MATERIAL, NAME=M\n*ELASTIC\n1000., 0.\n*DENSITY\n0.3\n" +
            ("*CONDUCTIVITY\n1.\n*SPECIFIC HEAT\n1.\n*EXPANSION\n1.E-5\n*INITIAL CONDITIONS, "
             "TYPE=TEMPERATURE\nTOP, 0.\nBOT, 0.\n" if coupled else "") +
            "*BOUNDARY\nBOT, 1, 3\nTOP, 1, 2\n" +
            ("*STEP\n*FREQUENCY\n1\n*END STEP\n" if first == "frequency" else "") +
            "*STEP\n*STATIC\n*CLOAD\nTOP, 3, 0.25\n*END STEP\n" + last +
            "*OUTPUT, HISTORY, FREQUENCY=1\n*NODE OUTPUT, NSET=TOP\nU\n*END STEP\n")


def elke_steps_deck(case, elke=True):
    """*EL PRINT ELKE (element kinetic energy) where ccx 2.23 segfaulted computing it (the
    converter's _el_print_stops).  'dynamic': energy_steps_deck's one-DOF cube pulled to
    u0 = 1e-3 in a static step requesting history ELKE and ELSE and the top's U, then let go for
    one period in an implicit *DYNAMIC step that carries them: kinetic energy 5e-4 sin^2 100 t,
    internal energy 5e-4 cos^2 100 t.  'buckle': buckle_gravity_deck's column with ELKE and
    ELSE printed in its *BUCKLE step (``elke``: False leaves them out), then pulled sideways."""
    if case == "buckle":
        deck = buckle_gravity_deck(preload="", static=True)
        end = deck.index("*END STEP\n", deck.index("*BUCKLE\n"))     # the *BUCKLE step's end
        return deck[:end] + ("*EL PRINT, ELSET=EALL\nELKE, ELSE\n" if elke else "") + deck[end:]
    return (CUBE8 + "*MATERIAL, NAME=M\n*ELASTIC\n1000., 0.\n*DENSITY\n0.3\n*BOUNDARY\nBOT, 1, 3\n"
            "TOP, 1, 2\n*STEP\n*STATIC\n*CLOAD\nTOP, 3, 0.25\n*OUTPUT, HISTORY, FREQUENCY=1\n*NODE "
            "OUTPUT, NSET=TOP\nU\n*ELEMENT OUTPUT, ELSET=EALL\nELKE, ELSE\n*END STEP\n*STEP, INC=1000\n"
            "*DYNAMIC, DIRECT\n2.51327412287E-4, 0.0628318530718\n*CLOAD, OP=NEW\n*END STEP\n")


def elke_frequency_deck(last="dynamic"):
    """energy_steps_deck's one-DOF cube (k 1000, m 0.1, omega 100) loaded by 4 x 0.25 in an
    implicit *DYNAMIC step of half a period that requests history ELKE and the top's U (it swings
    to 2 u0 = 2e-3 and stops), then a *FREQUENCY step (100 / 2 pi Hz), then ``last``: 'dynamic',
    let go for half a period in a *DYNAMIC step that carries the requests (2e-3 cos 100 t,
    kinetic energy 2e-3 sin^2 100 t); 'static', a *STATIC step under the load with its own
    *EL PRINT ELKE (u0 = 1e-3), which ccx runs linearly after the *FREQUENCY step."""
    half = "*DYNAMIC, DIRECT\n2.51327412287E-4, 0.0314159265359\n"
    end = ("*STEP, INC=1000\n" + half + "*CLOAD, OP=NEW\n*END STEP\n" if last == "dynamic" else
           "*STEP\n*STATIC\n*EL PRINT, ELSET=EALL\nELKE\n*END STEP\n")
    return (CUBE8 + "*MATERIAL, NAME=M\n*ELASTIC\n1000., 0.\n*DENSITY\n0.3\n*BOUNDARY\nBOT, 1, 3\n"
            "TOP, 1, 2\n*STEP, INC=1000\n" + half + "*CLOAD\nTOP, 3, 0.25\n*OUTPUT, HISTORY, "
            "FREQUENCY=1\n*NODE OUTPUT, NSET=TOP\nU\n*ELEMENT OUTPUT, ELSET=EALL\nELKE\n*END STEP\n"
            "*STEP\n*FREQUENCY\n1\n*END STEP\n" + end)


def contact_print_deck():
    """rigid_punch_deck's block pressed by 0.01 with Abaqus' *CONTACT PRINT CFN (and CPRESS, which
    ccx has not) for every contact pair: ccx needs the pair named and prints the total normal
    force on the slave surface, which the punch's reference node holds."""
    deck = rigid_punch_deck(tool="elements", d=0.01)
    i = deck.rindex("*END STEP")
    return deck[:i] + "*CONTACT PRINT\nCFN, CPRESS\n" + deck[i:]


def el_file_stops_deck(case, sdv=True):
    """Decks with *EL FILE output that stopped or crashed ccx 2.23 before (the converter's
    _el_file_stops).  'u1': a B31 cantilever (length 1000, A 1000, I11 4e5 about n1 = z, ten
    elements) under *BEAM GENERAL SECTION, run as U1, pulled by 100 along y at its tip, with
    *OUTPUT, FIELD, VARIABLE=ALL (ENER): tip deflection P L^3 / 3 E I11.  The others: CUBE8
    (E 210000, nu 0.3) pulled by 4 x 25 with S and SDV (``sdv``) requested, its top moving
    100 / E: 'depvar', of an elastic material with *DEPVAR, in a linear static step; 'carried',
    the same under NLGEOM, then a *FREQUENCY and a *STEADY STATE DYNAMICS step without element
    output, into which ccx carried SDV; 'plastic', of a plastic material (yield 250, never
    reached), then a *FREQUENCY step without element output; 'visco' and 'riks', of the
    *DEPVAR material in a *VISCO and a Riks step (--approximate: a linear *STATIC); 'dynamic',
    of it in a static step after a *DYNAMIC step under the same load (ccx iterates it);
    'explicit', after an explicit *DYNAMIC and a *FREQUENCY step (the explicit step's NLGEOM
    carries on: ccx iterates it; Abaqus would not mix them in one deck)."""
    field = "*OUTPUT, FIELD\n*ELEMENT OUTPUT\nS{}\n*NODE OUTPUT\nU\n".format(", SDV" if sdv else "")
    history = "*OUTPUT, HISTORY\n*NODE OUTPUT, NSET={}\nU\n"
    if case == "u1":
        return ("*NODE\n1, 0., 0., 0.\n11, 1000., 0., 0.\n*NGEN, NSET=AXIS\n1, 11\n*ELEMENT, "
                "TYPE=B31, ELSET=BEAM\n1, 1, 2\n*ELGEN, ELSET=BEAM\n1, 10, 1, 1\n*NSET, NSET=TIP\n"
                "11\n*BEAM GENERAL SECTION, ELSET=BEAM, SECTION=GENERAL\n1000., 4.E5, 0., 2.E5, "
                "5.4E5\n0., 0., 1.\n210000., 80769.2307692\n*BOUNDARY\n1, 1, 6\n*STEP\n*STATIC\n"
                "*CLOAD\nTIP, 2, 100.\n*OUTPUT, FIELD, VARIABLE=ALL\n" + history.format("TIP") +
                "*END STEP\n")
    law = "*PLASTIC\n250., 0.\n" if case == "plastic" else "*DEPVAR\n2\n*USER DEFINED FIELD\n"
    proc = {"visco": "*VISCO, CETOL=1.E-3\n0.1, 1.\n", "riks": "*STATIC, RIKS\n0.1, 1., , , 1.\n"
            }.get(case, "*STATIC\n")
    steps = (f"*STEP{', NLGEOM' if case == 'carried' else ''}\n{proc}*CLOAD\nTOP, 3, 25.\n"
             + field + history.format("TOP") + "*END STEP\n")
    if case == "dynamic":
        steps = "*STEP\n*DYNAMIC\n1.E-6, 1.E-5\n*CLOAD\nTOP, 3, 25.\n*END STEP\n" + steps
    if case == "explicit":
        steps = ("*STEP\n*DYNAMIC, EXPLICIT\n, 1.E-5\n*CLOAD\nTOP, 3, 25.\n*END STEP\n*STEP\n"
                 "*FREQUENCY\n3\n*END STEP\n" + steps)
    if case in ("carried", "plastic"):
        steps += "*STEP\n*FREQUENCY\n3\n*END STEP\n"
    if case == "carried":
        steps += ("*STEP\n*STEADY STATE DYNAMICS\n1.E5, 3.E5, 3\n*CLOAD\nTOP, 3, 25.\n*OUTPUT, "
                  "FIELD\n*NODE OUTPUT\nU\n" + history.format("TOP") + "*END STEP\n")
    return (CUBE8 + "*MATERIAL, NAME=M\n*ELASTIC\n210000., 0.3\n*DENSITY\n7.85E-9\n" + law +
            CUBE8_HELD + steps)


def tied_strip_deck(symmetric=True):
    """A composite S4R strip [0/90/90/0] of thickness 2 (its plies listed, or the bottom two
    with SYMMETRIC), cantilevered from a clamped rigid R3D4 plate below its first element by
    a *TIE (position tolerance 0.1, no adjustment): those nodes touch it with the bottom face."""
    nodes = [f"{11 + 10 * j + i}, {float(i)}, {float(j)}, 1." for j in range(2) for i in range(5)]
    elems = [f"{2 + i}, {11 + i}, {12 + i}, {22 + i}, {21 + i}" for i in range(4)]
    plies = ["0.5, 3, M, 0.", "0.5, 3, M, 90."] + ([] if symmetric else ["0.5, 3, M, 90.", "0.5, 3, M, 0."])
    lines = (["*NODE", "1, 0., 0., 0.", "2, 1., 0., 0.", "3, 1., 1., 0.", "4, 0., 1., 0.",
              "100, 0.5, 0.5, 0."] + nodes + ["*ELEMENT, TYPE=R3D4, ELSET=RIG", "1, 1, 2, 3, 4",
              "*ELEMENT, TYPE=S4R, ELSET=STRIP"] + elems +
             ["*NSET, NSET=TIP", "15, 25", "*RIGID BODY, REF NODE=100, ELSET=RIG",
              "*SURFACE, NAME=MASTER", "RIG, SPOS", "*SURFACE, NAME=SLAVE", "STRIP, SNEG",
              "*SHELL SECTION, ELSET=STRIP, COMPOSITE" + (", SYMMETRIC" if symmetric else "")] + plies +
             ["*MATERIAL, NAME=M", "*ELASTIC", "1000., 0.3",
              "*TIE, NAME=T, POSITION TOLERANCE=0.1, ADJUST=NO", "SLAVE, MASTER", "*STEP", "*STATIC",
              "*BOUNDARY", "100, 1, 6", "*CLOAD", "TIP, 3, -0.01", "*NODE PRINT, NSET=TIP", "U",
              "*END STEP"])
    return "\n".join(lines) + "\n"


def blank_nu_cube_deck():
    """A C3D8 cube at temperature 100 pulled by a stress of 190: *ELASTIC rows E 200000, nu 0.5
    at 20 (which --approximate clamps to 0.475) and E 190000, nu blank (0) at 100."""
    return (CUBE8 + "*NSET, NSET=ALLN\n1, 2, 3, 4, 5, 6, 7, 8\n*MATERIAL, NAME=M\n*ELASTIC\n"
            "200000., 0.5, 20.\n190000., , 100.\n*INITIAL CONDITIONS, TYPE=TEMPERATURE\nALLN, 100.\n" +
            CUBE8_HELD + "*STEP\n*STATIC\n*CLOAD\nTOP, 3, 47.5\n*NODE PRINT, NSET=TOP\nU\n*END STEP\n")


def instance_blank_cube_deck(form="orientation", blank=True):
    """An orthotropic C3D8 unit cube (E1 100, E2 = E3 10, nu 0.3, G 5) in an instance moved by
    (5, 0, 0) and turned 90 degrees about z.  Its material axes are the part's (an *ORIENTATION,
    or for ``form`` "distribution" a *DISTRIBUTION's element line), so axis 2 lies along global
    -x; a *TRANSFORM with the same axes on the face at global x = -1, pulled by 1 in local 2,
    and rollers (in local DOF 1 on its transformed nodes).  ``blank``: the instance lines, the
    axes and the *TRANSFORM written with blank fields for their zeros.  Uniaxial stress 1 along
    x: strains 1 / E2 = 0.1 along x, -nu12 / E1 = -0.003 along y, -nu23 / E2 = -0.03 along z."""
    axes = "1., , , , 1.," if blank else "1., 0., 0., 0., 1., 0."
    if form == "distribution":
        ori = ["*Distribution Table, name=T", "coord3D, coord3D",
               "*Distribution, name=D, location=ELEMENT, table=T", ", 1., 0., 0., 0., 1., 0.",
               "1, " + axes, "*Orientation, name=O", "D"]
    else:
        ori = ["*Orientation, name=O", axes]
    return "\n".join(
        ["*Part, name=P", "*Node"] + [f"{k + 1}, {x}., {y}., {z}." for k, (x, y, z) in enumerate(
            ((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)))] +
        ["*Element, type=C3D8, elset=CUBE", "1, 1, 2, 3, 4, 5, 6, 7, 8",
         "*Nset, nset=ALLN", "1, 2, 3, 4, 5, 6, 7, 8", "*Nset, nset=XFIX", "1, 2, 5, 6",
         "*Nset, nset=YFIX", "1, 5", "*Nset, nset=YFIXT", "4, 8", "*Nset, nset=ZFIX", "1, 2, 3, 4",
         "*Nset, nset=PULL", "3, 4, 7, 8", "*Transform, nset=PULL", axes] + ori +
        ["*Solid Section, elset=CUBE, material=M, orientation=O", "*End Part",
         "*Assembly, name=A", "*Instance, name=I, part=P",
         "5., , ," if blank else "5., 0., 0.",
         ", , , , , 1., 90." if blank else "0., 0., 0., 0., 0., 1., 90.",
         "*End Instance", "*End Assembly", "*Material, name=M", "*Elastic, type=ENGINEERING CONSTANTS",
         "100., 10., 10., 0.3, 0.3, 0.3, 5., 5.,", "5.", "*Boundary", "I.XFIX, 1, 1", "I.YFIX, 2, 2",
         "I.YFIXT, 1, 1", "I.ZFIX, 3, 3", "*Step", "*Static", "*Cload", "I.PULL, 2, 0.25",
         "*Node Print, nset=I.ALLN, global=yes", "U", "*End Step"]) + "\n"


def instance_beam_n1_deck(blank=True, n=10):
    """A cantilever of ``n`` B31 along the part's x (length 10, RECT 0.1 along n1 by 0.2, E 1e5,
    nu 0.3), n1 = -z, in an instance turned 90 degrees about x, so n1 lies along global y.  The
    tip pulled by 1e-3 along global z bends it about y: F L^3 / (3 E I), I = 0.1 x 0.2^3 / 12
    (with n1 left unturned, a quarter of I).  ``blank``: n1 and the rotation line written with
    blank fields for their zeros."""
    return "\n".join(
        ["*Part, name=P", "*Node"] + [f"{i + 1}, {10.0 * i / n}, 0., 0." for i in range(n + 1)] +
        ["*Element, type=B31, elset=BEAM"] + [f"{i + 1}, {i + 1}, {i + 2}" for i in range(n)] +
        ["*Nset, nset=ROOT", "1", "*Nset, nset=TIP", str(n + 1),
         "*Beam Section, elset=BEAM, material=M, section=RECT", "0.1, 0.2",
         "0., , -1." if blank else "0., 0., -1.", "*End Part", "*Assembly, name=A",
         "*Instance, name=I, part=P", "0., 0., 0.",
         "0., 0., 0., 1., , , 90." if blank else "0., 0., 0., 1., 0., 0., 90.",
         "*End Instance", "*End Assembly", "*Material, name=M", "*Elastic", "1e5, 0.3",
         "*Boundary", "I.ROOT, 1, 6", "*Step", "*Static", "*Cload", "I.TIP, 3, 1e-3",
         "*Node Print, nset=I.TIP", "U", "*End Step"]) + "\n"


def assembly_bolts_deck(blank=False):
    """Two instances, the second turned 90 degrees about x (its z axis along -y), of a part
    with a bolt (two C3D8 along z, length 2, both ends held) with a *PRE-TENSION SECTION at
    mid-length (node 99, loaded by 1000) and a unit block held at its bottom whose top a
    *DISTRIBUTING COUPLING (DCOUP3D node 98) loads by 100 along the part's -z.  E 210000,
    nu 0: the bolt's cut closes 1000 x 2 / E, the block shortens 100 / E.  ``blank``: the
    pre-tension normal and the second instance's lines written with blank fields for their
    zeros."""
    part = ["*PART, NAME=P", "*NODE"]
    part += [f"{1 + i + 2 * j + 4 * k}, {float(i)}, {float(j)}, {float(k)}"
             for k in range(3) for j in range(2) for i in range(2)]
    part += [f"{21 + i + 2 * j + 4 * k}, {2.0 + i}, {float(j)}, {float(k)}"
             for k in range(2) for j in range(2) for i in range(2)]
    part += ["98, 2.5, 0.5, 2.", "99, 0.5, 0.5, 1.", "*ELEMENT, TYPE=C3D8, ELSET=BOLT",
             "1, 1, 2, 4, 3, 5, 6, 8, 7", "2, 5, 6, 8, 7, 9, 10, 12, 11",
             "*ELEMENT, TYPE=C3D8, ELSET=BLK", "3, 21, 22, 24, 23, 25, 26, 28, 27",
             "*ELEMENT, TYPE=DCOUP3D, ELSET=DC", "4, 98", "*ELSET, ELSET=LOW", "1",
             "*NSET, NSET=ENDS", "1, 2, 3, 4, 9, 10, 11, 12", "*NSET, NSET=BOT", "21, 22, 23, 24",
             "*NSET, NSET=TOPF", "25, 26, 27, 28", "*NSET, NSET=PT", "99", "*NSET, NSET=RP", "98",
             "*SURFACE, NAME=CUT", "LOW, S2", "*SOLID SECTION, ELSET=BOLT, MATERIAL=M",
             "*SOLID SECTION, ELSET=BLK, MATERIAL=M", "*PRE-TENSION SECTION, SURFACE=CUT, NODE=99",
             ", , 1." if blank else "0., 0., 1.", "*DISTRIBUTING COUPLING, ELSET=DC", "TOPF, 1.",
             "*END PART"]
    asm = ["*ASSEMBLY, NAME=A", "*INSTANCE, NAME=I1, PART=P", "*END INSTANCE",
           "*INSTANCE, NAME=I2, PART=P"] + \
        ([", 5.", ", 5., , 1., 5., , 90."] if blank else ["0., 5., 0.", "0., 5., 0., 1., 5., 0., 90."]) + \
        ["*END INSTANCE", "*END ASSEMBLY", "*MATERIAL, NAME=M", "*ELASTIC", "210000., 0."]
    step = ["*STEP", "*STATIC", "*BOUNDARY", "I1.ENDS, 1, 3", "I2.ENDS, 1, 3", "I1.BOT, 1, 3",
            "I2.BOT, 1, 3", "*CLOAD", "I1.PT, 1, 1000.", "I2.PT, 1, 1000.", "I1.RP, 3, -100.",
            "I2.RP, 2, 100.", "*NODE PRINT, NSET=I1.PT", "U", "*NODE PRINT, NSET=I2.PT", "U",
            "*NODE PRINT, NSET=I1.TOPF", "U", "*NODE PRINT, NSET=I2.TOPF", "U", "*END STEP"]
    return "\n".join(part + asm + step) + "\n"


def perturbation_restore_deck(pert=None):
    """Four unit C3D8 cubes side by side (E 1000, nu 0, alpha 1e-3), each held statically at
    three corners.  A static step gives one cube each a *CLOAD, a face pressure, a prescribed
    displacement and temperature 100; the linear perturbation step ``pert`` (left out when
    None) changes all four, adds a load and a pressure and holds a free DOF ("modal": a
    *FREQUENCY step, then a *MODAL DYNAMIC step changing the loads); a last static step gives
    nothing, so it must end where the first one did."""
    nodes = [f"{10 * k + i + 1}, {3.0 * k + x}, {float(y)}, {float(z)}" for k in range(4)
             for i, (x, y, z) in enumerate(((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0),
                                            (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)))]
    elems = [f"{k + 1}, " + ", ".join(str(10 * k + i) for i in range(1, 9)) for k in range(4)]
    held = [f"{10 * k + n}, {d}" for k in range(4) for n, d in ((1, "1, 3"), (2, "2, 3"), (4, "3, 3"))]
    change = ["*CLOAD", "7, 1, 3.", "7, 2, 1.", "*DLOAD", "2, P2, 3.", "2, P4, 1.", "*BOUNDARY",
              "27, 2, 2, 0.3", "27, 1, 1, 0.5"]
    steps = {"freq": ["*STEP", "*FREQUENCY", "3"] + change + ["*TEMPERATURE", "TE, 300."],
             "buckle": ["*STEP, PERTURBATION", "*BUCKLE", "2"] + change,   # (no *TEMPERATURE there)
             # (Abaqus takes no BC or temperature in a modal dynamic step)
             "modal": ["*STEP", "*FREQUENCY", "3", "*END STEP", "*STEP", "*MODAL DYNAMIC",
                       "0.001, 0.003"] + change[:6]}
    return "\n".join(
        ["*NODE, NSET=ALLN"] + nodes + ["*ELEMENT, TYPE=C3D8, ELSET=EALL"] + elems +
        ["*NSET, NSET=TE, GENERATE", "31, 38", "*NSET, NSET=TIPS", "7, 17, 27, 37",
         "*MATERIAL, NAME=M", "*ELASTIC", "1000., 0.", "*DENSITY", "1.E-3", "*EXPANSION", "1.E-3",
         "*SOLID SECTION, ELSET=EALL, MATERIAL=M", "*INITIAL CONDITIONS, TYPE=TEMPERATURE",
         "ALLN, 0.", "*BOUNDARY"] + held +
        ["*STEP", "*STATIC", "*CLOAD", "7, 1, 1.", "*DLOAD", "2, P2, 1.", "*BOUNDARY",
         "27, 2, 2, 0.1", "*TEMPERATURE", "TE, 100.", "*END STEP"] +
        (steps[pert] + ["*END STEP"] if pert else []) +
        ["*STEP", "*STATIC", "*NODE PRINT, NSET=TIPS", "U", "*END STEP"]) + "\n"


def pert_chain_deck(case, twin=False):
    """A unit C3D8 cube (E 1000, nu 0.3, rho 1e-3) held at its bottom, its top pushed down in a
    static step, then linear perturbation steps; ``twin``: without the first of them, which
    Abaqus does not carry into the next one.  "freq_freq" / "freq_buckle": a *FREQUENCY step
    holding the top sideways, then a *FREQUENCY / *BUCKLE step; "buckle_freq": a *BUCKLE step
    holds a top corner sideways, then a *FREQUENCY step; "opnew_freq": a *FREQUENCY step with
    OP=NEW holding fewer DOFs, then a *FREQUENCY step; "modal": a *FREQUENCY step holding the
    top sideways, then a *FREQUENCY step, a static perturbation step and a *MODAL DYNAMIC step
    reading the second one's modes."""
    freq_bc = "*STEP\n*FREQUENCY\n3\n*BOUNDARY\nTOP, 1, 2\n*END STEP\n"
    first = {"freq_freq": freq_bc, "freq_buckle": freq_bc, "modal": freq_bc,
             "buckle_freq": "*STEP\n*BUCKLE\n2\n*BOUNDARY\n5, 1, 2\n*CLOAD\nTOP, 3, -1.\n*END STEP\n",
             "opnew_freq": "*STEP\n*FREQUENCY\n3\n*BOUNDARY, OP=NEW\nBOT, 3, 3\n1, 1, 2\n2, 2, 2\n"
                           "*END STEP\n"}[case]
    then = {"freq_buckle": "*STEP\n*BUCKLE\n2\n*CLOAD\nTOP, 3, -1.\n*END STEP\n",
            "modal": "*STEP\n*FREQUENCY\n3\n*END STEP\n*STEP, PERTURBATION\n*STATIC\n*CLOAD\n"
                     "TOP, 1, 0.001\n*END STEP\n*STEP\n*MODAL DYNAMIC\n0.01, 0.05\n*CLOAD\n7, 3, 0.001\n"
                     "*NODE PRINT, NSET=TOP\nU\n*END STEP\n"}.get(case, "*STEP\n*FREQUENCY\n3\n*END STEP\n")
    return ("*NODE\n1, 0.,0.,0.\n2, 1.,0.,0.\n3, 1.,1.,0.\n4, 0.,1.,0.\n5, 0.,0.,1.\n6, 1.,0.,1.\n"
            "7, 1.,1.,1.\n8, 0.,1.,1.\n*ELEMENT, TYPE=C3D8, ELSET=EALL\n1, 1,2,3,4,5,6,7,8\n"
            "*NSET, NSET=BOT\n1, 2, 3, 4\n*NSET, NSET=TOP\n5, 6, 7, 8\n*MATERIAL, NAME=M\n*ELASTIC\n"
            "1000., 0.3\n*DENSITY\n1e-3\n*SOLID SECTION, ELSET=EALL, MATERIAL=M\n*BOUNDARY\nBOT, 1, 3\n"
            "*STEP\n*STATIC\n*CLOAD\nTOP, 3, -1.\n*END STEP\n" + ("" if twin else first) + then)


def pert_fixed_deck(case, twin=False):
    """A unit C3D8 cube (E 1000, nu 0.3) on symmetry BCs, its corner node 7 held at u1 = 0.01 in
    a static step that also loads node 6, then a *BUCKLE step loading both (left out in the
    ``twin``), whose load case's response ccx 2.23 holds afterwards.  "own": the next static
    step holds node 7 with *BOUNDARY, FIXED (Abaqus: at its base-state 0.01); "given": a second
    static step before the *BUCKLE one holds it so after OP=NEW, which the last one carries on."""
    pr = "*NODE PRINT, NSET=X1\nU\n"
    if case == "own":
        steps = ["*STEP\n*STATIC\n*BOUNDARY\n7, 1, 1, 0.01\n*CLOAD\n6, 3, 0.5\n" + pr + "*END STEP\n",
                 "*STEP\n*STATIC\n*BOUNDARY, FIXED\n7, 1, 1\n*CLOAD\n6, 2, 0.5\n" + pr + "*END STEP\n"]
    else:
        steps = ["*STEP\n*STATIC\n*BOUNDARY\n7, 1, 1, 0.01\n" + pr + "*END STEP\n*STEP\n*STATIC\n"
                 "*BOUNDARY, OP=NEW\nX0, 1, 1\nY0, 2, 2\nZ0, 3, 3\n*BOUNDARY, FIXED\n7, 1, 1\n*CLOAD\n"
                 "6, 3, 0.5\n" + pr + "*END STEP\n",
                 "*STEP\n*STATIC\n*CLOAD\n6, 2, 0.5\n" + pr + "*END STEP\n"]
    buckle = "" if twin else "*STEP\n*BUCKLE\n1\n*CLOAD\n7, 1, 5.\n6, 3, 3.\n*END STEP\n"
    return ("*NODE\n1, 0.,0.,0.\n2, 1.,0.,0.\n3, 1.,1.,0.\n4, 0.,1.,0.\n5, 0.,0.,1.\n6, 1.,0.,1.\n"
            "7, 1.,1.,1.\n8, 0.,1.,1.\n*ELEMENT, TYPE=C3D8, ELSET=EALL\n1, 1,2,3,4,5,6,7,8\n"
            "*NSET, NSET=X0\n1, 4, 5, 8\n*NSET, NSET=Y0\n1, 2, 5, 6\n*NSET, NSET=Z0\n1, 2, 3, 4\n"
            "*NSET, NSET=X1\n2, 3, 6, 7\n*SOLID SECTION, ELSET=EALL, MATERIAL=M\n*MATERIAL, NAME=M\n"
            "*ELASTIC\n1000., 0.3\n*BOUNDARY\nX0, 1, 1\nY0, 2, 2\nZ0, 3, 3\n" + steps[0] + buckle + steps[1])


def buckle_chain_deck(twin=False):
    """A B32R cantilever column (10 elements, length 1, RECT 0.1 x 0.1, E 2e5; buckling load
    about 4.1) with no general step: a *STEP, PERTURBATION *BUCKLE step loading its tip
    sideways (left out in the ``twin``), whose load case's response ccx 2.23 then takes as the
    base state of a *STEP, PERTURBATION step, then one pushing it down."""
    nodes = "\n".join(f"{i + 1}, 0., 0., {i * 0.05:g}" for i in range(21))
    elems = "\n".join(f"{i + 1}, {2 * i + 1}, {2 * i + 2}, {2 * i + 3}" for i in range(10))
    return (f"*NODE\n{nodes}\n*ELEMENT, TYPE=B32R, ELSET=B\n{elems}\n*MATERIAL, NAME=M\n*ELASTIC\n"
            "2e5, 0.3\n*BEAM SECTION, ELSET=B, MATERIAL=M, SECTION=RECT\n0.1, 0.1\n1., 0., 0.\n"
            "*BOUNDARY\n1, 1, 6\n" +
            ("" if twin else "*STEP, PERTURBATION\n*BUCKLE\n2\n*CLOAD\n21, 1, 1.\n*END STEP\n") +
            "*STEP, PERTURBATION\n*BUCKLE\n2\n*CLOAD\n21, 3, -1.\n*END STEP\n")


def pert_frame_deck(case, pert=True, twin=False, n=4, blank=False):
    """A B31 frame (E 2.1e5, RECT 0.1 x 0.05, ``n`` elements per member): a beam along x from
    node 1 (clamped) to a joint at x = 2 (a ccx knot) and a column up from it, the joint with a
    *TRANSFORM.  "moment" (oblique local axes): a static step turns the joint by moments about
    local 1 and 2, the linear perturbation step ``pert`` ("buckle": *BUCKLE; "static": *STEP,
    PERTURBATION *STATIC; False: left out) loads it about local 3, and a last static step
    triples the moment about local 1 (the one about local 2 carries on); ``twin``: without the
    *TRANSFORM, the moments in global components.  "bc" (local axes about z): the first step
    turns local 1 and 3 by 0.01, a *FREQUENCY step holds local 3 at zero, the last step turns
    local 1 to 0.02 (local 3 stays at 0.01).  ``blank``: the *TRANSFORM's zeros as blank fields,
    which Abaqus and ccx read as 0."""
    j = 2 * n + 1                                     # the joint
    lines = (["*NODE"] + [f"{i + 1}, {i / n!r}, 0., 0." for i in range(2 * n + 1)] +
             [f"{j + k}, 2., 0., {k / n!r}" for k in range(1, n + 1)] + ["*ELEMENT, TYPE=B31, ELSET=B"] +
             [f"{i}, {i}, {i + 1}" for i in range(1, 2 * n + 1)] +
             [f"{2 * n + k}, {j + k - 1}, {j + k}" for k in range(1, n + 1)] +
             ["*NSET, NSET=FREE", f"{n}, {j + n}", "*BEAM SECTION, ELSET=B, MATERIAL=M, SECTION=RECT",
              "0.1, 0.05", "0., 1., 0.", "*MATERIAL, NAME=M", "*ELASTIC", "2.1e5, 0.3", "*DENSITY",
              "7.8e-9", "*BOUNDARY", "1, 1, 6"])
    ab = ((0.6, 0.8, 0.), (-0.8, 0.6, 0.5)) if case == "moment" else ((0., 1., 0.), (-1., 0., 0.))
    if not twin:
        lines += ["*NSET, NSET=TIP", str(j), "*TRANSFORM, NSET=TIP",
                  ", ".join("" if blank and not x else repr(x) for x in ab[0] + ab[1])]
    e3 = _unit(_cross(*ab))
    axes = (_unit(ab[0]), _cross(e3, _unit(ab[0])), e3)

    def moments(ms):
        if not twin:
            return ["*CLOAD"] + [f"{j}, {d}, {m!r}" for d, m in ms.items()]
        return ["*CLOAD"] + [f"{j}, {k + 4}, {sum(m * axes[d - 4][k] for d, m in ms.items())!r}"
                             for k in range(3)]
    out = ["*NODE PRINT, NSET=FREE", "U", "*END STEP"]
    if case == "bc":
        steps = [["*STEP", "*STATIC", "*BOUNDARY", f"{j}, 4, 4, 0.01", f"{j}, 6, 6, 0.01"] + out,
                 ["*STEP", "*FREQUENCY", "2", "*BOUNDARY", f"{j}, 6, 6", "*END STEP"] if pert else [],
                 ["*STEP", "*STATIC", "*BOUNDARY", f"{j}, 4, 4, 0.02"] + out]
    else:
        steps = [["*STEP", "*STATIC"] + moments({4: 0.01, 5: 0.01}) + out,
                 (["*STEP", "*BUCKLE", "2"] + moments({6: 1.}) + ["*END STEP"] if pert == "buckle" else
                  ["*STEP, PERTURBATION", "*STATIC"] + moments({6: 1.}) + out if pert else []),
                 ["*STEP", "*STATIC"] + moments({4: 0.03, 5: 0.01} if twin else {4: 0.03}) + out]
    return "\n".join(lines + [x for st in steps for x in st]) + "\n"


def pert_rest_deck(held=True):
    """A unit C3D8 cube (E 1000, nu 0, rho 1) held at its bottom: a *FREQUENCY step that holds
    node 7 in z (``held``), a static step pulling node 7 up, and a *DYNAMIC step taking it back
    to 0 with a displacement BC without AMPLITUDE (Abaqus/Standard ramps it)."""
    return ("*NODE\n1, 0.,0.,0.\n2, 1.,0.,0.\n3, 1.,1.,0.\n4, 0.,1.,0.\n5, 0.,0.,1.\n6, 1.,0.,1.\n"
            "7, 1.,1.,1.\n8, 0.,1.,1.\n*ELEMENT, TYPE=C3D8, ELSET=EALL\n1, 1,2,3,4,5,6,7,8\n"
            "*NSET, NSET=BOT\n1, 2, 3, 4\n*NSET, NSET=TOP\n5, 6, 7, 8\n*MATERIAL, NAME=M\n*ELASTIC\n"
            "1000., 0.\n*DENSITY\n1.\n*SOLID SECTION, ELSET=EALL, MATERIAL=M\n*BOUNDARY\nBOT, 1, 3\n"
            "*STEP\n*FREQUENCY\n3\n" + ("*BOUNDARY\n7, 3, 3\n" if held else "") + "*END STEP\n"
            "*STEP\n*STATIC\n*CLOAD\n7, 3, 10.\n*NODE PRINT, NSET=TOP\nU\n*END STEP\n*STEP\n"
            "*DYNAMIC\n0.01, 0.1\n*BOUNDARY\n7, 3, 3, 0.\n*NODE PRINT, NSET=TOP\nU\n*END STEP\n")


def pert_join_deck(held="21, 4, 6"):
    """A unit C3D8 cube (E 1000, nu 0.3) held on its x = 0 face, joined by a CONN3D2 JOIN from
    its node 2 to the end 21 of a B31 cantilever 1 away (a beam node's rotation turns the
    offset); a *FREQUENCY step holds ``held``, then a static step loads the cube's node 7."""
    return ("*NODE\n1, 0.,0.,0.\n2, 1.,0.,0.\n3, 1.,1.,0.\n4, 0.,1.,0.\n5, 0.,0.,1.\n6, 1.,0.,1.\n"
            "7, 1.,1.,1.\n8, 0.,1.,1.\n20, 3.,0.,0.\n21, 2.,0.,0.\n*ELEMENT, TYPE=C3D8, ELSET=EALL\n"
            "1, 1,2,3,4,5,6,7,8\n*ELEMENT, TYPE=B31, ELSET=B\n2, 20, 21\n*NSET, NSET=OUT\n2, 6, 7, 21\n"
            "*BEAM SECTION, ELSET=B, MATERIAL=M, SECTION=RECT\n0.2, 0.2\n0., 0., 1.\n"
            "*SOLID SECTION, ELSET=EALL, MATERIAL=M\n*MATERIAL, NAME=M\n*ELASTIC\n1000., 0.3\n"
            "*DENSITY\n1e-3\n*ELEMENT, TYPE=CONN3D2, ELSET=H\n30, 21, 2\n*CONNECTOR SECTION, ELSET=H\n"
            "JOIN,\n*BOUNDARY\n20, 1, 6\n1, 1, 3\n4, 1, 3\n5, 1, 3\n8, 1, 3\n"
            f"*STEP\n*FREQUENCY\n3\n*BOUNDARY\n{held}\n*END STEP\n"
            "*STEP\n*STATIC\n*CLOAD\n7, 3, 1.\n*NODE PRINT, NSET=OUT\nU\n*END STEP\n")


def after_pert_deck(case, twin=False):
    """A column of four unit C3D8 (E 1000, nu 0.3) held at its base, top nodes 17-20, for the
    steps after a linear perturbation step.  "nlgeom": a small shear in a static step, a *STEP,
    NLGEOM, PERTURBATION *FREQUENCY step, then a large tip shear (NLGEOM would give a quarter
    of the linear deflection); "modal" / "ssd": with *PLASTIC (yield 1e3: elastic throughout),
    a static step, *FREQUENCY and a *MODAL DYNAMIC step with Abaqus' preselected output (a
    *STEADY STATE DYNAMICS step with element output of its own); "total": a tip load on a
    TIME=TOTAL TIME amplitude (its value the total time) in two static steps around
    *FREQUENCY and a 0.5 *MODAL DYNAMIC step.  ``twin``: the answer Abaqus gives — without
    the perturbation steps ("nlgeom", "total"), the material elastic ("modal", "ssd")."""
    nodes = "".join(f"{1 + 4 * k}, 0., 0., {k}.\n{2 + 4 * k}, 1., 0., {k}.\n{3 + 4 * k}, 1., 1., {k}.\n"
                    f"{4 + 4 * k}, 0., 1., {k}.\n" for k in range(5))
    elems = "".join(f"{k + 1}, " + ", ".join(str(n + 4 * k) for n in range(1, 9)) + "\n" for k in range(4))
    plastic = "*PLASTIC\n1000., 0.\n1100., 0.1\n" if case in ("modal", "ssd") and not twin else ""
    deck = (f"*NODE\n{nodes}*ELEMENT, TYPE=C3D8, ELSET=EALL\n{elems}*NSET, NSET=BOT\n1, 2, 3, 4\n"
            f"*NSET, NSET=TOP\n17, 18, 19, 20\n*MATERIAL, NAME=M\n*ELASTIC\n1000., 0.3\n{plastic}"
            f"*DENSITY\n1e-3\n*SOLID SECTION, ELSET=EALL, MATERIAL=M\n*BOUNDARY\nBOT, 1, 3\n")
    out = "*NODE PRINT, NSET=TOP\nU\n*END STEP\n"
    if case == "nlgeom":
        freq = "" if twin else "*STEP, NLGEOM, PERTURBATION\n*FREQUENCY\n2\n*END STEP\n"
        return (deck + "*STEP\n*STATIC\n*CLOAD\nTOP, 2, 0.1\n" + out + freq +
                "*STEP\n*STATIC\n0.05, 1.\n*CLOAD, OP=NEW\nTOP, 2, 20.\n" + out)
    if case == "total":
        load = "*STEP\n*STATIC\n0.5, 1.\n*CLOAD, AMPLITUDE=TT\n19, 2, 0.1\n" + out
        pert = "" if twin else ("*STEP\n*FREQUENCY, STORAGE=YES\n2\n*END STEP\n*STEP\n*MODAL DYNAMIC\n"
                                "0.1, 0.5\n*END STEP\n")
        return deck + "*AMPLITUDE, NAME=TT, TIME=TOTAL TIME\n0., 0., 10., 10.\n" + load + pert + load
    deck += ("*STEP\n*STATIC\n*CLOAD\nTOP, 2, 0.1\n*END STEP\n*STEP\n*FREQUENCY, STORAGE=YES\n4\n"
             "*END STEP\n*STEP\n")
    if case == "modal":
        return deck + "*MODAL DYNAMIC\n0.01, 0.1\n*CLOAD\n19, 2, 1.\n" + out
    return (deck + "*STEADY STATE DYNAMICS\n1., 5., 3\n*CLOAD\n19, 2, 1.\n*OUTPUT, FIELD\n"
            "*NODE OUTPUT\nU\n*ELEMENT OUTPUT\nS\n" + out)


def nlgeom_no_deck(twin=False):
    """A cantilever of four C3D8I (E 1000, nu 0, 2 x 1 x 1 each) along x, clamped at x = 0, tip
    nodes 17-20: an NLGEOM static step loading the tip in z, then a *STEP, NLGEOM=NO static
    step loading it twice as hard (ccx ran it linear: tip 8.13, where NLGEOM gives 5.05).
    ``twin``: the second step with NLGEOM, the answer Abaqus gives (NLGEOM stays on)."""
    nodes = "".join(f"{4 * i + k + 1}, {2.0 * i}, {y}., {z}.\n"
                    for i in range(5) for k, (y, z) in enumerate(((0, 0), (1, 0), (1, 1), (0, 1))))
    elems = "".join(f"{i + 1}, " + ", ".join(str(4 * i + n) for n in (1, 5, 6, 2, 4, 8, 7, 3)) + "\n"
                    for i in range(4))
    step = "*STATIC\n0.1, 1.\n*CLOAD\nTIP, 3, {}\n*NODE PRINT, NSET=TIP\nU\n*END STEP\n"
    return (f"*NODE\n{nodes}*ELEMENT, TYPE=C3D8I, ELSET=EALL\n{elems}*NSET, NSET=FIX\n1, 2, 3, 4\n"
            "*NSET, NSET=TIP\n17, 18, 19, 20\n*MATERIAL, NAME=M\n*ELASTIC\n1000., 0.\n"
            "*SOLID SECTION, ELSET=EALL, MATERIAL=M\n*BOUNDARY\nFIX, 1, 3\n*STEP, NLGEOM\n" +
            step.format("0.5") + ("*STEP, NLGEOM\n" if twin else "*STEP, NLGEOM=NO\n") + step.format("1."))


def equation_held_deck(steps="both"):
    """Two C3D8 cubes (E 210000, nu 0.3, rho 7.8e-9) in a row, clamped at x = 0, with
    *EQUATION u2(12) = u2(9) between two far corners: a *FREQUENCY step whose BCs hold both
    those DOFs, then a static step pulling node 12 in y.  ``steps`` "freq": the frequency step
    alone, without the equation (it holds anyway); "static": the static step alone."""
    eq = "" if steps == "freq" else "*EQUATION\n2\n12, 2, 1., 9, 2, -1.\n"
    freq = "*STEP\n*FREQUENCY\n3\n*BOUNDARY\n12, 2, 2\n9, 2, 2\n*END STEP\n"
    static = "*STEP\n*STATIC\n1., 1.\n*CLOAD\n12, 2, 10.\n*NODE PRINT, NSET=FAR\nU\n*END STEP\n"
    return ("*NODE\n1, 0.,0.,0.\n2, 1.,0.,0.\n3, 2.,0.,0.\n4, 0.,1.,0.\n5, 1.,1.,0.\n6, 2.,1.,0.\n"
            "7, 0.,0.,1.\n8, 1.,0.,1.\n9, 2.,0.,1.\n10, 0.,1.,1.\n11, 1.,1.,1.\n12, 2.,1.,1.\n"
            "*ELEMENT, TYPE=C3D8, ELSET=EALL\n1, 1,2,5,4,7,8,11,10\n2, 2,3,6,5,8,9,12,11\n"
            "*NSET, NSET=LEFT\n1, 4, 7, 10\n*NSET, NSET=FAR\n3, 6, 9, 12\n"
            "*SOLID SECTION, ELSET=EALL, MATERIAL=M\n*MATERIAL, NAME=M\n*ELASTIC\n210000., 0.3\n"
            "*DENSITY\n7.8e-9\n*BOUNDARY\nLEFT, 1, 3\n" + eq +
            ("" if steps == "static" else freq) + ("" if steps == "freq" else static))


def lc2_column_deck(n=20):
    """A B31 column along z (length 4, ``n`` elements, RECT 0.1 x 0.1, E 2.1e11) clamped at its
    foot and held in x at its top: a static step loading it, then a *STEP, PERTURBATION
    *BUCKLE step whose LOAD CASE=1 BCs (OP=NEW) clamp the foot only and whose LOAD CASE=2 BCs
    hold the top in x too, under a unit axial load."""
    top = n + 1
    return ("*NODE\n" + "".join(f"{i + 1}, 0., 0., {4.0 * i / n!r}\n" for i in range(n + 1)) +
            "*ELEMENT, TYPE=B31, ELSET=COL\n" + "".join(f"{i + 1}, {i + 1}, {i + 2}\n" for i in range(n)) +
            "*BEAM SECTION, ELSET=COL, MATERIAL=M, SECTION=RECT\n0.1, 0.1\n1., 0., 0.\n"
            f"*MATERIAL, NAME=M\n*ELASTIC\n2.1e11, 0.3\n*BOUNDARY\n1, 1, 6\n{top}, 1, 1\n"
            f"*STEP\n*STATIC\n*CLOAD\n{top}, 3, -1.\n*END STEP\n"
            "*STEP, PERTURBATION\n*BUCKLE\n2\n*BOUNDARY, OP=NEW, LOAD CASE=1\n1, 1, 6\n"
            f"*BOUNDARY, OP=NEW, LOAD CASE=2\n1, 1, 6\n{top}, 1, 1\n*CLOAD\n{top}, 3, -1.\n*END STEP\n")


def pert_procs_deck():
    """A C3D8 cube (E 1000, nu 0.3) on rollers whose top moves up at 0.01 per time (*BOUNDARY,
    TYPE=VELOCITY) in a static step, then a *FREQUENCY and a *RESPONSE SPECTRUM step (linear
    perturbation steps), then a static step pulling a top corner sideways on a TIME=TOTAL TIME
    amplitude while the top moves on."""
    pert = "*STEP\n*FREQUENCY\n3\n*END STEP\n*STEP\n*RESPONSE SPECTRUM\n*END STEP\n"
    return ("*NODE\n1, 0.,0.,0.\n2, 1.,0.,0.\n3, 1.,1.,0.\n4, 0.,1.,0.\n5, 0.,0.,1.\n6, 1.,0.,1.\n"
            "7, 1.,1.,1.\n8, 0.,1.,1.\n*ELEMENT, TYPE=C3D8, ELSET=EALL\n1, 1,2,3,4,5,6,7,8\n"
            "*NSET, NSET=TOP\n5, 6, 7, 8\n*NSET, NSET=ALL\n1, 2, 3, 4, 5, 6, 7, 8\n"
            "*SOLID SECTION, ELSET=EALL, MATERIAL=M\n*MATERIAL, NAME=M\n*ELASTIC\n1000., 0.3\n"
            "*DENSITY\n1e-3\n*AMPLITUDE, NAME=TT, TIME=TOTAL TIME\n0., 0., 3., 1.\n"
            "*BOUNDARY\n1, 1, 3\n2, 2, 3\n3, 3, 3\n4, 1, 1\n4, 3, 3\n"
            "*STEP\n*STATIC\n0.5, 1.\n*BOUNDARY, TYPE=VELOCITY\nTOP, 3, 3, 0.01\n*END STEP\n" + pert +
            "*STEP\n*STATIC\n0.5, 1.\n*CLOAD, AMPLITUDE=TT\n7, 1, 1.\n*NODE PRINT, NSET=ALL\nU\n*END STEP\n")


def between_steps_deck(twin=False):
    """A C3D8 cube (E 1000, nu 0.3) on rollers, its top corner pushed up in a static step; then,
    between that step and the next static one (``twin``: inside it, after its procedure card),
    a *BOUNDARY, OP=NEW giving the rollers alone, a *CLOAD pulling a top corner sideways and a
    *NODE PRINT; the next step also pushes that corner along y."""
    move = ("*BOUNDARY, OP=NEW\n1, 1, 3\n2, 2, 3\n3, 3, 3\n4, 1, 1\n4, 3, 3\n*CLOAD\n6, 1, 1.\n"
            "*NODE PRINT, NSET=ALL\nU\n")
    return ("*NODE\n1, 0.,0.,0.\n2, 1.,0.,0.\n3, 1.,1.,0.\n4, 0.,1.,0.\n5, 0.,0.,1.\n6, 1.,0.,1.\n"
            "7, 1.,1.,1.\n8, 0.,1.,1.\n*ELEMENT, TYPE=C3D8, ELSET=EALL\n1, 1,2,3,4,5,6,7,8\n"
            "*NSET, NSET=ALL\n1, 2, 3, 4, 5, 6, 7, 8\n"
            "*SOLID SECTION, ELSET=EALL, MATERIAL=M\n*MATERIAL, NAME=M\n*ELASTIC\n1000., 0.3\n"
            "*BOUNDARY\n1, 1, 3\n2, 2, 3\n3, 3, 3\n4, 1, 1\n4, 3, 3\n"
            "*STEP\n*STATIC\n*BOUNDARY\n7, 3, 3, 0.01\n*END STEP\n" + ("" if twin else move) +
            "*STEP\n*STATIC\n" + (move if twin else "") + "*BOUNDARY\n6, 2, 2, 0.005\n*END STEP\n")


def shell_body_plate_deck(typ, steps, rho=7.5):
    """A 2 x 1 strip, t 0.1, E 1000, nu 0, clamped at x = 0 (its tip: node 3, x = 2): two S4
    (``typ`` "S4"), one S8R ("S8R") or its C3D8 twin ("C3D8": two bricks 0.1 thick, the tip
    nodes 3, 6, 9, 12) with ``steps`` (the step cards, each printing the tip's U); the shells'
    material has the density ``rho`` (None: none), the twin's none.  A surface TOPS (SPOS) and
    an amplitude A (a ramp) for the steps to use."""
    dens = "" if rho is None else f"*DENSITY\n{rho}\n"
    if typ == "C3D8":
        mesh = ("*NODE\n1, 0., 0., 0.\n2, 1., 0., 0.\n3, 2., 0., 0.\n4, 0., 1., 0.\n5, 1., 1., 0.\n"
                "6, 2., 1., 0.\n7, 0., 0., 0.1\n8, 1., 0., 0.1\n9, 2., 0., 0.1\n10, 0., 1., 0.1\n"
                "11, 1., 1., 0.1\n12, 2., 1., 0.1\n*ELEMENT, TYPE=C3D8, ELSET=E\n"
                "1, 1, 2, 5, 4, 7, 8, 11, 10\n2, 2, 3, 6, 5, 8, 9, 12, 11\n"
                "*SOLID SECTION, ELSET=E, MATERIAL=M\n*MATERIAL, NAME=M\n*ELASTIC\n1000., 0.\n"
                "*NSET, NSET=FIX\n1, 4, 7, 10\n*NSET, NSET=TIP\n3, 6, 9, 12\n*BOUNDARY\nFIX, 1, 3\n")
    else:
        if typ == "S8R":
            nodes = "1, 0., 0., 0.\n2, 1., 0., 0.\n3, 2., 0., 0.\n4, 0., .5, 0.\n5, 2., .5, 0.\n" \
                    "6, 0., 1., 0.\n7, 1., 1., 0.\n8, 2., 1., 0.\n"
            els, fix, tip = "1, 1, 3, 8, 6, 2, 5, 7, 4\n", "1, 4, 6", "3, 5, 8"
        else:
            nodes = "1, 0., 0., 0.\n2, 1., 0., 0.\n3, 2., 0., 0.\n4, 0., 1., 0.\n5, 1., 1., 0.\n6, 2., 1., 0.\n"
            els, fix, tip = "1, 1, 2, 5, 4\n2, 2, 3, 6, 5\n", "1, 4", "3, 6"
        mesh = (f"*NODE\n{nodes}*ELEMENT, TYPE={typ}, ELSET=E\n{els}*SHELL SECTION, ELSET=E, "
                f"MATERIAL=M\n0.1\n*MATERIAL, NAME=M\n*ELASTIC\n1000., 0.\n{dens}*NSET, NSET=FIX\n"
                f"{fix}\n*NSET, NSET=TIP\n{tip}\n*BOUNDARY\nFIX, 1, 6\n")
    return (mesh + "*SURFACE, NAME=TOPS\nE, SPOS\n*AMPLITUDE, NAME=A\n0., 0., 1., 1.\n" +
            "".join(f"*STEP\n*STATIC\n{cards}*NODE PRINT, NSET=TIP\nU\n*END STEP\n" for cards in steps))


def scordelis_roof_deck(typ, n, rho):
    """The Scordelis-Lo roof (MacNeal and Harder 1985) in inches, as the corpus deck
    petrkryslucsd_barrelvault_s3r_fineirreg gives it: R 300, half length 300, t 3, E 3e6,
    nu 0, a 40 degree half angle, its self-weight as *DLOAD ROOF, BX, -0.20833 (90 psf over
    3 in) along -x, the vertical.  The quarter on n x n ``typ`` (S4 / S8R) shells: the
    diaphragm at z = 0 holds u1 and u2, symmetry at z = 300 and along the crown (y = 0).
    ``rho``: the material's density (None: none).  Returns (deck, the free edge's midspan
    node), whose published vertical deflection is 0.3024 ft = 3.6288 in."""
    quad = typ == "S8R"
    m = 2 * n if quad else n
    nid = lambda i, j: 1 + i + (m + 1) * j              # i around the arc, j along z
    lines = ["*NODE"]
    for j in range(m + 1):
        for i in range(m + 1):
            a = math.radians(40.0) * i / m
            lines.append(f"{nid(i, j)}, {300 * math.cos(a):.12g}, {300 * math.sin(a):.12g}, {300.0 * j / m:.12g}")
    lines.append(f"*ELEMENT, TYPE={typ}, ELSET=ROOF")
    k = 0
    for j in range(n):
        for i in range(n):
            k += 1
            if quad:
                a, b = 2 * i, 2 * j
                c = [nid(a, b), nid(a + 2, b), nid(a + 2, b + 2), nid(a, b + 2),
                     nid(a + 1, b), nid(a + 2, b + 1), nid(a + 1, b + 2), nid(a, b + 1)]
            else:
                c = [nid(i, j), nid(i + 1, j), nid(i + 1, j + 1), nid(i, j + 1)]
            lines.append(", ".join(map(str, [k] + c)))
    sets = {"WALL": [nid(i, 0) for i in range(m + 1)], "SYMM": [nid(i, m) for i in range(m + 1)],
            "APEX": [nid(0, j) for j in range(m + 1)]}
    for name, ids in sets.items():
        lines.append(f"*NSET, NSET={name}")
        lines += [", ".join(map(str, ids[q:q + 16])) for q in range(0, len(ids), 16)]
    lines += ["*SHELL SECTION, ELSET=ROOF, MATERIAL=STEEL", "3., 5", "*MATERIAL, NAME=STEEL",
              "*ELASTIC", "3e+06, 0."] + (["*DENSITY", f"{rho}"] if rho is not None else []) + \
        ["*BOUNDARY", "APEX, YSYMM", "SYMM, ZSYMM", "WALL, 1, 2", "*STEP", "*STATIC", "*DLOAD",
         "ROOF, BX, -0.20833", "*NODE PRINT, NSET=SYMM", "U", "*END STEP"]
    return "\n".join(lines) + "\n", nid(m, m)


def equation_steps_deck(case):
    """A C3D8 cube (E 1000, nu 0.3) clamped at z = 0, with *EQUATION u2(7) = u2(6) between two top
    corners, in two static steps.  ``case`` "crossed": step 1 holds u2(7) at 0 alone, step 2 (OP=NEW)
    u2(6) alone, a corner pulled along x; "crossed_ref": both held in both steps, no equation;
    "nonzero": step 1 holds both at 0.1, step 2 frees them and pulls the tied DOFs along y;
    "nonzero_r1" / "nonzero_r2": step 1 without the equation / step 2 alone."""
    head = ("*NODE\n1, 0.,0.,0.\n2, 1.,0.,0.\n3, 1.,1.,0.\n4, 0.,1.,0.\n5, 0.,0.,1.\n6, 1.,0.,1.\n"
            "7, 1.,1.,1.\n8, 0.,1.,1.\n*ELEMENT, TYPE=C3D8, ELSET=EALL\n1, 1,2,3,4,5,6,7,8\n"
            "*NSET, NSET=ALL\n1, 2, 3, 4, 5, 6, 7, 8\n"
            "*SOLID SECTION, ELSET=EALL, MATERIAL=M\n*MATERIAL, NAME=M\n*ELASTIC\n1000., 0.3\n"
            "*BOUNDARY\n1, 1, 3\n2, 1, 3\n3, 1, 3\n4, 1, 3\n")
    eq = "" if case in ("crossed_ref", "nonzero_r1") else "*EQUATION\n2\n7, 2, 1., 6, 2, -1.\n"
    pr, new = "*NODE PRINT, NSET=ALL\nU\n", "*BOUNDARY, OP=NEW\n1, 1, 3\n2, 1, 3\n3, 1, 3\n4, 1, 3\n"
    if case.startswith("crossed"):
        both = case == "crossed_ref"
        return (head + eq + "*STEP\n*STATIC\n*BOUNDARY\n7, 2, 2\n" + ("6, 2, 2\n" if both else "") +
                "*CLOAD\n7, 1, 1.\n" + pr + "*END STEP\n*STEP\n*STATIC\n" + new + "6, 2, 2\n" +
                ("7, 2, 2\n" if both else "") + "*CLOAD\n7, 1, 2.\n" + pr + "*END STEP\n")
    one = "*STEP\n*STATIC\n*BOUNDARY\n7, 2, 2, 0.1\n6, 2, 2, 0.1\n*CLOAD\n7, 1, 1.\n" + pr + "*END STEP\n"
    two = "*STEP\n*STATIC\n" + ("" if case == "nonzero_r2" else new) + "*CLOAD\n" + \
        ("7, 1, 1.\n" if case == "nonzero_r2" else "") + "7, 2, 10.\n" + pr + "*END STEP\n"
    return head + eq + ("" if case == "nonzero_r2" else one) + ("" if case == "nonzero_r1" else two)


def after_pert_model(plastic=False):
    """after_pert_deck's column model alone (``plastic``: with its *PLASTIC, yield 1e3)."""
    text = after_pert_deck("modal", not plastic)
    return text[:text.index("*STEP")]


def plastic_contact_deck(case, twin=False):
    """after_pert_deck's plastic column (elastic throughout; ``twin``: no *PLASTIC) with a unit
    block pressed on its top (a prescribed displacement) through a *CONTACT PAIR: a static step
    with Abaqus' preselected output (its contact output too) and a *CONTACT PRINT, *FREQUENCY,
    then a *MODAL DYNAMIC step asking for U only ("modal": ccx would carry the contact output
    into it) or a *STEADY STATE DYNAMICS step with contact output of its own ("ssd").  (The
    frequency step leaves the base state's contact status out, reduced physics alike in both
    materials.)"""
    block = "".join(f"{21 + 4 * k}, 0., 0., {4 + k}.\n{22 + 4 * k}, 1., 0., {4 + k}.\n"
                    f"{23 + 4 * k}, 1., 1., {4 + k}.\n{24 + 4 * k}, 0., 1., {4 + k}.\n" for k in range(2))
    deck = (after_pert_model(not twin) + f"*NODE\n{block}*ELEMENT, TYPE=C3D8, ELSET=BLK\n"
            "5, 21, 22, 23, 24, 25, 26, 27, 28\n*SOLID SECTION, ELSET=BLK, MATERIAL=M\n"
            "*NSET, NSET=BTOP\n25, 26, 27, 28\n*ELSET, ELSET=E4\n4\n*SURFACE, NAME=COLTOP\nE4, S2\n"
            "*SURFACE, NAME=BLKBOT\nBLK, S1\n*SURFACE INTERACTION, NAME=INT\n*SURFACE BEHAVIOR, "
            "PRESSURE-OVERCLOSURE=LINEAR\n1e5\n*CONTACT PAIR, INTERACTION=INT\nBLKBOT, COLTOP\n"
            "*BOUNDARY\nBTOP, 1, 2\n*STEP\n*STATIC\n*BOUNDARY\nBTOP, 3, 3, -0.01\n*CONTACT PRINT\nCSTRESS\n"
            "*END STEP\n*STEP\n*FREQUENCY, STORAGE=YES\n4\n*END STEP\n")
    out = "*OUTPUT, FIELD\n*NODE OUTPUT\nU\n"
    if case == "modal":
        return deck + f"*STEP\n*MODAL DYNAMIC\n0.01, 0.1\n*CLOAD\n19, 2, 1.\n{out}" \
                      "*NODE PRINT, NSET=TOP\nU\n*END STEP\n"
    return deck + (f"*STEP\n*STEADY STATE DYNAMICS\n1., 5., 3\n*CLOAD\n19, 2, 1.\n{out}*CONTACT OUTPUT\n"
                   "CSTRESS, CDISP\n*CONTACT PRINT\nCSTRESS\n*NODE PRINT, NSET=TOP\nU\n*END STEP\n")


def contact_force_deck(case, cards=True):
    """plastic_contact_deck's block on the column through a face-to-face pair, the block's total
    reaction printed in the static step, and (``cards``) *CONTACT PRINT CFN there too, which ccx
    2.23 segfaulted on in the steps after, whatever the material: "modal", the plastic column,
    the static step's CFN carried into the *FREQUENCY step, and CFN in the *MODAL DYNAMIC step;
    "ssd", the elastic one, CFN in the *FREQUENCY step and CFS in the *STEADY STATE DYNAMICS
    step, then a static step pressing the block by 0.02, which Abaqus carries the static step's
    cards into."""
    cp = "*CONTACT PRINT, SLAVE=BLKBOT, MASTER=COLTOP\n{}\n"
    d = plastic_contact_deck(case, case == "ssd").replace(
        "*CONTACT PAIR, INTERACTION=INT\n", "*CONTACT PAIR, INTERACTION=INT, TYPE=SURFACE TO SURFACE\n")
    d = d.replace("CSTRESS\n*END STEP\n*STEP\n*FREQUENCY, STORAGE=YES\n4\n",
                  "CSTRESS\n*NODE PRINT, NSET=BTOP, TOTALS=YES\nRF\n" + cp.format("CFN") * cards +
                  "*END STEP\n*STEP\n*FREQUENCY, STORAGE=YES\n4\n" +
                  cp.format("CFN") * (cards and case == "ssd"))
    j = d.rindex("*END STEP")
    d = d[:j] + cp.format("CFN" if case == "modal" else "CFS") * cards + d[j:]
    return d + ("*STEP\n*STATIC\n*BOUNDARY\nBTOP, 3, 3, -0.02\n*NODE PRINT, NSET=BTOP, TOTALS=YES\n"
                "RF\n*END STEP\n" if case == "ssd" else "")


def modal_amplitude_deck(total, twin=False):
    """after_pert_deck's column (elastic) with a tip load on sin(2 pi t), an analytic *AMPLITUDE
    (DEFINITION=PERIODIC), in a *FREQUENCY and a 2.0 *MODAL DYNAMIC step; ``total``: on TIME=
    TOTAL TIME after a 0.25 static step, so the modal dynamic step reads it from 0.25 to 2.25.
    ``twin``: the curve as a TABULAR amplitude of 3001 points up to 3."""
    tt = ", TIME=TOTAL TIME" if total else ""
    if twin:
        amp = f"*AMPLITUDE, NAME=P{tt}\n" + "".join(
            f"{0.001 * k:.9g}, {math.sin(2 * math.pi * 0.001 * k):.12g}\n" for k in range(3001))
    else:
        amp = f"*AMPLITUDE, NAME=P, DEFINITION=PERIODIC{tt}\n1, {2 * math.pi!r}, 0., 0.\n0., 1.\n"
    load = "*CLOAD, AMPLITUDE=P\n19, 2, 0.1\n"
    static = f"*STEP\n*STATIC\n0.25, 0.25\n{load}*END STEP\n" if total else ""
    return (after_pert_model() + amp + static + "*STEP\n*FREQUENCY, STORAGE=YES\n4\n*END STEP\n"
            f"*STEP, INC=1000\n*MODAL DYNAMIC\n0.01, 2.\n{load}*NODE PRINT, NSET=TOP\nU\n*END STEP\n")


def frequency_loads_deck(loads=True):
    """after_pert_deck's column (elastic): an NLGEOM static step pushing its top sideways, a
    *FREQUENCY step with a traction on the top face (*DSLOAD TRVEC) and a *CLOAD, FOLLOWER of
    its own (``loads``), which Abaqus ignores, then a static step pulling the top the other
    way: as without them."""
    own = "*DSLOAD\nTOPS, TRVEC, 5., 0., 0., 1.\n*CLOAD, FOLLOWER\n10, 3, 3.\n" if loads else ""
    return (after_pert_model() + "*ELSET, ELSET=E4\n4\n*SURFACE, NAME=TOPS\nE4, S2\n*STEP, NLGEOM\n"
            "*STATIC\n0.5, 1.\n*CLOAD\n19, 1, 1.\n*END STEP\n"
            f"*STEP\n*FREQUENCY\n4\n{own}*END STEP\n"
            "*STEP\n*STATIC\n0.5, 1.\n*CLOAD\n19, 2, 2.\n*NODE PRINT, NSET=TOP\nU\n*END STEP\n")


def frequency_cload_deck(loads=True):
    """after_pert_deck's column (elastic): an NLGEOM static step pushing its top sideways, a
    *FREQUENCY step with a *CLOAD and gravity of its own (``loads``), which Abaqus ignores, then
    a static step pulling the top the other way in two increments (NLGEOM: a linear one runs in
    one): as without them."""
    own = "*CLOAD\n10, 3, 3.\n*DLOAD\nEALL, GRAV, 9.81, 0., 0., -1.\n" if loads else ""
    return (after_pert_model() + "*STEP, NLGEOM\n*STATIC\n*CLOAD\n19, 1, 1.\n*END STEP\n"
            f"*STEP\n*FREQUENCY\n4\n{own}*END STEP\n"
            "*STEP\n*STATIC\n0.5, 1.\n*CLOAD\n19, 2, 2.\n*NODE PRINT, NSET=TOP\nU\n*END STEP\n")


def modal_increments_deck(inc=""):
    """after_pert_deck's column (elastic): *FREQUENCY, then a *MODAL DYNAMIC step of 300
    increments (0.001 over 0.3) loading its top, ``inc`` on its *STEP card."""
    return (after_pert_model() + "*STEP\n*FREQUENCY, STORAGE=YES\n4\n*END STEP\n"
            f"*STEP{inc}\n*MODAL DYNAMIC\n0.001, 0.3\n*CLOAD\n19, 2, 1.\n*NODE PRINT, NSET=TOP\nU\n"
            "*END STEP\n")


def modal_bare_prints_deck(twin=False):
    """after_pert_deck's plastic column (elastic throughout): an NLGEOM static step printing the
    top's U and RF, *FREQUENCY, a *MODAL DYNAMIC step (where ccx 2.23 would segfault on RF: a
    bare *NODE PRINT ends it), then a static step without print cards, into which Abaqus
    carries the first step's; ``twin``: that step gives them itself."""
    out = "*NODE PRINT, NSET=TOP\nU, RF\n"
    return (after_pert_model(True) + f"*STEP, NLGEOM\n*STATIC\n*CLOAD\nTOP, 2, 0.1\n{out}*END STEP\n"
            "*STEP\n*FREQUENCY, STORAGE=YES\n4\n*END STEP\n*STEP\n*MODAL DYNAMIC\n0.01, 0.1\n"
            "*CLOAD\n19, 2, 1.\n*END STEP\n*STEP\n*STATIC\n0.5, 1.\n*CLOAD\nTOP, 2, 0.2\n"
            f"{out if twin else ''}*END STEP\n")


def pert_prints_deck(gen=True, own=True, last=""):
    """after_pert_deck's column (elastic): a static step loading its top (printing the base's
    RF if ``gen``), a *FREQUENCY step (printing the top's U if ``own``), then a static step
    loading it twice as much, with print cards ``last``."""
    rf = "*NODE PRINT, NSET=BOT\nRF\n"
    freq = "*NODE PRINT, NSET=TOP\nU\n" if own else ""
    return (after_pert_model() + f"*STEP\n*STATIC\n*CLOAD\nTOP, 2, 0.1\n{rf if gen else ''}*END STEP\n"
            f"*STEP\n*FREQUENCY\n4\n{freq}*END STEP\n*STEP\n*STATIC\n*CLOAD\nTOP, 2, 0.2\n{last}"
            "*END STEP\n")


def modal_own_loads_deck(base=True):
    """A unit C3D8 cube (E 1000, nu 0, rho 1e-3) held statically at three corners: a static
    step loads it (``base``: a *CLOAD, a face pressure, gravity and a traction, which becomes
    nodal forces), a *FREQUENCY step follows, then a *MODAL DYNAMIC step with a *CLOAD and a
    traction of its own.  Abaqus applies a modal dynamic step's own loads only, so its
    response must not depend on ``base``."""
    nodes = [f"{i + 1}, {float(x)}, {float(y)}, {float(z)}" for i, (x, y, z) in enumerate(
        ((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)))]
    loads = ["*CLOAD", "6, 2, 1.", "*DLOAD", "1, P2, 1.", "EALL, GRAV, 1000., 1., 0., 0.",
             "*DSLOAD", "SIDE, TRVEC, 1., 0., 0., 1."] if base else []
    return "\n".join(
        ["*NODE"] + nodes + ["*ELEMENT, TYPE=C3D8, ELSET=EALL", "1, 1, 2, 3, 4, 5, 6, 7, 8",
                             "*NSET, NSET=N7", "7", "*SURFACE, NAME=TOP", "EALL, S2",
                             "*SURFACE, NAME=SIDE", "EALL, S4", "*MATERIAL, NAME=M", "*ELASTIC",
                             "1000., 0.", "*DENSITY", "1.E-3", "*SOLID SECTION, ELSET=EALL, MATERIAL=M",
                             "*BOUNDARY", "1, 1, 3", "2, 2, 3", "4, 3, 3", "*STEP", "*STATIC"] +
        loads + ["*END STEP", "*STEP", "*FREQUENCY", "10", "*END STEP", "*STEP", "*MODAL DYNAMIC",
                 "0.001, 0.003", "*CLOAD", "7, 2, 1.", "*DSLOAD", "TOP, TRVEC, 1., 1., 0., 0.",
                 "*OUTPUT, FIELD, FREQUENCY=1", "*NODE OUTPUT", "U", "*NODE PRINT, NSET=N7", "U",
                 "*END STEP"]) + "\n"


def static_pert_own_loads_deck(base=True, between=True):
    """modal_own_loads_deck's cube (its static *CLOAD on node 3), without the static step if
    not ``base``, without the *FREQUENCY and *MODAL DYNAMIC steps if not ``between``, and a
    last *STEP, PERTURBATION *STATIC step loading node 6.  Abaqus applies only a perturbation
    step's own loads, about the base state, so its response must not depend on ``between``."""
    text = modal_own_loads_deck(base).replace("*CLOAD\n6, 2, 1.", "*CLOAD\n3, 1, 1.").replace(
        "*NODE PRINT, NSET=N7\nU\n", "").replace("*NSET, NSET=N7\n7\n", "*NSET, NSET=NALL, GENERATE\n1, 8, 1\n")
    if not base:
        text = text.replace("*STEP\n*STATIC\n*END STEP\n", "")
    if not between:
        text = text[:text.index("*STEP\n*FREQUENCY")]
    return text + "*STEP, PERTURBATION\n*STATIC\n*CLOAD\n6, 2, 1.\n*NODE PRINT, NSET=NALL\nU\n*END STEP\n"


def static_pert_adds_deck(between="", ref=False):
    """modal_own_loads_deck's cube, its static step also prescribing node 7's x (0.01), then
    ``between`` (steps) and a *STEP, PERTURBATION *STATIC step that changes each of those loads
    by half (the *CLOAD under OP=NEW, which removes nothing in a perturbation step) and node
    7's x by 0.02; ``ref``: one static step with the sums.  Abaqus reads a perturbation step's
    values as changes of the base state's, so base state plus perturbation is that step."""
    text = modal_own_loads_deck(True).replace("*NSET, NSET=N7\n7\n", "*NSET, NSET=NALL, GENERATE\n1, 8, 1\n")
    text = text[:text.index("*STEP\n*FREQUENCY")].replace("*END STEP\n", "*BOUNDARY\n7, 1, 1, 0.01\n*END STEP\n")
    cards = ("*CLOAD{}\n6, 2, {}\n*DLOAD\n1, P2, {}\nEALL, GRAV, {}, 1., 0., 0.\n*DSLOAD\nSIDE, TRVEC, {}, "
             "0., 0., 1.\n*BOUNDARY\n7, 1, 1, {}\n*NODE PRINT, NSET=NALL\nU\n*END STEP\n")
    if ref:
        return text[:text.index("*STEP")] + "*STEP\n*STATIC\n" + cards.format("", 1.5, 1.5, 1500., 1.5, 0.03)
    return text + between + "*STEP, PERTURBATION\n*STATIC\n" + cards.format(", OP=NEW", 0.5, 0.5, 500., 0.5, 0.02)


def static_pert_temps_deck(case, between="", ref=None):
    """modal_own_loads_deck's cube, unloaded, with expansion 1e-3 and initial temperatures 20:
    a static step heats nodes 5 and 6 to 100 and loads node 6, ``between`` (steps), then a
    *STEP, PERTURBATION *STATIC step.  ``case`` "temps": that step heats every node by 10 and
    loads node 6 by 1, both on an amplitude of 0.5 at time 0 (1 at its end), and node 7 by 0.5,
    and so does a first step before the static one (its base state: the initial one); "hold":
    it holds node 6's y, which the base state leaves free (a zero BC), and loads node 7.  The
    perturbation steps print U.  ``ref``: one static step with the sums, Abaqus' base state plus
    its perturbation ("first": of the first step; "hold": node 6's y held at ``ref``, its
    base-state value; "base": the base state)."""
    text = modal_own_loads_deck(False).replace("*NSET, NSET=N7\n7\n", "*NSET, NSET=NALL, GENERATE\n1, 8, 1\n"
                                               "*NSET, NSET=N56\n5, 6\n").replace(
        "*DENSITY", "*EXPANSION\n1.E-3\n*DENSITY")
    text = text[:text.index("*STEP")] + "*INITIAL CONDITIONS, TYPE=TEMPERATURE\nNALL, 20.\n" \
        "*AMPLITUDE, NAME=UP\n0., 0.5, 1., 1.\n"
    out = "*NODE PRINT, NSET=NALL\nU\n*END STEP\n"
    base = "*TEMPERATURE\nN56, 100.\n*CLOAD\n6, 2, 1.\n"
    if ref is not None:
        cards = {"temps": "*TEMPERATURE\nNALL, 25.\nN56, 105.\n*CLOAD\n6, 2, 1.5\n7, 1, 0.5\n",
                 "first": "*TEMPERATURE\nNALL, 25.\n*CLOAD\n6, 2, 0.5\n7, 1, 0.5\n",
                 "hold": f"{base}*CLOAD\n7, 1, 0.5\n*BOUNDARY\n6, 2, 2, {ref!r}\n", "base": base}[case]
        return text + "*STEP\n*STATIC\n" + cards + out
    pert = "*STEP, PERTURBATION\n*STATIC\n"
    if case == "temps":
        own = "*TEMPERATURE, AMPLITUDE=UP\nNALL, 10.\n*CLOAD, AMPLITUDE=UP\n6, 2, 1.\n*CLOAD\n7, 1, 0.5\n"
        return text + pert + own + out + "*STEP\n*STATIC\n" + base + "*END STEP\n" + between + pert + own + out
    return text + "*STEP\n*STATIC\n" + base + "*END STEP\n" + between + pert + \
        "*BOUNDARY\n6, 2, 2\n*CLOAD\n7, 1, 0.5\n" + out

def static_pert_leftovers_deck(case, between="", ref=False):
    """A static perturbation step after a general step, then ``between`` (steps).  ``case``
    "traction": modal_own_loads_deck's cube, its static step loading its top face by a traction
    on an amplitude (0.5 at the step's end), the perturbation step changing it by 0.3 (written
    as nodal forces); "gradient": a single S8 plate (thickness 0.1, E 1000, nu 0, expansion
    1e-3), the static step setting its temperature 50 and gradient 100 through the thickness,
    the perturbation step changing them by 10 and 20.  The perturbation step prints U.
    ``ref``: one static step with the sums, Abaqus' base state plus its perturbation."""
    out = "*NODE PRINT, NSET=NALL\nU\n*END STEP\n"
    if case == "traction":
        text = modal_own_loads_deck(False).replace("*NSET, NSET=N7\n7\n", "*NSET, NSET=NALL, GENERATE\n1, 8, 1\n")
        text = text[:text.index("*STEP")] + "*AMPLITUDE, NAME=HALF\n0., 0., 1., 0.5\n"
        base, own = "*DSLOAD, AMPLITUDE=HALF\nTOP, TRVEC, 1., 0., 1., 0.\n", "*DSLOAD\nTOP, TRVEC, 0.3, 0., 1., 0.\n"
        total = "*DSLOAD\nTOP, TRVEC, 0.8, 0., 1., 0.\n"
    else:
        text = ("*NODE\n1, 0., 0., 0.\n2, 0.5, 0., 0.\n3, 1., 0., 0.\n4, 1., 0.5, 0.\n5, 1., 1., 0.\n"
                "6, 0.5, 1., 0.\n7, 0., 1., 0.\n8, 0., 0.5, 0.\n*ELEMENT, TYPE=S8, ELSET=EALL\n"
                "1, 1, 3, 5, 7, 2, 4, 6, 8\n*NSET, NSET=NALL, GENERATE\n1, 8, 1\n*MATERIAL, NAME=M\n"
                "*ELASTIC\n1000., 0.\n*EXPANSION\n1.E-3\n*DENSITY\n1.E-3\n*SHELL SECTION, ELSET=EALL, "
                "MATERIAL=M\n0.1\n*BOUNDARY\n1, 1, 3\n3, 2, 3\n7, 3, 3\n"
                "*INITIAL CONDITIONS, TYPE=TEMPERATURE\nNALL, 0.\n")
        base, own, total = "*TEMPERATURE\nNALL, 50., 100.\n", "*TEMPERATURE\nNALL, 10., 20.\n", \
            "*TEMPERATURE\nNALL, 60., 120.\n"
    if ref:
        return text + "*STEP\n*STATIC\n" + total + out
    return text + "*STEP\n*STATIC\n" + base + "*END STEP\n" + between + "*STEP, PERTURBATION\n*STATIC\n" + \
        own + out


def static_pert_sums_deck(case, between="", ref=False):
    """modal_own_loads_deck's cube, unloaded, a static step, ``between`` (steps), then a *STEP,
    PERTURBATION *STATIC step.  ``case`` "twice": the static step loads node 6, face 1 by a
    pressure and the cube by gravity, the perturbation step changes each by two lines of half
    (the *CLOAD's on two cards); "total": the static step's *CLOAD on node 6, node 7's x and a
    traction on a TIME=TOTAL TIME amplitude (0.1 at its end), the perturbation step loading
    nodes 6 and 7; "shift": that *CLOAD alone, the perturbation step's *STATIC without a data
    line and an output request next, then a static step loading node 6 on the amplitude (0.2 at
    Abaqus' total time 2).  The last step prints U.  ``ref``: one static step with the sums,
    Abaqus' base state plus its perturbation (in "shift": the last step's state)."""
    text = modal_own_loads_deck(False).replace("*NSET, NSET=N7\n7\n", "*NSET, NSET=NALL, GENERATE\n1, 8, 1\n")
    text = text[:text.index("*STEP")] + "*AMPLITUDE, NAME=TT, TIME=TOTAL TIME\n0., 0., 10., 1.\n"
    out = "*NODE PRINT, NSET=NALL\nU\n*END STEP\n"
    if ref:
        return text + "*STEP\n*STATIC\n" + {
            "twice": "*CLOAD\n6, 2, 2.\n*DLOAD\n1, P2, 2.\nEALL, GRAV, 2000., 1., 0., 0.\n",
            "total": "*CLOAD\n6, 2, 1.5\n7, 3, 0.5\n*BOUNDARY\n7, 1, 1, 0.01\n*DSLOAD\n"
                     "SIDE, TRVEC, 0.1, 1., 0., 0.\n",
            "shift": "*CLOAD\n6, 2, 4.\n"}[case] + out
    if case == "twice":
        base = "*CLOAD\n6, 2, 1.\n*DLOAD\n1, P2, 1.\nEALL, GRAV, 1000., 1., 0., 0.\n"
        own = ("*CLOAD\n6, 2, 0.5\n*CLOAD\n6, 2, 0.5\n*DLOAD\n1, P2, 0.5\n1, P2, 0.5\n"
               "EALL, GRAV, 500., 1., 0., 0.\nEALL, GRAV, 500., 1., 0., 0.\n")
    else:
        base = "*CLOAD, AMPLITUDE=TT\n6, 2, 10.\n" + (
            "*BOUNDARY, AMPLITUDE=TT\n7, 1, 1, 0.1\n*DSLOAD, AMPLITUDE=TT\nSIDE, TRVEC, 1., 1., 0., 0.\n"
            if case == "total" else "")
        own = "*CLOAD\n6, 2, 0.5\n7, 3, 0.5\n"
    text += "*STEP\n*STATIC\n" + base + "*END STEP\n" + between + "*STEP, PERTURBATION\n*STATIC\n"
    if case == "shift":
        return text + "*NODE PRINT, NSET=NALL\nU\n" + own + "*END STEP\n*STEP\n*STATIC\n" \
            "*CLOAD, AMPLITUDE=TT\n6, 2, 20.\n" + out
    return text + own + out


def buckle_amplitude_deck(force, amp=True, start=0.25):
    """buckle_displacement_deck("tied", ``force``): its *STEP, PERTURBATION *BUCKLE step's
    *CLOAD on an amplitude of ``start`` at time 0 (1 at time 1) if ``amp``."""
    deck = buckle_displacement_deck("tied", force)
    if amp:
        deck = deck.replace("*Step, perturbation", f"*Amplitude, name=UP\n0., {start!r}, 1., 1.\n*Step, "
                                                   "perturbation").replace("*Cload\n", "*Cload, amplitude=UP\n")
    return deck


def delayed_traction_deck(pressure=False):
    """A unit C3D8 cube (E 1000, nu 0) on rollers, its top face pushed down by 1000 on an
    amplitude (0 at time 0, 1 at 1, 3 at 2) with TIME DELAY 0.25 in a static step of period 2
    (the end value a(1.75) = 2.5: the top at -2.5), then a static step giving nothing (the load
    stays at that value): as a traction (TRVEC), which becomes nodal forces, or as a pressure
    (``pressure``), which ccx takes with its delay."""
    load = "TOP, P, 1000." if pressure else "TOP, TRVEC, 1000., 0., 0., -1."
    return ("*NODE\n1, 0., 0., 0.\n2, 1., 0., 0.\n3, 1., 1., 0.\n4, 0., 1., 0.\n5, 0., 0., 1.\n"
            "6, 1., 0., 1.\n7, 1., 1., 1.\n8, 0., 1., 1.\n*ELEMENT, TYPE=C3D8, ELSET=EALL\n"
            "1, 1, 2, 3, 4, 5, 6, 7, 8\n*NSET, NSET=NALL, GENERATE\n1, 8, 1\n*MATERIAL, NAME=M\n"
            "*ELASTIC\n1000., 0.\n*SOLID SECTION, ELSET=EALL, MATERIAL=M\n*SURFACE, NAME=TOP\n"
            "EALL, S2\n*AMPLITUDE, NAME=B\n0., 0., 1., 1., 2., 3.\n*BOUNDARY\n1, 1, 3\n2, 2, 3\n"
            "3, 3, 3\n4, 1, 1\n4, 3, 3\n*STEP\n*STATIC\n0.5, 2.\n*DSLOAD, AMPLITUDE=B, TIME DELAY=0.25\n"
            f"{load}\n*NODE PRINT, NSET=NALL\nU\n*END STEP\n*STEP\n*STATIC\n*NODE PRINT, NSET=NALL\nU\n"
            "*END STEP\n")


def gradient_base_deck(case, ref=False):
    """static_pert_leftovers_deck("gradient")'s S8 plate, initial temperature 0, and a *STEP,
    PERTURBATION *STATIC step changing its temperature by 10 and its gradient through the
    thickness by 20.  ``case`` "one": after a static step that sets the temperature 50 by a
    one-value line (gradient 0); "back": right after initial temperatures 50, followed by a
    static step loading node 5 (the base state again).  The steps print U.  ``ref``: one static
    step with the sums (60, 20) / the base state's last step."""
    text = static_pert_leftovers_deck("gradient", ref=True)
    text = text[:text.index("*STEP")]
    out = "*NODE PRINT, NSET=NALL\nU\n*END STEP\n"
    pert = "*STEP, PERTURBATION\n*STATIC\n*TEMPERATURE\nNALL, 10., 20.\n" + out
    load = "*STEP\n*STATIC\n*CLOAD\n5, 3, 1.E-3\n" + out
    if case == "one":
        return text + "*STEP\n*STATIC\n*TEMPERATURE\nNALL, " + ("60., 20." if ref else "50.") + "\n" + \
            out + ("" if ref else pert)
    text = text.replace("TEMPERATURE\nNALL, 0.\n", "TEMPERATURE\nNALL, 50.\n")
    return text + ("" if ref else pert) + load


def shell_gradient_deck(etype):
    """A 2 x 1 plate of two S4 or S8R (``etype``; thickness 0.1, E 1000, nu 0, expansion 1e-3)
    held statically determinate and heated to 100 with a gradient of 100 through its
    thickness: free thermal strain and bending, the corner (2, 0) at x 0.2 and z -0.1."""
    order = 2 if etype == "S8R" else 1
    ids, nodes = {}, []
    for j in range(order + 1):
        for i in range(2 * order + 1):
            if order == 2 and i % 2 and j % 2:
                continue
            ids[(i, j)] = len(ids) + 1
            nodes.append(f"{ids[(i, j)]}, {i / order}, {j / order}, 0.")
    els = []
    for e in range(2):
        i, n = e * order, order
        conn = [(i, 0), (i + n, 0), (i + n, n), (i, n)]
        if order == 2:
            conn += [(i + 1, 0), (i + 2, 1), (i + 1, 2), (i, 1)]
        els.append(f"{e + 1}, " + ", ".join(str(ids[p]) for p in conn))
    return ("*NODE\n" + "\n".join(nodes) + f"\n*ELEMENT, TYPE={etype}, ELSET=EALL\n" + "\n".join(els) +
            f"\n*NSET, NSET=NALL, GENERATE\n1, {len(nodes)}, 1\n*MATERIAL, NAME=M\n*ELASTIC\n1000., 0.\n"
            f"*EXPANSION\n1.E-3\n*SHELL SECTION, ELSET=EALL, MATERIAL=M\n0.1\n*BOUNDARY\n{ids[(0, 0)]}, 1, 3\n"
            f"{ids[(order, 0)]}, 2, 3\n{ids[(0, order)]}, 3, 3\n*INITIAL CONDITIONS, TYPE=TEMPERATURE\n"
            f"NALL, 0.\n*STEP\n*STATIC\n*TEMPERATURE\nNALL, 100., 100.\n*NODE PRINT, NSET=NALL\nU\n"
            f"*END STEP\n"), ids[(2 * order, 0)]


def ramped_rotation_deck(step, twin=False):
    """pert_frame_deck("bc") without its *FREQUENCY step: the frame's joint 9 (a ccx knot, its
    *TRANSFORM about z: local 1 = y) turned about local 1 and 3 by 0.01, then about local 1 to
    0.02, by BCs without AMPLITUDE in steps where Abaqus ramps them and ccx would step them
    (``step``: "*DYNAMIC", or "*STATIC" under *STEP, AMPLITUDE=STEP); ``twin``: without the
    *TRANSFORM, the BCs on the global DOFs (5, 6)."""
    text = pert_frame_deck("bc", pert=False).replace(
        "*STEP\n*STATIC", "*STEP\n*DYNAMIC\n0.01, 1." if step == "*DYNAMIC" else
        "*STEP, AMPLITUDE=STEP\n*STATIC")
    if twin:
        text = re.sub(r"\*NSET, NSET=TIP\n.*\n\*TRANSFORM, NSET=TIP\n.*\n", "", text)
        text = re.sub(r"(?m)^9, 4, 4,", "9, 5, 5,", text)
    return text


def knot_offset_deck(twin=False):
    """Two S4 plates side by side (E 1000, nu 0.3, t 0.1), clamped along x = 0, their
    sections one with OFFSET=0. and one without (the same offset to ccx, which makes their
    shared node 5 no knot); node 5, with a *TRANSFORM (local 1 = y), turned about local 1 by
    0.01; ``twin``: without the *TRANSFORM, about global y."""
    return ("*NODE\n1, 0., 0., 0.\n2, 1., 0., 0.\n3, 2., 0., 0.\n4, 0., 1., 0.\n5, 1., 1., 0.\n"
            "6, 2., 1., 0.\n*ELEMENT, TYPE=S4, ELSET=E1\n1, 1, 2, 5, 4\n*ELEMENT, TYPE=S4, "
            "ELSET=E2\n2, 2, 3, 6, 5\n*SHELL SECTION, ELSET=E1, MATERIAL=M, OFFSET=0.\n0.1\n"
            "*SHELL SECTION, ELSET=E2, MATERIAL=M\n0.1\n*MATERIAL, NAME=M\n*ELASTIC\n1000., 0.3\n"
            "*NSET, NSET=FREE\n2, 3, 6\n" +
            ("" if twin else "*NSET, NSET=TR\n5\n*TRANSFORM, NSET=TR\n0., 1., 0., -1., 0., 0.\n") +
            "*BOUNDARY\n1, 1, 6\n4, 1, 6\n*STEP\n*STATIC\n*BOUNDARY\n" +
            ("5, 5, 5, 0.01\n" if twin else "5, 4, 4, 0.01\n") +
            "*NODE PRINT, NSET=FREE\nU\n*END STEP\n")


def midside_rotation_deck(twin=False):
    """A B31 cantilever along x (SECTION=CIRC, written as 3-node beams with midside nodes
    6-9), clamped at node 1, pinned at node 5; nodes 4 and 5, with a *TRANSFORM turned 30 deg
    about z, turned about local 1 by 0.01 and 0.02 and about local 2 by 0.005, as is the
    midside node 9 between them (interpolated); ``twin``: without the *TRANSFORM, the BCs in
    global components."""
    c, s = math.cos(math.radians(30.)), 0.5
    text = ("*NODE\n" + "".join(f"{i + 1}, {i * 0.5!r}, 0., 0.\n" for i in range(5)) +
            "*ELEMENT, TYPE=B31, ELSET=B\n" + "".join(f"{i}, {i}, {i + 1}\n" for i in range(1, 5)) +
            "*NSET, NSET=FREE\n2, 3\n*BEAM SECTION, ELSET=B, MATERIAL=M, SECTION=CIRC\n0.05\n"
            "0., 0., 1.\n*MATERIAL, NAME=M\n*ELASTIC\n2.1e5, 0.3\n*BOUNDARY\n1, 1, 6\n5, 1, 3\n" +
            ("" if twin else f"*NSET, NSET=TR\n4, 5\n*TRANSFORM, NSET=TR\n{c!r}, {s}, 0., {-s}, {c!r}, 0.\n") +
            "*STEP\n*STATIC\n*BOUNDARY\n")
    for n, a in ((4, 0.01), (5, 0.02)):
        text += (f"{n}, 4, 4, {a * c - 0.005 * s!r}\n{n}, 5, 5, {a * s + 0.005 * c!r}\n" if twin else
                 f"{n}, 4, 4, {a!r}\n{n}, 5, 5, 0.005\n")
    return text + "*NODE PRINT, NSET=FREE\nU\n*END STEP\n"


def curved_midside_deck(rot=False, twin=False):
    """A B31 quarter ring of radius 1 about z (SECTION=CIRC, written as 3-node beams), three
    elements, clamped at node 1; its last element's ends 3 and 4 with a cylindrical
    *TRANSFORM about z, moved radially, tangentially and axially (``rot``: node 4 pinned,
    both turned about those axes instead), as is that element's midside node (interpolated;
    its axes are 15 deg from both ends'); ``twin``: an identity *TRANSFORM there, the BCs in
    global components.  Prints nodes 1, 2 and the midside node between them."""
    pts = [(math.cos(math.radians(30. * i)), math.sin(math.radians(30. * i))) for i in range(4)]
    vals = {3: (0.01, 0.005, 0.003), 4: (0.02, 0., 0.006)} if not rot else \
        {3: (0.02, 0.01, 0.006), 4: (0.04, 0., 0.012)}
    text = ("*NODE\n" + "".join(f"{i + 1}, {x!r}, {y!r}, 0.\n" for i, (x, y) in enumerate(pts)) +
            "*ELEMENT, TYPE=B31, ELSET=B\n1, 1, 2\n2, 2, 3\n3, 3, 4\n*NSET, NSET=FREE\n1, 2\n"
            "*BEAM SECTION, ELSET=B, MATERIAL=M, SECTION=CIRC\n0.05\n0., 0., 1.\n*MATERIAL, NAME=M\n"
            "*ELASTIC\n2.1e5, 0.3\n*BOUNDARY\n1, 1, 6\n" + ("4, 1, 3\n" if rot else "") +
            "*NSET, NSET=TR\n3, 4\n" +
            ("*TRANSFORM, NSET=TR\n1., 0., 0., 0., 1., 0.\n" if twin else
             "*TRANSFORM, NSET=TR, TYPE=C\n0., 0., 0., 0., 0., 1.\n") + "*STEP\n*STATIC\n*BOUNDARY\n")
    for n, (r, t, z) in vals.items():
        x, y = pts[n - 1]
        g = (r * x - t * y, r * y + t * x, z) if twin else (r, t, z)
        text += "".join(f"{n}, {d}, {d}, {v:.12g}\n" for d, v in enumerate(g, 4 if rot else 1))
    return text + "*NODE PRINT, NSET=FREE, GLOBAL=YES\nU\n*END STEP\n"


def coupled_beam_deck(kind="kin"):
    """A B31 beam, SECTION=CIRC radius 0.01 (written as a 3-node beam with a new midside node),
    1 long, both ends kinematically coupled to a reference point RP (node 101), which a SPRING1
    of 1e4 holds in z (its other DOFs held); gravity.  Abaqus moves a linear beam between two
    coupled nodes rigidly, so every node of it moves u_z = -W / k.  ``kind``: "kin" — a
    *KINEMATIC COUPLING of translations, "native" — *COUPLING, *KINEMATIC on a node surface."""
    coupling = ("*KINEMATIC COUPLING, REF NODE=RP\nENDS, 1, 3\n" if kind == "kin" else
                "*SURFACE, NAME=SENDS, TYPE=NODE\nENDS\n"
                "*COUPLING, CONSTRAINT NAME=C1, REF NODE=101, SURFACE=SENDS\n*KINEMATIC\n")
    return ("*NODE\n101, 1.7, 0., 0.5\n1, 1.2, 0., 0.\n2, 2.2, 0., 0.\n"
            "*ELEMENT, TYPE=B31, ELSET=HANG\n11, 1, 2\n*ELEMENT, TYPE=SPRING1, ELSET=SPR\n20, 101\n"
            "*SPRING, ELSET=SPR\n3\n1.e4\n*NSET, NSET=ENDS\n1, 2\n*NSET, NSET=RP\n101\n"
            "*NSET, NSET=NALL\n101, 1, 2\n*MATERIAL, NAME=STEEL\n*ELASTIC\n2.1e11, 0.3\n"
            "*DENSITY\n7800.\n*BEAM SECTION, ELSET=HANG, MATERIAL=STEEL, SECTION=CIRC\n0.01\n"
            "0., 0., -1.\n" + coupling + "*BOUNDARY\nRP, 1, 2\nRP, 4, 6\n*STEP\n*STATIC\n*DLOAD\n"
            "HANG, GRAV, 9.81, 0., 0., -1.\n*NODE PRINT, NSET=NALL\nU\n*END STEP\n")


def transformed_beam_end(twin=False):
    """A straight B31 cantilever along y at x = 1 (SECTION=CIRC, written as 3-node beams;
    nodes 1-4, 0.5 apart, set ALLN), clamped at node 1, its last element's ends 3 and 4 with
    a cylindrical *TRANSFORM about z (their axes and their midside node's differ); ``twin``:
    without the *TRANSFORM.  Also how a node's (radial, tangential, axial) BC values read
    in the deck's axes."""
    def axes(n, v):
        if not twin:
            return v
        y = 0.5 * (n - 1)
        c, s = 1. / math.hypot(1., y), y / math.hypot(1., y)
        return (v[0] * c - v[1] * s, v[0] * s + v[1] * c, v[2])
    return ("*NODE\n" + "".join(f"{i + 1}, 1., {0.5 * i!r}, 0.\n" for i in range(4)) +
            "*ELEMENT, TYPE=B31, ELSET=B\n1, 1, 2\n2, 2, 3\n3, 3, 4\n*NSET, NSET=ALLN, GENERATE\n"
            "1, 4, 1\n*BEAM SECTION, ELSET=B, MATERIAL=M, SECTION=CIRC\n0.05\n0., 0., 1.\n"
            "*MATERIAL, NAME=M\n*ELASTIC\n2.1e5, 0.3\n*DENSITY\n7.8e-9\n*BOUNDARY\n1, 1, 6\n" +
            ("" if twin else "*NSET, NSET=TR\n3, 4\n*TRANSFORM, NSET=TR, TYPE=C\n0., 0., 0., 0., 0., 1.\n")), axes


def ramped_midside_deck(step, twin=False):
    """transformed_beam_end's ends 3 and 4 moved along all three local axes by BCs without
    AMPLITUDE in two steps where Abaqus ramps them and ccx would step them (``step``:
    "*DYNAMIC", or an NLGEOM "*STATIC" under *STEP, AMPLITUDE=STEP), the second with new
    values, as is their midside node (interpolated); ``twin``: without the *TRANSFORM, the BCs
    in global components.  Prints every node (the set takes the midside nodes) in every
    increment."""
    text, axes = transformed_beam_end(twin)
    head = ("*STEP\n*DYNAMIC\n0.05, 1., 1e-5, 0.05\n" if step == "*DYNAMIC" else
            "*STEP, NLGEOM, AMPLITUDE=STEP\n*STATIC\n0.25, 1., 1e-5, 0.25\n")
    for vals in ({3: (0.01, 0.005, 0.003), 4: (0.02, 0., 0.006)},
                 {3: (0.021, 0.012, 0.005), 4: (0.035, 0.004, 0.015)}):
        text += head + "*BOUNDARY\n" + "".join(f"{n}, {d}, {d}, {v:.12g}\n" for n, loc in vals.items()
                                               for d, v in enumerate(axes(n, loc), 1))
        text += "*NODE PRINT, NSET=ALLN, GLOBAL=YES\nU\n*END STEP\n"
    return text


def midside_velocity_deck(typ, twin=False):
    """transformed_beam_end's ends 3 and 4 moved along all three local axes by a *BOUNDARY,
    TYPE=``typ`` (VELOCITY or ACCELERATION) in a *DYNAMIC step, node 4's tangential rate
    zero, as is their midside node (the interpolated motion); ``twin``: without the
    *TRANSFORM, the rates in global components.  Prints every node."""
    text, axes = transformed_beam_end(twin)
    vals = {3: (0.01, 0.005, 0.003), 4: (0.02, 0., 0.006)}
    return (text + f"*STEP\n*DYNAMIC\n0.05, 1., 1e-5, 0.05\n*BOUNDARY, TYPE={typ}\n" +
            "".join(f"{n}, {d}, {d}, {v:.12g}\n" for n, loc in vals.items()
                    for d, v in enumerate(axes(n, loc), 1)) +
            "*NODE PRINT, NSET=ALLN, GLOBAL=YES\nU\n*END STEP\n")


def cshell_mass_deck(kind, proc="grav", twin=False):
    """A 2 x 1 plate of continuum shells 0.1 thick (4 x 2 SC8R, or each split into two SC6R),
    clamped at x = 0: ``kind`` "sc8r" / "sc6r" with *SHELL SECTION, MATERIAL=A (density 2), or
    "composite" (SC8R, plies of A and B (density 4), relative thickness 1:1, 0 / 90 degrees);
    the section DENSITY=0.5, a mass per unit area added to the materials'.  ``proc`` "grav":
    *STATIC under GRAV 1 in -z, the reactions' total and the tip (node 25) printed; "freq":
    *FREQUENCY, 3 modes.  ``twin``: no DENSITY=, the materials' densities 0.5 / 0.1 more."""
    nx, ny, t = 4, 2, 0.1
    nid = lambda i, j, k: 1 + i + (nx + 1) * j + (nx + 1) * (ny + 1) * k     # noqa: E731
    lines = ["*Heading", f"A {kind} plate of continuum shells with a section mass", "*Node"]
    lines += [f"{nid(i, j, k)}, {2.0 * i / nx:.12g}, {1.0 * j / ny:.12g}, {t * k:.12g}"
              for k in range(2) for j in range(ny + 1) for i in range(nx + 1)]
    lines.append(f"*Element, type={'SC6R' if kind == 'sc6r' else 'SC8R'}, elset=PLATE")
    e = 0
    for j in range(ny):
        for i in range(nx):
            q = [nid(i, j, 0), nid(i + 1, j, 0), nid(i + 1, j + 1, 0), nid(i, j + 1, 0)]
            top = [n + (nx + 1) * (ny + 1) for n in q]
            for c in ((0, 1, 2), (0, 2, 3)) if kind == "sc6r" else ((0, 1, 2, 3),):
                e += 1
                lines.append(f"{e}, " + ", ".join(str(n) for n in [q[a] for a in c] + [top[a] for a in c]))
    lines += ["*Nset, nset=LEFT"] + _ids([nid(0, j, k) for k in range(2) for j in range(ny + 1)])
    lines += ["*Nset, nset=TIP", str(nid(nx, ny // 2, 1))]
    add = 0.5 / t if twin else 0.0
    lines += ["*Material, name=A", "*Elastic", "100000., 0.3", "*Density", f"{2.0 + add:.12g}"]
    if kind == "composite":
        lines += ["*Material, name=B", "*Elastic", "50000., 0.3", "*Density", f"{4.0 + add:.12g}",
                  f"*Shell Section, elset=PLATE, composite{'' if twin else ', density=0.5'}",
                  "1., 3, A, 0.", "1., 3, B, 90."]
    else:
        lines += [f"*Shell Section, elset=PLATE, material=A{'' if twin else ', density=0.5'}", f"{t:g}"]
    lines += ["*Boundary", "LEFT, 1, 3", "*Step"]
    lines += ["*Static", "*Dload", "PLATE, GRAV, 1., 0., 0., -1.", "*Node print, nset=LEFT, totals=yes",
              "RF", "*Node print, nset=TIP", "U"] if proc == "grav" else ["*Frequency", "3"]
    return "\n".join(lines + ["*End Step"]) + "\n"


def coupled_made_mass_deck(kind, twin=False):
    """A transient *COUPLED TEMPERATURE-DISPLACEMENT step (fixed increments 0.1) with a mass
    the converter makes.  A C3D8T cube 1 x 1 x 1 (E 1000, nu 0.3, density 1e-3, no expansion)
    held at its bottom, heated there from 20 to 100, and ``kind`` "bgs": beside it a B31
    cantilever of length 2 along x, clamped, *BEAM GENERAL SECTION, SECTION=RECT 0.1 x 0.1, E
    1000, G 400, DENSITY=0.02 (first bending period about 1.1), its tip (node 24) loaded by
    1e-4 in -z on a ramp over the step; "stars": a *RIGID BODY of the cube's top face with
    *MASS 0.01 and *ROTARY INERTIA 1, 2, 3 at its reference node, turned by a moment 1 about z
    on a ramp (torsional period about 1.5), its top corner node 7 printed.  ``twin``: "bgs" a
    *BEAM SECTION of a material with the same E, nu = E / 2G - 1 and *DENSITY (which the
    converter always scaled), "stars" no *ROTARY INERTIA."""
    lines = ["*Heading", f"A converter-made mass ({kind}) in a transient coupled step", "*Node",
             "1, 0., 0., 0.", "2, 1., 0., 0.", "3, 1., 1., 0.", "4, 0., 1., 0.",
             "5, 0., 0., 1.", "6, 1., 0., 1.", "7, 1., 1., 1.", "8, 0., 1., 1."]
    lines += [f"{20 + k}, {3.0 + 0.5 * k:g}, 0., 0." for k in range(5)] if kind == "bgs" else \
        ["100, 0.5, 0.5, 1."]
    lines += ["*Element, type=C3D8T, elset=CUBE", "1, 1, 2, 3, 4, 5, 6, 7, 8", "*Nset, nset=BOT",
              "1, 2, 3, 4", "*Nset, nset=TOP", "5, 6, 7, 8", "*Material, name=M", "*Elastic",
              "1000., 0.3", "*Density", "0.001", "*Conductivity", "1.", "*Specific Heat", "1.",
              "*Solid Section, elset=CUBE, material=M"]
    if kind == "bgs":
        lines += ["*Element, type=B31, elset=BEAM"] + [f"{11 + k}, {20 + k}, {21 + k}" for k in range(4)]
        lines += ["*Nset, nset=ROOT", "20", "*Nset, nset=PROBE", "24"]
        lines += ["*Material, name=BM", "*Elastic", "1000., 0.25", "*Density", "0.02",
                  "*Beam Section, elset=BEAM, material=BM, section=RECT", "0.1, 0.1", "0., 1., 0."] if twin \
            else ["*Beam General Section, elset=BEAM, section=RECT, density=0.02", "0.1, 0.1", "0., 1., 0.",
                  "1000., 400."]
        load = ["PROBE, 3, -0.0001"]
    else:
        lines += ["*Element, type=MASS, elset=EM", "2, 100", "*Nset, nset=RP", "100", "*Nset, nset=PROBE",
                  "7", "*Rigid Body, ref node=RP, tie nset=TOP", "*Mass, elset=EM", "0.01"]
        if not twin:
            lines += ["*Element, type=ROTARYI, elset=ER", "3, 100", "*Rotary Inertia, elset=ER", "1., 2., 3."]
        load = ["RP, 6, 1."]
    lines += ["*Initial Conditions, type=temperature"] + [f"{k}, 20." for k in range(1, 9)]
    lines += ["*Amplitude, name=RAMP", "0., 0., 1., 1.", "*Step, inc=100",
              "*Coupled Temperature-displacement", "0.1, 1., 0.1, 0.1", "*Boundary", "BOT, 1, 3"]
    lines += ["ROOT, 1, 6"] if kind == "bgs" else []
    lines += ["*Boundary", "BOT, 11, 11, 100.", "*Cload, amplitude=RAMP"] + load
    lines += ["*Node print, nset=PROBE", "U", "*End Step"]
    return "\n".join(lines) + "\n"


def shell_mass_deck(kind, proc="grav", twin=False):
    """A 2 x 1 plate of conventional shells 0.1 thick (4 x 2 elements), clamped at x = 0:
    ``kind`` "s4" (S4, *SHELL SECTION, MATERIAL=A, density 2) or "composite" (S4R, which the
    converter writes as S8R, plies of A and B (density 4) 0.05 thick each, 0 / 90 degrees);
    the section DENSITY=0.5, a mass per unit area added to the materials'.  ``proc`` "grav":
    *STATIC under GRAV 1 in -z, the reactions' total and the tip (node 10) printed; "freq":
    *FREQUENCY, 3 modes.  ``twin``: no DENSITY=, the materials' densities 0.5 / 0.1 more."""
    nx, ny, t = 4, 2, 0.1
    nid = lambda i, j: 1 + i + (nx + 1) * j                                   # noqa: E731
    lines = ["*Heading", f"A {kind} plate of conventional shells with a section mass", "*Node"]
    lines += [f"{nid(i, j)}, {2.0 * i / nx:.12g}, {1.0 * j / ny:.12g}, 0." for j in range(ny + 1) for i in range(nx + 1)]
    lines.append(f"*Element, type={'S4' if kind == 's4' else 'S4R'}, elset=PLATE")
    lines += [f"{1 + i + nx * j}, {nid(i, j)}, {nid(i + 1, j)}, {nid(i + 1, j + 1)}, {nid(i, j + 1)}"
              for j in range(ny) for i in range(nx)]
    lines += ["*Nset, nset=LEFT"] + _ids([nid(0, j) for j in range(ny + 1)])
    lines += ["*Nset, nset=TIP", str(nid(nx, ny // 2))]
    add = 0.5 / t if twin else 0.0
    lines += ["*Material, name=A", "*Elastic", "100000., 0.3", "*Density", f"{2.0 + add:.12g}"]
    if kind == "composite":
        lines += ["*Material, name=B", "*Elastic", "50000., 0.3", "*Density", f"{4.0 + add:.12g}",
                  f"*Shell Section, elset=PLATE, composite{'' if twin else ', density=0.5'}",
                  "0.05, 3, A, 0.", "0.05, 3, B, 90."]
    else:
        lines += [f"*Shell Section, elset=PLATE, material=A{'' if twin else ', density=0.5'}", f"{t:g}, 5"]
    lines += ["*Boundary", "LEFT, 1, 6", "*Step"]
    lines += ["*Static", "*Dload", "PLATE, GRAV, 1., 0., 0., -1.", "*Node print, nset=LEFT, totals=yes",
              "RF", "*Node print, nset=TIP", "U"] if proc == "grav" else ["*Frequency", "3"]
    return "\n".join(lines + ["*End Step"]) + "\n"


def heatless_beam_deck(kind, twin=False):
    """coupled_made_mass_deck's "bgs" deck (a C3D8T cube heated in a coupled temperature-
    displacement step beside a B31 cantilever, its tip loaded on a ramp over 10 increments)
    with a beam whose material neither conducts nor stores heat, on which ccx 2.23 stopped
    (exit 255, 'matrix found to be singular' in spooles.out): ``kind`` "transient" a *BEAM
    SECTION material with *DENSITY 0, "steady" the same with *DENSITY 0.02 in a steady-state
    step, "general" a *BEAM GENERAL SECTION, DENSITY=0. in a transient step.  ``twin``: the
    *BEAM SECTION material with *CONDUCTIVITY 1 and *SPECIFIC HEAT 1 (the beam shares no node
    with the cube, so its heat goes nowhere)."""
    text = coupled_made_mass_deck("bgs", twin=kind != "general" or twin)
    rho = "0.02" if kind == "steady" else "0."
    bm = "*Material, name=BM\n*Elastic\n1000., 0.25\n*Density\n"
    text = text.replace(bm + "0.02\n", bm + rho + "\n" + ("*Conductivity\n1.\n*Specific Heat\n1.\n" if twin else ""))
    if kind == "general" and not twin:
        text = text.replace("density=0.02", "density=0.")
    if kind == "steady":
        text = text.replace("*Coupled Temperature-displacement\n", "*Coupled Temperature-displacement, steady state\n")
    return text


ROTATED_INSTANCES = {"I0": None, "I1": ((0., 3., 0.), (1., 3., 0.), 90.),
                     "I2": ((0., 0., 6.), (1., 2., 9.), 40.)}


def rotated_instance_dofs_deck():
    """A part, a C3D8 bar 3 x 1 x 1 held at x = 0, with DOF-numbered data in its own axes: an
    *EQUATION u3(10) - 0.5 u2(11) + 0.3 u1(12) = 0 (node 11 with a *TRANSFORM, so its term is
    in the local axes), a legacy *KINEMATIC COUPLING of DOFs 2-3 of face x = 1 to node 101, a
    *COUPLING, *KINEMATIC of DOF 2 of face x = 3 to node 100, a SPRING1 on DOF 2 of node 9 and
    a SPRING2 between DOF 1 of node 10 and DOF 3 of node 12.  Instanced three times
    (ROTATED_INSTANCES: point a, point b, angle): I0 as it is, I1 turned 90 degrees about x
    (each part axis along a global one) and I2 40 degrees about (1, 2, 3).  The reference
    nodes' six DOFs are prescribed and two nodes loaded, in each instance turned with it: R u0,
    R theta0, R F0 in global components, so every instance's displacements are R u(I0).
    Returns the deck and {instance: R}."""
    rots = {}
    for name, rot in ROTATED_INSTANCES.items():
        rots[name] = (lambda v: tuple(v)) if rot is None else (
            lambda v, e=_unit([y - x for x, y in zip(rot[0], rot[1])]), p=math.radians(rot[2]):
            _rotate(v, e, p))
    nodes = [f"{4 * i + c + 1}, {i}., {y}., {z}." for i in range(4)
             for c, (y, z) in enumerate(((0, 0), (1, 0), (1, 1), (0, 1)))]
    part = ("*PART, NAME=P\n*NODE\n" + "\n".join(nodes) + "\n100, 3.5, 0.5, 0.5\n101, 1., 0.5, 1.5\n"
            "*ELEMENT, TYPE=C3D8, ELSET=EALL\n" +
            "".join(f"{i + 1}, " + ", ".join(str(4 * i + k) for k in range(1, 9)) + "\n" for i in range(3)) +
            "*ELEMENT, TYPE=SPRING1, ELSET=S1\n20, 9\n*ELEMENT, TYPE=SPRING2, ELSET=S2\n21, 10, 12\n"
            "*NSET, NSET=BASE\n1, 2, 3, 4\n*NSET, NSET=MID\n5, 6, 7, 8\n*NSET, NSET=TIP\n13, 14, 15, 16\n"
            "*NSET, NSET=TR\n11\n*NSET, NSET=BODY, GENERATE\n1, 16, 1\n"
            "*SOLID SECTION, ELSET=EALL, MATERIAL=M\n*SPRING, ELSET=S1\n2\n50.\n*SPRING, ELSET=S2\n1, 3\n80.\n"
            "*TRANSFORM, NSET=TR\n0.6, 0.8, 0., -0.8, 0.6, 0.\n*EQUATION\n3\n10, 3, 1., 11, 2, -0.5, 12, 1, 0.3\n"
            "*KINEMATIC COUPLING, REF NODE=101\nMID, 2, 3\n*SURFACE, TYPE=NODE, NAME=STIP\nTIP\n"
            "*COUPLING, CONSTRAINT NAME=C, REF NODE=100, SURFACE=STIP\n*KINEMATIC\n2, 2\n*END PART\n")
    asm = "*ASSEMBLY, NAME=A\n"
    for name, rot in ROTATED_INSTANCES.items():
        asm += f"*INSTANCE, NAME={name}, PART=P\n"
        if rot is not None:
            asm += (", ".join(f"{x:g}" for x in rot[0]) + "\n" +
                    ", ".join(f"{x:g}" for x in (*rot[0], *rot[1], rot[2])) + "\n")
        asm += "*END INSTANCE\n"
    asm += "*END ASSEMBLY\n*MATERIAL, NAME=M\n*ELASTIC\n1000., 0.3\n"
    prescribed = {100: ((0.05, 0.1, -0.04), (0.02, -0.01, 0.03)), 101: ((0., 0.05, 0.02), (0.01, 0., -0.02))}
    loads = {14: (0.5, 0., 0.3), 6: (0.4, 0., 0.)}
    bc, cl, out = ["*BOUNDARY"], ["*CLOAD"], []
    for name, r in rots.items():
        bc.append(f"{name}.BASE, 1, 3")
        for n, (u, t) in prescribed.items():
            bc += [f"{name}.{n}, {k + 1}, {k + 1}, {x:.12g}" for k, x in enumerate((*r(u), *r(t)))]
        cl += [f"{name}.{n}, {k + 1}, {x:.12g}" for n, f in loads.items() for k, x in enumerate(r(f))]
        out += [f"*NODE PRINT, NSET={name}.BODY, GLOBAL=YES", "U"]
    return part + asm + "*STEP\n*STATIC\n" + "\n".join(bc + cl + out) + "\n*END STEP\n", rots


def _instances_of_p():
    """The *ASSEMBLY of part P instanced as ROTATED_INSTANCES, and {instance: R}."""
    rots, asm = {}, "*ASSEMBLY, NAME=A\n"
    for name, rot in ROTATED_INSTANCES.items():
        rots[name] = (lambda v: tuple(v)) if rot is None else (
            lambda v, e=_unit([y - x for x, y in zip(rot[0], rot[1])]), p=math.radians(rot[2]):
            _rotate(v, e, p))
        asm += f"*INSTANCE, NAME={name}, PART=P\n"
        if rot is not None:
            asm += (", ".join(f"{x:g}" for x in rot[0]) + "\n" +
                    ", ".join(f"{x:g}" for x in (*rot[0], *rot[1], rot[2])) + "\n")
        asm += "*END INSTANCE\n"
    return asm + "*END ASSEMBLY\n", rots


def rotated_instance_point_deck(kind):
    """A part P of node 1 (instance set M) and node 2 at the same place (set GR, held), its
    DOF-numbered data in the part's axes, instanced as ROTATED_INSTANCES; node 1 loaded by R F
    in each, in an NLGEOM step.  ``kind`` "dashpot": a point mass 1 on a SPRING1 on DOF 1 (k
    100) and DASHPOT1 elements on DOFs 2 (c 10) and 3 (c 20), F = (0.5, 1, 1), *DYNAMIC over
    1 s; "gap": SPRING1s on DOFs 1, 2, 3 (k 100, 100, 10) and a GAPUNI from 1 to 2, clearance
    0.02 along the part's z, F = (1, 2, 1), *STATIC (free, node 1 would move 0.1 along z).
    Node 1 printed in global components.  Returns the deck and {instance: R}."""
    part = "*PART, NAME=P\n*NODE\n1, 0., 0., 0.\n2, 0., 0., 0.\n*NSET, NSET=M\n1\n*NSET, NSET=GR\n2\n"
    springs = ((1, "100."),) if kind == "dashpot" else ((1, "100."), (2, "100."), (3, "10."))
    part += "".join(f"*ELEMENT, TYPE=SPRING1, ELSET=S{d}\n1{d}, 1\n*SPRING, ELSET=S{d}\n{d}\n{k}\n"
                    for d, k in springs)
    if kind == "dashpot":
        part += ("*ELEMENT, TYPE=MASS, ELSET=EM\n10, 1\n*MASS, ELSET=EM\n1.\n"
                 "*ELEMENT, TYPE=DASHPOT1, ELSET=D2\n22, 1\n*DASHPOT, ELSET=D2\n2\n10.\n"
                 "*ELEMENT, TYPE=DASHPOT1, ELSET=D3\n23, 1\n*DASHPOT, ELSET=D3\n3\n20.\n")
        step, force = "*DYNAMIC, DIRECT\n0.005, 1.\n", (0.5, 1.0, 1.0)
    else:
        part += "*ELEMENT, TYPE=GAPUNI, ELSET=G\n30, 1, 2\n*GAP, ELSET=G\n0.02, 0., 0., 1.\n"
        step, force = "*STATIC\n0.1, 1.\n", (1.0, 2.0, 1.0)
    asm, rots = _instances_of_p()
    deck = part + "*END PART\n" + asm + "*BOUNDARY\n" + "".join(f"{n}.GR, 1, 3\n" for n in rots)
    deck += "*STEP, NLGEOM, INC=1000\n" + step + "*CLOAD\n"
    for name, r in rots.items():
        deck += "".join(f"{name}.M, {k + 1}, {x:.12g}\n" for k, x in enumerate(r(force)))
    deck += "".join(f"*NODE PRINT, NSET={n}.M, GLOBAL=YES, FREQUENCY=20\nU\n" for n in rots)
    return deck + "*END STEP\n", rots


def rotated_instance_constraints_deck():
    """A part P of two C3D8 unit cubes held at their bases, constraints in its axes: cube A's top
    face coupled by *COUPLING, *DISTRIBUTING of DOFs 1-5 (the moment about the part's z
    released) to node 9 above it, cube B's top face by *COUPLING, *KINEMATIC to node 19 above
    it, and a HINGE connector from 9 to 19, free about the part's x — node 9's rotation about z
    is held by the hinge alone.  Instanced as ROTATED_INSTANCES; node 9 loaded by R (0.3, -0.2,
    0.5) and the moment R (0.1, 0.2, 0.15).  Returns the deck and {instance: R}."""
    corners = ((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1))
    nodes = [f"{o + i + 1}, {x0 + x}., {y}., {z}." for o, x0 in ((0, 0), (10, 2))
             for i, (x, y, z) in enumerate(corners)]
    part = ("*PART, NAME=P\n*NODE\n" + "\n".join(nodes) + "\n9, 0.5, 0.5, 1.5\n19, 2.5, 0.5, 1.5\n"
            "*ELEMENT, TYPE=C3D8, ELSET=CA\n1, 1, 2, 3, 4, 5, 6, 7, 8\n"
            "*ELEMENT, TYPE=C3D8, ELSET=CB\n2, 11, 12, 13, 14, 15, 16, 17, 18\n"
            "*ELEMENT, TYPE=CONN3D2, ELSET=CN\n5, 9, 19\n*NSET, NSET=BASE\n1, 2, 3, 4, 11, 12, 13, 14\n"
            "*NSET, NSET=BODY\n5, 6, 7, 8, 9, 15, 16, 17, 18, 19\n*SOLID SECTION, ELSET=CA, MATERIAL=M\n"
            "*SOLID SECTION, ELSET=CB, MATERIAL=M\n*CONNECTOR SECTION, ELSET=CN\nHINGE,\n"
            "*SURFACE, NAME=TA\nCA, S2\n*SURFACE, NAME=TB\nCB, S2\n"
            "*COUPLING, CONSTRAINT NAME=CD, REF NODE=9, SURFACE=TA\n*DISTRIBUTING\n1, 5\n"
            "*COUPLING, CONSTRAINT NAME=CK, REF NODE=19, SURFACE=TB\n*KINEMATIC\n*END PART\n")
    asm, rots = _instances_of_p()
    deck = part + asm + "*MATERIAL, NAME=M\n*ELASTIC\n1000., 0.3\n*STEP\n*STATIC\n*BOUNDARY\n"
    deck += "".join(f"{n}.BASE, 1, 3\n" for n in rots) + "*CLOAD\n"
    for name, r in rots.items():
        deck += "".join(f"{name}.9, {k + 1}, {x:.12g}\n" for k, x in
                        enumerate((*r((0.3, -0.2, 0.5)), *r((0.1, 0.2, 0.15)))))
    deck += "".join(f"*NODE PRINT, NSET={n}.BODY, GLOBAL=YES\nU\n" for n in rots)
    return deck + "*END STEP\n", rots


def turned_cantilever_deck(typ="B31", ne=4, proc="STATIC", knot=False):
    """Clamped RECT 0.2 x 0.3 cantilevers of length 1 (E 1000, nu 0.3): twin 0 along z with
    n1 = x, twin 1 the same turned by R, 40 deg about (1, 2, 3), 5 to the side — once with a tip
    force (0.3, -0.2, 0.5), once with a tip moment (0.1, 0.2, 0.15), turned by R on twin 1.
    ``proc`` FREQUENCY: one unloaded pair, density 1, eight modes.  ``knot``: one pair loaded by
    both, an *EQUATION between two free nodes (cards that tie DOFs: the converter gives the
    turned nodes knot beams) and a force-free dummy B31 at the unturned twin's root and tip,
    which ccx makes knots too.  Returns the deck, R and {case: (twin 0, twin 1 tip)}."""
    e = _unit((1.0, 2.0, 3.0))
    rot = lambda v: _rotate(v, e, math.radians(40.0))           # noqa: E731
    per = 2 if typ.startswith("B32") else 1
    nn = ne * per + 1
    cases = {"force+moment": (0, 1)} if knot else {"modes": (0, 1)} if proc == "FREQUENCY" else \
        {"force": (0, 1), "moment": (2, 3)}
    nodes, elems, secs, tips = ["*NODE"], [], [], {}
    for case, pair in cases.items():
        for m in pair:
            r = rot if m % 2 else (lambda v: tuple(v))
            nodes += [f"{1000 * m + i + 1}, " + ", ".join(f"{x + 5 * m:.15g}" for x in r((0.0, 0.0, i / (nn - 1))))
                      for i in range(nn)]
            elems += [f"*ELEMENT, TYPE={typ}, ELSET=E{m}"] + \
                [f"{1000 * m + k + 1}, " + ", ".join(str(1000 * m + per * k + j + 1) for j in range(per + 1))
                 for k in range(ne)]
            secs += [f"*BEAM SECTION, ELSET=E{m}, MATERIAL=M, SECTION=RECT", "0.2, 0.3",
                     ", ".join(f"{x:.15g}" for x in r((1.0, 0.0, 0.0)))]
        tips[case] = tuple(1000 * m + nn for m in pair)
    ms = [m for pair in cases.values() for m in pair]
    deck = nodes + elems + ["*MATERIAL, NAME=M", "*ELASTIC", "1000., 0.3"] + \
        (["*DENSITY", "1."] if proc == "FREQUENCY" else []) + secs + \
        ["*NSET, NSET=ROOTS", ", ".join(str(1000 * m + 1) for m in ms),
         "*NSET, NSET=TIPS", ", ".join(str(1000 * m + nn) for m in ms)]
    if knot:
        # (a knot's axial stiffness follows its force-free beams' E and size — a soft thin dummy is
        # 1e-5 of the tip motion apart — so the dummy is like the converter's knot beams: the
        # deck's E, about 1 % of the model's size, along (1, 1, 1))
        deck += ["*NODE", "9001, 0.0935, 0.0935, 0.0935", "9002, 0.0935, 0.0935, 1.0935", "9101, 9., 9., 9.",
                 "9102, 9., 9., 10.", "*ELEMENT, TYPE=B31, ELSET=DUMMY", "9001, 1, 9001", f"9002, {nn}, 9002",
                 "*MATERIAL, NAME=DM", "*ELASTIC", "1000., 0.", "*DENSITY", "0.",
                 "*BEAM SECTION, ELSET=DUMMY, MATERIAL=DM, SECTION=RECT", "0.08, 0.08", "1., -1., 0.",
                 "*EQUATION", "2", "9101, 1, 1., 9102, 1, -1."]
    deck += ["*STEP", "*FREQUENCY" if proc == "FREQUENCY" else "*STATIC"] + (["8"] if proc == "FREQUENCY" else []) + \
        ["*BOUNDARY", "ROOTS, ENCASTRE"]
    if proc != "FREQUENCY":
        deck.append("*CLOAD")
        for case, pair in cases.items():
            for m in pair:
                r = rot if m % 2 else (lambda v: tuple(v))
                loads = [(1, (0.3, -0.2, 0.5))] * ("force" in case) + [(4, (0.1, 0.2, 0.15))] * ("moment" in case)
                deck += [f"{1000 * m + nn}, {d + k}, {x:.12g}" for d, v in loads for k, x in enumerate(r(v))]
        deck += ["*NODE PRINT, NSET=TIPS", "U"]
    return "\n".join(deck + ["*END STEP"]) + "\n", rot, tips


def dashpot1_ground_deck():
    """Free point masses (1 each) on dashpots c = 10 in a *DYNAMIC, NLGEOM step of 2 s, each
    pushed by 1 along its dashpot and by 1 across it: DASHPOT1s on node 1's DOF 1 of an
    ORIENTATION 30 degrees about z, on node 2's DOF 2 of its *TRANSFORM 45 degrees about z (its
    loads local), on node 3's global DOF 3; and a DASHPOT2 on DOF 1 of nodes 4 (held)
    and 5 along x, node 5 held across.  Along a dashpot a mass moves u = t/10 - (1 - e^(-10 t))
    / 100 (0.19 at t = 2), across it t^2 / 2 (2, as far as the converter's ground node is).
    Printed in global components."""
    c, s, r = math.cos(math.radians(30)), math.sin(math.radians(30)), math.sqrt(0.5)
    return ("*NODE\n1, 0., 0., 0.\n2, 1., 0., 0.\n3, 0., 1., 0.\n4, 1., 1., 0.\n5, 2., 1., 0.\n"
            "*ELEMENT, TYPE=MASS, ELSET=EM\n11, 1\n12, 2\n13, 3\n15, 5\n*MASS, ELSET=EM\n1.\n"
            f"*ORIENTATION, NAME=OR\n{c:.15f}, {s:.15f}, 0., {-s:.15f}, {c:.15f}, 0.\n"
            f"*NSET, NSET=N2\n2\n*TRANSFORM, NSET=N2\n{r:.15f}, {r:.15f}, 0., {-r:.15f}, {r:.15f}, 0.\n"
            "*ELEMENT, TYPE=DASHPOT1, ELSET=D1\n21, 1\n*ELEMENT, TYPE=DASHPOT1, ELSET=D2\n22, 2\n"
            "*ELEMENT, TYPE=DASHPOT1, ELSET=D3\n23, 3\n*ELEMENT, TYPE=DASHPOT2, ELSET=D5\n25, 4, 5\n"
            "*DASHPOT, ELSET=D1, ORIENTATION=OR\n1\n10.\n*DASHPOT, ELSET=D2\n2\n10.\n"
            "*DASHPOT, ELSET=D3\n3\n10.\n*DASHPOT, ELSET=D5\n1, 1\n10.\n"
            "*NSET, NSET=PROBE\n1, 2, 3, 5\n*BOUNDARY\n4, 1, 3\n5, 2, 3\n"
            "*STEP, NLGEOM, INC=1000\n*DYNAMIC, DIRECT\n0.01, 2.\n*CLOAD\n"
            f"1, 1, {c:.15f}\n1, 2, {s:.15f}\n1, 3, 1.\n2, 2, 1.\n2, 1, 1.\n3, 3, 1.\n3, 1, 1.\n5, 1, 1.\n"
            "*NODE PRINT, NSET=PROBE, GLOBAL=YES, FREQUENCY=200\nU\n*END STEP\n")


def dashpot2_dofs_deck():
    """Two DASHPOT2s, c = 10, between unit masses, *DYNAMIC NLGEOM 2 s: (a) nodes 1 -> 2,
    ORIENTATION OR (30 degrees about z), DOFs 1, 2: node 1 pushed by 1 along OR axis 1 and by 1
    across it (along OR axis 2 and z); node 2 (its *TRANSFORM the OR axes, held in its local
    1, 3) by 0.5 along OR axis 2.  (b) nodes 3 -> 4, no ORIENTATION, DOFs 2, 3: node 3
    (*TRANSFORM 45 degrees about z) pushed by 1 along its local 2 and by 1 along its local 1
    and 3 (across); node 4 (held in x, y) by 0.5 along z.  Along the dashpot DOFs x1 + x2 =
    1.5 t^2 / 2 and x1 - x2 = w (t - (1 - e^(-20 t)) / 20), w = 0.5 / 20 (dashpot2_dofs_answer);
    across t^2 / 2.  Printed in global components."""
    c, s, r = math.cos(math.radians(30)), math.sin(math.radians(30)), math.sqrt(0.5)
    return ("*NODE\n1, 0., 0., 0.\n2, 1., 0., 0.\n3, 0., 1., 0.\n4, 1., 1., 0.\n"
            "*ELEMENT, TYPE=MASS, ELSET=EM\n11, 1\n12, 2\n13, 3\n14, 4\n*MASS, ELSET=EM\n1.\n"
            f"*ORIENTATION, NAME=OR\n{c:.15f}, {s:.15f}, 0., {-s:.15f}, {c:.15f}, 0.\n"
            f"*NSET, NSET=N2\n2\n*TRANSFORM, NSET=N2\n{c:.15f}, {s:.15f}, 0., {-s:.15f}, {c:.15f}, 0.\n"
            f"*NSET, NSET=N3\n3\n*TRANSFORM, NSET=N3\n{r:.15f}, {r:.15f}, 0., {-r:.15f}, {r:.15f}, 0.\n"
            "*ELEMENT, TYPE=DASHPOT2, ELSET=DA\n21, 1, 2\n*ELEMENT, TYPE=DASHPOT2, ELSET=DB\n22, 3, 4\n"
            "*DASHPOT, ELSET=DA, ORIENTATION=OR\n1, 2\n10.\n*DASHPOT, ELSET=DB\n2, 3\n10.\n"
            "*NSET, NSET=PROBE\n1, 2, 3, 4\n*BOUNDARY\n2, 1, 1\n2, 3, 3\n4, 1, 2\n"
            "*STEP, NLGEOM, INC=1000\n*DYNAMIC, DIRECT\n0.01, 2.\n*CLOAD\n"
            f"1, 1, {c - s:.15f}\n1, 2, {s + c:.15f}\n1, 3, 1.\n2, 2, 0.5\n3, 2, 1.\n3, 1, 1.\n3, 3, 1.\n"
            "4, 3, 0.5\n*NODE PRINT, NSET=PROBE, GLOBAL=YES, FREQUENCY=200\nU\n*END STEP\n")


def dashpot2_dofs_answer(t=2.0):
    """(x1, x2, across) of dashpot2_dofs_deck at time ``t``: m x1'' + c (x1' - x2') = 1,
    m x2'' - c (x1' - x2') = 0.5 (m = 1, c = 10)."""
    w = 0.5 / 20.0
    diff, total = w * (t - (1.0 - math.exp(-20.0 * t)) / 20.0), 1.5 * t * t / 2.0
    return (total + diff) / 2.0, (total - diff) / 2.0, t * t / 2.0


ANISO_MASS_AXES = ((1.0, 2.0, 2.0), (-2.0, 2.0, -1.0))   # ORIENTATION a, b: v1 = a / 3, v2 = b / 3


def anisotropic_mass_deck(kind):
    """Point masses 1, 4, 9 along the axes of ORIENTATION AX (v1 = (1, 2, 2) / 3, v2 = (-2, 2,
    -1) / 3).  "freq": nodes 1 and 3 on three SPRING1s each along x, y, z, of 36 and 72:
    *FREQUENCY, omega^2 = 4, 8, 9, 18, 36 (and 72; ccx returns fewer modes than the model has
    DOFs).  "dyn": node 1 free (on a 1e-12 spring: ccx 2.23 moves no node that is on MASS
    elements only), a force (1, 1, 1) for 1 s, *DYNAMIC NLGEOM: u = M^-1 F t^2 / 2."""
    a, b = ANISO_MASS_AXES
    d = ("*NODE\n1, 0., 0., 0.\n2, 1., 0., 0.\n3, 0., 1., 0.\n*ELEMENT, TYPE=MASS, ELSET=EM\n1, 1\n"
         + ("3, 3\n" if kind == "freq" else "") +
         f"*ORIENTATION, NAME=AX\n{a[0]}, {a[1]}, {a[2]}, {b[0]}, {b[1]}, {b[2]}\n"
         "*MASS, ELSET=EM, TYPE=ANISOTROPIC, ORIENTATION=AX\n1., 4., 9.\n*NSET, NSET=PROBE\n1\n")
    if kind == "freq":
        return d + "".join(f"*ELEMENT, TYPE=SPRING1, ELSET=K{n}{k}\n{30 + 3 * n + k}, {n}\n*SPRING, "
                           f"ELSET=K{n}{k}\n{k}\n{18 * (n + 1)}.\n" for n in (1, 3) for k in (1, 2, 3)) + \
            "*BOUNDARY\n2, 1, 3\n*STEP\n*FREQUENCY\n5\n*END STEP\n"
    return d + ("*ELEMENT, TYPE=SPRINGA, ELSET=KA\n31, 1, 2\n*SPRING, ELSET=KA\n\n1.e-12\n*BOUNDARY\n2, 1, 3\n"
                "*STEP, NLGEOM, INC=1000\n*DYNAMIC, DIRECT\n0.01, 1.\n*CLOAD\n1, 1, 1.\n1, 2, 1.\n1, 3, 1.\n"
                "*NODE PRINT, NSET=PROBE, FREQUENCY=100\nU\n*END STEP\n")


def anisotropic_mass_answer(t=1.0):
    """u of anisotropic_mass_deck("dyn") at time ``t``: M^-1 F t^2 / 2, M^-1 = sum v_i v_i^T / M_ii."""
    v1, v2 = (tuple(x / 3.0 for x in ax) for ax in ANISO_MASS_AXES)
    vs, m = (v1, v2, _cross(v1, v2)), (1.0, 4.0, 9.0)
    return tuple(sum(sum(vs[i]) / m[i] * vs[i][j] for i in range(3)) * t * t / 2.0 for j in range(3))


def spring_transform_deck():
    """SPRING1 / SPRING2 at nodes with a *TRANSFORM, *STATIC NLGEOM: node 1 (30 degrees about z)
    on a SPRING1 of 100 on its DOF 1, held in its local 2, 3 and loaded 1 along its local 1:
    0.01 along it.  Node 2 (45 degrees about z) to node 3 (30 degrees about x) by a SPRING2 of
    50 on DOFs 2, 3: node 3 held, its local DOF 3 moved 0.02; node 2 held in its local 1, 3 and
    loaded 1 along its local 2: 0.02 + 1/50 = 0.04 along it.  Printed in global components."""
    c, s, r = math.cos(math.radians(30)), math.sin(math.radians(30)), math.sqrt(0.5)
    return ("*NODE\n1, 0., 0., 0.\n2, 1., 0., 0.\n3, 2., 0., 0.\n*NSET, NSET=PROBE\n1, 2, 3\n"
            f"*NSET, NSET=T1\n1\n*TRANSFORM, NSET=T1\n{c:.15f}, {s:.15f}, 0., {-s:.15f}, {c:.15f}, 0.\n"
            f"*NSET, NSET=T2\n2\n*TRANSFORM, NSET=T2\n{r:.15f}, {r:.15f}, 0., {-r:.15f}, {r:.15f}, 0.\n"
            f"*NSET, NSET=T3\n3\n*TRANSFORM, NSET=T3\n1., 0., 0., 0., {c:.15f}, {s:.15f}\n"
            "*ELEMENT, TYPE=SPRING1, ELSET=K1\n1, 1\n*SPRING, ELSET=K1\n1\n100.\n"
            "*ELEMENT, TYPE=SPRING2, ELSET=K2\n2, 2, 3\n*SPRING, ELSET=K2\n2, 3\n50.\n"
            "*BOUNDARY\n1, 2, 3\n2, 1, 1\n2, 3, 3\n3, 1, 2\n*STEP, NLGEOM\n*STATIC\n*BOUNDARY\n3, 3, 3, 0.02\n"
            "*CLOAD\n1, 1, 1.\n2, 2, 1.\n*NODE PRINT, NSET=PROBE, GLOBAL=YES\nU\n*END STEP\n")


def spring_numbers_deck():
    """*SPRING constants Abaqus reads and ccx 2.23 stopped on: a SPRING1 of '100', a SPRINGA of
    '1e2' after a DOF line '2,' (Abaqus: a blank line), a SPRING2 of '50' on DOFs 1, 1, and a
    NONLINEAR SPRING1 '-200, -1 / 0, 0 / 200, 1', each pulled by 1: 0.01, 0.01, 0.02, 0.005."""
    return ("*NODE\n1, 0., 0., 0.\n2, -1., 1., 0.\n3, 0., 1., 0.\n4, 1., 1., 0.\n5, 2., 1., 0.\n6, 0., 2., 0.\n"
            "*NSET, NSET=PROBE\n1, 3, 5, 6\n*ELEMENT, TYPE=SPRING1, ELSET=K1\n1, 1\n*SPRING, ELSET=K1\n1\n100\n"
            "*ELEMENT, TYPE=SPRINGA, ELSET=KA\n2, 2, 3\n*SPRING, ELSET=KA\n2,\n1e2\n"
            "*ELEMENT, TYPE=SPRING2, ELSET=K2\n3, 4, 5\n*SPRING, ELSET=K2\n1, 1\n50\n"
            "*ELEMENT, TYPE=SPRING1, ELSET=KN\n4, 6\n*SPRING, ELSET=KN, NONLINEAR\n1\n-200, -1\n0, 0\n200, 1\n"
            "*BOUNDARY\n1, 2, 3\n2, 1, 3\n3, 2, 3\n4, 1, 3\n5, 2, 3\n6, 2, 3\n"
            "*STEP\n*STATIC\n*CLOAD\n1, 1, 1.\n3, 1, 1.\n5, 1, 1.\n6, 1, 1.\n*NODE PRINT, NSET=PROBE\nU\n*END STEP\n")


def connector_distributing_deck(form):
    """A 2 x 2 x 2 C3D8 cube (E 1000, nu 0.3) clamped at z = 0, its top face's nodes
    distributing-coupled to RP 9 at (0.5, 0.5, 1.5).  "conn": a BEAM connector from 9 to 19 at
    an arm (1, 0, 0), the force (0, 1, 0.5) at 19; "load": that force at 9 with the moment
    r x F = (0, -0.5, 1).  Abaqus: the same solution."""
    ids, lines = {}, ["*NODE"]
    for k in range(3):
        for j in range(3):
            for i in range(3):
                ids[(i, j, k)] = 101 + i + 3 * j + 9 * k
                lines.append(f"{ids[(i, j, k)]}, {0.5 * i}, {0.5 * j}, {0.5 * k}")
    lines += ["9, 0.5, 0.5, 1.5", "19, 1.5, 0.5, 1.5", "*ELEMENT, TYPE=C3D8, ELSET=CUBE"]
    for e, (i, j, k) in enumerate(((i, j, k) for k in range(2) for j in range(2) for i in range(2)), 1):
        lines.append(f"{e}, " + ", ".join(str(ids[(i + a, j + b, k + z)])
                                          for z in (0, 1) for a, b in ((0, 0), (1, 0), (1, 1), (0, 1))))
    lines += ["*NSET, NSET=BASE", ", ".join(str(v) for (i, j, k), v in ids.items() if k == 0),
              "*NSET, NSET=TOP", ", ".join(str(v) for (i, j, k), v in ids.items() if k == 2),
              "*NSET, NSET=PROBE", "9, 119, 125, 127"]
    d = "\n".join(lines) + ("\n*MATERIAL, NAME=M\n*ELASTIC\n1000., 0.3\n*SOLID SECTION, ELSET=CUBE, MATERIAL=M\n"
                            "*SURFACE, NAME=TS, TYPE=NODE\nTOP\n*COUPLING, CONSTRAINT NAME=CD, REF NODE=9, "
                            "SURFACE=TS\n*DISTRIBUTING\n")
    if form == "conn":
        d += "*ELEMENT, TYPE=CONN3D2, ELSET=CN\n50, 9, 19\n*CONNECTOR SECTION, ELSET=CN\nBEAM,\n"
    d += "*BOUNDARY\nBASE, 1, 3\n*STEP\n*STATIC\n*CLOAD\n"
    d += "19, 2, 1.\n19, 3, 0.5\n" if form == "conn" else "9, 2, 1.\n9, 3, 0.5\n9, 5, -0.5\n9, 6, 1.\n"
    return d + "*NODE PRINT, NSET=PROBE\nU\n*END STEP\n"


def buckle_gravity_deck(preload="grav", static=False, buckle=True, pert=True, n=2, m=20, load=1e5, nev=2):
    """A C3D8 column, 0.1 x 0.1 x 2 in n x n x m elements (E 210e9, nu 0.3, density 7850),
    clamped at its base, loaded ``load`` down at its top centre (node set TIP) in a *STEP,
    PERTURBATION *BUCKLE step asking for ``nev`` factors.  ``preload`` before it, in a static step: "grav" (gravity
    9810: its weight 1.54e6), "nodal" (the same as nodal forces, a brick's weight / 8 at each
    of its nodes, which is exact on bricks), "" (none), or "self" (gravity in the *BUCKLE step
    itself, no static step).  ``static``: a static step after it pulling TIP sideways by
    1e3; ``buckle``: False leaves the *BUCKLE step out; ``pert``: False writes a plain *STEP."""
    h, dz, rho_g = 0.1 / n, 2.0 / m, 7850.0 * 9810.0
    ids = {(i, j, k): 1 + i + (n + 1) * (j + (n + 1) * k)
           for k in range(m + 1) for j in range(n + 1) for i in range(n + 1)}
    elems = [[ids[(i + a, j + b, k + z)] for z in (0, 1) for a, b in ((0, 0), (1, 0), (1, 1), (0, 1))]
             for k in range(m) for j in range(n) for i in range(n)]
    share: dict = {}
    for c in elems:
        for v in c:
            share[v] = share.get(v, 0.0) + rho_g * h * h * dz / 8.0
    base = [v for (i, j, k), v in ids.items() if k == 0]
    lines = (["*NODE"] + [f"{v}, {i * h:.6g}, {j * h:.6g}, {k * dz:.6g}" for (i, j, k), v in ids.items()]
             + ["*ELEMENT, TYPE=C3D8, ELSET=EALL"]
             + [f"{e}, " + ", ".join(map(str, c)) for e, c in enumerate(elems, 1)]
             + ["*NSET, NSET=BASE"] + [", ".join(map(str, base[s:s + 16])) for s in range(0, len(base), 16)]
             + ["*NSET, NSET=TIP", str(ids[(n // 2, n // 2, m)]), "*MATERIAL, NAME=STEEL", "*ELASTIC",
                "210.e9, 0.3", "*DENSITY", "7850.", "*SOLID SECTION, ELSET=EALL, MATERIAL=STEEL",
                "*BOUNDARY", "BASE, 1, 3"])
    grav = ["*DLOAD", "EALL, GRAV, 9810., 0., 0., -1."]
    if preload in ("grav", "nodal"):
        lines += ["*STEP", "*STATIC"] + (grav if preload == "grav" else
                                         ["*CLOAD"] + [f"{v}, 3, {-f:.12g}" for v, f in share.items()])
        lines += ["*END STEP"]
    if buckle:
        lines += ["*STEP, PERTURBATION" if pert else "*STEP", "*BUCKLE", str(nev)] + \
            (grav if preload == "self" else []) + \
            ["*CLOAD", f"TIP, 3, {-load:.12g}", "*END STEP"]
    if static:
        lines += ["*STEP", "*STATIC", "*CLOAD", "TIP, 1, 1.e3", "*NODE PRINT, NSET=TIP", "U",
                  "*END STEP"]
    return "\n".join(lines) + "\n"


def buckle_displacement_deck(case, force=0.0, d=-1e-4, n=2, m=20):
    """A C3D20R column, 0.1 x 0.1 x 2 in n x n x m elements (E 210e9, nu 0.3), clamped at its
    base, its top nodes (TOP) held in z: fixed-guided, Euler load pi^2 EI / L^2.  ``case``:
    "own" a *STEP, PERTURBATION *BUCKLE step pushing TOP down by ``d``; "static" a static
    step doing so that prints TOP's reaction; "tied" TOP tied in z by *EQUATION to its first
    node, a *STEP, PERTURBATION *BUCKLE step loading that node by ``force``; "preload" the
    static step pushing TOP down, then a *STEP, PERTURBATION *BUCKLE step loaded by 1e5 down
    on the mid-height nodes (MID); "tied_preload" the same with the tie, the preload the
    force ``force`` (0: none) and the tie's node held in z in the buckle step; "pushed" the
    static step pushing TOP down, then a *STEP, PERTURBATION *BUCKLE step pushing it so."""
    h, dz = 0.1 / n / 2, 2.0 / m / 2                 # half steps
    ids = {}
    for k in range(2 * m + 1):
        for j in range(2 * n + 1):
            for i in range(2 * n + 1):
                if i % 2 + j % 2 + k % 2 <= 1:
                    ids[(i, j, k)] = len(ids) + 1
    elems = []
    for k in range(0, 2 * m, 2):
        for j in range(0, 2 * n, 2):
            for i in range(0, 2 * n, 2):
                bot = [(i + a, j + b, k) for a, b in ((0, 0), (2, 0), (2, 2), (0, 2))]
                top = [(x, y, z + 2) for x, y, z in bot]
                mid = [tuple((p + q) // 2 for p, q in zip(u, v)) for u, v in
                       [(bot[s], bot[(s + 1) % 4]) for s in range(4)] +
                       [(top[s], top[(s + 1) % 4]) for s in range(4)] + list(zip(bot, top))]
                elems.append([ids[p] for p in bot + top + mid])
    tops = [v for (i, j, k), v in ids.items() if k == 2 * m]
    ring = [v for (i, j, k), v in ids.items() if k == m]

    def nset(name, vs):
        return [f"*Nset, nset={name}"] + [", ".join(map(str, vs[s:s + 16])) for s in range(0, len(vs), 16)]
    lines = (["*Node"] + [f"{v}, {i * h:.9g}, {j * h:.9g}, {k * dz:.9g}" for (i, j, k), v in ids.items()]
             + ["*Element, type=C3D20R, elset=EALL"]
             + [f"{e}, " + ", ".join(map(str, c[:15])) + ",\n" + ", ".join(map(str, c[15:]))
                for e, c in enumerate(elems, 1)]
             + nset("BASE", [v for (i, j, k), v in ids.items() if k == 0]) + nset("TOP", tops)
             + nset("MID", ring) + ["*Material, name=STEEL", "*Elastic", "210.e9, 0.3",
                                   "*Solid Section, elset=EALL, material=STEEL", "*Boundary", "BASE, 1, 3"])
    if case.startswith("tied"):
        lines += ["*Equation"] + [x for v in tops[1:] for x in ("2", f"{v}, 3, 1., {tops[0]}, 3, -1.")]
    push = ["*Boundary", f"TOP, 3, 3, {d}"]
    buckle = ["*Step, perturbation", "*Buckle", "3"]
    ring_load = ["*Cload"] + [f"{v}, 3, {-1e5 / len(ring):.15g}" for v in ring]
    if case == "own":
        lines += buckle + push
    elif case == "static":
        lines += ["*Step", "*Static"] + push + ["*Node Print, nset=TOP, totals=only", "RF"]
    elif case == "tied":
        lines += buckle + ["*Cload", f"{tops[0]}, 3, {force!r}"]
    elif case == "preload":
        lines += ["*Step", "*Static"] + push + ["*End Step"] + buckle + ring_load
    elif case == "pushed":
        lines += ["*Step", "*Static"] + push + ["*End Step"] + buckle + push
    elif case == "tied_preload":
        lines += ["*Step", "*Static"] + (["*Cload", f"{tops[0]}, 3, {force!r}"] if force else []) + \
            ["*End Step"] + buckle + ["*Boundary", f"{tops[0]}, 3, 3, 0."] + ring_load
    return "\n".join(lines + ["*End Step"]) + "\n"


def frequency_preload_deck(nlgeom=False, pert=False, preload="grav"):
    """buckle_gravity_deck's column under ``preload`` in a static step (``nlgeom``: with
    NLGEOM), then a *FREQUENCY step for 4 modes, ``pert``: on a *STEP, PERTURBATION."""
    deck = buckle_gravity_deck(preload, buckle=False)
    if nlgeom:
        deck = deck.replace("*STEP\n*STATIC", "*STEP, NLGEOM\n*STATIC")
    return deck + "\n".join(["*STEP, PERTURBATION" if pert else "*STEP", "*FREQUENCY", "4",
                             "*END STEP"]) + "\n"


def surface_heat_deck(kind, out="film", op_new=False):
    """A bar of four unit elements (DC3D8 along x; DC2D4 of thickness 1 along x; DCAX4 along
    z at radii 1-2: ``kind``), conductivity 2, in steady heat transfer: *DSFLUX of 100 into
    the bar's first end (face S6 / edge S4 / edge S1) and, at its other end (S4 / S2 / S3),
    *SFILM to 20 with h = 10 (``out`` "film") or *SRADIATE to 20 with emissivity 0.5
    ("radiate"); the sides are insulated, so the temperature is linear along the bar with
    slope -50.  ``op_new``: a second step whose empty *DSFLUX, OP=NEW and *SFILM / *SRADIATE,
    OP=NEW remove both, with the first end held at 100: the bar at 100 throughout."""
    lines = ["*HEADING", f"Bar, *DSFLUX in, *S{'FILM' if out == 'film' else 'RADIATE'} out",
             "*NODE, NSET=ALLN"]
    nid = {}
    for k in range(1 if kind != "dc3d8" else 2):
        for j in range(2):
            for i in range(5):
                nid[(i, j, k)] = 1 + i + 5 * j + 10 * k
                xyz = (1.0 + j, float(i), 0.0) if kind == "dcax4" else (float(i), float(j), float(k))
                lines.append(f"{nid[(i, j, k)]}, " + ", ".join(str(x) for x in xyz))
    if kind == "dc3d8":
        lines.append("*ELEMENT, TYPE=DC3D8, ELSET=BAR")
        lines += [f"{i + 1}, {nid[(i, 0, 0)]}, {nid[(i + 1, 0, 0)]}, {nid[(i + 1, 1, 0)]}, "
                  f"{nid[(i, 1, 0)]}, {nid[(i, 0, 1)]}, {nid[(i + 1, 0, 1)]}, {nid[(i + 1, 1, 1)]}, "
                  f"{nid[(i, 1, 1)]}" for i in range(4)]
        faces = ("S6", "S4")
    elif kind == "dc2d4":
        lines.append("*ELEMENT, TYPE=DC2D4, ELSET=BAR")
        lines += [f"{i + 1}, {nid[(i, 0, 0)]}, {nid[(i + 1, 0, 0)]}, {nid[(i + 1, 1, 0)]}, "
                  f"{nid[(i, 1, 0)]}" for i in range(4)]
        faces = ("S4", "S2")
    else:                                   # counterclockwise in (r, z): S1 at z_i, S3 at z_i+1
        lines.append("*ELEMENT, TYPE=DCAX4, ELSET=BAR")
        lines += [f"{i + 1}, {nid[(i, 0, 0)]}, {nid[(i, 1, 0)]}, {nid[(i + 1, 1, 0)]}, "
                  f"{nid[(i + 1, 0, 0)]}" for i in range(4)]
        faces = ("S1", "S3")
    lines += ["*ELSET, ELSET=FIRST", "1", "*ELSET, ELSET=LAST", "4",
              "*NSET, NSET=START", ", ".join(str(n) for (i, _, _), n in nid.items() if i == 0),
              "*SURFACE, NAME=HOT", f"FIRST, {faces[0]}", "*SURFACE, NAME=COLD", f"LAST, {faces[1]}",
              "*SOLID SECTION, ELSET=BAR, MATERIAL=M", "1.", "*MATERIAL, NAME=M",
              "*CONDUCTIVITY", "2."]
    card = "SFILM" if out == "film" else "SRADIATE"
    if out == "radiate":
        lines += ["*PHYSICAL CONSTANTS, ABSOLUTE ZERO=-273.15, STEFAN BOLTZMANN=5.67E-8"]
    lines += ["*STEP", "*HEAT TRANSFER, STEADY STATE", "1., 1.", "*DSFLUX", "HOT, S, 100.",
              f"*{card}", "COLD, F, 20., 10." if out == "film" else "COLD, R, 20., 0.5",
              "*NODE PRINT, NSET=ALLN", "NT", "*END STEP"]
    if op_new:
        lines += ["*STEP", "*HEAT TRANSFER, STEADY STATE", "1., 1.", "*DSFLUX, OP=NEW",
                  f"*{card}, OP=NEW", "*BOUNDARY", "START, 11, 11, 100.", "*NODE PRINT, NSET=ALLN",
                  "NT", "*END STEP"]
    return "\n".join(lines) + "\n"


def member_mass_frequency_deck(mpc):
    """A rigid body held by an x spring (k 1000) and a y spring (4000) from its reference node
    1, which BCs keep from moving otherwise; its only mass, 2.5, sits on member node 4, which
    is in no other element (ccx 2.23's *FREQUENCY stopped on it: 'add_bo_st'): the body as a
    *RIGID BODY, or with ``mpc`` as an *MPC BEAM line.  Modes sqrt(k / m) / (2 pi)."""
    lines = ["*HEADING", "Spring-held rigid body, its mass on a member node in no other element",
             "*NODE", "1, 0., 0., 0.", "4, 1., 1., 0.", "11, -1., 0., 0.", "12, 0., -1., 0.",
             "*ELEMENT, TYPE=SPRINGA, ELSET=SX", "101, 1, 11", "*SPRING, ELSET=SX", "", "1000.",
             "*ELEMENT, TYPE=SPRINGA, ELSET=SY", "102, 1, 12", "*SPRING, ELSET=SY", "", "4000.",
             "*ELEMENT, TYPE=MASS, ELSET=M4", "201, 4", "*MASS, ELSET=M4", "2.5"]
    if mpc:
        lines += ["*MPC", "BEAM, 4, 1"]
    else:
        lines += ["*NSET, NSET=B", "4", "*RIGID BODY, REF NODE=1, TIE NSET=B"]
    lines += ["*BOUNDARY", "11, 1, 3", "12, 1, 3", "1, 3, 6", "*STEP", "*FREQUENCY", "1",
              "*END STEP"]
    return "\n".join(lines) + "\n"


def frequency_heated_deck(heat=True, t0=20.0, hyper=False):
    """buckle_gravity_deck's column with E 210e9 at 20 and 105e9 at 120 (rows), at the initial
    temperature ``t0``; ``heat``: a static step raising it to 120 (no load, no expansion: no
    stress), then a plain *FREQUENCY step for 4 modes.  ``hyper``: a Neo-Hooke material
    instead, C10 0.5e6 at 20 and 0.125e6 at 120 (D1 1e-7)."""
    deck = buckle_gravity_deck("", buckle=False).replace(
        "*ELASTIC\n210.e9, 0.3\n", "*HYPERELASTIC, NEO HOOKE\n0.5e6, 1.e-7, 20.\n0.125e6, 1.e-7, 120.\n"
        if hyper else "*ELASTIC\n210.e9, 0.3, 20.\n105.e9, 0.3, 120.\n")
    lines = ["*NSET, NSET=NALL, GENERATE", f"1, {3 * 3 * 21}, 1",
             "*INITIAL CONDITIONS, TYPE=TEMPERATURE", f"NALL, {t0:g}"]
    if heat:
        lines += ["*STEP", "*STATIC", "*TEMPERATURE", "NALL, 120.", "*END STEP"]
    return deck + "\n".join(lines + ["*STEP", "*FREQUENCY", "4", "*END STEP"]) + "\n"


def hyperfoam_deck(case, foam=True):
    """*HYPERFOAM (no N: N=1) mu1 2e6, alpha1 2, nu1 0.1, or (``foam`` False) *ELASTIC at its
    small-strain moduli (E 2 mu (1 + nu) = 4.4e6, nu 0.1): ``case`` "frequency" or "buckle"
    buckle_gravity_deck's column (4 modes; 2 factors under 0.01 down at TIP); "cube" a unit C3D8
    cube stretched to 0.8 along x (NLGEOM), its x = 0 face held in x, its sides free."""
    mat = "*HYPERFOAM\n2.e6, 2., 0.1\n" if foam else "*ELASTIC\n4.4e6, 0.1\n"
    if case == "cube":
        return ("*NODE\n1, 0, 0, 0\n2, 1, 0, 0\n3, 1, 1, 0\n4, 0, 1, 0\n5, 0, 0, 1\n6, 1, 0, 1\n"
                "7, 1, 1, 1\n8, 0, 1, 1\n*ELEMENT, TYPE=C3D8, ELSET=E\n1, 1, 2, 3, 4, 5, 6, 7, 8\n"
                "*NSET, NSET=X0\n1, 4, 5, 8\n*NSET, NSET=X1\n2, 3, 6, 7\n*MATERIAL, NAME=FOAM\n" + mat +
                "*SOLID SECTION, ELSET=E, MATERIAL=FOAM\n*BOUNDARY\nX0, 1, 1\n1, 2, 3\n4, 3, 3\n"
                "2, 3, 3\n*STEP, NLGEOM\n*STATIC\n0.1, 1.\n*BOUNDARY\nX1, 1, 1, -0.2\n"
                "*NODE PRINT, NSET=X1, TOTALS=YES\nRF\n*NODE PRINT, NSET=X1\nU\n*END STEP\n")
    deck = buckle_gravity_deck("", buckle=case == "buckle", load=0.01)
    deck = deck.replace("*ELASTIC\n210.e9, 0.3\n", mat)
    return deck + ("*STEP\n*FREQUENCY\n4\n*END STEP\n" if case == "frequency" else "")


def frequency_contact_deck(case, n=2, m=20, gap=0.0, pair="", head="", master="solid", stresses=False):
    """buckle_gravity_deck's column with a fixed C3D8 plate resting on its top face (a
    frictionless *CONTACT PAIR, Abaqus' default HARD contact), and a plain *FREQUENCY step for
    4 modes: ``case`` "first" (the first step), "after" (after a static step that loads
    nothing); "held" no plate, the top face held vertically instead (the closed frictionless
    contact Abaqus' frequency step freezes, without a penalty); "free" no plate.  ``gap``: the
    plate that far above the top (negative: overclosed), the static step then printing TIP's
    U; ``pair``: more *CONTACT PAIR parameters; ``head``: more *STEP parameters of the
    frequency step; ``master`` "shell": the plate an S4 one 0.01 thick, ``gap`` from its SNEG
    face; "rigid": an R3D4 one on a fixed reference node; ``stresses``: the static step also
    printing BASE's total reaction and the column's stresses."""
    deck = buckle_gravity_deck("", buckle=False, n=n, m=m)
    lines = ["*ELSET, ELSET=ETOP", ", ".join(map(str, range((m - 1) * n * n + 1, m * n * n + 1)))]
    if case in ("first", "after"):
        q = 4
        pid = lambda i, j, k: 10001 + i + (q + 1) * (j + (q + 1) * k)        # noqa: E731
        z0 = 2.0 + gap + (0.005 if master == "shell" else 0.0)
        lines += ["*NODE, NSET=PLATE"] + [f"{pid(i, j, k)}, {-0.05 + 0.2 * i / q:.6g}, "
                                          f"{-0.05 + 0.2 * j / q:.6g}, {z0 + 0.05 * k:.6g}"
                                          for k in ((0, 1) if master == "solid" else (0,))
                                          for j in range(q + 1) for i in range(q + 1)]
        quads = [[pid(i, j, 0), pid(i + 1, j, 0), pid(i + 1, j + 1, 0), pid(i, j + 1, 0)]
                 for j in range(q) for i in range(q)]
        if master == "solid":
            lines += ["*ELEMENT, TYPE=C3D8, ELSET=PL"] + [
                f"{1001 + k}, " + ", ".join(map(str, c + [x + (q + 1) ** 2 for x in c]))
                for k, c in enumerate(quads)]
            lines += ["*SOLID SECTION, ELSET=PL, MATERIAL=STEEL"]
        else:
            lines += [f"*ELEMENT, TYPE={'S4' if master == 'shell' else 'R3D4'}, ELSET=PL"] + [
                f"{1001 + k}, " + ", ".join(map(str, c)) for k, c in enumerate(quads)]
            lines += ["*SHELL SECTION, ELSET=PL, MATERIAL=STEEL", "0.01"] if master == "shell" else \
                ["*NODE, NSET=PLREF", "19999, 0.05, 0.05, 2.5", "*RIGID BODY, REF NODE=19999, ELSET=PL"]
        lines += ["*SURFACE, NAME=CTOP", "ETOP, S2",
                  "*SURFACE, NAME=PBOT", "PL, " + ("S1" if master == "solid" else "SNEG"),
                  "*SURFACE INTERACTION, NAME=SMOOTH",
                  "*CONTACT PAIR, INTERACTION=SMOOTH" + pair, "CTOP, PBOT", "*BOUNDARY",
                  {"solid": "PLATE, 1, 3", "shell": "PLATE, 1, 6"}.get(master, "PLREF, 1, 6")]
    elif case == "held":
        lines += ["*NSET, NSET=TOPN, ELSET=ETOP", "*BOUNDARY", "TOPN, 3, 3"]
    if case == "after":
        lines += ["*STEP", "*STATIC"] + (["*NODE PRINT, NSET=TIP", "U"] if gap else []) + \
            (["*NODE PRINT, NSET=BASE, TOTALS=ONLY", "RF", "*EL PRINT, ELSET=EALL", "S"] if stresses else []) + \
            ["*END STEP"]
    return deck + "\n".join(lines + ["*STEP" + head, "*FREQUENCY", "4", "*END STEP"]) + "\n"


def buckle_contact_deck(case, n=2, m=20):
    """buckle_gravity_deck's column (no preload) with a fixed C3D8 block touching each of the
    +x and +y faces of its top element layer (frictionless *CONTACT PAIRs, Abaqus' default
    HARD contact), *BUCKLE 2 factors: ``case`` "first" (the first step), "pushed" (after a
    static step pushing TIP 1e3 into both blocks, printing its U); "held" no blocks, those
    faces held normal to them instead (the closed contact Abaqus' buckling step freezes);
    "free" no blocks, "free_pushed" no blocks after that static step."""
    deck = buckle_gravity_deck("", buckle=False, n=n, m=m)
    top = range((m - 1) * n * n + 1, m * n * n + 1)
    ex = [e for e in top if (e - 1) % n == n - 1]               # the elements at x = 0.1
    ey = [e for e in top if (e - 1) // n % n == n - 1]          # ... at y = 0.1
    lines = ["*ELSET, ELSET=EX", ", ".join(map(str, ex)), "*ELSET, ELSET=EY", ", ".join(map(str, ey))]
    z0, z1 = 2.0 - 2.0 / m, 2.0
    if case in ("first", "pushed"):
        nid = iter(range(20001, 20100))
        lines += ["*NODE, NSET=BLOCKS"]
        elems = []
        for name, (x0, x1), (y0, y1) in (("BX", (0.1, 0.15), (-0.05, 0.15)),
                                         ("BY", (-0.05, 0.15), (0.1, 0.15))):
            c = []
            for z in (z0, z1):
                for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
                    c.append(next(nid))
                    lines.append(f"{c[-1]}, {x:.6g}, {y:.6g}, {z:.6g}")
            elems.append((name, c))
        for e, (name, c) in enumerate(elems, 2001):
            lines += [f"*ELEMENT, TYPE=C3D8, ELSET={name}", f"{e}, " + ", ".join(map(str, c))]
        lines += ["*SOLID SECTION, ELSET=BX, MATERIAL=STEEL", "*SOLID SECTION, ELSET=BY, MATERIAL=STEEL",
                  "*SURFACE, NAME=CX", "EX, S4", "*SURFACE, NAME=CY", "EY, S5",
                  "*SURFACE, NAME=MX", "BX, S6", "*SURFACE, NAME=MY", "BY, S3",
                  "*SURFACE INTERACTION, NAME=SMOOTH", "*CONTACT PAIR, INTERACTION=SMOOTH", "CX, MX",
                  "*CONTACT PAIR, INTERACTION=SMOOTH", "CY, MY", "*BOUNDARY", "BLOCKS, 1, 3"]
    elif case == "held":
        nx = [1 + n + (n + 1) * (j + (n + 1) * k) for k in (m - 1, m) for j in range(n + 1)]
        ny = [1 + i + (n + 1) * (n + (n + 1) * k) for k in (m - 1, m) for i in range(n + 1)]
        lines += ["*BOUNDARY"] + [f"{v}, 1, 1" for v in nx] + [f"{v}, 2, 2" for v in ny]
    if case.endswith("pushed"):
        lines += ["*STEP", "*STATIC", "*CLOAD", "TIP, 1, 1.e3", "TIP, 2, 1.e3",
                  "*NODE PRINT, NSET=TIP", "U", "*END STEP"]
    return deck + "\n".join(lines + ["*STEP", "*BUCKLE", "2", "*CLOAD", "TIP, 3, -1.e5",
                                      "*END STEP"]) + "\n"


def frequency_read_deck(modal=True):
    """frequency_preload_deck's column under gravity with NLGEOM, then a plain *FREQUENCY step;
    ``modal``: then a second *FREQUENCY step and a *MODAL DYNAMIC step (2 % damping) pulling
    TIP sideways by 1e3, which reads that second step's eigenmodes."""
    deck = frequency_preload_deck(True, False, "grav")
    if modal:
        deck += "\n".join(["*STEP", "*FREQUENCY", "4", "*END STEP", "*STEP", "*MODAL DYNAMIC",
                           "1.e-3, 2.e-2", "*MODAL DAMPING", "1, 4, 0.02", "*CLOAD", "TIP, 1, 1.e3",
                           "*NODE PRINT, NSET=TIP", "U", "*END STEP"]) + "\n"
    return deck


def compact_params_deck():
    """Two unit C3D8 cubes 0.05 apart (E 1000, nu 0) held at the bottom on rollers, every
    multi-word parameter name written without blanks: the upper cube an *ELCOPY of the lower
    (ELEMENTSHIFT, SHIFTNODES), tied to it (POSITIONTOLERANCE=0.1, so the tie closes the gap and
    the upper cube is 1.05 tall), pulled by 1.0 on a reference node coupled to its top
    (*COUPLING, REFNODE).  Uniaxial stress 1: the reference node rises 2.05e-3, the lower cube's
    top 1e-3."""
    xy = ((0, 0), (1, 0), (1, 1), (0, 1))
    nodes = [f"{4 * k + i + 1}, {x}., {y}., {z}" for k, z in enumerate((0.0, 1.0, 1.05, 2.05))
             for i, (x, y) in enumerate(xy)]
    return "\n".join(
        ["*NODE"] + nodes + ["100, 0.5, 0.5, 2.05", "*ELEMENT, TYPE=C3D8, ELSET=LOW",
                             "1, 1, 2, 3, 4, 5, 6, 7, 8",
                             "*ELCOPY, OLDSET=LOW, NEWSET=UP, ELEMENTSHIFT=1, SHIFTNODES=8",
                             "*NSET, NSET=RP", "100", "*NSET, NSET=TOP", "13, 14, 15, 16",
                             "*NSET, NSET=OUT", "6, 100", "*SURFACE, NAME=LOWTOP", "LOW, S2",
                             "*SURFACE, NAME=UPBOT", "UP, S1", "*SURFACE, TYPE=NODE, NAME=TOPS", "TOP",
                             "*MATERIAL, NAME=M", "*ELASTIC", "1000., 0.",
                             "*SOLID SECTION, ELSET=LOW, MATERIAL=M",
                             "*SOLID SECTION, ELSET=UP, MATERIAL=M",
                             "*TIE, NAME=GLUE, POSITIONTOLERANCE=0.1", "UPBOT, LOWTOP",
                             "*COUPLING, REFNODE=RP, SURFACE=TOPS, CONSTRAINTNAME=PULL",
                             "*KINEMATIC", "1, 3", "*BOUNDARY", "1, 1, 3", "2, 2, 3", "3, 3",
                             "4, 1", "4, 3", "*STEP", "*STATIC", "*CLOAD", "100, 3, 1.",
                             "*NODE PRINT, NSET=OUT", "U", "*END STEP"]) + "\n"


def include_files_deck():
    """Two T3D2 bars (E 1000, nu 0), parts A and B that *INCLUDE one mesh file; it *INCLUDEs a
    file of node data lines by a job-relative path, and the length 2, the area 0.5 and the
    tip loads 5 and 10 are *PARAMETERs from another included file.  The tips stretch
    F L / (E A) = 0.02 and 0.04.  Returns (deck, {file under the job directory: text})."""
    files = {"incl/params.inp": "*PARAMETER\nlen = 2.0\narea = 0.5\nforce = 5.0\n"
                                "force2 = 2 * force\n",
             "incl/bar.inp": "*NODE\n*INCLUDE, INPUT=incl/nodes.inp\n"
                             "*ELEMENT, TYPE=T3D2, ELSET=BAR\n1, 1, 2\n*NSET, NSET=FIX\n1\n"
                             "*NSET, NSET=TIP\n2\n"
                             "*SOLID SECTION, ELSET=BAR, MATERIAL=M\n<area>\n",
             "incl/nodes.inp": "1, 0., 0., 0.\n2, <len>, 0., 0.\n"}
    deck = "\n".join(
        ["*HEADING", "*INCLUDE, INPUT=incl/params.inp", "*PART, NAME=A",
         "*INCLUDE, INPUT=incl/bar.inp", "*END PART", "*PART, NAME=B",
         "*INCLUDE, INPUT=incl/bar.inp", "*END PART",
         "*ASSEMBLY, NAME=ASM", "*INSTANCE, NAME=A1, PART=A", "*END INSTANCE",
         "*INSTANCE, NAME=B1, PART=B", "0., 1., 0.", "*END INSTANCE", "*END ASSEMBLY",
         "*MATERIAL, NAME=M", "*ELASTIC", "1000., 0.", "*BOUNDARY", "ASM.A1.FIX, 1, 3",
         "ASM.A1.TIP, 2, 3", "ASM.B1.FIX, 1, 3", "ASM.B1.TIP, 2, 3", "*STEP", "*STATIC", "*CLOAD",
         "ASM.A1.TIP, 1, <force>", "ASM.B1.TIP, 1, <force2>", "*NODE PRINT, NSET=ASM.A1.TIP", "U",
         "*NODE PRINT, NSET=ASM.B1.TIP", "U", "*END STEP"]) + "\n"
    return deck, files


def s4r_plate_deck(step, n=16, t=0.01):
    """(deck, Kirchhoff answer): a 1 x 1 simply supported square plate of n x n S4R shells, a/t
    = 1 / t (E 210e9, nu 0.3, rho 7800; w held on every edge, u on x = 0, v on y = 0).
    "static": pressure 1e3, the centre's deflection (Navier: 0.00406235 q a^4 / D);
    "freq": the lowest frequency (pi sqrt(D / (rho t)) / a^2); "buckle": the x = 1 edge pushed
    with half the buckling load 4 pi^2 D / a (consistent nodal forces), factor 2."""
    nodes, elems = sheet_mesh("S4R", n, n)
    D = 210e9 * t ** 3 / (12 * (1 - 0.09))
    ids = lambda pred: [k for k, (x, y) in nodes.items() if pred(x, y)]     # noqa: E731
    edge = ids(lambda x, y: min(x, y) < 1e-9 or max(x, y) > 1 - 1e-9)
    mid = ids(lambda x, y: abs(x - 0.5) < 1e-9 and abs(y - 0.5) < 1e-9)
    lines = (["*NODE"] + [f"{k}, {x:.12g}, {y:.12g}, 0." for k, (x, y) in nodes.items()]
             + ["*ELEMENT, TYPE=S4R, ELSET=PLATE"] + [f"{e}, " + ", ".join(map(str, c))
                                                      for e, c in enumerate(elems, 1)]
             + ["*NSET, NSET=EDGE"] + _ids(edge) + ["*NSET, NSET=LEFT"] + _ids(ids(lambda x, y: x < 1e-9))
             + ["*NSET, NSET=BOT"] + _ids(ids(lambda x, y: y < 1e-9)) + ["*NSET, NSET=MID"] + _ids(mid)
             + ["*MATERIAL, NAME=STEEL", "*ELASTIC", "210e9, 0.3", "*DENSITY", "7800.",
                "*SHELL SECTION, ELSET=PLATE, MATERIAL=STEEL", f"{t:.12g}",
                "*BOUNDARY", "EDGE, 3, 3", "LEFT, 1, 1", "BOT, 2, 2", "*STEP"])
    if step == "static":
        lines += ["*STATIC", "*DLOAD", "PLATE, P, 1000.", "*NODE PRINT, NSET=MID", "U"]
        ref = 0.00406235 * 1000. / D
    elif step == "freq":
        lines += ["*FREQUENCY", "2"]
        ref = math.pi * math.sqrt(D / (7800. * t))
    else:
        push = 2 * math.pi ** 2 * D
        lines += ["*BUCKLE", "2", "*CLOAD"] + [
            f"{k}, 1, {-push / n * (0.5 if min(y, 1 - y) < 1e-9 else 1.0):.12g}"
            for k, (x, y) in nodes.items() if x > 1 - 1e-9]
        ref = 2.0
    return "\n".join(lines + ["*END STEP"]) + "\n", ref


def plane_cantilever_deck(typ, nx, ny, length, depth, thickness=None):
    """(deck, Timoshenko tip deflection): a plane cantilever length x depth of nx x ny ``typ``
    elements (E 210000, nu 0.3; plane thickness ``thickness``, Abaqus' 1 when None), its root
    held, a unit load across its tip spread over the tip nodes; the tip nodes' mean deflection
    is read."""
    nid = lambda i, j: 1 + i + (nx + 1) * j     # noqa: E731
    nodes = {nid(i, j): (i * length / nx, j * depth / ny) for j in range(ny + 1) for i in range(nx + 1)}
    elems = [[nid(i, j), nid(i + 1, j), nid(i + 1, j + 1), nid(i, j + 1)] for j in range(ny) for i in range(nx)]
    tip = [nid(nx, j) for j in range(ny + 1)]
    t = thickness or 1.0
    e_mod = 210000. / (1 - 0.09) if typ.startswith("CPE") else 210000.
    ref = length ** 3 / (3 * e_mod * t * depth ** 3 / 12) + length / (5 / 6 * 210000. / 2.6 * depth * t)
    lines = (["*NODE"] + [f"{k}, {x:.12g}, {y:.12g}" for k, (x, y) in nodes.items()]
             + [f"*ELEMENT, TYPE={typ}, ELSET=S"] + [f"{e}, " + ", ".join(map(str, c)) for e, c in enumerate(elems, 1)]
             + ["*NSET, NSET=ROOT"] + _ids([nid(0, j) for j in range(ny + 1)]) + ["*NSET, NSET=TIP"] + _ids(tip)
             + ["*MATERIAL, NAME=M", "*ELASTIC", "210000., 0.3", "*SOLID SECTION, ELSET=S, MATERIAL=M"]
             + ([f"{thickness:.12g}"] if thickness else [])
             + ["*BOUNDARY", "ROOT, 1, 2", "*STEP", "*STATIC", "*CLOAD"]
             + [f"{k}, 2, {1.0 / len(tip):.12g}" for k in tip] + ["*NODE PRINT, NSET=TIP", "U", "*END STEP"])
    return "\n".join(lines) + "\n", ref


def stretched_membrane_deck(typ, n=16, t=0.01):
    """(deck, membrane answer): a unit square of n x n ``typ`` membranes (E 210e9, nu 0.3), its
    edges stretched by a strain 1e-3 in both directions in a first NLGEOM step and held, then a
    pressure q in a second: the centre deflects 0.07367 q / N, N = E t 1e-3 / (1 - nu) (the
    membrane's Poisson equation), about 1e-3 here."""
    nodes, elems = sheet_mesh(typ, n, n)
    tension = 210e9 * t * 1e-3 / 0.7
    q = 1e-3 * tension / 0.07367
    edge = [k for k, (x, y) in nodes.items() if min(x, y) < 1e-9 or max(x, y) > 1 - 1e-9]
    mid = [k for k, (x, y) in nodes.items() if abs(x - 0.5) < 1e-9 and abs(y - 0.5) < 1e-9]
    lines = (["*NODE"] + [f"{k}, {x:.12g}, {y:.12g}, 0." for k, (x, y) in nodes.items()]
             + [f"*ELEMENT, TYPE={typ}, ELSET=S"] + [f"{e}, " + ", ".join(map(str, c)) for e, c in enumerate(elems, 1)]
             + ["*NSET, NSET=MID"] + _ids(mid)
             + ["*MATERIAL, NAME=M", "*ELASTIC", "210e9, 0.3", "*MEMBRANE SECTION, ELSET=S, MATERIAL=M", f"{t:.12g}",
                "*BOUNDARY"])
    for k in edge:
        x, y = nodes[k]
        lines += [f"{k}, 1, 1, {1e-3 * (x - 0.5):.12g}", f"{k}, 2, 2, {1e-3 * (y - 0.5):.12g}", f"{k}, 3, 3"]
    lines += ["*STEP, NLGEOM", "*STATIC", "0.5, 1.", "*END STEP", "*STEP, NLGEOM", "*STATIC", "0.25, 1.",
              "*DLOAD", f"S, P, {q:.12g}", "*NODE PRINT, NSET=MID", "U", "*END STEP"]
    return "\n".join(lines) + "\n", 0.07367 * q / tension


def beam_cantilever_deck(typ, n=10, a=0.1):
    """(deck, Timoshenko tip deflection): a unit cantilever of n ``typ`` beams, a x a RECT section
    (E 210000, nu 0.3), clamped, a unit tip load across it."""
    lines = (["*NODE"] + [f"{i + 1}, {i / n:.12g}, 0., 0." for i in range(n + 1)]
             + [f"*ELEMENT, TYPE={typ}, ELSET=B"] + [f"{i + 1}, {i + 1}, {i + 2}" for i in range(n)]
             + ["*NSET, NSET=TIP", str(n + 1), "*MATERIAL, NAME=M", "*ELASTIC", "210000., 0.3",
                "*BEAM SECTION, ELSET=B, MATERIAL=M, SECTION=RECT", f"{a:.12g}, {a:.12g}", "0., 0., -1.",
                "*BOUNDARY", "1, 1, 6", "*STEP", "*STATIC", "*CLOAD", f"{n + 1}, 2, 1.",
                "*NODE PRINT, NSET=TIP", "U", "*END STEP"])
    return "\n".join(lines) + "\n", 1 / (3 * 210000. * a ** 4 / 12) + 1 / (5 / 6 * 210000. / 2.6 * a * a)


def long_numbers_deck():
    """A unit C3D8 cube (nu 0) held on x = 0 and pulled on x = 1, its modulus and nodal forces
    written longer than the 20 characters ccx 2.23 reads of a field: E 1.0000000000000000000e-03
    (ccx read 1.0), each of the 4 forces -5.148903517857142e-05 ('*ERROR reading *CLOAD').  The
    loaded face moves 4 F / E = -0.2059561407142857."""
    return "\n".join(
        ["*NODE", "1, 0., 0., 0.", "2, 1., 0., 0.", "3, 1., 1., 0.", "4, 0., 1., 0.", "5, 0., 0., 1.",
         "6, 1., 0., 1.", "7, 1., 1., 1.", "8, 0., 1., 1.", "*ELEMENT, TYPE=C3D8, ELSET=EALL",
         "1, 1, 2, 3, 4, 5, 6, 7, 8", "*NSET, NSET=FIX", "1, 4, 5, 8", "*NSET, NSET=TIP", "2, 3, 6, 7", "*MATERIAL, NAME=M",
         "*ELASTIC", "1.0000000000000000000e-03, 0.", "*SOLID SECTION, ELSET=EALL, MATERIAL=M",
         "*BOUNDARY", "FIX, 1, 3", "*STEP", "*STATIC", "*CLOAD", "TIP, 1, -5.148903517857142e-05",
         "*NODE PRINT, NSET=TIP", "U", "*END STEP"]) + "\n"


R20_CUBE = """*Node
1, 0., 0., 0.
2, 1., 0., 0.
3, 1., 1., 0.
4, 0., 1., 0.
5, 0., 0., 1.
6, 1., 0., 1.
7, 1., 1., 1.
8, 0., 1., 1.
*Element, type=C3D8, elset=EALL
1, 1, 2, 3, 4, 5, 6, 7, 8
*Nset, nset=BOT
1, 2, 3, 4
*Nset, nset=TOP
5, 6, 7, 8
"""
# the cube held against rigid motion only: node 1 fixed, 2 in y and z, 3 in z, 4 in x and z
R20_HOLD = "1, 1, 3\n2, 2, 3\n3, 3\n4, 1\n4, 3\n"
R20_ELASTIC = "*Material, name=M\n*Elastic\n1000., 0.3\n*Solid Section, elset=EALL, material=M\n"


def ccx_rejects_deck(kind):
    """Decks of cards ccx 2.23 stopped or crashed on as the converter wrote them (code review
    2, R20).  rigid: a *RIGID BODY with ELSET and TIE NSET; kinematic: a face coupled on DOF 3
    alone, then a step with *BOUNDARY, OP=NEW; visco: *VISCO without CETOL; faces: a pressure
    on a *SURFACE line without a face label (two stacked cubes); dofs (dofs_ref): BCs on DOFs
    1-30 (1-3); plies: a *SOLID SECTION, COMPOSITE of two equal orthotropic plies on a turned
    orientation; ori_degenerate / ori_offset: an isotropic section on an orientation without
    axes."""
    if kind == "rigid":
        return (R20_CUBE + "*Node\n9, 0., 0., 2.\n10, 1., 0., 2.\n11, 1., 1., 2.\n12, 0., 1., 2.\n"
                "13, 0., 0., 3.\n14, 1., 0., 3.\n15, 1., 1., 3.\n16, 0., 1., 3.\n100, 0.5, 0.5, 4.\n"
                "*Element, type=C3D8, elset=E2\n2, 9, 10, 11, 12, 13, 14, 15, 16\n*Nset, nset=E2N\n"
                "9, 10, 11, 12, 13, 14, 15, 16\n" + R20_ELASTIC +
                "*Solid Section, elset=E2, material=M\n*Rigid Body, ref node=100, elset=E2, tie nset=TOP\n"
                "*Boundary\nBOT, 1, 3\n*Step\n*Static\n*Cload\n100, 3, 10.\n*Node Print, nset=TOP\nU\n"
                "*Node Print, nset=E2N\nU\n*End Step\n")
    if kind == "kinematic":
        return (R20_CUBE + "*Node\n100, 0.5, 0.5, 1.\n*Nset, nset=RP\n100\n*Surface, type=NODE, "
                "name=TS\nTOP\n" + R20_ELASTIC + "*Coupling, ref node=100, surface=TS, constraint "
                "name=C\n*Kinematic\n3, 3\n*Boundary\n" + R20_HOLD + "*Step\n*Static\n*Cload\n"
                "100, 3, 1.\n*Node Print\nU\n*End Step\n*Step\n*Static\n*Boundary, op=NEW\n" + R20_HOLD +
                "*Cload\n100, 3, 2.\n*Node Print\nU\n*End Step\n")
    if kind == "visco":
        return (R20_CUBE + "*Material, name=M\n*Elastic\n210000., 0.3\n*Creep, law=TIME\n1e-6, 1., 0.\n"
                "*Solid Section, elset=EALL, material=M\n*Boundary\n" + R20_HOLD +
                "*Step, amplitude=STEP\n*Visco\n0.1, 1.\n*Cload\nTOP, 3, 100.\n*Node Print, nset=TOP\nU\n"
                "*End Step\n")
    if kind == "faces":
        return (R20_CUBE + "*Node\n9, 0., 0., 2.\n10, 1., 0., 2.\n11, 1., 1., 2.\n12, 0., 1., 2.\n"
                "*Element, type=C3D8, elset=EALL\n2, 5, 6, 7, 8, 9, 10, 11, 12\n*Surface, name=OUT\n"
                "EALL\n" + R20_ELASTIC + "*Boundary\n" + R20_HOLD +
                "*Step\n*Static\n*Dsload\nOUT, P, 10.\n*Node Print, nset=ALLN\nU\n*End Step\n"
                ).replace("*Surface", "*Nset, nset=ALLN, generate\n1, 12, 1\n*Surface")
    if kind in ("dofs", "dofs_ref"):
        return (R20_CUBE + R20_ELASTIC + "*Boundary\nBOT, 1, " + ("30" if kind == "dofs" else "3") +
                "\n*Step\n*Static\n*Cload\n7, 3, 1.\n*Node Print, nset=TOP\nU\n*End Step\n")
    if kind == "plies":
        return (R20_CUBE + "*Material, name=M\n*Elastic, type=ENGINEERING CONSTANTS\n100., 10., 50., 0., "
                "0., 0., 5., 5.,\n5.\n*Orientation, name=OR1\n1., 0., 0., 0., 0., 1.\n*Solid Section, "
                "elset=EALL, composite, orientation=OR1, stack direction=3\n0.5, 2, M, OR1\n0.5, 2, M, OR1\n"
                "*Boundary\n" + R20_HOLD +
                "*Step\n*Static\n*Cload\nTOP, 3, 0.25\n*Node Print, nset=TOP\nU\n*End Step\n")
    ori = ("*Orientation, name=OR1\n1., 0., 0.\n" if kind == "ori_degenerate" else
           "*Orientation, name=OR1, definition=OFFSET TO NODES\n1, 2\n")
    return (R20_CUBE + ori + "*Material, name=M\n*Elastic\n1000., 0.3\n*Solid Section, elset=EALL, "
            "material=M, orientation=OR1\n*Boundary\n" + R20_HOLD + "*Step\n*Static\n*Cload\nTOP, 3, "
            "2.5\n*El Print, elset=EALL\nS\n*Node Print, nset=TOP\nU\n*End Step\n")


def ccx_leftovers_deck(kind):
    """Decks of the cards task 91 converts (ccx 2.23 stopped on them, or solved them wrong).
    twist (twist_nl, twist_ref): two stacked cubes, clamped at the bottom, whose top-face
    diagonal nodes 5 and 7 are coupled (all translations) to a reference node between them,
    which is loaded: its twist about the diagonal moves no coupled DOF; the reference: the
    node's force halved onto 5 and 7 and the rigid link's *EQUATION (u7 - u5) . (1, 1, 0) = 0.
    dload: a pressure on the top face beside a VP1 line ccx lacks; cax_bz / cax_br: a CAX4
    ring under an axial / radial body force; shell / shell_ref: an S4 strip whose tip element
    is coupled to a loaded node through a *SURFACE line without a face label / a node
    surface; blank: two stacked cubes under a pressure on a *SURFACE with a blank data line;
    comp_shear: a two-layer *SOLID SECTION, COMPOSITE cube (E 1000 and 3000, nu 0) in simple
    shear; comp_angles: two layers of one orthotropic material at 0 and 90 degrees, pulled
    along x."""
    if kind.startswith("twist"):
        nodes = "".join(f"{n}, {x}., {y}., {z}.\n" for n, (x, y, z) in enumerate(
            [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1),
             (0, 0, 2), (1, 0, 2), (1, 1, 2), (0, 1, 2)], 1))
        deck = ("*Node\n" + nodes + "100, 0.5, 0.5, 1.\n*Element, type=C3D8, elset=EALL\n"
                "1, 1, 2, 3, 4, 5, 6, 7, 8\n2, 5, 6, 7, 8, 9, 10, 11, 12\n*Nset, nset=MEM\n5, 7\n"
                "*Nset, nset=OUT\n5, 7, 11\n*Surface, type=NODE, name=MS\nMEM\n" + R20_ELASTIC)
        load = "100, 1, 1.\n100, 2, 2.\n100, 3, 3.\n"
        if kind == "twist_ref":
            deck += "*Equation\n4\n7, 1, 1., 7, 2, 1., 5, 1, -1., 5, 2, -1.\n"
            load = "".join(f"{n}, {k}, {f / 2}\n" for n in (5, 7) for k, f in ((1, 1.), (2, 2.), (3, 3.)))
        else:
            deck += "*Coupling, ref node=100, surface=MS, constraint name=C\n*Kinematic\n1, 3\n"
        return (deck + "*Boundary\n1, 1, 3\n2, 1, 3\n3, 1, 3\n4, 1, 3\n" +
                ("*Step, nlgeom=YES\n*Static\n0.25, 1.\n" if kind == "twist_nl" else "*Step\n*Static\n") +
                "*Cload\n" + load + "*Node Print, nset=OUT\nU\n*End Step\n")
    if kind == "dload":
        return (R20_CUBE + R20_ELASTIC + "*Boundary\n" + R20_HOLD + "*Step\n*Static\n*Dload\n"
                "EALL, P2, 10.\nEALL, VP1, 10.\n*Node Print, nset=TOP\nU\n*End Step\n")
    if kind.startswith("cax"):
        nr = 1 if kind == "cax_bz" else 16
        nodes = "".join(f"{1 + i + (nr + 1) * j}, {1. + i / nr}, {float(j)}\n"
                        for j in (0, 1) for i in range(nr + 1))
        elems = "".join(f"{i + 1}, {i + 1}, {i + 2}, {i + nr + 3}, {i + nr + 2}\n" for i in range(nr))
        return ("*Node\n" + nodes + "*Element, type=CAX4, elset=EALL\n" + elems +
                f"*Nset, nset=BOT, generate\n1, {nr + 1}, 1\n*Nset, nset=ALLN, generate\n"
                f"1, {2 * nr + 2}, 1\n*Material, name=M\n*Elastic\n1000., 0.\n*Solid Section, "
                f"elset=EALL, material=M\n*Boundary\nBOT, 2, 2\n*Step\n*Static\n*Dload\nEALL, "
                f"{'BZ' if kind == 'cax_bz' else 'BR'}, 1.\n*Node Print, nset=ALLN\nU\n*End Step\n")
    if kind.startswith("shell"):
        nodes = "".join(f"{i + 1 + 5 * j}, {float(i)}, {float(j)}, 0.\n" for j in (0, 1) for i in range(5))
        surf = ("*Surface, type=NODE, name=CS\nTIPN\n" if kind == "shell_ref" else
                "*Surface, type=ELEMENT, name=CS\nTIP\n")
        return ("*Node\n" + nodes + "100, 4.5, 0.5, 0.\n*Element, type=S4, elset=EALL\n"
                "1, 1, 2, 7, 6\n2, 2, 3, 8, 7\n3, 3, 4, 9, 8\n4, 4, 5, 10, 9\n*Elset, elset=TIP\n4\n"
                "*Nset, nset=TIPN\n4, 5, 9, 10\n*Nset, nset=OUT\n5, 10, 100\n*Nset, nset=CLAMP\n1, 6\n"
                "*Material, name=M\n*Elastic\n200000., 0.3\n*Shell Section, elset=EALL, material=M\n0.1\n"
                + surf + "*Coupling, ref node=100, surface=CS, constraint name=C\n*Kinematic\n"
                "*Boundary\nCLAMP, 1, 6\n*Step\n*Static\n*Cload\n100, 3, 1.\n100, 2, 1.\n"
                "*Node Print, nset=OUT\nU\n*End Step\n")
    if kind == "blank":
        return (R20_CUBE + "*Node\n9, 0., 0., 2.\n10, 1., 0., 2.\n11, 1., 1., 2.\n12, 0., 1., 2.\n"
                "*Element, type=C3D8, elset=EALL\n2, 5, 6, 7, 8, 9, 10, 11, 12\n*Nset, nset=ALLN, "
                "generate\n1, 12, 1\n*Surface, name=OUT\n\n" + R20_ELASTIC + "*Boundary\n" + R20_HOLD +
                "*Step\n*Static\n*Dsload\nOUT, P, 10.\n*Node Print, nset=ALLN\nU\n*End Step\n")
    # (loads, not prescribed motion: ccx's RF at a held node leaves out the force the
    # interface nodes' *EQUATIONs carry to it, probed)
    if kind == "comp_shear":
        return (R20_CUBE + "*Material, name=SOFT\n*Elastic\n1000., 0.\n*Material, name=STIFF\n"
                "*Elastic\n3000., 0.\n*Solid Section, elset=EALL, composite\n0.5, 3, SOFT\n"
                "0.5, 3, STIFF\n*Boundary\nBOT, 1, 3\nTOP, 2, 3\n*Step\n*Static\n*Cload\n"
                "TOP, 1, 2.5\n*Node Print, nset=TOP\nU\n*End Step\n")
    # (the forces of the single brick's field u = 0.01 x, sigma 1 / 0.1 in the layers, on the
    # face x = 1: (0.375 s1 + 0.125 s2) / 2 on each bottom corner, (0.125 s1 + 0.375 s2) / 2 on
    # each top one)
    return (R20_CUBE + "*Nset, nset=X0\n1, 4, 5, 8\n*Nset, nset=X1\n2, 3, 6, 7\n*Material, name=M\n"
            "*Elastic, type=ENGINEERING CONSTANTS\n100., 10., 10., 0., 0., 0., 5., 5.,\n5.\n"
            "*Orientation, name=OR1\n1., 0., 0., 0., 1., 0.\n3, 0.\n*Solid Section, elset=EALL, "
            "composite, orientation=OR1\n0.5, 3, M, 0.\n0.5, 3, M, 90.\n*Boundary\nX0, 1, 1\n"
            "1, 2, 3\n4, 3, 3\n5, 2, 2\n*Step\n*Static\n*Cload\n2, 1, 0.19375\n3, 1, 0.19375\n"
            "6, 1, 0.08125\n7, 1, 0.08125\n*Node Print, nset=X1\nU\n*End Step\n")


def ccx_leftovers2_deck(kind):
    """Decks of the cards task 95 converts (task 91's follow-ups).  dof79: a pressed cube with a
    *CLOAD and an *EQUATION on DOF 9 (ccx stopped on both); twist_*: the two stacked cubes of
    ccx_leftovers_deck's twist (members 5 and 7 coupled to node 100 between them, which is
    loaded) — dyn in a *DYNAMIC step, tr with a *TRANSFORM on node 100 (its force and a moment
    normal to the twist in the local axes), kc as a *KINEMATIC COUPLING card, shell_dyn on S4
    plate nodes in a *DYNAMIC step — and their coupling-free references (_ref: the force
    halved onto the members, a moment as a couple on them, the rigid link's *EQUATION);
    comp20_split / comp20_plain: a C3D20 cube of two layers of equal properties / the plain
    element; comp_ten_<type>: a cube of layers E 1000 / 3000 (nu 0) pulled along x with its face
    x = 1 kept plane; comp_dist_ori / comp_dist_angle: two side-by-side composite C3D8 with
    0.7 / 0.3 orthotropic layers whose axes / angles come per element from a *DISTRIBUTION,
    pulled along x; hp_block / hp_cpe8 / hp_cax8: a body of the fluid's density, submerged
    (C3D20, CPE8, CAX8), under *DLOAD HP on every outer face and its own weight."""
    import itertools
    if kind == "dof79":
        return (R20_CUBE + R20_ELASTIC + "*Boundary\n" + R20_HOLD + "*Equation\n2\n6, 9, 1., 7, 9, -1.\n"
                "*Step\n*Static\n*Dload\nEALL, P2, 10.\n*Cload\n7, 9, 1.\n*Node Print, nset=TOP\nU\n"
                "*End Step\n")
    if kind.startswith("twist"):
        dyn = "dyn" in kind
        nodes = "".join(f"{n}, {x}., {y}., {z}.\n" for n, (x, y, z) in enumerate(
            [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1),
             (0, 0, 2), (1, 0, 2), (1, 1, 2), (0, 1, 2)], 1))
        f, m = (1., 2., 3.), (0.3, -0.3, 0.) if kind.startswith("twist_tr") else None
        if kind.startswith("twist_shell"):
            pts = [(x, y) for y in range(3) for x in range(3)]
            mesh = ("*Node\n" + "".join(f"{n}, {x}., {y}., 0.\n" for n, (x, y) in enumerate(pts, 1)) +
                    "*Element, type=S4, elset=EALL\n1, 1, 2, 5, 4\n2, 2, 3, 6, 5\n3, 4, 5, 8, 7\n"
                    "4, 5, 6, 9, 8\n*Nset, nset=OUT\n3, 6, 9\n*Material, name=M\n*Elastic\n1000., 0.3\n"
                    "*Density\n1e-3\n*Shell Section, elset=EALL, material=M\n0.1\n*Boundary\n"
                    "1, 1, 6\n4, 1, 6\n7, 1, 6\n")
            a, b, ref, f = 5, 9, "1.5, 1.5, 0.", (0.01, 0.02, 0.03)
        else:
            mesh = ("*Node\n" + nodes + "*Element, type=C3D8, elset=EALL\n1, 1, 2, 3, 4, 5, 6, 7, 8\n"
                    "2, 5, 6, 7, 8, 9, 10, 11, 12\n*Nset, nset=OUT\n5, 7, 11\n*Material, name=M\n"
                    "*Elastic\n1000., 0.3\n*Density\n1e-3\n*Solid Section, elset=EALL, material=M\n"
                    "*Boundary\n1, 1, 3\n2, 1, 3\n3, 1, 3\n4, 1, 3\n")
            a, b, ref = 5, 7, "0.5, 0.5, 1."
        step = "*Step\n" + ("*Dynamic\n0.05, 1.\n" if dyn else "*Static\n")
        if kind.endswith("_ref"):
            forces = [[x / 2 for x in f], [x / 2 for x in f]]
            if m:                                   # the couple of M normal to the bar a-b
                r = (0.5, 0.5, 0.)
                c = (m[1] * r[2] - m[2] * r[1], m[2] * r[0] - m[0] * r[2], m[0] * r[1] - m[1] * r[0])
                forces = [[forces[0][k] - c[k] / 1.0 for k in range(3)], [forces[1][k] + c[k] / 1.0 for k in range(3)]]
            load = "".join(f"{n}, {k + 1}, {forces[i][k]}\n" for i, n in enumerate((a, b)) for k in range(3))
            body = mesh + f"*Equation\n4\n{b}, 1, 1., {b}, 2, 1., {a}, 1, -1., {a}, 2, -1.\n"
        else:
            s2 = 2 ** 0.5
            local = kind.startswith("twist_tr")         # (node 100 turned 45 degrees about z)
            fl = (3 / s2, 1 / s2, 3.) if local else f
            load = "".join(f"100, {k + 1}, {fl[k]}\n" for k in range(3)) + \
                ("100, 5, " + str(-0.3 * s2) + "\n" if local else "")
            members = f"*Nset, nset=MEM\n{a}, {b}\n"
            cpl = ("*Kinematic Coupling, ref node=100\nMEM, 1, 3\n" if kind == "twist_kc" else
                   "*Surface, type=NODE, name=MS\nMEM\n*Coupling, ref node=100, surface=MS, "
                   "constraint name=C\n*Kinematic\n1, 3\n")
            tr = ("*Nset, nset=NREF\n100\n*Transform, nset=NREF\n1., 1., 0., -1., 1., 0.\n" if local else "")
            body = mesh + f"*Node\n100, {ref}\n" + members + tr + cpl
        return body + step + "*Cload\n" + load + "*Node Print, nset=OUT\nU\n*End Step\n"
    if kind.startswith("comp"):
        c8 = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]
        e20 = [(1, 2), (2, 3), (3, 4), (4, 1), (5, 6), (6, 7), (7, 8), (8, 5), (1, 5), (2, 6), (3, 7), (4, 8)]
        pts = c8 + [tuple((u + v) / 2 for u, v in zip(c8[i - 1], c8[j - 1])) for i, j in e20]
        typ = {"comp20_split": "C3D20", "comp20_plain": "C3D20", "comp_ten_c3d20r": "C3D20R",
               "comp_ten_c3d8i": "C3D8I"}.get(kind, "C3D8")
        if typ.startswith("C3D20"):
            mesh = ("*Node\n" + "".join(f"{n}, {x}, {y}, {z}\n" for n, (x, y, z) in enumerate(pts, 1)) +
                    f"*Element, type={typ}, elset=EALL\n1, " + ", ".join(map(str, range(1, 16))) + ",\n" +
                    ", ".join(map(str, range(16, 21))) + "\n*Nset, nset=ALLN, generate\n1, 20, 1\n")
        else:
            pts = c8 + ([(1, 2, 0), (0, 2, 0), (1, 2, 1), (0, 2, 1)] if "dist" in kind else [])
            mesh = ("*Node\n" + "".join(f"{n}, {x}, {y}, {z}\n" for n, (x, y, z) in enumerate(pts, 1)) +
                    f"*Element, type={typ}, elset=EALL\n1, 1, 2, 3, 4, 5, 6, 7, 8\n" +
                    ("2, 4, 3, 9, 10, 8, 7, 11, 12\n" if "dist" in kind else "") +
                    f"*Nset, nset=ALLN, generate\n1, {len(pts)}, 1\n")
        if kind.startswith("comp20"):
            bot = [n for n, q in enumerate(pts, 1) if q[2] == 0]
            sec = ("*Solid Section, elset=EALL, material=A\n" if kind == "comp20_plain" else
                   "*Solid Section, elset=EALL, composite\n0.3, 3, A\n0.7, 3, B\n")
            return (mesh + "*Material, name=A\n*Elastic\n1000., 0.3\n*Material, name=B\n*Elastic\n"
                    "1000., 0.3\n" + sec + "*Boundary\n" + "".join(f"{n}, 1, 3\n" for n in bot) +
                    "*Step\n*Static\n*Cload\n6, 1, 1.\n7, 2, -2.\n14, 3, 3.\n15, 1, -0.5\n8, 3, 1.\n"
                    "*Node Print, nset=ALLN\nU\n*End Step\n")
        x0 = [n for n, q in enumerate(pts, 1) if q[0] == 0]
        plane = "*Equation\n" + "".join(f"2\n{n}, 1, 1., 2, 1, -1.\n" for n, q in enumerate(pts, 1)
                                        if q[0] == 1 and n != 2)
        if kind.startswith("comp_ten"):
            mat = ("*Material, name=SOFT\n*Elastic\n1000., 0.\n*Material, name=STIFF\n*Elastic\n3000., 0.\n"
                   "*Solid Section, elset=EALL, composite\n0.5, 3, SOFT\n0.5, 3, STIFF\n")
        else:
            ori = ("*Distribution Table, name=OT\ncoord3D, coord3D\n*Distribution, name=OD, location=ELEMENT, "
                   "table=OT\n, 1., 0., 0., 0., 1., 0.\n1, 1., 0., 0., 0., 1., 0.\n2, 0., 1., 0., -1., 0., 0.\n"
                   "*Orientation, name=OR1\nOD\n3, 0.\n" if kind == "comp_dist_ori" else
                   "*Orientation, name=OR1\n1., 0., 0., 0., 1., 0.\n3, 0.\n*Distribution Table, name=AT\n"
                   "ANGLE\n*Distribution, name=DA, location=ELEMENT, table=AT\n, 0.\n1, 0.\n2, 90.\n")
            mat = ("*Material, name=M\n*Elastic, type=ENGINEERING CONSTANTS\n100., 10., 10., 0., 0., 0., 5., 5.,\n"
                   "5.\n" + ori + "*Solid Section, elset=EALL, composite, orientation=OR1\n" +
                   ("0.7, 3, M, 0.\n" if kind == "comp_dist_ori" else "0.7, 3, M, DA\n") + "0.3, 3, M, 90.\n")
        return (mesh + mat + plane + "*Boundary\n" + "".join(f"{n}, 1, 1\n" for n in x0) +
                "1, 2, 3\n4, 3, 3\n5, 2, 2\n*Step\n*Static\n*Cload\n2, 1, 10.\n*Node Print, nset=ALLN\nU\n"
                "*End Step\n")
    # hp_*: E 1000, nu 0.25, density 2, g 10 (gamma 20), zero-pressure level 3, 2 x 2 (x 2) elements
    za, g = 3., 10.
    if kind == "hp_block":
        pts = {}
        for i, j, k in itertools.product(range(5), repeat=3):
            if sum(1 for q in (i, j, k) if q % 2) <= 1:
                pts[(i, j, k)] = len(pts) + 1
        els, ext = [], []
        mids = [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4), (0, 4), (1, 5), (2, 6), (3, 7)]
        for e, (I, J, K) in enumerate(itertools.product((0, 2), repeat=3), 1):
            c = [(I, J, K), (I + 2, J, K), (I + 2, J + 2, K), (I, J + 2, K),
                 (I, J, K + 2), (I + 2, J, K + 2), (I + 2, J + 2, K + 2), (I, J + 2, K + 2)]
            m = [tuple((u + v) // 2 for u, v in zip(c[p], c[q])) for p, q in mids]
            els.append([pts[x] for x in c + m])
            ext += [(e, f) for f, hit in ((1, K == 0), (2, K == 2), (3, J == 0), (4, I == 2), (5, J == 2),
                                          (6, I == 0)) if hit]
        nodes = "".join(f"{n}, {i / 2}, {j / 2}, {k / 2}\n" for (i, j, k), n in pts.items())
        el = "".join(f"{e}, " + ", ".join(map(str, c[:15])) + ",\n" + ", ".join(map(str, c[15:])) + "\n"
                     for e, c in enumerate(els, 1))
        typ, sec, bc = "C3D20", "", (f"{pts[(0, 0, 0)]}, 1, 3\n{pts[(4, 0, 0)]}, 2, 2\n"
                                     f"{pts[(0, 0, 4)]}, 1, 2\n")
        grav = f"EALL, GRAV, {g}, 0., 0., -1.\n"
        n_nodes = len(pts)
    else:
        pts = {}
        for i, j in itertools.product(range(5), repeat=2):
            if not (i % 2 and j % 2):
                pts[(i, j)] = len(pts) + 1
        els, ext = [], []
        for e, (I, J) in enumerate(itertools.product((0, 2), repeat=2), 1):
            c = [(I, J), (I + 2, J), (I + 2, J + 2), (I, J + 2)]
            m = [(I + 1, J), (I + 2, J + 1), (I + 1, J + 2), (I, J + 1)]
            els.append([pts[x] for x in c + m])
            ext += [(e, f) for f, hit in ((1, J == 0), (2, I == 2), (3, J == 2), (4, I == 0)) if hit]
        r0 = 1. if kind == "hp_cax8" else 0.
        nodes = "".join(f"{n}, {r0 + i / (4 if r0 else 2)}, {j / 2}\n" for (i, j), n in pts.items())
        el = "".join(f"{e}, " + ", ".join(map(str, c)) + "\n" for e, c in enumerate(els, 1))
        typ = "CAX8" if r0 else "CPE8"
        sec = "" if r0 else "1.\n"
        bc = f"{pts[(0, 0)]}, 2, 2\n" if r0 else f"{pts[(0, 0)]}, 1, 2\n{pts[(0, 4)]}, 1, 1\n"
        grav = f"EALL, GRAV, {g}, 0., -1., 0.\n"
        n_nodes = len(pts)
    return (f"*Node\n{nodes}*Element, type={typ}, elset=EALL\n{el}*Nset, nset=ALLN, generate\n1, {n_nodes}, 1\n"
            "*Material, name=M\n*Elastic\n1000., 0.25\n*Density\n2.\n*Solid Section, elset=EALL, material=M\n"
            + sec + "*Boundary\n" + bc + "*Step\n*Static\n*Dload\n" +
            "".join(f"{e}, HP{f}, {20. * za}, {za}, 0.\n" for e, f in ext) + grav +
            "*Node Print, nset=ALLN\nU\n*End Step\n")


def restored_chain_deck(chain=True):
    """An S4 cantilever strip (4 x 1, t 0.1, steel) clamped at x = 0 in the model data, its tip
    loaded in a static step; ``chain``: after a *FREQUENCY step that holds the tip rotations and
    a static perturbation step without loads or BCs, which ccx runs as a general step."""
    nodes = "".join(f"{i + 1 + 5 * j}, {i}., {j}., 0.\n" for j in (0, 1) for i in range(5))
    els = "".join(f"{e}, {e}, {e + 1}, {e + 6}, {e + 5}\n" for e in range(1, 5))
    pre = ("*Step\n*Frequency\n3\n*Boundary\nTIP, 4, 6\n*End Step\n"
           "*Step, perturbation\n*Static\n*End Step\n") if chain else ""
    return (f"*Node\n{nodes}*Element, type=S4, elset=PLATE\n{els}*Nset, nset=ROOT\n1, 6\n"
            "*Nset, nset=TIP\n5, 10\n*Material, name=STEEL\n*Elastic\n210000., 0.3\n*Density\n"
            "7.8e-09\n*Shell Section, elset=PLATE, material=STEEL\n0.1\n*Boundary\nROOT, 1, 6\n" + pre +
            "*Step\n*Static\n*Cload\nTIP, 3, 0.5\n*Node Print, nset=TIP\nU\n*End Step\n")


def wedge_master_deck(contact=True):
    """A C3D8 collapsed to a wedge (1, 1, 2, 3, 4, 4, 5, 6) held at its top, its face S1 the
    master of a *CONTACT PAIR with a cube 0.1 below it (held at its bottom), in a *FREQUENCY
    step: the gap is open, so the frequencies are those without the pair (``contact`` False)."""
    pair = ("*Surface, name=MS, type=element\nMASTER, S1\n*Surface, name=SL, type=element\n"
            "BLOCK, S2\n*Surface interaction, name=SI\n*Contact pair, interaction=SI\nSL, MS\n")
    return ("*Node\n1, 0., 0., 0.\n2, 2., 0., 0.\n3, 0., 2., 0.\n4, 0., 0., 1.\n5, 2., 0., 1.\n"
            "6, 0., 2., 1.\n11, 0.2, 0.2, -0.5\n12, 0.6, 0.2, -0.5\n13, 0.6, 0.6, -0.5\n"
            "14, 0.2, 0.6, -0.5\n15, 0.2, 0.2, -0.1\n16, 0.6, 0.2, -0.1\n17, 0.6, 0.6, -0.1\n"
            "18, 0.2, 0.6, -0.1\n*Element, type=C3D8, elset=MASTER\n1, 1, 1, 2, 3, 4, 4, 5, 6\n"
            "*Element, type=C3D8, elset=BLOCK\n2, 11, 12, 13, 14, 15, 16, 17, 18\n"
            "*Nset, nset=MTOP\n4, 5, 6\n*Nset, nset=BBOT\n11, 12, 13, 14\n*Material, name=M\n"
            "*Elastic\n1000., 0.3\n*Density\n1e-06\n*Solid Section, elset=MASTER, material=M\n"
            "*Solid Section, elset=BLOCK, material=M\n*Boundary\nMTOP, 1, 3\nBBOT, 1, 3\n" +
            (pair if contact else "") + "*Step\n*Frequency\n6\n*End Step\n")


def main():
    A._tolerant_stdio()                 # ccx's error lines may hold what cp1252 cannot show
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
    deck = open(os.path.join(EXAMPLES, "nle10_surface_elements.inp"), encoding="utf-8").read()
    face = syy
    for how, load in (("*DSLOAD P on SPOS", "*DSLOAD\n TOP,P,  1.0E6\n"),
                      ("*DLOAD P, element normal", "*DLOAD\n SKIN,P,  -1.0E6\n"),
                      ("*DLOAD TRVEC", "*DLOAD\n SKIN,TRVEC,  1.0E6, 0., 0., -1.\n")):
        src = os.path.join(tmp, "skin_src.inp")
        with open(src, "w", encoding="utf-8", newline="\n") as fh:
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
    # ccx 2.23 rejects linear beams with a circular section, so this checks the B31 -> B32R
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

    # --- sections ccx's expanded beams cannot carry, as ccx's U1 beam element -----------
    # A B33 cantilever with a general section (I12 nonzero, n1 not normal to the beam):
    # tip forces along y and z against unsymmetric bending theory, a torque against
    # T L / (G J) (U1's torsion G (I11 + I22) set to G J through a material copy's Poisson's
    # ratio) and the first bending frequencies against the Euler-Bernoulli cantilever about
    # the principal axes (U1 adds rotary inertia; its mass converges at O(h^2)).
    def f_cantilever(e_mod, inertia, rho_a, length, beta=1.875104069):
        return beta ** 2 / (2 * math.pi * length ** 2) * math.sqrt(e_mod * inertia / rho_a)

    eig = "E I G E N V A L U E   O U T P U T"
    inp = os.path.join(tmp, "u1_general.inp")
    convert(os.path.join(EXAMPLES, "beam_u1_general.inp"), inp)
    d, status, out = run_ccx(ccx, env, inp)
    tips = [b.get(21) for b in dat_node_blocks(os.path.join(d, "job.dat"))[:3]]
    freqs = dat_eigen_table(os.path.join(d, "job.dat"), eig)
    shutil.rmtree(d, ignore_errors=True)
    if status != "solved" or len(tips) < 3 or None in tips or len(freqs) < 2:
        print(f"FAIL  beam_u1_general: no results ({status})")
        print("\n".join(l for l in out.splitlines() if "ERROR" in l))
        failures += 1
    else:
        e_mod, g_mod, area, rho, length = 210000.0, 80769.2307692, 1000.0, 7.85e-9, 1000.0
        i11, i12, i22, tj = 4.0e5, 1.5e5, 2.0e5, 5.4e5
        det = i11 * i22 - i12 * i12

        def tip(f1, f2):
            """(u_y, u_z) of a tip force (f1 along n1 = z, f2 along n2 = -y): L^3 / 3E times
            the inverse of [[I22, I12], [I12, I11]] (the integrals of x1^2, x1 x2, x2^2)."""
            c = length ** 3 / (3 * e_mod * det)
            d1, d2 = c * (i11 * f1 - i12 * f2), c * (-i12 * f1 + i22 * f2)
            return -d2, d1
        mid, rad = (i11 + i22) / 2, math.hypot((i11 - i22) / 2, i12)
        rows = [("F_y", tips[0][1:3], tip(0.0, -100.0)), ("F_z", tips[1][1:3], tip(100.0, 0.0))]
        rows += [("twist", [tips[2][3]], [1.0e5 * length / (g_mod * tj)])]
        ok_static = all(abs(v - r) <= 1e-5 * max(abs(x) for x in ref) for _, got, ref in rows
                        for v, r in zip(got, ref))
        f_ref = [f_cantilever(e_mod, i, rho * area, length) for i in (mid - rad, mid + rad)]
        ok_freq = all(abs(f - r) <= 0.005 * r for f, r in zip(freqs[:2], f_ref))
        print(f"{'PASS' if ok_static and ok_freq else 'FAIL'}  beam_u1_general (B33 + *BEAM GENERAL "
              f"SECTION, I12 /= 0, as U1): "
              + "; ".join(f"{name} = " + ", ".join(f"{v:+.6g}" for v in got) + " (theory "
                          + ", ".join(f"{r:+.6g}" for r in ref) + ")" for name, got, ref in rows)
              + "; f1, f2 = " + ", ".join(f"{f:.3f}" for f in freqs[:2]) + " Hz (Euler-Bernoulli "
              + ", ".join(f"{r:.3f}" for r in f_ref) + ")")
        failures += 0 if ok_static and ok_freq else 1

    # An I-section B31 cantilever in space, with --approximate: U1's torsion stiffness is
    # G (I11 + I22), 385 times G J here, which no Poisson's ratio ccx accepts brings down —
    # both bending axes exact against beam theory, the twist U1's.  The same deck with a
    # clamped, unloaded stub beam beside it keeps U1 out (ccx stops on U1 beside any element
    # it expands), so --approximate falls back to the RECT of equal area and strong-axis
    # inertia: the gain is the weak axis.
    area, i_strong, i_weak, tj = i_profile(200.0, 100.0, 8.5, 5.6)
    e_mod, g_mod, rho, length = 210000.0, 210000.0 / 2.6, 7.85e-9, 2000.0
    src_text = open(os.path.join(EXAMPLES, "beam_u1_ibeam.inp"), encoding="utf-8").read()
    stub = ("*NODE\n101, 0., 500., 0.\n102, 100., 500., 0.\n*ELEMENT, TYPE=B31, ELSET=STUB\n"
            "101, 101, 102\n*BEAM SECTION, ELSET=STUB, MATERIAL=STEEL, SECTION=RECT\n10., 10.\n"
            "0., 0., 1.\n*NSET, NSET=FAR\n101, 102\n")
    variants = (("U1", src_text),
                ("RECT", src_text.replace("*BOUNDARY\nROOT, 1, 6\n",
                                          stub + "*BOUNDARY\nROOT, 1, 6\nFAR, 1, 6\n")))
    ref = {"u_y": 1000.0 * length ** 3 / (3 * e_mod * i_strong),
           "u_z": 100.0 * length ** 3 / (3 * e_mod * i_weak)}
    f_ref = [f_cantilever(e_mod, i, rho * area, length) for i in (i_weak, i_strong)]
    got = {}
    for label, text in variants:
        src = os.path.join(tmp, "u1_ibeam_src.inp")
        with open(src, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        inp = os.path.join(tmp, "u1_ibeam.inp")
        convert(src, inp, approximate=True)
        d, status, out = run_ccx(ccx, env, inp)
        blocks = dat_node_blocks(os.path.join(d, "job.dat"))[:3]
        freqs = dat_eigen_table(os.path.join(d, "job.dat"), eig)
        shutil.rmtree(d, ignore_errors=True)
        if status == "solved" and len(blocks) == 3 and all(21 in b for b in blocks) and len(freqs) > 1:
            got[label] = ({"u_y": blocks[0][21][1], "u_z": blocks[1][21][2]},
                          blocks[2][21][3] if len(blocks[2][21]) > 3 else None, freqs[:2])
    if set(got) != {"U1", "RECT"}:
        print(f"FAIL  beam_u1_ibeam: no results for {', '.join(sorted({'U1', 'RECT'} - set(got)))}")
        failures += 1
    else:
        (u1, twist, fu1), (rect, _, frect) = got["U1"], got["RECT"]
        err = {k: abs(u1[k] - ref[k]) / ref[k] for k in ref}
        twist_u1 = 1.0e4 * length / (g_mod * (i_strong + i_weak))
        # (U1's rotary inertia lowers the strong-axis frequency by 0.4 % here)
        ok = (max(err.values()) < 1e-4 and abs(twist - twist_u1) <= 1e-4 * twist_u1 and
              all(abs(f - r) <= 0.01 * r for f, r in zip(fu1, f_ref)))
        print(f"{'PASS' if ok else 'FAIL'}  beam_u1_ibeam (B31 + SECTION=I in space, --approximate "
              f"U1): strong-axis tip deflection {u1['u_y']:.6g} (beam theory {ref['u_y']:.6g}), weak "
              f"axis {u1['u_z']:.6g} ({ref['u_z']:.6g}), f1, f2 = {fu1[0]:.2f}, {fu1[1]:.2f} Hz "
              f"({f_ref[0]:.2f}, {f_ref[1]:.2f}); twist {twist:.4g} = T L / G (I11 + I22), "
              f"{(i_strong + i_weak) / tj:.0f} times stiffer than T L / G J = "
              f"{1.0e4 * length / (g_mod * tj):.4g} ([APPROX]); the RECT gives strong / weak "
              f"{rect['u_y']:.4g} / {rect['u_z']:.4g} ({(rect['u_y'] / ref['u_y'] - 1) * 100:+.1f} % / "
              f"{(rect['u_z'] / ref['u_z'] - 1) * 100:+.0f} %), f1 {frect[0]:.2f} Hz")
        failures += 0 if ok else 1

    # The cantilever of Abaqus' Verification Guide ("Verification of beam elements and section
    # types", eb2jidsd) with its unsymmetric I-section, as planar cubic beams: the tip
    # deflection and rotation against the guide's reference values and P L^3 / 3 E I11 with
    # the I11 of Abaqus' own general-section form of the profile (eb32gisd: 1.312095).
    inp = os.path.join(tmp, "u1_unsym.inp")
    convert(os.path.join(EXAMPLES, "beam_u1_unsymmetric_i.inp"), inp)
    d, status, out = run_ccx(ccx, env, inp)
    blocks = dat_node_blocks(os.path.join(d, "job.dat"))
    shutil.rmtree(d, ignore_errors=True)
    tip = blocks[-1].get(11) if status == "solved" and blocks else None
    if tip is None:
        print(f"FAIL  beam_u1_unsymmetric_i: no tip displacement ({status})")
        print("\n".join(l for l in out.splitlines() if "ERROR" in l))
        failures += 1
    else:
        u2, phi3 = tip[1], tip[5]
        exact = (25.0 * 75.0 ** 3 / (3 * 3.0e6 * 1.312095), 25.0 * 75.0 ** 2 / (2 * 3.0e6 * 1.312095))
        ok = (abs(u2 - exact[0]) <= 1e-5 * exact[0] and abs(phi3 - exact[1]) <= 1e-5 * exact[1] and
              abs(u2 - 0.8931) <= 5e-5 and abs(phi3 - 1.786e-2) <= 5e-6)
        print(f"{'PASS' if ok else 'FAIL'}  beam_u1_unsymmetric_i (B23 + an unsymmetric SECTION=I as U1): "
              f"u2 = {u2:.6g}, phi3 = {phi3:.6g} (Abaqus Verification Guide 0.8931, 1.786e-2; "
              f"P L^3 / 3 E I11 = {exact[0]:.6g}, P L^2 / 2 E I11 = {exact[1]:.6g})")
        failures += 0 if ok else 1

    # A hexagonal tube (HEX, d 2, t .2) on the same cantilever in space as U1: closed and
    # doubly symmetric, so its torsion is exact through the material's Poisson's ratio — the
    # tip deflection and rotation against the guide's reference values, the twist against
    # T L / G J with Abaqus' closed thin-walled J (the guide's own analytical twist, 2.796e-4,
    # is a thick-walled value; it says closed sections may differ by several percent).
    inp = os.path.join(tmp, "u1_hex.inp")
    convert(os.path.join(EXAMPLES, "beam_u1_hex.inp"), inp)
    d, status, out = run_ccx(ccx, env, inp)
    blocks = dat_node_blocks(os.path.join(d, "job.dat"))
    shutil.rmtree(d, ignore_errors=True)
    if status != "solved" or len(blocks) < 3 or any(11 not in b for b in blocks[:3]):
        print(f"FAIL  beam_u1_hex: no tip results ({status})")
        failures += 1
    else:
        rm = 2.0 - 0.2 / math.sqrt(3.0)
        j_hex = 4.5 * rm ** 3 * 0.2
        u2, phi3, twist = blocks[0][11][1], blocks[0][11][5], blocks[2][11][3]
        ok = (abs(u2 - 0.3489) <= 5e-5 and abs(phi3 - 6.978e-3) <= 5e-7 and
              abs(blocks[1][11][2] - u2) <= 1e-6 * u2 and
              abs(twist - 25.0 * 75.0 / (3.0e6 / 2.6 * j_hex)) <= 1e-5 * twist)
        print(f"{'PASS' if ok else 'FAIL'}  beam_u1_hex (B33 + SECTION=HEX as U1, in space): u2 = "
              f"{u2:.6g} along y and {blocks[1][11][2]:.6g} along z, phi3 = {phi3:.6g} (Abaqus "
              f"Verification Guide 0.3489, 6.978e-3); twist {twist:.6g} (T L / G J "
              f"{25.0 * 75.0 / (3.0e6 / 2.6 * j_hex):.6g})")
        failures += 0 if ok else 1

    # *BEAM GENERAL SECTION with a ccx profile becomes ccx's beam section with a material from
    # E and G: a RECT cantilever in space against beam theory about both axes, and NAFEMS NL6
    # (an axial end load past buckling, NLGEOM, G not given in a plane) on 32 B22 beams against
    # its published answers (Abaqus' own, on 8 B22: -0.447 / 0.723 and -1.577 / 0.427).
    inp = os.path.join(tmp, "gs_rect.inp")
    convert(os.path.join(EXAMPLES, "beam_general_rect.inp"), inp)
    d, status, out = run_ccx(ccx, env, inp)
    blocks = dat_node_blocks(os.path.join(d, "job.dat"))
    shutil.rmtree(d, ignore_errors=True)
    ref = (100.0 * 1000.0 ** 3 / (3 * 210000.0 * 20.0 * 40.0 ** 3 / 12),
           100.0 * 1000.0 ** 3 / (3 * 210000.0 * 40.0 * 20.0 ** 3 / 12))
    if status != "solved" or len(blocks) < 2:
        print(f"FAIL  beam_general_rect: no tip results ({status})")
        failures += 1
    else:
        got = (blocks[0][21][1], blocks[1][21][2])
        ok = all(abs(g - r) <= 0.002 * r for g, r in zip(got, ref))
        print(f"{'PASS' if ok else 'FAIL'}  beam_general_rect (*BEAM GENERAL SECTION, SECTION=RECT -> "
              f"ccx's B31 + RECT): tip deflection {got[0]:.6g} / {got[1]:.6g} (beam theory "
              f"{ref[0]:.6g} / {ref[1]:.6g})")
        failures += 0 if ok else 1
    inp = os.path.join(tmp, "gs_nl6.inp")
    convert(os.path.join(EXAMPLES, "beam_general_rect_nl6.inp"), inp)
    d, status, out = run_ccx(ccx, env, inp)
    hist = dat_displacement_history(os.path.join(d, "job.dat"), 65)
    times = [float(m) for m in re.findall(r"displacements \(vx,vy,vz\) for set TIP and time\s+(\S+)",
                                          open(os.path.join(d, "job.dat"), encoding="utf-8",
                                               errors="replace").read())] \
        if status == "solved" else []
    shutil.rmtree(d, ignore_errors=True)
    ends = [hist[i] for i, t in enumerate(times) if i < len(hist) and t in (1.0, 2.0)]
    if status != "solved" or len(ends) < 2:
        print(f"FAIL  beam_general_rect_nl6: no results at the ends of the steps ({status})")
        failures += 1
    else:
        got = [(u[0] / 3.2, -u[1] / 3.2) for u in (ends[0], ends[-1])]
        pub = [(-0.440, 0.719), (-1.577, 0.421)]
        ok = all(abs(g - p) <= 0.03 * abs(p) for gu, pu in zip(got, pub) for g, p in zip(gu, pu))
        print(f"{'PASS' if ok else 'FAIL'}  beam_general_rect_nl6 (NAFEMS NL6, *BEAM GENERAL SECTION, "
              f"SECT=RECT on B22, NLGEOM): ux/L, -uy/L = " +
              "; ".join(f"{g[0]:+.4f}, {g[1]:.4f} (published {p[0]:+.3f}, {p[1]:.3f})"
                        for g, p in zip(got, pub)))
        failures += 0 if ok else 1

    # A planar portal frame of I-sections (B23 -> U1, exact Euler-Bernoulli beams) with fixed
    # bases under its own weight (GRAV, which ccx refuses on U1: nodal forces), a line load
    # on the beam (P2) and a lateral load, against the direct-stiffness solution with
    # consistent loads: every node's displacements and rotation.
    inp = os.path.join(tmp, "u1_portal.inp")
    convert(os.path.join(EXAMPLES, "beam_u1_portal.inp"), inp)
    d, status, out = run_ccx(ccx, env, inp)
    blocks = dat_node_blocks(os.path.join(d, "job.dat"))
    shutil.rmtree(d, ignore_errors=True)
    if status != "solved" or not blocks or len(blocks[-1]) != 25:
        print(f"FAIL  beam_u1_portal: no results ({status})")
        print("\n".join(l for l in out.splitlines() if "ERROR" in l))
        failures += 1
    else:
        col, bm = i_profile(300.0, 150.0, 10.7, 7.1), i_profile(400.0, 180.0, 13.5, 8.6)
        nodes = {k: (0.0, 500.0 * (k - 1)) for k in range(1, 10)}
        nodes.update({k: (750.0 * (k - 9), 4000.0) for k in range(10, 18)})
        nodes.update({k: (6000.0, 4000.0 - 500.0 * (k - 17)) for k in range(18, 26)})
        elems = [(k, k + 1, 210000.0, *(bm if 9 <= k <= 16 else col)[:2]) for k in range(1, 25)]
        udl = [(j, 0.0, -7.85e-9 * e[3] * 9810.0 - (20.0 if 9 <= e[0] <= 16 else 0.0))
               for j, e in enumerate(elems)]
        fixed = {(n, k) for n in (1, 25) for k in (1, 2, 6)}
        sol = frame2d(nodes, elems, fixed, {(9, 1): 20000.0}, udl)
        res = blocks[-1]
        top = max(abs(sol[(n, k)]) for n in nodes for k in (1, 2))
        dev = max(abs(res[n][0] - sol[(n, 1)]) + abs(res[n][1] - sol[(n, 2)]) for n in nodes) / top
        rdev = max(abs(res[n][5] - sol[(n, 6)]) for n in nodes) / max(abs(sol[(n, 6)]) for n in nodes)
        ok = dev < 1e-5 and rdev < 1e-5
        print(f"{'PASS' if ok else 'FAIL'}  beam_u1_portal (B23 + SECTION=I as U1, GRAV, P2): "
              f"sway {res[9][0]:.6g} (Euler-Bernoulli frame {sol[(9, 1)]:.6g}), mid-span "
              f"{res[13][1]:.6g} ({sol[(13, 2)]:.6g}); largest difference {dev:.1e} of the largest "
              f"displacement, {rdev:.1e} of the largest rotation")
        failures += 0 if ok else 1

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
        err = ccx_ratio(max(abs(a - b) for a, b in zip(us, ur)), max(abs(b) for b in ur))
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
    # Under any rotational BC ccx 2.23 ties a B32/B32R end node's circular section to its corners,
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

    # --- the same beam without the cap: a diverged run, which the solve judge must catch ---
    # ccx ends it with "Job finished" and exit 0.  The judge reads the NaN in the .dat
    # (Fortran's spelling) and must find it in the .frd on its own as well: C's printf spells
    # it as the C runtime does (NAN on Linux and macOS, -NAN(IND) with Windows' UCRT).
    with open(inp, encoding="utf-8") as fh:
        deck = fh.read()
    uncapped = re.sub(r"(?m)^(\*DYNAMIC, EXPLICIT\n)[^\n]*\n", r"\1, 1.e-3\n", deck, count=1)
    src = os.path.join(tmp, "circexpl_uncapped.inp")
    with open(src, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(uncapped.replace("*END STEP", "*NODE FILE, FREQUENCY=200\nU\n*END STEP", 1))
    d, status, out = run_ccx(ccx, env, src)
    hits = []
    for ext, scan in ((".dat", A._dat_nonfinite), (".frd", A._frd_nonfinite)):
        try:
            with open(os.path.join(d, "job" + ext), "rb") as fh:
                hits.append(scan(fh))
        except OSError:
            hits.append(None)

    def spelling(hit):                  # the first value written as NaN or Inf
        m = hit and re.search(r"(?i)[+-]?(?:\d\.#\w+|nan(?:\(\w*\))?|inf(?:inity)?)",
                              hit.split(": ")[-1])
        return m.group(0) if m else hit or "nothing"
    ok = uncapped != deck and status == "nonfinite" and all(hits)
    print(f"{'PASS' if ok else 'FAIL'}  beam_circ_explicit without its increment cap (diverges): "
          f"judged {status}; NaN/Inf in the .dat as {spelling(hits[0])}, in the .frd as "
          f"{spelling(hits[1])}" + ("" if uncapped != deck else " (no *DYNAMIC, EXPLICIT to uncap)"))
    failures += 0 if ok else 1
    shutil.rmtree(d, ignore_errors=True)

    # --- planar beams on pinned supports: frequencies and buckling vs beam theory ---------
    # ccx runs B21 as a 3-D B31, so this checks the planar constraint: DOF 3 fixed on every
    # node (otherwise nothing holds the beam in its plane) and DOFs 4-5 at one node
    # (otherwise the free twist is a 0 Hz mode and the buckling factor meaningless): at the
    # pinned end, and on the circular section (a B32R in ccx) at the first element's middle
    # node — at the end node ccx 2.23 would lock the bending rotation as well (f1 1.46x).
    beam_refs = {}
    for name, label, ei, rho_a in (
            ("planar_pinned_beam", "B21", 210000.0 * 20.0 * 40.0 ** 3 / 12, 7.85e-9 * 20.0 * 40.0),
            ("planar_pinned_circ_beam", "B21 + CIRC", 210000.0 * math.pi * 10.0 ** 4 / 4,
             7.85e-9 * math.pi * 10.0 ** 2)):
        inp = os.path.join(tmp, name + ".inp")
        convert(os.path.join(EXAMPLES, name + ".inp"), inp)
        d, status, out = run_ccx(ccx, env, inp)
        length = 1000.0
        c = math.sqrt(ei / rho_a) * math.pi / (2 * length ** 2)            # in-plane E I
        refs = beam_refs[name] = [c, 4 * c, math.pi ** 2 * ei / length ** 2]   # f1, f2, Euler load
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

    # --- two B22 elements: the mesh on which Abaqus' quadratic beam is exact ----------------
    # Abaqus integrates its 3-node beams at 2 points along the beam, as ccx's B32R, which the
    # converter writes them as: Abaqus' mid-span deflection (Timoshenko, k = 0.85) to 0.15 %,
    # f1 and the Euler load to 1.3 % on two elements (ccx's B32, 3 points: 0.76, +11 %, +21 %).
    inp = os.path.join(tmp, "planar_b22_two_elements.inp")
    convert(os.path.join(EXAMPLES, "planar_b22_two_elements.inp"), inp)
    d, status, out = run_ccx(ccx, env, inp)
    ei, ga = 210000.0 * 20.0 * 40.0 ** 3 / 12, 210000.0 / 2.6 * 800.0
    refs = [math.sqrt(ei / (7.85e-9 * 800.0)) * math.pi / 2e6, math.pi ** 2 * ei / 1e6,
            -(1000.0 * 1000.0 ** 3 / (48 * ei) + 1000.0 * 1000.0 / (4 * 0.85 * ga))]
    dat = os.path.join(d, "job.dat")
    got = (dat_eigen_table(dat, "E I G E N V A L U E   O U T P U T")[:1]
           + dat_eigen_table(dat, "B U C K L I N G   F A C T O R   O U T P U T")[:1]
           + [(dat_displacement(dat, 3) or [0.0, None])[1]]) if status == "solved" else []
    if len(got) < 3 or got[2] is None:
        print(f"FAIL  planar_b22_two_elements: no frequency / buckling factor / deflection ({status})")
        print("\n".join(l for l in out.splitlines() if "ERROR" in l))
        failures += 1
    else:
        diffs = [abs(g - r) / abs(r) for g, r in zip(got, refs)]
        ok = max(diffs) < 0.02 and diffs[2] < 0.005
        print(f"{'PASS' if ok else 'FAIL'}  planar_b22_two_elements (2 x B22 -> B32R): mid-span "
              f"deflection {got[2]:+.4f} (Abaqus' exact {refs[2]:+.4f}, {diffs[2] * 100:.2f}% diff), "
              f"f1 {got[0]:.2f} Hz (beam theory {refs[0]:.2f}), buckling load {got[1]:.0f} (Euler "
              f"{refs[1]:.0f}); max {max(diffs) * 100:.1f}% diff")
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
            err = ccx_ratio(max(abs(a - b) for n in ue for a, b in zip(ud[n], ue[n])), scale)
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
        text = open(src, encoding="utf-8").read()
        for a, b in subs:
            text = text.replace(a, b)
        tmp_src = os.path.join(tmp, f"{name}_{len(subs)}_src.inp")
        with open(tmp_src, "w", encoding="utf-8", newline="\n") as fh:
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
        return ccx_ratio(abs(a - b), abs(b))

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
    # a second link (10 above the first, loaded less) on a second LINK line of the same card:
    # ccx reads one MPC per *MPC card, so each *MPC BEAM needs its own (both in one card
    # stop ccx: 'increase nk_')
    second = [("3, 7., 1., 0.\n", "3, 7., 1., 0.\n11, 0., 0., 10.\n12, 3., 4., 10.\n13, 7., 1., 10.\n"),
              ("*Nset, nset=FIXED\n1, 3\n", "*Nset, nset=FIXED\n1, 3, 11, 13\n"),
              ("*Nset, nset=ALLN\n1, 2, 3\n", "*Nset, nset=ALLN\n1, 2, 3, 11, 12, 13\n"),
              ("elset=SPRING\n1, 3, 2\n", "elset=SPRING\n1, 3, 2\n2, 13, 12\n"),
              ("LINK, 2, 1\n", "LINK, 2, 1\nLINK, 12, 11\n"), ("2, 3, 3\n", "2, 3, 3\n12, 3, 3\n"),
              ("*Step\n*Static\n", "*Step, nlgeom=YES\n*Static\n0.05, 1., 1e-5, 0.25\n"),
              ("2, 1, 10.", "2, 1, -2000.\n12, 1, -1500.")]
    u = solve("mpc_link", subs=second, nodes=(2, 12))
    if u:
        lengths = [math.dist((3 + u[n][0], 4 + u[n][1], u[n][2]), (0.0, 0.0, 0.0)) for n in (2, 12)]
        turns = [math.degrees(math.atan2(4 + u[n][1], 3 + u[n][0]) - math.atan2(4, 3))
                 for n in (2, 12)]
        ok = max(rel(x, 5.0) for x in lengths) < 1e-6 and min(turns) > 10
        print(f"{'PASS' if ok else 'FAIL'}  mpc_link, two LINK lines in one card, NLGEOM: lengths "
              f"{lengths[0]:.7f} / {lengths[1]:.7f} (5) after turning {turns[0]:.1f} / "
              f"{turns[1]:.1f} degrees")
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
            err = ccx_ratio(max(abs(a - b) for n in nodes for a, b in zip(ref[n], got[n])),
                            max(abs(a) for n in nodes for a in ref[n]))
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
        miss = ccx_ratio(max(abs(q + a - b - c) for n, x in pts.items()
                             for q, a, b, c in zip(x3, _rotate([p - q for p, q in zip(x, x3)], e1, phi),
                                                   x, u[n])),
                         max(abs(c) for n in pts for c in u[n]))
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
        diffs = [ccx_ratio(abs(v - ref), abs(ref)) for _, v, ref in refs]
        ok = diffs[0] < 0.02 and diffs[1] < 1e-4
        print(f"{'PASS' if ok else 'FAIL'}  {name}: step 2 " + ", ".join(
            f"{label} {v:+.4f} (expected {ref:+.4f}, {diff * 100:.2f}% diff)"
            for (label, v, ref), diff in zip(refs, diffs)))
        failures += 0 if ok else 1

    # --- *DSLOAD and *DLOAD, OP=NEW in one step ---------------------------------------------
    # ccx 2.23 has one OP=NEW flag for *DLOAD and *DSLOAD and acts on it on a step's first
    # card only.  A 1 x 1 x 0.5 column on its base: step 1 under gravity and a top pressure;
    # step 2 adds a body force up and a pressure on the (held) base, OP=NEW on its second card:
    # Abaqus removes the gravity (*DLOAD, OP=NEW) or the top pressure (*DSLOAD, OP=NEW).  The
    # top's uz: -p L / E, -rho g L^2 / (2 E), +b L^2 / (2 E) (converted before: both loads kept)
    column = ("*Node\n1, 0., 0., 0.\n2, 1., 0., 0.\n3, 1., 1., 0.\n4, 0., 1., 0.\n5, 0., 0., 0.5\n"
              "6, 1., 0., 0.5\n7, 1., 1., 0.5\n8, 0., 1., 0.5\n*Element, type=C3D8, elset=EALL\n"
              "1, 1, 2, 3, 4, 5, 6, 7, 8\n*Nset, nset=TOP\n5, 6, 7, 8\n*Surface, name=ST\n"
              "EALL, S2\n*Surface, name=SB\nEALL, S1\n*Solid Section, elset=EALL, material=M\n"
              "*Material, name=M\n*Elastic\n1000., 0.3\n*Density\n1.\n*Boundary\n1, 1, 3\n"
              "2, 2, 3\n3, 3, 3\n4, 1, 1\n4, 3, 3\n*Step\n*Static\n*Dload\n"
              "EALL, GRAV, 9.81, 0., 0., -1.\n*Dsload\nST, P, 1.\n*Node Print, nset=TOP\nU\n"
              "*End Step\n*Step\n*Static\n{}\n*Node Print, nset=TOP\nU\n*End Step\n")
    grav, top, up = -9.81 * 0.25 / 2000.0, -0.5 / 1000.0, 0.25 / 2000.0
    for how, cards, ref in (("*DSLOAD, then *DLOAD, OP=NEW",
                             "*Dsload\nSB, P, 2.\n*Dload, op=NEW\nEALL, BZ, 1.", top + up),
                            ("*DLOAD, then *DSLOAD, OP=NEW",
                             "*Dload\nEALL, BZ, 1.\n*Dsload, op=NEW\nSB, P, 2.", grav + up)):
        src = os.path.join(tmp, "dload_op_new_src.inp")
        with open(src, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(column.format(cards))
        inp = os.path.join(tmp, "dload_op_new.inp")
        convert(src, inp)
        d, status, out = run_ccx(ccx, env, inp)
        uz = [u[2] for u in dat_displacement_history(os.path.join(d, "job.dat"), 7)] \
            if status == "solved" else []
        shutil.rmtree(d, ignore_errors=True)
        if len(uz) != 2:
            print(f"FAIL  dload_op_new ({how}): no top displacement in both steps ({status})")
            print("\n".join(l for l in out.splitlines() if "ERROR" in l))
            failures += 1
            continue
        refs = [grav + top, ref]
        ok = all(abs(v - r) <= 1e-5 * abs(r) for v, r in zip(uz, refs))
        print(f"{'PASS' if ok else 'FAIL'}  dload_op_new ({how}): top uz " + ", ".join(
            f"step {k} {v:+.6e} (expected {r:+.6e})" for k, (v, r) in enumerate(zip(uz, refs), 1)))
        failures += 0 if ok else 1

    # --- body forces after *DLOAD, OP=NEW ----------------------------------------------------
    # ccx 2.23's *DLOAD, OP=NEW keeps the BX / BY / BZ of earlier steps (Abaqus removes them),
    # so the converter writes zero lines for them.  A bar of three unit cubes along x (nu = 0)
    # held at its root, under BX = 3 in step 1: tip ux = b L^2 / (2 E).  Step 2 removes it with
    # OP=NEW and loads the bar by gravity along -x, or its first cube by BX = 2 on an amplitude;
    # or step 3 follows a perturbation step with BX on the bar under gravity (converted before:
    # the BX stayed on, 4.5e-3, 1.3e-2, 4.5e-3)
    bar = ("*Node\n1,0.,0.,0.\n2,1.,0.,0.\n3,1.,1.,0.\n4,0.,1.,0.\n5,0.,0.,1.\n6,1.,0.,1.\n7,1.,1.,1.\n"
           "8,0.,1.,1.\n9,2.,0.,0.\n10,2.,1.,0.\n11,2.,0.,1.\n12,2.,1.,1.\n13,3.,0.,0.\n14,3.,1.,0.\n"
           "15,3.,0.,1.\n16,3.,1.,1.\n*Element, type=C3D8, elset=ALL\n1, 1,2,3,4,5,6,7,8\n"
           "2, 2,9,10,3,6,11,12,7\n3, 9,13,14,10,11,15,16,12\n*Elset, elset=E1\n1\n*Nset, nset=TIP\n16\n"
           "*Material, name=M\n*Elastic\n1000., 0.\n*Density\n1.\n*Solid Section, elset=ALL, material=M\n"
           "*Amplitude, name=A\n0., 1., 1., 1.\n*Boundary\n1, 1, 3\n4, 1, 3\n5, 1, 3\n8, 1, 3\n")
    step = "*Step{}\n*Static\n{}*Node Print, nset=TIP\nU\n*End Step\n"
    bx, grav = 3.0 * 9.0 / 2000.0, -2.0 * 9.0 / 2000.0
    for how, deck, ref in (
            ("gravity after OP=NEW", step.format("", "*Dload\nALL, BX, 3.\n") +
             step.format("", "*Dload, op=NEW\nALL, GRAV, 2., -1., 0., 0.\n"), [bx, grav]),
            ("first cube on an amplitude after OP=NEW", step.format("", "*Dload\nALL, BX, 3.\n") +
             step.format("", "*Dload, op=NEW, amplitude=A\nE1, BX, 2.\n"), [bx, 2.0 / 2000.0]),
            ("after a perturbation step", step.format("", "*Dload\nALL, GRAV, 2., -1., 0., 0.\n") +
             step.format(", perturbation", "*Dload\nALL, BX, 3.\n") + step.format("", ""), [grav, grav])):
        src = os.path.join(tmp, "body_force_src.inp")
        with open(src, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(bar + deck)
        inp = os.path.join(tmp, "body_force.inp")
        convert(src, inp)
        d, status, out = run_ccx(ccx, env, inp)
        ux = [u[0] for u in dat_displacement_history(os.path.join(d, "job.dat"), 16)] \
            if status == "solved" else []
        shutil.rmtree(d, ignore_errors=True)
        if len(ux) < 2:
            print(f"FAIL  dload_op_new_body_force ({how}): no tip displacement in each step ({status})")
            print("\n".join(l for l in out.splitlines() if "ERROR" in l))
            failures += 1
            continue
        got = [ux[0], ux[-1]]
        ok = all(abs(v - r) <= 1e-5 * abs(r) for v, r in zip(got, ref))
        print(f"{'PASS' if ok else 'FAIL'}  dload_op_new_body_force ({how}): tip ux " + ", ".join(
            f"step {k} {v:+.6e} (expected {r:+.6e})" for k, v, r in zip((1, len(ux)), got, ref)))
        failures += 0 if ok else 1

    # --- face loads of different sources from different steps --------------------------------
    # Abaqus adds two loads on one face that another surface, element set or card gives;
    # ccx 2.23 keeps one value per face, which a later step's line replaces, so the converter
    # gives the earlier load again there.  The bar above (nu = 0): a pressure p on its tip face
    # gives tip ux = -3 p / E; body forces b_j on its cubes, sum b_j (j - 0.5) / E.  Converted
    # before: -6e-3 / 0 for the tip (the later step's line alone), 1.7e-2 for the chain
    surfs = "*Surface, name=TIPA\n3, S4\n*Surface, name=TIPB\n3, S4\n*Elset, elset=E23\n2, 3\n" \
            "*Amplitude, name=T, time=total time\n0., 1., 10., 1.\n"
    tip_ux = lambda p: -3.0 * p / 1000.0
    bx_ux = lambda *b: sum(bj * (j + 0.5) for j, bj in enumerate(b)) / 1000.0
    freq_step = "*Step\n*Frequency\n2\n*End Step\n"        # (ccx prints its two modes too)
    for how, deck, ref in (
            ("*DLOAD, then *DSLOAD on the tip face", step.format("", "*Dload\n3, P4, 1.\n") +
             step.format("", "*Dsload\nTIPA, P, 2.\n"), [tip_ux(1.0), tip_ux(3.0)]),
            ("two surfaces, then the second removed", step.format("", "*Dsload\nTIPA, P, 1.\n") +
             step.format("", "*Dsload\nTIPB, P, 2.\n") + step.format("", "*Dsload\nTIPB, P, 0.\n"),
             [tip_ux(1.0), tip_ux(3.0), tip_ux(1.0)]),
            ("a total-time amplitude on both", step.format("", "*Dsload, amplitude=T\nTIPA, P, 1.\n") +
             step.format("", "*Dsload, amplitude=T\nTIPB, P, 2.\n"), [tip_ux(1.0), tip_ux(3.0)]),
            ("after a frequency step", step.format("", "*Dsload\nTIPA, P, 1.\n") + freq_step +
             step.format("", "*Dsload\nTIPB, P, 2.\n"), [tip_ux(1.0), None, None, tip_ux(3.0)]),
            ("body forces given again in a chain", step.format("", "*Dload\nALL, BX, 3.\nE23, BX, 1.\n") +
             step.format("", "*Dload\nE1, BX, 2.\n"), [bx_ux(3.0, 4.0, 4.0), bx_ux(5.0, 4.0, 4.0)])):
        src = os.path.join(tmp, "face_overlap_src.inp")
        with open(src, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(bar + surfs + deck)
        inp = os.path.join(tmp, "face_overlap.inp")
        convert(src, inp)
        d, status, out = run_ccx(ccx, env, inp)
        ux = [u[0] for u in dat_displacement_history(os.path.join(d, "job.dat"), 16)] \
            if status == "solved" else []
        shutil.rmtree(d, ignore_errors=True)
        if len(ux) != len(ref):
            print(f"FAIL  face_load_overlap ({how}): no tip displacement in each step ({status})")
            print("\n".join(l for l in out.splitlines() if "ERROR" in l))
            failures += 1
            continue
        ok = all(abs(v - r) <= 1e-5 * abs(r) for v, r in zip(ux, ref) if r is not None)
        print(f"{'PASS' if ok else 'FAIL'}  face_load_overlap ({how}): tip ux " + ", ".join(
            f"{v:+.6e} (expected {r:+.6e})" for v, r in zip(ux, ref) if r is not None))
        failures += 0 if ok else 1

    # --- concentrated and distributed loads of other sources, amplitudes ---------------------
    # Abaqus adds a node's *CLOAD through one node set to one through another set or its
    # number in a later step; ccx 2.23 keeps one value per node DOF, which the later line
    # replaces, so the earlier line is given again.  A load on a step-time amplitude holds its
    # end value in later steps: given again at that value, plain (also after a ccx *DLOAD,
    # OP=NEW, which the other card's loads come back after); two cards of one step with the
    # same AMPLITUDE and TIME DELAY become one (ccx stops on two copies of one amplitude).
    # Two lines of one source in one step add up, and are given again so (a zero line adds
    # nothing).  The bar above (nu = 0): an axial force F on each tip node gives tip ux =
    # 12 F / E, a tip pressure p -3 p / E.  Converted before: 2.4e-2, 1.2e-2, 2.4e-2 for
    # 3.6e-2 (the later line alone), and ccx stopped on two amplitudes on one face ('*ERROR in
    # loadadd') in the next two; -6e-3, -6e-3, -9e-3, -6e-3 for -9e-3, -9e-3, -1.5e-2, -9e-3
    # in the last four (one line of the source given again, none after its zero line).
    tips ="*Nset, nset=TIPF\n13, 14, 15, 16\n*Nset, nset=TIPG\n13, 14, 15, 16\n*Surface, name=TIPA\n" \
           "3, S4\n*Surface, name=TIPB\n3, S4\n*Amplitude, name=R\n0., 0., 1., 2.\n"
    tip_f = lambda f: 12.0 * f / 1000.0
    tip_p = lambda p: -3.0 * p / 1000.0
    by_number = "".join(f"{n}, 1, 2.\n" for n in (13, 14, 15, 16))
    delayed = "*{}, amplitude=A, time delay=0.\n{}\n"
    for how, deck, ref in (
            ("a node set, then its nodes by number", step.format("", "*Cload\nTIPF, 1, 1.\n") +
             step.format("", "*Cload\n" + by_number), [tip_f(1.0), tip_f(3.0)]),
            ("a step-time amplitude, then another node set", step.format("", "*Cload, amplitude=R\n"
             "TIPF, 1, 1.\n") + step.format("", "*Cload\nTIPG, 1, 1.\n"), [tip_f(2.0), tip_f(3.0)]),
            ("nodes by number after a frequency step", step.format("", "*Cload\nTIPF, 1, 1.\n") +
             "*Step\n*Frequency\n2\n*End Step\n" + step.format("", "*Cload\n" + by_number),
             [tip_f(1.0), None, None, tip_f(3.0)]),
            ("a step-time pressure, then another surface, then OP=NEW", step.format("", "*Dload, "
             "amplitude=R\n3, P4, 1.\n") + step.format("", "*Dsload\nTIPA, P, 0.5\n") +
             step.format("", "*Dsload, op=NEW\nTIPB, P, 1.\n"), [tip_p(2.0), tip_p(2.5), tip_p(3.0)]),
            ("one step's cards with the same amplitude and time delay", step.format("", "".join(
                delayed.format(*c) for c in (("Dload", "3, P4, 1."), ("Dsload", "TIPA, P, 2."),
                                             ("Cload", "TIPF, 1, 1."), ("Cload", "TIPG, 1, 1.")))),
             [tip_p(3.0) + tip_f(2.0)]),
            ("two lines of one surface, then another surface", step.format("", "*Dsload\nTIPA, P, 1.\n"
             "TIPA, P, 1.\n") + step.format("", "*Dsload\nTIPB, P, 1.\n"), [tip_p(2.0), tip_p(3.0)]),
            ("two cards of one surface, the second zero, then another surface", step.format(
                "", "*Dsload\nTIPA, P, 1.\n*Dsload\nTIPA, P, 0.\n") + step.format("", "*Dsload\nTIPB, P, 2.\n"),
             [tip_p(1.0), tip_p(3.0)]),
            ("two step-time lines of one face, then a surface", step.format("", "*Dload, amplitude=R\n"
             "3, P4, 1.\n3, P4, 1.\n") + step.format("", "*Dsload\nTIPA, P, 1.\n"), [tip_p(4.0), tip_p(5.0)]),
            ("two lines of one surface, a frequency step, then another surface", step.format(
                "", "*Dsload\nTIPA, P, 1.\nTIPA, P, 1.\n") + "*Step\n*Frequency\n2\n*End Step\n" +
             step.format("", "*Dsload\nTIPB, P, 1.\n"), [tip_p(2.0), None, None, tip_p(3.0)])):
        src = os.path.join(tmp, "load_overlap_src.inp")
        with open(src, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(bar + tips + deck)
        inp = os.path.join(tmp, "load_overlap.inp")
        convert(src, inp)
        d, status, out = run_ccx(ccx, env, inp)
        ux = [u[0] for u in dat_displacement_history(os.path.join(d, "job.dat"), 16)] \
            if status == "solved" else []
        shutil.rmtree(d, ignore_errors=True)
        if len(ux) != len(ref):
            print(f"FAIL  load_overlap ({how}): no tip displacement in each step ({status})")
            print("\n".join(l for l in out.splitlines() if "ERROR" in l))
            failures += 1
            continue
        ok = all(abs(v - r) <= 1e-5 * abs(r) for v, r in zip(ux, ref) if r is not None)
        print(f"{'PASS' if ok else 'FAIL'}  load_overlap ({how}): tip ux " + ", ".join(
            f"{v:+.6e} (expected {r:+.6e})" for v, r in zip(ux, ref) if r is not None))
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
    # The same cubes with DEPENDENCIES=0 on every *Elastic and *Expansion: a plain table (it
    # was read as unparsable, and the ANISO shear coefficients were not halved).
    with open(os.path.join(EXAMPLES, "thermal_expansion_cubes.inp"), encoding="utf-8") as fh:
        cubes = fh.read()
    for tag, text in (("thermal_expansion_cubes", None),
                      ("thermal_expansion_cubes_dependencies0",
                       cubes.replace("*Elastic\n", "*Elastic, dependencies=0\n")
                       .replace("*Expansion, type=", "*Expansion, dependencies=0, type="))):
        inp = os.path.join(tmp, f"{tag}.inp")
        if text is None:
            convert(os.path.join(EXAMPLES, "thermal_expansion_cubes.inp"), inp)
        else:
            src = os.path.join(tmp, f"{tag}_src.inp")
            with open(src, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
            convert(src, inp)
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
            print(f"FAIL  {tag}: no displacements / stresses ({status})")
            print("\n".join(l for l in out.splitlines() if "ERROR" in l))
            failures += 1
        else:
            sxx_ref = -e_hot * a1 * dt
            errs.append(abs(sig[0] - sxx_ref) / abs(sxx_ref))
            ok = max(errs) < 1e-3
            print(f"{'PASS' if ok else 'FAIL'}  {tag} (isotropic *Elastic + ORTHO/ANISO *Expansion"
                  f"{', all DEPENDENCIES=0' if text else ''}): free strains {errs[0] * 100:.4f}% / {errs[1] * 100:.4f}% off alpha dT, "
                  f"ANISO with shear terms {errs[3] * 100:.4f}% off (alpha_ij dT / 2 for i /= j); "
                  f"held cube at T = 90: strains {errs[2] * 100:.4f}% off, sigma_xx = {sig[0]:+.5f} "
                  f"(analytic {sxx_ref:+.5f})")
            failures += 0 if ok else 1
        shutil.rmtree(d, ignore_errors=True)

    # --- orthotropic / anisotropic *Elastic forms beside an ANISO *Expansion -----------------
    # Beside a TYPE=ANISO expansion, ccx 2.23 also misreads an orthotropic or engineering-
    # constants *Elastic in linear steps where no orientation applies (a free heated cube gets
    # spurious shear strains, near 1e27 with shear terms), and it stops every NLGEOM step on
    # an ANISO expansion ('too many cutbacks').  The converter writes such an *Elastic as ANISO
    # and an unturned ANISO expansion without shear terms as ORTHO.  Each case is a free cube
    # (its strains against alpha dT) and a clamped one (its face reactions against -C alpha dT);
    # the linear deck has turned and unturned materials of every *Elastic form, the NLGEOM one
    # the unturned expansions without shear terms (second-order terms: 1e-2 there).
    res = []
    for cases, nlgeom, tol in ((EXP_FORMS_LINEAR, False, 1e-5), (EXP_FORMS_NLGEOM, True, 1e-2)):
        src = os.path.join(tmp, f"expansion_forms{'_nlgeom' if nlgeom else ''}_abq.inp")
        deck, expect = expansion_forms_deck(cases, nlgeom)
        with open(src, "w", encoding="utf-8") as fh:
            fh.write(deck)
        inp = os.path.join(tmp, f"expansion_forms{'_nlgeom' if nlgeom else ''}.inp")
        convert(src, inp)
        d, status, out = run_ccx(ccx, env, inp)
        errs = expansion_forms_errors(os.path.join(d, "job.dat"), expect) if status == "solved" else None
        res.append((len(cases), status, errs, tol, out))
        shutil.rmtree(d, ignore_errors=True)
    if any(errs is None for _, _, errs, _, _ in res):
        print("FAIL  thermal_expansion_elastic_forms: no displacements / reactions "
              f"({', '.join(status for _, status, _, _, _ in res)})")
        for *_, out in res:
            print("\n".join(l for l in out.splitlines() if "ERROR" in l))
        failures += 1
    else:
        ok = all(max(errs) < tol for _, _, errs, tol, _ in res)
        (n_lin, _, lin, _, _), (n_nl, _, nl, _, _) = res
        print(f"{'PASS' if ok else 'FAIL'}  thermal_expansion_elastic_forms (isotropic / orthotropic / "
              f"engineering-constants / anisotropic *Elastic beside ANISO *Expansion): {n_lin} linear "
              f"cases, free strains {lin[0] * 100:.5f}% / clamped stresses {lin[1] * 100:.5f}% off; "
              f"{n_nl} NLGEOM cases (ANISO without shear terms written as ORTHO) {nl[0] * 100:.3f}% / "
              f"{nl[1] * 100:.3f}% off")
        failures += 0 if ok else 1

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

    # Beam line loads (*DLOAD PY / local P2 / PZ) on B31, B32 and a CIRC B31 run as B32R with
    # midside nodes: the applied resultants are q L, the tip deflections q L^4 / (8 E I).
    inp = os.path.join(tmp, "lineload.inp")
    convert(os.path.join(EXAMPLES, "beam_line_load_cantilever.inp"), inp)
    applied = {"A": [0.0] * 3, "B": [0.0] * 3, "C": [0.0] * 3}
    in_cload = False
    for ln in open(inp, encoding="utf-8"):
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

    # A follower traction normal to its faces under NLGEOM is a ccx pressure (Abaqus applies
    # its normal part along the current normal per unit current area, as ccx's NLGEOM pressure
    # acts): a cube / square turned 90 degrees about z by its held face, a unit traction
    # pushing into the far face — the reaction turns with it, p A (cos, sin) of the angle
    # (fixed nodal forces would keep it at (1, 0)); the far corner moves with the rotation.
    for form, how in (("3d", "C3D8 face, *DSLOAD TRVEC"), ("2d", "CPE4 edge, *DLOAD TRVEC2")):
        src, inp = os.path.join(tmp, "follower_src.inp"), os.path.join(tmp, "follower.inp")
        with open(src, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(follower_turning_deck(form))
        rep, conv = convert(src, inp)
        d, status, out = run_ccx(ccx, env, inp)
        rf = [rows[0] for _, rows in dat_history(os.path.join(d, "job.dat"), "total force", "LEFT")]
        u = dat_displacements(os.path.join(d, "job.dat")).get(3)
        shutil.rmtree(d, ignore_errors=True)
        if status != "solved" or len(rf) != 6 or u is None:
            print(f"FAIL  follower_traction_turning ({how}): {status}, {len(rf)} reactions")
            print("\n".join(l for l in out.splitlines() if "ERROR" in l)[:400])
            failures += 1
            continue
        err = max(math.hypot(f[0] - math.cos(math.radians(15 * k)), f[1] - math.sin(math.radians(15 * k)))
                  for k, f in enumerate(rf, 1))
        moved = math.hypot(u[0] + 2.0, u[1])               # corner (1, 1) turned to (-1, 1)
        ok = err < 2e-3 and moved < 1e-2 and not conv.reduced_physics and "*CLOAD" not in \
            open(inp, encoding="utf-8").read()
        print(f"{'PASS' if ok else 'FAIL'}  follower_traction_turning ({how}): reaction at 90 deg "
              f"({rf[-1][0]:+.5f}, {rf[-1][1]:+.5f}) (follower (0, 1); dead (1, 0)), largest miss "
              f"over the 6 steps {err:.1e}; far corner u = ({u[0]:+.4f}, {u[1]:+.4f}) (turned: (-2, 0))")
        failures += 0 if ok else 1

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
    cook = open(os.path.join(EXAMPLES, "cook_membrane_traction.inp"), encoding="utf-8").read().replace(
        "*NODE PRINT, NSET=C\nU\n", "*NODE PRINT, NSET=RIGHT, GLOBAL=YES\nU\n")
    edge = ("*NSET, NSET=RIGHT_LOW, GENERATE\n3201, 3216, 1\n*NSET, NSET=RIGHT_UP, GENERATE\n"
            f"3217, 3233, 1\n*TRANSFORM, NSET=RIGHT_LOW, TYPE=R\n{cs!r}, {sn!r}, 0., {sn!r}, {-cs!r}, 0.\n"
            "*TRANSFORM, NSET=RIGHT_UP, TYPE=C\n10., 20., 0., 10., 20., 1.\n")
    block = open(os.path.join(EXAMPLES, "traction_transformed_face.inp"), encoding="utf-8").read()
    for name, how, decks in (
            ("traction_transformed_face", "C3D20R face, rectangular + cylindrical",
             (block, re.sub(r"(?m)^\*TRANSFORM.*\n.*\n", "", block))),
            ("cook_membrane_traction", "CPS8 edge, in-plane rectangular + cylindrical",
             (cook.replace("*MATERIAL", edge + "*MATERIAL", 1), cook))):
        u, bad = [], ""
        for text in decks:
            src, inp = os.path.join(tmp, "transform_src.inp"), os.path.join(tmp, "transform.inp")
            with open(src, "w", encoding="utf-8", newline="\n") as fh:
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
        err = ccx_ratio(max(abs(a - b) for n in u[1] for a, b in zip(u[0][n], u[1][n])), scale)
        ok = err <= 1e-6
        print(f"{'PASS' if ok else 'FAIL'}  {name} with *TRANSFORM ({how}): u at {len(u[1])} nodes "
              f"differs from the model without it by {err:.1e} of max |u| ({scale:.4g})")
        failures += 0 if ok else 1

    # --- body loads written with blank fields -----------------------------------------------
    # Abaqus (and ccx) read a blank *DLOAD field as zero; a dropped one moves the fields after
    # it up.  Gravity along -z on a clamped column ('COLUMN, GRAV, 9810., , , -1.' pulled along
    # -x) and a quarter disc spinning about the z axis through the origin (a blank axis point
    # left the axis direction (0, 0, 0): NaN; blank axis components 1-2 made it the x axis).
    # The base must carry the column's weight rho g V along +z (less the load ccx applies at
    # the base nodes themselves, half the bottom element's weight), and the disc's radial
    # displacement must be the plane-stress rotating-disc solution (C3D20 mesh: 0.34 % off).
    weight = 7.85e-9 * 9810.0 * 10.0 * 10.0 * 100.0

    def spun(r, a=20.0, b=100.0, nu=0.3):                     # rho w^2 = 7.85e-3, E = 210000
        return 7.85e-3 / (8 * 210000.0) * ((3 + nu) * (1 - nu) * (a * a + b * b) * r
                                            + (3 + nu) * (1 + nu) * a * a * b * b / r
                                            - (1 - nu * nu) * r ** 3)
    blank = open(os.path.join(EXAMPLES, "dload_blank_fields.inp"), encoding="utf-8").read()
    for how, text in (("element sets; blank axis point and axis components 1-2", blank),
                      ("no element set for gravity; blank axis components 1-2", blank.replace(
                          "\nCOLUMN, GRAV, 9810., , , -1.\n", "\n, GRAV, 9810., , , -1.\n").replace(
                          "\nDISC, CENTRIF, 1.E6, , , , , , 1.\n",
                          "\nDISC, CENTRIF, 1.E6, 0., 0., 0., , , 1.\n"))):
        src, inp = os.path.join(tmp, "blank_src.inp"), os.path.join(tmp, "blank.inp")
        with open(src, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        convert(src, inp)
        d, status, out = run_ccx(ccx, env, inp)
        rf = dat_history(os.path.join(d, "job.dat"), "total force", "BASE")
        u = dat_displacements(os.path.join(d, "job.dat"))
        shutil.rmtree(d, ignore_errors=True)
        if status != "solved" or not rf or 1001 not in u or 1009 not in u:
            print(f"FAIL  dload_blank_fields ({how}): {status}, no base reaction or disc "
                  f"displacement")
            print("\n".join(l for l in out.splitlines() if "ERROR" in l)[:400])
            failures += 1
            continue
        fx, fy, fz = rf[-1][1][0]
        err_rf = max(abs(fx), abs(fy), abs(fz - 0.95 * weight)) / weight
        err_u = max(abs(u[n][0] / spun(r) - 1) for n, r in ((1001, 20.0), (1009, 100.0)))
        ok = err_rf < 1e-6 and err_u < 0.01
        print(f"{'PASS' if ok else 'FAIL'}  dload_blank_fields ({how}): base reaction "
              f"({fx:+.3g}, {fy:+.3g}, {fz:+.7f}) (0, 0, 0.95 rho g V = {0.95 * weight:+.7f}); disc "
              f"u_r = {u[1001][0]:.5e} / {u[1009][0]:.5e} at r = 20 / 100 (theory {spun(20.0):.5e} / "
              f"{spun(100.0):.5e}, {err_u * 100:.2f}% off)")
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
    deck = open(os.path.join(EXAMPLES, "transform_spherical_rigid.inp"), encoding="utf-8").read()
    u, bad = [], ""
    for text in (deck, global_twin(deck)):
        src, inp = os.path.join(tmp, "local_src.inp"), os.path.join(tmp, "local.inp")
        with open(src, "w", encoding="utf-8", newline="\n") as fh:
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
        err = ccx_ratio(max(abs(a - b) for n in u[1] for a, b in zip(u[0][n], u[1][n])), scale)
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

    def same_as(label, text, twin, turn=None, tol=1e-6):
        """Run ``text`` and ``twin`` (the same model in global components) and compare every
        printed displacement (the twin's turned by ``turn``: a rotated twin's back into the
        model's axes); 1 on failure."""
        u, bad = [], ""
        for i, t in enumerate((text, twin)):
            src, inp = os.path.join(tmp, f"ct{i}_src.inp"), os.path.join(tmp, f"ct{i}.inp")
            with open(src, "w", encoding="utf-8", newline="\n") as fh:
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
        if turn:
            u[1] = {n: turn(v) for n, v in u[1].items()}
        scale = max(abs(x) for v in u[1].values() for x in v)
        err = ccx_ratio(max(abs(p - q) for n in u[1] for p, q in zip(u[0][n], u[1][n])), scale)
        ok = err <= tol
        print(f"{'PASS' if ok else 'FAIL'}  {label}: u at {len(u[1])} nodes differs from the "
              f"{'rigidly rotated ' if turn else ''}model without the *TRANSFORM by {err:.1e} of "
              f"max |u| ({scale:.4g})")
        return 0 if ok else 1
    untransformed = lambda t: re.sub(r"(?mi)^\*Transform.*\n.*\n", "", t)  # noqa: E731
    plate = open(os.path.join(EXAMPLES, "connector_transform_plate.inp"), encoding="utf-8").read()
    failures += same_as("connector_transform_plate (JOIN to a rigid plate on a cylindrically "
                        "transformed face, LINK to a transformed node)", plate, untransformed(plate))
    join = open(os.path.join(EXAMPLES, "connector_transform_join.inp"), encoding="utf-8").read()
    failures += same_as("connector_transform_join (JOIN to a transformed face)", join,
                        untransformed(join))
    nl_join = join.replace("*Step\n*Static\n", "*Step, nlgeom=YES\n*Static\n0.1, 1., 1e-6, 0.2\n") \
        .replace("TIP, 1, 1.\nTIP, 2, -2.\nTIP, 3, 0.5", "TIP, 1, 40.\nTIP, 2, -80.\nTIP, 3, 20.")
    failures += same_as("connector_transform_join, NLGEOM x40 (max |u| 2.8 on a unit block)",
                        nl_join, untransformed(nl_join))
    # B's face transformed too: A's local terms then repeat global DOFs in ccx's expansion,
    # which ccx's cascade does not merge where B's axes keep global z, nor under NLGEOM —
    # abq2ccx writes A's nodes through twins (before: 40 % of max |u| off without a message;
    # under NLGEOM the JOINs were commented out)
    b_face = lambda t, typ, data: t.replace(  # noqa: E731
        "*Boundary\nFIX", "*Nset, nset=BFACE\n101, 104, 107, 110, 113, 116, 119, 122\n125\n"
                          f"*Transform, nset=BFACE, type={typ}\n{data}\n*Boundary\nFIX", 1)
    failures += same_as("connector_transform_join with B's face turned about z (twin nodes)",
                        b_face(join, "R", "0.8, 0.6, 0., -0.6, 0.8, 0."), untransformed(join))
    failures += same_as("connector_transform_join, NLGEOM x40, with B's face in cylindrical axes "
                        "(twin nodes)", b_face(nl_join, "C", "0.3, -0.2, -0.4, 1.1, 0.9, 1.6"),
                        untransformed(nl_join))
    hinge = open(os.path.join(EXAMPLES, "connector_hinge_bodies.inp"), encoding="utf-8").read().replace(
        "*Node Print, nset=OUT", "*Node Print, nset=OUT, global=YES")
    rect, cyl = ("R", (1., 2., 0.5), (-1., 0.3, 1.)), ("C", (0.3, -0.2, -0.4), (1.1, 0.9, 1.6))
    failures += same_as("connector_hinge_bodies with a rectangular *TRANSFORM on reference point 1",
                        with_transform(hinge, 1, *rect, (0., 0., 0.)), hinge)
    failures += same_as("connector_hinge_bodies with a cylindrical *TRANSFORM on reference point 3 "
                        "(its moment in the local axes)",
                        with_transform(hinge, 3, *cyl, (0.2, 0.5, -0.1)), hinge)
    ground = open(os.path.join(EXAMPLES, "connector_ground_hinge.inp"), encoding="utf-8").read().replace(
        "*Node Print, nset=OUT", "*Node Print, nset=OUT, global=YES")
    failures += same_as("connector_ground_hinge, NLGEOM, with a rectangular *TRANSFORM on its "
                        "reference point (moments in the local axes)",
                        with_transform(ground, 3, *rect, (0.2, 0.5, -0.1)), ground)

    # --- *MPC PIN / TIE / LINK on nodes with a *TRANSFORM ----------------------------------
    # Abaqus' PIN, TIE and LINK constrain the global displacements whatever the nodes'
    # transforms (its verification decks xmpcpinxt, xmpctiext and xmpclnk3t give the results
    # without them), and ccx reads *EQUATION terms on a transformed node in its local axes:
    # abq2ccx writes them there, one local term per node and equation — through an
    # untransformed twin of the node where it would need several, since ccx 2.23
    # mis-assembles an equation that holds a DOF twice.  examples/mpc_transform.inp is an
    # orthotropic model on an uneven mesh, so that no symmetry hides such an error: PIN and
    # TIE across an interface whose faces have a cylindrical and a rectangular transform, a
    # face pinned to a reference point, a LINK to a transformed node; then with a rectangular
    # or cylindrical transform on the loaded reference point (its load in the local axes),
    # and under NLGEOM (the LINK as ccx's *MPC BEAM).  The equations in global components
    # (abq2ccx before) miss here by 103-111 % of max |u| (ccx only warns of a zero coefficient
    # in cascade), in the probes by 44-190 % without a message, or stop ccx.
    mpc_tr = open(os.path.join(EXAMPLES, "mpc_transform.inp"), encoding="utf-8").read()
    rp_xyz = (2.6, 0.35, 0.2)
    failures += same_as("mpc_transform (PIN / TIE across faces with different *TRANSFORMs, a "
                        "LINK to a transformed node)", mpc_tr, untransformed(mpc_tr))
    failures += same_as("mpc_transform with a rectangular *TRANSFORM on the loaded reference point",
                        with_transform(mpc_tr, 301, *rect, rp_xyz), untransformed(mpc_tr))
    failures += same_as("mpc_transform with a cylindrical *TRANSFORM on the loaded reference point",
                        with_transform(mpc_tr, 301, *cyl, rp_xyz), untransformed(mpc_tr))
    nl_mpc_tr = mpc_tr.replace("*Step\n*Static\n", "*Step, nlgeom=YES\n*Static\n0.1, 1., 1e-6, 0.2\n") \
        .replace("301, 1, 2.\n301, 2, -3.\n301, 3, 1.", "301, 1, 10.\n301, 2, -15.\n301, 3, 5.")
    failures += same_as("mpc_transform, NLGEOM x5, with a cylindrical *TRANSFORM on the reference "
                        "point", with_transform(nl_mpc_tr, 301, *cyl, rp_xyz),
                        untransformed(nl_mpc_tr))
    # A deck's own *EQUATIONs that hold a DOF twice in ccx: a term written twice, or several
    # local translations of a transformed node whose axes share a global component.
    # examples/equation_tie.inp ties two orthotropic blocks on uneven meshes by u_b - u_a = 0;
    # written with each a-term split in two (and a cancelling pair), or in the local axes of a
    # cylindrical *TRANSFORM on block A's face nodes, it must give the same displacements
    # (abq2ccx sums the terms, and writes the local ones on the nodes' twins).  As written,
    # ccx 2.23 missed by 78 % and 108-130 % of max |u| without a message, and did not converge
    # under NLGEOM.
    tie = open(os.path.join(EXAMPLES, "equation_tie.inp"), encoding="utf-8").read()
    tie_eq = re.compile(r"\*Equation\n2\n(\d+), (\d), 1\., (\d+), \d, -1\.\n")
    tie_xyz = {int(f[0]): [float(x) for x in f[1:4]] for f in
               (ln.split(",") for ln in tie.split("*Node\n", 1)[1].split("*", 1)[0].splitlines())}

    def split_terms(deck):
        def sub(m):
            b, d, a = m.groups()
            pair = f", {a}, {int(d) % 3 + 1}, 0.25, {a}, {int(d) % 3 + 1}, -0.25" if d == "2" else ""
            return f"*Equation\n{5 if pair else 3}\n{b}, {d}, 1., {a}, {d}, -0.4, {a}, {d}, -0.6{pair}\n"
        return tie_eq.sub(sub, deck)

    def local_terms(deck, typ, a, b):
        def sub(m):
            bn, d, an = m.groups()
            ax = local_axes(typ, a, b, tie_xyz[int(an)])
            return (f"*Equation\n4\n{bn}, {d}, 1., " +
                    ", ".join(f"{an}, {j + 1}, {-ax[j][int(d) - 1]:.15g}" for j in range(3)) + "\n")
        card = f"*Transform, nset=FACE, type={typ}\n" + ", ".join(repr(float(v)) for v in a + b) + "\n"
        return tie_eq.sub(sub, deck).replace("*Step", card + "*Step", 1)
    nl_tie = tie.replace("*Step\n*Static\n", "*Step, nlgeom=YES\n*Static\n0.1, 1., 1e-6, 0.2\n") \
        .replace("TOP, 1, 2.\nTOP, 2, -1.5\nTOP, 3, 3.", "TOP, 1, 20.\nTOP, 2, -15.\nTOP, 3, 30.")
    failures += same_as("equation_tie with each term of block A split in two (and a cancelling "
                        "pair)", split_terms(tie), tie)
    failures += same_as("equation_tie in the local axes of a cylindrical *TRANSFORM on block A's "
                        "face", local_terms(tie, *cyl), tie)
    failures += same_as("equation_tie, NLGEOM x10 (max |u| 1.3), with split terms",
                        split_terms(nl_tie), nl_tie)
    failures += same_as("equation_tie, NLGEOM x10, in the local axes of a cylindrical *TRANSFORM",
                        local_terms(nl_tie, *cyl), nl_tie)
    # A *RIGID BODY whose REF NODE is one of its own nodes: ccx 2.23 prints the reaction force
    # there as that node's own elements' forces alone (abq2ccx before: 1e-15), so the body gets
    # a free reference node at the same place.  examples/rigid_ref_member_contact.inp pushes
    # three rigid cubes onto elastic blocks through contact, the REF NODE a cube node (PIN NSET
    # and ELSET form) or a free node: each reference node's RF3 must be its supports' total.
    for nl_rr in (True, False):
        src = open(os.path.join(EXAMPLES, "rigid_ref_member_contact.inp"), encoding="utf-8").read()
        src_path, inp = os.path.join(tmp, "rr_src.inp"), os.path.join(tmp, "rr.inp")
        with open(src_path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(src if nl_rr else src.replace("*Step, nlgeom=YES", "*Step"))
        convert(src_path, inp)
        d, status, out = run_ccx(ccx, env, inp)
        dat = os.path.join(d, "job.dat")
        rf = {s: rows[-1][3] for _, t, s, _, rows in A.dat_blocks(dat) if t == "forces" and rows}
        tot = dat_totals(dat)[-3:] if status == "solved" else []
        got = [rf.get(f"REF_{k}") for k in "ABR"]
        ok = len(tot) == 3 and None not in got and all(
            abs(g + t[2]) <= 1e-6 * abs(t[2]) and abs(t[2]) > 1.0 for g, t in zip(got, tot))
        print(f"{'PASS' if ok else 'FAIL'}  rigid_ref_member_contact ({'NLGEOM' if nl_rr else 'linear'}, "
              f"{status}): RF3 at the reference nodes (cube node, ELSET cube node, free node) = "
              f"{', '.join('-' if g is None else f'{g:.6g}' for g in got)}; supports "
              f"{', '.join(f'{t[2]:.6g}' for t in tot)}")
        failures += 0 if ok else 1
        shutil.rmtree(d, ignore_errors=True)
    # Rotational BCs and moments on DOFs 4-6 of nodes with a *TRANSFORM, which ccx 2.23 applies
    # about the global axes on a kinematic reference point and a knot (and as clashing mean-
    # rotation MPCs on a plain beam node): the reference point's coupling becomes a *RIGID BODY
    # whose ROT NODE has its axes, the beam tip a knot with its moments in global components.
    # The twin: no *TRANSFORM, a *RIGID BODY with an untransformed ROT NODE 101 whose rotation
    # about local 2 an *EQUATION holds, a knot beam at the tip, everything in global components.
    rot_deck = open(os.path.join(EXAMPLES, "transform_rotations.inp"), encoding="utf-8").read()
    ea = local_axes("C", (0.3, -0.2, -0.4), (1.1, 0.9, 1.6), (4.0, 0.5, 0.5))
    eb = local_axes("R", (1., 2., 0.5), (-1., 0.3, 1.), (2.5, 3., 0.))

    def components(node, base, pairs, axes):
        return [f"{node}, {base + k + 1}, {sum(v * axes[j][k] for j, v in pairs)!r}" for k in range(3)]
    twin = re.sub(r"(?m)^\*Transform.*\n.*\n", "", rot_deck)
    order = sorted(range(3), key=lambda k: -abs(ea[1][k]))
    twin = twin.replace(
        "*Surface, type=NODE, name=FACES\nFACE\n*Coupling, constraint name=END, ref node=RP, "
        "surface=FACES\n*Kinematic\n",
        "*Node\n101, 4.0, 0.5, 0.5\n212, 5.05, 3.05, 0.05\n*Rigid Body, ref node=RP, rot node=101, "
        "tie nset=FACE\n*Equation\n3\n" + ", ".join(f"101, {k + 1}, {ea[1][k]!r}" for k in order)
        + "\n*Element, type=B31, elset=KNOT\n30, 211, 212\n*Beam Section, elset=KNOT, material=M, "
        "section=RECT\n0.05, 0.05\n1., -1., 0.\n")
    twin = twin.replace("*Boundary\nRP, 5, 5\n", "")
    loads = "\n".join(components("RP", 0, [(0, 0.5)], ea) + components(101, 0, [(0, 0.3), (2, 2.)], ea)
                      + components("TIP", 0, [(1, 0.1)], eb)
                      + components("TIP", 3, [(0, 0.5), (2, -0.3)], eb))
    twin = re.sub(r"(?s)\*Cload\n.*?\*Node Print", "*Cload\n" + loads + "\n*Node Print", twin)
    failures += same_as("transform_rotations (a kinematic reference point with a cylindrical "
                        "*TRANSFORM, its rotation about local 2 held, local moments; a beam tip "
                        "with local moments)", rot_deck, twin)
    nl = lambda t: t.replace("*Step\n*Static\n", "*Step, nlgeom=YES, inc=200\n*Static\n0.05, 1., 1e-6, 0.05\n")  # noqa: E731
    failures += same_as("transform_rotations, NLGEOM", nl(rot_deck), nl(twin))
    # Rotational BCs and a moment on plain S4 nodes with a *TRANSFORM, kept in the local axes
    # (ccx's mean-rotation MPCs read them there), in steps ccx runs through its nonlinear
    # solver, where it makes no knot (only in a dynamic step): they must match the rigidly
    # rotated model whose global axes are those local axes.  (Both steps are 12-18 % off the
    # linear step's answer, as the model without a *TRANSFORM is too.)
    strip_axes = local_axes("R", (1., 1., 0.3), (-1., 1., 0.), (0., 0., 0.))

    def transformed_strip(turned, mat="", step="*Step"):
        xyz = {1: (0., 0., 0.), 2: (1., 0., 0.), 3: (1., 1., 0.), 4: (0., 1., 0.), 5: (2., 0., 0.),
               6: (2., 1., 0.)}
        if turned:
            xyz = {n: tuple(_dot(e, x) for e in strip_axes) for n, x in xyz.items()}
        return ("*Node, nset=ALLN\n" + "".join(f"{n}, {x[0]!r}, {x[1]!r}, {x[2]!r}\n" for n, x in xyz.items())
                + "*Element, type=S4, elset=E\n1, 1, 2, 3, 4\n2, 2, 5, 6, 3\n*Shell Section, elset=E, "
                "material=M\n0.1\n*Material, name=M\n*Elastic\n1000., 0.3\n" + mat
                + ("" if turned else "*Nset, nset=TR\n5, 6\n*Transform, nset=TR, type=R\n1., 1., 0.3, -1., 1., 0.\n")
                + "*Boundary\n1, 1, 6\n4, 1, 6\n" + step + "\n*Static\n*Boundary\n5, 4, 5\n*Cload\n6, 4, 0.1\n"
                "*Node Print, nset=ALLN, global=yes\nU\n*End Step\n")
    back = lambda v: tuple(sum(strip_axes[k][i] * v[k] for k in range(3)) for i in range(3))  # noqa: E731
    plastic = "*Plastic\n1e6, 0.\n"
    failures += same_as("transform_shell_rotations (local rotation BCs and moment on S4 nodes), a "
                        "*STATIC step with a *PLASTIC never reached", transformed_strip(False, plastic),
                        transformed_strip(True, plastic), back)
    failures += same_as("transform_shell_rotations, NLGEOM", transformed_strip(False, step="*Step, nlgeom"),
                        transformed_strip(True, step="*Step, nlgeom"), back, 1e-4)

    # --- two rotational BCs on a shell node, the free axis in the shell plane ---------------
    # ccx 2.23 holds both in-plane rotations for two rotational BCs on a shell node, so also
    # the free one where its axis is not the normal; abq2ccx writes one line (the in-plane
    # rotation about n x free axis).  The S8R strip turned 15 deg about z, its tip holding
    # the rotations about x and y (0.01 / 0.02 rad, linear and NLGEOM) and twisted about z, must
    # match the strip along x (where x is the drilling rotation, which ccx drops) turned back;
    # half a cylindrical panel with ZSYMM on its plane of symmetry must match the whole panel
    # (S8R and S4).  The two lines were 52-99 % off (probes).
    def pair_twin(label, text, twin, turn=None, tol=1e-6, moved=0.0):
        u, notes, flags = [], [], []
        for i, t in enumerate((text, twin)):
            src, inp = os.path.join(tmp, f"rp{i}_src.inp"), os.path.join(tmp, f"rp{i}.inp")
            with open(src, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(t)
            rep, conv = convert(src, inp)
            notes.append("written as one rotation line" in rep.text())
            flags.append(bool(conv.reduced_physics))
            d, status, _ = run_ccx(ccx, env, inp)
            u.append(dat_displacements(os.path.join(d, "job.dat")) if status == "solved" else {})
            shutil.rmtree(d, ignore_errors=True)
        if not u[0] or u[0].keys() != u[1].keys():
            print(f"FAIL  {label}: no displacements to compare")
            return 1
        if turn:
            u[1] = {n: turn(v) for n, v in u[1].items()}
        scale = max(math.hypot(*v) for v in u[1].values())
        err = ccx_ratio(max(math.dist(u[0][n], u[1][n]) for n in u[1]), scale)
        ok = err <= tol and scale >= moved and notes[0] and flags == [False, False]
        print(f"{'PASS' if ok else 'FAIL'}  {label}: u at {len(u[1])} nodes {err:.1e} of max |u| "
              f"({scale:.4g}) off the twin; {'one rotation line' if notes[0] else 'NOT rewritten'}")
        return 0 if ok else 1
    c15, s15 = math.cos(math.radians(15.0)), math.sin(math.radians(15.0))
    turn15 = lambda v: (c15 * v[0] - s15 * v[1], s15 * v[0] + c15 * v[1], v[2])  # noqa: E731
    v4, v5 = 0.01, 0.02
    back = ((4, c15 * v4 + s15 * v5), (5, -s15 * v4 + c15 * v5))    # the same rotations, turned back
    failures += pair_twin("shell_rotation_pair_strip (S8R strip turned 15 deg, its tip holding the "
                          "rotations about x and y, twisted about z)",
                          tilted_strip_deck(15.0, ((4, v4), (5, v5))), tilted_strip_deck(0.0, back),
                          turn15, moved=3.0)
    failures += pair_twin("shell_rotation_pair_strip, NLGEOM, torque /20",
                          tilted_strip_deck(15.0, ((4, v4), (5, v5)), 0.05, True),
                          tilted_strip_deck(0.0, back, 0.05, True), turn15, 1e-3, moved=0.05)
    for typ in ("S8R", "S4"):
        failures += pair_twin(f"shell_rotation_pair_symmetry ({typ} cylindrical panel: half of it, ZSYMM "
                              f"on its plane of symmetry)", symmetric_panel_deck(typ, True),
                              symmetric_panel_deck(typ, False), moved=0.01)
    failures += pair_twin("shell_rotation_pair_symmetry, S8R, NLGEOM", symmetric_panel_deck("S8R", True, 5.0, True),
                          symmetric_panel_deck("S8R", False, 5.0, True), tol=1e-4, moved=0.05)

    # --- translational BCs on S8R corner nodes with a *TRANSFORM -----------------------------
    # ccx 2.23 ties such a BC (an MPC in global coordinates) to the node's middle expanded node
    # only; abq2ccx takes the node out of the *TRANSFORM, its BCs and loads in global components.
    # The plate with its loaded and moved corner under a turned *TRANSFORM and its held corner
    # under a tilted one must match the plate in global components, the half panel with a
    # cylindrical *TRANSFORM on all nodes the whole panel without (before: 2.1 % / 1.3 % off).
    def corner_twin(label, text, twin, tol=1e-9, moved=0.0):
        u, notes, why = [], [], []
        for i, t in enumerate((text, twin)):
            src, inp = os.path.join(tmp, f"tc{i}_src.inp"), os.path.join(tmp, f"tc{i}.inp")
            with open(src, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(t)
            rep, conv = convert(src, inp)
            notes.append(("taken out of the *TRANSFORM" in rep.text(), list(conv.reduced_physics)))
            for _ in range(5):       # ccx 2.23 crashes at random at a *DYNAMIC step's start after
                d, status, out = run_ccx(ccx, env, inp)     # a *STATIC one (tempload): rerun it
                if status != "failed" or "*ERROR" in out or "Job finished" in out:
                    break
                shutil.rmtree(d, ignore_errors=True)
            u.append(dat_displacements(os.path.join(d, "job.dat")) if status == "solved" else {})
            if status != "solved":                  # say how ccx ended (the last lines it printed)
                tail = [ln.strip() for ln in out.splitlines() if ln.strip()][-3:]
                why.append(f"{('the deck', 'its twin')[i]} {status}: {' | '.join(tail)}")
            shutil.rmtree(d, ignore_errors=True)
        if not u[0] or u[0].keys() != u[1].keys():
            print(f"FAIL  {label}: no displacements to compare" + (f" ({'; '.join(why)})" if why else ""))
            return 1
        scale = max(math.hypot(*v) for v in u[1].values())
        err = ccx_ratio(max(math.dist(u[0][n], u[1][n]) for n in u[1]), scale)
        ok = err <= tol and scale >= moved and notes[0][0] and not notes[1][0] and notes[0][1] == notes[1][1]
        print(f"{'PASS' if ok else 'FAIL'}  {label}: u at {len(u[1])} nodes {err:.1e} of max |u| "
              f"({scale:.4g}) off the model without the *TRANSFORM; "
              f"{'taken out of it' if notes[0][0] else 'NOT taken out'}")
        return 0 if ok else 1
    failures += corner_twin("transform_shell_corner_plate (S8R corners: moved and loaded under a "
                            "turned *TRANSFORM, held under a tilted one)", corner_transform_plate_deck(True),
                            corner_transform_plate_deck(False), moved=0.01)
    failures += corner_twin("transform_shell_corner_panel (half a cylindrical S8R panel, a cylindrical "
                            "*TRANSFORM on all nodes, ZSYMM and the clamp in its axes)",
                            symmetric_panel_deck("S8R", True, transform=True), symmetric_panel_deck("S8R", False),
                            moved=0.01)
    # a knot (an S4 strip's fold) with a transformed BC in a *DYNAMIC step after a *STATIC one,
    # which ccx did not meet (before: 0.6 % of max |u| off)
    failures += corner_twin("transform_knot_dynamic (an S4 strip's fold node moved under a turned "
                            "*TRANSFORM, *STATIC then *DYNAMIC)", folded_strip_deck(True),
                            folded_strip_deck(False), moved=0.02)

    # --- shell/beam rotations in a step ccx runs nonlinear without NLGEOM -----------------
    # ccx turns the mean-rotation MPCs of rotational BCs and moments, and its knots' RIGID
    # MPCs, with the finite rotation there; abq2ccx warns (reduced physics, no linear form).
    # Each deck with a *PLASTIC never reached against its elastic twin (a linear step): the
    # drift the warning quotes (about theta^2 of max |u|; a knot 0.4-1 % at 0.01 rad), none
    # for held rotations
    def finite_drift(label, deck, lo, hi, moved):
        u, flagged = [], []
        for i, t in enumerate((deck, deck.replace(plastic, ""))):
            src, inp = os.path.join(tmp, f"fr{i}_src.inp"), os.path.join(tmp, f"fr{i}.inp")
            with open(src, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(t)
            _, conv = convert(src, inp)
            flagged.append(bool(conv.reduced_physics))
            d, status, _ = run_ccx(ccx, env, inp)
            u.append(dat_displacements(os.path.join(d, "job.dat")) if status == "solved" else {})
            shutil.rmtree(d, ignore_errors=True)
        if not u[0] or u[0].keys() != u[1].keys():
            print(f"FAIL  {label}: no displacements to compare")
            return 1
        scale = max(math.hypot(*v) for v in u[1].values())
        err = ccx_ratio(max(math.dist(u[0][n], u[1][n]) for n in u[1]), scale)
        ok = lo <= err <= hi and scale >= moved and flagged == [lo > 0, False]
        print(f"{'PASS' if ok else 'FAIL'}  {label}: u at {len(u[1])} nodes {err:.2e} of max |u| "
              f"({scale:.4g}) off the elastic twin's linear step (expected {lo:g}-{hi:g}); "
              f"{'warned as' if flagged[0] else 'not'} reduced physics")
        return 0 if ok else 1
    strip = ("*Node, nset=ALLN\n1, 0., 0., 0.\n2, 1., 0., 0.\n3, 1., 1., 0.\n4, 0., 1., 0.\n5, 2., 0., "
             "0.\n6, 2., 1., 0.\n*Element, type=S4, elset=E\n1, 1, 2, 3, 4\n2, 2, 5, 6, 3\n*Shell "
             "Section, elset=E, material=M\n0.1\n*Material, name=M\n*Elastic\n1000., 0.3\n" + plastic +
             "*Boundary\n1, 1, 6\n4, 1, 6\n*Step\n*Static\n{}*Node Print, nset=ALLN\nU\n*End Step\n")
    failures += finite_drift("finite_rotation_shell_bc (S4 strip, its free edge turned 0.1 rad by a "
                             "*BOUNDARY, a *STATIC step with a *PLASTIC never reached)",
                             strip.format("*Boundary\n5, 5, 5, 0.1\n6, 5, 5, 0.1\n"), 1e-3, 2e-2, 0.09)
    failures += finite_drift("finite_rotation_shell_moment (the strip turned 0.1 rad by edge moments)",
                             strip.format("*Cload\n5, 5, 0.002243\n6, 5, 0.002243\n"), 1e-3, 2e-2, 0.09)
    failures += finite_drift("finite_rotation_shell_held (the strip's edge rotations held at zero, "
                             "edge forces)", strip.format("*Boundary\n5, 4, 6\n6, 4, 6\n*Cload\n5, 3, "
                                                          "0.001\n6, 3, 0.001\n"), 0.0, 1e-9, 0.01)
    failures += finite_drift(
        "finite_rotation_frame_joint (B31 L frame, which ccx knots at its joint, an out-of-plane tip "
        "force turning the joint 0.009 rad)",
        "*Node, nset=ALLN\n1, 0., 0., 0.\n2, 1., 0., 0.\n3, 2., 0., 0.\n4, 2., 1., 0.\n5, 2., 2., 0.\n"
        "*Element, type=B31, elset=E\n1, 1, 2\n2, 2, 3\n3, 3, 4\n4, 4, 5\n*Beam Section, elset=E, "
        "material=M, section=RECT\n0.2, 0.1\n0., 0., -1.\n*Material, name=M\n*Elastic\n1000., 0.3\n"
        + plastic + "*Boundary\n1, 1, 6\n*Step\n*Static\n*Cload\n5, 3, 4.56306e-05\n*Node Print, "
        "nset=ALLN\nU\n*End Step\n", 4e-3, 3e-2, 0.019)

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
    src = open(os.path.join(EXAMPLES, "velocity_bc_bar.inp"), encoding="utf-8").read()
    accel = src.replace("nlgeom=YES\n*Dynamic, Explicit\n , 0.5",
                        "nlgeom=YES, inc=1000\n*Dynamic, direct\n 0.002, 0.5") \
        .replace("type=VELOCITY\n DRIVEN, 3, 3, 0.01", "type=ACCELERATION\n DRIVEN, 3, 3, 0.04")
    for label, text, ref, mean_only in (
            ("explicit, TYPE=VELOCITY", src, lambda z: -0.01 if z < 0.5 else 0.0, True),
            ("implicit, TYPE=ACCELERATION", accel, lambda z: -0.04 * (0.5 - z) if z < 0.5 else 0.0,
             False)):
        tmp_src = os.path.join(tmp, "velocity_bc_bar_src.inp")
        with open(tmp_src, "w", encoding="utf-8", newline="\n") as fh:
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
    # 0.004, in *VISCO sitting there from the first increment, in the coupled step (without
    # inertia: abq2ccx scales the masses away) well above the 0.0004 a ramp would give at
    # t = 0.1.
    # Abaqus/Explicit ignores the value of such a BC and holds the DOF (zero velocity): the
    # driven top stays at 0, and the loaded top, held by one in the second step, stays where
    # the first step left it.
    src = open(os.path.join(EXAMPLES, "default_amplitude_bars.inp"), encoding="utf-8").read()
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
        with open(tmp_src, "w", encoding="utf-8", newline="\n") as fh:
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

    # --- transient coupled temperature-displacement steps without inertia -----------------
    # ccx 2.23 solves a transient *COUPLED TEMPERATURE-DISPLACEMENT step as a dynamic one with
    # the mass of every *DENSITY and *MASS, where Abaqus/Standard neglects inertia; abq2ccx
    # divides the masses by 1e30 and multiplies the specific heats and the GRAV magnitudes by
    # it.  Two bars take their weight, ramped up in step 1 (one also point masses at its top);
    # in step 2 one is heated at its top, the other loaded there by a *CLOAD without an
    # amplitude.  The heated top must be at its static position at every increment: the sag
    # under the weight plus the thermal expansion of the temperatures printed along the bar,
    # which must equal the same model's in *HEAT TRANSFER steps (the heat capacity, density
    # x specific heat, is unchanged).  The loaded top must sink with the ramped weight and be
    # at its static extension from the third increment of step 2 on, having overshot the
    # load's jump by ccx's HHT alpha / (1 + alpha) = 5.26 % at the first and -0.28 % at the
    # second (abq2ccx warns about this).  With the masses as given, the heated top misses its
    # static position by up to 30 % of the expansion and the loaded top swings between -66 %
    # and +63 % of its extension about its static position.
    src = open(os.path.join(EXAMPLES, "coupled_quasistatic_bars.inp"), encoding="utf-8").read()
    heat = src.replace("type=C3D8T", "type=DC3D8").replace("*Coupled Temperature-displacement",
                                                           "*Heat Transfer")
    for cut in ("*Element, type=MASS, elset=WEIGHTS\n201, 17\n202, 18\n203, 19\n204, 20\n",
                "*Mass, elset=WEIGHTS\n 0.25\n", "*Boundary\n BOTTOMS, ENCASTRE\n",
                "*Dload\n BARS, GRAV, 1., 0., 0., -1.\n WEIGHTS, GRAV, 1., 0., 0., -1.\n",
                "*Cload\n LOADED_TOP, 3, 0.25\n", "*Node Print, nset=HEATED_TOP\n U\n",
                "*Node Print, nset=LOADED_TOP\n U\n"):
        heat = heat.replace(cut, "")
    found = {}
    for label, text in (("coupled", src), ("heat", heat)):
        tmp_src = os.path.join(tmp, "coupled_quasistatic_bars_src.inp")
        with open(tmp_src, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        inp = os.path.join(tmp, "coupled_quasistatic_bars.inp")
        convert(tmp_src, inp)
        d, status, out = run_ccx(ccx, env, inp)
        dat = os.path.join(d, "job.dat")
        found[label] = (status, out, {t: {int(r[0]): r[1] for r in rows}
                                      for t, rows in dat_history(dat, "temperatures", "HEATED_AXIS")},
                        dat_history(dat, "displacements", "HEATED_TOP"),
                        dat_history(dat, "displacements", "LOADED_TOP"))
        shutil.rmtree(d, ignore_errors=True)
    status, out, temps, heated, loaded = found["coupled"]
    status_h, out_h, temps_h = found["heat"][:3]
    if status != "solved" or status_h != "solved" or len(heated) != 20 or len(loaded) != 20 or \
            len(temps) != 10 or sorted(temps) != sorted(temps_h):
        print(f"FAIL  coupled_quasistatic_bars: did not solve ({status}; *HEAT TRANSFER twin {status_h})")
        print("\n".join(l for l in (out + out_h).splitlines() if "ERROR" in l)[:400])
        failures += 1
    else:
        rho, g, e, length, mass = 0.15625, 1.0, 1000.0, 4.0, 1.0
        sag = rho * g * length ** 2 / (2 * e)               # under its own weight (both bars)
        dev_t = max(abs(temps[t][n] - temps_h[t][n]) for t in temps for n in temps_h[t])
        dev_h = 0.0
        for t, rows in heated:
            # the heated bar also carries the point masses; in step 2 it grows by alpha times
            # the integral of its (linear-element) temperature along it
            grow = 1e-4 * sum((temps[t][n] + temps[t][n + 4]) / 2 for n in (1, 5, 9, 13)) \
                if t > 1.0 + 1e-9 else 0.0
            ref = -(sag + mass * g * length / e) * min(t, 1.0) + grow
            dev_h = max([dev_h] + [abs(r[2] - ref) for r in rows])
        dev_w = max(abs(r[2] + sag * t) for t, rows in loaded if t <= 1.0 + 1e-9 for r in rows)
        # the loaded top in step 2, as a fraction of the load's static extension 0.004 past its
        # static position: without mass ccx's HHT step gives (1 + alpha) R(n+1) = alpha R(n)
        jump = [(rows[0][2] + sag - 0.004) / 0.004 for t, rows in loaded if t > 1.0 + 1e-9]
        hht = -0.05 / (1.0 - 0.05)
        dev_j = max(abs(x + hht ** (k + 1)) for k, x in enumerate(jump))
        ok = dev_t < 1e-6 and dev_h < 1e-7 and dev_w < 1e-9 and dev_j < 1e-5
        print(f"{'PASS' if ok else 'FAIL'}  coupled_quasistatic_bars: heated top within {dev_h:.1e} "
              f"of its static position (weight + expansion) at 20 increments, temperatures within "
              f"{dev_t:.1e} of *HEAT TRANSFER; loaded top within {dev_w:.1e} of its ramped sag, "
              f"then past its static extension by {jump[0] * 100:+.2f} %, {jump[1] * 100:+.2f} %, "
              f"{jump[2] * 100:+.3f} % of the jump (HHT alpha / (1 + alpha) = {-hht * 100:.2f} %: "
              f"within {dev_j:.1e})")
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
    with open(inp, encoding="utf-8") as fi, open(bare, "w", encoding="utf-8", newline="\n") as fo:
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

    # Two field requests every 0.3 and every 0.2 of the step share no spacing: one *TIME POINTS
    # list of both requests' times (the converter crashed on it).  A bar of three unit cubes
    # (nu = 0, NLGEOM: ccx solves a linear step in one increment) pulled by a ramped dead tip
    # load P t: the section keeps its area, so S11 = P t / A, and the stretch l of the St
    # Venant-Kirchhoff bar solves E (l^2 - 1) / 2 = S11 / l; ux = L (l - 1).
    bar = ("*Node\n1,0.,0.,0.\n2,1.,0.,0.\n3,1.,1.,0.\n4,0.,1.,0.\n5,0.,0.,1.\n6,1.,0.,1.\n7,1.,1.,1.\n"
           "8,0.,1.,1.\n9,2.,0.,0.\n10,2.,1.,0.\n11,2.,0.,1.\n12,2.,1.,1.\n13,3.,0.,0.\n14,3.,1.,0.\n"
           "15,3.,0.,1.\n16,3.,1.,1.\n*Element, type=C3D8, elset=ALL\n1, 1,2,3,4,5,6,7,8\n"
           "2, 2,9,10,3,6,11,12,7\n3, 9,13,14,10,11,15,16,12\n*Nset, nset=TIP\n13, 14, 15, 16\n"
           "*Material, name=M\n*Elastic\n1000., 0.\n*Solid Section, elset=ALL, material=M\n"
           "*Boundary\n1, 1, 3\n4, 1, 3\n5, 1, 3\n8, 1, 3\n*Step, nlgeom\n*Static\n0.1, 1.\n*Cload\n"
           "TIP, 1, 0.25\n*Output, field, time interval=0.3\n*Node Output, nset=TIP\nU\n"
           "*Output, field, time interval=0.2\n*Element Output\nS\n*End Step\n")
    src = os.path.join(tmp, "two_intervals_src.inp")
    with open(src, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(bar)
    inp = os.path.join(tmp, "two_intervals.inp")
    convert(src, inp)
    d, status, out = run_ccx(ccx, env, inp)
    frd = os.path.join(d, "job.frd")
    disp, stress = (frd_blocks(frd, "DISP"), frd_blocks(frd, "STRESS")) if status == "solved" else ([], [])
    shutil.rmtree(d, ignore_errors=True)
    want = [0.2, 0.3, 0.4, 0.6, 0.8, 0.9, 1.0]
    if len(disp) != len(want) or len(stress) != len(want):
        print(f"FAIL  output_two_time_intervals: {len(disp)} DISP / {len(stress)} STRESS .frd "
              f"blocks, expected {len(want)} each ({status})")
        print("\n".join(l for l in out.splitlines() if "ERROR" in l))
        failures += 1
    else:
        def bar_ux(t):
            lam = 1.0 + t / 1000.0
            for _ in range(20):
                lam -= (1000.0 * (lam ** 2 - 1) / 2 - t / lam) / (1000.0 * lam + t / lam ** 2)
            return 3.0 * (lam - 1)
        dev_t = max(abs(t - w) for (t, _), w in zip(disp + stress, want + want))
        dev_u = max(abs(ccx_ratio(v[n][0], bar_ux(t)) - 1) for t, v in disp for n in (13, 14, 15, 16))
        dev_s = max(abs(ccx_ratio(s[0], t) - 1) for t, v in stress for s in v.values())
        ok = dev_t < 1e-9 and dev_u < 1e-5 and dev_s < 1e-4
        print(f"{'PASS' if ok else 'FAIL'}  output_two_time_intervals (*OUTPUT every 0.3 and every "
              f"0.2): .frd U and S at t = {', '.join(f'{t:g}' for t, _ in disp)}; tip ux = "
              f"{disp[-1][1][16][0]:.7f} at t = 1 ({bar_ux(1.0):.7f}); ux within {dev_u:.1e}, "
              f"S11 within {dev_s:.1e} of P t / A")
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
    with open(inp, encoding="utf-8") as fh:
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
        with open(src, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(open(os.path.join(EXAMPLES, "cps4i_slab_bending.inp"), encoding="utf-8").read().replace("CPS4I", kind))
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
        text = open(os.path.join(EXAMPLES, "kinematic_all_dofs.inp"), encoding="utf-8").read()
        for a, b in subs:
            text = text.replace(a, b)
        with open(src, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        inp = os.path.join(tmp, f"kin_{kind}.inp")
        convert(src, inp)
        d, status, out = run_ccx(ccx, env, inp)
        res[kind] = dat_displacements(os.path.join(d, "job.dat")) if status == "solved" else {}
        shutil.rmtree(d, ignore_errors=True)
    nodes = [n for n in range(1, 100) if n in res["kinematic"] and n in res["rigid"]]
    if len(nodes) == 99:
        scale = max(abs(x) for n in nodes for x in res["rigid"][n])
        err = ccx_ratio(max(abs(a - b) for n in nodes for a, b in zip(res["kinematic"][n], res["rigid"][n])),
                        scale)
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
        err = ccx_ratio(max(abs(a - b) for n in uf for a, b in zip(ua[n], uf[n])), scale)
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
    # the part's orientation by nodes, with node c (8, 6, 2) and without (7, 6: the origin is
    # the part's, which moves with I2): each instance's copy takes its own nodes (I2 took I1's)
    src = open(os.path.join(EXAMPLES, "assembly_rotated_instances.inp"), encoding="utf-8").read()
    for tag, line in (("assembly_rotated_instances_nodes", "8, 6, 2"),
                      ("assembly_rotated_instances_nodes_no_c", "7, 6")):
        text = src.replace("*ORIENTATION, NAME=ORI\n1., 1., 0., -1., 1., 0.\n",
                           f"*ORIENTATION, NAME=ORI, DEFINITION=NODES\n{line}\n")
        path = os.path.join(tmp, tag + "_src.inp")
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        inp = os.path.join(tmp, tag + ".inp")
        convert(path, inp)
        d, status, out = run_ccx(ccx, env, inp)
        un = dat_displacements(os.path.join(d, "job.dat")) if status == "solved" else {}
        shutil.rmtree(d, ignore_errors=True)
        if len(uf) == 40 and set(un) == set(uf):
            scale = max(abs(x) for v in uf.values() for x in v)
            err = ccx_ratio(max(abs(a - b) for n in uf for a, b in zip(un[n], uf[n])), scale)
            ok = text != src and err < 1e-6
            print(f"{'PASS' if ok else 'FAIL'}  {tag} (the part's orientation by nodes {line}): "
                  f"displacements max difference {err:.1e} of max |u| from the model written flat")
            failures += 0 if ok else 1
        else:
            print(f"FAIL  {tag}: the two models printed different nodes ({len(un)} / {len(uf)})")
            failures += 1
    # --- *PRE-TENSION SECTION, NODE= / ELEMENT= a one-member set (as Abaqus allows): ccx 2.23
    # reads only a number there and stops on a set name ('*ERROR reading *PRE-TENSION SECTION')
    def pretension_closures(text, tag, nodes):
        """The pre-tension nodes' DOF 1 (the cut's closure) of ``text`` converted and solved."""
        src, inp = os.path.join(tmp, tag + "_src.inp"), os.path.join(tmp, tag + ".inp")
        with open(src, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        convert(src, inp)
        d, status, out = run_ccx(ccx, env, inp)
        u = dat_displacements(os.path.join(d, "job.dat")) if status == "solved" else {}
        shutil.rmtree(d, ignore_errors=True)
        if any(n not in u for n in nodes):
            print(f"FAIL  {tag}: no closure printed ({status})")
            print("      " + " / ".join(l.strip() for l in out.splitlines() if "ERROR" in l)[:200])
            return None
        return [u[n][0] for n in nodes]

    want = 1000.0 * 2.0 / 210000.0
    for level, where in (("model", ""), ("part", "; a part's card, two instances, one turned"),
                         ("assembly", "; two instances, one turned, the cards at the assembly level "
                                      "naming I1.PT and an assembly set")):
        tag = "pretension_node_set" + ("" if level == "model" else "_" + level)
        got = pretension_closures(pretension_bolt_deck(level), tag, (99,) if level == "model" else (99, 198))
        if got is None:
            failures += 1
            continue
        err = max(abs(g / want - 1) for g in got)
        ok = err < 1e-6
        print(f"{'PASS' if ok else 'FAIL'}  {tag} (a C3D8 bolt cut by a *PRE-TENSION SECTION whose NODE= "
              f"is a one-node set{where}): closure {', '.join(f'{g:.7g}' for g in got)} vs F L / E A = "
              f"{want:.7g} ({err:.1e} apart; the set name stops ccx)")
        failures += 0 if ok else 1
    got = pretension_closures(pretension_beam_deck(), "pretension_element_set", (99,))
    ref = pretension_closures(pretension_beam_deck("1", "99"), "pretension_element_set_ref", (99,))
    if got and ref:
        ok = abs(ccx_ratio(got[0], ref[0]) - 1) < 1e-9 and abs(got[0] / want - 1) < 1e-6
        print(f"{'PASS' if ok else 'FAIL'}  pretension_element_set (a B31 bolt whose *PRE-TENSION SECTION "
              f"names its cut element and node by one-member sets): closure {got[0]:.7g} vs {ref[0]:.7g} "
              f"with ELEMENT=1, NODE=99 and F L / E A = {want:.7g} (the set names stop ccx; ccx's own "
              f"cut drops the cut element: F L / 2 E A)")
    failures += 0 if got and ref and ok else 1
    # --- a truss / beam cut (ELEMENT=): Abaqus puts the cut at the element's last node and keeps
    # the element; ccx 2.23 deletes it (no compliance, only the axial force across) and stops on
    # a truss or U1.  Bolt and member in parallel: closure F / kb + F / km, then held while P
    # pulls: the bolt takes kb P / (kb + km) of it
    kb, km, f, p = 210000.0 / 2.0, 210000.0, 1000.0, 3000.0
    want = [(f / kb + f / km, -f / km, f), (f / kb + f / km, -f / km + p / (kb + km), f + kb * p / (kb + km))]
    for tag, kw, what in (("pretension_cut_beam", {}, "a B31 bolt"),
                          ("pretension_cut_truss", {"bolt": "T3D2", "cut": 2}, "a T3D2 bolt cut at its end"),
                          ("pretension_cut_u1", {"bolt": "U1"}, "a *BEAM GENERAL SECTION bolt (U1)"),
                          ("pretension_cut_truss_node", {"cut": 2, "member": "truss"},
                           "a B31 bolt cut at the node only the T3D2 member shares")):
        src, inp = os.path.join(tmp, tag + "_src.inp"), os.path.join(tmp, tag + ".inp")
        with open(src, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(pretension_cut_deck(**kw))
        convert(src, inp)
        d, status, out = run_ccx(ccx, env, inp)
        got = {}
        for _, title, _s, time, rows in (A.dat_blocks(os.path.join(d, "job.dat")) if status == "solved" else []):
            if title.startswith("displacements"):
                u = {int(r[0]): r[1] for r in rows}
                got.setdefault(time, [None, None, None])[:2] = [u.get(99), u.get(3)]
            elif title.startswith("stresses") and rows:
                got.setdefault(time, [None, None, None])[2] = sum(r[2] for r in rows) / len(rows)
        shutil.rmtree(d, ignore_errors=True)
        steps = [got[t] for t in sorted(got)]
        if len(steps) != 2 or any(x is None for st in steps for x in st):
            print(f"FAIL  {tag}: no closure, end displacement or cut element stress in both steps ({status})")
            print("      " + " / ".join(l.strip() for l in out.splitlines() if "ERROR" in l)[:200])
            failures += 1
            continue
        err = max(abs(g / w - 1) for st, ws in zip(steps, want) for g, w in zip(st, ws))
        ok = err < 1e-6
        print(f"{'PASS' if ok else 'FAIL'}  {tag} ({what} beside a clamped member, cut by a *PRE-TENSION "
              f"SECTION, ELEMENT=; loaded, then held while the joint is pulled): closure "
              f"{steps[0][0]:.7g}, end {steps[0][1]:.7g} / {steps[1][1]:.7g}, cut element stress "
              f"{steps[0][2]:.6g} / {steps[1][2]:.6g} vs F / kb + F / km, bolt and member in parallel "
              f"({err:.1e} apart; ccx's own cut: closure 33 % low, or ccx stopped)")
        failures += 0 if ok else 1
    tips = []
    for tag, cut in (("pretension_cut_bending", True), ("pretension_cut_bending_uncut", False)):
        src, inp = os.path.join(tmp, tag + "_src.inp"), os.path.join(tmp, tag + ".inp")
        with open(src, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(pretension_bending_deck(cut))
        convert(src, inp)
        d, status, out = run_ccx(ccx, env, inp)
        u = dat_displacements(os.path.join(d, "job.dat")) if status == "solved" else {}
        tips.append(u[3] + u[4] if 3 in u and 4 in u else None)
        shutil.rmtree(d, ignore_errors=True)
    if None in tips or not max(abs(x) for x in tips[1]):
        print(f"FAIL  pretension_cut_bending: no tip displacement ({tips})")
        failures += 1
    else:
        big = max(abs(x) for x in tips[1])
        err = max(abs(a - b) for a, b in zip(*tips)) / big
        ok = err < 1e-6
        print(f"{'PASS' if ok else 'FAIL'}  pretension_cut_bending (a B31 cantilever cut by a *PRE-TENSION "
              f"SECTION, the adjustment held, the tip loaded across, out of plane and in torsion): tip "
              f"{', '.join(f'{x:.7g}' for x in tips[0][:3])}, its arm's end {tips[0][5]:.7g} along z vs "
              f"the uncut beam {err:.1e} of max |u| apart "
              f"(ccx's own cut: no moment across, the tip ran off to 1e10)")
        failures += 0 if ok else 1
    # --- a coupling's REF NODE= at the assembly level: an instance set, an instance node, an
    # assembly set, CAE's assembly reference point (numbered 1, like the instance's first
    # node), REFNODE=, a legacy *KINEMATIC COUPLING and a distributing coupling, each against
    # the model written flat (ccx needs a node number there and stops on a set name)
    tops = {}
    for form in ("flat", "flat_dist", "set", "node", "asm_set", "asm_point", "refnode", "legacy", "dist_node"):
        src, inp = os.path.join(tmp, f"cref_{form}_src.inp"), os.path.join(tmp, f"cref_{form}.inp")
        with open(src, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(coupling_ref_deck(form))
        convert(src, inp)
        d, status, out = run_ccx(ccx, env, inp)
        u = dat_displacements(os.path.join(d, "job.dat")) if status == "solved" else {}
        tops[form] = [u[n] for n in sorted(u)] if len(u) == 4 else None
        shutil.rmtree(d, ignore_errors=True)
    bad = [f for f, t in tops.items() if t is None or not max(abs(x) for r in t for x in r)]
    if bad:
        print(f"FAIL  coupling_ref_node_forms: the top did not move or ccx did not solve ({', '.join(bad)})")
        failures += 1
    else:
        err = max(abs(a - b) for f, t in tops.items() if not f.startswith("flat")
                  for ra, rb in zip(t, tops["flat_dist" if f.startswith("dist") else "flat"])
                  for a, b in zip(ra, rb)) / max(abs(x) for r in tops["flat"] for x in r)
        ok = err < 1e-9
        print(f"{'PASS' if ok else 'FAIL'}  coupling_ref_node_forms (a cube's top coupled to a reference node "
              f"named at the assembly level as I1.RP, I1.100, an assembly set, CAE's reference point 1, "
              f"by REFNODE=, by a legacy *KINEMATIC COUPLING and a distributing coupling): the top's "
              f"displacements {err:.1e} of max |u| from the model written flat (top u1 "
              f"{tops['flat'][0][0]:.6g}, distributing {tops['flat_dist'][0][0]:.6g})")
        failures += 0 if ok else 1
    # --- *COUPLING + *DISTRIBUTING: Abaqus moves the reference node with the coupling nodes'
    # weighted mean motion and turns it with their weighted least-squares rotation (and spreads
    # its loads by the same relations, distributing_relations); ccx's own card only spreads the
    # loads: a BC on the node moved nothing, the node printed U = 0, a beam on it hung free

    def dist_run(tag, text):
        src, inp = os.path.join(tmp, tag + "_src.inp"), os.path.join(tmp, tag + ".inp")
        with open(src, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        convert(src, inp)
        d, status, out = run_ccx(ccx, env, inp)
        u = dat_displacements(os.path.join(d, "job.dat")) if status == "solved" else {}
        shutil.rmtree(d, ignore_errors=True)
        return u, status, out
    xyz, _, top, _, _ = distributing_block()
    area = {n: 0.25 * (2 if 0 < xyz[n][0] < 3 else 1) * (2 if xyz[n][1] == 1 else 1) for n in top}
    motion, spread = distributing_relations(xyz, area, DIST_REF)
    cpl = ["*COUPLING, CONSTRAINT NAME=C, REF NODE=RP, SURFACE=TOP", "*DISTRIBUTING"]
    # (a) the reference node's motion prescribed (u3 = 0.01, a turn of 0.005 about x)
    u, status, out = dist_run("distributing_rp_motion", distributing_deck(cpl, ["*BOUNDARY", "RP, 3, 3, 0.01",
                                                                               "RP, 4, 4, 0.005"]))
    face = max((abs(x) for n in top for x in u.get(n, ())), default=0.0)
    if len(u) < len(xyz) + 1 or face < 1e-3:
        print(f"FAIL  distributing_rp_motion: the coupled face did not move ({status}, max |u| {face:.3g})")
        failures += 1
    else:
        ur, th = motion(u)
        err = max(abs(ur[2] - 0.01) / 0.01, abs(th[0] - 0.005) / 0.005,
                  max(abs(a - b) for a, b in zip(u[100], ur)) / face)
        ok = err < 1e-5
        print(f"{'PASS' if ok else 'FAIL'}  distributing_rp_motion (a block's top face coupled to a reference "
              f"node off its centroid, which is moved 0.01 along z and turned 0.005 about x): the face's "
              f"weighted mean motion and least-squares rotation give u3 {ur[2]:.7g}, rotation {th[0]:.7g}, "
              f"the node's own displacement {err:.1e} apart (the face moved {face:.3g}; ccx's card: not at all)")
        failures += 0 if ok else 1
    # (b) a force and a moment on it, vs Abaqus' distribution of them as nodal forces on the
    # block without the coupling; also on a node surface with weights and WEIGHTING METHOD=LINEAR
    f, m = (0.3, -0.2, 0.5), (0.4, 0.1, -0.3)
    loads = ["*CLOAD"] + [f"RP, {k + 1}, {f[k]}" for k in range(3)] + [f"RP, {k + 4}, {m[k]}" for k in range(3)]
    far = max(math.dist(xyz[n], DIST_REF) for n in top)
    weights = {n: 1.0 + 0.1 * (n % 3) for n in top}
    q = {n: math.dist(xyz[n], DIST_REF) / far for n in top}
    for tag, card, w, extra in (
            ("distributing_rp_loads", cpl, area, ()),
            ("distributing_node_surface_weights", [cpl[0].replace("TOP", "TOPW"), "*DISTRIBUTING, WEIGHTING METHOD=LINEAR"],
             {n: weights[n] * (1.0 - math.dist(xyz[n], DIST_REF) / far) for n in top},
             ["*SURFACE, NAME=TOPW, TYPE=NODE"] + [f"{n}, {weights[n]}" for n in top]),
            ("distributing_weighting_quadratic", [cpl[0], "*DISTRIBUTING, WEIGHTING METHOD=QUADRATIC"],
             {n: area[n] * (1.0 - q[n] ** 2) for n in top}, ()),
            ("distributing_weighting_cubic", [cpl[0], "*DISTRIBUTING, WEIGHTING METHOD=CUBIC"],
             {n: area[n] * (1.0 - 3.0 * q[n] ** 2 + 2.0 * q[n] ** 3) for n in top}, ())):
        motion_w, spread_w = distributing_relations(xyz, w, DIST_REF)
        got, status, out = dist_run(tag, distributing_deck(card, loads, extra))
        ref, _, _ = dist_run(tag + "_ref", distributing_deck((), ["*CLOAD"] + [
            f"{n}, {k + 1}, {x:.12g}" for n, fn in spread_w(f, m).items() for k, x in enumerate(fn)], extra))
        if len(got) < len(xyz) + 1 or len(ref) < len(xyz):
            print(f"FAIL  {tag}: no solution ({status})")
            print("      " + " / ".join(l.strip() for l in out.splitlines() if "ERROR" in l)[:200])
            failures += 1
            continue
        big = max(abs(x) for n in xyz for x in ref[n])
        ur = motion_w(ref)[0]
        err = ccx_ratio(max(max(abs(a - b) for n in xyz for a, b in zip(got[n], ref[n])),
                            max(abs(a - b) for a, b in zip(got[100], ur))), big)
        ok = err < 1e-5
        print(f"{'PASS' if ok else 'FAIL'}  {tag} (a force and a moment on the reference node of a block's top "
              + {"distributing_rp_loads": "face", "distributing_node_surface_weights": "nodes as a node surface "
                 "with weights, WEIGHTING METHOD=LINEAR"}.get(tag, f"face, {card[1][15:]}") + f"): every node "
              f"{err:.1e} of max |u| ({big:.3g}) from Abaqus' distribution of them as nodal forces, the reference "
              f"node's displacement included (u3 {got[100][2]:.6g}; ccx's "
              + {"distributing_rp_loads": "card: 0", "distributing_node_surface_weights": "card: stopped on the "
                 "node surface"}.get(tag, "card: 0, and it ignores WEIGHTING METHOD") + ")")
        failures += 0 if ok else 1
    # (b') under NLGEOM the coupling stays ccx's card (its equations would not turn with the
    # face), which ignores WEIGHTING METHOD: the same displacements as without it, flagged
    # reduced physics; the reference node's loads moved the face
    runs = []
    for card in ("*DISTRIBUTING, WEIGHTING METHOD=CUBIC", "*DISTRIBUTING"):
        src, inp = os.path.join(tmp, "dist_nl_src.inp"), os.path.join(tmp, "dist_nl.inp")
        with open(src, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(distributing_deck([cpl[0], card], loads).replace("*STEP\n", "*STEP, NLGEOM\n"))
        _, conv = convert(src, inp)
        d, status, out = run_ccx(ccx, env, inp)
        runs.append((dat_displacements(os.path.join(d, "job.dat")) if status == "solved" else {},
                     list(conv.reduced_physics)))
        shutil.rmtree(d, ignore_errors=True)
    (u, red), (ref, red0) = runs
    ok = bool(u) and set(u) == set(ref) and all(n in u for n in top)
    if ok:
        face = max(abs(x) for n in top for x in ref[n])
        err = ccx_ratio(max(abs(a - b) for n in ref for a, b in zip(u[n], ref[n])), face)
        lost = "*DISTRIBUTING WEIGHTING METHOD ignored by ccx's card"
        ok = err == 0.0 and face > 1e-4 and lost in red and lost not in red0
        print(f"{'PASS' if ok else 'FAIL'}  distributing_weighting_nlgeom_card (the block's top face, WEIGHTING "
              f"METHOD=CUBIC, under NLGEOM: ccx's card kept): {len(u)} nodes {err:.1e} of max |u| ({face:.3g}) "
              f"from the card without it; the weighting flagged as lost (reduced physics): {lost in red}")
    else:
        print("FAIL  distributing_weighting_nlgeom_card: no solution")
    failures += 0 if ok else 1
    # (c) a B31 cantilever from the reference node (a beam on a solid), its tip loaded: the
    # block takes f and the moment arm x f at the node (the beam is statically determinate), and
    # the tip moves with the face's motion plus the beam's own deflection (its root clamped)
    tip = (1.3, 2.8, 3.5)
    arm = [tip[k] - DIST_REF[k] for k in range(3)]
    mom = (arm[1] * f[2] - arm[2] * f[1], arm[2] * f[0] - arm[0] * f[2], arm[0] * f[1] - arm[1] * f[0])
    beam = ["*NODE, NSET=TIP", "101, " + ", ".join(map(str, tip)), "*ELEMENT, TYPE=B31, ELSET=BM", "50, 100, 101",
            "*BEAM SECTION, ELSET=BM, MATERIAL=MB, SECTION=RECT", "0.3, 0.3", "1., 0., 0.",
            "*MATERIAL, NAME=MB", "*ELASTIC", "1000., 0."]    # (nu 0: ccx's knot at the root is exact)
    tip_load = ["*CLOAD"] + [f"101, {k + 1}, {f[k]}" for k in range(3)] + ["*NODE PRINT, NSET=TIP", "U"]
    runs = [dist_run("distributing_beam_rp", distributing_deck(cpl, tip_load, beam)),
            dist_run("distributing_beam_rp_loads", distributing_deck(cpl, ["*CLOAD"] + [
                f"RP, {k + 1}, {f[k]}" for k in range(3)] + [f"RP, {k + 4}, {mom[k]:.12g}" for k in range(3)])),
            dist_run("distributing_beam_rp_root", distributing_deck((), ["*BOUNDARY", "RP, 1, 6"] + tip_load, beam))]
    if any(len(r[0]) < len(xyz) + 1 for r in runs[:2]) or 101 not in runs[0][0] or 101 not in runs[2][0]:
        print(f"FAIL  distributing_beam_rp: no solution ({', '.join(r[1] for r in runs)})")
        failures += 1
    else:
        a, b, c = (r[0] for r in runs)
        big = max(abs(x) for n in xyz for x in b[n])
        ur, th = motion(a)
        want = [ur[k] + (th[1] * arm[2] - th[2] * arm[1], th[2] * arm[0] - th[0] * arm[2],
                         th[0] * arm[1] - th[1] * arm[0])[k] + c[101][k] for k in range(3)]
        err = ccx_ratio(max(abs(a[n][k] - b[n][k]) for n in list(xyz) + [100] for k in range(3)), big)
        err_tip = ccx_ratio(max(abs(x - y) for x, y in zip(a[101], want)), max(abs(x) for x in want))
        ok = err < 1e-5 and err_tip < 1e-5
        print(f"{'PASS' if ok else 'FAIL'}  distributing_beam_rp (a B31 cantilever from the reference node, its "
              f"tip loaded): the block and the node {err:.1e} of max |u| from the same force and its moment on "
              f"the node; the tip {', '.join(f'{x:.6g}' for x in a[101])} vs the face's motion and rotation plus "
              f"the root-clamped beam's deflection {err_tip:.1e} apart (ccx's card: the beam hung free)")
        failures += 0 if ok else 1
    # --- a truss numbered below the beams at a node they share: ccx 2.23 gives a node its
    # lowest-numbered beam / truss element's expansion, so the node had no rotations — it held the
    # beams' rotation there (93 % off under a tip load) and stopped on a rotational BC or moment;
    # Abaqus' answer does not depend on the numbering
    for tag, step in (("truss_below_beams_tip_load", ["*CLOAD", "3, 2, 1.", "3, 3, 0.5"]),
                      ("truss_below_beams_moment", ["*CLOAD", "2, 6, 0.3", "2, 5, 0.2", "3, 3, 0.5"]),
                      ("truss_below_beams_rotation_bc", ["*BOUNDARY", "2, 4, 6", "*CLOAD", "3, 2, 1."])):
        pair = [dist_run(tag + ("" if first else "_after"), truss_below_beams_deck(first, step))
                for first in (True, False)]
        lo, hi = (r[0] for r in pair)
        if 3 not in lo or 3 not in hi or not max(abs(x) for x in hi[3]):
            print(f"FAIL  {tag}: no solution ({pair[0][1]} / {pair[1][1]})")
            print("      " + " / ".join(l.strip() for l in pair[0][2].splitlines() if "ERROR" in l)[:200])
            failures += 1
            continue
        big = max(abs(x) for v in hi.values() for x in v)
        err = max(abs(x - y) for n in hi for x, y in zip(lo[n], hi[n])) / big
        ok = err < 1e-9
        print(f"{'PASS' if ok else 'FAIL'}  {tag} (a B31 cantilever with a T3D2 at mid-span numbered before the "
              f"beams): tip {', '.join(f'{x:.6g}' for x in lo[3])}, {err:.1e} of max |u| from the truss "
              f"numbered after them (ccx: 93 % stiffer under the tip load, stopped on the moment / BC)")
        failures += 0 if ok else 1
    # --- a truss at a shell node without a beam: ccx 2.23 makes the node a knot whose turn about
    # the shell normal it holds along the truss's section axis only, normal to the shell normal in
    # the first case, where spooles crashed (exit 255, no message); in the second the knot ran,
    # 1e-3 off.  The truss ends at a copy tied through a hub of two knot beams to the node; the
    # reference has the truss as an axial spring of its stiffness, which ccx does not expand
    for tag, kw, base in (("shell_truss_node_s4", dict(typ="S4", plane="xy", d=(0.0, -0.5, -1.0), first=True),
                           "crashed in spooles, exit 255"),
                          ("shell_truss_node_s8r", dict(typ="S8R", plane="xz", d=(1.0, 0.0, 0.0), first=False),
                           "1e-3 off; a tie straight to the node is misread in this plane")):
        got, status, out = dist_run(tag, shell_truss_deck(**kw))
        ref, rstatus, _ = dist_run(tag + "_spring", shell_truss_deck(spring=True, **kw))
        if not got or not ref or set(ref) - set(got):
            print(f"FAIL  {tag}: no solution ({status} / {rstatus})")
            print("      " + " / ".join(l.strip() for l in out.splitlines() if "ERROR" in l)[:200])
            failures += 1
            continue
        big = max(abs(x) for v in ref.values() for x in v)
        err = max(abs(x - y) for n in ref for x, y in zip(got[n], ref[n])) / big
        tip = max(got, key=lambda n: abs(got[n][2 if kw["plane"] == "xy" else 1]) if n != 90 else 0.0)
        ok = err < 1e-6 and big > 0.1
        print(f"{'PASS' if ok else 'FAIL'}  {tag} ({kw['typ']} strip in the {kw['plane'][0]}-{kw['plane'][1]} plane, a "
              f"T3D2 at an inner node): every node {err:.1e} of max |u| ({big:.4g}, tip node {tip}) from the truss "
              f"as an axial spring (ccx's own knot: {base})")
        failures += 0 if ok else 1
    # --- the legacy *DISTRIBUTING COUPLING (DCOUP3D) vs Abaqus' own results: the Verification
    # Guide's linear problem, whose tables the equations of the distributing constraint give back
    # to 3 digits, offset moments and rotations included (ccx's card: (3.89e-3, 0, 0) in step 1)
    motion3, _ = distributing_relations(DCOUP3D_XYZ, {1: 1.0, 2: 2.0, 3: 3.0}, DCOUP3D_REF)
    worst, exact, shown = 0.0, 0.0, []
    for step in range(3):
        got, status, out = dist_run(f"dcoup3d_verification_{step + 1}", dcoup3d_deck(step))
        if not all(n in got for n in (1, 2, 3, 10)):
            worst = float("inf")
            shown.append(f"step {step + 1}: no solution ({status})")
            continue
        u_r, th = motion3({n: got[n] for n in (1, 2, 3)})
        for key, val in (("u10", got[10]), ("r10", th), ("u1", got[1])):
            tab = DCOUP3D_TABLES[key][step]
            scale = max(abs(x) for x in tab)
            worst = max(worst, max(abs(a - b) for a, b in zip(val, tab)) / scale)
        exact = max(exact, max(abs(a - b) for a, b in zip(got[10], u_r)) / max(abs(x) for x in got[10]))
        shown.append(f"u10 {', '.join(f'{x:.3g}' for x in got[10])}")
    ok = worst < 6e-3 and exact < 1e-6
    print(f"{'PASS' if ok else 'FAIL'}  dcoup3d_verification (Abaqus Verification Guide, linear DCOUP3D, three "
          f"steps of a force and a moment on the reference node): node 10's displacements and rotations and "
          f"node 1's within {worst:.1e} of Abaqus' tables (3 digits); node 10 {exact:.1e} from the coupling "
          f"nodes' weighted motion ({'; '.join(shown)})")
    failures += 0 if ok else 1
    # --- *COUPLING + *DISTRIBUTING on plane-element edges of two section thicknesses: the weights
    # are the edges' tributary lengths times the thickness (planned before the thicknesses were
    # read, they took 1 for both: 39 % off), vs the force and moment as Abaqus' nodal forces
    # (in the plane: one rotation, T = sum w r . r; the edge nodes lie on a line)
    xy2 = {1 + i + 5 * j: (float(i), float(j)) for j in range(3) for i in range(5)}
    w2 = {n: v / 8.0 for n, v in {11: 0.5, 12: 1.0, 13: 2.0, 14: 3.0, 15: 1.5}.items()}
    c2 = [sum(w2[n] * xy2[n][k] for n in w2) for k in (0, 1)]
    r2 = {n: (xy2[n][0] - c2[0], xy2[n][1] - c2[1]) for n in w2}
    rr2, t2 = (1.3 - c2[0], 3.5 - c2[1]), sum(w2[n] * (r2[n][0] ** 2 + r2[n][1] ** 2) for n in w2)
    f2, m2 = (0.3, -0.2), 0.4
    om2 = (m2 + rr2[0] * f2[1] - rr2[1] * f2[0]) / t2
    spread2 = {n: (w2[n] * (f2[0] - om2 * r2[n][1]), w2[n] * (f2[1] + om2 * r2[n][0])) for n in w2}

    def motion2(u):
        th = sum(w2[n] * (r2[n][0] * u[n][1] - r2[n][1] * u[n][0]) for n in w2) / t2
        return [sum(w2[n] * u[n][0] for n in w2) - th * rr2[1], sum(w2[n] * u[n][1] for n in w2) + th * rr2[0]]
    got, status, out = dist_run("distributing_plane_two_thicknesses", plane_two_thickness_deck(
        cpl, ["*CLOAD", f"RP, 1, {f2[0]}", f"RP, 2, {f2[1]}", f"RP, 6, {m2}"]))
    ref, _, _ = dist_run("distributing_plane_two_thicknesses_ref", plane_two_thickness_deck((), ["*CLOAD"] + [
        f"{n}, {k + 1}, {fn[k]:.12g}" for n, fn in spread2.items() for k in (0, 1)]))
    if not all(n in got for n in list(xy2) + [100]) or not all(n in ref for n in xy2):
        print(f"FAIL  distributing_plane_two_thicknesses: no solution ({status})")
        failures += 1
    else:
        big = max(abs(x) for n in xy2 for x in ref[n][:2])
        ur = motion2(ref)
        err = ccx_ratio(max(max(abs(a - b) for n in xy2 for a, b in zip(got[n][:2], ref[n][:2])),
                            max(abs(a - b) for a, b in zip(got[100][:2], ur))), big)
        ok = err < 1e-5 and big > 1e-5
        print(f"{'PASS' if ok else 'FAIL'}  distributing_plane_two_thicknesses (a CPS4 strip of thickness 1 and 3, "
              f"its top edges distributing-coupled, a force and a moment on the node): every node {err:.1e} of max "
              f"|u| ({big:.3g}) from Abaqus' nodal forces with edge length x thickness weights, the node's "
              f"displacement included (thickness 1 for both: 39 % off)")
        failures += 0 if ok else 1
    # --- *COUPLING + *DISTRIBUTING on an M3D4 / M3D3 skin on the block's top: equations on the
    # membrane nodes (ccx's card spread the load over the faces its hinge holds: 20 % off on M3D4,
    # nothing on M3D3), vs Abaqus' distribution of the force and moment as nodal forces
    _, els, _, topel, _ = distributing_block()
    for typ in ("M3D4", "M3D3"):
        tag = f"distributing_membrane_skin_{typ.lower()}"
        skin = [f"*ELEMENT, TYPE={typ}, ELSET=SKIN"]
        w_skin = {}
        for k, e in enumerate(topel):
            q = els[e][4:8]
            parts = [q] if typ == "M3D4" else [[q[0], q[1], q[2]], [q[0], q[2], q[3]]]
            for j, c in enumerate(parts):
                skin.append(f"{1000 + 2 * k + j}, " + ", ".join(map(str, c)))
                for n in c:
                    w_skin[n] = w_skin.get(n, 0.0) + (0.25 if typ == "M3D4" else 1.0 / 6.0)
        extra = skin + ["*SURFACE, NAME=SKINS", "SKIN, SPOS", "*MEMBRANE SECTION, ELSET=SKIN, MATERIAL=M", "0.05"]
        motion_s, spread_s = distributing_relations(xyz, w_skin, DIST_REF)
        got, status, out = dist_run(tag, distributing_deck([cpl[0].replace("SURFACE=TOP", "SURFACE=SKINS"), cpl[1]],
                                                           loads, extra))
        ref, _, _ = dist_run(tag + "_ref", distributing_deck((), ["*CLOAD"] + [
            f"{n}, {k + 1}, {x:.12g}" for n, fn in spread_s(f, m).items() for k, x in enumerate(fn)], extra))
        if len(got) < len(xyz) + 1 or len(ref) < len(xyz):
            print(f"FAIL  {tag}: no solution ({status})")
            print("      " + " / ".join(l.strip() for l in out.splitlines() if "ERROR" in l)[:200])
            failures += 1
            continue
        big = max(abs(x) for n in xyz for x in ref[n])
        ur = motion_s(ref)[0]
        err = ccx_ratio(max(max(abs(a - b) for n in xyz for a, b in zip(got[n], ref[n])),
                            max(abs(a - b) for a, b in zip(got[100], ur))), big)
        ok = err < 1e-5 and max(abs(x) for x in got[100]) > 1e-4
        print(f"{'PASS' if ok else 'FAIL'}  {tag} (a force and a moment on the reference node of an {typ} skin on "
              f"the block's top): every node {err:.1e} of max |u| ({big:.3g}) from Abaqus' distribution of them as "
              f"nodal forces, the reference node's displacement included (u3 {got[100][2]:.6g}; ccx's card: "
              + ("the face 20 % off, the node not moved" if typ == "M3D4" else "transmitted nothing") + ")")
        failures += 0 if ok else 1
    # --- Johnson-Cook damage initiation: ccx's indicator, the model unchanged -------
    # ccx 2.23 evaluates the criterion once it has its second data line (the damage at which
    # it deletes an element, out of reach so that it only reports): in uniaxial tension the
    # indicator is PEEQ / (d1 + d2 exp(-d3 / 3)), and the run is the same as without the card.
    src = open(os.path.join(EXAMPLES, "damage_johnson_cook_cubes.inp"), encoding="utf-8").read()
    card = "*DAMAGE INITIATION, CRITERION=JOHNSON COOK\n0.2, 0.3, 1.5, 0., 0., 1878., 293., 1.\n"
    runs = {}
    for label, text in (("with", src), ("without", src.replace(card, ""))):
        path = os.path.join(tmp, f"jc_{label}_src.inp")
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        inp = os.path.join(tmp, f"jc_{label}.inp")
        convert(path, inp)
        d, status, out = run_ccx(ccx, env, inp)
        dat = os.path.join(d, "job.dat")
        runs[label] = (status, dat_el_scalar(dat, "equivalent plastic strain"),
                       dat_el_scalar(dat, "ductile damage initiation"), dat_displacements(dat))
        shutil.rmtree(d, ignore_errors=True)
    (s1, peeq, duct, u1), (s0, peeq0, duct0, u0) = runs["with"], runs["without"]
    eps_f = 0.2 + 0.3 * math.exp(-0.5)
    if s1 != "solved" or s0 != "solved" or not peeq or set(duct) != {1, 2}:
        print(f"FAIL  damage_johnson_cook_cubes: {s1} / {s0} (with / without the card), DUCT "
              f"for elements {sorted(duct)}")
        failures += 1
    else:
        ratio = ccx_ratio(duct[2], peeq[2])
        same = peeq == peeq0 and u1 == u0
        ok = abs(ratio * eps_f - 1) < 1e-5 and duct[1] == 0.0 and peeq[1] > 0.0 and same
        print(f"{'PASS' if ok else 'FAIL'}  damage_johnson_cook_cubes (*DAMAGE INITIATION, "
              f"CRITERION=JOHNSON COOK): DUCT / PEEQ = {ratio:.6f} (1 / {eps_f:.6f} = "
              f"{1 / eps_f:.6f}) at PEEQ {peeq[2]:.5f}, DUCT {duct[1]:g} in the cube without the "
              f"criterion, results {'identical to' if same else 'DIFFERENT from'} the run "
              f"without the card")
        failures += 0 if ok else 1
    # --- rigid elements and analytical rigid surfaces ---------------------------------
    # ccx has neither: the converter gives each facet a force-free skin element that the rigid
    # body carries.  Against frictionless HARD contact (ccx: a linear law of slope K = 50 x the
    # first material's modulus) a flat punch on a free block has the series-spring answer
    # F = A d / (L / E' + 1 / K) — E' = E / (1 - nu^2) in plane strain — exactly, and the same
    # punch written as an analytical surface, or as a solid punch whose every node is given
    # the motion, must give the same block.
    def rigid_run(text, name, approximate=False):
        src = os.path.join(tmp, name + "_src.inp")
        with open(src, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        inp = os.path.join(tmp, name + ".inp")
        convert(src, inp, approximate)
        d, status, out = run_ccx(ccx, env, inp)
        dat = os.path.join(d, "job.dat")
        res = {"status": status, "out": out,
               "ref": dat_history(dat, "forces", "REF"), "top": dat_history(dat, "displacements", "TOPB"),
               "mid": dat_history(dat, "displacements", "MID"),
               "tool": dat_history(dat, "forces", "TOOLN"), "refu": dat_history(dat, "displacements", "REF")}
        if os.path.exists(dat):
            res["eig"] = dat_eigen_table(dat, "E I G E N V A L U E   O U T P U T")
        shutil.rmtree(d, ignore_errors=True)
        return res

    def rows_diff(a, b):
        return max(abs(x - y) for ra, rb in zip(a, b) for x, y in zip(ra, rb)), \
            max(abs(x) for r in b for x in r)

    E, nu, K, dd = 1000.0, 0.3, 50.0 * 1000.0, 0.01
    for dim, k, eprime in (("3d", 2, E), ("planar", 1, E / (1 - nu * nu))):
        ref = -1.0 * dd / (1.0 / eprime + 1.0 / K)
        got = {}
        for tool in ("elements", "analytic"):
            r = rigid_run(rigid_punch_deck(dim, tool), f"rigid_punch_{dim}_{tool}")
            got[tool] = r
            if r["status"] != "solved" or not r["ref"]:
                print(f"FAIL  rigid_punch ({dim}, {tool}): {r['status']}")
                print("\n".join(l for l in r["out"].splitlines() if "ERROR" in l))
                failures += 1
        if all(g["status"] == "solved" and g["ref"] for g in got.values()):
            fa, fb = got["elements"]["ref"][-1][1][0][k], got["analytic"]["ref"][-1][1][0][k]
            apart = ccx_ratio(*rows_diff(got["analytic"]["top"][-1][1], got["elements"]["top"][-1][1]))
            ok = abs(fa / ref - 1) < 1e-5 and abs(fb / ref - 1) < 1e-5 and apart <= 1e-6
            tools = ("R3D4", "CYLINDER") if dim == "3d" else ("R2D2", "SEGMENTS")
            print(f"{'PASS' if ok else 'FAIL'}  rigid_punch ({dim}, face-to-face): reaction {fa:+.6f} "
                  f"({tools[0]} skins), {fb:+.6f} ({tools[1]} analytical surface) vs A d / (L/E' + "
                  f"1/K) = {ref:+.6f}; block top {apart:.1e} apart")
            failures += 0 if ok else 1
    # axisymmetric (node-to-surface; ccx's face-to-face one is uneven at a punch edge, with a
    # prescribed punch too): RAX2 skins and a SEGMENTS surface against a prescribed CAX4 punch
    got = {tool: rigid_run(rigid_punch_deck("axisym", tool, ctype="NODE TO SURFACE"), f"rigid_punch_ax_{tool}")
           for tool in ("elements", "analytic", "prescribed")}
    if not all(g["status"] == "solved" and g["top"] for g in got.values()):
        print("FAIL  rigid_punch (axisymmetric): " + ", ".join(f"{t} {g['status']}" for t, g in got.items()))
        failures += 1
    else:
        ub = got["prescribed"]["top"][-1][1]
        fp = sum(r[1] for r in got["prescribed"]["tool"][-1][1])
        errs = [rows_diff(got[t]["top"][-1][1], ub) for t in ("elements", "analytic")]
        forces = [got[t]["ref"][-1][1][0][1] for t in ("elements", "analytic")]
        sc = errs[0][1]                                  # the block top under the prescribed punch
        ok = sc > 0.5 * dd and all(du <= 1e-6 * sc for du, _ in errs) and \
            all(abs(ccx_ratio(f, fp) - 1) < 1e-5 for f in forces)
        apart = max(ccx_ratio(du, s) for du, s in errs)
        print(f"{'PASS' if ok else 'FAIL'}  rigid_punch (axisymmetric, node-to-surface): RAX2 skins and a "
              f"SEGMENTS surface move the block as the prescribed punch does ({apart:.1e} apart; the "
              f"block top moved {sc / dd:.3f} d); reactions {forces[0]:+.6f}, {forces[1]:+.6f} vs "
              f"{fp:+.6f} (per 2-degree sector)")
        failures += 0 if ok else 1
    # NLGEOM: the punch pushed in and turned (3-D 0.05 rad about x, plane 0.03 rad about z)
    for dim, th in (("3d", 0.05), ("planar", 0.03)):
        got = {tool: rigid_run(rigid_punch_deck(dim, tool, nlgeom=True, d=0.1, theta=th, ctype="NODE TO SURFACE"),
                               f"rigid_tilt_{dim}_{tool}") for tool in ("elements", "analytic", "prescribed")}
        if not all(g["status"] == "solved" and g["top"] for g in got.values()):
            print(f"FAIL  rigid_punch_tilt ({dim}): " + ", ".join(f"{t} {g['status']}" for t, g in got.items()))
            failures += 1
            continue
        errs = [rows_diff(got[t]["top"][-1][1], got["prescribed"]["top"][-1][1]) for t in ("elements", "analytic")]
        worst = max(ccx_ratio(du, sc) for du, sc in errs)
        ok = worst < 1e-5
        print(f"{'PASS' if ok else 'FAIL'}  rigid_punch_tilt ({dim}, NLGEOM, turned {th:g} rad): rigid skins and "
              f"the analytical surface vs the punch given the exact motion: block top {worst:.1e} of |u| apart")
        failures += 0 if ok else 1
    # *TIE to a rigid plate that turns under NLGEOM: the tied nodes join the body
    got = {tool: rigid_run(rigid_tied_deck(tool), f"rigid_tie_{tool}") for tool in ("elements", "analytic", "prescribed")}
    if not all(g["status"] == "solved" and g["mid"] for g in got.values()):
        print("FAIL  rigid_tie: " + ", ".join(f"{t} {g['status']}" for t, g in got.items()))
        failures += 1
    else:
        errs = [rows_diff(got[t]["mid"][-1][1], got["prescribed"]["mid"][-1][1]) for t in ("elements", "analytic")]
        worst = max(ccx_ratio(du, sc) for du, sc in errs)
        ok = worst < 1e-5
        print(f"{'PASS' if ok else 'FAIL'}  rigid_tie (*TIE to a rigid plate turned 0.05 rad, NLGEOM): block "
              f"mid-height {worst:.1e} of |u| from the top given the exact motion (ccx's own tie: 1.3e-2)")
        failures += 0 if ok else 1
    # mass and rotary inertia from the deck's MASS / ROTARYI elements only (zero-density skins)
    r = rigid_run(rigid_inertia_deck(), "rigid_inertia")
    want = sorted([math.sqrt(2 * 96.0 / 6.0) / (2 * math.pi), math.sqrt(2 * 96.0 * 0.75 ** 2 / 1.0) / (2 * math.pi)])
    eig = r.get("eig") or []
    got_f = sorted(eig)[:2] if len(eig) >= 2 else []
    if r["status"] != "solved" or len(got_f) < 2:
        print(f"FAIL  rigid_inertia: {r['status']}, eigenvalues {eig}")
        failures += 1
    else:
        err = max(abs(a / b - 1) for a, b in zip(got_f, want))
        ok = err < 1e-5
        print(f"{'PASS' if ok else 'FAIL'}  rigid_inertia (R3D4 plate, MASS + ROTARYI on springs): f = "
              f"{got_f[0]:.6f}, {got_f[1]:.6f} Hz (theory {want[0]:.6f}, {want[1]:.6f}; {err:.1e} off)")
        failures += 0 if ok else 1
    # --approximate: a sphere (SEGMENTS with a CIRCL arc) meshed into facets, on a half-space
    r = rigid_run(rigid_hertz_deck(), "rigid_hertz", approximate=True)
    hertz = 4.0 / 3.0 * E / (1 - nu * nu) * math.sqrt(10.0) * 0.1 ** 1.5
    if r["status"] != "solved" or not r["ref"]:
        print(f"FAIL  rigid_hertz: {r['status']}")
        failures += 1
    else:
        f = -180.0 * r["ref"][-1][1][0][1]                 # ccx: per 2-degree sector
        ok = abs(f / hertz - 1) < 0.03
        print(f"{'PASS' if ok else 'FAIL'}  rigid_hertz (--approximate, faceted analytical sphere on a "
              f"half-space): F = {f:.2f} vs Hertz {hertz:.2f} ({(f / hertz - 1) * 100:+.1f}%; finite domain "
              f"and penalty contact)")
        failures += 0 if ok else 1

    # explicit dynamics: ccx leaves the contact of a plane model's expanded nodes with a rigid
    # surface out of its stable increment, so the converter caps the step's increment; the
    # punch given its motion node by node, run at that increment, is the reference
    r = rigid_run(rigid_punch_explicit_deck("elements"), "rigid_explicit_elements")
    with open(os.path.join(tmp, "rigid_explicit_elements.inp"), encoding="utf-8") as fh:
        m = re.search(r"(?m)^\*DYNAMIC, EXPLICIT[^\n]*\n([^\n]*)", fh.read())
    fields = [x.strip() for x in m.group(1).split(",")] if m else []
    cap = float(fields[3]) if len(fields) > 3 and fields[3] else None
    ref_run = rigid_run(rigid_punch_explicit_deck("prescribed", dtmax=cap), "rigid_explicit_prescribed") \
        if cap else None
    if not cap or r["status"] != "solved" or not r["top"] or not ref_run or ref_run["status"] != "solved" \
            or not ref_run["top"]:
        print(f"FAIL  rigid_punch_explicit (planar): cap {cap}, {r['status']}, "
              f"{ref_run['status'] if ref_run else 'no reference run'}")
        failures += 1
    else:
        du, sc = rows_diff(r["top"][-1][1], ref_run["top"][-1][1])
        f_s, f_p = r["ref"][-1][1][0][1], sum(row[1] for row in ref_run["tool"][-1][1])
        apart = ccx_ratio(du, sc)
        ok = sc > 0.5 * dd and apart <= 1e-6 and abs(ccx_ratio(f_s, f_p) - 1) < 1e-5
        print(f"{'PASS' if ok else 'FAIL'}  rigid_punch_explicit (planar, R2D2 skins): maximum increment "
              f"{cap:g} set by the converter (ccx's own estimate leaves this contact out); block top "
              f"{apart:.1e} of |u| from the punch given its motion node by node "
              f"at that increment (it moved {sc / dd:.3f} d), reaction {f_s:+.6f} vs {f_p:+.6f}")
        failures += 0 if ok else 1
    # pressure on rigid elements: positive along the element normal; an R2D2 per unit depth
    for kind, axis in (("R2D2", 1), ("R3D4", 2)):
        r = rigid_run(rigid_pressure_deck(kind), f"rigid_pressure_{kind}")
        u = r["refu"][-1][1][0][axis] if r["status"] == "solved" and r["refu"] else None
        ok = u is not None and abs(u / (2.0 / 4.0) - 1) < 1e-9
        what = "segment of length 1 (section 0.5 thick)" if kind == "R2D2" else "unit facet"
        print(f"{'PASS' if ok else 'FAIL'}  rigid_pressure ({kind}): P = 2 on a rigid {what} against a "
              f"spring k = 4: u = {u if u is not None else r['status']} (p / k = 0.5)")
        failures += 0 if ok else 1

    # --- user materials on a stock ccx: the name guard and --abaqus-umat --------------
    # ccx hands a *USER MATERIAL to the routine its name starts with: USER... to an empty stub
    # in a stock ccx, JOHNSONCOOK... to its own Johnson-Cook law.  Renamed, the material stops
    # ccx instead.  --abaqus-umat writes it for ccx's Abaqus-UMAT interface, where a stock ccx
    # has a linear-elastic example: the stretched cube gives S33 = E eps through ABAQUS (small
    # strain) and E ln(1 + eps) through ABAQUSNL (NLGEOM, logarithmic strain).
    src = os.path.join(tmp, "umat_src.inp")
    for name in ("UserMat", "JohnsonCook_Steel"):
        with open(src, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(umat_cube_deck(name))
        inp = os.path.join(tmp, "umat.inp")
        convert(src, inp)
        d, status, out = run_ccx(ccx, env, inp)
        shutil.rmtree(d, ignore_errors=True)
        ok = (status == "failed" and "no user material subroutine" in out
              and "ABQ2CCX_" + name.upper() in out)
        print(f"{'PASS' if ok else 'FAIL'}  umat_guard ({name}): renamed ABQ2CCX_{name}, ccx stops with "
              f"'no user material subroutine' ({status})")
        failures += 0 if ok else 1
    for nlgeom, ref in ((False, 210.0), (True, 210000.0 * math.log(1.001))):
        with open(src, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(umat_cube_deck("UserMat", nlgeom))
        inp = os.path.join(tmp, "umat.inp")
        convert(src, inp, abaqus_umat=True)
        d, status, out = run_ccx(ccx, env, inp)
        s = dat_el_stress(os.path.join(d, "job.dat"), 1) if status == "solved" else None
        shutil.rmtree(d, ignore_errors=True)
        ok = s is not None and abs(s[2] / ref - 1) < 1e-4
        what = "ABAQUSNL, NLGEOM: E ln(1.001)" if nlgeom else "ABAQUS: E 0.001"
        print(f"{'PASS' if ok else 'FAIL'}  umat_abaqus_interface ({what}): a stock ccx runs its example "
              f"UMAT, S33 = {f'{s[2]:.4f}' if s else status} (reference {ref:.4f})")
        failures += 0 if ok else 1

    # --- the --run results digest (abq2ccx.ccx_results_digest) against the references above:
    # the planar beam's frequencies and buckling load (beam theory, Euler), the circular-section
    # cantilever's tip deflection (P L^3 / 3 E I; ccx writes the beam expanded, so its largest
    # |U| is at a node next to the tip node 21), and the two-block assembly's reactions, which
    # statics makes the applied load (-100 in z on I2.7), at the names Abaqus gives them.
    for name in ("planar_pinned_beam", "beam_circ_cantilever", "assembly_two_blocks"):
        inp = os.path.join(tmp, name + ".inp")
        rep, conv = convert(os.path.join(EXAMPLES, name + ".inp"), inp)
        d, status, out = run_ccx(ccx, env, inp)
        dg = A.ccx_results_digest(os.path.join(d, "job"), rep.instances, conv.model_labels) \
            if status == "solved" else []
        shutil.rmtree(d, ignore_errors=True)
        if not dg:
            print(f"FAIL  results digest ({name}): no digest ({status})")
            failures += 1
            continue
        if name == "planar_pinned_beam":
            got = [x for e in dg for x in e.get("frequencies", [])[:2] + e.get("buckling_factors", [])[:1]]
            ok = len(got) == 3 and max(abs(g - r) / r for g, r in zip(got, beam_refs[name])) < 0.02
            what = (f"f1, f2 = {got[0]:.2f}, {got[1]:.2f} Hz, buckling load {got[2]:.0f} (beam theory "
                    + ", ".join(f"{r:.2f}" for r in beam_refs[name][:2])
                    + f", Euler {beam_refs[name][2]:.0f})" if len(got) == 3 else str(dg))
        elif name == "beam_circ_cantilever":
            u, ref = dg[0].get("max_u", {}), 1.0 * 100.0 ** 3 / (3 * 1.0e5 * math.pi / 4)
            ok = u.get("near") == 21 and abs(u["value"] - ref) / ref < 0.02
            what = (f"max |U| {u.get('value', float('nan')):.4f} near node {u.get('near')} (beam "
                    f"theory at node 21: {ref:.4f})")
        else:
            rf = {r.get("set"): r for r in dg[0].get("rf", [])}
            u = dg[0].get("max_u", {})
            ok = "FIX2" in rf and rf["FIX2"]["rf"][:2] == [0.0, 0.0] and \
                abs(rf["FIX2"]["rf"][2] - 100.0) < 1e-3 and \
                rf.get("FIX", {}).get("rf") == [0.0, 0.0, 0.0] and u.get("abaqus") == "I2.7"
            what = (f"sum of RF on FIX2 {rf.get('FIX2', {}).get('rf')} (applied: -100 in z) and FIX "
                    f"{rf.get('FIX', {}).get('rf')}; max |U| at node {u.get('node')} [{u.get('abaqus')}], "
                    f"the loaded corner")
        print(f"{'PASS' if ok else 'FAIL'}  results digest ({name}): {what}")
        failures += 0 if ok else 1
    # --- composite shells: S4R -> S8R, SC8R / SC6R -> one solid per ply ---------------------
    # ccx runs *SHELL SECTION, COMPOSITE on S8R / S6 only and has no layered solid section, so
    # abq2ccx upgrades composite S4R to S8R (a node at the middle of every edge) and writes a
    # composite continuum shell as one C3D8I / C3D6 per ply.  A simply supported [0/90/0] plate
    # under a sinusoidal load against classical lamination theory and Pagano's 3-D elasticity
    # solution (a/h = 100 and 10), the plate stacked along its elements' direction 1, and the
    # in-plane stiffness A of a [30/-60/45]s laminate in the x-y and the x-z plane (exact: the
    # strain is uniform).
    def composite_run(text, tag):
        src = os.path.join(tmp, f"{tag}_src.inp")
        with open(src, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        inp = os.path.join(tmp, f"{tag}.inp")
        convert(src, inp)
        d, status, out = run_ccx(ccx, env, inp)
        dat = os.path.join(d, "job.dat")
        res = (dat_displacements(dat), dat_totals(dat)) if status == "solved" else None
        shutil.rmtree(d, ignore_errors=True)
        if res is None:
            print(f"FAIL  {tag}: did not solve ({status})")
            print("\n".join(l for l in out.splitlines() if "ERROR" in l)[:400])
        return res

    plies = lambda h: [(h / 3, ang, PAGANO_PLY) for ang in (0, 90, 0)]     # noqa: E731
    centre_b, centre_t = 81, 162                    # the SC8R plate's centre, bottom and top
    stacked = {}
    for kind, h, stack in (("s4r", 0.01, 3), ("sc8r", 0.01, 3), ("sc8r", 0.1, 3), ("sc8r", 0.1, 1)):
        res = composite_run(composite_plate_deck(kind, h, stack), f"composite_plate_{kind}_{stack}_{h:g}")
        if res is None:
            failures += 1
            continue
        u = res[0]
        if kind == "sc8r" and h == 0.1:
            stacked[stack] = u
        if stack != 3:
            continue
        clt = navier_deflection(plies(h), 1.0, 1.0, 1.0)
        if kind == "s4r":
            w = abs(u[81][2])
            ok = abs(w / clt - 1) < 0.01
            print(f"{'PASS' if ok else 'FAIL'}  composite_plate_s4r (composite S4R -> S8R, a/h = 100): "
                  f"centre deflection {w:.6g} vs classical lamination theory {clt:.6g} "
                  f"({abs(w / clt - 1) * 100:.2f}% diff; Pagano 3-D "
                  f"{abs(pagano_deflection(plies(h), 1.0, 1.0, 1.0, h / 2)):.6g})")
        else:
            ref = [abs(pagano_deflection(plies(h), 1.0, 1.0, 1.0, z)) for z in (0.0, h)]
            got = [abs(u[n][2]) for n in (centre_b, centre_t)]
            err = max(abs(g / r - 1) for g, r in zip(got, ref))
            ok = err < (0.02 if h == 0.01 else 0.03)
            print(f"{'PASS' if ok else 'FAIL'}  composite_plate_sc8r (composite SC8R -> C3D8I per ply, "
                  f"a/h = {1 / h:g}): centre deflection bottom / top {got[0]:.6g} / {got[1]:.6g} vs "
                  f"Pagano's 3-D solution {ref[0]:.6g} / {ref[1]:.6g} ({err * 100:.2f}% diff; "
                  f"classical lamination theory {clt:.6g})")
        failures += 0 if ok else 1
    if len(stacked) == 2:
        a, b = stacked[3], stacked[1]
        scale = max(abs(x) for v in a.values() for x in v)
        err = ccx_ratio(max(abs(x - y) for nd in a for x, y in zip(a[nd], b.get(nd, (math.inf,) * 3))), scale)
        ok = set(a) == set(b) and err < 1e-6
        print(f"{'PASS' if ok else 'FAIL'}  composite_plate_sc8r (STACK DIRECTION=1 on renumbered "
              f"elements, top-face load P4): {len(b)} centre displacements vs STACK DIRECTION=3, max "
              f"difference {err:.1e} of max |u|")
        failures += 0 if ok else 1
    # ("s4r", "XYD"): the ply angles written with a Fortran exponent, 3.D1, -6.D1, 4.5D1 (one
    # was read as an orientation name, which ccx rejected)
    dexp = lambda t: t.replace("PLY, 30.", "PLY, 3.D1").replace("PLY, -60.", "PLY, -6.D1") \
        .replace("PLY, 45.", "PLY, 4.5D1")                                  # noqa: E731
    for kind in ("s4r", "sc8r", "sc6r"):
        for plane in ("XY", "XZ") + (("XYD",) if kind == "s4r" else ()):
            deck = composite_inplane_deck(kind, plane[:2])
            res = composite_run(dexp(deck) if plane == "XYD" else deck, f"composite_inplane_{kind}_{plane}")
            if res is None:
                failures += 1
                continue
            want = laminate_a_reactions(plane[:2])
            got = res[1]
            scale = max(abs(x) for r in want for x in r)
            err = max(abs(x - y) for r, g in zip(want, got) for x, y in zip(r, g)) / scale \
                if len(got) == len(want) else math.inf
            ok = err < 1e-4
            print(f"{'PASS' if ok else 'FAIL'}  composite_inplane_{kind} ([30/-60/45]s, {plane[:2]} plane"
                  f"{', angles 3.D1, -6.D1, 4.5D1' if plane == 'XYD' else ''}): "
                  f"edge reactions of three uniform strains vs classical lamination theory's A11 ... "
                  f"A66, max difference {err:.1e} of the largest")
            failures += 0 if ok else 1

    # --- material axes of plain shell and membrane sections, and *DISTRIBUTION ones -----
    # ccx 2.23 projects a shell orientation's turned axis 1 onto the shell (Abaqus: the axis
    # after the rotation axis) and gives a membrane its orientation's axes unprojected (or
    # the global ones); abq2ccx gives such sections Abaqus' directions element by element.
    for kind, plane, orient in (("s4r", "XY", True), ("s4r", "XZ", True), ("s4r", "YZ", True),
                                ("m3d4", "XZ", True), ("m3d4", "YZ", True), ("m3d4", "YZ", False),
                                ("s4r", "XY", PLATE_AXES), ("m3d4", "XZ", PLATE_AXES),
                                ("m3d8r", "YZ", True), ("m3d6", "XZ", True)):
        tag = f"shell_axes_{kind}_{plane}" + ("" if orient is True else "_norot" if orient else "_default")
        res = composite_run(shell_axes_inplane_deck(kind, plane, orient), tag)
        if res is None:
            failures += 1
            continue
        theta = shell_axes_angle(plane, orient)
        want, got = laminate_a_reactions(plane, (theta,)), res[1]
        scale = max(abs(x) for r in want for x in r)
        err = max(abs(x - y) for r, g in zip(want, got) for x, y in zip(r, g)) / scale \
            if len(got) == len(want) else math.inf
        ok = err < 1e-4
        what = "an orientation turned about its axis 1" if orient is True else \
            "the plate axes without a rotation line" if orient else "no orientation"
        print(f"{'PASS' if ok else 'FAIL'}  {tag} (plain {kind.upper()}, {what}, {plane} "
              f"plane): edge reactions of three uniform strains vs the ply's t Qbar at Abaqus' "
              f"direction {theta:.2f} deg, max difference {err:.1e} of the largest")
        failures += 0 if ok else 1
    hoop, probe, ur = 1.0 / (INPLANE_PLY[0] * 0.01), 1 + 24 // 8 + 24, {}
    for rot in ("", "3, 25."):
        res = composite_run(cylinder_hoop_deck(rot), "cylinder_hoop" + ("_rot3" if rot else ""))
        u = res[0].get(probe) if res else None
        if u is None:
            failures += 1
            continue
        ur[rot] = (u[0] + u[1]) / math.sqrt(2.0)          # the probe node is at 45 degrees
    if len(ur) == 2:
        err, same = abs(ur[""] / hoop - 1), abs(ccx_ratio(ur["3, 25."], ur[""]) - 1)
        ok = err < 0.01 and same < 1e-6
        print(f"{'PASS' if ok else 'FAIL'}  cylinder_hoop (S4, cylindrical *ORIENTATION on a cylinder, "
              f"internal pressure): radial displacement {ur['']:.6g} vs thin-wall theory with the "
              f"fibres along the hoop {hoop:.6g} ({err * 100:.2f}% diff; turned about axis 3 by 25 "
              f"deg: {same:.1e} apart)")
        failures += 0 if ok else 1
    # plain shell sections on continuum shells run as C3D8I / C3D6 solids, which ccx 2.23 gives
    # their orientation's axes unprojected (the global ones without one); Abaqus projects it
    # onto the mid-surface with the stack direction as axis 3
    for tag, kind, plane, orient, extra in (
            ("XY", "sc8r", "XY", True, ""), ("XZ", "sc8r", "XZ", True, ""), ("YZ", "sc8r", "YZ", True, ""),
            ("XZ_default", "sc8r", "XZ", False, ""), ("YZ_default", "sc8r", "YZ", False, ""),
            ("YZ", "sc6r", "YZ", True, ""), ("XZ_norot", "sc8r", "XZ", PLATE_AXES, ""),
            ("XZ_dist", "sc8r", "XZ", True, "dist"), ("XY_down_aniso", "sc8r", "XY", False, "aniso")):
        tag = f"sc_axes_{kind}_{tag}"
        res = composite_run(sc_axes_inplane_deck(kind, plane, orient, dist=extra == "dist",
                                                 aniso=extra == "aniso"), tag)
        if res is None:
            failures += 1
            continue
        if extra == "aniso":
            want, ref = aniso_patch_reactions(plane), "an anisotropic ply's plane-stress stiffness in Abaqus' axes"
            what = "no orientation, stacked downwards"
        else:
            theta = shell_axes_angle(plane, orient)
            want, ref = laminate_a_reactions(plane, (theta,)), f"the ply's t Qbar at Abaqus' direction {theta:.2f} deg"
            what = ("a *DISTRIBUTION orientation" if extra else "an orientation") + " turned about its axis 1" \
                if orient is True else "the plate axes without a rotation line" if orient else "no orientation"
        got = res[1]
        scale = max(abs(x) for r in want for x in r)
        err = max(abs(x - y) for r, g in zip(want, got) for x, y in zip(r, g)) / scale \
            if len(got) == len(want) else math.inf
        ok = err < 1e-4
        print(f"{'PASS' if ok else 'FAIL'}  {tag} (plain shell section on {kind.upper()}, {what}, {plane} "
              f"plane, thickness free): edge reactions of three uniform strains vs {ref}, max difference "
              f"{err:.1e} of the largest")
        failures += 0 if ok else 1
    res = composite_run(sc_cylinder_hoop_deck(), "sc_cylinder_hoop")
    u = res[0] if res else {}
    probe = [1 + 24 // 8 + 24 * (2 // 2) + 24 * 3 * k for k in (0, 1)]    # inner and outer node at 45 deg
    if all(p in u for p in probe):
        ur = sum(u[p][0] + u[p][1] for p in probe) / (2 * math.sqrt(2.0))
        hoop = (1.0 - 0.005) / (SC_PLY[0] * 0.01)
        err = abs(ur / hoop - 1)
        ok = err < 0.01
        print(f"{'PASS' if ok else 'FAIL'}  sc_cylinder_hoop (SC8R, cylindrical *ORIENTATION on a "
              f"cylinder, internal pressure): mid-surface radial displacement {ur:.6g} vs thin-wall "
              f"theory with the fibres along the hoop {hoop:.6g} ({err * 100:.2f}% diff)")
        failures += 0 if ok else 1
    else:
        if res:                                    # solved, but without the probe nodes
            print("FAIL  sc_cylinder_hoop: no displacement at the probe nodes")
        failures += 1
    # STACK DIRECTION=ORIENTATION stacks along the orientation's rotation axis, by default
    # axis 1: a cylindrical system's radial axis, whatever the elements' numbering
    for composite in (True, False):
        tag = "sc_cylinder_stack_" + ("composite" if composite else "plain")
        res = composite_run(sc_cylinder_stack_deck(composite), tag)
        if res is None:
            failures += 1
            continue
        want = sc_cylinder_stack_force(composite)
        got = res[1][0][2] if res[1] else math.inf
        err = abs(got / want - 1)
        ok = err < 1e-4
        print(f"{'PASS' if ok else 'FAIL'}  {tag} (SC8R cylinder numbered radially along direction 1, "
              f"{'[0/90/0] plies' if composite else 'one layer'}, STACK DIRECTION=ORIENTATION with a "
              f"cylindrical *ORIENTATION without a rotation line, axial strain): axial force {got:.6g} vs "
              f"the radially stacked wall's membrane stiffness {want:.6g} ({err:.1e} apart)")
        failures += 0 if ok else 1
    # ccx 2.23 has no spherical system (abq2ccx writes the card as a rectangular one, which a
    # sphere centred at the origin leaves without axes); the shells take Abaqus' spherical
    # directions element by element, and isotropic ones read the global axes instead (on zero
    # axes ccx prints NaN element stresses)
    for kind, rot in (("s4r", ""), ("s4r", "3, 25."), ("sc8r", ""), ("sc8r_composite", ""),
                      ("s4r_iso", ""), ("sc8r_iso", "")):
        tag = f"sphere_hoop_{kind}" + ("_rot3" if rot else "")
        text, probes = sphere_hoop_deck(kind, rot)
        res = composite_run(text, tag)
        u = res[0] if res else {}
        if not all(x in u for _th, _ph, ks in probes for x in ks):
            if res:                                # solved, but without the probe nodes
                print(f"FAIL  {tag}: no displacement at the probe nodes")
            failures += 1
            continue
        err = scale = 0.0
        for th, ph, ks in probes:
            v = [sum(u[x][c] for x in ks) / len(ks) for c in range(3)]      # the mid-surface
            radial = math.sin(th) * (math.cos(ph) * v[0] + math.sin(ph) * v[1]) + math.cos(th) * v[2]
            merid = math.cos(th) * (math.cos(ph) * v[0] + math.sin(ph) * v[1]) - math.sin(th) * v[2]
            want = sphere_membrane(th, kind)
            err = max(err, abs(radial - want[0]), abs(merid - want[1]))
            scale = max(scale, abs(want[0]), abs(want[1]))
        ok = err < (0.02 if kind.startswith("s4r") else 0.01) * scale
        what = {"s4r": "plain S4R", "sc8r": "plain SC8R", "sc8r_composite": "[0/90/0] SC8R plies",
                "s4r_iso": "isotropic S4R", "sc8r_iso": "isotropic SC8R stacked along the orientation"}[kind]
        print(f"{'PASS' if ok else 'FAIL'}  {tag} ({what}, spherical *ORIENTATION"
              + (" turned about axis 3" if rot else "") + f", internal pressure): radial and meridional "
              f"displacement at colatitudes 30-150 deg vs membrane theory"
              + ("" if kind.endswith("_iso") else " with the fibres along the parallels")
              + f", max difference {err / scale * 100:.2f}% of the largest {scale:.4g}"
              + (" (ccx loads the inner face of its expanded shells: 1 % less load at this t/R)"
                 if kind.startswith("s4r") else ""))
        failures += 0 if ok else 1

    # --- initial stresses and plastic strains given in an orientation's axes -----------------
    # Abaqus reads them in the axes of the element's orientation, ccx 2.23 in global ones, and a
    # plastic strain's shear as tensor components (Abaqus: engineering); abq2ccx turns them into
    # global axes, at each integration point on a cylindrical system.  A free cube relaxes its
    # initial stress to eps = -C^-1 sigma and takes its plastic strain stress-free; a quarter
    # annulus with a uniform hoop stress has a closed-form radial displacement; a CPS4 square's
    # initial shear (Abaqus' third component on plane stress, ccx's fourth) relaxes by tau / G
    def faithful_run(text, tag, allow=()):
        src = os.path.join(tmp, f"{tag}_src.inp")
        with open(src, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        inp = os.path.join(tmp, f"{tag}.inp")
        _rep, conv = convert(src, inp)
        d, status, out = run_ccx(ccx, env, inp)
        u = dat_displacements(os.path.join(d, "job.dat")) if status == "solved" else None
        shutil.rmtree(d, ignore_errors=True)
        lost = [r for r in conv.reduced_physics if not r.startswith(allow)] if allow else conv.reduced_physics
        if u is None or lost:
            print(f"FAIL  {tag}: " + (f"did not solve ({status})" if u is None else
                                      "reduced physics: " + "; ".join(lost)))
            print("\n".join(l for l in out.splitlines() if "ERROR" in l)[:400])
            return None
        return u

    for kind in ("stress", "plastic", "blank"):
        tag = f"initial_{kind}_turned"
        # "blank": blank fields in the *Orientation line and the stress record (Abaqus: 0)
        u = faithful_run(ic_cube_deck("stress", IC_STRESS_BLANK, True) if kind == "blank" else
                         ic_cube_deck(kind), tag)
        if u is None:
            failures += 1
            continue
        h = [[u[k][i] - u[1][i] for k in (2, 4, 5)] for i in range(3)]      # du_i / dx_j
        eps = [h[0][0], h[1][1], h[2][2], (h[0][1] + h[1][0]) / 2, (h[0][2] + h[2][0]) / 2,
               (h[1][2] + h[2][1]) / 2]
        if kind != "plastic":
            sg = local_to_global(TURNED_AB, IC_STRESS_BLANK if kind == "blank" else IC_STRESS)
            want = [-(1.25 * x - (0.25 * sum(sg[:3]) if k < 3 else 0.0)) / 1000.0 for k, x in enumerate(sg)]
        else:
            want = local_to_global(TURNED_AB, IC_PLASTIC[:3] + tuple(x / 2 for x in IC_PLASTIC[3:]))
        err = max(abs(x - y) for x, y in zip(eps, want)) / max(abs(y) for y in want)
        ok = err < 1e-6
        print(f"{'PASS' if ok else 'FAIL'}  {tag} (free C3D8 cube, an initial "
              + {"stress": "stress", "plastic": "plastic strain with engineering shear terms",
                 "blank": "stress with a blank syy"}[kind]
              + " in a turned rectangular *Orientation" + (" whose a_z is blank" if kind == "blank" else "")
              + f"): strains {err:.1e} of the largest off "
              + ("R eps_p R^T, stress-free" if kind == "plastic" else "-C^-1 R sigma R^T"))
        failures += 0 if ok else 1
    # one initial-temperature card per set, as CAE writes them: the fill of the nodes no card
    # lists (Abaqus: 0) came on every card, so B's card set A back to 0 (A then grew 120 alpha)
    u = faithful_run(ic_temperature_cards_deck(), "initial_temperature_cards")
    if u is None:
        failures += 1
    else:
        got = [u.get(7, [math.inf] * 3), [a - b for a, b in zip(u.get(17, [math.inf] * 3), u.get(11, [0.0] * 3))]]
        err = max(abs(x / 0.02 - 1) for v in got for x in v)
        ok = err < 1e-9
        print(f"{'PASS' if ok else 'FAIL'}  initial_temperature_cards (two free cubes, initial "
              f"temperatures on two *INITIAL CONDITIONS cards, heated by 20): corner displacements "
              f"{got[0][0]:.7g} and {got[1][0]:.7g} vs 20 alpha = 0.02 (max {err:.1e} off)")
        failures += 0 if ok else 1
    # mesh-generation cards read by position, with Abaqus' defaults: the arcs about a centre
    # given by coordinates and the fill with the default increment were skipped, *ELGEN's blank
    # increments shifted its fields (40 elements) and *NCOPY, MULTIPLE translated every copy
    runs = [faithful_run(mesh_generation_ring_deck(gen), "mesh_generation_fields" + ("" if gen else "_twin"))
            for gen in (True, False)]
    if None in runs:
        failures += 1
    else:
        u, t = runs
        moved = max(abs(x) for v in t.values() for x in v)
        err = ccx_ratio(max(abs(x - y) for n in t for x, y in zip(u.get(n, [math.inf] * 3), t[n])), moved)
        lame = [(1.3 / 3000.0 * (0.4 * r + 4.0 / r), sum(u.get(n, [math.inf] * 2)[:2]) / math.sqrt(2.0))
                for n, r in ((41, 1.0), (45, 2.0))]
        off = max(abs(got / want - 1) for want, got in lame)
        ok = err < 1e-9 and moved > 1e-3 and off < 0.02
        print(f"{'PASS' if ok else 'FAIL'}  mesh_generation_fields (a quarter annulus under internal "
              f"pressure, its mesh by *NGEN arcs about a centre by coordinates, *NFILL with the default "
              f"increment, *NCOPY, MULTIPLE and *ELGEN with blank increments): every displacement as "
              f"with the mesh listed ({err:.1e} apart, largest {moved:.4g}); radial displacements "
              f"{lame[0][1]:.5g} and {lame[1][1]:.5g} at r = a, b vs Lame {lame[0][0]:.5g} and "
              f"{lame[1][0]:.5g} ({off:.1%} off)")
        failures += 0 if ok else 1
    # *NGEN, LINE=C end nodes at unequal distances from the centre move radially onto one
    # circle (Abaqus "Node definition"); the arcs were spirals between them, off the top face
    u = faithful_run(mesh_generation_ring_deck(skew=0.05), "ngen_arc_radial_ends")
    if u is None or None in runs:
        failures += 1
    else:
        t = runs[1]
        moved = max(abs(x) for v in u.values() for x in v)
        err = ccx_ratio(max(abs(x - y) for n in t for x, y in zip(u.get(n, [math.inf] * 3), t[n])), moved)
        ends = [(1.3 / 3000.0 * (0.4 * r + 4.0 / r), u.get(n, [math.inf])[0]) for n, r in ((1, 1.0), (5, 2.0))]
        off = max(abs(got / want - 1) for want, got in ends)
        ok = err < 1e-9 and moved > 1e-3 and off < 0.02
        print(f"{'PASS' if ok else 'FAIL'}  ngen_arc_radial_ends (the quarter annulus of "
              f"mesh_generation_fields with each *NGEN arc's end nodes at r (1 -/+ 0.05)): every "
              f"displacement as with the mesh listed on the circles r = a, b ({err:.1e} apart, largest "
              f"{moved:.4g}); radial displacements {ends[0][1]:.5g} and {ends[1][1]:.5g} at the moved "
              f"end nodes vs Lame {ends[0][0]:.5g} and {ends[1][0]:.5g} ({off:.1%} off)")
        failures += 0 if ok else 1
    # *NCOPY, POLE: the pole node number (or the pole's coordinates) was read as a translation
    u = faithful_run(ncopy_pole_deck(), "ncopy_pole")
    if u is None:
        failures += 1
    else:
        got = [u.get(n, [math.inf])[0] for n in (1, 11, 21)]
        err = max(abs(g / w - 1) for g, w in zip(got, (0.01, 0.02, 0.03)))
        ok = err < 1e-9
        print(f"{'PASS' if ok else 'FAIL'}  ncopy_pole (three bars in a row pulled at their end, the "
              f"far nodes by *NCOPY, POLE from a pole node and from a pole point): displacements "
              f"{got[0]:.6g}, {got[1]:.6g}, {got[2]:.6g} vs F x / E A = 0.01, 0.02, 0.03 ({err:.1e} off)")
        failures += 0 if ok else 1
    text, xy = ic_annulus_deck()
    u = faithful_run(text, "initial_stress_cylindrical")
    if u is None:
        failures += 1
    else:
        err = scale = 0.0
        for n, (x, y) in xy.items():
            th, want = math.atan2(y, x), annulus_hoop_displacement(math.hypot(x, y))
            err = max(err, abs(u[n][0] * math.cos(th) + u[n][1] * math.sin(th) - want),
                      abs(u[n][1] * math.cos(th) - u[n][0] * math.sin(th)))
            scale = max(scale, abs(want))
        ok = err < 1e-4 * scale
        print(f"{'PASS' if ok else 'FAIL'}  initial_stress_cylindrical (C3D20R quarter annulus in plane "
              f"strain, a uniform hoop stress in a cylindrical *Orientation): displacement vs the "
              f"closed form, max difference {err / scale:.1e} of the largest {scale:.4g}")
        failures += 0 if ok else 1
    u = faithful_run("*Heading\nUnit square with an initial shear stress\n*Node, nset=ALL\n1, 0., 0.\n"
                     "2, 1., 0.\n3, 1., 1.\n4, 0., 1.\n*Element, type=CPS4, elset=SQ\n1, 1, 2, 3, 4\n"
                     "*Material, name=M\n*Elastic\n1000., 0.\n*Solid Section, elset=SQ, material=M\n1.\n"
                     "*Initial Conditions, type=STRESS\nSQ, 0., 0., 100.\n*Boundary\n1, 1, 2\n2, 2, 2\n"
                     "*Step\n*Static\n*Node Print, nset=ALL\nU\n*End Step\n", "initial_stress_plane_stress")
    if u is None:
        failures += 1
    else:
        ok = abs(u[4][0] + 0.2) < 1e-9
        print(f"{'PASS' if ok else 'FAIL'}  initial_stress_plane_stress (CPS4 square, initial S12 = 100, "
              f"G = 500): shear {u[4][0]:+.6f} (-tau / G = -0.2)")
        failures += 0 if ok else 1
    # a continuum shell's are its components 11, 22, 12 in its material directions, with or
    # without an orientation (1, 2 on the mid-surface, 3 the stack direction; a composite ply's
    # turned by its angle); ccx 2.23 reads them on its C3D8I / C3D6 in global axes.  A free plate
    # off the x-y plane relaxes an initial stress to -C^-1 R sigma R^T and takes a plastic strain
    # stress-free; [0/90/0] plies with an initial stress Q (e, e, 0) relax to one uniform strain
    # (the element substitution and the ply split are the only reduced physics)
    for kind, ic, orient, plies in (("sc8r", "stress", False, None), ("sc6r", "stress", False, None),
                                    ("sc8r", "stress", True, None), ("sc8r", "plastic", False, None),
                                    ("sc8r", "stress", False, (0, 90, 0)), ("sc6r", "stress", True, (0, 90, 0))):
        tag = f"initial_{ic}_{kind}" + ("_plies" if plies else "") + ("_oriented" if orient else "")
        text, xyz, axes = sc_ic_plate_deck(kind, ic, orient, plies)
        u = faithful_run(text, tag, allow=("element SC",))
        if u is None:
            failures += 1
            continue
        eps = fit_strain(u, xyz)
        if plies:
            want, ref = local_to_global(axes[:2], sc_ic_ply_relaxed()[1]), "every ply's relaxed strain"
        elif ic == "plastic":
            p11, p22, g12 = SC_IC_PLASTIC
            want, ref = local_to_global(axes[:2], (p11, p22, 0.0, g12 / 2, 0.0, 0.0)), "R eps_p R^T, stress-free"
        else:
            s11, s22, s12 = SC_IC_STRESS
            sg = local_to_global(axes[:2], (s11, s22, 0.0, s12, 0.0, 0.0))
            want = [-(1.25 * x - (0.25 * sum(sg[:3]) if k < 3 else 0.0)) / 1000.0 for k, x in enumerate(sg)]
            ref = "-C^-1 R sigma R^T"
        err = max(abs(x - y) for x, y in zip(eps, want)) / max(abs(y) for y in want)
        ok = err < 1e-4
        what = ("[0/90/0] plies, initial S11, S22 = Q (e, e)" if plies else
                "initial PE11, PE22, PE12 (engineering)" if ic == "plastic" else "initial S11, S22, S12")
        print(f"{'PASS' if ok else 'FAIL'}  {tag} (free {kind.upper()} plate off the x-y plane, {what} in "
              f"Abaqus' shell axes" + (", a projected *ORIENTATION" if orient else "") + f"): strains "
              f"{err:.1e} of the largest off {ref}")
        failures += 0 if ok else 1

    # --- *Deformation Plasticity on an orientation ------------------------------------------
    # an isotropic law, so Abaqus' results do not depend on the axes, but ccx 2.23's do (CalculiX
    # issue #160: up to 84 % off on turned axes, a hang on zero ones): abq2ccx writes its sections
    # without the orientation, and a bar on any must move as the one without
    for typ in ("C3D8", "C3D20R"):
        ref = faithful_run(dp_bar_deck(typ, "none"), f"deformation_plasticity_{typ.lower()}")
        if ref is None:
            failures += 1
            continue
        scale = max(abs(x) for v in ref.values() for x in v)
        for ori in ("turned", "cylindrical", "spherical"):
            tag = f"deformation_plasticity_{typ.lower()}_{ori}"
            u = faithful_run(dp_bar_deck(typ, ori), tag)
            if u is None:
                failures += 1
                continue
            err = ccx_ratio(max(abs(x - y) for n in ref for x, y in zip(u.get(n, [math.inf] * 3), ref[n])),
                            scale)
            ok = err < 1e-9
            print(f"{'PASS' if ok else 'FAIL'}  {tag} (four {typ} past yield, a {ori} *Orientation): "
                  f"displacements {err:.1e} of the largest {scale:.4g} off the bar without one")
            failures += 0 if ok else 1
    # ... and in a small-strain step: ccx 2.23 runs the law under NLGEOM, in the logarithmic
    # strain and the Cauchy stress, where Abaqus takes the small strain (reduced physics), and
    # with an explicit NLGEOM=NO reads the small strain as a Green-Lagrange one, so abq2ccx
    # drops that: both spellings strain as ccx's law says
    want, small = dp_uniaxial_strains(500.0)
    for step in ("*Step", "*Step, nlgeom=NO"):
        tag = "deformation_plasticity_small_strain" + ("_nlgeom_no" if "NO" in step else "")
        src, inp = os.path.join(tmp, f"{tag}_src.inp"), os.path.join(tmp, f"{tag}.inp")
        with open(src, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(dp_cube_deck(step))
        _rep, conv = convert(src, inp)
        d, status, out = run_ccx(ccx, env, inp)
        u = dat_displacements(os.path.join(d, "job.dat")) if status == "solved" else None
        shutil.rmtree(d, ignore_errors=True)
        eps = sum(u[n][0] for n in (2, 3, 6, 7)) / 4 if u else math.nan
        flagged = len(conv.reduced_physics) == 1 and "small-strain step" in conv.reduced_physics[0]
        ok = flagged and abs(eps / want - 1) < 1e-3
        print(f"{'PASS' if ok else 'FAIL'}  {tag} (a free C3D8 cube pulled to 2 sigma0, '{step}'): "
              f"strain {eps:.6g}, ccx's law {want:.6g} ({eps / want - 1:+.1e}), "
              f"{(eps / small - 1) * 100:+.1f} % past Abaqus' small-strain {small:.6g}; "
              + ("reduced physics" if flagged else f"reduced physics: {conv.reduced_physics}"))
        failures += 0 if ok else 1
    # --- quadratic membranes: ccx 2.23 expands each element on nodes of its own and leaves the
    # mid-thickness node of its corners free (M3D8R singular, M3D6 / M3D8 too soft); abq2ccx
    # writes the solids itself, held at the membrane nodes by *EQUATION
    for typ in ("M3D8R", "M3D8", "M3D6", "M3D9R"):
        for stretch in (None, 1.2):
            tag = f"quad_membrane_{typ.lower()}" + ("_nlgeom" if stretch else "")
            text = quad_membrane_strip_deck(typ, stretch=stretch)
            res = composite_run(text, tag)
            u = res[0].get(int(text.split("*Nset, nset=PROBE\n")[1].split("\n")[0])) if res else None
            if u is None:
                if res is not None:                # solved, but without the probe node
                    print(f"FAIL  {tag}: no displacement at the probe node")
                failures += 1
                continue
            want = (2e-3, -0.3e-3) if stretch is None else (2 * (stretch - 1), 0.0)
            err = max(abs(u[0] / want[0] - 1), abs(u[1] - want[1]) / abs(want[0]))
            ok = err < 1e-6
            print(f"{'PASS' if ok else 'FAIL'}  {tag} (strip of {typ}, thickness 0.1, uniaxial tension"
                  + (f", NLGEOM, stretch {stretch}" if stretch else "") + f"): end displacement "
                  f"{u[0]:.7g}, {u[1]:.4g} vs {want[0]:g}, {want[1]:g}"
                  + (" (St. Venant-Kirchhoff)" if stretch else "") + f", max difference {err:.1e}")
            failures += 0 if ok else 1
    for typ in ("M3D8R", "M3D6"):
        t = 0.01
        res = composite_run(sheet_sphere_deck(typ, 16, t), f"quad_membrane_sphere_{typ.lower()}")
        if res is None:
            failures += 1
            continue
        want = 0.7 / (2 * 1e5 * t)
        ur = [math.sqrt(sum(c * c for c in v)) for v in res[0].values()]
        err = max(abs(x / want - 1) for x in ur)
        ok = err < 0.005
        print(f"{'PASS' if ok else 'FAIL'}  quad_membrane_sphere_{typ.lower()} (sphere octant of {typ}, "
              f"t/R {t:g}, internal pressure): radial displacement {min(ur):.5g} .. {max(ur):.5g} vs "
              f"thin-wall theory {want:.5g}, max difference {err * 100:.2f}%")
        failures += 0 if ok else 1
    # --- shell / membrane pressure on the reference surface: ccx 2.23 loads one face of its
    # expanded element (a shell's P, P1 and P2 alike the bottom one, whose area is off by
    # O(t/R)) and that leaves a mean stress -p/2 through the thickness of its 3-D solid; abq2ccx
    # splits the pressure between both faces.  Sphere octants and a half cylinder, t/R 0.1, nu
    # 0.3: the symmetry-plane reaction against p times the reference surface's projected area
    # (on a sphere times 1 + (1 - 4 o^2) (t/2R)^2, the split's residual for OFFSET o; NLGEOM:
    # the deformed sphere's), the mean radial displacement against thin-wall theory
    t, e_mod = 0.1, 1e5
    for typ, kw, tag in (("S8R", {}, "s8r"), ("S8R", {"load": "SNEG"}, "s8r_sneg"),
                         ("S8R", {"load": "SPOS"}, "s8r_spos"), ("S8R", {"sets": 2}, "s8r_two_sets"),
                         ("S6", {}, "s6"),
                         ("S8R", {"offset": "SPOS", "nu": 0.0}, "s8r_offset"),
                         ("S8R", {"nlgeom": True}, "s8r_nlgeom"), ("S4R", {}, "s4r"),
                         ("M3D4", {}, "m3d4"), ("M3D8R", {}, "m3d8r"), ("M3D6", {}, "m3d6"), ("S8R", None, "cylinder_s8r")):
        tag = "sheet_pressure_" + tag
        linear = typ in ("S4R", "M3D4")
        if kw is None:
            text, nu, p = sheet_cylinder_deck(typ, 8, t), 0.3, 1.0
        else:
            nu = kw.get("nu", 0.3)
            p = 0.05 * 2 * e_mod * t / (1 - nu) if kw.get("nlgeom") else 1.0     # ~5 % stretch
            text = sheet_sphere_deck(typ, 16 if linear else 8, t, p, **kw)
        res = composite_run(text, tag)
        if res is None:
            failures += 1
            continue
        pts = {int(ln.split(",")[0]): [float(c) for c in ln.split(",")[1:]]
               for ln in text.split("*Node\n")[1].split("*Element")[0].splitlines()}
        if kw is None:
            for x in pts.values():
                x[2] = 0.0
        ur = sum(_dot(res[0][k], [c / math.sqrt(_dot(x, x)) for c in x]) for k, x in pts.items()) / len(pts)
        o = 0.5 if kw and kw.get("offset") else 0.0
        if kw is None:
            force, want_f, want_u = -res[1][-1][1], 2 * p, p / (e_mod * t)
        else:
            r = 1 + ur if kw.get("nlgeom") else 1.0
            force, want_f, want_u = -res[1][-1][0], p * math.pi / 4 * r ** 2 * (1 + (1 - 4 * o * o) * (t / 2 / r) ** 2), \
                p * (1 - nu) / (2 * e_mod * t)
        err_f, err_u = abs(force / want_f - 1), abs(ur / want_u - 1)
        # linear elements: ccx's RF at a held node leaves out its own share of the face load
        # (1 - O(h^2)), and M3D4's force barely moves (each element its own flat slab); its
        # displacement does (the through-thickness stress)
        checks = [err_f < (5e-3 if linear else 5e-4)] if typ != "M3D4" else []
        checks += [] if kw and kw.get("nlgeom") else [err_u < 5e-3]
        ok = all(checks)
        what = ("half cylinder" if kw is None else "sphere octant") + f" of {typ}, t/R {t:g}, " + \
            ("*DLOAD P" if not kw or "load" not in kw else f"*DSLOAD on {kw['load']}") + \
            (" on two sets in one card" if kw and kw.get("sets") else "") + \
            (", OFFSET=SPOS, nu 0" if o else "") + (", NLGEOM (5 % stretch)" if kw and kw.get("nlgeom") else "")
        disp = "" if kw and kw.get("nlgeom") else \
            f", mean radial displacement {ur:.6g} vs thin-wall {want_u:.6g} ({err_u * 100:.2f}% off)"
        print(f"{'PASS' if ok else 'FAIL'}  {tag} ({what}): pressure force {force:.6g} vs {want_f:.6g} "
              f"({err_f * 100:.3f}% off){disp}")
        failures += 0 if ok else 1
    # --- a *TIE / tied pair / kinematic coupling on membrane faces: ccx would take its expanded
    # membrane's face, whose bottom nodes its hinge eliminates (SNEG ties nothing, SPOS ties a
    # face that shears through the thickness); abq2ccx takes the membrane nodes, as Abaqus does
    for typ, flip, pair in (("M3D4", False, False), ("M3D4", True, False), ("M3D4R", False, False),
                            ("M3D3", True, False), ("M3D4", False, True)):
        face = "SPOS" if flip else "SNEG"
        tag = f"membrane_{'tied_pair' if pair else 'tie'}_{typ.lower()}_{face.lower()}"
        text, probe = membrane_skin_deck(typ, True, flip)
        if pair:
            text = text.replace("*Tie, name=GLUE\nSKIN_FACE, BLOCK_TOP",
                                "*Surface Interaction, name=GLUE\n*Contact Pair, interaction=GLUE, tied\n"
                                "SKIN_FACE, BLOCK_TOP")
        ref_text, ref_probe = membrane_skin_deck(typ, False)
        res, ref = composite_run(text, tag), composite_run(ref_text, tag + "_ref")
        if res is None or ref is None:
            failures += 1
            continue
        got, want = res[0].get(probe, [math.inf])[0], ref[0].get(ref_probe, [math.nan])[0]
        err = abs(ccx_ratio(got, want) - 1)
        ok = err < 1e-6
        print(f"{'PASS' if ok else 'FAIL'}  {tag} ({typ} skin {'tied by a *CONTACT PAIR, TIED' if pair else 'tied'} "
              f"by its {face} face to a block, no position tolerance): end displacement {got:.7g} vs "
              f"{want:.7g} with the skin on the block's nodes ({err:.1e} apart; native ccx: "
              f"{'untied, about 1e-3' if face == 'SNEG' else 'its face tied, 5.9 % stiff'})")
        failures += 0 if ok else 1
    # *MEMBRANE SECTION, DENSITY= (mass per area added to the material's; ccx has no section
    # mass) -> a copy of the material with DENSITY / t more: the frequencies of the same strip
    # whose material has that density
    for typ in ("M3D4", "M3D8R"):
        tag = f"membrane_area_mass_{typ.lower()}"
        freqs = []
        for k, text in enumerate((membrane_mass_deck(typ), membrane_mass_deck(typ, 7.0 + 2.0 / 0.01, 0.0))):
            src, inp = os.path.join(tmp, f"{tag}_{k}_src.inp"), os.path.join(tmp, f"{tag}_{k}.inp")
            with open(src, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
            convert(src, inp)
            d, status, out = run_ccx(ccx, env, inp)
            freqs.append(dat_eigen_table(os.path.join(d, "job.dat"), "E I G E N V A L U E   O U T P U T")
                         if status == "solved" else [])
            shutil.rmtree(d, ignore_errors=True)
        if min(len(f) for f in freqs) < 3:
            print(f"FAIL  {tag}: no frequencies ({status})")
            failures += 1
            continue
        err = max(abs(ccx_ratio(a, b) - 1) for a, b in zip(freqs[0][:3], freqs[1][:3]))
        ok = err < 1e-6
        print(f"{'PASS' if ok else 'FAIL'}  {tag} ({typ} strip, material density 7, thickness 0.01, "
              f"section DENSITY=2): first frequencies {', '.join(f'{x:.6g}' for x in freqs[0][:3])} vs "
              f"{', '.join(f'{x:.6g}' for x in freqs[1][:3])} with density 207 in the material ({err:.1e} "
              f"apart; the section mass dropped: 5.4x higher)")
        failures += 0 if ok else 1
    for typ, face in (("M3D4", "SNEG"), ("M3D3", "SPOS"), ("M3D4R", "SNEG"), ("S4", "SNEG"), ("S3", "SPOS")):
        tag = f"sheet_coupling_{typ.lower()}_{face.lower()}"
        text, probe = sheet_coupling_deck(typ, face)
        res = composite_run(text, tag)
        if res is None:
            failures += 1
            continue
        got, want = res[0].get(probe, [math.inf])[0], 1.75 / 2000
        err = abs(got / want - 1)
        ok = err < 1e-6
        print(f"{'PASS' if ok else 'FAIL'}  {tag} ({typ} strip, kinematic coupling on its last column's "
              f"{face} face, pulled): end displacement {got:.7g} vs {want:.7g} for a rigid end column "
              f"({err:.1e} apart; ccx on the faces: M3D4 1.2 % off, M3D4R 0.3 %, M3D3 / S3 / S4 crash)")
        failures += 0 if ok else 1
    ref = None
    for plane, tilt in (("XY", 0.0), ("XY", 30.0), ("XZ", 30.0), ("YZ", 30.0)):
        res = composite_run(distribution_panel_deck(plane, tilt), f"distribution_panel_{plane}_{tilt:g}")
        if res is None:
            failures += 1
            continue
        place = plate_place(plane)
        basis = [place(v) for v in ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))]
        u = {nd: tuple(_dot(v, e) for e in basis) for nd, v in res[0].items()}
        if ref is None:
            ref = u
            continue
        scale = max(abs(x) for v in ref.values() for x in v)
        err = ccx_ratio(max(abs(x - y) for nd in ref for x, y in zip(ref[nd], u.get(nd, (math.inf,) * 3))),
                        scale)
        ok = set(u) == set(ref) and err < 1e-6
        print(f"{'PASS' if ok else 'FAIL'}  distribution_panel_{plane}_{tilt:g} (composite S8R, "
              f"*DISTRIBUTION orientation with b {tilt:g} deg out of the plate, {plane} plane): "
              f"{len(u)} node displacements in plate axes vs the x-y strip with b in the plate, max "
              f"difference {err:.1e} of max |u|")
        failures += 0 if ok else 1

    # --- decks the converter got wrong before the 19 Oct 2026 code review ------------------
    def review_run(text, tag, read, approximate=False):
        """``read(.dat path)`` of ``text`` converted and solved, or None (FAIL printed)."""
        src, inp = os.path.join(tmp, f"{tag}_src.inp"), os.path.join(tmp, f"{tag}.inp")
        with open(src, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        try:
            convert(src, inp, approximate=approximate)
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL  {tag}: the conversion failed ({exc!r})")
            return None
        d, status, out = run_ccx(ccx, env, inp)
        res = read(os.path.join(d, "job.dat")) if status == "solved" else None
        shutil.rmtree(d, ignore_errors=True)
        if not res:
            print(f"FAIL  {tag}: no results ({status})")
            print("\n".join(l for l in out.splitlines() if "ERROR" in l)[:400])
        return res

    # a planar beam's tip node coupled to a reference node (the converter stopped on it)
    tips = [review_run(planar_coupled_tip_deck(c), "planar_coupled_tip" + ("" if c else "_ref"),
                       dat_displacements) for c in (True, False)]
    if all(tips):
        got, want = tips[0].get(11, [0.0, math.inf])[1], tips[1].get(11, [0.0, math.nan])[1]
        off = max(abs(v[2]) for v in tips[0].values())
        err = abs(ccx_ratio(got, want) - 1)
        ok = err < 1e-4 and off < 1e-9 * abs(want)
        print(f"{'PASS' if ok else 'FAIL'}  planar_coupled_tip (B21 cantilever, its tip coupled by "
              f"*COUPLING, *KINEMATIC to the loaded reference node): tip deflection {got:.7g} vs "
              f"{want:.7g} loaded at the tip ({err:.1e} apart: the tip's knot beam), out of plane "
              f"{off:.1e}")
    failures += 0 if all(tips) and ok else 1
    # a velocity BC card a rigid constraint implies, left out whole (it came back, and ccx
    # stopped); the free middle nodes show that ccx solved the step
    u = review_run(coupled_velocity_deck(), "coupled_velocity_card", dat_displacements)
    if u:
        got = [u.get(n, [math.inf])[0] for n in (9, 10, 11, 12)]
        mid = [u.get(n, [0.0])[0] for n in (5, 6, 7, 8)]
        ok = max(abs(x - 2.0) for x in got) < 1e-9 and all(0.1 < x < 1.9 for x in mid)
        print(f"{'PASS' if ok else 'FAIL'}  coupled_velocity_card (a column's rigid top face given "
              f"its reference node's velocity 2 by a second *BOUNDARY, TYPE=VELOCITY): top face at "
              f"{', '.join(f'{x:.7g}' for x in got)} after time 1 (2; the card as written stops ccx: "
              f"'dependent side of a MPC and a SPC'), free middle nodes at "
              f"{', '.join(f'{x:.4g}' for x in mid)}")
    failures += 0 if u and ok else 1
    # amplitude points 1e-4 apart at total time 100 (written to 6 digits, they fell on t = 100)
    for definition, want in (("EQUALLY SPACED", (0.25, 0.5, 0.75, 1.0)),
                             ("SMOOTH STEP", (0.103515625, 0.5, 0.896484375, 1.0))):
        tag = "amplitude_close_times_" + definition.split()[0].lower()
        hist = review_run(amplitude_close_times_deck(definition), tag,
                          lambda dat: dat_displacement_history(dat, 5))
        ok = bool(hist) and len(hist) == 4
        if ok:
            got = [ccx_ratio(h[2], hist[-1][2]) for h in hist]
            ok = max(abs(g - w) for g, w in zip(got, want)) < 1e-5
            print(f"{'PASS' if ok else 'FAIL'}  {tag} (a cube pulled through *AMPLITUDE, DEFINITION="
                  f"{definition}, rising from total time 100 to 100.0002): displacement after each "
                  f"fixed increment {', '.join(f'{g:.6g}' for g in got)} of the last (the amplitude: "
                  f"{', '.join(f'{w:g}' for w in want)}; the full load at each with the times merged)")
        elif hist:
            print(f"FAIL  {tag}: {len(hist)} increments printed, not 4")
        failures += 0 if ok else 1
    # kinematic couplings in *DYNAMIC steps (ccx's own *COUPLING + *KINEMATIC set up no
    # equations there: every free DOF stayed at 0), against ccx's own coupling in a slow
    # *STATIC step, the static limit; and couplings with an ORIENTATION (ccx reads its axes:
    # the dynamic equations tied global DOFs, the *KINEMATIC COUPLING card lost it, and a
    # part-level coupling named the part's orientation, which ccx stopped on)
    dyn = "ccx's coupling sets up no equations in a dynamic step: they stayed at 0"
    for tag, kw, why in (
            ("kinematic_dynamic_linear", {}, dyn), ("kinematic_dynamic_nlgeom", {"nlgeom": True}, dyn),
            ("kinematic_dynamic_some_dofs", {"dofs": "1, 2"}, dyn),
            ("kinematic_dynamic_explicit", {"proc": "explicit"}, dyn),
            ("kinematic_dynamic_member_bc", {"member_bc": True}, dyn),
            ("kinematic_dynamic_orientation", {"dofs": "1, 2", "ori": True},
             "in a tilted *ORIENTATION; its equations tied global x and y"),
            ("kinematic_dynamic_legacy_orientation", {"dofs": "1, 2", "ori": True, "legacy": True},
             "a *KINEMATIC COUPLING card with an *ORIENTATION"),
            ("kinematic_static_legacy_orientation",
             {"dofs": "1, 2", "ori": True, "legacy": True, "proc": "static"},
             "a *KINEMATIC COUPLING card with an *ORIENTATION, which it lost"),
            ("kinematic_static_part_orientation",
             {"dofs": "1, 2", "ori": True, "part": True, "proc": "static"},
             "both instances of a part coupled in its *ORIENTATION; ccx stopped on the deck")):
        u = review_run(kinematic_dynamic_deck(**kw), tag, dat_displacements)
        src = os.path.join(tmp, f"{tag}_ref.inp")
        with open(src, "w", encoding="utf-8", newline="\n") as fh:
            # (the converter runs an explicit step with NLGEOM)
            fh.write(kinematic_dynamic_deck(kw.get("dofs", "1, 3"),
                                            kw.get("nlgeom", kw.get("proc") == "explicit"), "static",
                                            ori=kw.get("ori", False)))
        d, status, out = run_ccx(ccx, env, src)
        ref = dat_displacements(os.path.join(d, "job.dat")) if status == "solved" else {}
        shutil.rmtree(d, ignore_errors=True)
        ok = bool(u) and set(ref) == set(range(5, 13))
        if ok:
            offs = (0, 100) if kw.get("part") else (0,)        # I2's nodes
            scale = max(math.hypot(*v) for v in ref.values())
            err = ccx_ratio(max(math.dist(u.get(n + o, (math.inf,) * 3), ref[n]) for n in ref for o in offs),
                            scale)
            mid = ccx_ratio(min(math.hypot(*u.get(n + o, (0.0,) * 3)) for n in (5, 6, 7, 8) for o in offs),
                            scale)
            # (the member BC: Abaqus does not apply it, and the converter drops it; ccx kept
            # it, holding node 9 at u3 = 0, where it follows the coupling to -0.15)
            held = ccx_ratio(abs(u.get(9, (0.0,) * 3)[2]), scale)
            ok = err < 1e-3 and mid > 0.2 and (held > 0.1 or "member_bc" not in kw)
            print(f"{'PASS' if ok else 'FAIL'}  {tag} (a column's top face kinematically coupled "
                  f"({kw.get('dofs', '1, 3')}) to a node that moves and turns over a slow "
                  f"{kw.get('proc', 'dynamic')} step{', NLGEOM' if 'nlgeom' in kw else ''}"
                  f"{', a *BOUNDARY on a coupled DOF' if 'member_bc' in kw else ''}): "
                  f"{8 * len(offs)} node displacements vs ccx's own coupling in a static step, max "
                  f"difference {err:.1e} of max |u|; the free middle nodes moved {mid:.2f} of it "
                  f"({why})" + (f", node 9 {held:.2f} along z" if "member_bc" in kw else ""))
        elif u:
            print(f"FAIL  {tag}: the static reference did not solve ({status})")
        failures += 0 if ok else 1
    # a coupling's INFLUENCE RADIUS (ccx ignores it: the whole face followed node 100), against
    # ccx's own coupling on a node surface of the nodes Abaqus couples in a static step; the
    # face's corners lie outside it and move freely
    x0, u0, th = (2., 2., 1.5), (0., 0., -0.1), (0.05, 0., 0.)
    src = os.path.join(tmp, "coupling_influence_radius_ref.inp")
    for proc in ("static", "dynamic"):
        for surface in ("element", "node"):
            tag = f"coupling_influence_radius_{proc}_{surface}"
            u = review_run(influence_radius_deck(surface, proc), tag, dat_displacements)
            with open(src, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(influence_radius_deck(nodes=INFLUENCE_KEPT[surface]))
            d, status, out = run_ccx(ccx, env, src)
            ref = dat_displacements(os.path.join(d, "job.dat")) if status == "solved" else {}
            shutil.rmtree(d, ignore_errors=True)
            ok = bool(u) and set(ref) == set(range(1, 51))
            if ok:
                def rigid(n):          # node n (on the top face) moved rigidly with node 100
                    p = ((n - 26) % 5 - x0[0], (n - 26) // 5 - x0[1], 1. - x0[2])
                    return [u0[0] + th[1] * p[2] - th[2] * p[1], u0[1] + th[2] * p[0] - th[0] * p[2],
                            u0[2] + th[0] * p[1] - th[1] * p[0]]
                scale = max(math.hypot(*v) for v in ref.values())
                err = ccx_ratio(max(math.dist(u.get(n, (math.inf,) * 3), ref[n]) for n in ref), scale)
                held = ccx_ratio(max(math.dist(u[n], rigid(n)) for n in INFLUENCE_KEPT[surface]), scale)
                free = ccx_ratio(min(math.dist(u[n], rigid(n)) for n in (26, 30, 46, 50)), scale)
                ok = err < 1e-3 and held < 1e-9 and free > 0.1
                print(f"{'PASS' if ok else 'FAIL'}  {tag} (a block's top {surface} surface coupled "
                      f"to a node above its centre within an INFLUENCE RADIUS of 0.8, the node moving "
                      f"and turning over a slow {proc} step): 50 node displacements vs ccx's coupling "
                      f"on the {len(INFLUENCE_KEPT[surface])} node(s) Abaqus couples in a static step, "
                      f"max difference {err:.1e} of max |u|; those follow the node rigidly ({held:.0e}), "
                      f"the face's corners moved {free:.2f} of max |u| off it (before: the whole face did)")
            elif u:
                print(f"FAIL  {tag}: the reference did not solve ({status})")
            failures += 0 if ok else 1
    # rotations coupled about the axes of a coupling's ORIENTATION (the knotted shell members'
    # ties took the global axes), against the model turned into those axes, whose global ties
    # the converter writes (validated by the shell checks above), in the same step (ccx turns
    # its knots with the finite rotation in a *DYNAMIC step: 6e-3 off a static one here)
    refs = {proc: review_run(coupled_rotations_deck(proc, turned=True),
                             f"coupled_rotations_orientation_{proc}_ref", dat_displacements)
            for proc in ("static", "dynamic")}
    for proc, legacy in (("static", False), ("dynamic", False), ("static", True)):
        tag = f"coupled_rotations_orientation_{proc}" + ("_legacy" if legacy else "")
        u, ref = review_run(coupled_rotations_deck(proc, legacy), tag, dat_displacements), refs[proc]
        ok = bool(u) and bool(ref) and set(ref) <= set(u)
        if ok:
            back = {n: [sum(ROT_FRAME[k][i] * v[k] for k in range(3)) for i in range(3)] for n, v in ref.items()}
            scale = max(math.hypot(*v) for v in back.values())
            err = ccx_ratio(max(math.dist(u[n], back[n]) for n in back), scale)
            moved = ccx_ratio(min(math.hypot(*u[n]) for n in (2, 3, 4, 12, 13, 14)), scale)
            ok = err < 1e-3 and moved > 0.05
            print(f"{'PASS' if ok else 'FAIL'}  {tag} (a shell strip's tip edge coupled in DOFs 1-5 "
                  f"of an oblique *ORIENTATION" + (", a *KINEMATIC COUPLING card" if legacy else "") +
                  f", to a node that moves and turns over a slow {proc} step): 10 node displacements "
                  f"vs the model turned into the orientation's axes, max difference "
                  f"{err:.1e} of max |u| (ties about the global axes: 1.2e-2 to 1.6e-2); the free nodes "
                  f"moved {moved:.2f} of it")
        failures += 0 if ok else 1
    # member BCs of a coupling of some translations along an ORIENTATION's axes (the converter
    # took them off or kept them by the global DOF numbers): local 1 = global y, a BC on y the
    # reference node's imposes and one on x, unrelated, against ccx's coupling of global y with
    # the x BC (before: ccx stopped); turned 60 / 30 degrees, a BC on x, which the coupling does
    # not hold (before: taken off), and an *EQUATION on the global DOF ccx eliminates (before:
    # ccx stopped)
    def run_ref(text, tag):
        src = os.path.join(tmp, f"{tag}_ref.inp")
        with open(src, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        d, status, out = run_ccx(ccx, env, src)
        res = dat_displacements(os.path.join(d, "job.dat")) if status == "solved" else {}
        shutil.rmtree(d, ignore_errors=True)
        return res
    ref = run_ref(oriented_coupling_deck(dofs="2, 2", bcs=["10, 1, 1, 0.005"], ori=False),
                  "coupling_orientation_member_bc")
    for proc in ("static", "dynamic"):
        tag = f"coupling_orientation_member_bc_implied_{proc}"
        u = review_run(oriented_coupling_deck(90., bcs=["10, 2, 2, 0.02", "10, 1, 1, 0.005"], proc=proc),
                       tag, dat_displacements)
        ok = bool(u) and set(ref) == set(range(1, 19)) | {100}
        if ok:
            scale = max(math.hypot(*v) for v in ref.values())
            err = ccx_ratio(max(math.dist(u.get(n, (math.inf,) * 3), ref[n]) for n in ref), scale)
            free = ccx_ratio(abs(u[18][2]), scale)
            ok = err < (1e-9 if proc == "static" else 1e-3) and free > 0.05
            print(f"{'PASS' if ok else 'FAIL'}  {tag} (a block's top face coupled along local axis 1 "
                  f"of an *ORIENTATION turned 90 degrees, global y, to a node moving over a slow {proc} "
                  f"step, a corner's BC on y the node's imposes and one on x): 19 node displacements vs "
                  f"ccx's coupling of global y with the x BC in a static step, max difference {err:.1e} "
                  f"of max |u| (before: ccx stopped); a free corner moved {free:.2f} of it along z")
        elif u:
            print(f"FAIL  {tag}: the reference did not solve")
        failures += 0 if ok else 1
    for deg, proc, extra, bcs in ((60., "static", "", ["10, 1, 1, 0.01"]), (30., "dynamic", "", ["10, 1, 1, 0.01"]),
                                  (60., "static", "*EQUATION\n2\n10, 2, 1., 11, 3, -1.", [])):
        tag = "coupling_orientation_" + ("equation_static" if extra else f"member_bc_across_{proc}")
        u = review_run(oriented_coupling_deck(deg, bcs=bcs, proc=proc, extra=extra), tag, dat_displacements)
        ok = bool(u) and {100, *range(10, 19)} <= set(u)
        if ok:
            c, s_ = math.cos(math.radians(deg)), math.sin(math.radians(deg))
            e1, e2 = (c, s_, 0.), (-s_, c, 0.)
            scale = max(math.hypot(*v) for v in u.values())
            rel = {n: [u[n][k] - u[100][k] for k in range(3)] for n in range(10, 19)}
            tie = ccx_ratio(max(abs(_dot(e1, rel[n])) for n in rel), scale)
            held = ccx_ratio(abs(u[10][1] - u[11][2] if extra else u[10][0] - 0.01), scale)
            free = ccx_ratio(max(abs(_dot(e2, rel[n])) for n in rel), scale)
            ok = tie < 1e-5 and held < 1e-5 and free > 0.01       # (the .dat's 7 digits: 2e-7)
            print(f"{'PASS' if ok else 'FAIL'}  {tag} (a block's top face coupled along local axis 1 of "
                  f"an *ORIENTATION turned {deg:g} degrees about z, to a node moving over a slow {proc} "
                  f"step" + (", an *EQUATION u10,y = u11,z on the DOF ccx eliminates" if extra else
                             ", a corner's BC on global x, which the coupling does not hold") +
                  f"): coupling residual {tie:.0e} of max |u|, " +
                  (f"equation residual {held:.0e} (before: ccx stopped)" if extra else
                   f"the BC holds to {held:.0e} (before: taken off, 0.1-0.2 of max |u| off)") +
                  f"; the members moved {free:.2f} of it across the coupled axis")
        failures += 0 if ok else 1
    # ... and a member's BC on the global DOF ccx's coupling eliminates (ccx stopped): the
    # coupling's linear equations, about z (one axis) and an oblique ORIENTATION (two axes)
    for tag, deg, dofs, frame, bc in (("one_axis", 60., "1, 1", None, 2),
                                      ("two_axes", 60., "1, 2", ROT_FRAME, 2)):
        tag = f"coupling_orientation_member_bc_stop_{tag}"
        deck = oriented_coupling_deck(deg, dofs=dofs, bcs=[f"10, {bc}, {bc}, 0.01"])
        if frame:
            deck = re.sub(r"\*ORIENTATION, NAME=OR1\n.*\n", "*ORIENTATION, NAME=OR1\n" + ", ".join(
                f"{x:g}" for x in frame[0] + frame[1]) + "\n", deck)
        c, s_ = math.cos(math.radians(deg)), math.sin(math.radians(deg))
        axes = frame or ((c, s_, 0.), (-s_, c, 0.), (0., 0., 1.))
        coupled = [axes[j] for j in range(int(dofs[0]) - 1, int(dofs[-1]))]
        u = review_run(deck, tag, dat_displacements)
        ok = bool(u) and {100, *range(10, 19)} <= set(u)
        if ok:
            scale = max(math.hypot(*v) for v in u.values())
            rel = {n: [u[n][k] - u[100][k] for k in range(3)] for n in range(10, 19)}
            tie = ccx_ratio(max(abs(_dot(e, rel[n])) for n in rel for e in coupled), scale)
            held = ccx_ratio(abs(u[10][bc - 1] - 0.01), scale)
            free = ccx_ratio(max(abs(_dot(axes[2 if len(coupled) == 2 else 1], rel[n])) for n in rel), scale)
            ok = tie < 1e-5 and held < 1e-5 and free > 0.01       # (the .dat's 7 digits)
            print(f"{'PASS' if ok else 'FAIL'}  {tag} (a block's top face coupled along "
                  f"{'one axis' if len(coupled) == 1 else 'two axes'} of an *ORIENTATION, a corner's BC on "
                  f"global {bc}, the DOF ccx's own coupling "
                  f"eliminates; a static step): coupling residual {tie:.0e} of max |u|, the BC holds to "
                  f"{held:.0e}; the members moved {free:.2f} of it across the coupled axes (before: ccx "
                  f"stopped)")
        failures += 0 if ok else 1
    # *COUPLING REF NODE= a node set of two nodes, each coupled to the nodes within its own
    # INFLUENCE RADIUS (the converter coupled the first only), against two couplings of one
    # reference node each in a static step
    ref = run_ref(several_refs_deck(twin=True), "coupling_several_reference_nodes")
    for proc in ("static", "dynamic"):
        tag = f"coupling_several_reference_nodes_{proc}"
        u = review_run(several_refs_deck(proc), tag, dat_displacements)
        ok = bool(u) and set(ref) == set(range(1, 51))
        if ok:
            scale = max(math.hypot(*v) for v in ref.values())
            err = ccx_ratio(max(math.dist(u.get(n, (math.inf,) * 3), ref[n]) for n in ref), scale)
            moved = ccx_ratio(min(math.hypot(*u[n]) for ns in SEVERAL_KEPT.values() for n in ns), scale)
            free = ccx_ratio(math.hypot(*u[38]), scale)
            ok = err < (1e-9 if proc == "static" else 1e-3) and moved > 0.3 and free > 0.01
            print(f"{'PASS' if ok else 'FAIL'}  {tag} (a block's top face coupled to the two reference "
                  f"nodes of a node set with an INFLUENCE RADIUS, each moving and turning its own way "
                  f"over a slow {proc} step): 50 node displacements vs a coupling of each in a static "
                  f"step, max difference {err:.1e} of max |u| (before: the second was not coupled); "
                  f"the coupled nodes moved at least {moved:.2f} of it, the free centre {free:.2f}")
        elif u:
            print(f"FAIL  {tag}: the reference did not solve")
        failures += 0 if ok else 1
    # an INFLUENCE RADIUS that reaches the first facet in its middle (no node within it), or
    # no facet (Abaqus then takes the nearest one), against ccx's coupling on that facet's
    # nodes in a static step (before: commented out)
    near = (26, 27, 31, 32)
    for case, x0, radius in (("facet_crossed", (0.5, 0.5, 1.3), "0.4"), ("nearest_facet", (0.5, 0.5, 1.5), "0.2")):
        ref = run_ref(influence_radius_deck(nodes=near, ref=x0), f"coupling_influence_radius_{case}")
        for proc in ("static", "dynamic"):
            tag = f"coupling_influence_radius_{case}_{proc}"
            u = review_run(influence_radius_deck("element", proc, ref=x0, radius=radius), tag, dat_displacements)
            ok = bool(u) and set(ref) == set(range(1, 51))
            if ok:
                scale = max(math.hypot(*v) for v in ref.values())
                err = ccx_ratio(max(math.dist(u.get(n, (math.inf,) * 3), ref[n]) for n in ref), scale)
                moved = ccx_ratio(min(math.hypot(*u[n]) for n in near), scale)
                ok = err < (1e-9 if proc == "static" else 1e-3) and moved > 0.3
                print(f"{'PASS' if ok else 'FAIL'}  {tag} (a block's top face coupled to a node with an "
                      f"INFLUENCE RADIUS that " + ("cuts the first facet, no node within it" if case ==
                                                   "facet_crossed" else "reaches no facet") +
                      f", the node moving and turning over a slow {proc} step): 50 node displacements vs "
                      f"ccx's coupling on that facet's nodes in a static step, max difference {err:.1e} "
                      f"of max |u| (before: commented out); they moved at least {moved:.2f} of it")
            elif u:
                print(f"FAIL  {tag}: the reference did not solve")
            failures += 0 if ok else 1
    # a distributing coupling's INFLUENCE RADIUS that cuts the four facets around the centre node
    # by the same part (0.3), or reaches no facet: Abaqus distributes a force and moment on the
    # node over those facets (the nearest one), its tributary-area weights scaled alike; against
    # ccx's distributing coupling on those facets, of DOFs 1-6 (without data lines ccx spreads no
    # moment, Abaqus couples all DOFs) (before: over the whole face)
    for case, x0, radius, facets in (("centre", (2., 2., 1.5), "0.8", (6, 7, 10, 11)),
                                     ("nearest_facet", (0.5, 0.5, 1.5), "0.2", (1,))):
        dist = lambda t: t.replace("*KINEMATIC", "*DISTRIBUTING").replace(  # noqa: E731
            "*BOUNDARY, AMPLITUDE=R\n100, 1, 2\n100, 3, 3, -0.1\n100, 4, 4, 0.05\n100, 5, 6\n",
            "*CLOAD\n100, 3, -10.\n100, 4, 2.\n")
        deck = dist(influence_radius_deck("element", ref=x0, radius=radius))
        ref = run_ref(deck.replace("*SURFACE, NAME=ST\nEALL, S2\n", "*SURFACE, NAME=ST\n" + "".join(
            f"{e}, S2\n" for e in facets)).replace(f", INFLUENCE RADIUS={radius}", "").replace(
            "*DISTRIBUTING\n", "*DISTRIBUTING\n1, 6\n"), f"distributing_influence_radius_{case}")
        tag = f"distributing_influence_radius_{case}"
        u = review_run(deck, tag, dat_displacements)
        ok = bool(u) and set(ref) == set(range(1, 51))
        if ok:
            scale = max(math.hypot(*v) for v in ref.values())
            err = ccx_ratio(max(math.dist(u.get(n, (math.inf,) * 3), ref[n]) for n in ref), scale)
            corners = ccx_ratio(min(math.hypot(*u[n]) for n in (26, 30, 46, 50)), scale)
            ok = err < 1e-9 and scale > 1e-3
            print(f"{'PASS' if ok else 'FAIL'}  {tag} (a block's top face distributing-coupled to a "
                  f"node with an INFLUENCE RADIUS that " + ("cuts the four facets around the centre "
                                                            "alike" if case == "centre" else
                                                            "reaches no facet") +
                  f", a force and moment on the node): 50 node displacements vs ccx's "
                  f"distributing coupling on {len(facets)} facet(s), max difference {err:.1e} of max "
                  f"|u| ({scale:.3g}; the face's corners moved {corners:.2f} of it)")
        elif u:
            print(f"FAIL  {tag}: the reference did not solve")
        failures += 0 if ok else 1
    # rigid constraints in a linear *DYNAMIC step (ccx turns its RIGID MPCs with the finite
    # rotation there: 3-7 % off), against the linear rigid motion prescribed in a *STATIC step;
    # 'transformed': members with a *TRANSFORM (their rows in local axes; a *RIGID BODY was 7 %
    # off), 'pin': PIN members on shell nodes (no knot beams: no RIGID MPC needs them)
    # 'after_nlgeom_frequency': a *STEP, NLGEOM *FREQUENCY step before it, whose NLGEOM Abaqus
    # keeps in that step (the converter made the dynamic step NLGEOM and kept the *RIGID BODY)
    nlfreq = "*STEP, NLGEOM, PERTURBATION\n*FREQUENCY\n2\n*BOUNDARY\nFIX, 1, 3\n*END STEP\n"
    for member, before in [(m, "") for m in ("solid", "mpc", "shell", "planar", "transformed", "pin")] + \
            [("solid", nlfreq)]:
        tag = f"rigid_dynamic_{member}" + ("_after_nlgeom_frequency" if before else "")
        u = review_run(rigid_dynamic_deck(member, before=before), tag, dat_displacements)
        src = os.path.join(tmp, f"{tag}_ref.inp")
        with open(src, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(rigid_dynamic_deck(member, "static"))
        d, status, out = run_ccx(ccx, env, src)
        ref = dat_displacements(os.path.join(d, "job.dat")) if status == "solved" else {}
        shutil.rmtree(d, ignore_errors=True)
        free = RIGID_DYNAMIC[RIGID_MESH.get(member, member)][3]
        ok = bool(u) and bool(ref) and all(n in ref for n in free)
        if ok:
            scale = max(math.hypot(*v) for v in ref.values())
            err = ccx_ratio(max(math.dist(u.get(n, (math.inf,) * 3), ref[n]) for n in ref), scale)
            moved = ccx_ratio(min(math.hypot(*u.get(n, (0.0,) * 3)) for n in free), scale)
            ok = err < 1e-3 and moved > 0.1
            what = {"mpc": "*MPC BEAM lines on solid", "transformed": "a *RIGID BODY on transformed "
                    "solid", "pin": "a *RIGID BODY, PIN NSET on shell"}.get(member, f"a *RIGID BODY on {member}")
            print(f"{'PASS' if ok else 'FAIL'}  {tag} ({what} members driven by a node that moves "
                  f"and turns over a slow linear "
                  f"dynamic step{' after a *STEP, NLGEOM *FREQUENCY step' if before else ''}): "
                  f"{len(ref)} node displacements vs the linear rigid motion prescribed "
                  f"in a static step, max difference {err:.1e} of max |u|; the free nodes moved "
                  f"{moved:.2f} of it (ccx's *RIGID BODY turns with the finite rotation there)")
        elif u:
            print(f"FAIL  {tag}: the static reference did not solve ({status})")
        failures += 0 if ok else 1
    # ... and in the other steps without NLGEOM that ccx runs through its nonlinear solver,
    # where it turns them the same way (1.7-7 % off): a plastic material, a contact pair, a
    # coupled temperature-displacement step, a static step after a heat transfer step; against
    # the linear rigid motion prescribed in the same step and model
    def both(dat):
        disp = dat_displacements(dat)
        return (disp, dat_el_scalar(dat, "equivalent plastic strain")) if disp else None
    for case in ("plastic", "kinematic", "contact", "coupled", "heat", "shell", "planar"):
        tag = f"rigid_nonlinear_{case}"
        u, peeq = review_run(rigid_nonlinear_deck(case), tag, both) or ({}, {})
        ref, _ = review_run(rigid_nonlinear_deck(case, True), tag + "_ref", both) or ({}, {})
        free = RIGID_DYNAMIC[case if case in ("shell", "planar") else "solid"][3]
        ok = bool(u) and bool(ref) and all(n in ref for n in free)
        if ok:
            scale = max(math.hypot(*v) for v in ref.values())
            err = ccx_ratio(max(math.dist(u.get(n, (math.inf,) * 3), ref[n]) for n in ref), scale)
            moved = ccx_ratio(min(math.hypot(*u.get(n, (0.0,) * 3)) for n in free), scale)
            yielded = max(peeq.values(), default=0.0)
            ok = err < 1e-3 and moved > 0.1 and (yielded > 1e-3 or case not in ("plastic", "kinematic"))
            what = {"plastic": "a *RIGID BODY on a plastic column (PEEQ up to {:.3f}), fixed increments",
                    "kinematic": "a kinematic coupling on a plastic column (PEEQ up to {:.3f}), fixed "
                                 "increments",
                    "contact": "a *RIGID BODY on a column beside a *CONTACT PAIR",
                    "coupled": "a *RIGID BODY on a heated C3D8T column, *COUPLED TEMPERATURE-DISPLACEMENT",
                    "heat": "a *RIGID BODY on a C3D8T column, a *STATIC step after a *HEAT TRANSFER step",
                    "shell": "a *RIGID BODY on S4 members, a *PLASTIC not reached",
                    "planar": "a *RIGID BODY on CPS4 members, a *PLASTIC not reached"}[case].format(yielded)
            print(f"{'PASS' if ok else 'FAIL'}  {tag} ({what}; driven by a node that moves and turns "
                  f"over a slow step without NLGEOM): {len(ref)} node displacements vs the "
                  f"linear rigid motion prescribed in "
                  f"{'a linear static' if case in ('shell', 'planar') else 'the same'} step, max "
                  f"difference {err:.1e} of max "
                  f"|u|; the free nodes moved {moved:.2f} of it (ccx's *RIGID BODY turns with the "
                  f"finite rotation there)")
        elif u:
            print(f"FAIL  {tag}: the reference did not solve")
        failures += 0 if ok else 1
    # ... and in an explicit step with NLGEOM=NO (Abaqus/Explicit runs it geometrically linear;
    # ccx turned the RIGID MPC finitely: a corner at (0.3008, -0.1788))
    u = review_run(rigid_explicit_deck(), "rigid_explicit_nlgeom_no", dat_displacements)
    ok = bool(u) and len(u) == 8
    if ok:
        th = 0.5
        err = max(math.dist(u[n], (-th * y, th * x, 0.0)) for n, (x, y, _z) in RIGID_EXPLICIT_CUBE.items())
        ok = err < 1e-9
        print(f"{'PASS' if ok else 'FAIL'}  rigid_explicit_nlgeom_no (a C3D8 cube as a *RIGID BODY turned "
              f"0.5 rad about its centre by a velocity BC in a *DYNAMIC, EXPLICIT step with NLGEOM=NO): "
              f"its 8 nodes at the linear rigid motion theta x r, max difference {err:.1e} (before: "
              f"0.087, the finite rotation)")
    failures += 0 if ok else 1
    # ... the forms that kept ccx's RIGID MPCs there, now equations too: a transformed
    # reference node and a coupling of some translations of transformed nodes (twins of the
    # nodes, _dir_terms), a rotation-only line beside a translation line (rotation ties)
    for case, what in (("ref", "a *RIGID BODY on a reference node with an oblique *TRANSFORM, its "
                               "motion given in its axes, vs the motion in global components"),
                       ("some", "a coupling of DOFs 1-2 of nodes with an oblique *TRANSFORM, vs the "
                                "nodes without it"),
                       ("rotation_line", "a *KINEMATIC COUPLING of a shell edge in lines of DOFs 1-3 "
                                         "and 4-6, vs one line of 1-6")):
        tag = f"rigid_nonlinear_{case}"
        u = review_run(rigid_transformed_deck(case), tag, dat_displacements)
        ref = review_run(rigid_transformed_deck(case, True), tag + "_twin", dat_displacements)
        free = RIGID_DYNAMIC["shell" if case == "rotation_line" else "solid"][3]
        ok = bool(u) and bool(ref) and all(n in ref for n in free)
        if ok:
            scale = max(math.hypot(*v) for v in ref.values())
            err = ccx_ratio(max(math.dist(u.get(n, (math.inf,) * 3), ref[n]) for n in ref), scale)
            moved = ccx_ratio(min(math.hypot(*ref[n]) for n in free), scale)
            ok = err < 1e-9 and moved > 0.1
            print(f"{'PASS' if ok else 'FAIL'}  {tag} ({what}; a *STATIC step with a *PLASTIC never "
                  f"reached, driven by a node that moves and turns): {len(ref)} node displacements, "
                  f"max difference {err:.1e} of max |u|; the free nodes moved {moved:.2f} of it "
                  f"(before: ccx's own constraint, turned with the finite rotation, 2-8 % off)")
        failures += 0 if ok else 1
    # an implicit *DYNAMIC or transient coupled step after a static step, which ccx 2.23 stopped
    # on ("energy output requests, if any, must be specified in the first step"; abq2ccx now
    # requests ENER in step 1): the one-DOF cube starts from the static step's deflection
    for first, second in ((None, "dynamic"), ("frequency", "dynamic"), (None, "coupled")):
        tag = f"energy_{second}" + (f"_after_{first}" if first else "")
        res = review_run(energy_steps_deck(first, second), tag, lambda dat: (
            dat_history(dat, "displacements", "TOP"),
            dat_eigen_table(dat, "E I G E N V A L U E   O U T P U T")))
        hist, freqs = res or ([], [])
        ok = bool(hist) and (first is None or bool(freqs))
        if res and not ok:
            print(f"FAIL  {tag}: no displacements{' or frequency' if first else ''} printed")
        if ok and second == "dynamic":
            err = max(abs(rows[0][2] / 1e-3 - math.cos(100.0 * (t - 1.0))) for t, rows in hist)
            ferr = abs(freqs[0] * 2.0 * math.pi / 100.0 - 1.0) if first else 0.0
            ok = len(hist) == 250 and err < 1e-3 and ferr < 1e-6
            print(f"{'PASS' if ok else 'FAIL'}  {tag} (a one-DOF cube pulled to 1e-3 in a static "
                  f"step{' after a *FREQUENCY step' if first else ''}, then let go in an implicit "
                  f"*DYNAMIC step): {len(hist)} increments of one period within {err:.1e} of the "
                  f"swing 1e-3 cos 100 t" + (f", frequency {freqs[0]:.7g} vs 100 / 2 pi ({ferr:.1e} "
                  f"apart)" if first else "") + " (before: ccx stopped at the *DYNAMIC step)")
        elif ok:
            got = hist[-1][1][0][2]
            ok = abs(got / 2e-3 - 1.0) < 1e-6
            print(f"{'PASS' if ok else 'FAIL'}  {tag} (the cube pulled to 1e-3 in a static step, then "
                  f"heated by 100 in a transient coupled temperature-displacement step, its lateral "
                  f"expansion held): top at {got:.7g} vs 1e-3 + alpha dT L = 2e-3 (before: ccx stopped "
                  f"at the coupled step)")
        failures += 0 if ok else 1
    # *EL FILE requests ccx 2.23 stopped or crashed on, which abq2ccx now drops: ENER and SDV of
    # a model with U1 beams ('only coded for fields with 6 entries'), SDV of a model with state
    # variables in a linear static step or carried into a *FREQUENCY / *STEADY STATE DYNAMICS
    # step (segfaults).  The U1 tip against beam theory, the cube's top against 100 / E, and the
    # carried runs against the same decks without SDV requested (every displacement table)
    tip = review_run(el_file_stops_deck("u1"), "el_file_u1_ener", dat_node_blocks)
    if tip:
        got, want = (tip[0].get(11) or [0.0, math.nan])[1], 100.0 * 1000.0 ** 3 / (3 * 210000.0 * 4.0e5)
        ok = abs(got / want - 1.0) < 1e-6
        print(f"{'PASS' if ok else 'FAIL'}  el_file_u1_ener (a B31 cantilever under *BEAM GENERAL "
              f"SECTION as U1, *OUTPUT, FIELD, VARIABLE=ALL): tip deflection {got:.7g} vs P L^3 / 3 E I "
              f"= {want:.7g} (before: ccx stopped writing ENER)")
    failures += 0 if tip and ok else 1
    def top_and_sdv(dat):
        with open(os.path.join(os.path.dirname(dat), "job.frd"), errors="replace") as fh:
            return dat_displacements(dat), fh.read().count(" -4  SDV")
    for case, what, before in (("depvar", "in a linear static step", "ccx segfaulted"),
                               ("visco", "in a *VISCO step, which ccx runs linearly", "ccx segfaulted"),
                               ("riks", "in a Riks step (--approximate: a linear *STATIC)",
                                "ccx segfaulted"),
                               ("dynamic", "in a static step after a *DYNAMIC step, which ccx "
                                "iterates", "SDV dropped"),
                               ("explicit", "in a static step after an explicit *DYNAMIC and a "
                                "*FREQUENCY step, NLGEOM carried on", "SDV dropped")):
        res = review_run(el_file_stops_deck(case), f"el_file_{case}_sdv", top_and_sdv,
                         approximate=case == "riks")
        if res:
            top, frd_sdv = res
            got = [top.get(n, [0.0, 0.0, math.nan])[2] for n in (5, 6, 7, 8)]
            ok = max(abs(u * 210000.0 / 100.0 - 1.0) for u in got) < \
                (1e-3 if case == "explicit" else 1e-6) and (frd_sdv > 0) == (case in ("dynamic", "explicit"))
            print(f"{'PASS' if ok else 'FAIL'}  el_file_{case}_sdv (a cube of an elastic material with "
                  f"*DEPVAR pulled {what}, S and SDV requested): top at "
                  f"{', '.join(f'{u:.7g}' for u in got)} vs 100 / E = {100.0 / 210000.0:.7g}, "
                  f"{frd_sdv} SDV block(s) in the .frd (before: {before})")
        failures += 0 if res and ok else 1

    def disp_tables(dat):
        return ([(time, rows) for _, title, _s, time, rows in A.dat_blocks(dat)
                 if title.startswith("displacements")],
                dat_eigen_table(dat, "E I G E N V A L U E   O U T P U T"))
    for case, what in (("carried", "*DEPVAR, NLGEOM, then *FREQUENCY and *STEADY STATE DYNAMICS"),
                       ("plastic", "a plastic material, then *FREQUENCY")):
        runs = [review_run(el_file_stops_deck(case, sdv), f"el_file_{case}_sdv" + ("" if sdv else "_ref"),
                           disp_tables) for sdv in (True, False)]
        ok = all(runs) and len(runs[0][0]) == len(runs[1][0]) > 1 and len(runs[0][1]) == 3
        if ok:
            (tables, freqs), (ref_tables, ref_freqs) = runs
            diff = max(abs(a - b) / (max(abs(x) for r in rr for x in r[1:]) or 1.0)
                       for (_t, rows), (_rt, rr) in zip(tables, ref_tables)
                       for row, rrow in zip(rows, rr) for a, b in zip(row, rrow))
            stretch = [r[3] * 210000.0 / 100.0 for r in tables[0][1]]
            ssd = max((abs(x) for t, rows in tables if t >= 1.0e5 for r in rows for x in r[1:]),
                      default=0.0)
            ok = (diff < 1e-9 and freqs == ref_freqs and max(abs(s - 1.0) for s in stretch) < 1e-3
                  and (case == "plastic" or ssd > 1e-5))
            print(f"{'PASS' if ok else 'FAIL'}  el_file_{case}_sdv (a cube of {what}, S and SDV "
                  f"requested in step 1): {len(tables)} displacement tables within {diff:.1e} of the "
                  f"same deck without SDV, top at {min(stretch):.6f} x 100 / E, f1 = {freqs[0]:.7g} Hz"
                  + (f", steady-state |u| up to {ssd:.3g}" if case == "carried" else "")
                  + " (before: ccx segfaulted in step 2)")
        elif all(runs):
            print(f"FAIL  el_file_{case}_sdv: tables or frequencies missing")
        failures += 0 if ok else 1
    # *EL PRINT ELKE, which ccx 2.23 segfaulted on in a linear static and a *BUCKLE step (abq2ccx
    # now drops it there, and writes the cards ccx would carry on without it again where it
    # runs): the one-DOF cube's energies against u0 cos 100 t, the column's buckling factors
    # and sideways pull against the same deck without ELKE

    def energy_tables(dat):
        return {title: [(t, rows[0][-1]) for _, tt, _s, t, rows in A.dat_blocks(dat)
                        if tt.startswith(title) and rows]      # the element's energy, node 5's z
                for title in ("kinetic energy", "internal energy", "displacements")}
    res = review_run(elke_steps_deck("dynamic"), "elke_static_then_dynamic", energy_tables)
    if res:
        kin = [(t, e) for t, e in res["kinetic energy"] if t > 1.0]
        internal = dict(res["internal energy"])
        ok = bool(kin) and 1.0 in internal and not any(t <= 1.0 for t, _e in res["kinetic energy"])
        if ok:
            err = max(abs(e / 5e-4 - math.sin(100.0 * (t - 1.0)) ** 2) for t, e in kin)
            swing = max(abs(u / 1e-3 - math.cos(100.0 * (t - 1.0)))
                        for t, u in res["displacements"] if t > 1.0)
            ok = len(kin) >= 20 and err < 1e-2 and swing < 1e-2 and abs(internal[1.0] / 5e-4 - 1) < 1e-6
            print(f"{'PASS' if ok else 'FAIL'}  elke_static_then_dynamic (the one-DOF cube pulled to "
                  f"1e-3 in a static step requesting ELKE and ELSE, then let go in an implicit *DYNAMIC "
                  f"step carrying them): static internal energy {internal[1.0]:.7g} vs k u0^2 / 2 = 5e-4, "
                  f"{len(kin)} kinetic energies within {err:.1e} x 5e-4 of 5e-4 sin^2 100 t, the top "
                  f"within {swing:.1e} x u0 of u0 cos 100 t (before: ccx segfaulted in the static step)")
        else:
            print("FAIL  elke_static_then_dynamic: kinetic energy missing from the dynamic step, or "
                  "printed in the static one")
    failures += 0 if res and ok else 1

    def buckle_tables(dat):
        return (dat_eigen_table(dat, "B U C K L I N G   F A C T O R   O U T P U T"),
                dat_displacements(dat), dat_tables(dat, "internal energy"))
    runs = [review_run(elke_steps_deck("buckle", elke), "elke_buckle" + ("" if elke else "_ref"),
                       buckle_tables) for elke in (True, False)]
    ok = all(runs) and len(runs[0][0]) == 2
    if ok:
        (factors, u, energies), (ref_factors, ref_u, _) = runs
        tip = [n for n in u if n in ref_u]
        ok = (factors == ref_factors and factors[0] > 1.0 and bool(energies) and len(tip) == 1
              and u[tip[0]] == ref_u[tip[0]] and u[tip[0]][0] > 0.0)
        print(f"{'PASS' if ok else 'FAIL'}  elke_buckle (a column's *BUCKLE step printing ELKE and "
              f"ELSE, then a sideways pull): buckling factors {factors[0]:.7g}, {factors[1]:.7g} and "
              f"the pulled tip at {u[tip[0]][0]:.4g} as without ELKE, {len(energies)} ELSE tables "
              f"(before: ccx segfaulted in the *BUCKLE step)")
    elif all(runs):
        print("FAIL  elke_buckle: buckling factors missing")
    failures += 0 if ok else 1
    # ELKE after a *FREQUENCY step, which deactivates it in ccx for every later step (abq2ccx now
    # writes the cards again in the dynamic step after it), and a *STATIC step after a *DYNAMIC and
    # a *FREQUENCY step, which ccx runs linearly again (it segfaulted on ELKE there): the one-DOF
    # cube's swing, kinetic energy, frequency and static deflection
    half = math.pi / 100.0
    for last in ("dynamic", "static"):
        tag = f"elke_after_frequency_{last}"
        res = review_run(elke_frequency_deck(last), tag, lambda dat: (
            energy_tables(dat), dat_eigen_table(dat, "E I G E N V A L U E   O U T P U T")))
        ok = False
        if res:
            tables, freqs = res
            kin, disp = tables["kinetic energy"], tables["displacements"]
            ferr = abs(freqs[0] * 2.0 * math.pi / 100.0 - 1.0) if freqs else math.inf
            amp = next((u for t, u in reversed(disp) if t <= half * 1.0001), math.nan)
            later = [(t, e) for t, e in kin if half * 1.0001 < t <= 2.0001 * half]
            first = [(t, e) for t, e in kin if t <= half * 1.0001]
            if last == "dynamic":
                err = max((ccx_ratio(abs(e - 500.0 * amp ** 2 * math.sin(100.0 * (t - half)) ** 2),
                                     500.0 * amp ** 2) for t, e in later), default=math.inf)
                swing = max((abs(ccx_ratio(u, amp) - math.cos(100.0 * (t - half))) for t, u in disp
                             if half * 1.0001 < t <= 2.0001 * half), default=math.inf)
                ok = (len(later) >= 20 and bool(first) and err < 1e-2 and swing < 1e-2 and ferr < 1e-6
                      and abs(amp / 2e-3 - 1.0) < 1e-2)
                print(f"{'PASS' if ok else 'FAIL'}  {tag} (the one-DOF cube swung to {amp:.6g} in a "
                      f"*DYNAMIC step printing ELKE, then a *FREQUENCY step, then let go in a *DYNAMIC "
                      f"step carrying the request): f1 {freqs[0] if freqs else math.nan:.7g} vs 100 / 2 pi "
                      f"({ferr:.1e} apart), {len(later)} kinetic energies within {err:.1e} of "
                      f"k A^2 / 2 sin^2 100 t, the top within {swing:.1e} x A of A cos 100 t (before: "
                      f"no kinetic energy after the *FREQUENCY step)")
            else:
                top = disp[-1][1] if disp else math.nan
                ok = (bool(first) and not later and ferr < 1e-6 and abs(top / 1e-3 - 1.0) < 1e-6
                      and abs(amp / 2e-3 - 1.0) < 1e-2)
                print(f"{'PASS' if ok else 'FAIL'}  {tag} (the one-DOF cube swung to {amp:.6g} in a "
                      f"*DYNAMIC step, then a *FREQUENCY and a *STATIC step under the load printing "
                      f"ELKE): f1 {freqs[0] if freqs else math.nan:.7g} vs 100 / 2 pi ({ferr:.1e} apart), "
                      f"the top at {top:.7g} vs u0 = 1e-3 (before: ccx segfaulted in the static step)")
        failures += 0 if ok else 1
    # Abaqus *CONTACT PRINT CFN for every contact pair (ccx stopped: 'no existing contact pair
    # defined'): the rigid punch's total normal contact force against its reference node's force
    res = review_run(contact_print_deck(), "contact_print_cfn", lambda dat: (
        dat_tables(dat, "statistics"), dat_history(dat, "forces", "REF")))
    ok = False
    if res:
        stats, rf = res
        cfn = stats[-1][0][2] if stats and stats[-1] else math.nan
        ref = rf[-1][1][0][2] if rf and rf[-1][1] else math.nan
        ok = abs(ccx_ratio(cfn, ref) - 1.0) < 1e-6
        print(f"{'PASS' if ok else 'FAIL'}  contact_print_cfn (a rigid flat punch pressed by 0.01, "
              f"*CONTACT PRINT CFN, CPRESS for every pair): total normal contact force {cfn:.7g} vs "
              f"the punch's reference-node force {ref:.7g} (before: ccx stopped reading the card)")
    failures += 0 if ok else 1
    # a SYMMETRIC layup's thickness in a tie to a rigid plate (counted half, ccx got the tie)
    strips = [review_run(tied_strip_deck(sym), "rigid_tie_symmetric_layup" + ("" if sym else "_ref"),
                         dat_displacements) for sym in (True, False)]
    if all(strips):
        got, want = strips[0].get(15, [0.0, 0.0, math.inf])[2], strips[1].get(15, [0.0, 0.0, math.nan])[2]
        err = abs(ccx_ratio(got, want) - 1)
        ok = err < 1e-9
        print(f"{'PASS' if ok else 'FAIL'}  rigid_tie_symmetric_layup (a composite S4R strip [0/90]s "
              f"tied to a clamped rigid plate under its first element, POSITION TOLERANCE=0.1): tip "
              f"deflection {got:.7g} vs {want:.7g} with all four plies listed ({err:.1e} apart; taken "
              f"half as thick, its tie was left to ccx: 3.3x)")
    failures += 0 if all(strips) and ok else 1
    # the same strip on a tied *CONTACT PAIR (ADJUST=0.1): its half thickness counts too, and a
    # tied pair ties translations only (Abaqus 2017 "Defining tied contact in Abaqus/Standard"),
    # so it bends like the strip with those nodes held in translation (left to ccx's tie of its
    # expanded faces, as before: 1.8x)
    tie_line = "*TIE, NAME=T, POSITION TOLERANCE=0.1, ADJUST=NO\nSLAVE, MASTER"
    pair_strips = [review_run(text, tag, dat_displacements) for text, tag in (
        (tied_strip_deck(False).replace(tie_line, "*SURFACE INTERACTION, NAME=SI\n*CONTACT PAIR, "
                                                  "INTERACTION=SI, TIED, ADJUST=0.1\nSLAVE, MASTER"),
         "rigid_tied_pair_shell"),
        (tied_strip_deck(False).replace(tie_line, "").replace(
            "*BOUNDARY\n100, 1, 6\n", "*BOUNDARY\n100, 1, 6\n11, 1, 3\n12, 1, 3\n21, 1, 3\n22, 1, 3\n"),
         "rigid_tied_pair_shell_ref"))]
    ok = False
    if all(pair_strips):
        got, want = (r.get(15, [0.0, 0.0, math.nan])[2] for r in pair_strips)
        err = abs(got / want - 1)
        ok = err < 1e-9
        print(f"{'PASS' if ok else 'FAIL'}  rigid_tied_pair_shell (the strip tied to the clamped rigid "
              f"plate by a *CONTACT PAIR, TIED, ADJUST=0.1): tip deflection {got:.7g} vs {want:.7g} "
              f"with the tied nodes held in translation ({err:.1e} apart; left to ccx's tie: 1.8x)")
    failures += 0 if ok else 1
    # a *STEP without *END STEP is closed before the next *STEP (it was written nested in the
    # next step, where ccx stops): a cube (E 1000, nu 0) pulled by 100, then by 200 (OP=NEW)
    unterminated = (CUBE8 + "*MATERIAL, NAME=M\n*ELASTIC\n1000., 0.\n" + CUBE8_HELD +
                    "*STEP\n*STATIC\n*CLOAD\nTOP, 3, 25.\n*NODE PRINT, NSET=TOP\nU\n*STEP\n*STATIC\n"
                    "*CLOAD, OP=NEW\nTOP, 3, 50.\n*NODE PRINT, NSET=TOP\nU\n*END STEP\n")
    blocks = review_run(unterminated, "unterminated_step", dat_node_blocks)
    ok = False
    if blocks:
        uz = [b.get(7, [0.0, 0.0, math.nan])[2] for b in blocks]
        ok = len(uz) == 2 and all(abs(u / w - 1) < 1e-9 for u, w in zip(uz, (0.1, 0.2)))
        print(f"{'PASS' if ok else 'FAIL'}  unterminated_step (a cube pulled by 100 in a *STEP without "
              f"*END STEP, then by 200 with OP=NEW): top displacement {', '.join(f'{u:.7g}' for u in uz)} "
              f"vs 0.1, 0.2 (before: the first step written inside the second, where ccx stops)")
    failures += 0 if ok else 1
    # ... and its blocks passed to Converter.convert as they are (a caller that builds them
    # itself), which closes the step as read_blocks does
    src, inp = (os.path.join(tmp, f"unterminated_step_blocks{x}.inp") for x in ("_src", ""))
    with open(src, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(unterminated)
    raw = A.read_blocks(src, A.Report())
    del raw[next(k for k, b in enumerate(raw) if b.keyword == "END STEP")]     # (read_blocks')
    rep = A.Report()
    body = A.Converter(rep, type("O", (), {"solid_dof": False})()).convert(raw)
    with open(inp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(rep.header_comment_lines() + body) + "\n")
    d, status, out = run_ccx(ccx, env, inp)
    blocks = dat_node_blocks(os.path.join(d, "job.dat")) if status == "solved" else None
    shutil.rmtree(d, ignore_errors=True)
    uz = [b.get(7, [0.0, 0.0, math.nan])[2] for b in blocks or ()]
    ok = len(uz) == 2 and all(abs(u / w - 1) < 1e-9 for u, w in zip(uz, (0.1, 0.2)))
    print(f"{'PASS' if ok else 'FAIL'}  unterminated_step_blocks (the same deck's blocks, its *STEP "
          f"left open, passed to Converter.convert): top displacement "
          f"{', '.join(f'{u:.7g}' for u in uz) or status} vs 0.1, 0.2 (before: the first step "
          f"written inside the second, where ccx stops)")
    failures += 0 if ok else 1
    # --approximate's Poisson clamp beside a blank nu (that row became "E, 0.475")
    u = review_run(blank_nu_cube_deck(), "approximate_blank_nu", dat_displacements, approximate=True)
    if u:
        v = u.get(7, [math.inf] * 3)
        lateral = max(abs(v[0]), abs(v[1]))
        ok = lateral < 1e-12 and abs(v[2] / 1e-3 - 1) < 1e-9
        print(f"{'PASS' if ok else 'FAIL'}  approximate_blank_nu (--approximate; *ELASTIC nu 0.5 at "
              f"T 20 and a blank nu at T 100, a cube at 100 pulled by 190): axial strain {v[2]:.7g} "
              f"(190 / 190000), lateral {lateral:.1e} (nu 0; read as 0.475 without its temperature: "
              f"-4.75e-4)")
    failures += 0 if u and ok else 1
    # part-level *PRE-TENSION SECTION / *DISTRIBUTING COUPLING in two instances (written once
    # with the part's names, they stopped ccx); instance 2's node ids are 99 higher.  With
    # blank fields (0) in the normal and instance 2's lines (the normal stayed unturned)
    for blank in (False, True):
        tag = "assembly_bolts" + ("_blank" if blank else "")
        u = review_run(assembly_bolts_deck(blank), tag, dat_displacements)
        if u:
            closed = [u.get(n, [math.inf])[0] for n in (99, 198)]
            short = [-u.get(n, [0.0, 0.0, math.inf])[2] for n in (25, 26, 27, 28)] + \
                    [u.get(n, [0.0, math.inf])[1] for n in (124, 125, 126, 127)]
            want_c, want_s = 1000.0 * 2.0 / 210000.0, 100.0 / 210000.0
            err = max([abs(x / want_c - 1) for x in closed] + [abs(x / want_s - 1) for x in short])
            ok = err < 1e-6
            print(f"{'PASS' if ok else 'FAIL'}  {tag} (two instances, one turned 90 deg, of a part "
                  f"with a *PRE-TENSION SECTION and a *DISTRIBUTING COUPLING"
                  f"{'; the normal and instance lines with blank fields' if blank else ''}): "
                  f"pre-tension closure {closed[0]:.7g}, {closed[1]:.7g} vs F L / E A {want_c:.7g}, "
                  f"coupled block tops shortened {min(short):.7g} to {max(short):.7g} vs F / E A "
                  f"{want_s:.7g} (max {err:.1e} off)")
        failures += 0 if u and ok else 1
    # an orthotropic cube in a moved and turned instance, blank fields (0) in the instance lines,
    # the material axes and a *TRANSFORM (the flattener dropped them and left the axes unturned)
    for form in ("orientation", "distribution"):
        runs = [review_run(instance_blank_cube_deck(form, blank), f"instance_blank_{form}" +
                           ("" if blank else "_zeros"), dat_displacements) for blank in (True, False)]
        ok = all(runs)
        if ok:
            pos = [(-y, x + 5.0, z) for x, y, z in ((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0),
                                                     (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1))]
            want = {k + 1: (0.1 * gx, -0.003 * (gy - 5.0), -0.03 * gz) for k, (gx, gy, gz) in enumerate(pos)}
            err = max(abs(a - b) for nd, w in want.items()
                      for a, b in zip(runs[0].get(nd, [math.inf] * 3), w)) / 0.1
            twin = max(abs(a - b) for nd in want
                       for a, b in zip(runs[0].get(nd, [math.inf] * 3), runs[1].get(nd, [math.nan] * 3)))
            ok = err < 1e-6 and twin < 1e-12
            print(f"{'PASS' if ok else 'FAIL'}  instance_blank_{form} (orthotropic cube in an instance "
                  f"moved and turned 90 deg about z, its {form} axes, a *TRANSFORM and the instance "
                  f"lines with blank fields, pulled along x in local 2): strains 0.1, -0.003, -0.03 "
                  f"(axis 2 along x) at all 8 nodes, {err:.1e} of max |u| off, {twin:.1e} from the deck "
                  f"with zeros")
        failures += 0 if ok else 1
    runs = [review_run(instance_beam_n1_deck(blank), "instance_blank_beam_n1" + ("" if blank else "_zeros"),
                       dat_displacements) for blank in (True, False)]
    ok = all(runs)
    if ok:
        got, ref = runs[0].get(11, [math.inf] * 3), runs[1].get(11, [math.nan] * 3)
        want = 1e-3 * 10.0 ** 3 / (3.0 * 1e5 * 0.1 * 0.2 ** 3 / 12.0)
        err = abs(got[2] / want - 1)
        twin = max(abs(a - b) for a, b in zip(got, ref))
        ok = err < 1e-2 and twin < 1e-12 and abs(got[1]) < 1e-9
        print(f"{'PASS' if ok else 'FAIL'}  instance_blank_beam_n1 (B31 cantilever, RECT 0.1 x 0.2, in an "
              f"instance turned 90 deg about its axis, n1 and the rotation line with blank fields): tip "
              f"deflection {got[2]:.7g} vs F L^3 / 3 E I {want:.7g} ({err:.1e} off; n1 unturned: 4x), "
              f"{twin:.1e} from the deck with zeros")
    failures += 0 if ok else 1
    # a static step after a linear perturbation step (ccx 2.23 carried the perturbation step's
    # loads and BCs on, and dropped or zeroed the earlier ones): the first step's state again
    ref = review_run(perturbation_restore_deck(), "perturbation_restore_ref", dat_displacements)
    # (solve evidence: each cube's printed corner moves, node 27 in its free DOFs 1 and 3)
    moved = min(max(abs(x) for k, x in enumerate(ref.get(n, [0.0] * 3)) if (n, k) != (27, 1))
                for n in (7, 17, 27, 37)) if ref else 0.0
    for pert, what in (("freq", "a *FREQUENCY step changing them all"),
                       ("buckle", "a *STEP, PERTURBATION + *BUCKLE step changing them all"),
                       ("modal", "a *FREQUENCY step and a *MODAL DYNAMIC step changing the loads")):
        u = review_run(perturbation_restore_deck(pert), "perturbation_restore_" + pert, dat_displacements)
        ok = bool(u and ref)
        if ok:
            err = max(abs(a - b) for n in (7, 17, 27, 37)
                      for a, b in zip(u.get(n, [math.inf] * 3), ref.get(n, [math.nan] * 3)))
            ok = err < 1e-9 and moved > 1e-3
            print(f"{'PASS' if ok else 'FAIL'}  perturbation_restore_{pert} (four cubes given a "
                  f"*CLOAD, a pressure, a prescribed displacement and a temperature, {what}, then "
                  f"a static step giving nothing): the last step's "
                  f"displacements are the first step's ({err:.1e} apart; each cube's corner moved "
                  f"at least {moved:.3g} in a free DOF)")
        failures += 0 if ok else 1
    # a linear perturbation step after one with its own BCs (ccx 2.23 kept them on, Abaqus
    # applies the base state's), against the deck without that step
    freq_t, buck_t = "E I G E N V A L U E   O U T P U T", "B U C K L I N G   F A C T O R   O U T P U T"

    def eigen_tables(dat, title):
        """Every eigenvalue (cycles/time) or buckling factor table of a .dat file, in order."""
        return [[r[3] if len(r) == 5 else r[1] for r in rows if len(r) in (2, 5)]
                for rows in dat_tables(dat, title)]

    for case, what in (("freq_freq", "a *FREQUENCY step holding the top sideways, then a *FREQUENCY step"),
                       ("freq_buckle", "a *FREQUENCY step holding the top sideways, then a *BUCKLE step"),
                       ("buckle_freq", "a *BUCKLE step holding a top corner sideways, then a *FREQUENCY step"),
                       ("opnew_freq", "a *FREQUENCY step with OP=NEW holding fewer DOFs, then a "
                                      "*FREQUENCY step")):
        first, last = (buck_t if case == "buckle_freq" else freq_t), (buck_t if case == "freq_buckle" else freq_t)

        def read(dat, first=first, last=last):
            a, b = eigen_tables(dat, first), eigen_tables(dat, last)
            return (a[0] if a else [], b[-1]) if b else None
        runs = [review_run(pert_chain_deck(case, twin), f"pert_chain_{case}" + ("_ref" if twin else ""), read)
                for twin in (False, True)]
        ok = all(runs)
        if ok:
            got, want = runs[0][1], runs[1][1]
            err = max(abs(ccx_ratio(a, b) - 1) for a, b in zip(got, want)) if len(got) == len(want) and \
                got else math.inf
            # (solve evidence: positive values, and the first step's BC changed its own: it acted there)
            acted = abs(ccx_ratio(runs[0][0][0], got[0]) - 1) if first == last and runs[0][0] else None
            ok = err < 1e-6 and min(want) > 0.0 and (acted is None or acted > 0.01)
            print(f"{'PASS' if ok else 'FAIL'}  pert_chain_{case} (a C3D8 cube pushed down, {what}): the "
                  f"last step's {'buckling factors' if last == buck_t else 'frequencies'} "
                  f"{', '.join('%.7g' % x for x in got)} vs {', '.join('%.7g' % x for x in want)} without "
                  f"the step before ({err:.1e} apart)" +
                  (f"; that step's own {runs[0][0][0]:.7g} ({acted:.0%} off: its BCs acted there)"
                   if acted is not None else ""))
        failures += 0 if ok else 1
    # ... and a modal dynamic step reading the modes of a *FREQUENCY step after such a step, after
    # a static perturbation step (ccx stopped on its .eig file)
    runs = [review_run(pert_chain_deck("modal", twin), "pert_chain_modal" + ("_ref" if twin else ""),
                       dat_node_blocks) for twin in (False, True)]
    ok = all(runs)
    if ok:
        got, want = runs[0][-1], runs[1][-1]
        err = max(abs(a - b) for n, v in want.items() for a, b in zip(got.get(n, [math.inf] * 3), v))
        moved = max(abs(x) for v in want.values() for x in v)
        ok = len(runs[0]) == len(runs[1]) and err <= 1e-9 * moved and moved > 1e-6
        print(f"{'PASS' if ok else 'FAIL'}  pert_chain_modal (the cube: a *FREQUENCY step holding the top "
              f"sideways, a *FREQUENCY step, a static perturbation step and a *MODAL DYNAMIC step reading "
              f"the second one's modes): the modal step's last displacements {err:.1e} from the deck "
              f"without the first *FREQUENCY step (the top moves up to {moved:.3g})")
    failures += 0 if ok else 1
    # *BOUNDARY, FIXED after a *BUCKLE step (ccx 2.23 held the buckling load case's response),
    # against the deck without that step
    for case, what in (("own", "the next static step holds node 7 with *BOUNDARY, FIXED"),
                       ("given", "a static step before it holds node 7 with *BOUNDARY, FIXED after "
                                 "OP=NEW, the next one carries that on")):
        runs = [review_run(pert_fixed_deck(case, twin), f"pert_fixed_{case}" + ("_ref" if twin else ""),
                           dat_displacements) for twin in (False, True)]
        ok = all(runs)
        if ok:
            got, want = runs[0].get(7, [math.inf] * 3), runs[1].get(7, [math.nan] * 3)
            err = max(abs(a - b) for a, b in zip(got, want))
            ok = err < 1e-12 and abs(got[0] - 0.01) < 1e-12 and min(abs(got[1]), abs(got[2])) > 1e-4
            print(f"{'PASS' if ok else 'FAIL'}  pert_fixed_{case} (a C3D8 cube, node 7 held at u1 0.01, "
                  f"a *BUCKLE step loading it, then {what}): node 7 at ({', '.join('%.7g' % x for x in got)}),"
                  f" {err:.1e} from the deck without the *BUCKLE step (u1 held at 0.01; it moves in "
                  f"its free y and z)")
        failures += 0 if ok else 1
    # a *STEP, PERTURBATION *BUCKLE step after another and no general step (ccx 2.23 took the
    # first one's load case response as its base state): PERTURBATION dropped
    runs = [review_run(buckle_chain_deck(twin), "buckle_chain" + ("_ref" if twin else ""),
                       lambda dat: eigen_tables(dat, buck_t)) for twin in (False, True)]
    ok = all(runs)
    if ok:
        got, want = runs[0][-1], runs[1][-1]
        err = max(abs(ccx_ratio(a, b) - 1) for a, b in zip(got, want)) if len(got) == len(want) else math.inf
        acted = abs(ccx_ratio(runs[0][0][0], got[0]) - 1)
        ok = err < 1e-6 and min(want) > 0.0 and acted > 0.01
        print(f"{'PASS' if ok else 'FAIL'}  buckle_chain (a B32R column, no general step: a *STEP, "
              f"PERTURBATION *BUCKLE step loading its tip sideways, then one pushing it down): the last "
              f"step's buckling factors {', '.join('%.7g' % x for x in got)} vs "
              f"{', '.join('%.7g' % x for x in want)} without the first ({err:.1e} apart; the first's "
              f"{runs[0][0][0]:.7g})")
    failures += 0 if ok else 1
    # the planners' BC and moment states after a linear perturbation step: the base state again
    def same(runs, k=None):
        """The largest difference between the NODE PRINT blocks of two runs (block ``k`` only,
        or all), and the largest |u| of the second (the reference)."""
        got, ref = runs
        if k is None and len(got) != len(ref):
            return math.inf, 0.0
        pairs = [(got[k], ref[k])] if k is not None else list(zip(got, ref))
        err = max(abs(a - b) for g, r in pairs for n, v in r.items()
                  for a, b in zip(g.get(n, [math.inf] * 3), v))
        return err, max(abs(x) for _, r in pairs for v in r.values() for x in v)

    # a rotation a *FREQUENCY step holds on a transformed joint (global components: it came back
    # in the next general step, held at the frequency step's zero)
    runs = [review_run(pert_frame_deck("bc", pert), "pert_rotation_bc" + ("" if pert else "_ref"),
                       dat_node_blocks) for pert in (True, False)]
    ok = all(runs)
    if ok:
        err, moved = same(runs, -1)
        ok = err < 1e-9 * moved and moved > 1e-3
        print(f"{'PASS' if ok else 'FAIL'}  pert_rotation_bc (a B31 frame's joint with a *TRANSFORM "
              f"turned about local 1 and 3 by 0.01, held about local 3 in a *FREQUENCY step, then "
              f"turned about local 1 to 0.02): the last step's displacements are the ones without "
              f"the frequency step ({err:.1e} apart, free nodes moved {moved:.3g})")
    failures += 0 if ok else 1
    # moments on it: a perturbation step's are its own (the base moments were added to its
    # load), and the next general step's are the base state's (the buckle's came back).  The
    # solves' displacements agree to round-off; the buckling modes only as far as ccx's
    # eigensolver converges them (3.8e-9 on x86_64), like the factors, and either sign

    def mode_gap(got, ref):
        """The largest difference between two eigenmodes' printed displacements, ``got`` of
        either sign, over the largest |u| of ``ref``."""
        return ccx_ratio(min(max(abs(sg * a - b) for n, v in ref.items()
                                 for a, b in zip(got.get(n, [math.inf] * 3), v)) for sg in (1, -1)),
                         max(abs(x) for v in ref.values() for x in v))
    for pert, what in (("buckle", "*BUCKLE"), ("static", "*STEP, PERTURBATION *STATIC")):
        runs = [review_run(pert_frame_deck("moment", pert, twin), f"pert_moment_{pert}" +
                           ("_twin" if twin else ""),
                           lambda dat: (dat_eigen_table(dat, "B U C K L I N G   F A C T O R   O U T P U T"),
                                        dat_solve_mode_blocks(dat)))
                for twin in (False, True)]
        nev = 2 if pert == "buckle" else 0
        ok = all(runs) and len(runs[0][1][0]) == len(runs[1][1][0]) >= 2 and \
            len(runs[0][1][1]) == len(runs[1][1][1]) == nev
        if ok:
            err, moved = same([r[1][0] for r in runs])
            gap = max((mode_gap(g, r) for g, r in zip(runs[0][1][1], runs[1][1][1])), default=0.0)
            lam = [r[0] for r in runs]
            ok = err < 1e-9 * moved and moved > 1e-3 and gap < 1e-6 and (pert == "static" or (
                len(lam[0]) == len(lam[1]) == 2 and
                max(abs(ccx_ratio(a, b) - 1) for a, b in zip(*lam)) < 1e-6))
            print(f"{'PASS' if ok else 'FAIL'}  pert_moment_{pert} (moments about local 1 and 2 on a "
                  f"B31 frame's joint with an oblique *TRANSFORM, one about local 3 in a {what} step, "
                  f"then the first tripled): every displacement as with the moments in global "
                  f"components and no *TRANSFORM ({err:.1e} apart, free nodes moved {moved:.3g})"
                  + (f", buckling modes {gap:.1e} apart, factors {lam[0][0]:.7g} vs {lam[1][0]:.7g}"
                     if pert == "buckle" else ""))
        elif all(runs):
            print(f"FAIL  pert_moment_{pert}: {[len(b) for b in runs[0][1]]} vs {[len(b) for b in runs[1][1]]} "
                  f"displacement tables (solves, modes)")
        failures += 0 if ok else 1
    # a blank field in the *TRANSFORM line (0 for Abaqus and ccx): the axes were "unreadable",
    # so the moments stayed in local components on the ccx knot, which reads them as global
    runs = [review_run(pert_frame_deck("moment", False, twin, blank=not twin),
                       "transform_blank" + ("_twin" if twin else ""), dat_node_blocks) for twin in (False, True)]
    ok = all(runs) and len(runs[0]) == len(runs[1]) == 2
    if ok:
        err, moved = same(runs)
        ok = err < 1e-9 * moved and moved > 1e-3
        print(f"{'PASS' if ok else 'FAIL'}  transform_blank (moments about local 1 and 2 on a B31 "
              f"frame's joint, a *TRANSFORM line '0.6, 0.8, , -0.8, 0.6, 0.5'): every displacement as "
              f"with the moments in global components and no *TRANSFORM ({err:.1e} apart, free nodes "
              f"moved {moved:.3g})")
    failures += 0 if ok else 1
    # moments of two sources on one local rotation (node set TIP, then node 9 itself): Abaqus
    # adds them; ccx replaced the global DOFs with the later step's (before: local 1 at 0.02
    # in the last step, its displacements 7.3e-2 off, free nodes moved 0.27)
    text = pert_frame_deck("moment", False).replace("*CLOAD\n9, 4, 0.01\n", "*CLOAD\nTIP, 4, 0.01\n", 1)
    runs = [review_run(t, "transform_sources" + tag, dat_node_blocks) for t, tag in (
        (text.replace("*CLOAD\n9, 4, 0.03\n", "*CLOAD\n9, 4, 0.02\n"), ""),
        (pert_frame_deck("moment", False, True), "_twin"))]
    ok = all(runs) and len(runs[0]) == len(runs[1]) == 2 and "TIP, 4" in text
    if ok:
        err, moved = same(runs)
        ok = err < 1e-9 * moved and moved > 1e-3
        print(f"{'PASS' if ok else 'FAIL'}  transform_sources (moments about local 1 through node set "
              f"TIP and local 2 on a B31 frame's joint with a *TRANSFORM, then local 1 by node number): "
              f"every displacement as with the moments added up in global components and no "
              f"*TRANSFORM ({err:.1e} apart, free nodes moved {moved:.3g})")
    failures += 0 if ok else 1
    # a zero BC without AMPLITUDE in a *DYNAMIC step after a perturbation step that held the DOF
    # (it counted as at rest, so ccx stepped it), and a JOIN connector off a beam node whose
    # rotation only a *FREQUENCY step holds (its rows lost the rotation)
    for tag, decks, what in (
            ("pert_rest_ramp", (pert_rest_deck(True), pert_rest_deck(False)),
             "a cube's corner held in a *FREQUENCY step, pulled up in a static step and brought "
             "back by a zero BC in a *DYNAMIC step: its motion as without the frequency step's BC"),
            ("pert_join_rotation", (pert_join_deck("21, 4, 6"), pert_join_deck("6, 3, 3")),
             "a cube JOINed to a beam end whose rotations a *FREQUENCY step holds, then loaded: "
             "as with the frequency step holding another DOF")):
        runs = [review_run(text, tag + ("" if k == 0 else "_ref"), dat_node_blocks)
                for k, text in enumerate(decks)]
        ok = all(runs)
        if ok:
            err, moved = same(runs)
            ok = err < 1e-9 * moved and moved > 1e-3
            print(f"{'PASS' if ok else 'FAIL'}  {tag} ({what}): every displacement table "
                  f"{err:.1e} apart, nodes moved {moved:.3g}")
        failures += 0 if ok else 1
    # the steps after a linear perturbation step: NLGEOM written on it (Abaqus keeps it there;
    # the converter switched it on for the next step), a plastic material in modal / steady-state
    # dynamics (ccx 2.23 segfaulted on their element output and RF; dropped), and a TIME=TOTAL
    # TIME amplitude after a modal dynamic step (ccx counts its time: read 0.5 late)
    for tag, case, what, was in (
            ("pert_nlgeom_static", "nlgeom", "a C3D8 column sheared, a *STEP, NLGEOM, PERTURBATION "
             "*FREQUENCY step, then sheared hard: the last step as without the frequency step "
             "(linear)", "NLGEOM, a quarter of it"),
            ("plastic_modal_output", "modal", "a plastic C3D8 column below yield, *FREQUENCY and a "
             "*MODAL DYNAMIC step with Abaqus' preselected output: its motion as with an elastic "
             "material", "ccx segfaulted"),
            ("plastic_ssd_output", "ssd", "the same with a *STEADY STATE DYNAMICS step writing "
             "stresses: its response as with an elastic material", "ccx segfaulted"),
            ("modal_total_time", "total", "a C3D8 column loaded on a TIME=TOTAL TIME amplitude in two "
             "static steps around *FREQUENCY and a 0.5 *MODAL DYNAMIC step: the last step as "
             "without the perturbation steps (total time 2)", "read at 2.5")):
        runs = [review_run(after_pert_deck(case, twin), tag + ("_ref" if twin else ""), dat_node_blocks)
                for twin in (False, True)]
        ok = all(runs)
        if ok:
            err, moved = same(runs, None if case in ("modal", "ssd") else -1)
            ok = err < 1e-7 * moved and moved > (1.0 if case == "nlgeom" else 1e-5)
            print(f"{'PASS' if ok else 'FAIL'}  {tag} ({what}): {err:.1e} apart, the top moved "
                  f"{moved:.4g} (before: {was})")
        failures += 0 if ok else 1
    # a *STEP, NLGEOM=NO after an NLGEOM step: Abaqus keeps NLGEOM on ("it will be active during
    # all subsequent steps", *STEP), ccx ran the step linear (written NLGEOM since)
    runs = [review_run(nlgeom_no_deck(twin), "nlgeom_no_after_nlgeom" + ("_ref" if twin else ""),
                       dat_node_blocks) for twin in (False, True)]
    ok = all(runs)
    if ok:
        err, moved = same(runs, -1)             # (the last increment's tip)
        ok = err < 1e-7 * moved and 4.0 < moved < 6.0
        print(f"{'PASS' if ok else 'FAIL'}  nlgeom_no_after_nlgeom (a C3D8I cantilever, an NLGEOM "
              f"static step, then a *STEP, NLGEOM=NO one loading it twice as hard): the tip as with "
              f"NLGEOM in the second step, {moved:.4g} ({err:.1e} apart; before: 8.13, linear)")
    failures += 0 if ok else 1
    # an *EQUATION whose every DOF a *FREQUENCY step holds (ccx stopped: a BC on its dependent
    # DOF; before that the converter dropped it, untying the static step after)
    runs = [review_run(equation_held_deck(s), "equation_held" + ("" if s == "both" else "_" + s),
                       lambda dat: (dat_eigen_table(dat, "E I G E N V A L U E   O U T P U T"),
                                    dat_node_blocks(dat)))
            for s in ("both", "freq", "static")]
    ok = all(runs) and len(runs[0][0]) == len(runs[1][0]) == 3 and \
        len(runs[0][1]) == len(runs[2][1]) == 1
    if ok:
        f_err = max(abs(ccx_ratio(a, b) - 1) for a, b in zip(runs[0][0], runs[1][0]))
        err, moved = same([runs[0][1], runs[2][1]])
        u = runs[0][1][0]
        tie = abs(u.get(12, [0.0, math.inf])[1] - u.get(9, [0.0, math.nan])[1])
        ok = f_err < 1e-6 and err < 1e-9 * moved and tie < 1e-9 * moved and moved > 1e-4
        print(f"{'PASS' if ok else 'FAIL'}  equation_held (*EQUATION u2(12) = u2(9) on two cubes, "
              f"both DOFs held in a *FREQUENCY step, then node 12 pulled in a static step): "
              f"frequencies {runs[0][0][0]:.7g}, ... as with the BCs alone (max {f_err:.1e} "
              f"apart), the static step as without the frequency step ({err:.1e} apart, "
              f"tied DOFs {tie:.1e} apart, moved {moved:.3g})")
    elif all(runs):
        print(f"FAIL  equation_held: {len(runs[0][0])} frequencies, {len(runs[0][1])} tables")
    failures += 0 if ok else 1
    # contact output in modal / steady-state dynamics of a plastic model (ccx 2.23 segfaulted:
    # dropped), an analytic amplitude in a *MODAL DYNAMIC step (tabulated over the general
    # steps' time only), a *FREQUENCY step's own loads after NLGEOM (Abaqus ignores them; a
    # traction was dropped as reduced physics, then converted, and ccx took them off over the
    # next step: commented out), a *MODAL DYNAMIC step's increments (ccx stopped at 100) and the
    # print cards a bare one in a modal step ended in ccx (written again in the next general step)
    eig = "E I G E N V A L U E   O U T P U T"
    for tag, decks, last, what, was in (
            ("plastic_contact_modal_output", [plastic_contact_deck("modal", t) for t in (False, True)],
             False, "the plastic column with a block pressed on it, *FREQUENCY and a *MODAL DYNAMIC "
             "step into which ccx would carry the contact output: its motion as with an elastic "
             "material", "ccx segfaulted"),
            ("plastic_contact_ssd_output", [plastic_contact_deck("ssd", t) for t in (False, True)],
             False, "the same with a *STEADY STATE DYNAMICS step writing contact output: its "
             "response as with an elastic material", "ccx segfaulted"),
            ("modal_analytic_amplitude", [modal_amplitude_deck(False, t) for t in (False, True)],
             False, "the column's top loaded on sin(2 pi t), DEFINITION=PERIODIC, in a 2.0 *MODAL "
             "DYNAMIC step after *FREQUENCY: as with the curve tabulated finely", "not tabulated: "
             "ccx stopped"),
            ("modal_total_time_amplitude", [modal_amplitude_deck(True, t) for t in (False, True)],
             False, "the same on TIME=TOTAL TIME after a 0.25 static step", "1.1 of the motion apart: "
             "the table ended at 0.25"),
            ("frequency_own_loads_nlgeom", [frequency_loads_deck(t) for t in (True, False)],
             False, "the column pushed sideways under NLGEOM, a *FREQUENCY step with a traction and a "
             "*CLOAD, FOLLOWER of its own, then pulled: frequencies and every increment of the last "
             "step as without them", "the traction dropped as reduced physics; the loads converted, "
             "ccx took them off over the last step: its first increment 0.013 apart"),
            ("frequency_own_cload", [frequency_cload_deck(t) for t in (True, False)], False,
             "the column pushed sideways under NLGEOM, a *FREQUENCY step with a *CLOAD and gravity "
             "of its own, then pulled in two increments: frequencies and every increment as "
             "without them", "the first increment 0.013 apart, the top moved 0.17"),
            ("modal_increments", [modal_increments_deck(t) for t in ("", ", INC=1000")], False,
             "a *MODAL DYNAMIC step of 300 increments, no INC=: every increment as with INC=1000",
             "ccx stopped at 100 increments"),
            ("modal_bare_prints_carried", [modal_bare_prints_deck(t) for t in (False, True)], True,
             "the plastic column: an NLGEOM static step printing U and RF, *FREQUENCY, *MODAL DYNAMIC "
             "(a bare *NODE PRINT there), then a static step without print cards: its end printed "
             "as with them", "nothing printed in the last step")):
        runs = [review_run(text, tag + ("_ref" if k else ""),
                           lambda dat: (dat_node_blocks(dat), dat_eigen_table(dat, eig)))
                for k, text in enumerate(decks)]
        ok = all(runs) and all(r[0] for r in runs)
        if ok:
            err, moved = same([r[0] for r in runs], -1 if last else None)
            lam = max((abs(ccx_ratio(a, b) - 1) for a, b in zip(runs[0][1], runs[1][1])), default=math.inf)
            ok = err < 1e-6 * moved and moved > 1e-3 and lam < 1e-9 and \
                len(runs[0][1]) == len(runs[1][1]) == 4
            print(f"{'PASS' if ok else 'FAIL'}  {tag} ({what}): {err:.1e} apart, the top moved "
                  f"{moved:.4g}, frequencies {lam:.0e} apart (before: {was})")
        elif all(runs):
            print(f"FAIL  {tag}: no displacement table")
        failures += 0 if ok else 1
    # a *STATIC, RIKS step (no --approximate), a *COMPLEX FREQUENCY step and a step of an Abaqus
    # procedure ccx lacks: *NO ANALYSIS, so ccx stops there after the steps before it, without a
    # crash (an *EL FILE carried into the step crashed ccx 2.23: an empty one ends it)
    static = "*STEP\n*STATIC\n*CLOAD\n19, 2, 1.\n*NODE PRINT, NSET=TOP\nU\n*END STEP\n"
    for tag, steps, proc, second, before in (
            ("riks_stops", static + "*STEP\n*STATIC, RIKS\n0.1, 1.\n*CLOAD\n19, 2, 2.\n*END STEP\n",
             "Static", "*STATIC, RIKS", "ccx ran the Riks step as a load-controlled *STATIC"),
            ("complex_frequency_stops", "*STEP\n*FREQUENCY\n4\n*END STEP\n*STEP\n*COMPLEX FREQUENCY\n"
             "2\n*END STEP\n", "Frequency", "*COMPLEX FREQUENCY", "ccx stopped at input"),
            ("soils_stops", static + "*STEP\n*SOILS, CONSOLIDATION\n0.1, 1.\n*CLOAD\n19, 2, 2.\n"
             "*END STEP\n", "Static", "*SOILS", "ccx ran the *SOILS step as a load-controlled *STATIC"),
            ("matrix_generate_stops", "*STEP\n*FREQUENCY\n4\n*END STEP\n*STEP\n*MATRIX GENERATE, "
             "STIFFNESS\n*END STEP\n", "Frequency", "*MATRIX GENERATE",
             "ccx ran a second *FREQUENCY step")):
        src, inp = os.path.join(tmp, f"{tag}_src.inp"), os.path.join(tmp, f"{tag}.inp")
        with open(src, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(after_pert_model() + steps)
        convert(src, inp)
        d = tempfile.mkdtemp(prefix="ccxval_")
        shutil.copy(inp, os.path.join(d, "job.inp"))
        r = subprocess.run([ccx, "job"], cwd=d, env={**os.environ, **env}, capture_output=True,
                           encoding="utf-8", errors="replace", timeout=600)
        dat = os.path.join(d, "job.dat")
        blocks = dat_node_blocks(dat)            # (one: step 1's, no second static solve)
        moved = max((abs(x) for blk in blocks for v in blk.values() for x in v), default=0.0)
        freqs = dat_eigen_table(dat, eig) if os.path.exists(dat) else []
        shutil.rmtree(d, ignore_errors=True)
        ok = (r.returncode == 0 and "*ERROR" not in r.stdout and "No analysis was selected" in r.stdout
              and r.stdout.count(" analysis was selected") == 2 and
              r.stdout.count(f"{proc} analysis was selected") == 1 and
              (moved > 1e-3 and len(blocks) == 1 if proc == "Static"
               else len(freqs) == 4 and min(freqs) > 0.0))
        print(f"{'PASS' if ok else 'FAIL'}  {tag} (the column, a *{proc.upper()} step, then "
              f"{second}): ccx ran step 1 "
              f"({'the top moved ' + format(moved, '.4g') if proc == 'Static' else str(len(freqs)) + ' frequencies'})"
              f" and stopped at step 2, exit code {r.returncode} (before: {before})")
        failures += 0 if ok else 1
    # the same in a model with a plastic material (yield 1e3: elastic throughout), where ccx
    # 2.23 segfaults at a *NO ANALYSIS step: the deck ends before the step, so ccx runs step 1
    # and finishes
    for tag, second, before in (
            ("plastic_soils_ends", "*STEP\n*SOILS, CONSOLIDATION\n0.1, 1.\n*CLOAD\n19, 2, 2.\n"
             "*END STEP\n", "ccx ran the *SOILS step as a load-controlled *STATIC and stopped in "
             "it: too many cutbacks"),
            ("plastic_riks_ends", "*STEP\n*STATIC, RIKS\n0.1, 1.\n*CLOAD\n19, 2, 2.\n*END STEP\n",
             "ccx segfaulted at the *NO ANALYSIS step")):
        src, inp = os.path.join(tmp, f"{tag}_src.inp"), os.path.join(tmp, f"{tag}.inp")
        with open(src, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(after_pert_model(True) + static + second)
        convert(src, inp)
        d = tempfile.mkdtemp(prefix="ccxval_")
        shutil.copy(inp, os.path.join(d, "job.inp"))
        r = subprocess.run([ccx, "job"], cwd=d, env={**os.environ, **env}, capture_output=True,
                           encoding="utf-8", errors="replace", timeout=600)
        blocks = dat_node_blocks(os.path.join(d, "job.dat"))
        moved = max((abs(x) for blk in blocks for v in blk.values() for x in v), default=0.0)
        shutil.rmtree(d, ignore_errors=True)
        sel = [ln.strip() for ln in r.stdout.splitlines() if "analysis was selected" in ln]
        ok = r.returncode == 0 and "Job finished" in r.stdout and "*ERROR" not in r.stdout and \
            sel == ["Static analysis was selected"] and len(blocks) == 1 and moved > 1e-3
        print(f"{'PASS' if ok else 'FAIL'}  {tag} (the plastic column, a *STATIC step, then "
              f"{second.split(chr(10))[1]}): ccx ran step 1 (the top moved {moved:.4g}) and "
              f"finished, exit code {r.returncode} (before: {before})")
        failures += 0 if ok else 1
    # a *FREQUENCY step's own *NODE PRINT, which ccx carried into the next static step (Abaqus
    # ends it with the perturbation steps): that step prints the cards Abaqus carries into it
    # (step 1's RF; the twin gives them itself), or nothing (the twin's frequency step prints
    # nothing); the .frd shows it solved as the twin
    def prints(dat):
        return dat_node_blocks(dat, "forces"), dat_node_blocks(dat), frd_last(dat[:-4] + ".frd", "DISP")
    rf = "*NODE PRINT, NSET=BOT\nRF\n"
    for tag, decks, counts, what in (
            ("perturbation_prints_carried", [pert_prints_deck(), pert_prints_deck(last=rf)],
             (2, 4, 2, 4), "the base's RF printed in the static steps, the top's U in the "
             "frequency step: the last step's RF as the twin's"),
            ("perturbation_prints_ended", [pert_prints_deck(False), pert_prints_deck(False, False)],
             (0, 4, 0, 0), "the top's U printed in the frequency step only: nothing printed in "
             "the last step")):
        runs = [review_run(text, tag + ("_ref" if k else ""), prints) for k, text in enumerate(decks)]
        ok = all(runs)
        if ok:
            (f, u, top), (f0, u0, top0) = runs
            err, rfs = same([f, f0]) if f0 else (0.0, 0.0)
            moved = max((abs(x) for v in top0.values() for x in v), default=0.0)
            off = max((abs(a - b) for n, v in top0.items() for a, b in zip(top.get(n, [math.inf] * 3), v)),
                      default=math.inf)
            ok = (len(f), len(u), len(f0), len(u0)) == counts and err <= 1e-9 * rfs and \
                off < 1e-9 * moved and moved > 1e-3 and (rfs > 1e-2 or not f0)
            print(f"{'PASS' if ok else 'FAIL'}  {tag} (the column: a static step, *FREQUENCY, then "
                  f"a static step without print cards; {what}): {len(f)} RF and {len(u)} U tables "
                  f"(twin {len(f0)}, {len(u0)}), RF {err:.1e} apart, the last .frd displacements "
                  f"{off:.1e} apart (the top moved {moved:.4g}) (before: the last step printed the "
                  f"frequency step's U)")
        failures += 0 if ok else 1
    # *CONTACT PRINT CF / CFN / CFS in the *FREQUENCY, modal and steady-state dynamics steps
    # (ccx 2.23 segfaulted, any material: left out there): the static step's CFN against the
    # block's reaction, the rest as without the cards
    for case, what in (("modal", "plastic column, CFN in the static step, carried into "
                                 "*FREQUENCY, and in a *MODAL DYNAMIC step"),
                       ("ssd", "elastic column, CFN in the static and the *FREQUENCY step, CFS in "
                               "a *STEADY STATE DYNAMICS step, then pressed by 0.02")):
        tag = f"contact_forces_{case}"
        runs = [review_run(contact_force_deck(case, c), tag + ("" if c else "_ref"), lambda dat: (
            dat_node_blocks(dat), dat_eigen_table(dat, eig), dat_tables(dat, "statistics"),
            dat_history(dat, "total force", "BTOP"))) for c in (True, False)]
        n = 1 if case == "modal" else 2     # the static steps' tables (the first and the last
        # reaction totals: ccx also prints the carried RF of each eigenmode)
        ok = all(runs) and all(r[0] and len(r[3]) >= n for r in runs) and len(runs[0][2]) == n
        if ok:
            err, moved = same([r[0] for r in runs])
            lam = max((abs(ccx_ratio(a, b) - 1) for a, b in zip(runs[0][1], runs[1][1])), default=math.inf)
            rfs = runs[0][3][:1] + runs[0][3][-1:] * (n - 1)
            pairs = [(t[0][2], tot[1][0][2]) for t, tot in zip(runs[0][2], rfs)]
            cfn, rf = pairs[-1]
            f_err = max(abs(ccx_ratio(c, -r) - 1) for c, r in pairs)
            ok = err < 1e-9 * moved and moved > 1e-3 and lam < 1e-9 and f_err < 1e-6 and \
                len(runs[0][1]) == len(runs[1][1]) == 4
            print(f"{'PASS' if ok else 'FAIL'}  {tag} ({what}): total normal contact force "
                  f"{cfn:.7g} vs the block's reaction {-rf:.7g} at the end ({n} static step(s), "
                  f"{f_err:.1e} apart), the rest "
                  f"{err:.1e} apart from the run without the cards (the top moved {moved:.4g}), "
                  f"frequencies {lam:.0e} apart (before: ccx segfaulted)")
        elif all(runs):
            print(f"FAIL  {tag}: {len(runs[0][2])} contact force tables, not {n}")
        failures += 0 if ok else 1
    # a *MODAL DYNAMIC step after a loaded static step (ccx 2.23 applied that step's loads in
    # it too): the response to its own loads alone
    runs = [review_run(modal_own_loads_deck(b), "modal_own_loads" + ("" if b else "_ref"),
                       dat_node_blocks) for b in (True, False)]
    ok = all(runs) and min(len(r) for r in runs) >= 3
    if ok:
        got, want = [[blk.get(7, [math.nan] * 3) for blk in r[:3]] for r in runs]
        err = max(abs(a - b) for g, w in zip(got, want) for a, b in zip(g, w))
        moved = max(abs(x) for x in want[0])
        ok = err < 1e-12 and moved > 1e-4
        print(f"{'PASS' if ok else 'FAIL'}  modal_own_loads (a cube loaded statically by a *CLOAD, a "
              f"pressure, gravity and a traction, then *FREQUENCY and a *MODAL DYNAMIC step with a "
              f"*CLOAD and a traction of its own): its response is the one without the static "
              f"loads ({err:.1e} apart; the corner moved {moved:.3g} in the first increment)")
    elif all(runs):
        print(f"FAIL  modal_own_loads: {min(len(r) for r in runs)} increments printed, not 3")
    failures += 0 if ok else 1
    # a static perturbation step after them (ccx 2.23 applied the modal dynamic step's loads
    # in it too): its own loads, on the base state's
    for base in (False, True):
        runs = [review_run(static_pert_own_loads_deck(base, b), "static_pert_own_loads" +
                           ("_base" if base else "") + ("" if b else "_ref"), dat_node_blocks)
                for b in (True, False)]
        ok = all(runs)
        if ok:
            err, moved = same(runs, -1)
            ok = err < 1e-9 * moved and moved > 1e-3
            print(f"{'PASS' if ok else 'FAIL'}  static_pert_own_loads{'_base' if base else ''} ("
                  f"{'a cube loaded statically, then ' if base else 'a cube: '}*FREQUENCY, a *MODAL "
                  f"DYNAMIC step with a *CLOAD and a traction, and a *STEP, PERTURBATION *STATIC step "
                  f"loading another node): its displacements are the ones without the frequency and "
                  f"modal dynamic steps ({err:.1e} apart, nodes moved {moved:.3g})")
        failures += 0 if ok else 1
    # the static perturbation step's values on what the base state loads (a *CLOAD, a pressure,
    # gravity, a traction, a prescribed displacement): ccx 2.23 replaced the base values with
    # them, the converter adds them up; right after the general step, and after *FREQUENCY
    # (and a *MODAL DYNAMIC step with loads of its own), where the base state is given again
    freq = "*STEP\n*FREQUENCY\n10\n*END STEP\n"
    modal = modal_own_loads_deck(True)
    modal = modal[modal.index("*STEP\n*MODAL DYNAMIC"):].replace("*NODE PRINT, NSET=N7\nU\n", "")
    ref = review_run(static_pert_adds_deck(ref=True), "static_pert_adds_ref", dat_node_blocks)
    for tag, between in (("", ""), ("_freq", freq), ("_modal", freq + modal)):
        got = review_run(static_pert_adds_deck(between), "static_pert_adds" + tag, dat_node_blocks)
        ok = bool(got and ref)
        if ok:
            err, moved = same([got, ref], -1)
            ok = err < 1e-9 * moved and moved > 1e-3
            print(f"{'PASS' if ok else 'FAIL'}  static_pert_adds{tag} (a cube loaded statically by a "
                  f"*CLOAD, a pressure, gravity, a traction and a prescribed displacement, "
                  f"{'then ' + ('*FREQUENCY and *MODAL DYNAMIC' if 'MODAL' in between else '*FREQUENCY') + ', ' if between else ''}"
                  f"then a *STEP, PERTURBATION *STATIC step changing each of them): its displacements "
                  f"are the ones of a static step with the sums ({err:.1e} apart, nodes moved {moved:.3g})")
        failures += 0 if ok else 1
    # a static perturbation step's temperatures change the base state's (from the initial ones
    # before any general step), an amplitude counts at its value at time 0, and a zero BC on a
    # DOF the base state leaves free holds its base-state value: ccx 2.23 read the temperatures
    # as the new ones, applied the amplitude's end value and held the DOF at 0
    first = review_run(static_pert_temps_deck("first", ref=True), "static_pert_first_ref", dat_node_blocks)
    for case in ("temps", "hold"):
        held = None
        if case == "hold":
            got = review_run(static_pert_temps_deck("base", ref=True), "static_pert_hold_base", dat_node_blocks)
            held = got[-1][6][1] if got else None
        ref = review_run(static_pert_temps_deck(case, ref=held), f"static_pert_{case}_ref", dat_node_blocks) \
            if case == "temps" or held else None
        for tag, between in (("", ""), ("_freq", freq)):
            got = review_run(static_pert_temps_deck(case, between), f"static_pert_{case}{tag}", dat_node_blocks)
            ok = bool(got and ref and first)
            if ok:
                err, moved = same([got, ref], -1)
                if case == "temps":         # (and the first step, from the initial temperatures)
                    err = max(err, same([got[:1], first], -1)[0])
                ok = err < 1e-9 * moved and moved > 1e-3 and (case == "temps" or abs(held) > 1e-3)
                print(f"{'PASS' if ok else 'FAIL'}  static_pert_{case}{tag} (a heated, loaded cube, "
                      f"{'then *FREQUENCY, ' if between else ''}then a *STEP, PERTURBATION *STATIC step "
                      + ("heating it and loading it, partly on an amplitude, as one before the static "
                         "step does: their displacements are those of static steps with the base "
                         "state's (initial) temperatures and loads plus the step's, at the amplitude's "
                         "time-0 value" if case == "temps" else
                         f"holding a DOF the base state leaves free (at {held:.4g}) and loading another "
                         f"node: its displacements are those of a static step with that DOF prescribed "
                         f"at its base value") + f" ({err:.1e} apart, nodes moved {moved:.3g})")
            failures += 0 if ok else 1
    # a static perturbation step's traction (nodal forces) on what a base-state traction on an
    # amplitude loads, and its shell temperature gradients over the base state's: the converter
    # adds them to the base state's (the traction's at its amplitude's end value, without it);
    # it dropped the traction, warned, and left the gradient line unsummed
    for case in ("traction", "gradient"):
        ref = review_run(static_pert_leftovers_deck(case, ref=True), f"static_pert_{case}_ref", dat_node_blocks)
        for tag, between in (("", ""), ("_freq", freq)):
            got = review_run(static_pert_leftovers_deck(case, between), f"static_pert_{case}{tag}",
                             dat_node_blocks)
            ok = bool(got and ref)
            if ok:
                err, moved = same([got, ref], -1)
                ok = err < 1e-9 * moved and moved > 1e-3
                print(f"{'PASS' if ok else 'FAIL'}  static_pert_{case}{tag} ("
                      + ("a cube under a traction on an amplitude (0.5 at the end of its static step)"
                         if case == "traction" else "an S8 plate heated with a gradient through its "
                         "thickness") + f", {'then *FREQUENCY, ' if between else ''}then a *STEP, "
                      f"PERTURBATION *STATIC step changing " + ("the traction" if case == "traction"
                                                                 else "temperature and gradient") +
                      f"): its displacements are those of a static step with the sums ({err:.1e} "
                      f"apart, nodes moved {moved:.3g})")
            failures += 0 if ok else 1
    # a static perturbation step's lines on one key add up, its base value goes on the first one
    # (ccx 2.23 got it on each: twice the base); the base state's values on a TIME=TOTAL TIME
    # amplitude stop at the general step's end (ccx went on along it: the load doubled); a
    # *STATIC without a data line has period 1 (the next card was read as one: the later step's
    # amplitude read at 3, 1.5 times the load)
    what = {"twice": "a cube loaded statically by a *CLOAD, a pressure and gravity, {}then a *STEP, "
                     "PERTURBATION *STATIC step changing each by two lines",
            "total": "a cube loaded statically by a *CLOAD, a prescribed displacement and a traction "
                     "on a TIME=TOTAL TIME amplitude, {}then a *STEP, PERTURBATION *STATIC step loading "
                     "it (the amplitude's value at the general step's end)",
            "shift": "a cube loaded on a TIME=TOTAL TIME amplitude, {}a *STEP, PERTURBATION *STATIC "
                     "step without a data line, then a static step loading it on the amplitude (at "
                     "Abaqus' total time 2)"}
    for case in what:
        ref = review_run(static_pert_sums_deck(case, ref=True), f"static_pert_{case}_ref", dat_node_blocks)
        for tag, between in (("", ""), ("_freq", freq))[:1 if case == "shift" else 2]:
            got = review_run(static_pert_sums_deck(case, between), f"static_pert_{case}{tag}",
                             dat_node_blocks)
            ok = bool(got and ref)
            if ok:
                err, moved = same([got, ref], -1)
                ok = err < 1e-9 * moved and moved > 1e-3
                print(f"{'PASS' if ok else 'FAIL'}  static_pert_{case}{tag} ("
                      + what[case].format("then *FREQUENCY, " if between else "") + f"): its "
                      f"displacements are those of a static step with the sums ({err:.1e} apart, "
                      f"nodes moved {moved:.3g})")
            failures += 0 if ok else 1
    def factors(dat):
        return dat_eigen_table(dat, "B U C K L I N G   F A C T O R   O U T P U T")
    # a *BUCKLE step's load on an amplitude: Abaqus applies its time-0 value (the step has no
    # time period), ccx 2.23 ignores the amplitude there (the full value): the converter scales
    # the load.  The column tied at its top, pushed by 4e6 on an amplitude of 0.25 at time 0
    runs = [review_run(buckle_amplitude_deck(f, amp), "buckle_amplitude" + tag, factors)
            for f, amp, tag in ((-4e6, True, ""), (-1e6, False, "_ref"))]
    ok = all(runs)
    if ok:
        euler = math.pi ** 2 * 210e9 * 0.1 ** 4 / 12 / 2.0 ** 2
        err = abs(ccx_ratio(runs[0][0], runs[1][0]) - 1)
        ok = err < 1e-6 and abs(runs[0][0] * 1e6 / euler - 1) < 0.05
        print(f"{'PASS' if ok else 'FAIL'}  buckle_amplitude (a C3D20R column's *BUCKLE step loaded "
              f"by 4e6 on an amplitude of 0.25 at time 0): factor {runs[0][0]:.7g} vs {runs[1][0]:.7g} "
              f"loaded by 1e6 ({err:.1e} apart; Euler / 1e6 = {euler / 1e6:.4g}; ccx 2.23 as written: "
              f"the full load, about a quarter of it)")
    else:
        print("FAIL  buckle_amplitude: a run gave no results")
    failures += 0 if ok else 1
    # every load of a *BUCKLE step on an amplitude that is 0 at time 0: no buckling load, so no
    # buckling factor exists; the converter warns (it warned per card, also beside other loads),
    # and ccx 2.23 prints huge factors (noise)
    zero = review_run(buckle_amplitude_deck(-4e6, start=0.0), "buckle_amplitude_zero", factors)
    rep, _ = convert(os.path.join(tmp, "buckle_amplitude_zero_src.inp"),
                     os.path.join(tmp, "buckle_amplitude_zero_flag.inp"))
    ok = bool(zero and runs[1])
    if ok:
        warned = "no buckling factor exists" in rep.text()
        ok = warned and zero[0] > 1e6 * runs[1][0]
        print(f"{'PASS' if ok else 'FAIL'}  buckle_amplitude_zero (the column's *BUCKLE load on an "
              f"amplitude of 0 at time 0): {'warned' if warned else 'NOT warned'} that no buckling "
              f"factor exists; ccx prints {zero[0]:.3g} ({zero[0] / runs[1][0]:.2g} times the factor "
              f"under a load)")
    failures += 0 if ok else 1
    # a traction (nodal forces) on an amplitude with TIME DELAY: the generated *CLOAD keeps the
    # delay; it had the amplitude only, which ccx applied undelayed (the top at -3, not -2.5)
    runs = [review_run(delayed_traction_deck(p), "delayed_traction" + ("_pressure" if p else ""),
                       dat_node_blocks) for p in (False, True)]
    ok = all(runs) and len(runs[0]) == 2
    if ok:
        err, moved = same(runs)
        top = [b[n][2] for b in runs[0] for n in (5, 6, 7, 8)]
        ok = err < 1e-9 * moved and max(abs(w + 2.5) for w in top) < 1e-9
        print(f"{'PASS' if ok else 'FAIL'}  delayed_traction (a cube's top face under a traction on "
              f"an amplitude with TIME DELAY=0.25, a static step of period 2, then one adding "
              f"nothing): the top at {min(top):.7g} to {max(top):.7g} in both steps (-2.5, the "
              f"delayed amplitude's end value; -3 undelayed), as under that pressure ({err:.1e} apart)")
    failures += 0 if ok else 1
    # a static perturbation step's gradient over one-value base temperatures (the gradient a
    # change of 0), and the general step after one right after the initial temperatures, which
    # *TEMPERATURE, OP=NEW would leave with its gradient: the converter warned and left the
    # line unsummed, and wrote OP=NEW alone
    for case in ("one", "back"):
        runs = [review_run(gradient_base_deck(case, r), f"gradient_base_{case}" + ("_ref" if r else ""),
                           dat_node_blocks) for r in (False, True)]
        ok = all(runs)
        if ok:
            err, moved = same(runs, -1)
            ok = err < 1e-9 * moved and moved > 1e-3
            print(f"{'PASS' if ok else 'FAIL'}  gradient_base_{case} (an S8 plate, "
                  + ("heated to 50 by a one-value line, then a *STEP, PERTURBATION *STATIC step "
                     "changing temperature and gradient: its displacements are those of a static step "
                     "with the sums" if case == "one" else
                     "initial temperature 50, a *STEP, PERTURBATION *STATIC step changing temperature "
                     "and gradient, then a loaded static step: its displacements are those of that "
                     "step without the perturbation step") + f" ({err:.1e} apart, nodes moved {moved:.3g})")
        failures += 0 if ok else 1
    # ccx 2.23 reads a shell's temperature gradient on S8R and ignores it on S4 (and S4R; their
    # C3D8I / C3D8R bricks): the converter flags the S4 deck reduced physics
    got = {}
    for etype in ("S8R", "S4"):
        text, far = shell_gradient_deck(etype)
        u = review_run(text, f"shell_gradient_{etype}", dat_displacements)
        _, conv = convert(os.path.join(tmp, f"shell_gradient_{etype}_src.inp"),
                          os.path.join(tmp, f"shell_gradient_{etype}_flag.inp"))
        flagged = "temperature gradient on S4 / S4R shells (ccx ignores it)" in conv.reduced_physics
        got[etype] = (u.get(far) if u else None, flagged)
    ok = all(v[0] for v in got.values())
    if ok:
        (s8, f8), (s4, f4) = got["S8R"], got["S4"]
        ok = abs(s8[0] - 0.2) < 1e-9 and abs(s8[2] + 0.1) < 1e-9 and not f8 and \
            abs(s4[0] - 0.2) < 1e-9 and abs(s4[2]) < 1e-9 and f4
        print(f"{'PASS' if ok else 'FAIL'}  shell_gradient (a 2 x 1 plate heated by 100 with a gradient "
              f"of 100 through its thickness): corner at x {s8[0]:.7g}, z {s8[2]:.7g} on S8R (0.2, -0.1), "
              f"{'flagged' if f8 else 'not flagged'}; at x {s4[0]:.7g}, z {s4[2]:.3g} on S4 (ccx ignores "
              f"the gradient), {'flagged' if f4 else 'NOT flagged'} reduced physics")
    else:
        print("FAIL  shell_gradient: a run gave no results")
    failures += 0 if ok else 1
    # gravity before a *BUCKLE step, and a static step after a buckle under gravity: ccx 2.23
    # aborted after the step that held no body load (the converter writes a zero GRAV there)
    lam = [review_run(buckle_gravity_deck(p, pert=pert), "buckle_gravity_" + (p or "none") + tag, factors)
           for p, pert, tag in (("grav", True, ""), ("nodal", True, ""), ("", True, ""),
                                ("grav", False, "_plain"))]
    ok = all(lam)
    if ok:
        err = max(abs(ccx_ratio(lam[k][0], lam[1][0]) - 1) for k in (0, 3))
        ok = err < 1e-6 and lam[0][0] < 0.8 * lam[2][0]
        print(f"{'PASS' if ok else 'FAIL'}  buckle_gravity_preload (a C3D8 column under gravity in "
              f"a static step, then a *STEP, PERTURBATION *BUCKLE step loaded at its top, and the same "
              f"with a plain *STEP): factor {lam[0][0]:.7g} and {lam[3][0]:.7g} vs {lam[1][0]:.7g} with "
              f"the gravity as nodal forces (max {err:.1e} apart; {lam[2][0]:.7g} without it)")
    failures += 0 if ok else 1
    lam = review_run(buckle_gravity_deck("self"), "buckle_self_weight", factors)
    both = review_run(buckle_gravity_deck("self", static=True), "buckle_self_weight_static",
                      lambda dat: factors(dat) and (factors(dat), dat_displacements(dat)))
    ref = review_run(buckle_gravity_deck("", static=True, buckle=False), "buckle_self_weight_ref",
                     dat_displacements)
    ok = bool(lam and both and ref)
    if ok:
        tip = next(iter(ref))
        err = ccx_ratio(max(abs(a - b) for a, b in zip(both[1].get(tip, [math.inf] * 3), ref[tip])),
                        max(abs(x) for x in ref[tip]))
        ok = both[0][0] == lam[0] and err < 1e-9
        print(f"{'PASS' if ok else 'FAIL'}  buckle_self_weight_then_static (the column buckling "
              f"under its weight and the top load in a *STEP, PERTURBATION *BUCKLE step, then a "
              f"static step pulling its top sideways): factor {both[0][0]:.7g} ({lam[0]:.7g} "
              f"without the static step), top displacement as in a static-only run ({err:.1e} "
              f"apart)")
    failures += 0 if ok else 1
    # Abaqus' frequencies include the preload's stress stiffness only after NLGEOM; ccx 2.23's
    # only with PERTURBATION, whatever the earlier steps' NLGEOM
    f = [review_run(frequency_preload_deck(nl, pert, p), "frequency_preload_" + tag,
                    lambda dat: dat_eigen_table(dat, "E I G E N V A L U E   O U T P U T"))
         for nl, pert, p, tag in ((True, False, "grav", "nlgeom"), (True, True, "grav", "nlgeom_pert"),
                                  (False, True, "grav", "linear_pert"), (False, False, "", "none"))]
    ok = all(f)
    if ok:
        err = max(abs(ccx_ratio(f[0][0], f[1][0]) - 1), abs(ccx_ratio(f[2][0], f[3][0]) - 1))
        ok = err < 1e-9 and f[0][0] < 0.9 * f[3][0]
        print(f"{'PASS' if ok else 'FAIL'}  frequency_preload (the column under gravity in a static "
              f"step, then a *FREQUENCY step): with NLGEOM, a plain *STEP {f[0][0]:.7g} vs "
              f"{f[1][0]:.7g} written with PERTURBATION; without NLGEOM, PERTURBATION {f[2][0]:.7g} "
              f"vs {f[3][0]:.7g} unloaded (max {err:.1e} apart)")
    failures += 0 if ok else 1
    # Abaqus evaluates a *FREQUENCY step's materials at the base temperatures, ccx 2.23's plain
    # step at the initial ones: after a step that only heats, the converter writes PERTURBATION
    f = [review_run(frequency_heated_deck(h, t0), "frequency_base_temperatures_" + tag,
                    lambda dat: dat_eigen_table(dat, "E I G E N V A L U E   O U T P U T"))
         for h, t0, tag in ((True, 20.0, "heated"), (False, 120.0, "hot"), (False, 20.0, "cold"))]
    ok = all(f)
    if ok:
        err = max(abs(ccx_ratio(a, b) - 1) for a, b in zip(f[0], f[1]))
        ratio = ccx_ratio(f[1][0], f[2][0])
        ok = len(f[0]) == len(f[1]) == 4 and err < 1e-9 and abs(ratio - math.sqrt(0.5)) < 1e-6
        print(f"{'PASS' if ok else 'FAIL'}  frequency_base_temperatures (the column, its E halved from "
              f"20 to 120 degrees, heated to 120 in a static step, then a plain *FREQUENCY step): "
              f"{f[0][0]:.7g} vs {f[1][0]:.7g} at an initial 120 (4 modes, max {err:.1e} apart); "
              f"{f[2][0]:.7g} cold, ratio {ratio:.7f} (sqrt(1/2))")
    failures += 0 if ok else 1
    # ccx 2.23's plain *FREQUENCY leaves contact out altogether, PERTURBATION brings the base
    # state's contact status in, as Abaqus keeps it: the converter writes it where the base
    # state holds no stress (a first step, or after a step that loads nothing)
    f = [review_run(frequency_contact_deck(case), "frequency_base_contact_" + case,
                    lambda dat: dat_eigen_table(dat, "E I G E N V A L U E   O U T P U T"))
         for case in ("first", "after", "held", "free")]
    ok = all(f)
    if ok:
        err = max(abs(ccx_ratio(a, b) - 1) for a, b in zip(f[0], f[1]))
        ok = len(f[0]) == len(f[1]) == 4 and err < 1e-6 and 0.9 * f[2][0] < f[0][0] < f[2][0] and \
            f[0][0] > 1.4 * f[3][0]
        print(f"{'PASS' if ok else 'FAIL'}  frequency_base_contact (the column's top face resting on "
              f"a fixed plate, frictionless contact, a plain *FREQUENCY step): {f[0][0]:.7g} as the "
              f"first step, {f[1][0]:.7g} after an unloaded static step (max {err:.1e} apart); "
              f"{f[2][0]:.7g} held vertically (ccx's HARD contact is a penalty), {f[3][0]:.7g} "
              f"without the plate (ccx's plain step)")
    failures += 0 if ok else 1
    # a PERTURBATION *FREQUENCY step whose eigenmodes no modal dynamics step reads keeps the
    # NLGEOM preload's stress stiffness; the one the *MODAL DYNAMIC step reads goes without
    title = "E I G E N V A L U E   O U T P U T"
    tables = lambda dat: [[r[3] if len(r) == 5 else r[1] for r in t if len(r) in (2, 5)]  # noqa: E731
                          for t in dat_tables(dat, title)]
    both = review_run(frequency_read_deck(True), "frequency_read_by_modal",
                      lambda dat: (tables(dat), dat_displacements(dat)))
    alone = review_run(frequency_read_deck(False), "frequency_read_alone", tables)
    unloaded = review_run(frequency_preload_deck(False, False, ""), "frequency_read_unloaded", tables)
    ok = bool(both and alone and unloaded) and len(both[0]) == 2
    if ok:
        (pre, plain), tip = both[0], next(iter(both[1].values()), [0.0])
        err = max(abs(ccx_ratio(a, b) - 1) for a, b in zip(pre, alone[0]))
        err2 = max(abs(ccx_ratio(a, b) - 1) for a, b in zip(plain, unloaded[0]))
        ok = err < 1e-9 and err2 < 1e-9 and pre[0] < 0.9 * plain[0] and abs(tip[0]) > 1e-4
        print(f"{'PASS' if ok else 'FAIL'}  frequency_read_by_modal (the column under gravity with "
              f"NLGEOM, two *FREQUENCY steps, a *MODAL DYNAMIC step): the first {pre[0]:.7g} with "
              f"the prestress, as alone ({err:.1e} apart), the second, which the modal step reads, "
              f"{plain[0]:.7g} without (ccx's modal step refuses perturbation eigenmodes; "
              f"{err2:.1e} from unloaded), TIP moves {tip[0]:.4g}")
    failures += 0 if ok else 1
    # temperature-dependent hyperelastic coefficients: ccx's plain step takes the initial
    # temperatures there too, so after a step that only heats the converter writes PERTURBATION
    f = [review_run(frequency_heated_deck(h, t0, True), "frequency_base_hyperelastic_" + tag,
                    lambda dat: dat_eigen_table(dat, "E I G E N V A L U E   O U T P U T"))
         for h, t0, tag in ((True, 20.0, "heated"), (False, 120.0, "hot"), (False, 20.0, "cold"))]
    ok = all(f)
    if ok:
        err = max(abs(ccx_ratio(a, b) - 1) for a, b in zip(f[0], f[1]))
        ratio = ccx_ratio(f[2][0], f[1][0])
        ok = len(f[0]) == len(f[1]) == 4 and err < 1e-6 and ratio > 1.5
        print(f"{'PASS' if ok else 'FAIL'}  frequency_base_hyperelastic (the column, Neo-Hooke, its C10 "
              f"quartered from 20 to 120 degrees, heated to 120 in a static step, then a plain "
              f"*FREQUENCY step): {f[0][0]:.7g} vs {f[1][0]:.7g} at an initial 120 (4 modes, max "
              f"{err:.1e} apart); {f[2][0]:.7g} cold, {ratio:.4f} times")
    failures += 0 if ok else 1
    # an overclosure the static step resolves stresses the base state (Abaqus: an interference
    # fit), which ccx's PERTURBATION would add: the deck's plain step stays, without contact;
    # ADJUST moves the slave nodes onto the plate strain-free: PERTURBATION, as touching
    first_u = lambda dat: (dat_tables(dat, "displacements") or [[[0] * 4]])[0][0][1:]  # noqa: E731
    eig = lambda dat: (dat_eigen_table(dat, "E I G E N V A L U E   O U T P U T"),  # noqa: E731
                       first_u(dat))         # (the static step's: the eigensteps print modes)
    over = review_run(frequency_contact_deck("after", gap=-5e-4), "frequency_base_overclosed", eig)
    kept = review_run(frequency_contact_deck("after", gap=-5e-4, head=", PERTURBATION"),
                      "frequency_base_overclosed_pert", eig)
    adj = review_run(frequency_contact_deck("after", gap=-5e-4, pair=", ADJUST=0."),
                     "frequency_base_overclosed_adjusted", eig)
    touch, free = [review_run(frequency_contact_deck(c), "frequency_base_overclosure_" + c,
                              lambda dat: dat_eigen_table(dat, "E I G E N V A L U E   O U T P U T"))
                   for c in ("after", "free")]
    ok = bool(over and kept and adj and touch and free and over[0] and adj[0] and kept[0])
    if ok:
        uz = [r[1][2] for r in (over, adj)]
        err = max(abs(ccx_ratio(a, b) - 1) for a, b in zip(over[0], free))
        err2 = abs(ccx_ratio(adj[0][0], touch[0]) - 1)
        pre = ccx_ratio(kept[0][0], touch[0]) - 1
        ok = err < 1e-9 and err2 < 2e-3 and abs(pre) > 0.01 and uz[0] < -1e-5 and abs(uz[1]) < 1e-9
        print(f"{'PASS' if ok else 'FAIL'}  frequency_base_overclosure (the column's top 5e-4 into "
              f"the plate, an unloaded static step, a *FREQUENCY step): plain {over[0][0]:.7g} as "
              f"without the plate ({err:.1e} apart), TIP pressed down {uz[0]:.3g}; the deck's "
              f"PERTURBATION {kept[0][0]:.7g}, {pre:+.1%} from touching {touch[0]:.7g} (the "
              f"interference prestress); ADJUST=0. {adj[0][0]:.7g} ({err2:.1e} from touching), TIP "
              f"{uz[1]:.2g}")
    failures += 0 if ok else 1
    # --approximate writes PERTURBATION there (only the overclosure stresses the base): as
    # the deck's own PERTURBATION, much closer to touching than the plain step
    approx = review_run(frequency_contact_deck("after", gap=-5e-4), "frequency_base_overclosed_approx",
                        eig, approximate=True)
    ok = bool(approx and kept and touch and free and approx[0])
    if ok:
        err = max(abs(ccx_ratio(a, b) - 1) for a, b in zip(approx[0], kept[0]))
        ok = err < 1e-9 and approx[0][0] > 1.4 * free[0] and approx[1][2] < -1e-5
        print(f"{'PASS' if ok else 'FAIL'}  frequency_base_overclosure_approx (as above, "
              f"--approximate): PERTURBATION {approx[0][0]:.7g} ({err:.1e} from the deck's), "
              f"touching {touch[0]:.7g}, plain {free[0]:.7g}; TIP pressed down {approx[1][2]:.3g}")
    failures += 0 if ok else 1
    # surface-to-surface ADJUST moves the slave nodes strain-free in ccx 2.23 too: the static
    # step leaves no reaction or stress, where the same pair without ADJUST presses TIP down,
    # and PERTURBATION brings the contact in.  Not compared with touching: that formulation's
    # zero-gap frequency differs by 4 % between ccx builds, as much as the prestress moves it
    s2s = ", TYPE=SURFACE TO SURFACE"

    def static_state(dat):
        """(frequencies, (TIP's u, BASE's total reaction, the column's largest |stress|) as the
        static step printed them last), or None."""
        last = {t: rows for step, t, _, _, rows in A.dat_blocks(dat) if step == 1 and rows}
        if not all(t in last for t in ("displacements", "total force", "stresses")):
            return None
        return (dat_eigen_table(dat, "E I G E N V A L U E   O U T P U T"),
                (last["displacements"][0][1:], last["total force"][0],
                 max(abs(x) for r in last["stresses"] for x in r[2:])))
    adj_s, over_s = [review_run(frequency_contact_deck("after", gap=-5e-4, pair=s2s + p, stresses=True),
                                "frequency_base_overclosed_s2s" + tag, static_state)
                     for p, tag in ((", ADJUST=0.", "_adjusted"), ("", ""))]
    ok = bool(adj_s and over_s and free and adj_s[0] and over_s[0])
    if ok:
        (u, rf, s), (u0, rf0, s0) = adj_s[1], over_s[1]
        err = max(abs(ccx_ratio(a, b) - 1) for a, b in zip(over_s[0], free))
        left = max(ccx_ratio(max(map(abs, u)), abs(u0[2])), ccx_ratio(max(map(abs, rf)), abs(rf0[2])),
                   ccx_ratio(s, s0))
        ok = err < 1e-9 and u0[2] < -1e-5 and left < 1e-6 and adj_s[0][0] > 1.2 * free[0]
        print(f"{'PASS' if ok else 'FAIL'}  frequency_base_overclosure_s2s_adjust (as above, a "
              f"surface-to-surface pair): without ADJUST the static step presses TIP down "
              f"{u0[2]:.3g} (base reaction {rf0[2]:.4g}, stress up to {s0:.3g}), plain {over_s[0][0]:.7g} "
              f"as without the plate ({err:.1e} apart); ADJUST=0. leaves {left:.1e} of TIP's u, the "
              f"reaction and the stress, PERTURBATION {adj_s[0][0]:.7g} (free {free[0]:.7g})")
    failures += 0 if ok else 1
    # an overclosure against a shell master's face (half its thickness below its nodes, as
    # Abaqus' surface-to-surface contact counts it) or a rigid one's: the plain step, as
    # without the plate, and the static step presses TIP down (ccx resolves it too)
    res = {(m, h): review_run(frequency_contact_deck("after", gap=-5e-4, master=m, head=h,
                                                     pair=s2s if m == "shell" else ""),
                              f"frequency_base_overclosed_{m}{'_pert' if h else ''}", eig)
           for m in ("shell", "rigid") for h in ("", ", PERTURBATION")}
    ok = all(res.values()) and all(r[0] for r in res.values()) and bool(free)
    if ok:
        err = max(abs(ccx_ratio(a, b) - 1) for m in ("shell", "rigid") for a, b in zip(res[(m, "")][0], free))
        uz = [res[(m, "")][1][2] for m in ("shell", "rigid")]
        pre = [res[(m, ", PERTURBATION")][0][0] for m in ("shell", "rigid")]
        ok = err < 1e-9 and all(-5e-4 < u < -4e-4 for u in uz) and all(f > 1.4 * free[0] for f in pre)
        print(f"{'PASS' if ok else 'FAIL'}  frequency_base_overclosure_masters (the column's top 5e-4 "
              f"into an S4 plate's SNEG face 0.01 thick, surface-to-surface, or into an R3D4 "
              f"plate): plain {res[('shell', '')][0][0]:.7g} / {res[('rigid', '')][0][0]:.7g} as "
              f"without the plate ({err:.1e} apart), TIP pressed down {uz[0]:.3g} / {uz[1]:.3g}; "
              f"the deck's PERTURBATION {pre[0]:.7g} / {pre[1]:.7g}")
    failures += 0 if ok else 1
    # ccx 2.23 gives an N=1 *HYPERFOAM no stiffness (it stops, or frequencies of 0): the
    # converter writes it as N=2 with mu1 halved, which ccx solves: the column's frequencies
    # and buckling factors as with *ELASTIC at the small-strain moduli, and the cube's
    # nominal stress and lateral stretch the closed form's.  The buckle load is 0.01: from 0.3
    # to 10, ccx's foam factor scatters about a Neo-Hooke one's, by 4e-3 to 1.2e-2 by build
    hf = {(c, f): review_run(hyperfoam_deck(c, f), f"hyperfoam_{c}{'' if f else '_elastic'}",
                             lambda dat: dat_eigen_table(dat, "E I G E N V A L U E   O U T P U T"
                                                         if c == "frequency" else
                                                         "B U C K L I N G   F A C T O R   O U T P U T"))
          for c in ("frequency", "buckle") for f in (True, False)}
    cube = review_run(hyperfoam_deck("cube"), "hyperfoam_cube",
                      lambda dat: ((dat_totals(dat) or [None])[-1], dat_displacements(dat)))
    ok = all(hf.values()) and bool(cube) and bool(cube[0])
    if ok:
        err, err_b = [max(abs(ccx_ratio(a, b) - 1) for a, b in zip(hf[(c, True)], hf[(c, False)]))
                      for c in ("frequency", "buckle")]
        beta = 0.1 / 0.8
        lat = 0.8 ** (-beta / (1 + 2 * beta))
        want = 2 * 2e6 / (2 * 0.8) * (0.8 ** 2 - lat ** 2)
        side = cube[1].get(3, [0.0, 0.0])[1]
        err2 = max(abs(cube[0][0] / want - 1), abs(side / (lat - 1) - 1))
        ok = err < 1e-6 and err_b < 1e-5 and err2 < 1e-5 and len(hf[("frequency", True)]) == 4
        print(f"{'PASS' if ok else 'FAIL'}  hyperfoam_n1 (*HYPERFOAM, N=1 mu 2e6, alpha 2, nu 0.1, "
              f"written as N=2): the column's f1 {hf[('frequency', True)][0]:.7g}, buckling factor "
              f"{hf[('buckle', True)][0]:.7g} under 0.01, as with *ELASTIC E 4.4e6, nu 0.1 ({err:.1e} / "
              f"{err_b:.1e} apart); "
              f"the cube stretched to 0.8: RF {cube[0][0]:.7g} vs {want:.7g}, its free side "
              f"{side:.6g} vs {lat - 1:.6g} ({err2:.1e} apart)")
    failures += 0 if ok else 1
    # ccx 2.23 leaves contact out of *BUCKLE altogether (warned): the factors without the
    # blocks, also after a static step in which the blocks held the pushed top
    fac = lambda dat: (dat_eigen_table(dat, "B U C K L I N G   F A C T O R   O U T P U T"),  # noqa: E731
                       first_u(dat))
    b = {c: review_run(buckle_contact_deck(c), "buckle_contact_" + c, fac)
         for c in ("first", "pushed", "held", "free", "free_pushed")}
    ok = all(b.values()) and all(r[0] for r in b.values())       # (factors read)
    if ok:
        tip = {c: b[c][1] for c in ("pushed", "free_pushed")}
        err = abs(ccx_ratio(b["first"][0][0], b["free"][0][0]) - 1)
        err2 = abs(ccx_ratio(b["pushed"][0][0], b["free"][0][0]) - 1)      # (the push's prestress)
        ok = err < 1e-9 and err2 < 1e-3 and b["held"][0][0] > 2.0 * b["free"][0][0] and \
            0 < tip["pushed"][0] < 0.1 * tip["free_pushed"][0]
        print(f"{'PASS' if ok else 'FAIL'}  buckle_contact (the column with blocks touching two sides "
              f"of its top): {b['first'][0][0]:.7g} as the first step, as without the blocks "
              f"({err:.1e} apart); {b['pushed'][0][0]:.7g} after a static step pushing TIP into them "
              f"(it moves {tip['pushed'][0]:.3g}, {tip['free_pushed'][0]:.3g} without the blocks; "
              f"{err2:.1e} from unpushed); {b['held'][0][0]:.7g} with those faces held")
    failures += 0 if ok else 1

    # *BUCKLE loaded by a prescribed displacement: ccx 2.23 does not solve a *STEP, PERTURBATION
    # *BUCKLE step for it (only the prescribed nodes move: 2.389 for 40.87); the converter drops
    # PERTURBATION before any general step and gives held-on values again at 0 after one
    def buckle_state(dat):
        """(the factors, the buckle step's static DISP block: the one before its 3 modes)."""
        blocks = frd_blocks(dat[:-4] + ".frd", "DISP")
        return factors(dat) and len(blocks) >= 4 and (factors(dat), blocks[-4][1])

    reaction = review_run(buckle_displacement_deck("static"), "buckle_displacement_static",
                          lambda dat: (dat_totals(dat) or [None])[-1])
    runs = [review_run(buckle_displacement_deck(c, f), "buckle_displacement_" + c + tag, buckle_state)
            for c, f, tag in (("own", 0.0, ""), ("tied", reaction[2] if reaction else 0.0, ""),
                              ("preload", 0.0, ""),
                              ("tied_preload", reaction[2] if reaction else 0.0, ""),
                              ("tied_preload", 0.0, "_none"))]
    ok = bool(reaction) and all(runs)
    if ok:
        (own, s_own), (tied, _), (pre, s_pre), (ref, s_ref), (none, _) = runs
        euler = ccx_ratio(math.pi ** 2 * 210e9 * 0.1 ** 4 / 12 / 2.0 ** 2, -reaction[2])
        err = max(abs(ccx_ratio(own[0], tied[0]) - 1), abs(ccx_ratio(pre[0], ref[0]) - 1))
        # the buckling load's static solution: a node at mid-height moved by half the push (ccx
        # without the fix: only the top did), and the preloaded column's equals the reference's
        half = sum(1 for u in s_own.values() if abs(u[2] / -0.5e-4 - 1) < 0.01)
        scale = max(abs(u[2]) for u in s_ref.values())
        apart = ccx_ratio(max(abs(u[2] - s_ref.get(v, [math.inf] * 3)[2]) for v, u in s_pre.items()), scale)
        ok = err < 1e-5 and half >= 1 and apart < 1e-6 and abs(own[0] / euler - 1) < 0.01 and \
            0.005 < abs(ccx_ratio(pre[0], none[0]) - 1) < math.inf      # (inf: a zero factor without it)
        print(f"{'PASS' if ok else 'FAIL'}  buckle_displacement (a C3D20R column pushed down 1e-4 at "
              f"its top in a *STEP, PERTURBATION *BUCKLE step, and the same push as a static preload "
              f"before a buckling step loaded at mid-height): factor {own[0]:.7g} vs {tied[0]:.7g} "
              f"with the top tied and given the static reaction (Euler {euler:.4g}), preloaded "
              f"{pre[0]:.7g} vs {ref[0]:.7g} with that force as the preload ({none[0]:.7g} without "
              f"it): max {err:.1e} apart; {half} mid-height nodes moved half the push in the "
              f"buckling load's solution, the preloaded one {apart:.1e} off the reference's "
              f"(ccx 2.23 as written: 2.389, only the top moved)")
    else:
        print("FAIL  buckle_displacement: a run gave no results")
    failures += 0 if ok else 1
    # ... after a preload no ccx form keeps it; --approximate drops PERTURBATION on a last step
    pushed = review_run(buckle_displacement_deck("pushed"), "buckle_displacement_pushed",
                        buckle_state, approximate=True)
    ok = bool(pushed and runs[0])
    if ok:
        (lam, s_lam), (own, _) = pushed, runs[0]
        half = sum(1 for u in s_lam.values() if abs(u[2] / -0.5e-4 - 1) < 0.01)
        ok = abs(ccx_ratio(lam[0], own[0]) - 1) < 1e-6 and half >= 1
        print(f"{'PASS' if ok else 'FAIL'}  buckle_displacement_approximate (the column pushed down "
              f"in a static step and again in a *STEP, PERTURBATION *BUCKLE step, --approximate): "
              f"factor {lam[0]:.7g} vs {own[0]:.7g} pushed without the preload; {half} mid-height "
              f"nodes moved half the push (ccx 2.23 with PERTURBATION: 2.389)")
    else:
        print("FAIL  buckle_displacement_approximate: a run gave no results")
    failures += 0 if ok else 1

    # ccx 2.23's *BUCKLE shift-inverts about 1: it returns the factors nearest 1 (in 1/factor),
    # not the lowest.  buckle_gravity_deck's column at about 10 times its buckling load shows
    # the factors of its spectrum (from a run at a load well below it) nearest 1, not the
    # lowest, and the --run digest warns there
    low = review_run(buckle_gravity_deck("", pert=False, nev=12), "buckle_factors_low", factors)
    high = review_run(buckle_gravity_deck("", pert=False, load=1.5e7, nev=4), "buckle_factors_high",
                      factors)
    ok = bool(low and high) and len(high) == 4
    if ok:
        true = [x / 150. for x in low]           # the spectrum at the high load
        nearest = sorted(sorted(true, key=lambda x: abs(ccx_ratio(1, x) - 1))[:len(high)])
        err = max(abs(ccx_ratio(a, b) - 1) for a, b in zip(high, nearest))
        warned = [A.buckle_factor_warning(x) for x in (low, high)]
        ok = err < 1e-5 and min(high) > 5 * true[0] and low == sorted(low) and \
            warned[1] is not None and warned[0] is None
        print(f"{'PASS' if ok else 'FAIL'}  buckle_factors_near_one (a column at 150 times a load "
              f"with factor {low[0]:.5g}): factors {', '.join(f'{x:.5g}' for x in high)}, the "
              f"spectrum's nearest 1 ({err:.1e} apart), not its lowest {true[0]:.4g}; the digest "
              f"warns {'there' if warned[1] else 'NOT there'}, "
              f"{'not' if not warned[0] else 'also'} at the low load")
    else:
        print("FAIL  buckle_factors_near_one: a run gave no results")
    failures += 0 if ok else 1

    # ccx 2.23 expands an S4R into one C3D8R brick integrated on its mid-surface, so only the
    # hourglass stiffness ccx adds to that brick resists its bending: the deck's S4R are
    # flagged reduced physics, and --approximate writes S4, within 3 % of the plate solution in
    # each step
    def centre_w(dat):
        return [abs(u[2]) for u in dat_displacements(dat).values()]

    # (S4 where an element is at most 6 thicknesses wide, S8R through the composite upgrade
    # where it is wider: S4 locks there)
    for (step, what, read), (n, twin, kind) in itertools.product((
            ("static", "centre deflection under pressure", centre_w),
            ("freq", "lowest frequency", lambda d: dat_eigen_table(d, "E I G E N V A L U E   O U T P U T")),
            ("buckle", "buckling factor at half the buckling load", factors)),
            ((20, "S4", "plate"), (4, "S8R", "coarse_plate"))):
        tag = f"s4r_{kind}_{step}"
        text, ref = s4r_plate_deck(step, n=n)
        raw = review_run(text, tag, read)
        _, conv = convert(os.path.join(tmp, f"{tag}_src.inp"), os.path.join(tmp, f"{tag}_flag.inp"))
        app = review_run(text, tag + "_approximate", read, approximate=True)
        ok = bool(raw and app)
        if ok:
            flagged = any(r.startswith("element S4R") for r in conv.reduced_physics)
            with open(os.path.join(tmp, f"{tag}_approximate.inp"), encoding="utf-8") as fh:
                written = f"*ELEMENT, TYPE={twin}\n" in fh.read()
            err = abs(app[0] / ref - 1)
            ok = flagged and written and err < 0.03 and app[0] > 0
            print(f"{'PASS' if ok else 'FAIL'}  {tag} (a simply supported S4R plate, a/t = 100, {n} x {n}, "
                  f"its {what}): {app[0]:.5g} written as {twin if written else 'NOT ' + twin} "
                  f"(--approximate), {err:.1%} off the plate solution {ref:.5g}; as S4R "
                  f"{raw[0] / ref:.3g} times it, {'flagged' if flagged else 'NOT flagged'} reduced physics")
        failures += 0 if ok else 1

    # CPS4R / CPE4R / M3D4R / B31R are expanded into one C3D8R brick too, its hourglass stiffness
    # following the brick, not the section: flagged where that is far off (a plane element much
    # larger than its depth — a plane-strain one: than 1 in the deck's length unit —, any
    # membrane, ccx's B31R); --approximate writes the fully integrated element, within 4 % here
    def tip_v(dat):
        u = dat_displacements(dat)
        return [sum(v[1] for v in u.values()) / len(u)] if u else None

    def centre_w2(dat):
        return [abs(u[2]) for u in dat_displacements(dat).values()]

    for tag, (text, ref), twin, read, what in (
            ("one_point_cps4r", plane_cantilever_deck("CPS4R", 40, 8, 1., 0.1, 0.001), "CPS4", tip_v,
             "a CPS4R cantilever 1 x 0.1 of 40 x 8 elements, 0.001 thick, its tip deflection"),
            ("one_point_cpe4r", plane_cantilever_deck("CPE4R", 40, 8, 1000., 100.), "CPE4", tip_v,
             "a CPE4R cantilever 1000 x 100 (mm) of 40 x 8 elements, its tip deflection"),
            ("one_point_m3d4r", stretched_membrane_deck("M3D4R"), "M3D4", centre_w2,
             "a stretched M3D4R membrane, 16 x 16, a/t = 100, its centre deflection under pressure"),
            ("one_point_b31r", beam_cantilever_deck("B31R"), "B31", tip_v,
             "a B31R cantilever of 10 elements, L/a = 10, its tip deflection")):
        raw = review_run(text, tag, read)
        _, conv = convert(os.path.join(tmp, f"{tag}_src.inp"), os.path.join(tmp, f"{tag}_flag.inp"))
        app = review_run(text, tag + "_approximate", read, approximate=True)
        ok = bool(raw and app)
        if ok:
            flagged = any(r.startswith("element " + twin) for r in conv.reduced_physics)
            with open(os.path.join(tmp, f"{tag}_approximate.inp"), encoding="utf-8") as fh:
                written = f"*ELEMENT, TYPE={twin}\n" in fh.read()
            err = abs(app[0] / ref - 1)
            ok = flagged and written and err < 0.04 and app[0] > 0
            print(f"{'PASS' if ok else 'FAIL'}  {tag} ({what}): {app[0]:.5g} written as "
                  f"{twin if written else 'NOT ' + twin} (--approximate), {err:.1%} off theory "
                  f"{ref:.5g}; as written {raw[0] / ref:.3g} times it, "
                  f"{'flagged' if flagged else 'NOT flagged'} reduced physics")
        failures += 0 if ok else 1

    # numbers over the 20 characters ccx 2.23 reads of a field: it stopped on the *CLOAD
    # (-5.148903517857142e-05) and read the modulus 1.0000000000000000000e-03 as 1
    u = review_run(long_numbers_deck(), "long_numbers", dat_displacements)
    ok = bool(u)
    if ok:
        got = [v[0] for v in u.values()]
        ok = len(got) == 4 and max(abs(g / -0.2059561407142857 - 1) for g in got) < 2e-6
        print(f"{'PASS' if ok else 'FAIL'}  long_numbers (a C3D8 cube pulled by four nodal forces, "
              f"the modulus and forces written in 23 and 22 characters): the loaded face moved "
              f"{', '.join(f'{g:.7g}' for g in got)} (4 F / E = -0.2059561; ccx 2.23 as written: "
              f"'*ERROR reading *CLOAD', and E read as 1)")
    failures += 0 if ok else 1

    # parameter names without blanks (REFNODE=, POSITIONTOLERANCE=, ...): ccx rejected the
    # *COUPLING, the *TIE lost its tolerance and tied nothing, the *ELCOPY copied nothing
    u = review_run(compact_params_deck(), "compact_param_names", dat_displacements)
    ok = bool(u)
    if ok:
        top, mid = u.get(100, [math.nan] * 3)[2], u.get(6, [math.nan] * 3)[2]
        ok = abs(top / 2.05e-3 - 1) < 1e-6 and abs(mid / 1e-3 - 1) < 1e-6
        print(f"{'PASS' if ok else 'FAIL'}  compact_param_names (two C3D8 cubes, the upper an *ELCOPY "
              f"tied to the lower across a 0.05 gap, pulled through a *COUPLING; ELEMENTSHIFT=, "
              f"POSITIONTOLERANCE=, REFNODE= without blanks): the reference node rose {top:.7g} "
              f"(2.05e-3), the lower cube's top {mid:.7g} (1e-3)")
    failures += 0 if ok else 1

    # *INCLUDE expands as text: a file of data lines lost its nodes, an included *PARAMETER
    # was not applied, a file included twice was skipped as a cycle, and a nested job-relative
    # path was not found
    deck, files = include_files_deck()
    for name, text in files.items():
        os.makedirs(os.path.dirname(os.path.join(tmp, name)), exist_ok=True)
        with open(os.path.join(tmp, name), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    u = review_run(deck, "include_files", dat_displacements)
    ok = bool(u)
    if ok:
        a, b = u.get(2, [math.nan] * 3)[0], u.get(4, [math.nan] * 3)[0]
        ok = abs(a / 0.02 - 1) < 1e-6 and abs(b / 0.04 - 1) < 1e-6
        print(f"{'PASS' if ok else 'FAIL'}  include_files (two T3D2 bars, parts that *INCLUDE one "
              f"mesh file, its nodes a file of data lines included by a job-relative path, length, "
              f"area and loads *PARAMETERs from an included file): the tips moved {a:.7g} (0.02) "
              f"and {b:.7g} (0.04)")
    failures += 0 if ok else 1

    # a rotational BC on a transformed knot node in a card the step ramp splits (it was left out),
    # on a shell node ccx makes no knot as one section has OFFSET=0. and the other none (it
    # was written in global components, which ccx read in the local axes), and on an upgraded
    # beam's midside node (kept in the local axes, where ccx's MPCs clash: 21 % off), also on
    # a curved one (its ends' local values averaged in its own turned axes: 4-8 % off there)
    for tag, decks, what, *ref in (
            ("ramped_rotation_dynamic", [ramped_rotation_deck("*DYNAMIC", t) for t in (False, True)],
             "a B31 frame's joint with a *TRANSFORM turned about local 1 and 3 by BCs without "
             "AMPLITUDE in two *DYNAMIC steps"),
            ("ramped_rotation_static", [ramped_rotation_deck("*STATIC", t) for t in (False, True)],
             "the same in two *STEP, AMPLITUDE=STEP *STATIC steps"),
            ("knot_offset", [knot_offset_deck(t) for t in (False, True)],
             "two S4 plates, one section with OFFSET=0., their shared node with a *TRANSFORM "
             "turned about local 1"),
            ("midside_rotation", [midside_rotation_deck(t) for t in (False, True)],
             "a CIRC B31 cantilever's last element written as a 3-node beam, its ends with a "
             "*TRANSFORM turned about local 1 and 2, its midside node too"),
            *((f"midside_curved{'_rotation' if rot else ''}",
               [curved_midside_deck(rot, t) for t in (False, True)],
               f"a CIRC B31 quarter ring written as 3-node beams, its last element's ends with a "
               f"cylindrical *TRANSFORM {'turned about' if rot else 'moved along'} all three local "
               f"axes, its midside node too", "with an identity *TRANSFORM") for rot in (False, True))):
        runs = [review_run(text, tag + ("" if k == 0 else "_ref"), dat_node_blocks)
                for k, text in enumerate(decks)]
        ok = all(runs)
        if ok:
            err, moved = same(runs)
            ok = err < 1e-9 * moved and moved > 1e-3
            print(f"{'PASS' if ok else 'FAIL'}  {tag} ({what}): every displacement table as "
                  f"{ref[0] if ref else 'without the *TRANSFORM'}, the BCs on the global DOFs "
                  f"({err:.1e} apart, free nodes moved {moved:.3g})")
        failures += 0 if ok else 1
    # ... in a step that ramps it (its lines were stepped: its own BCs before the step were not
    # seen; free node 2 2.0e-3 off in *DYNAMIC, 12 tables for 8), and moved by velocity or
    # acceleration BCs (interpolated in its turned axes: 3.5e-4 off there, 7.7e-5 at node 2)
    for tag, decks, what in (
            *((f"ramped_midside_{step[1:].lower()}", [ramped_midside_deck(step, t) for t in (False, True)],
               f"moved along local 1-3 by BCs without AMPLITUDE in two "
               f"{'*DYNAMIC' if step == '*DYNAMIC' else '*STEP, AMPLITUDE=STEP NLGEOM *STATIC'} steps")
              for step in ("*DYNAMIC", "*STATIC")),
            *((f"midside_{typ.lower()}", [midside_velocity_deck(typ, t) for t in (False, True)],
               f"moved along local 1-3 by a *BOUNDARY, TYPE={typ} in a *DYNAMIC step")
              for typ in ("VELOCITY", "ACCELERATION"))):
        runs = [review_run(text, tag + ("_ref" if k else ""), dat_node_blocks)
                for k, text in enumerate(decks)]
        ok = all(runs)
        if ok:
            err, top = same(runs)
            free = max(abs(x) for blk in runs[1] for x in blk.get(2, [0.0]))
            ok = err < 1e-9 * top and free > 1e-3
            print(f"{'PASS' if ok else 'FAIL'}  {tag} (a straight CIRC B31 cantilever's last "
                  f"element written as a 3-node beam, its ends and midside node with a cylindrical "
                  f"*TRANSFORM, {what}): every displacement table as without the *TRANSFORM "
                  f"({err:.1e} apart, free node 2 moved {free:.3g})")
        failures += 0 if ok else 1

    # a CIRC B31 between two kinematically coupled nodes: its new midside node joins the
    # coupling (left out, it sagged 5.4 % of the beam's motion below its ends)
    for kind in ("kin", "native"):
        u = review_run(coupled_beam_deck(kind), f"coupled_beam_{kind}", dat_displacements)
        ok = bool(u)
        if ok:
            # ccx's circle: the 20-node brick through 8 points of it, area (2 + 8 (sqrt 2 - 1) / 3) r^2
            want = -7800. * 9.81 * (2. + 8. * (math.sqrt(2.) - 1.) / 3.) * 0.01 ** 2 / 1.e4
            err = max(abs(v[2] / want - 1) for v in u.values())
            ok = len(u) == 4 and err < 1e-6
            print(f"{'PASS' if ok else 'FAIL'}  coupled_beam_{kind} (a CIRC B31 written as a 3-node "
                  f"beam, both ends in a {'*KINEMATIC COUPLING' if kind == 'kin' else '*COUPLING, *KINEMATIC'} "
                  f"held by a spring, gravity): its {len(u)} nodes moved u_z = -W/k = {want:.6e} "
                  f"({err:.1e} apart)")
        failures += 0 if ok else 1

    # *SHELL SECTION, DENSITY= on continuum shells, a mass per unit area added to the
    # materials' (it was dropped: the plate weighed 0.2 / 0.3 instead of 0.7 / 0.8 per area,
    # its frequencies 1.6x too high): the reactions take 7/8 of the weight (ccx's RF leaves
    # out the load on the held nodes, the clamped column's 1/8 share), and the composite
    # plate's frequencies are those of the same plate with the mass in its materials
    for kind, rho_t in (("sc8r", 0.2), ("sc6r", 0.2), ("composite", 0.3)):
        tag = f"cshell_area_mass_{kind}"
        res = review_run(cshell_mass_deck(kind), tag, lambda dat: (dat_totals(dat), dat_displacements(dat)))
        ok = bool(res)
        if ok:
            want = 7.0 / 8.0 * (rho_t + 0.5) * 2.0
            got, tip = (res[0] or [(0.0, 0.0, 0.0)])[-1][2], res[1].get(25, [0.0] * 3)[2]
            ok = abs(got / want - 1) < 1e-6 and tip < -1e-3
            print(f"{'PASS' if ok else 'FAIL'}  {tag} ({kind} plate 2 x 1 x 0.1, material mass "
                  f"{rho_t:g} per area, section DENSITY=0.5, clamped, gravity): reactions {got:.7g} vs "
                  f"7/8 of the weight {want:.7g} ({abs(got / want - 1):.1e} apart), tip moved {tip:.4g}")
        failures += 0 if ok else 1
    freqs = [review_run(cshell_mass_deck("composite", "freq", twin), f"cshell_area_mass_freq{'_ref' if twin else ''}",
                        lambda dat: dat_eigen_table(dat, "E I G E N V A L U E   O U T P U T"))
             for twin in (False, True)]
    ok = all(f and len(f) >= 3 for f in freqs)
    if ok:
        err = max(abs(ccx_ratio(a, b) - 1) for a, b in zip(freqs[0][:3], freqs[1][:3]))
        ok = err < 1e-6
        print(f"{'PASS' if ok else 'FAIL'}  cshell_area_mass_freq (the composite plate, *FREQUENCY): "
              f"first frequencies {', '.join(f'{x:.6g}' for x in freqs[0][:3])} vs "
              f"{', '.join(f'{x:.6g}' for x in freqs[1][:3])} with the section mass in the materials "
              f"({err:.1e} apart)")
    failures += 0 if ok else 1

    # masses the converter makes in a transient coupled temperature-displacement step: the
    # material of a *BEAM GENERAL SECTION, DENSITY= and the point masses that carry a rigid
    # body's *ROTARY INERTIA, divided by 1e30 as the deck's own (they kept their inertia: the
    # loaded point lagged its static position by up to 95 %): every increment t times the end
    # displacement, as the same beam's with a *BEAM SECTION material of that density / the
    # same body's without its rotary inertia
    for kind, what, ref in (("bgs", "a BEAM GENERAL SECTION cantilever with DENSITY=, tip load",
                             "a *BEAM SECTION material of that density"),
                            ("stars", "a rigid body with *MASS and *ROTARY INERTIA, moment",
                             "no rotary inertia")):
        tag = f"coupled_made_mass_{kind}"
        runs = [review_run(coupled_made_mass_deck(kind, twin), tag + ("_ref" if twin else ""),
                           lambda dat: [v for _t, rows in dat_history(dat, "displacements", "PROBE") for v in rows])
                for twin in (False, True)]
        ok = all(r and len(r) == 10 for r in runs)
        if ok:
            end = max(abs(x) for x in runs[1][-1])
            err = ccx_ratio(max(abs(x - y) for a, b in zip(*runs) for x, y in zip(a, b)), end)
            lin = ccx_ratio(max(abs(x - (k + 1) / 10 * y) for k, a in enumerate(runs[0])
                                for x, y in zip(a, runs[0][-1])), end)
            ok = err < 1e-6 and lin < 1e-6 and end > 1e-3
            print(f"{'PASS' if ok else 'FAIL'}  {tag} (C3D8T cube heated in a transient *COUPLED "
                  f"TEMPERATURE-DISPLACEMENT step, {what} ramped over 10 increments): every increment "
                  f"as with {ref} ({err:.1e} of the end displacement {end:.4g} apart) and t times "
                  f"the end displacement ({lin:.1e})")
        failures += 0 if ok else 1

    # *SHELL SECTION, DENSITY= on conventional shells (it was dropped: the plates weighed 0.2 /
    # 0.3 instead of 0.7 / 0.8 per area, their frequencies 1.9x / 1.6x too high): the reactions take the weight but the load on the
    # clamped edge, which ccx's RF leaves out (S4: 1/8; S8R: W/24, its corners' consistent loads
    # -1/12, its midsides' 1/3), the tip moves as the twin's with the mass in its materials,
    # and the frequencies are the twin's
    for kind, rho_t, share in (("s4", 0.2, 7.0 / 8.0), ("composite", 0.3, 23.0 / 24.0)):
        tag = f"shell_area_mass_{kind}"
        read = lambda dat: (dat_totals(dat), dat_displacements(dat))     # noqa: E731
        res = [review_run(shell_mass_deck(kind, "grav", twin), tag + ("_ref" if twin else ""), read)
               for twin in (False, True)]
        ok = all(res)
        if ok:
            want = share * (rho_t + 0.5) * 2.0
            (got, tip), (_ref, tip_ref) = [((r[0] or [(0.0, 0.0, 0.0)])[-1][2], r[1].get(10, [0.0] * 3)[2])
                                          for r in res]
            ok = abs(got / want - 1) < 1e-6 and abs(ccx_ratio(tip, tip_ref) - 1) < 1e-6 and tip < -1e-4
            print(f"{'PASS' if ok else 'FAIL'}  {tag} ({kind} plate 2 x 1 x 0.1, material mass {rho_t:g} "
                  f"per area, section DENSITY=0.5, clamped, gravity): reactions {got:.7g} vs {share:.4g} of "
                  f"the weight {want:.7g} ({abs(got / want - 1):.1e} apart), tip moved {tip:.6g} as with the "
                  f"mass in the materials ({tip_ref:.6g})")
        failures += 0 if ok else 1
        freqs = [review_run(shell_mass_deck(kind, "freq", twin), f"{tag}_freq{'_ref' if twin else ''}",
                            lambda dat: dat_eigen_table(dat, "E I G E N V A L U E   O U T P U T"))
                 for twin in (False, True)]
        ok = all(f and len(f) >= 3 for f in freqs)
        if ok:
            err = max(abs(ccx_ratio(a, b) - 1) for a, b in zip(freqs[0][:3], freqs[1][:3]))
            ok = err < 1e-6 and min(freqs[0][:3]) > 0.0
            print(f"{'PASS' if ok else 'FAIL'}  {tag}_freq (the {kind} plate, *FREQUENCY): first "
                  f"frequencies {', '.join(f'{x:.6g}' for x in freqs[0][:3])} vs "
                  f"{', '.join(f'{x:.6g}' for x in freqs[1][:3])} with the section mass in the "
                  f"materials ({err:.1e} apart)")
        failures += 0 if ok else 1

    # a beam whose material neither conducts nor stores heat in a coupled temperature-
    # displacement step: ccx 2.23 gives it temperature DOFs and stopped on a singular matrix
    # (exit 255); with *CONDUCTIVITY 1e-30 and *SPECIFIC HEAT 0 every increment is the
    # conducting twin's and t times the end displacement
    for kind, what in (("transient", "a *BEAM SECTION material with *DENSITY 0"),
                       ("steady", "a *BEAM SECTION material with *DENSITY 0.02, a steady-state step"),
                       ("general", "a *BEAM GENERAL SECTION, DENSITY=0.")):
        tag = f"heatless_beam_{kind}"
        runs = [review_run(heatless_beam_deck(kind, twin), tag + ("_ref" if twin else ""),
                           lambda dat: [v for _t, rows in dat_history(dat, "displacements", "PROBE") for v in rows])
                for twin in (False, True)]
        ok = all(r and len(r) == 10 for r in runs)
        if ok:
            end = max(abs(x) for x in runs[1][-1])
            err = ccx_ratio(max(abs(x - y) for a, b in zip(*runs) for x, y in zip(a, b)), end)
            lin = ccx_ratio(max(abs(x - (k + 1) / 10 * y) for k, a in enumerate(runs[0])
                                for x, y in zip(a, runs[0][-1])), end)
            ok = err < 1e-6 and lin < 1e-6 and end > 1e-3
            print(f"{'PASS' if ok else 'FAIL'}  {tag} (C3D8T cube heated in a *COUPLED TEMPERATURE-"
                  f"DISPLACEMENT step beside a B31 cantilever of {what}, tip load ramped over 10 "
                  f"increments): solved, every increment as with a conducting beam material ({err:.1e} "
                  f"of the end displacement {end:.4g} apart) and t times the end displacement ({lin:.1e})")
        failures += 0 if ok else 1
    # a part's equation, partial kinematic couplings and SPRING1 / SPRING2 in rotated instances:
    # Abaqus turns them with the instance, so each one's displacements are R u(unturned
    # instance). They kept the part's DOF numbers: 101 % / 42 % of max |u| off.
    deck, rots = rotated_instance_dofs_deck()

    def instance_tables(dat):
        return {s: {int(r[0]): r[1:] for r in rows} for _, title, s, _, rows in A.dat_blocks(dat)
                if title.startswith("displacements")}
    tabs = review_run(deck, "rotated_instance_dofs", instance_tables)
    ok = bool(tabs)
    if ok:
        base = tabs.get("I0_BODY", {})
        scale = max((abs(x) for v in base.values() for x in v), default=0.0)
        errs = {}
        for name in ("I1", "I2"):
            got = tabs.get(f"{name}_BODY", {})
            errs[name] = max(abs(a - c) for n0, n in zip(sorted(base), sorted(got))
                             for a, c in zip(got[n], rots[name](base[n0]))) \
                if len(got) == len(base) == 16 else math.inf
        ok = scale > 1e-2 and max(errs.values()) < 1e-6 * scale
        print(f"{'PASS' if ok else 'FAIL'}  rotated_instance_dofs (a part's *EQUATION, partial kinematic "
              f"couplings and SPRING1 / SPRING2 in instances turned 90 degrees about x and 40 about "
              f"(1, 2, 3)): their 16 nodes move R u of the unturned instance's (max |u| {scale:.3g}; "
              f"{errs['I1']:.1e} / {errs['I2']:.1e} apart)")
    failures += 0 if ok else 1

    # DASHPOT1 (a node's DOF to ground, acting along a fixed direction): ccx has none, and the
    # converter dropped it as a 2-node element; now a DASHPOTA to a ground node that *EQUATIONs
    # keep on the DOF's line. A DASHPOT2's DOF line stopped ccx ('the damping coefficient may
    # depend on temperature and frequency only').
    u = review_run(dashpot1_ground_deck(), "dashpot1_ground", dat_displacements)
    ok = bool(u) and all(n in u for n in (1, 2, 3, 5))
    if ok:
        c30, s30, r = math.cos(math.radians(30)), math.sin(math.radians(30)), math.sqrt(0.5)
        along, across = 0.2 - (1.0 - math.exp(-20.0)) / 100.0, 2.0
        got = {"ORIENTATION": (_dot(u[1], (c30, s30, 0.0)), _dot(u[1], (0.0, 0.0, 1.0)), _dot(u[1], (-s30, c30, 0.0))),
               "*TRANSFORM": (_dot(u[2], (-r, r, 0.0)), _dot(u[2], (r, r, 0.0)), u[2][2]),
               "global": (u[3][2], u[3][0], u[3][1]), "DASHPOT2": (u[5][0], across, 0.0)}
        err = max(max(abs(a - along), abs(b - across), abs(z)) for a, b, z in got.values())
        ok = err < 1e-5
        print(f"{'PASS' if ok else 'FAIL'}  dashpot1_ground (DASHPOT1 along an ORIENTATION axis, a *TRANSFORM "
              f"axis and a global DOF, and a DASHPOT2, c = 10, unit masses, *DYNAMIC NLGEOM): along each "
              f"dashpot {', '.join(f'{v[0]:.6f}' for v in got.values())} (t/10 - (1 - e^-10t)/100 = "
              f"{along:.6f}), across {got['global'][1]:.6f} ({across:g}); {err:.1e} off")
    else:
        print("FAIL  dashpot1_ground: no displacements of the four masses")
    failures += 0 if ok else 1

    # DASHPOT1, SPRING1 and a GAPUNI's closure direction in rotated instances, under NLGEOM
    # (Abaqus turns them with the instance, and keeps the directions fixed in space; the
    # converter dropped DASHPOT1 and kept the gap's part direction): each turned instance's
    # node moves R u of the unturned one's at every printed increment
    def point_history(dat):
        out = {}
        for _, title, s, _, rows in A.dat_blocks(dat):
            if title.startswith("displacements") and rows:
                out.setdefault(s, []).append(rows[0][1:])
        return out
    for kind, what, want in (("dashpot", "a mass on a SPRING1 and two DASHPOT1, *DYNAMIC", (None, 0.09, 0.0475)),
                             ("gap", "SPRING1s and a GAPUNI of clearance 0.02, *STATIC", (0.01, 0.02, 0.02))):
        deck, rots = rotated_instance_point_deck(kind)
        hist = review_run(deck, f"rotated_instance_{kind}", point_history)
        base = (hist or {}).get("I0_M", [])
        ok = bool(base) and all(len(hist.get(f"{n}_M", [])) == len(base) for n in ("I1", "I2"))
        if ok:
            errs = {n: max(abs(a - b) for u0, u in zip(base, hist[f"{n}_M"]) for a, b in zip(u, rots[n](u0)))
                    for n in ("I1", "I2")}
            end = base[-1]
            # the unturned node's end: the dashpots' t/10 - (1 - e^-10t)/100 and t/20 -
            # (1 - e^-20t)/400 (5e-5 off at dt 0.005), the gap's clearance and the springs' F/k
            near = max(abs(a - w) for a, w in zip(end, want) if w is not None)
            ok = max(errs.values()) < 1e-6 * max(abs(x) for x in end) and near < 2e-4
            print(f"{'PASS' if ok else 'FAIL'}  rotated_instance_{kind} ({what}, NLGEOM, in instances turned 90 "
                  f"degrees about x and 40 about (1, 2, 3)): the node moves R u of the unturned instance's at "
                  f"each of {len(base)} increments ({errs['I1']:.1e} / {errs['I2']:.1e} apart), the unturned "
                  f"one to {', '.join(f'{x:.5f}' for x in end)} ({near:.1e} off "
                  f"{', '.join('-' if w is None else f'{w:g}' for w in want)})")
        else:
            print(f"FAIL  rotated_instance_{kind}: no displacement history of the three instances' node")
        failures += 0 if ok else 1

    # a part's *DISTRIBUTING that releases a moment and a HINGE connector without an
    # orientation, in rotated instances (Abaqus: the part's axes; the converter kept the global
    # ones: 30 % / 41 % of max |u| off)
    deck, rots = rotated_instance_constraints_deck()
    tabs = review_run(deck, "rotated_instance_constraints", instance_tables)
    ok = bool(tabs)
    if ok:
        base = tabs.get("I0_BODY", {})
        scale = max((abs(x) for v in base.values() for x in v), default=0.0)
        errs = {}
        for name in ("I1", "I2"):
            got = tabs.get(f"{name}_BODY", {})
            errs[name] = max(abs(a - c) for n0, n in zip(sorted(base), sorted(got))
                             for a, c in zip(got[n], rots[name](base[n0]))) \
                if len(got) == len(base) == 10 else math.inf
        ok = scale > 1e-3 and max(errs.values()) < 1e-6 * scale
        print(f"{'PASS' if ok else 'FAIL'}  rotated_instance_constraints (a part's *DISTRIBUTING of DOFs 1-5 "
              f"and a HINGE connector between two cubes' couplings, in instances turned 90 degrees about x "
              f"and 40 about (1, 2, 3)): their 10 nodes move R u of the unturned instance's (max |u| "
              f"{scale:.3g}; {errs['I1']:.1e} / {errs['I2']:.1e} apart)")
    failures += 0 if ok else 1

    # DASHPOT2 (DOF i of a node against DOF j of another, in fixed directions): it was a
    # DASHPOTA along the node line (1.6 off); now a DASHPOTA to a new node that *EQUATIONs move
    # with the second node's DOF j along DOF i's line
    u = review_run(dashpot2_dofs_deck(), "dashpot2_dofs", dat_displacements)
    ok = bool(u) and all(n in u for n in (1, 2, 3, 4))
    if ok:
        c30, s30, r = math.cos(math.radians(30)), math.sin(math.radians(30)), math.sqrt(0.5)
        x1, x2, across = dashpot2_dofs_answer()
        got = [_dot(u[1], (c30, s30, 0.0)), _dot(u[2], (-s30, c30, 0.0)), _dot(u[3], (-r, r, 0.0)), u[4][2]]
        side = [_dot(u[1], (-s30, c30, 0.0)), u[1][2], _dot(u[3], (r, r, 0.0)), u[3][2]]
        err = max([abs(a - b) for a, b in zip(got, (x1, x2, x1, x2))] + [abs(a - across) for a in side])
        ok = err < 1e-5
        print(f"{'PASS' if ok else 'FAIL'}  dashpot2_dofs (DASHPOT2s on DOFs 1, 2 of an ORIENTATION and on "
              f"a *TRANSFORM's DOF 2 and global DOF 3, c = 10, unit masses pushed by 1 and 0.5, *DYNAMIC "
              f"NLGEOM): along {', '.join(f'{x:.6f}' for x in got)} ({x1:.6f}, {x2:.6f} analytic), across "
              f"{side[0]:.6f} ({across:g}); {err:.1e} off")
    else:
        print("FAIL  dashpot2_dofs: no displacements of the four masses")
    failures += 0 if ok else 1

    # *MASS, TYPE=ANISOTROPIC: ccx 2.23 read its first value as an isotropic mass (frequencies
    # 36, 36, 36, 72, 72; the free mass moved 0.5 along x, y and z); now the smallest mass on the
    # node and the rest on new nodes tied along each principal axis
    freqs = review_run(anisotropic_mass_deck("freq"), "anisotropic_mass_freq",
                       lambda dat: dat_eigen_table(dat, "E I G E N V A L U E   O U T P U T"))
    u = review_run(anisotropic_mass_deck("dyn"), "anisotropic_mass_dyn", dat_displacements)
    ok = bool(freqs) and len(freqs) == 5 and bool(u) and 1 in u
    if ok:
        want = [math.sqrt(w2) / (2.0 * math.pi) for w2 in (4.0, 8.0, 9.0, 18.0, 36.0)]
        ferr = max(abs(f / w - 1.0) for f, w in zip(freqs, want))
        uw = anisotropic_mass_answer()
        uerr = max(abs(a - b) for a, b in zip(u[1], uw))
        ok = ferr < 1e-5 and uerr < 1e-6 and min(abs(x) for x in u[1]) > 0.3
        print(f"{'PASS' if ok else 'FAIL'}  anisotropic_mass (*MASS, TYPE=ANISOTROPIC 1, 4, 9 on general "
              f"ORIENTATION axes): frequencies of masses on springs 36 and 72 "
              f"{', '.join(f'{f:.6f}' for f in freqs)} (omega^2 4, 8, 9, 18, 36: {ferr:.1e} off); a free "
              f"mass under (1, 1, 1), *DYNAMIC NLGEOM, moves ({', '.join(f'{x:.6f}' for x in u[1])}) = "
              f"M^-1 F t^2 / 2 ({uerr:.1e} off)")
    else:
        print(f"FAIL  anisotropic_mass: frequencies {freqs}, displacements {u}")
    failures += 0 if ok else 1

    # SPRING1 / SPRING2 at nodes with a *TRANSFORM: Abaqus springs the local DOF, ccx 2.23 the
    # global one (0.0133 / 0.0645 where 0.01 / 0.04 is right); now on a new node tied to it
    u = review_run(spring_transform_deck(), "spring_transform", dat_displacements)
    ok = bool(u) and all(n in u for n in (1, 2, 3))
    if ok:
        c30, s30, r = math.cos(math.radians(30)), math.sin(math.radians(30)), math.sqrt(0.5)
        got = (_dot(u[1], (c30, s30, 0.0)), _dot(u[2], (-r, r, 0.0)), _dot(u[3], (0.0, -s30, c30)))
        side = max(abs(_dot(u[1], (-s30, c30, 0.0))), abs(u[1][2]), abs(_dot(u[2], (r, r, 0.0))), abs(u[2][2]))
        err = max(abs(a - b) for a, b in zip(got, (0.01, 0.04, 0.02)))
        ok = err < 1e-7 and side < 1e-8               # (the .dat's 7 digits, turned)
        print(f"{'PASS' if ok else 'FAIL'}  spring_transform (a SPRING1 and a SPRING2 on local DOFs of "
              f"nodes with *TRANSFORMs 30 / 45 degrees about z and 30 about x, *STATIC NLGEOM): along "
              f"their local axes {got[0]:.6g} (1/100), {got[1]:.6g} (0.02 + 1/50); {err:.1e} off, across "
              f"{side:.1e}")
    else:
        print("FAIL  spring_transform: no displacements")
    failures += 0 if ok else 1

    # *SPRING constants without a decimal point ('100', '1e2'; ccx 2.23 read such a line as the
    # card's DOF line and stopped: '*SPRING card without data'), and a SPRINGA's DOF line
    u = review_run(spring_numbers_deck(), "spring_numbers", dat_displacements)
    ok = bool(u) and all(n in u for n in (1, 3, 5, 6))
    if ok:
        got = (u[1][0], u[3][0], u[5][0], u[6][0])
        err = max(abs(a - b) for a, b in zip(got, (0.01, 0.01, 0.02, 0.005)))
        ok = err < 1e-9
        print(f"{'PASS' if ok else 'FAIL'}  spring_numbers (*SPRING constants '100', '1e2' after a SPRINGA "
              f"DOF line, '50', a NONLINEAR '200, 1'; unit forces): {', '.join(f'{x:.6g}' for x in got)} "
              f"(0.01, 0.01, 0.02, 0.005); {err:.1e} off")
    failures += 0 if ok else 1

    # a connector on a *DISTRIBUTING reference node: the converter did not count it as using the
    # node's rotation, so the rotation was not tied to the surface (ccx exit 255); a BEAM
    # connector's force then acts as the force and moment it puts on the node
    tabs = [review_run(connector_distributing_deck(f), "connector_distributing_" + f, dat_displacements)
            for f in ("conn", "load")]
    ok = all(tabs) and all(n in t for t in tabs for n in (9, 119, 125, 127))
    if ok:
        scale = max(abs(x) for v in tabs[1].values() for x in v)
        err = max(abs(a - b) for n in (9, 119, 125, 127) for a, b in zip(tabs[0][n], tabs[1][n]))
        ok = scale > 1e-3 and err < 1e-6 * scale
        print(f"{'PASS' if ok else 'FAIL'}  connector_distributing_ref (a BEAM connector on a *DISTRIBUTING "
              f"reference node, loaded at its far end): the cube moves as under the force and moment at the "
              f"node (max |u| {scale:.3g}; {err:.1e} apart)")
    else:
        print("FAIL  connector_distributing_ref: no displacements")
    failures += 0 if ok else 1

    # beams in a general 3-D direction: ccx 2.23 makes rotational BCs and moments on a beam node
    # mean-rotation MPCs about the global axes, exact only about the section's own axes (the
    # turned twin was 6-92 % off under the tip force, 2x under the moment, frequencies 10 % low);
    # now a *TRANSFORM along the section axes, or a knot beam where none fits: R u of the
    # unturned twin's, which bends under the moment as beam theory says (M L^2 / 2 E I)
    for typ, ne in (("B31", 4), ("B32R", 2)):
        deck, rot, tips = turned_cantilever_deck(typ, ne)
        u = review_run(deck, f"turned_cantilever_{typ}", dat_displacements)
        ok = bool(u) and all(n in u for pair in tips.values() for n in pair)
        if ok:
            errs = {c: max(abs(x - y) for x, y in zip(u[b], rot(u[a]))) / max(abs(x) for x in u[a])
                    for c, (a, b) in tips.items()}
            um, theory = u[tips["moment"][0]], (0.2 / (2e3 * 2e-4), -0.1 / (2e3 * 4.5e-4), 0.0)
            off = max(abs(x - y) for x, y in zip(um, theory)) / theory[0]
            ok = max(errs.values()) < 1e-6 and (typ != "B31" or off < 1e-4) and \
                max(abs(x) for x in u[tips["force"][0]]) > 0.1
            print(f"{'PASS' if ok else 'FAIL'}  turned_cantilever_{typ} ({ne} {typ}, RECT 0.2 x 0.3, clamped, "
                  f"turned 40 deg about (1, 2, 3)): the turned tip moves R u of the unturned one's under a tip "
                  f"force ({errs['force']:.1e} apart) and a tip moment ({errs['moment']:.1e}); under the moment "
                  f"the unturned tip moves {', '.join(f'{x:.5f}' for x in um)} (beam theory "
                  f"{', '.join(f'{x:.5f}' for x in theory)}, {off:.1e} off)")
        failures += 0 if ok else 1
    deck, rot, tips = turned_cantilever_deck("B32R", 4, "FREQUENCY")
    f = review_run(deck, "turned_cantilever_modes", lambda p: dat_eigen_table(p, "E I G E N V A L U E   O U T P U T"))
    ok = bool(f) and len(f) >= 8
    if ok:
        f = sorted(f)[:8]
        split = max(abs(f[2 * i + 1] / f[2 * i] - 1) for i in range(4))
        eb = 1.8751 ** 2 / (2 * math.pi) * math.sqrt(1e3 * 2e-4 / 0.06)       # Euler-Bernoulli f1
        ok = split < 1e-6 and abs(f[0] / eb - 1) < 0.05
        print(f"{'PASS' if ok else 'FAIL'}  turned_cantilever_modes (4 B32R, the twins in one *FREQUENCY step): "
              f"each of the first four frequencies twice, {split:.1e} apart (f1 {f[0]:.5f}, Euler-Bernoulli "
              f"{eb:.5f})")
    failures += 0 if ok else 1
    deck, rot, tips = turned_cantilever_deck("B31", 4, knot=True)
    u = review_run(deck, "turned_cantilever_knots", dat_displacements)
    a, b = tips["force+moment"]
    ok = bool(u) and a in u and b in u
    if ok:
        err = max(abs(x - y) for x, y in zip(u[b], rot(u[a]))) / max(abs(x) for x in u[a])
        ok = err < 1e-5 and max(abs(x) for x in u[a]) > 0.1
        print(f"{'PASS' if ok else 'FAIL'}  turned_cantilever_knots (4 B31 under a tip force and moment, an "
              f"*EQUATION in the deck: knot beams at the turned root and tip, the unturned ones knots by a "
              f"force-free dummy beam): the turned tip moves R u of the unturned one's ({err:.1e} apart; "
              f"max |u| {max(abs(x) for x in u[a]):.4f})")
    failures += 0 if ok else 1

    # --- indented keyword lines and abbreviations, read as Abaqus reads them: a free cube
    # heated from the initial 20 to 120 strains alpha dT = 1e-3 (the initial temperature lost,
    # it strained 1.2e-3; the indented mesh lost, nothing solved)
    nodes = "".join(f"{n + 1}, {x}., {y}., {z}.\n" for n, (x, y, z) in enumerate(
        ((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1))))
    deck = ("  *NODE, NSET=ALL\n" + nodes + "   *ELEMENT, TYPE=C3D8, ELSET=E\n1, 1,2,3,4,5,6,7,8\n"
            "*SOLID SECT, ELSET=E, MAT=M\n*MATERIAL, NAME=M\n*ELAS, TYPE=ISO\n1000., 0.3\n"
            "*EXPAN\n1.e-5\n*BOUND\n1, 1, 3\n2, 2, 3\n4, 3, 3\n"
            "  *INITIAL CONDITION, TYPE=TEMP\nALL, 20.\n*STEP\n*STATIC\n*TEMPERATURE\nALL, 120.\n"
            "*NODE PRINT, NSET=ALL, F=1\nU\n*END STEP\n")
    u = review_run(deck, "abbreviated_indented", dat_displacements)
    ok = bool(u)
    if ok:
        err = max(abs(u[n][i] - 1e-3 * x) for n, x0 in enumerate(nodes.splitlines(), 1)
                  for i, x in enumerate(float(t) for t in x0.split(",")[1:]))
        ok = err < 1e-9 and abs(u[7][0] - 1e-3) < 1e-9
        print(f"{'PASS' if ok else 'FAIL'}  abbreviated_indented (indented *NODE / *ELEMENT / "
              f"*INITIAL CONDITION, *SOLID SECT, MAT=, *ELAS, TYPE=ISO, *EXPAN, *BOUND, F=1): a free "
              f"cube heated 20 -> 120 strains alpha dT, u = 1e-3 x ({err:.1e} apart, corner u_x "
              f"{u[7][0]:.6e})")
    failures += 0 if ok else 1

    # --- self-contact under --approximate: ccx's 'S, S' with TYPE=SURFACE TO SURFACE, on a strip
    # folding shut (tip 0.25 down over a gap 0.2), against the symmetric pairs Abaqus' two-way
    # self-contact acts like (the deck's node-to-surface ones); commented out without
    # --approximate, only the strip's bending carries (base: commented out either way)
    def tip_force(dat):
        h = dat_history(dat, "total force", "TIP")
        return (h[-1][0], *h[-1][1][0]) if h and h[-1][1] else None
    runs = {tag: review_run(folding_strip_deck(mode), f"self_contact_{tag}", tip_force, approximate=ap)
            for tag, mode, ap in (("approx", "self", True), ("pairs", "sym", False),
                                  ("plain", "self", False))}
    ok = all(runs.values())
    if ok:
        got, want, plain = (runs[k] for k in ("approx", "pairs", "plain"))
        err = abs(got[2] / want[2] - 1)
        ok = all(abs(r[0] - 1.0) < 1e-9 for r in runs.values()) and err < 5e-3 and \
            abs(got[2]) > 100 * abs(plain[2]) and abs(got[3]) < 1e-2 * abs(got[2])
        print(f"{'PASS' if ok else 'FAIL'}  self_contact_approx (C-shaped C3D8I strip folding onto "
              f"itself, Abaqus' self-contact line 'S,' under --approximate): tip force {got[2]:.6g} vs "
              f"{want[2]:.6g} with symmetric node-to-surface pairs ({err:.1e} apart; out of plane "
              f"{got[3]:.2g}), {plain[2]:.3g} with it commented out (no --approximate)")
    failures += 0 if ok else 1

    # --- Abaqus 2022+ MAIN / SECONDARY read as MASTER / SLAVE: a *CLEARANCE of 0 between two
    # cubes 0.01 apart, one pushed 0.005 toward the other, closes the gap from the start (ccx
    # applies a clearance on its MASTER / SLAVE pair; base: 'parameter not recognized', ccx
    # stopped).  Closed form: the two cubes (EA/L 1000) and the contact (1e4) in series
    def clearance_run(dat):
        tot = dat_totals(dat)
        u = [r for _, _t, s, _tm, rows in A.dat_blocks(dat) if s == "LTOP" for r in rows]
        return (tot[-1], u[-4:]) if tot and len(u) >= 4 else None
    runs = {tag: review_run(clearance_deck(roles), f"clearance_{tag}", clearance_run)
            for tag, roles in (("main", ("secondary", "main")), ("master", ("slave", "master")),
                               ("none", None))}
    ok = all(runs.values())
    if ok:
        want = 0.005 / (1 / 1000. + 1 / 1000. + 1 / 1.e4)
        (f_main, u_main), (f_old, u_old), (f_none, u_none) = (runs[k] for k in ("main", "master", "none"))
        err = abs(-f_main[2] / want - 1)
        apart = max(abs(a - b) for x, y in zip(u_main, u_old) for a, b in zip(x, y)) + abs(f_main[2] - f_old[2])
        ok = err < 1e-6 and apart < 1e-12 and all(abs(r[3] + want / 1000.) < 1e-9 for r in u_main) and \
            abs(f_none[2]) < 1e-9 and all(abs(r[3]) < 1e-12 for r in u_none)
        print(f"{'PASS' if ok else 'FAIL'}  clearance_main_secondary (*CLEARANCE, SECONDARY=, MAIN=, "
              f"VALUE=0 on a surface-to-surface pair of two cubes 0.01 apart, one pushed 0.005): force "
              f"{-f_main[2]:.7g} = the series closed form {want:.7g} ({err:.1e}), the struck cube's top "
              f"{u_main[0][3]:.4g}; as SLAVE= / MASTER= ({apart:.1e} apart); without it {f_none[2]:.1e}")
    failures += 0 if ok else 1

    # --- cards ccx 2.23 stopped or crashed on as they were written (code review 2, R20) ---
    def r20_run(tag, kind):
        """The .dat path of ccx_rejects_deck(kind) converted and solved, with no reduced
        physics (the directory is removed at the end of the block), or None (FAIL printed)."""
        src, inp = os.path.join(tmp, f"{tag}_src.inp"), os.path.join(tmp, f"{tag}.inp")
        with open(src, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(ccx_rejects_deck(kind))
        _rep, conv = convert(src, inp)
        d, status, out = run_ccx(ccx, env, inp)
        r20_dirs.append(d)
        if status != "solved" or conv.reduced_physics:
            print(f"FAIL  {tag}: " + (f"did not solve ({status})" if status != "solved" else
                                      "reduced physics: " + "; ".join(conv.reduced_physics)))
            print("\n".join(l for l in out.splitlines() if "ERROR" in l)[:400])
            return None
        return os.path.join(d, "job.dat")

    r20_dirs = []
    dat = r20_run("r20_rigid_elset_tie", "rigid")
    ok = dat is not None
    if ok:
        u = dat_displacements(dat)
        want = 10. * 1.3 * 0.4 / (1000. * 0.7)          # uniaxial strain: sigma (1+nu)(1-2nu) / E (1-nu)
        err = max(abs(u[n][2] / want - 1) for n in range(5, 17))
        side = max(abs(x) for n in range(5, 17) for x in u[n][:2])
        ok = len(u) == 12 and err < 1e-6 and side < 1e-9
        print(f"{'PASS' if ok else 'FAIL'}  r20_rigid_elset_tie (*RIGID BODY, ELSET=E2, TIE NSET=TOP "
              f"on a clamped C3D8, ccx stopped: 'either NSET or ELSET'): the TOP and E2 nodes moved "
              f"u_z = {u.get(16, [0, 0, 0])[2]:.7g} vs uniaxial strain {want:.7g} ({err:.1e} apart)")
    failures += 0 if ok else 1

    dat = r20_run("r20_kinematic_dof3", "kinematic")
    ok = dat is not None
    if ok:
        steps = [b for b in dat_node_blocks(dat)]
        err = 0.0
        for f, blk in zip((1.0, 2.0), steps):
            want = {n: (-0.3e-3 * f * x, -0.3e-3 * f * y, 1e-3 * f * z) for n, (x, y, z) in
                    {1: (0, 0, 0), 2: (1, 0, 0), 3: (1, 1, 0), 4: (0, 1, 0), 5: (0, 0, 1), 6: (1, 0, 1),
                     7: (1, 1, 1), 8: (0, 1, 1)}.items()}
            err = max([err] + [abs(blk[n][i] - want[n][i]) / 1e-3 for n in want for i in range(3)])
        ok = len(steps) == 2 and err < 1e-6 and abs(steps[1][100][2] - 2e-3) < 1e-9
        print(f"{'PASS' if ok else 'FAIL'}  r20_kinematic_dof3 (*COUPLING, *KINEMATIC '3, 3' of a "
              f"C3D8 top face, ccx exited 255; then a step with *BOUNDARY, OP=NEW): uniaxial stress "
              f"u = (-nu x, -nu y, z) F / E A in both steps ({err:.1e} of F / E A off), reference "
              f"node u_z = {steps[1][100][2] if len(steps) > 1 else math.nan:.6g} in step 2")
    failures += 0 if ok else 1

    dat = r20_run("r20_visco_fixed_increments", "visco")
    ok = dat is not None
    if ok:
        frames = [(t, {int(r[0]): r[1:] for r in rows}) for _, title, _, t, rows in A.dat_blocks(dat)
                  if title.startswith("displacements")]
        err = max([abs(u[7][2] / (400. / 210000. + 1e-6 * 400. * t) - 1) for t, u in frames] or [math.inf])
        times = [round(t, 9) for t, _ in frames]
        ok = times == [round(0.1 * k, 9) for k in range(1, 11)] and err < 1e-6
        print(f"{'PASS' if ok else 'FAIL'}  r20_visco_fixed_increments (*VISCO without CETOL, creep "
              f"rate A q, ccx stopped: 'no strictly positive value for CETOL'): {len(frames)} fixed "
              f"increments of 0.1 as Abaqus takes them, u_z = sigma / E + A sigma t at each "
              f"({err:.1e} apart)")
    failures += 0 if ok else 1

    dat = r20_run("r20_surface_free_faces", "faces")
    ok = dat is not None
    if ok:
        u = dat_displacements(dat)
        eps = -10. * 0.4 / 1000.                            # hydrostatic: -p (1 - 2 nu) / E
        xyz = {1: (0, 0, 0), 2: (1, 0, 0), 3: (1, 1, 0), 4: (0, 1, 0)}
        xyz.update({n + 4 * k: (x, y, z + k) for k in (1, 2) for n, (x, y, z) in list(xyz.items())[:4]})
        err = max(abs(u[n][i] - eps * xyz[n][i]) / abs(eps) for n in xyz for i in range(3))
        ok = len(u) == 12 and err < 1e-6
        print(f"{'PASS' if ok else 'FAIL'}  r20_surface_free_faces (pressure on a *SURFACE line "
              f"without a face label on two stacked C3D8, ccx stopped on it): the exterior faces, "
              f"hydrostatic u = -p (1 - 2 nu) x / E ({err:.1e} of it off)")
    failures += 0 if ok else 1

    runs = [r20_run("r20_boundary_dofs" + t, k) for t, k in (("", "dofs"), ("_ref", "dofs_ref"))]
    ok = all(runs)
    if ok:
        got, ref = dat_displacements(runs[0]), dat_displacements(runs[1])
        err = max(abs(a - b) for n in ref for a, b in zip(got.get(n, [math.inf] * 3), ref[n]))
        moved = max(abs(x) for v in ref.values() for x in v)
        ok = len(got) == 4 and err < 1e-12 and moved > 1e-4
        print(f"{'PASS' if ok else 'FAIL'}  r20_boundary_dofs (*BOUNDARY BOT, 1, 30 on a C3D8, ccx "
              f"stopped: 'unknown DOF: 10'): as BOT, 1, 3 ({err:.1e} apart, top moved {moved:.3g})")
    failures += 0 if ok else 1

    dat = r20_run("r20_solid_composite_plies", "plies")
    ok = dat is not None
    if ok:
        u = dat_displacements(dat)
        uz = [u[n][2] for n in (5, 6, 7, 8)]                # local 2 along global z: 1 / E2
        ok = len(u) == 4 and max(abs(x / 0.1 - 1) for x in uz) < 1e-6
        print(f"{'PASS' if ok else 'FAIL'}  r20_solid_composite_plies (*SOLID SECTION, COMPOSITE of two "
              f"equal orthotropic plies on an orientation turned 90 deg about x, ccx stopped: "
              f"'nonexistent material'): u_z = {uz[0]:.7g} vs sigma / E2 = 0.1 (1 / E3 = 0.02)")
    failures += 0 if ok else 1

    for kind, what in (("ori_degenerate", "'1., 0., 0.' (no b): stresses NaN"),
                       ("ori_offset", "DEFINITION=OFFSET TO NODES: commented out, ccx stopped")):
        dat = r20_run(f"r20_{kind}", kind)
        ok = dat is not None
        if ok:
            # (ccx writes the orientation's name after each stress row)
            rows = [[float(x) for x in ln.split()[2:8]] for ln in open(dat, encoding="utf-8")
                    if re.match(r"\s+1\s+\d\s+\S+\s+\S+\s+\S+\s+\S+\s+\S+\s+\S+\s+OR1", ln)]
            s = [sum(r[k] for r in rows) / len(rows) for k in range(6)] if len(rows) == 8 else [math.nan] * 6
            uz = dat_displacements(dat).get(7, [0, 0, math.nan])[2]
            ok = abs(s[2] / 10. - 1) < 1e-6 and max(abs(x) for x in s[:2] + s[3:]) < 1e-9 and \
                abs(uz / 1e-2 - 1) < 1e-6
            print(f"{'PASS' if ok else 'FAIL'}  r20_{kind} (isotropic C3D8 on an *ORIENTATION "
                  f"{what}): written as the global axes, S33 = {s[2]:.7g} vs 10, u_z = {uz:.7g} "
                  f"vs 0.01")
        failures += 0 if ok else 1
    for d in r20_dirs:
        shutil.rmtree(d, ignore_errors=True)

    # --- task 91: cards ccx 2.23 stopped on, or solved wrong, as they were written ---
    def t91_run(tag, kind, reduced=()):
        """The .dat path of ccx_leftovers_deck(kind) converted and solved with exactly the
        ``reduced`` physics (the directory is removed at the end of the block), or None (FAIL
        printed)."""
        src, inp = os.path.join(tmp, f"{tag}_src.inp"), os.path.join(tmp, f"{tag}.inp")
        with open(src, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(ccx_leftovers_deck(kind))
        _rep, conv = convert(src, inp)
        d, status, out = run_ccx(ccx, env, inp)
        t91_dirs.append(d)
        if status != "solved" or sorted(conv.reduced_physics) != sorted(reduced):
            print(f"FAIL  {tag}: " + (f"did not solve ({status})" if status != "solved" else
                                      "reduced physics: " + "; ".join(conv.reduced_physics)))
            print("\n".join(l for l in out.splitlines() if "ERROR" in l)[:400])
            return None
        return os.path.join(d, "job.dat")

    t91_dirs = []
    # a coupling's free twist about its members' line (it solved on roundoff, 4x off; NLGEOM
    # stopped converging): held through the ROT NODE, as the rigid link's own equations
    runs = [t91_run(f"t91_kinematic_{k}", k) for k in ("twist", "twist_ref", "twist_nl")]
    ok = all(runs)
    if ok:
        got, ref, nl = (dat_displacements(r) for r in runs)
        scale = max(abs(x) for v in ref.values() for x in v)
        err = max(abs(a - b) for n in ref for a, b in zip(got.get(n, [math.inf] * 3), ref[n]))
        dnl = max(abs(a - b) for n in ref for a, b in zip(nl.get(n, [math.inf] * 3), ref[n]))
        ok = len(got) == 3 and scale > 1e-3 and err < 1e-6 * scale and dnl < 0.05 * scale
        print(f"{'PASS' if ok else 'FAIL'}  t91_kinematic_twist (*KINEMATIC '1, 3' of two nodes on a "
              f"line through the loaded reference node: its twist about the line moves no coupled "
              f"DOF): as the members' force halves and rigid-link *EQUATION ({err:.1e} apart, max |u| "
              f"{scale:.4g}); NLGEOM converges, {dnl / scale:.1%} from the linear")
    failures += 0 if ok else 1

    dat = t91_run("t91_dload_unknown_type", "dload", ["*DLOAD VP1 load dropped"])
    ok = dat is not None
    if ok:
        u = dat_displacements(dat)
        err = max(abs(u[n][2] / -1e-2 - 1) for n in (5, 6, 7, 8))   # -p / E; VP1 left out
        ok = len(u) == 4 and err < 1e-6 and abs(u[7][0] / 3e-3 - 1) < 1e-6
        print(f"{'PASS' if ok else 'FAIL'}  t91_dload_unknown_type (*DLOAD VP1 beside a P2 on a C3D8, "
              f"ccx stopped: '*ERROR reading *DLOAD'): the line left out, the pressure's u_z = "
              f"-p / E ({err:.1e} off), u_x = nu p / E")
    failures += 0 if ok else 1

    # Abaqus' axial / radial body force on axisymmetric elements (BZ ran out of the plane in
    # ccx, BR stopped it): BY / BX
    dat = t91_run("t91_dload_cax_bz", "cax_bz")
    ok = dat is not None
    if ok:
        u = dat_displacements(dat)
        top = [u[n][1] for n in (3, 4)]                    # b h^2 / (2 E), nu = 0
        ok = max(abs(x / 5e-4 - 1) for x in top) < 1e-6 and max(abs(u[n][0]) for n in u) < 1e-12
        print(f"{'PASS' if ok else 'FAIL'}  t91_dload_cax_bz (*DLOAD BZ on a CAX4 ring, bottom held "
              f"axially): the top rises b h^2 / 2E = 5e-4 ({top[0]:.7g}), no radial motion")
    failures += 0 if ok else 1
    dat = t91_run("t91_dload_cax_br", "cax_br")
    ok = dat is not None
    if ok:
        u = dat_displacements(dat)
        # nu = 0, free ring 1 <= r <= 2: u = b / E (-r^2 / 3 + 14 r / 9 + 8 / (9 r))
        err = max(abs(u[1 + i][0] / ((-r * r / 3 + 14 * r / 9 + 8 / (9 * r)) / 1000.) - 1)
                  for i, r in enumerate(1. + k / 16 for k in range(17)))
        ok = len(u) == 34 and err < 1e-3
        print(f"{'PASS' if ok else 'FAIL'}  t91_dload_cax_br (*DLOAD BR on 16 CAX4 of a free ring, "
              f"nu = 0): u_r = b / E (14 r / 9 + 8 / 9r - r^2 / 3) ({err:.1e} off, the mesh's error)")
    failures += 0 if ok else 1

    runs = [t91_run(f"t91_{k}_faceless", k) for k in ("shell", "shell_ref")]
    ok = all(runs)
    if ok:
        got, ref = (dat_displacements(r) for r in runs)
        err = max(abs(a - b) for n in ref for a, b in zip(got.get(n, [math.inf] * 3), ref[n]))
        ok = len(got) == 3 and err < 1e-9 and ref[100][2] > 0.1
        print(f"{'PASS' if ok else 'FAIL'}  t91_shell_faceless (*COUPLING on a *SURFACE line of S4 "
              f"elements without a face label, which was left out as reduced physics): as on the "
              f"node surface of their nodes ({err:.1e} apart, reference node up {ref[100][2]:.4g})")
    failures += 0 if ok else 1

    dat = t91_run("t91_surface_blank_line", "blank")
    ok = dat is not None
    if ok:
        u = dat_displacements(dat)
        eps = -10. * 0.4 / 1000.                            # hydrostatic: -p (1 - 2 nu) / E
        xyz = {n + 1 + 4 * k: (x, y, k) for k in (0, 1, 2) for n, (x, y) in enumerate(
            ((0, 0), (1, 0), (1, 1), (0, 1)))}
        err = max(abs(u[n][i] - eps * xyz[n][i]) / abs(eps) for n in xyz for i in range(3))
        ok = len(u) == 12 and err < 1e-6
        print(f"{'PASS' if ok else 'FAIL'}  t91_surface_blank_line (a pressure on a *SURFACE whose "
              f"data line is blank, Abaqus/Explicit's model exterior; two stacked C3D8): "
              f"hydrostatic u = -p (1 - 2 nu) x / E ({err:.1e} of it off)")
    failures += 0 if ok else 1

    # *SOLID SECTION, COMPOSITE of different layers (commented out: ccx stopped, 'no material
    # was assigned'): one brick per layer, the stack held on one field as Abaqus' one element
    dat = t91_run("t91_composite_shear", "comp_shear")
    ok = dat is not None
    if ok:
        u = dat_displacements(dat)
        top = [u[n][0] for n in (5, 6, 7, 8)]          # F h^2 / (sum G_k t_k A); layerwise: 0.0133
        ok = len(u) == 4 and max(abs(x / 1e-2 - 1) for x in top) < 1e-6
        print(f"{'PASS' if ok else 'FAIL'}  t91_composite_shear (two-layer composite C3D8, E 1000 / "
              f"3000, nu 0, sheared by 10 on its top): u_x = F h^2 / (G1 t1 + G2 t2) = 0.01 "
              f"({top[0]:.7g}; layers free of each other: 0.0133)")
    failures += 0 if ok else 1
    dat = t91_run("t91_composite_angles", "comp_angles")
    ok = dat is not None
    if ok:
        u = dat_displacements(dat)
        ux = [u[n][0] for n in (2, 3, 6, 7)]
        ok = len(u) == 4 and max(abs(x / 1e-2 - 1) for x in ux) < 1e-6
        print(f"{'PASS' if ok else 'FAIL'}  t91_composite_angles (a 0 / 90 degree composite C3D8 of "
              f"one orthotropic material, E1 100, E2 10, the single brick's forces of u = 0.01 x on "
              f"its face x = 1): u_x = 0.01 there ({max(abs(x / 1e-2 - 1) for x in ux):.1e} off)")
    failures += 0 if ok else 1
    for d in t91_dirs:
        shutil.rmtree(d, ignore_errors=True)

    # --- task 95: task 91's follow-ups ---
    def t95_run(tag, kind, reduced=()):
        """The .dat path of ccx_leftovers2_deck(kind) converted and solved with exactly the
        ``reduced`` physics, or None (FAIL printed)."""
        src, inp = os.path.join(tmp, f"{tag}_src.inp"), os.path.join(tmp, f"{tag}.inp")
        with open(src, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(ccx_leftovers2_deck(kind))
        _rep, conv = convert(src, inp)
        d, status, out = run_ccx(ccx, env, inp)
        t95_dirs.append(d)
        if status != "solved" or sorted(conv.reduced_physics) != sorted(reduced):
            print(f"FAIL  {tag}: " + (f"did not solve ({status})" if status != "solved" else
                                      "reduced physics: " + "; ".join(conv.reduced_physics)))
            print("\n".join(l for l in out.splitlines() if "ERROR" in l)[:400])
            return None
        return os.path.join(d, "job.dat")

    def t95_apart(got, ref):
        """(largest difference, largest |u|) of two {node: u} over ref's nodes."""
        scale = max(abs(x) for v in ref.values() for x in v)
        return max(abs(a - b) for n in ref for a, b in zip(got.get(n, [math.inf] * 3), ref[n])), scale

    t95_dirs = []
    # *CLOAD / *EQUATION on DOF 9, which no element of the model has (ccx stopped: 'nonexistent
    # degree of freedom', '*ERROR reading *EQUATION'): left out
    dat = t95_run("t95_dof79", "dof79")
    ok = dat is not None
    if ok:
        u = dat_displacements(dat)
        err = max(abs(u[n][2] / -1e-2 - 1) for n in (5, 6, 7, 8))
        ok = len(u) == 4 and err < 1e-6
        print(f"{'PASS' if ok else 'FAIL'}  t95_dof79 (*CLOAD and *EQUATION on DOF 9 of a pressed C3D8 "
              f"cube, ccx stopped on both): left out, u_z = -p / E ({err:.1e} off)")
    failures += 0 if ok else 1
    # the off-axis free twist where task 91 only warned (or nothing): held on the ROT NODE that
    # carries the reference node's rotation in each form
    for kind, ref, what in (("twist_dyn", "twist_dyn_ref", "in a *DYNAMIC step (ccx: 'too many cutbacks')"),
                            ("twist_tr", "twist_tr_ref", "with a *TRANSFORM on the reference node and a moment "
                                                         "normal to the twist (ccx solved it 1e12 off, silently)"),
                            ("twist_kc", "twist_ref", "on a *KINEMATIC COUPLING card (ccx: 0.79 off)"),
                            ("twist_shell_dyn", "twist_shell_dyn_ref", "of S4 plate nodes in a *DYNAMIC step "
                                                                       "(ccx exited 255)")):
        runs = [t95_run(f"t95_{kind}", kind), t95_run(f"t95_{ref}", ref)]
        ok = all(runs)
        if ok:
            got, want = (dat_displacements(r) for r in runs)
            err, scale = t95_apart(got, want)
            ok = len(got) == 3 and scale > 1e-4 and err < 1e-6 * scale
            print(f"{'PASS' if ok else 'FAIL'}  t95_{kind} (a coupling's free twist about its members' "
                  f"line {what}): as the members' force halves and rigid-link *EQUATION ({err:.1e} "
                  f"apart, max |u| {scale:.4g})")
        failures += 0 if ok else 1
    # composite solids task 91 left commented out (ccx: 'no material was assigned')
    runs = [t95_run("t95_comp20_split", "comp20_split",
                    ["*SOLID SECTION, COMPOSITE: the layer integration of its ply bricks"]),
            t95_run("t95_comp20_plain", "comp20_plain")]
    ok = all(runs)
    if ok:
        got, want = (dat_displacements(r) for r in runs)
        err, scale = t95_apart(got, want)
        ok = len(got) >= 20 and scale > 1e-3 and err < 1e-9 * scale
        print(f"{'PASS' if ok else 'FAIL'}  t95_composite_c3d20_equal (a C3D20 of two layers of equal "
              f"properties, 0.3 / 0.7, split into ply C3D20 tied to the element's field): as the plain "
              f"C3D20 ({err:.1e} apart, max |u| {scale:.4g})")
    failures += 0 if ok else 1
    for kind, flag, want, what in (
            ("comp_ten_c3d20r", "the layer integration of its ply bricks", 10. / 2000., "C3D20R, E 1000 / 3000"),
            ("comp_ten_c3d8i", "the incompatible modes of its ply C3D8I bricks", 10. / 2000., "C3D8I, E 1000 / 3000"),
            ("comp_dist_ori", None, 10. / 110., "two C3D8, layer axes from a *DISTRIBUTION per element"),
            ("comp_dist_angle", None, 10. / 83., "two C3D8, a layer's angle from a *DISTRIBUTION per element")):
        dat = t95_run(f"t95_{kind}", kind, [f"*SOLID SECTION, COMPOSITE: {flag}"] if flag else [])
        ok = dat is not None
        if ok:
            ux = dat_displacements(dat)[2][0]
            ok = abs(ux / want - 1) < 1e-6
            print(f"{'PASS' if ok else 'FAIL'}  t95_{kind} (composite {what}, pulled along x, face x = 1 "
                  f"kept plane): u = F / sum(E_x A) = {want:.7g} ({ux:.7g})")
        failures += 0 if ok else 1
    # *DLOAD HP (ccx stopped: '*ERROR reading *DLOAD') -> consistent nodal forces: a body of the
    # fluid's density, submerged, is in sigma = -p I, p = gamma (za - z): u quadratic, exact
    c3, za = 0.5 * 20. / 1000., 3.
    for kind, what in (("hp_block", "2 x 2 x 2 C3D20 block"), ("hp_cpe8", "2 x 2 CPE8 square"),
                       ("hp_cax8", "2 x 2 CAX8 ring 1 <= r <= 2")):
        dat = t95_run(f"t95_{kind}", kind)
        ok = dat is not None
        if ok:
            u = dat_displacements(dat)
            xyz = {}
            for ln in ccx_leftovers2_deck(kind).split("*Element")[0].splitlines()[1:]:
                f = [float(x) for x in ln.split(",")]
                xyz[int(f[0])] = f[1:] + [0.] * (4 - len(f))
            if kind == "hp_block":
                want = {n: (c3 * (z - za) * x, c3 * (z - za) * y, c3 * (z * z / 2 - za * z - (x * x + y * y) / 2))
                        for n, (x, y, z) in xyz.items()}
            elif kind == "hp_cpe8":                  # plane strain: (1 + nu)(1 - 2 nu) gamma / E
                c2 = 1.25 * 0.5 * 20. / 1000.
                want = {n: (c2 * (y - za) * x, c2 * (y * y / 2 - za * y - x * x / 2), 0.) for n, (x, y, _) in xyz.items()}
            else:                                    # u_z held at (1, 0): the field shifted by c / 2
                want = {n: (c3 * (y - za) * x, c3 * (y * y / 2 - za * y - x * x / 2 + 0.5), 0.)
                        for n, (x, y, _) in xyz.items()}
            err, scale = t95_apart(u, want)
            tol = 1e-3 if kind == "hp_cax8" else 1e-9    # (ccx runs CAX8 as a 2-degree wedge: 2e-4)
            ok = len(u) == len(xyz) and err < tol * scale
            print(f"{'PASS' if ok else 'FAIL'}  t95_{kind} (*DLOAD HP on every outer face of a {what} "
                  f"of the fluid's density, under its weight): sigma = -p I, the exact quadratic u "
                  f"({err / scale:.1e} of max |u| {scale:.4g} off" +
                  ("; ccx's own pressure on CAX8 is 2e-4 off the exact ring" if kind == "hp_cax8" else "") + ")")
        failures += 0 if ok else 1
    for d in t95_dirs:
        shutil.rmtree(d, ignore_errors=True)

    # surface-based heat loads as ccx's element-based cards (they were commented out): a bar
    # heated by *DSFLUX at one end and cooled by *SFILM / *SRADIATE at the other, on DC3D8, on
    # DC2D4 and on DCAX4 (whose edge numbering ccx must read as Abaqus does): linear along the
    # bar, exactly; then empty OP=NEW cards remove both (the bar at its held 100 throughout)
    def temps(dat):
        blocks = [{int(r[0]): r[1] for r in rows if len(r) == 2} for rows in dat_tables(dat, "temperatures")]
        return blocks if blocks and all(blocks) else None
    for kind in ("dc3d8", "dc2d4", "dcax4"):
        for out in ("film", "radiate"):
            tag = f"surface_heat_loads_{kind}_{out}"
            steps = review_run(surface_heat_deck(kind, out, op_new=True), tag, temps)
            if not steps or len(steps) != 2:
                failures += 1
                continue
            t, t2 = steps
            cold = 30.0 if out == "film" else \
                ((20.0 + 273.15) ** 4 + 100.0 / (0.5 * 5.67e-8)) ** 0.25 - 273.15
            want = {n: cold + 50.0 * (4 - (n - 1) % 5) for n in t}
            err = max(abs(t[n] - want[n]) for n in t) / 200.0
            err2 = max(abs(v - 100.0) for v in t2.values()) / 100.0
            ok = len(t) == (20 if kind == "dc3d8" else 10) and err2 < 1e-6 and \
                err < (1e-6 if out == "film" else 1e-5)
            print(f"{'PASS' if ok else 'FAIL'}  {tag} (*DSFLUX 100 in at one end, *S"
                  f"{'FILM' if out == 'film' else 'RADIATE'} out at the other, k = 2): T = "
                  f"{max(t.values()):.6g} .. {min(t.values()):.6g} ({cold + 200:.6g} .. {cold:.6g}; "
                  f"{err:.1e} of the span off); after both cards' OP=NEW, held at 100: "
                  f"{min(t2.values()):.7g} .. {max(t2.values()):.7g}")
            failures += 0 if ok else 1
    # a *MASS on a rigid-body member node in no other element (ccx's *FREQUENCY stopped on it)
    for mpc in (False, True):
        tag = f"member_mass_frequency_{'mpc_beam' if mpc else 'rigid_body'}"
        f = review_run(member_mass_frequency_deck(mpc), tag,
                       lambda dat: dat_eigen_table(dat, "E I G E N V A L U E"))
        want = math.sqrt(1000.0 / 2.5) / (2 * math.pi)
        ok = bool(f) and abs(f[0] / want - 1) < 1e-6
        if f:
            print(f"{'PASS' if ok else 'FAIL'}  {tag} (a spring-held {'*MPC BEAM' if mpc else '*RIGID BODY'}"
                  f" body, its mass on a member node in no other element): f = {f[0]:.7g} "
                  f"(sqrt(k/m)/2pi = {want:.7g})")
        failures += 0 if ok else 1
    # --- one rule per step question (the walkers of the deck's steps agree) ----------
    # a *BUCKLE step's LOAD CASE=2 BCs, left out (ccx has one set of BCs per step: the modes
    # get the LOAD CASE=1 ones, warned), counted as BCs by the planners: the OP=NEW of
    # LOAD CASE=1 went, as if the step re-specified the BCs in force, so ccx kept the top's
    fac = review_run(lc2_column_deck(), "lc2_column",
                     lambda dat: dat_eigen_table(dat, "B U C K L I N G   F A C T O R   O U T P U T"))
    ok = bool(fac) and len(fac) == 2
    if ok:
        ref = math.pi ** 2 * 2.1e11 * 0.1 ** 4 / 12 / (4 * 4.0 ** 2)      # cantilever: pi^2 E I / (4 L^2)
        err = max(abs(f / ref - 1) for f in fac)
        ok = err < 0.01
        print(f"{'PASS' if ok else 'FAIL'}  lc2_column (B31 column, *BUCKLE with LOAD CASE=1 "
              f"clamping the foot, LOAD CASE=2 also holding the top): factors {fac[0]:.6g}, "
              f"{fac[1]:.6g} vs the cantilever's {ref:.6g} ({err:.1e} apart; held at the top "
              f"the second was 2.21e6)")
    elif fac:
        print(f"FAIL  lc2_column: {len(fac)} factors")
    failures += 0 if ok else 1

    # a *RESPONSE SPECTRUM step (a linear perturbation step, which ccx has no procedure for):
    # *NO ANALYSIS, so ccx stops there, after the static and the frequency step.  (ccx ran it as
    # a second *FREQUENCY step and went on, which showed the velocity-BC plan's error: it
    # counted the step as a general one of unknown time and dropped the top's velocity BC in
    # the last step; test_one_perturbation_step_rule keeps that.)
    src, inp = os.path.join(tmp, "pert_procs_src.inp"), os.path.join(tmp, "pert_procs.inp")
    with open(src, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(pert_procs_deck())
    convert(src, inp)
    d = tempfile.mkdtemp(prefix="ccxval_")
    shutil.copy(inp, os.path.join(d, "job.inp"))
    r = subprocess.run([ccx, "job"], cwd=d, env={**os.environ, **env}, capture_output=True,
                       encoding="utf-8", errors="replace", timeout=600)
    disp = frd_blocks(os.path.join(d, "job.frd"), "DISP")      # step 1's, then the modes'
    shutil.rmtree(d, ignore_errors=True)
    top = disp[0][1].get(7, [0.0, 0.0, math.nan])[2] if disp else math.nan
    sel = [ln.strip() for ln in r.stdout.splitlines() if "analysis was selected" in ln]
    ok = r.returncode == 0 and "*ERROR" not in r.stdout and abs(top / 0.01 - 1) < 1e-6 and \
        sel == ["Static analysis was selected", "Frequency analysis was selected",
                "No analysis was selected"]
    print(f"{'PASS' if ok else 'FAIL'}  pert_procs (a C3D8 cube's top moving at 0.01 per time in a "
          f"static step, then *FREQUENCY, *RESPONSE SPECTRUM and a static step): ccx ran the static "
          f"step (the top at {top:.7g}, 0.01) and the frequency step and stopped at the *RESPONSE "
          f"SPECTRUM step, exit code {r.returncode} (before: it ran that step as a second "
          f"*FREQUENCY and went on)")
    failures += 0 if ok else 1

    # cards between two steps act in the next one (ccx reads them so): the *CLOAD and *NODE
    # PRINT there were commented out
    runs = [review_run(between_steps_deck(twin), "between_steps" + ("_ref" if twin else ""),
                       dat_node_blocks) for twin in (False, True)]
    ok = all(runs) and len(runs[0]) == len(runs[1]) == 1
    if ok:
        err, moved = same(runs, -1)
        side = runs[0][-1].get(6, [0.0])[0]
        ok = err < 1e-12 + 1e-9 * moved and side > 1e-4
        print(f"{'PASS' if ok else 'FAIL'}  between_steps (a C3D8 cube: *BOUNDARY, OP=NEW, *CLOAD and "
              f"*NODE PRINT between two static steps): solved as with them in the second step "
              f"({err:.1e} apart; the loaded corner moved {side:.4g})")
    elif all(runs):
        print(f"FAIL  between_steps: {len(runs[0])} and {len(runs[1])} printed blocks")
    failures += 0 if ok else 1

    # an *EQUATION whose DOFs other steps hold ("crossed"), or held at nonzero values it
    # satisfies (ccx stopped: a BC on its dependent DOF, '*ERROR in cascade')
    runs = {c: review_run(equation_steps_deck(c), "equation_" + c, dat_node_blocks)
            for c in ("crossed", "crossed_ref", "nonzero", "nonzero_r1", "nonzero_r2")}
    ok = all(runs.values()) and len(runs["crossed"]) == len(runs["nonzero"]) == 2
    if ok:
        e1, moved = same([runs["crossed"], runs["crossed_ref"]])
        e2, _ = same([runs["nonzero"][:1], runs["nonzero_r1"]])
        e3, _ = same([runs["nonzero"][1:], runs["nonzero_r2"]])
        tie = abs(runs["nonzero"][1].get(7, [0.0, math.inf])[1] - runs["nonzero"][1].get(6, [0.0, math.nan])[1])
        ok = max(e1, e2, e3, tie) < 1e-9 * moved and moved > 1e-3
        print(f"{'PASS' if ok else 'FAIL'}  equation_crossed / _nonzero (*EQUATION u2(7) = u2(6) on a "
              f"cube, held by BCs on one DOF per step, or on both at 0.1): solved as without the "
              f"equation where the BCs hold it ({e1:.1e}, {e2:.1e} apart) and as the tied step alone "
              f"({e3:.1e} apart; tied DOFs {tie:.1e} apart; moved {moved:.3g})")
    elif all(runs.values()):
        print(f"FAIL  equation_crossed / _nonzero: {len(runs['crossed'])}, {len(runs['nonzero'])} tables")
    failures += 0 if ok else 1

    # three valid decks the converter crashed on (code review 3), solved as the deck without
    # what triggered it: a general step after a restored static perturbation step on shells
    # (the restore's OP=NEW, which removes nothing there, indexed the step's first *BOUNDARY)
    runs = [review_run(restored_chain_deck(c), "restored_chain" + ("" if c else "_ref"),
                       dat_displacements) for c in (True, False)]
    if all(runs):
        got, want = runs[0].get(5, [0.0, 0.0, math.inf])[2], runs[1].get(5, [0.0, 0.0, math.nan])[2]
        err = abs(ccx_ratio(got, want) - 1)
        ok = err < 1e-6 and want > 0.5
        print(f"{'PASS' if ok else 'FAIL'}  restored_chain (S4 strip: *FREQUENCY holding the tip "
              f"rotations, a static perturbation step, then a loaded static step): tip deflection "
              f"{got:.7g} vs {want:.7g} in the static step alone ({err:.1e} apart)")
    failures += 0 if all(runs) and ok else 1
    # a contact pair's master face on a C3D8 collapsed to a wedge (0 / 0 in closest_on_triangle)
    eig_title = "E I G E N V A L U E   O U T P U T"
    runs = [review_run(wedge_master_deck(c), "wedge_master" + ("" if c else "_ref"),
                       lambda p: dat_eigen_table(p, eig_title)) for c in (True, False)]
    if all(runs):
        err = max(abs(ccx_ratio(a, b) - 1) for a, b in zip(runs[0], runs[1]))
        ok = len(runs[0]) == len(runs[1]) == 6 and err < 1e-6 and runs[0][0] > 1.0
        print(f"{'PASS' if ok else 'FAIL'}  wedge_master (*CONTACT PAIR on a C3D8 face collapsed "
              f"to a triangle, open gap, *FREQUENCY): {len(runs[0])} frequencies from "
              f"{runs[0][0]:.7g}, {err:.1e} apart from the deck without the pair")
    failures += 0 if all(runs) and ok else 1
    # *NODE, INP= (INPUT abbreviated) in an included file whose data file sits beside it: a
    # unit cube (nu = 0) pulled by 4 at x = 1 stretches by 4 / 1000
    os.makedirs(os.path.join(tmp, "sub"), exist_ok=True)
    for name, text in (("mesh.inp", "*Node, inp=nodes.inp\n*Element, type=C3D8, elset=E\n"
                                    "1, 1, 2, 3, 4, 5, 6, 7, 8\n*Nset, nset=FIX\n1, 4, 5, 8\n"
                                    "*Nset, nset=TIP\n2, 3, 6, 7\n"),
                       ("nodes.inp", "1, 0., 0., 0.\n2, 1., 0., 0.\n3, 1., 1., 0.\n4, 0., 1., 0.\n"
                                     "5, 0., 0., 1.\n6, 1., 0., 1.\n7, 1., 1., 1.\n8, 0., 1., 1.\n")):
        with open(os.path.join(tmp, "sub", name), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    u = review_run("*Include, input=sub/mesh.inp\n*Material, name=M\n*Elastic\n1000., 0.\n"
                   "*Solid Section, elset=E, material=M\n*Step\n*Static\n*Boundary\nFIX, 1, 3\n"
                   "*Cload\nTIP, 1, 1.\n*Node Print, nset=TIP\nU\n*End Step\n", "inp_abbreviated",
                   dat_displacements)
    if u:
        dev = max(abs(u.get(n, [math.inf])[0] / 0.004 - 1) for n in (2, 3, 6, 7))
        ok = dev < 1e-9
        print(f"{'PASS' if ok else 'FAIL'}  inp_abbreviated (*NODE, INP=nodes.inp in an included "
              f"sub/mesh.inp): the pulled face moves {u.get(2, [math.nan])[0]:.7g} (4 / 1000; "
              f"{dev:.1e} apart)")
    failures += 0 if u and ok else 1


    # --- *DLOAD BX / BY / BZ on shells: a body force per unit volume in Abaqus, a pressure on
    # face 1 in ccx 2.23 (the strip's tip moved 48.08 out of its plane under BX), written as GRAV
    # of B / rho on a set of the shells (rho 7.5) or, without a density, as consistent nodal
    # forces of B t per area.  The strip under BX against q L^2 / (2 E A) (0.004) and its C3D8
    # twin; under BY against the deck written with that GRAV; under BZ against the pressure B t
    twin = review_run(shell_body_plate_deck("C3D8", ["*DLOAD\nE, BX, 2.\n"]), "shell_body_twin",
                      dat_node_blocks)
    for typ, rho in (("S4", 7.5), ("S4", None), ("S8R", 7.5)):
        how = f"{typ}, " + ("GRAV" if rho else "nodal forces")
        tag = f"shell_body_{typ.lower()}_{'grav' if rho else 'nodal'}"
        tip = 3
        for lab, ref_cards in (("BX", None), ("BY", "E, GRAV, {g}, 0., 1., 0."), ("BZ", "E, P, 0.2")):
            got = review_run(shell_body_plate_deck(typ, [f"*DLOAD\nE, {lab}, 2.\n"], rho),
                             f"{tag}_{lab.lower()}", dat_node_blocks)
            if lab == "BX":
                ref = twin
                want = [0.004, 0.0, 0.0]
            else:
                ref = review_run(shell_body_plate_deck(typ, ["*DLOAD\n" + ref_cards.format(g=2.0 / 7.5) + "\n"], 7.5),
                                 f"{tag}_{lab.lower()}_ref", dat_node_blocks)
                want = ref[-1].get(tip) if ref else None
            ok = bool(got and ref and want)
            if ok:
                u = got[-1].get(tip, [math.nan] * 3)
                scale = max(abs(x) for x in want)
                err = max(abs(a - b) for a, b in zip(u, want)) / scale
                twin_err = abs(twin[-1][3][0] / 0.004 - 1) if lab == "BX" else 0.0
                ok = err < 1e-4 and twin_err < 1e-4 and scale > 1e-3
                print(f"{'PASS' if ok else 'FAIL'}  {tag}_{lab.lower()} (the strip of {how}, E, {lab}, 2.): tip "
                      f"({', '.join(f'{x:.6g}' for x in u)}) vs " +
                      ("q L^2 / 2EA = 0.004 along x and the C3D8 twin's "
                       f"{twin[-1][3][0]:.6g}" if lab == "BX" else
                       "the deck with " + ("GRAV 2 / rho along y" if lab == "BY" else "*DLOAD P 0.2") +
                       f": ({', '.join(f'{x:.6g}' for x in want)})") + f", {err:.1e} apart")
            failures += 0 if ok else 1

    # the corpus barrel vault's shell: the Scordelis-Lo roof under its self-weight as BX, the
    # free edge's midspan vertical deflection against the published 0.3024 ft (3.6288 in);
    # before, ccx lifted the roof (BX as a pressure)
    for typ, n, rho, tol in (("S8R", 8, 1.0, 0.005), ("S8R", 8, None, 0.005), ("S4", 16, 1.0, 0.01)):
        text, node = scordelis_roof_deck(typ, n, rho)
        tag = f"scordelis_lo_{typ.lower()}_{'grav' if rho else 'nodal'}"
        got = review_run(text, tag, dat_node_blocks)
        u = -got[-1].get(node, [math.nan])[0] if got else math.nan
        ok = abs(u / 3.6288 - 1) < tol
        print(f"{'PASS' if ok else 'FAIL'}  {tag} (Scordelis-Lo roof, {n} x {n} {typ}, ROOF, BX, -0.20833 "
              f"as {'GRAV' if rho else 'nodal forces'}): free-edge midspan deflection {u:.5g} vs the "
              f"published 3.6288 in ({abs(u / 3.6288 - 1) * 100:.2f}% off, tolerance {tol * 100:g}%)")
        failures += 0 if ok else 1

    # the strip's body force over steps (tip ux per step: BX 2 is 0.004): a pressure beside it on
    # another amplitude (ccx stopped, '*ERROR in loadadd': both were face 1 loads), a later
    # step's BX replacing it, *DLOAD, OP=NEW removing it, *DSLOAD, OP=NEW keeping it (ccx's
    # *DLOAD, OP=NEW removed it: given again), BY kept beside a new BX, the deck's own GRAV
    # replaced beside it
    p_uz = None
    for name, steps, want, both in (
            ("amplitude", ["*DLOAD, AMPLITUDE=A\nE, BX, 2.\n*DLOAD\nE, P, 0.001\n"], [0.004], True),
            ("replaced", ["*DLOAD\nE, BX, 2.\n", "*DLOAD\nE, BX, -2.\n"], [0.004, -0.004], True),
            ("op_new", ["*DLOAD\nE, BX, 2.\n", "*DLOAD, OP=NEW\nE, P, 0.001\n"], [0.004, 0.0], True),
            ("dsload_op_new", ["*DLOAD\nE, BX, 2.\n*DSLOAD\nTOPS, P, 0.001\n",
                               "*DSLOAD, OP=NEW\nTOPS, P, 0.002\n"], [0.004, 0.004], True),
            ("by_kept", ["*DLOAD\nE, BX, 2.\nE, BY, 2.\n", "*DLOAD\nE, BX, 4.\n"], [0.022, 0.026], True),
            ("own_grav", ["*DLOAD\nE, BX, 2.\nE, GRAV, 0.2666666666667, 1., 0., 0.\n",
                          "*DLOAD\nE, GRAV, 0.5333333333333, 1., 0., 0.\n"], [0.008, 0.012], False)):
        for rho in ((7.5, None) if both else (7.5,)):
            tag = f"shell_body_steps_{name}_{'grav' if rho else 'nodal'}"
            got = review_run(shell_body_plate_deck("S4", steps, rho), tag, dat_node_blocks)
            ux = [blk.get(3, [math.nan])[0] for blk in got] if got else []
            ok = len(ux) == len(want) and all(abs(a - b) <= 1e-6 + 1e-4 * abs(b) for a, b in zip(ux, want))
            if ok and name == "amplitude":
                p_uz = got[-1][3][2]
                ok = abs(p_uz / 0.02404 - 1) < 1e-3          # the pressure's own (_plan_sheet_pressure)
            print(f"{'PASS' if ok else 'FAIL'}  {tag} (S4 strip, {'GRAV' if rho else 'nodal forces'}): "
                  f"tip ux per step {', '.join(f'{x:.6g}' for x in ux)} vs {', '.join(f'{x:g}' for x in want)}"
                  + (f"; uz {p_uz:.6g} vs the pressure's 0.02404" if name == "amplitude" and p_uz else ""))
            failures += 0 if ok else 1

    # --- other decks: confirm they are accepted and solve ----------------------
    # (loaded, every BC zero: any displacement is the solve's)
    for name in ("composite_shell", "assembly_two_blocks"):
        inp = os.path.join(tmp, name + ".inp")
        convert(os.path.join(EXAMPLES, name + ".inp"), inp)
        d, status, out = run_ccx(ccx, env, inp)
        disp = frd_last(os.path.join(d, "job.frd"), "DISP") if status == "solved" else {}
        shutil.rmtree(d, ignore_errors=True)
        moved = max((abs(x) for v in disp.values() for x in v[:3]), default=0.0)
        if status == "solved" and moved > 0.0:
            print(f"PASS  {name}: accepted by ccx and solved (largest |u| {moved:.4g} in the .frd)")
        elif status == "solved":
            print(f"FAIL  {name}: solved, but no node moves in the .frd ({len(disp)} nodes)")
            failures += 1
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
