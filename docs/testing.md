# Testing

| Layer | Command | Needs | Checks |
| --- | --- | --- | --- |
| Unit tests | `python tests/test_convert.py` (or `pytest tests/`) | nothing | exact conversion behaviour on small inline decks and the bundled examples |
| End-to-end | `python validate_with_ccx.py` | CalculiX | the converted examples solve and match independent references |
| Corpus | `python corpus/fetch.py`, then `python tests/test_corpus.py` | network once; CalculiX for the solve test | 1052 real decks convert cleanly, keep their loads and solve; 26 of Abaqus' NAFEMS benchmark decks give their published answer |

Each layer skips cleanly when its prerequisite is missing, so the unit tests always run
offline. Before handing over a change, run all three and check that
`python docs/generate_reference.py` leaves `git diff` empty (the reference docs are
generated: edit the generator, not the `.md`). The corpus solve test runs every gated deck
in ccx and takes about ten minutes; run ccx under a file-size cap (`ulimit -f 4194304`) so
that a runaway job cannot fill the disk.

**CI.** GitHub Actions ([`ci.yml`](../.github/workflows/ci.yml)) run on every push and pull
request: the unit tests, the generated-reference check and a `pip install .` on Ubuntu, macOS
and Windows with Python 3.9 (the oldest supported) and the newest; and `validate_with_ccx.py`
and an `abq2ccx --run` on Ubuntu and on Windows (there on Python 3.9, whose `open()` defaults
to the code page) with conda-forge's `calculix` 2.23 build 2, the build FreeCAD 1.1.4 bundles
(`conda-meta/calculix-2.23-pl5321h484372f_2.json` in its macOS app; on Windows built by MinGW
GCC against the UCRT), so CI solves with the ccx the checks were written on (Ubuntu packages
2.21; later conda-forge builds of 2.23 add fixes made after its release). The two runs agree
to every printed digit except how NaN is spelled (`-NAN` on Linux, `-NAN(IND)` on Windows)
and the sixth digit of one buckling factor. ARPACK converges it only to `*BUCKLE`'s default
accuracy of 1 %, so each platform's BLAS lands on its own value: 223458 on Linux, 223460 on
Windows, 223459 on macOS. The corpus stays local: it downloads 1052 decks and needs ten
minutes of ccx.

## 1. Unit tests — `tests/test_convert.py`

Each test converts a small inline deck (`convert_str(text)`) or a bundled example and
asserts the exact output; the test names say what they check, and the run lists them.
They cover:

* **Input syntax** — keyword-line continuations, `*PARAMETER` arithmetic (a safe AST
  evaluator, not `eval`), `INPUT=` files, abbreviations, Fortran `D` exponents, blank-less
  keywords, blank data fields kept in place.
* **Mesh generation and assemblies** — `*NGEN`/`*NFILL`/`*NCOPY`/`*ELGEN`/`*ELCOPY`
  (curves, bias, reflection), `*NMAP`, instance transforms (translation before rotation),
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
  transient coupled steps, explicit defaults, Riks, analytic amplitudes, transient heat-transfer
  increments.
* **Reduced physics** — the record of what a conversion drops or replaces
  (`Converter.reduced_physics`), and what does not count (exact substitutions, output
  requests, numerical controls); `*NODE, SYSTEM=` coordinates and `*NODE` normals.
* **Output** — the `.frd`/`.dat` mapping, output frequencies, preselected field and contact
  output, ccx's label lists, `ENER` from the first step, `*EL FILE` labels ccx cannot write.
* **`--run`** — the `.frd`/`.dat` readers and the results digest on a cut-down job in ccx's
  formats (`tests/fixtures/digest`), the ccx version check, an assembly's instance map
  (offsets, renamed sets, the capped listing) and `--json`.

Every bundled example is also converted and checked for referential consistency: no
dangling set, surface, material, orientation or amplitude reference.

## 2. End-to-end — `validate_with_ccx.py`

Converts the examples, runs them in CalculiX (found as `--run` finds it: `$CCX`, `PATH`,
FreeCAD, PrePoMax and bConverged installs, Homebrew/MacPorts) and compares the results with
references that do not come from the converter. It prints one `PASS`/`FAIL` line per check.
Each check reads something ccx must solve for (a free node's motion, a reaction, a stress, an
eigenvalue), and a run counts as solved only if the solve judge (below) finds each step
setting up its system: ccx 2.23 ends a step that sets up none with "Job finished".

| Example | Check | Reference | Agreement |
| --- | --- | --- | --- |
| `nle10_thickplate` | NAFEMS LE10 σyy at point D | published −5.38 MPa | −5.650 MPa, 5 % (element and mesh) |
| `nle10_surface_elements` | the same pressure on an `SFM3D8` skin (`*DSLOAD P` on `SPOS`, element `P`, `TRVEC`) | the face-pressure result | 7 digits |
| `beam_circ_cantilever`, `beam_pipe_box_cantilever` | tip deflection of `CIRC`, `PIPE` and `BOX` cantilevers | P L³ / 3 E I | ≤ 1.0 % |
| `beam_u1_general`, `beam_u1_ibeam`, `beam_u1_unsymmetric_i`, `beam_u1_hex`, `beam_u1_portal` | `U1` beams: a general section with I12 ≠ 0 (tip forces along y and z, a torque, frequencies), an I-section in space (`--approximate`; against the `RECT` it would otherwise get: weak axis 68× too flexible), the unsymmetric I and hexagonal-tube cantilevers of Abaqus' Verification Guide, a planar I-section portal frame under gravity, a line load and a lateral load | unsymmetric bending theory, T L / G J, Euler–Bernoulli frequencies; Abaqus' reference values (0.8931, 1.786e-2; 0.3489, 6.978e-3); the direct-stiffness frame | 1e-6 statics (the frame 2e-7); frequencies ≤ 0.5 % (rotary inertia) |
| `beam_general_rect`, `beam_general_rect_nl6` | `*BEAM GENERAL SECTION, SECTION=RECT` as ccx's rectangular beam: a cantilever in space; NAFEMS NL6 (NLGEOM, past buckling) on 32 `B22` | P L³ / 3 E I; NL6's published answers | 0.05 %; ≤ 2.4 % |
| `beam_circ_rotation_bcs` | a held twist at pinned supports; a prescribed tip rotation | beam theory | ≤ 0.3 % |
| `beam_circ_explicit` | a circular-section beam in `*DYNAMIC, EXPLICIT`; without the converter's increment cap it diverges | beam theory; the solve judge | 0.7 %; judged nonfinite, the NaN found in the `.dat` and in the `.frd` |
| `planar_pinned_beam`, `planar_pinned_circ_beam` | first two frequencies and the buckling load of planar `B21` beams | beam theory, Euler | ≤ 0.8 % |
| `planar_b22_two_elements` | two `B22` (→ `B32R`) between pins: mid-span deflection, first frequency, buckling load | Abaqus' deflection on this mesh (exact), beam theory, Euler | 0.15 %; ≤ 1.3 % |
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
| `thermal_expansion_elastic_forms` | isotropic, orthotropic, engineering-constants and anisotropic `*Elastic` beside an ANISO `*Expansion`, turned and not; also NLGEOM | α ΔT; clamped stress −C α ΔT | ≤ 1e-5; 1e-2 NLGEOM |
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
| `assembly_rotated_instances` (also `_nodes`, `_nodes_no_c`) | a turned instance with an oriented orthotropic material (the part's orientation by coordinates, or by nodes with and without node c), instance-qualified loads, a surface pressure | the same model written flat by hand | exact (coordinates and displacements; by nodes before: 9 % of \|u\|) |
| `pretension_node_set` (also `_part`, `_assembly`), `pretension_element_set` (generated) | a `C3D8` bolt whose `*PRE-TENSION SECTION` names its node by a one-node set (also two instances, one turned, of a part with the card, or with assembly-level cards naming `I1.PT` and an assembly set); a `B31` bolt naming its cut element and node by sets | F L / E A; the card with `ELEMENT=1, NODE=99` | 1e-6; exact (ccx stopped on the set names) |
| `damage_johnson_cook_cubes` | a Johnson-Cook `*DAMAGE INITIATION`: ccx's indicator `DUCT` (from `JCCRT`) in uniaxial tension; the run with the card against the run without | PEEQ / (d1 + d2 e^(−d3/3)); identical results | 5e-7; exact |
| `rigid_punch_block`, `rigid_punch_cylinder`, and generated plane and axisymmetric twins | a rigid flat punch of `R3D4`, `R2D2` or `RAX2` elements, or the same face as a `CYLINDER` / `SEGMENTS` analytical surface | ccx's penalty law A d / (L/E′ + 1/K); the punch given its motion node by node (the block top must move) | 2e-7; ≤ 1e-14 |
| the same punches turned under NLGEOM (0.05 rad; plane 0.03 rad) | rigid skins and analytical surfaces | the punch given the exact motion | ≤ 8e-7 of \|u\| |
| a block tied to a turning rigid plate (`R3D4`, `CYLINDER`) | a `*TIE` to a rigid surface, NLGEOM | its top given the exact motion | 1.8e-7 (ccx's own tie: 1.3e-2) |
| `rigid_body_inertia` | `MASS` + `ROTARYI` of an `R3D4` plate on springs | its translation and rotation frequencies | 1.9e-7 |
| a faceted analytical sphere (`--approximate`) | the indentation force on a block | Hertz | 2.3 % (finite block, penalty contact) |
| the plane punch in explicit dynamics | `R2D2` skins at the increment the converter caps (ccx leaves this contact out of its estimate) | the punch given its motion node by node at that increment | exact |
| a rigid `R2D2` segment and an `R3D4` facet on a spring | an element pressure `P` (on the `R2D2`: per unit depth) | p / k | exact |
| a stretched cube with a `*USER MATERIAL` | named `UserMat` and `JohnsonCook_Steel` (renamed); with `--abaqus-umat`, small strain and NLGEOM | ccx stops: "no user material subroutine"; ccx's example UMAT: E ε, E ln(1 + ε) | —; exact; 1e-7 |
| `planar_pinned_beam`, `beam_circ_cantilever`, `assembly_two_blocks` | the `--run` results digest: frequencies and buckling load, largest \|U\| (near the tip node of the expanded beam), the reaction at each support under its Abaqus name | the references above; statics (the applied load) | as above; 6 digits |
| `composite_plate_s4r` | a simply supported [0/90/0] plate as composite `S4R` (run as `S8R`), a/h = 100, sinusoidal load | classical lamination theory (Navier) | 0.15 % |
| `composite_plate_sc8r` | the same plate as `SC8R` (one `C3D8I` per ply), a/h = 100 and 10; numbered so that `STACK DIRECTION=1` is the thickness | Pagano's 3-D elasticity solution; `STACK DIRECTION=3` | 0.96 %, 2.3 %; exact |
| `composite_inplane_s4r`, `composite_inplane_sc8r` (and `SC6R` wedges) | a [30/-60/45]s laminate under three uniform strains, in the x-y and the x-z plane | classical lamination theory's A11 … A66 | ≤ 2e-5 (`S8R`), 1.5e-7 (plies) |
| `shell_axes_*` (generated) | an orthotropic ply on plain `S4R` shells and `M3D4`, `M3D8R` and `M3D6` membranes under three uniform strains, an orientation turned about its axis 1 (and a membrane without one) in the x-y, x-z and y-z planes, and the plate's axes without a rotation line (Abaqus: direction 1 = axis 2) | the ply's t Q̄ at Abaqus' direction | 3e-7 (ccx alone: 0.7–1.0 off) |
| `quad_membrane_*` (generated) | strips of `M3D8R`, `M3D8`, `M3D6` and `M3D9R` (thickness 0.1) in uniaxial tension, also under NLGEOM at a stretch of 1.2; a sphere octant of `M3D8R` and `M3D6` (t/R 0.01) under internal pressure | uniaxial stress (ν 0.3); the St. Venant-Kirchhoff bar; thin-wall theory | exact; 2e-16; 0.39 % (ccx alone: 6.5 % to 3e13 off, or no solution) |
| `sheet_pressure_*` (generated) | pressure on sphere octants of `S8R`, `S6`, `S4R`, `M3D4`, `M3D8R`, `M3D6` and a half cylinder of `S8R`, t/R 0.1: `*DLOAD P` (also on two sets in one card), `*DSLOAD` on `SNEG` / `SPOS`, `OFFSET=SPOS`, NLGEOM | the reaction: p × the reference surface's projected area (sphere: × 1 + (t/2R)², the split's residual); thin-wall theory | ≤ 0.02 % (linear elements 0.2 %); ≤ 0.3 % (ccx alone: 5–19 % off) |
| `cylinder_hoop` (generated) | a cylindrical orientation on an `S4` cylinder under internal pressure, also turned about its axis 3 | thin-wall theory, fibres along the hoop | 0.35 % (ccx alone: 14× too soft) |
| `distribution_panel_*` (generated) | a variable-angle-tow `S8R` strip whose `*DISTRIBUTION` b leaves the plate by 30°, in the x-y, x-z and y-z planes | the x-y strip with b in the plate | 7e-12 (ccx alone: 3.3e-2) |
| `sc_axes_*` (generated) | the ply as a plain `SC8R` / `SC6R` section, thickness free: the orientation turned about its axis 1 in the x-y, x-z and y-z planes (also as a `*DISTRIBUTION`), the plate axes without a rotation line, none in x-z and y-z; an anisotropic ply stacked downwards | the ply's t Q̄ at Abaqus' direction; the anisotropic ply's plane-stress stiffness in Abaqus' axes | 3e-7 (ccx alone: 4e-2–0.99 off) |
| `sc_cylinder_hoop` (generated) | a cylindrical orientation on an `SC8R` cylinder under internal pressure | thin-wall theory, fibres along the hoop | 0.10 % (ccx alone: 14× too soft) |
| `sc_cylinder_stack_*` (generated) | an `SC8R` cylinder numbered radially along the elements' direction 1, `STACK DIRECTION=ORIENTATION` with a cylindrical orientation without a rotation line, as `[0/90/0]` plies and as one layer, under an axial strain | the wall's membrane stiffness, plies stacked radially | 3e-6, 2e-5 (stacked along axis 3: 13×, 2.5× too soft) |
| `sphere_hoop_*` (generated) | a spherical orientation on a sphere (t/R 0.01) of plain `S4R` shells (also turned about its axis 3), plain `SC8R` continuum shells and `[0/90/0]` `SC8R` plies under internal pressure; `_iso`: isotropic `S4R` and `SC8R` (stacked along the orientation) with element stresses printed | membrane theory, fibres along the parallels, colatitudes 30–150° | 1.2 % (ccx loads the shells' inner face, 1 % short), 0.35 %, 0.34 % of the largest displacement (ccx alone: 113–210 %); `_iso` 0.53 % (main's rectangular card: NaN stresses) |
| `initial_stress_turned`, `initial_plastic_turned`, `initial_stress_cylindrical`, `initial_stress_plane_stress` (generated) | an initial stress and a plastic strain (engineering shear) in a turned rectangular orientation on a free `C3D8` cube; a uniform hoop stress in a cylindrical one on a plane-strain `C3D20R` quarter annulus; an initial S12 on a `CPS4` square | the cube's strains −C⁻¹RσRᵀ and Rε_pRᵀ; the closed-form radial displacement; −τ/G | round-off; 1.6e-6 (before: 158 %, 100 %, 130 % off; S12 lost) |
| `initial_stress_sc8r`, `_sc6r`, `_sc8r_oriented`, `initial_plastic_sc8r`, `initial_stress_sc8r_plies`, `_sc6r_plies_oriented` (generated) | a free `SC8R` / `SC6R` plate off the x-y plane with an initial S11, S22, S12 or PE11, PE22, PE12 in Abaqus' shell axes (global X projected, or a projected orientation); `[0/90/0]` plies with an initial S11, S22 = Q(e, e) in each ply's axes | the strains −C⁻¹RσRᵀ, Rε_pRᵀ; one uniform strain, −e in the plane | 2.4e-6 (before: 55 % to 13× off) |
| `deformation_plasticity_*` (generated) | a `*DEFORMATION PLASTICITY` bar of `C3D8` / `C3D20R` past yield on a turned, a cylindrical and a spherical orientation | the same bar without an orientation | identical (before: `C3D20R` 84 % off) |
| `deformation_plasticity_small_strain`, `_nlgeom_no` (generated) | a free `C3D8` cube of that steel pulled to 2σ0 in a small-strain step (`*Step`, `*Step, nlgeom=NO`) | ccx's law: Ramberg-Osgood in the logarithmic strain and the Cauchy stress (reduced physics: 12 % past Abaqus' small-strain law) | 2e-6 (`NLGEOM=NO` kept: 17 % off) |
| `planar_coupled_tip` (generated) | a `B21` cantilever loaded through a kinematic `*COUPLING` at its tip | the cantilever loaded at the tip | 1.1e-5 (the knot beam), in plane (the converter stopped) |
| `coupled_velocity_card` (generated) | a rigid face given its reference node's velocity by a second `TYPE=VELOCITY` card | v t | exact (ccx stopped: "dependent side of a MPC and a SPC") |
| `amplitude_close_times_*` (generated) | a cube pulled through an `EQUALLY SPACED` and a `SMOOTH STEP` amplitude rising from total time 100 to 100.0002 | the amplitude at four fixed increments | 1e-6 (6 digits: the full load at each) |
| `kinematic_dynamic_linear`, `_nlgeom`, `_some_dofs`, `_explicit` (generated) | a column's top face kinematically coupled (all or two translations) to a node that moves and turns over a slow `*DYNAMIC` step: linear, NLGEOM, explicit | ccx's own coupling in a slow `*STATIC` step (the static limit); the free middle nodes must move | 6e-5 to 3.5e-4, the dynamic effect (ccx's coupling: no equations, the middle nodes stayed at 0) |
| `rigid_dynamic_solid`, `_mpc`, `_shell`, `_planar` (generated) | a `*RIGID BODY` (`*MPC BEAM` lines) on a column's top face or a clamped `S4` / `CPS4` strip's tip edge, driven by a node that moves and turns over a slow linear `*DYNAMIC` step | the linear rigid motion u_ref + θ × d prescribed in a `*STATIC` step; the free nodes must move | 2.5e-6, 2.5e-6, 2.4e-4 (ccx's own shells in a dynamic step), 0 (ccx's `*RIGID BODY`: 7e-2, 7e-2, 1.7e-2, 4.5e-2) |
| `energy_dynamic`, `_after_frequency`, `energy_coupled` (generated) | a one-DOF cube pulled in a static step (also after a `*FREQUENCY` step), then let go in an implicit `*DYNAMIC` step or heated in a transient coupled temperature-displacement step | u0 cos ωt and ω / 2π; u0 + α ΔT L | 3.4e-4 of u0, 2.7e-7; exact (ccx stopped: energies first needed after step 1) |
| `el_file_u1_ener`, `el_file_depvar_sdv`, `el_file_carried_sdv`, `el_file_plastic_sdv` (generated) | a `U1` cantilever with `VARIABLE=ALL` (`ENER`); cubes with `S, SDV` requested: `*DEPVAR` in a linear static step, then (NLGEOM, or a plastic material) `*FREQUENCY` and `*STEADY STATE DYNAMICS` steps ccx carried `SDV` into | P L³ / 3 E I; 100 / E; the same decks without `SDV` | exact (ccx stopped / segfaulted) |
| `rigid_tie_symmetric_layup` (generated) | a `[0/90]s` `S4R` strip tied to a clamped rigid plate | the strip with its four plies listed | exact (half the thickness: 3.3× too soft) |
| `approximate_blank_nu` (generated) | `--approximate` beside an `*ELASTIC` row with a blank ν at the cube's temperature | uniaxial stress, ν 0 | exact (ν 0.475) |
| `assembly_bolts` (generated) | two instances, one turned, of a part with a `*PRE-TENSION SECTION` and a `*DISTRIBUTING COUPLING` | F L / E A, F / E A | 1e-6 (ccx stopped on the part's names) |
| `perturbation_restore_*` (generated) | cubes given a `*CLOAD`, a pressure, a prescribed displacement and a temperature, a `*FREQUENCY` (or `*STEP, PERTURBATION` + `*BUCKLE`) step changing them all (or, after a `*FREQUENCY` step, a `*MODAL DYNAMIC` one changing the loads), then a static step giving nothing | the first step's state; each cube's corner must move | exact (before: 0.49 off) |
| `modal_own_loads` (generated) | a cube loaded statically (a `*CLOAD`, a pressure, gravity, a traction), then `*FREQUENCY` and a `*MODAL DYNAMIC` step with loads of its own | the same deck without the static loads | exact (before: 0.013 off) |
| `buckle_gravity_preload` (generated) | a `C3D8` column under gravity in a static step, then a `*BUCKLE` step loaded at its top (`*STEP, PERTURBATION` and a plain `*STEP`) | the same gravity as nodal forces (exact on bricks) | exact (ccx aborted after the buckle step; the plain step ignored the preload) |
| `frequency_preload` (generated) | the `buckle_gravity_preload` column under gravity in a static step, then a `*FREQUENCY` step: with `NLGEOM` and a plain `*STEP`; without `NLGEOM` and `*STEP, PERTURBATION` | the same written with `PERTURBATION`; the unloaded column | exact (before: 25.02 Hz for 20.74, 20.74 for 25.02) |
| `buckle_self_weight_then_static` (generated) | the column buckling under its weight and a top load, then a static step pulling its top sideways | the buckle step alone; the static step alone | exact (ccx aborted after the static step) |
| `buckle_displacement` (generated) | a `C3D20R` column pushed down at its top in a `*STEP, PERTURBATION` `*BUCKLE` step; the same push as a static preload before a buckling step loaded at mid-height | the top tied and given the static reaction as a force; Euler | 2.4e-7; Euler 0.4 % (ccx 2.23 as written: 2.389 for 40.87, only the top moved) |
| `composite_shell`, `assembly_two_blocks` | accepted and solved; a node moves | — | — |

## 3. Corpus — `corpus/` and `tests/test_corpus.py`

[`corpus/manifest.py`](../corpus/manifest.py) lists 1052 genuine Abaqus decks: 1022 from
about 180 public repositories and 30 NAFEMS benchmark decks of the Abaqus 2017 documentation
([published answers](#published-answers)). They cover CAE exports with parts and
assemblies, UMAT/VUMAT and UEL decks, cohesive, explicit and coupled models, mesh-generation
cards, `*Parameter` decks, across composites, geotechnics, biomechanics, fracture, forming,
thermal analysis, FEA-tool test suites and teaching material. CalculiX-native decks are excluded on purpose: they would just
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
| `reference=dict(...)` | its published answer: the quantity and where ccx writes it (`read`), the NAFEMS `target`, Abaqus' result for the deck's mesh (`abaqus`), a tolerance (`tol`), the `source` page; `ccx` and `why` where ccx answers differently for a reason traced to ccx |

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
  crash message on stdout or stderr, runs analysis steps that each show a solve (the
  structure of the step's matrix or its number of equations), and writes only finite
  results to the `.dat` print blocks and the `.frd`; **unsolved** when a step shows none
  (ccx 2.23 runs a step that sets up no equations to "Job finished" and exit 0);
  **nonfinite** when it finishes with NaN/Inf (likewise for a diverged solution);
  **accepted** for a mesh-only deck that reads cleanly; **failed** otherwise.
* `test_classify_ccx_run` — the judge itself, including the "Job finished, then abort" case
  of issue #3, a `*DYNAMIC` step that sets up no equations (kinematic couplings), and
  NaN/Inf results as ccx 2.23 writes them, also as `-NAN(IND)` (a Windows
  build whose printf is the UCRT's, as conda-forge's is) and `1.#QNAN` and `-1.#IND` (msvcrt's).
* `test_corpus_references` — every `expect_solve` deck with a `reference` gives its
  published answer in ccx ([published answers](#published-answers)).
* `test_hood_hinge_keeps_one_mechanism_mode` — the hood-hinge deck's hinge leaves exactly
  one mechanism mode besides the six rigid-body modes.

**Results on ccx 2.23** (the FreeCAD 1.1.4 build): all 1052 decks convert with no dangling
reference. 232 are gated `expect_solve`: **189 solve the deck's own physics**; 14 are
`source_unloaded`, one is `solver_differs` (a snap-fit insert that only contact holds drifts
out of its buckle) and 31 (3 of them also unloaded) are `reduced_physics` — concrete damaged
plasticity (2), UHARD / VUHARD hardening (2), field-dependent elasticity set by USDFLD or a
user field (3), Chaboche back-stresses (3), `HOURGLASS=ENHANCED` (1), `CPE4H` (2),
`CPS6M`/`CPE6M` (4), `C3D10M`/`C3D10HS` (2), `STRI3` (2), linear circular-section beams run as
`B32R` (3), I-section `B21` beams run as ccx's Euler–Bernoulli `U1` (3), general contact (2), a
dropped `*IMPERFECTION` (1), planar beams whose eigenmodes include twist (1). 221 mesh-only
decks are accepted. The other 599 stop first on, or (the last row) run without, what they need:

| Decks | First blocker |
| ---: | --- |
| 353 | a user material (UMAT/VUMAT) |
| 66 | a user element (UEL) |
| 50 | an incomplete or invalid source deck (undefined sets or materials, external parameters, CAE fragments) |
| 34 | an explicit coupled temperature–displacement step (28), or `*MATRIX GENERATE` (6) |
| 27 | no convergence or divergence (19), or more than the gate's 300 s (8) |
| 16 | NLGEOM follower tractions (they convert with `--approximate`) |
| 19 | other ccx errors, one or a few decks each |
| 22 | an element type, beam section, user subroutine or physics ccx lacks (piezoelectric and infinite elements; I and general beam sections where ccx's `U1` beam cannot carry them; cohesive, acoustic, pore-pressure models) |
| 12 | Abaqus general contact (7), an XFEM crack (1), Hashin damage of composite plies (2) or the only path of the load, kinematic couplings of some translations in an explicit NLGEOM step (2): ccx has none of them, and the converted deck runs without it — not the deck's physics, so not gated |

Every one of them was checked to fail no worse than the original, unconverted deck. Fixing
a first error often only exposes a second, fundamental one behind it, so the converter aims
to translate or clearly flag each incompatibility rather than to make a deck run at any
cost.

### Published answers

30 decks are Abaqus' own benchmark decks: NAFEMS tests of the Abaqus 2017 Benchmarks Manual,
from the documentation mirror at abaqus-docs.mit.edu (Dassault Systèmes' decks, fetched on
demand and not redistributed). The 25 that run carry a `reference`, as does the corpus's copy
of Abaqus' LE1 `CPS3` deck: a quantity, where ccx writes it (a `.frd` nodal stress or
temperature, `.dat` eigenfrequencies, integration-point stresses or displacements), the
NAFEMS target and Abaqus' published result for the deck's own mesh. `test_corpus_references`
runs them in ccx and compares; `python tests/test_corpus.py` prints the comparison.

The yardstick is Abaqus' result for the same mesh: it has the same discretization error, so
the tolerance only covers what the two codes do differently with one mesh — ccx's
one-element-thick expansion of plane, shell and beam elements, its nodal extrapolation, the
digits Abaqus prints: 0.5 % for temperatures and frequencies, 1 % for stresses and
displacements. A conversion error moves an answer far more (NAFEMS T3 on ccx's own time
increments: −16 %). Where ccx answers differently for a reason traced to ccx and checked
independently, the entry records ccx's value and `why`: the check then holds ccx to that value
within the same tolerance, so a conversion change still shows, and fails once ccx reaches
Abaqus' value.

On ccx 2.23, 20 match Abaqus:

| Test | Element, mesh | Quantity | ccx | Abaqus | NAFEMS |
| --- | --- | --- | --- | --- | --- |
| LE1 | `CPS8`, `CPS8R`, `CPS6` fine; `CPS3` coarse | σyy at D, MPa | 92.79, 90.14, 94.36; 51.32 | 92.81, 90.07, 94.01; 51.04 | 92.7 |
| LE2 | `S8R`, 10° (`*NMAP`) | outer tangential stress at E | 59.78 | 59.7 | 60 |
| LE5 | `S8R` | σxx at A | −110.02 | −109.85 | −108 |
| LE10 | `C3D20R` fine; `C3D10` coarse, fine | σyy at D | −5.528; −5.448, −5.769 | −5.53; −5.44, −5.77 | −5.38 |
| T2 | `DC2D8`; `C3D8T` coupled | T at B, °C | 653.85 | 653.85 | 653.84 (927 K) |
| T3 | `DC2D8` fine, transient | T at 0.08 m, 32 s | 36.15 | 36.09 | 36.60 |
| T4 | `DC3D20` coarse | T at E | 17.895 | 17.89 | 18.3 |
| FV32 | `CPS8` | modes 1–6, Hz | ≤ 0.22 % off Abaqus | 44.636 … 391.55 | 44.623 … 391.44 |
| FV41, FV42 | `CAX8` | modes 2–6, 1–5 | all of Abaqus' digits | 243.50 …; 370.97 … | 243.53 …; 369.91 … |
| FV52 | `C3D20` | modes 4–10 | all of Abaqus' digits | 44.796 … 206.64 | 44.092 … 200.13 |
| NL1 | `CPE4R`, perfect and hardening plasticity | von Mises after each of 8 steps | Abaqus' 16 values (≤ 0.01 %) | 3.824 … 7.297 | 3.917 … 7.322 |
| NL2 | `CAX8R`, plasticity | σrr, σθθ at 8 Gauss radii, 80 and 160 MPa | ≤ 0.35 % off | the targets, but 95.8 for σθθ at r = 124.2 under 80 MPa | 98.5 there |
| NL6 | `B22`, NLGEOM | ux/L, uy/L after both load steps | −0.4503, 0.7242; −1.5818, 0.4231 | −0.447, 0.723; −1.577, 0.427 | −0.440, 0.719; −1.577, 0.421 |

Six differ for a reason traced to ccx:

| Test | Element | ccx | Abaqus | Why |
| --- | --- | --- | --- | --- |
| LE10 | `C3D20` coarse | −7.343 | −6.72 | ccx extrapolates a `C3D20`'s 27 integration-point stresses to the nodes by a least-squares fit of its 20 nodal functions, Abaqus through all 27 points: ccx's own integration-point stresses give −6.724 Abaqus' way |
| T1 | `CPS8` | 52.86 | 51.53 | ccx's plane-stress element is a slab with a free thickness (σzz = 2.8 MPa at D, the hot spot's edge); a 2-D plane-stress solution of the mesh gives 51.533 |
| T4 | `DC3D8` fine | 17.954 | 18.91 | ccx integrates `*FILM` consistently, Abaqus lumps it on first-order elements: a separate solution gives 17.954 and 18.914 |
| FV52 | `C3D8I` | 44.18 … 205.15 | 44.092 … 200.13 | Abaqus lumps first-order masses (Theory Guide, "Implicit dynamic analysis") and condenses the incompatible modes, which ccx keeps as DOFs with a consistent mass: a separate solution gives 44.12 … 156.5 Abaqus' way, 44.18 … 157.9 ccx's |
| FV12 | `S8R` | mode 9: 7.653 | 7.559 | ccx's `S8R` is a one-layer `C3D20R` solid: modes 4–8 within 0.26 %, mode 9 a coarse-mesh error (ccx: 7.375 at 8 × 8) |
| FV2 | `B22` | 11.34, 18.06, 45.90, 59.30 | 11.34, 17.68, 45.69, 57.75 | ccx's beam is a 3-D brick whose clamped or knotted end section cannot contract with Poisson's ratio (0.3): modes 2 and 10, whose arms the crossing clamps, come out 2–3 % stiff on 4 elements an arm (one such arm: 18.08, 59.63 Hz; with ν = 0 17.72, 58.45) |

The other five do not run in ccx 2.23: creep tests 1(a), 2(a) and 5(a) stop on a singular
matrix once an increment's creep strain is about 20 times the elastic one (Abaqus takes
increments of about 100 h; ccx is exact until it stops); FV4 stops in its `*FREQUENCY` step
("add_bo_st") because `*MASS` elements sit on `*RIGID BODY` members; NL5 stops at about 90°
of end rotation ("increment size smaller than minimum") on 8 or 32 elements, as `B32` or
`B32R`. These decks also found converter faults, fixed with them: `*NFILL` sets without their
bounding nodes, one `*EQUATION` card with several set equations, 2-D and axisymmetric
heat-transfer elements, `*NMAP`, `PERIODIC` amplitudes, and the increments and initial
temperatures of transient heat transfer.

### Adding a deck

Append an entry to `corpus/manifest.py` (name, raw URL, license, what it exercises), run
`python corpus/fetch.py`, then `python tests/test_corpus.py`. Gate a deck with
`expect_solve=True` only when it solves under its own loads (add `reduced_physics` with the
reason if the conversion report ends with "Reduced physics", and `solver_differs` if ccx's
results are not the deck's — a part that flies away, contact that never closes), and give a
non-solving deck a `note` with its first ccx error. A deck with a published answer gets a
`reference`.
