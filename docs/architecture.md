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
Converter._prescan()   deck-wide facts the handlers need: node kinds, the *TRANSFORM of each
                       node (_transform_defs), the connector plan (_plan_connectors), rigid
                       bodies and their ROT NODEs, the *MPC plan (_plan_mpcs), knot beams
                       (_plan_rigid_couplings), the ROT NODEs' local axes (_plan_rot_axes),
                       the connectors' constraint rows in the DOFs ccx reads, local on
                       transformed nodes (_plan_connector_rows), the BCs on rigid-constraint
                       members their reference node imposes or, on a *RIGID BODY, takes over
                       (_plan_coupled_bcs), the velocity / acceleration BCs
                       (_plan_velocity_bcs), …; then _plan_distributions(),
                       _plan_planar_constraint() and _plan_circ_rotation_knots(); last
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

## Element handling

`ccx_element_type(typ, report)` decides each element's fate using
`ELEMENT_TYPE_MAP` (node-count-preserving substitutions), `CCX_ELEMENTS` (direct), and
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

## Velocity and acceleration boundary conditions

ccx prescribes displacements only, so `*BOUNDARY, TYPE=VELOCITY / ACCELERATION` becomes a
displacement BC whose amplitude is the time integral of the prescribed history.
`amplitude_curve()` turns an Abaqus `*AMPLITUDE` (tabular, equally spaced, smooth step,
periodic, modulated, decay) into a function of time; `integrate_history()` integrates a rate
once or twice exactly (Gauss-Legendre panels between the breakpoints) and samples it densely
enough that ccx's straight lines between the points stay within 1e-4 of the step's travel.
`_plan_velocity_bcs()` (in `_prescan`, after `_plan_coupled_bcs()`, whose rewrite of a card
it reads through `_rate_lines()`) follows every DOF such a BC touches through the steps —
its displacement and velocity at each step start, the BC in force (`OP=NEW` and
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
`_resolve_field()`), so nothing de-syncs.

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
[Testing](testing.md) describes the three layers and the gates a change must pass.
