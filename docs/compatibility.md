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
| **ccx has no surface-traction load** (no `TRVEC`/`TRSHR` labels) **and reads `P1`/`P2` on a beam as a pressure on its expanded section face** | tractions and beam line loads become consistent nodal forces (`*CLOAD`) | no traction label in the 2.23 binary; probed: `P1` on a 1 × 2 `RECT` cantilever deflects 2× beam theory (pressure × section width) |
| **A `*CLOAD` on a `CPS`/`CPE` node is the total for the section thickness; on a `CAX` node the total over 2π**, as in Abaqus | traction forces are scaled by the thickness / integrated over the full circle | probed on 2.23: each matches a pressure-loaded twin |
| **`*CLOAD`s on one node DOF (and `*DLOAD`s on one face) add within a step and replace across steps; `OP=NEW` removes only earlier steps' loads** | converted forces are re-emitted as totals, never with `OP=NEW`; ccx's `*DLOAD, OP=NEW` removes the `*DSLOAD` pressures Abaqus keeps, so those are given again | probed on 2.23 |
| **Abaqus tractions: `FOLLOWER=YES` and `CONSTANT RESULTANT=NO` by default; `FOLLOWER` does not apply to `TRSHR`, whose direction is projected onto the surface in the reference configuration** | nodal forces (fixed in ccx) are exact under NLGEOM only for `TRVEC` with `FOLLOWER=NO, CONSTANT RESULTANT=YES` | Abaqus Keywords manual (`*DSLOAD`, `*DLOAD`) and Analysis User's Guide (distributed loads) |
| **ccx has no surface element** (`SFM3D*`, `SFMAX*`, `SFMGAX*`: `*ERROR reading *ELEMENT`); **in Abaqus they have no stiffness** ("membrane elements with zero thickness") and carry loads, mass per unit area (`DENSITY=`) or rebar layers | they leave the mesh and their loads become consistent nodal forces; with rebar, or mass that acts (dynamics, frequency, gravity), they stay unless `--approximate` | Abaqus Analysis User's Guide, "Surface elements" and the general / axisymmetric surface element libraries (2016, 2017) |
| **Abaqus surface-element pressures: an element-based `P` is positive along the positive element normal; a surface-based (`*DSLOAD`) `P` is positive against the surface normal** (`SPOS`: the element normal, `SNEG`: its reverse). The normal is the right-hand rule over the nodes (3-D) or the direction node 1 → 2 turned 90° counterclockwise (axisymmetric) | the converted forces take each sign; an element-based `P` and a `*DSLOAD P` on `SPOS` load opposite ways | the element libraries' load tables (2016, 2017); checked in ccx: an `SFM3D8` skin on the LE10 plate reproduces its face pressure `P2` to 7 digits each way (`validate_with_ccx.py`) |
| **A `*CLOAD` on a node with a `*TRANSFORM` acts in the node's local axes, in ccx as in Abaqus. Rectangular: 1 along `a`, 2 towards `b` in the plane of `a` and `b`, 3 = 1 × 2. Cylindrical: 3 along the axis from `a` to `b`, 1 radial from the axis through the node, 2 = 3 × 1, evaluated at the node's undeformed position. The axes are fixed in space under NLGEOM** | converted nodal forces (tractions, beam line loads, surface-element pressures) on such nodes are given in those axes, so the global load is unchanged | Abaqus Analysis User's Guide, "Transformed coordinate systems" (2016): "fixed in space", right-handed, one transform per node, none on the cylinder axis. Probed on 2.23: the local axes recovered from a `C3D8` cube's response match these, also under NLGEOM with the node moving far. A local load equals its global counterpart to round-off on `C3D8`, `C3D20R`, `S4`, `S4R`, `S8`, `S8R`, `M3D4`, `M3D4R`, `M3D8`, `B31`, `B32R`, `CPS4`, `CPE4`, `CPS8`, `CPE8R`, `CAX4` and `CAX8` nodes, corner and midside alike. `validate_with_ccx.py` repeats this on a transformed `C3D20R` face and on Cook's membrane |
| **ccx 2.23 edge cases: a spherical `*TRANSFORM` (`TYPE=S`) and one with `a` = 0 give NaN results without an error. On the cylinder axis (closer than ~1e-11) ccx silently uses the global axes. With `a` parallel to `b` the axes are arbitrary. With two `*TRANSFORM` cards on a node the last one wins. On a `CPS`/`CPE` node whose local 3-axis is not global Z a local load does not reproduce its global counterpart (up to 86 % of |u| off)** (`CAX` nodes do) | a converted load on such a node is commented out with the reason. In 2-D only transforms that keep local 3 on the Z axis are accepted (Abaqus 2-D nodes have DOFs 1 and 2 only). The converter refuses within 1e-6 of the axis | probed on 2.23 (a `C3D8` cube; `CPS4`/`CPE4`/`CPS8`/`CPE8R` and `CAX4`/`CAX8` plates) |
| **ccx silently ignores a `*CLOAD` on a node that belongs to no element** | surface elements whose nodes no other element uses are warned | probed on 2.23: no error, zero displacement there |

## Version notes

* The converter is written against **CalculiX 2.22–2.23** and validated on **2.23** (the
  build bundled with FreeCAD 1.1.4). Keyword syntax for the structural cards is stable
  across 2.7 → 2.23.
* **2.23** (Nov 2025) adds capability (new `*DAMAGE INITIATION` card, "the first term in
  an `*EQUATION` can be a node set", linear temperature distributions on
  `*TEMPERATURE`/`*BOUNDARY`, composite shells in heat transfer, a `C3D8I` correction),
  but in practice it is **stricter about invalid input** than 2.22. Found in the corpus
  run, and handled or flagged by the converter:
  * step data (`*CLOAD`, `*DLOAD`, `*FREQUENCY`, output cards) outside any `*STEP`, a
    section naming an undefined material, and `*BOUNDARY` DOFs 4–6 on plane-element nodes
    now **crash** ccx (segfault / bus error) instead of a clean `*ERROR`;
  * rigid couplings (`*KINEMATIC`, `*RIGID BODY`) on shell, membrane, beam or truss nodes
    stop with `*ERROR in gen3dmpc: nodes belonging to shell elements must not be subject
    to a RIGID MPC` (2.22 ran them; the current ccx sources only warn) — unless ccx has
    made the node a *knot*, which a beam element attached to it does. The converter gives
    each such node a force-free *knot beam*, and uses the knot's rotations to tie the
    node's rotations to the coupling as Abaqus does (see [testing](testing.md)).
* No 2.24 exists as of October 2026.
* A few cards are version-gated in older ccx (e.g. `*MEMBRANE SECTION` from 2.14, the
  `*ORIENTATION` rotation line from ~2.15, `C3D8R` hourglass control from 2.3). Check
  your target version if you rely on them.

## End-to-end validation

Beyond these facts, the converter is checked against a real solve.
`validate_with_ccx.py` (repo root) converts the example decks and runs them in
CalculiX (auto-detecting `ccx`, including FreeCAD's bundled binary). The headline
check is the **NAFEMS LE10 thick-plate benchmark**: the converted deck solves and
reports σ_yy = −5.65 MPa at point D vs the published reference −5.38 MPa (5 % — in
line with the element type and mesh density). A cantilever on linear beams with a
circular section matches beam theory's tip deflection within 0.4 %, pipe- and
box-section cantilevers match it within 0.6 %, a shell plate whose edge is rigidly coupled
to a loaded reference point matches the same plate built from solids under `*RIGID BODY`
within 0.001 %, the LE10 plate with its pressure on a skin of `SFM3D8` surface elements
(which ccx does not have) reproduces the face-pressure result to 7 digits, Cook's membrane
under a shear traction matches the published 23.96 within
0.12 %, cantilevers under beam line loads match q L⁴/(8 E I) within 1.2 %, an axisymmetric
cylinder under a radial traction matches Lamé within 0.02 %, tractions on nodes with a
`*TRANSFORM` (a `C3D20R` face, Cook's loaded edge) match the same models without one to
round-off, and the composite-shell and assembly decks also solve. This proves the
full pipeline — `*NCOPY`/`*ELGEN` expansion, node ordering, boundary sets, pressure face,
sections — is correct, not merely well-formed.

In addition, a **corpus of 1022 genuine Abaqus decks** (`corpus/manifest.py`, fetched on
demand) is converted and run on ccx 2.23: all 1022 convert with zero dangling references,
189 solve in CalculiX under their own loads (14 more solve but load nothing in the source
deck) and 219 mesh-only decks (no `*STEP`) are accepted by it; the rest
convert cleanly but use features ccx cannot run, and each was verified to fail no worse
than the original unconverted deck. Bulk-running every deck
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
| ~80% | **Fundamental ccx limits** | The physics isn't in stock ccx: `UMAT`/`VUMAT` user materials (no compiled subroutine), `*USER ELEMENT` (UEL), cohesive elements, user MPCs, rigid `R3D` elements, Riks arc-length steps, incompressible `ν≥0.5`, per-element distribution orientations — plus genuine non-convergence and degenerate (nonpositive-Jacobian) meshes. |
| ~4% | **Incomplete source deck** | The deck itself is partial and fails in Abaqus too: no `*MATERIAL` at all, an undefined CAE `_PickedSet`, a material name that doesn't match its section, externally-supplied `<parameter>` values, or a mesh/parser fixture with **no `*STEP`**. |
| ~15% | **Addressable error, but downstream-blocked** | The *first* error is converter-fixable, but a second, fundamental wall sits behind it. |

The third row is the important subtlety: **fixing the first error rarely makes such a
deck solve.** For example, the rigid couplings on shell nodes that ccx 2.23 rejects are
now repaired — but of the eight corpus decks that have one, only two newly solve (a
third already ran); the other five then hit a VUMAT, a user element, an unsupported
damage criterion, an incomplete source or an overconstraint and still don't run. So the
converter is built to **translate or clearly flag** each incompatibility (so the deck is
faithful and the blocker is visible), not to manufacture ccx capabilities or complete a
partial deck.

**If your converted deck won't solve,** read the first `*ERROR` ccx prints and place it in
the table above. A *fundamental* or *incomplete-source* error means the model needs
remodelling (replace a UMAT with a built-in material, mesh a rigid surface, add the
missing step, refine an inverted element) — not a different conversion. The conversion
**report** (the `**`-comment header in the output) flags the cards that were translated
approximately or commented out, which is the first place to look.

`*COUPLING`+`*Kinematic` passes to ccx natively (ccx has both keywords; the converter
resolves the `REF NODE` set and fills an empty `*Kinematic`). Where it couples shell,
membrane, beam or truss nodes, ccx 2.23 accepts it only through the knot beams above;
explicit-dynamics steps cannot run it at all, and a coupled DOF that also carries a
`*BOUNDARY` stops ccx ("dependent side of a MPC and a SPC") where Abaqus resolves the
overconstraint.

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
