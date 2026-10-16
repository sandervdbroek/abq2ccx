#!/usr/bin/env python3
"""
abq2ccx.py -- Convert Abaqus ``.inp`` files to CalculiX (CCX) ``.inp`` files.

CalculiX deliberately mimics the Abaqus input syntax, so a large fraction of a
deck can be passed through unchanged.  The job of this converter is to handle
the parts that *differ*:

  * Mesh-generation cards (``*NCOPY``, ``*NGEN``, ``*NFILL``, ``*ELGEN``,
    ``*ELCOPY``) do not exist in CalculiX, so they are expanded into explicit
    ``*NODE`` / ``*ELEMENT`` blocks.
  * ``*PART`` / ``*INSTANCE`` / ``*ASSEMBLY`` do not exist in CalculiX, so an
    assembly is flattened into a single global node/element numbering (applying
    each instance's translation/rotation).
  * Keyword / parameter / data differences are translated (see the per-keyword
    handlers below and the README for the full mapping table).

Anything the converter does not understand is passed through unchanged and
flagged in the conversion report, so the output is a starting point you should
always check against your target ``ccx`` version.

The CalculiX syntax used here was verified against the CalculiX CrunchiX user
manual (v2.7 HTML / v2.22 PDF, dhondt.de).  Where a feature is version
dependent it is noted in the report and the README.

Usage
-----
    python3 abq2ccx.py model.inp               # -> model_ccx.inp (+ model_ccx.log)
    python3 abq2ccx.py decks/*.inp --outdir out   # batch convert
    python3 abq2ccx.py model.inp --run         # convert + run CalculiX on the result
    python3 abq2ccx.py model.inp --check --json   # dry-run, machine-readable report
    python3 abq2ccx.py model.inp --approximate    # opt-in physics approximations
    python3 abq2ccx.py model.inp --solid-dof   # force translational-only ENCASTRE

This file is intentionally a single self-contained script (no dependencies
beyond the Python standard library) so it is trivial to drop into a project or
run on a cluster.
"""

from __future__ import annotations

import argparse
import ast
import bisect
import glob
import itertools
import json
import math
import operator
import os
import re
import shutil
import subprocess
import sys
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterator, List, Optional, Sequence, Tuple, Union

__version__ = "1.1.0"

# ---------------------------------------------------------------------------
# Element reference data
# ---------------------------------------------------------------------------

# Number of connectivity nodes per element type.  Used to read connectivity across
# continuation lines and to classify elements.  Covers both CalculiX-native types
# and Abaqus types we substitute or warn about (so connectivity always parses).
ELEMENT_NNODES: Dict[str, int] = {
    # 3-D continuum (+ hybrid/modified Abaqus variants)
    "C3D4": 4, "C3D4H": 4, "C3D6": 6, "C3D6H": 6,
    "C3D8": 8, "C3D8R": 8, "C3D8I": 8, "C3D8H": 8, "C3D8RH": 8, "C3D8IH": 8,
    "C3D10": 10, "C3D10H": 10, "C3D10M": 10, "C3D10MH": 10, "C3D10HS": 10, "C3D10T": 10,
    "C3D15": 15, "C3D15H": 15, "C3D20": 20, "C3D20R": 20, "C3D20RI": 20,
    "C3D20H": 20, "C3D20RH": 20,
    # CFD / network
    "F3D4": 4, "F3D6": 6, "F3D8": 8, "F3D10": 10, "F3D15": 15, "F3D20": 20, "D": 3,
    # shells (+ continuum shells + heat-transfer shells)
    "S3": 3, "S3R": 3, "STRI3": 3, "STRI65": 6, "US3": 3,
    "S4": 4, "S4R": 4, "S4R5": 4, "S6": 6, "S8": 8, "S8R": 8, "S8R5": 8, "S9R5": 9,
    "SC6R": 6, "SC8R": 8, "DS3": 3, "DS4": 4, "DS6": 6, "DS8": 8,
    # plane stress / plane strain / generalized / axisymmetric
    "CPS3": 3, "CPS4": 4, "CPS4R": 4, "CPS4I": 4, "CPS6": 6, "CPS6M": 6, "CPS8": 8, "CPS8R": 8,
    "CPE3": 3, "CPE4": 4, "CPE4R": 4, "CPE4I": 4, "CPE4H": 4, "CPE6": 6, "CPE6M": 6, "CPE8": 8,
    "CPE8R": 8, "CPE8H": 8,
    "CPEG3": 3, "CPEG4": 4, "CPEG4R": 4, "CPEG6": 6, "CPEG6M": 6, "CPEG8": 8, "CPEG8R": 8,
    "CAX3": 3, "CAX4": 4, "CAX4R": 4, "CAX4H": 4, "CAX6": 6, "CAX6M": 6, "CAX8": 8, "CAX8R": 8, "CAX8H": 8,
    "CGAX3": 3, "CGAX4": 4, "CGAX4R": 4, "CGAX6": 6, "CGAX8": 8, "CGAX8R": 8,
    # membranes
    "M3D3": 3, "M3D4": 4, "M3D4R": 4, "M3D6": 6, "M3D8": 8, "M3D8R": 8, "M3D9": 9, "M3D9R": 9,
    # beams / trusses / pipes
    "B21": 2, "B21H": 2, "B22": 3, "B23": 2, "B31": 2, "B31R": 2, "B31H": 2, "B32": 3,
    "B32R": 3, "B32H": 3, "B33": 2, "B33H": 2,
    "PIPE21": 2, "PIPE22": 3, "PIPE31": 2, "PIPE32": 3,
    "T2D2": 2, "T2D3": 3, "T3D2": 2, "T3D3": 3,
    # springs / dashpots / gaps / mass / coupling
    "SPRING1": 1, "SPRING2": 2, "SPRINGA": 2, "DASHPOT1": 2, "DASHPOT2": 2, "DASHPOTA": 2,
    "GAPUNI": 2, "GAPCYL": 2, "GAPSPHER": 2, "MASS": 1, "ROTARYI": 1, "DCOUP3D": 1,
    # cohesive / gasket (approximated by a thin continuum) / connector / rigid
    "COH2D4": 4, "COH3D6": 6, "COH3D8": 8, "COHAX4": 4, "CONN3D2": 2, "CONN2D2": 2,
    "GK3D8": 8, "GK3D6": 6, "GK2D4": 4, "GK2D6": 6, "GKPS4": 4, "GKPS6": 6, "GKAX4": 4, "GKAX6": 6,
    "R3D3": 3, "R3D4": 4, "RB2D2": 2, "RB3D2": 2, "RAX2": 2,
    # heat-transfer continuum (Abaqus-compatible names accepted by ccx)
    "DC3D4": 4, "DC3D6": 6, "DC3D8": 8, "DC3D10": 10, "DC3D15": 15, "DC3D20": 20,
    "DC1D2": 2, "DC1D3": 3,
    # surface elements (load carriers without stiffness; see SURFACE_ELEMENTS)
    "SFM3D3": 3, "SFM3D4": 4, "SFM3D4R": 4, "SFM3D6": 6, "SFM3D8": 8, "SFM3D8R": 8,
    "SFMAX1": 2, "SFMAX2": 3, "SFMGAX1": 2, "SFMGAX2": 3,
}

# Abaqus surface elements: no stiffness of their own ("membrane elements with zero
# thickness"), used to carry distributed loads, mass per unit area (*SURFACE SECTION,
# DENSITY=) or rebar layers.  ccx has no such element ("*ERROR reading *ELEMENT"), so as pure
# load carriers they leave the mesh and their loads become nodal forces (see
# Converter._drop_surface_elements).  The 3-D ones are faces (corners, then midside nodes),
# the axisymmetric ones edges (end, middle, end; SFMGAX twist as in CGAX -> CAX).
SURFACE_ELEMENTS = {"SFM3D3", "SFM3D4", "SFM3D4R", "SFM3D6", "SFM3D8", "SFM3D8R",
                    "SFMAX1", "SFMAX2", "SFMGAX1", "SFMGAX2"}

# Element types CalculiX has no native name for -> substitute.  Every entry is
# NODE-COUNT PRESERVING so connectivity stays valid (a warning is emitted on use).
ELEMENT_TYPE_MAP: Dict[str, str] = {
    "S3R": "S3", "STRI3": "S3", "STRI65": "S6", "S4R5": "S4R", "S8R5": "S8R",
    "B23": "B33", "B22": "B32", "B33": "B31", "B33H": "B31",          # no cubic/2-node-2D beams
    "T2D3": "T3D3",                                                   # 3-node 2D truss -> 3-node 3D truss
    "B21H": "B21", "B31H": "B31", "B32H": "B32",                      # hybrid beams
    "PIPE21": "B21", "PIPE22": "B32", "PIPE31": "B31", "PIPE32": "B32",  # internal pressure lost
    "CPEG3": "CPE3", "CPEG4": "CPE4", "CPEG4R": "CPE4R", "CPEG6": "CPE6",  # gen. plane strain
    "CPEG8": "CPE8", "CPEG8R": "CPE8R",
    "CGAX3": "CAX3", "CGAX4": "CAX4", "CGAX4R": "CAX4R", "CGAX6": "CAX6",  # gen. axisym (twist lost)
    "CGAX8": "CAX8", "CGAX8R": "CAX8R",
    "SC6R": "C3D6", "SC8R": "C3D8I",                                  # continuum shells -> solids
    "C3D10M": "C3D10", "C3D10MH": "C3D10", "C3D10HS": "C3D10",
    "CPS6M": "CPS6", "CPE6M": "CPE6", "CAX6M": "CAX6", "CPEG6M": "CPE6",  # modified 6-node tris
    "DASHPOT1": "DASHPOTA", "DASHPOT2": "DASHPOTA",
    "GAPCYL": "GAPUNI", "GAPSPHER": "GAPUNI",
    "CPS4I": "CPS4", "CPE4I": "CPE4",
    # hybrid continuum -> non-hybrid base (ccx has no mixed u/p formulation)
    "C3D4H": "C3D4", "C3D6H": "C3D6", "C3D8H": "C3D8", "C3D8RH": "C3D8R", "C3D8IH": "C3D8I",
    "C3D10H": "C3D10", "C3D15H": "C3D15", "C3D20H": "C3D20", "C3D20RH": "C3D20R",
    "CPE4H": "CPE4", "CPE8H": "CPE8", "CAX4H": "CAX4", "CAX8H": "CAX8",
    # cohesive / gasket: ccx has no such formulation, so approximate each by the
    # node-count-identical CONTINUUM element (a thin bonded/compressed layer).  The
    # special behaviour is lost and a ZERO-thickness layer fails — ccx_element_type
    # emits a strong, targeted warning for these (COH*/GK* prefixes).
    # (6-node 2D gaskets GK2D6/GKPS6/GKAX6 are deliberately NOT mapped: they are
    # quad-like top/bottom stacks, while CPE6/CPS6/CAX6 are quadratic TRIANGLES —
    # reinterpreting the connectivity would garble the geometry.)
    "COH3D8": "C3D8", "COH3D6": "C3D6", "COH2D4": "CPE4", "COHAX4": "CAX4",
    "GK3D8": "C3D8", "GK3D6": "C3D6", "GK2D4": "CPE4",
    "GKPS4": "CPS4", "GKAX4": "CAX4",
}

# Element types CalculiX supports directly (verified, ccx 2.22).  Used to tell a
# direct passthrough from one needing substitution / a warning.
CCX_ELEMENTS = {
    "C3D4", "C3D6", "C3D8", "C3D8R", "C3D8I", "C3D10", "C3D10T", "C3D15", "C3D20",
    "C3D20R", "C3D20RI", "F3D4", "F3D6", "F3D8", "D",
    "S3", "S4", "S4R", "S6", "S8", "S8R", "US3",
    "M3D3", "M3D4", "M3D4R", "M3D6", "M3D8", "M3D8R",
    "CPS3", "CPS4", "CPS4R", "CPS6", "CPS8", "CPS8R",
    "CPE3", "CPE4", "CPE4R", "CPE6", "CPE8", "CPE8R",
    "CAX3", "CAX4", "CAX4R", "CAX6", "CAX8", "CAX8R",
    "B21", "B31", "B31R", "B32", "B32R", "T2D2", "T3D2", "T3D3",
    "SPRING1", "SPRING2", "SPRINGA", "DASHPOTA", "GAPUNI", "MASS", "DCOUP3D",
    "DC3D4", "DC3D6", "DC3D8", "DC3D10", "DC3D15", "DC3D20", "U1",
}
# Element families with no geometric CalculiX equivalent at all.
UNSUPPORTED_ELEM_PREFIXES = ("COH", "GK", "GKPS", "GKAX", "CONN", "ROTARYI")

# Integration points per (emitted ccx) element type — empirically probed against ccx 2.22
# by counting *EL PRINT stress rows on single-element decks.  NOTE the 2D counts are the
# counts of the internally EXPANDED 3D elements (ccx expands plane/axisym to bricks and
# wedges: CPS4 -> 8 like C3D8, CPS8 -> 27 like C3D20, CPS3 -> 2 like C3D6), which is what
# *INITIAL CONDITIONS, TYPE=STRESS/... addresses.
ELEMENT_IP_COUNT = {
    "C3D4": 1, "C3D6": 2, "C3D8": 8, "C3D8R": 1, "C3D8I": 8, "C3D10": 4, "C3D10T": 4,
    "C3D15": 9, "C3D20": 27, "C3D20R": 8, "C3D20RI": 8,
    "CPS3": 2, "CPS4": 8, "CPS4R": 1, "CPS6": 9, "CPS8": 27, "CPS8R": 8,
    "CPE3": 2, "CPE4": 8, "CPE4R": 1, "CPE6": 9, "CPE8": 27, "CPE8R": 8,
    "CAX3": 2, "CAX4": 8, "CAX4R": 1, "CAX6": 9, "CAX8": 27, "CAX8R": 8,
}


def element_node_count(typ: str) -> Optional[int]:
    """Node count used to parse connectivity, tolerant of the coupled-temperature ``T``,
    hybrid ``H`` and pore-pressure ``P`` suffixes (none changes the node count, e.g.
    ``C3D8T``, ``CAX4RT``, ``C3D20HT``, ``CAX4P`` all match their base's count)."""
    typ = typ.upper()
    if typ in ELEMENT_NNODES:
        return ELEMENT_NNODES[typ]
    if typ in ELEMENT_TYPE_MAP:                 # mapped types keep their node count
        return ELEMENT_NNODES.get(ELEMENT_TYPE_MAP[typ])
    base = typ
    while base and base[-1] in ("T", "H", "P"):
        base = base[:-1]
        if base in ELEMENT_NNODES:
            return ELEMENT_NNODES[base]
        if base in ELEMENT_TYPE_MAP:
            return ELEMENT_NNODES.get(ELEMENT_TYPE_MAP[base])
    return None


def ccx_element_type(typ: str, report: "Report") -> str:
    """Return the CalculiX element name for an Abaqus type, substituting where
    needed (node-count preserving) and warning on anything not directly supported."""
    typ = typ.upper()
    if typ in ELEMENT_TYPE_MAP:
        sub = ELEMENT_TYPE_MAP[typ]
        seen = {typ}
        while sub not in CCX_ELEMENTS and sub in ELEMENT_TYPE_MAP and sub not in seen:
            seen.add(sub)                       # e.g. B23 -> B33 -> B31
            sub = ELEMENT_TYPE_MAP[sub]
        if typ.startswith(("COH", "GK")):
            report.warn(f"Element {typ} has no ccx formulation; approximated by the continuum "
                        f"element {sub} (node-count-preserving, runs as a thin elastic layer). The "
                        f"cohesive/gasket behaviour (separation/closure) is LOST, and a ZERO-thickness "
                        f"layer fails with a nonpositive-jacobian error — give the layer a small finite "
                        f"thickness or remodel with contact/*SPRING. Verify the result.", once=True)
        else:
            report.warn(f"Element {typ} -> {sub} (no native CalculiX type; node-count-preserving "
                        f"substitution — verify it is acceptable).", once=True)
        return sub
    if typ in CCX_ELEMENTS:
        return typ
    # Suffix elements — coupled-temperature ``T``, hybrid ``H``, pore-pressure ``P`` — in
    # any combination (C3D8T, CAX4RP, C3D8PT, C3D20RHT): strip trailing suffix letters
    # until a known base is reached, warn once per dropped capability, and resolve the
    # base (which may itself need mapping, e.g. C3D10MT -> C3D10M -> C3D10).
    base, dropped = typ, ""
    while len(base) > 1 and base[-1] in "THP" and \
            base not in CCX_ELEMENTS and base not in ELEMENT_TYPE_MAP:
        dropped += base[-1]
        base = base[:-1]
    if dropped and (base in CCX_ELEMENTS or base in ELEMENT_TYPE_MAP):
        if "T" in dropped:
            report.warn(f"Element {typ} -> {base} (CalculiX uses the base element for coupled "
                        f"temperature-displacement; the temperature DOF comes from the step).", once=True)
        if "H" in dropped:
            report.warn(f"Element {typ} -> {base} (CalculiX has no hybrid formulation).", once=True)
        if "P" in dropped:
            report.warn(f"Element {typ} -> {base}: ccx has no pore-pressure (coupled u-p) element; "
                        f"the pore-pressure DOF is dropped and only the mechanical response is solved — "
                        f"consolidation/seepage is NOT modelled. Verify.", once=True)
        return ccx_element_type(base, report)
    if typ in SURFACE_ELEMENTS:                 # only when the conversion had to keep them
        report.warn(f"Element {typ} is an Abaqus surface element; ccx has none and stops with "
                    f"'*ERROR reading *ELEMENT' (see the warning on why the conversion kept it).",
                    once=True)
        return typ
    if typ.startswith(("R3D", "RB2", "RB3", "RAX", "R2D")):
        report.warn(f"Element {typ} is a rigid (R3D/RB) element; ccx has no rigid element — define "
                    f"the region as a *RIGID BODY (NSET + REF NODE/ROT NODE) instead. Emitted "
                    f"unchanged.", once=True)
        return typ
    if typ.startswith(UNSUPPORTED_ELEM_PREFIXES):
        report.warn(f"Element {typ} (cohesive/gasket/connector/rotary-inertia) has NO CalculiX "
                    f"equivalent; emitted unchanged. Remodel with contact, *SPRING/*GAP, *MPC or "
                    f"*MASS — the deck will not run until this is addressed.", once=True)
        return typ
    report.warn(f"Element {typ} is unknown to this converter; emitted unchanged — confirm your "
                f"ccx version supports it.", once=True)
    return typ


SHELL_TYPES = {t for t in ELEMENT_NNODES if (t[0] == "S" and not t.startswith("SPRING")) or t.startswith("DS")}
BEAM_TYPES = {t for t in ELEMENT_NNODES if t[0] == "B" or t.startswith(("T2D", "T3D", "PIPE"))}
COMPOSITE_SHELL_OK = {"S6", "S8R"}  # CalculiX restricts composite shells to these
# ccx 2.23 stops on a 2-node beam with a circular section ("Please use quadratic elements
# for beams with circular cross section"): it expands a linear beam into an 8-node brick,
# whose corner nodes cannot follow a circle.  Emitted 2-node type -> the 3-node beam such
# elements are upgraded to (ccx runs B21 as a B31).
CIRC_QUADRATIC = {"B21": "B32", "B31": "B32", "B31R": "B32R"}
# ccx 2.23 accepts PIPE and BOX sections only on B32R ("*BEAM SECTION of type PIPE can only
# be used for B32R elements"): their integration-point schemes are defined on the expanded
# C3D20R.  Emitted type -> B32R; a 2-node beam gets a midside node, B32 changes type only.
PIPE_BOX_B32R = {"B21": "B32R", "B31": "B32R", "B31R": "B32R", "B32": "B32R"}
# *BEAM SECTION, SECTION= -> the upgrade its beams need (THICK PIPE is emitted as PIPE)
SECTION_BEAM_UPGRADE = {"CIRC": CIRC_QUADRATIC, "PIPE": PIPE_BOX_B32R, "THICK PIPE": PIPE_BOX_B32R,
                        "BOX": PIPE_BOX_B32R}

MAX_ENTRIES_PER_LINE = 16  # CalculiX hard limit for entries on a data line

# ---------------------------------------------------------------------------
# Conversion report
# ---------------------------------------------------------------------------


class Report:
    """Collects warnings / notes emitted during conversion."""

    def __init__(self) -> None:
        self.entries: List[Tuple[str, str]] = []
        self._seen: set = set()
        self.n_commented = 0          # cards emitted as ** comments (no ccx equivalent)

    def warn(self, msg: str, once: bool = False) -> None:
        if once:
            if msg in self._seen:
                return
            self._seen.add(msg)
        self.entries.append(("WARNING", msg))

    def note(self, msg: str, once: bool = False) -> None:
        if once:
            if msg in self._seen:
                return
            self._seen.add(msg)
        self.entries.append(("NOTE", msg))

    @property
    def n_warnings(self) -> int:
        return sum(1 for level, _ in self.entries if level == "WARNING")

    @property
    def n_notes(self) -> int:
        return sum(1 for level, _ in self.entries if level == "NOTE")

    def summary(self) -> str:
        return (f"{self.n_warnings} warning(s), {self.n_notes} note(s), "
                f"{self.n_commented} commented card(s)")

    def header_comment_lines(self) -> List[str]:
        lines = ["** ====================================================================",
                 f"** Converted from Abaqus to CalculiX by abq2ccx v{__version__}",
                 f"** {self.summary()} — review below; find commented cards with '** abq2ccx:'.",
                 "** --------------------------------------------------------------------"]
        if not self.entries:
            lines.append("** No conversion issues were flagged.")
        for level, msg in self.entries:
            for i, chunk in enumerate(_wrap(msg, 66)):
                prefix = f"** [{level}] " if i == 0 else "**          "
                lines.append(prefix + chunk)
        lines.append("** ====================================================================")
        return lines

    def text(self) -> str:
        if not self.entries:
            return "No conversion issues were flagged.\n"
        return "\n".join(f"[{level}] {msg}" for level, msg in self.entries) + "\n"


def _wrap(text: str, width: int) -> List[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}" if cur else w
    if cur:
        lines.append(cur)
    return lines or [""]


# ---------------------------------------------------------------------------
# Tokenizing: raw text -> list of Block
# ---------------------------------------------------------------------------


@dataclass
class Block:
    """One keyword card and its data lines."""

    keyword: str                                   # upper-case, no leading '*', spaces kept
    params: "OrderedDict[str, Optional[str]]"      # PARAM (upper) -> value (orig case) or None
    data: List[str] = field(default_factory=list)  # raw data lines (comments/newlines stripped)
    # parsing context (Abaqus part/instance this block belongs to), if any
    part: Optional[str] = None
    instance: Optional[str] = None

    def param(self, key: str, default: Optional[str] = None) -> Optional[str]:
        return self.params.get(key.upper(), default)

    def has(self, key: str) -> bool:
        return key.upper() in self.params


# Abaqus permits unambiguous abbreviations of parameter names; CalculiX wants the
# full spelling.  Normalise the common ones that appear in real decks (an unexpanded
# ``AMP=`` on a load card is "parameter not recognized" in ccx, so the load silently
# loses its amplitude).
PARAM_ALIASES = {"GEN": "GENERATE", "PERT": "PERTURBATION", "PERTURB": "PERTURBATION",
                 "AMP": "AMPLITUDE", "POS": "POSITION"}
# Abaqus keyword abbreviations CalculiX does not accept.
KEYWORD_ALIASES = {"AMP": "AMPLITUDE"}


_KEYWORD_BY_COMPACT: Dict[str, str] = {}


def canonical_keyword(keyword: str) -> str:
    """The spelling the converter knows for ``keyword``.  ccx (like Abaqus) ignores blanks
    in keyword names, so ``*ENDSTEP`` / ``*SOLIDSECTION`` / ``*ELPRINT`` mean ``*END STEP``
    / ``*SOLID SECTION`` / ``*EL PRINT`` — unrecognised, such cards were commented out (and
    a missing *END STEP nested the next step)."""
    if not _KEYWORD_BY_COMPACT:
        known = (set(CCX_KEYWORDS) | GEOM_KW | set(DROP_KEYWORDS) | set(DROP_WARN_KEYWORDS) |
                 set(SPECIAL_UNSUPPORTED) | set(SEMANTIC_TRAP) | set(PASS_WITH_NOTE) |
                 {"KINEMATIC COUPLING", "SHELL GENERAL SECTION", "BEAM GENERAL SECTION",
                  "COHESIVE SECTION", "GASKET SECTION", "CONNECTOR SECTION", "PARAMETER",
                  "SYSTEM", "UNIT SYSTEM",
                  "DISTRIBUTING COUPLING", "RATE DEPENDENT", "INITIAL CONDITIONS",
                  "SURFACE INTERACTION", "SURFACE BEHAVIOR", "CONTACT PAIR"})
        for k in known:
            _KEYWORD_BY_COMPACT.setdefault(k.replace(" ", ""), k)
    if " " in keyword:
        return keyword
    return _KEYWORD_BY_COMPACT.get(keyword, keyword)


def parse_keyword_line(line: str) -> Tuple[str, "OrderedDict[str, Optional[str]]"]:
    """``*EL PRINT, POSITION=AVERAGED AT NODES, ELSET=EOUT`` ->
    ("EL PRINT", {"POSITION": "AVERAGED AT NODES", "ELSET": "EOUT"})."""
    tokens = _split_commas(line)
    keyword = " ".join(tokens[0].lstrip("*").split()).upper()
    keyword = KEYWORD_ALIASES.get(keyword, keyword)
    keyword = canonical_keyword(keyword)
    params: "OrderedDict[str, Optional[str]]" = OrderedDict()
    for tok in tokens[1:]:
        if not tok:
            continue
        if "=" in tok:
            key, val = tok.split("=", 1)
            key = key.strip().upper()
            params[PARAM_ALIASES.get(key, key)] = val.strip()
        else:
            key = tok.strip().upper()
            params[PARAM_ALIASES.get(key, key)] = None
    return keyword, params


def _split_commas(line: str) -> List[str]:
    """Split on commas, honouring double quotes (used by *INCLUDE file names)."""
    out, cur, q = [], [], False
    for ch in line:
        if ch == '"':
            q = not q
            cur.append(ch)
        elif ch == "," and not q:
            out.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    out.append("".join(cur))
    return out


# Constants and functions permitted inside Abaqus ``*PARAMETER`` expressions (e.g.
# ``strain = abs(stretch - 1.0)``, ``r = 2*pi``).  Constants are reachable as bare
# names; functions only as ``f(...)`` calls.  Expressions are evaluated by
# ``_safe_eval_param`` (an AST walk), NOT ``eval`` — there is no attribute/subscript
# access, so a malicious deck cannot reach ``__globals__``/``os`` and execute code.
_PARAM_EVAL_CONSTS: Dict[str, float] = {"pi": math.pi, "e": math.e}
_PARAM_EVAL_FUNCS: Dict[str, object] = {
    "abs": abs, "min": min, "max": max, "round": round, "pow": pow,
    "int": int, "float": float,
    **{k: getattr(math, k) for k in (
        "sqrt", "sin", "cos", "tan", "asin", "acos", "atan", "atan2", "exp",
        "log", "log10", "radians", "degrees", "floor", "ceil",
        "sinh", "cosh", "tanh", "fabs", "hypot")},
}
_PARAM_BINOPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
                 ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
                 ast.Mod: operator.mod, ast.Pow: operator.pow}
_PARAM_UNARYOPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def _safe_eval_param(expr: str, names: Dict[str, object]) -> object:
    """Evaluate an arithmetic ``*PARAMETER`` expression with NO attribute, subscript,
    or builtin access — so, unlike ``eval``, it cannot be coerced into running code.
    ``names`` supplies values for bare identifiers (user parameters and the math
    constants); ``_PARAM_EVAL_FUNCS`` supplies functions reachable only as ``f(...)``.
    Raises ``ValueError`` on anything outside the arithmetic grammar."""
    def ev(node: ast.AST) -> object:
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant):
            # numbers AND quoted strings: a string-valued *PARAMETER (e.g.
            # ``eltype = "CPS4"``) must resolve to its *unquoted* value so that a
            # ``<eltype>`` token substitutes to ``CPS4``, not ``"CPS4"`` (which ccx
            # would reject as an unknown element type).
            if isinstance(node.value, bool) or not isinstance(node.value, (int, float, str)):
                raise ValueError("unsupported constant")
            return node.value
        if isinstance(node, ast.Name):
            if node.id in names:
                return names[node.id]
            raise ValueError(f"unknown name {node.id!r}")
        if isinstance(node, ast.BinOp) and type(node.op) in _PARAM_BINOPS:
            return _PARAM_BINOPS[type(node.op)](ev(node.left), ev(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _PARAM_UNARYOPS:
            return _PARAM_UNARYOPS[type(node.op)](ev(node.operand))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords:
            fn = _PARAM_EVAL_FUNCS.get(node.func.id)
            if not callable(fn):
                raise ValueError(f"call to {node.func.id!r} not allowed")
            return fn(*[ev(a) for a in node.args])
        raise ValueError("unsupported expression")
    return ev(ast.parse(expr, mode="eval"))


def apply_parameters(lines: List[str], report: Report, params: Dict[str, object]) -> List[str]:
    """Resolve Abaqus ``*PARAMETER`` input: collect ``name = expr`` definitions, drop
    the ``*PARAMETER`` blocks (ccx has no such card), and substitute every ``<name>``
    token with its value.  Without this, parametric coordinates like ``<l>`` reach the
    float parser and crash.  ``params`` is shared across *INCLUDE so parameters defined
    in a master deck are visible in included files."""
    raw_defs: List[Tuple[str, str]] = []
    kept: List[str] = []
    in_param = False
    for line in lines:
        s = line.strip()
        # exactly *PARAMETER — not *PARAMETER TABLE / *PARAMETER DEPENDENCE / ..., which
        # are different cards whose data must not be swallowed as definitions
        if re.match(r"\*parameter\s*(,|$)", s, re.I):
            in_param = True
            continue
        if in_param:
            if s.startswith("**"):          # a comment inside the block does NOT end it
                continue
            if s.startswith("*"):           # the next real keyword ends the block
                in_param = False            # fall through to keep this line
            else:
                if s and "=" in s:
                    name, expr = s.split("=", 1)
                    raw_defs.append((name.strip(), expr.strip()))
                continue                    # drop parameter-definition lines
        kept.append(line)

    if raw_defs:                            # resolve, iterating to handle forward references
        user_names = {nm for nm, _ in raw_defs}
        for _ in range(len(raw_defs) + 1):
            progressed = False
            # math constants are visible, but a user parameter of the same name
            # (e.g. a deck that defines ``pi``) always wins — never shadowed.
            ns: Dict[str, object] = {k: v for k, v in _PARAM_EVAL_CONSTS.items() if k not in user_names}
            ns.update({k: v for k, v in params.items() if not isinstance(v, str)})
            for name, expr in raw_defs:
                if name in params and not isinstance(params[name], str):
                    continue
                try:
                    val = _safe_eval_param(expr, ns)
                    params[name] = val
                    ns[name] = val          # visible to later defs resolved in this same pass
                    progressed = True
                except Exception:           # noqa: BLE001 — unresolved (maybe forward ref)
                    params.setdefault(name, expr)
            if not progressed:
                break
        report.note(f"*PARAMETER: resolved {len(raw_defs)} parameter(s) and substituted <name> "
                    "tokens (ccx has no *PARAMETER).", once=True)

    if not params:
        return lines

    def sub(line: str) -> str:
        return re.sub(r"<([^<>]+)>", lambda m: str(params.get(m.group(1), m.group(0))), line)

    return [sub(ln) for ln in kept]


def join_keyword_continuations(lines: List[str]) -> List[str]:
    """Splice Abaqus keyword-parameter continuation lines back onto their keyword.

    A keyword card whose parameter list is long may end the ``*KEYWORD`` line with a
    trailing comma and continue the parameters on the following line(s), e.g.::

        *NCOPY, CHANGE NUMBER=10000, OLD SET=MIDPLANE, SHIFT,
        NEW SET=FRONT
        *ELSET, ELSET=loaded,
        GENERATE

    CalculiX (and ``parse_keyword_line``) expect all parameters on one physical line,
    so we merge them.  Only a line that starts with ``*`` (a keyword, not a ``**``
    comment) initiates a merge, and only a following line that *looks like parameters*
    is consumed: it must contain ``=`` (``KEY=VALUE``) or be one of the bare parameter
    flags below.  This is what distinguishes a continuation from a genuine data record
    — so a stray trailing comma on a ``*NODE,`` / ``*ELEMENT, TYPE=C3D8,`` header does
    NOT swallow the first data line (which would silently drop a node/element).
    Comment / blank lines between the keyword and its continuation are skipped (Abaqus
    allows them)."""
    bare_flags = {"GENERATE", "GEN", "SHIFT", "UNSORTED", "REFLECT", "INTERNAL", "ROUGH",
                  "NLGEOM", "PERTURBATION", "PERT", "EXPLICIT", "DIRECT", "RIKS",
                  "STEADY STATE", "SMALL SLIDING", "TIED", "COMPOSITE", "SYMMETRIC",
                  "NEO HOOKE", "MOONEY-RIVLIN", "POLYNOMIAL", "REDUCED POLYNOMIAL", "OGDEN",
                  "YEOH", "ARRUDA-BOYCE"}

    def is_params(text: str) -> bool:
        if "=" in text:
            return True
        toks = [t.strip().upper() for t in text.split(",") if t.strip()]
        return bool(toks) and all(t in bare_flags for t in toks)

    out: List[str] = []
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        s = line.strip()
        if s.startswith("*") and not s.startswith("**"):
            acc = line.rstrip()
            while acc.endswith(","):
                j = i + 1                            # skip blank / comment lines
                while j < n and (not lines[j].strip() or lines[j].strip().startswith("**")):
                    j += 1
                if j >= n:
                    break
                nxt = lines[j].strip()
                if nxt.startswith("*") or not is_params(nxt):   # next keyword or a data line
                    break
                acc = acc + " " + nxt
                i = j
            out.append(acc)
        else:
            out.append(line)
        i += 1
    return out


def read_blocks(path: str, report: Report, _seen: Optional[set] = None,
                _params: Optional[Dict[str, object]] = None) -> List[Block]:
    """Read a file into Blocks, following ``*INCLUDE`` recursively."""
    if _seen is None:
        _seen = set()
    if _params is None:
        _params = {}
    realpath = os.path.realpath(path)
    if realpath in _seen:
        report.warn(f"*INCLUDE cycle detected for {path}; skipped.")
        return []
    _seen.add(realpath)

    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            raw_lines = fh.read().splitlines()
    except OSError as exc:
        report.warn(f"Could not read {path}: {exc}")
        return []

    raw_lines = apply_parameters(raw_lines, report, _params)
    raw_lines = join_keyword_continuations(raw_lines)
    blocks: List[Block] = []
    current: Optional[Block] = None
    for raw in raw_lines:
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("**"):          # comment line
            continue
        if stripped.startswith("*"):           # keyword line
            keyword, params = parse_keyword_line(line)
            if keyword == "INCLUDE":
                inc = params.get("INPUT") or params.get("INP")
                if inc:
                    inc = inc.strip().strip('"')
                    inc_path = inc if os.path.isabs(inc) else os.path.join(os.path.dirname(path), inc)
                    blocks.extend(read_blocks(inc_path, report, _seen, _params))
                else:
                    report.warn("*INCLUDE without INPUT= ignored.")
                current = None
                continue
            current = Block(keyword=keyword, params=params)
            blocks.append(current)
            src = params.get("INPUT")
            if src:
                # Abaqus INPUT= on a data card (*NODE, *ELEMENT, *AMPLITUDE, ...) reads the
                # card's data lines from that file; ccx has no such parameter, so inline it
                # here — dropped, the card would silently be empty.
                src = src.strip().strip('"')
                src_path = src if os.path.isabs(src) else os.path.join(os.path.dirname(path), src)
                try:
                    with open(src_path, "r", encoding="utf-8", errors="replace") as fh:
                        ext = apply_parameters(fh.read().splitlines(), report, _params)
                except OSError:
                    report.warn(f"*{keyword}, INPUT={src}: data file not found next to the deck; "
                                f"the card has no data lines (copy the file alongside and "
                                f"reconvert).", once=True)
                else:
                    current.data.extend(x.strip() for x in ext
                                        if x.strip() and not x.strip().startswith("*"))
                    report.note(f"*{keyword}, INPUT={src}: data lines inlined from the file "
                                f"(ccx has no INPUT= on data cards).", once=True)
                del params["INPUT"]
        else:                                   # data line
            if current is None:
                report.warn(f"Data line before any keyword ignored: {stripped!r}")
                continue
            current.data.append(stripped)
    return blocks


def numeric_fields(line: str) -> List[str]:
    """Split a purely-numeric data line on commas *and/or* whitespace.  Some exporters
    emit space-separated values where Abaqus expects commas (e.g. an ``*INSTANCE``
    offset written ``0 0 0`` rather than ``0., 0., 0.``).  Only use this where every
    field is expected to be a number — never where a field can be a name."""
    return [t for t in re.split(r"[,\s]+", line.strip()) if t]


def merged_data_records(block: Block) -> List[List[str]]:
    """One record per physical data line (fields stripped, trailing empties trimmed).

    Abaqus uses a trailing comma to pad an *omitted last field* on per-record cards
    (e.g. ``node, dof,`` on ``*BOUNDARY``), NOT as a general line continuation — so we
    must NOT merge trailing-comma lines, or many short records collapse into one giant
    line.  Element connectivity that legitimately spans lines is handled separately by
    node count (``_register_elements``), and material/constraint data lines are passed
    through verbatim, so nothing here needs continuation merging.  Interior blank fields
    are preserved (they are positional placeholders)."""
    records: List[List[str]] = []
    for line in block.data:
        fields = [p.strip() for p in line.split(",")]
        while fields and fields[-1] == "":
            fields.pop()
        records.append(fields)
    return records


def material_rows(block: Block, nvals: int) -> Optional[List[List[str]]]:
    """The data rows of a material card with ``nvals`` property values per row: the values,
    the temperature, then the DEPENDENCIES= field values, as stripped tokens ("" for a blank
    field), padded or cut to that width.  A row takes as many lines as it needs at 8 entries
    a line, as Abaqus reads them.  None when the lines do not make whole rows or
    DEPENDENCIES is not a number."""
    try:
        ndep = max(0, int(float(block.param("DEPENDENCIES") or "0")))
    except ValueError:
        return None
    width = nvals + 1 + ndep
    per_rec = -(-width // 8)
    lines = [ln for ln in block.data if ln.strip()]
    if len(lines) % per_rec:
        return None
    rows: List[List[str]] = []
    for i in range(0, len(lines), per_rec):
        toks: List[str] = []
        for j, ln in enumerate(lines[i:i + per_rec]):
            f = [x.strip() for x in ln.split(",")]
            if j < per_rec - 1:
                f = (f + [""] * 8)[:8]
            toks.extend(f)
        rows.append((toks + [""] * width)[:width])
    return rows


# ---------------------------------------------------------------------------
# Geometry registries (needed to expand mesh-generation cards / flatten)
# ---------------------------------------------------------------------------


class Geometry:
    """Live registry of nodes / elements / sets while processing a part."""

    def __init__(self) -> None:
        self.nodes: "OrderedDict[int, Tuple[float, float, float]]" = OrderedDict()
        self.elements: "OrderedDict[int, Tuple[str, List[int]]]" = OrderedDict()
        self.nsets: Dict[str, List[int]] = {}
        self.elsets: Dict[str, List[int]] = {}
        self.unsorted: set = set()          # node sets declared UNSORTED (keep listing order)

    # -- nodes / elements ---------------------------------------------------
    def add_node(self, nid: int, xyz: Tuple[float, float, float]) -> None:
        self.nodes[nid] = xyz

    def add_element(self, eid: int, typ: str, conn: List[int]) -> None:
        self.elements[eid] = (typ, conn)

    # -- sets ---------------------------------------------------------------
    def add_to_nset(self, name: str, ids: Sequence[int]) -> None:
        self.nsets.setdefault(name.upper(), []).extend(ids)

    def add_to_elset(self, name: str, ids: Sequence[int]) -> None:
        self.elsets.setdefault(name.upper(), []).extend(ids)

    def nset(self, name: str) -> List[int]:
        return self.nsets.get(name.upper(), [])

    def elset(self, name: str) -> List[int]:
        return self.elsets.get(name.upper(), [])


def expand_generate(fields: List[str]) -> List[int]:
    """``start, end[, inc]`` -> explicit list of ids.  A malformed (non-integer) field
    yields an empty list rather than aborting the whole conversion — matching the
    "one bad line should not kill the file" handling of *NODE/*ELEMENT."""
    try:
        nums = [int(float(f)) for f in fields if f != ""]
    except ValueError:
        return []
    if len(nums) == 2:
        start, end, inc = nums[0], nums[1], 1
    elif len(nums) >= 3:
        start, end, inc = nums[0], nums[1], nums[2]
    else:
        return nums
    if inc == 0:
        inc = 1
    return list(range(start, end + (1 if inc > 0 else -1), inc))


# ---------------------------------------------------------------------------
# Number formatting for output
# ---------------------------------------------------------------------------


def pf(token: str) -> float:
    """Parse a float, tolerating Fortran 'D' exponents (e.g. '1.5D2', '0.0d0') which are
    legal in Abaqus/CalculiX numeric fields but reject ``float()``."""
    try:
        return float(token)
    except ValueError:
        return float(token.replace("D", "e").replace("d", "e").replace("E", "e"))


def pint(token) -> int:
    """Parse an integer that may be written in float form (``2.0``, ``1.0E2``) or with a
    Fortran 'D' exponent — both common in exporter output, where bare ``int('2.0')``
    would raise.  Used for the count/increment/id fields of the mesh-generation cards."""
    return int(pf(token))


def fmt_num(value) -> str:
    """Format a float compactly but losslessly enough for FE input."""
    if isinstance(value, str):
        return value
    if isinstance(value, int):
        return str(value)
    if not math.isfinite(value):              # inf / nan would crash int(value) below
        return repr(value)
    if value == int(value) and abs(value) < 1e15:
        return f"{int(value)}."
    return repr(value)


def emit_keyword(keyword: str, params: "OrderedDict[str, Optional[str]]") -> str:
    out = "*" + keyword
    for key, val in params.items():
        out += f", {key}={val}" if val is not None else f", {key}"
    return out


def reflow(values: Sequence, per_line: int = MAX_ENTRIES_PER_LINE) -> List[str]:
    """Group already-formatted tokens into comma-separated lines."""
    toks = [v if isinstance(v, str) else fmt_num(v) for v in values]
    lines = []
    for i in range(0, len(toks), per_line):
        lines.append(", ".join(toks[i:i + per_line]))
    return lines or [""]


def compress_ids(ids: Sequence[int]) -> List[str]:
    """Emit ids as a single ``GENERATE`` triple when they form an arithmetic run,
    otherwise as explicit comma-separated lines (<=16 per line).  Returns the data
    lines; the first element is the literal ``"GENERATE"`` sentinel when applicable."""
    ids = list(ids)
    if len(ids) >= 3:
        inc = ids[1] - ids[0]
        if inc != 0 and all(b - a == inc for a, b in zip(ids, ids[1:])):
            # CalculiX's GENERATE wants first <= last with a positive increment; a set's
            # membership is order-independent, so emit a *descending* run as its
            # equivalent ascending range rather than the invalid "5, 1, -1".
            if inc > 0:
                return ["GENERATE", f"{ids[0]}, {ids[-1]}, {inc}"]
            return ["GENERATE", f"{ids[-1]}, {ids[0]}, {-inc}"]
    return reflow([str(i) for i in ids])


# ---------------------------------------------------------------------------
# Vector helpers (mesh-generation geometry)
# ---------------------------------------------------------------------------

Vec = Tuple[float, float, float]


def vadd(a: Vec, b: Vec) -> Vec:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def vsub(a: Vec, b: Vec) -> Vec:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def vscale(a: Vec, s: float) -> Vec:
    return (a[0] * s, a[1] * s, a[2] * s)


def vdot(a: Vec, b: Vec) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def vcross(a: Vec, b: Vec) -> Vec:
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def vnorm(a: Vec) -> float:
    return math.sqrt(vdot(a, a))


def vunit(a: Vec) -> Vec:
    n = vnorm(a)
    return vscale(a, 1.0 / n) if n else a


def rotate_about_axis(p: Vec, a: Vec, b: Vec, angle_deg: float) -> Vec:
    """Rotate point ``p`` about the axis through ``a``->``b`` by ``angle_deg`` (Rodrigues)."""
    u = vunit(vsub(b, a))
    th = math.radians(angle_deg)
    c, s = math.cos(th), math.sin(th)
    d = vsub(p, a)
    term = vadd(vadd(vscale(d, c), vscale(vcross(u, d), s)),
                vscale(u, vdot(u, d) * (1.0 - c)))
    return vadd(a, term)


def reflect_point(p: Vec, kind: str, data: Sequence[Vec]) -> Optional[Vec]:
    """Reflect a point in a POINT, LINE or MIRROR (plane through three points) — the
    Abaqus *NCOPY, REFLECT= options.  ``PLANE`` with two points (normal = q - o) is kept
    for decks from other writers.  Returns None when too few points are given."""
    if kind == "POINT" and len(data) >= 1:
        return vsub(vscale(data[0], 2.0), p)
    if kind == "LINE" and len(data) >= 2:
        o, q = data[0], data[1]
        u = vunit(vsub(q, o))
        d = vsub(p, o)
        proj = vadd(o, vscale(u, vdot(d, u)))
        return vsub(vscale(proj, 2.0), p)
    if kind in ("MIRROR", "PLANE") and len(data) >= 2:
        o = data[0]
        if len(data) >= 3:
            n = vcross(vsub(data[1], o), vsub(data[2], o))
            if vnorm(n) == 0.0:
                return None
            n = vunit(n)
        else:
            n = vunit(vsub(data[1], o))
        dist = vdot(vsub(p, o), n)
        return vsub(p, vscale(n, 2.0 * dist))
    return None


# ---------------------------------------------------------------------------
# Mesh-generation expansion
# ---------------------------------------------------------------------------


def _ngen_curve(kind: str, p1: Vec, p2: Vec, extra: Optional[Vec], normal: Optional[Vec]):
    """Point generator for one *NGEN line: straight, circular arc about the centre node
    (LINE=C) or parabola through the midside node at t=0.5 (LINE=P).  Returns a function
    t -> point, or None when the curve is undefined (missing/degenerate extra node)."""
    if kind == "C":
        if extra is None:
            return None
        v1, v2 = vsub(p1, extra), vsub(p2, extra)
        r1, r2 = vnorm(v1), vnorm(v2)
        n = vunit(normal) if normal and vnorm(normal) > 0.0 else vunit(vcross(v1, v2))
        if r1 == 0.0 or vnorm(n) == 0.0:
            return None                     # 180-degree arc needs the normal on the card
        u1 = vscale(v1, 1.0 / r1)
        w = vcross(n, u1)
        theta = math.atan2(vdot(v2, w), vdot(v2, u1))
        if theta <= 0.0:
            theta += 2.0 * math.pi
        return lambda t: vadd(extra, vscale(vadd(vscale(u1, math.cos(t * theta)),
                                                 vscale(w, math.sin(t * theta))),
                                            r1 + t * (r2 - r1)))
    if kind == "P":
        if extra is None:
            return None
        return lambda t: vadd(vadd(vscale(p1, (1 - t) * (1 - 2 * t)), vscale(extra, 4 * t * (1 - t))),
                              vscale(p2, t * (2 * t - 1)))
    return lambda t: vadd(vscale(p1, 1 - t), vscale(p2, t))


def expand_ngen(block: Block, geom: Geometry, report: Report) -> List[int]:
    """``*NGEN`` -> nodes between two existing end nodes, on a straight line (default),
    a circular arc about a centre node (LINE=C) or a parabola through a midside node
    (LINE=P); the extra node is the 4th data field, an arc normal fields 5-7.  Nodes are
    spaced evenly in arc angle / curve parameter."""
    kind = (block.param("LINE") or "S").strip().upper()[:1]
    created: List[int] = []
    for rec in merged_data_records(block):
        f = [x for x in rec if x != ""]
        if len(f) < 2:
            continue
        n1, n2 = pint(f[0]), pint(f[1])
        inc = pint(f[2]) if len(f) > 2 and f[2] else 1
        if n1 not in geom.nodes or n2 not in geom.nodes:
            report.warn(f"*NGEN endpoints {n1},{n2} not both defined; skipped.")
            continue
        p1, p2 = geom.nodes[n1], geom.nodes[n2]
        extra = None
        if kind in ("C", "P"):
            nx = pint(f[3]) if len(f) > 3 else 0
            extra = geom.nodes.get(nx)
        normal = None
        if len(f) >= 7:
            try:
                normal = (pf(f[4]), pf(f[5]), pf(f[6]))
            except ValueError:
                normal = None
        curve = _ngen_curve(kind, p1, p2, extra, normal)
        if curve is None:
            report.warn(f"*NGEN LINE={kind}: the {'centre' if kind == 'C' else 'midside'} node "
                        f"is missing or the arc is degenerate (a 180-degree arc needs the normal "
                        f"on the data line); nodes {n1}..{n2} not generated.", once=True)
            continue
        ids = list(range(n1, n2 + (1 if inc > 0 else -1), inc))
        if not ids:
            report.warn(f"*NGEN endpoints {n1},{n2} with increment {inc} generated no nodes "
                        f"(check the ordering/sign of the range); skipped.", once=True)
            continue
        steps = len(ids) - 1
        for k, nid in enumerate(ids):
            if nid in (n1, n2):
                created.append(nid)         # end nodes keep their own coordinates
                continue
            geom.add_node(nid, curve(k / steps if steps else 0.0))
            created.append(nid)
    if kind in ("C", "P"):
        report.note(f"*NGEN LINE={kind}: nodes spaced evenly in {'arc angle' if kind == 'C' else 'the parabola parameter'}.",
                    once=True)
    return created


def expand_nfill(block: Block, geom: Geometry, report: Report) -> List[int]:
    """``*NFILL`` -> linear fill of nodes between two node sets.  ``BIAS=b`` grades the
    spacing geometrically (adjacent intervals in ratio 1/b, so b < 1 concentrates nodes
    toward the first set, as in Abaqus)."""
    created: List[int] = []
    bias = 1.0
    if block.param("BIAS"):
        try:
            bias = pf(block.param("BIAS") or "1")
        except ValueError:
            bias = 1.0
        if bias <= 0.0:
            report.warn("*NFILL BIAS must be positive; uniform spacing used.", once=True)
            bias = 1.0
    for opt in ("SINGULAR", "TWO STEP"):
        if block.has(opt):
            report.warn(f"*NFILL, {opt} is not supported by the converter; the fill is generated "
                        f"as a plain (biased) linear fill — verify the generated nodes.", once=True)

    def frac(j: int, nint: int) -> float:
        if abs(bias - 1.0) < 1e-12:
            return j / nint
        r = 1.0 / bias
        return (1.0 - r ** j) / (1.0 - r ** nint)

    for rec in merged_data_records(block):
        f = [x for x in rec if x != ""]
        if len(f) < 4:
            report.warn("*NFILL record needs set1,set2,nintervals,ninc; skipped.")
            continue
        s1, s2 = geom.nset(f[0]), geom.nset(f[1])
        nint, ninc = pint(f[2]), pint(f[3])
        if not s1 or not s2:
            report.warn("*NFILL node set is empty; skipped.")
            continue
        if len(s1) != len(s2):
            # A real deck may carry one spurious extra edge node, so pair the common
            # (zip) nodes.  But if the sets differ by more than 2x they are not a
            # corresponding edge pair at all — skip rather than fabricate a bad mesh.
            if min(len(s1), len(s2)) < 0.5 * max(len(s1), len(s2)):
                report.warn("*NFILL bounding node sets differ in length by more than 2x; "
                            "skipped (cannot pair them reliably).", once=True)
                continue
            report.warn("*NFILL bounding node sets differ slightly in length; filling the "
                        "corresponding (leading) node pairs only (a spurious extra edge "
                        "node is ignored).", once=True)
        for a, b in zip(s1, s2):
            pa, pb = geom.nodes.get(a), geom.nodes.get(b)
            if pa is None or pb is None:
                continue
            for j in range(1, nint):
                nid = a + j * ninc
                t = frac(j, nint)
                geom.add_node(nid, vadd(vscale(pa, 1 - t), vscale(pb, t)))
                created.append(nid)
    return created


def expand_ncopy(block: Block, geom: Geometry, report: Report) -> List[int]:
    """``*NCOPY`` -> copy a node set with SHIFT (translate/rotate) or REFLECT."""
    old = block.param("OLD SET") or block.param("OLDSET")
    new = block.param("NEW SET") or block.param("NEWSET")
    change = pint(block.param("CHANGE NUMBER") or block.param("CHANGENUMBER") or 0)
    multiple = pint(block.param("MULTIPLE") or 1)
    if not old:
        report.warn("*NCOPY without OLD SET ignored.")
        return []
    src = list(geom.nset(old))
    if not src:
        report.warn(f"*NCOPY OLD SET={old} is empty or undefined; nothing copied.")
        return []

    recs = [r for r in merged_data_records(block) if any(x != "" for x in r)]
    created: List[int] = []

    def transform_shift(p: Vec, mult: int) -> Vec:
        shift = (0.0, 0.0, 0.0)
        if recs:
            v = [pf(x) for x in recs[0] if x != ""]
            if len(v) >= 3:
                shift = (v[0], v[1], v[2])
        out = p
        for _ in range(mult):
            out = vadd(out, shift)
            if len(recs) > 1:                       # optional rotation line
                v = [pf(x) for x in recs[1] if x != ""]
                if len(v) >= 7:
                    a, b, ang = (v[0], v[1], v[2]), (v[3], v[4], v[5]), v[6]
                    out = rotate_about_axis(out, a, b, ang)
        return out

    reflect = None
    for key in ("REFLECT",):
        if block.has(key):
            reflect = (block.param(key) or "").upper()
    if block.has("POLE"):
        report.warn("*NCOPY, POLE is not supported by the converter; nodes are copied with the "
                    "SHIFT/REFLECT data only — verify the generated nodes.", once=True)
    # REFLECT data: the points' coordinates may sit on one line (LINE: x1..z2) or
    # several (MIRROR: a, b on the first, c on the second) — take them as a flat list.
    pts: List[Vec] = []
    if reflect:
        try:
            vals = [pf(x) for r in recs for x in r if x != ""]
        except ValueError:
            vals = []
        pts = [(vals[i], vals[i + 1], vals[i + 2]) for i in range(0, len(vals) - 2, 3)]

    for m in range(1, multiple + 1):
        for nid in src:
            p = geom.nodes.get(nid)
            if p is None:
                continue
            new_id = nid + change * m
            if reflect:
                np_ = reflect_point(p, reflect, pts)
                if np_ is None:
                    report.warn(f"*NCOPY REFLECT={reflect} could not be applied (too few or "
                                f"degenerate points); skipped.", once=True)
                    continue
                newp = np_
            else:
                newp = transform_shift(p, m)
            geom.add_node(new_id, newp)
            created.append(new_id)
            if new:
                geom.add_to_nset(new, [new_id])
    return created


def expand_elgen(block: Block, geom: Geometry, report: Report) -> List[int]:
    """``*ELGEN`` -> generate elements from a master element via up to 3 triples."""
    elset = block.param("ELSET")
    created: List[int] = []
    for rec in merged_data_records(block):
        f = [x for x in rec if x != ""]
        if not f:
            continue
        master = pint(f[0])
        if master not in geom.elements:
            report.warn(f"*ELGEN master element {master} not defined; skipped.")
            continue
        typ, conn = geom.elements[master]
        triples = []
        rest = f[1:]
        for i in range(0, len(rest), 3):
            grp = rest[i:i + 3]
            n = pint(grp[0])
            ninc = pint(grp[1]) if len(grp) > 1 and grp[1] else 1
            einc = pint(grp[2]) if len(grp) > 2 and grp[2] else 1
            triples.append((n, ninc, einc))
        # nested loops over up to three generation directions
        ranges = [range(t[0]) for t in triples]
        while len(ranges) < 3:
            ranges.append(range(1))
            triples.append((1, 0, 0))
        for k in ranges[2]:
            for j in ranges[1]:
                for i in ranges[0]:
                    eid = master + i * triples[0][2] + j * triples[1][2] + k * triples[2][2]
                    noff = i * triples[0][1] + j * triples[1][1] + k * triples[2][1]
                    if eid == master and noff == 0:
                        new_conn = list(conn)
                    else:
                        new_conn = [c + noff for c in conn]
                    geom.add_element(eid, typ, new_conn)
                    created.append(eid)
    if elset:
        geom.add_to_elset(elset, created)
    return created


def expand_elcopy(block: Block, geom: Geometry, report: Report) -> List[int]:
    """``*ELCOPY`` -> copy an element set with element- and node-number shifts."""
    eshift = pint(block.param("ELEMENT SHIFT") or 0)
    nshift = pint(block.param("SHIFT NODES") or 0)
    old = block.param("OLD SET") or block.param("OLDSET")
    new = block.param("NEW SET") or block.param("NEWSET")
    if not old:
        report.warn("*ELCOPY without OLD SET ignored.")
        return []
    created: List[int] = []
    for eid in list(geom.elset(old)):
        if eid not in geom.elements:
            continue
        typ, conn = geom.elements[eid]
        new_id = eid + eshift
        geom.add_element(new_id, typ, [c + nshift for c in conn])
        created.append(new_id)
        if new:
            geom.add_to_elset(new, [new_id])
    return created


def dedup(seq: Sequence[int]) -> List[int]:
    seen, out = set(), []
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def fmt_coord(x: float) -> str:
    # 12 significant digits cleans float-accumulation artefacts (e.g. 0.45 from
    # repeated *NCOPY shifts) while keeping ample precision for FE geometry.  Values
    # below 1e-12 (e.g. IEEE rotation residue ~1e-16) are snapped to a clean 0.
    x = float(x)
    if abs(x) < 1e-12:
        x = 0.0
    return "%.12g" % x


# ---------------------------------------------------------------------------
# Keyword classification & variable maps
# ---------------------------------------------------------------------------

# Geometry keywords are consumed into the registry and emitted once, canonically.
GEOM_KW = {"NODE", "ELEMENT", "NSET", "ELSET", "NGEN", "NFILL", "NCOPY", "NMAP", "ELGEN", "ELCOPY"}

# Procedure keywords that may appear inside a *STEP.
PROC_KW = {"STATIC", "FREQUENCY", "BUCKLE", "DYNAMIC", "MODAL DYNAMIC", "HEAT TRANSFER",
           "VISCO", "STEADY STATE DYNAMICS", "COUPLED TEMPERATURE-DISPLACEMENT",
           "COMPLEX FREQUENCY", "ELECTROMAGNETICS", "CFD", "GREEN", "SUBSTRUCTURE GENERATE",
           "UNCOUPLED TEMPERATURE-DISPLACEMENT", "CRACK PROPAGATION", "HCF", "SENSITIVITY",
           "FEASIBLE DIRECTION", "NO ANALYSIS"}

# Procedures in which temperature is a degree of freedom (11): Abaqus does not allow a
# predefined temperature field (*TEMPERATURE) in their steps — *BOUNDARY prescribes DOF 11
# there — and ccx stops on the card ("this is a *HEAT TRANSFER or (UN)COUPLED TEMPERATURE-
# DISPLACEMENT analysis").
TEMPERATURE_DOF_PROCS = {"HEAT TRANSFER", "COUPLED TEMPERATURE-DISPLACEMENT",
                         "UNCOUPLED TEMPERATURE-DISPLACEMENT", "COUPLED THERMAL-ELECTRICAL",
                         "DYNAMIC TEMPERATURE-DISPLACEMENT"}

# Step (history) data: valid only between *STEP and *END STEP.  Outside a step Abaqus
# rejects these, ccx stops with "*CLOAD should only be used within a STEP" — and ccx 2.23
# segfaults outright when the deck has no *STEP at all (verified: *CLOAD, *DLOAD,
# *FREQUENCY, *NODE FILE).  (*BOUNDARY, *CONTROLS and *RESTART are legal model data.)
HISTORY_ONLY_KW = PROC_KW | {
    "CLOAD", "DLOAD", "DSLOAD", "TEMPERATURE", "CFLUX", "DFLUX", "DSFLUX", "FILM", "SFILM",
    "RADIATE", "SRADIATE", "NODE FILE", "EL FILE", "NODE PRINT", "EL PRINT", "NODE OUTPUT",
    "ELEMENT OUTPUT", "CONTACT FILE", "CONTACT OUTPUT", "CONTACT PRINT", "SECTION PRINT",
    "MODAL DAMPING", "CHANGE MATERIAL", "CHANGE PLASTIC", "CHANGE SOLID SECTION",
    "CHANGE SURFACE BEHAVIOR", "CHANGE CONTACT TYPE", "CHANGE FRICTION", "OUTPUT"}

# Emitted ccx types of plane-stress / plane-strain / axisymmetric continuum elements.
# Their nodes have NO rotational DOFs; ccx turns a *BOUNDARY on DOF 4-6 there into
# rotational constraints and ccx 2.23 then crashes (bus error) or stops in usermpc.
PLANE_ELEM_PREFIXES = ("CPS", "CPE", "CAX")

# Sets synthesized for *EL PRINT / *NODE PRINT cards that name no set (Abaqus default:
# the whole model; ccx: no output at all).
ALL_ELEMENTS_SET = "ABQ2CCX_ALL_ELEMENTS"
ALL_NODES_SET = "ABQ2CCX_ALL_NODES"
# Element set (and material) of the force-free "knot beams" that make the shell/beam nodes
# of a rigid coupling ccx knots — see Converter._plan_rigid_couplings.
KNOT_SET = "ABQ2CCX_KNOT"
# Why moving *RIGID BODY member BCs to the reference node (as Abaqus does) would hold the
# body more than the BCs themselves — see Converter._plan_rigid_body_move.
RB_MOVE_INEXACT = {
    "geometry": "the BC'd nodes leave the body a rotation that the moved zero rotations fix — "
                "they lie on one line seen along the DOF, for example, or are a single node",
    "history": "the body may have turned before the step, its rotations not being held from the "
               "start, and the BC values would then ramp from the turned position",
    "overlap": "the reference node's own zero velocity meets a zero displacement on the nodes, or "
               "the reverse: the same only if the DOF has not moved before the step",
}

# Abaqus face -> 1-based local node positions (corners, then midsides) of the continuum
# families; a lower-order element simply has fewer nodes.  Shells use every node for a face
# and the corner/midside pair for an edge (see Converter._face_nodes).
FACE_NODES = {
    "HEX": {1: (1, 2, 3, 4, 9, 10, 11, 12), 2: (5, 8, 7, 6, 16, 15, 14, 13),
            3: (1, 5, 6, 2, 17, 13, 18, 9), 4: (2, 6, 7, 3, 18, 14, 19, 10),
            5: (3, 7, 8, 4, 19, 15, 20, 11), 6: (4, 8, 5, 1, 20, 16, 17, 12)},
    "TET": {1: (1, 2, 3, 5, 6, 7), 2: (1, 4, 2, 8, 9, 5), 3: (2, 4, 3, 9, 10, 6),
            4: (3, 4, 1, 10, 8, 7)},
    "WEDGE": {1: (1, 2, 3, 7, 8, 9), 2: (4, 6, 5, 12, 11, 10), 3: (1, 4, 5, 2, 13, 10, 14, 7),
              4: (2, 5, 6, 3, 14, 11, 15, 8), 5: (3, 6, 4, 1, 15, 12, 13, 9)},
}

# Abaqus planar (2-D) beams and trusses.  ccx has no planar beam: B21 "is internally replaced
# by a B31 element and is treated as such", T2D2 likewise by a T3D2 (manual 6.2.31, 6.2.34),
# and ELEMENT_TYPE_MAP sends the others to 3-D beams/trusses, so their out-of-plane DOFs are
# free.  In a planar model the converter fixes DOF 3 on their nodes (node set PLANAR_NODES_SET,
# see Converter._plan_planar_constraint).
PLANAR_LINE_TYPES = {"B21", "B22", "B23", "PIPE21", "PIPE22", "T2D2", "T2D3"}
PLANAR_TRUSS_TYPES = {"T2D2", "T2D3"}
# Element families that can share a planar model with them: plane continuum, 2-D rigid,
# connector, cohesive/gasket and heat-transfer elements, and dimensionless springs/masses.
PLANAR_COMPANION_PREFIXES = ("CPS", "CPE", "DC2D", "AC2D", "COH2D", "GK2D", "GKPS", "R2D", "RB2D",
                             "CONN2D", "SPRING", "DASHPOT", "MASS", "ROTARYI", "GAPUNI")
PLANAR_NODES_SET = "ABQ2CCX_PLANAR"


def planar_line_type(typ: str) -> Optional[str]:
    """The planar beam/truss type an Abaqus element type belongs to (B21H -> B21, T2D2T ->
    T2D2), or None for any other element."""
    base = typ.upper()
    while base not in PLANAR_LINE_TYPES and len(base) > 1 and base[-1] in "HT":
        base = base[:-1]
    return base if base in PLANAR_LINE_TYPES else None


# The COMPLETE set of CalculiX (ccx 2.22 + 2.23) input keywords, verified against the ccx
# user manual (dhondt.de 2.22 PDF, 2.23 release notes) and the calculix/new_keywords +
# calculix/cae keyword lists.  Any Abaqus keyword found here is emitted as-is (CalculiX
# accepts it); anything NOT here and without a dedicated handler has no direct equivalent
# and is commented out with a warning (see translate_one) rather than silently kept.
# *DAMAGE INITIATION was introduced in ccx 2.23 (calculix/new_keywords#4).
CCX_KEYWORDS = {
    # model definition
    "AMPLITUDE", "BASE MOTION", "BEAM SECTION", "CFD", "CHANGE FRICTION", "CLEARANCE",
    "CONDUCTIVITY", "CONSTRAINT", "CONTACT DAMPING", "CONTACT PAIR", "CORRELATION LENGTH",
    "COUPLING", "CREEP", "CYCLIC HARDENING", "CYCLIC SYMMETRY MODEL", "DAMAGE INITIATION",
    "DAMPING", "DASHPOT",
    "DEFORMATION PLASTICITY", "DENSITY", "DEPVAR", "DESIGN RESPONSE", "DESIGN VARIABLES",
    "DISTRIBUTING", "DISTRIBUTING COUPLING", "DISTRIBUTION", "ELASTIC",
    "ELECTRICAL CONDUCTIVITY", "ELECTROMAGNETICS", "ELEMENT", "ELSET", "EQUATION",
    "EXPANSION", "FILTER", "FLUID CONSTANTS", "FLUID SECTION", "FRICTION", "GAP",
    "GAP CONDUCTANCE", "GAP HEAT GENERATION", "GEOMETRIC CONSTRAINT", "GEOMETRIC TOLERANCES",
    "HEADING", "HYPERELASTIC", "HYPERFOAM", "INCLUDE", "INITIAL CONDITIONS",
    "INITIAL STRAIN INCREASE", "KINEMATIC", "MAGNETIC PERMEABILITY", "MASS", "MATERIAL",
    "MATRIX ASSEMBLE", "MEMBRANE SECTION", "MODEL CHANGE", "MOHR COULOMB",
    "MOHR COULOMB HARDENING", "MPC", "NETWORK MPC", "NODAL THICKNESS", "NODE", "NORMAL",
    "NSET", "ORIENTATION", "PHYSICAL CONSTANTS", "PLASTIC", "PRE-TENSION SECTION",
    "RATE DEPENDENT", "RETAINED NODAL DOFS", "RIGID BODY", "ROBUST DESIGN", "SHELL SECTION",
    "SOLID SECTION", "SPECIFIC GAS CONSTANT", "SPECIFIC HEAT", "SPRING", "SUBMODEL",
    "SURFACE", "SURFACE BEHAVIOR", "SURFACE INTERACTION", "TIE", "TIME POINTS", "TRANSFORM",
    "USER ELEMENT", "USER MATERIAL", "USER SECTION", "VALUES AT INFINITY", "VIEWFACTOR",
    # step / procedure / loads / output
    "STEP", "END STEP", "STATIC", "DYNAMIC", "FREQUENCY", "BUCKLE", "MODAL DYNAMIC",
    "STEADY STATE DYNAMICS", "COMPLEX FREQUENCY", "HEAT TRANSFER",
    "COUPLED TEMPERATURE-DISPLACEMENT", "UNCOUPLED TEMPERATURE-DISPLACEMENT", "VISCO",
    "GREEN", "SUBSTRUCTURE GENERATE", "SUBSTRUCTURE MATRIX OUTPUT", "CRACK PROPAGATION",
    "HCF", "FEASIBLE DIRECTION", "SENSITIVITY", "NO ANALYSIS", "CONTROLS", "RESTART",
    "REFINE MESH", "INITIAL MESH", "OBJECTIVE", "SELECT CYCLIC SYMMETRY MODES", "BOUNDARY",
    "CLOAD", "DLOAD", "DSLOAD", "CFLUX", "DFLUX", "FILM", "RADIATE", "TEMPERATURE",
    "MASS FLOW", "CHANGE CONTACT TYPE", "CHANGE MATERIAL", "CHANGE PLASTIC",
    "CHANGE SOLID SECTION", "CHANGE SURFACE BEHAVIOR", "MODAL DAMPING", "NODE FILE",
    "NODE OUTPUT", "NODE PRINT", "EL FILE", "ELEMENT OUTPUT", "EL PRINT", "CONTACT FILE",
    "CONTACT OUTPUT", "CONTACT PRINT", "SECTION PRINT", "FACE PRINT", "OUTPUT",
}

# Abaqus organisational / preprocessing keywords with no CalculiX meaning -> dropped.
DROP_KEYWORDS = {
    "PART", "END PART", "INSTANCE", "END INSTANCE", "ASSEMBLY", "END ASSEMBLY",
    "PREPRINT", "MANIFEST", "END LOAD CASE",
}
# Dropped, but loudly (they can change the model -> the user must check).
DROP_WARN_KEYWORDS = {
    "SYSTEM": "*SYSTEM (local coordinate system for following *NODE cards) is unsupported "
              "by ccx and was dropped; node coordinates defined under it may be in a rotated "
              "frame — verify they are global.",
    "UNIT SYSTEM": "*UNIT SYSTEM is unsupported by ccx and was dropped (informational only).",
}
# Keywords that exist in BOTH but mean something different in ccx -> warn, then emit.
SEMANTIC_TRAP = {
    "FILTER": "*FILTER in CalculiX is a sensitivity-smoothing card for *SENSITIVITY steps, "
              "NOT the Abaqus output filter — emitted as-is but almost certainly wrong; remove "
              "it unless this is an optimisation run.",
}
# Supported by ccx but worth a heads-up about a behavioural/interface difference.
PASS_WITH_NOTE = {
    "DAMAGE INITIATION": "*DAMAGE INITIATION was added in ccx 2.23 and is emitted unchanged; ccx "
                "implements a subset of Abaqus' damage-initiation criteria and has no *DAMAGE "
                "EVOLUTION card, so verify your ccx version (>= 2.23), the CRITERION, and that "
                "progressive damage is not required to soften/fail the material.",
    "USER MATERIAL": "*USER MATERIAL kept, but ccx uses its own umat interface (umat_*.f), not an "
                     "Abaqus UMAT binary — the subroutine must be ported.",
    "USER ELEMENT": "*USER ELEMENT kept; ensure the matching ccx user-element routine is built in.",
}
# Abaqus keywords with NO ccx equivalent: commented out with targeted guidance.
SPECIAL_UNSUPPORTED = {
    "VISCOELASTIC": "time-domain viscoelasticity is unsupported (ccx *VISCO is a creep STEP, not a "
                    "material); drop, or approximate with *DAMPING.",
    "INERTIA RELIEF": "ccx has no inertia relief; constrain with a soft spring-to-ground / 3-2-1 "
                      "set, or balance with the equilibrating load.",
    "CONNECTOR BEHAVIOR": "connector behaviour has no ccx equivalent (a section that uses it is "
                          "commented out); remodel as *SPRING / *DASHPOT / *MPC per the behaviour.",
    "CONNECTOR MOTION": "prescribes motion of connector components, which the converted "
                        "connector (ccx constraints, no connector element) does not have; the "
                        "prescribed motion is missing.",
    "CONNECTOR LOAD": "loads connector components, which the converted connector (ccx "
                      "constraints, no connector element) does not have; the load is missing.",
    "GASKET BEHAVIOR": "gasket behaviour has no ccx equivalent.",
    "COHESIVE SECTION": "ccx has no cohesive element; model debonding with contact (*SURFACE "
                        "BEHAVIOR) or a nonlinear *SPRING.",
    "DAMAGE EVOLUTION": "ccx 2.23 added *DAMAGE INITIATION but not *DAMAGE EVOLUTION, so "
                        "progressive damage cannot fully run (the material will not soften/fail); drop.",
    "FIELD": "*FIELD predefined fields are unsupported; use *INITIAL CONDITIONS / *TEMPERATURE / "
             "*DISTRIBUTION instead.",
    "REBAR": "rebar/reinforcement layers have no ccx equivalent; mesh reinforcements explicitly.",
    "BEAM GENERAL SECTION": "no direct ccx card; use *USER ELEMENT (U1) + *BEAM SECTION, "
                            "SECTION=GENERAL with A, I11, I12, I22, shear factor.",
    "CONCRETE": "concrete plasticity models are unsupported by ccx; substitute *PLASTIC or remodel.",
    "CONCRETE DAMAGED PLASTICITY": "unsupported by ccx; substitute *PLASTIC or remodel.",
    **{f"CONNECTOR {k}": "connector behaviour has no ccx equivalent (a *CONNECTOR SECTION that "
                         "uses it is commented out)."
       for k in ("ELASTICITY", "DAMPING", "STOP", "LOCK", "FRICTION", "PLASTICITY", "HARDENING",
                 "DAMAGE INITIATION", "DAMAGE EVOLUTION", "CONSTITUTIVE REFERENCE",
                 "DERIVED COMPONENT", "POTENTIAL", "UNIAXIAL BEHAVIOR", "FAILURE")},
    "CONTACT": "Abaqus general contact has no ccx equivalent; define explicit pairs instead: "
               "*CONTACT PAIR, INTERACTION=<name>, TYPE=SURFACE TO SURFACE with two element "
               "surfaces (+ *SURFACE INTERACTION / *SURFACE BEHAVIOR).",
    "CONTACT INCLUSIONS": "general-contact inclusion list (ALL EXTERIOR is not translatable); "
                          "create the two surfaces and a *CONTACT PAIR instead.",
    "CONTACT EXCLUSIONS": "general-contact exclusion list; not applicable to ccx *CONTACT PAIR.",
    "CONTACT PROPERTY ASSIGNMENT": "assigns a general-contact property; in ccx name the "
                                   "*SURFACE INTERACTION via *CONTACT PAIR, INTERACTION= instead.",
    "LATENT HEAT": "ccx has no *LATENT HEAT; approximate with an apparent *SPECIFIC HEAT peak "
                   "cp + L/(Tliq-Tsol) over the melting interval.",
    "EMBEDDED ELEMENT": "no ccx equivalent; mesh the reinforcement conformally or tie the "
                        "embedded nodes with *EQUATION constraints.",
    # Newer Abaqus keywords (2024/2025) with no ccx equivalent (calculix/new_keywords#4).
    "ALLOWABLE STRESS": "Abaqus 2024 optimisation stress limit; ccx has no equivalent — express a "
                        "stress constraint via *DESIGN RESPONSE/*CONSTRAINT in a *SENSITIVITY run.",
    "REDUCED BASIS GENERATE": "Abaqus 2024 reduced-order-basis generation has no ccx equivalent; drop.",
    "SUBMODEL CUT": "Abaqus 2024 submodel-cut card; ccx drives submodels with *SUBMODEL plus "
                    "*BOUNDARY/*CLOAD, SUBMODEL — remodel using those.",
    "WEAR SURFACE PROPERTIES": "Abaqus 2024 surface-wear properties have no ccx equivalent; drop.",
    "ELECTRICAL RESISTIVITY": "ccx parameterises conduction by *ELECTRICAL CONDUCTIVITY (the "
                              "inverse); convert resistivity -> conductivity.",
    "ELECTRIC MACHINE LOAD": "Abaqus 2024 electric-machine load has no ccx equivalent; drop.",
    "ELECTRIC MACHINE PROPERTY": "Abaqus 2024 electric-machine property has no ccx equivalent; drop.",
    "ELEMENT USER OUTPUT VARIABLES": "Abaqus UVARM-style user output; ccx has no equivalent (fill "
                                     "state variables via *DEPVAR + a ccx umat instead).",
    "PIEZORESISTIVITY": "Abaqus 2024 piezoresistive coupling has no ccx equivalent; drop.",
    "STEP CYCLING": "Abaqus 2025 step cycling has no ccx equivalent; remodel as repeated steps.",
    "STEP CYCLING CONTROL": "Abaqus 2025 step-cycling controls have no ccx equivalent; drop.",
    "LOAD CASE": "ccx solves one load case per step: the loads of all *LOAD CASE blocks in this "
                 "step are now SUPERPOSED into one solution — split each load case into its own "
                 "step (with OP=NEW on the loads).",
}

# ---- output variable maps (Abaqus identifier -> ccx) --------------------------
# Dropped: no ccx equivalent (derived in post-processing or simply unavailable).
ABQ_DROP_VARS = {"MISES", "PRESS", "TRESC", "A", "NE", "IE", "CF", "NFORC", "COORD", "STH",
                 "STATUS", "CDISP", "CSTRESS", "CFORCE", "CTF", "VENER", "AENER", "AREA",
                 "AT", "SE", "SM", "SF", "ELEN", "NFLUX", "RBFOR", "CELENT", "EVF", "PEEQVAVG",
                 "PEVAVG", "SVAVG", "EVOLAVG", "TEMP", "STATUSXFEM", "PHILSM", "PSILSM", "DMICRT",
                 "SDEG", "DAMAGEC", "DAMAGET", "DAMAGEFT", "DAMAGEFC", "DAMAGEMT", "DAMAGEMC",
                 "DAMAGESHR", "TRIAX", "LODE", "ESEDEN", "EPDDEN", "MMIXDME", "ELEDEN"}
# Renamed / folded onto a ccx identifier.
ABQ_MAP_VARS = {"LE": "E", "PE": "PEEQ", "PEMAG": "PEEQ", "CEEQ": "PEEQ", "EE": "ME",
                "NE11": "E", "NT11": "NT", "UT": "U", "UR": "U", "RT": "RF", "RM": "RF"}
# What a remap above does NOT preserve (shown in the conversion note).
ABQ_MAP_CAVEATS = {"LE": "ccx E is the Lagrangian (Green-Lagrange) strain under NLGEOM, not "
                         "the logarithmic strain",
                   "PE": "the scalar equivalent plastic strain, not the plastic strain tensor",
                   "PEMAG": "the equivalent plastic strain, not the plastic strain magnitude",
                   "CEEQ": "ccx keeps a single equivalent inelastic strain",
                   "EE": "ccx ME is the mechanical strain (total minus thermal), which includes "
                         "plastic strain — not the elastic strain",
                   "UR": "ccx U holds translations only, no rotations",
                   "RM": "ccx RF holds reaction forces only, no moments"}
# ccx identifiers that are valid only on *EL PRINT / *NODE PRINT (.dat), not *EL FILE.
EL_PRINT_ONLY_VARS = {"ELSE", "ELKE", "EVOL", "CELS"}
# Output labels ccx accepts, per card (ccx sources elprints.f / nodeprints.f / noelfiles.f;
# ccx compares the first 4 characters, SDV the first 3).  An unknown label is FATAL on
# *EL PRINT ('label not applicable or unknown') and a skipped token with a warning on the
# other cards — so labels outside these sets are dropped.
CCX_EL_PRINT_LABELS = {"S", "E", "ME", "EVOL", "EMAS", "COOR", "CENT", "ENER", "ELSE", "ELKE",
                       "PEEQ", "SDV", "HFL", "SVF", "SF", "HFLF", "EBHE"}
CCX_NODE_PRINT_LABELS = {"U", "NT", "TS", "RF", "RFL", "PS", "PN", "MF", "V", "A", "VF", "PSF",
                         "TSF", "MACH", "DEPF", "TTF", "PTF", "CP", "TURB", "RECU"}
CCX_FILE_LABELS = {"U", "NT", "RF", "RFL", "TT", "MF", "PT", "TS", "PU", "PNT", "MAXU", "V", "PS",
                   "MACH", "CP", "TURB", "VF", "PSF", "TSF", "PTF", "TTF", "CSTR", "CDIS", "CELS",
                   "DEPT", "HCRI", "PRF", "POT", "SEN", "A", "S", "E", "PEEQ", "SDV", "ENER",
                   "HFL", "HER", "ZZS", "ERR", "NOE", "PHS", "MAXS", "MAXE", "ME", "SF", "HFLF",
                   "SVF", "DEPF", "DTF", "ECD", "EMFE", "EMFB", "PCON", "SNEG", "SMID", "SPOS",
                   "KEQ", "THE"}
# *CONTACT OUTPUT / *CONTACT FILE: ccx writes CDIS (opening/slip), CSTR (pressure/shear)
# and CELS (contact energy); CDIS and CSTR switch on the same CONTACT block, all of COPEN,
# CSLIP1/2, CPRESS and CSHEAR1/2 (probed on 2.23).  Only Abaqus names ccx itself recognises
# by their first four characters (CDISP, CSTRESS) are kept; CPRESS, COPEN, ... are dropped,
# not folded onto them.  Where ccx 2.23 has no contact output to write or aborts on it, see
# CONTACT_OUTPUT_ISSUES.
CCX_CONTACT_FILE_LABELS = {"CDIS", "CSTR", "CELS", "PCON"}
ABQ_CONTACT_MAP = {"CDISP": "CDIS", "CSTRESS": "CSTR"}
# Contact output (*CONTACT FILE CDIS/CSTR) ccx 2.23 cannot write, probed on a block pressed
# onto another (plane strain/stress, axisymmetric and 3-D solid elements of every order and
# shape, a shell and a membrane plate; static, NLGEOM, *VISCO, implicit and explicit
# dynamics, coupled temperature-displacement, and the steps after them; ccx's own implicit-
# dynamics contact decks): ccx writes it only for *CONTACT PAIR contact, an empty block
# without one; in a model with axisymmetric elements it aborts (SIGABRT, after the CONTACT
# block) once S output adds its stress error estimate to the .frd, unless every pair is
# face-to-face — with node-to-surface pairs and without pairs, whatever the procedure,
# OUTPUT=3D or contact state; and it writes node-to-surface contact of plane, axisymmetric
# and membrane elements at the slave nodes of their expanded 3-D form, which the .frd of a
# model without beams or shells (CCX_FRD_3D_TRIGGER) does not hold.  Everywhere else the
# values land on nodes of the .frd (the deck's own, or expanded ones of a 3-D .frd).
CONTACT_OUTPUT_ISSUES = {
    "nopair": "the ccx model has no contact pair (Abaqus general contact is not converted, a "
              "tied pair becomes a *TIE), so ccx has no contact output to write",
    "abort": "ccx 2.23 aborts writing contact output in a model with axisymmetric elements "
             "once the .frd also gets S, unless every contact pair is face-to-face "
             "(TYPE=SURFACE TO SURFACE)",
    "expanded": "ccx writes node-to-surface contact output of plane, axisymmetric and membrane "
                "elements at the slave nodes of their expanded 3-D form, which the .frd of a "
                "model without beams or shells does not hold",
}
# Which nodes a ccx 2.23 .frd holds (probed): a model with a beam (B...) or shell (S3, S4,
# S6, S8...) element is written in its expanded 3-D form — ccx's default OUTPUT=3D then
# (elements.f) — and the .frd has the expanded nodes only, none of the original nodes of a
# 1-D/2-D element (CCX_EXPANDED_PREFIXES); a node of no element (a reference point) is in
# no .frd.  A *NODE FILE set of such nodes writes empty blocks.  OUTPUT=2D (read in the
# first step only, for the whole run) maps the results back onto the original nodes: the
# mean displacement of the expanded nodes and the sum of their forces, so the labels below
# stay exact, while every other field is averaged through the thickness, which removes the
# bending stresses of beams and shells.
CCX_FRD_3D_TRIGGER = ("B", "S3", "S4", "S6", "S8")
CCX_EXPANDED_PREFIXES = ("B", "T2D", "T3D", "S3", "S4", "S6", "S8", "M3D", "CPS", "CPE", "CAX")
CCX_SOLID_PREFIXES = ("C3D", "DC3D", "F3D")
FRD_2D_EXACT_LABELS = {"U", "V", "RF", "PU"}
OUTPUT_CARDS = {"NODE FILE", "EL FILE", "NODE PRINT", "EL PRINT", "NODE OUTPUT", "ELEMENT OUTPUT",
                "CONTACT OUTPUT", "CONTACT FILE"}
# Procedures without time increments: an output frequency means nothing there.
UNTIMED_PROCS = {"FREQUENCY", "BUCKLE", "STEADY STATE DYNAMICS", "COMPLEX FREQUENCY", "GREEN",
                 "SUBSTRUCTURE GENERATE", "SENSITIVITY", "FEASIBLE DIRECTION", "NO ANALYSIS"}
# Abaqus' preselected field output per procedure (*OUTPUT, FIELD, VARIABLE=PRESELECT, and
# what Abaqus writes when a deck requests no output database output at all; Analysis
# User's Guide, "Output to the output database", table 1) as the ccx labels that carry it:
# (*NODE FILE labels, *EL FILE labels).  PEEQ (Abaqus' PE, PEEQ, PEMAG, CEEQ) only where a
# material yields or creeps: ccx warns "PEEQ-output requested" on a model without.  Left
# out (probed on 2.23): A, which *NODE FILE rejects as "label not applicable", and V in
# steady state dynamics ("V only available ..."); CF, EVF and the volume averages have no
# ccx label.  ccx's E is Abaqus' LE only without NLGEOM (Green-Lagrange strain with it).
PRESELECT_FIELD = {
    "STATIC": (("U", "RF"), ("S", "E", "PEEQ")),
    "VISCO": (("U", "RF"), ("S", "E", "PEEQ")),
    "DYNAMIC": (("U", "V", "RF"), ("S", "E", "PEEQ")),
    "MODAL DYNAMIC": (("U", "V", "RF"), ("S", "E")),
    "STEADY STATE DYNAMICS": (("U", "RF"), ("S", "E")),
    "FREQUENCY": (("U",), ()),
    "BUCKLE": (("U",), ()),
    "COMPLEX FREQUENCY": (("U",), ()),
    "HEAT TRANSFER": (("NT", "RFL"), ("HFL",)),
    "COUPLED TEMPERATURE-DISPLACEMENT": (("U", "RF", "NT", "RFL"), ("S", "E", "PEEQ", "HFL")),
}
# What of it has no ccx label (A, CF, the explicit volume averages).
PRESELECT_NO_CCX = {
    "STATIC": "CF", "VISCO": "CF", "DYNAMIC": "A, CF",
    "EXPLICIT": "A, EVF and the volume averages",
    "MODAL DYNAMIC": "A, CF", "STEADY STATE DYNAMICS": "V, A, CF",
    "COUPLED TEMPERATURE-DISPLACEMENT": "CF",
}
# Its contact output, which Abaqus writes where the model has contact: (Abaqus variables,
# ccx *CONTACT FILE labels) — CSTRESS and CDISP in general static, quasi-static, implicit
# dynamic and coupled temperature-displacement steps, CSTRESS alone in explicit dynamics,
# none in linear perturbation steps.  Written where ccx can (CONTACT_OUTPUT_ISSUES).
PRESELECT_CONTACT = {
    "STATIC": ("CSTRESS, CDISP", ("CDIS", "CSTR")), "VISCO": ("CSTRESS, CDISP", ("CDIS", "CSTR")),
    "DYNAMIC": ("CSTRESS, CDISP", ("CDIS", "CSTR")), "EXPLICIT": ("CSTRESS", ("CSTR",)),
    "COUPLED TEMPERATURE-DISPLACEMENT": ("CSTRESS, CDISP", ("CDIS", "CSTR")),
}
# Abaqus' linear perturbation procedures: output requests carry over only between
# consecutive perturbation steps, and those of general steps skip them.
PERTURBATION_PROCS = {"FREQUENCY", "BUCKLE", "COMPLEX FREQUENCY", "MODAL DYNAMIC",
                      "STEADY STATE DYNAMICS", "SUBSTRUCTURE GENERATE", "GREEN"}

# ccx sizes an explicit increment per element (calcstabletimeincvol.f) as critom * h * f /
# (2 c) times a safety factor 0.8 / 1.3: c the material's largest wave speed, h the
# smallest of volume * k / face area over the element's faces (k = 3 for tetrahedra, 2 for
# a wedge's quadrilateral faces, else 1; volume and areas from the one-point Jacobians,
# exact for straight-edged elements) and f the factor of the brick type below.  Beams,
# shells, membranes and plane elements are sized as the bricks ccx expands them into
# (gen3delem.f): through their thickness, a truss's square section, or the 2-degree
# sector of an axisymmetric element.  The factors were probed on one element of each type
# (ccx 2.23 prints the estimate): C3D8R's is 0.625 there (0.938 in later sources).
COURANT_FACTOR = (("C3D20", 0.3), ("C3D10", 0.3), ("C3D15", 0.3), ("C3D8I", 0.125),
                  ("C3D8R", 0.625), ("C3D8", 0.9), ("C3D4", 1.0), ("C3D6", 1.0))
COURANT_BRICK = (("S3", "C3D6"), ("M3D3", "C3D6"), ("CPS3", "C3D6"), ("CPE3", "C3D6"),
                 ("CAX3", "C3D6"), ("S4R", "C3D8R"), ("M3D4R", "C3D8R"), ("CPS4R", "C3D8R"),
                 ("CPE4R", "C3D8R"), ("CAX4R", "C3D8R"), ("S4", "C3D8I"), ("M3D4", "C3D8"),
                 ("CPS4", "C3D8"), ("CPE4", "C3D8"), ("CAX4", "C3D8"), ("S6", "C3D15"),
                 ("M3D6", "C3D15"), ("CPS6", "C3D15"), ("CPE6", "C3D15"), ("CAX6", "C3D15"),
                 ("S8R", "C3D20R"), ("M3D8R", "C3D20R"), ("CPS8R", "C3D20R"), ("CPE8R", "C3D20R"),
                 ("CAX8R", "C3D20R"), ("S8", "C3D20"), ("M3D8", "C3D20"), ("CPS8", "C3D20"),
                 ("CPE8", "C3D20"), ("CAX8", "C3D20"), ("B31R", "C3D8R"), ("B31", "C3D8I"),
                 ("B21", "C3D8I"), ("T3D2", "C3D8I"), ("T2D2", "C3D8I"), ("B32R", "C3D20R"),
                 ("B32", "C3D20"), ("T3D3", "C3D20"))
HEX_FACES = ((3, 2, 1, 0), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7))
TET_FACES = ((0, 2, 1), (0, 1, 3), (1, 2, 3), (0, 3, 2))
WEDGE_FACES = ((0, 2, 1), (3, 4, 5), (0, 1, 4, 3), (1, 2, 5, 4), (3, 5, 2, 0))


def _face_area(p: Sequence[Vec]) -> float:
    """Area of a straight-edged triangle or (warped: its one-point Jacobian) quadrilateral."""
    if len(p) == 3:
        return 0.5 * vnorm(vcross(vsub(p[1], p[0]), vsub(p[2], p[0])))
    return 0.5 * vnorm(vcross(vsub(p[2], p[0]), vsub(p[3], p[1])))


def _tet_volume(a: Vec, b: Vec, c: Vec, d: Vec) -> float:
    return abs(vdot(vsub(b, a), vcross(vsub(c, a), vsub(d, a)))) / 6.0


def max_normal_stiffness(typ: str, v: Sequence[float]) -> Optional[float]:
    """The largest normal stiffness (C11, C22, C33) of an orthotropic or anisotropic
    *ELASTIC card of TYPE ``typ`` with values ``v`` (its first temperature)."""
    try:
        if typ.startswith("ENGINEERING"):
            e1, e2, e3, n12, n13, n23 = v[:6]
            s = [[1 / e1, -n12 / e1, -n13 / e1], [-n12 / e1, 1 / e2, -n23 / e2],
                 [-n13 / e1, -n23 / e2, 1 / e3]]
            det = (s[0][0] * (s[1][1] * s[2][2] - s[1][2] * s[2][1])
                   - s[0][1] * (s[1][0] * s[2][2] - s[1][2] * s[2][0])
                   + s[0][2] * (s[1][0] * s[2][1] - s[1][1] * s[2][0]))
            diag = [(s[1][1] * s[2][2] - s[1][2] ** 2) / det, (s[0][0] * s[2][2] - s[0][2] ** 2) / det,
                    (s[0][0] * s[1][1] - s[0][1] ** 2) / det]
        elif typ.startswith(("ORTHO", "ANISO")):
            diag = [v[0], v[2], v[5]]
        elif typ == "LAMINA":
            e1, e2, n12 = v[:3]
            diag = [max(e1, e2) / (1 - n12 * n12 * e2 / e1)]
        else:
            return None
    except (IndexError, ValueError, ZeroDivisionError):
        return None
    k = max(diag)
    return k if math.isfinite(k) and k > 0 else None


def courant_length(ctype: str, pts: Sequence[Vec], section: dict) -> Optional[float]:
    """h * f of ccx's explicit increment estimate (COURANT_FACTOR) for an element of ccx
    type ``ctype`` with node coordinates ``pts``; ``section``: 't' (shell, membrane or
    plane thickness), 'area' (truss), 'rect' (a, b), 'circ' (diameter).  None for
    elements ccx does not size (springs, masses...) or that cannot be measured."""
    brick = next((b for p, b in COURANT_BRICK if ctype.startswith(p)), ctype)
    f = next((v for p, v in COURANT_FACTOR if brick.startswith(p)), None)
    if f is None or not pts:
        return None
    if ctype.startswith("C3D"):
        if brick.startswith(("C3D4", "C3D10")) and len(pts) >= 4:
            vol = _tet_volume(*pts[:4])
            areas = [(3.0, _face_area([pts[i] for i in fc])) for fc in TET_FACES]
        elif brick.startswith(("C3D6", "C3D15")) and len(pts) >= 6:
            c = pts[:6]
            vol = _tet_volume(c[0], c[1], c[2], c[3]) + _tet_volume(c[1], c[2], c[3], c[4]) + \
                _tet_volume(c[2], c[3], c[4], c[5])
            areas = [(1.0 if len(fc) == 3 else 2.0, _face_area([c[i] for i in fc]))
                     for fc in WEDGE_FACES]
        elif len(pts) >= 8:
            c = pts[:8]
            sg = ((-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
                  (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1))
            jac = [tuple(sum(sg[n][d] * c[n][x] for n in range(8)) / 8.0 for x in range(3))
                   for d in range(3)]
            vol = 8.0 * abs(vdot(jac[0], vcross(jac[1], jac[2])))
            areas = [(1.0, _face_area([c[i] for i in fc])) for fc in HEX_FACES]
        else:
            return None
        hs = [k * vol / a for k, a in areas if a > 0]
        return min(hs) * f if hs and vol > 0 else None
    if ctype.startswith(("B", "T3D", "T2D")):       # a beam or truss: a box along the axis
        end = 1 if ctype.startswith(("B31", "B21", "T3D2", "T2D2")) else 2
        if len(pts) <= end:
            return None
        sizes = [vnorm(vsub(pts[end], pts[0]))]
        if "rect" in section:
            sizes += list(section["rect"])
        elif "circ" in section:                 # ccx sees the box around the circle
            sizes.append(math.sqrt(2.0) * section["circ"])
        elif "area" in section:
            sizes.append(math.sqrt(section["area"]))
        else:
            return None
        return min(sizes) * f if min(sizes) > 0 else None
    # a shell, membrane or plane element: the brick ccx makes of it, its polygon moved by
    # half the thickness to either side (an axisymmetric one: turned about the y axis by
    # 1 degree to either side), sized as that brick
    n = 3 if brick.startswith(("C3D6", "C3D15")) else 4
    if len(pts) < n:
        return None
    poly = list(pts[:n])
    if ctype.startswith("CAX"):
        a = math.radians(1.0)
        sides = [[(x * math.cos(a), y, s * x * math.sin(a)) for x, y, _z in poly] for s in (-1, 1)]
    else:
        t = section.get("t")
        normal = vcross(vsub(poly[2], poly[0]), vsub(poly[-1], poly[1]))
        if not t or vnorm(normal) == 0:
            return None
        normal = vscale(normal, 0.5 * t / vnorm(normal))
        sides = [[vsub(q, normal) for q in poly], [vadd(q, normal) for q in poly]]
    return courant_length(brick, sides[0] + sides[1], section)


def ccx_label_ok(label: str, allowed: set) -> bool:
    """Whether ccx accepts ``label`` on a card with label set ``allowed`` (ccx compares
    the first 4 characters; SDV1..SDVn match SDV)."""
    lab = label.upper()
    if lab.startswith("SDV") and "SDV" in allowed:
        return True
    return lab[:4] in allowed

# Abaqus *DLOAD body-force labels CalculiX has no equivalent for (verified: ccx accepts
# only GRAV and CENTRIF body loads, and rejects the whole *DLOAD on any of these).  CENT
# is Abaqus' density-scaled centrifugal load; ROTA/CORIO/ROTDYNF are rotary-acceleration /
# Coriolis / rotor-dynamic loads.
DLOAD_UNSUPPORTED = {"CENT", "ROTA", "CORIO", "ROTDYNF"}

# In a deck with temperatures, ccx 2.23 runs a linear-elastic material correctly in linear
# steps only when its *ELASTIC form is at least as anisotropic as its *EXPANSION (probed).
# With an isotropic *ELASTIC and a TYPE=ORTHO or ANISO expansion, its stress routine stores
# the stiffness in orthotropic/anisotropic form while the element stiffness still reads it
# as (E, nu): E becomes lambda + 2 mu and nu becomes lambda, a wrong stiffness for every
# load, without an error.  A free heated cube (E = 1000, nu = 0.2, alpha = 1e-3, 2e-3, 4e-3)
# shrinks with strains near -2, with or without an *ORIENTATION; frequencies come out 17x
# too low.  An orthotropic or engineering-constants *ELASTIC fails the same way with an
# ANISO expansion unless an *ORIENTATION applies.
# (emitted *ELASTIC type, expansion type) -> the type that works, with the same stiffness.
ELASTIC_FOR_EXPANSION = {("ISO", "ORTHO"): "ENGINEERING CONSTANTS", ("ISO", "ANISO"): "ANISO",
                         ("ENGINEERING CONSTANTS", "ANISO"): "ANISO", ("ORTHO", "ANISO"): "ANISO"}
# Material cards that put ccx on its nonlinear material path, which combines any *ELASTIC
# with any *EXPANSION correctly (verified for *PLASTIC and *CREEP) but accepts only an
# isotropic or orthotropic *ELASTIC: such materials (and those with a kept *PLASTIC) are
# left as they are.
INELASTIC_MATERIAL_CARDS = {"CREEP", "DEFORMATION PLASTICITY", "HYPERELASTIC", "HYPERFOAM",
                            "MOHR COULOMB", "USER MATERIAL"}


def ortho_from_iso(e: float, nu: float) -> List[float]:
    """The 9 ccx TYPE=ORTHO constants (D1111, D1122, D2222, D1133, D2233, D3333, D1212,
    D1313, D2323) of an isotropic material."""
    lam = e * nu / ((1.0 + nu) * (1.0 - 2.0 * nu))
    mu = e / (2.0 * (1.0 + nu))
    return [lam + 2.0 * mu, lam, lam + 2.0 * mu, lam, lam, lam + 2.0 * mu, mu, mu, mu]


def ortho_from_engineering(v: Sequence[float]) -> List[float]:
    """The 9 ccx TYPE=ORTHO constants of engineering constants (E1, E2, E3, nu12, nu13,
    nu23, G12, G13, G23), computed the way ccx converts them when it reads them."""
    e1, e2, e3, n12, n13, n23, g12, g13, g23 = v
    n21, n31, n32 = n12 * e2 / e1, n13 * e3 / e1, n23 * e3 / e2
    gam = 1.0 / (1.0 - n12 * n21 - n23 * n32 - n31 * n13 - 2.0 * n21 * n32 * n13)
    return [e1 * (1.0 - n23 * n32) * gam, e1 * (n21 + n31 * n23) * gam,
            e2 * (1.0 - n13 * n31) * gam, e1 * (n31 + n21 * n32) * gam,
            e2 * (n32 + n12 * n31) * gam, e3 * (1.0 - n12 * n21) * gam, g12, g13, g23]


def aniso_from_ortho(d: Sequence[float]) -> List[float]:
    """The 21 ccx TYPE=ANISO constants (D1111, D1122, D2222, D1133, D2233, D3333, D1112,
    D2212, D3312, D1212, D1113, D2213, D3313, D1213, D1313, D1123, D2223, D3323, D1223,
    D1323, D2323) of the 9 orthotropic ones."""
    z = 0.0
    return [d[0], d[1], d[2], d[3], d[4], d[5], z, z, z, d[6], z, z, z, z, d[7],
            z, z, z, z, z, d[8]]


def _fortran_real_like(text: str) -> bool:
    """Whether ccx 2.23 reads ``text`` as a number on an ``*ORIENTATION`` data line.  It
    tries ``(f20.0)`` on the first 20 characters before taking the line as a distribution
    name, and gfortran accepts names such as ``D1``, ``E-3``, ``Q1``, ``1+2``, ``12``,
    ``.``, ``+``, ``INF`` and ``NAN`` there (verified): the orientation then silently
    becomes a plain one with zero axes and the stiffness matrix is singular."""
    s = text.strip().upper()[:20]
    return bool(re.fullmatch(r"[+-]?\d*\.?\d*(?:[EDQ][+-]?\d+|[+-]\d+)?", s)
                or re.fullmatch(r"[+-]?(?:INF|INFINITY|NAN(?:\(.*\))?)", s))


def _distribution_axes(vals: Sequence[float], rect: bool,
                       rot: Optional[Tuple[int, float]]) -> Tuple[Vec, Vec]:
    """The ccx points ``a``, ``b`` of one orientation-distribution line ``a, b[, c]``.

    For a rectangular system the origin ``c`` is subtracted (ccx ignores fields past the
    sixth; Abaqus measures a and b from c) and an additional rotation ``(local axis,
    degrees)`` is applied to the axes themselves: ccx 2.23 turns only a distribution's
    first line by the *ORIENTATION's rotation line and leaves the others practically
    unrotated (verified).  Cylindrical a, b are points on the axis and are kept."""
    a, b = tuple(vals[0:3]), tuple(vals[3:6])
    if not rect:
        return a, b
    if len(vals) >= 9 and any(vals[6:9]):
        c = tuple(vals[6:9])
        a, b = vsub(a, c), vsub(b, c)
    if rot and rot[1]:
        e1 = vunit(a)
        e3 = vunit(vcross(a, b))
        e2 = vcross(e3, e1)
        axis = (e1, e2, e3)[rot[0] - 1]
        origin = (0.0, 0.0, 0.0)
        a = rotate_about_axis(e1, origin, axis, rot[1])
        b = rotate_about_axis(e2, origin, axis, rot[1])
    return a, b

# Abaqus connector elements and the connection types of *CONNECTOR SECTION (first data
# line: one assembled type, or a basic translational and/or a basic rotational type).
# ccx has no connector element; the converter writes the kinematic constraint of the types
# below as ccx constraints (see Converter._plan_connectors) — without a *CONNECTOR BEHAVIOR,
# a connector is exactly its constraint.
CONN_TYPES = ("CONN3D2", "CONN2D2")
CONN_ASSEMBLED = {"HINGE": ("JOIN", "REVOLUTE"), "WELD": ("JOIN", "ALIGN"),
                  "CYLINDRICAL": ("SLOT", "REVOLUTE"), "TRANSLATOR": ("SLOT", "ALIGN"),
                  "PLANAR": ("SLIDE-PLANE", "REVOLUTE"), "UJOINT": ("JOIN", "UNIVERSAL"),
                  "CVJOINT": ("JOIN", "CONSTANT VELOCITY"),
                  "BUSHING": ("PROJECTION CARTESIAN", "PROJECTION FLEXION-TORSION")}
CONN_TRANSLATIONAL = {"JOIN", "LINK", "SLOT", "SLIDE-PLANE", "CARTESIAN", "AXIAL",
                      "PROJECTION CARTESIAN", "RADIAL-THRUST", "ACCELEROMETER"}
CONN_ROTATIONAL = {"REVOLUTE", "ALIGN", "UNIVERSAL", "CONSTANT VELOCITY", "CARDAN", "EULER",
                   "ROTATION", "FLEXION-TORSION", "PROJECTION FLEXION-TORSION",
                   "ROTATION-ACCELEROMETER"}
# basic types with no kinematic constraint (every relative motion is available): without
# a behaviour such a component transmits nothing
CONN_UNCONSTRAINED = {"CARTESIAN", "AXIAL", "PROJECTION CARTESIAN", "CARDAN", "EULER",
                      "ROTATION", "FLEXION-TORSION", "PROJECTION FLEXION-TORSION"}


# ---------------------------------------------------------------------------
# Load audit: which steps still carry a load after conversion
# ---------------------------------------------------------------------------

# Eigenvalue extractions solve without any load.
LOAD_FREE_PROCEDURES = {"FREQUENCY", "COMPLEX FREQUENCY"}
# Linear-perturbation procedures: only the loads given in the step itself act, and they do
# not carry over to later steps.
PERTURBATION_PROCEDURES = {"BUCKLE", "MODAL DYNAMIC", "STEADY STATE DYNAMICS"}
# History cards that load the model -> the field (0-based) whose non-zero value makes a
# data line a load.  *BOUNDARY loads only through a prescribed non-zero value (field 3), a
# film / radiation condition through its coefficient / emissivity (field 3).
LOAD_CARD_FIELD = {"CLOAD": 2, "DLOAD": 2, "DSLOAD": 2, "BOUNDARY": 3, "TEMPERATURE": 1,
                   "CFLUX": 2, "DFLUX": 2, "DSFLUX": 2, "FILM": 3, "SFILM": 3, "RADIATE": 3,
                   "SRADIATE": 3, "CONNECTOR MOTION": 2, "CONNECTOR LOAD": 2, "BASE MOTION": -1}
# ccx user subroutine that supplies the magnitude of a user-defined load / BC card (Abaqus
# writes USER on the card, or a load label ending in NU).
CCX_USER_SUBROUTINE = {"BOUNDARY": "uboun.f", "CLOAD": "cload.f", "DLOAD": "dload.f",
                       "DSLOAD": "dload.f", "FILM": "film.f", "SFILM": "film.f",
                       "DFLUX": "dflux.f", "DSFLUX": "dflux.f", "CFLUX": "cflux.f",
                       "RADIATE": "radiate.f", "SRADIATE": "radiate.f",
                       "TEMPERATURE": "utemp.f", "AMPLITUDE": "uamplitude.f"}


def _is_user_load(b: Block, f: Sequence[str]) -> bool:
    """Whether data line ``f`` of load card ``b`` takes its magnitude from a user
    subroutine: USER on the card, or a distributed / film / flux label ending in NU."""
    if b.has("USER"):
        return True
    return b.keyword not in ("CLOAD", "BOUNDARY", "TEMPERATURE", "CFLUX") and len(f) > 1 and \
        f[1].strip().upper().endswith("NU")


def _load_entries(b: Block, user_loads: bool) -> List[Tuple[tuple, Optional[str]]]:
    """(key, description) per data line of load card ``b``; the description is None where
    the line applies no load (a zero value, a homogeneous BC).  ``user_loads``: whether a
    user-subroutine magnitude counts as a load (see step_load_audit)."""
    kw = b.keyword
    idx = LOAD_CARD_FIELD[kw]
    out: List[Tuple[tuple, Optional[str]]] = []
    if idx < 0:                                   # *BASE MOTION: the card is the load
        return [((kw, tuple(b.params.items())), f"*{kw}")]
    for rec in merged_data_records(b):
        f = [x.strip() for x in rec]
        if not f or not any(f):
            continue
        target = f[0] or "the whole model"
        label = f[1].upper() if len(f) > 1 else ""
        if kw == "BOUNDARY":
            try:
                d1 = int(label)
                d2 = int(f[2]) if len(f) > 2 and f[2] else d1
            except ValueError:                    # a named type (ENCASTRE, XSYMM, ...)
                continue
            keys = [(kw, f[0].upper(), d) for d in range(min(d1, d2), max(d1, d2) + 1)]
        else:
            keys = [(kw, f[0].upper(), label)]
        desc: Optional[str] = None
        if _is_user_load(b, f):
            if user_loads:
                desc = f"*{kw} on {target} (user subroutine)"
        elif kw == "TEMPERATURE":
            desc = f"*TEMPERATURE on {target}" if len(f) > 1 and f[1] else None
        else:
            val = f[idx] if len(f) > idx else ""
            try:
                nonzero = bool(val) and pf(val) != 0.0
            except ValueError:                    # unresolved symbol: assume it loads
                nonzero = True
            if nonzero:
                desc = (f"*BOUNDARY: prescribed value on {target}" if kw == "BOUNDARY"
                        else f"*{kw} {label} on {target}" if kw in ("DLOAD", "DSLOAD")
                        else f"*{kw} on {target}")
        out += [(k, desc) for k in keys]
    return out


def step_load_audit(blocks: Sequence[Block], user_loads: bool) -> List[Optional[List[str]]]:
    """Per *STEP, in order: None for an eigenvalue extraction (it needs no load), else the
    loads active in the step — an empty list means the step solves with no load at all,
    i.e. to a zero response.  Loads and prescribed BCs carry over to later steps until an
    OP=NEW card of the same keyword; a linear-perturbation step counts only its own loads.
    Initial velocities load a dynamic step, initial stresses any step.

    ``user_loads``: whether a magnitude that comes from a user subroutine (USER, ...NU
    labels) counts.  It does in an Abaqus deck; in a ccx deck the stock ccx subroutine
    would run in place of the deck's own, so it does not."""
    state: Dict[str, Dict[tuple, str]] = {}
    initial: Dict[str, List[str]] = {"VELOCITY": [], "STRESS": []}
    fresh: Dict[str, set] = {}             # keys (re)defined in the current step, per card

    def apply(b: Block, into: Dict[str, Dict[tuple, str]]) -> None:
        card = into.setdefault(b.keyword, {})
        if (b.param("OP") or "").strip().upper() == "NEW":
            # OP=NEW removes what earlier steps applied, not the cards before it in this
            # step (Abaqus; probed on ccx 2.23 for *CLOAD and *BOUNDARY)
            kept = fresh.get(b.keyword, set())
            into[b.keyword] = card = {k: v for k, v in card.items() if k in kept}
        for key, desc in _load_entries(b, user_loads):
            fresh.setdefault(b.keyword, set()).add(key)
            if desc:
                card[key] = desc
            else:
                card.pop(key, None)

    out: List[Optional[List[str]]] = []
    step: Optional[List[Block]] = None
    for b in list(blocks) + [Block("END STEP", OrderedDict())]:
        kw = b.keyword
        if kw == "STEP":
            step = [b]
            fresh.clear()
            continue
        if kw != "END STEP":
            if step is not None:
                step.append(b)
            elif kw in LOAD_CARD_FIELD:           # model-data *BOUNDARY
                apply(b, state)
            elif kw == "INITIAL CONDITIONS":
                typ = (b.param("TYPE") or "").strip().upper()
                # the values: node, DOF, velocity | node set, angular velocity, axis ... |
                # element, stress components
                lo, hi = {"VELOCITY": (2, 3), "ROTATING VELOCITY": (1, 2)}.get(typ, (1, None))
                typ = "VELOCITY" if typ == "ROTATING VELOCITY" else typ
                if typ in initial:
                    nums = [x for r in merged_data_records(b) for x in r[lo:hi] if x.strip()]
                    try:
                        moving = any(pf(x) != 0.0 for x in nums)
                    except ValueError:
                        moving = True
                    if moving:
                        initial[typ].append(f"*INITIAL CONDITIONS, TYPE={typ}")
            continue
        if step is None:
            continue
        proc = next((x.keyword for x in step if x.keyword in PROC_KW), None)
        perturb = proc in PERTURBATION_PROCEDURES or (step[0].has("PERTURBATION") and
                                                      proc not in LOAD_FREE_PROCEDURES)
        active = {} if perturb else state
        for x in step[1:]:
            if x.keyword in LOAD_CARD_FIELD:
                apply(x, active)
        if proc in LOAD_FREE_PROCEDURES:
            out.append(None)
        else:
            loads = [d for card in active.values() for d in card.values()] + initial["STRESS"]
            if proc in ("DYNAMIC", "MODAL DYNAMIC"):
                loads += initial["VELOCITY"]
            out.append(dedup_str(loads))
        step = None
    return out


# ---------------------------------------------------------------------------
# Consistent nodal forces of distributed loads ccx has no card for
# ---------------------------------------------------------------------------

# Gauss rules: 4-point Gauss-Legendre on [-1, 1]; 3 x 3 Gauss on the square; the 7-point
# degree-5 rule on the triangle 0 <= r, s, r + s <= 1 (weights sum to its area 1/2).
_GAUSS_LINE = ((-0.8611363115940526, 0.3478548451374538), (-0.3399810435848563, 0.6521451548625461),
               (0.3399810435848563, 0.6521451548625461), (0.8611363115940526, 0.3478548451374538))
_GAUSS3 = ((-0.7745966692414834, 5.0 / 9.0), (0.0, 8.0 / 9.0), (0.7745966692414834, 5.0 / 9.0))
_GAUSS_QUAD = tuple((a, b, wa * wb) for a, wa in _GAUSS3 for b, wb in _GAUSS3)
_GAUSS_TRI = ((1.0 / 3.0, 1.0 / 3.0, 0.1125),
              *((r, s, 0.0661970763942531) for r, s in ((0.4701420641051151, 0.4701420641051151),
                                                        (0.0597158717897698, 0.4701420641051151),
                                                        (0.4701420641051151, 0.0597158717897698))),
              *((r, s, 0.0629695902724136) for r, s in ((0.1012865073234563, 0.1012865073234563),
                                                        (0.7974269853530873, 0.1012865073234563),
                                                        (0.1012865073234563, 0.7974269853530873))))
_Q8_MID = ((0.0, -1.0), (1.0, 0.0), (0.0, 1.0), (-1.0, 0.0))
_Q4_CORNER = ((-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0))


def _shape(kind: str, n: int, a: float, b: float = 0.0) -> Tuple[List[float], List[float], List[float]]:
    """Shape functions N and their derivatives along both face coordinates at (a, b) of an
    edge (``kind`` "line": 2 or 3 nodes, corners first) or a face ("area": tri 3/6, quad
    4/8 nodes, corners first, then the midside nodes after each corner)."""
    if kind == "line":
        if n == 2:
            return [(1 - a) / 2, (1 + a) / 2], [-0.5, 0.5], [0.0, 0.0]
        return [a * (a - 1) / 2, a * (a + 1) / 2, 1 - a * a], [a - 0.5, a + 0.5, -2 * a], [0.0] * 3
    if n in (3, 6):                                    # triangle, area coordinates
        l1, l2, l3 = 1 - a - b, a, b
        if n == 3:
            return [l1, l2, l3], [-1.0, 1.0, 0.0], [-1.0, 0.0, 1.0]
        return ([l1 * (2 * l1 - 1), l2 * (2 * l2 - 1), l3 * (2 * l3 - 1), 4 * l1 * l2, 4 * l2 * l3,
                 4 * l3 * l1],
                [1 - 4 * l1, 4 * l2 - 1, 0.0, 4 * (l1 - l2), 4 * l3, -4 * l3],
                [1 - 4 * l1, 0.0, 4 * l3 - 1, -4 * l2, 4 * l2, 4 * (l1 - l3)])
    N, da, db = [], [], []
    for ai, bi in _Q4_CORNER:
        if n == 4:
            N.append((1 + a * ai) * (1 + b * bi) / 4)
            da.append(ai * (1 + b * bi) / 4)
            db.append(bi * (1 + a * ai) / 4)
        else:
            N.append((1 + a * ai) * (1 + b * bi) * (a * ai + b * bi - 1) / 4)
            da.append(ai * (1 + b * bi) * (2 * a * ai + b * bi) / 4)
            db.append(bi * (1 + a * ai) * (a * ai + 2 * b * bi) / 4)
    if n == 8:
        for ai, bi in _Q8_MID:
            if ai == 0.0:
                N.append((1 - a * a) * (1 + b * bi) / 2)
                da.append(-a * (1 + b * bi))
                db.append(bi * (1 - a * a) / 2)
            else:
                N.append((1 + a * ai) * (1 - b * b) / 2)
                da.append(ai * (1 - b * b) / 2)
                db.append(-b * (1 + a * ai))
    return N, da, db


def consistent_nodal_forces(kind: str, xyz: Sequence[Vec], load, axisymmetric: bool = False
                            ) -> List[Vec]:
    """f_i = integral of N_i t over one edge or face in its undeformed geometry, by Gauss
    quadrature (exact for the constant tractions and line loads of straight or flat
    members, and to quadrature accuracy on curved ones).  ``kind`` is "line" (2/3 nodes) or
    "area" (3/6/4/8 nodes), corner nodes first.  ``load(point, normal, tangent)`` gives
    the traction / line load vector there: an edge passes its in-plane (x-y) normal, a
    face its unit normal; the tangent is the unit edge direction (None on a face).  An
    axisymmetric edge integrates over the full circle (2 pi r ds, r = x): ccx reads a
    concentrated load on an axisymmetric node as the total around the circumference
    (probed on 2.23 against a pressure-loaded twin)."""
    n = len(xyz)
    rule = (((g, 0.0, w) for g, w in _GAUSS_LINE) if kind == "line" else
            _GAUSS_TRI if n in (3, 6) else _GAUSS_QUAD)
    forces = [[0.0, 0.0, 0.0] for _ in range(n)]
    for a, b, w in rule:
        N, da, db = _shape(kind, n, a, b)
        p = tuple(sum(N[i] * xyz[i][k] for i in range(n)) for k in range(3))
        ga = tuple(sum(da[i] * xyz[i][k] for i in range(n)) for k in range(3))
        if kind == "line":
            jac = vnorm(ga)
            tangent: Optional[Vec] = vunit(ga)
            normal = vunit((ga[1], -ga[0], 0.0))
            if axisymmetric:
                jac *= 2.0 * math.pi * p[0]
        else:
            gb = tuple(sum(db[i] * xyz[i][k] for i in range(n)) for k in range(3))
            cross = vcross(ga, gb)
            jac = vnorm(cross)
            normal, tangent = vunit(cross), None
        t = load(p, normal, tangent)
        for i in range(n):
            s = N[i] * jac * w
            for k in range(3):
                forces[i][k] += s * t[k]
    return [(f[0], f[1], f[2]) for f in forces]


def blocks_from_lines(lines: Sequence[str]) -> List[Block]:
    """The keyword cards of flat deck text (no *INCLUDE, *PARAMETER or keyword continuation
    lines) — the converter's own output.  Mesh data lines are skipped."""
    blocks: List[Block] = []
    cur: Optional[Block] = None
    for raw in lines:
        s = raw.strip()
        if not s or s.startswith("**"):
            continue
        if s.startswith("*"):
            kw, params = parse_keyword_line(s)
            cur = Block(kw, params)
            blocks.append(cur)
        elif cur is not None and cur.keyword not in GEOM_KW:
            cur.data.append(s)
    return blocks


# ---------------------------------------------------------------------------
# Converter
# ---------------------------------------------------------------------------


def bc_steps(segments: List[List[Tuple[bool, Tuple[int, int], bool]]]):
    """Yield the *BOUNDARY DOFs in force in each step, as {(node, dof): held at zero}, from
    the BC entries (OP=NEW, (node, dof), zero value) of the model data (segments[0]) and of
    each step.  Abaqus and ccx semantics: a step keeps the BCs in force before it, a later
    value on a DOF replaces the earlier one, and a step with a *BOUNDARY, OP=NEW starts from
    none.  A deck without steps yields the model data's BCs.  (One dict, updated in place.)"""
    active: Dict[Tuple[int, int], bool] = {}
    for _, k, z in segments[0]:
        active[k] = z
    if len(segments) == 1:
        yield active
    for seg in segments[1:]:
        if any(new for new, _, _ in seg):
            active = {}
        for _, k, z in seg:
            active[k] = z
        yield active


# ---------------------------------------------------------------------------
# Velocity / acceleration boundary conditions (ccx prescribes displacements only)
# ---------------------------------------------------------------------------

# 5-point Gauss-Legendre rule on [-1, 1] (node, weight): exact up to degree 9, so one panel
# integrates a piecewise-linear or SMOOTH STEP (quintic) amplitude piece - once or twice -
# exactly.
_GL5 = ((-0.9061798459386640, 0.2369268850561891), (-0.5384693101056831, 0.4786286704993665),
        (0.0, 0.5688888888888889), (0.5384693101056831, 0.4786286704993665),
        (0.9061798459386640, 0.2369268850561891))


@dataclass
class AmplitudeCurve:
    """An Abaqus *AMPLITUDE as a function of its own time (``value``).  ``breaks``: the
    times where it is not smooth; ``panel``: the length of one integration panel for a
    non-polynomial curve (PERIODIC / MODULATED / DECAY; 0 = polynomial pieces);
    ``total``: TIME=TOTAL TIME; ``absolute``: VALUE=ABSOLUTE (its values replace the
    magnitude on the card); ``corners``: the inner points of a piecewise-linear curve
    where its slope changes, which Abaqus smooths where it needs the curve's time
    derivative, by ``smooth`` (its SMOOTH parameter; None: the default, 0.25 in
    Abaqus/Standard and 0 in Abaqus/Explicit)."""
    value: Callable[[float], float]
    breaks: List[float]
    panel: float = 0.0
    total: bool = False
    absolute: bool = False
    corners: List[float] = field(default_factory=list)
    smooth: Optional[float] = None


def amplitude_curve(b: Block) -> Optional[AmplitudeCurve]:
    """The time function of an Abaqus *AMPLITUDE - TABULAR, EQUALLY SPACED, SMOOTH STEP,
    PERIODIC, MODULATED or DECAY - or None for the other definitions (USER, SOLUTION
    DEPENDENT, BUBBLE, ...), data in an INPUT file or unreadable data.  SCALEX/SCALEY then
    SHIFTX/SHIFTY act on the points of the point-wise forms, as in handle_amplitude and
    ccx; before its first and after its last point such an amplitude keeps its end values
    (Abaqus and ccx alike)."""
    definition = (b.param("DEFINITION") or "TABULAR").strip().upper()
    total = (b.param("TIME") or "").upper().replace(" ", "") == "TOTALTIME"
    absolute = (b.param("VALUE") or "").strip().upper() == "ABSOLUTE"

    def num(key: str, default: float) -> float:
        v = b.param(key)
        return pf(v) if v not in (None, "") else default
    try:
        sx, sy, dx, dy = num("SCALEX", 1.0), num("SCALEY", 1.0), num("SHIFTX", 0.0), num("SHIFTY", 0.0)
        vals = [pf(x) for rec in merged_data_records(b) for x in rec if x != ""]
        fixed, begin = num("FIXED INTERVAL", 0.0), num("BEGIN", 0.0)
    except ValueError:
        return None
    try:
        smooth = num("SMOOTH", -1.0)                 # -1: not given
    except ValueError:
        smooth = -1.0
    if b.has("INPUT") or not vals:
        return None
    if definition in ("TABULAR", "SMOOTH STEP", "EQUALLY SPACED"):
        if definition == "EQUALLY SPACED":
            if fixed <= 0.0:
                return None
            pts = [(begin + i * fixed, a) for i, a in enumerate(vals)]
        else:
            pts = [(vals[i], vals[i + 1]) for i in range(0, len(vals) - 1, 2)]
        ts = [t * sx + dx for t, _ in pts]
        amps = [a * sy + dy for _, a in pts]
        if not ts or any(t1 < t0 for t0, t1 in zip(ts, ts[1:])):
            return None
        step = definition == "SMOOTH STEP"

        def tabular(t: float) -> float:
            if t <= ts[0]:
                return amps[0]
            if t >= ts[-1]:
                return amps[-1]
            i = bisect.bisect_right(ts, t) - 1          # ts[i] <= t < ts[i + 1]
            x = (t - ts[i]) / (ts[i + 1] - ts[i])
            if step:
                x = x ** 3 * (10.0 - 15.0 * x + 6.0 * x * x)
            return amps[i] + (amps[i + 1] - amps[i]) * x
        slopes = [(a1 - a0) / (t1 - t0) if t1 > t0 else math.inf
                  for t0, t1, a0, a1 in zip(ts, ts[1:], amps, amps[1:])]
        corners = [] if step else [ts[i + 1] for i, (s0, s1) in enumerate(zip(slopes, slopes[1:]))
                                   if s0 != s1]
        return AmplitudeCurve(tabular, ts, 0.0, total, absolute, corners,
                              None if smooth < 0.0 else smooth)
    if (sx, sy, dx, dy) != (1.0, 1.0, 0.0, 0.0):
        return None                 # scaling/shifting of the analytic forms: not modelled
    if definition == "PERIODIC" and len(vals) >= 4:
        n = int(vals[0])
        w, t0, a0 = vals[1], vals[2], vals[3]
        ab = vals[4:4 + 2 * n]
        if n < 0 or len(ab) < 2 * n:
            return None

        def periodic(t: float) -> float:
            if t < t0:
                return a0
            return a0 + sum(ab[2 * k - 2] * math.cos(k * w * (t - t0)) +
                            ab[2 * k - 1] * math.sin(k * w * (t - t0)) for k in range(1, n + 1))
        return AmplitudeCurve(periodic, [t0], 2.0 * math.pi / (8.0 * max(n, 1) * abs(w)) if w else 0.0,
                              total, absolute)
    if definition == "MODULATED" and len(vals) >= 5:
        a0, a, t0, w1, w2 = vals[:5]

        def modulated(t: float) -> float:
            return a0 if t <= t0 else a0 + a * math.sin(w1 * (t - t0)) * math.sin(w2 * (t - t0))
        w = abs(w1) + abs(w2)
        return AmplitudeCurve(modulated, [t0], 2.0 * math.pi / (8.0 * w) if w else 0.0, total, absolute)
    if definition == "DECAY" and len(vals) >= 4 and vals[3] > 0.0:
        a0, a, t0, td = vals[:4]

        def decay(t: float) -> float:
            return a0 if t < t0 else a0 + a * math.exp(-(t - t0) / td)
        return AmplitudeCurve(decay, [t0], td / 4.0, total, absolute)
    return None


def integrate_history(rate: Callable[[float], float], breaks: Sequence[float], period: float,
                      order: int = 1, x0: float = 0.0, r0: float = 0.0, panel: float = 0.0,
                      rel_tol: float = 1e-4, max_points: int = 1000):
    """The motion a velocity (``order`` 1) or acceleration (``order`` 2) history prescribes
    over a step of length ``period``: x(t) = x0 + int_0^t rate, or x0 + r0 t +
    int_0^t (t - s) rate(s) ds, t in step time.  Returns (points, x(period), r(period),
    deviation) with r = r0 + int rate.  ``points`` [(t, x)] are exact - Gauss-Legendre
    panels between ``breaks`` (exact for polynomial pieces; a non-polynomial curve gets
    panels no longer than ``panel``) - and dense enough that the straight lines between
    them, which is what ccx applies, stay within rel_tol of the largest |x - x0| of the
    step; a piecewise-constant rate (piecewise-linear x) is exact at its breakpoints alone.
    ``deviation`` is that bound in absolute terms (above rel_tol only where max_points
    capped the sampling)."""
    cuts = sorted({0.0, period} | {t for t in breaks if 0.0 < t < period})

    def advance(t0: float, x: float, r: float, t1: float) -> Tuple[float, float]:
        n = 1 if panel <= 0.0 else max(1, min(4096, math.ceil((t1 - t0) / panel)))
        h = (t1 - t0) / n
        dx = dr = 0.0
        for k in range(n):
            a = t0 + k * h
            for xi, w in _GL5:
                s = a + (xi + 1.0) * 0.5 * h
                f = rate(s) * w * 0.5 * h
                dr += f
                dx += f if order == 1 else (t1 - s) * f
        return x + dx + (0.0 if order == 1 else r * (t1 - t0)), r + dr

    # the state at every break, and the step's travel (which sets the tolerance) from
    # coarse samples marched through each smooth piece
    starts = [(cuts[0], x0, r0)]
    travel = 0.0
    for a, c in zip(cuts, cuts[1:]):
        state = starts[-1]
        m = 16 if panel <= 0.0 else max(16, min(4096, math.ceil(2.0 * (c - a) / panel)))
        for k in range(1, m + 1):
            q = a + (c - a) * k / m if k < m else c
            state = (q,) + advance(state[0], state[1], state[2], q)
            travel = max(travel, abs(state[1] - x0))
        starts.append(state)
    if travel == 0.0:
        return [(0.0, x0), (period, x0)], x0, starts[-1][2], 0.0

    def sample(tol: float):
        pts: List[Tuple[float, float]] = [(0.0, x0)]
        dev = 0.0
        for (a, xa, ra), (c, xc, rc) in zip(starts, starts[1:]):
            if order == 1 and len({rate(a + (xi + 1.0) * 0.5 * (c - a)) for xi, _ in _GL5}) == 1:
                pts.append((c, xc))                   # constant rate: x is exactly linear
                continue
            m = 4 if panel <= 0.0 else max(4, math.ceil((c - a) / panel))
            if m > max_points:                       # too many oscillations to follow
                m, dev = max_points, travel
            spans = []
            prev = (a, xa, ra)
            for k in range(1, m + 1):
                nxt = (a + (c - a) * k / m,) + advance(prev[0], prev[1], prev[2],
                                                       a + (c - a) * k / m) if k < m else (c, xc, rc)
                spans.append((prev, nxt, 0))
                prev = nxt
            spans.reverse()
            while spans:
                (p, xp, rp), (q, xq, rq), depth = spans.pop()
                checks = [(p + (q - p) * j / 4.0,) + advance(p, xp, rp, p + (q - p) * j / 4.0)
                          for j in (1, 2, 3)]
                err = max(abs(xm - (xp + (xq - xp) * (tm - p) / (q - p))) for tm, xm, _ in checks)
                if err <= tol or depth >= 40:
                    dev = max(dev, err)
                    pts.append((q, xq))
                elif len(pts) + len(spans) > max_points:
                    return None, dev                    # too fine for max_points
                else:
                    spans.append((checks[1], (q, xq, rq), depth + 1))
                    spans.append(((p, xp, rp), checks[1], depth + 1))
        return pts, dev
    tol = rel_tol * travel
    for _ in range(40):
        pts, dev = sample(tol)
        if pts is not None:
            return pts, starts[-1][1], starts[-1][2], dev
        tol *= 4.0
    raise ValueError("velocity history could not be sampled")      # unreachable in practice


class Converter:

    def __init__(self, report: Report, options) -> None:
        self.report = report
        self.opt = options
        self._approx = bool(getattr(options, "approximate", False))
        self.geom = Geometry()
        self.orientations: Dict[str, Tuple[Vec, Vec, str]] = {}
        self._orient_rotation: Dict[str, Optional[Tuple[int, float]]] = {}
        self.surfaces: Dict[str, Tuple[str, List[Tuple[str, Optional[str]]]]] = {}
        self._elem_types: set = set()
        self._synth_cache: Dict[Tuple[str, float], str] = {}
        # deck-wide facts filled in by _prescan (defaults keep handlers usable standalone)
        self._plane_only: set = set()
        self._shell_nodes: set = set()
        self._beam_nodes: set = set()
        self._n_inactive_rot = 0
        self._depvar_counts: set = set()
        self._fields_set = False
        self._n_steps = 0
        self._step_idx = 0
        self._step_nlgeom = False
        self._synth_counter = 0
        self._has_sensitivity = False
        self._freq_storage = False
        self._general_step_seen = False
        self._cyclic_ok: set = set()
        self._temp_ic_fill = False
        self._temp_ic_default = False
        self._temp_ic_covered: Optional[set] = None    # nodes the deck's initial temperatures name
        self._step_temp_dof: Optional[str] = None  # the step's procedure if temperature is a DOF
        # planar 2-D beams/trusses: element -> its PLANAR_LINE_TYPES type, and the model-data
        # *BOUNDARY lines that keep them in their plane (_plan_planar_constraint)
        self._planar_elems: Dict[int, str] = {}
        self._planar_others: List[str] = []
        self._planar_bc: List[str] = []
        self._planar_twist: List[int] = []         # ... the nodes among them with DOFs 4-5 fixed
        # *BOUNDARY cards whose OP=NEW removes nothing and is dropped: id -> first card of
        # its step (_plan_op_new_rotations)
        self._op_new_drop: Dict[int, bool] = {}
        self._jc_with_rate: set = set()
        # id(*EXPANSION, TYPE=ANISO) written as TYPE=ORTHO -> its material's name
        self._expansion_as_ortho: Dict[int, str] = {}
        # id(*ELASTIC) -> (TYPE of its material's ORTHO/ANISO *EXPANSION, material name)
        self._elastic_expansion: Dict[int, Tuple[str, str]] = {}
        self._expansion_material: Dict[int, str] = {}   # id(*EXPANSION) -> its material's name
        self._ref_nodes: set = set()
        self._rb_rot: Dict[int, int] = {}          # rigid-body REF NODE -> ROT NODE
        self._rb_rot_synth: Dict[int, int] = {}    # ... where the converter created the ROT NODE
        # 2-node beams upgraded to 3-node beams (_upgrade_section_beams): element -> (end node,
        # end node, midside node)
        self._midside: "OrderedDict[int, Tuple[int, int, int]]" = OrderedDict()
        # knot beams: rigid couplings on shell/beam nodes, rotational BCs on circular-section
        # beams and across *BOUNDARY, OP=NEW (see _plan_rigid_couplings,
        # _plan_circ_rotation_knots, _plan_op_new_rotations, _add_knot_beams)
        self._knots: "OrderedDict[int, int]" = OrderedDict()   # node -> free end of its knot beam
        self._knot_e = 1.0                         # knot-beam modulus / section size / length
        self._knot_a = 1.0
        self._knot_ell = 1.0
        self._knot_k: Optional[float] = None       # its conductivity (thermal decks only)
        self._tie_rotations = True                 # False in a heat-transfer-only deck
        self._rot_nodes: set = set()               # nodes with rotations (shell/beam, not truss)
        self._rot_tied: set = set()                # (node, dof) already tied to a body rotation
        # nodes with a *TRANSFORM (local DOFs) -> its (TYPE letter, a, b), or why its local axes
        # are unknown (see _transform_defs / _local_axes)
        self._transformed: Dict[int, Union[Tuple[str, Vec, Vec], str]] = {}
        self._transform_last: Dict[int, int] = {}  # node -> id() of the last *TRANSFORM naming it
        self._transform_twice: set = set()         # nodes named by several cards with equal data
        self._n_transform_sets = 0                 # ABQ2CCX_TRn sets written so far
        # *RIGID BODY ROT NODE (or a connector's rotation node) -> (local 1, local 2) of its
        # REF NODE's *TRANSFORM, which it gets too; REF NODE -> why its ROT NODE cannot (see
        # _plan_rot_axes)
        self._rot_axes: Dict[int, Tuple[Vec, Vec]] = {}
        self._rot_axes_why: Dict[int, str] = {}
        self._rot_axes_warned = False
        self._coupling_plan: Dict[int, dict] = {}  # id(*COUPLING / *KINEMATIC COUPLING) -> plan
        self._last_coupling: Optional[dict] = None
        # *DISTRIBUTION orientations (see _plan_distributions)
        self._dists: "OrderedDict[str, Block]" = OrderedDict()  # NAME -> *DISTRIBUTION
        self._dist_ori: "OrderedDict[str, dict]" = OrderedDict()  # *ORIENTATION NAME -> plan
        self._dist_refs: set = set()               # every *ORIENTATION that names a distribution
        self._dist_split: Dict[int, List[Tuple[str, dict]]] = {}  # id(section) -> groups
        self._dist_tables: set = set()             # *DISTRIBUTION TABLE names they use
        self._dist_plain: Dict[tuple, str] = {}    # (axes, angle, system) -> orientation name
        self._used_names: set = set()              # names the converter may not reuse
        # Abaqus *MPC lines (see _plan_mpcs): (id(card), line) -> (mode, node pairs or reason),
        # and the rigid bodies of the BEAM lines by the card they are emitted with
        self._mpc_plan: Dict[Tuple[int, int], Tuple[str, object]] = {}
        self._mpc_bodies: Dict[int, List[dict]] = {}
        self._mpc_thermal = False                  # a step solves for temperatures
        self._mpc_mechanical = True                # ... for displacements
        self._gen_ties: set = set()                # the rotation ties the converter writes
        # explicit dynamics with circular-section beams (_plan_circ_explicit_increment): the
        # smallest min(element length, d / sqrt(2)) / wave speed and its element, and the
        # beams it could not size
        self._circ_explicit: Optional[Tuple[float, int]] = None
        self._circ_explicit_issue = ""
        # output requests (see _plan_output)
        self._out_plan: Dict[int, dict] = {}       # id(output card) -> its ccx cards
        self._out_notes: Dict[int, List[str]] = {}  # id(*OUTPUT card) -> notes it triggers
        self._out_ctl: Dict[int, Tuple[str, str]] = {}  # step -> output control (FREQUENCY= ...)
        self._out_ctl_now: Tuple[str, str] = ("FREQUENCY", "1")   # the one ccx has in force
        self._out_ctl_step = 0                     # last step whose first output card is out
        self._out_tp_cards: List[str] = []         # *TIME POINTS to emit before the first *STEP
        self._out_contact = {"abaqus": False, "pairs": 0, "nts": False, "flat": False, "axi": False}
        # *BOUNDARY on rigid-coupling members (see _plan_coupled_bcs)
        self._bc_drop: Dict[int, set] = {}         # id(*BOUNDARY) -> (node, dof) taken off it
        self._bc_lines: Dict[int, List[List[str]]] = {}   # id(*BOUNDARY) -> its records after that
        self._bc_subsets: Dict[Tuple[int, ...], str] = {}  # remaining nodes of a split line -> set
        # id(*BOUNDARY) -> reference node -> DOF -> value: rigid-body member BCs moved there
        self._bc_add: Dict[int, "OrderedDict[int, Dict[int, float]]"] = {}
        self._rb_moved: List[Tuple[int, int, int, frozenset]] = []  # (node, dof, ref, why inexact)
        # (kind, emit, node, dof, ref, why) left in place; why: '' or, on a *RIGID BODY,
        # 'differ', 'conflict', 'kind' or 'approx:<reasons>' (see _plan_rigid_body_move)
        self._coupled_clash: List[Tuple[str, str, int, int, int, str]] = []
        self._clash_dofs: set = set()              # ... their (node, dof)
        self._span: Optional[float] = None         # model size (bounding-box diagonal), lazily
        self._planar_kin: set = set()              # id(coupling card) whose members are all 2-D
        self._last_planar = False
        # load audit (see _audit_loads): steps loaded in the deck but not after conversion
        self.unloaded_steps: List[int] = []
        self.source_unloaded = False
        # distributed loads emitted as consistent nodal forces (see _flush_nodal_loads):
        # (card, target, label) -> ({(node, DOF): force}, amplitude), in Abaqus semantics
        self._nodal_loads: "OrderedDict[tuple, Tuple[Dict[Tuple[int, int], float], Optional[str]]]" = \
            OrderedDict()
        self._nodal_fresh: set = set()              # keys (re)defined in the current step
        self._nodal_reset: set = set()              # cards with OP=NEW in the current step
        self._nodal_emitted: Dict[Tuple[int, int], Tuple[str, Optional[str]]] = {}   # in ccx
        self._cload_new = False                     # the deck's *CLOAD, OP=NEW in this step
        self._section_thick: Dict[int, float] = {}  # plane element -> section thickness
        self._beam_n1: Dict[int, Optional[Vec]] = {}    # beam -> approximate n1 of its section
        self._deck_cloads: Dict[Tuple[int, int], set] = {}   # deck *CLOAD (node, DOF) -> amplitudes
        self._has_normal = False
        self._planar_beams = False                  # the deck's beams are 2-D (B21, B22, ...)
        # *DLOAD lines emitted per source card ("DLOAD" / "DSLOAD"): key -> (line, amplitude),
        # so a ccx *DLOAD, OP=NEW does not remove the other card's loads (see _flush_dloads)
        self._dl_state: Dict[str, "OrderedDict[tuple, Tuple[str, Optional[str]]]"] = {}
        self._dl_fresh: set = set()                 # (card, key) given in the current step
        self._dl_wiped = False                      # a ccx *DLOAD, OP=NEW in the current step
        # Abaqus surface elements left out of the ccx mesh (_drop_surface_elements): element ->
        # (type, nodes), and the full member list of each element set that had some
        self._carriers: "OrderedDict[int, Tuple[str, List[int]]]" = OrderedDict()
        self._carrier_sets: Dict[str, List[int]] = {}
        # connector elements (see _plan_connectors): element -> (type, node a, node b), None
        # for a grounded node.  They are constraints in ccx, never emitted as elements.
        self._conn: "OrderedDict[int, Tuple[str, Optional[int], Optional[int]]]" = OrderedDict()
        self._conn_plan: Dict[int, dict] = {}      # id(*CONNECTOR SECTION) -> its plan
        self._conn_beam: List[Tuple[int, int, int]] = []    # rigid links: (a, b, id(section))
        self._conn_knots: List[int] = []           # shell/beam nodes whose rotations they use
        self._conn_bcs: List[str] = []             # their *BOUNDARY lines (held in every step)
        self._conn_held: set = set()               # (node, DOF) held at zero in every step
        self._conn_bc_dofs: set = set()            # (node, DOF) with a BC in any step
        self._conn_turned: set = set()             # nodes with moments / prescribed rotations
        self._conn_rot: set = set()                # rotation nodes made for connector rotations
        self._nl_any = self._nl_all = False        # a step / every step runs NLGEOM (_plan_mpcs)
        self._expanded: set = set()                # nodes of elements ccx expands to 3-D
        # *BOUNDARY, TYPE=VELOCITY / ACCELERATION (see _plan_velocity_bcs): what replaces each
        # such card, what each step appends for the ones it keeps, and the amplitudes only
        # they use
        self._vel_cards: Dict[int, List[object]] = {}
        self._vel_tail: Dict[int, List[object]] = {}
        self._vel_only_amps: set = set()
        self._vel_amp_count = 0

    # -- properties ---------------------------------------------------------
    @property
    def has_rotational_dof(self) -> bool:
        if self.opt.solid_dof:
            return False
        return any(t in SHELL_TYPES or t in BEAM_TYPES for t in self._elem_types)

    # ======================================================================
    # Pass A -- build geometry
    # ======================================================================
    def build_geometry(self, blocks: List[Block]) -> None:
        for b in blocks:
            kw = b.keyword
            if kw == "NODE":
                self._register_nodes(b)
            elif kw == "ELEMENT":
                self._register_elements(b)
            elif kw == "NSET":
                self._register_set(b, "N")
            elif kw == "ELSET":
                self._register_set(b, "E")
            elif kw == "NGEN":
                created = expand_ngen(b, self.geom, self.report)
                if b.param("NSET"):
                    self.geom.add_to_nset(b.param("NSET"), created)
            elif kw == "NFILL":
                created = expand_nfill(b, self.geom, self.report)
                if b.param("NSET"):
                    self.geom.add_to_nset(b.param("NSET"), created)
            elif kw == "NCOPY":
                expand_ncopy(b, self.geom, self.report)
            elif kw == "ELGEN":
                expand_elgen(b, self.geom, self.report)
            elif kw == "ELCOPY":
                expand_elcopy(b, self.geom, self.report)
            elif kw == "NMAP":
                self.report.warn("*NMAP (coordinate mapping) is not supported; skipped.")
            elif kw == "ORIENTATION":
                self._register_orientation(b)
            elif kw == "SURFACE":
                self._register_surface(b)

    def _register_nodes(self, b: Block) -> None:
        if b.has("SYSTEM"):
            self.report.warn("*NODE with SYSTEM= (cylindrical/spherical input) treated as Cartesian; verify.", once=True)
        ids = []
        for rec in merged_data_records(b):
            f = [x for x in rec if x != ""]
            if not f:
                continue
            try:
                nid = int(float(f[0]))
                coords = [pf(x) for x in f[1:4]]
            except ValueError:              # one malformed line should not abort the file
                self.report.warn("Skipped a *NODE record with non-numeric data; verify the deck.", once=True)
                continue
            while len(coords) < 3:
                coords.append(0.0)
            if len(f) > 4:
                self.report.note("*NODE normal directions (fields 5-7) dropped — ccx averages "
                                 "shell/beam normals from the elements (use *NORMAL to impose "
                                 "them).", once=True)
            if nid in self.geom.nodes:
                self.report.warn("Duplicate node id(s) in the input; the last definition is kept "
                                 "(Abaqus behaviour) — check for an upstream renumbering error.", once=True)
            self.geom.add_node(nid, (coords[0], coords[1], coords[2]))
            ids.append(nid)
        if b.param("NSET"):
            self.geom.add_to_nset(b.param("NSET"), ids)

    def _register_elements(self, b: Block) -> None:
        typ = (b.param("TYPE") or "").upper()
        if typ in CONN_TYPES:
            self._register_connectors(b, typ)
            return
        nn = element_node_count(typ)
        toks: List[str] = []
        for line in b.data:
            toks.extend(t.strip() for t in line.split(","))
        toks = [t for t in toks if t != ""]
        if nn is None:
            recs = merged_data_records(b)
            nn = len([x for x in recs[0] if x != ""]) - 1 if recs else 0
            self.report.warn(f"Unknown element type {typ}: inferred {nn} nodes/element. "
                             f"Verify CalculiX supports it.", once=True)
        ids = []
        i = 0
        while nn > 0 and i + 1 + nn <= len(toks):
            try:
                eid = int(toks[i])
                conn = [int(x) for x in toks[i + 1:i + 1 + nn]]
            except ValueError:
                # non-numeric connectivity — e.g. an assembly-level connector/MPC element
                # using instance-qualified node names (PART-1-1.1).  ccx needs resolved
                # integer ids, so skip the element instead of crashing.
                self.report.warn(f"*ELEMENT TYPE={typ}: non-numeric connectivity "
                                 f"(instance-qualified or named node); element skipped — "
                                 f"verify it is a connector/MPC with no ccx equivalent.", once=True)
                i += 1 + nn
                continue
            if eid in self.geom.elements or eid in self._conn:
                self.report.warn("Duplicate element id(s) in the input; the last definition is kept "
                                 "(Abaqus behaviour) — check for an upstream renumbering error.", once=True)
                self._conn.pop(eid, None)
            self.geom.add_element(eid, typ, conn)
            ids.append(eid)
            i += 1 + nn
        if nn > 0 and i != len(toks):
            self.report.warn(f"*ELEMENT TYPE={typ}: {len(toks) - i} trailing token(s) "
                             f"not parsed; check connectivity.", once=True)
        self._elem_types.add(typ)
        if b.param("ELSET"):
            self.geom.add_to_elset(b.param("ELSET"), ids)

    def _register_connectors(self, b: Block, typ: str) -> None:
        """Connector elements, one per data line ``element, node a, node b``; a blank node
        is ground (Abaqus).  They stay out of the mesh — ccx has no connector element; the
        *CONNECTOR SECTION handler writes each connection as constraints."""
        ids = []
        for rec in merged_data_records(b):
            if not rec or not rec[0]:
                continue
            try:
                eid = int(rec[0])
                ends = [int(x) if x else None for x in (rec[1:3] + ["", ""])[:2]]
            except ValueError:
                self.report.warn(f"*ELEMENT TYPE={typ}: a node given by a name ccx cannot "
                                 f"resolve (instance or set name); that connector is skipped "
                                 f"— its constraint is missing.", once=True)
                continue
            if ends[0] is None and ends[1] is None:
                continue
            if eid in self._conn or eid in self.geom.elements:
                self.report.warn("Duplicate element id(s) in the input; the last definition is kept "
                                 "(Abaqus behaviour) — check for an upstream renumbering error.", once=True)
                self.geom.elements.pop(eid, None)
            self._conn[eid] = (typ, ends[0], ends[1])
            ids.append(eid)
        if b.param("ELSET"):
            self.geom.add_to_elset(b.param("ELSET"), ids)

    def _register_set(self, b: Block, kind: str) -> None:
        name = b.param("NSET") if kind == "N" else b.param("ELSET")
        if not name:
            return
        gen = b.has("GENERATE")
        ids: List[int] = []
        # Abaqus *NSET, ELSET=... (collect the nodes of an element set) has no ccx
        # equivalent -> expand it to an explicit node list here.
        if kind == "N" and b.has("ELSET"):
            src = b.param("ELSET")
            for eid in self.geom.elset(src):
                if eid in self.geom.elements:
                    ids.extend(self.geom.elements[eid][1])
            self.report.note(f"*NSET {name}, ELSET={src} expanded to the element set's nodes "
                             f"(ccx has no NSET-from-ELSET).", once=True)
        for rec in merged_data_records(b):
            f = [x for x in rec if x != ""]
            if not f:
                continue
            if gen:
                ids.extend(expand_generate(f))
            else:
                for tok in f:
                    if re.fullmatch(r"[-+]?\d+", tok):
                        ids.append(int(tok))
                    else:
                        nested = self.geom.nset(tok) if kind == "N" else self.geom.elset(tok)
                        if nested:
                            ids.extend(nested)
                        else:
                            self.report.warn(f"Set {name}: member set '{tok}' undefined when used; "
                                             f"verify ordering.", once=True)
        if kind == "N":
            self.geom.add_to_nset(name, ids)
            if b.has("UNSORTED"):
                self.geom.unsorted.add(name.upper())
        else:
            self.geom.add_to_elset(name, ids)

    def _register_orientation(self, b: Block) -> None:
        name = (b.param("NAME") or "").upper()
        system = (b.param("SYSTEM") or "RECTANGULAR").upper()
        a, bvec = (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)
        pts = self._orientation_points(b)     # a distribution-based *ORIENTATION has a
        if pts is not None:                   # name on its data line, not coordinates
            a, bvec = (pts[0], pts[1], pts[2]), (pts[3], pts[4], pts[5])
        self.orientations[name] = (a, bvec, system)
        # optional additional-rotation line: local axis, angle (degrees)
        recs = merged_data_records(b)
        rot = None
        if len(recs) > 1:
            f = [x for x in recs[1] if x != ""]
            try:
                if len(f) >= 2:
                    rot = (pint(f[0]), pf(f[1]))
            except ValueError:
                rot = None
        self._orient_rotation[name] = rot

    def _register_surface(self, b: Block) -> None:
        name = (b.param("NAME") or "").upper()
        typ = (b.param("TYPE") or "ELEMENT").upper()
        entries: List[Tuple[str, Optional[str]]] = []
        for rec in merged_data_records(b):
            f = [x for x in rec if x != ""]
            if not f:
                continue
            face = f[1].upper() if len(f) > 1 else None
            entries.append((f[0], face))
        self.surfaces[name] = (typ, entries)

    # ======================================================================
    # Pass B -- emit
    # ======================================================================
    def emit_geometry(self) -> List[str]:
        out: List[str] = []
        out.append("*NODE")
        for nid, (x, y, z) in self.geom.nodes.items():
            out.append(f"{nid}, {fmt_coord(x)}, {fmt_coord(y)}, {fmt_coord(z)}")

        by_type: "OrderedDict[str, List[Tuple[int, List[int]]]]" = OrderedDict()
        for eid, (typ, conn) in self.geom.elements.items():
            by_type.setdefault(typ, []).append((eid, conn))
        for typ, items in by_type.items():
            out_typ = ccx_element_type(typ, self.report)
            out.append(f"*ELEMENT, TYPE={out_typ}")
            for eid, conn in items:
                out.extend(reflow([str(eid)] + [str(c) for c in conn], MAX_ENTRIES_PER_LINE))

        for name, ids in self.geom.nsets.items():
            self._emit_set(out, "NSET", name, ids)
        for name, ids in self.geom.elsets.items():
            self._emit_set(out, "ELSET", name, ids)
        return out

    def _emit_set(self, out: List[str], kw: str, name: str, ids: Sequence[int]) -> None:
        pool = self.geom.nodes if kw == "NSET" else self.geom.elements
        raw = dedup(ids)
        if kw == "ELSET" and self._conn:
            raw = [i for i in raw if i not in self._conn]      # constraints, not elements
        ids = [i for i in raw if i in pool]
        dropped = len(raw) - len(ids)
        if dropped:
            self.report.warn(f"*{kw} {name}: {dropped} member(s) reference undefined "
                             f"{'nodes' if kw == 'NSET' else 'elements'} and were removed "
                             f"(Abaqus tolerates gappy GENERATE ranges; ccx may not). If the count "
                             f"is unexpected, check for a renumbering error upstream.", once=True)
        if not ids:
            return
        lines = compress_ids(ids)
        if lines and lines[0] == "GENERATE":
            out.append(f"*{kw}, {kw}={name}, GENERATE")
            out.extend(lines[1:])
        else:
            out.append(f"*{kw}, {kw}={name}")
            out.extend(lines)

    def emit_other(self, blocks: List[Block]) -> List[str]:
        out: List[str] = []
        i, n = 0, len(blocks)
        while i < n:
            b = blocks[i]
            if b.keyword == "HEADING" or b.keyword in GEOM_KW:
                i += 1
                continue
            if b.keyword == "STEP":
                if self._temp_ic_default and self._step_idx == 0:
                    out.extend(self._default_temperature_ic())
                out.extend(self._out_tp_cards)          # ccx: *TIME POINTS before any *STEP
                self._out_tp_cards = []
                group = []
                j = i
                while j < n:
                    group.append(blocks[j])
                    if blocks[j].keyword == "END STEP":
                        break
                    j += 1
                out.extend(self.handle_step(group))
                i = j + 1
                continue
            if b.keyword == "END STEP":
                i += 1
                continue
            if b.keyword in HISTORY_ONLY_KW:
                where = "before the first *STEP" if self._step_idx == 0 else "between steps"
                out.extend(self._commented(
                    b, f"*{b.keyword} is step (history) data but appears {where}: Abaqus rejects "
                       f"that, ccx stops with '*{b.keyword} should only be used within a STEP', "
                       f"and ccx 2.23 segfaults when the deck has no *STEP at all. Commented out "
                       f"— move it into a step if it was meant to apply."))
                i += 1
                continue
            out.extend(self.translate_one(b))
            i += 1
        return out

    # -- dispatch -----------------------------------------------------------
    def translate_one(self, b: Block) -> List[str]:
        kw = b.keyword
        handlers = {
            "ELASTIC": self.handle_elastic,
            "ORIENTATION": self.handle_orientation,
            "DISTRIBUTION": self.handle_distribution,
            "DISTRIBUTION TABLE": self.handle_distribution_table,
            "SOLID SECTION": self.handle_solid_section,
            "SHELL SECTION": self.handle_shell_section,
            "SHELL GENERAL SECTION": self.handle_shell_section,
            "MEMBRANE SECTION": self.handle_membrane_section,
            "BEAM SECTION": self.handle_beam_section,
            "COHESIVE SECTION": self.handle_cohesive_section,
            "GASKET SECTION": self.handle_cohesive_section,
            "SURFACE SECTION": self.handle_surface_section,
            "TRANSFORM": self.handle_transform,
            "TIE": self.handle_tie,
            "BOUNDARY": self.handle_boundary,
            "CLOAD": self.handle_cload,
            "DLOAD": self.handle_dload,
            "DSLOAD": self.handle_dsload,
            "MPC": self.handle_mpc,
            "CONNECTOR SECTION": self.handle_connector_section,
            "RESTART": self.handle_restart,
            "AMPLITUDE": self.handle_amplitude,
            "SURFACE": self.handle_surface,
            "CREEP": self.handle_creep,
            "FRICTION": self.handle_friction,
            "CONTACT PAIR": self.handle_contact_pair,
            "RIGID BODY": self.handle_rigid_body,
            "COUPLING": self.handle_coupling_card,
            "KINEMATIC": self.handle_kinematic,
            "SURFACE INTERACTION": self.handle_surface_interaction,
            "INITIAL CONDITIONS": self.handle_initial_conditions,
            "TEMPERATURE": self.handle_temperature,
            "FILM": self.handle_flux_film,
            "DFLUX": self.handle_flux_film,
            "CFLUX": self.handle_flux_film,
            "RADIATE": self.handle_flux_film,
            "NORMAL": self.handle_normal,
            "EQUATION": self.handle_equation,
            "STATIC": self.handle_static,
            "DYNAMIC": self.handle_dynamic,
            "FREQUENCY": self.handle_frequency,
            "BUCKLE": self.handle_buckle,
            "HEAT TRANSFER": self.handle_heat_transfer,
            "PLASTIC": self.handle_plastic,
            "DEPVAR": self.handle_depvar,
            "CYCLIC HARDENING": self.handle_cyclic_hardening,
            "HYPERELASTIC": self.handle_hyperelastic,
            "DENSITY": self.handle_dependent_material,
            "SPECIFIC HEAT": self.handle_dependent_material,
            "CONDUCTIVITY": self.handle_dependent_material,
            "EXPANSION": self.handle_expansion,
            "MOHR COULOMB": self.handle_dependent_material,
            "MOHR COULOMB HARDENING": self.handle_dependent_material,
        }
        if kw in handlers:
            return handlers[kw](b)
        if kw in ("NODE FILE", "EL FILE", "NODE PRINT", "EL PRINT", "NODE OUTPUT", "ELEMENT OUTPUT",
                  "CONTACT OUTPUT", "CONTACT FILE"):
            return self.handle_output(b)
        if kw == "OUTPUT":
            for msg in self._out_notes.get(id(b), []):
                self.report.note(msg, once=True)
            self.report.note("*OUTPUT cards dropped (ccx's own *OUTPUT takes only FREQUENCY): a "
                             "FIELD request goes to the .frd (*NODE FILE / *EL FILE), a HISTORY "
                             "request for a set to the .dat (*NODE PRINT / *EL PRINT), and its "
                             "FREQUENCY / NUMBER INTERVAL / TIME INTERVAL / TIME POINTS onto the "
                             "step's first output card.", once=True)
            return self._anchored_output(b)        # a preselected request's cards
        if kw == "KINEMATIC COUPLING":
            return self.handle_coupling(b)
        if kw == "PARAMETER":
            self.report.note("*PARAMETER card dropped; its <name> substitutions were already "
                             "applied to the deck (ccx has no parametric input).", once=True)
            return []
        if kw == "SYSTEM" and not any(x.strip() for x in b.data):
            # a bare *System resets to the global frame — a no-op, not worth a warning
            self.report.note("Bare *SYSTEM (reset to global coordinates) dropped — no effect.", once=True)
            return []
        if kw in DROP_KEYWORDS:
            self.report.note(f"*{kw} dropped (Abaqus-only organisational card; no ccx meaning).", once=True)
            return []
        if kw in DROP_WARN_KEYWORDS:
            self.report.warn(DROP_WARN_KEYWORDS[kw], once=True)
            return []
        return self.passthrough(b)

    def passthrough(self, b: Block) -> List[str]:
        """Emit a keyword unchanged when ccx supports it; otherwise comment it out
        with guidance.  This is the table-driven heart of 'support as many as
        possible, convert/flag the rest'."""
        kw = b.keyword
        if kw == "FILTER" and not self._has_sensitivity:
            # Abaqus *FILTER is an output filter (anti-aliasing / HALT on a limit); ccx's
            # *FILTER smooths sensitivities and is an error outside a *SENSITIVITY run
            return self._commented(b, "*FILTER: the Abaqus output filter (anti-aliasing / halt "
                                      "on limit) has no ccx equivalent, and ccx's *FILTER — a "
                                      "sensitivity-smoothing card — is an error outside a "
                                      "*SENSITIVITY step. Commented out.")
        if kw in SEMANTIC_TRAP:
            self.report.warn(SEMANTIC_TRAP[kw], once=True)
        elif kw in PASS_WITH_NOTE:
            self.report.note(PASS_WITH_NOTE[kw], once=True)
        elif kw not in CCX_KEYWORDS:
            guidance = SPECIAL_UNSUPPORTED.get(kw)
            msg = (f"*{kw}: {guidance}" if guidance
                   else f"*{kw} has no direct CalculiX equivalent; emitted as a comment for review.")
            return self._commented(b, msg)
        params = b.params
        if b.has("DEPENDENCIES"):
            params = OrderedDict((k, v) for k, v in b.params.items() if k != "DEPENDENCIES")
            self.report.warn(f"*{kw}, DEPENDENCIES=...: ccx has no field-variable dependence and "
                             f"in effect uses only the first data row; parameter dropped — "
                             f"verify the property.", once=True)
        return [emit_keyword(kw, params)] + list(b.data)

    def _commented(self, b: Block, msg: str) -> List[str]:
        self.report.n_commented += 1
        self.report.warn(msg, once=True)
        out = ["** abq2ccx: " + msg, "** " + emit_keyword(b.keyword, b.params)]
        out += ["** " + d for d in b.data]
        return out

    # -- model-data handlers ------------------------------------------------
    def _collapse_dependencies(self, b: Block, nvals: int) -> Optional[List[str]]:
        """Data lines of a ``DEPENDENCIES=n`` material card reduced to a single field-
        variable state, or None if the card has no dependencies / cannot be parsed.

        ccx has no field variables: it ignores DEPENDENCIES and reads the field columns as
        further temperature rows, so effectively only the first row counts.  Abaqus with no
        field defined uses field = 0, so that state is kept — interpolated between rows
        (one field variable, one row per state) or else the rows of the state nearest 0.
        Each row is ``nvals`` property values, the temperature, then the n field values,
        8 entries per physical line."""
        try:
            ndep = int(float(b.param("DEPENDENCIES") or "0"))
        except ValueError:
            return None
        if ndep <= 0:
            return None
        width = nvals + 1 + ndep
        recs = material_rows(b, nvals)
        if not recs:
            return None

        def num(x: str) -> float:
            return pf(x) if x.strip() else 0.0
        try:
            rows = [(r[:nvals], r[nvals], tuple(num(x) for x in r[nvals + 1:width])) for r in recs]
            temps = [num(t) for _, t, _ in rows]
        except ValueError:
            return None
        states: List[Tuple[float, ...]] = []
        for _, _, fl in rows:
            if fl not in states:
                states.append(fl)
        out_rows: List[Tuple[List[str], str]] = []
        per_state_unique = len({(t, fl) for t, (_, _, fl) in zip(temps, rows)}) == len(rows)
        if ndep == 1 and per_state_unique and len(states) > 1:
            by_t: "OrderedDict[float, List[Tuple[float, List[str], str]]]" = OrderedDict()
            for t, (vals, traw, fl) in zip(temps, rows):
                by_t.setdefault(t, []).append((fl[0], vals, traw))
            for t, grp in by_t.items():
                grp.sort(key=lambda g: g[0])
                if any(g[0] == 0.0 for g in grp):
                    g = next(g for g in grp if g[0] == 0.0)
                    out_rows.append((g[1], g[2]))
                elif 0.0 < grp[0][0]:
                    out_rows.append((grp[0][1], grp[0][2]))
                elif 0.0 > grp[-1][0]:
                    out_rows.append((grp[-1][1], grp[-1][2]))
                else:
                    lo = max((g for g in grp if g[0] < 0.0), key=lambda g: g[0])
                    hi = min((g for g in grp if g[0] > 0.0), key=lambda g: g[0])
                    w = -lo[0] / (hi[0] - lo[0])
                    try:
                        vals = [f"{num(a) + w * (num(c) - num(a)):.6g}" if (a or c) else ""
                                for a, c in zip(lo[1], hi[1])]
                    except ValueError:
                        return None
                    out_rows.append((vals, lo[2]))
            desc = "field variable 1 = 0 (the Abaqus value when no field is defined; interpolated)"
        else:
            keep = min(states, key=lambda s: (sum(abs(x) for x in s), states.index(s)))
            out_rows = [(vals, traw) for vals, traw, fl in rows if fl == keep]
            desc = (f"the rows for field variable(s) = {', '.join(f'{x:g}' for x in keep)} (the "
                    f"state nearest the Abaqus no-field value 0)")
        self.report.warn(f"*{b.keyword}, DEPENDENCIES={ndep}: ccx has no field-variable dependence "
                         f"(it ignores the parameter and in effect uses only the first row). "
                         f"Collapsed to {desc}"
                         + ("; this deck sets field variables (*FIELD / USDFLD / TYPE=FIELD), which "
                            "ccx cannot replicate" if self._fields_set else "")
                         + ". Verify.", once=True)
        data: List[str] = []
        for vals, traw in out_rows:
            entries = list(vals) + [traw]
            while len(entries) > 1 and entries[-1] == "":
                entries.pop()
            for k in range(0, len(entries), 8):
                data.append(", ".join(entries[k:k + 8]))
        return data

    def handle_dependent_material(self, b: Block) -> List[str]:
        """Material cards whose only conversion need is DEPENDENCIES= collapsing (*DENSITY,
        *SPECIFIC HEAT, *CONDUCTIVITY, *EXPANSION, *MOHR COULOMB[ HARDENING]), and the shear
        coefficients of an anisotropic *EXPANSION (_tensor_expansion_shear)."""
        typ = (b.param("TYPE") or "ISO").upper()
        n = {"ORTHO": 3, "ORTHOTROPIC": 3, "ANISO": 6, "ANISOTROPIC": 6}.get(typ, 1)
        nvals = {"MOHR COULOMB": 2, "MOHR COULOMB HARDENING": 2}.get(b.keyword, n)
        # with USER the data lines are VUEXPAN's user properties, not coefficients
        aniso = b.keyword == "EXPANSION" and n == 6 and not b.has("USER")
        if b.has("DEPENDENCIES"):
            data = self._collapse_dependencies(b, nvals)
            params: "OrderedDict[str, Optional[str]]" = OrderedDict(
                (k, v) for k, v in b.params.items() if k != "DEPENDENCIES")
            if data is None:
                self.report.warn(f"*{b.keyword}, DEPENDENCIES=...: rows could not be parsed; "
                                 f"passed through — ccx ignores field-variable dependence and in "
                                 f"effect uses only the first row. Verify."
                                 + (" Its shear coefficients alpha12, alpha13, alpha23 are NOT "
                                    "halved to the tensor components ccx reads." if aniso else ""),
                                 once=True)
                return [emit_keyword(b.keyword, params)] + list(b.data)
            out = [emit_keyword(b.keyword, params)] + data
        else:
            out = self.passthrough(b)
        return self._tensor_expansion_shear(b, out) if aniso else out

    def _tensor_expansion_shear(self, b: Block, out: List[str]) -> List[str]:
        """The emitted *EXPANSION, TYPE=ANISO card ``out`` (one row per data line: alpha11,
        alpha22, alpha33, alpha12, alpha13, alpha23, temperature) with its shear coefficients
        halved.  Abaqus gives alpha12, alpha13, alpha23 as engineering coefficients (the shear
        thermal strain gamma_ij = 2 eps_ij = alpha_ij dT): its material data use the
        engineering shear strains of its strain vector (Conventions: (eps11, eps22, eps33,
        gamma12, gamma13, gamma23)), as do the thermal strain increments UEXPAN returns for
        TYPE=ANISO, and its PZT-5H verification enters the strain coefficient d15 in the
        d_113 slot unhalved.  ccx 2.23 reads them as tensor components: a free cube strains
        eps_ij = alpha_ij dT (probed for 12, 13 and 23), a clamped one has sigma12 =
        -2 mu alpha12 dT.  Temperatures, blank fields and a distribution name stay as they are."""
        lines = list(out)
        halved = False
        for i in range(1, len(lines)):
            if lines[i].lstrip().startswith("*"):
                continue
            f = [x.strip() for x in lines[i].split(",")]
            try:
                shear = [pf(x) if x else 0.0 for x in f[3:6]]
            except ValueError:
                continue                            # a distribution name, not coefficients
            if not any(shear):
                continue
            for k, v in enumerate(shear, 3):
                if v != 0.0:
                    # 12 significant digits: ccx reads only the first 20 characters of a field
                    f[k] = "%.12g" % (0.5 * v)
            lines[i] = ", ".join(f).rstrip()
            halved = True
        if halved:
            mat = self._expansion_material.get(id(b), "?")
            self.report.note(f"Material {mat}: the shear coefficients alpha12, alpha13, alpha23 of "
                             f"its *EXPANSION, TYPE=ANISO halved — Abaqus gives them as engineering "
                             f"shear strain per degree (gamma12 = alpha12 dT, the shear measure of "
                             f"its strains), ccx 2.23 reads tensor components (eps12 = alpha12 dT).",
                             once=True)
        return lines

    def handle_plastic(self, b: Block) -> List[str]:
        """``*PLASTIC``: ccx implements ISOTROPIC / KINEMATIC / COMBINED tabular hardening
        and Johnson-Cook; any other card is silently skipped (verified: HARDENING=USER runs
        purely elastic without a word).  Johnson-Cook gets the *RATE DEPENDENT card ccx
        needs to switch it on; user / parametric (Chaboche) forms are commented out."""
        hard = (b.param("HARDENING") or "ISOTROPIC").strip().upper()
        hard_n = hard.replace(" ", "").replace("-", "")
        if hard_n == "USER":
            return self._commented(b, "*PLASTIC, HARDENING=USER needs an Abaqus UHARD/VUHARD "
                                      "subroutine, which ccx does not have — ccx would silently "
                                      "skip the card. Commented out: the material now runs purely "
                                      "elastic; supply a tabulated *PLASTIC curve instead.")
        if hard_n == "JOHNSONCOOK":
            # ccx has Johnson-Cook natively (A, B, n, m, T_melt, T_transition, as in Abaqus),
            # but activates it only together with *RATE DEPENDENT, TYPE=JOHNSON COOK — alone,
            # the card silently leaves the material elastic (verified on 2.23).  Abaqus
            # without *RATE DEPENDENT is rate-independent, i.e. C = 0.
            vals = [x.strip() for x in (b.data[0].split(",") if b.data else [])]
            while vals and vals[-1] == "":
                vals.pop()
            try:
                nums = [pf(x) if x else 0.0 for x in vals]
            except ValueError:
                nums = []
            if len(nums) < 3:
                return self._commented(b, "*PLASTIC, HARDENING=JOHNSON COOK: data line could not "
                                          "be parsed (need A, B, n, m); commented out — the "
                                          "material now runs elastic.")
            if len(nums) < 4 or nums[3] <= 0.0:
                vals = (vals + [""] * 4)[:max(4, len(vals))]
                vals[3] = "1."
                self.report.note("*PLASTIC, HARDENING=JOHNSON COOK: thermal-softening exponent m "
                                 "missing or zero -> 1 (ccx requires m > 0; it only acts above the "
                                 "transition temperature).", once=True)
            out = [emit_keyword("PLASTIC", OrderedDict([("HARDENING", "JOHNSON COOK")])),
                   ", ".join(vals)]
            if id(b) not in self._jc_with_rate:
                out += ["*RATE DEPENDENT, TYPE=JOHNSON COOK", "0., 1."]
                self.report.note("*PLASTIC, HARDENING=JOHNSON COOK: ccx activates its Johnson-Cook "
                                 "law only with a *RATE DEPENDENT card, so a rate-independent one "
                                 "(C = 0) was added — as in Abaqus without *RATE DEPENDENT.",
                                 once=True)
            return out
        if (b.param("DATATYPE") or "").strip().upper().startswith("PARAM"):
            return self._commented(b, "*PLASTIC, DATATYPE=PARAMETERS (Chaboche back-stress "
                                      "parameters) has no ccx equivalent — ccx would read them as "
                                      "one stress/strain point. Commented out: the material now "
                                      "runs elastic; tabulate the hardening curve instead.")
        if hard_n not in ("ISOTROPIC", "KINEMATIC", "COMBINED"):
            return self._commented(b, f"*PLASTIC, HARDENING={hard} is not a ccx hardening law "
                                      f"(ISOTROPIC, KINEMATIC, COMBINED) — ccx would silently skip "
                                      f"the card. Commented out: the material now runs elastic.")
        if hard_n == "COMBINED":
            self.report.warn("*PLASTIC, HARDENING=COMBINED: Abaqus fits a nonlinear-kinematic "
                             "(Chaboche) model to these data, while ccx reads the table as its own "
                             "combined law (isotropic part from *CYCLIC HARDENING) — verify the "
                             "response under load reversal.", once=True)
        params: "OrderedDict[str, Optional[str]]" = OrderedDict()
        for k, v in b.params.items():
            if k == "HARDENING":
                params[k] = hard
            elif k == "DEPENDENCIES":
                continue
            else:
                self.report.note(f"*PLASTIC parameter {k} dropped (not a ccx parameter).", once=True)
        data = self._collapse_dependencies(b, 2) if b.has("DEPENDENCIES") else None
        return [emit_keyword("PLASTIC", params)] + (data if data is not None else list(b.data))

    def handle_cyclic_hardening(self, b: Block) -> List[str]:
        """``*CYCLIC HARDENING``: ccx reads it only after a *PLASTIC, HARDENING=COMBINED of
        the same material (an error otherwise), and only in tabular form — Abaqus'
        PARAMETERS form (Q_inf, b) would be misread."""
        if b.has("PARAMETERS"):
            return self._commented(b, "*CYCLIC HARDENING, PARAMETERS (Voce Q_inf, b) has no ccx "
                                      "equivalent — ccx takes a tabulated isotropic curve; "
                                      "commented out.")
        if id(b) not in self._cyclic_ok:
            return self._commented(b, "*CYCLIC HARDENING without a (kept) *PLASTIC, "
                                      "HARDENING=COMBINED in its material is an error in ccx; "
                                      "commented out.")
        return self.passthrough(b)

    def handle_depvar(self, b: Block) -> List[str]:
        """``*DEPVAR``: ccx reads only the SDV count.  Abaqus' DELETE= (element deletion
        when that SDV reaches 0) and the per-SDV label lines have no ccx meaning."""
        if b.has("DELETE"):
            self.report.warn(f"*DEPVAR, DELETE={b.param('DELETE')}: element deletion is unsupported "
                             f"by ccx — failed elements are never removed from the model.", once=True)
        recs = [[x for x in r if x != ""] for r in merged_data_records(b)]
        recs = [r for r in recs if r]
        if len(recs) > 1:
            self.report.note("*DEPVAR output-label lines dropped (ccx reads only the number of "
                             "state variables).", once=True)
        return [emit_keyword("DEPVAR", OrderedDict())] + ([recs[0][0] + ","] if recs else [])

    def handle_hyperelastic(self, b: Block) -> List[str]:
        """``*HYPERELASTIC`` without a model keyword means POLYNOMIAL in Abaqus; ccx needs it
        spelled out (a bare card segfaults ccx 2.22 — verified).  TEST DATA INPUT (Abaqus
        fits the coefficients from separate test-data cards) has no ccx equivalent."""
        models = {"ARRUDA-BOYCE", "MOONEY-RIVLIN", "NEO HOOKE", "OGDEN", "POLYNOMIAL",
                  "REDUCED POLYNOMIAL", "YEOH", "VAN DER WAALS", "MARLOW", "USER"}
        if b.has("TEST DATA INPUT"):
            return self._commented(b, "*HYPERELASTIC, TEST DATA INPUT: Abaqus fits the "
                                      "coefficients from *UNIAXIAL/*BIAXIAL/... TEST DATA; ccx needs "
                                      "the coefficients themselves — fit them and re-add the card.")
        params: "OrderedDict[str, Optional[str]]" = OrderedDict(b.params)
        if not any(k in models for k in params):
            params = OrderedDict([("POLYNOMIAL", None)] + list(params.items()))
            self.report.note("*HYPERELASTIC without a model keyword -> POLYNOMIAL (the Abaqus "
                             "default; ccx requires it explicitly).", once=True)
        return [emit_keyword("HYPERELASTIC", params)] + list(b.data)

    def handle_elastic(self, b: Block) -> List[str]:
        typ = (b.param("TYPE") or "ISO").upper()
        if typ == "LAMINA":
            converted = self._lamina_to_engineering_constants(b)
            if converted is not None:
                return self._fit_elastic_to_expansion(b, "ENGINEERING CONSTANTS", converted)
            self.report.warn("*ELASTIC TYPE=LAMINA could not be parsed; emitted unchanged — ccx "
                             "will reject TYPE=LAMINA.", once=True)
        tmap = {"ISOTROPIC": "ISO", "ISO": "ISO", "ORTHOTROPIC": "ORTHO", "ORTHO": "ORTHO",
                "ENGINEERING CONSTANTS": "ENGINEERING CONSTANTS",
                "ANISOTROPIC": "ANISO", "ANISO": "ANISO"}
        cc = tmap.get(typ, typ)
        params: "OrderedDict[str, Optional[str]]" = OrderedDict()
        for k, v in b.params.items():
            if k == "TYPE":
                if cc != "ISO":
                    params["TYPE"] = cc
            elif k == "DEPENDENCIES":
                continue
            else:
                params[k] = v
        if typ in ("ORTHOTROPIC", "ANISOTROPIC"):
            self.report.note(f"*ELASTIC TYPE={typ} -> {cc} (constant order is identical; "
                             f"data lines passed through).", once=True)
        data = list(b.data)
        if b.has("DEPENDENCIES"):
            nvals = {"ISO": 2, "ORTHO": 9, "ENGINEERING CONSTANTS": 9, "ANISO": 21}.get(cc)
            collapsed = self._collapse_dependencies(b, nvals) if nvals else None
            if collapsed is None:
                self.report.warn("*ELASTIC, DEPENDENCIES=...: rows could not be parsed; passed "
                                 "through — ccx ignores field-variable dependence and in effect "
                                 "uses only the first row. Verify.", once=True)
            else:
                data = collapsed
        if self._approx and cc == "ISO":
            newdata, clamped = [], False
            for rec in ([p.strip() for p in ln.split(",")] for ln in data):
                f = [x for x in rec if x != ""]
                if len(f) >= 2:
                    try:
                        if pf(f[1]) >= 0.5:
                            f[1] = "0.475"
                            clamped = True
                    except ValueError:
                        pass
                if f:
                    newdata.append(", ".join(f))
            if clamped:
                self.report.warn("[APPROX] *ELASTIC Poisson ratio >= 0.5 clamped to 0.475 (ccx "
                                 "rejects incompressible nu; slight compressibility introduced — "
                                 "use *HYPERELASTIC for true incompressibility). Verify.", once=True)
                data = newdata
        return self._fit_elastic_to_expansion(b, cc, [emit_keyword("ELASTIC", params)] + data)

    def _lamina_to_engineering_constants(self, b: Block) -> Optional[List[str]]:
        """``*ELASTIC, TYPE=LAMINA`` (E1,E2,nu12,G12,G13,G23[,T]) has no ccx equivalent;
        expand to ENGINEERING CONSTANTS assuming transverse isotropy: E3=E2, nu13=nu12,
        nu23 from G23=E2/(2(1+nu23)).  Returns None if the data cannot be parsed."""
        rows: List[str] = []
        for rec in merged_data_records(b):
            f = [x for x in rec if x != ""]
            if not f:
                continue
            try:
                v = [pf(x) for x in f]
            except ValueError:
                return None
            if len(v) < 6:
                return None
            E1, E2, nu12, G12, G13, G23 = v[:6]
            nu23 = max(0.0, min(0.495, E2 / (2.0 * G23) - 1.0)) if G23 > 0 else nu12
            rows.append(f"{E1:.6g}, {E2:.6g}, {E2:.6g}, {nu12:.6g}, {nu12:.6g}, "
                        f"{nu23:.6g}, {G12:.6g}, {G13:.6g}")
            rows.append(f"{G23:.6g}" + (f", {v[6]:.6g}" if len(v) > 6 else ""))
        if not rows:
            return None
        params: "OrderedDict[str, Optional[str]]" = OrderedDict(b.params)
        params["TYPE"] = "ENGINEERING CONSTANTS"
        self.report.warn("*ELASTIC TYPE=LAMINA -> ENGINEERING CONSTANTS with assumed transverse "
                         "isotropy (E3=E2, nu13=nu12, nu23 derived from G23). ccx expands shells "
                         "to solids, so these through-thickness constants DO enter the stiffness — "
                         "verify.", once=True)
        return [emit_keyword("ELASTIC", params)] + rows

    @staticmethod
    def _material_groups(blocks: List[Block]) -> List[List[Block]]:
        """Each *MATERIAL with its cards, which run from the *MATERIAL to the next card that
        cannot belong to it."""
        ends = {"MATERIAL", "STEP", "NODE", "ELEMENT", "SURFACE INTERACTION", "CONNECTOR BEHAVIOR",
                "GASKET BEHAVIOR"}
        groups: List[List[Block]] = []
        group: List[Block] = []
        for b in blocks:
            if b.keyword in ends or b.keyword.endswith("SECTION"):
                if group:
                    groups.append(group)
                group = [b] if b.keyword == "MATERIAL" else []
            elif group:
                group.append(b)
        if group:
            groups.append(group)
        return groups

    def _expansion_card(self, group: List[Block]) -> Tuple[Optional[str], Optional[Block]]:
        """``("ORTHO" | "ANISO", card)`` when a material's (last) *EXPANSION is orthotropic or
        anisotropic as it is written for ccx (_plan_expansion_as_ortho), else ``(None, None)``."""
        exp = [g for g in group if g.keyword == "EXPANSION"]
        typ = (exp[-1].param("TYPE") or "ISO").strip().upper() if exp else "ISO"
        kind = {"ORTHO": "ORTHO", "ORTHOTROPIC": "ORTHO", "ANISO": "ANISO",
                "ANISOTROPIC": "ANISO"}.get(typ)
        if kind == "ANISO" and id(exp[-1]) in self._expansion_as_ortho:
            kind = "ORTHO"
        return (kind, exp[-1]) if kind else (None, None)

    def _plan_expansion_as_ortho(self, blocks: List[Block]) -> None:
        """The *EXPANSION, TYPE=ANISO cards that handle_expansion writes as TYPE=ORTHO: those
        whose shear coefficients alpha12, alpha13, alpha23 are zero in every row, unless a
        section or composite ply that uses the material turns its axes so that the expansion
        has shear in global axes.  Both types give the same thermal strain in linear steps,
        but in NLGEOM steps of a deck with temperatures ccx 2.23 stops on any TYPE=ANISO
        expansion with 'too many cutbacks', while it computes TYPE=ORTHO exactly in such axes
        (probed: a free heated cube; see _check_nlgeom_expansion).  In turned axes it would
        drop the turned shear of TYPE=ORTHO there without an error, so such a card stays
        ANISO and those steps fail loudly.  With USER the data lines hold no coefficients."""
        self._expansion_as_ortho = {}
        uses: Optional[List[Tuple[str, Optional[Tuple[Vec, Vec, Vec]]]]] = None
        for group in self._material_groups(blocks):
            name = (group[0].param("NAME") or "").strip()
            for exp in group:
                if exp.keyword != "EXPANSION" or exp.has("USER") or \
                        (exp.param("TYPE") or "").strip().upper() not in ("ANISO", "ANISOTROPIC"):
                    continue
                rows = material_rows(exp, 6)
                try:
                    if not rows or any(pf(x) for r in rows for x in r[3:6] if x) or \
                            not all(math.isfinite(pf(x)) for r in rows for x in r if x):
                        continue
                except ValueError:                  # a distribution name, a parameter, ...
                    continue
                if uses is None:
                    uses = self._material_uses(blocks)
                if not any(mat == name.upper() and self._expansion_shear(exp, axes)
                           for mat, axes in uses):
                    self._expansion_as_ortho[id(exp)] = name

    def handle_expansion(self, b: Block) -> List[str]:
        """``*EXPANSION``: DEPENDENCIES= collapsed and the shear coefficients of an anisotropic
        one halved (handle_dependent_material), and an anisotropic one without shear
        coefficients written as TYPE=ORTHO (alpha11, alpha22, alpha33[, temperature]) where
        _plan_expansion_as_ortho chose it."""
        out = self.handle_dependent_material(b)
        mat = self._expansion_as_ortho.get(id(b))
        if mat is None:
            return out
        params: "OrderedDict[str, Optional[str]]" = OrderedDict(
            (k, "ORTHO" if k == "TYPE" else v) for k, v in b.params.items() if k != "DEPENDENCIES")
        lines = [emit_keyword(b.keyword, params)]
        for ln in out[1:]:                          # one row per line, also once collapsed
            f = [x.strip() for x in ln.split(",")]
            f = f[:3] + f[6:]
            while len(f) > 1 and f[-1] == "":
                f.pop()
            lines.append(", ".join(f))
        self.report.note(f"Material {mat}: *EXPANSION, TYPE=ANISO without shear coefficients "
                         f"written as TYPE=ORTHO, the same thermal strain: in NLGEOM steps of a "
                         f"deck with temperatures ccx 2.23 stops on any TYPE=ANISO expansion with "
                         f"'too many cutbacks', but computes TYPE=ORTHO right where no "
                         f"*ORIENTATION or ply angle turns the material axes so that it has shear "
                         f"in global axes, as here.", once=True)
        return lines

    def _plan_elastic_expansion(self, blocks: List[Block]) -> None:
        """The *ELASTIC cards whose material has an orthotropic or anisotropic *EXPANSION,
        which handle_elastic may have to rewrite (ELASTIC_FOR_EXPANSION).  Materials on
        ccx's nonlinear material path (INELASTIC_MATERIAL_CARDS, or a *PLASTIC card that
        handle_plastic keeps) are left out."""
        self._elastic_expansion = {}
        for group in self._material_groups(blocks):
            kind = self._expansion_card(group)[0]
            if kind is None or any(g.keyword in INELASTIC_MATERIAL_CARDS or
                                   (g.keyword == "PLASTIC" and self._plastic_kept(g)) for g in group):
                continue
            for g in group:
                if g.keyword == "ELASTIC":
                    self._elastic_expansion[id(g)] = (kind, group[0].param("NAME") or "?")

    @staticmethod
    def _plastic_kept(b: Block) -> bool:
        """Whether handle_plastic emits this *PLASTIC card rather than commenting it out
        (user, parametric or unknown hardening, unreadable Johnson-Cook data)."""
        hard = (b.param("HARDENING") or "ISOTROPIC").strip().upper().replace(" ", "").replace("-", "")
        if hard == "JOHNSONCOOK":
            vals = [x.strip() for x in (b.data[0].split(",") if b.data else [])]
            while vals and vals[-1] == "":
                vals.pop()
            try:
                return len([pf(x) if x else 0.0 for x in vals]) >= 3
            except ValueError:
                return False
        return hard in ("ISOTROPIC", "KINEMATIC", "COMBINED") and \
            not (b.param("DATATYPE") or "").strip().upper().startswith("PARAM")

    def _fit_elastic_to_expansion(self, b: Block, cc: str, out: List[str]) -> List[str]:
        """The emitted *ELASTIC card ``out`` (ccx type ``cc``) in the form ccx 2.23 needs beside
        its material's orthotropic or anisotropic *EXPANSION (ELASTIC_FOR_EXPANSION), with the
        same stiffness; ``out`` itself when no change is needed.  ccx interpolates the
        converted stiffness linearly in temperature where Abaqus interpolates the given
        constants, so rows are added between the given temperatures until the two agree to
        1e-4 of the stiffness (they coincide at the given temperatures)."""
        kind, mat = self._elastic_expansion.get(id(b), ("", ""))
        target = ELASTIC_FOR_EXPANSION.get((cc, kind))
        if target is None:
            return out
        to_ortho = {"ISO": lambda v: ortho_from_iso(v[0], v[1]),
                    "ENGINEERING CONSTANTS": ortho_from_engineering, "ORTHO": list}[cc]
        n_line = 1 if cc == "ISO" else 2               # data lines per temperature row
        data = [ln for ln in out[1:] if ln.strip()]
        rows: List[Tuple[List[float], str]] = []       # (constants, temperature token)
        try:
            if len(data) % n_line:
                raise ValueError("incomplete row")
            for k in range(0, len(data), n_line):
                recs = [[x.strip() for x in ln.split(",")] for ln in data[k:k + n_line]]
                if n_line == 1:                        # E, nu[, T]
                    vals, rest = (recs[0] + ["", ""])[:2], recs[0][2:]
                else:                                  # 8 constants / 9th[, T]
                    vals, rest = (recs[0] + [""] * 8)[:8] + recs[1][:1], recs[1][1:]
                v = [pf(x) if x else 0.0 for x in vals]
                if cc == "ISO" and not (v[0] > 0.0 and -1.0 < v[1] < 0.5):
                    raise ValueError("invalid constants")
                if not all(math.isfinite(x) for x in to_ortho(v)):
                    raise ValueError("invalid constants")
                rows.append((v, rest[0] if rest else ""))
        except (ValueError, ZeroDivisionError):
            self.report.warn(f"Material {mat}: its *ELASTIC data could not be read or is invalid, "
                             f"so it was emitted unchanged beside *EXPANSION, TYPE={kind}; ccx 2.23 "
                             f"uses a wrong stiffness for this combination in linear steps of a "
                             f"deck with temperatures — give the elastic constants as "
                             f"TYPE={target}.", once=True)
            return out
        added, worst = 0, 0.0
        try:
            temps = [pf(t) for _, t in rows] if len(rows) > 1 else []
        except ValueError:
            temps = []
        if temps and all(t0 < t1 for t0, t1 in zip(temps, temps[1:])):
            fine = rows[:1]
            for (v0, _), row1, t0, t1 in zip(rows, rows[1:], temps, temps[1:]):
                def at(s: float, v0=v0, v1=row1[0]) -> List[float]:
                    return [x + s * (y - x) for x, y in zip(v0, v1)]
                # n equal sub-intervals; the error of ccx's interpolation at their middles,
                # relative to the largest stiffness constant there
                for n in (1, 2, 4, 8, 16, 32, 64):
                    d = [to_ortho(at(k / (2 * n))) for k in range(2 * n + 1)]
                    err = max(max(abs(m - (p + q) / 2.0) for p, m, q in zip(d[k], d[k + 1], d[k + 2]))
                              / (max(abs(x) for x in d[k + 1]) or 1.0) for k in range(0, 2 * n, 2))
                    if err <= 1e-4:
                        break
                worst = max(worst, err)
                fine += [(at(k / n), "%.12g" % (t0 + k * (t1 - t0) / n)) for k in range(1, n)]
                fine.append(row1)
            added = len(fine) - len(rows)
            rows = fine
        params = [p.strip() for p in out[0].split(",")[1:] if not p.strip().upper().startswith("TYPE=")]
        lines = [", ".join(["*ELASTIC", f"TYPE={target}"] + params)]
        for v, temp in rows:
            if target == "ANISO":
                consts = aniso_from_ortho(to_ortho(v))
            else:                                      # engineering constants of an isotropic material
                g = v[0] / (2.0 * (1.0 + v[1]))
                consts = [v[0]] * 3 + [v[1]] * 3 + [g] * 3
            # 12 significant digits: ccx reads only the first 20 characters of a field
            toks = ["%.12g" % x for x in consts] + ([temp] if temp else [])
            lines += [", ".join(toks[i:i + 8]) for i in range(0, len(toks), 8)]
        what = {"ISO": "isotropic", "ENGINEERING CONSTANTS": "engineering-constants",
                "ORTHO": "orthotropic"}[cc]
        why = ("an isotropic *ELASTIC with an orthotropic or anisotropic expansion" if cc == "ISO"
               else "an orthotropic *ELASTIC with an anisotropic expansion unless an *ORIENTATION "
                    "applies")
        self.report.note(f"Material {mat}: {what} *ELASTIC written as TYPE={target} with the same "
                         f"stiffness because of its *EXPANSION, TYPE={kind}: in linear steps of a "
                         f"deck with temperatures, ccx 2.23 uses a wrong stiffness (and thermal "
                         f"strains) for {why}."
                         + (f" {added} temperature row(s) added between the given ones: ccx "
                            f"interpolates the converted stiffness linearly in temperature, Abaqus "
                            f"the given constants, and the extra rows keep the two within "
                            f"{'1e-4' if worst <= 1e-4 else f'{worst:.1g}'}." if added else ""),
                         once=True)
        return lines

    def _check_nlgeom_expansion(self, blocks: List[Block]) -> None:
        """Warn about thermal expansions that ccx 2.23 computes wrongly in NLGEOM steps, which
        no form of the deck avoids.  There it splits the deformation gradient into a
        mechanical and a thermal part (calcmechstrain, modifystressstiff), and (probed with
        free heated unit cubes and plates):

        * it treats every *EXPANSION, TYPE=ORTHO as diagonal in global axes: where an
          *ORIENTATION or a composite ply angle turns the material axes so that the thermal
          strain has shear in global axes, the shear is dropped, without an error, with every
          *ELASTIC form and element type (C3D8/8R/8I/20R, S4, S8R and composite S8R, M3D4),
          in static, dynamic, explicit and coupled temperature-displacement steps, also with
          *PLASTIC.  Axes that the orientation only permutes are right;
        * it builds the thermal deformation gradient of a TYPE=ANISO expansion from the wrong
          array, and the step stops with 'too many cutbacks' once the deck has temperatures,
          with or without an *ORIENTATION and even when the temperature does not change.
          One without shear coefficients goes out as TYPE=ORTHO where its axes are not
          turned (_plan_expansion_as_ortho), and is checked as such.

        Linear steps and NLGEOM=NO are right; the CalculiX sources changed both routines in
        October 2026, after 2.23.  Decks without temperatures have no thermal strain."""
        nlgeom, step = False, None
        for b in blocks:
            if b.keyword == "STEP":
                step = b
                if b.has("NLGEOM") and (b.param("NLGEOM") or "YES").strip().upper() != "NO":
                    nlgeom = True
            elif b.keyword == "DYNAMIC" and b.has("EXPLICIT") and step is not None and \
                    not step.has("NLGEOM"):
                nlgeom = True                   # handle_step switches NLGEOM on there
        keys = {b.keyword for b in blocks}
        changes = bool(keys & {"TEMPERATURE", "COUPLED TEMPERATURE-DISPLACEMENT",
                               "UNCOUPLED TEMPERATURE-DISPLACEMENT"})
        if not nlgeom or not (changes or any(
                b.keyword == "INITIAL CONDITIONS" and
                (b.param("TYPE") or "").strip().upper() == "TEMPERATURE" for b in blocks)):
            return
        kinds: Dict[str, Tuple[str, Block, str]] = {}      # MATERIAL -> (kind, *EXPANSION, name)
        for group in self._material_groups(blocks):
            kind, exp = self._expansion_card(group)
            if kind and exp is not None:
                name = (group[0].param("NAME") or "").strip()
                kinds[name.upper()] = (kind, exp, name)
        if not kinds:
            return
        ortho: List[str] = []
        aniso: List[str] = []
        for mat, axes in self._material_uses(blocks):
            kind, exp, name = kinds.get(mat, ("", None, ""))
            if kind == "ANISO" and name not in aniso:
                aniso.append(name)
            elif kind == "ORTHO" and changes and exp is not None and name not in ortho and \
                    self._expansion_shear(exp, axes):
                ortho.append(name)

        def names(ms: List[str]) -> str:
            more = ", ..." if len(ms) > 5 else ""
            return f"Material{'s' if len(ms) > 1 else ''} {', '.join(ms[:5])}{more}"

        if ortho:
            self.report.warn(f"{names(ortho)}: *EXPANSION, TYPE=ORTHO in material axes that an "
                             f"*ORIENTATION or a composite ply angle turns off the global axes, in a "
                             f"deck with NLGEOM steps. In NLGEOM steps ccx 2.23 drops the shear "
                             f"that such a turned thermal strain has in global axes, without an "
                             f"error, with any *ELASTIC form, element type or procedure (probed: a "
                             f"free cube turned 30 deg keeps its normal strains but gets no shear "
                             f"strain; a [30/-30]s laminate's in-plane thermal strains come out 8 and "
                             f"41 % off). Linear steps are right, and no form of the deck avoids it in "
                             f"ccx 2.23: check the thermal strains against a hand calculation.",
                             once=True)
        if aniso:
            self.report.warn(f"{names(aniso)}: *EXPANSION, TYPE=ANISO in a deck with NLGEOM steps "
                             f"and temperatures. ccx 2.23 builds the thermal deformation gradient of "
                             f"an anisotropic expansion wrongly in NLGEOM steps, so they stop with "
                             f"'too many cutbacks' — with or without an *ORIENTATION, and even where "
                             f"the temperature does not change. Linear steps are right. An "
                             f"expansion without shear coefficients is written as TYPE=ORTHO, which "
                             f"ccx 2.23 computes right, except where an *ORIENTATION or a composite "
                             f"ply angle turns it so that it has shear in global axes: TYPE=ORTHO "
                             f"would lose that shear there without an error.", once=True)

    def _material_uses(self, blocks: List[Block]) -> List[Tuple[str, Optional[Tuple[Vec, Vec, Vec]]]]:
        """``(MATERIAL, axes)`` for every section and composite ply (shell or solid) that uses
        a material, its axes as _material_axes gives them (None where they vary)."""
        oris = {(b.param("NAME") or "").strip().upper(): b for b in blocks if b.keyword == "ORIENTATION"}
        uses: List[Tuple[str, Optional[Tuple[Vec, Vec, Vec]]]] = []
        for b in blocks:
            if not b.keyword.endswith("SECTION"):
                continue
            base = (b.param("ORIENTATION") or "").strip().upper()
            if b.has("COMPOSITE"):
                for rec in merged_data_records(b):  # thickness, points, material, angle or name
                    ply = rec[3] if len(rec) > 3 else ""
                    if len(rec) < 3 or not rec[2]:
                        continue
                    try:
                        ori, angle = base, (pf(ply) if ply else 0.0)
                    except ValueError:              # the ply names its own orientation
                        ori, angle = ply.upper(), 0.0
                    uses.append((rec[2].upper(), self._material_axes(oris, ori, angle)))
            elif b.param("MATERIAL"):
                uses.append(((b.param("MATERIAL") or "").strip().upper(),
                             self._material_axes(oris, base, 0.0)))
        return uses

    def _material_axes(self, oris: Dict[str, Block], name: str,
                       angle: float) -> Optional[Tuple[Vec, Vec, Vec]]:
        """The material axes (local 1, 2, 3 in global coordinates) of the *ORIENTATION
        ``name`` (the global axes when empty), turned by a composite ply ``angle`` about local
        3; None when they vary or cannot be formed (cylindrical and spherical systems,
        distributions, axes from each element's nodes, an undefined name)."""
        axes: Tuple[Vec, Vec, Vec] = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
        rots: List[Tuple[int, float]] = []
        if name:
            b = oris.get(name)
            if b is None or not (b.param("SYSTEM") or "RECTANGULAR").strip().upper().startswith("RECT") \
                    or (b.param("DEFINITION") or "").strip().upper().startswith("OFFSET"):
                return None
            pts = self._orientation_points(b)           # None for a distribution's name
            if pts is None:
                return None
            a, e3 = tuple(pts[0:3]), vcross(tuple(pts[0:3]), tuple(pts[3:6]))
            if not vnorm(a) or not vnorm(e3):
                return None
            e1, e3 = vunit(a), vunit(e3)
            axes = (e1, vcross(e3, e1), e3)
            recs = merged_data_records(b)
            if len(recs) > 1 and any(recs[1]):          # additional rotation: local axis, degrees
                try:
                    rots.append((pint(recs[1][0]), pf(recs[1][1]) if len(recs[1]) > 1 else 0.0))
                except ValueError:
                    return None
        rots.append((3, angle))
        for k, deg in rots:
            if k not in (1, 2, 3):
                return None
            if deg:
                u = axes[k - 1]
                axes = (rotate_about_axis(axes[0], (0.0, 0.0, 0.0), u, deg),
                        rotate_about_axis(axes[1], (0.0, 0.0, 0.0), u, deg),
                        rotate_about_axis(axes[2], (0.0, 0.0, 0.0), u, deg))
        return axes

    @staticmethod
    def _expansion_shear(exp: Block, axes: Optional[Tuple[Vec, Vec, Vec]]) -> bool:
        """Whether the orthotropic *EXPANSION ``exp`` (or an anisotropic one by its normal
        coefficients) in material ``axes`` (None: axes that vary) gives a thermal strain with
        shear in global axes at any of its temperature rows: eps_ij = sum_k alpha_k a_ki a_kj
        for local axes a_k.  Unreadable data counts as shear."""
        aniso = (exp.param("TYPE") or "").strip().upper() in ("ANISO", "ANISOTROPIC")
        recs = material_rows(exp, 6 if aniso else 3)
        if recs is None:
            return True
        try:
            rows = [[pf(x) if x else 0.0 for x in r[:3]] for r in recs]
        except ValueError:
            return True
        for a in rows or [[1.0, 2.0, 3.0]]:
            tol = 1e-9 * max(abs(x) for x in a)
            if axes is None:
                if max(a) - min(a) > tol:
                    return True
            elif any(abs(sum(a[k] * axes[k][i] * axes[k][j] for k in range(3))) > tol
                     for i, j in ((0, 1), (0, 2), (1, 2))):
                return True
        return False

    def _orientation_points(self, b: Block) -> Optional[List[float]]:
        """The ccx ``a, b`` direction points of an Abaqus *ORIENTATION, or None when they
        cannot be formed.  Abaqus measures a and b from the optional origin c (9-value
        line), and DEFINITION=NODES gives node numbers instead of coordinates."""
        recs = merged_data_records(b)
        v = [x for x in recs[0] if x != ""] if recs else []
        definition = (b.param("DEFINITION") or "COORDINATES").strip().upper()
        rect = (b.param("SYSTEM") or "RECTANGULAR").strip().upper().startswith("RECT")
        try:
            if definition.startswith("NODES"):
                ids = [pint(x) for x in v[:3]]
                pts = [self.geom.nodes[i] for i in ids if i in self.geom.nodes]
                if len(pts) < 2:
                    return None
                a, bb = pts[0], pts[1]
                c = pts[2] if len(pts) > 2 else (0.0, 0.0, 0.0)
            else:
                nums = [pf(x) for x in v]
                if len(nums) < 6:
                    return None
                a, bb = tuple(nums[0:3]), tuple(nums[3:6])
                c = tuple(nums[6:9]) if len(nums) >= 9 else (0.0, 0.0, 0.0)
        except (ValueError, KeyError):
            return None
        if rect and any(c):
            a, bb = vsub(a, c), vsub(bb, c)
        return [*a, *bb]

    def handle_orientation(self, b: Block) -> List[str]:
        definition = (b.param("DEFINITION") or "COORDINATES").strip().upper()
        if definition.startswith("OFFSET"):
            return self._commented(b, "*ORIENTATION, DEFINITION=OFFSET TO NODES (axes from each "
                                      "element's own local nodes) has no ccx equivalent; define "
                                      "the system by coordinates or a *DISTRIBUTION.")
        if self._orientation_distribution(b) is not None:
            return self._distribution_orientation(b)
        params: "OrderedDict[str, Optional[str]]" = OrderedDict()
        for k, v in b.params.items():
            if k == "DEFINITION":
                continue
            if k == "SYSTEM" and v and v.upper().startswith("SPHER"):
                self.report.warn("*ORIENTATION SYSTEM=SPHERICAL is unsupported by ccx; emitted as "
                                 "RECTANGULAR — verify the local system.", once=True)
                params["SYSTEM"] = "RECTANGULAR"
            else:
                params[k] = v
        out = [emit_keyword("ORIENTATION", params)]
        recs = merged_data_records(b)
        if recs:
            v = [x for x in recs[0] if x != ""]
            pts = self._orientation_points(b)
            if definition.startswith("NODES"):
                if pts is None:
                    return self._commented(b, "*ORIENTATION, DEFINITION=NODES: the node numbers "
                                              "could not be resolved to coordinates; define the "
                                              "system by coordinates.")
                v = [_fmt_component(x) for x in pts]
                self.report.note("*ORIENTATION, DEFINITION=NODES resolved to coordinates (ccx "
                                 "takes points a, b).", once=True)
                name = (b.param("NAME") or "").upper()
                if name in self.orientations:      # nodes may follow the card in the deck
                    self.orientations[name] = (tuple(pts[0:3]), tuple(pts[3:6]),
                                               self.orientations[name][2])
            elif len(v) > 6:
                try:
                    has_origin = len(v) >= 9 and any(pf(x) != 0.0 for x in v[6:9])
                except ValueError:
                    has_origin = False
                if pts is not None and has_origin:
                    v = [_fmt_component(x) for x in pts]
                    self.report.note("*ORIENTATION origin c subtracted from points a, b (ccx has no "
                                     "origin field; the axes are a-c and b-c as in Abaqus).", once=True)
                else:
                    self.report.note("*ORIENTATION: coordinates beyond points a,b dropped (ccx "
                                     "uses 2 points).", once=True)
                    v = v[:6]
            out.append(", ".join(v))
        if len(recs) > 1:
            v = [x for x in recs[1] if x != ""]
            if v:
                system = (params.get("SYSTEM") or "RECTANGULAR").upper()
                if system.startswith("RECT"):
                    out.append(", ".join(v))
                    self.report.note("*ORIENTATION additional-rotation line kept (needs ccx >= ~2.15).", once=True)
                else:
                    # ccx: "additional rotation ... is only allowed for rectangular systems"
                    self.report.warn(f"*ORIENTATION SYSTEM={system}: the additional-rotation line is "
                                     f"not allowed by ccx for non-rectangular systems and was dropped "
                                     f"— verify material directions.", once=True)
        return out

    # -- *DISTRIBUTION orientations -----------------------------------------
    def handle_distribution(self, b: Block) -> List[str]:
        """An orientation distribution is re-emitted right before each *ORIENTATION that
        names it (see _plan_distributions), so the card itself emits nothing.  ccx has no
        other kind of distribution."""
        name = (b.param("NAME") or "").strip().upper()
        if not (b.param("LOCATION") or "ELEMENT").strip().upper().startswith("ELEM"):
            return self._commented(b, f"*DISTRIBUTION {name}, LOCATION={b.param('LOCATION')}: ccx "
                                      f"takes per-element orientations from element distributions "
                                      f"only, and has no other kind.")
        plans = [p for p in self._dist_ori.values() if p["dist"] == name]
        if any(p["has_data"] for p in plans):
            self.report.note("*DISTRIBUTION orientations re-emitted for ccx 2.23 right before "
                             "each *ORIENTATION that names them: one line per element of its "
                             "solid sections (default line first, origin subtracted, the "
                             "additional rotation applied to the axes); its shell and membrane "
                             "sections get one plain *ORIENTATION per distinct direction.",
                             once=True)
            return []
        if plans:
            return self._commented(b, f"*DISTRIBUTION {name} has no data lines, so the "
                                      f"*ORIENTATION that names it cannot be formed.")
        return self._commented(b, f"*DISTRIBUTION {name} is not named by any *ORIENTATION: ccx "
                                  f"supports distributions only as per-element orientations "
                                  f"(Abaqus also distributes shell thicknesses and material "
                                  f"properties) — model the variation with element sets and one "
                                  f"section or material each.")

    def handle_distribution_table(self, b: Block) -> List[str]:
        if (b.param("NAME") or "").strip().upper() in self._dist_tables:
            self.report.note("*DISTRIBUTION TABLE of an orientation distribution dropped (ccx "
                             "needs no table: its distribution lines are always a, b).", once=True)
            return []
        return self.passthrough(b)

    def _orientation_distribution(self, b: Block) -> Optional[str]:
        """The distribution an *ORIENTATION names on its data line in place of the point
        coordinates (Abaqus per-element orientations), or None."""
        if not (b.param("DEFINITION") or "COORDINATES").strip().upper().startswith("COORD"):
            return None
        recs = merged_data_records(b)
        tok = recs[0][0] if recs and recs[0] else ""
        if not tok:
            return None
        if tok.upper() in self._dists:            # even a name such as INF or NAN
            return tok.upper()
        try:
            pf(tok)
        except ValueError:
            return tok.upper()
        return None

    def _distribution_orientation(self, b: Block) -> List[str]:
        """An *ORIENTATION that names a *DISTRIBUTION, preceded by the distribution in the
        form ccx 2.23 runs correctly (see _plan_distributions)."""
        name = (b.param("NAME") or "").strip().upper()
        ref = self._orientation_distribution(b)
        plan = self._dist_ori.get(name)
        if plan is None and ref in self._dists:
            return self._commented(b, f"*ORIENTATION {name} names *DISTRIBUTION {ref}, which is not "
                                      f"element-based: per-element orientations need an element "
                                      f"distribution (LOCATION=ELEMENT).")
        if plan is None:
            return self._commented(b, f"*ORIENTATION {name} names *DISTRIBUTION {ref}, which the "
                                      f"deck does not define; define the distribution or give "
                                      f"the axes by coordinates.")
        if not plan["has_data"]:
            return self._commented(b, f"*ORIENTATION {name}: its *DISTRIBUTION {ref} has no data "
                                      f"lines (INPUT= file missing?), so the per-element material "
                                      f"directions are unknown and the sections that use it "
                                      f"cannot run until the data is supplied.")
        params: "OrderedDict[str, Optional[str]]" = OrderedDict()
        for k, v in b.params.items():
            if k == "DEFINITION":
                continue
            if k == "SYSTEM" and v and v.upper().startswith("SPHER"):
                self.report.warn("*ORIENTATION SYSTEM=SPHERICAL is unsupported by ccx; emitted as "
                                 "RECTANGULAR — verify the local system.", once=True)
                params["SYSTEM"] = "RECTANGULAR"
            else:
                params[k] = v
        if plan["dropped_rot"]:
            self.report.warn(f"*ORIENTATION {name}: an additional rotation is not allowed by ccx "
                             f"for a non-rectangular system and was dropped — verify material "
                             f"directions.", once=True)
        if plan["split"] and not plan["solid"]:
            return []                              # its shell sections carry their own axes
        first = plan["default"]
        head = [", " + ", ".join(first)] if first else []
        body: List[str] = []
        if plan["solid"]:
            elems = sorted(plan["solid"])
            body = [f"{e}, " + ", ".join(plan["vec"][e]) for e in elems if e in plan["vec"]]
            uncovered = sum(1 for e in elems if e not in plan["vec"])
            if uncovered and first is None:
                self.report.warn(f"*ORIENTATION {name}: {uncovered} element(s) of its solid "
                                 f"sections are not listed in *DISTRIBUTION {ref}, which has no "
                                 f"default line (Abaqus requires one); ccx gives them the first "
                                 f"line's axes — verify.", once=True)
        if not head and not body:                  # unused: one untagged line keeps it valid
            head = [", " + ", ".join(next(iter(plan["vec"].values())))]
        return ([f"*DISTRIBUTION, NAME={plan['copy']}"] + head + body
                + [emit_keyword("ORIENTATION", params), plan["copy"]])

    def _plan_distributions(self, blocks: List[Block]) -> None:
        """Per-element orientations given by a *DISTRIBUTION (Abaqus discrete orientations,
        variable-angle-tow layups), planned for what ccx 2.23 does with them (probed, and
        read off its distribution, orientation and section readers):

        * every distribution line becomes an orientation of its own, and the *ORIENTATION
          that names the distribution takes all of them over, so a second *ORIENTATION
          naming the same distribution stops ccx ('distribution ... has not been defined');
        * only *SOLID SECTION gives each listed element its own line; the elements it does
          not list get the first line, so the Abaqus default line must come first;
        * *SHELL SECTION, plain or COMPOSITE, and *MEMBRANE SECTION ignore the lines and give
          every element the first one;
        * the *ORIENTATION's additional-rotation line turns only the first line correctly;
        * origin values (fields 8-10) are ignored, and a distribution name ccx can read as a
          number (D1, E5, 12) silently zeroes the orientation (see _fortran_real_like).

        So each such orientation gets its own copy of the distribution, resolved to one line
        per element of its solid sections (default line first, origin subtracted, the
        additional rotation applied to the axes, no rotation line), which handle_orientation
        emits right before it; and every shell or membrane section that uses one is split
        into an element set, a plain *ORIENTATION and a section per distinct direction."""
        self._dists = OrderedDict()
        for b in blocks:
            if b.keyword == "DISTRIBUTION" and (b.param("NAME") or "").strip():
                self._dists[b.param("NAME").strip().upper()] = b
        refs: List[Tuple[str, str, Block]] = []
        plain: set = set()
        for b in blocks:
            if b.keyword != "ORIENTATION":
                continue
            name = (b.param("NAME") or "").strip().upper()
            ref = self._orientation_distribution(b)
            if ref is None:
                plain.add(name)
            else:
                self._dist_refs.add(name)
                if ref in self._dists:
                    refs.append((name, ref, b))
        if not self._dists:
            return
        self._used_names = set(self.geom.elsets) | plain | set(self._dists) | {r[0] for r in refs}
        given: set = set()
        for name, ref, b in refs:
            dist = self._dists[ref]
            if not (dist.param("LOCATION") or "ELEMENT").strip().upper().startswith("ELEM"):
                continue                           # node labels: handle_orientation reports it
            rect = not (b.param("SYSTEM") or "RECTANGULAR").strip().upper().startswith("CYL")
            rot = self._orient_rotation.get(name)
            dropped = bool(rot and rot[1] and not rect)
            if rot and (not rect or rot[0] not in (1, 2, 3)):
                rot = None
            default, vec = self._distribution_lines(dist, ref, rect, rot)
            # ccx hands a distribution to the first *ORIENTATION that names it, and reads a
            # name that looks like a number as coordinates: give those a copy of their own
            if ref in given or ref in plain or _fortran_real_like(ref):
                copy = self._fresh_name(f"{ref}_{name}")
            else:
                copy = ref
            given.add(ref)
            if dist.param("TABLE"):
                self._dist_tables.add(dist.param("TABLE").strip().upper())
            self._dist_ori[name] = dict(dist=ref, copy=copy, rect=rect, rot=rot,
                                        dropped_rot=dropped, default=default, vec=vec,
                                        has_data=default is not None or bool(vec),
                                        solid=set(), split=False)
        for b in blocks:
            kw = b.keyword
            ori = (b.param("ORIENTATION") or "").strip().upper()
            elset = (b.param("ELSET") or "").strip()
            shell = kw in ("SHELL SECTION", "SHELL GENERAL SECTION")
            if shell and self._continuum_shell_elset(elset):
                if ori in self._dist_ori and not b.has("COMPOSITE"):    # runs as a solid
                    self._dist_ori[ori]["solid"].update(self._existing(elset))
            elif shell or kw == "MEMBRANE SECTION":
                if not (kw == "SHELL GENERAL SECTION"
                        and not (b.has("MATERIAL") or b.has("COMPOSITE"))):
                    self._plan_split(b, ori)
            elif kw in ("SOLID SECTION", "COHESIVE SECTION", "GASKET SECTION"):
                if ori in self._dist_ori:
                    self._dist_ori[ori]["solid"].update(self._existing(elset))
            elif ori in self._dist_ori:
                self.report.warn(f"*{kw}, ORIENTATION={ori}: a *DISTRIBUTION orientation gives "
                                 f"per-element axes to sections only; ccx gives this card the "
                                 f"distribution's first (default) axes — verify.", once=True)

    def _existing(self, elset: str) -> List[int]:
        return [e for e in self.geom.elset(elset) if e in self.geom.elements]

    def _continuum_shell_elset(self, elset: Optional[str]) -> bool:
        """Whether every element of ``elset`` is a continuum shell (SC6R/SC8R): those run as
        C3D6/C3D8I solids in ccx, so their *SHELL SECTION becomes a *SOLID SECTION."""
        types = {self.geom.elements[e][0].upper() for e in self.geom.elset(elset or "")
                 if e in self.geom.elements}
        return bool(types) and all(t.startswith("SC") for t in types)

    def _distribution_lines(self, dist: Block, ref: str, rect: bool,
                            rot: Optional[Tuple[int, float]]):
        """``(default, {element: axes})`` of an orientation distribution, each axes entry the
        six ccx tokens of a, b (see _distribution_axes); a later line wins, as in ccx, and an
        element-set label covers every member."""
        default = None
        vec: "OrderedDict[int, Tuple[str, ...]]" = OrderedDict()
        bad = undefined = 0
        for rec in merged_data_records(dist):
            if not any(rec):
                continue
            label, toks = rec[0], [x for x in rec[1:] if x != ""]
            try:
                vals = [pf(x) for x in toks]
            except ValueError:
                vals = []
            if len(vals) < 6:
                bad += 1
                continue
            # ccx reads each value as (f20.0): a longer token would be cut off
            if (rect and ((len(vals) >= 9 and any(vals[6:9])) or (rot and rot[1]))) or \
                    any(len(t) > 20 for t in toks[:6]):
                a, bv = _distribution_axes(vals, rect, rot)
                axes = tuple(_fmt_component(x) for x in (*a, *bv))
            else:
                axes = tuple(toks[:6])
            if label == "":
                default = axes
            elif re.fullmatch(r"[-+]?\d+", label):
                if int(label) in self.geom.elements:
                    vec[int(label)] = axes
                else:
                    undefined += 1
            else:
                members = self._existing(label)
                undefined += 0 if members else 1
                for e in members:
                    vec[e] = axes
        if bad:
            self.report.warn(f"*DISTRIBUTION {ref}: {bad} line(s) without six numeric values "
                             f"(a, b) were skipped.", once=True)
        if undefined:
            self.report.warn(f"*DISTRIBUTION {ref}: {undefined} line(s) name an undefined element "
                             f"or element set and were skipped.", once=True)
        return default, vec

    def _plan_split(self, b: Block, ori: str) -> None:
        """Split a shell/membrane section that uses *DISTRIBUTION orientations (its own or a
        composite ply's) into element groups that share the same axes."""
        involved = [ori] if ori in self._dist_ori else []
        if b.has("COMPOSITE"):
            for rec in merged_data_records(b):
                o = rec[3].strip().upper() if len(rec) > 3 else ""
                if o in self._dist_ori and o not in involved:
                    involved.append(o)
        involved = [o for o in involved if self._dist_ori[o]["has_data"]]
        elset = (b.param("ELSET") or "").strip().upper()
        if not involved or not elset:
            return
        groups: "OrderedDict[tuple, List[int]]" = OrderedDict()
        uncovered = 0
        for e in dedup(self._existing(elset)):
            key = []
            for o in involved:
                p = self._dist_ori[o]
                axes = p["vec"].get(e, p["default"])
                if axes is None:
                    uncovered += 1
                    axes = next(iter(p["vec"].values()))
                key.append(axes)
            groups.setdefault(tuple(key), []).append(e)
        if uncovered:
            self.report.warn(f"*{b.keyword} {elset}: {uncovered} element(s) are not listed in its "
                             f"*DISTRIBUTION orientation, which has no default line (Abaqus "
                             f"requires one); they get the first line's axes — verify.", once=True)
        split = []
        for k, (key, members) in enumerate(groups.items(), 1):
            gname = elset if len(groups) == 1 else self._fresh_name(f"{elset}_G{k}")
            if gname != elset:
                self.geom.elsets[gname] = members
            split.append((gname, dict(zip(involved, key))))
        self._dist_split[id(b)] = split
        for o in involved:
            self._dist_ori[o]["split"] = True
        self.report.note(f"*{b.keyword} with a *DISTRIBUTION orientation split into one element "
                         f"set, plain *ORIENTATION and section per distinct direction (ccx 2.23 "
                         f"gives every element of a shell or membrane section the "
                         f"distribution's first line).", once=True)

    def _plain_dist_orientation(self, name: str, axes: Tuple[str, ...], angle: float,
                                pre: List[str]) -> str:
        """A plain *ORIENTATION with the axes of one distribution group, turned by ``angle``
        about the shell normal for a composite ply, written into ``pre`` the first time a
        section needs it."""
        plan = self._dist_ori[name]
        key = (axes, round(angle, 6), plan["rect"])
        if key in self._dist_plain:
            return self._dist_plain[key]
        oname = self._fresh_name(f"{name}_A{len(self._dist_plain) + 1}")
        self._dist_plain[key] = oname
        pre.append(f"*ORIENTATION, NAME={oname}" + ("" if plan["rect"] else ", SYSTEM=CYLINDRICAL"))
        pre.append(", ".join(axes))
        if angle and plan["rect"]:
            pre.append(f"3, {fmt_num(angle)}")
        elif angle:
            self.report.warn(f"Composite ply angle on the cylindrical *DISTRIBUTION orientation "
                             f"'{name}': ccx allows no additional rotation for a non-rectangular "
                             f"system, so the ply angle was dropped — verify ply directions.",
                             once=True)
        return oname

    def _fresh_name(self, base: str) -> str:
        """A set / orientation / distribution name used nowhere else in the deck, within
        ccx's 80-character limit, and one ccx cannot read as a number."""
        base = base.upper()
        if _fortran_real_like(base):
            base = "ABQ2CCX_" + base
        cand, i = base[:CCX_NAME_LIMIT], 1
        while cand in self._used_names:
            sfx = f"~{i}"
            cand = base[:CCX_NAME_LIMIT - len(sfx)] + sfx
            i += 1
        self._used_names.add(cand)
        return cand

    def handle_solid_section(self, b: Block) -> List[str]:
        keep: "OrderedDict[str, Optional[str]]" = OrderedDict()
        for k, v in b.params.items():
            if k in ("ELSET", "MATERIAL", "ORIENTATION"):
                keep[k] = v
            elif k == "COMPOSITE":
                self.report.warn("*SOLID SECTION, COMPOSITE is not supported by ccx; model each layer "
                                 "with its own solid elements/section.", once=True)
            else:
                self.report.note(f"*SOLID SECTION parameter {k} dropped (unused by ccx).", once=True)
        data = list(b.data)
        thick = data[0].split(",")[0].strip() if data else ""
        if not thick and b.param("ELSET"):
            quiet = Report()
            types = {ccx_element_type(self.geom.elements[e][0], quiet)
                     for e in self.geom.elset(b.param("ELSET") or "") if e in self.geom.elements}
            if types and any(t.startswith(("CPS", "CPE")) for t in types):
                data = ["1."] + data[1:]
                self.report.note("*SOLID SECTION on plane-stress/strain elements without a "
                                 "thickness -> 1. (the Abaqus default; ccx stops on a zero "
                                 "thickness).", once=True)
        return [emit_keyword("SOLID SECTION", keep)] + data

    def handle_cohesive_section(self, b: Block) -> List[str]:
        """``*COHESIVE SECTION`` / ``*GASKET SECTION`` -> ``*SOLID SECTION``.  The cohesive/
        gasket elements are substituted by a thin continuum (see ccx_element_type), so they
        need an ordinary solid section.  The traction-separation / closure law is NOT
        reproduced -- the layer runs as an elastic solid and MATERIAL must be a valid solid
        material (a traction *ELASTIC, TYPE=... would be rejected by ccx)."""
        kind = "cohesive" if b.keyword == "COHESIVE SECTION" else "gasket"
        elset, mat = b.param("ELSET"), b.param("MATERIAL")
        if not elset or not mat:
            return self._commented(b, f"*{b.keyword} has no ELSET/MATERIAL to map to *SOLID SECTION.")
        self.report.warn(f"*{b.keyword} -> *SOLID SECTION: the {kind} elements run as a thin elastic "
                         f"solid, so the {kind} traction/closure behaviour is NOT modelled; ensure "
                         f"MATERIAL={mat} is a valid solid material (a traction-separation "
                         f"*ELASTIC, TYPE=... will be rejected by ccx). Verify.", once=True)
        keep: "OrderedDict[str, Optional[str]]" = OrderedDict([("ELSET", elset), ("MATERIAL", mat)])
        if b.param("ORIENTATION"):
            keep["ORIENTATION"] = b.param("ORIENTATION")
        return [emit_keyword("SOLID SECTION", keep)]

    def handle_surface_section(self, b: Block) -> List[str]:
        """``*SURFACE SECTION``: the section of surface elements; dropped with them when they
        leave the ccx mesh (_drop_surface_elements), commented out otherwise (ccx has none)."""
        if self._only_carriers(b.param("ELSET") or ""):
            self.report.note("*SURFACE SECTION dropped with its surface elements.", once=True)
            return []
        return self.passthrough(b)

    def handle_beam_section(self, b: Block) -> List[str]:
        sec = (b.param("SECTION") or "").upper()
        # ccx 2.22 beam profiles: RECT, CIRC (ellipse), PIPE, BOX.  Anything else is a
        # hard "unknown section" error, so comment it out with the escape hatches.
        if sec not in ("", "RECT", "CIRC", "PIPE", "BOX", "THICK PIPE"):
            if self._approx and sec == "I":
                approx = self._ibeam_to_rect(b)
                if approx is not None:
                    return approx
            return self._commented(b, f"*BEAM SECTION SECTION={sec} is not a ccx profile (ccx has "
                                      f"RECT, CIRC, PIPE, BOX; GENERAL only with user element U1). "
                                      f"Remodel with an equivalent BOX/RECT, or use beam-like solids"
                                      f"{'' if self._approx else ', or rerun with --approximate'}.")
        keep: "OrderedDict[str, Optional[str]]" = OrderedDict()
        for k, v in b.params.items():
            if k in ("ELSET", "MATERIAL", "SECTION", "ORIENTATION", "OFFSET1", "OFFSET2"):
                keep[k] = v
            else:
                self.report.note(f"*BEAM SECTION parameter {k} dropped.", once=True)
        if sec == "THICK PIPE":
            keep["SECTION"] = "PIPE"
            self.report.note("*BEAM SECTION SECTION=THICK PIPE -> PIPE (same outer radius / wall "
                             "thickness data; ccx places PIPE's integration points at the radius "
                             "that reproduces a thick wall's second moment of area).", once=True)
        # PIPE (outer radius, wall thickness) and BOX (a, b, t1..t4: a along local 1, b along
        # local 2, walls t1..t4 at +1, +2, -1, -2) data lines read the same in both codes
        # (ccx manual 7.3 and Fig. 82; the wall order probed on 2.23), so they pass through.
        data = list(b.data)
        if sec == "CIRC":
            # Abaqus gives the radius; ccx reads the two section DIAMETERS (an ellipse's axis
            # lengths; a lone value is used for both).  Passed through, the radius made the
            # beam 16x too flexible in bending (probed on 2.23 against PL^3/3EI).
            first = [x.strip() for x in data[0].split(",") if x.strip()] if data else []
            try:
                r = pf(first[0]) if first else 0.0
            except ValueError:
                r = 0.0
            if r > 0:
                data[0] = "%.12g, %.12g" % (2 * r, 2 * r)
                self.report.note("*BEAM SECTION SECTION=CIRC: the Abaqus radius r -> ccx's two "
                                 "section diameters 2r, 2r.", once=True)
            else:
                self.report.warn("*BEAM SECTION SECTION=CIRC: no readable radius on the first data "
                                 "line; ccx expects the two section diameters (2r, 2r) there — "
                                 "set it by hand.", once=True)
        return [emit_keyword("BEAM SECTION", keep)] + data

    def _ibeam_to_rect(self, b: Block) -> Optional[List[str]]:
        """--approximate: replace an I-profile with the RECT of equal area and equal
        strong-axis inertia.  Weak-axis bending, torsion and shear areas DIFFER."""
        recs = merged_data_records(b)
        if not recs:
            return None
        try:
            v = [pf(x) for x in recs[0] if x != ""]
        except ValueError:
            return None
        if len(v) < 7:
            return None
        _l, h, b1, b2, t1, t2, t3 = v[:7]
        hw = h - t1 - t2
        if min(h, b1, b2, t1, t2, t3) <= 0 or hw <= 0:
            return None
        segs = [(b1 * t1, t1 / 2.0, b1 * t1 ** 3 / 12.0),
                (b2 * t2, h - t2 / 2.0, b2 * t2 ** 3 / 12.0),
                (t3 * hw, t1 + hw / 2.0, t3 * hw ** 3 / 12.0)]
        area = sum(a for a, _, _ in segs)
        ybar = sum(a * y for a, y, _ in segs) / area
        inertia = sum(i0 + a * (y - ybar) ** 2 for a, y, i0 in segs)
        h_r = math.sqrt(12.0 * inertia / area)
        b_r = area / h_r
        keep: "OrderedDict[str, Optional[str]]" = OrderedDict()
        for k, val in b.params.items():
            if k in ("ELSET", "MATERIAL", "ORIENTATION", "OFFSET1", "OFFSET2"):
                keep[k] = val
        keep["SECTION"] = "RECT"
        self.report.warn("[APPROX] *BEAM SECTION SECTION=I replaced by the RECT with equal area "
                         "and equal strong-axis inertia; weak-axis bending, torsion and shear "
                         "response DIFFER. Verify.", once=True)
        out = [emit_keyword("BEAM SECTION", keep), f"{b_r:.6g}, {h_r:.6g}"]
        if len(recs) > 1:                          # keep the direction-cosine line
            second = [x for x in recs[1] if x != ""]
            if second:
                out.append(", ".join(second))
        return out

    def handle_shell_section(self, b: Block) -> List[str]:
        elset = b.param("ELSET")
        base_ori = b.param("ORIENTATION") or ""
        if b.keyword == "SHELL GENERAL SECTION":
            # ccx has no *SHELL GENERAL SECTION.  A thickness+material form maps to
            # *SHELL SECTION; a stiffness/ABD form has no equivalent.
            if not (b.has("MATERIAL") or b.has("COMPOSITE")):
                return self._commented(b, "*SHELL GENERAL SECTION given as a stiffness (ABD) section "
                                          "has no ccx equivalent; rebuild as *SHELL SECTION with a "
                                          "thickness + material, or a composite layup.")
            self.report.note("*SHELL GENERAL SECTION -> *SHELL SECTION (membrane/bending stiffness "
                             "semantics are not identical; verify).", once=True)
        if elset and self._continuum_shell_elset(elset):
            # continuum shells run as C3D6/C3D8I solids in ccx, which stops on a shell
            # section there; the thickness comes from the mesh
            if b.has("COMPOSITE"):
                return self._commented(b, "*SHELL SECTION, COMPOSITE on continuum shells "
                                          "(SC6R/SC8R): they run as solids in ccx, which has no "
                                          "layered solid section — mesh the plies as separate "
                                          "solid layers or use S8R composite shells.")
            keep_s: "OrderedDict[str, Optional[str]]" = OrderedDict(
                (k, v) for k, v in b.params.items() if k in ("ELSET", "MATERIAL", "ORIENTATION"))
            self.report.note("*SHELL SECTION on continuum shells (SC6R/SC8R) -> *SOLID SECTION "
                             "(they run as C3D6/C3D8I solids; thickness comes from the mesh).",
                             once=True)
            return [emit_keyword("SOLID SECTION", keep_s)]
        split = self._dist_split.get(id(b))
        if split is None:
            return self._shell_section_cards(b, elset, base_ori, {})
        out: List[str] = []
        for gname, axes in split:
            out += self._shell_section_cards(b, gname, base_ori, axes)
        return out

    def _shell_section_cards(self, b: Block, elset: Optional[str], base_ori: str,
                             axes: Dict[str, Tuple[str, ...]]) -> List[str]:
        """The ccx cards of a *SHELL SECTION for the elements of ``elset``.  ``axes`` holds,
        for a group of elements that share them, the a, b tokens of each *DISTRIBUTION
        orientation the section uses (see _plan_split); it is empty when it uses none."""
        base = base_ori.upper()
        if b.has("COMPOSITE"):
            if elset:
                types = {self.geom.elements[e][0] for e in self.geom.elset(elset)
                         if e in self.geom.elements}
                bad = sorted(t for t in types if t in SHELL_TYPES and t not in COMPOSITE_SHELL_OK)
                if bad:
                    self.report.warn(f"*SHELL SECTION, COMPOSITE on {bad}: ccx composite shells require "
                                     f"S6 or S8R.", once=True)
            keep: "OrderedDict[str, Optional[str]]" = OrderedDict()
            for k, v in b.params.items():
                if k == "ELSET":
                    keep[k] = elset
                elif k == "OFFSET":
                    keep[k] = v
                elif k == "COMPOSITE":
                    keep[k] = None
                elif k in ("ORIENTATION", "SYMMETRIC"):
                    continue
                else:
                    self.report.note(f"*SHELL SECTION parameter {k} dropped.", once=True)
            pre: List[str] = []
            ply_lines: List[str] = []
            for rec in merged_data_records(b):
                # Positional: thickness, integration-pts, material, angle[, plyname].
                # Interior blanks are significant, so do NOT filter empty fields out.
                g = [x.strip() for x in rec]
                while g and g[-1] == "":
                    g.pop()
                if len(g) < 3 or g[0] == "":
                    continue
                thick, mat = g[0], g[2]
                ply_ori = g[3] if len(g) > 3 else ""
                if ply_ori == "":
                    oriname = self._plain_dist_orientation(base, axes[base], 0.0, pre) \
                        if base in axes else (base or None)
                else:
                    try:                                  # Abaqus: numeric ply angle
                        angle = float(ply_ori)
                    except ValueError:                    # already an *ORIENTATION name
                        oriname = ply_ori.upper()
                        if oriname in axes:
                            oriname = self._plain_dist_orientation(oriname, axes[oriname], 0.0, pre)
                    else:
                        # a distribution orientation's own rotation is already in its axes
                        oriname = self._plain_dist_orientation(base, axes[base], angle, pre) \
                            if base in axes else self._synth_orientation(base_ori, ply_ori, pre)
                if oriname:
                    ply_lines.append(f"{thick}, , {mat}, {oriname}")
                else:
                    ply_lines.append(f"{thick}, , {mat}")
            self.report.note("*SHELL SECTION, COMPOSITE: ply angles converted to synthesized "
                             "*ORIENTATION cards (rotation about the shell normal). Verify for curved "
                             "shells.", once=True)
            if b.has("SYMMETRIC"):
                # Abaqus lists the bottom half of a symmetric layup and mirrors it about the
                # mid-surface; ccx has no such flag, so write the full stack
                ply_lines = ply_lines + ply_lines[::-1]
                self.report.note("*SHELL SECTION, COMPOSITE, SYMMETRIC: plies mirrored about the "
                                 "mid-surface (ccx needs the full layup).", once=True)
            return pre + [emit_keyword("SHELL SECTION", keep)] + ply_lines
        # simple (single-material) shell
        keep = OrderedDict()
        for k, v in b.params.items():
            if k in ("ELSET", "MATERIAL", "ORIENTATION", "OFFSET", "NODAL THICKNESS"):
                keep[k] = v
            else:
                self.report.note(f"*SHELL SECTION parameter {k} dropped.", once=True)
        if "ELSET" in keep:
            keep["ELSET"] = elset
        pre = []
        if base in axes:
            keep["ORIENTATION"] = self._plain_dist_orientation(base, axes[base], 0.0, pre)
        out = pre + [emit_keyword("SHELL SECTION", keep)]
        recs = merged_data_records(b)
        if recs:
            f = [x for x in recs[0] if x != ""]
            if f:
                if len(f) > 1:
                    self.report.note("*SHELL SECTION: integration-point count dropped (ccx wants the "
                                     "thickness only).", once=True)
                out.append(f[0])
        return out

    def handle_membrane_section(self, b: Block) -> List[str]:
        split = self._dist_split.get(id(b))
        if split is None:
            return self.passthrough(b)
        base = (b.param("ORIENTATION") or "").strip().upper()
        out: List[str] = []
        for gname, axes in split:
            params: "OrderedDict[str, Optional[str]]" = OrderedDict(b.params)
            params["ELSET"] = gname
            pre: List[str] = []
            params["ORIENTATION"] = self._plain_dist_orientation(base, axes[base], 0.0, pre)
            out += pre + [emit_keyword("MEMBRANE SECTION", params)] + list(b.data)
        return out

    def _synth_orientation(self, base_name: str, angle: str, pre: List[str]) -> Optional[str]:
        if base_name and base_name.upper() in self._dist_refs:
            # an orientation that names a *DISTRIBUTION reaches here only when its axes could
            # not be resolved (it is commented out): there are no axes to turn
            return base_name.upper()
        try:
            ang = float(angle)
        except ValueError:
            ang = 0.0
        base = self.orientations.get(base_name.upper()) if base_name else None
        if base:
            a, bvec, system = base
            if system != "RECTANGULAR":
                self.report.warn(f"Composite ply orientation is based on non-rectangular system "
                                 f"'{system}'; the synthesized orientation may be inaccurate.", once=True)
        else:
            a, bvec = (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)
        if ang == 0.0:
            return base_name.upper() if base_name else None
        key = (base_name.upper() if base_name else "", round(ang, 6))
        if key in self._synth_cache:
            return self._synth_cache[key]
        # the base orientation's own additional rotation: one about the shell normal
        # (local 3) composes with the ply angle; ccx allows one rotation line, so any
        # other axis cannot be combined
        total = ang
        rot = self._orient_rotation.get(base_name.upper()) if base_name else None
        if rot:
            if rot[0] == 3:
                total = rot[1] + ang
            else:
                self.report.warn(f"Composite ply angle on orientation '{base_name}', which already "
                                 f"rotates about local axis {rot[0]}: ccx allows a single rotation "
                                 f"per orientation, so that base rotation is not combined — verify "
                                 f"the ply directions.", once=True)
        name = f"ABQ2CCX_OR{len(self._synth_cache) + 1}"
        self._synth_cache[key] = name
        pre.append(f"*ORIENTATION, NAME={name}")
        pre.append(", ".join(fmt_num(x) for x in (a[0], a[1], a[2], bvec[0], bvec[1], bvec[2])))
        pre.append(f"3, {fmt_num(total)}")
        return name

    # -- step / load / bc handlers -----------------------------------------
    def handle_step(self, group: List[Block]) -> List[str]:
        step_block = group[0]
        inner = group[1:]
        self._step_idx += 1
        proc_block = next((b for b in inner if b.keyword in PROC_KW), None)
        proc = proc_block.keyword if proc_block else None
        explicit = proc == "DYNAMIC" and proc_block is not None and proc_block.has("EXPLICIT")
        params: "OrderedDict[str, Optional[str]]" = OrderedDict()
        for k, v in step_block.params.items():
            if k == "NAME":
                continue
            if k == "PERTURBATION":
                if proc == "FREQUENCY" and self._freq_storage:
                    # ccx's modal / steady-state dynamics refuses an .eig file written by a
                    # perturbation frequency step ('created with perturbation info')
                    if self._general_step_seen:
                        params[k] = v
                        self.report.warn("*FREQUENCY step with PERTURBATION after a general step: "
                                         "ccx's later modal / steady-state dynamics step refuses "
                                         "these (prestressed) eigenmodes — drop PERTURBATION to "
                                         "run it without the prestress.", once=True)
                    else:
                        self.report.note("*STEP, PERTURBATION dropped on the first *FREQUENCY step "
                                         "(no preload before it, so nothing changes; ccx's modal / "
                                         "steady-state dynamics step refuses perturbation "
                                         "eigenmodes).", once=True)
                elif proc in ("FREQUENCY", "BUCKLE"):
                    params[k] = v
                elif self._step_idx < self._n_steps:
                    self.report.warn("*STEP, PERTURBATION on a static step dropped: ccx runs it as a "
                                     "general step, so its loads persist into the following steps "
                                     "(an Abaqus perturbation leaves the base state untouched). Move "
                                     "the perturbation load case after the last general step or remove "
                                     "its loads in the next step (OP=NEW).", once=True)
                else:
                    self.report.note("*STEP PERTURBATION dropped (ccx allows it only for *FREQUENCY / "
                                     "*BUCKLE; a final perturbation *STATIC is an ordinary linear "
                                     "static step).", once=True)
                continue
            if k == "AMPLITUDE":
                if (v or "").strip().upper() in ("RAMP", "STEP"):
                    params[k] = v.strip().upper()
                else:
                    self.report.warn(f"*STEP AMPLITUDE={v}: ccx accepts only RAMP or STEP here; "
                                     f"dropped.", once=True)
                continue
            if k in ("NLGEOM", "INC", "INCF", "THERMAL NETWORK", "SHOCK SMOOTHING"):
                params[k] = v
                continue
            self.report.note(f"*STEP parameter {k} dropped (not a ccx *STEP parameter).", once=True)
        if explicit:
            # Abaqus/Explicit has no increment cap (it ignores INC=) and runs with NLGEOM on
            # by default; ccx caps a step at 100 increments and is linear by default
            try:
                inc = int(float(params.get("INC") or 0))
            except ValueError:
                inc = 0
            if inc < 10000000:
                params["INC"] = "10000000"
                self.report.note("Explicit *STEP: INC=10000000 set (Abaqus/Explicit has no "
                                 "increment limit and ignores INC=; ccx stops at 100 increments "
                                 "by default).", once=True)
            if "NLGEOM" not in params:
                params["NLGEOM"] = None
                self.report.note("Explicit *STEP: NLGEOM added (Abaqus/Explicit includes geometric "
                                 "nonlinearity by default; ccx does not).", once=True)
        if proc == "DYNAMIC" and proc_block is not None and "AMPLITUDE" not in params and \
                (proc_block.param("APPLICATION") or "").upper().startswith("QUASI"):
            params["AMPLITUDE"] = "RAMP"
            self.report.note("*DYNAMIC, APPLICATION=QUASI-STATIC: *STEP AMPLITUDE=RAMP added (the "
                             "Abaqus default for quasi-static dynamics; ccx steps loads in dynamic "
                             "steps by default).", once=True)
        if proc in ("STATIC", "DYNAMIC", "HEAT TRANSFER", "COUPLED TEMPERATURE-DISPLACEMENT",
                    "UNCOUPLED TEMPERATURE-DISPLACEMENT", "VISCO") and not step_block.has("PERTURBATION"):
            self._general_step_seen = True
        nl = params.get("NLGEOM", "")
        # NLGEOM stays on for all later steps once a step has switched it on (Abaqus)
        self._step_nlgeom = self._step_nlgeom or \
            ("NLGEOM" in params and (nl or "YES").strip().upper() != "NO")
        out = [emit_keyword("STEP", params)]
        self._nodal_fresh, self._nodal_reset, self._cload_new = set(), set(), False
        self._dl_fresh, self._dl_wiped = set(), False
        self._step_temp_dof = next((b.keyword for b in inner if b.keyword in TEMPERATURE_DOF_PROCS),
                                   None)
        for b in inner:
            if b.keyword == "END STEP" or b.keyword in GEOM_KW:
                continue
            out.extend(self.translate_one(b))
        out.extend(self._boundary_pieces(self._vel_tail.get(self._step_idx, [])))
        out.extend(self._flush_dloads())
        out.extend(self._flush_nodal_loads())
        out.extend(self._anchored_output(step_block))  # Abaqus' default output, if any
        self._step_temp_dof = None
        out.append("*END STEP")
        return out

    def _boundary_pieces(self, pieces: Sequence[object]) -> List[str]:
        """Emit planned output: text lines as they are, *BOUNDARY blocks through
        handle_boundary (so they get every treatment a deck's own BC gets)."""
        out: List[str] = []
        for p in pieces:
            out.extend(self.handle_boundary(p) if isinstance(p, Block) else [p])
        return out

    def handle_boundary(self, b: Block) -> List[str]:
        if self._bc_type(b) in self._RATE_TYPES and id(b) in self._vel_cards:   # _plan_velocity_bcs
            pieces = self._vel_cards[id(b)]
            if id(b) in self._op_new_drop:       # the card's OP=NEW goes with its first block
                for p in pieces:
                    if isinstance(p, Block) and p.has("OP"):
                        self._op_new_drop[id(p)] = self._op_new_drop[id(b)]
            return self._boundary_pieces(pieces)
        if b.has("USER"):
            return self._user_load_card(b)
        params: "OrderedDict[str, Optional[str]]" = OrderedDict()
        for k, v in b.params.items():
            if k == "TYPE":
                if v and v.upper() in ("VELOCITY", "ACCELERATION"):
                    self.report.warn(f"*BOUNDARY TYPE={v} is unsupported by ccx (displacement BCs "
                                     f"only); TYPE dropped — values now read as displacements.", once=True)
                continue  # ccx *BOUNDARY has no TYPE parameter
            if k == "LOAD CASE":
                # ccx hard-errors on LOAD CASE outside *STEADY STATE DYNAMICS
                self.report.warn("*BOUNDARY LOAD CASE dropped (ccx allows it only in steady-state "
                                 "dynamics; elsewhere it is a fatal error).", once=True)
                continue
            if k == "OP" and id(b) in self._op_new_drop:
                continue                # an OP=NEW that removes nothing (_plan_op_new_rotations)
            params[k] = v
        out = ["** [abq2ccx] OP=NEW dropped: this step re-specifies every boundary condition in "
               "effect (ccx 2.23 would not rebuild the shell/beam rotations after it)"] \
            if self._op_new_drop.get(id(b)) and (b.param("OP") or "").strip().upper() == "NEW" else []
        out.append(emit_keyword("BOUNDARY", params))
        midside = [ln.split(",") for ln in self._midside_records(b, "boundary")]
        # coupled member DOFs whose BC _plan_coupled_bcs removed are already gone here
        recs = self._bc_lines[id(b)] if id(b) in self._bc_lines else merged_data_records(b)
        for rec in recs + midside:
            # Interior blanks are positional (e.g. "node, dof1, , value" = blank last
            # DOF), so trim only trailing empties — never filter interior fields.
            g = [x.strip() for x in rec]
            while g and g[-1] == "":
                g.pop()
            if not g:
                continue
            spec, rest = g[0], g[1:]
            self._check_node_target("BOUNDARY", spec)
            if rest and rest[0] and not re.fullmatch(r"[-+]?\d+", rest[0]):
                dofs = self._named_bc_dofs(rest[0], self._named_bc_rot(spec))
                if dofs is None:
                    self.report.warn(f"*BOUNDARY type '{rest[0]}' not recognised; line passed through.", once=True)
                    out.append(", ".join(g))
                else:
                    for d1, d2 in dofs:
                        kept = self._active_dof_lines(spec, d1, d2, [])
                        out.extend(kept if kept is not None else [f"{spec}, {d1}, {d2}"])
            elif len(rest) >= 2:
                # node, first-dof, last-dof[, magnitude]; blank last-dof means = first
                dof2 = rest[1] if rest[1] != "" else rest[0]
                kept = None
                if re.fullmatch(r"[-+]?\d+", rest[0]) and re.fullmatch(r"[-+]?\d+", dof2):
                    kept = self._active_dof_lines(spec, int(rest[0]), int(dof2), rest[2:])
                out.extend(kept if kept is not None else [", ".join([spec, rest[0], dof2] + rest[2:])])
            elif len(rest) == 1 and re.fullmatch(r"[-+]?\d+", rest[0]):
                kept = self._active_dof_lines(spec, int(rest[0]), int(rest[0]), [])
                out.extend(kept if kept is not None else [", ".join(g)])
            else:
                out.append(", ".join(g))
        if getattr(self, "_n_inactive_rot", 0):
            self.report.warn("Rotational DOFs (4-6) prescribed on nodes that only belong to plane-"
                             "stress/plane-strain/axisymmetric elements were dropped: those nodes "
                             "have no rotations (Abaqus ignores such BCs with a warning), but ccx "
                             "treats them as rotational constraints and 2.23 crashes (bus error) or "
                             "stops in usermpc.", once=True)
        if self._planar_bc and (params.get("OP") or "").strip().upper() == "NEW":
            # OP=NEW also removes the model-data planar constraint (verified on 2.23)
            out += ["** [abq2ccx] planar constraint re-applied (OP=NEW removed it)"] + self._planar_bc
        if self._conn_bcs and (params.get("OP") or "").strip().upper() == "NEW":
            out += self._conn_bcs
            self.report.note("*BOUNDARY, OP=NEW: the boundary conditions that hold converted "
                             "connectors are repeated after it (OP=NEW removes every earlier BC "
                             "in ccx, model data included; probed), as a connector holds in every "
                             "step.", once=True)
        return out

    def _check_node_target(self, kw: str, spec: str) -> None:
        """Warn when a BC/load names a node set the deck never defines (ccx stops with
        '... node set X has not yet been defined')."""
        if not spec or re.fullmatch(r"[-+]?\d+", spec) or spec.upper() in self.geom.nsets:
            return
        if spec.upper() in self.surfaces:
            self.report.warn(f"*{kw} on '{spec}', which is a *SURFACE, not a node set — ccx needs "
                             f"a node set here; define an *NSET with the surface's nodes.", once=True)
        else:
            self.report.warn(f"*{kw} references node set '{spec}', which the deck never defines "
                             f"(incomplete export?); ccx stops with 'node set {spec.upper()} has not "
                             f"yet been defined'.", once=True)

    def _active_dof_lines(self, spec: str, d1: int, d2: int, extra: List[str]) -> Optional[List[str]]:
        """BC data lines for DOFs d1..d2 on ``spec`` with the rotational DOFs (4-6) moved or
        removed where ccx needs it, or None when the line can stay as it is:

        * rotations of a rigid-body reference node go to DOFs 1-3 of its ROT NODE (ccx
          ignores DOFs 4-6 of the REF NODE), which has the reference node's local axes if it
          has a *TRANSFORM (_plan_rot_axes);
        * nodes that only belong to plane/axisymmetric continuum elements have no
          rotations — those DOFs are dropped (a set mixing them with shell/beam nodes keeps
          its rotations on the latter, one line per node)."""
        def line(target: str, a: int, b: int) -> str:
            return ", ".join([target, str(a), str(b)] + extra)
        lo, hi = min(d1, d2), max(d1, d2)
        if hi < 4 or lo > 6:
            return None
        nodes = self._resolve_nodes(spec)
        refs = [n for n in nodes if n in self._rb_rot]
        if refs:
            out = [line(spec, lo, min(hi, 3))] if lo <= 3 and len(refs) == len(nodes) else \
                  ([] if len(refs) == len(nodes) else [line(spec, d1, d2)])
            if hi >= 7 and len(refs) == len(nodes):
                out.append(line(spec, 7, hi))
            try:                                  # zero on all of 4-6: the same in any axes
                held = lo <= 4 and hi >= 6 and (not extra or not extra[0] or pf(extra[0]) == 0.0)
            except ValueError:
                held = False
            for n in refs:
                out.append(line(str(self._rb_rot[n]), max(lo, 4) - 3, min(hi, 6) - 3))
                if not held:
                    self._warn_rot_frame(n)
            self.report.note("Rotational BCs on a *RIGID BODY reference point moved to DOFs 1-3 "
                             "of its ROT NODE (ccx ignores DOFs 4-6 of the REF NODE).", once=True)
            return out
        if not self._plane_only:
            return None
        flat = [n for n in nodes if n in self._plane_only]
        if not nodes or not flat:
            return None
        self._n_inactive_rot += len(flat)
        out: List[str] = []
        if lo <= 3:
            out.append(line(spec, lo, 3))
        if hi >= 7:
            out.append(line(spec, 7, hi))
        for n in nodes:
            if n not in self._plane_only:
                out.append(line(str(n), max(lo, 4), min(hi, 6)))
        return out

    def _named_bc_rot(self, spec: str) -> bool:
        """Whether a named BC (ENCASTRE, XSYMM, ...) on ``spec`` includes rotations: in a model
        with rotational DOFs, and on a reference point even in a solid-only model."""
        return self.has_rotational_dof or (not getattr(self.opt, "solid_dof", False) and
                                           any(n in self._ref_nodes for n in self._resolve_nodes(spec)))

    def _named_bc_dofs(self, name: str, rot: Optional[bool] = None) -> Optional[List[Tuple[int, int]]]:
        if rot is None:
            rot = self.has_rotational_dof
        name = name.upper()
        table = {
            "ENCASTRE": [(1, 6)] if rot else [(1, 3)],
            "PINNED": [(1, 3)],
            "XSYMM": [(1, 1), (5, 6)] if rot else [(1, 1)],
            "YSYMM": [(2, 2), (4, 4), (6, 6)] if rot else [(2, 2)],
            "ZSYMM": [(3, 3), (4, 5)] if rot else [(3, 3)],
            "XASYMM": [(2, 3), (4, 4)] if rot else [(2, 3)],
            "YASYMM": [(1, 1), (3, 3), (5, 5)] if rot else [(1, 1), (3, 3)],
            "ZASYMM": [(1, 2), (6, 6)] if rot else [(1, 2)],
        }
        return table.get(name)

    # -- velocity / acceleration boundary conditions -------------------------------
    _RATE_TYPES = ("VELOCITY", "ACCELERATION")
    # linear perturbation procedures: the base state does not move, BCs only constrain
    _PERTURBATION_PROCS = {"FREQUENCY", "BUCKLE", "STEADY STATE DYNAMICS", "MODAL DYNAMIC",
                           "COMPLEX FREQUENCY", "RANDOM RESPONSE", "RESPONSE SPECTRUM",
                           "SUBSTRUCTURE GENERATE", "MATRIX GENERATE"}
    # procedures that move nodes over a time period given as the 2nd field of their data line
    _MOTION_PROCS = {"STATIC", "DYNAMIC", "VISCO", "COUPLED TEMPERATURE-DISPLACEMENT",
                     "UNCOUPLED TEMPERATURE-DISPLACEMENT", "SOILS", "GEOSTATIC"}

    @staticmethod
    def _bc_type(b: Block) -> str:
        return (b.param("TYPE") or "DISPLACEMENT").strip().upper()

    def _rate_lines(self, b: Block) -> List[Tuple[str, List[int], str, Optional[str], str]]:
        """(node spec, DOFs, magnitude text, named type, line text) of each data line of
        *BOUNDARY ``b`` as it will be emitted (after _plan_coupled_bcs's rewrite of the card,
        if any).  DOFs are [] where the line names none the converter can read (a blank
        first DOF, an unknown type); a named type covers DOFs 4-6 where handle_boundary
        expands it so (_named_bc_rot)."""
        out = []
        for rec in self._bc_lines.get(id(b)) or merged_data_records(b):
            g = [x.strip() for x in rec]
            while g and g[-1] == "":
                g.pop()
            if len(g) < 2 or not g[0]:
                continue
            text = ", ".join(g)
            if re.fullmatch(r"[-+]?\d+", g[1]):
                d1 = int(g[1])
                d2 = int(g[2]) if len(g) > 2 and re.fullmatch(r"[-+]?\d+", g[2]) else d1
                out.append((g[0], list(range(min(d1, d2), max(d1, d2) + 1)),
                            g[3] if len(g) > 3 else "", None, text))
            elif g[1]:
                dofs = [d for a, c in (self._named_bc_dofs(g[1], self._named_bc_rot(g[0])) or [])
                        for d in range(a, c + 1)]
                out.append((g[0], dofs, "", g[1] if dofs else None, text))
            else:
                out.append((g[0], [], "", None, text))
        return out

    def _step_motion(self, group: List[Block], nlgeom: bool) -> dict:
        """What the velocity-BC plan needs to know of a step: the time period over which its
        nodes move (None for Riks, heat transfer, a linear perturbation, ...), the time it
        adds to the total time (0 for a perturbation step, None when unknown), the default
        amplitude of its velocity and acceleration BCs, and whether it is dynamic /
        explicit / under NLGEOM."""
        step_b = group[0]
        proc_b = next((x for x in group[1:] if x.keyword in PROC_KW or
                       x.keyword in self._MOTION_PROCS), None)
        proc = proc_b.keyword if proc_b is not None else ""
        explicit = proc == "DYNAMIC" and proc_b.has("EXPLICIT")
        perturbation = step_b.has("PERTURBATION") or proc in self._PERTURBATION_PROCS
        period = None
        advance: Optional[float] = 0.0 if perturbation else None
        if (proc in self._MOTION_PROCS or proc == "HEAT TRANSFER") and not proc_b.has("RIKS") \
                and not perturbation:
            rec = (merged_data_records(proc_b) or [[]])[0]
            try:
                advance = pf(rec[1]) if len(rec) > 1 and rec[1] else 1.0     # Abaqus default 1
            except ValueError:
                advance = None
            if advance is not None and not advance > 0.0:
                advance = None
            if proc != "HEAT TRANSFER":
                period = advance
        # the default amplitude of loads and BCs (Abaqus manual, "Defining an analysis",
        # Table 1): STEP in Abaqus/Explicit and in transient procedures, RAMP in static and
        # steady-state ones; *STEP AMPLITUDE overrides it in Abaqus/Standard
        quasi = proc == "DYNAMIC" and \
            (proc_b.param("APPLICATION") or "").strip().upper().startswith("QUASI")
        default = (step_b.param("AMPLITUDE") or "").strip().upper()
        if explicit:
            default = "STEP"
        elif default not in ("RAMP", "STEP"):
            if proc == "DYNAMIC":
                transient = not quasi
            elif proc.endswith("TEMPERATURE-DISPLACEMENT"):
                transient = not proc_b.has("STEADY STATE")
            elif proc == "SOILS":
                transient = proc_b.has("CONSOLIDATION")
            else:
                transient = proc == "VISCO"            # the table's "quasi-static": STEP too
            default = "STEP" if transient else "RAMP"
        # *BOUNDARY, AMPLITUDE: "when displacement or rotation components in a static step or
        # in a dynamic step with APPLICATION=QUASI-STATIC are given with TYPE=VELOCITY, ...
        # the default is always a STEP function"
        static = proc in ("STATIC", "GEOSTATIC")
        defaults = {"VELOCITY": "STEP" if static or quasi else default, "ACCELERATION": default}
        if step_b.has("NLGEOM"):
            nlgeom = nlgeom or (step_b.param("NLGEOM") or "YES").strip().upper() != "NO"
        return dict(period=period, advance=advance, defaults=defaults, dynamic=proc == "DYNAMIC",
                    explicit=explicit, perturbation=perturbation, nlgeom=nlgeom or explicit,
                    proc=(proc + (", RIKS" if proc_b.has("RIKS") else "")) if proc else "(no procedure)")

    @staticmethod
    def _bc_history(bc: dict, period: float, t0: Optional[float], u_start: Optional[float],
                    prev: float):
        """(value(t), breaks, panel) of the quantity a tracked BC prescribes over a step
        (t in step time, t0 the total time at the step start), or None if not known."""
        mode = bc["mode"]
        if mode == "AMP":
            c = bc["curve"]
            if c.total and t0 is None:
                return None
            off = t0 if c.total else 0.0
            k = 1.0 if c.absolute else bc["mag"]
            return (lambda t: k * c.value(off + t)), [x - off for x in c.breaks], c.panel
        if mode in ("STEP", "HOLD"):
            v = bc["mag"] if mode == "STEP" else bc["hold"]
            return (lambda t: v), [], 0.0
        if mode == "RAMP":
            m = bc["mag"]
            return (lambda t: prev + (m - prev) * t / period), [], 0.0
        if mode == "FIXED" and u_start is not None:
            return (lambda t: u_start), [], 0.0
        return None

    def _plan_velocity_bcs(self, blocks: List[Block]) -> None:
        """*BOUNDARY, TYPE=VELOCITY / ACCELERATION -> displacement BCs: ccx prescribes
        displacements only (its *BOUNDARY has no TYPE).

        The DOF moves by the time integral of the prescribed velocity (an acceleration:
        twice, from the velocity at the step start) from the displacement it has at the
        start of the step, so the converted BC is a displacement BC whose generated
        amplitude is that integral: exact at its points, straight between them like any ccx
        amplitude (integrate_history keeps that within 1e-4 of the step's travel; a
        constant or piecewise-constant rate is exact).  The rate is the magnitude times the
        amplitude (VALUE=ABSOLUTE: the amplitude alone; TIME=TOTAL TIME on total time) or,
        without AMPLITUDE, the Abaqus default (_step_motion): a velocity is held over a
        static or quasi-static step (STEP); anything else follows the step's default
        amplitude, where a RAMP starts from the value at the end of the previous step (a
        velocity in a dynamic step: from the DOF's velocity).  A rate BC a later step keeps
        (no OP=NEW, not re-specified) keeps moving the DOF in Abaqus - at the rate it ended
        with, or along a TOTAL TIME amplitude - while a ccx BC with a step-time amplitude
        stays at its last value (manual, *AMPLITUDE), so that step gets the continued motion
        before its *END STEP (_vel_tail).  The start displacement and velocity of each DOF are
        followed through the steps; where the displacement is unknown (the DOF was free, or
        held by a USER / SUBMODEL BC) a zero rate becomes *BOUNDARY, FIXED (probed: holds
        the value the previous step ended with) and any other rate cannot be converted.
        The midside node of an upgraded 2-node beam whose end nodes a card drives gets the
        mean of their motions, which is what the Abaqus element sees between them."""
        self._vel_cards = {}
        self._vel_tail = {}
        self._vel_only_amps = set()
        rate_cards = [b for b in blocks if b.keyword == "BOUNDARY" and self._bc_type(b) in self._RATE_TYPES]
        if not rate_cards:
            return
        curves: Dict[str, Optional[AmplitudeCurve]] = {}
        for b in blocks:
            if b.keyword == "AMPLITUDE" and b.param("NAME"):
                curves[b.param("NAME").strip().upper()] = amplitude_curve(b)
        # amplitudes no other card names (any parameter, e.g. FILM AMPLITUDE=, or data field)
        named_amps = {(b.param("AMPLITUDE") or "").strip().upper() for b in rate_cards} - {""}
        others: set = set()
        for b in blocks:
            if b.keyword == "AMPLITUDE" or b.keyword in GEOM_KW:
                continue
            rate = b.keyword == "BOUNDARY" and self._bc_type(b) in self._RATE_TYPES
            others.update(v.strip().upper() for k, v in b.params.items()
                          if v and not (k == "AMPLITUDE" and (rate or b.keyword == "STEP")))
            others.update(x.upper() for rec in merged_data_records(b) for x in rec if x)
        self._vel_only_amps = named_amps - others
        tracked: set = set()
        for b in rate_cards:
            for spec, dofs, _, _, _ in self._rate_lines(b):
                tracked.update((n, d) for n in self._resolve_nodes(spec) for d in dofs if 1 <= d <= 6)
        v_init: Dict[Tuple[int, int], Optional[float]] = {}
        for b in blocks:
            typ = (b.param("TYPE") or "").strip().upper() if b.keyword == "INITIAL CONDITIONS" else ""
            for rec in merged_data_records(b) if typ in ("VELOCITY", "ROTATING VELOCITY") else []:
                try:
                    val = (int(rec[1]), pf(rec[2])) if typ == "VELOCITY" else None
                except (IndexError, ValueError):
                    continue
                for n in self._resolve_nodes(rec[0]) if rec else []:
                    if val is None:                    # rotating: not followed
                        v_init.update(((n, d), None) for d in range(1, 7))
                    else:
                        v_init[(n, val[0])] = val[1]
        # per tracked DOF: [displacement, velocity, BC in force] (None: unknown / free)
        state = {k: [0.0, v_init.get(k, 0.0), None] for k in tracked}
        model: List[Block] = []
        groups: List[List[Block]] = []
        i = 0
        while i < len(blocks):                       # the step grouping of emit_other
            if blocks[i].keyword == "STEP":
                j, group = i, []
                while j < len(blocks):
                    group.append(blocks[j])
                    if blocks[j].keyword == "END STEP":
                        break
                    j += 1
                groups.append(group)
                i = j + 1
                continue
            if blocks[i].keyword == "BOUNDARY" and not groups:
                model.append(blocks[i])
            i += 1
        names = {"VELOCITY": "VEL", "ACCELERATION": "ACC"}
        stats = {"dev": 0.0, "n": 0}
        max_points = 1000

        def amp_card(pts: List[Tuple[float, float]], q: str) -> Tuple[str, List[str]]:
            self._vel_amp_count += 1
            name = f"ABQ2CCX_{names[q]}{self._vel_amp_count}"
            toks = [f"{t:.12g}, {x:.12g}" for t, x in pts]
            return name, [f"*AMPLITUDE, NAME={name}"] + [", ".join(toks[i:i + 4])
                                                         for i in range(0, len(toks), 4)]

        def runs(ds: Sequence[int]) -> List[Tuple[int, int]]:
            """Contiguous runs of sorted DOFs."""
            out: List[Tuple[int, int]] = []
            for d in ds:
                if out and out[-1][1] == d - 1:
                    out[-1] = (out[-1][0], d)
                else:
                    out.append((d, d))
            return out

        def lines(spec: str, dofs: List[int], members: List[Tuple[int, int]], value: str,
                  named: Optional[str] = None) -> List[str]:
            """Data lines for ``members`` of a line on spec x dofs: on the spec itself (its
            named type, when it is all of it and has no value) when they are some DOFs of
            all its nodes, else per node; DOFs as contiguous runs."""
            tail = [value] if value else []
            nodes = self._resolve_nodes(spec)
            sub = sorted({d for _, d in members})
            if not nodes or set(members) == {(n, d) for n in nodes for d in sub}:
                if named and sub == sorted(dofs) and not value:
                    return [f"{spec}, {named}"]
                return [", ".join([spec, str(a), str(c)] + tail) for a, c in runs(sub or dofs)]
            out = []
            for n in dedup([n for n, _ in members]):
                out += [", ".join([str(n), str(a), str(c)] + tail)
                        for a, c in runs(sorted(d for m, d in members if m == n))]
            return out

        def pieces(op: Optional[str], amp_lines: List[str], entries: List[Tuple[object, str]],
                   notes: List[str]) -> List[object]:
            """The generated amplitudes, then one *BOUNDARY per run of lines of one kind
            (line order kept: a later line overrides an earlier one on the same DOF)."""
            out: List[object] = list(notes) + list(amp_lines)
            for sig, text in entries:
                if sig == "#":
                    out.append(text)
                    continue
                if out and isinstance(out[-1], Block) and getattr(out[-1], "_sig", None) == sig:
                    out[-1].data.append(text)
                    continue
                params = []
                if op and not any(isinstance(p, Block) for p in out):
                    params.append(("OP", op))
                if sig == "FIXED":
                    params.append(("FIXED", None))
                elif sig is not None:
                    params.append(("AMPLITUDE", sig))
                blk = mkblock("BOUNDARY", params, [text])
                blk._sig = sig
                out.append(blk)
            if op and not any(isinstance(p, Block) for p in out):
                out.append(mkblock("BOUNDARY", [("OP", op)], []))     # it still removes BCs
            return out

        def comment(what: str, why: str) -> Tuple[str, str]:
            self.report.warn(why, once=True)
            return ("#", f"** [abq2ccx] not converted: {what} -- {why}")

        def constraint_card(b: Block, why: str) -> List[object]:
            """A rate card where only its constraint can be kept (model data, perturbation)."""
            entries = []
            for spec, dofs, mag, named, text in self._rate_lines(b):
                try:
                    nonzero = bool(mag) and pf(mag) != 0.0
                except ValueError:
                    nonzero = True
                if not dofs or nonzero:
                    entries.append(comment(text, f"*BOUNDARY, TYPE={self._bc_type(b)} {why}: "
                                                 f"only a zero value on readable DOFs can be "
                                                 f"converted (to a zero displacement BC)."))
                else:
                    entries.append((None, f"{spec}, {named}" if named else
                                    f"{spec}, {dofs[0]}, {dofs[-1]}"))
            self.report.note(f"*BOUNDARY, TYPE=VELOCITY/ACCELERATION {why}: zero-valued, so "
                             f"converted to the zero displacement BC it amounts to.", once=True)
            return pieces(b.param("OP"), [], entries, [])

        for b in model:
            if self._bc_type(b) in self._RATE_TYPES:
                self._vel_cards[id(b)] = constraint_card(b, "in model data")
            for spec, dofs, mag, _, _ in self._rate_lines(b):      # held from the first step on
                try:
                    value = pf(mag) if mag and self._bc_type(b) not in self._RATE_TYPES else 0.0
                except ValueError:
                    value = 0.0
                bc = dict(q="DISPLACEMENT", mode="STEP", mag=value, end=value)
                for k in ((n, d) for n in self._resolve_nodes(spec) for d in dofs):
                    if k in state:
                        state[k][2] = bc
        t0: Optional[float] = 0.0                # total time at the step start (None: unknown)
        nlgeom = False
        for s, group in enumerate(groups, 1):
            info = self._step_motion(group, nlgeom)
            nlgeom = info["nlgeom"]
            T = info["period"]
            cards = [x for x in group[1:] if x.keyword == "BOUNDARY"]
            if T is None:
                why = ("in a linear perturbation step (the base state does not move; only the "
                       "constraint applies)" if info["perturbation"] else
                       f"in a {info['proc']} step (no time period over which to integrate it)")
                for b in cards:
                    if self._bc_type(b) in self._RATE_TYPES:
                        self._vel_cards[id(b)] = constraint_card(b, why)
                if not info["perturbation"] and info["proc"] != "HEAT TRANSFER":
                    for st in state.values():          # nodes moved, by unknown amounts
                        st[0] = st[1] = None
                t0 = None if t0 is None or info["advance"] is None else t0 + info["advance"]
                continue
            start = {k: (st[0], st[1]) for k, st in state.items()}
            prev_bc = {k: st[2] for k, st in state.items()}
            # where a RAMP starts: the value the DOF's earlier BC of that type ended with
            # (read before this step's end values overwrite a carried BC's)
            prev_end = {k: (pb["q"], pb.get("end")) for k, pb in prev_bc.items() if pb}
            op_new = any((b.param("OP") or "").strip().upper() == "NEW" for b in cards)
            if op_new:
                for st in state.values():
                    st[2] = None
            memo: Dict[tuple, Tuple[dict, object]] = {}

            def motion(bc: dict, u_s: Optional[float], v_s: Optional[float], prev: float):
                """integrate_history of the DOF under rate BC bc from (u_s, v_s), or None."""
                key = (id(bc), u_s, v_s, prev)
                if key not in memo:          # the entry keeps bc alive: no other dict gets its id
                    h = self._bc_history(bc, T, t0, None, prev)
                    order = 2 if bc["q"] == "ACCELERATION" else 1
                    memo[key] = (bc, None if h is None or u_s is None or (order == 2 and v_s is None)
                                 or too_fast(h) else
                                 integrate_history(h[0], h[1], T, order, u_s, v_s or 0.0, h[2],
                                                   max_points=max_points))
                return memo[key][1]

            def too_fast(h) -> bool:
                """More than a thousand oscillations in the step: no sampled amplitude can
                follow them (integrate_history caps its points)."""
                return h[2] > 0.0 and T / h[2] > 8 * max_points

            def prev_rate(k: Tuple[int, int], bc: dict) -> float:
                """Where a RAMP of bc on DOF k starts: in a dynamic step a velocity starts from
                the DOF's velocity at the step start (Abaqus Verification Guide, boundary
                condition types: "linear from the previous value at the end of the first
                step"), anything else from the value the DOF's earlier BC of its type ended
                with (0 without one)."""
                if bc["mode"] != "RAMP":
                    return 0.0
                u_s, v_s = start.get(k, (None, None))
                if info["dynamic"] and bc["q"] == "VELOCITY":
                    if v_s is not None:
                        return v_s
                    if u_s is not None:          # (else the BC cannot be converted anyway)
                        self.report.warn("*BOUNDARY, TYPE=VELOCITY ramped (no AMPLITUDE, *STEP "
                                         "AMPLITUDE=RAMP) in a dynamic step on a DOF whose velocity "
                                         "at the step start the converter does not know (a "
                                         "displacement BC or a static step moved it): Abaqus ramps "
                                         "from that velocity; taken as the DOF's earlier velocity "
                                         "BC value (0 without one).", once=True)
                pe = prev_end.get(k)
                return (pe[1] or 0.0) if pe and pe[0] == bc["q"] else 0.0

            def convert(bc: dict, keys: List[Tuple[int, int]], shapes: Dict[tuple, str],
                        amp_lines: List[str], entries: list, driven: dict) -> None:
                """Entries for the DOFs ``keys`` of a line under rate BC ``bc``."""
                q, order = bc["q"], 2 if bc["q"] == "ACCELERATION" else 1
                spec, dofs, named, text = bc["spec"], bc["dofs"], bc.get("named"), bc["text"]
                if bc["mode"] == "UNKNOWN":
                    entries.append(comment(text, f"*BOUNDARY, TYPE={q} with AMPLITUDE={bc['amp']}: "
                                                 f"that amplitude is not one the converter can "
                                                 f"integrate (TABULAR, EQUALLY SPACED, SMOOTH STEP, "
                                                 f"PERIODIC, MODULATED, DECAY)."))
                    return
                if bc["mode"] == "AMP" and bc["curve"].total and t0 is None:
                    entries.append(comment(text, f"*BOUNDARY, TYPE={q} with a TIME=TOTAL TIME "
                                                 f"amplitude after a step whose time period is "
                                                 f"unknown (Riks, or no procedure)."))
                    return
                if bc["mode"] == "AMP" and too_fast((None, None, bc["curve"].panel)):
                    entries.append(comment(text, f"*BOUNDARY, TYPE={q} whose amplitude oscillates "
                                                 f"over a thousand times in the step: too fast for "
                                                 f"a sampled displacement amplitude."))
                    return
                c = bc.get("curve")
                if bc["mode"] == "AMP" and q == "VELOCITY" and info["dynamic"]:
                    # *BOUNDARY: "In an Abaqus/Standard dynamic ... procedure, amplitude curves
                    # specified for ... TYPE=VELOCITY will be smoothed automatically"
                    off = t0 if c.total else 0.0
                    frac = c.smooth if c.smooth is not None else 0.0 if info["explicit"] else 0.25
                    if frac > 0.0 and any(off < x < off + T for x in c.corners):
                        self.report.warn(f"*BOUNDARY, TYPE=VELOCITY with a TABULAR amplitude in a "
                                         f"dynamic step: Abaqus replaces the curve around each of "
                                         f"its points by a quadratic (SMOOTH={frac:g}) so that the "
                                         f"acceleration stays finite, while the converter integrates "
                                         f"the piecewise-linear curve: the displacement can differ by "
                                         f"up to the change of slope x (SMOOTH x the time interval)^2 "
                                         f"/ 6 per point. Give the amplitude SMOOTH=0 in the Abaqus "
                                         f"deck to compare like with like.", once=True)
                groups_: "OrderedDict[tuple, List[Tuple[int, int]]]" = OrderedDict()
                for k in keys:
                    u_s, v_s = start.get(k, (0.0, 0.0))
                    groups_.setdefault((u_s, v_s if order == 2 else 0.0, prev_rate(k, bc)), []).append(k)
                if not keys:                           # unresolved set: ccx will say so
                    groups_[(0.0, 0.0, 0.0)] = []
                for (u_s, v_s, prev), members in groups_.items():
                    members = members or [(0, d) for d in dofs]
                    if u_s is None or v_s is None:
                        still = None if v_s is None else motion(bc, 0.0, v_s, prev)
                        if still is None or any(x != 0.0 for _, x in still[0]):
                            entries.append(comment(text, f"*BOUNDARY, TYPE={q} on a DOF whose "
                                                         f"displacement at the start of the step is "
                                                         f"unknown (it was free, or held by a "
                                                         f"USER/SUBMODEL BC, before): ccx prescribes "
                                                         f"total displacements only."))
                            continue
                        # a zero rate holds the DOF where the step finds it: FIXED takes the
                        # translations (and a rigid body's rotations, which go to its ROT
                        # NODE's translations); a solid node has no DOFs 4-6 to hold
                        fix = [(n, d) for n, d in members if d <= 3 or n in self._rb_rot]
                        rotating = [(n, d) for n, d in members
                                    if (n, d) not in fix and n in self._rot_nodes]
                        if fix:
                            entries += [("FIXED", ln) for ln in lines(spec, dofs, fix, "")]
                        if rotating:
                            entries.append(comment(
                                f"{spec}, DOF {', '.join(map(str, sorted({d for _, d in rotating})))}",
                                f"*BOUNDARY, TYPE={q}: a zero rate on a shell/beam rotation whose "
                                f"value at the start of the step is unknown (ccx's *BOUNDARY, "
                                f"FIXED takes no rotations)."))
                        continue
                    pts, _, _, dev = motion(bc, u_s, v_s, prev)
                    travel = max(abs(x - u_s) for _, x in pts)
                    if travel == 0.0:
                        value = "%.12g" % u_s if u_s else ""
                        entries += [(None, ln) for ln in lines(spec, dofs, members, value, named)]
                        driven.update((k, (bc, u_s, v_s, prev, None, value or "0")) for k in members)
                        continue
                    stats["dev"] = max(stats["dev"], dev / travel)
                    stats["n"] += 1
                    absolute = bc["mode"] == "AMP" and bc["curve"].absolute
                    hold = (bc.get("hold"), bc["mag"]) if bc["mode"] == "HOLD" else None
                    if u_s == 0.0 and v_s == 0.0 and prev == 0.0 and bc["mag"] and not absolute:
                        key, value = (q, bc["mode"], bc.get("amp"), hold), "%.12g" % bc["mag"]
                        scale = bc["mag"]              # motion per unit magnitude, shared
                    else:                              # the motion itself, shared if identical
                        key, value = (q, bc["mode"], bc.get("amp"), hold, bc["mag"], absolute,
                                      u_s, v_s, prev), "1."
                        scale = 1.0
                    if key not in shapes:
                        shapes[key], text_ = amp_card([(t, x / scale) for t, x in pts], q)
                        amp_lines += text_
                    entries += [(shapes[key], ln) for ln in lines(spec, dofs, members, value)]
                    driven.update((k, (bc, u_s, v_s, prev, shapes[key], value)) for k in members)
                    if info["dynamic"] and order == 1:
                        f0 = self._bc_history(bc, T, t0, None, prev)[0](0.0)
                        if abs(f0 - (start.get(members[0], (0.0, 0.0))[1] or 0.0)) > 1e-12 * abs(f0):
                            self.report.note("*BOUNDARY, TYPE=VELOCITY with a jump in velocity at the "
                                             "start of a dynamic step: ccx derives the driven node's "
                                             "velocity from its prescribed displacement, so that "
                                             "node's own velocity output oscillates for a while "
                                             "after the jump (it decays); the motion it imposes and "
                                             "the rest of the model are unaffected (probed on "
                                             "2.23).", once=True)
                    if any(n in self._transformed and (d <= 3 or n not in self._rb_rot)
                           for n, d in members):
                        self.report.warn("*BOUNDARY, TYPE=VELOCITY/ACCELERATION on a node with a "
                                         "*TRANSFORM: ccx allows only one amplitude for all DOFs of "
                                         "such a node; check its other BCs.", once=True)

            def mean_entry(ea: tuple, ec: tuple, m: int, d: int, shapes: Dict[tuple, str],
                           amp_lines: List[str]) -> Optional[Tuple[object, str]]:
                """The line that moves midside node m with the mean of the motions of its
                end nodes (entries ``ea``/``ec`` of a driven map), or None (a velocity and an
                acceleration end)."""
                if ea[4] == ec[4]:                 # one amplitude (or none): mean of the values
                    return (ea[4], f"{m}, {d}, {d}, {(pf(ea[5]) + pf(ec[5])) / 2.0:.12g}")
                orders = {e[0]["q"] for e in (ea, ec) if e[4] is not None}
                if len(orders) > 1:
                    return None
                order = 2 if orders == {"ACCELERATION"} else 1
                rates = [(self._bc_history(e[0], T, t0, None, e[3]) if e[4] is not None else None)
                         or ((lambda t: 0.0), [], 0.0) for e in (ea, ec)]
                pts, _, _, _ = integrate_history(
                    lambda t: 0.5 * (rates[0][0](t) + rates[1][0](t)), list(rates[0][1]) +
                    list(rates[1][1]), T, order, (ea[1] + ec[1]) / 2.0,
                    ((ea[2] or 0.0) + (ec[2] or 0.0)) / 2.0,
                    min([h[2] for h in rates if h[2] > 0.0], default=0.0), max_points=max_points)
                key = ("midside", m, d, ea[4], ec[4], ea[5], ec[5])
                if key not in shapes:
                    shapes[key], text_ = amp_card(pts, "ACCELERATION" if order == 2 else "VELOCITY")
                    amp_lines += text_
                return (shapes[key], f"{m}, {d}, {d}, 1.")

            def midside(driven: dict, shapes: Dict[tuple, str], amp_lines: List[str],
                        entries: list, done: set) -> None:
                """The midside node of an upgraded 2-node beam whose end nodes these lines
                drive moves with the mean of their motions, which is what the Abaqus element
                sees between them (handle_boundary interpolates only within one *BOUNDARY
                block, and the end nodes may get different amplitudes)."""
                for a, c, m in self._midside.values():
                    for d in range(1, 7):
                        ea, ec = driven.get((a, d)), driven.get((c, d))
                        if ea and ec and (m, d) not in driven:
                            e = mean_entry(ea, ec, m, d, shapes, amp_lines)
                            if e is not None:
                                entries.append(e)
                                done.add((m, d))

            redefined: set = set()
            shapes: Dict[tuple, str] = {}
            step_driven: dict = {}                 # every DOF a rate BC moves in this step
            mid_done: set = set()
            for b in cards:
                q = self._bc_type(b)
                amp = (b.param("AMPLITUDE") or "").strip()
                curve = curves.get(amp.upper()) if amp else None
                rate = q in self._RATE_TYPES
                amp_lines: List[str] = []
                entries: list = []
                driven: dict = {}
                for spec, dofs, mag_txt, named, text in self._rate_lines(b):
                    keys = [(n, d) for n in self._resolve_nodes(spec) for d in dofs if (n, d) in state]
                    try:
                        mag: Optional[float] = pf(mag_txt) if mag_txt else 0.0
                    except ValueError:
                        mag = None
                    if not rate:
                        mode = "UNKNOWN" if mag is None or b.has("USER") or b.has("SUBMODEL") else \
                            "FIXED" if b.has("FIXED") else ("AMP" if curve else "UNKNOWN") if amp \
                            else "STEP"
                        bc = dict(q="DISPLACEMENT", mode=mode, mag=mag or 0.0, curve=curve)
                    else:
                        bad = mag is None or b.has("USER") or not dofs or \
                            any(not 1 <= d <= 6 for d in dofs)
                        if bad:
                            entries.append(comment(text, f"*BOUNDARY, TYPE={q}: only constant "
                                                         f"magnitudes on DOFs 1-6 or a known named "
                                                         f"type (no USER) can be integrated into "
                                                         f"displacements."))
                            mode = "UNKNOWN"
                        elif named:
                            mode, mag = "STEP", 0.0
                        else:
                            mode = ("AMP" if curve else "UNKNOWN") if amp else info["defaults"][q]
                        bc = dict(q=q, mode=mode, mag=mag or 0.0, curve=curve, amp=amp or None,
                                  spec=spec, dofs=dofs, named=named, text=text)
                        if mode == "RAMP" and (mag or any(prev_rate(k, bc) for k in keys)):
                            self.report.note(f"*BOUNDARY, TYPE={q} without AMPLITUDE in a "
                                             f"{info['proc']} step whose default amplitude is RAMP "
                                             f"(*STEP AMPLITUDE, or the procedure's default): the "
                                             f"{q.lower()} ramps over the step to the given one from "
                                             f"its value at the end of the previous step (0 at "
                                             f"first; a velocity in a dynamic step: from the DOF's "
                                             f"velocity), as in Abaqus.", once=True)
                        if q == "ACCELERATION" and not info["dynamic"] and not bad and \
                                (mag or curve is not None):
                            self.report.warn(f"*BOUNDARY, TYPE=ACCELERATION in a {info['proc']} step: "
                                             f"the Abaqus manual says acceleration histories should "
                                             f"not be used in static steps. Converted to the motion "
                                             f"the acceleration integrates to from the velocity at "
                                             f"the step start, which Abaqus need not reproduce.",
                                             once=True)
                        if not bad:
                            convert(bc, keys, shapes, amp_lines, entries, driven)
                    for k in keys:
                        state[k][2] = bc
                        redefined.add(k)
                if rate:
                    midside(driven, shapes, amp_lines, entries, mid_done)
                    self._vel_cards[id(b)] = pieces(b.param("OP"), amp_lines, entries, [])
                for spec, dofs, _, _, _ in self._rate_lines(b):   # a later card replaces a BC
                    for n in self._resolve_nodes(spec):
                        for d in dofs:
                            step_driven.pop((n, d), None)
                step_driven.update(driven)
            # rate BCs this step keeps from an earlier one keep moving their DOFs
            tail_amps: List[str] = []
            tail: list = []
            tail_driven: dict = {}
            carried: "OrderedDict[int, List[Tuple[int, int]]]" = OrderedDict()
            for k in sorted(state):
                bc = state[k][2]
                if k not in redefined and bc is not None and bc["q"] in self._RATE_TYPES:
                    carried.setdefault(id(bc), []).append(k)
            for keys in carried.values():
                convert(state[keys[0]][2], keys, shapes, tail_amps, tail, tail_driven)
            midside(tail_driven, shapes, tail_amps, tail, mid_done)
            step_driven.update(tail_driven)
            for a, c, m in self._midside.values():  # end nodes driven by different cards
                for d in range(1, 7):
                    ea, ec = step_driven.get((a, d)), step_driven.get((c, d))
                    if ea and ec and (m, d) not in mid_done and (m, d) not in step_driven:
                        e = mean_entry(ea, ec, m, d, shapes, tail_amps)
                        if e is not None:
                            tail.append(e)
            tail = [e for e in tail if e[0] not in (None, "FIXED")]   # ccx holds those already
            if tail:
                self._vel_tail[s] = pieces(None, tail_amps, tail,
                                           ["** [abq2ccx] *BOUNDARY, TYPE=VELOCITY/ACCELERATION of "
                                            "an earlier step, still in force: its motion continues"])
            # warn where finite rotations about several axes are integrated component-wise:
            # a node turned about more than one axis in this step, or about another axis
            # than the one it turned about before (the manual's own example of velocity BCs)
            if nlgeom:
                axes: Dict[int, set] = {}
                for k, st in state.items():
                    bc = st[2]
                    if bc is not None and bc["q"] in self._RATE_TYPES and k[1] >= 4:
                        res = motion(bc, 0.0, 0.0, prev_rate(k, bc))
                        if res is not None and any(x != 0.0 for _, x in res[0]):
                            axes.setdefault(k[0], set()).add(k[1])
                for (n, d), (u_s, _) in start.items():
                    if d >= 4 and u_s and n in axes:
                        axes[n].add(d)
                if any(len(ds) > 1 for ds in axes.values()):
                    self.report.warn("*BOUNDARY, TYPE=VELOCITY/ACCELERATION turning a node under "
                                     "NLGEOM about more than one axis (in one step, or one after "
                                     "the other): each rotation component is integrated on its "
                                     "own, which is exact only for a rotation about a fixed axis "
                                     "(finite rotations do not add up).", once=True)
            # where each DOF ends the step, and the form its BC carries into the next one
            for k, st in state.items():
                bc, (u_s, v_s) = st[2], start[k]
                if bc is None:
                    st[0] = st[1] = None
                    continue
                prev = prev_rate(k, bc) if bc["q"] in self._RATE_TYPES else 0.0
                h = self._bc_history(bc, T, t0, u_s, prev)
                bc["end"] = None if h is None else h[0](T)
                if bc["q"] == "DISPLACEMENT":
                    st[0] = bc["end"]
                    st[1] = 0.0 if h is not None and u_s is not None and \
                        all(h[0](t) == u_s for t in (0.0, 0.5 * T, T)) else None
                else:
                    res = motion(bc, u_s, v_s, prev)
                    still = res is not None and all(x == u_s for _, x in res[0])
                    st[0] = res[1] if res else None
                    # only a dynamic step leaves a velocity a later ACCELERATION BC can
                    # start from (a static step has none, unless nothing moved)
                    st[1] = (bc["end"] if bc["q"] == "VELOCITY" else res[2] if res else None) \
                        if info["dynamic"] else (0.0 if still else None)
            forms: Dict[int, dict] = {}
            for st in state.values():
                bc = st[2]
                if bc is None or bc["mode"] in ("FIXED", "UNKNOWN") or \
                        (bc["mode"] == "AMP" and bc["curve"].total):
                    continue                 # holds / unknown / still follows its amplitude
                if id(bc) not in forms:
                    forms[id(bc)] = dict(bc, mode="HOLD", hold=bc["end"]) if bc["end"] is not None \
                        else dict(bc, mode="UNKNOWN")
                st[2] = forms[id(bc)]
            t0 = None if t0 is None else t0 + T
        for b in rate_cards:                       # *BOUNDARY between steps: no step to act in
            if id(b) not in self._vel_cards:
                self._vel_cards[id(b)] = constraint_card(b, "outside a step")
        if stats["n"]:
            self.report.note(f"*BOUNDARY, TYPE=VELOCITY/ACCELERATION -> displacement BCs whose "
                             f"generated amplitudes (ABQ2CCX_VEL*/ACC*) are the time integral of the "
                             f"prescribed history from the displacement at the step start: exact at "
                             f"their points, straight between them (max deviation {stats['dev']:.1e} "
                             f"of a step's travel; a constant rate is exact).", once=True)
        if stats["dev"] > 2e-4:
            self.report.warn(f"A *BOUNDARY, TYPE=VELOCITY/ACCELERATION history varies too fast to "
                             f"sample exactly: the generated displacement amplitude deviates by up "
                             f"to {stats['dev']:.1e} of the step's travel between its points.",
                             once=True)

    def _load_params(self, b: Block, allowed: Sequence[str]) -> "OrderedDict[str, Optional[str]]":
        """Parameters ccx's distributed-load cards read; Abaqus-only ones are dropped —
        with a WARNING where they change the load under NLGEOM (ccx pressures always
        follow the deformed surface with their current area)."""
        keep: "OrderedDict[str, Optional[str]]" = OrderedDict()
        for k, v in b.params.items():
            if k in allowed:
                keep[k] = v
                continue
            vu = (v or "YES").strip().upper()
            changes = (k == "FOLLOWER" and vu == "NO") or (k == "CONSTANT RESULTANT" and vu == "YES")
            if changes and self._step_nlgeom:
                self.report.warn(f"*{b.keyword} {k}={vu} dropped: under NLGEOM ccx pressure loads "
                                 f"always follow the deformed surface and scale with its current "
                                 f"area, so this load differs from Abaqus as the mesh deforms.",
                                 once=True)
            else:
                self.report.note(f"*{b.keyword} parameter {k} dropped (not read by ccx"
                                 f"{'; no effect without NLGEOM' if changes else ''}).", once=True)
        return keep

    def handle_cload(self, b: Block) -> List[str]:
        """``*CLOAD``: moments (DOFs 4-6) on a *RIGID BODY reference point go to DOFs 1-3 of
        its ROT NODE — ccx silently ignores them on the REF NODE (verified: no rotation); the
        ROT NODE has the reference node's local axes if it has a *TRANSFORM.
        Abaqus ORIENTATION= (local load axes) and FOLLOWER=YES have no ccx counterpart."""
        if b.has("USER"):
            return self._user_load_card(b)
        if (b.param("OP") or "").strip().upper() == "NEW":
            self._cload_new = True        # it also removes the converted nodal forces (ccx)
        keep: "OrderedDict[str, Optional[str]]" = OrderedDict()
        for k, v in b.params.items():
            if k in ("OP", "AMPLITUDE", "TIME DELAY", "LOAD CASE", "SECTOR", "SUBMODEL", "STEP"):
                keep[k] = v
            elif k == "ORIENTATION":
                self.report.warn(f"*CLOAD, ORIENTATION={v} dropped: ccx applies concentrated loads "
                                 f"in the global system (or a node's *TRANSFORM), so these load "
                                 f"components now act along the global axes — verify.", once=True)
            elif k == "FOLLOWER" and (v or "YES").strip().upper() == "YES":
                (self.report.warn if self._step_nlgeom else self.report.note)(
                    "*CLOAD, FOLLOWER=YES dropped: ccx concentrated loads keep their direction"
                    + (" — under NLGEOM this load no longer rotates with the node." if
                       self._step_nlgeom else " (no effect without NLGEOM)."), once=True)
            else:
                self.report.note(f"*CLOAD parameter {k} dropped (not read by ccx).", once=True)
        out = [emit_keyword("CLOAD", keep)]
        moved = False
        for ln in b.data:
            f = [x.strip() for x in ln.split(",")]
            self._check_node_target("CLOAD", f[0] if f else "")
            refs: List[int] = []
            if len(f) >= 2 and re.fullmatch(r"[-+]?\d+", f[1]) and 4 <= int(f[1]) <= 6:
                nodes = self._resolve_nodes(f[0])
                refs = [n for n in nodes if n in self._rb_rot]
            if not refs:
                out.append(ln)
                continue
            moved = True
            if len(refs) != len(nodes):
                out.append(ln)                       # the other nodes keep the moment
            try:                                     # a zero moment: the same in any axes
                zero = pf(f[2]) == 0.0
            except (IndexError, ValueError):
                zero = False
            for n in refs:
                out.append(", ".join([str(self._rb_rot[n]), str(int(f[1]) - 3)] + f[2:]))
                if not zero:
                    self._warn_rot_frame(n)
        if moved:
            self.report.note("Moments on a *RIGID BODY reference point moved to DOFs 1-3 of its "
                             "ROT NODE (ccx ignores DOFs 4-6 of the REF NODE).", once=True)
        return out

    def handle_dload(self, b: Block) -> List[str]:
        """``*DLOAD``: body loads and face pressures pass through.  Element-based tractions
        (TRVECn / TRSHRn) and beam line loads (PX, PY, PZ, P1, P2) have no ccx card — ccx reads
        P1 / P2 on a beam as a pressure on its expanded section face, i.e. scaled by the
        section width (probed on 2.23) — and become consistent nodal forces
        (_to_nodal_forces), as do the tractions and pressures (P) on surface elements, which
        are not in the ccx mesh; user-subroutine loads (...NU labels) are commented out."""
        op_new = (b.param("OP") or "").strip().upper() == "NEW"
        if op_new:
            self._reset_nodal_loads("DLOAD")
        body: List[str] = []
        lines: List[Tuple[tuple, str, str]] = []           # (key, line, magnitude) of the body
        side: List[str] = []                                # converted / commented-out lines
        for rec in merged_data_records(b):
            g = [x.strip() for x in rec]
            f = [x for x in g if x != ""]
            if not f:
                continue
            label = g[1].upper() if len(g) >= 2 else ""
            if label in DLOAD_UNSUPPORTED:
                self.report.warn(f"*DLOAD type {label} has no CalculiX equivalent (ccx body loads are "
                                 f"GRAV and CENTRIF only — not rotary-acceleration/Coriolis/density-"
                                 f"scaled centrifugal); this load line was dropped. Verify.", once=True)
                continue
            if _is_user_load(b, g):
                side += self._user_load_line(b, g)
                continue
            m = re.fullmatch(r"(TRVEC|TRSHR)([1-6]?)", label)
            if m:
                eids = self._load_elements(g[0])
                faces, why = self._load_faces(eids, m.group(2), shell_reference=not m.group(2)) \
                    if eids else ([], f"element set '{g[0]}' is empty or undefined")
                side += self._to_nodal_forces(b, "DLOAD", g, faces, why)
                continue
            if re.fullmatch(r"P[XYZ12]", label):
                eids = self._load_elements(g[0])
                beams = [e for e in eids if self._is_beam(e)]
                if beams:
                    faces, why = self._beam_lines(eids, label) if len(beams) == len(eids) else \
                        ([], f"element set '{g[0]}' mixes beams with other elements")
                    side += self._to_nodal_forces(b, "DLOAD", g, faces, why)
                    continue
            # surface elements on the line (no element set: the whole model) are not in the ccx
            # mesh: a pressure on them becomes nodal forces, a mass-proportional load adds
            # nothing (they carry no mass unless --approximate dropped it), others are lost
            carriers = [e for e in self._load_elements(g[0]) if e in self._carriers] if g[0] \
                else list(self._carriers)
            if carriers:
                if label == "P":
                    faces, why = self._load_faces(carriers, "", shell_reference=True)
                    side += self._to_nodal_forces(b, "DLOAD", g, faces, why)
                elif label not in ("GRAV", "CENTRIF"):
                    side += self._drop_load_line(b, g, f"it loads surface elements, which are not "
                                                       f"in the ccx mesh, and a {label} load on "
                                                       f"them is not converted")
                    continue
                if not (self.geom.elements if not g[0] else
                        any(e not in self._carriers for e in self._load_elements(g[0]))):
                    if label != "P":
                        side.append(f"** abq2ccx: {', '.join(x for x in g if x)} -> no load: it "
                                    f"acts only on surface elements, which carry no mass in ccx")
                    continue
            if not g[0] and ALL_ELEMENTS_SET in self.geom.elsets:
                # Abaqus applies a body load with no element set to the whole model; ccx
                # needs a set (without one the line read as 'GRAV, 9.81, ...' is garbage)
                g = [ALL_ELEMENTS_SET] + g[1:]
                f = [x for x in g if x != ""]
                self.report.note(f"*DLOAD line without an element set (Abaqus: the whole model) -> "
                                 f"ELSET {ALL_ELEMENTS_SET}.", once=True)
            if label == "P":
                self.report.warn("*DLOAD label 'P' has no face number; CalculiX needs P1..P6 for element "
                                 "pressure. Verify.", once=True)
            body.append(", ".join(f))
            lines.append(((f[0].upper(), label), body[-1], f[2] if len(f) > 2 else ""))
        had_data = any(x != "" for rec in merged_data_records(b) for x in rec)
        params: "OrderedDict[str, Optional[str]]" = OrderedDict()
        if body or op_new:
            params = self._load_params(b, ("OP", "AMPLITUDE", "TIME DELAY", "LOAD CASE", "SECTOR",
                                           "SUBMODEL", "STEP"))
        if op_new:
            self._dload_op_new("DLOAD")
        self._track_dloads("DLOAD", b, lines)
        if not body and had_data:
            if op_new:
                # keep the bare header: OP=NEW validly removes all previous distributed
                # loads in ccx, and losing that would leak stale loads across steps
                if not side:
                    self.report.warn("*DLOAD, OP=NEW: every load line was unsupported and dropped, "
                                     "but the bare OP=NEW card is kept so previous distributed loads "
                                     "are still removed.", once=True)
                return [emit_keyword("DLOAD", params)] + side
            if side:
                return side
            # every load line was unsupported — commenting is louder than emitting a bare card
            return self._commented(b, "*DLOAD has no CalculiX-compatible load lines; dropped.")
        # a *DLOAD with no data at all is valid ccx (OP=NEW clears previous distributed
        # loads; plain is a no-op) — pass it through unchanged
        return [emit_keyword("DLOAD", params)] + body + side

    def handle_dsload(self, b: Block) -> List[str]:
        """``*DSLOAD``: a surface pressure becomes a ccx *DLOAD face pressure (ccx's P1..P6 face
        numbers match Abaqus' continuum faces); a surface traction (TRVEC / TRSHR), and a
        pressure on the faces of surface elements, which are not in the ccx mesh, become
        consistent nodal forces (_to_nodal_forces); a user-subroutine load (...NU labels) is
        commented out."""
        op_new = (b.param("OP") or "").strip().upper() == "NEW"
        if op_new:
            self._reset_nodal_loads("DSLOAD")
        body: List[str] = []
        lines: List[Tuple[tuple, str, str]] = []
        side: List[str] = []
        for rec in merged_data_records(b):
            g = [x.strip() for x in rec]
            f = [x for x in g if x != ""]
            if len(f) < 2:
                continue
            surf, label = f[0].upper(), f[1].upper()
            mag = f[2] if len(f) > 2 else ""
            if _is_user_load(b, g):
                side += self._user_load_line(b, g)
                continue
            if label in ("TRVEC", "TRSHR"):
                faces, why = self._surface_faces(surf)
                side += self._to_nodal_forces(b, "DSLOAD", g, faces, why)
                continue
            if not re.fullmatch(r"P[1-6]?", label):
                side += self._drop_load_line(b, f, f"the load type {label} has no ccx equivalent (ccx "
                                                   f"surface loads are pressures)")
                continue
            sd = self.surfaces.get(surf)
            if not sd or sd[0].startswith("NODE"):
                side += self._drop_load_line(b, f, f"surface '{f[0]}' is not defined in the deck" if
                                             not sd else f"'{f[0]}' is a node-based surface (a pressure "
                                                         f"needs element faces)")
                continue
            if self._carriers and any(e in self._carriers for token, _ in sd[1]
                                      for e in self._load_elements(token)):
                # faces of surface elements, which are not in the ccx mesh: nodal forces
                if label != "P":
                    side += self._drop_load_line(b, g, f"surface '{f[0]}' lies on surface "
                                                       f"elements, whose pressure label is P")
                    continue
                faces, why = self._surface_faces(surf, carriers_only=True)
                side += self._to_nodal_forces(b, "DSLOAD", g, faces, why)
            for token, face in sd[1]:
                if self._only_carriers(token):
                    continue
                if face and re.fullmatch(r"S[1-6]", face):
                    pl = "P" + face[1]
                else:
                    self.report.warn(f"*DSLOAD on '{surf}': face '{face or '?'}' has no ccx Px "
                                     f"equivalent (ccx needs P1..P6 for element pressure); emitted "
                                     f"with a bare 'P' which ccx will reject — set the face manually.",
                                     once=True)
                    pl = "P"
                line = f"{token}, {pl}"
                if mag != "":
                    line += f", {mag}"
                body.append(line)
                lines.append(((token.upper(), pl), line, mag))
        if body:
            self.report.note("*DSLOAD surface pressure converted to *DLOAD with Px face labels "
                             "(solid faces match Abaqus).", once=True)
        # OP=NEW: Abaqus removes the earlier *DSLOAD loads only; ccx's *DLOAD, OP=NEW removes
        # every earlier distributed load, so the deck's own *DLOADs are restored at the end of
        # the step (_flush_dloads).  Without earlier *DSLOAD pressures nothing needs removing.
        wipe = op_new and any(("DSLOAD", k) not in self._dl_fresh
                              for k in self._dl_state.get("DSLOAD", {}))
        out: List[str] = []
        if body or wipe:
            keep = self._load_params(b, ("OP", "AMPLITUDE", "TIME DELAY", "SUBMODEL", "STEP"))
            if not wipe:
                keep.pop("OP", None)
            if op_new:
                self._dload_op_new("DSLOAD", wipe)
            out = [emit_keyword("DLOAD", keep)] + body
        elif op_new:
            self._dload_op_new("DSLOAD", False)
        self._track_dloads("DSLOAD", b, lines)
        if not out and not side:
            if not any(x.strip() for x in b.data):
                return []                 # nothing to apply and (OP=NEW) nothing left to remove
            return self._commented(b, "Could not convert *DSLOAD automatically; edit manually.")
        return out + side

    # -- distributed loads as nodal forces, and *DLOAD bookkeeping -------------------
    def _load_elements(self, token: str) -> List[int]:
        """The defined elements a load line targets — a set counts each member once (a set
        built by *ELGEN lists its master element twice), as the emitted set does — including
        the surface elements left out of the ccx mesh (_drop_surface_elements)."""
        eids = [int(token)] if re.fullmatch(r"[-+]?\d+", token) else \
            dedup(self._carrier_sets.get(token.upper()) or self.geom.elset(token))
        return [e for e in eids if e in self.geom.elements or e in self._carriers]

    def _only_carriers(self, token: str) -> bool:
        """Whether element ``token`` / the elements of set ``token`` are all surface elements
        left out of the ccx mesh (so the emitted deck has no such element / set)."""
        eids = self._load_elements(token) if self._carriers else []
        return bool(eids) and all(e in self._carriers for e in eids)

    def _is_beam(self, eid: int) -> bool:
        info = self.geom.elements.get(eid)
        return bool(info) and info[0].upper().startswith(("B2", "B3", "PIPE"))

    def _surface_faces(self, name: str, carriers_only: bool = False) -> Tuple[list, Optional[str]]:
        """The element faces / edges of element-based *SURFACE ``name`` (see _load_faces), or
        why they cannot be resolved; with ``carriers_only`` just those on surface elements left
        out of the ccx mesh."""
        sd = self.surfaces.get(name.upper())
        if sd is None:
            return [], f"surface '{name}' is not defined in the deck"
        if sd[0].startswith("NODE"):
            return [], f"'{name}' is a node-based surface (a traction needs element faces)"
        faces: list = []
        seen: set = set()
        for token, face in sd[1]:
            eids = self._load_elements(token)
            if carriers_only:
                eids = [e for e in eids if e in self._carriers]
                if not eids:
                    continue
            if not eids:
                return [], f"surface '{name}' member '{token}' matches no element"
            label = (face or "").upper()
            eids = [e for e in eids if (e, label) not in seen]   # each face counts once
            seen.update((e, label) for e in eids)
            got, why = self._load_faces(eids, label, shell_reference=False)
            if why:
                return [], why
            faces += got
        return faces, None

    def _load_faces(self, eids: Sequence[int], face: str, shell_reference: bool
                    ) -> Tuple[list, Optional[str]]:
        """Per element, the edge / face a traction acts on as (nodes — corners first, then the
        midside nodes —, "line" or "area", scale, axisymmetric, planar, n1, sense), or why it
        cannot be resolved.  ``face``: S1..S6 or 1..6 (continuum faces, plane-element edges),
        SPOS / SNEG (the reference surface of a shell or surface element; with
        ``shell_reference`` also no face at all).  A plane-stress / plane-strain edge carries the
        section thickness as its scale.  ``sense`` (surface elements only): a pressure p acts as
        the traction p * sense * the normal consistent_nodal_forces passes."""
        out: list = []
        quiet = Report()
        m = re.fullmatch(r"S?([1-6])", face)
        for e in eids:
            info = self.geom.elements.get(e) or self._carriers.get(e)
            if info is None:
                return [], f"element {e} is not defined"
            typ, conn = info
            cc, n = ccx_element_type(typ, quiet), len(conn)
            if typ.upper() in SURFACE_ELEMENTS:
                if face not in ("SPOS", "SNEG") and not (shell_reference and not face):
                    return [], (f"face '{face}' of the {typ} element {e} is not its reference "
                                f"surface (SPOS / SNEG)")
                # Abaqus: an element-based pressure is positive along the positive element
                # normal, a surface pressure against the surface normal (SPOS: the element
                # normal, SNEG: its reverse).  The positive normal of a 3-D surface element is
                # the right-hand rule over its nodes — the face normal here; an axisymmetric
                # one turns the direction node 1 -> node 2 counterclockwise, while the edge
                # normal here turns it clockwise.
                sense = -1.0 if face == "SPOS" else 1.0
                if typ.upper().startswith(("SFMAX", "SFMGAX")):
                    out.append(([conn[0], conn[-1]] + ([conn[1]] if n == 3 else []), "line", 1.0,
                                True, True, None, -sense))
                else:
                    out.append((list(conn), "area", 1.0, False, False, None, sense))
            elif cc.startswith(PLANE_ELEM_PREFIXES):
                nc = 3 if n in (3, 6) else 4
                if not m or int(m.group(1)) > nc or n not in (nc, 2 * nc):
                    return [], f"face '{face}' is not an edge of the {typ} element {e}"
                k = int(m.group(1))
                pos = [k, k % nc + 1] + ([nc + k] if n == 2 * nc else [])
                axi = cc.startswith("CAX")
                out.append(([conn[p - 1] for p in pos], "line",
                             1.0 if axi else self._section_thick.get(e, 1.0), axi, True, None, None))
            elif cc.startswith("C3D"):
                fam = {4: "TET", 10: "TET", 6: "WEDGE", 15: "WEDGE", 8: "HEX", 20: "HEX"}.get(n)
                if not fam or not m or int(m.group(1)) not in FACE_NODES[fam]:
                    return [], f"face '{face}' is not a face of the {typ} element {e}"
                out.append(([conn[p - 1] for p in FACE_NODES[fam][int(m.group(1))] if p <= n], "area",
                            1.0, False, False, None, None))
            elif (cc in SHELL_TYPES or cc.startswith("M3D")) and n in (3, 4, 6, 8):
                if face not in ("SPOS", "SNEG") and not (shell_reference and not face):
                    return [], (f"face '{face}' of the {typ} element {e} is not its reference "
                                f"surface (SPOS / SNEG)")
                out.append((list(conn), "area", 1.0, False, False, None, None))
            else:
                return [], f"element {e} ({typ}) has no face this conversion can load"
        return out, None

    def _beam_lines(self, eids: Sequence[int], label: str) -> Tuple[list, Optional[str]]:
        """Per beam element, its nodes — ends first, then the midside node of a 3-node beam (as
        converted: an upgraded 2-node beam has one) — as a "line" for _to_nodal_forces, with
        the approximate n1 of its cross section, which P1 / P2 need."""
        out: list = []
        for e in eids:
            typ, conn = self.geom.elements[e]
            nodes = [conn[0], conn[-1]] + ([conn[1]] if len(conn) == 3 else [])
            n1 = (0.0, 0.0, -1.0) if self._planar_beams else self._beam_n1.get(e)
            if label in ("P1", "P2"):
                if self._has_normal:
                    return [], "the deck's *NORMAL cards redefine the beams' local axes"
                if n1 is None:
                    return [], f"the cross-section axes of beam {e} are unknown"
            out.append((nodes, "line", 1.0, False, self._planar_beams, n1, None))
        return out, None

    def _nodal_load_inexact(self, b: Block, base: str) -> Optional[str]:
        """Why nodal forces from the undeformed geometry would not reproduce the Abaqus load
        in this step, or None when they do: always in a small-strain step; under NLGEOM only
        for a traction that keeps its direction (FOLLOWER=NO) and its resultant (CONSTANT
        RESULTANT=YES) — ccx keeps a *CLOAD fixed in direction and magnitude."""
        if not self._step_nlgeom:
            return None
        if base in ("P1", "P2"):
            return "under NLGEOM a beam line load in the local directions rotates with the beam"
        if base in ("PX", "PY", "PZ"):
            return ("under NLGEOM Abaqus keeps a global beam line load fixed in direction but does "
                    "not document whether it acts per unit original or current length")
        if base == "TRSHR":
            return "under NLGEOM a shear traction (TRSHR) stays tangent to the deforming surface"
        if base == "P":
            return ("under NLGEOM a pressure stays normal to the deforming surface and acts per "
                    "unit current area")
        if (b.param("FOLLOWER") or "YES").strip().upper() != "NO":
            return ("under NLGEOM the traction rotates with the surface (FOLLOWER=YES, the Abaqus "
                    "default)")
        if (b.param("CONSTANT RESULTANT") or "NO").strip().upper() != "YES":
            return ("under NLGEOM the traction acts per unit current area (CONSTANT RESULTANT=NO, "
                    "the Abaqus default)")
        return None

    def _to_nodal_forces(self, b: Block, card: str, g: List[str], faces: list,
                         why: Optional[str]) -> List[str]:
        """One traction (TRVEC / TRSHR), beam line-load (PX / PY / PZ / P1 / P2) or surface-element
        pressure (P) data line ``g`` -> consistent nodal forces (consistent_nodal_forces over
        ``faces``), registered for the *CLOAD at the end of the step (_flush_nodal_loads).
        Returns the comment lines that take the load's place in the deck.  As the Abaqus
        Analysis User's Guide defines them: TRVEC is the magnitude times the normalized
        direction; TRSHR projects the direction onto the face in its undeformed geometry, at
        every integration point, and normalizes it — a point where the direction is normal to
        the face gets no load.  P acts along the face normal, with each face's sense
        (_load_faces); plane-element edges carry the section thickness, axisymmetric edges the
        full circle; a 2-D model has no third component."""
        label = g[1].upper()
        base = label[:5] if label.startswith("TR") else label
        if why:
            return self._drop_load_line(b, g, why)
        try:
            mag = pf(g[2]) if len(g) > 2 and g[2] else 0.0
            d = tuple(pf(x) if x else 0.0 for x in (g[3:6] + ["", "", ""])[:3])
        except ValueError:
            return self._drop_load_line(b, g, "its magnitude or direction is not a number")
        if b.param("ORIENTATION") and base in ("TRVEC", "TRSHR"):
            return self._drop_load_line(b, g, f"its direction is given in the local system "
                                              f"{b.param('ORIENTATION')}, which this conversion "
                                              f"does not apply")
        inexact = self._nodal_load_inexact(b, base)
        if inexact and not self._approx:
            return self._drop_load_line(b, g, f"{inexact}; nodal forces from the undeformed "
                                              f"geometry are known to be exact only in small-strain "
                                              f"steps, and under NLGEOM for TRVEC with FOLLOWER=NO, "
                                              f"CONSTANT RESULTANT=YES — rerun with --approximate to "
                                              f"apply them anyway")
        degenerate: List[int] = []
        if base in ("TRVEC", "TRSHR"):
            if any(f[4] for f in faces):                      # 2-D: in-plane components only
                d = (d[0], d[1], 0.0)
            if mag and vnorm(d) == 0.0:
                return self._drop_load_line(b, g, "its direction vector is zero")
            unit = vunit(d)

            def load(p, normal, tangent):
                if base == "TRVEC":
                    return vscale(unit, mag)
                s = vsub(unit, vscale(normal, vdot(unit, normal)))
                if vnorm(s) < 1e-9:
                    degenerate.append(1)
                    return (0.0, 0.0, 0.0)
                return vscale(vunit(s), mag)
        elif base in ("PX", "PY", "PZ"):
            axis = {"PX": (1.0, 0.0, 0.0), "PY": (0.0, 1.0, 0.0), "PZ": (0.0, 0.0, 1.0)}[base]

            def load(p, normal, tangent):
                return vscale(axis, mag)
        forces: Dict[Tuple[int, int], float] = {}
        flat: set = set()                                   # nodes of a 2-D model (DOFs 1-2)
        for nodes, kind, scale, axi, planar, n1, sense in faces:
            if planar:
                flat.update(nodes)
            if base in ("P1", "P2"):
                def load(p, normal, tangent, n1=n1):
                    n2 = vcross(tangent, n1)
                    if vnorm(n2) < 1e-9:
                        degenerate.append(1)
                        return (0.0, 0.0, 0.0)
                    n2 = vunit(n2)
                    return vscale(vcross(n2, tangent) if base == "P1" else n2, mag)
            elif base == "P":
                def load(p, normal, tangent, s=sense):
                    return vscale(normal, mag * s)
            fv = consistent_nodal_forces(kind, [self.geom.nodes[n] for n in nodes], load, axi)
            for nd, v in zip(nodes, fv):
                for k in range(2 if planar else 3):
                    if v[k]:
                        forces[(nd, k + 1)] = forces.get((nd, k + 1), 0.0) + scale * v[k]
        if degenerate and base != "TRSHR":
            return self._drop_load_line(b, g, "a beam is parallel to its n1 direction")
        big = max((abs(v) for v in forces.values()), default=0.0)
        forces = {k: v for k, v in forces.items() if abs(v) > 1e-12 * big}
        if degenerate:
            if not forces:
                return self._drop_load_line(b, g, "its direction is normal to the surface "
                                                  "everywhere, so it has no shear component "
                                                  "(Abaqus applies no load there either)")
            self.report.note(f"*{b.keyword} TRSHR on '{g[0]}': the direction is normal to part of the "
                             f"surface, which carries no shear load there (as in Abaqus).", once=True)
        res = [sum(v for (_, k), v in forces.items() if k == c) for c in (1, 2, 3)]   # global
        n_loaded = len({n for n, _ in forces})
        local = sorted({n for n, _ in forces if n in self._transformed})
        if local:
            forces, why = self._to_local_axes(forces, local, flat)
            if why:
                return self._drop_load_line(b, g, why)
            forces = {k: v for k, v in forces.items() if abs(v) > 1e-12 * big}
        amp = b.param("AMPLITUDE")
        key = (card, g[0].upper(), label)
        clash = self._nodal_load_clash(key, forces, amp)
        if clash:
            return self._drop_load_line(b, g, clash)
        if inexact:
            self.report.warn(f"[APPROX] *{b.keyword} {base}: {inexact}; converted anyway to nodal "
                             f"forces from the undeformed geometry, which ccx keeps fixed in "
                             f"direction and magnitude — the response differs from Abaqus as the "
                             f"mesh deforms. Verify.", once=True)
        self._set_nodal_load(key, forces, amp)
        if base.startswith("TR"):
            what, lack = "surface tractions (TRVEC / TRSHR)", "ccx has no such load"
        elif base == "P":
            what, lack = "pressures (P) on surface elements", "ccx has no surface element"
        else:
            what, lack = ("beam line loads (PX / PY / PZ / P1 / P2)", "ccx has no such load (it "
                          "reads P1 / P2 on a beam as a pressure on the expanded section face)")
        self.report.note(f"*{b.keyword} {what} -> consistent nodal forces in a *CLOAD at the end of "
                         f"the step: {lack}. The shape functions are integrated over the undeformed "
                         f"faces / edges (times the section thickness on plane elements, over the "
                         f"full circle on axisymmetric ones).", once=True)
        if local:
            self.report.note("Converted nodal forces on nodes with a *TRANSFORM are given in each "
                             "node's local axes, in which ccx (like Abaqus) reads a *CLOAD there: "
                             "rectangular, or cylindrical at the node's undeformed position, fixed "
                             "in space.", once=True)
        return [f"** abq2ccx: {', '.join(x for x in g if x)} -> nodal forces on "
                f"{n_loaded} node(s), resultant ({', '.join('%.6g' % x for x in res)}),"
                f" in the *CLOAD at the end of this step"
                + (f"; in the local axes of the {len(local)} with a *TRANSFORM" if local else "")]

    _SEVERAL_TRANSFORMS = ("is in several *TRANSFORM cards with different data (Abaqus allows "
                           "one per node; ccx takes the last)")

    @staticmethod
    def _transform_card(b: Block) -> Union[Tuple[str, Vec, Vec], str]:
        """A *TRANSFORM card's (TYPE letter, a, b), or why its data line cannot be read.  Like
        ccx, only the first letter of TYPE counts."""
        typ = ((b.param("TYPE") or "").strip().upper() or "R")[0]
        try:
            v = [pf(x) for rec in merged_data_records(b) for x in rec if x != ""]
            return typ, (v[0], v[1], v[2]), (v[3], v[4], v[5])
        except (IndexError, ValueError):
            return "has a *TRANSFORM whose data line cannot be read"

    def _transform_defs(self, blocks: List[Block]) -> Dict[int, Union[Tuple[str, Vec, Vec], str]]:
        """Each node with a *TRANSFORM -> its card's (TYPE letter, a, b), or why the local axes
        of the node are unknown: an unreadable data line, or several cards with different data
        (Abaqus allows one per node; ccx 2.23 silently takes the last, probed).  Also fills
        _transform_last (node -> id of the last card naming it) and _transform_twice (nodes
        that several cards with the same data name)."""
        out: Dict[int, Union[Tuple[str, Vec, Vec], str]] = {}
        self._transform_last, twice = {}, set()
        for b in blocks:
            if b.keyword != "TRANSFORM":
                continue
            d = self._transform_card(b)
            for n in self._resolve_nodes((b.param("NSET") or "").strip()):
                if n not in out:
                    out[n] = d
                elif out[n] == d and not isinstance(d, str):
                    twice.add(n)
                else:
                    out[n] = self._SEVERAL_TRANSFORMS
                self._transform_last[n] = id(b)
        self._transform_twice = {n for n in twice if out[n] != self._SEVERAL_TRANSFORMS}
        return out

    def _local_axes(self, n: int) -> Union[Tuple[Vec, Vec, Vec], str]:
        """The local axes 1, 2, 3 in which ccx — like Abaqus — reads a *CLOAD, a *BOUNDARY and
        *EQUATION terms on node ``n``, which has a *TRANSFORM (a spherical one as converted by
        handle_transform), or why they are unknown (see _transform_axes)."""
        d = self._transformed[n]
        if isinstance(d, str):
            return f"node {n} {d}"
        return self._transform_axes(n, *d)

    def _transform_axes(self, n: int, typ: str, a: Vec, b: Vec) -> Union[Tuple[Vec, Vec, Vec], str]:
        """The local axes 1, 2, 3 of node ``n`` under a *TRANSFORM of type ``typ`` with points
        ``a`` and ``b``, or why they are undefined.  Probed on 2.23 (solid, shell, membrane,
        beam, plane and axisymmetric nodes): rectangular — 1 along a, 2 towards b in the plane
        of a and b, 3 = 1 x 2; cylindrical — 3 along the axis from a to b, 1 radial from the
        axis to the node, 2 = 3 x 1, at the node's undeformed position and fixed in space
        under NLGEOM, as in Abaqus; ccx uses the global axes for a node on the cylinder axis,
        and reads any other TYPE as rectangular.  Spherical, which ccx does not have
        (handle_transform writes these axes as a rectangular card per node) — Abaqus manual,
        "Transformed coordinate systems": 1 radial from the centre a through the node, 3
        meridional (in the plane of the polar axis a-b and the node, towards b), 2 = 3 x 1
        circumferential, at the node's original position.  Abaqus cannot define a cylindrical
        or spherical system for a node on the line through a and b."""
        if typ == "R":
            e3 = vcross(a, b)
            if vnorm(e3) <= 1e-9 * vnorm(a) * vnorm(b):
                return (f"the rectangular *TRANSFORM of node {n} is degenerate (point a at the "
                        f"origin, or in line with b)")
            e1, e3 = vunit(a), vunit(e3)
            return e1, vcross(e3, e1), e3
        if typ not in ("C", "S"):
            return (f"the *TRANSFORM of node {n} has an unknown TYPE (Abaqus knows R, C and S; "
                    f"ccx reads it as rectangular)")
        kind = "cylindrical" if typ == "C" else "spherical"
        if n not in self.geom.nodes:
            return f"node {n} of a {kind} *TRANSFORM is not defined"
        axis, p = vsub(b, a), vsub(self.geom.nodes[n], a)
        if not vnorm(axis):
            return f"the {kind} *TRANSFORM of node {n} is degenerate (a and b coincide)"
        e3 = vunit(axis)
        r = vsub(p, vscale(e3, vdot(p, e3)))
        # cylindrical: within 1e-6 of the model's scale; spherical: within 1e-6 rad of the axis
        if vnorm(r) <= 1e-6 * (max(vnorm(axis), vnorm(p)) if typ == "C" else vnorm(p)):
            return (f"node {n} lies on the {'axis' if typ == 'C' else 'polar axis'} of its {kind} "
                    f"*TRANSFORM, where the local directions are undefined (Abaqus cannot "
                    f"define the system there; ccx uses the global axes)")
        if typ == "C":
            e1 = vunit(r)
            return e1, vcross(e3, e1), e3
        e1 = vunit(p)
        e2 = vunit(vcross(e3, e1))
        return e1, e2, vcross(e1, e2)

    def _rect_transform(self, nodes: Sequence[int], data: str) -> List[str]:
        """A rectangular *TRANSFORM, data line ``data`` (points a, b), on a new node set
        ABQ2CCX_TRn of ``nodes``."""
        self._n_transform_sets += 1
        name = f"ABQ2CCX_TR{self._n_transform_sets}"
        return [f"*NSET, NSET={name}"] + reflow(list(nodes)) + \
            [f"*TRANSFORM, NSET={name}, TYPE=R", data]

    def handle_transform(self, b: Block) -> List[str]:
        """``*TRANSFORM``: rectangular and cylindrical cards pass through.  ccx 2.23 has no
        spherical system: it silently reads TYPE=S as a rectangular system through points a and
        b (probed: the same results as TYPE=R), degenerate when the centre a is the origin (NaN
        results with a *CLOAD there, a singular matrix with a BC).  So a TYPE=S card becomes
        a rectangular card per node (nodes with equal axes share one) with that node's
        spherical axes (_transform_axes), fixed at its original position as in Abaqus: BCs,
        loads and *EQUATION terms there keep their meaning.  After the card that last names a
        *RIGID BODY reference node, its ROT NODE gets the same local axes (_plan_rot_axes)."""
        d = self._transform_card(b)
        nset = (b.param("NSET") or "").strip()
        if isinstance(d, str) or d[0] != "S":
            out = [emit_keyword("TRANSFORM", b.params)] + list(b.data)
        else:
            out = ["** abq2ccx: spherical *TRANSFORM (ccx has none) -> a rectangular *TRANSFORM per "
                   "node with the same local axes", "** " + emit_keyword("TRANSFORM", b.params)] + \
                  ["** " + x for x in b.data]
            groups: "OrderedDict[str, List[int]]" = OrderedDict()
            off: List[int] = []
            why = ""
            for n in dedup(self._resolve_nodes(nset)):
                axes = self._transform_axes(n, *d)
                if isinstance(axes, str):
                    off.append(n)
                    why = why or axes
                else:
                    groups.setdefault(", ".join(_fmt_unit(x) for x in axes[0] + axes[1]), []).append(n)
            for data, nodes in groups.items():
                out += self._rect_transform(nodes, data)
            self.report.note("*TRANSFORM, TYPE=S (spherical): ccx has none and silently reads the "
                             "card as a rectangular system through points a and b (probed on 2.23; "
                             "with the centre a at the origin that system is degenerate: NaN results "
                             "with a *CLOAD there, a singular matrix with a BC). Each node gets a "
                             "rectangular *TRANSFORM with its spherical axes instead — 1 radial from "
                             "the centre a, 3 meridional towards the pole b, 2 = 3 x 1 — at its "
                             "original position, fixed in space as in Abaqus, so BCs, loads and "
                             "equations there act as in Abaqus.", once=True)
            if off:
                self.report.warn(f"*TRANSFORM, TYPE=S on {nset}: no local axes for {len(off)} "
                                 f"node(s), since {why}. Their BCs and loads act along the global "
                                 f"axes in ccx — verify.", once=True)
        for ref, rot in self._rb_rot.items():
            if rot in self._rot_axes and self._transform_last.get(ref) == id(b):
                e1, e2 = self._rot_axes[rot]
                out += self._rect_transform([rot], ", ".join(_fmt_unit(x) for x in e1 + e2))
        return out

    def _plan_rot_axes(self, pairs: Dict[int, int]) -> None:
        """Local axes of the rotation nodes in ``pairs`` (reference node -> its ROT NODE, or
        a node -> the rotation node _plan_connector_rows made for it).  ccx carries the node's
        rotation on DOFs 1-3 of that node, where _active_dof_lines / handle_cload move the
        node's rotational BCs and moments, and Abaqus reads those in the node's local axes
        when it has a *TRANSFORM: the rotation node gets the same axes as a rectangular
        *TRANSFORM (handle_transform writes it; probed on 2.23: exact, also under NLGEOM), and
        the rotation ties and connector constraints on it are written in them.  Where they are
        undefined the reason is kept for a warning when such a BC or moment is moved
        (_warn_rot_frame); a rotation node with a *TRANSFORM of its own keeps that one."""
        for ref, rot in pairs.items():
            if ref not in self._transformed or rot in self._transformed:
                continue
            axes = self._local_axes(ref)
            if isinstance(axes, str):
                self._rot_axes_why[ref] = axes
            else:
                self._rot_axes[rot] = (axes[0], axes[1])

    def _check_transforms(self) -> None:
        """Deck-wide *TRANSFORM checks, once _transform_defs, _plan_rigid_couplings and
        _plan_rot_axes have filled _transformed, _rb_rot and _rot_axes:

        * several cards with different data on a node: Abaqus does not allow it ("Multiple
          transformation definitions are not allowed at a node"), ccx 2.23 silently takes the
          last card (probed) -> warning (the same data twice: a note);
        * a node of 2-D elements whose local 3-axis leaves the global Z axis: the Abaqus manual
          requires a transformation consistent with the degrees of freedom at the node, and
          ccx 2.23 gets such a node wrong without an error (probed) -> warning;
        * a *RIGID BODY reference node whose rotational BCs and moments go to DOFs 1-3 of its
          ROT NODE (_active_dof_lines, handle_cload): Abaqus reads them in the reference
          node's local axes, so the ROT NODE has the same axes (_plan_rot_axes) -> note."""
        if not self._transformed:
            return
        several = sorted(n for n, d in self._transformed.items() if d == self._SEVERAL_TRANSFORMS)
        if several:
            self.report.warn(f"{len(several)} node(s) (e.g. node {several[0]}) are named by several "
                             f"*TRANSFORM cards with different data. Abaqus does not allow that "
                             f"('Multiple transformation definitions are not allowed at a node'); "
                             f"ccx 2.23 silently uses the last card (probed), so BCs, loads and "
                             f"equations on these nodes act in its axes. Keep one *TRANSFORM per "
                             f"node.")
        if self._transform_twice:
            twice = sorted(self._transform_twice)
            self.report.note(f"{len(twice)} node(s) (e.g. node {twice[0]}) are named by several "
                             f"*TRANSFORM cards with the same data: Abaqus does not allow multiple "
                             f"transformation definitions at a node; ccx uses the last card, which "
                             f"defines the same axes here.")
        flat = set(self._plane_only)                  # nodes of 2-D elements
        for typ, conn in self.geom.elements.values():
            if typ.upper().startswith(("B21", "B22", "B23", "PIPE21", "PIPE22", "T2D")):
                flat.update(conn)
        tilted = []
        for n in sorted(flat & set(self._transformed)):
            axes = self._local_axes(n)
            if not isinstance(axes, str) and math.hypot(axes[2][0], axes[2][1]) > 1e-6:
                tilted.append(n)
        if tilted:
            self.report.warn(f"*TRANSFORM turns the local 3-axis of {len(tilted)} node(s) of 2-D "
                             f"elements (e.g. node {tilted[0]}) out of the global Z axis, the normal "
                             f"of the model plane. The Abaqus manual requires a transformation "
                             f"consistent with the degrees of freedom at the node (local 1 and 2 in "
                             f"the plane), and ccx 2.23 gets such nodes wrong without an error "
                             f"(probed: the *TRANSFORM alone changes plane-strain and quadratic "
                             f"plane-stress models by up to 91 % of |u|; BCs and loads there act "
                             f"partly out of the plane, on axisymmetric, truss and beam nodes too). "
                             f"Give these nodes a transformation about the Z axis.")
        if any(rot not in self._conn_rot for rot in self._rot_axes):
            self.report.note("*RIGID BODY reference node(s) with a *TRANSFORM: Abaqus reads their "
                             "rotational BCs and moments in the local axes, so each ROT NODE, which "
                             "carries them as its DOFs 1-3, gets the same axes as a rectangular "
                             "*TRANSFORM (probed on 2.23: exact, also under NLGEOM).")

    def _warn_rot_frame(self, ref: int) -> None:
        """Warn (once) when a rotational BC or moment moves from *RIGID BODY reference node
        ``ref``, whose *TRANSFORM leaves its local axes undefined, to its untransformed ROT
        NODE: there it acts about the global axes."""
        why = self._rot_axes_why.get(ref)
        if why and not self._rot_axes_warned:
            self._rot_axes_warned = True
            self.report.warn(f"Rotational BCs / moments on *RIGID BODY reference node {ref}, which "
                             f"has a *TRANSFORM, moved to DOFs 1-3 of its ROT NODE act about the "
                             f"global axes there; Abaqus reads them in the node's local axes, but "
                             f"{why}. Verify.")

    def _to_local_axes(self, forces: Dict[Tuple[int, int], float], nodes: Sequence[int],
                       flat: set) -> Tuple[Dict[Tuple[int, int], float], Optional[str]]:
        """Converted nodal forces (global components) with those on ``nodes``, which have a
        *TRANSFORM, given in each node's local axes (_local_axes) — or why that cannot be done.
        A node of a 2-D model (in ``flat``) has DOFs 1 and 2 only, so its transform must keep
        local 3 along the global Z axis (probed: ccx then matches the global load exactly)."""
        out = {k: v for k, v in forces.items() if k[0] not in self._transformed}
        for n in nodes:
            axes = self._local_axes(n)
            if isinstance(axes, str):
                return {}, axes
            f = tuple(forces.get((n, k), 0.0) for k in (1, 2, 3))
            loc = [vdot(e, f) for e in axes]
            if n in flat:
                if math.hypot(axes[2][0], axes[2][1]) > 1e-6:
                    return {}, (f"the *TRANSFORM of node {n} turns its local 3-direction out of the "
                                f"global Z axis, so the 2-D node's in-plane force has no local "
                                f"components")
                loc[2] = 0.0
            for k, v in enumerate(loc, 1):
                if v:
                    out[(n, k)] = v
        return out, None

    def _nodal_load_clash(self, key: tuple, forces: Dict[Tuple[int, int], float],
                          amp: Optional[str]) -> Optional[str]:
        """Why ``forces`` cannot join the generated *CLOAD, or None.  ccx keeps one value and one
        amplitude per node and DOF: values given in one step add up, a later step replaces
        them.  A node DOF shared with the deck's own *CLOAD is therefore exact only when the
        deck has a single step and the same amplitude; one shared with another converted load
        needs the same amplitude."""
        for nd in forces:
            amps = self._deck_cloads.get(nd)
            if amps is not None and (self._n_steps > 1 or amps != {amp}):
                return (f"its nodal force on node {nd[0]} DOF {nd[1]} would share the entry of the "
                        f"deck's own *CLOAD there (ccx keeps one value and amplitude per node and "
                        f"DOF, and a later step replaces it)")
        for other, (f2, a2) in self._nodal_loads.items():
            if other != key and a2 != amp and not f2.keys().isdisjoint(forces):
                return (f"it shares nodes with another converted load ({other[2]} on {other[1]}) "
                        f"under a different amplitude, and ccx keeps one amplitude per node and DOF")
        return None

    def _set_nodal_load(self, key: tuple, forces: Dict[Tuple[int, int], float],
                        amp: Optional[str]) -> None:
        """Record the nodal forces of a converted load (Abaqus semantics: a key given again in
        a later step replaces it, twice in one step adds up; no force removes it)."""
        if key in self._nodal_fresh and key in self._nodal_loads:
            old = self._nodal_loads[key][0]
            for nd, v in forces.items():
                old[nd] = old.get(nd, 0.0) + v
        elif forces:
            self._nodal_loads[key] = (dict(forces), amp)
        else:
            self._nodal_loads.pop(key, None)
        self._nodal_fresh.add(key)

    def _reset_nodal_loads(self, card: str) -> None:
        """OP=NEW on a *DSLOAD / *DLOAD: the converted loads of that card from earlier steps go
        (those given earlier in this step stay — Abaqus, and ccx alike)."""
        if card in self._nodal_reset:
            return
        self._nodal_reset.add(card)
        for k in [k for k in self._nodal_loads if k[0] == card and k not in self._nodal_fresh]:
            del self._nodal_loads[k]

    def _flush_nodal_loads(self) -> List[str]:
        """The *CLOAD (one per amplitude) that brings ccx's generated nodal forces to the state
        the step's converted loads define: every node DOF whose force changed, with 0 where a
        load went away.  Never OP=NEW, which would also remove the deck's own *CLOADs; after
        the deck's own *CLOAD, OP=NEW (which removes these too) every force is given again."""
        target: Dict[Tuple[int, int], Tuple[str, Optional[str]]] = {}
        sums: Dict[Tuple[int, int], float] = {}
        amps: Dict[Tuple[int, int], Optional[str]] = {}
        for forces, amp in self._nodal_loads.values():
            for nd, v in forces.items():
                sums[nd] = sums.get(nd, 0.0) + v
                amps[nd] = amp
        for nd, v in sums.items():
            target[nd] = ("%.12g" % v if v else "0", amps[nd])
        held = {} if self._cload_new else self._nodal_emitted
        groups: "OrderedDict[Optional[str], List[str]]" = OrderedDict()
        for nd in sorted(set(target) | set(held)):
            new = target.get(nd, ("0", None))
            if held.get(nd) == new or (nd not in held and new[0] == "0"):
                continue
            groups.setdefault(new[1], []).append(f"{nd[0]}, {nd[1]}, {new[0]}")
        self._nodal_emitted = {nd: v for nd, v in target.items() if v[0] != "0"}
        out: List[str] = []
        if groups:
            out.append("** abq2ccx: consistent nodal forces of the distributed loads converted "
                       "above (tractions, beam line loads, pressures on surface elements)")
        for amp, data in groups.items():
            out.append("*CLOAD" + (f", AMPLITUDE={amp}" if amp else ""))
            out.extend(data)
        return out

    def _drop_load_line(self, b: Block, g: Sequence[str], why: str) -> List[str]:
        """Comment out one load data line, with the reason."""
        text = ", ".join(x for x in g if x)
        label = g[1].upper() if len(g) > 1 else ""
        msg = f"*{b.keyword} {label} on '{g[0]}' not converted: {why}. Commented out."
        self.report.n_commented += 1
        self.report.warn(msg, once=True)
        return ["** abq2ccx: " + msg, "** " + text]

    def _user_load_line(self, b: Block, g: Sequence[str]) -> List[str]:
        """A load line whose magnitude comes from an Abaqus user subroutine (a ...NU label)."""
        label = g[1].upper() if len(g) > 1 else ""
        if label.startswith(("TRVEC", "TRSHR", "EDLD")):
            return self._drop_load_line(b, g, "its magnitude and direction come from the Abaqus "
                                              "user subroutine UTRACLOAD, and ccx has no user "
                                              "traction load")
        sub = CCX_USER_SUBROUTINE.get(b.keyword, "user subroutine")
        return self._drop_load_line(b, g, f"its magnitude comes from an Abaqus user subroutine, "
                                          f"which ccx cannot call (kept, ccx would run its stock "
                                          f"{sub} in its place); port the subroutine to ccx's "
                                          f"{sub} and restore the line")

    def _user_load_card(self, b: Block) -> List[str]:
        """A load / BC card with USER: its magnitudes come from an Abaqus user subroutine."""
        sub = CCX_USER_SUBROUTINE.get(b.keyword, "user subroutine")
        what = "prescribed values" if b.keyword == "BOUNDARY" else "magnitudes"
        return self._commented(b, f"*{b.keyword}, USER: the {what} come from an Abaqus user "
                                  f"subroutine, which ccx cannot call — kept, ccx would run its "
                                  f"stock {sub} in place of the deck's own. Commented out: port the "
                                  f"subroutine to ccx's {sub} and restore the card.")

    def _track_dloads(self, origin: str, b: Block, lines: List[Tuple[tuple, str, str]]) -> None:
        """Record the *DLOAD lines emitted for a *DLOAD / *DSLOAD card (``origin``), in
        Abaqus semantics: a zero magnitude removes the load."""
        state = self._dl_state.setdefault(origin, OrderedDict())
        amp = b.param("AMPLITUDE")
        for key, line, mag in lines:
            self._dl_fresh.add((origin, key))
            try:
                zero = bool(mag) and pf(mag) == 0.0
            except ValueError:
                zero = False
            if zero:
                state.pop(key, None)
            else:
                state[key] = (line, amp)

    def _dload_op_new(self, origin: str, wipes: bool = True) -> None:
        """OP=NEW on a *DLOAD / *DSLOAD: Abaqus removes that card's loads of earlier steps.  An
        emitted ccx *DLOAD, OP=NEW (``wipes``) removes the other card's too, so they are given
        again at the end of the step (_flush_dloads)."""
        state = self._dl_state.setdefault(origin, OrderedDict())
        for key in [k for k in state if (origin, k) not in self._dl_fresh]:
            del state[key]
        self._dl_wiped = self._dl_wiped or wipes

    def _flush_dloads(self) -> List[str]:
        """After a ccx *DLOAD, OP=NEW in this step: the distributed loads of earlier steps that
        Abaqus keeps (the other card's, not redefined here), given again."""
        if not self._dl_wiped:
            return []
        groups: "OrderedDict[Optional[str], List[str]]" = OrderedDict()
        for origin, state in self._dl_state.items():
            for key, (line, amp) in state.items():
                if (origin, key) not in self._dl_fresh:
                    groups.setdefault(amp, []).append(line)
        out: List[str] = []
        if groups:
            out.append("** abq2ccx: distributed loads of earlier steps that Abaqus keeps here (ccx's "
                       "*DLOAD, OP=NEW above removed them)")
            self.report.note("*DLOAD / *DSLOAD, OP=NEW: Abaqus removes only the earlier loads of the "
                             "same card, ccx's *DLOAD, OP=NEW every earlier distributed load — the "
                             "other card's loads are given again at the end of the step.", once=True)
        for amp, data in groups.items():
            out.append("*DLOAD" + (f", AMPLITUDE={amp}" if amp else ""))
            out.extend(data)
        return out

    def handle_output(self, b: Block) -> List[str]:
        """An output card -> the ccx cards _plan_output chose for it (the notes on its
        parameters and variables are given here, where the card stands)."""
        p = self._out_plan.get(id(b)) or self._lone_output_plan(b)
        if p["cc"] == "CONTACT FILE":
            self._contact_card(p.get("src", b), self.report)
        elif p["cc"]:
            self._output_card(p.get("src", b), p["cc"], self.report)
        return self._anchored_output(b, p)

    def _anchored_output(self, b: Block, p: Optional[dict] = None) -> List[str]:
        """The ccx output cards (and their notes) _plan_output placed at block ``b``."""
        p = p or self._out_plan.get(id(b))
        if not p:
            return []
        for msg in p["notes"]:
            self.report.note(msg, once=True)
        for msg in p["warnings"]:
            self.report.warn(msg, once=True)
        return self._emit_output_cards(p["cards"], p["out2d"])

    def _lone_output_plan(self, b: Block) -> dict:
        """The plan of an output card _plan_output did not see: the card on its own, its
        FREQUENCY / TIME POINTS kept."""
        cc = self._output_route(b, None)
        quiet = Report()
        if cc == "CONTACT FILE":
            params, labels = self._contact_card(b, quiet, keep_ctl=True)
        else:
            params, labels = self._output_card(b, cc, quiet, keep_ctl=True)
        off = (params.get("FREQUENCY") or "").strip() == "0"
        cards = [] if labels is None or off else [(cc, params, labels)]
        return {"cc": cc, "cards": cards, "notes": [], "warnings": [], "out2d": False}

    @staticmethod
    def _output_route(b: Block, ctx: Optional[Block]) -> str:
        """The ccx card that output card ``b`` becomes (``ctx``: the *OUTPUT it follows).
        History output for a set — a time series at its nodes or elements — goes to the
        .dat (*NODE PRINT / *EL PRINT), everything else to the .frd."""
        hist = ctx is not None and ctx.has("HISTORY")
        if b.keyword in ("CONTACT OUTPUT", "CONTACT FILE"):
            return "CONTACT FILE"
        if b.keyword == "NODE OUTPUT":
            return "NODE PRINT" if hist and b.param("NSET") else "NODE FILE"
        if b.keyword == "ELEMENT OUTPUT":
            return "EL PRINT" if hist and b.param("ELSET") else "EL FILE"
        return b.keyword

    def _output_card(self, b: Block, cc: str, report: "Report", keep_ctl: bool = False):
        """(parameters, ccx labels) of output card ``b`` written as ``*cc``, with notes on
        what is dropped or renamed; labels None when nothing of the card is left.  Its
        FREQUENCY / TIME POINTS are left to the step's output control (_plan_output) unless
        ``keep_ctl``."""
        members = self.geom.elset((b.param("ELSET") or "").strip()) if b.param("ELSET") else []
        if members and all(e in self._conn for e in members):
            report.note(f"*{b.keyword} on connector elements dropped: they are constraints in "
                        f"ccx, which has no connector output (CTF, CU, ...).", once=True)
            return OrderedDict(), None
        is_print = cc.endswith("PRINT")
        # parameters ccx's *NODE FILE / *EL FILE reader accepts (noelfiles.f); anything else
        # is "parameter not recognized" there
        file_ok = {"FREQUENCYF", "GLOBAL", "OUTPUT", "SECTION FORCES", "OUTPUT ALL", "NSET",
                   "LAST ITERATIONS", "CONTACT ELEMENTS", "DOUBLE"}
        params: "OrderedDict[str, Optional[str]]" = OrderedDict()
        for k, v in b.params.items():
            if k == "POSITION":
                report.note("Output POSITION=... dropped (ccx extrapolates to nodes automatically).", once=True)
                continue
            if k in ("VARIABLE", "MODE", "MODE LIST", "SUMMARY", "LAST MODE"):
                report.note(f"Output parameter {k} dropped.", once=True)
                continue
            if k in ("FREQ", "FREQUENCY", "TIME POINTS"):
                if keep_ctl:
                    params["FREQUENCY" if k == "FREQ" else k] = v
                continue
            if k == "ELSET" and cc == "EL FILE":
                report.note("*EL FILE ELSET= dropped (ccx writes all elements to .frd; use "
                            "*EL PRINT, ELSET= to restrict).", once=True)
                continue
            if not is_print and k not in file_ok:
                report.note(f"*{cc} parameter {k} dropped (not read by ccx).", once=True)
                continue
            if is_print and k == "DIRECTIONS":
                report.note(f"*{cc} parameter {k} dropped (not read by ccx).", once=True)
                continue
            params[k] = v
        if b.keyword in ("NODE OUTPUT", "ELEMENT OUTPUT") and is_print:
            # a history request: only its set carries over to the print card
            key = "NSET" if cc == "NODE PRINT" else "ELSET"
            params = OrderedDict([(key, b.param(key))])
        if cc == "EL PRINT" and self._only_carriers(params.get("ELSET") or ""):
            report.note("*EL PRINT on surface elements dropped: they are not in the ccx mesh.",
                        once=True)
            return params, None
        if cc == "EL PRINT" and "ELSET" not in params and ALL_ELEMENTS_SET in self.geom.elsets:
            params["ELSET"] = ALL_ELEMENTS_SET
            report.note(f"*EL PRINT without ELSET -> ELSET={ALL_ELEMENTS_SET} (Abaqus prints "
                        f"every element; ccx prints nothing without a set).", once=True)
        if cc == "NODE PRINT" and "NSET" not in params and ALL_NODES_SET in self.geom.nsets:
            params["NSET"] = ALL_NODES_SET
            report.note(f"*NODE PRINT without NSET -> NSET={ALL_NODES_SET} (Abaqus prints "
                        f"every node; ccx prints nothing without a set).", once=True)
        if cc == "EL PRINT" and "ELSET" not in params:
            report.warn("*EL PRINT requires ELSET= in ccx; none present.", once=True)
        if cc == "NODE PRINT" and "NSET" not in params:
            report.warn("*NODE PRINT requires NSET= in ccx; none present.", once=True)
        invars: List[str] = []
        for rec in merged_data_records(b):
            invars.extend(x for x in rec if x != "")
        outvars: List[str] = []
        known_bases = set(ABQ_DROP_VARS) | set(ABQ_MAP_VARS) | \
            {"S", "E", "U", "V", "RF", "NT", "ME", "PEEQ", "THE", "SDV", "HFL", "ENER"}
        for v in invars:
            vu = v.upper()
            # per-component identifiers (S11, EE12, THE33...) collapse to their base tensor
            # name — ccx output identifiers are whole quantities, and a long component list
            # also overflows ccx's 16-entries-per-line reader
            mcomp = re.fullmatch(r"([A-Z]+?)(\d{1,2})", vu)
            if vu not in known_bases and mcomp and mcomp.group(1) in known_bases:
                report.note("Per-component output identifiers (e.g. S11, EE12) collapsed to "
                            "their base quantity (ccx writes whole tensors).", once=True)
                vu = mcomp.group(1)
            if vu in ABQ_DROP_VARS:
                report.note(f"Output variable {vu} dropped (no ccx equivalent; derive in "
                            f"post-processing).", once=True)
                continue
            mapped = ABQ_MAP_VARS.get(vu, vu)
            if mapped != vu:
                why = ABQ_MAP_CAVEATS.get(vu, "CalculiX naming")
                report.note(f"Output variable {vu} -> {mapped} ({why}).", once=True)
            if not is_print and mapped in EL_PRINT_ONLY_VARS:
                report.note(f"Output variable {mapped} is valid only on *EL PRINT/*NODE PRINT; "
                            f"dropped from *{cc} (.frd).", once=True)
                continue
            outvars.append(mapped)
        allowed = (CCX_EL_PRINT_LABELS if cc == "EL PRINT" else
                   CCX_NODE_PRINT_LABELS if cc == "NODE PRINT" else CCX_FILE_LABELS)
        kept: List[str] = []
        for v in outvars:
            if ccx_label_ok(v, allowed):
                kept.append(v)
            else:
                report.note(f"Output variable {v} dropped from *{cc} (not a ccx label there"
                            f"{'; ccx stops on an unknown *EL PRINT label' if cc == 'EL PRINT' else ''}).",
                            once=True)
        outvars = kept
        if is_print and not outvars and invars:
            report.note(f"*{cc}: none of its variables exists in ccx; card dropped.", once=True)
            return params, None
        if is_print and not invars and b.keyword in ("NODE OUTPUT", "ELEMENT OUTPUT"):
            report.note(f"*{b.keyword} for history output names no variables (a VARIABLE= "
                        f"selection has no ccx equivalent); dropped.", once=True)
            return params, None
        if not outvars and not is_print:
            outvars = ["U"] if cc == "NODE FILE" else ["S"]
            report.note(f"*{cc}: no explicit variables -> default '{outvars[0]}'.", once=True)
        final = dedup_str(outvars)
        if len(final) > 16:                       # ccx reads at most 16 entries per line
            report.warn(f"*{cc}: more than 16 output identifiers after mapping; keeping "
                        f"the first 16 (ccx line limit).", once=True)
            final = final[:16]
        return params, final

    def _contact_card(self, b: Block, report: "Report", keep_ctl: bool = False):
        """``*CONTACT OUTPUT`` / ``*CONTACT FILE`` -> ccx ``*CONTACT FILE``: Abaqus contact
        variables fold onto ccx's CDIS (opening/slip) and CSTR (pressure/shear); others
        (forces, areas, status) are dropped; Abaqus-only parameters too.  Returns
        (parameters, labels), labels None when no ccx contact variable is left."""
        keep: "OrderedDict[str, Optional[str]]" = OrderedDict()
        for k, v in b.params.items():
            if k in ("FREQ", "FREQUENCY", "TIME POINTS"):
                if keep_ctl:
                    keep["FREQUENCY" if k == "FREQ" else k] = v
            elif k in ("LAST ITERATIONS", "CONTACT ELEMENTS", "FREQUENCYF"):
                keep[k] = v
            else:
                report.note(f"*{b.keyword} parameter {k} dropped (not read by ccx).", once=True)
        labels: List[str] = []
        for rec in merged_data_records(b):
            for v in (x.upper() for x in rec if x != ""):
                m = ABQ_CONTACT_MAP.get(v, v)
                if ccx_label_ok(m, CCX_CONTACT_FILE_LABELS):
                    labels.append(m[:4])
                else:
                    report.note(f"Contact output variable {v} dropped (ccx writes CDIS, CSTR "
                                f"and CELS only; its CSTR includes the contact pressure).",
                                once=True)
        if not labels:
            had = any(x != "" for rec in merged_data_records(b) for x in rec)
            if had:                                 # every requested variable was dropped
                report.note(f"*{b.keyword}: no ccx contact variable requested; card dropped.",
                            once=True)
                return keep, None
            labels = ["CDIS", "CSTR"]
        return keep, dedup_str(labels)

    def _emit_output_cards(self, cards: List[tuple], out2d: bool = False) -> List[str]:
        """Write ``cards`` [(keyword, params, labels)].  The first output card of a step
        carries the step's output control when ccx would otherwise keep another one (ccx
        has one for all output cards of a step, and carries it into later steps); with
        ``out2d`` the first *NODE FILE gets OUTPUT=2D."""
        out: List[str] = []
        for i, (kw, params, labels) in enumerate(cards):
            params = OrderedDict(params)
            if out2d and kw == "NODE FILE":
                params["OUTPUT"] = "2D"
                out2d = False
            if i == 0:
                if self._out_ctl_step != self._step_idx:
                    self._out_ctl_step = self._step_idx
                    ctl = self._out_ctl.get(self._step_idx)
                    if ctl and ctl != self._out_ctl_now:
                        params[ctl[0]] = ctl[1]
                        self._out_ctl_now = ctl
            out.append(emit_keyword(kw, params))
            if labels:
                out.append(", ".join(labels))
        return out

    # -- output planning ----------------------------------------------------
    def _plan_output(self, blocks: List[Block]) -> None:
        """Fit the output requests of each step to ccx's output model, which differs from
        Abaqus' in ways that silently lose output (all probed on ccx 2.23):

        * a .frd keeps ONE node set per variable and step: a second *NODE FILE for U on a
          set replaces the whole-model U of the first;
        * a .frd has no node of no element (a reference point) and — in a model with a beam
          or shell — no original node of a beam, shell, truss, membrane or plane element
          (CCX_EXPANDED_PREFIXES): a set of those writes empty blocks;
        * one output control, FREQUENCY= or TIME POINTS=, serves every .frd and .dat card
          of a step: the last one given wins, and it carries over into later steps;
        * TIME POINTS work only where ccx picks the increments (not under DIRECT, in
          *MODAL DYNAMIC or in explicit dynamics, where they are ignored).

        So history output for a set (a time series at its nodes or elements) goes to the
        .dat (_output_route); each .frd variable keeps one node set (the whole model before
        a set; several sets joined); a .frd set the .frd cannot show gets a *NODE PRINT
        twin, or OUTPUT=2D when every .frd request of the deck is U / V / RF, which
        OUTPUT=2D keeps exact; and each step gets one output control, taken from its .frd
        requests first (_step_output_control)."""
        quiet = Report()
        self._out_user_tp = {(b.param("NAME") or "").strip().upper(): b
                             for b in blocks if b.keyword == "TIME POINTS"}
        self._out_amp_names = {(b.param("NAME") or "").strip().upper()
                               for b in blocks if b.keyword in ("AMPLITUDE", "TIME POINTS")}
        self._out_tp_names: Dict[tuple, str] = {}
        self._out_subsets: Dict[str, str] = {}      # .frd set -> its nodes missing from the .frd
        self._used_names |= set(self.geom.nsets) | set(self.geom.elsets)
        types = {t: ccx_element_type(t, quiet) for t in {t for t, _c in self.geom.elements.values()}}
        frd3d = any(c.startswith(CCX_FRD_3D_TRIGGER) for c in types.values())
        solid_nodes: set = set()
        flat_nodes: set = set()
        for typ, conn in self.geom.elements.values():
            if types[typ].startswith(CCX_SOLID_PREFIXES):
                solid_nodes.update(conn)
            elif types[typ].startswith(CCX_EXPANDED_PREFIXES):
                flat_nodes.update(conn)
        self._out_yields = self._yielding_materials(blocks)
        pairs = [b for b in blocks if b.keyword == "CONTACT PAIR" and not b.has("TIED")]
        self._out_contact = {           # the contact ccx gets (_contact_output_issues)
            "abaqus": any(b.keyword in ("CONTACT PAIR", "CONTACT") for b in blocks),
            "pairs": len(pairs),
            "nts": any((b.param("TYPE") or "").upper().replace(" ", "") != "SURFACETOSURFACE"
                       for b in pairs),
            # elements whose expanded nodes only a 3-D .frd (a beam or shell model) holds
            "flat": not frd3d and any(c.startswith(PLANE_ELEM_PREFIXES + ("M3D",))
                                      for c in types.values()),
            "axi": any(c.startswith("CAX") for c in types.values())}
        self._courant = None                    # (min h f / c, element), see _courant_min
        steps: List[Tuple[int, dict, List[dict]]] = []
        # The field output requests Abaqus keeps for a later step without requests of its
        # own, per kind of step (general, linear perturbation): None while there are none
        # (Abaqus then writes its preselected output), else the cards of the step that made
        # them, [(card, the *OUTPUT it follows)] — a PRESELECT / ALL *OUTPUT standing for
        # its preselected variables, "DEFAULT" for the preselected default
        carried: Dict[bool, Optional[list]] = {False: None, True: None}
        prev_pert = False
        i, k = 0, 0
        while i < len(blocks):
            if blocks[i].keyword == "STEP":
                j = i + 1
                while j < len(blocks) and blocks[j].keyword != "END STEP":
                    j += 1
                k += 1
                inner = blocks[i + 1:j]
                proc = next((x for x in inner if x.keyword in PROC_KW), None)
                timing = self._step_timing(proc)
                if timing["kind"] == "explicit":
                    timing["dtstable"] = self._explicit_stable_increment(blocks, proc)
                    timing["dtmax"] = self._circ_capped_max(proc, timing["dtmax"])
                pert = timing["proc"] in PERTURBATION_PROCS or blocks[i].has("PERTURBATION")
                timing["pert"] = pert
                ctx, reqs, odb, add, own = None, [], False, False, []
                for x in inner:
                    if x.keyword == "OUTPUT":
                        ctx, odb = x, True
                        add = add or (x.param("OP") or "").strip().upper() in ("ADD", "REPLACE")
                        var = (x.param("VARIABLE") or "").strip().upper()
                        if not x.has("FIELD"):
                            if var in ("PRESELECT", "ALL"):
                                self._out_notes.setdefault(id(x), []).append(
                                    f"*OUTPUT, HISTORY, VARIABLE={var}: Abaqus' preselected history "
                                    f"output (whole-model energies ALLIE, ALLKE, ...) has no ccx "
                                    f"counterpart; dropped.")
                            continue
                        if var in ("PRESELECT", "ALL"):
                            own.append((x, None))
                            reqs += self._preselect_requests(x, x, timing, var, quiet, k)
                    elif x.keyword in OUTPUT_CARDS:
                        sub = x.keyword in ("NODE OUTPUT", "ELEMENT OUTPUT", "CONTACT OUTPUT")
                        if sub and ctx is not None and ctx.has("FIELD") and \
                                (ctx.param("VARIABLE") or "").strip().upper() == "ALL":
                            self._out_notes.setdefault(id(ctx), []).append(
                                f"*{x.keyword} under *OUTPUT, FIELD, VARIABLE=ALL dropped (Abaqus "
                                f"ignores the individual requests then).")
                            self._out_plan[id(x)] = {"cc": None, "cards": [], "notes": [],
                                                     "warnings": [], "out2d": False}
                            continue
                        src = self._preselect_card(x, ctx, timing) if sub else x
                        if src is None:     # a preselected request with no ccx label here
                            self._out_plan[id(x)] = {"cc": None, "cards": [], "warnings": [],
                                                     "out2d": False, "notes": [
                                f"*{x.keyword}, VARIABLE=PRESELECT in a *{timing['proc']} step: "
                                f"Abaqus preselects no such variable there; dropped."]}
                            continue
                        if sub and ctx is not None and ctx.has("FIELD"):
                            own.append((x, ctx))
                        r = self._output_request(src, ctx, timing, quiet)
                        r["anchor"] = x
                        reqs.append(r)
                if odb and not add:
                    carried[pert] = own
                else:
                    # Abaqus: a step without output database requests keeps those in force —
                    # of the previous general step, or of the previous step when both are
                    # perturbation steps — and the first such step writes the preselected
                    # output; OP=ADD / REPLACE keeps them beside the step's own.  ccx keeps
                    # its cards too, but at the previous step's frequency (or time points)
                    # and as a step in between left them, so they are written again
                    held = carried[pert] if (not pert or prev_pert) else None
                    reqs += self._carried_requests(blocks[i], held, timing, quiet, k)
                    carried[pert] = (held if held is not None else [("DEFAULT", None)]) + own
                prev_pert = pert
                steps.append((k, timing, reqs))
                i = j
            i += 1
        self._contact_requests_checked(steps)
        # one .frd node set per variable and step: the whole model before a set, several
        # sets joined into one
        unions: Dict[Tuple[str, ...], str] = {}
        for k, timing, reqs in steps:
            node_files = [r for r in reqs if r["live"] and r["cc"] == "NODE FILE"]
            want: "OrderedDict[str, List[Optional[str]]]" = OrderedDict()
            for r in node_files:
                for lab in r["labels"]:
                    sets = want.setdefault(lab, [])
                    if r["set"] not in sets:
                        sets.append(r["set"])
            final: Dict[str, Optional[str]] = {}
            for lab, sets in want.items():
                if None in sets or len(sets) == 1:
                    final[lab] = None if None in sets else sets[0]
                    continue
                key = tuple(sorted(sets))
                if key not in unions:
                    unions[key] = self._fresh_name("ABQ2CCX_OUTPUT")
                    self.geom.nsets[unions[key]] = dedup([n for s in key for n in self.geom.nset(s)])
                final[lab] = unions[key]
                node_files[0]["notes"].append(
                    f"*NODE FILE: {lab} requested on node sets {', '.join(sets)} in one step -> "
                    f"their union, node set {final[lab]} (a ccx .frd keeps one node set per "
                    f"variable; the last card's would replace the others).")
            done: set = set()
            for r in node_files:
                groups: "OrderedDict[Optional[str], List[str]]" = OrderedDict()
                for lab in r["labels"]:
                    s = final[lab]
                    if s is None and r["set"] is not None:
                        r["covered"].append(lab)
                        r["notes"].append(
                            f"*NODE FILE, NSET={r['set']}: {lab} left to the step's whole-model "
                            f"request (a ccx .frd keeps one node set per variable, so the set "
                            f"would replace the whole model).")
                        continue
                    if (lab, s) not in done:
                        done.add((lab, s))
                        groups.setdefault(s, []).append(lab)
                r["frd_sets"] = list(groups.items())
        # OUTPUT=2D when the beam/shell nodes of a .frd set would be missing from the .frd
        # and every .frd request of the deck is one OUTPUT=2D keeps exact
        stated = next((v.strip().upper() for _k, _t, reqs in steps[:1] for r in reqs
                       for v in [r["b"].param("OUTPUT")] if r["frd"] and v), None)
        frd_reqs = [r for _k, _t, reqs in steps for r in reqs if r["live"] and r["frd"]]
        hidden_flat = any(s is not None and any(n in flat_nodes and n not in solid_nodes
                                                for n in self.geom.nset(s))
                          for r in frd_reqs if r["cc"] == "NODE FILE" for s, _l in r["frd_sets"])
        shown = solid_nodes | flat_nodes
        carrier = next((r for r in (steps[0][2] if steps else [])
                        if r["live"] and r["cc"] == "NODE FILE" and
                        any(s is None or any(n in shown for n in self.geom.nset(s))
                            for s, _l in r["frd_sets"])), None)
        out2d = (frd3d and stated is None and hidden_flat and carrier is not None and
                 all(r["cc"] == "NODE FILE" and set(r["labels"]) <= FRD_2D_EXACT_LABELS
                     for r in frd_reqs))
        if out2d:
            carrier["out2d"] = True
            carrier["notes"].append(
                "OUTPUT=2D added to the first *NODE FILE: ccx writes a model with beams or "
                "shells to the .frd expanded to 3-D, without the original nodes the deck "
                "requests output at; OUTPUT=2D (for the whole run) maps the results back onto "
                "them — exact for U, V and RF, the only .frd variables the deck requests.")
        two_d = stated == "2D" or (stated is None and (not frd3d or out2d))
        visible = solid_nodes | (flat_nodes if two_d else set())
        for k, timing, reqs in steps:
            self._out_ctl[k] = self._step_output_control(k, timing, reqs)
            for r in reqs:
                # the cards are written where their anchor stands: the output card itself, the
                # *OUTPUT of a preselected request, or the *STEP of Abaqus' default output
                p = self._out_plan.setdefault(id(r.get("anchor", r["b"])), {
                    "cc": r["cc"], "src": r["b"], "cards": [], "notes": [], "warnings": [],
                    "out2d": False})
                p["cards"] += self._request_cards(r, visible)
                p["notes"] += r["notes"]
                p["warnings"] += r["warnings"]
                p["out2d"] = p["out2d"] or r.get("out2d", False)

    def _output_request(self, b: Block, ctx: Optional[Block], timing: dict, quiet: "Report") -> dict:
        """One output card of a step: where it goes, its labels and the output control it
        asks for."""
        sub = b.keyword in ("NODE OUTPUT", "ELEMENT OUTPUT", "CONTACT OUTPUT")
        ctx = ctx if sub else None
        cc = self._output_route(b, ctx)
        if cc == "CONTACT FILE":
            params, labels = self._contact_card(b, quiet)
        else:
            params, labels = self._output_card(b, cc, quiet)
        ctl, default = self._requested_control(b, ctx, timing)
        r = {"b": b, "cc": cc, "params": params, "labels": labels, "notes": [], "warnings": [],
             "frd": cc in ("NODE FILE", "EL FILE", "CONTACT FILE"), "frd_sets": [], "covered": [],
             "set": (params.get("NSET") or "").strip().upper() or None if cc == "NODE FILE" else None,
             "ctl": ctl, "default": default, "live": labels is not None and ctl[0] != "OFF"}
        if labels is not None and ctl[0] == "OFF":
            r["notes"].append(f"*{b.keyword} with {ctl[1]}=0 dropped (output suppressed)." if ctx is None
                              else f"*OUTPUT with {ctl[1]}=0: Abaqus writes none of its requests; "
                                   f"*{b.keyword} dropped.")
        if r["live"] and cc == "CONTACT FILE" and not self._out_contact["pairs"]:
            r["live"] = False               # see _contact_requests_checked
            r["notes"].append(f"*{b.keyword} dropped: {CONTACT_OUTPUT_ISSUES['nopair']}.")
        if r["live"] and cc in ("NODE PRINT", "EL PRINT") and sub:
            kind, key = ("node", "NSET") if cc == "NODE PRINT" else ("element", "ELSET")
            name = params[key].strip().upper()
            pool = self.geom.nsets if kind == "node" else self.geom.elsets
            if not pool.get(name):
                r["live"] = False
                r["warnings"].append(f"History *{b.keyword}, {key}={params[key]}: the {kind} set "
                                     f"is not defined (or empty) in the converted deck; dropped.")
            else:
                r["notes"].append(
                    "*OUTPUT, HISTORY: *NODE OUTPUT, NSET= -> *NODE PRINT and *ELEMENT OUTPUT, "
                    "ELSET= -> *EL PRINT (.dat, every output increment, like Abaqus history "
                    "output): a ccx .frd keeps one node set per variable, so a history set "
                    "would replace the step's field output, and it has no values at beam or "
                    "shell nodes or at reference points.")
        return r

    def _yielding_materials(self, blocks: List[Block]) -> bool:
        """Whether a material of the deck yields or creeps in ccx (a *PLASTIC card the
        converter keeps, or *CREEP): ccx writes PEEQ only then, and warns otherwise."""
        return any((b.keyword == "PLASTIC" and self._plastic_kept(b)) or b.keyword == "CREEP"
                   for b in blocks)

    def _contact_output_issues(self) -> List[str]:
        """Why ccx 2.23 cannot write the model's contact output, as CONTACT_OUTPUT_ISSUES
        keys, the most telling first: no ccx contact pair; the abort in a model with
        axisymmetric elements (unless every pair is face-to-face); node-to-surface contact of
        plane, axisymmetric or membrane elements, written at nodes the .frd does not hold."""
        c = self._out_contact
        issues = [] if c["pairs"] else ["nopair"]
        if c["axi"] and (c["nts"] or not c["pairs"]):
            issues.append("abort")
        if c["flat"] and c["nts"]:
            issues.append("expanded")
        return issues

    def _contact_requests_checked(self, steps: List[Tuple[int, dict, List[dict]]]) -> None:
        """The deck's own contact output requests against _contact_output_issues (Abaqus'
        preselected contact output is planned only where ccx writes it; a request in a model
        without a ccx contact pair is dropped when it is made, _output_request): dropped where
        ccx 2.23 would abort — a model with axisymmetric elements that writes S to the .frd
        as well —, noted where ccx writes them at nodes the .frd does not hold."""
        issues = self._contact_output_issues()
        reqs = [r for _k, _t, step in steps for r in step if r["live"]]
        stress = any(r["cc"] == "EL FILE" and "S" in r["labels"] for r in reqs)
        for r in (r for r in reqs if r["cc"] == "CONTACT FILE"):
            if "abort" in issues and stress:
                r["live"] = False
                r["warnings"].append(f"*{r['b'].keyword} dropped: {CONTACT_OUTPUT_ISSUES['abort']}.")
            elif "expanded" in issues:
                r["notes"].append(f"*{r['b'].keyword}: {CONTACT_OUTPUT_ISSUES['expanded']}.")

    def _preselect_labels(self, proc: Optional[str], var: str) -> Tuple[List[str], List[str]]:
        """(*NODE FILE labels, *EL FILE labels) of Abaqus' preselected field output in a
        ``proc`` step (PRESELECT_FIELD); VARIABLE=ALL adds the strain energy density (not
        the state variables: SDV on a model with *DEPVAR but no user material crashes ccx
        2.23, probed)."""
        node, elem = PRESELECT_FIELD.get(proc or "", ((), ()))
        elem = [x for x in elem if x != "PEEQ" or self._out_yields]
        if var == "ALL" and "S" in elem:
            elem.append("ENER")
        return list(node), elem

    def _preselect_requests(self, anchor: Block, ctx: Block, timing: dict, var: str,
                            quiet: "Report", k: int, why: str = "") -> List[dict]:
        """The whole-model *NODE FILE / *EL FILE / *CONTACT FILE requests of Abaqus'
        preselected field output (``var`` PRESELECT or ALL) for step ``k``, under *OUTPUT
        ``ctx`` (its frequency applies), written where ``anchor`` stands: the *OUTPUT card, or
        the *STEP of a step without output database requests (``why``): 'default', the
        output Abaqus writes then, or 'carried', an earlier step's preselected request, whose
        variables change with the procedure.  Its contact output (PRESELECT_CONTACT) only
        where ccx writes it for the model (_contact_output_issues)."""
        node, elem = self._preselect_labels(timing["proc"], var)
        key = "EXPLICIT" if timing["kind"] == "explicit" else timing["proc"]
        abq_contact, contact = self._preselect_contact(timing)
        issues = self._contact_output_issues() if contact else []
        if issues:
            contact = ()
        reqs = []
        for kw, labels in (("NODE OUTPUT", node), ("ELEMENT OUTPUT", elem),
                           ("CONTACT OUTPUT", contact)):
            if labels:
                r = self._output_request(mkblock(kw, None, [", ".join(labels)]), ctx, timing, quiet)
                r["anchor"] = anchor
                reqs.append(r)
        proc = f"*{timing['proc']}" if timing["proc"] else "an unknown"
        cards = " and ".join(f"*{cc} {', '.join(labels)}" for cc, labels in
                             (("NODE FILE", node), ("EL FILE", elem), ("CONTACT FILE", contact))
                             if labels)
        if not reqs:
            if not why:
                self._out_notes.setdefault(id(anchor), []).append(
                    f"*OUTPUT, FIELD, VARIABLE={var} in {proc} step: ccx has no counterpart of "
                    f"Abaqus' preselected field output there; dropped.")
            return reqs
        if not any(r["live"] for r in reqs):        # FREQUENCY=0: none of it is written
            for r in reqs:
                r["notes"] = []
            reqs[0]["notes"].append(f"*OUTPUT, FIELD, VARIABLE={var} with {reqs[0]['ctl'][1]}=0: "
                                    f"Abaqus writes none of it; nothing written.")
            return reqs
        lost = [f"no ccx label for {PRESELECT_NO_CCX[key]}"] if PRESELECT_NO_CCX.get(key or "") else []
        if issues and (issues[0] != "nopair" or self._out_contact["abaqus"]):
            lost.append(f"{abq_contact} left out: {CONTACT_OUTPUT_ISSUES[issues[0]]}")
        lost = f" ({'; '.join(lost)})" if lost else ""
        if why == "default":
            reqs[0]["notes"].append(
                f"Step {k} ({proc}) requests no output database output and inherits none, so "
                f"Abaqus writes its preselected field output -> {cards} added{lost}.")
        elif why:
            reqs[0]["notes"].append(
                f"Step {k} ({proc}) carries over an earlier step's preselected field output "
                f"(Abaqus) -> {cards} written again{lost}: ccx keeps its cards too, but at the "
                f"earlier step's output frequency and variables.")
        else:
            reqs[0]["notes"].append(
                f"*OUTPUT, FIELD, VARIABLE={var} in {proc} step -> {cards}: Abaqus' "
                f"{'preselected' if var == 'PRESELECT' else 'applicable'} field output in ccx "
                f"labels{lost}.")
        return reqs

    @staticmethod
    def _preselect_contact(timing: dict) -> Tuple[str, Tuple[str, ...]]:
        """(Abaqus variables, ccx *CONTACT FILE labels) of the contact output Abaqus
        preselects in a step (PRESELECT_CONTACT); none in a linear perturbation step."""
        if timing.get("pert"):
            return "", ()
        key = "EXPLICIT" if timing["kind"] == "explicit" else timing["proc"]
        return PRESELECT_CONTACT.get(key or "", ("", ()))

    def _preselect_card(self, b: Block, ctx: Optional[Block], timing: dict) -> Optional[Block]:
        """A field *NODE OUTPUT / *ELEMENT OUTPUT / *CONTACT OUTPUT with VARIABLE=PRESELECT
        (the procedure's preselected variables of that kind, plus the ones it names) or
        VARIABLE=ALL (the names ignored, as Abaqus does) as the plain card the planner reads;
        None when nothing is left; any other card unchanged."""
        var = (b.param("VARIABLE") or "").strip().upper()
        if var not in ("PRESELECT", "ALL") or ctx is None or not ctx.has("FIELD"):
            return b
        if b.keyword == "CONTACT OUTPUT":
            labels = self._preselect_contact(timing)[1]
        else:
            node, elem = self._preselect_labels(timing["proc"], var)
            labels = node if b.keyword == "NODE OUTPUT" else elem
        own = [] if var == "ALL" else [v for rec in merged_data_records(b) for v in rec if v != ""]
        if not labels and not own:
            return None
        return mkblock(b.keyword, [(p, v) for p, v in b.params.items() if p != "VARIABLE"],
                       [", ".join(dedup_str(list(labels) + own))])

    def _carried_requests(self, anchor: Block, held: Optional[list], timing: dict,
                          quiet: "Report", k: int) -> List[dict]:
        """The field output requests step ``k`` carries over (``held``, see _plan_output) as
        requests written at its *STEP ``anchor``: the cards of the step that made them, at
        their *OUTPUT's frequency and with this step's preselected variables; Abaqus'
        preselected default when ``held`` is None."""
        if held is None:
            return self._preselect_requests(anchor, mkblock("OUTPUT", [("FIELD", None)]), timing,
                                            "PRESELECT", quiet, k, why="default")
        reqs: List[dict] = []
        listed: List[dict] = []
        for x, ctx in held:
            if x == "DEFAULT":
                reqs += self._preselect_requests(anchor, mkblock("OUTPUT", [("FIELD", None)]),
                                                 timing, "PRESELECT", quiet, k, why="carried")
            elif x.keyword == "OUTPUT":
                reqs += self._preselect_requests(anchor, x, timing,
                                                 (x.param("VARIABLE") or "").strip().upper(),
                                                 quiet, k, why="carried")
            else:
                src = self._preselect_card(x, ctx, timing)
                if src is not None:
                    r = self._output_request(src, ctx, timing, quiet)
                    r["anchor"] = anchor
                    listed.append(r)
        written = [r for r in listed if r["live"]]
        if written:
            written[0]["notes"].append(
                f"Step {k} carries over the field output requests of an earlier step (Abaqus) "
                f"-> their cards written again: ccx keeps them too, but at the earlier step's "
                f"output frequency and as a step in between left them.")
        return reqs + listed

    def _request_cards(self, r: dict, visible: set) -> List[tuple]:
        """The ccx cards of output request ``r`` (see _plan_output): a .frd node set with
        nodes the .frd lacks is printed (.dat) too, and leaves the .frd when none of its
        nodes is there — also when the step's whole-model request covers the set, which
        lacks those nodes as well."""
        if not r["live"]:
            return []
        if r["cc"] != "NODE FILE":
            return [(r["cc"], r["params"], r["labels"])]
        cards: List[tuple] = []
        parts = [(s, labels, False) for s, labels in r["frd_sets"]]
        if r["covered"]:
            parts.append((r["set"], r["covered"], True))
        for s, labels, covered in parts:
            params = OrderedDict((k, v) for k, v in r["params"].items() if k != "NSET")
            if s is not None:
                params["NSET"] = r["params"]["NSET"] if s == r["set"] else s
            twin = None
            if s is not None:
                ids = [n for n in dedup(self.geom.nset(s)) if n in self.geom.nodes]
                hidden = [n for n in ids if n not in visible]
                if hidden:
                    plabels = [x for x in labels if ccx_label_ok(x, CCX_NODE_PRINT_LABELS)]
                    whole = len(hidden) == len(ids)
                    if plabels:
                        name = r["params"]["NSET"] if s == r["set"] else s
                        if not whole:
                            if s not in self._out_subsets:
                                self._out_subsets[s] = self._fresh_name(f"{s}_DAT")
                                self.geom.nsets[self._out_subsets[s]] = hidden
                            name = self._out_subsets[s]
                        twin = ("NODE PRINT", OrderedDict([("NSET", name)]), plabels)
                    r["notes"].append(
                        f"*NODE FILE, NSET={s}: {'its' if whole else f'{len(hidden)} of its'} nodes "
                        f"are not in a ccx .frd (ccx writes beam and shell models expanded to 3-D, "
                        f"without the original nodes, and never writes a node of no element) -> "
                        + (f"*NODE PRINT, NSET={twin[1]['NSET']} (.dat)" if twin else "no ccx output")
                        + (" instead." if whole else " for those."))
                    if whole:
                        labels = []
            if labels and not covered:
                cards.append(("NODE FILE", params, labels))
            if twin:
                same = next((c for c in cards if c[0] == "NODE PRINT" and c[1] == twin[1]), None)
                if same:
                    same[2].extend(x for x in twin[2] if x not in same[2])
                else:
                    cards.append(twin)
        return cards

    @staticmethod
    def _step_timing(proc: Optional[Block]) -> dict:
        """How ccx increments a step: kind 'untimed' (no time increments), 'explicit',
        'fixed' (DIRECT, *MODAL DYNAMIC: every increment the data line's first value) or
        'auto' (ccx picks the increments); its period, fixed increment and (explicit)
        maximum increment."""
        t = {"kind": "auto", "proc": proc.keyword if proc else None, "period": 1.0,
             "dt": None, "dtmax": None}
        if proc is None:
            return t
        if proc.keyword in UNTIMED_PROCS:
            t["kind"] = "untimed"
            return t
        vals = next((r for r in merged_data_records(proc) if any(x for x in r)), [])

        def num(i: int) -> Optional[float]:
            try:
                v = pf(vals[i])
            except (IndexError, ValueError):
                return None
            return v if math.isfinite(v) and v > 0 else None
        t["period"] = num(1) or 1.0
        direct = proc.has("DIRECT") or proc.has("DIRECT USER CONTROL")
        if proc.keyword == "DYNAMIC" and proc.has("EXPLICIT"):
            t.update(kind="explicit", dt=num(0) if direct else None, dtmax=num(3))
        elif proc.keyword == "MODAL DYNAMIC" or direct:
            t.update(kind="fixed", dt=num(0))
        return t

    @staticmethod
    def _requested_control(b: Block, ctx: Optional[Block], timing: dict) -> Tuple[tuple, bool]:
        """(control, defaulted): the output control output card ``b`` (following *OUTPUT
        ``ctx``) asks for — ('F', n) every n increments, ('D', dt) every dt of step time,
        ('N', n) n equal intervals of the step, ('P', name) a *TIME POINTS sequence, ('OFF',
        parameter) — and whether it is the Abaqus default: every increment, every 10 in
        *DYNAMIC and *MODAL DYNAMIC, and in explicit dynamics 20 intervals for field and
        200 for history output."""
        for src in (b,) if ctx is None else (b, ctx):
            p = src.params
            for key in ("FREQUENCY", "FREQ", "NUMBER INTERVAL"):
                if key in p:
                    try:
                        n = int(pf((p[key] or "").strip()))
                    except ValueError:
                        continue
                    if n <= 0:
                        return ("OFF", key), False
                    return (("N", n) if key == "NUMBER INTERVAL" else ("F", n)), False
            if "TIME INTERVAL" in p:
                try:
                    dt = pf((p["TIME INTERVAL"] or "").strip())
                except ValueError:
                    dt = 0.0
                if dt > 0 and math.isfinite(dt):
                    return ("D", dt), False
            if (p.get("TIME POINTS") or "").strip():
                return ("P", p["TIME POINTS"].strip().upper()), False
        if ctx is not None:
            if timing["kind"] == "explicit":
                return ("N", 200 if ctx.has("HISTORY") else 20), True
            if timing["proc"] in ("DYNAMIC", "MODAL DYNAMIC"):
                return ("F", 10), True
        return ("F", 1), True

    def _step_output_control(self, k: int, timing: dict, reqs: List[dict]) -> Optional[Tuple[str, str]]:
        """The one output control ccx can give step ``k`` (as FREQUENCY= or TIME POINTS=):
        its .frd requests' (or, without any, its .dat requests'); the .dat requests' when
        the .frd's cannot be given.  None when the step has no time increments or nothing
        can be given.  Notes go to the step's first request."""
        live = [r for r in reqs if r["live"]]
        if not live or timing["kind"] == "untimed":
            return None
        frd = [r for r in live if r["frd"]]
        dat = [r for r in live if not r["frd"]]
        groups = [frd, dat] if frd and dat else [frd or dat]
        msgs = live[0]["notes"]
        spacing = None
        for group in groups:
            ctl = self._group_control(timing, group, msgs)
            if ctl[0] == "NONE":
                spacing = ctl[1] if spacing is None else spacing
                continue
            others = [r for g in groups if g is not group for r in g]
            if any(r["ctl"] != group[0]["ctl"] for r in others):
                msgs.append("ccx writes all output of a step at one frequency (Abaqus gives each "
                            "request its own): " + ("the .dat (print / history) requests follow "
                                                    "the .frd requests'." if group is frd else
                                                    "the .frd requests here follow the .dat "
                                                    "requests', whose frequency ccx can give."))
            return ctl
        if timing["kind"] == "explicit":
            live[0]["warnings"].append(
                f"Step {k}: output every {fmt_num(spacing)} of step time (*OUTPUT NUMBER INTERVAL "
                f"/ TIME INTERVAL, or the Abaqus/Explicit default of 20 field / 200 history "
                f"intervals) cannot be given in ccx explicit dynamics, which ignores TIME POINTS "
                f"and writes every increment: set FREQUENCY=N on the step's first output card, "
                f"N = {fmt_num(spacing)} / the increment ccx reports as 'SELECTED time "
                f"increment'.")
        else:
            live[0]["warnings"].append(
                f"Step {k}: output every {fmt_num(spacing)} of step time cannot be given (the "
                f"step has fixed increments, but its data line names none); ccx writes every "
                f"increment.")
        return None

    def _group_control(self, timing: dict, group: List[dict], msgs: List[str]) -> Tuple[str, object]:
        """The ccx control for the requests ``group`` of a step (see _step_output_control):
        (parameter, value), or ('NONE', spacing) if ccx cannot give output every
        ``spacing`` of step time there."""
        ctls = [r["ctl"] for r in group]
        freqs = [c[1] for c in ctls if c[0] == "F"]
        timed = [c for c in ctls if c[0] != "F"]
        if freqs:
            if timed:
                msgs.append("ccx writes all output of a step at one frequency: the requests at "
                            "time intervals here follow the ones every so many increments.")
            if all(r["default"] for r in group) and freqs[0] == 10:
                msgs.append(f"*{timing['proc']}: output every 10 increments, the Abaqus default "
                            f"for this procedure (ccx's is every increment).")
            return ("FREQUENCY", str(math.gcd(*freqs)))
        times = self._control_times(timed, timing["period"])
        if timing["kind"] == "auto":
            if len(set(timed)) == 1 and timed[0][0] == "P" and timed[0][1] in self._out_user_tp:
                return ("TIME POINTS", self._out_user_tp[timed[0][1]].param("NAME").strip())
            return ("TIME POINTS", self._time_points_card(times, timing["period"]))
        if times[0] == "U":
            spacing = times[1]
        else:
            gaps = [b - a for a, b in zip((0.0,) + times[1], times[1])]
            spacing = min((g for g in gaps if g > 1e-12 * timing["period"]), default=timing["period"])
        if timing["dt"]:
            n = max(1, int(round(spacing / timing["dt"])))
            msgs.append(f"Output every {fmt_num(spacing)} of step time in a step with fixed "
                        f"increments of {fmt_num(timing['dt'])} -> FREQUENCY={n} (ccx takes TIME "
                        f"POINTS only where it picks the increments; DIRECT and *MODAL DYNAMIC "
                        f"stop on them).")
            return ("FREQUENCY", str(n))
        sizes = [(v, what) for v, what in ((timing["dtmax"], "the maximum increment"),
                                           (timing.get("dtstable"), "ccx's stable increment"))
                 if v]
        if sizes:
            inc, what = min(sizes)
            n = max(1, int(spacing / inc + 1e-9))
            how = ("" if what.startswith("the") else " as abq2ccx estimates it with ccx's "
                   "Courant formula (calcstabletimeincvol.f)")
            msgs.append(f"Explicit output every {fmt_num(spacing)} of step time -> FREQUENCY={n} "
                        f"from {what} {'%.3g' % inc}{how} (ccx ignores TIME POINTS in explicit "
                        f"dynamics; where contact makes its increment smaller, the output comes "
                        f"more often).")
            return ("FREQUENCY", str(n))
        return ("NONE", spacing)

    def _control_times(self, timed: List[tuple], period: float) -> tuple:
        """Time-based controls of one step -> ('U', dt) every dt of step time, or ('L',
        times) the sorted union of their times."""
        if all(c[0] in ("N", "D") for c in timed):
            dts = sorted({period / c[1] if c[0] == "N" else c[1] for c in timed})
            if all(abs(d / dts[0] - round(d / dts[0])) < 1e-6 for d in dts):
                return ("U", dts[0])
        pts: set = set()
        for c in timed:
            if c[0] == "P":
                pts.update(self._user_time_points(c[1]))
            else:
                dt = period / c[1] if c[0] == "N" else c[1]
                count = min(int(period / dt + 1e-9), 100000)
                pts.update(round(i * dt, 12) for i in range(1, count + 1))
        pts.add(period)
        return ("L", tuple(sorted(pts)))

    def _user_time_points(self, name: str) -> List[float]:
        """The times of the deck's *TIME POINTS ``name`` (empty if it has none)."""
        b = self._out_user_tp.get(name)
        if b is None:
            return []
        out: List[float] = []
        for rec in merged_data_records(b):
            try:
                vals = [pf(x) for x in rec if x != ""]
            except ValueError:
                continue
            if b.has("GENERATE") and len(vals) >= 3 and vals[2] > 0:
                n = min(int((vals[1] - vals[0]) / vals[2] + 1e-9), 100000)
                out += [vals[0] + i * vals[2] for i in range(n + 1)] + [vals[1]]
            elif not b.has("GENERATE"):
                out += vals
        return [t for t in out if t > 0]

    def _time_points_card(self, times: tuple, period: float) -> str:
        """A *TIME POINTS card (emitted before the first *STEP) for ``times``; its name."""
        key = (times[0], round(times[1], 12) if times[0] == "U" else times[1], round(period, 12))
        if key in self._out_tp_names:
            return self._out_tp_names[key]
        n = len(self._out_tp_names) + 1
        name = f"ABQ2CCX_TP{n}"
        while name in self._out_amp_names:
            n += 1
            name = f"ABQ2CCX_TP{n}"
        self._out_amp_names.add(name)
        self._out_tp_names[key] = name
        if times[0] == "U":
            self._out_tp_cards += [f"*TIME POINTS, NAME={name}, GENERATE",
                                   f"{fmt_num(times[1])}, {fmt_num(period)}, {fmt_num(times[1])}"]
        else:
            self._out_tp_cards += [f"*TIME POINTS, NAME={name}"] + reflow(list(times), 8)
        self.report.note("*OUTPUT NUMBER INTERVAL / TIME INTERVAL -> *TIME POINTS (ccx writes "
                         "the output at those times of the step, cutting increments to reach "
                         "them, as Abaqus' TIME MARKS=YES).", once=True)
        return name

    def handle_mpc(self, b: Block) -> List[str]:
        """Abaqus ``*MPC``, converted line by line (a line ccx cannot take is commented out
        on its own, the rest of the card is kept), from the deck-wide plan of _plan_mpcs:

        * PLANE / STRAIGHT: native ccx MPCs, kept;
        * PIN (equal displacements) and TIE (all common DOFs equal) -> per-DOF *EQUATION,
          exact; TIE ties rotations only between shell/beam nodes, which get knot beams —
          ccx ignores DOFs 4-6 of a non-knot shell/beam node in an *EQUATION (probed: a
          tied beam joint stays a hinge);
        * LINK (constant distance, rotations free) -> its linearised *EQUATION when no step
          runs NLGEOM, else ccx's *MPC BEAM, which keeps the distance between two nodes
          (probed) but rejects nodes of beam/truss/shell/membrane/plane elements;
        * BEAM (rigid beam: displacements AND rotations) -> one *RIGID BODY per independent
          node, emitted at the card where its first line appears;
        * user MPCs (a numeric type) and the other Abaqus types are commented out."""
        native: List[str] = []
        eqs: List[str] = []
        skipped: "OrderedDict[str, List[str]]" = OrderedDict()     # reason -> lines
        for i, f in enumerate(self._mpc_fields(b)):
            typ = f[0].upper()
            line = ", ".join(f)
            mode, arg = self._mpc_plan.get((id(b), i), (None, None))
            if typ in ("PLANE", "STRAIGHT") and not b.has("USER"):
                native.append(line)
            elif re.fullmatch(r"[-+]?\d+", typ) or b.has("USER"):
                skipped.setdefault(f"*MPC user type {typ}: ccx runs user MPCs only from its own "
                                   f"compiled umpc routine, and the Abaqus MPC subroutine cannot "
                                   f"be used; commented out — the constraint is missing.",
                                   []).append(line)
            elif mode == "skip" or mode is None:
                skipped.setdefault(arg or f"*MPC {typ} has no ccx equivalent the converter can "
                                          f"write (supported: PIN, TIE, LINK, BEAM, PLANE, "
                                          f"STRAIGHT); commented out — the constraint is missing.",
                                   []).append(line)
            elif mode == "beam":
                continue                    # part of a *RIGID BODY (self._mpc_bodies)
            elif mode == "link-mpc":
                native += [f"BEAM, {dep}, {ind}" for dep, ind in arg]
            elif mode == "link-eq":
                self._warn_transformed_mpc(arg)
                for dep, ind in arg:
                    eqs += self._link_equation(dep, ind)
            else:                           # PIN / TIE
                self._warn_transformed_mpc(arg)
                for dep, ind in arg:
                    both = all(n in self._knots and n in self._rot_nodes for n in (dep, ind))
                    dofs = ((1, 2, 3, 4, 5, 6) if typ == "TIE" and both and self._tie_rotations
                            else (1, 2, 3)) if self._mpc_mechanical else ()
                    if typ == "TIE" and self._mpc_thermal:
                        dofs += (11,)
                    for d in dofs:
                        eqs += ["*EQUATION", "2", f"{dep}, {d}, 1., {ind}, {d}, -1."]
                    if typ == "TIE" and not both and any(n in self._rot_nodes for n in (dep, ind)):
                        self.report.warn("*MPC TIE between a shell/beam node and a node without "
                                         "rotations (solid or free node): only the displacements "
                                         "are tied — ccx has no rotations on the other node.",
                                         once=True)
                if typ == "PIN" and not self._mpc_mechanical:
                    self.report.note("*MPC PIN ties displacements only; a heat-transfer-only deck "
                                     "has none, so it was left out.", once=True)
                else:
                    self.report.note("*MPC PIN -> *EQUATION on DOFs 1-3 (equal displacements, "
                                     "rotations free; exact)." if typ == "PIN" else
                                     "*MPC TIE -> per-DOF *EQUATION (exact): displacements, the "
                                     "rotations of two shell/beam nodes (made ccx knots for it) "
                                     "and the temperature in thermal steps.", once=True)
        out: List[str] = []
        if native:
            out += ["*MPC"] + native
        out += eqs
        for body in self._mpc_bodies.get(id(b), []):
            out += self._mpc_rigid_body(body)
        for reason, lines in skipped.items():
            out += self._commented(mkblock("MPC", b.params.items(), lines), reason)
        return out

    def handle_connector_section(self, b: Block) -> List[str]:
        """``*CONNECTOR SECTION``: its connector elements as ccx constraints, from the plan of
        _plan_connectors / _plan_connector_rows — *BOUNDARY lines and *EQUATIONs (JOIN,
        REVOLUTE, ALIGN, HINGE; WELD / BEAM to ground), a *RIGID BODY (BEAM, WELD), a
        linearised *EQUATION or ccx's *MPC BEAM (LINK).  An element that cannot be converted
        is listed in a commented-out copy of the card, with the reason."""
        sec = self._conn_plan.get(id(b)) or \
            {"reason": f"*CONNECTOR SECTION on ELSET={(b.param('ELSET') or '').strip()}, which holds "
                       f"no connector element (CONN3D2 / CONN2D2); commented out."}
        if sec["reason"]:
            return self._commented(b, sec["reason"])
        out: List[str] = []
        bcs: List[str] = []
        skipped: "OrderedDict[str, List[dict]]" = OrderedDict()
        rows = approx = local = False
        for it in sec["items"]:
            if it["route"] == "skip":
                skipped.setdefault(it["reason"], []).append(it)
            elif it["route"] == "link":
                out += ["*MPC", f"BEAM, {it['b']}, {it['a']}"] if it["link"] == "link-mpc" else \
                    self._link_equation(it["b"], it["a"], local=True)
                local = local or (it["link"] == "link-eq" and any(
                    n in self._transformed for n in (it["a"], it["b"])))
            elif it["route"] == "rows":
                rows, approx = True, approx or bool(it.get("approx"))
                local = local or bool(it.get("local"))
                bcs += [f"{n}, {d}, {d}" for n, d in it["bcs"]]
                for eq in it["eqs"]:
                    out += ["*EQUATION", str(len(eq))]
                    out += [", ".join(f"{n}, {d}, {c:.12g}" for n, d, c in eq[i:i + 4])
                            for i in range(0, len(eq), 4)]
        if bcs:
            bcs = dedup_str(bcs)
            out = ["*BOUNDARY"] + bcs + out
            self._conn_bcs += [x for x in bcs if x not in self._conn_bcs]
        for body in self._mpc_bodies.get(id(b), []):
            out += self._mpc_rigid_body(body)
        if any(it["route"] == "beam" for it in sec["items"]):
            self.report.note("Connector BEAM / WELD (a rigid link) -> *RIGID BODY, like *MPC BEAM: "
                             "the nodes it links move as one rigid body, exact at any rotation.",
                             once=True)
        if rows:
            self.report.note("Connector elements -> ccx constraints (ccx has no connector element; "
                             "without a behaviour a connector is its kinematic constraint): JOIN "
                             "keeps node b at its initial offset in node a's local system, "
                             "REVOLUTE / HINGE leave only the rotation about node a's local "
                             "1-direction free, ALIGN locks the relative rotation — as *EQUATIONs "
                             "on the translations and rotation vectors (a reference point's "
                             "rotation on its ROT NODE, a shell/beam node's on a knot) and *BOUNDARY "
                             "lines where a side is grounded or held; exact in a linear analysis.",
                             once=True)
        if local:
            self.report.note("Connector constraints on nodes with a *TRANSFORM are written in each "
                             "node's local DOFs, in which ccx (like Abaqus) reads *EQUATION terms "
                             "and *BOUNDARY lines there, and a rotation on its rotation node's DOFs "
                             "in that node's local axes (probed on 2.23: the same results as the "
                             "model without the *TRANSFORM, linear and NLGEOM).", once=True)
        if approx:
            self.report.warn("[APPROX] Connector under NLGEOM written in its linear form: a "
                             "REVOLUTE / ALIGN between two moving nodes, or a JOIN offset that "
                             "turns with node a, holds for small rotations only, and ccx 2.23 "
                             "solves *EQUATIONs that link rigid bodies' reference / rotation DOFs "
                             "inaccurately under NLGEOM (probed: about 1 % at 30 degrees).",
                             once=True)
        for reason, its in skipped.items():
            listing = ", ".join(f"{it['eid']} (nodes {'ground' if it['a'] is None else it['a']}, "
                                f"{'ground' if it['b'] is None else it['b']})" for it in its)
            out += self._commented(mkblock("CONNECTOR SECTION", b.params.items(),
                                           list(b.data) + [f"connector element(s) {listing}"]),
                                   reason)
        return out

    def _warn_transformed_mpc(self, pairs: Sequence[Tuple[int, int]]) -> None:
        if any(n in self._transformed for p in pairs for n in p):
            self.report.warn("*MPC on a node with a *TRANSFORM: ccx reads the DOFs of the "
                             "*EQUATION it becomes in the node's local axes — verify that the "
                             "constraint acts in the directions intended.", once=True)

    def _link_equation(self, dep: int, ind: int, local: bool = False) -> List[str]:
        """Abaqus *MPC LINK in a deck without NLGEOM: the distance constraint linearised at
        the initial geometry, e . (u_dep - u_ind) = 0 with e the unit vector between the
        nodes — what Abaqus solves in a small-displacement analysis.  The dependent term is
        the first node's largest component.  ``local`` (connectors): the terms on a node with
        a *TRANSFORM are in its local DOFs, e . e_j for local DOF j — ccx reads them there,
        as Abaqus does — and a node without one is listed first (its DOF is eliminated)."""
        e = vunit(vsub(self.geom.nodes[dep], self.geom.nodes[ind]))
        ks = sorted((k for k in range(3) if abs(e[k]) > 1e-12), key=lambda k: -abs(e[k]))
        terms = [(dep, k + 1, e[k]) for k in ks] + [(ind, k + 1, -e[k]) for k in ks]
        if local and (dep in self._transformed or ind in self._transformed):
            terms = []
            first = ind if dep in self._transformed and ind not in self._transformed else dep
            for n in (first, dep if first == ind else ind):
                axes = self._local_axes(n) if n in self._transformed else \
                    ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
                c = [(j + 1, (1.0 if n == dep else -1.0) * vdot(e, axes[j])) for j in range(3)]
                terms += [(n, j, v) for j, v in sorted(c, key=lambda t: -abs(t[1])) if abs(v) > 1e-12]
        lines = ["*EQUATION", str(len(terms))]
        for j in range(0, len(terms), 4):
            lines.append(", ".join(f"{n}, {d}, {c:.12g}" for n, d, c in terms[j:j + 4]))
        return lines

    def _mpc_rigid_body(self, body: dict) -> List[str]:
        """The *RIGID BODY of a group of Abaqus *MPC BEAM lines (see _plan_mpcs): the
        dependent nodes follow the root node rigidly; the rotations of knotted shell/beam
        members are tied to the ROT NODE, which follows a shell/beam root's own rotation."""
        ref, rot, members = body["ref"], body["rot"], body["members"]
        self._synth_counter += 1
        name = f"ABQ2CCX_MPCB{self._synth_counter}"
        out = [f"*NSET, NSET={name}"] + reflow([str(n) for n in members])
        out.append(f"*RIGID BODY, NSET={name}, REF NODE={ref}, ROT NODE={rot}")
        if (ref in self._knots and ref in self._rot_nodes) or body.get("follow"):
            out += self._rot_node_follows(rot, ref)
        out += self._rotation_ties(members, rot, -3)
        self.report.note("*MPC BEAM -> *RIGID BODY: the lines that share an independent node "
                         "(or chain through one another) form one rigid body about it; the "
                         "dependent nodes follow it in displacement and rotation, exact at any "
                         "rotation (BCs and moments on the independent node's DOFs 4-6 act on "
                         "the body's rotation).", once=True)
        return out

    def handle_coupling(self, b: Block) -> List[str]:
        """Abaqus standalone ``*KINEMATIC COUPLING, REF NODE=r`` (data: node/nset, first DOF,
        last DOF — one line per member).  Every line is kept, as node surfaces with ccx
        ``*COUPLING`` + ``*KINEMATIC`` per DOF range (ccx couples translations; the reference
        node's rotations still drive them, and unlike *RIGID BODY its DOFs 4-6 take BCs and
        moments); rotation ranges on knotted shell/beam members become *EQUATION ties to
        those DOFs.  (The newer *COUPLING/*KINEMATIC/*DISTRIBUTING are native ccx keywords.)"""
        ref = (b.param("REF NODE") or b.param("REFNODE") or "").strip()
        recs = [[x for x in r if x != ""] for r in merged_data_records(b)]
        recs = [r for r in recs if r]
        if not ref or not recs:
            return self._commented(b, "*KINEMATIC COUPLING could not be converted (no REF NODE or "
                                      "no members); edit manually.")
        if not re.fullmatch(r"[-+]?\d+", ref) and self.geom.nset(ref):
            ref = str(self.geom.nset(ref)[0])
        groups: "OrderedDict[Tuple[int, int], List[str]]" = OrderedDict()
        try:
            for r in recs:
                d1 = pint(r[1]) if len(r) > 1 else 1
                d2 = pint(r[2]) if len(r) > 2 else (d1 if len(r) > 1 else 6)
                groups.setdefault((min(d1, d2), max(d1, d2)), []).append(r[0])
        except ValueError:
            return self._commented(b, "*KINEMATIC COUPLING DOF fields could not be parsed; edit "
                                      "manually.")
        members = [m for ms in groups.values() for m in ms]
        if (self._coupling_plan.get(id(b)) or {}).get("kind") == "unsupported":
            self._warn_rigid_unsupported()
        self._synth_counter += 1
        tag = f"ABQ2CCX_KC{self._synth_counter}"
        out: List[str] = []
        ties: List[str] = []
        top = 2 if id(b) in self._planar_kin else 3     # 2-D members: no DOF 3 (see handle_kinematic)
        # ccx carries the coupling's rotation on DOFs 4-6 of the reference node once a
        # translational group couples it, so knotted shell/beam members can tie theirs
        coupled = any(lo <= 3 for lo, _ in groups) and re.fullmatch(r"[-+]?\d+", ref) is not None
        for gi, ((lo, hi), ms) in enumerate(groups.items(), 1):
            nodes = [n for m in ms for n in self._resolve_nodes(m)]
            if hi > 3 and coupled:
                ties += self._rotation_ties(nodes, int(ref), 0, range(max(lo, 4), hi + 1))
            if hi > 3 and any(n in self._rot_nodes and n not in self._knots for n in nodes):
                self.report.warn("*KINEMATIC COUPLING DOFs above 3 clamped: ccx *KINEMATIC couples "
                                 "translations only, so the rotations of the coupled shell/beam "
                                 "nodes are free.", once=True)
            if lo > 3:
                if not any(n in self._knots for n in nodes) or not coupled:
                    self.report.warn("*KINEMATIC COUPLING line couples only rotational DOFs "
                                     "(4..6); ccx couples translations only — line dropped, "
                                     "rotations are NOT coupled.", once=True)
                continue
            if top == 2 and hi > 2:
                self._note_planar_kinematic()
                if lo > 2:
                    continue
            out += [f"*SURFACE, TYPE=NODE, NAME={tag}_{gi}"] + list(ms)
            out += [f"*COUPLING, CONSTRAINT NAME={tag}_{gi}, REF NODE={ref}, SURFACE={tag}_{gi}",
                    "*KINEMATIC", f"{lo}, {min(hi, top)}"]
        self.report.note("*KINEMATIC COUPLING -> node-surface *COUPLING + *KINEMATIC per DOF "
                         "range (every member line kept).", once=True)
        return (out + ties) or self._commented(b, "*KINEMATIC COUPLING couples no translational "
                                                  "DOF; dropped.")

    def _warn_rigid_unsupported(self) -> None:
        """The one rigid-coupling form the knot beams cannot repair (see
        _plan_rigid_couplings): a shell/beam reference node with only some translations
        coupled, or in a legacy *KINEMATIC COUPLING card."""
        self.report.warn("Rigid coupling (*KINEMATIC) whose reference node is a shell/beam node, "
                         "with only some translations coupled (or in a *KINEMATIC COUPLING card): "
                         "ccx implements it with RIGID MPCs, which ccx 2.23 (e.g. the FreeCAD 1.1 "
                         "build) rejects ('*ERROR in gen3dmpc: nodes belonging to shell elements "
                         "must not be subject to a RIGID MPC'), and the converter can only repair "
                         "full-translation couplings of such a node. Couple DOFs 1-3, or use a "
                         "separate reference point tied to the node.", once=True)

    def handle_creep(self, b: Block) -> List[str]:
        keep: "OrderedDict[str, Optional[str]]" = OrderedDict()
        law = (b.param("LAW") or "STRAIN").strip().upper()
        for k, v in b.params.items():
            if k == "LAW":
                vu = (v or "").upper()
                if vu in ("STRAIN", "TIME", "", "NORTON"):
                    self.report.note("*CREEP LAW=STRAIN/TIME -> ccx Norton law (A, n, m); LAW token "
                                     "dropped (Norton is the ccx default).", once=True)
                    continue  # Norton is ccx default
                self.report.warn(f"*CREEP LAW={v} has no ccx built-in equivalent; set to LAW=USER "
                                 f"(implement creep.f).", once=True)
                keep["LAW"] = "USER"
            else:
                keep[k] = v
        if law in ("STRAIN", ""):
            # Abaqus' default is STRAIN hardening; ccx's Norton law is TIME hardening.
            # They coincide only for m = 0 (steady-state creep) or a constant stress.
            for rec in merged_data_records(b):
                f = [x for x in rec if x != ""]
                try:
                    m = pf(f[2]) if len(f) > 2 else 0.0
                except ValueError:
                    continue
                if m != 0.0:
                    self.report.warn("*CREEP (Abaqus default LAW=STRAIN, strain hardening) -> ccx "
                                     "Norton law, which is TIME hardening: with m != 0 the creep "
                                     "strain differs whenever the stress changes. Verify.", once=True)
                    break
        return [emit_keyword("CREEP", keep)] + list(b.data)

    def handle_frequency(self, b: Block) -> List[str]:
        """``*FREQUENCY``: ccx's card knows SOLVER / STORAGE / GLOBAL / CYCMPC.  Abaqus'
        EIGENSOLVER, NORMALIZATION, SIM, ACOUSTIC COUPLING, ... are dropped.  With
        EIGENSOLVER=SUBSPACE the second data field is Abaqus' maximum frequency of
        interest, which ccx would read as the LOWER bound of the search — blanked."""
        keep: "OrderedDict[str, Optional[str]]" = OrderedDict()
        solver = (b.param("EIGENSOLVER") or "LANCZOS").strip().upper()
        for k, v in b.params.items():
            if k in ("SOLVER", "STORAGE", "GLOBAL", "CYCMPC"):
                keep[k] = v
            elif k == "NORMALIZATION":
                if (v or "").strip().upper().startswith("DISP"):
                    self.report.note("*FREQUENCY NORMALIZATION=DISPLACEMENT: ccx mass-normalizes "
                                     "the mode shapes, so their amplitudes differ (frequencies do "
                                     "not).", once=True)
            elif k == "EIGENSOLVER":
                continue
            else:
                self.report.note(f"*FREQUENCY parameter {k} dropped (Abaqus-only).", once=True)
        if self._freq_storage and "STORAGE" not in keep:
            keep["STORAGE"] = "YES"
            self.report.note("*FREQUENCY: STORAGE=YES added — a later modal / steady-state "
                             "dynamics step reads the eigenmodes from the .eig file ccx writes "
                             "only then.", once=True)
        data = list(b.data)
        if solver.startswith("SUB") and data:
            f = [x.strip() for x in data[0].split(",")]
            if len(f) > 1 and f[1]:
                f[1] = ""
                data[0] = ", ".join(f)
                self.report.warn("*FREQUENCY, EIGENSOLVER=SUBSPACE: the maximum frequency of "
                                 "interest (field 2) was blanked — ccx reads that field as the lower "
                                 "frequency bound.", once=True)
        if data:
            f = [x.strip() for x in data[0].split(",")]
            if not f[0] and any(f[1:3]):
                # Abaqus: blank count + a range = every mode in the range; ccx needs a
                # count ("less than 1 eigenvalue requested").  Stay below the DOF count:
                # ccx trims an oversized request but reports it as an *ERROR.
                f[0] = str(min(100, max(1, len(self.geom.nodes))))
                data[0] = ", ".join(f)
                self.report.note(f"*FREQUENCY: no number of modes given (Abaqus: all modes in the "
                                 f"frequency range) -> {f[0]} requested (ccx needs a count).", once=True)
        return [emit_keyword("FREQUENCY", keep)] + data

    def handle_buckle(self, b: Block) -> List[str]:
        """``*BUCKLE``: ccx data line = number of factors, accuracy, Lanczos vectors, max
        iterations.  Abaqus' subspace layout (n, max eigenvalue, vectors, iterations)
        differs only in field 2; the Lanczos layout (n, min, max, block size, ...) from
        field 2 on — those fields are blanked so ccx uses its defaults."""
        keep: "OrderedDict[str, Optional[str]]" = OrderedDict()
        solver = (b.param("EIGENSOLVER") or "SUBSPACE").strip().upper()
        for k, v in b.params.items():
            if k == "SOLVER":
                keep[k] = v
            elif k != "EIGENSOLVER":
                self.report.note(f"*BUCKLE parameter {k} dropped (Abaqus-only).", once=True)
        data = list(b.data)
        if data:
            f = [x.strip() for x in data[0].split(",")]
            dropped = f[1:] if solver.startswith("LANC") else f[1:2]
            if any(dropped):
                self.report.note("*BUCKLE: Abaqus eigensolver range/size fields blanked (those "
                                 "positions mean accuracy/vectors/iterations in ccx).", once=True)
            if solver.startswith("LANC"):
                f = f[:1]
            elif len(f) > 1:
                f[1] = ""
            while len(f) > 1 and f[-1] == "":
                f.pop()
            data[0] = ", ".join(f)
        return [emit_keyword("BUCKLE", keep)] + data

    def handle_heat_transfer(self, b: Block) -> List[str]:
        """``*HEAT TRANSFER``: Abaqus' END= (stop at steady state) and MXDEM have no ccx
        parameter; ccx keeps STEADY STATE, DELTMX, SOLVER, STORAGE, TIME RESET, ..."""
        keep: "OrderedDict[str, Optional[str]]" = OrderedDict()
        for k, v in b.params.items():
            if k in ("END", "MXDEM"):
                self.report.note(f"*HEAT TRANSFER {k}= dropped (no ccx equivalent; the step runs "
                                 f"its full time period).", once=True)
            else:
                keep[k] = v
        return [emit_keyword("HEAT TRANSFER", keep)] + list(b.data)

    def handle_tie(self, b: Block) -> List[str]:
        keep: "OrderedDict[str, Optional[str]]" = OrderedDict()
        for k, v in b.params.items():
            if k in ("NAME", "POSITION TOLERANCE", "ADJUST", "CYCLIC SYMMETRY", "MULTISTAGE"):
                if k == "ADJUST" and v and v.upper() not in ("YES", "NO"):
                    self.report.note(f"*TIE ADJUST={v}: ccx expects YES/NO; verify.", once=True)
                keep[k] = v
            elif k == "TYPE":
                self.report.note(f"*TIE TYPE={v} dropped (not a ccx parameter).", once=True)
            else:
                self.report.note(f"*TIE parameter {k} dropped (unsupported by ccx).", once=True)
        self.report.note("*TIE: in ccx the MASTER (independent, 2nd) surface must be element-based; "
                         "a node-based master will be rejected — verify surface roles.", once=True)
        return [emit_keyword("TIE", keep)] + list(b.data)

    def handle_restart(self, b: Block) -> List[str]:
        keep: "OrderedDict[str, Optional[str]]" = OrderedDict()
        for k, v in b.params.items():
            if k in ("WRITE", "READ", "FREQUENCY", "STEP"):
                keep[k] = v
            else:
                self.report.note(f"*RESTART parameter {k} dropped (unsupported by ccx).", once=True)
        return [emit_keyword("RESTART", keep)] + list(b.data)

    def handle_amplitude(self, b: Block) -> List[str]:
        if (b.param("NAME") or "").strip().upper() in self._vel_only_amps:
            self.report.note("*AMPLITUDE used only by *BOUNDARY, TYPE=VELOCITY/ACCELERATION "
                             "dropped: those BCs get generated displacement amplitudes that "
                             "integrate it.", once=True)
            return [f"** [abq2ccx] *AMPLITUDE, NAME={b.param('NAME')}: integrated into the "
                    f"displacement amplitudes of the velocity/acceleration BCs using it"]
        keep: "OrderedDict[str, Optional[str]]" = OrderedDict()
        definition = ""
        fixed = None
        begin = 0.0
        scale = [1.0, 1.0]                       # SCALEX (time), SCALEY (amplitude)
        for k, v in b.params.items():
            if k in ("NAME", "TIME", "SHIFTX", "SHIFTY"):
                keep[k] = v
            elif k == "DEFINITION":
                definition = (v or "").upper()
            elif k == "FIXED INTERVAL":
                try:
                    fixed = pf(v or "")
                except ValueError:
                    pass
            elif k == "BEGIN":
                try:
                    begin = pf(v or "")
                except ValueError:
                    pass
            elif k in ("SCALEX", "SCALEY"):
                try:
                    scale[0 if k == "SCALEX" else 1] = pf(v or "1")
                except ValueError:
                    self.report.warn(f"*AMPLITUDE {k}={v} could not be parsed; ignored.", once=True)
            elif k == "VALUE":
                if (v or "").strip().upper() == "ABSOLUTE":
                    self.report.warn("*AMPLITUDE, VALUE=ABSOLUTE: Abaqus uses these values as the "
                                     "load magnitudes themselves, ccx always multiplies them by the "
                                     "magnitude on the load/BC card — set those magnitudes to 1.",
                                     once=True)
            else:
                self.report.note(f"*AMPLITUDE parameter {k} dropped.", once=True)

        def scaled(pairs: List[str]) -> List[str]:
            """Apply SCALEX/SCALEY to 'time, amplitude' lines (Abaqus scales, then shifts —
            SHIFTX/SHIFTY stay on the card for ccx to apply)."""
            if scale == [1.0, 1.0]:
                return pairs
            try:
                vals = [pf(x) for ln in pairs for x in ln.split(",") if x.strip()]
            except ValueError:
                self.report.warn("*AMPLITUDE SCALEX/SCALEY could not be applied (non-numeric "
                                 "data); amplitude left unscaled — verify.", once=True)
                return pairs
            self.report.note("*AMPLITUDE SCALEX/SCALEY applied to the data points (ccx has no "
                             "such parameters).", once=True)
            pts = [f"{vals[i] * scale[0]:.6g}, {vals[i + 1] * scale[1]:.6g}"
                   for i in range(0, len(vals) - 1, 2)]
            return [", ".join(pts[i:i + 4]) for i in range(0, len(pts), 4)]

        if definition == "SMOOTH STEP":
            sampled = self._smooth_step_to_tabular(b)
            if sampled is not None:
                self.report.note("*AMPLITUDE DEFINITION=SMOOTH STEP sampled into tabular points "
                                 "(ccx has no smooth-step; the quintic ramp is approximated).", once=True)
                return [emit_keyword("AMPLITUDE", keep)] + scaled(sampled)
            self.report.warn("*AMPLITUDE DEFINITION=SMOOTH STEP could not be parsed; emitted as "
                             "TABULAR (linear between points) — verify.", once=True)
        elif definition == "EQUALLY SPACED":
            # data lines are bare amplitudes; ccx would misread them as (time, amplitude)
            # pairs, so expand to explicit points at BEGIN + i*FIXED INTERVAL.
            if fixed:
                try:
                    vals = [pf(x) for rec in merged_data_records(b) for x in rec if x != ""]
                except ValueError:
                    vals = []
                if vals:
                    self.report.note("*AMPLITUDE DEFINITION=EQUALLY SPACED expanded to explicit "
                                     "time/amplitude pairs.", once=True)
                    return [emit_keyword("AMPLITUDE", keep)] + \
                           scaled([f"{begin + i * fixed:.6g}, {a:.6g}" for i, a in enumerate(vals)])
            return self._commented(b, "*AMPLITUDE DEFINITION=EQUALLY SPACED could not be expanded "
                                      "(missing/invalid FIXED INTERVAL or data); rebuild as TABULAR.")
        elif definition == "USER":
            return self._commented(b, "*AMPLITUDE, DEFINITION=USER: the amplitude comes from the "
                                      "Abaqus user subroutine UAMP, which ccx cannot call (its own "
                                      "is uamplitude.f). Commented out: the loads that use it stop "
                                      "ccx ('nonexistent amplitude') until the subroutine is ported.")
        elif definition in ("PERIODIC", "MODULATED", "DECAY", "SOLUTION DEPENDENT", "ACTUATOR"):
            # first data line holds series constants, not (t, A) pairs — passing it
            # through would be silent garbage
            return self._commented(b, f"*AMPLITUDE DEFINITION={definition} has no ccx equivalent and "
                                      f"its data is not time/amplitude pairs; sample the curve into a "
                                      f"TABULAR amplitude manually.")
        elif definition not in ("", "TABULAR"):
            self.report.warn(f"*AMPLITUDE DEFINITION={definition} unsupported by ccx; treated as "
                             f"TABULAR.", once=True)
        return [emit_keyword("AMPLITUDE", keep)] + scaled(list(b.data))

    def _smooth_step_to_tabular(self, b: Block) -> Optional[List[str]]:
        """Sample Abaqus' SMOOTH STEP quintic (a = A0 + (A1-A0)*x^3*(10-15x+6x^2)) into
        tabular time/amplitude pairs ccx can use.  Returns None if the data is unparsable."""
        pts: List[Tuple[float, float]] = []
        try:
            vals: List[float] = []
            for rec in merged_data_records(b):
                vals.extend(pf(x) for x in rec if x != "")
            for i in range(0, len(vals) - 1, 2):
                pts.append((vals[i], vals[i + 1]))
        except ValueError:
            return None
        if len(pts) < 2:
            return None
        out: List[str] = [f"{pts[0][0]:.6g}, {pts[0][1]:.6g}"]
        N = 10                                     # samples per interval
        for (t0, a0), (t1, a1) in zip(pts, pts[1:]):
            if t1 <= t0:
                return None
            for k in range(1, N + 1):
                x = k / N
                a = a0 + (a1 - a0) * x**3 * (10.0 - 15.0 * x + 6.0 * x * x)
                out.append(f"{t0 + (t1 - t0) * x:.6g}, {a:.6g}")
        return out

    def handle_friction(self, b: Block) -> List[str]:
        """``*FRICTION``: the ccx card is ``mu, stick slope`` with no parameters, mu > 0
        (zero/empty is a hard error; no card = frictionless).  Abaqus' second field is a
        slip rate (rate tables) or mu_kinetic (EXPONENTIAL DECAY) — ccx would take it as the
        stick slope (verified: friction force off by ~15x), so only mu is emitted and ccx
        picks its default stick slope.  ROUGH (no slip) has no ccx equivalent."""
        if b.has("ROUGH"):
            self.report.warn("*FRICTION, ROUGH (no slip once in contact) has no ccx equivalent; "
                             "dropped, so this interaction becomes FRICTIONLESS. Re-add *FRICTION "
                             "with a large mu (or tie the surfaces) to approximate no-slip.", once=True)
            return ["** [abq2ccx] *FRICTION, ROUGH dropped (no ccx equivalent)"]
        for k in b.params:
            if k not in ("DEPENDENCIES",):
                level = self.report.warn if k in ("EXPONENTIAL DECAY", "ANISOTROPIC", "TAUMAX",
                                                  "USER") else self.report.note
                level(f"*FRICTION parameter {k} dropped (ccx's *FRICTION takes only mu and a "
                      f"stick slope).", once=True)
        if b.has("DEPENDENCIES"):            # rows: mu, slip rate, pressure, T, fields...
            data = self._collapse_dependencies(b, 3) or list(b.data)
        else:
            data = list(b.data)
        mus: List[float] = []
        for ln in data:
            f = [x.strip() for x in ln.split(",")]
            try:
                mus.append(float(f[0]))
            except (IndexError, ValueError):
                continue
        if not mus or max(mus) <= 0.0:
            self.report.note("*FRICTION with no positive coefficient dropped — ccx treats the absence "
                             "of *FRICTION as frictionless, whereas a zero/empty coefficient is a hard "
                             "error there. Re-add it with mu>0 if you need friction.", once=True)
            return ["** [abq2ccx] *FRICTION dropped (frictionless / no positive coefficient)"]
        mu = mus[0] if mus[0] > 0.0 else max(mus)
        if len(set(mus)) > 1 or len(data) > 1 or any(
                x.strip() for ln in data for x in ln.split(",")[1:]):
            self.report.warn(f"*FRICTION: only the coefficient mu={mu:g} is kept — ccx friction is "
                             f"a constant mu (slip-rate / pressure / temperature tables, exponential "
                             f"decay and anisotropy are not modelled) and Abaqus' later fields would "
                             f"be read as ccx's stick slope.", once=True)
        return ["*FRICTION", f"{mu:g},"]

    def handle_rigid_body(self, b: Block) -> List[str]:
        """``*RIGID BODY``: Abaqus uses ``PIN NSET``/``TIE NSET`` for the node set that
        moves with the reference node; ccx calls that simply ``NSET`` and rejects the
        Abaqus spellings.  Map them, keep ``REF NODE``/``ROT NODE``/``ELSET``.  ccx moves
        only the members' translations, so the rotations of knotted TIE/ELSET shell/beam
        members are tied to the ROT NODE (PIN members keep theirs, as in Abaqus), and a
        shell/beam reference node drives the ROT NODE (see _plan_rigid_couplings)."""
        keep: "OrderedDict[str, Optional[str]]" = OrderedDict()
        pre: List[str] = []
        node_sets = [v for k, v in b.params.items()
                     if k.upper().replace(" ", "") in ("PINNSET", "TIENSET", "NSET") and v]
        if len(node_sets) > 1:
            # PIN NSET and TIE NSET together: ccx has one NSET, so use their union rather
            # than letting the second silently replace the first
            self._synth_counter += 1
            union = f"ABQ2CCX_RB{self._synth_counter}"
            pre = [f"*NSET, NSET={union}"] + reflow(node_sets, MAX_ENTRIES_PER_LINE)
            node_sets = [union]
        for k, v in b.params.items():
            ku = k.upper().replace(" ", "")
            if ku in ("PINNSET", "TIENSET", "NSET"):
                keep["NSET"] = node_sets[0]
            elif ku == "REFNODE":
                keep["REF NODE"] = v
            elif ku == "ROTNODE":
                keep["ROT NODE"] = v
            elif ku == "ELSET":
                keep["ELSET"] = v
            else:
                self.report.note(f"*RIGID BODY parameter {k} dropped (Abaqus-only).", once=True)
        tie, pin = self._rigid_body_members(b)
        if any(k.upper().replace(" ", "") in ("PINNSET", "TIENSET") for k in b.params):
            self.report.note("*RIGID BODY: Abaqus PIN/TIE NSET mapped to ccx NSET (the set moves "
                             "rigidly with REF NODE); the rotations of TIE (and ELSET) shell/beam "
                             "nodes are tied to the body, those of PIN nodes stay free, as in "
                             "Abaqus.", once=True)
        # ccx requires REF NODE / ROT NODE to be node NUMBERS; CAE writes reference-point
        # set names (_PickedSet47) — resolve single-node sets, exactly as for *COUPLING.
        for key in ("REF NODE", "ROT NODE"):
            ref = (keep.get(key) or "").strip()
            if ref and not re.fullmatch(r"[-+]?\d+", ref):
                nodes = self.geom.nset(ref)
                if len(nodes) == 1:
                    keep[key] = str(nodes[0])
                    self.report.note(f"*RIGID BODY {key}={ref} resolved to node {nodes[0]} "
                                     f"(ccx needs a node number).", once=True)
                elif nodes:
                    keep[key] = str(nodes[0])
                    self.report.warn(f"*RIGID BODY {key}={ref} names a set with {len(nodes)} nodes; "
                                     f"the first ({nodes[0]}) is used — verify.", once=True)
                else:
                    self.report.warn(f"*RIGID BODY {key}={ref} could not be resolved to a node id; "
                                     f"ccx will reject a set name here.", once=True)
        ref_ids = self._resolve_nodes((keep.get("REF NODE") or "").strip())
        ref = ref_ids[0] if ref_ids else None
        own = ref in self._knots and ref in self._rot_nodes    # a shell/beam reference node
        if ref in self._rb_rot_synth and not keep.get("ROT NODE"):
            keep["ROT NODE"] = str(self._rb_rot_synth[ref])
            self.report.note("*RIGID BODY: explicit ROT NODE added — ccx carries the body's "
                             "rotations on its DOFs 1-3 and ignores DOFs 4-6 of the REF NODE, so "
                             + ("it is tied to the rotations of the shell/beam reference node."
                                if own else "rotational BCs and moments on the reference point "
                                            "are moved there."), once=True)
        rot = self._first_node(keep.get("ROT NODE") or "")
        ties: List[str] = []
        if ref is not None and rot is not None:
            if own:
                ties += self._rot_node_follows(rot, ref)
            ties += self._rotation_ties([n for n in tie if n != ref], rot, -3)
        return pre + [emit_keyword("RIGID BODY", keep)] + list(b.data) + ties

    def handle_equation(self, b: Block) -> List[str]:
        """``*EQUATION``: ccx 2.22 requires node NUMBERS in the terms; Abaqus/CAE decks
        (esp. periodic-BC lattices) write node SETS.  Resolve single-node sets directly;
        expand equal-length multi-node sets into one equation per node pairing."""
        recs = [[x for x in rec if x != ""] for rec in merged_data_records(b)]
        recs = [r for r in recs if r]
        if not recs:
            return [emit_keyword("EQUATION", b.params)] + list(b.data)
        toks: List[str] = [t for r in recs[1:] for t in r]
        if len(toks) % 3 != 0 or not any(not re.fullmatch(r"[-+]?[\d.eE+-]+", t) for t in toks[0::3]):
            return [emit_keyword("EQUATION", b.params)] + list(b.data)   # all-numeric: untouched
        terms = [(toks[i], toks[i + 1], toks[i + 2]) for i in range(0, len(toks), 3)]
        resolved: List[Tuple[List[int], str, str]] = []
        for tok, dof, coef in terms:
            if re.fullmatch(r"[-+]?\d+", tok):
                resolved.append(([int(tok)], dof, coef))
            else:
                nodes = self.geom.nset(tok)
                if not nodes:
                    self.report.warn(f"*EQUATION references set '{tok}' which resolves to no nodes; "
                                     f"card left unchanged — ccx 2.22 rejects set names here "
                                     f"(2.23 accepts them).", once=True)
                    return [emit_keyword("EQUATION", b.params)] + list(b.data)
                # Abaqus applies a set-based equation node by node in the set's SORTED
                # order (ascending ids) unless the set was declared UNSORTED
                if tok.upper() not in self.geom.unsorted:
                    nodes = sorted(set(nodes))
                else:
                    nodes = dedup(nodes)
                resolved.append((list(nodes), dof, coef))
        sizes = {len(n) for n, _, _ in resolved if len(n) > 1}
        if len(sizes) > 1:
            self.report.warn("*EQUATION mixes node sets of different sizes; card left unchanged — "
                             "rewrite with explicit nodes.", once=True)
            return [emit_keyword("EQUATION", b.params)] + list(b.data)
        n_eq = sizes.pop() if sizes else 1
        out: List[str] = [emit_keyword("EQUATION", b.params)]
        for i in range(n_eq):
            trip = [(nodes[i] if len(nodes) > 1 else nodes[0], dof, coef)
                    for nodes, dof, coef in resolved]
            out.append(str(len(trip)))
            for j in range(0, len(trip), 4):          # ccx: at most 12 entries per line
                out.append(", ".join(f"{n}, {d}, {c}" for n, d, c in trip[j:j + 4]))
        self.report.note("*EQUATION set-name terms resolved to node numbers (ccx 2.22 needs "
                         "explicit nodes; multi-node sets expanded pairwise).", once=True)
        return out

    def handle_coupling_card(self, b: Block) -> List[str]:
        """``*COUPLING``: ccx accepts the card but requires REF NODE to be a NODE NUMBER —
        a set name (what Abaqus/CAE always writes, e.g. REF NODE=_PickedSet8) is a hard
        error.  Resolve single-node sets to their node id."""
        params: "OrderedDict[str, Optional[str]]" = OrderedDict(b.params)
        ref = (b.param("REF NODE") or "").strip()
        if ref and not re.fullmatch(r"[-+]?\d+", ref):
            nodes = self.geom.nset(ref)
            if len(nodes) == 1:
                params["REF NODE"] = str(nodes[0])
                self.report.note(f"*COUPLING REF NODE={ref} resolved to node {nodes[0]} "
                                 f"(ccx needs a node number, not a set name).", once=True)
            elif nodes:
                params["REF NODE"] = str(nodes[0])
                self.report.warn(f"*COUPLING REF NODE={ref} names a set with {len(nodes)} nodes; "
                                 f"the first ({nodes[0]}) is used — verify.", once=True)
            else:
                self.report.warn(f"*COUPLING REF NODE={ref} could not be resolved to a node id; "
                                 f"ccx will reject a set name here.", once=True)
        self._last_coupling = self._coupling_plan.get(id(b))
        self._last_planar = id(b) in self._planar_kin
        if (self._last_coupling or {}).get("kind") == "rb":
            return self._coupling_as_rigid_body(self._last_coupling)
        if (self._last_coupling or {}).get("kind") == "unsupported":
            self._warn_rigid_unsupported()
        return [emit_keyword("COUPLING", params)] + list(b.data)

    def _coupling_as_rigid_body(self, plan: dict) -> List[str]:
        """A kinematic coupling of all translations whose reference node is a shell/beam
        node, as the equivalent *RIGID BODY: ccx would otherwise carry the coupling's
        rotation and the knotted node's own rotation as two unrelated unknowns (see
        _plan_rigid_couplings), so the ROT NODE is tied to the node's rotations instead."""
        ref, rot, members = plan["ref"], plan["rot"], plan["members"]
        if not members:
            self.report.warn("*COUPLING couples only its own reference node; dropped.", once=True)
            return []
        self._synth_counter += 1
        name = f"ABQ2CCX_RB{self._synth_counter}"
        out = [f"*NSET, NSET={name}"] + reflow([str(n) for n in members])
        out.append(f"*RIGID BODY, NSET={name}, REF NODE={ref}, ROT NODE={rot}")
        out += self._rot_node_follows(rot, ref)
        out += self._rotation_ties(members, rot, -3, sorted(plan["dofs"]))
        self.report.note("*COUPLING + *KINEMATIC with a shell/beam REF NODE -> *RIGID BODY on the "
                         "coupled nodes (the reference node itself left out), with a ROT NODE tied "
                         "to the reference node's rotations: as a ccx kinematic coupling the node "
                         "would carry two unrelated rotations.", once=True)
        return out

    def handle_kinematic(self, b: Block) -> List[str]:
        """``*KINEMATIC`` under ``*COUPLING``: ccx allows only DOFs 1..3, and an EMPTY
        card runs without warnings but creates NO constraint (the ref-node load silently
        vanishes — verified).  Abaqus' empty default means 'all DOFs', so synthesize
        1,3; clamp rotational DOFs to the translational range.  The rotations Abaqus
        couples on knotted shell/beam members are tied to the reference node's DOFs 4-6,
        which carry the ccx coupling's rotation (see _plan_rigid_couplings).  On 2-D
        (plane/axisymmetric) members DOF 3 is left out: Abaqus has none there, and ccx holds it
        fixed itself, so coupling it stops ccx ('dependent side of a MPC and a SPC')."""
        plan, self._last_coupling = self._last_coupling or {}, None
        planar, self._last_planar = self._last_planar, False
        if plan.get("kind") == "rb":
            return []                 # folded into the *RIGID BODY of the *COUPLING card
        top = 2 if planar else 3
        lines: List[str] = []
        had_lines = False
        clamped = False
        for rec in merged_data_records(b):
            f = [x for x in rec if x != ""]
            if not f:
                continue
            had_lines = True
            try:
                d1 = pint(f[0])
                d2 = pint(f[1]) if len(f) > 1 and f[1] else d1
            except ValueError:
                lines.append(", ".join(f))
                continue
            if d1 > 3 and d2 > 3:
                self.report.warn("*KINEMATIC line couples only rotational DOFs (4..6); ccx supports "
                                 "1..3 only — line dropped, rotations are NOT coupled.", once=True)
                continue
            if planar and max(d1, d2) > 2:
                self._note_planar_kinematic()
                if min(d1, d2) > 2:
                    continue
            c1, c2 = min(d1, top), min(d2, top)
            clamped = clamped or (not planar and (c1, c2) != (d1, d2))
            lines.append(f"{c1}, {c2}")
        if not had_lines:
            self.report.warn(f"*KINEMATIC without DOF lines creates NO constraint in ccx (the "
                             f"coupling silently does nothing); synthesized '1, {top}' to match the "
                             f"Abaqus default of coupling all DOFs"
                             f"{' (in-plane: the nodes are 2-D)' if planar else ''} — verify.",
                             once=True)
            lines = [f"1, {top}"]
        ties: List[str] = []
        if plan.get("kind") == "kin" and lines:
            # ccx carries the coupling's rotation on DOFs 4-6 of the reference node
            ties = self._rotation_ties(plan["members"], plan["ref"], 0, sorted(plan["dofs"]))
        if clamped:
            self.report.note("*KINEMATIC DOFs above 3 clamped to 1..3 (ccx couples translations; "
                             "the surface still follows the ref node rigidly"
                             + ("; the rotations of the coupled shell/beam nodes are tied to the "
                                "ref node by *EQUATION)." if ties else ")."), once=True)
        return [emit_keyword("KINEMATIC", b.params)] + lines + ties

    def _note_planar_kinematic(self) -> None:
        self.report.note("Kinematic coupling of 2-D (plane/axisymmetric) nodes: DOFs above 2 left "
                         "out of the ccx *KINEMATIC — such nodes have no DOF 3 in Abaqus, and ccx "
                         "holds it fixed itself and stops on a coupled one ('dependent side of a "
                         "MPC and a SPC'); they still follow the reference node's in-plane rigid "
                         "motion.", once=True)

    def handle_static(self, b: Block) -> List[str]:
        """``*STATIC, RIKS``: ccx has no arc-length solver, and passed through it would
        silently run a load-controlled *STATIC (it only warns 'parameter not recognized').
        By default the procedure card is therefore commented out, so ccx stops at this
        step; under --approximate the step becomes a plain *STATIC (the first data fields
        carry over as increments)."""
        params: "OrderedDict[str, Optional[str]]" = OrderedDict()
        for k, v in b.params.items():
            if k == "DIRECT":
                params[k] = None            # Abaqus DIRECT=NO STOP: ccx would not see DIRECT
                if v:
                    self.report.note(f"*STATIC DIRECT={v} -> DIRECT (fixed increments; ccx stops "
                                     f"if an increment does not converge).", once=True)
            elif k in ("SOLVER", "TIME RESET", "TOTAL TIME AT START", "EXPLICIT", "RIKS"):
                params[k] = v
            elif k in ("STABILIZE", "ALLSDTOL", "CONTINUE", "FACTOR"):
                self.report.warn(f"*STATIC {k} dropped: ccx has no automatic (viscous) "
                                 f"stabilization, so a deck that relies on it to pass an "
                                 f"instability may not converge.", once=True)
            else:
                self.report.note(f"*STATIC parameter {k} dropped (not a ccx parameter).", once=True)
        if "RIKS" in params:
            if self._approx:
                del params["RIKS"]
                self.report.warn("[APPROX] *STATIC, RIKS -> plain *STATIC (ccx has no Riks "
                                 "arc-length solver; snap-through/post-buckling paths may not "
                                 "converge or may differ). Verify.", once=True)
                return [emit_keyword("STATIC", params)] + list(b.data)
            return self._commented(b, "*STATIC, RIKS: ccx has no Riks arc-length solver. Passed "
                                      "through, ccx would silently run a load-controlled *STATIC "
                                      "instead, so the procedure is commented out and ccx stops at "
                                      "this step. Rerun with --approximate to accept the plain-"
                                      "*STATIC reframing.")
        return [emit_keyword("STATIC", params)] + list(b.data)

    def handle_dynamic(self, b: Block) -> List[str]:
        """``*DYNAMIC``: ccx runs implicit (HHT-alpha) and explicit (``EXPLICIT``, central
        difference) direct integration natively; its card knows only EXPLICIT, DIRECT,
        ALPHA, SOLVER and RELATIVE TO ABSOLUTE.  Abaqus-only controls are dropped with a
        note (``DIRECT USER CONTROL`` = ccx DIRECT: a fixed, user-given increment); the
        data line (initial increment, period, min, max) has the same layout in both.  An
        explicit step in a deck with circular-section beams gets a maximum increment
        (_circ_explicit_increment)."""
        keep: "OrderedDict[str, Optional[str]]" = OrderedDict()
        for k, v in b.params.items():
            if k in ("EXPLICIT", "DIRECT"):
                keep[k] = None              # flags in ccx (DIRECT=NO STOP would not register)
            elif k in ("ALPHA", "SOLVER", "RELATIVE TO ABSOLUTE"):
                keep[k] = v
            elif k == "DIRECT USER CONTROL":
                keep["DIRECT"] = None
                self.report.note("*DYNAMIC DIRECT USER CONTROL -> DIRECT (fixed time increment "
                                 "from the data line).", once=True)
            elif k == "APPLICATION":
                app = (v or "").upper()
                if (app.startswith("QUASI") or app.startswith("MODERATE")) and "ALPHA" not in b.params:
                    keep["ALPHA"] = "-0.3333"
                    self.report.note(f"*DYNAMIC APPLICATION={v} -> ALPHA=-0.3333 (ccx's strongest "
                                     f"HHT numerical damping; Abaqus uses a more dissipative "
                                     f"integrator for this application).", once=True)
                else:
                    self.report.note(f"*DYNAMIC APPLICATION={v} dropped (ccx uses the HHT alpha-"
                                     f"method, default ALPHA=-0.05).", once=True)
            elif k == "SCALE FACTOR":
                self.report.warn(f"*DYNAMIC, EXPLICIT SCALE FACTOR={v} dropped: ccx sizes the "
                                 f"stable time increment itself — use the maximum increment on "
                                 f"the data line if a smaller step is needed.", once=True)
            elif k == "ADIABATIC":
                self.report.warn("*DYNAMIC ADIABATIC dropped: ccx does not convert plastic work "
                                 "into heat in a mechanical step.", once=True)
            else:
                self.report.note(f"*DYNAMIC parameter {k} dropped (Abaqus-only).", once=True)
        data = list(b.data)
        if "EXPLICIT" in keep:
            data = self._circ_explicit_increment(keep, data)
        return [emit_keyword("DYNAMIC", keep)] + data

    def handle_initial_conditions(self, b: Block) -> List[str]:
        """``*INITIAL CONDITIONS, TYPE=STRESS/PLASTIC STRAIN/SOLUTION``: Abaqus writes one
        line per element/elset with NO integration-point column; ccx requires one line per
        element AND integration point (verified: the Abaqus form is a hard error, the
        expanded form solves).  Expand each record to every int pt of the emitted ccx
        element type (uniform value per element).  Other TYPEs pass through unchanged."""
        typ = (b.param("TYPE") or "").upper()
        ccx_known = {"DISPLACEMENT", "FLUID VELOCITY", "MASS FLOW", "PLASTIC STRAIN", "PRESSURE",
                     "SOLUTION", "STRESS", "TEMPERATURE", "TOTAL PRESSURE", "VELOCITY"}
        if typ and typ not in ccx_known:
            # e.g. TYPE=ENRICHMENT (XFEM/VCCT), HARDENING, FIELD, RATIO — ccx stops with
            # "unknown type"; comment the card out with the reason instead
            return self._commented(b, f"*INITIAL CONDITIONS TYPE={typ} is not a ccx initial-"
                                      f"condition type (ccx knows {', '.join(sorted(ccx_known))}); "
                                      f"remodel or remove.")
        layout = {"TEMPERATURE": "field", "VELOCITY": "dof", "DISPLACEMENT": "dof"}.get(typ)
        midside = self._midside_records(b, layout) if layout else []
        if typ == "TEMPERATURE" and self._temp_ic_fill:
            self.report.note(f"*INITIAL CONDITIONS, TYPE=TEMPERATURE: nodes it does not list get "
                             f"0 first ({ALL_NODES_SET}, 0.) — the Abaqus default; ccx stops on a "
                             f"node without an initial temperature.", once=True)
            return [emit_keyword("INITIAL CONDITIONS", b.params), f"{ALL_NODES_SET}, 0."] + \
                list(b.data) + midside
        if typ not in ("STRESS", "PLASTIC STRAIN", "SOLUTION"):
            return self.passthrough(b) + midside
        if b.has("GEOSTATIC"):
            return self._commented(b, f"*INITIAL CONDITIONS TYPE={typ}, GEOSTATIC (stress varying "
                                      f"with elevation) has no ccx equivalent; compute per-element "
                                      f"stresses and list them explicitly.")
        if b.has("USER"):
            return self._commented(b, f"*INITIAL CONDITIONS TYPE={typ}, USER needs the "
                                      f"sigini/sdvini user subroutine — port it to ccx and re-add.")
        out: List[str] = [emit_keyword("INITIAL CONDITIONS", b.params)]
        expanded = skipped = 0
        records = [[x for x in rec if x != ""] for rec in merged_data_records(b)]
        records = [r for r in records if r]
        if typ == "SOLUTION":
            # one record = label + nsdv values: 7 on the first line, 8 per continuation
            # line; without the count, continuation lines would read as new records
            nsdv = next(iter(self._depvar_counts)) if len(self._depvar_counts) == 1 else None
            if nsdv and nsdv > 7:
                per = 1 + -(-(nsdv - 7) // 8)
                records = [sum(records[i:i + per], []) for i in range(0, len(records), per)]
            elif nsdv is None and any(len(r) >= 8 for r in records):
                self.report.warn("*INITIAL CONDITIONS, TYPE=SOLUTION: records may continue over "
                                 "several lines, but the deck has no single *DEPVAR size to tell "
                                 "them apart — each line was taken as its own record. Verify.",
                                 once=True)
        for f in records:
            tok, vals = f[0], f[1:]
            eids = [int(tok)] if re.fullmatch(r"[-+]?\d+", tok) else self.geom.elset(tok)
            if not eids:
                self.report.warn(f"*INITIAL CONDITIONS TYPE={typ}: '{tok}' matches no element or "
                                 f"elset; record dropped.", once=True)
                continue
            for eid in eids:
                info = self.geom.elements.get(eid)
                n = ELEMENT_IP_COUNT.get(ccx_element_type(info[0], self.report)) if info else None
                if not n:
                    skipped += 1
                    continue
                for k in range(1, n + 1):
                    out.extend(reflow([str(eid), str(k)] + vals, MAX_ENTRIES_PER_LINE))
                expanded += 1
        if expanded:
            self.report.warn(f"*INITIAL CONDITIONS TYPE={typ} expanded to ccx's per-integration-"
                             f"point format (uniform value per element; 2D elements use the "
                             f"internally-expanded 3D point counts).", once=True)
        if skipped:
            self.report.warn(f"*INITIAL CONDITIONS TYPE={typ}: {skipped} element(s) have no "
                             f"integration-point mapping (shells/beams/unknown types); set those "
                             f"manually.", once=True)
        if len(out) == 1:
            return self._commented(b, f"*INITIAL CONDITIONS TYPE={typ} had no expandable records.")
        return out

    def handle_temperature(self, b: Block) -> List[str]:
        """``*TEMPERATURE`` passes through; the midside nodes of upgraded 2-node beams get the
        mean of their end nodes' values.  USER (Abaqus UTEMP) is commented out.  In a step where
        temperature is a degree of freedom (``TEMPERATURE_DOF_PROCS``) Abaqus does not allow
        the card and ccx stops on it (probed on 2.23, with and without initial temperatures):
        commented out."""
        if self._step_temp_dof:
            return self._commented(b, f"*TEMPERATURE in a *{self._step_temp_dof} step: temperature "
                                      f"is degree of freedom 11 there, and Abaqus does not allow a "
                                      f"predefined temperature field in such a step (prescribe the "
                                      f"temperature with *BOUNDARY on DOF 11); ccx stops on the "
                                      f"card. Commented out.")
        if b.has("USER"):
            return self._user_load_card(b)
        return self.passthrough(b) + self._midside_records(b, "field")

    def handle_flux_film(self, b: Block) -> List[str]:
        """``*FILM`` / ``*DFLUX`` / ``*CFLUX`` / ``*RADIATE`` pass through, minus the loads whose
        magnitude comes from an Abaqus user subroutine (USER on the card, a ...NU label):
        kept, ccx would run its stock film.f / dflux.f / ... in place of the deck's own."""
        if b.has("USER"):
            return self._user_load_card(b)
        kept: List[str] = []
        side: List[str] = []
        for ln in b.data:
            g = [x.strip() for x in ln.split(",")]
            if _is_user_load(b, g):
                side += self._user_load_line(b, g)
            else:
                kept.append(ln)
        if not side:
            return self.passthrough(b)
        return ([emit_keyword(b.keyword, b.params)] + kept if kept else []) + side

    def _default_temperature_ic(self) -> List[str]:
        """Initial temperatures for a deck that applies ``*TEMPERATURE`` without any: Abaqus
        starts every node at 0, and ccx reads a *TEMPERATURE card only after thermal
        *INITIAL CONDITIONS (verified on 2.23: a free heated cube then strains alpha T
        exactly)."""
        self.report.note(f"*TEMPERATURE with no *INITIAL CONDITIONS, TYPE=TEMPERATURE: every node "
                         f"starts at 0, the Abaqus default, so thermal strains count from 0 "
                         f"(*INITIAL CONDITIONS, TYPE=TEMPERATURE / {ALL_NODES_SET}, 0. added "
                         f"before the first step); ccx stops on *TEMPERATURE without thermal "
                         f"initial conditions.", once=True)
        return ["** [abq2ccx] initial temperatures: the Abaqus default, 0, at every node (ccx "
                "reads *TEMPERATURE only after thermal initial conditions)",
                "*INITIAL CONDITIONS, TYPE=TEMPERATURE", f"{ALL_NODES_SET}, 0."]

    def _complete_temperature_ic(self) -> None:
        """Once a deck has initial temperatures ccx needs one in every node ("no initial
        temperature defined in node"), also at the free ends of the knot beams planned after
        _prescan (_plan_circ_rotation_knots, _plan_op_new_rotations): those get the Abaqus
        default 0 with the other nodes the deck's initial conditions leave out."""
        cov = self._temp_ic_covered
        if cov is not None and not self._temp_ic_fill and not set(self.geom.nodes) <= cov:
            self._temp_ic_fill = True
        if self._temp_ic_fill or self._temp_ic_default:
            self.geom.nsets[ALL_NODES_SET] = list(self.geom.nodes)

    def handle_normal(self, b: Block) -> List[str]:
        """``*NORMAL`` passes through.  ccx builds a beam's expanded cross-section from the
        normal in every node, so when both end nodes of an upgraded 2-node beam have an
        explicit normal its midside node gets their normalised mean — otherwise ccx would
        derive that node's normal from the section's n1 instead and twist the element
        wherever the two disagree."""
        out = self.passthrough(b)
        if not self._midside:
            return out
        given: Dict[Tuple[int, int], Vec] = {}
        for rec in merged_data_records(b):
            f = [x for x in rec if x != ""]
            try:
                if len(f) >= 5:
                    given[(pint(f[0]), pint(f[1]))] = (pf(f[2]), pf(f[3]), pf(f[4]))
            except ValueError:
                continue
        n_out = len(out)
        for eid, (a, c, m) in self._midside.items():
            na, nc = given.get((eid, a)), given.get((eid, c))
            if na and nc and (eid, m) not in given:
                n = vadd(vunit(na), vunit(nc))
                if vnorm(n) > 1e-9:
                    out.append(f"{eid}, {m}, " + ", ".join(_fmt_component(x) for x in vunit(n)))
        if len(out) > n_out:
            self._note_midside_lines("NORMAL")
        return out

    def handle_surface_interaction(self, b: Block) -> List[str]:
        """``*SURFACE INTERACTION``: Abaqus' default contact is hard pressure-overclosure
        with NO *SURFACE BEHAVIOR card, but ccx then stops with 'no PRESSURE-OVERCLOSURE'.
        Synthesize the HARD behavior when the interaction has none."""
        # The optional Abaqus data line is the out-of-plane thickness of 2D contact
        # surfaces; ccx takes no data line here (it uses the element thickness) and
        # would report the line as a card it cannot interpret.
        if any(x.strip() for x in b.data):
            self.report.note("*SURFACE INTERACTION data line (2D out-of-plane thickness) dropped — "
                             "ccx uses the plane-element section thickness for contact.", once=True)
        out = [emit_keyword("SURFACE INTERACTION", b.params)]
        name = (b.param("NAME") or "").upper()
        if name and name in getattr(self, "_si_missing_behavior", set()):
            self.report.note(f"*SURFACE INTERACTION {name} has no *SURFACE BEHAVIOR; added "
                             f"PRESSURE-OVERCLOSURE=HARD (the Abaqus default) so *CONTACT PAIR "
                             f"does not fail.", once=True)
            out.append("*SURFACE BEHAVIOR, PRESSURE-OVERCLOSURE=HARD")
        return out

    def handle_contact_pair(self, b: Block) -> List[str]:
        """``*CONTACT PAIR``: ccx *requires* a ``TYPE`` (Abaqus defaults to node-to-surface)
        and does not understand Abaqus-only parameters such as ``SUPPLEMENTARY
        CONSTRAINTS``/``GEOMETRIC CORRECTION``.  ``TIED`` (surfaces bonded for the whole
        analysis) becomes a ccx ``*TIE`` per surface pair — dropping it would let the
        bodies separate (verified: RF 0 instead of the tied value)."""
        if b.has("TIED"):
            out: List[str] = []
            adj = (b.param("ADJUST") or "").strip()
            for rec in merged_data_records(b):
                f = [x for x in rec if x != ""]
                if len(f) < 2:
                    continue
                self._synth_counter += 1
                params: "OrderedDict[str, Optional[str]]" = OrderedDict(
                    [("NAME", f"ABQ2CCX_TIED{self._synth_counter}")])
                try:
                    pf(adj)
                    params["POSITION TOLERANCE"] = adj
                except ValueError:
                    pass
                out += [emit_keyword("TIE", params), f"{f[0]}, {f[1]}"]
            if out:
                self.report.note("*CONTACT PAIR, TIED -> *TIE (same slave/master surfaces; ccx "
                                 "ties the nodes with MPCs instead of a contact formulation).",
                                 once=True)
                return out
        ccx_ok = {"INTERACTION", "TYPE", "SMALL SLIDING", "ADJUST", "CYCLIC SYMMETRY"}
        keep: "OrderedDict[str, Optional[str]]" = OrderedDict()
        for k, v in b.params.items():
            if k in ccx_ok:
                keep[k] = v
            else:
                self.report.note(f"*CONTACT PAIR parameter {k} dropped (Abaqus-only; not read by "
                                 f"ccx).", once=True)
        if "TYPE" not in keep:
            # Abaqus/Standard's default is node-to-surface.  Neither ccx discretization is
            # uniformly more robust (corpus: some decks converge only with one, some only
            # with the other), so keep the Abaqus meaning and point at the alternative.
            keep["TYPE"] = "NODE TO SURFACE"
            self.report.note("*CONTACT PAIR without TYPE -> TYPE=NODE TO SURFACE (the Abaqus/Standard "
                             "default; ccx requires it explicitly). If ccx struggles to converge, "
                             "try TYPE=SURFACE TO SURFACE (ccx's face-to-face contact).", once=True)
        if "SMALL SLIDING" in keep and (keep.get("TYPE") or "").upper().replace(" ", "") == \
                "SURFACETOSURFACE":
            del keep["SMALL SLIDING"]
            self.report.note("*CONTACT PAIR SMALL SLIDING dropped for SURFACE TO SURFACE contact "
                             "(ccx supports it only for node-to-surface and would ignore it).",
                             once=True)
        return [emit_keyword("CONTACT PAIR", keep)] + list(b.data)

    def handle_surface(self, b: Block) -> List[str]:
        if (b.param("TYPE") or "").upper().startswith("ANALYTICAL"):
            return self._commented(b, "*SURFACE TYPE=ANALYTICAL RIGID is unsupported by ccx; mesh the "
                                      "rigid surface with elements instead.")
        is_node = (b.param("TYPE") or "").upper() == "NODE"
        if b.has("COMBINE"):
            return self._commented(b, "*SURFACE, COMBINE (a surface built from other surfaces) has "
                                      "no ccx equivalent; list the element faces / nodes directly.")
        params: "OrderedDict[str, Optional[str]]" = OrderedDict()
        for k, v in b.params.items():
            if k in ("NAME", "TYPE"):
                params[k] = v
            elif k != "INTERNAL":
                self.report.note(f"*SURFACE parameter {k} dropped (ccx's *SURFACE takes only NAME "
                                 f"and TYPE).", once=True)
        out = [emit_keyword("SURFACE", params)]
        on_carriers = 0
        for rec in merged_data_records(b):
            f = [x for x in rec if x != ""]
            if not f:
                continue
            eids = self._load_elements(f[0]) if self._carriers and not is_node else []
            carried = sum(1 for e in eids if e in self._carriers)
            if carried:                          # surface elements: not in the ccx mesh
                on_carriers += 1
                if carried == len(eids):
                    continue
            if not re.fullmatch(r"[-+]?\d+", f[0]):
                known = self.geom.nsets if is_node else self.geom.elsets
                if f[0].upper() not in known:
                    self.report.warn(f"*SURFACE {b.param('NAME') or ''} references "
                                     f"{'node' if is_node else 'element'} set '{f[0]}', which the "
                                     f"deck never defines (incomplete export?); ccx stops with "
                                     f"'*ERROR reading *SURFACE'.", once=True)
            if is_node:
                # ccx node-based *SURFACE accepts exactly one node/nset per line; Abaqus
                # may append a weight ("NSET, 1."), which ccx rejects with "only one entry
                # per line allowed".  Keep just the node/nset.
                if len(f) > 1:
                    try:
                        if abs(pf(f[1]) - 1.0) > 1e-12:
                            self.report.warn("Node-based *SURFACE weights other than 1 dropped "
                                             "(ccx node surfaces carry no weights) — distributed "
                                             "couplings/loads on it will weight nodes equally.",
                                             once=True)
                    except ValueError:
                        pass
                out.append(f[0])
                continue
            if len(f) >= 2 and f[1].upper() in ("SPOS", "SNEG"):
                self.report.warn("*SURFACE shell face SPOS/SNEG: ccx handles shell faces differently; "
                                 "verify.", once=True)
            if len(f) >= 2 and re.fullmatch(r"E[1-4]", f[1].upper()):
                f = [f[0], self._edge_face(f[0], int(f[1][1:]))] + f[2:]
            out.append(", ".join(f))
        if on_carriers:
            if len(out) == 1:
                self.report.note("A *SURFACE on surface elements only is dropped with them; the "
                                 "loads on it become nodal forces.", once=True)
                return []
            self.report.warn(f"*SURFACE {b.param('NAME') or ''}: its faces on surface elements are "
                             f"left out with them (loads on it still reach them as nodal forces); a "
                             f"contact, tie or coupling on it sees only its other faces.", once=True)
        return out

    def _edge_face(self, token: str, k: int) -> str:
        """ccx face label for Abaqus edge ``E<k>`` of the elements in ``token``.  On ccx
        shells and membranes S1/S2 are the bottom/top faces and the edges are S3..S6
        (verified: a tie on S1 of a shell edge silently ties nothing); plane elements
        number their edges S1..S4 like Abaqus."""
        eids = [int(token)] if re.fullmatch(r"[-+]?\d+", token) else self.geom.elset(token)
        quiet = Report()
        types = {ccx_element_type(self.geom.elements[e][0], quiet) for e in eids
                 if e in self.geom.elements}
        if types and all(t.startswith(PLANE_ELEM_PREFIXES) for t in types):
            self.report.note("*SURFACE edge faces E1..E4 of plane elements -> ccx S1..S4 (same "
                             "edge numbering).", once=True)
            return f"S{k}"
        if not types or not all(t in SHELL_TYPES or t.startswith("M3D") for t in types):
            self.report.warn(f"*SURFACE edge face E{k} on '{token}': element family unknown or "
                             f"mixed; mapped to S{k + 2} (the ccx shell-edge numbering) — verify.",
                             once=True)
        else:
            self.report.note("*SURFACE shell edges E1..E4 -> ccx S3..S6 (S1/S2 are the shell "
                             "faces in ccx).", once=True)
        return f"S{k + 2}"

    # ======================================================================
    def convert(self, blocks: List[Block]) -> List[str]:
        raw = blocks
        if any(b.keyword in ("PART", "INSTANCE", "ASSEMBLY") for b in blocks):
            blocks = flatten_assembly(blocks, self.report, self.opt)
        self.build_geometry(blocks)
        self._drop_surface_elements(raw, blocks)
        self._find_planar_elements()            # before the beam upgrades below retype them
        self._upgrade_section_beams(blocks)
        self._check_nonpositive_ids()
        self._prescan(blocks)
        self._warn_coupled_clashes()                # BCs on coupled DOFs left (_prescan)
        self._plan_distributions(blocks)
        self._check_undefined_materials(blocks)
        self._plan_planar_constraint(blocks)
        self._plan_circ_rotation_knots(blocks)          # after the planar DOF 4-5 picks
        self._plan_op_new_rotations(blocks)     # after the planar BCs, which OP=NEW removes too
        self._plan_circ_explicit_increment(blocks)
        self._complete_temperature_ic()         # after every planner that adds knot nodes
        self._plan_output(blocks)               # last: it reads the final mesh (knot beams too)
        # interactions with no *SURFACE BEHAVIOR (Abaqus default = hard contact; ccx
        # errors without the card) — handle_surface_interaction synthesizes HARD for these
        self._si_missing_behavior = set()
        cur_si = None
        for blk in blocks:
            if blk.keyword == "SURFACE INTERACTION":
                cur_si = (blk.param("NAME") or "").upper()
                if cur_si:
                    self._si_missing_behavior.add(cur_si)
            elif blk.keyword == "SURFACE BEHAVIOR" and cur_si:
                self._si_missing_behavior.discard(cur_si)
        out: List[str] = []
        for b in blocks:
            if b.keyword == "HEADING":
                out.append("*HEADING")
                out.extend(b.data)
                break
        out.extend(self.emit_geometry())
        out.extend(self._knot_section())
        if self._planar_bc:
            out += ["** [abq2ccx] planar model: keep the 2-D beams/trusses in their plane (ccx "
                    "runs them as 3-D elements)"] + self._planar_bc
        out.extend(self.emit_other(blocks))
        out = self._settle_dependents(out)
        self._audit_loads(blocks, out)
        return out

    # procedures and *DLOAD labels in which an element's mass acts
    _INERTIA_PROCEDURES = {"DYNAMIC", "FREQUENCY", "MODAL DYNAMIC", "STEADY STATE DYNAMICS",
                           "COMPLEX FREQUENCY"}
    _MASS_LOADS = {"GRAV", "CENTRIF", "CENT", "ROTA", "CORIO", "ROTDYNF"}

    def _drop_surface_elements(self, raw: List[Block], blocks: List[Block]) -> None:
        """Leave Abaqus surface elements (SURFACE_ELEMENTS) out of the ccx mesh — ccx has no
        such element.  As pure load carriers they add nothing else: they have no stiffness,
        and their loads become consistent nodal forces on their nodes (_load_faces).  Element
        sets keep their other members; the full lists stay in _carrier_sets for the loads.
        Elements that also carry rebar layers (stiffness), or mass (*SURFACE SECTION,
        DENSITY=) in a deck where mass acts, stay in the mesh — ccx then stops on them — unless
        --approximate drops them anyway."""
        found = OrderedDict((e, v) for e, v in self.geom.elements.items()
                            if v[0].upper() in SURFACE_ELEMENTS)
        if not found:
            return
        kinds = ", ".join(sorted({v[0].upper() for v in found.values()}))
        why: List[str] = []
        if any(a.keyword == "SURFACE SECTION" and c.keyword == "REBAR LAYER"
               for a, c in zip(raw, raw[1:])):
            why.append("rebar layers (*REBAR LAYER) give them stiffness and mass")
        dens = [b.param("DENSITY") for b in blocks if b.keyword == "SURFACE SECTION"]
        try:
            heavy = any(d and pf(d) != 0.0 for d in dens)
        except ValueError:                        # an unresolved value: assume a mass
            heavy = True
        acts = sorted({b.keyword for b in blocks if b.keyword in self._INERTIA_PROCEDURES} |
                      {r[1].strip().upper() for b in blocks if b.keyword == "DLOAD"
                       for r in merged_data_records(b)
                       if len(r) > 1 and r[1].strip().upper() in self._MASS_LOADS})
        if heavy and acts:
            why.append(f"they carry mass (*SURFACE SECTION, DENSITY=), which acts in this deck "
                       f"({', '.join(acts)})")
        if why and not self._approx:
            self.report.warn(f"Surface elements ({kinds}) kept in the mesh: {'; '.join(why)}. ccx "
                             f"has no surface element and stops with '*ERROR reading *ELEMENT'; "
                             f"rerun with --approximate to leave them out (losing that) and apply "
                             f"their loads as nodal forces.")
            return
        if why:
            self.report.warn(f"[APPROX] Surface elements ({kinds}) left out of the mesh although "
                             f"{'; '.join(why)}: that is lost in ccx. Their loads become nodal "
                             f"forces. Verify.")
        for e in found:
            del self.geom.elements[e]
        self._carriers = found
        for name, ids in self.geom.elsets.items():
            if any(i in found for i in ids):
                self._carrier_sets[name] = list(ids)
                self.geom.elsets[name] = [i for i in ids if i not in found]
        self.report.note(f"{len(found)} surface element(s) ({kinds}) left out of the ccx mesh: they "
                         f"have no stiffness and ccx has no such element. The loads they carry "
                         f"(TRVEC, TRSHR, P) become consistent nodal forces on their nodes; element "
                         f"sets keep their other members.")
        used = {n for _, conn in self.geom.elements.values() for n in conn}
        free = {n for _, conn in found.values() for n in conn} - used
        if free:
            self.report.warn(f"{len(free)} node(s) of the surface elements belong to no other "
                             f"element: ccx silently ignores a load on a node without stiffness "
                             f"(probed on 2.23), so their share of the converted loads acts only "
                             f"where a constraint (*EQUATION, *MPC, *RIGID BODY, *COUPLING) ties "
                             f"them to the structure. Verify.")

    def _audit_loads(self, blocks: List[Block], out: List[str]) -> None:
        """Guard against a hollow solve: a step the Abaqus deck loads but whose every load
        was commented out (or became a stock ccx user subroutine) would still run — to a
        zero response.  Fills ``unloaded_steps`` (1-based) and ``source_unloaded`` (the deck
        itself applies no load in any step and has no eigenvalue step)."""
        src = step_load_audit(blocks, user_loads=True)
        dst = step_load_audit(blocks_from_lines(out), user_loads=False)
        self.source_unloaded = bool(src) and all(s == [] for s in src)
        self.unloaded_steps = [i for i, (s, d) in enumerate(zip(src, dst), 1) if s and d == []]
        for i in self.unloaded_steps:
            lost = src[i - 1]
            self.report.warn(f"Step {i} is loaded in the Abaqus deck ({'; '.join(lost[:3])}"
                             f"{'; ...' if len(lost) > 3 else ''}), but no load survives the "
                             f"conversion: ccx would solve it with no load at all, to a zero "
                             f"response. See the commented-out load cards.")
        if self.source_unloaded:
            self.report.note("The Abaqus deck applies no load, prescribed displacement or "
                             "initial velocity in any step, so its solution is zero — in ccx "
                             "as in Abaqus.", once=True)

    # Cards that read a node set as per-node state or as an output selection: a midside node
    # between two members belongs to the set too (a *BOUNDARY on every node of a beam must
    # still fix the whole beam).  Any other use (loads, *EQUATION, *MPC, couplings, node
    # surfaces) counts the set's nodes, so an extra node would change it.
    _MIDSIDE_SET_CARDS = {"BOUNDARY", "INITIAL CONDITIONS", "TEMPERATURE", "NODE PRINT",
                          "NODE FILE", "NODE OUTPUT", "RIGID BODY", "TRANSFORM"}

    def _upgrade_section_beams(self, blocks: List[Block]) -> None:
        """Beams whose *BEAM SECTION ccx 2.23 rejects on their emitted type -> the type it
        accepts (``SECTION_BEAM_UPGRADE``).  ``SECTION=CIRC``: 2-node beams stop with 'Please
        use quadratic elements for beams with circular cross section' (a linear beam expands
        to an 8-node brick, whose corner nodes cannot follow a circle) and become B32/B32R.
        ``SECTION=PIPE``/``BOX`` (and THICK PIPE, emitted as PIPE) run only on B32R: B32
        changes type, 2-node beams become B32R.  A 2-node element gets a midside node at the
        midpoint of its end nodes (new ids above the highest node; flattened coordinates are
        already global, so the instance transform is included), in ccx's end, middle, end
        order (probed on 2.23: end, end, middle stops with a nonpositive jacobian).  Element
        ids and element sets are unchanged; node sets follow ``_MIDSIDE_SET_CARDS``."""
        table: Dict[int, Tuple[str, Dict[str, str]]] = {}      # element -> (section, upgrade)
        for b in blocks:
            sec = (b.param("SECTION") or "").strip().upper() if b.keyword == "BEAM SECTION" else ""
            if sec not in SECTION_BEAM_UPGRADE:
                continue
            for e in self.geom.elset((b.param("ELSET") or "").strip()):
                if e not in table or table[e][1] is not PIPE_BOX_B32R:     # B32R suits CIRC too
                    table[e] = (sec, SECTION_BEAM_UPGRADE[sec])
        if not table:
            return
        quiet = Report()
        nodes = self.geom.nodes
        next_id = max(nodes, default=0)
        # per case (True: 2-node beam given a midside node, False: B32 retyped) the Abaqus
        # sections involved and the "TYPE -> new type" counts
        sections: Dict[bool, set] = {True: set(), False: set()}
        kinds: Dict[bool, "OrderedDict[str, int]"] = {True: OrderedDict(), False: OrderedDict()}
        for eid, (typ, conn) in list(self.geom.elements.items()):
            sec, up = table.get(eid, ("", {}))
            new = up.get(ccx_element_type(typ, quiet)) if up else None
            if new is None or len(conn) not in (2, 3) or not all(n in nodes for n in conn):
                continue
            mid = len(conn) == 2
            if mid:
                next_id += 1
                self.geom.add_node(next_id, vscale(vadd(nodes[conn[0]], nodes[conn[1]]), 0.5))
                self.geom.elements[eid] = (new, [conn[0], next_id, conn[1]])
                self._midside[eid] = (conn[0], conn[1], next_id)
            else:
                self.geom.elements[eid] = (new, conn)
            self._elem_types.add(new)
            sections[mid].add(sec)
            kind = f"{typ.upper()} -> {new}"
            kinds[mid][kind] = kinds[mid].get(kind, 0) + 1

        def label(mid: bool) -> str:
            return "/".join(s for s in SECTION_BEAM_UPGRADE if s in sections[mid])

        def counts(mid: bool) -> str:
            return ", ".join(f"{k}: {v}" for k, v in kinds[mid].items())

        if kinds[False]:
            self.report.warn(f"SECTION={label(False)} beams: {sum(kinds[False].values())} 3-node "
                             f"element(s) emitted as B32R instead of B32 ({counts(False)}), with the "
                             f"same nodes; ccx 2.23 accepts PIPE and BOX sections only on B32R.",
                             once=True)
        if not self._midside:
            return
        why = []
        if "CIRC" in sections[True]:
            why.append("stops on linear beams with a circular section")
        if sections[True] - {"CIRC"}:
            why.append("accepts PIPE and BOX sections only on B32R")
        mids = [m for _, _, m in self._midside.values()]
        span = f"node {mids[0]}" if len(mids) == 1 else f"nodes {mids[0]}-{mids[-1]}"
        self.report.warn(f"SECTION={label(True)} beams: {len(mids)} 2-node element(s) emitted as 3-node "
                         f"beams ({counts(True)}), each with a new midside node at its midpoint "
                         f"({span}); ccx 2.23 {' and '.join(why)}. Element ids and sets are kept, and "
                         f"BCs, temperatures and initial conditions on both end nodes also reach the "
                         f"midside node. The quadratic beam is closer to beam theory than the linear "
                         f"one, so results can differ slightly from Abaqus.", once=True)
        names = set(self.geom.nsets)
        counted: set = set()                    # node sets some other card counts node by node
        for b in blocks:
            if b.keyword in GEOM_KW or b.keyword in ELEM_REF_KW or b.keyword == "HEADING" or \
                    b.keyword in self._MIDSIDE_SET_CARDS:
                continue
            toks = {v.strip().upper() for k, v in b.params.items() if v and k in REF_PARAMS}
            for line in b.data:
                toks.update(t.strip().upper() for t in line.split(","))
            counted |= toks & names
        by_end: Dict[int, List[Tuple[int, int]]] = {}
        for a, c, m in self._midside.values():
            by_end.setdefault(a, []).append((c, m))
        skipped: List[str] = []
        for name, ids in self.geom.nsets.items():
            members = set(ids)
            add = [m for n in dedup(ids) for c, m in by_end.get(n, ()) if c in members]
            if add and name in counted:
                skipped.append(name)
            elif add:
                ids.extend(add)
        if skipped:
            self.report.note(f"Node set(s) {', '.join(skipped[:3])}{', ...' if len(skipped) > 3 else ''} "
                             f"hold both end nodes of upgraded 2-node beams but a load, constraint or "
                             f"surface card uses them, so the midside nodes were not added (an extra "
                             f"node there would add load or equation terms); *BOUNDARY and "
                             f"temperature lines on them still reach the midside nodes.", once=True)

    def _midside_records(self, b: Block, layout: str) -> List[str]:
        """Extra data lines that carry a per-node card onto the midside nodes of upgraded 2-node
        beams: when the card gives both end nodes a value (by id or through a set), the
        midside node gets the linear interpolation, which is what the Abaqus element sees
        between its nodes.  ``layout`` is ``"boundary"`` (node, first DOF[, last DOF[,
        magnitude]] or a named type), ``"dof"`` (node, DOF, value) or ``"field"`` (node,
        values...).  Appended after the card's own lines, they override what a set gave the
        midside node; a value the card already gives it is not repeated."""
        if not self._midside:
            return []
        recs: Dict[int, Dict[int, object]] = {}
        for rec in merged_data_records(b):
            g = [x.strip() for x in rec]
            while g and g[-1] == "":
                g.pop()
            if len(g) < 2 or not g[0]:
                continue
            vals: Dict[int, object] = {}
            try:
                if layout == "field":
                    vals[0] = [pf(x) if x else 0.0 for x in g[1:]]
                elif layout == "dof":
                    vals[int(g[1])] = pf(g[2]) if len(g) > 2 and g[2] else 0.0
                elif re.fullmatch(r"[-+]?\d+", g[1]):
                    d1 = int(g[1])
                    d2 = int(g[2]) if len(g) > 2 and g[2] else d1
                    mag = pf(g[3]) if len(g) > 3 and g[3] else None
                    vals.update((d, mag) for d in range(min(d1, d2), max(d1, d2) + 1))
                else:
                    for d1, d2 in self._named_bc_dofs(g[1]) or []:
                        vals.update((d, None) for d in range(d1, d2 + 1))
            except ValueError:
                continue
            for n in self._resolve_nodes(g[0]):
                recs.setdefault(n, {}).update(vals)
        out: List[str] = []
        for a, c, m in self._midside.values():
            if a not in recs or c not in recs:
                continue
            ra, rc, rm = recs[a], recs[c], recs.get(m, {})
            if layout == "field":
                mean = [(x + y) / 2.0 for x, y in zip(ra[0], rc[0])]
                if rm.get(0) != mean:
                    out.append(", ".join([str(m)] + ["%.12g" % x for x in mean]))
                continue
            runs: List[List] = []                # [first DOF, last DOF, value] (value None = blank)
            for d in sorted(set(ra) & set(rc)):
                va, vc = ra[d], rc[d]
                v = None if va is None and vc is None else ((va or 0.0) + (vc or 0.0)) / 2.0
                if d in rm and rm[d] == v:
                    continue
                if layout == "boundary" and runs and runs[-1][1] == d - 1 and runs[-1][2] == v:
                    runs[-1][1] = d
                else:
                    runs.append([d, d, v])
            for d1, d2, v in runs:
                head = [str(m), str(d1)] if layout == "dof" else [str(m), str(d1), str(d2)]
                out.append(", ".join(head + ([] if v is None else ["%.12g" % v])))
        if out:
            self._note_midside_lines(b.keyword)
        return out

    def _note_midside_lines(self, keyword: str) -> None:
        self.report.note(f"*{keyword} lines given for both end nodes of an upgraded 2-node beam were "
                         f"extended to its midside node (values interpolated linearly).", once=True)

    def _prescan(self, blocks: List[Block]) -> None:
        """Deck-wide facts that individual card handlers need: which nodes can carry
        rotations, which sets *EL PRINT / *NODE PRINT must default to, *DEPVAR sizes,
        whether field variables are ever set, and the step count."""
        quiet = Report()
        emitted: Dict[str, str] = {}
        plane: Dict[int, bool] = {}
        self._shell_nodes = set()
        self._beam_nodes = set()
        for typ, conn in self.geom.elements.values():
            if typ not in emitted:
                emitted[typ] = ccx_element_type(typ, quiet)
            cc = emitted[typ]
            is_plane = cc.startswith(PLANE_ELEM_PREFIXES)
            for n in conn:
                plane[n] = plane.get(n, True) and is_plane
            if cc in SHELL_TYPES:
                self._shell_nodes.update(conn)
            elif cc in BEAM_TYPES:
                self._beam_nodes.update(conn)
        # nodes that only belong to plane-stress/strain/axisymmetric continuum elements:
        # they have no rotational DOFs at all — unless they are the reference/rotation node
        # of a rigid body or coupling, which carries the body's rotations
        self._plane_only = {n for n, p in plane.items() if p}
        # reference/rotation nodes of rigid bodies and couplings carry real rotations (the
        # independent node of *MPC BEAM lines too: it becomes a *RIGID BODY's REF NODE);
        # rigid connectors join the *MPC BEAM bodies
        self._transformed = self._transform_defs(blocks)
        self._plan_connectors(blocks)
        self._plan_mpcs(blocks)
        mpc_refs = [body["ref"] for bodies in self._mpc_bodies.values() for body in bodies]
        self._plane_only.difference_update(mpc_refs)
        self._ref_nodes = set(mpc_refs)
        for b in blocks:
            if b.keyword in ("RIGID BODY", "COUPLING", "KINEMATIC COUPLING", "DISTRIBUTING COUPLING"):
                for k, v in b.params.items():
                    if k.replace(" ", "") in ("REFNODE", "ROTNODE") and v:
                        refs = self._resolve_nodes(v.strip())[:1]
                        self._plane_only.difference_update(refs)
                        self._ref_nodes.update(refs)
        # ccx carries a *RIGID BODY's rotations on DOFs 1-3 of its ROT NODE and silently
        # ignores BCs/moments on DOFs 4-6 of the REF NODE (verified on 2.23: a moment there
        # does nothing).  Give every rigid body an explicit rotation node so the
        # converter can move rotational BCs/loads onto it.
        self._rb_rot = {}
        self._rb_rot_synth = {}
        next_id = max(self.geom.nodes, default=0)
        for b in blocks:
            if b.keyword != "RIGID BODY":
                continue
            refs = self._resolve_nodes((b.param("REF NODE") or b.param("REFNODE") or "").strip())
            if not refs or refs[0] in self._rb_rot:
                continue
            ref = refs[0]
            rots = self._resolve_nodes((b.param("ROT NODE") or b.param("ROTNODE") or "").strip())
            if rots:
                self._rb_rot[ref] = rots[0]
                continue
            next_id += 1
            self.geom.add_node(next_id, self.geom.nodes.get(ref, (0.0, 0.0, 0.0)))
            self._rb_rot[ref] = self._rb_rot_synth[ref] = next_id
        for bodies in self._mpc_bodies.values():
            for body in bodies:
                ref = body["ref"]
                if ref not in self._rb_rot:
                    next_id += 1
                    self.geom.add_node(next_id, self.geom.nodes[ref])
                    self._rb_rot[ref] = self._rb_rot_synth[ref] = next_id
                body["rot"] = self._rb_rot[ref]
        self._plan_rigid_couplings(blocks)
        self._plan_rot_axes(self._rb_rot)              # the connector rows use them
        self._plan_connector_rows(blocks)
        self._plan_coupled_bcs(blocks)
        self._plan_velocity_bcs(blocks)       # after _plan_coupled_bcs: reads its card rewrites
        if any(b.keyword == "DYNAMIC" and b.has("EXPLICIT") for b in blocks) and any(
                any(m in self._plane_only for m in members)
                for _, members, _ in self._rigid_members(blocks)):
            self.report.warn("Rigid constraint (*RIGID BODY, kinematic coupling or *MPC BEAM) on "
                             "nodes of plane / axisymmetric elements in a deck with an explicit "
                             "dynamic step: ccx's explicit solver stops on it ('linear and nonlinear "
                             "MPC's depend on each other' — its 2-D expansion is built from linear "
                             "MPCs; probed on 2.23); only implicit steps can run it.", once=True)
        self._check_transforms()
        self._n_inactive_rot = 0
        self._depvar_counts = set()
        for b in blocks:
            if b.keyword == "DEPVAR":
                vals = [x for r in merged_data_records(b) for x in r if x != ""]
                try:
                    self._depvar_counts.add(int(float(vals[0])))
                except (IndexError, ValueError):
                    pass
        self._fields_set = any(
            b.keyword in ("FIELD", "USER DEFINED FIELD")
            or (b.keyword == "INITIAL CONDITIONS" and (b.param("TYPE") or "").upper() == "FIELD")
            for b in blocks)
        self._n_steps = sum(1 for b in blocks if b.keyword == "STEP")
        self._step_idx = 0
        self._step_nlgeom = False
        self._has_sensitivity = any(b.keyword in ("SENSITIVITY", "FEASIBLE DIRECTION") for b in blocks)
        # a *FREQUENCY step must store its eigenmodes (STORAGE=YES) for a later modal or
        # steady-state dynamics step to read them ("cannot open eigenvalue file")
        self._freq_storage = any(b.keyword in ("MODAL DYNAMIC", "STEADY STATE DYNAMICS",
                                               "COMPLEX FREQUENCY") for b in blocks)
        # *CYCLIC HARDENING is read by ccx only after a *PLASTIC, HARDENING=COMBINED of the
        # same material (one the converter does not comment out)
        self._cyclic_ok = set()
        combined = False
        for b in blocks:
            if b.keyword == "MATERIAL":
                combined = False
            elif b.keyword == "PLASTIC":
                combined = ((b.param("HARDENING") or "").upper() == "COMBINED" and
                            not (b.param("DATATYPE") or "").upper().startswith("PARAM"))
            elif b.keyword == "CYCLIC HARDENING" and combined:
                self._cyclic_ok.add(id(b))
        # the material each *EXPANSION card belongs to (named in handle_dependent_material's
        # notes); a gasket or connector behavior's expansion has none
        self._expansion_material = {}
        mat = "?"
        for b in blocks:
            if b.keyword == "MATERIAL":
                mat = (b.param("NAME") or "?").strip()
            elif b.keyword in ("STEP", "GASKET BEHAVIOR", "CONNECTOR BEHAVIOR") or \
                    b.keyword.endswith("SECTION"):
                mat = "?"
            elif b.keyword == "EXPANSION":
                self._expansion_material[id(b)] = mat
        # Abaqus gives nodes without an initial temperature 0; ccx stops ("no initial
        # temperature defined in node ...") once any are missing
        self._temp_ic_fill = False
        covered: set = set()
        any_temp_ic = False
        for b in blocks:
            if b.keyword == "INITIAL CONDITIONS" and (b.param("TYPE") or "").upper() == "TEMPERATURE":
                any_temp_ic = True
                for rec in merged_data_records(b):
                    if rec and rec[0]:
                        covered.update(self._resolve_nodes(rec[0]))
                covered.update(int(ln.split(",")[0]) for ln in self._midside_records(b, "field"))
        self._temp_ic_covered = covered if any_temp_ic else None     # _complete_temperature_ic
        if any_temp_ic and self.geom.nodes and not set(self.geom.nodes) <= covered:
            self._temp_ic_fill = True
        # ... and with none at all it stops on the first *TEMPERATURE card ("no thermal
        # *INITIAL CONDITIONS are given"): every node then starts at the Abaqus default, 0,
        # ahead of the first step (emit_other) — for the cards ccx reads: those outside steps,
        # in steps where temperature is a DOF and with USER are commented out
        self._temp_ic_default = False
        if not any_temp_ic and self.geom.nodes:
            steps: List[List[Block]] = []          # grouped as emit_other groups them
            inside = False
            for b in blocks:
                if b.keyword == "STEP" and not inside:
                    inside = True
                    steps.append([])
                elif b.keyword == "END STEP":
                    inside = False
                elif inside:
                    steps[-1].append(b)
            temps = [b for s in steps if not any(x.keyword in TEMPERATURE_DOF_PROCS for x in s)
                     for b in s if b.keyword == "TEMPERATURE" and not b.has("USER")]
            # temperatures ccx cannot take from the deck: with them the default would turn
            # ccx's stop into a run on undefined temperatures (probed on 2.23: with the FILE=
            # file missing ccx only prints "ERROR in readfrd")
            if any(b.has("FILE") for b in temps):
                self.report.warn("*TEMPERATURE, FILE= with no *INITIAL CONDITIONS, TYPE=TEMPERATURE: "
                                 "ccx stops on the card ('no thermal *INITIAL CONDITIONS'). The "
                                 "Abaqus default initial temperature (0) was not added: ccx reads "
                                 "FILE= as a CalculiX .frd results file, not Abaqus' .odb/.fil, and "
                                 "runs on undefined temperatures without one. Run the heat transfer "
                                 "in ccx and point FILE= at its .frd, then add the initial "
                                 "temperatures.", once=True)
            elif temps:
                self._temp_ic_default = True
        if self._temp_ic_fill or self._temp_ic_default:
            self.geom.nsets.setdefault(ALL_NODES_SET, list(self.geom.nodes))
        # Johnson-Cook *PLASTIC cards whose material also has a *RATE DEPENDENT card
        self._jc_with_rate = set()
        jc_block = None
        for b in blocks:
            if b.keyword == "MATERIAL":
                jc_block = None
            elif b.keyword == "PLASTIC" and \
                    (b.param("HARDENING") or "").upper().replace(" ", "") == "JOHNSONCOOK":
                jc_block = b
            elif b.keyword == "RATE DEPENDENT" and jc_block is not None:
                self._jc_with_rate.add(id(jc_block))
            elif b.keyword in ("STEP", "SOLID SECTION", "SHELL SECTION", "BEAM SECTION", "NODE",
                               "ELEMENT"):
                jc_block = None
        self._plan_expansion_as_ortho(blocks)
        self._plan_elastic_expansion(blocks)
        self._check_nlgeom_expansion(blocks)
        # distributed loads that become nodal forces need the plane-section thickness, the
        # beams' n1 directions and the DOFs the deck's own *CLOADs act on
        self._section_thick, self._beam_n1, self._deck_cloads = {}, {}, {}
        self._has_normal = any(b.keyword == "NORMAL" for b in blocks)
        # Abaqus models are 2-D or 3-D throughout: 2-D beams make every beam planar
        self._planar_beams = any(t.upper().startswith(("B21", "B22", "B23", "PIPE21", "PIPE22"))
                                 for t in self._elem_types)
        # a *DLOAD line with no element set loads the whole model (Abaqus); ccx needs a set
        if self.geom.elements and any(b.keyword == "DLOAD" and any(
                len(r) > 1 and not r[0].strip() for r in merged_data_records(b)) for b in blocks):
            self.geom.elsets.setdefault(ALL_ELEMENTS_SET, list(self.geom.elements))
        for b in blocks:
            recs = [[x.strip() for x in r] for r in merged_data_records(b)]
            if b.keyword == "SOLID SECTION":
                try:
                    t = pf(recs[0][0]) if recs and recs[0] and recs[0][0] else 1.0
                except ValueError:
                    t = 1.0
                for e in self.geom.elset(b.param("ELSET") or ""):
                    self._section_thick[e] = t
            elif b.keyword == "BEAM SECTION":
                # the second data line of a standard profile is the approximate n1 direction
                n1: Optional[Vec] = None
                sec = (b.param("SECTION") or "").strip().upper()
                if sec in ("RECT", "CIRC", "PIPE", "BOX", "THICK PIPE", "I", "L", "HEX", "TRAPEZOID",
                           "ELLIPSE"):
                    n1 = (0.0, 0.0, -1.0)
                    if len(recs) > 1 and len([x for x in recs[1] if x]) >= 3:
                        try:
                            n1 = tuple(pf(x) for x in [x for x in recs[1] if x][:3])
                        except ValueError:
                            n1 = None
                for e in self.geom.elset(b.param("ELSET") or ""):
                    self._beam_n1[e] = n1
            elif b.keyword == "CLOAD":
                amp = b.param("AMPLITUDE")
                for r in recs:
                    if len(r) > 1 and re.fullmatch(r"[-+]?\d+", r[1]):
                        for n in self._resolve_nodes(r[0]):
                            self._deck_cloads.setdefault((n, int(r[1])), set()).add(amp)
        # Abaqus prints the whole model when *EL PRINT / *NODE PRINT has no set; ccx
        # silently prints nothing — give those cards an explicit whole-model set
        if any(b.keyword == "EL PRINT" and not b.param("ELSET") for b in blocks) and self.geom.elements:
            self.geom.elsets[ALL_ELEMENTS_SET] = list(self.geom.elements)
        if any(b.keyword == "NODE PRINT" and not b.param("NSET") for b in blocks) and self.geom.nodes:
            self.geom.nsets[ALL_NODES_SET] = list(self.geom.nodes)

    def _check_undefined_materials(self, blocks: List[Block]) -> None:
        """A section naming a material the deck never defines is invalid input; ccx stops
        with 'nonexistent material' — and ccx 2.23 segfaults instead when the section has
        a data line (e.g. a plane-element thickness).  Flag it so the crash is explained."""
        defined = {(b.param("NAME") or "").upper() for b in blocks if b.keyword == "MATERIAL"}
        missing: "OrderedDict[str, str]" = OrderedDict()
        for b in blocks:
            if not b.keyword.endswith("SECTION"):
                continue
            names = [b.param("MATERIAL")] if b.param("MATERIAL") else []
            if b.has("COMPOSITE"):                       # ply lines: thick, nip, material, ...
                for rec in merged_data_records(b):
                    if len(rec) > 2 and rec[2].strip():
                        names.append(rec[2].strip())
            for nm in names:
                if nm and nm.upper() not in defined and nm.upper() not in missing:
                    missing[nm.upper()] = b.param("ELSET") or "?"
        for nm, elset in list(missing.items())[:5]:
            known = (f"defined: {', '.join(sorted(defined)[:6])}" if defined
                     else "the deck defines no *MATERIAL at all — is a material *INCLUDE missing?")
            self.report.warn(f"A section (ELSET={elset}) references material '{nm}', which is never "
                             f"defined ({known}). ccx stops with 'nonexistent material', and ccx "
                             f"2.23 segfaults instead when the section has a data line.", once=True)

    def _check_nonpositive_ids(self) -> None:
        """Abaqus requires positive node numbers; a deck numbered from 0 (some mesh
        writers do this) is invalid input, and ccx behaves unpredictably on it —
        unpatched builds can print 'Job finished' and then crash, patched builds reject
        the deck.  Flag it; renumbering is left to the user."""
        bad_n = sorted(n for n in self.geom.nodes if n <= 0)
        bad_e = sorted(e for e in self.geom.elements if e <= 0)
        if not (bad_n or bad_e):
            return
        parts = []
        if bad_n:
            parts.append(f"{len(bad_n)} node(s), e.g. {bad_n[0]}")
        if bad_e:
            parts.append(f"{len(bad_e)} element(s), e.g. {bad_e[0]}")
        self.report.warn(f"Non-positive numbering ({'; '.join(parts)}): Abaqus requires positive "
                         f"node/element numbers and ccx's behaviour is undefined (unpatched builds "
                         f"can crash after 'Job finished', patched builds reject the deck). "
                         f"Renumber the mesh.", once=True)

    # -- Abaqus *MPC lines -------------------------------------------------------
    @staticmethod
    def _mpc_fields(b: Block) -> List[List[str]]:
        """The data lines of an *MPC card as field lists (MPC type first)."""
        recs = [[x for x in rec if x != ""] for rec in merged_data_records(b)]
        return [r for r in recs if r]

    def _mpc_nodes(self, token: str) -> List[int]:
        """The nodes of one *MPC node field: a node number, or a node set in the order Abaqus
        pairs it (ascending ids unless the set is UNSORTED, as for *EQUATION)."""
        if re.fullmatch(r"[-+]?\d+", token):
            return [int(token)]
        nodes = self.geom.nset(token)
        return dedup(nodes) if token.upper() in self.geom.unsorted else sorted(set(nodes))

    def _mpc_pairs(self, f: List[str]) -> Optional[List[Tuple[int, int]]]:
        """(first node, second node) pairs of a two-node *MPC line ``TYPE, first, second``:
        node sets pair node by node, or every node of the first field with a single second
        node; None if a field names no defined node or the sets do not pair up."""
        if len(f) < 3:
            return None
        a, c = self._mpc_nodes(f[1]), self._mpc_nodes(f[2])
        if not a or not c or (len(c) != 1 and len(a) != len(c)) or \
                any(n not in self.geom.nodes for n in a + c):
            return None
        return [(n, c[0] if len(c) == 1 else c[i]) for i, n in enumerate(a)]

    def _plan_mpcs(self, blocks: List[Block]) -> None:
        """Deck-wide plan of the Abaqus *MPC lines (see handle_mpc): the node pairs of each
        PIN / TIE / LINK / BEAM line, or why the line cannot be converted.

        A BEAM MPC moves its first node with a rigid beam from the second (displacements
        and rotations), so all BEAM lines that share a second node — and lines chained
        through a node that is first in one line and second in another — move as ONE rigid
        body about the root of the chain.  Each such group becomes a ccx *RIGID BODY on the
        root: exact at any rotation, where linear *EQUATION ties hold for small ones only."""
        self._mpc_plan = {}
        self._mpc_bodies = {}
        steps: List[bool] = []
        for b in blocks:
            if b.keyword == "STEP":
                nl = b.param("NLGEOM")
                steps.append("NLGEOM" in b.params and (nl or "YES").strip().upper() != "NO")
            elif b.keyword == "DYNAMIC" and b.has("EXPLICIT") and steps:
                steps[-1] = True               # the converter runs explicit steps with NLGEOM
        # NLGEOM stays on for all later steps once a step has switched it on (Abaqus)
        self._nl_any, self._nl_all = any(steps), bool(steps) and steps[0]
        # a TIE also ties the temperature (DOF 11) where a step has one; a heat-transfer-only
        # deck has no displacements to tie
        procs = [b.keyword for b in blocks if b.keyword in PROC_KW]
        self._mpc_thermal = any(k in ("HEAT TRANSFER", "COUPLED TEMPERATURE-DISPLACEMENT",
                                      "UNCOUPLED TEMPERATURE-DISPLACEMENT") for k in procs)
        self._mpc_mechanical = not procs or any(k != "HEAT TRANSFER" for k in procs)
        quiet = Report()
        kinds: Dict[str, str] = {}
        self._expanded = set()                 # nodes of elements ccx expands to 3-D
        for typ, conn in self.geom.elements.values():
            if typ not in kinds:
                kinds[typ] = ccx_element_type(typ, quiet)
            cc = kinds[typ]
            if cc in SHELL_TYPES or cc in BEAM_TYPES or cc.startswith(("M3D",) + PLANE_ELEM_PREFIXES):
                self._expanded.update(conn)
        parent: "OrderedDict[int, int]" = OrderedDict()     # BEAM: dependent -> independent
        anchor: Dict[int, int] = {}                          # dependent -> id(its *MPC card)

        def root(n: int) -> int:
            while n in parent:
                n = parent[n]
            return n
        for b in blocks:
            if b.keyword != "MPC" or b.has("USER"):
                continue
            for i, f in enumerate(self._mpc_fields(b)):
                typ = f[0].upper()
                if typ not in ("PIN", "TIE", "LINK", "BEAM"):
                    continue
                key = (id(b), i)
                pairs = self._mpc_pairs(f)
                if pairs is None:
                    self._mpc_plan[key] = ("skip", f"*MPC {typ} line '{', '.join(f)}': a node "
                                           f"field names no defined node, or two node sets of "
                                           f"different sizes are paired; commented out — the "
                                           f"constraint is missing.")
                elif typ == "BEAM":
                    kept = []
                    for dep, ind in pairs:
                        if dep == ind or dep in parent or root(ind) == dep:
                            self.report.warn(f"*MPC BEAM: node {dep} is the dependent node of "
                                             f"more than one BEAM line, or the lines form a loop "
                                             f"(Abaqus rejects both); only its first line is "
                                             f"used.", once=True)
                            continue
                        parent[dep] = ind
                        anchor[dep] = id(b)
                        kept.append((dep, ind))
                    self._mpc_plan[key] = ("beam", kept) if kept else \
                        ("skip", f"*MPC BEAM line '{', '.join(f)}' adds no new dependent node; "
                                 f"commented out.")
                elif typ != "LINK":
                    self._mpc_plan[key] = (typ.lower(), pairs)
                else:
                    self._mpc_plan[key] = self._link_mode(pairs, "*MPC LINK")
        # rigid connectors (BEAM, WELD; see _plan_connectors) are the same rigid link with no
        # preferred direction: node b joins node a's body, or a joins b's, or b's chain is
        # first re-rooted at b (reversing a rigid link changes nothing)
        for a, c, sec in self._conn_beam:
            if root(a) == root(c):
                self.report.note("A rigid connector (BEAM / WELD) joins two nodes that already "
                                 "move as one rigid body; it adds nothing and is left out.",
                                 once=True)
                continue
            if c in parent and a not in parent:
                a, c = c, a
            if c in parent:
                path = [c]
                while path[-1] in parent:
                    path.append(parent[path[-1]])
                del parent[c], anchor[c]
                for i in range(len(path) - 1, 0, -1):
                    parent[path[i]] = path[i - 1]
                    anchor.setdefault(path[i], sec)
            parent[c] = a
            anchor[c] = sec
        groups: "OrderedDict[int, List[int]]" = OrderedDict()
        for dep in parent:                     # deck order, so a body's first member is its
            groups.setdefault(root(dep), []).append(dep)        # first line
        for ref, members in groups.items():
            self._mpc_bodies.setdefault(anchor[members[0]], []).append(
                {"ref": ref, "members": members, "rot": None})

    def _link_mode(self, pairs: Sequence[Tuple[int, int]], what: str) -> Tuple[str, object]:
        """How a constant-distance constraint between node pairs (dependent, independent) —
        Abaqus *MPC LINK or a LINK connector — is written: ("link-eq", pairs), its
        linearised *EQUATION, when no step runs NLGEOM; ("link-mpc", pairs), ccx's distance
        MPC (*MPC BEAM), under NLGEOM; or ("skip", why).  Uses the step facts of _plan_mpcs."""
        if any(vnorm(vsub(self.geom.nodes[a], self.geom.nodes[c])) == 0.0 for a, c in pairs):
            return ("skip", f"{what} between coincident nodes has no direction to keep a distance "
                            f"along; commented out — the constraint is missing.")
        if not self._nl_any:
            self.report.note(f"{what} in a deck without NLGEOM -> its linearised *EQUATION (the "
                             f"distance constraint at the initial geometry, as in an Abaqus "
                             f"small-displacement analysis; exact).", once=True)
            return ("link-eq", pairs)
        if any(n in self._expanded for p in pairs for n in p):
            return ("skip", f"{what} under NLGEOM on a node of a beam, truss, shell, membrane or "
                            f"plane element: ccx's distance MPC (*MPC BEAM) rejects such nodes "
                            f"('*ERROR in gen3dmpc: nodes belonging to 1D/2D elements must not be "
                            f"subject to a BEAM MPC') and a linear *EQUATION is exact for small "
                            f"rotations only; commented out — the constraint is missing.")
        if not self._nl_all and not self._approx:
            return ("skip", f"{what} in a deck whose first step is linear and a later one NLGEOM: "
                            f"Abaqus linearises the link in the small-displacement step, while "
                            f"ccx's distance MPC (*MPC BEAM) runs every step geometrically "
                            f"nonlinear; commented out — rerun with --approximate to use *MPC BEAM "
                            f"in all steps.")
        if self._nl_all:
            self.report.note(f"{what} under NLGEOM -> ccx *MPC BEAM, which keeps the distance "
                             f"between the two nodes (exact).", once=True)
        else:
            self.report.warn(f"[APPROX] {what} -> ccx *MPC BEAM in a deck whose first step is "
                             f"linear: ccx runs every step geometrically nonlinear with it, where "
                             f"Abaqus linearises the link in the small-displacement steps.",
                             once=True)
        return ("link-mpc", pairs)

    # -- connector elements (CONN3D2 / CONN2D2) ------------------------------------
    def _conn_axes(self, name: str) -> Optional[Tuple[Vec, Vec, Vec]]:
        """Unit local directions (e1, e2, e3) of the rectangular *ORIENTATION ``name``, its
        additional rotation applied, or None."""
        key = name.strip().strip('"').upper()
        hit = next((k for k in self.orientations if k.strip('"') == key), None)
        if hit is None:
            return None
        a, bvec, system = self.orientations[hit]
        e1, e3 = vunit(a), vunit(vcross(a, bvec))
        if not system.upper().startswith("RECT") or vnorm(e1) < 0.5 or vnorm(e3) < 0.5:
            return None
        axes = [e1, vcross(e3, e1), e3]
        rot = self._orient_rotation.get(hit)
        if rot and rot[0] in (1, 2, 3) and rot[1]:
            k = rot[0] - 1
            axes = [v if i == k else rotate_about_axis(v, (0.0, 0.0, 0.0), axes[k], rot[1])
                    for i, v in enumerate(axes)]
        return axes[0], axes[1], axes[2]

    _CONN_OWN_ROTATION = (
        "Connector on the rotation of a node with a *TRANSFORM that carries its rotation on its "
        "own DOFs 4-6 (a shell/beam node, or a kinematic coupling's reference node): ccx 2.23 "
        "misreads *EQUATION terms on DOFs 4-6 of a node with a *TRANSFORM (DOF 4 as the global "
        "rotation, DOFs 5 and 6 through an out-of-range read of the transformation matrix; "
        "probed), so the constraint cannot be written there; commented out — the connector is "
        "missing.")

    @staticmethod
    def _conn_axes_reason(why: str) -> str:
        """Why a connector on a node whose local axes are undefined is commented out (``why``
        from _local_axes, without the node: one reason, and warning, for all such nodes)."""
        why = re.sub(r"\bnode \d+", "a node", why)
        return (f"Connector on a node without defined local axes: {why}. Abaqus does not define "
                f"the directions of the constraint's DOFs there; commented out — the connector "
                f"is missing.")

    def _plan_connectors(self, blocks: List[Block]) -> None:
        """Connector elements, part 1 of their plan: before _plan_mpcs, whose rigid bodies the
        rigid connectors join (part 2 is _plan_connector_rows).  ccx has no connector
        element, but without a *CONNECTOR BEHAVIOR a connector is just the kinematic
        constraint of its connection type, which ccx holds exactly:

        * JOIN: node b keeps its initial position in node a's local system, which turns with
          node a when node a has rotations (else fixed directions; Abaqus): u_b - u_a -
          theta_a x d = 0 with d = x_b - x_a at the start, linearised;
        * REVOLUTE: relative rotation about node a's local 1-direction e1 only, i.e.
          (theta_b - theta_a) parallel to e1: two equations, linear in the rotation vectors
          ccx solves for — exact for small rotations, and at any rotation when one side
          cannot turn (the axis then stays put).  HINGE = JOIN + REVOLUTE;
        * ALIGN: theta_b = theta_a;
        * BEAM, and WELD (JOIN + ALIGN, the same rigid link): node b moves rigidly with
          node a — a rigid body through the *MPC BEAM plan, exact at any rotation;
        * LINK: as *MPC LINK;  CARTESIAN, CARDAN, ...: no constraint, nothing to transmit.

        This part reads each *CONNECTOR SECTION (connection type, node a's local directions,
        each element's initial offset) and gives every element a route: "rows" (constraint
        equations, built in part 2), "beam" (rigid body), "link", "free" (no constraint) or
        "skip" (commented out, with the reason).  Shell/beam nodes whose rotations the rows
        use become knots (_plan_rigid_couplings): ccx ignores DOFs 4-6 of a plain shell/beam
        node in an *EQUATION."""
        self._conn_plan = {}
        self._conn_beam = []
        self._conn_knots = []
        if not self._conn:
            return
        quiet = Report()
        rotn: set = set()                       # shell/beam nodes: rotations of their own
        for typ, conn in self.geom.elements.values():
            cc = ccx_element_type(typ, quiet)
            if cc in SHELL_TYPES or (cc in BEAM_TYPES and not cc.startswith(("T2D", "T3D"))):
                rotn.update(conn)
        segs = self._bc_segments(blocks)
        held: Optional[set] = None              # (node, DOF) held at zero in every step
        for active in bc_steps(segs):
            now = {k for k, z in active.items() if z}
            held = now if held is None else held & now
        self._conn_held = held or set()
        self._conn_bc_dofs = {k for seg in segs for _, k, _ in seg}
        # nodes whose rotation is loaded or prescribed (not just held at zero)
        turned = {n for seg in segs for _, (n, d), _ in seg
                  if 4 <= d <= 6 and (n, d) not in self._conn_held}
        for b in blocks:
            if b.keyword == "CLOAD":
                for rec in merged_data_records(b):
                    if len(rec) > 1 and re.fullmatch(r"[456]", rec[1].strip()):
                        turned.update(self._resolve_nodes(rec[0].strip()))
        self._conn_turned = turned
        # rotations that exist apart from the connectors: reference / rotation nodes of
        # rigid constraints and the nodes of *MPC BEAM lines
        refs: set = set()
        for b in blocks:
            if b.keyword in ("RIGID BODY", "COUPLING", "KINEMATIC COUPLING", "DISTRIBUTING COUPLING"):
                for k, v in b.params.items():
                    if k.replace(" ", "") in ("REFNODE", "ROTNODE") and v:
                        refs.update(self._resolve_nodes(v.strip())[:1])
            elif b.keyword == "MPC" and not b.has("USER"):
                for f in self._mpc_fields(b):
                    if f[0].upper() == "BEAM":
                        refs.update(n for tok in f[1:3] for n in self._mpc_nodes(tok))
        # behaviours that define anything (sub-options follow *CONNECTOR BEHAVIOR)
        rich: set = set()
        cur = None
        for b in blocks:
            if b.keyword == "CONNECTOR BEHAVIOR":
                cur = (b.param("NAME") or "").strip().upper()
            elif cur is not None and b.keyword.startswith("CONNECTOR ") and \
                    b.keyword != "CONNECTOR SECTION":
                rich.add(cur)
            else:
                cur = None
        procs = [b.keyword for b in blocks if b.keyword in PROC_KW]
        mechanical = not procs or any(k != "HEAT TRANSFER" for k in procs)
        explicit = any(b.keyword == "DYNAMIC" and b.has("EXPLICIT") for b in blocks)
        items: List[Tuple[dict, int]] = []
        planned: set = set()
        for b in blocks:
            if b.keyword != "CONNECTOR SECTION":
                continue
            elset = (b.param("ELSET") or "").strip()
            sec: dict = {"items": [], "reason": None}
            self._conn_plan[id(b)] = sec
            eids = [e for e in dedup(self.geom.elset(elset)) if e in self._conn]
            if not eids:
                sec["reason"] = (f"*CONNECTOR SECTION on ELSET={elset}, which holds no connector "
                                 f"element (CONN3D2 / CONN2D2); commented out.")
                continue
            recs = merged_data_records(b)
            words = [x.strip().upper() for x in (recs[0] if recs else []) if x.strip()]
            oris = [x.strip() for x in recs[1]] if len(recs) > 1 else []
            label = "/".join(words) or "(none)"
            if len(words) == 1 and words[0] in CONN_ASSEMBLED:
                trans, rot = CONN_ASSEMBLED[words[0]]
            elif words == ["BEAM"]:
                trans = rot = "BEAM"
            else:
                trans = next((w for w in words if w in CONN_TRANSLATIONAL), None)
                rot = next((w for w in words if w in CONN_ROTATIONAL), None)
                if not words or len(words) != (trans is not None) + (rot is not None):
                    trans = rot = "?"
            t = None if trans in CONN_UNCONSTRAINED else trans
            r = None if rot in CONN_UNCONSTRAINED else rot
            beh = (b.param("BEHAVIOR") or "").strip().upper()
            why = None
            if trans == "?":
                kind, why = "skip", (f"*CONNECTOR SECTION: connection type {label} is not an Abaqus "
                                     f"connection type the converter knows; commented out — the "
                                     f"connector is missing.")
            elif beh in rich:
                kind, why = "skip", ("*CONNECTOR SECTION with a *CONNECTOR BEHAVIOR (elasticity, "
                                     "damping, stops, locks, friction, ...): ccx has no connector "
                                     "element to carry it; commented out — the connector is "
                                     "missing.")
            elif not mechanical:
                kind = "free"
                self.report.note("Connector elements left out: a heat-transfer-only deck has no "
                                 "displacements for them to constrain.", once=True)
            elif (t, r) in (("BEAM", "BEAM"), ("JOIN", "ALIGN")):
                kind = "rigid"
            elif t is None and r is None:
                kind = "free"
                self.report.note(f"Connector of type {label}: it constrains no relative motion "
                                 f"and has no behaviour, so it transmits nothing — left out.",
                                 once=True)
            elif t in (None, "JOIN") and r in (None, "REVOLUTE", "ALIGN"):
                kind = "rows"
            elif t == "LINK" and r is None:
                kind = "link"
            else:
                kind, why = "skip", (f"*CONNECTOR SECTION: connection type {label} is not converted "
                                     f"(the converter writes JOIN, REVOLUTE, ALIGN, HINGE, WELD, "
                                     f"BEAM, LINK and the unconstrained types); commented out — "
                                     f"the connector is missing.")
            if beh and beh not in rich:
                self.report.note(f"*CONNECTOR SECTION, BEHAVIOR={beh}: the behaviour defines nothing "
                                 f"and is ignored.", once=True)
            for e in eids:
                if e in planned:
                    self.report.warn("A connector element belongs to more than one *CONNECTOR "
                                     "SECTION; the first one is used.", once=True)
                    continue
                planned.add(e)
                typ, na, nb = self._conn[e]
                it = {"eid": e, "a": na, "b": nb, "dim": 2 if typ == "CONN2D2" else 3,
                      "route": kind, "reason": why, "trans": t, "rot": r, "d": (0.0, 0.0, 0.0)}
                sec["items"].append(it)
                if kind in ("skip", "free"):
                    continue
                if any(n is not None and n not in self.geom.nodes for n in (na, nb)) or na == nb:
                    it["route"], it["reason"] = "skip", ("Connector element on an undefined node, "
                                                         "or with the same node twice; commented "
                                                         "out — the connector is missing.")
                    continue
                if na is not None and nb is not None:
                    it["d"] = vsub(self.geom.nodes[nb], self.geom.nodes[na])
                if r == "REVOLUTE":
                    axes = self._conn_axes(oris[0]) if oris and oris[0] else \
                        ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
                    other = self._conn_axes(oris[1]) if len(oris) > 1 and oris[1] else axes
                    if it["dim"] == 2:
                        it["route"], it["reason"] = "skip", (f"*CONNECTOR SECTION: {label} on a "
                                                             f"CONN2D2 element (REVOLUTE is a 3-D "
                                                             f"connection type); commented out.")
                    elif axes is None or other is None:
                        it["route"], it["reason"] = "skip", (
                            "*CONNECTOR SECTION: the local directions of a REVOLUTE / HINGE "
                            "connector (its *ORIENTATION) are missing or not rectangular "
                            "coordinates the converter reads; commented out — the connector "
                            "is missing.")
                    elif abs(vdot(axes[0], other[0])) < 1.0 - 1e-6:
                        it["route"], it["reason"] = "skip", (
                            "*CONNECTOR SECTION: a REVOLUTE / HINGE connector whose node b has "
                            "a local 1-direction other than node a's at the start (Abaqus then "
                            "holds that misalignment) is not converted; commented out.")
                    else:
                        it["e1"] = axes[0]
                items.append((it, id(b)))
        if not items:
            return
        # nodes whose rotation more than one connector uses
        uses: Dict[int, int] = {}
        for it, _ in items:
            if it["route"] in ("rows", "rigid") and it["rot"] is not None:
                for n in (it["a"], it["b"]):
                    if n is not None:
                        uses[n] = uses.get(n, 0) + 1

        def turns(n: Optional[int]) -> bool:
            return n is not None and (n in rotn or n in refs or n in turned or uses.get(n, 0) > 1)

        def free_rotation(n: Optional[int], dim: int) -> bool:
            dofs = (6,) if dim == 2 else (4, 5, 6)
            return n is not None and not all((n, d) in self._conn_held for d in dofs)
        for it, sec_id in items:
            a, b, dim = it["a"], it["b"], it["dim"]
            if it["route"] == "rigid":
                if a is None or b is None or not (turns(a) or turns(b)):
                    # to ground, or between nodes without rotations of their own: JOIN rows
                    # (the ALIGN part only fixes connector-only rotations), or, offset, a link
                    if a is not None and b is not None and vnorm(it["d"]) > 0.0:
                        it["route"] = "link"
                    else:
                        it["route"], it["trans"], it["rot"] = "rows", "JOIN", "ALIGN"
                else:
                    it["route"] = "beam"
                    self._conn_beam.append((a, b, sec_id))
                    continue
            if it["route"] == "link" and (a is None or b is None):
                it["route"], it["reason"] = "skip", ("Connector LINK to ground has no length to "
                                                     "keep (Abaqus puts the ground point at the "
                                                     "other node); commented out.")
            if it["route"] != "rows" or explicit:   # (explicit dynamics: no equations on knots)
                continue
            ends = [a, b] if it["rot"] is not None else \
                [a] if vnorm(it["d"]) > 0.0 else []
            if any(n in rotn and free_rotation(n, dim) and n in self._transformed for n in ends):
                it["route"], it["reason"] = "skip", self._CONN_OWN_ROTATION
                continue
            self._conn_knots += [n for n in ends if n in rotn and free_rotation(n, dim)]

    def _kinematic_refs(self, blocks: List[Block]) -> set:
        """Reference nodes of kinematic couplings that couple translations, where ccx carries
        the coupling's rotation on the node's own DOFs 4-6 (BCs and moments there act on it,
        and an *EQUATION can use them as independent terms — ccx eliminates them itself);
        not a shell/beam reference node, whose coupling becomes a *RIGID BODY."""
        refs: set = set()
        for i, b in enumerate(blocks):
            ref = self._first_node(b.param("REF NODE") or b.param("REFNODE") or "")
            if ref is None or ref in self._rot_nodes:
                continue
            if b.keyword == "COUPLING" and i + 1 < len(blocks) and \
                    blocks[i + 1].keyword == "KINEMATIC" and \
                    self._kinematic_dofs(blocks[i + 1]) & {1, 2, 3}:
                refs.add(ref)
            elif b.keyword == "KINEMATIC COUPLING":
                for rec in merged_data_records(b):
                    f = [x for x in rec if x != ""]
                    try:
                        if f and (len(f) < 2 or min(pint(x) for x in f[1:3]) <= 3):
                            refs.add(ref)
                    except ValueError:
                        pass
        return refs

    def _plan_connector_rows(self, blocks: List[Block]) -> None:
        """Connector elements, part 2 of their plan (after the rigid bodies and knots): the
        LINK routes, and the constraint equations of the "rows" route, as *BOUNDARY lines
        and *EQUATIONs on the ccx DOFs:

        * rows in node DOFs: translations 1-3 and the rotation vector 4-6 (DOF 6 alone in
          2-D) of nodes a and b; a grounded node has none;
        * a DOF held at zero in every step (its BC) drops out of the rows;
        * a rotation lives where ccx has it: on the ROT NODE of a reference point (DOFs
          1-3), on a knotted shell/beam node itself, on DOFs 4-6 of a kinematic coupling's
          reference node, on the body of a rigid-body member — or, for a node with no
          rotation of its own (solid, plane or free node), on a new rotation node when the
          rotation shows elsewhere (another connector, a moment, a prescribed rotation);
          otherwise it is a connector-only unknown that Abaqus adds and nothing else
          touches, and it is eliminated from the rows (what is left is what it constrains);
        * a row left with one DOF holds it at zero (a *BOUNDARY in every step); the others
          become *EQUATIONs;
        * ccx — like Abaqus — reads the DOFs of a node with a *TRANSFORM in its local axes (and
          a rotation node's in its reference node's, _plan_rot_axes): a global component k
          there becomes sum_j e_j[k] times local DOF j, a BC holds a local DOF, and an
          equation eliminates a DOF without local axes where it can (ccx turns an eliminated
          local DOF into a global one by its own rule, which _settle_dependents follows).
          Where the local axes are undefined (a node on its cylinder axis, several cards), or
          a rotation lives on DOFs 4-6 of a transformed shell/beam or kinematic reference node
          (ccx misreads those, probed), the connector is commented out.

        Under NLGEOM (or explicit dynamics) the linear rows are exact only as boundary
        conditions, as equations among the rotation components of one rotation node (a
        revolute whose other side cannot turn: the axis stays put), or as equations among
        the translations of plain nodes (a plain node may also follow a reference point's
        translations: no MPC of ccx's own eliminates either, probed).  ccx 2.23 also solves *EQUATIONs that link two
        rigid bodies' reference / rotation DOFs inaccurately under NLGEOM (probed), so the
        rest is commented out, or written with an [APPROX] warning under --approximate."""
        items = [it for sec in self._conn_plan.values() for it in sec["items"]]
        for it in items:
            if it["route"] == "link":
                mode, arg = self._link_mode([(it["b"], it["a"])], "Connector LINK")
                if mode == "skip":
                    it["route"], it["reason"] = "skip", arg
                    continue
                it["link"] = mode
                # its *EQUATION is written in local DOFs (_link_equation); ccx's distance MPC
                # under NLGEOM is not affected by a *TRANSFORM (probed)
                why = next((x for x in (self._local_axes(n) for n in (it["b"], it["a"])
                                        if n in self._transformed) if isinstance(x, str)), None)
                if mode == "link-eq" and why:
                    it["route"], it["reason"] = "skip", self._conn_axes_reason(why)
        rows_items = [it for it in items if it["route"] == "rows"]
        if not rows_items:
            return
        kin = self._kinematic_refs(blocks)
        # a rigid body's member turns with the body (*RIGID BODY: its TIE members)
        body_of = {m: body for bodies in self._mpc_bodies.values() for body in bodies
                   for m in body["members"]}
        for b in blocks:
            ref = self._first_node(b.param("REF NODE") or b.param("REFNODE") or "") \
                if b.keyword == "RIGID BODY" else None
            if ref is not None:
                for m in self._rigid_body_members(b)[0]:
                    if m != ref:
                        body_of.setdefault(m, {"ref": ref})

        def carrier(n: int) -> Optional[Tuple[int, int]]:
            """(node, its DOF that carries rotation component 1) of node n's rotation."""
            for _ in range(len(body_of) + 1):
                if n in kin:
                    return (n, 4)
                if n in self._rb_rot:
                    return (self._rb_rot[n], 1)
                if n in self._rot_nodes and n in self._knots:
                    return (n, 4)
                if n not in body_of:
                    return None
                n = body_of[n]["ref"]
            return None
        busy = {(m, d) for _, members, dofs in self._rigid_members(blocks)
                for m in members for d in dofs}
        # (a transformed node's local DOFs all mix the global ones ccx eliminates)
        busy |= {(m, j) for m, d in list(busy) if d <= 3 and m in self._transformed
                 for j in (1, 2, 3)}
        nonplain = {n for n, _ in busy} | self._ref_nodes | set(self._rb_rot.values()) | \
            set(self._knots) | kin
        held = self._conn_held

        def frame(n: int) -> Union[None, str, Tuple[Vec, Vec, Vec]]:
            """The local axes in which ccx reads DOFs 1-3 of node ``n``, None for the global
            ones, or why they are undefined."""
            if n in self._rot_axes:
                e1, e2 = self._rot_axes[n]
                return e1, e2, vcross(e1, e2)
            return self._local_axes(n) if n in self._transformed else None
        # rotation-node DOFs held in every step: BCs moved there from DOFs 4-6 of its node
        rot_held = {(self._rb_rot[n], d - 3) for n, d in held if 4 <= d <= 6 and n in self._rb_rot}
        skew = lambda d: ((0.0, -d[2], d[1]), (d[2], 0.0, -d[0]), (-d[1], d[0], 0.0))  # noqa: E731

        def rows_of(it: dict, a_turns: bool) -> List[Dict[Tuple[int, int], float]]:
            a, b, d, dim = it["a"], it["b"], it["d"], it["dim"]
            rows: List[Dict[Tuple[int, int], float]] = []
            if it["rot"] == "REVOLUTE" and vnorm(vcross(it["e1"], d)) <= 1e-9 * vnorm(d) and \
                    (b is None or all((b, g) in held for g in (4, 5, 6))):
                a_turns = False      # node a then turns about e1 only, which leaves d in place
            if it["trans"] == "JOIN":                 # u_b - u_a - theta_a x d = 0
                for k in ((1, 2) if dim == 2 else (1, 2, 3)):
                    row: Dict[Tuple[int, int], float] = {}
                    if b is not None:
                        row[(b, k)] = 1.0
                    if a is not None:
                        row[(a, k)] = -1.0
                        if a_turns and dim == 2:
                            row[(a, 6)] = d[1] if k == 1 else -d[0]
                        elif a_turns:
                            row.update(((a, 3 + m), skew(d)[k - 1][m - 1]) for m in (1, 2, 3))
                    rows.append(row)
            if it["rot"] == "ALIGN":                  # theta_b = theta_a
                for g in ((6,) if dim == 2 else (4, 5, 6)):
                    rows.append({**({(b, g): 1.0} if b is not None else {}),
                                 **({(a, g): -1.0} if a is not None else {})})
            elif it["rot"] == "REVOLUTE":             # (theta_b - theta_a) parallel to e1
                e1 = it["e1"]
                p = max(range(3), key=lambda k: abs(e1[k]))
                for i in (k for k in range(3) if k != p):
                    c = e1[i] / e1[p]
                    row = {}
                    if b is not None:
                        row.update({(b, 4 + i): 1.0, (b, 4 + p): -c})
                    if a is not None:
                        row.update({(a, 4 + i): -1.0, (a, 4 + p): c})
                    rows.append(row)
            return [{k: v for k, v in rw.items() if abs(v) > 1e-14} for rw in rows]

        def native(rw: Dict[Tuple[int, int], float]) -> Union[str, Dict[Tuple[int, int], float]]:
            """Row ``rw`` of rows_of in the DOFs ccx reads, those a BC holds at zero in every
            step dropped (in the axes ccx holds them) — or why it cannot be written.  A term
            on a node without local axes stays as it is (dof() moves a rotation to its
            carrier); on a transformed node global component k becomes sum_j e_j[k] times
            local DOF j, and a rotation goes to its rotation node's DOFs in that node's axes."""
            out: "OrderedDict[Tuple[int, int], float]" = OrderedDict()
            local = False

            def add(k: Tuple[int, int], v: float) -> None:
                out[k] = out.get(k, 0.0) + v

            def spread(n: int, base: int, k: int, v: float, ax: Tuple[Vec, Vec, Vec],
                       skip: set) -> None:
                for j in range(3):
                    if ax[j][k] and (n, base + j) not in skip:
                        add((n, base + j), v * ax[j][k])
            unit = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
            for (n, d), v in rw.items():
                own = frame(n)
                if d <= 3:
                    if own is None:
                        if (n, d) not in held:
                            add((n, d), v)
                    elif isinstance(own, str):
                        return own
                    else:
                        local = True
                        spread(n, 1, d - 1, v, own, held)
                    continue
                c = carrier(n)
                zero = all((n, g) in held for g in (4, 5, 6))        # zero in any axes
                if c is None:                     # a connector-only rotation (eliminated)
                    if own is None or (isinstance(own, str) and
                                       not any((n, g) in held for g in (4, 5, 6))):
                        if (n, d) not in held:
                            add((n, d), v)
                    elif isinstance(own, str) and not zero:
                        return own
                    elif not zero:
                        local = True
                        spread(n, 4, d - 4, v, own, held)
                elif c[1] == 4:                   # the node's own DOFs 4-6 (ccx misreads them
                    if c[0] not in self._transformed:          # on a transformed node)
                        if (n, d) not in held:
                            add((n, d), v)
                    elif not zero:
                        return self._CONN_OWN_ROTATION
                else:                             # DOFs 1-3 of a rotation node
                    ax = frame(c[0])
                    if ax is None and (own is None or isinstance(own, str)):
                        if (n, d) not in held:
                            add((n, d), v)        # (dof() moves it there)
                    elif isinstance(ax, str):
                        return ax
                    elif not zero:
                        local = True
                        spread(c[0], 1, d - 4, v, ax or unit, rot_held)
            big = max([abs(v) for v in out.values()] or [0.0])
            return OrderedDict((k, v) for k, v in out.items()
                               if abs(v) > 1e-14 and (not local or abs(v) > 1e-12 * big))

        def natives(it: dict, a_turns: bool) -> List[Dict[Tuple[int, int], float]]:
            rows = [native(rw) for rw in rows_of(it, a_turns)]
            return [rw for rw in rows if not isinstance(rw, str)]

        def is_local(k: Tuple[int, int]) -> bool:
            return k[1] <= 3 and isinstance(frame(k[0]), tuple)
        # rotations that show beyond one connector get a rotation node of their own
        uses: Dict[int, int] = {}
        for it in rows_items:
            if it["rot"] is None:
                continue
            for n in {k[0] for rw in natives(it, True) for k in rw if k[1] >= 4}:
                uses[n] = uses.get(n, 0) + 1
        for it in rows_items:                 # a JOIN offset turns with rotations node a has
            a = it["a"]
            if it["rot"] is None and a in uses and \
                    any(k[0] == a and k[1] >= 4 for rw in natives(it, True) for k in rw):
                uses[a] += 1
        synth = sorted(n for n, c in uses.items() if carrier(n) is None and
                       n not in self._rot_nodes and (c > 1 or n in self._conn_turned))
        next_id = max(self.geom.nodes, default=0)
        for n in synth:
            next_id += 1
            self.geom.add_node(next_id, self.geom.nodes[n])
            self._rb_rot[n] = next_id
            self._ref_nodes.add(n)
            self._conn_rot.add(next_id)
        self._plan_rot_axes({n: self._rb_rot[n] for n in synth})
        rot_held |= {(self._rb_rot[n], d - 3) for n, d in held if 4 <= d <= 6 and n in synth}
        if synth:
            self.report.note(f"Connector rotations on {len(synth)} node(s) without rotations of "
                             f"their own (solid, plane or free nodes) live on new rotation nodes "
                             f"(DOFs 1-3 = the rotation vector, as a *RIGID BODY's ROT NODE); "
                             f"BCs and moments on DOFs 4-6 of those nodes are moved there."
                             + (" The rotation node of a node with a *TRANSFORM has the node's "
                                "local axes (a rectangular *TRANSFORM), in which Abaqus reads "
                                "those BCs and moments." if any(self._rb_rot[n] in self._rot_axes
                                                                for n in synth) else ""))
        explicit = any(b.keyword == "DYNAMIC" and b.has("EXPLICIT") for b in blocks)
        nl = self._nl_any or explicit
        carriers = set(self._rb_rot.values())          # rotation nodes (DOFs 1-3 turn)
        synth_nodes = {self._rb_rot[n] for n in synth}

        def turning(n: int, d: int) -> bool:
            return d >= 4 or n in carriers

        def plain(n: int, d: int) -> bool:
            """A translation no ccx MPC of its own touches."""
            return not turning(n, d) and n not in nonplain

        def moved(k: Tuple[int, int]) -> bool:
            """A local translation of a node with a *TRANSFORM of its own (not a rotation node
            with its reference node's axes)."""
            return k[1] <= 3 and k[0] in self._transformed and is_local(k)

        def gauss_jordan(rows: List["OrderedDict[Tuple[int, int], float]"]) -> \
                List["OrderedDict[Tuple[int, int], float]"]:
            """Rows with local DOFs reduced (Gauss-Jordan) on the local translations of a
            transformed node first — node b's where it has them — then on the other local DOFs,
            each pivot in one row only: the rows of a JOIN become one per local DOF of the node
            (projected on its axes), as ccx 2.23 needs under NLGEOM (probed: an *EQUATION with
            several local translations of one node fails to converge or drifts there; one per
            equation is exact), and a row left with one DOF holds it.  The eliminated DOF of a
            row is then one without local axes where the row has one (chosen as for the other
            connectors, not twice), else its pivot; it is listed first."""
            rows = [OrderedDict(rw) for rw in rows]
            pivots: List[Optional[Tuple[int, int]]] = [None] * len(rows)
            for i in range(len(rows)):
                rw = rows[i]
                free = [k for k in rw if k not in busy and not (k[0] in kin and k[1] >= 4)]
                if not free:
                    continue
                top = max(abs(rw[k]) for k in free)
                big = [k for k in free if abs(rw[k]) >= 0.1 * top]
                pick = [k for k in big if moved(k)] or [k for k in big if is_local(k)]
                if pick:
                    p = max((k for k in pick if k[0] == pick[0][0]), key=lambda k: abs(rw[k]))
                else:
                    p = next((k for k in big if plain(*k) and k not in self._conn_bc_dofs), big[0])
                pivots[i] = p
                for j, other in enumerate(rows):
                    if j != i and p in other:
                        f = other[p] / rw[p]
                        for k, v in rw.items():
                            other[k] = other.get(k, 0.0) - f * v
                        del other[p]
                        m = max([abs(v) for v in other.values()] or [0.0])
                        rows[j] = OrderedDict((k, v) for k, v in other.items() if abs(v) > 1e-12 * m)
            out: List["OrderedDict[Tuple[int, int], float]"] = []
            used: set = set()
            for rw, p in zip(rows, pivots):
                if not rw:
                    continue
                if p is not None and is_local(p) and len(rw) > 1:
                    top = max(abs(v) for v in rw.values())
                    glob = sorted((k for k in rw if not is_local(k) and k not in busy and k not in used
                                   and not (k[0] in kin and k[1] >= 4) and abs(rw[k]) >= 0.1 * top),
                                  key=lambda k: (not (plain(*k) and k not in self._conn_bc_dofs),
                                                 -abs(rw[k])))
                    p = glob[0] if glob else p
                    used.add(p)
                out.append(rw if p is None else
                           OrderedDict([(p, rw[p])] + [(k, v) for k, v in rw.items() if k != p]))
            # ccx eliminates a global DOF for a local first term: the first component from the
            # term's own direction on (1 -> 2 -> 3 -> 1) of size 1e-5 or more that no earlier
            # equation took, and stops when none is left ('cannot be converted in MPC: all') —
            # which some axes reach in one order and not another (probed): the rows whose first
            # terms are local DOFs of one node go in an order in which each finds one
            for n in dedup([next(iter(rw))[0] for rw in out if rw and is_local(next(iter(rw)))]):
                idx = [i for i, rw in enumerate(out) if rw and next(iter(rw))[0] == n and
                       is_local(next(iter(rw)))]
                ax = frame(n)

                def found(perm: Sequence[int]) -> bool:
                    tk: set = set()
                    for i in perm:
                        rw = out[i]
                        j = next(iter(rw))[1]
                        g = next((g for g in ((j - 1 + q) % 3 + 1 for q in range(3))
                                  if g not in tk and abs(ax[j - 1][g - 1]) >= 1e-5), None)
                        top = max(abs(v) for v in rw.values())
                        if g is None or abs(sum(v * ax[q - 1][g - 1] for (m, q), v in rw.items()
                                                if m == n and q <= 3)) <= 1e-6 * top:
                            return False
                        tk.add(g)
                    return True
                if len(idx) > 1 and not found(idx):
                    perm = next((p for p in itertools.permutations(idx) if found(p)), None)
                    if perm is not None:
                        rows_n = [out[i] for i in perm]
                        for i, rw in zip(idx, rows_n):
                            out[i] = rw
            return out
        for it in rows_items:
            a = it["a"]
            a_turns = it["rot"] is not None or (a is not None and (carrier(a) is not None or
                                                                   a in self._rot_nodes))
            rows = [native(rw) for rw in rows_of(it, a_turns)]
            why = next((rw for rw in rows if isinstance(rw, str)), None)
            if why is not None:
                it["route"], it["reason"] = "skip", why if why == self._CONN_OWN_ROTATION else \
                    self._conn_axes_reason(why)
                continue
            rows = [rw for rw in rows if rw]
            if any(k[1] >= 4 and k[0] in self._rot_nodes and carrier(k[0]) is None
                   for rw in rows for k in rw):
                # a shell/beam node's rotation without a knot (explicit dynamics, where the
                # converter makes none): ccx would ignore it in an *EQUATION
                it["route"], it["reason"] = "skip", (
                    "Connector on the rotation of a shell/beam node in a deck with explicit "
                    "dynamics: ccx ignores DOFs 4-6 of a plain shell/beam node in an *EQUATION, "
                    "and its explicit solver stops on the knot that would give the node real "
                    "rotations; commented out — the connector is missing.")
                continue
            # eliminate connector-only rotations: the rows that fix them say nothing else
            for col in sorted({k for rw in rows for k in rw if k[1] >= 4 and carrier(k[0]) is None}):
                with_col = [rw for rw in rows if col in rw]
                if not with_col:
                    continue
                piv = max(with_col, key=lambda rw: abs(rw[col]))
                rows.remove(piv)
                for rw in rows:
                    if col in rw:
                        f = rw[col] / piv[col]
                        for k, v in piv.items():
                            rw[k] = rw.get(k, 0.0) - f * v
                for i, rw in enumerate(rows):
                    big = max([abs(v) for v in rw.values()] or [0.0])
                    rows[i] = {k: v for k, v in rw.items() if abs(v) > 1e-12 * big}
                rows = [rw for rw in rows if rw]
            # a one-DOF row holds that DOF at zero; it drops out of the others
            zero: List[Tuple[int, int]] = []
            while True:
                singles = [next(iter(rw)) for rw in rows if len(rw) == 1]
                if not singles:
                    break
                zero += [k for k in singles if k not in zero]
                rows = [{k: v for k, v in rw.items() if k not in zero} for rw in rows]
                rows = [rw for rw in rows if rw]

            def dof(k: Tuple[int, int]) -> Tuple[int, int]:
                if k[1] <= 3:
                    return k
                c = carrier(k[0])
                return (c[0], c[1] + k[1] - 4)
            bcs = dedup([dof(k) for k in zero])
            mapped: List["OrderedDict[Tuple[int, int], float]"] = []
            for rw in rows:
                terms: "OrderedDict[Tuple[int, int], float]" = OrderedDict()
                for k, v in rw.items():
                    terms[dof(k)] = terms.get(dof(k), 0.0) + v
                big = max([abs(v) for v in terms.values()] or [0.0])
                mapped.append(OrderedDict((k, v) for k, v in terms.items() if abs(v) > 1e-12 * big))
            reduced = any(is_local(k) for terms in mapped for k in terms)
            if reduced:
                mapped = gauss_jordan(mapped)
            eqs: List[List[Tuple[int, int, float]]] = []
            for terms in mapped:
                if len(terms) == 1:
                    bcs += [k for k in terms if k not in bcs]
                elif terms:
                    # eliminated (first) term: a DOF no other constraint takes, node b's
                    # (listed first) unless its coefficient is small
                    free = [k for k in terms if k not in busy and not (k[0] in kin and k[1] >= 4)]
                    if not free:
                        it["route"], it["reason"] = "skip", (
                            "Connector constraint whose DOFs are all eliminated by other "
                            "constraints (rigid-body members, a kinematic coupling's reference "
                            "rotation); commented out — the connector is missing.")
                        break
                    top = max(abs(terms[k]) for k in free)
                    big = [k for k in free if abs(terms[k]) >= 0.1 * top]
                    # a plain node's translation without a BC first (no ccx MPC touches it)
                    first = next(iter(terms)) if reduced else \
                        next((k for k in big if plain(*k) and k not in self._conn_bc_dofs), big[0])
                    eqs.append([(first[0], first[1], terms[first])] +
                               [(k[0], k[1], v) for k, v in terms.items() if k != first])
            if it["route"] != "rows":
                continue
            if any(k in busy for k in bcs):
                it["route"], it["reason"] = "skip", (
                    "Connector that would hold a translation of a rigid-body member at zero "
                    "(ccx eliminates those, a boundary condition on one stops ccx); commented "
                    "out — the connector is missing.")
                continue
            several = [eq for eq in eqs if any(
                sum(1 for m, d, _ in eq if m == n and moved((m, d))) > 1 for n, _, _ in eq)]
            if nl and several:
                it["route"], it["reason"] = "skip", (
                    "Connector under NLGEOM (or explicit dynamics) between nodes with different "
                    "*TRANSFORMs whose constraint keeps several local translations of one node in "
                    "an *EQUATION: ccx 2.23 does not converge on such an equation under NLGEOM, or "
                    "drifts (probed; one local translation per equation is exact); commented out "
                    "— the connector is missing.")
                continue
            if nl:
                def exact(eq: List[Tuple[int, int, float]]) -> bool:
                    if all(plain(n, d) for n, d, _ in eq):
                        return True                   # translations of plain nodes
                    nodes = {n for n, _, _ in eq}
                    # the rotation components of one rotation node (the axis of a revolute
                    # whose other side cannot turn stays put)
                    one = len(nodes) == 1 and all(turning(n, d) for n, d, _ in eq)
                    if explicit:                      # (and no MPC of ccx's own: it stops)
                        return one and nodes <= synth_nodes
                    # translations only, eliminated on a plain node's DOF that no BC takes,
                    # the other terms a reference point's own translations (no MPC eliminates
                    # those): no linear-nonlinear MPC cascade in ccx, exact (probed)
                    tied = plain(*eq[0][:2]) and eq[0][:2] not in self._conn_bc_dofs and all(
                        plain(n, d) or (d <= 3 and n in self._ref_nodes and n not in carriers
                                        and (n, d) not in busy) for n, d, _ in eq[1:])
                    return one or tied
                if not all(exact(eq) for eq in eqs):
                    if self._approx and not explicit:
                        it["approx"] = True
                    else:
                        it["route"], it["reason"] = "skip", (
                            "Connector under NLGEOM (or explicit dynamics) whose constraint is "
                            "exact in ccx only for small rotations: its rotation equations link "
                            "two moving nodes (or a joint offset turns with node a), and ccx "
                            "2.23 also solves *EQUATIONs that link rigid bodies' reference / "
                            "rotation DOFs inaccurately under NLGEOM (probed); commented out — "
                            "rerun with --approximate to write the linear form (not with "
                            "explicit dynamics, which stops on it).")
                        continue
            it["bcs"], it["eqs"] = bcs, eqs
            it["local"] = reduced or any(is_local(k) for k in bcs)

    # -- rigid couplings on shell / beam nodes ---------------------------------
    def _plan_rigid_couplings(self, blocks: List[Block]) -> None:
        """ccx builds *RIGID BODY and *KINEMATIC couplings from RIGID MPCs, which ccx 2.23
        (the FreeCAD 1.1 build) rejects on a shell, membrane, beam or truss node unless ccx
        has made the node a *knot* ('*ERROR in gen3dmpc: nodes belonging to shell elements must not
        be subject to a RIGID MPC'; 2.22 accepted it, current sources warn).  A beam element
        attached to a node makes it a knot, so every such node of a rigid constraint gets a
        *knot beam*: a B31 from the node to a new free end node, in a material without
        density — it carries no load in any procedure, linear or NLGEOM.  The knot also
        gives the node real rotations, which the handlers tie to the body's rotation where
        Abaqus couples them (a rotational DOF of a non-knot shell/beam node does nothing in
        an MPC, so ccx's own coupling leaves those rotations free).  Probed on 2.23: a
        knotted S8R plate edge matches a C3D20R solid with *RIGID BODY to 1e-3 (linear and
        NLGEOM), a knotted beam end the statically equivalent tip load to 1e-4.

        A *KINEMATIC coupling whose reference node is itself a shell/beam node cannot keep
        that form: ccx then carries two unrelated rotations on the node (probed: the beam
        acts as if hinged at the coupled face), so it becomes a *RIGID BODY whose ROT NODE
        follows the reference node's own rotation."""
        quiet = Report()
        self._rot_nodes = set()
        structural = self._shell_nodes | self._beam_nodes      # + membranes (no rotations)
        for typ, conn in self.geom.elements.values():
            cc = ccx_element_type(typ, quiet)
            if cc in SHELL_TYPES or (cc in BEAM_TYPES and not cc.startswith(("T2D", "T3D"))):
                self._rot_nodes.update(conn)
            elif cc.startswith("M3D"):
                structural.update(conn)
        self._coupling_plan = {}
        knots: List[int] = []
        for i, b in enumerate(blocks):
            ref = self._first_node(b.param("REF NODE") or b.param("REFNODE") or "")
            if b.keyword == "RIGID BODY":
                tie, pin = self._rigid_body_members(b)
                if ref is None or not any(n in structural for n in tie + pin + [ref]):
                    continue
                knots += [n for n in [ref] + tie + pin if n in structural]
                if ref in self._rot_nodes:
                    # the reference node's own rotation drives the body (its ROT NODE is tied
                    # to it), so BCs and moments on DOFs 4-6 stay on the node
                    self._rb_rot.pop(ref, None)
            elif b.keyword == "COUPLING":
                nxt = blocks[i + 1] if i + 1 < len(blocks) else None
                if ref is None or nxt is None or nxt.keyword != "KINEMATIC":
                    continue
                members = self._surface_member_nodes(b.param("SURFACE") or "")
                dofs = self._kinematic_dofs(nxt)
                if not dofs & {1, 2, 3} or not any(n in structural for n in members + [ref]):
                    continue
                if ref not in structural:
                    knots += [n for n in members if n in structural]
                    self._coupling_plan[id(b)] = {"kind": "kin", "ref": ref, "members": members,
                                                  "dofs": dofs}
                elif {1, 2, 3} <= dofs and ref in self._rot_nodes:
                    rot = max(self.geom.nodes) + 1
                    self.geom.add_node(rot, self.geom.nodes[ref])
                    knots += [ref] + [n for n in members if n in structural]
                    self._coupling_plan[id(b)] = {"kind": "rb", "ref": ref, "rot": rot, "dofs": dofs,
                                                  "members": [n for n in members if n != ref]}
                else:
                    self._coupling_plan[id(b)] = {"kind": "unsupported"}
            elif b.keyword == "KINEMATIC COUPLING":
                members, translational = [], False
                for r in merged_data_records(b):
                    f = [x for x in r if x != ""]
                    if not f:
                        continue
                    members += self._resolve_nodes(f[0])
                    try:          # member, first DOF, last DOF (no DOFs: all of them)
                        translational = translational or len(f) < 2 or min(
                            pint(f[1]), pint(f[2]) if len(f) > 2 else pint(f[1])) <= 3
                    except ValueError:
                        pass
                if ref is None or not translational or \
                        not any(n in structural for n in members + [ref]):
                    continue
                if ref in structural:
                    self._coupling_plan[id(b)] = {"kind": "unsupported"}
                else:
                    knots += [n for n in members if n in structural]
        # the rigid bodies of *MPC BEAM lines (and rigid connectors), like a *RIGID BODY with
        # TIE members; an *MPC TIE ties the rotations of two shell/beam nodes, which only
        # works between knots.  A body on a kinematic coupling's reference node turns with
        # the coupling: its ROT NODE follows the node's DOFs 4-6, where ccx carries the
        # coupling's rotation (and BCs and moments stay there)
        kin = self._kinematic_refs(blocks)
        for bodies in self._mpc_bodies.values():
            for body in bodies:
                ref, members = body["ref"], body["members"]
                knots += [n for n in [ref] + members if n in structural]
                if ref in self._rot_nodes and any(n in structural for n in [ref] + members):
                    self._rb_rot.pop(ref, None)
                elif ref in kin:
                    self._rb_rot.pop(ref, None)
                    body["follow"] = True
        for mode, arg in self._mpc_plan.values():
            if mode == "tie":
                knots += [n for p in arg if all(x in self._rot_nodes for x in p) for n in p]
        rigid = set(knots)
        # shell/beam nodes whose rotations a connector constrains (see _plan_connectors)
        conn = [n for n in dedup(self._conn_knots) if n not in rigid and n in self._rot_nodes]
        knots = [n for n in dedup(knots + conn) if n in self.geom.nodes]
        if not knots:
            return
        # a heat-transfer-only deck makes thermal knots without rotations ('*ERROR in gen3dmpc:
        # ... a rotational DOF is constrained'), so nothing is tied there
        procs = [b for b in blocks if b.keyword in PROC_KW]
        self._tie_rotations = not procs or any(b.keyword != "HEAT TRANSFER" for b in procs)
        if any(b.keyword == "DYNAMIC" and b.has("EXPLICIT") for b in procs):
            self.report.warn("Rigid coupling on shell/beam nodes in a deck with an explicit dynamic "
                             "step: ccx's explicit solver stops on it ('linear and nonlinear MPC's "
                             "depend on each other', probed on 2.23 with and without the knot "
                             "beams); only the implicit steps can run it.", once=True)
        self._add_knot_beams(knots, blocks)
        if len(knots) > len(conn):
            self.report.note(f"Rigid coupling on shell/beam nodes: ccx builds *KINEMATIC / *RIGID "
                             f"BODY from RIGID MPCs, which ccx 2.23 (FreeCAD 1.1 build) rejects on a "
                             f"shell/beam node unless ccx made it a knot ('*ERROR in gen3dmpc: ... "
                             f"RIGID MPC'). Each of the {len(knots) - len(conn)} such node(s) got a "
                             f"force-free knot beam (a B31 to a new free node, elset/material "
                             f"{KNOT_SET}, no density), which makes it a knot; the rotations Abaqus "
                             f"couples are tied to the reference rotation with *EQUATION.")
        if conn:
            self.report.note(f"Connectors on shell/beam nodes: ccx ignores DOFs 4-6 of a plain "
                             f"shell/beam node in an *EQUATION, so the {len(conn)} node(s) whose "
                             f"rotations a connector constrains got force-free knot beams too "
                             f"(elset/material {KNOT_SET}), which give them real rotations.")

    def _add_knot_beams(self, nodes: Sequence[int], blocks: List[Block]) -> None:
        """Give each of ``nodes`` a force-free *knot beam*: a B31 from the node to a new free
        end node, in elset/material KNOT_SET without density, so it carries no load in any
        procedure.  ccx makes a node that two different beam expansions share a knot — a
        rigid section whose rotations are true DOFs (rotational BCs, moments and MPC terms
        act on its rotation node).  The first call fixes the beams' length, size, modulus
        and (thermal decks) conductivity; nodes that already have one are skipped."""
        nodes = [n for n in dedup(nodes) if n in self.geom.nodes and n not in self._knots]
        if not nodes:
            return
        if not self._knots:
            # the knot beam carries no load, so its geometry and stiffness only need to be
            # harmless: short (1 % of the model size), a modulus of the deck's order (keeps
            # the matrix well scaled), all along one oblique direction (one section card)
            lo = [min(x[k] for x in self.geom.nodes.values()) for k in range(3)]
            hi = [max(x[k] for x in self.geom.nodes.values()) for k in range(3)]
            span = vnorm(vsub((hi[0], hi[1], hi[2]), (lo[0], lo[1], lo[2])))
            self._knot_ell = 0.01 * span if span > 0 else 1.0
            self._knot_a = float(f"{self._knot_ell / 2:.4g}")
            moduli = []
            for b in blocks:
                if b.keyword == "ELASTIC":
                    recs = [[x for x in r if x != ""] for r in merged_data_records(b)]
                    try:
                        moduli.append(pf(recs[0][0]))
                    except (IndexError, ValueError):
                        pass
            self._knot_e = max([m for m in moduli if m > 0] or [1.0])
            # a thermal step needs a conductivity on every element (ccx stops without one)
            if any(b.keyword in ("HEAT TRANSFER", "COUPLED TEMPERATURE-DISPLACEMENT",
                                 "UNCOUPLED TEMPERATURE-DISPLACEMENT") for b in blocks):
                ks = []
                for b in blocks:
                    if b.keyword == "CONDUCTIVITY":
                        recs = [[x for x in r if x != ""] for r in merged_data_records(b)]
                        try:
                            ks.append(pf(recs[0][0]))
                        except (IndexError, ValueError):
                            pass
                self._knot_k = max([k for k in ks if k > 0] or [1.0])
        d = vunit((1.0, 1.0, 1.0))
        nid = max(self.geom.nodes)
        eid = max(list(self.geom.elements) + list(self._carriers) + list(self._conn), default=0)
        elems = []
        for n in nodes:
            nid += 1
            eid += 1
            self.geom.add_node(nid, vadd(self.geom.nodes[n], vscale(d, self._knot_ell)))
            self.geom.add_element(eid, "B31", [n, nid])
            self._knots[n] = nid
            elems.append(eid)
        self.geom.add_to_elset(KNOT_SET, elems)

    def _knot_section(self) -> List[str]:
        if not self._knots:
            return []
        a = fmt_num(self._knot_a)
        thermal = [] if self._knot_k is None else \
            ["*CONDUCTIVITY", fmt_num(self._knot_k), "*SPECIFIC HEAT", "0."]
        return [f"*MATERIAL, NAME={KNOT_SET}", "*ELASTIC", f"{fmt_num(self._knot_e)}, 0.",
                "*DENSITY", "0."] + thermal + [
                f"*BEAM SECTION, ELSET={KNOT_SET}, MATERIAL={KNOT_SET}, SECTION=RECT",
                f"{a}, {a}", "1., -1., 0."]

    def _rotation_ties(self, members: Sequence[int], target: int, offset: int,
                       dofs: Sequence[int] = (4, 5, 6)) -> List[str]:
        """*EQUATION ties rotation(member) = DOF ``k + offset`` of ``target`` for the knotted
        members that have rotations — on a ROT NODE that has its reference node's local axes
        (_rot_axes), the member's global rotation written in them (probed on 2.23: a shell
        edge tied to such a body matches the transform-free model exactly, also under
        NLGEOM; plain ties miss by 0.5 % of max |u|).  A member DOF under a *BOUNDARY cannot
        be the tie's dependent term (ccx stops on a DOF that is both SPC'd and dependent in
        an MPC): _settle_dependents then makes the body's DOF dependent instead, or drops the
        tie when that one is taken too (self._gen_ties marks the ties it may drop)."""
        out: List[str] = []
        if not self._tie_rotations:
            return out
        for n in dedup(members):
            if n not in self._knots or n not in self._rot_nodes or n == target:
                continue
            if n in self._transformed or target in self._transformed:
                self.report.warn("Coupled rotation not tied on a node with a *TRANSFORM (its "
                                 "*EQUATION DOFs are local, the body rotation global) — the "
                                 "rotation stays free there.", once=True)
                continue
            for k in dofs:
                if k < 4 or k > 6:
                    continue
                if (n, k) in self._rot_tied:
                    self.report.warn("A shell/beam node belongs to two rigid constraints; its "
                                     "rotation is tied to the first one only — verify.", once=True)
                    continue
                self._rot_tied.add((n, k))
                axes = self._rot_axes.get(target) if offset == -3 else None
                if axes:
                    # a ROT NODE with its reference node's local axes (_plan_rot_axes):
                    # ccx reads its *EQUATION terms in them, so the member's global rotation k
                    # is the sum over j of e_j[k] times its local rotation j (exact, linear)
                    terms = [(j + 1, -e[k - 4]) for j, e in enumerate(axes + (vcross(*axes),))
                             if abs(e[k - 4]) > 1e-12]
                    self._gen_ties.add(frozenset([(n, k)] + [(target, j) for j, _ in terms]))
                    out += ["*EQUATION", str(1 + len(terms)), ", ".join(
                        [f"{n}, {k}, 1."] + [f"{target}, {j}, {_fmt_unit(c)}" for j, c in terms])]
                    continue
                self._gen_ties.add(frozenset(((n, k), (target, k + offset))))
                out += ["*EQUATION", "2", f"{n}, {k}, 1., {target}, {k + offset}, -1."]
        return out

    def _rot_node_follows(self, rot: int, ref: int) -> List[str]:
        """*EQUATION ties ROT NODE DOFs 1-3 = rotations of the (knotted) shell/beam reference
        node, ROT NODE dependent: BCs and moments then act on the node's own rotations."""
        if not self._tie_rotations:
            return []
        if ref in self._transformed:
            self.report.warn("Coupled rotation not tied on a node with a *TRANSFORM (its "
                             "*EQUATION DOFs are local, the body rotation global) — the "
                             "rotation stays free there.", once=True)
            return []
        return [x for k in (1, 2, 3) for x in ("*EQUATION", "2", f"{rot}, {k}, 1., {ref}, {k + 3}, -1.")]

    def _boundary_dofs(self, blocks: List[Block]) -> set:
        """(node, dof) pairs a *BOUNDARY constrains in any step."""
        return {(n, d) for b in blocks if b.keyword == "BOUNDARY"
                for nodes, dofs, _ in self._bc_records(b) for n in nodes for d in dofs}

    def _bc_records(self, b: Block, rot: Optional[bool] = None) -> List[Tuple[List[int], List[int], float]]:
        """(nodes, DOFs, magnitude) per data line of a *BOUNDARY card, as handle_boundary
        emits it: a named type (ENCASTRE, XSYMM, ...) has magnitude 0 and includes the
        rotations where handle_boundary does (``rot`` overrides that), an unreadable
        magnitude is NaN (equal to nothing)."""
        out = []
        for rec in merged_data_records(b):
            g = [x.strip() for x in rec]
            while g and g[-1] == "":
                g.pop()
            if len(g) < 2 or not g[0]:
                continue
            if re.fullmatch(r"[-+]?\d+", g[1]):
                d1 = int(g[1])
                d2 = int(g[2]) if len(g) > 2 and re.fullmatch(r"[-+]?\d+", g[2]) else d1
                dofs = list(range(min(d1, d2), max(d1, d2) + 1))
                try:
                    mag = pf(g[3]) if len(g) > 3 and g[3] else 0.0
                except ValueError:
                    mag = float("nan")
            else:
                named = self._named_bc_dofs(g[1], self._named_bc_rot(g[0]) if rot is None else rot)
                dofs = [d for a, c in (named or []) for d in range(a, c + 1)]
                mag = 0.0
            out.append((self._resolve_nodes(g[0]), dofs, mag))
        return out

    def _rigid_members(self, blocks: List[Block]):
        """(reference node, members, coupled translations) of every rigid constraint ccx
        builds from RIGID MPCs: *RIGID BODY, kinematic couplings and the rigid bodies of
        *MPC BEAM lines.  ccx eliminates the members' coupled translations."""
        for i, b in enumerate(blocks):
            ref = self._first_node(b.param("REF NODE") or b.param("REFNODE") or "")
            if ref is None:
                continue
            if b.keyword == "RIGID BODY":
                tie, pin = self._rigid_body_members(b)
                yield ref, [n for n in tie + pin if n != ref], {1, 2, 3}
            elif b.keyword == "COUPLING" and i + 1 < len(blocks) and \
                    blocks[i + 1].keyword == "KINEMATIC":
                members = self._surface_member_nodes(b.param("SURFACE") or "")
                yield ref, [n for n in members if n != ref], \
                    self._kinematic_dofs(blocks[i + 1]) & {1, 2, 3}
            elif b.keyword == "KINEMATIC COUPLING":
                for r in merged_data_records(b):
                    f = [x for x in r if x != ""]
                    try:
                        d1 = pint(f[1]) if len(f) > 1 else 1
                        d2 = pint(f[2]) if len(f) > 2 else (d1 if len(f) > 1 else 3)
                    except (IndexError, ValueError):
                        continue
                    yield ref, [n for n in self._resolve_nodes(f[0]) if n != ref], \
                        set(range(min(d1, d2), max(d1, d2) + 1)) & {1, 2, 3}
        for bodies in self._mpc_bodies.values():
            for body in bodies:
                yield body["ref"], body["members"], {1, 2, 3}

    # -- *BOUNDARY on rigid-coupling members ------------------------------------
    def _plan_coupled_bcs(self, blocks: List[Block]) -> None:
        """ccx makes the coupled DOFs of a rigid coupling's members (and the rotations the
        converter ties) the dependent side of MPCs, and stops on one that also has a
        *BOUNDARY ('*ERROR in cascade: ... dependent side of a MPC and a SPC') — an
        overconstraint Abaqus resolves.  Where the reference node's own BCs impose the
        member's BC anyway (the same value on that DOF, and no rotation about the other two
        axes during the step; 2-D: about z) the BC is redundant and is taken off the card:
        exact, under NLGEOM too, since a rotation about the DOF's own axis leaves that
        displacement component alone (probed on 2.23: the dropped BCs hold to 1e-20).  So is
        a BC on DOF 3 of a plane/axisymmetric node (Abaqus has none there; ccx's 2-D rigid
        body makes it dependent).  An imposed BC on a tied rotation stays, and
        _settle_dependents drops the tie (the BC governs it).  A *RIGID BODY's other member
        BCs go where Abaqus/Standard puts them, onto the reference node
        (_plan_rigid_body_move).  The rest is warned (_warn_coupled_clashes), or with
        --approximate dropped where Abaqus drops it: a kinematic coupling and an MPC eliminate
        the constrained DOFs of their nodes, so Abaqus/Standard does not apply a BC there.
        Rigid constraints: *RIGID BODY, kinematic couplings and the rigid bodies of *MPC BEAM
        lines (_plan_mpcs)."""
        cons = self._rigid_constraints(blocks)
        if not cons:
            return
        relevant = {n for c in cons for n in list(c["trans"]) + list(c["rots"]) + [c["ref"], c["rot"]]}
        states, cards = self._bc_states(blocks, relevant)
        for c in cons:
            self._coupled_steps(c, states)
        # (node, dof) -> its BC is implied in every step one governs it; and its constraint
        verdict: "OrderedDict[Tuple[int, int], bool]" = OrderedDict()
        owner: Dict[Tuple[int, int], dict] = {}
        for c in cons:
            for m, ds in list(c["trans"].items()) + list(c["rots"].items()):
                for d in sorted(ds):
                    steps = [s for s, st in enumerate(states) if (m, d) in st]
                    if steps:                   # a BC no step keeps in force cannot clash
                        ok = all(self._bc_implied(c, m, d, s) for s in steps)
                        verdict[(m, d)] = verdict.get((m, d), True) and ok
                        owner.setdefault((m, d), c)
        moved: set = set()
        for c in cons:
            if c["kind"] == "rb":
                moved |= self._plan_rigid_body_move(c, cards, verdict, owner)
        implied, planar3, approx = [], 0, []
        for (m, d), ok in verdict.items():
            if (m, d) in moved:
                continue
            c = owner[(m, d)]
            loose = not ok and self._approx and c["kind"] != "rb"
            if not ok and not loose:
                # a *RIGID BODY's tied rotation that _plan_rigid_body_move left: _settle_dependents
                # reorders the tie so the body follows the member's BC, as Abaqus moves it to
                # the reference node — warned where the BCs differ or contradict its own
                why = c.get("why", {}).get(d, "")
                if not (d > 3 and c["kind"] == "rb" and not why):
                    self._coupled_clash.append((c["kind"], c["emit"], m, d, c["ref"], why))
                    self._clash_dofs.add((m, d))
                continue
            if ok and d > 3:
                continue        # kept; _settle_dependents drops the tie (the BC governs it)
            # off every card that names it, so no overridden value stays behind either
            for card in cards[(m, d)]:
                self._bc_drop.setdefault(card, set()).add((m, d))
            if loose:
                approx.append((m, d))
            elif d == 3 and c["planar"]:
                planar3 += 1
            else:
                implied.append((m, d))
        for b in blocks:
            if b.keyword == "BOUNDARY" and id(b) in self._bc_drop:
                self._bc_lines[id(b)] = self._bc_lines_without(b, self._bc_drop[id(b)],
                                                               self._bc_add.get(id(b)))
        self._note_rigid_body_moves()
        if implied or planar3:
            eg = f" (e.g. node {implied[0][0]} DOF {implied[0][1]})" if implied else ""
            self.report.note(f"*BOUNDARY taken off {len(implied) + planar3} DOF(s) that a rigid "
                             f"constraint (*RIGID BODY, kinematic coupling, *MPC BEAM) makes follow "
                             f"its reference node"
                             f"{eg}: ccx stops on a DOF that is both SPC'd and dependent in an MPC "
                             f"('*ERROR in cascade ... dependent side of a MPC and a SPC'), and the "
                             f"reference node's own BCs impose these anyway — the same value on the "
                             f"DOF and no rotation about the other two axes"
                             + (" (and DOF 3 of 2-D nodes, which has no meaning there)"
                                if planar3 else "") + ". Exact.", once=True)
        if approx:
            nodes = {m for m, _ in approx}
            self.report.warn(f"[APPROX] *BOUNDARY taken off {len(approx)} DOF(s) of {len(nodes)} "
                             f"node(s) that a kinematic coupling or *MPC also constrains (e.g. node "
                             f"{approx[0][0]} DOF {approx[0][1]}), although the reference node's "
                             f"BCs do not impose them: the nodes follow the constraint, as in "
                             f"Abaqus/Standard, which eliminates the constrained DOFs at those "
                             f"nodes and does not apply a BC there (it warns that the BC 'may not "
                             f"be applied'). Check the model: the BC region probably overlaps the "
                             f"constraint by mistake.", once=True)

    def _rigid_constraints(self, blocks: List[Block]) -> List[dict]:
        """The rigid constraints as the converter emits them: per constraint its Abaqus kind
        ('rb' = *RIGID BODY, 'kin' = a kinematic coupling, 'mpc' = the rigid body of *MPC BEAM
        lines), how ccx gets it ('emit': 'rb' = a *RIGID BODY, 'kin' = a *KINEMATIC
        coupling), reference node, explicit ROT NODE (a ccx-style deck), whether all members
        are 2-D nodes, and per member the translations ccx makes dependent ('trans') and the
        rotations the converter ties ('rots')."""
        out: List[dict] = []
        for i, b in enumerate(blocks):
            if b.keyword not in ("RIGID BODY", "COUPLING", "KINEMATIC COUPLING"):
                continue
            ref = self._first_node(b.param("REF NODE") or b.param("REFNODE") or "")
            if ref is None:
                continue
            rot = None
            lines: List[Tuple[List[int], set]] = []      # (nodes, coupled Abaqus DOFs)
            if b.keyword == "RIGID BODY":
                kind, tied, rb = "rb", True, True
                rot = self._first_node(b.param("ROT NODE") or b.param("ROTNODE") or "")
                tie, pin = self._rigid_body_members(b)
                lines = [(tie, set(range(1, 7))), (pin, {1, 2, 3})]
            elif b.keyword == "COUPLING":
                nxt = blocks[i + 1] if i + 1 < len(blocks) else None
                if nxt is None or nxt.keyword != "KINEMATIC":
                    continue
                plan = (self._coupling_plan.get(id(b)) or {}).get("kind")
                kind, tied, rb = "kin", plan in ("kin", "rb"), plan == "rb"   # rb: a *RIGID BODY
                lines = [(self._surface_member_nodes(b.param("SURFACE") or ""),
                          self._kinematic_dofs(nxt))]
            else:
                kind, rb = "kin", False
                for r in merged_data_records(b):
                    f = [x for x in r if x != ""]
                    if not f:
                        continue
                    try:          # member, first DOF, last DOF (no DOFs: all of them)
                        d1 = pint(f[1]) if len(f) > 1 else 1
                        d2 = pint(f[2]) if len(f) > 2 else (d1 if len(f) > 1 else 6)
                    except ValueError:
                        continue
                    lines.append((self._resolve_nodes(f[0]), set(range(min(d1, d2), max(d1, d2) + 1))))
                tied = any(ds & {1, 2, 3} for _, ds in lines)
            members = {n for ns, _ in lines for n in ns} - {ref, rot}
            if not members:
                continue
            planar = all(n in self._plane_only for n in members)
            if planar and kind == "kin":
                self._planar_kin.add(id(b))
            top = 2 if planar and not rb else 3
            tie_ok = tied and self._tie_rotations and ref not in self._transformed and \
                rot not in self._transformed
            trans: Dict[int, set] = {}
            rots: Dict[int, set] = {}
            for ns, ds in lines:
                for n in ns:
                    if n not in members:
                        continue
                    trans.setdefault(n, set()).update({1, 2, 3} if rb else
                                                      {d for d in ds if d <= top})
                    if tie_ok and n in self._knots and n in self._rot_nodes and \
                            n not in self._transformed:
                        rots.setdefault(n, set()).update(ds & {4, 5, 6})
            out.append(dict(kind=kind, emit="rb" if rb else "kin", ref=ref, rot=rot,
                            planar=planar, trans=trans, rots=rots))
        # the rigid bodies of *MPC BEAM lines, emitted as *RIGID BODY with a ROT NODE: the
        # dependent nodes follow the independent one in displacement and rotation
        for bodies in self._mpc_bodies.values():
            for body in bodies:
                ref = body["ref"]
                members = set(body["members"]) - {ref, body["rot"]}
                if not members:
                    continue
                tie_ok = self._tie_rotations and ref not in self._transformed
                out.append(dict(kind="mpc", emit="rb", ref=ref, rot=None,
                                planar=all(n in self._plane_only for n in members),
                                trans={n: {1, 2, 3} for n in members},
                                rots={n: {4, 5, 6} for n in members
                                      if tie_ok and n in self._knots and n in self._rot_nodes
                                      and n not in self._transformed}))
        return out

    def _bc_states(self, blocks: List[Block], nodes: set):
        """The *BOUNDARY in force on ``nodes`` in each step, as ccx applies them: model data
        first, OP=NEW on a step's first *BOUNDARY removing the earlier ones.  (node, dof) ->
        (id of the card, magnitude, amplitude, kind): kind "disp" for a displacement, "rate"
        for a velocity, None for what cannot be compared (FIXED, USER, accelerations).  A
        deck without steps: its model-data state.  Also (node, dof) -> ids of every card that
        names it, in force or overridden.  (bc_steps is the zero / nonzero view of the emitted
        deck that _settle_dependents uses; this one keeps the values, amplitudes and cards the
        implied-BC test needs.)"""
        states: List[Dict[Tuple[int, int], tuple]] = []
        cards: Dict[Tuple[int, int], List[int]] = {}
        cur: Dict[Tuple[int, int], tuple] = {}
        in_step = first = False
        for b in blocks:
            if b.keyword == "STEP":
                in_step = first = True
            elif b.keyword == "END STEP" and in_step:
                states.append(dict(cur))
                in_step = False
            elif b.keyword == "BOUNDARY":
                if in_step and first and (b.param("OP") or "").strip().upper() == "NEW":
                    cur = {}
                first = False
                typ = (b.param("TYPE") or "DISPLACEMENT").strip().upper()
                fixed = b.has("FIXED") or b.has("USER")
                amp = (b.param("AMPLITUDE") or "").strip().upper()
                for ns, dofs, mag in self._bc_records(b):
                    kind = None if fixed else "disp" if typ == "DISPLACEMENT" else \
                        "rate" if typ == "VELOCITY" else None
                    for n in ns:
                        if n in nodes:
                            for d in dofs:
                                cur[(n, d)] = (id(b), mag, amp, kind)
                                if id(b) not in cards.setdefault((n, d), []):
                                    cards[(n, d)].append(id(b))
        if in_step:
            states.append(dict(cur))
        return states or [cur], cards

    def _coupled_steps(self, c: dict, states) -> None:
        """Per step of rigid constraint ``c`` (c["steps"]): its BC state ('st'), the reference
        node's own BC on each DOF 1-6 ('ref'), the members under a BC per coupled DOF ('S'),
        and which reference DOFs are provably zero when the step starts ('z0').  Everything
        starts at zero; a DOF ends a step at zero under a zero displacement, under a zero
        velocity when it started at zero, and — on a *RIGID BODY, whose member BCs Abaqus
        keeps (on the reference node) — the body's u_d and its rotations about the other axes
        where identical member BCs on DOF d hold them (_move_geometry_ok) from an unturned
        start.  c["axes"]: the body's rotation axes (2-D: z only)."""
        axes = (3,) if c["planar"] else (1, 2, 3)
        on: "OrderedDict[int, List[int]]" = OrderedDict()
        for m, ds in list(c["trans"].items()) + list(c["rots"].items()):
            for d in sorted(ds):
                on.setdefault(d, []).append(m)
        c["axes"], c["steps"] = axes, []
        z0 = {k: True for k in range(1, 7)}
        for s, st in enumerate(states):
            ref = {k: self._ref_bc(c, st, k) for k in range(1, 7)}
            members = OrderedDict((d, [m for m in ms if (m, d) in st]) for d, ms in on.items())
            c["steps"].append(dict(st=st, ref=ref, S={d: ms for d, ms in members.items() if ms},
                                   z0=dict(z0)))
            end = {k: bool(ref[k]) and ref[k][1] == 0.0 and
                   (ref[k][3] == "disp" or (ref[k][3] == "rate" and z0[k])) for k in range(1, 7)}
            held = []                              # DOFs whose identical member BCs act together
            for d in ((1, 2) if c["planar"] else (1, 2, 3)) if c["kind"] == "rb" else ():
                es = [st[(m, d)] for m in members.get(d, ())]
                if es and all(self._same_bc(e, es[0], False) for e in es):
                    held.append(d)
            rot = {j for d in held for j in axes if j != d}
            if held and all(z0[3 + j] for j in rot) and self._move_geometry_ok(c, s, held):
                for j in rot:
                    end[3 + j] = True
                for d in held:
                    e = st[(members[d][0], d)]
                    end[d] = end[d] or (e[1] == 0.0 and (e[3] == "disp" or z0[d]))
            z0 = end

    def _bc_segments(self, blocks: List[Block]) -> List[List[Tuple[bool, Tuple[int, int], bool]]]:
        """The source deck's *BOUNDARY entries for bc_steps: (OP=NEW, (node, DOF), zero value)
        of the model data and of each step.  A named BC counts its rotations too (it fixes
        them wherever the node has rotations, also ones a connector gives it)."""
        segs: List[List[Tuple[bool, Tuple[int, int], bool]]] = [[]]
        for b in blocks:
            if b.keyword == "STEP":
                segs.append([])
            elif b.keyword == "BOUNDARY":
                new = (b.param("OP") or "").strip().upper() == "NEW"
                typed = (b.param("TYPE") or "DISPLACEMENT").strip().upper() != "DISPLACEMENT" or \
                    b.has("FIXED") or b.has("USER")
                for ns, dofs, mag in self._bc_records(b, True):
                    segs[-1] += [(new, (n, d), not typed and mag == 0.0) for n in ns for d in dofs]
        return segs

    def _bc_implied(self, c: dict, m: int, d: int, s: int) -> bool:
        """Do the reference node's own BCs in step ``s`` impose the BC member ``m`` has on DOF
        ``d`` there?  A translation follows the reference node's when the rotations about the
        other two axes stay zero (rigid motion: u_d = u_ref,d + (θ × r)_d, and a finite
        rotation about axis d leaves component d alone): zero when the step starts, and held
        by the reference node (_rot_held).  A tied rotation equals the reference rotation.
        Both then start the step equal, so the same target (_same_bc) keeps them equal."""
        step = c["steps"][s]
        e = step["st"][(m, d)]
        if not e[3]:
            return False
        if d == 3 and c["planar"]:
            return True                  # no DOF 3 on a 2-D node in Abaqus; ccx's is held anyway
        if m in self._transformed or c["ref"] in self._transformed:
            return False                 # local DOFs
        r = step["ref"][d]
        if r is None or not self._same_bc(e, r, step["z0"][d]):
            return False
        return d > 3 or all(self._rot_held(c, s, j) for j in c["axes"] if j != d)

    @staticmethod
    def _rot_held(c: dict, s: int, j: int) -> bool:
        """Do the reference node's own BCs keep the body's rotation about axis ``j`` at zero
        all through step ``s`` — zero at its start, held by a zero displacement or velocity?"""
        step = c["steps"][s]
        r = step["ref"][3 + j]
        return step["z0"][3 + j] and r is not None and r[3] in ("disp", "rate") and r[1] == 0.0

    @staticmethod
    def _same_bc(e: tuple, r: tuple, zero_start: bool) -> bool:
        """Do BC entries ``e`` and ``r`` (from _bc_states) drive two DOFs that start the step
        equal the same way?  The same kind (displacement or velocity) with the same value and
        amplitude, or zero both; a zero velocity and a zero displacement when the DOF starts
        at zero (``zero_start``)."""
        if not e[3] or not r[3]:
            return False
        if e[3] == r[3]:
            return (e[1] == 0.0 and r[1] == 0.0) or \
                (r[2] == e[2] and abs(r[1] - e[1]) <= 1e-12 * max(abs(r[1]), abs(e[1])))
        return e[1] == 0.0 and r[1] == 0.0 and zero_start

    def _move_geometry_ok(self, c: dict, s: int, ds: Sequence[int]) -> bool:
        """Do the members' BCs on translations ``ds`` of *RIGID BODY ``c`` in step ``s`` hold
        what moving them to the reference node holds — its u_d (d in ds) and its rotations
        about the other axes (each d: the two axes other than d; 2-D: z)?  In the body's rigid
        motion u_m = u_ref + θ × r_m a member BC is the row [e_d, r_m × e_d]·(u_ref, θ) (2-D:
        u_m,1 = u_ref,1 − θ_z r_y, u_m,2 = u_ref,2 + θ_z r_x), and a BC on a tied shell/beam
        rotation is the row of that body rotation; with the reference node's own BCs these
        rows must span every moved row.  Then the BCs fix the same DOFs, and under NLGEOM
        too where the moved model holds every rotation at zero (2-D; two or more DOFs moved;
        the remaining one held): the constraint rank is that of the unturned body all along.
        With one DOF d moved and the body free to turn about e_d, the members' translation
        rows alone must hold both other rotations — their projections on the plane normal to
        e_d not collinear —, which a turn about e_d leaves as it is."""
        x0 = self.geom.nodes.get(c["ref"])
        if x0 is None:
            return False
        step, axes, planar = c["steps"][s], c["axes"], c["planar"]
        rot = sorted({j for d in ds for j in axes if j != d})
        size = self._model_span()
        width = 3 if planar else 6
        col = {1: 0, 2: 1, 6: 2} if planar else {k: k - 1 for k in range(1, 7)}

        def unit(k):
            v = [0.0] * width
            v[col[k]] = 1.0
            return v
        spun: List[int] = []             # tied rotations under identical member BCs
        zero: set = set()                # ... those holding the body at zero all through the step
        for j in axes:
            es = [step["st"][(m, 3 + j)] for m in step["S"].get(3 + j, ())]
            if es and all(self._same_bc(e, es[0], False) for e in es):
                spun.append(3 + j)
                if es[0][1] == 0.0 and step["z0"][3 + j]:
                    zero.add(j)
        free = [j for j in axes if j not in rot and j not in zero and not self._rot_held(c, s, j)]
        rows: List[List[float]] = []
        for d in ds:
            for m in step["S"][d]:
                p = self.geom.nodes.get(m)
                if p is None:
                    return False
                r = [(p[k] - x0[k]) / size for k in range(3)]
                if planar:
                    rows.append([1.0, 0.0, -r[1]] if d == 1 else [0.0, 1.0, r[0]])
                else:
                    e = [0.0, 0.0, 0.0]
                    e[d - 1] = 1.0
                    rows.append(e + [r[1] * e[2] - r[2] * e[1], r[2] * e[0] - r[0] * e[2],
                                     r[0] * e[1] - r[1] * e[0]])
        if free:                         # one DOF moved, the body free to turn about it
            return self._spans(rows, [unit(3 + j) for j in rot])
        rows += [unit(k) for k in spun] + [unit(k) for k in col if step["ref"][k] is not None]
        return self._spans(rows, [unit(d) for d in ds] + [unit(3 + j) for j in rot])

    @staticmethod
    def _spans(rows: List[List[float]], targets: List[List[float]], tol: float = 1e-6) -> bool:
        """Is every vector of ``targets`` in the span of ``rows`` (to a relative ``tol``, so a
        nearly degenerate set counts as degenerate)?  Gram-Schmidt on the rows."""
        basis: List[List[float]] = []
        width = len(targets[0]) if targets else 0
        for v in rows:
            if len(basis) == width:
                break
            norm = math.sqrt(sum(x * x for x in v))
            w = list(v)
            for _ in range(2):                    # twice: keeps the basis orthogonal
                for b in basis:
                    p = sum(x * y for x, y in zip(w, b))
                    w = [x - p * y for x, y in zip(w, b)]
            n = math.sqrt(sum(x * x for x in w))
            if n > tol * max(norm, 1.0):
                basis.append([x / n for x in w])
        for v in targets:
            w = list(v)
            for _ in range(2):
                for b in basis:
                    p = sum(x * y for x, y in zip(w, b))
                    w = [x - p * y for x, y in zip(w, b)]
            if math.sqrt(sum(x * x for x in w)) > tol:
                return False
        return True

    def _model_span(self) -> float:
        if self._span is None:
            xs = list(self.geom.nodes.values())
            self._span = math.sqrt(sum((max(p[k] for p in xs) - min(p[k] for p in xs)) ** 2
                                       for k in range(3))) if xs else 0.0
            self._span = self._span or 1.0
        return self._span

    def _plan_rigid_body_move(self, c: dict, cards, verdict, owner) -> set:
        """Abaqus/Standard moves the BCs on a *RIGID BODY's nodes to its reference node when
        they are identical (else it stops with an error) and agree with the reference node's
        own BCs, which it keeps, and adds zero rotations about the other axes to make up for
        the removed displacement constraints (Analysis User's Guide, 'Overconstraint
        checks').  That is the same constraint as the BCs themselves where the nodes BC'd on
        DOF d (one value, one amplitude) hold the body's u_d and its rotations about the other
        two axes (_move_geometry_ok), and the body has not turned about those axes when the step
        starts — else the values ramp from a turned position, which a rigid body cannot
        follow under NLGEOM.  A BC on a tied shell/beam rotation is a BC on the body's
        rotation itself.  So the move is made by default only where exact, elsewhere only with
        --approximate.  Decided per DOF over every step; the moved BCs go into the cards that
        held the members' BCs, so step, OP, amplitude and type stay (_bc_lines_without), and
        the rotations of a *RIGID BODY reference node reach its ROT NODE through
        _active_dof_lines.  Returns the (node, DOF) pairs it took over; c["why"][dof] says
        why the others stay."""
        groups: "OrderedDict[int, List[int]]" = OrderedDict()
        for m, ds in list(c["trans"].items()) + list(c["rots"].items()):
            for d in sorted(ds):
                if owner.get((m, d)) is c:     # a BC some step keeps in force (_plan_coupled_bcs)
                    groups.setdefault(d, []).append(m)
        todo = [d for d, ms in groups.items() if not all(verdict[(m, d)] for m in ms)]
        why = c.setdefault("why", {})
        res: Dict[int, list] = {d: [] for d in todo}     # dof -> [(step, outcome, reasons, lines)]
        for s, step in enumerate(c["steps"]):
            outs = {d: self._rb_step_outcome(c, d, s) for d in todo if d in step["S"]}
            moving = [d for d, o in outs.items() if d <= 3 and o[0] in ("move", "approx")]
            if moving and not self._move_geometry_ok(c, s, moving):
                for d in moving:
                    outs[d] = ("approx", outs[d][1] | {"geometry"}, outs[d][2])
            asked: Dict[int, set] = {}                      # reference DOF -> values asked for
            for d, (state, _, need) in outs.items():
                for k, v in need.items():
                    asked.setdefault(k, set()).add(v)
            for d, out in outs.items():
                # a rotation BC on tied shell/beam rotations vs the zero rotation a moved
                # translation needs: Abaqus finds them inconsistent too
                if any(len(asked[k]) > 1 for k in out[2]):
                    out = ("conflict", set(), {})
                res[d].append((s,) + out)
        taken: set = set()
        for d in todo:
            bad = [o[1] for o in res[d] if o[1] in ("differ", "conflict", "kind")]
            inexact = set().union(*[o[2] for o in res[d]])
            if bad or not any(o[1] in ("move", "approx") for o in res[d]):
                why[d] = min(bad, key=("differ", "conflict", "kind").index) if bad else ""
                continue
            if inexact and not self._approx:
                why[d] = "approx:" + ",".join(sorted(inexact))
                continue
            for s, state, _, need in res[d]:
                step = c["steps"][s]
                for m in step["S"][d] if need else ():
                    lines = self._bc_add.setdefault(step["st"][(m, d)][0], OrderedDict()) \
                        .setdefault(c["ref"], {})
                    lines.update(need)
            for m in groups[d]:
                # off every card that names it, so no overridden value stays behind either
                for card in cards[(m, d)]:
                    self._bc_drop.setdefault(card, set()).add((m, d))
                taken.add((m, d))
                if not verdict[(m, d)]:
                    self._rb_moved.append((m, d, c["ref"], frozenset(inexact)))
        return taken

    def _rb_step_outcome(self, c: dict, d: int, s: int) -> Tuple[str, set, Dict[int, float]]:
        """How Abaqus resolves the BCs on DOF ``d`` of a *RIGID BODY's nodes in step ``s``:
        ('implied', ...) when the reference node's own BCs impose them; 'differ' (not
        identical), 'conflict' (against the reference node's own BCs) or 'kind' (FIXED,
        USER, an acceleration, local DOFs) when they cannot be moved; else 'move' or
        'approx' (the reasons it is not the same constraint: 'history', 'overlap'; the
        caller adds 'geometry') with the lines the reference node needs: {DOF: value} — the
        BC itself unless the reference node has its own, zero rotations about the other axes
        unless it holds them already."""
        step = c["steps"][s]
        ms = step["S"][d]
        if all(self._bc_implied(c, m, d, s) for m in ms):
            return "implied", set(), {}
        es = [step["st"][(m, d)] for m in ms]
        if not all(e[3] for e in es) or c["ref"] in self._transformed or \
                any(m in self._transformed for m in ms):
            return "kind", set(), {}
        if not all(self._same_bc(e, es[0], False) for e in es):
            return "differ", set(), {}
        e, r = es[0], step["ref"][d]
        need: Dict[int, float] = {}
        inexact: set = set()
        if r is None:
            need[d] = e[1]
        elif not self._same_bc(e, r, step["z0"][d]):
            if not (r[3] and e[1] == 0.0 and r[1] == 0.0):
                return "conflict", set(), {}
            inexact.add("overlap")       # a zero velocity against a zero displacement
        if d <= 3:
            for j in c["axes"]:
                if j == d:
                    continue
                rr = step["ref"][3 + j]
                if rr is None:
                    need[3 + j] = 0.0
                elif not (rr[3] in ("disp", "rate") and rr[1] == 0.0):
                    return "conflict", set(), {}
                if not step["z0"][3 + j]:
                    inexact.add("history")
        return ("approx" if inexact else "move"), inexact, need

    def _note_rigid_body_moves(self) -> None:
        """Report the *RIGID BODY member BCs _plan_rigid_body_move put on reference nodes."""
        exact = [x for x in self._rb_moved if not x[3]]
        loose = [x for x in self._rb_moved if x[3]]
        if exact:
            m, d, ref, _ = exact[0]
            self.report.note(f"*BOUNDARY on {len(exact)} DOF(s) of {len({x[0] for x in exact})} "
                             f"*RIGID BODY node(s) moved to the reference node, translations with zero "
                             f"rotations about the other axes (e.g. node {m} DOF {d} -> reference node "
                             f"{ref}), as Abaqus/Standard does: ccx stops on a BC on a node the body drives "
                             f"('*ERROR in cascade ... dependent side of a MPC and a SPC'), and the "
                             f"BC'd nodes hold that DOF of the body and its rotations about the "
                             f"other axes anyway (identical BCs, nodes not on one line seen along "
                             f"the DOF, body not turned before the step). Exact.", once=True)
        if loose:
            m, d, ref, _ = loose[0]
            reasons = set().union(*[x[3] for x in loose])
            self.report.warn(f"[APPROX] *BOUNDARY on {len(loose)} DOF(s) of "
                             f"{len({x[0] for x in loose})} *RIGID BODY node(s) moved to the "
                             f"reference node, translations with zero rotations about the other axes "
                             f"(e.g. node {m} DOF {d} -> reference node {ref}), as Abaqus/Standard does, "
                             f"although that holds the body more than these BCs do: "
                             + "; ".join(RB_MOVE_INEXACT[k] for k in sorted(reasons)) +
                             ". Verify.", once=True)

    @staticmethod
    def _ref_bc(c: dict, st: Dict[Tuple[int, int], tuple], k: int) -> Optional[tuple]:
        """The BC on DOF ``k`` (1-6) of a constraint's reference node in state ``st``; its
        rotations may also be given on DOFs 1-3 of an explicit ROT NODE."""
        e = st.get((c["ref"], k))
        if e is None and k > 3 and c["rot"] is not None:
            e = st.get((c["rot"], k - 3))
        return e

    def _bc_lines_without(self, b: Block, drop: set,
                          add: "Optional[Dict[int, Dict[int, float]]]" = None) -> List[List[str]]:
        """The records of *BOUNDARY card ``b`` without the (node, DOF) pairs in ``drop``: a line
        that loses some of its nodes on some DOFs is split per DOF range, onto the remaining
        node or a node set of the remaining nodes (ABQ2CCX_BCn, registered for emission).
        ``add`` (reference node -> DOF -> value) goes in where the first line lost nodes."""
        out: List[List[str]] = []
        pending: List[List[str]] = []
        for ref, vals in (add or {}).items():
            spans: List[list] = []                 # [first DOF, last DOF, value]
            for k in sorted(vals):
                if spans and spans[-1][1] == k - 1 and spans[-1][2] == vals[k]:
                    spans[-1][1] = k
                else:
                    spans.append([k, k, vals[k]])
            pending += [[str(ref), str(a), str(c)] + ([fmt_num(v)] if v else [])
                        for a, c, v in spans]
        for rec in merged_data_records(b):
            g = [x.strip() for x in rec]
            while g and g[-1] == "":
                g.pop()
            if len(g) < 2:
                out.append(g)
                continue
            spec, rest = g[0], g[1:]
            if re.fullmatch(r"[-+]?\d+", rest[0]):
                last = rest[1] if len(rest) > 1 and rest[1] != "" else rest[0]
                if not re.fullmatch(r"[-+]?\d+", last):
                    out.append(g)
                    continue
                d1, d2 = int(rest[0]), int(last)
                dofs, extra = list(range(min(d1, d2), max(d1, d2) + 1)), rest[2:]
            else:
                named = self._named_bc_dofs(rest[0], self._named_bc_rot(spec))
                if named is None:
                    out.append(g)
                    continue
                dofs, extra = [d for a, c in named for d in range(a, c + 1)], []
            nodes = self._resolve_nodes(spec)
            if not any((n, d) in drop for n in nodes for d in dofs):
                out.append(g)
                continue
            runs: List[list] = []                  # [first DOF, last DOF, remaining nodes]
            for d in dofs:
                keep = [n for n in nodes if (n, d) not in drop]
                if runs and runs[-1][1] == d - 1 and runs[-1][2] == keep:
                    runs[-1][1] = d
                else:
                    runs.append([d, d, keep])
            for a, c, keep in runs:
                if keep:
                    out.append([spec if len(keep) == len(nodes) else self._node_subset(keep),
                                str(a), str(c)] + extra)
            out += pending
            pending = []
        return out + pending

    def _node_subset(self, nodes: List[int]) -> str:
        """A node id, or the name of a node set (ABQ2CCX_BCn) holding ``nodes``."""
        key = tuple(dedup(nodes))
        if len(key) == 1:
            return str(key[0])
        if key not in self._bc_subsets:
            k = len(self._bc_subsets) + 1
            while f"ABQ2CCX_BC{k}" in self.geom.nsets:
                k += 1
            self._bc_subsets[key] = f"ABQ2CCX_BC{k}"
            self.geom.nsets[f"ABQ2CCX_BC{k}"] = list(key)
        return self._bc_subsets[key]

    def _first_node(self, token: str) -> Optional[int]:
        nodes = self._resolve_nodes(token.strip()) if token.strip() else []
        return nodes[0] if nodes else None

    def _rigid_body_members(self, b: Block) -> Tuple[List[int], List[int]]:
        """(tie, pin) members of an Abaqus *RIGID BODY: TIE NSET and ELSET nodes move with
        the body in all DOFs, PIN NSET nodes in their translations only (ccx's NSET, should
        a deck use it, counts as TIE)."""
        tie: List[int] = []
        pin: List[int] = []
        for k, v in b.params.items():
            ku = k.upper().replace(" ", "")
            if not v:
                continue
            if ku == "PINNSET":
                pin.extend(self.geom.nset(v))
            elif ku in ("TIENSET", "NSET"):
                tie.extend(self.geom.nset(v))
            elif ku == "ELSET":
                for e in self.geom.elset(v):
                    if e in self.geom.elements:
                        tie.extend(self.geom.elements[e][1])
        tie = dedup(tie)
        tied = set(tie)
        return tie, [n for n in dedup(pin) if n not in tied]

    def _kinematic_dofs(self, b: Block) -> set:
        """DOFs a *KINEMATIC card couples (no data line: all of them, as in Abaqus)."""
        dofs: set = set()
        for rec in merged_data_records(b):
            f = [x for x in rec if x != ""]
            try:
                d1 = pint(f[0])
                d2 = pint(f[1]) if len(f) > 1 else d1
            except (IndexError, ValueError):
                continue
            dofs.update(range(min(d1, d2), max(d1, d2) + 1))
        return dofs or set(range(1, 7))

    def _surface_member_nodes(self, name: str) -> List[int]:
        """The nodes a *COUPLING on surface ``name`` acts on: a node surface's nodes, or the
        nodes on the listed element faces/edges."""
        sd = self.surfaces.get(name.upper())
        if not sd:
            return []
        nodes: List[int] = []
        types: Dict[str, str] = {}
        for token, face in sd[1]:
            if sd[0].startswith("NODE"):
                nodes.extend(self._resolve_nodes(token))
                continue
            eids = [int(token)] if re.fullmatch(r"[-+]?\d+", token) else self.geom.elset(token)
            for e in eids:
                nodes.extend(self._face_nodes(e, face, types))
        return dedup(nodes)

    def _face_nodes(self, eid: int, face: Optional[str], types: Dict[str, str]) -> List[int]:
        info = self.geom.elements.get(eid)
        if not info:
            return []
        typ, conn = info
        if typ not in types:
            types[typ] = ccx_element_type(typ, Report())
        cc, f, n = types[typ], (face or "").upper(), len(conn)
        if cc in SHELL_TYPES or cc.startswith("M3D"):
            # SPOS/SNEG (ccx S1/S2) cover the whole element; edges are E1..E4 (ccx S3..S6)
            m = re.fullmatch(r"E([1-4])", f) or re.fullmatch(r"S([3-6])", f)
            if not m:
                return list(conn)
            k = int(m.group(1)) - (2 if f.startswith("S") else 0)
            nc = 3 if n in (3, 6) else 4
            pos = [k, k % nc + 1] + ([nc + k] if n >= 2 * nc else [])
            return [conn[p - 1] for p in pos if p <= n]
        fam = {4: "TET", 10: "TET", 6: "WEDGE", 15: "WEDGE", 8: "HEX", 20: "HEX"}.get(n)
        m = re.fullmatch(r"S(\d)", f)
        if cc.startswith("C3D") and fam and m and int(m.group(1)) in FACE_NODES[fam]:
            return [conn[p - 1] for p in FACE_NODES[fam][int(m.group(1))] if p <= n]
        return list(conn)

    def _resolve_nodes(self, token: str) -> List[int]:
        if re.fullmatch(r"[-+]?\d+", token):
            return [int(token)]
        return self.geom.nset(token)

    # -- dependent DOFs of the converted deck ------------------------------------
    def _settle_dependents(self, out: List[str]) -> List[str]:
        """Choose the eliminated (first) term of every *EQUATION of the converted deck.

        ccx eliminates an equation's first DOF and stops when that DOF also has a *BOUNDARY
        ('*ERROR in cascade: the DOF ... is detected on the dependent side of a MPC and a
        SPC') or is eliminated by another constraint ('... on the dependent side of two
        different MPC's'); Abaqus resolves such overconstraints itself.  The terms of an
        equation can be listed in any order, so a clashing first term is swapped for one
        whose DOF is free: the same equation, which ccx then accepts.  The DOFs ccx
        eliminates itself are taken first — the coupled translations of *RIGID BODY and
        *KINEMATIC members, a *KINEMATIC reference node's DOFs 4-6 (they carry the coupling
        rotation; probed: an equation on one is 'on the dependent side of two different
        MPC's'), *TIE slaves and the nodes of native *MPCs — and a bipartite matching
        (augmenting paths) assigns the equations, so one can hand its DOF to another that has
        no other choice.  The equations are then accepted in order, each reduced by the ones
        before it: one that reduces to 0 = 0 is redundant and dropped (a duplicate, or a loop
        of ties, which ccx would hold at zero).  An equation left without a free DOF stays
        as it is, with a warning, except the converter's own rotation ties, which are
        dropped (the *BOUNDARY then governs that rotation)."""
        cards: List[Tuple[str, "OrderedDict[str, Optional[str]]", int, List[int]]] = []
        for j, line in enumerate(out):
            if line.startswith("**"):
                continue
            if line.startswith("*"):
                kw, params = parse_keyword_line(line)
                cards.append((kw, params, j, []))
            elif cards and line.strip():
                cards[-1][3].append(j)
        isint = re.compile(r"[-+]?\d+").fullmatch

        def fields(j: int) -> List[str]:
            f = [x.strip() for x in out[j].split(",")]
            while f and f[-1] == "":
                f.pop()
            return f
        inline: Dict[str, List[int]] = {}        # node sets / node surfaces the handlers wrote
        nsurf: Dict[str, List[int]] = {}

        def nodes_of(tok: str) -> List[int]:
            if isint(tok):
                return [int(tok)]
            return inline.get(tok.upper()) or self.geom.nset(tok)
        for kw, params, _, data in cards:
            if kw == "NSET" and (params.get("NSET") or "").upper() not in self.geom.nsets:
                toks = [t for j in data for t in fields(j) if t]
                ids: List[int] = []
                if "GENERATE" in params:
                    for a, c, inc in zip(toks[0::3], toks[1::3], toks[2::3]):
                        ids += list(range(pint(a), pint(c) + 1, max(pint(inc), 1)))
                else:
                    for t in toks:
                        ids += nodes_of(t)
                inline[(params.get("NSET") or "").upper()] = ids
            elif kw == "SURFACE" and (params.get("TYPE") or "").upper() == "NODE":
                nsurf[(params.get("NAME") or "").upper()] = \
                    [n for j in data for n in nodes_of(fields(j)[0])]

        def surface_nodes(name: str) -> List[int]:
            return nsurf.get(name.upper()) or self._surface_member_nodes(name)
        spc: set = set()
        segs: List[List[Tuple[bool, Tuple[int, int], bool]]] = [[]]   # BCs: model, each step
        transformed: set = set()
        tcard: Dict[int, Optional[Tuple[str, Vec, Vec]]] = {}   # node -> its (last) *TRANSFORM
        bc_first: Dict[Tuple[int, int], int] = {}               # (node, DOF) -> card of 1st BC
        # DOFs ccx eliminates itself: rigid-body / kinematic members' translations (a BC on
        # one stops ccx) and the DOFs its other constraints may eliminate (those accept a BC
        # — ccx picks around it or carries it over — but no *EQUATION can eliminate them)
        busy: Dict[Tuple[int, int], str] = {}
        taken_too: set = set()
        for ci, (kw, params, _, data) in enumerate(cards):
            if kw == "STEP":
                segs.append([])
            elif kw == "BOUNDARY":
                new = (params.get("OP") or "").strip().upper() == "NEW"
                for j in data:
                    f = fields(j)
                    if len(f) < 2 or not isint(f[1]):
                        continue
                    d1 = int(f[1])
                    d2 = int(f[2]) if len(f) > 2 and isint(f[2]) else d1
                    try:
                        z = "FIXED" not in params and (len(f) < 4 or pf(f[3]) == 0.0)
                    except ValueError:
                        z = False
                    for n in nodes_of(f[0]):
                        for d in range(min(d1, d2), max(d1, d2) + 1):
                            spc.add((n, d))
                            segs[-1].append((new, (n, d), z))
                            bc_first.setdefault((n, d), ci)
            elif kw == "TRANSFORM":
                ns = nodes_of((params.get("NSET") or "").strip())
                transformed.update(ns)
                try:
                    v = [pf(x) for j in data for x in fields(j) if x]
                    tc: Optional[Tuple[str, Vec, Vec]] = (
                        "C" if (params.get("TYPE") or "").strip().upper().startswith("C") else "R",
                        (v[0], v[1], v[2]), (v[3], v[4], v[5]))
                except (ValueError, IndexError):
                    tc = None
                tcard.update((n, tc) for n in ns)
            elif kw == "RIGID BODY":
                ref = (params.get("REF NODE") or "").strip()
                rot = (params.get("ROT NODE") or "").strip()
                members = nodes_of((params.get("NSET") or "").strip()) if params.get("NSET") else \
                    [n for e in self.geom.elset((params.get("ELSET") or "").strip())
                     if e in self.geom.elements for n in self.geom.elements[e][1]]
                for m in members:
                    if str(m) not in (ref, rot):
                        busy.update({(m, d): "*RIGID BODY" for d in (1, 2, 3)})
            elif kw == "COUPLING" and ci + 1 < len(cards) and \
                    cards[ci + 1][0] in ("KINEMATIC", "DISTRIBUTING"):
                ref = (params.get("REF NODE") or "").strip()
                nxt = cards[ci + 1]
                dofs: set = set()
                for j in nxt[3]:
                    f = fields(j)
                    if f and isint(f[0]):
                        d2 = int(f[1]) if len(f) > 1 and isint(f[1]) else int(f[0])
                        dofs.update(range(int(f[0]), d2 + 1))
                if not isint(ref) or not dofs:
                    continue
                if nxt[0] == "DISTRIBUTING":
                    taken_too.update((int(ref), d) for d in dofs)
                    continue
                taken_too.update((int(ref), d) for d in (4, 5, 6))    # the coupling rotation
                for m in surface_nodes((params.get("SURFACE") or "").strip()):
                    if m != int(ref):
                        busy.update({(m, d): "*KINEMATIC coupling" for d in dofs if d <= 3})
            elif kw == "MPC":
                for j in data:
                    f = fields(j)
                    nodes = [int(t) for t in f[1:] if isint(t)]
                    typ = f[0].upper() if f else ""
                    nodes = nodes[3:] if typ == "PLANE" else nodes[2:] if typ == "STRAIGHT" \
                        else nodes[:1] if typ == "BEAM" else nodes
                    taken_too.update((n, d) for n in nodes for d in (1, 2, 3))
            elif kw == "TIE":
                for j in data:
                    f = fields(j)
                    if f:
                        taken_too.update((n, d) for n in surface_nodes(f[0]) or nodes_of(f[0])
                                         for d in (1, 2, 3))
        # ccx turns a BC on a node with a *TRANSFORM into an MPC on its global DOFs
        spc_x = spc | {(n, d) for n, k in spc if n in transformed and k <= 3 for d in (1, 2, 3)}
        clash = sorted(k for k in busy if k in spc_x and k not in self._clash_dofs)
        for n, d in clash[:3]:
            self.report.warn(f"Possible overconstraint: node {n} DOF {d} is eliminated by a "
                             f"{busy[(n, d)]} (ccx builds it from MPCs) AND has a *BOUNDARY. "
                             f"CalculiX will stop with '*ERROR in cascade ... dependent side of a "
                             f"MPC and a SPC'. Remove the BC or the constraint on that DOF.",
                             once=True)
        # the equations: (card, [(node, dof, coefficient text), ...])
        eqs: List[Tuple[int, List[Tuple[int, int, str]]]] = []
        for ci, (kw, params, _, data) in enumerate(cards):
            if kw != "EQUATION" or params:
                continue
            toks = [t for j in data for t in fields(j) if t]
            parsed: List[List[Tuple[int, int, str]]] = []
            pos = 0
            try:
                while pos < len(toks):
                    cnt = pint(toks[pos])
                    trip = toks[pos + 1:pos + 1 + 3 * cnt]
                    pos += 1 + 3 * cnt
                    if cnt < 1 or len(trip) < 3 * cnt or \
                            not all(isint(trip[q]) and isint(trip[q + 1]) for q in range(0, len(trip), 3)):
                        raise ValueError
                    parsed.append([(int(trip[q]), int(trip[q + 1]), trip[q + 2])
                                   for q in range(0, len(trip), 3)])
            except (ValueError, IndexError):
                continue                       # set names / unreadable: left as written
            eqs += [(ci, terms) for terms in parsed]
        if not eqs:
            return out
        # the local axes of the transformed nodes (ccx reads any TYPE but C as rectangular)
        taxes: Dict[int, Tuple[Vec, Vec, Vec]] = {}
        for n, tc in tcard.items():
            ax = self._transform_axes(n, *tc) if tc and n in self.geom.nodes else "?"
            if not isinstance(ax, str):
                taxes[n] = ax
        taken = spc | set(busy) | taken_too
        # a local DOF of a transformed node mixes its global DOFs: none of them can be
        # eliminated here where ccx's own constraints eliminate one of those, or the axes are
        # unknown; where only a BC does, ccx's choice is followed (ccx_pick)
        taken |= {(n, d) for n, k in list(taken) if n in transformed and k <= 3 and
                  (n not in taxes or (n, k) in busy or (n, k) in taken_too) for d in (1, 2, 3)}
        # ccx eliminates a global DOF for each local one: for a BC (bounadd) the largest
        # component it can, for an *EQUATION's first term (equations.f) the first component from
        # its own direction on (1 -> 2 -> 3 -> 1) whose size is 1e-5 or more and that no
        # constraint eliminates yet — in deck order, and stops ('cannot be converted in MPC:
        # all ...') when none is left
        bc_ev = sorted((ci, n, d) for (n, d), ci in bc_first.items() if n in taxes and d <= 3)
        gtaken: Dict[int, set] = {}
        pos = [0]

        def bc_pick(n: int, i: int, tk: set) -> Optional[int]:
            e = taxes[n][i - 1]
            gs = [g for g in (1, 2, 3) if g not in tk and abs(e[g - 1]) > 1e-30]
            return max(gs, key=lambda g: abs(e[g - 1])) if gs else None

        def flush(upto: int) -> None:
            while pos[0] < len(bc_ev) and bc_ev[pos[0]][0] < upto:
                _, n, i = bc_ev[pos[0]]
                pos[0] += 1
                g = bc_pick(n, i, gtaken.setdefault(n, set()))
                if g is not None:
                    gtaken[n].add(g)

        def later_ok(n: int, tk: set) -> bool:
            tk = set(tk)
            for _, m, i in bc_ev[pos[0]:]:
                if m == n:
                    g = bc_pick(m, i, tk)
                    if g is None:
                        return False
                    tk.add(g)
            return True

        def ccx_pick(k: Tuple[int, int], coef: Dict[Tuple[int, int], float]) -> Optional[int]:
            """The global DOF ccx eliminates for dependent ``k``, a local DOF of a transformed
            node (0: not one), or None where it finds none, one whose coefficient vanishes in
            the equation's global form, or one a later BC on the node needs."""
            n, j = k
            if j > 3 or n not in taxes:
                return 0
            ax, tk = taxes[n], gtaken.setdefault(n, set())
            for g in ((j - 1 + q) % 3 + 1 for q in range(3)):
                if g in tk or abs(ax[j - 1][g - 1]) < 1e-5:
                    continue
                total = sum(c * ax[i - 1][g - 1] for (m, i), c in coef.items() if m == n and i <= 3)
                if abs(total) <= 1e-6 * max(abs(c) for c in coef.values()) or \
                        not later_ok(n, tk | {g}):
                    return None
                return g
            return None
        cands: List[List[Tuple[int, int]]] = []
        for _, terms in eqs:
            dofs = [(n, d) for n, d, _ in terms]
            try:
                big = max(abs(pf(c)) for _, _, c in terms)
                cands.append([(n, d) for n, d, c in terms if (n, d) not in taken and
                              dofs.count((n, d)) == 1 and abs(pf(c)) > 1e-9 * big])
            except ValueError:
                cands.append([])
        assign: Dict[int, Tuple[int, int]] = {}
        owner: Dict[Tuple[int, int], int] = {}
        for e, (_, terms) in enumerate(eqs):
            t0 = terms[0][:2]
            if cands[e] and cands[e][0] == t0 and t0 not in owner:
                assign[e], owner[t0] = t0, e

        def augment(start: int) -> bool:
            via: Dict[Tuple[int, int], int] = {}

            def options(e: int):                # free DOFs first, then the ones to displace
                return iter(sorted(cands[e], key=lambda c: (c in owner, c[1] <= 3 and
                                                            c[0] in transformed)))
            stack = [(start, options(start))]
            budget = 20000
            while stack and budget > 0:
                e, it = stack[-1]
                nxt = None
                for c in it:
                    if c in via:
                        continue
                    via[c] = e
                    budget -= 1
                    if c not in owner:         # free DOF: shift the assignments along the path
                        while True:
                            w = via[c]
                            prev = assign.get(w)
                            assign[w], owner[c] = c, w
                            if w == start:
                                return True
                            c = prev
                    nxt = owner[c]
                    break
                if nxt is None:
                    stack.pop()
                else:
                    stack.append((nxt, options(nxt)))
            return False
        for e in range(len(eqs)):
            if e not in assign:
                augment(e)
        # held at zero by a BC in every step
        held: Optional[set] = None
        for active in bc_steps(segs):
            now = {k for k, z in active.items() if z}
            held = now if held is None else held & now
        held = held or set()
        # Accept the equations in deck order, each reduced by the ones accepted before it
        # (their eliminated DOFs substituted): one that reduces to 0 = 0 — a duplicate, or
        # one closing a loop of ties — holds whenever the others do and is dropped; ccx
        # cannot take it (no DOF of it is free, or the loop gives a zero coefficient on the
        # dependent side and ccx then silently holds the loop at zero, probed).  The
        # eliminated DOF must keep a nonzero coefficient in the reduced equation, so no
        # loop reaches ccx; the matching's choice is tried first.
        accepted: Dict[Tuple[int, int], Dict[Tuple[int, int], float]] = {}

        def reduce(coef: Dict[Tuple[int, int], float], tol: float):
            res = dict(coef)
            for _ in range(500):
                k = next((q for q in res if q in accepted), None)
                if k is None:
                    return res
                c = res.pop(k)
                for q, a in accepted[k].items():
                    res[q] = res.get(q, 0.0) + c * a
                res = {q: v for q, v in res.items() if abs(v) > tol}
                if len(res) > 500:
                    break
            return None                        # too large to tell: taken as independent
        final: List[Optional[List[Tuple[int, int, str]]]] = []
        moved = dropped = redundant = rewritten = 0
        stuck: List[Tuple[int, int]] = []
        for e, (ci, terms) in enumerate(eqs):
            flush(ci)
            dofs = [(n, d) for n, d, _ in terms]
            try:
                coef: Dict[Tuple[int, int], float] = {}
                for n, d, c in terms:
                    coef[(n, d)] = coef.get((n, d), 0.0) + pf(c)
            except ValueError:
                final.append(terms)
                continue
            tol = 1e-9 * max(abs(c) for c in coef.values())
            res = reduce(coef, tol)
            if res is not None and all(q in held for q in res):
                final.append(None)                 # 0 = 0 in every step
                redundant += 1
                continue
            order = ([assign[e]] if e in assign else []) + \
                sorted(dofs, key=lambda k: k[1] <= 3 and k[0] in transformed)
            dep = next((k for k in order if k not in taken and k not in accepted and
                        dofs.count(k) == 1 and abs(coef[k]) > tol and
                        (res is None or abs(res.get(k, 0.0)) > tol) and
                        ccx_pick(k, coef) is not None), None)
            if dep is not None:
                g = ccx_pick(dep, coef)
                if g:
                    gtaken[dep[0]].add(g)
                accepted[dep] = {q: -c / coef[dep] for q, c in coef.items() if q != dep}
                if dep != dofs[0]:
                    k = dofs.index(dep)
                    terms = [terms[k]] + terms[:k] + terms[k + 1:]
                    moved += 1
                final.append(terms)
                continue
            alt = next((k for k in (res or {}) if k not in taken and k not in accepted and
                        ccx_pick(k, res) is not None), None)
            if alt is not None:
                g = ccx_pick(alt, res)
                if g:
                    gtaken[alt[0]].add(g)
                # no DOF of the equation itself is free, but the equation reduced by the
                # accepted ones (the same constraint, given those) has one
                accepted[alt] = {q: -c / res[alt] for q, c in res.items() if q != alt}
                final.append([(alt[0], alt[1], f"{res[alt]:.12g}")] +
                             [(q[0], q[1], f"{c:.12g}") for q, c in res.items() if q != alt])
                rewritten += 1
            elif frozenset(dofs) in self._gen_ties and len(terms) == 2:
                final.append(None)
                dropped += 1
            else:
                final.append(terms)
                stuck.append(dofs[0])
        new_cards: Dict[int, List[str]] = {}
        by_card: "OrderedDict[int, List[int]]" = OrderedDict()
        for e, (ci, _) in enumerate(eqs):
            by_card.setdefault(ci, []).append(e)
        for ci, es in by_card.items():
            if all(final[e] is eqs[e][1] for e in es):
                continue                           # this card stays as written
            lines: List[str] = []
            for e in es:
                terms = final[e]
                if terms is None:
                    continue
                lines.append(str(len(terms)))
                for q in range(0, len(terms), 4):
                    lines.append(", ".join(f"{n}, {d}, {c}" for n, d, c in terms[q:q + 4]))
            new_cards[ci] = lines
        if moved or rewritten:
            self.report.note(f"*EQUATION: {moved + rewritten} equation(s) reordered so that the "
                             f"eliminated (first) term is a DOF without a *BOUNDARY that no other "
                             f"constraint eliminates — ccx stops otherwise ('*ERROR in cascade ... "
                             f"dependent side of a MPC and a SPC' / '... two different MPC's'); "
                             f"each equation is unchanged"
                             + (f" ({rewritten} written reduced by the equations before it: the "
                                f"same constraint, given those)" if rewritten else "")
                             + " — Abaqus resolves this overconstraint itself.")
        if redundant:
            self.report.note(f"*EQUATION: {redundant} redundant equation(s) dropped — each follows "
                             f"from the equations before it and zero *BOUNDARY values that hold in "
                             f"every step (a duplicate, or one closing a loop of ties), so it holds "
                             f"anyway. ccx cannot take it: no DOF of it is free ('*ERROR in cascade "
                             f"... dependent side of a MPC and a SPC' / '... two different MPC's'), "
                             f"or a loop leaves a zero coefficient on the dependent side and ccx "
                             f"silently holds the loop at zero. Abaqus removes such a redundant "
                             f"constraint itself.")
        if dropped:
            self.report.note("Coupled rotation not tied where the node's DOF has a *BOUNDARY and "
                             "the body's rotation DOF is already fixed or eliminated (ccx stops on a "
                             "DOF that is SPC'd and dependent in an MPC) — the BC governs it.",
                             once=True)
        for n, d in stuck[:5]:
            self.report.warn(f"Possible overconstraint: node {n} DOF {d} is on the dependent side of "
                             f"an *EQUATION whose every DOF has a *BOUNDARY or is eliminated by "
                             f"another constraint. CalculiX will stop with '*ERROR in cascade ... "
                             f"dependent side of a MPC and a SPC' (or '... two different MPC's'). "
                             f"Remove the BC or the constraint on that DOF.", once=True)
        if not new_cards:
            return out
        drop_lines: set = set()
        insert: Dict[int, List[str]] = {}
        for ci, lines in new_cards.items():
            _, _, j, data = cards[ci]
            drop_lines.update(data)
            if lines:
                insert[data[0]] = lines
            else:
                drop_lines.add(j)              # every equation of the card dropped
        res: List[str] = []
        for j, line in enumerate(out):
            if j in insert:
                res += insert[j]
            if j not in drop_lines:
                res.append(line)
        return res

    def _warn_coupled_clashes(self) -> None:
        """The *BOUNDARY on rigid-constraint member DOFs that the reference node's BCs do not
        impose and that stay (_plan_coupled_bcs): one warning per constraint kind, DOF type and
        reason, with what ccx does with it and what Abaqus does instead."""
        what = {"kin": "a kinematic coupling", "rb": "a *RIGID BODY",
                "mpc": "an *MPC BEAM (a *RIGID BODY in ccx)"}
        groups: "OrderedDict[Tuple[str, str, bool, str], List[Tuple[int, int, int]]]" = OrderedDict()
        for kind, emit, m, d, ref, why in self._coupled_clash:
            groups.setdefault((kind, emit, d <= 3, why), []).append((m, d, ref))
        for (kind, emit, trans, why), items in groups.items():
            m, d, ref = items[0]
            nodes = len({n for n, _, _ in items})
            where = (f"node {m} DOF {d} follows reference node {ref} through {what[kind]} and also "
                     f"has a *BOUNDARY that the reference node's BCs do not impose ({len(items)} "
                     f"such DOF(s) on {nodes} node(s)). ")
            if trans:
                effect = "ccx stops: '*ERROR in cascade ... dependent side of a MPC and a SPC'. "
            elif emit == "kin":
                effect = ("The shell/beam rotation keeps the BC and is not tied to the coupling's "
                          "(ccx cannot have both), unlike in Abaqus. ")
            else:
                effect = ("In ccx the body then follows that rotation (the converter's rotation tie "
                          "is turned round; the first node's, if they differ), unlike in "
                          "Abaqus. ")
            move = ("Abaqus/Standard moves identical BCs on rigid-body nodes to the reference node, "
                    "adding zero rotations about the other axes")
            if kind != "rb":
                fix = ("Abaqus/Standard eliminates the constrained DOFs at these nodes and does not "
                       "apply a BC there, so the node follows the constraint: take the node out of "
                       "the BC (or the constraint), or rerun with --approximate to drop such BCs as "
                       "Abaqus does.")
            elif why.startswith("approx:"):
                fix = (move + "; here that holds the body more than these BCs do ("
                       + "; ".join(RB_MOVE_INEXACT[k] for k in why[7:].split(",")) +
                       "). Rerun with --approximate to move them as Abaqus does, or put the BC on "
                       "the reference node.")
            elif why == "differ":
                fix = ("The BCs differ between the body's nodes, and Abaqus/Standard stops with an "
                       "error too (it only moves identical BCs to the reference node): put one BC "
                       "on the reference node instead.")
            elif why == "conflict":
                fix = ("They disagree with the reference node's own BCs (on that DOF, or on a "
                       "rotation about another axis, which the moved BC would hold at zero), and "
                       "Abaqus/Standard stops with an error too: fix the BCs.")
            elif why == "kind":
                fix = (move + ", but the converter does not move a FIXED, USER or acceleration BC "
                       "or one in local (*TRANSFORM) DOFs: put the BC on the reference node.")
            else:
                fix = move + " and stops if they differ: put the BC on the reference node instead."
            self.report.warn("Possible overconstraint: " + where + effect + fix, once=True)

    # ======================================================================
    # Planar models: ccx runs 2-D beams and trusses as 3-D elements
    # ======================================================================
    def _find_planar_elements(self) -> None:
        """Record the deck's planar beams/trusses (B21, T2D2, ...) and the element types that
        keep the model from being planar — before the beam-section upgrades retype elements
        (a B21 with a circular section becomes a B32 with a midside node)."""
        self._planar_elems = {}
        others: set = set()
        for eid, (typ, _conn) in self.geom.elements.items():
            base = planar_line_type(typ)
            if base:
                self._planar_elems[eid] = base
            elif not typ.upper().startswith(PLANAR_COMPANION_PREFIXES):
                others.add(typ.upper())
        self._planar_others = sorted(others)

    def _plan_planar_constraint(self, blocks: List[Block]) -> None:
        """Keep a planar model's 2-D beams and trusses in their plane.  ccx runs them as 3-D
        B31/B32/T3D2 elements whose out-of-plane motion nothing restrains (probed on 2.23):
        every bending mode appears twice in *FREQUENCY, *BUCKLE finds out-of-plane buckling,
        and a truss node is a mechanism (0 Hz modes; U3 is solver noise).  Fixing DOF 3 on
        their nodes (midside nodes of upgraded beams included) leaves the in-plane response
        unchanged (static, NLGEOM and *DYNAMIC to 6 digits).  The rotations are NOT fixed on
        every node: that stiffens ccx's expanded beams (a circular-section B32's bending
        frequencies 16x too high, a RECT B32 ~10 % too stiff) and changes *DYNAMIC results
        (knots).  A straight beam whose twist nothing restrains (pinned supports, or the
        U1/U2/UR3 clamp CAE writes) keeps a rigid twist mode — 0 Hz in *FREQUENCY, *BUCKLE
        factors near 1, an NLGEOM step that stops converging (B31) — so DOFs 4-5 are fixed
        at ONE of its nodes: one whose in-plane rotation is already fixed (no effect on any
        section), else a support (no effect on B31, B32 RECT, B32R PIPE/BOX).  A beam with a
        circular section gets them at the middle node of an element next to a support
        instead: at an element end node ccx 2.23 would lock the bending rotation as well
        (see _plan_circ_rotation_knots), at a middle node the BC holds only the rotations it
        names (probed: static, NLGEOM, *FREQUENCY and *BUCKLE as with the twist free, to 4
        digits).  Nodes whose DOF 3 a constraint drives, or under a *TRANSFORM whose 3-axis
        is not z, are left out.  Fills ``self._planar_bc`` (model data; handle_boundary
        repeats it after OP=NEW, which removes it) and ``self._planar_twist``."""
        self._planar_bc = []
        self._planar_twist = []
        planar = {e: t for e, t in self._planar_elems.items() if e in self.geom.elements}
        if not planar:
            return
        kinds = ", ".join(sorted(set(planar.values())))
        if self._planar_others:
            more = ", ..." if len(self._planar_others) > 4 else ""
            self.report.warn(f"2-D beam/truss elements ({kinds}) share the model with "
                             f"{', '.join(self._planar_others[:4])}{more}: ccx runs them as 3-D "
                             f"elements, and in a model that is not planar their out-of-plane DOFs "
                             f"were left free — verify.", once=True)
            return
        nodes = dedup([n for e in planar for n in self.geom.elements[e][1] if n in self.geom.nodes])
        if not nodes:
            return
        pts = [self.geom.nodes[n] for n in nodes]
        extent = max(max(p[i] for p in pts) - min(p[i] for p in pts) for i in range(3))
        zs = [p[2] for p in pts]
        if max(zs) - min(zs) > 1e-6 * extent:
            self.report.warn(f"2-D beam/truss elements ({kinds}) whose nodes are not in one plane "
                             f"z = const (z from {min(zs):g} to {max(zs):g}): ccx runs them as 3-D "
                             f"elements at the given z, while Abaqus' planar elements ignore z; "
                             f"their out-of-plane DOFs were left free — verify.", once=True)
            return
        held = self._planar_held_nodes(blocks)
        skew = self._planar_skew_nodes(blocks)
        fixed = [n for n in nodes if n not in held and n not in skew]
        twist, loose = ([], 0) if getattr(self.opt, "solid_dof", False) else \
            self._planar_twist_nodes(blocks, planar, held)
        left = len(nodes) - len(fixed)
        why = (f"{left} node(s) whose DOF 3 an *EQUATION, *MPC, rigid body, coupling or *TIE "
               f"drives, or under a *TRANSFORM whose 3-axis is not z, were left out")
        if not fixed and not twist:
            self.report.warn(f"Planar model: ccx runs the 2-D beams/trusses ({kinds}) as 3-D "
                             f"elements, but no out-of-plane constraint could be added: {why}.",
                             once=True)
            return
        self.geom.nsets[PLANAR_NODES_SET] = sorted(fixed)
        self._planar_bc = ["*BOUNDARY"] + ([f"{PLANAR_NODES_SET}, 3, 3"] if fixed else []) + \
            [f"{n}, 4, 5" for n in twist]
        self._planar_twist = list(twist)
        effects = ([] if set(planar.values()) <= PLANAR_TRUSS_TYPES else
                   ["each bending mode would appear twice in *FREQUENCY and *BUCKLE could find "
                    "out-of-plane buckling"]) + \
                  (["truss nodes would be mechanisms (U3 solver noise, 0 Hz modes)"]
                   if set(planar.values()) & PLANAR_TRUSS_TYPES else [])
        self.report.note(f"Planar model: ccx runs the 2-D beams/trusses ({kinds}) as 3-D elements "
                         f"(B21 as a B31, T2D2 as a T3D2), whose out-of-plane motion is free — "
                         f"{'; '.join(effects)}. DOF 3 is fixed on their {len(fixed)} node(s) (node "
                         f"set {PLANAR_NODES_SET}, model data, repeated after *BOUNDARY, OP=NEW), as "
                         f"in Abaqus' planar model{'; ' + why if left else ''}.", once=True)
        if twist:
            shown = ", ".join(map(str, twist[:5])) + (", ..." if len(twist) > 5 else "")
            circ_mids = {c[1] for e in self._circ_beam_elements(blocks)
                         for c in [self.geom.elements[e][1]] if len(c) == 3}
            middle = (" (on a circular section: at the middle node of an element next to one, "
                      "where ccx 2.23 does not lock the bending rotation with it)"
                      if set(twist) & circ_mids else "")
            self.report.note(f"The twist (rotation about the beam axis) of {len(twist)} straight 2-D "
                             f"beam(s) was unrestrained — Abaqus' planar beams have no such DOF; in "
                             f"ccx it is a 0 Hz *FREQUENCY mode, makes *BUCKLE factors meaningless "
                             f"and can stop an NLGEOM step converging. DOFs 4-5 are fixed at node(s) "
                             f"{shown}: one per beam, at a node whose in-plane rotation is already "
                             f"fixed, else at a support{middle}.", once=True)
        if loose:
            self.report.warn(f"The twist (rotation about the beam axis) of {loose} straight 2-D "
                             f"beam(s) is unrestrained — Abaqus' planar beams have no such DOF; ccx "
                             f"shows a 0 Hz twist mode in *FREQUENCY and its *BUCKLE factors (near 1) "
                             f"are meaningless. No BC was added: none of its nodes can take one "
                             f"(nodes under a *TRANSFORM, where ccx allows no rotational BC, and "
                             f"rigid-body/coupling reference nodes are skipped; on a circular section "
                             f"only an element's middle node holds the twist alone).", once=True)
        if any(t not in PLANAR_TRUSS_TYPES for t in planar.values()) and \
                any(b.keyword in ("FREQUENCY", "COMPLEX FREQUENCY") for b in blocks):
            self.report.warn("*FREQUENCY on a planar beam model: ccx's 3-D beams keep their twist "
                             "(rotation about the beam axis), so the eigenmodes include twist modes "
                             "that Abaqus' planar beams cannot have — skip them when comparing "
                             "frequencies (fixing the rotations on every node would stiffen ccx's "
                             "expanded beams instead).", once=True)

    def _planar_held_nodes(self, blocks: List[Block]) -> set:
        """Nodes whose DOF 3 a ccx constraint may drive: the dependent term of an *EQUATION,
        *MPC nodes, *RIGID BODY members, coupling reference and member nodes, *TIE slaves.
        A *BOUNDARY on a dependent DOF stops ccx ('dependent side of a MPC and a SPC'), and
        their out-of-plane motion follows the constraint."""
        held: set = set()
        for b in blocks:
            kw = b.keyword
            if kw == "EQUATION":
                toks = [x for rec in merged_data_records(b) for x in rec if x != ""]
                i = 0
                while i + 3 < len(toks):                 # count, then node, DOF, coefficient, ...
                    try:
                        k, dof = pint(toks[i]), pint(toks[i + 2])
                    except ValueError:
                        break
                    if dof == 3:
                        held.update(self._resolve_nodes(toks[i + 1]))
                    i += 1 + 3 * max(k, 1)
            elif kw == "MPC":
                for rec in merged_data_records(b):
                    for tok in [x for x in rec if x != ""][1:]:
                        held.update(self._resolve_nodes(tok))
            elif kw == "RIGID BODY":
                for k, v in b.params.items():
                    key = k.replace(" ", "")
                    if v and key in ("NSET", "PINNSET", "TIENSET"):
                        held.update(self.geom.nset(v.strip()))
                    elif v and key == "ELSET":
                        for e in self.geom.elset(v.strip()):
                            held.update(self.geom.elements[e][1] if e in self.geom.elements else [])
            elif kw in ("COUPLING", "KINEMATIC COUPLING", "DISTRIBUTING COUPLING"):
                ref = (b.param("REF NODE") or b.param("REFNODE") or "").strip()
                held.update(self._resolve_nodes(ref) if ref else [])
                if kw == "COUPLING":
                    held.update(self._surface_nodes((b.param("SURFACE") or "").strip()))
                else:
                    for rec in merged_data_records(b):
                        if rec and rec[0].strip():
                            held.update(self._resolve_nodes(rec[0].strip()))
            elif kw == "TIE" or (kw == "CONTACT PAIR" and b.has("TIED")):
                for rec in merged_data_records(b):
                    if rec and rec[0].strip():
                        held.update(self._surface_nodes(rec[0].strip()))
        return held

    def _planar_skew_nodes(self, blocks: List[Block]) -> set:
        """Nodes under a *TRANSFORM whose local 3-axis is not the global z: ccx applies their
        BCs in the local system, so DOF 3 there is not the out-of-plane direction."""
        skew: set = set()
        for b in blocks:
            if b.keyword != "TRANSFORM":
                continue
            kind = (b.param("TYPE") or "R").strip().upper()
            try:
                v = [pf(x) for rec in merged_data_records(b) for x in rec if x != ""]
            except ValueError:
                v = []
            axis: Optional[Vec] = None
            if len(v) >= 6 and kind in ("R", "C"):     # R: a x b; C: the axis through a and b
                a, c = (v[0], v[1], v[2]), (v[3], v[4], v[5])
                axis = vcross(a, c) if kind == "R" else vsub(c, a)
            if axis is None or vnorm(axis) == 0 or abs(axis[2]) < (1 - 1e-6) * vnorm(axis):
                skew.update(self._resolve_nodes((b.param("NSET") or "").strip()))
        return skew

    def _boundary_records(self, b: Block) -> Iterator[Tuple[List[int], set, bool]]:
        """(nodes, DOFs, moves) per data line of the *BOUNDARY ``b``; ``moves`` is True when
        the line prescribes a value other than 0 (or the card velocities, accelerations,
        FIXED or USER values)."""
        typ = (b.param("TYPE") or "").strip().upper()
        moving = typ in ("VELOCITY", "ACCELERATION") or b.has("FIXED") or b.has("USER")
        for nodes, dofs, mag in self._bc_records(b, rot=True):
            yield nodes, set(dofs), moving or mag != 0.0     # NaN (a *PARAMETER name): moves

    def _bc_dofs_by_node(self, blocks: List[Block]) -> Dict[int, set]:
        """Every DOF some *BOUNDARY (model data or any step) prescribes, per node."""
        dofs: Dict[int, set] = {}
        for b in blocks:
            if b.keyword != "BOUNDARY":
                continue
            for nodes, ds, _moves in self._boundary_records(b):
                for n in nodes:
                    dofs.setdefault(n, set()).update(ds)
        return dofs

    def _circ_beam_elements(self, blocks: List[Block]) -> set:
        """Elements under a *BEAM SECTION with SECTION=CIRC."""
        circ: set = set()
        for b in blocks:
            if b.keyword == "BEAM SECTION" and (b.param("SECTION") or "").strip().upper() == "CIRC":
                circ.update(self.geom.elset((b.param("ELSET") or "").strip()))
        return {e for e in circ if e in self.geom.elements}

    def _planar_twist_nodes(self, blocks: List[Block], planar: Dict[int, str],
                            held: set) -> Tuple[List[int], int]:
        """For each straight 2-D beam (a connected set of planar beam elements on one line)
        whose twist no BC restrains: the node to fix DOFs 4-5 at (see
        _plan_planar_constraint).  Returns those nodes and the number of such beams with no
        safe node.  Beams with constrained nodes are left alone (the constraint may hold
        the twist); a beam that is not straight has no rigid twist once DOF 3 is fixed.
        Nodes with a *TRANSFORM are never picked: ccx allows no rotational BC there.  On a
        circular section the node is a 3-node element's middle node."""
        beams = [e for e, t in planar.items() if t not in PLANAR_TRUSS_TYPES]
        root: Dict[int, int] = {}

        def find(n: int) -> int:
            root.setdefault(n, n)
            while root[n] != n:
                root[n] = root[root[n]]
                n = root[n]
            return n

        for e in beams:
            conn = self.geom.elements[e][1]
            for n in conn[1:]:
                root[find(n)] = find(conn[0])
        groups: "OrderedDict[int, List[int]]" = OrderedDict()
        for e in beams:
            groups.setdefault(find(self.geom.elements[e][1][0]), []).append(e)
        circ = self._circ_beam_elements(blocks)
        bc = self._bc_dofs_by_node(blocks) if groups else {}
        turned = {n for b in blocks if b.keyword == "TRANSFORM"
                  for n in self._resolve_nodes((b.param("NSET") or "").strip())}
        picks: List[int] = []
        loose = 0
        for elems in groups.values():
            cn = dedup([n for e in elems for n in self.geom.elements[e][1] if n in self.geom.nodes])
            if not cn or any(n in held for n in cn):
                continue
            p0 = self.geom.nodes[cn[0]]
            far = max(cn, key=lambda n: vnorm(vsub(self.geom.nodes[n], p0)))
            length = vnorm(vsub(self.geom.nodes[far], p0))
            if length == 0:
                continue
            d = vscale(vsub(self.geom.nodes[far], p0), 1.0 / length)
            if any(vnorm(vcross(vsub(self.geom.nodes[n], p0), d)) > 1e-6 * length for n in cn):
                continue
            # the twist is the rotation about d: DOF 4 alone holds it on a beam along x
            if any({4, 5} <= ds or (4 in ds and abs(d[1]) < 1e-6) or (5 in ds and abs(d[0]) < 1e-6)
                   for ds in (bc.get(n, set()) for n in cn)):
                continue
            cand = [n for n in cn if n not in turned and n not in self._ref_nodes]
            clamped = [n for n in cand if 6 in bc.get(n, set())]
            supports = [n for n in cand if bc.get(n, set()) & {1, 2, 3}]
            if clamped:
                picks.append(clamped[0])
            elif any(e in circ for e in elems):
                # a circular section: the middle node of a 3-node element, one next to a
                # support if there is one (at an end node the BC would lock the bending too)
                mids = [c for c in (self.geom.elements[e][1] for e in elems)
                        if len(c) == 3 and c[1] in cand]
                near = [c for c in mids if c[0] in supports or c[2] in supports]
                if mids:
                    picks.append((near or mids)[0][1])
                else:
                    loose += 1
            elif not cand:
                loose += 1
            else:
                picks.append(supports[0] if supports else min(cand))
        return picks, loose

    # ======================================================================
    # Rotational BCs on circular-section beams
    # ======================================================================
    def _plan_circ_rotation_knots(self, blocks: List[Block]) -> None:
        """ccx expands a circular-section beam node into eight nodes on the circle (corners
        at 45 degrees, midsides on the section axes) and, for every rotational BC on a
        B32/B32R node that is not a knot, ties that section's four midside nodes to the mean
        of their corners (gen3dboun) — exact on a rectangle (RECT, PIPE, BOX), but no rigid
        rotation of a circle satisfies it, so a BC on DOF 4, 5 or 6 at an element end node
        locks the twist and both bending rotations there.  Probed on 2.23 (B32, 10
        elements): a pinned beam whose twist is held at both supports deflects 0.27 of beam
        theory (DOF 4 at one end: 0.46), a prescribed tip rotation gives 0.76 of its
        deflection, DOF 4 on every node 0.009.  A knot hands the BCs to its rotation node
        instead, so every element end node of a CIRC beam whose rotational BCs hold only some
        of DOFs 4-6, or a nonzero value, in some step gets a knot beam (_add_knot_beams):
        0.994 and 1.00.  The knot's rigid section costs a little where the beam bends
        (0.3-1.3 % with a knot inside a span of 40-10 elements; nothing at a pinned end); a
        node ccx makes a knot anyway (a frame joint) gets one too, harmlessly.  Left alone:
        full zero clamps (exact as they are), 3-node elements' middle nodes (the tied nodes
        are unused there), nodes with a *TRANSFORM (ccx allows no rotational BC there) or
        that are rigid-body/coupling reference nodes, heat-transfer-only decks; a deck with
        an explicit dynamic step is only warned (the explicit solver stops on the density-
        free knot beams: '*ERROR in calcstabletimeincvol').  Runs after
        _plan_planar_constraint, whose DOF 4-5 lines count in every step."""
        if getattr(self.opt, "solid_dof", False):
            return
        ends = {n for e in self._circ_beam_elements(blocks)
                for c in [self.geom.elements[e][1]] if len(c) == 3 for n in (c[0], c[2])}
        procs = [b.keyword for b in blocks if b.keyword in PROC_KW]
        if not ends or all(p == "HEAT TRANSFER" for p in procs):
            return
        twist = set(self._planar_twist) & ends
        active: Dict[int, set] = {}                      # node -> rotations a BC holds now
        moves: set = set()                               # nodes given a nonzero rotation
        need: List[int] = []

        def check() -> None:                             # the BCs a step solves with
            for n in sorted((set(active) | twist) & ends):
                rot = active.get(n, set()) | ({4, 5} if n in twist else set())
                if rot and (rot != {4, 5, 6} or n in moves):
                    need.append(n)

        for b in blocks:
            if b.keyword == "BOUNDARY":
                if (b.param("OP") or "").strip().upper() == "NEW":
                    active = {}
                for nodes, ds, moving in self._boundary_records(b):
                    for n in (nodes if ds & {4, 5, 6} else []):
                        if n in ends:
                            active.setdefault(n, set()).update(ds & {4, 5, 6})
                            if moving:
                                moves.add(n)
            elif b.keyword == "END STEP":
                check()
        check()
        turned = {n for b in blocks if b.keyword == "TRANSFORM"
                  for n in self._resolve_nodes((b.param("NSET") or "").strip())}
        need = [n for n in dedup(need) if n not in turned and n not in self._ref_nodes
                and n not in self._knots]
        if not need:
            return
        shown = ", ".join(map(str, need[:5])) + (", ..." if len(need) > 5 else "")
        if any(b.keyword == "DYNAMIC" and b.has("EXPLICIT") for b in blocks):
            self.report.warn(f"Rotational BCs on {len(need)} element end node(s) of circular-section "
                             f"beams ({shown}) hold only some rotations, or a nonzero one: ccx 2.23 "
                             f"locks the node's other rotations as well (probed: a pinned beam with "
                             f"its twist held at the supports deflects about 0.3 of beam theory). The "
                             f"knot beams that repair it were not added: ccx's explicit solver stops "
                             f"on them ('*ERROR in calcstabletimeincvol', they have no density) — "
                             f"verify.", once=True)
            return
        self._add_knot_beams(need, blocks)
        self.report.note(f"Rotational BCs on circular-section beams: for a rotational BC on a "
                         f"B32/B32R node ccx 2.23 ties the section's midside nodes to its corners, "
                         f"which a circle cannot follow, so a BC on some of DOFs 4-6 (or a nonzero "
                         f"one) would lock the node's other rotations as well (probed: a pinned beam "
                         f"with its twist held at the supports deflects about 0.3 of beam theory). "
                         f"The {len(need)} such node(s) ({shown}) got a force-free knot beam (a B31 "
                         f"to a new free node, elset/material {KNOT_SET}, no density): a knot's BCs "
                         f"hold only the rotations they name.", once=True)
        if len(need) > max(2, len(ends) // 4):
            self.report.warn(f"{len(need)} of the {len(ends)} element end nodes of circular-section "
                             f"beams got a knot beam for their rotational BCs: each knot is a rigid "
                             f"section, which stiffens the beam where it bends (probed: DOF 4 held on "
                             f"every node of a 10-element beam deflects 0.84 of beam theory with the "
                             f"knots, 0.009 without) — verify.", once=True)

    # ======================================================================
    # *BOUNDARY, OP=NEW after rotational BCs on shell/beam nodes
    # ======================================================================
    def _plan_op_new_rotations(self, blocks: List[Block]) -> None:
        """ccx 2.23 does not rebuild rotational BCs on shell/beam nodes after a later step's
        *BOUNDARY, OP=NEW (probed; ccx sources boundarys.f, gen3dboun.f, usermpc.f).  ccx
        applies a rotational BC on a shell/beam node that is not a knot through a mean-
        rotation MPC whose angle is a hidden SPC.  OP=NEW deletes that SPC with the user's BCs
        but keeps the MPC, and the re-specified BC's new MPC finds no free dependent DOF
        ('*WARNING in usermpc: no MPC is generated for the mean rotation'): a clamped B31
        cantilever then deflects 3e5 times too far, *FREQUENCY finds a 0.1 Hz mode, *BUCKLE
        factors are ~1 and an NLGEOM step never converges.  On shells the stale SPC indices
        also zero unrelated BCs (a prescribed displacement came out 0), without any message.
        OP=NEW in the first step is harmless (ccx builds these MPCs after reading a step), as
        are *DYNAMIC steps (ccx uses knots there) and *CLOAD, OP=NEW.  From the second step
        on, once shell/beam nodes have had rotational BCs:

        * a step whose *BOUNDARY cards re-specify every BC in effect removes nothing, so its
          OP=NEW is dropped (``self._op_new_drop``): the same model in Abaqus and ccx;
        * a step that does remove BCs keeps OP=NEW, and the shell nodes that had rotational
          BCs before it (the stale indices) and the beam nodes that had them before it and
          get them again from it on get a knot beam (``_add_knot_beams``): ccx then carries
          the node's rotations on a knot, whose BCs OP=NEW removes and re-applies cleanly.
          Probed: exact on S4/S4R/S8R (6 digits); a knot holds a beam section rigid, which
          stiffens a B31 clamp by 0.65 % and a B32R one by 0.1 %.  A deck with an explicit
          step only gets a warning: the massless knot beams stop ccx's explicit solver."""
        if not self._rot_nodes:
            return
        planar = self._boundary_dofs([mkblock("BOUNDARY", data=self._planar_bc[1:])]) \
            if self._planar_bc else set()
        state = set(planar)                        # (node, DOF) pairs in effect
        steps: List[List[Block]] = []               # each step's *BOUNDARY cards ...
        procs: List[str] = []                       # ... and procedure
        inside = False
        for b in blocks:
            if b.keyword in ("STEP", "END STEP"):
                inside = b.keyword == "STEP"
                if inside:
                    steps.append([])
                    procs.append("")
            elif inside and b.keyword == "BOUNDARY":
                steps[-1].append(b)
            elif inside and b.keyword in PROC_KW:
                procs[-1] = procs[-1] or b.keyword
            elif b.keyword == "BOUNDARY":
                state |= self._boundary_pairs(b)

        def rotations(pairs: set) -> set:
            return {n for n, d in pairs if 4 <= d <= 6 and n in self._rot_nodes
                    and n not in self._knots}

        # ccx acts on OP=NEW on a step's first *BOUNDARY card only; handle_boundary repeats
        # the planar constraint after it
        new = [bool(c) and (c[0].param("OP") or "").strip().upper() == "NEW" for c in steps]
        given = [set().union(*map(self._boundary_pairs, c)) | (planar if nw else set())
                 for c, nw in zip(steps, new)]
        later = [set() for _ in range(len(steps) + 1)]   # nodes given rotations in step k or later
        for k in range(len(steps) - 1, -1, -1):
            later[k] = later[k + 1] | rotations(given[k])
        built: set = set()          # nodes whose rotational BCs ccx has made mean-rotation MPCs
        dropped: List[int] = []
        removing: List[int] = []
        knots: set = set()
        for k, cards in enumerate(steps):
            if new[k] and k and built:
                if state <= given[k]:
                    self._op_new_drop.update({id(c): i == 0 for i, c in enumerate(cards)})
                    dropped.append(k + 1)
                else:
                    removing.append(k + 1)
                    knots |= (built & self._shell_nodes) | ((built - self._shell_nodes) & later[k])
            state = given[k] if new[k] else state | given[k]
            if procs[k] != "DYNAMIC":               # a *DYNAMIC step makes knots instead
                built |= rotations(state)
        why = ("ccx 2.23 does not rebuild rotational BCs on shell/beam nodes after OP=NEW (probed: "
               "a clamped beam becomes a hinge, *FREQUENCY finds ~0 Hz modes, *BUCKLE factors "
               "near 1; on shells unrelated BC values are zeroed)")
        if dropped:
            self.report.note(f"*BOUNDARY, OP=NEW dropped in step(s) {', '.join(map(str, dropped))}: "
                             f"each re-specifies every boundary condition in effect, so OP=NEW "
                             f"removes nothing (the same model) — and {why}.", once=True)
        if not knots:
            return
        when = f"*BOUNDARY, OP=NEW in step(s) {', '.join(map(str, removing))} removes boundary " \
               f"conditions, and {why}."
        if any(b.keyword == "DYNAMIC" and b.has("EXPLICIT") for b in blocks):
            self.report.warn(f"{when} The knot beams that repair this stop ccx's explicit solver "
                             f"('*ERROR in calcstabletimeincvol': they have no mass), so none were "
                             f"added: check the rotations of the {len(knots)} shell/beam node(s) "
                             f"involved from step {removing[0]} on.", once=True)
            return
        self._add_knot_beams(sorted(knots), blocks)
        self.report.note(f"{when} Each of the {len(knots)} shell/beam node(s) whose rotational BCs "
                         f"it would break got a force-free knot beam (a B31 to a new free node, "
                         f"elset/material {KNOT_SET}, no density): ccx then carries the node's "
                         f"rotations on a knot, which OP=NEW handles. A knot holds a beam section "
                         f"rigid at the node, as beam theory does: a clamped B31 is ~0.7 % stiffer "
                         f"than with ccx's own clamp (B32R 0.1 %; shells unchanged).", once=True)

    def _boundary_pairs(self, b: Block) -> set:
        """(node, DOF) pairs one *BOUNDARY card prescribes, upgraded beams' midside nodes
        included (handle_boundary extends a DOF that both end nodes get to the midside node)."""
        pairs = self._boundary_dofs([b])
        if self._midside:
            by_node: Dict[int, set] = {}
            for n, d in pairs:
                by_node.setdefault(n, set()).add(d)
            pairs |= {(m, d) for a, c, m in self._midside.values()
                      for d in by_node.get(a, set()) & by_node.get(c, set())}
        return pairs

    # ======================================================================
    # Explicit dynamics with circular-section beams
    # ======================================================================
    def _plan_circ_explicit_increment(self, blocks: List[Block]) -> None:
        """ccx sizes an explicit step's increment from a Courant estimate per element
        (calcstabletimeincvol.f): critom * h * 0.3 / (2 c) times a safety factor 0.8/1.3,
        with c the material's dilatational wave speed, critom = 1.96 / sqrt(1 - a (1 + a
        (2 + a))) for ALPHA = a, and h the smallest one-point volume / face area of the
        20-node brick a 3-node beam expands into.  A circular section puts that brick's
        corners at 45 degrees on the circle and its midside nodes on the section axes
        (gen3dfrom1d.f): the one-point volume is the circumscribed box's while the side
        faces are measured by their corner chords, so h = min(l, sqrt(2) d) (l: element
        length, d: diameter) and ccx runs CIRC beams at about 1.3x their stable increment —
        NaN displacements.  Probed on 2.23 by bisecting the maximum increment (B32 and
        B32R, d = 10-80, l = 5-100, nu = 0-0.49, NLGEOM on and off): the limit is the
        formula with h = 1.01-1.17 d once l > d, while ccx's own increment holds for
        l <= d; RECT, PIPE and BOX sections (expanded as rectangles) run at ccx's own
        increment.  Explicit steps are therefore capped at the formula with h = min(l,
        d / sqrt(2)), the square through the section's corner nodes: at least 1.4x below
        the probed limit where ccx's estimate fails, and never above ccx's own estimate.
        Records the smallest h / c over the B32/B32R beams under a CIRC *BEAM SECTION (and
        its element), and which beams could not be sized (no isotropic *ELASTIC with a
        *DENSITY, or no radius)."""
        self._circ_explicit = None
        self._circ_explicit_issue = ""
        if not any(b.keyword == "DYNAMIC" and b.has("EXPLICIT") for b in blocks):
            return
        speeds = self._wave_speeds(blocks)
        nodes = self.geom.nodes
        best: Optional[Tuple[float, int]] = None
        missing: List[str] = []
        for b in blocks:
            if b.keyword != "BEAM SECTION" or (b.param("SECTION") or "").strip().upper() != "CIRC":
                continue
            elset = (b.param("ELSET") or "").strip()
            elems = [e for e in self.geom.elset(elset) if e in self.geom.elements
                     and self.geom.elements[e][0] in ("B32", "B32R")
                     and len(self.geom.elements[e][1]) == 3]
            if not elems:
                continue
            mat = (b.param("MATERIAL") or "").strip().upper()
            try:
                d = 2 * pf(merged_data_records(b)[0][0])        # Abaqus gives the radius
            except (IndexError, ValueError):
                d = 0.0
            c = speeds.get(mat)
            if d <= 0 or not c:
                missing.append(f"ELSET={elset} (" + ("no readable radius" if d <= 0 else
                               f"material {mat} has no isotropic *ELASTIC with a *DENSITY") + ")")
                continue
            for e in elems:
                conn = self.geom.elements[e][1]
                length = vnorm(vsub(nodes[conn[2]], nodes[conn[0]])) \
                    if conn[0] in nodes and conn[2] in nodes else 0.0
                if length > 0:
                    h = min(length, d / math.sqrt(2))
                    if best is None or h / c < best[0]:
                        best = (h / c, e)
        self._circ_explicit = best
        self._circ_explicit_issue = ", ".join(dedup_str(missing))

    def _wave_speeds(self, blocks: List[Block]) -> Dict[str, float]:
        """Material (upper-case name) -> the largest dilatational wave speed
        sqrt(E (1 - nu) / ((1 + nu) (1 - 2 nu) rho)) over its *ELASTIC and *DENSITY rows
        (all temperatures) — the speed ccx sizes an explicit increment with — for the
        materials with isotropic elasticity and a positive density."""
        moduli: Dict[str, List[float]] = {}
        densities: Dict[str, List[float]] = {}
        other: set = set()
        cur: Optional[str] = None
        for b in blocks:
            kw = b.keyword
            if kw == "MATERIAL":
                cur = (b.param("NAME") or "").strip().upper()
            elif kw in ("STEP", "NODE", "ELEMENT") or kw.endswith("SECTION"):
                cur = None
            elif cur is not None and kw == "ELASTIC":
                if (b.param("TYPE") or "ISO").strip().upper() not in ("ISO", "ISOTROPIC"):
                    other.add(cur)
                for rec in merged_data_records(b):
                    try:
                        e = pf(rec[0])
                        nu = pf(rec[1]) if len(rec) > 1 and rec[1] else 0.0
                    except (IndexError, ValueError):
                        continue
                    if self._approx and nu >= 0.5:
                        nu = 0.475                          # handle_elastic's clamp
                    if e > 0 and -1.0 < nu < 0.5:
                        moduli.setdefault(cur, []).append(e * (1 - nu) / ((1 + nu) * (1 - 2 * nu)))
            elif cur is not None and kw == "DENSITY":
                for rec in merged_data_records(b):
                    try:
                        rho = pf(rec[0])
                    except (IndexError, ValueError):
                        continue
                    if rho > 0:
                        densities.setdefault(cur, []).append(rho)
        return {m: math.sqrt(max(moduli[m]) / min(densities[m]))
                for m in moduli if m in densities and m not in other}

    def _all_wave_speeds(self, blocks: List[Block]) -> Dict[str, float]:
        """_wave_speeds, plus the orthotropic and anisotropic materials: sqrt(largest normal
        stiffness / rho), which can fall a little short of the speed ccx finds over all
        directions (anisomaxwavspd.f)."""
        speeds = dict(self._wave_speeds(blocks))
        stiff: Dict[str, float] = {}
        rho: Dict[str, float] = {}
        cur: Optional[str] = None
        for b in blocks:
            kw = b.keyword
            if kw == "MATERIAL":
                cur = (b.param("NAME") or "").strip().upper()
            elif kw in ("STEP", "NODE", "ELEMENT") or kw.endswith("SECTION"):
                cur = None
            elif cur is not None and kw == "ELASTIC":
                typ = (b.param("TYPE") or "ISO").strip().upper()
                try:
                    vals = [pf(x) for rec in merged_data_records(b) for x in rec if x != ""]
                except ValueError:
                    continue
                k = max_normal_stiffness(typ, vals)
                if k:
                    stiff[cur] = k
            elif cur is not None and kw == "DENSITY":
                try:
                    r = min(pf(rec[0]) for rec in merged_data_records(b) if rec and rec[0])
                except ValueError:
                    continue
                if r > 0:
                    rho[cur] = r
        for m, k in stiff.items():
            if m not in speeds and m in rho:
                speeds[m] = math.sqrt(k / rho[m])
        return speeds

    @staticmethod
    def _critom(proc: Optional[Block]) -> float:
        """ccx's critical frequency factor of the explicit increment for the *DYNAMIC
        ALPHA (calcstabletimeincvol.f, no damping)."""
        try:
            alpha = min(max(pf((proc.param("ALPHA") if proc else None) or "-0.05"), -1.0 / 3.0), 0.0)
        except ValueError:
            alpha = -0.05
        return 1.96 / math.sqrt(1.0 - alpha * (1.0 + alpha * (2.0 + alpha)))

    def _explicit_stable_increment(self, blocks: List[Block], proc: Optional[Block]) -> Optional[float]:
        """The increment ccx picks for an explicit step (calcstabletimeincvol.f; COURANT_FACTOR):
        0.8 / 1.3 * critom * min(h f / c) / 2 over the elements it can size; None when it
        can size none (no material with a density and elastic constants: ccx then runs the
        step in a single increment)."""
        if self._courant is None:
            self._courant = self._courant_min(blocks) or False
        if not self._courant:
            return None
        return self._critom(proc) * (0.8 / 1.3) / 2.0 * self._courant[0]

    def _courant_min(self, blocks: List[Block]) -> Optional[Tuple[float, int]]:
        """(smallest h f / c, its element) over the elements under a section whose material
        has a wave speed (_all_wave_speeds); courant_length gives h f."""
        speeds = self._all_wave_speeds(blocks)
        if not speeds:
            return None
        sized: Dict[int, Tuple[float, dict]] = {}
        for b in blocks:
            if b.keyword not in ("SOLID SECTION", "SHELL SECTION", "SHELL GENERAL SECTION",
                                 "MEMBRANE SECTION", "BEAM SECTION", "COHESIVE SECTION",
                                 "GASKET SECTION"):
                continue
            recs = [r for r in merged_data_records(b) if any(x for x in r)]

            def num(r: int, i: int) -> Optional[float]:
                try:
                    v = pf(recs[r][i])
                except (IndexError, ValueError):
                    return None
                return v if math.isfinite(v) and v > 0 else None
            mats = [(b.param("MATERIAL") or "").strip().upper()]
            sec: dict = {}
            if b.has("COMPOSITE"):                  # plies: thickness, -, material, ...
                plies = [r for r in range(len(recs)) if num(r, 0)]
                sec["t"] = sum(num(r, 0) for r in plies)
                mats = [recs[r][2].strip().upper() for r in plies if len(recs[r]) > 2]
            elif b.keyword == "BEAM SECTION":
                shape = (b.param("SECTION") or "").strip().upper()
                if shape in ("RECT", "BOX") and num(0, 0) and num(0, 1):
                    sec["rect"] = (num(0, 0), num(0, 1))
                elif shape in ("CIRC", "PIPE", "THICK PIPE") and num(0, 0):
                    sec["circ"] = 2.0 * num(0, 0)           # Abaqus gives the radius
            elif b.keyword == "SOLID SECTION":
                sec["t"] = sec["area"] = num(0, 0) or 1.0   # plane thickness, truss area
            elif b.keyword in ("COHESIVE SECTION", "GASKET SECTION"):
                sec["t"] = 1.0          # a *SOLID SECTION without data in ccx (continuum)
            else:
                sec["t"] = num(0, 0)
            cs = [speeds[m] for m in mats if m in speeds]
            if not cs:
                continue
            for e in self.geom.elset((b.param("ELSET") or "").strip()):
                sized[e] = (max(cs), sec)
        quiet = Report()
        types: Dict[str, str] = {}
        best: Optional[Tuple[float, int]] = None
        for e, (c, sec) in sized.items():
            if e not in self.geom.elements:
                continue
            typ, conn = self.geom.elements[e]
            if typ not in types:
                types[typ] = ccx_element_type(typ, quiet)
            if any(n not in self.geom.nodes for n in conn):
                continue
            hf = courant_length(types[typ], [self.geom.nodes[n] for n in conn], sec)
            if hf and (best is None or hf / c < best[0]):
                best = (hf / c, e)
        return best

    def _circ_capped_max(self, proc: Optional[Block], dtmax: Optional[float]) -> Optional[float]:
        """An explicit step's maximum increment as converted: the deck's, or the smaller cap
        _circ_explicit_increment sets for circular-section beams."""
        if self._circ_explicit is None or proc is None or proc.has("DIRECT") or \
                proc.has("DIRECT USER CONTROL"):
            return dtmax
        cap = float("%.3g" % (self._critom(proc) * 0.3 * (0.8 / 1.3) / 2.0 * self._circ_explicit[0]))
        return min(cap, dtmax) if dtmax else cap

    def _circ_explicit_increment(self, params: "OrderedDict[str, Optional[str]]",
                                 data: List[str]) -> List[str]:
        """The data line of an explicit *DYNAMIC in a deck with circular-section beams
        (_plan_circ_explicit_increment): the maximum increment (4th field, the same in both
        codes) becomes ccx's Courant estimate with h = min(l, d / sqrt(2)) unless the
        deck's own maximum or the step period is no larger.  A fixed increment (DIRECT)
        above it is only warned: ccx's mass scaling for it is sized from the same
        overestimate (probed: NaN at 1.2x and 2.4x ccx's estimate, where RECT beams run)."""
        if self._circ_explicit_issue:
            self.report.warn(f"*DYNAMIC, EXPLICIT with circular-section (CIRC) beams: ccx 2.23 "
                             f"runs them at about 1.3x their stable increment (NaN displacements, "
                             f"probed), and abq2ccx could not size a cap for "
                             f"{self._circ_explicit_issue}. Set the maximum increment (4th field "
                             f"of the *DYNAMIC data line) to at most 0.12 d / c (d: section "
                             f"diameter, c: the material's dilatational wave speed).", once=True)
        if self._circ_explicit is None:
            return data
        try:
            alpha = min(max(pf(params.get("ALPHA") or "-0.05"), -1.0 / 3.0), 0.0)
        except ValueError:
            alpha = -0.05
        critom = 1.96 / math.sqrt(1.0 - alpha * (1.0 + alpha * (2.0 + alpha)))
        h_over_c, elem = self._circ_explicit
        cap = "%.3g" % (critom * 0.3 * (0.8 / 1.3) / 2.0 * h_over_c)
        top = float(cap)
        # no data line: ccx runs the step with a period of 1
        fields = [x.strip() for x in data[0].split(",")] if data else ["", "1."]
        fields += [""] * (4 - len(fields))

        def num(i: int) -> Optional[float]:
            try:
                return pf(fields[i]) if fields[i] else 0.0
            except ValueError:
                return None

        if "DIRECT" in params:
            fixed = num(0)
            if fixed and fixed > top:
                self.report.warn(f"*DYNAMIC, EXPLICIT, DIRECT: the fixed increment {fields[0]} "
                                 f"exceeds the stable increment of the circular-section (CIRC) "
                                 f"beams (about {cap}, element {elem}). ccx 2.23 overestimates "
                                 f"it by about 1.3x, and its mass scaling for a larger fixed "
                                 f"increment is sized from the same estimate, so the run "
                                 f"diverges (NaN displacements, probed). Use a fixed increment "
                                 f"of at most {cap}, or drop DIRECT so abq2ccx caps the "
                                 f"automatic increment.", once=True)
            return data
        period, limit = num(1), num(3)
        if limit is None or 0 < limit <= top or (period is not None and 0 < period <= top):
            return data
        fields[3] = cap
        self.report.note(f"*DYNAMIC, EXPLICIT: maximum increment {cap} set for the circular-"
                         f"section (CIRC) beams (4th data field; ccx still picks a smaller "
                         f"increment where other elements need one). ccx 2.23 measures their "
                         f"expanded section by the box around the circle and runs them at about "
                         f"1.3x their stable increment: NaN displacements (probed). {cap} is "
                         f"ccx's own Courant estimate with the square through the section's "
                         f"corner nodes (smallest at element {elem}), at least 1.4x below the "
                         f"probed limit.", once=True)
        return [", ".join(fields)] + data[1:]


def dedup_str(seq: Sequence[str]) -> List[str]:
    seen, out = set(), []
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


# ---------------------------------------------------------------------------
# Assembly flattening (*PART / *INSTANCE / *ASSEMBLY -> flat blocks)
# ---------------------------------------------------------------------------

PART_PER_INSTANCE = {"SOLID SECTION", "SHELL SECTION", "SHELL GENERAL SECTION", "BEAM SECTION",
                     "MEMBRANE SECTION", "COHESIVE SECTION", "GASKET SECTION", "SURFACE SECTION",
                     "SPRING", "DASHPOT", "MASS", "GAP", "ORIENTATION", "DISTRIBUTION", "SURFACE",
                     "CONNECTOR SECTION"}
# Part-level constraint cards that reference the part's own nodes/elements/sets: each
# instance needs its own copy with offset ids and prefixed names (emitted once, raw,
# they would constrain only one instance — or the wrong nodes after renumbering).
PART_CONSTRAINT_KW = {"EQUATION", "MPC", "RIGID BODY", "NODAL THICKNESS", "TRANSFORM",
                      "COUPLING", "KINEMATIC", "DISTRIBUTING", "KINEMATIC COUPLING", "NORMAL"}


# Keywords whose members are elements, so a bare instance-qualified id (``I2.7``) takes
# the element offset, not the node offset.  Covers element/face-based loads (*DLOAD,
# *DSLOAD, *DFLUX, *DFILM, *FILM, *RADIATE), the element sections, element output and the
# element labels of a *DISTRIBUTION.
# (Nodal loads/BCs — *CLOAD, *CFLUX, *BOUNDARY — are absent, so they take the node offset.)
ELEM_REF_KW = {"DLOAD", "ELSET", "DSLOAD", "DFLUX", "DFILM", "FILM", "RADIATE",
               "SOLID SECTION", "SHELL SECTION", "BEAM SECTION", "MEMBRANE SECTION",
               "EL PRINT", "EL FILE", "ELEMENT OUTPUT", "DISTRIBUTION"}

# Parameters whose VALUE names a node set / element set / surface / node (e.g.
# ``*EL PRINT, ELSET=Part-1.body`` or ``*RIGID BODY, REF NODE=Part-1.ref``).  An
# instance-qualified value here must be resolved exactly like a data-line member;
# a plain name is already global.  (REF/ROT NODE point at a node or 1-node set.)
REF_PARAMS = {"NSET", "ELSET", "SURFACE", "SLAVE", "MASTER",
              "REF NODE", "REFNODE", "ROT NODE", "ROTNODE", "PIN NSET", "TIE NSET"}


def _split_instance_ref(tok: str, maps) -> Optional[Tuple[str, str]]:
    """Split a (possibly multi-level) instance-qualified token into ``(instance, rest)``.

    Abaqus names a member as ``Instance.set`` / ``Instance.7``; some exporters also write
    the assembly prefix (``Assembly.Instance.set``).  Return the first dot-separated
    segment that names a known instance, paired with everything after it, or ``None`` when
    no segment is a known instance — so plain names and numeric data like ``0.5`` (no
    segment is an instance) are left untouched."""
    if "." not in tok:
        return None
    segs = tok.split(".")
    for i, seg in enumerate(segs):
        if seg.upper() in maps:
            return seg.upper(), ".".join(segs[i + 1:])
    return None


def _resolve_field(field: str, maps: Dict[str, Tuple[int, int]], entity: str, namer) -> str:
    sr = _split_instance_ref(field, maps)
    if sr is None or not sr[1]:
        return field
    pre, rest = sr
    if re.fullmatch(r"[-+]?\d+", rest):
        off = maps[pre][0 if entity == "node" else 1]
        return str(int(rest) + off)
    return namer(pre, rest)   # same namer as set definitions -> names stay in sync


def mkblock(keyword: str, params=None, data=None) -> Block:
    p: "OrderedDict[str, Optional[str]]" = OrderedDict()
    for k, v in (params or []):
        p[k] = v
    return Block(keyword=keyword, params=p, data=list(data or []))


def set_block(kw: str, name: str, ids: Sequence[int]) -> Block:
    ids = dedup(ids)
    lines = compress_ids(ids)
    if lines and lines[0] == "GENERATE":
        return mkblock(kw, [(kw, name), ("GENERATE", None)], lines[1:])
    return mkblock(kw, [(kw, name)], lines)


CCX_NAME_LIMIT = 80          # verified: ccx 2.22 accepts 80-char set names, errors at >80


def make_namer(report: Report):
    """A consistent name factory that keeps CalculiX's 80-character set/surface-name
    limit (verified against ccx 2.22: names up to 80 chars resolve correctly, longer
    ones stop with 'set name too long'): the same logical name always maps to the same
    unique string, so a definition and every reference stay in sync."""
    memo: Dict[str, str] = {}
    used: set = set()

    def namer(*parts) -> str:
        base = "_".join(str(p) for p in parts).upper()
        if base in memo:
            return memo[base]
        cand = base if len(base) <= CCX_NAME_LIMIT else base[:CCX_NAME_LIMIT]
        if cand in used:
            i = 1
            while True:
                sfx = f"~{i}"
                cand = base[:CCX_NAME_LIMIT - len(sfx)] + sfx
                if cand not in used:
                    break
                i += 1
            report.warn(f"Flattened set/surface names collide within CalculiX's {CCX_NAME_LIMIT}-"
                        f"character name limit and were uniquified; verify set references.", once=True)
        elif len(base) > CCX_NAME_LIMIT:
            report.note(f"A flattened set/surface name exceeded {CCX_NAME_LIMIT} characters and was "
                        f"truncated (ccx rejects longer names).", once=True)
        used.add(cand)
        memo[base] = cand
        return cand

    def reserve(raw: str) -> None:
        """Register a name emitted verbatim (assembly-level sets/surfaces keep their
        original names) so generated names can never collide with it, and flag names
        over ccx's limit."""
        n = raw.upper()
        used.add(n)
        if len(n) > CCX_NAME_LIMIT:
            report.warn(f"An assembly-level set/surface name exceeds CalculiX's "
                        f"{CCX_NAME_LIMIT}-character limit and will be rejected by ccx "
                        f"('set name too long'); shorten it in the source deck.", once=True)

    namer.reserve = reserve
    return namer


def _partition_assembly(blocks: List[Block]):
    """Split a *PART/*INSTANCE/*ASSEMBLY deck into its sections via a small state machine:
    parts (name -> blocks), instances (dicts), assembly-level blocks, and the pre-/post-
    assembly top-level blocks."""
    parts: "OrderedDict[str, List[Block]]" = OrderedDict()
    instances: List[dict] = []
    assembly_blocks: List[Block] = []
    pre: List[Block] = []
    post: List[Block] = []
    state = None
    seen_assembly = False

    for b in blocks:
        kw = b.keyword
        if kw == "PART":
            name = (b.param("NAME") or "").upper()
            parts[name] = []
            state = ("PART", name)
            continue
        if kw == "END PART":
            state = None
            continue
        if kw == "ASSEMBLY":
            state = ("ASM", None)
            seen_assembly = True
            continue
        if kw == "END ASSEMBLY":
            state = None
            continue
        if kw == "INSTANCE":
            inst = {"name": (b.param("NAME") or "").upper(),
                    "part": (b.param("PART") or "").upper(),
                    "data": list(b.data), "extra": []}
            instances.append(inst)
            state = ("INST", inst)
            continue
        if kw == "END INSTANCE":
            state = ("ASM", None)
            continue
        if state is None:
            (post if seen_assembly else pre).append(b)
        elif state[0] == "PART":
            parts[state[1]].append(b)
        elif state[0] == "ASM":
            assembly_blocks.append(b)
        elif state[0] == "INST":
            state[1]["extra"].append(b)
    return parts, instances, assembly_blocks, pre, post


def _emit_part_global_data(parts) -> List[Block]:
    """Each part's 'global once' model data (materials etc.) — not the mesh (consumed
    per instance) and not the per-instance section cards."""
    out: List[Block] = []
    for pblocks in parts.values():
        for b in pblocks:
            if b.keyword in GEOM_KW or b.keyword in PART_PER_INSTANCE or \
                    b.keyword in PART_CONSTRAINT_KW:
                continue
            out.append(b)
    return out


def _fmt_component(x: float) -> str:
    """A derived coordinate/direction component, with rounding noise (|x| < 1e-12 of a
    unit-ish vector, e.g. cos 90 deg) printed as an exact 0."""
    return "0" if abs(x) < 1e-12 else f"{x:.9g}"


def _fmt_unit(x: float) -> str:
    """A unit-vector component to 15 decimals, trailing zeros dropped: at most 18 characters,
    since ccx 2.23 reads only the first 20 of a data field (probed on *TRANSFORM: a longer
    number is cut — 6.000000000000000E-01 is read as 6 — or stops ccx when the cut is no
    number)."""
    s = f"{x:.15f}".rstrip("0")
    return "0." if s in ("0.", "-0.") else s


def _remap_part_constraint(b: Block, prefix: str, namer, node_off: int, elem_off: int,
                           rotv, rotp) -> Block:
    """One instance's copy of a part-level constraint card: numeric node/element ids
    offset, set/surface names prefixed exactly like the instance's own sets, direction
    vectors (*NORMAL, rectangular *TRANSFORM) rotated and axis points (cylindrical /
    spherical *TRANSFORM) moved with the instance (``rotv`` / ``rotp``)."""
    def node(tok: str) -> str:
        if re.fullmatch(r"[-+]?\d+", tok):
            return str(int(tok) + node_off) if int(tok) > 0 else tok
        return namer(prefix, tok) if tok else tok

    def elem(tok: str) -> str:
        if re.fullmatch(r"[-+]?\d+", tok):
            return str(int(tok) + elem_off) if int(tok) > 0 else tok
        return namer(prefix, tok) if tok else tok

    kw = b.keyword
    p: "OrderedDict[str, Optional[str]]" = OrderedDict(b.params)
    for k in ("REF NODE", "REFNODE", "ROT NODE", "ROTNODE"):
        if p.get(k):
            p[k] = node(p[k].strip())
    for k in ("NSET", "PIN NSET", "TIE NSET", "SURFACE"):
        if p.get(k):
            p[k] = namer(prefix, p[k].strip())
    if p.get("ELSET"):
        p["ELSET"] = namer(prefix, p["ELSET"].strip())
    if kw == "COUPLING" and p.get("CONSTRAINT NAME"):
        p["CONSTRAINT NAME"] = namer(prefix, p["CONSTRAINT NAME"].strip())
    data: List[str] = []
    if kw == "EQUATION":
        pending = 0                                  # terms still to read for this equation
        for ln in b.data:
            f = [x.strip() for x in ln.split(",")]
            while f and f[-1] == "":
                f.pop()
            if pending == 0:
                data.append(ln)                      # term count line
                try:
                    pending = int(float(f[0]))
                except (IndexError, ValueError):
                    pending = 0
                continue
            for i in range(0, len(f) - 2, 3):
                f[i] = node(f[i])
            pending -= len(f) // 3
            data.append(", ".join(f))
    elif kw in ("MPC", "NODAL THICKNESS", "KINEMATIC COUPLING", "NORMAL"):
        for ln in b.data:
            f = [x.strip() for x in ln.split(",")]
            if kw == "MPC":
                f = f[:1] + [node(x) if x else x for x in f[1:]]
            elif kw == "NORMAL":
                if len(f) >= 5:
                    try:
                        v = rotv((pf(f[2]), pf(f[3]), pf(f[4])))
                        f[2:5] = [_fmt_component(x) for x in v]
                    except ValueError:
                        pass
                if len(f) >= 2:
                    f[0], f[1] = elem(f[0]), node(f[1])
            elif f:
                f[0] = node(f[0])
            data.append(", ".join(f))
    elif kw == "TRANSFORM" and b.data:
        move = rotv if (b.param("TYPE") or "R").strip().upper().startswith("R") else rotp
        try:
            v = [pf(x) for x in b.data[0].split(",") if x.strip()]
            if len(v) >= 6:
                a, c = move((v[0], v[1], v[2])), move((v[3], v[4], v[5]))
                data = [", ".join(_fmt_component(x) for x in (*a, *c))] + list(b.data[1:])
            else:
                data = list(b.data)
        except ValueError:
            data = list(b.data)
    else:
        data = list(b.data)
    return Block(kw, p, data)


def _instance_transform(inst: dict, report: Report) -> Tuple[Vec, Optional[Tuple[Vec, Vec, float]]]:
    """Parse an *INSTANCE positioning block: a translation line and an optional rotation
    line (point a, point b, angle).  Returns (translation, rotation-or-None)."""
    T: Vec = (0.0, 0.0, 0.0)
    rot = None
    dl = [ln for ln in inst["data"] if ln.strip()]
    try:
        if dl:
            v = [pf(x) for x in numeric_fields(dl[0])]
            if len(v) >= 3:
                T = (v[0], v[1], v[2])
        if len(dl) > 1:
            v = [pf(x) for x in numeric_fields(dl[1])]
            if len(v) >= 7:
                rot = ((v[0], v[1], v[2]), (v[3], v[4], v[5]), v[6])
    except ValueError:
        report.warn(f"*INSTANCE {inst['name']}: could not fully parse the transform "
                    f"line(s); any unparsed translation/rotation is dropped — verify "
                    f"positioning.", once=True)
    if rot:
        report.warn(f"*INSTANCE {inst['name']} is rotated; node coordinates, *ORIENTATION axes "
                    f"(also per-element *DISTRIBUTION axes), beam n1 directions and part-level "
                    f"*NORMAL/*TRANSFORM data are transformed with it — verify material "
                    f"directions.", once=True)
    return T, rot


def _emit_instance(inst: dict, parts, namer, report: Report, options,
                   gmax_node: int, gmax_elem: int):
    """Emit one *INSTANCE as flat global geometry: build its mesh (from the *Part and/or
    the instance's own blocks — CAE 'dependent' instances keep the mesh in the *Part,
    'independent' ones put it inside *Instance...*End Instance), offset node/element ids
    past the running maxima, apply the instance translation+rotation, and remap its
    sets/sections/surfaces.  Returns ``(blocks, new_gmax_node, new_gmax_elem,
    (node_off, elem_off))`` or ``None`` if the instance has no mesh."""
    geo_conv = Converter(report, options)
    geo_conv.build_geometry(parts.get(inst["part"], []) + inst["extra"])
    geo = geo_conv.geom
    if not geo.nodes and not geo.elements:
        report.warn(f"*INSTANCE {inst['name']}: no mesh found in part {inst['part']} or the "
                    f"instance itself; skipped.")
        return None
    node_off, elem_off = gmax_node, gmax_elem
    out: List[Block] = []
    T, rot = _instance_transform(inst, report)

    ndata = []
    for nid, (x, y, z) in geo.nodes.items():
        p = vadd((x, y, z), T)
        if rot:
            p = rotate_about_axis(p, rot[0], rot[1], rot[2])
        gid = nid + node_off
        ndata.append(f"{gid}, {fmt_coord(p[0])}, {fmt_coord(p[1])}, {fmt_coord(p[2])}")
        gmax_node = max(gmax_node, gid)
    out.append(mkblock("NODE", [("NSET", namer(inst["name"]))], ndata))

    by_type: "OrderedDict[str, List[Tuple[int, List[int]]]]" = OrderedDict()
    for eid, (typ, conn) in geo.elements.items():
        by_type.setdefault(typ, []).append((eid, conn))
    for typ, items in by_type.items():
        edata = []
        for eid, conn in items:
            gid = eid + elem_off
            edata.extend(reflow([str(gid)] + [str(c + node_off) for c in conn], MAX_ENTRIES_PER_LINE))
            gmax_elem = max(gmax_elem, gid)
        out.append(mkblock("ELEMENT", [("TYPE", typ), ("ELSET", namer(inst["name"], "ALL"))], edata))
    conns: "OrderedDict[str, List[str]]" = OrderedDict()      # part-level connector elements
    for eid, (typ, a, c) in geo_conv._conn.items():
        conns.setdefault(typ, []).append(", ".join(
            [str(eid + elem_off)] + ["" if n is None else str(n + node_off) for n in (a, c)]))
        gmax_elem = max(gmax_elem, eid + elem_off)
    for typ, edata in conns.items():
        out.append(mkblock("ELEMENT", [("TYPE", typ)], edata))

    for sname, ids in geo.nsets.items():
        out.append(set_block("NSET", namer(inst["name"], sname), [i + node_off for i in ids]))
    for sname, ids in geo.elsets.items():
        out.append(set_block("ELSET", namer(inst["name"], sname), [i + elem_off for i in ids]))

    # per-instance sections / orientations / surfaces (remap names).  Use .get() (as the
    # build_geometry call above does): an independent instance can carry its own mesh while
    # referencing a PART= name that was never declared (typo / un-included file) — index it
    # raw and one bad instance would KeyError out of the whole conversion.
    prefix = inst["name"]
    if rot:
        axis = vsub(rot[1], rot[0])
        rotv = lambda v: rotate_about_axis(v, (0.0, 0.0, 0.0), axis, rot[2])  # noqa: E731
    else:
        rotv = lambda v: v                                                     # noqa: E731

    def rotp(p: Vec) -> Vec:                    # a point moves exactly like a node
        q = vadd(p, T)
        return rotate_about_axis(q, rot[0], rot[1], rot[2]) if rot else q

    # the part's orientation distributions move like the axes of the *ORIENTATION that
    # names them (None: unchanged by this instance's transform)
    inst_blocks = parts.get(inst["part"], []) + inst["extra"]
    dists = {(b.param("NAME") or "").strip().upper() for b in inst_blocks if b.keyword == "DISTRIBUTION"}
    dist_move = {}
    for b in inst_blocks:
        ref = b.data[0].split(",")[0].strip().upper() if b.keyword == "ORIENTATION" and b.data else ""
        if ref in dists:
            rect = (b.param("SYSTEM") or "RECTANGULAR").upper().startswith("RECT")
            dist_move[ref] = (rotv if rot else None) if rect else (rotp if rot or any(T) else None)
    for b in inst_blocks:
        if b.keyword in ("SOLID SECTION", "SHELL SECTION", "SHELL GENERAL SECTION", "BEAM SECTION",
                         "MEMBRANE SECTION", "COHESIVE SECTION", "GASKET SECTION", "SURFACE SECTION",
                         "SPRING",
                         "DASHPOT", "MASS", "GAP"):
            nb = _remap_named(b, prefix, ("ELSET", "ORIENTATION"), namer)
            if b.has("COMPOSITE"):
                # a ply line (thickness, points, material, angle or orientation, ply name)
                # can name one of the part's orientations: this instance's copy
                for i, ln in enumerate(nb.data):
                    f = ln.split(",")
                    o = f[3].strip() if len(f) > 3 else ""
                    if o and not re.fullmatch(r"[-+]?(\d+\.?\d*|\.\d+)([EeDd][-+]?\d+)?", o):
                        f[3] = " " + namer(prefix, o)
                        nb.data[i] = ",".join(f)
            if rot and b.keyword == "BEAM SECTION" and len(nb.data) > 1:
                # the second data line is the beam's n1 direction: it turns with the part
                try:
                    v = [pf(x) for x in nb.data[1].split(",") if x.strip()]
                    if len(v) >= 3:
                        nb.data[1] = ", ".join(_fmt_component(x) for x in rotv((v[0], v[1], v[2])))
                except ValueError:
                    pass
            out.append(nb)
        elif b.keyword == "ORIENTATION":
            nb = _remap_named(b, prefix, ("NAME",), namer)
            system = (b.param("SYSTEM") or "RECTANGULAR").upper()
            ref = nb.data[0].split(",")[0].strip() if nb.data else ""
            if ref.upper() in dists:
                # the axes come from the part's *DISTRIBUTION: name this instance's copy
                nb.data[0] = ", ".join([namer(prefix, ref)] + nb.data[0].split(",")[1:])
            elif (rot or any(T)) and nb.data and \
                    (b.param("DEFINITION") or "COORDINATES").upper().startswith("COORD"):
                # rectangular axes are direction points measured from the origin (or from
                # c on a 9-value line): they only rotate.  Cylindrical a, b are points on
                # the axis: they move with the part like nodes.
                move = rotv if system.startswith("RECT") else rotp
                try:
                    v = [pf(x) for x in nb.data[0].split(",") if x.strip()]
                    if len(v) >= 6 and (rot or move is rotp):
                        pts = [move(tuple(v[i:i + 3])) for i in range(0, len(v) - 2, 3)]
                        nb.data[0] = ", ".join(_fmt_component(x) for p in pts for x in p)
                except ValueError:
                    pass
            out.append(nb)
        elif b.keyword == "DISTRIBUTION":
            name = (b.param("NAME") or "").strip().upper()
            move = dist_move[name] if name in dist_move else (rotv if rot else None)
            out.append(_remap_distribution(b, prefix, namer, elem_off, move))
        elif b.keyword == "CONNECTOR SECTION":
            nb = _remap_named(b, prefix, ("ELSET",), namer)
            if len(nb.data) > 1:                    # local orientations of nodes a and b
                nb.data[1] = ", ".join(namer(prefix, x.strip()) if x.strip() else ""
                                       for x in nb.data[1].split(","))
            out.append(nb)
        elif b.keyword == "SURFACE":
            out.append(_remap_surface(b, prefix, namer, node_off, elem_off))
        elif b.keyword in PART_CONSTRAINT_KW:
            out.append(_remap_part_constraint(b, prefix, namer, node_off, elem_off, rotv, rotp))
    return out, gmax_node, gmax_elem, (node_off, elem_off)


def _emit_assembly_blocks(assembly_blocks: List[Block], maps, namer) -> List[Block]:
    """Translate assembly-level sets / surfaces / constraints, resolving instance-qualified
    members (``Instance.id`` / ``Instance.setname``) to the flat global numbering."""
    def resolve(tok: str, entity: str = "node"):
        sr = _split_instance_ref(tok, maps)
        if sr is not None and sr[1]:
            iname, rest = sr
            if re.fullmatch(r"[-+]?\d+", rest):
                return ("id", int(rest) + maps[iname][0 if entity == "node" else 1])
            return ("name", namer(iname, rest))
        return ("raw", tok)

    out: List[Block] = []
    for b in assembly_blocks:
        kw = b.keyword
        if kw in ("NSET", "ELSET"):
            name = (b.param("NSET") if kw == "NSET" else b.param("ELSET")) or ""
            namer.reserve(name)
            inst = b.param("INSTANCE")
            off = None
            if inst and inst.upper() in maps:
                off = maps[inst.upper()][0 if kw == "NSET" else 1]
            gen = b.has("GENERATE")
            ids: List[int] = []
            names: List[str] = []
            for rec in merged_data_records(b):
                f = [x for x in rec if x != ""]
                if not f:
                    continue
                if gen:
                    base = expand_generate(f)
                    ids.extend(x + (off or 0) for x in base)
                else:
                    for tok in f:
                        if re.fullmatch(r"[-+]?\d+", tok) and off is not None:
                            ids.append(int(tok) + off)
                        else:
                            kind, val = resolve(tok, "node" if kw == "NSET" else "elem")
                            (ids if kind == "id" else names).append(val)
            if ids:
                out.append(set_block(kw, name.upper(), ids))
            if names:
                out.append(mkblock(kw, [(kw, name.upper())], [", ".join(str(n) for n in names)]))
        elif kw == "SURFACE":
            if b.param("NAME"):
                namer.reserve(b.param("NAME"))
            # members of an element surface are element refs, of a node surface node refs
            surf_ent = "node" if (b.param("TYPE") or "ELEMENT").upper().startswith("NODE") else "elem"
            data = []
            for rec in merged_data_records(b):
                f = [x for x in rec if x != ""]
                if not f:
                    continue
                kind, val = resolve(f[0], surf_ent)
                data.append(", ".join([str(val)] + f[1:]))
            out.append(Block("SURFACE", OrderedDict(b.params), data))
        else:
            out.append(b)
    return out


def _resolve_qualified_refs(out: List[Block], maps, namer) -> None:
    """Final pass (in place): rewrite any leftover instance-qualified references to global
    ids/names, now that all instance offsets are known.  Covers both data-line members
    (e.g. a ``*CLOAD`` on ``I2.7``) and the set/surface-naming *parameters* of step/model/
    output cards (e.g. ``*EL PRINT, ELSET=I2.body`` -> ``ELSET=I2_BODY``)."""
    for blk in out:
        if blk.keyword == "NODE":
            continue
        # ELEMENT blocks: assembly-level spring/mass/gap elements may write their
        # connectivity as instance-qualified node refs ("1, Part-1-1.5, Part-2-1.3");
        # resolve those to global node ids (the leading element id is plain numeric and
        # is left untouched) so the element registers instead of being skipped.  Types
        # with NO ccx equivalent (COH*, JOINTC, ...) are deliberately left unresolved:
        # they then drop out via the non-numeric-connectivity skip, which keeps the rest
        # of the deck solvable instead of feeding ccx a fatal unknown element.  Connector
        # elements are resolved: the converter writes them as constraints.
        if blk.keyword == "ELEMENT":
            etyp = (blk.param("TYPE") or "").upper()
            if (etyp.startswith(UNSUPPORTED_ELEM_PREFIXES) and etyp not in CONN_TYPES) or \
                    etyp in ("JOINTC",):
                continue
            entity = "node"                       # connectivity references nodes
        elif blk.keyword == "SURFACE":            # members follow the surface's TYPE
            entity = "node" if (blk.param("TYPE") or "ELEMENT").upper().startswith("NODE") else "elem"
        else:
            entity = "elem" if blk.keyword in ELEM_REF_KW else "node"
        # (a) parameters that name a set/surface.  Only dotted values whose prefix is a
        #     known instance are touched, so a definition's own name (LOADED, I2_BODY) and
        #     unrelated params (MATERIAL=, NAME=) are left untouched.
        for k, v in list(blk.params.items()):
            if v and "." in v and k in REF_PARAMS:
                ent = "elem" if ("ELSET" in k or "ELEMENT" in k) else \
                      "node" if ("NSET" in k or "NODE" in k) else entity
                blk.params[k] = _resolve_field(v, maps, ent, namer)
        # (b) instance-qualified members in data lines.
        if not blk.data:
            continue
        rewritten, changed = [], False
        for line in blk.data:
            fields = [_resolve_field(p.strip(), maps, entity, namer) for p in line.split(",")]
            joined = ", ".join(fields)
            changed = changed or joined != line
            rewritten.append(joined)
        if changed:
            blk.data = rewritten


def _partition_assembly_geometry(assembly_blocks: List[Block]):
    """Assembly-level ``*NODE``/``*ELEMENT`` cards (Abaqus/CAE reference points, connector
    or mass elements) live in their own id space that must NOT be overwritten by the
    flattened instances.  Split them out so they can be emitted first, keeping their
    original ids, with the instances numbered above them.  Returns ``(geometry_blocks,
    max_node_id, max_elem_id, remaining_assembly_blocks)``."""
    geom: List[Block] = []
    remaining: List[Block] = []
    max_node = max_elem = 0
    for b in assembly_blocks:
        if b.keyword not in ("NODE", "ELEMENT"):
            remaining.append(b)
            continue
        geom.append(b)
        for rec in merged_data_records(b):
            f = [x for x in rec if x != ""]
            if not f:
                continue
            try:
                first = int(float(f[0]))
            except ValueError:               # instance-qualified connectivity, blank, etc.
                continue
            if b.keyword == "NODE":
                max_node = max(max_node, first)
            else:
                max_elem = max(max_elem, first)
    return geom, max_node, max_elem, remaining


def flatten_assembly(blocks: List[Block], report: Report, options) -> List[Block]:
    """``*PART``/``*INSTANCE``/``*ASSEMBLY`` -> one flat, globally-numbered mesh (ccx has
    no assembly concept).  Orchestrates the phases, each a helper above: partition the
    deck -> emit per-part global data -> emit assembly-level nodes/elements -> emit each
    instance's geometry (id-offset + transform) -> translate assembly-level sets/surfaces/
    constraints -> resolve leftover instance-qualified references."""
    report.warn("Model uses *PART/*INSTANCE/*ASSEMBLY. Flattened to a single global mesh "
                "(best-effort) — verify node/element renumbering and instance transforms.", once=True)
    namer = make_namer(report)
    parts, instances, assembly_blocks, pre, post = _partition_assembly(blocks)

    out: List[Block] = list(pre)
    out.extend(_emit_part_global_data(parts))

    # Assembly-level *NODE/*ELEMENT (CAE reference points etc.) keep their original ids and
    # are emitted BEFORE the instances; the instances are then numbered above them so an
    # assembly node id can never overwrite a part/instance node id.
    asm_geom, asm_max_node, asm_max_elem, assembly_blocks = _partition_assembly_geometry(assembly_blocks)
    if asm_geom:
        report.warn("Assembly-level *NODE/*ELEMENT (e.g. CAE reference points) kept with their "
                    "original ids; instance meshes are numbered above them so ids do not collide.",
                    once=True)
    out.extend(asm_geom)

    maps: Dict[str, Tuple[int, int]] = {}      # instance -> (node_off, elem_off)
    gmax_node, gmax_elem = asm_max_node, asm_max_elem
    for inst in instances:
        res = _emit_instance(inst, parts, namer, report, options, gmax_node, gmax_elem)
        if res is None:
            continue
        inst_blocks, gmax_node, gmax_elem, offs = res
        out.extend(inst_blocks)
        maps[inst["name"]] = offs

    out.extend(_emit_assembly_blocks(assembly_blocks, maps, namer))
    out.extend(post)
    _resolve_qualified_refs(out, maps, namer)
    return out


def _remap_distribution(b: Block, prefix: str, namer, elem_off: int, move) -> Block:
    """One instance's copy of a part-level *DISTRIBUTION: its name prefixed like the
    instance's other names, element labels offset, element-set labels prefixed, and the
    a, b[, c] points of every line moved with the instance by ``move`` (None: unchanged)."""
    p: "OrderedDict[str, Optional[str]]" = OrderedDict(b.params)
    if p.get("NAME"):
        p["NAME"] = namer(prefix, p["NAME"].strip())
    data = []
    for rec in merged_data_records(b):
        if not any(rec):
            continue
        label, vals = rec[0], rec[1:]
        if re.fullmatch(r"[-+]?\d+", label):
            label = str(int(label) + elem_off) if int(label) > 0 else label
        elif label:
            label = namer(prefix, label)
        if move is not None:
            try:
                v = [pf(x) for x in vals if x != ""]
            except ValueError:
                v = []
            if len(v) in (6, 9):
                vals = [_fmt_component(x) for i in range(0, len(v), 3) for x in move(tuple(v[i:i + 3]))]
        data.append(", ".join([label] + vals))
    return Block(b.keyword, p, data)


def _remap_named(b: Block, prefix: str, keys: Sequence[str], namer) -> Block:
    p: "OrderedDict[str, Optional[str]]" = OrderedDict(b.params)
    for k in keys:
        if k in p and p[k]:
            p[k] = namer(prefix, p[k])
    return Block(b.keyword, p, list(b.data))


def _remap_surface(b: Block, prefix: str, namer, node_off: int, elem_off: int) -> Block:
    p: "OrderedDict[str, Optional[str]]" = OrderedDict(b.params)
    if "NAME" in p and p["NAME"]:
        p["NAME"] = namer(prefix, p["NAME"])
    is_node = (b.param("TYPE") or "ELEMENT").upper().startswith("NODE")
    data = []
    for rec in merged_data_records(b):
        f = [x for x in rec if x != ""]
        if not f:
            continue
        # a member may be a bare id (offset it) or a set name (remap it)
        if re.fullmatch(r"[-+]?\d+", f[0]):
            first = str(int(f[0]) + (node_off if is_node else elem_off))
        else:
            first = namer(prefix, f[0])
        data.append(", ".join([first] + f[1:]))
    return Block("SURFACE", p, data)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def default_output(input_path: str) -> str:
    stem, _ = os.path.splitext(input_path)
    return stem + "_ccx.inp"


class Options:
    """Conversion options (the CLI argparse namespace also satisfies this contract)."""

    def __init__(self, solid_dof: bool = False, approximate: bool = False) -> None:
        self.solid_dof = solid_dof
        self.approximate = approximate


class Result:
    """Outcome of a programmatic conversion (see convert_file / convert_text)."""

    def __init__(self, text: str, body: List[str], report: Report, geometry: Geometry) -> None:
        self.text = text          # full deck including the header comments
        self.body = body          # deck lines without the header
        self.report = report
        self.geometry = geometry

    @property
    def ok(self) -> bool:
        return bool(self.body)


def convert_file(path: str, solid_dof: bool = False, approximate: bool = False) -> Result:
    """One-call module API: convert an Abaqus deck file to CalculiX text."""
    report = Report()
    blocks = read_blocks(path, report)
    conv = Converter(report, Options(solid_dof, approximate))
    body = conv.convert(blocks) if blocks else []
    text = ("\n".join(report.header_comment_lines() + body) + "\n") if body else ""
    return Result(text, body, report, conv.geom)


def convert_text(text: str, solid_dof: bool = False, base_dir: str = ".",
                 approximate: bool = False) -> Result:
    """Convert Abaqus deck text; ``*INCLUDE`` paths resolve relative to ``base_dir``."""
    import tempfile
    fd, p = tempfile.mkstemp(suffix=".inp", dir=base_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        return convert_file(p, solid_dof, approximate)
    finally:
        os.unlink(p)


def find_ccx(override: Optional[str] = None) -> Tuple[Optional[str], Dict[str, str]]:
    """Locate a CalculiX executable: --ccx/$CCX override, PATH, then known bundle spots
    (incl. FreeCAD's copy, whose dylibs need the ../lib fallback path)."""
    for cand in ([override] if override else []) + \
                ([os.environ["CCX"]] if not override and os.environ.get("CCX") else []):
        if os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand, {}
        return None, {}
    for name in ("ccx", "ccx_2.23", "ccx_2.22", "ccx_2.21", "CalculiX"):
        p = shutil.which(name)
        if p:
            return p, {}
    candidates = (glob.glob("/Applications/FreeCAD*.app/Contents/Resources/bin/ccx")
                  + glob.glob("/usr/local/bin/ccx*") + glob.glob("/opt/homebrew/bin/ccx*")
                  + glob.glob("/opt/local/bin/ccx*"))
    for c in candidates:
        if os.path.isfile(c) and os.access(c, os.X_OK):
            env = {}
            libdir = os.path.join(os.path.dirname(os.path.dirname(c)), "lib")
            if os.path.isdir(libdir):
                env["DYLD_FALLBACK_LIBRARY_PATH"] = libdir
                env["LD_LIBRARY_PATH"] = libdir
            return c, env
    return None, {}


# What a crashing ccx prints after (or instead of) a clean finish: unpatched builds can
# print "Job finished" and then abort in glibc's free() (issue #3).
CCX_ABORT_SIGNS = ("free(): ", "double free", "malloc(): ", "corrupted size", "Aborted",
                   "Segmentation fault")
_CCX_STEP_RE = re.compile(r"^\s*STEP\s+\d+\s*$", re.M)
# A solution that went to NaN (an unstable explicit increment, say) still ends with "Job
# finished" and exit 0; only the results show it: Fortran writes NaN/Infinity to the .dat,
# C writes NAN/INF to the .frd.
_NONFINITE_RE = re.compile(rb"(?i)(?<![a-z])[+-]?(?:nan|inf(?:inity)?)(?![a-z])")
_DAT_LINE_RE = re.compile(rb"\s*(?:(?P<row>[+-]?(?:\.?\d|(?i:(?:nan|inf(?:inity)?)(?![a-z]))))|[A-Za-z])")
_DAT_TABLE_RE = re.compile(rb"\s*(?:[A-Z] ){3}")      # "S T E P", "E I G E N V A L U E ..."


def _squash(line: bytes, limit: int = 100) -> str:
    text = " ".join(line.decode("latin-1").split())
    return text if len(text) <= limit else text[:limit - 3] + "..."


def _dat_nonfinite(fh) -> Optional[str]:
    # Only the rows of print blocks, whose headings end "... and time t" (*NODE, *EL,
    # *CONTACT and *SECTION PRINT; a section print's sub-headings stay in its block), up
    # to the next spaced-out heading of ccx's own: its tables may hold an Inf that is no
    # divergence, e.g. an undamped *STEADY STATE DYNAMICS mode's participation factor at
    # its eigenfrequency.
    header = None
    for ln in fh:
        m = _DAT_LINE_RE.match(ln)
        if not m:                                   # a blank line
            continue
        if not m.group("row"):                      # a heading
            if b" and time " in ln:
                header = ln
            elif _DAT_TABLE_RE.match(ln):
                header = None
        elif header and (b"n" in ln or b"N" in ln) and _NONFINITE_RE.search(ln):
            return f"{_squash(header)}: {_squash(ln)}"
    return None


def _frd_nonfinite(fh) -> Optional[str]:
    block, at = "", ""
    for ln in fh:
        if ln.startswith((b" -1", b" -2")):         # one node's values
            if (b"N" in ln or b"n" in ln) and _NONFINITE_RE.search(ln):
                return f"{block} at {at}: {_squash(ln[3:])}"
        elif ln.startswith(b" -4"):                 # " -4  DISP        4    1"
            block = _squash(ln[3:]).split(" ")[0]
        elif ln.startswith(b"  100C"):              # "  100CL  101 1.66826E-03 ..."
            at = _squash(ln[12:24])
        elif ln.startswith(b"    2C"):
            block, at = "node coordinates", "the mesh"
    return None


def ccx_nonfinite_result(job: str) -> Optional[str]:
    """Where ccx's results for ``job`` (its path without the extension) first hold a NaN
    or Inf: a value row of the .dat (*NODE PRINT, *EL PRINT, ...) or a node's values in
    a .frd result block, as "<file>: <where>: <values>"; None if all are finite."""
    for ext, scan in ((".dat", _dat_nonfinite), (".frd", _frd_nonfinite)):
        try:
            with open(job + ext, "rb") as fh:
                hit = scan(fh)
        except OSError:
            continue
        if hit:
            return f"{os.path.basename(job)}{ext}: {hit}"
    return None


def classify_ccx_run(returncode, stdout: str, stderr: str, job: Optional[str] = None) -> str:
    """Classify a finished ccx run:

    * ``"solved"``    - exit 0, "Job finished", no ``*ERROR``, no crash/abort message, at
                        least one analysis STEP executed, and (given ``job``, the job's
                        path without the extension) every value its .dat print blocks
                        and .frd result blocks hold is finite;
    * ``"nonfinite"`` - the same, but the results hold NaN or Inf: ccx finishes a
                        diverged solution like any other (see ccx_nonfinite_result);
    * ``"accepted"``  - no STEP ran (a mesh-only deck ccx only parsed), otherwise clean;
    * ``"failed"``    - anything else, including a crash after "Job finished".

    The per-iteration "no convergence" message is normal in nonlinear solves and is not
    a failure; a run that really gives up prints ``*ERROR``."""
    if returncode != 0 or "Job finished" not in stdout:
        return "failed"
    if "*ERROR" in stdout or "*ERROR" in stderr:
        return "failed"
    if any(s in stdout or s in stderr for s in CCX_ABORT_SIGNS):
        return "failed"
    if not _CCX_STEP_RE.search(stdout):
        return "accepted"
    return "nonfinite" if job and ccx_nonfinite_result(job) else "solved"


def run_ccx(out_path: str, override: Optional[str], quiet: bool) -> int:
    """Run CalculiX on a converted deck; 0 if the analysis solves with finite results (or
    ccx accepts a mesh-only deck that has nothing to solve), 1 otherwise."""
    exe, extra_env = find_ccx(override)
    if not exe:
        sys.stderr.write("abq2ccx: no CalculiX executable found (searched --ccx/$CCX, PATH, the "
                         "FreeCAD bundle, Homebrew/MacPorts); install ccx or pass --ccx PATH.\n")
        return 1
    env = dict(os.environ)
    env.update(extra_env)
    stem = os.path.splitext(os.path.basename(out_path))[0]
    cwd = os.path.dirname(os.path.abspath(out_path))
    if not quiet:
        sys.stderr.write(f"abq2ccx: running {exe} {stem}\n")
    try:
        p = subprocess.run([exe, stem], cwd=cwd, env=env, capture_output=True, text=True)
    except OSError as exc:
        sys.stderr.write(f"abq2ccx: could not run ccx: {exc}\n")
        return 1
    out = p.stdout + p.stderr
    if not quiet:
        sys.stderr.write(out)
    job = os.path.join(cwd, stem)
    status = classify_ccx_run(p.returncode, p.stdout, p.stderr, job)
    if status == "accepted":
        sys.stderr.write("abq2ccx: ccx accepted the deck, but it has no analysis step — "
                         "nothing was solved.\n")
        return 0
    if status == "nonfinite":
        sys.stderr.write(f"abq2ccx: ccx finished, but its results hold NaN/Inf values (the "
                         f"solution diverged): {ccx_nonfinite_result(job)}\n")
        return 1
    if status == "failed":
        errs = [ln.strip() for ln in out.splitlines() if "*ERROR" in ln][:3]
        aborts = [s.strip() for s in CCX_ABORT_SIGNS if s in out]
        why = (" | ".join(errs) if errs else
               f"exit code {p.returncode}" if p.returncode != 0 else
               f"crash after 'Job finished' ({aborts[0]})" if aborts else
               "no 'Job finished'")
        sys.stderr.write(f"abq2ccx: ccx did NOT finish cleanly: {why}\n")
        return 1
    return 0


def _convert_one(path: str, args) -> int:
    report = Report()
    blocks = read_blocks(path, report)
    if not blocks:
        if not os.path.exists(path):
            sys.stderr.write(f"abq2ccx: cannot read {path}: no such file\n")
        else:
            sys.stderr.write(f"abq2ccx: no Abaqus keywords found in {path} "
                             f"(is it an Abaqus .inp deck?)\n")
            msg = report.text().strip()
            if msg and not msg.startswith("No conversion issues"):
                sys.stderr.write(msg + "\n")
        return 1
    conv = Converter(report, args)
    try:
        body = conv.convert(blocks)
    except Exception as exc:                # surface a clean message, not a bare traceback
        sys.stderr.write(f"abq2ccx: conversion failed for {path} ({type(exc).__name__}: {exc}).\n"
                         f"Please report this deck. Run with PYTHONFAULTHANDLER for a traceback.\n")
        return 4

    if args.output:
        out_path = args.output
    else:
        out_path = default_output(path)
        if args.outdir:
            try:
                os.makedirs(args.outdir, exist_ok=True)
            except OSError as exc:
                sys.stderr.write(f"abq2ccx: cannot create --outdir {args.outdir}: {exc}\n")
                return 1
            out_path = os.path.join(args.outdir, os.path.basename(out_path))
    text = "\n".join(report.header_comment_lines() + body) + "\n"

    wrote = False
    if not args.check:
        try:
            with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
            wrote = True
        except OSError as exc:
            sys.stderr.write(f"abq2ccx: cannot write {out_path}: {exc}\n")
            return 1
        if not args.no_log:
            log_path = os.path.splitext(out_path)[0] + ".log"
            try:
                with open(log_path, "w", encoding="utf-8", newline="\n") as fh:
                    fh.write(report.text())
            except OSError as exc:
                sys.stderr.write(f"abq2ccx: cannot write {log_path}: {exc}\n")

    if args.json_out:
        print(json.dumps({
            "tool": "abq2ccx", "version": __version__, "input": path,
            "output": out_path if wrote else None, "check_only": bool(args.check),
            "nodes": len(conv.geom.nodes), "elements": len(conv.geom.elements),
            "counts": {"warnings": report.n_warnings, "notes": report.n_notes,
                       "commented_cards": report.n_commented},
            "entries": [{"level": lvl, "message": m} for lvl, m in report.entries],
            "ok": report.n_warnings == 0 and report.n_commented == 0,
        }))
    elif not args.quiet:
        verb = "checked" if args.check else "wrote"
        sys.stderr.write(f"abq2ccx: {verb} {path if args.check else out_path} "
                         f"({len(conv.geom.nodes)} nodes, {len(conv.geom.elements)} elements, "
                         f"{report.summary()})\n")
        sys.stderr.write(report.text())

    if args.strict and (report.n_warnings > 0 or report.n_commented > 0):
        return 3
    if args.run and wrote:
        return run_ccx(out_path, args.ccx, args.quiet)
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="abq2ccx",
        description="Convert Abaqus .inp file(s) to CalculiX (ccx) .inp files.",
        epilog="Exit codes: 0 converted; 1 cannot read/write; 2 usage error; "
               "3 --strict findings; 4 internal conversion error. "
               "The output is a starting point: always review the [WARNING]/[NOTE] lines.")
    ap.add_argument("input", nargs="+", help="Abaqus input deck(s) (.inp); glob patterns allowed")
    ap.add_argument("-o", "--output", help="output file (single input only; default: <input>_ccx.inp)")
    ap.add_argument("--outdir", help="write outputs (default names) into this directory")
    ap.add_argument("--solid-dof", action="store_true",
                    help="force translational-only DOFs when expanding ENCASTRE/PINNED/*SYMM "
                         "(use for solid-only models that have no rotational DOFs)")
    ap.add_argument("--no-log", action="store_true", help="do not write a .log report file")
    ap.add_argument("--quiet", action="store_true", help="suppress the report on stderr")
    ap.add_argument("--approximate", action="store_true",
                    help="opt-in: reframe constructs ccx cannot run as approximately equivalent "
                         "ones it can (Riks->static, nu>=0.5 clamped, I-beam->equivalent RECT, "
                         "NLGEOM follower tractions->fixed nodal forces, surface elements with "
                         "rebar or mass->left out), each with a loud [APPROX] warning")
    ap.add_argument("--check", action="store_true",
                    help="dry run: parse + convert + report, write nothing")
    ap.add_argument("--strict", action="store_true",
                    help="exit 3 if the conversion produced warnings or commented-out cards")
    ap.add_argument("--json", dest="json_out", action="store_true",
                    help="print a machine-readable JSON report to stdout")
    ap.add_argument("--run", action="store_true",
                    help="run CalculiX on the converted output (auto-detected; see --ccx)")
    ap.add_argument("--ccx", help="CalculiX executable to use with --run ($CCX also honoured)")
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = ap.parse_args(argv)

    inputs: List[str] = []
    for pat in args.input:
        if any(ch in pat for ch in "*?[") and not os.path.exists(pat):
            matches = sorted(glob.glob(pat))         # Windows shells do not expand globs
            if matches:
                inputs.extend(matches)
            else:
                sys.stderr.write(f"abq2ccx: no files match {pat}\n")
        else:
            inputs.append(pat)
    if not inputs:
        sys.stderr.write("abq2ccx: nothing to convert\n")
        return 1
    if args.output and len(inputs) > 1:
        ap.error("-o/--output is only valid with a single input; use --outdir for batches")

    codes = [_convert_one(p, args) for p in inputs]
    if len(inputs) > 1 and not args.quiet and not args.json_out:
        ok = sum(1 for c in codes if c == 0)
        sys.stderr.write(f"abq2ccx: converted {ok}/{len(inputs)} deck(s)"
                         + (f", {len(inputs) - ok} with findings/failures" if ok != len(inputs) else "")
                         + "\n")
    return max(codes)


if __name__ == "__main__":
    raise SystemExit(main())
