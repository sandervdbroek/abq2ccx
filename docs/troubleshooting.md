# Troubleshooting

A clean conversion is half the job: the deck still has to run in CalculiX and give the right
answer. These are the problems people actually hit (from the
[CalculiX Discourse](https://calculix.discourse.group/), the
[PrePoMax forum](https://prepomax.discourse.group/), the manual and the test corpus), with
causes and fixes. [Compatibility](compatibility.md) has the evidence behind each.

## CalculiX stops with an error

**`*ERROR in cascade: … detected on the dependent side of a MPC and a SPC`** (or "… of two
different MPC's"). A DOF is eliminated by an `*EQUATION`, `*MPC`, tie or rigid coupling and
also has a `*BOUNDARY`; ccx cannot have both, Abaqus resolves it itself. The converter
resolves what it can exactly — it reorders equation terms, drops redundant equations, takes
off member BCs that a rigid body's reference node already imposes, and moves identical BCs
on `*RIGID BODY` nodes to the reference node — and warns about the rest ("Possible
overconstraint: node N DOF d …"). The warning says what Abaqus does there and whether
`--approximate` does the same; otherwise remove the BC or the constraint on that DOF. A
closed loop of ties doesn't stop ccx — it holds the loop at zero — so the converter drops the
closing equation.

**`*ERROR in gen3dmpc: nodes belonging to shell elements must not be subject to a RIGID
MPC`.** ccx 2.23 rejects rigid constraints on shell, membrane, beam and truss nodes. The
converter attaches *knot beams* to such nodes; you see this error only in a deck written by
hand, or in explicit dynamics, where ccx cannot run rigid constraints on these nodes at all.

**`*ERROR reading *ELSET`, or "set used before it was created".** ccx is order-dependent,
Abaqus is not. The converter writes geometry, sets, sections and steps in that order, so this
means the output was hand-edited.

**`*ERROR … nonpositive jacobian`.** Distorted or inverted elements, or second-order
elements whose midside nodes collide after ccx expands shells and beams to solids. Remesh or
use a linear element. (Node ordering is not the cause: it is the same in both codes.)

**`*ERROR … no material defined`, or an element type rejected.** A section names a material
the converter commented out (see the report), or an element has no ccx counterpart
(cohesive, gasket, a `ROTARYI` that is not on a rigid body) and needs remodelling. Rigid
elements become skins of their rigid body, except those of an Abaqus/Explicit `*RIGID BODY`
with `DENSITY` and a thickness, whose mass the conversion would lose: `--approximate`
converts them without it. Surface elements reach ccx only when they carry rebar or mass
that acts; `--approximate` leaves them out anyway.

**`*ERROR reading *COMPLEX FREQUENCY: either parameter CORIOLIS or parameter FLUTTER is
required`.** ccx's complex eigenvalue step covers only Coriolis forces and flutter; Abaqus'
damped one (dashpots, damping) has no ccx counterpart. Use `*MODAL DYNAMIC` or `*STEADY
STATE DYNAMICS` with the damping instead.

**Composite shell errors.** `*SHELL SECTION, COMPOSITE` works only on `S6` and `S8R`; a
layup on `S4`/`S4R`/`S3` must be re-meshed with quadratic shells.

**`*ERROR reading *ORIENTATION: distribution … has not been defined`, or `matrix found to be
singular`, with per-element orientations.** In a hand-written deck: a second `*ORIENTATION`
naming the same distribution, or a distribution named like a number (`D1`, `12`) — ccx
zeroes that orientation. The converter avoids both. If it commented an orientation out
because its `INPUT=` file is missing, copy the file next to the deck and convert again.

**`*ERROR reading *TEMPERATURE: … no thermal *INITIAL CONDITIONS are given`, or `no initial
temperature defined in node N`.** ccx reads `*TEMPERATURE` only after thermal initial
conditions on every node. The converter adds 0, Abaqus' default, so thermal strains count
from 0 in both codes — a deck with absolute temperatures expands from 0, not from room
temperature. It does not do so for `*TEMPERATURE, FILE=`: ccx reads `FILE=` as a CalculiX
`.frd`, and without one prints `ERROR in readfrd` and runs on undefined temperatures. In a
heat-transfer or coupled step, prescribe temperatures with `*BOUNDARY` on DOF 11; the
converter comments `*TEMPERATURE` out there.

**"Job killed" without an error.** Usually out of memory (forum rule of thumb: ~32 GB for
~1 M equations).

## It runs, but the results look wrong

* **The report ends with "Reduced physics — ccx solves a different model than this Abaqus
  deck: …".** The conversion dropped or replaced something ccx has no counterpart for: a
  constitutive behaviour (concrete damaged plasticity, user hardening, Chaboche
  back-stresses, field-dependent properties), an element formulation (hybrid, modified or
  thin-shell elements run as ccx's plain ones; `CPS4I`/`CPE4I` outside small-strain linear
  elasticity), a section control, an interaction (general contact), a load or the geometry
  (an imperfection). ccx runs, but not the deck's own problem; the warnings above say what is
  missing and how to remodel it. The list is `Converter.reduced_physics` in the API.
* **A step solves to zero.** The report says "Step N is loaded in the Abaqus deck …, but no
  load survives the conversion": its loads were all commented out — a user-subroutine load,
  an NLGEOM follower traction (`--approximate` applies it as fixed forces), a load on an
  undefined surface, or a traction on nodes with unusable `*TRANSFORM` axes.
* **NaN or Inf after "Job finished".** ccx 2.23 ends a diverged solution like a good one.
  `abq2ccx --run` reads the results and names the first NaN/Inf value (file, block, time,
  row). In explicit dynamics, lower the maximum increment (4th field of the `*DYNAMIC` data
  line); otherwise look for a load or BC the converter had to drop or reinterpret.
* **A material lost its plasticity.** ccx runs tabulated isotropic, kinematic and combined
  hardening and Johnson-Cook, and silently skips other `*PLASTIC` forms. The converter
  comments `HARDENING=USER` and Chaboche `PARAMETERS` out (the report says the material now
  runs elastic, as reduced physics) and adds the `*RATE DEPENDENT` card Johnson-Cook needs.
  A tabulated curve is no stand-in for Chaboche: ccx's isotropic table has no Bauschinger
  effect, and its kinematic table does not follow the curve.
* **A heated part shrinks, or a model with temperatures is far too soft.** ccx 2.23 uses a
  wrong stiffness in linear steps when the `*ELASTIC` is less anisotropic than the
  `*EXPANSION`; the converter rewrites the `*ELASTIC` with the same stiffness (a NOTE per
  material). Keep that form if you edit the deck. The converted ANISO expansion has half the
  shear coefficients on purpose: Abaqus' are engineering strains, ccx's tensor components.
* **Under NLGEOM, turned orthotropic thermal strains lose their shear, or an anisotropic
  expansion stops with "too many cutbacks".** A ccx 2.23 bug; the converter warns, naming
  the materials. Check one element's thermal strain by hand, or keep the thermal load out of
  NLGEOM steps.
* **Field-variable dependence is gone.** ccx ignores `DEPENDENCIES=`; the converter keeps
  the Abaqus no-field state (field = 0): exact (a note) when the deck sets no field variable
  and the table gives that state, reduced physics (warned) otherwise.
* **A rigid body ignores rotations at its reference point.** ccx carries a `*RIGID BODY`'s
  rotation on a separate `ROT NODE`; the converter adds one and moves the reference point's
  rotational BCs and moments to it. Read reaction moments there.
* **A rigid body's reaction force is zero.** ccx 2.23 reports no reaction at a `*RIGID BODY`
  reference node that is one of the body's own nodes, although the body is loaded and the
  rest of the model is right. Read the reaction at the supports, or give the body a reference
  node of its own.
* **Rotational BCs, moments or an `*EQUATION` on a `*TRANSFORM`ed node are commented out.**
  ccx reads them in the local axes only on a shell/beam node that is no knot; elsewhere the
  converter writes them in global components where that is exact, and the warning names
  what is not (rotations held about non-global local axes on a knot, a shell in a
  `*DYNAMIC` deck, ...). Hold all three rotations, or give the support its own reference
  point with a kinematic coupling, whose rotation the converter carries in its local axes.
* **Short extra beams in the model (`ABQ2CCX_KNOT`).** Knot beams carry no load; ignore
  them in the results.
* **Thin extra solids on rigid tools (`ABQ2CCX_RIGID`).** ccx has no rigid element and no
  analytical surface, so each rigid facet becomes a force-free solid *skin* that its rigid
  body moves; the skin's face on the facet is the contact face. Skins never strain: ignore
  them in the results. Their material comes after the deck's on purpose — ccx takes the
  default `HARD` contact stiffness from the first material.
* **An analytical rigid surface was "not converted".** Curved profiles, surfaces of
  revolution and fillets would only be facets, so without `--approximate` the surface, its
  rigid body and its contact pairs and ties are commented out. With it, the `[APPROX]`
  warning gives the facets' chord angle and sag.
* **A `*TIE` to a rigid surface is gone.** Its slave nodes became members of the rigid body:
  ccx's tie would follow an NLGEOM rotation only linearly and stops explicit dynamics.
* **Rotary inertia became point masses (`ABQ2CCX_STAR*`).** ccx 2.23 has no `ROTARYI`; a
  rigid body's inertia comes from six point masses on its principal axes and a negative
  `*MASS` that keeps the body's mass and centre of mass.
* **Axisymmetric reactions are 180 times too small.** ccx prints them per 2° sector;
  multiply by 180 for Abaqus' whole-circumference value.
* **An explicit run of a plane or axisymmetric model bounces off a rigid tool.** ccx 2.23
  leaves that contact out of its stable increment; the converter caps the step's maximum
  increment (a NOTE gives the value). Keep a hand-set maximum or `DIRECT` increment below it.
* **Velocity and acceleration BCs.** ccx prescribes displacements only, so they become
  displacement BCs with generated amplitudes (`ABQ2CCX_VEL*`/`ACC*`). Edit the Abaqus BC and
  reconvert rather than the amplitudes. After a velocity jump, the driven node's own velocity
  output oscillates for a while; the motion is unaffected.
* **A Riks step does not run.** ccx has no arc-length method and would run it as plain
  static, so the converter comments it out; `--approximate` accepts the plain static step.
* **Linear perturbation steps.** A perturbation `*STATIC` becomes a general linear step in
  ccx: right for small elastic perturbations, and its loads persist into later steps (warned).
* **Results at beam and shell nodes are missing from the `.frd`.** ccx writes a model with
  beams or shells expanded to 3-D, under new node numbers. The converter sends history output
  to the `.dat`, prints the node sets the `.frd` cannot show, and adds `OUTPUT=2D` only when
  the `.frd` gets nothing but U, V and RF (`OUTPUT=2D` averages stresses through the
  thickness).
* **Output comes at one frequency per step.** ccx has a single output control per step for
  all `.frd` and `.dat` output; the converter puts `*OUTPUT`'s frequency on the step's first
  output card, so history output may come coarser or finer than in Abaqus. Where an explicit
  step's elements cannot be sized (user materials), ccx writes every increment (warned): set
  `FREQUENCY=N` on that card yourself.
* **ccx aborts right after writing contact output** (SIGABRT, no message). ccx 2.23 does
  that with axisymmetric elements whose `.frd` also gets `S`, unless every contact pair is
  face-to-face; the converter drops such a request with a warning.
* **NaN in an explicit step with circular-section beams.** ccx 2.23 overestimates their
  stable increment; the converter caps it. Keep a hand-set maximum increment below
  0.12·d/c (d the section diameter, c the wave speed).
* **Contact behaves differently.** ccx contact is penalty-based (node-to-surface or
  face-to-face), with different default stiffness and no "no separation". A pair without
  `TYPE` gets Abaqus' default, node-to-surface; some decks converge only face-to-face.
* **A part flies away, or contact never closes, in a static step.** ccx has no contact
  stabilization: a part that only contact holds (its reference point driven in one direction,
  say) has no stiffness in its free directions until the contact closes, and ccx's solution
  drifts there. Hold those directions where the model allows it (a BC on the reference point).
* **`C3D8R` hourglassing.** Prefer `C3D8I` or `C3D20R` for bending; ccx has no artificial
  energy output, so check a scaled deformed shape.
* **Units are not enforced.** A mixed unit system silently corrupts results.
* **NLGEOM formulations differ.** ccx uses total Lagrangian with Lagrange strain, Abaqus
  updated Lagrangian with logarithmic strain: expect small differences at large strain.

## Things that need remodelling

The converter keeps these as `**` comments with guidance:

* **Connectors with a behaviour**, fasteners and joints → `*RIGID BODY`, `*MPC`, `*SPRING`,
  `*DASHPOT`. (Connectors without a behaviour are converted.)
* **Gaskets** → a thin soft solid or a `*SPRING`; **cohesive elements and debonding** →
  contact or a nonlinear `*SPRING` (by default they run as a bonded thin continuum, warned).
* **Abaqus general contact** (`*CONTACT`) → `*CONTACT PAIR`s between the surfaces that can
  touch (rigid elements and analytical surfaces convert, so they can be part of them).
* **Inertia relief** → soft springs to ground or a 3-2-1 constraint.
* **Unsupported materials** (`*VISCOELASTIC`, `*CONCRETE …`, `*DAMAGE EVOLUTION`, …) → the
  nearest supported model.
* **User subroutines** → port them to ccx's (`umat.f`, `dload.f`, `uboun.f`, …), as the
  warning names.

## Reporting a conversion problem

Include the input keyword block, the converted output, and the relevant `[WARNING]` and
`[NOTE]` lines. `abq2ccx.convert_file(path).geometry` gives the parsed model for your own
checks.
