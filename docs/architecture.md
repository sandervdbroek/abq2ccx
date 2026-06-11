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
Converter._check_overconstraints()   pre-flight warning for BC-on-dependent-DOF
        │
        ▼
emit_geometry()  +  emit_other()     Pass B: write nodes/elements/sets from the registry,
                                             then translate the remaining blocks in order
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
checks the NAFEMS LE10 benchmark stress against the published reference. It skips
cleanly if no `ccx` is found.

There is also a **corpus** of 1022 genuine Abaqus decks (`corpus/manifest.py`) fetched on
demand and tested end-to-end:

```bash
python corpus/fetch.py          # download to corpus/files/ (gitignored)
python tests/test_corpus.py     # convert all + (if ccx) solve the ones expected to
```

`tests/test_corpus.py` asserts every deck converts with zero dangling references, and
that decks marked `expect_solve` actually solve in ccx. To add a deck, append an entry
to `corpus/manifest.py`. The complete test suite — unit, end-to-end, and corpus, with a
description of each test — is documented in [testing.md](testing.md).
