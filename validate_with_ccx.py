#!/usr/bin/env python3
"""End-to-end validation: convert the example decks and actually run them in CalculiX.

This is the proof that the converter produces *runnable, correct* CalculiX input — not
just structurally-valid text.  It auto-detects a ``ccx`` binary (including the one
bundled with FreeCAD) and checks results against reference values: the NAFEMS LE10
stress, the tip deflections of circular-, pipe- and box-section cantilevers against beam
theory, a shell plate rigidly coupled to a loaded reference point against the same plate
built from solids, circular-section beams with a held twist and a prescribed rotation
against beam theory, the natural frequencies and buckling loads of planar (B21) beams with a
rectangular and a circular section, and per-element *DISTRIBUTION orientations (a C3D8 plate
and a composite S8R panel) against the same models written with one orientation per element.

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
