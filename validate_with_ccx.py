#!/usr/bin/env python3
"""End-to-end validation: convert the example decks and actually run them in CalculiX.

This is the proof that the converter produces *runnable, correct* CalculiX input — not
just structurally-valid text.  It auto-detects a ``ccx`` binary (including the one
bundled with FreeCAD) and checks results against reference values: the NAFEMS LE10
stress (also with the pressure carried by surface elements, which ccx does not have),
the tip deflections of circular-, pipe- and box-section cantilevers against beam
theory, a shell plate rigidly coupled to a loaded reference point against the same
plate built from solids, and the loads ccx has no card for — surface tractions (Cook's
membrane, Lame's cylinder) and beam line loads (cantilevers against beam theory) —
applied as consistent nodal forces, also on nodes with a *TRANSFORM (local axes), which
must match the same models without one.

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


def dat_displacement(dat_path, node):
    """Last displacement (ux, uy, uz) printed for ``node`` by *NODE PRINT in a ccx .dat
    file, or None."""
    return dat_displacements(dat_path).get(node)


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
