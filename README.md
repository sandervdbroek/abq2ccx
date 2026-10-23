# abq2ccx — Abaqus → CalculiX input converter

`abq2ccx.py` converts an Abaqus `.inp` deck into a [CalculiX](http://www.calculix.de/)
(`ccx`) deck. It is one Python 3 file with no dependencies.

CalculiX copies most of Abaqus' keyword syntax, so much of a deck passes through as it is;
the work is in the parts that differ. The converter knows the complete CalculiX 2.22 + 2.23
keyword set and does one of three things with every Abaqus card: passes it through,
translates it into the CalculiX construct that does the same, or comments it out with a
warning that says what to do. Nothing is dropped silently, and nothing that changes the
physics happens unless you ask for it with `--approximate`.

## Quick start

Run the file with Python 3.9 or later — copy it anywhere — or install it as the `abq2ccx`
command (`abq2ccx model.inp`, same options):

```bash
pipx install abq2ccx                                       # from PyPI
pipx install git+https://github.com/sandervdbroek/abq2ccx  # the latest main
conda install -c conda-forge calculix=2.23                 # CalculiX 2.23, to run the decks
```

```bash
python3 abq2ccx.py model.inp                 # -> model_ccx.inp (+ model_ccx.log)
python3 abq2ccx.py model.inp ccx_model.inp   # -> ccx_model.inp (+ ccx_model.log)
python3 abq2ccx.py decks/*.inp --outdir out  # batch-convert into a directory
python3 abq2ccx.py model.inp --run           # convert, run CalculiX, digest its results
python3 abq2ccx.py model.inp --check         # report only, write nothing
ccx model_ccx                                # run it yourself (no .inp extension)
```

Always read the report: it is printed to stderr, written to `*_ccx.log` and repeated as
`**` comments at the top of the converted deck. The [user guide](https://github.com/sandervdbroek/abq2ccx/blob/main/docs/user-guide.md) has
every option, the exit codes and the Python API.

```python
import abq2ccx
result = abq2ccx.convert_file("model.inp")   # or convert_text(deck_string)
print(result.report.summary())               # "N warning(s), M note(s), K commented card(s)"
```

## What it converts

* **Mesh generation** (`*NGEN`, `*NFILL`, `*NCOPY`, `*ELGEN`, `*ELCOPY`) → explicit nodes
  and elements.
* **Parts, instances and assemblies** → one flat model, with instance transforms applied
  and part-level sections, constraints and orientations copied per instance.
* **Elements** → CalculiX types, keeping the node count. Incompatible-mode `CPS4I`/`CPE4I`
  become exact one-element-thick `C3D8I` slabs (ccx has no such plane element); beams under
  circular, pipe and box sections get the midside nodes ccx 2.23 needs; planar beams and
  trusses are held in their plane; surface elements leave the mesh and their loads become
  nodal forces; connector elements become their kinematic constraints. A substitution that
  changes the element formulation (hybrid, modified or thin-shell elements run as ccx's
  plain ones) is flagged as reduced physics.
* **Materials and orientations** — elastic types, plasticity (including Johnson-Cook), the
  Johnson-Cook damage initiation criterion ccx shares with Abaqus, thermal expansion,
  composite layups and per-element `*DISTRIBUTION` orientations (variable-angle-tow layups);
  composite `S4R`/`S4`/`S3` shells run as `S8R`/`S6`, composite continuum shells (`SC8R`,
  `SC6R`) as one solid per ply.
* **Constraints** — `*MPC`, kinematic couplings and rigid bodies (with *knot beams* where
  ccx 2.23 rejects rigid constraints on shell and beam nodes), and the overconstraints ccx
  rejects but Abaqus resolves.
* **Rigid tools** — rigid elements (`R3D3`, `R3D4`, `R2D2`, `RAX2`, …) become force-free
  solid skins carried by their rigid body, so contact against them works; analytical rigid
  surfaces are meshed the same way, curved ones only with `--approximate`; a `*TIE` to a
  rigid surface makes its nodes part of the body, and `ROTARYI` becomes point masses.
* **Loads and BCs** — surface tractions and beam line loads become consistent nodal forces;
  velocity and acceleration BCs become integrated displacement BCs; `*TRANSFORM` local axes
  are respected wherever ccx reads them.
* **Steps and output** — explicit dynamics with Abaqus/Explicit's defaults, output requests
  fitted to ccx's `.frd`/`.dat` model, and Abaqus' preselected output.

The exact handling of every keyword, element type and output variable is in the generated
references: [keywords](https://github.com/sandervdbroek/abq2ccx/blob/main/docs/keyword-reference.md), [elements](https://github.com/sandervdbroek/abq2ccx/blob/main/docs/element-reference.md),
[output variables](https://github.com/sandervdbroek/abq2ccx/blob/main/docs/output-reference.md).

**Reduced physics.** Whatever the converter has to drop or replace of the Abaqus model — a
constitutive behaviour ccx lacks (concrete damaged plasticity, user hardening, Chaboche
back-stresses, field-dependent properties), an element formulation, a section control, a
constraint or interaction, a load — is named in a "Reduced physics" warning at the end of
the report (`Converter.reduced_physics` in the API): ccx then runs, but not the deck's own
problem.

**`--approximate`** (off by default) lets the converter reframe what ccx cannot run exactly
as a close equivalent, each flagged `[APPROX]` — a Riks step as plain static, ν ≥ 0.5 as
0.475, an I-section in space as ccx's `U1` beam with too stiff a torsion (or an equivalent
rectangle where `U1` cannot run), NLGEOM follower tractions as fixed nodal
forces, a curved analytical rigid surface as flat facets, general contact as contact pairs
between the model's bodies, and a few more
([full list](https://github.com/sandervdbroek/abq2ccx/blob/main/docs/user-guide.md#--approximate)). Without it those cards are commented out
with the reason, so ccx never silently runs a different model.

## Validation

`python validate_with_ccx.py` converts the bundled examples, runs them in CalculiX (it finds
`ccx`, including FreeCAD's copy) and compares each result with an independent reference. It
prints one `PASS` line per check, about 600 in all; [testing](https://github.com/sandervdbroek/abq2ccx/blob/main/docs/testing.md) lists them.

| Check | Reference | Agreement |
| --- | --- | --- |
| NAFEMS LE10 thick plate (`*NCOPY`, `*ELGEN`, pressure face) | published σyy at D = −5.38 MPa | −5.650 MPa, 5 % (element and mesh) |
| the same plate loaded through `SFM3D8` surface elements | its face-pressure result | 7 digits |
| circular, pipe, box and planar beams; I, hexagonal and general sections as ccx's `U1` beam (cantilevers, a portal frame), general sections with a ccx profile (NAFEMS NL6); beam line loads; pinned, tied and hinged spans | beam theory, Euler buckling, the direct-stiffness frame, Abaqus' and NAFEMS' published answers | ≤ 2.4 % |
| Cook's membrane under a shear traction; a thick cylinder under a radial traction | published 23.96; Lamé | 0.12 %; 0.02 % |
| rigid couplings, `*MPC`s, connectors, BCs on coupled nodes, loads, connectors, `*MPC`s and rotations on `*TRANSFORM`ed nodes | the same model built another way (solids, hand-written equations, no transform) | ≤ 4e-5 of \|u\|, mostly exact |
| per-element `*DISTRIBUTION` orientations (a solid plate, a composite shell) | one `*ORIENTATION` per element | ≤ 3e-11 |
| a simply supported [0/90/0] plate as composite `S4R` (run as `S8R`) and `SC8R` (one `C3D8I` per ply); a [30/-60/45]s laminate's in-plane stiffness in the x-y and x-z planes (`S4R`, `SC8R`, `SC6R`) | classical lamination theory (Navier, A); Pagano's 3-D elasticity solution | 0.15 % (`S8R`, a/h = 100); 1.0 % / 2.3 % (plies, a/h = 100 / 10); A ≤ 2e-5 |
| thermal expansion (orthotropic, anisotropic, no initial temperatures) | α ΔT; analytic stress | ≤ 5e-6 |
| velocity / acceleration BCs; displacement BCs without an amplitude | their time integral; wave theory; Abaqus' default amplitudes | 5e-5 of the travel; wave stress ≈ 1 % on average; exact |
| preselected and default output, contact output | statics, wave theory | ≤ 0.005 % (static) |
| `CPS4I` / `CPE4I` cantilevers under an end couple (as `C3D8I` slabs) | beam theory (deflection, σ_xx = −My/I, σ_zz) | 4e-8 |
| pressure on a shell's `SPOS` / `SNEG` side and element-based `P` | Navier plate solution, each sign | 1.0 % |
| a bare `*KINEMATIC` (all DOFs); an assembly with a turned instance | `*RIGID BODY`; the same model written flat | exact |
| a rigid flat punch of `R3D4`, `R2D2` or `RAX2` elements or the same face as an analytical surface, also turned under NLGEOM and in explicit dynamics; a block tied to a turning rigid plate; pressure on rigid elements; `MASS` + `ROTARYI` on a rigid plate | ccx's penalty contact law; the punch given its motion node by node; p / k; spring frequencies | ≤ 8e-7 of \|u\|, mostly round-off |
| a faceted analytical sphere on a block (`--approximate`) | Hertz | 2.3 % (finite block, penalty contact) |

A **corpus of 1052 genuine Abaqus decks** — 1022 from about 180 public repositories (CAE
exports, UMAT and UEL decks, explicit and coupled models, …) and 30 NAFEMS benchmark decks of
the Abaqus 2017 documentation — is fetched on demand and run through convert → integrity check
→ ccx. On ccx 2.23 all 1052 convert with no dangling reference; **181 solve the deck's own
physics**; 65 more solve but stay out of that count — 14 load nothing in the source deck, 58
(8 of them also unloaded) solve a model with reduced physics, and two (one also reduced) converge to solutions
that are not the deck's (a part that only contact holds drifts away in ccx; a plate pushed far past
its buckling load, whose lowest factors ccx's `*BUCKLE` does not return) — and 221 mesh-only
decks are accepted. The other 585 need what ccx cannot run — mostly user materials (349) and
user elements (66). **30 benchmark decks are checked against their published answer**: 23
match Abaqus' result for the same mesh (within 0.5 % for temperatures and frequencies, 1 % for
stresses and displacements), 7 differ for reasons traced to ccx (its nodal extrapolation,
plane-stress slab, film integration, mass matrices, a coarse shell mesh, beam clamps, a coarse beam mesh). See
[testing](https://github.com/sandervdbroek/abq2ccx/blob/main/docs/testing.md#published-answers).

## How it works

```
read (+ *INCLUDE, *PARAMETER)  →  flatten *PART/*INSTANCE/*ASSEMBLY
  →  build the geometry (expand mesh generation)  →  plan deck-wide fixes
  →  translate card by card  →  settle *EQUATION dependents, audit loads  →  write
```

| Bucket | Action | Examples |
| --- | --- | --- |
| Supported | emitted as it is | `*PLASTIC`, `*CONTACT PAIR`, `*DENSITY` |
| Translated | a handler adjusts the keyword, parameters or data | `*ELASTIC`, `*SHELL SECTION`, `*STEP`, `*DSLOAD`, output cards |
| Equivalent | mapped to the CalculiX construct that does the same | `*MPC BEAM` → `*RIGID BODY`, connectors → `*EQUATION`s, tractions → `*CLOAD` |
| Dropped | organisational, no CalculiX meaning | `*PART`/`*INSTANCE`/`*ASSEMBLY` (flattened), `*PREPRINT` |
| Commented | no equivalent: kept as `**` comments with a warning | `*VISCOELASTIC`, `*CONNECTOR BEHAVIOR`, `*INERTIA RELIEF` |

The [architecture guide](https://github.com/sandervdbroek/abq2ccx/blob/main/docs/architecture.md) describes the pipeline and how to extend it.

## Limitations

* User subroutines (UMAT/VUMAT, UEL, DLOAD, DISP, …) do not run in stock ccx. Such cards are
  commented out, naming the ccx subroutine to port; a UMAT runs in a ccx built with it
  (`--abaqus-umat`), a VUMAT has no ccx interface.
* Cohesive and gasket elements run as thin continua (their traction-separation law is lost;
  warned). Abaqus general contact (`*CONTACT`; `--approximate`: contact pairs between the
  bodies), connector behaviours, inertia relief and materials such as viscoelasticity and
  concrete damaged plasticity have no equivalent and are flagged for remodelling; a deck that
  runs without them is flagged as reduced physics.
* ccx's own first-order elements are not Abaqus': its `CPE4`/`C3D8`/`CAX4` are plain 2×2(×2)
  integration, without Abaqus' selectively reduced volume terms (on a coarse bending mesh
  Abaqus' `CPE4` deflects 9–19 % more for ν 0–0.3), and its `CPS4` is a 3-D slab with a free
  thickness, not 2-D plane stress ([compatibility](https://github.com/sandervdbroek/abq2ccx/blob/main/docs/compatibility.md)).
* Explicit coupled temperature–displacement steps do not run; Riks steps, NLGEOM follower
  tractions and curved analytical rigid surfaces run only with `--approximate`.
* Contact is translated card by card, but ccx's penalty contact behaves differently from
  Abaqus' — check it.
* ccx 2.23 gets some valid input wrong without an error. The converter works around what it
  can and warns about the rest ([compatibility](https://github.com/sandervdbroek/abq2ccx/blob/main/docs/compatibility.md),
  [troubleshooting](https://github.com/sandervdbroek/abq2ccx/blob/main/docs/troubleshooting.md)).
* The converter checks structure, and physics on its benchmarks — not on your model. Run ccx
  and sanity-check the results.

Validated on CalculiX 2.23 (conda-forge's `calculix` 2.23 build 2); written for 2.22–2.23.

## Examples

| File | Exercises |
| --- | --- |
| [`nle10_thickplate`](https://github.com/sandervdbroek/abq2ccx/blob/main/examples/nle10_thickplate.inp) | NAFEMS LE10: C3D20, `*NCOPY` + `*ELGEN`, `GEN`/`PERT`, `*DLOAD Px` |
| [`nle10_surface_elements`](https://github.com/sandervdbroek/abq2ccx/blob/main/examples/nle10_surface_elements.inp) | the same plate loaded through an `SFM3D8` skin → nodal forces |
| [`composite_shell`](https://github.com/sandervdbroek/abq2ccx/blob/main/examples/composite_shell.inp) | S8R composite layup, orthotropic, `*ORIENTATION`, `ENCASTRE`, `*DSLOAD` |
| [`composite_plate_s4r`](https://github.com/sandervdbroek/abq2ccx/blob/main/examples/composite_plate_s4r.inp), [`composite_plate_sc8r`](https://github.com/sandervdbroek/abq2ccx/blob/main/examples/composite_plate_sc8r.inp) | a simply supported cross-ply plate: composite `S4R` → `S8R`; composite `SC8R` → one `C3D8I` per ply |
| [`composite_inplane_s4r`](https://github.com/sandervdbroek/abq2ccx/blob/main/examples/composite_inplane_s4r.inp), [`composite_inplane_sc8r`](https://github.com/sandervdbroek/abq2ccx/blob/main/examples/composite_inplane_sc8r.inp) | an angle-ply laminate's in-plane stiffness; BCs interpolated onto the new nodes |
| [`assembly_two_blocks`](https://github.com/sandervdbroek/abq2ccx/blob/main/examples/assembly_two_blocks.inp) | two-instance assembly, an `instance.node` reference in a step |
| [`beam_circ_cantilever`](https://github.com/sandervdbroek/abq2ccx/blob/main/examples/beam_circ_cantilever.inp) | `B31` + `SECTION=CIRC` → `B32R` with midside nodes, radius → diameters |
| [`beam_pipe_box_cantilever`](https://github.com/sandervdbroek/abq2ccx/blob/main/examples/beam_pipe_box_cantilever.inp) | `PIPE31` + `SECTION=PIPE` and `B32` + `SECTION=BOX` → `B32R` |
| [`beam_circ_rotation_bcs`](https://github.com/sandervdbroek/abq2ccx/blob/main/examples/beam_circ_rotation_bcs.inp) | circular-section beams with a held twist and a prescribed rotation → knot beams |
| [`beam_circ_explicit`](https://github.com/sandervdbroek/abq2ccx/blob/main/examples/beam_circ_explicit.inp) | a circular-section beam in `*DYNAMIC, EXPLICIT` → a maximum time increment |
| [`planar_pinned_beam`](https://github.com/sandervdbroek/abq2ccx/blob/main/examples/planar_pinned_beam.inp), [`planar_pinned_circ_beam`](https://github.com/sandervdbroek/abq2ccx/blob/main/examples/planar_pinned_circ_beam.inp) | planar `B21` beams in `*FREQUENCY` + `*BUCKLE` → planar constraint |
| [`planar_b22_two_elements`](https://github.com/sandervdbroek/abq2ccx/blob/main/examples/planar_b22_two_elements.inp) | two `B22` → `B32R`, integrated along the beam as Abaqus does |
| [`beam_line_load_cantilever`](https://github.com/sandervdbroek/abq2ccx/blob/main/examples/beam_line_load_cantilever.inp) | `*DLOAD PY` / `P2` / `PZ` on `B31`, `B32` and a `CIRC` beam → nodal forces |
| [`beam_output_requests`](https://github.com/sandervdbroek/abq2ccx/blob/main/examples/beam_output_requests.inp) | output at `B32` nodes → `OUTPUT=2D`, `*NODE PRINT`, `*TIME POINTS` |
| [`coupling_shell_plate`](https://github.com/sandervdbroek/abq2ccx/blob/main/examples/coupling_shell_plate.inp), [`coupling_solid_plate`](https://github.com/sandervdbroek/abq2ccx/blob/main/examples/coupling_solid_plate.inp) | a rigid coupling on `S8R` nodes (knot beams) and its `C3D20R` reference |
| [`coupling_bc_bars`](https://github.com/sandervdbroek/abq2ccx/blob/main/examples/coupling_bc_bars.inp) | BCs on coupled nodes that the reference point imposes → taken off |
| [`rigid_body_bc_bars`](https://github.com/sandervdbroek/abq2ccx/blob/main/examples/rigid_body_bc_bars.inp) | BCs on `*RIGID BODY` nodes → moved to the reference node, as Abaqus does |
| [`equation_overconstraint`](https://github.com/sandervdbroek/abq2ccx/blob/main/examples/equation_overconstraint.inp) | an `*EQUATION` on a BC'd DOF, a duplicate and a loop of ties |
| [`mpc_beam_lever`](https://github.com/sandervdbroek/abq2ccx/blob/main/examples/mpc_beam_lever.inp), [`mpc_pin_tie_joints`](https://github.com/sandervdbroek/abq2ccx/blob/main/examples/mpc_pin_tie_joints.inp), [`mpc_link`](https://github.com/sandervdbroek/abq2ccx/blob/main/examples/mpc_link.inp) | `*MPC BEAM`, `PIN`, `TIE`, `LINK` |
| [`connector_hinge_beams`](https://github.com/sandervdbroek/abq2ccx/blob/main/examples/connector_hinge_beams.inp), [`connector_hinge_bodies`](https://github.com/sandervdbroek/abq2ccx/blob/main/examples/connector_hinge_bodies.inp), [`connector_ground_hinge`](https://github.com/sandervdbroek/abq2ccx/blob/main/examples/connector_ground_hinge.inp) | `CONN3D2` `HINGE` connectors between beams, rigid bodies and to ground |
| [`connector_transform_plate`](https://github.com/sandervdbroek/abq2ccx/blob/main/examples/connector_transform_plate.inp), [`connector_transform_join`](https://github.com/sandervdbroek/abq2ccx/blob/main/examples/connector_transform_join.inp) | `JOIN` / `LINK` connectors on nodes with a `*TRANSFORM` |
| [`mpc_transform`](https://github.com/sandervdbroek/abq2ccx/blob/main/examples/mpc_transform.inp) | `*MPC` `PIN`, `TIE` and `LINK` on nodes with a `*TRANSFORM` → local DOFs, twin nodes |
| [`op_new_respecify`](https://github.com/sandervdbroek/abq2ccx/blob/main/examples/op_new_respecify.inp), [`op_new_remove`](https://github.com/sandervdbroek/abq2ccx/blob/main/examples/op_new_remove.inp) | `*BOUNDARY, OP=NEW` after rotational BCs on beams and shells |
| [`distribution_solid_plate`](https://github.com/sandervdbroek/abq2ccx/blob/main/examples/distribution_solid_plate.inp), [`distribution_shell_plate`](https://github.com/sandervdbroek/abq2ccx/blob/main/examples/distribution_shell_plate.inp) | per-element `*DISTRIBUTION` orientations (solid, composite S8R); `*_explicit` are their one-orientation-per-element twins |
| [`thermal_expansion_cubes`](https://github.com/sandervdbroek/abq2ccx/blob/main/examples/thermal_expansion_cubes.inp) | isotropic `*Elastic` beside ORTHO / ANISO `*Expansion` |
| [`thermal_no_initial_temperature`](https://github.com/sandervdbroek/abq2ccx/blob/main/examples/thermal_no_initial_temperature.inp) | `*Temperature` without initial temperatures |
| [`cook_membrane_traction`](https://github.com/sandervdbroek/abq2ccx/blob/main/examples/cook_membrane_traction.inp), [`cylinder_traction_cax`](https://github.com/sandervdbroek/abq2ccx/blob/main/examples/cylinder_traction_cax.inp) | `*DSLOAD TRVEC` on `CPS8` and `CAX8` edges → nodal forces |
| [`traction_transformed_face`](https://github.com/sandervdbroek/abq2ccx/blob/main/examples/traction_transformed_face.inp), [`transform_spherical_rigid`](https://github.com/sandervdbroek/abq2ccx/blob/main/examples/transform_spherical_rigid.inp) | loads on `*TRANSFORM`ed nodes; a spherical transform; a transformed rigid-body reference point |
| [`transform_rotations`](https://github.com/sandervdbroek/abq2ccx/blob/main/examples/transform_rotations.inp) | rotational BCs and moments on a transformed kinematic reference point (→ `*RIGID BODY` with a `ROT NODE` in its axes) and beam tip (→ knot, global components) |
| [`velocity_bc_column`](https://github.com/sandervdbroek/abq2ccx/blob/main/examples/velocity_bc_column.inp), [`velocity_bc_bar`](https://github.com/sandervdbroek/abq2ccx/blob/main/examples/velocity_bc_bar.inp) | `*BOUNDARY, TYPE=VELOCITY` (implicit and explicit) |
| [`default_amplitude_bars`](https://github.com/sandervdbroek/abq2ccx/blob/main/examples/default_amplitude_bars.inp) | a displacement `*BOUNDARY` and a `*CLOAD` without an amplitude → ramped / stepped as in Abaqus (run as `*DYNAMIC`, `*VISCO`, coupled and explicit) |
| [`preselect_output_bar`](https://github.com/sandervdbroek/abq2ccx/blob/main/examples/preselect_output_bar.inp), [`explicit_default_output_bar`](https://github.com/sandervdbroek/abq2ccx/blob/main/examples/explicit_default_output_bar.inp), [`preselect_contact_blocks`](https://github.com/sandervdbroek/abq2ccx/blob/main/examples/preselect_contact_blocks.inp) | Abaqus' preselected and default output |
| [`cps4i_slab_bending`](https://github.com/sandervdbroek/abq2ccx/blob/main/examples/cps4i_slab_bending.inp) | a `CPS4I` cantilever under an end couple → `C3D8I` slabs (also run as `CPE4I`) |
| [`shell_pressure_sides`](https://github.com/sandervdbroek/abq2ccx/blob/main/examples/shell_pressure_sides.inp) | `*DSLOAD P` on a shell's `SPOS` / `SNEG` side and an element-based `P` |
| [`kinematic_all_dofs`](https://github.com/sandervdbroek/abq2ccx/blob/main/examples/kinematic_all_dofs.inp) | a bare `*Coupling` + `*Kinematic` (all DOFs) on a solid face, against `*RIGID BODY` |
| [`assembly_rotated_instances`](https://github.com/sandervdbroek/abq2ccx/blob/main/examples/assembly_rotated_instances.inp), [`…_flat`](https://github.com/sandervdbroek/abq2ccx/blob/main/examples/assembly_rotated_instances_flat.inp) | a turned instance with an oriented orthotropic material, against the same model written flat |
| [`damage_johnson_cook_cubes`](https://github.com/sandervdbroek/abq2ccx/blob/main/examples/damage_johnson_cook_cubes.inp) | a Johnson-Cook `*DAMAGE INITIATION` → ccx's form, reporting `DUCT` |
| [`rigid_punch_block`](https://github.com/sandervdbroek/abq2ccx/blob/main/examples/rigid_punch_block.inp), [`rigid_punch_cylinder`](https://github.com/sandervdbroek/abq2ccx/blob/main/examples/rigid_punch_cylinder.inp), [`rigid_body_inertia`](https://github.com/sandervdbroek/abq2ccx/blob/main/examples/rigid_body_inertia.inp) | a rigid `R3D4` punch and the same face as an analytical `CYLINDER` → skins of their rigid body; `MASS` + `ROTARYI` on a rigid plate → point masses |
| [`coverage_kitchen_sink`](https://github.com/sandervdbroek/abq2ccx/blob/main/examples/coverage_kitchen_sink.inp) | element substitutions, dropped and commented cards, output-variable mapping |

## Tests

```bash
python tests/test_convert.py                            # unit tests, no solver needed
python validate_with_ccx.py                             # end-to-end checks in CalculiX
python corpus/fetch.py && python tests/test_corpus.py   # the corpus
```

[Testing](https://github.com/sandervdbroek/abq2ccx/blob/main/docs/testing.md) describes the three layers; GitHub Actions run the first two on
every push, the unit tests on Linux, macOS and Windows and the CalculiX checks on Linux and
Windows.

## Documentation

* [User guide](https://github.com/sandervdbroek/abq2ccx/blob/main/docs/user-guide.md) — options, workflow, reading the report, the Python API.
* [Troubleshooting](https://github.com/sandervdbroek/abq2ccx/blob/main/docs/troubleshooting.md) — ccx errors and results that look wrong.
* [Compatibility](https://github.com/sandervdbroek/abq2ccx/blob/main/docs/compatibility.md) — the Abaqus/CalculiX facts the converter relies
  on, ccx 2.23 issues, and what does not convert.
* [Testing](https://github.com/sandervdbroek/abq2ccx/blob/main/docs/testing.md) · [Architecture](https://github.com/sandervdbroek/abq2ccx/blob/main/docs/architecture.md) ·
  [Changelog](https://github.com/sandervdbroek/abq2ccx/blob/main/CHANGELOG.md)
* Generated references: [keywords](https://github.com/sandervdbroek/abq2ccx/blob/main/docs/keyword-reference.md) ·
  [elements](https://github.com/sandervdbroek/abq2ccx/blob/main/docs/element-reference.md) · [output variables](https://github.com/sandervdbroek/abq2ccx/blob/main/docs/output-reference.md)

## Sources

* CalculiX CrunchiX User's Manual v2.23 — <https://www.dhondt.de/ccx_2.23.pdf>, v2.22 —
  <https://www.dhondt.de/ccx_2.22.pdf>, v2.7 (HTML) —
  <https://web.mit.edu/calculix_v2.7/CalculiX/ccx_2.7/doc/ccx/ccx.html>
* `calculix/new_keywords` (Abaqus↔CalculiX keyword delta) — <https://github.com/calculix/new_keywords>
* `calculix/cae` (CalculiX keyword model) — <https://github.com/calculix/cae>
* "A Guide to Modifying Abaqus Input Files for Use in CalculiX" —
  <https://calculix.discourse.group/t/a-guide-to-modifying-abaqus-input-files-for-use-in-calculix/1430>
* CalculiX Discourse — <https://calculix.discourse.group/> · PrePoMax forum —
  <https://prepomax.discourse.group/>

[Compatibility](https://github.com/sandervdbroek/abq2ccx/blob/main/docs/compatibility.md#sources) lists the Abaqus manual pages behind
individual facts.

## License

[MIT](https://github.com/sandervdbroek/abq2ccx/blob/main/LICENSE) © Sander van den Broek. `abq2ccx` is an independent tool, not affiliated
with or endorsed by Dassault Systèmes (Abaqus) or the CalculiX project. The test corpus is
fetched on demand and **not** redistributed here; each deck keeps its own upstream license,
recorded in [`corpus/manifest.py`](https://github.com/sandervdbroek/abq2ccx/blob/main/corpus/manifest.py).
