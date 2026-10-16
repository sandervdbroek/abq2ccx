# Troubleshooting

Converting cleanly is only half the job — the deck still has to run in CalculiX and
give the right answer. This page lists the failures people actually hit (sourced from
the [CalculiX Discourse](https://calculix.discourse.group/) and
[PrePoMax](https://prepomax.discourse.group/) forums and the manual), what causes
them, and how to fix them.

## CalculiX stops with an error

### `*ERROR in cascade: the DOF corresponding to node N in direction d is detected on the dependent side of a MPC and a SPC`

The single most common crash on converted decks. A degree of freedom is **both** the
dependent term of an `*EQUATION`/`*MPC`/tie/coupling **and** the target of a
`*BOUNDARY`. CalculiX eliminates the dependent DOF, so it can't also be constrained.

* The converter resolves what it can exactly, as Abaqus would: it lists the terms of an
  `*EQUATION` (also the ones it writes) so that a DOF without a BC is eliminated, drops an
  equation that follows from the others and zero BCs, and takes a BC off a rigid
  constraint member's eliminated DOF when the reference node's own BCs impose it anyway. What remains is warned
  ("Possible overconstraint: node N DOF d …"). Fix those by removing either the BC or the
  constraint on that DOF.
* **Rigid couplings** (`*RIGID BODY`, `*COUPLING`+`*KINEMATIC`, `*MPC BEAM`) make their
  members' coupled DOFs dependent. Where the reference node's own BCs already impose a member's BC
  (the same value, no rotation about the other two axes), the converter removes it — exact,
  and Abaqus resolves the redundancy the same way. On a `*RIGID BODY` Abaqus moves identical
  BCs on the body's nodes to the reference node, with zero rotations about the other axes,
  and the converter does the same where that changes nothing (note "moved to the reference
  node … Exact."). Otherwise the warning says what Abaqus does and why it is not done:
  * kinematic coupling or `*MPC` — Abaqus/Standard ignores the BC (the node follows the
    constraint); `--approximate` drops it the same way;
  * `*RIGID BODY`, "holds the body more than these BCs do" — the BC'd nodes leave the body a
    rotation the move would fix (one node, one line seen along the DOF, one in-plane
    direction on a flat face), or the body may have turned before the step (free in an
    earlier step), or a zero velocity on the reference node meets zero displacements on the
    nodes. `--approximate` moves them as Abaqus does; or put the BC on the reference node;
  * `*RIGID BODY`, "the BCs differ between the body's nodes" or "disagree with the reference
    node's own BCs" — Abaqus stops on these too: fix the BCs (one BC on the reference node);
  * `*RIGID BODY` with a `FIXED`/`USER`/acceleration BC or local (`*TRANSFORM`) DOFs — not
    moved by the converter: put the BC on the reference node.
* The sibling message `*ERROR reading *EQUATION: the DOF corresponding to node N in
  direction d is detected on the dependent side of two different MPC's` has the same
  cause (two equations eliminating one DOF) and the same handling.
* A closed loop of `*EQUATION` ties (u1 = u2, u2 = u3, u3 = u1) does **not** stop ccx: it
  warns `zero coefficient on the dependent side of an equation` and holds the loop at zero.
  The converter drops the loop's closing equation; if you see that warning on a deck you
  wrote by hand, look for one.
* For 2-D/plane models, keep DOF 3 out of couplings (the converter does for `*KINEMATIC`).
* It often appears after assembly flattening or `*SYMM` expansion drops a BC onto a
  coupled node.

### `*ERROR reading *ELSET` / "The set definition was used before the set was created"

CalculiX is **order-dependent** (Abaqus tolerates forward references). The converter
emits geometry → sets → sections → steps in that order, which avoids this. If you see
it, you probably hand-edited the output and moved an `*INCLUDE` or a set use above its
definition.

### `*ERROR … nonpositive jacobian`

Distorted or inverted elements, bad node ordering, or extreme small-dimension scaling.
Notably also second-order elements whose mid-side nodes collide after CalculiX expands
shells/beams to solids. Fixes: remesh, or drop to a linear element. (Node *ordering*
itself is not the cause — it is verified identical to Abaqus.)

### `*ERROR … no material defined` / element type rejected

* A `*SOLID SECTION`/`*SHELL SECTION` references a material that wasn't emitted —
  check the report for a commented-out material card.
* The element type has no CalculiX equivalent (cohesive/gasket/rigid). The
  report flags these; they must be remodelled (see below).
* Abaqus surface elements (`SFM3D*`, `SFMAX*`) only get here when the converter kept them:
  normally they leave the mesh (no stiffness) and their loads become nodal forces, but
  rebar layers or a mass that acts (`*SURFACE SECTION, DENSITY=` in a dynamic or frequency
  step, or under gravity) keep them — the report says which. `--approximate` drops them
  anyway, losing that stiffness or mass.

### Composite shell errors

`*SHELL SECTION, COMPOSITE` works only on **S6 or S8R** elements — `S4`/`S4R`/`S3` are
rejected, and `S8` (full integration) is not `S8R`. A linear-shell composite mesh
can't be relabelled (node counts differ); it must be re-meshed with quadratic shells.

### `*ERROR reading *ORIENTATION: distribution … has not been defined`, or spooles reports `matrix found to be singular`

Both come from per-element orientations given by a `*DISTRIBUTION` (Abaqus discrete
orientations, variable-angle-tow layups) when the ccx deck is written by hand. The
converter's output avoids both:

* ccx gives a distribution to the **first** `*ORIENTATION` that names it, so a second
  `*ORIENTATION` naming the same distribution stops with "has not been defined". Give
  each orientation its own copy of the distribution (the converter does).
* ccx first tries to read the orientation's data line as a number, so a distribution
  named like one — `D1`, `E5`, `Q1`, `12`, `1.5` — silently turns the orientation into an
  all-zero one, and the solver then finds the stiffness matrix singular. Rename the
  distribution (the converter does).
* When the converter comments an `*ORIENTATION` out because its distribution has **no
  data lines** — typically an `INPUT=` file (a TexGen `.ori` file, say) that is not next
  to the deck — ccx then stops at the section with "nonexistent orientation". Copy the
  file alongside the deck and convert again; without it the per-element directions are
  simply unknown.

### `*ERROR reading *TEMPERATURE: a *TEMPERATURE card is detected but - no thermal *INITIAL CONDITIONS are given OR - this is a *HEAT TRANSFER or (UN)COUPLED TEMPERATURE-DISPLACEMENT analysis`, or `*ERROR in checktemp: no initial temperature defined in node N`

ccx reads a `*TEMPERATURE` card only after thermal `*INITIAL CONDITIONS`, and then needs
an initial temperature in every node. Abaqus needs neither: a node without one starts at 0.

* When a deck applies `*TEMPERATURE` without initial temperatures, the converter adds
  `*INITIAL CONDITIONS, TYPE=TEMPERATURE` with `ABQ2CCX_ALL_NODES, 0.` ahead of the first
  step; when the deck's own initial conditions leave nodes out (the free nodes of knot
  beams too), those get 0 first. Thermal strains then count from 0, as in Abaqus — a deck
  whose temperatures are absolute (in K, or a room temperature in °C) expands from 0, not
  from the room, in both codes.
* Not for a `*TEMPERATURE, FILE=` card (warned): ccx reads `FILE=` as a CalculiX `.frd`
  results file, not Abaqus' `.odb`/`.fil` — without one it only prints `ERROR in readfrd`
  and runs on undefined temperatures. Run the heat transfer in ccx and point `FILE=` at its
  `.frd`, then add the initial temperatures. (A `USER` card, an Abaqus `UTEMP`, is commented
  out.)
* In a `*HEAT TRANSFER` or `*COUPLED TEMPERATURE-DISPLACEMENT` step temperature is DOF 11.
  Abaqus does not allow `*TEMPERATURE` there either, and ccx refuses it even with initial
  temperatures, so the converter comments it out (warned): prescribe the temperature with
  `*BOUNDARY` on DOF 11.

### "Job killed without any error"

Usually out of memory. Big models need a lot of RAM (rule of thumb from the forum:
~32 GB for ~1M equations). Reduce the model or add memory.

## It runs but the results look wrong

These are the silent ones — no error, wrong physics.

* **Geometric nonlinearity (`NLGEOM`) is off by default in ccx.** Abaqus/Standard is
  the same, so a converted static step keeps its meaning. Abaqus/Explicit defaults to
  `NLGEOM=ON`; the converter therefore adds `NLGEOM` (and a large `INC`) to every
  `*DYNAMIC, EXPLICIT` step.
* **A step solves to zero displacement.** Check the report for `Step N is loaded in the
  Abaqus deck (...), but no load survives the conversion`: every load of that step was
  commented out — a user-subroutine load or BC (port it to the ccx subroutine the warning
  names), an NLGEOM follower traction (`--approximate` applies it as fixed nodal forces), a
  load on an undefined surface, or a traction on nodes whose `*TRANSFORM` axes are unknown
  (spherical, a node on the cylinder axis, degenerate data, two transforms on one node).
  ccx then solves the step with no load at all. A deck that loads nothing even in Abaqus
  gets a note instead.
* **A Riks step does not run.** ccx has no arc-length solver; passed through, it would
  silently solve a load-controlled static step instead, so the converter comments the
  `*STATIC, RIKS` card out and ccx stops at that step. `--approximate` accepts the
  plain-static reframing explicitly.
* **Linear perturbation vs general static.** A perturbation `*STATIC` uses the
  base-state stiffness in Abaqus; the converter maps it to a linear ccx `*STATIC`.
  Correct for small-strain elastic perturbations — verify if the base state was
  nonlinear. In ccx it is a general step, so its loads persist into later steps (the
  converter warns when steps follow).
* **A material quietly lost its plasticity.** ccx implements tabulated
  isotropic/kinematic/combined hardening and Johnson-Cook, and silently skips any other
  `*PLASTIC` card. Its Johnson-Cook law only switches on together with a `*RATE
  DEPENDENT, TYPE=JOHNSON COOK` card — alone the material runs elastic — so the converter
  adds a rate-independent one (C = 0) when the deck has none. `HARDENING=USER` and
  Chaboche `DATATYPE=PARAMETERS` cards are commented out, so the report tells you when a
  material now runs elastic.
* **The converted `*EXPANSION, TYPE=ANISO` has half the shear coefficients.** That is
  intended: Abaqus gives α12, α13, α23 as engineering shear strain per degree
  (γ12 = α12 ΔT), ccx reads tensor components (ε12 = α12 ΔT), so the converter halves them
  (a NOTE per material). Keep them halved if you edit the converted deck.
* **A heated part shrinks, or a model with temperatures is far too soft.** In linear steps
  of a deck with temperatures (an initial temperature field), ccx 2.23 silently uses a
  wrong stiffness — for thermal and mechanical loads and for frequencies alike — when a
  material's `*EXPANSION` is more anisotropic than its `*ELASTIC`: an isotropic `*ELASTIC`
  beside `TYPE=ORTHO` or `ANISO`, or an orthotropic / engineering-constants one beside
  `TYPE=ANISO` without an `*ORIENTATION`. The converter writes such an `*ELASTIC` as
  `ENGINEERING CONSTANTS` or `ANISO` with the same stiffness, adding temperature rows when
  E and ν both vary with temperature (the report has a NOTE per material); keep that form
  if you edit the converted deck.
* **Under `NLGEOM`, turned orthotropic thermal strains lose their shear, and an
  anisotropic expansion stops the step.** In `NLGEOM` steps ccx 2.23 treats an `*EXPANSION,
  TYPE=ORTHO` as diagonal in global axes: where an `*ORIENTATION` or a composite ply angle
  turns the material axes, the shear part of the thermal strain is silently lost (a cube
  turned 30° keeps its normal thermal strains but gets no shear strain; a [30/−30]s
  laminate's in-plane thermal strains come out 8 and 41 % off) — with any elastic type,
  element and procedure, `*PLASTIC` and explicit dynamics included. An `*EXPANSION,
  TYPE=ANISO` makes `NLGEOM` steps stop with "too many cutbacks" as soon as the deck has
  temperatures, turned or not, even where the temperature never changes. Linear steps are
  right. An ANISO expansion without shear coefficients is written as `TYPE=ORTHO` (a NOTE
  per material), which runs and is exact — unless an `*ORIENTATION` or a ply angle turns
  it so that it has shear in global axes: there ORTHO would lose that shear silently, so
  it stays ANISO and is warned. For the rest no form of the deck avoids either in 2.23
  (the CalculiX sources fixed both in October 2026), so the converter only warns, naming
  the materials: check one element's thermal strain against a hand calculation, or keep
  the thermal load out of `NLGEOM` steps where that is acceptable.
* **Field-variable dependence is gone.** ccx ignores `DEPENDENCIES=` and would use the
  first table row; the converter keeps the Abaqus no-field state (field = 0) and warns.
* **Per-element (`*DISTRIBUTION`) orientations quietly collapse to one.** ccx 2.23 gives
  each element its own distribution line only under `*SOLID SECTION`; there the elements
  it does not list get the *first* line, the `*ORIENTATION`'s additional-rotation line
  turns only the first line, and an origin given after `a, b` is ignored. Under a
  `*SHELL SECTION` — plain or `COMPOSITE` — or a `*MEMBRANE SECTION`, every element gets
  the first line. The
  converter therefore writes, for solids, one resolved line per element (default line
  first, the rotation and the origin already applied to the axes, no rotation line) and,
  for shells and membranes, one plain `*ORIENTATION` and section per distinct direction.
  If you edit the converted deck, keep that form.
* **A rigid body's reference point ignores rotations.** ccx carries a `*RIGID BODY`'s
  rotations on DOFs 1–3 of a separate `ROT NODE` and silently ignores BCs and moments on
  DOFs 4–6 of the `REF NODE` (a moment there does nothing). The converter adds an explicit
  `ROT NODE` and moves those BCs/moments onto it — keep that in mind when editing the
  converted deck or reading reaction moments.
* **Short beams on coupled shell/beam nodes (`ABQ2CCX_KNOT`).** ccx 2.23 rejects a rigid
  coupling on a shell, membrane, beam or truss node unless ccx has made the node a
  "knot", so the converter attaches a short beam with a free end and no density to each
  such node; the knot also carries the node's rotations, which `*EQUATION`s tie to the
  coupling's. Circular-section beam nodes with a rotational BC on only some of DOFs 4–6
  (or a nonzero one) get the same beam: without the knot ccx 2.23 locks the node's other
  rotations too. So do the shell/beam nodes whose rotational BCs a later step's
  `*BOUNDARY, OP=NEW` would otherwise break. The beams carry no load — ignore them in the
  results (whole-model output lists them).
* **`C3D8R` hourglassing.** CalculiX auto-enables hourglass control only from v2.3.
  For bending-dominated linear bricks prefer `C3D8I` or `C3D20R`. There is no
  artificial-energy output in ccx, so check a scaled deformed shape for hourglass modes.
* **Shells/beams are expanded to 3-D internally.** Add `OUTPUT=3D` to `*NODE FILE` to
  see the expanded geometry and through-thickness stress; otherwise the `.frd` looks
  "wrong." Results for non-axis-aligned beams with applied moments can be off.
* **NaN displacements in an explicit step with circular-section beams.** ccx 2.23 sizes a
  `CIRC` beam's stable increment as if its section were the box around the circle and runs
  it at about 1.3× the limit. The converter caps every automatic `*DYNAMIC, EXPLICIT`
  increment for such beams (the data line's 4th field; up to twice as many increments as
  ccx alone would take) and warns about a fixed `DIRECT` increment above that cap — lower
  it or drop `DIRECT`. Editing the deck by hand, keep the maximum increment at or below
  0.12·d/c (d the section diameter, c the material's dilatational wave speed).
* **NaN or Inf in the results after "Job finished".** ccx 2.23 ends a solution that has
  diverged with "Job finished" and exit code 0 like any other, so check the results, not
  just the log: `abq2ccx --run` exits 1 and names the first NaN/Inf value in the `.dat`
  print blocks or the `.frd` (file, block, time, row), which tells you when it went
  wrong. In an explicit step it is an increment above the stable limit — set a smaller
  maximum increment in the 4th field of the `*DYNAMIC` data line — or a load the model
  cannot follow: check the converter's `[WARNING]`s for a load or BC it had to drop or
  reinterpret.
* **`*TEMPERATURE` is not a thermal BC.** In a heat-transfer step, a *prescribed*
  temperature is `*BOUNDARY` on DOF 11; `*TEMPERATURE` only supplies the field that
  drives thermal expansion in a mechanical run (in a heat transfer or coupled step the
  converter comments it out). Watch K vs °C too: without initial temperatures every node
  starts at 0, in Abaqus and in the converted deck.
* **Contact differs.** CalculiX contact is penalty-based (node-to-face / face-to-face);
  default stiffness differs from Abaqus and there is no "no separation" behaviour. The
  converter passes `*CONTACT PAIR`/`*SURFACE INTERACTION` through but does not retune
  them — review the contact setup.
* **Units are unenforced.** CalculiX is unitless; a mixed unit system (E in MPa, a film
  coefficient in SI) silently corrupts results. Keep one coherent system.
* **`*NLGEOM` total vs updated Lagrangian.** Even with `NLGEOM` on, ccx uses a total
  Lagrangian formulation and Lagrange strain, where Abaqus uses updated Lagrangian and
  logarithmic strain — expect small numerical differences and convert thermal-expansion
  coefficients if needed.

## Things that need manual remodelling

The converter flags these and preserves the original as `**` comments; there is no
automatic equivalent:

* **Connectors with a behaviour, fasteners, joints** → rebuild with `*RIGID BODY`,
  `*MPC`, `*SPRING`, `*DASHPOT` per the connector behaviour. (A connector *without* a
  behaviour — `JOIN`, `HINGE`, `REVOLUTE`, `ALIGN`, `WELD`, `BEAM`, `LINK` — is converted
  to its constraint; one under `NLGEOM` whose linear form is not exact there, e.g. a hinge
  between two moving bodies, is commented out — `--approximate` writes it linear.)
* **Gaskets** → approximate with a thin soft solid or a `*SPRING`.
* **Cohesive elements / debonding** → model with contact (`*SURFACE BEHAVIOR`) or a
  nonlinear `*SPRING`.
* **Rigid elements (`R3D*`/`RB*`)** → `*RIGID BODY` (NSET + ref node, plus a rot node
  for rotational DOFs).
* **Inertia relief** → a soft spring-to-ground / 3-2-1 constraint, or an equilibrating
  load.
* **Advanced materials** (`*VISCOELASTIC`, `*CONCRETE *`, `*DAMAGE *`, …) → substitute
  the nearest supported model or drop.

## Reporting a conversion problem

If a deck converts wrong, the most useful things to capture are: the input keyword
block, the emitted output, and the relevant `[WARNING]`/`[NOTE]` lines from the report.
`conv.geom` (when used as a module) lets you inspect the parsed model directly.
