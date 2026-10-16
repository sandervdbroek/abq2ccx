#!/usr/bin/env python3
"""End-to-end validation: convert the example decks and actually run them in CalculiX.

This is the proof that the converter produces *runnable, correct* CalculiX input — not
just structurally-valid text.  It auto-detects a ``ccx`` binary (including the one
bundled with FreeCAD) and, for the NAFEMS LE10 benchmark, checks the computed stress
against the published reference value.

    python validate_with_ccx.py

Exits 0 if every available check passes (or ccx is not installed — then it skips with
a clear message), 1 if a check fails.  Requires CalculiX; install it or FreeCAD.
"""

import glob
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
