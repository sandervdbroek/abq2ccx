# abq2ccx — Abaqus → CalculiX input converter

`abq2ccx.py` converts an Abaqus `.inp` deck into a [CalculiX](http://www.calculix.de/)
(`ccx`) `.inp` deck.

CalculiX deliberately copies the Abaqus keyword syntax, so much of a deck passes
through unchanged. The value of this tool is in the parts that **differ** — and in
being *complete and honest* about coverage: every one of the ~140 CalculiX keywords
is recognised, supported Abaqus keywords are emitted as-is, and anything CalculiX
does not support is either converted to its nearest CalculiX construct or **commented
out with specific guidance** — never silently dropped.

What it handles:

* **Mesh-generation cards** (`*NGEN`, `*NFILL`, `*NCOPY`, `*ELGEN`, `*ELCOPY`) →
  expanded into explicit `*NODE`/`*ELEMENT`.
* **`*PART`/`*INSTANCE`/`*ASSEMBLY`** → flattened into one global numbering
  (instance translation/rotation applied, references resolved).
* **Elements** → mapped to CalculiX equivalents, with node-count-preserving
  substitutions for the ~60 Abaqus types that need them.
* **Keywords / parameters / data** → translated (materials, orientation/composites,
  sections, steps, BCs, loads, constraints, output).
* **Everything else** → classified against the full CalculiX keyword set and either
  passed, dropped (organisational cards), or commented with guidance.

It is a single dependency-free Python 3 script (standard library only).

## Documentation

Detailed docs live in [`docs/`](docs/index.md):

* [User guide](docs/user-guide.md) — install, CLI, options, workflow, module API.
* [Troubleshooting](docs/troubleshooting.md) — ccx runtime errors & silent-physics gotchas.
* [Architecture & developer guide](docs/architecture.md) — pipeline, data model, extending it.
* [Compatibility & sources](docs/compatibility.md) — the verified facts and where they come from.
* Generated references: [keywords](docs/keyword-reference.md) · [elements](docs/element-reference.md) · [output variables](docs/output-reference.md).

The rest of this README is a self-contained overview.

---

## Quick start

```bash
python3 abq2ccx.py model.inp                 # -> model_ccx.inp  (+ model_ccx.log)
python3 abq2ccx.py model.inp -o out.inp      # choose the output name
python3 abq2ccx.py decks/*.inp --outdir out  # batch-convert into a directory
python3 abq2ccx.py model.inp --run           # convert, then run CalculiX on the result
python3 abq2ccx.py model.inp --check         # dry run: report only, write nothing
python3 abq2ccx.py model.inp --json          # machine-readable report on stdout (CI)
python3 abq2ccx.py model.inp --strict        # exit 3 on any warning/commented card (CI)
python3 abq2ccx.py model.inp --approximate   # opt-in physics approximations (see below)
python3 abq2ccx.py model.inp --solid-dof     # solid-only model: ENCASTRE/*SYMM use DOF 1-3
```

Exit codes: `0` converted · `1` cannot read/write · `2` usage error · `3` `--strict`
findings · `4` internal conversion error.  `--run` auto-detects `ccx` (PATH, the
FreeCAD-bundled copy, Homebrew/MacPorts) — or point at one with `--ccx`/`$CCX`.

**`--approximate` mode** reframes constructs CalculiX cannot run as *approximately
equivalent* ones it can, each flagged with a loud `[APPROX]` warning: `*STATIC, RIKS` →
plain `*STATIC`, incompressible `ν ≥ 0.5` → `0.475`, `*BEAM SECTION, SECTION=I` → the
RECT with equal area + strong-axis inertia, a `*BOUNDARY` on DOFs a kinematic coupling or
an `*MPC` also constrains → dropped, as Abaqus/Standard does (ccx stops on it), and
identical BCs on a `*RIGID BODY`'s nodes that hold the body less than Abaqus' resolution
does → moved to the reference node with zero rotations about the other axes, as
Abaqus/Standard moves them (by default only where that is the same constraint). Off by
default — nothing changes silently: a Riks step is then commented out, because ccx would
otherwise run it as an ordinary load-controlled static step without saying so. (`*DYNAMIC,
EXPLICIT` needs no reframing: ccx integrates explicitly itself, and the converter adds the
Abaqus/Explicit defaults ccx lacks — no increment cap, `NLGEOM` on — and, for circular-
section beams, whose stable increment ccx 2.23 overestimates, a maximum time increment.)

Then run it in CalculiX (`ccx out`, no extension). The converter validates
*structure and syntax*, not *physics* — **always read the report** (printed to
stderr, written as `*_ccx.log`, and repeated as `**` comments at the top of the
output) and confirm the result against your `ccx` version.

Use as a module:

```python
import abq2ccx
result = abq2ccx.convert_file("model.inp")          # or convert_text(deck_string)
print(result.text)                                  # converted deck incl. header
print(result.report.summary())                      # "N warning(s), M note(s), ..."
result.geometry.nodes, result.geometry.elements     # parsed model
```

---

## Validation

The converter is validated **end-to-end against a solver**, not just structurally.
[`validate_with_ccx.py`](validate_with_ccx.py) converts the example decks and runs them
through CalculiX (it auto-detects `ccx`, including the copy bundled with FreeCAD):

```text
PASS  nle10_thickplate (NAFEMS LE10): SYY at point D = -5.650 MPa (reference -5.38 MPa, 5.0% diff)
PASS  beam_circ_cantilever (B31 + CIRC): tip deflection = -4.2290 (beam theory -4.2441, 0.4% diff)
PASS  beam_pipe_box_cantilever (PIPE31 + PIPE): tip deflection y = -7.1490 (beam theory -7.1886, 0.6% diff)
PASS  beam_pipe_box_cantilever (B32 + BOX): tip deflection y = -1.7898 (beam theory -1.7887, 0.1% diff), z = -4.5091 (beam theory -4.5265, 0.4% diff)
PASS  coupling_shell_plate (rigid coupling on S8R nodes): RP displacement (-0.1025, +0.0191, +1.7152) vs the solid *Rigid Body (-0.1025, +0.0191, +1.7152), 0.001% of |u|
PASS  coupling_bc_bars (BCs on coupled nodes): bar A vs the same constraints without a coupling, max |du| = 2.4e-18 of |u| 0.0624; bar C's end face |u3| <= 7.4e-21 as it moves 0.770 (NLGEOM)
PASS  beam_circ_rotation_bcs (A: pinned, twist held): deflection = -12.6581 (beam theory -12.6313, 0.2% diff)
PASS  beam_circ_rotation_bcs (B: tip turned 0.001 rad): deflection = +0.5004 (beam theory +0.5000, 0.1% diff)
PASS  beam_circ_explicit (B31 + CIRC, *DYNAMIC, EXPLICIT): end deflection = -0.1756 (beam theory -0.1773, 1.0% diff)
PASS  planar_pinned_beam (B21): f1, f2 = 93.67, 373.02 Hz (beam theory 93.81, 375.25), buckling load 220545 (Euler 221079); max 0.6% diff
PASS  planar_pinned_circ_beam (B21 + CIRC): f1, f2 = 40.81, 163.28 Hz (beam theory 40.62, 162.49), buckling load 16239 (Euler 16278); max 0.5% diff
PASS  distribution_solid_plate (C3D8 *SOLID SECTION, per-element *DISTRIBUTION orientation): 84 node displacements vs one *ORIENTATION per element, max difference 2.8e-11 of max |u|
PASS  distribution_shell_plate (composite S8R *SHELL SECTION, per-element *DISTRIBUTION orientation): 69 node displacements vs one *ORIENTATION per element, max difference 0.0e+00 of max |u|
PASS  mpc_beam_lever (*MPC BEAM -> *RIGID BODY): tip -3.2488 / lever end -4.2982 (statics -3.2500 / -4.3000, 0.04% diff); vs the equivalent tip load and a stiff-beam lever 3.8e-05
PASS  mpc_beam_lever, NLGEOM x10: lever end -38.410 vs a stiff-beam lever -38.410 (5.2e-07); lever length 20.0000010 (20)
PASS  mpc_pin_tie_joints: PIN hinge w = -1.2494 (beam theory -1.2500), TIE joint w = -0.4185 (propped cantilever -0.4199); worst 0.33% diff over both spans
PASS  mpc_link (linearised *EQUATION): u = (+0.00640, -0.00480) (statics (+0.00640, -0.00480), 0.0e+00 off)
PASS  mpc_link, NLGEOM (*MPC BEAM): length 5.0000001 (5) after turning 24.5 degrees
PASS  equation_overconstraint: solves (ccx rejects the deck as written); tied node u_x = -0.0e+00, loop u_x = +0.0420 (+0.0420, +0.0420)
PASS  op_new_respecify: step 2 beam tip +1.1898 (expected +1.1905, 0.05% diff), plate tip (prescribed) +2.0000 (expected +2.0000, 0.00% diff)
PASS  op_new_remove: step 2 beam tip +0.5910 (expected +0.5952, 0.71% diff), plate tip (step 1) +4.6380 (expected +4.6380, 0.00% diff)
PASS  thermal_expansion_cubes (isotropic *Elastic + ORTHO/ANISO *Expansion): free strains 0.0000% / 0.0000% off alpha dT; held cube at T = 90: strains 0.0001% off, sigma_xx = -1.71000 (analytic -1.71000)
PASS  rigid_body_bc_bars (BCs on *RIGID BODY nodes moved to the reference node): bar A vs the same BCs on the reference point by hand, max |du| = 9.7e-21 of |u| 0.3421; A's far face |u1| <= 9.0e-21 as it moves 0.512 (NLGEOM)
PASS  composite_shell: accepted by ccx and solved
PASS  assembly_two_blocks: accepted by ccx and solved
```

The **NAFEMS LE10 thick-plate benchmark** is the headline check: the Abaqus deck uses
`*NCOPY` (→ 465 nodes) and `*ELGEN` (→ 48 C3D20 elements) with `GEN` sets and a `P2`
pressure face. After conversion, CalculiX solves it and reports σ_yy = −5.65 MPa at
point D versus the published reference −5.38 MPa — a 5 % difference, in line with this
element type and mesh density. That exercises the whole pipeline (mesh expansion,
node ordering, boundary sets, pressure face, solid section) and confirms it is correct.
The second check is a cantilever on linear `B31` beams with a circular section: its tip
deflection is compared with beam theory, P L³/(3 E I). The third does the same for a pipe
section on `PIPE31` elements and a box section on `B32` elements, which ccx 2.23 runs only
on `B32R`. The box has unequal sides and wall pairs and is loaded in both directions, so a
misread box dimension would miss beam theory by 18 % or more. The fourth couples a shell
plate's edge rigidly to an offset reference point that carries a force and a moment (a
coupling ccx 2.23 rejects on shell nodes without the converter's knot beams) and compares
the reference point's displacement with the same plate built from `C3D20R` bricks under
`*RIGID BODY`. The fifth gives coupled bars' end faces BCs that their reference points'
own BCs already impose — ccx stops on such a BC, so the converter takes it off — and
compares them with the same constraints written as BCs and `*EQUATION`s, in an `NLGEOM`
step where one end face also turns about the axis of its dropped BC. The sixth gives two
circular-section beams rotational BCs — a twist held at
pinned supports, a prescribed tip rotation — and compares their deflections with beam
theory: under a rotational BC ccx 2.23 locks a circular section's other rotations, so this
needs the converter's knot beams (without them 0.31 and 0.76 of beam theory). The seventh
runs a circular-section beam through an explicit dynamic step — a load raised smoothly and
then held — and compares its end deflection with beam theory: ccx 2.23 sizes such a beam's
stable increment as if its section were the box around the circle, so without the
converter's increment cap the displacements turn NaN. The eighth and ninth run planar
`B21` beams (rectangular and circular sections) on pinned supports through a frequency
and a buckling step and compare the first two frequencies and the buckling load with beam
theory. ccx runs `B21` as a 3-D `B31`, so this needs the converter's planar constraint:
without it ccx reports 0 Hz modes (the free twist and the unsupported out-of-plane motion)
and a buckling factor of 1. The next two give every element its own
fibre angle through a `*DISTRIBUTION`, as a variable-angle-tow layup does: a `C3D8` plate
(two instances, one rotated; a default line, an element-set line and an additional
rotation) and a composite `S8R` panel whose plies follow +θ and −θ paths. Every node must
move exactly as in the same model written with one `*ORIENTATION` and section per element.
The `*MPC` checks hang a rigid lever (`BEAM`) on a cantilever tip and compare it with
statics, with the statically equivalent tip load and with a 10⁴× stiffer beam lever (also
at ten times the load under `NLGEOM`, about 27° of rotation); join two-span beams with a
`PIN` (a hinge: the second span hands half the load to the cantilever) and a `TIE` (a
rigid joint: one propped cantilever); and hold a spring-supported node with a `LINK`,
linearised and under `NLGEOM`. The next runs a deck ccx rejects as written: an `*EQUATION`
whose first DOF has a BC, a duplicate of it, and a loop of ties that ccx would silently
hold at zero.
The next two clamp a beam and a plate and give step 2 a `*BOUNDARY, OP=NEW`, which ccx 2.23
lets drop the clamps' rotations: one step re-specifies every BC (the converter drops its
OP=NEW), the other removes the beam's prop (the clamped nodes become knots). Converted
without these repairs, the beam tip moves 1e5 times too far and the plate's prescribed tip
displacement comes out 0. The thermal check heats unit cubes whose isotropic `*Elastic` sits
beside an orthotropic or anisotropic `*Expansion` — whose stiffness ccx 2.23 silently gets
wrong in linear steps once a deck has temperatures (a free cube shrinks) — and compares their
strains (one has its material system turned 30°) and the stress of a cube held in x, whose E
and ν vary with temperature, with the analytic values. The last gives the far face of a
bar's rigid end cap (a `*RIGID BODY` on its elements) `u1 = 0`, which ccx stops on and the
converter moves to the reference point with zero rotations about y and z, as Abaqus does —
implied in a first step that holds the reference point, moved in a second that releases
it — and compares the bar with the same BCs written on the reference point, in `NLGEOM`
steps where the cap twists 25° about the axis of the moved BC.

```bash
python validate_with_ccx.py        # requires CalculiX or FreeCAD; skips cleanly if absent
```

### Real-world corpus

Beyond the bundled examples, there is a **corpus of 1022 genuine Abaqus decks** pulled
from ~179 public repositories — Abaqus/CAE exports (`*Part`/`*Instance`/`*Assembly`),
user-element/UMAT/VUMAT decks, cohesive-zone and explicit-dynamics models, coupled
temperature-displacement, mesh-generation cards, named BCs, `*Parameter` — across many
engineering domains (composites, geotech, biomechanics, fracture/fatigue, metal forming,
thermal/AM, FEA-tool test suites, teaching material) — i.e. real files that do **not**
run in CalculiX directly, so they exercise the actual conversion. (CalculiX-native decks are
deliberately excluded; they would just pass through.) The files are fetched on demand
(not committed — licenses vary; see [`corpus/manifest.py`](corpus/manifest.py)):

```bash
python corpus/fetch.py             # download the decks into corpus/files/ (gitignored)
python tests/test_corpus.py        # convert all + (if ccx present) solve them
```

Results (CalculiX 2.23, the FreeCAD 1.1.4 build): **all 1022 convert with zero dangling
references; 219 solve in CalculiX** (ccx exits 0, prints "Job finished" with no `*ERROR` or
crash, and runs an analysis step), and **219 mesh-only decks** — no `*STEP`, so nothing to
solve — are **accepted** by ccx. The other 584 convert cleanly but use features ccx cannot
run (user elements, UMAT/VUMAT and other user subroutines, Riks, cohesive/connector
elements, piezoelectric/acoustic coupling) or are CAE part fragments / incomplete or
invalid source decks — each verified to fail *no worse than the original, unconverted deck*. The converter never makes a deck
worse than the original. Bulk-running every deck through convert → integrity → ccx (later
waves gathered by parallel discovery agents across a dozen engineering domains; plus
adversarial code reviews) surfaced and fixed real converter bugs — keyword-line
continuation, coupled-temperature `T`-suffix elements, `*PARAMETER` arithmetic (with a
safe AST evaluator, not `eval`), modified 6-node triangles, frictionless `*FRICTION`,
`*NFILL` with unequal bounding sets, space-separated `*INSTANCE` transforms, non-numeric
connector connectivity — on top of earlier fixes (independent-instance meshes,
`*PARAMETER` substitution, trailing-comma over-merge, Fortran `D` exponents, set-name
truncation). See [docs/testing.md](docs/testing.md) for the full test suite and a
description of each test.

---

## How it works

```
read (+*INCLUDE, normalise abbreviations)
   → flatten *PART/*INSTANCE/*ASSEMBLY
   → build geometry (expand *NGEN/*NCOPY/*ELGEN/… to explicit nodes & elements)
   → translate each keyword against the CalculiX keyword set
   → write
```

Every keyword falls into one of five buckets:

| Bucket | Action | Examples |
| --- | --- | --- |
| **Supported** | emit as-is (it's in the CalculiX keyword set) | `*PLASTIC`, `*HYPERELASTIC`, `*CONTACT PAIR`, `*EQUATION`, `*DENSITY` |
| **Translated** | dedicated handler adjusts keyword/params/data | `*NCOPY`, `*ELGEN`, `*ELASTIC`, `*SHELL SECTION` composite, `*STEP`, `*DSLOAD`, output cards |
| **Equivalent** | mapped to the nearest CalculiX construct | `*KINEMATIC COUPLING`→`*COUPLING`+`*KINEMATIC`, `*MPC` PIN/TIE→`*EQUATION`, `*MPC` BEAM→`*RIGID BODY`, `*DSLOAD`(pressure)→`*DLOAD`, `*COHESIVE/GASKET SECTION`→`*SOLID SECTION` (thin-continuum approx) |
| **Dropped** | organisational, no CalculiX meaning | `*PART/*INSTANCE/*ASSEMBLY` (flattened), `*PREPRINT`, `*PARAMETER`, `*SYSTEM` |
| **Commented** | no equivalent — emitted as `**` comments + warning | `*VISCOELASTIC`, `*CONNECTOR SECTION`, `*GASKET BEHAVIOR`, `*INERTIA RELIEF`, `*FIELD`, `*CONCRETE *` |

---

## Keyword reference

Verified against the CalculiX CrunchiX manual (v2.7 HTML / v2.22 PDF) plus the 2.23
release notes, and the `calculix/new_keywords` and `calculix/cae` keyword lists (which
track the exact Abaqus↔CalculiX delta). The converter knows the complete **CalculiX
2.22 + 2.23 keyword set (143 cards)**; any Abaqus card in that set is emitted unchanged.
`*DAMAGE INITIATION` (new in ccx 2.23) is passed through with a version/criterion note.

### Translated / equivalent (dedicated handlers)

| Abaqus | CalculiX | Notes |
| --- | --- | --- |
| `*NGEN/*NFILL/*NCOPY/*ELGEN/*ELCOPY` | explicit `*NODE`/`*ELEMENT` | no mesh-generation in ccx |
| `*PART/*INSTANCE/*ASSEMBLY` | flattened, one global numbering | instance transform applied; `inst.node`/`inst.set` resolved |
| `*ELASTIC, ORTHOTROPIC/ANISOTROPIC` | `ORTHO`/`ANISO` | same constant order |
| `*ELASTIC` less anisotropic than the material's `*EXPANSION` | isotropic beside `ORTHO` → `ENGINEERING CONSTANTS`; isotropic / orthotropic / engineering constants beside `ANISO` → `ANISO` | same stiffness; otherwise ccx 2.23 uses a wrong stiffness in linear steps once the deck has temperatures (thermal strains, displacements and frequencies all off); temperature rows added so the stiffness interpolation matches Abaqus' to 1e-4; materials with `*PLASTIC`/`*CREEP` left alone |
| `*ORIENTATION` | `*ORIENTATION` | origin `c` subtracted (axes `a−c`, `b−c`); `DEFINITION=NODES` resolved; `SPHERICAL` unsupported; rotation line kept (ccx ≥ ~2.15) |
| `*DISTRIBUTION` (per-element orientation) | solids: resolved per element; shells/membranes: one `*ORIENTATION` + section per direction | ccx 2.23 honours a distribution only under `*SOLID SECTION` (default line first, rotation line on the first line only, origin ignored) and gives a shell section its first line; one distribution per orientation; other distributions commented |
| `*BEAM SECTION, SECTION=CIRC` | radius `r` → diameters `2r, 2r`; 2-node beams → `B32`/`B32R` | ccx reads an ellipse's axis lengths; ccx 2.23 rejects linear beams with a circular section, so each gets a midside node (BCs, temperatures and initial conditions on both end nodes reach it) |
| `*BEAM SECTION, SECTION=PIPE/BOX/THICK PIPE` | data unchanged, `THICK PIPE` → `PIPE`; beams → `B32R` | both codes read the data alike (outer radius, wall; `a, b, t1..t4`); ccx 2.23 runs these sections only on `B32R`, so 2-node beams get a midside node as for `CIRC` and `B32` only changes type |
| `*SHELL SECTION, COMPOSITE` | S6/S8R; synth `*ORIENTATION` per ply angle | no inline ply angle in ccx; `SYMMETRIC` layups mirrored; on continuum shells (SC8R) → `*SOLID SECTION` |
| `*STEP` | `NAME` dropped, `NLGEOM` on step, `AMPLITUDE=RAMP/STEP` kept, `PERTURBATION` only for freq/buckle, `*END STEP` added | explicit steps get `INC=10000000` + `NLGEOM` (Abaqus/Explicit defaults) |
| `*BOUNDARY ENCASTRE/PINNED/*SYMM` | numeric DOFs | rotational DOFs only if shells/beams (`--solid-dof` to force 1-3) |
| `*BOUNDARY, TYPE=VELOCITY/ACCEL` | `TYPE` dropped | ccx is displacement-only |
| `*DLOAD, Px` | unchanged | solid face numbering matches Abaqus |
| `*DSLOAD` (pressure) | `*DLOAD` with `Px` | ccx `*DSLOAD` is submodel-only; shells use `P` |
| `*MPC` | line by line: `PIN`/`TIE` → per-DOF `*EQUATION`; `BEAM` → `*RIGID BODY` per independent node; `LINK` → linearised `*EQUATION` (no `NLGEOM`) or ccx `*MPC BEAM` | `PLANE`/`STRAIGHT` kept; a line ccx cannot take (user MPCs, other types) is commented out alone. `TIE` ties shell/beam rotations through knots (ccx ignores DOFs 4–6 of a plain shell/beam node in an `*EQUATION`) and the temperature in thermal steps; BEAM lines chained through a node form one body; ccx's `*MPC BEAM` keeps the distance between two nodes but rejects beam/shell/plane nodes |
| `*KINEMATIC COUPLING` | node-surface `*COUPLING`+`*KINEMATIC` per DOF range | every data line kept; newer `*COUPLING`/`*KINEMATIC`/`*DISTRIBUTING` pass natively |
| `*RIGID BODY` | explicit `ROT NODE` added | ccx ignores BCs/moments on DOFs 4–6 of the `REF NODE`; they are moved to the `ROT NODE`'s DOFs 1–3 |
| rigid coupling on shell/beam nodes | knot beam per node + rotation `*EQUATION`s | ccx 2.23 rejects a rigid MPC on a shell, membrane, beam or truss node unless ccx made it a *knot*; a force-free `B31` (elset `ABQ2CCX_KNOT`) makes it one, and the rotations Abaqus couples are tied to the coupling's |
| `*DYNAMIC, EXPLICIT` with `CIRC` beams | maximum time increment set (4th data field) | ccx 2.23 sizes a circular-section beam's stable increment as if its section were the box around the circle and runs it at about 1.3× the limit (NaN displacements); the cap is ccx's own estimate with the square through the section's corner nodes, side d/√2; a fixed (`DIRECT`) increment above it is warned |
| rotational BCs on `CIRC` beam nodes | knot beam per node | a BC on some of DOFs 4–6 (or a nonzero one) at a circular-section `B32` end node makes ccx 2.23 lock the node's other rotations too (a pinned beam with its twist held deflects 0.3 of beam theory); as a knot the node's BCs hold only the rotations they name |
| `*BOUNDARY, OP=NEW` in a later step, after rotational BCs on shell/beam nodes | OP=NEW dropped when the step re-specifies every BC; else knot beams on the nodes it would break | ccx 2.23 does not rebuild the rotational BCs it re-specifies (a clamp becomes a hinge) and on shells zeroes unrelated BCs; a knot carries the rotations in a form OP=NEW handles (exact on shells; a beam clamp 0.1–0.7 % stiffer); an explicit step in the deck: warned |
| `*BOUNDARY` on rigid-coupling members | taken off where the reference node's own BCs impose it; on a `*RIGID BODY` moved to the reference node (+ zero rotations about the other axes) where the BC'd nodes hold the same | ccx stops on a DOF that is both SPC'd and an MPC dependent; other such BCs are warned (`--approximate` drops them on a kinematic coupling and moves identical ones on a `*RIGID BODY`, as Abaqus/Standard does); a 2-D `*KINEMATIC` couples `1, 2` |
| `*CONTACT PAIR, TIED` | `*TIE` per surface pair | without `TYPE` → `NODE TO SURFACE` (the Abaqus/Standard default; face-to-face suggested if ccx struggles) |
| `*FRICTION` | `mu` only | ccx reads Abaqus' 2nd field (slip rate / mu_k) as its stick slope; `ROUGH` warned (no equivalent) |
| `*PLASTIC, HARDENING=JOHNSON COOK` | native ccx Johnson-Cook + `*RATE DEPENDENT` | ccx switches JC on only with a rate card (C = 0 added if the deck has none); `HARDENING=USER` / Chaboche `PARAMETERS` commented (material runs elastic) |
| `DEPENDENCIES=n` (field variables) | collapsed to field = 0 | ccx ignores field dependence and in effect uses the first row |
| `*CREEP, LAW=STRAIN/TIME` | ccx Norton (default) | other laws → `LAW=USER` |
| `*NODE/ELEMENT OUTPUT`, `*OUTPUT` | `*NODE FILE`/`*EL FILE` | `POSITION=`/`DIRECTIONS=` stripped, `FREQ`→`FREQUENCY` |
| `*EL PRINT`/`*NODE PRINT` without a set | whole-model set added | Abaqus prints everything; ccx prints nothing |
| output variables | ccx's own label lists per card | an unknown `*EL PRINT` label stops ccx; `*CONTACT OUTPUT` → `*CONTACT FILE` with `CDIS`/`CSTR` |
| `*SURFACE` shell edges `E1..E4` | `S3..S6` | on ccx shells `S1`/`S2` are the faces |
| `*AMPLITUDE, SCALEX/SCALEY` | scaled data points | ccx has no such parameters |
| `INPUT=` on a data card | file contents inlined | ccx reads `INPUT=` only on `*INCLUDE` |
| `*NSET, nset=X, ELSET=Y` | explicit `*NSET` of the elset's nodes | ccx has no NSET-from-ELSET |
| `*SHELL GENERAL SECTION` | `*SHELL SECTION` | thickness+material form only; ABD/stiffness form has no equivalent |
| `*TIE, TYPE=…, ADJUST=…` | `*TIE` (those params stripped) | ccx rejects them; master surface must be element-based |
| `*AMP` | `*AMPLITUDE` | keyword abbreviation expanded |
| `R3D3`/`R3D4` rigid elements | flagged | model as `*RIGID BODY` (NSET + ref/rot node) |

The converter also **resolves overconstraints** that ccx rejects and Abaqus resolves itself
— the single most common crash on converted decks (`*ERROR in cascade … dependent side of
a MPC and a SPC` / `… two different MPC's`). ccx eliminates the *first* term of every
`*EQUATION` (also the ones the converter writes), so where that DOF has a `*BOUNDARY` or is
eliminated by another constraint, another term of the same equation goes first (a bipartite
matching assigns them); an equation that follows from the others and zero BCs (a duplicate,
or one closing a loop of ties — ccx would silently hold such a loop at zero) is dropped, and
a `*BOUNDARY` on a rigid constraint member's eliminated DOF that the reference node's own
BCs impose anyway (the same value, no rotation about the other axes) is taken off.
Identical BCs on a `*RIGID BODY`'s nodes go where Abaqus/Standard puts them, onto the
reference node with zero rotations about the other axes, wherever the BC'd nodes hold that
DOF and those rotations themselves (exact). What cannot be resolved exactly keeps the
`Possible overconstraint` warning, which for a coupled node says what Abaqus does instead.
Flattened set/surface names are kept within CalculiX's **20-significant-character** limit
(and uniquified) so instance prefixing can't silently collide two sets.

### Dropped (organisational) and Commented (no equivalent)

* **Dropped:** `*PART/*INSTANCE/*ASSEMBLY` (after flattening), `*PREPRINT`,
  `*MANIFEST`, `*PARAMETER` (warns), `*SYSTEM` (warns — nodes may be in a rotated
  frame), `*UNIT SYSTEM`.
* **Commented out with guidance:** connectors (`*CONNECTOR *`, `*FASTENER`,
  `*JOINT`), gaskets (`*GASKET *`), cohesive/fracture (`*COHESIVE *`, `*DEBOND`,
  `*DAMAGE *`, `*ENRICHMENT`), `*INERTIA RELIEF`, `*FIELD`/`*REBAR`, unsupported
  materials (`*VISCOELASTIC`, `*CONCRETE *`, `*CAP/CLAY PLASTICITY`, `*HYPOELASTIC`,
  `*POROUS METAL PLASTICITY`), `*BEAM GENERAL SECTION`, and specialized procedures
  (`*RANDOM RESPONSE`, `*RESPONSE SPECTRUM`, `*GEOSTATIC`, `*MASS DIFFUSION`,
  explicit-only / co-simulation steps).
* **Semantic trap warned:** `*FILTER` (in ccx = sensitivity smoothing, *not* the
  Abaqus output filter). Note `*VISCO` is a ccx *creep step*, not material
  viscoelasticity.

---

## Element reference

Standard solid/shell/beam node and **face numbering are identical** to Abaqus, so
pressure-face labels (`P1..P6`) carry across unchanged. Element handling:

* **Direct** (emitted unchanged): `C3D4/6/8/8R/8I/10/15/20/20R/20RI`, `S3/4/4R/6/8/8R`,
  `M3D3/4/4R/6/8/8R`, `CPS*`, `CPE*`, `CAX*`, `B21/31/31R/32/32R`, `T2D2/T3D2/T3D3`,
  `SPRING*`, `DASHPOTA`, `GAPUNI`, `MASS`, `DC3D*`, `F3D*`.
* **Substituted** (node-count preserving, warned): `S3R→S3`, `STRI3→S3`,
  `STRI65→S6`, `S4R5→S4R`, `S8R5→S8R`, `B22→B32`, `B33→B31`, `T2D3→T3D3`, `PIPE3x→B3x`,
  `CPEG*→CPE*` (generalized plane strain), `CGAX*→CAX*` (generalized axisym),
  `SC6R→C3D6`/`SC8R→C3D8I` (continuum shell → solid), `C3D10M→C3D10`,
  `DASHPOT1/2→DASHPOTA`, `GAPCYL/GAPSPHER→GAPUNI`, and all hybrid `…H` → non-hybrid
  base (ccx has no mixed u/p formulation).
* **Upgraded** (warned): 2-node beams under a `*BEAM SECTION, SECTION=CIRC` (`B21`/`B31` →
  `B32`, `B31R` → `B32R`), which ccx 2.23 rejects, get a midside node at each element's
  midpoint; element ids and sets are kept. Under `SECTION=PIPE`, `BOX` or `THICK PIPE`, which
  ccx 2.23 runs only on `B32R`, `B21`/`B31`/`B31R` become `B32R` the same way and `B32` →
  `B32R` keeps its nodes.
* **Planar models**: ccx has no planar beam or truss — it runs `B21` as `B31` and `T2D2` as
  `T3D2`, and the other 2-D types map onto 3-D ones — so their out-of-plane motion is free
  (each bending mode twice in `*FREQUENCY`, out-of-plane `*BUCKLE` modes, truss nodes that are
  mechanisms). When the model is planar (2-D beams/trusses, no 3-D elements, all their nodes at
  one z) the converter fixes DOF 3 on their nodes, midside nodes of upgraded beams included
  (node set `ABQ2CCX_PLANAR`, model data, repeated after `*BOUNDARY, OP=NEW`), leaving out nodes
  that an `*EQUATION`, `*MPC`, rigid body, coupling or `*TIE` drives. A straight beam whose
  twist nothing restrains (pinned supports, or CAE's U1/U2/UR3 clamp) also gets DOFs 4–5 fixed
  at one node; otherwise its twist is a 0 Hz mode and `*BUCKLE` factors are meaningless — on a
  circular section at the middle node of an element, as at an end node ccx 2.23 would lock
  the bending rotation too. The rotations are not fixed everywhere (that stiffens ccx's
  expanded beams), so `*FREQUENCY` results also contain twist modes, which Abaqus' planar
  beams cannot have (warned).
* **Best-effort approximation** (node-count preserving, *strong* warning — behaviour lost):
  cohesive `COH*` and gasket `GK*` → the matching thin continuum (`COH3D8→C3D8`,
  `COH2D4→CPE4`, `GK3D8→C3D8`, …), with `*COHESIVE/GASKET SECTION → *SOLID SECTION`.
  The layer runs as a bonded/elastic solid; the traction-separation / closure law is
  **not** reproduced and a *zero-thickness* layer fails — give it a small finite
  thickness or remodel with contact. Pore-pressure `…P` → mechanical base
  (`CAX4P→CAX4`): the pore-pressure DOF is dropped (no consolidation).
* **No equivalent** (emitted unchanged, strong warning — needs remodelling):
  connector `CONN*`, `ROTARYI`, rigid `R2D/R3D/RB*` (use `*RIGID BODY` instead).

---

## Material & output reference

**Materials** — supported as-is: `*ELASTIC` (all TYPEs), `*PLASTIC` (all hardening),
`*DENSITY`, `*EXPANSION`, `*DAMPING`, `*HYPERELASTIC`, `*HYPERFOAM`, `*CONDUCTIVITY`,
`*SPECIFIC HEAT`, `*DEPVAR`, `*USER MATERIAL` (port the subroutine), `*DEFORMATION
PLASTICITY`, `*CYCLIC HARDENING`, `*MOHR COULOMB`, `*CREEP` (Norton). Unsupported
(commented): `*VISCOELASTIC`, `*DAMAGE *`, `*GASKET *`, `*HYPOELASTIC`, `*CONCRETE *`,
`*CAP/CLAY PLASTICITY`, `*POROUS METAL PLASTICITY`.

**Output variables** — renamed: `LE→E`, `PE→PEEQ`, `CEEQ→PEEQ`, `EE→ME`, `NT11→NT`,
`RM→RF`. Dropped (no ccx key; derive in post): `MISES`, `PRESS`, `NE`, `IE`, `A`,
`CF`, `NFORC`, `COORD`, `STH`, `CSTRESS`, `SF/SM/SE`. `ELSE`/`ELKE`/`EVOL`/`COORD`
are `*EL PRINT`-only and are dropped from `*EL FILE`.

---

## Runtime errors & silent-physics gotchas (from the CalculiX community)

These don't stop the *conversion* but bite when you run `ccx` or read results. The
converter warns about the ones it can detect; the rest are here so you know to check.
(Sourced from the CalculiX Discourse, PrePoMax forum, and the manual — see Sources.)

**It crashes / won't read:**

* **Overconstraint** — a `*BOUNDARY` on a DOF that's also an `*EQUATION`/`*MPC`/tie
  dependent → `*ERROR in cascade … dependent side of a MPC and a SPC`. The converter
  reorders equation terms, drops redundant equations, leaves out BCs a rigid body already
  implies and moves identical BCs on a `*RIGID BODY`'s nodes to its reference node where
  that is the same constraint; what is left is warned — fix by removing the BC or the
  constraint on that DOF.
* **Set used before defined** — ccx is order-dependent (Abaqus isn't). The converter
  emits nodes/elements, then sets, then steps, which avoids this.
* **Set/surface name > 20 significant chars** → silent collision. Handled for the
  flattened (assembly) path; keep your own set names short and ASCII.
* **Number field > 20 chars** (Fortran `f20.0`) is read **wrong without an error** —
  keep numeric tokens short (the converter emits coordinates at 12 significant digits).

**It runs but the physics differs:**

* **`NLGEOM` default** — Abaqus/Explicit defaults geometric nonlinearity **on**,
  ccx is linear unless `NLGEOM` is on the `*STEP`. The converter adds `NLGEOM` to
  explicit steps; Abaqus/Standard steps are linear by default in both.
* **Linear perturbation `*STATIC`** uses the base-state (tangent) stiffness in Abaqus;
  the converter maps it to a linear ccx `*STATIC`. Correct for small-strain elastic
  perturbations — verify if the base state was nonlinear. In ccx the step is a general
  step, so its loads **persist** into later steps (warned when steps follow).
* **`C3D8R` hourglassing** — ccx auto-enables hourglass control only from **v2.3**;
  for bending-dominated linear bricks prefer `C3D8I` or `C3D20R`.
* **Shells/beams are expanded to 3-D internally** — use `*NODE FILE, OUTPUT=3D` to see
  the expanded geometry/through-thickness stress; otherwise results look "wrong."
* **`*TEMPERATURE` ≠ a thermal BC** — in a heat-transfer step a fixed temperature is
  `*BOUNDARY` DOF 11; `*TEMPERATURE` is only the field driving thermal expansion.
* **Contact is penalty-based** (node-to-face / face-to-face); stiffness defaults differ
  from Abaqus, and there is no "no separation" behaviour.
* **Units are unenforced** — ccx is unitless; mixed unit systems silently corrupt results.

## Known limitations — review these

* Contact is translated card by card (`TYPE` default, `TIED` → `*TIE`, `*FRICTION` →
  constant `mu`, hard pressure-overclosure synthesized) — ccx's penalty contact still
  behaves differently from Abaqus; verify. A pair without `TYPE` gets Abaqus' default,
  node-to-surface; some decks converge in ccx only with `TYPE=SURFACE TO SURFACE` instead.
* Assembly flattening is best-effort. Part-level constraints (`*EQUATION`, `*MPC`,
  `*RIGID BODY`, `*COUPLING`, …) are copied per instance; rotated instances rotate
  `*ORIENTATION` axes (also per-element `*DISTRIBUTION` axes), beam `n1` and `*NORMAL`.
* Rigid couplings (`*KINEMATIC`, `*RIGID BODY`) on **shell/beam nodes** are rejected by
  ccx 2.23 (FreeCAD 1.1 build: `*ERROR in gen3dmpc … RIGID MPC`) unless the node is a
  ccx *knot*. The converter attaches a short force-free beam (elset `ABQ2CCX_KNOT`, no
  density) to each such node, which makes it one, and ties the node's rotations to the
  coupling as Abaqus does — exact in linear and `NLGEOM` steps (validated against the same
  plate built from solids). Not covered: explicit dynamics (ccx stops: "linear and
  nonlinear MPC's depend on each other" — also for rigid bodies on plane/axisymmetric
  nodes) and a coupling whose shell/beam reference node couples only some translations.
* A `*BOUNDARY` on a DOF that a rigid constraint also eliminates stops ccx; Abaqus resolves
  it. The converter removes it where the reference node's own BCs impose it anyway (exact).
  On a kinematic coupling or an `*MPC` Abaqus/Standard ignores any other such BC: the
  converter warns, and `--approximate` drops it the same way. On a `*RIGID BODY` Abaqus moves identical BCs
  on the body's nodes to the reference node, adding zero rotations about the other axes;
  the converter does the same where it changes nothing — the nodes BC'd on a DOF hold that
  DOF of the body and its rotations about the other axes (seen along the DOF they are not
  all on one line, or the reference node's own BCs make up the rest), and the body has not
  turned when the step starts — and otherwise only with `--approximate` (a single BC'd node,
  a face held in one in-plane direction, a body free before the BC appears). BCs that
  differ between the body's nodes, or contradict the reference node's own, stop Abaqus too
  and stay warned; so do `FIXED`/`USER` BCs.
* A rotational BC on a **circular-section beam** node also locks the node's other rotations
  in ccx 2.23 (it ties the section's midside nodes to its corners, which a circle cannot
  follow). Where a BC holds only some of DOFs 4–6, or a nonzero one, the converter gives the
  node a knot beam as above, whose BCs then hold only what they name (pinned beam with its
  twist held: 0.994 of beam theory instead of about 0.3). The knot's rigid section stiffens the
  beam slightly where it bends (0.3–1.3 % with a knot inside a span), which adds up when
  most nodes carry such a BC (warned). Not repaired in a deck with an explicit dynamic step
  (ccx stops on the knot beams; warned).
* A later step's `*BOUNDARY, OP=NEW` makes ccx 2.23 lose the rotational BCs it re-specifies
  on shell/beam nodes (a clamp becomes a hinge; on shells it also zeroes unrelated BCs). The
  converter drops an OP=NEW that removes nothing, and gives the affected nodes knot beams
  where it does remove BCs (a beam clamp then is 0.1–0.7 % stiffer, as a rigid section);
  with an explicit step in the deck it can only warn.
* `*MPC`: user MPCs (a numeric type) and types other than `PIN`, `TIE`, `LINK`, `BEAM`,
  `PLANE`, `STRAIGHT` are commented out. `LINK` under `NLGEOM` on a beam, shell, truss,
  membrane or plane-element node has no exact ccx form (ccx's distance MPC rejects such
  nodes), nor in a deck whose first step is linear and a later one `NLGEOM` (only with
  `--approximate`); ccx's distance MPC also struggles to converge once a link turns past 45°
  to the axis of its eliminated DOF.
* `*DISTRIBUTION` / variable-angle-tow orientations: ccx 2.23 applies them per element
  only under `*SOLID SECTION`, so the converter splits shell and membrane sections into
  one plain `*ORIENTATION` and section per distinct direction (validated against the same
  models written per element). A distribution that is not an orientation (Abaqus shell
  thickness or material-property distributions) has no ccx equivalent and is commented
  out; when a distribution's `INPUT=` file is missing, its `*ORIENTATION` is commented out
  too, so ccx stops at the sections that use it rather than run them in global axes.
* Thermal expansion under `NLGEOM`: ccx 2.23 silently loses the shear part of an
  orthotropic `*EXPANSION` whose axes an `*ORIENTATION` or a composite ply angle turns off
  the global axes, and stops with "too many cutbacks" on any `TYPE=ANISO` expansion once the
  deck has temperatures (linear steps are right). No form of the deck avoids it — the
  CalculiX sources fixed both after 2.23 — so the converter warns, naming the materials.
* Commented/unsupported cards (connectors, gaskets, cohesive, inertia relief,
  specialised materials/steps) must be remodelled by hand — the report tells you how.
* The converter validates *structure*, not *physics*. Run `ccx` and sanity-check.
* Validated on CalculiX 2.23 (the FreeCAD 1.1.4 build); written against 2.22–2.23.
  `*DAMAGE INITIATION` (added in 2.23) is emitted; newer
  Abaqus 2024/2025 cards (`*STEP CYCLING`, `*PIEZORESISTIVITY`, `*ELECTRIC MACHINE …`,
  `*ALLOWABLE STRESS`, …) have no ccx equivalent and are commented with guidance.
  Solid/shell node ordering is verified identical to Abaqus (so connectivity is passed
  through unchanged).

---

## Examples

| File | Exercises |
| --- | --- |
| [`examples/nle10_thickplate.inp`](examples/nle10_thickplate.inp) | NAFEMS LE10, C3D20, `*NCOPY`+`*ELGEN`+`GEN`/`PERT`, `*DLOAD Px` |
| [`examples/composite_shell.inp`](examples/composite_shell.inp) | S8R composite layup, orthotropic, `*ORIENTATION`, `ENCASTRE`, `*DSLOAD` |
| [`examples/assembly_two_blocks.inp`](examples/assembly_two_blocks.inp) | two-instance assembly, `instance.node` reference in a step |
| [`examples/beam_circ_cantilever.inp`](examples/beam_circ_cantilever.inp) | `B31` + `SECTION=CIRC` → `B32` with midside nodes, radius → diameters, `*NGEN`/`*ELGEN` |
| [`examples/beam_pipe_box_cantilever.inp`](examples/beam_pipe_box_cantilever.inp) | `PIPE31` + `SECTION=PIPE` → `B32R` with midside nodes, `B32` + `SECTION=BOX` → `B32R`, biaxial tip load |
| [`examples/coupling_shell_plate.inp`](examples/coupling_shell_plate.inp) | `S8R` edge `*Coupling`+`*Kinematic` to a loaded reference point → knot beams + rotation ties, `*NGEN`/`*NFILL`/`*ELGEN` |
| [`examples/coupling_solid_plate.inp`](examples/coupling_solid_plate.inp) | its `C3D20R` + `*Rigid Body, TIE NSET` reference, `*NCOPY` |
| [`examples/coupling_bc_bars.inp`](examples/coupling_bc_bars.inp) | `*Coupling`+`*Kinematic` on `C3D8` end faces that also carry BCs the reference point imposes → BCs taken off; a twin bar with the same constraints as BCs + `*EQUATION`; `NLGEOM` |
| [`examples/beam_circ_rotation_bcs.inp`](examples/beam_circ_rotation_bcs.inp) | circular-section `B31` beams with a twist held at pinned supports and a prescribed tip rotation → knot beams |
| [`examples/beam_circ_explicit.inp`](examples/beam_circ_explicit.inp) | circular-section `B31` beam in a `*DYNAMIC, EXPLICIT` step, `SMOOTH STEP` load → `B32` + a maximum time increment |
| [`examples/planar_pinned_beam.inp`](examples/planar_pinned_beam.inp) | planar `B21` beam on pinned supports: DOF 3 fixed on its nodes and the twist at the pin, `*FREQUENCY` + `*BUCKLE` |
| [`examples/planar_pinned_circ_beam.inp`](examples/planar_pinned_circ_beam.inp) | the same with a circular section (`B32` in ccx): the twist held at the first element's middle node |
| [`examples/op_new_respecify.inp`](examples/op_new_respecify.inp) | clamped `B31` beam + `S4` plate, step 2 re-specifies every BC with `*BOUNDARY, OP=NEW` → OP=NEW dropped |
| [`examples/op_new_remove.inp`](examples/op_new_remove.inp) | the same, step 2's `*BOUNDARY, OP=NEW` removes the beam's prop → knot beams on the clamped nodes |
| [`examples/mpc_beam_lever.inp`](examples/mpc_beam_lever.inp) | `*MPC BEAM` lever on a `B31` tip → `*RIGID BODY` on a knot, vs the equivalent tip load and a stiff-beam lever |
| [`examples/mpc_pin_tie_joints.inp`](examples/mpc_pin_tie_joints.inp) | two-span beams joined by `*MPC PIN` (hinge) and `TIE` (rigid joint, knots) |
| [`examples/mpc_link.inp`](examples/mpc_link.inp) | `*MPC LINK` + `SPRINGA` → linearised `*EQUATION`; ccx `*MPC BEAM` under `NLGEOM` |
| [`examples/equation_overconstraint.inp`](examples/equation_overconstraint.inp) | `*EQUATION` on a BC'd DOF (terms reordered), a duplicate and a loop of ties (dropped) |
| [`examples/coverage_kitchen_sink.inp`](examples/coverage_kitchen_sink.inp) | element substitutions, dropped/commented cards, output-var mapping |

## Tests

```bash
python tests/test_convert.py        # or: pytest tests/
```

Converts each example and asserts the emitted deck is referentially consistent and
that the keyword/element/output mappings behave as documented (including the
invariant that every element substitution preserves node count).

## Sources

* CalculiX CrunchiX User's Manual v2.23 — <https://www.dhondt.de/ccx_2.23.pdf>
* CalculiX CrunchiX User's Manual v2.22 — <https://www.dhondt.de/ccx_2.22.pdf>
* CalculiX CrunchiX User's Manual v2.7 (HTML) — <https://web.mit.edu/calculix_v2.7/CalculiX/ccx_2.7/doc/ccx/ccx.html>
* `calculix/new_keywords` (Abaqus↔CalculiX keyword delta) — <https://github.com/calculix/new_keywords>
* `calculix/cae` (CalculiX keyword model) — <https://github.com/calculix/cae>
* "A Guide to Modifying Abaqus Input Files for Use in CalculiX" (CalculiX Discourse) — <https://calculix.discourse.group/t/a-guide-to-modifying-abaqus-input-files-for-use-in-calculix/1430>
* CalculiX Discourse forum — <https://calculix.discourse.group/> · PrePoMax forum — <https://prepomax.discourse.group/>
* CalculiX — <http://www.calculix.de/>

## License

[MIT](LICENSE) © Sander van den Broek. `abq2ccx` is an independent tool and is not
affiliated with or endorsed by Dassault Systèmes (Abaqus) or the CalculiX project. The
real-world test corpus is fetched on demand and **not** redistributed here — each deck
keeps its own upstream license, recorded per entry in
[`corpus/manifest.py`](corpus/manifest.py).
