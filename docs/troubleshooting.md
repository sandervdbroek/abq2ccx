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

### "Job killed without any error"

Usually out of memory. Big models need a lot of RAM (rule of thumb from the forum:
~32 GB for ~1M equations). Reduce the model or add memory.

## It runs but the results look wrong

These are the silent ones — no error, wrong physics.

* **Geometric nonlinearity (`NLGEOM`) is off by default in a ccx `*STATIC`.** If your
  Abaqus deck relied on Abaqus/Explicit's default (which is `NLGEOM=ON`), add `NLGEOM`
  to the `*STEP`. The converter keeps `NLGEOM` when it's explicit in the source but
  cannot infer the Explicit default.
* **Linear perturbation vs general static.** A perturbation `*STATIC` uses the
  base-state stiffness in Abaqus; the converter maps it to a linear ccx `*STATIC`.
  Correct for small-strain elastic perturbations — verify if the base state was
  nonlinear.
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
