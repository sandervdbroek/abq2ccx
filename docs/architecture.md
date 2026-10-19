# Architecture & developer guide

How `abq2ccx.py` is structured internally, and how to extend it. The file is one
self-contained module organised top-to-bottom into the sections below.

## Pipeline

```
read_blocks()          tokenize text -> list[Block]   (follow *INCLUDE, resolve *PARAMETER,
                                                        splice keyword-line continuations,
                                                        strip ** comments, normalise GEN/PERT/AMP)
        │
        ▼
Converter._cartesian_nodes()   *NODE, SYSTEM=C / S coordinates -> Cartesian
        │
        ▼
flatten_assembly()     *PART/*INSTANCE/*ASSEMBLY -> flat list[Block]   (only if present)
        │
        ▼
Converter.build_geometry()   Pass A: walk blocks in order, fill the geometry registry,
                                     expand *NGEN/*NCOPY/*ELGEN/… to explicit nodes/elements
        │
        ▼
Converter._drop_surface_elements()   surface elements (SFM*) leave the registry; their
                                     loads become nodal forces later
        │
        ▼
Converter._plan_incompatible_slabs()   CPS4I / CPE4I -> C3D8I slabs (top nodes, *EQUATION
                                       ties, held DOF 3, plane-stress ORTHO material) where
                                       exact; otherwise CPS4 / CPE4 as reduced physics
Converter._plan_rigid()   rigid elements -> skin solids of their rigid body, analytical
                          surfaces meshed into skins, *RIGID BODY cards -> TIE NSETs, ties to
                          rigid surfaces -> body members, ROTARYI -> point masses
Converter._plan_u1_beams()   beams under *BEAM GENERAL SECTION / SECTION=I -> ccx's U1 element
                             (all of them or none: see U1_CARD for what ccx 2.23 allows)
Converter._plan_quadratic_shells()   composite S3 / S4 / S4R (and the linear shells and beams
                                     joined to them by an edge) -> S6 / S8R / B32R with shared
                                     midside nodes
Converter._plan_ply_split()   composite SC6R / SC8R -> one C3D6 / C3D8I per ply: interface
                              nodes on the stack edges, element sets, surfaces and face loads
                              moved to the plies (_remap_ply_faces), *EQUATION ties where
                              layups differ; nodes put between two nodes (_between) join the
                              node sets that hold both (_extend_edge_sets) and take the BCs
                              interpolated (_midside_records)
        │
        ▼
Converter._prescan()   deck-wide facts the handlers need: node kinds, the *TRANSFORM of each
                       node (_transform_defs), the connector plan (_plan_connectors), rigid
                       bodies and their ROT NODEs (also for kinematic couplings whose
                       transformed reference node needs one, _plan_kinematic_rot_nodes),
                       the *MPC plan (_plan_mpcs), knot beams
                       (_plan_rigid_couplings), the ROT NODEs' local axes (_plan_rot_axes),
                       the connectors' constraint rows in the DOFs ccx reads, local on
                       transformed nodes (_plan_connector_rows), the BCs on rigid-constraint
                       members their reference node imposes or, on a *RIGID BODY, takes over
                       (_plan_coupled_bcs), the velocity / acceleration BCs
                       (_plan_velocity_bcs), …; then _plan_load_cases() (a *BUCKLE step's
                       LOAD CASE=2 BCs), _plan_distributions(),
                       _plan_planar_constraint(), _plan_circ_rotation_knots(),
                       _plan_late_op_new(), _plan_op_new_rotations() and
                       _plan_transformed_rotations()
                       (rotational BCs / moments of transformed shell/beam and
                       kinematic reference nodes: kept, knot + global components, or
                       refused, per card); last
                       _plan_output(): each step's output requests fitted to ccx's output
                       model (.frd or .dat, one node set per variable, one output control),
                       Abaqus' preselected and default field output added, and explicit
                       output intervals turned into increments with ccx's Courant estimate
        │
        ▼
emit_geometry()  +  emit_other()     Pass B: write nodes/elements/sets from the registry,
                                             then translate the remaining blocks in order
        │
        ▼
Converter._settle_dependents()   choose each *EQUATION's eliminated (first) term against the
                                 BCs and ccx's own dependents — on a transformed node where ccx
                                 can turn it into a global DOF; drop redundant equations
Converter._restore_base_states()   a general step after linear perturbation steps starts with
                                   the last general step's loads, BCs and temperatures given
                                   again (_plan_base_restore: where its *BOUNDARY needs OP=NEW)
Converter._keep_body_loads()   a zero GRAV line in a step that would hold no body load after
                               one did (*BUCKLE drops them; ccx 2.23 aborts after such a step)
Converter._audit_loads()     load audit: step_load_audit() on the Abaqus blocks and on the
                             output; a step loaded there but not here is warned
```

`Converter.convert(blocks)` runs the whole thing and returns the output as a
`list[str]`. `main()` wraps it with file I/O and the report.

## Data model

**`Block`** (dataclass) — one keyword card: `keyword` (upper-case, no `*`), `params`
(ordered dict, values keep original case), and `data` (raw data lines). Helpers:
`block.param("ELSET")`, `block.has("GENERATE")`.

**`Geometry`** — the live registry built during Pass A: `nodes` (id → xyz),
`elements` (id → (type, conn)), `nsets`/`elsets` (name → id list). Mesh-generation
and flattening write into it; `emit_geometry()` reads from it.

**`Report`** — collects `[NOTE]`/`[WARNING]` entries (`once=True` de-duplicates),
and renders the header comment block / log.

## Why two passes

Geometry (`*NODE`, `*ELEMENT`, `*NSET`, `*ELSET`, and the mesh-generation cards) is
*consumed* into the registry and re-emitted once, canonically — this is what lets the
converter expand `*ELGEN`, resolve `GENERATE`, prune dangling set members, and prefix
instance names consistently. Everything else (materials, sections, steps, loads, BCs,
output) is translated **in its original order** by `emit_other()` → `translate_one()`,
which keeps the deck faithful to what the author wrote.

## Keyword dispatch — the five buckets

`translate_one()` routes each non-geometry block:

1. **Dedicated handler** (`handle_*`) — keywords needing real logic.
2. **Drop** — `DROP_KEYWORDS` (silent + note) / `DROP_WARN_KEYWORDS` (loud).
3. **Supported** — in `CCX_KEYWORDS` → `passthrough()` emits it unchanged.
4. **Pass-with-note / semantic-trap** — `PASS_WITH_NOTE` / `SEMANTIC_TRAP`.
5. **No equivalent** — not in `CCX_KEYWORDS` → `_commented()` emits it as `**`
   comments plus a warning (with tailored text from `SPECIAL_UNSUPPORTED` if present).

This is the "support as many as possible, convert or flag the rest" policy in code.

## Loads ccx has no card for

Surface tractions (`TRVEC`/`TRSHR` on `*DSLOAD` or element-based `*DLOAD`) and beam line
loads (`*DLOAD PX/PY/PZ/P1/P2`) become **consistent nodal forces**. `_load_faces` /
`_beam_lines` resolve the faces, edges or beams (corner nodes first, the plane-section
thickness or the axisymmetric flag, beam n1); `consistent_nodal_forces()` integrates the
shape functions by Gauss quadrature over each one in its undeformed geometry; and
`_to_nodal_forces` records the result per (card, target, label) in `_nodal_loads`, in
Abaqus semantics (a later step replaces a load, `OP=NEW` drops the card's earlier ones).
Forces on a node with a `*TRANSFORM` are first given in its local axes (`_to_local_axes`,
`_local_axes`; `_transform_defs` reads the cards into `_transformed`), since ccx and Abaqus read
a `*CLOAD` there in those axes; a node whose axes are unknown makes the line stay commented.
`handle_transform` writes a spherical `*TRANSFORM`, which ccx does not have, as a rectangular
one per node with its spherical axes (`_transform_axes`), and gives a `*RIGID BODY` ROT NODE
its reference node's axes; `_check_transforms` (end of `_prescan`) plans those and warns about
two cards with different data on a node and 2-D nodes whose local 3-axis leaves Z.
Rotations of transformed nodes: a kinematic coupling whose transformed reference node's
rotation the deck uses becomes a `*RIGID BODY` with a ROT NODE of its own
(`_plan_kinematic_rot_nodes`, emitted by `_coupling_as_rigid_body`); `handle_equation` moves
terms on a rigid-body reference node's DOFs 4–6 to its ROT NODE and comments out equations
with DOF 4–6 terms on other transformed nodes; `_plan_transformed_rotations` decides per
transformed shell/beam or kinematic reference node whether its rotational BCs and moments
stay (ccx reads them locally), go to global components on a knot (`_rot_global_lines`,
`_rot_bc_global`; `_ccx_knot` reads ccx's knot rule) or are refused, and
`_active_dof_lines` / `handle_cload` emit those lines at the end of each card.
At the end of every step `_flush_nodal_loads` writes one `*CLOAD` per amplitude with the
node DOFs whose total changed (0 where a load went away) — never `OP=NEW`, which in ccx
would also remove the deck's own concentrated loads. `_nodal_load_inexact` decides whether
nodal forces are exact (small strain; NLGEOM `TRVEC` with `FOLLOWER=NO, CONSTANT
RESULTANT=YES`); otherwise the line stays commented unless `--approximate`.
`_dl_state` / `_flush_dloads` do the same bookkeeping for the `*DLOAD` lines that come from
`*DLOAD` and from `*DSLOAD`, whose `OP=NEW` scopes differ in Abaqus but not in ccx.

Abaqus **surface elements** (`SURFACE_ELEMENTS`: `SFM3D*`, `SFMAX*`, `SFMGAX*`) have no
stiffness and no ccx counterpart. Right after Pass A, `_drop_surface_elements` moves them out
of the registry into `_carriers` and out of the element sets (`_carrier_sets` keeps each
set's full member list) — unless rebar, or mass in a deck where mass acts, keeps them
(without `--approximate`). `_load_elements` still sees them, so their `TRVEC`/`TRSHR` and
`P` loads, element-based or on a `*SURFACE` side, go through `_load_faces` like any face; a
surface element's face carries a pressure *sense* (Abaqus: an element-based `P` along the
element normal, a surface `P` against the surface normal). `_only_carriers` lets
`*SURFACE SECTION`, `*SURFACE` and `*EL PRINT` drop what only names them.

The **load audit** (`step_load_audit`) lists the loads active in every step — loads and
prescribed BC values persist until `OP=NEW`, a perturbation step counts only its own, user
subroutine magnitudes count in the Abaqus deck but not in ccx's (its stock subroutine would
run). `_audit_loads` compares the two and fills `unloaded_steps` / `source_unloaded`, which
`tests/test_corpus.py` gates on.

The **BCs in force per step** come from `bc_steps()` as ccx 2.23 reads them: `OP=NEW` acts on
a step's first `*BOUNDARY` only (`op_new_cards()`, which the other step walkers use too).

The **reduced-physics record** (`Converter.reduced_physics`, kept on the `Report` as
`Report.reduced`, so deck reading, mesh generation and flattening add to it too) names what
the ccx model drops or replaces of the Abaqus one. Every path that comments out, drops or
substitutes something Abaqus would solve calls `_reduces` (`report.reduce` outside a
`Converter`): `_commented` does unless its caller passes `reduces=False` (output requests,
numerical controls — `OUTPUT_ONLY_KEYWORDS`, `NUMERICAL_KEYWORDS` — and input Abaqus would
not apply), and so do `_drop_load_line` and `substitution_loss` (an `ELEMENT_TYPE_MAP` entry
outside `EXACT_SUBSTITUTIONS`); `Report.warn` records every `[APPROX]` reframing. A non-empty
record ends the report with a "Reduced physics" warning; `tests/test_corpus.py` checks the
manifest's `reduced_physics` flags against it.

## Element handling

`ccx_element_type(typ, report)` decides each element's fate using
`ELEMENT_TYPE_MAP` (node-count-preserving substitutions; `EXACT_SUBSTITUTIONS` are the exact
ones, the rest reduced physics), `CCX_ELEMENTS` (direct), and
recursive coupled-temperature (`T`) / hybrid (`H`) suffix strips, then the
rigid/cohesive prefix checks. `element_node_count(typ)` gives the node count used to
parse connectivity across continuation lines (tolerant of the `T`/`H` suffixes and the
`ELEMENT_TYPE_MAP`, and inferring a count for genuinely unknown types).

## How to extend

All the tables are module-level near the top of the file; after editing any of them
regenerate the docs (below).

* **Mark an Abaqus keyword as supported by ccx** → add it to `CCX_KEYWORDS`. It will
  then pass through unchanged instead of being commented.
* **Add a translation** → write a `handle_xxx(self, b)` method returning `list[str]`,
  and register it in the `handlers` dict inside `translate_one()`.
* **Add/declare an element type** → add its node count to `ELEMENT_NNODES`; then either
  add it to `CCX_ELEMENTS` (direct) or to `ELEMENT_TYPE_MAP` (substitution — keep the
  node count identical to the target, the test suite enforces this).
* **Map or drop an output variable** → edit `ABQ_MAP_VARS` / `ABQ_DROP_VARS` /
  `EL_PRINT_ONLY_VARS`; Abaqus' preselected field output per procedure is `PRESELECT_FIELD`,
  its contact output `PRESELECT_CONTACT`, and where ccx cannot write contact output
  `CONTACT_OUTPUT_ISSUES` (`Converter._contact_output_issues`).
* **Give an unsupported keyword tailored guidance** → add an entry to
  `SPECIAL_UNSUPPORTED` (otherwise it gets a generic "no equivalent" comment).
* **Drop an organisational keyword** → add it to `DROP_KEYWORDS` (or
  `DROP_WARN_KEYWORDS` with a message if it can change the model).
* **Normalise an abbreviation** → `PARAM_ALIASES` (parameter) or `KEYWORD_ALIASES`
  (keyword).

## Constraints: `*MPC`, rigid bodies and overconstraints

ccx eliminates one DOF per constraint equation — the *first* term of an `*EQUATION`, the
members' translations of a `*RIGID BODY` or `*KINEMATIC` coupling — and stops when that DOF
also has a `*BOUNDARY` or is eliminated twice. Abaqus resolves such overconstraints itself,
so the converter does it in three places, each exact:

* `_plan_mpcs()` (in `_prescan`) resolves every Abaqus `*MPC` line to node pairs, decides
  how each type is written (`handle_mpc()` then emits it line by line) and groups the `BEAM`
  lines into rigid bodies by their independent node (union-find over chained lines). The
  bodies get ROT NODEs and, on shell/beam nodes, knot beams like any `*RIGID BODY`.
  On nodes with a `*TRANSFORM` (`_plan_mpc_transforms()`) a `PIN`/`TIE` is written along
  one node's local axes (`_tie_rows()`) and a linear `LINK` with its local terms
  (`_link_terms()`) — `_dir_terms()` gives v · u_n in the DOFs ccx reads: a node's local
  terms only where no two share a global DOF, else the global terms of the node's *twin*
  (`_mpc_twin()`, a new node tied by u_twin = u_n, `_twin_rows()`), because ccx 2.23
  mis-assembles an equation that holds a DOF twice; `_ccx_dependent_order()` orders the rows whose eliminated terms are
  local DOFs of one node as ccx needs (shared with the connector rows). Pairs on nodes
  without local axes, and `TIE` rotations on a transformed shell/beam node, are refused
  (`_mpc_refused`).
* Connector elements (`CONN3D2`/`CONN2D2`) are kept out of the mesh (`Converter._conn`;
  `_emit_set` drops them from element sets) and planned in two parts. `_plan_connectors()`
  (before `_plan_mpcs`) reads each `*CONNECTOR SECTION` and routes every element: rigid
  links (`BEAM`, `WELD`) join the `*MPC BEAM` union-find, `LINK` goes the `*MPC LINK` way,
  unconstrained types are left out, and the rest become constraint *rows* — `JOIN`,
  `REVOLUTE`, `ALIGN` in the translations and rotation vectors of nodes a and b — whose
  shell/beam nodes get knots. `_plan_connector_rows()` (after the knots) maps each rotation
  to where ccx carries it (a ROT NODE, a knot, a kinematic coupling's reference node, a
  new rotation node for a solid or free node whose rotation shows elsewhere), drops DOFs
  held at zero in every step, eliminates connector-only rotations, turns one-DOF rows into
  `*BOUNDARY` lines (repeated after any `OP=NEW`) and keeps under `NLGEOM` only the rows
  that stay exact there; `handle_connector_section()` writes them.
* `_plan_coupled_bcs()` (in `_prescan`) finds BCs on rigid-constraint members that the
  reference node's own BCs impose anyway (the same value, no rotation about the other axes
  while the BC is in force, `bc_steps()`) and takes them off the card; a `*RIGID BODY`'s
  other member BCs move to its reference node where Abaqus/Standard puts them
  (`_plan_rigid_body_move()`), and the rest is warned (`_warn_coupled_clashes()`) or, with
  `--approximate`, dropped where Abaqus drops it. `handle_boundary()` applies the plan.
* `_settle_dependents()` runs on the finished output: it collects the BCs per step and the
  DOFs ccx eliminates itself, assigns each `*EQUATION` a free DOF by bipartite matching
  (original first term preferred), then accepts the equations in deck order reducing each
  by the ones before it — an equation that reduces to 0 = 0 is dropped, and the eliminated
  DOF must keep a nonzero reduced coefficient, so no loop of ties reaches ccx (which would
  hold it at zero). Converter rotation ties that find no free DOF are dropped; anything else
  left over is kept and warned.

## Rigid elements and analytical rigid surfaces

ccx has no rigid element and no analytical surface, and its `*RIGID BODY` refuses shell and
beam nodes, so `_plan_rigid()` — right after `_drop_surface_elements`, before the other
planners, which then see an ordinary mesh and ordinary rigid bodies — turns each rigid
element into a force-free solid *skin* (`_plan_skin_elements`: `R3D3`/`R3D4` → `C3D6`/`C3D8`
behind the facet, `R2D2`/`RB2D2`/`RAX2` → `C3D8` across ccx's expansion of the 2-D model via
`skin_lift`; `RB3D2` → its nodes only), keyed in `_skins` by (element, side) → (skin, face).
The deck's `*SURFACE` records that name rigid elements get element sets of the skins and
their faces (`_rigid_lines`, used by `handle_surface`). Analytical surfaces
(`_mesh_analytic`: `analytic_profile` reads the card, `profile_points` cuts the profile into
facets about the slave faces' size from `_analytic_size`, `analytic_frame` gives the
`CYLINDER`/`REVOLUTION` axes) become skins too (`_analytic`), unless they would need
`--approximate` (`_analytic_skipped`: their `*SURFACE`, `*RIGID BODY`, pairs and ties are
commented out). `_plan_rigid_ties` makes the slave nodes of a `*TIE` to a rigid surface body
members (`_tie_to_rigid`), and `_rewrite_rigid_bodies` gives every touched `*RIGID BODY` a
`TIE NSET` (and `PIN NSET`) of all its nodes, in place, so `_rigid_body_members()` and the
knot, coupled-BC and output planners read the full body. `_plan_rotary_stars` replaces
`ROTARYI` elements by `inertia_star()` point masses; `_plan_skin_material` sizes the skin
material, which `_rigid_model_cards()` writes after the deck's materials, just before the
first `*STEP`. After `_prescan` (which adds the ROT NODEs) `_plan_rigid_planar_holds()`
writes the model-data BCs that keep plane and axisymmetric bodies in their plane;
`handle_boundary` repeats them after `OP=NEW`. In assemblies, `_place_analytic` gives a
part's analytical surface its instance's frame. `_plan_rigid_contact_increment` (after
`_plan_circ_explicit_increment`) sizes the explicit-step cap for contact of plane and
axisymmetric elements with a rigid surface, which ccx leaves out of its stable increment;
`_explicit_caps` gives both caps to `_circ_explicit_increment` (the `*DYNAMIC` data line) and
to the output planner (`_circ_capped_max`).

## Velocity and acceleration boundary conditions

ccx prescribes displacements only, so `*BOUNDARY, TYPE=VELOCITY / ACCELERATION` becomes a
displacement BC whose amplitude is the time integral of the prescribed history.
`amplitude_curve()` turns an Abaqus `*AMPLITUDE` (tabular, equally spaced, smooth step,
periodic, modulated, decay) into a function of time; `integrate_history()` integrates a rate
once or twice exactly (Gauss-Legendre panels between the breakpoints) and samples it densely
enough that ccx's straight lines between the points stay within 1e-4 of the step's travel.
`_plan_velocity_bcs()` (in `_prescan`, after `_plan_coupled_bcs()`, whose rewrite of a card
it reads through `_rate_lines()`) follows every DOF such a BC touches through the steps —
its displacement and velocity at each step start, the BC in force (`op_new_cards()`, and
re-specification as in Abaqus) — and plans:

* `_vel_cards`: what replaces each velocity / acceleration card — the generated amplitudes
  and plain `*BOUNDARY` blocks, which `handle_boundary()` then converts like any deck BC
  (rigid-body rotations to the `ROT NODE`, midside nodes); the card's `OP=NEW` decision
  (`_op_new_drop`) goes with its first block;
* `_vel_tail`: the continued motion of a rate BC a later step keeps, emitted before that
  step's `*END STEP` (a ccx BC with a step-time amplitude would freeze at its last value),
  and the mean motion of an upgraded beam's midside node whose end nodes different cards
  drive.

`_plan_coupled_bcs()` reads a zero velocity from rest as a BC that holds its DOF at zero
itself (`_bc_states`, kind `rate`).

## Mesh-generation expanders

`expand_ngen / expand_nfill / expand_ncopy / expand_elgen / expand_elcopy` each take a
`Block` + the live `Geometry` and write the generated nodes/elements back into it.
They are plain functions (easy to unit-test) and use the vector helpers
(`vadd`, `rotate_about_axis`, `reflect_point`, …) for the geometry.

## Assembly flattening

`flatten_assembly()` partitions the deck into parts / instances / assembly /
top-level, parses each part's geometry once, then for every instance offsets the
node/element ids, applies the instance transform (**translation then rotation**, per
Abaqus), and emits per-instance geometry/sets/sections. `make_namer()` produces
collision-free set/surface names within CalculiX's 80-character limit (`CCX_NAME_LIMIT`),
used consistently by both the definitions and the reference resolver (`resolve()` /
`_resolve_field()`), so nothing de-syncs. Each instance's offsets, label ranges and renamed
sets and surfaces go to `Report.instances`: the instance map of the report and of `--json`.

## Regenerating the reference docs

The keyword/element/output tables in `docs/*-reference.md` are generated from the code:

```bash
python docs/generate_reference.py
```

Run it after changing any of the tables above so the docs stay in sync.

## Testing

When you add a feature, add a focused test to `tests/test_convert.py` next to the existing
ones (`convert_str(text)` converts an inline deck), an example plus a check in
`validate_with_ccx.py` when the result can be compared with a reference, and run the corpus.
[Testing](testing.md) describes the three layers and the gates a change must pass. Give every
`open()` of a deck or document `encoding="utf-8"`: CI runs the tests on Windows, where the
default is the code page.

## Releasing

Set `__version__` and the changelog heading, then publish a GitHub release tagged `v` +
`__version__` (`v1.2.0`). [`release.yml`](../.github/workflows/release.yml) checks the tag,
runs the unit tests, builds the sdist and wheel and uploads them to PyPI by trusted
publishing: PyPI trusts that workflow in the `pypi` environment, so no token is stored.
