# Changelog

Corpus counts are on the CalculiX version current at the time; from October 2026 on, "solve"
counts only decks that solve their own problem: under their own loads, without reduced
physics.

## Unreleased (October 2026, still `__version__ = "1.1.0"`) — CalculiX 2.23

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
  installs an `abq2ccx` command (`pyproject.toml`; copying the file still works). GitHub
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
  principal axes, n1 projected per element, a material copy for G J, line loads and gravity as
  nodal forces with consistent end moments; in space where G J cannot be had, only with
  `--approximate`, which otherwise keeps the I → `RECT` route. Three planar I-beam decks solve
  (Euler–Bernoulli for Timoshenko beams: reduced physics).

Corpus: 165 decks solve their own problem; 32 more solve with reduced physics, 14 load
nothing (3 both) and one drifts to a solution that is not the deck's; 221 mesh-only decks are
accepted, 592 need what ccx cannot run.

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
