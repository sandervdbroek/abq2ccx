# User guide

## Requirements

* Python 3.9 or later, standard library only. The whole tool is `abq2ccx.py`; copy it
  anywhere or run it from the repository, or install it as the `abq2ccx` command with
  `pipx install abq2ccx`, or the latest main with
  `pipx install git+https://github.com/sandervdbroek/abq2ccx` (`pip install .` in a clone).
* CalculiX (`ccx`) only to run the result. `--run` and `validate_with_ccx.py` take `$CCX`
  (`--run` also `--ccx PATH`), else look on `PATH`, then in FreeCAD (FreeCAD 1.1.4 ships ccx
  2.23), PrePoMax and bConverged installs on Windows, and in FreeCAD's macOS bundle and
  Homebrew/MacPorts elsewhere. A conda environment's ccx on Windows needs no `conda activate`:
  it runs with the folders activation would put on `PATH`. `--run` prints the version it runs
  and warns if it is not 2.22 or 2.23, the versions the converter targets.

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
| `--json` | print a machine-readable report on stdout |
| `--run` | run CalculiX on the result and print a digest of its results |
| `--ccx PATH` | the CalculiX executable for `--run` (`$CCX` works too) |
| `--no-log`, `--quiet` | write no `.log` file; print no report on stderr |
| `--version`, `-h` | version; help |

**Exit codes:** `0` converted · `1` cannot read or write, or `--run` failed · `2` usage
error · `3` `--strict` findings · `4` internal conversion error. `--run` fails when ccx
stops with an `*ERROR`, crashes, writes NaN/Inf results or runs a step that sets up no
equations — ccx 2.23 ends a diverged solution, and such a step, with "Job finished" all the
same, so `--run` reads the results and names the first NaN/Inf value, or the step.

**Outputs:** `<output>.inp`, the CalculiX deck, with the report as `**` comments at the
top; `<output>.log`, the same report as text; and a one-line summary plus the report on
stderr. Run the deck with `ccx <output>` (no `.inp` extension).

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
  and `B31R` (the same `C3D8R` hourglass stiffness) → `CPS4`, `CPE4`, `CAX4`, `M3D4`, `B31`.

## `--abaqus-umat`

ccx picks the routine for a `*USER MATERIAL` by the start of the material name. Without the
option, a material whose name would pick one of ccx's own routines (`USER…`, `ABAQUS…`,
`JOHNSONCOOK…`, …) is renamed `ABQ2CCX_<name>`, so ccx stops with "no user material
subroutine" instead of running another material. With it, every mechanical user material
becomes `ABAQUS<name>` for ccx's Abaqus-UMAT interface (small strain), or `ABAQUSNL<name>` in
a deck with NLGEOM steps (logarithmic strain); a note names each UMAT argument ccx supplies
differently ([compatibility](compatibility.md#materials)). A stock ccx runs its linear-elastic
example there, so build one with the deck's UMAT:

1. Unpack the ccx 2.23 sources (`ccx_2.23.src.tar.bz2`, <https://www.dhondt.de>) and build
   SPOOLES 2.2 (`make lib`, with `CC` set in `Make.inc` and `drawTree.c` renamed `draw.c` in
   `Tree/src/makeGlobalLib`) and ARPACK, without which ccx 2.23 does not link.
2. Save the deck's UMAT as `src/umat.f` in place of ccx's example (the routine is `umat`, with
   Abaqus' arguments), next to an `ABA_PARAM.INC` holding `implicit real*8(a-h,o-z)` and
   `parameter (nprecd=2)`. ccx has no Abaqus utility routines (`XIT`, `SINV`, `SPRINC`,
   `ROTSIG`, …): supply those it calls.
3. `make ccx_2.23` in `src` with gfortran, a LAPACK in `LIBS` (ccx calls `dgesv`; give
   libraries as file paths, as the Makefile also lists them as prerequisites), and run the
   converted deck with the new `ccx_2.23`. On macOS with Homebrew's gcc 13, compile the C
   files with Apple clang (`-Wno-int-conversion -Wno-incompatible-pointer-types
   -Wno-implicit-function-declaration -Wno-implicit-int -Wno-return-mismatch`, SPOOLES also
   `-std=gnu89`) and link with `SDKROOT=$(xcrun --show-sdk-path)`.

Built this way with a J2 UMAT (isotropic hardening, radial return), a `C3D8` and a `CPE4`
cantilever bent well past yield give exactly the reactions and stresses of the same models with
`*ELASTIC` and `*PLASTIC`.

A ccx built with `-DCALCULIX_EXTERNAL_BEHAVIOURS_SUPPORT` (`src/Makefile_MFront`) loads the
UMAT from a shared library instead: rename the material `@ABAQUS_<LIB>_<FUNCTION>` for the
function `<FUNCTION>` in `lib<LIB>.so` (ccx manual 8.5); FreeCAD's ccx has no such support.
In ccx 2.23 `umat_abaqusnl.f` never sets U0, so under `ABAQUSNL` a UMAT that adds to the
stress it gets (plasticity, damage) goes wrong: under NLGEOM that J2 cantilever's tip reaction
stayed near its first increment's value, 70 % low at the end. Set U0 after the first
`um1(3,2)=um1(2,3)` line, and it matches ccx's own plasticity to 2e-5:

```fortran
      do jj=1,6
        u0(kal(1,jj),kal(2,jj))=xm1(jj)/wum1(1)+xm2(jj)/wum1(2)
     &       +xm3(jj)/wum1(3)
        u0(kal(2,jj),kal(1,jj))=u0(kal(1,jj),kal(2,jj))
      enddo
```

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

Messages are de-duplicated. A clean conversion says *"No conversion issues were flagged."*

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
result.report         # .summary(), .entries: [(level, message)], .n_warnings, .n_notes,
                      # .instances: an assembly's instance map
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
