# Changelog

Corpus counts are on the CalculiX version current at the time; from October 2026 on, "solve"
counts only decks that solve their own problem: under their own loads, without reduced
physics.

## Unreleased

* **Preloads in `*FREQUENCY` steps** — Abaqus includes a preload's stress stiffness in a
  frequency step only when the base state has NLGEOM; ccx 2.23 includes the base state only
  with `*STEP, PERTURBATION`, whatever the NLGEOM. A `*FREQUENCY` step after an NLGEOM general
  step now gets `PERTURBATION` (a column under gravity: 20.74 Hz, before 25.02 as if unloaded),
  and after general steps without NLGEOM loses it (25.02 Hz, before 20.74), unless contact,
  temperatures or base-state-dependent material need it there (warned as reduced physics).
  Where a modal or steady-state dynamics step reads the modes, which ccx refuses from a
  perturbation step, the prestress is left out (warned). Initial stresses before a first
  `*FREQUENCY` step drop its `PERTURBATION` (Abaqus leaves them out there); before a first
  `*BUCKLE` step, where ccx leaves them out and Abaqus does not, they are warned as reduced
  physics.
* **`*EL FILE` output that stopped or crashed ccx 2.23** — in a model with U1 beams, ccx stops
  writing `ENER` or `SDV` to the .frd ("only coded for fields with 6 entries"), even in a
  linear static step, so `*OUTPUT, FIELD, VARIABLE=ALL` never ran there. In a model with state
  variables (`*DEPVAR`, a plastic or creeping material), `SDV` segfaults ccx in a linear
  `*STATIC` or a `*STEADY STATE DYNAMICS` step, and in a `*FREQUENCY` or `*BUCKLE` step that
  ccx carried the request into from an earlier step. These labels are now dropped there, with
  a note (a warning for U1's `ENER`); `*EL PRINT` still writes them. A U1 model no longer gets
  `ENER` in its first step: it is linear, and ccx takes energy requests from any step there.
* **A step that solved nothing is no solve** — ccx 2.23 can run a step that sets up no system
  of equations to "Job finished" and exit 0, every free DOF left at its initial value (a
  `*DYNAMIC` step whose kinematic couplings chain no MPCs, which the converter avoids). The
  solve judge, `classify_ccx_run` (shared by `--run`, `validate_with_ccx.py` and the corpus
  tests), called that run solved. It now needs each step to show the structure of its matrix
  or its number of equations, and calls a run where one does not **unsolved**: `--run` names
  the step and exits 1. No corpus deck changes status.
* **Body forces after `*DLOAD, OP=NEW`** — ccx 2.23's `*DLOAD, OP=NEW` removes the earlier
  pressures and `GRAV` / `CENTRIF` loads but keeps `BX`, `BY` and `BZ`, which Abaqus removes. So
  they stayed on after a deck's own `OP=NEW`, after a linear perturbation step and in a
  `*MODAL DYNAMIC` step (a bar's tip after a step 2 under gravity: 4.5e-3 for -9e-3). The
  converter now writes zero lines for them after every `OP=NEW` ccx acts on, leaving out the
  elements the step loads itself (ccx stops on two amplitudes for one element).
* **`*BUCKLE` loaded by prescribed displacements** — ccx 2.23 does not solve a `*STEP,
  PERTURBATION` `*BUCKLE` step for prescribed displacements: only the prescribed nodes move,
  by every nonzero BC value in force, so the buckling factors were wrong (a column pushed down
  at its top: 2.389 for 40.87). Such a step now drops `PERTURBATION` when no general step
  precedes it (ccx's plain `*BUCKLE` solves the displacement); nonzero BCs held on from earlier
  steps, which are no load in an Abaqus perturbation step, are given again at 0 there; a step
  loaded by its own prescribed displacement after a general step is warned as reduced physics.
* **U1 beams beside a deformation-plasticity solid** — ccx 2.23 runs a model with a
  `*DEFORMATION PLASTICITY` material under NLGEOM, where its U1 beam stops ("no second order").
  Such a deck no longer gets U1 beams; its beam sections are handled as where U1 cannot run.
* **Notes on ccx 2.23 crashes and thermal expansion, made exact** — a card ccx rejects (step
  data outside a step, a section naming an undefined material) segfaults it only as the deck's
  last card with a data line; DOFs 4–6 and 8 on plane nodes crash only builds without the fix
  of CalculiX PR #200; a damage deletion stops SPOOLES once nodes are left without elements and
  crashes any solver on the last element.
  The NLGEOM expansion warnings no longer call linear steps right in ccx itself: they are right
  as converted, with the `*ELASTIC` rewrite, which `validate_with_ccx.py
  thermal_expansion_elastic_forms` now checks for every `*ELASTIC` form, turned and not.
* **`*DSLOAD` and `*DLOAD, OP=NEW` in one step** — ccx 2.23 has one `OP=NEW` flag for both
  cards and acts on it on a step's first one only, and the converter writes `*DSLOAD` as
  `*DLOAD`. So a step with a `*DSLOAD`, then a `*DLOAD, OP=NEW` (or the other way round), which
  is valid Abaqus, kept the earlier steps' loads that Abaqus removes (a block's gravity from
  step 1 stayed on in step 2). A bare `*DLOAD, OP=NEW` now opens such a step.
* **Implicit dynamics after a first step** — ccx 2.23 computes element energies from the first
  step that needs them on: every implicit `*DYNAMIC` and transient coupled
  temperature-displacement step, or an `ENER`, `ELSE`, `ELKE` or `CELS` request. In a nonlinear
  calculation it stops when that is not the first step ("energy output requests, if any, must
  be specified in the first step"), so a static, frequency or other first step followed by such
  a step never ran. The first step now requests `ENER` on its `*EL FILE` (on a card of its own
  where it has none), kept out of the steps after it: a cube preloaded in a static step and
  then let go in an implicit `*DYNAMIC` step swings from its static deflection as u0 cos ωt
  (3.4e-4 of u0 apart).
* **Rigid constraints in linear dynamic steps** — in a `*DYNAMIC` step ccx 2.23 turns the RIGID
  MPCs of `*RIGID BODY` and kinematic couplings with the finite rotation even without NLGEOM,
  where Abaqus linearizes them (a cantilever under a tip moment 9 % stiffer at 0.1 rad). In a
  deck with a `*DYNAMIC` step and no NLGEOM every `*RIGID BODY`, `*MPC BEAM` body and kinematic
  coupling, on solid, knotted shell/beam or 2-D nodes, is now written as the linear `*EQUATION`s
  u = u_ref + θ × d, one card per constraint (on a member with a `*TRANSFORM` along its local
  axes: 2.5e-6 off the linear answer, where the `*RIGID BODY` was 7 % off; knot beams only where
  rotations are tied). A transformed reference node keeps the `*RIGID BODY`, warned as reduced
  physics, as does a deck whose linear `*DYNAMIC` step comes before an NLGEOM step.
* **BCs on the nodes of those linear rigid constraints** — ccx solves with such a BC kept (it
  had a false "ccx stops" warning). A kinematic coupling's or `*MPC BEAM`'s is now dropped, as
  Abaqus does: it eliminates that DOF. A `*RIGID BODY`'s that cannot be moved to the reference
  node is warned as reduced physics. The notes no longer describe a `*RIGID BODY` that isn't
  written.
* **`*BOUNDARY, OP=NEW` as ccx reads it** — ccx 2.23 acts on `OP=NEW` on a step's first
  `*BOUNDARY` only; the converter's step walkers (load audit, results digest, velocity BCs,
  constraint and connector checks) took it on any card. An `OP=NEW` on a later card only,
  which Abaqus does not allow, is dropped and warned.
* **Loads in `*MODAL DYNAMIC` steps** — a modal dynamic step applies only its own loads, as
  Abaqus does in a linear perturbation step. ccx 2.23 applied the earlier steps' `*CLOAD` and
  `*DLOAD` (pressures, gravity, centrifugal loads) there too (a statically preloaded cube: 0.013
  off a response of 0.016). The step now opens with `*CLOAD` / `*DLOAD, OP=NEW` where earlier
  steps gave such loads, and its loads converted to nodal forces are written in full. A modal
  dynamic step that ccx starts from a deformed or moving model, which Abaqus does not carry
  into it, is flagged: after a loaded general step (whose loads then stay on, so a static
  deflection stays in its results as an offset) or a moving modal dynamic step without
  `CONTINUE=YES`.
* **`*BUCKLE` steps that ccx 2.23 aborted or stopped on** — ccx 2.23 aborts (SIGABRT, the `.dat`
  sometimes empty) at the end of a step that holds no body load once an earlier step held one:
  a `*BUCKLE` step after a gravity or centrifugal preload, or any step after a `*STEP,
  PERTURBATION` `*BUCKLE` under its own weight. Such a step now gets a zero `GRAV` line, which
  loads nothing (a column's factor under a gravity preload: the same as with the preload as
  nodal forces). A plain `*STEP` + `*BUCKLE` after a general step gets `PERTURBATION`: Abaqus
  always buckles about the preloaded base state, ccx without it buckled the unloaded structure
  (the column: 10.81 for 6.11). `*TEMPERATURE` in a `*BUCKLE` step, which ccx refuses
  ("temperature loading is not allowed in a linear buckling step") and Abaqus scales with the
  factor, is commented out as reduced physics.

## 1.3.0 (October 2026)

Material directions as Abaqus defines them on shells, membranes and continuum shells (composite
plies, stack directions and spherical systems included); ccx's own membranes and quadratic beams
written so that ccx 2.23 solves them right; initial stresses and deformation plasticity on
oriented sections; general steps after perturbation steps; and the fixes and cleanups of a
whole-file code review. Corpus on ccx 2.23: 232 decks gated, 189 solving their own physics.

* **General steps after linear perturbation steps** — a step that follows a `*FREQUENCY`,
  `*BUCKLE`, modal or steady-state dynamics or `*STEP, PERTURBATION` step starts from the last
  general step's state, as in Abaqus. ccx 2.23 carried the perturbation step's loads and BC
  changes on, zeroed prescribed BC values after `*FREQUENCY` and dropped earlier loads and
  temperatures after `*BUCKLE` (cubes' next static step: 0.49 off), and forgot NLGEOM. Those
  loads, BCs and temperatures are now given again at the step's start, without the loads it
  gives itself, on a constant amplitude `ABQ2CCX_HOLD` (`*BOUNDARY, OP=NEW` where the
  perturbation step held a free DOF), and NLGEOM is written again. A `*DYNAMIC` step after
  `*BUCKLE` or `*MODAL DYNAMIC`, which ccx starts from that step's displacements, is flagged.
  A `*BUCKLE` step's loads converted to nodal forces are written in full, as ccx drops the
  earlier ones there (one repeating the static step's traction buckled under no load).
* **Deformation plasticity in small-strain steps** — ccx 2.23 runs `*DEFORMATION PLASTICITY`
  under NLGEOM, in the logarithmic strain and the Cauchy stress, where Abaqus takes the small
  strain without NLGEOM: such steps are now flagged as reduced physics (a bar in tension strains
  0.39 % more at σ0, 12 % at 2σ0). An explicit `NLGEOM=NO`, with which ccx reads the small
  strain as a Green-Lagrange one (32 % at 2σ0), is dropped, so both spellings run the same
  law, and a material of the law that nothing uses is commented out (ccx ran the whole model
  under NLGEOM for it).
* **Initial conditions on continuum shells** — `*INITIAL CONDITIONS, TYPE=STRESS / PLASTIC
  STRAIN` on `SC8R` / `SC6R` are read as Abaqus' components for them, 11, 22, 12 (the third was
  taken as S33), in the shell's material directions, which apply also without an orientation (3
  the stack direction; a composite ply's turned by its angle), and turned into the global axes
  ccx 2.23 reads on its `C3D8I` / `C3D6` (a free plate off the x-y plane relaxed 55 % off
  before, `[0/90/0]` plies up to 13×). A split element's label reaches all its ply solids, as
  its element sets did. Left out as reduced physics: a `*SHELL GENERAL SECTION`'s values, which
  are section forces, rebar records, which ccx stopped on, and section point records, which it
  read with the point number as a stress.
* **Code-review fixes** — a planar `B21`/`T2D2` model with a `*COUPLING`, `*TIE` or tied
  `*CONTACT PAIR` no longer stops the converter; a `TYPE=VELOCITY` card a rigid constraint
  implies whole is left out (it came back, and ccx stopped); amplitude points are written to
  12 digits (6 merged times 1e-4 apart at t = 100); a `SYMMETRIC` layup counts its mirrored
  plies in rigid ties, ccx's knot test and the explicit increment (a tie left to ccx: 3.3×
  too soft); `*FRICTION` reads `3.D-1`; `--approximate`'s Poisson clamp keeps blank fields; a
  moment on DOF `+6` of a transformed beam node is DOF 6; `*RIGID BODY, REFNODE=` keeps a plane
  body's holds; a part's `*DISTRIBUTING COUPLING` and `*PRE-TENSION SECTION` are copied per
  instance (ccx stopped on the part's names), also from inside an `*INSTANCE`, where another
  card the flattener cannot place is now warned; circular-section beam knots no longer depend
  on the order of a step's `OP=NEW` cards; an `*ORIENTATION, DEFINITION=NODES` with an
  undefined node no longer takes the next nodes as its points.
* **More code-review fixes** — blank-free spellings of every keyword the converter knows by name
  (`*ROTARYINERTIA`, `*SECTIONCONTROLS`, `*ENERGYPRINT`, ...) reach their handlers; a
  mesh-generation record with a non-numeric field (an undefined `<parameter>`) is skipped with a
  warning instead of failing the conversion, and `*NCOPY, MULTIPLE` copies in linear time;
  `*STEP, NLGEO` is read as `NLGEOM`; `*ELASTIC, TYPE=LAMINA` collapses `DEPENDENCIES` rows like
  the other types and reads a blank field as 0; a tied pair's `NO THICKNESS` holds on a rigid
  master too; a connector or rotary inertia whose orientation has no fixed axes (a
  distribution's) is refused instead of taking the global axes; a blank `*KINEMATIC COUPLING`
  line no longer stops explicit decks. Now reported: unreadable `*PLASTIC` dependency rows,
  `*PARAMETER` expressions that cannot be evaluated, a prescribed value only ccx loses after a
  frequency step's `OP=NEW`, and constraints on rotations of transformed nodes that are
  commented out (reduced physics; `SCALE STRESS=1.00` no longer is). Converted decks mark all
  the converter's comments `** abq2ccx:`.
* **Kinematic couplings in dynamic steps** — ccx 2.23 solves no `*DYNAMIC` step (implicit or
  explicit) of a model whose `*COUPLING` + `*KINEMATIC` chain no MPCs: it sets up no equations,
  and every free DOF kept its initial value, with no message. In a deck with a `*DYNAMIC` step
  a coupling of solid or free nodes is now the linear `*EQUATION`s Abaqus solves without NLGEOM,
  or a `*RIGID BODY` under NLGEOM; under NLGEOM one of only some translations is commented out
  (`--approximate`: the linear equations). `davidmorinntnu_example_vuhard_v1` / `_v2` had run
  with their specimens' lateral DOFs frozen; their DOF-2 couplings are now commented out, which
  leaves the specimens without load, so the corpus no longer gates them (232 `expect_solve`).
* **Pre-tension nodes named by a set** — `*PRE-TENSION SECTION, NODE=` (and a truss or beam
  cut's `ELEMENT=`) naming a set of one node (element), as Abaqus allows, is written with its
  number: ccx 2.23 reads only a number there and stopped on the set name. Instance-qualified
  names at the assembly level resolve too; a set of several members or none is warned and left
  for ccx to stop on, as Abaqus would.
* **Initial stresses and deformation plasticity on oriented sections** — `*INITIAL CONDITIONS,
  TYPE=STRESS / PLASTIC STRAIN` are turned out of the orientation's axes, in which Abaqus gives
  them, into the global ones ccx 2.23 reads them in — at each of ccx's integration points on a
  cylindrical or spherical system (a free cube on a turned system relaxed 158 % off before).
  Records ccx misread get its form too: a plane-stress element's S12 (read as szz) and a
  plastic strain's engineering shear (ccx reads tensor components). The sections and plies of a
  `*DEFORMATION PLASTICITY` material are written without their orientation: the law is
  isotropic, but ccx's results depended on the axes (CalculiX issue #160: a `C3D20R` bar 84 %
  off, a hang on zero axes).
* **Orientations isotropic sections read** — a spherical `*ORIENTATION` and a cylindrical one's
  rotation line, which ccx 2.23 lacks, are no longer reduced physics where every section that
  reads them is isotropic or gets Abaqus' directions per element: ccx's results do not depend on
  the axes there (probed). A spherical one is then written as the global axes: on its
  rectangular stand-in, without axes for a sphere centred at the origin, ccx printed NaN element
  stresses, and hung with `*DEFORMATION PLASTICITY`.
* **Shell and membrane pressure on the reference surface** — Abaqus applies it to the reference
  surface, ccx 2.23 to one face of the solid it expands the element into: on a shell the
  bottom face for every label, whose area is off by O(t/R) (a sphere's force 10 % low at
  t/R 0.1), leaving a mean stress −p/2 through the thickness (an `M3D4` sphere's displacement 5 % high).
  Each such pressure is now split between the two faces (0.5 − o and 0.5 + o for `OFFSET`
  o): the force matches Abaqus to O((t/R)²) — 0.25 % at t/R 0.1 on a sphere, exact on a
  cylinder — also under NLGEOM.
* **Membrane ties and couplings** — a `*TIE` or tied `*CONTACT PAIR` slave surface and a
  kinematic coupling's surface on ccx's own membranes (`M3D3`, `M3D4`, `M3D4R`) now take the
  membrane nodes, as Abaqus does: ccx tied an `SNEG` face not at all and an `SPOS` face
  5.9 % too stiff (a skin on a block), and coupled such faces 1.2 % off or crashed, as it did
  on shell faces, which couplings now also take by their nodes. Such a tie gets Abaqus'
  position tolerance written out, ccx's own default being some 20 times smaller (quadratic
  membranes' ties without a tolerance stayed open), and a `*TIE` with several lines becomes
  one per line (ccx read only the first). `*MEMBRANE SECTION, DENSITY=`, a mass per area,
  goes into a copy of the material (frequencies were 5.4 times too high in a test);
  `POISSON`, which ccx ignores, is warned about where it changes the `NLGEOM` thickness.
* **Quadratic membranes** — ccx 2.23 leaves the mid-thickness node of a quadratic membrane's
  corners free in each element it expands (`M3D8R` singular in any mesh of two or more
  elements, `M3D6` several times too soft, `M3D8` too soft in thick elements). `M3D6`,
  `M3D8` and `M3D8R` are now written as the solids ccx would make, on nodes held at the
  membrane nodes by `*EQUATION`; `M3D9` / `M3D9R`, which ccx does not have, the same
  without their centre node (reduced physics). Strips in tension now give the exact answer,
  a pressurised sphere thin-wall theory within 0.85 %.
* **Quadratic beams** — every 3-node beam (Abaqus' `B22`, `B32`, `PIPE22`, `PIPE32`, and the
  2-node beams that circular, pipe and box sections need upgraded) runs as ccx's `B32R`,
  integrated at 2 points along the beam as Abaqus integrates its quadratic beams, instead of
  `B32` (3 points), which locks on coarse meshes: NAFEMS NL6 on its own 8 elements now gives
  Abaqus' answer (was 10 % off), FV2's frequencies come within 2.7 % of it (were 22 % off).
  A note covers `B32R`'s 50 `*EL PRINT` rows per `RECT`/`CIRC` element (the `--run` digest
  reads the 8 real ones) and its convergence on coarse members in 3-D `NLGEOM` steps.
  Published answers: 20 of 26 match Abaqus, 6 differ for a reason traced to ccx.
* **Shell and membrane material directions** — oriented `*SHELL SECTION`, `*SHELL GENERAL
  SECTION` and `*MEMBRANE SECTION` sections (composites and `*DISTRIBUTION`s included) get
  Abaqus' material directions per element group wherever ccx 2.23 places them otherwise: ccx
  projects the orientation's axis 1 onto a shell (axis 3 where axis 1 is the normal), uses a
  membrane's 3-D axes unprojected, and takes a cylindrical system once per element. A
  pressurised orthotropic cylinder with a cylindrical orientation came out 14 times too soft;
  it now matches thin-wall theory to 0.35 %.
* **Default rotation axis** — an `*ORIENTATION` without a rotation line turns about its axis 1
  on shells and membranes, as Abaqus documents, so material direction 1 follows axis 2 (it
  followed the axis closest to the normal); warned where axis 1 lies in the shell.
* **Continuum-shell material axes** — plain shell sections on continuum shells (`SC8R`,
  `SC6R`) get Abaqus' material axes (the stack direction as axis 3, the orientation projected
  onto the mid-surface), where ccx 2.23 would use the orientation's axes unprojected: an
  `SC8R` hoop-wound cylinder came out 14 times too soft and now matches thin-wall theory to
  0.10 %.
* **Stack direction** — `STACK DIRECTION=ORIENTATION` stacks continuum shells along the
  orientation's rotation axis (axis 1 without a rotation line: radial for a cylindrical or
  spherical system), as Abaqus does; it stacked along axis 3. `STACK DIR` is read as `STACK
  DIRECTION`.
* **Spherical orientations** — shell, membrane and continuum-shell sections (plies included) on
  a `SYSTEM=SPHERICAL` `*ORIENTATION` get Abaqus' spherical material directions per element
  (1 radial, 2 along the parallels, 3 along the meridians); ccx 2.23 has no spherical system
  and read the rectangular card the converter writes instead (no axes at all for a sphere
  centred at the origin). Where only such sections read the card, it is no longer reduced
  physics. A pressurised orthotropic sphere now matches membrane theory to 0.35–1.2 %. A
  cylindrical or spherical system turning within an element is no longer reported for
  elements Abaqus integrates at their centre alone (`S3`, `S4R`, `M3D3`, `M3D4R` ...), as ccx
  takes the orientation there too.
* **CalculiX on Windows** — CI now runs `validate_with_ccx.py` and `--run` with conda-forge's
  Windows ccx 2.23 as well. That ccx does not start outside its activated environment, so
  `--run` and `validate_with_ccx.py` give a conda environment's ccx the folders `conda
  activate` puts on `PATH`; and a ccx that Windows cannot start is reported as such ("exit
  code 0xC0000135 (a DLL that ccx needs is missing)", not 3221225781).
* **Node-defined orientations in instanced parts** — a part's `*ORIENTATION, DEFINITION=NODES`
  now names each instance's own nodes (every copy named the first instance's, or other nodes
  behind an assembly-level reference point); without node c a moved instance gets the part's
  axes turned with it.

## 1.2.1 (October 2026)

* **The output file as the second argument** — `abq2ccx deck.inp out.inp` converts into
  `out.inp` (and `out.log`) when `out.inp` is new or abq2ccx wrote it, so a rerun overwrites
  it; two existing Abaqus decks still convert as a batch, so this form never overwrites a deck
  abq2ccx did not write. `-o` works as before.

## 1.2.0 (October 2026) — CalculiX 2.23

FreeCAD 1.1.4 moved to ccx 2.23, which is stricter than 2.22 and gets some valid input wrong
without an error. A full audit and the work that followed:

* **Solve judge** — one judge (`classify_ccx_run`) for `--run`, `validate_with_ccx.py` and
  the corpus: a clean exit, no crash message, a real analysis step, and finite results
  (ccx ends a diverged solution with "Job finished"). Mesh-only decks are a separate
  `parse_only` class (issue #3).
* **Load audit** — a step the Abaqus deck loads must still be loaded after conversion;
  decks that load nothing are flagged `source_unloaded` and kept out of the headline.
* **Reduced physics** — whatever a conversion drops or replaces of the Abaqus model (a
  material behaviour, an element formulation, a section control, an interaction, a load, the
  geometry) is named in a closing "Reduced physics" warning (`Converter.reduced_physics`);
  such decks are flagged `reduced_physics` and kept out of the headline. Each "verify" hedge
  was settled with a ccx probe: `CPS4I`/`CPE4I` now run exactly as `C3D8I` slabs (they locked
  as `CPS4`), a shell pressure on the `SPOS` side pushes the right way, `*NODE, SYSTEM=C/S`
  coordinates and `*NODE` normals are converted, steady-state `IMAGINARY` loads become ccx's
  `LOAD CASE=2`, and exact cases (`S3R`, a bare `*KINEMATIC`, duplicated `*BUCKLE` load cases,
  turned instances) are notes. `--approximate` reframings count as reduced physics too.
* **Loads** — surface tractions, beam line loads and surface-element loads as consistent
  nodal forces, in the local axes of `*TRANSFORM`ed nodes; user-subroutine loads and BCs
  commented out, naming the ccx subroutine; velocity and acceleration BCs integrated into
  displacement BCs, with Abaqus' default amplitudes; blank `*DLOAD` and `*DSLOAD` fields
  kept in place as zeros (dropped, they moved the fields after them: `GRAV` pulled along the
  wrong axis, a `CENTRIF` axis came out wrong or of length zero).
* **Default amplitudes** — displacement BCs without an amplitude follow Abaqus where its
  default departs from ccx's: ramped from the previous value where ccx would step them
  (implicit dynamics, `*VISCO`, transient coupled steps), held where they are in explicit
  steps; `*STEP, AMPLITUDE` dropped on explicit steps.
* **Coupled temperature–displacement** — transient steps run without inertia, as in
  Abaqus/Standard (ccx 2.23 solves them as dynamic steps): masses divided by 10³⁰, specific
  heats and GRAV/CENTRIF magnitudes multiplied by it, which leaves heat capacity and body
  forces as they were; load jumps and BCs released at the start of such a step, which ccx's
  HHT scheme overshoots, are warned.
* **Beams** — circular, pipe and box sections upgraded to the quadratic beams ccx 2.23 runs;
  planar beams and trusses held in their plane; knot beams for rotational BCs on
  circular-section nodes and across `*BOUNDARY, OP=NEW`; a capped explicit increment for
  circular-section beams.
* **Constraints** — knot beams for rigid couplings on shell and beam nodes; `*MPC` converted
  line by line; `*EQUATION` overconstraints settled exactly; BCs on rigid-constraint members
  resolved as Abaqus does; connector elements without a behaviour as their constraints,
  also on transformed nodes; `*TRANSFORM` cases ccx gets wrong handled or warned.
* **One `*MPC` card per ccx MPC** — `PLANE` and `STRAIGHT` lines, and the `*MPC BEAM` of each
  `LINK` node pair under NLGEOM, each get a card of their own, as ccx reads one MPC per card:
  two `LINK` pairs in one card stopped ccx ("increase nk_"), and a second `PLANE` or
  `STRAIGHT` line's nodes were silently put on the first line's plane or line.
* **`*MPC` on transformed nodes** — `PIN`, `TIE` and `LINK` written in the local DOFs ccx reads
  on nodes with a `*TRANSFORM` (they constrain the global motion in Abaqus): a node's local
  terms only where no two share a global DOF, else through an untransformed twin node, as
  ccx 2.23 mis-assembles an equation that holds a DOF twice (this also fixes the connector
  `LINK` to a transformed node).
* **Rotations of `*TRANSFORM`ed nodes** — rotational BCs, moments and `*EQUATION` terms on
  DOFs 4–6 written as ccx reads them: a transformed kinematic reference node's coupling as
  a `*RIGID BODY` with a `ROT NODE` in its axes, knot beams and global components on beam
  nodes, equation terms moved to rigid bodies' `ROT NODE`s; what has no exact form
  commented out and warned.
* **Rigid tools** — rigid elements (`R3D3`, `R3D4`, `R2D2`, `RB2D2`, `RAX2`, `RB3D2`) as
  force-free solid skins of their rigid body, so contact against them works; analytical
  rigid surfaces meshed into skins (curved ones with `--approximate`); ties to rigid
  surfaces as body members; `ROTARYI` on rigid bodies as point masses; explicit increments
  capped where ccx leaves plane or axisymmetric contact with a rigid surface out of its
  estimate.
* **Materials and orientations** — per-element `*DISTRIBUTION` orientations; the elastic
  forms ccx 2.23 needs beside orthotropic and anisotropic expansion; halved ANISO expansion
  shear coefficients; zero-shear ANISO written as ORTHO; default initial temperatures.
* **Composite shells** — composite `S3`/`S4`/`S4R` shells run as `S6`/`S8R` with shared
  midside nodes (with the linear shells and beams joined to them by an edge); composite
  continuum shells (`SC8R`, `SC6R`) as one `C3D8I`/`C3D6` per ply, with their sets, faces,
  loads and BCs carried to the plies (`--max-ply-elements`); ply directions as Abaqus defines
  them on any shell plane, and every ply naming an orientation (ccx 2.23 gives a ply without
  one the previous ply's). Validated against classical lamination theory and Pagano's 3-D
  solution.
* **Output** — requests fitted to ccx's `.frd`/`.dat` model, one output control per step,
  explicit output intervals from ccx's stable increment, Abaqus' preselected field and
  contact output.
* **`--run` results digest** — after a clean run, a line or two per step to set beside the
  Abaqus results (largest |U| and von Mises stress and their node, the sum of RF at each
  `*BOUNDARY`, eigenfrequencies or buckling factors, the time reached), also under `results`
  in `--json`; the ccx version printed and checked against 2.22–2.23; an assembly's instance
  map (label offsets, renamed sets and surfaces) in the report and `--json`, which the
  digest uses to name nodes and sets `Instance.label`.
* **Crash guards** — step data outside a step, undefined materials, rotational DOFs on plane
  nodes and other inputs that crash ccx 2.23 are commented, warned or dropped.
* **First ccx errors of non-solving decks** — `*DAMAGE INITIATION` in the form ccx 2.23
  reads (Johnson-Cook kept as an output-only criterion, other criteria commented);
  Poisson's ratio 0 on E-only `*ELASTIC` lines; unused cohesive `TYPE=TRACTION`
  elasticity commented; BCs on DOFs a node does not have (truss rotations, DOFs 7
  and 9) dropped, and DOF 8, which ccx 2.23 reads as the rotation about x, where the
  converted model has no pore, fluid or acoustic pressure (warned where a pore-pressure
  element or a `*FLUID CAVITY` lost it); `OFFSET=SPOS`/`SNEG` as numbers; the
  source-deck faults among the rest named in the corpus notes.
* **Packaging, CI and Windows** — `pipx install git+https://github.com/sandervdbroek/abq2ccx`
  installs an `abq2ccx` command (`pyproject.toml`; copying the file still works), and
  publishing a GitHub release uploads it to PyPI (`release.yml`). GitHub
  Actions run the unit tests and the reference check on Linux, macOS and Windows (Python 3.9
  and the newest) and `validate_with_ccx.py` on FreeCAD 1.1.4's ccx build. Python 3.9 is the
  real minimum: the converter already called `math.gcd` with more than two arguments (the
  docs said 3.7). On Windows, `--run` and `validate_with_ccx.py` find ccx in FreeCAD,
  PrePoMax and bConverged installs, and ccx's output, the reports and the generated docs no
  longer depend on the code page; the solve judge also reads msvcrt's NaN spellings
  (`1.#QNAN`, `-1.#IND`) in the `.frd`.
* **User materials** — a `*USER MATERIAL` whose name would make ccx run one of its own
  routines (`USER…` and `@…` are empty in a stock ccx, `ABAQUS…` a linear-elastic example,
  `JOHNSONCOOK…` and ten more ccx's own laws) is renamed `ABQ2CCX_<name>`, so ccx stops on
  it; `--abaqus-umat` writes user materials for ccx's Abaqus-UMAT interface (`ABAQUS<name>`,
  `ABAQUSNL<name>` under NLGEOM) to run in a ccx built with the deck's UMAT, with a note per
  argument ccx supplies differently. The temperature line ccx reads after a multiple of 8
  constants is added; thermal user materials (ccx's empty `umatht`) and VUMATs are warned.
  Checked in a ccx 2.23 built with a J2 UMAT, which also showed that ccx's `ABAQUSNL`
  interface breaks incremental UMATs (the user guide has the fix).

* **Beam sections the expanded beams cannot carry** — `*BEAM GENERAL SECTION` and `SECTION=I`
  run as ccx 2.23's 2-node beam `U1` where the whole deck allows it (probed: an exact
  Euler–Bernoulli beam once its shear area is large, a wrong shear term, torsion G (I11 + I22),
  wrong nodal forces, linear static and modal steps only, no element ccx expands beside it):
  principal axes, n1 projected per element, a material copy for G J, the I (and T) properties
  of Abaqus' own general-section form, line loads and gravity as nodal forces with consistent
  end moments; in space where G J cannot be had or the shear centre is off the centroid, only with
  `--approximate`, which otherwise keeps the I → `RECT` route. Three planar I-beam decks solve
  (Euler–Bernoulli for Timoshenko beams: reduced physics). The `HEX`, `TRAPEZOID` and
  `ARBITRARY` profiles follow, with Abaqus' formulas (Verification Guide), and a general
  section with a `RECT`, `CIRC`, `PIPE` or `BOX` profile becomes ccx's own beam section with a
  material from E and G (NAFEMS NL6 runs, and its Benchmarks deck is gated with its answer).
* **Published answers** — 30 NAFEMS benchmark decks of the Abaqus 2017 documentation joined
  the corpus, and 26 decks are checked against their published answer (`reference`,
  `test_corpus_references`): 19 give Abaqus' result for the same mesh, 7 differ for reasons
  traced to ccx. They found converter faults, fixed: `*NFILL` sets hold their bounding
  nodes; each equation of an `*EQUATION` card resolves its sets; `DC2D*` / `DCAX*` run as
  ccx's plane and axisymmetric elements; `*NMAP` maps coordinates and normals; `PERIODIC`,
  `MODULATED` and `DECAY` amplitudes are sampled; a transient `*HEAT TRANSFER` without
  `DELTMX` takes Abaqus' fixed increments, and transient thermal steps start from 0 without
  initial temperatures; a zero extra rotation of a cylindrical `*ORIENTATION` is no reduced
  physics.

Corpus: 189 decks solve their own problem; 33 more solve with reduced physics, 14 load
nothing (3 both) and one drifts to a solution that is not the deck's; 221 mesh-only decks are
accepted, 597 need what ccx cannot run; 26 give their published answer (7 with a documented
ccx difference).

## 1.1.0 (July 2026)

* Census-driven fixes over the corpus; usability overhaul of the CLI (batch, `--check`,
  `--json`, `--strict`, `--run`, `--version`) and the module API (`convert_file`,
  `convert_text`).
* `--approximate` mode: opt-in physics reframings with `[APPROX]` warnings.
* Coupling kit, amplitude handling (`SMOOTH STEP` sampling, `EQUALLY SPACED`), name limits,
  `LAMINA` elasticity; assembly reference-node collision fixed (issue #2).

## Initial release (June 2026)

* First release: mesh-generation expansion, assembly flattening, keyword classification
  against the full CalculiX keyword set, element substitutions, the conversion report.
* Cohesive, gasket and pore-pressure elements approximated (warned); ccx 2.23 and Abaqus
  2024–2025 keywords recognised (issue #1).
