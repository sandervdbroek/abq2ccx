# Changelog

Corpus counts are on the CalculiX version current at the time; from October 2026 on, "solve"
counts only decks that solve their own problem: under their own loads, without reduced
physics.

## Unreleased

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
