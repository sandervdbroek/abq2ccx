# abq2ccx documentation

`abq2ccx.py` converts Abaqus `.inp` decks to CalculiX (`ccx`) decks. The
[README](../README.md) is the overview; these pages are the reference.

* **[User guide](user-guide.md)** — options, `--approximate`, workflow, reading the report,
  the names the converter adds, the Python API.
* **[Troubleshooting](troubleshooting.md)** — ccx errors and results that look wrong, with
  causes and fixes.
* **[Compatibility](compatibility.md)** — the Abaqus and CalculiX facts the converter relies
  on and their evidence, ccx 2.23 issues, and what does not convert.
* **[Testing](testing.md)** — unit tests, the end-to-end checks in ccx, and the corpus of
  1052 real decks, 26 of them checked against their published answers.
* **[Architecture & developer guide](architecture.md)** — the pipeline, the data model, and
  how to extend the tables and handlers.
* **[Changelog](../CHANGELOG.md)** — what changed, release by release.

## Generated references

Built from the code by `python docs/generate_reference.py` (run it after changing the
tables; edit the generator, not these files):

* **[Keyword reference](keyword-reference.md)** — every keyword and how it is handled.
* **[Element reference](element-reference.md)** — every element type, its node count and
  CalculiX mapping.
* **[Output-variable reference](output-reference.md)** — output identifiers and Abaqus'
  preselected output.
