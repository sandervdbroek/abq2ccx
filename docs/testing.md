# Testing

| Layer | Command | Needs | Checks |
| --- | --- | --- | --- |
| Unit tests | `python tests/test_convert.py` (or `pytest tests/`) | nothing | exact conversion behaviour on small inline decks and the bundled examples |
| End-to-end | `python validate_with_ccx.py` | CalculiX | the converted examples solve and match independent references |
| Corpus | `python corpus/fetch.py`, then `python tests/test_corpus.py` | network once; CalculiX for the solve test | 1022 real decks convert cleanly, keep their loads and solve |

Each layer skips cleanly when its prerequisite is missing, so the unit tests always run
offline. Before handing over a change, run all three and check that
`python docs/generate_reference.py` leaves `git diff` empty (the reference docs are
generated: edit the generator, not the `.md`). The corpus solve test runs every gated deck
in ccx and takes about ten minutes; run ccx under a file-size cap (`ulimit -f 4194304`) so
that a runaway job cannot fill the disk.

## 1. Unit tests — `tests/test_convert.py`

Each test converts a small inline deck (`convert_str(text)`) or a bundled example and
asserts the exact output; the test names say what they check, and the run lists them.
They cover:

* **Input syntax** — keyword-line continuations, `*PARAMETER` arithmetic (a safe AST
  evaluator, not `eval`), `INPUT=` files, abbreviations, Fortran `D` exponents, blank-less
  keywords.
* **Mesh generation and assemblies** — `*NGEN`/`*NFILL`/`*NCOPY`/`*ELGEN`/`*ELCOPY`
  (curves, bias, reflection), instance transforms (translation before rotation),
  instance-qualified references, part-level sections and constraints copied per instance,
  set-name limits.
* **Elements and sections** — substitutions (the suite enforces that each keeps the node
  count), beam upgrades for circular, pipe and box sections, the planar constraint,
  surface elements, composite and continuum shells.
* **Materials** — elastic types, the expansion rewrites, plasticity forms, field
  dependencies, creep, `*DEPVAR`.
* **Constraints** — `*MPC`, couplings and rigid bodies, knot beams, overconstraint
  settling, connectors, `*TRANSFORM`s.
* **Loads, BCs and steps** — consistent nodal forces, the load audit, surface-element
  loads, velocity and acceleration BCs, the default amplitude of displacement BCs, `OP=NEW`,
  temperatures, explicit defaults, Riks.
* **Output** — the `.frd`/`.dat` mapping, output frequencies, preselected field and contact
  output, ccx's label lists.

Every bundled example is also converted and checked for referential consistency: no
dangling set, surface, material, orientation or amplitude reference.

## 2. End-to-end — `validate_with_ccx.py`

Converts the examples, runs them in CalculiX (found on `PATH`, in FreeCAD's bundle or in
Homebrew/MacPorts) and compares the results with references that do not come from the
converter. It prints one `PASS`/`FAIL` line per check.

| Example | Check | Reference | Agreement |
| --- | --- | --- | --- |
| `nle10_thickplate` | NAFEMS LE10 σyy at point D | published −5.38 MPa | −5.650 MPa, 5 % (element and mesh) |
| `nle10_surface_elements` | the same pressure on an `SFM3D8` skin (`*DSLOAD P` on `SPOS`, element `P`, `TRVEC`) | the face-pressure result | 7 digits |
| `beam_circ_cantilever`, `beam_pipe_box_cantilever` | tip deflection of `CIRC`, `PIPE` and `BOX` cantilevers | P L³ / 3 E I | ≤ 0.6 % |
| `beam_circ_rotation_bcs` | a held twist at pinned supports; a prescribed tip rotation | beam theory | ≤ 0.2 % |
| `beam_circ_explicit` | a circular-section beam in `*DYNAMIC, EXPLICIT` | beam theory | 1.0 % |
| `planar_pinned_beam`, `planar_pinned_circ_beam` | first two frequencies and the buckling load of planar `B21` beams | beam theory, Euler | ≤ 0.6 % |
| `beam_line_load_cantilever` | `*DLOAD PY`, `P2`, `PZ`: applied resultant and tip deflection | q L, q L⁴ / 8 E I | ≤ 1.2 % |
| `beam_output_requests` | output at `B32` nodes in the `.frd` (at `*TIME POINTS`) and the `.dat` | beam theory | ≤ 1.3 % |
| `coupling_shell_plate` | a rigid coupling on `S8R` nodes (knot beams) | the same plate in `C3D20R` under `*RIGID BODY` | 1e-5 of \|u\| |
| `coupling_bc_bars` | BCs on coupled nodes taken off (also NLGEOM) | the same constraints as BCs and `*EQUATION`s | round-off |
| `rigid_body_bc_bars` | BCs on `*RIGID BODY` nodes moved to the reference node (also NLGEOM) | the BCs written on the reference node | round-off |
| `equation_overconstraint` | an `*EQUATION` on a BC'd DOF, a duplicate, a loop of ties | ccx rejects the deck as written | solves, ties held |
| `mpc_beam_lever` | `*MPC BEAM` lever, linear and NLGEOM | statics; a 10⁴× stiffer beam lever | 0.04 %; ≤ 4e-5 |
| `mpc_pin_tie_joints` | `PIN` hinge and `TIE` joint between beam spans | beam theory | 0.33 % |
| `mpc_link` | `LINK`, linearised and NLGEOM | statics; constant length | exact; 1e-7 |
| connector variants of the three `*MPC` examples | `JOIN`, `WELD`, `BEAM`, `LINK` connectors | the `*MPC` versions | exact |
| `connector_hinge_beams` | a `HINGE` releases in-plane bending and transmits out-of-plane | beam theory | 0.33 % |
| `connector_hinge_bodies` | a hinge between two rigid bodies, oblique axis, offset joint | exact solution | 6e-8 |
| `connector_ground_hinge` | a body hinged to ground turned 138° under NLGEOM | rigid rotation about the axis | 6e-6 |
| `connector_transform_plate`, `connector_transform_join`, and the hinge examples with a `*TRANSFORM` | connectors on transformed nodes, also NLGEOM | the same models without the transform | exact |
| `op_new_respecify`, `op_new_remove` | clamps across a later step's `*BOUNDARY, OP=NEW` | expected deflections | ≤ 0.7 % |
| `distribution_solid_plate`, `distribution_shell_plate` | per-element `*DISTRIBUTION` orientations | their `*_explicit` twins (one orientation per element) | ≤ 3e-11 |
| `thermal_expansion_cubes` | isotropic `*Elastic` beside ORTHO / ANISO `*Expansion` (with shear terms) | α ΔT; analytic stress | ≤ 1e-6 |
| `thermal_no_initial_temperature` | `*Temperature` without initial temperatures | α T, α T L | ≤ 5e-6 |
| `cook_membrane_traction` | `*DSLOAD TRVEC` on `CPS8` edges | published 23.96 | 0.12 % |
| `cylinder_traction_cax` | radial `TRVEC` on a thick `CAX8` cylinder | Lamé | 0.02 % |
| `traction_transformed_face`, Cook's membrane with a `*TRANSFORM` | tractions on transformed nodes | the same models without the transform | round-off |
| `transform_spherical_rigid` | a spherical `*TRANSFORM`; a transformed rigid-body reference point | the model in global components | exact |
| `velocity_bc_column` | `TYPE=VELOCITY` with a `SMOOTH STEP`, kept into a second step | the integral of the velocity | 5e-5 of the travel |
| `velocity_bc_bar` | a bar driven by a velocity (explicit) and an acceleration (implicit) | wave theory | ≈ 1 % on average |
| `default_amplitude_bars` | a displacement BC and a `*CLOAD` without an amplitude, in implicit `*DYNAMIC`, `*VISCO`, a transient coupled and an explicit step | Abaqus' defaults: the BC ramped (explicit: held where it is), the load applied at once | the ramp to 7e-18 (ccx alone: 0.02 off); 1.98 × static overshoot; the hold exact |
| `preselect_output_bar`, `preselect_contact_blocks` | Abaqus/CAE's `PRESELECT` requests: U, RF, S, contact pressure | statics | ≤ 0.005 % |
| `explicit_default_output_bar` | an explicit step with no output request: 20 intervals | wave theory | exact before the wave arrives |
| `composite_shell`, `assembly_two_blocks` | accepted and solved | — | — |

## 3. Corpus — `corpus/` and `tests/test_corpus.py`

[`corpus/manifest.py`](../corpus/manifest.py) lists 1022 genuine Abaqus decks from about
180 public repositories: CAE exports with parts and assemblies, UMAT/VUMAT and UEL decks,
cohesive, explicit and coupled models, mesh-generation cards, `*Parameter` decks, across
composites, geotechnics, biomechanics, fracture, forming, thermal analysis, FEA-tool test
suites and teaching material. CalculiX-native decks are excluded on purpose: they would just
pass through. The files are not committed (licenses vary); `corpus/fetch.py` downloads them
into `corpus/files/` (gitignored), content-deduplicated.

Each entry has its URL, license, what it exercises, and:

| Field | Meaning |
| --- | --- |
| `expect_solve=True` | the deck must solve in ccx |
| `parse_only=True` | a mesh-only deck (no `*STEP`); ccx must accept it |
| `source_unloaded=True` | it solves, but the source deck loads nothing (an empty `*STEP`); kept as a conversion check, out of the headline count |
| `note` | why a deck does not solve, or what a gated one depends on |

The tests:

* `test_corpus_converts` — every deck converts without a crash and with no dangling
  reference. Always runs.
* `test_corpus_loads` — every step an `expect_solve` deck loads in Abaqus still carries a
  load after conversion (the converter's load audit), and `source_unloaded` flags exactly
  the decks that load nothing. Always runs.
* `test_corpus_solves` — runs every `expect_solve` and `parse_only` deck in ccx (300 s
  each). The judge, `classify_ccx_run` (shared with `--run` and `validate_with_ccx.py`),
  calls a run **solved** when ccx exits 0, prints "Job finished" without an `*ERROR` or a
  crash message on stdout or stderr, runs an analysis step, and writes only finite results
  to the `.dat` print blocks and the `.frd`; **nonfinite** when it finishes with NaN/Inf
  (ccx 2.23 ends a diverged solution with "Job finished" and exit 0); **accepted** for a
  mesh-only deck that reads cleanly; **failed** otherwise.
* `test_classify_ccx_run` — the judge itself, including the "Job finished, then abort" case
  of issue #3 and NaN/Inf results as ccx 2.23 writes them.
* `test_hood_hinge_keeps_one_mechanism_mode` — the hood-hinge deck's hinge leaves exactly
  one mechanism mode besides the six rigid-body modes.

**Results on ccx 2.23** (the FreeCAD 1.1.4 build): all 1022 decks convert with no dangling
reference. 200 are gated `expect_solve`: 186 solve under their own loads and 14 are
`source_unloaded`. 219 mesh-only decks are accepted. The other 603 stop first on:

| Decks | First blocker |
| ---: | --- |
| 353 | a user material (UMAT/VUMAT) |
| 66 | a user element (UEL) |
| 46 | an incomplete or invalid source deck (undefined sets or materials, external parameters, CAE fragments) |
| 34 | an explicit coupled temperature–displacement step (28), or `*MATRIX GENERATE` (6) |
| 19 | a `*DAMAGE INITIATION` criterion ccx 2.23 rejects |
| 24 | no convergence or divergence (17), or more than the gate's 300 s (7) |
| 16 | NLGEOM follower tractions (they convert with `--approximate`) |
| 16 | other ccx errors, one or a few decks each |
| 29 | an element type, beam section, user subroutine or physics ccx lacks (rigid, piezoelectric, infinite elements; I and general beam sections; cohesive, acoustic, pore-pressure models) |

Every one of them was checked to fail no worse than the original, unconverted deck. Fixing
a first error often only exposes a second, fundamental one behind it, so the converter aims
to translate or clearly flag each incompatibility rather than to make a deck run at any
cost.

### Adding a deck

Append an entry to `corpus/manifest.py` (name, raw URL, license, what it exercises), run
`python corpus/fetch.py`, then `python tests/test_corpus.py`. Gate a deck with
`expect_solve=True` only when it solves under its own loads, and give a non-solving deck a
`note` with its first ccx error.
