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
    python abq2ccx.py model.inp                # -> model_ccx.inp (+ model_ccx.log)
    python abq2ccx.py model.inp -o out.inp
    python abq2ccx.py model.inp --quiet
    python abq2ccx.py model.inp --solid-dof 3  # force translational-only ENCASTRE

This file is intentionally a single self-contained script (no dependencies
beyond the Python standard library) so it is trivial to drop into a project or
run on a cluster.
"""

from __future__ import annotations

import argparse
import ast
import math
import operator
import os
import re
import sys
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

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
    "COH3D8": "C3D8", "COH3D6": "C3D6", "COH2D4": "CPE4", "COHAX4": "CAX4",
    "GK3D8": "C3D8", "GK3D6": "C3D6", "GK2D4": "CPE4", "GK2D6": "CPE6",
    "GKPS4": "CPS4", "GKPS6": "CPS6", "GKAX4": "CAX4", "GKAX6": "CAX6",
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
    # Coupled temperature-displacement elements (the ``T`` suffix): CalculiX uses the
    # *base* element name and gets the temperature DOF from the
    # ``*COUPLED TEMPERATURE-DISPLACEMENT`` step, so C3D8T->C3D8, CAX4RT->CAX4R,
    # C3D10MT->C3D10M.  Recurse so a base that itself needs mapping is resolved.
    if typ.endswith("T") and len(typ) > 1 and (
            typ[:-1] in CCX_ELEMENTS or typ[:-1] in ELEMENT_TYPE_MAP
            or (typ[:-1].endswith("H") and typ[:-2] in CCX_ELEMENTS)):
        report.warn(f"Element {typ} -> {typ[:-1]} (CalculiX uses the base element for coupled "
                    f"temperature-displacement; the temperature DOF comes from the step).", once=True)
        return ccx_element_type(typ[:-1], report)
    if typ.endswith("H") and len(typ) > 1 and (typ[:-1] in CCX_ELEMENTS or typ[:-1] in ELEMENT_TYPE_MAP):
        report.warn(f"Element {typ} -> {typ[:-1]} (CalculiX has no hybrid formulation).", once=True)
        return ccx_element_type(typ[:-1], report)
    # Pore-pressure (coupled displacement / pore-pressure) elements (the ``P`` suffix):
    # ccx has no pore-pressure element, so fall back to the mechanical base and drop the
    # pore-pressure DOF (e.g. CAX4P->CAX4, CPE8P->CPE8, C3D8P->C3D8).
    if typ.endswith("P") and len(typ) > 1 and (typ[:-1] in CCX_ELEMENTS or typ[:-1] in ELEMENT_TYPE_MAP):
        report.warn(f"Element {typ} -> {typ[:-1]}: ccx has no pore-pressure (coupled u-p) element; "
                    f"the pore-pressure DOF is dropped and only the mechanical response is solved — "
                    f"consolidation/seepage is NOT modelled. Verify.", once=True)
        return ccx_element_type(typ[:-1], report)
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

MAX_ENTRIES_PER_LINE = 16  # CalculiX hard limit for entries on a data line

# ---------------------------------------------------------------------------
# Conversion report
# ---------------------------------------------------------------------------


class Report:
    """Collects warnings / notes emitted during conversion."""

    def __init__(self) -> None:
        self.entries: List[Tuple[str, str]] = []
        self._seen: set = set()

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

    def header_comment_lines(self) -> List[str]:
        lines = ["** ====================================================================",
                 "** Converted from Abaqus to CalculiX by abq2ccx.py",
                 "** Review the notes below and verify against your ccx version.",
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
# full spelling.  Normalise the common ones that appear in real decks.
PARAM_ALIASES = {"GEN": "GENERATE", "PERT": "PERTURBATION"}
# Abaqus keyword abbreviations CalculiX does not accept.
KEYWORD_ALIASES = {"AMP": "AMPLITUDE"}


def parse_keyword_line(line: str) -> Tuple[str, "OrderedDict[str, Optional[str]]"]:
    """``*EL PRINT, POSITION=AVERAGED AT NODES, ELSET=EOUT`` ->
    ("EL PRINT", {"POSITION": "AVERAGED AT NODES", "ELSET": "EOUT"})."""
    tokens = _split_commas(line)
    keyword = tokens[0].lstrip("*").strip().upper()
    keyword = KEYWORD_ALIASES.get(keyword, keyword)
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
        if s.lower().startswith("*parameter"):
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
    bare_flags = {"GENERATE", "GEN", "SHIFT", "UNSORTED", "REFLECT", "INTERNAL", "ROUGH"}

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
        with open(path, "r", errors="replace") as fh:
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
    """Reflect a point in a POINT, LINE or PLANE mirror."""
    if kind == "POINT":
        o = data[0]
        return vsub(vscale(o, 2.0), p)
    if kind == "PLANE":
        o, q = data[0], data[1]              # two points; normal approximated below
        # PLANE is given by two points in Abaqus only for 2-D; for 3-D a third is
        # needed.  We treat (o,q) as defining the plane normal n=q-o through o.
        n = vunit(vsub(q, o))
        dist = vdot(vsub(p, o), n)
        return vsub(p, vscale(n, 2.0 * dist))
    if kind == "LINE":
        o, q = data[0], data[1]
        u = vunit(vsub(q, o))
        d = vsub(p, o)
        proj = vadd(o, vscale(u, vdot(d, u)))
        return vsub(vscale(proj, 2.0), p)
    return None


# ---------------------------------------------------------------------------
# Mesh-generation expansion
# ---------------------------------------------------------------------------


def expand_ngen(block: Block, geom: Geometry, report: Report) -> List[int]:
    """``*NGEN`` -> straight-line node generation between two existing nodes."""
    if (block.param("LINE") or "").upper().startswith("C"):
        report.warn("*NGEN with circular LINE=C is not supported; nodes not generated.")
        return []
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
        ids = list(range(n1, n2 + (1 if inc > 0 else -1), inc))
        if not ids:
            report.warn(f"*NGEN endpoints {n1},{n2} with increment {inc} generated no nodes "
                        f"(check the ordering/sign of the range); skipped.", once=True)
            continue
        steps = len(ids) - 1
        for k, nid in enumerate(ids):
            t = k / steps if steps else 0.0
            geom.add_node(nid, vadd(vscale(p1, 1 - t), vscale(p2, t)))
            created.append(nid)
    return created


def expand_nfill(block: Block, geom: Geometry, report: Report) -> List[int]:
    """``*NFILL`` -> linear fill of nodes between two node sets."""
    created: List[int] = []
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
                t = j / nint
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

    for m in range(1, multiple + 1):
        for nid in src:
            p = geom.nodes.get(nid)
            if p is None:
                continue
            new_id = nid + change * m
            if reflect:
                pts = [tuple(pf(x) for x in r[:3]) for r in recs if len(r) >= 3]
                np_ = reflect_point(p, reflect, pts) if pts else None
                if np_ is None:
                    report.warn(f"*NCOPY REFLECT={reflect} could not be applied; skipped.", once=True)
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
    "PREPRINT", "MANIFEST",
}
# Dropped, but loudly (they can change the model -> the user must check).
DROP_WARN_KEYWORDS = {
    "SYSTEM": "*SYSTEM (local coordinate system for following *NODE cards) is unsupported "
              "by ccx and was dropped; node coordinates defined under it may be in a rotated "
              "frame — verify they are global.",
    "PARAMETER": "*PARAMETER (parametric input) is unsupported by ccx and was dropped; any "
                 "<parameter> substitutions will not resolve.",
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
    "COUPLING": "*COUPLING + *KINEMATIC/*DISTRIBUTING is accepted by recent ccx, but ccx "
                "*KINEMATIC requires an explicit DOF list (Abaqus allows none = all 6) — verify.",
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
}

# ---- output variable maps (Abaqus identifier -> ccx) --------------------------
# Dropped: no ccx equivalent (derived in post-processing or simply unavailable).
ABQ_DROP_VARS = {"MISES", "PRESS", "TRESC", "A", "NE", "IE", "CF", "NFORC", "COORD", "STH",
                 "STATUS", "CDISP", "CSTRESS", "CFORCE", "CTF", "VENER", "AENER", "AREA",
                 "AT", "SE", "SM", "SF", "ELEN", "NFLUX", "RBFOR"}
# Renamed / folded onto a ccx identifier.
ABQ_MAP_VARS = {"LE": "E", "PE": "PEEQ", "PEMAG": "PEEQ", "CEEQ": "PEEQ", "EE": "ME",
                "NE11": "E", "NT11": "NT", "UT": "U", "UR": "U", "RT": "RF", "RM": "RF",
                "CELENT": "EVOL"}
# ccx identifiers that are valid only on *EL PRINT / *NODE PRINT (.dat), not *EL FILE.
EL_PRINT_ONLY_VARS = {"ELSE", "ELKE", "EVOL", "CELS"}

# Abaqus *DLOAD body-force labels CalculiX has no equivalent for (verified: ccx accepts
# only GRAV and CENTRIF body loads, and rejects the whole *DLOAD on any of these).  CENT
# is Abaqus' density-scaled centrifugal load; ROTA/CORIO/ROTDYNF are rotary-acceleration /
# Coriolis / rotor-dynamic loads.
DLOAD_UNSUPPORTED = {"CENT", "ROTA", "CORIO", "ROTDYNF"}


# ---------------------------------------------------------------------------
# Converter
# ---------------------------------------------------------------------------


class Converter:

    def __init__(self, report: Report, options) -> None:
        self.report = report
        self.opt = options
        self.geom = Geometry()
        self.orientations: Dict[str, Tuple[Vec, Vec, str]] = {}
        self.surfaces: Dict[str, Tuple[str, List[Tuple[str, Optional[str]]]]] = {}
        self._elem_types: set = set()
        self._synth_cache: Dict[Tuple[str, float], str] = {}

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
        else:
            self.geom.add_to_elset(name, ids)

    def _register_orientation(self, b: Block) -> None:
        name = (b.param("NAME") or "").upper()
        system = (b.param("SYSTEM") or "RECTANGULAR").upper()
        a, bvec = (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)
        recs = merged_data_records(b)
        if recs:
            try:                              # distribution-based *ORIENTATION has a
                v = [pf(x) for x in recs[0] if x != ""]   # name here, not coords
                if len(v) >= 6:
                    a, bvec = (v[0], v[1], v[2]), (v[3], v[4], v[5])
            except ValueError:
                pass
        self.orientations[name] = (a, bvec, system)

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
            "SOLID SECTION": self.handle_solid_section,
            "SHELL SECTION": self.handle_shell_section,
            "SHELL GENERAL SECTION": self.handle_shell_section,
            "BEAM SECTION": self.handle_beam_section,
            "COHESIVE SECTION": self.handle_cohesive_section,
            "GASKET SECTION": self.handle_cohesive_section,
            "TIE": self.handle_tie,
            "BOUNDARY": self.handle_boundary,
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
        }
        if kw in handlers:
            return handlers[kw](b)
        if kw in ("NODE FILE", "EL FILE", "NODE PRINT", "EL PRINT", "NODE OUTPUT", "ELEMENT OUTPUT"):
            return self.handle_output(b)
        if kw == "OUTPUT":
            self.report.note("*OUTPUT wrapper dropped; CalculiX output frequency defaults to every "
                             "increment (set FREQUENCY= on the file/print cards if needed).", once=True)
            return []
        if kw == "KINEMATIC COUPLING":
            return self.handle_coupling(b)
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
        if kw in SEMANTIC_TRAP:
            self.report.warn(SEMANTIC_TRAP[kw], once=True)
        elif kw in PASS_WITH_NOTE:
            self.report.note(PASS_WITH_NOTE[kw], once=True)
        elif kw not in CCX_KEYWORDS:
            guidance = SPECIAL_UNSUPPORTED.get(kw)
            msg = (f"*{kw}: {guidance}" if guidance
                   else f"*{kw} has no direct CalculiX equivalent; emitted as a comment for review.")
            return self._commented(b, msg)
        return [emit_keyword(kw, b.params)] + list(b.data)

    def _commented(self, b: Block, msg: str) -> List[str]:
        self.report.warn(msg, once=True)
        out = ["** abq2ccx: " + msg, "** " + emit_keyword(b.keyword, b.params)]
        out += ["** " + d for d in b.data]
        return out

    # -- model-data handlers ------------------------------------------------
    def handle_elastic(self, b: Block) -> List[str]:
        typ = (b.param("TYPE") or "ISO").upper()
        tmap = {"ISOTROPIC": "ISO", "ISO": "ISO", "ORTHOTROPIC": "ORTHO", "ORTHO": "ORTHO",
                "ENGINEERING CONSTANTS": "ENGINEERING CONSTANTS",
                "ANISOTROPIC": "ANISO", "ANISO": "ANISO"}
        cc = tmap.get(typ, typ)
        params: "OrderedDict[str, Optional[str]]" = OrderedDict()
        for k, v in b.params.items():
            if k == "TYPE":
                if cc != "ISO":
                    params["TYPE"] = cc
            else:
                params[k] = v
        if typ in ("ORTHOTROPIC", "ANISOTROPIC"):
            self.report.note(f"*ELASTIC TYPE={typ} -> {cc} (constant order is identical; "
                             f"data lines passed through).", once=True)
        return [emit_keyword("ELASTIC", params)] + list(b.data)

    def handle_orientation(self, b: Block) -> List[str]:
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
            if len(v) > 6:
                self.report.note("*ORIENTATION: coordinates beyond points a,b dropped (ccx uses 2 points).", once=True)
                v = v[:6]
            out.append(", ".join(v))
        if len(recs) > 1:
            v = [x for x in recs[1] if x != ""]
            if v:
                out.append(", ".join(v))
                self.report.note("*ORIENTATION additional-rotation line kept (needs ccx >= ~2.15).", once=True)
        return out

    def handle_distribution(self, b: Block) -> List[str]:
        params: "OrderedDict[str, Optional[str]]" = OrderedDict()
        for k, v in b.params.items():
            if k in ("LOCATION", "TABLE"):
                continue
            params[k] = v
        self.report.warn("*DISTRIBUTION passed through: CalculiX supports it only via *ORIENTATION on a "
                         "*SOLID SECTION (never on shells), and the table layout may need manual "
                         "adjustment to 'elset, ax,ay,az, bx,by,bz'. Verify.", once=True)
        return [emit_keyword("DISTRIBUTION", params)] + list(b.data)

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
        return [emit_keyword("SOLID SECTION", keep)] + list(b.data)

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
        keep: "OrderedDict[str, Optional[str]]" = OrderedDict()
        for k, v in b.params.items():
            if k in ("ELSET", "MATERIAL", "SECTION", "ORIENTATION", "OFFSET1", "OFFSET2"):
                keep[k] = v
            else:
                self.report.note(f"*BEAM SECTION parameter {k} dropped.", once=True)
        if (b.param("SECTION") or "").upper() == "CIRC":
            self.report.warn("*BEAM SECTION SECTION=CIRC: Abaqus uses a radius, ccx uses two elliptical "
                             "axis lengths; verify the dimension line.", once=True)
        return [emit_keyword("BEAM SECTION", keep)] + list(b.data)

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
                if k in ("ELSET", "OFFSET"):
                    keep[k] = v
                elif k == "COMPOSITE":
                    keep[k] = None
                elif k == "ORIENTATION":
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
                    oriname = base_ori.upper() if base_ori else None
                else:
                    try:                                  # Abaqus: numeric ply angle
                        float(ply_ori)
                        oriname = self._synth_orientation(base_ori, ply_ori, pre)
                    except ValueError:                    # already an *ORIENTATION name
                        oriname = ply_ori.upper()
                if oriname:
                    ply_lines.append(f"{thick}, , {mat}, {oriname}")
                else:
                    ply_lines.append(f"{thick}, , {mat}")
            self.report.note("*SHELL SECTION, COMPOSITE: ply angles converted to synthesized "
                             "*ORIENTATION cards (rotation about the shell normal). Verify for curved "
                             "shells.", once=True)
            return pre + [emit_keyword("SHELL SECTION", keep)] + ply_lines
        # simple (single-material) shell
        keep = OrderedDict()
        for k, v in b.params.items():
            if k in ("ELSET", "MATERIAL", "ORIENTATION", "OFFSET", "NODAL THICKNESS"):
                keep[k] = v
            else:
                self.report.note(f"*SHELL SECTION parameter {k} dropped.", once=True)
        out = [emit_keyword("SHELL SECTION", keep)]
        recs = merged_data_records(b)
        if recs:
            f = [x for x in recs[0] if x != ""]
            if f:
                if len(f) > 1:
                    self.report.note("*SHELL SECTION: integration-point count dropped (ccx wants the "
                                     "thickness only).", once=True)
                out.append(f[0])
        return out

    def _synth_orientation(self, base_name: str, angle: str, pre: List[str]) -> Optional[str]:
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
        name = f"ABQ2CCX_OR{len(self._synth_cache) + 1}"
        self._synth_cache[key] = name
        pre.append(f"*ORIENTATION, NAME={name}")
        pre.append(", ".join(fmt_num(x) for x in (a[0], a[1], a[2], bvec[0], bvec[1], bvec[2])))
        pre.append(f"3, {fmt_num(ang)}")
        return name

    # -- step / load / bc handlers -----------------------------------------
    def handle_step(self, group: List[Block]) -> List[str]:
        step_block = group[0]
        inner = group[1:]
        proc = next((b.keyword for b in inner if b.keyword in PROC_KW), None)
        params: "OrderedDict[str, Optional[str]]" = OrderedDict()
        for k, v in step_block.params.items():
            if k == "NAME":
                continue
            if k == "PERTURBATION":
                if proc in ("FREQUENCY", "BUCKLE"):
                    params[k] = v
                else:
                    self.report.note("*STEP PERTURBATION dropped (ccx allows it only for *FREQUENCY / "
                                     "*BUCKLE; a perturbation *STATIC becomes a linear static step).", once=True)
                continue
            if k == "AMPLITUDE":
                self.report.warn("*STEP AMPLITUDE= is unsupported by ccx; attach the amplitude to the "
                                 "individual loads/BCs instead.", once=True)
                continue
            params[k] = v
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
                self.report.note("*BOUNDARY LOAD CASE is only meaningful in ccx steady-state "
                                 "dynamics.", once=True)
            params[k] = v
        out = [emit_keyword("BOUNDARY", params)]
        for rec in merged_data_records(b):
            # Interior blanks are positional (e.g. "node, dof1, , value" = blank last
            # DOF), so trim only trailing empties — never filter interior fields.
            g = [x.strip() for x in rec]
            while g and g[-1] == "":
                g.pop()
            if not g:
                continue
            spec, rest = g[0], g[1:]
            if rest and rest[0] and not re.fullmatch(r"[-+]?\d+", rest[0]):
                dofs = self._named_bc_dofs(rest[0])
                if dofs is None:
                    self.report.warn(f"*BOUNDARY type '{rest[0]}' not recognised; line passed through.", once=True)
                    out.append(", ".join(g))
                else:
                    for d1, d2 in dofs:
                        out.append(f"{spec}, {d1}, {d2}")
            elif len(rest) >= 2:
                # node, first-dof, last-dof[, magnitude]; blank last-dof means = first
                dof2 = rest[1] if rest[1] != "" else rest[0]
                out.append(", ".join([spec, rest[0], dof2] + rest[2:]))
            else:
                out.append(", ".join(g))
        return out

    def _named_bc_dofs(self, name: str) -> Optional[List[Tuple[int, int]]]:
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
        if not body:
            return self._commented(b, "*DLOAD has no CalculiX-compatible load lines; dropped.")
        return [emit_keyword("DLOAD", b.params)] + body

    def handle_dsload(self, b: Block) -> List[str]:
        keep: "OrderedDict[str, Optional[str]]" = OrderedDict()
        for k, v in b.params.items():
            if k in ("OP", "AMPLITUDE", "TIME DELAY"):
                keep[k] = v
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
                "NODE PRINT": "NODE PRINT", "EL PRINT": "EL PRINT"}
        cc = fmap.get(b.keyword, b.keyword)
        is_print = cc.endswith("PRINT")
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
            params[k] = v
        if suppress:
            self.report.note(f"*{b.keyword} with FREQUENCY=0 dropped (output suppressed).", once=True)
            return []
        if cc == "EL PRINT" and "ELSET" not in params:
            self.report.warn("*EL PRINT requires ELSET= in ccx; none present.", once=True)
        if cc == "NODE PRINT" and "NSET" not in params:
            self.report.warn("*NODE PRINT requires NSET= in ccx; none present.", once=True)
        invars: List[str] = []
        for rec in merged_data_records(b):
            invars.extend(x for x in rec if x != "")
        outvars: List[str] = []
        for v in invars:
            vu = v.upper()
            if vu in ABQ_DROP_VARS:
                self.report.note(f"Output variable {vu} dropped (no ccx equivalent; derive in "
                                 f"post-processing).", once=True)
                continue
            mapped = ABQ_MAP_VARS.get(vu, vu)
            if mapped != vu:
                self.report.note(f"Output variable {vu} -> {mapped} (CalculiX naming).", once=True)
            if not is_print and mapped in EL_PRINT_ONLY_VARS:
                self.report.note(f"Output variable {mapped} is valid only on *EL PRINT/*NODE PRINT; "
                                 f"dropped from *{cc} (.frd).", once=True)
                continue
            outvars.append(mapped)
        if not outvars and not is_print:
            outvars = ["U"] if cc == "NODE FILE" else ["S"]
            self.report.note(f"*{cc}: no explicit variables -> default '{outvars[0]}'.", once=True)
        out = [emit_keyword(cc, params)]
        if outvars:
            out.append(", ".join(dedup_str(outvars)))
        return out

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
        # Abaqus standalone *KINEMATIC COUPLING (newer *COUPLING/*KINEMATIC/
        # *DISTRIBUTING are native ccx keywords and pass through unchanged).
        ref = b.param("REF NODE") or b.param("REFNODE")
        recs = merged_data_records(b)
        nsetspec = recs[0][0] if recs and recs[0] else None
        if ref and nsetspec:
            self.report.note("*KINEMATIC COUPLING -> *RIGID BODY (couples all 6 DOFs; partial-DOF "
                             "coupling is not preserved).", once=True)
            return [f"*RIGID BODY, NSET={nsetspec}, REF NODE={ref}"]
        return self._commented(b, "*KINEMATIC COUPLING could not be converted; edit manually.")

    def handle_creep(self, b: Block) -> List[str]:
        keep: "OrderedDict[str, Optional[str]]" = OrderedDict()
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
        return [emit_keyword("CREEP", keep)] + list(b.data)

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
        for k, v in b.params.items():
            if k in ("NAME", "TIME", "SHIFTX", "SHIFTY"):
                keep[k] = v
            elif k == "DEFINITION" and v and v.upper() != "TABULAR":
                self.report.warn(f"*AMPLITUDE DEFINITION={v} unsupported by ccx; treated as TABULAR.", once=True)
            else:
                self.report.note(f"*AMPLITUDE parameter {k} dropped.", once=True)
        return [emit_keyword("AMPLITUDE", keep)] + list(b.data)

    def handle_friction(self, b: Block) -> List[str]:
        """``*FRICTION``: CalculiX requires a strictly positive coefficient, and treats
        the *absence* of the card as frictionless.  A zero/empty/rough coefficient
        (common in Abaqus contact decks) makes ccx stop, so drop the card in that
        case."""
        mu = None
        for rec in merged_data_records(b):
            vals = [x for x in rec if x != ""]
            if vals:
                try:
                    mu = float(vals[0])
                except ValueError:
                    mu = None
                break
        if (b.param("ROUGH") is not None) or mu is None or mu <= 0.0:
            self.report.note("*FRICTION with no positive coefficient dropped — ccx treats the absence "
                             "of *FRICTION as frictionless, whereas a zero/empty/ROUGH coefficient is "
                             "a hard error there. Re-add it with mu>0 if you need friction.", once=True)
            return ["** [abq2ccx] *FRICTION dropped (frictionless / no positive coefficient)"]
        return [emit_keyword("FRICTION", b.params)] + list(b.data)

    def handle_rigid_body(self, b: Block) -> List[str]:
        """``*RIGID BODY``: Abaqus uses ``PIN NSET``/``TIE NSET`` for the node set that
        moves with the reference node; ccx calls that simply ``NSET`` and rejects the
        Abaqus spellings.  Map them, keep ``REF NODE``/``ROT NODE``/``ELSET``."""
        keep: "OrderedDict[str, Optional[str]]" = OrderedDict()
        for k, v in b.params.items():
            ku = k.upper().replace(" ", "")
            if ku in ("PINNSET", "TIENSET", "NSET"):
                keep["NSET"] = v
            elif ku == "REFNODE":
                keep["REF NODE"] = v
            elif ku == "ROTNODE":
                keep["ROT NODE"] = v
            elif ku == "ELSET":
                keep["ELSET"] = v
            else:
                self.report.note(f"*RIGID BODY parameter {k} dropped (Abaqus-only).", once=True)
        if any(k.upper().replace(" ", "") in ("PINNSET", "TIENSET") for k in b.params):
            self.report.warn("*RIGID BODY: Abaqus PIN/TIE NSET mapped to ccx NSET (the set moves "
                             "rigidly with REF NODE); the pin-vs-tie DOF nuance may differ — verify.",
                             once=True)
        return [emit_keyword("RIGID BODY", keep)] + list(b.data)

    def handle_contact_pair(self, b: Block) -> List[str]:
        """``*CONTACT PAIR``: ccx *requires* a ``TYPE`` (Abaqus lets it default to
        surface-to-surface) and does not understand Abaqus-only parameters such as
        ``SUPPLEMENTARY CONSTRAINTS``/``TIED``/``GEOMETRIC CORRECTION``."""
        ccx_ok = {"INTERACTION", "TYPE", "SMALL SLIDING", "ADJUST", "CYCLIC SYMMETRY"}
        keep: "OrderedDict[str, Optional[str]]" = OrderedDict()
        for k, v in b.params.items():
            if k in ccx_ok:
                keep[k] = v
            else:
                self.report.note(f"*CONTACT PAIR parameter {k} dropped (Abaqus-only; not read by "
                                 f"ccx).", once=True)
        if "TYPE" not in keep:
            keep["TYPE"] = "SURFACE TO SURFACE"
            self.report.note("*CONTACT PAIR without TYPE -> TYPE=SURFACE TO SURFACE (Abaqus default; "
                             "ccx requires it explicitly).", once=True)
        return [emit_keyword("CONTACT PAIR", keep)] + list(b.data)

    def handle_surface(self, b: Block) -> List[str]:
        if (b.param("TYPE") or "").upper().startswith("ANALYTICAL"):
            return self._commented(b, "*SURFACE TYPE=ANALYTICAL RIGID is unsupported by ccx; mesh the "
                                      "rigid surface with elements instead.")
        is_node = (b.param("TYPE") or "").upper() == "NODE"
        out = [emit_keyword("SURFACE", b.params)]
        for rec in merged_data_records(b):
            f = [x for x in rec if x != ""]
            if not f:
                continue
            if is_node:
                # ccx node-based *SURFACE accepts exactly one node/nset per line; Abaqus
                # may append a weight ("NSET, 1."), which ccx rejects with "only one entry
                # per line allowed".  Keep just the node/nset.
                out.append(f[0])
                continue
            if len(f) >= 2 and f[1].upper() in ("SPOS", "SNEG"):
                self.report.warn("*SURFACE shell face SPOS/SNEG: ccx handles shell faces differently; "
                                 "verify.", once=True)
            out.append(", ".join(f))
        return out

    # ======================================================================
    def convert(self, blocks: List[Block]) -> List[str]:
        if any(b.keyword in ("PART", "INSTANCE", "ASSEMBLY") for b in blocks):
            blocks = flatten_assembly(blocks, self.report, self.opt)
        self.build_geometry(blocks)
        self._check_overconstraints(blocks)
        out: List[str] = []
        for b in blocks:
            if b.keyword == "HEADING":
                out.append("*HEADING")
                out.extend(b.data)
                break
        out.extend(self.emit_geometry())
        out.extend(self.emit_other(blocks))
        return out

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

PART_PER_INSTANCE = {"SOLID SECTION", "SHELL SECTION", "BEAM SECTION", "MEMBRANE SECTION",
                     "ORIENTATION", "DISTRIBUTION", "SURFACE"}


# Keywords whose members are elements, so a bare instance-qualified id (``I2.7``) takes
# the element offset, not the node offset.  Covers element/face-based loads (*DLOAD,
# *DSLOAD, *DFLUX, *DFILM, *FILM, *RADIATE), the element sections, and element output.
# (Nodal loads/BCs — *CLOAD, *CFLUX, *BOUNDARY — are absent, so they take the node offset.)
ELEM_REF_KW = {"DLOAD", "ELSET", "DSLOAD", "DFLUX", "DFILM", "FILM", "RADIATE",
               "SOLID SECTION", "SHELL SECTION", "BEAM SECTION", "MEMBRANE SECTION",
               "EL PRINT", "EL FILE", "ELEMENT OUTPUT"}

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


def make_namer(report: Report):
    """A consistent name factory that keeps CalculiX's 20-significant-character set/
    surface-name limit: the same logical name always maps to the same <=20-char
    unique string, so a definition and every reference stay in sync."""
    memo: Dict[str, str] = {}
    used: set = set()

    def namer(*parts) -> str:
        base = "_".join(str(p) for p in parts).upper()
        if base in memo:
            return memo[base]
        cand = base if len(base) <= 20 else base[:20]
        if cand in used:
            i = 1
            while True:
                sfx = f"~{i}"
                cand = base[:20 - len(sfx)] + sfx
                if cand not in used:
                    break
                i += 1
            report.warn("Flattened set/surface names collide within CalculiX's 20-character "
                        "significant-name limit and were uniquified; verify set references.", once=True)
        elif len(base) > 20:
            report.note("A flattened set/surface name exceeded 20 characters and was truncated "
                        "(ccx keeps only the first 20).", once=True)
        used.add(cand)
        memo[base] = cand
        return cand

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
            if b.keyword in GEOM_KW or b.keyword in PART_PER_INSTANCE:
                continue
            out.append(b)
    return out


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
        report.warn(f"*INSTANCE {inst['name']} is rotated; node coords are transformed but any "
                    f"part *ORIENTATION vectors are NOT rotated — verify material directions.", once=True)
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
    for b in parts.get(inst["part"], []) + inst["extra"]:
        if b.keyword in ("SOLID SECTION", "SHELL SECTION", "BEAM SECTION", "MEMBRANE SECTION"):
            out.append(_remap_named(b, prefix, ("ELSET", "ORIENTATION"), namer))
        elif b.keyword == "ORIENTATION":
            out.append(_remap_named(b, prefix, ("NAME",), namer))
        elif b.keyword == "DISTRIBUTION":
            out.append(_remap_named(b, prefix, ("NAME",), namer))
        elif b.keyword == "SURFACE":
            out.append(_remap_surface(b, prefix, namer))
    return out, gmax_node, gmax_elem, (node_off, elem_off)


def _emit_assembly_blocks(assembly_blocks: List[Block], maps, namer) -> List[Block]:
    """Translate assembly-level sets / surfaces / constraints, resolving instance-qualified
    members (``Instance.id`` / ``Instance.setname``) to the flat global numbering."""
    def resolve(tok: str):
        sr = _split_instance_ref(tok, maps)
        if sr is not None and sr[1]:
            iname, rest = sr
            if re.fullmatch(r"[-+]?\d+", rest):
                return ("id", int(rest) + maps[iname][0])
            return ("name", namer(iname, rest))
        return ("raw", tok)

    out: List[Block] = []
    for b in assembly_blocks:
        kw = b.keyword
        if kw in ("NSET", "ELSET"):
            name = (b.param("NSET") if kw == "NSET" else b.param("ELSET")) or ""
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
                            kind, val = resolve(tok)
                            (ids if kind == "id" else names).append(val)
            if ids:
                out.append(set_block(kw, name.upper(), ids))
            if names:
                out.append(mkblock(kw, [(kw, name.upper())], [", ".join(str(n) for n in names)]))
        elif kw == "SURFACE":
            data = []
            for rec in merged_data_records(b):
                f = [x for x in rec if x != ""]
                if not f:
                    continue
                kind, val = resolve(f[0])
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
        if blk.keyword in ("NODE", "ELEMENT"):
            continue
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


def _remap_named(b: Block, prefix: str, keys: Sequence[str], namer) -> Block:
    p: "OrderedDict[str, Optional[str]]" = OrderedDict(b.params)
    for k in keys:
        if k in p and p[k]:
            p[k] = namer(prefix, p[k])
    return Block(b.keyword, p, list(b.data))


def _remap_surface(b: Block, prefix: str, namer) -> Block:
    p: "OrderedDict[str, Optional[str]]" = OrderedDict(b.params)
    if "NAME" in p and p["NAME"]:
        p["NAME"] = namer(prefix, p["NAME"])
    data = []
    for rec in merged_data_records(b):
        f = [x for x in rec if x != ""]
        if not f:
            continue
        data.append(", ".join([namer(prefix, f[0])] + f[1:]))
    return Block("SURFACE", p, data)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def default_output(input_path: str) -> str:
    stem, _ = os.path.splitext(input_path)
    return stem + "_ccx.inp"


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Convert an Abaqus .inp file to a CalculiX (ccx) .inp file.",
        epilog="The output is a starting point: always review the [WARNING]/[NOTE] lines "
               "at the top of the file and check it against your ccx version.")
    ap.add_argument("input", help="Abaqus input deck (.inp)")
    ap.add_argument("-o", "--output", help="output file (default: <input>_ccx.inp)")
    ap.add_argument("--solid-dof", action="store_true",
                    help="force translational-only DOFs when expanding ENCASTRE/PINNED/*SYMM "
                         "(use for solid-only models that have no rotational DOFs)")
    ap.add_argument("--no-log", action="store_true", help="do not write a .log report file")
    ap.add_argument("--quiet", action="store_true", help="suppress the report on stderr")
    args = ap.parse_args(argv)

    report = Report()
    blocks = read_blocks(args.input, report)
    if not blocks:
        sys.stderr.write(f"abq2ccx: no keywords parsed from {args.input}\n")
        return 1

    conv = Converter(report, args)
    try:
        body = conv.convert(blocks)
    except Exception as exc:                # surface a clean message, not a bare traceback
        sys.stderr.write(f"abq2ccx: conversion failed ({type(exc).__name__}: {exc}).\n"
                         f"Please report this deck. Run with PYTHONFAULTHANDLER for a traceback.\n")
        return 2

    out_path = args.output or default_output(args.input)
    text = "\n".join(report.header_comment_lines() + body) + "\n"
    with open(out_path, "w") as fh:
        fh.write(text)

    if not args.no_log:
        log_path = os.path.splitext(out_path)[0] + ".log"
        with open(log_path, "w") as fh:
            fh.write(report.text())

    if not args.quiet:
        sys.stderr.write(
            f"abq2ccx: wrote {out_path} "
            f"({len(conv.geom.nodes)} nodes, {len(conv.geom.elements)} elements, "
            f"{report.n_warnings} warning(s))\n")
        sys.stderr.write(report.text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
