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
    # ccx requires a TYPE on *CONTACT PAIR (Abaqus defaults it); Abaqus-only params drop.
    deck = "*SURFACE INTERACTION, NAME=SI\n*CONTACT PAIR, INTERACTION=SI, SUPPLEMENTARY CONSTRAINTS=NO\nA, B\n"
    body, _, _ = convert_str(deck)
    cp = [l for l in body.splitlines() if l.upper().startswith("*CONTACT PAIR")][0]
    assert "TYPE=SURFACE TO SURFACE" in cp.upper() and "SUPPLEMENTARY" not in cp.upper()


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
    # --approximate reframes *STATIC, RIKS as plain *STATIC; without it the card is kept
    # (with a pointer to the flag) so nothing changes silently.
    deck = ("*Node\n1,0,0,0\n2,1,0,0\n*Element,type=T3D2,elset=E\n1,1,2\n"
            "*Step\n*Static, RIKS\n0.01,1.,1e-5,0.1\n*End Step\n")
    body, _, rep = convert_str(deck)
    assert any(l.upper().startswith("*STATIC, RIKS") for l in body.splitlines())
    assert "--approximate" in rep.text()
    body, _, rep = convert_str(deck, approximate=True)
    lines = [l for l in body.splitlines() if l.upper().startswith("*STATIC")]
    assert lines == ["*STATIC"] and "[APPROX]" in rep.text()


def test_approximate_explicit_to_implicit():
    deck = ("*Node\n1,0,0,0\n2,1,0,0\n*Element,type=T3D2,elset=E\n1,1,2\n"
            "*Step\n*Dynamic, EXPLICIT\n, 0.01\n*End Step\n")
    body, _, rep = convert_str(deck, approximate=True)
    lines = body.splitlines()
    i = next(k for k, l in enumerate(lines) if l.upper().startswith("*DYNAMIC"))
    assert "EXPLICIT" not in lines[i].upper()
    assert lines[i + 1].replace(" ", "") == "1e-05,0.01"     # period/1000, period
    assert "[APPROX]" in rep.text()


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
