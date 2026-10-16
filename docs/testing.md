# Testing

The converter has three layers of tests:

1. **Unit tests** — fast, no solver needed, run on small controlled fixtures and the
   bundled examples.
2. **End-to-end solver validation** — converts the example decks and runs them in
   CalculiX, checking the NAFEMS LE10 benchmark and circular-, pipe- and box-section
   cantilevers numerically.
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

## 1. Unit tests — `tests/test_convert.py` (127)

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
| `test_consistent_nodal_forces_integrate_shape_functions` | the face/edge integrator: a unit load gives ¼ per quad4 node, −1/12 and ⅓ on quad8 corners and midsides, ⅙ per tri3 node, 0 and ⅙ on tri6 corners and midsides, ⅙-⅙-⅔ on a 3-node edge, and 2π ∫ N r ds on an axisymmetric edge |
| `test_dsload_traction_becomes_consistent_nodal_forces` | `*DSLOAD TRVEC` on a C3D8 face → a `*CLOAD` of magnitude × area / 4 per node along the normalised direction; `TRSHR` projected onto the face; a `TRSHR` normal to the face is refused; element-based `TRVEC2` is the same load |
| `test_traction_on_plane_and_axisymmetric_edges` | a plane-stress edge traction is times the section thickness and in-plane only; an axisymmetric one is over the full circle (2πr) |
| `test_traction_under_nlgeom_converts_only_when_exact` | under NLGEOM a follower (`FOLLOWER=YES`, the default) or per-current-area (`CONSTANT RESULTANT=NO`) traction is commented and the step flagged; `FOLLOWER=NO, CONSTANT RESULTANT=YES` converts; `--approximate` converts the rest with `[APPROX]` |
| `test_converted_loads_across_steps_never_use_op_new` | converted forces carry their `AMPLITUDE`; an unchanged load is not re-emitted; `*DSLOAD, OP=NEW` gives the old traction's nodes 0 instead of `OP=NEW`; after the deck's own `*CLOAD, OP=NEW` the converted forces are given again |
| `test_converted_load_sharing_a_deck_cload_dof` | a converted force on a node DOF the deck's own `*CLOAD` also loads is kept in a one-step deck (ccx adds them) and refused in a multi-step one (ccx would replace one with the other) |
| `test_beam_line_loads_become_consistent_nodal_forces` | `*DLOAD PY` / `P1` / `P2` / `PZ` on `B31`, `B32`, an upgraded `CIRC` beam (its midside node takes ⅔) and a planar `B21` → nodal forces along the global or local (n1, t × n1) axes |
| `test_user_subroutine_loads_are_commented_out` | `*BOUNDARY, USER`, `*CLOAD, USER`, a `P1NU` line, `*TEMPERATURE, USER`, a `F1NU` film and `*AMPLITUDE, DEFINITION=USER` are commented, naming `uboun.f` / `cload.f` / `dload.f` / `utemp.f` / `film.f` / `uamplitude.f`; the other lines stay |
| `test_load_audit_flags_steps_whose_loads_do_not_survive` | a step loaded only by a `*BOUNDARY, USER` is flagged (`unloaded_steps`); an empty step marks the deck `source_unloaded`, a frequency step does not; `step_load_audit` carries loads across steps and resets them only with `OP=NEW` (not the cards before it in the same step) |
| `test_dload_and_dsload_op_new_keep_each_others_loads` | a `*DLOAD, OP=NEW` keeps the earlier `*DSLOAD` pressure (given again), and a `*DSLOAD, OP=NEW` the earlier gravity — ccx's `OP=NEW` would remove both |
| `test_dload_without_element_set_loads_the_whole_model` | `, GRAV, ...` (no element set: the whole model in Abaqus) → a whole-model element set |
| `test_dsload_on_undefined_surface_says_so` | a `*DSLOAD` on a surface the deck never defines says so (it used to say "not element-based") and flags the step |
| `test_distributed_load_examples` | the Cook, line-load and cylinder examples' converted forces add up to the applied loads (1; q L per beam; 2π a h p) |

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
* **`cook_membrane_traction`** — Cook's membrane (plane stress, E = 1, ν = 1/3, 16 × 16
  `CPS8`) under a shear traction on its right edge (`*DSLOAD TRVEC`, total 1), which ccx has
  no card for: the converter applies consistent nodal forces. Checks the vertical
  displacement of the loaded edge's midpoint against the published 23.96 (Bergan & Felippa
  1985): 23.932, 0.12 %. (An independent plane-stress Q8 solution converges to 23.963 there;
  the top corner converges to 25.19, so the classic reference point is the edge midpoint.)
* **`beam_line_load_cantilever`** — uniform line loads on three cantilevers: `*DLOAD PY` on
  `B31`, the local `P2` on `B32` and `PZ` on a circular `B31` run as `B32` with midside nodes.
  Checks that the converted forces add up to q L exactly and the tip deflections against
  q L⁴/(8 E I): 0.1 %, 1.2 % and 0.6 % (the 10-element `B32` is stiffest).
* **`cylinder_traction_cax`** — an open-ended thick cylinder (`CAX8`) under internal pressure
  applied as a radial traction (`*DSLOAD TRVEC`): u_r at the inner and outer radius against
  Lamé, within 0.02 % — the full-circle (2πr) convention of axisymmetric nodal forces, which
  ccx shares with Abaqus (probed: a `*CLOAD` on a `CAX4` edge matches the same edge under
  pressure only as the 2π total).
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
* **`tests/test_corpus.py`** — these checks:
  * `test_corpus_converts` — every present deck converts without crashing and the
    result is referentially consistent (zero dangling references). **Always runs.**
  * `test_corpus_loads` — an `expect_solve` deck must keep a load in every step the
    Abaqus deck loads (the converter's load audit, `Converter.unloaded_steps`): a step
    whose loads were all commented out would still "solve" in ccx, to a zero response.
    And `source_unloaded=True` must flag exactly the decks that load no step at all.
    **Always runs** (no ccx needed).
  * `test_corpus_solves` — decks marked `expect_solve` are run in CalculiX and must
    **solve**: ccx exits 0, prints "Job finished" with no `*ERROR` and no crash/abort
    message on stdout or stderr, and executes at least one analysis `STEP`. Mesh-only
    decks marked `parse_only` (no `*STEP`, so nothing to solve) must be **accepted** by
    ccx under the same clean-exit rules. Only runs when `ccx` is available.
  * `test_classify_ccx_run` — unit test of that judge (no ccx needed), including the
    "Job finished, then abort" case from issue #3.

  Run standalone (`python tests/test_corpus.py`) it prints a per-deck table.

**Results** (CalculiX 2.23, the FreeCAD 1.1.4 build): all 1022 convert with zero dangling
references; **188 solve** in CalculiX under their own loads and **219 mesh-only decks are
accepted** by it. 14 more decks solve but load nothing in the source deck itself (an empty
`*STEP`), so their solution is zero in Abaqus as well; they stay in the gate as conversion
checks (`source_unloaded=True`), outside the headline count. The other 601 convert cleanly
but use features ccx cannot run (user elements, UMAT/VUMAT and other user subroutines,
Riks, NLGEOM follower tractions, cohesive/connector elements, piezoelectric/acoustic
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

**Hollow solves: loads that did not survive the conversion.** A solve only counts if the
model carries the deck's loads. A load audit (`step_load_audit`, run on the Abaqus deck and
on the converted one) found that 53 of the 220 decks then gated as solving ran with no load
at all, so ccx "solved" them to zero displacement:

* 36 lost their only load, a surface traction (`*DSLOAD TRVEC` / `TRSHR`), which ccx has no
  card for and the converter used to comment out;
* 3 had a user-subroutine BC (`*BOUNDARY, USER`), which went through unchanged, so ccx ran
  its stock `uboun.f` instead of the deck's `DISP` routine;
* 14 load nothing in the source deck itself.

Tractions and beam line loads (`*DLOAD PX/PY/PZ/P1/P2`, which ccx reads on a beam as a
section-face pressure) now become consistent nodal forces: the face/edge shape functions
integrated by Gauss quadrature over the undeformed geometry, times the plane-section
thickness (probed: a ccx `*CLOAD` on a `CPS`/`CPE` node is the total for the section
thickness) or over the full circle on axisymmetric edges (probed: ccx, like Abaqus, takes
the 2π total there), emitted as a `*CLOAD` at the end of the step. ccx adds `*CLOAD`s on
one node and DOF within a step and replaces them across steps (probed, as for `*DLOAD`), so
the converted forces are re-emitted as totals when they change, never with `OP=NEW` (which
would also remove the deck's own concentrated loads). Nodal forces are exact in small-strain
steps; under NLGEOM only for a `TRVEC` that keeps its direction and resultant
(`FOLLOWER=NO, CONSTANT RESULTANT=YES` — the defaults are `YES` / `NO`), since ccx keeps a
`*CLOAD` fixed. Any other NLGEOM traction stays commented unless `--approximate`.
User-subroutine loads and BCs are commented out, naming the ccx subroutine to port. The
audit is now a corpus gate (`test_corpus_loads`).

Of the 36 traction decks, 20 now solve under their real load: their converted forces add up
to traction × area to 1e-13 per surface, and on `minhnguyenikm_cook_q4_job_2` (`TRSHR`) ccx
gives the same corner deflection as an independent Q4 solution of the same mesh (1.073028).
`xzhang66_plainstrain` (element-based `TRSHR2`/`TRSHR4` with end pressures), which ccx
used to stop on, now solves and joins the gate: ccx matches an independent Q4 solution
there on all 45 nodes to 2e-7. The other 16 traction decks are NLGEOM follower or
current-area tractions and leave the gate, as do the 3 user-subroutine decks. Net: 220
gated decks, of which 167 carried their real loads → 202 gated, of which 188 (all but the
14 `source_unloaded` ones) do.

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
