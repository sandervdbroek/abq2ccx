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
  displacement BCs, with Abaqus' default amplitudes.
* **Default amplitudes** — displacement BCs without an amplitude follow Abaqus where its
  default departs from ccx's: ramped from the previous value where ccx would step them
  (implicit dynamics, `*VISCO`, transient coupled steps), held where they are in explicit
  steps; `*STEP, AMPLITUDE` dropped on explicit steps.
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
* **Materials and orientations** — per-element `*DISTRIBUTION` orientations; the elastic
  forms ccx 2.23 needs beside orthotropic and anisotropic expansion; halved ANISO expansion
  shear coefficients; zero-shear ANISO written as ORTHO; default initial temperatures.
* **Output** — requests fitted to ccx's `.frd`/`.dat` model, one output control per step,
  explicit output intervals from ccx's stable increment, Abaqus' preselected field and
  contact output.
* **Crash guards** — step data outside a step, undefined materials, rotational DOFs on plane
  nodes and other inputs that crash ccx 2.23 are commented, warned or dropped.

Corpus: 160 decks solve their own problem; 28 more solve with reduced physics, 14 load
nothing (3 both) and one drifts to a solution that is not the deck's; 219 mesh-only decks are
accepted, 603 need what ccx cannot run.

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
