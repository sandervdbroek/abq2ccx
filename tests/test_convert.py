#!/usr/bin/env python3
"""Regression tests for abq2ccx.

Run directly:   python tests/test_convert.py
or with pytest: pytest tests/

The checks convert each bundled example deck and assert that the resulting
CalculiX model is referentially consistent (every element node, set member and
load/section reference resolves) plus a handful of conversion-specific
expectations.
"""

import math
import os
import re
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
    # *BOUNDARY, TYPE=VELOCITY: a zero velocity from rest is a zero displacement BC
    assert "*BOUNDARY\nNALL, 1, 3\n" in body
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


def test_overconstraint_equation_reordered():
    # ccx eliminates an equation's FIRST term and stops when that DOF also has a BC, or is
    # the first term of another equation; listing the same equation with a free DOF first
    # is accepted.  A duplicate holds whenever the original does, so it is dropped.
    deck = ("*NODE\n1, 0.,0.,0.\n2, 1.,0.,0.\n3, 2.,0.,0.\n"
            "*EQUATION\n2\n1, 1, 1.0, 2, 1, -1.0\n")
    body, _, rep = convert_str(deck + "*BOUNDARY\n1, 1, 1\n")
    assert _equations(body) == ["2,1,-1.0,1,1,1.0"] and "reordered" in rep.text()
    assert "Possible overconstraint" not in rep.text()
    body, _, _ = convert_str(deck + "*EQUATION\n2\n1, 1, 1.0, 3, 1, -1.0\n")
    assert _equations(body) == ["1,1,1.0,2,1,-1.0", "3,1,-1.0,1,1,1.0"]
    body, _, rep = convert_str(deck + "*EQUATION\n2\n1, 1, 1.0, 2, 1, -1.0\n*BOUNDARY\n1, 1, 1\n")
    assert _equations(body) == ["2,1,-1.0,1,1,1.0"] and body.count("*EQUATION") == 1
    assert "redundant" in rep.text()
    # a loop of ties: the closing equation follows from the others — ccx would take it, but
    # finds a zero coefficient on its dependent side and silently holds the loop at zero
    loop = "".join(f"*EQUATION\n2\n{a},1,1.,{b},1,-1.\n" for a, b in ((1, 2), (2, 3), (3, 1)))
    body, _, rep = convert_str("*NODE\n1,0,0,0\n2,1,0,0\n3,2,0,0\n" + loop)
    assert _equations(body) == ["1,1,1.,2,1,-1.", "2,1,1.,3,1,-1."] and "redundant" in rep.text()
    # every DOF under a BC, one of them nonzero: a real overconstraint, kept and flagged
    body, _, rep = convert_str(deck + "*BOUNDARY\n1, 1, 1\n2, 1, 1, 0.5\n")
    assert _equations(body) == ["1,1,1.0,2,1,-1.0"] and "Possible overconstraint" in rep.text()
    # a rigid-body member's translation is eliminated by ccx itself: never made dependent
    rb = (HEX + "*Node\n100, 0.5, 0.5, 2.\n9, 3., 0., 0.\n*Nset, nset=TOP\n5,6,7,8\n"
          "*Rigid Body, ref node=100, tie nset=TOP\n*Equation\n2\n5, 1, 1., 9, 1, -1.\n")
    body, _, _ = convert_str(rb)
    assert _equations(body) == ["9,1,-1.,5,1,1."]
    _, _, rep = convert_str(rb + "*Boundary\n6, 1, 1\n100, 2, 2\n")
    assert "node 6 DOF 1 follows reference node 100 through a *RIGID BODY" in rep.text()


def test_mpc_lines_converted_one_by_one():
    # one line ccx cannot take no longer drops the whole card: PIN -> *EQUATION on DOFs
    # 1-3 (exact), the SLIDER and user (numeric) lines alone are commented out
    deck = B2 + "*MPC\nPIN, 3, 2\nSLIDER, 3, 1, 4\n99, 3, 2\n"
    body, _, rep = convert_str(deck)
    assert _equations(body) == [f"3,{d},1.,2,{d},-1." for d in (1, 2, 3)]
    assert "** SLIDER, 3, 1, 4" in body and "** 99, 3, 2" in body
    assert "user type 99" in rep.text() and "*MPC SLIDER has no ccx equivalent" in rep.text()
    # node sets pair node by node (ascending ids), or every node with a single second
    # node; sets of different sizes cannot pair: that line is commented out
    sets = (HEX + "*Node\n11,0,0,2\n12,1,0,2\n13,1,1,2\n14,0,1,2\n*Nset,nset=A\n12, 11\n"
            "*Nset,nset=B\n2, 1\n*Nset,nset=D\n13, 14\n*Nset,nset=E\n5, 6, 7\n"
            "*MPC\nPIN, A, B\nPIN, D, 8\nPIN, D, E\n")
    body, _, rep = convert_str(sets)
    assert _equations(body) == [f"{a},{d},1.,{b},{d},-1." for a, b in ((11, 1), (12, 2), (13, 8),
                                                                      (14, 8)) for d in (1, 2, 3)]
    assert "** PIN, D, E" in body and "different sizes" in rep.text()
    # ccx reads an *EQUATION's DOFs in a node's *TRANSFORM axes: warned
    _, _, rep = convert_str(HEX + "*Node\n9,2,0,0\n*Nset,nset=T9\n9\n*Transform, nset=T9\n"
                            "0.,1.,0.,-1.,0.,0.\n*MPC\nPIN, 9, 2\n")
    assert "*MPC on a node with a *TRANSFORM" in rep.text()


def test_mpc_tie_ties_rotations_between_knots():
    # ccx ignores DOFs 4-6 of a plain beam node in an *EQUATION (probed: a TIE'd joint
    # stays a hinge), so both nodes become knots and all six DOFs are tied
    body, conv, rep = convert_str(B2 + "*MPC\nTIE, 3, 2\n")
    assert sorted(conv._knots) == [2, 3] and "ABQ2CCX_KNOT" in body
    assert _equations(body) == [f"3,{d},1.,2,{d},-1." for d in range(1, 7)]
    # a solid and a free node have no rotations; a thermal step ties the temperature too
    solid = HEX + "*Node\n9, 2., 0., 0.\n*MPC\nTIE, 9, 2\n"
    body, conv, _ = convert_str(solid)
    assert _equations(body) == [f"9,{d},1.,2,{d},-1." for d in (1, 2, 3)] and not conv._knots
    body, _, _ = convert_str(solid + "*Step\n*Coupled Temperature-Displacement\n1., 1.\n*End Step\n")
    assert _equations(body) == [f"9,{d},1.,2,{d},-1." for d in (1, 2, 3, 11)]


def test_mpc_link_linearised_or_ccx_beam():
    # LINK keeps the distance between two nodes: linearised at the initial geometry when no
    # step runs NLGEOM (as Abaqus' small-displacement analysis does) ...
    link = ("*Node\n1,0,0,0\n2,3,4,0\n3,7,1,0\n*Element,type=SpringA,elset=S\n1,3,2\n*Spring,"
            "elset=S\n\n1000.\n*MPC\nLINK, 2, 1\n")
    body, _, rep = convert_str(link + "*Step\n*Static\n*End Step\n")
    lines = body.splitlines()
    i = lines.index("*EQUATION")
    assert lines[i + 1:i + 3] == ["4", "2, 2, 0.8, 2, 1, 0.6, 1, 2, -0.8, 1, 1, -0.6"]
    assert "linearised" in rep.text()
    # ... and ccx's *MPC BEAM (a distance MPC, probed) under NLGEOM
    nl = link + "*Step, nlgeom=YES\n*Static\n*End Step\n"
    body, _, rep = convert_str(nl)
    assert "*MPC\nBEAM, 2, 1" in body and "*EQUATION" not in "\n".join(_live(body))
    # ccx rejects a BEAM MPC on nodes of beams, shells or plane elements
    body, _, rep = convert_str(B2 + "*MPC\nLINK, 4, 1\n*Step, nlgeom=YES\n*Static\n*End Step\n")
    assert "** LINK, 4, 1" in body and "gen3dmpc" in rep.text()
    # a linear first step and a later NLGEOM one: only with --approximate
    mixed = link + "*Step\n*Static\n*End Step\n*Step, nlgeom=YES\n*Static\n*End Step\n"
    body, _, rep = convert_str(mixed)
    assert "** LINK, 2, 1" in body and "--approximate" in rep.text()
    body, _, rep = convert_str(mixed, approximate=True)
    assert "*MPC\nBEAM, 2, 1" in body and "[APPROX] *MPC LINK" in rep.text()


def test_mpc_beam_lines_become_rigid_bodies():
    # BEAM ties displacements AND rotations of the first node to a rigid beam from the
    # second: lines sharing a second node — or chained through one another — form one
    # *RIGID BODY on the chain's root, exact at any rotation
    deck = (S4 + "*Node\n200, 3., 0.5, 0.\n*MPC\nBEAM, R, REF\nBEAM, REF, 200\n"
            "*Boundary\n200, 4, 6\n")
    body, conv, rep = convert_str(deck)
    rot = conv._rb_rot[200]
    assert f"*RIGID BODY, NSET=ABQ2CCX_MPCB1, REF NODE=200, ROT NODE={rot}" in body
    assert "*NSET, NSET=ABQ2CCX_MPCB1\n5, 6, 100\n" in body
    assert sorted(conv._knots) == [5, 6]                               # shell members
    assert _equations(body) == [f"{n},{k},1.,{rot},{k - 3},-1." for n in (5, 6) for k in (4, 5, 6)]
    assert f"{rot}, 1, 3" in body and "200, 4, 6" not in body          # rotations -> ROT NODE
    assert "BEAM -> *RIGID BODY" in rep.text()
    # a shell node as the independent node: the ROT NODE follows its own rotation
    body, conv, _ = convert_str(S4 + "*MPC\nBEAM, 5, 2\nBEAM, 6, 2\n")
    rot = conv._rb_rot_synth[2]
    assert f"REF NODE=2, ROT NODE={rot}" in body and sorted(conv._knots) == [2, 5, 6]
    eqs = _equations(body)
    assert eqs[:3] == [f"{rot},{k},1.,2,{k + 3},-1." for k in (1, 2, 3)]
    # a node that is dependent twice is invalid in Abaqus too: its first line is used
    body, _, rep = convert_str(S4 + "*MPC\nBEAM, 5, 2\nBEAM, 5, 1\n")
    assert "dependent node of more than one BEAM line" in rep.text()
    assert body.count("*RIGID BODY") == 1 and "** BEAM, 5, 1" in body


def test_rigid_member_bcs_the_body_implies_are_left_out():
    # a member's zero BC on a DOF the rigid body eliminates stops ccx; it is implied (and
    # left out) when the reference node is held there and cannot rotate
    deck = (HEX + "*Node\n100, 0.5, 0.5, 2.\n*Nset,nset=TOP\n5,6,7,8\n*Nset,nset=SYM\n1,4,5,8\n"
            "*Rigid Body, ref node=100, tie nset=TOP\n*Boundary\nSYM, 1, 1\n100, 1, 1\n"
            "100, 3, 6\n*Step\n*Static\n*Boundary\n100, 2, 2, 0.1\n*End Step\n")
    body, conv, rep = convert_str(deck)
    lines = _live(body)
    i = lines.index("*BOUNDARY")
    assert lines[i + 1:i + 5] == ["ABQ2CCX_BC1, 1, 1", "100, 1, 1", "100, 3, 3",
                                  f"{conv._rb_rot[100]}, 1, 3"]      # SYM without 5 and 8
    assert reparse(body).nsets["ABQ2CCX_BC1"] == [1, 4] and "taken off 2 DOF(s)" in rep.text()
    # not implied: the body may turn about y, or a BC is nonzero; one that OP=NEW releases
    # before any step keeps it is left alone (it cannot clash)
    for edit in (("100, 3, 6", "100, 3, 3\n100, 6, 6"), ("SYM, 1, 1", "SYM, 1, 1, 0.01"),
                 ("*Boundary\n100, 2", "*Boundary, op=NEW\n100, 2")):
        body, _, rep = convert_str(deck.replace(*edit))
        assert "ABQ2CCX_BC1" not in body and "taken off" not in rep.text(), edit
    # a body of plane-strain nodes only turns about z; ccx's explicit solver cannot run it
    q = (Q4 + "*Node\n10, 0.5, 2.\n*Nset,nset=TOP\n3,4\n*Rigid Body, ref node=10, tie nset=TOP\n"
         "*Boundary\nL, 1, 1\n10, 1, 1\n10, 6, 6\n")
    body, _, rep = convert_str(q)
    assert [l for l in _bc_lines(body) if l.startswith(("L,", "1,", "4,"))] == ["1,1,1"]
    assert "taken off 1 DOF(s)" in rep.text() and "explicit dynamic" not in rep.text()
    _, _, rep = convert_str(q + "*Step\n*Dynamic, Explicit\n, 1e-4\n*End Step\n")
    assert "plane / axisymmetric elements in a deck with an explicit" in rep.text()


def test_bc_steps_follow_op_new():
    # a step keeps the BCs before it and a later value replaces an earlier one; OP=NEW
    # in a step starts from none
    k1, k2 = (1, 1), (2, 1)
    steps = [dict(a) for a in A.bc_steps([[(False, k1, True)], [(False, k2, False)],
                                          [(True, k2, True)], []])]
    assert steps == [{k1: True, k2: False}, {k2: True}, {k2: True}]
    assert [dict(a) for a in A.bc_steps([[(False, k1, True)]])] == [{k1: True}]


def test_rotation_tie_on_a_member_bc_makes_the_body_dependent():
    # a member rotation under a BC cannot be the tie's dependent term.  On a *RIGID BODY the BC
    # moves to the ROT NODE, as Abaqus moves it (the tie keeps the member dependent); where it
    # stays on the members (BCs that differ: warned), the ROT NODE's DOF becomes the first
    # tie's dependent term (the BC then holds the body's rotation) and the second tie is
    # dropped.  A *KINEMATIC reference node's DOFs 4-6 are eliminated by ccx itself, so that
    # tie is dropped (the BC governs it)
    rb = S4 + "*Rigid Body, ref node=REF, tie nset=R\n*Boundary\n5, 4, 4\n"
    body, conv, _ = convert_str(rb)
    rot = conv._rb_rot[100]
    assert _bc_lines(body) == [f"{rot},1,1"] and f"5,4,1.,{rot},1,-1." in _equations(body)
    body, _, rep = convert_str(rb + "6, 4, 4, 0.01\n")
    assert _bc_lines(body) == ["5,4,4", "6,4,4,0.01"] and "differ between the body's nodes" in rep.text()
    assert f"{rot},1,-1.,5,4,1." in _equations(body)
    assert not any(e.startswith("6,4,") for e in _equations(body))
    deck = (S4 + "*Surface, type=node, name=RS\nR\n*Coupling, constraint name=C, ref node=100, "
            "surface=RS\n*Kinematic\n*Boundary\n5, 4, 4\n")
    body, _, rep = convert_str(deck)
    assert not any(e.startswith("5,4,") or e.endswith(",5,4,1.") for e in _equations(body))
    assert "the BC governs it" in rep.text()


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
    def kinematic_line(body):
        lines = body.splitlines()
        return lines[next(i for i, l in enumerate(lines) if l.upper().startswith("*KINEMATIC")) + 1]
    deck = (HEX + "*Node\n9,0.5,0.5,2.\n*Nset, nset=TOP\n5,6,7,8\n*Surface, type=NODE, name=S\n"
            "TOP\n*Coupling, constraint name=C, ref node=9, surface=S\n*Kinematic\n1, 6\n")
    body, _, rep = convert_str(deck)
    assert kinematic_line(body).replace(" ", "") == "1,3"
    assert "clamped" in rep.text().lower()
    # 2-D nodes have no DOF 3 in Abaqus, and ccx holds theirs fixed and stops on a coupled one
    # ('dependent side of a MPC and a SPC', probed on 2.23): plane elements couple 1-2 only
    deck = ("*Node\n1,0.,0.,0.\n2,1.,0.,0.\n3,1.,1.,0.\n4,0.,1.,0.\n9,0.5,0.5,1.\n"
            "*Nset, nset=R\n9\n*Element, type=CPS4, elset=E\n1,1,2,3,4\n"
            "*Surface, type=ELEMENT, name=S\nE, S1\n"
            "*Coupling, constraint name=C, ref node=9, surface=S\n*Kinematic\n1, 6\n")
    body, _, rep = convert_str(deck)
    assert kinematic_line(body).replace(" ", "") == "1,2" and "DOFs above 2 left out" in rep.text()
    body, _, rep = convert_str(deck.replace("1, 6\n", ""))          # empty card: Abaqus' all
    assert kinematic_line(body).replace(" ", "") == "1,2" and "synthesized '1, 2'" in rep.text()
    body, _, _ = convert_str(deck.replace("*Coupling, constraint name=C, ref node=9, surface=S\n"
                                          "*Kinematic\n1, 6\n",
                                          "*Nset, nset=M\n1, 2\n*Kinematic Coupling, ref node=9\n"
                                          "M, 1, 3\nM, 3, 3\n"))
    assert body.count("*KINEMATIC") == 1 and kinematic_line(body) == "1, 2"     # 3, 3 dropped


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
SHEARED_EXPANSION = "*Expansion, type=ANISO\n1e-3, 2e-3, 4e-3, 5e-4, 0., 0.\n"


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
    # (beside one with a shear coefficient: one without goes out as ORTHO)
    body, _, rep = convert_str("*Material, name=ISO\n*Elastic\n1000., 0.2, 50.\n" + SHEARED_EXPANSION +
                               "*Material, name=EC\n*Elastic, type=ENGINEERING CONSTANTS\n"
                               "1000., 2000., 3000., 0.2, 0.25, 0.3, 400., 500.\n600.\n"
                               + SHEARED_EXPANSION + "*Material, name=LAM\n*Elastic, type=LAMINA\n"
                                 "1000., 600., 0.25, 300., 300., 250.\n" + SHEARED_EXPANSION)
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


def expansion_card(body, material):
    """The emitted *EXPANSION card of ``material``: (keyword line, data lines)."""
    lines = body.splitlines()
    i = lines.index(f"*MATERIAL, NAME={material}")
    j = next(k for k in range(i + 1, len(lines)) if lines[k].startswith("*EXPANSION"))
    k = next((k for k in range(j + 1, len(lines)) if lines[k].startswith("*")), len(lines))
    return lines[j], lines[j + 1:k]


def test_aniso_expansion_shear_halved():
    # Abaqus gives alpha12, alpha13, alpha23 as engineering shear strain per degree (gamma12 =
    # alpha12 dT), ccx 2.23 reads them as tensor components (eps12 = alpha12 dT): they are
    # halved, row by row; the normal coefficients, temperatures and blanks stay
    elastic = "*Elastic, type=ANISOTROPIC\n" + "1., 0., 1., 0., 0., 1., 0., 0.\n0., 1., 0., 0., " \
              "0., 0., 1., 0.\n0., 0., 0., 0., 1.\n"
    body, _, rep = convert_str(
        "*Material, name=TURNED\n" + elastic + "*Expansion, type=ANISO\n"
        "1e-5, 2e-5, 4e-5, -8.6602540378e-6, 3.D-6, 1.e-6, 20.\n"
        "1.1e-5, 2.2e-5, 4.4e-5, -1e-5,, 2e-6, 120.\n"
        "*Material, name=ZERO\n" + elastic + ANISO_EXPANSION +
        "*Material, name=ORTHO\n" + elastic + "*Expansion, type=ORTHO\n1e-5, 2e-5, 4e-5, 20.\n"
        "*Material, name=FIELD\n" + elastic + "*Expansion, type=ANISO, dependencies=1\n"
        "1e-5, 2e-5, 4e-5, 2e-6, 0., 0., 0., 0.\n9e-5, 9e-5, 9e-5, 8e-6, 0., 0., 0., 1.\n"
        "*Material, name=DIST\n" + elastic + "*Expansion, type=ANISO\nEXPDIST\n"
        "*Material, name=USERX\n" + elastic + "*Expansion, type=ANISO, user\n1., 2., 3., 4., 5.\n"
        "*Material, name=TIGHT\n" + elastic + "*Expansion, type=ANISO\n1e-3,2e-3,4e-3,0.,0.,0.\n")
    assert expansion_card(body, "TURNED") == ("*EXPANSION, TYPE=ANISO", [
        "1e-5, 2e-5, 4e-5, -4.3301270189e-06, 1.5e-06, 5e-07, 20.",
        "1.1e-5, 2.2e-5, 4.4e-5, -5e-06, , 1e-06, 120."])
    assert expansion_card(body, "ZERO") == ("*EXPANSION, TYPE=ORTHO", ["1e-3, 2e-3, 4e-3"])
    assert expansion_card(body, "TIGHT") == ("*EXPANSION, TYPE=ORTHO", ["1e-3, 2e-3, 4e-3"])
    assert expansion_card(body, "ORTHO")[1] == ["1e-5, 2e-5, 4e-5, 20."]
    # DEPENDENCIES: collapsed to the field-free row first, then halved
    assert expansion_card(body, "FIELD") == ("*EXPANSION, TYPE=ANISO",
                                             ["1e-5, 2e-5, 4e-5, 1e-06, 0., 0., 0."])
    assert expansion_card(body, "DIST")[1] == ["EXPDIST"]          # a distribution name
    assert expansion_card(body, "USERX")[1] == ["1., 2., 3., 4., 5."]  # VUEXPAN properties
    text = rep.text()
    assert "Material TURNED: the shear coefficients alpha12, alpha13, alpha23 of its " \
           "*EXPANSION, TYPE=ANISO halved" in text and "Material FIELD: the shear" in text
    assert not any(f"Material {m}: the shear" in text for m in ("ZERO", "ORTHO", "DIST", "USERX",
                                                                 "TIGHT"))


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


TURNED_30 = "*Orientation, name=T\n0.866025403784, 0.5, 0., -0.5, 0.866025403784, 0.\n"
NLGEOM_STEP = "*Step, nlgeom\n*Static\n"
HEATED = "*Temperature\nALL, 100.\n"
TEMPS_IC = "*Initial Conditions, type=TEMPERATURE\nALL, 0.\n"


def nlgeom_expansion_warnings(expansion, orientation="", section="", step=NLGEOM_STEP,
                              load=HEATED, ic=TEMPS_IC):
    """The NLGEOM thermal-expansion WARNINGs for a heated C3D8 of material M."""
    deck = (HEX + "*Nset, nset=ALL, generate\n1, 8, 1\n" + orientation +
            f"*Solid Section, elset=EALL, material=M{section}\n,\n*Material, name=M\n"
            "*Elastic\n1000., 0.2\n" + expansion + ic + step + load + "*End Step\n")
    _, _, rep = convert_str(deck)
    return [m for m in rep.text().splitlines() if "in a deck with NLGEOM steps" in m]


def test_nlgeom_turned_ortho_expansion_warned():
    # ccx 2.23 drops the shear of a turned orthotropic thermal strain in NLGEOM steps
    # (probed: a free cube turned 30 deg gets no shear strain), whatever the deck's form
    w = nlgeom_expansion_warnings(ORTHO_EXPANSION, TURNED_30, ", orientation=T")
    assert len(w) == 1 and w[0].startswith("[WARNING] Material M: *EXPANSION, TYPE=ORTHO in material "
                                           "axes that an *ORIENTATION")
    for ori, step in (("*Orientation, name=T\n1., 0., 0., 0., 1., 0.\n3, 30.\n", NLGEOM_STEP),
                      (TURNED_30, "*Step, nlgeom=YES\n*Static\n"),
                      (TURNED_30, "*Step\n*Dynamic, Explicit\n, 1.\n"),   # NLGEOM added there
                      (TURNED_30, "*Step\n*Coupled Temperature-displacement, steady state\n1., 1.\n"
                                  "*Step, nlgeom\n*Static\n")):
        assert len(nlgeom_expansion_warnings(ORTHO_EXPANSION, ori, ", orientation=T", step)) == 1
    # ... and not where ccx is right: linear steps, NLGEOM=NO, no orientation, axes the
    # orientation only permutes (also through its rotation line), an isotropic expansion,
    # equal coefficients across the turn, no temperature change, no temperatures
    quiet = [(ORTHO_EXPANSION, TURNED_30, "*Step\n*Static\n", HEATED, TEMPS_IC),
             (ORTHO_EXPANSION, TURNED_30, "*Step, nlgeom=NO\n*Static\n", HEATED, TEMPS_IC),
             (ORTHO_EXPANSION, TURNED_30, "*Step, nlgeom=NO\n*Dynamic, Explicit\n, 1.\n", HEATED,
              TEMPS_IC),
             (ORTHO_EXPANSION, "", NLGEOM_STEP, HEATED, TEMPS_IC),
             (ORTHO_EXPANSION, "*Orientation, name=T\n1., 0., 0., 0., 1., 0.\n3, 0.\n", NLGEOM_STEP,
              HEATED, TEMPS_IC),
             (ORTHO_EXPANSION, "*Orientation, name=T\n0., 1., 0., -1., 0., 0.\n", NLGEOM_STEP,
              HEATED, TEMPS_IC),
             (ORTHO_EXPANSION, "*Orientation, name=T\n1., 0., 0., 0., 1., 0.\n1, 90.\n", NLGEOM_STEP,
              HEATED, TEMPS_IC),
             ("*Expansion\n1e-3\n", TURNED_30, NLGEOM_STEP, HEATED, TEMPS_IC),
             ("*Expansion, type=ORTHO\n2e-3, 2e-3, 4e-3\n", TURNED_30, NLGEOM_STEP, HEATED, TEMPS_IC),
             (ORTHO_EXPANSION, TURNED_30, NLGEOM_STEP, "", TEMPS_IC),
             (ORTHO_EXPANSION, TURNED_30, NLGEOM_STEP, "", "")]
    for exp, ori, step, load, ic in quiet:
        assert not nlgeom_expansion_warnings(exp, ori, ", orientation=T" if ori else "", step, load, ic)
    # a temperature row with unequal coefficients is enough; a cylindrical system turns
    assert nlgeom_expansion_warnings("*Expansion, type=ORTHO\n2e-3, 2e-3, 4e-3, 0.\n1e-3, 2e-3, 4e-3, "
                                     "100.\n", TURNED_30, ", orientation=T")
    assert nlgeom_expansion_warnings(ORTHO_EXPANSION, "*Orientation, name=T, system=CYLINDRICAL\n"
                                     "0., 0., 0., 0., 0., 1.\n", ", orientation=T")


def test_nlgeom_aniso_expansion_warned():
    # an anisotropic expansion stops ccx 2.23's NLGEOM steps ('too many cutbacks', probed)
    # once the deck has temperatures, turned or not, even where the temperature stays
    w = nlgeom_expansion_warnings(SHEARED_EXPANSION, load="")
    assert len(w) == 1 and w[0].startswith("[WARNING] Material M: *EXPANSION, TYPE=ANISO in a deck")
    assert nlgeom_expansion_warnings(SHEARED_EXPANSION, TURNED_30, ", orientation=T")
    assert not nlgeom_expansion_warnings(SHEARED_EXPANSION, step="*Step\n*Static\n")
    assert not nlgeom_expansion_warnings(SHEARED_EXPANSION, load="", ic="")
    # one without shear coefficients goes out as ORTHO, unless its axes are turned
    assert not nlgeom_expansion_warnings(ANISO_EXPANSION, load="")
    assert nlgeom_expansion_warnings(ANISO_EXPANSION, TURNED_30, ", orientation=T")
    # a material no section uses is not computed at all
    _, _, rep = convert_str(HEX + "*Nset, nset=ALL, generate\n1, 8, 1\n*Solid Section, elset=EALL, "
                            "material=M\n,\n*Material, name=M\n*Elastic\n1000., 0.2\n*Material, "
                            "name=SPARE\n*Elastic\n1000., 0.2\n" + SHEARED_EXPANSION + TEMPS_IC +
                            NLGEOM_STEP + HEATED + "*End Step\n")
    assert "NLGEOM" not in rep.text()


def test_nlgeom_expansion_composite_plies():
    # composite plies: the ply angle turns the section's orientation about its local 3
    def warned(plies, orientation=""):
        deck = ("*Node, nset=ALL\n1, 0., 0., 0.\n2, 1., 0., 0.\n3, 1., 1., 0.\n4, 0., 1., 0.\n"
                "5, .5, 0., 0.\n6, 1., .5, 0.\n7, .5, 1., 0.\n8, 0., .5, 0.\n"
                "*Element, type=S8R, elset=P\n1, 1, 2, 3, 4, 5, 6, 7, 8\n" + TURNED_30 +
                f"*Shell Section, elset=P, composite{orientation}\n" + plies +
                "*Material, name=PLY\n*Elastic, type=LAMINA\n10000., 1000., 0.3, 500., 500., 400.\n"
                + ORTHO_EXPANSION + TEMPS_IC + NLGEOM_STEP + HEATED + "*End Step\n")
        _, _, rep = convert_str(deck)
        return "Material PLY: *EXPANSION, TYPE=ORTHO" in rep.text()

    assert warned("0.1, 3, PLY, 0.\n0.1, 3, PLY, 45.\n")
    assert warned("0.1, 3, PLY, T\n")                                 # the ply names T
    assert warned("0.1, 3, PLY, 0.\n0.1, 3, PLY,\n", ", orientation=T")
    assert not warned("0.1, 3, PLY, 0.\n0.1, 3, PLY, 90.\n0.1, 3, PLY, -90.\n")
    assert not warned("0.1, 3, PLY, -30.\n", ", orientation=T")       # back to the global axes


def heated_cube(expansion, orientation="", section=""):
    """A heated C3D8 of material M (isotropic *ELASTIC) in an NLGEOM step: (body, report)."""
    body, _, rep = convert_str(HEX + "*Nset, nset=ALL, generate\n1, 8, 1\n" + orientation +
                               f"*Solid Section, elset=EALL, material=M{section}\n,\n*Material, "
                               "name=M\n*Elastic\n1000., 0.2\n" + expansion + TEMPS_IC +
                               NLGEOM_STEP + HEATED + "*End Step\n")
    return body, rep


AS_ORTHO_NOTE = "*EXPANSION, TYPE=ANISO without shear coefficients written as TYPE=ORTHO"


def test_aniso_expansion_without_shear_written_as_ortho():
    # ccx 2.23 stops NLGEOM steps on any TYPE=ANISO expansion once the deck has temperatures
    # (probed), but computes TYPE=ORTHO right in axes no orientation turns: an anisotropic
    # expansion without shear coefficients goes out as ORTHO (the same thermal strain), and
    # an isotropic *ELASTIC beside it as engineering constants rather than ANISO
    body, rep = heated_cube(ANISO_EXPANSION)
    assert expansion_card(body, "M") == ("*EXPANSION, TYPE=ORTHO", ["1e-3, 2e-3, 4e-3"])
    assert elastic_card(body, "M")[0] == "*ELASTIC, TYPE=ENGINEERING CONSTANTS"
    assert rep.text().count(AS_ORTHO_NOTE) == 1 and f"Material M: {AS_ORTHO_NOTE}" in rep.text()
    assert "in a deck with NLGEOM steps" not in rep.text()
    # the long type name, blank or negative-zero shears, other parameters, engineering
    # constants (left as they are beside ORTHO), materials no section uses
    body, _, rep = convert_str(
        "*Material, name=A\n*Elastic\n1000., 0.2\n*Expansion, type=ANISOTROPIC, zero=20.\n"
        "1e-3,2e-3,4e-3\n*Material, name=B\n*Elastic, type=ENGINEERING CONSTANTS\n"
        "1000., 2000., 3000., 0.2, 0.25, 0.3, 400., 500.\n600.\n*Expansion, type=ANISO\n"
        "1e-3, 2e-3, 4e-3, -0., , 0.D0\n")
    assert expansion_card(body, "A") == ("*EXPANSION, TYPE=ORTHO, ZERO=20.", ["1e-3, 2e-3, 4e-3"])
    assert expansion_card(body, "B") == ("*EXPANSION, TYPE=ORTHO", ["1e-3, 2e-3, 4e-3"])
    assert elastic_card(body, "B") == ("*ELASTIC, TYPE=ENGINEERING CONSTANTS",
                                       ["1000., 2000., 3000., 0.2, 0.25, 0.3, 400., 500.", "600."])
    assert "Material A: " + AS_ORTHO_NOTE in rep.text() and "Material B: " + AS_ORTHO_NOTE in rep.text()
    # axes that are not turned so that the expansion has shear: the identity orientation
    # Abaqus/CAE writes, a permutation, a turn about the axis of two equal coefficients
    for exp, ori in ((ANISO_EXPANSION, "*Orientation, name=T\n1., 0., 0., 0., 1., 0.\n3, 0.\n"),
                     (ANISO_EXPANSION, "*Orientation, name=T\n0., 1., 0., -1., 0., 0.\n"),
                     ("*Expansion, type=ANISO\n2e-3, 2e-3, 4e-3, 0., 0., 0.\n", TURNED_30)):
        body, rep = heated_cube(exp, ori, ", orientation=T")
        assert expansion_card(body, "M")[0] == "*EXPANSION, TYPE=ORTHO"
        assert "in a deck with NLGEOM steps" not in rep.text()


def test_aniso_expansion_kept_when_turned():
    # turned axes: as TYPE=ORTHO ccx 2.23 would drop the turned shear in NLGEOM steps without
    # an error, so the card stays ANISO (beside an ANISO *ELASTIC) and is warned
    for ori, section in ((TURNED_30, ", orientation=T"),
                         ("*Orientation, name=T\n1., 0., 0., 0., 1., 0.\n3, 30.\n", ", orientation=T"),
                         ("*Orientation, name=T, system=CYLINDRICAL\n0., 0., 0., 0., 0., 1.\n",
                          ", orientation=T")):
        body, rep = heated_cube(ANISO_EXPANSION, ori, section)
        assert expansion_card(body, "M") == ("*EXPANSION, TYPE=ANISO", ["1e-3, 2e-3, 4e-3, 0., 0., 0."])
        assert elastic_card(body, "M")[0] == "*ELASTIC, TYPE=ANISO"
        assert AS_ORTHO_NOTE not in rep.text()
        w = [m for m in rep.text().splitlines() if "in a deck with NLGEOM steps" in m]
        assert len(w) == 1 and "Material M: *EXPANSION, TYPE=ANISO" in w[0]
    # ... also when only one of the material's sections, or one composite ply, turns it
    deck = (HEX + "*Element, type=C3D8, elset=E2\n2, 1, 2, 3, 4, 5, 6, 7, 8\n" + TURNED_30 +
            "*Solid Section, elset=EALL, material=M\n,\n*Solid Section, elset=E2, material=M, "
            "orientation=T\n,\n*Material, name=M\n*Elastic\n1000., 0.2\n" + ANISO_EXPANSION)
    assert expansion_card(convert_str(deck)[0], "M")[0] == "*EXPANSION, TYPE=ANISO"

    def ply_card(plies):
        deck = ("*Node, nset=ALL\n1, 0., 0., 0.\n2, 1., 0., 0.\n3, 1., 1., 0.\n4, 0., 1., 0.\n"
                "5, .5, 0., 0.\n6, 1., .5, 0.\n7, .5, 1., 0.\n8, 0., .5, 0.\n"
                "*Element, type=S8R, elset=P\n1, 1, 2, 3, 4, 5, 6, 7, 8\n" + TURNED_30 +
                "*Shell Section, elset=P, composite\n" + plies + "*Material, name=PLY\n"
                "*Elastic, type=LAMINA\n10000., 1000., 0.3, 500., 500., 400.\n" + ANISO_EXPANSION)
        return expansion_card(convert_str(deck)[0], "PLY")[0]

    assert ply_card("0.1, 3, PLY, 0.\n0.1, 3, PLY, 45.\n") == "*EXPANSION, TYPE=ANISO"
    assert ply_card("0.1, 3, PLY, T\n") == "*EXPANSION, TYPE=ANISO"     # the ply names T
    assert ply_card("0.1, 3, PLY, 0.\n0.1, 3, PLY, 90.\n") == "*EXPANSION, TYPE=ORTHO"


def test_aniso_expansion_with_shear_kept():
    # a shear coefficient in any row, data that are no coefficients, or USER: left as ANISO
    for exp in (SHEARED_EXPANSION,
                "*Expansion, type=ANISO\n1e-3, 2e-3, 4e-3, 0., 0., 0., 20.\n"
                "1e-3, 2e-3, 4e-3, 0., 0., 1e-6, 120.\n",
                "*Expansion, type=ANISO\nEXPDIST\n",
                "*Expansion, type=ANISO\n1e-3, 2e-3, 4e-3, 0., 0., 0., nan\n",
                "*Expansion, type=ANISO, user\n1., 2., 3.\n"):
        body, rep = heated_cube(exp)
        assert expansion_card(body, "M")[0].startswith("*EXPANSION, TYPE=ANISO")
        assert elastic_card(body, "M")[0] == "*ELASTIC, TYPE=ANISO"
        assert AS_ORTHO_NOTE not in rep.text()


def test_aniso_expansion_as_ortho_rows_and_dependencies():
    # temperature rows keep their temperatures; blank shear fields count as zero
    body, _, _ = convert_str("*Material, name=M\n*Elastic\n1000., 0.2\n*Expansion, type=ANISO\n"
                             "1e-3, 2e-3, 4e-3, 0., 0., 0., 20.\n1.5e-3, 2.5e-3, 4.5e-3, , , , 120.\n")
    assert expansion_card(body, "M")[1] == ["1e-3, 2e-3, 4e-3, 20.", "1.5e-3, 2.5e-3, 4.5e-3, 120."]
    # DEPENDENCIES: the field columns after the temperature are no shear coefficients; the
    # rows are collapsed to field = 0 first (two lines a row from two field variables on)
    body, _, rep = convert_str(
        "*Material, name=ONE\n*Elastic\n1000., 0.2\n*Expansion, type=ANISO, dependencies=1\n"
        "1e-3, 2e-3, 4e-3, 0., 0., 0., 20., 0.\n9e-3, 9e-3, 9e-3, 0., 0., 0., 20., 1.\n"
        "1.5e-3, 2.5e-3, 4.5e-3, 0., 0., 0., 120., 0.\n9e-3, 9e-3, 9e-3, 0., 0., 0., 120., 1.\n"
        "*Material, name=TWO\n*Elastic\n1000., 0.2\n*Expansion, type=ANISO, dependencies=2\n"
        "1e-3, 2e-3, 4e-3, 0., 0., 0., 20., 0.\n0.\n9e-3, 9e-3, 9e-3, 0., 0., 0., 20., 1.\n2.\n"
        "*Material, name=SHEAR\n*Elastic\n1000., 0.2\n*Expansion, type=ANISO, dependencies=2\n"
        "1e-3, 2e-3, 4e-3, 0., 0., 0., 20., 0.\n0.\n9e-3, 9e-3, 9e-3, 1e-6, 0., 0., 20., 1.\n2.\n")
    assert expansion_card(body, "ONE") == ("*EXPANSION, TYPE=ORTHO",
                                           ["1e-3, 2e-3, 4e-3, 20.", "1.5e-3, 2.5e-3, 4.5e-3, 120."])
    assert expansion_card(body, "TWO") == ("*EXPANSION, TYPE=ORTHO", ["1e-3, 2e-3, 4e-3, 20."])
    assert expansion_card(body, "SHEAR")[0] == "*EXPANSION, TYPE=ANISO"     # in any field state
    assert "*EXPANSION, DEPENDENCIES=1: ccx has no field-variable dependence" in rep.text()


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


CIRC_EXPLICIT = """*Node
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
*Density
7.85e-9
*Boundary
1, 1, 3
3, 2, 3
"""


def explicit_step(data, params=""):
    return f"*Step\n*Dynamic, Explicit{params}\n{data}\n*Cload\n2, 2, -1.\n*End Step\n"


def test_circ_beam_explicit_increment_capped():
    # ccx 2.23 sizes a circular-section beam's explicit increment as if the section were the
    # box around the circle, about 1.3x its stable limit (NaN displacements); the step's
    # maximum increment becomes ccx's Courant estimate with the square through the section's
    # corner nodes: 0.177 min(l, d / sqrt(2)) / c, here d = 0.1 and c = 6.001e6
    body, conv, rep = convert_str(CIRC_EXPLICIT + explicit_step(", 0.001"))
    assert "*DYNAMIC, EXPLICIT\n, 0.001, , 2.09e-09\n" in body
    assert "maximum increment 2.09e-09 set" in rep.text() and conv._circ_explicit[1] == 1
    # a larger maximum is lowered, a smaller one kept; a period below the cap needs none
    body, _, _ = convert_str(CIRC_EXPLICIT + explicit_step(", 0.001, , 1e-6"))
    assert "\n, 0.001, , 2.09e-09\n" in body
    body, _, rep = convert_str(CIRC_EXPLICIT + explicit_step(", 0.001, , 1e-9"))
    assert "\n, 0.001, , 1e-9\n" in body and "maximum increment" not in rep.text()
    body, _, rep = convert_str(CIRC_EXPLICIT + explicit_step(", 1e-9"))
    assert "\n, 1e-9\n" in body and "maximum increment" not in rep.text()
    # an element shorter than d / sqrt(2) sets it by its length (ccx's own estimate there)
    short = CIRC_EXPLICIT.replace("3, 2., 0., 0.", "3, 1.05, 0., 0.")
    body, conv, _ = convert_str(short + explicit_step(", 0.001"))
    assert "\n, 0.001, , 1.47e-09\n" in body and conv._circ_explicit[1] == 2


def test_circ_beam_explicit_increment_left_alone_or_warned():
    # implicit dynamics and other sections keep their data line
    body, conv, _ = convert_str(CIRC_EXPLICIT + "*Step\n*Dynamic\n1e-4, 0.001\n*End Step\n")
    assert "*DYNAMIC\n1e-4, 0.001\n" in body and conv._circ_explicit is None
    rect = CIRC_EXPLICIT.replace("section=CIRC\n0.05", "section=RECT\n0.1, 0.1")
    body, _, rep = convert_str(rect + explicit_step(", 0.001"))
    assert "*DYNAMIC, EXPLICIT\n, 0.001\n" in body and "maximum increment" not in rep.text()
    # a fixed increment (DIRECT USER CONTROL -> DIRECT) above the cap is only warned: ccx's
    # mass scaling for it is sized from the same overestimate
    direct = ", direct user control"
    body, _, rep = convert_str(CIRC_EXPLICIT + explicit_step("1e-8, 0.001", direct))
    assert "*DYNAMIC, EXPLICIT, DIRECT\n1e-8, 0.001\n" in body
    assert "the fixed increment 1e-8 exceeds" in rep.text()
    _, _, rep = convert_str(CIRC_EXPLICIT + explicit_step("1e-9, 0.001", direct))
    assert "fixed increment" not in rep.text()
    # no density (nor any wave speed): no cap, a warning with the rule of thumb
    body, _, rep = convert_str(CIRC_EXPLICIT.replace("*Density\n7.85e-9\n", "")
                               + explicit_step(", 0.001"))
    assert "*DYNAMIC, EXPLICIT\n, 0.001\n" in body and "0.12 d / c" in rep.text()
    assert "could not size a cap for ELSET=BEAM (material M has no isotropic" in rep.text()


def test_beam_circ_explicit_example():
    # the deck validate_with_ccx.py checks against beam theory: 6 elements 40 long, d = 20,
    # steel, so the cap is 0.177 * 20 / sqrt(2) / 6.001e6 (ccx alone would pick 8.3e-7)
    body, _, _ = convert(os.path.join(EXAMPLES, "beam_circ_explicit.inp"))
    g = reparse(body)
    assert "*DYNAMIC, EXPLICIT\n, 6.e-3, , 4.17e-07\n" in body
    assert {t for t, _ in g.elements.values()} == {"B32"} and not dangling_refs(g)


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
# two B31 beams whose ends 2 and 3 meet at x = 1
B2 = ("*Node\n1,0,0,0\n2,1,0,0\n3,1,0,0\n4,2,0,0\n*Element,type=B31,elset=B\n1,1,2\n2,3,4\n"
      "*Beam Section,elset=B,material=M,section=RECT\n1.,1.\n0.,0.,1.\n*Material,name=M\n"
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
    # a DOF list without rotations ties none; a rotation under a *BOUNDARY keeps the BC (ccx
    # cannot have both), warned unless the reference node's own BC imposes it
    body, _, _ = convert_str(deck + "2, 2\n")
    assert "B31" in body and not _equations(body)
    body, _, rep = convert_str(deck + "*Boundary\n5, 4, 4\n")
    assert "5,4,1.,100,4,-1." not in _equations(body) and "5,5,1.,100,5,-1." in _equations(body)
    assert "keeps the BC and is not tied" in rep.text() and "--approximate" in rep.text()
    body, _, rep = convert_str(deck + "*Boundary\n5, 4, 4\n100, 4, 4\n")
    assert "5,4,1.,100,4,-1." not in _equations(body) and "Possible overconstraint" not in rep.text()
    assert "5, 4, 4" in body                                  # the BC governs it (exact)
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


def _bc_lines(body):
    """The *BOUNDARY data lines of a converted deck, blanks removed."""
    out, inside = [], False
    for l in _live(body):
        if l.startswith("*"):
            inside = l.upper().startswith("*BOUNDARY")
        elif inside:
            out.append(l.replace(" ", ""))
    return out


def test_coupled_member_bc_implied_by_reference_dropped():
    # ccx makes the coupled DOFs of rigid-coupling members dependent and stops on one that also
    # has a *BOUNDARY ('*ERROR in cascade ... dependent side of a MPC and a SPC'); where the
    # reference node's own BCs impose it anyway (that DOF, and no rotation about the other two
    # axes), the BC is taken off — a line keeping some nodes moves onto a set of them
    deck = (HEX + "*Node\n100,0.5,0.5,2.\n*Nset,nset=TOP\n5,6,7,8\n*Nset,nset=SIDE\n1,2,5,6\n"
            "*Rigid Body, ref node=100, tie nset=TOP\n")
    body, conv, rep = convert_str(deck + "*Boundary\n100, 1, 6\nTOP, 1, 3\nSIDE, 2, 2\n")
    rot = conv._rb_rot[100]
    assert _bc_lines(body) == ["100,1,3", f"{rot},1,3", "ABQ2CCX_BC1,2,2"]
    assert reparse(body).nsets["ABQ2CCX_BC1"] == [1, 2] and "Exact." in rep.text()
    assert "overconstraint" not in rep.text()
    # the same through a kinematic coupling whose reference may only slide in x-y and turn
    # about z: the members' z is imposed (NLGEOM too: a rotation about z leaves z alone), their
    # x and y are not — those BCs stay, warned
    kin = (HEX + "*Node\n100,0.5,0.5,2.\n*Nset,nset=TOP\n5,6,7,8\n*Surface, type=node, name=ST\n"
           "TOP\n*Coupling, constraint name=C, ref node=100, surface=ST\n*Kinematic\n")
    body, _, rep = convert_str(kin + "*Boundary\n100, 3, 5\nTOP, 1, 3\n")
    assert _bc_lines(body) == ["100,3,5", "TOP,1,2"]
    assert "node 5 DOF 1 follows reference node 100 through a kinematic coupling" in rep.text()
    assert "(8 such DOF(s) on 4 node(s))" in rep.text() and "Exact." in rep.text()
    # not imposed: a rotation about another axis is free, the values differ, or the reference's
    # rotation is only held from the second step on (the body may have turned in the first)
    for bcs in ("100, 1, 2\n100, 4, 4\nTOP, 1, 1\n",         # rotations about y and z free
                "100, 1, 6\nTOP, 1, 1, 0.1\n"):               # u1 = 0 vs 0.1
        body, _, rep = convert_str(kin + "*Boundary\n" + bcs)
        assert "TOP,1,1" in "".join(_bc_lines(body)) and "Possible overconstraint" in rep.text()
    body, _, rep = convert_str(kin + "*Boundary\nTOP, 1, 1\n100, 1, 3\n*Step\n*Static\n*End Step\n"
                               "*Step\n*Static\n*Boundary\n100, 4, 6\n*End Step\n")
    assert "TOP,1,1" in _bc_lines(body) and "Possible overconstraint" in rep.text()
    body, _, rep = convert_str(kin + "*Boundary\nTOP, 1, 1\n100, 1, 6\n*Step\n*Static\n*End Step\n"
                               "*Step\n*Static\n*Boundary, op=NEW\n100, 1, 6\n*End Step\n")
    assert "TOP,1,1" not in _bc_lines(body) and "overconstraint" not in rep.text()
    # a zero velocity holds the reference still once it does so from the first step
    body, _, rep = convert_str(kin + "*Boundary\nTOP, 1, 1\n*Step\n*Static\n*Boundary, type=velocity\n"
                               "100, 1, 1\n100, 4, 6\n100, 3, 3, -1.\n*End Step\n")
    assert "TOP,1,1" not in _bc_lines(body) and "Exact." in rep.text()
    body, _, rep = convert_str(kin + "*Boundary\nTOP, 1, 1\n*Step\n*Static\n*Boundary, type=velocity\n"
                               "100, 1, 1, 0.5\n100, 4, 6\n*End Step\n")
    assert "TOP,1,1" in _bc_lines(body) and "Possible overconstraint" in rep.text()


def test_coupled_member_bc_conflicts_and_approximate():
    # a member BC the reference node's BCs do not impose stops ccx; Abaqus/Standard ignores it
    # (a kinematic coupling eliminates the coupled DOFs at its nodes), so --approximate drops
    # it there; on a *RIGID BODY, Abaqus moves identical member BCs to the reference node
    # (test_rigid_body_member_bc_moved_to_reference), and BCs that differ between the body's
    # nodes stop Abaqus too: those stay a warning, --approximate or not
    kin = (HEX + "*Node\n100,0.5,0.5,2.\n*Nset,nset=TOP\n5,6,7,8\n*Surface, type=node, name=ST\n"
           "TOP\n*Coupling, constraint name=C, ref node=100, surface=ST\n*Kinematic\n"
           "*Boundary\nTOP, ENCASTRE\n")
    body, _, rep = convert_str(kin)
    assert _bc_lines(body) == ["TOP,1,3"] and "rerun with --approximate" in rep.text()
    body, _, rep = convert_str(kin, approximate=True)
    assert _bc_lines(body) == [] and "[APPROX] *BOUNDARY taken off 12 DOF(s) of 4 node(s)" in rep.text()
    rb = kin.replace("*Surface, type=node, name=ST\nTOP\n*Coupling, constraint name=C, ref node=100, "
                     "surface=ST\n*Kinematic\n", "*Rigid Body, ref node=100, tie nset=TOP\n"
                     "*Nset, nset=HALF\n5, 6\n").replace("TOP, ENCASTRE", "TOP, 1, 1\nHALF, 1, 1, 0.1")
    for approximate in (False, True):
        body, _, rep = convert_str(rb, approximate=approximate)
        assert _bc_lines(body) == ["TOP,1,1", "HALF,1,1,0.1"] and "[APPROX]" not in rep.text()
        assert "through a *RIGID BODY" in rep.text() and "stops with an error too" in rep.text()


def test_coupled_member_bc_shell_and_planar():
    # the dheller1_uprofile pattern: a coupled shell edge whose reference node is one of its
    # own nodes (-> *RIGID BODY), every edge node held in x, z and all rotations: the members'
    # x and z go, their rotations stay (imposed, so left untied)
    deck = (S4 + "*Nset, nset=EDGE\n2, 3, 5, 6\n*Surface, type=node, name=SE\nEDGE\n"
            "*Coupling, constraint name=C, ref node=2, surface=SE\n*Kinematic\n"
            "*Boundary\nEDGE, 1, 1\nEDGE, 3, 6\n*Step\n*Static\n*Cload\n2, 2, -1.\n*End Step\n")
    body, _, rep = convert_str(deck)
    assert "*RIGID BODY, NSET=ABQ2CCX_RB1, REF NODE=2" in body
    assert _bc_lines(body) == ["2,1,1", "2,3,3", "EDGE,4,6"]
    assert len(_equations(body)) == 3            # only the ROT NODE follows node 2's rotations
    assert "overconstraint" not in rep.text()
    # 2-D: the in-plane rotation is the only one; DOF 3 does not exist there (ccx's 2-D rigid
    # body makes it dependent all the same)
    q = ("*Node\n1,0,0\n2,1,0\n3,1,1\n4,0,1\n5,2,0\n6,2,1\n100,3,0.5\n*Element,type=CPE4,elset=E\n"
         "1,1,2,3,4\n2,2,5,6,3\n*Nset,nset=R\n5,6\n*Solid Section,elset=E,material=M\n1.,\n"
         "*Material,name=M\n*Elastic\n1000.,0.3\n*Rigid Body, ref node=100, tie nset=R\n")
    body, _, rep = convert_str(q + "*Boundary\n100, 1, 1\n100, 6, 6\nR, 1, 1\nR, 3, 3\n")
    assert [l for l in _bc_lines(body) if l.startswith("R,")] == [] and "DOF 3 of 2-D nodes" in rep.text()
    # the reference node's rotation free: R's u1 at two heights holds it, so the BC moves to
    # the reference node as Abaqus moves it — the rotation held at zero, on the ROT NODE
    body, conv, rep = convert_str(q + "*Boundary\n100, 1, 1\nR, 1, 1\n")
    assert _bc_lines(body) == ["100,1,1", f"{conv._rb_rot[100]},3,3"] and "Exact." in rep.text()
    assert "overconstraint" not in rep.text()


RB_TOP = HEX + "*Node\n100,0.5,0.5,2.\n*Nset,nset=TOP\n5,6,7,8\n*Rigid Body, ref node=100, tie nset=TOP\n"


def _bc_cards(body):
    """(header, data lines) of each *BOUNDARY card of a converted deck, blanks removed."""
    out = []
    for l in _live(body):
        if l.startswith("*"):
            if l.upper().startswith("*BOUNDARY"):
                out.append((l, []))
            elif out and out[-1] is not None:
                out.append(None)
        elif out and out[-1] is not None:
            out[-1][1].append(l.replace(" ", ""))
    return [c for c in out if c is not None]


def test_rigid_body_member_bc_moved_to_reference():
    # Abaqus/Standard moves identical BCs on a *RIGID BODY's nodes to its reference node, with
    # zero rotations about the other axes ('Overconstraint checks'); where the BC'd nodes hold
    # those anyway it is the same constraint, so it is done by default — in the card that held
    # the BC, which keeps its step, OP, amplitude and type
    body, conv, rep = convert_str(RB_TOP + "*Amplitude, name=A\n0., 0., 1., 1.\n*Step\n*Static\n"
                                  "*Boundary, amplitude=A\nTOP, 3, 3, 0.25\n*End Step\n")
    rot = conv._rb_rot[100]
    assert _bc_cards(body) == [("*BOUNDARY, AMPLITUDE=A", ["100,3,3,0.25", f"{rot},1,2"])]
    assert "*BOUNDARY on 4 DOF(s) of 4 *RIGID BODY node(s) moved" in rep.text() and "Exact." in rep.text()
    assert "overconstraint" not in rep.text()           # the manual's symmetry-face example
    # four face nodes held in all three directions hold the body entirely, although each
    # direction alone leaves the face a tilt; a line naming other nodes too keeps those
    body, _, rep = convert_str(RB_TOP + "*Nset, nset=BOTH\n1, 5, 6, 7, 8\n*Boundary\nBOTH, ENCASTRE\n")
    assert _bc_lines(body) == ["1,1,3", "100,1,3", f"{rot},1,3"] and "overconstraint" not in rep.text()
    body, _, _ = convert_str(RB_TOP + "*Step\n*Static\n*Boundary, type=velocity\nTOP, 3, 3\n*End Step\n")
    assert _bc_lines(body) == ["100,3,3", f"{rot},1,2"]     # a zero velocity: the same, as rates
    # the cold-forging pattern (CAX4): a die's axis nodes keep XSYMM while its reference node is
    # held in step 1 (implied there, dropped) and released in step 2 (moved: the die cannot
    # have turned, being held at the end of step 1)
    q = ("*Node\n1,0,0\n2,1,0\n3,1,1\n4,0,1\n5,0,2\n6,1,2\n100,0,3\n*Element,type=CAX4,elset=E\n"
         "1,1,2,3,4\n*Element,type=CAX4,elset=DIE\n2,4,3,6,5\n*Nset,nset=AXIS\n4,5\n"
         "*Solid Section,elset=E,material=M\n1.,\n*Solid Section,elset=DIE,material=M\n1.,\n"
         "*Material,name=M\n*Elastic\n1000.,0.3\n*Rigid Body, ref node=100, elset=DIE\n*Step\n*Static\n"
         "*Boundary\n1, 2, 2\n2, 2, 2\nAXIS, XSYMM\n100, ENCASTRE\n*End Step\n*Step\n*Static\n"
         "*Boundary, op=NEW\n1, 2, 2\n2, 2, 2\nAXIS, XSYMM\n*Cload\n100, 2, -1.\n*End Step\n")
    body, conv, rep = convert_str(q)
    rot = conv._rb_rot[100]
    assert _bc_cards(body) == [("*BOUNDARY", ["1,2,2", "2,2,2", "100,1,3", f"{rot},1,3"]),
                               ("*BOUNDARY, OP=NEW", ["1,2,2", "2,2,2", "100,1,1", f"{rot},3,3"])]
    assert "Exact." in rep.text() and "overconstraint" not in rep.text()
    # a shell edge held in all six DOFs is one line, but its rotation BCs (on the body's
    # rotation, which the knots' ties make theirs) hold the turn about it; once the BCs are on
    # the reference node, the edge rotations are tied to the body again
    body, conv, rep = convert_str(S4 + "*Rigid Body, ref node=100, tie nset=R\n*Boundary\nR, ENCASTRE\n")
    rot = conv._rb_rot[100]
    assert _bc_lines(body) == ["100,1,3", f"{rot},1,3"] and "overconstraint" not in rep.text()
    assert _equations(body) == [f"{n},{k},1.,{rot},{k - 3},-1." for n in (5, 6) for k in (4, 5, 6)]
    body, _, _ = convert_str(S4 + "*Rigid Body, ref node=100, tie nset=R\n*Boundary\nR, 4, 4, 0.01\n")
    assert _bc_lines(body) == [f"{rot},1,1,0.01"] and len(_equations(body)) == 6


def test_rigid_body_member_bc_move_inexact():
    # where the BC'd nodes do not hold what the moved BCs hold, Abaqus' move holds the body more
    # than the model does: a warning by default, the move itself with --approximate
    for deck, why, moved in (
            # u1 on a flat face normal to z: the face keeps a (first-order) tilt about y
            (RB_TOP + "*Boundary\nTOP, 1, 1\n", "lie on one line seen along the DOF",
             ["100,1,1", "ROT,2,3"]),
            # free in step 1, the body may have turned before its face is fixed in step 2
            (RB_TOP + "*Step\n*Static\n*Cload\n100, 1, 1.\n*End Step\n*Step\n*Static\n*Boundary\n"
             "TOP, ENCASTRE\n*End Step\n", "may have turned before the step", ["100,1,3", "ROT,1,3"]),
            # a zero velocity on the reference node against zero displacements on the face
            (RB_TOP + "*Step\n*Static\n*End Step\n*Step\n*Static\n*Boundary, type=velocity\n"
             "100, 3, 5\n*Boundary\nTOP, 3, 3\n*End Step\n", "own zero velocity meets a zero "
             "displacement", ["100,3,3", "ROT,1,2"])):
        body, _, rep = convert_str(deck)
        assert "Possible overconstraint" in rep.text() and why in rep.text()
        assert "Rerun with --approximate" in rep.text() and "TOP" in "".join(_bc_lines(body))
        body, conv, rep = convert_str(deck, approximate=True)
        assert _bc_lines(body) == [l.replace("ROT", str(conv._rb_rot[100])) for l in moved]
        assert "[APPROX] *BOUNDARY on" in rep.text() and why in rep.text()
    # against the reference node's own BCs (another value on the DOF; a turn, in a later step,
    # that the moved BC would hold at zero) or not comparable (FIXED): nothing moves
    for deck, why in ((RB_TOP + "*Boundary\n100, 1, 1, 0.5\nTOP, 1, 1\n", "disagree with the reference"),
                      (RB_TOP + "*Boundary\nTOP, 3, 3\n*Step\n*Static\n*Boundary\n100, 4, 4, 0.1\n"
                       "*End Step\n", "disagree with the reference"),
                      (RB_TOP + "*Step\n*Static\n*Boundary, fixed\nTOP, 3, 3\n*End Step\n",
                       "does not move a FIXED")):
        for approximate in (False, True):
            body, _, rep = convert_str(deck, approximate=approximate)
            assert why in rep.text() and "[APPROX] *BOUNDARY on" not in rep.text()
            assert any(l.startswith("TOP,") for l in _bc_lines(body))


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


OUT_BEAM = ("*Node\n1, 0., 0., 0.\n7, 60., 0., 0.\n*Ngen, nset=AXIS\n1, 7, 1\n*Nset, nset=TIP\n7\n"
            "*Element, type=B31, elset=BEAM\n1, 1, 2\n*Elgen, elset=BEAM\n1, 6, 1, 1\n"
            "*Beam Section, elset=BEAM, material=M, section=RECT\n1., 2.\n0., 0., -1.\n"
            "*Material, name=M\n*Elastic\n1000., 0.3\n*Boundary\n1, ENCASTRE\n")


def _step(body, k):
    """The text of step ``k`` (1-based) of a converted deck."""
    return body.split("*STEP")[k].split("*END STEP")[0]


def test_history_output_goes_to_print_cards():
    # a ccx .frd keeps one node set per variable: as *NODE FILE, NSET=TOP the history request
    # replaced the field output's whole-model U (probed on 2.23); *OUTPUT, HISTORY for a set
    # is a time series there, which ccx writes to the .dat
    deck = (HEX + "*Nset, nset=TOP\n5, 6, 7, 8\n*Step\n*Static\n*Output, field\n*Node Output\nU, RF\n"
            "*Element Output\nS\n*Output, history\n*Node Output, nset=TOP\nU2\n"
            "*Element Output, elset=EALL\nS11, SDV1\n*End Step\n")
    body, _, rep = convert_str(deck)
    assert ("*NODE FILE\nU, RF\n*EL FILE\nS\n*NODE PRINT, NSET=TOP\nU\n*EL PRINT, ELSET=EALL\n"
            "S, SDV\n") in _step(body, 1)
    assert "*NODE FILE, NSET" not in body and "*OUTPUT, HISTORY" in rep.text()
    # a history set the deck never defines is dropped, not left for ccx to skip with a warning
    body, _, rep = convert_str(HEX + "*Step\n*Static\n*Output, history\n*Node Output, nset=NOPE\nU\n"
                               "*End Step\n")
    assert "NOPE" not in "\n".join(_live(body)) and "not defined" in rep.text()


def test_frd_node_sets_one_per_variable():
    # ccx gives each .frd variable one node set per step (the last card's): a whole-model
    # request keeps it whole, and a variable requested on several sets gets their union
    deck = (HEX + "*Nset, nset=TOP\n5, 6, 7, 8\n*Nset, nset=BOT\n1, 2\n*Step\n*Static\n*Output, field\n"
            "*Node Output\nU\n*Node Output, nset=TOP\nU, RF\n*End Step\n*Step\n*Static\n"
            "*Output, field\n*Node Output, nset=TOP\nU\n*Node Output, nset=BOT\nU, RF\n*End Step\n")
    body, conv, rep = convert_str(deck)
    assert "*NODE FILE\nU\n*NODE FILE, NSET=TOP\nRF\n" in _step(body, 1)
    assert "*NODE FILE, NSET=ABQ2CCX_OUTPUT\nU\n*NODE FILE, NSET=BOT\nRF\n" in _step(body, 2)
    assert sorted(conv.geom.nsets["ABQ2CCX_OUTPUT"]) == [1, 2, 5, 6, 7, 8]
    assert "*NSET, NSET=ABQ2CCX_OUTPUT" in body and "union" in rep.text()


def test_frd_set_at_reference_node_printed():
    # a node of no element is in no ccx .frd, not even under a whole-model request: its
    # field output goes to the .dat
    deck = (HEX + "*Node\n100, 0.5, 0.5, 2.\n*Nset, nset=RP\n100\n*Nset, nset=TOP\n5, 6, 7, 8\n"
            "*Rigid Body, ref node=RP, tie nset=TOP\n*Step\n*Static\n*Output, field\n*Node Output\nU\n"
            "*Node Output, nset=RP\nU, RF\n*End Step\n")
    body, _, rep = convert_str(deck)
    assert "*NODE FILE\nU\n*NODE PRINT, NSET=RP\nRF, U\n" in _step(body, 1)
    assert "never writes a node of no element" in rep.text()


def test_beam_node_set_output_2d_or_printed():
    # ccx writes a beam model to the .frd expanded to 3-D, without the beam nodes: with only
    # U / V / RF in the .frd -> OUTPUT=2D (first step only; exact for those), with element
    # output too (which OUTPUT=2D would average through the section) -> the .dat
    body, _, rep = convert_str(OUT_BEAM + "*Step\n*Static\n*Cload\nTIP, 2, -1.\n*Output, field\n"
                               "*Node Output, nset=TIP\nU, RF\n*End Step\n*Step\n*Static\n"
                               "*Output, field\n*Node Output, nset=TIP\nU\n*End Step\n")
    assert "*NODE FILE, NSET=TIP, OUTPUT=2D\nU, RF\n" in _step(body, 1)
    assert "OUTPUT=2D" not in _step(body, 2) and "*NODE FILE, NSET=TIP\nU\n" in _step(body, 2)
    assert "OUTPUT=2D added" in rep.text()
    body, _, rep = convert_str(OUT_BEAM + "*Step\n*Static\n*Cload\nTIP, 2, -1.\n*Output, field\n"
                               "*Node Output, nset=TIP\nU\n*Element Output\nS\n*End Step\n")
    s = _step(body, 1)
    assert "OUTPUT=2D" not in body and "*NODE PRINT, NSET=TIP\nU\n" in s and "*NODE FILE" not in s


def test_output_frequency_carried_to_the_step():
    # ccx has one output frequency for all output cards of a step and keeps it for later
    # steps: the .frd requests' wins, and step 2 gets its own back (every increment)
    deck = (HEX + "*Nset, nset=TOP\n5, 6, 7, 8\n*Step, nlgeom\n*Static\n0.1, 1.\n"
            "*Output, field, frequency=10\n*Node Output\nU\n*Output, history, frequency=1\n"
            "*Node Output, nset=TOP\nU\n*End Step\n*Step, nlgeom\n*Static\n0.1, 1.\n*Output, field\n"
            "*Node Output\nU\n*End Step\n")
    body, _, rep = convert_str(deck)
    assert "*NODE FILE, FREQUENCY=10\nU\n*NODE PRINT, NSET=TOP\nU\n" in _step(body, 1)
    assert "*NODE FILE, FREQUENCY=1\nU\n" in _step(body, 2)
    assert "at one frequency" in rep.text()
    # FREQUENCY=0 on *OUTPUT: Abaqus writes none of its requests
    body, _, _ = convert_str(HEX + "*Step\n*Static\n*Output, field, frequency=0\n*Node Output\nU\n"
                             "*End Step\n")
    assert "*NODE FILE" not in body


def test_output_intervals_to_time_points_or_frequency():
    # NUMBER INTERVAL / TIME INTERVAL -> *TIME POINTS (before the first *STEP, as ccx needs)
    # where ccx picks the increments; FREQUENCY from the fixed increment under DIRECT, where
    # ccx stops on TIME POINTS
    deck = (HEX + "*Step, nlgeom\n*Static\n0.1, 2.\n*Output, field, number interval=4\n*Node Output\nU\n"
            "*End Step\n*Step, nlgeom\n*Static, direct\n0.05, 1.\n*Output, field, time interval=0.2\n"
            "*Node Output\nU\n*End Step\n")
    body, _, _ = convert_str(deck)
    assert "*TIME POINTS, NAME=ABQ2CCX_TP1, GENERATE\n0.5, 2., 0.5\n*STEP" in body
    assert "*NODE FILE, TIME POINTS=ABQ2CCX_TP1\nU\n" in _step(body, 1)
    assert "*NODE FILE, FREQUENCY=4\nU\n" in _step(body, 2)
    # the deck's own *TIME POINTS are used by name
    body, _, _ = convert_str(HEX + "*Time Points, name=TP\n0.5, 1.\n*Step, nlgeom\n*Static\n0.1, 1.\n"
                             "*Output, field, time points=TP\n*Node Output\nU\n*End Step\n")
    assert "*NODE FILE, TIME POINTS=TP\nU\n" in body and "ABQ2CCX_TP" not in body


def test_dynamic_output_defaults_and_explicit_intervals():
    # Abaqus writes *DYNAMIC (implicit) output every 10 increments by default; *MODAL DYNAMIC
    # and explicit dynamics take no TIME POINTS in ccx: FREQUENCY from the fixed or the
    # maximum increment, else a warning
    body, _, rep = convert_str(HEX + "*Step\n*Dynamic\n0.01, 1.\n*Output, field\n*Node Output\nU\n"
                               "*End Step\n*Step\n*Frequency\n5\n*End Step\n*Step\n*Modal Dynamic\n"
                               "0.001, 0.1\n*Output, field, number interval=5\n*Node Output\nU\n*End Step\n")
    assert "*NODE FILE, FREQUENCY=10\nU\n" in _step(body, 1) and "every 10 increments" in rep.text()
    assert "*NODE FILE, FREQUENCY=20\nU\n" in _step(body, 3)
    body, _, _ = convert_str(HEX + "*Step\n*Dynamic, Explicit, direct user control\n1.e-6, 1.e-4\n"
                             "*Output, field, time interval=2.e-5\n*Node Output\nU\n*End Step\n"
                             "*Step\n*Dynamic, Explicit\n, 1.e-4, , 1.e-6\n*Output, field, number interval=4\n"
                             "*Node Output\nU\n*End Step\n")
    assert "*NODE FILE, FREQUENCY=20\nU\n" in _step(body, 1)
    assert "*NODE FILE, FREQUENCY=25\nU\n" in _step(body, 2)
    _, _, rep = convert_str(HEX + "*Step\n*Dynamic, Explicit\n, 1.e-4\n*Output, field\n*Node Output\nU\n"
                            "*End Step\n")
    assert "SELECTED time increment" in rep.text()


def test_beam_output_requests_example():
    # the validate_with_ccx.py deck: OUTPUT=2D for the tip set, *NODE PRINT for the history
    # node, both at the *TIME POINTS NUMBER INTERVAL = 4 became
    body, _, _ = convert(os.path.join(EXAMPLES, "beam_output_requests.inp"))
    assert "*TIME POINTS, NAME=ABQ2CCX_TP1, GENERATE\n0.25, 1., 0.25\n*STEP" in body
    assert ("*NODE FILE, NSET=TIP, OUTPUT=2D, TIME POINTS=ABQ2CCX_TP1\nU, RF\n*NODE PRINT, NSET=MID\n"
            "U\n") in body
    assert not dangling_refs(reparse(body))


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


HOT_CUBE = HEX + "*Solid Section, elset=EALL, material=M\n,\n*Material, name=M\n*Elastic\n" \
    "1000., 0.3\n*Expansion\n1.e-5\n*Conductivity\n50.\n*Boundary\n1, 1, 3\n2, 2, 3\n4, 3, 3\n"
HEAT_STEP = "*Step\n*Static\n*Temperature\n1, 100.\n*Node Print\nU\n*End Step\n"
DEFAULT_IC = ("** [abq2ccx] initial temperatures: the Abaqus default, 0, at every node (ccx reads "
              "*TEMPERATURE only after thermal initial conditions)\n*INITIAL CONDITIONS, "
              "TYPE=TEMPERATURE\nABQ2CCX_ALL_NODES, 0.\n*STEP")


def test_temperature_without_initial_conditions_starts_at_zero():
    # Abaqus starts every node at 0 when the deck gives no initial temperatures; ccx stops on
    # *TEMPERATURE without thermal initial conditions (probed on 2.23: with them a free heated
    # cube strains alpha T exactly), so they come ahead of the first step
    body, _, rep = convert_str(HOT_CUBE + HEAT_STEP)
    assert DEFAULT_IC in body and body.count("*INITIAL CONDITIONS") == 1
    assert reparse(body).nsets["ABQ2CCX_ALL_NODES"] == list(range(1, 9))
    assert "every node starts at 0, the Abaqus default" in rep.text() and rep.n_warnings == 0
    assert "*TEMPERATURE\n1, 100.\n*NODE PRINT" in body
    # a later step's card: still ahead of the first step, once
    body, _, _ = convert_str(HOT_CUBE + "*Step\n*Static\n*End Step\n" + HEAT_STEP + HEAT_STEP)
    assert body.count(DEFAULT_IC) == 1 and body.index(DEFAULT_IC) < body.index("*STATIC")
    # none without a *TEMPERATURE ccx reads: no card, one outside the steps (commented out)
    for deck in (HOT_CUBE + "*Step\n*Static\n*End Step\n",
                 HOT_CUBE + "*Temperature\n1, 100.\n*Step\n*Static\n*End Step\n"):
        body, _, rep = convert_str(deck)
        assert "INITIAL CONDITIONS" not in body and "ABQ2CCX_ALL_NODES" not in body
    # the deck's own initial temperatures are kept as they are when they name every node
    body, _, rep = convert_str(HOT_CUBE + "*Nset, nset=ALL, generate\n1, 8, 1\n"
                               "*Initial Conditions, type=temperature\nALL, 20.\n" + HEAT_STEP)
    assert "*INITIAL CONDITIONS, TYPE=temperature\nALL, 20.\n*STEP" in body
    assert body.count("*INITIAL CONDITIONS") == 1 and "Abaqus default" not in rep.text()


def test_temperature_in_thermal_step_commented_out():
    # temperature is DOF 11 in heat transfer and coupled temperature-displacement steps:
    # Abaqus does not allow *TEMPERATURE there, and ccx stops on it even with initial
    # temperatures (probed on 2.23) — commented out with the reason
    for proc in ("Heat Transfer, steady state", "Coupled Temperature-Displacement, steady state"):
        kw = proc.split(",")[0].upper()
        body, _, rep = convert_str(HOT_CUBE + f"*Step\n*{proc}\n1., 1.\n*Boundary\n7, 11, 11, 50.\n"
                                   "*Temperature\nEALL, 100.\n*Node Print\nNT\n*End Step\n")
        assert f"** abq2ccx: *TEMPERATURE in a *{kw} step: temperature is degree of freedom 11" \
            in body and "\n** *TEMPERATURE\n** EALL, 100.\n*NODE PRINT" in body
        assert "INITIAL CONDITIONS" not in body                       # no card ccx reads
        assert "prescribe the temperature with *BOUNDARY on DOF 11" in rep.text()
        assert rep.n_commented == 1
    # a mechanical step's card in the same deck stays, and gets its initial temperatures
    body, _, rep = convert_str(HOT_CUBE + "*Step\n*Heat Transfer, steady state\n1., 1.\n"
                               "*Temperature\n1, 100.\n*End Step\n" + HEAT_STEP)
    assert DEFAULT_IC in body and rep.n_commented == 1
    assert body.split("*STEP")[2].count("\n*TEMPERATURE\n1, 100.") == 1


def test_temperature_from_file_without_initial_conditions_warned():
    # ccx reads FILE= as a CalculiX .frd (with none it runs on undefined temperatures, printing
    # only "ERROR in readfrd"): the default would turn ccx's stop on the card into a run that
    # is not the deck's, so none is added, and the report says why
    body, _, rep = convert_str(HOT_CUBE + "*Step\n*Static\n*Temperature, file=thermal, bstep=1\n"
                               "*End Step\n" + HEAT_STEP)
    assert "INITIAL CONDITIONS" not in body and "*TEMPERATURE, FILE=thermal, BSTEP=1" in body
    assert "*TEMPERATURE, FILE= with no *INITIAL CONDITIONS" in rep.text() and ".frd" in rep.text()
    # with the deck's own initial temperatures the card passes through without the warning
    _, _, rep = convert_str(HOT_CUBE + "*Initial Conditions, type=temperature\n1, 0.\n"
                            "*Step\n*Static\n*Temperature, file=thermal\n*End Step\n")
    assert "ccx stops on the card" not in rep.text()
    # a USER card (Abaqus UTEMP) is commented out: only the cards ccx reads count
    body, _, _ = convert_str(HOT_CUBE + "*Step\n*Static\n*Temperature, user\n1\n*End Step\n")
    assert "INITIAL CONDITIONS" not in body and "** *TEMPERATURE, USER" in body
    body, _, _ = convert_str(HOT_CUBE + "*Step\n*Static\n*Temperature, user\n1\n*End Step\n"
                             + HEAT_STEP)
    assert DEFAULT_IC in body


def test_initial_temperatures_reach_knot_beam_nodes():
    # the knot beams of circular-section beams are planned after the deck's initial
    # temperatures are counted; their free nodes need one too (ccx: "no initial temperature
    # defined in node"), with the default and with the deck's own initial conditions
    heat = "*Step\n*Static\n*Temperature\nBEAM_N, 100.\n*End Step\n"
    deck = CIRC_BEAM + "*Nset, nset=BEAM_N\n1, 2, 3\n*Boundary\n1, 1, 4\n3, 2, 4\n"
    body, conv, _ = convert_str(deck + heat)
    assert list(conv._knots) == [1, 3] and DEFAULT_IC in body
    assert sorted(reparse(body).nsets["ABQ2CCX_ALL_NODES"]) == list(range(1, 8))
    body, _, rep = convert_str(deck + "*Initial Conditions, type=temperature\nBEAM_N, 20.\n" + heat)
    assert "*INITIAL CONDITIONS, TYPE=temperature\nABQ2CCX_ALL_NODES, 0.\nBEAM_N, 20." in body
    assert sorted(reparse(body).nsets["ABQ2CCX_ALL_NODES"]) == list(range(1, 8))


def test_thermal_no_initial_temperature_example():
    # the validate_with_ccx.py deck: the default initial temperatures reach every node, the
    # free node of the knot beam at the circular-section beam's pinned end included
    body, conv, rep = convert(os.path.join(EXAMPLES, "thermal_no_initial_temperature.inp"))
    g = reparse(body)
    assert DEFAULT_IC in body and list(conv._knots) == [11] and not dangling_refs(g)
    assert sorted(g.nsets["ABQ2CCX_ALL_NODES"]) == sorted(g.nodes) and len(g.nodes) == 14


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


def test_coupling_bc_bars_example():
    # the validate_with_ccx.py deck: bar A's redundant end-face BCs (x, y) and bar C's (z) are
    # taken off, bar B (the same constraints without a coupling) keeps all of its own
    body, _, rep = convert(os.path.join(EXAMPLES, "coupling_bc_bars.inp"))
    g = reparse(body)
    assert not dangling_refs(g), dangling_refs(g)
    assert [l for l in _bc_lines(body) if l.split(",")[0] in ("A_END", "B_END", "C_END")] == ["B_END,1,2"]
    assert "*BOUNDARY taken off 27 DOF(s)" in rep.text() and rep.n_warnings == 0


def _cloads(body):
    """Per *STEP, the summed *CLOAD data {(node, DOF): value} of a converted deck."""
    steps, in_cload = [], False
    for ln in body.splitlines():
        if ln.startswith("*STEP"):
            steps.append({})
        if ln.startswith("*"):
            in_cload = ln.startswith("*CLOAD")
        elif in_cload and steps:
            n, d, v = (x.strip() for x in ln.split(","))
            steps[-1][(int(n), int(d))] = steps[-1].get((int(n), int(d)), 0.0) + float(v)
    return steps


def _close(got, want, tol=1e-12):
    """Two {key: value} maps (or value lists) agree to ``tol``."""
    if isinstance(got, dict):
        return got.keys() == want.keys() and all(abs(got[k] - want[k]) <= tol for k in got)
    return len(got) == len(want) and all(abs(a - b) <= tol for a, b in zip(got, want))


def test_consistent_nodal_forces_integrate_shape_functions():
    unit = lambda p, n, t: (1.0, 0.0, 0.0)                        # noqa: E731

    def fx(xyz, kind="area", axi=False):
        return [f[0] for f in A.consistent_nodal_forces(kind, xyz, unit, axi)]
    square = [(0., 0., 0.), (1., 0., 0.), (1., 1., 0.), (0., 1., 0.)]
    sq_mid = [(.5, 0., 0.), (1., .5, 0.), (.5, 1., 0.), (0., .5, 0.)]
    tri = [(0., 0., 0.), (1., 0., 0.), (0., 1., 0.)]
    tri_mid = [(.5, 0., 0.), (.5, .5, 0.), (0., .5, 0.)]
    assert _close(fx(square), [.25] * 4)
    assert _close(fx(square + sq_mid), [-1 / 12] * 4 + [1 / 3] * 4)    # serendipity quad8
    assert _close(fx(tri), [1 / 6] * 3)
    assert _close(fx(tri + tri_mid), [0.] * 3 + [1 / 6] * 3)           # tri6: midsides only
    line = [(0., 0., 0.), (2., 0., 0.)]
    assert _close(fx(line, "line"), [1., 1.])
    assert _close(fx(line + [(1., 0., 0.)], "line"), [1 / 3, 1 / 3, 4 / 3])
    # axisymmetric edge r = 1..3: over the full circle, f_i = 2 pi * integral(N_i r ds)
    assert _close(fx([(1., 0., 0.), (3., 0., 0.)], "line", True),
                  [2 * math.pi * 5 / 3, 2 * math.pi * 7 / 3])


def test_dsload_traction_becomes_consistent_nodal_forces():
    deck = HEX + "*Surface, name=TOP\nEALL, S2\n*Step\n*Static\n*Dsload\nTOP, {}\n*End Step\n"
    body, conv, _ = convert_str(deck.format("TRVEC, 4., 0., 0., -2."))
    # 4 x area 1 over the face's 4 nodes, along the normalised direction
    assert _cloads(body) == [{(n, 3): -1.0 for n in (5, 6, 7, 8)}]
    assert "*DSLOAD" not in body and "** abq2ccx: TOP, TRVEC, 4., 0., 0., -2. -> nodal forces on 4 " \
                                     "node(s), resultant (0, 0, -4)" in body
    assert not conv.unloaded_steps
    # TRSHR: the direction projected onto the face (and normalised), at every point
    body, _, _ = convert_str(deck.format("TRSHR, 2., 1., 0., 1."))
    assert _cloads(body) == [{(n, 1): 0.5 for n in (5, 6, 7, 8)}]
    body, conv, rep = convert_str(deck.format("TRSHR, 2., 0., 0., 1."))
    assert _cloads(body) == [{}] and "no shear component" in rep.text()
    assert conv.unloaded_steps == [1]
    # where the direction is normal to a face, that face gets no shear load (Abaqus); the
    # rest of the surface keeps its load
    body, _, rep = convert_str(HEX + "*Surface, name=TWO\nEALL, S2\nEALL, S4\n*Step\n*Static\n"
                                     "*Dsload\nTWO, TRSHR, 2., 1., 0., 0.\n*End Step\n")
    assert _cloads(body) == [{(n, 1): 0.5 for n in (5, 6, 7, 8)}]
    assert "normal to part of the surface" in rep.text()
    # an element-based traction on face 2 is the same load
    body, _, _ = convert_str(HEX + "*Step\n*Static\n*Dload\nEALL, TRVEC2, 4., 0., 0., -2.\n*End Step\n")
    assert _cloads(body) == [{(n, 3): -1.0 for n in (5, 6, 7, 8)}]


def test_traction_on_plane_and_axisymmetric_edges():
    deck = ("*Node\n1, 1., 0.\n2, 2., 0.\n3, 2., 1.\n4, 1., 1.\n*Element, type={}, elset=E\n1, 1, 2, 3, 4\n"
            "*Material, name=M\n*Elastic\n1., 0.3\n*Solid Section, elset=E, material=M\n{}"
            "*Surface, name=R\nE, S2\n*Step\n*Static\n*Dsload\nR, TRVEC, 3., 0., 1., 7.\n*End Step\n")
    # plane stress: times the section thickness; a 2-D model has no third component
    body, _, _ = convert_str(deck.format("CPS4", "0.5\n"))
    assert _cloads(body) == [{(2, 2): 0.75, (3, 2): 0.75}]
    # axisymmetric (edge at r = 2): over the full circle, 2 pi r per unit length
    body, _, _ = convert_str(deck.format("CAX4", ""))
    assert _close(_cloads(body)[0], {(2, 2): 6 * math.pi, (3, 2): 6 * math.pi}, 1e-9)


def test_traction_under_nlgeom_converts_only_when_exact():
    deck = (HEX + "*Surface, name=TOP\nEALL, S2\n*Step, nlgeom\n*Static\n*Dsload{}\n"
            "TOP, TRVEC, 4., 0., 0., -1.\n*End Step\n")
    exact = [{(n, 3): -1.0 for n in (5, 6, 7, 8)}]
    body, conv, rep = convert_str(deck.format(""))                     # FOLLOWER=YES default
    assert _cloads(body) == [{}] and conv.unloaded_steps == [1]
    assert "rotates with the surface (FOLLOWER=YES, the Abaqus default)" in rep.text()
    assert "Step 1 is loaded in the Abaqus deck (*DSLOAD TRVEC on TOP)" in rep.text()
    body, conv, rep = convert_str(deck.format(", follower=no"))        # per current area
    assert _cloads(body) == [{}] and "CONSTANT RESULTANT=NO, the Abaqus default" in rep.text()
    body, conv, rep = convert_str(deck.format(", follower=no, constant resultant=yes"))
    assert _cloads(body) == exact and not conv.unloaded_steps and "[APPROX]" not in rep.text()
    body, conv, rep = convert_str(deck.format(""), approximate=True)
    assert _cloads(body) == exact and "[APPROX] *DSLOAD TRVEC" in rep.text()


def test_converted_loads_across_steps_never_use_op_new():
    deck = (HEX + "*Surface, name=TOP\nEALL, S2\n*Surface, name=BOT\nEALL, S1\n"
            "*Amplitude, name=A1\n0., 0., 1., 1.\n"
            "*Step\n*Static\n*Dsload, amplitude=A1\nTOP, TRVEC, 4., 0., 0., -1.\n*End Step\n"
            "*Step\n*Static\n*End Step\n"
            "*Step\n*Static\n*Dsload, op=new\nBOT, TRVEC, 8., 0., 0., 1.\n*End Step\n"
            "*Step\n*Static\n*Cload, op=new\n1, 1, 5.\n*End Step\n")
    body, conv, _ = convert_str(deck)
    s1, s2, s3, s4 = _cloads(body)
    assert s1 == {(n, 3): -1.0 for n in (5, 6, 7, 8)} and "*CLOAD, AMPLITUDE=A1" in body
    assert s2 == {}                                                     # unchanged: ccx keeps it
    # OP=NEW on the *DSLOAD: the earlier traction goes (0 on its nodes), the new one comes in
    assert s3 == {**{(n, 3): 0.0 for n in (5, 6, 7, 8)}, **{(n, 3): 2.0 for n in (1, 2, 3, 4)}}
    # the deck's own *CLOAD, OP=NEW also removes ccx's converted forces: given again
    assert s4 == {(1, 1): 5.0, **{(n, 3): 2.0 for n in (1, 2, 3, 4)}}
    assert body.upper().count("OP=NEW") == 1 and not conv.unloaded_steps


def test_converted_load_sharing_a_deck_cload_dof():
    deck = (HEX + "*Surface, name=TOP\nEALL, S2\n*Step\n*Static\n*Cload\n5, 3, 1.\n*Dsload\n"
            "TOP, TRVEC, 4., 0., 0., -1.\n*End Step\n")
    body, _, _ = convert_str(deck)                  # one step, one amplitude: the values add
    assert _cloads(body) == [{(5, 3): 0.0, (6, 3): -1.0, (7, 3): -1.0, (8, 3): -1.0}]
    body, _, rep = convert_str(deck + "*Step\n*Static\n*End Step\n")
    assert "share the entry of the deck's own *CLOAD" in rep.text()
    assert _cloads(body)[0] == {(5, 3): 1.0}


def test_beam_line_loads_become_consistent_nodal_forces():
    beam = ("*Node\n1, 0., 0., 0.\n2, 1., 0., 0.\n3, 2., 0., 0.\n*Element, type={}, elset=B\n{}"
            "*Material, name=M\n*Elastic\n1., 0.3\n*Beam Section, elset=B, material=M, section={}\n"
            "{}\n0., 0., 1.\n*Step\n*Static\n*Dload\nB, {}\n*End Step\n")
    two = "1, 1, 2\n2, 2, 3\n"
    body, _, _ = convert_str(beam.format("B31", two, "RECT", "1., 1.", "PY, 2."))
    assert _cloads(body) == [{(1, 2): 1.0, (2, 2): 2.0, (3, 2): 1.0}]
    # local axes: 1 = n1 (here z), 2 = t x n1 (here -y)
    body, _, _ = convert_str(beam.format("B31", two, "RECT", "1., 1.", "P1, 2."))
    assert _cloads(body) == [{(1, 3): 1.0, (2, 3): 2.0, (3, 3): 1.0}]
    body, _, rep = convert_str(beam.format("B31", two, "RECT", "1., 1.", "P2, 2."))
    assert _cloads(body) == [{(1, 2): -1.0, (2, 2): -2.0, (3, 2): -1.0}]
    assert "reads P1 / P2 on a beam as a pressure on the expanded section face" in rep.text()
    # a 3-node beam (end, middle, end): q L / 6, 2 q L / 3, q L / 6
    body, _, _ = convert_str(beam.format("B32", "1, 1, 2, 3\n", "RECT", "1., 1.", "PZ, 3."))
    assert _cloads(body) == [{(1, 3): 1.0, (2, 3): 4.0, (3, 3): 1.0}]
    # a CIRC B31 runs as B32: its new midside node takes its share
    body, _, _ = convert_str(beam.format("B31", "1, 1, 3\n", "CIRC", "0.1", "PZ, 3."))
    assert _cloads(body) == [{(1, 3): 1.0, (4, 3): 4.0, (3, 3): 1.0}]
    # planar beams: n1 = -z, so P2 acts along t x n1 = +y, and nothing out of plane
    planar = ("*Node\n1, 0., 0.\n2, 1., 0.\n*Element, type=B21, elset=B\n1, 1, 2\n*Material, "
              "name=M\n*Elastic\n1., 0.3\n*Beam Section, elset=B, material=M, section=RECT\n1., 1.\n"
              "*Step\n*Static\n*Dload\nB, P2, 2.\n*End Step\n")
    body, _, _ = convert_str(planar)
    assert _cloads(body) == [{(1, 2): 1.0, (2, 2): 1.0}]


def test_user_subroutine_loads_are_commented_out():
    deck = HEX + ("*Nset, nset=TOP\n5, 6, 7, 8\n*Amplitude, name=U1, definition=user, variables=1\n"
                  "*Step\n*Static\n*Boundary, user\nTOP, 3, 3\n*Cload, user\n5, 1, 1.\n"
                  "*Dload\nEALL, P1NU, 1.\nEALL, P2, 3.\n*Temperature, user\nTOP\n"
                  "*Film\nEALL, F1NU, 20., 5.\n*End Step\n")
    body, _, rep = convert_str(deck)
    for sub in ("uboun.f", "cload.f", "dload.f", "utemp.f", "film.f", "uamplitude.f"):
        assert sub in rep.text(), sub
    assert "** *BOUNDARY, USER" in body and "\n*BOUNDARY, USER" not in body
    assert "\nEALL, P2, 3." in body and "\nEALL, P1NU" not in body and "** EALL, P1NU, 1." in body
    assert "\n*FILM" not in body and "\n*TEMPERATURE" not in body


def test_load_audit_flags_steps_whose_loads_do_not_survive():
    body, conv, rep = convert_str(HEX + "*Nset, nset=TOP\n5, 6, 7, 8\n*Step\n*Static\n"
                                        "*Boundary, user\nTOP, 3, 3\n*End Step\n")
    assert conv.unloaded_steps == [1] and not conv.source_unloaded
    assert "Step 1 is loaded in the Abaqus deck (*BOUNDARY on TOP (user subroutine)), but no " \
           "load survives the conversion" in rep.text()
    _, conv, rep = convert_str(HEX + "*Step\n*Static\n*End Step\n")
    assert conv.source_unloaded and not conv.unloaded_steps and "applies no load" in rep.text()
    _, conv, _ = convert_str(HEX + "*Step\n*Frequency\n4\n*End Step\n")
    assert not conv.source_unloaded and not conv.unloaded_steps
    # loads carry over; OP=NEW removes the earlier steps' loads, not the cards before it in its
    # own step; an eigenvalue step needs none
    blocks = A.blocks_from_lines("""*STEP\n*STATIC\n*CLOAD\n1, 1, 1.\n*END STEP
*STEP\n*STATIC\n*BOUNDARY\n2, 1, 1, 0.\n*END STEP
*STEP\n*STATIC\n*CLOAD, OP=NEW\n2, 1, 1.\n*CLOAD, OP=NEW\n3, 1, 1.\n*END STEP
*STEP\n*STATIC\n*CLOAD, OP=NEW\n*BOUNDARY\n2, 1, 1, 0.5\n*END STEP
*STEP\n*STATIC\n*BOUNDARY, OP=NEW\n*END STEP\n*STEP\n*FREQUENCY\n*END STEP""".splitlines())
    assert A.step_load_audit(blocks, True) == [
        ["*CLOAD on 1"], ["*CLOAD on 1"], ["*CLOAD on 2", "*CLOAD on 3"],
        ["*BOUNDARY: prescribed value on 2"], [], None]


def test_dload_and_dsload_op_new_keep_each_others_loads():
    deck = (HEX + "*Surface, name=SF\nEALL, S2\n*Step\n*Static\n*Dsload\nSF, P, 1.\n*Dload\n"
            "EALL, GRAV, 9.81, 0., 0., -1.\n*End Step\n*Step\n*Static\n{}\n*End Step\n")
    # Abaqus' *DLOAD, OP=NEW keeps the *DSLOAD pressure, ccx's would remove it: given again
    body, conv, _ = convert_str(deck.format("*Dload, op=new"))
    step2 = body.split("*STEP")[2]
    assert "*DLOAD, OP=NEW" in step2 and "\nEALL, P2, 1." in step2 and "GRAV" not in step2
    # and the other way round
    body, conv, _ = convert_str(deck.format("*Dsload, op=new"))
    step2 = body.split("*STEP")[2]
    assert "*DLOAD, OP=NEW" in step2 and "\nEALL, GRAV, 9.81, 0., 0., -1." in step2
    assert "P2" not in step2 and not conv.unloaded_steps


def test_dload_without_element_set_loads_the_whole_model():
    body, _, _ = convert_str(HEX + "*Step\n*Static\n*Dload\n, GRAV, 9.81, 0., 0., -1.\n*End Step\n")
    assert "\nABQ2CCX_ALL_ELEMENTS, GRAV, 9.81, 0., 0., -1." in body
    assert "*ELSET, ELSET=ABQ2CCX_ALL_ELEMENTS\n1\n" in body


def test_dsload_on_undefined_surface_says_so():
    body, conv, rep = convert_str(HEX + "*Step\n*Static\n*Dsload\nNOPE, P, 1.\n*End Step\n")
    assert "surface 'NOPE' is not defined in the deck" in rep.text() and conv.unloaded_steps == [1]


def test_distributed_load_examples():
    # the decks validate_with_ccx.py runs: the converted forces add up to the applied loads
    body, conv, _ = convert(os.path.join(EXAMPLES, "cook_membrane_traction.inp"))
    (cook,) = _cloads(body)
    assert abs(sum(cook.values()) - 1.0) < 1e-12 and {d for _, d in cook} == {2}
    assert len(cook) == 33 and not conv.unloaded_steps                 # the loaded edge's nodes
    body, _, _ = convert(os.path.join(EXAMPLES, "beam_line_load_cantilever.inp"))
    (beams,) = _cloads(body)
    for nodes, dof, total in ((range(1, 22), 2, -1.0), (range(101, 122), 3, 1.0),
                              (list(range(201, 222)) + list(range(222, 242)), 3, -0.1)):
        assert abs(sum(beams.get((n, dof), 0.0) for n in nodes) - total) < 1e-12
    body, _, _ = convert(os.path.join(EXAMPLES, "cylinder_traction_cax.inp"))
    (ring,) = _cloads(body)
    assert abs(sum(ring.values()) - 2 * math.pi * 10 * 2) < 1e-9 and {d for _, d in ring} == {1}


# a surface element on the cube's top face, its normal (right-hand rule) +z: out of the cube
SKIN = HEX + "*ELEMENT, TYPE=SFM3D4, ELSET=SKIN\n9, 5, 6, 7, 8\n*SURFACE SECTION, ELSET=SKIN\n"
TOP4 = (5, 6, 7, 8)


def test_surface_elements_leave_the_mesh_and_carry_their_loads():
    deck = SKIN + ("*ELSET, ELSET=BOTH\nEALL, SKIN\n*SURFACE, NAME=TOP\nSKIN, SPOS\n*Step\n*Static\n"
                   "*Dload\nSKIN, TRVEC, 4., 0., 0., -2.\n*El Print, elset=SKIN\nS\n*End Step\n")
    body, conv, rep = convert_str(deck)
    geom = reparse(body)
    assert list(geom.elements) == [1] and geom.elsets["BOTH"] == [1] and "SKIN" not in geom.elsets
    assert "SFM3D4" not in body and "SURFACE" not in body and "*EL PRINT" not in body
    assert _cloads(body) == [{(n, 3): -1.0 for n in TOP4}]
    assert not conv.unloaded_steps and rep.n_warnings == 0 and rep.n_commented == 0
    assert "1 surface element(s) (SFM3D4) left out of the ccx mesh" in rep.text()


def test_surface_element_pressure_sense():
    # Abaqus: an element-based P is positive along the element normal (+z here, so a suction),
    # a surface P against the surface normal (SPOS: the element normal, SNEG: its reverse)
    deck = SKIN + "*SURFACE, NAME=TOP\nSKIN, {}\n*Step\n*Static\n{}\n*End Step\n"
    for side, load, fz in (("SPOS", "*Dload\nSKIN, P, 4.", 1.0), ("SPOS", "*Dsload\nTOP, P, 4.", -1.0),
                           ("SNEG", "*Dsload\nTOP, P, 4.", 1.0)):
        body, conv, _ = convert_str(deck.format(side, load))
        assert _cloads(body) == [{(n, 3): fz for n in TOP4}], (side, load)
        assert not conv.unloaded_steps and "*DLOAD" not in body
    # a surface with faces of both kinds: the solid face keeps ccx's own pressure
    body, _, rep = convert_str(deck.format("SPOS\nEALL, S2", "*Dsload\nTOP, P, 4."))
    assert "\nEALL, P2, 4." in body and _cloads(body) == [{(n, 3): -1.0 for n in TOP4}]
    assert "*SURFACE, NAME=TOP\nEALL, S2\n" in body and "sees only its other faces" in rep.text()


def test_quadratic_and_axisymmetric_surface_elements():
    c3d20 = ("*Node\n1, 0., 0., 0.\n2, 1., 0., 0.\n3, 1., 1., 0.\n4, 0., 1., 0.\n5, 0., 0., 1.\n"
             "6, 1., 0., 1.\n7, 1., 1., 1.\n8, 0., 1., 1.\n9, .5, 0., 0.\n10, 1., .5, 0.\n11, .5, 1., 0.\n"
             "12, 0., .5, 0.\n13, .5, 0., 1.\n14, 1., .5, 1.\n15, .5, 1., 1.\n16, 0., .5, 1.\n"
             "17, 0., 0., .5\n18, 1., 0., .5\n19, 1., 1., .5\n20, 0., 1., .5\n"
             "*Element, type=C3D20, elset=E\n1, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, "
             "17, 18, 19, 20\n*Element, type=SFM3D8, elset=SKIN\n2, 5, 6, 7, 8, 13, 14, 15, 16\n"
             "*Step\n*Static\n*Dload\nSKIN, TRVEC, 12., 0., 0., -1.\n*End Step\n")
    body, _, _ = convert_str(c3d20)                      # serendipity: -1/12 and 1/3 of the total
    assert _close(_cloads(body)[0], {**{(n, 3): 1.0 for n in (5, 6, 7, 8)},
                                     **{(n, 3): -4.0 for n in (13, 14, 15, 16)}})
    # axisymmetric: the edge r = 2 of a CAX8 (z up), 2 pi r per unit length.  Abaqus turns
    # node 1 -> node 2 (+z) counterclockwise for the element normal: -r, into the element
    cax8 = ("*Node\n1, 1., 0.\n2, 2., 0.\n3, 2., 1.\n4, 1., 1.\n5, 1.5, 0.\n6, 2., .5\n7, 1.5, 1.\n"
            "8, 1., .5\n*Element, type=CAX8, elset=E\n1, 1, 2, 3, 4, 5, 6, 7, 8\n"
            "*Element, type={}, elset=SKIN\n2, {}\n*Surface, name=OUT\nSKIN, SPOS\n"
            "*Step\n*Static\n{}\n*End Step\n")
    two, three = ("SFMAX1", "2, 3"), ("SFMAX2", "2, 6, 3")
    for (typ, nodes), load, share in ((two, "*Dload\nSKIN, P, 3.", {2: -1, 3: -1}),
                                      (two, "*Dsload\nOUT, P, 3.", {2: 1, 3: 1}),
                                      (two, "*Dload\nSKIN, TRVEC, 3., 1., 0., 5.", {2: 1, 3: 1}),
                                      (three, "*Dload\nSKIN, P, 3.", {2: -1, 6: -4, 3: -1})):
        body, conv, _ = convert_str(cax8.format(typ, nodes, load))
        want = {(n, 1): s * 12 * math.pi / sum(abs(x) for x in share.values())
                for n, s in share.items()}
        assert _close(_cloads(body)[0], want, 1e-9), (typ, load)
        assert typ not in body and not conv.unloaded_steps


def test_surface_element_pressure_under_nlgeom_needs_approximate():
    deck = SKIN + "*Step, nlgeom\n*Static\n*Dload\nSKIN, P, 4.\n*End Step\n"
    body, conv, rep = convert_str(deck)
    assert _cloads(body) == [{}] and conv.unloaded_steps == [1]
    assert "pressure stays normal to the deforming surface" in rep.text()
    body, conv, rep = convert_str(deck, approximate=True)
    assert _cloads(body) == [{(n, 3): 1.0 for n in TOP4}] and "[APPROX] *DLOAD P" in rep.text()


def test_other_loads_on_surface_elements():
    deck = SKIN + "*Step\n*Static\n*Dload\n{}\n*End Step\n"
    # a mass-proportional load: the surface elements carry no mass, the solids keep it
    body, conv, rep = convert_str(deck.format(", GRAV, 9.81, 0., 0., -1."))
    assert "\nABQ2CCX_ALL_ELEMENTS, GRAV, 9.81, 0., 0., -1." in body
    assert reparse(body).elsets["ABQ2CCX_ALL_ELEMENTS"] == [1] and not conv.unloaded_steps
    body, conv, _ = convert_str(deck.format("SKIN, GRAV, 9.81, 0., 0., -1."))
    assert "-> no load: it acts only on surface elements" in body and "\n*DLOAD" not in body
    # loads this conversion does not apply to surface elements are commented out
    body, conv, rep = convert_str(deck.format("SKIN, BZ, 3."))
    assert "a BZ load on them is not converted" in rep.text() and conv.unloaded_steps == [1]


def test_surface_elements_with_mass_or_rebar_stay_unless_approximate():
    heavy = SKIN.replace("SECTION, ELSET=SKIN\n", "SECTION, ELSET=SKIN, DENSITY=0.5\n")
    body, _, rep = convert_str(heavy + "*Step\n*Frequency\n3\n*End Step\n")
    assert "TYPE=SFM3D4" in body and "carry mass (*SURFACE SECTION, DENSITY=)" in rep.text()
    body, _, rep = convert_str(heavy + "*Step\n*Frequency\n3\n*End Step\n", approximate=True)
    assert "SFM3D4" not in body and "[APPROX] Surface elements (SFM3D4) left out" in rep.text()
    body, _, rep = convert_str(heavy + "*Step\n*Static\n*Dload\nSKIN, P, 4.\n*End Step\n")
    assert "SFM3D4" not in body and "[APPROX]" not in rep.text()     # mass does not act here
    rebar = SKIN + "*Rebar Layer\nR1, 0.01, 0.1, , M, 0., 1\n*Step\n*Static\n*End Step\n"
    body, _, rep = convert_str(rebar)
    assert "TYPE=SFM3D4" in body and "rebar layers (*REBAR LAYER)" in rep.text()


def test_surface_element_on_free_nodes_warns():
    deck = HEX + ("*Node\n9, 0., 0., 2.\n10, 1., 0., 2.\n11, 1., 1., 2.\n12, 0., 1., 2.\n"
                  "*Element, type=SFM3D4, elset=SKIN\n9, 9, 10, 11, 12\n")
    _, _, rep = convert_str(deck)
    assert "4 node(s) of the surface elements belong to no other element" in rep.text()


def test_surface_elements_in_an_assembly_instance():
    # the shape of petrkryslucsd_problem_le10nafems_mst10: an independent instance holding a
    # solid and its surface elements (with their section), loaded from the assembly
    deck = ("*Part, name=P\n*End Part\n*Assembly, name=A\n*Instance, name=I1, part=P\n"
            + HEX + "*Element, type=SFM3D4, elset=SKIN\n2, 5, 6, 7, 8\n*Solid Section, elset=EALL, material=M\n"
              "*Surface Section, elset=SKIN\n*End Instance\n*End Assembly\n*Material, name=M\n"
              "*Elastic\n1., 0.3\n*Step\n*Static\n*Dload, follower=NO\nA.I1.SKIN, TRVEC, 4., 0., 0., -1.\n"
              "*End Step\n")
    body, conv, rep = convert_str(deck)
    assert "SFM3D4" not in body and "SURFACE SECTION" not in body and rep.n_commented == 0
    assert _cloads(body) == [{(n, 3): -1.0 for n in TOP4}] and not conv.unloaded_steps


def test_nle10_surface_elements_example():
    body, conv, _ = convert(os.path.join(EXAMPLES, "nle10_surface_elements.inp"))
    (skin,) = _cloads(body)
    area = math.pi / 4 * (3.25 * 2.75 - 2 * 1)                      # the quarter elliptic annulus
    assert {d for _, d in skin} == {3} and abs(sum(skin.values()) / -1e6 - area) < 1e-4 * area
    assert "TYPE=SFM3D8" not in body and not conv.unloaded_steps


# the cube's top face under a traction along (3, 0, -4): (0.6, 0, -0.8) on each of its nodes
TRVEC_TOP = HEX + "*Surface, name=TOP\nEALL, S2\n*Step\n*Static\n*Dsload\nTOP, TRVEC, 4., 3., 0., -4.\n*End Step\n"


def _transformed(deck, nodes, data, typ="R", nset="TR"):
    """``deck`` with a *TRANSFORM of ``typ`` on ``nodes``, defined ahead of its first *Step."""
    return deck.replace("*Step", f"*Nset, nset={nset}\n{nodes}\n*Transform, nset={nset}, type={typ}\n"
                                 f"{data}\n*Step", 1)


def test_nodal_forces_on_transformed_nodes_go_into_their_local_axes():
    # ccx and Abaqus read a *CLOAD on a node with a *TRANSFORM in its local axes.  Rectangular:
    # 1 along a (here y), 3 = a x b (z), 2 = 3 x 1 (-x)
    body, conv, rep = convert_str(_transformed(TRVEC_TOP, "5, 6, 7, 8", "0., 2., 0., -1., 1., 0."))
    assert _close(_cloads(body)[0], {**{(n, 2): -0.6 for n in TOP4}, **{(n, 3): -0.8 for n in TOP4}})
    assert ("resultant (2.4, 0, -3.2), in the *CLOAD at the end of this step; in the local axes of "
            "the 4 with a *TRANSFORM") in body                               # the resultant: global
    assert not conv.unloaded_steps and rep.n_commented == 0 and "each node's local axes" in rep.text()
    # nodes without one keep the global components
    body, _, _ = convert_str(_transformed(TRVEC_TOP, "5, 6", "0., 2., 0., -1., 1., 0."))
    assert _close(_cloads(body)[0], {(5, 2): -0.6, (6, 2): -0.6, (7, 1): 0.6, (8, 1): 0.6,
                                     **{(n, 3): -0.8 for n in TOP4}})
    # cylindrical about the axis x = y = -1 (along +z): 1 radial at the node, 2 = 3 x 1, 3 = z
    body, _, _ = convert_str(_transformed(TRVEC_TOP, "5, 6, 7, 8", "-1., -1., 0., -1., -1., 2.", "C"))
    want = {}
    for n, (x, y) in zip(TOP4, ((0., 0.), (1., 0.), (1., 1.), (0., 1.))):
        c, s = (x + 1) / math.hypot(x + 1, y + 1), (y + 1) / math.hypot(x + 1, y + 1)
        want.update({(n, 1): 0.6 * c, (n, 2): -0.6 * s, (n, 3): -0.8})
    assert _close(_cloads(body)[0], want)


def test_nodal_forces_on_unusable_transforms_are_refused():
    for typ, data, why in (
            ("R", "0., 0., 0., 0., 1., 0.", "the rectangular *TRANSFORM of node 5 is degenerate"),
            ("R", "1., 1., 0., 2., 2., 0.", "the rectangular *TRANSFORM of node 5 is degenerate"),
            ("C", "1., 1., 1., 1., 1., 1.", "the cylindrical *TRANSFORM of node 5 is degenerate"),
            ("C", "0., 0., 0., 0., 0., 3.", "node 5 lies on the axis of its cylindrical *TRANSFORM"),
            ("S", "0., 0., 0., 0., 0., 3.", "node 5 lies on the polar axis of its spherical *TRANSFORM"),
            ("S", "1., 1., 1., 1., 1., 1.", "the spherical *TRANSFORM of node 5 is degenerate"),
            ("R", "0., 1., 0.", "node 5 has a *TRANSFORM whose data line cannot be read")):
        body, conv, rep = convert_str(_transformed(TRVEC_TOP, "5, 6, 7, 8", data, typ))
        assert _cloads(body) == [{}] and conv.unloaded_steps == [1], (typ, data)
        assert f"*DSLOAD TRVEC on 'TOP' not converted: {why}" in rep.text(), (typ, data)
        assert "\n** TOP, TRVEC, 4., 3., 0., -4.\n" in body
    # Abaqus allows one *TRANSFORM per node (ccx takes the last): two that differ are refused
    once = _transformed(TRVEC_TOP, "5", "0., 2., 0., -1., 1., 0.")
    body, conv, rep = convert_str(_transformed(once, "5, 6", "1., 0., 0., 0., 1., 0.", nset="TR2"))
    assert _cloads(body) == [{}] and "node 5 is in several *TRANSFORM cards" in rep.text()
    body, conv, _ = convert_str(_transformed(once, "5", "0., 2., 0., -1., 1., 0.", nset="TR2"))
    assert len(_cloads(body)[0]) == 8 and not conv.unloaded_steps            # the same twice


def test_nodal_forces_on_transformed_2d_nodes():
    deck = ("*Node\n1, 1., 0.\n2, 2., 0.\n3, 2., 1.\n4, 1., 1.\n*Element, type=CPS4, elset=E\n"
            "1, 1, 2, 3, 4\n*Material, name=M\n*Elastic\n1., 0.3\n*Solid Section, elset=E, material=M\n"
            "0.5\n*Surface, name=EDGE\nE, S2\n*Step\n*Static\n*Dsload\nEDGE, TRVEC, 3., 0., 1., 7.\n"
            "*End Step\n")                                     # (0, 0.75) on nodes 2 and 3
    r2 = 0.75 / math.sqrt(2)
    body, _, _ = convert_str(_transformed(deck, "2, 3", "1., 1., 0., -1., 1., 0."))
    assert _close(_cloads(body)[0], {(2, 1): r2, (2, 2): r2, (3, 1): r2, (3, 2): r2})
    # local 3 along -z: local 2 = 3 x 1 turns the other way; still only DOFs 1 and 2
    body, _, _ = convert_str(_transformed(deck, "2, 3", "1., 1., 0., 1., -1., 0."))
    assert _close(_cloads(body)[0], {(2, 1): r2, (2, 2): -r2, (3, 1): r2, (3, 2): -r2})
    # cylindrical about the z axis through the origin: radial and tangential in the plane
    body, _, _ = convert_str(_transformed(deck, "2, 3", "0., 0., 0., 0., 0., 1.", "C"))
    assert _close(_cloads(body)[0], {(2, 2): 0.75, (3, 1): 0.75 / math.sqrt(5),
                                     (3, 2): 1.5 / math.sqrt(5)})
    # a local 3-direction out of the model plane leaves the in-plane force no 2-D components
    body, conv, rep = convert_str(_transformed(deck, "2, 3", "1., 0., 1., 0., 1., 0."))
    assert _cloads(body) == [{}] and conv.unloaded_steps == [1]
    assert "the *TRANSFORM of node 2 turns its local 3-direction out of the global Z axis" in rep.text()


def test_beam_and_surface_element_loads_on_transformed_nodes():
    # a beam line load PY on node 3 with local axes 1 = z, 2 = x, 3 = y
    beam = ("*Node\n1, 0., 0., 0.\n2, 1., 0., 0.\n3, 2., 0., 0.\n*Element, type=B31, elset=B\n1, 1, 2\n"
            "2, 2, 3\n*Material, name=M\n*Elastic\n1., 0.3\n*Beam Section, elset=B, material=M, "
            "section=RECT\n1., 1.\n0., 0., 1.\n*Step\n*Static\n*Dload\nB, PY, 2.\n*End Step\n")
    body, _, _ = convert_str(_transformed(beam, "3", "0., 0., 1., 1., 0., 0."))
    assert _cloads(body) == [{(1, 2): 1.0, (2, 2): 2.0, (3, 3): 1.0}]
    # a pressure on a surface element (+z on the cube's top nodes) with local axes 1 = z
    body, conv, _ = convert_str(_transformed(SKIN + "*Surface, name=TOP\nSKIN, SPOS\n*Step\n*Static\n"
                                                    "*Dload\nSKIN, P, 4.\n*End Step\n",
                                             "5, 6, 7, 8", "0., 0., 1., 1., 0., 0."))
    assert _cloads(body) == [{(n, 1): 1.0 for n in TOP4}] and not conv.unloaded_steps


def test_transformed_nodal_forces_meet_the_decks_cload_on_local_dofs():
    # local 1 = z on node 5: the traction's force there shares local DOF 1 with the deck's own
    # *CLOAD, which a later step would replace in ccx -> refused (globally they look disjoint)
    deck = _transformed(HEX + "*Surface, name=TOP\nEALL, S2\n*Step\n*Static\n*Cload\n5, 1, 1.\n"
                              "*Dsload\nTOP, TRVEC, 4., 0., 0., -1.\n*End Step\n*Step\n*Static\n"
                              "*End Step\n", "5", "0., 0., 1., 1., 0., 0.")
    body, _, rep = convert_str(deck)
    assert "its nodal force on node 5 DOF 1 would share the entry of the deck's own *CLOAD" in rep.text()
    assert _cloads(body)[0] == {(5, 1): 1.0}


def test_transform_of_a_rotated_instance_rotates_the_local_axes():
    # the part's identity transform, in an instance turned 90 degrees about z: 1 = y, 2 = -x
    deck = ("*Part, name=P\n" + HEX + "*Nset, nset=TOPN\n5, 6, 7, 8\n*Transform, nset=TOPN\n"
            "1., 0., 0., 0., 1., 0.\n*Surface, name=TOP\nEALL, S2\n*Solid Section, elset=EALL, "
            "material=M\n*End Part\n*Assembly, name=A\n*Instance, name=I1, part=P\n0., 0., 0.\n"
            "0., 0., 0., 0., 0., 1., 90.\n*End Instance\n*End Assembly\n*Material, name=M\n"
            "*Elastic\n1., 0.3\n*Step\n*Static\n*Dsload\nI1.TOP, TRVEC, 4., 1., 0., 0.\n*End Step\n")
    body, conv, _ = convert_str(deck)
    (forces,) = _cloads(body)
    assert len(forces) == 4 and {d for _, d in forces} == {2} and _close(list(forces.values()), [-1.0] * 4)
    assert not conv.unloaded_steps


def test_traction_transformed_face_example():
    # the deck validate_with_ccx.py runs: its forces, turned back from each node's local axes,
    # are those of the same block without the *TRANSFORM cards
    path = os.path.join(EXAMPLES, "traction_transformed_face.inp")
    body, conv, _ = convert(path)
    plain, _, _ = convert_str(re.sub(r"(?m)^\*TRANSFORM.*\n.*\n", "", open(path).read()))
    (local,), (glob,) = _cloads(body), _cloads(plain)
    nodes = {n for n, _ in glob}
    assert len(nodes) == 21 and not conv.unloaded_steps and not dangling_refs(reparse(body))
    unit = lambda v: [x / math.sqrt(sum(y * y for y in v)) for x in v]    # noqa: E731
    cross = lambda a, b: [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2],   # noqa: E731
                          a[0] * b[1] - a[1] * b[0]]
    for n in nodes:
        i, j = (n - 801) % 10, (n - 801) // 10                    # node (x, y) = (i, j) / 4, z = 2
        if i <= 2:                                                # rectangular: a, b
            e1, e3 = unit([1., 2., .5]), unit(cross([1., 2., .5], [-1., 1., 3.]))
        else:                                                     # cylindrical: axis a -> b
            e3 = unit([.1, .2, 3.])
            p = [i / 4 + .5, j / 4 + .3, 2.]
            e1 = unit([p[k] - sum(x * y for x, y in zip(p, e3)) * e3[k] for k in range(3)])
        axes = (e1, cross(e3, e1), e3)
        back = [sum(local.get((n, d + 1), 0.0) * axes[d][k] for d in range(3)) for k in range(3)]
        assert _close(back, [glob.get((n, k + 1), 0.0) for k in range(3)], 1e-9), n


def test_rigid_body_bc_bars_example():
    # the validate_with_ccx.py deck: bar A's far-face u1 = 0 is implied in step 1 (its reference
    # point fixed) and moved to the reference point in step 2's OP=NEW card, where bar B has
    # the same BCs by hand
    body, conv, rep = convert(os.path.join(EXAMPLES, "rigid_body_bc_bars.inp"))
    g = reparse(body)
    assert not dangling_refs(g), dangling_refs(g)
    ra, rb = conv._rb_rot[9001], conv._rb_rot[9002]
    assert _bc_cards(body) == [
        ("*BOUNDARY", ["A_FIX,1,3", "B_FIX,1,3", "RP_A,1,3", f"{ra},1,3", "RP_B,1,3", f"{rb},1,3"]),
        ("*BOUNDARY, OP=NEW", ["A_FIX,1,3", "B_FIX,1,3", "9001,1,1", f"{ra},2,3", "RP_B,1,1",
                               f"{rb},2,3"])]
    assert "*BOUNDARY on 9 DOF(s) of 9 *RIGID BODY node(s) moved" in rep.text() and rep.n_warnings == 0


# two reference points (1 and 3, coincident) tied by *MPC BEAM to free nodes, and a HINGE
# connector between them about z (orientation AX)
RP2 = ("*Node\n1, 0.,0.,0.\n3, 0.,0.,0.\n11, 1.,0.,0.\n12, 0.,1.,0.\n21, 0.,0.,1.\n22, 1.,1.,1.\n"
       "*MPC\nBEAM, 11, 1\nBEAM, 12, 1\nBEAM, 21, 3\nBEAM, 22, 3\n"
       "*Element, type=CONN3D2, elset=H\n7, 1, 3\n*Orientation, name=AX\n0., 0., 1., 1., 0., 0.\n"
       "*Connector Section, elset=H\nHinge,\nAX,\n")


def test_connector_hinge_between_reference_points():
    # ccx has no connector element: a HINGE is its constraint, equal translations and equal
    # rotations about the two axes normal to the hinge axis, on the reference points' ROT
    # NODEs (ccx carries a rigid body's rotation there); the element itself is not emitted
    body, conv, rep = convert_str(RP2)
    r1, r3 = conv._rb_rot[1], conv._rb_rot[3]
    assert _equations(body) == [f"3,{k},1,1,{k},-1" for k in (1, 2, 3)] + \
        [f"{r3},{k},1,{r1},{k},-1" for k in (1, 2)]
    assert "CONN3D2" not in body and "ELSET=H" not in body and "undefined" not in rep.text()
    assert "Connector elements -> ccx constraints" in rep.text()
    # an oblique axis and an offset joint: rows over three rotation components, and node b
    # keeps its offset d in node a's turning system (u_3 - u_1 - theta_1 x d = 0)
    oblique = RP2.replace("3, 0.,0.,0.", "3, 0.,0.,2.").replace("0., 0., 1., 1., 0., 0.",
                                                                 "1., 0., 1., 0., 1., 0.")
    body, conv, _ = convert_str(oblique)
    r1, r3 = conv._rb_rot[1], conv._rb_rot[3]
    lines = _live(body)
    eqs = [lines[i + 2] for i, l in enumerate(lines) if l == "*EQUATION"]
    assert eqs[:2] == [f"3, 1, 1, 1, 1, -1, {r1}, 2, -2", f"3, 2, 1, 1, 2, -1, {r1}, 1, 2"]
    assert eqs[3:] == [f"{r3}, 2, 1, {r1}, 2, -1", f"{r3}, 3, 1, {r3}, 1, -1, {r1}, 3, -1, {r1}, 1, 1"]


def test_connector_in_assembly_resolves_instance_nodes():
    # CAE writes wires at assembly level with instance-qualified nodes: resolved to the flat
    # numbering (they used to be skipped, the connector lost), set members filtered quietly
    deck = ("*Part, name=P\n*Node\n1, 0.,0.,0.\n2, 1.,0.,0.\n*Element, type=T3D2, elset=B\n1, 1, 2\n"
            "*Solid Section, elset=B, material=M\n1.,\n*End Part\n*Assembly, name=A\n"
            "*Instance, name=I1, part=P\n*End Instance\n*Instance, name=I2, part=P\n1., 0., 0.\n"
            "*End Instance\n*Element, type=CONN3D2\n1, I1.2, I2.1\n*Elset, elset=W\n1,\n"
            "*Connector Section, elset=W\nJoin,\n*End Assembly\n*Material, name=M\n*Elastic\n"
            "1000., 0.3\n")
    body, conv, rep = convert_str(deck)
    assert _equations(body) == [f"3,{k},1,2,{k},-1" for k in (1, 2, 3)]
    assert "non-numeric connectivity" not in rep.text() and "reference undefined" not in rep.text()
    assert not dangling_refs(reparse(body))
    # a connector inside a part is one per instance
    part = deck.replace("*End Part", "*Element, type=CONN3D2, elset=W\n5, 1, 2\n"
                        "*Connector Section, elset=W\nJoin,\n*End Part")
    body, _, _ = convert_str(part)
    assert [f"2,{k},1,1,{k},-1" for k in (1, 2, 3)] + [f"4,{k},1,3,{k},-1" for k in (1, 2, 3)] \
        == _equations(body)[:6] and not dangling_refs(reparse(body))


def test_connector_to_ground_and_held_nodes():
    # a blank node is ground (at the other node): JOIN to ground holds the node — *BOUNDARY
    # lines, repeated after OP=NEW (which removes every earlier BC in ccx, model data too)
    deck = (HEX + "*Node\n9, 2.,0.,0.\n*Element, type=CONN3D2, elset=G\n5, 9,\n"
            "*Connector Section, elset=G\nJoin,\n*Boundary\n1, 1, 3\n*Step\n*Static\n"
            "*Boundary, op=NEW\n1, 1, 3\n*End Step\n")
    body, _, rep = convert_str(deck)
    lines = _live(body)
    assert lines.count("9, 1, 1") == 2 and lines.count("9, 3, 3") == 2
    assert lines[lines.index("*BOUNDARY, OP=NEW") + 2] == "9, 1, 1" and "OP=NEW" in rep.text()
    # HINGE to ground about z on a reference point: its translations and the rotations about
    # x and y held; the same constraint written against a node held by its own BCs
    rp = ("*Node\n1, 0.,0.,0.\n11, 1.,0.,0.\n12, 0.,1.,0.\n*MPC\nBEAM, 11, 1\nBEAM, 12, 1\n"
          "*Orientation, name=AX\n0., 0., 1., 1., 0., 0.\n")
    body, conv, _ = convert_str(rp + "*Element, type=CONN3D2, elset=H\n7, , 1\n"
                                "*Connector Section, elset=H\nHinge,\nAX,\n")
    r1 = conv._rb_rot[1]
    assert _bc_lines(body) == ["1,1,1", "1,2,2", "1,3,3", f"{r1},1,1", f"{r1},2,2"]
    assert not _equations(body)
    body, conv, _ = convert_str(rp + "*Node\n2, 0.,0.,0.\n*Element, type=CONN3D2, elset=H\n7, 2, 1\n"
                                "*Connector Section, elset=H\nHinge,\nAX,\n*Boundary\n2, ENCASTRE\n")
    r1 = conv._rb_rot[1]
    assert _bc_lines(body) == ["1,1,1", "1,2,2", "1,3,3", f"{r1},1,1", f"{r1},2,2",
                               "2,1,3"] and not _equations(body)


def test_connector_beam_weld_and_link():
    # BEAM (and WELD, the same rigid link) -> a rigid body, exactly like *MPC BEAM
    deck = B2 + "*Node\n100, 1.5, 0., 0.\n"
    as_mpc, _, _ = convert_str(deck + "*MPC\nBEAM, 100, 2\n")
    body, conv, _ = convert_str(deck + "*Element, type=CONN3D2, elset=W\n9, 2, 100\n"
                                "*Connector Section, elset=W\nBeam,\n")
    assert "*RIGID BODY, NSET=ABQ2CCX_MPCB1, REF NODE=2" in body and sorted(conv._knots) == [2]
    assert _equations(body) == _equations(as_mpc)
    # WELD between two nodes without rotations of their own: the rotations are
    # connector-only unknowns, so a coincident weld is a JOIN and an offset one a LINK
    body, conv, _ = convert_str(HEX + "*Node\n9, 1.,0.,0.\n*Element, type=CONN3D2, elset=W\n"
                                "20, 2, 9\n*Connector Section, elset=W\nWeld,\n")
    assert _equations(body) == [f"9,{k},1,2,{k},-1" for k in (1, 2, 3)] and not conv._rb_rot
    body, _, _ = convert_str(HEX + "*Node\n9, 3.,0.,0.\n*Element, type=CONN3D2, elset=W\n"
                             "20, 2, 9\n*Connector Section, elset=W\nWeld,\n")
    assert _equations(body) == ["9,1,1,2,1,-1"]
    # LINK -> as *MPC LINK
    body, _, rep = convert_str(HEX + "*Node\n9, 1.,3.,4.\n*Element, type=CONN3D2, elset=W\n"
                               "20, 2, 9\n*Connector Section, elset=W\nLink,\n")
    lines = _live(body)
    assert lines[lines.index("*EQUATION") + 2] == "9, 3, 0.8, 9, 2, 0.6, 2, 3, -0.8, 2, 2, -0.6"
    assert "Connector LINK in a deck without NLGEOM" in rep.text()


def test_connector_types_behaviour_and_free_types():
    base = HEX + "*Node\n9, 1.,0.,0.\n*Element, type=CONN3D2, elset=W\n20, 2, 9\n"
    # no constraint and no behaviour: transmits nothing — left out (exact)
    body, _, rep = convert_str(base + "*Connector Section, elset=W\nCartesian, Cardan\n")
    assert "transmits nothing" in rep.text() and not _equations(body) and "** *CONNECTOR" not in body
    # a type the converter does not write, and any behaviour: commented out with the reason
    body, _, rep = convert_str(base + "*Connector Section, elset=W\nSlot,\n")
    assert "** *CONNECTOR SECTION, ELSET=W" in body and "type SLOT is not converted" in rep.text()
    assert "** connector element(s) 20 (nodes 2, 9)" in body
    beh = "*Connector Behavior, name=B\n*Connector Elasticity, component=1\n100.,\n"
    body, _, rep = convert_str(base + beh + "*Connector Section, elset=W, behavior=B\nJoin,\n")
    assert "** *CONNECTOR SECTION" in body and "with a *CONNECTOR BEHAVIOR" in rep.text()
    assert not _equations(body)
    body, _, rep = convert_str(base + "*Connector Behavior, name=B\n"
                               "*Connector Section, elset=W, behavior=B\nJoin,\n")
    assert len(_equations(body)) == 3 and "defines nothing" in rep.text()
    # a section on an elset without connector elements stays a comment, and so does a
    # connector on one node twice
    body, _, rep = convert_str(HEX + "*Connector Section, elset=EALL\nJoin,\n")
    assert "** *CONNECTOR SECTION" in body and "holds no connector element" in rep.text()
    body, _, rep = convert_str(base.replace("20, 2, 9", "20, 2, 2") +
                               "*Connector Section, elset=W\nJoin,\n")
    assert not _equations(body) and "same node twice" in rep.text()


def test_connector_nlgeom_exact_cases_only():
    # under NLGEOM a hinge between two turning bodies is linear in the rotation vectors only
    # for small rotations, and ccx solves *EQUATIONs that link two rigid bodies inaccurately
    # (probed): commented out, or written with [APPROX] under --approximate
    nl = "*Step, nlgeom=YES\n*Static\n*End Step\n"
    body, _, rep = convert_str(RP2 + nl)
    assert not _equations(body) and "--approximate" in rep.text() and "** *CONNECTOR" in body
    body, _, rep = convert_str(RP2 + nl, approximate=True)
    assert len(_equations(body)) == 5 and "[APPROX] Connector under NLGEOM" in rep.text()
    # ... but a hinge to ground keeps its axis, so it is exact at any rotation
    ground = RP2.replace("7, 1, 3", "7, , 3")
    body, conv, rep = convert_str(ground + nl)
    r3 = conv._rb_rot[3]
    assert _bc_lines(body) == ["3,1,1", "3,2,2", "3,3,3", f"{r3},1,1", f"{r3},2,2"]
    assert not _equations(body) and "--approximate" not in rep.text()
    # oblique axis (x + z): an equation among the ROT NODE's own components — still exact
    body, _, rep = convert_str(ground.replace("0., 0., 1., 1., 0., 0.", "1., 0., 1., 0., 1., 0.") + nl)
    assert _equations(body) == [f"{r3},3,1,{r3},1,-1"] and f"{r3},2,2" in _bc_lines(body)
    assert "--approximate" not in rep.text() and "** *CONNECTOR" not in body
    # a JOIN from a reference point to a mesh node: eliminated on the mesh node (no ccx MPC
    # touches it), the reference point's translations independent — exact (probed), either
    # way round; a hinge between two solid nodes whose rotations live on new rotation nodes
    # (moments on them) links two turning nodes — commented out
    rp = ("*Node\n1, 0.5,0.5,1.\n100, 0.5,0.5,1.\n*Nset, nset=TOP\n5,6,7,8\n"
          "*Rigid Body, ref node=1, tie nset=TOP\n*Element, type=CONN3D2, elset=J\n")
    for conn in ("9, 1, 100", "9, 100, 1"):
        body, _, _ = convert_str(HEX + rp + conn + "\n*Connector Section, elset=J\nJoin,\n" + nl)
        assert [e.split(",")[:2] for e in _equations(body)] == [["100", str(k)] for k in (1, 2, 3)]
    body, conv, rep = convert_str(
        HEX + "*Node\n9, 1.,0.,0.\n*Orientation, name=AX\n1., 0., 1., 0., 1., 0.\n*Element, "
        "type=CONN3D2, elset=H\n30, 2, 9\n*Connector Section, elset=H\nHinge,\nAX,\n*Step, "
        "nlgeom=YES\n*Static\n*Cload\n2, 4, 1.\n9, 5, 1.\n*End Step\n")
    assert sorted(conv._rb_rot) == [2, 9] and not _equations(body) and "--approximate" in rep.text()
    # explicit dynamics: no knots (its solver stops on them), so a beam end's rotation
    # cannot be constrained — commented out rather than silently dropped
    beams = (B2 + "*Orientation, name=AX\n0., 0., 1., 1., 0., 0.\n*Element, type=CONN3D2, "
             "elset=H\n9, 2, 3\n*Connector Section, elset=H\nHinge,\nAX,\n")
    body, conv, rep = convert_str(beams + "*Step\n*Dynamic, Explicit\n, 1e-4\n*End Step\n")
    assert not _equations(body) and not conv._knots and "explicit dynamics" in rep.text()
    body, conv, _ = convert_str(beams)
    assert _equations(body) == [f"3,{k},1,2,{k},-1" for k in range(1, 6)] and \
        sorted(conv._knots) == [2, 3]


def test_connector_rotations_of_nodes_without_rotations():
    # HINGE between a beam end and a coincident solid node: the solid node's rotation is a
    # connector-only unknown (Abaqus adds it, nothing else touches it), so the revolute part
    # constrains nothing and only the JOIN remains ...
    deck = (HEX + "*Node\n20, 1.,0.,0.\n21, 2.,0.,0.\n*Element, type=B31, elset=B\n2, 20, 21\n"
            "*Beam Section, elset=B, material=M, section=RECT\n1.,1.\n0.,0.,1.\n"
            "*Material, name=M\n*Elastic\n1000., 0.3\n*Orientation, name=AX\n0., 0., 1., 1., 0., 0.\n"
            "*Element, type=CONN3D2, elset=H\n30, 20, 2\n*Connector Section, elset=H\nHinge,\nAX,\n")
    body, conv, _ = convert_str(deck)
    assert _equations(body) == [f"2,{k},1,20,{k},-1" for k in (1, 2, 3)]
    # ... unless that rotation shows elsewhere (a moment on it): it then lives on a new
    # rotation node, which the moment moves to
    body, conv, _ = convert_str(deck + "*Step\n*Static\n*Cload\n2, 4, 1.\n*End Step\n")
    rot = conv._rb_rot[2]
    assert _equations(body)[3:] == [f"{rot},1,1,20,4,-1", f"{rot},2,1,20,5,-1"]
    assert f"{rot}, 1, 1." in body and "2, 4, 1." not in body


def test_connector_examples():
    for name, eqs in (("connector_hinge_beams", 10), ("connector_hinge_bodies", 5),
                      ("connector_ground_hinge", 2)):
        body, conv, rep = convert(os.path.join(EXAMPLES, name + ".inp"))
        g = reparse(body)
        assert body.count("*EQUATION") - body.count("** *EQUATION") >= eqs, name
        assert "TYPE=CONN3D2" not in body and not dangling_refs(g), (name, dangling_refs(g))
        assert "WARNING" not in rep.text(), (name, rep.text())


def _emitted_transforms(body):
    """{node: (TYPE letter, [a, b])} of a converted deck's *TRANSFORM cards (the last wins)."""
    geom, out, lines = reparse(body), {}, body.splitlines()
    for i, ln in enumerate(lines):
        m = re.match(r"\*TRANSFORM, NSET=([^,]+)(?:, TYPE=(\w))?$", ln)
        if m:
            for n in geom.nset(m.group(1)):
                out[n] = (m.group(2) or "R", [float(x) for x in lines[i + 1].split(",")])
    return out


def _unit(v):
    return [x / math.sqrt(sum(y * y for y in v)) for x in v]


def _cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


HEX_XYZ = {1: (0., 0., 0.), 2: (1., 0., 0.), 3: (1., 1., 0.), 4: (0., 1., 0.), 5: (0., 0., 1.),
           6: (1., 0., 1.), 7: (1., 1., 1.), 8: (0., 1., 1.)}
STEP = "*Step\n*Static\n*End Step\n"


def test_spherical_transform_becomes_a_rectangular_one_per_node():
    # ccx has no spherical system (NaN results, or a singular matrix with a BC): each node gets
    # a rectangular *TRANSFORM with its Abaqus spherical axes — 1 radial from the centre a,
    # 2 = (b - a) x 1 circumferential, 3 = 1 x 2 meridional (towards the pole b)
    a, pole = (-1., -1., -1.), (0., 0., 1.)
    deck = _transformed(HEX + STEP, "1, 2, 3, 4, 5, 6, 7, 8", "-1., -1., -1., -1., -1., 3.", "S")
    body, _, rep = convert_str(deck)
    assert "** *TRANSFORM, NSET=TR, TYPE=S\n** -1., -1., -1., -1., -1., 3.\n" in body
    got = _emitted_transforms(body)
    for n, p in HEX_XYZ.items():
        e1 = _unit([x - y for x, y in zip(p, a)])
        assert got[n][0] == "R" and _close(got[n][1], e1 + _unit(_cross(pole, e1)), 1e-14), n
    assert len(re.findall(r"(?m)^\*TRANSFORM, NSET=ABQ2CCX_TR\d+, TYPE=R$", body)) == 7  # 1, 7: one ray
    assert "Each node gets a rectangular *TRANSFORM with its spherical axes" in rep.text()
    assert "*TRANSFORM" not in "".join(m for lvl, m in rep.entries if lvl == "WARNING")
    # nodes on the polar axis (here the z axis through the centre) have no spherical axes
    body, _, rep = convert_str(_transformed(HEX + STEP, "1, 2, 3, 4, 5, 6, 7, 8",
                                            "0., 0., 0., 0., 0., 3.", "S"))
    assert sorted(_emitted_transforms(body)) == [2, 3, 4, 6, 7, 8]
    assert ("*TRANSFORM, TYPE=S on TR: no local axes for 2 node(s), since node 1 lies on the polar "
            "axis of its spherical *TRANSFORM") in rep.text()
    # a set member the deck never defines has no position, hence no axes (and no crash)
    body, _, rep = convert_str(_transformed(HEX + STEP, "5, 6, 99", "-1., -1., -1., -1., -1., 3.", "S"))
    assert sorted(_emitted_transforms(body)) == [5, 6] and "node 99 of a spherical *TRANSFORM is " \
        "not defined" in rep.text()
    # converted loads on such nodes go into the same axes: turned back, they are the global ones
    body, conv, _ = convert_str(_transformed(TRVEC_TOP, "5, 6, 7, 8", "-1., -1., -1., -1., -1., 3.", "S"))
    (local,), got = _cloads(body), _emitted_transforms(body)
    for n in TOP4:
        e1, e2 = got[n][1][:3], got[n][1][3:]
        axes = (e1, e2, _cross(e1, e2))
        back = [sum(local.get((n, d + 1), 0.0) * axes[d][k] for d in range(3)) for k in range(3)]
        assert _close(back, [0.6, 0.0, -0.8], 1e-12), n
    assert not conv.unloaded_steps


def test_several_transforms_on_a_node_warn():
    # Abaqus: "Multiple transformation definitions are not allowed at a node"; ccx silently
    # takes the last card
    once = _transformed(HEX + STEP, "5", "0., 2., 0., -1., 1., 0.")
    body, _, rep = convert_str(_transformed(once, "5, 6", "1., 0., 0., 0., 1., 0.", nset="TR2"))
    assert ("1 node(s) (e.g. node 5) are named by several *TRANSFORM cards with different data"
            in rep.text()) and _emitted_transforms(body)[5] == ("R", [1., 0., 0., 0., 1., 0.])
    _, _, rep = convert_str(_transformed(once, "5", "0., 2., 0., -1., 1., 0.", nset="TR2"))
    assert "with the same data" in rep.text() and "different data" not in rep.text()
    _, _, rep = convert_str(once)
    assert "several *TRANSFORM cards" not in rep.text()


def test_transform_turning_2d_nodes_out_of_the_plane_warns():
    # a 2-D node has DOFs 1 and 2 in the model plane: the Abaqus manual wants a consistent
    # transformation (local 3 along Z); ccx 2.23 gets any other one wrong without an error
    plate = ("*Node\n1, 1., 0.\n2, 2., 0.\n3, 2., 1.\n4, 1., 1.\n*Element, type={}, elset=E\n"
             "1, 1, 2, 3, 4\n*Material, name=M\n*Elastic\n1., 0.3\n*Solid Section, elset=E, "
             "material=M\n{}" + STEP)
    warning = "out of the global Z axis, the normal of the model plane"
    for typ, data, tilted in (("R", "1., 1., 0., -1., 1., 0.", False),     # local 3 = +z
                              ("R", "1., 1., 0., 1., -1., 0.", False),     # local 3 = -z
                              ("C", "0., 0., 0., 0., 0., 1.", False),      # about z
                              ("R", "1., 0., 1., 0., 1., 0.", True),       # tilted
                              ("C", "0., 0., 0., 0., 1., 0.", True)):      # about y, in the plane
        for elem, thick in (("CPS4", "0.5\n"), ("CPE4", "0.5\n"), ("CAX4", "")):
            _, _, rep = convert_str(_transformed(plate.format(elem, thick), "2, 3", data, typ))
            assert (warning in rep.text()) == tilted, (elem, typ, data)
            if tilted:
                assert "2 node(s) of 2-D elements (e.g. node 2)" in rep.text()
    truss = ("*Node\n1, 0., 0.\n2, 1., 0.\n3, 0.5, 0.8\n*Element, type=T2D2, elset=E\n1, 1, 2\n"
             "2, 2, 3\n3, 3, 1\n*Material, name=M\n*Elastic\n1., 0.3\n*Solid Section, elset=E, "
             "material=M\n0.01\n" + STEP)
    _, _, rep = convert_str(_transformed(truss, "3", "1., 0., 1., 0., 1., 0."))
    assert warning in rep.text()
    _, _, rep = convert_str(_transformed(HEX + STEP, "6, 7", "1., 0., 1., 0., 1., 0."))   # 3-D
    assert warning not in rep.text()


# a rigid top face whose reference point 9 carries rotational BCs and a moment
RB = HEX + ("*Node\n9, 0.5, 0.5, 2.\n*Nset, nset=RP\n9\n*Nset, nset=TOPN\n5, 6, 7, 8\n"
            "*Rigid Body, ref node=RP, tie nset=TOPN\n*Step\n*Static\n*Boundary\nRP, 4, 5\n"
            "RP, 6, 6, 0.01\n*Cload\nRP, 6, 2.\n*End Step\n")


def test_rigid_body_rot_node_gets_the_reference_node_axes():
    # rotational BCs / moments on the reference node move to DOFs 1-3 of its ROT NODE; Abaqus
    # reads them in the reference node's local axes, so the ROT NODE gets the same ones
    rect = _transformed(RB, "9", "0., 2., 0., -1., 1., 0.")         # 1 = y, 2 = -x, 3 = z
    body, conv, rep = convert_str(rect)
    rot = conv._rb_rot[9]
    got = _emitted_transforms(body)
    assert got[rot] == ("R", [0., 1., 0., -1., 0., 0.]) and got[9] == ("R", [0., 2., 0., -1., 1., 0.])
    assert f"\n{rot}, 1, 2\n{rot}, 3, 3, 0.01\n" in body and _cloads(body) == [{(rot, 3): 2.0}]
    assert "each ROT NODE, which carries them as its DOFs 1-3, gets the same axes" in rep.text()
    # cylindrical about the x axis: the axes at the reference node's position (0.5, 0.5, 2)
    body, conv, _ = convert_str(_transformed(RB, "9", "0., 0., 0., 1., 0., 0.", "C"))
    e1 = _unit([0., 0.5, 2.])
    assert _close(_emitted_transforms(body)[conv._rb_rot[9]][1], e1 + _cross([1., 0., 0.], e1), 1e-14)
    # spherical (centre 0, pole z): the ROT NODE takes the reference node's spherical axes
    body, conv, _ = convert_str(_transformed(RB, "9", "0., 0., 0., 0., 0., 1.", "S"))
    e1 = _unit([0.5, 0.5, 2.])
    got = _emitted_transforms(body)
    assert _close(got[conv._rb_rot[9]][1], got[9][1], 0.) and \
        _close(got[9][1], e1 + _unit(_cross([0., 0., 1.], e1)), 1e-14)
    # on the cylinder axis the local axes are undefined: no transform for the ROT NODE, and the
    # moved BCs and moments act about the global axes there — warned
    axis = _transformed(RB, "9", "0.5, 0.5, 0., 0.5, 0.5, 1.", "C")
    body, conv, rep = convert_str(axis)
    assert conv._rb_rot[9] not in _emitted_transforms(body)
    assert ("Rotational BCs / moments on *RIGID BODY reference node 9, which has a *TRANSFORM, "
            "moved to DOFs 1-3 of its ROT NODE act about the global axes") in rep.text()
    held = axis.replace("RP, 4, 5\nRP, 6, 6, 0.01\n*Cload\nRP, 6, 2.\n", "RP, 4, 6\n")
    _, _, rep = convert_str(held)                       # all rotations held at 0: any axes
    assert "act about the global axes" not in rep.text()


def test_rotation_ties_to_a_transformed_rot_node_use_its_axes():
    # knotted shell members of the body tie their (global) rotations to the ROT NODE, whose
    # DOFs are local once it has the reference node's axes (1 = y, 2 = -x, 3 = z here):
    # rotation x = -local 2, y = local 1, z = local 3
    plate = ("*Node\n1, 0., 0., 0.\n2, 1., 0., 0.\n3, 1., 1., 0.\n4, 0., 1., 0.\n9, 1.5, 0.5, 0.\n"
             "*Element, type=S4, elset=P\n1, 1, 2, 3, 4\n*Material, name=M\n*Elastic\n1., 0.3\n"
             "*Shell Section, elset=P, material=M\n0.1\n*Nset, nset=RP\n9\n*Nset, nset=EDGE\n2, 3\n"
             "*Rigid Body, ref node=RP, tie nset=EDGE\n*Step\n*Static\n*Boundary\n1, 1, 6\n4, 1, 6\n"
             "RP, 4, 5\n*Cload\nRP, 6, 1.\n*End Step\n")
    body, conv, rep = convert_str(_transformed(plate, "9", "0., 2., 0., -1., 1., 0."))
    rot = conv._rb_rot[9]
    for n in (2, 3):
        for line in (f"{n}, 4, 1., {rot}, 2, 1.", f"{n}, 5, 1., {rot}, 1, -1.", f"{n}, 6, 1., {rot}, 3, -1."):
            assert f"*EQUATION\n2\n{line}\n" in body, line
    assert "Coupled rotation not tied" not in rep.text()
    body, conv, _ = convert_str(plate)                                  # no transform: as before
    assert f"*EQUATION\n2\n2, 4, 1., {conv._rb_rot[9]}, 1, -1.\n" in body


def test_rot_node_with_connector_rows_keeps_the_global_axes():
    # connector constraints on a reference point's rotation are written in global components on
    # its ROT NODE (RP2: a hinge between two *MPC BEAM reference points), so a ROT NODE that
    # carries them gets no transform; a rotational BC moved there is warned
    deck = RP2 + "*Nset, nset=R1\n1\n*Transform, nset=R1\n0., 1., 0., -1., 0., 0.\n*Step\n*Static\n" \
                 "*Boundary\n1, 5, 5\n*End Step\n"
    body, conv, rep = convert_str(deck)
    assert conv._rb_rot[1] not in _emitted_transforms(body) and 1 in _emitted_transforms(body)
    assert f"its rotation node {conv._rb_rot[1]} also carries connector constraints" in rep.text()


def test_transform_spherical_rigid_example():
    # the deck validate_with_ccx.py runs against its global twin: nine spherical nodes on
    # nine rays (nine cards), the cylindrical reference point's ROT NODE (one more)
    body, conv, rep = convert(os.path.join(EXAMPLES, "transform_spherical_rigid.inp"))
    rot = conv._rb_rot[100]
    got = _emitted_transforms(body)
    assert len(re.findall(r"(?m)^\*TRANSFORM, NSET=ABQ2CCX_TR\d+, TYPE=R$", body)) == 10
    assert sorted(got) == [32, 33, 34, 37, 38, 39, 42, 43, 44, 100, rot] and got[100][0] == "C"
    assert f"\n{rot}, 1, 2\n" in body and f"\n{rot}, 3, 0.05\n" in body
    assert rep.n_warnings == 0 and not conv.unloaded_steps and not dangling_refs(reparse(body))


# --- *BOUNDARY, TYPE=VELOCITY / ACCELERATION ------------------------------------------

VEL_HEX = HEX + """*NSET, NSET=TOP
5, 6, 7, 8
*NSET, NSET=BOT
1, 2, 3, 4
*MATERIAL, NAME=M
*ELASTIC
1000., 0.
*DENSITY
1.
*SOLID SECTION, ELSET=EALL, MATERIAL=M
*BOUNDARY
BOT, 1, 3
"""


def _amplitude(body, name):
    """The (time, value) points of *AMPLITUDE NAME=name in an emitted deck."""
    lines = body.splitlines()
    vals = []
    for ln in lines[lines.index(f"*AMPLITUDE, NAME={name}") + 1:]:
        if ln.startswith("*"):
            break
        vals += [float(x) for x in ln.split(",")]
    return list(zip(vals[0::2], vals[1::2]))


def _at(points, t):
    """What ccx applies at time t from tabular points: straight lines, end values held."""
    if t <= points[0][0]:
        return points[0][1]
    for (t0, v0), (t1, v1) in zip(points, points[1:]):
        if t <= t1:
            return v0 + (v1 - v0) * (t - t0) / (t1 - t0)
    return points[-1][1]


def test_amplitude_curve_definitions():
    def curve(params, data):
        return A.amplitude_curve(A.mkblock("AMPLITUDE", [("NAME", "A")] + params, data))
    c = curve([], ["0., 0., 1., 2., 3., 2."])
    assert [c.value(t) for t in (-1., 0.5, 2., 9.)] == [0., 1., 2., 2.] and c.breaks == [0., 1., 3.]
    c = curve([("DEFINITION", "SMOOTH STEP")], ["0., 0., 2., 1."])
    assert c.value(1.) == 0.5 and abs(c.value(0.5) - 0.103515625) < 1e-15
    c = curve([("DEFINITION", "EQUALLY SPACED"), ("FIXED INTERVAL", "0.5"), ("BEGIN", "1.")],
              ["0., 4., 2."])
    assert [c.value(t) for t in (1., 1.25, 1.5, 2.)] == [0., 2., 4., 2.]
    c = curve([("SCALEX", "2."), ("SCALEY", "3."), ("SHIFTX", "1."), ("SHIFTY", "-1.")],
              ["0., 0., 1., 1."])                                  # scaled, then shifted
    assert c.breaks == [1., 3.] and c.value(2.) == 0.5 and c.value(3.) == 2.
    c = curve([("DEFINITION", "PERIODIC"), ("TIME", "TOTAL TIME")], ["1, 2., 0.5, 1.", "0., 3."])
    assert c.total and c.value(0.) == 1. and abs(c.value(1.) - (1. + 3. * math.sin(1.))) < 1e-14
    c = curve([("DEFINITION", "DECAY"), ("VALUE", "ABSOLUTE")], ["1., 2., 0., 0.5"])
    assert c.absolute and abs(c.value(1.) - (1. + 2. * math.exp(-2.))) < 1e-14
    assert curve([("DEFINITION", "USER")], []) is None
    assert curve([], ["1., 0., 0., 1."]) is None                  # times must not decrease


def test_integrate_history_is_exact_at_its_points():
    pts, x, _, dev = A.integrate_history(lambda t: 5.0, [], 0.005)   # constant: exactly linear
    assert len(pts) == 2 and abs(x - 0.025) < 1e-15 and dev == 0.0
    # a SMOOTH STEP velocity over the first 0.001 of a 0.01 step (the davidmorin decks)
    c = A.amplitude_curve(A.mkblock("AMPLITUDE", [("NAME", "A"), ("DEFINITION", "SMOOTH STEP")],
                                    ["0., 0., 0.001, 1."]))
    pts, x, _, dev = A.integrate_history(lambda t: 100.0 * c.value(t), c.breaks, 0.01)

    def exact(t):
        s = min(t / 0.001, 1.0)
        return 100.0 * (0.001 * s ** 4 * (2.5 - 3. * s + s * s) + max(t - 0.001, 0.0))
    assert abs(x - 0.95) < 1e-14 and max(abs(v - exact(t)) for t, v in pts) < 1e-15
    # between the points, the straight lines ccx applies stay within 1e-4 of the travel
    worst = max(abs(_at(pts, k * 1e-6) - exact(k * 1e-6)) for k in range(10001))
    assert worst <= dev + 1e-15 and dev <= 1e-4 * 0.95 and len(pts) < 40
    # an acceleration from x0, r0: x = x0 + r0 t + a t^2 / 2
    pts, x, r, _ = A.integrate_history(lambda t: 2.0, [], 1.0, order=2, x0=1.0, r0=-1.0)
    assert abs(x - 1.0) < 1e-14 and abs(r - 1.0) < 1e-14
    assert max(abs(v - (1.0 - t + t * t)) for t, v in pts) < 1e-14


def test_velocity_bc_integrated_into_displacement_amplitude():
    deck = VEL_HEX + ("*Amplitude, name=Amp-1, definition=SMOOTH STEP\n0., 0., 0.001, 1\n"
                      "*Step, nlgeom=YES, inc=10000\n*Static\n0.000001, 0.01, 1e-08, 0.00001\n"
                      "*Boundary, amplitude=Amp-1, type=VELOCITY\nTOP, 3, 3, 100.\n*End Step\n")
    body, _, rep = convert_str(deck)
    # the magnitude stays on the line, the amplitude is the motion per unit velocity
    assert "*BOUNDARY, AMPLITUDE=ABQ2CCX_VEL1\nTOP, 3, 3, 100\n" in body
    assert "TYPE=VELOCITY" not in body
    pts = _amplitude(body, "ABQ2CCX_VEL1")
    assert pts[0] == (0.0, 0.0) and pts[-2] == (0.001, 0.0005) and pts[-1] == (0.01, 0.0095)
    assert "\n*AMPLITUDE, NAME=Amp-1" not in body                 # only the velocity used it
    assert "read as displacements" not in rep.text()


def test_velocity_bc_explicit_default_is_constant():
    deck = VEL_HEX + ("*Step, nlgeom=YES\n*Dynamic, Explicit\n, 0.005\n*Boundary, type=VELOCITY\n"
                      "TOP, 1, 1\nTOP, 3, 3, 5.\n*End Step\n")
    body, _, rep = convert_str(deck)
    # Abaqus/Explicit applies a BC without amplitude at once: a constant velocity, u = 5 t
    assert "*BOUNDARY\nTOP, 1, 1\n*BOUNDARY, AMPLITUDE=ABQ2CCX_VEL1\nTOP, 3, 3, 5\n" in body
    assert _amplitude(body, "ABQ2CCX_VEL1") == [(0.0, 0.0), (0.005, 0.005)]
    assert "jump in velocity at the start of a dynamic step" in rep.text()


def test_velocity_bc_carried_into_later_steps_and_ramped():
    deck = VEL_HEX + ("*Amplitude, name=A1\n0., 0., 0.5, 1., 1., 1.\n"
                      "*Step\n*Static\n0.1, 1.\n*Boundary, type=VELOCITY, amplitude=A1\n"
                      "TOP, 3, 3, 0.1\n*End Step\n*Step\n*Static\n0.1, 2.\n*End Step\n"
                      "*Step\n*Static\n0.1, 1.\n*Boundary, type=VELOCITY\nTOP, 3, 3, -0.2\n*End Step\n")
    body, _, rep = convert_str(deck)
    steps = body.split("*STEP")
    assert _amplitude(body, "ABQ2CCX_VEL1")[-1] == (1.0, 0.75)          # 0.1 x 0.75 = 0.075
    # step 2 keeps the BC: in Abaqus the DOF keeps moving at the velocity it ended with,
    # where a ccx BC would freeze at its last value
    assert "*BOUNDARY, AMPLITUDE=ABQ2CCX_VEL2\nTOP, 3, 3, 1.\n*END STEP" in steps[2]
    assert _amplitude(body, "ABQ2CCX_VEL2") == [(0.0, 0.075), (2.0, 0.275)]
    # step 3, no amplitude in a static step: the velocity ramps from 0.1 to -0.2
    pts = _amplitude(body, "ABQ2CCX_VEL3")
    assert pts[0] == (0.0, 0.275) and pts[-1] == (1.0, 0.225)
    assert max(abs(v - (0.275 + 0.1 * t - 0.15 * t * t)) for t, v in pts) < 1e-12
    assert "default amplitude is RAMP" in rep.text()


def test_velocity_bc_after_a_free_step():
    deck = VEL_HEX + ("*Step\n*Static\n*Cload\nTOP, 3, 1.\n*End Step\n"
                      "*Step\n*Static\n*Boundary, type=VELOCITY\nTOP, 3, 3, 0.5\nTOP, 1, 2\n*End Step\n")
    body, _, rep = convert_str(deck)
    # TOP moved freely in step 1, so ccx cannot be given the total displacement: a zero
    # velocity holds the DOFs where they are (FIXED), another one is left out
    assert "** [abq2ccx] not converted: TOP, 3, 3" in body
    assert "*BOUNDARY, FIXED\nTOP, 1, 2\n" in body
    assert "displacement at the start of the step is unknown" in rep.text()


def test_acceleration_bc_from_initial_velocity():
    deck = VEL_HEX + ("*Initial Conditions, type=VELOCITY\nTOP, 3, 0.5\n*Step\n*Dynamic\n0.1, 1.\n"
                      "*Boundary, type=ACCELERATION\nTOP, 3, 3, 2.\n*End Step\n")
    body, _, _ = convert_str(deck)
    pts = _amplitude(body, "ABQ2CCX_ACC1")                 # u = 0.5 t + t^2
    assert "*BOUNDARY, AMPLITUDE=ABQ2CCX_ACC1\nTOP, 3, 3, 1.\n" in body and pts[-1] == (1.0, 1.5)
    assert max(abs(v - (0.5 * t + t * t)) for t, v in pts) < 1e-9


def test_velocity_bc_on_rigid_body_reference_point():
    rigid = (VEL_HEX + "*Node\n100, 0.5, 0.5, 1.\n*Nset, nset=RP\n100\n"
             "*Rigid Body, ref node=100, tie nset=TOP\n")
    deck = rigid + ("*Step, amplitude=STEP\n*Static\n0.1, 1.\n*Boundary, type=VELOCITY\n"
                    "RP, 1, 5\nRP, 6, 6, 0.2\n*End Step\n")
    body, _, rep = convert_str(deck)
    # the angular velocity drives the body's ROT NODE (ccx ignores DOFs 4-6 of the REF NODE);
    # under *STEP, AMPLITUDE=STEP it is constant, so the turn is exactly linear
    assert "*BOUNDARY, AMPLITUDE=ABQ2CCX_VEL1\n101, 3, 3, 0.2\n" in body
    assert _amplitude(body, "ABQ2CCX_VEL1") == [(0.0, 0.0), (1.0, 1.0)]
    assert "*BOUNDARY\nRP, 1, 3\n101, 1, 2\n" in body and "default amplitude is RAMP" not in rep.text()
    # a zero velocity from a zero start holds the reference point at zero: the members'
    # x BC is implied by the body (ccx would stop on it) and taken off (_plan_coupled_bcs)
    deck = rigid + ("*Step\n*Static\n0.1, 1.\n*Boundary\nTOP, 1, 1\n*Boundary, type=VELOCITY\n"
                    "RP, 1, 2\nRP, 4, 6\nRP, 3, 3, 0.1\n*End Step\n")
    body, conv, _ = convert_str(deck)
    assert {(n, 1) for n in (5, 6, 7, 8)} <= set().union(*conv._bc_drop.values())
    assert "TOP, 1, 1" not in body


def test_velocity_bc_examples():
    # the decks validate_with_ccx.py runs: the column's reference point follows the
    # SMOOTH STEP velocity and keeps moving in the second step; the bar's end moves at v
    body, _, _ = convert(os.path.join(EXAMPLES, "velocity_bc_column.inp"))
    assert "*BOUNDARY, AMPLITUDE=ABQ2CCX_VEL1\nRP, 3, 3, 1\n" in body
    assert _amplitude(body, "ABQ2CCX_VEL1")[-1] == (0.01, 0.0095)
    assert "*BOUNDARY, AMPLITUDE=ABQ2CCX_VEL2\nRP, 3, 3, 1.\n*END STEP" in body
    assert _amplitude(body, "ABQ2CCX_VEL2") == [(0.0, 0.0095), (0.005, 0.0145)]
    assert not dangling_refs(reparse(body))
    body, _, _ = convert(os.path.join(EXAMPLES, "velocity_bc_bar.inp"))
    assert "*BOUNDARY, AMPLITUDE=ABQ2CCX_VEL1\nDRIVEN, 3, 3, 0.01\n" in body
    assert _amplitude(body, "ABQ2CCX_VEL1") == [(0.0, 0.0), (0.5, 0.5)]
    assert not dangling_refs(reparse(body))


def test_velocity_bc_card_follows_op_new_drop():
    # a later step whose velocity card re-specifies every BC with OP=NEW: the converted card
    # loses OP=NEW like a displacement card would (_plan_op_new_rotations); TIP's x was
    # free in step 1, so its velocity cannot become a total displacement
    deck = ("*Node\n1, 0., 0., 0.\n2, 1., 0., 0.\n3, 2., 0., 0.\n"
            "*Element, type=B31, elset=BEAM\n1, 1, 2\n2, 2, 3\n"
            "*Beam Section, elset=BEAM, material=M, section=RECT\n0.1, 0.1\n0., 0., -1.\n"
            "*Material, name=M\n*Elastic\n2.1e5, 0.3\n*Nset, nset=ROOT\n1\n*Nset, nset=TIP\n3\n"
            "*Boundary\nROOT, 1, 6\n*Step\n*Static\n*Cload\nTIP, 2, -1.\n*End Step\n"
            "*Step\n*Static\n*Boundary, op=NEW, type=VELOCITY\nROOT, 1, 6\nTIP, 1, 1, 0.5\n*End Step\n")
    body, _, _ = convert_str(deck)
    step2 = body.split("*STEP")[2]
    assert "** [abq2ccx] OP=NEW dropped" in step2 and "*BOUNDARY\nROOT, 1, 6\n" in step2
    assert "OP=NEW\n" not in step2 and "not converted: TIP, 1, 1" in step2


def test_velocity_bc_zero_rate_from_unknown_start_holds_what_it_can():
    # TOP moved freely in step 1: a zero velocity on DOFs 1-6 (or ENCASTRE) of these solid
    # nodes holds their translations (the solid nodes have no DOFs 4-6 to hold)
    for line in ("TOP, 1, 6", "TOP, ENCASTRE"):
        body, _, _ = convert_str(VEL_HEX + "*Step\n*Static\n*Cload\nTOP, 3, 1.\n*End Step\n*Step\n"
                                           "*Static\n*Boundary, type=VELOCITY\n" + line + "\n*End Step\n")
        assert "*BOUNDARY, FIXED\nTOP, 1, 3\n*END STEP" in body, line
    # XSYMM (DOFs 1, 5, 6) on a rigid body's reference point: x on the point, the turns on
    # its ROT NODE's translations — never a DOF range over 1-6
    body, _, _ = convert_str(VEL_HEX + "*Node\n100, 0.5, 0.5, 1.\n*Nset, nset=RP\n100\n"
                                       "*Rigid Body, ref node=100, tie nset=TOP\n*Step\n*Static\n*Cload\n"
                                       "RP, 3, 1.\n*End Step\n*Step\n*Static\n*Boundary, type=VELOCITY\n"
                                       "RP, XSYMM\n*End Step\n")
    assert "*BOUNDARY, FIXED\nRP, 1, 1\n101, 2, 3\n*END STEP" in body


def test_velocity_bc_midside_node_follows_its_end_nodes():
    deck = ("*Node\n1, 0., 0., 0.\n2, 1., 0., 0.\n*Element, type=B31, elset=BEAM\n1, 1, 2\n"
            "*Beam Section, elset=BEAM, material=M, section=CIRC\n0.05\n0., 0., -1.\n*Material, name=M\n"
            "*Elastic\n2.1e5, 0.3\n*Boundary\n1, 1, 2\n1, 4, 6\n2, 1, 2\n"
            "*Step, amplitude=STEP\n*Static\n0.1, 1.\n*Boundary, type=VELOCITY\n1, 3, 3, 1.\n2, 3, 3, 1.\n"
            "*End Step\n*Step, amplitude=STEP\n*Static\n0.1, 1.\n*End Step\n"
            "*Step, amplitude=STEP\n*Static\n0.1, 1.\n*Boundary, type=VELOCITY\n2, 3, 3, 3.\n*End Step\n")
    body, conv, _ = convert_str(deck)
    assert list(conv._midside.values()) == [(1, 2, 3)]           # the CIRC beam's midside node
    steps = body.split("*STEP")
    assert "1, 3, 3, 1\n2, 3, 3, 1\n3, 3, 3, 1\n" in steps[1]
    # kept into step 2: the continuation moves the midside node with its ends
    assert "1, 3, 3, 1.\n2, 3, 3, 1.\n3, 3, 3, 1\n*END STEP" in steps[2]
    # step 3 re-specifies node 2 only: node 1 keeps moving at 1, node 2 at 3, the midside
    # node at their mean (2 -> 4)
    assert "*BOUNDARY, AMPLITUDE=ABQ2CCX_VEL5\n3, 3, 3, 1.\n*END STEP" in steps[3]
    assert _amplitude(body, "ABQ2CCX_VEL5") == [(0.0, 2.0), (1.0, 4.0)]


def test_velocity_bc_ramp_start_does_not_depend_on_node_order():
    # node 6 shares a TOTAL TIME velocity with node 5 in step 1 and gets its own ramped one
    # in step 2; step 3 must continue it from where step 2 left it, whichever node comes first
    ends = []
    for pair in ("5, 6", "6, 5"):
        body, _, _ = convert_str(VEL_HEX + f"*Nset, nset=PAIR\n{pair}\n*Amplitude, name=A, time=TOTAL TIME"
                                           f"\n0., 0., 10., 10.\n*Step\n*Static\n0.1, 1.\n*Boundary, "
                                           f"type=VELOCITY, amplitude=A\nPAIR, 3, 3, 1.\n*End Step\n"
                                           f"*Step\n*Static\n0.1, 1.\n*Boundary, type=VELOCITY\n6, 3, 3, 5."
                                           f"\n*End Step\n*Step\n*Static\n0.1, 1.\n*End Step\n")
        ends.append([_amplitude(body, f"ABQ2CCX_VEL{i}")[-1] for i in (2, 3, 4, 5)])
    # step 2: node 6 ramps 1 -> 5 (0.5 -> 3.5), node 5 follows A (0.5 -> 2); step 3: node 5
    # follows A (-> 4.5), node 6 holds 5 (3.5 -> 8.5)
    assert ends[0] == ends[1] == [(1.0, 3.5), (1.0, 2.0), (1.0, 4.5), (1.0, 8.5)]


def test_velocity_bc_unreadable_lines_and_amplitudes():
    for deck in (VEL_HEX + "*Step\n*Static\n*Boundary, type=VELOCITY\nTOP, , 3, 1.\n*End Step\n",
                 VEL_HEX + "*Boundary, type=VELOCITY\nTOP, , 3, 0.\n*Step\n*Static\n*End Step\n",
                 VEL_HEX + "*Step\n*Static\n*Boundary, type=VELOCITY, user\nTOP, FOO\n*End Step\n"):
        body, _, _ = convert_str(deck)                       # commented, not a crash
        assert "** [abq2ccx] not converted: TOP, " in body
    # an amplitude another card also names (FILM AMPLITUDE=) is kept
    body, conv, _ = convert_str(VEL_HEX + "*Amplitude, name=A\n0., 0., 1., 1.\n*Step\n*Static\n"
                                          "*Boundary, type=VELOCITY, amplitude=A\nTOP, 3, 3, 1.\n"
                                          "*Film, film amplitude=A\n1, S1, 20., 5.\n*End Step\n")
    assert not conv._vel_only_amps and "\n*AMPLITUDE, NAME=A\n" in body
    # Abaqus/Explicit applies BCs at once whatever *STEP AMPLITUDE says
    body, _, rep = convert_str(VEL_HEX + "*Step, amplitude=RAMP\n*Dynamic, Explicit\n, 1.\n"
                                         "*Boundary, type=VELOCITY\nTOP, 3, 3, 1.\n*End Step\n")
    assert _amplitude(body, "ABQ2CCX_VEL1") == [(0.0, 0.0), (1.0, 1.0)]
    # too many oscillations to sample; a TOTAL TIME amplitude after a step of unknown length
    body, _, _ = convert_str(VEL_HEX + "*Amplitude, name=P, definition=PERIODIC\n1, 1e5, 0., 0.\n"
                                       "0., 1.\n*Step\n*Static\n0.1, 10.\n*Boundary, type=VELOCITY, "
                                       "amplitude=P\nTOP, 3, 3, 1.\n*End Step\n")
    assert "oscillates over a thousand times" in body
    body, _, _ = convert_str(VEL_HEX + "*Amplitude, name=A, time=TOTAL TIME\n0., 0., 10., 10.\n"
                                       "*Step\n*Static, riks\n0.1, 1.\n*Cload\nTOP, 3, 1.\n*End Step\n"
                                       "*Step\n*Static\n*Boundary, type=VELOCITY, amplitude=A\n"
                                       "TOP, 3, 3, 1.\n*End Step\n")
    assert "TIME=TOTAL TIME amplitude after a step whose time period is unknown" in body


def test_velocity_bc_in_frequency_step_keeps_the_constraint():
    deck = VEL_HEX + "*Step\n*Frequency\n5\n*Boundary, type=VELOCITY\nTOP, 3, 3, 0.\n*End Step\n"
    body, _, _ = convert_str(deck)
    assert "*BOUNDARY\nTOP, 3, 3\n" in body and "ABQ2CCX_VEL" not in body


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
