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
import glob
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
from typing import Dict, Iterator, List, Optional, Sequence, Tuple

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
}

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
                  "COHESIVE SECTION", "GASKET SECTION", "PARAMETER", "SYSTEM", "UNIT SYSTEM",
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
    "CONNECTOR SECTION": "connectors have no ccx element; remodel as *RIGID BODY / *MPC / *SPRING / "
                         "*DASHPOT per the connector behaviour.",
    "CONNECTOR BEHAVIOR": "connector behaviour has no ccx equivalent; see *CONNECTOR SECTION.",
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
    "CONNECTOR ELASTICITY": "connector behaviour has no ccx equivalent; see *CONNECTOR SECTION.",
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
# and CELS (contact energy).  Only Abaqus names ccx itself recognises by their first four
# characters (CDISP, CSTRESS) are kept: folding CPRESS/COPEN/... onto CSTR/CDIS as well
# would switch contact output on for decks where ccx 2.23 then aborts while writing it
# (verified on an axisymmetric node-to-surface model that solves without it).
CCX_CONTACT_FILE_LABELS = {"CDIS", "CSTR", "CELS", "PCON"}
ABQ_CONTACT_MAP = {"CDISP": "CDIS", "CSTRESS": "CSTR"}


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


# ---------------------------------------------------------------------------
# Converter
# ---------------------------------------------------------------------------


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
        self._spc: set = set()                     # (node, dof) under a *BOUNDARY in any step
        self._rot_tied: set = set()                # (node, dof) already tied to a body rotation
        self._transformed: set = set()             # nodes with a *TRANSFORM (local DOFs)
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
            if eid in self.geom.elements:
                self.report.warn("Duplicate element id(s) in the input; the last definition is kept "
                                 "(Abaqus behaviour) — check for an upstream renumbering error.", once=True)
            self.geom.add_element(eid, typ, conn)
            ids.append(eid)
            i += 1 + nn
        if nn > 0 and i != len(toks):
            self.report.warn(f"*ELEMENT TYPE={typ}: {len(toks) - i} trailing token(s) "
                             f"not parsed; check connectivity.", once=True)
        self._elem_types.add(typ)
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
            "TIE": self.handle_tie,
            "BOUNDARY": self.handle_boundary,
            "CLOAD": self.handle_cload,
            "DLOAD": self.handle_dload,
            "DSLOAD": self.handle_dsload,
            "MPC": self.handle_mpc,
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
            "EXPANSION": self.handle_dependent_material,
            "MOHR COULOMB": self.handle_dependent_material,
            "MOHR COULOMB HARDENING": self.handle_dependent_material,
        }
        if kw in handlers:
            return handlers[kw](b)
        if kw in ("NODE FILE", "EL FILE", "NODE PRINT", "EL PRINT", "NODE OUTPUT", "ELEMENT OUTPUT",
                  "CONTACT OUTPUT", "CONTACT FILE"):
            return self.handle_output(b)
        if kw == "OUTPUT":
            self.report.note("*OUTPUT wrapper dropped; CalculiX output frequency defaults to every "
                             "increment (set FREQUENCY= on the file/print cards if needed).", once=True)
            return []
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
        per_rec = -(-width // 8)
        lines = [ln for ln in b.data if ln.strip()]
        if not lines or len(lines) % per_rec:
            return None
        recs: List[List[str]] = []
        for i in range(0, len(lines), per_rec):
            toks: List[str] = []
            for j, ln in enumerate(lines[i:i + per_rec]):
                f = [x.strip() for x in ln.split(",")]
                if j < per_rec - 1:
                    f = (f + [""] * 8)[:8]
                toks.extend(f)
            recs.append((toks + [""] * width)[:width])

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
        *SPECIFIC HEAT, *CONDUCTIVITY, *EXPANSION, *MOHR COULOMB[ HARDENING])."""
        typ = (b.param("TYPE") or "ISO").upper()
        n = {"ORTHO": 3, "ORTHOTROPIC": 3, "ANISO": 6, "ANISOTROPIC": 6}.get(typ, 1)
        nvals = {"MOHR COULOMB": 2, "MOHR COULOMB HARDENING": 2}.get(b.keyword, n)
        if b.has("DEPENDENCIES"):
            data = self._collapse_dependencies(b, nvals)
            params: "OrderedDict[str, Optional[str]]" = OrderedDict(
                (k, v) for k, v in b.params.items() if k != "DEPENDENCIES")
            if data is None:
                self.report.warn(f"*{b.keyword}, DEPENDENCIES=...: rows could not be parsed; "
                                 f"passed through — ccx ignores field-variable dependence and in "
                                 f"effect uses only the first row. Verify.", once=True)
                data = list(b.data)
            return [emit_keyword(b.keyword, params)] + data
        return self.passthrough(b)

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
                return converted
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
        return [emit_keyword("ELASTIC", params)] + data

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
        for b in inner:
            if b.keyword == "END STEP" or b.keyword in GEOM_KW:
                continue
            out.extend(self.translate_one(b))
        out.append("*END STEP")
        return out

    def handle_boundary(self, b: Block) -> List[str]:
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
        for rec in merged_data_records(b) + midside:
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
                # a named BC on a reference point constrains its rotations as well, even in
                # a solid-only model
                rot = self.has_rotational_dof or (not getattr(self.opt, "solid_dof", False) and
                                                  any(n in self._ref_nodes
                                                      for n in self._resolve_nodes(spec)))
                dofs = self._named_bc_dofs(rest[0], rot)
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
          ignores DOFs 4-6 of the REF NODE);
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
            for n in refs:
                out.append(line(str(self._rb_rot[n]), max(lo, 4) - 3, min(hi, 6) - 3))
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
        its ROT NODE — ccx silently ignores them on the REF NODE (verified: no rotation).
        Abaqus ORIENTATION= (local load axes) and FOLLOWER=YES have no ccx counterpart."""
        keep: "OrderedDict[str, Optional[str]]" = OrderedDict()
        for k, v in b.params.items():
            if k in ("OP", "AMPLITUDE", "TIME DELAY", "USER", "LOAD CASE", "SECTOR", "SUBMODEL",
                     "STEP"):
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
            for n in refs:
                out.append(", ".join([str(self._rb_rot[n]), str(int(f[1]) - 3)] + f[2:]))
        if moved:
            self.report.note("Moments on a *RIGID BODY reference point moved to DOFs 1-3 of its "
                             "ROT NODE (ccx ignores DOFs 4-6 of the REF NODE).", once=True)
        return out

    def handle_dload(self, b: Block) -> List[str]:
        body: List[str] = []
        for rec in merged_data_records(b):
            f = [x for x in rec if x != ""]
            if not f:
                continue
            label = f[1].upper() if len(f) >= 2 else ""
            if label in DLOAD_UNSUPPORTED:
                self.report.warn(f"*DLOAD type {label} has no CalculiX equivalent (ccx body loads are "
                                 f"GRAV and CENTRIF only — not rotary-acceleration/Coriolis/density-"
                                 f"scaled centrifugal); this load line was dropped. Verify.", once=True)
                continue
            if label == "P":
                self.report.warn("*DLOAD label 'P' has no face number; CalculiX needs P1..P6 for element "
                                 "pressure. Verify.", once=True)
            body.append(", ".join(f))
        had_data = any(x != "" for rec in merged_data_records(b) for x in rec)
        params = self._load_params(b, ("OP", "AMPLITUDE", "TIME DELAY", "LOAD CASE", "SECTOR", "SUBMODEL", "STEP"))
        if not body and had_data:
            if (b.param("OP") or "").upper() == "NEW":
                # keep the bare header: OP=NEW validly removes all previous distributed
                # loads in ccx, and losing that would leak stale loads across steps
                self.report.warn("*DLOAD, OP=NEW: every load line was unsupported and dropped, but "
                                 "the bare OP=NEW card is kept so previous distributed loads are "
                                 "still removed.", once=True)
                return [emit_keyword("DLOAD", params)]
            # every load line was unsupported — commenting is louder than emitting a bare card
            return self._commented(b, "*DLOAD has no CalculiX-compatible load lines; dropped.")
        # a *DLOAD with no data at all is valid ccx (OP=NEW clears previous distributed
        # loads; plain is a no-op) — pass it through unchanged
        return [emit_keyword("DLOAD", params)] + body

    def handle_dsload(self, b: Block) -> List[str]:
        keep = self._load_params(b, ("OP", "AMPLITUDE", "TIME DELAY", "SUBMODEL", "STEP"))
        body: List[str] = []
        for rec in merged_data_records(b):
            f = [x for x in rec if x != ""]
            if len(f) < 2:
                continue
            surf, label = f[0].upper(), f[1].upper()
            mag = f[2] if len(f) > 2 else ""
            if not re.fullmatch(r"P[1-6]?", label):
                self.report.warn(f"*DSLOAD label {label} is not a simple pressure; convert manually.", once=True)
                continue
            sd = self.surfaces.get(surf)
            if not sd or sd[0].startswith("NODE"):
                self.report.warn(f"*DSLOAD on '{surf}': not an element-based surface; cannot map to "
                                 f"*DLOAD automatically.", once=True)
                continue
            for token, face in sd[1]:
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
        if not body:
            return self._commented(b, "Could not convert *DSLOAD automatically; edit manually.")
        self.report.note("*DSLOAD surface pressure converted to *DLOAD with Px face labels "
                         "(solid faces match Abaqus).", once=True)
        return [emit_keyword("DLOAD", keep)] + body

    def handle_output(self, b: Block) -> List[str]:
        fmap = {"NODE OUTPUT": "NODE FILE", "ELEMENT OUTPUT": "EL FILE",
                "NODE FILE": "NODE FILE", "EL FILE": "EL FILE",
                "NODE PRINT": "NODE PRINT", "EL PRINT": "EL PRINT",
                "CONTACT OUTPUT": "CONTACT FILE", "CONTACT FILE": "CONTACT FILE"}
        cc = fmap.get(b.keyword, b.keyword)
        if cc == "CONTACT FILE":
            return self._contact_output(b)
        is_print = cc.endswith("PRINT")
        # parameters ccx's *NODE FILE / *EL FILE reader accepts (noelfiles.f); anything else
        # is "parameter not recognized" there
        file_ok = {"FREQUENCY", "FREQUENCYF", "GLOBAL", "OUTPUT", "SECTION FORCES", "OUTPUT ALL",
                   "TIME POINTS", "NSET", "LAST ITERATIONS", "CONTACT ELEMENTS", "DOUBLE"}
        params: "OrderedDict[str, Optional[str]]" = OrderedDict()
        suppress = False
        for k, v in b.params.items():
            if k == "POSITION":
                self.report.note("Output POSITION=... dropped (ccx extrapolates to nodes automatically).", once=True)
                continue
            if k in ("VARIABLE", "MODE", "MODE LIST", "SUMMARY", "LAST MODE"):
                self.report.note(f"Output parameter {k} dropped.", once=True)
                continue
            if k in ("FREQ", "FREQUENCY"):
                if v is not None and v.strip() == "0":
                    suppress = True
                params["FREQUENCY"] = v
                continue
            if k == "ELSET" and cc == "EL FILE":
                self.report.note("*EL FILE ELSET= dropped (ccx writes all elements to .frd; use "
                                 "*EL PRINT, ELSET= to restrict).", once=True)
                continue
            if not is_print and k not in file_ok:
                self.report.note(f"*{cc} parameter {k} dropped (not read by ccx).", once=True)
                continue
            if is_print and k == "DIRECTIONS":
                self.report.note(f"*{cc} parameter {k} dropped (not read by ccx).", once=True)
                continue
            params[k] = v
        if suppress:
            self.report.note(f"*{b.keyword} with FREQUENCY=0 dropped (output suppressed).", once=True)
            return []
        if cc == "EL PRINT" and "ELSET" not in params and ALL_ELEMENTS_SET in self.geom.elsets:
            params["ELSET"] = ALL_ELEMENTS_SET
            self.report.note(f"*EL PRINT without ELSET -> ELSET={ALL_ELEMENTS_SET} (Abaqus prints "
                             f"every element; ccx prints nothing without a set).", once=True)
        if cc == "NODE PRINT" and "NSET" not in params and ALL_NODES_SET in self.geom.nsets:
            params["NSET"] = ALL_NODES_SET
            self.report.note(f"*NODE PRINT without NSET -> NSET={ALL_NODES_SET} (Abaqus prints "
                             f"every node; ccx prints nothing without a set).", once=True)
        if cc == "EL PRINT" and "ELSET" not in params:
            self.report.warn("*EL PRINT requires ELSET= in ccx; none present.", once=True)
        if cc == "NODE PRINT" and "NSET" not in params:
            self.report.warn("*NODE PRINT requires NSET= in ccx; none present.", once=True)
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
                self.report.note("Per-component output identifiers (e.g. S11, EE12) collapsed to "
                                 "their base quantity (ccx writes whole tensors).", once=True)
                vu = mcomp.group(1)
            if vu in ABQ_DROP_VARS:
                self.report.note(f"Output variable {vu} dropped (no ccx equivalent; derive in "
                                 f"post-processing).", once=True)
                continue
            mapped = ABQ_MAP_VARS.get(vu, vu)
            if mapped != vu:
                why = ABQ_MAP_CAVEATS.get(vu, "CalculiX naming")
                self.report.note(f"Output variable {vu} -> {mapped} ({why}).", once=True)
            if not is_print and mapped in EL_PRINT_ONLY_VARS:
                self.report.note(f"Output variable {mapped} is valid only on *EL PRINT/*NODE PRINT; "
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
                self.report.note(f"Output variable {v} dropped from *{cc} (not a ccx label there"
                                 f"{'; ccx stops on an unknown *EL PRINT label' if cc == 'EL PRINT' else ''}).",
                                 once=True)
        outvars = kept
        if is_print and not outvars and invars:
            self.report.note(f"*{cc}: none of its variables exists in ccx; card dropped.", once=True)
            return []
        if not outvars and not is_print:
            outvars = ["U"] if cc == "NODE FILE" else ["S"]
            self.report.note(f"*{cc}: no explicit variables -> default '{outvars[0]}'.", once=True)
        out = [emit_keyword(cc, params)]
        if outvars:
            final = dedup_str(outvars)
            if len(final) > 16:                       # ccx reads at most 16 entries per line
                self.report.warn(f"*{cc}: more than 16 output identifiers after mapping; keeping "
                                 f"the first 16 (ccx line limit).", once=True)
                final = final[:16]
            out.append(", ".join(final))
        return out

    def _contact_output(self, b: Block) -> List[str]:
        """``*CONTACT OUTPUT`` / ``*CONTACT FILE`` -> ccx ``*CONTACT FILE``: Abaqus contact
        variables fold onto ccx's CDIS (opening/slip) and CSTR (pressure/shear); others
        (forces, areas, status) are dropped; Abaqus-only parameters too."""
        keep: "OrderedDict[str, Optional[str]]" = OrderedDict()
        for k, v in b.params.items():
            if k in ("FREQ", "FREQUENCY"):
                keep["FREQUENCY"] = v
            elif k in ("TIME POINTS", "LAST ITERATIONS", "CONTACT ELEMENTS", "FREQUENCYF"):
                keep[k] = v
            else:
                self.report.note(f"*{b.keyword} parameter {k} dropped (not read by ccx).", once=True)
        if (keep.get("FREQUENCY") or "").strip() == "0":
            return []
        labels: List[str] = []
        for rec in merged_data_records(b):
            for v in (x.upper() for x in rec if x != ""):
                m = ABQ_CONTACT_MAP.get(v, v)
                if ccx_label_ok(m, CCX_CONTACT_FILE_LABELS):
                    labels.append(m[:4])
                else:
                    self.report.note(f"Contact output variable {v} dropped (ccx writes CDIS, CSTR "
                                     f"and CELS only; its CSTR includes the contact pressure).",
                                     once=True)
        if not labels:
            had = any(x != "" for rec in merged_data_records(b) for x in rec)
            if had:                                 # every requested variable was dropped
                self.report.note(f"*{b.keyword}: no ccx contact variable requested; card dropped.",
                                 once=True)
                return []
            labels = ["CDIS", "CSTR"]
        return [emit_keyword("CONTACT FILE", keep), ", ".join(dedup_str(labels))]

    def handle_mpc(self, b: Block) -> List[str]:
        rot = self.has_rotational_dof
        plane_lines: List[str] = []
        eq_lines: List[str] = []
        for rec in merged_data_records(b):
            f = [x for x in rec if x != ""]
            if not f:
                continue
            typ = f[0].upper()
            if typ in ("PLANE", "STRAIGHT"):
                plane_lines.append(", ".join(f))
            elif typ == "TIE" and len(f) >= 3:
                dep, indep = f[1], f[2]
                for d in range(1, (6 if rot else 3) + 1):
                    eq_lines += ["*EQUATION", "2", f"{dep}, {d}, 1.0, {indep}, {d}, -1.0"]
                self.report.note("*MPC TIE converted to per-DOF *EQUATION.", once=True)
            else:
                return self._commented(b, f"*MPC TYPE={typ} not convertible automatically; edit manually.")
        out: List[str] = []
        if plane_lines:
            out.append("*MPC")
            out.extend(plane_lines)
        out.extend(eq_lines)
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
            out += [f"*SURFACE, TYPE=NODE, NAME={tag}_{gi}"] + list(ms)
            out += [f"*COUPLING, CONSTRAINT NAME={tag}_{gi}, REF NODE={ref}, SURFACE={tag}_{gi}",
                    "*KINEMATIC", f"{lo}, {min(hi, 3)}"]
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
        which carry the ccx coupling's rotation (see _plan_rigid_couplings)."""
        plan, self._last_coupling = self._last_coupling or {}, None
        if plan.get("kind") == "rb":
            return []                 # folded into the *RIGID BODY of the *COUPLING card
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
            c1, c2 = min(d1, 3), min(d2, 3)
            clamped = clamped or (c1, c2) != (d1, d2)
            lines.append(f"{c1}, {c2}")
        if not had_lines:
            self.report.warn("*KINEMATIC without DOF lines creates NO constraint in ccx (the "
                             "coupling silently does nothing); synthesized '1, 3' to match the "
                             "Abaqus default of coupling all DOFs — verify.", once=True)
            lines = ["1, 3"]
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
        data line (initial increment, period, min, max) has the same layout in both."""
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
        return [emit_keyword("DYNAMIC", keep)] + list(b.data)

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
        mean of their end nodes' values."""
        return self.passthrough(b) + self._midside_records(b, "field")

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
        for rec in merged_data_records(b):
            f = [x for x in rec if x != ""]
            if not f:
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
        if any(b.keyword in ("PART", "INSTANCE", "ASSEMBLY") for b in blocks):
            blocks = flatten_assembly(blocks, self.report, self.opt)
        self.build_geometry(blocks)
        self._find_planar_elements()            # before the beam upgrades below retype them
        self._upgrade_section_beams(blocks)
        self._check_nonpositive_ids()
        self._check_overconstraints(blocks)
        self._prescan(blocks)
        self._plan_distributions(blocks)
        self._check_undefined_materials(blocks)
        self._plan_planar_constraint(blocks)
        self._plan_circ_rotation_knots(blocks)          # after the planar DOF 4-5 picks
        self._plan_op_new_rotations(blocks)     # after the planar BCs, which OP=NEW removes too
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
        return out

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
        # reference/rotation nodes of rigid bodies and couplings carry real rotations
        self._ref_nodes = set()
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
        self._plan_rigid_couplings(blocks)
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
        if any_temp_ic and self.geom.nodes and not set(self.geom.nodes) <= covered:
            self._temp_ic_fill = True
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
        self._spc = self._boundary_dofs(blocks)
        self._transformed = {n for b in blocks if b.keyword == "TRANSFORM"
                             for n in self._resolve_nodes((b.param("NSET") or "").strip())}
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
        knots = [n for n in dedup(knots) if n in self.geom.nodes]
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
        self.report.note(f"Rigid coupling on shell/beam nodes: ccx builds *KINEMATIC / *RIGID BODY "
                         f"from RIGID MPCs, which ccx 2.23 (FreeCAD 1.1 build) rejects on a shell/"
                         f"beam node unless ccx made it a knot ('*ERROR in gen3dmpc: ... RIGID "
                         f"MPC'). Each of the {len(knots)} such node(s) got a force-free knot beam "
                         f"(a B31 to a new free node, elset/material {KNOT_SET}, no density), "
                         f"which makes it a knot; the rotations Abaqus couples are tied to the "
                         f"reference rotation with *EQUATION.")

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
        eid = max(self.geom.elements, default=0)
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
        members that have rotations; a member DOF under a *BOUNDARY keeps the BC (ccx stops
        on a DOF that is both SPC'd and the dependent term of an MPC)."""
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
                if (n, k) in self._spc:
                    self.report.note("Coupled rotation not tied where the node's DOF has a "
                                     "*BOUNDARY (ccx stops on a DOF that is SPC'd and dependent "
                                     "in an MPC) — the BC governs it.", once=True)
                    continue
                if (n, k) in self._rot_tied:
                    self.report.warn("A shell/beam node belongs to two rigid constraints; its "
                                     "rotation is tied to the first one only — verify.", once=True)
                    continue
                self._rot_tied.add((n, k))
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
        out: set = set()
        for b in blocks:
            if b.keyword != "BOUNDARY":
                continue
            for rec in merged_data_records(b):
                g = [x.strip() for x in rec]
                while g and g[-1] == "":
                    g.pop()
                if len(g) < 2:
                    continue
                if re.fullmatch(r"[-+]?\d+", g[1]):
                    d1 = int(g[1])
                    d2 = int(g[2]) if len(g) > 2 and re.fullmatch(r"[-+]?\d+", g[2]) else d1
                    dofs = list(range(min(d1, d2), max(d1, d2) + 1))
                else:
                    dofs = [d for a, c in (self._named_bc_dofs(g[1], True) or [])
                            for d in range(a, c + 1)]
                out.update((n, d) for n in self._resolve_nodes(g[0]) for d in dofs)
        return out

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

    def _check_overconstraints(self, blocks: List[Block]) -> None:
        """Flag the #1 runtime crash on converted decks: a DOF that is both the
        dependent term of an *EQUATION/*MPC and the target of a *BOUNDARY (ccx stops
        with '*ERROR in cascade ... dependent side of a MPC and a SPC')."""
        dep: Dict[Tuple[int, int], str] = {}
        ndof = 6 if self.has_rotational_dof else 3
        for b in blocks:
            if b.keyword == "EQUATION":
                nums: List[str] = []
                for rec in merged_data_records(b):
                    nums.extend(x for x in rec if x != "")
                if len(nums) >= 3:                       # count, then node, dof, coef, ...
                    try:
                        dep[(int(float(nums[1])), int(float(nums[2])))] = "EQUATION"
                    except ValueError:
                        pass
            elif b.keyword == "MPC":
                for rec in merged_data_records(b):
                    f = [x for x in rec if x != ""]
                    if len(f) >= 2 and f[0].upper() == "TIE":
                        try:
                            n = int(float(f[1]))
                            for d in range(1, ndof + 1):
                                dep[(n, d)] = "MPC TIE"
                        except ValueError:
                            pass
        if not dep:
            return
        clashes: List[Tuple[int, int, str]] = []
        for b in blocks:
            if b.keyword != "BOUNDARY":
                continue
            for rec in merged_data_records(b):
                f = [x for x in rec if x != ""]
                if not f:
                    continue
                if len(f) >= 2 and re.fullmatch(r"[-+]?\d+", f[1]):
                    d1 = int(f[1])
                    d2 = int(f[2]) if len(f) > 2 and re.fullmatch(r"[-+]?\d+", f[2]) else d1
                    dofs = list(range(min(d1, d2), max(d1, d2) + 1))
                elif len(f) >= 2:
                    nb = self._named_bc_dofs(f[1]) or []
                    dofs = [d for a, c in nb for d in range(a, c + 1)]
                else:
                    dofs = list(range(1, ndof + 1))
                for n in self._resolve_nodes(f[0]):
                    for d in dofs:
                        if (n, d) in dep:
                            clashes.append((n, d, dep[(n, d)]))
        for n, d, src in clashes[:5]:
            self.report.warn(f"Possible overconstraint: node {n} DOF {d} is on the dependent side of "
                             f"a {src} AND has a *BOUNDARY. CalculiX will stop with '*ERROR in cascade "
                             f"... dependent side of a MPC and a SPC'. Remove the BC or the constraint "
                             f"on that DOF.", once=True)

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
        for rec in merged_data_records(b):
            g = [x.strip() for x in rec]
            while g and g[-1] == "":
                g.pop()
            if len(g) < 2 or not g[0]:
                continue
            value = 0.0
            if re.fullmatch(r"[-+]?\d+", g[1]):
                d1 = int(g[1])
                d2 = int(g[2]) if len(g) > 2 and re.fullmatch(r"[-+]?\d+", g[2]) else d1
                ds = set(range(min(d1, d2), max(d1, d2) + 1))
                try:
                    value = pf(g[3]) if len(g) > 3 and g[3] else 0.0
                except ValueError:
                    value = 1.0                          # a *PARAMETER name: assume it moves
            else:
                ds = {d for lo, hi in self._named_bc_dofs(g[1], True) or [] for d in range(lo, hi + 1)}
            yield self._resolve_nodes(g[0]), ds, moving or value != 0.0

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
                     "MEMBRANE SECTION", "COHESIVE SECTION", "GASKET SECTION", "SPRING", "DASHPOT",
                     "MASS", "GAP", "ORIENTATION", "DISTRIBUTION", "SURFACE"}
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
                         "MEMBRANE SECTION", "COHESIVE SECTION", "GASKET SECTION", "SPRING",
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
        # with NO ccx equivalent (CONN*, JOINTC, ...) are deliberately left unresolved:
        # they then drop out via the non-numeric-connectivity skip, which keeps the rest
        # of the deck solvable instead of feeding ccx a fatal unknown element.
        if blk.keyword == "ELEMENT":
            etyp = (blk.param("TYPE") or "").upper()
            if etyp.startswith(UNSUPPORTED_ELEM_PREFIXES) or etyp in ("JOINTC",):
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


def classify_ccx_run(returncode, stdout: str, stderr: str) -> str:
    """Classify a finished ccx run:

    * ``"solved"``   - exit 0, "Job finished", no ``*ERROR``, no crash/abort message, and
                       at least one analysis STEP executed;
    * ``"accepted"`` - the same, but no STEP ran (a mesh-only deck ccx only parsed);
    * ``"failed"``   - anything else, including a crash after "Job finished".

    The per-iteration "no convergence" message is normal in nonlinear solves and is not
    a failure; a run that really gives up prints ``*ERROR``."""
    if returncode != 0 or "Job finished" not in stdout:
        return "failed"
    if "*ERROR" in stdout or "*ERROR" in stderr:
        return "failed"
    if any(s in stdout or s in stderr for s in CCX_ABORT_SIGNS):
        return "failed"
    return "solved" if _CCX_STEP_RE.search(stdout) else "accepted"


def run_ccx(out_path: str, override: Optional[str], quiet: bool) -> int:
    """Run CalculiX on a converted deck; 0 if the analysis solves (or ccx accepts a
    mesh-only deck that has nothing to solve), 1 otherwise."""
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
    status = classify_ccx_run(p.returncode, p.stdout, p.stderr)
    if status == "accepted":
        sys.stderr.write("abq2ccx: ccx accepted the deck, but it has no analysis step — "
                         "nothing was solved.\n")
        return 0
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
                         "ones it can (Riks->static, nu>=0.5 clamped, I-beam->equivalent RECT), "
                         "each with a loud [APPROX] warning")
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
