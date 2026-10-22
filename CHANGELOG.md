# Changelog

Corpus counts are on the CalculiX version current at the time; from October 2026 on, "solve"
counts only decks that solve their own problem: under their own loads, without reduced
physics.

## Unreleased

* **Geostatic initial stresses and steps** — `*INITIAL CONDITIONS, TYPE=STRESS, GEOSTATIC` was
  commented out. It is now written at each of ccx's integration points: the vertical stress
  linear in the elevation (z in 3-D, y in plane and axisymmetric models) through the card's two
  points, the lateral ones K1 and K2 times it. A linear `*GEOSTATIC` step of a model without
  pore pressure elements becomes a `*STATIC` step (it was `*NO ANALYSIS`, where ccx stopped):
  a soil column under gravity with its geostatic stresses stays put. With pore pressure, `UTOL`
  or a nonlinear step the step stays as it was, and the warning now says why.
* **Warnings and notes say where the card is** — a report entry about one card starts with its
  file and line (`mesh/part.inp:120: ...`; an `*INCLUDE` file relative to the deck's folder), in
  the report, the converted deck's header and `--json` (`location` in each of `entries`, null
  for an entry about no one card). Lines count through `*INCLUDE` and `*PARAMETER`, and a card
  the converter makes from another (an instance's copy of its part's cards) points to that card.
* **Field-dependent material data at each element's field values** — material cards with
  `DEPENDENCIES=n` were collapsed to field 0, and `*INITIAL CONDITIONS, TYPE=FIELD` / `*FIELD`
  commented out as reduced physics, since ccx has no field variables. Where the deck sets the
  values itself, each material's tables are now interpolated at its elements' values as
  Abaqus does (linear in each variable, the last first, held beyond the table; temperature
  and hardening columns kept exactly), one material copy per distinct state
  (`{material}_FIELD<k>`), each section split by element set. Exact where every node of an
  element has the same values all the analysis long (a `*FIELD` applied at once at the start
  of step 1 included); warned as reduced physics where the nodes differ (their mean), a shell
  or beam section varies through its thickness, or a step changes the values (those at the
  end of step 1). User-set fields (USDFLD, `*FIELD, USER`, `FILE=`) keep the field-0 collapse.
* **`*IMPERFECTION` converted** — it was commented out (reduced physics). Data lines and an
  `INPUT=` file (node and shift, `SYSTEM=R`, `C` or `S`) now move the `*NODE` coordinates: the
  deck's own geometry. `FILE=job, STEP=n` takes modes or a static solution from another job's
  results, which ccx cannot read: `--run` first converts and runs that job's deck, `job.inp`
  next to the deck, as `<output>_imperfection.inp`, then moves the nodes by its modes (each
  scaled to a largest displacement component of 1.0, as Abaqus scales them) and runs the deck.
  It does so only for the same mesh and a `*BUCKLE`, `*FREQUENCY` or general `*STATIC` step,
  and not where ccx's buckling factors may not be the lowest; it says why otherwise, and the
  deck runs on its perfect geometry. Without `--run` the card stays commented out and names the
  deck to supply.
* **OFFSET TO NODES orientations, value distributions, integrated output** — three cards that
  were commented out now convert exactly. `*ORIENTATION, DEFINITION=OFFSET TO NODES` (a
  rectangular or cylindrical system) becomes a `*DISTRIBUTION` orientation with each element's
  own axes from its local nodes; ccx stopped on the sections that named it. A `*DISTRIBUTION` of
  a shell's thickness or offset, a composite layer's thickness or angle, a membrane's thickness,
  or a solid's `*ELASTIC`, `*DENSITY` or `*EXPANSION` gives one section per distinct value on
  its own element set, with a material copy per distinct property values; ccx used the
  data-line thickness, or stopped on the distribution name. `*INTEGRATED OUTPUT` (with its
  `*INTEGRATED OUTPUT SECTION`) becomes `*SECTION PRINT` on the surface: the total force, the
  moment about the origin and the area in global axes. A reference node's moment, an
  orientation's axes and `SOCF` are noted: ccx prints none of them.
* **Recorded suspects probed** — a heat load of an earlier step from another source (a node,
  element or set as written) on the node DOFs or faces a later step loads is given again
  there, as Abaqus adds the two (ccx kept only the later value: 14-67 % off); two film
  conditions on one face become one exact film. A radiation condition, or another amplitude,
  is warned. A `*DSFLUX` / `*SFILM` / `*SRADIATE` whose faces another card also loads is now
  converted (it was commented out). A `*STEP, PERTURBATION, NLGEOM=NO` after an NLGEOM step
  drops the NLGEOM=NO, as Abaqus keeps NLGEOM and linearizes about the deformed base state (ccx
  ran a static perturbation step linear: a taut string 12x too soft). A rotation BC on a member
  of a rigid body, kinematic coupling or `*MPC BEAM` whose reference node has a `*TRANSFORM` now
  follows the same rules as without one: it was kept silently, also under `--approximate`. S8R
  elements with two opposite free edges (a strip one element wide) are warned in models with a
  step ccx iterates, where ccx's C3D20R expansion drifts (9-410 % off). Two suspects proved
  exact and are unchanged.
* **Assembly decks convert faster, in less memory** — an instance's mesh is no longer written
  out as text and read back, mesh cards are read a line at a time, and the mesh takes less
  memory per node and element: about 14 % less CPU time over the corpus's 1052 decks (17 % on
  its 661 assembly decks) and 12–34 % less peak memory on the largest assembly decks. The
  converted decks are the same, byte for byte.
* **Explicit coupled temperature-displacement steps under `--approximate`** — ccx 2.23 has no
  explicit coupled step, so `*DYNAMIC TEMPERATURE-DISPLACEMENT, EXPLICIT` stops ccx (`*NO
  ANALYSIS`; the warning now names `--approximate`). With `--approximate` it becomes ccx's
  transient `*COUPLED TEMPERATURE-DISPLACEMENT`, which ccx solves implicitly with the model's
  mass (not scaled away as for Abaqus/Standard's coupled step): the deck's period, increments
  from 1/100 of it (or its maximum increment) down, and Abaqus/Explicit's rules — NLGEOM by
  default, no increment limit, a displacement BC without amplitude held, 20 output intervals.
  Flagged `[APPROX]`: explicit time integration and the heat of plastic work are lost. 19 of
  the corpus' 28 such decks without user materials solve this way, the single-element ones in
  under a second (ccx's explicit form took 5–30 minutes per element). Where ccx's implicit
  dynamics runs 2-D elements with half their mass, this step is flagged too.
* **One output interval** — `*OUTPUT, NUMBER INTERVAL=1` (or a `TIME INTERVAL` of the step's
  period) was written as `*TIME POINTS, GENERATE` from the period to the period, on which ccx
  2.23 stops; it is now the step's end alone.
* **Held BCs at converter-added nodes in Abaqus/Explicit's first step** — a displacement BC
  without amplitude, whose value Abaqus/Explicit ignores, holds the DOF at 0 in the deck's first
  step; a midside node between such a node and a moved one now gets the interpolation, where it
  was left free (warned).

* **Batch triage, crash reports, ccx install hint** — `--json` prints one object per deck per
  line (JSON Lines), now with the deck's `status` (`converted`, `reduced`, `commented` or
  `failed`) and `reduced_physics`, and a line with `error` for a deck that failed (none was
  printed). `--summary FILE.csv` writes a row per deck: status, counts, reduced physics, and
  with `--run` ccx's status and the last step's digest line. An internal error (exit 4) writes
  its traceback into the `.log` (with `--debug` also to stderr) and points to the issues page;
  it suggested PYTHONFAULTHANDLER, which could not show it. `--run` without a ccx, and its
  version warning, say how to get ccx 2.23: `conda install -c conda-forge calculix=2.23`. The
  `--approximate` help and the user guide now name the same reframings, and the guide all of them.
* **Blank fields read by position on more cards** — a blank field before a used one was
  dropped and the next field read in its place. These cards now read it as Abaqus does (0, or
  the field's default): `*CREEP` m (a blank m before the temperature warned of strain
  hardening), the `*SHELL SECTION` thickness (with NODAL THICKNESS the integration-point count
  was written as the thickness), `*NORMAL` components (left out of a midside node's normal),
  `*EQUATION` coefficients, `*TRANSFORM` axes and orthotropic / anisotropic `*ELASTIC` constants
  in the converter's planners, analytical `*SURFACE` coordinates (the surface was rejected), and
  a rotated instance's `*DISTRIBUTION` rows. A blank first DOF on a `*KINEMATIC`,
  `*DISTRIBUTING` or `*KINEMATIC COUPLING` line couples all DOFs, as Abaqus documents; the last
  DOF alone was coupled, and ccx 2.23 stops on such a `*DISTRIBUTING` line passed through.
* **Midside nodes follow a BC that moves one end** — a node the converter adds between two
  (the midside nodes of upgraded shells and beams, ply interface nodes) got a `*BOUNDARY` line
  only from a card that gave both of its end nodes a value. A card that moves one end now gives
  it the interpolation with the other end's BC in force, across cards and steps (`OP=NEW` and
  linear perturbation steps as Abaqus applies them): before, the node kept an earlier step's
  value, or stayed free where two cards held the ends, and the edge kinked (an S8R strip's
  midside node at 0.1 for 0.05). Where the other end's BC varies on another amplitude, or its
  value is unknown (`FIXED`, `USER`, a velocity), it is warned as reduced physics.
* **Body loads and mass of 2-D quadratic elements** — ccx 2.23 integrates `GRAV`, `CENTRIF` and
  `BX` / `BY` on `CAX8R` / `CPE8R` / `CPS8R` at 2 × 2 points, Abaqus fully: on elements whose
  midside nodes lie off the middle of the edges, axisymmetric ones other than parallelograms,
  and under `CENTRIF` on axisymmetric ones, ccx moved part of the load between the nodes
  (0.13–0.38 % of the displacements on 3 × 4 meshes). Such lines now become consistent nodal
  forces; a set's other elements keep the line, and `CENTRIF` under NLGEOM stays, warned. Mass: an implicit `*DYNAMIC` step in ccx 2.23 runs `CPE4` / `CPS4`
  / `CAX4` / `CPE8R` / `CPS8R` / `CAX8R` with half their mass (vibrating √2 times faster): no
  card gives ccx another mass matrix, so that is now flagged reduced physics. `*FREQUENCY`
  integrates the mass of `CPE8R` / `CPS8R` / `CAX8R` / `CPE6` / `CPS6` / `CAX6` at fewer points
  than Abaqus (up to 2.7 % higher frequencies on a coarse mesh, 0.14 % on a fine one): warned.
* **`*DLOAD CENT` and `ROTA`** — ccx 2.23 has neither, and both were dropped. `CENT` (a
  centrifugal load given as ρω²) now becomes ccx's `CENTRIF` of ω² = magnitude / density on a
  set of the elements of each density (`ABQ2CCX_CENT_…`; a `RECT` beam's ρab, as a beam's `CENT`
  is per unit length), and consistent nodal forces where there is no single constant density
  (axisymmetric elements too) or where ccx would integrate the `CENTRIF` at 2 × 2 points and
  move its shares (`CAX8R` / `CPE8R` / `CPS8R`, as for their own `CENTRIF`; under NLGEOM the
  `CENTRIF` stays, warned). `ROTA` (a rotary acceleration α) becomes consistent nodal forces of
  the d'Alembert force −ρα n × r over each element's mass: solids, plane elements, shells (at
  their mid-thickness), membranes, beams, trusses and point masses. The nodal forces stay on the
  undeformed geometry, so under NLGEOM they need `--approximate`. Checked against the
  rotating-disc solution, the hoop displacement of a disc under rotary acceleration and beam
  theory.
* **`*MATRIX GENERATE` writes the matrices** — the step was commented out and ccx stopped there.
  A step asking for the stiffness or mass matrix now becomes `*FREQUENCY, SOLVER=MATRIXSTORAGE`:
  ccx writes the same stiffness and mass to `<job>.sti` and `<job>.mas`, with the DOF of each
  row in `<job>.dof`, in its own format (the report says how it differs from Abaqus' `.mtx`
  files), and stops. It is converted only as the last step, for the whole model, with
  multipoint constraints applied; else it stays commented out, with the reason. A material
  without `*DENSITY` gets `*DENSITY 0` (ccx stops without one: a zero mass). A damping or
  load matrix is not written, and beam, shell and plane elements give the matrices of ccx's
  expanded 3-D model: both flagged as reduced physics. The six corpus decks with such a step
  now write their matrices; the solve judge has a "matrices" verdict for this run, which exits
  without "Job finished".
* **`*EMBEDDED ELEMENT`** — rebar, fibres and other embedded elements were commented out (the
  embedded mesh hung loose). Each embedded node's translations are now tied by `*EQUATION`s to
  its host element's interpolation at the node's natural coordinates, as Abaqus constrains them
  (rotations and temperatures stay free): exact, under `NLGEOM` too. Hosts of every continuum
  type the converter writes (`C3D4/6/8/10/15/20`, plane and axisymmetric elements; a modified
  tetrahedron by its corners), from `HOST ELSET` or the whole model; `EMBED NODES`; nodes shared
  with a host are not embedded; a node outside its host within the exterior tolerance
  (`EXTERIOR TOLERANCE`, `ABSOLUTE EXTERIOR TOLERANCE`) is moved onto it, and weights below
  `ROUNDOFF TOLERANCE` are zeroed, as Abaqus does; a node farther out is warned unless `PARTIAL
  EMBED=YES`. A BC on an embedded node's translations is taken off, as Abaqus neglects it. Part,
  instance and assembly level. An embedded bar on its own nodes matches the merged mesh exactly;
  under a prescribed affine field or a 1 rad turn its nodes and stress are exact.
* **Upgraded shells' new nodes on the curved surface** — the linear shells written as `S8R` /
  `S6` (composite sections; coarse `S4R` under `--approximate`) got their new node at the
  middle of the straight edge, so each quadratic element was a flat facet: on a thin curved
  shell it carried pressure by plate bending between its fold lines (a pressurized quarter
  cylinder, R/t 1000, 8 × 8 cells: u_r −2.9 to 7.6 times the membrane value). The new node now
  lies on the surface the shells' averaged nodal normals define (exact on cylinder and sphere
  meshes, free and symmetry edges included: 0.999–1.003), and stays on the straight edge where
  the shell is flat or folds (Abaqus' 20° rule for averaging normals). Flat meshes are
  unchanged.
* **General contact under `--approximate`** — Abaqus general contact (`*CONTACT` with
  `*CONTACT INCLUSIONS`, `ALL EXTERIOR` or named surfaces, `*CONTACT EXCLUSIONS` and
  `*CONTACT PROPERTY ASSIGNMENT`), which ccx lacks, is written as node-to-surface `*CONTACT
  PAIR` cards between the model's bodies (their exterior faces) that can meet over the analysis
  (boxes within four times the largest prescribed travel plus 5 % of the model's size, a
  heuristic; any load: all): one line per slave body (the struck, yielding or finer-meshed one)
  against the union of its masters, the assigned property or Abaqus' hard frictionless default,
  `ADJUST` where a pair starts overclosed. Self-contact, edge-to-edge contact and pairs of two
  rigid bodies are left out (warned). Two blocks pressed together carry what a hand-written
  pair carries, to all digits. Without the option the cards stay commented out, and the
  warning names `--approximate`.
* **Linear connector behaviour and JOINTC** — a connector with a `*CONNECTOR BEHAVIOR` was
  commented out, and a JOINTC element stopped ccx. Linear `*CONNECTOR ELASTICITY` / `DAMPING`
  (uncoupled or coupled) on the components of `CARTESIAN`, `BUSHING`, `CARDAN`, `ROTATION` and
  `REVOLUTE` / `HINGE` connectors, and a `*JOINT`'s springs and dashpots, now become a
  `SPRINGA` / `DASHPOTA` from a helper node that an `*EQUATION` ties to the component in node
  a's axes (not a `SPRING1`: ccx 2.23's linear solve drops what a prescribed displacement puts on
  one through an equation) to a held node; `AXIAL` a `SPRINGA` / `DASHPOTA`; `RIGID` components and a
  model-data `*CONNECTOR MOTION` constraints. A history `*CONNECTOR MOTION` / `LOAD` becomes a
  `*BOUNDARY` / `*CLOAD` on the helper. Exact for small motions, and under `NLGEOM` where the
  directions cannot turn (rotation components: `--approximate`). A BUSHING under force and
  moment, a coupled bushing, a JOINTC between U1 or B31 beams, motions, loads and a damped mass
  match their closed forms (validate_with_ccx.py `connector_*`, `jointc_*`). U1 beams may now
  carry such connectors.

* **Small conversions** — `*SYSTEM` frames are applied: the `*NODE` coordinates and normals and
  the `*NGEN` arc and parabola points after a `*SYSTEM` card are given in its frame, as Abaqus
  reads them, until the next one or the end of the part (they were read as global, warned).
  `*CONTROLS, ANALYSIS=DISCONTINUOUS` becomes ccx's `*CONTROLS, PARAMETERS=TIME INCREMENTATION`
  with I0 = 8, IR = 10 (ccx ignored it). `*MODEL CHANGE` and `*SUBMODEL` without `TYPE` get
  Abaqus' default (`ELEMENT`, `NODE`), without which ccx 2.23 stops; a `*SUBMODEL` deck is told
  that ccx needs `INPUT=` the global model's `.frd`, and an `ADD` of beam, shell or plane
  elements the first step removed is warned (ccx never adds them back). An Abaqus user element
  is no longer read as ccx's own `U1` beam: its elements take the `*USER ELEMENT`'s node count
  (they were read with none) and the report says ccx cannot run it.

* **Norton creep past ccx's singular-matrix stop** — ccx 2.23 stops ('matrix found to be
  singular') once one `*VISCO` increment's creep strain passes about 45 / (n - 3)^1.5 elastic
  strains (Norton exponent n > 3), where Abaqus integrates on. A `*VISCO` step now gets a
  largest increment below half that at the largest pressure the steps apply, and `INC=` to
  match: a numerical control, the solution unchanged. NAFEMS creep tests 1(a), 2(a) and 5(a)
  now run their 1000 h and give the published creep strains (they stopped at 6.6 and 168 h).
  A `*USER MATERIAL` on a material no section uses is now reported as never called (the note
  said ccx would stop on it). `corpus/fetch.py` also fetches the files the decks read with
  `INPUT=` (`--companions`: only those).
* **`*LOAD CASE`: one step per load case** — a linear perturbation `*STATIC` or `*STEADY STATE
  DYNAMICS` step with several load cases was solved as one, the cases superposed (warned). Each
  load case now becomes its own ccx step with the step's loads, BCs and output requests and the
  case's own, about the same base state, as Abaqus reads them; a `*BOUNDARY, OP=NEW` in any case
  releases the base-state BCs in every case. A two-case step after a loaded static step now
  matches the hand-written single-case steps exactly (the superposed answer was 0.02 off).
* **`*BOUNDARY, FIXED` on `*TRANSFORM` translations** — ccx 2.23 holds such a DOF at the
  node's global displacement component, read as the local value (silently wrong). It is now
  written as the value the step finds it at, in the local axes: 0 at rest, else the value of
  the BC that holds it (a midside node's interpolated one too); where that is unknown (moved by
  loads) FIXED stays, warned. A local axis along the global one keeps FIXED. A FIXED rotation
  on an upgraded beam's midside node gets its value too (it was left free). In a linear
  perturbation step a FIXED translation or shell/beam rotation is a zero perturbation (a FIXED
  rotation in a static perturbation step was given twice its base value).
* **Small correctness batch** — ccx 2.23 has one output frequency for the `.frd` and the `.dat`:
  where the `.frd` requests take Abaqus' default and every request asks for output every so
  many increments, it is now their greatest common divisor (a `*NODE PRINT, FREQUENCY=1` in a
  `*DYNAMIC` step beside the default field output every 10 increments was printed every tenth
  increment; a `.frd` frequency the deck names still wins). A load on a
  `VALUE=ABSOLUTE` amplitude at magnitude 1 is held at its end value in later steps (it was lost
  after a `*CLOAD, OP=NEW`). `*DLOAD BX / BY / BZ` on surface elements (a force per unit area)
  becomes nodal forces, and a set that mixes them with other elements keeps the line for those
  (it was dropped whole, unflagged). Newly flagged as reduced physics: `*STATIC, STABILIZE` in a
  step ccx runs nonlinearly; `DASHPOTA` in explicit dynamics (ccx ignores it) and in a
  small-strain implicit step where its nodes can move across its line (ccx damps along the
  current line). No longer flagged: a knot whose rotations BCs hold at zero in a step ccx runs
  nonlinearly without NLGEOM.
* **Contact property tables in ccx's meaning** — ccx reads three cards' tables otherwise than
  Abaqus, and they passed through. A `*SURFACE BEHAVIOR, PRESSURE-OVERCLOSURE=TABULAR` curve gets
  a point far out on its last slope: Abaqus continues it there, ccx held the last pressure (two
  pressed cubes: 100 for Abaqus' 294.1). `EXPONENTIAL` becomes Abaqus' curve as a TABULAR one
  (within 0.2 %): ccx's c0 is where the pressure is 1 % of p0, never zero (466.2 for Abaqus'
  431.4). A `*GAP CONDUCTANCE` table against clearance becomes its closed-gap value for every
  pressure, as Abaqus keeps it in contact: ccx read it against pressure (no heat flow across the
  pressed cubes for Abaqus' 49.75); beside a `PRESSURE` card it is left out. ccx 2.23's
  face-to-face contact reads no TABULAR table (no contact force): a straight line through the
  origin becomes `LINEAR` there, other curves and `EXPONENTIAL` there are reduced physics. So
  are conduction across open gaps, which ccx does not model, and a `PRESSURE` conductance table
  on a node-to-surface pair, which ccx 2.23 reads at a pressure of its own.
* **Energy, volume and contact output mapped** — output requests that were dropped now reach
  ccx 2.23's labels, with what differs said in a note; none changes the solution (probed on
  static, NLGEOM, plastic, implicit and explicit dynamic runs) or a step's output control:
  * whole-model energies (`*OUTPUT, HISTORY, VARIABLE=PRESELECT`, `*ENERGY OUTPUT / PRINT /
    FILE`; about 600 corpus decks) -> `*EL PRINT, TOTALS=ONLY` over the model or the element
    set: ELSE for ALLIE / ALLSE (ccx's stress work: ALLSE + ALLPD + ALLCD, without ALLAE), in
    `*DYNAMIC` steps ELKE for ALLKE; none in eigenvalue and perturbation steps, as in Abaqus.
    A step ccx iterates after a `*FREQUENCY` / `*BUCKLE` step is warned: ccx starts its
    energies from the last eigenmode's;
  * SENER -> ENER; ELSE, ELKE, EVOL and SVOL as field output -> an `*EL PRINT` per element
    beside the `*EL FILE` (ccx prints them only; its EVOL is the undeformed volume);
  * CPRESS, CSHEAR, COPEN, CSLIP -> ccx's CSTR / CDIS; CFN, CFS, CFT and their components on
    `*CONTACT OUTPUT` -> `*CONTACT PRINT` per face-to-face pair;
  * labels past 16 wrap onto another data line (they were cut: ccx stops on a 17-entry line),
    and SDV<n> of three digits is SDV like shorter ones (each printed every state variable
    again). Node output A stays dropped: ccx 2.23 writes no accelerations.
* **`*DAMPING` per material** — Abaqus' Rayleigh damping is a material option; ccx 2.23 has one
  `ALPHA`, `BETA` pair for the whole model (the last card wins), so the passed-through cards ran
  every material at the last one's values. Values that every material with mass (`ALPHA`) or
  stiffness (`BETA`) shares are now written as that pair, both given (a missing one is Abaqus'
  0); a value that differs, also against a point mass (ccx damps it, Abaqus only by the `*MASS`'s
  own `ALPHA`) or a spring or contact (ccx's `BETA` damps them, Abaqus' does not), is left out as
  reduced physics (`--approximate`: the materials' value). `BETA` with an explicit step is left
  out too (ccx's explicit solver stops on it; mode-based steps: see `*MODAL DAMPING`).
  `STRUCTURAL` stays per material; a zero one and `COMPOSITE` are not written.
* **`--run` streams ccx's output** — it held all of ccx's output in memory and showed it only
  when ccx ended; ccx 2.23 can print without end (a vanishing pivot in its MPC cascade), and
  that output once filled 13 GB. Now it shows the output as it comes, writes it to
  `<output>.ccx.log` (the first 100 MB, then the last lines) with bounded memory, and ends
  with ccx's own `*ERROR` and `*WARNING` lines, each once with its count. `--timeout SECONDS`
  stops ccx and what it started after that much wall-clock time (status `timeout`; no limit
  by default); `--json`'s `run` gives the log's path. `validate_with_ccx.py` and the corpus
  test run ccx the same way, stopped after their time limit or 100 MB of output.
* **`*TIE` on conventional shells** — Abaqus ties a shell's nodes, its reference surface; ccx
  2.23 ties the faces of the solids it expands shells to, half the thickness off. A slave
  surface on shells whose nodes lie on solid master faces (a skin on a solid, a shell edge on a
  solid face) now becomes a node surface of those nodes, and with `OFFSET=SPOS` / `SNEG` the face
  at the reference surface; Abaqus' position tolerance is written out. Against the merged mesh
  the SPOS / SNEG / both-sides faces were 1–14 % off, a T joint's edge faces 57 % in bending
  (they clamp the joint the tie hinges), and without a tolerance in the deck ccx tied none of
  them. A faceless (double-sided) shell line in a tie is no longer dropped, and a slave sharing
  nodes with the master no longer leaves the tie out. Where no ccx form is exact (shell nodes
  off the master surface, which Abaqus ties through a rigid offset; a master on shells; shell
  faces on shells; shell edges at an angle or of other sections; a step solving for
  temperatures), the deck's surfaces stay, warned, as reduced physics. Also for `*CONTACT PAIR,
  TIED`. Shell edges tied to coplanar edges of the same section stay as they were: exact.
* **Trusses beside held beam / shell rotations** — ccx 2.23 overwrites one entry of its BC index
  per truss node (`gen3dtruss.f`), so a truss anywhere in the model, even an unconnected one held
  at both ends, could free a held beam or shell rotation without a message (a clamped `B31` tip
  3.2e11 for -1.145; a `*BUCKLE` factor 7.87 for 654.8) or send a later step's BC value to the
  truss. Where that can do harm the deck now gets one-term `*EQUATION`s on new unconnected nodes,
  one per BC DOF at step 1 plus one: they move every such entry past the BCs and hold nothing of
  the model (the decks without their trusses to the last digit). `--run` checks the job's `.12d`
  for a mean-rotation MPC per rotation held at step 1 and reports any it lacks (exit code 1).
* **`*MODAL DAMPING`** — passed through raw, it ran differently in ccx 2.23: Abaqus'
  `VISCOUS=RAYLEIGH` alpha was read as a damping ratio, a step's ratios stayed in the later
  steps (Abaqus: its own step only), a later card for fewer modes left the higher modes of an
  earlier one undamped and could crash ccx, and a `RAYLEIGH` card replaced the `*DAMPING` pair
  of later `*DYNAMIC` steps. Each mode-based step now gets its own damping: ratios (zeros where
  it has none), or one `*MODAL DAMPING, RAYLEIGH` with the step's Rayleigh factors plus the
  material `ALPHA`, `BETA` that Abaqus projects onto the modes (exact where one pair damps the
  whole model, which was flagged and left out before); a later `*DYNAMIC` step gets the
  `*DAMPING` pair back. Rayleigh factors that differ between modes, frequency-dependent values,
  `STRUCTURAL` and `COMPOSITE` modal damping, and ratios together with Rayleigh damping (ccx
  applies one kind per step) are left out as reduced physics.
* **Explicit mass scaling on part of the model** — `*FIXED MASS SCALING, FACTOR=f, ELSET=...`
  on part of the model (a local factor overriding the global one) was dropped (ccx ran the true
  mass); each section whose elements share a factor now gets a copy of its materials with the
  density f times and the specific heat 1/f times the original, and `*MASS` values, a `*BEAM
  GENERAL SECTION`'s `DENSITY=` and rotary inertias go out f times larger, GRAV magnitudes f
  times smaller (a GRAV set holding several factors split into a set per factor): Abaqus'
  scaled mass matrix. A section of two factors, a user material or a factor that changes
  between steps stay dropped, with the reason.
* **Checked against Abaqus' own decks** — a `*SURFACE` line without a face label now takes its
  faces trimmed as Abaqus trims an open free surface (a face at the perimeter goes where it turns
  an element's corner or more than 30°; not with `TRIM=NO` or on the master of a finite-sliding
  contact pair), as Abaqus' trimming verification decks show: a distributing coupling or load on
  such a surface took the faces at its ends too (0.28 off a uniform pressure on a `C3D8` layer). A
  distributing coupling on axisymmetric faces becomes equations weighted by areas of revolution,
  where Abaqus' `xcouplingd_std_tarea_cax4` puts its reference node (it stayed ccx's card, 0.26
  off). A steady-state heat transfer or temperature-displacement step with a blank time period
  gets `1.` (ccx read 0: `*ERROR`, step time NaN); a blank one elsewhere, and a `*MODAL DYNAMIC`
  without a data line, are warned. The `*ELCOPY, REFLECT` brick order is the one Abaqus' bolted
  pipe flange decks label the copies' faces by.
* **Pressures on `CAX8R` / `CAX6` edges** — ccx 2.23 integrates a face pressure on the bricks it
  expands these axisymmetric elements into at 2 points along the edge, while Abaqus integrates
  distributed loads fully: where an edge's midside node lies off its middle or off its chord, ccx
  moved part of the load between the edge's nodes (0.95–1.07 of the face displacements on a 3 × 4
  mesh with the midside nodes at a third of each edge; a 2 × 2 thick sphere 0.986–1.054 of Lamé's
  inner displacement). In a deck without NLGEOM such a `*DLOAD` / `*DSLOAD` pressure line now
  becomes its consistent nodal forces (0.993–1.007 there); under NLGEOM, where the pressure
  follows the deforming faces, it stays, warned. `CAX8`, plane elements and straight edges with
  the midside node in the middle load exactly in ccx and are unchanged.
* **`--abaqus-umat`, run on the corpus** — 130 user-material decks run with their own UMATs (31
  builds of ccx 2.23) showed three more interface facts, now in the notes and the user guide:
  under `ABAQUSNL` DFGRD0 / DFGRD1 are global while the stress comes in turning axes (a UMAT
  that builds its stress from DFGRD1 is off where the material turns: neo-Hookean simple
  shear 37 %; exact when handed the right stretch U), a UMAT's plane-stress branch never runs,
  and ccx's worker threads (512 KB of stack on macOS) need large UMAT arrays out of the stack.
  The U0 warning no longer says that a DFGRD1-based UMAT runs right; the user guide builds
  ccx once and links each deck's UMAT, compiled as Abaqus compiles it, ahead of its archive.

* **ccx stops the conversion now avoids** — a `*TIE` line naming one surface as slave and master
  is left out (Abaqus ties nothing there; ccx 2.23 looped without end), and a solid or node slave
  surface that shares nodes with its master becomes a node surface of its other nodes (Abaqus
  ties no shared node; other element families: the line is left out, warned). An unread node
  surface holding `*RIGID BODY` members of plane elements is left out (ccx stopped in cascade).
  A `*MASS`-only member of a kinematic coupling gets the massless tetrahedron a rigid-body member
  gets in `*FREQUENCY` decks (ccx stopped in add_bo_st). A static perturbation step between a
  `*FREQUENCY` step with its own BCs and the modal step reading its modes keeps those BCs, warned
  (ccx stopped on the .eig file). `*STEP, PERTURBATION` after a `*BUCKLE` step is dropped where
  the general steps before it leave the model unstressed (was reduced physics). Section
  materials without `*DENSITY` get `*DENSITY 0` where mass acts and temperatures are defined
  (ccx gave them the density of the element assembled before). Warned: `*DEFORMATION
  PLASTICITY` with a `*FREQUENCY` step (ccx can stop after the eigenvalues, depending on the
  units), and a `*FREQUENCY` step whose eigenvalue count ccx's ARPACK cannot reach because
  massless sections add degrees of freedom. The beam-node moment warnings now say what happens
  and how to avoid it: in `*DYNAMIC` ccx exits where the step starts with the node unturned;
  after a `*BUCKLE` ccx deletes every load, so the moments given again make a second
  mean-rotation MPC and ccx loops (or, about one axis, runs 1 % off: now reduced physics).
* **Explicit mass scaling** — `*FIXED MASS SCALING, FACTOR=f` on the whole model, the same in
  every explicit step, was dropped (ccx ran the true mass, at a sqrt(f) smaller increment); its
  densities, `*MASS` values and rotary inertias now go out f times larger and its specific heats
  and GRAV magnitudes f times smaller (Abaqus' gravity and thermal response keep the true mass):
  Abaqus' scaled mass matrix. A target increment `DT` (`TYPE=BELOW MIN`) becomes ccx's selective
  mass scaling under `--approximate`; the other forms stay dropped, with the reason.
* **`--abaqus-umat`** — the user guide builds ccx 2.23 with the deck's UMAT and the U0 fix in
  a few commands (conda-forge's compilers, SPOOLES and ARPACK). Checked in such a build with an
  elastic and a J2 UMAT on ten element types, and `validate_with_ccx.py` checks one built with
  its `TEST_UMAT` when `CCX_UMAT` names it; the `ABAQUSNL` notes now say that strain and
  stress come in axes that turn with the material while DROT is the rotation increment (a UMAT
  that turns its tensor state variables by DROT turns them twice) and that COORDS is the
  undeformed position.
* **Small follow-ups** — `*NGEN` with an increment of 0 (the default 1) no longer skips its
  line, and a skipped line's end nodes still join its NSET, as Abaqus documents. `*NMAP,
  DEFINITION=NODES` reads its node fields by position. A beam section without an n1 line turns
  its default n1 with a rotated instance (it stayed global: the turned beams bent up to 52 %
  off). A coupling written as a `*RIGID BODY` no longer leaves its surface, and an internal
  element set only that surface names, in the deck unread. Now reduced physics: `*DSLOAD,
  SUBMODEL`, model data holding a `*PARAMETER` that does not evaluate, and step-time
  amplitudes in a `*MODAL DYNAMIC, CONTINUE=YES` step (Abaqus continues the step time there,
  ccx starts it at 0). A material whose copies took all its sections gets no conversion notes.

## 1.5.0 (October 2026)

Steps read through one step model, with one rule each for NLGEOM, step time and an unterminated
`*STEP`; chains of linear perturbation steps, static perturbation sums and `*BUCKLE` base
states; eigenvalue, modal and steady-state steps with knots. Couplings and constraints: free
coupling twists held, distributing couplings on plane, axisymmetric and membrane edges and the
legacy `*DISTRIBUTING COUPLING`, rigid-body reference nodes, nodes whose rotation two features
use. Elements that ccx 2.23 runs otherwise than Abaqus are flagged as reduced physics: `S4R`,
the one-point plane, membrane and beam elements where only hourglass stiffness resists their
bending, and plastic `CPE4` / `CAX4`, which lock; `--approximate` writes elements that behave in
their place. Beams in general 3-D directions, springs, dashpots, composite solids and shell
section axes now convert as Abaqus reads them. More cards ccx 2.23 stopped or crashed on without a word are converted or warned,
the converter crashes a third whole-file code review found are fixed, and the corpus converts in
about 40 % less CPU time. Corpus on ccx 2.23: 235 decks gated, 177 solving their own physics
(1.4.0 counted 188, mainly because its `S4R` and plastic `CPE4` / `CAX4` decks now count as
reduced physics).

* **Input-side readings** — a blank `*BEAM SECTION` n1 line (the default) before the
  integration-point line made that line n1 (8.9x the deflection); n1 lines with a blank or
  left-out field and `*AMPLITUDE` data with a blank field (SCALEY, EQUALLY SPACED, PERIODIC, a
  held end value) are now read by position. A beam element line with Abaqus' extra orientation
  node shifted every later element; the node now gives the beam's n1, with one `*BEAM SECTION`
  per direction. `*ELCOPY, REFLECT` reverses the copies' node order (they were inside out). A
  redefined `*PARAMETER` takes its last value; instance-qualified element labels on `*INITIAL
  CONDITIONS` and `*MODEL CHANGE` take the element offset; an assembly set named like a
  flattened instance set stays apart; bare flags on a keyword continuation line (`STABILIZE`,
  `FIXED`) are read as flags. `*INITIAL CONDITIONS, TYPE=TEMPERATURE, FILE=` and
  `*FRICTION, ANISOTROPIC` now count as reduced physics.
* **Step time periods** — a zero time period on `*STATIC` / `*GEOSTATIC`, which Abaqus and ccx
  read as 1.0, was read as 0 where the converter evaluates a step-time amplitude: a load on one
  was given back at its time-0 value after a linear perturbation step ("every load lost"), and
  velocity BCs of the step were not integrated. ccx reads a blank `*MODAL DYNAMIC` period and a
  zero static perturbation one as 1.0 and adds it to its total time: the later steps'
  `TIME=TOTAL TIME` amplitudes are now shifted by it (were read 1.0 late, or warned as unknown),
  and such a modal dynamic step gets the `INC=` its increments need.
* **Shell sections: material axes and temperatures** — a shell, membrane or continuum shell
  off the x-y plane counted as having the global axes, so an orthotropic `*EXPANSION` there got
  no NLGEOM warning (ccx 2.23 drops its turned shear: half the stretch), and a zero-shear
  `TYPE=ANISO` one went out as `ORTHO`; they now take their elements' own axes. `*SHELL
  SECTION, TEMPERATURE=n` and `*BEAM SECTION, TEMPERATURE=VALUES` were dropped with a note, and
  ccx read the second point's temperature as a gradient (a uniformly heated plate bent); their
  temperature lines are now written as ccx's temperature and gradients — exact where the
  values vary linearly through the thickness or across a RECT section, warned otherwise. A
  midside node the converter adds between nodes given temperatures on two cards got none
  (a bar moved 0.068 where it stays put); it now follows the temperatures in force. A
  `*SURFACE` with a rigid element line and a line the ply split divides lost a ply line; rigid
  skins on an S4R edge written as S8R drew a false "hanging midside node"; and a coupling on a
  node set that a load also names missed the S8R midside nodes (the surface takes a copy now).
* **Eigenvalue and modal steps ccx gets wrong with knots** — a `*MODAL DYNAMIC` step
  segfaulted ccx on a rotational BC of a shell/beam node and stopped on a moment there, and a
  `*CLOAD` on such a node moved the model wrongly in `*MODAL DYNAMIC` and `*STEADY STATE
  DYNAMICS` steps (orders of magnitude too small), unwarned. Those nodes now get knot beams:
  the response equals ccx's own modes superposed. After a step ccx runs through its nonlinear
  solver, ccx carries an equation or rigid constraint that eliminates a knot's DOF wrongly
  into later eigenvalue, modal and linear steps (a cantilever tied to a `*RIGID BODY`: 61 kHz
  for 462 Hz); that is now warned, with reduced physics. A `*MASS`-only member of such a body
  no longer gets the massless tetrahedron there, on which ccx exited 255.
* **Cards ccx stopped on without a warning** — a transient `*HEAT TRANSFER` without DELTMX
  and a `*VISCO` without CETOL get DIRECT, but their interval output went out as TIME POINTS,
  which ccx refuses beside DIRECT; it is now FREQUENCY=. An analytic amplitude is sampled
  over the steps that read it, not commented out because a later step's time is unknown (a
  Riks step); an amplitude a card uses that is still commented out is warned (ccx stops
  there). `*BOUNDARY, FIXED` on shell, beam or coupling rotations holds them at the value the
  step finds them at, where it is known (else left free, warned). A collapsed S4R is written
  as S3R, Abaqus' own triangle for it (exact; a collapsed S4 under `--approximate`). `*CLOAD`
  on DOF 0, 11 or above 30 is left out, warned. A displacement BC new on a `*TRANSFORM`
  node's DOF still at rest ramps as in Abaqus (it was stepped, flagged reduced). Warned where
  ccx still stops or runs without end: trusses in an explicit step, `*DISTRIBUTING` on a
  node surface kept as ccx's card, moments on beam nodes in `*DYNAMIC` (exit 255) and around
  a `*BUCKLE` step (an endless MPC loop).
* **Rigid-body reference nodes** — a shell `REF NODE` with a `*TRANSFORM` in its own body kept
  the axes after the free reference node took its place, so its drilling rotation stayed free in
  a `*DYNAMIC` step and ccx stopped; the free node now takes the `*TRANSFORM`, and the shell
  node's rotation is tied to the body. A `REF NODE` on an element outside the body (a rigid
  element's node, the deformable mesh, a spring) printed that element's forces as its reaction
  force; it now gets a free reference node too. A BEAM / WELD connector whose node b carries
  the BCs lost them (ccx exit 255): its rigid body is now rooted at the node with the most BCs,
  and the other node's BCs follow the `*RIGID BODY` rules, not the `*MPC BEAM` ones. An initial
  angular velocity on a rigid body's reference node landed on another node's DOFs (the body
  stood or spun about another axis); it now goes to the ROT NODE, and initial rotation values
  ccx cannot take elsewhere are dropped with a warning.
* **Nodes whose rotation two features use** — a distributing coupling whose reference node
  another coupling also uses (two parts joined at one reference point) tied no rotation, so
  ccx solved a mechanism (1e13) without a warning. Its rotation rows now go on a ROT NODE the
  couplings share, or on a kinematic coupling's reference node's own DOFs 4-6. A `*RIGID BODY`
  and a kinematic `*COUPLING` on one REF NODE turned separately; the body's ROT NODE now
  follows the node. `*COUPLING, ORIENTATION=` with `*DISTRIBUTING` of some rotations stopped
  ccx; the rotations no row ties are now held (exact). A pre-tension cut of a beam's last
  element clamped the cut end (5.2x stiffer) or stopped ccx at a kinematic coupling's
  reference node; the end now turns freely, or with the node through a knot of its own
  where something else uses the node's rotation (U1 beams: held at zero, warned). Equations
  whose eliminated DOFs appear in each other could reach ccx with a pivot that vanished; ccx
  then printed warnings without end.
* **Load entries ccx keys otherwise than Abaqus** — nodal forces converted from tractions,
  beam line loads or surface-element pressures on a step-time amplitude are now held at their
  end value in later steps, as Abaqus and ccx hold them: after the deck's `*CLOAD, OP=NEW` they
  went out on the amplitude again, which ccx started over, and given again on their amplitude
  they were not written, so ccx held the old value (2x). `GRAV` / `CENTRIF` given again in
  another direction added to the old load (ccx keeps one per set and direction): a zero line
  in the old direction now goes first. Two such lines of one set and direction on two
  amplitudes in a step went on the later amplitude; the later one now goes on a copy of the
  set (exact). One converted load on two amplitudes in a step, two `*CFLUX` / `*DFLUX`
  amplitudes on one node or face (ccx stopped) and a second `*FILM` / `*RADIATE` on one face
  (ccx kept the later only) are now left out, warned. OP=NEW on a later card of a step
  (invalid in Abaqus, ignored by ccx) is dropped with a warning for every load card, as for
  `*BOUNDARY`. A delayed `*CLOAD` / `*DLOAD` card whose twin had no data lines lost its
  amplitude.
* **One rule per step question** — the facts the converter reads from a deck's steps follow
  one rule each. A model-only deck (no procedure) with circular-section beams now gets the
  knot beams its rotational BCs need, as a mechanical deck does. A step with a second
  procedure card (Abaqus allows one, right after `*STEP`) is converted as its first one, the
  other card commented out and warned: ccx ran the later card. A procedure card between steps
  (commented out) no longer counts for the step before it or for the deck: an explicit one made
  the whole deck explicit. A circular-section beam node whose rotation a step's later line sets
  back to 0 no longer gets a knot beam (it stiffened the beam slightly; the zero clamp is exact).
  A `*BUCKLE` step's `LOAD CASE=2` cards, which ccx cannot have, no longer count as BCs
  anywhere: a 2-D column whose twist only such a card held buckled about the free twist
  (factors near 1, without a warning). `LOAD CASE=2` cards that repeat the `LOAD CASE=1` lines
  but not their missing OP=NEW (the modes then lose the base state's BCs) are now warned as
  reduced physics, not noted as exact.
* **Material copies and card order** — a section-mass copy (`*SHELL SECTION` / `*MEMBRANE
  SECTION, DENSITY=`) lost cards such as `*DEFORMATION PLASTICITY`, so ccx stopped ('no elastic
  constants'); a copy now has every card but `*DENSITY`. Ply-split continuum shells now name the
  copy on their ply lines, so its expansion is no longer misjudged. Blank-free values
  (`TYPE=ENGINEERINGCONSTANTS`, `DEFINITION=SMOOTHSTEP`) are read as spelled with blanks (the
  `*ELASTIC` was commented out). ccx stops on `*CREEP` or `*PLASTIC` before `*ELASTIC` and on
  `*CREEP` before `*PLASTIC`: they are now written in that order. A Johnson-Cook `*DAMAGE
  INITIATION` is commented out where the converter writes a material after the deck's (ccx gives
  it to the last one and stopped). In thermal steps, elements without temperature DOFs (a C3D8
  beside C3D8T) now carry and store no heat: their material gets `*CONDUCTIVITY 1e-30` and
  `*SPECIFIC HEAT 0` in place of its own (a copy where it is shared). They conducted, and the
  heated cube's far face was at 20.9 instead of 42.6. `*HYPERFOAM, N=1, DEPENDENCIES=0` gets the
  exact N=2 form.
* **Couplings on plane and axisymmetric element edges** — a kinematic coupling on an element
  surface of CPS / CPE / CAX elements coupled every node of the elements, not the edge's
  (interior nodes rigid: 52-56 % off), with false "ccx stops" warnings and, under
  `--approximate`, a legitimate BC dropped. ccx 2.23's own coupling on such faces couples
  other nodes for every face label (CPE4 -56 %, CAX4 -22 %). The edge's nodes are now coupled,
  through a node surface where ccx's card stays: exact. ccx's `*DISTRIBUTING` card on such
  faces (kept on axisymmetric ones) is warned as reduced physics. A legacy `*KINEMATIC
  COUPLING` with one node set on two DOF ranges (`RIGHT, 1, 2` / `RIGHT, 3`) became two
  couplings of the same nodes, and ccx exited 255: one coupling per set of coupled DOFs now.
* **Static perturbation steps: base + perturbation** — two lines of one load in such a step
  each got the base value added, so ccx counted it twice. It now goes on the first line only.
  Base-state loads, BCs and temperatures on a `TIME=TOTAL TIME` amplitude kept rising through
  the step in ccx (the load doubled). They are now held at their values at the general step's
  end. A `*STATIC` without a data line read the next card as one: a card with parameters gave a
  false "unknown time period" warning, and a later step's `TIME=TOTAL TIME` load came out 1.5x.
  Its period is now 1, Abaqus' default.
* **Beams in general 3-D directions** — ccx 2.23 makes rotational BCs and moments on a beam
  node mean-rotation MPCs about the global axes, exact only about the section's own axes: a
  cantilever turned in space was 6 % to 4.5x off under a tip force, 2x under a tip moment, its
  frequencies 10-65 % low. Such a node now gets a `*TRANSFORM` along its section axes, its BCs
  and loads in its components: the axis-aligned answer to 1e-7. Where that has no exact form
  (BCs about other global axes, cards that tie DOFs, a `*DYNAMIC` step) it gets a knot beam
  (frame-invariant; the section is rigid there). Under NLGEOM, moments about several section
  axes are warned; a deck with an explicit step is reduced physics.
* **`*DLOAD` BX / BY / BZ on shells** — Abaqus applies them as a body force per unit volume;
  ccx 2.23 applied them on its shells as a pressure on the shell's face, so a plate under BX
  bent out of its plane, without a warning. They are now `GRAV` of B / density along the axis,
  on a set of the shells of their own, or consistent nodal forces (B x thickness per unit area)
  where the material has no single constant density. A body force and a pressure on one shell
  under different amplitudes no longer stop ccx. The corpus's Scordelis-Lo roof
  (barrelvault_s3r_fineirreg) now sags under its own weight instead of lifting.
* **BCs and base states across linear perturbation steps** — a `*FREQUENCY` or `*BUCKLE`
  step's own BCs (or its OP=NEW) stayed in force in the next one in ccx, silently (frequencies
  2.5x too high). That step now gets the base state's BCs again. A `*BUCKLE` step between a
  `*FREQUENCY` step and the modal step reading its modes keeps that step's BCs, which ccx
  needs there (warned). A modal step starting with other BCs is warned about (ccx stops on
  fewer, holds more). A `*STEP, PERTURBATION` step after a `*BUCKLE` or `*MODAL DYNAMIC` step
  started from that step's state (16-20 % low): before any general step PERTURBATION is
  dropped (exact), else warned. `*BOUNDARY, FIXED` after such a step or a static perturbation
  step held that step's state; it is now the base-state value where the base state prescribes
  the DOF, else warned. A `*FREQUENCY` step no longer gets converted nodal forces as a `*CLOAD`.
* **Springs, dashpots and anisotropic masses** — ccx 2.23 stopped on a `*SPRING` constant
  without a decimal point (`100`, `1e-3`), on a `SPRINGA` card's DOF line and on a `DASHPOTA`
  card's: constants now get a point, and those lines go. `SPRING1` / `SPRING2` DOFs at a node
  with a `*TRANSFORM` are the node's local ones in Abaqus; ccx used the global ones (33 % off
  at 30°). `DASHPOT2` (a DASHPOTA along the node line) and `*MASS, TYPE=ANISOTROPIC` (the
  isotropic M11) are now exact, through new nodes that `*EQUATION`s tie to the elements' nodes.
  A connector on a `*DISTRIBUTING` reference node now ties its rotation (ccx exited 255). Under
  NLGEOM, an unoriented kinematic coupling of some translations whose reference node can turn
  is warned as reduced physics (ccx keeps the global axes; Abaqus turns them).
* **Faster conversion** — reading a deck, registering and writing its mesh, and the planners'
  passes over every element are faster, and Python's cyclic garbage collector, which found
  next to nothing to collect, is off while a deck converts: about 40 % less CPU time over the
  corpus's 1052 decks, up to half on the largest. The converted decks are the same, byte for
  byte.
* **Free coupling twists held in every form** — the hold on the ROT NODE now also covers
  `*DYNAMIC` and linear-rigid decks (ccx stopped converging or exited 255, without a warning),
  a `*TRANSFORM` on the reference node (solved 1e12 off, silently), `*KINEMATIC COUPLING` cards,
  and, without NLGEOM, couplings of some translations or of shell or beam nodes (as the linear
  equations Abaqus solves there). The deck's own BCs on the node's rotations count. All
  probed exact; under NLGEOM the last ones are warned.
* **`*CLOAD` and `*EQUATION` on DOFs ccx lacks** (7-10, 12-30) stopped ccx. The line, or the
  whole equation, is now left out, warned as lost where an element has the DOF.
* **More composite solids split** — C3D8I, C3D20 and C3D20R bricks (a 20-node layer is tied to
  the element's own field), and layer axes or angles from a `*DISTRIBUTION`. These were
  commented out (ccx stopped). The `*DISTRIBUTION` axes are exact; the new bricks are
  reduced physics (their layer integration or C3D8I's modes differ).
* **`*DLOAD` / `*DSLOAD` HP** (hydrostatic pressure) is now consistent nodal forces, exact in
  small-strain steps. A face the zero-pressure level cuts, and NLGEOM steps, stay commented out.
* **`DASHPOT1`, and more part data in rotated instances** — a `DASHPOT1` (a node's DOF to
  ground) was read as a 2-node element and dropped with its set, so ccx stopped on its
  `*DASHPOT`. It is now a `DASHPOTA` to a new ground node that `*EQUATION`s keep on the DOF's
  line: exact, also under `NLGEOM` (probed). The `*DASHPOT` DOF line of `DASHPOT1` /
  `DASHPOT2` is dropped; ccx read it as a coefficient and stopped in a `*DYNAMIC` step. In a
  rotated instance, a `*GAP` closure direction, a `DASHPOT1` DOF, the moments a `*DISTRIBUTING`
  releases and the axis of a `HINGE` / `REVOLUTE` without an orientation now turn with the
  part. A warning comes where an assembly `*TRANSFORM` sits on a node of a turned part
  `*EQUATION` (Abaqus does not document it). `*MASS, TYPE=ANISOTROPIC` is written as the
  isotropic M11 that ccx reads, as reduced physics unless all three are equal. Two NLGEOM
  cases count as reduced physics: an oriented coupling of some translations (ccx does not turn
  its axes) and a kept `*DISTRIBUTING` card with an `ORIENTATION` whose reference node is
  loaded (ccx reads those loads in its axes).
* **Two rotational BCs on a shell node** — ccx 2.23 then holds both rotations in the shell
  plane, so also the third, free one where its axis is not the normal: `ZSYMM` on half a
  cylindrical panel was 52-63 % off the whole panel. Where the free axis lies in the shell
  plane, one rotation line is the exact form and is written instead (probed); elsewhere it is
  warned (reduced physics). The corpus' NAFEMS LE3 hemispheres and barrel vault change.
* **Translational BCs on transformed S8R / S6 corner nodes** — ccx 2.23 ties such a BC to the
  middle of the three nodes it expands the node into, so the shell section turns there (NAFEMS
  LE2 6.4 % off in displacement). Such a node now leaves the `*TRANSFORM`, its BCs and loads
  written in global components where they have that form; else it is warned (reduced
  physics). The same for a knot's transformed BCs in a `*DYNAMIC` step after a geometrically
  linear step, which ccx did not meet.
* **A kinematic coupling's free twist** — with its members on one line through the reference
  node, the node's rotation about that line moves nothing. ccx 2.23 solved such a linear step
  on roundoff, silently wrong (4× off, probed), and an NLGEOM step stopped converging. The
  coupling is now the `*RIGID BODY` it is in ccx, with that rotation held on its ROT NODE by an
  `*EQUATION`. Exact.
* **`*SOLID SECTION, COMPOSITE` with different layers** on C3D8 / C3D8R was commented out
  (ccx has no layered solid section). Each element is now one brick per layer, and `*EQUATION`s
  keep the stack on one displacement field, as Abaqus' single element. Exact where the layer
  integration agrees (C3D8 with 3 or more section points per layer, C3D8R with 1); else
  reduced physics.
* **`*DLOAD` types ccx lacks** — VP, SP, SBF, PI, PE, edge loads other than EDNOR, a bare
  `P` on solids: ccx 2.23 stopped on them (crashed on the `P`). They are now commented out,
  warned. On axisymmetric elements, `BR` / `BZ` (radial / axial) become ccx's `BX` / `BY`;
  `BZ` used to act out of the plane.
* **More cards ccx stopped on** — `*BOUNDARY` on DOF 7 or 9 is dropped, warned, also where an
  element has the DOF. A used `*ELASTIC, TYPE=TRACTION` is commented out: ccx read it as E and
  ν, and could solve with that. A `*SURFACE` line without a face label on shells or membranes is
  both faces where only couplings use it. A blank `*SURFACE` data line (Abaqus/Explicit) is the
  model's exterior continuum faces.
* **Loads given again in a later step: every line** — a `*DLOAD` / `*DSLOAD` given again where a
  later step loads its faces from another source came back as one line where one step gave it
  two (Abaqus adds them: 1 + 1, then 1 from another surface: ccx 2, Abaqus 3), and not at all
  after a zero line or a line left out for its amplitude. Every line now comes back. Moments
  on a knot node with a `*TRANSFORM` (written in global components): one by node number in a
  later step replaced one through a node set on the same rotation, where Abaqus adds them; the
  earlier one is now given again.
* **TIME DELAY kept on loads converted to nodal forces** — the `*CLOAD` written for a
  traction, beam line load or surface-element pressure carried its amplitude without the
  delay, so ccx applied the amplitude undelayed. ccx 2.23's `*CLOAD` takes TIME DELAY
  (probed): it is kept now. A deck `*CLOAD` sharing a node DOF with another delay no longer
  stops ccx ('forcadd'); such a load is dropped, warned.
* **Static perturbation gradients over one-value temperatures** — a perturbation step's
  shell or beam gradient over base temperatures given by one value (or the reverse) was
  warned and left unsummed. A missing gradient is 0 on GRADIENT sections, as ccx 2.23 reads
  it too (probed), so the values are summed. The general step after such a step gets the
  initial temperatures back line by line: ccx's `*TEMPERATURE, OP=NEW` keeps the last
  gradient (probed).
* **Shell gradients on S4 / S4R warned** — ccx 2.23 ignores a temperature gradient through
  the thickness on S4 and S4R (probed; S3, S6, S8 and S8R read it), so their thermal bending
  was lost silently. A deck that changes one there is now warned, reduced physics.
* **`*BUCKLE` steps without a load** — a step whose loads are all zero (on an amplitude that
  is 0 at time 0, zero values, or none) has no buckling factor; ccx 2.23 prints noise of 1e9
  and more. One warning per step now says so; a zeroed card beside other loads is no longer
  warned.
* **Self-contact, contact roles and contact on shells**:
  * Under `--approximate`, a self-contact line becomes ccx's `S, S` with TYPE=SURFACE TO
    SURFACE ([APPROX]). On a strip folding onto itself it came within 0.1 % of symmetric
    node-to-surface pairs on a mild closure, and between ccx's two pair formulations on a deep one.
  * A TIED self-contact line (written as `*TIE S, S`) is left out with a warning: Abaqus rejects
    TIED self-contact, and ccx 2.23 looped on the tie until it was killed.
  * The Abaqus 2022+ names MAIN and SECONDARY are read as MASTER and SLAVE, so a `*CLEARANCE`
    or `*CONTACT PRINT` that uses them now reaches ccx (the clearance stopped ccx before).
  * Shell or membrane surfaces in finite-sliding node-to-surface pairs, or in pairs with NO
    THICKNESS, are warned (reduced physics): Abaqus ignores their thickness there, but ccx's
    expanded shells always count it.
* **`*HYPERFOAM, TEST DATA INPUT`** is commented out with a warning, like `*HYPERELASTIC`'s. ccx
  reads no test data and stopped on the card's missing coefficients.
* **Output frequency notes** — ccx writes all output of a step at one frequency. When the step's
  requests ask for different ones (a print card's FREQUENCY=100 beside preselected .frd output),
  a note now gives the frequency ccx writes.
* **Plastic `CPE4` / `CAX4`** — ccx 2.23 integrates them fully, without the selectively
  reduced volume terms of Abaqus' first-order quadrilaterals, so they lock in plastic flow and
  reach no limit load (a thick cylinder carried 1.4 times its limit pressure on any mesh; a
  bent strip 1.6 times its plastic moment on 4 elements through its depth). With a plastic
  material they are now flagged as reduced physics; `--approximate` writes `CPE8R` / `CAX8R`
  with a node at the middle of every edge (within 1.3 % of both), and a flagged plastic
  `CPE4R` / `CAX4R` the same way instead of its locking twin.
* **Hyperelastic D1 below 1e-10** — ccx 2.23 replaces it by 0.1 / μ0, a Poisson's ratio of
  0.475, whatever the deck's units: a neo-Hooke steel in Pa ran 9× too stiff in bulk (a
  cantilever deflected 0.86 of beam theory). Now warned as reduced physics, with the advice to
  rescale the units.
* **Notes** on `SECTION=RECT` beams, which ccx twists 1.19 times too stiffly on a square
  section (1.07 at a side ratio of 10), and on curved linear membranes in a geometrically
  linear step, whose near-mechanisms show as a node-to-node zigzag.
* **`*SHELL SECTION, DENSITY=` on conventional shells** — the mass per unit area was dropped
  with a note, so the modes came out up to 1.9× too high. Where mass acts, each material (each
  ply material of a composite) now gets a copy with DENSITY / t more, t the section's
  thickness, as continuum shells and membranes already did. The copy gives the added mass
  some rotary inertia, which Abaqus' section mass lacks (noted; small for thin shells). A
  varying thickness drops it with a warning. Copy names are cut to ccx's 80 characters.
* **Materials that neither conduct nor store heat in thermal steps** — ccx 2.23 gives every
  element temperature DOFs there. It stopped with no message (exit 255, a singular matrix) on
  a beam whose material had no `*CONDUCTIVITY` in a steady-state step, or also `*DENSITY 0` in
  a transient one. Where `*DENSITY` or `*SPECIFIC HEAT` is missing, it takes the value of the
  element it assembled before (probed). Such section materials, and the one made for a
  `*BEAM GENERAL SECTION`, now get `*CONDUCTIVITY 1e-30` (and `*SPECIFIC HEAT 0` where they have
  none): they carry and store no heat, as Abaqus' elements without temperature DOFs.
* **`*NGEN` arcs and skipped lines; GENERATE lines by position** — when a `LINE=C` arc's end
  nodes lie at unequal distances from its centre, Abaqus moves them radially onto one circle.
  Both now move onto their mean distance, with a warning (Abaqus' documentation does not give
  the radius); the arc was a spiral between them. An `*NGEN` line skipped for a missing end
  node or centre now counts as reduced physics. `*NSET` / `*ELSET, GENERATE` lines are read by
  position everywhere: a line with a blank first or last member is skipped (it was compacted,
  so `1, , 4` read as 1 to 4), and the planners read a negative or zero increment the way the
  set handler does.
* **Trusses at shell nodes, and the legacy `*DISTRIBUTING COUPLING`** — ccx 2.23 crashed without a
  message (exit 255) on some shell nodes a truss shares: its knot there could not turn about the
  shell normal. Where it ran, it was up to 1e-2 off. Such a truss now ends at a copy of the node,
  tied to it through a hub node with two knot beams, and matches the truss as a spring (probed).
  A `*DISTRIBUTING COUPLING` (DCOUP2D / DCOUP3D) now becomes the equations of `*COUPLING` +
  `*DISTRIBUTING`. ccx's card dropped the moments and the reference node's offset; the result
  now matches Abaqus' Verification Guide to 3 digits. A distributing coupling on membrane faces
  is written as equations too. ccx's card was 20 % off there, or transmitted nothing on M3D3.
  On plane-element edges, the weights now take each section's thickness. They had taken 1 for
  every edge: 39 % off with sections of thickness 1 and 3.
* **More `*EQUATION`s held by BCs in some steps** — two more cases no longer stop ccx 2.23
  ('dependent side of a MPC and a SPC'). In the first, each step holds one DOF of the equation
  ("crossed" holds); the BC at zero moves onto the DOF that step leaves free. In the second,
  the DOFs are held at nonzero values the equation satisfies, on one amplitude; the BC on the
  eliminated DOF goes. Both are exact (probed).
* **Where mass acts** — four planners asked it with two rules and two procedure lists. The
  StepModel now holds both: inertia (a dynamic or eigenvalue step) and weight (a GRAV,
  CENTRIF, ... load too). `*DYNAMIC TEMPERATURE-DISPLACEMENT` counts as inertia now, so a
  section's `DENSITY=` is no longer dropped there as unused.
* **Cards between two steps act in the next step** — ccx 2.23 applies a `*BOUNDARY` or `*CLOAD`
  written after a step's `*END STEP` in the next step (probed), but the planners read such cards
  five different ways, and loads or output requests there were commented out. They are now
  moved into the next step, after its procedure card, with a warning. A card after the last
  step no longer reads that step's procedure (a `*BOUNDARY, IMAGINARY` there got `LOAD CASE=2`).
* **One definition of a linear perturbation step** — the planners used three sets of
  perturbation procedures. Abaqus' list is now used everywhere: `*FREQUENCY`, `*BUCKLE`,
  `*COMPLEX FREQUENCY`, `*MODAL DYNAMIC`, `*STEADY STATE DYNAMICS`, `*RANDOM RESPONSE`,
  `*RESPONSE SPECTRUM`, `*SUBSTRUCTURE GENERATE`, `*MATRIX GENERATE`, or `*STEP, PERTURBATION`.
  A velocity BC carried over a `*RESPONSE SPECTRUM`, `*RANDOM RESPONSE` or `*MATRIX GENERATE`
  step was dropped after it (the step counted as a general one of unknown time). Its output
  requests and loads now follow the perturbation rules too.
* **`*BOUNDARY, LOAD CASE=2` cards no longer count as BCs** — the converter leaves a `*BUCKLE`
  step's buckling-mode BCs out (ccx has one set of BCs per step), but seven of its planners still
  counted them. Where they hold more than the LOAD CASE=1 cards, an OP=NEW that removes a BC was
  dropped as if the step re-specified every BC, and knot beams were added for BCs ccx never gets.
  ccx now gets the LOAD CASE=1 BCs, as the warning says.
* **`*NCOPY, POLE` projected from its pole** — the pole's node number (or its coordinates)
  was read as a `SHIFT` translation, so the copies landed elsewhere (reduced physics). Each
  copy now lies so that its old node is midway between the pole and it, as in Abaqus.
* **`*STATIC, DIRECT` with contact** — ccx's penalty contact can need a cutback where Abaqus'
  contact converges at the fixed increment, and under `DIRECT` ccx then stops ("solution seems
  to diverge"). In a model with contact pairs the step now gets automatic increments, with the
  fixed increment as the initial and the maximum one: the deck's increments wherever ccx
  converges. The corpus' Berkovich indentation deck now solves (in about 300 s, the corpus
  gate's limit).
* **`*DSFLUX`, `*SFILM` and `*SRADIATE`** — surface heat flux, film and radiation were
  commented out as having no ccx equivalent. They are now written as ccx's element-based
  `*DFLUX` / `*FILM` / `*RADIATE` on the surface's faces (`Sn` → `Sn` / `Fn` / `Rn`). They
  stay commented where ccx would act differently: an `OP=NEW` mixed with the element-based
  cards, faces another card also loads, shell faces, `*FILM PROPERTY` tables, cavity
  radiation.
* **`*MASS` on a rigid-body node in no other element** — ccx 2.23's `*FREQUENCY` stopped
  ("add_bo_st: coefficient should be 0"), e.g. on point masses carried by `*MPC BEAM`. Such a
  node now gets a massless tetrahedron that moves with the body, which changes nothing else.
* **Element types ccx lacks** — piezoelectric, thermal-electrical, infinite, acoustic and
  `JOINTC` elements were reported as "unknown to this converter", their node count guessed
  from the first line. The report now names the family, and connectivity is read with the
  right node count.
* **Follower tractions under NLGEOM** — a `TRVEC` normal to flat continuum faces, with
  `FOLLOWER=YES` and `CONSTANT RESULTANT=NO` (the defaults), now becomes a ccx face pressure
  instead of needing `--approximate`. Abaqus applies a follower traction's normal part along the
  current normal per unit current area, as ccx's NLGEOM pressure acts (probed: a cube turned
  90° by its held face, a stretched one). Shear parts, `FOLLOWER=NO` and `CONSTANT
  RESULTANT=YES` have no ccx load and still need `--approximate`. That includes the 16 corpus
  decks, which load an end face in shear. `FOLLOWER=NO` / `CONSTANT RESULTANT=YES` on a pressure
  card is no longer warned as reduced physics, since Abaqus reads them for tractions and edge
  loads only.
* **Tied contact pairs on a rigid surface** — a `*CONTACT PAIR, TIED` measured a shell slave's
  distance from its mid-surface, so a shell within `ADJUST` of the rigid master by its face was
  left to ccx's tie of its expanded faces (a cantilever strip 1.8× too soft); its half thickness
  now counts, as in Abaqus, unless `NO THICKNESS`. The tied nodes join the body in translation
  only (`PIN`), since a tied pair does not tie rotations.
* **A `*STEP` without `*END STEP`** was written inside the next step, where ccx stops, and the
  load audit and other step walkers counted the steps differently. It is now closed before the
  next `*STEP` (or at the end of the deck), with a warning.
* **`DEPENDENCIES=0`** (a plain table) gave "rows could not be parsed" and reduced physics on
  `*ELASTIC`, `*DENSITY`, `*PLASTIC` and other material cards, and left an anisotropic
  `*EXPANSION`'s shear coefficients unhalved. It is now read as a table without field variables.
* **Report fixes** — a deck loaded only by `*BOUNDARY, SUBMODEL` or `*TEMPERATURE, FILE=` no
  longer gets "applies no load"; a pressure on rigid elements that cannot be converted is a
  warned, commented-out line and reduced physics (an unreadable magnitude was dropped without a
  word); a `<name>` token no `*PARAMETER` resolves is reduced physics where it stays in model
  data; a velocity BC removed by a Riks step no longer gets a false warning in the next step; the
  velocity BC note no longer says a commented-out line was converted; output at times of a step
  ccx runs linearly is noted as written at the step end only (ccx solves it in one increment);
  `/` between two integers in `*PARAMETER` is noted (Abaqus 2023 and older floor-divide). The
  keyword reference no longer lists `*CYCLIC HARDENING`, `*NODAL THICKNESS` and `*NORMAL` as
  emitted unchanged, and lists `*MOHR COULOMB HARDENING`.
* **`--run`** — with an `-o` name not ending in `.inp` it ran ccx on `<name>.inp`, which can be
  the Abaqus deck; that is now a usage error. `--ccx NAME` / `CCX=NAME` is also looked up on
  PATH.
* **Contact forces in eigenvalue and modal steps** — ccx 2.23 segfaults on `*CONTACT PRINT`
  `CF`, `CFN` and `CFS` in `*FREQUENCY` (without PERTURBATION), `*BUCKLE`, `*MODAL DYNAMIC` and
  `*STEADY STATE DYNAMICS` steps, whatever the material, also when an earlier step's card
  carries them in. They are left out of those steps now (of every `*FREQUENCY` step), with a
  warning; an empty card ends a carried one, and the next general step gets the
  cards Abaqus carries into it again.
* **Explicit dynamics before a `*FREQUENCY` step** — the converter writes NLGEOM on an explicit
  step and again on the general steps after a `*FREQUENCY` or `*BUCKLE` step, so ccx iterates
  them: `*EL PRINT ELKE` and `*EL FILE SDV` are kept there now (they were dropped).
* **Element energies after a `*DYNAMIC` step** — ccx 2.23 adds the strain energy the model
  holds when a `*DYNAMIC` step after the first step starts to ELSE and ENER once more, and
  keeps it in later steps. A note says so where a deck asks for them there.
* **`WEIGHTING METHOD` on a distributing coupling kept as ccx's card** — ccx 2.23 accepts the
  parameter but ignores it, weighting by tributary area alone (probed). The equation form
  applies `LINEAR`, `QUADRATIC` and `CUBIC`. Where the card stays ccx's, as under NLGEOM without
  `--approximate`, such a weighting is now warned and flagged as reduced physics.
* **Shell and beam rotations in steps ccx runs nonlinearly** — without NLGEOM, ccx 2.23 still
  runs a step with a plastic, creeping, hyperelastic or user material, a contact pair, or a
  `*DYNAMIC` or coupled procedure through its nonlinear solver. There it turns its shell/beam
  rotation constraints with the finite rotation, where Abaqus keeps rotations linear. These
  constraints are the mean-rotation MPCs of non-zero rotational BCs and moments, and the knots
  (frame joints, folded shell edges, knot beams). The results drift by about theta^2 of max |u|
  (1 % at 0.1 rad), and by 0.4-1 % at a beam knot turning 0.01 rad. Held rotations are exact.
  ccx has no linear form, so such a deck is now warned and flagged as reduced physics.
* **Rigid constraints that still kept ccx's finite rotations** — in a deck written as linear
  rigid equations (a step ccx runs nonlinearly without NLGEOM), three forms kept ccx's own
  constraint, which turns with the finite rotation (2-8 % off, reduced physics). These were a
  reference node with a `*TRANSFORM`, a coupling of some translations of transformed nodes, and
  a `*KINEMATIC COUPLING` with a rotation-only line on shell/beam nodes. They are now exact
  equations: the transformed nodes' terms go through twin nodes, and the rotation-only line
  becomes rotation ties.
* **Coupling along an `ORIENTATION` with a member BC that stopped ccx** — a member BC on the
  global DOF that ccx's own coupling eliminates along a turned axis stopped ccx. Without NLGEOM,
  such a coupling is now written as its linear equations, and ccx holds both the coupling and
  the BC.
* **Invalid or incomplete source decks** — the report now names what is missing, where ccx
  used to stop with nothing explained: a section on an element set the deck never defines or
  that holds no element; elements no section covers; an element set where `*INITIAL
  CONDITIONS, TYPE=TEMPERATURE` (`VELOCITY`, `DISPLACEMENT`) takes a node set; a field that is
  not a number in a material, procedure or `*AMPLITUDE` card (a template's `#E`); elements
  whose repeated nodes leave them no area or volume; a `*PARAMETER` given as a `<name>` no
  block defines (a template's placeholder), with what is computed from it; `*INCLUDE, FILE=`.
  An assembly `*NSET` / `*ELSET` whose `INSTANCE=` names no instance kept its labels, which
  then named another instance's nodes: it is left out (warned).
* **Cards ccx 2.23 stopped or crashed on, without a warning** — each is now written in a form
  ccx runs, or warned (reduced physics):
  * `*RIGID BODY` with `ELSET` and a `PIN` / `TIE NSET`: one `NSET` of all their nodes (ccx
    takes one or the other).
  * `*COUPLING`, `*KINEMATIC` of some translations, such as `3, 3`: a rotation of the reference
    node that no coupled DOF uses crashed ccx (no message). It is held at zero, which is exact.
  * `*VISCO` without `CETOL` (fixed increments in Abaqus): `DIRECT, CETOL=1.E30`.
  * An element `*SURFACE` line without a face label: the exterior faces of its continuum
    elements, as in Abaqus. On shells and beams the line is left out (warned).
  * `*SOLID SECTION, COMPOSITE`: plies of one material in the same directions become a plain
    solid section. Other layups are commented out (warned); ccx stopped on them.
  * `*BOUNDARY` on DOF 10 or 12–30: dropped like DOFs 7–9 (warned where an element has it).
  * An `*ORIENTATION` without axes (`1., 0., 0.`), or `OFFSET TO NODES`: written as the global
    axes where only direction-free sections use it. Otherwise it is commented out (warned).
  * `*ELASTIC, TYPE=SHEAR` and `*FRICTION, USER` are commented out (warned). The user
    friction's first property had been written as mu.
* **Indented keyword lines** — Abaqus reads `  *NODE` as `*NODE`; the converter read a keyword
  `*NODE` with no CalculiX equivalent, so an indented `*INSTANCE` left a deck without its mesh.
* **Abbreviations** — Abaqus reads any unambiguous abbreviation of a keyword, parameter or
  value (`*INITIAL CONDITION`, `VAR=PRESELECT`, `F=1`, `TYPE=ISO`, `SYSTEM=C`). The converter
  knew a few; it now reads them all in full against the Abaqus keyword list and the parameters
  of the keywords it converts, with a note. An ambiguous one is warned and kept as written.
  `*AMPLITUDE, VALUE=ABSOLUTE` whose every load / BC has magnitude 1 is exact in ccx (magnitude
  x amplitude) and is no longer reduced physics.
* **Self-contact** — a `*CONTACT PAIR` line with one surface, or the same surface twice, passed
  through, and ccx 2.23 stopped on the first ("allocont: master surface"). ccx's own `S, S`
  runs, but is not Abaqus' two-way self-contact (probed: half the contact force of a strip
  folding onto itself), so the line is commented out with a warning (reduced physics).
* **`*HYPERFOAM`, N=1** — ccx 2.23 gives an N=1 hyperfoam (the default) no stiffness: it
  stopped without a message in static and buckling steps and returned frequencies of 0. It is
  now written as N=2 with mu1 halved in both terms (the same energy), which ccx solves (closed
  form, beam frequency and buckling load). Warned: unequal exponents (N >= 2) in eigenvalue
  steps, where ccx's tangent puts frequencies and buckling loads 9-14 % low (reduced physics),
  and static or `*VISCO` steps, which ccx 2.23 did not converge beyond one element.
* **Overclosed contact before a `*FREQUENCY` step** — overclosures against shell faces
  (thickness and `OFFSET`, where Abaqus counts them), from slave shells and against rigid
  surfaces are now detected. Under `--approximate`, a `*FREQUENCY` step after a linear base
  that only an overclosure stresses gets `PERTURBATION` ([APPROX]: much closer to Abaqus than
  the plain step, which drops contact).
* **Rotated instances** — a part's `*EQUATION`, kinematic couplings of some DOFs and SPRING1 /
  SPRING2 kept the part's DOF numbers in a turned `*INSTANCE`, so they acted along the wrong
  directions. Abaqus turns them with the instance. Each equation term now becomes terms on the
  global DOFs. A coupling or spring takes the global DOFs its turned axes lie along, or else the
  instance's axes as `ORIENTATION=`.
* **Section options in parts** — `*TRANSVERSE SHEAR STIFFNESS`, `*SECTION POINTS`, `*HOURGLASS
  STIFFNESS` and a part section's other options went out once, apart from their section. They
  were judged without it, e.g. reduced physics after a beam written as U1, where a flat deck
  gets a note. They now go with each instance's copy of the section.
* **Static perturbation and `*BUCKLE` leftovers** — a static perturbation step's traction or
  other load written as nodal forces, on what a base-state load on an amplitude loads, was
  dropped (warned); it is now added to the base forces at the amplitude's end value, without
  the amplitude. `*BUCKLE` has no time period either, so Abaqus applies its loads and BCs at
  their amplitude's time-0 value; ccx 2.23 ignored the amplitude (the full load). They are now
  scaled by it, and a zero there is warned. Shell temperature gradients in a static
  perturbation step add to the base state's where it has the same kind of line (warned before);
  other mixes stay warned.
* **`*SHELL SECTION, DENSITY=` on continuum shells** — the mass per unit area was dropped
  (silently on a plain section), so the modes came out about 2× too high. Where mass acts,
  each material now gets a copy with DENSITY / t more, t the mesh's thickness, as membranes
  already did; plies too. Where the thickness varies the parameter is dropped with a warning.
* **Mass scaling in transient coupled temperature-displacement steps** — the material made
  from `*BEAM GENERAL SECTION, DENSITY=` and the point masses that carry a rigid body's
  `*ROTARY INERTIA` kept their full mass (the stars a net negative mass at the body's node).
  They are now scaled like the deck's own masses.
* **Mesh generation with blank fields** — `*ELGEN`, `*NGEN` and `*NFILL` dropped blank
  (default) fields and read the rest one place early: `*ELGEN` line `1, 4, , , 3, 10, 10` gave 40
  wrong elements instead of 12, and an `*NGEN` arc with a blank increment generated nothing.
  Fields are now read by position with Abaqus' defaults. `*NGEN` also takes the extra point
  from its coordinates (fields 5–7, in the `SYSTEM=` frame) when no node is given, and the arc
  normal from fields 8–10 (5–7 were read as the normal). `*NFILL` takes the default increment
  1 (the line was skipped) and puts a bounding node without coordinates at the origin, as
  Abaqus does. `*NCOPY, MULTIPLE` with a rotation now translates once, then turns each copy
  (copy k was translated k times). A `*NSET` / `*ELSET, GENERATE` line that is not numbers is
  now warned and reduced physics (the set came out empty without a word).
* **Distributing couplings move their reference node** — ccx 2.23's `*COUPLING` + `*DISTRIBUTING`
  only spreads the reference node's loads over the surface: a BC on the node moved nothing, the
  node printed U = 0 and a beam on it hung free; a card without DOF lines (Abaqus: all DOFs)
  spread no moment either. Abaqus moves the node with the coupling nodes' weighted mean motion
  and turns it with their weighted least-squares rotation. The coupling is now written as
  `*EQUATION`s of that constraint, on node surfaces too (ccx stopped), with Abaqus' weights:
  tributary areas, a node surface's areas, `WEIGHTING METHOD` (ignored before) and an `INFLUENCE
  RADIUS` (each facet's areas scaled by the part of it within). Under NLGEOM, where the
  equations would turn with the surface, the coupling stays ccx's card unless `--approximate`,
  warned.
* **A truss numbered below the beams at a node** — ccx 2.23 gives a node its lowest-numbered
  beam or truss element's expansion, so such a node had no rotations: ccx held the beams'
  rotation there (a cantilever 93 % stiffer) and stopped on a rotational BC, moment or equation
  there. The truss now ends at a tied copy of the node, which gets a knot beam; a beam's
  pre-tension cut node that only trusses share keeps its rotation tie the same way.
* **`S4R` shells** — ccx 2.23 expands an `S4R` into one `C3D8R` brick integrated at a single
  point on the mid-surface, so its bending is resisted only by the hourglass stiffness ccx adds
  to that brick, not by the section, in every step: a simply supported plate of a/t 100
  deflected 1/50 of the plate solution, vibrated 7× and buckled 97× higher; at a/t 10 it
  deflected 3.7×. A plain `S4R` is now reduced physics, with a warning; `--approximate` writes
  it as `S4` (within 2.5 % on those plates).
* **One-point plane, membrane and beam elements** — ccx 2.23 expands `CPS4R`, `CPE4R`, `CAX4R`,
  `M3D4R` and its own `B31R` into one `C3D8R` brick too, and the hourglass stiffness it adds to
  that brick, all that resists the element's bending, grows with the square of the element's
  size over the brick's depth: the plane thickness; 1 in the deck's length unit for plane
  strain (a `CPE4R` cantilever deflected 1.02× beam theory in m, 0.06× in mm); the 2° sector,
  0.035 r, for axisymmetry. Where the median ratio exceeds 3 (1.5 with a plastic material, as
  that stiffness does not yield: a limit load +24 % on 4 elements through the depth), and on
  every `M3D4R` (a stretched membrane under pressure: 0.16 of its deflection) and `B31R` (0.6–7×
  beam theory), they are now reduced physics with a warning; `--approximate` writes `CPS4`,
  `CPE4`, `CAX4`, `M3D4`, `B31`. A note where most `C3D8R` bricks are over 3 times as wide as
  thick, which bend too stiffly in ccx.
* **`--approximate` writes a coarse `S4R` as `S8R`** — where an element is more than 6
  thicknesses wide, with midside nodes as on composite shells: `S4` locks there (8 × 8 elements,
  a/t 100: 26 % in bending, a buckling load 37 % high), `S8R` is within 2 %.
* **Numbers longer than 20 characters** — ccx 2.23 reads only a field's first 20 characters, so
  a longer number in the deck (or a `*PARAMETER` value) stopped it (`-5.148903517857142e-05`:
  "*ERROR reading *CLOAD") or was read as another number (`2.500000000000000000e-1` as 2.5).
  Such numbers are now written to 12 significant digits, with a note.
* **Steps ccx cannot run: Riks and complex frequency** — a `*STATIC, RIKS` step without
  `--approximate` had only its procedure commented out, and ccx repeated the previous step's
  procedure (after a static step a load-controlled `*STATIC`) without a word; a `*COMPLEX
  FREQUENCY` step, whose damped modes ccx does not compute (it takes only `CORIOLIS` or
  `FLUTTER`), stopped ccx at input. Both now get `*NO ANALYSIS`, where ccx stops after the
  steps before it, with the step's other cards as comments (warned, reduced physics).
* **`*MODAL DYNAMIC` increments** — ccx stopped such a step at 100 increments (or its `INC=`),
  where Abaqus runs every increment of the step's period: `INC=` is now written.
* **A `*FREQUENCY` step's own loads** — Abaqus ignores them; ccx carried them into the next
  general step and took them off over it (its first increment 7.5 % of the motion off under
  NLGEOM). They are now commented out.
* **Print cards after modal and steady-state dynamics** — the empty `*NODE PRINT`, `*EL PRINT`
  or `*CONTACT PRINT` written in such a step of a plastic model (ccx 2.23 segfaults on what it
  would carry there) also ended the request for the later general steps, which Abaqus prints:
  the next general step now gets the cards again.
* **Other steps ccx cannot run** — a step of an Abaqus procedure ccx lacks (`*GEOSTATIC`,
  `*SOILS`, `*MATRIX GENERATE`, `*RANDOM RESPONSE`, `*RESPONSE SPECTRUM`, `*DIRECT CYCLIC`,
  `*FATIGUE`, `*DYNAMIC TEMPERATURE-DISPLACEMENT`, `*COUPLED THERMAL-ELECTRICAL`, ...) was left
  without a procedure, and ccx ran it as the previous step's (a `*SOILS` step's loads in a
  load-controlled `*STATIC`) without a word. Such steps now get `*NO ANALYSIS` too (warned,
  reduced physics). The load audit skips the steps after one, which ccx never reaches.
  ccx 2.23 segfaults at `*NO ANALYSIS` in a model with a plastic, creeping, Mohr-Coulomb,
  deformation-plasticity or user material (also at Riks and complex frequency steps): there a
  first step is left without a procedure, where ccx stops all the same, and a later one ends the
  deck, so ccx runs the steps before it and finishes.
* **Print cards of perturbation steps** — ccx carried a perturbation step's own `*NODE PRINT`,
  `*EL PRINT` or `*CONTACT PRINT` into the next general step, where Abaqus prints the last
  general step's requests. That step now gets those cards again, or an empty card ending them.
* **Face loads of different sources across steps** — Abaqus adds a later step's `*DLOAD` /
  `*DSLOAD` to an earlier one on the same faces when it comes from another surface, element set
  or card; ccx 2.23 keeps one value per face and the later line replaced it (a tip pressure of
  1, then 2 from another surface: ccx 2, Abaqus 3). The earlier load is now given again in that
  step (also `BX` / `BY` / `BZ`). On another amplitude than the later line's this is
  impossible (ccx stops), so it is warned (reduced physics). `*DSLOAD, IMAGINARY` →
  `LOAD CASE=2`, as on `*DLOAD` (it acted in phase).
* **Concentrated loads of different sources across steps; load amplitudes** — the same for
  `*CLOAD`: a node loaded through a node set and later by its number (or another set) carries
  both in Abaqus, ccx kept the later line (-2 for -3); the earlier line is now given again. A
  load on a step-time amplitude given again (also after another card's `OP=NEW`) gets the value
  it ended with and no amplitude: ccx started it over, or stopped on two amplitudes on one face.
  Load cards of one step with the same `AMPLITUDE` and `TIME DELAY` become one; a line on a face
  or node DOF that an earlier card of the step loads on another amplitude is left out, warned
  (ccx stopped on both).
* **Element output in steps ccx 2.23 runs linearly** — `*EL FILE SDV` segfaulted ccx in a
  `*VISCO` step of an elastic material and in a Riks step under `--approximate`; both are
  dropped there now, as in a linear `*STATIC` step. A `*FREQUENCY` or `*BUCKLE` step makes ccx
  run the next `*STATIC` step linearly even after a `*DYNAMIC`, heat transfer or coupled step,
  where `*EL PRINT ELKE` and `*EL FILE SDV` segfaulted it; they are dropped there too. Without
  such a step in between, SDV is now kept in a static step after those steps (it was dropped).
* **`*EL PRINT ELKE` after a `*FREQUENCY` step** — ccx turns ELKE off for every later step;
  the first later step that carries the request now gets its cards written again.
* **`*CONTACT PRINT`** — passed through before; now its variables are checked against ccx
  2.23's. `CFN`, `CFS` and `CFT` (ccx's `CF`) get one card per face-to-face contact pair with
  its `SLAVE` and `MASTER` (ccx stopped without them and segfaults on a node-to-surface pair).
  Other Abaqus variables and `NSET`, `SUMMARY`, `TOTALS` are dropped with a note; `FREQUENCY`
  joins the step's output control; without a ccx contact pair the card is dropped.
* **Input left out without a word** — the report now says where the conversion leaves input
  out: a `*PART` that no `*INSTANCE` names (a note; a warning in a deck without any instance,
  which came out empty: about 100 corpus decks, mostly include fragments); a composite ply line
  without a thickness or a material (a warning; one without a material is no longer written);
  the section parameters the continuum-shell, U1, expanded general-beam and `--approximate`
  I-beam cards do not carry; `EIGENSOLVER=`; and, warned, `*NGEN`, `*NFILL`, `*TIME POINTS`,
  `*DSLOAD` and tied `*CONTACT PAIR` lines Abaqus would reject, nameless `*NSET` / `*ELSET`
  cards and connector elements without nodes.
* **Distributing coupling with an `INFLUENCE RADIUS`** — ccx 2.23 ignores the radius, so the
  coupling spread over the whole surface (reduced physics). It is now written on the facets
  with a node within the radius, or on the nearest facet where it holds none.
* **Contact pairs that are commented out** — a `*CONTACT PAIR` on an analytical surface the
  converter does not mesh no longer counts as a step ccx runs nonlinearly, so the deck's rigid
  constraints stay ccx's own. Either form is exact; only the notes change.
* **Large `*BUCKLE` factors** — under a unit load the factor is the buckling load itself, and
  ccx 2.23, which shift-inverts about 1, returns it the less accurately the larger it is and the
  more slender the model (probed, 1 % off: near 500 on a plate 1000 times as wide as thick, 1e7
  at 100 times, 1e9 on a beam). The `*BUCKLE` note now says so; a load just below the lowest
  buckling load keeps the factors exact. No digest warning: where the error reaches 1 % depends
  on the model too much for one threshold.
* **Upgraded beams between kinematically coupled nodes** — the midside node the converter adds
  to a B31 under `SECTION=CIRC`, `PIPE` or `BOX` stayed out of a kinematic coupling (or a
  node surface or set) holding both its end nodes, so the beam sagged between them where
  Abaqus' linear beam moves rigidly (probed: 5.4 % of the motion under gravity, with the
  translations coupled). It now joins, as it joins a `*RIGID BODY`; a distributing coupling
  keeps its nodes (it would load mid-span). The midside node now also joins node-based
  surfaces and `*SUBMODEL` sets, as a shell's new edge nodes do, and stays out of `UNSORTED`
  sets.
* **Membrane `DENSITY=` in a deck with a `*COUPLED THERMAL-ELECTRICAL` step** — the section mass
  was left out (warned) to keep the heat capacity of a step that ccx does not run (the step is
  commented out); it is now carried by the material copy, as in other decks.
* **`*BOUNDARY` line with a last DOF that is not a number** (`TOP, 3, X, 0.01`) — passed through
  as before, on which ccx stops; it is now warned, and no planner reads it as a BC on DOF 3
  (three of seven did).
* **`*ROTARY INERTIA` on a turned `*ORIENTATION`** — an orientation with an additional rotation
  line was refused (the rigid body's rotary inertia not converted, reduced physics). Its turned
  axes are the inertia axes, as for connectors and coupling orientations, and are now used.
* **`*KINEMATIC COUPLING, REF NODE=<set>` of several nodes** — Abaqus requires the set to hold one
  node; the converter took the first without a word. It is now warned, as on `*RIGID BODY`.
* **Analytic amplitudes in `*MODAL DYNAMIC` steps** — a `PERIODIC`, `MODULATED` or `DECAY`
  amplitude was tabulated over the general steps' time only: a modal dynamic step read it past
  the table's end (constant there), and a deck with no general step lost it (ccx stopped). The
  table now covers each modal dynamic step's time period too.
* **More ccx 2.23 segfaults with a plastic or creeping material** — contact output (CDIS, CSTR,
  CELS) in modal and steady-state dynamics steps, own or carried in, is now left out there with
  a warning. `*FREQUENCY` steps after an NLGEOM step no longer report their FOLLOWER options
  and tractions as reduced physics: Abaqus ignores their loads.
* **Pre-tension of a truss or beam cut** — ccx 2.23 deletes the element a `*PRE-TENSION
  SECTION, ELEMENT=` names and ties its end nodes along the normal only: the closure of a held
  bolt missed the element's own length (33 % low for a bolt of two elements), no shear, moment
  or torque crossed the cut, and ccx stopped on trusses, quadratic and circular-section beams.
  Abaqus puts the cut at the element's last node and keeps the element. The element now ends
  at a copy of that node, displaced from it by the pre-tension node's DOF 1 along the normal,
  with the node's rotations.
* **Static perturbation values on what the base state loads** — Abaqus reads a `*STEP,
  PERTURBATION` `*STATIC` step's load and BC values as changes of the base state's; ccx 2.23
  took a value on a node DOF, face or body load that the base state also loads as its new
  value (a cube: 0.022 off a response of 0.037). Such lines now get the base value added.
  `OP=NEW` on a `*CLOAD`, `*DLOAD` or `*DSLOAD` there removes nothing in Abaqus, so it is
  dropped (ccx removed the base state's loads). A BC on a DOF the base state leaves free, a
  released base BC and a value on an amplitude cannot be added up: warned (reduced physics).
* **Eigenvalue steps with contact or hyperelastic temperatures** — ccx 2.23 leaves contact
  out of `*BUCKLE` altogether, with or without `PERTURBATION` (probed: a column braced by
  touching blocks kept its free factors): now warned (reduced physics). An initial
  overclosure stresses the base state (Abaqus resolves it as an interference fit in the first
  general step; probed alike in ccx): a `*FREQUENCY` step after it no longer gets
  `PERTURBATION` as an unstressed one. Exceptions: `ADJUST`, which moves the nodes
  strain-free (a node set: its nodes), and a `*CLEARANCE` that sets a gap.
  Temperature-dependent `*HYPERELASTIC` / `*HYPERFOAM` coefficients now count as heated
  materials there, as `*ELASTIC` rows do. Contact pairs on unconverted analytical surfaces no
  longer count as contact.
* **Static perturbation temperatures, amplitudes and zero BCs** — in a `*STEP, PERTURBATION`
  `*STATIC` step a `*TEMPERATURE` is a change of the base state's temperatures (the initial
  ones before any general step), and an amplitude counts at its value at time 0 (Abaqus); ccx
  2.23 read the temperature as the new one and applied the amplitude's end value. The base
  temperature is now added, and values on an amplitude are scaled by its time-0 value; one the
  converter cannot evaluate there is warned. A zero BC on a DOF the base state leaves free holds
  its base-state value: written as `*BOUNDARY, FIXED` where ccx then holds that value (right
  after the general step or `*FREQUENCY` steps; translations of nodes without `*TRANSFORM`),
  warned elsewhere. Temperatures there with temperature-dependent materials are warned.
* **New midside nodes of `*TRANSFORM` edges in ramped steps** — where Abaqus ramps a BC
  without AMPLITUDE and ccx would step it (`*DYNAMIC` after an earlier step, say), the midside
  node's lines were stepped and flagged as reduced physics: its own BCs before the step went
  unseen (2e-3 off at a free node). They now ramp with its end nodes'.
* **Velocity and acceleration BCs on new midside nodes of curved edges** — under a cylindrical
  or spherical `*TRANSFORM` they are now interpolated in global components, as displacements
  are since 1.4.0 (3.5e-4 off at the node before), and no second, approximated line reaches
  that node.
* **Two rotational BCs on a shell node with a `*TRANSFORM`** — where neither held axis nor the
  free one is the shell normal, ccx 2.23 also holds the free rotation's in-plane part (a second
  mean-rotation MPC; probed: 30 % off on a cylindrical panel). Now warned, reduced physics.
* **12 significant digits** — the constants of `*ELASTIC, TYPE=LAMINA`, rows interpolated at
  field variable 0 (`DEPENDENCIES=`), the `--approximate` I-beam's `RECT` and the `*FRICTION`
  coefficient were written to 6 (up to 5e-6 off); they now get 12, as every other real.
* **`*EQUATION` terms that ccx holds twice** — ccx 2.23 mis-assembles an equation that holds a
  DOF twice: the constraint holds, the answer does not. A deck's own equation with a term
  written twice (78 % of max |u| off), or with several local translations of a transformed
  node whose axes share a global component (108-130 %), passed through; under NLGEOM ccx did
  not converge. Repeated terms are now summed, and such local terms go through the node's
  untransformed twin, as `*MPC PIN` does since 1.4.0 (exact, also under NLGEOM).
* **Connectors between two transformed nodes** — where a connector's equation kept several
  local translations of one node that ccx expands into a repeated DOF, a linear step could be
  29-40 % of max |u| off without a message (where ccx's own substitution does not merge them:
  the other node's axes keep a global one), and under NLGEOM or explicit dynamics the connector
  was commented out. Such a node now goes through its twin (exact, linear, NLGEOM and explicit).
* **Reaction force at a rigid body's own node** — ccx 2.23 prints the reaction at a `*RIGID
  BODY` reference node that is one of the body's nodes as zero (its own elements' forces
  alone), e.g. at an indenter whose reference node is a node of its mesh. Such a body now gets
  a free reference node at the same place, which takes the reference point's BCs, loads and
  output.
* **`Converter.convert` closes an unterminated `*STEP` as `read_blocks` does** — with the same
  warning, for a caller that builds its blocks itself. Such blocks were written with the next
  step inside the open one, where ccx stops. Decks read from a file are unchanged.
* **Converter crashes on valid decks** — on shells or beams, a general step after a static
  perturbation step that follows another perturbation step with BCs of its own (the general
  step's redundant `*BOUNDARY, OP=NEW` is now left out); a contact pair whose master face is
  collapsed to a triangle (an S4 or C3D8 given a node twice) in a deck with a `*FREQUENCY`
  step; `*NODE, INP=` (INPUT abbreviated) in an included file whose data file sits beside it.
  An error reading a deck now exits 4 with the conversion-failed message, not a traceback.
* **Malformed input reported instead of crashing the converter** — `*NSET, ELSET` without a
  value; a U1 beam on an undefined node; a kinematic coupling of 2-D members along an
  `ORIENTATION` axis normal to their plane (warned: it couples nothing there); `*NFILL, BIAS`
  below 1 on many intervals; a distributing coupling in a deck without nodes; a `*PARAMETER`
  nested too deep for Python's parser. A `*PARAMETER` string format over 100000 characters
  wide, and `round(x, -n)` with a huge n, could exhaust the memory: refused / bounded.
* **`*STEP, NLGEOM=NO` after an NLGEOM step** — Abaqus keeps NLGEOM on once a step has
  switched it on; ccx ran such a step geometrically linear (a cantilever's tip 8.13 against
  5.05, without a message; with plasticity ccx segfaulted). It is now written `NLGEOM`, with
  a note.
* **No false "ccx segfaults" after an NLGEOM step** — a plastic or creeping model's `*STATIC`
  step after a `*FREQUENCY` step was warned as segfaulting, and flagged reduced physics, also
  where NLGEOM carries on into it in ccx from an earlier step, which ccx solves.
* **Rigid constraints in more steps ccx iterates** — without NLGEOM, ccx turns its RIGID MPCs
  with the finite rotation also in a `*STATIC` step after a heat transfer, dynamic or
  (un)coupled step, with a `*DEFORMATION PLASTICITY` material, and in an explicit step with
  `NLGEOM=NO` (7 % off at 0.3 rad after a heat transfer step, 25 % at 0.5 rad in an explicit
  one, without a warning). Rigid bodies and couplings are now the linear `*EQUATION`s Abaqus
  solves there (exact). One rule now says which steps ccx iterates; after an `*UNCOUPLED
  TEMPERATURE-DISPLACEMENT` step it also keeps `*EL PRINT ELKE`, which was dropped as for a
  linear step.
* **Explicit steps with `NLGEOM=NO`** are geometrically linear in Abaqus/Explicit and in ccx
  (probed), and no longer count as NLGEOM steps: links, couplings and twists get their linear
  forms there.

## 1.4.0 (October 2026)

Steps as ccx 2.23 reads them: `OP=NEW` on loads and boundary conditions; buckling and frequency
steps with their preloads, prescribed displacements, base-state temperatures and contact; modal
and static perturbation steps, and the general steps after them. Rigid bodies and kinematic
couplings as linear equations wherever ccx would turn them with the finite rotation, and
couplings' `ORIENTATION`, `INFLUENCE RADIUS` and several reference nodes. Output requests ccx
2.23 stops or crashes on kept out; `*INCLUDE` read as text, blank fields and blank-free parameter
names read as Abaqus reads them; a `--run` judge that counts a step that solved nothing as
unsolved, and a warning where ccx's `*BUCKLE` misses the lowest factors; and the fixes of a
second whole-file code review. Corpus on ccx 2.23: 232 decks gated, 188 solving their own
physics.

* **Member BCs of a coupling along an `ORIENTATION=`** — where a kinematic coupling ties only
  some local translations, the converter judged its members' BCs by the global DOF numbers.
  A BC the coupling does not hold was taken off as implied (0.1-0.2 of max |u| off), and ccx
  stopped on BCs and `*EQUATION`s on the global DOF it eliminates. Those are now judged along
  the coupled axes. A BC that the coupled axes only partly cover stays, with a warning: Abaqus
  does not document which global DOF it eliminates there.
* **Coupling `REF NODE=` a set of several nodes** — Abaqus couples each reference node to the
  surface nodes within its own `INFLUENCE RADIUS`; the converter coupled the first only. Each
  now gets its own coupling. A kinematic coupling without a radius, or whose spheres share a
  node, keeps the first reference node, with a warning (reduced physics).
* **`*EL PRINT ELKE` where ccx 2.23 segfaults** — ccx crashes computing element kinetic
  energies in a `*BUCKLE` step and in a `*STATIC` or `*VISCO` step it runs linearly (probed).
  The converter now drops `ELKE` there, with a note: such a step has no kinetic energy. ccx
  carries `*EL PRINT` into later steps, so the cards are written again without `ELKE` in such a
  step, and with it in the next step where it runs. `*CONTACT PRINT CELS` (contact energy) in a
  later step now also gets `ENER` in step 1, so ccx no longer stops on it in a nonlinear run.
* **Rigid constraints in the other steps ccx runs nonlinear** — ccx 2.23 also turns the RIGID
  MPCs of `*RIGID BODY` and kinematic couplings with the finite rotation without NLGEOM in a
  coupled temperature-displacement step and in a `*STATIC` (a perturbation one too) or `*VISCO`
  step of a model with a plastic, creeping, hyperelastic or user material (used or not) or a
  contact pair: a 0.36 rad tip turn was 7 % off the linear answer. There too they are now the
  linear `*EQUATION`s Abaqus solves (exact), as in a linear `*DYNAMIC` step. A kept BC on a
  rotation that a rigid constraint ties is now flagged as reduced physics.
* **An `*EQUATION` held by BCs in some steps only** — where a step's BCs hold every DOF of an
  equation (both tied DOFs held in a `*FREQUENCY` step, say), ccx stopped ("`*ERROR in
  cascade`": a BC on the equation's dependent DOF), while Abaqus solves it. The BC on that DOF
  now goes in the steps whose BCs hold the equation's other DOFs at zero, so the equation holds
  it there, and the steps after keep the tie. Nonzero values stay as they were, warned.
* **General steps after linear perturbation steps** — NLGEOM written on a perturbation step
  switched NLGEOM on for the general steps after it (ccx then ran them nonlinear), kept ccx's
  nonlinear `*RIGID BODY` in a `*DYNAMIC` deck (7 % off) and gave an Abaqus UMAT the
  large-strain interface; Abaqus keeps it in that step, and the converter drops it there
  where the base state is linear.
  ccx 2.23 counts a `*MODAL DYNAMIC` step's time in the total time, so a later step read a
  `TIME=TOTAL TIME` amplitude late (at 2.5 for 2.0); such steps now use a copy shifted by that
  time. With a plastic or creeping material ccx segfaults in a `*BUCKLE` step, and in a
  `*STATIC` or `*VISCO` step without NLGEOM after `*FREQUENCY`: now warned (reduced physics).
  It also segfaulted on the element output and RF of modal and steady-state dynamics steps,
  which are now left out there, with a warning.
* **Coupling `INFLUENCE RADIUS=`** — ccx 2.23 ignores the parameter and coupled the whole
  surface. Abaqus couples the nodes of a node surface within the radius of the reference node,
  and every node of each element face the radius reaches; if it reaches none, those of the
  nearest face. A kinematic coupling now gets a node surface of those nodes (its linear
  equations in a `*DYNAMIC` deck cover only them); a node surface with no node within the
  radius is commented out, with a warning. A distributing coupling keeps its surface, warned
  where the radius leaves nodes out.
* **Coupled rotations along a coupling `ORIENTATION=`** — the rotations of knotted shell and
  beam members were tied about the global axes where only some rotations are coupled (1.6 %
  off a model turned into the orientation's axes). They are now tied about the orientation's
  axes; an orientation whose axes are not known, or NLGEOM (Abaqus turns the axes with the
  reference node), leaves them free, with a warning (`--approximate` ties them about the
  initial axes under NLGEOM).
* **Blank data fields read as 0, in place** — Abaqus reads a blank field as 0; the converter
  dropped it and read the later fields one place early. An `*ORIENTATION` line
  `0., 1., , -1., 0., 0.` made ccx exit, others gave other axes. A blank `*TRANSFORM` field left
  the node's axes unknown, so its moments on a ccx knot acted about the global axes.
  `*INITIAL CONDITIONS, TYPE=STRESS / PLASTIC STRAIN / SOLUTION`: `1, 100., , 50.` gave syy = 50,
  and the CAE line `Set-1, , , , , 20` gave SDV 1 = 20 instead of SDV 5.
* **Blank fields in moved or turned instances** — the assembly flattener dropped them too: a
  part's `*ORIENTATION` (or orientation `*DISTRIBUTION`) line `1., , , , 1.,`, a `*TRANSFORM`,
  a `*NORMAL`, a `*PRE-TENSION SECTION` normal and a beam's n1 line stayed in the part's axes,
  and a blank in the instance's own translation or rotation line left the part unmoved or
  unturned. `--approximate`'s RECT for an I-beam wrote n1 `0., , -1.` as `0., -1.` and
  commented out a profile with a blank first field.
* **Initial temperatures on several cards** — the line that gives the nodes no
  `*INITIAL CONDITIONS, TYPE=TEMPERATURE` card lists their Abaqus default, 0, was written on
  every card, so each card set the earlier cards' nodes back to 0 (CAE writes one card per
  field). It now goes on the first card only.
* **Composite ply angles** — an angle with a Fortran exponent (`4.5D1`) was read as an
  orientation name, and ccx stopped. A ply on an orientation named INF crashed the converter,
  one named NAN got `nan` axes. Plies on an orientation whose axes the converter cannot form
  (OFFSET TO NODES, unresolved nodes) were turned from the global axes without a word; they now
  name it unturned, with a warning and reduced physics. The commented-out orientation itself is
  now warned as reduced physics where a card that names it stops ccx (a note before).
* **`*FREQUENCY` at the base state's temperatures** — Abaqus evaluates a frequency step's
  materials at the base temperatures; ccx 2.23's plain `*FREQUENCY` uses the initial ones
  (probed: a column whose E halves when heated kept its cold frequencies). After linear steps
  that only heat the model, the converter now writes `*STEP, PERTURBATION`, which is exact
  there. Where the base state also holds a preload, a prescribed displacement or thermal
  expansion, no ccx form is exact: warned and flagged as reduced physics. `PERTURBATION` is
  no longer kept for temperatures of temperature-independent materials, or for `*FIELD`.
  Before a modal or steady-state dynamics step, which refuses perturbation eigenmodes, the
  deck's own `PERTURBATION` is dropped (warned, reduced physics): ccx stopped there.
* **`*FREQUENCY` with contact** — ccx 2.23's plain `*FREQUENCY` leaves contact pairs out
  altogether, even surfaces that touch at the start (probed: a column resting against a fixed
  plate kept its free frequencies); Abaqus keeps the base state's contact status. As the first
  step, or after linear steps that leave the model unstressed, the converter now writes
  `*STEP, PERTURBATION`, which is exact there; after a preload it warns (reduced physics). After
  linear steps, a deck's `PERTURBATION`, which adds the preload's stress stiffness Abaqus leaves
  out, is now dropped for hyperelastic materials, gaps, nonlinear springs and `*MODEL CHANGE`
  (ccx's plain step keeps their base state; probed), user materials, and damage or concrete,
  which ccx does not have.
* **Eigenmodes read per `*FREQUENCY` step** — `STORAGE=YES`, and dropping `PERTURBATION`
  before a modal or steady-state dynamics or complex frequency step, now apply only to the
  frequency step that step reads (the last one before it); the others keep their prestress.
* **Rotational BCs on new midside nodes with a `*TRANSFORM`** — the midside node the
  converter adds to an upgraded beam (B31 under `SECTION=CIRC`, `PIPE`, `BOX`) or composite
  shell edge (S4 → S8R) takes its end nodes' BCs. Its rotations stayed in local components
  where the end nodes' took the global form, which ccx got wrong (21-37 % off). The midside
  node is now converted as its end nodes are.
* **New midside nodes on curved edges under a cylindrical or spherical `*TRANSFORM`** — the
  midside node took the average of its end nodes' local BC values, but its local axes differ
  from theirs (4-8 % off at the node). The prescribed vectors are now averaged in global
  components and written in the node's own axes. Where the ends hold only some local DOFs
  and their free directions reach the node's, no exact form exists: warned, reduced physics.
* **Rotational BCs on `*TRANSFORM` nodes in ramped steps** — where Abaqus ramps a displacement
  BC without AMPLITUDE and ccx would step it (implicit `*DYNAMIC`, `*VISCO`, transient coupled
  steps, `*STEP, AMPLITUDE=STEP`), a rotational BC on a transformed knot or kinematic reference
  node was left out, for a velocity BC's reason. It is now written in global components under
  ccx's step ramp. In an explicit step, such a BC on rotations at rest takes the zero value
  Abaqus/Explicit gives it, so one holding all three is kept instead of left out.
* **Shell `OFFSET` compared as a number** — `OFFSET=0.` beside a section without OFFSET (or
  `SPOS` beside `0.5`) counted as another section, so the converter predicted a ccx knot that
  ccx does not make. A rotational BC on such a node with a `*TRANSFORM` was then written in
  global components, which ccx read in the local axes: the plate turned the other way.
* **`*INCLUDE` inserts the file's text** — as in Abaqus, an included file now continues the
  input where its `*INCLUDE` stands; each file was parsed on its own. So a file of data lines
  (`*NODE` / `*INCLUDE, INPUT=nodes.inp`) no longer loses them all, a `*PARAMETER` from an
  included file now holds in the including file (the raw `<name>` was written), and a file
  included twice (two parts sharing a mesh file) is no longer skipped as an include cycle.
  A relative `INPUT=` name resolves against the job directory first, then the including
  file's. A `<name>` no `*PARAMETER` defines is warned, and data lines before the first
  keyword get one warning, not one each.
* **Two output intervals in one step** — time-based output controls of one step that share no
  spacing (`*OUTPUT, FIELD, TIME INTERVAL=0.3` beside `TIME INTERVAL=0.2`, `NUMBER INTERVAL=20`
  beside `TIME INTERVAL=0.03`, `TIME POINTS` beside an interval) stopped the converter with a
  TypeError. They now get one `*TIME POINTS` list of all their times, to 12 digits. A
  `TIME POINTS=` that names no `*TIME POINTS` card is warned.
* **Malformed input reported instead of crashing the converter** — a `*RIGID BODY` `PIN NSET`
  / `TIE NSET` with no value (dropped; a card left with no set is commented out); a rigid
  master surface with an element of no `*RIGID BODY` (its `*TIE` is left to ccx); an element on
  an undefined node (warned; a traction or beam line load on it is commented out); a
  `*PARAMETER` value beyond the float range (`10**5000`; `9**9**9` ran for minutes); `*BOUNDARY`
  DOFs above 30 (left out; a range in the millions stalled the converter).
* **BCs and moments after a linear perturbation step** — Abaqus drops a perturbation step's
  BCs and loads after it, and the converter gives ccx the base state again, but six planners
  still read them as carried on. An `*EQUATION` on DOFs that only a `*FREQUENCY` step held was
  dropped as redundant, so its tie was gone in the next general step (now kept). A JOIN
  connector off a beam node whose rotations only such
  a step held lost that rotation. On a `*TRANSFORM` node written in global components, the
  step's rotation hold or moment came back in the next general step, and a `*BUCKLE` step's
  load included the earlier moments (buckling factor 0.9 % off). A zero BC in a later
  `*DYNAMIC` step could be stepped instead of ramped, and the transient coupled step's
  released-BC warning compared the wrong BCs.
* **Coupling `ORIENTATION=`** — Abaqus couples the DOFs in the orientation's axes. In a
  `*DYNAMIC` deck the coupling's equations tied the global DOFs instead (40 % off with some
  translations coupled), a `*KINEMATIC COUPLING` card lost the parameter, and a part-level
  coupling named the part's orientation, so ccx stopped ("nonexistent orientation"). The
  equations now tie the local DOFs (a non-rectangular orientation with some translations
  coupled is commented out, with a warning), the card keeps `ORIENTATION=`, and each instance
  names its own copy.
* **Kinematic couplings in `*DYNAMIC` decks** — a coupling on an undefined node stopped the
  converter (KeyError); undefined members are now left out with a warning, and an undefined
  reference node is left to ccx, which stops on it. A `*KINEMATIC COUPLING` line whose DOFs do
  not read was dropped without a word; the card is now commented out, as in static decks, and
  no longer counts as a constraint (a static deck took its members' own BCs off). A connector
  on the members of a coupling that is commented out is now written; it was refused as if the
  coupling held them.
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
* **Parameter names without blanks** — Abaqus ignores blanks in parameter names, but the
  converter read most multi-word names only as spelled with them. So `*TIE,
  POSITIONTOLERANCE=` was dropped and ccx tied nothing (displacements of about 1e12),
  `*COUPLING, REFNODE=<set>` went out unresolved and ccx stopped, `*ELCOPY, ELEMENTSHIFT=,
  SHIFTNODES=` copied nothing, an assembly left a part's `TIENSET=` / `PINNSET=` unrenamed,
  `*TIE, NOROTATION` lost its reduced-physics warning and `*HYPERELASTIC, NEOHOOKE` got a
  `POLYNOMIAL` in front. Such names now read as their blank spelling everywhere.
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
* **Loads in static perturbation steps** — a `*STEP, PERTURBATION` `*STATIC` step after other
  perturbation steps now gets the base state's loads, BCs and temperatures again, plus its own,
  as in Abaqus. ccx 2.23 also applied the loads and BCs of those earlier steps (`*MODAL DYNAMIC`,
  `*BUCKLE`, `*FREQUENCY`, steady-state dynamics, static perturbation): a cube after a modal
  dynamic step was 0.024 off a response of 0.027. Two static perturbation steps in a row are
  therefore no longer flagged as reduced physics.
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
* **`*BUCKLE` factors nearest 1** — ccx 2.23 shift-inverts its buckling solve about 1, so it
  returns the factors nearest 1, not the lowest: those are the lowest only while the load is
  below the lowest buckling load (probed: a column at twice its buckling load gave 4.42,
  11.9, ..., not 0.5). Every `*BUCKLE` step now notes it, and the `--run` digest warns when a
  factor is below 1 or all lie within 5 % of 1 (also the mark of a free rigid-body mode). `--approximate` drops `PERTURBATION` on a last
  `*BUCKLE` step that a prescribed displacement loads after a preload: ccx then solves for the
  displacement, without the preload (warned before, and still without the option).

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
