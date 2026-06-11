# AtoC documentation

`abq2ccx.py` converts Abaqus `.inp` decks to CalculiX (`ccx`) `.inp` decks. Start with
the [project README](../README.md) for the overview; this folder is the detailed
reference.

## Contents

* **[User guide](user-guide.md)** — install, command line, options, workflow, reading
  the conversion report, and using the converter as a Python module.
* **[Troubleshooting](troubleshooting.md)** — CalculiX runtime errors and silent-physics
  gotchas, with causes and fixes.
* **[Architecture & developer guide](architecture.md)** — the conversion pipeline, the
  data model, and how to extend the keyword/element/output tables.
* **[Testing](testing.md)** — the three test layers (unit, end-to-end ccx, real-world
  corpus) with a description of each test.
* **[Compatibility & sources](compatibility.md)** — the verified facts the converter
  relies on, version notes, and where they come from. Includes the **end-to-end
  validation** against the NAFEMS LE10 benchmark (run it with
  `python validate_with_ccx.py`).

### Generated references (from the code — never out of date)

* **[Keyword reference](keyword-reference.md)** — every keyword and exactly how it is
  handled.
* **[Element reference](element-reference.md)** — every element type, node count, and
  CalculiX mapping.
* **[Output-variable reference](output-reference.md)** — output identifier mapping.

Regenerate the three reference files after editing the code with:

```bash
python docs/generate_reference.py
```

## At a glance

* One dependency-free Python 3 script; no install.
* Knows the complete CalculiX 2.22 keyword set; supported cards pass through,
  unsupported ones are converted to an equivalent or commented with guidance — never
  silently dropped.
* Expands mesh-generation cards (`*NCOPY`/`*ELGEN`/…) and flattens
  `*PART`/`*INSTANCE`/`*ASSEMBLY`.
* Node and face numbering are verified identical to Abaqus, so connectivity and
  pressure-face labels pass through unchanged.
* Validates *structure*, not *physics* — always run `ccx` and sanity-check.
