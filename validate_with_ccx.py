#!/usr/bin/env python3
"""End-to-end validation: convert the example decks and actually run them in CalculiX.

This is the proof that the converter produces *runnable, correct* CalculiX input — not
just structurally-valid text.  It auto-detects a ``ccx`` binary (including the one
bundled with FreeCAD) and checks results against reference values: the NAFEMS LE10
stress, the tip deflections of circular-, pipe- and box-section cantilevers against beam
theory, a shell plate rigidly coupled to a loaded reference point against the same plate
built from solids, coupled bars whose coupled nodes also carry BCs against the same
constraints written without a coupling, a bar whose rigid end cap carries BCs on its nodes
against the same BCs written on its reference point, circular-section beams with a held
twist and a prescribed rotation against beam theory, a circular-section beam in an explicit
dynamic step against its static deflection, the natural frequencies and buckling loads of
planar (B21) beams with a rectangular and a circular section, per-element *DISTRIBUTION
orientations (a C3D8 plate and a composite S8R panel) against the same models written with
one orientation per element, a clamped beam and plate after a later step's *BOUNDARY,
OP=NEW, and the thermal strains of isotropic materials with an orthotropic / anisotropic
expansion.

    python validate_with_ccx.py

Exits 0 if every available check passes (or ccx is not installed — then it skips with
a clear message), 1 if a check fails.  Requires CalculiX; install it or FreeCAD.
"""

import glob
import math
import os
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
    abq2ccx.classify_ccx_run ("solved" / "accepted" / "failed")."""
    d = tempfile.mkdtemp(prefix="ccxval_")
    shutil.copy(inp_path, os.path.join(d, "job.inp"))
    full_env = dict(os.environ)
    full_env.update(env)
    try:
        r = subprocess.run([ccx, "job"], cwd=d, env=full_env,
                           capture_output=True, text=True, timeout=600)
        return d, A.classify_ccx_run(r.returncode, r.stdout, r.stderr), r.stdout + r.stderr
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


def dat_displacement(dat_path, node):
    """Last displacement (ux, uy, uz) printed for ``node`` by *NODE PRINT in a ccx .dat
    file, or None."""
    found, inblock = None, False
    if not os.path.exists(dat_path):
        return None
    for ln in open(dat_path):
        if ln.strip().startswith("displacements"):
            inblock = True
            continue
        f = ln.split()
        if inblock and len(f) == 4 and f[0] == str(node):
            found = [float(x) for x in f[1:]]
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


def dat_displacements(dat_path):
    """{node: (ux, uy, uz)} of every node *NODE PRINT wrote to a ccx .dat file (the last
    value printed for each), or None if there is no .dat file."""
    if not os.path.exists(dat_path):
        return None
    found, inblock = {}, False
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
    # as ENGINEERING CONSTANTS or ANISO.  Three heated unit cubes: two free ones against
    # alpha dT (one with its material system turned 30 deg about z), and one held in x whose
    # E and nu depend on temperature, read between the given rows (without the added rows
    # ccx is 0.6 % / 1.4 % off there).
    inp = os.path.join(tmp, "thermal.inp")
    convert(os.path.join(EXAMPLES, "thermal_expansion_cubes.inp"), inp)
    d, status, out = run_ccx(ccx, env, inp)
    dat = os.path.join(d, "job.dat")
    a1, a2, a3, dt = 1e-5, 2e-5, 4e-5, 90.0
    c, s = math.cos(math.radians(30.0)), math.sin(math.radians(30.0))
    e_hot, nu_hot = 1900.0, 0.245                                    # E, nu at T = 90
    expect = {1: [(a1 * c * c + a2 * s * s) * dt, (a1 * s * s + a2 * c * c) * dt, a3 * dt,
                  (a1 - a2) * s * c * dt, 0.0, 0.0],
              11: [a1 * dt, a2 * dt, a3 * dt, 0.0, 0.0, 0.0],
              21: [0.0, (a2 + nu_hot * a1) * dt, (a3 + nu_hot * a1) * dt, 0.0, 0.0, 0.0]}
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
              f"*Expansion): free strains {errs[0] * 100:.4f}% / {errs[1] * 100:.4f}% off alpha dT; "
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
