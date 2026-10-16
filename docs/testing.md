# Testing

The converter has three layers of tests:

1. **Unit tests** — fast, no solver needed, run on small controlled fixtures and the
   bundled examples.
2. **End-to-end solver validation** — converts the example decks and runs them in
   CalculiX, checking the NAFEMS LE10 benchmark numerically.
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

## 1. Unit tests — `tests/test_convert.py` (70)

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
| `test_contact_pair_default_type` | `*CONTACT PAIR` gets the required `TYPE=SURFACE TO SURFACE` (Abaqus default) and Abaqus-only params are dropped |
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
| `test_approximate_riks_and_default_off` | `--approximate` turns `*STATIC, RIKS` into plain `*STATIC`; without the flag the card is kept and points at the flag |
| `test_approximate_explicit_to_implicit` | `--approximate` turns `*DYNAMIC, EXPLICIT` into implicit `*DYNAMIC` with a period/1000 initial increment |
| `test_approximate_nu_clamp` | `--approximate` clamps ν ≥ 0.5 to 0.475; without the flag ν is untouched |
| `test_approximate_ibeam_to_rect` | `--approximate` replaces an I-profile with the RECT of equal area and strong-axis inertia |
| `test_nonpositive_node_number_warns` | a mesh numbered from node 0 (invalid Abaqus input, issue #3) is flagged; a positive-numbered one is not |

## 2. End-to-end validation — `validate_with_ccx.py`

Auto-detects `ccx` (including the binary bundled with FreeCAD), converts each example
deck and runs it in CalculiX:

* **`nle10_thickplate`** — the NAFEMS LE10 benchmark: checks σ_yy at point D against the
  published −5.38 MPa reference (the converted deck gives −5.65 MPa, a 5 % difference
  in line with the element type and mesh — proving the whole pipeline is correct, not
  just well-formed).
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

**Results:** all 1022 convert with zero dangling references; **199 solve** in CalculiX
and **214 mesh-only decks are accepted** by it. The other 609 convert cleanly but use
features ccx cannot run (user elements, UMAT/VUMAT, explicit dynamics, cohesive/connector
elements, piezoelectric/acoustic coupling, other user subroutines) or are CAE part
fragments / incomplete or invalid source decks (e.g. externally-supplied `<parameter>`
values, or nodes numbered from 0) — and each was verified to fail *no worse than the
original, unconverted deck*.

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
