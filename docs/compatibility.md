# Compatibility & sources

The converter's behaviour is grounded in the CalculiX manual, the
Abaqus↔CalculiX keyword delta tracked by the CalculiX project, and the community
forums — cross-checked against how existing tools handle real decks. This page records
the load-bearing facts and where they come from, so you can trust (or re-verify) them.

## Verified core facts

| Fact | Consequence for the converter | Evidence |
| --- | --- | --- |
| **Solid/shell node ordering is identical** (C3D20, C3D10, C3D15, C3D6, S8R, S6 — corner nodes then mid-side nodes in the same sequence) | element connectivity is passed through **unchanged** | ccx manual keeps "compatibility with ABAQUS" for C3D10; `DC3D*` heat elements documented "identical to" `C3D*`; `calculix/gmsh2ccx` writes Abaqus-ordered connectivity with no permutation |
| **Solid face numbering is identical** (hex/tet/wedge faces map index-for-index) | `*DLOAD Px` pressure-face labels and `*SURFACE Sx` pass through unchanged | ccx "Facial distributed loading" table == Abaqus 3-D element face table |
| **No mesh-generation cards** (`*NGEN`/`*NFILL`/`*NCOPY`/`*ELGEN`/`*ELCOPY`) | must be expanded to explicit `*NODE`/`*ELEMENT` | absent from the ccx keyword set |
| **No `*PART`/`*INSTANCE`/`*ASSEMBLY`/`*SYSTEM`** | must be flattened to one global numbering | absent from the ccx keyword set; forum guidance to export flat |
| **Set/surface names: 20 significant characters** (21st is a reserved `N`/`E`/`S`/`T` suffix) | flattened instance-prefixed names are truncated + uniquified | ccx manual "Sets" section |
| **`*ELASTIC` constant order is identical**; only the `TYPE` token differs (`ORTHOTROPIC`→`ORTHO`, `ANISOTROPIC`→`ANISO`) | rename token, pass data through | ccx `*ELASTIC` section |
| **`*INSTANCE` applies translation before rotation** (`R(p+T)`) | flatten transforms accordingly | Abaqus keyword manual: "translation is applied before rotation" |
| **Coupled temperature-displacement elements share the base element name** (`C3D8T`≡`C3D8`, `CAX4RT`≡`CAX4R`); the temperature DOF comes from the step | strip the trailing `T` | ccx `*COUPLED TEMPERATURE-DISPLACEMENT` / element sections (no separate `…T` element names) |
| **A keyword line ending in a comma continues its *parameters* on the next line** | splice them back; never merge a genuine data row | Abaqus input syntax: "continue a long keyword line by ending it with a comma" |
| **`NSET=` on `*NODE`, `ELSET=` on `*ELEMENT`, `GENERATE` on `*NSET`/`*ELSET`** are accepted | relied upon when emitting geometry | ccx `*NODE`/`*ELEMENT`/`*NSET`/`*ELSET` sections |
| **`*EQUATION`/`*MPC` dependent DOF can't also be an SPC** | pre-flight overconstraint warning | ccx `*EQUATION` section; the `cascade` error on the forums |

## Version notes

* The converter targets **CalculiX 2.22**. Keyword syntax for the structural cards is
  stable across 2.7 → 2.22.
* The latest release is **2.23** (Nov 2025); it is backward compatible and only adds
  capability (new `*DAMAGE INITIATION` card, "the first term in an `*EQUATION` can be a
  node set", linear temperature distributions on `*TEMPERATURE`/`*BOUNDARY`, composite
  shells in heat transfer, a `C3D8I` correction). None of these break existing
  Abaqus-style decks. No 2.24 exists as of mid-2026.
* A few cards are version-gated in older ccx (e.g. `*MEMBRANE SECTION` from 2.14, the
  `*ORIENTATION` rotation line from ~2.15, `C3D8R` hourglass control from 2.3). Check
  your target version if you rely on them.

## End-to-end validation

Beyond these facts, the converter is checked against a real solve.
`validate_with_ccx.py` (repo root) converts the example decks and runs them in
CalculiX (auto-detecting `ccx`, including FreeCAD's bundled binary). The headline
check is the **NAFEMS LE10 thick-plate benchmark**: the converted deck solves and
reports σ_yy = −5.65 MPa at point D vs the published reference −5.38 MPa (5 % — in
line with the element type and mesh density). The composite-shell and assembly decks
also solve. This proves the full pipeline — `*NCOPY`/`*ELGEN` expansion, node ordering,
boundary sets, pressure face, sections — is correct, not merely well-formed.

In addition, a **corpus of 1022 genuine Abaqus decks** (`corpus/manifest.py`, fetched on
demand) is converted and run: all 1022 convert with zero dangling references and 386 solve
in CalculiX; the rest convert cleanly but use features ccx cannot run, and each was
verified to fail no worse than the original unconverted deck. Bulk-running every deck
through convert → integrity → ccx is also what drove several converter fixes
(keyword-line continuation, coupled-temperature `T`-suffix elements, `*PARAMETER`
arithmetic, `*NFILL` with unequal bounding sets, space-separated `*INSTANCE` transforms).
See [testing.md](testing.md).

## The keyword-coverage reality

Abaqus defines ~570 keywords; CalculiX ~140. So for any non-trivial deck, "unsupported
keyword" is *expected*, not a failure — which is exactly why the converter classifies
every keyword and either translates it, drops an organisational card, or comments it
with guidance, rather than failing or silently passing it. The exhaustive split is in
[keyword-reference.md](keyword-reference.md).

## Compatibility limits — what doesn't convert/solve, and why

A converted deck can fail to *solve* in CalculiX for reasons that are mostly **not** the
converter's to fix. A full audit of the test corpus (every non-solving deck re-run
through ccx and classified by its failure *and* its source) breaks down as:

| Share | Category | Why no converter can help |
| --- | --- | --- |
| ~80% | **Fundamental ccx limits** | The physics isn't in stock ccx: `UMAT`/`VUMAT` user materials (no compiled subroutine), `*USER ELEMENT` (UEL), cohesive elements, explicit dynamics, user MPCs, rigid `R3D` elements, incompressible `ν≥0.5`, per-element distribution orientations — plus genuine non-convergence and degenerate (nonpositive-Jacobian) meshes. |
| ~4% | **Incomplete source deck** | The deck itself is partial and fails in Abaqus too: no `*MATERIAL` at all, an undefined CAE `_PickedSet`, a material name that doesn't match its section, externally-supplied `<parameter>` values, or a mesh/parser fixture with **no `*STEP`**. |
| ~15% | **Addressable error, but downstream-blocked** | The *first* error is converter-fixable, but a second, fundamental wall sits behind it. |

The third row is the important subtlety: **fixing the first error rarely makes such a
deck solve.** For example, Abaqus `*COUPLING`+`*Kinematic` can be translated to ccx
`*RIGID BODY`, which clears the coupling error on ~30 corpus decks — but *every one* then
hits a UMAT material, a non-convergence, or a degenerate-mesh error and still doesn't
run. So the converter is built to **translate or clearly flag** each incompatibility (so
the deck is faithful and the blocker is visible), not to manufacture ccx capabilities or
complete a partial deck.

**If your converted deck won't solve,** read the first `*ERROR` ccx prints and place it in
the table above. A *fundamental* or *incomplete-source* error means the model needs
remodelling (replace a UMAT with a built-in material, mesh a rigid surface, add the
missing step, refine an inverted element) — not a different conversion. The conversion
**report** (the `**`-comment header in the output) flags the cards that were translated
approximately or commented out, which is the first place to look.

One known translation the converter does *not* yet attempt is `*COUPLING`+`*Kinematic`
→ `*RIGID BODY` (it is passed through and ccx rejects it): it is a common CAE construct
worth adding, but every corpus deck that uses it is downstream-blocked, so it could not
be end-to-end-validated against ccx here.

## What "verified" means here

Each fact above was taken from a primary source (the CalculiX manual or the Abaqus
keyword manual), and where possible **cross-checked** a second way — against the
`calculix/new_keywords` and `calculix/cae` keyword lists, the community conversion
guide, or the behaviour of an existing importer (`gmsh2ccx`, FreeCAD, PrePoMax). The
one item that could not be quoted as text (the exact mid-side *edge* sequence, which
the manual shows only as figures) is the universal Abaqus/Gmsh convention and is
corroborated by the no-permutation pass-through in `gmsh2ccx`; if you want
belt-and-suspenders certainty, run a single quadratic element through `ccx` and check a
known displacement.

## Sources

* CalculiX CrunchiX User's Manual v2.22 (PDF) — <https://www.dhondt.de/ccx_2.22.pdf>
* CalculiX CrunchiX User's Manual v2.7 (HTML mirror) — <https://web.mit.edu/calculix_v2.7/CalculiX/ccx_2.7/doc/ccx/ccx.html>
* CalculiX "New features" changelog — <http://www.dhondt.de/new_calc.htm>
* `calculix/new_keywords` (Abaqus↔CalculiX keyword delta) — <https://github.com/calculix/new_keywords>
* `calculix/cae` (CalculiX keyword model) — <https://github.com/calculix/cae>
* "A Guide to Modifying Abaqus Input Files for Use in CalculiX" — <https://calculix.discourse.group/t/a-guide-to-modifying-abaqus-input-files-for-use-in-calculix/1430>
* CalculiX Discourse — <https://calculix.discourse.group/> · PrePoMax forum — <https://prepomax.discourse.group/>
* Abaqus Keywords Reference Manual, `*INSTANCE` — <https://www.sharcnet.ca/Software/Abaqus/6.14.2/v6.14/books/key/ch09abk19.html>
