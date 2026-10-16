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
| **`*EXPANSION, TYPE=ANISO` has the same order (α11, α22, α33, α12, α13, α23) but not the same shear measure**: Abaqus' α12, α13, α23 are engineering (γ12 = 2ε12 = α12 ΔT), ccx 2.23 reads tensor components (ε12 = α12 ΔT) | halve α12, α13, α23 on every temperature row (NOTE per material) | ccx: probed (a free cube strains ε12, ε13, ε23 = α12, α13, α23 · ΔT; a clamped one has σ12 = −2μ α12 ΔT). Abaqus: no page says it of α12 in words, but four sources agree — its Conventions give material data in the strain vector (ε11, ε22, ε33, γ12, γ13, γ23) and "Abaqus always reports shear strain as engineering shear strain"; the TYPE=ANISO thermal strain increments a `UEXPAN` returns sit in Abaqus/Standard's strain arrays, which carry "NSHR engineering shear components" (`UMAT`; `VUMAT`: tensor components in Abaqus/Explicit, "different from … UMAT in Abaqus/Standard, which uses engineering components"); the Verification Guide's PZT-5H test (`ppzovallin.inp`) enters the strain coefficient d15 = 741e-12 m/V unhalved as d<sub>113</sub> and verifies the unconstrained permittivity D11 = 2.77e-8 F/m, which holds only if that slot multiplies the engineering shear strain (a tensor reading gives 6.56e-8); and an Abaqus run reported in `wenbinyugroup/sgio` (commit 9087061): a free C3D8 with α12 = 1e-3, ΔT = 1 prints E12 = 1e-3. No 2017 verification, benchmark or example deck (19,612) has an ANISO expansion |
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
| **A `*CLOAD` on a node with a `*TRANSFORM` acts in the node's local axes, in ccx as in Abaqus; so do `*BOUNDARY` DOFs and `*EQUATION` terms there. Rectangular: 1 along `a`, 2 towards `b` in the plane of `a` and `b`, 3 = 1 × 2. Cylindrical: 3 along the axis from `a` to `b`, 1 radial from the axis through the node, 2 = 3 × 1, evaluated at the node's undeformed position. Spherical (Abaqus): 1 radial from the centre `a` through the node, 3 meridional — in the plane of the polar axis `a`–`b` and the node, towards `b` — and 2 = 3 × 1 (circumferential), at the node's original position. The axes are fixed in space under NLGEOM** | converted nodal forces (tractions, beam line loads, surface-element pressures) on such nodes are given in those axes, so the global load is unchanged | Abaqus Analysis User's Guide, "Transformed coordinate systems" (2016; 2017 for the spherical axes, text and Figure 3): "fixed in space", right-handed, one transform per node, "cannot be defined for a node that lies along the line joining points a and b" (cylindrical and spherical). Probed on 2.23: the local axes recovered from a `C3D8` cube's response match these, also under NLGEOM with the node moving far. A local load equals its global counterpart to round-off on `C3D8`, `C3D20R`, `S4`, `S4R`, `S8`, `S8R`, `M3D4`, `M3D4R`, `M3D8`, `B31`, `B32R`, `CPS4`, `CPE4`, `CPS8`, `CPE8R`, `CAX4` and `CAX8` nodes, corner and midside alike; on a `C3D8` block a BC on some local DOFs equals the same constraint as `*EQUATION` (e · u = 0) and an `*EQUATION` term on local DOF 1 equals the one written in global components, exactly. `validate_with_ccx.py` repeats this on a transformed `C3D20R` face, on Cook's membrane and on `examples/transform_spherical_rigid.inp` |
| **ccx 2.23 has no spherical system: it silently reads `*TRANSFORM, TYPE=S` — any `TYPE` but `C` — as a rectangular one through `a` and `b`** (the same results as `TYPE=R`, no message). With the centre `a` at the origin that system is degenerate: NaN results with a `*CLOAD` on such a node (exit code 0), `matrix found to be singular` with a BC there (exit code 255); otherwise the axes are wrong without a sign | a `TYPE=S` card is commented out and each node gets a rectangular `*TRANSFORM` with its spherical axes (exact: the axes are fixed). Nodes on the polar axis keep the global axes, warned | probed on 2.23 (`C3D8` block; `TYPE=S`, `R`, `C`, an unknown letter and none on the same data, centre at and away from the origin) |
| **Many `*TRANSFORM` cards are fine in ccx 2.23: a rectangular card per node on all 1331 nodes of a block solves as fast as without and matches the transform-free model to round-off. ccx reads only the first 20 characters of a data field**: a longer number is cut — read wrong without a message when the cut is still a number (`6.000000000000000E-01` is read as 6), `*ERROR reading *TRANSFORM` when it is not (`6.0000000000000000E-1`) | the spherical replacement writes one card per node (nodes with equal axes share one), components with 15 decimals (≤ 18 characters) | probed on 2.23 |
| **ccx 2.23 honours a `*TRANSFORM` on a `*RIGID BODY` `ROT NODE`: its DOFs 1–3, the body's rotation, are then local too** — for BCs on some of them, prescribed rotations and moments, linear and NLGEOM. Abaqus reads rotational BCs and moments on the reference node in its local axes | the `ROT NODE`, to which the converter moves the reference node's DOFs 4–6, gets the reference node's local axes as a rectangular `*TRANSFORM`, and the rotation ties of knotted shell/beam members to it are written in those axes (probed: an `S4` edge tied to such a body, rectangular and cylindrical, linear and NLGEOM, matches the transform-free model exactly; plain ties miss by 0.5 %). A ROT NODE that also carries connector constraints, which are written in global components, keeps the global axes; there, and where the reference node's axes are undefined (reference node on the cylinder axis, two different cards, ...) moving a rotational BC or moment is warned | probed on 2.23: a `C3D8` block with a rigid end face, rectangular and cylindrical transforms on the reference node (the same card or a rectangular one with its axes on the `ROT NODE`), rotations held about local 1 and 2 with a moment, or a prescribed rotation (0.01, and 0.4 rad under NLGEOM): identical to the transform-free model with `*EQUATION`s on the `ROT NODE` (≤ 2e-16 of max \\|u\\|); an untransformed `ROT NODE` misses by 84 % (90 % NLGEOM) of max \|u\| |
| **ccx 2.23 edge cases: one with `a` = 0 gives NaN results without an error. On the cylinder axis (closer than ~1e-11) ccx silently uses the global axes. With `a` parallel to `b` the axes are arbitrary. With two `*TRANSFORM` cards on a node the last one in the file wins, whichever set it names** (Abaqus: "Multiple transformation definitions are not allowed at a node, even if one of them is at the part level and another is at the assembly level") | a converted load on such a node is commented out with the reason (the converter refuses within 1e-6 of the axis). Two cards with different data on a node are warned; with the same data, noted | probed on 2.23 (a `C3D8` cube; two cards on a node in both orders); Abaqus manual (2017) |
| **A `*TRANSFORM` whose local 3-axis is not ±Z on a node of 2-D elements is wrong in ccx 2.23, without an error.** The `*TRANSFORM` alone changes plane-strain and quadratic plane-stress models (`CPE4`, `CPE8R`, `CPS8`) by 12–91 % of max \|u\|, and `CPS4` by 91 % when local 3 lies in the plane; BCs on local DOFs there constrain partly out of the plane (`CPS4`, `CAX4`, `CAX8`: prescribed values miss by up to 15 × max \|u\|); a local `*CLOAD` misses its in-plane counterpart on `CPE`, quadratic `CPS`, `T2D2` (singular, 3e12) and `B21` nodes (`CAX` and tilted `CPS4` nodes: exact). With local 3 along +Z or −Z, or a cylinder about Z, everything matches. The Abaqus manual: "The coordinate transformation defined at a node must be consistent with the degrees of freedom that exist at the node" | warning (such a node needs a transformation about Z); converted loads there are refused (Abaqus 2-D nodes have DOFs 1 and 2 only) | probed on 2.23: `CPS4`, `CPE4`, `CPS8`, `CPE8R`, `CAX4`, `CAX8`, `T2D2`, `B21`; three tilted rectangular transforms and a cylinder about an in-plane axis against ±Z and a cylinder about Z, each alone, with a local `*CLOAD` and with local BCs; Abaqus manual (2017) |
| **ccx silently ignores a `*CLOAD` on a node that belongs to no element** | surface elements whose nodes no other element uses are warned | probed on 2.23: no error, zero displacement there |
| **ccx reads `*TEMPERATURE` only after thermal `*INITIAL CONDITIONS`** ("a *TEMPERATURE card is detected but no thermal *INITIAL CONDITIONS are given"), then needs one in every node ("no initial temperature defined in node"), and **refuses it in heat transfer and (un)coupled temperature-displacement steps**, with initial conditions too; Abaqus starts every node at 0 when none is given, and does not allow a predefined temperature field in steps where temperature is a DOF | a deck that applies `*TEMPERATURE` without initial temperatures gets `*INITIAL CONDITIONS, TYPE=TEMPERATURE` with 0 on every node ahead of the first step; with them, the nodes they leave out — knot-beam nodes too — get 0 first. Not for a `FILE=` card (ccx reads it as a CalculiX `.frd`; warned) — a `USER` card is commented out anyway; `*TEMPERATURE` in a heat transfer or coupled step is commented out (warned) | Abaqus Analysis User's Guide 2017, "Initial conditions" ("If initial conditions are not specified, all initial conditions are zero") and "Predefined fields" (restrictions); probed on 2.23 (a free heated `C3D8` cube converted without initial temperatures strains α T exactly) |
| **ccx has no connector element; a connector without a behaviour is exactly its kinematic constraint.** Abaqus `JOIN` keeps node b's coordinates in node a's local system (fixed directions, or turning with node a when it has rotations); `REVOLUTE` imposes e1a·e2b = e1a·e3b = 0 (rotation about node a's local 1-direction only); `HINGE` = `JOIN` + `REVOLUTE`, `WELD` = `JOIN` + `ALIGN`; a blank node is ground, placed at the other node | `CONN3D2`/`CONN2D2` are not emitted; their `*CONNECTOR SECTION` becomes `*EQUATION`s, `*BOUNDARY` lines, a `*RIGID BODY` (`BEAM`, `WELD`) or the `*MPC LINK` forms | Abaqus connection-type reference (JOIN, REVOLUTE, HINGE, connector elements); the hood-hinge deck has 7 zero modes (6 rigid-body + the hinge) instead of two free parts' 12, and every mode's relative rotation lies along the hinge axis to 3e-6 |
| **A `*RIGID BODY`'s `ROT NODE` (and a knot's rotation) is a total rotation vector** (Rodrigues: `nonlinmpc.f`; a knot's DOFs 4–6 are replaced by its rotation node's 1–3 in `gen3dmpc.f`) | equal vectors are equal rotations; a vector held parallel to a fixed axis is a rotation about it — so a hinge to ground (or to a held node) is exact at any angle as `*BOUNDARY` lines / equations among one rotation node's components | ccx sources; probed: a body hinged to ground about an oblique axis turned 138° follows the exact rotation to ccx's convergence tolerance (and a knotted beam end to 7e-7) |
| **Under `NLGEOM`, `*EQUATION`s that link two rigid bodies' reference / rotation DOFs are solved inaccurately** — two `*RIGID BODY` cards on one REF/ROT node are exact, but the same bodies joined by `*EQUATION`s (u5 = u1, θ4 = θ2) or chained (a member of one is the other's reference) all converge to the same wrong state | under `NLGEOM` a connector is written only where it needs no such link (to ground / a held node, between plain nodes or from a reference point to a mesh node, a rigid link); otherwise it is commented out, or written linear under `--approximate` (`[APPROX]`) | probed on 2.23: ~1 % displacement and ~10 % moment imbalance at 30°, members of the untouched body off rigidity by 7e-4; exact to all digits without `NLGEOM` |
| **DOFs 4–6 of a node without rotational elements do nothing**, and **a `ROT NODE` without stiffness crashes ccx** (exit 255, no message) | a connector rotation on a solid / plane / free node goes to a new rotation node only when it shows elsewhere (another connector, a moment, a prescribed rotation); otherwise it is eliminated (the connector-only rotation Abaqus adds constrains nothing); a `WELD`/`BEAM` between two such nodes is a `JOIN` (coincident) or a `LINK` | probed on 2.23 (a moment on a free node's DOF 6 tied to a body moves nothing) |
| **`*BOUNDARY, OP=NEW` removes model-data BCs too** | the BCs that hold a connector (to ground, or to a held node) are repeated after every `OP=NEW` card | probed on 2.23 |
| **ccx's `*BOUNDARY` prescribes displacements only** (no `TYPE`). With an amplitude a value is magnitude × amplitude (held at the end values outside its points); a value with a step-time amplitude **freezes at its end value** in later steps; `FIXED` holds the value the previous step ended with, also on a DOF that was free, but takes no rotations | `TYPE=VELOCITY / ACCELERATION` → a displacement BC whose generated amplitude is the time integral of the history from the DOF's state at the step start; a velocity BC a later step keeps (it keeps moving the DOF in Abaqus) is continued in that step | ccx manual `*BOUNDARY` / `*AMPLITUDE`, sources `tempload.f`, `bounadd.f`, `spcmatch.f`; probed on 2.23 |
| **In dynamics ccx derives a prescribed node's velocity and acceleration from its displacement** (Newmark update, implicit and explicit) | a velocity jump at a step start shows as a decaying oscillation of that node's own velocity output; the motion it imposes and the rest of the model are unaffected (a bar driven at 0.01: identical wave with or without the matching initial velocity) | `resultsini.c`; probed on 2.23 |
| **A `.frd` keeps one node set per variable and step** (the last `*NODE FILE`'s), has no node of no element (a reference point), and — in a model with any beam or shell, which ccx writes expanded to 3-D (its default `OUTPUT=3D` then) — no original node of a beam, shell, truss, membrane or plane element; `OUTPUT=2D` (read in the first step only, for the whole run) maps results back onto those nodes, exactly for U/V/RF, but averages stresses through the thickness | Abaqus history output for a set → `*NODE PRINT`/`*EL PRINT` (.dat); per `.frd` variable one set — the whole model before a set, several sets joined; a `.frd` set with nodes the `.frd` lacks is also printed (or, when all `.frd` output is U/V/RF, `OUTPUT=2D` is added) | probed on 2.23: field U + history U on a set → whole-model U lost; a set of `B32`/`S8R`/`S4` nodes → empty blocks (`OUTPUT=3D` + `NSET` too); `*RIGID BODY` reference node → never written (`OUTPUT ALL` writes it but pads the mesh with every unused node id at the origin); ccx sources `elements.f`, `noelfiles.f`, `frdset.c`, `map3dto1d2d.f`; ccx manual `*NODE FILE` |
| **One output control per step**: the last `FREQUENCY=` or `TIME POINTS=` on any `.frd`/`.dat` card applies to all of them and carries into later steps; `TIME POINTS` stop ccx under `DIRECT` and in `*MODAL DYNAMIC` and are ignored in explicit dynamics | `*OUTPUT`'s `FREQUENCY`/`NUMBER INTERVAL`/`TIME INTERVAL`/`TIME POINTS` go onto the step's first output card — the `.frd` requests' first, Abaqus' defaults included (every 10 increments in `*DYNAMIC`/`*MODAL DYNAMIC`); intervals → generated `*TIME POINTS` (before the first `*STEP`), or a `FREQUENCY` from a fixed or maximum increment, in explicit dynamics else from the increment ccx will take (next row); an explicit step whose elements cannot be sized is warned; a step without requests of its own gets the requests Abaqus carries over again, with its own control | ccx manual `*NODE FILE`/`*NODE PRINT`/`*OUTPUT`/`*TIME POINTS`; sources `noelfiles.f`, `nodeprints.f`, `outputs.f`, `checkconvergence.c`; probed on 2.23 |
| **ccx's explicit increment is its own Courant estimate** (unless a fixed or smaller maximum increment is given): 0.8/1.3 · critom · min over the elements of h·f/(2c), c the largest wave speed of the element's material, h the smallest one-point volume over a face area (×3 for tetrahedra, ×2 for a wedge's quadrilateral faces), f a factor per brick type — `C3D8R` 0.625 in 2.23 (0.938 in later sources), `C3D8` 0.9, `C3D8I` 0.125, `C3D4`/`C3D6` 1, quadratic bricks 0.3; beams, shells, membranes, plane and axisymmetric elements are sized as the bricks they expand into (axisymmetric ones as a 2° sector) | explicit output intervals become `FREQUENCY` = interval / that increment, repeated by the converter from the mesh, sections and materials (orthotropic/anisotropic: the largest normal stiffness) | ccx sources `calcstabletimeincvol.f`, `nonlingeo.c`, `gen3delem.f`, `solidsections.f`; probed on 2.23 for 19 element types (ccx prints the estimate), and on the corpus: exact in 5 of the 6 decks ccx sizes, the sixth (field-dependent elasticity) 1.35× smaller |
| **ccx has no preselected output** (`*OUTPUT` takes only `FREQUENCY`), and on `*NODE FILE` rejects `A` ("label not applicable", also in dynamics), and `V` in steady state dynamics ("V only available ..."); `PEEQ` without plasticity draws "PEEQ-output requested"; `SDV` on a `*DEPVAR` model without a user material crashes it | Abaqus' preselected field output (`VARIABLE=PRESELECT`, and the default of a step without output database requests) → whole-model `*NODE FILE`/`*EL FILE` with the ccx labels it has per procedure ([output-reference](output-reference.md)); `PEEQ` only with plasticity; `VARIABLE=ALL` adds `ENER` | Abaqus Analysis User's Guide 2017, *Output to the output database* (table 1, default output, multiple steps); probed on 2.23 (static, implicit/explicit/modal dynamics, steady state dynamics, frequency, buckle, heat transfer, coupled temperature-displacement) |

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
    (thermal ε12 = α12 ΔT, probed for all three), where Abaqus' are engineering ones
    (γ12 = α12 ΔT; sources in the table above): passed through, a converted deck would
    have twice the Abaqus shear thermal strain, so the converter halves them on every
    row (after collapsing `DEPENDENCIES`; a distribution name is left as it is).

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
    changes. A `TYPE=ORTHO` expansion with the same α11, α22, α33 runs, and is exact where
    no orientation turns it so that it has shear in global axes: a free heated C3D8 with
    α = 1e-3, 2e-3, 4e-3 strains ((1 + α ΔT)² − 1) / 2 to 1e-15 at ΔT = 1, 10 and 100
    (0.105, 0.22, 0.48 at 100), also with temperature rows, a collapsed `DEPENDENCIES`
    table, engineering-constants elasticity and an identity `*ORIENTATION`, and one held in
    x matches the multiplicative split with St. Venant–Kirchhoff elasticity to the digits
    ccx prints;
  * linear steps (also coupled and `*PLASTIC` ones) and `NLGEOM=NO` are right, and a deck
    without temperatures has no thermal strain to get wrong.

  The CalculiX sources changed both routines on 9–10 October 2026 (Dhondtguido/CalculiX
  commits 67faf64 and 2c609be), after 2.23 was posted on 2 November 2025; a build with
  the change was not tried here. One case has an exact form that 2.23 runs: an ANISO
  expansion whose shear coefficients α12, α13, α23 are zero in every row is the
  orthotropic expansion α11, α22, α33, so the converter writes it as `TYPE=ORTHO` (a NOTE
  per material; an isotropic `*ELASTIC` beside it then goes out as `ENGINEERING
  CONSTANTS`, not `ANISO`: previous item) — unless a section or composite ply that uses
  the material turns its axes so that the expansion has shear in global axes. There
  ccx 2.23 would drop that shear from an ORTHO expansion without an error, while with an
  ANISO one the step at least stops. Otherwise no form of the deck avoids it in 2.23, so
  the converter only warns, once per kind and naming the materials, when a step has
  `NLGEOM` (an explicit step counts unless it says `NLGEOM=NO`: the converter switches it
  on) and a section or composite ply uses a material with an ORTHO expansion in axes
  turned so that its thermal strain has shear in global axes, in a deck where the
  temperature changes, or one with an ANISO expansion (with shear coefficients, or turned
  so), in a deck with temperatures.
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
`*MPC LINK` matches statics exactly and keeps its length under `NLGEOM`, the same
joints, lever and link written as `CONN3D2` connectors (`JOIN`, `WELD`, `BEAM`, `LINK`)
give the same answers, a `HINGE` between beam spans releases bending about its axis and
transmits it about the other, two rigid bodies on springs hinged about an oblique axis
with an offset joint match the exact solution to 6e-8, a body hinged to ground turns 138°
under `NLGEOM` exactly about the axis, a deck whose
`*EQUATION` clashes with a BC (and has a duplicate and a loop of ties) solves with the ties
held, a clamped beam and plate keep their clamps across a later step's
`*BOUNDARY, OP=NEW` (beam theory within 0.7 %, a prescribed plate displacement exactly),
the LE10 plate with its pressure on a skin of `SFM3D8` surface elements
(which ccx does not have) reproduces the face-pressure result to 7 digits, Cook's membrane
under a shear traction matches the published 23.96 within
0.12 %, cantilevers under beam line loads match q L⁴/(8 E I) within 1.2 %, an axisymmetric
cylinder under a radial traction matches Lamé within 0.02 %, tractions on nodes with a
`*TRANSFORM` (a `C3D20R` face, Cook's loaded edge) match the same models without one to
round-off, a free cube and a circular-section beam heated without initial temperatures
expand by α T from Abaqus' default 0 (exactly, and within 5e-6), a column pulled through a
rigid reference point by a velocity BC with a `SMOOTH STEP` amplitude follows the integral
of the velocity at every increment (within 5e-5 of its travel, and on into a second step
that keeps the BC), a bar driven at one end by a velocity (explicit) or an acceleration
(implicit) carries the wave stress −ρcv (−ρca(t − z/c)) behind its front, and the
composite-shell and assembly decks also solve. This proves the full pipeline —
`*NCOPY`/`*ELGEN` expansion, node ordering, boundary sets, pressure face, sections — is
correct, not merely well-formed.

In addition, a **corpus of 1022 genuine Abaqus decks** (`corpus/manifest.py`, fetched on
demand) is converted and run on ccx 2.23: all 1022 convert with zero dangling references,
186 solve in CalculiX under their own loads (14 more solve but load nothing in the source
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

Connector elements (`CONN3D2`/`CONN2D2` with `*CONNECTOR SECTION`) have no ccx element, but
a connector without a `*CONNECTOR BEHAVIOR` is only the kinematic constraint of its
connection type, which ccx holds exactly: `JOIN`, `REVOLUTE`, `ALIGN` and `HINGE` become
`*EQUATION`s in the nodes' translations and rotation vectors (node b keeps its initial
offset in node a's turning system; the hinge leaves only the rotation about node a's local
1-direction free), with `*BOUNDARY` lines where a side is ground or held; `BEAM` and `WELD`
(the same rigid link) become a `*RIGID BODY`; `LINK` goes the `*MPC LINK` way; and the
unconstrained types (`CARTESIAN`, `CARDAN`, `ROTATION`, …) transmit nothing and are left
out. Rotations are taken where ccx carries them — a reference point's `ROT NODE`, a knot on
a shell/beam node. The equations are linear in the rotation vectors: exact in a linear or
perturbation analysis, and under `NLGEOM` exact only where one side cannot turn (the hinge
axis stays put) or no rotation enters. A hinge between two moving bodies under `NLGEOM` is
therefore commented out (written linear, with an `[APPROX]` warning, under
`--approximate`), as are connectors with a behaviour, `*CONNECTOR MOTION`/`LOAD`, and the
other connection types (`SLOT`, `SLIDE-PLANE`, `UNIVERSAL`, `CONSTANT VELOCITY`, …). In
the corpus only two decks have connectors: the hood-hinge modal deck (one `HINGE`), whose
parts now move as a mechanism instead of floating apart, and the teeter deck (`BEAM` and
`HINGE`), which still stops on its `*BEAM GENERAL SECTION`.

`*BOUNDARY, TYPE=VELOCITY / ACCELERATION` has no ccx counterpart (ccx prescribes
displacements only), so the converter integrates it: a DOF moves by the integral of the
prescribed velocity (an acceleration twice, from the velocity at the step start) from where
the step finds it. The velocity is the magnitude times its amplitude (`VALUE=ABSOLUTE`: the
amplitude itself; `TIME=TOTAL TIME` on total time), or without an amplitude the step's
default — held from the start of the step in explicit and transient dynamics (and under
`*STEP, AMPLITUDE=STEP`), ramped from its previous value under the `RAMP` default of static
steps. That last case is taken from Abaqus' general rule for BCs without an amplitude and is
**warned**: it has not been checked against an Abaqus run, and a constant velocity is easily
made explicit with an amplitude. The integral is exact at the amplitude's points and within
1e-4 of the step's travel between them (a constant or piecewise-constant velocity exact), so
it is a sampled history, not a physics approximation, and is not gated behind
`--approximate` (the converter samples `SMOOTH STEP` displacement amplitudes the same way,
far more coarsely). The displacement at each step start is followed through the steps;
where it is unknown — the DOF was free in an earlier step — a zero velocity becomes
`*BOUNDARY, FIXED` and any other line is commented out with a warning (`FIXED` takes no
rotations in ccx, so a shell or beam rotation there is commented out too; a rigid body's
rotations are held on its `ROT NODE`). The midside node the converter adds to a 2-node beam
moves with the mean of its end nodes' motions, as the Abaqus element's interior does. In a
linear perturbation step only the constraint is kept, and under `NLGEOM` angular velocities
about more than one axis of a node are warned (each rotation is integrated on its own, exact
only about a fixed axis). Not converted (warned): an amplitude with more than a thousand
oscillations in the step, and a `TIME=TOTAL TIME` amplitude after a step of unknown length
(Riks).

## What "verified" means here

Each fact above was taken from a primary source (the CalculiX manual or the Abaqus
keyword manual), and where possible **cross-checked** a second way — against the
`calculix/new_keywords` and `calculix/cae` keyword lists, the community conversion
guide, or the behaviour of an existing importer (`gmsh2ccx`, FreeCAD, PrePoMax). The
one item that could not be quoted as text (the exact mid-side *edge* sequence, which
the manual shows only as figures) is the universal Abaqus/Gmsh convention and is
corroborated by the no-permutation pass-through in `gmsh2ccx`; if you want
belt-and-suspenders certainty, run a single quadratic element through `ccx` and check a
known displacement. Likewise no Abaqus page states in words that the shear coefficients
of an anisotropic `*EXPANSION` are engineering ones: that rests on the four sources in
the table (conventions, subroutine storage, a verification deck, an outside Abaqus run);
a free unit cube with α12 ≠ 0 in Abaqus settles it (E12 = α12 ΔT).

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
* Abaqus 2017 documentation (MIT mirror), for the shear measure of `*EXPANSION, TYPE=ANISO`:
  Conventions — <https://abaqus-docs.mit.edu/2017/English/SIMACAEMODRefMap/simamod-c-conventions.htm>;
  Thermal expansion — <https://abaqus-docs.mit.edu/2017/English/SIMACAEMATRefMap/simamat-c-thermalexpan.htm>;
  UEXPAN — <https://abaqus-docs.mit.edu/2017/English/SIMACAESUBRefMap/simasub-c-uexpan.htm>;
  UMAT — <https://abaqus-docs.mit.edu/2017/English/SIMACAESUBRefMap/simasub-c-umat.htm>;
  VUMAT — <https://abaqus-docs.mit.edu/2017/English/SIMACAESUBRefMap/simasub-c-vumat.htm>;
  piezoelectric verification (`ppzovallin.inp`) — <https://abaqus-docs.mit.edu/2017/English/SIMACAEVERRefMap/simaver-c-piezogeneral.htm>
* `wenbinyugroup/sgio`, Abaqus `*Expansion, type=ANISO` reader (commit 9087061) — <https://github.com/wenbinyugroup/sgio/commit/9087061aa3>
* Abaqus Analysis User's Guide (2017), "Initial conditions in Abaqus/Standard and Abaqus/Explicit" (all initial conditions are zero unless specified) — <https://abaqus-docs.mit.edu/2017/English/SIMACAEPRCRefMap/simaprc-c-initialcond.htm>
* Abaqus Analysis User's Guide (2017), "Predefined fields" (no predefined temperature field in heat transfer, coupled thermal-electrical or fully coupled temperature-displacement analyses) — <https://abaqus-docs.mit.edu/2017/English/SIMACAEPRCRefMap/simaprc-c-fields.htm>
