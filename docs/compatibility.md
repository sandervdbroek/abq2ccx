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
| **`*EQUATION`/`*MPC` dependent DOF can't also be an SPC** — ccx eliminates an equation's *first* term | equation terms reordered so a free DOF goes first, redundant equations dropped, BCs a rigid body implies left out; the rest warned | ccx `*EQUATION` section; the `cascade` error on the forums; probed on 2.23 |
| **ccx has no planar beam or truss**: `B21` "is internally replaced by a B31 element", `T2D2` by a `T3D2`, so their out-of-plane DOFs are free; a rotational BC on every node of an expanded beam stiffens it | in a planar model, fix DOF 3 on the nodes of 2-D beams/trusses, and DOFs 4–5 at one node of a straight beam whose twist is free — on a circular section an element's middle node (twist modes stay in `*FREQUENCY`, warned) | ccx manual 6.2.31, 6.2.34; probed on 2.23 (`B21` frequency deck: every bending mode twice) |
| **A rotational BC on a circular-section beam node locks its other rotations**: for every rotational BC on a non-knot `B32`/`B32R` node ccx ties the section's midside nodes to the mean of its corners, and a `CIRC` section's eight nodes lie on the circle, where no rigid rotation satisfies that; at a 3-node element's middle node the tied nodes are unused | an element end node whose rotational BCs hold only some of DOFs 4–6, or a nonzero one, gets a force-free knot beam: a knot's BCs act on its rotation node (warned when most nodes need one, or not repaired under an explicit step) | ccx sources `gen3dfrom1d.f`, `gen3dboun.f`; probed on 2.23 (twist held at pinned ends: 0.27 of beam theory, 0.994 with knots) |
| **A later step's `*BOUNDARY, OP=NEW` loses the rotational BCs it re-specifies on shell/beam nodes**: ccx applies them through mean-rotation MPCs whose angle SPC OP=NEW deletes, and the rebuilt MPC finds no free dependent DOF; on shells stale SPC indices also zero unrelated BCs | from step 2 on, after rotational BCs on shell/beam nodes, an OP=NEW that removes nothing is dropped; where it removes BCs, the shell/beam nodes it would break get knot beams (a deck with an explicit step: warned) | ccx sources `boundarys.f`, `gen3dboun.f`, `usermpc.f` ("no MPC is generated for the mean rotation"); probed on 2.23 (clamped cantilever re-clamped with OP=NEW: tip deflection 1.87e5 instead of 0.595; a prescribed shell displacement of 2 came out 0) |
| **ccx's `*MPC BEAM` keeps the distance between two nodes** (Abaqus `LINK`, not Abaqus `BEAM`) and rejects nodes of beam, truss, shell, membrane and plane elements | Abaqus `LINK` → ccx `*MPC BEAM` under `NLGEOM` (a linearised `*EQUATION` without it); Abaqus `BEAM` → `*RIGID BODY` | probed on 2.23 (a link turned through 8° and 25° keeps its length to 1e-8; `*ERROR in gen3dmpc: nodes belonging to 1D/2D elements must not be subject to a BEAM MPC`) |
| **A rotational DOF of a non-knot shell/beam node does nothing in an `*EQUATION`** | `*MPC TIE` rotations are tied between knots only | probed on 2.23: two beam spans `TIE`d by six equations deflect exactly like a `PIN`ned hinge, as knots like one continuous beam |
| **A closed loop of `*EQUATION` ties** (u1 = u2, u2 = u3, u3 = u1) is accepted, but ccx then warns "zero coefficient on the dependent side" and **holds the whole loop at zero** | the loop's closing equation is dropped (it follows from the others) | probed on 2.23 |
| **ccx's explicit stable increment is about 1.3× too large for circular-section beams**: its Courant estimate measures each element by the one-point volume of the 20-node brick a `B32`/`B32R` expands into over its largest face area, and a `CIRC` section's nodes on the circle make that h = min(l, √2·d) — the box around the circle — while the stable limit corresponds to h = 1.01–1.17·d (`RECT`/`PIPE`/`BOX` run at ccx's own increment) | each automatic `*DYNAMIC, EXPLICIT` increment is capped (the data line's 4th field) at ccx's own formula with h = min(l, d/√2), the square through the section's corner nodes; a fixed (`DIRECT`) increment above it is warned, since ccx's mass scaling is sized from the same estimate | ccx sources `calcstabletimeincvol.f`, `gen3dfrom1d.f`; probed on 2.23 (NaN displacements; limit bisected over `B32`/`B32R`, d = 10–80, l = 5–100, ν = 0–0.49; capped, a load raised smoothly and held ends within 1 % of beam theory) |
| **A rigid coupling makes its members' coupled DOFs MPC dependents too** (`*RIGID BODY` and `*MPC BEAM`: every translation; `*KINEMATIC`: the listed ones), and ccx holds DOF 3 of 2-D nodes itself | a member `*BOUNDARY` that the reference node's own BCs impose is taken off (exact); identical ones on a `*RIGID BODY` move to the reference node with zero rotations about the other axes, as Abaqus/Standard moves them, where the BC'd nodes hold the same DOFs (exact; otherwise only with `--approximate`); the others are warned (`--approximate` drops them on a kinematic coupling or an `*MPC`, as Abaqus/Standard does); a 2-D `*KINEMATIC` couples `1, 2` | probed on ccx 2.23 (`*ERROR in cascade`; moved vs hand-placed BCs identical, `C3D8` and `CAX4`, linear and `NLGEOM`); Abaqus manual: coupled DOFs are eliminated at the coupling nodes, identical BCs on rigid-body nodes move to the reference node (non-identical ones are an error) |
| **ccx has no surface-traction load** (no `TRVEC`/`TRSHR` labels) **and reads `P1`/`P2` on a beam as a pressure on its expanded section face** | tractions and beam line loads become consistent nodal forces (`*CLOAD`) | no traction label in the 2.23 binary; probed: `P1` on a 1 × 2 `RECT` cantilever deflects 2× beam theory (pressure × section width) |
| **A `*CLOAD` on a `CPS`/`CPE` node is the total for the section thickness; on a `CAX` node the total over 2π** | traction forces are scaled by the thickness / integrated over the full circle | probed on 2.23: each matches a pressure-loaded twin |
| **`*CLOAD`s on one node DOF (and `*DLOAD`s on one face) add within a step and replace across steps; `OP=NEW` removes only earlier steps' loads** | converted forces are re-emitted as totals, never with `OP=NEW`; ccx's `*DLOAD, OP=NEW` removes the `*DSLOAD` pressures Abaqus keeps, so those are given again | probed on 2.23 |
| **Abaqus tractions: the direction is normalized (it does not scale the load); `TRSHR` is projected onto the surface in the reference configuration and then normalized, so a point where the direction is normal to the surface gets no load. `FOLLOWER=YES` and `CONSTANT RESULTANT=NO` by default; `FOLLOWER` does not apply to `TRSHR`, which always stays tangent to the current surface. Beam line loads in global directions never follow the beam; `P1`/`P2` rotate with it** | nodal forces (fixed in ccx) are exact under NLGEOM only for `TRVEC` with `FOLLOWER=NO, CONSTANT RESULTANT=YES`; beam line loads under NLGEOM only with `--approximate` (Abaqus does not say whether `PX`/`PY`/`PZ` are per original or current length) | Abaqus Keywords manual (`*DSLOAD`, `*DLOAD`) and Analysis User's Guide ("Distributed Loads", 2025) |
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
* **Per-element orientations (`*DISTRIBUTION` + an `*ORIENTATION` that names it) are
  supported by ccx 2.23, but only partly as Abaqus defines them** (probed with small decks
  and read off its distribution, orientation and section readers):
  * `*DISTRIBUTION` takes `NAME`, `LOCATION` and `TABLE`; each data line is
    `element or element set, ax, ay, az, bx, by, bz` in global coordinates, and becomes an
    orientation of its own. `*DISTRIBUTION TABLE` is ignored (with a warning), and values
    after the sixth — an Abaqus origin `c` — are silently dropped.
  * The `*ORIENTATION` that names the distribution takes all its lines over, so a second
    one naming the same distribution stops ccx; a name ccx can read as a number (`D1`,
    `E5`, `12`) silently makes the orientation all-zero.
  * Only `*SOLID SECTION` gives each listed element its own line; the elements it does not
    list get the first line, so the Abaqus default line (blank element field) works only
    as the first line. `*SHELL SECTION`, plain or `COMPOSITE`, and `*MEMBRANE SECTION` give
    every element the first line — the results equal a single orientation.
  * An additional-rotation line turns only the first line correctly; the others are left
    practically unrotated (the angle is converted to radians again for each line).

  The converter gives each orientation its own distribution, resolved to one line per
  element of its solid sections (default first, the origin subtracted and the rotation
  applied to the axes, no rotation line), and splits shell and membrane sections into one
  plain `*ORIENTATION` and section per distinct direction. Composite plies get their
  orientations from their group's own axes, and assembly flattening renames the
  distribution per instance, offsets its element labels and turns its axes with a rotated
  instance.
* **An elasticity less anisotropic than the thermal expansion gets a wrong stiffness in
  linear steps of a deck with temperatures** (probed with unit cubes on
  C3D8/C3D8I/C3D8R/C3D20R, S4/S4R, M3D4, CPS4/CPE4/CAX4, B31/B32R and T3D2, and read off
  ccx's `linel`, `materialdata_me` and `elastics`):
  * an isotropic `*ELASTIC` beside `*EXPANSION, TYPE=ORTHO` or `ANISO`: once the deck has
    temperatures (an initial temperature field), the stress routine stores the stiffness
    in orthotropic or anisotropic form, but the linear element stiffness still reads it
    as (E, ν), so E becomes λ + 2μ and ν becomes λ — for every load, without an error.
    Heated, a free cube (E = 1000, ν = 0.2, α = 1e-3, 2e-3, 4e-3) *shrinks*, with strains
    of −2.2, −2.0 and −1.6, with or without an `*ORIENTATION`; pulled at a temperature
    that does not change, it contracts sideways by 0.25 instead of 2e-4; its frequencies
    come out 17 times too low. Without temperatures the material is right;
  * an orthotropic or engineering-constants `*ELASTIC` beside `TYPE=ANISO` goes wrong the
    same way (spurious shear strains, or values of 1e14) unless an `*ORIENTATION` applies.
    Only `TYPE=ANISO` elasticity is right beside an ANISO expansion everywhere, and
    `ENGINEERING CONSTANTS` (or `ORTHO`) beside an ORTHO expansion;
  * `NLGEOM` steps and materials with `*PLASTIC` or `*CREEP` (ccx's nonlinear path) get
    these combinations right, but there ccx accepts only an isotropic or orthotropic
    `*ELASTIC`. `NLGEOM` has a limitation of its own with these expansions, whatever the
    elastic type (next item);
  * temperature rows are interpolated linearly in the given constants for `TYPE=ISO`
    (E, ν, as Abaqus does), but in the stiffness matrix for every other type (ccx turns
    engineering constants into one per row as it reads them);
  * the shear coefficients α12, α13, α23 of an ANISO expansion are tensor components
    (thermal ε12 = α12 ΔT). Whether Abaqus means the same is not verified here; the
    converter passes the coefficients through.

  The converter writes an isotropic `*ELASTIC` as `ENGINEERING CONSTANTS` beside an ORTHO
  expansion, and an isotropic, orthotropic or engineering-constants one as `ANISO` beside
  an ANISO expansion — the same stiffness, so a stress analysis is unchanged — and adds
  rows between the given temperatures until ccx's interpolation of the stiffness is
  within 1e-4 of the stiffness from Abaqus' interpolated constants. Materials on the
  nonlinear path are left as they are. The `NLGEOM` limitation cannot be fixed this way.
* **Under `NLGEOM`, an orthotropic thermal expansion in turned material axes, and any
  anisotropic one, are computed wrongly** (probed with free heated unit cubes and plates,
  E = 1000, ν = 0.2, α = 1e-3, 2e-3, 4e-3, ΔT = 1, strains from the displacements; read off
  ccx's `calcmechstrain` and `modifystressstiff`). With `NLGEOM`, ccx splits the
  deformation gradient into a mechanical and a thermal part, and in 2.23:
  * it treats every `TYPE=ORTHO` expansion as diagonal in global axes. Where an
    `*ORIENTATION` or a composite ply angle turns the material axes so that the thermal
    strain has shear in global axes, that shear is dropped, without an error: a cube
    turned 30° about z gets its normal strains (1.25e-3, 1.75e-3) but no shear strain
    instead of −4.33e-4, and a [30/−30]s fibre laminate's in-plane thermal strains come
    out 41 % and 8 % off. This holds with every `*ELASTIC` form (isotropic as given,
    engineering constants, orthotropic, anisotropic), on C3D8/C3D8R/C3D8I/C3D20R, S4, S8R
    (plain, and composite by ply angle or section orientation) and M3D4, in `*STATIC`,
    implicit and explicit `*DYNAMIC` and `*COUPLED TEMPERATURE-DISPLACEMENT` (steady state
    and transient) steps, and with `*PLASTIC`. Axes that the orientation only permutes
    (0°, 90°, a [0/90] layup) and coefficients equal across the turn are right: there is
    no shear to lose;
  * it builds the thermal deformation gradient of a `TYPE=ANISO` expansion from the wrong
    array, so the step stops with "too many cutbacks" — with or without an `*ORIENTATION`,
    as soon as the deck has temperatures, even for a pulled cube whose temperature never
    changes;
  * linear steps (also coupled and `*PLASTIC` ones) and `NLGEOM=NO` are right, and a deck
    without temperatures has no thermal strain to get wrong.

  The CalculiX sources changed both routines on 9–10 October 2026 (Dhondtguido/CalculiX
  commits 67faf64 and 2c609be), after 2.23 was posted on 2 November 2025; a build with
  the change was not tried here. No form of the deck avoids it in 2.23, so the converter
  only warns, once per kind and naming the materials, when a step has `NLGEOM` (an
  explicit step counts unless it says `NLGEOM=NO`: the converter switches it on) and a
  section or composite ply uses a material with an ORTHO expansion in axes turned so that
  its thermal strain has shear in global axes, in a deck where the temperature changes,
  or one with an ANISO expansion, in a deck with temperatures.
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
within 0.001 %, coupled bars whose coupled nodes also carry BCs match the same constraints
written without a coupling to 2e-18, circular-section beams with a held twist and a prescribed rotation match
beam theory within 0.2 %, planar `B21` beams' frequencies and buckling loads (rectangular
and circular sections) match it within 0.6 %, a C3D8 plate and a composite S8R
variable-angle-tow panel whose fibre angles come from a `*DISTRIBUTION` move exactly like
the same models written with one `*ORIENTATION` and section per element (to 3e-11 and
exactly), a rigid lever (`*MPC BEAM`) on a cantilever tip matches statics within 0.04 % (and
a 10⁴× stiffer beam lever within 5e-7 at 27° of rotation), `*MPC PIN` and `TIE` joints
between beam spans match the hinge and the propped-cantilever solutions within 0.33 %, an
`*MPC LINK` matches statics exactly and keeps its length under `NLGEOM`, a deck whose
`*EQUATION` clashes with a BC (and has a duplicate and a loop of ties) solves with the ties
held, a clamped beam and plate keep their clamps across a later step's
`*BOUNDARY, OP=NEW` (beam theory within 0.7 %, a prescribed plate displacement exactly),
the LE10 plate with its pressure on a skin of `SFM3D8` surface elements
(which ccx does not have) reproduces the face-pressure result to 7 digits, Cook's membrane
under a shear traction matches the published 23.96 within
0.12 %, cantilevers under beam line loads match q L⁴/(8 E I) within 1.2 %, an axisymmetric
cylinder under a radial traction matches Lamé within 0.02 %, tractions on nodes with a
`*TRANSFORM` (a `C3D20R` face, Cook's loaded edge) match the same models without one to
round-off, and the composite-shell and assembly decks also solve. This proves the full pipeline —
`*NCOPY`/`*ELGEN` expansion, node ordering, boundary sets, pressure face, sections — is
correct, not merely well-formed.

In addition, a **corpus of 1022 genuine Abaqus decks** (`corpus/manifest.py`, fetched on
demand) is converted and run on ccx 2.23: all 1022 convert with zero dangling references,
184 solve in CalculiX under their own loads (14 more solve but load nothing in the source
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
| ~80% | **Fundamental ccx limits** | The physics isn't in stock ccx: `UMAT`/`VUMAT` user materials (no compiled subroutine), `*USER ELEMENT` (UEL), cohesive elements, user MPCs, rigid `R3D` elements, Riks arc-length steps, incompressible `ν≥0.5`, layered (composite) solid sections — plus genuine non-convergence and degenerate (nonpositive-Jacobian) meshes. |
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
explicit-dynamics steps cannot run it at all (nor any rigid body on plane or axisymmetric
nodes: "linear and nonlinear MPC's depend on each other"). A coupled DOF that also carries
a `*BOUNDARY` stops ccx ("dependent side of a MPC and a SPC"), an overconstraint Abaqus
resolves: the converter takes such a BC off where the reference node's own BCs impose it
anyway (exact). On a kinematic coupling or an `*MPC` it otherwise warns — Abaqus/Standard
eliminates the constrained DOFs and ignores the BC, and `--approximate` drops it the same way. On a `*RIGID
BODY` Abaqus/Standard moves identical BCs on the body's nodes to its reference node, adding
zero rotations about the other axes, and stops if they differ; the converter makes the same
move, in the card that held the BC, wherever it is the same constraint — the BC'd nodes hold
that DOF of the body and its rotations about the other axes (not all on one line seen along
the DOF, or with the reference node's own BCs), and the body is unturned when the step
starts — and with `--approximate` (`[APPROX]`) where it holds the body more than the BCs
do. BCs that differ between the body's nodes, or contradict the reference node's own, stay
warned: Abaqus stops on them too.

Abaqus `*MPC` is converted line by line: `PIN` and `TIE` become `*EQUATION`s, `BEAM`
lines become one `*RIGID BODY` per independent node (lines chained through a node form one
body), `LINK` becomes its linearised `*EQUATION` without `NLGEOM` and ccx's distance MPC
with it, and `PLANE`/`STRAIGHT` pass through. User MPCs (a numeric type, the Abaqus `MPC`
subroutine) and the other types (`SLIDER`, `REVOLUTE`, `UNIVERSAL`, `ELBOW`, `LINEAR`, …)
are commented out one line at a time, with the reason in the report.

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
* Abaqus Analysis User's Guide (2016), "Coupling constraints" (kinematic coupling eliminates the coupled DOFs; no BCs on them in Abaqus/Standard) — <https://ceae-server.colorado.edu/v2016/books/usb/pt08ch35s03aus135.html>
* Abaqus Analysis User's Guide (2016), "Overconstraint checks" (BCs on rigid-body nodes moved to the reference node) — <https://ceae-server.colorado.edu/v2016/books/usb/pt08ch35s06aus140.html>
