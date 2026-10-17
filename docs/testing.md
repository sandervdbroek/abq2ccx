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

**CI.** GitHub Actions ([`ci.yml`](../.github/workflows/ci.yml)) run on every push and pull
request: the unit tests, the generated-reference check and a `pip install .` on Ubuntu, macOS
and Windows with Python 3.9 (the oldest supported) and the newest; and `validate_with_ccx.py`
on Ubuntu with conda-forge's `calculix` 2.23 build 2, the build FreeCAD 1.1.4 bundles
(`conda-meta/calculix-2.23-pl5321h484372f_2.json` in its macOS app), so CI solves with the ccx
the checks were written on (Ubuntu packages 2.21; later conda-forge builds of 2.23 add fixes
made after its release). The corpus stays local: it downloads 1022 decks and needs ten
minutes of ccx.

## 1. Unit tests — `tests/test_convert.py`

Each test converts a small inline deck (`convert_str(text)`) or a bundled example and
asserts the exact output; the test names say what they check, and the run lists them.
They cover:

* **Input syntax** — keyword-line continuations, `*PARAMETER` arithmetic (a safe AST
  evaluator, not `eval`), `INPUT=` files, abbreviations, Fortran `D` exponents, blank-less
  keywords, blank data fields kept in place.
* **Mesh generation and assemblies** — `*NGEN`/`*NFILL`/`*NCOPY`/`*ELGEN`/`*ELCOPY`
  (curves, bias, reflection), instance transforms (translation before rotation),
  instance-qualified references, part-level sections and constraints copied per instance,
  set-name limits.
* **Elements and sections** — substitutions (the suite enforces that each keeps the node
  count) and which of them are exact, `CPS4I`/`CPE4I` as `C3D8I` slabs and when they fall
  back, beam upgrades for circular, pipe and box sections, the planar constraint, surface
  elements, composite and continuum shells, `*SECTION CONTROLS`, rigid elements and analytical
  rigid surfaces (skins, normals, facets), rotary inertia.
* **Materials** — elastic types (an E-only line, cohesive traction elasticity), the
  expansion rewrites, plasticity forms, `*DAMAGE INITIATION` (the Johnson-Cook form ccx
  reads, other criteria commented), field dependencies, creep, `*DEPVAR`.
* **Constraints** — `*MPC`, couplings and rigid bodies, knot beams, overconstraint
  settling, connectors, `*TRANSFORM`s, ties to rigid surfaces.
* **Loads, BCs and steps** — consistent nodal forces, the load audit, surface-element
  loads, shell and membrane pressure on `SPOS`/`SNEG` sides, velocity and acceleration BCs,
  the default amplitude of displacement BCs, BCs on DOFs a node does not have, `OP=NEW`, `*BUCKLE` load cases, temperatures, the masses of
  transient coupled steps, explicit defaults, Riks.
* **Reduced physics** — the record of what a conversion drops or replaces
  (`Converter.reduced_physics`), and what does not count (exact substitutions, output
  requests, numerical controls); `*NODE, SYSTEM=` coordinates and `*NODE` normals.
* **Output** — the `.frd`/`.dat` mapping, output frequencies, preselected field and contact
  output, ccx's label lists.

Every bundled example is also converted and checked for referential consistency: no
dangling set, surface, material, orientation or amplitude reference.

## 2. End-to-end — `validate_with_ccx.py`

Converts the examples, runs them in CalculiX (found as `--run` finds it: `$CCX`, `PATH`,
FreeCAD, PrePoMax and bConverged installs, Homebrew/MacPorts) and compares the results with
references that do not come from the converter. It prints one `PASS`/`FAIL` line per check.

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
| `mpc_link` | `LINK`, linearised and NLGEOM (also two `LINK` lines in one card) | statics; constant length | exact; 1e-7 |
| connector variants of the three `*MPC` examples | `JOIN`, `WELD`, `BEAM`, `LINK` connectors | the `*MPC` versions | exact |
| `connector_hinge_beams` | a `HINGE` releases in-plane bending and transmits out-of-plane | beam theory | 0.33 % |
| `connector_hinge_bodies` | a hinge between two rigid bodies, oblique axis, offset joint | exact solution | 6e-8 |
| `connector_ground_hinge` | a body hinged to ground turned 138° under NLGEOM | rigid rotation about the axis | 6e-6 |
| `connector_transform_plate`, `connector_transform_join`, and the hinge examples with a `*TRANSFORM` | connectors on transformed nodes, also NLGEOM | the same models without the transform | exact |
| `mpc_transform` | `*MPC` `PIN`, `TIE` across faces with different transforms (twin nodes), a face pinned to a transformed reference point, a `LINK` to a transformed node; orthotropic, uneven mesh; also NLGEOM | the same model without the transforms | exact |
| `op_new_respecify`, `op_new_remove` | clamps across a later step's `*BOUNDARY, OP=NEW` | expected deflections | ≤ 0.7 % |
| `distribution_solid_plate`, `distribution_shell_plate` | per-element `*DISTRIBUTION` orientations | their `*_explicit` twins (one orientation per element) | ≤ 3e-11 |
| `thermal_expansion_cubes` | isotropic `*Elastic` beside ORTHO / ANISO `*Expansion` (with shear terms) | α ΔT; analytic stress | ≤ 1e-6 |
| `thermal_no_initial_temperature` | `*Temperature` without initial temperatures | α T, α T L | ≤ 5e-6 |
| `cook_membrane_traction` | `*DSLOAD TRVEC` on `CPS8` edges | published 23.96 | 0.12 % |
| `cylinder_traction_cax` | radial `TRVEC` on a thick `CAX8` cylinder | Lamé | 0.02 % |
| `traction_transformed_face`, Cook's membrane with a `*TRANSFORM` | tractions on transformed nodes | the same models without the transform | round-off |
| `dload_blank_fields` | `GRAV` and `CENTRIF` lines with blank fields (also without an element set): a clamped column, a spinning quarter disc | statics (the base carries the weight along z); the plane-stress rotating disc | round-off; ≤ 0.34 % |
| `transform_spherical_rigid` | a spherical `*TRANSFORM`; a transformed rigid-body reference point | the model in global components | exact |
| `transform_rotations` | rotational BCs and moments on a transformed kinematic reference point and beam tip, linear and NLGEOM | the model in global components (an untransformed `ROT NODE` held by an `*EQUATION`, a knot beam) | 2e-8 of \|u\| (before: 130 %) |
| `velocity_bc_column` | `TYPE=VELOCITY` with a `SMOOTH STEP`, kept into a second step | the integral of the velocity | 5e-5 of the travel |
| `velocity_bc_bar` | a bar driven by a velocity (explicit) and an acceleration (implicit) | wave theory | ≈ 1 % on average |
| `default_amplitude_bars` | a displacement BC and a `*CLOAD` without an amplitude, in implicit `*DYNAMIC`, `*VISCO`, a transient coupled and an explicit step | Abaqus' defaults: the BC ramped (explicit: held where it is), the load applied at once | the ramp to 7e-18 (ccx alone: 0.02 off); 1.98 × static overshoot; the hold exact |
| `coupled_quasistatic_bars` | transient coupled steps without inertia: two bars under ramped gravity (one with point masses), then one heated at its top, the other loaded at once | statics, with the temperatures the run prints; the same model in `*HEAT TRANSFER` steps; ccx's HHT overshoot of a jump, α / (1 + α) | 6e-9 at every increment (with the masses as given: 6e-3, 30 % of the expansion); temperatures equal; 5.26 %, −0.28 %, 0.015 % |
| `preselect_output_bar`, `preselect_contact_blocks` | Abaqus/CAE's `PRESELECT` requests: U, RF, S, contact pressure | statics | ≤ 0.005 % |
| `explicit_default_output_bar` | an explicit step with no output request: 20 intervals | wave theory | exact before the wave arrives |
| `cps4i_slab_bending` (also as `CPE4I`) | `CPS4I`/`CPE4I` as `C3D8I` slabs under an end couple: tip deflection, σ_xx, σ_zz | beam theory (exact for Abaqus' four-mode element on rectangles) | 4e-8 (a plain `CPS4`: 39 % of the deflection) |
| `shell_pressure_sides` | pressure on an `S8R` plate's `SPOS` side, its `SNEG` side, and element-based `P` | Navier, with the sign Abaqus gives each | 1.0 % |
| `kinematic_all_dofs` | a bare `*KINEMATIC` (all DOFs) on a solid face under a force and two moments | the face under `*RIGID BODY` | exact |
| `assembly_rotated_instances` | a turned instance with an oriented orthotropic material, instance-qualified loads, a surface pressure | the same model written flat by hand | exact (coordinates and displacements) |
| `damage_johnson_cook_cubes` | a Johnson-Cook `*DAMAGE INITIATION`: ccx's indicator `DUCT` (from `JCCRT`) in uniaxial tension; the run with the card against the run without | PEEQ / (d1 + d2 e^(−d3/3)); identical results | 5e-7; exact |
| `rigid_punch_block`, `rigid_punch_cylinder`, and generated plane and axisymmetric twins | a rigid flat punch of `R3D4`, `R2D2` or `RAX2` elements, or the same face as a `CYLINDER` / `SEGMENTS` analytical surface | ccx's penalty law A d / (L/E′ + 1/K); the punch given its motion node by node | 2e-7; ≤ 1e-14 |
| the same punches turned under NLGEOM (0.05 rad; plane 0.03 rad) | rigid skins and analytical surfaces | the punch given the exact motion | ≤ 8e-7 of \|u\| |
| a block tied to a turning rigid plate (`R3D4`, `CYLINDER`) | a `*TIE` to a rigid surface, NLGEOM | its top given the exact motion | 1.8e-7 (ccx's own tie: 1.3e-2) |
| `rigid_body_inertia` | `MASS` + `ROTARYI` of an `R3D4` plate on springs | its translation and rotation frequencies | 1.9e-7 |
| a faceted analytical sphere (`--approximate`) | the indentation force on a block | Hertz | 2.3 % (finite block, penalty contact) |
| the plane punch in explicit dynamics | `R2D2` skins at the increment the converter caps (ccx leaves this contact out of its estimate) | the punch given its motion node by node at that increment | exact |
| a rigid `R2D2` segment and an `R3D4` facet on a spring | an element pressure `P` (on the `R2D2`: per unit depth) | p / k | exact |
| a stretched cube with a `*USER MATERIAL` | named `UserMat` and `JohnsonCook_Steel` (renamed); with `--abaqus-umat`, small strain and NLGEOM | ccx stops: "no user material subroutine"; ccx's example UMAT: E ε, E ln(1 + ε) | —; exact; 1e-7 |
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
| `reduced_physics='<what>'` | it solves, but the conversion drops or replaces part of the Abaqus model (a constitutive behaviour, an element formulation, a section control, an interaction, a load, the geometry), so not its own problem; kept as a conversion check, out of the headline count |
| `solver_differs='<why>'` | the conversion keeps the deck's physics, but ccx's solution is not the deck's: the deck relies on solver behaviour ccx 2.23 lacks (a part that only contact holds drifts away before the contact closes); found in the results; out of the headline count |
| `note` | why a deck does not solve, or what a gated one depends on |

The tests:

* `test_corpus_converts` — every deck converts without a crash and with no dangling
  reference. Always runs.
* `test_corpus_loads` — every step an `expect_solve` deck loads in Abaqus still carries a
  load after conversion (the converter's load audit), and `source_unloaded` flags exactly
  the decks that load nothing. Always runs.
* `test_corpus_fidelity` — `reduced_physics` flags exactly the `expect_solve` decks whose
  conversion records reduced physics (`Converter.reduced_physics`): no deck counts as a
  faithful solve while the converter drops its material model or replaces its element;
  `solver_differs` sits only on `expect_solve` decks. Always runs.
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
reference. 206 are gated `expect_solve`: **165 solve the deck's own physics**; 14 are
`source_unloaded`, one is `solver_differs` (a snap-fit insert that only contact holds drifts
out of its buckle) and 29 (3 of them also unloaded) are `reduced_physics` — concrete damaged
plasticity (2), UHARD / VUHARD hardening (4), field-dependent elasticity set by USDFLD or a
user field (3), Chaboche back-stresses (3), `HOURGLASS=ENHANCED` (1), `CPE4H` (2),
`CPS6M`/`CPE6M` (4), `C3D10M`/`C3D10HS` (2), `STRI3` (2), linear circular-section beams run as
`B32` (3), general contact (2), a dropped `*IMPERFECTION` (1). 221 mesh-only decks are
accepted. The other 595 stop first on, or (the last row) run without, what they need:

| Decks | First blocker |
| ---: | --- |
| 353 | a user material (UMAT/VUMAT) |
| 66 | a user element (UEL) |
| 50 | an incomplete or invalid source deck (undefined sets or materials, external parameters, CAE fragments) |
| 34 | an explicit coupled temperature–displacement step (28), or `*MATRIX GENERATE` (6) |
| 26 | no convergence or divergence (18), or more than the gate's 300 s (8) |
| 16 | NLGEOM follower tractions (they convert with `--approximate`) |
| 15 | other ccx errors, one or a few decks each |
| 27 | an element type, beam section, user subroutine or physics ccx lacks (piezoelectric and infinite elements; I and general beam sections; cohesive, acoustic, pore-pressure models; composites on `S4R`) |
| 8 | Abaqus general contact (7) or an XFEM crack (1): ccx has neither, and the converted deck runs without it — not the deck's physics, so not gated |

Every one of them was checked to fail no worse than the original, unconverted deck. Fixing
a first error often only exposes a second, fundamental one behind it, so the converter aims
to translate or clearly flag each incompatibility rather than to make a deck run at any
cost.

### Adding a deck

Append an entry to `corpus/manifest.py` (name, raw URL, license, what it exercises), run
`python corpus/fetch.py`, then `python tests/test_corpus.py`. Gate a deck with
`expect_solve=True` only when it solves under its own loads (add `reduced_physics` with the
reason if the conversion report ends with "Reduced physics", and `solver_differs` if ccx's
results are not the deck's — a part that flies away, contact that never closes), and give a
non-solving deck a `note` with its first ccx error.
