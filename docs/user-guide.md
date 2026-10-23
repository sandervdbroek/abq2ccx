# User guide

## Requirements

* Python 3.9 or later, standard library only. The whole tool is `abq2ccx.py`; copy it
  anywhere or run it from the repository, or install it as the `abq2ccx` command with
  `pipx install abq2ccx`, or the latest main with
  `pipx install git+https://github.com/sandervdbroek/abq2ccx` (`pip install .` in a clone).
* CalculiX (`ccx`) 2.23 only to run the result: `conda install -c conda-forge calculix=2.23`
  installs it on Linux, macOS and Windows. `--run` and `validate_with_ccx.py` take `$CCX`
  (`--run` also `--ccx PATH`), else look on `PATH`, then in the install folders of programs
  that ship ccx (PrePoMax and bConverged on Windows) and Homebrew/MacPorts. A conda
  environment's ccx on Windows needs no `conda activate`: it runs with the folders activation
  would put on `PATH`. `--run` prints the version it runs and warns if it is not 2.22 or 2.23,
  the versions the converter targets.

## Command line

```bash
python abq2ccx.py INPUT.inp [INPUT.inp ...] [options]     # glob patterns allowed
abq2ccx INPUT.inp [INPUT.inp ...] [options]               # the same, installed
abq2ccx INPUT.inp OUTPUT.inp [options]                    # into OUTPUT.inp
```

With two `.inp` files, the second is the output when it does not exist yet or abq2ccx wrote
it (so a rerun overwrites it); two existing Abaqus decks convert as a batch, so this form never
overwrites a deck abq2ccx did not write.

| Option | Effect |
| --- | --- |
| `-o, --output FILE` | output file (one input only; default `<input>_ccx.inp`) |
| `--outdir DIR` | write the outputs, under their default names, into `DIR` |
| `--solid-dof` | expand `ENCASTRE`/`PINNED`/`*SYMM` to DOFs 1–3 only (solid-only models) |
| `--approximate` | allow the physics approximations [below](#--approximate), each flagged `[APPROX]` |
| `--abaqus-umat` | write `*USER MATERIAL` materials for ccx's Abaqus-UMAT interface, to run a ccx built with the deck's UMAT ([below](#--abaqus-umat)) |
| `--max-ply-elements N` | write composite continuum shells as one solid per ply only up to `N` solids (default 1000000; `0`: no limit) |
| `--check` | parse, convert and report; write nothing |
| `--strict` | exit 3 if the conversion produced warnings or commented-out cards |
| `--json` | print one JSON object per deck per line on stdout ([batch triage](#batch-triage)) |
| `--summary FILE.csv` | write one CSV row per deck ([batch triage](#batch-triage)) |
| `--debug` | on an internal error (exit 4), print the Python traceback |
| `--run` | run CalculiX on the result and print a digest of its results |
| `--ccx PATH` | the CalculiX executable for `--run` (`$CCX` works too) |
| `--timeout SECONDS` | stop ccx after `SECONDS` of wall-clock time (`--run`; default: no limit) |
| `--no-log`, `--quiet` | write no `.log` file; print no report on stderr |
| `--version`, `-h` | version; help |

**Exit codes:** `0` converted · `1` cannot read or write, or `--run` failed · `2` usage
error · `3` `--strict` findings · `4` internal conversion error, a bug: the traceback goes
into the `.log` (with `--debug` also to stderr; the `.log` writes your home folder `~`, but
check it for private paths before posting); please report it at
[the issues](https://github.com/sandervdbroek/abq2ccx/issues) with the deck or a cut-down one
that fails the same way. `--run` fails when ccx
stops with an `*ERROR`, crashes, writes NaN/Inf results or runs a step that sets up no
equations — ccx 2.23 ends a diverged solution, and such a step, with "Job finished" all the
same, so `--run` reads the results and names the first NaN/Inf value, or the step.

**Outputs:** `<output>.inp`, the CalculiX deck, with the report as `**` comments at the
top; `<output>.log`, the same report as text; and a one-line summary plus the report on
stderr. Run the deck with `ccx <output>` (no `.inp` extension). `--run` streams ccx's output
to stderr as it comes and to `<output>.ccx.log` (its first 100 MB, then its last lines), and
ends with ccx's own `*ERROR` and `*WARNING` lines.
An `*IMPERFECTION, FILE=job` reads modes from another job's results: give that job's deck,
`job.inp`, next to the deck, and `--run` runs it first (as `<output>_imperfection.inp`) and
moves the nodes by its modes.

### Batch triage

`--json` prints one object per deck per line (JSON Lines): `input`, `output`, `nodes`,
`elements`, `counts`, `entries` (the report: `level`, `message` and `location`, the card's
`file:line` or null), `status`, `reduced_physics`, `instances`, with
`--run` also `run` and `results`, and `error` for a deck that failed. `status` is `failed`
(nothing converted), `reduced` (ccx solves another model; `reduced_physics` says what),
`commented` (cards commented out, the physics kept) or `converted`. `--summary FILE.csv` writes a
row per deck: deck, status, nodes, elements, warnings, commented cards, reduced
physics, ccx's status and the last step's digest line (`--run`), and the error. The rows go to
`FILE.csv.part` as the batch runs, which replaces `FILE.csv` when it ends (a pipe or device,
such as `/dev/stdout`, gets them directly); a deck, an input or a file that is no summary is
never overwritten, and a cell starting with `=`, `+`, `-` or `@`
gets a `'` before it (spreadsheets read it as a formula).

```bash
abq2ccx variants/*.inp --outdir out --run --quiet --summary out/summary.csv
```

## `--approximate`

Without it, a construct ccx cannot run exactly is commented out or warned, so ccx never runs
a different model without saying so. With it, these reframings are made, each with an
`[APPROX]` warning and listed in the closing "Reduced physics" warning:

* `*STATIC, RIKS` → a plain, load-controlled `*STATIC` (ccx has no arc-length method);
* `*ELASTIC` with ν ≥ 0.5 → ν = 0.475 (ccx has no hybrid elements);
* I, T, trapezoidal, arbitrary and general beam sections in space whose torsion ccx's `U1`
  beam cannot match (no Poisson's ratio ccx accepts gives G J, the shear centre is off the
  centroid, or Abaqus computes J numerically) → `U1` all the same (bending exact);
  `SECTION=I` where `U1` cannot run (a deck with shells, NLGEOM, plasticity, …) → the
  rectangle with the same area and strong-axis inertia;
* surface tractions under NLGEOM that follow the surface or act per current area (but a
  follower `TRVEC` normal to flat faces, a pressure), and beam line loads under NLGEOM →
  fixed nodal forces;
* surface elements that carry mass or rebar → left out of the mesh;
* curved analytical rigid surfaces (`CIRCL` and `PARAB` profiles, `TYPE=REVOLUTION`,
  `FILLET RADIUS`) → flat facets about the slave faces' size (the warning gives their chord
  angle and sag);
* rigid elements of an Abaqus/Explicit `*RIGID BODY` with `DENSITY` and a thickness → skins
  without that mass;
* `ROTARYI` on an axisymmetric rigid body in a deck with a dynamic or frequency step →
  dropped;
* a `*BOUNDARY` on DOFs that a kinematic coupling or `*MPC` eliminates → dropped, as
  Abaqus/Standard ignores it; identical BCs on `*RIGID BODY` nodes → moved to the reference
  node even where that holds the body more than the BCs did;
* a connector under NLGEOM whose linear form is not exact (a hinge between two moving
  bodies) → written in its linear form;
* an `*MPC LINK` → ccx's distance MPC in a deck whose first step is linear and a later one
  NLGEOM;
* `S4R` shells (ccx 2.23 bends them only through their `C3D8R`'s hourglass stiffness) → `S4`,
  or `S8R` with midside nodes where an element is more than 6 thicknesses wide;
* flagged `CPS4R`, `CPE4R`, `CAX4R` (elements much larger than their brick's depth), `M3D4R`
  and `B31R` (the same `C3D8R` hourglass stiffness) → `CPS4`, `CPE4`, `CAX4`, `M3D4`, `B31`;
* self-contact (one surface, or the same surface twice) → ccx's `S, S` with
  `TYPE=SURFACE TO SURFACE` (within 0.1 % of symmetric pairs on a mild closure, 10–13 % off
  on a deep one);
* `CPE4` / `CAX4` of a plastic, creeping or nearly incompressible material (they lock), and
  such flagged `CPE4R` / `CAX4R` → `CPE8R` / `CAX8R` with midside nodes, their linear
  neighbours too; such `C3D8` → `C3D8I`;
* `S3` / `S3R` shells (one `C3D6` wedge in ccx 2.23, which locks in bending) → `S6` with
  midside nodes;
* a plastic `*SHELL SECTION` (ccx integrates it at 2 Gauss points through the thickness) → a
  composite of 2 equal layers, its linear shells `S8R` / `S6`;
* `S4`, `S4R5`, `S4T` and `S4RT` shells collapsed to a triangle → `S3`, `S3R`, `S3T`, `S3RT`
  (a collapsed `S4R` is `S3R` without the option: exact);
* a `*DAMPING` value the materials share but Abaqus does not apply to point masses, springs or
  contact → the materials' value, which ccx's one model-wide pair applies to them too;
* explicit mass scaling to a target increment (`TYPE=BELOW MIN`) → ccx's selective mass
  scaling, `DT` the step's minimum increment;
* `*DYNAMIC TEMPERATURE-DISPLACEMENT, EXPLICIT` (ccx has no explicit coupled step) → ccx's
  transient `*COUPLED TEMPERATURE-DISPLACEMENT`, which it solves implicitly with the model's
  mass: the deck's period, increments from 1/100 of it down, Abaqus/Explicit's NLGEOM, BC and
  output rules; explicit time integration and the heat of plastic work are lost;
* a distributing coupling that turns, in a deck with NLGEOM → linear `*EQUATION`s (exact for
  small rotations); a kinematic coupling of some rotations about its `ORIENTATION`'s axes
  under NLGEOM → tied about the initial axes; one of only some translations in a deck with a
  `*DYNAMIC` step and NLGEOM → linear `*EQUATION`s (7 % off at 0.36 rad);
* a `*FREQUENCY` step after general steps without NLGEOM that resolve an overclosure as an
  interference fit → `*STEP, PERTURBATION` (it keeps the contact status, and adds the fit's
  stress stiffness);
* a last `*BUCKLE` step loaded by a prescribed displacement after a general step → without
  PERTURBATION, which buckles it without its preload;
* general contact (`*CONTACT`, `ALL EXTERIOR` or named surfaces) → node-to-surface contact
  pairs between the bodies that can meet (their exterior faces; the struck, yielding or finer
  body the slave, one line per slave body), without self-contact and edge-to-edge contact.

## `--abaqus-umat`

ccx picks the routine for a `*USER MATERIAL` by the start of the material name. Without the
option, a material whose name would pick one of ccx's own routines (`USER…`, `ABAQUS…`,
`JOHNSONCOOK…`, …) is renamed `ABQ2CCX_<name>`, so ccx stops with "no user material
subroutine" instead of running another material. With it, every mechanical user material
becomes `ABAQUS<name>` for ccx's Abaqus-UMAT interface (small strain), or `ABAQUSNL<name>` in
a deck with NLGEOM steps (logarithmic strain); a note names each UMAT argument ccx supplies
differently ([compatibility](compatibility.md#materials)). A stock ccx runs its linear-elastic
example there; to run the deck's UMAT, build ccx 2.23 with it. With conda-forge's compilers and
libraries (tested on macOS arm64; any gfortran and C compiler with SPOOLES 2.2, ARPACK and
LAPACK will do):

```bash
conda create -y -n ccx-umat -c conda-forge "spooles>=2.2=*_1006" "arpack=*=nompi*" liblapack c-compiler fortran-compiler make
conda activate ccx-umat
```

Unpack the ccx 2.23 sources (`ccx_2.23.src.tar.bz2`, <https://www.dhondt.de>) and, in
`CalculiX/ccx_2.23/src`:

1. Set U0 in `umat_abaqusnl.f`, which ccx 2.23 never does
   ([#225](https://github.com/Dhondtguido/CalculiX/issues/225)): under `ABAQUSNL` a UMAT that
   adds to the stress it gets (plasticity, damage, any incremental law) goes wrong without it.

   ```bash
   python3 - <<'EOF'
   p, a = "umat_abaqusnl.f", "      um1(3,2)=um1(2,3)\n"
   u0 = ("      do jj=1,6\n"
         "        u0(kal(1,jj),kal(2,jj))=xm1(jj)/wum1(1)+xm2(jj)/wum1(2)\n"
         "     &       +xm3(jj)/wum1(3)\n"
         "        u0(kal(2,jj),kal(1,jj))=u0(kal(1,jj),kal(2,jj))\n"
         "      enddo\n")
   s = open(p).read()
   open(p, "w").write(s.replace(a, a + u0, 1))
   EOF
   ```
2. Build ccx's objects, once (the `-Wno-` flags let today's C compilers take ccx 2.23's C;
   elsewhere name your C and Fortran compilers):

   ```bash
   make -j4 CalculiX.o CalculiX.a CC=clang FC=gfortran FFLAGS="-O2 -cpp -fallow-argument-mismatch -w" \
     CFLAGS="-O2 -w -I$CONDA_PREFIX/include/spooles -DARCH=\"Linux\" -DSPOOLES -DARPACK -DMATRIXSTORAGE -DNETWORKOUT -Wno-int-conversion -Wno-incompatible-pointer-types -Wno-implicit-function-declaration -Wno-implicit-int -Wno-return-mismatch"
   ```
3. Compile the deck's UMAT as Abaqus does (fixed form to column 132, preprocessed; add
   `-ffree-form` for free-form source), with the files it `INCLUDE`s and an `ABA_PARAM.INC`
   (`implicit real*8(a-h,o-z)`, `parameter (nprecd=2)`) beside it, and link it ahead of
   ccx's archive (ccx's example UMAT then stays out):

   ```bash
   gfortran -c -O2 -cpp -ffixed-line-length-132 -fmax-stack-var-size=4096 -fallow-argument-mismatch -fcray-pointer -w umat_deck.for -o umat_deck.o
   gfortran -o ccx_umat umat_deck.o CalculiX.o CalculiX.a $CONDA_PREFIX/lib/spooles.a -L$CONDA_PREFIX/lib -larpack -llapack -lblas -lpthread -lm -Wl,-rpath,$CONDA_PREFIX/lib
   ```

   ccx calls only `UMAT` (no `UEXTERNALDB`, `SDVINI`, …) and has none of Abaqus' utility
   routines (`XIT`, `GETOUTDIR`, `SINV`, `SPRINC`, `ROTSIG`, …): add those the link reports
   missing. ccx calls the UMAT in worker threads with the system's default stack (512 KB on
   macOS), which large local arrays overrun, corrupting ccx's memory:
   `-fmax-stack-var-size=4096` puts them in static memory, so run with `OMP_NUM_THREADS=1`.

The repository's `tools/build_ccx_umat.py` does the three steps in one command, in the
environment above (ccx's objects once per source tree, cached), with the Abaqus utility routines a UMAT may call (`XIT`,
`GETOUTDIR`, `GETJOBNAME`, `SINV`, `SPRINC`, `SPRIND`, `ROTSIG`, the SMA arrays, …):

```bash
python3 tools/build_ccx_umat.py --src CalculiX/ccx_2.23/src -o ccx_umat umat_deck.for
```

`--stretch` hands the UMAT U in place of DFGRD0 and DFGRD1 (see below), `--uexternaldb` calls
its `UEXTERNALDB` as Abaqus does, `--patch` and `--fflags` port Intel Fortran source.

Then `abq2ccx --abaqus-umat --run --ccx ./ccx_umat model.inp` converts and runs the deck.
Built this way with an elastic and a J2 UMAT (isotropic hardening, radial return), cantilevers
of ten element types bent past yield give exactly the reactions, displacements and stresses of
the same models with `*ELASTIC` and `*PLASTIC`, and with NLGEOM within 4e-5 of ccx's own
plasticity; without step 1 the NLGEOM J2 cantilever's tip reaction ends 70 % low. Under
`ABAQUSNL` the strain and stress come in axes that turn with the material, while DFGRD0,
DFGRD1 and DROT are global: a UMAT that builds its stress from DFGRD1 (hyperelastic, crystal
plasticity) must use the right stretch U (DFGRD1 = R U) in its place, and one that turns its
tensor state variables by DROT (`ROTSIG`) must leave them unturned (a neo-Hookean UMAT in
simple shear 0.4: 37 % off ccx's own law from DFGRD1, exact from U). A UMAT's plane-stress
branch (NDI = 2) never runs: ccx calls it in 3-D on plane-stress, membrane and shell elements.

A ccx built with `-DCALCULIX_EXTERNAL_BEHAVIOURS_SUPPORT` (`src/Makefile_MFront`) loads the
UMAT from a shared library instead: rename the material `@ABAQUS_<LIB>_<FUNCTION>` for the
function `<FUNCTION>` in `lib<LIB>.so` (ccx manual 8.5); a stock build has no such support.

A `TYPE=THERMAL` user material always goes to `umatht.f` (Abaqus' UMATHT arguments first; ccx
uses only FLUX and DFDG). ccx has no VUMAT interface: an Abaqus/Explicit deck's user material
must be ported to a UMAT, and the option leaves it alone.

## Recommended workflow

1. **Export a flat deck if you can** (Abaqus/CAE: *Do not use parts and assemblies*). The
   converter flattens assemblies (turned instances included: `validate_with_ccx.py`
   compares one with the same model written flat), but a flat deck has less to convert.
2. **Convert and read the report.** Every `[WARNING]` and `[NOTE]` is there for a reason.
3. **Resolve commented cards.** A card emitted as `** abq2ccx: …` has no CalculiX
   equivalent and needs remodelling; the comment says how.
4. **Run ccx and check the results.** Field output is in `<job>.frd`; history output for a
   set is in `<job>.dat`, as are node sets the `.frd` cannot show (beam and shell nodes —
   ccx writes such models expanded to 3-D — and reference points). After a clean run,
   `--run` prints a digest of each step to set beside your Abaqus results: the largest |U|
   and von Mises stress and their node, the reaction (sum of RF) at each `*BOUNDARY`,
   eigenfrequencies or buckling factors, the time reached
   ([output reference](output-reference.md#results-digest---run)). In an assembly a ccx
   label is the Abaqus label plus its instance's offset, as the report's instance map
   lists, and the digest names nodes and sets `Instance.label`. If ccx stops, see
   [troubleshooting](troubleshooting.md). `python validate_with_ccx.py` checks your ccx
   end to end on the bundled examples.

## Reading the conversion report

* **`[NOTE]`** — a routine translation you should know about (a parameter dropped, a
  variable renamed, a default applied). Usually nothing to do.
* **`[WARNING]`** — something that may be wrong or needs your judgement: an element with no
  exact equivalent, an unresolved overconstraint, a card commented out, a load that could not
  be converted.

An entry about one card starts with where the card is: `[WARNING] mesh/part.inp:120: ...`
(an `*INCLUDE` file relative to the deck's folder; lines count as the file has them). A card
the converter makes from another, such as an instance's copy of its part's cards, points to
that card. Messages are de-duplicated. A clean conversion says *"No conversion issues were flagged."*

| Message | Meaning and action |
| --- | --- |
| `Reduced physics — ccx solves a different model than this Abaqus deck: …` | the last warning, naming what the conversion dropped or replaced (a material behaviour, an element formulation, a constraint, a load, …); ccx runs, but its results are not the deck's own solution — remodel what the warnings above name |
| `Element X -> Y: the same solution — …` | an exact node-count-preserving swap (a note); nothing to do |
| `Element X -> Y: ccx has no X, and Y is a different element formulation …` | a stand-in with other physics (reduced physics); check that Y suits your problem |
| `… has NO CalculiX equivalent … emitted unchanged` | a cohesive or gasket element, or a `ROTARYI` that is not on a rigid body; the deck won't run until it is remodelled |
| `Analytical rigid surface … not converted` | it would only be facets (or has no rigid body): it, its rigid body and its contact pairs and ties are commented out; `--approximate` meshes it |
| `*KEYWORD … emitted as a comment` | no equivalent; the original is kept as `**` comments for you to edit |
| `Step N is loaded in the Abaqus deck …, but no load survives the conversion` | every load of that step was commented out; ccx would solve it with no load — see the step's other warnings |
| `Possible overconstraint: node N DOF d …` | a `*BOUNDARY` on a DOF that an `*EQUATION`, `*MPC` or rigid body eliminates, which the converter could not resolve exactly; ccx will stop. The message says what Abaqus does and whether `--approximate` resolves it |
| `*BOUNDARY taken off …` / `… moved to the reference node … Exact.` | BCs on rigid-constraint members resolved the way Abaqus does; nothing to do |
| `*BOUNDARY, TYPE=VELOCITY … start of the step is unknown` | the DOF was free before the step, so its displacement there is unknown: a zero velocity became `*BOUNDARY, FIXED`, anything else was commented out — prescribe a displacement, or constrain the DOF in the earlier step |
| `*BOUNDARY (displacement) with a nonzero value and no AMPLITUDE in an explicit step` | Abaqus/Explicit ignores that value and holds the DOF, so nothing moves — in Abaqus too; give the BC an amplitude if the DOF should move |
| `… Kept as given: ccx moves the DOF to that value at once` / `… on a node with a *TRANSFORM, on a DOF that had no BC before the step` | ccx cannot hold or ramp that displacement BC the way Abaqus does, so the DOF jumps to the given value; give the BC an amplitude in the Abaqus deck |
| `Transient *COUPLED TEMPERATURE-DISPLACEMENT … Densities and *MASS values divided by 1e+30 …` | ccx solves this step with inertia, Abaqus/Standard without; the masses were scaled away and what multiplies them (specific heat, GRAV, CENTRIF) scaled back, so only the inertia changed. Nothing to do; expect such numbers in the deck, and no kinetic energy |
| `… The masses were not scaled away because …` | the deck also has a dynamic or eigenvalue step, which needs the mass (ccx has one density per material for all steps), or a mass value the converter cannot read: the coupled steps keep inertia Abaqus does not have. Run them in a deck of their own, or give the value as a number |
| `… a mechanical load without AMPLITUDE … or a BC that *BOUNDARY, OP=NEW releases, jumps at the start of the step` | ccx overshoots such a jump by 5 % at the step's first increment (0.3 % at the second), where Abaqus is in equilibrium; a plastic material keeps the overshoot. Check the first increments |
| `… member(s) reference undefined …` | a set named ids that don't exist; check upstream renumbering if the count surprises you |
| `Duplicate node/element id(s) …` | the deck defines an id twice; the last one wins, as in Abaqus |

### Names the converter adds

Everything the converter creates starts with `ABQ2CCX_`:

| Name | What it is |
| --- | --- |
| `ABQ2CCX_ALL_NODES`, `ABQ2CCX_ALL_ELEMENTS` | whole-model sets (output requests without a set, default initial temperatures) |
| `ABQ2CCX_KNOT` | the force-free *knot beams* on shell and beam nodes that carry rigid couplings or rotational BCs; ignore them in the results |
| `ABQ2CCX_PLANAR` | the nodes of a planar model held in its plane |
| `ABQ2CCX_SLAB` | the nodes of `CPS4I`/`CPE4I` elements written as one-element-thick `C3D8I` slabs, held in DOF 3; a plane-stress slab's material is `<material>_PLANE_STRESS` |
| `ABQ2CCX_RIGID` | the force-free skin elements, and their material, that stand for rigid elements and meshed analytical surfaces; ignore them in the results |
| `ABQ2CCX_RS*`, `ABQ2CCX_AS*`, `ABQ2CCX_STAR*` | the skins a surface uses, a meshed analytical surface, and the point masses of a rigid body's rotary inertia |
| `ABQ2CCX_RB*`, `ABQ2CCX_MPCB*`, `ABQ2CCX_KC*`, `ABQ2CCX_TIED*` | node sets and surfaces of rigid bodies, `*MPC BEAM` bodies, kinematic couplings and tied contact pairs |
| `ABQ2CCX_BC*` | node subsets of a BC card that the converter partly moved or removed |
| `ABQ2CCX_TR*`, `ABQ2CCX_OR*`, `ABQ2CCX_PLY*`, `ABQ2CCX_AXES*` | synthesized `*TRANSFORM` node sets and `*ORIENTATION`s (spherical transforms, rotation-node axes, composite ply angles and directions, shell, membrane and continuum-shell material directions) |
| `<elset>_P<k>`, `<elset>_AX<k>` | the element groups of a composite / plain shell or membrane section whose material directions are written group by group |
| `<elset>_PLY<k>`, `…_ORI`, `…_AXES`; `<set>_S<k>_PLIES` | the ply solids of a composite continuum-shell section from ply `k` on (one material and layer angle), their orientation and per-element axes (a plain section's: `<elset>_ORI`, `<elset>_AXES`); the ply faces a surface or face load names |
| `ABQ2CCX_VEL*`, `ABQ2CCX_ACC*` | amplitudes that integrate velocity and acceleration BCs |
| `ABQ2CCX_TP*`, `ABQ2CCX_OUTPUT*` | generated `*TIME POINTS` and output node sets |
| `ABQ2CCX_<material>` | a `*USER MATERIAL` whose name would make ccx run one of its own routines, renamed so ccx stops instead |

Two names are ccx's own: `AMPLITUDE=RAMP12357111317` on a `*BOUNDARY` is ccx's step ramp, which
the converter uses where Abaqus/Standard ramps a displacement BC that ccx would apply at once,
and the `ABAQUS`/`ABAQUSNL` in front of a user material's name with `--abaqus-umat`.

Edit the Abaqus deck and convert again rather than editing these by hand.

## Python API

```python
import abq2ccx

result = abq2ccx.convert_file("model.inp", solid_dof=False, approximate=False, abaqus_umat=False)
# or: abq2ccx.convert_text(deck_string, base_dir=".")  — *INCLUDE paths relative to base_dir

result.text           # the converted deck, report header included
result.body           # the deck lines without the header
result.report         # .summary(), .entries: [(level, message)], .where: {entry index:
                      # "file:line"}, .n_warnings, .n_notes, .instances: an assembly's instance map
result.geometry       # the flattened, expanded model: .nodes, .elements, .nsets, .elsets
result.ok             # False if nothing could be converted
```

The lower-level pieces are `read_blocks(path, report)` (parse, follow `*INCLUDE`) and
`Converter(report, Options(solid_dof, approximate, abaqus_umat)).convert(blocks)`; the
[architecture guide](architecture.md) describes them. `classify_ccx_run(returncode, stdout,
stderr, job)` is the solve judge that `--run`, `validate_with_ccx.py` and the corpus tests
share; `ccx_results_digest(job)` is the digest `--run` prints, and `frd_index`, `frd_rows`
and `dat_blocks` read ccx's result files.

## What is and isn't converted

Static, frequency, buckling, implicit and explicit dynamic, steady-state dynamic, heat
transfer and coupled temperature–displacement analyses of solids, shells and beams are well
covered, with the common materials, orientations and composite layups (linear composite
shells run as `S8R`/`S6`, composite continuum shells as one `C3D8I`/`C3D6` per ply), sets,
surfaces, BCs, loads, ties, equations, couplings, rigid bodies, rigid elements and analytical
rigid surfaces, and connectors without a behaviour. Contact is translated card by card, but ccx's
penalty contact behaves differently — check it. User subroutines, connector behaviours,
gaskets, inertia relief, Riks and some specialised materials and procedures have no
equivalent and are flagged for manual work.

The generated references list every case: [keywords](keyword-reference.md),
[elements](element-reference.md), [output variables](output-reference.md).
