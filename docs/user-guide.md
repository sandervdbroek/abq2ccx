# User guide

## Requirements

* Python 3.7 or later, standard library only. The whole tool is `abq2ccx.py`; copy it
  anywhere or run it from the repository.
* CalculiX (`ccx`) only to run the result. `--run` and `validate_with_ccx.py` look for it on
  `PATH`, in FreeCAD's bundle (FreeCAD 1.1.4 ships ccx 2.23) and in Homebrew/MacPorts;
  `--run` also takes `--ccx PATH` or `$CCX`.

## Command line

```bash
python abq2ccx.py INPUT.inp [INPUT.inp ...] [options]     # glob patterns allowed
```

| Option | Effect |
| --- | --- |
| `-o, --output FILE` | output file (one input only; default `<input>_ccx.inp`) |
| `--outdir DIR` | write the outputs, under their default names, into `DIR` |
| `--solid-dof` | expand `ENCASTRE`/`PINNED`/`*SYMM` to DOFs 1–3 only (solid-only models) |
| `--approximate` | allow the physics approximations [below](#--approximate), each flagged `[APPROX]` |
| `--check` | parse, convert and report; write nothing |
| `--strict` | exit 3 if the conversion produced warnings or commented-out cards |
| `--json` | print a machine-readable report on stdout |
| `--run` | run CalculiX on the result |
| `--ccx PATH` | the CalculiX executable for `--run` (`$CCX` works too) |
| `--no-log`, `--quiet` | write no `.log` file; print no report on stderr |
| `--version`, `-h` | version; help |

**Exit codes:** `0` converted · `1` cannot read or write, or `--run` failed · `2` usage
error · `3` `--strict` findings · `4` internal conversion error. `--run` fails when ccx
stops with an `*ERROR`, crashes, or writes NaN/Inf results — ccx 2.23 ends a diverged
solution with "Job finished" all the same, so `--run` reads the results and names the first
NaN/Inf value.

**Outputs:** `<output>.inp`, the CalculiX deck, with the report as `**` comments at the
top; `<output>.log`, the same report as text; and a one-line summary plus the report on
stderr. Run the deck with `ccx <output>` (no `.inp` extension).

## `--approximate`

Without it, a construct ccx cannot run exactly is commented out or warned, so ccx never runs
a different model without saying so. With it, these reframings are made, each with an
`[APPROX]` warning:

* `*STATIC, RIKS` → a plain, load-controlled `*STATIC` (ccx has no arc-length method);
* `*ELASTIC` with ν ≥ 0.5 → ν = 0.475 (ccx has no hybrid elements);
* `*BEAM SECTION, SECTION=I` → the rectangle with the same area and strong-axis inertia;
* surface tractions under NLGEOM that follow the surface or act per current area, and beam
  line loads under NLGEOM → fixed nodal forces;
* surface elements that carry mass or rebar → left out of the mesh;
* a `*BOUNDARY` on DOFs that a kinematic coupling or `*MPC` eliminates → dropped, as
  Abaqus/Standard ignores it; identical BCs on `*RIGID BODY` nodes → moved to the reference
  node even where that holds the body more than the BCs did;
* a connector under NLGEOM whose linear form is not exact (a hinge between two moving
  bodies) → written in its linear form;
* an `*MPC LINK` → ccx's distance MPC in a deck whose first step is linear and a later one
  NLGEOM.

## Recommended workflow

1. **Export a flat deck if you can** (Abaqus/CAE: *Do not use parts and assemblies*). The
   converter flattens assemblies, but a flat deck is the lower-risk input.
2. **Convert and read the report.** Every `[WARNING]` and `[NOTE]` is there for a reason.
3. **Resolve commented cards.** A card emitted as `** abq2ccx: …` has no CalculiX
   equivalent and needs remodelling; the comment says how.
4. **Run ccx and check the results.** Field output is in `<job>.frd`; history output for a
   set is in `<job>.dat`, as are node sets the `.frd` cannot show (beam and shell nodes —
   ccx writes such models expanded to 3-D — and reference points). If ccx stops, see
   [troubleshooting](troubleshooting.md). `python validate_with_ccx.py` checks your ccx
   end to end on the bundled examples.

## Reading the conversion report

* **`[NOTE]`** — a routine translation you should know about (a parameter dropped, a
  variable renamed, a default applied). Usually nothing to do.
* **`[WARNING]`** — something that may be wrong or needs your judgement: an element with no
  exact equivalent, an unresolved overconstraint, a card commented out, a load that could not
  be converted.

Messages are de-duplicated. A clean conversion says *"No conversion issues were flagged."*

| Message | Meaning and action |
| --- | --- |
| `Element X -> Y (… substitution)` | a node-count-preserving swap; check that Y suits your physics |
| `… has NO CalculiX equivalent … emitted unchanged` | a cohesive, gasket or rigid element; the deck won't run until it is remodelled |
| `*KEYWORD … emitted as a comment` | no equivalent; the original is kept as `**` comments for you to edit |
| `Step N is loaded in the Abaqus deck …, but no load survives the conversion` | every load of that step was commented out; ccx would solve it with no load — see the step's other warnings |
| `Possible overconstraint: node N DOF d …` | a `*BOUNDARY` on a DOF that an `*EQUATION`, `*MPC` or rigid body eliminates, which the converter could not resolve exactly; ccx will stop. The message says what Abaqus does and whether `--approximate` resolves it |
| `*BOUNDARY taken off …` / `… moved to the reference node … Exact.` | BCs on rigid-constraint members resolved the way Abaqus does; nothing to do |
| `*BOUNDARY, TYPE=VELOCITY … start of the step is unknown` | the DOF was free before the step, so its displacement there is unknown: a zero velocity became `*BOUNDARY, FIXED`, anything else was commented out — prescribe a displacement, or constrain the DOF in the earlier step |
| `*BOUNDARY (displacement) with a nonzero value and no AMPLITUDE in an explicit step` | Abaqus/Explicit ignores that value and holds the DOF, so nothing moves — in Abaqus too; give the BC an amplitude if the DOF should move |
| `… Kept as given: ccx moves the DOF to that value at once` / `… on a node with a *TRANSFORM, on a DOF that had no BC before the step` | ccx cannot hold or ramp that displacement BC the way Abaqus does, so the DOF jumps to the given value; give the BC an amplitude in the Abaqus deck |
| `… member(s) reference undefined …` | a set named ids that don't exist; check upstream renumbering if the count surprises you |
| `Duplicate node/element id(s) …` | the deck defines an id twice; the last one wins, as in Abaqus |

### Names the converter adds

Everything the converter creates starts with `ABQ2CCX_`:

| Name | What it is |
| --- | --- |
| `ABQ2CCX_ALL_NODES`, `ABQ2CCX_ALL_ELEMENTS` | whole-model sets (output requests without a set, default initial temperatures) |
| `ABQ2CCX_KNOT` | the force-free *knot beams* on shell and beam nodes that carry rigid couplings or rotational BCs; ignore them in the results |
| `ABQ2CCX_PLANAR` | the nodes of a planar model held in its plane |
| `ABQ2CCX_RB*`, `ABQ2CCX_MPCB*`, `ABQ2CCX_KC*`, `ABQ2CCX_TIED*` | node sets and surfaces of rigid bodies, `*MPC BEAM` bodies, kinematic couplings and tied contact pairs |
| `ABQ2CCX_BC*` | node subsets of a BC card that the converter partly moved or removed |
| `ABQ2CCX_TR*`, `ABQ2CCX_OR*` | synthesized `*TRANSFORM` node sets and `*ORIENTATION`s (spherical transforms, rotation-node axes, composite ply angles) |
| `ABQ2CCX_VEL*`, `ABQ2CCX_ACC*` | amplitudes that integrate velocity and acceleration BCs |
| `ABQ2CCX_TP*`, `ABQ2CCX_OUTPUT*` | generated `*TIME POINTS` and output node sets |

One name is ccx's own: `AMPLITUDE=RAMP12357111317` on a `*BOUNDARY` is ccx's step ramp, which
the converter uses where Abaqus/Standard ramps a displacement BC that ccx would apply at once.

Edit the Abaqus deck and convert again rather than editing these by hand.

## Python API

```python
import abq2ccx

result = abq2ccx.convert_file("model.inp", solid_dof=False, approximate=False)
# or: abq2ccx.convert_text(deck_string, base_dir=".")  — *INCLUDE paths relative to base_dir

result.text           # the converted deck, report header included
result.body           # the deck lines without the header
result.report         # .summary(), .entries: [(level, message)], .n_warnings, .n_notes
result.geometry       # the flattened, expanded model: .nodes, .elements, .nsets, .elsets
result.ok             # False if nothing could be converted
```

The lower-level pieces are `read_blocks(path, report)` (parse, follow `*INCLUDE`) and
`Converter(report, Options(solid_dof, approximate)).convert(blocks)`; the
[architecture guide](architecture.md) describes them. `classify_ccx_run(returncode, stdout,
stderr, job)` is the solve judge that `--run`, `validate_with_ccx.py` and the corpus tests
share.

## What is and isn't converted

Static, frequency, buckling, implicit and explicit dynamic, steady-state dynamic, heat
transfer and coupled temperature–displacement analyses of solids, shells and beams are well
covered, with the common materials, orientations and composite layups, sets, surfaces, BCs,
loads, ties, equations, couplings, rigid bodies and connectors without a behaviour. Contact
is translated card by card, but ccx's penalty contact behaves differently — check it. User
subroutines, connector behaviours, gaskets, inertia relief, Riks and some specialised
materials and procedures have no equivalent and are flagged for manual work.

The generated references list every case: [keywords](keyword-reference.md),
[elements](element-reference.md), [output variables](output-reference.md).
