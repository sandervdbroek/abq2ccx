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

* The converter **pre-flight-warns** about this ("Possible overconstraint: node N
  DOF d …"). Fix by removing either the BC or the constraint on that DOF.
* For 2-D/plane models, keep DOF 3 out of couplings.
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
* The element type has no CalculiX equivalent (cohesive/gasket/connector/rigid). The
  report flags these; they must be remodelled (see below).

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

### "Job killed without any error"

Usually out of memory. Big models need a lot of RAM (rule of thumb from the forum:
~32 GB for ~1M equations). Reduce the model or add memory.

## It runs but the results look wrong

These are the silent ones — no error, wrong physics.

* **Geometric nonlinearity (`NLGEOM`) is off by default in ccx.** Abaqus/Standard is
  the same, so a converted static step keeps its meaning. Abaqus/Explicit defaults to
  `NLGEOM=ON`; the converter therefore adds `NLGEOM` (and a large `INC`) to every
  `*DYNAMIC, EXPLICIT` step.
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
* **A heated part shrinks, or a model with temperatures is far too soft.** In linear steps
  of a deck with temperatures (an initial temperature field), ccx 2.23 silently uses a
  wrong stiffness — for thermal and mechanical loads and for frequencies alike — when a
  material's `*EXPANSION` is more anisotropic than its `*ELASTIC`: an isotropic `*ELASTIC`
  beside `TYPE=ORTHO` or `ANISO`, or an orthotropic / engineering-constants one beside
  `TYPE=ANISO` without an `*ORIENTATION`. The converter writes such an `*ELASTIC` as
  `ENGINEERING CONSTANTS` or `ANISO` with the same stiffness, adding temperature rows when
  E and ν both vary with temperature (the report has a NOTE per material); keep that form
  if you edit the converted deck. Under `NLGEOM`, an orthotropic or anisotropic expansion
  turned by an `*ORIENTATION` is wrong in ccx 2.23 with any elastic type (the turned shear
  part is lost, or the step does not converge), which no rewrite fixes — check one
  element's thermal strain against a hand calculation there.
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
* **`*TEMPERATURE` is not a thermal BC.** In a heat-transfer step, a *prescribed*
  temperature is `*BOUNDARY` on DOF 11; `*TEMPERATURE` only supplies the field that
  drives thermal expansion in a mechanical run. Watch K vs °C too.
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

* **Connectors / fasteners / joints** → rebuild with `*RIGID BODY`, `*MPC`, `*SPRING`,
  `*DASHPOT` per the connector behaviour.
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
