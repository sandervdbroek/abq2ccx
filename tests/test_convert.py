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


def elastic_card(body, material):
    """The emitted *ELASTIC card of ``material``: (keyword line, data lines)."""
    lines = body.splitlines()
    i = lines.index(f"*MATERIAL, NAME={material}")
    j = next(k for k in range(i + 1, len(lines)) if lines[k].startswith("*ELASTIC"))
    k = next((k for k in range(j + 1, len(lines)) if lines[k].startswith("*")), len(lines))
    return lines[j], lines[j + 1:k]


ORTHO_EXPANSION = "*Expansion, type=ORTHO\n1e-3, 2e-3, 4e-3\n"
ANISO_EXPANSION = "*Expansion, type=ANISO\n1e-3, 2e-3, 4e-3, 0., 0., 0.\n"


def test_iso_elastic_with_ortho_expansion_becomes_engineering_constants():
    # ccx 2.23 gets the thermal strains wrong for an isotropic *ELASTIC beside an orthotropic
    # *EXPANSION (linear steps): the same stiffness goes out as engineering constants
    body, _, rep = convert_str("*Material, name=M\n*Elastic\n1000., 0.2\n" + ORTHO_EXPANSION +
                               "*Material, name=PLAIN\n*Elastic\n1000., 0.2\n*Expansion\n1e-3\n"
                               "*Material, name=EC\n*Elastic, type=ENGINEERING CONSTANTS\n"
                               "1., 2., 3., .1, .2, .3, 4., 5.\n6.\n" + ORTHO_EXPANSION)
    assert ("*ELASTIC, TYPE=ENGINEERING CONSTANTS\n1000, 1000, 1000, 0.2, 0.2, 0.2, 416.666666667, "
            "416.666666667\n416.666666667\n*EXPANSION, TYPE=ORTHO") in body
    assert "*MATERIAL, NAME=PLAIN\n*ELASTIC\n1000., 0.2\n" in body      # isotropic expansion
    assert elastic_card(body, "EC")[1] == ["1., 2., 3., .1, .2, .3, 4., 5.", "6."]
    assert "Material M: isotropic *ELASTIC written as TYPE=ENGINEERING CONSTANTS" in rep.text()
    assert "Material PLAIN" not in rep.text() and "Material EC" not in rep.text()


def test_iso_elastic_temperature_rows_for_ortho_expansion():
    # only E varies: the stiffness is linear in E, so the given rows (and columns) suffice
    body, _, _ = convert_str("*Material, name=M\n*Elastic\n1000., 0.2, 20.\n2000., 0.2, 120.\n"
                             + ORTHO_EXPANSION)
    assert elastic_card(body, "M")[1] == [
        "1000, 1000, 1000, 0.2, 0.2, 0.2, 416.666666667, 416.666666667", "416.666666667, 20.",
        "2000, 2000, 2000, 0.2, 0.2, 0.2, 833.333333333, 833.333333333", "833.333333333, 120."]
    # nu varies too: ccx interpolates the converted stiffness, Abaqus E and nu, so rows are
    # added (E, nu linear in T) until the stiffness between them is within 1e-4
    body, _, rep = convert_str("*Material, name=M\n*Elastic\n1000., 0.2, 0.\n3000., 0.3, 200.\n"
                               + ORTHO_EXPANSION)
    data = elastic_card(body, "M")[1]
    rows = [[float(x) for x in data[k].split(",") + data[k + 1].split(",")]
            for k in range(0, len(data), 2)]
    temps = [r[9] for r in rows]
    assert temps[0] == 0. and temps[-1] == 200. and len(temps) > 2 and temps == sorted(temps)
    for r in rows:
        e, nu = 1000. + 10. * r[9], 0.2 + 0.0005 * r[9]
        assert r[0:3] == [r[0]] * 3 and r[3:6] == [r[3]] * 3 and r[6:9] == [r[6]] * 3
        assert abs(r[0] - e) < 1e-6 and abs(r[3] - nu) < 1e-9 and abs(r[6] - e / (2 + 2 * nu)) < 1e-6
    for r0, r1 in zip(rows, rows[1:]):
        t = (r0[9] + r1[9]) / 2
        exact = A.ortho_from_iso(1000. + 10. * t, 0.2 + 0.0005 * t)
        lin = [(a + b) / 2 for a, b in zip(A.ortho_from_iso(r0[0], r0[3]), A.ortho_from_iso(r1[0], r1[3]))]
        assert max(abs(a - b) for a, b in zip(exact, lin)) <= 1e-4 * max(exact)
    assert f"{len(rows) - 2} temperature row(s) added" in rep.text()


def test_elastic_for_aniso_expansion_becomes_aniso():
    # engineering constants do not help with an ANISO expansion (ccx 2.23 also gets an
    # orthotropic *ELASTIC wrong beside it without an *ORIENTATION): all go out as ANISO
    body, _, rep = convert_str("*Material, name=ISO\n*Elastic\n1000., 0.2, 50.\n" + ANISO_EXPANSION +
                               "*Material, name=EC\n*Elastic, type=ENGINEERING CONSTANTS\n"
                               "1000., 2000., 3000., 0.2, 0.25, 0.3, 400., 500.\n600.\n" + ANISO_EXPANSION
                               + "*Material, name=LAM\n*Elastic, type=LAMINA\n"
                                 "1000., 600., 0.25, 300., 300., 250.\n" + ANISO_EXPANSION)
    head, data = elastic_card(body, "ISO")
    assert head == "*ELASTIC, TYPE=ANISO" and [len(ln.split(",")) for ln in data] == [8, 8, 6]
    lam, mu = 1000. * .2 / (1.2 * .6), 1000. / 2.4
    iso = A.aniso_from_ortho([lam + 2 * mu, lam, lam + 2 * mu, lam, lam, lam + 2 * mu, mu, mu, mu])
    assert all(abs(a - b) < 1e-6 for a, b in zip([float(x) for ln in data for x in ln.split(",")],
                                                 iso + [50.]))
    # engineering constants: the normal block inverts back to the compliance, G's in place
    head, data = elastic_card(body, "EC")
    d = [float(x) for ln in data for x in ln.split(",")]
    dn = [[d[0], d[1], d[3]], [d[1], d[2], d[4]], [d[3], d[4], d[5]]]
    sn = [[1 / 1000., -.2 / 1000., -.25 / 1000.], [-.2 / 1000., 1 / 2000., -.3 / 2000.],
          [-.25 / 1000., -.3 / 2000., 1 / 3000.]]
    prod = [[sum(dn[i][k] * sn[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    assert head == "*ELASTIC, TYPE=ANISO" and len(d) == 21
    assert all(abs(prod[i][j] - (i == j)) < 1e-9 for i in range(3) for j in range(3))
    assert (d[9], d[14], d[20]) == (400., 500., 600.) and not any(d[6:9] + d[10:14] + d[15:20])
    assert elastic_card(body, "LAM")[0] == "*ELASTIC, TYPE=ANISO"
    assert "orthotropic *ELASTIC with an anisotropic expansion unless an *ORIENTATION" in rep.text()


def test_elastic_left_alone_beside_expansion():
    # a kept *PLASTIC puts ccx on its nonlinear material path: correct there, and it takes
    # only an isotropic or orthotropic *ELASTIC
    body, _, rep = convert_str("*Material, name=P\n*Elastic\n1000., 0.2\n" + ORTHO_EXPANSION +
                               "*Plastic\n100., 0.\n")
    assert "*ELASTIC\n1000., 0.2\n" in body and "written as" not in rep.text()
    # ... but a *PLASTIC the converter comments out leaves the material elastic
    body, _, _ = convert_str("*Material, name=P\n*Elastic\n1000., 0.2\n" + ORTHO_EXPANSION +
                             "*Plastic, hardening=USER\n100., 0.\n")
    assert elastic_card(body, "P")[0] == "*ELASTIC, TYPE=ENGINEERING CONSTANTS"
    # an expansion belongs to its own material only
    body, _, _ = convert_str("*Material, name=A\n*Elastic\n1000., 0.2\n*Material, name=B\n"
                             "*Elastic\n500., 0.3\n" + ORTHO_EXPANSION)
    assert elastic_card(body, "A") == ("*ELASTIC", ["1000., 0.2"])
    assert elastic_card(body, "B")[0] == "*ELASTIC, TYPE=ENGINEERING CONSTANTS"
    # constants ccx rejects anyway (nu >= 0.5) are not rewritten
    body, _, rep = convert_str("*Material, name=M\n*Elastic\n1000., 0.5\n" + ORTHO_EXPANSION)
    assert elastic_card(body, "M") == ("*ELASTIC", ["1000., 0.5"])
    assert "could not be read" in rep.text()


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


def _equations(body):
    """The two-term *EQUATION data lines of a converted deck, blanks removed."""
    lines = body.splitlines()
    return [lines[i + 2].replace(" ", "") for i, l in enumerate(lines)
            if l == "*EQUATION" and lines[i + 1] == "2"]


def test_rigid_coupling_on_shell_nodes_gets_knot_beams():
    # ccx 2.23 rejects a RIGID MPC (*KINEMATIC / *RIGID BODY) on a shell node that is not a
    # knot ('*ERROR in gen3dmpc'); a force-free dangling B31 per coupled node makes it one,
    # and the rotations an empty *Kinematic couples are tied to the ref node's DOFs 4-6
    deck = (S4 + "*Surface, type=node, name=RS\nR\n*Coupling, constraint name=C, ref node=100, "
            "surface=RS\n*Kinematic\n")
    body, conv, rep = convert_str(deck)
    assert list(conv._knots) == [5, 6] and 100 not in conv._knots     # the free RP needs none
    g = reparse(body)
    assert g.elements[3] == ("B31", [5, 101]) and g.elements[4] == ("B31", [6, 102])
    assert g.elsets["ABQ2CCX_KNOT"] == [3, 4] and not dangling_refs(g), dangling_refs(g)
    assert ("*MATERIAL, NAME=ABQ2CCX_KNOT\n*ELASTIC\n1000., 0.\n*DENSITY\n0.\n*BEAM SECTION, "
            "ELSET=ABQ2CCX_KNOT, MATERIAL=ABQ2CCX_KNOT, SECTION=RECT\n") in body
    assert "*KINEMATIC\n1, 3\n*EQUATION" in body
    assert _equations(body) == [f"{n},{k},1.,100,{k},-1." for n in (5, 6) for k in (4, 5, 6)]
    assert "gen3dmpc" in rep.text() and "knot beam" in rep.text()
    # a DOF list without rotations ties none; a rotation under a *BOUNDARY keeps the BC
    body, _, _ = convert_str(deck + "2, 2\n")
    assert "B31" in body and not _equations(body)
    body, _, rep = convert_str(deck + "*Boundary\n5, 4, 4\n")
    assert "5,4,1.,100,4,-1." not in _equations(body) and "5,5,1.,100,5,-1." in _equations(body)
    assert "the BC governs it" in rep.text()
    # solid members need no knots: no beams, no note
    body, _, rep = convert_str(HEX + "*Nset,nset=TOP\n5,6,7,8\n*Node\n100,0.5,0.5,2.\n"
                               "*Rigid Body, nset=TOP, ref node=100\n")
    assert "gen3dmpc" not in rep.text() and "ABQ2CCX_KNOT" not in body


def test_rigid_body_shell_tie_and_pin_members():
    # TIE NSET (and ELSET) shell nodes follow the body's rotation (its ROT NODE DOFs 1-3);
    # PIN NSET nodes keep theirs free — the Abaqus distinction, which ccx's NSET lacks
    body, conv, rep = convert_str(S4 + "*Rigid Body, ref node=REF, tie nset=R\n")
    rot = conv._rb_rot[100]
    assert f"ROT NODE={rot}" in body and list(conv._knots) == [5, 6]
    assert _equations(body) == [f"{n},{k},1.,{rot},{k - 3},-1." for n in (5, 6) for k in (4, 5, 6)]
    body, conv, rep = convert_str(S4 + "*Rigid Body, ref node=REF, pin nset=R\n")
    assert list(conv._knots) == [5, 6] and not _equations(body)
    assert "those of PIN nodes stay free" in rep.text()


def test_coupling_with_shell_reference_node_becomes_rigid_body():
    # a shell/beam REF NODE would carry the ccx coupling's rotation and its own knot rotation
    # as two unrelated unknowns (probed: a beam acts hinged at the coupled face), so the
    # coupling becomes a *RIGID BODY whose ROT NODE follows the node's own rotations; BCs and
    # moments on the node's DOFs 4-6 therefore stay on the node
    deck = (S4 + "*Nset, nset=EDGE\n2, 3, 5, 6\n*Surface, type=node, name=SE\nEDGE\n"
            "*Coupling, constraint name=C, ref node=2, surface=SE\n*Kinematic\n"
            "*Step\n*Static\n*Cload\n2, 5, 7.\n*End Step\n")
    body, conv, rep = convert_str(deck)
    live = "\n".join(_live(body))
    assert "*COUPLING" not in live and "*KINEMATIC" not in live
    assert "*NSET, NSET=ABQ2CCX_RB1\n3, 5, 6\n*RIGID BODY, NSET=ABQ2CCX_RB1, REF NODE=2, ROT NODE=101" in body
    assert list(conv._knots) == [2, 3, 5, 6]
    eqs = _equations(body)
    assert eqs[:3] == [f"101,{k},1.,2,{k + 3},-1." for k in (1, 2, 3)]
    assert eqs[3:] == [f"{n},{k},1.,101,{k - 3},-1." for n in (3, 5, 6) for k in (4, 5, 6)]
    assert "2, 5, 7." in body                                     # the moment stays on node 2
    # only some translations coupled: not repairable, warned (no knots)
    body, conv, rep = convert_str(deck.replace("*Kinematic\n", "*Kinematic\n2, 2\n"))
    assert not conv._knots and "full-translation couplings" in rep.text()


def test_rigid_coupling_knots_on_edges_trusses_and_thermal_decks():
    # an element-edge surface knots only the edge's nodes (S4 element 2 = 2,5,6,3: E2 = 5,6)
    deck = (S4 + "*Elset, elset=E2S\n2\n*Surface, type=element, name=SE\nE2S, E2\n"
            "*Coupling, constraint name=C, ref node=100, surface=SE\n*Kinematic\n")
    _, conv, _ = convert_str(deck)
    assert list(conv._knots) == [5, 6]
    # truss nodes get knots (ccx rejects RIGID MPCs on them too) but no rotation ties
    truss = ("*Node\n1,0,0,0\n2,1,0,0\n3,2,0,0\n*Element, type=T3D2, elset=T\n1, 1, 2\n"
             "*Nset, nset=M\n2\n*Rigid Body, ref node=3, tie nset=M\n")
    body, conv, _ = convert_str(truss)
    assert list(conv._knots) == [2] and not _equations(body)
    # a thermal step needs a conductivity on the knot material; a heat-transfer-only deck
    # gets no rotation ties (its knots have no rotations: '*ERROR in gen3dmpc')
    td = deck.replace("*Elastic\n1000.,0.3\n", "*Elastic\n1000.,0.3\n*Conductivity\n45.\n")
    body, _, _ = convert_str(td + "*Step\n*Coupled Temperature-Displacement, steady state\n1., 1.\n"
                             "*End Step\n")
    assert "*DENSITY\n0.\n*CONDUCTIVITY\n45.\n*SPECIFIC HEAT\n0.\n" in body and _equations(body)
    body, _, _ = convert_str(td + "*Step\n*Heat Transfer, steady state\n1., 1.\n*End Step\n")
    assert "*CONDUCTIVITY\n45." in body and not _equations(body)
    # explicit dynamics cannot run it at all (ccx: linear and nonlinear MPCs depend on each other)
    _, _, rep = convert_str(deck + "*Step\n*Dynamic, Explicit\n, 1e-4\n*End Step\n")
    assert "explicit dynamic step" in rep.text()


def test_kinematic_rotation_lines():
    # a *Kinematic with only rotational lines couples nothing in ccx — it must not get the
    # '1, 3' synthesized for an EMPTY card (that would couple translations Abaqus leaves free)
    deck = (HEX + "*Node\n100,0.5,0.5,2.\n*Nset,nset=TOP\n5,6,7,8\n*Surface, type=node, name=ST\n"
            "TOP\n*Coupling, constraint name=C, ref node=100, surface=ST\n*Kinematic\n4, 6\n")
    body, _, rep = convert_str(deck)
    lines = body.splitlines()
    ki = lines.index("*KINEMATIC")
    assert ki == len(lines) - 1 or lines[ki + 1].startswith("*")
    assert "rotations are NOT coupled" in rep.text() and "synthesized" not in rep.text()
    # a *KINEMATIC COUPLING rotation line on shell nodes is tied once a translation line
    # couples the same reference node
    body, _, rep = convert_str(S4 + "*Kinematic Coupling, ref node=100\nR, 1, 3\nR, 4, 6\n")
    assert body.count("*COUPLING") == 1
    assert _equations(body) == [f"{n},{k},1.,100,{k},-1." for n in (5, 6) for k in (4, 5, 6)]
    assert "NOT coupled" not in rep.text()


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


PIPE_BEAM = CIRC_BEAM.replace("section=CIRC\n0.05", "section=PIPE\n0.05, 0.01")
B32_PIPE_BEAM = """*Node
1, 0., 0., 0.
2, 0.5, 0., 0.
3, 1., 0., 0.
*Element, type=B32, elset=BEAM
1, 1, 2, 3
*Beam Section, elset=BEAM, material=M, section=PIPE
0.05, 0.01
0., 0., -1.
*Material, name=M
*Elastic
2.1e5, 0.3
"""
BOX_DATA = "section=BOX\n0.1, 0.06, 0.01, 0.005, 0.01, 0.005"


def test_pipe_box_beams_become_b32r():
    body, conv, rep = convert_str(PIPE_BEAM)
    # ccx 2.23 runs PIPE and BOX sections only on B32R: a 2-node beam gets a midside node
    # (end, middle, end; ids and the elset kept) and the data line passes through
    assert "*ELEMENT, TYPE=B32R\n1, 1, 4, 2\n2, 2, 5, 3\n" in body
    assert conv.geom.nodes[4] == (0.5, 0.0, 0.0) and "*ELSET, ELSET=BEAM\n1, 2\n" in body
    assert "SECTION=PIPE\n0.05, 0.01\n0., 0., -1." in body           # outer radius, wall
    assert "3-node beams (B31 -> B32R: 2)" in rep.text()
    assert "accepts PIPE and BOX sections only on B32R" in rep.text() and "circular" not in rep.text()
    for typ in ("B21", "B31R", "PIPE31"):
        body, _, _ = convert_str(PIPE_BEAM.replace("type=B31", f"type={typ}"))
        assert "*ELEMENT, TYPE=B32R\n1, 1, 4, 2\n" in body, typ
    # THICK PIPE runs as PIPE; BOX's a, b, t1..t4 mean the same in both codes
    body, _, rep = convert_str(PIPE_BEAM.replace("section=PIPE", "section=THICK PIPE"))
    assert "SECTION=PIPE\n0.05, 0.01\n" in body and "*ELEMENT, TYPE=B32R\n1, 1, 4, 2\n" in body
    assert "SECTION=THICK PIPE beams: 2 2-node element(s)" in rep.text()
    body, _, _ = convert_str(CIRC_BEAM.replace("section=CIRC\n0.05", BOX_DATA))
    assert "*ELEMENT, TYPE=B32R\n1, 1, 4, 2\n" in body
    assert "SECTION=BOX\n0.1, 0.06, 0.01, 0.005, 0.01, 0.005\n" in body
    # the midside node joins a node set only a *BOUNDARY uses, as for CIRC beams
    _, conv, _ = convert_str(PIPE_BEAM + "*Nset, nset=ALLN\n1, 2, 3\n*Boundary\nALLN, 3, 3\n")
    assert conv.geom.nset("ALLN") == [1, 2, 3, 4, 5]


def test_pipe_box_b32_only_changes_type():
    body, conv, rep = convert_str(B32_PIPE_BEAM)
    assert "*ELEMENT, TYPE=B32R\n1, 1, 2, 3\n" in body and len(conv.geom.nodes) == 3
    assert "SECTION=PIPE beams: 1 3-node element(s) emitted as B32R instead of B32 " \
           "(B32 -> B32R: 1), with the same nodes" in rep.text()
    assert "midside" not in rep.text()
    body, _, _ = convert_str(B32_PIPE_BEAM.replace("type=B32", "type=PIPE32")
                             .replace("section=PIPE\n0.05, 0.01", BOX_DATA))
    assert "*ELEMENT, TYPE=B32R\n1, 1, 2, 3\n" in body
    _, _, rep = convert_str(B32_PIPE_BEAM.replace("section=PIPE\n0.05, 0.01", "section=CIRC\n0.05"))
    assert "B32R" not in rep.text()                     # ccx runs CIRC on B32 as it is


def test_mixed_section_beams_report_each_case():
    deck = ("*Node\n1, 0., 0., 0.\n2, 1., 0., 0.\n3, 2., 0., 0.\n4, 3., 0., 0.\n5, 3.5, 0., 0.\n"
            "6, 4., 0., 0.\n*Element, type=B31, elset=ROD\n1, 1, 2\n*Element, type=B31, elset=TUBE\n"
            "2, 2, 3\n*Element, type=B32, elset=BOXB\n3, 4, 5, 6\n"
            "*Beam Section, elset=ROD, material=M, section=CIRC\n0.05\n0., 0., -1.\n"
            "*Beam Section, elset=TUBE, material=M, section=PIPE\n0.05, 0.01\n0., 0., -1.\n"
            "*Beam Section, elset=BOXB, material=M, section=BOX\n0.1, 0.1, 0.01, 0.01, 0.01, 0.01\n"
            "*Material, name=M\n*Elastic\n2.1e5, 0.3\n")
    body, _, rep = convert_str(deck)
    assert "*ELEMENT, TYPE=B32\n1, 1, 7, 2\n*ELEMENT, TYPE=B32R\n2, 2, 8, 3\n3, 4, 5, 6\n" in body
    # one line per case, each naming its sections and ccx's reason
    assert "SECTION=CIRC/PIPE beams: 2 2-node element(s) emitted as 3-node beams (B31 -> B32: 1, " \
           "B31 -> B32R: 1), each with a new midside node at its midpoint (nodes 7-8); ccx 2.23 " \
           "stops on linear beams with a circular section and accepts PIPE and BOX sections only " \
           "on B32R." in rep.text()
    assert "SECTION=BOX beams: 1 3-node element(s) emitted as B32R instead of B32" in rep.text()
    # an element under both a PIPE and a later CIRC section stays B32R, which suits both
    body, _, _ = convert_str(PIPE_BEAM + "*Beam Section, elset=BEAM, material=M, section=CIRC\n0.05\n")
    assert "*ELEMENT, TYPE=B32R\n1, 1, 4, 2\n" in body


def test_beam_pipe_box_cantilever_example():
    body, _, _ = convert(os.path.join(EXAMPLES, "beam_pipe_box_cantilever.inp"))
    g = reparse(body)
    # 20 PIPE31 -> B32R with midside nodes 142-161, 20 B32 -> B32R on their own nodes
    assert [t for t, _ in g.elements.values()] == ["B32R"] * 40 and len(g.nodes) == 82
    assert g.elements[1][1] == [1, 142, 2] and g.nodes[142] == (2.5, 0.0, 0.0)
    assert g.elements[101][1] == [101, 102, 103] and g.elements[120][1] == [139, 140, 141]
    assert "SECTION=PIPE\n1., 0.2\n" in body and "SECTION=BOX\n2., 3., 0.1, 0.2, 0.1, 0.2\n" in body
    assert not dangling_refs(g), dangling_refs(g)


def test_beam_circ_cantilever_example():
    body, _, _ = convert(os.path.join(EXAMPLES, "beam_circ_cantilever.inp"))
    g = reparse(body)
    assert [t for t, _ in g.elements.values()] == ["B32"] * 20 and len(g.nodes) == 41
    assert g.elements[1][1] == [1, 22, 2] and g.nodes[22] == (2.5, 0.0, 0.0)
    assert "SECTION=CIRC\n2, 2\n" in body                          # radius 1 -> diameters
    assert not dangling_refs(g), dangling_refs(g)


def test_coupling_plate_examples():
    # the shell/solid pair validate_with_ccx.py compares: the S8R edge gets a knot beam per
    # coupled node and its rotations tied; the C3D20R reference needs neither
    body, conv, _ = convert(os.path.join(EXAMPLES, "coupling_shell_plate.inp"))
    g = reparse(body)
    assert list(conv._knots) == list(range(21, 822, 100)) and len(g.elsets["ABQ2CCX_KNOT"]) == 9
    assert len(_equations(body)) == 27 and not dangling_refs(g), dangling_refs(g)
    body, conv, _ = convert(os.path.join(EXAMPLES, "coupling_solid_plate.inp"))
    g = reparse(body)
    assert not conv._knots and "ABQ2CCX_KNOT" not in body and not _equations(body)
    assert len(g.nodes) == 3 * 189 + 2 and len(g.elements) == 40      # + RP and its ROT NODE
    assert not dangling_refs(g), dangling_refs(g)


PLANAR_BEAM = """*Node
1, 0., 0.
2, 1., 0.
3, 2., 0.
4, 3., 0.
*Element, type=B21, elset=BEAM
1, 1, 2
2, 2, 3
3, 3, 4
*Beam Section, elset=BEAM, material=M, section=RECT
0.1, 0.2
*Material, name=M
*Elastic
2.1e5, 0.3
*Density
7.85e-9
*Step
*Frequency
5
*Boundary
1, ENCASTRE
*End Step
"""


def test_planar_line_types():
    assert [A.planar_line_type(t) for t in ("B21", "b21h", "B22H", "B23", "PIPE21H", "PIPE22",
                                            "T2D2", "T2D2T", "T2D3H")] == \
        ["B21", "B21", "B22", "B23", "PIPE21", "PIPE22", "T2D2", "T2D2", "T2D3"]
    assert {A.planar_line_type(t) for t in ("B31", "B32", "T3D2", "PIPE31", "CPS4", "S4R")} == {None}


def test_planar_beams_fix_out_of_plane_dof():
    # ccx runs B21 as a 3-D B31 (T2D2 as a T3D2): with DOF 3 free each bending mode of a
    # planar beam shows up twice in *FREQUENCY, and a truss node is a mechanism
    body, _, rep = convert_str(PLANAR_BEAM)
    model = body.split("*STEP")[0]                                 # model data
    assert "*NSET, NSET=ABQ2CCX_PLANAR, GENERATE\n1, 4, 1\n" in model
    assert "*BOUNDARY\nABQ2CCX_PLANAR, 3, 3\n*BEAM SECTION" in model
    assert ", 4, 5\n" not in body                       # ENCASTRE (DOFs 1-6) holds the twist
    assert "DOF 3 is fixed on their 4 node(s)" in rep.text()
    assert "eigenmodes include twist modes" in rep.text()
    # the other 2-D beams and trusses (B23 -> B33 -> B31, PIPE21 -> B21, ...) alike
    for typ in ("B21H", "B23", "PIPE21"):
        body, _, _ = convert_str(PLANAR_BEAM.replace("type=B21", f"type={typ}"))
        assert "*BOUNDARY\nABQ2CCX_PLANAR, 3, 3\n" in body, typ
    body, conv, _ = convert_str(PLANAR_BEAM.replace("1, 1, 2\n2, 2, 3\n3, 3, 4\n", "1, 1, 2, 3\n")
                                .replace("type=B21", "type=B22"))
    assert "*ELEMENT, TYPE=B32\n1, 1, 2, 3\n" in body and conv.geom.nset("ABQ2CCX_PLANAR") == [1, 2, 3]
    truss = PLANAR_BEAM.replace("type=B21", "type=T2D2").replace(
        "*Beam Section, elset=BEAM, material=M, section=RECT\n0.1, 0.2",
        "*Solid Section, elset=BEAM, material=M\n0.01").replace("1, ENCASTRE", "1, 1, 2\n4, 2, 2")
    body, _, rep = convert_str(truss)
    assert "*BOUNDARY\nABQ2CCX_PLANAR, 3, 3\n*SOLID SECTION" in body and ", 4, 5\n" not in body
    assert "twist" not in rep.text()                    # a truss carries no twist
    # 3-D beams are left as they are
    body, _, rep = convert_str(CIRC_BEAM)
    assert "ABQ2CCX_PLANAR" not in body and "lanar" not in rep.text()


def test_planar_constraint_reaches_upgraded_midside_nodes():
    # a B21 under a circular section becomes a B32 with midside nodes 5-7 (ccx 2.23 rejects
    # linear CIRC beams); they would move out of plane just the same
    body, conv, _ = convert_str(PLANAR_BEAM.replace("section=RECT\n0.1, 0.2", "section=CIRC\n0.05"))
    assert "*ELEMENT, TYPE=B32\n1, 1, 5, 2\n" in body
    assert conv.geom.nset("ABQ2CCX_PLANAR") == [1, 2, 3, 4, 5, 6, 7]
    assert "*NSET, NSET=ABQ2CCX_PLANAR, GENERATE\n1, 7, 1\n" in body


def test_planar_straight_beam_twist_held_at_one_node():
    # pinned supports leave the twist of a straight beam free in ccx (a 0 Hz mode, *BUCKLE
    # factors ~1): DOFs 4-5 are fixed at one support...
    pinned = PLANAR_BEAM.replace("1, ENCASTRE", "1, 1, 2\n4, 2, 2")
    body, _, rep = convert_str(pinned)
    assert "*BOUNDARY\nABQ2CCX_PLANAR, 3, 3\n1, 4, 5\n*BEAM SECTION" in body
    assert "DOFs 4-5 are fixed at node(s) 1" in rep.text()
    # ... preferably where the in-plane rotation is already fixed (CAE's U1, U2, UR3 clamp)
    clamped = PLANAR_BEAM.replace("1, ENCASTRE", "1, 1, 2\n4, 1, 2\n4, 6, 6")
    body, _, _ = convert_str(clamped)
    assert "ABQ2CCX_PLANAR, 3, 3\n4, 4, 5\n" in body
    # ... and never at a node with a *TRANSFORM (ccx allows no rotational BC there)
    body, _, _ = convert_str(pinned.replace("*Step", "*Nset, nset=TURN\n1\n*Transform, nset=TURN\n"
                                            "1., 1., 0., -1., 1., 0.\n*Step", 1))
    assert "ABQ2CCX_PLANAR, 3, 3\n4, 4, 5\n" in body
    # on a circular section a DOF 4/5 BC at an element end node locks the bending rotation
    # as well (ccx 2.23): at a node whose in-plane rotation is fixed anyway, else at the
    # middle node of an element next to a support (B21 -> B32 1, 5, 2), where it holds
    # only the twist — no knot beam needed
    circ = "section=CIRC\n0.05"
    body, conv, _ = convert_str(clamped.replace("section=RECT\n0.1, 0.2", circ))
    assert "ABQ2CCX_PLANAR, 3, 3\n4, 4, 5\n" in body and not conv._knots
    body, conv, rep = convert_str(pinned.replace("section=RECT\n0.1, 0.2", circ))
    assert "*BOUNDARY\nABQ2CCX_PLANAR, 3, 3\n5, 4, 5\n*BEAM SECTION" in body and not conv._knots
    assert "DOFs 4-5 are fixed at node(s) 5" in rep.text() and "is unrestrained" not in rep.text()
    body, _, _ = convert_str(pinned.replace("section=RECT\n0.1, 0.2", circ).replace(
        "1, 1, 2\n4, 2, 2", "3, 2, 2\n4, 1, 2"))          # supports at nodes 3, 4: element 2, 6, 3
    assert "ABQ2CCX_PLANAR, 3, 3\n6, 4, 5\n" in body
    # a frame that is not straight has no rigid twist once DOF 3 is fixed
    frame = PLANAR_BEAM.replace("3, 2., 0.\n4, 3., 0.", "3, 2., 1.\n4, 2., 2.").replace(
        "1, ENCASTRE", "1, 1, 2\n4, 1, 2")
    body, _, rep = convert_str(frame)
    assert "ABQ2CCX_PLANAR, 3, 3\n*BEAM SECTION" in body and "DOFs 4-5" not in rep.text()


def test_planar_constraint_skips_constrained_and_skewed_nodes():
    # a DOF-3 BC on the dependent term of an *EQUATION stops ccx ('dependent side of a MPC
    # and a SPC'); a *TRANSFORM that tilts the local 3-axis out of z makes DOF 3 another
    # direction; one rotating about z keeps it
    deck = PLANAR_BEAM.replace("*Step", "*Equation\n2\n4, 3, 1., 3, 3, -1.\n"
                               "*Nset, nset=TILT\n2\n*Transform, nset=TILT\n1., 0., 0., 0., 1., 1.\n"
                               "*Nset, nset=TURN\n3\n*Transform, nset=TURN\n1., 1., 0., -1., 1., 0.\n"
                               "*Step", 1)
    _, conv, rep = convert_str(deck)
    assert conv.geom.nset("ABQ2CCX_PLANAR") == [1, 3]
    assert "2 node(s) whose DOF 3 an *EQUATION" in rep.text()
    # *MPC nodes and rigid-body members likewise
    _, conv, _ = convert_str(PLANAR_BEAM.replace("*Step", "*MPC\nTIE, 4, 3\n*Step", 1))
    assert conv.geom.nset("ABQ2CCX_PLANAR") == [1, 2]
    _, conv, _ = convert_str(PLANAR_BEAM.replace("*Step", "*Node\n5, 4., 0.\n*Nset, nset=RB\n3, 4\n"
                                                 "*Rigid Body, ref node=5, tie nset=RB\n*Step", 1))
    assert conv.geom.nset("ABQ2CCX_PLANAR") == [1, 2]


def test_planar_constraint_repeated_after_op_new():
    # *BOUNDARY, OP=NEW removes the model-data constraint as well (verified on ccx 2.23);
    # here it removes node 4's support
    step2 = "*End Step\n*Step\n*Static\n*Boundary, op=NEW\n1, ENCASTRE\n*Cload\n4, 2, -1.\n*End Step\n"
    deck = PLANAR_BEAM.replace("1, ENCASTRE\n", "1, ENCASTRE\n4, 2, 2\n").replace("*End Step\n", step2)
    body, conv, _ = convert_str(deck)
    first, second = body.split("*STEP")[1:]
    assert "ABQ2CCX_PLANAR" not in first
    assert "*BOUNDARY, OP=NEW\n1, 1, 6\n** [abq2ccx] planar constraint re-applied (OP=NEW removed " \
           "it)\n*BOUNDARY\nABQ2CCX_PLANAR, 3, 3\n*CLOAD" in second
    assert list(conv._knots) == [1]           # the clamp OP=NEW re-specifies (see below)
    # an OP=NEW that removes nothing is dropped: the constraint stays as it is
    body, _, _ = convert_str(PLANAR_BEAM.replace("*End Step\n", step2))
    second = body.split("*STEP")[2]
    assert "*BOUNDARY, OP=NEW" not in second and "ABQ2CCX_PLANAR" not in second


def test_planar_constraint_needs_a_planar_model():
    # among 3-D elements, or off a z = const plane, a 2-D beam is left as ccx runs it
    body, _, rep = convert_str(PLANAR_BEAM.replace("*Beam Section", "*Element, type=C3D8, elset=BLK\n"
                                                   "9, 1, 2, 3, 4, 1, 2, 3, 4\n*Beam Section"))
    assert "ABQ2CCX_PLANAR" not in body and "share the model with C3D8" in rep.text()
    body, _, rep = convert_str(PLANAR_BEAM.replace("4, 3., 0.", "4, 3., 0., 0.5"))
    assert "ABQ2CCX_PLANAR" not in body and "not in one plane z = const" in rep.text()


def test_planar_pinned_beam_example():
    body, _, _ = convert(os.path.join(EXAMPLES, "planar_pinned_beam.inp"))
    g = reparse(body)
    assert [t for t, _ in g.elements.values()] == ["B21"] * 20 and len(g.nodes) == 21
    # DOF 3 on all 21 nodes, the twist held at the pinned end, ahead of the steps
    assert g.nset("ABQ2CCX_PLANAR") == list(range(1, 22))
    assert "*BOUNDARY\nABQ2CCX_PLANAR, 3, 3\n1, 4, 5\n" in body.split("*STEP")[0]
    assert not dangling_refs(g), dangling_refs(g)


CIRC_STATIC = "*Step\n*Static\n*Cload\n2, 2, -1.\n*End Step\n"


def test_circ_beam_partial_rotation_bc_gets_knot_beam():
    # a rotational BC on a B32 end node makes ccx 2.23 tie the section's midside nodes to its
    # corners, which a circle cannot follow: the node's other rotations lock as well (a
    # pinned beam with its twist held deflects 0.27 of beam theory).  A knot beam per such
    # node hands the BCs to the knot's rotation node; the BC lines stay as they are.
    body, conv, rep = convert_str(CIRC_BEAM + "*Boundary\n1, 1, 4\n3, 2, 4\n" + CIRC_STATIC)
    g = reparse(body)
    assert list(conv._knots) == [1, 3] and g.elsets["ABQ2CCX_KNOT"] == [3, 4]
    assert g.elements[3] == ("B31", [1, 6]) and g.elements[4] == ("B31", [3, 7])
    assert "*MATERIAL, NAME=ABQ2CCX_KNOT\n*ELASTIC\n210000., 0.\n*DENSITY\n0.\n" in body
    assert "*BOUNDARY\n1, 1, 4\n3, 2, 4\n*STEP" in body and not dangling_refs(g)
    assert "would lock the node's other rotations" in rep.text() and "(1, 3) got a force-free" \
        in rep.text()
    # a symmetry plane (XSYMM = DOFs 1, 5, 6) holds some rotations too; a prescribed rotation
    # is locked even when all three are given
    _, conv, _ = convert_str(CIRC_BEAM + "*Boundary\n1, ENCASTRE\n3, XSYMM\n" + CIRC_STATIC)
    assert list(conv._knots) == [3]
    _, conv, _ = convert_str(CIRC_BEAM + "*Boundary\n1, ENCASTRE\n3, 4, 5\n3, 6, 6, 0.001\n"
                             + CIRC_STATIC)
    assert list(conv._knots) == [3]
    # full zero clamps are exact as they are; other sections need no knot
    body, conv, rep = convert_str(CIRC_BEAM + "*Boundary\n1, ENCASTRE\n3, 1, 6\n" + CIRC_STATIC)
    assert not conv._knots and "ABQ2CCX_KNOT" not in body and "knot" not in rep.text()
    _, conv, _ = convert_str(CIRC_BEAM.replace("section=CIRC\n0.05", "section=RECT\n0.1, 0.1")
                             + "*Boundary\n1, 1, 4\n3, 2, 4\n" + CIRC_STATIC)
    assert not conv._knots
    # at a 3-node element's middle node the tied section nodes are unused: exact already
    b32 = CIRC_BEAM.replace("type=B31", "type=B32").replace("1, 1, 2\n2, 2, 3\n", "1, 1, 2, 3\n")
    _, conv, _ = convert_str(b32 + "*Boundary\n1, 1, 3\n3, 2, 3\n2, 4, 4\n" + CIRC_STATIC)
    assert not conv._knots


def test_circ_beam_rotation_knots_follow_steps_and_skip_unsafe_nodes():
    # the BCs a step solves with count: OP=NEW may leave only some rotations held
    deck = CIRC_BEAM + "*Boundary\n1, ENCASTRE\n" + CIRC_STATIC + \
        "*Step\n*Static\n*Boundary, op=NEW\n1, 1, 4\n3, 2, 4\n*End Step\n"
    _, conv, _ = convert_str(deck)
    assert list(conv._knots) == [1, 3]
    # no knot where ccx allows no rotational BC (*TRANSFORM), nor in a heat-transfer-only deck
    _, conv, _ = convert_str(CIRC_BEAM + "*Nset, nset=TURN\n1\n*Transform, nset=TURN\n"
                             "0., 1., 0., -1., 0., 0.\n*Boundary\n1, 1, 4\n3, 2, 4\n" + CIRC_STATIC)
    assert list(conv._knots) == [3]
    _, conv, _ = convert_str(CIRC_BEAM + "*Boundary\n1, 1, 4\n*Step\n*Heat Transfer\n1., 1.\n"
                             "*End Step\n")
    assert not conv._knots
    # ccx's explicit solver stops on the density-free knot beams: warned instead
    _, conv, rep = convert_str(CIRC_BEAM + "*Density\n7.85e-9\n*Boundary\n1, 1, 4\n3, 2, 4\n"
                               "*Step\n*Dynamic, explicit\n, 0.001\n*Cload\n2, 2, -1.\n*End Step\n")
    assert not conv._knots and "calcstabletimeincvol" in rep.text()
    # many knots: each rigid section stiffens the beam where it bends
    _, conv, rep = convert_str(CIRC_BEAM + "*Nset, nset=ALL\n1, 2, 3\n*Boundary\n1, 1, 3\n"
                               "3, 2, 3\nALL, 4, 4\n" + CIRC_STATIC)
    assert list(conv._knots) == [1, 2, 3] and "3 of the 3 element end nodes" in rep.text()


def test_circ_rotation_bc_examples():
    # the decks validate_with_ccx.py checks against beam theory: knot beams at the pinned ends
    # whose twist is held (1, 21) and at the turned tip (121), none at the clamp (101) ...
    body, conv, _ = convert(os.path.join(EXAMPLES, "beam_circ_rotation_bcs.inp"))
    g = reparse(body)
    assert list(conv._knots) == [1, 21, 121] and len(g.elsets["ABQ2CCX_KNOT"]) == 3
    assert {t for t, _ in g.elements.values()} == {"B32", "B31"} and not dangling_refs(g)
    # ... and the planar circular beam's twist held at the first element's middle node
    body, conv, _ = convert(os.path.join(EXAMPLES, "planar_pinned_circ_beam.inp"))
    g = reparse(body)
    assert g.elements[1] == ("B32", [1, 22, 2]) and not conv._knots
    assert "*BOUNDARY\nABQ2CCX_PLANAR, 3, 3\n22, 4, 5\n" in body.split("*STEP")[0]
    assert g.nset("ABQ2CCX_PLANAR") == list(range(1, 42)) and not dangling_refs(g)


# --- *DISTRIBUTION orientations (what ccx 2.23 does: see Converter._plan_distributions) ---
HEX3 = """*Node
1, 0.,0.,0.
2, 1.,0.,0.
3, 1.,1.,0.
4, 0.,1.,0.
5, 0.,0.,1.
6, 1.,0.,1.
7, 1.,1.,1.
8, 0.,1.,1.
9, 2.,0.,0.
10, 2.,1.,0.
11, 2.,0.,1.
12, 2.,1.,1.
13, 3.,0.,0.
14, 3.,1.,0.
15, 3.,0.,1.
16, 3.,1.,1.
*Element, type=C3D8, elset=ALL
1, 1,2,3,4,5,6,7,8
2, 2,9,10,3,6,11,12,7
3, 9,13,14,10,11,15,16,12
*Elset, elset=PAIR
2, 3
*Elset, elset=E1
1
*Material, name=M
*Elastic, type=ENGINEERING CONSTANTS
100000., 8000., 8000., 0.3, 0.3, 0.45, 4000., 4000.
3000.
"""


def _card(body, head):
    """The data lines after the live card line ``head`` up to the next keyword line."""
    lines = body.splitlines()
    i = lines.index(head)
    out = []
    for ln in lines[i + 1:]:
        if ln.startswith("*"):
            break
        out.append(ln)
    return out


def test_distribution_solid_lines_resolved_for_ccx():
    # ccx turns only a distribution's first line by the rotation line and ignores an origin:
    # both are applied to the axes instead; the default line comes first; the set label
    # covers its members and the later line for element 3 wins; the table is dropped
    body, _, rep = convert_str(HEX3 + "*Distribution Table, name=T1\ncoord3D, coord3D\n"
                               "*Distribution, name=Disc, location=ELEMENT, Table=T1\n"
                               ", 1., 0., 0., 0., 1., 0.\n1, 0., 1., 0., -1., 0., 0.\n"
                               "PAIR, 0., 1., 0., -1., 0., 0.\n"
                               "3, 11., 10., 0., 10., 11., 0., 10., 10., 0.\n"
                               "*Orientation, name=Ori-1\nDisc\n3, 90.\n"
                               "*Solid Section, elset=ALL, material=M, orientation=Ori-1\n,\n")
    assert _card(body, "*DISTRIBUTION, NAME=DISC") == [
        ", 0, 1, 0, -1, 0, 0", "1, -1, 0, 0, 0, -1, 0", "2, -1, 0, 0, 0, -1, 0", "3, 0, 1, 0, -1, 0, 0"]
    assert _card(body, "*ORIENTATION, NAME=Ori-1") == ["DISC"]                # no rotation line
    assert not any(l.startswith("*DISTRIBUTION TABLE") for l in _live(body))
    assert "TABLE of an orientation distribution dropped" in rep.text() and rep.n_warnings == 0
    # lines that need no change keep their tokens exactly
    body, _, _ = convert_str(HEX3 + "*Distribution, name=Disc\n, 1., 0., 0., 0., 1., 0.\n"
                             "2, 0.866025403784, 0.5, 0., -0.5, 0.866025403784, 0.\n"
                             "*Orientation, name=Ori-1\nDisc\n3, 0.\n"
                             "*Solid Section, elset=PAIR, material=M, orientation=Ori-1\n,\n")
    assert _card(body, "*DISTRIBUTION, NAME=DISC") == [
        ", 1., 0., 0., 0., 1., 0.", "2, 0.866025403784, 0.5, 0., -0.5, 0.866025403784, 0."]


def test_distribution_name_ccx_reads_as_number():
    # ccx tries (f20.0) on the orientation's data line first: these names parse as reals
    for name in ("D1", "E-3", "Q1", "1+2", "12", "1.5", ".", "+", "INF", "nan",
                 "12345678901234567890X"):
        assert A._fortran_real_like(name), name
    for name in ("E", "D", "1E", "D+", "INFX", "DISC", "ORI-1-DISCORIENT", "D_1"):
        assert not A._fortran_real_like(name), name
    body, _, _ = convert_str(HEX3 + "*Distribution, name=D1\n, 1., 0., 0., 0., 1., 0.\n"
                             "*Orientation, name=Ori-1\nD1\n"
                             "*Solid Section, elset=ALL, material=M, orientation=Ori-1\n,\n")
    name = _card(body, "*ORIENTATION, NAME=Ori-1")[0]
    assert name != "D1" and not A._fortran_real_like(name) and f"*DISTRIBUTION, NAME={name}" in body


def test_distribution_named_by_two_orientations_gets_two_copies():
    # ccx hands a distribution to the first *ORIENTATION naming it; each copy lists only the
    # elements of its own solid sections, so the copies never re-tag each other's elements
    body, _, _ = convert_str(HEX3 + "*Distribution, name=Disc\n, 1., 0., 0., 0., 1., 0.\n"
                             "1, 0., 1., 0., -1., 0., 0.\n2, 0., 1., 0., -1., 0., 0.\n"
                             "3, 0., 1., 0., -1., 0., 0.\n"
                             "*Orientation, name=O1\nDisc\n*Orientation, name=O2\nDisc\n3, 90.\n"
                             "*Solid Section, elset=E1, material=M, orientation=O1\n,\n"
                             "*Solid Section, elset=PAIR, material=M, orientation=O2\n,\n")
    assert _card(body, "*DISTRIBUTION, NAME=DISC") == [", 1., 0., 0., 0., 1., 0.",
                                                        "1, 0., 1., 0., -1., 0., 0."]
    assert _card(body, "*DISTRIBUTION, NAME=DISC_O2") == [
        ", 0, 1, 0, -1, 0, 0", "2, -1, 0, 0, 0, -1, 0", "3, -1, 0, 0, 0, -1, 0"]
    assert _card(body, "*ORIENTATION, NAME=O1") == ["DISC"]
    assert _card(body, "*ORIENTATION, NAME=O2") == ["DISC_O2"]


DIST_PART = """*Part, name=P
*Node
1, 0.,0.,0.
2, 1.,0.,0.
3, 1.,1.,0.
4, 0.,1.,0.
5, 0.,0.,1.
6, 1.,0.,1.
7, 1.,1.,1.
8, 0.,1.,1.
*Element, type=C3D8, elset=ALL
1, 1,2,3,4,5,6,7,8
*Distribution, name=Disc, location=ELEMENT, Table=Disc_Table
, 1., 0., 0., 0., 1., 0.
1, 1., 0., 0., 0., 1., 0.
*Orientation, name=Ori-1, system=RECTANGULAR
Disc
3, 0.
*Solid Section, elset=ALL, orientation=Ori-1, material=M
,
*End Part
*Assembly, name=Assembly
*Instance, name=I1, part=P
*End Instance
*Instance, name=I2, part=P
0., 0., 0.
0., 0., 0., 0., 0., 1., 90.
*End Instance
*End Assembly
*Distribution Table, name=Disc_Table
coord3D, coord3D
*Material, name=M
*Elastic, type=ENGINEERING CONSTANTS
100000., 8000., 8000., 0.3, 0.3, 0.45, 4000., 4000.
3000.
"""


def test_distribution_flattened_per_instance():
    # each instance: its own distribution name (and the orientation's reference to it),
    # element labels offset, and the axes turned with a rotated instance
    body, _, _ = convert_str(DIST_PART)
    assert _card(body, "*DISTRIBUTION, NAME=I1_DISC") == [", 1., 0., 0., 0., 1., 0.",
                                                           "1, 1., 0., 0., 0., 1., 0."]
    assert _card(body, "*ORIENTATION, NAME=I1_ORI-1, SYSTEM=RECTANGULAR") == ["I1_DISC"]
    assert _card(body, "*DISTRIBUTION, NAME=I2_DISC") == [", 0, 1, 0, -1, 0, 0",
                                                           "2, 0, 1, 0, -1, 0, 0"]
    assert _card(body, "*ORIENTATION, NAME=I2_ORI-1, SYSTEM=RECTANGULAR") == ["I2_DISC"]
    assert "*SOLID SECTION, ELSET=I2_ALL, ORIENTATION=I2_ORI-1, MATERIAL=M" in body
    assert not dangling_refs(reparse(body))


def test_composite_ply_orientation_named_per_instance():
    deck = DIST_PART.replace("*Solid Section, elset=ALL, orientation=Ori-1, material=M\n,\n",
                             "*Orientation, name=Ori-2\n1., 0., 0., 0., 1., 0.\n"
                             "*Solid Section, elset=ALL, composite\n1., 1, M, Ori-2, Ply-1\n"
                             "1., 1, M, 45., Ply-2\n")
    body, _, _ = convert_str(deck)
    assert "1., 1, M, I1_ORI-2, Ply-1" in body and "1., 1, M, I2_ORI-2, Ply-1" in body
    assert "1., 1, M, 45., Ply-2" in body                                       # angle kept


def test_shell_general_section_copied_per_instance():
    # a part's *Shell General Section is copied per instance like a *Shell Section: on the
    # instance's own set, naming the instance's orientations (also on ply lines).  Emitted
    # once with the part's names, it named an undefined set and no instance had a section.
    part = ("*Part, name=P\n*Node\n1, 0., 0., 0.\n2, 1., 0., 0.\n3, 1., 1., 0.\n4, 0., 1., 0.\n"
            "5, .5, 0., 0.\n6, 1., .5, 0.\n7, .5, 1., 0.\n8, 0., .5, 0.\n"
            "*Element, type=S8R, elset=PANEL\n1, 1, 2, 3, 4, 5, 6, 7, 8\n"
            "*Orientation, name=Ori-1\n1., 0., 0., 0., 1., 0.\n"
            "*Orientation, name=Ori-2\n0., 1., 0., -1., 0., 0.\n{}*End Part\n"
            "*Assembly, name=A\n*Instance, name=I1, part=P\n*End Instance\n"
            "*Instance, name=I2, part=P\n2., 0., 0.\n0., 0., 0., 0., 0., 1., 90.\n*End Instance\n"
            "*End Assembly\n*Material, name=M\n*Elastic\n1000., 0.3\n")
    bodies = {}
    for form, section in (("material", "*Shell General Section, elset=PANEL, material=M, "
                                       "orientation=Ori-1\n0.1,\n"),
                          ("composite", "*Shell General Section, elset=PANEL, composite, "
                                        "orientation=Ori-1\n0.1, , M, 0., Ply-1\n"
                                        "0.1, , M, Ori-2, Ply-2\n0.1, , M, 45., Ply-3\n")):
        body, _, _ = convert_str(part.format(section))
        live = _live(body)
        # one section per instance; the sets and orientations they name are all defined
        assert sum(l.startswith("*SHELL SECTION") for l in live) == 2, form
        assert all(f"*ORIENTATION, NAME={i}_ORI-{k}" in live for i in ("I1", "I2") for k in (1, 2))
        g = reparse(body)
        assert g.elsets["I1_PANEL"] == [1] and g.elsets["I2_PANEL"] == [2]
        assert not dangling_refs(g), dangling_refs(g)
        bodies[form] = body
    for inst, axes in (("I1", "1., 0., 0., 0., 1., 0."), ("I2", "0., 1., 0., -1., 0., 0.")):
        assert _card(bodies["material"], f"*SHELL SECTION, ELSET={inst}_PANEL, MATERIAL=M, "
                                         f"ORIENTATION={inst}_ORI-1") == ["0.1"]
        plies = _card(bodies["composite"], f"*SHELL SECTION, ELSET={inst}_PANEL, COMPOSITE")
        assert plies[:2] == [f"0.1, , M, {inst}_ORI-1", f"0.1, , M, {inst}_ORI-2"], plies
        # the 45 deg ply turns this instance's copy of the section axes (I2's are turned)
        assert _card(bodies["composite"], "*ORIENTATION, NAME=" + plies[2].split(", ")[-1]) == \
            [axes, "3, 45."]


def test_distribution_shell_section_split_per_direction():
    # ccx gives every element of a shell section the distribution's first line, so the
    # section is split into one set + plain orientation + section per distinct direction
    deck = S4.replace("*Shell Section,elset=E,material=M\n0.1\n",
                      "*Distribution, name=DP\n, 1., 0., 0., 0., 1., 0.\n2, 0., 1., 0., -1., 0., 0.\n"
                      "*Orientation, name=OP\nDP\n3, 0.\n"
                      "*Shell Section, elset=E, material=M, orientation=OP\n0.1, 5\n")
    body, _, rep = convert_str(deck)
    g = reparse(body)
    assert g.elsets["E_G1"] == [1] and g.elsets["E_G2"] == [2]
    assert _card(body, "*ORIENTATION, NAME=OP_A1") == ["1., 0., 0., 0., 1., 0."]
    assert _card(body, "*ORIENTATION, NAME=OP_A2") == ["0., 1., 0., -1., 0., 0."]
    assert _card(body, "*SHELL SECTION, ELSET=E_G1, MATERIAL=M, ORIENTATION=OP_A1") == ["0.1"]
    assert _card(body, "*SHELL SECTION, ELSET=E_G2, MATERIAL=M, ORIENTATION=OP_A2") == ["0.1"]
    assert not any(l.startswith(("*DISTRIBUTION", "*ORIENTATION, NAME=OP\n")) for l in _live(body))
    assert "split into one element set" in rep.text()
    # composite: a ply angle turns the group's own axes; a ply may name a distribution
    # orientation of its own
    deck = S4.replace("*Shell Section,elset=E,material=M\n0.1\n",
                      "*Distribution, name=DP\n, 1., 0., 0., 0., 1., 0.\n2, 0., 1., 0., -1., 0., 0.\n"
                      "*Distribution, name=DM\n, 1., 0., 0., 0., 1., 0.\n2, 0., -1., 0., 1., 0., 0.\n"
                      "*Orientation, name=OP\nDP\n*Orientation, name=OM\nDM\n"
                      "*Shell Section, elset=E, composite, orientation=OP\n0.1, 3, M, 30.\n"
                      "0.1, 3, M, OM\n")
    body, _, _ = convert_str(deck)
    sec = _card(body, "*SHELL SECTION, ELSET=E_G2, COMPOSITE")
    assert len(sec) == 2
    turned = _card(body, "*ORIENTATION, NAME=" + sec[0].split(", ")[-1])
    assert turned == ["0., 1., 0., -1., 0., 0.", "3, 30."]
    assert _card(body, "*ORIENTATION, NAME=" + sec[1].split(", ")[-1]) == ["0., -1., 0., 1., 0., 0."]
    assert not dangling_refs(reparse(body))


def test_distribution_without_data_comments_out_its_orientation():
    body, _, rep = convert_str(HEX3 + "*Distribution, name=Disc, input=missing.ori\n"
                               "*Orientation, name=O1\nDisc\n"
                               "*Solid Section, elset=ALL, material=M, orientation=O1\n,\n")
    assert not any(l.startswith(("*DISTRIBUTION", "*ORIENTATION")) for l in _live(body))
    assert "per-element material" in rep.text() and "INPUT=missing.ori" in rep.text()
    # a composite ply angle on it is not turned off a made-up frame; ccx then stops on the
    # missing orientation instead of running global axes
    deck = S4.replace("*Shell Section,elset=E,material=M\n0.1\n",
                      "*Distribution, name=DP, input=missing.ori\n*Orientation, name=OP\nDP\n"
                      "*Shell Section, elset=E, composite, orientation=OP\n0.1, 3, M, 30.\n")
    body, _, _ = convert_str(deck)
    assert "0.1, , M, OP" in body and "ABQ2CCX_OR" not in body
    # node-based distributions cannot orient elements
    body, _, rep = convert_str(HEX3 + "*Distribution, name=Disc, location=NODE\n"
                               ", 1., 0., 0., 0., 1., 0.\n1, 0., 1., 0., -1., 0., 0.\n"
                               "*Orientation, name=O1\nDisc\n"
                               "*Solid Section, elset=ALL, material=M, orientation=O1\n,\n")
    assert not any(l.startswith(("*DISTRIBUTION", "*ORIENTATION")) for l in _live(body))
    assert "not element-based" in rep.text()


def test_distribution_not_named_by_an_orientation_commented():
    # ccx distributes orientations only (Abaqus also shell thicknesses, material properties)
    body, _, rep = convert_str(HEX3 + "*Distribution, name=Thick, location=ELEMENT, table=TT\n"
                               ", 0.1\n1, 0.2\n*Solid Section, elset=ALL, material=M\n,\n")
    assert not any(l.startswith("*DISTRIBUTION") for l in _live(body))
    assert "not named by any *ORIENTATION" in rep.text()


def test_distribution_plate_examples():
    # the pairs validate_with_ccx.py compares: distribution form vs one orientation and
    # section per element
    body, _, _ = convert(os.path.join(EXAMPLES, "distribution_solid_plate.inp"))
    for inst in ("PLATE-1", "PLATE-2"):
        lines = _card(body, f"*DISTRIBUTION, NAME={inst}_ORI-1-DISCORIENT")
        assert len(lines) == 11 and lines[0].startswith(", ")    # default + elements 1-10
        assert _card(body, f"*ORIENTATION, NAME={inst}_ORI-1, SYSTEM=RECTANGULAR") == \
            [f"{inst}_ORI-1-DISCORIENT"]
    assert not dangling_refs(reparse(body))
    body, _, _ = convert(os.path.join(EXAMPLES, "distribution_shell_plate.inp"))
    g = reparse(body)
    assert [len(g.elsets[f"PANEL-1_PANEL_G{k}"]) for k in range(1, 17)] == [1] * 16
    assert body.count("*SHELL SECTION, ELSET=PANEL-1_PANEL_G") == 16
    assert not any(l.startswith("*DISTRIBUTION") for l in _live(body))
    assert not dangling_refs(g), dangling_refs(g)
    for name in ("distribution_solid_plate_explicit", "distribution_shell_plate_explicit"):
        body, _, _ = convert(os.path.join(EXAMPLES, name + ".inp"))
        assert "*DISTRIBUTION" not in body and not dangling_refs(reparse(body))


# a clamped RECT cantilever, static step 1
STEPPED_BEAM = CIRC_BEAM.replace("section=CIRC\n0.05", "section=RECT\n0.1, 0.2") + """*Step
*Static
*Boundary
1, ENCASTRE
*Cload
3, 3, -1.
*End Step
"""

# a 2-element S4 plate clamped along x = 0 (ROOT), its tip z prescribed, static step 1
STEPPED_PLATE = """*Node
1, 0., 0., 0.
2, 1., 0., 0.
3, 2., 0., 0.
4, 0., 1., 0.
5, 1., 1., 0.
6, 2., 1., 0.
*Element, type=S4, elset=PLATE
1, 1, 2, 5, 4
2, 2, 3, 6, 5
*Nset, nset=ROOT
1, 4
*Nset, nset=TIP
3, 6
*Shell Section, elset=PLATE, material=M
0.1
*Material, name=M
*Elastic
2.1e5, 0.3
*Step
*Static
*Boundary
ROOT, ENCASTRE
TIP, 3, 3, 0.01
*End Step
"""


def test_op_new_that_removes_nothing_is_dropped():
    # ccx 2.23 does not rebuild rotational BCs that a later step's *BOUNDARY, OP=NEW
    # re-specifies on shell/beam nodes (probed: the clamped root becomes a hinge, *FREQUENCY
    # finds a 0.1 Hz mode); an OP=NEW that removes nothing changes nothing, so it goes
    deck = STEPPED_BEAM + "*Step\n*Frequency\n4\n*Boundary, op=NEW\n1, 1, 3\n*Boundary, op=NEW\n" \
                          "1, 4, 6\n*End Step\n"
    body, conv, rep = convert_str(deck)
    second = body.split("*STEP")[2]
    assert "*BOUNDARY, OP=NEW" not in body and not conv._knots
    assert second.count("** [abq2ccx] OP=NEW dropped") == 1 and "*BOUNDARY\n1, 4, 6\n" in second
    assert "OP=NEW dropped in step(s) 2" in rep.text()
    # on shells it would also zero unrelated BCs; a changed value is no removal
    body, conv, _ = convert_str(STEPPED_PLATE + "*Step\n*Static\n*Boundary, op=NEW\nROOT, ENCASTRE\n"
                                                "TIP, 3, 3, 0.02\n*End Step\n")
    assert "*BOUNDARY, OP=NEW" not in body and "*BOUNDARY\nROOT, 1, 6\nTIP, 3, 3, 0.02\n" in body
    # kept where ccx has no rotation constraint to rebuild: in the first step (it builds
    # them after reading a step), ...
    body, _, rep = convert_str(STEPPED_BEAM.replace("*Step\n*Static\n*Boundary\n",
                                                    "*Boundary\n1, ENCASTRE\n*Step\n*Static\n"
                                                    "*Boundary, op=NEW\n"))
    assert "*BOUNDARY, OP=NEW\n1, 1, 6\n" in body and "OP=NEW dropped" not in rep.text()
    # ... without rotational BCs on shell/beam nodes, ...
    body, _, _ = convert_str(deck.replace("1, ENCASTRE", "1, PINNED\n3, 2, 3").replace("1, 4, 6",
                                                                                       "3, 2, 3"))
    assert body.count("*BOUNDARY, OP=NEW") == 2
    # ... and after *DYNAMIC steps (ccx makes knots of their rotational-BC nodes)
    body, conv, _ = convert_str(deck.replace("*Static", "*Dynamic\n0.01, 0.1").replace(
        "*Frequency\n4", "*Dynamic\n0.01, 0.1"))
    assert body.count("*BOUNDARY, OP=NEW") == 2 and not conv._knots


def test_op_new_that_removes_bcs_makes_knots():
    # an OP=NEW that removes a BC stays; the clamp it re-specifies gets a force-free knot
    # beam: ccx then carries the node's rotations on a knot, whose BCs OP=NEW handles
    deck = STEPPED_BEAM.replace("1, ENCASTRE\n", "1, ENCASTRE\n2, 3, 3\n") + \
        "*Step\n*Static\n*Boundary, op=NEW\n1, ENCASTRE\n*End Step\n"
    body, conv, rep = convert_str(deck)
    assert "*BOUNDARY, OP=NEW\n1, 1, 6\n" in body and list(conv._knots) == [1]
    g = reparse(body)
    assert g.elsets["ABQ2CCX_KNOT"] == [3] and g.elements[3] == ("B31", [1, 4])
    assert "OP=NEW in step(s) 2 removes boundary conditions" in rep.text()
    assert not dangling_refs(g), dangling_refs(g)
    # a beam node whose rotations OP=NEW releases needs none, ...
    released = STEPPED_BEAM.replace("1, ENCASTRE\n", "1, ENCASTRE\n3, 3, 3\n") + \
        "*Step\n*Static\n*Boundary, op=NEW\n1, 1, 3\n3, 3, 3\n*End Step\n"
    _, conv, _ = convert_str(released)
    assert not conv._knots
    # ... unless a later step fixes them again (ccx would not rebuild them either)
    _, conv, _ = convert_str(released + "*Step\n*Static\n*Boundary\n1, 4, 6\n*End Step\n")
    assert list(conv._knots) == [1]
    # shell nodes with rotational BCs before such a step always do: ccx's stale SPC
    # indices would zero unrelated BCs (probed: a prescribed displacement came out 0)
    plate = STEPPED_PLATE + "*Step\n*Static\n*Boundary, op=NEW\nROOT, 1, 3\n*End Step\n"
    body, conv, _ = convert_str(plate)
    assert list(conv._knots) == [1, 4] and "*ELSET, ELSET=ABQ2CCX_KNOT\n3, 4\n" in body


def test_op_new_knots_skipped_with_explicit_steps():
    # the massless knot beams stop ccx's explicit solver ('*ERROR in calcstabletimeincvol',
    # probed on 2.23): a deck with an explicit step gets a warning instead
    deck = STEPPED_PLATE + "*Step\n*Static\n*Boundary, op=NEW\nROOT, 1, 3\n*End Step\n" \
                           "*Step\n*Dynamic, Explicit\n1e-6, 1e-5\n*End Step\n"
    body, conv, rep = convert_str(deck)
    assert not conv._knots and "ABQ2CCX_KNOT" not in body
    assert "stop ccx's explicit solver" in rep.text() and "from step 2 on" in rep.text()


def test_op_new_examples():
    # the decks validate_with_ccx.py runs: step 2 re-specifies every BC (OP=NEW dropped) /
    # removes the beam's prop (OP=NEW kept, the beam root and plate root nodes are knots)
    body, conv, _ = convert(os.path.join(EXAMPLES, "op_new_respecify.inp"))
    assert "*BOUNDARY, OP=NEW" not in body and not conv._knots
    assert not dangling_refs(reparse(body))
    body, conv, _ = convert(os.path.join(EXAMPLES, "op_new_remove.inp"))
    assert body.split("*STEP")[2].count("*BOUNDARY, OP=NEW") == 2
    assert list(conv._knots) == [1, 1001, 1101, 1201, 1301, 1401]
    assert not dangling_refs(reparse(body))


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
