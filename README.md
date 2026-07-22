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
plain `*STATIC`, `*DYNAMIC, EXPLICIT` → implicit `*DYNAMIC`, incompressible `ν ≥ 0.5` →
`0.475`, `*BEAM SECTION, SECTION=I` → the RECT with equal area + strong-axis inertia.
Off by default — nothing changes silently.

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
PASS  composite_shell: accepted by ccx and solved
PASS  assembly_two_blocks: accepted by ccx and solved
```

The **NAFEMS LE10 thick-plate benchmark** is the headline check: the Abaqus deck uses
`*NCOPY` (→ 465 nodes) and `*ELGEN` (→ 48 C3D20 elements) with `GEN` sets and a `P2`
pressure face. After conversion, CalculiX solves it and reports σ_yy = −5.65 MPa at
point D versus the published reference −5.38 MPa — a 5 % difference, in line with this
element type and mesh density. That exercises the whole pipeline (mesh expansion,
node ordering, boundary sets, pressure face, solid section) and confirms it is correct.

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

Results: **all 1022 convert with zero dangling references, and 414 solve in CalculiX.**
The other 608 convert cleanly but use features ccx cannot run (user elements, UMAT/VUMAT,
explicit dynamics, cohesive/connector elements, piezoelectric/acoustic coupling, other
user subroutines) or are CAE part fragments / incomplete source decks — each verified to
fail *no worse than the original, unconverted deck*. The converter never makes a deck
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
| **Equivalent** | mapped to the nearest CalculiX construct | `*KINEMATIC COUPLING`→`*RIGID BODY`, `*MPC,TIE`→`*EQUATION`, `*DSLOAD`(pressure)→`*DLOAD`, `*COHESIVE/GASKET SECTION`→`*SOLID SECTION` (thin-continuum approx) |
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
| `*ORIENTATION` | `*ORIENTATION` | `SPHERICAL` unsupported; rotation line kept (ccx ≥ ~2.15) |
| `*DISTRIBUTION` | passed (solid-section only) | shells not supported by ccx |
| `*SHELL SECTION, COMPOSITE` | S6/S8R; synth `*ORIENTATION` per ply angle | no inline ply angle in ccx |
| `*STEP` | `NAME` dropped, `NLGEOM` on step, `PERTURBATION` only for freq/buckle, `*END STEP` added | |
| `*BOUNDARY ENCASTRE/PINNED/*SYMM` | numeric DOFs | rotational DOFs only if shells/beams (`--solid-dof` to force 1-3) |
| `*BOUNDARY, TYPE=VELOCITY/ACCEL` | `TYPE` dropped | ccx is displacement-only |
| `*DLOAD, Px` | unchanged | solid face numbering matches Abaqus |
| `*DSLOAD` (pressure) | `*DLOAD` with `Px` | ccx `*DSLOAD` is submodel-only; shells use `P` |
| `*MPC, TIE` | per-DOF `*EQUATION` | `PLANE`/`STRAIGHT` kept |
| `*KINEMATIC COUPLING` | `*RIGID BODY` | newer `*COUPLING`/`*KINEMATIC`/`*DISTRIBUTING` pass natively |
| `*CREEP, LAW=STRAIN/TIME` | ccx Norton (default) | other laws → `LAW=USER` |
| `*NODE/ELEMENT OUTPUT`, `*OUTPUT` | `*NODE FILE`/`*EL FILE` | `POSITION=` stripped, `FREQ`→`FREQUENCY` |
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

* **`NLGEOM` default** — Abaqus/Explicit defaults geometric nonlinearity **on**;
  ccx `*STATIC` is linear unless `NLGEOM` is on the `*STEP`. Converting an explicit
  deck to implicit static can silently drop large-displacement effects.
* **Linear perturbation `*STATIC`** uses the base-state (tangent) stiffness in Abaqus;
  the converter maps it to a linear ccx `*STATIC`. Correct for small-strain elastic
  perturbations — verify if the base state was nonlinear.
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

* Contact (`*CONTACT PAIR`, `*SURFACE INTERACTION`) is passed through, not
  translated — property syntax differs in ccx; verify.
* Assembly flattening is best-effort; rotated instances do **not** rotate part
  `*ORIENTATION` vectors.
* `*DISTRIBUTION` / variable-angle-tow orientation is solid-section-only in ccx.
* Commented/unsupported cards (connectors, gaskets, cohesive, inertia relief,
  specialised materials/steps) must be remodelled by hand — the report tells you how.
* The converter validates *structure*, not *physics*. Run `ccx` and sanity-check.
* Targets CalculiX 2.22–2.23. `*DAMAGE INITIATION` (added in 2.23) is emitted; newer
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
| [`examples/coverage_kitchen_sink.inp`](examples/coverage_kitchen_sink.inp) | element substitutions, dropped/commented cards, output-var mapping |

## Tests

```bash
python tests/test_convert.py        # or: pytest tests/
```

Converts each example and asserts the emitted deck is referentially consistent and
that the keyword/element/output mappings behave as documented (including the
invariant that every element substitution preserves node count).

## Sources

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
