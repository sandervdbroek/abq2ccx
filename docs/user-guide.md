# User guide

How to install, run, and interpret the output of `abq2ccx.py`.

## Requirements

* Python 3.7+ (standard library only — no packages to install).
* To *run* the result you need CalculiX (`ccx`); the converter does not require it.

The whole tool is one file. Copy `abq2ccx.py` anywhere, or run it from the repo.

## Command line

```bash
python abq2ccx.py INPUT.inp [options]
```

| Option | Effect |
| --- | --- |
| `-o, --output FILE` | output path (default: `<input>_ccx.inp`) |
| `--solid-dof` | expand `ENCASTRE`/`PINNED`/`*SYMM` using translational DOFs 1–3 only — use for solid-only models that have no rotational DOFs |
| `--no-log` | do not write the `<output>.log` report file |
| `--quiet` | do not print the report to stderr |
| `-h, --help` | usage |

Outputs:

* `<output>.inp` — the CalculiX deck. The conversion report is also reproduced as
  `**` comments at the very top of this file.
* `<output>.log` — the same report as plain text (unless `--no-log`).
* stderr — a one-line summary (`N nodes, M elements, K warnings`) plus the report
  (unless `--quiet`).

### Examples

```bash
python abq2ccx.py model.inp                      # -> model_ccx.inp + model_ccx.log
python abq2ccx.py model.inp -o run/job.inp       # custom output path
python abq2ccx.py solid_only.inp --solid-dof     # ENCASTRE -> DOF 1,2,3
ccx model_ccx                                    # run it (note: no .inp extension)
```

## Recommended workflow

1. **Export a flat deck if you can.** In Abaqus/CAE, *Model → Edit Keywords* or the
   input-file export option "Do not use parts and assemblies" produces a deck that
   skips the `*PART`/`*INSTANCE`/`*ASSEMBLY` flattening step (which is best-effort).
   The converter flattens assemblies for you, but a flat deck is lower-risk.
2. **Convert** and **read the report.** Every `[WARNING]` and `[NOTE]` is there for a
   reason — see [Reading the report](#reading-the-conversion-report) below.
3. **Resolve commented cards.** Anything emitted as `** abq2ccx: …` has no CalculiX
   equivalent and needs manual remodelling; the comment says how.
4. **Run `ccx`** and sanity-check results. If it stops, see
   [troubleshooting.md](troubleshooting.md). To confirm your toolchain end-to-end, run
   `python validate_with_ccx.py` — it converts the bundled examples and runs them in
   CalculiX (auto-detecting `ccx`, including FreeCAD's bundled copy), and checks the
   NAFEMS LE10 benchmark stress against its reference value.

## Reading the conversion report

The report has two levels:

* **`[NOTE]`** — a routine translation you should be aware of (a parameter dropped, a
  variable renamed, a default applied). Usually no action needed.
* **`[WARNING]`** — something that may be wrong or needs your judgement (an element
  with no exact equivalent, a possible overconstraint, an unsupported card commented
  out, a non-Cartesian system approximated).

Messages are de-duplicated, so each distinct issue appears once no matter how many
times it occurs. A clean conversion prints *"No conversion issues were flagged."*

Common messages and what to do:

| Message fragment | Meaning / action |
| --- | --- |
| `Element X -> Y (… substitution)` | a node-count-preserving swap; verify Y is acceptable for your physics |
| `… has NO CalculiX equivalent … emitted unchanged` | cohesive/gasket/connector/rigid element — the deck won't run until you remodel it |
| `*KEYWORD … emitted as a comment` | no equivalent; the original is preserved as `**` comments for you to edit |
| `Possible overconstraint: node N DOF d …` | a `*BOUNDARY` sits on an `*EQUATION`/`*MPC` dependent DOF — ccx will crash; remove one |
| `… member(s) reference undefined … removed` | a set had ids that don't exist; if the count is surprising, check upstream renumbering |
| `Duplicate node/element id(s) …` | the deck defines an id twice; last one wins (as in Abaqus) |
| `*ORIENTATION SYSTEM=SPHERICAL …` | ccx has no spherical system; emitted rectangular — verify |

## Using it as a Python module

```python
import abq2ccx

report = abq2ccx.Report()
blocks = abq2ccx.read_blocks("model.inp", report)        # parse (+ *INCLUDE)

class Opt:                                                # options object
    solid_dof = False

conv = abq2ccx.Converter(report, Opt())
lines = conv.convert(blocks)                              # list[str] of ccx deck lines
text = "\n".join(report.header_comment_lines() + lines)

# inspect the parsed/expanded model
print(len(conv.geom.nodes), "nodes,", len(conv.geom.elements), "elements")
for level, msg in report.entries:
    print(level, msg)
```

`conv.geom` is the fully expanded, flattened geometry (`nodes`, `elements`, `nsets`,
`elsets`), useful for your own checks or post-processing.

## What is and isn't converted

For the exhaustive lists see the generated references:

* **[keyword-reference.md](keyword-reference.md)** — every keyword and its handling.
* **[element-reference.md](element-reference.md)** — every element type and its mapping.
* **[output-reference.md](output-reference.md)** — output-variable mapping.

In short: linear/nonlinear **static, frequency, buckling, dynamic, heat-transfer**
structural analyses with solids/shells/beams, the common materials, orientation and
composite layups, sets/surfaces, BCs, loads, ties and equations are well covered.
**Contact** is passed through but not semantically translated. **Connectors, gaskets,
cohesive elements, inertia relief, advanced material models, and explicit/specialised
procedures** have no equivalent and are flagged for manual work.
