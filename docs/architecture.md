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
Converter._prescan()   deck-wide facts the handlers need: node kinds, rigid bodies and their
                       ROT NODEs, the *MPC plan (_plan_mpcs), knot beams
                       (_plan_rigid_couplings), the BCs on rigid-constraint members their
                       reference node imposes or, on a *RIGID BODY, takes over
                       (_plan_coupled_bcs), …; then _plan_distributions(),
                       _plan_planar_constraint() and _plan_circ_rotation_knots()
        │
        ▼
emit_geometry()  +  emit_other()     Pass B: write nodes/elements/sets from the registry,
                                             then translate the remaining blocks in order
        │
        ▼
Converter._settle_dependents()   choose each *EQUATION's eliminated (first) term against the
                                 BCs and ccx's own dependents; drop redundant equations
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
  `EL_PRINT_ONLY_VARS`.
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
* `_plan_implied_spcs()` finds zero BCs on rigid-body members that the body already holds
  (reference node fixed in that DOF and unable to rotate, in every step the BC is in force,
  `bc_steps()`); `handle_boundary()` leaves them out.
* `_settle_dependents()` runs on the finished output: it collects the BCs per step and the
  DOFs ccx eliminates itself, assigns each `*EQUATION` a free DOF by bipartite matching
  (original first term preferred), then accepts the equations in deck order reducing each
  by the ones before it — an equation that reduces to 0 = 0 is dropped, and the eliminated
  DOF must keep a nonzero reduced coefficient, so no loop of ties reaches ccx (which would
  hold it at zero). Converter rotation ties that find no free DOF are dropped; anything else
  left over is kept and warned.

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
`≤20`-character, collision-free set/surface names used consistently by both the
definitions and the reference-resolver (`resolve()` / `_resolve_field()`), so nothing
de-syncs. Set this against CalculiX's 20-significant-character name limit.

## Regenerating the reference docs

The keyword/element/output tables in `docs/*-reference.md` are generated from the code:

```bash
python docs/generate_reference.py
```

Run it after changing any of the tables above so the docs stay in sync.

## Testing

```bash
python tests/test_convert.py        # or: pytest tests/
```

Tests convert the bundled example decks and assert referential consistency plus the
documented behaviours. When you add a feature, add a focused test next to the existing
ones (`convert_str(...)` builds a deck from an inline string).

For end-to-end validation against a real solver:

```bash
python validate_with_ccx.py     # converts + runs the examples in CalculiX
```

It auto-detects `ccx` (including FreeCAD's bundled binary), runs the example decks, and
checks the NAFEMS LE10 benchmark stress against the published reference (and with its
pressure carried by surface elements against the face-pressure result), the tip
deflections of circular-, pipe- and box-section cantilevers, circular-section beams with
rotational BCs and in an explicit dynamic step, planar beams' frequencies and buckling
loads against beam theory, a clamped beam and plate across a later step's
`*BOUNDARY, OP=NEW`, and the loads applied as consistent nodal forces (Cook's membrane,
beam line loads, Lamé's cylinder, and tractions on nodes with a `*TRANSFORM` against the
same models without one). It skips cleanly if no `ccx` is found.

There is also a **corpus** of 1022 genuine Abaqus decks (`corpus/manifest.py`) fetched on
demand and tested end-to-end:

```bash
python corpus/fetch.py          # download to corpus/files/ (gitignored)
python tests/test_corpus.py     # convert all + (if ccx) solve the ones expected to
```

`tests/test_corpus.py` asserts every deck converts with zero dangling references, that
decks marked `expect_solve` keep a load in every step their Abaqus deck loads (the load
audit) and actually solve in ccx (clean exit, no crash, an analysis step runs), while
mesh-only `parse_only` decks are accepted. To add a deck, append an entry
to `corpus/manifest.py`. The complete test suite — unit, end-to-end, and corpus, with a
description of each test — is documented in [testing.md](testing.md).
