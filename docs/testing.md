# Testing

The converter has three layers of tests:

1. **Unit tests** — fast, no solver needed, run on small controlled fixtures and the
   bundled examples.
2. **End-to-end solver validation** — converts the example decks and runs them in
   CalculiX, checking the NAFEMS LE10 benchmark, circular-, pipe- and box-section
   cantilevers, circular-section beams with rotational BCs and in an explicit dynamic
   step, planar beams' frequencies and buckling loads, per-element `*DISTRIBUTION`
   orientations, a clamped beam and plate across a later step's `*BOUNDARY, OP=NEW`,
   rigidly coupled models (a shell plate, and bars whose coupled nodes also carry BCs) and
   the `*MPC` conversions numerically.
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

## 1. Unit tests — `tests/test_convert.py` (173)

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
| `test_overconstraint_equation_reordered` | an `*EQUATION` whose first DOF has a BC, or is the first DOF of another equation, gets a free term first; a duplicate and a loop's closing equation are dropped; a rigid-body member's translation is never made dependent; an equation whose every DOF is held (one of them nonzero) keeps the overconstraint warning, as does a BC on a rigid member's eliminated DOF |
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
| `test_kinematic_rotational_dofs_clamped` | `*KINEMATIC` DOFs above 3 are clamped to ccx's translational range; on 2-D (plane/axisymmetric) nodes to `1, 2` — an empty card too, and a `*KINEMATIC COUPLING` line `3, 3` is dropped (ccx holds DOF 3 of 2-D nodes itself and stops on a coupled one) |
| `test_surface_interaction_hard_behavior_synthesized` | an interaction without `*SURFACE BEHAVIOR` gets `PRESSURE-OVERCLOSURE=HARD`; one with a behaviour is left alone |
| `test_lamina_to_engineering_constants` | `*ELASTIC, TYPE=LAMINA` → `ENGINEERING CONSTANTS` (E3=E2, ν13=ν12, ν23 from G23) |
| `test_iso_elastic_with_ortho_expansion_becomes_engineering_constants` | an isotropic `*ELASTIC` beside `*EXPANSION, TYPE=ORTHO` → `ENGINEERING CONSTANTS` with the same stiffness (G = E/2(1+ν)) and a NOTE; it is left alone beside an isotropic expansion, as are engineering constants beside an ORTHO one |
| `test_iso_elastic_temperature_rows_for_ortho_expansion` | temperature columns kept; E alone varying needs no extra rows; E and ν varying get rows (E, ν linear in T) until the linearly interpolated stiffness is within 1e-4 between them |
| `test_elastic_for_aniso_expansion_becomes_aniso` | isotropic, engineering-constants and `LAMINA` `*ELASTIC` beside `TYPE=ANISO` → `TYPE=ANISO` (8/8/5 + T lines); the engineering constants' normal block inverts back to their compliance, the G's sit at D1212/D1313/D2323 |
| `test_elastic_left_alone_beside_expansion` | a kept `*PLASTIC` (ccx's nonlinear path) leaves the material alone, a commented-out one does not; an expansion affects only its own material; ν ≥ 0.5 is not rewritten and warned |
| `test_beam_section_unsupported_profile_commented` | `*BEAM SECTION, SECTION=I` (no ccx profile) is commented out with guidance |
| `test_equally_spaced_amplitude_expanded` | `DEFINITION=EQUALLY SPACED` expands to explicit time/amplitude pairs |
| `test_assembly_elset_element_member_uses_elem_offset` | an assembly `*Elset` member `I2.1` takes the element offset |
| `test_part_cohesive_section_remapped_per_instance` | a part-level `*Cohesive Section` elset is remapped per instance (`I1_COH`) |
| `test_combined_suffix_element_resolves` | combined suffixes resolve (`C3D8PT→C3D8`, `C3D20RHT→C3D20R`) |
| `test_initial_stress_expanded_to_integration_points` | `*INITIAL CONDITIONS, TYPE=STRESS` on an elset expands to one line per element and integration point |
| `test_initial_stress_geostatic_commented` | a `GEOSTATIC` initial stress (no ccx equivalent) is commented with guidance |
| `test_approximate_riks_and_default_off` | without the flag `*STATIC, RIKS` is commented out (ccx would silently run plain static) and points at the flag; `--approximate` turns it into plain `*STATIC` |
| `test_explicit_dynamics_native` | `*DYNAMIC, EXPLICIT` is kept in both modes (ccx integrates explicitly), Abaqus/Explicit-only controls dropped, and the step gets `INC=10000000` + `NLGEOM` |
| `test_circ_beam_explicit_increment_capped` | an explicit step in a deck with `CIRC` beams gets a maximum increment (4th data field): ccx's own Courant estimate with h = min(element length, d/√2), the square through the section's corner nodes — ccx's h = min(l, √2·d) (the box around the circle) runs them at about 1.3× their stable increment (NaN); a larger deck maximum is lowered, a smaller one or a shorter step period kept; an element shorter than d/√2 sizes it by its length |
| `test_circ_beam_explicit_increment_left_alone_or_warned` | implicit `*DYNAMIC` and `RECT` beams keep their data line; a fixed increment (`DIRECT USER CONTROL` → `DIRECT`) above the cap is warned (ccx's mass scaling for it is sized from the same overestimate); a `CIRC` material without a density is warned with the 0.12 d/c rule of thumb |
| `test_beam_circ_explicit_example` | the bundled `beam_circ_explicit` deck gets the cap 4.17e-07 (ccx alone picks 8.3e-7), all `B32`, no dangling refs |
| `test_approximate_nu_clamp` | `--approximate` clamps ν ≥ 0.5 to 0.475; without the flag ν is untouched |
| `test_approximate_ibeam_to_rect` | `--approximate` replaces an I-profile with the RECT of equal area and strong-axis inertia |
| `test_nonpositive_node_number_warns` | a mesh numbered from node 0 (invalid Abaqus input, issue #3) is flagged; a positive-numbered one is not |
| `test_history_card_outside_step_commented` | step data (`*CLOAD`) before any `*STEP` is commented out with the reason; model-data `*BOUNDARY` stays |
| `test_undefined_material_warns` | a section naming an undefined material is warned (with the defined names); a valid deck is not |
| `test_plane_node_rotational_bc_dropped` | DOFs 4–6 on plane-element nodes are dropped (`L,6,6` gone, `L,1,6`→`L,1,3`); shell nodes keep `1,6` |
| `test_rigid_coupling_on_shell_nodes_gets_knot_beams` | each shell node of a `*COUPLING`+`*KINEMATIC` gets a force-free knot beam (`B31` to a new free node, elset/material `ABQ2CCX_KNOT`, no density), without which ccx 2.23 rejects the rigid MPC; the rotations an empty `*KINEMATIC` couples are tied to the reference node's DOFs 4–6 by `*EQUATION` — not for a translations-only card, nor on a DOF with a `*BOUNDARY` (warned unless the reference node's own BC imposes it); solid members get no knots |
| `test_rigid_body_shell_tie_and_pin_members` | `*RIGID BODY` `TIE NSET` shell nodes get their rotations tied to the `ROT NODE`; `PIN NSET` nodes get knots but keep their rotations free |
| `test_coupling_with_shell_reference_node_becomes_rigid_body` | a kinematic coupling whose `REF NODE` is a shell node becomes a `*RIGID BODY` on the other coupled nodes whose `ROT NODE` follows the node's rotations (a moment on the node stays there); one that couples only some translations is warned instead |
| `test_rigid_coupling_knots_on_edges_trusses_and_thermal_decks` | an element-edge surface knots only its edge nodes; truss members get knots but no rotation ties; a thermal step gives the knot material a conductivity; a heat-transfer-only deck gets no rotation ties; an explicit step is warned |
| `test_kinematic_rotation_lines` | a rotations-only `*KINEMATIC` is not given the `1, 3` meant for an empty card; `*KINEMATIC COUPLING` rotation lines on shell nodes become rotation ties |
| `test_coupled_member_bc_implied_by_reference_dropped` | a `*BOUNDARY` on a rigid-coupling member DOF that the reference node's own BCs impose (that DOF, and no rotation about the other two axes: zero when the step starts, held through it) is taken off its card — a line keeping some nodes moves onto a set of them (`ABQ2CCX_BCn`); through a kinematic coupling a reference free to turn about z still imposes the members' z; not imposed (a free rotation, another value, a rotation held only from step 2) → kept and warned; an `OP=NEW` that removes the BC needs nothing; a zero velocity on the reference counts as held still from the first step on |
| `test_coupled_member_bc_conflicts_and_approximate` | a member BC the reference node's BCs do not impose stays and is warned (with the Abaqus semantics); `--approximate` drops it on a kinematic coupling (Abaqus/Standard ignores BCs on the DOFs a kinematic coupling eliminates), `[APPROX]`; on a `*RIGID BODY`, BCs that differ between the body's nodes (Abaqus stops on them too) stay a warning either way |
| `test_coupled_member_bc_shell_and_planar` | the `dheller1_uprofile` pattern: a coupled shell edge whose reference is one of its own nodes (→ `*RIGID BODY`), every edge node held in x, z and all rotations: the members' x and z BCs go, their rotations stay untied; 2-D: only the in-plane rotation counts, and BCs on DOF 3 of 2-D members go; with the reference node's rotation free, members' x at two heights move to it as Abaqus moves them (+ the rotation held, on the `ROT NODE`) |
| `test_rigid_body_member_bc_moved_to_reference` | identical BCs on a `*RIGID BODY`'s nodes that hold the same DOFs move to the reference node with zero rotations about the other axes, in the card that held them: a symmetry face (z, turns about x and y; the card's `AMPLITUDE` kept), a face held in all three directions (although one direction alone leaves a tilt; a line naming another node keeps it), a zero velocity; the `CAX4` cold-forging pattern — axis `XSYMM` implied in step 1, moved into step 2's `OP=NEW` card once the reference node is released; a shell edge `ENCASTRE`d (one line, but its rotation BCs hold the turn about it), its rotations tied to the body again; a tied rotation BC alone |
| `test_rigid_body_member_bc_move_inexact` | where the move would hold the body more than its BCs do it is warned (the reason, `--approximate`), and done with `--approximate` (`[APPROX]`): one in-plane direction on a flat face (a tilt left), a body free in the first step (it may have turned), a zero velocity against zero displacements after a free step; against the reference node's own BCs (another value; a later prescribed turn) or `FIXED`: never moved |
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
| `test_planar_constraint_repeated_after_op_new` | a `*BOUNDARY, OP=NEW` step that removes a BC repeats the planar constraint (OP=NEW removes model-data BCs too) and knots the clamp it re-specifies; one that removes nothing loses its OP=NEW and leaves the constraint as it is |
| `test_planar_constraint_needs_a_planar_model` | `B21` among 3-D elements, or with nodes off one z plane, gets no constraint and a warning |
| `test_planar_pinned_beam_example` | the bundled planar beam converts to 20 `B21` with DOF 3 on all 21 nodes and DOFs 4–5 at the pinned end, ahead of the steps, no dangling refs |
| `test_circ_beam_partial_rotation_bc_gets_knot_beam` | an element end node of a `CIRC` beam whose rotational BCs hold only some rotations (DOFs 1–4 at a pinned end, `XSYMM`), or a nonzero one (a prescribed rotation, even with all three given), gets a force-free knot beam (ccx 2.23 would lock its other rotations); the BC lines are kept; none for full zero clamps, `RECT` beams or a BC on a 3-node element's middle node |
| `test_circ_beam_rotation_knots_follow_steps_and_skip_unsafe_nodes` | a later `*BOUNDARY, OP=NEW` step that leaves only some rotations held gets knots; none on a node with a `*TRANSFORM` nor in a heat-transfer-only deck; an explicit dynamic step is warned instead (it stops on the knot beams); knots on most end nodes are warned (their rigid sections stiffen the beam) |
| `test_circ_rotation_bc_examples` | the bundled `beam_circ_rotation_bcs` deck gets knot beams at the two pinned ends whose twist is held and at the turned tip, none at the clamp; `planar_pinned_circ_beam` holds its twist at the first element's middle node, no knots; no dangling refs |
| `test_distribution_solid_lines_resolved_for_ccx` | a `*DISTRIBUTION` orientation on a `*SOLID SECTION`: default line first, an element-set label expanded, a later line winning, the origin subtracted and the `*ORIENTATION`'s rotation applied to the axes (no rotation line left), `*DISTRIBUTION TABLE` dropped; untouched lines keep their tokens |
| `test_distribution_name_ccx_reads_as_number` | names ccx 2.23 reads as numbers on an `*ORIENTATION` data line (`D1`, `E-3`, `Q1`, `1+2`, `12`, `.`, `INF`, 20 leading digits) are detected and the emitted distribution renamed; `E`, `D`, `1E`, `D_1` are left alone |
| `test_distribution_named_by_two_orientations_gets_two_copies` | two `*ORIENTATION`s naming one distribution get a copy each, listing only their own sections' elements |
| `test_distribution_flattened_per_instance` | a part's distribution per instance: its name and the orientation's reference to it prefixed, element labels offset, axes turned with a rotated instance |
| `test_composite_ply_orientation_named_per_instance` | a composite ply line naming one of the part's orientations names the instance's copy; a ply angle is kept |
| `test_shell_general_section_copied_per_instance` | a part's `*Shell General Section` (thickness + material, and composite) is copied per instance: a `*SHELL SECTION` on each instance's own set, naming its copies of the orientations, also on ply lines; a ply angle turns the instance's own (rotated) axes; no dangling refs |
| `test_distribution_shell_section_split_per_direction` | a shell section on a distribution orientation → one element set, plain `*ORIENTATION` and section per direction; composite plies: an angle turns the group's axes, a ply may name a distribution orientation of its own |
| `test_distribution_without_data_comments_out_its_orientation` | a distribution with no data (missing `INPUT=` file): its orientation is commented out with the reason |
| `test_distribution_not_named_by_an_orientation_commented` | a distribution no `*ORIENTATION` names (a shell-thickness/material distribution in Abaqus) is commented out |
| `test_distribution_plate_examples` | the `distribution_*_plate` validation pairs: one resolved distribution per instance (default + 10 elements), the S8R panel split into 16 sections, the explicit decks free of distributions; no dangling refs |
| `test_op_new_that_removes_nothing_is_dropped` | a later step's `*BOUNDARY, OP=NEW` cards that re-specify every BC in effect lose their OP=NEW (one `** [abq2ccx]` comment per step; a changed value is no removal), after rotational BCs on beam or shell nodes; kept in the first step, without rotational BCs on shell/beam nodes, and after `*DYNAMIC` steps |
| `test_op_new_that_removes_bcs_makes_knots` | an OP=NEW that removes a BC stays and the beam clamp it re-specifies gets a knot beam (`ABQ2CCX_KNOT`); a beam node whose rotations it releases gets none unless a later step fixes them again; shell nodes with rotational BCs before it always get one |
| `test_op_new_knots_skipped_with_explicit_steps` | with an explicit step in the deck no knot beams are added (they stop ccx's explicit solver), and the removal is warned |
| `test_op_new_examples` | the two OP=NEW validation decks: no OP=NEW left where step 2 removes nothing; where it removes the prop, OP=NEW stays and the beam root and the five plate root nodes are knots; no dangling refs |
| `test_mpc_lines_converted_one_by_one` | an `*MPC` card keeps its convertible lines (`PIN` → `*EQUATION` on DOFs 1–3) and comments out only the `SLIDER` and user (`99`) lines; node sets pair node by node in ascending order or with a single second node, and mismatched sets comment that line out; an MPC on a node with a `*TRANSFORM` is warned |
| `test_mpc_tie_ties_rotations_between_knots` | `TIE` between two beam nodes knots both and ties all six DOFs; with a solid or free node only DOFs 1–3; a coupled temperature-displacement step adds DOF 11 |
| `test_mpc_link_linearised_or_ccx_beam` | `LINK` without `NLGEOM` → the linearised `*EQUATION` (direction cosines, largest component first); under `NLGEOM` → ccx `*MPC BEAM`; on beam nodes under `NLGEOM`, or in a linear-then-`NLGEOM` deck, commented out (the latter converted with `--approximate`, `[APPROX]`) |
| `test_mpc_beam_lines_become_rigid_bodies` | `BEAM` lines sharing an independent node, or chained through one another, become one `*RIGID BODY` with a `ROT NODE`; shell members get knots and rotation ties; rotational BCs on the independent node move to the `ROT NODE`; a shell independent node's own rotation drives the `ROT NODE`; a node dependent twice is warned and its later line commented |
| `test_rigid_member_bcs_the_body_implies_are_left_out` | zero BCs on rigid-body members are taken off where the reference node is held in that DOF and cannot rotate (the `SYM` line moves onto a set of its other nodes); not when the body may turn or a value differs, and a BC that `OP=NEW` releases before any step keeps it is left alone; a body of plane-strain nodes needs only DOF 6 held, and is warned in a deck with an explicit step |
| `test_bc_steps_follow_op_new` | the BCs in force per step: kept from earlier steps, a later value replaces an earlier one, `OP=NEW` starts from none |
| `test_rotation_tie_on_a_member_bc_makes_the_body_dependent` | a shell member's rotation under a BC: on a `*RIGID BODY` it moves to the `ROT NODE` (the tie keeps the member dependent); where it stays on the members (BCs that differ, warned) the `ROT NODE` DOF becomes the first tie's dependent term and the second tie is dropped; on a `*KINEMATIC` reference node (whose DOFs 4–6 ccx eliminates itself) the tie is dropped instead |
| `test_coupling_bc_bars_example` | the `coupling_bc_bars` validation deck: bars A and C lose their 27 redundant end-face BCs, bar B (the same constraints without a coupling) keeps its own; no warnings, no dangling refs |
| `test_rigid_body_bc_bars_example` | the `rigid_body_bc_bars` validation deck: bar A's far-face `u1 = 0` is taken off in step 1 and moved to its reference point (+ `ROT NODE` 2–3) in step 2's `OP=NEW` card, card for card the BCs bar B has by hand; no warnings, no dangling refs |

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
* **`coupling_bc_bars`** — three `C3D8` bars in one `NLGEOM` step whose coupled end faces
  also carry BCs that the reference point's own BCs impose (ccx stops on such a BC; the
  converter takes it off). Bar A, its reference guided along z, must match bar B — the same
  constraints written as BCs and `*EQUATION`s, no coupling — to 1e-9 (they agree to 2e-18 of
  |u|); bar C's end face, turning about z under a moment, must keep the dropped u3 = 0 (it
  does to 7e-21 while it moves 0.77).
* **`beam_circ_rotation_bcs`** — two `B31` beams with a circular section, which ccx 2.23
  runs as `B32`: one pinned at both ends with its twist held there and a mid-span load, one
  clamped with its tip turned by a prescribed rotation of 0.001 rad. Under a rotational BC
  ccx ties a circular section to its corners and locks the rotations the BC leaves free
  (without the converter's knot beams the first deflects 0.31 of beam theory, the second
  0.76); checks the mid-span deflection, −12.658 vs P L³/(48 E I) = −12.631 (0.2 %), and
  the tip deflection, +0.5004 vs θ L/2 = +0.5 (0.1 %).
* **`beam_circ_explicit`** — a simply supported `B31` beam with a circular section
  (L = 240, r = 10, six elements, each twice the diameter) in a `*DYNAMIC, EXPLICIT` step:
  a mid-span load rises with a `SMOOTH STEP` over about three periods and is then held.
  ccx 2.23 sizes a `CIRC` beam's stable increment as if its section were the box around
  the circle and picks 8.3e-7, about 1.3× the limit: the displacements turn NaN. With the
  converter's maximum increment of 4.17e-7 the beam ends at −0.1756 vs Timoshenko beam
  theory −0.1773 (1.0 %; ccx's static solution of the same mesh is 0.992 of it).
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
* **`distribution_solid_plate`** vs **`distribution_solid_plate_explicit`**, and
  **`distribution_shell_plate`** vs **`distribution_shell_plate_explicit`** — per-element
  fibre angles from a `*DISTRIBUTION`, as in a variable-angle-tow layup, against the same
  model written with one `*ORIENTATION` and one section per element (a form ccx runs
  unchanged). The `C3D8` plate has two instances (one translated and rotated about an
  inclined axis), a default line, an element-set line and a 10° additional rotation; the
  composite `S8R` panel is a rotated instance whose plies follow +θ and −θ paths from two
  distributions, one ply at 90° to the section orientation. Every node's displacement must
  agree within 1e-6 of max |u| (they agree to 3e-11 and exactly). Converted without the
  rotation built into the axes, the plate misses by 21 %; with the shell section left to
  ccx's own distribution handling, the panel misses by 62 %.
* **`mpc_beam_lever`** — three B31 cantilevers: one carries a rigid lever (`*MPC BEAM`,
  converted to a `*RIGID BODY` on the knotted tip node) loaded at its end, one the
  statically equivalent tip force and moment, one a 10⁴× stiffer beam as the lever. The tip
  and lever-end deflections match statics within 0.04 % (−3.2488 / −4.2982 vs −3.25 /
  −4.30) and the two references within 4e-5. A variant at ten times the load under
  `NLGEOM` (about 27° at the tip) matches the stiff-beam lever within 5e-7 and keeps the
  lever's length to 5e-8.
* **`mpc_pin_tie_joints`** — two-span beams joined at coincident nodes by `*MPC PIN` (a
  hinge: w = −1.2494 vs (P/2) L³/(3EI) = −1.25) and by `*MPC TIE` (a rigid joint: one
  propped cantilever, −0.4185 vs −0.4199); worst 0.33 % over both spans. Without the knots
  the `TIE` gives the `PIN` result: ccx ignores DOFs 4–6 of a plain beam node in an
  `*EQUATION`.
* **`mpc_link`** — a node held by a `*MPC LINK` and a spring perpendicular to it: the
  linearised `*EQUATION` gives statics exactly ((P·n)/k n); under `NLGEOM` with a large
  load ccx's `*MPC BEAM` keeps the length to 1e-8 while the link turns 24.5°.
* **`equation_overconstraint`** — a deck ccx rejects as written: an `*EQUATION` whose first
  DOF has a BC, its duplicate, and a loop of three ties. Converted, it solves with the tied
  node held and the loop's nodes moving together (ccx, given the whole loop, holds it at
  zero).
* **`op_new_respecify`**, **`op_new_remove`** — a clamped `B31` cantilever and a clamped `S4`
  plate whose step 2 has `*BOUNDARY, OP=NEW`. In the first, step 2 re-specifies every BC
  (OP=NEW is dropped), doubles the beam's tip load and prescribes the plate tip z = 2: the
  beam tip moves 1.1898 (beam theory 1.1905, 0.05 %) and the plate tip exactly 2. In the
  second, step 2 removes the beam's mid-span prop (the clamped nodes become knots): the beam
  tip moves 0.5910 (beam theory 0.5952; the knot stiffens the clamp by 0.7 %) and the plate
  tip as in step 1, to 1e-4. Converted as they were, ccx gives 3.7e5 and 0 (the prescribed
  value lost), 1.9e5 and 2.2e9, and the checks fail.
* **`thermal_expansion_cubes`** — three heated unit cubes whose isotropic `*Elastic` sits beside
  an orthotropic or anisotropic `*Expansion`, whose stiffness ccx 2.23 gets wrong in linear
  steps once temperatures are defined (the converter writes the `*Elastic` as
  `ENGINEERING CONSTANTS` / `ANISO`): a free cube with its material system turned 30° about
  z and a free one with an ANISO expansion, against the analytic strain R diag(α ΔT) Rᵀ
  (exact), and a cube held in x whose E and ν vary strongly with temperature, read at
  T = 90 between the given rows: σ_xx = −1.71000 vs −E α_x ΔT = −1.71 and ε_yy, ε_zz within
  1e-6. Converted without the rewrite, the free cubes shrink (a displacement of −964 where
  +0.0011 is right); without the added temperature rows the held cube is 0.6 % / 1.4 % off.
* **`rigid_body_bc_bars`** — two `C3D8` bars clamped at x = 0 whose end caps (x = 4..5) are
  `*RIGID BODY`s on their elements, in two `NLGEOM` steps. Bar A's cap has `u1 = 0` on its
  far face (ccx stops on a BC on a rigid-body node): implied in step 1, which holds the
  reference point, and moved to the reference point with zero rotations about y and z in
  step 2, whose `OP=NEW` releases it (four face nodes hold the same). Bar B has the same BCs
  on its reference point by hand. Under a moment about x and a force along y the caps twist
  25°: A must match B to 1e-9 (they agree to 1e-20 of |u|), and A's far face must keep
  u1 = 0 (it does to 9e-21 while it moves 0.51).
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
references; **219 solve** in CalculiX and **219 mesh-only decks are accepted** by it. The
other 584 convert cleanly but use features ccx cannot run (user elements, UMAT/VUMAT and
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
beams). Coupled DOFs that also carry a `*BOUNDARY`: *BCs on coupled nodes*, below.

**Abaqus `*MPC` and overconstraints.** `*MPC` used to keep only `PLANE`/`STRAIGHT` and
`TIE`; any other line commented out the whole card, so four gated decks ran with their
`BEAM` MPCs missing. Each line is now converted on its own. Probed on 2.23:

* ccx's `*MPC BEAM` is a **distance** constraint — Abaqus `LINK`, not Abaqus `BEAM`: a node
  swung by a prescribed motion keeps its distance to the other to 1e-6. ccx rejects it on
  any node of a beam, truss, shell, membrane or plane element, knot or not ("nodes belonging
  to 1D/2D elements must not be subject to a BEAM MPC"), and switching its dependent DOF
  when a link passes 45° to the axis of that DOF stalls the increment. A coincident free
  node tied to a beam node by `PIN` equations does not get around it: the linear equations
  depend on the nonlinear MPC's dependent DOF and ccx's result breaks the tie. So `LINK`
  becomes its linearised `*EQUATION` in a deck without `NLGEOM` (what Abaqus solves there),
  ccx's `*MPC BEAM` under `NLGEOM`, and is commented out on beam/shell/plane nodes under
  `NLGEOM` (or, without `--approximate`, in a linear-then-`NLGEOM` deck: ccx's distance MPC
  runs every step geometrically nonlinear).
* Abaqus `BEAM` (displacements *and* rotations) → one `*RIGID BODY` per independent node;
  lines chained through a node are one body, since rigid links compose. Exact at any
  rotation, and on shell/beam nodes through the knot beams. The barrel-vault deck's four
  coincident shell node pairs then match an exact linear-equation tie of the same model to
  all printed digits.
* A `TIE` on two plain beam nodes ties nothing beyond the translations: two spans tied by
  six equations deflect exactly like the pinned hinge. Knots make the rotations tie (the
  `TIE` spans then match one continuous beam within 0.3 %).
* ccx eliminates an `*EQUATION`'s first term. Where that DOF has a BC or is another
  equation's, a free term now goes first (a bipartite matching, deck-wide, including the
  converter's own equations); an equation that reduces to 0 = 0 given the earlier ones and
  zero BCs is dropped. A **closed loop** of ties (u1 = u2, u2 = u3, u3 = u1) is not rejected
  by ccx: it warns "zero coefficient on the dependent side" and returns zero displacements —
  a silent wrong result the converter now prevents.
* A `*BOUNDARY` on a rigid constraint member's eliminated DOF is taken off where the
  reference node's own BCs impose it anyway, and warned otherwise: *BCs on coupled
  nodes*, below.

Corpus: `dheller1_uprofile` now solves (it stopped on the cascade). Of the four gated
`BEAM` decks, the hood-hinge modal deck and the barrel vault still solve and now carry the
constraint (in all ten hood modes every BEAM group moves rigidly with its reference node
to 7e-7). The two `davidmorin` patches (`uexternaldb`, `usdfld_v2`) lost their gate: their
earlier "solve" left the loaded reference point unconnected (a zero-load run); with the
constraint carried, the `*BOUNDARY, TYPE=VELOCITY` the converter reads as a displacement
(100 instead of the ~0.95 the velocity integrates to) stretches the patch until ccx stops.
With that displacement corrected by hand, `uexternaldb` solves with the edge following its
reference point exactly and `usdfld_v2` necks at 15 % stretch. Six NASA CompDam decks get
past `*ERROR in cascade` / "two different MPC's" and stop on their VUMAT (one on an
unsupported `*DLOAD TRVEC5`); `marcello_gori_job_1_3` (a coupling whose reference node is
free while 38 coupled nodes are clamped) and `sahmotaman_coldforging` (die nodes on the
axis keep their BC in steps where the die is released) still stop there by default (both
are taken up below, the second only in part). The explicit `davidmorin` decks now stop on
ccx's explicit-MPC limit instead of running past the time limit without their constraint.
Net: 220 → 219 solving (+1, −2).

**BCs on coupled nodes.** ccx makes the coupled DOFs of every rigid-coupling member the
dependent side of an MPC (and the converter's rotation ties do the same for shell/beam
rotations), so a member that also has a `*BOUNDARY` on such a DOF stops ccx: `*ERROR in
cascade: the DOF corresponding to node N in direction d is detected on the dependent side
of a MPC and a SPC`. Abaqus resolves the overconstraint — for `*RIGID BODY` it moves
identical BCs on the dependent nodes to the reference node (adding zero rotations about the
other axes) and stops if they differ; a kinematic coupling eliminates the coupled DOFs at
its nodes, so Abaqus/Standard does not apply a BC there and warns. The converter now
removes such a BC where the reference node's own BCs impose it anyway: the same value on
that DOF, and no rotation about the other two axes in that step or any before it (2-D: about
z). That is exact in linear and `NLGEOM` steps alike — the member's displacement along d is
u_ref,d + (θ × r)_d, and a finite rotation about axis d leaves component d alone — and
Abaqus' own resolution gives the same model. A zero velocity counts as held still from the
first step on; BCs on DOF 3 of plane/axisymmetric members go too (Abaqus has no such DOF,
ccx's 2-D rigid body makes it dependent). The rigid bodies of `*MPC BEAM` lines count as
rigid constraints too. A member's rotation BC that the reference imposes stays, and the
rotation tie is dropped (the BC governs it); one it does not impose turns the tie round on a
`*RIGID BODY`, so the body follows the member's BC, as Abaqus moves it to the reference
node. Probed on 2.23:

* a `C3D8` bar with its end face under `*RIGID BODY` and a fully fixed reference vs the same
  bar encastred at that face, and under `*COUPLING` with the reference guided along z vs the
  same constraints as BCs and `*EQUATION`s: identical displacements (max |Δu| = 0); under
  `NLGEOM` with the end face turning about z, the dropped u3 = 0 holds to 3e-20;
* `CPE4` and `CAX4` strips with an edge under `*RIGID BODY` or `*COUPLING`, the reference
  held in x and about z: the members' x BCs dropped give identical results; these also showed
  that an empty `*KINEMATIC` must couple `1, 2` on 2-D nodes — `1, 3` stopped every 2-D
  coupling on DOF 3, which ccx holds fixed itself — now fixed;
* `dheller1_uprofile` (`S4R` U-profile whose end section is coupled to one of its own
  nodes, every end node held in x, z and all rotations): 222 member BCs dropped; identical
  to the same deck with those BCs restored and the coupling replaced by `*EQUATION`
  u2 = u2(ref) (max |Δu| = 0 over all 4592 nodes). Without the knot beams the same
  constraints differ by 4.9e-4 of |u| — ccx makes the shell normal rigid at a knot.

`dheller1_uprofile` solves this way (counted above). Where the reference node's BCs do not
impose a member's BC, the converter warns ("Possible overconstraint: node N DOF d follows reference
node R …") and leaves it. With `--approximate` it drops it on a kinematic coupling or an
`*MPC`, as Abaqus/Standard does (`[APPROX]`): `marcello_gori_job_1_3`, whose coupling surface overlaps
the encastred face at 38 nodes, then solves. On a `*RIGID BODY` the converter makes
Abaqus' move itself (next paragraph). The other decks with BCs on coupled nodes
(`frodal_axisymmetric_*`, `sahmotaman_upsetting`, and all but two BCs of
`jasiuk_research_group_boundarycond_2`, whose punch moves along z) are resolved and stop at
their next blocker (an undefined material or amplitude, UMAT, a damage criterion).

**BCs on rigid-body nodes, moved to the reference node.** For the `*RIGID BODY` member BCs
the reference node's own BCs do not impose, the converter now does what Abaqus/Standard does
("Overconstraint checks", Analysis User's Guide): if the BCs on a DOF are identical over the
body's nodes (else Abaqus stops) and agree with the reference node's own (else Abaqus stops),
they move to the reference node, with zero rotations about the other axes to make up for the
removed displacement constraints; the reference node's own BCs stay. The moved lines go into
the card that held the member's BC, so its step, `OP`, amplitude and type stay, and the
rotations reach a `ROT NODE` (or a shell/beam reference node's own DOFs 4–6). That reproduces
the model as written only where the BC'd nodes hold what the moved BCs hold. In the body's
rigid motion u_m = u_ref + θ × r_m a member BC on DOF d is the row [e_d, r_m × e_d]·(u_ref, θ)
(a BC on a tied shell/beam rotation is the row of that body rotation); with the reference
node's own BCs, these rows must span every moved one. A face normal to z held in z spans
u_z, θ_x and θ_y — the manual's symmetry-plane example; the same face held in x alone leaves
it a first-order tilt about y that the moved θ_y = 0 would fix, held in all three directions
it fixes the body entirely. Under `NLGEOM` this holds along the whole path where the moved
model holds every rotation at zero (2-D, two or more DOFs moved, the remaining one held);
with a single DOF d moved and the body free to turn about e_d, the members' rows alone must
hold the other two rotations (their projections normal to e_d not collinear), which a turn
about e_d leaves as it is. The body must also be unturned when the step starts — zero at
the end of the previous step under a zero displacement, a zero velocity from zero, or such
member BCs — or the BC values ramp from a turned position. Only then is the move made by
default ("Exact."); otherwise it is warned with the reason, and `--approximate` makes it as
Abaqus does (`[APPROX]`). The same start-of-step rule now decides when a member BC is
implied, too: the reference node's BCs must hold the rotations through the step, and a
step that ended with them at zero is enough — before, every step from the first had to
hold them. Probed on 2.23 (the literal model run as a cap 10⁶ times stiffer than the bar,
carrying the member BCs, no rigid body):

* `C3D8` bar with a rigid end cap whose far face has u1 = 0 (members) vs the same BCs on
  the reference point by hand (u1, rotations about y and z): identical (max |Δu| = 0) in a
  linear step and in an `NLGEOM` one where the cap twists 25°, the far face keeping
  u1 = 0 to 1e-20; against the literal model 5e-7 of |u| (the stiffness ratio). With u1 = 0
  on one edge line of the face instead, Abaqus' move changes the bar's response by 22 % —
  why that case needs `--approximate`;
* `CAX4` billet with a rigid cap whose axis nodes keep `XSYMM` while the reference point is
  held in step 1 and released in step 2 (the cold-forging pattern), linear and `NLGEOM`:
  identical to the BCs on the reference point by hand (max |Δu| = 0), and 2e-7 from the
  literal model.

Across the corpus 3 converted files change (conversion time unchanged), none of them
solving before or after. `sahmotaman_coldforging`: the axis `XSYMM` of `Die1` and `Punch1`
moves exactly once their reference nodes are released (13 DOFs); `Die2` and `Punch2`, free
in the first steps (and `Punch2`'s zero velocity meeting the axis displacement BC), move
only with `--approximate`. `abuganza_square_expander` encastres the 441 nodes of a body that
is free in its first two steps: `--approximate` only. `jasiuk_research_group_boundarycond_2`
only states its conflict precisely (two pole nodes held in z against the reference node's
velocity along z). Both of the first are UMAT decks, so neither solves.

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
("*ERROR in calcstabletimeincvol"), so there it is only warned (the NaN displacements ccx's
explicit solver gave `CIRC` beams even without such a BC have their own cause: below). No
corpus deck has such a BC, and every corpus deck converts byte-identically;
`validate_with_ccx.py` checks both 3-D cases and the planar beam against beam theory.

**Circular-section beams in explicit dynamics.** Under `*DYNAMIC, EXPLICIT` ccx 2.23
returned NaN displacements for `CIRC` beams (`B32` and `B32R`, with and without `NLGEOM`),
where the same beam with a `RECT`, `PIPE` or `BOX` section runs. The cause is the stable
increment ccx estimates (`calcstabletimeincvol`): per element critom·h·0.3/(2c) times a
safety factor 0.8/1.3, with c the dilatational wave speed and h the smallest ratio of the
one-point volume to a face area of the 20-node brick the beam expands into. A circular
section puts that brick's corner nodes at 45° on the circle and its midside nodes on the
section axes (`gen3dfrom1d`), so the one-point volume is the circumscribed box's while the
side faces are measured by their corner chords: h = min(l, √2·d) for element length l and
diameter d, where a d × d rectangle gives min(l, d). Bisecting the maximum increment (the
data line's 4th field, which ccx honours) over `B32`/`B32R`, d = 10–80, l = 5–100,
ν = 0–0.49 and `NLGEOM` on and off puts the stable limit at the formula with h = 1.01–1.17·d
once l > d (ccx picks 1.2–1.4× it where l ≥ √2·d, 1.3× for steel), while for l ≤ d ccx's
own increment holds. The converter therefore caps each automatic explicit increment at
ccx's formula with h = min(l, d/√2), the square through the section's corner nodes: at
least 1.4× below the probed limit where ccx's estimate fails, and never above ccx's own
estimate (ccx still picks a smaller increment where other elements need one). Capped, a
`CIRC` beam behaves like a `RECT` one: under a load ramped up and then held, both oscillate
with a 5 % longer period in explicit than in implicit dynamics (ccx's lumped mass), and a
load raised smoothly over three periods leaves the beam at its static deflection. A fixed
increment (`DIRECT`) above the cap is only warned: ccx's mass scaling for it is sized from
the same overestimate, and the run still diverged at 1.2× and 2.4× ccx's estimate. No
corpus deck has beams in an explicit step, and every corpus deck converts
byte-identically; `validate_with_ccx.py` checks a `CIRC` beam's end deflection in an
explicit step against beam theory.

**Per-element (`*DISTRIBUTION`) orientations.** Abaqus gives each element its own material
axes through a `*DISTRIBUTION` that an `*ORIENTATION` names (CAE discrete orientations,
TexGen yarn directions, variable-angle-tow layups). ccx 2.23 has the feature, but probing
it with small decks — a free cube with orthotropic thermal expansion strains along its
material axes, so each element's axes can be read off its displacements — and reading its
distribution, orientation and section readers showed that it implements only part of it:
each distribution line becomes an orientation of its own, which `*SOLID SECTION` hands to
its element (the elements a distribution does not list get its first line); the
`*ORIENTATION` naming the distribution takes all its lines, so a second one naming it stops
ccx; a name ccx can read as a number (`D1`, `E5`, `12`) silently gives an all-zero
orientation and a singular stiffness matrix; an origin after `a, b` is ignored; an
additional-rotation line turns only the first line (each later one gets the angle converted
to radians again); and `*SHELL SECTION`, plain or composite, gives every element the first
line, so its results equal those of one uniform orientation. The converter used to pass the
distribution through, renamed per instance while the `*ORIENTATION` kept the old name (and
ccx stopped: "distribution … has not been defined"), with element labels not offset and axes
not turned with a rotated instance; composite plies synthesized from a distribution
orientation used a fixed x-y frame. Each orientation now gets its own distribution, resolved
to one line per element of its solid sections, and each shell or membrane section using one
is split per direction; `validate_with_ccx.py` checks both against the per-element form. The
same work fixed composite ply lines that name an orientation inside a part: they kept the
part-level name after flattening. Of the seven corpus decks with a distribution
orientation, none starts solving — they now get past the distribution and stop on what
remains: the five TexGen decks' distribution data lives in `.ori` files not in the corpus,
`shridharbailkeri_solid_plate_cfrp` has a composite section on continuum shells (no layered
solid section in ccx) and a HASHIN damage criterion ccx rejects, and
`vineethravi2310_tensile` has a UMAT and a composite solid section.

**Shell general sections in parts.** Flattening copies a part's sections per instance onto
the instance's renamed sets, but left out `*Shell General Section`: it was emitted once with
the part's own set and orientation names (`PANEL`, while the instances' sets are `I1_PANEL`
and `I2_PANEL`), so ccx stopped on the undefined set or orientation and no instance had a
section; one inside an `*Instance` block was dropped without a trace. It is now copied per
instance like a `*Shell Section`, its composite ply lines naming the instance's orientations.
Probed on 2.23 with an `S8R` lamina plate (fibres at 30°) as a part with two instances, one
turned 90° about z: both instances give the displacements of the same plate written without
parts, exactly, in the thickness + material form and in a composite form with a ply on a
second orientation and a 90° ply (with I2's section on I1's orientation, they miss by 138 %
of max |u|). No corpus deck has such a section (the one deck with a `*Shell General Section`
has no parts), and all 1073 corpus files convert byte-identically.

**`*BOUNDARY, OP=NEW` after rotational BCs on shells and beams.** ccx applies a rotational
BC on a shell or beam node that is not a knot through a mean-rotation MPC over the expanded
nodes, whose angle is a hidden SPC (`gen3dboun.f`, run again after each step is read). A
later step's `*BOUNDARY, OP=NEW` deletes every user SPC — the hidden one too — but keeps the
MPC, and the MPC for the re-specified BC finds no free dependent DOF (`*WARNING in usermpc:
no MPC is generated for the mean rotation in node 1 and direction 5`): that rotation is
free. Probed on 2.23 with a clamped cantilever (L = 1000, 20 elements, `RECT` 20 × 40, tip
load 10) clamped again with OP=NEW in step 2: the tip deflection went from 0.5949 to
1.87e5 (`B31`; `B31R`, `B32` and `B32R` alike; a third such step lost a second rotation),
a following `*FREQUENCY` step found a 0.10 Hz mode (16.72 Hz with the clamp) and `*BUCKLE`
factors of 0.997–1.003 (13822), and an `NLGEOM` step never converged. On `S4`, `S4R` and
`S8R` plates the clamp went as well (tip deflections of 1e8–1e9, a 0 Hz mode), and since ccx
keeps the hidden SPCs' indices for shells, OP=NEW's compaction made them zero unrelated
BCs: a prescribed tip displacement of 2 came out 0 — without any message. OP=NEW in the
first step is harmless (ccx builds the MPCs after reading a step), and so are `*DYNAMIC`
steps (ccx makes knots there) and `*CLOAD, OP=NEW` on moments; a rotation that OP=NEW
releases, or one first given after it, works. So from the second step on, once shell/beam
nodes have had rotational BCs, an OP=NEW whose step re-specifies every BC in effect — it
removes nothing — is dropped: both codes then hold the same model, and ccx updates the
re-specified values and amplitudes in place. Where OP=NEW does remove BCs, the shell nodes
that had rotational BCs before it, and the beam nodes that had them before it and get them
again, get a knot beam as for rigid couplings: ccx then carries their rotations on the
knot's rotation node, whose BCs OP=NEW removes and re-applies cleanly. The knot is exact on
shells (deflections and frequencies to 6 digits) and holds a beam section rigid at the node,
as beam theory does, so a clamped `B31` is 0.65 % stiffer than with ccx's own clamp and a
`B32R` 0.1 %. A deck with an explicit step gets a warning instead: the massless knot beams
stop ccx's explicit solver (`*ERROR in calcstabletimeincvol`). Of the 16 corpus decks that
use OP=NEW with shells or beams, 12 use it in their first step only; in later steps the two
`igrega348` lattices prescribe only reference nodes and `juliafem_plate_with_hole` (which
removes a BC in step 2) has no rotational BCs, so neither is affected, while
`oyvindwpetersen_frame_structure` re-specifies its supports' DOF 4 in step 2. Its OP=NEW is
dropped — the only corpus deck that converts differently — but it still stops before that,
on its `SECTION=RECTANGULAR` (with `RECT`: `*ERROR in cascade` in step 1).
`validate_with_ccx.py` checks both repairs on a clamped beam and plate.

**Isotropic elasticity with orthotropic thermal expansion.** Found while probing
distribution orientations: in a linear step ccx 2.23 gives a free cube with an isotropic
`*ELASTIC` and `*EXPANSION, TYPE=ORTHO` (α = 1e-3, 2e-3, 4e-3) strains of −2.2, −2.0 and
−1.6, with or without an `*ORIENTATION` and on every element family tried (continuum,
shell, membrane, plane, axisymmetric, beam, truss). Its stress routine stores the
stiffness of such a material in orthotropic form, while the element stiffness still
reads it as (E, ν) — E becomes λ + 2μ and ν becomes λ, a negative bulk modulus; a fully
clamped cube even shows the right stress. The stiffness is wrong for any load once the
deck has temperatures: a cube pulled at an unchanged temperature contracts sideways by
0.25 instead of 2e-4, and its frequencies are 17 times too low (without temperatures it
is right). The same stiffness as `ENGINEERING CONSTANTS` is exact in every case. Probing
the rest of the matrix showed that engineering constants do not help with `TYPE=ANISO`
(wrong shear strains without an `*ORIENTATION`), that `TYPE=ANISO` elasticity is right
with every expansion, that `*PLASTIC` / `*CREEP` materials and `NLGEOM` steps were never
affected (and ccx rejects `ANISO` elasticity with `*PLASTIC`), but also that under
`NLGEOM` a turned non-isotropic expansion is wrong with any elastic type. ccx interpolates the converted stiffness, not E and ν, between temperature rows: up
to 8 % off mid-interval for a table whose E triples while ν goes 0.2 → 0.3, so rows are
added until the two agree to 1e-4 (a steel-like table, E 210 → 180 GPa and ν 0.30 → 0.32,
needs 3). A prescribed general strain gives the same stresses with the original and the
rewritten `*ELASTIC` (isotropic, orthotropic, engineering constants with three different
G's, `LAMINA`). No corpus deck has the combination (four have an ORTHO expansion, beside
engineering constants or a user material); all 1073 corpus files convert byte-identically.

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
