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
  substitutions for the ~60 Abaqus types that need them; surface elements (`SFM3D*`,
  `SFMAX*`), which only carry loads, leave the mesh and their loads become nodal forces.
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
RECT with equal area + strong-axis inertia, an NLGEOM surface traction or surface-element
pressure that follows the deforming surface (or acts per current area) → fixed nodal forces,
surface elements that carry mass or rebar → left out of the mesh. Off by default — nothing changes silently: a
Riks step is then commented out, because ccx would otherwise run it as an ordinary
load-controlled static step without saying so. (`*DYNAMIC, EXPLICIT` needs no reframing:
ccx integrates explicitly itself, and the converter adds the Abaqus/Explicit defaults ccx
lacks — no increment cap, `NLGEOM` on.)

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
PASS  nle10_surface_elements (SFM3D8 skin, *DSLOAD P on SPOS): SYY at D = -5.650160 MPa (face pressure -5.650160 MPa)
PASS  nle10_surface_elements (SFM3D8 skin, *DLOAD P, element normal): SYY at D = -5.650160 MPa (face pressure -5.650160 MPa)
PASS  nle10_surface_elements (SFM3D8 skin, *DLOAD TRVEC): SYY at D = -5.650160 MPa (face pressure -5.650160 MPa)
PASS  beam_circ_cantilever (B31 + CIRC): tip deflection = -4.2290 (beam theory -4.2441, 0.4% diff)
PASS  beam_pipe_box_cantilever (PIPE31 + PIPE): tip deflection y = -7.1490 (beam theory -7.1886, 0.6% diff)
PASS  beam_pipe_box_cantilever (B32 + BOX): tip deflection y = -1.7898 (beam theory -1.7887, 0.1% diff), z = -4.5091 (beam theory -4.5265, 0.4% diff)
PASS  coupling_shell_plate (rigid coupling on S8R nodes): RP displacement (-0.1025, +0.0191, +1.7152) vs the solid *Rigid Body (-0.1025, +0.0191, +1.7152), 0.001% of |u|
PASS  cook_membrane_traction (TRVEC on CPS8 edges): v_C = 23.932 (reference 23.96, 0.12% diff)
PASS  beam_line_load_cantilever (A): applied -1 (q L = -1), tip deflection -0.001173 (beam theory -0.001172, 0.1% diff)
PASS  beam_line_load_cantilever (B): applied +1 (q L = +1), tip deflection +0.001158 (beam theory +0.001172, 1.2% diff)
PASS  beam_line_load_cantilever (C): applied -0.1 (q L = -0.1), tip deflection -0.001583 (beam theory -0.001592, 0.6% diff)
PASS  cylinder_traction_cax (TRVEC on CAX8): u_r(10) = 0.019667 (Lame 0.019667, 0.00% diff)
PASS  cylinder_traction_cax (TRVEC on CAX8): u_r(20) = 0.013331 (Lame 0.013333, 0.02% diff)
PASS  composite_shell: accepted by ccx and solved
PASS  assembly_two_blocks: accepted by ccx and solved
```

The **NAFEMS LE10 thick-plate benchmark** is the headline check: the Abaqus deck uses
`*NCOPY` (→ 465 nodes) and `*ELGEN` (→ 48 C3D20 elements) with `GEN` sets and a `P2`
pressure face. After conversion, CalculiX solves it and reports σ_yy = −5.65 MPa at
point D versus the published reference −5.38 MPa — a 5 % difference, in line with this
element type and mesh density. That exercises the whole pipeline (mesh expansion,
node ordering, boundary sets, pressure face, solid section) and confirms it is correct.
The same plate then carries its pressure on a skin of `SFM3D8` surface elements, which ccx
does not have: the converter leaves the skin out and applies its load as consistent nodal
forces, which must reproduce the face-pressure result — given as a pressure on the skin's
`SPOS` side, as an element-based `P` of −p (Abaqus: positive along the element normal,
which points out of the plate here) and as a `TRVEC` into the plate.
The third check is a cantilever on linear `B31` beams with a circular section: its tip
deflection is compared with beam theory, P L³/(3 E I). The fourth does the same for a pipe
section on `PIPE31` elements and a box section on `B32` elements, which ccx 2.23 runs only
on `B32R`. The box has unequal sides and wall pairs and is loaded in both directions, so a
misread box dimension would miss beam theory by 18 % or more. The fifth couples a shell
plate's edge rigidly to an offset reference point that carries a force and a moment (a
coupling ccx 2.23 rejects on shell nodes without the converter's knot beams) and compares
the reference point's displacement with the same plate built from `C3D20R` bricks under
`*RIGID BODY`. The last three check loads ccx has no card for, which the converter applies
as consistent nodal forces: a shear traction (`*DSLOAD TRVEC`) on Cook's membrane against
the published displacement of its loaded edge (23.96, Bergan & Felippa 1985); uniform line
loads (`*DLOAD PY`, local `P2`, `PZ`) on three cantilevers — `B31`, `B32` and a circular
`B31` run as `B32` — against q L⁴/(8 E I), with the applied resultants checked against q L;
and a radial traction on an axisymmetric thick cylinder against Lamé's solution.

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
references; 189 solve in CalculiX under their own loads** (ccx exits 0, prints "Job
finished" with no `*ERROR` or crash, and runs an analysis step — and every step the
Abaqus deck loads still carries a load after conversion), and **219 mesh-only decks** — no
`*STEP`, so nothing to solve — are **accepted** by ccx. 14 more solve but apply no load in
the source deck itself (an empty `*STEP`: the solution is zero, in Abaqus too); they stay
in the gate as conversion checks, flagged `source_unloaded`. The other 600 convert cleanly
but use features ccx cannot run (user elements, UMAT/VUMAT and other user subroutines,
Riks, NLGEOM follower tractions, cohesive/connector elements, piezoelectric/acoustic
coupling) or are CAE part fragments / incomplete or invalid source decks — each verified to fail *no worse than the original, unconverted deck*. The converter never makes a deck
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
| **Equivalent** | mapped to the nearest CalculiX construct | `*KINEMATIC COUPLING`→`*COUPLING`+`*KINEMATIC`, `*MPC,TIE`→`*EQUATION`, `*DSLOAD`(pressure)→`*DLOAD`, `*COHESIVE/GASKET SECTION`→`*SOLID SECTION` (thin-continuum approx) |
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
| `*ORIENTATION` | `*ORIENTATION` | origin `c` subtracted (axes `a−c`, `b−c`); `DEFINITION=NODES` resolved; `SPHERICAL` unsupported; rotation line kept (ccx ≥ ~2.15) |
| `*DISTRIBUTION` | passed (solid-section only) | shells not supported by ccx |
| `*BEAM SECTION, SECTION=CIRC` | radius `r` → diameters `2r, 2r`; 2-node beams → `B32`/`B32R` | ccx reads an ellipse's axis lengths; ccx 2.23 rejects linear beams with a circular section, so each gets a midside node (BCs, temperatures and initial conditions on both end nodes reach it) |
| `*BEAM SECTION, SECTION=PIPE/BOX/THICK PIPE` | data unchanged, `THICK PIPE` → `PIPE`; beams → `B32R` | both codes read the data alike (outer radius, wall; `a, b, t1..t4`); ccx 2.23 runs these sections only on `B32R`, so 2-node beams get a midside node as for `CIRC` and `B32` only changes type |
| `*SHELL SECTION, COMPOSITE` | S6/S8R; synth `*ORIENTATION` per ply angle | no inline ply angle in ccx; `SYMMETRIC` layups mirrored; on continuum shells (SC8R) → `*SOLID SECTION` |
| `*STEP` | `NAME` dropped, `NLGEOM` on step, `AMPLITUDE=RAMP/STEP` kept, `PERTURBATION` only for freq/buckle, `*END STEP` added | explicit steps get `INC=10000000` + `NLGEOM` (Abaqus/Explicit defaults) |
| `*BOUNDARY ENCASTRE/PINNED/*SYMM` | numeric DOFs | rotational DOFs only if shells/beams (`--solid-dof` to force 1-3) |
| `*BOUNDARY, TYPE=VELOCITY/ACCEL` | `TYPE` dropped | ccx is displacement-only |
| `*DLOAD, Px` | unchanged | solid face numbering matches Abaqus |
| `*DSLOAD` (pressure) | `*DLOAD` with `Px` | ccx `*DSLOAD` is submodel-only; shells use `P` |
| `*DSLOAD`/`*DLOAD` `TRVEC`, `TRSHR` (surface tractions) | consistent nodal forces (`*CLOAD`) | ccx has no traction load: the face/edge shape functions are integrated over the undeformed geometry (× plane thickness, × 2πr axisymmetric; `TRSHR` projected onto the face). Exact in small-strain steps and for NLGEOM `TRVEC` with `FOLLOWER=NO, CONSTANT RESULTANT=YES`; other NLGEOM tractions only with `--approximate` |
| `*DLOAD` `PX`/`PY`/`PZ`/`P1`/`P2` on beams | consistent nodal forces (`*CLOAD`) | on the converted element's nodes (incl. inserted midside nodes); ccx's own beam `P1`/`P2` is a section-face pressure |
| surface elements `SFM3D3/4/4R/6/8/8R`, `SFMAX1/2`, `SFMGAX1/2` | left out of the mesh; their `TRVEC`, `TRSHR`, `P` (`*DLOAD`, or `*DSLOAD` on their `SPOS`/`SNEG` side) → consistent nodal forces | ccx has no surface element; they have no stiffness, so only their loads matter. Element sets keep their other members; `*SURFACE SECTION` and surfaces / `*EL PRINT` on them only are dropped. Abaqus signs: an element-based `P` acts along the element normal, a surface `P` against the surface normal. Kept (ccx then stops on them) if they carry rebar, or mass in a dynamic / frequency step or under gravity — unless `--approximate` |
| `*BOUNDARY, USER`, `*CLOAD, USER`, `...NU` load labels, `*TEMPERATURE, USER`, `*AMPLITUDE, DEFINITION=USER` | commented out | the Abaqus user subroutine cannot run in ccx, which would call its own stock `uboun.f` / `cload.f` / `dload.f` / ... instead — the warning names the one to port |
| `*MPC, TIE` | per-DOF `*EQUATION` | `PLANE`/`STRAIGHT` kept |
| `*KINEMATIC COUPLING` | node-surface `*COUPLING`+`*KINEMATIC` per DOF range | every data line kept; newer `*COUPLING`/`*KINEMATIC`/`*DISTRIBUTING` pass natively |
| `*RIGID BODY` | explicit `ROT NODE` added | ccx ignores BCs/moments on DOFs 4–6 of the `REF NODE`; they are moved to the `ROT NODE`'s DOFs 1–3 |
| rigid coupling on shell/beam nodes | knot beam per node + rotation `*EQUATION`s | ccx 2.23 rejects a rigid MPC on a shell, membrane, beam or truss node unless ccx made it a *knot*; a force-free `B31` (elset `ABQ2CCX_KNOT`) makes it one, and the rotations Abaqus couples are tied to the coupling's |
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

The converter also runs a **pre-flight overconstraint check**: if a DOF is both the
dependent term of an `*EQUATION`/`*MPC` and the target of a `*BOUNDARY`, it warns —
that combination is the single most common crash on converted decks (`*ERROR in
cascade … dependent side of a MPC and a SPC`). Flattened set/surface names are kept
within CalculiX's **20-significant-character** limit (and uniquified) so instance
prefixing can't silently collide two sets.

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
  pre-flight-warns; fix by removing the BC or the constraint on that DOF.
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
  `*ORIENTATION` axes, beam `n1` and `*NORMAL`, but not `*DISTRIBUTION` tables.
* Rigid couplings (`*KINEMATIC`, `*RIGID BODY`) on **shell/beam nodes** are rejected by
  ccx 2.23 (FreeCAD 1.1 build: `*ERROR in gen3dmpc … RIGID MPC`) unless the node is a
  ccx *knot*. The converter attaches a short force-free beam (elset `ABQ2CCX_KNOT`, no
  density) to each such node, which makes it one, and ties the node's rotations to the
  coupling as Abaqus does — exact in linear and `NLGEOM` steps (validated against the same
  plate built from solids). Not covered: explicit dynamics (ccx stops: "linear and
  nonlinear MPC's depend on each other"), a coupling whose shell/beam reference node
  couples only some translations, and coupled DOFs that also carry a `*BOUNDARY` (ccx
  stops on that overconstraint, which Abaqus resolves).
* `*DISTRIBUTION` / variable-angle-tow orientation is solid-section-only in ccx.
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
| [`examples/nle10_surface_elements.inp`](examples/nle10_surface_elements.inp) | the same plate, its pressure on an `SFM3D8` skin (`*DSLOAD P` on `SPOS`) → nodal forces |
| [`examples/composite_shell.inp`](examples/composite_shell.inp) | S8R composite layup, orthotropic, `*ORIENTATION`, `ENCASTRE`, `*DSLOAD` |
| [`examples/assembly_two_blocks.inp`](examples/assembly_two_blocks.inp) | two-instance assembly, `instance.node` reference in a step |
| [`examples/beam_circ_cantilever.inp`](examples/beam_circ_cantilever.inp) | `B31` + `SECTION=CIRC` → `B32` with midside nodes, radius → diameters, `*NGEN`/`*ELGEN` |
| [`examples/beam_pipe_box_cantilever.inp`](examples/beam_pipe_box_cantilever.inp) | `PIPE31` + `SECTION=PIPE` → `B32R` with midside nodes, `B32` + `SECTION=BOX` → `B32R`, biaxial tip load |
| [`examples/coupling_shell_plate.inp`](examples/coupling_shell_plate.inp) | `S8R` edge `*Coupling`+`*Kinematic` to a loaded reference point → knot beams + rotation ties, `*NGEN`/`*NFILL`/`*ELGEN` |
| [`examples/coupling_solid_plate.inp`](examples/coupling_solid_plate.inp) | its `C3D20R` + `*Rigid Body, TIE NSET` reference, `*NCOPY` |
| [`examples/cook_membrane_traction.inp`](examples/cook_membrane_traction.inp) | Cook's membrane, `CPS8`, `*DSLOAD TRVEC` → consistent nodal forces, `*NGEN`/`*NFILL`/`*ELGEN` |
| [`examples/beam_line_load_cantilever.inp`](examples/beam_line_load_cantilever.inp) | beam line loads `*DLOAD PY` / `P2` / `PZ` on `B31`, `B32` and an upgraded `CIRC` beam → nodal forces |
| [`examples/cylinder_traction_cax.inp`](examples/cylinder_traction_cax.inp) | axisymmetric `CAX8` thick cylinder, radial `*DSLOAD TRVEC` (2πr) |
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
