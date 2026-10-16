#!/usr/bin/env python3
"""Regression tests for abq2ccx.

Run directly:   python tests/test_convert.py
or with pytest: pytest tests/

The checks convert each bundled example deck and assert that the resulting
CalculiX model is referentially consistent (every element node, set member and
load/section reference resolves) plus a handful of conversion-specific
expectations.
"""

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import abq2ccx as A  # noqa: E402

EXAMPLES = os.path.join(ROOT, "examples")


class Opt:
    solid_dof = False


def convert(path, **overrides):
    report = A.Report()
    blocks = A.read_blocks(path, report)
    opt = Opt()
    for k, v in overrides.items():
        setattr(opt, k, v)
    conv = A.Converter(report, opt)
    body = "\n".join(conv.convert(blocks))
    return body, conv, report


def convert_str(text, **overrides):
    fd, path = tempfile.mkstemp(suffix=".inp")
    os.close(fd)
    try:
        with open(path, "w") as fh:
            fh.write(text)
        return convert(path, **overrides)
    finally:
        os.unlink(path)


HEX = """*NODE
1, 0.,0.,0.
2, 1.,0.,0.
3, 1.,1.,0.
4, 0.,1.,0.
5, 0.,0.,1.
6, 1.,0.,1.
7, 1.,1.,1.
8, 0.,1.,1.
*ELEMENT, TYPE=C3D8, ELSET=EALL
1, 1,2,3,4,5,6,7,8
"""


def reparse(body):
    """Parse the *emitted* CalculiX deck back into a geometry registry, so checks
    reflect exactly what was written (e.g. emit-time filtering of gappy sets)."""
    report = A.Report()
    fd, path = tempfile.mkstemp(suffix=".inp")
    os.close(fd)
    try:
        with open(path, "w") as fh:
            fh.write(body)
        blocks = A.read_blocks(path, report)
        conv = A.Converter(report, Opt())
        conv.build_geometry(blocks)
        return conv.geom
    finally:
        os.unlink(path)


def dangling_refs(g):
    """Return references that point at undefined nodes/elements (should be empty)."""
    bad = []
    for eid, (_typ, conn) in g.elements.items():
        bad += [f"elem {eid} -> node {n}" for n in conn if n not in g.nodes]
    for name, ids in g.nsets.items():
        bad += [f"nset {name} -> node {i}" for i in ids if i not in g.nodes]
    for name, ids in g.elsets.items():
        bad += [f"elset {name} -> elem {i}" for i in ids if i not in g.elements]
    return bad


def test_le10_thickplate():
    body, _, _ = convert(os.path.join(EXAMPLES, "nle10_thickplate.inp"))
    g = reparse(body)
    assert len(g.nodes) == 465, len(g.nodes)          # 93 nodes/layer x 5 (*NCOPY)
    assert len(g.elements) == 48, len(g.elements)     # 6x4x2 (*ELGEN)
    assert len(g.nsets["AB"]) == 45, len(g.nsets["AB"])   # GEN expanded, not literal triples
    assert len(g.elsets["LOAD"]) == 24, len(g.elsets["LOAD"])  # gappy GENERATE -> real elems only
    assert "*STEP, PERT" not in body                  # PERT (perturbation) dropped for static
    assert "\n*STEP\n" in body
    assert not dangling_refs(g), dangling_refs(g)


def test_composite_shell():
    body, _, _ = convert(os.path.join(EXAMPLES, "composite_shell.inp"))
    assert "TYPE=ENGINEERING CONSTANTS" in body       # orthotropic kept
    assert "*ORIENTATION, NAME=ABQ2CCX_OR1" in body   # ply angle -> synthesized orientation
    assert "3, 45." in body                           # rotation about shell normal
    assert "EDGE, 1, 6" in body                       # ENCASTRE on shell -> 6 DOF
    assert "PLATE, P, 0.01" in body                   # *DSLOAD -> *DLOAD (shell pressure)
    assert "S, E, PEEQ" in body                       # LE->E, PE->PEEQ, CF dropped, deduped
    assert not dangling_refs(reparse(body))


def test_assembly_flatten():
    body, _, _ = convert(os.path.join(EXAMPLES, "assembly_two_blocks.inp"))
    g = reparse(body)
    assert len(g.nodes) == 16                         # two instances, renumbered
    assert len(g.elements) == 2
    assert "I2.7" not in body                         # instance ref resolved
    assert "15, 3, -100." in body                     # I2.7 -> global node 15
    assert "FIX, 1, 3" in body                        # ENCASTRE on solids -> 3 DOF
    assert not dangling_refs(g), dangling_refs(g)


def test_solid_dof_flag():
    body, _, _ = convert(os.path.join(EXAMPLES, "composite_shell.inp"), solid_dof=True)
    assert "EDGE, 1, 3" in body                       # forced translational-only ENCASTRE


def test_comprehensive_coverage():
    body, _, _ = convert(os.path.join(EXAMPLES, "coverage_kitchen_sink.inp"))
    # element substitutions (node-count preserving)
    assert "*ELEMENT, TYPE=C3D8\n" in body            # C3D8H -> C3D8 (hybrid)
    assert "*ELEMENT, TYPE=C3D8I\n" in body           # SC8R -> C3D8I (continuum shell)
    assert "TYPE=COH3D8" not in body                  # COH3D8 -> C3D8 (ccx has no cohesive; warned)
    # organisational cards dropped
    assert "*PREPRINT" not in body and "*PARAMETER" not in body
    # unsupported -> commented out, not silently kept
    assert "** *VISCOELASTIC" in body
    assert "** *CONNECTOR SECTION" in body
    assert "** *INERTIA RELIEF" in body
    # supported, lightly translated
    assert "*CREEP\n" in body and "LAW=STRAIN" not in body   # LAW translated to Norton default
    assert "*USER MATERIAL, CONSTANTS=2" in body
    # *BOUNDARY TYPE= stripped
    assert "*BOUNDARY\nNALL, 1, 3, 0." in body
    # output variable mapping
    assert "S, E, ME, PEEQ" in body                   # LE->E, EE->ME, MISES & ELSE dropped
    assert "U, RF" in body                            # RM->RF, A dropped
    assert "MISES" not in body


def test_element_substitutions():
    rep = A.Report()
    assert A.ccx_element_type("CPEG8", rep) == "CPE8"      # generalized plane strain -> plane strain
    assert A.ccx_element_type("CGAX4R", rep) == "CAX4R"    # generalized axisym -> axisym
    assert A.ccx_element_type("STRI65", rep) == "S6"
    assert A.ccx_element_type("B33", rep) == "B31"
    assert A.ccx_element_type("DASHPOT2", rep) == "DASHPOTA"
    assert A.ccx_element_type("C3D20RH", rep) == "C3D20R"  # hybrid -> base
    assert A.ccx_element_type("C3D20R", rep) == "C3D20R"   # direct, unchanged
    # node-count preservation: a substitution must keep the connectivity length
    for abq, ccx in A.ELEMENT_TYPE_MAP.items():
        assert A.ELEMENT_NNODES[abq] == A.ELEMENT_NNODES[ccx], (abq, ccx)


def test_nset_from_elset():
    # ccx has no *NSET, ELSET=...; the converter expands it to the elset's nodes.
    body, conv, _ = convert_str(HEX + "*NSET, NSET=CLAMP, ELSET=EALL\n")
    assert sorted(conv.geom.nsets["CLAMP"]) == [1, 2, 3, 4, 5, 6, 7, 8]


def test_overconstraint_warning():
    deck = ("*NODE\n1, 0.,0.,0.\n2, 1.,0.,0.\n"
            "*EQUATION\n2\n1, 1, 1.0, 2, 1, -1.0\n"
            "*BOUNDARY\n1, 1, 1\n")
    _, _, rep = convert_str(deck)
    assert any("overconstraint" in m.lower() for _, m in rep.entries)


def test_tie_param_handling():
    # Abaqus-only *TIE params (TYPE=) are stripped; ccx-supported ADJUST is kept.
    deck = (HEX + "*SURFACE, NAME=SS, TYPE=NODE\n1\n*SURFACE, NAME=MM, TYPE=ELEMENT\nEALL, S1\n"
            "*TIE, NAME=T1, TYPE=SURFACE TO SURFACE, ADJUST=NO\nSS, MM\n")
    body, _, _ = convert_str(deck)
    assert "*TIE, NAME=T1" in body
    assert "TYPE=SURFACE" not in body          # Abaqus-only parameter stripped
    assert "ADJUST=NO" in body                 # ccx-supported parameter kept


def test_instance_rotation_order():
    # Abaqus applies the *INSTANCE translation BEFORE the rotation (R(p+T)).
    # node (1,0,0) + T(10,0,0) -> (11,0,0), then 90 deg about z -> (0,11,0).
    deck = ("*PART, NAME=P\n*NODE\n1, 1., 0., 0.\n*ELEMENT, TYPE=MASS, ELSET=E\n1, 1\n*END PART\n"
            "*ASSEMBLY, NAME=A\n*INSTANCE, NAME=I, PART=P\n10., 0., 0.\n0.,0.,0., 0.,0.,1., 90.\n"
            "*END INSTANCE\n*END ASSEMBLY\n")
    body, _, _ = convert_str(deck)
    assert "1, 0, 11, 0" in body               # correct (translate-then-rotate) + zero-snap
    assert "1, 10, 1, 0" not in body           # the wrong rotate-then-translate result


def test_shell_general_section():
    deck = ("*NODE\n1,0.,0.,0.\n2,1.,0.,0.\n3,1.,1.,0.\n4,0.,1.,0.\n"
            "*ELEMENT, TYPE=S4, ELSET=SH\n1,1,2,3,4\n"
            "*MATERIAL, NAME=ST\n*ELASTIC\n200000.,0.3\n"
            "*SHELL GENERAL SECTION, ELSET=SH, MATERIAL=ST\n2.0\n")
    body, _, _ = convert_str(deck)
    assert "*SHELL SECTION" in body and "GENERAL" not in body


def test_step_nlgeom_and_name():
    # NAME dropped from *STEP, NLGEOM kept on the step.
    deck = HEX + "*STEP, NAME=Load, NLGEOM=YES\n*STATIC\n*BOUNDARY\n1, 1, 3\n*END STEP\n"
    body, _, _ = convert_str(deck)
    assert "NLGEOM" in body and "NAME=Load" not in body


def test_amp_keyword_alias():
    body, _, _ = convert_str("*NODE\n1,0.,0.,0.\n*AMP, NAME=A1\n0.,0., 1.,1.\n")
    assert "*AMPLITUDE, NAME=A1" in body


def test_rigid_element_flagged():
    deck = "*NODE\n1,0.,0.,0.\n2,1.,0.,0.\n3,1.,1.,0.\n*ELEMENT, TYPE=R3D3, ELSET=R\n1,1,2,3\n"
    body, _, rep = convert_str(deck)
    assert "*ELEMENT, TYPE=R3D3" in body                       # emitted unchanged
    assert any("rigid" in m.lower() and "R3D3" in m for _, m in rep.entries)


def test_name_length_limit():
    # ccx 2.22's real set-name limit is 80 chars (verified: 80 resolves correctly, >80 stops
    # with 'set name too long').  Flattened names must stay <= 80 but are NOT needlessly
    # truncated below that, so CAE names like Instance_SetName keep full fidelity.
    deck = ("*PART, NAME=PART\n" + HEX +
            "*NSET, NSET=A_VERY_LONG_NODE_SET_NAME_INDEED\n1,2,3,4\n"
            "*NSET, NSET=" + "X" * 78 + "\n1,2\n*END PART\n"
            "*ASSEMBLY, NAME=ASM\n*INSTANCE, NAME=INSTANCE_NUMBER_ONE, PART=PART\n*END INSTANCE\n"
            "*END ASSEMBLY\n*MATERIAL, NAME=ST\n*ELASTIC\n200000.,0.3\n")
    body, _, _ = convert_str(deck)
    import re as _re
    names = [n.strip() for n in
             _re.findall(r"\*(?:NSET|ELSET),\s*(?:NSET|ELSET)=([^,\n]+)", body)]
    assert names and all(len(n) <= 80 for n in names), names
    # the moderate CAE-style name survives un-truncated
    assert "INSTANCE_NUMBER_ONE_A_VERY_LONG_NODE_SET_NAME_INDEED" in names
    # the pathological 78-char part name got prefixed past 80 -> truncated to exactly 80
    assert any(len(n) == 80 for n in names), names


def test_parameter_with_internal_comment():
    # A ** comment inside a *PARAMETER block must NOT terminate it.
    deck = ("*PARAMETER\nl = 2.0\n** a comment inside the block\nw = 3.0\n"
            "*NODE\n1, <l>, <w>, 0.\n*ELEMENT, TYPE=MASS, ELSET=E\n1, 1\n")
    body, conv, _ = convert_str(deck)
    assert conv.geom.nodes[1] == (2.0, 3.0, 0.0)
    assert "<l>" not in body and "<w>" not in body


def test_parameter_forward_reference():
    # Abaqus does not require parameters to be defined before use.
    deck = ("*PARAMETER\na = b*2\nb = 3.0\n*NODE\n1, <a>, 0., 0.\n"
            "*ELEMENT, TYPE=MASS, ELSET=E\n1, 1\n")
    _, conv, _ = convert_str(deck)
    assert conv.geom.nodes[1][0] == 6.0


def test_no_residual_parameter_tokens():
    deck = ("*PARAMETER\nx = 1.5\n*NODE\n1, <x>, 0., 0.\n2, <x>, 1., 0.\n"
            "*ELEMENT, TYPE=T3D2, ELSET=E\n1, 1, 2\n")
    body, _, _ = convert_str(deck)
    import re as _re
    assert not _re.search(r"<[A-Za-z_]\w*>", body)


def test_fortran_d_exponent():
    # Fortran 'D' exponents are legal Abaqus numeric fields.
    deck = "*NODE\n1, 0.0d0, 1.5D2, -2.5d-1\n*ELEMENT, TYPE=MASS, ELSET=E\n1, 1\n"
    _, conv, _ = convert_str(deck)
    assert conv.geom.nodes[1] == (0.0, 150.0, -0.25)


def test_keyword_line_continuation():
    # A keyword line ending in a comma continues onto the next line as *parameters*
    # (not data): '*ELSET, ELSET=SUB,' + 'GENERATE' must parse GENERATE as a param.
    deck = ("*NODE\n1,0,0,0\n2,1,0,0\n*ELEMENT, TYPE=T3D2, ELSET=EALL\n1,1,2\n"
            "*ELSET, ELSET=SUB,\nGENERATE\n1,1,1\n")
    _, conv, _ = convert_str(deck)
    assert list(conv.geom.elset("SUB")) == [1]


def test_coupled_temperature_element_suffix():
    # Coupled temperature-displacement elements: the trailing 'T' is dropped because
    # ccx uses the base element (C3D8T->C3D8, CAX4RT->CAX4R) and the node count is kept.
    r = A.Report()
    assert A.ccx_element_type("C3D8T", r) == "C3D8"
    assert A.ccx_element_type("CAX4RT", r) == "CAX4R"
    assert A.element_node_count("C3D20T") == 20
    body, _, _ = convert_str(HEX.replace("TYPE=C3D8", "TYPE=C3D8T"))
    el = [l for l in body.splitlines() if l.upper().startswith("*ELEMENT")][0]
    assert "C3D8T" not in el.upper() and "C3D8" in el.upper()


def test_hybrid_element_suffix_recurses():
    # Hybrid 'H' is dropped and a base that itself needs mapping is resolved
    # (CPEG8H -> CPEG8 -> CPE8).
    r = A.Report()
    assert A.ccx_element_type("CPEG8H", r) == "CPE8"
    assert A.ccx_element_type("C3D8H", r) == "C3D8"


def test_modified_triangle_element():
    # Modified 6-node triangles map to the plain 6-node triangle (same node count).
    r = A.Report()
    assert A.ccx_element_type("CPS6M", r) == "CPS6"
    assert A.ccx_element_type("CPE6M", r) == "CPE6"
    assert A.element_node_count("CAX6M") == 6


def test_parameter_math_functions():
    # *PARAMETER expressions may use math functions (abs, sqrt, ...); they must be
    # evaluated to numbers, not left as text that would reach the float parser.
    deck = ("*PARAMETER\nx = abs(sqrt(4.0) - 5.0)\n*NODE\n1, <x>, 0., 0.\n"
            "*ELEMENT, TYPE=MASS, ELSET=E\n1,1\n")
    _, conv, _ = convert_str(deck)
    assert conv.geom.nodes[1][0] == 3.0          # abs(2 - 5) == 3


def test_frictionless_friction_dropped():
    # *FRICTION with no positive coefficient is dropped (ccx treats the absence of the
    # card as frictionless; a zero coefficient is a hard error there). mu>0 is kept.
    body, _, _ = convert_str("*SURFACE INTERACTION, NAME=SI\n*FRICTION\n0.0\n")
    assert not [l for l in body.splitlines() if l.strip().upper().startswith("*FRICTION")]
    body2, _, _ = convert_str("*SURFACE INTERACTION, NAME=SI\n*FRICTION\n0.3\n")
    assert any(l.strip().upper().startswith("*FRICTION") for l in body2.splitlines())


def test_nfill_unequal_bounding_sets():
    # *NFILL whose two bounding node sets differ in length fills the common (zip)
    # pairs instead of skipping — a real deck may carry one spurious extra edge node.
    deck = ("*NODE\n1,0.,0.\n3,0.,2.\n101,4.,0.\n104,4.,3.\n"
            "*NGEN,NSET=LEFT\n1,3\n"          # -> nodes 1,2,3   (3 nodes)
            "*NGEN,NSET=RIGHT\n101,104\n"     # -> nodes 101..104 (4 nodes, one extra)
            "*NFILL\nLEFT,RIGHT,2,50\n")      # 2 intervals, node increment 50
    _, conv, _ = convert_str(deck)
    assert {51, 52, 53} <= set(conv.geom.nodes)   # interior of the 3 common pairs


def test_generate_malformed_token_no_crash():
    # A malformed (non-integer) field in a GENERATE record skips that record instead of
    # aborting the whole conversion (matching the *NODE/*ELEMENT one-bad-line handling);
    # a valid GENERATE in the same deck still works.
    deck = ("*NODE\n1,0,0,0\n2,1,0,0\n3,2,0,0\n"
            "*ELEMENT, TYPE=MASS, ELSET=E\n1,1\n2,2\n3,3\n"
            "*ELSET, ELSET=BAD, GENERATE\n1, oops, 1\n"      # malformed -> skipped, no crash
            "*ELSET, ELSET=GOOD, GENERATE\n1, 3, 1\n")       # valid
    _, conv, _ = convert_str(deck)                            # must not raise
    assert list(conv.geom.elset("GOOD")) == [1, 2, 3]


def test_string_parameter_substitution():
    # A string-valued *PARAMETER (quoted) must substitute as its *unquoted* value, so
    # `*Element, type=<eltype>` with eltype="CPS4" emits TYPE=CPS4 (not TYPE="CPS4",
    # which ccx rejects as an unknown element type).
    deck = ('*PARAMETER\neltype = "CPS4"\n*NODE\n1,0,0\n2,1,0\n3,1,1\n4,0,1\n'
            '*ELEMENT, TYPE=<eltype>, ELSET=E\n1,1,2,3,4\n')
    body, _, _ = convert_str(deck)
    el = [l for l in body.splitlines() if l.upper().startswith("*ELEMENT")][0]
    assert "TYPE=CPS4" in el.upper() and '"' not in el


def test_node_surface_drops_weight():
    # ccx node-based *SURFACE accepts one entry per line; an Abaqus weight ("NS, 1.")
    # must be dropped to just the node/nset.
    deck = "*NODE\n1,0,0,0\n*NSET,NSET=NS\n1\n*SURFACE, TYPE=NODE, NAME=S\nNS, 1.\n"
    body, _, _ = convert_str(deck)
    assert "NS" in [l.strip() for l in body.splitlines()]      # bare 'NS', no ', 1.'


def test_contact_pair_default_type():
    # ccx requires a TYPE on *CONTACT PAIR; Abaqus/Standard defaults it to node-to-surface
    # (and the note points at face-to-face if ccx struggles). Abaqus-only params drop.
    deck = "*SURFACE INTERACTION, NAME=SI\n*CONTACT PAIR, INTERACTION=SI, SUPPLEMENTARY CONSTRAINTS=NO\nA, B\n"
    body, _, rep = convert_str(deck)
    cp = [l for l in body.splitlines() if l.upper().startswith("*CONTACT PAIR")][0]
    assert "TYPE=NODE TO SURFACE" in cp.upper() and "SUPPLEMENTARY" not in cp.upper()
    assert "SURFACE TO SURFACE" in rep.text()


def test_rigid_body_pin_nset_mapped():
    # Abaqus *RIGID BODY, PIN NSET=... -> ccx NSET=... (ccx rejects the PIN NSET spelling).
    deck = ("*NODE\n1,0,0,0\n2,1,0,0\n3,2,0,0\n*NSET,NSET=RN\n1,2\n*NSET,NSET=REF\n3\n"
            "*RIGID BODY, REF NODE=REF, PIN NSET=RN\n")
    body, _, _ = convert_str(deck)
    rb = [l for l in body.splitlines() if "RIGID BODY" in l.upper()][0]
    assert "NSET=RN" in rb.upper() and "PIN NSET" not in rb.upper()


def test_meshgen_float_formatted_integers():
    # Exporters sometimes write integer count/increment fields of the mesh-gen cards in
    # float form ("2.0"); the expanders must accept them, not abort the whole deck.
    deck = ("*NODE\n1, 0.,0.,0.\n5, 4.,0.,0.\n"
            "*NGEN, NSET=LINE\n1, 5, 2.0\n"
            "*ELEMENT, TYPE=T3D2, ELSET=E\n1, 1, 3\n")
    _, conv, _ = convert_str(deck)
    assert {1, 3, 5} <= set(conv.geom.nodes)        # NGEN 1->5 step 2 -> nodes 1,3,5


def test_descending_set_emits_ascending_generate():
    # A descending arithmetic run must NOT emit an invalid "5, 1, -1" GENERATE (ccx
    # would silently empty the set); emit the equivalent ascending range instead.
    import re as _re
    deck = ("*NODE\n1,0.,0.,0.\n2,1.,0.,0.\n3,2.,0.,0.\n4,3.,0.,0.\n5,4.,0.,0.\n"
            "*ELEMENT, TYPE=MASS, ELSET=EALL\n1,1\n"
            "*NSET, NSET=DESC\n5, 4, 3, 2, 1\n")
    body, _, _ = convert_str(deck)
    lines = body.splitlines()
    gen = next((lines[i + 1] for i, l in enumerate(lines)
                if _re.search(r"(?i)\*nset.*DESC.*generate", l)), None)
    assert gen is not None, "expected a GENERATE line for the descending run"
    a, b, inc = (int(x) for x in gen.split(","))
    assert a <= b and inc > 0, f"invalid GENERATE emitted: {gen!r}"
    assert set(reparse(body).nsets.get("DESC", [])) == {1, 2, 3, 4, 5}


def test_instance_space_separated_transform():
    # Some exporters write the *Instance offset space-separated ("10 0 0") instead of
    # comma-separated; flattening must parse it, not crash on float("10 0 0").
    deck = ("*Part, name=P\n*Node\n1,0.,0.,0.\n2,1.,0.,0.\n"
            "*Element, type=T3D2, elset=E\n1,1,2\n*End Part\n"
            "*Assembly, name=A\n*Instance, name=I, part=P\n10 0 0\n*End Instance\n*End Assembly\n")
    _, conv, _ = convert_str(deck)
    xs = {round(x, 6) for (x, _y, _z) in conv.geom.nodes.values()}
    assert {10.0, 11.0} <= xs           # both part nodes translated by (10,0,0)


def test_instance_qualified_set_param_resolved():
    # Output requests reference sets through a PARAMETER (elset=/nset=), not a data line.
    # An instance-qualified value (I.body / I.corner) must flatten to the renamed global
    # set, or ccx reports "elementset I.BODY does not exist" and drops the request.
    deck = ("*Part, name=P\n*Node\n1,0.,0.,0.\n2,1.,0.,0.\n3,1.,1.,0.\n4,0.,1.,0.\n"
            "*Element, type=CPS4, elset=body\n1,1,2,3,4\n*Nset, nset=corner\n1\n"
            "*Solid Section, elset=body, material=m\n*End Part\n"
            "*Assembly, name=A\n*Instance, name=I, part=P\n*End Instance\n*End Assembly\n"
            "*Material, name=m\n*Elastic\n1.,0.3\n"
            "*Step\n*Static\n*El Print, elset=I.body\nS\n*Node Print, nset=I.corner\nU\n*End Step\n")
    body, _, _ = convert_str(deck)
    elp = [l for l in body.splitlines() if l.upper().startswith("*EL PRINT")][0]
    ndp = [l for l in body.splitlines() if l.upper().startswith("*NODE PRINT")][0]
    assert "ELSET=I_BODY" in elp.upper() and "I.BODY" not in elp.upper()
    assert "NSET=I_CORNER" in ndp.upper() and "I.CORNER" not in ndp.upper()
    # the renamed sets are actually emitted, so the references resolve
    assert any("ELSET=I_BODY" in l.upper() for l in body.splitlines())
    assert any("NSET=I_CORNER" in l.upper() for l in body.splitlines())


def test_rigid_body_refnode_instance_qualified():
    # *RIGID BODY names its control node through REF NODE= (a parameter).  An instance-
    # qualified value must resolve to the renamed node set that flattening emits.
    deck = ("*Part, name=P\n*Node\n1,0.,0.,0.\n2,1.,0.,0.\n3,1.,1.,0.\n4,0.,1.,0.\n"
            "*Element, type=CPS4, elset=body\n1,1,2,3,4\n*Nset, nset=ref\n1\n*End Part\n"
            "*Assembly, name=A\n*Instance, name=I, part=P\n*End Instance\n"
            "*Rigid Body, ref node=I.ref, elset=I.body\n*End Assembly\n")
    body, _, _ = convert_str(deck)
    rb = [l for l in body.splitlines() if "RIGID BODY" in l.upper()][0]
    # the flattened single-node set I_REF is further resolved to its node NUMBER
    # (ccx requires REF NODE to be a node id, not a set name)
    assert "REF NODE=1" in rb.upper() and "I_BODY" in rb.upper()
    assert "I.REF" not in rb.upper() and "I.BODY" not in rb.upper()
    assert any("NSET=I_REF" in l.upper() for l in body.splitlines())


def test_assembly_instance_set_three_level_ref():
    # Some exporters qualify a member with the assembly name as well (Assembly.Instance.set).
    # Flattening must strip the outer assembly level and resolve to the renamed instance set.
    deck = ("*Part, name=P\n*Node\n1,0.,0.,0.\n2,1.,0.,0.\n3,1.,1.,0.\n4,0.,1.,0.\n"
            "*Element, type=CPS4, elset=body\n1,1,2,3,4\n*Nset, nset=edge\n1,2\n"
            "*Solid Section, elset=body, material=m\n*End Part\n"
            "*Assembly, name=ASM\n*Instance, name=INST, part=P\n*End Instance\n*End Assembly\n"
            "*Material, name=m\n*Elastic\n1.,0.3\n"
            "*Step\n*Static\n*Boundary\nASM.INST.edge, 1, 2\n*End Step\n")
    body, _, _ = convert_str(deck)
    lines = body.splitlines()
    i = next(k for k, l in enumerate(lines) if l.upper().startswith("*BOUNDARY"))
    assert lines[i + 1].upper().startswith("INST_EDGE")          # ASM. stripped, INST.edge joined
    assert "ASM.INST" not in body.upper() and "INST.EDGE" not in body.upper()
    assert any("NSET=INST_EDGE" in l.upper() for l in lines)     # the set it points at exists


def test_element_load_uses_element_offset():
    # An element/face-based load that names an element by instance-qualified id (I2.1)
    # must take the ELEMENT offset, not the node offset.  Two single-element instances:
    # I2's element 1 -> global element 2 (elem_off=1), which must NOT be read as node 5
    # (node_off=4).  Guards *DFLUX/*DFILM/*FILM/*RADIATE being treated as element-based.
    deck = ("*Part, name=P\n*Node\n1,0.,0.,0.\n2,1.,0.,0.\n3,1.,1.,0.\n4,0.,1.,0.\n"
            "*Element, type=CPS4, elset=e\n1,1,2,3,4\n*Solid Section, elset=e, material=m\n1.0\n*End Part\n"
            "*Assembly, name=A\n*Instance, name=I1, part=P\n*End Instance\n"
            "*Instance, name=I2, part=P\n2.,0.,0.\n*End Instance\n*End Assembly\n"
            "*Material, name=m\n*Elastic\n1.,0.3\n"
            "*Step\n*Heat Transfer\n*Dflux\nI2.1, BF, 10.0\n*End Step\n")
    body, _, _ = convert_str(deck)
    lines = body.splitlines()
    i = next(k for k, l in enumerate(lines) if l.upper().startswith("*DFLUX"))
    first = lines[i + 1].split(",")[0].strip()
    assert first == "2", f"*DFLUX element ref took the wrong offset: expected '2', got '{first}'"


def test_named_bc_condition_on_instance_set():
    # *Boundary with a named condition (ENCASTRE) on an instance node set: the set ref must
    # be flattened (I.fix -> I_FIX) *before* the condition is expanded to DOF ranges, so the
    # emitted lines name the renamed set.  Guards the flatten-then-expand ordering.
    deck = ("*Part, name=P\n*Node\n1,0.,0.,0.\n2,1.,0.,0.\n3,1.,1.,0.\n4,0.,1.,0.\n"
            "5,0.,0.,1.\n6,1.,0.,1.\n7,1.,1.,1.\n8,0.,1.,1.\n"
            "*Element, type=C3D8, elset=e\n1,1,2,3,4,5,6,7,8\n*Nset, nset=fix\n1,2,3,4\n"
            "*Solid Section, elset=e, material=m\n*End Part\n"
            "*Assembly, name=A\n*Instance, name=I, part=P\n*End Instance\n*End Assembly\n"
            "*Material, name=m\n*Elastic\n1.,0.3\n"
            "*Step\n*Static\n*Boundary\nI.fix, ENCASTRE\n*End Step\n")
    body, _, _ = convert_str(deck)
    lines = body.splitlines()
    i = next(k for k, l in enumerate(lines) if l.upper().startswith("*BOUNDARY"))
    assert lines[i + 1].upper().startswith("I_FIX,")     # resolved set name, not I.fix
    assert "1, 3" in lines[i + 1]                          # solid model -> ENCASTRE = DOF 1..3
    assert "I.FIX" not in body.upper()


def test_damage_initiation_emitted_for_ccx223():
    # ccx 2.23 added *DAMAGE INITIATION: it is now emitted (pass-through, with its data),
    # while *DAMAGE EVOLUTION (still not in ccx) stays commented out.
    deck = ("*Material, name=m\n*Elastic\n210000., 0.3\n"
            "*Damage Initiation, criterion=DUCTILE\n0.1, 0.0, 0.0\n"
            "*Damage Evolution, type=DISPLACEMENT\n0.001,\n")
    body, _, _ = convert_str(deck)
    lines = body.splitlines()
    i = next((k for k, l in enumerate(lines) if l.upper().startswith("*DAMAGE INITIATION")), None)
    assert i is not None, "expected *DAMAGE INITIATION emitted as a real card"
    assert lines[i + 1].strip().startswith("0.1")          # its data row survives
    de = [l for l in lines if "DAMAGE EVOLUTION" in l.upper()]
    assert de and all(l.lstrip().startswith("**") for l in de)  # evolution commented out


def test_new_abaqus_keywords_targeted_guidance():
    # Newer Abaqus keywords (2024/2025) are recognised and commented with TARGETED guidance,
    # not the generic "no direct CalculiX equivalent" fallback.
    deck = ("*Material, name=m\n*Elastic\n1.,0.3\n*Electrical Resistivity\n1.7e-8,\n"
            "*Step\n*Static\n*Step Cycling\n10,\n*End Step\n")
    _, _, rep = convert_str(deck)
    txt = rep.text().upper()
    assert "ELECTRICAL CONDUCTIVITY" in txt                 # resistivity -> conductivity hint
    assert "STEP CYCLING" in txt and "REPEATED STEPS" in txt
    assert "NO DIRECT CALCULIX EQUIVALENT" not in txt       # targeted, not the generic fallback


def test_t2d3_maps_to_t3d3():
    # 3-node 2D truss has no ccx name; route it to the (node-count-identical) 3-node 3D
    # truss T3D3 instead of emitting a literal T2D3 that ccx rejects.
    assert A.ccx_element_type("T2D3", A.Report()) == "T3D3"


def test_independent_instance_undefined_part_no_crash():
    # An independent *Instance can carry its own mesh while naming a PART= that was never
    # declared (typo / un-included file).  This must not KeyError out of the conversion.
    deck = ("*Assembly, name=A\n*Instance, name=I, part=GHOST\n"
            "*Node\n1,0.,0.,0.\n2,1.,0.,0.\n*Element, type=T3D2, elset=e\n1,1,2\n"
            "*End Instance\n*End Assembly\n")
    body, _, _ = convert_str(deck)
    assert any(l.upper().startswith("*ELEMENT") for l in body.splitlines())  # mesh still emitted


def test_dsload_unmappable_face_warns():
    # *DSLOAD on a surface whose face is not S1..S6 (e.g. a shell SPOS) cannot become a ccx
    # Px label; it must warn rather than silently emit a bare 'P' that ccx rejects.
    deck = ("*Node\n1,0.,0.,0.\n2,1.,0.,0.\n3,1.,1.,0.\n4,0.,1.,0.\n*Element,type=S4,elset=e\n1,1,2,3,4\n"
            "*Surface,type=element,name=sf\ne, SPOS\n*Step\n*Static\n*Dsload\nsf, P, 5.0\n*End Step\n")
    _, _, rep = convert_str(deck)
    assert "px equivalent" in rep.text().lower()


def test_ngen_descending_range_warns():
    # A descending *NGEN range with the default positive increment yields no nodes; that
    # silent edge-drop must surface as a warning.
    deck = "*Node\n1,0.,0.,0.\n10,9.,0.,0.\n*Ngen, nset=line\n10,1\n"
    _, _, rep = convert_str(deck)
    assert "generated no nodes" in rep.text().lower()


def test_cohesive_element_substituted_to_continuum():
    # ccx has no cohesive element; COH* is approximated by the node-count-identical
    # continuum element so the mesh is at least parseable, with a strong warning.
    deck = ("*Node\n1,0.,0.,0.\n2,1.,0.,0.\n3,1.,1.,0.\n4,0.,1.,0.\n"
            "5,0.,0.,1.\n6,1.,0.,1.\n7,1.,1.,1.\n8,0.,1.,1.\n"
            "*Element, type=COH3D8, elset=c\n1,1,2,3,4,5,6,7,8\n")
    body, _, rep = convert_str(deck)
    el = [l for l in body.splitlines() if l.upper().startswith("*ELEMENT")][0]
    assert "TYPE=C3D8" in el.upper() and "COH" not in el.upper()
    txt = rep.text().lower()
    assert "cohesive" in txt and "zero-thickness" in txt        # behaviour-lost + degeneracy warning


def test_cohesive_2d_maps_to_plane_strain():
    deck = "*Node\n1,0.,0.\n2,1.,0.\n3,1.,1.\n4,0.,1.\n*Element, type=COH2D4, elset=c\n1,1,2,3,4\n"
    body, _, _ = convert_str(deck)
    el = [l for l in body.splitlines() if l.upper().startswith("*ELEMENT")][0]
    assert "TYPE=CPE4" in el.upper()


def test_cohesive_section_becomes_solid_section():
    # The cohesive ELEMENT is substituted by a continuum, so *Cohesive Section must become
    # a *Solid Section (same elset+material) — otherwise the substituted elements are
    # section-less and ccx errors "no material assigned".
    deck = ("*Node\n1,0.,0.,0.\n2,1.,0.,0.\n3,1.,1.,0.\n4,0.,1.,0.\n"
            "5,0.,0.,1.\n6,1.,0.,1.\n7,1.,1.,1.\n8,0.,1.,1.\n"
            "*Element, type=COH3D8, elset=c\n1,1,2,3,4,5,6,7,8\n"
            "*Cohesive Section, elset=c, material=glue, response=TRACTION SEPARATION\n"
            "*Material, name=glue\n*Elastic\n1000., 0.3\n")
    body, _, _ = convert_str(deck)
    sol = [l for l in body.splitlines() if l.upper().startswith("*SOLID SECTION")]
    assert any("ELSET=C," in l.upper() and "MATERIAL=GLUE" in l.upper() for l in sol)
    assert "** *COHESIVE SECTION" not in body          # translated, not commented out


def test_pore_pressure_element_suffix_dropped():
    # ccx has no coupled displacement/pore-pressure element; CAX4P -> CAX4 (pore-pressure
    # DOF dropped) with a warning, analogous to the coupled-temperature T suffix.
    deck = "*Node\n1,0.,0.\n2,1.,0.\n3,1.,1.\n4,0.,1.\n*Element, type=CAX4P, elset=e\n1,1,2,3,4\n"
    body, _, rep = convert_str(deck)
    el = [l for l in body.splitlines() if l.upper().startswith("*ELEMENT")][0]
    assert "TYPE=CAX4" in el.upper() and "CAX4P" not in el.upper()
    assert "pore-pressure" in rep.text().lower()


def test_empty_dload_op_new_passthrough():
    # *DLOAD, OP=NEW with no data is valid ccx and MEANS something (remove all previous
    # distributed loads); it must pass through, not be commented out.
    deck = ("*Node\n1,0,0,0\n2,1,0,0\n3,1,1,0\n4,0,1,0\n*Element,type=CPS4,elset=E\n1,1,2,3,4\n"
            "*Step\n*Static\n*Dload, OP=NEW\n*End Step\n")
    body, _, _ = convert_str(deck)
    live = [l for l in body.splitlines() if not l.lstrip().startswith("**")]
    assert any(l.upper().startswith("*DLOAD") and "OP=NEW" in l.upper() for l in live)


def test_assembly_element_instance_qualified_connectivity():
    # Assembly-level spring/connector/mass elements often write connectivity as
    # instance-qualified refs (I1.2, I2.1); these must resolve to global node ids so the
    # element registers instead of being skipped as non-numeric.
    deck = ("*Part, name=P\n*Node\n1,0.,0.,0.\n2,1.,0.,0.\n3,1.,1.,0.\n4,0.,1.,0.\n"
            "*Element, type=CPS4, elset=e\n1,1,2,3,4\n*End Part\n"
            "*Assembly, name=A\n*Instance, name=I1, part=P\n*End Instance\n"
            "*Instance, name=I2, part=P\n5.,0.,0.\n*End Instance\n"
            "*Element, type=SPRINGA, elset=spr\n1, I1.2, I2.1\n*End Assembly\n")
    _, conv, rep = convert_str(deck)
    springs = [(typ, conn) for typ, conn in conv.geom.elements.values() if typ == "SPRINGA"]
    assert springs == [("SPRINGA", [2, 5])]      # I1.2 -> 2 (off 0), I2.1 -> 5 (off 4)
    assert "skipped" not in rep.text().lower()


def test_smooth_step_amplitude_sampled():
    # ccx has no DEFINITION=SMOOTH STEP (it would silently degrade to a linear ramp);
    # the quintic is sampled into tabular points: midpoint exact, quarter-point quintic.
    deck = "*Amplitude, name=SS, definition=SMOOTH STEP\n0., 0., 1., 1.\n"
    body, _, rep = convert_str(deck)
    lines = body.splitlines()
    i = next(k for k, l in enumerate(lines) if l.upper().startswith("*AMPLITUDE"))
    assert "DEFINITION" not in lines[i].upper()               # param dropped from the card
    pts = [tuple(float(x) for x in l.split(",")) for l in lines[i + 1:i + 12]]
    assert len(pts) == 11 and pts[0] == (0.0, 0.0) and pts[-1] == (1.0, 1.0)
    assert abs(dict(pts)[0.5] - 0.5) < 1e-12                  # quintic midpoint
    assert abs(dict(pts)[0.2] - 0.05792) < 1e-9               # x^3(10-15x+6x^2) at 0.2
    assert "sampled" in rep.text().lower()


def test_dload_unsupported_body_load_dropped():
    # ccx supports only GRAV and CENTRIF body loads; ROTA/CORIO/CENT/ROTDYNF are rejected
    # outright by ccx, so they must be dropped (warned) rather than emitted — keeping the
    # supported lines so the rest of the *DLOAD survives (forum: "ROTA not supported").
    deck = ("*Node\n1,0.,0.,0.\n2,1.,0.,0.\n3,1.,1.,0.\n4,0.,1.,0.\n"
            "5,0.,0.,1.\n6,1.,0.,1.\n7,1.,1.,1.\n8,0.,1.,1.\n"
            "*Element,type=C3D8,elset=E\n1,1,2,3,4,5,6,7,8\n"
            "*Material,name=m\n*Elastic\n1.,.3\n*Density\n1e-9\n*Solid Section,elset=E,material=m\n"
            "*Step\n*Static\n*Dload\nE, GRAV, 9810., 0.,0.,-1.\nE, ROTA, 500., 0.,0.,0., 0.,0.,1.\n*End Step\n")
    body, _, rep = convert_str(deck)
    live = [l for l in body.splitlines() if not l.lstrip().startswith("**")]
    assert any("GRAV" in l.upper() for l in live)           # GRAV kept
    assert not any("ROTA" in l.upper() for l in live)        # ROTA dropped from live output
    assert "rota" in rep.text().lower()                       # and warned


def test_assembly_node_not_overwritten_by_instance():
    # Assembly-level *Node cards (Abaqus/CAE reference points placed inside *Assembly) must
    # keep their ids and be emitted BEFORE the instances, which are then numbered above them
    # so an assembly node id never overwrites a flattened part node id (GitHub issue #2).
    deck = ("*Part, name=p\n*Node\n1,0.,0.,0.\n2,1.,0.,0.\n3,1.,1.,0.\n4,0.,1.,0.\n"
            "*Element, type=CPS4, elset=e\n1,1,2,3,4\n*End Part\n"
            "*Assembly, name=A\n*Instance, name=p-1, part=p\n*End Instance\n"
            "*Node\n999, 5.,5.,5.\n*End Assembly\n")
    _, conv, _ = convert_str(deck)
    assert conv.geom.nodes.get(999) == (5., 5., 5.)          # assembly ref node survives
    inst_ids = [n for n in conv.geom.nodes if n != 999]
    assert len(inst_ids) == 4 and all(n > 999 for n in inst_ids)  # instances offset above it


def test_coupling_refnode_set_resolved_and_empty_kinematic():
    # CAE writes REF NODE=<set name> (ccx hard error) and an empty *Kinematic (ccx: runs
    # but silently creates NO constraint).  Both must be repaired.
    deck = ("*Node\n1,0.,0.,0.\n2,1.,0.,0.\n3,1.,1.,0.\n4,0.,1.,0.\n"
            "5,0.,0.,1.\n6,1.,0.,1.\n7,1.,1.,1.\n8,0.,1.,1.\n9,0.5,0.5,2.\n"
            "*Nset, nset=_PickedSet8, internal\n9\n*Element, type=C3D8, elset=E\n1,1,2,3,4,5,6,7,8\n"
            "*Solid Section, elset=E, material=m\n*Material, name=m\n*Elastic\n1.,.3\n"
            "*Surface, type=ELEMENT, name=TOP\nE, S2\n"
            "*Coupling, constraint name=C1, ref node=_PickedSet8, surface=TOP\n*Kinematic\n")
    body, _, _ = convert_str(deck)
    lines = body.splitlines()
    cp = next(l for l in lines if l.upper().startswith("*COUPLING"))
    assert "REF NODE=9" in cp.upper()
    ki = next(i for i, l in enumerate(lines) if l.upper().startswith("*KINEMATIC"))
    assert lines[ki + 1].replace(" ", "") == "1,3"


def test_kinematic_rotational_dofs_clamped():
    deck = ("*Node\n1,0.,0.,0.\n2,1.,0.,0.\n3,1.,1.,0.\n4,0.,1.,0.\n9,0.5,0.5,1.\n"
            "*Nset, nset=R\n9\n*Element, type=CPS4, elset=E\n1,1,2,3,4\n"
            "*Surface, type=ELEMENT, name=S\nE, S1\n"
            "*Coupling, constraint name=C, ref node=9, surface=S\n*Kinematic\n1, 6\n")
    body, _, rep = convert_str(deck)
    lines = body.splitlines()
    ki = next(i for i, l in enumerate(lines) if l.upper().startswith("*KINEMATIC"))
    assert lines[ki + 1].replace(" ", "") == "1,3"
    assert "clamped" in rep.text().lower()


def test_surface_interaction_hard_behavior_synthesized():
    # An interaction without *SURFACE BEHAVIOR is the Abaqus hard-contact default, but a
    # ccx *CONTACT PAIR then stops; the HARD behavior card must be synthesized.  One with
    # an explicit behavior must NOT get a second card.
    deck = ("*Node\n1,0.,0.,0.\n2,1.,0.,0.\n3,1.,1.,0.\n4,0.,1.,0.\n"
            "*Element, type=CPS4, elset=E\n1,1,2,3,4\n"
            "*Surface Interaction, name=BARE\n"
            "*Surface Interaction, name=FULL\n*Surface Behavior, pressure-overclosure=LINEAR\n1e5\n")
    body, _, _ = convert_str(deck)
    txt = body.upper()
    i_bare = txt.index("NAME=BARE"); i_full = txt.index("NAME=FULL")
    assert "PRESSURE-OVERCLOSURE=HARD" in txt[i_bare:i_full]
    assert "HARD" not in txt[i_full:]                       # FULL keeps only its LINEAR card


def test_lamina_to_engineering_constants():
    deck = "*Material, name=cfrp\n*Elastic, type=LAMINA\n140000., 10000., 0.3, 5000., 5000., 3800.\n"
    body, _, rep = convert_str(deck)
    lines = body.splitlines()
    el = next(i for i, l in enumerate(lines) if l.upper().startswith("*ELASTIC"))
    assert "ENGINEERING CONSTANTS" in lines[el].upper() and "LAMINA" not in lines[el].upper()
    row1 = [float(x) for x in lines[el + 1].split(",")]
    assert row1[:5] == [140000., 10000., 10000., 0.3, 0.3]   # E3=E2, nu13=nu12
    nu23 = 10000. / (2 * 3800.) - 1                            # from G23
    assert abs(row1[5] - nu23) < 1e-6
    assert [float(x) for x in lines[el + 2].split(",")] == [3800.]
    assert "transverse" in rep.text().lower()


def test_beam_section_unsupported_profile_commented():
    deck = ("*Node\n1,0,0,0\n2,1,0,0\n*Element,type=B31,elset=E\n1,1,2\n"
            "*Beam Section, elset=E, material=m, section=I\n0.1,0.2,0.1,0.1,0.01,0.01,0.01\n")
    body, _, _ = convert_str(deck)
    live = [l for l in body.splitlines() if not l.lstrip().startswith("**")]
    assert not any(l.upper().startswith("*BEAM SECTION") for l in live)
    assert "SECTION=I" in body.upper()                        # visible in the comment


def test_equally_spaced_amplitude_expanded():
    deck = "*Amplitude, name=EQ, definition=EQUALLY SPACED, fixed interval=0.5\n0., 1., 0.5, 1.\n"
    body, _, _ = convert_str(deck)
    lines = body.splitlines()
    i = next(k for k, l in enumerate(lines) if l.upper().startswith("*AMPLITUDE"))
    pts = [tuple(float(x) for x in l.split(",")) for l in lines[i + 1:i + 5]]
    assert pts == [(0.0, 0.0), (0.5, 1.0), (1.0, 0.5), (1.5, 1.0)]


def test_assembly_elset_element_member_uses_elem_offset():
    # An assembly *Elset member I2.1 is an ELEMENT ref and must take the element offset
    # (not the node offset) — I2's element 1 is global element 2.
    deck = ("*Part, name=P\n*Node\n1,0.,0.,0.\n2,1.,0.,0.\n3,1.,1.,0.\n4,0.,1.,0.\n"
            "*Element, type=CPS4, elset=e\n1,1,2,3,4\n*Solid Section, elset=e, material=m\n*End Part\n"
            "*Assembly, name=A\n*Instance, name=I1, part=P\n*End Instance\n"
            "*Instance, name=I2, part=P\n5.,0.,0.\n*End Instance\n"
            "*Elset, elset=LOADEL\nI2.1\n*End Assembly\n*Material, name=m\n*Elastic\n1.,.3\n")
    _, conv, _ = convert_str(deck)
    assert conv.geom.elset("LOADEL") == [2]


def test_part_cohesive_section_remapped_per_instance():
    # A part-level *Cohesive Section must have its elset remapped per instance (I1_COH),
    # or the substituted continuum elements end up section-less.
    deck = ("*Part, name=P\n*Node\n1,0.,0.,0.\n2,1.,0.,0.\n3,1.,1.,0.\n4,0.,1.,0.\n"
            "5,0.,0.,1.\n6,1.,0.,1.\n7,1.,1.,1.\n8,0.,1.,1.\n"
            "*Element, type=COH3D8, elset=coh\n1,1,2,3,4,5,6,7,8\n"
            "*Cohesive Section, elset=coh, material=glue, response=TRACTION SEPARATION\n*End Part\n"
            "*Assembly, name=A\n*Instance, name=I1, part=P\n*End Instance\n*End Assembly\n"
            "*Material, name=glue\n*Elastic\n1000.,.3\n")
    body, _, _ = convert_str(deck)
    sol = [l for l in body.splitlines() if l.upper().startswith("*SOLID SECTION")]
    assert any("ELSET=I1_COH" in l.upper() for l in sol), sol


def test_combined_suffix_element_resolves():
    assert A.ccx_element_type("C3D8PT", A.Report()) == "C3D8"
    assert A.ccx_element_type("C3D20RHT", A.Report()) == "C3D20R"


def test_initial_stress_expanded_to_integration_points():
    # Abaqus writes *Initial Conditions, TYPE=STRESS as "elset, values" (no int-pt column),
    # which is a hard ccx error; it must expand to one line per element and integration
    # point (C3D8 = 8, empirically probed).  Non-expanding TYPEs pass through.
    deck = ("*Node\n1,0.,0.,0.\n2,1.,0.,0.\n3,1.,1.,0.\n4,0.,1.,0.\n"
            "5,0.,0.,1.\n6,1.,0.,1.\n7,1.,1.,1.\n8,0.,1.,1.\n"
            "*Element, type=C3D8, elset=body\n1,1,2,3,4,5,6,7,8\n"
            "*Solid Section, elset=body, material=m\n*Material, name=m\n*Elastic\n1.,.3\n"
            "*Initial Conditions, type=STRESS\nbody, 10., 10., 10., 0., 0., 0.\n"
            "*Initial Conditions, type=VELOCITY\n1, 1, 0.5\n")
    body, _, rep = convert_str(deck)
    lines = body.splitlines()
    i = next(k for k, l in enumerate(lines) if "TYPE=STRESS" in l.upper())
    ip_lines = [l for l in lines[i + 1:i + 10] if l.startswith("1, ")]
    assert len(ip_lines) == 8 and ip_lines[0].startswith("1, 1, 10.") and ip_lines[7].startswith("1, 8, 10.")
    j = next(k for k, l in enumerate(lines) if "TYPE=VELOCITY" in l.upper())
    assert lines[j + 1].replace(" ", "") == "1,1,0.5"          # untouched
    assert "per-integration" in rep.text().lower()


def test_initial_stress_geostatic_commented():
    deck = ("*Node\n1,0.,0.,0.\n2,1.,0.,0.\n3,1.,1.,0.\n4,0.,1.,0.\n"
            "*Element, type=CPS4, elset=e\n1,1,2,3,4\n"
            "*Initial Conditions, type=STRESS, GEOSTATIC\ne, -100., 10., 0., 0., 0.5\n")
    body, _, _ = convert_str(deck)
    live = [l for l in body.splitlines() if not l.lstrip().startswith("**")]
    assert not any("INITIAL CONDITIONS" in l.upper() for l in live)
    assert "GEOSTATIC" in body.upper()                          # visible in the comment


def test_approximate_riks_and_default_off():
    # ccx has no Riks solver and would silently run a passed-through *STATIC, RIKS as a
    # load-controlled static step, so by default the procedure is commented out (ccx then
    # stops at that step); --approximate reframes it as plain *STATIC.
    deck = ("*Node\n1,0,0,0\n2,1,0,0\n*Element,type=T3D2,elset=E\n1,1,2\n"
            "*Step\n*Static, RIKS\n0.01,1.,1e-5,0.1\n*End Step\n")
    body, _, rep = convert_str(deck)
    live = [l for l in body.splitlines() if not l.startswith("**")]
    assert not any(l.upper().startswith("*STATIC") for l in live)
    assert "** *STATIC, RIKS" in body and "--approximate" in rep.text()
    body, _, rep = convert_str(deck, approximate=True)
    lines = [l for l in body.splitlines() if l.upper().startswith("*STATIC")]
    assert lines == ["*STATIC"] and "[APPROX]" in rep.text()


def test_explicit_dynamics_native():
    # ccx runs *DYNAMIC, EXPLICIT itself: keep it (also under --approximate), drop the
    # Abaqus/Explicit-only controls, and give the step Abaqus/Explicit's defaults (no
    # increment cap, NLGEOM on) instead of ccx's 100-increment, linear-geometry ones.
    deck = ("*Node\n1,0,0,0\n2,1,0,0\n*Element,type=T3D2,elset=E\n1,1,2\n"
            "*Step\n*Dynamic, Explicit, element by element\n, 0.01\n*End Step\n")
    for approx in (False, True):
        body, _, rep = convert_str(deck, approximate=approx)
        lines = body.splitlines()
        i = next(k for k, l in enumerate(lines) if l.upper().startswith("*DYNAMIC"))
        assert lines[i] == "*DYNAMIC, EXPLICIT" and lines[i + 1].replace(" ", "") == ",0.01"
        step = next(l for l in lines if l.upper().startswith("*STEP"))
        assert "INC=10000000" in step and "NLGEOM" in step
        assert "no explicit solver" not in rep.text()


def test_approximate_nu_clamp():
    deck = "*Material,name=m\n*Elastic\n1000., 0.5\n"
    body, _, _ = convert_str(deck)
    assert "1000., 0.5" in body                                # untouched by default
    body, _, rep = convert_str(deck, approximate=True)
    assert "1000., 0.475" in body and "[APPROX]" in rep.text()


def test_approximate_ibeam_to_rect():
    deck = ("*Node\n1,0,0,0\n2,1,0,0\n*Element,type=B31,elset=E\n1,1,2\n"
            "*Beam Section, elset=E, material=m, section=I\n"
            "0.1, 0.2, 0.1, 0.1, 0.01, 0.01, 0.008\n0.,0.,1.\n")
    body, _, rep = convert_str(deck, approximate=True)
    lines = body.splitlines()
    i = next(k for k, l in enumerate(lines) if "BEAM SECTION" in l.upper())
    assert "SECTION=RECT" in lines[i].upper()
    b_r, h_r = (float(x) for x in lines[i + 1].split(","))
    assert abs(b_r * h_r - 0.00344) < 1e-6                     # area preserved
    assert lines[i + 2].replace(" ", "") == "0.,0.,1."         # direction line kept
    assert "[APPROX]" in rep.text()


def test_nonpositive_node_number_warns():
    # Abaqus requires positive node numbers; a deck numbered from 0 (issue #3) is invalid
    # input and ccx behaves unpredictably on it, so the converter must flag it.
    deck = "*Node\n0,0.,0.\n1,1.,0.\n2,1.,1.\n3,0.,1.\n*Element, type=CPS4, elset=E\n1, 0,1,2,3\n"
    _, _, rep = convert_str(deck)
    assert "non-positive numbering" in rep.text().lower() and "e.g. 0" in rep.text()
    _, _, rep = convert_str(deck.replace("0,0.,0.", "4,0.,0.").replace("1, 0,1", "1, 4,1"))
    assert "non-positive" not in rep.text().lower()


Q4 = ("*Node\n1,0,0\n2,1,0\n3,1,1\n4,0,1\n*Element,type=CPS4,elset=E\n1,1,2,3,4\n"
      "*Nset,nset=L\n1,4\n*Solid Section,elset=E,material=M\n1.,\n*Material,name=M\n"
      "*Elastic\n1000.,0.3\n")
S4 = ("*Node\n1,0,0,0\n2,1,0,0\n3,1,1,0\n4,0,1,0\n5,2,0,0\n6,2,1,0\n100,2.5,0.5,0\n"
      "*Element,type=S4,elset=E\n1,1,2,3,4\n2,2,5,6,3\n*Nset,nset=R\n5,6\n*Nset,nset=REF\n100\n"
      "*Shell Section,elset=E,material=M\n0.1\n*Material,name=M\n*Elastic\n1000.,0.3\n")


def _live(body):
    return [l for l in body.splitlines() if not l.startswith("**")]


def test_history_card_outside_step_commented():
    # Step data before any *STEP is invalid Abaqus; ccx 2.23 segfaults on it when the deck
    # has no step at all, so it is commented out with the reason.
    body, _, rep = convert_str(Q4 + "*Boundary\nL,1,2\n*Cload\n3,2,-1.\n")
    assert not any(l.upper().startswith("*CLOAD") for l in _live(body))
    assert "** *CLOAD" in body and "history" in rep.text()
    assert any(l.upper().startswith("*BOUNDARY") for l in _live(body))   # model data stays


def test_undefined_material_warns():
    _, _, rep = convert_str(Q4.replace("material=M", "material=steel"))
    assert "'STEEL', which is never defined" in rep.text() and "defined: M" in rep.text()
    _, _, rep = convert_str(Q4)
    assert "never defined" not in rep.text()


def test_plane_node_rotational_bc_dropped():
    # plane-element nodes have no rotations; ccx 2.23 crashes on a BC there (Abaqus ignores it)
    body, _, rep = convert_str(Q4 + "*Boundary\nL,1,2\nL,6,6\n*Step\n*Static\n*Boundary\nL,1,6\n*End Step\n")
    bc = [l.replace(" ", "") for l in _live(body) if l.startswith("L,")]
    assert bc == ["L,1,2", "L,1,3"] and "Rotational DOFs (4-6)" in rep.text()
    body, _, rep = convert_str(S4 + "*Boundary\nR,1,6\n")          # shells keep rotations
    assert "R, 1, 6" in body and "Rotational DOFs" not in rep.text()
    # named BC in a model that also has beams (so XSYMM expands to rotations too): the
    # rotational part is dropped on the plane-element nodes only
    mixed = Q4 + "*Node\n10,2,0\n11,3,0\n*Element,type=B21,elset=B\n2,10,11\n"
    body, _, _ = convert_str(mixed + "*Boundary\nL, XSYMM\n")
    assert [l for l in _live(body) if l.startswith("L,")] == ["L, 1, 1"]


def test_rigid_coupling_on_shell_nodes_warns():
    deck = (S4 + "*Surface, type=node, name=RS\nR\n*Coupling, constraint name=C, ref node=100, "
            "surface=RS\n*Kinematic\n1, 3\n")
    _, _, rep = convert_str(deck)
    assert "gen3dmpc" in rep.text()
    _, _, rep = convert_str(HEX + "*Nset,nset=TOP\n5,6,7,8\n*Node\n100,0.5,0.5,2.\n"
                            "*Rigid Body, nset=TOP, ref node=100\n")
    assert "gen3dmpc" not in rep.text()


def test_plastic_hardening_forms():
    mat = "*Material,name=M\n*Elastic\n1000.,0.3\n"
    # ccx's native Johnson-Cook only switches on with a *RATE DEPENDENT card (alone it
    # silently runs elastic): a rate-independent one (C = 0) is added, an existing one kept
    body, _, rep = convert_str(mat + "*Plastic, hardening=Johnson Cook\n300., 500., 0.3, 1., 1500., 20.\n")
    assert ("*PLASTIC, HARDENING=JOHNSON COOK\n300., 500., 0.3, 1., 1500., 20.\n"
            "*RATE DEPENDENT, TYPE=JOHNSON COOK\n0., 1.") in body
    body, _, _ = convert_str(mat + "*Plastic, hardening=Johnson Cook\n300., 500., 0.3, 1.\n"
                             "*Rate Dependent, type=Johnson Cook\n0.01, 1.\n")
    assert body.count("*RATE DEPENDENT") == 1 and "0.01, 1." in body
    body, _, rep = convert_str(mat + "*Plastic, hardening=user, properties=2\n1., 2.\n")
    assert not any(l.startswith("*PLASTIC") for l in _live(body)) and "UHARD" in rep.text()
    body, _, _ = convert_str(mat + "*Plastic, hardening=combined, datatype=parameters\n300., 10., 5.\n")
    assert not any(l.startswith("*PLASTIC") for l in _live(body))
    body, _, _ = convert_str(mat + "*Plastic\n300., 0.\n400., 0.1\n")
    assert "*PLASTIC\n300., 0.\n400., 0.1" in body                      # tabular untouched


def test_field_dependencies_collapsed():
    # ccx ignores DEPENDENCIES and in effect uses the first row; collapse to field = 0
    body, _, rep = convert_str("*Material,name=M\n*Elastic,dependencies=1\n"
                               "21000.,0.3,0.,-1.\n210000.,0.3,0.,1.\n")
    assert "*ELASTIC\n115500, 0.3, 0." in body and "DEPENDENCIES=1" in rep.text()
    body, _, _ = convert_str("*Material,name=M\n*Plastic, dependencies=1\n100.,0.,,0.\n"
                             "200.,0.1,,0.\n150.,0.,,1.\n250.,0.1,,1.\n")
    assert "*PLASTIC\n100., 0.\n200., 0.1" in body and "150." not in body
    body, _, _ = convert_str("*Material,name=M\n*Density, dependencies=1\n1., , 0.5\n2., , 1.\n")
    assert "*DENSITY\n1.\n" in body + "\n"


def test_depvar_delete_and_labels():
    body, _, rep = convert_str('*Material,name=M\n*Depvar, delete=3\n3,\n1, PEEQ, "eq"\n')
    assert "*DEPVAR\n3," in body and "PEEQ" not in body and "element deletion" in rep.text()


def test_print_cards_without_set_get_whole_model_sets():
    body, _, _ = convert_str(HEX + "*Step\n*Static\n*El Print\nS\n*Node Print\nU\n*End Step\n")
    assert "*EL PRINT, ELSET=ABQ2CCX_ALL_ELEMENTS" in body
    assert "*NODE PRINT, NSET=ABQ2CCX_ALL_NODES" in body
    assert "*ELSET, ELSET=ABQ2CCX_ALL_ELEMENTS" in body and "*NSET, NSET=ABQ2CCX_ALL_NODES" in body


def test_step_amplitude_kept_and_quasi_static_ramp():
    body, _, _ = convert_str(HEX + "*Step, amp=step\n*Static\n*End Step\n"
                             "*Step\n*Dynamic, application=quasi-static\n0.01,1.\n*End Step\n")
    steps = [l for l in body.splitlines() if l.upper().startswith("*STEP")]
    assert steps == ["*STEP, AMPLITUDE=STEP", "*STEP, AMPLITUDE=RAMP"]
    assert "*DYNAMIC, ALPHA=-0.3333" in body


def test_friction_keeps_only_mu():
    si = "*Surface Interaction, name=SI\n*Surface Behavior, pressure-overclosure=hard\n"
    body, _, rep = convert_str(si + "*Friction, exponential decay\n0.3, 0.2, 1.0\n")
    assert "*FRICTION\n0.3," in body and "EXPONENTIAL" in rep.text()
    body, _, _ = convert_str(si + "*Friction, slip tolerance=0.005\n 0.2,\n")
    assert "*FRICTION\n0.2," in body and "SLIP TOLERANCE" not in body.split("*FRICTION")[1]
    body, _, rep = convert_str(si + "*Friction, rough\n")
    assert not any(l.startswith("*FRICTION") for l in _live(body)) and "FRICTIONLESS" in rep.text()


def test_contact_pair_tied_becomes_tie():
    body, _, _ = convert_str("*Surface Interaction,name=SI\n*Contact Pair, interaction=SI, tied, "
                             "adjust=0.01\nA, B\n")
    assert "*TIE, NAME=ABQ2CCX_TIED1, POSITION TOLERANCE=0.01\nA, B" in body
    assert "*CONTACT PAIR" not in body


def test_composite_symmetric_and_base_rotation():
    deck = S4.replace("*Shell Section,elset=E,material=M\n0.1\n",
                      "*Orientation, name=ORI-1\n1.,0.,0.,0.,1.,0.\n3, 45.\n"
                      "*Shell Section, elset=E, composite, orientation=ORI-1, symmetric\n"
                      "0.1, 3, M, 0., P1\n0.1, 3, M, 90., P2\n")
    body, _, _ = convert_str(deck)
    plies = [l for l in body.splitlines() if l.startswith("0.1, , M")]
    assert len(plies) == 4 and plies[0] == plies[3] and plies[1] == plies[2]
    i = body.index("*ORIENTATION, NAME=ABQ2CCX_OR1")
    assert body[i:].splitlines()[2] == "3, 135."                          # 45 + 90


def test_shell_edge_faces_map_to_s3_s6():
    body, _, _ = convert_str(S4 + "*Surface, name=SS\n1, E1\n2, E4\n")
    assert "1, S3\n2, S6" in body
    body, _, _ = convert_str(Q4 + "*Surface, name=SS\n1, E2\n")
    assert "1, S2" in body


def test_amplitude_scaling_applied():
    body, _, rep = convert_str("*Amplitude, name=A1, scalex=2., scaley=1000.\n0., 0., 1., 1.\n")
    assert "*AMPLITUDE, NAME=A1\n0, 0, 2, 1000" in body
    _, _, rep = convert_str("*Amplitude, name=A1, value=absolute\n0., 0., 1., 1.\n")
    assert "VALUE=ABSOLUTE" in rep.text()


def test_kinematic_coupling_keeps_every_line():
    body, _, _ = convert_str(HEX + "*Node\n100,0.5,0.5,2.\n*Nset,nset=TOP\n5,6\n"
                             "*Kinematic Coupling, ref node=100\nTOP, 1, 1\n7, 3, 3\n")
    assert body.count("*COUPLING") == 2 and "*KINEMATIC\n1, 1" in body and "*KINEMATIC\n3, 3" in body
    body, _, rep = convert_str(HEX + "*Node\n100,0.5,0.5,2.\n*Nset,nset=TOP\n5,6\n"
                               "*Kinematic Coupling, ref node=100\nTOP\n7\n")
    assert body.count("*COUPLING") == 1 and "*KINEMATIC\n1, 3" in body   # all DOFs, solid nodes
    assert "clamped" not in rep.text()                                    # exact for solids


def test_orientation_origin_and_node_definition():
    body, _, _ = convert_str("*Orientation, name=O1\n11., 10., 0., 10., 11., 0., 10., 10., 0.\n")
    assert "*ORIENTATION, NAME=O1\n1, 0, 0, 0, 1, 0" in body
    body, _, _ = convert_str(S4 + "*Orientation, name=O2, definition=nodes\n2, 4, 1\n")
    assert "*ORIENTATION, NAME=O2\n1, 0, 0, 0, 1, 0" in body


def test_equation_node_sets_pair_in_sorted_order():
    body, _, _ = convert_str(S4 + "*Nset, nset=LEFT\n1, 4, 2\n*Nset, nset=RIGHT\n6, 5, 3\n"
                             "*Equation\n2\nLEFT, 1, 1., RIGHT, 1, -1.\n")
    assert "1, 1, 1., 3, 1, -1.\n2\n2, 1, 1., 5, 1, -1.\n2\n4, 1, 1., 6, 1, -1." in body


def test_perturbation_static_before_general_step_warns():
    _, _, rep = convert_str(HEX + "*Step, perturbation\n*Static\n*End Step\n*Step\n*Static\n*End Step\n")
    assert "loads persist" in rep.text()
    _, _, rep = convert_str(HEX + "*Step, perturbation\n*Static\n*End Step\n")
    assert "loads persist" not in rep.text()


def test_eigen_data_line_layouts():
    body, _, _ = convert_str(HEX + "*Step\n*Frequency, eigensolver=subspace\n4, 20000.\n*End Step\n")
    assert "*FREQUENCY\n4, \n" in body + "\n" or "*FREQUENCY\n4,\n" in body + "\n"
    body, _, _ = convert_str(HEX + "*Step\n*Buckle, eigensolver=lanczos\n5, 0., 100., 7\n*End Step\n")
    assert "*BUCKLE\n5\n" in body + "\n"
    body, _, _ = convert_str(HEX + "*Step\n*Frequency\n, 0., 60.\n*End Step\n")
    assert "*FREQUENCY\n8, 0., 60." in body                       # count capped by the mesh size


def test_dsload_follower_warns_under_nlgeom():
    deck = HEX + "*Surface,name=SF\nEALL, S2\n*Step{}\n*Static\n*Dsload, follower=no\nSF, P, 1.\n*End Step\n"
    _, _, rep = convert_str(deck.format(", nlgeom"))
    assert "FOLLOWER=NO dropped" in rep.text()
    _, _, rep = convert_str(deck.format(""))
    assert "FOLLOWER=NO dropped" not in rep.text()


def test_creep_strain_hardening_warns():
    _, _, rep = convert_str("*Material,name=M\n*Creep\n1e-10, 3., -0.5\n")
    assert "TIME hardening" in rep.text()
    _, _, rep = convert_str("*Material,name=M\n*Creep\n1e-10, 3., 0.\n")
    assert "TIME hardening" not in rep.text()


def test_rigid_body_pin_and_tie_sets_united():
    body, _, _ = convert_str(S4 + "*Rigid Body, ref node=100, pin nset=R, tie nset=REF\n")
    assert "*NSET, NSET=ABQ2CCX_RB1\nR, REF" in body and "NSET=ABQ2CCX_RB1" in body.split("*RIGID BODY")[1]


def test_initial_solution_continuation_lines():
    deck = HEX + ("*Material,name=M2\n*Depvar\n10,\n*Initial Conditions, type=solution\n"
                  "EALL, 1., 2., 3., 4., 5., 6., 7.\n8., 9., 10.\n")
    body, _, _ = convert_str(deck)
    assert "1, 1, 1., 2., 3., 4., 5., 6., 7., 8., 9., 10." in body
    assert "8, 1, 9., 10." not in body                                  # no phantom record


def test_keyword_continuation_with_bare_flag():
    body, _, _ = convert_str(HEX + "*Step, name=S1,\nnlgeom\n*Static\n*End Step\n")
    assert "*STEP, NLGEOM" in body


def test_mesh_generation_curves_bias_and_reflect():
    body, _, _ = convert_str("*Node\n1, 0., 0., 0.\n10, 5., 5., 0.\n30, 5., 0., 0.\n"
                             "*Ngen, line=C\n1, 10, 3, 30\n")
    x4, y4 = (float(v) for v in next(l for l in body.splitlines() if l.startswith("4,")).split(",")[1:3])
    assert abs((x4 - 5) ** 2 + y4 ** 2 - 25.0) < 1e-6                   # on the r=5 arc
    body, _, _ = convert_str("*Node\n1,0,0,0\n101,10,0,0\n*Nset,nset=A\n1\n*Nset,nset=B\n101\n"
                             "*Nfill, bias=0.5\nA, B, 4, 25\n")
    xs = [float(l.split(",")[1]) for l in body.splitlines() if l.split(",")[0] in ("26", "51", "76")]
    assert abs(xs[1] / xs[0] - 3.0) < 1e-6                             # intervals 1:2:4:8
    body, _, _ = convert_str("*Node\n1, 1., 1., 0.\n*Nset, nset=A\n1\n*Ncopy, old set=A, "
                             "change number=10, reflect=line\n0.,0.,0., 1.,0.,0.\n")
    assert "11, 1, -1, 0" in body


def test_input_data_file_inlined():
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "nodes.inp"), "w") as fh:
        fh.write("** comment\n1, 0., 0., 0.\n2, 1., 0., 0.\n")
    with open(os.path.join(d, "main.inp"), "w") as fh:
        fh.write("*Node, input=nodes.inp\n*Element, type=T3D2, elset=E\n1, 1, 2\n")
    body, conv, _ = convert(os.path.join(d, "main.inp"))
    assert set(conv.geom.nodes) == {1, 2} and "INPUT" not in body.upper()


def test_parameter_table_not_swallowed():
    body, _, rep = convert_str("*Parameter Table, type=T1\n1, 2\n*Node\n1,0,0,0\n")
    assert "*PARAMETER TABLE" in rep.text() and "1, 0, 0, 0" in body


def test_element_and_material_defaults():
    body, _, _ = convert_str("*Node\n1,0,0\n2,1,0\n*Element, type=B23, elset=E\n1,1,2\n")
    assert "*ELEMENT, TYPE=B31" in body                                  # B23 -> B33 -> B31
    body, _, _ = convert_str("*Material,name=M\n*Hyperelastic, n=1\n1., 2., 0.01\n")
    assert "*HYPERELASTIC, POLYNOMIAL, N=1" in body


def test_continuum_shell_section_becomes_solid():
    sc = ("*Node\n1,0,0,0\n2,1,0,0\n3,1,1,0\n4,0,1,0\n5,0,0,0.1\n6,1,0,0.1\n7,1,1,0.1\n8,0,1,0.1\n"
          "*Element,type=SC8R,elset=E\n1,1,2,3,4,5,6,7,8\n*Material,name=M\n*Elastic\n1000.,0.3\n")
    body, _, _ = convert_str(sc + "*Shell Section, elset=E, material=M\n0.1, 5\n")
    assert "*SOLID SECTION, ELSET=E, MATERIAL=M" in body and "*SHELL SECTION" not in body


def test_part_level_constraints_replicated_per_instance():
    deck = ("*Part, name=P\n*Node\n1,0.,0.,0.\n2,1.,0.,0.\n3,1.,1.,0.\n"
            "*Element, type=T3D2, elset=E\n1,1,2\n2,2,3\n*Solid Section, elset=E, material=M\n1.,\n"
            "*Equation\n2\n1, 1, 1., 3, 1, -1.\n*End Part\n*Assembly, name=A\n"
            "*Instance, name=I1, part=P\n*End Instance\n*Instance, name=I2, part=P\n10.,0.,0.\n"
            "*End Instance\n*End Assembly\n*Material, name=M\n*Elastic\n1000., 0.3\n")
    body, _, _ = convert_str(deck)
    eqs = [l for l in body.splitlines() if l.endswith(", 1, -1.")]
    assert eqs == ["1, 1, 1., 3, 1, -1.", "4, 1, 1., 6, 1, -1."]


def test_surface_interaction_thickness_line_dropped():
    body, _, _ = convert_str("*Surface Interaction, name=SI\n1.,\n*Surface Behavior, "
                             "pressure-overclosure=hard\n")
    assert "*SURFACE INTERACTION, NAME=SI\n*SURFACE BEHAVIOR" in body


def test_load_case_superposition_warned():
    _, _, rep = convert_str(HEX + "*Step, perturbation\n*Static\n*Load Case, name=LC1\n*Cload\n"
                            "7, 1, 1.\n*End Load Case\n*End Step\n")
    assert "SUPERPOSED" in rep.text()


def test_abaqus_output_filter_commented():
    # Abaqus *FILTER (output filter) is not ccx's sensitivity *FILTER, which is an error
    # outside a *SENSITIVITY step
    body, _, rep = convert_str(HEX + "*Filter, name=F1, operator=Max, limit=1.0, HALT\n")
    assert not any(l.upper().startswith("*FILTER") for l in _live(body)) and "*FILTER" in rep.text()


def test_surface_undefined_set_warns():
    _, _, rep = convert_str(HEX + "*Surface, type=element, name=S1\n_missing_S4, S4\n")
    assert "never defines" in rep.text()
    _, _, rep = convert_str(HEX + "*Surface, type=element, name=S1\nEALL, S4\n")
    assert "never defines" not in rep.text()


def test_rigid_body_reference_rotations_go_to_rot_node():
    # ccx ignores BCs/moments on DOFs 4-6 of a *RIGID BODY REF NODE (verified) and carries
    # the body's rotations on its ROT NODE: one is created and the rotations moved there
    deck = (HEX + "*Node\n100, 0.5, 0.5, 1.5\n*Nset, nset=TOP\n5,6,7,8\n*Nset, nset=RP\n100\n"
            "*Rigid Body, ref node=RP, elset=EALL\n*Boundary\nRP, ENCASTRE\n"
            "*Step\n*Static\n*Cload\nRP, 6, 100.\n*End Step\n")
    body, conv, rep = convert_str(deck)
    rot = max(conv.geom.nodes)
    assert f"*RIGID BODY, REF NODE=100, ELSET=EALL, ROT NODE={rot}" in body
    assert "RP, 1, 3" in body and f"{rot}, 1, 3" in body             # ENCASTRE incl. rotations
    assert f"{rot}, 3, 100." in body and "RP, 6, 100." not in body    # the moment moved
    assert "ROT NODE" in rep.text()


def test_el_print_unknown_labels_dropped():
    # an unknown *EL PRINT label is fatal in ccx ('label not applicable or unknown')
    body, _, _ = convert_str(HEX + "*Step\n*Static\n*El Print, elset=EALL\nS, DG\n"
                             "*El Print, elset=EALL\nDG\n*End Step\n")
    prints = [l for l in body.splitlines() if l.startswith("*EL PRINT")]
    assert len(prints) == 1 and "*EL PRINT, ELSET=EALL\nS\n" in body + "\n"


def test_contact_output_maps_to_ccx_labels():
    body, _, _ = convert_str(HEX + "*Step\n*Static\n*Contact Output\nCDISP, CSTRESS, CFORCE\n"
                             "*End Step\n")
    assert "*CONTACT FILE\nCDIS, CSTR" in body
    # names ccx does not know itself are dropped, not folded onto CSTR: switching contact
    # output on that way made ccx 2.23 abort on a deck that solves without it
    body, _, _ = convert_str(HEX + "*Step\n*Static\n*Contact Output\nCPRESS\n*End Step\n")
    assert "*CONTACT FILE" not in body


def test_cload_orientation_warned():
    _, _, rep = convert_str(HEX + "*Step\n*Static\n*Cload, orientation=O1\n7, 1, 1.\n*End Step\n")
    assert "global axes" in rep.text()


def test_blankless_keywords_recognised():
    # ccx ignores blanks in keyword names: *ENDSTEP / *SOLIDSECTION / *ELPRINT are real cards
    deck = (HEX.replace("*ELEMENT, TYPE=C3D8", "*ELEMENT,TYPE=C3D8") +
            "*SOLIDSECTION, ELSET=EALL, MATERIAL=M\n*MATERIAL, NAME=M\n*ELASTIC\n1000., 0.3\n"
            "*STEP\n*STATIC\n*ELPRINT, ELSET=EALL\nS\n*ENDSTEP\n*STEP\n*STATIC\n*ENDSTEP\n")
    body, _, _ = convert_str(deck)
    assert "*SOLID SECTION, ELSET=EALL, MATERIAL=M" in body and "*EL PRINT, ELSET=EALL" in body
    assert body.count("*STEP") == 2 and body.count("*END STEP") == 2


def test_frequency_storage_for_later_modal_step():
    deck = HEX + "*Step\n*Frequency\n5\n*End Step\n*Step\n*Modal Dynamic\n0.1, 1.\n*End Step\n"
    body, _, _ = convert_str(deck)
    assert "*FREQUENCY, STORAGE=YES" in body
    body, _, _ = convert_str(HEX + "*Step\n*Frequency\n5\n*End Step\n")
    assert "STORAGE" not in body
    # a first-step perturbation frequency feeding steady-state dynamics loses PERTURBATION
    body, _, _ = convert_str(HEX + "*Step, perturbation\n*Frequency\n5\n*End Step\n"
                             "*Step, perturbation\n*Steady State Dynamics\n0., 80., 20, 3.\n*End Step\n")
    assert "*STEP\n*FREQUENCY, STORAGE=YES" in body


def test_initial_temperature_defaults_uncovered_nodes_to_zero():
    body, _, _ = convert_str(HEX + "*Nset, nset=SOME\n1, 2\n*Initial Conditions, type=temperature\nSOME, 20.\n")
    assert "*INITIAL CONDITIONS, TYPE=temperature\nABQ2CCX_ALL_NODES, 0.\nSOME, 20." in body
    body, _, _ = convert_str(HEX + "*Initial Conditions, type=temperature\nEALL_NODES, 20.\n"
                             .replace("EALL_NODES", "1") + "".join(f"{n}, 20.\n" for n in range(2, 9)))
    assert "ABQ2CCX_ALL_NODES" not in body                           # every node covered


def test_plane_section_blank_thickness_defaults_to_one():
    body, _, _ = convert_str("*Node\n1,0,0\n2,1,0\n3,1,1\n4,0,1\n*Element,type=CPS4,elset=E\n1,1,2,3,4\n"
                             "*Solid Section, elset=E, material=M\n,\n*Material,name=M\n*Elastic\n1000.,0.3\n")
    assert "*SOLID SECTION, ELSET=E, MATERIAL=M\n1." in body


def test_cyclic_hardening_needs_combined_plastic():
    mat = "*Material,name=M\n*Elastic\n1000.,0.3\n"
    body, _, _ = convert_str(mat + "*Plastic, hardening=combined, datatype=parameters\n300., 10., 5.\n"
                             "*Cyclic Hardening, parameters\n300., 50., 5.\n")
    assert not any(l.startswith(("*PLASTIC", "*CYCLIC")) for l in _live(body))
    body, _, _ = convert_str(mat + "*Plastic, hardening=combined\n300., 0.\n400., 0.1\n"
                             "*Cyclic Hardening\n300., 0.\n350., 0.1\n")
    assert "*CYCLIC HARDENING" in body


def test_boundary_on_undefined_set_warns():
    _, _, rep = convert_str(HEX + "*Boundary\nMISSING, 1, 3\n")
    assert "never defines" in rep.text()
    _, _, rep = convert_str(HEX + "*Surface, name=SURF\nEALL, S1\n*Boundary\nSURF, 1, 3\n")
    assert "is a *SURFACE" in rep.text()


CIRC_BEAM = """*Node
1, 0., 0., 0.
2, 1., 0., 0.
3, 2., 0., 0.
*Element, type=B31, elset=BEAM
1, 1, 2
2, 2, 3
*Beam Section, elset=BEAM, material=M, section=CIRC
0.05
0., 0., -1.
*Material, name=M
*Elastic
2.1e5, 0.3
"""


def test_circ_linear_beam_becomes_quadratic():
    body, conv, rep = convert_str(CIRC_BEAM)
    # ccx 2.23 rejects linear beams with a circular section: midside nodes 4, 5 at the
    # element midpoints, B32 in ccx's end, middle, end order; ids and the elset are kept
    assert "*ELEMENT, TYPE=B32\n1, 1, 4, 2\n2, 2, 5, 3\n" in body
    assert conv.geom.nodes[4] == (0.5, 0.0, 0.0) and conv.geom.nodes[5] == (1.5, 0.0, 0.0)
    assert "*ELSET, ELSET=BEAM\n1, 2\n" in body and "3-node beams (B31 -> B32: 2)" in rep.text()
    # ccx reads the CIRC dimensions as the two diameters: Abaqus radius 0.05 -> 0.1, 0.1
    assert "SECTION=CIRC\n0.1, 0.1\n0., 0., -1." in body
    body, _, _ = convert_str(CIRC_BEAM.replace("type=B31", "type=B31R"))
    assert "*ELEMENT, TYPE=B32R\n1, 1, 4, 2\n" in body
    body, _, _ = convert_str(CIRC_BEAM.replace("type=B31", "type=B21"))   # ccx runs B21 as B31
    assert "*ELEMENT, TYPE=B32\n1, 1, 4, 2\n" in body
    body, _, rep = convert_str(CIRC_BEAM.replace("section=CIRC\n0.05", "section=RECT\n0.1, 0.1"))
    assert "*ELEMENT, TYPE=B31\n1, 1, 2\n" in body and "3-node beams" not in rep.text()
    _, _, rep = convert_str(CIRC_BEAM.replace("CIRC\n0.05\n", "CIRC\n"))  # no radius line
    assert "no readable radius" in rep.text()


def test_circ_beam_midside_follows_instance_transform():
    deck = ("*Part, name=P\n*Node\n1, 0., 0., 0.\n2, 2., 0., 0.\n*Element, type=B31, elset=B\n1, 1, 2\n"
            "*Beam Section, elset=B, material=M, section=CIRC\n0.1\n0., 0., -1.\n*End Part\n"
            "*Assembly, name=A\n*Instance, name=I, part=P\n10., 0., 0.\n0., 0., 0., 0., 0., 1., 90.\n"
            "*End Instance\n*End Assembly\n*Material, name=M\n*Elastic\n1000., 0.3\n")
    _, conv, _ = convert_str(deck)
    typ, conn = conv.geom.elements[1]
    assert typ == "B32" and conn == [1, 3, 2]
    # ends at R(p + T) = (0, 10, 0) and (0, 12, 0): the midside node is their midpoint
    assert all(abs(p - q) < 1e-9 for p, q in zip(conv.geom.nodes[3], (0.0, 11.0, 0.0)))


def test_circ_beam_midside_node_gets_sets_bcs_and_fields():
    deck = CIRC_BEAM + ("*Nset, nset=ALLN\n1, 2, 3\n*Nset, nset=LOADED\n2, 3\n"
                        "*Normal\n1, 1, 0., 1., 0.\n1, 2, 0., 1., 0.\n"
                        "*Boundary\nALLN, 3, 3\n1, 1, 2\n2, 1, 2\n"
                        "*Initial Conditions, type=temperature\n1, 20.\n2, 40.\n3, 60.\n"
                        "*Initial Conditions, type=velocity\n1, 2, 4.\n2, 2, 8.\n"
                        "*Step\n*Static\n*Cload\nLOADED, 2, -1.\n*Temperature\n1, 100.\n2, 200.\n*End Step\n")
    body, conv, rep = convert_str(deck)
    # a set only BCs use takes the midside nodes (the BC still fixes the whole beam); one a
    # *CLOAD counts keeps its nodes (an extra node would add load)
    assert conv.geom.nset("ALLN") == [1, 2, 3, 4, 5] and conv.geom.nset("LOADED") == [2, 3]
    assert "LOADED hold both end nodes" in rep.text()
    # node-numbered data on both end nodes is interpolated onto the midside node, per DOF
    assert "\n2, 1, 2\n4, 1, 2\n" in body and "\n5, 1, 2" not in body
    assert "\n3, 60.\n4, 30\n5, 50\n" in body and "ABQ2CCX_ALL_NODES" not in body
    assert "\n2, 2, 8.\n4, 2, 6\n" in body and "\n2, 200.\n4, 150\n" in body
    assert "\n1, 2, 0., 1., 0.\n1, 4, 0, 1, 0\n" in body          # *NORMAL averaged
    # a set value the end nodes override is replaced by the interpolation (Abaqus sees
    # 25 halfway between 30 and 20); where it already matches, nothing is added
    body, _, _ = convert_str(CIRC_BEAM + "*Nset, nset=ALLN\n1, 2, 3\n"
                             "*Initial Conditions, type=temperature\nALLN, 20.\n1, 30.\n")
    assert body.split("*INITIAL CONDITIONS")[1] == ", TYPE=temperature\nALLN, 20.\n1, 30.\n4, 25"


def test_beam_circ_cantilever_example():
    body, _, _ = convert(os.path.join(EXAMPLES, "beam_circ_cantilever.inp"))
    g = reparse(body)
    assert [t for t, _ in g.elements.values()] == ["B32"] * 20 and len(g.nodes) == 41
    assert g.elements[1][1] == [1, 22, 2] and g.nodes[22] == (2.5, 0.0, 0.0)
    assert "SECTION=CIRC\n2, 2\n" in body                          # radius 1 -> diameters
    assert not dangling_refs(g), dangling_refs(g)


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL  {fn.__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
