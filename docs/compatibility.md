# Compatibility

The facts about Abaqus and CalculiX that the converter relies on, and where each comes from.
Each was taken from a primary source — the CalculiX manual or sources, the Abaqus manuals —
and the behavioural ones were **probed** on ccx 2.23 (the FreeCAD 1.1.4 build): small decks
run against a hand calculation or an equivalent model. `validate_with_ccx.py` repeats many
of the probes on the bundled examples ([testing](testing.md#2-end-to-end--validate_with_ccxpy)).

## Syntax and mesh

| Fact | What the converter does | Evidence |
| --- | --- | --- |
| Solid and shell node ordering is the same in both codes (C3D20, C3D10, C3D15, C3D6, S8R, S6) | passes connectivity through | ccx manual ("compatibility with ABAQUS"); `gmsh2ccx`; the LE10 benchmark |
| Solid face numbering is the same | passes `P1..P6` and `S1..S6` through | the two codes' face tables |
| ccx has no mesh-generation cards and no `*PART`/`*INSTANCE`/`*ASSEMBLY`/`*SYSTEM` | expands the cards; flattens to one numbering | ccx keyword set |
| `*INSTANCE` applies the translation before the rotation | flattens as R(p + T) | Abaqus Keywords manual |
| ccx accepts set and surface names up to 80 characters | keeps flattened names within 80, unique | probed (longer: "set name too long") |
| ccx reads only the first 20 characters of a numeric field, without an error when the cut is still a number (`6.000000000000000E-01` → 6) | writes at most 12 significant digits | probed |
| A keyword line ending in a comma continues its parameters on the next line | splices them; never merges a data line | Abaqus input syntax |
| Coupled temperature–displacement elements have the base element's name in ccx (`C3D8T` ≡ `C3D8`); the step supplies the temperature DOF | strips the `T` | ccx element sections |
| `NSET=` on `*NODE`, `ELSET=` on `*ELEMENT`, `GENERATE` on sets are accepted; an `*NSET` built from an `ELSET` is not | uses the first; expands the second | ccx manual |

## Elements and sections

| Fact | What the converter does | Evidence |
| --- | --- | --- |
| ccx 2.23 rejects linear beams with a circular section and runs `PIPE`/`BOX` sections only on `B32R`; it reads `CIRC` data as an ellipse's axis lengths | gives 2-node beams a midside node (`B32`/`B32R`); radius r → diameters 2r, 2r | probed; ccx manual |
| A rotational BC on a circular-section beam node locks its other rotations (ccx ties the section's midside nodes to its corners, which a circle cannot follow) | gives an end node with a partial or nonzero rotational BC a *knot beam* | sources `gen3dfrom1d.f`, `gen3dboun.f`; probed (held twist: 0.27 of beam theory, 0.994 with knots) |
| ccx has no planar beam or truss: `B21` runs as `B31`, `T2D2` as `T3D2`, so out-of-plane motion is free | in a planar model fixes DOF 3 on their nodes, and DOFs 4–5 at one node of a straight beam whose twist nothing holds | ccx manual 6.2.31, 6.2.34; probed (every bending mode twice) |
| `*SHELL SECTION, COMPOSITE` works only on `S6` and `S8R` | — (a linear-shell layup must be re-meshed) | ccx manual |
| ccx has no surface element (`SFM3D*`, `SFMAX*`, `SFMGAX*`); in Abaqus they have no stiffness and carry loads, mass or rebar | leaves them out of the mesh and applies their loads as nodal forces; keeps them, with a warning, if they carry rebar or mass that acts (unless `--approximate`) | Abaqus "Surface elements"; probed |
| An element-based surface-element `P` acts along the element normal; a `*DSLOAD P` against the surface normal (`SPOS` = element normal) | applies each sign | Abaqus element libraries; LE10 `SFM3D8` skin reproduces the face pressure to 7 digits |

## Materials

| Fact | What the converter does | Evidence |
| --- | --- | --- |
| `*ELASTIC` constants come in the same order; only the `TYPE` token differs | renames `ORTHOTROPIC` → `ORTHO`, `ANISOTROPIC` → `ANISO` | ccx manual |
| `*EXPANSION, TYPE=ANISO`: Abaqus' α12, α13, α23 are engineering shear (γ12 = α12 ΔT), ccx's are tensor components (ε12 = α12 ΔT) | halves them on every temperature row (a NOTE per material) | probed in ccx; Abaqus: Conventions, the `UEXPAN`/`UMAT` strain arrays, the PZT-5H verification `ppzovallin.inp`, and an Abaqus run in `wenbinyugroup/sgio` |
| In linear steps of a deck with temperatures, ccx 2.23 uses a wrong stiffness when the `*ELASTIC` is less anisotropic than the `*EXPANSION` (isotropic beside ORTHO/ANISO; orthotropic beside ANISO without an orientation): a heated free cube shrinks, frequencies come out 17× low | writes the `*ELASTIC` as `ENGINEERING CONSTANTS` or `ANISO` with the same stiffness, adding temperature rows so the interpolation matches Abaqus' | probed on solids, shells, membranes, plane elements, beams and trusses; sources `linel`, `materialdata_me`, `elastics` |
| Under NLGEOM, ccx 2.23 treats an ORTHO expansion as diagonal in global axes (the shear of turned material axes is lost) and stops an ANISO one with "too many cutbacks" | writes a zero-shear ANISO expansion as ORTHO where no orientation turns it; warns about the rest | probed; sources `calcmechstrain`, `modifystressstiff` (fixed in the CalculiX sources after 2.23, October 2026) |
| ccx's Johnson-Cook plasticity switches on only with a `*RATE DEPENDENT, TYPE=JOHNSON COOK` card; ccx silently skips `*PLASTIC` forms it lacks | adds a rate-independent card (C = 0) when the deck has none; comments `HARDENING=USER` and Chaboche `PARAMETERS` out (the material runs elastic, warned) | probed |
| ccx ignores `DEPENDENCIES=` and in effect uses the first row | collapses the table to field = 0, Abaqus' no-field state | probed |
| ccx reads `*TEMPERATURE` only after thermal `*INITIAL CONDITIONS`, then needs one on every node, and refuses it in heat transfer and coupled steps; Abaqus starts every node at 0 | adds initial temperatures of 0 where none are given; comments `*TEMPERATURE` out in heat transfer and coupled steps | Abaqus 2017 "Initial conditions", "Predefined fields"; probed |
| ccx 2.23 honours a `*DISTRIBUTION` per element only under `*SOLID SECTION` (default line first, additional rotation on the first line only, origin ignored); shells and membranes get its first line; a second orientation naming the same distribution stops ccx; a distribution named like a number (`D1`, `12`) zeroes the orientation | gives each orientation its own distribution, resolved per element for solids; splits shell and membrane sections into one orientation and section per direction; renames per instance, offsets labels, turns axes with the instance | probed; ccx's distribution, orientation and section readers |
| ccx 2.23's `*DAMAGE INITIATION` knows only `RICE TRACEY` and `JOHNSON COOK` | passes the card through with a note | the 2.23 binary; corpus decks |

## Constraints and rigid bodies

| Fact | What the converter does | Evidence |
| --- | --- | --- |
| ccx eliminates the first term of every `*EQUATION` and stops when that DOF also has a `*BOUNDARY` or is eliminated twice ("cascade"); Abaqus resolves such overconstraints itself | reorders terms so a free DOF is eliminated (bipartite matching), drops equations that follow from the others, warns about the rest | ccx manual; probed |
| A closed loop of equation ties is accepted, but ccx holds the whole loop at zero | drops the closing equation | probed |
| A rigid coupling makes its members' coupled DOFs dependent (`*RIGID BODY`, `*MPC BEAM`: every translation; `*KINEMATIC`: the listed DOFs) | takes off member BCs the reference node imposes anyway; moves identical BCs on `*RIGID BODY` nodes to the reference node where that is the same constraint, as Abaqus/Standard does (otherwise only with `--approximate`); warns about the rest | probed; Abaqus "Coupling constraints", "Overconstraint checks" |
| ccx 2.23 rejects a rigid constraint on a shell, membrane, beam or truss node unless ccx made the node a *knot* (2.22 ran them) | attaches a force-free `B31` (elset `ABQ2CCX_KNOT`) to each such node and ties its rotations to the coupling's; not possible in explicit dynamics ("linear and nonlinear MPC's depend on each other") | probed |
| ccx ignores BCs and moments on DOFs 4–6 of a `*RIGID BODY`'s `REF NODE`; the body's rotation lives on DOFs 1–3 of its `ROT NODE`, as a total rotation vector | adds an explicit `ROT NODE` and moves them there | probed; sources `nonlinmpc.f`, `gen3dmpc.f` |
| ccx's `*MPC BEAM` keeps the distance between two nodes (Abaqus `LINK`, not Abaqus `BEAM`) and rejects nodes of 1-D and 2-D elements | `LINK` → ccx `*MPC BEAM` under NLGEOM, a linearised `*EQUATION` otherwise; Abaqus `BEAM` → `*RIGID BODY` | probed |
| A rotational DOF of a non-knot shell or beam node does nothing in an `*EQUATION` | ties `*MPC TIE` rotations through knots | probed (a `TIE`d joint behaved as a hinge) |
| A connector without a behaviour is exactly its kinematic constraint (`JOIN`, `REVOLUTE`, `ALIGN`, `HINGE`, `WELD`, `BEAM`, `LINK`) | writes `*EQUATION`s, `*BOUNDARY` lines or a `*RIGID BODY`; comments behaviours and other types out | Abaqus connection-type reference; the hood-hinge deck keeps 6 rigid-body modes + 1 mechanism |
| Under NLGEOM, `*EQUATION`s linking two rigid bodies' reference or rotation DOFs converge to a wrong state (~1 % displacement at 30°) | writes NLGEOM connectors only in forms that stay exact (to ground, rigid links, mesh nodes); the rest commented, or linear with `--approximate` | probed |
| DOFs 4–6 of a node without rotational elements do nothing; a `ROT NODE` without stiffness crashes ccx | routes a connector rotation on such a node to a rotation node only where it acts elsewhere | probed |
| `*BOUNDARY, OP=NEW` removes model-data BCs too | repeats the BCs that hold a connector after every `OP=NEW` | probed |

## Loads and boundary conditions

| Fact | What the converter does | Evidence |
| --- | --- | --- |
| ccx has no surface-traction load, and reads `P1`/`P2` on a beam as a pressure on its expanded section face | applies tractions and beam line loads as consistent nodal forces (Gauss quadrature over the undeformed faces) | the 2.23 binary; probed (`P1` on a 1 × 2 section: twice beam theory) |
| A `*CLOAD` on a `CPS`/`CPE` node is the total for the section thickness; on a `CAX` node, the total over 2π | scales by the thickness; integrates over the full circle | probed |
| `*CLOAD`s on one DOF add within a step and replace across steps; `OP=NEW` removes only earlier steps' loads; ccx's `*DLOAD, OP=NEW` also removes the `*DSLOAD` pressures Abaqus keeps | writes converted forces as totals, never with `OP=NEW`; repeats those pressures | probed |
| Abaqus traction directions are normalized; `TRSHR` is projected onto the reference surface and stays tangent to it; `FOLLOWER=YES` and `CONSTANT RESULTANT=NO` by default; beam loads in global directions never follow the beam | nodal forces are exact for small strain, and under NLGEOM only for `TRVEC` with `FOLLOWER=NO, CONSTANT RESULTANT=YES`; the rest converts only with `--approximate` | Abaqus Keywords manual (`*DSLOAD`, `*DLOAD`); Analysis User's Guide, "Distributed loads" |
| ccx silently ignores a `*CLOAD` on a node of no element | warns about surface elements whose nodes no other element uses | probed |
| ccx's `*BOUNDARY` prescribes displacements only; a value with a step-time amplitude freezes at its end value in later steps; `FIXED` holds the previous end value but takes no rotations | integrates `TYPE=VELOCITY`/`ACCELERATION` into a displacement BC with a generated amplitude (exact at its points, within 1e-4 of the travel between them) and continues it in later steps that keep it | ccx manual; sources `tempload.f`, `bounadd.f`, `spcmatch.f`; probed |
| Abaqus holds a velocity BC without amplitude constant over a static or quasi-static step ("always a STEP function") and of an Abaqus/Explicit step; elsewhere the step or procedure default applies | applies the same defaults | Abaqus `*BOUNDARY`, "Defining an analysis" |
| A load or BC without an amplitude takes its procedure's default in ccx as in Abaqus: a ramp from the previous value in `*STATIC` and steady-state steps, a step in dynamics, `*VISCO` and transient steps. But Abaqus/Standard always ramps a displacement BC ("always a RAMP function"), and Abaqus/Explicit ignores its value and enforces a zero velocity ("does not admit jumps in displacement"); Abaqus/Explicit also ignores `*STEP, AMPLITUDE` | where ccx would step such a line, gives it ccx's own step ramp (`AMPLITUDE=RAMP12357111317`, which ccx defines once a `*STEP` has `AMPLITUDE=`; the step gets `AMPLITUDE=STEP`, its default anyway); in an explicit step writes a zero BC, or `FIXED` where the DOF may have moved, and drops `*STEP, AMPLITUDE`; a zero line on DOFs still at zero stays as it is | Abaqus `*BOUNDARY`, "Defining an analysis", "Fully coupled thermal-stress analysis", Verification Guide (boundary condition types); sources `tempload.f`, `steps.f`, `allocation.f`, `spcmatch.f`; probed for each procedure |
| In dynamics ccx derives a prescribed node's velocity from its displacement (Newmark) | — (a velocity jump shows only in that node's own velocity output) | source `resultsini.c`; probed |
| A later step's `*BOUNDARY, OP=NEW` loses the rotational BCs it re-specifies on shell and beam nodes, and on shells zeroes unrelated BCs | drops an `OP=NEW` that removes nothing; otherwise gives the affected nodes knot beams (warned with an explicit step) | sources `boundarys.f`, `gen3dboun.f`, `usermpc.f`; probed (a re-clamped cantilever moved 1.87e5 instead of 0.595) |

## `*TRANSFORM`

| Fact | What the converter does | Evidence |
| --- | --- | --- |
| On a node with a `*TRANSFORM`, ccx — like Abaqus — reads `*CLOAD`s, `*BOUNDARY` DOFs 1–3 and `*EQUATION` terms in the local axes (rectangular: 1 along a, 2 towards b; cylindrical: 3 along the axis, 1 radial; fixed in space under NLGEOM) | gives converted forces and connector rows in each node's local axes | Abaqus "Transformed coordinate systems"; probed on 17 element types |
| ccx has no spherical system and silently reads `TYPE=S` as rectangular (NaN or a singular matrix with the centre at the origin) | comments it out and gives each node a rectangular transform with its spherical axes; nodes on the polar axis keep global axes (warned) | probed |
| ccx honours a `*TRANSFORM` on a `ROT NODE` (the body's rotation becomes local) | gives the `ROT NODE` its reference node's axes, and writes rotation ties and connector rows on it in those axes | probed |
| ccx misreads `*EQUATION` terms on DOFs 4–6 of a transformed node (DOF 4 globally, 5–6 through an out-of-range read), and applies `*BOUNDARY` DOFs 4–6 there globally | comments out connector rotations on such DOFs | sources `equations.f`, `bounadd.f`; probed |
| ccx turns an eliminated local DOF into a global one by its own rule and stops when none is left | orders connector rows so ccx finds one for each; the equation-settling pass follows the rule | sources; probed |
| Under NLGEOM ccx does not converge on an `*EQUATION` with several local translations of one transformed node | reduces rows to one local DOF per equation; comments out NLGEOM connectors between differently transformed nodes | probed |
| Edge cases: a = 0 gives NaN; on the cylinder axis ccx silently uses global axes; with two cards on a node the last wins (Abaqus forbids it); on 2-D nodes a local 3-axis other than ±Z gives wrong results | refuses converted loads on such nodes; warns about two cards and about tilted 2-D transforms | probed; Abaqus manual |
| `*RIGID BODY` and ccx's `*MPC BEAM` are not affected by a `*TRANSFORM` on their nodes | writes them as without | probed |
| ccx takes a transformed node's BCs through an auxiliary node: `*BOUNDARY, FIXED` there holds the global component as the local value (2.23; fixed in the sources in July 2026), and the step ramp starts a BC new on a DOF from that node's value (0), not from where the DOF is | writes no `FIXED` there (an explicit hold is kept as given, a velocity BC's zero rate from an unknown start commented out, both warned); ramps a node's displacement BCs only all together, and only in the first step or where each DOF had a BC before (else ccx's step, warned) | source `bounadd.f`; probed |

## Steps, dynamics and output

| Fact | What the converter does | Evidence |
| --- | --- | --- |
| NLGEOM is off by default in ccx and Abaqus/Standard, on in Abaqus/Explicit | adds `NLGEOM` and a large `INC` to explicit steps | ccx and Abaqus manuals |
| ccx has no Riks method and would run `*STATIC, RIKS` as plain static without saying so | comments the step out (`--approximate`: plain static) | probed |
| ccx's explicit increment is its own Courant estimate, which for circular-section beams is about 1.3× the stable limit (it measures the box around the circle) | caps the increment for such beams with ccx's formula and the square through the section's corner nodes; turns explicit output intervals into `FREQUENCY` from the estimate | sources `calcstabletimeincvol.f`, `gen3dfrom1d.f`; probed on 19 element types |
| A `.frd` keeps one node set per variable and step and has no node of no element; a model with any beam or shell is written expanded to 3-D, without the original beam, shell, truss, membrane or plane nodes; `OUTPUT=2D` (first step only, whole run) maps U/V/RF back exactly but averages stresses through the thickness | sends history output to the `.dat`; joins sets per variable; prints sets the `.frd` cannot show, or adds `OUTPUT=2D` when the `.frd` gets only U/V/RF | probed; sources `frdset.c`, `map3dto1d2d.f` |
| ccx has one output control per step (the last `FREQUENCY` or `TIME POINTS`, carried into later steps); `TIME POINTS` stop ccx under `DIRECT` and in `*MODAL DYNAMIC` and are ignored in explicit dynamics | puts `*OUTPUT`'s frequency or intervals on the step's first output card, as `*TIME POINTS` or a `FREQUENCY` | ccx manual; probed |
| ccx has no preselected output; its `*NODE FILE` rejects `A`, and `V` in steady-state dynamics | writes Abaqus' preselected field output per procedure in ccx labels ([output reference](output-reference.md)) | Abaqus 2017 "Output to the output database"; probed |
| ccx 2.23 aborts writing contact output in a model with axisymmetric elements once `S` goes to the `.frd`, unless every pair is face-to-face; for 2-D models it writes node-to-surface contact at nodes the `.frd` lacks | writes contact output only where ccx can | probed on 23 element types |

## Version notes

* Written for CalculiX 2.22–2.23 and validated on **2.23**, the build in FreeCAD 1.1.4. There
  is no 2.24 as of October 2026.
* 2.23 is stricter than 2.22. Step data outside a `*STEP`, a section naming an undefined
  material, and DOFs 4–6 on plane-element nodes now crash ccx (segfault or bus error) instead
  of stopping it with an `*ERROR`; the converter comments, warns about or drops them. Rigid
  constraints on shell and beam nodes are rejected, hence the knot beams.
* The CalculiX sources fixed the NLGEOM thermal-expansion problems after 2.23 (October 2026);
  a build with the fix was not tried.
* Older versions gate some cards: `*MEMBRANE SECTION` from 2.14, the `*ORIENTATION` rotation
  line from about 2.15, `C3D8R` hourglass control from 2.3.

## What does not convert or solve

Abaqus has about 570 keywords and CalculiX about 140, so "unsupported keyword" is expected
for any non-trivial deck. The converter classifies every keyword — translated, dropped as
organisational, or commented with guidance — and the [keyword reference](keyword-reference.md)
gives the full split.

Of the 1022 corpus decks, 603 do not solve; most need what stock ccx does not have: user
materials (353 decks), user elements (66), and other user subroutines, Riks, explicit coupled
temperature–displacement steps, cohesive and acoustic models, rigid elements. Others are
incomplete source decks (46). The [testing page](testing.md#3-corpus--corpus-and-teststest_corpuspy)
breaks them down. Fixing a first error often only exposes a second, fundamental one, so the
converter translates or clearly flags each incompatibility rather than forcing a deck to run.

**If your converted deck won't solve,** read the first `*ERROR` ccx prints. A missing
capability or an incomplete deck needs remodelling (replace a UMAT with a built-in material,
mesh a rigid surface, add the missing step, refine an inverted element), not a different
conversion. The report at the top of the converted deck lists the cards that were
approximated or commented out; [troubleshooting](troubleshooting.md) covers the common
errors.

## What "verified" means

Each fact comes from a primary source and, where possible, a second one: the
`calculix/new_keywords` and `calculix/cae` keyword lists, the community conversion guide, an
existing importer (`gmsh2ccx`, FreeCAD, PrePoMax), or a probe. Two facts rest on indirect
evidence: the midside edge-node sequence, which the manuals show only in figures (it is the
universal Abaqus/Gmsh convention, and `gmsh2ccx` passes it through unpermuted), and the
engineering shear measure of `*EXPANSION, TYPE=ANISO`, which no Abaqus page states in words
(four sources agree; a free unit cube with α12 ≠ 0 in Abaqus would settle it).

## Sources

* CalculiX CrunchiX User's Manual v2.23 — <https://www.dhondt.de/ccx_2.23.pdf>; v2.22 —
  <https://www.dhondt.de/ccx_2.22.pdf>; v2.7 (HTML) —
  <https://web.mit.edu/calculix_v2.7/CalculiX/ccx_2.7/doc/ccx/ccx.html>
* CalculiX "New features" — <http://www.dhondt.de/new_calc.htm>
* `calculix/new_keywords` — <https://github.com/calculix/new_keywords>; `calculix/cae` —
  <https://github.com/calculix/cae>
* "A Guide to Modifying Abaqus Input Files for Use in CalculiX" —
  <https://calculix.discourse.group/t/a-guide-to-modifying-abaqus-input-files-for-use-in-calculix/1430>
* CalculiX Discourse — <https://calculix.discourse.group/> · PrePoMax forum —
  <https://prepomax.discourse.group/>
* Abaqus Keywords Reference Manual, `*INSTANCE` —
  <https://www.sharcnet.ca/Software/Abaqus/6.14.2/v6.14/books/key/ch09abk19.html>
* Abaqus Analysis User's Guide (2016): "Coupling constraints" —
  <https://ceae-server.colorado.edu/v2016/books/usb/pt08ch35s03aus135.html>; "Overconstraint
  checks" — <https://ceae-server.colorado.edu/v2016/books/usb/pt08ch35s06aus140.html>
* Abaqus 2017 documentation (MIT mirror): Conventions —
  <https://abaqus-docs.mit.edu/2017/English/SIMACAEMODRefMap/simamod-c-conventions.htm>;
  Thermal expansion —
  <https://abaqus-docs.mit.edu/2017/English/SIMACAEMATRefMap/simamat-c-thermalexpan.htm>;
  UEXPAN — <https://abaqus-docs.mit.edu/2017/English/SIMACAESUBRefMap/simasub-c-uexpan.htm>;
  UMAT — <https://abaqus-docs.mit.edu/2017/English/SIMACAESUBRefMap/simasub-c-umat.htm>;
  VUMAT — <https://abaqus-docs.mit.edu/2017/English/SIMACAESUBRefMap/simasub-c-vumat.htm>;
  piezoelectric verification —
  <https://abaqus-docs.mit.edu/2017/English/SIMACAEVERRefMap/simaver-c-piezogeneral.htm>;
  Initial conditions —
  <https://abaqus-docs.mit.edu/2017/English/SIMACAEPRCRefMap/simaprc-c-initialcond.htm>;
  Predefined fields —
  <https://abaqus-docs.mit.edu/2017/English/SIMACAEPRCRefMap/simaprc-c-fields.htm>
* `wenbinyugroup/sgio`, an Abaqus `*Expansion, type=ANISO` run (commit 9087061) —
  <https://github.com/wenbinyugroup/sgio/commit/9087061aa3>
