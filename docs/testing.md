# Testing

The converter has three layers of tests:

1. **Unit tests** — fast, no solver needed, run on small controlled fixtures and the
   bundled examples.
2. **End-to-end solver validation** — converts the example decks and runs them in
   CalculiX, checking the NAFEMS LE10 benchmark, circular-, pipe- and box-section
   cantilevers, circular-section beams with rotational BCs, and planar beams'
   frequencies and buckling loads numerically.
3. **Real-world corpus** — 1022 genuine Abaqus decks pulled from the internet, each
   converted and (optionally) solved in CalculiX.

```bash
python tests/test_convert.py     # 1. unit tests           (or: pytest tests/)
python validate_with_ccx.py      # 2. end-to-end (needs ccx/FreeCAD; skips if absent)
python corpus/fetch.py           # 3a. download the corpus (needs network)
python tests/test_corpus.py      # 3b. corpus convert + (if ccx) solve
```

Every layer skips cleanly when its prerequisite (CalculiX, or a fetched corpus) is
absent, so `python tests/test_convert.py` always runs offline.

## 1. Unit tests — `tests/test_convert.py` (138)

Small inline decks (`convert_str(...)`) and the bundled `examples/`, asserting exact
conversion behaviour and referential integrity.

| Test | What it checks |
| --- | --- |
| `test_le10_thickplate` | NAFEMS LE10 deck: `*NCOPY`→465 nodes, `*ELGEN`→48 C3D20, `GEN`/`PERT` handled, gappy `LOAD` set filtered, no dangling refs |
| `test_composite_shell` | S8R composite + orthotropic + `*ORIENTATION`, `ENCASTRE`→6 DOF, `*DSLOAD`→`*DLOAD`, synthesized ply orientations, `LE/PE`→`E/PEEQ` |
| `test_assembly_flatten` | two-instance `*ASSEMBLY` flattened to one global numbering; `instance.node` reference resolved to a global id |
| `test_solid_dof_flag` | `--solid-dof` expands `ENCASTRE` to translational DOFs 1–3 only |
| `test_comprehensive_coverage` | element substitutions, dropped/commented cards, and output-variable mapping in a single kitchen-sink deck |
| `test_element_substitutions` | `ccx_element_type()` mappings (e.g. `CPEG8→CPE8`, `STRI65→S6`) **and** the invariant that every substitution preserves node count |
| `test_nset_from_elset` | `*Nset, ELSET=…` expanded to the element set's nodes (ccx has no NSET-from-ELSET) |
| `test_overconstraint_warning` | a `*BOUNDARY` on an `*EQUATION` dependent DOF raises the pre-flight overconstraint warning |
| `test_tie_param_handling` | `*TIE` strips Abaqus-only `TYPE=`, keeps ccx-supported `ADJUST` |
| `test_instance_rotation_order` | `*INSTANCE` applies translation **then** rotation (`R(p+T)`), per the Abaqus manual |
| `test_shell_general_section` | `*SHELL GENERAL SECTION` → `*SHELL SECTION` |
| `test_step_nlgeom_and_name` | `*STEP` drops `NAME`, keeps `NLGEOM` |
| `test_amp_keyword_alias` | the `*AMP` abbreviation → `*AMPLITUDE` |
| `test_rigid_element_flagged` | `R3D3` rigid element flagged (model as `*RIGID BODY`) and emitted unchanged |
| `test_name_length_limit` | flattened instance set names kept within ccx's 80-character name limit (probed on ccx 2.22), but not truncated below it |
| `test_parameter_with_internal_comment` | a `**` comment inside a `*PARAMETER` block does **not** terminate it |
| `test_parameter_forward_reference` | `*PARAMETER` resolves regardless of definition order (`a = b*2; b = 3.`) |
| `test_no_residual_parameter_tokens` | no `<name>` tokens remain in the output after substitution |
| `test_fortran_d_exponent` | Fortran `D` exponents (`1.5D2`, `0.0d0`) parse as numbers |
| `test_keyword_line_continuation` | a keyword line ending in a comma continues onto the next line as parameters (`*ELSET, ELSET=X,` + `GENERATE`), but a stray comma on a `*NODE`/`*ELEMENT` header does **not** swallow the first data line |
| `test_coupled_temperature_element_suffix` | coupled temp-displacement elements drop the `T` suffix (`C3D8T→C3D8`, `CAX4RT→CAX4R`), node count preserved |
| `test_hybrid_element_suffix_recurses` | the hybrid `H` suffix is stripped and a base that itself needs mapping is resolved (`CPEG8H→CPEG8→CPE8`) |
| `test_modified_triangle_element` | modified 6-node triangles map to the plain triangle (`CPS6M→CPS6`, `CPE6M→CPE6`) |
| `test_parameter_math_functions` | `*PARAMETER` expressions may use math functions (`abs`, `sqrt`, …) and evaluate to numbers |
| `test_frictionless_friction_dropped` | a `*FRICTION` with no positive coefficient is dropped (ccx treats absent `*FRICTION` as frictionless); `mu>0` is kept |
| `test_nfill_unequal_bounding_sets` | `*NFILL` whose two bounding node sets differ in length fills the common (zip) node pairs instead of skipping |
| `test_instance_space_separated_transform` | an `*Instance` offset written space-separated (`10 0 0`) instead of comma-separated is parsed, not crashed on |
| `test_meshgen_float_formatted_integers` | mesh-gen count/increment fields written in float form (`*NGEN … 2.0`) are accepted, not crashed on |
| `test_descending_set_emits_ascending_generate` | a descending set run emits a valid ascending `GENERATE` (not the ccx-invalid `5, 1, -1`) and still resolves to all members |
| `test_string_parameter_substitution` | a string-valued `*PARAMETER` (`eltype="CPS4"`) substitutes unquoted, so `type=<eltype>` emits `TYPE=CPS4` (not the ccx-rejected `TYPE="CPS4"`) |
| `test_node_surface_drops_weight` | a node-based `*SURFACE` line (`NS, 1.`) drops the Abaqus weight to one entry per line |
| `test_contact_pair_default_type` | `*CONTACT PAIR` gets the required `TYPE=NODE TO SURFACE` (the Abaqus/Standard default; the note suggests face-to-face if ccx struggles) and Abaqus-only params are dropped |
| `test_rigid_body_pin_nset_mapped` | `*RIGID BODY, PIN NSET=…` maps to ccx's `NSET=…` |
| `test_generate_malformed_token_no_crash` | a non-integer field in a `GENERATE` record skips that record instead of aborting the conversion |
| `test_instance_qualified_set_param_resolved` | instance-qualified set names in keyword **parameters** (`*EL PRINT, ELSET=I.body`) resolve to the flattened global set |
| `test_rigid_body_refnode_instance_qualified` | `*RIGID BODY, REF NODE=I.ref` resolves through the flattened set to a node number |
| `test_assembly_instance_set_three_level_ref` | `Assembly.Instance.set` members strip the assembly level and resolve to the instance set |
| `test_element_load_uses_element_offset` | a numeric instance-qualified element id in an element load (`*DFLUX I2.1`) takes the element offset, not the node offset |
| `test_named_bc_condition_on_instance_set` | `ENCASTRE` on an instance node set is flattened **before** expansion, so the DOF lines name the renamed set |
| `test_damage_initiation_emitted_for_ccx223` | `*DAMAGE INITIATION` (ccx 2.23) is emitted with its data; `*DAMAGE EVOLUTION` stays commented |
| `test_new_abaqus_keywords_targeted_guidance` | Abaqus 2024/2025 keywords get targeted guidance, not the generic "no equivalent" comment |
| `test_t2d3_maps_to_t3d3` | the 3-node 2D truss maps to the node-count-identical `T3D3` |
| `test_independent_instance_undefined_part_no_crash` | an instance with its own mesh naming an undeclared `PART=` converts instead of crashing |
| `test_dsload_unmappable_face_warns` | a `*DSLOAD` on a face with no ccx `P1..P6` label (shell `SPOS`) warns instead of silently emitting a bare `P` |
| `test_ngen_descending_range_warns` | a descending `*NGEN` range that generates no nodes is reported, not silently dropped |
| `test_cohesive_element_substituted_to_continuum` | `COH3D8` → `C3D8` with the cohesive-behaviour-lost / zero-thickness warning |
| `test_cohesive_2d_maps_to_plane_strain` | `COH2D4` → `CPE4` |
| `test_cohesive_section_becomes_solid_section` | `*COHESIVE SECTION` → `*SOLID SECTION` with the same elset and material |
| `test_pore_pressure_element_suffix_dropped` | pore-pressure elements drop the `P` suffix (`CAX4P→CAX4`) with a warning |
| `test_empty_dload_op_new_passthrough` | an empty `*DLOAD, OP=NEW` (clears previous loads) passes through rather than being commented out |
| `test_assembly_element_instance_qualified_connectivity` | assembly-level spring elements with instance-qualified connectivity (`I1.2, I2.1`) resolve to global nodes and register |
| `test_smooth_step_amplitude_sampled` | `DEFINITION=SMOOTH STEP` is sampled as the Abaqus quintic into tabular points (midpoint and quarter-point exact) |
| `test_dload_unsupported_body_load_dropped` | `*DLOAD` `ROTA` lines are dropped with a warning while supported `GRAV` lines are kept |
| `test_assembly_node_not_overwritten_by_instance` | assembly-level reference nodes keep their ids and instances are numbered above them (issue #2) |
| `test_coupling_refnode_set_resolved_and_empty_kinematic` | `*COUPLING, REF NODE=<set>` → node number; an empty `*KINEMATIC` gets `1, 3` (ccx otherwise creates no constraint) |
| `test_kinematic_rotational_dofs_clamped` | `*KINEMATIC` DOFs above 3 are clamped to ccx's translational range |
| `test_surface_interaction_hard_behavior_synthesized` | an interaction without `*SURFACE BEHAVIOR` gets `PRESSURE-OVERCLOSURE=HARD`; one with a behaviour is left alone |
| `test_lamina_to_engineering_constants` | `*ELASTIC, TYPE=LAMINA` → `ENGINEERING CONSTANTS` (E3=E2, ν13=ν12, ν23 from G23) |
| `test_beam_section_unsupported_profile_commented` | `*BEAM SECTION, SECTION=I` (no ccx profile) is commented out with guidance |
| `test_equally_spaced_amplitude_expanded` | `DEFINITION=EQUALLY SPACED` expands to explicit time/amplitude pairs |
| `test_assembly_elset_element_member_uses_elem_offset` | an assembly `*Elset` member `I2.1` takes the element offset |
| `test_part_cohesive_section_remapped_per_instance` | a part-level `*Cohesive Section` elset is remapped per instance (`I1_COH`) |
| `test_combined_suffix_element_resolves` | combined suffixes resolve (`C3D8PT→C3D8`, `C3D20RHT→C3D20R`) |
| `test_initial_stress_expanded_to_integration_points` | `*INITIAL CONDITIONS, TYPE=STRESS` on an elset expands to one line per element and integration point |
| `test_initial_stress_geostatic_commented` | a `GEOSTATIC` initial stress (no ccx equivalent) is commented with guidance |
| `test_approximate_riks_and_default_off` | without the flag `*STATIC, RIKS` is commented out (ccx would silently run plain static) and points at the flag; `--approximate` turns it into plain `*STATIC` |
| `test_explicit_dynamics_native` | `*DYNAMIC, EXPLICIT` is kept in both modes (ccx integrates explicitly), Abaqus/Explicit-only controls dropped, and the step gets `INC=10000000` + `NLGEOM` |
| `test_approximate_nu_clamp` | `--approximate` clamps ν ≥ 0.5 to 0.475; without the flag ν is untouched |
| `test_approximate_ibeam_to_rect` | `--approximate` replaces an I-profile with the RECT of equal area and strong-axis inertia |
| `test_nonpositive_node_number_warns` | a mesh numbered from node 0 (invalid Abaqus input, issue #3) is flagged; a positive-numbered one is not |
| `test_history_card_outside_step_commented` | step data (`*CLOAD`) before any `*STEP` is commented out with the reason; model-data `*BOUNDARY` stays |
| `test_undefined_material_warns` | a section naming an undefined material is warned (with the defined names); a valid deck is not |
| `test_plane_node_rotational_bc_dropped` | DOFs 4–6 on plane-element nodes are dropped (`L,6,6` gone, `L,1,6`→`L,1,3`); shell nodes keep `1,6` |
| `test_rigid_coupling_on_shell_nodes_gets_knot_beams` | each shell node of a `*COUPLING`+`*KINEMATIC` gets a force-free knot beam (`B31` to a new free node, elset/material `ABQ2CCX_KNOT`, no density), without which ccx 2.23 rejects the rigid MPC; the rotations an empty `*KINEMATIC` couples are tied to the reference node's DOFs 4–6 by `*EQUATION` — not for a translations-only card, nor on a DOF with a `*BOUNDARY`; solid members get no knots |
| `test_rigid_body_shell_tie_and_pin_members` | `*RIGID BODY` `TIE NSET` shell nodes get their rotations tied to the `ROT NODE`; `PIN NSET` nodes get knots but keep their rotations free |
| `test_coupling_with_shell_reference_node_becomes_rigid_body` | a kinematic coupling whose `REF NODE` is a shell node becomes a `*RIGID BODY` on the other coupled nodes whose `ROT NODE` follows the node's rotations (a moment on the node stays there); one that couples only some translations is warned instead |
| `test_rigid_coupling_knots_on_edges_trusses_and_thermal_decks` | an element-edge surface knots only its edge nodes; truss members get knots but no rotation ties; a thermal step gives the knot material a conductivity; a heat-transfer-only deck gets no rotation ties; an explicit step is warned |
| `test_kinematic_rotation_lines` | a rotations-only `*KINEMATIC` is not given the `1, 3` meant for an empty card; `*KINEMATIC COUPLING` rotation lines on shell nodes become rotation ties |
| `test_plastic_hardening_forms` | Johnson-Cook kept native and given the `*RATE DEPENDENT` card ccx needs (C = 0 unless the deck has one); `HARDENING=USER` and Chaboche `PARAMETERS` commented; tabular hardening untouched |
| `test_field_dependencies_collapsed` | `DEPENDENCIES=1` collapsed to field = 0: interpolated `*ELASTIC` (E = 115500), the f = 0 `*PLASTIC` curve, the nearest `*DENSITY` row |
| `test_depvar_delete_and_labels` | `*DEPVAR` keeps the count, drops label lines and warns on `DELETE=` |
| `test_print_cards_without_set_get_whole_model_sets` | `*EL PRINT`/`*NODE PRINT` without a set get the synthesized whole-model sets |
| `test_step_amplitude_kept_and_quasi_static_ramp` | `*STEP, AMP=STEP` → `AMPLITUDE=STEP`; quasi-static `*DYNAMIC` gets `AMPLITUDE=RAMP` and `ALPHA=-0.3333` |
| `test_friction_keeps_only_mu` | `*FRICTION` emits only `mu` (exponential decay, slip tolerance); `ROUGH` is dropped with a frictionless warning |
| `test_contact_pair_tied_becomes_tie` | `*CONTACT PAIR, TIED` → `*TIE` (with `ADJUST` as position tolerance) |
| `test_composite_symmetric_and_base_rotation` | `SYMMETRIC` layups are mirrored; a ply angle composes with the base orientation's normal rotation (45 + 90 = 135) |
| `test_shell_edge_faces_map_to_s3_s6` | shell edges `E1..E4` → `S3..S6`; plane-element edges keep `S1..S4` |
| `test_amplitude_scaling_applied` | `SCALEX`/`SCALEY` are applied to the data; `VALUE=ABSOLUTE` warns |
| `test_kinematic_coupling_keeps_every_line` | `*KINEMATIC COUPLING` keeps every line as node-surface `*COUPLING` + `*KINEMATIC` per DOF range (all DOFs on solid nodes → one `1, 3` coupling, no clamp warning) |
| `test_orientation_origin_and_node_definition` | an `*ORIENTATION` origin is subtracted; `DEFINITION=NODES` resolves to coordinates |
| `test_equation_node_sets_pair_in_sorted_order` | set-based `*EQUATION` pairs nodes in sorted order, as Abaqus does |
| `test_perturbation_static_before_general_step_warns` | a static perturbation step followed by another step warns that its loads persist; a final one does not |
| `test_eigen_data_line_layouts` | `EIGENSOLVER=SUBSPACE` max frequency blanked; Lanczos `*BUCKLE` range fields blanked; a blank mode count with a range gets a count (ccx needs one) |
| `test_dsload_follower_warns_under_nlgeom` | `FOLLOWER=NO` warns only under NLGEOM |
| `test_creep_strain_hardening_warns` | default (strain-hardening) `*CREEP` with m ≠ 0 warns about ccx's time hardening; m = 0 does not |
| `test_rigid_body_pin_and_tie_sets_united` | `PIN NSET` + `TIE NSET` together become one union `NSET` |
| `test_initial_solution_continuation_lines` | `TYPE=SOLUTION` records with more than 7 SDVs are joined by the `*DEPVAR` size, not split into phantom records |
| `test_keyword_continuation_with_bare_flag` | `*STEP, NAME=S1,` + `NLGEOM` on the next line keeps `NLGEOM` |
| `test_mesh_generation_curves_bias_and_reflect` | `*NGEN, LINE=C` lands on the arc, `*NFILL, BIAS` grades the intervals, `*NCOPY, REFLECT=LINE` with one data line works |
| `test_input_data_file_inlined` | `*NODE, INPUT=file` data lines are inlined |
| `test_parameter_table_not_swallowed` | `*PARAMETER TABLE` is not treated as `*PARAMETER` (it is commented, later cards survive) |
| `test_element_and_material_defaults` | `B23` → `B33` → `B31` (map applied recursively); bare `*HYPERELASTIC` → `POLYNOMIAL` |
| `test_continuum_shell_section_becomes_solid` | `*SHELL SECTION` on SC8R elements → `*SOLID SECTION` |
| `test_part_level_constraints_replicated_per_instance` | a part-level `*EQUATION` is emitted once per instance with offset node ids |
| `test_surface_interaction_thickness_line_dropped` | the 2D out-of-plane thickness line of `*SURFACE INTERACTION` is dropped |
| `test_load_case_superposition_warned` | `*LOAD CASE` warns that ccx superposes the load cases |
| `test_abaqus_output_filter_commented` | an Abaqus output `*FILTER` is commented out (ccx's `*FILTER` is a sensitivity card) |
| `test_surface_undefined_set_warns` | a `*SURFACE` member set the deck never defines is warned |
| `test_rigid_body_reference_rotations_go_to_rot_node` | a `*RIGID BODY` gets an explicit `ROT NODE`; `ENCASTRE` and moments on the reference point reach its DOFs 1–3 (ccx ignores DOFs 4–6 of the REF NODE) |
| `test_el_print_unknown_labels_dropped` | unknown `*EL PRINT` labels (fatal in ccx) are dropped; a card left empty is dropped |
| `test_contact_output_maps_to_ccx_labels` | `*CONTACT OUTPUT` → `*CONTACT FILE` with `CDIS`/`CSTR`; names ccx doesn't know (`CPRESS`, `CFORCE`) are dropped, and a card left empty is dropped |
| `test_cload_orientation_warned` | `*CLOAD, ORIENTATION=` (local load axes) is warned |
| `test_blankless_keywords_recognised` | blank-less keywords (`*SOLIDSECTION`, `*ELPRINT`, `*ENDSTEP`) are recognised as ccx does |
| `test_frequency_storage_for_later_modal_step` | `*FREQUENCY` gets `STORAGE=YES` when a later modal/steady-state step needs its eigenmodes |
| `test_initial_temperature_defaults_uncovered_nodes_to_zero` | nodes an initial-temperature card doesn't list get Abaqus' default 0 (ccx stops otherwise) |
| `test_plane_section_blank_thickness_defaults_to_one` | a blank plane-element thickness becomes Abaqus' default 1.0 |
| `test_cyclic_hardening_needs_combined_plastic` | `*CYCLIC HARDENING` without a kept `COMBINED` `*PLASTIC`, or in `PARAMETERS` form, is commented out |
| `test_boundary_on_undefined_set_warns` | a BC on an undefined node set (or on a surface name) is warned |
| `test_circ_linear_beam_becomes_quadratic` | 2-node beams under `SECTION=CIRC` (rejected by ccx 2.23) → `B32`/`B32R` with a midside node at each midpoint, in ccx's end, middle, end order (`B21`/`B31` → `B32`, `B31R` → `B32R`); element ids and the elset kept; the Abaqus radius → ccx's two diameters; `RECT` beams stay linear |
| `test_circ_beam_midside_follows_instance_transform` | in a translated and rotated instance the midside node lands at the midpoint of the transformed end nodes |
| `test_circ_beam_midside_node_gets_sets_bcs_and_fields` | the midside node joins a node set only BCs use, not one a `*CLOAD` counts; `*BOUNDARY` (per DOF), initial temperature/velocity, `*TEMPERATURE` and `*NORMAL` lines on both end nodes are interpolated onto it, replacing a set value that the end nodes override |
| `test_pipe_box_beams_become_b32r` | ccx 2.23 runs `PIPE`/`BOX` sections only on `B32R`: under `PIPE`, `BOX` and `THICK PIPE` (emitted as `PIPE`), 2-node `B21`/`B31`/`B31R`/`PIPE31` → `B32R` with a midside node, end, middle, end; ids and the elset kept; the `PIPE` (outer radius, wall) and `BOX` (a, b, t1..t4) data lines pass through; the midside node joins a node set only a `*BOUNDARY` uses |
| `test_pipe_box_b32_only_changes_type` | `B32`/`PIPE32` under `PIPE`/`BOX` → `B32R` with the same nodes and no midside message; `B32` under `CIRC` is left alone |
| `test_mixed_section_beams_report_each_case` | `CIRC`, `PIPE` and `BOX` beams in one deck: one report line for the midside-node upgrades (naming both sections and both reasons) and one for the retyped `B32`; an element under both a `PIPE` and a `CIRC` section stays `B32R` |
| `test_beam_pipe_box_cantilever_example` | the bundled pipe/box cantilevers convert to 40 `B32R` (the `PIPE31` beams with midside nodes, the `B32` beams on their own nodes) with both data lines unchanged, no dangling refs |
| `test_beam_circ_cantilever_example` | the bundled CIRC cantilever converts to 20 `B32` with midside nodes and diameters, no dangling refs |
| `test_coupling_plate_examples` | the `coupling_shell_plate`/`coupling_solid_plate` validation pair: 9 knot beams and 27 rotation ties on the `S8R` edge, none for the `C3D20R` reference; no dangling refs |
| `test_planar_line_types` | `planar_line_type()` maps the Abaqus 2-D beams/trusses and their `H`/`T` variants (`B21H` → `B21`, `T2D2T` → `T2D2`, `PIPE22`, …) and nothing else (`B31`, `T3D2`, `CPS4`, …) |
| `test_planar_beams_fix_out_of_plane_dof` | a planar `B21` model gets node set `ABQ2CCX_PLANAR` with DOF 3 fixed in model data ahead of the steps (ccx runs `B21` as a 3-D `B31`, so each bending mode would appear twice); `B21H`, `B23`, `PIPE21`, `B22` and `T2D2` trusses alike; `ENCASTRE` already holds the twist; `*FREQUENCY` warns that twist modes remain; 3-D beams are left alone |
| `test_planar_constraint_reaches_upgraded_midside_nodes` | a `B21` under `SECTION=CIRC` (→ `B32`) has its inserted midside nodes in the planar set |
| `test_planar_straight_beam_twist_held_at_one_node` | a straight beam on pinned supports gets DOFs 4–5 at one support (its twist is otherwise a 0 Hz mode); with CAE's U1/U2/UR3 clamp, at the clamped node, for a circular section too; a pinned circular-section beam gets them at the middle node of an element next to a support (at an end node ccx 2.23 would lock its bending rotation too), no knot beam; a frame that is not straight needs none |
| `test_planar_constraint_skips_constrained_and_skewed_nodes` | nodes whose DOF 3 is the dependent term of an `*EQUATION` (an SPC there stops ccx), `*MPC` nodes, rigid-body members and nodes under a `*TRANSFORM` whose 3-axis is not z are left out; a transform about z is kept |
| `test_planar_constraint_repeated_after_op_new` | a `*BOUNDARY, OP=NEW` step repeats the planar constraint (OP=NEW removes model-data BCs too) |
| `test_planar_constraint_needs_a_planar_model` | `B21` among 3-D elements, or with nodes off one z plane, gets no constraint and a warning |
| `test_planar_pinned_beam_example` | the bundled planar beam converts to 20 `B21` with DOF 3 on all 21 nodes and DOFs 4–5 at the pinned end, ahead of the steps, no dangling refs |
| `test_circ_beam_partial_rotation_bc_gets_knot_beam` | an element end node of a `CIRC` beam whose rotational BCs hold only some rotations (DOFs 1–4 at a pinned end, `XSYMM`), or a nonzero one (a prescribed rotation, even with all three given), gets a force-free knot beam (ccx 2.23 would lock its other rotations); the BC lines are kept; none for full zero clamps, `RECT` beams or a BC on a 3-node element's middle node |
| `test_circ_beam_rotation_knots_follow_steps_and_skip_unsafe_nodes` | a later `*BOUNDARY, OP=NEW` step that leaves only some rotations held gets knots; none on a node with a `*TRANSFORM` nor in a heat-transfer-only deck; an explicit dynamic step is warned instead (it stops on the knot beams); knots on most end nodes are warned (their rigid sections stiffen the beam) |
| `test_circ_rotation_bc_examples` | the bundled `beam_circ_rotation_bcs` deck gets knot beams at the two pinned ends whose twist is held and at the turned tip, none at the clamp; `planar_pinned_circ_beam` holds its twist at the first element's middle node, no knots; no dangling refs |

## 2. End-to-end validation — `validate_with_ccx.py`

Auto-detects `ccx` (including the binary bundled with FreeCAD), converts each example
deck and runs it in CalculiX:

* **`nle10_thickplate`** — the NAFEMS LE10 benchmark: checks σ_yy at point D against the
  published −5.38 MPa reference (the converted deck gives −5.65 MPa, a 5 % difference
  in line with the element type and mesh — proving the whole pipeline is correct, not
  just well-formed).
* **`beam_circ_cantilever`** — a cantilever on linear `B31` beams with a circular section,
  which ccx 2.23 rejects; the converter emits `B32` with inserted midside nodes and turns
  the Abaqus radius into ccx's diameters. Checks the tip deflection against beam theory,
  P L³/(3 E I) = −4.244 (the converted deck gives −4.229, 0.4 %).
* **`beam_pipe_box_cantilever`** — a pipe section on `PIPE31` elements and a box section on
  `B32` elements, which ccx 2.23 runs only on `B32R`; the converter emits both as `B32R`
  (the `PIPE31` beams with midside nodes). Checks the tip deflections against beam theory:
  pipe −7.149 vs −7.189 (0.6 %); box −1.790 vs −1.789 (0.1 %) along y and −4.509 vs
  −4.527 (0.4 %) along z. The box has a ≠ b and unequal wall pairs and is loaded along both
  axes, so a swapped a/b or wall pair would miss by 18 % or more.
* **`coupling_shell_plate`** vs **`coupling_solid_plate`** — a 100 × 40 × 2 plate clamped at
  one end, its other edge rigidly coupled to an offset reference point that carries a force
  and a moment: as `S8R` shells under `*COUPLING`+`*KINEMATIC` (rejected by ccx 2.23 on
  shell nodes; the converter adds knot beams and rotation ties), and as `C3D20R` bricks —
  one through the thickness, the brick ccx expands an `S8R` into — under `*RIGID BODY`.
  The reference-point displacements must agree within 0.5 % of |u| (they agree to
  0.001 %).
* **`beam_circ_rotation_bcs`** — two `B31` beams with a circular section, which ccx 2.23
  runs as `B32`: one pinned at both ends with its twist held there and a mid-span load, one
  clamped with its tip turned by a prescribed rotation of 0.001 rad. Under a rotational BC
  ccx ties a circular section to its corners and locks the rotations the BC leaves free
  (without the converter's knot beams the first deflects 0.31 of beam theory, the second
  0.76); checks the mid-span deflection, −12.658 vs P L³/(48 E I) = −12.631 (0.2 %), and
  the tip deflection, +0.5004 vs θ L/2 = +0.5 (0.1 %).
* **`planar_pinned_beam`** — a simply supported `B21` beam (rectangular section) with a
  `*FREQUENCY` and a `*BUCKLE` step. ccx runs `B21` as a 3-D `B31`, so this
  checks the planar constraint: the first two frequencies against beam theory, 93.67 and
  373.02 Hz vs 93.81 and 375.25 Hz (0.6 %), and the buckling load against Euler's,
  220545 vs 221079 (0.2 %). Without the constraint ccx reports 0 Hz modes (the free twist
  and the unsupported out-of-plane motion) and a buckling factor of 1, and the check fails.
* **`planar_pinned_circ_beam`** — the same check on a `B21` beam with a circular section
  (a `B32` in ccx), whose twist is held at the first element's middle node: 40.81 and
  163.28 Hz vs 40.62 and 162.49 Hz (0.5 %), buckling load 16239 vs 16278 (0.2 %). At an end
  node the twist BC would lock the bending rotation as well (f1 1.46-fold, buckling load
  1.88-fold); with none, ccx reports a 0 Hz twist mode and a buckling factor of 0.0001.
* **`composite_shell`**, **`assembly_two_blocks`** — confirm they are accepted by ccx
  and solve.

## 3. Real-world corpus — `corpus/` + `tests/test_corpus.py`

* **`corpus/manifest.py`** — 1022 **genuine Abaqus** decks from ~179 public GitHub
  repositories (Abaqus/CAE exports with `*Part`/`*Instance`/`*Assembly`,
  user-element/UMAT/VUMAT decks, cohesive-zone and explicit-dynamics models, coupled
  temperature-displacement, mesh-generation cards `*NGEN`/`*NFILL`/`*NCOPY`/`*ELGEN`,
  named BCs, `*Parameter` with arithmetic expressions, …), each with its download URL,
  license, what it exercises, an `expect_solve` flag, and a note for those that can't
  solve. They span many engineering domains — composites, geotech, biomechanics,
  fracture/fatigue, metal forming, thermal/AM, FEA-tool test suites, teaching material.
  These are real files that do **not** run in ccx directly, so they exercise the actual
  conversion. The files are fetched on demand (not committed — licenses vary; each entry
  records its own) into `corpus/files/` (gitignored), and are content-deduplicated so a
  byte-identical fixture shared across repos appears once.
* **`corpus/fetch.py`** — downloads the manifest's decks.
* **`tests/test_corpus.py`** — two checks:
  * `test_corpus_converts` — every present deck converts without crashing and the
    result is referentially consistent (zero dangling references). **Always runs.**
  * `test_corpus_solves` — decks marked `expect_solve` are run in CalculiX and must
    **solve**: ccx exits 0, prints "Job finished" with no `*ERROR` and no crash/abort
    message on stdout or stderr, and executes at least one analysis `STEP`. Mesh-only
    decks marked `parse_only` (no `*STEP`, so nothing to solve) must be **accepted** by
    ccx under the same clean-exit rules. Only runs when `ccx` is available.
  * `test_classify_ccx_run` — unit test of that judge (no ccx needed), including the
    "Job finished, then abort" case from issue #3.

  Run standalone (`python tests/test_corpus.py`) it prints a per-deck table.

**Results** (CalculiX 2.23, the FreeCAD 1.1.4 build): all 1022 convert with zero dangling
references; **220 solve** in CalculiX and **219 mesh-only decks are accepted** by it. The
other 583 convert cleanly but use features ccx cannot run (user elements, UMAT/VUMAT and
other user subroutines, Riks, cohesive/connector elements, piezoelectric/acoustic
coupling) or are CAE part fragments / incomplete or invalid source decks (e.g.
externally-supplied `<parameter>` values, or nodes numbered from 0) — and each was
verified to fail *no worse than the original, unconverted deck*.

**The ccx 2.23 audit (October 2026).** FreeCAD 1.1.4 moved from ccx 2.22 to 2.23, which is
stricter about invalid input. A full re-run of the corpus on 2.23 — recording every ccx
`*WARNING`, crash and result file, not just the judge's verdict — plus a handler-by-handler
review for silent drops found three kinds of problem, all fixed in the converter:

* **inputs that crash ccx 2.23** (segfault / bus error instead of an `*ERROR`): step data
  before any `*STEP`, an undefined material on a plane-element section, rotation BCs on
  plane-element nodes, an unknown `*EL PRINT` label;
* **places where ccx quietly runs a different model** — the expensive kind, because the
  run "succeeds": ccx ignores rotations on a `*RIGID BODY` reference node (a moment there
  did nothing), runs a Riks step as plain static, skips `HARDENING=USER` plasticity and
  switches its own Johnson-Cook law on only with a `*RATE DEPENDENT` card, ignores
  field-variable `DEPENDENCIES`, reads Abaqus' slip-rate column as the friction stick
  slope, drops a `TIED` contact pair (bodies separate), uses shell faces for Abaqus shell
  *edges*, halves a `SYMMETRIC` layup, and loses part-level constraints of all but one
  instance;
* **wrong claims in the converter's own messages** — e.g. that ccx has no explicit solver
  (it has; explicit decks now run natively) or rejects `*STEP AMPLITUDE=` (it supports it).

Net on 2.23: 199 → 215 solving and 214 → 219 accepted. Four decks lost their gate on
purpose — a Riks deck (now commented out instead of silently run as static), a shell model
whose rigid coupling 2.23 rejects (since repaired, below), and two VCCT decks whose
remaining contact (Abaqus' default node-to-surface) does not converge once the unsupported
bonded start is gone. Two decks that solve stay ungated: one is nondeterministic (ccx's
built-in `utemp` stub segfaults about 1 run in 6), one takes ~260 s.

**Circular-section beams.** ccx 2.23 also stops on linear beams with a circular section
("Please use quadratic elements for beams with circular cross section"), which blocked a
`B21` frequency analysis and two `B31` lattice decks. Such beams are now emitted as
`B32`/`B32R` with a midside node per element. The same work found that ccx reads a `CIRC`
section's data as two *diameters* while Abaqus gives the radius: passed through, the radius
made circular beams 16× too flexible in bending. Both are fixed; the three decks solve
(215 → 218), the frequency deck's first bending modes match Euler–Bernoulli within 0.6 %,
and `validate_with_ccx.py` checks a circular cantilever against beam theory.

**Pipe and box beams.** ccx 2.23 accepts `SECTION=PIPE` and `SECTION=BOX` only on `B32R`
("*BEAM SECTION of type PIPE can only be used for B32R elements"), so beams under them, and
under `THICK PIPE` (emitted as `PIPE`), now become `B32R`: 2-node beams get the same midside
nodes, `B32` only changes type. Both data lines mean the same in the two codes — `PIPE` is
the outer radius and wall thickness; `BOX` is `a` along local 1, `b` along local 2, then the
walls at +1, +2, −1, −2 (from the manual; a probe with one thick wall under axial tension
confirms the wall order). A 40-element cantilever's tip deflection is 0.997 (`PIPE`) and
1.010 (`BOX`) of P L³/(3 E I); `BOX` converges to 1.012 because ccx integrates the walls
along their centre lines and ignores each wall's own bending stiffness. `validate_with_ccx.py`
checks a pipe and a box cantilever against beam theory. No corpus deck starts solving: the
two `PIPE31H` decks that use `THICK PIPE` also need externally supplied `<parameter>` values.

**Rigid couplings on shell, beam and truss nodes.** ccx builds `*RIGID BODY` and
`*KINEMATIC` couplings from RIGID MPCs, and 2.23 stops on one that touches a shell,
membrane, beam or truss node (`*ERROR in gen3dmpc: nodes belonging to shell elements must
not be subject to a RIGID MPC`; 2.22 ran them, current sources only warn) — unless ccx has
made the node a *knot*, which a beam element attached to it does. Each such node now gets
a force-free *knot beam* (a `B31` to a new free node, no density) and ccx's own constraint
stays. The knot also gives the node real rotations, so the rotations Abaqus couples are
tied to the body's by `*EQUATION`: ccx's coupling never coupled them (a rotational DOF of a
non-knot shell node does nothing in an MPC), so a straight coupled edge hinged freely about
itself. Probed on 2.23:

* an `S8R` plate edge coupled to an offset, loaded reference point vs the same plate as
  `C3D20R` under `*RIGID BODY`: reference-point displacement within 1.3e-5 of |u|, body
  rotations within 0.1 %; under `NLGEOM` (about 8° end rotation) within 6e-4; the
  zero-density knot beams leave the eigenfrequencies unchanged. As `S4` vs `C3D8I` and
  `S4R` vs `C3D8R` (the bricks ccx expands them into): 5e-5 and 2e-5 of |u|;
* a `B31`/`B32` cantilever whose tip is coupled to an offset point vs the statically
  equivalent tip load: within 1e-4;
* `marcello_gori_u_shaped_bracket`, whose reference points are encastred, vs the same deck
  with the coupled nodes encastred directly: within 5.7e-7 over all 2092 nodes;
* `marcello_gori_spring_plate_nl` (`NLGEOM` and plasticity): unchanged to 6 digits when the
  knot beams' modulus is scaled by 1000 either way or their section by 10 — they carry no
  load.

Linear `*EQUATION` ties u = u_R + θ × (x − x_R) were the alternative: exact only without
`NLGEOM` (up to 23 % off at 8° in the same probe), and they still could not tie the shell
rotations. Both decks above now solve (218 → 220); `marcello_gori_job_1`, a beam tower,
already did, and its first buckling factor rises 0.4 % now that the column tops'
rotations follow the reference point, as its empty `*Kinematic` asks. A kinematic
coupling whose reference node is itself a shell/beam node becomes a `*RIGID BODY` whose
`ROT NODE` follows that node: kept as a ccx coupling, the node carries two unrelated
rotations (probed: the beam acts hinged at the coupled face). Not covered: explicit
dynamics ("linear and nonlinear MPC's depend on each other", with or without the knot
beams), and coupled DOFs that also carry a `*BOUNDARY` — `dheller1_uprofile` now passes
the gen3dmpc check but stops on that overconstraint, which Abaqus resolves and ccx does
not.

**Planar beams and trusses.** ccx has no planar beam or truss: it runs `B21` "as a B31" and
`T2D2` as a `T3D2` (manual 6.2.31, 6.2.34), and the converter maps the other 2-D types onto
3-D ones, so nothing holds them in their plane. The `B21` frequency deck reported every
bending mode twice (13.59/13.59, 85.05/85.05, 237.7/237.7 Hz, …), and in the seven `T2D2`
truss decks the out-of-plane displacement was solver noise of the size of the in-plane one
(up to 34 times it); given a density, one of them showed a 0 Hz mode per node. The converter
now fixes DOF 3 on the nodes of 2-D beams and trusses in a planar model (model data,
repeated after `*BOUNDARY, OP=NEW`, which removes it). The frequency deck then gives each
bending mode once — 13.59, 85.05, 237.65, 464.3 Hz against Euler–Bernoulli's 13.52, 84.70,
237.2, 464.8 — plus the 748.9 Hz twist mode, which Abaqus' planar beam cannot have and which
is warned; the truss decks' in-plane displacements are unchanged to 1e-15 and their U3 is
zero. All 14 corpus decks with 2-D elements keep their verdict (8 solve, 2 accepted, 4
failing as before), and every other corpus deck converts byte-identically. A portal frame
(`B21`, fixed bases, 10 elements per member) matches a 2-D Euler–Bernoulli frame solution:
sway deflection 1.2343 vs 1.2456, frequencies 14.95, 43.85, 97.28, 103.65 Hz vs 14.89,
43.62, 97.48, 103.38, buckling factor 107.1 vs 106.3 — where the unconstrained deck put
out-of-plane modes first (4.7 Hz, factor 9.8). The rotations are not fixed on every node:
probed on 2.23, that raises the bending frequencies of a `B32` beam with a circular section
16-fold, makes a rectangular one about 10 % stiffer, and changes a `B31` beam's `*DYNAMIC`
response by 3.6 % (knots). The twist needs one BC, though: a straight beam whose twist
nothing restrains (pinned supports, or CAE's U1/U2/UR3 clamp) has a 0 Hz twist mode and
meaningless `*BUCKLE` factors (about 1), and under NLGEOM a pinned `B31` beam stopped
converging ("increment size smaller than minimum"; with the BC its large deflection matches
the elastica). So DOFs 4–5 are fixed at one of its nodes — one whose in-plane rotation is
already fixed, else a support (on a circular section, the middle node of an element next to
one: see below). `validate_with_ccx.py` checks pinned planar beams' frequencies and buckling
loads against beam theory.

**Rotational BCs on circular-section beams.** Adding the twist BC above showed that on a
circular section ccx 2.23 couples a rotational BC into the other rotations; its sources
explain why. ccx expands a `CIRC` beam node into eight nodes on the circle (`gen3dfrom1d`),
and for every rotational BC on a `B32`/`B32R` node that is not a knot it ties the
section's four midside nodes to the mean of their corners (`gen3dboun`) — exact on the
rectangles `RECT`, `PIPE` and `BOX` expand into, but no rigid rotation of a circle
satisfies it. So a BC on DOF 4, 5 or 6 at an element end node locks the twist and both
bending rotations there. Probed with 10 `B32` per span: a simply supported beam with its
twist held at one end deflects 0.46 of beam theory, with the twist held at both pinned
ends 0.27; a cantilever whose tip is turned by a prescribed rotation reaches 0.76 of
θ L/2 (all three rotations given); DOF 4 on every node gives 0.009; `RECT`, `PIPE` and `BOX`
are unaffected. Moments are not affected (`gen3dforc` adds no such ties), nor is a BC at a
3-node element's middle node (no element uses the section nodes tied there), nor a knot,
whose BCs act on its rotation node. The converter therefore gives each element end node of
a `CIRC` beam whose rotational BCs hold only some rotations, or a nonzero one, in some step
a force-free knot beam, as for rigid couplings: 0.994 and 1.00 of beam theory. A knot's
rigid section costs a little where the beam bends (Poisson locking — it vanishes with
ν = 0): 1.3, 0.6 and 0.3 % with a knot inside a span of 10, 20 and 40 elements, nothing at
a pinned end. So full zero clamps keep ccx's handling, and knots on more than a quarter of
the end nodes are warned (DOF 4 on every node: 0.84 with the knots). A planar `CIRC` beam
on pinned supports gets its twist BC at an element's middle node instead, where nothing
else changes: bending frequencies and buckling load as with the twist free, to 4 digits.
Implicit `*DYNAMIC` turns rotational BCs into knots by itself (identical results with and
without the knot beams); an explicit step stops on the density-free knot beams
("*ERROR in calcstabletimeincvol"), so there it is only warned — ccx's explicit solver also
returned NaN displacements for `CIRC` beams with no rotational BC at all. No corpus deck has
such a BC, and every corpus deck converts byte-identically; `validate_with_ccx.py` checks
both 3-D cases and the planar beam against beam theory.

Until issue #3 the judge only looked for "Job finished" on stdout, so it counted
mesh-only decks (which ccx merely parses) as solved and would have missed a crash after
"Job finished" (the exit code and stderr were ignored); that inflated the earlier
headline of 414 "solving" decks.

This corpus was assembled in waves: bulk-downloading hundreds of genuine Abaqus decks
from public GitHub repositories (the second wave via parallel discovery agents fanned
out across engineering domains), then running **every one** through convert →
referential-integrity check → CalculiX, content-deduplicating as it went. That stress
test (plus an adversarial code review) surfaced and fixed real converter bugs:

* **keyword-line continuation** — a `*KEYWORD,…,` line whose parameters spill onto the
  next line (`*NCOPY,…,SHIFT,` ⏎ `NEW SET=…`; `*ELSET, ELSET=X,` ⏎ `GENERATE`) is now
  spliced back together, *without* a stray comma on a `*NODE`/`*ELEMENT` header
  swallowing the first data row;
* **coupled temperature-displacement elements** — the `T` suffix is dropped
  (`C3D8T→C3D8`, `CAX4RT→CAX4R`), since ccx uses the base element;
* **`*PARAMETER` arithmetic** — expressions may use math functions (`abs`, `sqrt`, …),
  evaluated by a safe AST walk (no `eval`, so an untrusted deck cannot execute code),
  with user parameters never shadowed by the math constants `pi`/`e`;
* **modified 6-node triangles** (`CPS6M`/`CPE6M`/`CAX6M` → `CPS6`/`CPE6`/`CAX6`) and the
  recursive hybrid-suffix strip (`CPEG8H→CPE8`);
* **frictionless `*FRICTION`** dropped (ccx treats a zero/empty coefficient as an error,
  but the *absence* of the card as frictionless);
* **`*NFILL` with unequal bounding sets** now fills the common node pairs instead of
  skipping (a real textbook deck carried one spurious extra edge node), but skips if the
  sets differ by more than 2×;
* **space-separated `*INSTANCE` transform** (`10 0 0` instead of `10., 0., 0.`, emitted
  by some lattice generators) is parsed via a comma-or-whitespace splitter;
* **non-numeric element connectivity** (an assembly-level connector/MPC using
  instance-qualified node names like `PART-1-1.1`) is skipped with a warning rather than
  crashing;
* **float-formatted mesh-gen integers** (`*NGEN … 2.0`, `*NCOPY, CHANGE NUMBER=100.0`)
  are parsed with `int(float(...))` instead of crashing the whole conversion (a final
  pre-publication review surfaced this);
* **descending set runs** now emit a valid ascending `GENERATE` rather than the
  ccx-invalid `5, 1, -1` (which silently empties the set, dropping a BC/load).

A later pass mining the non-solving decks for *converter-addressable* failures (as
opposed to fundamental ccx limits — UMAT/UEL/cohesive/explicit, which no converter can
run) added four more lossless fidelity fixes: **string-valued `*PARAMETER`** (`<eltype>`
→ `CPS4`, not `"CPS4"`), **node-based `*SURFACE`** one-entry-per-line, **`*CONTACT PAIR`**
default `TYPE`, and **`*RIGID BODY` `PIN/TIE NSET` → `NSET`**. These correct ~100+ decks'
emitted cards; most still don't *solve* because they hit a second, fundamental blocker,
so the net solve gain was small (+1) — the corpus is dominated by genuinely
ccx-unsupported physics, which is by design (it is a *genuine-Abaqus* corpus).

Earlier rounds also fixed independent-instance meshes, `*PARAMETER` substitution
(`**`-comments and forward refs), trailing-comma over-merge, Fortran `D` exponents, and
set-name truncation consistency.

## Adding to the corpus

Append one `dict(...)` entry to `corpus/manifest.py` (name, url, license, exercises,
`expect_solve`, `parse_only=True` for a mesh-only deck with no `*STEP`, optional note),
then `python corpus/fetch.py` and re-run `python tests/test_corpus.py`.
