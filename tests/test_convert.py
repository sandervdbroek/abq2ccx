#!/usr/bin/env python3
"""Regression tests for abq2ccx.

Run directly:   python tests/test_convert.py
or with pytest: pytest tests/

The checks convert each bundled example deck and assert that the resulting
CalculiX model is referentially consistent (every element node, set member and
load/section reference resolves) plus a handful of conversion-specific
expectations.
"""

import io
import math
import os
import re
import shutil
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
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
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
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
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
    assert "PLATE, P, 0.005\nABQ2CCX_TOP_PLATE, P, -0.005" in body   # *DSLOAD -> both faces
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


def test_heat_transfer_plane_and_axisymmetric_elements():
    # DC2D* / DCAX* run as ccx's plane / axisymmetric element of the same interpolation, the
    # temperature uniform through its one-element-thick expansion (NAFEMS T2, T3: DC2D8 as
    # CPS8 gives Abaqus' temperatures)
    quad = "*Node\n1,1.,0.\n2,2.,0.\n3,2.,1.\n4,1.,1.\n5,1.5,0.\n6,2.,.5\n7,1.5,1.\n8,1.,.5\n"
    for abq, ccx, conn in (("DC2D4", "CPS4", "1,1,2,3,4"), ("DC2D8", "CPS8", "1,1,2,3,4,5,6,7,8"),
                           ("DCAX4", "CAX4", "1,1,2,3,4"), ("DCAX8", "CAX8", "1,1,2,3,4,5,6,7,8")):
        body, conv, rep = convert_str(quad + f"*Element, type={abq}, elset=E\n{conn}\n")
        assert f"*ELEMENT, TYPE={ccx}\n{conn.replace(',', ', ')}" in body, body
        assert conv.reduced_physics == [] and rep.n_warnings == 0 and "same solution" in rep.text()


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
    # ccx reads an *EQUATION's DOFs in a node's *TRANSFORM axes (here local 1 = y, 2 = -x,
    # 3 = z): the global u_9 = u_2 is written along them (test_mpc_pin_on_a_transformed_node...)
    body, _, rep = convert_str(HEX + "*Node\n9,2,0,0\n*Nset,nset=T9\n9\n*Transform, nset=T9\n"
                               "0.,1.,0.,-1.,0.,0.\n*MPC\nPIN, 9, 2\n")
    assert _equation_terms(body) == [[(9, 1, 1.), (2, 2, -1.)], [(9, 2, 1.), (2, 1, 1.)],
                                     [(9, 3, 1.), (2, 3, -1.)]]
    assert "Abaqus makes the global displacements equal" in rep.text() and rep.n_warnings == 0


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


def test_mpc_lines_ccx_reads_get_one_card_each():
    # ccx reads one MPC per *MPC card — its type from the first line, every later node as a
    # further node of it — and reserves a BEAM MPC's extra node once per card (probed: two
    # BEAM lines in one card stop ccx, 'increase nk_'; a second PLANE / STRAIGHT line's
    # nodes silently land on the first line's plane / line).  So each LINK node pair under
    # NLGEOM — of several lines, or of one line pairing node sets — and each PLANE /
    # STRAIGHT line gets a card of its own, in deck order
    deck = ("*Node\n1,0,0,0\n2,3,4,0\n11,0,0,10\n12,3,4,10\n21,0,0,20\n22,3,4,20\n"
            "31,0,0,-2\n32,1,0,-2\n33,0,1,-2\n34,.3,.3,-2\n41,0,0,-5\n42,1,0,-5\n43,.5,0,-5\n"
            "*Nset,nset=A\n22, 12\n*Nset,nset=B\n21, 11\n*MPC\nLINK, 2, 1\nPLANE, 31, 32, 33, 34\n"
            "LINK, A, B\nSTRAIGHT, 41, 42, 43\n*Step, nlgeom=YES\n*Static\n*End Step\n")
    body, _, _ = convert_str(deck)
    lines = _live(body)
    cards = [lines[i + 1:i + 3] for i, l in enumerate(lines) if l == "*MPC"]
    assert [c[0] for c in cards] == ["BEAM, 2, 1", "PLANE, 31, 32, 33, 34", "BEAM, 12, 11",
                                     "BEAM, 22, 21", "STRAIGHT, 41, 42, 43"]
    assert all(c[1].startswith("*") for c in cards)                 # one line per card


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


def test_rigid_element_without_body_becomes_a_skin():
    # Abaqus requires a *RIGID BODY for rigid elements; a mesh-only deck without one still
    # converts (to a skin, warned) so that ccx accepts the mesh
    deck = "*NODE\n1,0.,0.,0.\n2,1.,0.,0.\n3,1.,1.,0.\n*ELEMENT, TYPE=R3D3, ELSET=R\n1,1,2,3\n"
    body, _, rep = convert_str(deck)
    assert "*ELEMENT, TYPE=R3D3" not in body and "*ELEMENT, TYPE=C3D6\n1, " in body
    assert any("belong to no *RIGID BODY" in m for _, m in rep.entries)


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
    _, conv, rep = convert_str(deck)
    assert conv.geom.nodes[1][0] == 6.0 and "resolved 2 parameter(s)" in rep.text()


def test_unresolved_parameter_is_reported():
    # an expression the converter cannot evaluate is substituted as written, warned, and not
    # counted as resolved
    deck = ("*PARAMETER\na = 2.0\nb = foo(a)\nc = a * 3\n*NODE\n1, <a>, 0., <c>\n2, <b>, 0., 0.\n"
            "*ELEMENT, TYPE=MASS, ELSET=E\n1, 1\n")
    _, conv, rep = convert_str(deck)
    assert conv.geom.nodes[1] == (2.0, 0.0, 6.0) and 2 not in conv.geom.nodes
    assert "resolved 2 parameter(s)" in rep.text() and "*PARAMETER: b could not be evaluated" in rep.text()


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


def test_friction_coefficient_with_fortran_exponent():
    # 3.D-1 is 0.3 (read with float(), it made the pair frictionless with only a note)
    body, _, rep = convert_str("*SURFACE INTERACTION, NAME=SI\n*FRICTION\n3.D-1,\n")
    assert "*FRICTION\n0.3," in body and "no positive coefficient" not in rep.text()


def test_nfill_unequal_bounding_sets():
    # *NFILL whose two bounding node sets differ in length fills the common (zip)
    # pairs instead of skipping — a real deck may carry one spurious extra edge node.
    deck = ("*NODE\n1,0.,0.\n3,0.,2.\n101,4.,0.\n104,4.,3.\n"
            "*NGEN,NSET=LEFT\n1,3\n"          # -> nodes 1,2,3   (3 nodes)
            "*NGEN,NSET=RIGHT\n101,104\n"     # -> nodes 101..104 (4 nodes, one extra)
            "*NFILL\nLEFT,RIGHT,2,50\n")      # 2 intervals, node increment 50
    _, conv, _ = convert_str(deck)
    assert {51, 52, 53} <= set(conv.geom.nodes)   # interior of the 3 common pairs


def test_nfill_set_holds_its_bounding_nodes():
    # Abaqus 2017 Keywords *NFILL: NSET gets "the nodes created by this operation (including
    # the bounding nodes)", so a fill between two such sets reaches their edge rows too (the
    # NAFEMS FV52 C3D8I and T4 DC3D20 decks lost them: a nonpositive jacobian in ccx). The
    # bounding sets pair in sorted order, as Abaqus node sets are sorted (X2 runs backwards).
    deck = ("*NODE\n1,0.,0.,0.\n3,2.,0.,0.\n201,0.,2.,0.\n203,2.,2.,0.\n"
            "*NGEN,NSET=X1\n1,3\n*NGEN,NSET=X2\n203,201,-1\n*NFILL,NSET=BASE\nX1,X2,2,100\n"
            "*NCOPY,OLD SET=BASE,NEW SET=TOP,CHANGE NUMBER=2000,SHIFT\n0.,0.,1.\n0.,0.,0.,0.,0.,1.,0.\n"
            "*NFILL,NSET=ALL\nBASE,TOP,2,1000\n")
    _, conv, _ = convert_str(deck)
    g = conv.geom
    assert sorted(set(g.nset("BASE"))) == [1, 2, 3, 101, 102, 103, 201, 202, 203]
    assert all(g.nodes[n + 1000] == (g.nodes[n][0], g.nodes[n][1], 0.5) for n in g.nset("BASE"))
    assert g.nodes[102] == (1.0, 1.0, 0.0) and g.nodes[101] == (0.0, 1.0, 0.0)
    assert len(set(g.nset("ALL"))) == 27


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


def test_mesh_generation_skips_unreadable_records():
    # a non-numeric field (here an undefined <parameter>) in a mesh-generation card skips that
    # record or card with a warning, as on *NODE, instead of aborting the conversion
    ends = "*NODE\n1, 0., 0., 0.\n2, 1., 0., 0.\n10, 9., 0., 0.\n*ELEMENT, TYPE=T3D2, ELSET=E\n1, 1, 2\n"
    for kw, card in (("*NGEN record", "*NGEN, NSET=L\n1, 10, <n>\n"),
                     ("*NFILL record", "*NSET, NSET=A\n1\n*NSET, NSET=B\n10\n*NFILL\nA, B, <n>, 1\n"),
                     ("*NCOPY card", "*NSET, NSET=A\n1, 2\n*NCOPY, OLD SET=A, CHANGE NUMBER=100, SHIFT\n"
                                     "<dx>, 0., 0.\n"),
                     ("*ELGEN record", "*ELGEN, ELSET=E\n1, <n>, 1, 1\n"),
                     ("*ELCOPY card", "*ELCOPY, ELEMENT SHIFT=<k>, OLD SET=E, SHIFT NODES=1\n")):
        _, conv, rep = convert_str(ends + card + "*NGEN\n1, 10, 0\n")
        assert f"Skipped a {kw} with non-numeric data" in rep.text(), (kw, rep.text())
        assert sorted(conv.geom.nodes) == [1, 2, 10] and list(conv.geom.elements) == [1]
        assert any("non-numeric" in r for r in conv.reduced_physics)
        assert "with increment 0 generated no nodes" in rep.text()


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


JC_MATERIAL = ("*Material, name=TI\n*Elastic\n110000., 0.3\n*Plastic\n900., 0.\n1100., 1.\n"
               "*Damage Initiation, criterion=JOHNSON COOK\n"
               "-0.09, 0.25, 0.5, 0.014, 3.87, 1878., 293., 1.\n")
JC_STEP = "*Solid Section, elset=EALL, material=TI\n*Step, nlgeom\n*Static\n0.1, 1.\n*End Step\n"


def test_damage_initiation_criteria_ccx_cannot_run_are_commented():
    # ccx 2.23 knows RICE TRACEY and JOHNSON COOK only and stops on any other criterion.
    # Without *DAMAGE EVOLUTION Abaqus only evaluates the criterion (output), so commenting
    # it out is exact (a note); with one, the evolution is lost anyway (a warning).
    # (a section uses the material: the cards of a material nothing uses change nothing)
    plain = HEX + ("*Material, name=m\n*Elastic\n210000., 0.3\n"
                   "*Damage Initiation, criterion=DUCTILE\n0.1, 0.0, 0.0\n")
    section = "*Solid Section, elset=EALL, material=m\n"
    body, _, rep = convert_str(plain + section)
    di = [l for l in body.splitlines() if "DAMAGE INITIATION" in l.upper()]
    assert di and all(l.lstrip().startswith("**") for l in di)
    assert any(lvl == "NOTE" and "CRITERION=DUCTILE (material m)" in m and "only that output"
               in m for lvl, m in rep.entries)
    body, _, rep = convert_str(plain + "*Damage Evolution, type=DISPLACEMENT\n0.001,\n" + section)
    assert all(l.lstrip().startswith("**") for l in body.splitlines() if "DAMAGE" in l.upper())
    assert any(lvl == "WARNING" and "CRITERION=DUCTILE" in m and "*DAMAGE EVOLUTION" in m
               for lvl, m in rep.entries)


def test_damage_initiation_johnson_cook_kept_with_ccx_second_line():
    # Abaqus' Johnson-Cook data (d1-d5, melting and transition temperature, reference strain
    # rate) are ccx's first line; ccx wants a second, the damage at which it deletes the
    # element (which crashes 2.23): 1E30 keeps the criterion an output, as in Abaqus.
    body, _, rep = convert_str(HEX + JC_MATERIAL + JC_STEP)
    lines = body.splitlines()
    i = lines.index("*DAMAGE INITIATION, CRITERION=JOHNSON COOK")
    assert lines[i + 1] == "-0.09, 0.25, 0.5, 0.014, 3.87, 1878., 293., 1."
    assert lines[i + 2] == "1.E30"
    assert any("1E30 there keeps every element" in m for _, m in rep.entries)
    # without temperature dependence (d5 = 0, temperatures blank) ccx still wants the melting
    # temperature above the transition one
    body, _, _ = convert_str(HEX + JC_MATERIAL.replace("3.87, 1878., 293., 1.", "0., , , 1.")
                             + JC_STEP)
    assert "-0.09, 0.25, 0.5, 0.014, 0., 1., 0., 1." in body.splitlines()
    # an output request for Abaqus' Johnson-Cook criterion reads ccx's indicator
    body, _, _ = convert_str(HEX + JC_MATERIAL + JC_STEP.replace(
        "*End Step", "*El Print, elset=EALL\nPEEQ, JCCRT\n*End Step"))
    assert "PEEQ, DUCT" in body.splitlines()


def test_damage_initiation_johnson_cook_commented_where_ccx_misreads_it():
    def kept(deck):
        return "*DAMAGE INITIATION, CRITERION=JOHNSON COOK" in convert_str(deck)[0].splitlines()
    assert kept(HEX + JC_MATERIAL + JC_STEP)
    # ccx 2.23 gives every *DAMAGE INITIATION card to the deck's last *MATERIAL (probed)
    other = "*Material, name=STEEL\n*Elastic\n210000., 0.3\n"
    assert kept(HEX + other + JC_MATERIAL + JC_STEP)
    assert not kept(HEX + JC_MATERIAL + other + JC_STEP)
    _, _, rep = convert_str(HEX + JC_MATERIAL + other + JC_STEP)
    assert any("deck's last *MATERIAL (STEEL)" in m for _, m in rep.entries)
    # ... evaluates it only for a plastic material, in nonlinear *STATIC / *DYNAMIC steps
    assert not kept(HEX + JC_MATERIAL.replace("*Plastic\n900., 0.\n1100., 1.\n", "") + JC_STEP)
    assert not kept(HEX + JC_MATERIAL + JC_STEP + "*Step\n*Frequency\n5\n*End Step\n")
    assert not kept(HEX + JC_MATERIAL + JC_STEP.replace("*Step, nlgeom", "*Step, perturbation"))
    assert not kept(HEX + JC_MATERIAL)                                   # no step at all
    # ... and reads one card: of two Johnson-Cook cards the later one is kept
    body, _, _ = convert_str(HEX + JC_MATERIAL + "*Damage Initiation, criterion=JOHNSON COOK\n"
                                                 "0.2, 0., 0., 0., 0., 1000., 20., 1.\n" + JC_STEP)
    live = [l for l in body.splitlines() if not l.startswith("**")]
    assert live.count("*DAMAGE INITIATION, CRITERION=JOHNSON COOK") == 1
    assert "0.2, 0., 0., 0., 0., 1000., 20., 1." in live


def test_elastic_young_modulus_only_gets_zero_poisson():
    # Abaqus reads an omitted Poisson's ratio as 0; ccx stops: 'not enough constants'
    body, _, _ = convert_str("*Material, name=m\n*Elastic\n 3e+07, \n")
    assert "*ELASTIC\n3e+07, 0." in body
    body, _, _ = convert_str("*Material, name=m\n*Elastic\n3e+07, , 20.\n4e+07\n")
    assert "*ELASTIC\n3e+07, , 20.\n4e+07, 0." in body


def test_traction_elastic_of_unused_material_commented():
    # a cohesive traction-separation stiffness: ccx reads it as isotropic E, nu and stops
    deck = (HEX + "*Material, name=STEEL\n*Elastic\n210000., 0.3\n*Material, name=GLUE\n"
            "*Elastic, type=TRACTION\n8.5e+11, 8.5e+11, 8.5e+11\n"
            "*Solid Section, elset=EALL, material=STEEL\n")
    body, _, rep = convert_str(deck)
    assert "** *ELASTIC, TYPE=TRACTION" in body and "\n*ELASTIC, TYPE=TRACTION" not in body
    assert any(lvl == "NOTE" and "No section uses material GLUE" in m for lvl, m in rep.entries)
    body, _, _ = convert_str(deck.replace("material=STEEL\n", "material=GLUE\n"))
    assert "\n*ELASTIC, TYPE=TRACTION" in body          # used: left for the cohesive warning


def test_boundary_on_inactive_unknown_dof_dropped():
    # DOF 9 (electric potential) exists only on piezoelectric / electrical elements (and user
    # elements); elsewhere Abaqus ignores the BC, while ccx stops: 'unknown DOF'
    deck = HEX + ("*Nset, nset=TOP\n5,6,7,8\n*Step\n*Static\n*Boundary\nTOP, 9, 9, 500.\n"
                  "TOP, 1, 9\n*End Step\n")
    body, _, rep = convert_str(deck)
    assert "TOP, 9, 9" not in body and "TOP, 1, 6\n" in body and "TOP, 8, 8" not in body
    assert any("DOF 9 (electric potential) dropped" in m for _, m in rep.entries)
    body, _, _ = convert_str(deck.replace("TYPE=C3D8", "TYPE=C3D8E"))
    assert "TOP, 9, 9, 500." in body


def test_boundary_on_dof8_dropped_where_the_ccx_model_has_none():
    # ccx 2.23 reads DOF 8 as its DOF 4 (probed): the rotation about x of a shell or beam node,
    # held or prescribed without a message; a crash on plane nodes; nothing on solid nodes
    step = "*Step\n*Static\n*Boundary\nTOP, 8, 8, 0.5\nTOP, 1, 8\n*Cload\nTOP, 3, 1.\n*End Step\n"
    deck = HEX + "*Nset, nset=TOP\n5,6,7,8\n" + step
    body, _, rep = convert_str(deck)                   # no element has DOF 8: Abaqus ignores it
    assert "TOP, 8, 8" not in body and "TOP, 1, 6\n*CLOAD" in body
    assert any(lvl == "NOTE" and "DOF 8 (pore, fluid or acoustic pressure) dropped" in m
               for lvl, m in rep.entries)
    shell = ("*Node\n1,0,0,0\n2,1,0,0\n3,1,1,0\n4,0,1,0\n*Element, type=S4, elset=P\n1,1,2,3,4\n"
             "*Material, name=m\n*Elastic\n1., 0.3\n*Shell Section, elset=P, material=m\n0.1\n"
             "*Nset, nset=TOP\n3, 4\n")
    body, _, _ = convert_str(shell + step)              # it would hold the shell's rotation
    assert "TOP, 8, 8" not in body and "TOP, 1, 6\n*CLOAD" in body
    # a pore-pressure element loses DOF 8 with its P suffix: the BC goes with it (warned)
    body, _, rep = convert_str(deck.replace("TYPE=C3D8", "TYPE=C3D8P"))
    assert "TOP, 8, 8" not in body and "TOP, 1, 6\n*CLOAD" in body
    assert any(lvl == "WARNING" and "DOF 8 (pore pressure) dropped" in m for lvl, m in rep.entries)
    # elements emitted with their DOF 8 keep the BC (here ccx's CFD element)
    body, _, _ = convert_str(HEX + "*Element, type=F3D4, elset=F\n2, 1, 2, 3, 5\n"
                                   "*Nset, nset=TOP\n5,6,7,8\n" + step)
    assert "TOP, 8, 8, 0.5" in body
    assert all(A.keeps_dof8(t) for t in ("AC3D8", "ACIN3D4", "ASI3D4", "F3D4", "FAX2", "FLINK",
                                          "FPC3D2", "U12", "VU1"))
    assert not any(A.keeps_dof8(t) for t in ("C3D8P", "CPE8P", "CAX8RP", "S4R", "FRAME3D"))
    # the default-amplitude planner leaves the line out as handle_boundary does
    dyn = HEX + ("*Material, name=m\n*Elastic\n1000., 0.3\n*Density\n1e-3\n*Solid Section, "
                 "elset=EALL, material=m\n*Nset, nset=TOP\n5,6,7,8\n*Step\n*Dynamic\n0.1, 1.\n"
                 "*Boundary\nTOP, 3, 3, 0.1\nTOP, 8, 8, 5.\nTOP, 1, 1, 0.01\n*End Step\n")
    body, _, _ = convert_str(dyn)
    assert "*BOUNDARY, AMPLITUDE=RAMP12357111317\nTOP, 3, 3, 0.1\nTOP, 1, 1, 0.01\n" in body


def test_fluid_cavity_pressure_bc_dropped_and_its_step_unloaded():
    # DOF 8 of a *FLUID CAVITY reference node is the cavity pressure: in Abaqus the BC loads
    # the cavity surface; ccx has no fluid cavity and ignores DOF 8 on a node of no element
    deck = HEX + ("*Node\n99, 0.5, 0.5, 0.5\n*Surface, type=ELEMENT, name=CAVS\nEALL, S1\n"
                  "*Fluid Behavior, name=WATER\n*Fluid Density\n1.\n*Fluid Cavity, name=CAV, "
                  "behavior=WATER, refnode=99, surface=CAVS\n*Step\n*Static\n*Boundary\n"
                  "99, 8, 8, 0.1\n*End Step\n")
    body, conv, rep = convert_str(deck)
    assert "99, 8, 8" not in body and conv.unloaded_steps == [1]
    assert any(lvl == "WARNING" and "*FLUID CAVITY CAV dropped" in m and "LOST" in m
               for lvl, m in rep.entries)


def test_inactive_dof_lines_leave_no_empty_or_split_card():
    # the default-amplitude planner sees a card's lines as handle_boundary keeps them: a line
    # on a DOF no element has neither splits the ramped card nor leaves an empty one behind
    mat = ("*Material, name=m\n*Elastic\n1000., 0.3\n*Density\n1e-3\n*Solid Section, elset=EALL, "
           "material=m\n*Nset, nset=TOP\n5,6,7,8\n*Nset, nset=BOT\n1,2,3,4\n*Boundary\nBOT, 1, 3\n")
    body, _, _ = convert_str(HEX + mat + "*Step\n*Dynamic\n0.1, 1.\n*Boundary\nTOP, 3, 3, 0.1\n"
                                         "TOP, 9, 9, 5.\nTOP, 1, 1, 0.01\n*End Step\n")
    step = body[body.index("*DYNAMIC"):]
    assert "*BOUNDARY, AMPLITUDE=RAMP12357111317\nTOP, 3, 3, 0.1\nTOP, 1, 1, 0.01\n*NODE FILE" in step
    body, _, _ = convert_str(HEX + mat + "*Step\n*Dynamic, Explicit\n, 1.\n*Boundary\nTOP, 3, 3, 0.1\n"
                                         "TOP, 9, 9, 5.\n*End Step\n")
    assert "*BOUNDARY\nTOP, 3, 3\n*NODE FILE" in body
    body, _, _ = convert_str(HEX + mat + "*Step\n*Static\n*Boundary\nTOP, 9, 9, 5.\n*Cload\nTOP, 3, 1.\n"
                                         "*End Step\n")
    step = body[body.index("*STATIC"):]
    assert "*BOUNDARY" not in step                        # the card had nothing else
    body, _, _ = convert_str(HEX + mat + "*Step\n*Static\n*Boundary, op=NEW\nTOP, 9, 9, 5.\n*End Step\n")
    assert "*BOUNDARY, OP=NEW\n" in body                  # but OP=NEW still removes BOT's BC


def test_rotation_bc_on_truss_nodes_dropped():
    # truss nodes have no rotations: Abaqus ignores XASYMM's DOF 4 there, ccx stops in gen3dboun
    deck = ("*Node\n1, 0., 0.\n2, 1., 1.\n3, 2., 0.\n*Element, type=T2D2, elset=T\n1, 1, 2\n2, 2, 3\n"
            "*Material, name=m\n*Elastic\n1., 0.3\n*Solid Section, elset=T, material=m\n1.\n"
            "*Boundary\n3, XASYMM\n1, PINNED\n*Step\n*Static\n*Cload\n2, 2, -1.\n*End Step\n")
    body, _, rep = convert_str(deck)
    assert "3, 2, 3" in body and "3, 4, 4" not in body
    assert any("only belong to truss elements" in m for _, m in rep.entries)


def test_shell_offset_labels_become_numbers():
    # ccx takes OFFSET only as a number; Abaqus' SPOS / SNEG are 0.5 / -0.5 in both codes
    shell = ("*Node\n1,0,0,0\n2,1,0,0\n3,1,1,0\n4,0,1,0\n*Element, type=S4R, elset=P\n1,1,2,3,4\n"
             "*Material, name=m\n*Elastic\n1., 0.3\n")
    for label, value in (("SNEG", "-0.5"), ("spos", "0.5")):
        body, _, _ = convert_str(shell + f"*Shell Section, elset=P, material=m, offset={label}\n1.\n")
        assert f"*SHELL SECTION, ELSET=P, MATERIAL=m, OFFSET={value}" in body


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
    # *DSLOAD on a surface whose face is neither S1..S6 nor a shell / membrane side (here
    # SPOS on a solid) cannot become a ccx Px label; it must warn rather than silently emit
    # a bare 'P' that ccx rejects.
    deck = HEX + ("*Elset, elset=e\n1\n*Surface,type=element,name=sf\ne, SPOS\n*Step\n*Static\n"
                  "*Dsload\nsf, P, 5.0\n*End Step\n")
    _, _, rep = convert_str(deck)
    assert "px equivalent" in rep.text().lower()


def test_shell_and_membrane_pressure_sides():
    # Abaqus pushes a surface pressure against the surface normal (SPOS along -n, SNEG along
    # +n) and an element-based *DLOAD P along +n; ccx's *DLOAD P on a shell and P1 on a
    # membrane push along +n, and ccx stops on P on a membrane (probed on 2.23).  Half of it
    # goes on the top face (S2), where a pressure pushes along -n (_plan_sheet_pressure)
    def card(typ, face=None):
        load = (f"*Surface,type=element,name=sf\ne, {face}\n*Step\n*Static\n*Dsload\nsf, P, 5.0\n"
                if face else "*Step\n*Static\n*Dload\ne, P, 5.0\n")
        deck = (f"*Node\n1,0.,0.,0.\n2,1.,0.,0.\n3,1.,1.,0.\n4,0.,1.,0.\n*Element,type={typ},elset=e\n"
                f"1,1,2,3,4\n" + load + "*End Step\n")
        body, _, rep = convert_str(deck)
        assert _card_at(body, "*SURFACE, NAME=ABQ2CCX_TOP_E, TYPE=ELEMENT") == ["e, S2"]
        return _card_at(body, "*DLOAD"), rep
    assert card("S4", "SPOS")[0] == ["e, P, -2.5", "ABQ2CCX_TOP_E, P, 2.5"]
    assert card("S4", "SNEG")[0] == ["e, P, 2.5", "ABQ2CCX_TOP_E, P, -2.5"]
    assert card("S4")[0] == ["e, P, 2.5", "ABQ2CCX_TOP_E, P, -2.5"]
    assert card("M3D4", "SPOS")[0] == ["e, P1, -2.5", "ABQ2CCX_TOP_E, P, 2.5"]
    assert card("M3D4", "SNEG")[0] == ["e, P1, 2.5", "ABQ2CCX_TOP_E, P, -2.5"]
    assert card("M3D4")[0] == ["e, P1, 2.5", "ABQ2CCX_TOP_E, P, -2.5"]
    for typ, face in (("S4", "SPOS"), ("S4", None), ("M3D4", None)):
        assert card(typ, face)[1].n_warnings == 0, card(typ, face)[1].text()


SHEET_PAIR = ("*Node\n1,0.,0.,0.\n2,1.,0.,0.\n3,1.,1.,0.\n4,0.,1.,0.\n5,2.,0.,0.\n6,2.,1.,0.\n"
              "*Element,type=S4,elset=E\n1,1,2,3,4\n*Element,type=S4,elset=F\n2,2,5,6,3\n"
              "*Elset, elset=BOTH\nE, F\n*Material, name=M\n*Elastic\n1e6, 0.3\n")


def test_sheet_pressure_split_by_offset():
    # Abaqus loads a shell's reference surface, ccx 2.23 only the bottom face of its expanded
    # solid: 0.5 - o of the pressure goes there, 0.5 + o on the top face (S2) for OFFSET o —
    # no first moment about the reference surface (_plan_sheet_pressure)
    def card(off, load="*Dload\nE, P, 4."):
        sec = f"*Shell Section, elset=BOTH, material=M{off}\n0.1\n*Surface, name=SF\nE, SPOS\n"
        body, _, rep = convert_str(SHEET_PAIR + sec + "*Step\n*Static\n" + load + "\n*End Step\n")
        return _card_at(body, "*DLOAD"), body, rep
    assert card(", offset=SPOS")[0] == ["ABQ2CCX_TOP_E, P, -4."]       # the top face is the reference
    assert card(", offset=SPOS", "*Dsload\nSF, P, 4.")[0] == ["ABQ2CCX_TOP_E, P, 4."]
    lines, body, _ = card(", offset=SNEG")
    assert lines == ["E, P, 4."] and "ABQ2CCX_TOP" not in body        # the bottom face is
    assert card(", offset=0.25")[0] == ["E, P, 1.", "ABQ2CCX_TOP_E, P, -3."]
    lines, body, _ = card("")
    assert lines == ["E, P, 2.", "ABQ2CCX_TOP_E, P, -2."]
    assert _card_at(body, "*SURFACE, NAME=ABQ2CCX_TOP_E, TYPE=ELEMENT") == ["E, S2"]
    assert body.index("*SURFACE, NAME=ABQ2CCX_TOP_E") < body.index("*STEP")
    # an offset that is no number (a distribution): the one-face load stays, warned
    lines, body, rep = card(", offset=OFFDIST")
    assert lines == ["E, P, 4."] and "OFFSET is not a number" in rep.text()
    # one load set over shells of two offsets: an element set and a top surface per offset
    sec = ("*Shell Section, elset=E, material=M\n0.1\n*Shell Section, elset=F, material=M, offset=SPOS\n"
           "0.1\n*Surface, name=SG\nBOTH, SNEG\n")
    body, _, _ = convert_str(SHEET_PAIR + sec + "*Step\n*Static\n*Dsload\nSG, P, 1.1\n*End Step\n")
    assert _card_at(body, "*DLOAD") == ["ABQ2CCX_P1_BOTH, P, 0.55", "ABQ2CCX_TOP_BOTH_1, P, -0.55",
                                        "ABQ2CCX_TOP_BOTH_2, P, -1.1"]
    g = reparse(body)
    assert g.elsets["ABQ2CCX_P1_BOTH"] == [1] and g.elsets["ABQ2CCX_P2_BOTH"] == [2] and not dangling_refs(g)
    assert _card_at(body, "*SURFACE, NAME=ABQ2CCX_TOP_BOTH_2, TYPE=ELEMENT") == ["ABQ2CCX_P2_BOTH, S2"]


def test_sheet_pressure_split_across_steps_and_names():
    # Abaqus' *DSLOAD, OP=NEW keeps the *DLOAD pressure, ccx's *DLOAD, OP=NEW removes it: both
    # of its faces are given again
    deck = (SHEET_PAIR + "*Shell Section, elset=BOTH, material=M\n0.1\n*Surface, name=SF\nF, SNEG\n"
            "*Step\n*Static\n*Dload\nE, P, 2.\n*Dsload\nSF, P, 3.\n*End Step\n"
            "*Step\n*Static\n*Dsload, op=new\nSF, P, 5.\n*End Step\n")
    body, conv, _ = convert_str(deck)
    step2 = body.split("*STEP")[2]
    assert "*DLOAD, OP=NEW\nF, P, 2.5\nABQ2CCX_TOP_F, P, -2.5\n" in step2.upper()
    assert "\nE, P, 1.\nABQ2CCX_TOP_E, P, -1.\n" in step2 and not conv.unloaded_steps
    # a zero pressure removes the load (Abaqus), on both faces
    body, _, _ = convert_str(deck.replace("*Dsload, op=new\nSF, P, 5.", "*Dload\nE, P, 0."))
    assert "\nE, P, 0.\nABQ2CCX_TOP_E, P, 0.\n" in body.split("*STEP")[2]
    # a set name too long for ccx's 80 characters with the prefix: cut (_fresh_name)
    long = "S" * 70
    body, _, _ = convert_str(SHEET_PAIR.replace("elset=E\n", f"elset={long}\n") +
                             f"*Shell Section, elset={long}, material=M\n0.1\n*Step\n*Static\n*Dload\n"
                             f"{long}, P, 2.\n*End Step\n")
    top = ("ABQ2CCX_TOP_" + long)[:80]
    assert _card_at(body, "*DLOAD") == [f"{long}, P, 1.", f"{top}, P, -1."]
    assert _card_at(body, f"*SURFACE, NAME={top}, TYPE=ELEMENT") == [f"{long}, S2"]


def test_sheet_pressure_surface_lines_last():
    # ccx 2.23 never resets dloads.f's 'surface' flag within a *DLOAD card: an element-set line
    # after a surface line is read as a surface (its load lost or misplaced, or ccx crashes;
    # probed), so every card lists the top-face surfaces last
    sec = "*Shell Section, elset=BOTH, material=M\n0.1\n*Surface, name=SA\nE, SNEG\n*Surface, name=SB\nF, SNEG\n"
    deck = SHEET_PAIR + sec + "*Step\n*Static\n{}\n*End Step\n"
    want = ["E, P, 0.5", "F, P, 0.5", "ABQ2CCX_TOP_E, P, -0.5", "ABQ2CCX_TOP_F, P, -0.5"]
    for load in ("*Dload\nE, P, 1.\nF, P, 1.", "*Dsload\nSA, P, 1.\nSB, P, 1."):
        body, _, _ = convert_str(deck.format(load))
        assert _card_at(body, "*DLOAD") == want, load
    # a set over two offsets: both bottom-face lines first
    body, _, _ = convert_str(SHEET_PAIR + "*Shell Section, elset=E, material=M\n0.1\n*Shell Section, "
                             "elset=F, material=M, offset=-0.25\n0.1\n*Step\n*Static\n*Dload\nBOTH, P, 1.\n*End Step\n")
    assert _card_at(body, "*DLOAD") == ["ABQ2CCX_P1_BOTH, P, 0.5", "ABQ2CCX_P2_BOTH, P, 0.75",
                                        "ABQ2CCX_TOP_BOTH_1, P, -0.5", "ABQ2CCX_TOP_BOTH_2, P, -0.25"]
    # the loads given again after ccx's *DLOAD, OP=NEW (_flush_dloads): one card, surfaces last
    body, _, _ = convert_str(deck.format("*Dload\nE, P, 1.\n*Dload\nF, P, 1.\n*Dsload\nSA, P, 1.").replace(
        "*End Step\n", "*End Step\n*Step\n*Static\n*Dsload, op=new\nSB, P, 1.\n*End Step\n"))
    step2 = body.split("*STEP")[2]
    assert step2.split("removed them)\n")[1].startswith("*DLOAD\n" + "\n".join(want) + "\n"), step2


def test_sheet_pressure_names_and_whole_model():
    # generated names never collide: set K over two offsets, and a loaded set named K_1
    deck = ("*Node\n1,0.,0.,0.\n2,1.,0.,0.\n3,1.,1.,0.\n4,0.,1.,0.\n5,2.,0.,0.\n6,2.,1.,0.\n7,3.,0.,0.\n"
            "8,3.,1.,0.\n*Element,type=S4,elset=A\n1,1,2,3,4\n*Element,type=S4,elset=B\n2,2,5,6,3\n"
            "*Element,type=S4,elset=K_1\n3,5,7,8,6\n*Elset, elset=K\nA, B\n*Material, name=M\n*Elastic\n"
            "1e6, 0.3\n*Shell Section, elset=A, material=M\n0.1\n*Shell Section, elset=B, material=M, "
            "offset=0.25\n0.1\n*Shell Section, elset=K_1, material=M\n0.1\n*Step\n*Static\n*Dload\n"
            "K, P, 1.\nK_1, P, 1.\n*End Step\n")
    body, _, _ = convert_str(deck)
    surfs = [ln.split("NAME=")[1].split(",")[0] for ln in body.splitlines() if ln.startswith("*SURFACE, NAME=ABQ2CCX")]
    assert len(surfs) == 3 and len(set(surfs)) == 3, surfs
    g = reparse(body)
    assert not dangling_refs(g)
    # a pressure line without an element set loads the whole model (Abaqus): split too
    body, _, _ = convert_str(SHEET_PAIR + "*Shell Section, elset=BOTH, material=M\n0.1\n*Step\n*Static\n"
                             "*Dload\n, P, 2.\n*End Step\n")
    assert _card_at(body, "*DLOAD") == ["ABQ2CCX_ALL_ELEMENTS, P, 1.", "ABQ2CCX_TOP_ABQ2CCX_ALL_ELEMENTS, P, -1."]


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
    pts = []
    for l in lines[i + 1:]:
        if l.startswith("*"):
            break
        pts.append(tuple(float(x) for x in l.split(",")))
    assert len(pts) == 101 and pts[0] == (0.0, 0.0) and pts[-1] == (1.0, 1.0)
    assert abs(dict(pts)[0.5] - 0.5) < 1e-12                  # quintic midpoint
    assert abs(dict(pts)[0.2] - 0.05792) < 1e-9               # x^3(10-15x+6x^2) at 0.2
    # between the points the table stays within 7.2e-5 of the quintic (h^2/8 max|f''|)
    quintic = lambda x: x ** 3 * (10 - 15 * x + 6 * x * x)
    worst = max(abs(a0 + (a1 - a0) * (x - t0) / (t1 - t0) - quintic(x))
                for (t0, a0), (t1, a1) in zip(pts, pts[1:]) for x in (t0 + (t1 - t0) * k / 8
                                                                      for k in range(9)))
    assert worst < 7.3e-5, worst
    assert "sampled" in rep.text().lower()


def test_periodic_amplitude_sampled_over_the_step_time():
    # ccx has no analytic amplitudes: PERIODIC / DECAY / MODULATED become points over the step
    # time (NAFEMS T3: T = 100 sin(pi t / 40) at one end, its first data line without A0)
    heat = ("*Material, name=M\n*Conductivity\n35.\n*Density\n7200.\n*Specific Heat\n440.5\n"
            "*Solid Section, elset=EALL, material=M\n")
    amp = "*Amplitude, name=SINE, definition=PERIODIC\n1, 0.07854, 0.\n0., 100.\n"
    step = "*Step\n*Heat Transfer\n1., 32.\n*Boundary, amplitude=SINE\n1, 11, 11, 1.\n*End Step\n"
    body, conv, rep = convert_str(HEX + heat + amp + step)
    pts = [tuple(float(x) for x in pair.split(","))
           for ln in _card(body, "*AMPLITUDE, NAME=SINE") for pair in re.findall(r"[^,]+,[^,]+", ln)]
    assert pts[0] == (0.0, 0.0) and pts[-1][0] == 32.0 and len(pts) == 81    # 0.4 apart
    assert max(abs(a - 100.0 * math.sin(0.07854 * t)) for t, a in pts) < 1e-6
    mid = max(abs(0.5 * (a0 + a1) - 100.0 * math.sin(0.07854 * 0.5 * (t0 + t1)))
              for (t0, a0), (t1, a1) in zip(pts, pts[1:]))
    assert mid < 100.0 * 1.3e-4 and "sampled into 81 time/amplitude points" in rep.text()
    assert conv.reduced_physics == []
    # DECAY over the longest step (here 2.0); without a step there is no time to sample: commented
    decay = "*Amplitude, name=D, definition=DECAY\n1., 2., 0.5, 0.25\n"
    body, _, _ = convert_str(HEX + heat + decay + step.replace("1., 32.", "1., 2.")
                             .replace("amplitude=SINE", "amplitude=D"))
    pts = [tuple(float(x) for x in pair.split(","))
           for ln in _card(body, "*AMPLITUDE, NAME=D") for pair in re.findall(r"[^,]+,[^,]+", ln)]
    assert pts[-1][0] == 2.0 and abs(dict(pts)[0.5] - 3.0) < 1e-12
    assert abs(dict(pts)[1.0] - (1.0 + 2.0 * math.exp(-2.0))) < 1e-8          # 9 digits
    body, _, rep = convert_str(HEX + heat + amp)
    assert "** *AMPLITUDE, NAME=SINE" in body.upper() and "could not be sampled" in rep.text()


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
    assert kinematic_line(body).replace(" ", "") == "1,2" and "'1, 2' is written" in rep.text()
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
    # DEPENDENCIES: collapsed to the field-0 rows (the parameter dropped), as on the other
    # types; fields are read by position, a blank one being 0
    body, _, rep = convert_str("*Material, name=cfrp\n*Elastic, type=LAMINA, dependencies=1\n"
                               "140e3, 10e3, , 5e3, 5e3, 3.5e3, 20., 0.\n"
                               "130e3, 9e3, 0.3, 4.5e3, 4.5e3, 3.2e3, 20., 1.\n")
    assert _card_at(body, "*ELASTIC, TYPE=ENGINEERING CONSTANTS") == [
        "140000, 10000, 10000, 0, 0, 0.428571, 5000, 5000", "3500, 20"]
    assert "DEPENDENCIES=1: ccx has no field-variable dependence; collapsed" in rep.text()


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
    assert "\n, 0.001, , 1e-9\n" in body and "set for the circular-section" not in rep.text()
    body, _, rep = convert_str(CIRC_EXPLICIT + explicit_step(", 1e-9"))
    assert "\n, 1e-9\n" in body and "set for the circular-section" not in rep.text()
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
    assert "*DYNAMIC, EXPLICIT\n, 0.001\n" in body and "set for the circular-section" not in rep.text()
    # a fixed increment (DIRECT USER CONTROL -> DIRECT) above the cap is only warned: ccx's
    # mass scaling for it is sized from the same overestimate
    direct = ", direct user control"
    body, _, rep = convert_str(CIRC_EXPLICIT + explicit_step("1e-8, 0.001", direct))
    assert "*DYNAMIC, EXPLICIT, DIRECT\n1e-8, 0.001\n" in body
    assert "the fixed increment 1e-8 exceeds" in rep.text()
    _, _, rep = convert_str(CIRC_EXPLICIT + explicit_step("1e-9, 0.001", direct))
    assert "the fixed increment" not in rep.text()
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
    assert {t for t, _ in g.elements.values()} == {"B32R"} and not dangling_refs(g)


def test_approximate_nu_clamp():
    deck = "*Material,name=m\n*Elastic\n1000., 0.5\n"
    body, _, _ = convert_str(deck)
    assert "1000., 0.5" in body                                # untouched by default
    body, _, rep = convert_str(deck, approximate=True)
    assert "1000., 0.475" in body and "[APPROX]" in rep.text()
    # blank fields are positional (a blank nu is 0): the other rows keep them and their
    # temperatures (they became "190000., 0.475", validate_with_ccx.py approximate_blank_nu)
    body, _, _ = convert_str("*Material,name=m\n*Elastic\n200000., 0.5, 20.\n190000., , 100.\n"
                             "180000., 0.45, 200.,\n", approximate=True)
    assert "*ELASTIC\n200000., 0.475, 20.\n190000., , 100.\n180000., 0.45, 200." in body


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


def test_i_section_properties():
    # Abaqus' I profile: l, h, b1, b2, t1, t2, t3 — three rectangles, the web between the flanges
    p = A.i_section(100.0, 200.0, 100.0, 100.0, 8.5, 8.5, 5.6)
    assert abs(p.area - 2724.8) < 1e-9
    assert abs(p.i11 - (100 * 200 ** 3 - 94.4 * 183 ** 3) / 12) < 1e-6           # strong axis
    assert abs(p.i22 - (2 * 8.5 * 100 ** 3 + 183 * 5.6 ** 3) / 12) < 1e-6        # weak axis
    assert abs(p.j - (2 * 100 * 8.5 ** 3 + 183 * 5.6 ** 3) / 3) < 1e-6           # thin-walled
    assert p.i12 == 0.0 and abs(p.c2) < 1e-12 and p.c1 == 0.0 and abs(p.s2) < 1e-12
    off = A.i_section(80.0, 200.0, 100.0, 100.0, 8.5, 8.5, 5.6)                 # node 20 below
    assert abs(off.c2 - 20.0) < 1e-9 and abs(off.s2 - 20.0) < 1e-9
    tee = A.i_section(0.0, 2.0, 2.0, 0.0, 0.2, 0.0, 0.2)                        # T: flange down
    assert abs(tee.area - 0.76) < 1e-12 and abs(tee.s2 - 0.1) < 1e-12           # on the flange
    assert isinstance(A.i_section(100.0, 10.0, 100.0, 100.0, 8.5, 8.5, 5.6), str)
    assert isinstance(A.i_section(1.0, 2.0, 0.0, 0.0, 0.0, 0.0, 0.2), str)     # no flange
    g = A.beam_section_properties("GENERAL", [["10.", "80.", "", "84.375", "80."]])
    assert (g.area, g.i11, g.i12, g.i22, g.j) == (10.0, 80.0, 0.0, 84.375, 80.0)
    assert isinstance(A.beam_section_properties("I", [["1.", "2."]]), str)
    assert isinstance(A.beam_section_properties("L", [["1.", "2.", "0.1", "0.1"]]), str)


def test_i_section_matches_abaqus_verification():
    # Abaqus' Verification Guide, "Verification of beam elements and section types": the I
    # profile of eb32idsd (l at its centroid) and its general-section form in eb32gisd —
    # A 1.4, I11 1.312095, I12 0, I22 .5846667, J .01866, centroid (0, -.1571428) and shear
    # centre (0, -.5971428) from a node at mid-height
    p = A.i_section(1.0428572, 2.4, 3.0, 2.0, 0.2, 0.2, 0.2)
    assert abs(p.area - 1.4) < 1e-12 and abs(p.i11 - 1.312095) < 1e-6
    assert abs(p.i22 - 0.5846667) < 1e-7 and abs(p.j - 0.01866) < 1e-5 and p.i12 == 0.0
    assert abs(p.c2) < 1e-6                                           # the node at the centroid
    assert abs((p.s2 - p.c2) - (-0.5971428 + 0.1571428)) < 1e-6       # shear centre - centroid
    # Abaqus' reference tip deflection under 25 at L = 75, E = 3e6: P L^3 / 3 E I11
    assert abs(25.0 * 75.0 ** 3 / (3 * 3.0e6 * p.i11) - 0.8931) < 1e-4


def test_library_profiles_match_abaqus_verification():
    # Abaqus' Verification Guide cantilever (L 75, E 3e6, P 25): reference tip deflections of
    # its HEX (d 2, t .2) and of the thin-walled box built as an ARBITRARY section
    u2 = lambda i: 25.0 * 75.0 ** 3 / (3 * 3.0e6 * i)
    h = A.hex_section(2.0, 0.2)
    assert abs(u2(h.i11) - 0.3489) < 5e-5 and h.i11 == h.i22 and h.exact_j
    rm = 2.0 - 0.2 / math.sqrt(3.0)                                  # Bredt on the median line
    assert abs(h.j - 4 * (1.5 * math.sqrt(3) * rm ** 2) ** 2 / (6 * rm / 0.2)) < 1e-12
    box = [[x.strip() for x in l.split(",")] for l in
           ["8, -1.9, -.95, -1.9, 0., .2", "-1.9, .95, .2", "0., .95, .1", "1.9, .95, .1",
            "1.9, 0., .2", "1.9, -.95, .2", "0., -.95, .1", "-1.9, -.95, .1"]]
    b = A.arbitrary_section(box)
    assert abs(u2(b.i11) - 1.278) < 0.005 and abs(b.c1) < 1e-12 and abs(b.c2) < 1e-12
    assert abs(b.j - 4 * (3.8 * 1.9) ** 2 / (2 * 3.8 / 0.1 + 2 * 1.9 / 0.2)) < 1e-9   # one closed cell
    assert not b.exact_j and not b.shear_known
    # an open ARBITRARY profile (legs along x2 and x1 from the corner): thin-walled line
    # integrals about the centroid (.5, .5), J the sum of L t^3 / 3
    ell = A.arbitrary_section([["2", "0", "2", "0", "0", ".1"], ["2", "0", ".1"]])
    assert abs(ell.area - 0.4) < 1e-12 and abs(ell.j - 2 * 2 * 0.001 / 3) < 1e-12
    assert abs(ell.c1 - 0.5) < 1e-12 and abs(ell.c2 - 0.5) < 1e-12
    assert abs(ell.i11 - (0.1 * (1.5 ** 3 + 0.5 ** 3) / 3 + 0.1 * 2 * 0.25)) < 1e-12   # each leg
    assert abs(ell.i12 + 0.1) < 1e-12                                   # both legs: -0.05
    # TRAPEZOID: exact area and moments; a square one is the square
    sq = A.trapezoid_section(2.0, 2.0, 2.0, 1.0)
    assert sq.area == 4.0 and abs(sq.i11 - 4 / 3) < 1e-12 and abs(sq.i22 - 4 / 3) < 1e-12 and sq.c2 == 0
    tr = A.trapezoid_section(3.0, 2.0, 1.0, 0.0)
    assert abs(tr.area - 4.0) < 1e-12 and abs(tr.c2 - 2 * (3 + 2) / (3 * 4)) < 1e-12
    assert abs(A.rect_torsion(1.0, 1.0) - 0.1406) < 1e-4 and abs(A.rect_torsion(2.0, 1.0) - 0.4574) < 1e-4
    assert "legs" in A.beam_section_properties("L", [["4.", "4.", ".1", ".1"]])


def test_beam_n1_line_counts_the_lines():
    # blank data lines are not kept, so a default (blank) n1 line is found by counting
    blk = lambda kw, params, data: A.Block(kw, A.OrderedDict(params), data)
    g = "BEAM GENERAL SECTION"
    assert A.beam_n1_line(blk(g, [("SECTION", "RECT")], ["1., 2.", "0., 0., -1.", "2e5, 8e4"])) == 1
    assert A.beam_n1_line(blk(g, [("SECTION", "RECT")], ["1., 2.", "2e5, 8e4, 1e-5"])) is None
    arb = ["2, 0., 1., 0., 0., .1", "1., 0., .1"]
    assert A.beam_n1_line(blk(g, [("SECTION", "ARBITRARY")], arb + ["0., 0., 1.", "2e5, 8e4"])) == 2
    assert A.beam_n1_line(blk("BEAM SECTION", [("SECTION", "ARBITRARY")], arb + ["0., 0., 1."])) == 2
    assert A.beam_n1_line(blk("BEAM SECTION", [("SECTION", "I")], ["1, 2, 1, 1, .1, .1, .1"])) is None
    assert A.beam_n1_line(blk(g, [("SECTION", "GENERAL"), ("TAPER", None)],
                              ["1, 2, 0, 3, 4", "1, 2, 0, 3, 4", "0, 1, 0", "2e5, 8e4"])) == 2


def test_principal_section_turns_n1():
    p = A.BeamSection(1000.0, 4.0e5, 1.5e5, 2.0e5, 5.4e5)
    alpha, ia, ib = A.principal_section(p)
    mid, rad = 3.0e5, math.hypot(1.0e5, 1.5e5)
    assert abs(ia - (mid + rad)) < 1e-6 and abs(ib - (mid - rad)) < 1e-6
    # the product of inertia vanishes in the turned axes, and they keep the sum
    c, s = math.cos(alpha), math.sin(alpha)
    assert abs(c * s * (p.i11 - p.i22) + (c * c - s * s) * p.i12) < 1e-6 * p.i11
    assert abs(ia + ib - p.i11 - p.i22) < 1e-6
    assert A.principal_section(A.BeamSection(1.0, 2.0, 0.0, 3.0, 1.0)) == (0.0, 3.0, 2.0)


# a planar cantilever of two B21 beams under an I profile, clamped at node 1
U1_PLANAR = ("*Node\n1, 0., 0.\n2, 1., 0.\n3, 2., 0.\n*Element, type=B21, elset=B\n1, 1, 2\n2, 2, 3\n"
             "*Nset, nset=TIP\n3\n*Beam Section, elset=B, material=STEEL, section=I\n"
             "0.1, 0.2, 0.1, 0.1, 0.01, 0.01, 0.008\n0., 0., -1.\n*Material, name=STEEL\n"
             "*Elastic\n2.1e11, 0.3\n*Density\n7850.\n*Boundary\n1, ENCASTRE\n")
U1_STEP = "*Step\n*Static\n*Cload\nTIP, 2, -1000.\n*End Step\n"


def _u1_sections(body):
    """The (data line, direction line) of each emitted *BEAM SECTION, SECTION=GENERAL."""
    lines = body.splitlines()
    return [(lines[i + 1], lines[i + 2]) for i, l in enumerate(lines)
            if l.startswith("*BEAM SECTION") and l.endswith("SECTION=GENERAL")]


def test_u1_planar_ibeam():
    # a 2-D I-beam runs as ccx's U1: A, I22 (along n1), 0, I11 (along n2), a large shear
    # factor; DOFs 3-5 held on every node; Timoshenko -> Euler-Bernoulli is reduced physics
    body, conv, rep = convert_str(U1_PLANAR + U1_STEP)
    assert A.U1_CARD in body and "*ELEMENT, TYPE=U1" in body and "TYPE=B21" not in body
    p = A.i_section(0.1, 0.2, 0.1, 0.1, 0.01, 0.01, 0.008)
    (data, n1), = _u1_sections(body)
    v = [float(x) for x in data.split(",")]
    assert abs(v[0] - p.area) < 1e-12 and abs(v[1] - p.i22) < 1e-15 and v[2] == 0.0
    assert abs(v[3] - p.i11) < 1e-15 and v[4] >= 1e6
    assert [float(x) for x in n1.split(",")] == [0.0, 0.0, -1.0]
    assert "ABQ2CCX_PLANAR, 3, 5" in body
    assert any("B21 -> U1" in r for r in conv.reduced_physics), conv.reduced_physics
    assert "RF at U1 nodes" in rep.text()
    # B23 (Abaqus' cubic Euler-Bernoulli beam) is U1's own formulation: exact in statics
    body, conv, _ = convert_str((U1_PLANAR + U1_STEP).replace("B21", "B23"))
    assert "*ELEMENT, TYPE=U1" in body and conv.reduced_physics == []
    # ... but not in a frequency step (U1's mass matrix)
    body, conv, _ = convert_str((U1_PLANAR + "*Step\n*Frequency\n3\n*End Step\n").replace("B21", "B23"))
    assert "*ELEMENT, TYPE=U1" in body and any("mass" in r for r in conv.reduced_physics)


def test_u1_beam_nodes_have_no_dofs_7_to_9():
    # U1 has DOFs 1-6 (MAXDOF=6): BCs on 7-9 go as on the beams it replaces (ccx stops on
    # 7 and 9, and reads 8 as the rotation about x)
    body, _, _ = convert_str(U1_PLANAR + "*Boundary\nTIP, 7, 9\n" + U1_STEP)
    assert "*ELEMENT, TYPE=U1" in body
    assert not any(l.replace(" ", "").startswith(("TIP,7", "TIP,8", "TIP,9")) for l in _live(body))


def test_u1_general_section_exact_torsion():
    # a general section in space: J = 0.9 (I11 + I22), so a copy of the material with
    # nu' = (1 + nu) / 0.9 - 1 makes U1's torsion G (I11 + I22) the section's G J
    deck = ("*Node\n1, 0., 0., 0.\n2, 1., 0., 0.\n*Element, type=B33, elset=B\n1, 1, 2\n"
            "*Beam General Section, elset=B, section=GENERAL, density=7850.\n"
            "1e-3, 4e-7, 0., 2e-7, 5.4e-7\n0., 0., 1.\n2.1e11, 8.076923076923e10\n"
            "*Boundary\n1, 1, 6\n*Step\n*Static\n*Cload\n2, 4, 10.\n*End Step\n")
    body, conv, rep = convert_str(deck)
    assert "*MATERIAL, NAME=ABQ2CCX_U1_GENERAL" in body and "*DENSITY\n7850." in body
    i = body.index("*MATERIAL, NAME=ABQ2CCX_U1_GENERAL")
    e_mod, nu = (float(x) for x in body[i:].splitlines()[2].split(","))
    assert abs(e_mod - 2.1e11) < 1 and abs(nu - (1.3 / 0.9 - 1.0)) < 1e-9
    assert conv.reduced_physics == [] and "[APPROX]" not in rep.text()


def test_u1_in_space_needs_approximate_for_open_sections():
    deck = U1_PLANAR.replace("B21", "B31").replace("0., 0., -1.", "0., 0., 1.") + U1_STEP
    body, conv, rep = convert_str(deck)
    assert "TYPE=U1" not in body and "torsion stiffness is G (I11 + I22)" in body
    body, conv, rep = convert_str(deck, approximate=True)
    assert "*ELEMENT, TYPE=U1" in body and "SECTION=RECT" not in body
    assert "[APPROX]" in rep.text() and "torsion" in rep.text()


def test_u1_unsymmetric_i_and_t_sections():
    # the node at the centroid of an unsymmetric I: exact in a 2-D model (no torsion there);
    # in space its shear centre lies off the centroid, which U1 cannot couple
    sec = "1.0428572, 2.4, 3., 2., .2, .2, .2"
    deck = U1_PLANAR.replace("0.1, 0.2, 0.1, 0.1, 0.01, 0.01, 0.008", sec) + U1_STEP
    body, conv, _ = convert_str(deck.replace("B21", "B23"))
    assert "*ELEMENT, TYPE=U1" in body and conv.reduced_physics == []
    space = deck.replace("B21", "B31").replace("0., 0., -1.", "0., 0., 1.")
    body, _, rep = convert_str(space)
    assert "TYPE=U1" not in body and "shear centre lies" in body
    body, _, rep = convert_str(space, approximate=True)
    assert "*ELEMENT, TYPE=U1" in body and "[APPROX]" in rep.text() and "shear centre" in rep.text()
    # a T with its node away from the centroid has an offset: not U1
    body, _, _ = convert_str(deck.replace(sec, "2., 2., 2., 0., .2, 0., .2"))
    assert "TYPE=U1" not in body and "not at the section's centroid" in body


def test_u1_hex_trapezoid_arbitrary_and_l():
    # HEX: closed and doubly symmetric, J = 0.9 (I11 + I22): exact in space through nu'
    hexdeck = ("*Node\n1, 0., 0., 0.\n2, 1., 0., 0.\n*Element, type=B33, elset=B\n1, 1, 2\n"
               "*Beam Section, elset=B, material=M, section=HEX\n2., .2\n0., 0., 1.\n"
               "*Material, name=M\n*Elastic\n3e6, 0.3\n*Boundary\n1, 1, 6\n"
               "*Step\n*Static\n*Cload\n2, 4, 1.\n*End Step\n")
    body, conv, rep = convert_str(hexdeck)
    assert "*ELEMENT, TYPE=U1" in body and conv.reduced_physics == [] and "[APPROX]" not in rep.text()
    assert "*MATERIAL, NAME=ABQ2CCX_U1_M" in body                        # nu' for G J
    # TRAPEZOID: exact in a 2-D model with the node at its centroid; in space only --approximate
    trap = U1_PLANAR.replace("section=I\n0.1, 0.2, 0.1, 0.1, 0.01, 0.01, 0.008",
                             "section=TRAPEZOID\n0.3, 0.2, 0.1, 0.0833333333333333") + U1_STEP
    body, conv, _ = convert_str(trap.replace("B21", "B23"))
    assert "*ELEMENT, TYPE=U1" in body and conv.reduced_physics == []
    space = trap.replace("B21", "B33").replace("0., 0., -1.", "0., 0., 1.")
    body, _, _ = convert_str(space)
    assert "TYPE=U1" not in body and "numerically" in body
    body, _, rep = convert_str(space, approximate=True)
    assert "*ELEMENT, TYPE=U1" in body and "[APPROX]" in rep.text()
    # ARBITRARY (beams in space only), a symmetric I with the node at its centroid: Abaqus
    # computes its torsion constant numerically, so U1 only with --approximate
    arb = space.replace("section=TRAPEZOID\n0.3, 0.2, 0.1, 0.0833333333333333",
                        "section=ARBITRARY\n5, -.1, -.1, .1, -.1, .01\n0., -.1, 0.\n0., .1, .01\n"
                        ".1, .1, 0.\n-.1, .1, .01")
    body, _, _ = convert_str(arb)
    assert "TYPE=U1" not in body and "numerically" in body
    body, _, rep = convert_str(arb, approximate=True)
    assert "*ELEMENT, TYPE=U1" in body and "[APPROX]" in rep.text()
    # L: the node at its legs' corner, never at its centroid
    ell = U1_PLANAR.replace("section=I\n0.1, 0.2, 0.1, 0.1, 0.01, 0.01, 0.008",
                            "section=L\n0.1, 0.1, 0.01, 0.01") + U1_STEP
    body, _, _ = convert_str(ell)
    assert "TYPE=U1" not in body and "legs" in body


def test_general_section_library_profiles_become_expanded_beams():
    # *BEAM GENERAL SECTION with a ccx profile: ccx's beam section and a material from E, G
    # (nu = 0 in a 2-D model, where Abaqus does not use G); SECT= abbreviates SECTION
    planar = ("*Node\n1, 0., 0.\n3, 2., 0.\n*Ngen\n1, 3\n*Element, type=B22, elset=B\n1, 1, 2, 3\n"
              "*Beam General Section, elset=B, sect=RECT\n0.1, 0.2\n0., 0., -1.\n210e9,\n"
              "*Boundary\n1, 1, 6\n*Step\n*Static\n*Cload\n3, 2, -1.\n*End Step\n")
    body, conv, rep = convert_str(planar)
    lines = body.splitlines()
    i = lines.index("*ELASTIC")
    assert lines[i + 1].replace(" ", "") == "210000000000.,0." and "TYPE=B32" in body
    j = next(k for k, l in enumerate(lines) if l.startswith("*BEAM SECTION"))
    assert "SECTION=RECT" in lines[j] and lines[j + 1].replace(" ", "") == "0.1,0.2"
    assert conv.reduced_physics == []
    space = ("*Node\n1, 0., 0., 0.\n2, 1., 0., 0.\n*Element, type=B31, elset=B\n1, 1, 2\n"
             "*Beam General Section, elset=B, section=CIRC, density=7800.\n0.1\n\n2e11, 8e10, 1.2e-5\n"
             "*Boundary\n1, 1, 6\n*Step\n*Static\n*Cload\n2, 2, -1.\n*End Step\n")
    body, conv, _ = convert_str(space)
    lines = body.splitlines()
    i = lines.index("*ELASTIC")
    e_mod, nu = (float(x) for x in lines[i + 1].split(","))
    assert abs(nu - 0.25) < 1e-12 and "*DENSITY\n7800." in body and "*EXPANSION" in body
    j = next(k for k, l in enumerate(lines) if l.startswith("*BEAM SECTION"))
    assert lines[j + 1].replace(" ", "") == "0.2,0.2" and "TYPE=B32" in body     # r -> 2r; 3 nodes
    body, _, _ = convert_str(space.replace("2e11, 8e10, 1.2e-5", "2e11,"))   # no G in space
    assert "*BEAM SECTION" not in "\n".join(_live(body)) and "no G" in body


def test_u1_refusals_keep_todays_section_handling():
    shell = "*Node\n10, 0., 1.\n11, 1., 1.\n12, 1., 2.\n13, 0., 2.\n*Element, type=CPS4, elset=P\n9, 10, 11, 12, 13\n"
    cases = {
        "beside solid, spring, dashpot and mass": U1_PLANAR + shell + U1_STEP,
        "NLGEOM": U1_PLANAR + U1_STEP.replace("*Step", "*Step, nlgeom=YES"),
        "*BUCKLE": U1_PLANAR + "*Step\n*Buckle\n2\n*Cload\nTIP, 1, -1.\n*End Step\n",
        "*PLASTIC": U1_PLANAR.replace("*Density", "*Plastic\n2.5e8, 0.\n*Density") + U1_STEP,
        "*DYNAMIC": U1_PLANAR + "*Step\n*Dynamic\n0.01, 1.\n*End Step\n",
        "CENTRIF": U1_PLANAR + U1_STEP.replace("*End Step", "*Dload\nB, CENTRIF, 10., 0., 0., 0., 0., 0., 1.\n*End Step"),
    }
    for why, deck in cases.items():
        body, _, rep = convert_str(deck)
        assert "TYPE=U1" not in body, why
        assert why in rep.text(), (why, rep.text())
    # with --approximate the I profile falls back to the RECT there
    body, _, rep = convert_str(cases["NLGEOM"], approximate=True)
    assert "SECTION=RECT" in body and "U1 beam, which carries the profile, cannot be used" in rep.text()


def test_u1_line_load_and_gravity_become_nodal_forces_with_end_moments():
    # PY on a U1 beam: forces q L / 2 and the cubic element's consistent moments +-q L^2 / 12;
    # GRAV (which ccx refuses on U1) the same with rho A g
    body, _, _ = convert_str(U1_PLANAR + "*Step\n*Static\n*Dload\nB, PY, -12.\n, GRAV, 9.81, 0., -1., 0.\n*End Step\n")
    assert ", GRAV" not in "\n".join(_live(body))
    cl = _live(body)[_live(body).index("*CLOAD"):]
    loads = {(int(l.split(",")[0]), int(l.split(",")[1])): float(l.split(",")[2])
             for l in cl[1:] if l[0].isdigit()}
    q = -12.0 - 7850.0 * A.i_section(0.1, 0.2, 0.1, 0.1, 0.01, 0.01, 0.008).area * 9.81
    assert abs(loads[(2, 2)] - q) < 1e-9 * abs(q) and abs(loads[(3, 2)] - q / 2) < 1e-9 * abs(q)
    assert abs(loads[(1, 6)] - q / 12) < 1e-9 * abs(q) and abs(loads[(3, 6)] + q / 12) < 1e-9 * abs(q)
    assert (2, 6) not in loads                                  # the inner moments cancel


def test_u1_gravity_beside_solids_and_long_set_names():
    # U1 beside a C3D8: the GRAV line keeps the solid on a set of its own; a section set
    # name longer than 20 characters (ccx reads 20 there) gets a short alias
    deck = (U1_PLANAR.replace("B21", "B31").replace("elset=B", "elset=A_VERY_LONG_BEAM_SET_NAME")
            .replace("0., 0., -1.", "0., 0., 1.") + HEX.replace("1, 1,2,3,4,5,6,7,8", "9, 11,12,13,14,15,16,17,18")
            .replace("*NODE\n1, ", "*NODE\n11, ").replace("\n2, ", "\n12, ").replace("\n3, ", "\n13, ")
            .replace("\n4, ", "\n14, ").replace("\n5, ", "\n15, ").replace("\n6, ", "\n16, ")
            .replace("\n7, ", "\n17, ").replace("\n8, ", "\n18, ")
            + "*Solid Section, elset=EALL, material=STEEL\n*Boundary\n11, 1, 3\n12, 1, 3\n13, 1, 3\n14, 1, 3\n"
            "*Step\n*Static\n*Dload\n, GRAV, 9.81, 0., -1., 0.\n*End Step\n")
    body, conv, rep = convert_str(deck.replace("B31", "B33"), approximate=True)
    assert "*ELEMENT, TYPE=U1" in body, rep.text()
    assert "ABQ2CCX_U1_REST1, GRAV" in body and conv.geom.elset("ABQ2CCX_U1_REST1") == [9]
    (data, _n1), = _u1_sections(body)
    assert "ELSET=ABQ2CCX_U1," in body and conv.geom.elset("ABQ2CCX_U1") == [1, 2]


def test_u1_n1_projected_per_element_direction():
    # a frame in space: n1 (0, 0, 1) is normal to both members; a skew n1 is projected on
    # each element's normal plane, one card per direction
    deck = ("*Node\n1, 0., 0., 0.\n2, 1., 0., 0.\n3, 1., 1., 0.\n*Element, type=B33, elset=B\n"
            "1, 1, 2\n2, 2, 3\n*Beam General Section, elset=B, section=GENERAL\n"
            "1e-3, 4e-7, 0., 4e-7, 7.5e-7\n0.5, 0.5, 1.\n2.1e11, 8.076923076923e10\n"
            "*Boundary\n1, 1, 6\n*Step\n*Static\n*Cload\n3, 3, 10.\n*End Step\n")
    body, conv, rep = convert_str(deck)
    dirs = sorted(tuple(float(x) for x in n1.split(",")) for _, n1 in _u1_sections(body))
    r = 1 / math.sqrt(1.25)
    want = [(0.0, 0.5 * r, r), (0.5 * r, 0.0, r)]
    assert all(abs(x - y) < 1e-9 for d, w in zip(dirs, want) for x, y in zip(d, w)), dirs
    assert sorted(conv.geom.elset(s) for s in ("ABQ2CCX_U1", "ABQ2CCX_U1_2")) == [[1], [2]]


def test_beam_general_section_in_a_part_is_per_instance():
    deck = ("*Part, name=P\n*Node\n1, 0., 0., 0.\n2, 1., 0., 0.\n*Element, type=B33, elset=B\n1, 1, 2\n"
            "*Beam General Section, elset=B, section=GENERAL\n1e-3, 4e-7, 0., 4e-7, 7.5e-7\n"
            "0., 0., 1.\n2.1e11, 8.076923076923e10\n*End Part\n*Assembly, name=A\n"
            "*Instance, name=I1, part=P\n*End Instance\n*End Assembly\n"
            "*Boundary\nI1.1, 1, 6\n*Step\n*Static\n*Cload\nI1.2, 2, 1.\n*End Step\n")
    body, conv, rep = convert_str(deck)
    assert "*ELEMENT, TYPE=U1" in body, rep.text()
    (data, n1), = _u1_sections(body)


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
    # on solid nodes the rotation line is dropped; the conversion note covers converted lines
    # only, and none when nothing is converted
    body, _, rep = convert_str(HEX + "*Node\n100,0.5,0.5,2.\n*Nset,nset=TOP\n5,6\n"
                               "*Kinematic Coupling, ref node=100\nTOP, 1, 3\nTOP, 4, 6\n")
    assert "NOT coupled" in rep.text() and "every member line kept" not in rep.text()
    _, _, rep = convert_str(HEX + "*Node\n100,0.5,0.5,2.\n*Kinematic Coupling, ref node=100\n5, 4, 6\n")
    assert "couples no translational DOF" in rep.text() and "per DOF range" not in rep.text()


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
    # SCALE STRESS is read as a number: 1.00 and 1e0 change nothing, 2 is reduced physics
    for scale, reduced in (("1.00", []), ("1e0", []), ("2.", ["*PLASTIC, SCALE STRESS"])):
        _, conv, _ = convert_str(mat + f"*Plastic, scale stress={scale}\n300., 0.\n400., 0.1\n")
        assert conv.reduced_physics == reduced, scale


def test_field_dependencies_collapsed():
    # ccx ignores DEPENDENCIES and in effect uses the first row; collapse to field = 0
    body, _, rep = convert_str("*Material,name=M\n*Elastic,dependencies=1\n"
                               "21000.,0.3,0.,-1.\n210000.,0.3,0.,1.\n")
    assert "*ELASTIC\n115500, 0.3, 0." in body and "DEPENDENCIES=1" in rep.text()
    body, _, _ = convert_str("*Material,name=M\n*Plastic, dependencies=1\n100.,0.,,0.\n"
                             "200.,0.1,,0.\n150.,0.,,1.\n250.,0.1,,1.\n")
    assert "*PLASTIC\n100., 0.\n200., 0.1" in body and "150." not in body
    # rows that cannot be read are passed through, warned and reduced physics, as on *ELASTIC
    _, conv, rep = convert_str("*Material,name=M\n*Plastic, dependencies=1\n100.,0.,20.,abc\n")
    assert "*PLASTIC, DEPENDENCIES=...: rows could not be parsed" in rep.text()
    assert conv.reduced_physics == ["*PLASTIC field-variable dependence"]
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


def test_step_nlgeo_abbreviates_nlgeom():
    # Abaqus reads the abbreviation NLGEO as NLGEOM (real decks write NLGEO=NO): the step is
    # written NLGEOM, as the B32R note and the U1 planner already read it
    beam = ("*Node\n1, 0., 0., 0.\n2, 1., 0., 0.\n3, 2., 0., 0.\n*Element, type=B32, elset=B\n1, 1, 2, 3\n"
            "*Beam Section, elset=B, material=M, section=RECT\n0.1, 0.1\n0., 0., 1.\n*Material, name=M\n"
            "*Elastic\n1000., 0.3\n*Boundary\n1, 1, 6\n*Step, nlgeo\n*Static\n*Cload\n3, 2, 1.\n*End Step\n")
    body, _, rep = convert_str(beam)
    assert "*STEP, NLGEOM\n" in body and "in an NLGEOM step" in rep.text()
    assert "NLGEO dropped" not in rep.text()
    body, _, _ = convert_str(beam.replace("nlgeo", "nlgeo=NO"))
    assert "*STEP, NLGEOM=NO\n" in body


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


def test_amplitude_times_close_together_stay_apart():
    # written to 6 digits, the points 1e-4 apart from BEGIN=100 fell on t = 100, and a SMOOTH
    # STEP from 10 to 10.001 became one jump (validate_with_ccx.py amplitude_close_times)
    body, _, _ = convert_str("*Amplitude, name=EQ, definition=EQUALLY SPACED, fixed interval=1e-4, "
                             "begin=100.\n0., 0.5, 1.\n*Amplitude, name=SS, definition=SMOOTH STEP\n"
                             "10., 0., 10.001, 1.\n*Amplitude, name=TAB, scalex=1.0000001\n"
                             "0., 0., 1., 0.1234567891\n")
    assert _amplitude(body, "EQ") == [(100.0, 0.0), (100.0001, 0.5), (100.0002, 1.0)]
    ss = _amplitude(body, "SS")
    assert len({t for t, _ in ss}) == 101 and ss[50] == (10.0005, 0.5) and ss[-1] == (10.001, 1.0)
    assert _amplitude(body, "TAB") == [(0.0, 0.0), (1.0000001, 0.1234567891)]


def test_kinematic_coupling_keeps_every_line():
    body, _, _ = convert_str(HEX + "*Node\n100,0.5,0.5,2.\n*Nset,nset=TOP\n5,6\n"
                             "*Kinematic Coupling, ref node=100\nTOP, 1, 1\n7, 3, 3\n")
    assert body.count("*COUPLING") == 2 and "*KINEMATIC\n1, 1" in body and "*KINEMATIC\n3, 3" in body
    body, _, rep = convert_str(HEX + "*Node\n100,0.5,0.5,2.\n*Nset,nset=TOP\n5,6\n"
                               "*Kinematic Coupling, ref node=100\nTOP\n7\n")
    assert body.count("*COUPLING") == 1 and "*KINEMATIC\n1, 3" in body   # all DOFs, solid nodes
    assert "clamped" not in rep.text()                                    # exact for solids
    # a blank line (only commas) is skipped, also by the explicit-step planners (an IndexError)
    deck = (HEX + "*Node\n100,0.5,0.5,2.\n*Nset,nset=TOP\n5,6\n*Solid Section, elset=EALL, material=M\n"
            "*Material, name=M\n*Elastic\n1000., 0.3\n*Density\n1e-9\n*Kinematic Coupling, ref node=100\n"
            "TOP, 1, 3\n{}*Step\n*Dynamic, Explicit\n, 1e-4\n*Boundary\n100, 3, 3, 0.01\n*End Step\n")
    assert convert_str(deck.format(",\n"))[0] == convert_str(deck.format(""))[0]


def test_orientation_origin_and_node_definition():
    body, _, _ = convert_str("*Orientation, name=O1\n11., 10., 0., 10., 11., 0., 10., 10., 0.\n")
    assert "*ORIENTATION, NAME=O1\n1, 0, 0, 0, 1, 0" in body
    body, _, _ = convert_str(S4 + "*Orientation, name=O2, definition=nodes\n2, 4, 1\n")
    assert "*ORIENTATION, NAME=O2\n1, 0, 0, 0, 1, 0" in body
    # the nodes count by position: an undefined one (here 9) leaves no axes, where the others
    # moved up into its place; c may be 0, blank or left out (the global origin)
    body, conv, _ = convert_str(S4 + "*Orientation, name=O3, definition=nodes\n9, 2, 4\n"
                                "*Orientation, name=O4, definition=nodes\n2, 4, 9\n"
                                "*Orientation, name=O5, definition=nodes\n2, 4, 0\n")
    assert "\n** *ORIENTATION, NAME=O3, DEFINITION=nodes\n** 9, 2, 4\n" in body
    assert "\n** *ORIENTATION, NAME=O4, DEFINITION=nodes\n** 2, 4, 9\n" in body
    assert "*ORIENTATION, NAME=O5\n1, 0, 0, 0, 1, 0" in body
    assert "O5" in conv._orient_axes and not {"O3", "O4"} & conv._orient_axes
    # a cylindrical system's a, b are not measured from c: c is dropped, and the note says so
    body, _, rep = convert_str("*Orientation, name=C, system=cylindrical\n0., 0., 0., 0., 0., 1., 5., 0., 0.\n")
    assert "coordinates beyond points a,b dropped" in rep.text() and "origin c" not in rep.text()


def test_orientation_zero_additional_rotation_on_a_cylindrical_system():
    # ccx takes the additional-rotation line only for rectangular systems; a zero angle turns
    # nothing, so leaving it out is exact (NAFEMS LE2: "1, 0."), and so is a turn no card uses
    deck = HEX + "*Orientation, name=ORI, system=cylindrical\n0.,0.,0., 0.,0.,1.\n1, 0.\n"
    _, conv, rep = convert_str(deck)
    assert conv.reduced_physics == [] and "zero angle" in rep.text()
    _, conv, rep = convert_str(deck.replace("1, 0.", "1, 30."))
    assert conv.reduced_physics == [] and "no card uses it" in rep.text()
    _, conv, _ = convert_str(deck.replace("1, 0.", "1, 30.") + COMPOSITE_MAT
                             + "*Solid Section, elset=EALL, material=CFRP, orientation=ORI\n")
    assert conv.reduced_physics == ["*ORIENTATION additional rotation on a non-rectangular system dropped"]


def test_equation_node_sets_pair_in_sorted_order():
    body, _, _ = convert_str(S4 + "*Nset, nset=LEFT\n1, 4, 2\n*Nset, nset=RIGHT\n6, 5, 3\n"
                             "*Equation\n2\nLEFT, 1, 1., RIGHT, 1, -1.\n")
    assert "1, 1, 1., 3, 1, -1.\n2\n2, 1, 1., 5, 1, -1.\n2\n4, 1, 1., 6, 1, -1." in body


def test_equation_card_with_several_set_equations():
    # one *EQUATION card may hold several equations (NAFEMS FV42: TOP-BOT, then MID_1-BOT_1);
    # each resolves its node sets on its own, where the card used to reach ccx with set names
    body, _, _ = convert_str(S4 + "*Nset, nset=A\n1, 2\n*Nset, nset=B\n3, 4\n*Nset, nset=C\n5\n"
                             "*Nset, nset=D\n6\n*Equation\n2\nA, 1, 1., B, 1, -1.\n2\nC, 2, 1., D, 2, -1.\n")
    assert ("*EQUATION\n2\n1, 1, 1., 3, 1, -1.\n2\n2, 1, 1., 4, 1, -1.\n2\n5, 2, 1., 6, 2, -1."
            in body), body


def test_perturbation_static_before_general_step_warns():
    # ccx runs it as a general step: the next general step gets its loads back
    # (_restore_base_states) but starts from its deformed state
    _, conv, rep = convert_str(HEX + "*Step, perturbation\n*Static\n*End Step\n*Step\n*Static\n*End Step\n")
    assert "starts from its deformed state" in rep.text() and conv.reduced_physics
    _, conv, rep = convert_str(HEX + "*Step, perturbation\n*Static\n*End Step\n*Step, perturbation\n"
                                     "*Static\n*End Step\n")
    assert "loads persist" in rep.text() and conv.reduced_physics
    _, _, rep = convert_str(HEX + "*Step, perturbation\n*Static\n*End Step\n")
    assert "loads persist" not in rep.text() and "deformed state" not in rep.text()


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
    with open(os.path.join(d, "nodes.inp"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("** comment\n1, 0., 0., 0.\n2, 1., 0., 0.\n")
    with open(os.path.join(d, "main.inp"), "w", encoding="utf-8", newline="\n") as fh:
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


PART_BOLT = ("*Part, name=P\n*Node\n1,0.,0.,0.\n2,1.,0.,0.\n3,1.,1.,0.\n4,0.,1.,0.\n5,0.,0.,1.\n"
             "6,1.,0.,1.\n7,1.,1.,1.\n8,0.,1.,1.\n9,0.,0.,2.\n10,1.,0.,2.\n11,1.,1.,2.\n12,0.,1.,2.\n"
             "98,0.5,0.5,3.\n99,0.5,0.5,1.\n*Element, type=C3D8, elset=BAR\n1,1,2,3,4,5,6,7,8\n"
             "2,5,6,7,8,9,10,11,12\n*Element, type=DCOUP3D, elset=DC\n3,98\n*Nset, nset=TOP\n9,10,11,12\n"
             "*Elset, elset=LOW\n1\n*Surface, name=CUT\nLOW, S2\n*Solid Section, elset=BAR, material=M\n"
             "{part}*End Part\n*Assembly, name=A\n*Instance, name=I1, part=P\n{i1}*End Instance\n"
             "*Instance, name=I2, part=P\n3., 0., 0.\n3., 0., 0., 4., 0., 0., 90.\n{i2}*End Instance\n"
             "*End Assembly\n*Material, name=M\n*Elastic\n1000., 0.3\n")
BOLT_CARDS = "*Distributing Coupling, elset=DC\nTOP, 1.\n*Pre-tension Section, surface=CUT, node=99\n0., 0., 1.\n"


def test_part_level_distributing_coupling_and_pretension_per_instance():
    # each instance gets its own copy: its names, node ids and turned normal (written once, raw,
    # they named the part's sets: ccx stopped, validate_with_ccx.py assembly_bolts)
    body, _, _ = convert_str(PART_BOLT.format(part=BOLT_CARDS, i1="", i2=""))
    assert "*DISTRIBUTING COUPLING, ELSET=I1_DC\nI1_TOP, 1.\n" in body
    assert "*DISTRIBUTING COUPLING, ELSET=I2_DC\nI2_TOP, 1.\n" in body
    assert "*PRE-TENSION SECTION, SURFACE=I1_CUT, NODE=99\n0, 0, 1\n" in body
    assert "*PRE-TENSION SECTION, SURFACE=I2_CUT, NODE=198\n0, -1, 0\n" in body
    assert "ELSET=DC\n" not in body and "SURFACE=CUT," not in body
    # inside an *INSTANCE: that instance's (it was left out without a word), and a card the
    # flattener does not write per instance is warned
    body, conv, rep = convert_str(PART_BOLT.format(part="", i1=BOLT_CARDS, i2="*Hourglass Stiffness\n1.\n"))
    assert "*DISTRIBUTING COUPLING, ELSET=I1_DC\nI1_TOP, 1.\n" in body and "I2_DC\nI2_TOP" not in body
    assert "*PRE-TENSION SECTION, SURFACE=I1_CUT, NODE=99\n" in body and "SURFACE=I2_CUT" not in body
    assert "*HOURGLASS STIFFNESS inside an *INSTANCE left out" in rep.text()
    assert conv.reduced_physics == ["*HOURGLASS STIFFNESS inside an *INSTANCE left out"]


def test_pretension_node_and_element_sets_resolved():
    # Abaqus takes NODE= as a node number or a set of exactly that node, ELEMENT= (a truss or
    # beam cut) likewise; ccx 2.23 stops on a set name there ('*ERROR reading *PRE-TENSION
    # SECTION'), so a one-member set is written as its number (validate_with_ccx.py
    # pretension_node_set*)
    bar = ("*Node\n1,0.,0.,0.\n2,1.,0.,0.\n3,1.,1.,0.\n4,0.,1.,0.\n5,0.,0.,1.\n6,1.,0.,1.\n7,1.,1.,1.\n"
           "8,0.,1.,1.\n9,0.,0.,2.\n10,1.,0.,2.\n11,1.,1.,2.\n12,0.,1.,2.\n99,0.5,0.5,1.\n"
           "*Element, type=C3D8, elset=BAR\n1,1,2,3,4,5,6,7,8\n2,5,6,7,8,9,10,11,12\n*Elset, elset=LOW\n1\n"
           "*Nset, nset=PT\n99\n*Nset, nset=TWO\n99, 5\n*Surface, name=CUT\nLOW, S2\n"
           "*Solid Section, elset=BAR, material=M\n*Material, name=M\n*Elastic\n210000., 0.\n")
    body, _, rep = convert_str(bar + "*Pre-tension Section, surface=CUT, node=PT\n0., 0., 1.\n")
    assert "*PRE-TENSION SECTION, SURFACE=CUT, NODE=99\n0., 0., 1." in body
    assert "*PRE-TENSION SECTION NODE=<set> written as the set's node number" in rep.text()
    # any other set: Abaqus rejects it too, and ccx stops on it rather than solve without the cut
    for name, why in (("TWO", "a set of 2 nodes"), ("NOSUCH", "no node set")):
        body, conv, rep = convert_str(bar + f"*Pre-tension Section, surface=CUT, node={name}\n")
        assert f"*PRE-TENSION SECTION, SURFACE=CUT, NODE={name}" in body.splitlines()
        assert f"[WARNING] *PRE-TENSION SECTION NODE={name} names {why}" in rep.text()
        assert not conv.reduced_physics
    # a part's card naming its set: each instance's copy names that instance's node
    body, _, _ = convert_str(PART_BOLT.format(part="*Nset, nset=PT\n99\n*Pre-tension Section, surface=CUT, "
                                                   "node=PT\n0., 0., 1.\n", i1="", i2=""))
    assert "*PRE-TENSION SECTION, SURFACE=I1_CUT, NODE=99\n0, 0, 1\n" in body
    assert "*PRE-TENSION SECTION, SURFACE=I2_CUT, NODE=198\n0, -1, 0\n" in body
    # at the assembly level: instance-qualified sets and numbers (an element number takes the
    # element offset) and an assembly set
    beams = ("*Part, name=B\n*Node\n1,0.,0.,0.\n2,1.,0.,0.\n3,2.,0.,0.\n99,1.,0.,0.\n"
             "*Element, type=B31, elset=BOLT\n1,1,2\n2,2,3\n*Elset, elset=CUTEL\n1\n*Nset, nset=PT\n99\n"
             "*Beam Section, elset=BOLT, material=M, section=RECT\n1., 1.\n0., 0., 1.\n*End Part\n"
             "*Assembly, name=A\n*Instance, name=I1, part=B\n*End Instance\n*Instance, name=I2, part=B\n"
             "0., 5., 0.\n*End Instance\n*Nset, nset=PT2, instance=I2\n99\n"
             "*Pre-tension Section, element=I1.CUTEL, node=I1.PT\n*Pre-tension Section, {i2}\n"
             "*End Assembly\n*Material, name=M\n*Elastic\n210000., 0.\n")
    for i2 in ("element=I2.1, node=PT2", "element=I2.CUTEL, node=I2.99", "element=3, node=I2.PT"):
        body, _, _ = convert_str(beams.format(i2=i2))
        assert "*PRE-TENSION SECTION, ELEMENT=1, NODE=99\n*PRE-TENSION SECTION, ELEMENT=3, NODE=198\n" in body


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


def _contact(pair="", mesh=None, faces=("S1", "S2")):
    """A model with a contact pair between two faces of its element(s)."""
    return ((mesh or HEX) + f"*Surface, name=A\nEALL, {faces[0]}\n*Surface, name=B\nEALL, {faces[1]}\n"
            f"*Surface interaction, name=SI\n*Contact pair, interaction=SI{pair}\nA, B\n")


QUAD = "*NODE\n1, 0.,0.\n2, 1.,0.\n3, 1.,1.\n4, 0.,1.\n*ELEMENT, TYPE={}, ELSET=EALL\n1, 1,2,3,4\n"


def test_contact_output_maps_to_ccx_labels():
    body, _, _ = convert_str(_contact() + "*Step\n*Static\n*Output, field\n*Contact Output\nCDISP, "
                             "CSTRESS, CFORCE\n*End Step\n")
    assert "*CONTACT FILE\nCDIS, CSTR" in body
    # names ccx does not know itself are dropped, not folded onto CSTR
    body, _, _ = convert_str(_contact() + "*Step\n*Static\n*Output, field\n*Contact Output\nCPRESS\n"
                             "*End Step\n")
    assert "*CONTACT FILE" not in body


def test_contact_output_requests_ccx_cannot_write():
    # ccx writes contact output only for *CONTACT PAIR contact (a model without one gets an
    # empty block), and 2.23 aborts on it in a model with axisymmetric elements once the .frd
    # gets S too (its stress error estimate comes with S) — unless every pair is face-to-face;
    # node-to-surface contact of plane / axisymmetric elements lands on the nodes of their
    # expanded 3-D form, which the 2-D .frd lacks (probed)
    req = "*Output, field\n*Node Output\nU\n*Element Output\nS\n*Contact Output\nCSTRESS\n"
    body, _, rep = convert_str(HEX + "*Step\n*Static\n" + req + "*End Step\n")
    assert "*CONTACT FILE" not in body and "*EL FILE\nS\n" in body
    assert "*CONTACT OUTPUT dropped: the ccx model has no contact pair" in rep.text()
    body, _, rep = convert_str(HEX + "*Surface, name=A\nEALL, S1\n*Surface, name=B\nEALL, S2\n"
                               "*Contact pair, interaction=SI, tied\nA, B\n*Step\n*Static\n" + req +
                               "*End Step\n")
    assert "*TIE" in body and "*CONTACT FILE" not in body
    axi = QUAD.format("CAX4")
    body, _, rep = convert_str(_contact(mesh=axi, faces=("S1", "S3")) + "*Step\n*Static\n" + req +
                               "*End Step\n")
    assert "*CONTACT FILE" not in body
    assert ("*CONTACT OUTPUT dropped: ccx 2.23 aborts writing contact output in a model with "
            "axisymmetric elements") in rep.text()
    body, _, rep = convert_str(_contact(mesh=axi, faces=("S1", "S3")) + "*Step\n*Static\n" +
                               req.replace("*Element Output\nS\n", "") + "*End Step\n")
    assert "*CONTACT FILE\nCSTR\n" in body and "expanded 3-D form" in rep.text()
    body, _, rep = convert_str(_contact(", type=SURFACE TO SURFACE", axi, ("S1", "S3")) +
                               "*Step\n*Static\n" + req + "*End Step\n")
    assert "*CONTACT FILE\nCSTR\n" in body and "*CONTACT OUTPUT" not in rep.text()
    body, _, rep = convert_str(_contact(mesh=QUAD.format("CPE4"), faces=("S1", "S3")) +
                               "*Step\n*Static\n" + req + "*End Step\n")
    assert "*CONTACT FILE\nCSTR\n" in body
    assert "*CONTACT OUTPUT: ccx writes node-to-surface contact output of plane" in rep.text()


def test_preselect_contact_output():
    # Abaqus' preselected field output has the contact stresses and displacements (CSTRESS,
    # CDISP) in general static, quasi-static, implicit dynamic and coupled temperature-
    # displacement steps of a model with contact, CSTRESS in explicit dynamics (table 1):
    # *CONTACT FILE beside the *NODE FILE / *EL FILE cards (CDIS and CSTR switch on the same
    # CONTACT block in ccx); node-to-surface pairs (Abaqus' default) of solid elements too
    sts = ", type=SURFACE TO SURFACE"
    cases = {"*Static\n": "*EL FILE\nS, E\n*CONTACT FILE\nCDIS, CSTR\n",
             "*Visco, cetol=1.e-3\n0.1, 1.\n": "*EL FILE\nS, E\n*CONTACT FILE\nCDIS, CSTR\n",
             "*Dynamic\n0.01, 1.\n": "*EL FILE\nS, E\n*CONTACT FILE\nCDIS, CSTR\n",
             "*Coupled Temperature-displacement\n0.1, 1.\n":
                 "*EL FILE\nS, E, HFL\n*CONTACT FILE\nCDIS, CSTR\n",
             "*Dynamic, Explicit\n, 1.e-4\n": "*EL FILE\nS, E\n*CONTACT FILE\nCSTR\n"}
    for proc, cards in cases.items():
        for pair in (sts, ""):
            body, _, rep = convert_str(_contact(pair) + STEEL + "*Step\n" + proc + PRESELECT +
                                       "*End Step\n")
            assert cards in _step(body, 1), (proc, pair, _step(body, 1))
            assert "*CONTACT FILE " in rep.text() and "CSTRESS" not in rep.text(), proc
    # none in linear perturbation steps; the default output of a step without requests and
    # the carried one have it
    body, _, _ = convert_str(_contact(sts) + "*Step\n*Static\n" + PRESELECT + "*End Step\n"
                             "*Step, perturbation\n*Static\n" + PRESELECT + "*End Step\n"
                             "*Step, perturbation\n*Frequency\n3\n" + PRESELECT + "*End Step\n")
    assert "*CONTACT FILE" in _step(body, 1)
    assert "*CONTACT FILE" not in _step(body, 2) + _step(body, 3)
    body, _, rep = convert_str(_contact(sts) + "*Step\n*Static\n*End Step\n*Step\n*Static\n"
                               "*End Step\n")
    assert _step(body, 1).endswith("*EL FILE\nS, E\n*CONTACT FILE\nCDIS, CSTR\n")
    assert _step(body, 2).endswith("*EL FILE\nS, E\n*CONTACT FILE\nCDIS, CSTR\n")
    # a model without contact: Abaqus writes no contact output, so the notes do not miss it
    body, _, rep = convert_str(HEX + "*Step\n*Static\n" + PRESELECT + "*End Step\n")
    assert "*CONTACT FILE" not in body and "(no ccx label for CF)." in rep.text()
    assert "CSTRESS" not in rep.text()


def test_preselect_contact_output_left_out_where_ccx_cannot_write_it():
    # Abaqus contact ccx has no contact pair for — a tied pair (a *TIE in ccx), general
    # contact (not converted) — and node-to-surface pairs of plane and axisymmetric elements
    # (ccx 2.23 aborts on their contact output in an axisymmetric model; in a plane one it
    # lands on nodes the 2-D .frd lacks): no *CONTACT FILE, a note why
    deck = "*Step\n*Static\n" + PRESELECT + "*End Step\n"
    no_pair = "CSTRESS, CDISP left out: the ccx model has no contact pair"
    body, _, rep = convert_str(HEX + "*Surface, name=A\nEALL, S1\n*Surface, name=B\nEALL, S2\n"
                               "*Contact pair, interaction=SI, tied\nA, B\n" + deck)
    assert "*TIE" in body and "*CONTACT FILE" not in body and no_pair in rep.text()
    body, _, rep = convert_str(HEX + "*Contact\n*Contact Inclusions, all exterior\n" +
                               deck.replace("*Static", "*Dynamic, Explicit\n, 1.e-4"))
    assert "*CONTACT FILE" not in body and "CSTRESS left out: the ccx model has no contact" in rep.text()
    for elem in ("CAX4", "CPE4", "CPS4", "M3D4"):
        body, _, rep = convert_str(_contact(mesh=QUAD.format(elem), faces=("S1", "S3")) + deck)
        assert "*CONTACT FILE" not in body, elem
        assert ("ccx 2.23 aborts" if elem == "CAX4" else "expanded 3-D form") in rep.text(), elem
        body, _, rep = convert_str(_contact(", type=SURFACE TO SURFACE", QUAD.format(elem),
                                            ("S1", "S3")) + deck)
        assert "*EL FILE\nS, E\n*CONTACT FILE\nCDIS, CSTR\n" in _step(body, 1), elem
    # a beam makes ccx write the .frd in 3-D, expanded nodes included: plane elements then
    # have it, axisymmetric ones still not
    beam = "*NODE\n9, 5.,0.\n10, 6.,0.\n*ELEMENT, TYPE=B31, ELSET=BEAM\n9, 9, 10\n"
    for elem, ok in (("CPE4", True), ("CAX4", False)):
        body, _, rep = convert_str(_contact(mesh=QUAD.format(elem) + beam, faces=("S1", "S3")) + deck)
        assert ("*CONTACT FILE\nCDIS, CSTR\n" in body) == ok, elem


def test_contact_output_variable_preselect():
    # a field *CONTACT OUTPUT, VARIABLE=PRESELECT / ALL: the contact variables Abaqus
    # preselects for the procedure (none in a linear perturbation step) plus the ones named
    req = "*Output, field\n*Contact Output, variable={}\n"
    for proc, var, card in (("*Static\n", "PRESELECT", "*CONTACT FILE\nCDIS, CSTR\n"),
                            ("*Dynamic, Explicit\n, 1.e-4\n", "ALL", "*CONTACT FILE, FREQUENCY=56\nCSTR\n")):
        body, _, rep = convert_str(_contact() + STEEL + "*Step\n" + proc + req.format(var) +
                                   "*End Step\n")
        assert card in body and "parameter VARIABLE dropped" not in rep.text(), proc
    body, _, rep = convert_str(_contact() + "*Step\n*Static\n*End Step\n*Step, perturbation\n"
                               "*Frequency\n3\n" + req.format("PRESELECT") + "*End Step\n")
    assert "*CONTACT FILE" not in _step(body, 2)
    assert "*CONTACT OUTPUT, VARIABLE=PRESELECT in a *FREQUENCY step: Abaqus preselects" in rep.text()
    # a request carried into a later step that ccx cannot write (no contact pair) is not
    # announced as written again
    body, _, rep = convert_str(HEX + "*Step\n*Static\n*Output, field\n*Contact Output\n*End Step\n"
                               "*Step\n*Static\n*End Step\n")
    assert "*CONTACT FILE" not in body and "their cards written again" not in rep.text()


OUT_BEAM = ("*Node\n1, 0., 0., 0.\n7, 60., 0., 0.\n*Ngen, nset=AXIS\n1, 7, 1\n*Nset, nset=TIP\n7\n"
            "*Element, type=B31, elset=BEAM\n1, 1, 2\n*Elgen, elset=BEAM\n1, 6, 1, 1\n"
            "*Beam Section, elset=BEAM, material=M, section=RECT\n1., 2.\n0., 0., -1.\n"
            "*Material, name=M\n*Elastic\n1000., 0.3\n*Boundary\n1, ENCASTRE\n")


def _step(body, k):
    """The text of step ``k`` (1-based) of a converted deck."""
    return body.split("*STEP")[k].split("*END STEP")[0]


def _without_output(text):
    """``text`` without its *NODE FILE / *EL FILE cards: a step without output requests gets
    Abaqus' default output at its end."""
    return re.sub(r"\*(?:NODE FILE|EL FILE)[^\n]*\n[^*\n][^\n]*\n", "", text)


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


PRESELECT = "*Output, field, variable=PRESELECT\n"
STEEL = ("*Material, name=M\n*Elastic\n210000., 0.3\n*Density\n7.85e-9\n"
         "*Solid Section, elset=EALL, material=M\n")


def test_preselect_field_output_per_procedure():
    # *OUTPUT, FIELD, VARIABLE=PRESELECT (the Abaqus/CAE default) -> the ccx labels of Abaqus'
    # preselected field output for the step's procedure ("Output to the output database",
    # table 1); before, ccx wrote the mesh only.  A in no step and V in steady state dynamics
    # are left out (ccx 2.23 rejects them on *NODE FILE, probed); implicit *DYNAMIC output
    # comes every 10 increments, the Abaqus default there
    cases = {"*Static\n": "*NODE FILE\nU, RF\n*EL FILE\nS, E\n",
             "*Dynamic\n0.01, 1.\n": "*NODE FILE, FREQUENCY=10\nU, V, RF\n*EL FILE\nS, E\n",
             "*Frequency\n5\n": "*NODE FILE\nU\n",
             "*Buckle\n2\n": "*NODE FILE\nU\n",
             "*Heat Transfer, steady state\n1., 1.\n": "*NODE FILE\nNT, RFL\n*EL FILE\nHFL\n",
             "*Coupled Temperature-displacement\n0.1, 1.\n":
                 "*NODE FILE\nU, RF, NT, RFL\n*EL FILE\nS, E, HFL\n"}
    for proc, cards in cases.items():
        body, _, rep = convert_str(HEX + "*Step\n" + proc + PRESELECT + "*End Step\n")
        assert cards in _step(body, 1), (proc, _step(body, 1))
        assert _step(body, 1).count("*EL FILE") == cards.count("*EL FILE"), proc
        assert "VARIABLE=PRESELECT in *" in rep.text()
    body, _, _ = convert_str(HEX + "*Step\n*Frequency, storage=yes\n5\n" + PRESELECT + "*End Step\n"
                             "*Step\n*Steady State Dynamics\n1., 10., 5\n" + PRESELECT + "*End Step\n"
                             "*Step\n*Modal Dynamic\n0.001, 0.1\n" + PRESELECT + "*End Step\n")
    assert "*NODE FILE\nU, RF\n*EL FILE\nS, E\n" in _step(body, 2)
    assert "*NODE FILE, FREQUENCY=10\nU, V, RF\n*EL FILE\nS, E\n" in _step(body, 3)
    # preselected history output (whole-model energies) has no ccx counterpart
    body, _, rep = convert_str(HEX + "*Step\n*Static\n*Output, history, variable=PRESELECT\n"
                               "*End Step\n")
    assert "*NODE FILE" not in body and "has no ccx counterpart; dropped" in rep.text()


def test_preselect_peeq_only_where_a_material_yields():
    # ccx warns 'PEEQ-output requested' on a model without plasticity (probed): PEEQ only
    # with a *PLASTIC the converter keeps, or *CREEP
    plastic = STEEL.replace("*Density", "*Plastic\n200., 0.\n400., 0.1\n*Density")
    deck = "*Step\n*Static\n" + PRESELECT + "*End Step\n"
    body, _, _ = convert_str(HEX + plastic + deck)
    assert "*EL FILE\nS, E, PEEQ\n" in _step(body, 1)
    body, _, _ = convert_str(HEX + plastic.replace("*Plastic", "*Plastic, hardening=user, properties=2")
                             + deck)
    assert "*EL FILE\nS, E\n" in _step(body, 1)
    body, _, _ = convert_str(HEX + STEEL + deck)
    assert "*EL FILE\nS, E\n" in _step(body, 1)


def test_preselect_with_named_variables_and_all():
    # PRESELECT plus variables named under it: Abaqus appends them; a field *NODE OUTPUT /
    # *ELEMENT OUTPUT with VARIABLE=PRESELECT: its kind's preselected variables plus its own;
    # *OUTPUT, FIELD, VARIABLE=ALL: also ENER, and the cards under it are ignored (Abaqus)
    body, _, _ = convert_str(HEX + "*Step\n*Static\n" + PRESELECT + "*Element Output\nENER\n"
                             "*End Step\n")
    assert "*NODE FILE\nU, RF\n*EL FILE\nS, E\n*EL FILE\nENER\n" in _step(body, 1)
    body, _, rep = convert_str(HEX + "*Step\n*Static\n*Output, field\n*Node Output, variable=PRESELECT\n"
                               "NT\n*Element Output, variable=PRESELECT\n*End Step\n")
    assert "*NODE FILE\nU, RF, NT\n*EL FILE\nS, E\n" in _step(body, 1)
    assert "VARIABLE dropped" not in rep.text()
    body, _, rep = convert_str(HEX + "*Nset, nset=TOP\n5, 6, 7, 8\n*Step\n*Static\n"
                               "*Output, field, variable=ALL\n*Node Output, nset=TOP\nU\n*End Step\n")
    assert "*NODE FILE\nU, RF\n*EL FILE\nS, E, ENER\n" in _step(body, 1)
    assert "NSET=TOP" not in _step(body, 1) and "ignores the individual requests" in rep.text()
    # a kind with nothing preselected for the procedure is dropped, not defaulted to U / S
    body, _, _ = convert_str(HEX + "*Step\n*Frequency\n3\n*Output, field\n*Element Output, "
                             "variable=PRESELECT\n*End Step\n")
    assert "*EL FILE" not in body


def test_default_output_without_output_requests():
    # Abaqus writes its preselected field output for a step without output database
    # requests (*OUTPUT) and carries it over; *NODE PRINT / *EL PRINT (.dat) and *NODE FILE /
    # *EL FILE (.fil) requests do not replace it.  Added at the end of the step
    body, _, rep = convert_str(HEX + "*Step\n*Static\n*End Step\n")
    assert _step(body, 1).endswith("*NODE FILE\nU, RF\n*EL FILE\nS, E\n")
    assert "requests no output database output and inherits none" in rep.text()
    body, _, _ = convert_str(HEX + "*Step\n*Static\n*Node Print\nU\n*El Print\nS\n*End Step\n")
    assert _step(body, 1).endswith("*EL PRINT, ELSET=ABQ2CCX_ALL_ELEMENTS\nS\n*NODE FILE\nU, RF\n"
                                   "*EL FILE\nS, E\n")
    # history requests only: Abaqus writes no field output in that step
    body, _, _ = convert_str(HEX + "*Nset, nset=TOP\n5, 6, 7, 8\n*Step\n*Static\n*Output, history\n"
                             "*Node Output, nset=TOP\nU\n*End Step\n")
    assert "*NODE FILE" not in body and "*EL FILE" not in body
    # later steps of the kind keep it and get it again, with their procedure's variables and
    # default frequency (ccx would keep the earlier step's); a perturbation step after a
    # general one gets the default
    body, _, rep = convert_str(HEX + "*Step\n*Static\n*End Step\n*Step\n*Static\n*End Step\n"
                               "*Step\n*Dynamic\n0.01, 1.\n*End Step\n*Step\n*Frequency\n3\n"
                               "*End Step\n")
    assert _step(body, 2).endswith("*NODE FILE\nU, RF\n*EL FILE\nS, E\n")
    assert _step(body, 3).endswith("*NODE FILE, FREQUENCY=10\nU, V, RF\n*EL FILE\nS, E\n")
    assert _step(body, 4).endswith("*NODE FILE\nU\n")
    assert "carries over an earlier step's preselected field output" in rep.text()
    # the deck's own field requests are what Abaqus writes, also in the steps after them
    body, _, _ = convert_str(HEX + "*Step\n*Static\n*Output, field\n*Node Output\nU\n*End Step\n"
                             "*Step\n*Static\n*End Step\n")
    assert "*EL FILE" not in body and _step(body, 2).endswith("*NODE FILE\nU\n")


def test_carried_output_requests_written_again():
    # ccx keeps a step's output cards for later steps, but at that step's frequency or time
    # points and as a step in between left them; Abaqus carries the requests themselves over,
    # so a step without requests of its own gets them again: here the time points of its own
    # period, a FREQUENCY where ccx stops on time points (DIRECT), the static default after a
    # dynamic step, and the variables a perturbation step replaced in ccx
    body, _, _ = convert_str(HEX + "*Step, nlgeom\n*Static\n0.1, 1.\n*Output, field, "
                             "variable=PRESELECT, number interval=4\n*End Step\n*Step, nlgeom\n"
                             "*Static\n0.1, 3.\n*End Step\n*Step, nlgeom\n*Static, direct\n0.5, 1.\n"
                             "*End Step\n")
    assert "*TIME POINTS, NAME=ABQ2CCX_TP2, GENERATE\n0.75, 3., 0.75\n" in body
    assert "*NODE FILE, TIME POINTS=ABQ2CCX_TP2\nU, RF\n" in _step(body, 2)
    assert "*NODE FILE, FREQUENCY=1\nU, RF\n" in _step(body, 3)
    body, _, _ = convert_str(HEX + "*Step\n*Dynamic\n0.01, 1.\n*End Step\n*Step\n*Static\n*End Step\n")
    assert _step(body, 2).endswith("*NODE FILE, FREQUENCY=1\nU, RF\n*EL FILE\nS, E\n")
    body, _, _ = convert_str(HEX + "*Step\n*Static\n*Output, field\n*Node Output\nRF, U\n*Element "
                             "Output\nS\n*End Step\n*Step, perturbation\n*Frequency\n3\n" + PRESELECT +
                             "*End Step\n*Step\n*Static\n*End Step\n")
    assert _step(body, 2).endswith("*NODE FILE\nU\n")
    assert _step(body, 3).endswith("*NODE FILE\nRF, U\n*EL FILE\nS\n")
    # named variables beside a preselected request stay, at the request's own frequency
    body, _, _ = convert_str(HEX + "*Step\n*Static\n*Output, field, variable=PRESELECT, frequency=5\n"
                             "*Element Output\nENER\n*End Step\n*Step\n*Dynamic\n0.01, 1.\n*End Step\n")
    assert _step(body, 2).endswith("*NODE FILE\nU, V, RF\n*EL FILE\nS, E\n*EL FILE\nENER\n")
    # OP=ADD keeps the requests in force (here Abaqus' default) beside the new ones
    body, _, _ = convert_str(HEX + "*Step\n*Static\n*Output, field, op=add\n*Element Output\nENER\n"
                             "*End Step\n")
    assert _step(body, 1).endswith("*EL FILE\nENER\n*NODE FILE\nU, RF\n*EL FILE\nS, E\n")
    # an explicit step gets its own FREQUENCY (20 intervals of 1e-2 over ccx's 8.847e-8)
    body, _, _ = convert_str(HEX + STEEL + "*Step\n*Dynamic, Explicit\n, 1.e-4\n" + PRESELECT +
                             "*End Step\n*Step\n*Dynamic, Explicit\n, 1.e-2\n*End Step\n")
    assert "*NODE FILE, FREQUENCY=56\n" in _step(body, 1)
    assert "*NODE FILE, FREQUENCY=5651\n" in _step(body, 2)
    # FREQUENCY=0: nothing written, one note
    body, _, rep = convert_str(HEX + "*Step\n*Static\n*Output, field, variable=PRESELECT, "
                               "frequency=0\n*End Step\n*Step\n*Static\n*End Step\n")
    assert "*NODE FILE" not in body and "*EL FILE" not in body
    assert "Abaqus writes none of it" in rep.text() and "*NODE OUTPUT dropped" not in rep.text()


def test_explicit_output_frequency_from_ccx_stable_increment():
    # ccx ignores TIME POINTS in explicit dynamics and writes every increment unless given a
    # FREQUENCY; its increment is its Courant estimate (calcstabletimeincvol.f): 8.847e-8 for
    # a unit C3D8 cube of steel, as ccx 2.23 prints it.  Abaqus' default 20 field intervals of
    # 1e-4 -> every 5e-6 -> FREQUENCY=56
    body, conv, rep = convert_str(HEX + STEEL + "*Step\n*Dynamic, Explicit\n, 1.e-4\n*End Step\n")
    assert "*NODE FILE, FREQUENCY=56\nU, V, RF\n*EL FILE\nS, E\n" in _step(body, 1)
    assert "from ccx's stable increment 8.85e-08" in rep.text()
    assert abs(conv._explicit_stable_increment([], None) / 8.847263e-08 - 1) < 1e-6
    # a smaller maximum increment (4th field) sets it; the *OUTPUT's NUMBER INTERVAL counts
    body, _, rep = convert_str(HEX + STEEL + "*Step\n*Dynamic, Explicit\n, 1.e-4, , 1.e-8\n" +
                               PRESELECT.replace("\n", ", number interval=4\n") + "*End Step\n")
    assert "*NODE FILE, FREQUENCY=2500\nU, V, RF\n" in body and "maximum increment 1e-08" in rep.text()


def test_preselect_output_examples():
    # the validate_with_ccx.py decks: Abaqus/CAE's default requests on a bar in tension, and
    # an explicit bar impact without output requests (FREQUENCY=4: ccx's increment 8.85e-7
    # into 20 intervals of 7.7336e-5)
    body, _, _ = convert(os.path.join(EXAMPLES, "preselect_output_bar.inp"))
    assert "*CLOAD\nTIP, 1, 250.\n*NODE FILE\nU, RF\n*EL FILE\nS, E\n*END STEP" in body
    assert not dangling_refs(reparse(body))
    body, _, _ = convert(os.path.join(EXAMPLES, "explicit_default_output_bar.inp"))
    assert _step(body, 1).endswith("*NODE FILE, FREQUENCY=4\nU, V, RF\n*EL FILE\nS, E\n")
    assert not dangling_refs(reparse(body))
    # two blocks pressed together: the contact output in step 1 and, carried, in step 2
    body, _, _ = convert(os.path.join(EXAMPLES, "preselect_contact_blocks.inp"))
    for k in (1, 2):
        assert _step(body, k).endswith("*NODE FILE\nU, RF\n*EL FILE\nS, E\n*CONTACT FILE\nCDIS, CSTR\n")
    assert not dangling_refs(reparse(body))


def test_courant_length_matches_ccx_223():
    # h * f of ccx's explicit increment estimate against the increments ccx 2.23 printed for
    # one element of each type (steel: c = 6.0010e6; dt = 0.8/1.3 * 1.91722 * h f / (2 c)).
    # C3D8R's factor is 0.625 in 2.23 (0.938 in later sources); shells, membranes and plane
    # elements are sized through their thickness, axisymmetric ones as a 2-degree sector at
    # their mean radius, beams by their section (a CIRC one as the box around the circle)
    c = math.sqrt(210000. * 0.7 / (1.3 * 0.4 * 7.85e-9))
    k = 0.8 / 1.3 * A.Converter._critom(None) / (2 * c)

    def mid(a, b):
        return tuple((x + y) / 2 for x, y in zip(a, b))
    box = [(0, 0, 0), (1, 0, 0), (1, 2, 0), (0, 2, 0), (0, 0, 3), (1, 0, 3), (1, 2, 3), (0, 2, 3)]
    box20 = box + [mid(box[i], box[j]) for i, j in ((0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6),
                                                   (6, 7), (7, 4), (0, 4), (1, 5), (2, 6), (3, 7))]
    tet = [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)]
    tet10 = tet + [mid(tet[i], tet[j]) for i, j in ((0, 1), (1, 2), (2, 0), (0, 3), (1, 3), (2, 3))]
    wed = [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 2), (1, 0, 2), (0, 1, 2)]
    quad = [(0, 0, 0), (2, 0, 0), (2, 3, 0), (0, 3, 0)]
    quad8 = quad + [mid(quad[i], quad[(i + 1) % 4]) for i in range(4)]
    tri = [(0, 0, 0), (2, 0, 0), (0, 2, 0)]
    axi = [(10, 0, 0), (12, 0, 0), (12, 2, 0), (10, 2, 0)]
    line2, line3 = [(0, 0, 0), (1, 0, 0)], [(0, 0, 0), (0.5, 0, 0), (1, 0, 0)]
    rect = {"rect": (0.2, 0.3)}
    probes = [("C3D8", box, {}, 8.847263e-08), ("C3D8R", box, {}, 6.143933e-08),
              ("C3D8I", box, {}, 1.228787e-08), ("C3D20R", box20, {}, 2.949088e-08),
              ("C3D4", tet, {}, 5.675522e-08), ("C3D10", tet10, {}, 1.702657e-08),
              ("C3D6", wed, {}, 6.951066e-08), ("S4R", quad, {"t": 0.5}, 3.071966e-08),
              ("S4", quad, {"t": 0.5}, 6.143933e-09), ("S8R", quad8, {"t": 0.5}, 1.474544e-08),
              ("S3", tri, {"t": 0.5}, 4.915146e-08), ("M3D4", quad, {"t": 0.5}, 4.423631e-08),
              ("CPS4R", quad, {"t": 0.5}, 3.071966e-08), ("CAX4R", axi, {}, 2.358622e-08),
              ("CAX4", axi, {}, 3.396415e-08), ("B31", line2, rect, 2.457573e-09),
              ("B31R", line2, rect, 1.228787e-08), ("B32R", line3, rect, 5.898175e-09),
              ("B32", line3, {"circ": 0.1}, 4.170640e-09)]
    for typ, pts, sec, dt in probes:
        got = k * A.courant_length(typ, pts, sec)
        assert abs(got / dt - 1) < 2e-4, (typ, got, dt)
    assert A.courant_length("SPRINGA", line2, {}) is None and A.courant_length("S4", quad, {}) is None
    # ccx runs B21 / T2D2 as B31 / T3D2 (sized as C3D8I)
    assert A.courant_length("B21", line2, rect) == A.courant_length("B31", line2, rect)
    assert A.courant_length("T2D2", line2, {"area": 0.04}) == A.courant_length("T3D2", line2, {"area": 0.04})
    # a cohesive layer (a thin continuum in ccx) sizes the increment; short LAMINA data is
    # skipped, not a crash
    glue = ("*Node\n9, 0.,0.,1.01\n10, 1.,0.,1.01\n11, 1.,1.,1.01\n12, 0.,1.,1.01\n*Element, "
            "type=COH3D8, elset=GLUE\n2, 5,6,7,8,9,10,11,12\n*Material, name=G\n*Elastic\n"
            "1000., 0.3\n*Density\n1e-9\n*Cohesive Section, elset=GLUE, material=G, "
            "response=continuum\n")
    _, conv, _ = convert_str(HEX + STEEL + glue + "*Step\n*Dynamic, Explicit\n, 1.e-4\n*End Step\n")
    assert conv._courant[1] == 2
    lamina = STEEL.replace("*Elastic\n210000., 0.3", "*Elastic, type=LAMINA\n100000., 8000.")
    _, conv, _ = convert_str(HEX + lamina + "*Step\n*Dynamic, Explicit\n, 1.e-4\n*End Step\n")
    assert conv._courant is False


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


def test_blankless_spellings_of_handled_and_tabled_keywords():
    # *ENERGYPRINT is the output request *ENERGY PRINT (a note, no reduced physics), and
    # *ROTARYINERTIA / *SECTIONCONTROLS reach their handlers like the spellings with blanks
    plain = HEX + "*Material, name=M\n*Elastic\n1000., 0.3\n*Solid Section, elset=EALL, material=M\n"
    step = "*Boundary\n1, 1, 3\n*Step\n*Static\n*Cload\n7, 3, 1.\n*EnergyPrint\n*End Step\n"
    _, conv, rep = convert_str(plain + step)
    assert "*ENERGY PRINT: an output" in rep.text() and conv.reduced_physics == []
    sc = plain.replace("material=M\n", "material=M, controls=EC\n") + \
        "*SectionControls, name=EC, second order accuracy=YES\n1., 1., 1.\n" + step
    _, conv, rep = convert_str(sc)
    assert conv.reduced_physics == [] and "changes nothing" in rep.text()
    deck = RIGID_PLATE + ("*ELEMENT, TYPE=MASS, ELSET=PM\n10, 9\n*MASS, ELSET=PM\n6.\n"
                          "*ELEMENT, TYPE=ROTARYI, ELSET=PI\n11, 9\n*ROTARYINERTIA, ELSET=PI\n"
                          "1.5, 2., 1., 0., 0., 0.\n*STEP\n*FREQUENCY\n3\n*END STEP\n")
    body, conv, _ = convert_str(deck)
    assert "*MASS, ELSET=ABQ2CCX_STAR" in body and conv.reduced_physics == []


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
DEFAULT_IC = ("** abq2ccx: initial temperatures: the Abaqus default, 0, at every node (ccx reads "
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


def test_transient_heat_transfer_fixed_increments_and_initial_temperatures():
    # Abaqus' transient *HEAT TRANSFER without DELTMX takes fixed increments of its initial
    # increment (2017 "Uncoupled heat transfer analysis"), ccx its own unless DIRECT; and with no
    # initial temperatures Abaqus starts from 0, where ccx 2.23 stops ("please define initial
    # conditions for the temperature") — NAFEMS T3: 30.29 against Abaqus' 36.09 before
    deck = HEX + ("*Material, name=M\n*Conductivity\n35.\n*Density\n7200.\n*Specific Heat\n440.5\n"
                  "*Solid Section, elset=EALL, material=M\n*Step\n*Heat Transfer{}\n1., 32.\n"
                  "*Boundary\n1, 11, 11, 10.\n*End Step\n")
    body, _, rep = convert_str(deck.format(""))
    assert "*HEAT TRANSFER, DIRECT\n1., 32." in body and "-> DIRECT" in rep.text()
    assert "*INITIAL CONDITIONS, TYPE=TEMPERATURE\nABQ2CCX_ALL_NODES, 0.\n*STEP" in body
    assert "ccx 2.23 stops without initial temperatures" in rep.text()
    body, _, _ = convert_str(deck.format(", deltmx=5."))              # automatic in both
    assert "*HEAT TRANSFER, DELTMX=5.\n" in body and body.count("INITIAL CONDITIONS") == 1
    body, _, _ = convert_str(deck.format(", steady state"))          # no time, no start state
    assert "DIRECT" not in body and "INITIAL CONDITIONS" not in body
    body, _, _ = convert_str(deck.format("").replace("*Step", "*Initial Conditions, type=temperature\n"
                                                     "EALL, 20.\n*Step"))
    assert "Abaqus default" not in body


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
    # element midpoints, B32R in ccx's end, middle, end order; ids and the elset are kept
    assert "*ELEMENT, TYPE=B32R\n1, 1, 4, 2\n2, 2, 5, 3\n" in body
    assert conv.geom.nodes[4] == (0.5, 0.0, 0.0) and conv.geom.nodes[5] == (1.5, 0.0, 0.0)
    assert "*ELSET, ELSET=BEAM\n1, 2\n" in body and "3-node beams (B31 -> B32R: 2)" in rep.text()
    # ccx reads the CIRC dimensions as the two diameters: Abaqus radius 0.05 -> 0.1, 0.1
    assert "SECTION=CIRC\n0.1, 0.1\n0., 0., -1." in body
    body, _, _ = convert_str(CIRC_BEAM.replace("type=B31", "type=B31R"))
    assert "*ELEMENT, TYPE=B32R\n1, 1, 4, 2\n" in body
    body, _, _ = convert_str(CIRC_BEAM.replace("type=B31", "type=B21"))   # ccx runs B21 as B31
    assert "*ELEMENT, TYPE=B32R\n1, 1, 4, 2\n" in body
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
    assert typ == "B32R" and conn == [1, 3, 2]
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


def test_circ_beam_midside_node_and_couplings_whatever_else_the_deck_has():
    # a coupling on both beam ends keeps them alone (_MIDSIDE_SET_CARDS); the midside node
    # used to join it as soon as a composite shell elsewhere was upgraded (_extend_edge_sets)
    shell = ("*Node\n201, 5., 5., 0.\n202, 6., 5., 0.\n203, 6., 6., 0.\n204, 5., 6., 0.\n"
             "*Element, type=S4R, elset=PLATE\n201, 201, 202, 203, 204\n"
             "*Shell Section, elset=PLATE, composite\n0.1, 3, M, , 0.\n0.1, 3, M, , 90.\n")
    cpl = "*Node\n100, 0.5, 1., 0.\n*Kinematic Coupling, ref node=100\n1, 1, 6\n2, 1, 6\n"
    for deck in (CIRC_BEAM + cpl, CIRC_BEAM + shell + cpl):
        body, _, rep = convert_str(deck)
        assert _card_at(body, "*SURFACE, TYPE=NODE, NAME=ABQ2CCX_KC1_1") == ["1", "2"]
        assert "*KINEMATIC COUPLING lines given" not in rep.text()


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


def test_quadratic_beams_run_as_b32r():
    # Abaqus integrates its 3-node beams at 2 points along the beam, as ccx's B32R (its B32 at
    # 3, which locks): the same element, on the same nodes, whatever the section
    body, conv, rep = convert_str(B32_PIPE_BEAM)
    assert "*ELEMENT, TYPE=B32R\n1, 1, 2, 3\n" in body and len(conv.geom.nodes) == 3
    assert "Element B32 -> B32R: the same solution" in rep.text() and not conv.reduced_physics
    assert "midside" not in rep.text()
    for typ, sec in (("B32", "section=CIRC\n0.05"), ("B32", "section=RECT\n0.1, 0.2"),
                     ("B22", "section=RECT\n0.1, 0.2"), ("B32H", "section=RECT\n0.1, 0.2"),
                     ("PIPE32", "section=PIPE\n0.05, 0.01"), ("PIPE22", BOX_DATA)):
        body, conv, rep = convert_str(B32_PIPE_BEAM.replace("type=B32", f"type={typ}")
                                      .replace("section=PIPE\n0.05, 0.01", sec))
        assert "*ELEMENT, TYPE=B32R\n1, 1, 2, 3\n" in body, typ
        # the hybrid and pipe elements' own physics is dropped, not the beam's integration
        assert bool(conv.reduced_physics) == (typ in ("B32H", "PIPE32", "PIPE22")), typ

def test_mixed_section_beams_report_each_case():
    deck = ("*Node\n1, 0., 0., 0.\n2, 1., 0., 0.\n3, 2., 0., 0.\n4, 3., 0., 0.\n5, 3.5, 0., 0.\n"
            "6, 4., 0., 0.\n*Element, type=B31, elset=ROD\n1, 1, 2\n*Element, type=B31, elset=TUBE\n"
            "2, 2, 3\n*Element, type=B32, elset=BOXB\n3, 4, 5, 6\n"
            "*Beam Section, elset=ROD, material=M, section=CIRC\n0.05\n0., 0., -1.\n"
            "*Beam Section, elset=TUBE, material=M, section=PIPE\n0.05, 0.01\n0., 0., -1.\n"
            "*Beam Section, elset=BOXB, material=M, section=BOX\n0.1, 0.1, 0.01, 0.01, 0.01, 0.01\n"
            "*Material, name=M\n*Elastic\n2.1e5, 0.3\n")
    body, conv, rep = convert_str(deck)
    assert "*ELEMENT, TYPE=B32R\n1, 1, 7, 2\n2, 2, 8, 3\n*ELEMENT, TYPE=B32R\n3, 4, 5, 6\n" in body
    # one line naming the sections and ccx's reasons; the B32 is B32R anyway (no message)
    assert "SECTION=CIRC/PIPE beams: 2 2-node element(s) emitted as 3-node beams (B31 -> B32R: " \
           "2), each with a new midside node at its midpoint (nodes 7-8); ccx 2.23 stops on linear " \
           "beams with a circular section and accepts PIPE and BOX sections only on B32R." in rep.text()
    assert "SECTION=BOX" not in rep.text()
    assert conv.reduced_physics == ["element B31 -> B32R (SECTION=CIRC/PIPE needs a 3-node beam in ccx)"]
    # an element under both a PIPE and a later CIRC section is reported under PIPE
    body, _, rep = convert_str(PIPE_BEAM + "*Beam Section, elset=BEAM, material=M, section=CIRC\n0.05\n")
    assert "*ELEMENT, TYPE=B32R\n1, 1, 4, 2\n" in body and "SECTION=PIPE beams" in rep.text()

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
    assert [t for t, _ in g.elements.values()] == ["B32R"] * 20 and len(g.nodes) == 41
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
    assert "*ELEMENT, TYPE=B32R\n1, 1, 2, 3\n" in body and conv.geom.nset("ABQ2CCX_PLANAR") == [1, 2, 3]
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
    # a B21 under a circular section becomes a B32R with midside nodes 5-7 (ccx 2.23 rejects
    # linear CIRC beams); they would move out of plane just the same
    body, conv, _ = convert_str(PLANAR_BEAM.replace("section=RECT\n0.1, 0.2", "section=CIRC\n0.05"))
    assert "*ELEMENT, TYPE=B32R\n1, 1, 5, 2\n" in body
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
    # ... and never at a node with a *TRANSFORM (ccx would read the BC in its local axes)
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


def test_planar_constraint_skips_coupled_and_tied_nodes():
    # a *COUPLING's surface nodes and the slave nodes of a *TIE or a tied *CONTACT PAIR follow
    # their constraint (these decks once stopped the converter: AttributeError)
    tip = "*Nset, nset=TIP\n4\n*Surface, name=TIPS, type=NODE\nTIP\n"
    coupling = "*Node\n5, 3., 0.\n" + tip + "*Coupling, ref node=5, surface=TIPS, constraint name=C\n*Kinematic\n"
    _, conv, rep = convert_str(PLANAR_BEAM.replace("*Step", coupling + "*Step", 1))
    assert conv.geom.nset("ABQ2CCX_PLANAR") == [1, 2, 3]
    assert "1 node(s) whose DOF 3 an *EQUATION, *MPC, rigid body, coupling or *TIE" in rep.text()
    base = tip + "*Elset, elset=E1\n1\n*Surface, name=BASE\nE1, SPOS\n"
    for tie in ("*Tie, name=T\nTIPS, BASE\n",
                "*Surface Interaction, name=SI\n*Contact Pair, interaction=SI, tied\nTIPS, BASE\n"):
        _, conv, _ = convert_str(PLANAR_BEAM.replace("*Step", base + tie + "*Step", 1))
        assert conv.geom.nset("ABQ2CCX_PLANAR") == [1, 2, 3], tie


def test_planar_constraint_repeated_after_op_new():
    # *BOUNDARY, OP=NEW removes the model-data constraint as well (verified on ccx 2.23);
    # here it removes node 4's support
    step2 = "*End Step\n*Step\n*Static\n*Boundary, op=NEW\n1, ENCASTRE\n*Cload\n4, 2, -1.\n*End Step\n"
    deck = PLANAR_BEAM.replace("1, ENCASTRE\n", "1, ENCASTRE\n4, 2, 2\n").replace("*End Step\n", step2)
    body, conv, _ = convert_str(deck)
    first, second = body.split("*STEP")[1:]
    assert "ABQ2CCX_PLANAR" not in first
    assert "*BOUNDARY, OP=NEW\n1, 1, 6\n** abq2ccx: planar constraint re-applied (OP=NEW removed " \
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
    # Abaqus/CAE writes OP=NEW on every *BOUNDARY of such a step: a later card keeps the ones
    # before it in the step (the knot depended on the order of the cards)
    for cards in ("3, 4, 4\n*Boundary, op=NEW\n1, 1, 6\n", "1, 1, 6\n*Boundary, op=NEW\n3, 4, 4\n"):
        _, conv, _ = convert_str(CIRC_BEAM + "*Step\n*Static\n*Boundary, op=NEW\n" + cards +
                                 "*Cload\n2, 2, -1.\n*End Step\n")
        assert list(conv._knots) == [3], cards
    # a node with a *TRANSFORM gets its knot from _plan_transformed_rotations, which writes the
    # local rotation in global components there (local 1 = y: DOF 5); none in a heat-transfer-
    # only deck
    body, conv, _ = convert_str(CIRC_BEAM + "*Nset, nset=TURN\n1\n*Transform, nset=TURN\n"
                                "0., 1., 0., -1., 0., 0.\n*Boundary\n1, 1, 4\n3, 2, 4\n" + CIRC_STATIC)
    assert list(conv._knots) == [3, 1] and conv._rot_mode == {1: "global"}
    assert {"1,1,3", "1,5,5"} <= set(_bc_lines(body))
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
    assert {t for t, _ in g.elements.values()} == {"B32R", "B31"} and not dangling_refs(g)
    # ... and the planar circular beam's twist held at the first element's middle node
    body, conv, _ = convert(os.path.join(EXAMPLES, "planar_pinned_circ_beam.inp"))
    g = reparse(body)
    assert g.elements[1] == ("B32R", [1, 22, 2]) and not conv._knots
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
            "*Orientation, name=Ori-1\n1., 0., 0., 0., 1., 0.\n3, 0.\n"
            "*Orientation, name=Ori-2\n0., 1., 0., -1., 0., 0.\n3, 0.\n{}*End Part\n"
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
                      "*Orientation, name=OP\nDP\n3, 0.\n*Orientation, name=OM\nDM\n3, 0.\n"
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
    assert second.count("** abq2ccx: OP=NEW dropped") == 1 and "*BOUNDARY\n1, 4, 6\n" in second
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
    # in Abaqus a frequency step is a perturbation step: its cards do not carry over (ccx's
    # do), so its OP=NEW removes a prescribed value only in ccx — which the conversion gives
    # back in step 3 (_restore_base_states)
    freq = ("*Step\n*Static\n*Boundary\n7, 1, 1, 0.5\n*End Step\n*Step\n*Frequency\n3\n"
            "*Boundary, op=NEW\n7, 1, 1\n*End Step\n*Step\n*Static\n*End Step\n")
    blocks = A.blocks_from_lines(freq.splitlines())
    assert A.step_load_audit(blocks, True, abaqus=True)[2] == ["*BOUNDARY: prescribed value on 7"]
    assert A.step_load_audit(blocks, False)[2] == []
    body, conv, rep = convert_str(HEX + freq)
    assert "*BOUNDARY, AMPLITUDE=ABQ2CCX_HOLD\n7, 1, 1, 0.5\n" in body.split("*STEP")[3]
    assert not conv.unloaded_steps and "Step 3 is loaded in the Abaqus deck" not in rep.text()
    blocks = A.blocks_from_lines(freq.replace("*Boundary, op=NEW\n7, 1, 1\n", "*Cload\n7, 1, 1.\n")
                                 .splitlines())
    assert A.step_load_audit(blocks, True, abaqus=True)[2] == ["*BOUNDARY: prescribed value on 7"]


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


# a static step (a load, a pressure, a prescribed displacement, temperatures), a *FREQUENCY
# step with the given cards, and a static step with the given cards
PERT = (HEX + "*Nset, nset=ALL, generate\n1, 8, 1\n*Material, name=M\n*Elastic\n1000., 0.\n"
        "*Density\n1e-3\n*Expansion\n1e-3\n*Solid Section, elset=EALL, material=M\n"
        "*Initial Conditions, type=temperature\nALL, 0.\n*Boundary\n1, 1, 3\n2, 2, 3\n4, 3, 3\n"
        "*Step\n*Static\n*Cload\n7, 1, 1.\n*Dload\n1, P2, 1.\n*Boundary\n8, 2, 2, 0.1\n"
        "*Temperature\nALL, 100.\n*End Step\n"
        "*Step\n*Frequency\n3\n{}*End Step\n*Step\n*Static\n{}*End Step\n")


def test_general_step_after_perturbation_gets_the_base_state():
    # Abaqus continues from the last general step's state after a linear perturbation step;
    # ccx 2.23 carries the perturbation step's loads and BCs on (probed: its *CLOAD loaded
    # step 3, its BC held node 6) and zeroes prescribed BC values.  So step 3 starts with the
    # base state given again, at once (the constant amplitude), without the load it gives
    # itself (ccx adds up a load given twice in one step), and with OP=NEW on the *BOUNDARY
    # where the perturbation step held a DOF the base state leaves free
    body, conv, rep = convert_str(PERT.format("*Cload\n7, 2, 1.\n*Boundary\n6, 1, 1, 0.5\n",
                                              "*Cload\n7, 1, 2.\n"))
    steps = body.split("*STEP")
    assert steps[0].endswith("*AMPLITUDE, NAME=ABQ2CCX_HOLD\n0., 1., 1., 1.\n")
    assert "HOLD" not in steps[1] + steps[2] and "OP=NEW" not in steps[2]
    assert steps[3].startswith("\n*STATIC\n** abq2ccx: the loads, BCs and temperatures of step 1 "
                               "given again (linear perturbation step(s) 2 in between)\n"
                               "*BOUNDARY, OP=NEW, AMPLITUDE=ABQ2CCX_HOLD\n1, 1, 3\n2, 2, 3\n4, 3, 3\n"
                               "8, 2, 2, 0.1\n*CLOAD, OP=NEW\n*DLOAD, OP=NEW, AMPLITUDE=ABQ2CCX_HOLD\n"
                               "1, P2, 1.\n*TEMPERATURE, OP=NEW, AMPLITUDE=ABQ2CCX_HOLD\nALL, 100.\n"
                               "*CLOAD\n7, 1, 2.\n"), steps[3]
    assert "Step 3 follows a linear perturbation step" in rep.text()
    assert not conv.reduced_physics and not conv.unloaded_steps
    # a changed value needs no OP=NEW; nor does a *FREQUENCY step without cards, after which
    # ccx 2.23 still has zeroed the prescribed values (from the first nonzero line on)
    third = convert_str(PERT.format("*Boundary\n8, 2, 2, 0.3\n", ""))[0].split("*STEP")[3]
    assert "*BOUNDARY, AMPLITUDE=ABQ2CCX_HOLD\n1, 1, 3\n2, 2, 3\n4, 3, 3\n8, 2, 2, 0.1\n" \
           "*CLOAD, OP=NEW, AMPLITUDE=ABQ2CCX_HOLD\n7, 1, 1.\n" in third
    third = convert_str(PERT.format("", ""))[0].split("*STEP")[3]
    assert "*BOUNDARY, AMPLITUDE=ABQ2CCX_HOLD\n8, 2, 2, 0.1\n*CLOAD, OP=NEW" in third
    # a card the step gives with OP=NEW is left to it (it removes the base state in Abaqus too)
    third = convert_str(PERT.format("", "*Cload, op=NEW\n7, 2, 1.\n*Boundary, op=NEW\n1, 1, 3\n"
                                        "2, 2, 3\n4, 3, 3\n"))[0].split("*STEP")[3]
    assert third.count("*CLOAD") == third.count("*BOUNDARY") == 1 and "\n*DLOAD, OP=NEW" in third
    # without a perturbation step nothing changes
    body, _, rep = convert_str(PERT.replace("*Step\n*Frequency\n3\n{}*End Step\n", "").format(""))
    assert "HOLD" not in body and "perturbation" not in rep.text()


def test_base_state_after_perturbation_values_and_keys():
    deck = HEX + ("*Material, name=M\n*Elastic\n1000., 0.\n*Density\n1e-3\n*Solid Section, elset=EALL, "
                  "material=M\n*Boundary\n1, 1, 3\n2, 2, 3\n4, 3, 3\n*Nset, nset=TOP\n5, 6, 7, 8\n"
                  "*Amplitude, name=A\n0., 0., 2., 4.\n*Amplitude, name=T, time=total time\n0., 0., 10., 10.\n"
                  "*Step\n*Static\n0.5, 1.\n{}*End Step\n*Step\n*Frequency\n3\n*End Step\n"
                  "*Step\n*Static\n{}*End Step\n")
    # a step-time amplitude's value at the end of its step (A(1) = 2: ccx and Abaqus hold it
    # there), a TIME=TOTAL TIME one kept as it is
    body, _, _ = convert_str(deck.format("*Cload, amplitude=A\n7, 1, 1.\n*Cload, amplitude=T\n7, 2, 1.\n",
                                         ""))
    assert "*CLOAD, OP=NEW, AMPLITUDE=ABQ2CCX_HOLD\n7, 1, 2.\n*CLOAD, AMPLITUDE=T\n7, 2, 1.\n" in body
    # the step's own loads are left out: a set's other nodes are given one by one, a face
    # load on an element of a set it loads goes; a body load is one per set and direction
    body, _, _ = convert_str(deck.format("*Cload\nTOP, 3, -1.\n*Dload\nEALL, P2, 1.\n"
                                         "EALL, GRAV, 9.81, 0., 0., -1.\n",
                                         "*Cload\n7, 3, -2.\n*Dload\n1, P2, 2.\n"))
    assert ("*CLOAD, OP=NEW, AMPLITUDE=ABQ2CCX_HOLD\n5, 3, -1.\n6, 3, -1.\n8, 3, -1.\n"
            "*DLOAD, OP=NEW, AMPLITUDE=ABQ2CCX_HOLD\nEALL, GRAV, 9.81, 0., 0., -1.\n"
            "*CLOAD\n7, 3, -2.\n*DLOAD\n1, P2, 2.\n") in body


def test_perturbation_step_nodal_forces_do_not_carry_over():
    # converted loads (nodal forces) of a perturbation step are not the state the next step
    # starts from: step 3 re-gives its own traction (the same as step 2's), or none
    deck = (HEX + "*Material, name=M\n*Elastic\n1000., 0.\n*Density\n1e-3\n*Solid Section, elset=EALL, "
            "material=M\n*Boundary\n1, 1, 3\n2, 2, 3\n4, 3, 3\n*Surface, name=S2\nEALL, S2\n"
            "*Step\n*Static\n*Dsload\nS2, TRVEC, 1., 1., 0., 0.\n*End Step\n*Step\n*Frequency\n3\n"
            "*Dsload\nS2, TRVEC, 2., 1., 0., 0.\n*End Step\n*Step\n*Static\n{}*End Step\n")
    body, _, _ = convert_str(deck.format("*Dsload\nS2, TRVEC, 2., 1., 0., 0.\n"))
    assert _cloads(body)[2] == {(n, 1): 0.5 for n in (5, 6, 7, 8)}
    assert "*CLOAD, OP=NEW\n** abq2ccx: S2, TRVEC" in body
    body, _, _ = convert_str(deck.format(""))
    assert _cloads(body)[2] == {(n, 1): 0.25 for n in (5, 6, 7, 8)}
    assert "*CLOAD, OP=NEW, AMPLITUDE=ABQ2CCX_HOLD\n5, 1, 0.25" in body


def test_base_state_after_a_first_perturbation_step_beams_and_couplings():
    # a perturbation step first: the base state is the model data's
    deck = (HEX + "*Material, name=M\n*Elastic\n1000., 0.\n*Density\n1e-3\n*Solid Section, elset=EALL, "
            "material=M\n*Boundary\n1, 1, 3\n2, 2, 3\n4, 3, 3\n*Step\n*Frequency\n3\n*Boundary\n"
            "6, 1, 1\n*End Step\n*Step\n*Static\n*Cload\n7, 1, 1.\n*End Step\n")
    second = convert_str(deck)[0].split("*STEP")[2]
    assert second.startswith("\n*STATIC\n** abq2ccx: the loads, BCs and temperatures before the "
                             "first step given again (linear perturbation step(s) 1 in between)\n"
                             "*BOUNDARY, OP=NEW, AMPLITUDE=ABQ2CCX_HOLD\n1, 1, 3\n2, 2, 3\n4, 3, 3\n"
                             "*CLOAD\n7, 1, 1.\n"), second
    # the restore's OP=NEW would break the clamp's rotations in ccx 2.23: it gets a knot
    deck = STEPPED_BEAM + "*Step\n*Frequency\n2\n*Boundary\n3, 2, 2\n*End Step\n*Step\n*Static\n*End Step\n"
    body, conv, rep = convert_str(deck)
    assert "*BOUNDARY, OP=NEW, AMPLITUDE=ABQ2CCX_HOLD\n1, 1, 6\n" in body and list(conv._knots) == [1]
    assert "OP=NEW in step(s) 3 removes boundary conditions" in rep.text()
    # a reference-node BC of the perturbation step does not impose step 3's member BC, nor
    # does its hold on the rotations make step 3 start unturned (_bc_states, _coupled_steps)
    kin = (HEX + "*Node\n100,0.5,0.5,2.\n*Nset,nset=TOP\n5,6,7,8\n*Surface, type=node, name=ST\n"
           "TOP\n*Coupling, constraint name=C, ref node=100, surface=ST\n*Kinematic\n*Boundary\n{}\n"
           "*Step\n*Static\n*End Step\n*Step\n*Frequency\n2\n*Boundary\n{}\n*End Step\n"
           "*Step\n*Static\n*Boundary\n{}TOP, 1, 1\n*End Step\n")
    body, _, rep = convert_str(kin.format("100, 4, 6", "100, 1, 1", ""))
    assert _bc_lines(body) == ["100,4,6", "100,1,1", "100,4,6", "TOP,1,1"]
    assert "*BOUNDARY, OP=NEW, AMPLITUDE=ABQ2CCX_HOLD\n100, 4, 6\n*BOUNDARY\nTOP, 1, 1\n" in body
    assert "Possible overconstraint" in rep.text()
    body, _, rep = convert_str(kin.format("100, 1, 3", "100, 4, 6", "100, 4, 6\n"))
    assert _bc_lines(body)[-1] == "TOP,1,1" and "Possible overconstraint" in rep.text()


def test_dload_without_element_set_loads_the_whole_model():
    body, _, _ = convert_str(HEX + "*Step\n*Static\n*Dload\n, GRAV, 9.81, 0., 0., -1.\n*End Step\n")
    assert "\nABQ2CCX_ALL_ELEMENTS, GRAV, 9.81, 0., 0., -1." in body
    assert "*ELSET, ELSET=ABQ2CCX_ALL_ELEMENTS\n1\n" in body


def test_dload_blank_fields_stay_in_place():
    # Abaqus reads a blank data field as zero.  Dropped, it moved the fields after it up: ccx
    # read 'EALL, GRAV, 9810., , , -1.' as gravity along -x, and a CENTRIF line with a blank
    # axis point as one with no axis direction (NaN results; probed on 2.23)
    deck = HEX + "*Step\n*Static\n*Dload\n{}\n*End Step\n"
    for src, want in (("EALL, GRAV, 9810., , , -1.", "EALL, GRAV, 9810., 0., 0., -1."),
                      (", GRAV, 9810., , , -1.", "ABQ2CCX_ALL_ELEMENTS, GRAV, 9810., 0., 0., -1."),
                      ("EALL, GRAV, , 0., 0., -1.", "EALL, GRAV, 0., 0., 0., -1."),
                      ("EALL, CENTRIF, 1.E6, , , , , , 1.",
                       "EALL, CENTRIF, 1.E6, 0., 0., 0., 0., 0., 1."),
                      ("EALL, CENTRIF, 1.E6, 0., 0., 0., , , 1.",
                       "EALL, CENTRIF, 1.E6, 0., 0., 0., 0., 0., 1."),
                      ("EALL, GRAV, 9.81, 0., -1.", "EALL, GRAV, 9.81, 0., -1."),   # 2-D, as given
                      ("EALL, P2, 5., ,", "EALL, P2, 5.")):          # trailing blanks: nothing after
        body, _, _ = convert_str(deck.format(src))
        assert "\n" + want + "\n" in body, (src, body)
    # given again after ccx's *DLOAD, OP=NEW removed it (_flush_dloads): the same line
    body, _, _ = convert_str(HEX + "*Surface, name=SF\nEALL, S2\n*Step\n*Static\n*Dload\n"
                                   "EALL, GRAV, 9.81, , , -1.\n*Dsload\nSF, P, 1.\n*End Step\n"
                                   "*Step\n*Static\n*Dsload, op=new\nSF, P, 2.\n*End Step\n")
    step2 = body.split("*STEP")[2]
    assert "*DLOAD, OP=NEW" in step2 and "\nEALL, GRAV, 9.81, 0., 0., -1." in step2


def test_dsload_and_commented_load_lines_keep_blank_fields():
    deck = HEX + "*Surface, name=TOP\nEALL, S2\n*Step\n*Static\n{}\n*End Step\n"
    # a traction with blank direction components: along -z (4 x area 1 over 4 nodes)
    body, _, _ = convert_str(deck.format("*Dsload\nTOP, TRVEC, 4., , , -1."))
    assert _cloads(body) == [{(n, 3): -1.0 for n in (5, 6, 7, 8)}]
    assert "** abq2ccx: TOP, TRVEC, 4., , , -1. -> nodal forces on 4 node(s)" in body
    # a commented-out line is the deck's own, to restore as it was
    for card, line in (("*Dsload", "TOP, TRVECNU, 4., , , -1."),
                       ("*Dload", "EALL, TRVEC2NU, 4., , , -1."),
                       ("*Dload, orientation=OR", "EALL, TRVEC2, 4., , , -1.")):
        body, _, _ = convert_str(deck.format(card + "\n" + line))
        assert "\n** " + line + "\n" in body, (line, body)
    # a pressure's fields are read in place: a blank surface name is not the label
    body, conv, rep = convert_str(deck.format("*Dsload\n, P, 5."))
    assert "surface '' is not defined in the deck" in rep.text() and conv.unloaded_steps == [1]


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
    plain, _, _ = convert_str(re.sub(r"(?m)^\*TRANSFORM.*\n.*\n", "", open(path, encoding="utf-8").read()))
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
    # the axes of a distribution orientation are per element: none to take (were global x)
    dist = RP2.replace("*Orientation, name=AX\n0., 0., 1., 1., 0., 0.\n",
                       "*Distribution, name=AXD\n, 0., 0., 1., 1., 0., 0.\n*Orientation, name=AX\nAXD\n")
    body, conv, rep = convert_str(dist)
    assert not _equations(body) and conv.reduced_physics == ["*CONNECTOR SECTION"]
    assert "connector (its *ORIENTATION) are missing or not rectangular" in rep.text()
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
                      ("connector_ground_hinge", 2), ("connector_transform_plate", 28),
                      ("connector_transform_join", 27)):
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


def _equation_terms(body):
    """Every *EQUATION of a converted deck as [(node, DOF, coefficient), ...]."""
    lines, out = _live(body), []
    for i, l in enumerate(lines):
        if l == "*EQUATION":
            n, toks, j = int(lines[i + 1]), [], i + 2
            while len(toks) < 3 * n:
                toks += [t.strip() for t in lines[j].split(",") if t.strip()]
                j += 1
            out.append([(int(toks[q]), int(toks[q + 1]), float(toks[q + 2])) for q in range(0, 3 * n, 3)])
    return out


def _ccx_dependents(eqs, node, axes):
    """The global DOFs ccx 2.23 eliminates for equations whose first term is a local DOF of
    ``node`` (equations.f: from the term's own direction on, 1 -> 2 -> 3 -> 1, the first
    component of size 1e-5 or more not taken yet), in order; None where it finds none."""
    taken = []
    for eq in eqs:
        n, j, _ = eq[0]
        if n != node:
            continue
        g = next((g for g in ((j - 1 + q) % 3 + 1 for q in range(3))
                  if g not in taken and abs(axes[j - 1][g - 1]) >= 1e-5), None)
        if g is None:
            return None
        taken.append(g)
    return taken


def test_rot_node_with_connector_rows_gets_the_local_axes():
    # connector constraints on a reference point's rotation go to its ROT NODE (RP2: a hinge
    # about z between two *MPC BEAM reference points); with a *TRANSFORM on the reference point
    # (local 1 = y, 2 = -x, 3 = z) the ROT NODE gets its axes and every row is written in
    # local DOFs: u_3 = u_1 is u_3x = -u_1,2, u_3y = u_1,1, u_3z = u_1,3, and the rotations
    # likewise on the ROT NODE (probed on 2.23: exact against the model without the transform)
    deck = RP2 + "*Nset, nset=R1\n1\n*Transform, nset=R1\n0., 1., 0., -1., 0., 0.\n"
    body, conv, rep = convert_str(deck)
    r1, r3 = conv._rb_rot[1], conv._rb_rot[3]
    got = _emitted_transforms(body)
    assert got[1] == ("R", [0., 1., 0., -1., 0., 0.]) and got[r1][0] == "R"
    assert _close(got[r1][1], [0., 1., 0., -1., 0., 0.])
    assert _equation_terms(body)[:5] == [
        [(3, 1, 1.), (1, 2, 1.)], [(3, 2, 1.), (1, 1, -1.)], [(3, 3, 1.), (1, 3, -1.)],
        [(r3, 1, 1.), (r1, 2, 1.)], [(r3, 2, 1.), (r1, 1, -1.)]]
    assert "written in each node's local DOFs" in rep.text() and rep.n_warnings == 0
    # a rotational BC on the reference point is moved to the ROT NODE in those axes, and the
    # hinge row it decides (theta_1x = -theta_1,2 = 0) holds theta_3x: no warning either
    body, conv, rep = convert_str(deck + "*Step\n*Static\n*Boundary\n1, 5, 5\n*End Step\n")
    r1, r3 = conv._rb_rot[1], conv._rb_rot[3]
    assert f"{r1},2,2" in _bc_lines(body) and f"{r3},1,1" in _bc_lines(body)
    assert [(r3, 2, 1.), (r1, 1, -1.)] in _equation_terms(body) and rep.n_warnings == 0


# a JOIN between cube corner 2 and a coincident free node 9, which has a cylindrical
# *TRANSFORM about z through (0.5, 0.5): local 1 radial (1, -1, 0)/sqrt(2), 2 = (1, 1, 0)/sqrt(2)
JOIN9 = (HEX + "*Node\n9, 1.,0.,0.\n*Element, type=CONN3D2, elset=J\n20, 2, 9\n"
         "*Connector Section, elset=J\nJoin,\n*Nset, nset=T9\n9\n*Transform, nset=T9, type=C\n"
         "0.5, 0.5, 0., 0.5, 0.5, 1.\n")


def test_connector_join_on_a_transformed_node_uses_its_local_dofs():
    # ccx reads *EQUATION terms on a node with a *TRANSFORM in its local axes, as Abaqus does:
    # u_9 = u_2 becomes one equation per local DOF j of node 9, u_9,j = e_j . u_2 (projected:
    # several local translations of one node in an equation fail under NLGEOM, probed), each
    # eliminating a DOF of the untransformed node 2
    body, conv, rep = convert_str(JOIN9)
    h = math.sqrt(0.5)
    eqs = sorted(_equation_terms(body))
    assert all(len([t for t in eq if t[0] == 9]) == 1 for eq in eqs) and len(eqs) == 3
    assert all(eq[0][0] == 2 for eq in eqs)
    want = {1: (h, -h, 0.), 2: (h, h, 0.), 3: (0., 0., 1.)}
    for eq in eqs:
        (j, c9), = [(d, c) for n, d, c in eq if n == 9]
        assert _close([-c / c9 for n, d, c in sorted(eq) if n == 2],
                      [x for x in want[j] if x], 1e-11), eq
    # node 2 held: the rows hold node 9's local DOFs (*BOUNDARY), as Abaqus does
    body, conv, rep = convert_str(JOIN9 + "*Boundary\n2, 1, 3\n")
    assert not _equation_terms(body) and sorted(l for l in _bc_lines(body) if l.startswith("9,")) \
        == ["9,1,1", "9,2,2", "9,3,3"]


def test_connector_link_on_a_transformed_node_uses_its_local_dofs():
    # the linearised LINK e . (u_9 - u_2) = 0, e = (0, 0.6, 0.8): node 9's terms are e . e_j
    # in its local axes (1 = y, 2 = -x, 3 = z), node 2's (no *TRANSFORM) come first
    deck = (HEX + "*Node\n9, 1.,3.,4.\n*Element, type=CONN3D2, elset=W\n20, 2, 9\n"
            "*Connector Section, elset=W\nLink,\n*Nset, nset=T9\n9\n*Transform, nset=T9\n"
            "0., 1., 0., -1., 0., 0.\n")
    body, _, rep = convert_str(deck)
    assert _equation_terms(body) == [[(2, 3, -0.8), (2, 2, -0.6), (9, 3, 0.8), (9, 1, 0.6)]]
    assert "written in each node's local DOFs" in rep.text()


def test_connector_refused_where_ccx_cannot_take_the_local_axes():
    # a node on its cylinder's axis: Abaqus cannot define the local directions there
    body, conv, rep = convert_str(JOIN9.replace("0.5, 0.5, 0., 0.5, 0.5, 1.", "1., 0., 0., 1., 0., 1."))
    assert not _equation_terms(body) and "** *CONNECTOR SECTION" in body
    assert "Connector on a node without defined local axes: a node lies on the axis" in rep.text()
    # a rotation on DOFs 4-6 of a node with a *TRANSFORM (here a beam end): ccx misreads
    # *EQUATION terms there (DOF 4 as global, DOFs 5-6 out of range; probed) — no knot either
    beams = (B2 + "*Orientation, name=AX\n0., 0., 1., 1., 0., 0.\n*Element, type=CONN3D2, "
             "elset=H\n9, 2, 3\n*Connector Section, elset=H\nHinge,\nAX,\n*Nset, nset=T3\n3\n"
             "*Transform, nset=T3\n1., 2., 0.5, -1., 0.3, 1.\n")
    body, conv, rep = convert_str(beams)
    assert not _equation_terms(body) and not conv._knots and "own DOFs 4-6" in rep.text()
    # ... unless the node's rotation is held: then only the JOIN part is left
    body, conv, rep = convert_str(beams + "*Boundary\n3, 4, 6\n")
    assert len(_equation_terms(body)) == 3 and "own DOFs 4-6" not in rep.text()


def test_connector_between_differently_transformed_nodes_under_nlgeom():
    # u_9 = u_2 with both nodes transformed differently keeps several local translations of
    # node 2 in each equation: exact in a linear step, but ccx 2.23 does not converge on such
    # an equation under NLGEOM (probed) — commented out there
    deck = JOIN9 + "*Nset, nset=T2\n2\n*Transform, nset=T2\n1., 2., 0.5, -1., 0.3, 1.\n"
    body, _, rep = convert_str(deck)
    assert len(_equation_terms(body)) == 3 and "different *TRANSFORMs" not in rep.text()
    body, _, rep = convert_str(deck + "*Step, nlgeom=YES\n*Static\n*End Step\n")
    assert not _equation_terms(body) and "different *TRANSFORMs" in rep.text()
    # one transformed node under NLGEOM: one local translation per equation, written
    body, _, rep = convert_str(JOIN9 + "*Step, nlgeom=YES\n*Static\n*End Step\n")
    assert len(_equation_terms(body)) == 3 and "** *CONNECTOR" not in body


def test_connector_dependents_on_a_transformed_node_in_an_order_ccx_takes():
    # node 2 is a rigid-body member (ccx eliminates its translations), so the JOIN eliminates
    # node 9's local DOFs; ccx turns each into a global DOF by its own rule, which fails for
    # these axes (a cylinder axis in the x-y plane) in the order 1, 2, 3 ('SPC in node 9 in
    # transformed coordinates cannot be converted in MPC: all', probed): another order is used
    deck = (HEX + "*Node\n9, 1.,0.,0.\n100, 0.5,0.5,0.5\n*Nset, nset=ALL8\n1,2,3,4,5,6,7,8\n"
            "*Rigid Body, ref node=100, tie nset=ALL8\n*Element, type=CONN3D2, elset=J\n20, 2, 9\n"
            "*Connector Section, elset=J\nJoin,\n*Nset, nset=T9\n9\n*Transform, nset=T9, type=C\n"
            "0.3, -0.2, 0.5, 0.9, 0.6, 0.5\n")
    body, conv, rep = convert_str(deck)
    eqs = _equation_terms(body)
    axes = conv._local_axes(9)
    assert [eq[0][0] for eq in eqs] == [9, 9, 9] and _ccx_dependents(eqs, 9, axes) is not None
    natural = sorted(eqs, key=lambda eq: eq[0][1])
    assert _ccx_dependents(natural, 9, axes) is None
    assert "Possible overconstraint" not in rep.text()


def test_settle_dependents_follows_ccx_on_a_transformed_node_with_a_bc():
    # node 1 is fixed, node 2 has a *TRANSFORM (about z, local 1 along the link) and a BC on its
    # local 3: the LINK's eliminated DOF goes to a local DOF of node 2 that ccx can take (its BC
    # takes global z)
    deck = ("*Node\n1, 0., 0., 0.\n2, 3., 4., 0.\n3, 7., 1., 0.\n*Element, type=SpringA, elset=S\n"
            "1, 3, 2\n*Spring, elset=S\n\n1000.\n*Element, type=CONN3D2, elset=L\n9, 1, 2\n"
            "*Connector Section, elset=L\nLink,\n*Nset, nset=T2\n2\n*Transform, nset=T2\n"
            "0.6, 0.8, 0., -0.8, 0.6, 0.\n"
            "*Boundary\n1, 1, 3\n3, 1, 3\n2, 3, 3\n*Step\n*Static\n*Cload\n2, 1, 10.\n*End Step\n")
    body, conv, rep = convert_str(deck)
    eq, = _equation_terms(body)
    assert eq[0][:2] == (2, 1) and len(eq) == 3 and "Possible overconstraint" not in rep.text()
    # turned off the link (0.5 rad about z): e has two local components on node 2, which ccx
    # would expand into repeated global DOFs, so the link goes through node 2's twin; node 1
    # is fixed, so a twin DOF is eliminated, and the twin row on node 2's local 3 (its BC
    # takes global z, ccx's only choice there) eliminates the twin's z instead
    body, conv, rep = convert_str(deck.replace(
        "0.6, 0.8, 0., -0.8, 0.6, 0.", "0.8775825618903728, 0.479425538604203, 0., "
        "-0.479425538604203, 0.8775825618903728, 0."))
    twin = conv._twins[2]
    eqs = _equation_terms(body)
    assert len(eqs) == 4 and not _ccx_expansion_repeats(body)
    link = next(eq for eq in eqs if any(n == 1 for n, _, _ in eq))
    assert link[0][0] == twin and {n for n, _, _ in link} == {1, twin}
    z = next(eq for eq in eqs if (2, 3) in [t[:2] for t in eq])
    assert z[0][:2] == (twin, 3) and "Possible overconstraint" not in rep.text()


def test_settle_dependents_writes_no_equation_with_several_local_translations():
    # an *EQUATION none of whose DOFs is free is written reduced by the equations before it
    # where that frees one — not where the reduced equation would hold two local translations
    # of a node with a *TRANSFORM (the last one here would become u_11,2, u_12,2, u_9,2 and
    # u_9,3): ccx 2.23 expands them into repeated global DOFs and mis-assembles such an
    # equation without a message, so it stays as written, with the overconstraint warning
    eqs = [[(11, 1, 2.), (11, 2, 2.), (12, 2, 0.5)], [(10, 2, 1.), (11, 2, 1.), (9, 2, -1.), (12, 1, 2.)],
           [(12, 1, -1.), (9, 3, -1.), (12, 2, 1.), (10, 1, 2.)], [(12, 1, -1.), (10, 3, 2.)],
           [(10, 1, 2.), (11, 1, 1.), (10, 2, 0.5)]]
    deck = (HEX + "*Node\n9, 2., 0., 0.\n10, 3., 0., 0.\n11, 3., 1., 0.\n12, 4., 0., 0.\n"
            "*Nset, nset=T9\n9\n*Transform, nset=T9\n1., 2., 0.5, -1., 0.3, 1.\n" +
            "".join(f"*Equation\n{len(eq)}\n" + ", ".join(f"{n}, {d}, {c}" for n, d, c in eq) + "\n"
                    for eq in eqs))
    body, _, rep = convert_str(deck)
    assert _equation_terms(body)[4] == eqs[4] and not _ccx_expansion_repeats(body)
    assert "Possible overconstraint" in rep.text()


def _transform_axes(typ, a, b, x):
    """Abaqus' local axes of a rectangular / cylindrical *TRANSFORM at point ``x`` (computed
    here, apart from abq2ccx)."""
    if typ == "R":
        e1, e3 = _unit(a), _unit(_cross(a, b))
        return e1, _cross(e3, e1), e3
    e3 = _unit([q - p for p, q in zip(a, b)])
    r = [xi - ai for xi, ai in zip(x, a)]
    e1 = _unit([ri - sum(s * t for s, t in zip(r, e3)) * e for ri, e in zip(r, e3)])
    return e1, _cross(e3, e1), e3


def _ccx_expansion_repeats(body):
    """The *EQUATIONs of a converted deck that hold a global DOF twice once ccx expands each
    term on DOFs 1-3 of a node with a *TRANSFORM into the global DOFs of its local axis (the
    components of 1e-5 or more; equations.f) — ccx 2.23 mis-assembles such an equation unless
    another MPC is substituted into it (probed: 38-144 % of max |u| off, silently)."""
    geom, tr, bad = reparse(body), _emitted_transforms(body), []
    for eq in _equation_terms(body):
        seen = []
        for n, d, _ in eq:
            if n in tr and d <= 3:
                typ, v = tr[n]
                ax = _transform_axes(typ, v[:3], v[3:], geom.nodes[n])
                seen += [(n, g + 1) for g in range(3) if abs(ax[d - 1][g]) >= 1e-5]
            else:
                seen.append((n, d))
        if len(seen) != len(set(seen)):
            bad.append(eq)
    return bad


# node 9 next to the unit cube, with a cylindrical *TRANSFORM whose axis lies along (0.6, 0.8, 0):
# ccx's own choice of the global DOFs it eliminates for local dependents fails there in the
# order 1, 2, 3 (probed: 'SPC in node ... cannot be converted in MPC: all')
CYL9 = (HEX + "*Node\n9, 2., 0.3, 0.2\n*Nset, nset=T9\n9\n*Transform, nset=T9, type=C\n"
        "0.3, -0.2, 0.5, 0.9, 0.6, 0.5\n")
CYL9_AXES = _transform_axes("C", (0.3, -0.2, 0.5), (0.9, 0.6, 0.5), (2., 0.3, 0.2))


def test_mpc_pin_on_a_transformed_node_uses_its_local_dofs():
    # Abaqus' PIN makes the GLOBAL displacements equal, also on a node with a *TRANSFORM (the
    # manual's "General multi-point constraints"; its verification xmpcpinxt.inp gives the
    # results without transforms), and ccx reads *EQUATION terms there in the local axes: u_9 =
    # u_2 is written along node 9's axes, u_9,j = e_j . u_2 — one local term per equation, which
    # ccx needs (several drift or stop under NLGEOM, and a DOF repeated in ccx's expansion is
    # mis-assembled), node 9's (the dependent node's) local DOF eliminated, the equations in an
    # order in which ccx finds a global DOF for each
    body, conv, rep = convert_str(CYL9 + "*MPC\nPIN, 9, 2\n")
    eqs = _equation_terms(body)
    assert len(eqs) == 3 and all(eq[0][0] == 9 and [n for n, _, _ in eq].count(9) == 1 for eq in eqs)
    for eq in eqs:
        j = eq[0][1]
        assert _close([c for n, d, c in sorted(eq) if n == 2],
                      [-x for x in CYL9_AXES[j - 1] if abs(x) > 1e-12], 1e-11), eq
    assert _ccx_dependents(eqs, 9, CYL9_AXES) is not None
    assert _ccx_dependents(sorted(eqs, key=lambda eq: eq[0][1]), 9, CYL9_AXES) is None
    assert not conv._twins and not _ccx_expansion_repeats(body) and rep.n_warnings == 0
    assert "Abaqus makes the global displacements equal" in rep.text()
    # node 9 the independent node: e_j . u_2 = u_9,j, a different DOF of node 2 eliminated in each
    body, conv, rep = convert_str(CYL9 + "*MPC\nPIN, 2, 9\n")
    eqs = _equation_terms(body)
    assert sorted(eq[0][:2] for eq in eqs) == [(2, 1), (2, 2), (2, 3)]
    assert all([(n, c) for n, _, c in eq if n == 9] == [(9, -1.)] for eq in eqs)
    for eq in eqs:
        j = next(d for n, d, _ in eq if n == 9)
        assert _close([c for n, d, c in sorted(eq) if n == 2],
                      [x for x in CYL9_AXES[j - 1] if abs(x) > 1e-12], 1e-11), eq
    # a TIE between solid nodes: the same, and its temperature (DOF 11, a scalar) as before
    body, _, _ = convert_str(CYL9 + "*MPC\nTIE, 9, 2\n*Step\n*Coupled Temperature-Displacement\n"
                                    "1., 1.\n*End Step\n")
    eqs = _equation_terms(body)
    assert len(eqs) == 4 and eqs[-1] == [(9, 11, 1.), (2, 11, -1.)]


def test_mpc_pin_between_differently_transformed_nodes_uses_a_twin():
    # both nodes with a *TRANSFORM, the axes different: along node 9's axes node 10 would have
    # local terms that share global DOFs, so it gets a twin — a new untransformed node at its
    # place, tied by e_j . u_twin = u_10,j (node 10's local DOF eliminated, the twin's free) —
    # and u_9 = u_twin is written along node 9's axes; the twin's equations are written once,
    # for every line that needs node 10's global displacement (here also node 12's, in another
    # *MPC card)
    deck = (CYL9 + "*Node\n10, 2., 0.3, 0.2\n11, 1., 1.5, 0.\n12, 2., 0.3, 0.2\n*Nset, nset=T10\n10\n"
            "*Transform, nset=T10\n1., 2., 0.5, -1., 0.3, 1.\n*Nset, nset=T12\n12\n"
            "*Transform, nset=T12\n0.3, -1., 0.2, 0.8, 0.5, -0.4\n*MPC\nPIN, 9, 10\nPIN, 11, 10\n"
            "*MPC\nPIN, 12, 10\n")
    body, conv, rep = convert_str(deck)
    twin = conv._twins[10]
    assert list(conv._twins) == [10] and conv.geom.nodes[twin] == conv.geom.nodes[10]
    eqs = _equation_terms(body)
    assert len(eqs) == 12 and not _ccx_expansion_repeats(body)
    assert all({n for n, _, _ in eq} == {12, twin} for eq in eqs if eq[0][0] == 12)
    ax10 = _transform_axes("R", (1., 2., 0.5), (-1., 0.3, 1.), None)
    rows10 = [eq for eq in eqs if eq[0][0] == 10]
    assert len(rows10) == 3 and all({n for n, _, _ in eq} == {10, twin} for eq in rows10)
    for eq in rows10:
        assert _close([c for n, d, c in sorted(eq) if n == twin],
                      [-x for x in ax10[eq[0][1] - 1] if abs(x) > 1e-12], 1e-11)
    assert all({n for n, _, _ in eq} == {9, twin} for eq in eqs if eq[0][0] == 9)
    # (node 11 has no *TRANSFORM: its line needs no twin, one local term of node 10 per row)
    assert all({n for n, _, _ in eq} == {11, 10} for eq in eqs if eq[0][0] == 11)
    assert "got a twin node" in rep.text() and rep.n_warnings == 0
    # the same axes on both nodes (one card): local DOF j of one equals local DOF j of the other
    same = (HEX + "*Node\n9, 2., 0.3, 0.2\n10, 2., 0.3, 0.2\n*Nset, nset=T\n9, 10\n"
            "*Transform, nset=T, type=C\n0.3, -0.2, 0.5, 0.9, 0.6, 0.5\n*MPC\nPIN, 9, 10\n")
    body, conv, _ = convert_str(same)
    assert not conv._twins and sorted(_equation_terms(body)) == \
        [[(9, j, 1.), (10, j, -1.)] for j in (1, 2, 3)]
    # axes along the global ones (local 1 = y, 2 = -x, 3 = z on node 10): its three local terms
    # in each equation share no global DOF, so no twin (probed: exact, also under NLGEOM)
    aligned = deck.replace("1., 2., 0.5, -1., 0.3, 1.", "0., 1., 0., -1., 0., 0.")
    body, conv, _ = convert_str(aligned.split("*MPC")[0] + "*MPC\nPIN, 9, 10\n")
    eqs = _equation_terms(body)
    assert not conv._twins and max(sum(1 for n, _, _ in eq if n == 10) for eq in eqs) == 3
    assert not _ccx_expansion_repeats(body)


def test_mpc_tie_rotations_on_a_transformed_shell_or_beam_node_are_refused():
    # a TIE between beam ends ties the rotations too, and ccx 2.23 misreads *EQUATION terms on
    # DOFs 4-6 of a node with a *TRANSFORM (DOF 4 global, DOFs 5-6 out of range: ccx stops or
    # ties other DOFs; probed): such a pair is commented out, and no knot beams are made for it
    tr3 = "*Nset, nset=T3\n3\n*Transform, nset=T3\n1., 2., 0.5, -1., 0.3, 1.\n"
    body, conv, rep = convert_str(B2 + tr3 + "*MPC\nTIE, 3, 2\n")
    assert not _equation_terms(body) and not conv._knots and "** TIE, 3, 2" in body
    assert "misreads *EQUATION terms on DOFs 4-6" in rep.text()
    # a node-set line: the other pair is converted (knots, all six DOFs)
    b3 = B2 + "*Node\n5,2,0,0\n6,3,0,0\n*Element,type=B31,elset=B\n3,5,6\n" \
        "*Nset, nset=A\n3, 5\n*Nset, nset=B\n2, 4\n"
    tr5 = "*Nset, nset=T5\n5\n*Transform, nset=T5\n1., 2., 0.5, -1., 0.3, 1.\n"
    body, conv, rep = convert_str(b3 + tr5 + "*MPC\nTIE, A, B\n")
    assert sorted(conv._knots) == [2, 3] and _equations(body) == \
        [f"3,{d},1.,2,{d},-1." for d in range(1, 7)]
    assert "node pair(s) (5, 4) of this line commented out" in rep.text() and "** TIE, A, B" in body
    # a heat-transfer-only deck ties the temperatures only: nothing to refuse
    body, _, rep = convert_str(B2 + tr3 + "*MPC\nTIE, 3, 2\n*Step\n*Heat Transfer\n1., 1.\n*End Step\n")
    assert _equations(body) == ["3,11,1.,2,11,-1."] and "misreads" not in rep.text()
    # a beam end tied to a free node: no rotation in common, so only the displacements are tied,
    # in node 3's local axes
    body, _, rep = convert_str(B2 + tr3 + "*Node\n9, 1., 0., 0.\n*MPC\nTIE, 3, 9\n")
    eqs = _equation_terms(body)
    assert len(eqs) == 3 and all(eq[0][0] == 3 for eq in eqs) and "misreads" not in rep.text()


def test_mpc_on_a_node_without_local_axes_is_refused():
    # a node on the axis of its cylindrical *TRANSFORM has no local directions (Abaqus rejects
    # the system there): the PIN / LINK lines on it are commented out
    deck = (HEX + "*Node\n9, 2., 0., 0.5\n*Nset, nset=T9\n9\n*Transform, nset=T9, type=C\n"
            "2., 0., 0., 2., 0., 1.\n")
    for line in ("PIN, 9, 2", "LINK, 9, 2"):
        body, conv, rep = convert_str(deck + f"*MPC\n{line}\n")
        assert not _equation_terms(body) and f"** {line}" in body and not conv._twins
        assert "on a node without defined local axes: a node lies on the axis" in rep.text()
    # ccx's distance MPC (*MPC BEAM, a LINK under NLGEOM) does not read the axes
    body, _, rep = convert_str(deck + "*MPC\nLINK, 9, 2\n*Step, nlgeom\n*Static\n*End Step\n")
    assert "*MPC\nBEAM, 9, 2" in body and "without defined local axes" not in rep.text()


def test_mpc_link_on_transformed_nodes_uses_one_local_term_per_node():
    # the linearised LINK e . (u_9 - u_2) = 0: along a local axis of node 9 it is one local
    # term; across them (here e = (1, 0.3, 0.2) / |.|, cylindrical axes) node 9 would have
    # several, which ccx expands into repeated global DOFs and mis-assembles (probed: 74-144 %
    # of max |u| off) — so the LINK uses node 9's twin
    body, conv, rep = convert_str(CYL9 + "*MPC\nLINK, 9, 2\n*Step\n*Static\n*End Step\n")
    twin = conv._twins[9]
    eqs = _equation_terms(body)
    assert len(eqs) == 4 and not _ccx_expansion_repeats(body)
    link, = [eq for eq in eqs if any(n == 2 for n, _, _ in eq)]
    e = _unit([1., 0.3, 0.2])
    assert {n for n, _, _ in link} == {2, twin} and _close(
        [c for n, d, c in sorted(link)], [-x for x in e] + list(e), 1e-11)
    assert sorted(eq[0][:2] for eq in eqs if eq is not link) == [(9, 1), (9, 2), (9, 3)]
    # a link along node 9's local 1 (radial from the z axis, e = (1, 0, 0) from node 2): one
    # local term, no twin
    radial = (HEX + "*Node\n9, 2., 0., 0.\n*Nset, nset=T9\n9\n*Transform, nset=T9, type=C\n"
              "0., 0., 0., 0., 0., 1.\n*MPC\nLINK, 9, 2\n*Step\n*Static\n*End Step\n")
    body, conv, _ = convert_str(radial)
    assert not conv._twins and _equation_terms(body) == [[(2, 1, -1.), (9, 1, 1.)]]
    # NLGEOM: ccx's *MPC BEAM keeps the distance whatever the transform (probed)
    body, conv, _ = convert_str(CYL9 + "*MPC\nLINK, 9, 2\n*Step, nlgeom\n*Static\n*End Step\n")
    assert "*MPC\nBEAM, 9, 2" in body and not conv._twins and not _equation_terms(body)
    # a heat-transfer-only deck has no displacements: the LINK is left out, as a PIN is
    body, conv, rep = convert_str(CYL9 + "*MPC\nLINK, 9, 2\n*Step\n*Heat Transfer\n1., 1.\n*End Step\n")
    assert not _equation_terms(body) and not conv._twins and "it was left out" in rep.text()


def test_connector_rotation_node_of_a_transformed_solid_node_gets_its_axes():
    # a hinge between a solid node with a moment (its rotation then lives on a new rotation
    # node) and a beam end: that node has a *TRANSFORM, so its rotation node gets the same
    # axes — the moment moved there acts in them, as in Abaqus (probed: exact)
    deck = (HEX + "*Node\n20, 1.,0.,0.\n21, 2.,0.,0.\n*Element, type=B31, elset=B\n2, 20, 21\n"
            "*Beam Section, elset=B, material=M, section=RECT\n1.,1.\n0.,0.,1.\n"
            "*Material, name=M\n*Elastic\n1000., 0.3\n*Orientation, name=AX\n0., 0., 1., 1., 0., 0.\n"
            "*Element, type=CONN3D2, elset=H\n30, 2, 20\n*Connector Section, elset=H\nHinge,\nAX,\n"
            "*Nset, nset=T2\n2\n*Transform, nset=T2\n0., 1., 0., -1., 0., 0.\n"
            "*Step\n*Static\n*Cload\n2, 4, 1.\n*End Step\n")
    body, conv, rep = convert_str(deck)
    rot = conv._rb_rot[2]
    assert rot in conv._conn_rot and rot in _emitted_transforms(body)
    assert _close(_emitted_transforms(body)[rot][1], [0., 1., 0., -1., 0., 0.])
    assert f"{rot}, 1, 1." in body and "local axes (a rectangular *TRANSFORM)" in rep.text()
    assert rep.n_warnings == 0


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


# --- deck BCs, moments and *EQUATION terms on DOFs 4-6 of nodes with a *TRANSFORM -------

# the top face of the cube coupled kinematically (all DOFs) to reference point 9
KIN9 = HEX + ("*Node\n9, 0.5, 0.5, 2.\n*Nset, nset=RP\n9\n*Nset, nset=TOPN\n5, 6, 7, 8\n"
              "*Surface, type=NODE, name=TOPS\nTOPN\n*Coupling, constraint name=C1, ref node=RP, "
              "surface=TOPS\n*Kinematic\n1, 6\n")
KIN9_STEP = ("*Step\n*Static\n*Boundary\n1, 1, 3\n2, 1, 3\n3, 1, 3\n4, 1, 3\nRP, 5, 5\n"
             "RP, 4, 4, 0.01\n*Cload\nRP, 6, 2.\n*End Step\n")
YX = "0., 2., 0., -1., 1., 0."          # rectangular: local 1 = y, 2 = -x, 3 = z


def _axes_rect(a, b):
    """Local axes e1, e2, e3 of a rectangular *TRANSFORM through a and b (Abaqus, ccx)."""
    e1, e3 = _unit(a), _unit(_cross(a, b))
    return e1, _cross(e3, e1), e3


def test_kinematic_reference_node_with_a_transform_becomes_a_rigid_body():
    # ccx's kinematic coupling carries the rotation on an internal node without the reference
    # node's *TRANSFORM: rotational BCs and moments there would act about the global axes
    # (probed: 34-253 % off).  As the *RIGID BODY it is in ccx, with a ROT NODE in the node's
    # axes, they are read locally, as in Abaqus (probed: exact, linear and NLGEOM)
    body, conv, rep = convert_str(_transformed(KIN9 + KIN9_STEP, "9", YX))
    rot = conv._rb_rot[9]
    assert "*COUPLING" not in body and "*KINEMATIC" not in body
    assert f"*RIGID BODY, NSET=ABQ2CCX_RB1, REF NODE=9, ROT NODE={rot}" in body
    assert _emitted_transforms(body)[rot] == ("R", [0., 1., 0., -1., 0., 0.])
    assert {f"{rot},2,2", f"{rot},1,1,0.01"} <= set(_bc_lines(body))
    assert _cloads(body) == [{(rot, 3): 2.0}]
    assert "written as *RIGID BODY with a ROT NODE in the node's local axes" in rep.text()
    assert rep.n_warnings == 0
    # an *EQUATION term on the reference node's DOF 6 goes to the ROT NODE's DOF 3
    deck = _transformed(KIN9 + "*Equation\n2\nRP, 6, 1., 1, 1, -1.\n" + STEP, "9", YX)
    body, conv, rep = convert_str(deck)
    assert sorted(_equation_terms(body)[0]) == [(1, 1, -1.), (conv._rb_rot[9], 3, 1.)]
    # two couplings on the reference node: both rigid bodies, one ROT NODE; with one of them
    # coupling some translations only, neither (that one cannot be a *RIGID BODY)
    two = KIN9 + ("*Nset, nset=BOTN\n1, 2, 3, 4\n*Surface, type=NODE, name=BOTS\nBOTN\n"
                  "*Coupling, constraint name=C2, ref node=RP, surface=BOTS\n*Kinematic\n1, 6\n")
    body, conv, _ = convert_str(_transformed(two + KIN9_STEP.replace("1, 1, 3\n2, 1, 3\n3, 1, 3\n"
                                                                     "4, 1, 3\n", ""), "9", YX))
    rot = conv._rb_rot[9]
    assert body.count(f"REF NODE=9, ROT NODE={rot}") == 2 and "*COUPLING" not in body
    body, conv, _ = convert_str(_transformed(two.replace("*Kinematic\n1, 6\n*Nset", "*Kinematic\n"
                                                         "1, 2\n*Nset") + KIN9_STEP, "9", YX))
    assert body.count("*COUPLING") == 2 and 9 not in conv._rb_rot and conv._rot_mode[9] == "global"
    # all three rotations held at zero (the same in any axes) uses no axes: still a coupling
    held = KIN9 + "*Step\n*Static\n*Boundary\nRP, 4, 4\nRP, 5, 5\nRP, 6, 6\n*End Step\n"
    body, conv, rep = convert_str(_transformed(held, "9", YX))
    assert "*COUPLING" in body and 9 not in conv._rb_rot and rep.n_warnings == 0
    # on its cylinder axis the reference node has no local axes: a coupling, warned
    body, conv, rep = convert_str(_transformed(KIN9 + KIN9_STEP, "9", "0.5, 0.5, 0., 0.5, 0.5, 1.", "C"))
    assert "*COUPLING" in body and "act about the global axes in ccx" in rep.text()
    _, _, rep = convert_str(_transformed(held, "9", "0.5, 0.5, 0., 0.5, 0.5, 1.", "C"))
    assert "act about the global axes" not in rep.text()


def test_connector_on_a_transformed_kinematic_reference_node_uses_its_rot_node():
    # a hinge to ground on the reference point: as a kinematic coupling ccx would carry the
    # rotation on the point's DOFs 4-6, which it misreads (the connector was commented out);
    # as the rigid body the rotation is on its ROT NODE, in the point's axes, where the rows
    # go (probed: exact against the model without the transform)
    hinge = KIN9 + ("*Orientation, name=AX\n0., 1., 0., 0., 0., 1.\n*Element, type=CONN3D2, "
                    "elset=H\n20, 9\n*Connector Section, elset=H\nHinge,\nAX,\n" + STEP)
    body, conv, rep = convert_str(_transformed(hinge, "9", YX))
    rot = conv._rb_rot[9]
    assert f"REF NODE=9, ROT NODE={rot}" in body and "** *CONNECTOR SECTION" not in body
    # the hinge axis y is the point's local 1: its local 2 and 3 are held on the ROT NODE
    assert {f"{rot},2,2", f"{rot},3,3"} <= set(_bc_lines(body)) and f"{rot},1,1" not in _bc_lines(body)
    assert "own DOFs 4-6" not in rep.text() and rep.n_warnings == 0


def test_kinematic_reference_node_that_stays_a_coupling_gets_global_components():
    # a coupling of some translations cannot be a *RIGID BODY; ccx reads the moments and
    # rotational BCs on its reference node about the global axes, so they are written in
    # global components (local 1 = y, 2 = -x: theta . e1 = 0.01, theta . e2 = 0 is
    # theta_x = 0, theta_y = 0.01; the moment about local 3 = z stays on DOF 6)
    some = KIN9.replace("*Kinematic\n1, 6\n", "*Kinematic\n1, 2\n4, 6\n")
    deck = _transformed(some + KIN9_STEP, "9", YX)
    body, conv, rep = convert_str(deck)
    assert "*COUPLING" in body and 9 not in conv._rb_rot and conv._rot_mode[9] == "global"
    assert {"9,4,4", "9,5,5,0.01"} <= set(_bc_lines(body))
    assert not any(l.startswith("RP,") and l.split(",")[1] in "456" for l in _bc_lines(body))
    assert _close(_cloads(body)[0], {(9, 4): 0., (9, 5): 0., (9, 6): 2.})
    assert "written in global components" in rep.text()
    # a single oblique local rotation held there has no such form: commented out, warned
    tilted = _transformed(some + KIN9_STEP.replace("RP, 4, 4, 0.01\n", ""), "9", "1., 1., 0., -1., 1., 1.")
    body, conv, rep = convert_str(tilted)
    assert "node 9, DOFs 4-6 of this *BOUNDARY left out" in body
    assert "the local rotation axes held are not a set of global ones" in rep.text()


def test_kinematic_coupling_in_a_dynamic_deck():
    # ccx 2.23 sets up no equations for a *DYNAMIC step of a model whose *COUPLING + *KINEMATIC
    # chain no MPCs: every free DOF stays at its initial value (validate_with_ccx.py
    # kinematic_dynamic_*).  Without NLGEOM the coupling is the linear equations Abaqus solves,
    # u = u_ref + theta x d, theta on a ROT NODE that takes the rotational BCs
    step = ("*Step{}\n*Dynamic\n0.01, 1.\n*Boundary\n1, 1, 3\n2, 1, 3\n3, 1, 3\n4, 1, 3\nRP, 2, 6\n"
            "*Boundary\nRP, 1, 1, 0.1\n*End Step\n")
    body, conv, rep = convert_str(KIN9 + step.format(""))
    rot = conv._rb_rot[9]
    assert "*COUPLING" not in body and "*KINEMATIC" not in body and "*RIGID BODY" not in body
    eqs = _equation_terms(body)
    assert len(eqs) == 12        # node 5: d = (-0.5, -0.5, -1), (theta x d)_1 = -theta_2 + theta_3 / 2
    assert eqs[0] == [(5, 1, 1.), (9, 1, -1.), (rot, 2, 1.), (rot, 3, -0.5)]
    assert {"RP,2,3", f"{rot},1,3"} <= set(_bc_lines(body))
    assert "Kinematic coupling in a deck with a *DYNAMIC step" in rep.text()
    assert rep.n_warnings == 0 and not conv.reduced_physics
    # the legacy card alike
    legacy = KIN9.split("*Surface")[0] + "*Kinematic Coupling, ref node=RP\nTOPN, 1, 3\n"
    body, conv, _ = convert_str(legacy + step.format(""))
    assert _equation_terms(body) == eqs and "*COUPLING" not in body
    # under NLGEOM (explicit steps run with it) a coupling of all translations is the *RIGID
    # BODY it is in ccx, the same RIGID MPCs
    for deck in (KIN9 + step.format(", nlgeom"), legacy + step.format(", nlgeom"),
                 KIN9 + step.format("").replace("*Dynamic\n", "*Dynamic, explicit\n")):
        body, conv, rep = convert_str(deck)
        rot = conv._rb_rot[9]
        assert f"*RIGID BODY, NSET=ABQ2CCX_RB1, REF NODE=9, ROT NODE={rot}" in body
        assert not _equation_terms(body) and "*COUPLING" not in body and not conv.reduced_physics
    # some translations: linear equations without NLGEOM; under NLGEOM nothing exact
    # (equations: 7 % off at 0.36 rad), so commented out, or --approximate's equations
    some = KIN9.replace("*Kinematic\n1, 6\n", "*Kinematic\n1, 2\n")
    body, conv, _ = convert_str(some + step.format(""))
    assert len(_equation_terms(body)) == 8 and not conv.reduced_physics
    body, conv, rep = convert_str(some + step.format(", nlgeom"))
    assert "** *COUPLING" in body and "** *KINEMATIC\n** 1, 2" in body and not _equation_terms(body)
    assert conv.reduced_physics and "--approximate to write the linear equations" in rep.text()
    assert 9 not in conv._rb_rot and "RP,2,6" in _bc_lines(body)     # no ROT NODE for it
    body, conv, rep = convert_str(some + step.format(", nlgeom"), approximate=True)
    assert len(_equation_terms(body)) == 8 and "[APPROX] Kinematic coupling" in rep.text()
    # a reference node shared with a *RIGID BODY: one ROT NODE, one rotation
    shared = KIN9 + "*Nset, nset=BOTN\n1, 2\n*Rigid Body, ref node=RP, tie nset=BOTN\n"
    body, conv, _ = convert_str(shared + step.format("").replace("1, 1, 3\n2, 1, 3\n", ""))
    rot = conv._rb_rot[9]
    assert f"*RIGID BODY, REF NODE=9, NSET=BOTN, ROT NODE={rot}" in body
    assert {t[0] for t in _equation_terms(body)[0]} == {5, 9, rot}
    # unchanged: a deck without a *DYNAMIC step, and couplings ccx solves in one (their
    # knotted shell or 2-D members chain the MPCs; probed)
    body, conv, _ = convert_str(KIN9 + KIN9_STEP)
    assert "*COUPLING" in body and "*KINEMATIC\n1, 3" in body and 9 not in conv._rb_rot
    dyn = "*Step\n*Dynamic\n0.01, 1.\n*End Step\n"
    for deck in (S4 + "*Surface, type=node, name=RS\nR\n*Coupling, constraint name=C, ref node=100, "
                      "surface=RS\n*Kinematic\n1, 3\n" + dyn,
                 Q4 + "*Node\n9, 0.5, 2.\n*Surface, type=node, name=LS\nL\n*Coupling, constraint "
                      "name=C, ref node=9, surface=LS\n*Kinematic\n" + dyn):
        body, conv, _ = convert_str(deck)
        assert "*COUPLING" in body and "*KINEMATIC" in body and not conv._kin_dyn


def test_equation_terms_on_rigid_body_reference_rotations_move_to_the_rot_node():
    # ccx carries a *RIGID BODY's rotation on DOFs 1-3 of its ROT NODE and ignores DOFs 4-6
    # of the REF NODE: an *EQUATION term there acted as a fixed zero (probed: 100 % off), or
    # stopped ccx on a transformed reference node; on the ROT NODE it is exact
    eq = "*Equation\n2\nRP, 5, 1., 1, 1, -0.5\n"
    for deck in (RB.replace("*Step", eq + "*Step", 1),
                 _transformed(RB.replace("*Step", eq + "*Step", 1), "9", YX)):
        body, conv, rep = convert_str(deck)
        rot = conv._rb_rot[9]
        assert sorted(_equation_terms(body)[0]) == [(1, 1, -0.5), (rot, 2, 1.)]
        assert "moved to DOFs 1-3 of its ROT NODE, which carries the body's rotation" in rep.text()
    # translations of the reference node stay where they are
    body, conv, _ = convert_str(RB.replace("*Step", "*Equation\n2\nRP, 2, 1., 1, 1, -0.5\n*Step", 1))
    assert sorted(_equation_terms(body)[0]) == [(1, 1, -0.5), (9, 2, 1.)]


def test_equation_on_rotations_of_a_transformed_node_is_commented_out():
    # ccx 2.23 reads an *EQUATION term on DOF 4 of a transformed node about the global axis
    # and DOFs 5-6 through an out-of-range read of the transformation matrix (terms on the
    # translations with undefined coefficients, or it stops; probed): no exact form
    beams = _transformed(B2 + "*Equation\n2\n3, 5, 1., 2, 5, -1.\n" + STEP, "3", YX)
    body, conv, rep = convert_str(beams)
    assert not _equation_terms(body) and "** *EQUATION" in body
    assert "*EQUATION with a term on DOFs 4-6 of a node with a *TRANSFORM (e.g. node 3)" in rep.text()
    assert "*EQUATION on DOFs 4-6 of a node with a *TRANSFORM" in conv.reduced_physics
    # a solid node's (no rotations in Abaqus; ccx misreads DOFs 5-6 just the same)
    solid = _transformed(HEX + "*Equation\n2\n2, 5, 1., 1, 1, -1.\n" + STEP, "2", YX)
    body, _, rep = convert_str(solid)
    assert not _equation_terms(body) and "commented out — the constraint is missing" in rep.text()
    # translations of transformed nodes, and rotations of other nodes, are untouched
    body, _, rep = convert_str(_transformed(B2 + "*Equation\n2\n3, 1, 1., 2, 5, -1.\n" + STEP, "3", YX))
    assert len(_equation_terms(body)) == 1 and "DOFs 4-6 of a node with a *TRANSFORM" not in rep.text()


# a B31 cantilever 1-2-3 (section axes oblique), clamped at 1, a *TRANSFORM on the tip 3
TIP3 = ("*Node\n1, 0., 0., 0.\n2, 1., 0., 0.\n3, 2., 0., 0.\n*Element, type=B31, elset=B\n"
        "1, 1, 2\n2, 2, 3\n*Beam Section, elset=B, material=M, section=RECT\n1., 0.5\n0., 0.6, 0.8\n"
        "*Material, name=M\n*Elastic\n1000., 0.3\n*Nset, nset=TIP\n3\n*Transform, nset=TIP\n{}\n"
        "*Boundary\n1, 1, 6\n*Step\n*Static\n{}*End Step\n")
TIP_AB = ((0., 1., 0.), (-1., 0., 0.5))       # local 1 = y, local 3 = (1, 0, 2) / sqrt(5)


def _tip(steps, data="0., 1., 0., -1., 0., 0.5"):
    return TIP3.format(data, steps)


def test_transformed_beam_node_keeps_a_single_local_rotation():
    # on a beam node that is no knot ccx makes a rotational BC / moment a mean-rotation MPC
    # about the LOCAL axis (gen3dboun / gen3dforc use the transform): exact for one local
    # rotation per node (probed, linear and NLGEOM) — kept as it is, no knot
    for steps in ("*Boundary\n3, 5, 5, 0.01\n", "*Cload\n3, 6, 2.\n",
                  "*Boundary\n3, 5, 5\n*End Step\n*Step\n*Static\n*Cload\n3, 5, 1.\n"):
        body, conv, rep = convert_str(_tip(steps))
        assert conv._rot_mode == {3: "keep"} and not conv._knots, steps
        assert rep.n_warnings == 0
    assert "3,5,5,0.01" in _bc_lines(convert_str(_tip("*Boundary\n3, 5, 5, 0.01\n"))[0])


def test_transformed_beam_node_rotations_in_global_components_on_a_knot():
    # several local rotations on one beam node: ccx's mean-rotation MPCs can clash (probed:
    # 'zero coefficient on the dependent side', up to 156 % off), so the node gets a knot
    # beam, on which ccx reads rotational BCs and moments about the global axes: they are
    # written in global components (probed: exact, linear, NLGEOM, *DYNAMIC)
    e = _axes_rect(*TIP_AB)
    body, conv, rep = convert_str(_tip("*Cload\n3, 4, 1.\n3, 6, 2.\n"))
    assert 3 in conv._knots and conv._rot_mode[3] == "global"
    want = {(3, 4 + k): e[0][k] + 2. * e[2][k] for k in range(3)}
    assert _close(_cloads(body)[0], want, 1e-10)
    assert "got a force-free knot beam" in rep.text() and rep.n_warnings == 0
    # DOF +6 or 06 is DOF 6, as ccx reads it (both moments were kept local, no knot)
    for dof in ("+6", "06"):
        body, conv, _ = convert_str(_tip(f"*Cload\n3, 4, 1.\n3, {dof}, 2.\n"))
        assert 3 in conv._knots and _close(_cloads(body)[0], want, 1e-10), dof
    # three local rotations prescribed: their global values
    body, _, _ = convert_str(_tip("*Boundary\n3, 4, 4, 0.01\n3, 5, 6, 0.02\n"))
    rows = {l.split(",")[1]: float(l.split(",")[3]) for l in _bc_lines(body) if l.startswith("3,")}
    assert _close([rows[str(4 + k)] for k in range(3)],
                  [0.01 * e[0][k] + 0.02 * e[1][k] + 0.02 * e[2][k] for k in range(3)], 1e-10)
    # all six held (ENCASTRE): the translations locally, the rotations as they are
    body, _, _ = convert_str(_tip("*Boundary\n3, ENCASTRE\n*Cload\n2, 2, 1.\n"))
    assert [l for l in _bc_lines(body) if l.startswith("3,")] == ["3,1,3", "3,4,6"]
    # two oblique local rotations held: no global form — commented out, warned
    body, conv, rep = convert_str(_tip("*Boundary\n3, 4, 5\n*Cload\n2, 2, 1.\n"))
    assert not [l for l in _bc_lines(body) if l.startswith("3,")]
    assert "node 3, DOFs 4-6 of this *BOUNDARY left out" in body
    assert "*BOUNDARY on DOFs 4-6 of a node with a *TRANSFORM (e.g. node 3) commented out" in rep.text()
    assert conv.reduced_physics == ["*BOUNDARY on DOFs 4-6 of a node with a *TRANSFORM"]
    # ... unless they span global axes: a transform about z (local 3 = z)
    body, _, rep = convert_str(_tip("*Boundary\n3, 4, 5\n3, 6, 6, 0.01\n", "0.6, 0.8, 0., -0.8, 0.6, 0."))
    assert [l for l in _bc_lines(body) if l.startswith("3,")] == ["3,4,4", "3,5,5", "3,6,6,0.01"]
    assert rep.n_warnings == 0
    # a set line with the transformed node and another: the other keeps its line
    ends = _tip("*Boundary\nENDS, 1, 6\n*Cload\nENDS, 6, 2.\n").replace("*Nset, nset=TIP",
                                                                         "*Nset, nset=ENDS\n2, 3\n*Nset, nset=TIP")
    body, _, rep = convert_str(ends)
    assert {"ENDS,1,3", "2,4,6", "3,4,6"} <= set(_bc_lines(body))
    assert _close(_cloads(body)[0], {(2, 6): 2., **{(3, 4 + k): 2. * e[2][k] for k in range(3)}}, 1e-10)


def test_transformed_moments_carry_on_over_steps_on_a_knot():
    # Abaqus keeps an earlier step's moment on a local rotation the next step leaves; ccx
    # replaces whole global DOFs, so that step gives the carried components again
    e = _axes_rect(*TIP_AB)
    body, _, rep = convert_str(_tip("*Cload\n3, 4, 1.\n3, 5, 1.\n*End Step\n*Step\n*Static\n"
                                    "*Cload\n3, 6, 2.\n"))
    s1, s2 = _cloads(body)
    assert _close(s1, {(3, 4 + k): e[0][k] + e[1][k] for k in range(3)}, 1e-10)
    assert _close(s2, {(3, 4 + k): e[0][k] + e[1][k] + 2. * e[2][k] for k in range(3)}, 1e-10)
    # with an amplitude the carried moment would restart: commented out, warned
    body, _, rep = convert_str(_tip("*Cload\n3, 4, 1.\n3, 5, 1.\n*End Step\n*Step\n*Static\n"
                                    "*Cload, amplitude=A\n3, 6, 2.\n").replace(
                                        "*Boundary\n1, 1, 6", "*Amplitude, name=A\n0., 0., 1., 1.\n*Boundary\n1, 1, 6"))
    assert "an earlier step's moment on another rotation of the node carries on" in rep.text()
    # OP=NEW removes the earlier moments in both
    body, _, _ = convert_str(_tip("*Cload\n3, 4, 1.\n*End Step\n*Step\n*Static\n*Cload, op=NEW\n3, 6, 2.\n"))
    assert _close(_cloads(body)[1], {(3, 4 + k): 2. * e[2][k] for k in range(3)}, 1e-10)


def test_transformed_rotations_on_a_frame_joint_and_in_dynamic_decks():
    # a frame joint is a ccx knot (two beam directions): read about the global axes there
    frame = TIP3.replace("2, 2, 3\n", "2, 2, 3\n3, 3, 4\n").replace(
        "3, 2., 0., 0.\n", "3, 2., 0., 0.\n4, 2., 0., 1.\n")
    deck = frame.format("0., 1., 0., -1., 0., 0.5", "*Cload\n3, 5, 1.\n")
    body, conv, rep = convert_str(deck)
    e = _axes_rect(*TIP_AB)
    assert conv._rot_mode[3] == "global" and not conv._knots
    assert _close(_cloads(body)[0], {(3, 4 + k): e[1][k] for k in range(3)}, 1e-10)
    # one local rotation held on a knot: about local 1 = y it is global DOF 5; about the
    # oblique local 2 it has no global form — commented out
    body, conv, rep = convert_str(frame.format("0., 1., 0., -1., 0., 0.5", "*Boundary\n3, 4, 4, 0.01\n"))
    assert "3,5,5,0.01" in _bc_lines(body) and rep.n_warnings == 0
    _, conv, rep = convert_str(frame.format("0., 1., 0., -1., 0., 0.5", "*Boundary\n3, 5, 5, 0.01\n"))
    assert "DOFs 4-6 of a node with a *TRANSFORM (e.g. node 3) commented out" in rep.text()
    # a *DYNAMIC step: ccx makes the knot itself and evaluates the transform elsewhere (probed:
    # 0.7-380 % off), so even one local rotation goes onto a knot beam in global components
    dyn = _tip("*Cload\n3, 6, 2.\n").replace("*Static", "*Dynamic\n0.1, 1.")
    body, conv, rep = convert_str(dyn)
    assert 3 in conv._knots and conv._rot_mode[3] == "global"
    assert _close(_cloads(body)[0], {(3, 4 + k): 2. * e[2][k] for k in range(3)}, 1e-10)
    # an explicit step stops on knot beams: refused, unless all three are held at zero
    exp = _tip("*Cload\n3, 6, 2.\n").replace("*Static", "*Dynamic, explicit\n, 1.")
    body, conv, rep = convert_str(exp)
    assert not conv._knots and "ccx's explicit solver stops on the knot beam" in rep.text()
    body, conv, rep = convert_str(exp.replace("*Cload\n3, 6, 2.\n", "*Boundary\n3, 4, 6\n"))
    assert conv._rot_mode[3] == "keep" and "3,4,6" in _bc_lines(body)


def test_transformed_shell_node_rotations():
    # a shell node that is no knot: ccx's mean-rotation MPCs in the local axes are exact for
    # its BCs (two at most) and one or two moment components (probed): kept
    shell = _transformed(S4 + "*Boundary\n1, 1, 6\n4, 1, 6\n*Step\n*Static\n*Boundary\n5, 4, 5\n"
                              "*Cload\n6, 4, 0.1\n*End Step\n", "5, 6", "1., 1., 0.3, -1., 1., 0.")
    body, conv, rep = convert_str(shell)
    assert conv._rot_mode == {5: "keep", 6: "keep"} and not conv._knots
    assert "5,4,5" in _bc_lines(body) and _cloads(body) == [{(6, 4): 0.1}]
    # in a deck with a *DYNAMIC step ccx makes the node a knot itself (probed: 28-90 % off)
    body, conv, rep = convert_str(shell.replace("*Static", "*Dynamic\n0.1, 1."))
    assert conv._rot_mode[5] == "refuse" and "a *DYNAMIC step ccx makes the shell node a knot" in rep.text()


def _knot_of(deck, n):
    """The converter's guess whether ccx makes node ``n`` of ``deck`` a knot."""
    fd, path = tempfile.mkstemp(suffix=".inp")
    os.close(fd)
    try:
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(deck)
        blocks = A.read_blocks(path, A.Report())
    finally:
        os.unlink(path)
    conv = A.Converter(A.Report(), Opt())
    conv.convert(blocks)
    return conv._ccx_knot(n, conv._knot_sections(blocks))


def test_ccx_knot_prediction():
    # gen3dnor: one expansion group per section and direction (within 20 deg) at a node;
    # more than one group makes a knot
    assert _knot_of(_tip(""), 2) is False and _knot_of(_tip(""), 3) is False
    assert _knot_of(_tip("").replace("3, 2., 0., 0.", "3, 2., 0.3, 0."), 2) is None   # 16.7 deg
    assert _knot_of(_tip("").replace("3, 2., 0., 0.", "3, 1., 1., 0."), 2) is True    # 90 deg
    two = _tip("").replace("*Material", "*Elset, elset=B2\n2\n*Beam Section, elset=B2, "
                                        "material=M, section=RECT\n1., 0.4\n0., 0.6, 0.8\n*Material")
    assert _knot_of(two, 2) is True                       # another section
    # shells: a flat plate's shared edge is one group, a fold of 90 deg two
    assert _knot_of(S4, 2) is False
    assert _knot_of(S4.replace("5,2,0,0\n6,2,1,0", "5,1,0,1\n6,1,1,1"), 2) is True
    # a SYMMETRIC layup is its plies mirrored: 2 x 0.025 is the other element's 0.1
    sym = S4.replace("*Shell Section,elset=E,material=M\n0.1\n", "*Elset,elset=E1\n1\n*Elset,elset=E2\n2\n"
                     "*Shell Section,elset=E1,material=M\n0.1\n*Shell Section,elset=E2,composite,"
                     "symmetric\n0.025,3,M,0.\n0.025,3,M,90.\n")
    assert _knot_of(sym, 2) is False
    assert _knot_of(sym.replace("0.025,3,M,90.\n", "0.025,3,M,90.\n0.01,3,M,0.\n"), 2) is True


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
                      "*Step\n*Static\n0.1, 1.\n*Boundary, type=VELOCITY\nTOP, 3, 3, -0.2\n*End Step\n"
                      "*Step, amplitude=RAMP\n*Visco\n0.1, 1.\n*Boundary, type=VELOCITY\n"
                      "TOP, 3, 3, 0.4\n*End Step\n")
    body, _, rep = convert_str(deck)
    steps = body.split("*STEP")
    assert _amplitude(body, "ABQ2CCX_VEL1")[-1] == (1.0, 0.75)          # 0.1 x 0.75 = 0.075
    # step 2 keeps the BC: in Abaqus the DOF keeps moving at the velocity it ended with,
    # where a ccx BC would freeze at its last value
    assert "*BOUNDARY, AMPLITUDE=ABQ2CCX_VEL2\nTOP, 3, 3, 1.\n*END STEP" in _without_output(steps[2])
    assert _amplitude(body, "ABQ2CCX_VEL2") == [(0.0, 0.075), (2.0, 0.275)]
    # step 3, no amplitude in a static step: the velocity is constant (Abaqus manual,
    # *BOUNDARY AMPLITUDE: "always a STEP function"), so the displacement is linear
    assert _amplitude(body, "ABQ2CCX_VEL3") == [(0.0, 0.275), (1.0, 0.075)]
    # step 4, *STEP AMPLITUDE=RAMP in a quasi-static (*VISCO) step: the velocity ramps from
    # the -0.2 step 3 ended with to 0.4
    pts = _amplitude(body, "ABQ2CCX_VEL4")
    assert pts[0] == (0.0, 0.075) and pts[-1] == (1.0, 0.175)
    assert max(abs(v - (0.075 - 0.2 * t + 0.3 * t * t)) for t, v in pts) < 1e-12
    assert "VISCO step whose default amplitude is RAMP" in rep.text()


def test_velocity_bc_after_a_free_step():
    deck = VEL_HEX + ("*Step\n*Static\n*Cload\nTOP, 3, 1.\n*End Step\n"
                      "*Step\n*Static\n*Boundary, type=VELOCITY\nTOP, 3, 3, 0.5\nTOP, 1, 2\n*End Step\n")
    body, _, rep = convert_str(deck)
    # TOP moved freely in step 1, so ccx cannot be given the total displacement: a zero
    # velocity holds the DOFs where they are (FIXED), another one is left out
    assert "** abq2ccx: not converted: TOP, 3, 3" in body
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


def test_velocity_bc_card_a_coupling_implies_is_left_out_whole():
    # the members' velocity equals the reference node's, which also holds the rotations:
    # _plan_coupled_bcs takes every line off the second card, so none of it is written (its raw
    # lines came back once, as a BC on coupled DOFs: ccx stopped, 'dependent side of a MPC and a
    # SPC', validate_with_ccx.py coupled_velocity_card)
    deck = (HEX + "*Node\n100, 0.5, 0.5, 1.\n*Nset, nset=TOP\n5, 6, 7, 8\n*Nset, nset=BOT\n1, 2, 3, 4\n"
            "*Kinematic Coupling, ref node=100\nTOP, 1, 3\n*Step\n*Dynamic\n0.01, 1.\n*Boundary\n"
            "BOT, 1, 3\n*Boundary, type=VELOCITY\n100, 1, 1, 2.\n100, 4, 6, 0.\n"
            "*Boundary, type=VELOCITY\nTOP, 1, 1, 2.\n*End Step\n")
    body, _, rep = convert_str(deck)
    # (in a *DYNAMIC step the coupling is linear equations, its rotation on the ROT NODE 101)
    assert "*BOUNDARY, AMPLITUDE=ABQ2CCX_VEL1\n100, 1, 1, 2\n*BOUNDARY\n101, 1, 3\n*NODE" in body
    assert "TOP, 1, 1" not in body and "taken off 4 DOF(s)" in rep.text()
    assert "Possible overconstraint" not in rep.text()


def test_velocity_bc_finite_rotations_about_several_axes_warned():
    # the manual's example: three turns about z in one static step, a quarter turn about x
    # in the next; integrated per component, the second is wrong under NLGEOM
    rigid = (VEL_HEX + "*Node\n100, 0.5, 0.5, 1.\n*Nset, nset=RP\n100\n"
             "*Rigid Body, ref node=100, tie nset=TOP\n")
    turn_z = ("*Step, nlgeom\n*Static\n0.1, 1.\n*Boundary, type=VELOCITY\nRP, 1, 5\n"
              "RP, 6, 6, 18.84955592\n*End Step\n")
    turn_x = ("*Step, nlgeom\n*Static\n0.1, 1.\n*Boundary, type=VELOCITY\n"
              "RP, 4, 4, 1.570796327\nRP, 5, 6\n*End Step\n")
    warning = "about more than one axis (in one step, or one after the other)"
    assert warning not in convert_str(rigid + turn_z)[2].text()
    assert warning in convert_str(rigid + turn_z + turn_x)[2].text()
    both = turn_z.replace("RP, 1, 5\n", "RP, 1, 3\nRP, 5, 5\nRP, 4, 4, 1.\n")
    assert warning in convert_str(rigid + both)[2].text()


def test_velocity_bc_examples():
    # the decks validate_with_ccx.py runs: the column's reference point follows the
    # SMOOTH STEP velocity and keeps moving in the second step; the bar's end moves at v
    body, _, _ = convert(os.path.join(EXAMPLES, "velocity_bc_column.inp"))
    assert "*BOUNDARY, AMPLITUDE=ABQ2CCX_VEL1\nRP, 3, 3, 1\n" in body
    assert _amplitude(body, "ABQ2CCX_VEL1")[-1] == (0.01, 0.0095)
    assert "*BOUNDARY, AMPLITUDE=ABQ2CCX_VEL2\nRP, 3, 3, 1.\n*END STEP" in _without_output(body)
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
    assert "** abq2ccx: OP=NEW dropped" in step2 and "*BOUNDARY\nROOT, 1, 6\n" in step2
    assert "OP=NEW\n" not in step2 and "not converted: TIP, 1, 1" in step2


def test_velocity_bc_zero_rate_from_unknown_start_holds_what_it_can():
    # TOP moved freely in step 1: a zero velocity on DOFs 1-6 (or ENCASTRE) of these solid
    # nodes holds their translations (the solid nodes have no DOFs 4-6 to hold)
    for line in ("TOP, 1, 6", "TOP, ENCASTRE"):
        body, _, _ = convert_str(VEL_HEX + "*Step\n*Static\n*Cload\nTOP, 3, 1.\n*End Step\n*Step\n"
                                           "*Static\n*Boundary, type=VELOCITY\n" + line + "\n*End Step\n")
        assert "*BOUNDARY, FIXED\nTOP, 1, 3\n*END STEP" in _without_output(body), line
    # XSYMM (DOFs 1, 5, 6) on a rigid body's reference point: x on the point, the turns on
    # its ROT NODE's translations — never a DOF range over 1-6
    body, _, _ = convert_str(VEL_HEX + "*Node\n100, 0.5, 0.5, 1.\n*Nset, nset=RP\n100\n"
                                       "*Rigid Body, ref node=100, tie nset=TOP\n*Step\n*Static\n*Cload\n"
                                       "RP, 3, 1.\n*End Step\n*Step\n*Static\n*Boundary, type=VELOCITY\n"
                                       "RP, XSYMM\n*End Step\n")
    assert "*BOUNDARY, FIXED\nRP, 1, 1\n101, 2, 3\n*END STEP" in _without_output(body)


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
    assert "1, 3, 3, 1.\n2, 3, 3, 1.\n3, 3, 3, 1\n*END STEP" in _without_output(steps[2])
    # step 3 re-specifies node 2 only: node 1 keeps moving at 1, node 2 at 3, the midside
    # node at their mean (2 -> 4)
    assert "*BOUNDARY, AMPLITUDE=ABQ2CCX_VEL5\n3, 3, 3, 1.\n*END STEP" in _without_output(steps[3])
    assert _amplitude(body, "ABQ2CCX_VEL5") == [(0.0, 2.0), (1.0, 4.0)]


def test_velocity_bc_ramp_start_does_not_depend_on_node_order():
    # node 6 shares a TOTAL TIME velocity with node 5 in step 1 and gets its own ramped one
    # in step 2; step 3 must continue it from where step 2 left it, whichever node comes first
    ends = []
    for pair in ("5, 6", "6, 5"):
        body, _, _ = convert_str(VEL_HEX + f"*Nset, nset=PAIR\n{pair}\n*Amplitude, name=A, time=TOTAL TIME"
                                           f"\n0., 0., 10., 10.\n*Step\n*Static\n0.1, 1.\n*Boundary, "
                                           f"type=VELOCITY, amplitude=A\nPAIR, 3, 3, 1.\n*End Step\n"
                                           f"*Step, amplitude=RAMP\n*Visco\n0.1, 1.\n*Boundary, type=VELOCITY"
                                           f"\n6, 3, 3, 5.\n*End Step\n*Step\n*Static\n0.1, 1.\n*End Step\n")
        ends.append([_amplitude(body, f"ABQ2CCX_VEL{i}")[-1] for i in (2, 3, 4, 5)])
    # step 2: node 6 ramps 1 -> 5 (0.5 -> 3.5), node 5 follows A (0.5 -> 2); step 3: node 5
    # follows A (-> 4.5), node 6 holds 5 (3.5 -> 8.5)
    assert ends[0] == ends[1] == [(1.0, 3.5), (1.0, 2.0), (1.0, 4.5), (1.0, 8.5)]


def test_velocity_bc_default_amplitude_follows_the_abaqus_manual():
    def end(step, proc, extra="", card="*Boundary, type=VELOCITY\nTOP, 3, 3, 1.\n"):
        body, _, rep = convert_str(VEL_HEX + extra + f"{step}\n{proc}\n0.1, 1.\n{card}*End Step\n")
        return _amplitude(body, "ABQ2CCX_VEL1" if "VELOCITY" in card else "ABQ2CCX_ACC1")[-1], rep.text()
    # a velocity without AMPLITUDE is held over a static or quasi-static step whatever
    # *STEP AMPLITUDE says; elsewhere it follows the procedure's default amplitude
    # ("Defining an analysis", Table 1) unless *STEP AMPLITUDE overrides it
    held, ramped = (1.0, 1.0), (1.0, 0.5)
    for step, proc, want in (("*Step", "*Static", held), ("*Step, amplitude=RAMP", "*Static", held),
                             ("*Step", "*Dynamic, application=QUASI-STATIC", held),
                             ("*Step", "*Dynamic", held), ("*Step, amplitude=RAMP", "*Dynamic", ramped),
                             ("*Step", "*Visco", held), ("*Step, amplitude=RAMP", "*Visco", ramped),
                             ("*Step", "*Coupled temperature-displacement", held),
                             ("*Step", "*Coupled temperature-displacement, steady state", ramped),
                             ("*Step", "*Soils, consolidation", held), ("*Step", "*Soils", ramped)):
        assert end(step, proc)[0] == want, (step, proc)
    # an acceleration follows the step's default: ramped in a quasi-static dynamic step
    acc = "*Boundary, type=ACCELERATION\nTOP, 3, 3, 1.\n"
    pt, text = end("*Step", "*Dynamic, application=QUASI-STATIC", card=acc)
    assert abs(pt[1] - 1.0 / 6.0) < 1e-9 and "should not be used" not in text   # t^3 / 6
    # Abaqus says acceleration histories should not be used in static steps
    pt, text = end("*Step", "*Static", card=acc)
    assert abs(pt[1] - 1.0 / 6.0) < 1e-9 and "should not be used in static steps" in text
    # a ramped velocity in a dynamic step starts from the DOF's velocity
    pt, text = end("*Step, amplitude=RAMP", "*Dynamic", "*Initial Conditions, type=VELOCITY\nTOP, 3, 2.\n")
    assert pt == (1.0, 1.5) and "default amplitude is RAMP" in text      # 2 t - t^2 / 2
    # Abaqus/Standard smooths a TABULAR velocity curve in a dynamic step (SMOOTH=0.25 by
    # default), Abaqus/Explicit only on request
    tab = "*Amplitude, name=T{}\n0., 0., 0.5, 1., 1., 1.\n"
    card = "*Boundary, type=VELOCITY, amplitude=T\nTOP, 3, 3, 1.\n"
    smoothed = "replaces the curve around each of its points by a quadratic"
    assert smoothed in end("*Step", "*Dynamic", tab.format(""), card)[1]
    assert smoothed not in end("*Step", "*Dynamic", tab.format(", smooth=0."), card)[1]
    assert smoothed not in end("*Step", "*Dynamic, explicit", tab.format(""), card)[1]
    assert smoothed in end("*Step", "*Dynamic, explicit", tab.format(", smooth=0.1"), card)[1]
    assert smoothed not in end("*Step", "*Static", tab.format(""), card)[1]


def test_velocity_bc_unreadable_lines_and_amplitudes():
    for deck in (VEL_HEX + "*Step\n*Static\n*Boundary, type=VELOCITY\nTOP, , 3, 1.\n*End Step\n",
                 VEL_HEX + "*Boundary, type=VELOCITY\nTOP, , 3, 0.\n*Step\n*Static\n*End Step\n",
                 VEL_HEX + "*Step\n*Static\n*Boundary, type=VELOCITY, user\nTOP, FOO\n*End Step\n"):
        body, _, _ = convert_str(deck)                       # commented, not a crash
        assert "** abq2ccx: not converted: TOP, " in body
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


RAMP = "*BOUNDARY, AMPLITUDE=RAMP12357111317"


def test_default_amplitude_ramps_displacement_bcs_where_ccx_steps_them():
    # ccx gives a BC without AMPLITUDE its procedure's default as Abaqus does (RAMP in static
    # and steady-state steps, STEP elsewhere), but Abaqus/Standard always ramps a displacement:
    # where ccx would step it, the line gets ccx's own step ramp, and *STEP, AMPLITUDE=STEP
    # (ccx's default there anyway) makes ccx define it
    for step, proc, ramped, head in (
            ("*Step", "*Static", False, "*STEP\n"),
            ("*Step, amplitude=STEP", "*Static", True, "*STEP, AMPLITUDE=STEP\n"),
            ("*Step", "*Dynamic", True, "*STEP, AMPLITUDE=STEP\n"),
            ("*Step", "*Dynamic, application=QUASI-STATIC", False, "*STEP, AMPLITUDE=RAMP\n"),
            ("*Step, amplitude=RAMP", "*Dynamic", False, "*STEP, AMPLITUDE=RAMP\n"),
            ("*Step", "*Visco, cetol=0.001", True, "*STEP, AMPLITUDE=STEP\n"),
            ("*Step", "*Coupled temperature-displacement", True, "*STEP, AMPLITUDE=STEP\n"),
            ("*Step", "*Coupled temperature-displacement, steady state", False, "*STEP\n"),
            ("*Step", "*Uncoupled temperature-displacement", True, "*STEP, AMPLITUDE=STEP\n"),
            ("*Step", "*Uncoupled temperature-displacement, steady state", False, "*STEP\n"),
            ("*Step", "*Heat transfer", False, "*STEP\n"), ("*Step", "*Frequency", False, "*STEP\n"),
            ("*Step, perturbation", "*Static", False, "*STEP\n")):
        body, _, rep = convert_str(VEL_HEX + f"{step}\n{proc}\n0.1, 1.\n*Boundary\nTOP, 3, 3, 0.1\n"
                                             f"*Cload\n5, 1, 1.\n*End Step\n")
        st = _without_output("*STEP" + _step(body, 1))
        assert st.startswith(head), (step, proc, st)
        assert (f"{RAMP}\nTOP, 3, 3, 0.1\n" in st) == ramped, (step, proc, st)
        assert "*CLOAD\n5, 1, 1.\n" in st, (step, proc)                # loads: the step's default
        assert ("'always a RAMP function'" in rep.text()) == ramped
    # an amplitude, FIXED, a velocity or the temperature: as given
    for card in ("*Boundary, amplitude=A\nTOP, 3, 3, 0.1\n", "*Boundary, fixed\nTOP, 3, 3\n",
                 "*Boundary, type=VELOCITY\nTOP, 3, 3, 0.1\n", "*Boundary\nTOP, 11, 11, 20.\n"):
        body, _, _ = convert_str(VEL_HEX + "*Amplitude, name=A\n0., 0., 1., 1.\n*Step\n"
                                           "*Coupled temperature-displacement\n0.1, 1.\n" + card +
                                 "*End Step\n")
        assert RAMP not in body and "*STEP\n" in body, card


def test_default_amplitude_ramp_only_where_it_changes_something():
    # a zero line on DOFs still at zero when the step starts is the same ramped or not: kept
    # as it is; DOFs a step moved (or left free) ramp back from where they are, line by line
    # and DOF by DOF (node 6's DOFs 1-2 held at zero in step 1, its DOF 3 moved; node 8 moved,
    # node 1 is held by the model's BC)
    body, _, _ = convert_str(VEL_HEX + "*Step\n*Dynamic\n0.1, 1.\n*Boundary\nTOP, 3, 3, 0.1\n1, 1, 3\n"
                                       "6, 1, 2\n*End Step\n*Step\n*Dynamic\n0.1, 1.\n*Boundary\n"
                                       "TOP, 3, 3\n6, 1, 3\n8, ENCASTRE\n1, ENCASTRE\n*End Step\n"
                                       "*Step\n*Dynamic\n0.1, 1.\n*Boundary\n6, 1, 2\n*End Step\n")
    s1, s2, s3 = (_without_output("*STEP" + _step(body, k)) for k in (1, 2, 3))
    assert s1.startswith("*STEP, AMPLITUDE=STEP\n") and \
        f"{RAMP}\nTOP, 3, 3, 0.1\n*BOUNDARY\n1, 1, 3\n6, 1, 2\n" in s1
    assert s2.startswith("*STEP, AMPLITUDE=STEP\n") and \
        f"{RAMP}\nTOP, 3, 3\n*BOUNDARY\n6, 1, 2\n{RAMP}\n6, 3, 3\n8, 1, 3\n*BOUNDARY\n1, 1, 3\n" in s2
    assert s3.startswith("*STEP\n") and "*BOUNDARY\n6, 1, 2\n" in s3 and RAMP not in s3
    # the card's OP=NEW goes with its first piece; a midside node of an upgraded beam ramps
    # with the end node that moves it (the card's own interpolation, kept in one piece)
    deck = ("*Node\n1, 0., 0., 0.\n2, 1., 0., 0.\n*Element, type=B31, elset=BEAM\n1, 1, 2\n"
            "*Beam Section, elset=BEAM, material=M, section=CIRC\n0.05\n0., 0., -1.\n*Material, "
            "name=M\n*Elastic\n2.1e5, 0.3\n*Density\n7.8e-9\n*Boundary\n1, 1, 6\n2, 1, 2\n2, 4, 6\n"
            "*Step\n*Dynamic\n0.1, 1.\n*Boundary, op=NEW\n1, 1, 6\n2, 1, 2\n2, 3, 3, 0.2\n2, 4, 6\n"
            "*End Step\n")
    body, conv, _ = convert_str(deck)
    assert list(conv._midside.values()) == [(1, 2, 3)]
    st = _without_output("*STEP" + _step(body, 1))
    assert f"*BOUNDARY, OP=NEW\n1, 1, 6\n2, 1, 2\n{RAMP}\n2, 3, 3, 0.2\n*BOUNDARY\n2, 4, 6\n" \
           f"3, 1, 2\n{RAMP}\n3, 3, 3, 0.1\n*BOUNDARY\n3, 4, 6\n" in st, st
    assert st.count("OP=NEW") == 1


def test_default_amplitude_explicit_holds_the_dof():
    # Abaqus/Explicit ignores the value of a displacement BC without AMPLITUDE and enforces a
    # zero velocity: a DOF still at zero gets a zero BC; one that may have moved is held
    # where the previous step left it (FIXED), per DOF of a named type too
    body, _, rep = convert_str(VEL_HEX + "*Step, amplitude=RAMP\n*Dynamic, explicit\n, 1.\n*Boundary\n"
                                         "TOP, 3, 3, 0.1\n*Cload\nTOP, 1, 1.\n*End Step\n*Step\n"
                                         "*Dynamic, explicit\n, 1.\n*Boundary\nTOP, 3, 3, 0.2\n"
                                         "TOP, PINNED\n*End Step\n")
    s1, s2 = (_without_output("*STEP" + _step(body, k)) for k in (1, 2))
    assert s1.startswith("*STEP, INC=10000000, NLGEOM\n")              # *STEP AMPLITUDE dropped
    assert "*BOUNDARY\nTOP, 3, 3\n*CLOAD" in s1
    assert "*BOUNDARY\nTOP, 3, 3\n*BOUNDARY, FIXED\nTOP, 1, 2\n*BOUNDARY\nTOP, 3, 3\n" in s2
    text = rep.text()
    assert "ignores the value ('does not admit jumps in displacement')" in text
    assert "held where the previous step left them (*BOUNDARY, FIXED)" in text
    assert "dropped on an explicit step" in text
    # the load audit follows: a nonzero value without AMPLITUDE moves nothing in Abaqus/Explicit
    _, conv, _ = convert_str(VEL_HEX + "*Step\n*Dynamic, explicit\n, 1.\n*Boundary\nTOP, 3, 3, 0.1\n"
                                       "*End Step\n")
    assert conv.source_unloaded and not conv.unloaded_steps
    _, conv, _ = convert_str(VEL_HEX + "*Amplitude, name=A\n0., 0., 1., 1.\n*Step\n*Dynamic, explicit\n"
                                       ", 1.\n*Boundary, amplitude=A\nTOP, 3, 3, 0.1\n*End Step\n")
    assert not conv.source_unloaded and not conv.unloaded_steps


def test_default_amplitude_explicit_hold_limits():
    # FIXED holds a rigid body's rotations on its ROT NODE's translations; it takes no
    # shell/beam rotation and misreads a node with a *TRANSFORM in ccx 2.23: kept, warned
    later = "*Step\n*Dynamic, explicit\n, 1.\n*Cload\n{0}, 3, 1.\n*End Step\n*Step\n*Dynamic, explicit\n" \
            ", 1.\n*Boundary\n{1}\n*End Step\n"
    body, conv, rep = convert_str(VEL_HEX + "*Node\n100, 0.5, 0.5, 1.\n*Nset, nset=RP\n100\n"
                                            "*Rigid Body, ref node=100, tie nset=TOP\n" +
                                  later.format("RP", "RP, 4, 6"))
    assert f"*BOUNDARY, FIXED\n{conv._rb_rot[100]}, 1, 3\n" in body and "Kept as given" not in rep.text()
    body, _, rep = convert_str(VEL_HEX + "*Transform, nset=TOP\n0., 1., 0., -1., 0., 0.\n" +
                               later.format("TOP", "TOP, 1, 1, 0.5"))
    assert "*BOUNDARY\nTOP, 1, 1, 0.5\n" in _without_output(_step(body, 2)) and \
        "Kept as given" in rep.text()
    shell = ("*Node\n1, 0., 0., 0.\n2, 1., 0., 0.\n3, 1., 1., 0.\n4, 0., 1., 0.\n*Element, type=S4, "
             "elset=P\n1, 1, 2, 3, 4\n*Shell Section, elset=P, material=M\n0.1\n*Material, name=M\n"
             "*Elastic\n1000., 0.3\n*Density\n1.\n*Boundary\n1, 1, 6\n2, 1, 6\n")
    body, _, rep = convert_str(shell + later.format("3", "3, 4, 4\n3, 1, 3"))
    assert "*BOUNDARY\n3, 4, 4\n*BOUNDARY, FIXED\n3, 1, 3\n" in _without_output(_step(body, 2)) and \
        "Kept as given" in rep.text()
    # a velocity BC's zero rate from an unknown start, on a transformed node: not FIXED either
    body, _, _ = convert_str(VEL_HEX + "*Transform, nset=TOP\n0., 1., 0., -1., 0., 0.\n*Step\n*Static\n"
                                       "*Cload\nTOP, 3, 1.\n*End Step\n*Step\n*Static\n*Boundary, "
                                       "type=VELOCITY\nTOP, 1, 3\n*End Step\n")
    assert "\n*BOUNDARY, FIXED\n" not in body and "a node with a *TRANSFORM: ccx 2.23 reads the global" in body


def test_default_amplitude_on_transformed_nodes():
    # ccx allows one amplitude for all DOFs of a node with a *TRANSFORM, and its step ramp
    # starts a BC new on a DOF there from an auxiliary node's value (probed: from 0), so all
    # the node's lines of a step ramp - its zero ones too, warned - where every DOF had a BC
    # before the step (or in the first step), and none where one had not (warned)
    tr = "*Transform, nset=TOP\n0., 1., 0., -1., 0., 0.\n"
    body, _, rep = convert_str(VEL_HEX + tr + "*Step\n*Dynamic\n0.1, 1.\n*Boundary\nTOP, 1, 1, 0.01\n"
                                         "TOP, 2, 2\n*End Step\n*Step\n*Dynamic\n0.1, 1.\n*Boundary\n"
                                         "TOP, 3, 3, -0.005\nTOP, 1, 1, 0.02\n*End Step\n*Step\n"
                                         "*Dynamic\n0.1, 1.\n*Boundary\nTOP, 1, 1, 0.03\n*End Step\n")
    s1, s2, s3 = (_without_output("*STEP" + _step(body, k)) for k in (1, 2, 3))
    assert f"{RAMP}\nTOP, 1, 1, 0.01\nTOP, 2, 2\n" in s1
    assert s2.startswith("*STEP\n") and "*BOUNDARY\nTOP, 3, 3, -0.005\nTOP, 1, 1, 0.02\n" in s2
    assert f"{RAMP}\nTOP, 1, 1, 0.03\n" in s3            # DOF 1 had a BC: ccx ramps from it
    text = rep.text()
    assert "so its zero displacement BCs in that step were ramped too" in text
    assert "ccx's step ramp would start it there from the value of the auxiliary node" in text
    body, _, rep = convert_str(VEL_HEX + tr + "*Step\n*Dynamic\n0.1, 1.\n*Boundary\nTOP, 1, 1, 0.01\n"
                                         "*End Step\n")
    assert f"{RAMP}\nTOP, 1, 1, 0.01\n" in body and "were ramped too" not in rep.text()
    # the BCs that hold a connector, repeated after OP=NEW, get their own card after a FIXED one
    deck = (HEX + "*Node\n9, 2.,0.,0.\n*Element, type=CONN3D2, elset=G\n5, 9,\n*Connector Section, "
            "elset=G\nJoin,\n*Boundary\n1, 1, 3\n*Step\n*Dynamic, explicit\n, 1.\n*Cload\n7, 3, 1.\n"
            "*End Step\n*Step\n*Dynamic, explicit\n, 1.\n*Boundary, op=NEW\n7, 1, 3\n1, 1, 3\n*End Step\n")
    body, _, _ = convert_str(deck)
    assert "*BOUNDARY, OP=NEW, FIXED\n7, 1, 3\n*BOUNDARY\n9, 1, 1\n9, 2, 2\n9, 3, 3\n*BOUNDARY\n" \
           "1, 1, 3\n" in _step(body, 2)


def test_default_amplitude_example():
    # the deck validate_with_ccx.py runs: the driven top ramps in both steps, the load steps
    body, _, _ = convert(os.path.join(EXAMPLES, "default_amplitude_bars.inp"))
    s1, s2 = (_without_output("*STEP" + _step(body, k)) for k in (1, 2))
    assert s1.startswith("*STEP, INC=1000, AMPLITUDE=STEP\n") and \
        f"{RAMP}\nDRIVEN_TOP, 3, 3, 0.01\n*CLOAD\nLOADED_TOP, 3, 0.25\n" in s1
    assert s2.startswith("*STEP, INC=1000, AMPLITUDE=STEP\n") and f"{RAMP}\nDRIVEN_TOP, 3, 3, 0.03\n" in s2
    assert not dangling_refs(reparse(body))


def test_default_amplitude_explicit_hold_feeds_the_velocity_plan():
    # a velocity BC after an explicit step that held its DOF with a displacement BC without
    # AMPLITUDE (zero velocity) starts from where the DOF stood, not from the ignored value
    body, _, _ = convert_str(VEL_HEX + "*Step\n*Dynamic, explicit\n, 1.\n*Boundary, type=VELOCITY\n"
                                       "TOP, 3, 3, 1.\n*End Step\n*Step\n*Dynamic, explicit\n, 1.\n"
                                       "*Boundary\nTOP, 3, 3, 5.\n*End Step\n*Step\n*Dynamic, explicit\n"
                                       ", 1.\n*Boundary, type=VELOCITY\nTOP, 3, 3, 1.\n*End Step\n")
    assert "*BOUNDARY, FIXED\nTOP, 3, 3\n" in _step(body, 2)
    assert "*BOUNDARY, AMPLITUDE=ABQ2CCX_VEL2\nTOP, 3, 3, 1.\n" in _step(body, 3)
    assert _amplitude(body, "ABQ2CCX_VEL2") == [(0.0, 1.0), (1.0, 2.0)]

# --- solve fidelity: exact conversions and the reduced-physics record -------------------
PLANE2 = ("*Node\n1,0.,0.\n2,2.,0.\n3,4.,0.\n4,0.,1.\n5,2.,1.\n6,4.,1.\n"
          "*Element, type=CPS4I, elset=B\n1,1,2,5,4\n2,2,3,6,5\n*Nset, nset=ROOT\n1,4\n"
          "*Material, name=STEEL\n*Elastic\n1000., 0.3\n*Density\n7.8e-9\n"
          "*Solid Section, elset=B, material=STEEL\n0.5,\n*Boundary\nROOT, ENCASTRE\n")


def test_cps4i_written_as_c3d8i_slab():
    # ccx has no incompatible-mode plane element; a CPS4I becomes a C3D8I slab one section
    # thickness deep on its 2-D nodes, with plane stress through an ORTHO material
    deck = PLANE2 + "*Step\n*Static\n*Dload\n2, P2, 1.\n*Cload\n6, 2, -1.\n*End Step\n"
    body, conv, rep = convert_str(deck)
    assert "*ELEMENT, TYPE=C3D8I" in body and "CPS4" not in body.split("*NSET")[0]
    assert re.search(r"^1, 1, 2, 5, 4, 7, 8, 9, 10$", body, re.M), body[:600]
    assert "\n7, 0, 0, 0.5\n" in body                    # top node one thickness above node 1
    assert "*EQUATION\n2\n7, 1, 1., 1, 1, -1." in body and "ABQ2CCX_SLAB, 3, 3" in body
    assert "*ELASTIC, TYPE=ORTHO" in body and "STEEL_PLANE_STRESS" in body
    ortho = body.split("*ELASTIC, TYPE=ORTHO\n")[1].splitlines()
    vals = [float(x) for x in ortho[0].split(",")] + [float(ortho[1])]
    d11, g = 1000. / (1 - 0.09), 1000. / 2.6
    assert all(abs(a - b) <= 1e-6 * d11 for a, b in
               zip(vals, (d11, 0.3 * d11, d11, 0., 0., 1000., g, g, g))), vals
    assert "*DENSITY\n7.8e-9" in body or "*DENSITY\n7.8E-09" in body.upper()
    assert "2, P4, 1." in body                           # edge 2 is the slab's side face 4
    assert conv.reduced_physics == [] and rep.n_warnings == 0, rep.text()
    # a plane-strain CPE4I keeps its material; DOF 3 is held again after OP=NEW
    body, conv, _ = convert_str(deck.replace("CPS4I", "CPE4I").replace(
        "*Dload", "*Boundary, op=NEW\nROOT, 1, 2\n*Dload"))
    assert "material=STEEL" in body.replace("MATERIAL", "material") and "ORTHO" not in body
    assert body.count("ABQ2CCX_SLAB, 3, 3") == 2 and conv.reduced_physics == []
    # *ELASTIC with E alone has nu = 0 (a blank field, as Abaqus reads it)
    body, conv, _ = convert_str(deck.replace("1000., 0.3\n", "1000.\n"))
    ortho = body.split("*ELASTIC, TYPE=ORTHO\n")[1].splitlines()
    assert [float(x) for x in ortho[0].split(",")] == [1000., 0., 1000., 0., 0., 1000., 500., 500.]
    assert conv.reduced_physics == []
    # a Poisson's ratio the plane-stress stiffness cannot take keeps the plain element
    body, conv, _ = convert_str(deck.replace("1000., 0.3\n", "1000., 1.\n"))
    assert "C3D8I" not in body and conv.reduced_physics


def test_cps4i_outside_the_exact_slab_form_is_reduced_physics():
    # NLGEOM (and plasticity, contact, couplings ...) keep the old CPS4 stand-in, which locks in
    # bending: reduced physics
    deck = PLANE2 + "*Step, nlgeom=YES\n*Static\n*Cload\n6, 2, -1.\n*End Step\n"
    body, conv, rep = convert_str(deck)
    assert "TYPE=CPS4\n" in body and "C3D8I" not in body
    assert conv.reduced_physics == ["element CPS4I -> CPS4 (incompatible modes dropped)"]
    assert "a step runs NLGEOM" in rep.text() and "Reduced physics" in rep.text()
    deck = PLANE2.replace("*Density\n7.8e-9\n", "*Plastic\n10., 0.\n") + \
        "*Step\n*Static\n*Cload\n6, 2, -1.\n*End Step\n"
    assert "material STEEL has *PLASTIC" in convert_str(deck)[2].text()
    # CPE4I: Abaqus adds a fifth, volumetric mode, which matters off a parallelogram
    deck = PLANE2.replace("CPS4I", "CPE4I").replace("6,4.,1.", "6,4.5,1.") + \
        "*Step\n*Static\n*Cload\n6, 2, -1.\n*End Step\n"
    _, conv, rep = convert_str(deck)
    assert conv.reduced_physics and "not a parallelogram" in rep.text()


def test_reduced_physics_record():
    # a dropped constitutive card, a replaced element formulation and a dropped interaction
    # are reduced physics; exact substitutions, output requests and numerical controls are not
    plain = HEX + "*Material, name=M\n*Elastic\n1000., 0.3\n*Solid Section, elset=EALL, material=M\n"
    step = "*Boundary\n1, 1, 3\n*Step\n*Static\n*Cload\n7, 3, 1.\n*End Step\n"
    _, conv, _ = convert_str(plain + step)
    assert conv.reduced_physics == []
    _, conv, rep = convert_str(plain.replace("*Solid", "*Plastic, hardening=USER\n3\n*Solid") + step)
    assert conv.reduced_physics == ["*PLASTIC"] and "Reduced physics" in rep.text()
    _, conv, _ = convert_str(plain.replace("*Solid", "*Concrete Damaged Plasticity\n30., 0.1\n*Solid")
                             + step)
    assert conv.reduced_physics == ["*CONCRETE DAMAGED PLASTICITY"]
    _, conv, _ = convert_str(plain.replace("C3D8", "C3D8H") + step)
    assert conv.reduced_physics == ["element C3D8H -> C3D8"]
    _, conv, _ = convert_str(plain + "*Energy Output\n*Bulk Viscosity\n0.06, 1.2\n"
                                     "*File Format, ascii\n" + step)
    assert conv.reduced_physics == [], conv.reduced_physics
    tri = ("*Node\n1,0.,0.\n2,1.,0.\n3,0.,1.\n*Element, type={}, elset=E\n1,1,2,3\n"
           "*Material, name=M\n*Elastic\n1000., 0.3\n*{} Section, elset=E, material=M\n0.1\n"
           "*Boundary\n1, 1, 3\n2, 2, 3\n*Step\n*Static\n*Cload\n3, 2, 1.\n*End Step\n")
    for typ, sec, reduced in (("CPE3H", "Solid", False), ("S3R", "Shell", False),
                              ("STRI3", "Shell", True), ("CPS6M", "Solid", True)):
        deck = tri.format(typ, sec)
        if typ == "CPS6M":
            deck = deck.replace("1,1,2,3\n", "1,1,2,3,4,5,6\n").replace(
                "3,0.,1.\n", "3,0.,1.\n4,0.5,0.\n5,0.5,0.5\n6,0.,0.5\n")
        _, conv, rep = convert_str(deck)
        assert bool(conv.reduced_physics) == reduced, (typ, conv.reduced_physics, rep.text())
    # a *SECTION CONTROLS whose options do not apply (SECOND ORDER ACCURACY in Abaqus/Standard,
    # hourglass factors 1 on a fully integrated element) changes nothing; ENHANCED hourglass
    # control on a C3D8R does
    sc = plain.replace("material=M\n", "material=M, controls=EC\n") + \
        "*Section Controls, name=EC, second order accuracy=YES\n1., 1., 1.\n" + step
    _, conv, rep = convert_str(sc)
    assert conv.reduced_physics == [] and "changes nothing" in rep.text()
    _, conv, _ = convert_str(sc.replace("C3D8,", "C3D8R,").replace("second order accuracy=YES",
                                                                    "hourglass=ENHANCED"))
    assert conv.reduced_physics == ["*SECTION CONTROLS (HOURGLASS=ENHANCED on C3D8R)"]



def test_commented_card_of_an_unused_material_is_no_reduced_physics():
    # a material no section uses changes nothing: its commented cards are notes, not reduced
    # physics; the same cards in the material a section uses are
    used = HEX + ("*Material, name=M\n*Elastic\n1000., 0.3\n*Damage Evolution, type=ENERGY\n1.\n"
                  "*Solid Section, elset=EALL, material=M\n")
    unused = HEX + ("*Material, name=M\n*Elastic\n1000., 0.3\n*Solid Section, elset=EALL, material=M\n"
                    "*Material, name=COH\n*Elastic\n1000., 0.3\n*Damage Evolution, type=ENERGY\n1.\n")
    step = "*Boundary\n1, 1, 3\n*Step\n*Static\n*Cload\n7, 3, 1.\n*End Step\n"
    _, conv, _ = convert_str(used + step)
    assert conv.reduced_physics == ["*DAMAGE EVOLUTION"]
    _, conv, rep = convert_str(unused + step)
    assert conv.reduced_physics == [] and "No section uses material COH" in rep.text()

def test_node_system_cylindrical_and_spherical():
    # Abaqus *NODE, SYSTEM=C gives R, theta (degrees), Z; SYSTEM=S gives R, theta, phi with phi
    # up from the X-Y plane (Abaqus 'Node definition')
    body, conv, _ = convert_str("*Node, system=C\n1, 10., 20., 5.\n*Node, system=S\n2, 2., 90., 30.\n")
    x, y, z = conv.geom.nodes[1]
    assert abs(x - 10 * math.cos(math.radians(20))) < 1e-12 and abs(y - 10 * math.sin(math.radians(20))) < 1e-12
    assert z == 5.0
    x, y, z = conv.geom.nodes[2]
    assert abs(x) < 1e-12 and abs(y - math.sqrt(3)) < 1e-12 and abs(z - 1.0) < 1e-12
    assert conv.reduced_physics == []
    # a normal on such a line is given in the same form (*NODE: its second entry is an angle,
    # in a spherical system its third too): 1, 20, 0 is the radial direction at theta = 20
    body, conv, _ = convert_str("*Node, system=C\n1, 10., 20., 5., 1., 20., 0.\n"
                                "*Node, system=S\n2, 2., 90., 30., 1., 90., 30.\n")
    nx, ny, nz = conv._node_normals[1]
    assert abs(nx - math.cos(math.radians(20))) < 1e-12 and abs(ny - math.sin(math.radians(20))) < 1e-12
    assert abs(nz) < 1e-12
    nx, ny, nz = conv._node_normals[2]
    assert abs(nx) < 1e-12 and abs(ny - math.sqrt(3) / 2) < 1e-12 and abs(nz - 0.5) < 1e-12


def test_nmap_maps_nodes_and_their_normals():
    # NAFEMS LE2 writes its cylindrical shell in (r, theta, z) and maps it with *NMAP,
    # TYPE=CYLINDRICAL; its *NODE normals (1, 0, 0) are radial in those local axes
    deck = ("*Node\n1, 1., 10., 0.5, 1., 0., 0.\n2, 2., 0., 0.\n*Nset, nset=ALL\n1, 2\n"
            "*Nmap, nset=ALL, type=CYLINDRICAL\n0.,0.,0.,0.,0.,1.\n1.,0.,0.\n")
    _, conv, _ = convert_str(deck)
    c, s = math.cos(math.radians(10.)), math.sin(math.radians(10.))
    assert max(abs(u - v) for u, v in zip(conv.geom.nodes[1], (c, s, 0.5))) < 1e-12
    assert max(abs(u - v) for u, v in zip(conv._node_normals[1], (c, s, 0.))) < 1e-12
    assert conv.geom.nodes[2] == (2.0, 0.0, 0.0) and conv.reduced_physics == []
    # RECTANGULAR: x along a-b, y toward c, local coordinates scaled by the third line first
    _, conv, _ = convert_str("*Node\n1, 1., 2., 3.\n*Nset, nset=N\n1\n*Nmap, nset=N, type=RECTANGULAR\n"
                             "1.,1.,1.,1.,2.,1.\n0.,1.,1.\n2.,0.,1.\n")
    assert max(abs(u - v) for u, v in zip(conv.geom.nodes[1], (-1., 3., 4.))) < 1e-12
    # ROTATION by 90 degrees about z through c = (1, 0, 0); SPHERICAL (R, theta, phi)
    _, conv, _ = convert_str("*Node\n1, 2., 0., 0.\n*Nset, nset=N\n1\n*Nmap, nset=N, type=ROTATION\n"
                             "0.,0.,0.,0.,0.,1.\n1.,0.,0.\n90.\n")
    assert max(abs(u - v) for u, v in zip(conv.geom.nodes[1], (1., 1., 0.))) < 1e-12
    _, conv, _ = convert_str("*Node\n1, 2., 90., 30.\n*Nset, nset=N\n1\n*Nmap, nset=N, type=SPHERICAL\n"
                             "0.,0.,0.,0.,0.,1.\n1.,0.,0.\n")
    assert max(abs(u - v) for u, v in zip(conv.geom.nodes[1], (0., math.sqrt(3.), 1.))) < 1e-12
    _, conv, rep = convert_str(deck.replace("CYLINDRICAL", "TOROIDAL"))
    assert conv.reduced_physics == ["*NMAP, TYPE=TOROIDAL coordinate mapping skipped"]


def test_node_normals_become_normal_cards():
    # Abaqus uses the *NODE normal for every shell element at the node; ccx would average the
    # element normals, so they are written as *NORMAL lines (a deck's own *NORMAL wins)
    deck = ("*Node\n1,0.,0.,0.,0.,0.6,0.8\n2,1.,0.,0.\n3,1.,1.,0.\n4,0.,1.,0.\n"
            "*Element, type=S4, elset=E\n7,1,2,3,4\n")
    body, conv, rep = convert_str(deck)
    assert "*NORMAL\n7, 1, 0, 0.6, 0.8" in body.replace("0.,", "0,").replace("0.0,", "0,") or \
        re.search(r"\*NORMAL\n7, 1, [-0. ]*, 0\.6, 0\.8", body), body
    assert conv.reduced_physics == []
    body, _, _ = convert_str(deck + "*Normal\n7, 1, 0., 0., 1.\n")
    assert body.count("*NORMAL") == 1


def test_buckle_load_case_two_cards():
    # Abaqus/CAE writes each buckling BC for LOAD CASE=1 and 2; ccx has one set of BCs: the
    # repeats are left out (exact), differing buckling-mode BCs are reduced physics
    base = HEX + "*Material, name=M\n*Elastic\n1000., 0.3\n*Solid Section, elset=EALL, material=M\n"
    step = ("*Step, perturbation\n*Buckle\n2\n*Boundary, op=NEW, load case=1\n1, 1, 3\n"
            "*Boundary, op=NEW, load case=2\n1, 1, 3\n*Cload\n7, 3, -1.\n*End Step\n")
    body, conv, rep = convert_str(base + step)
    cards = [ln for ln in body.splitlines() if ln.startswith("*BOUNDARY")]
    assert cards == ["*BOUNDARY, OP=NEW"] and conv.reduced_physics == [], body
    body, conv, rep = convert_str(base + step.replace("load case=2\n1, 1, 3", "load case=2\n1, 1, 2"))
    assert conv.reduced_physics == ["*BUCKLE buckling-mode BCs (*BOUNDARY, LOAD CASE=2)"]


def _normal_rows(body):
    return [[float(x) for x in ln.split(",")] for ln in _card(body, "*NORMAL")]


def test_node_normals_blank_fields_trusses_knots_and_undefined_nodes():
    # *NODE fields are positional: a blank normal component is 0, as Abaqus reads it
    shell = ("*Node\n1,0.,0.,0.,0., ,1.\n2,1.,0.,0.\n3,1.,1.,0.\n4,0.,1.,0.\n"
             "*Element, type=S4, elset=E\n7,1,2,3,4\n")
    body, conv, _ = convert_str(shell)
    assert _normal_rows(body) == [[7., 1., 0., 0., 1.]] and conv.reduced_physics == []
    # a truss has no cross-section orientation, a beam takes its n2 from the normal
    body, conv, _ = convert_str(shell + "*Element, type=T3D2, elset=T\n8,1,2\n")
    assert conv.reduced_physics == [], conv.reduced_physics
    body, conv, _ = convert_str(shell + "*Element, type=B31, elset=B\n8,1,2\n")
    assert conv.reduced_physics == ["*NODE normals of beam nodes (cross-section orientation)"]
    # the converter's own knot beams (a rigid coupling on shell nodes) are no such beams
    body, conv, _ = convert_str(shell + "*Node\n100, 0.5, 0.5, 1.\n*Nset, nset=TIPN\n1, 2\n"
                                "*Kinematic Coupling, ref node=100\nTIPN, 1, 6\n")
    assert "ABQ2CCX_KNOT" in body and not any("normals" in r for r in conv.reduced_physics)
    # an element on an undefined node does not stop the conversion
    body, conv, _ = convert_str(shell.replace("7,1,2,3,4", "7,1,2,3,99"))
    assert "*ELEMENT, TYPE=S4" in body


def test_node_system_empty_record_and_cps4i_slab_guards():
    body, conv, _ = convert_str("*Node, system=C\n1, 10., 0., 0.\n,\n2, 10., 90., 0.\n")
    assert abs(conv.geom.nodes[2][1] - 10.) < 1e-12 and abs(conv.geom.nodes[2][0]) < 1e-12
    # an element on an undefined node, or a step the slab is not probed for, keeps the
    # plain element (reduced physics) instead of stopping the conversion
    load = "*Step\n*Static\n*Cload\n6, 2, -1.\n*End Step\n"
    body, conv, _ = convert_str(PLANE2.replace("2,2,3,6,5", "2,2,3,99,5") + load)
    assert "C3D8I" not in body and conv.reduced_physics
    body, conv, _ = convert_str(PLANE2 + "*Step\n*Frequency\n3\n*End Step\n")
    assert "C3D8I" not in body and conv.reduced_physics == ["element CPS4I -> CPS4 (incompatible modes dropped)"]
    # a planar beam beside the slabs is still held in its plane
    beam = ("*Node\n50, 10., 0.\n51, 11., 0.\n*Element, type=B21, elset=BM\n90, 50, 51\n"
            "*Beam Section, elset=BM, material=STEEL, section=RECT\n0.1, 0.1\n")
    body, conv, rep = convert_str(PLANE2 + beam + load.replace("6, 2", "51, 2"))
    assert "C3D8I" in body and "ABQ2CCX_PLANAR" in body and conv.reduced_physics == [], rep.text()


def test_steady_state_dynamics_real_and_imaginary_parts():
    # Abaqus gives the out-of-phase part with IMAGINARY and ignores LOAD CASE outside
    # *BUCKLE; ccx reads LOAD CASE=2 as the imaginary part
    base = (HEX + "*Material, name=M\n*Elastic\n1000., 0.3\n*Density\n1e-9\n"
            "*Solid Section, elset=EALL, material=M\n*Boundary\n1, 1, 3\n2, 1, 3\n3, 1, 3\n4, 1, 3\n")
    ssd = "*Steady State Dynamics\n10., 100., 5\n"
    body, conv, rep = convert_str(
        base + "*Step\n*Frequency\n4\n*End Step\n*Step\n" + ssd + "*Cload, imaginary\n7, 3, 1.\n"
        "*Cload, real\n8, 3, 1.\n*Boundary, imaginary\n5, 1, 1, 0.001\n"
        "*Boundary, load case=2\n6, 1, 1, 0.001\n*End Step\n")
    live = _live(body)
    assert "*CLOAD, LOAD CASE=2" in live and "*BOUNDARY, LOAD CASE=2" in live, body
    assert sum("LOAD CASE" in ln for ln in live) == 2 and conv.reduced_physics == []
    # a PERTURBATION steady-state dynamics step is no static perturbation step
    body, conv, rep = convert_str(
        base + "*Step, perturbation\n*Frequency\n4\n*End Step\n" +
        2 * ("*Step, perturbation\n" + ssd + "*Cload\n7, 3, 1.\n*End Step\n"))
    assert conv.reduced_physics == [] and "PERTURBATION on a static step" not in rep.text()


def test_field_dependencies_exact_only_where_abaqus_has_that_state():
    # field 0 a state of the table: its rows, exact (other temperatures elsewhere do not matter)
    rows = "1000.,0.3,0.,0.\n2000.,0.3,100.,0.\n500.,0.3,0.,1.\n700.,0.3,50.,1.\n900.,0.3,100.,1.\n"
    body, conv, _ = convert_str("*Material,name=M\n*Elastic,dependencies=1\n" + rows)
    assert _card(body, "*ELASTIC") == ["1000., 0.3, 0.", "2000., 0.3, 100."] and conv.reduced_physics == []
    # 0 between two states given at different temperatures: not reproduced exactly
    body, conv, _ = convert_str("*Material,name=M\n*Elastic,dependencies=1\n" +
                                rows.replace(",0.\n", ",-1.\n"))
    assert conv.reduced_physics == ["*ELASTIC field-variable dependence"]
    # a single state at another field value: Abaqus holds it beyond the table, exact
    body, conv, _ = convert_str("*Material,name=M\n*Density, dependencies=1\n7.8e-9, , 1.\n")
    assert _card(body, "*DENSITY") == ["7.8e-9"] and conv.reduced_physics == []


def test_distribution_trailing_blank_is_zero():
    body, conv, rep = convert_str(HEX3 + "*Distribution, name=Disc\n, 1., 0., 0., 0., 1., 0.\n"
                                  "2, 0.866025403784, 0.5, 0., -0.5, 0.866025403784,\n"
                                  "*Orientation, name=Ori-1\nDisc\n3, 0.\n"
                                  "*Solid Section, elset=PAIR, material=M, orientation=Ori-1\n,\n")
    assert _card(body, "*DISTRIBUTION, NAME=DISC")[1] == "2, 0.866025403784, 0.5, 0., -0.5, 0.866025403784, 0."
    assert conv.reduced_physics == [], conv.reduced_physics


def test_section_controls_defaults_change_nothing():
    base = (HEX.replace("C3D8,", "C3D8R,") + "*Material, name=M\n*Elastic\n1000., 0.3\n"
            "*Solid Section, elset=EALL, material=M, controls=SC\n")
    # HOURGLASS=STIFFNESS is Abaqus/Standard's default; data-line value 7 is not used, 8 is an
    # Abaqus/Explicit drill scale
    body, conv, _ = convert_str(base + "*Section Controls, name=SC, hourglass=STIFFNESS\n"
                                "1., 1., 2., 0.5, 0.5, 1., 5., 2.\n")
    assert conv.reduced_physics == [], conv.reduced_physics
    body, conv, _ = convert_str(base + "*Section Controls, name=SC\n2.\n")
    assert conv.reduced_physics == ["*SECTION CONTROLS (data-line value 1 = 2.)"]


def test_approximate_reframings_are_reduced_physics():
    body, conv, _ = convert_str(HEX + "*Material, name=M\n*Elastic\n1000., 0.5\n"
                                "*Solid Section, elset=EALL, material=M\n", approximate=True)
    assert conv.reduced_physics == ["--approximate: *ELASTIC Poisson ratio >= 0.5 clamped to 0.475"]

COUPLED_HEX = HEX.replace("TYPE=C3D8", "TYPE=C3D8T") + """*ELEMENT, TYPE=MASS, ELSET=PM
9, 8
*NSET, NSET=TOP
5, 6, 7, 8
*NSET, NSET=BOT
1, 2, 3, 4
*NSET, NSET=ALLN, GENERATE
1, 8, 1
*MATERIAL, NAME=M
*ELASTIC
1000., 0.
*DENSITY
7.8e-9, 20.
7.7e-9, 520.
*CONDUCTIVITY
45.
*SPECIFIC HEAT
4.6e8, 20.
5.2e8, 520.
*EXPANSION
1.2e-5
*SOLID SECTION, ELSET=EALL, MATERIAL=M
*MASS, ELSET=PM
0.002
*AMPLITUDE, NAME=A
0., 0., 1., 1.
*INITIAL CONDITIONS, TYPE=TEMPERATURE
ALLN, 20.
*BOUNDARY
BOT, 1, 3
"""
COUPLED_STEP = "*STEP\n*COUPLED TEMPERATURE-DISPLACEMENT\n0.1, 1.\n*BOUNDARY\nTOP, 11, 11, 100.\n*END STEP\n"


def test_coupled_inertia_masses_scaled_away():
    # ccx 2.23 solves a transient *COUPLED TEMPERATURE-DISPLACEMENT step as a dynamic one with
    # the mass of every *DENSITY and *MASS, where Abaqus/Standard neglects inertia: the masses
    # go out divided by 1e30, the specific heats (temperature by temperature) and the GRAV /
    # CENTRIF magnitudes multiplied by it, so that density x specific heat and the body
    # forces stay as they were; the step card (ccx's HHT alpha) and the rest stay as given
    body, conv, rep = convert_str(COUPLED_HEX + "*STEP\n*COUPLED TEMPERATURE-DISPLACEMENT, DELTMX=5.\n"
                                                "0.1, 1.\n*DLOAD, AMPLITUDE=A\n"
                                                "EALL, GRAV, 9810., 0., 0., -1.\n"
                                                "PM, GRAV, 9810., 0., 0., -1.\n"
                                                "EALL, CENTRIF, 100., 0., 0., 0., 0., 0., 1.\n*END STEP\n")
    assert conv._mass_scale == 1e30
    assert _card(body, "*DENSITY") == ["7.8e-39, 20.", "7.7e-39, 520."]
    assert _card(body, "*SPECIFIC HEAT") == ["4.6e+38, 20.", "5.2e+38, 520."]
    assert _card(body, "*MASS, ELSET=PM") == ["2e-33"]
    assert _card(body, "*CONDUCTIVITY") == ["45."] and _card(body, "*EXPANSION") == ["1.2e-5"]
    for (rho, c), want in zip(zip(_card(body, "*DENSITY"), _card(body, "*SPECIFIC HEAT")),
                              (7.8e-9 * 4.6e8, 7.7e-9 * 5.2e8)):
        assert abs(float(rho.split(",")[0]) * float(c.split(",")[0]) / want - 1.0) < 1e-12
    st = _step(body, 1)
    assert "*COUPLED TEMPERATURE-DISPLACEMENT, DELTMX=5.\n0.1, 1.\n" in st and "ALPHA" not in body
    assert "*DLOAD, AMPLITUDE=A\nEALL, GRAV, 9.81e+33, 0., 0., -1.\nPM, GRAV, 9.81e+33, 0., 0., -1.\n" \
           "EALL, CENTRIF, 1e+32, 0., 0., 0., 0., 0., 1.\n" in st
    assert "Densities and *MASS values divided by 1e+30" in rep.text()
    assert "jumps at the start" not in rep.text() and "not scaled away" not in rep.text()
    assert not dangling_refs(reparse(body))


def test_coupled_inertia_only_in_transient_coupled_steps():
    # no mass acts in a steady-state coupled step (static in ccx too), a heat transfer or a
    # static step; ccx's own *UNCOUPLED TEMPERATURE-DISPLACEMENT, not an Abaqus keyword, means
    # what ccx makes of it; without a mass nothing moves: the cards stay as given, unflagged
    for deck, proc in ((COUPLED_HEX, "*COUPLED TEMPERATURE-DISPLACEMENT, STEADY STATE"),
                       (COUPLED_HEX, "*HEAT TRANSFER"), (COUPLED_HEX, "*STATIC"),
                       (COUPLED_HEX, "*UNCOUPLED TEMPERATURE-DISPLACEMENT"),
                       (COUPLED_HEX.replace("7.8e-9, 20.\n7.7e-9, 520.", "0.").replace(
                           "*MASS, ELSET=PM\n0.002", "*MASS, ELSET=PM\n0."),
                        "*COUPLED TEMPERATURE-DISPLACEMENT")):
        body, conv, rep = convert_str(deck + f"*STEP\n{proc}\n0.1, 1.\n*DLOAD\nEALL, GRAV, 9810., 0., "
                                             f"0., -1.\n*END STEP\n")
        assert conv._mass_scale is None, proc
        assert "EALL, GRAV, 9810., 0., 0., -1.\n" in body and "e+30" not in body, proc
        assert "inertia" not in rep.text() and "jumps at the start" not in rep.text(), proc


def test_coupled_inertia_kept_where_a_step_needs_the_mass():
    # ccx has one density per material for all steps: with a dynamic or eigenvalue step in the
    # deck the masses stay as they are and the coupled steps' inertia is warned about, as it is
    # when a value cannot be read
    for other in ("*STEP\n*FREQUENCY\n5\n*END STEP\n", "*STEP\n*DYNAMIC\n0.1, 1.\n*END STEP\n"):
        body, conv, rep = convert_str(COUPLED_HEX + COUPLED_STEP + other)
        assert conv._mass_scale is None
        assert _card(body, "*DENSITY") == ["7.8e-9, 20.", "7.7e-9, 520."]
        assert "(step 1): Abaqus/Standard neglects inertia" in rep.text()
        assert "need them (ccx has one density per material for all steps)" in rep.text()
    for old, new, what in (("*MASS, ELSET=PM\n0.002", "*MASS, ELSET=PM\nM0", "*MASS value 'M0'"),
                           ("*DENSITY\n7.8e-9, 20.\n7.7e-9, 520.", "*DENSITY, DEPENDENCIES=7\n7.8e-9",
                            "the rows of a *DENSITY, DEPENDENCIES= card"),
                           ("*DENSITY\n7.8e-9, 20.\n7.7e-9, 520.", "*DENSITY, DEPENDENCIES=1\n7.8e-9, 20., F1",
                            "*DENSITY value 'F1'")):
        body, conv, rep = convert_str(COUPLED_HEX.replace(old, new) + COUPLED_STEP)
        assert conv._mass_scale is None and "e+30" not in body
        assert f"not scaled away because the converter cannot read {what}" in rep.text(), what


def test_coupled_inertia_load_jump_warned():
    # without mass ccx's HHT step puts an increment in equilibrium when the one before was: a
    # mechanical load that jumps at the step start (no AMPLITUDE, Abaqus' STEP default in this
    # procedure, or removed by OP=NEW) is overshot at the first increments - warned; an
    # amplitude, *STEP, AMPLITUDE=RAMP or thermal loads alone do not jump
    for step, loads, warned in (("*STEP", "*CLOAD\n8, 3, 1.\n", True),
                                ("*STEP", "*DLOAD\nEALL, P2, 1.\n", True),
                                ("*STEP", "*CLOAD, AMPLITUDE=A\n8, 3, 1.\n", False),
                                ("*STEP, AMPLITUDE=RAMP", "*CLOAD\n8, 3, 1.\n", False),
                                ("*STEP", "*CLOAD, OP=NEW, AMPLITUDE=A\n", True),
                                ("*STEP", "*BOUNDARY\nTOP, 11, 11, 100.\n*DFLUX\nEALL, BF, 1.\n", False)):
        body, conv, rep = convert_str(COUPLED_HEX + f"{step}\n*COUPLED TEMPERATURE-DISPLACEMENT\n"
                                                    f"0.1, 1.\n{loads}*END STEP\n")
        assert conv._mass_scale == 1e30, (step, loads)
        assert ("(step 1): a mechanical load without AMPLITUDE" in rep.text() and
                "jumps at the start of the step" in rep.text()) == warned, (step, loads)
    # only the steps where it jumps are named
    body, _, rep = convert_str(COUPLED_HEX + "*STEP\n*COUPLED TEMPERATURE-DISPLACEMENT\n0.1, 1.\n"
                                             "*CLOAD, AMPLITUDE=A\n8, 3, 1.\n*END STEP\n" + COUPLED_STEP +
                               "*STEP\n*COUPLED TEMPERATURE-DISPLACEMENT\n0.1, 1.\n*CLOAD\n8, 3, 2.\n"
                               "*END STEP\n")
    assert "(step 1, 2, 3): Abaqus/Standard neglects inertia" in rep.text()
    assert "(step 3): a mechanical load without AMPLITUDE" in rep.text()
    # a BC that a later *BOUNDARY, OP=NEW releases drops its reaction at the step start: a jump
    # too; not where OP=NEW gives every mechanical BC again, nor for a temperature BC
    held = COUPLED_HEX + "*STEP\n*COUPLED TEMPERATURE-DISPLACEMENT\n0.1, 1.\n*BOUNDARY\nTOP, 3, 3\n" \
                         "TOP, 11, 11, 100.\n*END STEP\n"
    for again, warned in (("BOT, 1, 3\n", True), ("BOT, 1, 3\nTOP, 3, 3\n", False),
                          ("BOT, 1, 3\nTOP, 3, 3\n8, 11, 11, 50.\n", False)):
        body, _, rep = convert_str(held + "*STEP\n*COUPLED TEMPERATURE-DISPLACEMENT\n0.1, 1.\n"
                                          f"*BOUNDARY, OP=NEW\n{again}*END STEP\n")
        assert ("(step 2): a mechanical load without AMPLITUDE" in rep.text()) == warned, again
        assert "(step 1): a mechanical load" not in rep.text(), again
    # a DOF the node does not have bears no load: DOF 3 of a plane-strain node
    plane = ("*NODE\n1, 0., 0.\n2, 1., 0.\n3, 1., 1.\n4, 0., 1.\n*ELEMENT, TYPE=CPE4T, ELSET=EALL\n"
             "1, 1, 2, 3, 4\n*NSET, NSET=BOT\n1, 2\n*NSET, NSET=ALLN\n1, 2, 3, 4\n*MATERIAL, NAME=M\n"
             "*ELASTIC\n1000., 0.\n*DENSITY\n1.\n*CONDUCTIVITY\n1.\n*SPECIFIC HEAT\n1.\n"
             "*SOLID SECTION, ELSET=EALL, MATERIAL=M\n1.\n*INITIAL CONDITIONS, TYPE=TEMPERATURE\n"
             "ALLN, 0.\n*BOUNDARY\nBOT, 1, 3\n")
    for again, warned in (("BOT, 1, 2\n", False), ("BOT, 1, 1\n", True)):
        body, conv, rep = convert_str(plane + "*STEP\n*COUPLED TEMPERATURE-DISPLACEMENT\n0.1, 1.\n"
                                              f"*BOUNDARY, OP=NEW\n{again}*END STEP\n")
        assert conv._mass_scale == 1e30, again
        assert ("(step 1): a mechanical load without AMPLITUDE" in rep.text()) == warned, again
    # ... and a point mass leaves the model 2-D: DOF 3 of its node bears nothing either
    body, conv, rep = convert_str(plane.replace("*NSET, NSET=BOT", "*ELEMENT, TYPE=MASS, ELSET=PM\n9, 4\n"
                                                                   "*NSET, NSET=BOT") +
                                  "*MASS, ELSET=PM\n1.\n*BOUNDARY\n4, 3, 3\n*STEP\n"
                                  "*COUPLED TEMPERATURE-DISPLACEMENT\n0.1, 1.\n*BOUNDARY, OP=NEW\n"
                                  "BOT, 1, 3\n*END STEP\n")
    assert conv._mass_scale == 1e30 and "a mechanical load without AMPLITUDE" not in rep.text()


def test_coupled_inertia_dependencies_rows():
    # a *DENSITY / *SPECIFIC HEAT with DEPENDENCIES= is collapsed to the no-field state first,
    # then scaled: the property value only, not the temperature
    deck = COUPLED_HEX.replace("*DENSITY\n7.8e-9, 20.\n7.7e-9, 520.\n",
                               "*DENSITY, DEPENDENCIES=1\n7.8e-9, 20., 0.\n7.0e-9, 20., 1.\n")
    body, conv, _ = convert_str(deck + COUPLED_STEP)
    assert conv._mass_scale == 1e30 and _card(body, "*DENSITY") == ["7.8e-39, 20."]


def test_coupled_inertia_example():
    # the deck validate_with_ccx.py runs: masses, specific heat and gravity scaled; the load
    # that jumps in step 2 is warned about
    body, _, rep = convert(os.path.join(EXAMPLES, "coupled_quasistatic_bars.inp"))
    assert _card(body, "*DENSITY") == ["1.5625e-31"] and _card(body, "*SPECIFIC HEAT") == ["1e+30"]
    assert _card(body, "*MASS, ELSET=WEIGHTS") == ["2.5e-31"]
    assert "BARS, GRAV, 1e+30, 0., 0., -1.\nWEIGHTS, GRAV, 1e+30, 0., 0., -1.\n" in _step(body, 1)
    assert "(step 2): a mechanical load without AMPLITUDE" in rep.text()
    assert not dangling_refs(reparse(body))

# --- rigid elements and analytical rigid surfaces ---------------------------------------

RIGID_PLATE = """*NODE
1, 0.,0.,0.
2, 1.,0.,0.
3, 1.,1.,0.
4, 0.,1.,0.
5, 2.,0.,0.
9, 0.5, 0.5, 1.
*ELEMENT, TYPE=R3D4, ELSET=PLATE
1, 1, 2, 3, 4
*ELEMENT, TYPE=R3D3, ELSET=PLATE
2, 2, 5, 3
*MATERIAL, NAME=STEEL
*ELASTIC
210000., 0.3
*RIGID BODY, REF NODE=9, ELSET=PLATE
"""


def _emitted(body):
    g = reparse(body)
    return g, {e: t for e, (t, _) in g.elements.items()}


def _face_points(g, eid, face):
    typ, conn = g.elements[eid]
    fam = "WEDGE" if typ == "C3D6" else "HEX"
    pos = A.FACE_NODES[fam][int(face[1:])]
    n = 3 if fam == "WEDGE" and face in ("S1", "S2") else 4
    return [g.nodes[conn[i - 1]] for i in pos[:n]]


def _outward(g, eid, face):
    """Unit outward normal of a skin element's face (the Abaqus / ccx face node order turns
    clockwise seen from outside)."""
    p = _face_points(g, eid, face)
    if len(p) == 3:
        nrm = A.vcross(A.vsub(p[1], p[0]), A.vsub(p[2], p[0]))
    else:
        nrm = A.vcross(A.vsub(p[2], p[0]), A.vsub(p[3], p[1]))
    return A.vscale(A.vunit(nrm), -1.0)


def _surface_lines(body, name):
    m = re.search(r"\*SURFACE, NAME=" + name + r"[^\n]*\n((?:[^*][^\n]*\n)+)", body)
    return [l.split(",") for l in m.group(1).strip().splitlines()] if m else []


def test_rigid_facets_become_skins_with_their_contact_side():
    deck = RIGID_PLATE + ("*SURFACE, NAME=UP\nPLATE, SPOS\n*SURFACE, NAME=DOWN\nPLATE, SNEG\n"
                          "*SURFACE, NAME=BOTH\nPLATE,\n*STEP\n*STATIC\n*BOUNDARY\n9, 1, 6\n*END STEP\n")
    body, conv, rep = convert_str(deck)
    g, types = _emitted(body)
    assert types[1] == "C3D8" and types[2] == "C3D6"              # same ids, the SPOS skins
    for name, want in (("UP", 1.0), ("DOWN", -1.0)):
        lines = _surface_lines(body, name)
        assert lines and all(f[1].strip() in ("S1", "S2") for f in lines)
        for f in lines:
            for e in g.elset(f[0].strip()):
                n = _outward(g, e, f[1].strip())
                assert abs(n[2] - want) < 1e-12, (name, e, n)       # +z is the facets' SPOS
                assert all(abs(p[2]) < 1e-12 for p in _face_points(g, e, f[1].strip()))
    assert len(_surface_lines(body, "BOTH")) == 2                  # double-sided: both skins
    # the body moves every node of the skins (facet nodes and the offset copies)
    m = re.search(r"\*RIGID BODY, REF NODE=9, NSET=([^,\s]+), ROT NODE=\d+", body)
    members = set(g.nset(m.group(1)))
    skin_nodes = {n for e in g.elset(A.RIGID_SET) for n in g.elements[e][1]}
    assert skin_nodes <= members and {1, 2, 3, 4, 5} <= members
    # the skin material comes after the deck's (ccx's HARD contact stiffness is 50 x the
    # first material's first constant) with its modulus, and with no density outside
    # explicit dynamics
    assert body.index("*MATERIAL, NAME=STEEL") < body.index(f"*MATERIAL, NAME={A.RIGID_SET}") \
        < body.index("*STEP")
    blk = body[body.index(f"*MATERIAL, NAME={A.RIGID_SET}"):]
    assert "*ELASTIC\n210000., 0.\n*DENSITY\n0.\n" in blk
    assert f"*SOLID SECTION, ELSET={A.RIGID_SET}, MATERIAL={A.RIGID_SET}" in blk


def test_rigid_skins_in_explicit_dynamics_get_a_small_density():
    deck = RIGID_PLATE + "*STEP\n*DYNAMIC, EXPLICIT\n, 1e-3\n*BOUNDARY\n9, 1, 6\n*END STEP\n"
    body, _, _ = convert_str(deck)
    m = re.search(r"\*MATERIAL, NAME=" + A.RIGID_SET + r"\n\*ELASTIC\n(\S+), 0\.\n\*DENSITY\n(\S+)\n", body)
    e, rho = float(m.group(1)), float(m.group(2))
    assert 0 < rho < 1e-6 and 0 < e < 1e-6                        # wave speed 1e-3 of the deck's
    assert all(len(x) <= 20 for x in (m.group(1), m.group(2)))     # ccx reads 20 characters


def test_rigid_density_with_thickness_needs_approximate():
    deck = (RIGID_PLATE.replace("*RIGID BODY, REF NODE=9, ELSET=PLATE",
                                "*RIGID BODY, REF NODE=9, ELSET=PLATE, DENSITY=7.8e-9\n0.5")
            + "*STEP\n*DYNAMIC, EXPLICIT\n, 1e-3\n*END STEP\n")
    body, _, rep = convert_str(deck)
    assert "*ELEMENT, TYPE=R3D4" in body and "DENSITY= with a thickness" in rep.text()
    body, _, rep = convert_str(deck, approximate=True)
    assert "*ELEMENT, TYPE=R3D4" not in body and "[APPROX] *RIGID BODY, DENSITY=" in rep.text()


def test_rigid_explicit_thickness_offsets_the_contact_faces():
    # Abaqus/Explicit: a thickness t on the *RIGID BODY data line puts the SPOS contact
    # surface t/2 above the facet (OFFSET=SPOS: on it), SNEG t/2 below
    for off, up, down in (("", 0.25, -0.25), (", OFFSET=SPOS", 0.0, -0.5)):
        deck = (RIGID_PLATE.replace("*RIGID BODY, REF NODE=9, ELSET=PLATE",
                                    f"*RIGID BODY, REF NODE=9, ELSET=PLATE{off}\n0.5")
                + "*SURFACE, NAME=UP\nPLATE, SPOS\n*SURFACE, NAME=DOWN\nPLATE, SNEG\n"
                + "*STEP\n*DYNAMIC, EXPLICIT\n, 1e-3\n*END STEP\n")
        body, _, _ = convert_str(deck)
        g, _ = _emitted(body)
        for name, z in (("UP", up), ("DOWN", down)):
            for f in _surface_lines(body, name):
                for e in g.elset(f[0].strip()):
                    assert all(abs(p[2] - z) < 1e-12 for p in _face_points(g, e, f[1].strip())), (off, name)
        assert "*RIGID BODY, REF NODE=9, NSET=" in body and "\n0.5\n" not in body


def test_plane_and_axisymmetric_rigid_segments():
    # R2D2 in a plane-strain model: a C3D8 through twice the thickest section, face S5 on
    # the segment (SPOS = 90 degrees counterclockwise from node 1 -> 2), a 3-D body held
    # out of its plane in model data and again after OP=NEW
    plane = ("*NODE\n1,0.,0.\n2,1.,0.\n3,1.,1.\n4,0.,1.\n11,1.5,1.\n12,-0.5,1.\n9,0.5,2.\n"
             "*ELEMENT, TYPE=CPE4, ELSET=B\n1,1,2,3,4\n*ELEMENT, TYPE=R2D2, ELSET=R\n5,11,12\n"
             "*SOLID SECTION, ELSET=B, MATERIAL=M\n2.\n*MATERIAL, NAME=M\n*ELASTIC\n100., 0.3\n"
             "*SURFACE, NAME=TOOL\nR, SPOS\n*RIGID BODY, REF NODE=9, ELSET=R\n"
             "*STEP\n*STATIC\n*BOUNDARY, OP=NEW\n9, 1, 2\n9, 6, 6\n*END STEP\n")
    body, conv, _ = convert_str(plane)
    g, types = _emitted(body)
    assert types[5] == "C3D8"
    (elset, face), = [(f[0].strip(), f[1].strip()) for f in _surface_lines(body, "TOOL")]
    assert face == "S5"
    pts = _face_points(g, 5, "S5")
    assert sorted({round(p[2], 9) for p in pts}) == [-2.0, 2.0] and all(abs(p[1] - 1) < 1e-12 for p in pts)
    assert abs(_outward(g, 5, "S5")[1] + 1.0) < 1e-12               # SPOS of 11 -> 12 is -y
    rot = conv._rb_rot[9]
    holds = f"*BOUNDARY\n9, 3, 3\n{rot}, 1, 2\n"
    assert body.count(holds) == 2                                  # model data + after OP=NEW
    # REFNODE= (no blank) is the same parameter: the same deck (it lost the holds)
    assert convert_str(plane.replace("REF NODE=9", "REFNODE=9"))[0] == body
    m = re.search(r"\*RIGID BODY, REF NODE=9, NSET=([^,\s]+)", body)
    assert {11, 12} <= set(g.nset(m.group(1)))                     # the segment's own nodes too
    # RAX2 in an axisymmetric model: the +/-1 degree sector ccx expands CAX elements to
    ax = plane.replace("CPE4", "CAX4").replace("R2D2", "RAX2").replace("12,-0.5,1.", "12,0.,1.")
    body, _, _ = convert_str(ax)
    g, types = _emitted(body)
    assert types[5] == "C3D8"
    for p in _face_points(g, 5, "S5"):
        r = math.hypot(p[0], p[2])
        assert r < 1e-12 or abs(abs(math.degrees(math.atan2(p[2], p[0]))) - 1.0) < 1e-9


def test_rb3d2_links_join_their_rigid_body():
    deck = ("*NODE\n1,0.,0.,0.\n2,1.,0.,0.\n3,2.,0.,0.\n*ELEMENT, TYPE=RB3D2, ELSET=L\n1,1,2\n2,2,3\n"
            "*RIGID BODY, REF NODE=1, ELSET=L\n*STEP\n*STATIC\n*BOUNDARY\n1,1,6\n*END STEP\n")
    body, _, _ = convert_str(deck)
    assert "RB3D2" not in body.split("** ===")[-1] and "*ELSET, ELSET=L" not in body
    m = re.search(r"\*RIGID BODY, REF NODE=1, NSET=([^,\s]+)", body)
    members = set(reparse(body).nset(m.group(1)))
    assert members >= {2, 3} and 1 not in members          # the reference node is no member


ANALYTIC_2D = ("*NODE\n1,0.,0.\n2,1.,0.\n3,1.,1.\n4,0.,1.\n9,0.,4.\n"
               "*ELEMENT, TYPE=CAX4, ELSET=B\n1,1,2,3,4\n*ELSET, ELSET=TOPE\n1\n"
               "*SURFACE, NAME=TOP\nTOPE, S3\n*SOLID SECTION, ELSET=B, MATERIAL=M\n"
               "*MATERIAL, NAME=M\n*ELASTIC\n100., 0.3\n")


def test_analytical_segments_exact_or_approximate():
    straight = ANALYTIC_2D + ("*SURFACE, TYPE=SEGMENTS, NAME=TOOL\nSTART, 1.5, 1.\nLINE, 0., 1.\n"
                              "*RIGID BODY, REF NODE=9, ANALYTICAL SURFACE=TOOL\n"
                              "*SURFACE INTERACTION, NAME=I\n*SURFACE BEHAVIOR, PRESSURE-OVERCLOSURE=HARD\n"
                              "*CONTACT PAIR, INTERACTION=I\nTOP, TOOL\n")
    body, _, rep = convert_str(straight)
    assert "meshed exactly" in rep.text() and "[APPROX]" not in rep.text()
    g, types = _emitted(body)
    (elset, face), = [(f[0].strip(), f[1].strip()) for f in _surface_lines(body, "TOOL")]
    assert face == "S5" and len(g.elset(elset)) >= 2                # cut to the slave's size
    for e in g.elset(elset):
        assert abs(_outward(g, e, face)[1] + 1.0) < 1e-9            # n = e3 x s: -z towards TOP
        assert all(abs(p[1] - 1.0) < 1e-12 for p in _face_points(g, e, face))
    assert re.search(r"\*RIGID BODY, REF NODE=9, NSET=\S+, ROT NODE=\d+", body)
    curved = straight.replace("START, 1.5, 1.\nLINE, 0., 1.", "START, 1.5, 2.5\nCIRCL, 0., 1., 0., 2.5")
    body, _, rep = convert_str(curved)
    assert "not converted" in rep.text() and "--approximate" in rep.text()
    for kw in ("*SURFACE, TYPE=SEGMENTS", "*RIGID BODY", "*CONTACT PAIR"):
        assert f"** {kw}" in body                                   # commented out, all three
    # a *TIE's line on that surface is commented out, its other lines kept: reduced physics
    tie = (ANALYTIC_2D + "*SURFACE, NAME=BOT\nTOPE, S1\n*SURFACE, NAME=RT\nTOPE, S2\n" +
           curved[len(ANALYTIC_2D):].split("*SURFACE INTERACTION")[0] + "*TIE, NAME=T1\nTOP, TOOL\nBOT, RT\n")
    body, conv, _ = convert_str(tie)
    assert "\nBOT, RT" in body and "** TOP, TOOL" in body and "*TIE" in conv.reduced_physics
    body, _, rep = convert_str(curved, approximate=True)
    msg = [m for _, m in rep.entries if m.startswith("[APPROX] Analytical rigid surface TOOL")]
    assert msg and "degrees" in msg[0] and "chord sag" in msg[0]
    g, _ = _emitted(body)
    (elset, face), = [(f[0].strip(), f[1].strip()) for f in _surface_lines(body, "TOOL")]
    for e in g.elset(elset):                                       # facet ends on the arc
        for p in _face_points(g, e, face):
            r = math.hypot(p[0], p[2])
            assert abs(math.hypot(r, p[1] - 2.5) - 1.5) < 1e-9


def test_analytical_cylinder_and_revolution_frames():
    base = ("*NODE\n1,0.,0.,0.\n2,1.,0.,0.\n3,1.,1.,0.\n4,0.,1.,0.\n5,0.,0.,1.\n6,1.,0.,1.\n7,1.,1.,1.\n"
            "8,0.,1.,1.\n9,0.5,0.5,3.\n*ELEMENT, TYPE=C3D8, ELSET=B\n1,1,2,3,4,5,6,7,8\n"
            "*SOLID SECTION, ELSET=B, MATERIAL=M\n*MATERIAL, NAME=M\n*ELASTIC\n100., 0.3\n")
    # CYLINDER: point c lies on the NEGATIVE local z-axis, so with c = a - Y the local y is
    # -Z and the profile's normal e3 x s (s = +x) points down
    cyl = base + ("*SURFACE, TYPE=CYLINDER, NAME=TOOL\n0., 0., 1., 1., 0., 1.\n0., -1., 1.\n"
                  "START, -0.5, 0.\nLINE, 1.5, 0.\n*RIGID BODY, REF NODE=9, ANALYTICAL SURFACE=TOOL\n")
    body, _, rep = convert_str(cyl)
    assert "meshed exactly" in rep.text()
    g, _ = _emitted(body)
    (elset, face), = [(f[0].strip(), f[1].strip()) for f in _surface_lines(body, "TOOL")]
    ys = [p[1] for e in g.elset(elset) for p in _face_points(g, e, face)]
    assert min(ys) < 0.0 and max(ys) > 1.0                         # spans the model along Y
    for e in g.elset(elset):
        assert abs(_outward(g, e, face)[2] + 1.0) < 1e-9
        assert all(abs(p[2] - 1.0) < 1e-12 for p in _face_points(g, e, face))
    # REVOLUTION about the axis a -> b: a cylinder r = 2 whose profile runs down (-z) has
    # its normal outward (e3 x s, e3 = e_r x e_z), only under --approximate
    rev = base + ("*SURFACE, TYPE=REVOLUTION, NAME=TOOL\n0.5, 0.5, 0., 0.5, 0.5, 1.\n"
                  "START, 2., 1.\nLINE, 2., 0.\n*RIGID BODY, REF NODE=9, ANALYTICAL SURFACE=TOOL\n")
    body, _, rep = convert_str(rev)
    assert "not converted" in rep.text()
    body, _, rep = convert_str(rev, approximate=True)
    assert "circumference becomes" in rep.text()
    g, _ = _emitted(body)
    (elset, face), = [(f[0].strip(), f[1].strip()) for f in _surface_lines(body, "TOOL")]
    for e in g.elset(elset):
        p = _face_points(g, e, face)
        c = [sum(q[k] for q in p) / len(p) for k in range(3)]
        radial = A.vunit((c[0] - 0.5, c[1] - 0.5, 0.0))
        assert A.vdot(_outward(g, e, face), radial) > 0.99


def test_rotary_inertia_on_a_rigid_body_becomes_point_masses():
    deck = RIGID_PLATE + ("*ELEMENT, TYPE=MASS, ELSET=PM\n10, 9\n*MASS, ELSET=PM\n6.\n"
                          "*ELEMENT, TYPE=ROTARYI, ELSET=PI\n11, 9\n*ROTARY INERTIA, ELSET=PI\n"
                          "1.5, 2., 1., 0., 0., 0.\n*STEP\n*FREQUENCY\n3\n*END STEP\n")
    body, _, rep = convert_str(deck)
    assert "ROTARYI" not in body.split("** ===")[-1] and "*ROTARY INERTIA" not in body
    g = reparse(body)
    masses = {}
    for m in re.finditer(r"\*MASS, ELSET=(\S+)\n(\S+)\n", body):
        for e in g.elset(m.group(1)):
            masses[g.elements[e][1][0]] = masses.get(g.elements[e][1][0], 0.0) + float(m.group(2))
    assert abs(sum(masses.values()) - 6.0) < 1e-9                  # the body's mass unchanged
    c = g.nodes[9]
    first = [sum(m * (g.nodes[n][k] - c[k]) for n, m in masses.items()) for k in range(3)]
    assert max(abs(x) for x in first) < 1e-9                       # centre of mass unchanged
    inertia = [[sum(m * ((A.vdot(A.vsub(g.nodes[n], c), A.vsub(g.nodes[n], c)) if i == j else 0.0)
                         - (g.nodes[n][i] - c[i]) * (g.nodes[n][j] - c[j])) for n, m in masses.items())
                for j in range(3)] for i in range(3)]
    want = [[1.5, 0, 0], [0, 2.0, 0], [0, 0, 1.0]]
    assert max(abs(inertia[i][j] - want[i][j]) for i in range(3) for j in range(3)) < 1e-9
    m = re.search(r"\*RIGID BODY, REF NODE=9, NSET=([^,\s]+)", body)
    assert set(masses) <= set(g.nset(m.group(1))) | {9}           # the star moves with the body
    star = [e for e in g.elset(A.RIGID_SET) if g.elements[e][0] == "C3D4"]
    assert len(star) == 4                                          # its nodes need an element
    # a body of the deck's own elements (no rigid element) gets the same, and the material
    body, _, _ = convert_str(HEX + "*NODE\n9, 0.5, 0.5, 2.\n*NSET, NSET=ALLN\n1, 2, 3, 4, 5, 6, 7, 8\n"
                                   "*SOLID SECTION, ELSET=EALL, MATERIAL=M\n*MATERIAL, NAME=M\n*ELASTIC\n"
                                   "100., 0.3\n*RIGID BODY, REF NODE=9, TIE NSET=ALLN\n"
                                   "*ELEMENT, TYPE=MASS, ELSET=PM\n10, 9\n*MASS, ELSET=PM\n2.\n"
                                   "*ELEMENT, TYPE=ROTARYI, ELSET=PI\n11, 9\n*ROTARY INERTIA, ELSET=PI\n"
                                   "1., 1., 1.\n*STEP\n*FREQUENCY\n2\n*END STEP\n")
    assert "ROTARYI" not in body.split("** ===")[-1] and f"*MATERIAL, NAME={A.RIGID_SET}" in body
    assert "*MASS, ELSET=ABQ2CCX_STAR" in body
    # a distribution orientation has no axes to take (they were the global ones): refused
    _, conv, rep = convert_str(deck.replace("*ROTARY INERTIA, ELSET=PI\n", "*Distribution, name=OD\n"
                                            ", 0., 0., 1., 1., 0., 0.\n*Orientation, name=O\nOD\n"
                                            "*ROTARY INERTIA, ELSET=PI, ORIENTATION=O\n"))
    assert "an orientation without fixed rectangular axes: not converted" in rep.text()
    assert "*ROTARY INERTIA" in conv.reduced_physics


def test_tie_to_a_rigid_surface_makes_the_slave_nodes_members():
    deck = (HEX + "*NODE\n11, 0.,0.,1.\n12, 1.,0.,1.\n13, 1.,1.,1.\n14, 0.,1.,1.\n9, 0.5,0.5,2.\n"
            "*ELEMENT, TYPE=R3D4, ELSET=PLATE\n2, 11, 14, 13, 12\n*ELSET, ELSET=TOPE\n1\n"
            "*SURFACE, NAME=TOP\nTOPE, S2\n*SURFACE, NAME=TOOL\nPLATE, SPOS\n"
            "*SOLID SECTION, ELSET=EALL, MATERIAL=M\n*MATERIAL, NAME=M\n*ELASTIC\n100., 0.3\n"
            "*RIGID BODY, REF NODE=9, ELSET=PLATE\n*TIE, NAME=GLUE\nTOP, TOOL\n"
            "*STEP\n*STATIC\n*BOUNDARY\n9, 1, 6\n*END STEP\n")
    body, _, rep = convert_str(deck)
    assert "*TIE" not in body.replace("** abq2ccx: *TIE", "") and "join that rigid body" in rep.text()
    m = re.search(r"\*RIGID BODY, REF NODE=9, NSET=([^,\s]+)", body)
    assert {5, 6, 7, 8} <= set(reparse(body).nset(m.group(1)))


def test_instanced_analytical_surface_moves_with_its_instance():
    deck = ("*PART, NAME=TOOLP\n*SURFACE, TYPE=CYLINDER, NAME=FACE\nSTART, -1., 0.\nLINE, 1., 0.\n"
            "*NODE\n1, 0., 0., 0.\n*NSET, NSET=RP\n1\n*RIGID BODY, REF NODE=RP, ANALYTICAL SURFACE=FACE\n"
            "*END PART\n*PART, NAME=BLK\n" + HEX + "*SOLID SECTION, ELSET=EALL, MATERIAL=M\n*END PART\n"
            "*ASSEMBLY, NAME=A\n*INSTANCE, NAME=T1, PART=TOOLP\n0., 0., 5.\n0., 0., 5., 1., 0., 5., 90.\n"
            "*END INSTANCE\n*INSTANCE, NAME=B1, PART=BLK\n*END INSTANCE\n*END ASSEMBLY\n"
            "*MATERIAL, NAME=M\n*ELASTIC\n100., 0.3\n")
    blocks = A.flatten_assembly(A.read_blocks_text(deck) if hasattr(A, "read_blocks_text") else
                                _blocks_of(deck), A.Report(), Opt())
    surf = [b for b in blocks if b.keyword == "SURFACE" and (b.param("TYPE") or "").upper() == "CYLINDER"]
    assert len(surf) == 1 and surf[0].param("NAME") != "FACE"
    frame = A.analytic_profile(surf[0])[0]["frame"]
    # part axes moved by the instance: a = (0,0,5); x stays x; the part's -z turns to +y
    assert max(abs(x - y) for x, y in zip(frame[0], (0.0, 0.0, 5.0))) < 1e-9
    assert max(abs(x - y) for x, y in zip(frame[1], (1.0, 0.0, 5.0))) < 1e-9
    assert max(abs(x - y) for x, y in zip(frame[2], (0.0, 1.0, 5.0))) < 1e-9
    rb = [b for b in blocks if b.keyword == "RIGID BODY"]
    assert rb[0].param("ANALYTICAL SURFACE") == surf[0].param("NAME")


def test_loads_on_rigid_elements():
    deck = RIGID_PLATE.replace("*ELEMENT, TYPE=R3D3, ELSET=PLATE\n2, 2, 5, 3\n", "") + (
        "*SURFACE, NAME=UP\nPLATE, SPOS\n*SURFACE, NAME=DOWN\nPLATE, SNEG\n*STEP\n*STATIC\n"
        "*BOUNDARY\n9, 1, 6\n{}*END STEP\n")
    # an element-based P pushes along the element normal (+z here): minus a pressure on the
    # SPOS skin's face S2; a surface P pushes into its side's face
    body, _, _ = convert_str(deck.format("*DLOAD\nPLATE, P, 10.\n"))
    assert "*DLOAD\n1, P2, -10.\n" in body
    body, _, _ = convert_str(deck.format("*DSLOAD\nUP, P, 10.\n"))
    assert "*DLOAD\n1, P2, 10.\n" in body
    body, _, _ = convert_str(deck.format("*DSLOAD\nDOWN, P, 10.\n"))
    m = re.search(r"\*DLOAD\n(\d+), P1, 10\.\n", body)
    assert m and int(m.group(1)) != 1                              # the SNEG skin, face S1
    # a body force per volume would act on the skin's volume: commented out; gravity on
    # rigid elements only: nothing (no mass in Abaqus/Standard)
    body, _, rep = convert_str(deck.format("*DLOAD\nPLATE, BZ, 10.\n"))
    assert "** PLATE, BZ, 10." in body and "\nPLATE, BZ" not in body
    body, _, _ = convert_str(deck.format("*DLOAD\nPLATE, GRAV, 9.81, 0., 0., -1.\n"))
    assert "-> no load: it acts only on rigid elements" in body


def test_pressure_on_plane_rigid_segments_is_per_unit_depth():
    # an R2D2 has no section thickness: Abaqus' P acts per unit depth, while its skin spans
    # z = -T .. T (T the thickest section, 2 here), so the face pressure is P / (2 T)
    deck = ("*NODE\n1,0.,0.\n2,1.,0.\n3,1.,1.\n4,0.,1.\n11,1.5,1.\n12,-0.5,1.\n9,0.5,2.\n"
            "*ELEMENT, TYPE=CPE4, ELSET=B\n1,1,2,3,4\n*ELEMENT, TYPE=R2D2, ELSET=R\n5,11,12\n"
            "*SOLID SECTION, ELSET=B, MATERIAL=M\n2.\n*MATERIAL, NAME=M\n*ELASTIC\n100., 0.3\n"
            "*RIGID BODY, REF NODE=9, ELSET=R\n*STEP\n*STATIC\n*BOUNDARY\n9, 1, 6\n"
            "*DLOAD\nR, P, 1.\n*END STEP\n")
    body, _, rep = convert_str(deck)
    assert "*DLOAD\n5, P5, -0.25\n" in body and "per unit depth" in rep.text()
    assert "Unknown element type R2D2" not in rep.text()


def test_reference_node_on_a_facet_is_no_member():
    # ccx's reaction at a reference node misses the body's share when a skin is attached to
    # it: the skin gets a copy of the node, and the reference node is not in the body's set
    body, _, _ = convert_str(RIGID_PLATE.replace("REF NODE=9", "REF NODE=1"))
    g = reparse(body)
    assert 1 not in g.elements[1][1]
    m = re.search(r"\*RIGID BODY, REF NODE=1, NSET=([^,\s]+)", body)
    members = set(g.nset(m.group(1)))
    assert 1 not in members and {2, 3, 4} <= members
    copy = [n for n in g.elements[1][1] if n not in (2, 3, 4) and g.nodes[n] == g.nodes[1]]
    assert copy and copy[0] in members


def test_instanced_rotary_inertia_turns_with_its_instance():
    # without an ORIENTATION a part's rotary inertia is in the part's axes (Abaqus): an
    # instance turned 90 degrees about z gives I' = R I R^T
    deck = ("*PART, NAME=P\n*NODE\n1, 0., 0., 0.\n*ELEMENT, TYPE=ROTARYI, ELSET=RI\n1, 1\n"
            "*ROTARY INERTIA, ELSET=RI\n1., 2., 3., 0.5, 0., 0.\n*END PART\n*ASSEMBLY, NAME=A\n"
            "*INSTANCE, NAME=I1, PART=P\n0., 0., 0.\n0., 0., 0., 0., 0., 1., 90.\n*END INSTANCE\n"
            "*END ASSEMBLY\n")
    blocks = A.flatten_assembly(_blocks_of(deck), A.Report(), Opt())
    card, = [b for b in blocks if b.keyword == "ROTARY INERTIA"]
    vals = [float(x) for x in card.data[0].split(",")]
    assert max(abs(x - y) for x, y in zip(vals, (2.0, 1.0, 3.0, -0.5, 0.0, 0.0))) < 1e-12


def test_plane_rotary_inertia_uses_only_i33():
    # Abaqus' 2-D input gives only I33 (", , I33"): the star lies in the plane, without the
    # triangle-inequality refusal a 3-D tensor diag(0, 0, I33) would get
    deck = ("*NODE\n1,0.,0.\n2,1.,0.\n3,1.,1.\n4,0.,1.\n9,0.5,0.5\n*ELEMENT, TYPE=CPE4, ELSET=B\n"
            "1,1,2,3,4\n*SOLID SECTION, ELSET=B, MATERIAL=M\n1.\n*MATERIAL, NAME=M\n*ELASTIC\n"
            "1000., 0.3\n*DENSITY\n1e-12\n*RIGID BODY, REF NODE=9, ELSET=B\n"
            "*ELEMENT, TYPE=MASS, ELSET=MM\n20, 9\n*MASS, ELSET=MM\n2.\n"
            "*ELEMENT, TYPE=ROTARYI, ELSET=RI\n21, 9\n*ROTARY INERTIA, ELSET=RI\n, , 0.25\n"
            "*STEP\n*FREQUENCY\n2\n*END STEP\n")
    body, _, rep = convert_str(deck)
    assert "triangle inequality" not in rep.text() and "ROTARYI" not in body.split("** ===")[-1]
    g = reparse(body)
    masses = {}
    for m in re.finditer(r"\*MASS, ELSET=(\S+)\n(\S+)\n", body):
        for e in g.elset(m.group(1)):
            masses[g.elements[e][1][0]] = masses.get(g.elements[e][1][0], 0.0) + float(m.group(2))
    c = g.nodes[9]
    assert all(abs(g.nodes[n][2]) < 1e-12 for n, m in masses.items() if m)       # in the plane
    i33 = sum(m * ((g.nodes[n][0] - c[0]) ** 2 + (g.nodes[n][1] - c[1]) ** 2) for n, m in masses.items())
    assert abs(i33 - 0.25) < 1e-12 and abs(sum(masses.values()) - 2.0) < 1e-12


def test_axisymmetric_rotary_inertia_is_dropped_only_where_exact():
    deck = ("*NODE\n1,0.,0.\n2,1.,0.\n3,1.,1.\n4,0.,1.\n11,1.5,1.\n12,0.,1.\n9,0.5,2.\n"
            "*ELEMENT, TYPE=CAX4, ELSET=B\n1,1,2,3,4\n*ELEMENT, TYPE=RAX2, ELSET=R\n5,11,12\n"
            "*SOLID SECTION, ELSET=B, MATERIAL=M\n*MATERIAL, NAME=M\n*ELASTIC\n100., 0.3\n"
            "*DENSITY\n1.\n*RIGID BODY, REF NODE=9, ELSET=R\n*ELEMENT, TYPE=MASS, ELSET=MM\n"
            "20, 9\n*MASS, ELSET=MM\n2.\n*ELEMENT, TYPE=ROTARYI, ELSET=RI\n21, 9\n"
            "*ROTARY INERTIA, ELSET=RI\n, , 0.25\n*STEP\n{}\n*END STEP\n")
    body, _, rep = convert_str(deck.format("*STATIC"))            # no inertia acts: exact
    assert "ROTARYI" not in body.split("** ===")[-1] and "no dynamic or frequency step" in rep.text()
    body, _, rep = convert_str(deck.format("*FREQUENCY\n2"))
    assert "ROTARYI" in body.split("** ===")[-1] and "not converted" in rep.text()
    body, _, rep = convert_str(deck.format("*FREQUENCY\n2"), approximate=True)
    assert "ROTARYI" not in body.split("** ===")[-1] and "[APPROX] ROTARYI" in rep.text()


TIED_PLATE = (HEX + "*NODE\n11, 0.,0.,1.\n12, 1.,0.,1.\n13, 1.,1.,1.\n14, 0.,1.,1.\n9, 0.5,0.5,2.\n"
              "*ELEMENT, TYPE=R3D4, ELSET=PLATE\n2, 11, 14, 13, 12\n*ELSET, ELSET=TOPE\n1\n"
              "*SURFACE, NAME=TOP\nTOPE, S2\n*SURFACE, NAME=TOOL\nPLATE, SPOS\n"
              "*SOLID SECTION, ELSET=EALL, MATERIAL=M\n*MATERIAL, NAME=M\n*ELASTIC\n100., 0.3\n"
              "*RIGID BODY, REF NODE=9, ELSET=PLATE\n{}*STEP\n*STATIC\n*BOUNDARY\n9, 1, 6\n*END STEP\n")


def _body_members(body, ref=9):
    m = re.search(rf"\*RIGID BODY, REF NODE={ref}, NSET=([^,\s]+)", body)
    return set(reparse(body).nset(m.group(1)))


def test_tied_contact_pair_to_a_rigid_surface_makes_the_slave_nodes_members():
    body, _, rep = convert_str(TIED_PLATE.format("*SURFACE INTERACTION, NAME=G\n"
                                                 "*CONTACT PAIR, INTERACTION=G, TIED\nTOP, TOOL\n"))
    assert "*TIE" not in body and "*CONTACT PAIR" not in body.replace("** abq2ccx: *CONTACT PAIR", "")
    assert {5, 6, 7, 8} <= _body_members(body) and "join that rigid body" in rep.text()


def test_tie_to_a_rigid_surface_follows_abaqus_tolerances():
    # Abaqus' default position tolerance: 10 % of the typical master facet diagonal (sqrt 2
    # here) surface-to-surface, 5 % node-to-surface; a node 0.1 below the plate is tied by
    # the first and moved onto it, left alone by the second
    low = TIED_PLATE.replace("7, 1.,1.,1.", "7, 1.,1.,0.9")
    body, conv, _ = convert_str(low.format("*TIE, NAME=GLUE\nTOP, TOOL\n"))
    assert 7 in _body_members(body) and abs(conv.geom.nodes[7][2] - 1.0) < 1e-12
    body, conv, rep = convert_str(low.format("*TIE, NAME=GLUE, TYPE=NODE TO SURFACE\nTOP, TOOL\n"))
    assert 7 not in _body_members(body) and {5, 6, 8} <= _body_members(body)
    assert abs(conv.geom.nodes[7][2] - 0.9) < 1e-12 and "left untied, as Abaqus" in rep.text()
    # TIED NSET: exactly those nodes, whatever their distance
    body, _, _ = convert_str(low.format("*NSET, NSET=TN\n5, 7\n*TIE, NAME=GLUE, TIED NSET=TN, "
                                        "TYPE=NODE TO SURFACE\nTOP, TOOL\n"))
    assert {5, 7} <= _body_members(body) and not {6, 8} & _body_members(body)
    # a slave shell keeps its half thickness to the master (just touching), unless NO THICKNESS
    shell = ("*NODE\n1,0.,0.,0.85\n2,1.,0.,0.85\n3,1.,1.,0.85\n4,0.,1.,0.85\n"
             "*ELEMENT, TYPE=S4, ELSET=SH\n1, 1, 2, 3, 4\n*SURFACE, NAME=TOP\nSH, SPOS\n"
             "*SHELL SECTION, ELSET=SH, MATERIAL=M\n0.2\n*MATERIAL, NAME=M\n*ELASTIC\n100., 0.3\n"
             "*NODE\n11, 0.,0.,1.\n12, 1.,0.,1.\n13, 1.,1.,1.\n14, 0.,1.,1.\n9, 0.5,0.5,2.\n"
             "*ELEMENT, TYPE=R3D4, ELSET=PLATE\n2, 11, 14, 13, 12\n*SURFACE, NAME=TOOL\nPLATE, SPOS\n"
             "*RIGID BODY, REF NODE=9, ELSET=PLATE\n*TIE, NAME=GLUE{}\nTOP, TOOL\n"
             "*STEP\n*STATIC\n*BOUNDARY\n9, 1, 6\n*END STEP\n")
    body, conv, _ = convert_str(shell.format(""))
    assert {1, 2, 3, 4} <= _body_members(body)
    assert all(abs(conv.geom.nodes[n][2] - 0.9) < 1e-12 for n in (1, 2, 3, 4))
    body, conv, _ = convert_str(shell.format(", NO THICKNESS"))      # 0.15 > 0.1 sqrt 2
    assert not {1, 2, 3, 4} & _body_members(body)
    body, conv, _ = convert_str(shell.format(", NO THICKNESS, POSITION TOLERANCE=0.2"))
    assert {1, 2, 3, 4} <= _body_members(body)
    assert all(abs(conv.geom.nodes[n][2] - 1.0) < 1e-12 for n in (1, 2, 3, 4))
    # a SYMMETRIC layup lists the bottom half of its plies: 0.05 / 0.05 mirrored is the 0.2 shell
    # above (counted as 0.1, its nodes were moved to 0.95, into the master)
    sym = shell.replace("*SHELL SECTION, ELSET=SH, MATERIAL=M\n0.2\n", "*SHELL SECTION, ELSET=SH, "
                        "COMPOSITE, SYMMETRIC\n0.05, 3, M, 0.\n0.05, 3, M, 90.\n")
    body, conv, _ = convert_str(sym.format(""))
    assert {1, 2, 3, 4} <= _body_members(body)
    assert all(abs(conv.geom.nodes[n][2] - 0.9) < 1e-12 for n in (1, 2, 3, 4))


def test_unconverted_analytical_surface_comments_only_its_lines():
    deck = (ANALYTIC_2D + "*NODE\n11, 1.5, 1.\n12, 0., 1.\n8, 0., 5.\n"
            "*ELEMENT, TYPE=RAX2, ELSET=R\n5, 11, 12\n*SURFACE, NAME=FLAT\nR, SPOS\n"
            "*RIGID BODY, REF NODE=8, ELSET=R\n"
            "*SURFACE, TYPE=SEGMENTS, NAME=TOOL\nSTART, 1.5, 2.5\nCIRCL, 0., 1., 0., 2.5\n"
            "*RIGID BODY, REF NODE=9, ANALYTICAL SURFACE=TOOL\n*SURFACE INTERACTION, NAME=I\n"
            "*SURFACE BEHAVIOR, PRESSURE-OVERCLOSURE=HARD\n*CONTACT PAIR, INTERACTION=I\n"
            "TOP, TOOL\nTOP, FLAT\n")
    body, _, rep = convert_str(deck)
    assert "\nTOP, FLAT\n" in body and "\n** TOP, TOOL\n" in body and "\nTOP, TOOL\n" not in body
    assert "other lines are kept" in rep.text()


def test_explicit_plane_contact_with_a_rigid_surface_caps_the_increment():
    # ccx leaves contact between a plane model's expanded nodes and a rigid surface out of
    # its stable increment; the cap is ccx's contact formula: 0.8 critom / 2 sqrt(m / (K A))
    import validate_with_ccx as V
    def explicit(dim):
        d = V.rigid_punch_deck(dim, "elements", ctype="NODE TO SURFACE")
        return d.replace("*ELASTIC\n1000., 0.3", "*ELASTIC\n1000., 0.3\n*DENSITY\n1e-3").replace(
            "*STATIC\n1., 1.", "*DYNAMIC, EXPLICIT\n, 0.002")
    body, _, rep = convert_str(explicit("planar"))
    critom = 1.96 / math.sqrt(1.0 + 0.05 * (1.0 - 0.05 * 1.95))
    want = 0.8 * critom * 0.5 * math.sqrt(0.5 * 1e-3 * 0.0625 / (50 * 1000.0 * 0.25))
    line = body.split("*DYNAMIC, EXPLICIT")[1].splitlines()[1]
    assert abs(float(line.split(",")[3]) / want - 1) < 5e-3 and "rigid surface (4th data field" in rep.text()
    body, _, _ = convert_str(explicit("3d"))                       # ccx sizes 3-D contact itself
    assert body.split("*DYNAMIC, EXPLICIT")[1].splitlines()[1].strip() == ", 0.002"


def test_rigid_examples_match_the_validation_decks():
    import validate_with_ccx as V
    for name, text in (("rigid_punch_block", V.rigid_punch_deck("3d", "elements")),
                       ("rigid_punch_cylinder", V.rigid_punch_deck("3d", "analytic")),
                       ("rigid_body_inertia", V.rigid_inertia_deck())):
        path = os.path.join(EXAMPLES, name + ".inp")
        with open(path, encoding="utf-8") as fh:
            assert fh.read() == text, f"examples/{name}.inp differs from validate_with_ccx.py's deck"
        body, _, _ = convert(path)
        g = reparse(body)
        assert all(n in g.nodes for _, conn in g.elements.values() for n in conn)
        assert all(i in g.nodes for ids in g.nsets.values() for i in ids)
        assert all(i in g.elements for ids in g.elsets.values() for i in ids)


def _blocks_of(text):
    fd, path = tempfile.mkstemp(suffix=".inp")
    os.close(fd)
    try:
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        return A.read_blocks(path, A.Report())
    finally:
        os.unlink(path)


def _touch(*parts):
    os.makedirs(os.path.join(*parts[:-1]), exist_ok=True)
    open(os.path.join(*parts), "wb").close()
    os.chmod(os.path.join(*parts), 0o755)
    return os.path.join(*parts)


def test_find_ccx_in_windows_installs():
    # FreeCAD (Program Files or a per-user install, newest first), PrePoMax (unzipped, or
    # nested by Explorer's "Extract All"; the static build first) and bConverged (its ccx.bat)
    d = tempfile.mkdtemp()
    pf, pf86, local, home, drive = (os.path.join(d, n) for n in ("pf", "pf86", "local", "home", "c"))
    want = [_touch(pf, "FreeCAD 1.10", "bin", "ccx.exe"), _touch(pf, "FreeCAD 1.9", "bin", "ccx.exe"),
            _touch(pf, "FreeCAD 0.21", "bin", "ccx.exe"),
            _touch(local, "Programs", "FreeCAD 1.0", "bin", "ccx.exe"),
            _touch(drive, "PrePoMax v3.0.0", "Solver", "ccx_dynamic.exe"),
            _touch(home, "Downloads", "PrePoMax v2.4.0", "PrePoMax v2.4.0", "Solver", "ccx_static.exe"),
            _touch(home, "Downloads", "PrePoMax v2.4.0", "PrePoMax v2.4.0", "Solver", "ccx_dynamic.exe"),
            _touch(pf86, "bConverged", "CalculiX", "bin", "ccx.bat"),
            _touch(pf86, "bConverged", "CalculiX", "bin", "ccx.exe")]
    _touch(pf, "FreeCAD 1.1", "bin", "FreeCAD.exe")                  # no ccx in it
    saved = dict(os.environ)
    try:
        os.environ.update({"ProgramFiles": pf, "ProgramW6432": pf, "ProgramFiles(x86)": pf86,
                           "LOCALAPPDATA": local, "USERPROFILE": home, "SystemDrive": drive})
        got = A._windows_ccx_candidates()
        if os.name == "nt":                     # the whole search, with nothing on PATH
            os.environ["PATH"] = ""
            os.environ.pop("CCX", None)
            assert A.find_ccx() == (want[0], {}), A.find_ccx()
    finally:
        os.environ.clear()
        os.environ.update(saved)
        shutil.rmtree(d, ignore_errors=True)
    assert got == want, got


def test_find_ccx_override_is_absolute():
    # --run starts ccx in the output folder, so a relative --ccx / $CCX must not stay relative
    d, cwd = tempfile.mkdtemp(), os.getcwd()
    try:
        exe = _touch(d, "myccx.exe")
        os.chdir(d)
        (found, env), missing = A.find_ccx("myccx.exe"), A.find_ccx("nonexistent.exe")
        ok = bool(found) and os.path.isabs(found) and os.path.samefile(found, exe) and not env
    finally:
        os.chdir(cwd)
        shutil.rmtree(d, ignore_errors=True)
    assert ok and missing == (None, {}), (found, missing)


def test_find_ccx_in_a_conda_environment():
    # conda-forge's Windows ccx is <env>\Library\bin\ccx.exe and loads ARPACK from
    # <env>\Library\mingw-w64\bin: unless the environment is active, it runs with the folders
    # that `conda activate` puts on PATH (those that exist, in conda's order)
    d = tempfile.mkdtemp()
    try:
        env = os.path.join(d, "envs", "ccx")
        exe = _touch(env, "Library", "bin", "ccx.exe")
        _touch(env, "Library", "mingw-w64", "bin", "libarpack.dll")
        os.makedirs(os.path.join(env, "conda-meta"))
        dirs = A._conda_dll_dirs(exe)
        found, extra = A.find_ccx(exe)
        outside = [A._conda_dll_dirs(_touch(d, "Library", "bin", "ccx.exe")),     # no conda-meta
                   A._conda_dll_dirs(_touch(env, "Library", "ccx.exe"))]          # not Library\bin
    finally:
        shutil.rmtree(d, ignore_errors=True)
    assert dirs == [env, os.path.join(env, "Library", "mingw-w64", "bin"),
                    os.path.join(env, "Library", "bin")], dirs
    assert outside == [[], []], outside
    want = {"PATH": os.pathsep.join(dirs + [os.environ.get("PATH", "")])} if os.name == "nt" else {}
    assert found == exe and extra == want, (found, extra)


def test_run_explains_windows_exit_codes():
    # a ccx that Windows could not start exits with an NTSTATUS, which --run spells out
    assert A._exit_code_text(0xC0000135) == "exit code 0xC0000135 (a DLL that ccx needs is missing)"
    assert A._exit_code_text(-1073741571) == "exit code 0xC00000FD (stack overflow)"
    assert A._exit_code_text(201) == "exit code 201" and A._exit_code_text(-11) == "exit code -11"


def test_cli_output_on_a_cp1252_console():
    # a Latin-1 byte reads as U+FFFD, which the report echoes: on a strict cp1252 stream (a
    # Windows console or redirect) the CLI writes it as an escape instead of raising
    # UnicodeEncodeError, on stdout as on stderr
    d = tempfile.mkdtemp()
    deck = os.path.join(d, "latin1.inp")
    with open(deck, "wb") as fh:
        fh.write(b"caf\xe9\n*NODE\n1, 0., 0., 0.\n")
    out, err = (io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict", newline="\n")
                for _ in range(2))
    saved = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = out, err
    try:
        code = A.main([deck, "--check"])
        print("ccx 2.23 \u2192 \u03bd", file=sys.stdout)
        out.flush()
        err.flush()
    finally:
        sys.stdout, sys.stderr = saved
        shutil.rmtree(d, ignore_errors=True)
    assert code == 0
    assert b"before any keyword ignored: 'caf\\ufffd'" in err.buffer.getvalue(), err.buffer.getvalue()
    assert out.buffer.getvalue() == b"ccx 2.23 \\u2192 \\u03bd\n", out.buffer.getvalue()


def test_run_reads_ccx_output_in_any_encoding():
    # ccx echoes deck lines in UTF-8, whatever the console's code page; bytes that decode in
    # neither (0x81 is no cp1252 character, a lone 0xE9 no UTF-8) must not stop --run.  The
    # stand-in ccx is a script, as bConverged's ccx.bat is on Windows, in a folder named like
    # Program Files (x86): spaces and parentheses, which cmd.exe parses unless quoted.
    if os.name == "nt" and not (sys.executable + tempfile.gettempdir()).isascii():
        return                                  # cmd.exe would read the .bat in the OEM code page
    d = tempfile.mkdtemp()
    try:
        bindir = os.path.join(d, "Program Files (x86)")
        os.mkdir(bindir)
        fake = os.path.join(bindir, "fake_ccx.py")
        with open(fake, "w", encoding="utf-8") as fh:
            fh.write("import sys\nsys.stdout.buffer.write(b' STEP 1\\n caf\\xe9 \\xc5\\x81\\n"
                     " Job finished\\n')\n")
        if os.name == "nt":
            ccx = os.path.join(bindir, "ccx.bat")
            with open(ccx, "w", encoding="ascii") as fh:
                fh.write(f'@"{sys.executable}" "{fake}" %*\n')
        else:
            ccx = os.path.join(bindir, "ccx")
            with open(ccx, "w", encoding="utf-8") as fh:
                fh.write(f'#!/bin/sh\nexec "{sys.executable}" "{fake}" "$@"\n')
            os.chmod(ccx, 0o755)
        deck = os.path.join(d, "hex.inp")
        with open(deck, "w", encoding="utf-8") as fh:
            fh.write(HEX + "*STEP\n*STATIC\n*END STEP\n")
        code = A.main([deck, "--run", "--ccx", ccx, "--quiet"])
    finally:
        shutil.rmtree(d, ignore_errors=True)
    assert code == 0


def test_cli_second_deck_is_the_output_when_new_or_written_by_abq2ccx():
    # "abq2ccx deck.inp out.inp" converts into out.inp where out.inp is new or abq2ccx wrote
    # it (so a rerun overwrites it); two existing Abaqus decks still convert as a batch, and
    # --outdir keeps the batch reading
    from contextlib import redirect_stderr
    d = tempfile.mkdtemp()
    a, b, out = (os.path.join(d, n) for n in ("a.inp", "b.inp", "out.inp"))
    for path in (a, b):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(HEX)
    try:
        codes = [A.main([a, out, "--quiet"]), A.main([a, out, "--quiet"])]   # new, then rerun
        first = sorted(os.listdir(d))
        codes.append(A.main([a, b, "--quiet"]))                              # a batch
        with open(b, encoding="utf-8") as fh:
            b_kept = fh.read() == HEX
        with redirect_stderr(io.StringIO()) as err:
            codes.append(A.main([a, os.path.join(d, "new.inp"), "--outdir", d, "--quiet"]))
        last = sorted(os.listdir(d))
    finally:
        shutil.rmtree(d, ignore_errors=True)
    assert codes == [0, 0, 0, 1] and "cannot read" in err.getvalue(), codes
    assert first == ["a.inp", "b.inp", "out.inp", "out.log"], first
    assert b_kept and last == ["a.inp", "a_ccx.inp", "a_ccx.log", "b.inp", "b_ccx.inp",
                               "b_ccx.log", "out.inp", "out.log"], last


UMAT_CUBE = HEX + """*MATERIAL, NAME={name}
*USER MATERIAL, CONSTANTS=2
210000., 0.3
*DEPVAR
3
*SOLID SECTION, ELSET=EALL, MATERIAL={name}
*BOUNDARY
1, 1, 3
*STEP{step}
*STATIC
*CLOAD
7, 3, 1.
*END STEP
"""


def test_user_material_names_never_pick_another_ccx_routine():
    # ccx hands a *USER MATERIAL to the routine its name starts with (upper-cased): to its
    # Abaqus-UMAT interface, empty stubs or its own laws.  Such a material is renamed, so ccx
    # stops with 'no user material subroutine' instead of running another material.
    for prefix in A.UMAT_NAME_PREFIXES:
        name = prefix.lower() + "Mat" if prefix != "@" else "@Mat"
        body, conv, rep = convert_str(UMAT_CUBE.format(name=name, step=""))
        assert f"*MATERIAL, NAME=ABQ2CCX_{name}\n" in body, prefix
        assert f"MATERIAL=ABQ2CCX_{name}\n" in body, prefix
        assert f"material renamed ABQ2CCX_{name}" in rep.text(), prefix
        assert "*USER MATERIAL, CONSTANTS=2\n210000., 0.3\n" in body
        assert "*USER MATERIAL (the Abaqus subroutine does not run in ccx)" in conv.reduced_physics
    # other names stop ccx as they are: ccx keeps the quotes of a quoted name
    for name in ("Steel", '"user mat"'):
        body, _, rep = convert_str(UMAT_CUBE.format(name=name, step=""))
        assert f"*MATERIAL, NAME={name}\n" in body and "renamed" not in rep.text()
    # only a user material is dispatched by its name; the new name is unique
    deck = UMAT_CUBE.format(name="UserMat", step="") + ("*MATERIAL, NAME=ABQ2CCX_UserMat\n"
                                                        "*ELASTIC\n1., 0.3\n*MATERIAL, NAME=Abaqus_Steel\n"
                                                        "*ELASTIC\n1., 0.3\n")
    body, _, rep = convert_str(deck)
    assert "*MATERIAL, NAME=ABQ2CCX_UserMat_2\n" in body and "MATERIAL=ABQ2CCX_UserMat_2\n" in body
    assert "*MATERIAL, NAME=ABQ2CCX_UserMat\n" in body and "*MATERIAL, NAME=Abaqus_Steel\n" in body
    # composite plies name the material too
    deck = S4.replace("*Shell Section,elset=E,material=M\n0.1\n",
                      "*Shell Section, elset=E, composite\n0.1, 3, UserPly, 0.\n0.1, 3, M, 90.\n"
                      "*Material, name=UserPly\n*User Material, constants=1\n7.\n")
    body, _, _ = convert_str(deck)
    assert "\n0.1, , ABQ2CCX_UserPly, ABQ2CCX_OR0\n" in body and "*MATERIAL, NAME=ABQ2CCX_UserPly\n" in body
    assert not dangling_refs(reparse(body))


def test_abaqus_umat_writes_user_materials_for_the_abaqus_interface():
    body, conv, rep = convert_str(UMAT_CUBE.format(name="UserMat", step=""), abaqus_umat=True)
    assert "*MATERIAL, NAME=ABAQUSUserMat\n" in body and "MATERIAL=ABAQUSUserMat\n" in body
    assert "*USER MATERIAL, CONSTANTS=2\n210000., 0.3\n*DEPVAR\n3," in body
    assert "umat_abaqus.f: small strain" in rep.text() and "linear-elastic example" in rep.text()
    for arg in ("STRAN, DSTRAN, STRESS, DROT", "CELENT", "LAYER, KSPT", "PREDEF, DPRED",
                "SSE, SPD, SCD", "RPL, DDSDDT, DRPLDE, DRPLDT", "TEMP, DTEMP", "NDI, NSHR, NTENS",
                "DDSDDE", "PNEWDT", "KSTEP", "CMNAME"):
        assert f"Abaqus-UMAT interface, {arg}" in rep.text(), arg
    assert "NSTATV" not in rep.text() and "U0" not in rep.text()
    assert conv.reduced_physics == ["*USER MATERIAL (only a ccx rebuilt with the deck's UMAT runs it)"]
    # NLGEOM: the logarithmic-strain interface, whose start-of-increment stress 2.23 gets wrong
    body, _, rep = convert_str(UMAT_CUBE.format(name="Mat", step=", NLGEOM"), abaqus_umat=True)
    assert "*MATERIAL, NAME=ABAQUSNLMat\n" in body and "never computes U0" in rep.text()
    # ccx reads the name without blanks and would keep quotes; at most 80 characters
    body, _, rep = convert_str(UMAT_CUBE.format(name='"my mat"', step=""), abaqus_umat=True)
    assert "*MATERIAL, NAME=ABAQUSmymat\n" in body and "MATERIAL=ABAQUSmymat\n" in body
    body, _, rep = convert_str(UMAT_CUBE.format(name="M" * 76, step=""), abaqus_umat=True)
    assert f"*MATERIAL, NAME=ABAQUS{'M' * 74}\n" in body and "so the UMAT sees CMNAME" in rep.text()
    # Abaqus/Explicit: a VUMAT, which ccx cannot call: guarded as without the option
    deck = UMAT_CUBE.format(name="UserMat", step="").replace(
        "*STATIC", "*DYNAMIC, EXPLICIT\n, 1e-4").replace("*DEPVAR", "*DENSITY\n7.8e-9\n*DEPVAR")
    body, conv, rep = convert_str(deck, abaqus_umat=True)
    assert "*MATERIAL, NAME=ABQ2CCX_UserMat\n" in body and "ABAQUS" not in body
    assert "no VUMAT interface" in rep.text() and "Abaqus-UMAT interface," not in rep.text()


def test_user_material_card_as_ccx_reads_it():
    # ccx reads a temperature after the last constant: for 8 constants a line of its own;
    # it knows CONSTANTS and TYPE=THERMAL only
    card = ("*USER MATERIAL, CONSTANTS={n}, UNSYMM, TYPE=MECHANICAL\n{data}"
            "*USER MATERIAL, TYPE=THERMAL, CONSTANTS=1\n50.\n")
    for n, data, extra in ((8, "1.,2.,3.,4.,5.,6.,7.,8.\n", True), (2, "1.,2.\n", False),
                           (16, "1.,2.,3.,4.,5.,6.,7.,8.\n9.,10.,11.,12.,13.,14.,15.,16.\n", True),
                           (10, "1.,2.,3.,4.,5.,6.,7.,8.\n9.,10.\n", False)):
        deck = UMAT_CUBE.format(name="Plain", step="").replace(
            "*USER MATERIAL, CONSTANTS=2\n210000., 0.3\n", card.format(n=n, data=data))
        body, conv, rep = convert_str(deck)
        assert f"*USER MATERIAL, CONSTANTS={n}\n{data}{'0.' + chr(10) if extra else ''}*USER" in body, n
        assert ("on a line of its own" in rep.text()) == extra
        assert "*USER MATERIAL, TYPE=THERMAL, CONSTANTS=1\n50.\n" in body
        assert "UNSYMM dropped" in rep.text() and "TYPE=MECHANICAL" not in body
        assert "umatht" in rep.text() and len(conv.reduced_physics) == 2
    # a material no section uses changes nothing
    body, conv, _ = convert_str(UMAT_CUBE.format(name="Plain", step="").replace(
        "MATERIAL=Plain", "MATERIAL=Other") + "*MATERIAL, NAME=Other\n*ELASTIC\n1., 0.3\n")
    assert "*USER MATERIAL, CONSTANTS=2" in body and not conv.reduced_physics


# --- --run: the results digest and the instance map -----------------------------------------
# tests/fixtures/digest/job.{inp,frd,dat}: ccx's formats, cut down.  The Abaqus model is nodes
# 1-12 and elements 1-2 (element 2 a shell that ccx writes expanded, as nodes 21-24); node 13
# and element 3 (a knot beam, expanded as nodes 31-32) are the converter's.  Step 1 (*STATIC,
# two increments), 2 (*FREQUENCY), 3 (*BUCKLE), 4 (*STATIC after *BOUNDARY, OP=NEW).
DIGEST_JOB = os.path.join(ROOT, "tests", "fixtures", "digest", "job")


def test_frd_and_dat_readers_on_a_fixture():
    frd = DIGEST_JOB + ".frd"
    index = A.frd_index(frd)
    assert [(s, t, n) for s, t, n, _ in index] == [
        (0, None, "NODES"), (0, None, "ELEMENTS"), (1, 0.5, "DISP"), (1, 1.0, "DISP"),
        (1, 1.0, "STRESS"), (1, 1.0, "FORC"), (2, 12.5, "DISP"), (2, 30.25, "DISP"),
        (4, 2.0, "DISP"), (4, 2.0, "FORC"), (4, 2.0, "SDV")]
    rows = dict(A.frd_rows(frd, index[3][3]))
    assert rows[23] == [0.012, 0.012, 0.1] and rows[13] == [0.0, 0.0, 5.0] and len(rows) == 17
    assert dict(A.frd_rows(frd, index[0][3]))[24] == [0.0, 1.0, 1.05]          # coordinates
    assert dict(A.frd_rows(frd, index[-1][3])) == {1: [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]}
    assert A._frd_element_nodes(frd, index[1][3], 2) == {31, 32}
    blocks = list(A.dat_blocks(DIGEST_JOB + ".dat"))
    assert [(s, t, n, time, len(r)) for s, t, n, time, r in blocks] == [
        (1, "displacements", "TOP", 0.5, 4), (1, "forces", "RP", 0.5, 1),
        (1, "total force", "CORNER", 0.5, 1), (1, "displacements", "TOP", 1.0, 4),
        (1, "forces", "RP", 1.0, 1), (1, "total force", "CORNER", 1.0, 1),
        (2, "E I G E N V A L U E   O U T P U T", "", None, 2),
        (2, "P A R T I C I P A T I O N   F A C T O R S", "", None, 2),
        (3, "B U C K L I N G   F A C T O R   O U T P U T", "", None, 2), (4, "stresses", "EALL", 2.0, 3)]
    assert blocks[3][4][0] == [5, 0.0, 1e-101, 0.1]      # Fortran's 1.000000-101 (no E)
    assert blocks[6][4][1] == [2, 0.3612546e5, 0.1900664e3, 30.25, 0.0]
    assert list(A.dat_blocks(DIGEST_JOB + ".missing")) == [] and A.frd_index(DIGEST_JOB + ".missing") == []


def test_results_digest_supports_from_the_deck():
    deck = A._deck_steps(DIGEST_JOB + ".inp")
    assert deck["max_node"] == 13 and deck["transformed"] == {11, 12}
    assert deck["members"]("ALLBC") == [1, 2, 3, 4, 5, 6, 7, 8]          # nested names, GENERATE
    one, two, _, four = deck["steps"]
    assert [s["procedure"] for s in deck["steps"]] == ["STATIC", "FREQUENCY", "BUCKLE", "STATIC"]
    # model-level BOT and the step's TOP / RP / SIDE; not the ROT NODE 10 (rotations)
    assert list(one["targets"]) == ["BOT", "TOP", "RP", "SIDE"] and 10 not in one["held"]
    assert one["held"][5] == {3} and one["held"][9] == {1, 2, 3} and one["targets"]["SIDE"] == {11: {1}, 12: {1}}
    assert two["held"] == one["held"]                    # carried over
    assert list(four["targets"]) == ["BOT"] and set(four["held"]) == {1, 2, 3, 4}   # OP=NEW


def test_results_digest_on_a_fixture():
    inst = [{"name": "I1", "part": "P", "node_offset": 0, "element_offset": 0, "nodes": [1, 12],
             "elements": [1, 2], "names": {"BOTTOM": "BOT"}}]
    d = A.ccx_results_digest(DIGEST_JOB, inst, (12, 2))
    assert [e["step"] for e in d] == [1, 2, 3, 4]
    s1 = d[0]
    assert s1["procedure"] == "STATIC" and s1["time"] == 1.0
    # the last increment's |U|, not t = 0.5's node 6; converter node 13 and the knot's 31-32
    # left out; ccx's node 23, expanded from the shell, sits next to node 7
    u = dict(s1["max_u"])
    assert abs(u.pop("value") - math.sqrt(2 * 0.012 ** 2 + 0.1 ** 2)) < 1e-15
    assert u == {"node": 23, "near": 7, "abaqus": "I1.7"}
    assert s1["max_mises"] == {"value": 100.0, "node": 3, "abaqus": "I1.3"}
    # RF over the DOFs each BC holds: TOP only in z (its x RF 0.4 is no reaction); RP from the
    # .dat (no element: not in the .frd); CORNER's TOTALS=ONLY print; SIDE (local axes) left out
    assert s1["rf"] == [{"set": "RP", "rf": [0.0, 0.0, -24.0]},
                        {"set": "BOT", "rf": [0.0, 0.0, -12.0], "abaqus": "I1.BOTTOM"},
                        {"set": "TOP", "rf": [0.0, 0.0, 12.0]},
                        {"set": "CORNER", "rf": [-0.5, -1.5, -3.0]}]
    assert d[1] == {"step": 2, "procedure": "FREQUENCY", "frequencies": [12.5, 30.25]}
    assert d[2] == {"step": 3, "procedure": "BUCKLE", "buckling_factors": [3.5, 7.25]}
    assert d[3]["max_mises"] == {"value": 40.0, "element": 1, "set": "EALL", "abaqus": "I1.1"}
    assert d[3]["rf"] == [{"set": "BOT", "rf": [0.0, 0.0, -4.0], "abaqus": "I1.BOTTOM"}]
    assert A.format_results_digest(d) == [
        "  step 1 *STATIC, time 1: max |U| 0.1014 near node 7 [I1.7]; max Mises 100 at node 3 [I1.3]",
        "    sum of RF: RP (0, 0, -24); BOT [I1.BOTTOM] (0, 0, -12); TOP (0, 0, 12); +1 more",
        "  step 2 *FREQUENCY: 2 frequencies (cycles/time) 12.5, 30.25",
        "  step 3 *BUCKLE: 2 buckling factors 3.5, 7.25",
        "  step 4 *STATIC, time 2: max |U| 0.5 at node 7 [I1.7]; max Mises 40 in element 1 [I1.1] "
        "(set EALL)",
        "    sum of RF: BOT [I1.BOTTOM] (0, 0, -4)"]
    # without the model's labels nothing is left out
    d = A.ccx_results_digest(DIGEST_JOB)
    assert d[0]["max_u"] == {"value": 5.0, "node": 13}
    assert d[0]["max_mises"] == {"value": 2000.0, "node": 31, "near": 7}
    assert d[3]["max_mises"]["element"] == 3


def test_results_digest_skips_the_rows_b32r_prints_past_its_points():
    # ccx 2.23 prints 50 *EL PRINT rows per B32R element under a RECT or CIRC section, of
    # which the first 8 are its integration points; under PIPE all 16 rows are
    inp = ("*NODE, NSET=NALL\n" + "".join(f"{n}, {n}., 0., 0.\n" for n in range(1, 30)) +
           "*ELEMENT, TYPE=C3D20, ELSET=SOLID\n9, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, "
           "21, 22, 23\n1, 24, 25, 26, 27\n"            # a continuation line: no element 1 there
           "*ELEMENT, TYPE=B32R\n1, 1, 2, 3\n2, 3, 4, 5\n3, 5, 6, 7\n"
           "*ELSET, ELSET=EB, GENERATE\n1, 2, 1\n*ELSET, ELSET=ROD\nEB\n*ELSET, ELSET=TUBE\n3\n"
           "*BEAM SECTION, ELSET=ROD, MATERIAL=M, SECTION=RECT\n0.1, 0.2\n0., 0., 1.\n"
           "*BEAM SECTION, ELSET=TUBE, MATERIAL=M, SECTION=PIPE\n0.1, 0.01\n0., 0., 1.\n"
           "*STEP\n*STATIC\n*EL PRINT, ELSET=EALL\nS\n*END STEP\n")
    rows = "".join(f"{e:10d}{k:4d}  {v:.6E}  0.000000E+00  0.000000E+00  0.000000E+00  0.000000E+00  "
                   f"0.000000E+00\n" for e, k, v in ((1, 8, 5.0), (1, 9, 50.0), (2, 1, 4.0), (2, 50, 70.0),
                                                     (3, 16, 6.0), (9, 27, 1.0)))
    d = tempfile.mkdtemp()
    try:
        job = os.path.join(d, "job")
        open(job + ".inp", "w", encoding="utf-8", newline="\n").write(inp)
        open(job + ".dat", "w", encoding="utf-8", newline="\n").write(
            "\n S T E P       1\n\n INCREMENT     1\n\n stresses (elem, "
            "integ.pnt.,sxx,syy,szz,sxy,sxz,syz) for set EALL and time  0.1000000E+01\n\n" + rows)
        assert A._deck_steps(job + ".inp")["rows"] == {1: 8, 2: 8}
        assert A.ccx_results_digest(job)[0]["max_mises"] == {"value": 6.0, "element": 3, "set": "EALL"}
    finally:
        shutil.rmtree(d)


def test_b32r_notes_on_its_print_rows_and_3d_nlgeom():
    beam = ("*Node\n1, 0., 0., 0.\n2, 1., 0., 0.\n3, 2., 0., 0.\n*Element, type={typ}, elset=B\n"
            "1, 1, 2, 3\n*Beam Section, elset=B, material=M, section={sec}\n0., 0., -1.\n"
            "*Material, name=M\n*Elastic\n2.1e5, 0.3\n*Step{nl}\n*Static\n*Boundary\n1, 1, 6\n"
            "*Cload\n3, 2, -1.\n*El Print, elset=B\nS\n*End Step\n")
    _, conv, rep = convert_str(beam.format(typ="B32", sec="RECT\n0.1, 0.2", nl=", nlgeom"))
    assert conv._b32r_rows == {1} and "prints 50 rows per such element" in rep.text()
    assert "ccx 2.23 can stop converging on members of 2-4 elements" in rep.text()
    _, conv, rep = convert_str(beam.format(typ="B32", sec="PIPE\n0.1, 0.01", nl=""))
    assert not conv._b32r_rows and "50 rows" not in rep.text() and "stop converging" not in rep.text()
    _, _, rep = convert_str(beam.format(typ="B32", sec="RECT\n0.1, 0.2", nl="")   # prints nothing
                            .replace("*El Print, elset=B\nS\n", "*El Print, elset=B, frequency=0\nS\n"))
    assert "50 rows" not in rep.text()
    # a 2-D model holds DOF 3, which keeps B32R converging under NLGEOM
    _, _, rep = convert_str(beam.format(typ="B22", sec="RECT\n0.1, 0.2", nl=", nlgeom")
                            .replace(", 0.\n2, 1., 0., 0.\n3, 2., 0., 0.", "\n2, 1., 0.\n3, 2., 0."))
    assert "50 rows" in rep.text() and "stop converging" not in rep.text()


def test_instance_map_of_two_blocks():
    path = os.path.join(EXAMPLES, "assembly_two_blocks.inp")
    body, conv, rep = convert(path)
    assert rep.instances == [
        {"name": "I1", "part": "BLOCK", "node_offset": 0, "element_offset": 0, "nodes": [1, 8],
         "elements": [1, 1], "names": {"BOT": "I1_BOT", "TOPF": "I1_TOPF", "ALL": "I1_ALL"}},
        {"name": "I2", "part": "BLOCK", "node_offset": 8, "element_offset": 1, "nodes": [9, 16],
         "elements": [2, 2], "names": {"BOT": "I2_BOT", "TOPF": "I2_TOPF", "ALL": "I2_ALL"}}]
    assert conv.model_labels == (16, 2)
    g = reparse(body)
    part = {1: (0, 0, 0), 2: (1, 0, 0), 3: (1, 1, 0), 4: (0, 1, 0), 5: (0, 0, 1), 6: (1, 0, 1),
            7: (1, 1, 1), 8: (0, 1, 1)}
    for inst, shift in zip(rep.instances, (0.0, 2.0)):       # I2 is translated by x = 2
        for n, (x, y, z) in part.items():                    # ccx label = Abaqus label + offset
            assert g.nodes[n + inst["node_offset"]] == (x + shift, y, z)
        assert sorted(g.nsets[inst["names"]["BOT"]]) == [n + inst["node_offset"] for n in (1, 2, 3, 4)]
        assert g.elsets[inst["names"]["ALL"]] == [1 + inst["element_offset"]]
    assert A.instance_label(rep.instances, 15) == "I2.7" and A.instance_label(rep.instances, 3) == "I1.3"
    assert A.instance_label(rep.instances, 2, "element") == "I2.1"
    assert A.instance_label(rep.instances, 17) is None
    log = rep.text().splitlines()
    assert log[-3:] == [
        "Instances (ccx label = Abaqus label + offset; Abaqus Instance.name -> ccx name):",
        "  I1 (part BLOCK): nodes 1-8 (+0), elements 1-1 (+0); BOT -> I1_BOT, TOPF -> I1_TOPF, ALL -> I1_ALL",
        "  I2 (part BLOCK): nodes 9-16 (+8), elements 2-2 (+1); BOT -> I2_BOT, TOPF -> I2_TOPF, ALL -> I2_ALL"]
    head = rep.header_comment_lines()
    assert "**   I2 (part BLOCK): nodes 9-16 (+8), elements 2-2 (+1); BOT -> I2_BOT," in head
    assert "**     TOPF -> I2_TOPF, ALL -> I2_ALL" in head       # wrapped between pairs


def test_instance_map_of_rotated_instances():
    body, conv, rep = convert(os.path.join(EXAMPLES, "assembly_rotated_instances.inp"))
    i1, i2 = rep.instances
    assert (i1["nodes"], i1["elements"], i2["nodes"], i2["elements"]) == ([1, 20], [1, 4], [21, 40], [5, 8])
    assert (i2["node_offset"], i2["element_offset"]) == (20, 4)
    assert i2["names"] == {"ROOT": "I2_ROOT", "TIP": "I2_TIP", "ALL": "I2_ALL", "TOPF": "I2_TOPF"}
    # the part's sets keep their members, offset; the instance-qualified loads of the deck
    # (I1.TIP, I2.TIP, I2.5, I2.TOPF) name the same ccx entities
    g = reparse(body)
    for inst in (i1, i2):
        assert sorted(g.nsets[inst["names"]["ROOT"]]) == [n + inst["node_offset"] for n in (1, 6, 11, 16)]
        assert sorted(g.nsets[inst["names"]["TIP"]]) == [n + inst["node_offset"] for n in (5, 10, 15, 20)]
    assert "*CLOAD\nI1_TIP, 3, -0.25\nI2_TIP, 1, 0.5\n25, 2, -1.\n" in body      # I2.5: 5 + 20
    assert "*SURFACE, TYPE=ELEMENT, NAME=I2_TOPF\nI2_ALL, S2\n" in body


def test_instance_map_listing_is_capped():
    part = ("*PART, NAME=P\n*NODE\n1, 0., 0., 0.\n2, 1., 0., 0.\n*ELEMENT, TYPE=T3D2, ELSET=E\n1, 1, 2\n"
            + "".join(f"*NSET, NSET=S{k}\n1\n" for k in range(10)) + "*END PART\n*ASSEMBLY, NAME=A\n")
    insts = "".join(f"*INSTANCE, NAME=I{k}, PART=P\n{k}., 0., 0.\n*END INSTANCE\n" for k in range(25))
    _, _, rep = convert_str(part + insts + "*END ASSEMBLY\n")
    assert len(rep.instances) == 25 and rep.instances[24]["node_offset"] == 48
    lines = rep.instance_lines()
    assert len(lines) == 22 and lines[-1] == "  ... and 5 more instance(s) (--json lists them all)"
    assert lines[1].endswith("S7 -> I0_S7, +3 more")        # 10 sets and E: 8 names shown


def test_json_has_the_instances_and_the_run():
    import contextlib
    import json
    path = os.path.join(EXAMPLES, "assembly_two_blocks.inp")
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        assert A.main([path, "--check", "--json"]) == 0
    doc = json.loads(out.getvalue())
    assert [i["name"] for i in doc["instances"]] == ["I1", "I2"] and "run" not in doc
    # --run: what run_ccx returns lands under "run" and "results" (ccx itself: validate_with_ccx)
    seen = {}

    def fake_run(out_path, override, quiet, digest, instances, model, expanded=None):
        seen.update(digest=digest, instances=instances, model=model)
        return {"code": 0, "ccx": "ccx", "ccx_version": "2.23", "status": "solved",
                "results": [{"step": 1, "time": 1.0}]}
    real = A.run_ccx
    A.run_ccx = fake_run
    try:
        with tempfile.TemporaryDirectory() as d:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                assert A.main([path, "--outdir", d, "--run", "--json", "--quiet"]) == 0
    finally:
        A.run_ccx = real
    doc = json.loads(out.getvalue())
    assert doc["run"] == {"ccx": "ccx", "ccx_version": "2.23", "status": "solved"}
    assert doc["results"] == [{"step": 1, "time": 1.0}]
    assert seen == {"digest": False, "instances": doc["instances"], "model": (16, 2)}


def test_ccx_version_is_read_and_checked():
    import contextlib
    import subprocess

    class Done:
        def __init__(self, text):
            self.stdout, self.stderr, self.returncode = text, "", 201
    real = A.subprocess.run
    calls = []
    A.subprocess.run = lambda cmd, **kw: (calls.append(cmd), Done("\nThis is Version 2.21\n\n"))[1]
    try:
        assert A.ccx_version("/fake/ccx_221") == "2.21" and calls == [["/fake/ccx_221", "-v"]]
        assert A.ccx_version("/fake/ccx_221") == "2.21" and len(calls) == 1      # asked once
    finally:
        A.subprocess.run = real
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        A._warn_ccx_version("/fake/ccx_221", "2.21")
        A._warn_ccx_version("/fake/ccx_221", "2.21")             # once per executable
        A._warn_ccx_version("/fake/ccx_223", "2.23")
        A._warn_ccx_version("/fake/ccx_unknown", None)
    lines = err.getvalue().splitlines()
    assert len(lines) == 2 and "/fake/ccx_221 is ccx 2.21; abq2ccx targets ccx 2.22-2.23" in lines[0]
    assert "could not tell which ccx version /fake/ccx_unknown is" in lines[1]
    assert subprocess.run is real
# --- composite shells: S4R -> S8R and continuum shells -> one solid per ply ---------------

COMPOSITE_MAT = ("*Material, name=CFRP\n*Elastic, type=ENGINEERING CONSTANTS\n"
                 "140000., 10000., 10000., 0.3, 0.3, 0.4, 5000., 5000.,\n3500.\n")
S4R_STRIP = ("*Node\n1, 0., 0., 0.\n2, 1., 0., 0.\n3, 2., 0., 0.\n4, 0., 1., 0.\n5, 1., 1., 0.\n"
             "6, 2., 1., 0.\n*Element, type=S4R, elset=PLATE\n1, 1, 2, 5, 4\n2, 2, 3, 6, 5\n"
             "*Nset, nset=CLAMP\n1, 4\n*Nset, nset=TIP\n3, 6\n" + COMPOSITE_MAT)
SC8R_STRIP = ("*Node\n1, 0., 0., 0.\n2, 1., 0., 0.\n3, 2., 0., 0.\n4, 0., 1., 0.\n5, 1., 1., 0.\n"
              "6, 2., 1., 0.\n11, 0., 0., 0.3\n12, 1., 0., 0.3\n13, 2., 0., 0.3\n14, 0., 1., 0.3\n"
              "15, 1., 1., 0.3\n16, 2., 1., 0.3\n*Element, type=SC8R, elset=PLATE\n"
              "1, 1, 2, 5, 4, 11, 12, 15, 14\n2, 2, 3, 6, 5, 12, 13, 16, 15\n"
              "*Nset, nset=CLAMP\n1, 4, 11, 14\n*Nset, nset=TIP\n3, 6, 13, 16\n" + COMPOSITE_MAT)
LAYUP = "1., 3, CFRP, 0.\n1., 3, CFRP, 90.\n1., 3, CFRP, 0.\n"


def _card_at(body, head):
    """The data lines of the first card of ``body`` whose keyword line starts with ``head``."""
    lines = body.splitlines()
    i = next(k for k, ln in enumerate(lines) if ln.startswith(head))
    out = []
    for ln in lines[i + 1:]:
        if ln.startswith("*"):
            break
        out.append(ln)
    return out


def test_composite_s4r_becomes_s8r_with_shared_midside_nodes():
    # ccx 2.23 reads a composite section only on S8R / S6: the S4R strip becomes two S8R that
    # share the midside node of their common edge 2-5; ids, sets and the layup stay
    body, conv, rep = convert_str(S4R_STRIP + "*Shell Section, elset=PLATE, composite\n"
                                  "0.1, 3, CFRP, 0.\n0.1, 3, CFRP, 90.\n*Step\n*Static\n*Boundary\n"
                                  "CLAMP, ENCASTRE\n*Cload\nTIP, 3, -1.\n*Node print, nset=TIP\nU\n*End Step\n")
    assert conv.geom.elements[1] == ("S8R", [1, 2, 5, 4, 7, 8, 9, 10])
    assert conv.geom.elements[2] == ("S8R", [2, 3, 6, 5, 11, 12, 13, 8])
    assert conv.geom.nodes[8] == (1.0, 0.5, 0.0)                 # the shared edge 2-5
    assert "*ELEMENT, TYPE=S8R" in body and "*ELEMENT, TYPE=S4R" not in body
    # the BC set takes the midside node of its edge 1-4; the CLOAD set does not (it would add
    # load), and its *NODE PRINT keeps the deck's nodes
    assert conv.geom.nset("CLAMP") == [1, 4, 10] and conv.geom.nset("TIP") == [3, 6]
    assert "element S4R -> S8R" in "; ".join(conv.reduced_physics)
    assert "*ELSET, ELSET=PLATE\n1, 2" in body


def test_composite_s4r_bc_lines_reach_the_midside_nodes():
    # node-numbered BC values on both ends of an edge are interpolated onto its midside node
    body, _, _ = convert_str(S4R_STRIP + "*Shell Section, elset=PLATE, composite\n0.1, 3, CFRP, 0.\n"
                             "*Step\n*Static\n*Boundary\n1, 1, 1, 0.\n2, 1, 1, 0.2\n3, 3, 3, 1.\n"
                             "6, 3, 3, 3.\n*End Step\n")
    lines = _card_at(body, "*BOUNDARY")
    assert "7, 1, 1, 0.1" in lines and "12, 3, 3, 2" in lines


def test_composite_s4r_upgrades_its_linear_neighbours_and_edge_beams():
    # a plain S4R sharing an edge with the composite one and a B31 stiffener along an
    # upgraded edge are upgraded too: no midside node is left hanging
    deck = (S4R_STRIP.replace("*Element, type=S4R, elset=PLATE\n1, 1, 2, 5, 4\n2, 2, 3, 6, 5\n",
                              "*Element, type=S4R, elset=SKIN\n1, 1, 2, 5, 4\n*Element, type=S4R, "
                              "elset=METAL\n2, 2, 3, 6, 5\n*Element, type=B31, elset=STRINGER\n"
                              "3, 1, 2\n4, 2, 3\n")
            + "*Material, name=AL\n*Elastic\n70000., 0.3\n*Shell Section, elset=SKIN, composite\n"
            "0.1, 3, CFRP, 0.\n0.1, 3, CFRP, 90.\n*Shell Section, elset=METAL, material=AL\n0.2\n"
            "*Beam Section, elset=STRINGER, material=AL, section=RECT\n0.1, 0.2\n0., 0., 1.\n")
    body, conv, rep = convert_str(deck)
    g = conv.geom
    assert g.elements[1][0] == "S8R" and g.elements[2][0] == "S8R"
    assert g.elements[3] == ("B32R", [1, 7, 2]) and g.elements[4] == ("B32R", [2, 11, 3])
    assert g.elements[1][1][4] == 7 and g.elements[2][1][4] == 11       # shell and beam share them
    assert "1 other linear shell(s) joined to them by an edge" in rep.text()
    assert "2 2-node beam(s) along an upgraded edge" in rep.text()


def test_composite_plies_without_orientation_name_the_global_axes():
    # ccx 2.23 gives a ply line without an orientation the previous line's (probed: a [0/90/0]
    # plate runs as [0/90/90]); so when one ply has an orientation, all name one
    body, _, _ = convert_str(S4R_STRIP + "*Shell Section, elset=PLATE, composite\n0.1, 3, CFRP, 0.\n"
                             "0.1, 3, CFRP, 90.\n0.1, 3, CFRP, 0.\n")
    assert "*ORIENTATION, NAME=ABQ2CCX_OR0\n1., 0., 0., 0., 1., 0." in body
    assert _card_at(body, "*SHELL SECTION") == ["0.1, , CFRP, ABQ2CCX_OR0", "0.1, , CFRP, ABQ2CCX_OR1",
                                             "0.1, , CFRP, ABQ2CCX_OR0"]
    body, _, _ = convert_str(S4R_STRIP + "*Shell Section, elset=PLATE, composite\n0.1, 3, CFRP\n"
                             "0.1, 3, CFRP\n")
    assert _card_at(body, "*SHELL SECTION") == ["0.1, , CFRP", "0.1, , CFRP"]      # none: unchanged


def test_composite_shell_plies_off_their_axis_get_exact_directions():
    # Abaqus turns a layer about the shell normal after projecting the section axes; ccx turns
    # the orientation about its own axis 3.  On a plate in the x-z plane (normal -y) a 30 degree
    # ply about global z would project onto x: its directions are given element by element
    xz = S4R_STRIP.replace(", 1., 0.\n", ", 0., 1.\n")         # y -> z: the strip in the x-z plane
    body, _, rep = convert_str(xz + "*Shell Section, elset=PLATE, composite\n0.1, 3, CFRP, 30.\n"
                               "0.1, 3, CFRP, 0.\n")
    assert "as Abaqus defines them" in rep.text()
    c, s = math.cos(math.radians(30.0)), math.sin(math.radians(30.0))
    want = [c, 0.0, s]                                        # x turned by +30 about -y
    lines = body.splitlines()
    ori = lines[lines.index("*ORIENTATION, NAME=ABQ2CCX_PLY1") + 1]
    got = [float(x) for x in ori.split(",")]
    assert max(abs(x - y) for x, y in zip(got[:3], want)) < 1e-8, got
    assert _card_at(body, "*SHELL SECTION") == ["0.1, , CFRP, ABQ2CCX_PLY1", "0.1, , CFRP, ABQ2CCX_PLY2"]
    # the same strip in its own x-y plane keeps the usual orientations
    body, _, rep = convert_str(S4R_STRIP + "*Shell Section, elset=PLATE, composite\n0.1, 3, CFRP, 30.\n")
    assert "as Abaqus defines them" not in rep.text() and "3, 30." in body


def test_shell_material_axes_follow_abaqus_rules():
    nz = (0.0, 0.0, 1.0)
    assert A.shell_local_axes(nz) == ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0))
    # global X along the normal: the projection of Z
    d1, d2 = A.shell_local_axes((1.0, 0.0, 0.0))
    assert d1 == (0.0, 0.0, 1.0) and d2 == (0.0, -1.0, 0.0)
    # an orientation projects the axis that follows its rotation axis: about axis 1, axis 2;
    # without a rotation line Abaqus' default rotation axis is 1 (2017 "Orientations"), also
    # where it lies in the shell (warned), and where the next axis is the normal the default
    # directions are taken (warned)
    frame, k = A.orientation_frame((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), "RECTANGULAR", (0, 0, 0), (1, 0.0))
    assert k == 1 and A.shell_local_axes(nz, frame, k)[0] == (0.0, 1.0, 0.0)
    frame, k = A.orientation_frame((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), "RECTANGULAR", (0, 0, 0), None)
    assert k is None and A.shell_local_axes(nz, frame, k) == ((0.0, 1.0, 0.0), (-1.0, 0.0, 0.0))
    assert "lies in the shell" in A.shell_axes_caveat(nz, frame, k)
    assert A.shell_local_axes((0.0, 1.0, 0.0), frame, k)[0] == (1.0, 0.0, 0.0)
    assert "is the shell normal" in A.shell_axes_caveat((0.0, 1.0, 0.0), frame, k)
    assert A.shell_axes_caveat(nz, frame, 3) is None and A.shell_axes_caveat((1.0, 0.0, 0.0), frame, k) is None
    frame, k = A.orientation_frame((0.0, 0.0, 0.0), (0.0, 0.0, 1.0), "CYLINDRICAL", (0.0, 2.0, 5.0), None)
    assert A.shell_local_axes((0.0, 1.0, 0.0), frame, k)[0] == (-1.0, 0.0, 0.0)   # hoop direction
    frame, k = A.orientation_frame((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), "RECTANGULAR", (0, 0, 0), (3, 90.0))
    d1, _ = A.shell_local_axes(nz, frame, k)
    assert max(abs(x - y) for x, y in zip(d1, (0.0, 1.0, 0.0))) < 1e-12
    # cylindrical: axis 1 radial at the point, 2 tangential, 3 along the axis a -> b
    frame, _ = A.orientation_frame((0.0, 0.0, 0.0), (0.0, 0.0, 1.0), "CYLINDRICAL", (0.0, 2.0, 5.0), None)
    assert frame[0] == (0.0, 1.0, 0.0) and frame[2] == (0.0, 0.0, 1.0)
    # spherical: a the centre, b on the polar axis; 1 radial, 2 circumferential, 3 meridional
    frame, _ = A.orientation_frame((0.0, 0.0, 0.0), (0.0, 0.0, 1.0), "SPHERICAL", (0.0, 2.0, 0.0), None)
    assert frame == ((0.0, 1.0, 0.0), (-1.0, 0.0, 0.0), (0.0, 0.0, 1.0))
    # a layer angle turns about the normal: about -z a +90 ply points along -y
    d1, d2 = A.ply_axes((0.0, 0.0, -1.0), A.shell_local_axes((0.0, 0.0, -1.0)), 90.0)
    assert max(abs(x - y) for x, y in zip(d1, (0.0, -1.0, 0.0))) < 1e-12


def test_continuum_shell_stack_orders_are_right_handed():
    iso = {1: (-1, -1, -1), 2: (1, -1, -1), 3: (1, 1, -1), 4: (-1, 1, -1), 5: (-1, -1, 1),
           6: (1, -1, 1), 7: (1, 1, 1), 8: (-1, 1, 1)}
    for d, order in A.HEX_STACK_ORDER.items():
        jac = [[sum(iso[i + 1][c] * iso[p][r] / 8.0 for i, p in enumerate(order)) for c in range(3)]
               for r in range(3)]
        det = (jac[0][0] * (jac[1][1] * jac[2][2] - jac[1][2] * jac[2][1])
               - jac[0][1] * (jac[1][0] * jac[2][2] - jac[1][2] * jac[2][0])
               + jac[0][2] * (jac[1][0] * jac[2][1] - jac[1][1] * jac[2][0]))
        assert det > 0, d
        stack = [sum(iso[p][c] for p in order[4:]) - sum(iso[p][c] for p in order[:4]) for c in range(3)]
        assert stack[abs(d) - 1] * d > 0 and sum(1 for x in stack if x) == 1, (d, stack)
    assert A.stack_face_map(A.HEX_STACK_ORDER[3]) == {1: ("first", 1), 2: ("last", 2), 3: ("all", 3),
                                                       4: ("all", 4), 5: ("all", 5), 6: ("all", 6)}
    assert A.stack_face_map(A.HEX_STACK_ORDER[1])[6] == ("first", 1)          # xi = -1 at the bottom
    assert A.stack_face_map(A.HEX_STACK_ORDER[1])[4] == ("last", 2)


def test_continuum_shell_plies_split_with_shared_interface_nodes():
    deck = (SC8R_STRIP + "*Elset, elset=E2\n2\n*Surface, name=TOP\nPLATE, S2\n*Surface, name=BOT\n"
            "PLATE, S1\n*Surface, name=END\nE2, S4\n*Shell Section, elset=PLATE, composite\n" + LAYUP
            + "*Step\n*Static\n*Boundary\nCLAMP, ENCASTRE\n3, 1, 1, 0.\n13, 1, 1, 0.3\n*Dload\n2, P4, 1.\n"
            "2, BZ, -1.\n*Dsload\nTOP, P, 0.1\n*Node print, nset=TIP\nU\n*End Step\n")
    body, conv, rep = convert_str(deck)
    g = conv.geom
    # three plies a stack, ply 1 keeping the element id; the interface nodes of the shared
    # stack edges 2-12 and 5-15 serve both stacks
    assert g.elements[1] == ("C3D8I", [1, 2, 5, 4, 17, 18, 19, 20])
    assert g.elements[3] == ("C3D8I", [17, 18, 19, 20, 21, 22, 23, 24])
    assert g.elements[4] == ("C3D8I", [21, 22, 23, 24, 11, 12, 15, 14])
    assert g.elements[2][1][4:] == [18, 25, 26, 19]
    assert max(abs(x - y) for x, y in zip(g.nodes[18], (1.0, 0.0, 0.1))) < 1e-12 and \
        abs(g.nodes[22][2] - 0.2) < 1e-12
    assert g.elset("PLATE") == [1, 3, 4, 2, 5, 6] and g.elset("E2") == [2, 5, 6]
    # node sets of BCs and output take the interface nodes of the edges they hold
    assert g.nset("CLAMP") == [1, 4, 11, 14, 17, 21, 20, 24]
    assert g.nset("TIP") == [3, 6, 13, 16, 25, 27, 26, 28]
    # node-numbered BC values interpolate along the stack edge 3-13
    assert "25, 1, 1, 0.1" in body and "27, 1, 1, 0.2" in body
    # faces: the top on the last ply, the bottom on the first, a side face on every ply
    assert _card_at(body, "*SURFACE, NAME=TOP") == ["PLATE_S2_PLIES, S2"] and g.elset("PLATE_S2_PLIES") == [4, 6]
    assert g.elset("PLATE_S1_PLIES") == [1, 2] and g.elset("E2_S4_PLIES") == [2, 5, 6]
    assert "ABQ2CCX_E2_S4_PLIES, P4, 1." in body and "ABQ2CCX_PLIES_2, BZ, -1." in body
    assert g.elset("ABQ2CCX_PLIES_2") == [2, 5, 6]
    assert "PLATE_S2_PLIES, P2, 0.1" in body                     # *DSLOAD on the top face
    # one solid section per material and layer angle, with the ply axes; ENCASTRE on solids
    assert "*SOLID SECTION, ELSET=PLATE_PLY1, MATERIAL=CFRP, ORIENTATION=PLATE_PLY1_ORI" in body
    assert g.elset("PLATE_PLY1") == [1, 2, 4, 6] and g.elset("PLATE_PLY2") == [3, 5]
    assert "*ORIENTATION, NAME=PLATE_PLY2_ORI\n0, 1, 0, -1, 0, 0" in body
    assert "CLAMP, 1, 3" in body and "SHELL SECTION" not in body.split("*STEP")[0].split("** ===")[-1]
    assert any("one C3D8I / C3D6 solid per ply" in r for r in conv.reduced_physics)


def test_continuum_shell_stack_direction_restacks_the_element():
    # the same strip numbered with its thickness along the elements' direction 1: STACK
    # DIRECTION=1 splits it into the same solids, and its top face S4 is the last ply's S2
    order = A.HEX_STACK_ORDER[1]

    def renumber(line):
        f = [x.strip() for x in line.split(",")]
        renum = [""] * 8
        for pos, node in zip(order, f[1:]):
            renum[pos - 1] = node
        return ", ".join([f[0]] + renum)
    deck3 = SC8R_STRIP + "*Shell Section, elset=PLATE, composite\n" + LAYUP
    lines = deck3.splitlines()
    i = lines.index("*Element, type=SC8R, elset=PLATE")
    lines[i + 1], lines[i + 2] = renumber(lines[i + 1]), renumber(lines[i + 2])
    deck1 = "\n".join(lines).replace("composite\n1.", "composite, stack direction=1\n1.") + "\n"
    geo = []
    for deck in (deck3 + "*Surface, name=TOP\nPLATE, S2\n", deck1 + "*Surface, name=TOP\nPLATE, S4\n"):
        body, conv, _ = convert_str(deck)
        g = conv.geom
        name, face = _card_at(body, "*SURFACE")[0].split(", ")
        geo.append(([[g.nodes[n] for n in conn] for _, conn in g.elements.values()], g.elset(name), face))
    assert geo[0] == geo[1] and geo[0][1:] == ([4, 6], "S2")
    # STACK DIRECTION=ORIENTATION: the isoparametric direction closest to the orientation's
    # rotation axis, Abaqus' approximate normal (2017 "About shell elements"), by default axis 1
    # (the elements' direction 1 is z, 2 is x, 3 is y)
    deck = deck1.replace("stack direction=1", "stack direction=ORIENTATION, orientation=O").replace(
        "*Shell Section", "*Orientation, name=O\n1., 0., 0., 0., 1., 0.\n*Shell Section")
    _, conv, rep = convert_str(deck)                   # axis 1 = x: along x
    xs = sorted({round(conv.geom.nodes[n][0], 9) for _, conn in conv.geom.elements.values() for n in conn})
    assert xs == [0.0, 0.333333333, 0.666666667, 1.0, 1.333333333, 1.666666667, 2.0], xs
    assert "STACK DIRECTION" not in rep.text()
    split = {}
    for rot in ("3, 30.", "2, 0."):                    # about axis 3 = z, about axis 2 = y
        _, conv, rep = convert_str(deck.replace("1., 0., 0., 0., 1., 0.\n", f"1., 0., 0., 0., 1., 0.\n{rot}\n"))
        split[rot] = [[conv.geom.nodes[n] for n in conn] for _, conn in conv.geom.elements.values()]
        assert "STACK DIRECTION" not in rep.text()
    ys = sorted({round(p[1], 9) for conn in split["2, 0."] for p in conn})
    assert split["3, 30."] == geo[0][0] and ys == [0.0, 0.333333333, 0.666666667, 1.0], ys
    # an orientation whose axes come from each element's nodes: direction 3 (warned)
    _, conv, rep = convert_str(deck.replace("name=O\n1., 0., 0., 0., 1., 0.", "name=O, definition=OFFSET TO NODES\n1, 2, 4"))
    assert [[conv.geom.nodes[n] for n in conn] for _, conn in conv.geom.elements.values()] == split["2, 0."]
    assert "orientation 'O' has no fixed axes here" in rep.text()


def test_continuum_shell_layups_meeting_on_an_edge_are_tied():
    # a three-ply and a two-ply stack share the stack edges 2-12 and 5-15: their interface
    # nodes there are held on the straight edge, which both stacks share (*EQUATION)
    deck = (SC8R_STRIP.replace("*Element, type=SC8R, elset=PLATE\n1, 1, 2, 5, 4, 11, 12, 15, 14\n"
                               "2, 2, 3, 6, 5, 12, 13, 16, 15\n",
                               "*Element, type=SC8R, elset=A\n1, 1, 2, 5, 4, 11, 12, 15, 14\n"
                               "*Element, type=SC8R, elset=B\n2, 2, 3, 6, 5, 12, 13, 16, 15\n")
            + "*Nset, nset=MID\n2, 12\n*Shell Section, elset=A, composite\n" + LAYUP
            + "*Shell Section, elset=B, composite\n1., 3, CFRP, 0.\n1., 3, CFRP, 90.\n"
            "*Initial Conditions, type=TEMPERATURE\n2, 20.\n12, 50.\n"
            "*Step\n*Static\n*Boundary\nCLAMP, ENCASTRE\n*Node print, nset=MID\nU\n*End Step\n")
    body, conv, rep = convert_str(deck)
    eq = _card_at(body, "*EQUATION")
    assert len(eq) == 2 * 3 * 6                        # 6 interface nodes, 3 DOFs, 2 lines each
    assert "25, 1, 1., 2, 1, -0.5, 12, 1, -0.5" in eq   # B's mid-height node on edge 2-12
    assert "22, 3, 1., 2, 3, -0.3333333333, 12, 3, -0.6666666667" in eq
    assert "held on the shared line by *EQUATIONs" in rep.text()
    # the tied nodes join no node set (a BC there would clash with the tie) but take the
    # temperatures interpolated along their stack edge
    assert conv.geom.nset("MID") == [2, 12]
    ic = _card_at(body, "*INITIAL CONDITIONS")
    assert "25, 35" in ic and "22, 40" in ic and "18, 30" in ic


def test_continuum_shell_wedges_and_symmetric_layups_split():
    deck = ("*Node\n1, 0., 0., 0.\n2, 1., 0., 0.\n3, 0., 1., 0.\n4, 0., 0., 1.\n5, 1., 0., 1.\n"
            "6, 0., 1., 1.\n*Element, type=SC6R, elset=W\n1, 1, 2, 3, 4, 5, 6\n" + COMPOSITE_MAT
            + "*Shell Section, elset=W, composite, symmetric\n1., 3, CFRP, 45.\n3., 3, CFRP, -45.\n")
    body, conv, _ = convert_str(deck)
    g = conv.geom
    assert [t for t, _ in g.elements.values()] == ["C3D6"] * 4
    zs = sorted({round(g.nodes[n][2], 9) for _, conn in g.elements.values() for n in conn})
    assert zs == [0.0, 0.125, 0.5, 0.875, 1.0]        # relative thicknesses 1 : 3 : 3 : 1
    assert g.elset("W_PLY1") == [1, 4] and g.elset("W_PLY2") == [2, 3]


def test_continuum_shell_split_above_the_limit_is_left_out():
    deck = SC8R_STRIP + "*Shell Section, elset=PLATE, composite\n" + LAYUP
    body, conv, rep = convert_str(deck, max_ply_elements=5)
    assert "one solid per ply would make 6 elements, more than --max-ply-elements (5)" in rep.text()
    assert "** abq2ccx" in body and conv.geom.elements[1][0] == "SC8R"
    body, conv, _ = convert_str(deck, max_ply_elements=0)          # 0: no limit
    assert len(conv.geom.elements) == 6


def test_continuum_shell_layer_angle_distribution():
    # a layer's orientation field may name a distribution of angles (one per element)
    deck = (SC8R_STRIP + "*Distribution, name=ANG, location=ELEMENT, table=ANG_T\n, 10.\n2, 50.\n"
            "*Distribution Table, name=ANG_T\nANGLE\n*Shell Section, elset=PLATE, composite\n"
            "1., 3, CFRP, ANG\n1., 3, CFRP, 0.\n")
    body, conv, rep = convert_str(deck)
    lines = _card_at(body, "*DISTRIBUTION, NAME=PLATE_PLY1_AXES")
    c10, s10 = math.cos(math.radians(10.0)), math.sin(math.radians(10.0))
    first = [float(x) for x in lines[0].split(",")]
    assert first[0] == 1 and abs(first[1] - c10) < 1e-8 and abs(first[2] - s10) < 1e-8
    assert len(lines) == 2 and lines[1].startswith("2, 0.642787")      # cos 50
    assert "*DISTRIBUTION, NAME=ANG" not in body and "of composite layer angles" in rep.text()


def test_composite_shell_plies_on_a_cylinder_follow_the_hoop():
    # a cylindrical orientation's axis 1 is radial — the shell normal on a cylinder — so ccx
    # would project nothing; Abaqus projects axis 2 (the hoop direction), axis 1 being the
    # one closest to the normal
    nodes = "".join(f"{k + 1}, {math.cos(t):.9f}, {math.sin(t):.9f}, {z}\n" for k, (t, z) in enumerate(
        (math.radians(a), z) for z in (0.0, 1.0) for a in (0.0, 30.0, 60.0)))
    deck = (f"*Node\n{nodes}*Element, type=S4R, elset=CYL\n1, 1, 2, 5, 4\n2, 2, 3, 6, 5\n" + COMPOSITE_MAT
            + "*Orientation, name=CYLO, system=CYLINDRICAL\n0., 0., 0., 0., 0., 1.\n"
            "*Shell Section, elset=CYL, composite, orientation=CYLO\n0.1, 3, CFRP, 0.\n0.1, 3, CFRP, 90.\n")
    body, conv, rep = convert_str(deck)
    assert "as Abaqus defines them" in rep.text()
    lines = body.splitlines()
    first = [float(x) for x in lines[lines.index("*ORIENTATION, NAME=ABQ2CCX_PLY1") + 1].split(",")]
    t = math.radians(15.0)                             # the first element's middle
    assert max(abs(x - y) for x, y in zip(first[:3], (-math.sin(t), math.cos(t), 0.0))) < 2e-3, first
    assert "*ELSET, ELSET=CYL_P1" in body and "*ELSET, ELSET=CYL_P2" in body


def test_new_nodes_take_the_transform_of_their_edge():
    # a *TRANSFORM's set that a *CLOAD counts does not take the midside node, but the node's
    # interpolated BC is in local DOFs: it gets a copy of the transform
    deck = (S4R_STRIP + "*Shell Section, elset=PLATE, composite\n0.1, 3, CFRP, 0.\n0.1, 3, CFRP, 90.\n"
            "*Transform, nset=CLAMP, type=C\n0., 0., 0., 0., 0., 1.\n*Step\n*Static\n*Boundary\n"
            "CLAMP, 2, 2\n*Cload\nCLAMP, 3, 1.\n*End Step\n")
    body, conv, rep = convert_str(deck)
    assert conv.geom.nset("CLAMP") == [1, 4] and conv.geom.nset("CLAMP_NEW") == [10]
    assert "*TRANSFORM, NSET=CLAMP_NEW, TYPE=C" in body and "10, 2, 2" in body


def test_collapsed_composite_quad_becomes_a_triangle():
    # ccx stops on a collapsed S8R ('*ERROR in gen3dnor'): an S4R with a repeated corner is an S6
    deck = (S4R_STRIP.replace("2, 2, 3, 6, 5\n", "2, 2, 3, 6, 6\n")
            + "*Shell Section, elset=PLATE, composite\n0.1, 3, CFRP, 0.\n")
    _, conv, _ = convert_str(deck)
    assert conv.geom.elements[2] == ("S6", [2, 3, 6, 11, 12, 13])


def _orientation_values(body, name):
    return [float(x) for x in _card_at(body, f"*ORIENTATION, NAME={name}")[0].split(",")]


def test_plain_shell_section_gets_abaqus_axes():
    # Abaqus projects the axis after an orientation's rotation axis onto the shell, ccx 2.23 its
    # turned axis 1: about axis 1 on the x-y strip Abaqus' direction 1 is the turned axis 2, y
    sec = "*Shell Section, elset=PLATE, material=CFRP, orientation=O\n0.1, 5\n"
    body, conv, rep = convert_str(S4R_STRIP + "*Orientation, name=O\n1., 0., 0., 0., 1., 0.\n1, 30.\n" + sec)
    assert "given element group by element group (1 group(s) here)" in rep.text()
    assert _card_at(body, "*ORIENTATION, NAME=ABQ2CCX_AXES1") == ["0, 1, 0, -1, 0, 0"]
    assert _card_at(body, "*SHELL SECTION, ELSET=PLATE, MATERIAL=CFRP, ORIENTATION=ABQ2CCX_AXES1") == ["0.1"]
    # without a rotation line Abaqus turns about axis 1 and projects axis 2: y on the x-y strip
    # (ccx would project axis 1, x); in the x-z plane y is the normal, which Abaqus leaves
    # undocumented: the default directions, x as in ccx, warned
    body, _, rep = convert_str(S4R_STRIP + "*Orientation, name=O\n1., 0., 0., 0., 1., 0.\n" + sec)
    assert _card_at(body, "*ORIENTATION, NAME=ABQ2CCX_AXES1") == ["0, 1, 0, -1, 0, 0"]
    assert "*SHELL SECTION PLATE: orientation O: it has no rotation line" in rep.text()
    xz = S4R_STRIP.replace(", 1., 0.\n", ", 0., 1.\n")
    body, _, rep = convert_str(xz + "*Orientation, name=O\n1., 0., 0., 0., 1., 0.\n" + sec)
    assert "ABQ2CCX_AXES" not in body and "its axis 2, which Abaqus projects" in rep.text()
    # a rotation about axis 3 is read alike, and an isotropic material has no directions
    for deck in (S4R_STRIP + "*Orientation, name=O\n1., 0., 0., 0., 1., 0.\n3, 30.\n" + sec,
                 xz.replace("type=ENGINEERING CONSTANTS\n140000., 10000., 10000., 0.3, 0.3, 0.4, 5000., "
                            "5000.,\n3500.", "\n70000., 0.3") + "*Orientation, name=O\n1., 0., 0., 0., 1., 0.\n" + sec):
        body, conv, rep = convert_str(deck)
        assert "ABQ2CCX_AXES" not in body and "MATERIAL=CFRP, ORIENTATION=O" in body
    assert conv._mat_symmetry == {"CFRP": None}


def test_orientation_rotation_line_defaults():
    # Keywords *ORIENTATION: the rotation axis defaults to 1, the angle to 0.  A line "3" keeps
    # the x-y strip's cards; ", 30." turns about axis 1 and is written so for ccx 2.23, which
    # reads a blank axis as no rotation and stops on a bare angle
    sec = "*Shell Section, elset=PLATE, material=CFRP, orientation=O\n0.1, 5\n"
    ori = "*Orientation, name=O\n1., 0., 0., 0., 1., 0.\n"
    body, conv, rep = convert_str(S4R_STRIP + ori + "3\n" + sec)
    assert conv._orient_rotation["O"] == (3, 0.0) and "ABQ2CCX_AXES" not in body
    assert "no rotation line" not in rep.text()
    body, conv, _ = convert_str(S4R_STRIP + ori + ", 30.\n" + sec)
    assert conv._orient_rotation["O"] == (1, 30.0)
    assert _card_at(body, "*ORIENTATION, NAME=O") == ["1., 0., 0., 0., 1., 0.", "1, 30."]
    assert _card_at(body, "*ORIENTATION, NAME=ABQ2CCX_AXES1") == ["0, 1, 0, -1, 0, 0"]


def test_orientation_by_nodes_after_the_card_is_resolved_before_planning():
    deck = ("*Orientation, name=O, definition=NODES\n101, 102\n1, 30.\n" + S4R_STRIP
            + "*Node\n101, 0., 1., 0.\n102, -1., 0., 0.\n"
            "*Shell Section, elset=PLATE, material=CFRP, orientation=O\n0.1\n")
    body, conv, _ = convert_str(deck)
    assert conv.orientations["O"][:2] == ((0.0, 1.0, 0.0), (-1.0, 0.0, 0.0))
    # axis 1 = y, 3 = z, turned about y: Abaqus projects axis 2 (-x turned out of the plate), -x
    assert _card_at(body, "*ORIENTATION, NAME=ABQ2CCX_AXES1") == ["-1, 0, 0, 0, -1, 0"]


def test_membrane_section_gets_abaqus_axes():
    # ccx 2.23 gives a membrane its orientation's axes unprojected (the global ones without
    # one): on a y-z strip, normal x, Abaqus' direction 1 is the projection of Z
    strip = ("*Node\n1, 0., 0., 0.\n2, 0., 1., 0.\n3, 0., 2., 0.\n4, 0., 0., 1.\n5, 0., 1., 1.\n6, 0., 2., 1.\n"
             "*Element, type=M3D4, elset=SKIN\n1, 1, 2, 5, 4\n2, 2, 3, 6, 5\n" + COMPOSITE_MAT
             + "*Membrane Section, elset=SKIN, material=CFRP\n0.1\n")
    body, _, rep = convert_str(strip)
    assert _card_at(body, "*ORIENTATION, NAME=ABQ2CCX_AXES1") == ["0, 0, 1, 0, -1, 0"]
    assert _card_at(body, "*MEMBRANE SECTION, ELSET=SKIN, MATERIAL=CFRP, ORIENTATION=ABQ2CCX_AXES1") == ["0.1"]
    # an x-y strip whose normal is -z: the global axes turned half about x, the same for an
    # orthotropic material, not for an anisotropic one
    xy = strip.replace("1, 0., 0., 0.\n2, 0., 1., 0.\n3, 0., 2., 0.\n4, 0., 0., 1.\n5, 0., 1., 1.\n6, 0., 2., 1.",
                       "1, 0., 0., 0.\n2, 0., 1., 0.\n3, 0., 2., 0.\n4, 1., 0., 0.\n5, 1., 1., 0.\n6, 1., 2., 0.")
    body, _, _ = convert_str(xy)
    assert "ORIENTATION" not in body.split("*MEMBRANE SECTION")[1].splitlines()[0]
    aniso = ("*Elastic, type=ANISOTROPIC\n" + ", ".join(["100."] * 8) + "\n" + ", ".join(["10."] * 8)
             + "\n" + ", ".join(["10."] * 5) + "\n")
    body, conv, _ = convert_str(xy.replace("*Elastic, type=ENGINEERING CONSTANTS\n140000., 10000., 10000., 0.3, "
                                           "0.3, 0.4, 5000., 5000.,\n3500.\n", aniso))
    assert conv._mat_symmetry["CFRP"] == "aniso"
    assert _card_at(body, "*ORIENTATION, NAME=ABQ2CCX_AXES1") == ["1, 0, 0, 0, -1, 0"]     # x, -z cross x


def test_cylindrical_orientation_on_a_plain_shell_cylinder():
    # the system's axis 1, radial, is the normal: Abaqus turns about it and projects axis 2 (the
    # hoop direction, here turned 25 degrees towards the axis); ccx would project axis 1 and
    # drop the rotation, which the element-by-element axes keep
    nodes = "".join(f"{k + 1}, {math.cos(t):.9f}, {math.sin(t):.9f}, {z}\n" for k, (t, z) in enumerate(
        (math.radians(a), z) for z in (0.0, 1.0) for a in (0.0, 30.0, 60.0)))
    deck = (f"*Node\n{nodes}*Element, type=S4R, elset=CYL\n1, 1, 2, 5, 4\n2, 2, 3, 6, 5\n" + COMPOSITE_MAT
            + "*Orientation, name=CYLO, system=CYLINDRICAL\n0., 0., 0., 0., 0., 1.\n1, 25.\n"
            "*Shell Section, elset=CYL, material=CFRP, orientation=CYLO\n0.1\n")
    body, conv, rep = convert_str(deck)
    t, r = math.radians(15.0), math.radians(25.0)
    want = (-math.sin(t) * math.cos(r), math.cos(t) * math.cos(r), math.sin(r))
    assert max(abs(x - y) for x, y in zip(_orientation_values(body, "ABQ2CCX_AXES1")[:3], want)) < 1e-6
    assert "*ELSET, ELSET=CYL_AX1" in body and "*ELSET, ELSET=CYL_AX2" in body
    assert "the rotation applied" in rep.text() and not conv.reduced_physics
    # the same as a cylindrical *DISTRIBUTION (one line scaled): the rotation is kept too
    deck = deck.replace("*Orientation, name=CYLO, system=CYLINDRICAL\n0., 0., 0., 0., 0., 1.\n",
                        "*Distribution, name=D, location=ELEMENT, table=T\n, 0., 0., 0., 0., 0., 1.\n"
                        "2, 0., 0., 0., 0., 0., 2.\n*Distribution Table, name=T\ncoord3D, coord3D\n"
                        "*Orientation, name=CYLO, system=CYLINDRICAL\nD\n")
    body, conv, rep = convert_str(deck)
    assert max(abs(x - y) for x, y in zip(_orientation_values(body, "ABQ2CCX_AXES1")[:3], want)) < 1e-6
    assert "*DISTRIBUTION" not in body and "was dropped" not in rep.text() and not conv.reduced_physics


def test_distribution_orientation_on_a_plain_shell_gets_abaqus_axes():
    # each element's distribution line turned about its axis 1: Abaqus projects the turned
    # axis 2, ccx would project axis 1 of the per-direction orientations
    deck = (S4R_STRIP + "*Distribution, name=D, location=ELEMENT, table=T\n, 1., 0., 0., 0., 1., 0.\n"
            "2, 0., 1., 0., -1., 0., 0.\n*Distribution Table, name=T\ncoord3D, coord3D\n"
            "*Orientation, name=O\nD\n1, 30.\n*Shell Section, elset=PLATE, material=CFRP, orientation=O\n0.1\n")
    body, conv, rep = convert_str(deck)
    assert _card_at(body, "*ORIENTATION, NAME=ABQ2CCX_AXES1") == ["0, 1, 0, -1, 0, 0"]
    assert _card_at(body, "*ORIENTATION, NAME=ABQ2CCX_AXES2") == ["-1, 0, 0, 0, -1, 0"]
    assert "*ELSET, ELSET=PLATE_AX1\n1\n" in body and "*ELSET, ELSET=PLATE_AX2\n2\n" in body
    assert "*DISTRIBUTION" not in body and "_A1" not in body


def test_distribution_composite_with_axis_3_off_the_normal_gets_exact_plies():
    # b out of the plate tilts the distribution's axis 3: Abaqus still projects axis 1 (the
    # rotation line names axis 3) and turns the 45-degree ply about the normal
    deck = (S4R_STRIP + "*Distribution, name=D, location=ELEMENT, table=T\n, 1., 0., 0., 0., 0.866025404, 0.5\n"
            "*Distribution Table, name=T\ncoord3D, coord3D\n*Orientation, name=O\nD\n3, 0.\n"
            "*Shell Section, elset=PLATE, composite, orientation=O\n0.1, 3, CFRP, 0.\n0.1, 3, CFRP, 45.\n")
    body, _, rep = convert_str(deck)
    assert "as Abaqus defines them" in rep.text() and "*DISTRIBUTION" not in body
    assert _card_at(body, "*ORIENTATION, NAME=ABQ2CCX_PLY1") == ["1, 0, 0, 0, 1, 0"]
    c = math.sqrt(0.5)
    assert max(abs(x - y) for x, y in zip(_orientation_values(body, "ABQ2CCX_PLY2"), (c, c, 0, -c, c, 0))) < 1e-8
    # with b in the plate ccx turns the ply about the normal as Abaqus does: the usual split
    body, _, rep = convert_str(deck.replace("0., 0.866025404, 0.5", "0., 1., 0."))
    assert "as Abaqus defines them" not in rep.text() and "3, 45." in body


def test_orientation_without_axes_is_not_given_made_up_directions():
    # an orientation from each element's nodes, or one whose points are missing, has no axes
    # the converter knows: its sections keep naming it (commented out, so ccx stops)
    xz = S4R_STRIP.replace(", 1., 0.\n", ", 0., 1.\n")
    sec = "*Shell Section, elset=PLATE, material=CFRP, orientation=O\n0.1\n"
    for ori in ("*Orientation, name=O, definition=OFFSET TO NODES\n1, 2, 4\n", "*Orientation, name=O\n1., 0., 0.\n"):
        body, conv, _ = convert_str(xz + ori + sec)
        assert "ABQ2CCX_AXES" not in body and "MATERIAL=CFRP, ORIENTATION=O" in body
    # a composite ply split on such an orientation warns, as for an undefined one
    body, conv, rep = convert_str(SC8R_STRIP + "*Orientation, name=O, definition=OFFSET TO NODES\n1, 2, 4\n"
                                  "*Shell Section, elset=PLATE, composite, orientation=O\n" + LAYUP)
    assert "has no axes the converter can form" in rep.text()
    assert any("ply orientation O without axes" in r for r in conv.reduced_physics)


def test_isotropic_composite_keeps_its_exact_plies():
    # isotropic plies need no directions, but their usual cards would turn a 45-degree ply on an
    # orientation rotated about axis 1 and warn: the plies keep their exact directions instead
    deck = (S4R_STRIP + "*Material, name=AL\n*Elastic\n70000., 0.3\n*Orientation, name=O\n"
            "1., 0., 0., 0., 1., 0.\n1, 30.\n*Shell Section, elset=PLATE, composite, orientation=O\n"
            "0.1, 3, AL, 0.\n0.1, 3, AL, 45.\n")
    body, conv, rep = convert_str(deck)
    assert "as Abaqus defines them" in rep.text()
    assert conv.reduced_physics == ["element S4R -> S8R (ccx runs composite shells on S8R / S6 only)"]


def test_cylindrical_orientation_turning_across_an_element_is_warned():
    # ccx takes a shell orientation once per element: on an annulus of 8 S4 elements a
    # cylindrical system turns by 45 degrees across one, which Abaqus follows to its four
    # integration points; an S4R has one, at the centre, where ccx takes it too
    pts = [(r * math.cos(math.radians(45.0 * i)), r * math.sin(math.radians(45.0 * i)))
           for r in (1.0, 2.0) for i in range(8)]
    nodes = "".join(f"{k + 1}, {x:.9f}, {y:.9f}, 0.\n" for k, (x, y) in enumerate(pts))
    elems = "".join(f"{i + 1}, {i + 1}, {(i + 1) % 8 + 1}, {(i + 1) % 8 + 9}, {i + 9}\n" for i in range(8))
    deck = (f"*Node\n{nodes}*Element, type=S4, elset=DISK\n{elems}" + COMPOSITE_MAT
            + "*Orientation, name=C, system=CYLINDRICAL\n0., 0., 0., 0., 0., 1.\n3, 0.\n"
            "*Shell Section, elset=DISK, material=CFRP, orientation=C\n0.1\n")
    body, conv, rep = convert_str(deck)
    assert re.search(r"turns the material directions by up to 2[23] degrees across an element", rep.text())
    assert conv.reduced_physics and "ABQ2CCX_AXES" not in body    # ccx's own radial agrees at the centre
    _, conv, rep = convert_str(deck.replace("type=S4,", "type=S4R,"))
    assert "across an element" not in rep.text() and not conv.reduced_physics
    # without the rotation line Abaqus turns about axis 1, radial in the disk, and projects
    # axis 2: the hoop direction (normal -z here), element group by element group
    body, _, rep = convert_str(deck.replace("3, 0.\n", ""))
    assert _card_at(body, "*ORIENTATION, NAME=ABQ2CCX_AXES1") == \
        ["-0.382683432, 0.923879533, 0, 0.923879533, 0.382683432, 0"]
    assert "orientation C: it has no rotation line" in rep.text()
    _, conv, rep = convert_str(deck.replace("material=CFRP", "material=ISO") + "*Material, name=ISO\n*Elastic\n1., 0.3\n")
    assert "across an element" not in rep.text() and not conv.reduced_physics


def test_material_symmetry_classes():
    deck = (S4R_STRIP + "*Material, name=ISO\n*Elastic\n200000., 0.3\n*Plastic\n250., 0.\n"
            "*Material, name=EXP\n*Elastic\n200000., 0.3\n*Expansion, type=ORTHO\n1e-5, 2e-5, 3e-5\n"
            "*Material, name=HILL\n*Elastic\n200000., 0.3\n*Plastic\n250., 0.\n*Potential\n1., 1.1, 1., 1., 1., 1.\n"
            "*Material, name=COND\n*Conductivity, type=ANISO\n1., 2., 3., 0.1, 0., 0.\n"
            "*Material, name=UM\n*User Material, constants=1\n1.\n")
    _, conv, _ = convert_str(deck)
    assert {k: conv._mat_symmetry[k] for k in ("CFRP", "ISO", "EXP", "HILL", "COND", "UM")} == \
        dict(CFRP="ortho", ISO=None, EXP="ortho", HILL="ortho", COND="aniso", UM="aniso")


def _placed(deck, place):
    """``deck`` with the coordinates of its *Node lines mapped by ``place``."""
    out, nodes = [], False
    for line in deck.splitlines():
        if line.startswith("*"):
            nodes = line.lower() == "*node"
        elif nodes:
            f = line.split(",")
            line = f[0] + "".join(f", {c:g}" for c in place(tuple(float(x) for x in f[1:4])))
        out.append(line)
    return "\n".join(out) + "\n"


SC8R_XZ = _placed(SC8R_STRIP, lambda p: (p[0], -p[2], p[1]))      # the strip in the x-z plane, normal -y
ANISO_CFRP = ("*Elastic, type=ANISOTROPIC\n" + ", ".join(["100."] * 8) + "\n" + ", ".join(["10."] * 8)
              + "\n" + ", ".join(["10."] * 5) + "\n")


def test_continuum_shell_section_gets_abaqus_axes():
    # a plain section on continuum shells runs as a *SOLID SECTION, whose orientation ccx 2.23
    # takes unprojected (the global axes without one); Abaqus projects it onto the mid-surface,
    # the stack direction as axis 3
    sec = "*Shell Section, elset=PLATE, material=CFRP{}\n0.3\n"
    body, _, _ = convert_str(SC8R_STRIP + sec.format(""))
    assert "*SOLID SECTION, ELSET=PLATE, MATERIAL=CFRP" in body.splitlines() and "ABQ2CCX_AXES" not in body
    # in the x-z plane direction 2 is z and the normal -y (ccx: y and z)
    body, conv, rep = convert_str(SC8R_XZ + sec.format(""))
    assert _card_at(body, "*ORIENTATION, NAME=ABQ2CCX_AXES1") == ["1, 0, 0, 0, 0, 1"]
    assert "*SOLID SECTION, ELSET=PLATE, MATERIAL=CFRP, ORIENTATION=ABQ2CCX_AXES1" in body
    assert "on continuum shells whose material directions ccx's solids would place otherwise" in rep.text()
    assert conv.reduced_physics == ["element SC8R -> C3D8I"]
    body, _, _ = convert_str(SC8R_XZ.replace("*Shell Section", "*Shell General Section") + sec.format("")
                             .replace("*Shell Section", "*Shell General Section"))
    assert "MATERIAL=CFRP, ORIENTATION=ABQ2CCX_AXES1" in body
    # turned about axis 1, Abaqus projects axis 2 (y); turned about axis 3 it is ccx's axis 1
    ori = "*Orientation, name=O\n1., 0., 0., 0., 1., 0.\n{}, 30.\n"
    body, _, _ = convert_str(SC8R_STRIP + ori.format(1) + sec.format(", orientation=O"))
    assert _card_at(body, "*ORIENTATION, NAME=ABQ2CCX_AXES1") == ["0, 1, 0, -1, 0, 0"]
    body, _, _ = convert_str(SC8R_STRIP + ori.format(3) + sec.format(", orientation=O"))
    assert "ABQ2CCX_AXES" not in body and "*SOLID SECTION, ELSET=PLATE, MATERIAL=CFRP, ORIENTATION=O" in body
    # without a rotation line Abaqus turns about axis 1, here in the plate: direction 1 is axis 2
    body, _, rep = convert_str(SC8R_STRIP + "*Orientation, name=O\n1., 0., 0., 0., 1., 0.\n" + sec.format(", orientation=O"))
    assert _card_at(body, "*ORIENTATION, NAME=ABQ2CCX_AXES1") == ["0, 1, 0, -1, 0, 0"]
    assert "it has no rotation line, so Abaqus turns it about its axis 1" in rep.text()
    # an isotropic material has no directions
    iso = SC8R_XZ.replace("type=ENGINEERING CONSTANTS\n140000., 10000., 10000., 0.3, 0.3, 0.4, 5000., 5000.,\n"
                          "3500.", "\n70000., 0.3")
    body, _, _ = convert_str(iso + sec.format(""))
    assert "ABQ2CCX_AXES" not in body
    # stacked downwards: the global axes turned half about x, the same for an orthotropic
    # material, not for an anisotropic one
    down = SC8R_STRIP.replace("1, 1, 2, 5, 4, 11, 12, 15, 14\n2, 2, 3, 6, 5, 12, 13, 16, 15",
                              "1, 11, 14, 15, 12, 1, 4, 5, 2\n2, 12, 15, 16, 13, 2, 5, 6, 3")
    body, _, _ = convert_str(down + sec.format(""))
    assert "ABQ2CCX_AXES" not in body
    body, _, _ = convert_str(down.replace(COMPOSITE_MAT.split("\n", 1)[1], ANISO_CFRP) + sec.format(""))
    assert _card_at(body, "*ORIENTATION, NAME=ABQ2CCX_AXES1") == ["1, 0, 0, 0, -1, 0"]


def test_continuum_shell_axes_follow_the_stack_direction():
    # the x-z strip numbered with its thickness along the elements' direction 1: with STACK
    # DIRECTION=1 its directions are the strip's own (x, z; normal -y); read along direction 3
    # its normal would be z, whose shell axes x, y are ccx's own
    order = A.HEX_STACK_ORDER[1]

    def renumber(line):
        f = [x.strip() for x in line.split(",")]
        renum = [""] * 8
        for pos, node in zip(order, f[1:]):
            renum[pos - 1] = node
        return ", ".join([f[0]] + renum)
    lines = SC8R_XZ.splitlines()
    i = lines.index("*Element, type=SC8R, elset=PLATE")
    lines[i + 1], lines[i + 2] = renumber(lines[i + 1]), renumber(lines[i + 2])
    deck = "\n".join(lines) + "\n*Shell Section, elset=PLATE, material=CFRP, stack direction=1\n0.3\n"
    body, _, _ = convert_str(deck)
    assert _card_at(body, "*ORIENTATION, NAME=ABQ2CCX_AXES1") == ["1, 0, 0, 0, 0, 1"]
    body, _, _ = convert_str(deck.replace(", stack direction=1", ""))
    assert "ABQ2CCX_AXES" not in body
    # STACK DIRECTION=ORIENTATION: along the orientation's rotation axis, here 3: -y, whose axes
    # then agree; without a rotation line along axis 1, here -y too, and Abaqus projects axis 2
    body, _, _ = convert_str(deck.replace("stack direction=1", "stack direction=ORIENTATION, orientation=O")
                             + "*Orientation, name=O\n1., 0., 0., 0., 0., 1.\n3, 0.\n")
    assert "ABQ2CCX_AXES" not in body and "MATERIAL=CFRP, ORIENTATION=O" in body
    body, _, rep = convert_str(deck.replace("stack direction=1", "stack direction=ORIENTATION, orientation=O")
                               + "*Orientation, name=O\n0., -1., 0., 1., 0., 0.\n")
    assert _card_at(body, "*ORIENTATION, NAME=ABQ2CCX_AXES1") == ["1, 0, 0, 0, 0, 1"]
    assert "STACK DIRECTION" not in rep.text()
    # an SC6R wedge is stacked from nodes 1-3 to 4-6
    wedge = ("*Node\n1, 0., 0., 0.\n2, 1., 0., 0.\n3, 0., 0., 1.\n4, 0., -0.1, 0.\n5, 1., -0.1, 0.\n"
             "6, 0., -0.1, 1.\n*Element, type=SC6R, elset=W\n1, 1, 2, 3, 4, 5, 6\n" + COMPOSITE_MAT
             + "*Shell Section, elset=W, material=CFRP\n0.1\n")
    body, _, _ = convert_str(wedge)
    assert _card_at(body, "*ORIENTATION, NAME=ABQ2CCX_AXES1") == ["1, 0, 0, 0, 0, 1"]
    assert "*SOLID SECTION, ELSET=W, MATERIAL=CFRP, ORIENTATION=ABQ2CCX_AXES1" in body


def test_continuum_shell_cylindrical_orientation_gets_axes_element_by_element():
    # an SC8R ring stacked outward: the system's axis 1, radial, is the normal; Abaqus turns about
    # it and projects axis 2 at the element's centre, ccx would take the system's axes (fibres
    # radial) at each integration point and drop the rotation
    pts = [(r, math.radians(a), z) for r in (1.0, 1.1) for z in (0.0, 1.0) for a in (0.0, 30.0, 60.0)]
    nodes = "".join(f"{k + 1}, {r * math.cos(t):.9f}, {r * math.sin(t):.9f}, {z}\n" for k, (r, t, z) in enumerate(pts))
    deck = (f"*Node\n{nodes}*Element, type=SC8R, elset=CYL\n1, 1, 2, 5, 4, 7, 8, 11, 10\n"
            "2, 2, 3, 6, 5, 8, 9, 12, 11\n" + COMPOSITE_MAT
            + "*Orientation, name=CYLO, system=CYLINDRICAL\n0., 0., 0., 0., 0., 1.\n1, 25.\n"
            "*Shell Section, elset=CYL, material=CFRP, orientation=CYLO\n0.1\n")
    body, conv, rep = convert_str(deck)
    lines = _card_at(body, "*DISTRIBUTION, NAME=CYL_AXES")
    t, r = math.radians(15.0), math.radians(25.0)
    want = (1.0, -math.sin(t) * math.cos(r), math.cos(t) * math.cos(r), math.sin(r),     # direction 1
            math.sin(t) * math.sin(r), -math.cos(t) * math.sin(r), math.cos(r))         # radial x it
    vals = [float(x) for x in lines[0].split(",")]
    assert len(lines) == 2 and len(vals) == 7 and max(abs(x - y) for x, y in zip(vals, want)) < 1e-6
    assert _card_at(body, "*ORIENTATION, NAME=CYL_ORI") == ["CYL_AXES"]
    assert "*SOLID SECTION, ELSET=CYL, MATERIAL=CFRP, ORIENTATION=CYL_ORI" in body
    assert "the rotation applied" in rep.text() and conv.reduced_physics == ["element SC8R -> C3D8I"]
    # on an annulus the system agrees with Abaqus' axes at the element centres, not across
    # them: Abaqus takes them at the centre, ccx would at each integration point
    pts = [(r * math.cos(math.radians(45.0 * i)), r * math.sin(math.radians(45.0 * i)), z)
           for z in (0.0, 0.1) for r in (1.0, 2.0) for i in range(8)]
    nodes = "".join(f"{k + 1}, {x:.9f}, {y:.9f}, {z}\n" for k, (x, y, z) in enumerate(pts))
    elems = "".join(f"{i + 1}, {i + 1}, {i + 9}, {(i + 1) % 8 + 9}, {(i + 1) % 8 + 1}, {i + 17}, {i + 25}, "
                    f"{(i + 1) % 8 + 25}, {(i + 1) % 8 + 17}\n" for i in range(8))
    disk = (f"*Node\n{nodes}*Element, type=SC8R, elset=DISK\n{elems}" + COMPOSITE_MAT
            + "*Orientation, name=C, system=CYLINDRICAL\n0., 0., 0., 0., 0., 1.\n3, 0.\n"
            "*Shell Section, elset=DISK, material=CFRP, orientation=C\n0.1\n")
    body, _, _ = convert_str(disk)
    c, s = math.cos(math.radians(22.5)), math.sin(math.radians(22.5))
    lines = _card_at(body, "*DISTRIBUTION, NAME=DISK_AXES")
    assert len(lines) == 8 and max(abs(float(x) - y) for x, y in zip(lines[0].split(","), (1, c, s, 0, -s, c, 0))) < 1e-8


def test_continuum_shell_distribution_orientation_gets_abaqus_axes():
    # each element's distribution line turned about its axis 1: Abaqus projects the turned axis 2,
    # ccx would take the turned axes as they are; the deck's distribution is then not needed
    deck = (SC8R_STRIP + "*Distribution, name=D, location=ELEMENT, table=T\n, 1., 0., 0., 0., 1., 0.\n"
            "2, 0., 1., 0., -1., 0., 0.\n*Distribution Table, name=T\ncoord3D, coord3D\n"
            "*Orientation, name=O\nD\n1, 30.\n*Shell Section, elset=PLATE, material=CFRP, orientation=O\n0.3\n")
    body, conv, rep = convert_str(deck)
    assert _card_at(body, "*DISTRIBUTION, NAME=PLATE_AXES") == ["1, 0, 1, 0, -1, 0, 0", "2, -1, 0, 0, 0, -1, 0"]
    assert "*SOLID SECTION, ELSET=PLATE, MATERIAL=CFRP, ORIENTATION=PLATE_ORI" in body
    assert not {"*DISTRIBUTION, NAME=D", "*ORIENTATION, NAME=O"} & set(body.splitlines())
    # turned about axis 3, ccx's per-element lines agree: the deck's distribution stays
    body, _, _ = convert_str(deck.replace("1, 30.", "3, 30."))
    assert "*DISTRIBUTION, NAME=D" in body.splitlines() and "MATERIAL=CFRP, ORIENTATION=O" in body


def test_continuum_shell_distribution_orientation_shared_with_other_cards():
    # a C3D8 solid on the same distribution orientation keeps its line in the deck's distribution
    # (the continuum shells have their own), and a card that is no section still finds it
    deck = (SC8R_STRIP + "*Node\n21, 3., 0., 0.\n22, 4., 0., 0.\n23, 4., 1., 0.\n24, 3., 1., 0.\n"
            "25, 3., 0., 1.\n26, 4., 0., 1.\n27, 4., 1., 1.\n28, 3., 1., 1.\n*Element, type=C3D8, elset=BLOCK\n"
            "3, 21, 22, 23, 24, 25, 26, 27, 28\n*Distribution, name=D, location=ELEMENT, table=T\n"
            ", 1., 0., 0., 0., 1., 0.\n3, 0., 1., 0., -1., 0., 0.\n*Distribution Table, name=T\ncoord3D, coord3D\n"
            "*Orientation, name=O\nD\n1, 30.\n*Shell Section, elset=PLATE, material=CFRP, orientation=O\n0.3\n")
    body, _, _ = convert_str(deck + "*Solid Section, elset=BLOCK, material=CFRP, orientation=O\n")
    lines = _card_at(body, "*DISTRIBUTION, NAME=D")
    assert lines[0].startswith(", ") and [ln.split(",")[0] for ln in lines[1:]] == ["3"]
    assert "*SOLID SECTION, ELSET=PLATE, MATERIAL=CFRP, ORIENTATION=ABQ2CCX_AXES1" in body   # both: default line
    body, _, rep = convert_str(deck + "*Element, type=SPRING2, elset=SPR\n50, 3, 13\n"
                               "*Spring, elset=SPR, orientation=O\n1, 1\n100.\n")
    assert {"*DISTRIBUTION, NAME=D", "*ORIENTATION, NAME=O"} <= set(body.splitlines())
    assert "*SPRING, ELSET=SPR, ORIENTATION=O" in body and "MATERIAL=CFRP, ORIENTATION=ABQ2CCX_AXES1" in body


def test_continuum_shell_stack_along_a_cylindrical_orientation():
    # STACK DIRECTION=ORIENTATION stacks along the orientation's rotation axis at each element's
    # centre, axis 1 without a rotation line: a cylindrical system's radial axis (2017 "About
    # shell elements", Figure 6).  The ring's elements run radially along their direction 1 and
    # axially along 3, yet the plies stack outward, the 0-degree ply along the hoop
    pts = [(r, math.radians(a), z) for r in (1.0, 1.1) for z in (0.0, 1.0) for a in (0.0, 30.0, 60.0)]
    nodes = "".join(f"{k + 1}, {r * math.cos(t):.9f}, {r * math.sin(t):.9f}, {z}\n" for k, (r, t, z) in enumerate(pts))
    deck = (f"*Node\n{nodes}*Element, type=SC8R, elset=CYL\n1, 1, 7, 8, 2, 4, 10, 11, 5\n"
            "2, 2, 8, 9, 3, 5, 11, 12, 6\n" + COMPOSITE_MAT
            + "*Orientation, name=C, system=CYLINDRICAL\n0., 0., 0., 0., 0., 1.\n"
            "*Shell Section, elset=CYL, composite, stack direction=ORIENTATION, orientation=C\n"
            "1., 3, CFRP, 0.\n1., 3, CFRP, 90.\n")
    body, conv, _ = convert_str(deck)
    g = conv.geom
    assert {round(math.hypot(*g.nodes[n][:2]), 9) for n in g.nodes if n > 12} == {1.05}
    assert g.elements[1] == ("C3D8I", [1, 2, 5, 4, 13, 14, 15, 16])          # the inner ply
    c, s = math.cos(math.radians(15.0)), math.sin(math.radians(15.0))
    vals = [float(x) for x in _card_at(body, "*DISTRIBUTION, NAME=CYL_PLY1_AXES")[0].split(",")]
    assert max(abs(x - y) for x, y in zip(vals, (1, -s, c, 0, 0, 0, 1))) < 1e-8
    # turned about its axis 3, the plies stack along the cylinder's axis
    _, conv, _ = convert_str(deck.replace("0., 0., 1.\n*Shell", "0., 0., 1.\n3, 0.\n*Shell"))
    assert {conv.geom.nodes[n][2] for n in conv.geom.nodes if n > 12} == {0.5}


def test_continuum_shell_stack_along_a_spherical_orientation():
    # a spherical system's axis 1 is radial from its centre a: a patch of a sphere whose element
    # runs around along direction 1, outward along 2 and down along 3 stacks outward (read as a
    # rectangular system, the centre at the origin gave no axis at all); STACK DIR abbreviates
    # STACK DIRECTION, as Abaqus allows
    def sph(r, ph, th):
        ph, th = math.radians(ph), math.radians(th)
        return (r * math.sin(th) * math.cos(ph), r * math.sin(th) * math.sin(ph), r * math.cos(th))
    corners = [(9.99, 0, 30), (9.99, 10, 30), (10.01, 10, 30), (10.01, 0, 30),
               (9.99, 0, 40), (9.99, 10, 40), (10.01, 10, 40), (10.01, 0, 40)]
    nodes = "".join(f"{i + 1}, " + ", ".join(f"{x:.12f}" for x in sph(*c)) + "\n" for i, c in enumerate(corners))
    deck = (f"*Node\n{nodes}*Element, type=SC8R, elset=CAP\n1, 1, 2, 3, 4, 5, 6, 7, 8\n" + COMPOSITE_MAT
            + "*Orientation, name=SPH, system=SPHERICAL\n0., 0., 0., 0., 0., 1.\n"
            "*Shell Section, elset=CAP, composite, stack dir=ORIENTATION, orientation=SPH\n"
            "1., 3, CFRP, 0.\n1., 3, CFRP, 90.\n")
    _, conv, rep = convert_str(deck)
    g = conv.geom
    assert {round(math.sqrt(sum(x * x for x in g.nodes[n])), 9) for n in g.nodes if n > 8} == {10.0}
    assert "STACK DIR" not in rep.text()


NODE_ORI_ASSEMBLY = ("*Assembly, name=A\n*Instance, name=I1, part=P\n*End Instance\n"
                     "*Instance, name=I2, part=P\n5., 0., 0.\n5., 0., 0., {}, 90.\n*End Instance\n"
                     "*End Assembly\n")


def test_continuum_shell_stack_along_a_node_orientation_of_each_instance():
    # *ORIENTATION, DEFINITION=NODES in a *Part names the part's nodes: each instance's copy
    # names its own.  I2, moved 5 along x and turned 90 degrees about y, stacks along its 0.3
    # thickness, now along x (it took I1's nodes and stacked across its 1.0 side)
    deck = ("*Part, name=P\n*Node\n1, 0., 0., 0.\n2, 1., 0., 0.\n3, 1., 1., 0.\n4, 0., 1., 0.\n"
            "5, 0., 0., 0.3\n6, 1., 0., 0.3\n7, 1., 1., 0.3\n8, 0., 1., 0.3\n"
            "*Element, type=SC8R, elset=E\n1, 1, 2, 3, 4, 5, 6, 7, 8\n"
            "*Orientation, name=O, definition=NODES\n5, 2, 1\n"
            "*Shell Section, elset=E, composite, stack direction=ORIENTATION, orientation=O\n"
            "0.1, 3, CFRP, 0.\n0.1, 3, CFRP, 90.\n*End Part\n"
            + NODE_ORI_ASSEMBLY.format("5., 1., 0.") + COMPOSITE_MAT)
    _, conv, _ = convert_str(deck)
    g = conv.geom
    a, b = conv.orientations["I2_O"][:2]
    assert max(abs(x - y) for x, y in zip(a + b, (0.3, 0., 0., 0., 0., -1.))) < 1e-12
    for inst, along in (("I1", 2), ("I2", 0)):
        for ply in ("PLY1", "PLY2"):
            (e,) = g.elset(f"{inst}_E_{ply}")
            xyz = [g.nodes[n] for n in g.elements[e][1]]
            size = [max(p[i] for p in xyz) - min(p[i] for p in xyz) for i in range(3)]
            assert max(abs(s - (0.15 if i == along else 1.0)) for i, s in enumerate(size)) < 1e-12, (inst, size)


def test_node_orientation_of_a_solid_section_turns_with_each_instance():
    # a part's solid-section axes by nodes 2 (x), 4 (y) and origin 1: I2, moved 5 along x and
    # turned 90 degrees about z, gets them turned (it took I1's).  Without node c the origin is
    # the part's, which moves with I2: a and b are the part's directions turned (I2's own nodes
    # 2 and 4 seen from the global origin would put axis 1 along (5, 1, 0)).  Behind a reference
    # point numbered first, I1 too names its own nodes (it took the point and I1's nodes 1 and
    # 3).  A cylindrical system's axis points move like nodes
    deck = ("*Part, name=P\n" + HEX + "*Orientation, name=O, definition=NODES\n2, 4, 1\n"
            "*Solid Section, elset=EALL, material=CFRP, orientation=O\n*End Part\n"
            + NODE_ORI_ASSEMBLY.format("5., 0., 1.") + COMPOSITE_MAT)
    rp = "*Assembly, name=A\n*Node\n1, 9., 9., 9.\n"
    for text in (deck, deck.replace("2, 4, 1\n", "2, 4\n"), deck.replace("*Assembly, name=A\n", rp)):
        body, _, _ = convert_str(text)
        assert _card_at(body, "*ORIENTATION, NAME=I1_O") == ["1, 0, 0, 0, 1, 0"]
        assert _card_at(body, "*ORIENTATION, NAME=I2_O") == ["0, 1, 0, -1, 0, 0"]
        assert "*SOLID SECTION, ELSET=I2_EALL, MATERIAL=CFRP, ORIENTATION=I2_O" in body
    body, _, _ = convert_str(deck.replace("name=O, definition=NODES\n2, 4, 1",
                                          "name=O, system=CYLINDRICAL, definition=NODES\n1, 5"))
    assert _card_at(body, "*ORIENTATION, NAME=I2_O") == ["5, 0, 0, 5, 0, 1"]


def _sph(r, th, ph):
    """The point at radius ``r``, colatitude ``th`` and longitude ``ph`` (degrees) about the origin."""
    th, ph = math.radians(th), math.radians(ph)
    return (r * math.sin(th) * math.cos(ph), r * math.sin(th) * math.sin(ph), r * math.cos(th))


# a patch of a sphere of radius 10 about the origin at colatitudes 40-50 degrees and longitudes 0-20:
# nodes 1-3 and 4-6 on its two parallels (11-16 on the outer face of a continuum shell)
SPHERE_PATCH_NODES = "".join(f"{10 * k + 3 * i + j + 1}, " + ", ".join(f"{x:.12f}" for x in _sph(r, 40 + 10 * i, 10 * j)) + "\n"
                             for k, r in ((0, 10.0), (1, 10.02)) for i in range(2) for j in range(3))
SPH_ORIENTATION = "*Orientation, name=SPH, system=SPHERICAL\n0., 0., 0., 0., 0., 1.\n"


def test_spherical_orientation_on_a_plain_shell_sphere():
    # Abaqus' spherical system: 1 radial from the centre a, 2 along the parallels, 3 along the
    # meridians towards b (2017 "Orientations"); turned about axis 1, the normal, Abaqus projects
    # axis 2.  ccx has none and reads the rectangular card the converter writes as zero axes
    deck = ("*Node\n" + "".join(ln + "\n" for ln in SPHERE_PATCH_NODES.splitlines()[:6])
            + "*Element, type=S4R, elset=CAP\n1, 1, 4, 5, 2\n2, 2, 5, 6, 3\n" + COMPOSITE_MAT + SPH_ORIENTATION
            + "*Shell Section, elset=CAP, material=CFRP, orientation=SPH\n0.02\n")
    body, conv, rep = convert_str(deck)
    s, c = math.sin(math.radians(5.0)), math.cos(math.radians(5.0))
    assert max(abs(x - y) for x, y in zip(_orientation_values(body, "ABQ2CCX_AXES1")[:3], (-s, c, 0.0))) < 1e-9
    assert _orientation_values(body, "ABQ2CCX_AXES1")[5] > 0.7            # direction 2 up the meridian
    assert "*ELSET, ELSET=CAP_AX1" in body and "*ORIENTATION, NAME=SPH, SYSTEM=RECTANGULAR" in body
    assert "no element reads it" in rep.text() and not conv.reduced_physics
    # membranes alike (ccx takes their axes unprojected: a = direction 1, b = normal x it)
    body, conv, _ = convert_str(deck.replace("type=S4R", "type=M3D4").replace("*Shell Section", "*Membrane Section"))
    assert _orientation_values(body, "ABQ2CCX_AXES1")[:3] == _orientation_values(convert_str(deck)[0], "ABQ2CCX_AXES1")[:3]
    assert "*MEMBRANE SECTION, ELSET=CAP_AX1, MATERIAL=CFRP, ORIENTATION=ABQ2CCX_AXES1" in body and not conv.reduced_physics
    # turned 90 degrees about axis 1, Abaqus projects axis 3: the meridian towards the pole
    body, _, _ = convert_str(deck.replace("0., 0., 1.\n*Shell", "0., 0., 1.\n1, 90.\n*Shell"))
    want = (-math.cos(math.radians(45.0)) * c, -math.cos(math.radians(45.0)) * s, math.sin(math.radians(45.0)))
    assert max(abs(x - y) for x, y in zip(_orientation_values(body, "ABQ2CCX_AXES1")[:3], want)) < 2e-3
    # a solid that reads the card too takes it rectangular: reduced physics, as before
    block = "*Node\n" + "".join(f"{101 + k}, {k % 2}., {k // 2 % 2}., {k // 4}.\n" for k in range(8)) + \
        "*Element, type=C3D8, elset=BLOCK\n9, 101, 102, 104, 103, 105, 106, 108, 107\n"
    _, conv, rep = convert_str(deck + block + "*Solid Section, elset=BLOCK, material=CFRP, orientation=SPH\n")
    assert "SYSTEM=SPHERICAL is unsupported by ccx" in rep.text()
    assert "*ORIENTATION, SYSTEM=SPHERICAL written rectangular" in conv.reduced_physics


def test_spherical_orientation_on_continuum_shells():
    # a plain section gets Abaqus' axes per element (the stack direction radial), composite
    # plies their own: no element reads the rectangular card, so it loses nothing
    deck = ("*Node\n" + SPHERE_PATCH_NODES + "*Element, type=SC8R, elset=CAP\n1, 1, 4, 5, 2, 11, 14, 15, 12\n"
            "2, 2, 5, 6, 3, 12, 15, 16, 13\n" + COMPOSITE_MAT + SPH_ORIENTATION)
    s, c = math.sin(math.radians(5.0)), math.cos(math.radians(5.0))
    body, conv, rep = convert_str(deck + "*Shell Section, elset=CAP, material=CFRP, orientation=SPH\n0.02\n")
    vals = [float(x) for x in _card_at(body, "*DISTRIBUTION, NAME=CAP_AXES")[0].split(",")]
    assert vals[0] == 1 and max(abs(x - y) for x, y in zip(vals[1:4], (-s, c, 0.0))) < 1e-9
    assert "no element reads it" in rep.text() and conv.reduced_physics == ["element SC8R -> C3D8I"]
    body, conv, rep = convert_str(deck + "*Shell Section, elset=CAP, composite, orientation=SPH\n"
                                  "1., 3, CFRP, 0.\n1., 3, CFRP, 90.\n")
    vals = [float(x) for x in _card_at(body, "*DISTRIBUTION, NAME=CAP_PLY1_AXES")[0].split(",")]
    assert max(abs(x - y) for x, y in zip(vals[1:4], (-s, c, 0.0))) < 1e-9
    assert "no element reads it" in rep.text()
    assert conv.reduced_physics == ["element SC8R / SC6R composite continuum shells -> one C3D8I / C3D6 solid per ply"]


ISO_STEEL = "*Material, name=STEEL\n*Elastic\n210000., 0.3\n"
DEFORMATION_STEEL = "*Material, name=STEEL\n*Deformation Plasticity\n210000., 0.3, 250., 5., 0.5\n"


def test_isotropic_sections_lose_nothing_on_a_spherical_orientation():
    # ccx 2.23 gives an isotropic section the same results on any axes (probed on C3D8, C3D8I,
    # C3D8R, C3D20R, S4R, M3D4), but prints its element stresses in them: NaN on the rectangular
    # stand-in of a sphere centred at the origin, so the card becomes the global axes
    block = "*Node\n" + "".join(f"{101 + k}, {k % 2}., {k // 2 % 2}., {2 + k // 4}.\n" for k in range(8)) + \
        "*Element, type=C3D8, elset=BLOCK\n9, 101, 102, 104, 103, 105, 106, 108, 107\n"
    solid = "*Solid Section, elset=BLOCK, material=STEEL, orientation=SPH\n"
    head = "*ORIENTATION, NAME=SPH, SYSTEM=RECTANGULAR"
    body, conv, rep = convert_str(block + ISO_STEEL + SPH_ORIENTATION + solid)
    assert _card(body, head) == ["1., 0., 0., 0., 1., 0."] and "ORIENTATION=SPH" in body
    assert not conv.reduced_physics and "written as the global axes" in rep.text()
    # ccx's *DEFORMATION PLASTICITY depends on the axes (CalculiX issue #160): its section reads none;
    # initial stresses, which Abaqus reads in the orientation's axes, are written in global ones
    for extra in ("", "*Initial Conditions, type=STRESS\n9, 1., 0., 0., 0., 0., 0.\n"):
        for mat in (DEFORMATION_STEEL, ISO_STEEL):
            body, conv, _ = convert_str(block + mat + SPH_ORIENTATION + solid + extra)
            assert _card(body, head) == ["1., 0., 0., 0., 1., 0."] and not conv.reduced_physics
            assert ("ORIENTATION=SPH" in body) == (mat == ISO_STEEL)
    # an orthotropic section and a spring use the axes: reduced physics, the card as before
    for deck in (block + COMPOSITE_MAT + SPH_ORIENTATION + solid.replace("STEEL", "CFRP"),
                 block + ISO_STEEL + SPH_ORIENTATION + solid + "*Element, type=SPRINGA, elset=SP\n19, 101, 108\n"
                 "*Spring, elset=SP, orientation=SPH\n\n10.\n"):
        body, conv, _ = convert_str(deck)
        assert _card(body, head) == ["0., 0., 0., 0., 0., 1."]
        assert conv.reduced_physics == ["*ORIENTATION, SYSTEM=SPHERICAL written rectangular"]
    # isotropic shells, membranes and continuum shells (stacked along the orientation, as in
    # Abaqus' LE3 hemisphere) alike, also beside orthotropic shells with their own directions
    cap = "*Node\n" + "".join(ln + "\n" for ln in SPHERE_PATCH_NODES.splitlines()[:6]) + \
        "*Element, type=S4R, elset=CAP\n1, 1, 4, 5, 2\n2, 2, 5, 6, 3\n"
    shell = "*Shell Section, elset=CAP, material=STEEL, orientation=SPH\n0.02\n"
    for deck in (cap + ISO_STEEL + SPH_ORIENTATION + shell,
                 cap.replace("S4R", "M3D4") + ISO_STEEL + SPH_ORIENTATION + shell.replace("Shell", "Membrane")):
        body, conv, _ = convert_str(deck)
        assert _card(body, head) == ["1., 0., 0., 0., 1., 0."] and not conv.reduced_physics
    body, conv, rep = convert_str(cap + COMPOSITE_MAT + SPH_ORIENTATION + shell.replace("STEEL", "CFRP")
                                  + block + ISO_STEEL + solid)
    assert _card(body, head) == ["1., 0., 0., 0., 1., 0."] and not conv.reduced_physics
    assert "element by element" in rep.text() and "no direction dependence" in rep.text()
    sc = ("*Node\n" + SPHERE_PATCH_NODES + "*Element, type=SC8R, elset=CAP\n1, 1, 4, 5, 2, 11, 14, 15, 12\n"
          "2, 2, 5, 6, 3, 12, 15, 16, 13\n" + ISO_STEEL + SPH_ORIENTATION
          + "*Shell Section, elset=CAP, material=STEEL, orientation=SPH, stack direction=ORIENTATION\n0.02\n")
    body, conv, _ = convert_str(sc)
    assert "*SOLID SECTION, ELSET=CAP, MATERIAL=STEEL, ORIENTATION=SPH" in body
    assert _card(body, head) == ["1., 0., 0., 0., 1., 0."] and conv.reduced_physics == ["element SC8R -> C3D8I"]
    # a card no section uses loses nothing either
    _, conv, rep = convert_str(block + ISO_STEEL + SPH_ORIENTATION + solid.replace(", orientation=SPH", ""))
    assert not conv.reduced_physics and "no card uses it" in rep.text()


def test_isotropic_sections_lose_nothing_by_a_dropped_cylindrical_rotation():
    # ccx refuses a rotation line on a cylindrical system: an isotropic section loses nothing by
    # it, nor a *DEFORMATION PLASTICITY one, which reads no orientation in ccx (CalculiX issue
    # #160), but an orthotropic section its directions; a cylindrical *DISTRIBUTION alike
    sec = "*Solid Section, elset=EALL, material=STEEL, orientation=CYL\n"
    plain = "*Orientation, name=CYL, system=CYLINDRICAL\n0., 0., 0., 0., 0., 1.\n1, 30.\n"
    for cyl in (plain, "*Distribution, name=D, location=ELEMENT, table=T\n, 0., 0., 0., 0., 0., 1.\n"
                       "*Distribution Table, name=T\ncoord3D, coord3D\n*Orientation, name=CYL, system=CYLINDRICAL\nD\n1, 30.\n"):
        for mat in (ISO_STEEL, DEFORMATION_STEEL):
            body, conv, _ = convert_str(HEX + mat + cyl + sec)
            assert not conv.reduced_physics and "1, 30." not in body
            assert ("*SOLID SECTION, ELSET=EALL, MATERIAL=STEEL" in body.splitlines()) == (mat == DEFORMATION_STEEL)
        _, conv, _ = convert_str(HEX + COMPOSITE_MAT.replace("CFRP", "STEEL") + cyl + sec)
        assert conv.reduced_physics == ["*ORIENTATION additional rotation on a non-rectangular system dropped"]
    assert "no direction dependence lose nothing" in convert_str(HEX + ISO_STEEL + plain + sec)[2].text()


TURNED_ORIENTATION = "*Orientation, name=OR\n0.8, 0.6, 0., -0.36, 0.48, 0.8\n"
DP_FLAG = "*DEFORMATION PLASTICITY on an orientation (CalculiX issue #160)"


def test_deformation_plasticity_sections_name_no_orientation():
    # ccx 2.23's *DEFORMATION PLASTICITY depends on an orientation's axes (CalculiX issue #160: up
    # to 84 % off on turned ones, a hang on zero ones), Abaqus' isotropic law does not: its solid,
    # shell, membrane and continuum-shell sections and composite plies name none in ccx
    sec = "*Solid Section, elset=EALL, material=STEEL, orientation=OR\n"
    body, conv, rep = convert_str(HEX + DEFORMATION_STEEL + TURNED_ORIENTATION + sec)
    assert "*SOLID SECTION, ELSET=EALL, MATERIAL=STEEL" in body.splitlines()
    assert not conv.reduced_physics and "CalculiX issue #160" in rep.text() and "in global axes" in rep.text()
    quad = "*Node\n1, 0., 0., 0.\n2, 1., 0., 0.\n3, 1., 1., 0.\n4, 0., 1., 0.\n*Element, type={}, elset=PLATE\n1, 1, 2, 3, 4\n"
    for kw, typ in (("Shell", "S4R"), ("Membrane", "M3D4")):
        body, conv, _ = convert_str(quad.format(typ) + DEFORMATION_STEEL + TURNED_ORIENTATION
                                    + f"*{kw} Section, elset=PLATE, material=STEEL, orientation=OR\n0.1\n")
        assert f"*{kw.upper()} SECTION, ELSET=PLATE, MATERIAL=STEEL" in body.splitlines()
        assert not conv.reduced_physics
    body, conv, _ = convert_str(HEX.replace("C3D8", "SC8R") + DEFORMATION_STEEL + TURNED_ORIENTATION
                                + "*Shell Section, elset=EALL, material=STEEL, orientation=OR\n1.\n")
    assert "*SOLID SECTION, ELSET=EALL, MATERIAL=STEEL" in body.splitlines() and DP_FLAG not in conv.reduced_physics
    # a ply of it names the global axes, as ccx would give it the previous ply's orientation
    s8r = ("*Node\n1, 0., 0., 0.\n2, 1., 0., 0.\n3, 1., 1., 0.\n4, 0., 1., 0.\n5, 0.5, 0., 0.\n6, 1., 0.5, 0.\n"
           "7, 0.5, 1., 0.\n8, 0., 0.5, 0.\n*Element, type=S8R, elset=PLATE\n1, 1, 2, 3, 4, 5, 6, 7, 8\n")
    for ori in ("*Orientation, name=OR\n1., 0., 0., 0., 1., 0.\n3, 0.\n", TURNED_ORIENTATION):
        body, conv, _ = convert_str(s8r + DEFORMATION_STEEL + COMPOSITE_MAT + ori
                                    + "*Shell Section, elset=PLATE, composite, orientation=OR\n"
                                      "0.1, 3, STEEL, 30.\n0.1, 3, CFRP, 30.\n")
        plies = [ln for ln in body.splitlines() if ln.startswith("0.1, , ")]
        assert len(plies) == 2 and plies[0] == "0.1, , STEEL, ABQ2CCX_OR0" and not plies[1].endswith("OR0")
        assert DP_FLAG not in conv.reduced_physics
    body, conv, _ = convert_str(HEX.replace("C3D8", "SC8R") + DEFORMATION_STEEL + COMPOSITE_MAT
                                + "*Shell Section, elset=EALL, composite\n0.5, 3, STEEL, 0.\n0.5, 3, CFRP, 90.\n")
    solids = [ln for ln in body.splitlines() if ln.startswith("*SOLID SECTION")]
    assert len(solids) == 2 and "ORIENTATION" not in solids[0] and "MATERIAL=CFRP, ORIENTATION=" in solids[1]
    # with an option that depends on the axes the orientation stays: reduced physics
    body, conv, _ = convert_str(HEX + DEFORMATION_STEEL + "*Expansion, type=ORTHO\n1e-5, 2e-5, 3e-5\n"
                                + TURNED_ORIENTATION + sec)
    assert "*SOLID SECTION, ELSET=EALL, MATERIAL=STEEL, ORIENTATION=OR" in body.splitlines()
    assert DP_FLAG in conv.reduced_physics


DP_SMALL = "*DEFORMATION PLASTICITY in a small-strain step (ccx 2.23 runs it under NLGEOM)"
DP_SECTION = "*Solid Section, elset=EALL, material=STEEL\n"


def _steps(body):
    return [ln for ln in body.splitlines() if ln.startswith("*STEP")]


def test_deformation_plasticity_in_small_strain_steps_is_reduced_physics():
    # ccx 2.23 switches NLGEOM on when it reads *DEFORMATION PLASTICITY and computes the law in the
    # logarithmic strain and the Cauchy stress (probed), Abaqus in the small strain without NLGEOM;
    # with an explicit NLGEOM=NO ccx reads the small strain as a Green-Lagrange one: dropped
    static = "*Static\n0.1, 1.\n*Cload\n2, 1, 10.\n*End Step\n"
    for step in ("*Step\n", "*Step, nlgeom=NO\n", "*Step, perturbation\n"):
        body, conv, rep = convert_str(HEX + DEFORMATION_STEEL + DP_SECTION + step + static)
        assert _steps(body) == ["*STEP"] and conv.reduced_physics == [DP_SMALL]
        assert "logarithmic strain and the Cauchy stress" in rep.text()
        assert ("Each NLGEOM=NO is dropped" in rep.text()) == ("NO" in step)
    # under NLGEOM, which stays on for the later steps in Abaqus, ccx's law is Abaqus'
    body, conv, _ = convert_str(HEX + DEFORMATION_STEEL + DP_SECTION + "*Step, nlgeom\n" + static
                                + "*Step, nlgeom=NO\n" + static)
    assert _steps(body) == ["*STEP, NLGEOM", "*STEP"] and not conv.reduced_physics
    # a frequency step from the unloaded state takes the elastic stiffness in both
    _, conv, _ = convert_str(HEX + DEFORMATION_STEEL + DP_SECTION + "*Step\n*Frequency\n5\n*End Step\n")
    assert not conv.reduced_physics
    # other materials keep NLGEOM=NO
    body, conv, _ = convert_str(HEX + ISO_STEEL + DP_SECTION + "*Step, nlgeom=NO\n" + static)
    assert _steps(body) == ["*STEP, NLGEOM=NO"] and not conv.reduced_physics
    # ... also beside a *DEFORMATION PLASTICITY material nothing uses: it is commented out, as
    # ccx would switch NLGEOM on for the whole model on reading it
    spare = DEFORMATION_STEEL.replace("STEEL", "SPARE") + "*Density\n7.8e-9\n"
    body, conv, rep = convert_str(HEX + ISO_STEEL + spare + DP_SECTION + "*Step, nlgeom=NO\n" + static)
    assert _steps(body) == ["*STEP, NLGEOM=NO"] and not conv.reduced_physics
    assert "** *MATERIAL, NAME=SPARE" in body and "** *DENSITY" in body and "*ELASTIC" in body.splitlines()
    assert "material SPARE: no card uses it" in rep.text() and rep.n_commented == 3
    # the NLGEOM thermal-expansion checks see ccx's NLGEOM
    dp = ("*Element, type=C3D8, elset=DP\n2, 1, 2, 3, 4, 5, 6, 7, 8\n" + DEFORMATION_STEEL
          + "*Solid Section, elset=DP, material=STEEL\n")
    assert not nlgeom_expansion_warnings(ORTHO_EXPANSION, TURNED_30, ", orientation=T", "*Step\n*Static\n")
    assert len(nlgeom_expansion_warnings(ORTHO_EXPANSION, TURNED_30 + dp, ", orientation=T",
                                         "*Step\n*Static\n")) == 1


def _ic_values(body, head="*INITIAL CONDITIONS, TYPE=STRESS"):
    """{(element, integration point): [values]} of the live card ``head``."""
    return {(int(r[0]), int(r[1])): [float(x) for x in r[2:]]
            for r in (ln.split(", ") for ln in _card(body, head))}


def test_initial_stress_and_plastic_strain_turned_into_global_axes():
    # Abaqus reads them in the axes of the element's orientation (2017 Keywords *INITIAL
    # CONDITIONS), ccx 2.23 in global ones (probed): one rotation per element on a rectangular
    # system; a plastic strain's engineering shear also halved, ccx reading tensor components
    sec = "*Solid Section, elset=EALL, material=STEEL, orientation=OR\n"
    quarter = "*Orientation, name=OR\n0., 1., 0., -1., 0., 0.\n"        # local 1 = global y
    body, conv, rep = convert_str(HEX + ISO_STEEL + quarter + sec
                                  + "*Initial Conditions, type=STRESS\nEALL, 100., 0., 0., 0., 0., 0.\n")
    assert _card(body, "*INITIAL CONDITIONS, TYPE=STRESS") == [f"1, {k}, 0., 100., 0., 0., 0., 0." for k in range(1, 9)]
    assert not conv.reduced_physics and "written in global axes" in rep.text()
    body, conv, rep = convert_str(HEX + ISO_STEEL + quarter + sec
                                  + "*Initial Conditions, type=PLASTIC STRAIN\nEALL, 0., 0., 0., 0.002, 0., 0.\n")
    assert _card(body, "*INITIAL CONDITIONS, TYPE=PLASTIC STRAIN")[0] == "1, 1, 0., 0., 0., -0.001, 0., 0."
    frame = A.orientation_frame((0.8, 0.6, 0.), (-0.36, 0.48, 0.8), "RECTANGULAR", (0., 0., 0.), None)[0]
    body, conv, _ = convert_str(HEX + ISO_STEEL + TURNED_ORIENTATION + sec
                                + "*Initial Conditions, type=STRESS\nEALL, 100., -40., 25., 30., -20., 15.\n")
    want = A.tensor_to_global(frame, [100., -40., 25., 30., -20., 15.])
    got = _ic_values(body)
    assert len(got) == 8 and all(_close(v, want, 1e-9) for v in got.values()) and not conv.reduced_physics
    # a *DISTRIBUTION gives each element its own axes: element 2 turned, element 1 on the default line
    two = HEX + "*NODE\n9, 2.,0.,0.\n10, 2.,1.,0.\n11, 2.,0.,1.\n12, 2.,1.,1.\n*ELEMENT, TYPE=C3D8, ELSET=EALL\n" \
        "2, 2,9,10,3,6,11,12,7\n"
    dist = ("*Distribution, name=D, location=ELEMENT, table=T\n, 1., 0., 0., 0., 1., 0.\n2, 0., 1., 0., -1., 0., 0.\n"
            "*Distribution Table, name=T\ncoord3D, coord3D\n*Orientation, name=OR\nD\n")
    body, conv, _ = convert_str(two + ISO_STEEL + dist + sec
                                + "*Initial Conditions, type=STRESS\nEALL, 100., 0., 0., 0., 0., 0.\n")
    rows = _card(body, "*INITIAL CONDITIONS, TYPE=STRESS")
    assert rows[0] == "1, 1, 100., 0., 0., 0., 0., 0." and rows[8] == "2, 1, 0., 100., 0., 0., 0., 0."
    assert not conv.reduced_physics
    # a cylindrical system turns at each of ccx's integration points: a hoop stress on a box at
    # x = 1 .. 2, y = 0 .. 1 about the z axis
    box = HEX.replace("1, 0.,0.,0.", "1, 1.,0.,0.").replace("2, 1.,0.,0.", "2, 2.,0.,0.").replace(
        "3, 1.,1.,0.", "3, 2.,1.,0.").replace("4, 0.,1.,0.", "4, 1.,1.,0.").replace(
        "5, 0.,0.,1.", "5, 1.,0.,1.").replace("6, 1.,0.,1.", "6, 2.,0.,1.").replace(
        "7, 1.,1.,1.", "7, 2.,1.,1.").replace("8, 0.,1.,1.", "8, 1.,1.,1.")
    cyl = "*Orientation, name=OR, system=CYLINDRICAL\n0., 0., 0., 0., 0., 1.\n"
    for typ, g in (("C3D8", 0.5 / math.sqrt(3)), ("C3D8R", 0.0)):
        body, conv, _ = convert_str(box.replace("C3D8", typ) + ISO_STEEL + cyl + sec
                                    + "*Initial Conditions, type=STRESS\nEALL, 0., 100., 0., 0., 0., 0.\n")
        got = _ic_values(body)
        pts = [(1.5 + a, 0.5 + b) for _c in (0, 1) for b in (-g, g) for a in (-g, g)] if g else [(1.5, 0.5)]
        assert len(got) == len(pts) and not conv.reduced_physics
        for k, (x, y) in enumerate(pts, 1):
            th = math.atan2(y, x)
            assert _close(got[(1, k)], [100 * math.sin(th) ** 2, 100 * math.cos(th) ** 2, 0.,
                                        -100 * math.sin(th) * math.cos(th), 0., 0.], 1e-9)
    # a plane-strain element with its axis 3 normal to the plane turns in it, else reduced physics
    sq = "*Node\n1, 0., 0.\n2, 1., 0.\n3, 1., 1.\n4, 0., 1.\n*Element, type=CPE4, elset=EALL\n1, 1, 2, 3, 4\n"
    plane = f"*Orientation, name=OR\n{math.cos(math.radians(30))}, 0.5, 0., -0.5, {math.cos(math.radians(30))}, 0.\n"
    psec = sec.replace("orientation=OR\n", "orientation=OR\n1.\n")
    ic = "*Initial Conditions, type=STRESS\nEALL, 100., 0., 0., 0.\n"
    body, conv, _ = convert_str(sq + ISO_STEEL + plane + psec + ic)
    assert _close(_ic_values(body)[(1, 1)], [75., 25., 0., 25 * math.sqrt(3), 0., 0.], 1e-9)
    assert not conv.reduced_physics
    flag = ["*INITIAL CONDITIONS, TYPE=STRESS in an orientation's axes, not turned"]
    body, conv, rep = convert_str(sq + ISO_STEEL + TURNED_ORIENTATION + psec + ic)
    assert conv.reduced_physics == flag and "not normal to the model plane" in rep.text()
    assert _card(body, "*INITIAL CONDITIONS, TYPE=STRESS")[0] == "1, 1, 100., 0., 0., 0."
    # axes undefined at an integration point (on a cylindrical system's axis) and unknown axes:
    # the values as given, reduced physics
    on_axis = "*Orientation, name=OR, system=CYLINDRICAL\n0.5, 0.5, 0., 0.5, 0.5, 1.\n"
    for deck, why in ((HEX.replace("C3D8", "C3D8R") + ISO_STEEL + on_axis + sec, "undefined at an integration point"),
                      (HEX + ISO_STEEL + "*Orientation, name=OR, definition=OFFSET TO NODES\n1, 2, 4\n" + sec,
                       "are not known")):
        body, conv, rep = convert_str(deck + "*Initial Conditions, type=STRESS\nEALL, 100., 0., 0., 0., 0., 0.\n")
        assert flag[0] in conv.reduced_physics and why in rep.text()
        assert _card(body, "*INITIAL CONDITIONS, TYPE=STRESS")[0] == "1, 1, 100., 0., 0., 0., 0., 0."


def test_initial_stress_on_continuum_shells_in_their_shell_axes():
    # Abaqus' continuum shells have the components 11, 22, 12 (2017 "Continuum shell element
    # library"), which it reads in the shell's material directions with or without an orientation:
    # 1, 2 on the mid-surface (the orientation projected, else global X, or Z where X is the
    # normal), 3 the stack direction; ccx 2.23 reads xx, yy, zz, xy, xz, yz on its C3D8I / C3D6 in
    # global axes (probed), so they are written in that form, turned once per element
    full = [100., -40., 0., 30., 0., 0.]              # S11, S22, S12 in ccx's order
    ic = "*Initial Conditions, type=STRESS\nEALL, 100., -40., 30.\n"
    sec = "*Shell Section, elset=EALL, material=STEEL\n1.\n"
    sc8r = HEX.replace("C3D8", "SC8R")
    flag = "*INITIAL CONDITIONS, TYPE=STRESS in a continuum shell's axes, not turned"
    # in the x-y plane, stacked up z: Abaqus' axes are the global ones; S12 is ccx's fourth value
    body, conv, rep = convert_str(sc8r + ISO_STEEL + sec + ic)
    assert _card(body, "*INITIAL CONDITIONS, TYPE=STRESS") == [f"1, {k}, 100., -40., 0., 30., 0., 0."
                                                               for k in range(1, 9)]
    assert conv.reduced_physics == ["element SC8R -> C3D8I"] and "TYPE=STRESS on continuum shells" in rep.text()
    body, conv, rep = convert_str(sc8r + ISO_STEEL + sec + "*Initial Conditions, type=STRESS\nEALL, 100, -40, 0\n")
    assert _card(body, "*INITIAL CONDITIONS, TYPE=STRESS")[0] == "1, 1, 100, -40, 0"    # as written
    assert "TYPE=STRESS on continuum shells" not in rep.text()
    # values past the third are not Abaqus' components: left out, warned
    body, conv, rep = convert_str(sc8r + ISO_STEEL + sec + "*Initial Conditions, type=STRESS\n"
                                  "EALL, 100., -40., 30., 7., 8., 9.\n")
    assert _card(body, "*INITIAL CONDITIONS, TYPE=STRESS")[0] == "1, 1, 100., -40., 0., 30., 0., 0."
    assert "values past the third left out" in rep.text()

    def turned(deck, frame, head="*INITIAL CONDITIONS, TYPE=STRESS", vals=full):
        body, conv, rep = convert_str(deck)
        got = _ic_values(body, head)
        want = A.tensor_to_global(frame, vals)
        assert got and all(_close(v, want, 1e-9) for v in got.values()), (got, want)
        assert not [r for r in conv.reduced_physics if "INITIAL" in r]
        return got, rep
    # stacked down z (the top face listed first): direction 2 = -y, 3 = -z
    down = sc8r.replace("1, 1,2,3,4,5,6,7,8", "1, 5,6,7,8,1,2,3,4")
    got, rep = turned(down + ISO_STEEL + sec + ic, ((1., 0., 0.), (0., -1., 0.), (0., 0., -1.)))
    assert got[(1, 1)] == [100., -40., 0., -30., 0., 0.] and len(got) == 8
    assert "in the shell's material directions, also without an orientation" in rep.text()
    # a plate in the y-z plane (normal x): global Z projected is direction 1, 2 = x cross z = -y
    yz = sc8r.replace("2, 1.,0.,0.", "2, 0.,1.,0.").replace("3, 1.,1.,0.", "3, 0.,1.,1.").replace(
        "4, 0.,1.,0.", "4, 0.,0.,1.").replace("5, 0.,0.,1.", "5, 1.,0.,0.").replace(
        "6, 1.,0.,1.", "6, 1.,1.,0.").replace("8, 0.,1.,1.", "8, 1.,0.,1.")
    got, _ = turned(yz + ISO_STEEL + sec + ic, ((0., 0., 1.), (0., -1., 0.), (1., 0., 0.)))
    assert _close(got[(1, 1)], [0., -40., 100., 0., 0., -30.], 1e-9)
    # STACK DIRECTION=1: the element's first isoparametric direction is the normal (here global x)
    turned(sc8r + ISO_STEEL + sec.replace("material=STEEL", "material=STEEL, stack direction=1") + ic,
           ((0., 0., 1.), (0., -1., 0.), (1., 0., 0.)))
    # an orientation, projected onto the mid-surface: without a rotation line Abaqus turns it about
    # axis 1 and projects axis 2 (shell_local_axes)
    frame = A.orientation_frame((0.8, 0.6, 0.), (-0.36, 0.48, 0.8), "RECTANGULAR", (0., 0., 0.), None)[0]
    d1, d2 = A.shell_local_axes((0., 0., 1.), frame, None)
    oriented = sec.replace("material=STEEL", "material=STEEL, orientation=OR")
    turned(sc8r + ISO_STEEL + TURNED_ORIENTATION + oriented + ic, (d1, d2, (0., 0., 1.)))
    d1, d2 = A.shell_local_axes((0., 0., 1.), frame, 3)
    turned(sc8r + ISO_STEEL + TURNED_ORIENTATION + "3, 0.\n" + oriented + ic, (d1, d2, (0., 0., 1.)))
    # an SC6R wedge (stacked from nodes 1-3 to 4-6), its two points
    wedge = ("*Node\n1, 0., 0., 0.\n2, 0., 1., 0.\n3, 0., 0., 1.\n4, 0.1, 0., 0.\n5, 0.1, 1., 0.\n"
             "6, 0.1, 0., 1.\n*Element, type=SC6R, elset=EALL\n1, 1, 2, 3, 4, 5, 6\n")
    got, _ = turned(wedge + ISO_STEEL + sec + ic, ((0., 0., 1.), (0., -1., 0.), (1., 0., 0.)))
    assert len(got) == 2
    # a plastic strain's engineering shear is halved first
    turned(down + ISO_STEEL + "*Plastic\n250., 0.\n" + sec + "*Initial Conditions, type=PLASTIC STRAIN\n"
           "EALL, 0.004, -0.001, 0.002\n", ((1., 0., 0.), (0., -1., 0.), (0., 0., -1.)),
           "*INITIAL CONDITIONS, TYPE=PLASTIC STRAIN", [0.004, -0.001, 0., 0.001, 0., 0.])
    # axes the converter cannot form: the values as given, reduced physics
    body, conv, rep = convert_str(down + ISO_STEEL + "*Orientation, name=OR, definition=OFFSET TO NODES\n1, 2, 4\n"
                                  + oriented + ic)
    assert flag in conv.reduced_physics and "cannot form their shell axes" in rep.text()
    assert _card(body, "*INITIAL CONDITIONS, TYPE=STRESS")[0] == "1, 1, 100., -40., 0., 30., 0., 0."
    # a *SHELL GENERAL SECTION takes section forces and moments per unit width: left out
    body, conv, rep = convert_str(down + ISO_STEEL + "*Shell General Section, elset=EALL, material=STEEL\n1.\n" + ic)
    assert "*INITIAL CONDITIONS, TYPE=STRESS on a *SHELL GENERAL SECTION (section forces)" in conv.reduced_physics
    assert "section forces and moments per unit width" in rep.text() and "\n*INITIAL CONDITIONS" not in body


def test_initial_stress_on_split_continuum_shells_in_each_plys_axes():
    # a composite continuum shell runs as one solid per ply: a record by element set or by the
    # element's label reaches every ply solid, each turned by its own ply axes (the section's
    # directions turned by the layer angle about the stack normal); also where a deformation
    # plasticity ply's solid section names no orientation, Abaqus' axes still apply
    full = [100., -40., 0., 30., 0., 0.]
    down = HEX.replace("C3D8", "SC8R").replace("1, 1,2,3,4,5,6,7,8", "1, 5,6,7,8,1,2,3,4")
    n = (0., 0., -1.)
    plies = {0.: ((1., 0., 0.), (0., -1., 0.), n), 90.: ((0., -1., 0.), (-1., 0., 0.), n)}
    layup = "*Shell Section, elset=EALL, composite\n0.5, 3, CFRP, 0.\n0.5, 3, {}, 90.\n"
    for tok in ("EALL", "1"):
        for second in ("CFRP", "STEEL"):
            body, conv, rep = convert_str(down + COMPOSITE_MAT + DEFORMATION_STEEL + layup.format(second)
                                          + f"*Initial Conditions, type=STRESS\n{tok}, 100., -40., 30.\n")
            got = _ic_values(body)
            assert {e for e, _k in got} == {1, 2} and len(got) == 16
            assert all(_close(got[(1, k)], A.tensor_to_global(plies[0.], full), 1e-9) for k in range(1, 9))
            assert all(_close(got[(2, k)], A.tensor_to_global(plies[90.], full), 1e-9) for k in range(1, 9))
            assert not [r for r in conv.reduced_physics if "INITIAL" in r]
            if second == "STEEL":                          # its solid section names no orientation
                assert any(ln.startswith("*SOLID SECTION") and "MATERIAL=STEEL" in ln and "ORIENTATION" not in ln
                           for ln in body.splitlines())
    # state variables too: the element's label names all its ply solids
    body, _, _ = convert_str(down + COMPOSITE_MAT + "*Depvar\n1\n" + layup.format("CFRP")
                             + "*Initial Conditions, type=SOLUTION\n1, 5.\n")
    assert {ln.split(",")[0] for ln in _card(body, "*INITIAL CONDITIONS, TYPE=SOLUTION")} == {"1", "2"}
    # a split left out (over --max-ply-elements): no ply axes, the values not turned, reduced physics
    body, conv, rep = convert_str(down + COMPOSITE_MAT + layup.format("CFRP")
                                  + "*Initial Conditions, type=STRESS\nEALL, 100., -40., 30.\n", max_ply_elements=1)
    assert "*INITIAL CONDITIONS, TYPE=STRESS in a continuum shell's axes, not turned" in conv.reduced_physics
    assert "not split into ply solids" in rep.text()
    assert _card(body, "*INITIAL CONDITIONS, TYPE=STRESS")[0] == "1, 1, 100., -40., 0., 30., 0., 0."


def test_initial_conditions_on_rebars_and_section_points_commented_out():
    # ccx has no rebars and no section points: an Abaqus record (element, rebar name, value) stops
    # ccx, one at a section point (element, point, values) is read with the point number as the
    # first component (probed) — both commented out, reduced physics
    sec = "*Solid Section, elset=EALL, material=STEEL\n"
    for opt, rec, label in (("REBAR", "EALL, BAR, 100.", "*INITIAL CONDITIONS, TYPE=STRESS, REBAR"),
                            ("SECTION POINTS", "EALL, 1, 100., 0., 0., 0., 0., 0.",
                             "*INITIAL CONDITIONS, TYPE=STRESS, SECTION POINTS")):
        body, conv, rep = convert_str(HEX + ISO_STEEL + sec + f"*Initial Conditions, type=STRESS, {opt}\n{rec}\n")
        assert "*INITIAL CONDITIONS" not in [ln.split(",")[0] for ln in body.splitlines()]
        assert f"** *INITIAL CONDITIONS, TYPE=STRESS, {opt}" in body and label in conv.reduced_physics


def test_ccx_integration_points_where_ccx_prints_them():
    # ccx 2.23's *EL PRINT, COORD on one distorted element of each type (curved edges for the
    # quadratic ones): its integration points in its order, at which initial conditions on a
    # cylindrical or spherical orientation are turned
    def warp(x, y, z=None):
        if z is None:
            return 2.0 + x + 0.15 * y * y, 3.0 + 0.8 * y + 0.12 * x * x, 0.0
        return (2.0 + x + 0.15 * y * y + 0.1 * z, 3.0 + 0.8 * y + 0.12 * x * x - 0.05 * z * x,
                1.0 + 0.6 * z + 0.1 * x * y)
    hex8 = [(-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1), (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)]
    hex20 = hex8 + [(0, -1, -1), (1, 0, -1), (0, 1, -1), (-1, 0, -1), (0, -1, 1), (1, 0, 1), (0, 1, 1),
                    (-1, 0, 1), (-1, -1, 0), (1, -1, 0), (1, 1, 0), (-1, 1, 0)]
    tet10 = [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1), (.5, 0, 0), (.5, .5, 0), (0, .5, 0), (0, 0, .5),
             (.5, 0, .5), (0, .5, .5)]
    wed6 = [(0, 0, -1), (1, 0, -1), (0, 1, -1), (0, 0, 1), (1, 0, 1), (0, 1, 1)]
    wed15 = wed6 + [(.5, 0, -1), (.5, .5, -1), (0, .5, -1), (.5, 0, 1), (.5, .5, 1), (0, .5, 1), (0, 0, 0),
                    (1, 0, 0), (0, 1, 0)]
    quad8 = [(-1, -1), (1, -1), (1, 1), (-1, 1), (0, -1), (1, 0), (0, 1), (-1, 0)]
    printed = {
        "C3D20": (hex20, {1: (1.237944, 2.422323, 0.5952420), 14: (2.0, 3.0, 1.0),
                          27: (2.942056, 3.661677, 1.524758)}),
        "C3D15": (wed15, {1: (2.093374, 3.143122, 0.5380198), 5: (2.670833, 3.186667, 1.011111),
                          9: (2.310793, 3.530212, 1.475869)}),
        "C3D10": (tet10, {1: (2.154881, 3.111894, 1.084828), 2: (2.602095, 3.147637, 1.091008),
                          3: (2.203422, 3.469665, 1.091008), 4: (2.199602, 3.108804, 1.353156)}),
        "C3D6": (wed6, {1: (2.325598, 3.316289, 0.6535898), 2: (2.441068, 3.297044, 1.346410)}),
        "CPS8": (quad8, {1: (1.315403, 2.452323), 14: (2.0, 3.0)}),      # in its plane: ccx's layers are off it
    }
    for typ, (ref, want) in printed.items():
        pts = A.ccx_integration_points(typ, [warp(*p) for p in ref])
        assert len(pts) == A.ELEMENT_IP_COUNT[typ]
        assert all(_close(pts[k - 1][:len(w)], w, 2e-6) for k, w in want.items()), typ
    assert A.ccx_integration_points("C3D8", [(0., 0., 0.)] * 4) is None


def test_initial_conditions_in_ccx_component_order():
    # Abaqus orders a plane-stress element's components 11, 22, 12, ccx reads a third value as zz
    # (probed); a plastic strain's shear is engineering in Abaqus, tensor in ccx (probed: xy = 0.01
    # shears a free cube by 0.02); records ccx reads alike stay as written
    sq = "*Node\n1, 0., 0.\n2, 1., 0.\n3, 1., 1.\n4, 0., 1.\n*Element, type=CPS4, elset=EALL\n1, 1, 2, 3, 4\n"
    sec = "*Solid Section, elset=EALL, material=STEEL\n1.\n"
    body, conv, rep = convert_str(sq + ISO_STEEL + sec + "*Initial Conditions, type=STRESS\nEALL, 0., 0., 100.\n")
    assert _card(body, "*INITIAL CONDITIONS, TYPE=STRESS") == [f"1, {k}, 0., 0., 0., 100., 0., 0." for k in range(1, 9)]
    assert not conv.reduced_physics and "third value as zz" in rep.text()
    body, _, _ = convert_str(sq + ISO_STEEL + sec + "*Initial Conditions, type=STRESS\nEALL, 0.0, 50000.0, 0.0,\n")
    assert _card(body, "*INITIAL CONDITIONS, TYPE=STRESS")[0] == "1, 1, 0.0, 50000.0, 0.0"
    plastic = ISO_STEEL + "*Plastic\n250., 0.\n*Solid Section, elset=EALL, material=STEEL\n"
    head = "*INITIAL CONDITIONS, TYPE=PLASTIC STRAIN"
    body, _, rep = convert_str(HEX + plastic + "*Initial Conditions, type=PLASTIC STRAIN\nEALL, 0.004, -0.002, -0.002, 0.003, 0., 0.\n")
    assert _card(body, head)[0] == "1, 1, 0.004, -0.002, -0.002, 0.0015, 0., 0." and "engineering shear" in rep.text()
    body, _, _ = convert_str(HEX + plastic + "*Initial Conditions, type=PLASTIC STRAIN\nEALL, 0.004, -0.002, -0.002\n")
    assert _card(body, head)[0] == "1, 1, 0.004, -0.002, -0.002"


def test_composite_continuum_shells_keep_a_cylindrical_rotation_line():
    # the plies take their axes, rotation applied, from the orientation themselves, so the
    # rotation line ccx refuses on a cylindrical system loses nothing
    pts = [(r, math.radians(a), z) for r in (1.0, 1.1) for z in (0.0, 1.0) for a in (0.0, 30.0, 60.0)]
    nodes = "".join(f"{k + 1}, {r * math.cos(t):.9f}, {r * math.sin(t):.9f}, {z}\n" for k, (r, t, z) in enumerate(pts))
    deck = (f"*Node\n{nodes}*Element, type=SC8R, elset=CYL\n1, 1, 2, 5, 4, 7, 8, 11, 10\n"
            "2, 2, 3, 6, 5, 8, 9, 12, 11\n" + COMPOSITE_MAT
            + "*Orientation, name=C, system=CYLINDRICAL\n0., 0., 0., 0., 0., 1.\n1, 25.\n"
            "*Shell Section, elset=CYL, composite, orientation=C\n1., 3, CFRP, 0.\n1., 3, CFRP, 90.\n")
    body, conv, rep = convert_str(deck)
    assert "the rotation applied" in rep.text() and "not allowed by ccx" not in rep.text()
    assert conv.reduced_physics == ["element SC8R / SC6R composite continuum shells -> one C3D8I / C3D6 solid per ply"]
    t, r = math.radians(15.0), math.radians(25.0)        # the hoop direction turned towards the axis
    vals = [float(x) for x in _card_at(body, "*DISTRIBUTION, NAME=CYL_PLY1_AXES")[0].split(",")]
    want = (-math.sin(t) * math.cos(r), math.cos(t) * math.cos(r), math.sin(r))
    assert max(abs(x - y) for x, y in zip(vals[1:4], want)) < 1e-6
    # the same system as a cylindrical *DISTRIBUTION
    body, conv, rep = convert_str(deck.replace(
        "*Orientation, name=C, system=CYLINDRICAL\n0., 0., 0., 0., 0., 1.\n",
        "*Distribution, name=D, location=ELEMENT, table=T\n, 0., 0., 0., 0., 0., 1.\n"
        "*Distribution Table, name=T\ncoord3D, coord3D\n*Orientation, name=C, system=CYLINDRICAL\nD\n"))
    vals = [float(x) for x in _card_at(body, "*DISTRIBUTION, NAME=CYL_PLY1_AXES")[0].split(",")]
    assert max(abs(x - y) for x, y in zip(vals[1:4], want)) < 1e-6 and "was dropped" not in rep.text()
    assert conv.reduced_physics == ["element SC8R / SC6R composite continuum shells -> one C3D8I / C3D6 solid per ply"]


def test_orientation_axes_are_undefined_on_the_axis():
    # a point on a spherical system's polar axis (also off it by a rounding error) or at its
    # centre, or on a cylindrical system's axis, has no circumferential direction
    sph = lambda p, rot=None: A.orientation_frame((0., 0., 0.), (0., 0., 1.), "SPHERICAL", p, rot)   # noqa: E731
    assert A.frame_defined(*sph((0.0, 2.0, 0.0)))
    assert not any(A.frame_defined(*sph(p)) for p in ((0., 0., 1.), (1.2e-16, 0., -1.), (0., 0., 0.)))
    assert not A.frame_defined(*A.orientation_frame((0., 0., 0.), (1., 1., 1.), "CYLINDRICAL",
                                                    (0.3, 0.3, 0.3 + 1e-12), None))
    # what a shell projects after rotation axis 3, axis 1, is radial there; turned, it is not
    assert A.frame_defined(*sph((0., 0., 1.), (3, 0.0))) and not A.frame_defined(*sph((0., 0., 1.), (3, 30.0)))
    nz = (0.0, 0.0, 1.0)
    assert A.shell_local_axes(nz, *sph((0., 0., 1.))) == A.shell_local_axes(nz)
    assert "its axis 2, which Abaqus projects, is undefined at an element's centre" in \
        A.shell_axes_caveat(nz, *sph((0., 0., 1.)))
    assert "is the shell normal" in A.shell_axes_caveat(nz, *sph((0., 0., 1.), (3, 0.0)))
    # a shell element centred on the pole: the default directions, warned
    deck = ("*Node\n1, -0.1, -0.1, 1.\n2, 0.1, -0.1, 1.\n3, 0.1, 0.1, 1.\n4, -0.1, 0.1, 1.\n"
            "*Element, type=S4R, elset=TOP\n1, 1, 2, 3, 4\n" + COMPOSITE_MAT + SPH_ORIENTATION
            + "*Shell Section, elset=TOP, material=CFRP, orientation=SPH\n0.01\n")
    body, _, rep = convert_str(deck)
    assert _card_at(body, "*ORIENTATION, NAME=ABQ2CCX_AXES1") == ["1, 0, 0, 0, 1, 0"]
    assert "orientation SPH: its axis 2, which Abaqus projects, is undefined at an element's centre" in rep.text()
    # an S4 there, integrated at four points around the pole: their directions part by 90 degrees
    _, conv, rep = convert_str(deck.replace("type=S4R", "type=S4"))
    assert "turns the material directions by up to 90 degrees across an element" in rep.text()
    # stacked along the system's axis 3, which the pole does not define: along direction 3, warned
    cap = ("*Node\n" + "".join(f"{k + 1}, {x}, {y}, {z}\n" for k, (x, y, z) in enumerate(
        (x, y, z) for z in (9.99, 10.01) for x, y in ((-0.1, -0.1), (0.1, -0.1), (0.1, 0.1), (-0.1, 0.1))))
        + "*Element, type=SC8R, elset=TOP\n1, 1, 2, 3, 4, 5, 6, 7, 8\n" + COMPOSITE_MAT + SPH_ORIENTATION
        + "3, 0.\n*Shell Section, elset=TOP, composite, stack direction=ORIENTATION, orientation=SPH\n"
        "1., 3, CFRP, 0.\n1., 3, CFRP, 90.\n")
    _, conv, rep = convert_str(cap)
    assert "orientation 'SPH' has no axis 3 at the centre of an element" in rep.text()
    assert {round(conv.geom.nodes[n][2], 9) for n in conv.geom.nodes if n > 8} == {10.0}


def _sphere_shells(m, rotation="", quad="S4R", tri="S3", section="*Shell Section"):
    """A sphere of radius 1 about the origin meshed along its parallels and meridians (2 m rings
    of 4 m elements, ``tri`` at the poles, ``quad`` elsewhere) of CFRP on SPH_ORIENTATION."""
    nr, na = 2 * m, 4 * m
    nid = lambda i, j: 1 if i == 0 else 2 + (nr - 1) * na if i == nr else 2 + (i - 1) * na + j % na  # noqa: E731
    nodes = "".join(f"{nid(i, j)}, " + ", ".join(f"{x:.12g}" for x in _sph(1.0, 180.0 * i / nr, 360.0 * j / na)) + "\n"
                    for i in range(nr + 1) for j in (range(na) if 0 < i < nr else (0,)))
    tris = [(nid(0, 0), nid(1, j), nid(1, j + 1)) for j in range(na)] + \
        [(nid(nr, 0), nid(nr - 1, j + 1), nid(nr - 1, j)) for j in range(na)]
    quads = [(nid(i, j), nid(i + 1, j), nid(i + 1, j + 1), nid(i, j + 1)) for i in range(1, nr - 1) for j in range(na)]
    elems = f"*Element, type={tri}, elset=SPHERE\n" + "".join(f"{e}, {a}, {b}, {c}\n" for e, (a, b, c) in enumerate(tris, 1))
    elems += f"*Element, type={quad}, elset=SPHERE\n" + "".join(
        f"{e}, " + ", ".join(map(str, q)) + "\n" for e, q in enumerate(quads, len(tris) + 1))
    return (f"*Node\n{nodes}{elems}" + COMPOSITE_MAT + SPH_ORIENTATION + (rotation + "\n" if rotation else "")
            + f"{section}, elset=SPHERE, material=CFRP, orientation=SPH\n0.01\n")


def test_spherical_orientation_turning_across_an_element_is_warned():
    # 30-degree S4 elements: along the parallels the system turns by some 11 degrees within one,
    # which Abaqus follows to its four integration points and ccx takes at the centre
    _, conv, rep = convert_str(_sphere_shells(3, quad="S4"))
    assert re.search(r"its spherical orientation turns the material directions by up to 1[0-9] degrees "
                     r"across an element;", rep.text())
    assert conv.reduced_physics and "spherical orientation at element centres" in conv.reduced_physics[0]
    # 7.5-degree ones: under 4 degrees, no element corner on the poles counting
    _, conv, rep = convert_str(_sphere_shells(12, quad="S4"))
    assert "across an element" not in rep.text() and not conv.reduced_physics
    # S3 and S4R take the directions at their one integration point, the centre, as ccx does
    _, conv, rep = convert_str(_sphere_shells(3, "3, 25."))
    assert "across an element" not in rep.text() and not conv.reduced_physics
    # a flat membrane projects onto its own plane: turned about axis 3, the radial axis 1 Abaqus
    # projects tilts across each facet of 7.5 degrees by some 12 degrees
    _, conv, rep = convert_str(_sphere_shells(12, "3, 25.", "M3D4", "M3D3", "*Membrane Section"))
    assert re.search(r"turns the material directions by up to 1[0-9] degrees across an element", rep.text())


QM8_STRIP = ("*Node\n1, 0., 0., 0.\n2, 0.5, 0., 0.\n3, 1., 0., 0.\n4, 1.5, 0., 0.\n5, 2., 0., 0.\n"
             "6, 0., 0.5, 0.\n8, 1., 0.5, 0.\n10, 2., 0.5, 0.\n11, 0., 1., 0.\n12, 0.5, 1., 0.\n"
             "13, 1., 1., 0.\n14, 1.5, 1., 0.\n15, 2., 1., 0.\n"
             "*Element, type=M3D8R, elset=SKIN\n1, 1, 3, 13, 11, 2, 8, 12, 6\n2, 3, 5, 15, 13, 4, 10, 14, 8\n"
             "*Nset, nset=LEFT\n1, 6, 11\n*Nset, nset=RIGHT\n5, 10, 15\n"
             "*Material, name=M\n*Elastic\n100000., 0.3\n")
QM_STEP = "*Step\n*Static\n*Boundary\nLEFT, 1, 3\n*Cload\nRIGHT, 1, 1.\n*End Step\n"


def _all_equations(body):
    """Every *EQUATION of a converted deck as a list of (node, DOF, coefficient) terms."""
    lines, out, i = body.splitlines(), [], 0
    while i < len(lines):
        if lines[i] == "*EQUATION":
            i += 1
            while i < len(lines) and not lines[i].startswith("*"):
                n, terms = int(lines[i]), []
                i += 1
                while len(terms) < n:
                    f = [x.strip() for x in lines[i].split(",") if x.strip()]
                    terms += [(int(f[k]), int(f[k + 1]), float(f[k + 2])) for k in range(0, len(f), 3)]
                    i += 1
                out.append(terms)
        else:
            i += 1
    return out


def test_quadratic_membranes_become_solids_held_at_their_nodes():
    # ccx 2.23 leaves the mid-thickness node of a quadratic membrane's corner free in each
    # element (M3D8R singular, M3D6 / M3D8 too soft; probed): the converter writes the
    # C3D20R itself, with nodes of its own held at the membrane nodes by *EQUATION
    body, conv, rep = convert_str(QM8_STRIP + "*Membrane Section, elset=SKIN, material=M\n0.01\n" + QM_STEP)
    g = reparse(body)
    assert [g.elements[e][0] for e in (1, 2)] == ["C3D20R", "C3D20R"] and not dangling_refs(g)
    c1, c2 = g.elements[1][1], g.elements[2][1]
    assert not set(c1 + c2) & set(range(1, 16))              # the membrane nodes are in no element
    assert set(c1) & set(c2) == {c1[17], c1[18]} == {c2[16], c2[19]}   # mid nodes of corners 3, 13
    assert g.nodes[c1[0]] == (0.0, 0.0, -0.005) and g.nodes[c1[4]] == (0.0, 0.0, 0.005)
    assert g.nodes[c1[16]] == (0.0, 0.0, 0.0)
    assert _card_at(body, "*SOLID SECTION, ELSET=SKIN, MATERIAL=M") == [] and "TYPE=M3D8R" not in body
    eqs = _all_equations(body)
    hinge = [e for e in eqs if len(e) == 3]
    assert len(hinge) == 2 * 8 * 3 and (c1[0], 1, 1.0) == hinge[0][0] and hinge[0][2] == (1, 1, -2.0)
    assert len([e for e in eqs if len(e) == 2]) == 6 * 3          # corners 1, 3, 5, 11, 13, 15
    # one equation per C3D20R holds its fibres' zero-energy hourglass (the top / bottom nodes)
    hg = [e for e in eqs if len(e) > 3]
    assert len(hg) == 2 and all(t[0] in c1[:16] for t in hg[0]) and hg[0][0][0] in c1[4:8] + c1[12:16]
    assert "Quadratic membranes: 2 element(s) (2 M3D8R -> C3D20R)" in rep.text() and not conv.reduced_physics
    # M3D8 -> C3D20 and M3D6 -> C3D15: no hourglass equation
    body, _, _ = convert_str((QM8_STRIP + "*Membrane Section, elset=SKIN, material=M\n0.01\n" + QM_STEP)
                             .replace("M3D8R", "M3D8"))
    assert "*ELEMENT, TYPE=C3D20\n" in body and max(len(e) for e in _all_equations(body)) == 3
    tri = QM8_STRIP.replace("type=M3D8R, elset=SKIN\n1, 1, 3, 13, 11, 2, 8, 12, 6\n2, 3, 5, 15, 13, 4, 10, 14, 8",
                            "type=M3D6, elset=SKIN\n1, 1, 3, 13, 2, 8, 7\n2, 1, 13, 11, 7, 12, 6")
    tri = tri.replace("8, 1., 0.5, 0.\n", "7, 0.5, 0.5, 0.\n8, 1., 0.5, 0.\n")
    body, _, _ = convert_str(tri + "*Membrane Section, elset=SKIN, material=M\n0.01\n")
    g = reparse(body)
    assert g.elements[1][0] == "C3D15" and len(g.elements[1][1]) == 15 and not dangling_refs(g)


def test_quadratic_membrane_sections_loads_and_output():
    # P on a membrane -> P1 as before (the solid has ccx's own expanded faces); a section on
    # linear and quadratic membranes splits; *NODE FILE at the membrane nodes -> *NODE PRINT
    lin = ("*Node\n21, 0., 3., 0.\n22, 1., 3., 0.\n23, 1., 4., 0.\n24, 0., 4., 0.\n"
           "*Element, type=M3D4, elset=SKIN\n9, 21, 22, 23, 24\n")
    body, conv, rep = convert_str(QM8_STRIP + lin + "*Membrane Section, elset=SKIN, material=M, density=2.\n0.01\n"
                                  "*Step\n*Dynamic\n0.1, 1.\n*Boundary\nLEFT, 1, 3\n*Dload\nSKIN, P, 3.\n"
                                  "*Node File, nset=RIGHT\nU\n*End Step\n")
    # DENSITY= (mass per area) -> a material copy with DENSITY / t, for both forms
    assert "*MEMBRANE SECTION, ELSET=SKIN_MEMBRANE, MATERIAL=M_MEMBRANE_MASS\n0.01\n" in body
    assert _card_at(body, "*SOLID SECTION, ELSET=SKIN_SOLID, MATERIAL=M_MEMBRANE_MASS") == []
    assert "*MATERIAL, NAME=M_MEMBRANE_MASS\n*ELASTIC\n100000., 0.3\n*DENSITY\n200.\n" in body
    g = reparse(body)
    assert g.elsets["SKIN_MEMBRANE"] == [9] and g.elsets["SKIN_SOLID"] == [1, 2] and g.elements[9][0] == "M3D4"
    assert _card_at(body, "*DLOAD") == ["SKIN, P1, 1.5", "ABQ2CCX_TOP_SKIN, P, -1.5"]
    assert _card_at(body, "*SURFACE, NAME=ABQ2CCX_TOP_SKIN") == ["SKIN, S2"]
    assert _card_at(body, "*NODE PRINT, NSET=RIGHT") == ["U"]
    assert "material M_MEMBRANE_MASS, a copy of M" in rep.text() and not conv.reduced_physics
    # thickness from *NODAL THICKNESS
    body, _, _ = convert_str(QM8_STRIP + "*Nodal Thickness\n1, 0.02\n2, 0.02\n3, 0.04\n4, 0.04\n5, 0.04\n6, 0.02\n"
                             "8, 0.04\n10, 0.04\n11, 0.02\n12, 0.02\n13, 0.04\n14, 0.04\n15, 0.04\n"
                             "*Membrane Section, elset=SKIN, material=M, nodal thickness\n")
    g = reparse(body)
    assert g.nodes[g.elements[1][1][4]] == (0.0, 0.0, 0.01) and g.nodes[g.elements[1][1][5]] == (1.0, 0.0, 0.02)
    # no thickness: the element stays ccx's own membrane, warned as reduced physics
    body, conv, rep = convert_str(QM8_STRIP + "*Membrane Section, elset=SKIN, material=M\n\n")
    assert "*ELEMENT, TYPE=M3D8R" in body and "no positive thickness" in rep.text() and conv.reduced_physics


def test_quadratic_membrane_axes_temperatures_and_transforms():
    # the membrane axes path (_shell_axes_rows) carries over: ccx reads a solid's orientation
    # unprojected as it reads a membrane's
    strip = ("*Node\n1, 0., 0., 0.\n2, 0., 0.5, 0.\n3, 0., 1., 0.\n4, 0., 1., 0.5\n5, 0., 1., 1.\n"
             "6, 0., 0.5, 1.\n7, 0., 0., 1.\n8, 0., 0., 0.5\n"
             "*Element, type=M3D8R, elset=SKIN\n1, 1, 3, 5, 7, 2, 4, 6, 8\n" + COMPOSITE_MAT
             + "*Membrane Section, elset=SKIN, material=CFRP\n0.1\n")
    body, _, _ = convert_str(strip)
    assert _card_at(body, "*ORIENTATION, NAME=ABQ2CCX_AXES1") == ["0, 0, 1, 0, -1, 0"]
    assert _card_at(body, "*SOLID SECTION, ELSET=SKIN, MATERIAL=CFRP, ORIENTATION=ABQ2CCX_AXES1") == []
    # temperatures reach the solids' nodes
    body, conv, _ = convert_str(QM8_STRIP + "*Nset, nset=ALL\nLEFT, RIGHT, 2, 3, 4, 8, 12, 13, 14\n"
                                "*Membrane Section, elset=SKIN, material=M\n0.01\n"
                                "*Initial Conditions, type=TEMPERATURE\nALL, 20.\n"
                                "*Step\n*Static\n*Temperature\nALL, 120.\n*End Step\n")
    new = sorted(conv._qmem_copies)
    assert len(new) == 2 * 16 + 6 and set(_card_at(body, "*TEMPERATURE")[1:]) == {f"{m}, 120" for m in new}
    # a *TRANSFORM on membrane nodes: the solids' nodes stay global, and each tie names the
    # transformed node in one local direction (ccx expands each local term into global ones)
    body, conv, _ = convert_str(QM8_STRIP + "*Transform, nset=RIGHT\n0.8, 0.6, 0., -0.6, 0.8, 0.\n"
                                "*Membrane Section, elset=SKIN, material=M\n0.01\n" + QM_STEP)
    assert body.count("*TRANSFORM") == 1
    for eq in _all_equations(body):
        named = [n for n, _, _ in eq if n in (5, 10, 15)]
        assert len(named) == len(set(named)), eq
    hinge5 = [eq for eq in _all_equations(body) if eq[-1][0] == 5 and eq[-1][2] == -2.0]
    assert sorted(eq[-1][1] for eq in hinge5) == [1, 2, 3]          # bottom + top = 2 x node, local axes


def test_tie_on_quadratic_membranes_ties_their_own_nodes():
    # ccx would tie the solids' face nodes, which the converter's *EQUATIONs eliminate (it
    # skips them: 'DOF ... is not active'); the slave becomes the membrane nodes Abaqus ties
    block = ("*Node\n101, 0., 0., -0.5\n102, 1., 0., -0.5\n103, 1., 1., -0.5\n104, 0., 1., -0.5\n"
             "105, 0., 0., -0.005\n106, 1., 0., -0.005\n107, 1., 1., -0.005\n108, 0., 1., -0.005\n"
             "*Element, type=C3D8, elset=BLOCK\n101, 101, 102, 103, 104, 105, 106, 107, 108\n"
             "*Solid Section, elset=BLOCK, material=M\n")
    body, conv, rep = convert_str(QM8_STRIP + block + "*Membrane Section, elset=SKIN, material=M\n0.01\n"
                                  "*Elset, elset=E1\n1\n*Surface, name=MS, type=ELEMENT\nE1, SNEG\n"
                                  "*Surface, name=BS, type=ELEMENT\nBLOCK, S2\n"
                                  "*Tie, name=T1, position tolerance=0.02\nMS, BS\n" + QM_STEP)
    assert _card_at(body, "*SURFACE, NAME=MS_NODES, TYPE=NODE") == ["1", "3", "13", "11", "2", "8", "12", "6"]
    assert _card_at(body, "*TIE, NAME=T1") == ["MS_NODES, BS"] and "node surface MS_NODES" in rep.text()
    assert not conv.reduced_physics


LM4_SKIN = ("*Node\n1, 0., 0., 0.\n2, 1., 0., 0.\n3, 2., 0., 0.\n4, 0., 1., 0.\n5, 1., 1., 0.\n6, 2., 1., 0.\n"
            "101, 0., 0., -0.5\n102, 1., 0., -0.5\n103, 1., 1., -0.5\n104, 0., 1., -0.5\n"
            "105, 0., 0., -0.005\n106, 1., 0., -0.005\n107, 1., 1., -0.005\n108, 0., 1., -0.005\n"
            "*Element, type=M3D4, elset=SKIN\n1, 1, 2, 5, 4\n2, 2, 3, 6, 5\n"
            "*Element, type=C3D8, elset=BLOCK\n101, 101, 102, 103, 104, 105, 106, 107, 108\n"
            "*Nset, nset=LEFT\n1, 4\n*Material, name=M\n*Elastic\n100000., 0.3\n"
            "*Membrane Section, elset=SKIN, material=M\n0.01\n*Solid Section, elset=BLOCK, material=M\n"
            "*Elset, elset=E1\n1\n*Surface, name=MS, type=ELEMENT\nE1, SNEG\n"
            "*Surface, name=BS, type=ELEMENT\nBLOCK, S2\n")
LM4_STEP = "*Step\n*Static\n*Boundary\nLEFT, 1, 3\n*Cload\n3, 1, 1.\n*End Step\n"


def test_tie_on_linear_membranes_ties_their_nodes():
    # ccx ties its expanded membrane's face, whose bottom nodes its own membrane hinge eliminates:
    # SNEG ties nothing, SPOS ties a face that shears through the thickness (probed); Abaqus ties
    # the membrane nodes, its tolerance measured from them (no membrane thickness in a *TIE)
    body, conv, rep = convert_str(LM4_SKIN + "*Tie, name=T1\nMS, BS\n" + LM4_STEP)
    assert _card_at(body, "*SURFACE, NAME=MS_NODES, TYPE=NODE") == ["1", "2", "5", "4"]
    # Abaqus' default, written out (ccx's is far smaller): 10 % of the master facet diagonal
    assert _card_at(body, "*TIE, NAME=T1, POSITION TOLERANCE=0.141421") == ["MS_NODES, BS"]
    assert "node surface MS_NODES" in rep.text() and not conv.reduced_physics
    body, _, _ = convert_str(LM4_SKIN + "*Tie, name=T1, position tolerance=0.02\nMS, BS\n" + LM4_STEP)
    assert _card_at(body, "*TIE, NAME=T1, POSITION TOLERANCE=0.02") == ["MS_NODES, BS"]
    body, _, _ = convert_str(LM4_SKIN + "*Tie, name=T1, type=NODE TO SURFACE\nMS, BS\n" + LM4_STEP)
    assert _card_at(body, "*TIE, NAME=T1, POSITION TOLERANCE=0.0707107") == ["MS_NODES, BS"]
    # ccx reads one line of a *TIE card: several lines -> one card each
    body, _, rep = convert_str(LM4_SKIN + "*Surface, name=S1, type=ELEMENT\nSKIN, SPOS\n"
                               "*Tie, name=T1, position tolerance=0.02\nBS, MS\nMS, BS\n" + LM4_STEP)
    assert _card_at(body, "*TIE, NAME=T1, POSITION TOLERANCE=0.02") == ["BS, MS"]
    assert _card_at(body, "*TIE, NAME=T1_2, POSITION TOLERANCE=0.02") == ["MS_NODES, BS"]
    assert "one *TIE per line" in rep.text()
    # a tied contact pair counts the membrane's half thickness: ccx's default tolerance (2.5 % of
    # the master edges) plus t / 2
    body, _, _ = convert_str(LM4_SKIN + "*Surface Interaction, name=SI\n*Contact Pair, interaction=SI, tied\n"
                             "MS, BS\n" + LM4_STEP)
    assert _card_at(body, "*TIE, NAME=ABQ2CCX_TIED1, POSITION TOLERANCE=0.03") == ["MS_NODES, BS"]
    # a surface on membranes and solids stays, warned
    body, conv, rep = convert_str(LM4_SKIN + "*Surface, name=MIX, type=ELEMENT\nE1, SNEG\nBLOCK, S1\n"
                                  "*Tie, name=T1\nMIX, BS\n" + LM4_STEP)
    assert _card_at(body, "*TIE, NAME=T1") == ["MIX, BS"] and "lies on membranes and on other" in rep.text()
    assert conv.reduced_physics
    # a slave node that is a node of the master face stays out (ccx would tie it to itself and
    # loop in its cascade); with every slave node on the master the line ties nothing
    shared = LM4_SKIN.replace("1, 1, 2, 5, 4\n", "1, 105, 2, 5, 4\n")
    body, _, _ = convert_str(shared + "*Tie, name=T1\nMS, BS\n" + LM4_STEP)
    assert _card_at(body, "*SURFACE, NAME=MS_NODES, TYPE=NODE") == ["2", "5", "4"]
    on_top = LM4_SKIN.replace("1, 1, 2, 5, 4\n", "1, 105, 106, 107, 108\n")
    body, _, _ = convert_str(on_top + "*Tie, name=T1\nMS, BS\n" + LM4_STEP)
    assert "*TIE" not in body.split("*HEADING")[-1].replace("** abq2ccx: *TIE", "")
    assert "every slave node of MS is a node of BS" in body


def test_tied_pair_of_a_membrane_on_a_rigid_surface_counts_its_thickness():
    # Abaqus' tied contact counts membrane thickness ("Defining tied contact"): a membrane whose
    # SNEG face rests on a rigid plate (its nodes half a thickness above) joins the plate's body
    deck = ("*Node\n1, 0., 0., 0.05\n2, 1., 0., 0.05\n3, 1., 1., 0.05\n4, 0., 1., 0.05\n"
            "11, 0., 0., 0.\n12, 1., 0., 0.\n13, 1., 1., 0.\n14, 0., 1., 0.\n19, 0.5, 0.5, -1.\n"
            "*Element, type=M3D4, elset=SKIN\n1, 1, 2, 3, 4\n*Element, type=R3D4, elset=RIG\n11, 11, 12, 13, 14\n"
            "*Rigid Body, ref node=19, elset=RIG\n*Material, name=M\n*Elastic\n1000., 0.3\n"
            "*Membrane Section, elset=SKIN, material=M\n0.1\n*Surface, name=MS\nSKIN, SNEG\n"
            "*Surface, name=MAST\nRIG, SPOS\n*Surface Interaction, name=SI\n*Contact Pair, interaction=SI, tied\n"
            "MS, MAST\n*Step\n*Static\n*Boundary\n19, 1, 6\n*End Step\n")
    body, conv, _ = convert_str(deck)
    assert "ABQ2CCX_TIED" not in body and not conv.reduced_physics
    rb = next(ln for ln in body.splitlines() if ln.startswith("*RIGID BODY"))
    members = [int(x) for x in _card_at(body, f"*NSET, NSET={rb.split('NSET=')[1].split(',')[0]}")[0].split(",")]
    assert {1, 2, 3, 4} <= set(members) and conv.geom.nodes[1][2] == 0.05      # not moved: touching
    # NO THICKNESS measures from the membrane nodes, as _membrane_tie_tolerance does: ADJUST
    # then moves them onto the plate
    body, conv, _ = convert_str(deck.replace("tied\n", "tied, no thickness, adjust=0.1\n"))
    assert "ABQ2CCX_TIED" not in body and conv.geom.nodes[1][2] == 0.0


def test_kinematic_couplings_on_membrane_and_shell_faces_take_their_nodes():
    # ccx would couple the expanded faces: 1.2 % off on M3D4, a crash (SIGBUS) on M3D3 and on the
    # shells the converter knots for the coupling (probed); Abaqus couples the surface's nodes
    cpl = "*Node\n9, 3., 0.5, 0.\n*Coupling, constraint name=C, ref node=9, surface=MS\n*Kinematic\n1, 3\n"
    body, _, rep = convert_str(LM4_SKIN + cpl + LM4_STEP)
    assert "*COUPLING, CONSTRAINT NAME=C, REF NODE=9, SURFACE=MS_NODES" in body
    assert _card_at(body, "*SURFACE, NAME=MS_NODES, TYPE=NODE") == ["1", "2", "5", "4"]
    # a reference node on the surface stays out of it
    body, _, _ = convert_str(LM4_SKIN + cpl.replace("ref node=9", "ref node=5") + LM4_STEP)
    assert _card_at(body, "*SURFACE, NAME=MS_NODES, TYPE=NODE") == ["1", "2", "4"]
    shell = LM4_SKIN.replace("type=M3D4, elset=SKIN", "type=S4, elset=SKIN").replace(
        "*Membrane Section, elset=SKIN, material=M\n0.01", "*Shell Section, elset=SKIN, material=M\n0.01")
    body, _, rep = convert_str(shell + cpl + LM4_STEP)
    assert "SURFACE=MS_NODES" in body and "on shells -> node surface MS_NODES" in rep.text()
    # a shell's *TIE slave stays its face (ccx ties the expanded face)
    body, _, _ = convert_str(shell + "*Tie, name=T1\nMS, BS\n" + LM4_STEP)
    assert _card_at(body, "*TIE, NAME=T1") == ["MS, BS"]
    # a coupling acts on nodes: a surface on membranes and solid faces takes all their nodes
    body, _, _ = convert_str(LM4_SKIN + "*Surface, name=MIX, type=ELEMENT\nE1, SNEG\nBLOCK, S1\n"
                             + cpl.replace("surface=MS", "surface=MIX") + LM4_STEP)
    assert "SURFACE=MIX_NODES" in body
    assert _card_at(body, "*SURFACE, NAME=MIX_NODES, TYPE=NODE") == ["1", "2", "5", "4", "101", "102", "103", "104"]
    # ccx takes a distributing coupling only on an element surface: on ccx's own membranes it
    # spreads the load over faces its hinge holds (M3D4 about 2 % off, M3D3 nothing): warned
    body, conv, rep = convert_str(LM4_SKIN + cpl.replace("*Kinematic", "*Distributing") + LM4_STEP)
    assert "REF NODE=9, SURFACE=MS\n" in body and "*DISTRIBUTING on membrane faces" in rep.text()
    assert any("DISTRIBUTING" in r for r in conv.reduced_physics)


def test_membrane_section_density_and_poisson():
    # ccx has no section mass and no thickness law: both parameters leave the card, said so
    dense = LM4_SKIN.replace("material=M\n0.01", "material=M, density=2., poisson=0.3\n0.01")
    body, conv, rep = convert_str(dense + LM4_STEP)
    assert "*MEMBRANE SECTION, ELSET=SKIN, MATERIAL=M\n0.01\n" in body
    assert "DENSITY= dropped: ccx has no section mass, and no step" in rep.text()
    assert "POISSON= dropped: Abaqus changes a membrane's thickness with it only under NLGEOM" in rep.text()
    assert not conv.reduced_physics
    # where mass acts: a copy of the material carries DENSITY / t (2 / 0.01) — also beside the
    # material's own density
    body, conv, rep = convert_str(dense + "*Step\n*Frequency\n3\n*End Step\n")
    assert "*MEMBRANE SECTION, ELSET=SKIN, MATERIAL=M_MEMBRANE_MASS\n0.01\n" in body
    assert "*MATERIAL, NAME=M_MEMBRANE_MASS\n*ELASTIC\n100000., 0.3\n*DENSITY\n200.\n" in body
    assert "*SOLID SECTION, ELSET=BLOCK, MATERIAL=M\n" in body and not conv.reduced_physics
    body, _, _ = convert_str(dense.replace("*Elastic\n100000., 0.3\n", "*Elastic\n100000., 0.3\n*Density\n7.\n")
                             + "*Step\n*Frequency\n3\n*End Step\n")
    assert "*MATERIAL, NAME=M_MEMBRANE_MASS\n*ELASTIC\n100000., 0.3\n*DENSITY\n207.\n" in body
    # a varying thickness cannot go into one copy: dropped, warned, reduced physics
    _, conv, rep = convert_str(dense.replace("density=2., poisson=0.3\n0.01", "density=2., nodal thickness\n")
                               + "*Nodal Thickness\n1, 0.01\n2, 0.01\n3, 0.02\n4, 0.01\n5, 0.01\n6, 0.02\n"
                               + "*Step\n*Frequency\n3\n*End Step\n")
    assert "DENSITY= (mass per unit area added to the material's) dropped" in rep.text()
    assert any("DENSITY" in r for r in conv.reduced_physics)
    # under NLGEOM the thickness follows the material's own ratio in ccx: 0.3 against the default
    # 0.5 -> warned (1 - 0.3 / 0.7 = 0.571); the same ratio -> a note
    nl = LM4_STEP.replace("*Step\n", "*Step, nlgeom\n")
    _, _, rep = convert_str(LM4_SKIN + nl)
    assert "differs at finite strain by about 0.571 x (e11 + e22)" in rep.text()
    _, _, rep = convert_str(LM4_SKIN.replace("material=M\n0.01", "material=M, poisson=0.3\n0.01") + nl)
    assert "with their material (the same ratio)" in rep.text() and "differs at finite strain" not in rep.text()
    # POISSON=MATERIAL, Abaqus/Explicit's default, thins with the material as ccx does
    _, _, rep = convert_str(LM4_SKIN.replace("material=M\n0.01", "material=M, poisson=MATERIAL\n0.01") + nl)
    assert "POISSON=MATERIAL" in rep.text() and "differs at finite strain" not in rep.text()


def test_constraints_on_quadratic_membranes_take_their_own_nodes():
    # a tied contact pair, a kinematic coupling and a rigid body ELSET: ccx would resolve them on
    # the solids' nodes, which the converter's *EQUATIONs eliminate; Abaqus uses the membrane's
    deck = (QM8_STRIP + "*Node\n100, 2.5, 0.5, 0.\n*Membrane Section, elset=SKIN, material=M\n0.01\n"
            "*Elset, elset=E1\n1\n*Surface, name=MS, type=ELEMENT\nE1, SNEG\n")
    block = ("*Node\n101, 0., 0., -0.5\n102, 1., 0., -0.5\n103, 1., 1., -0.5\n104, 0., 1., -0.5\n"
             "105, 0., 0., -0.005\n106, 1., 0., -0.005\n107, 1., 1., -0.005\n108, 0., 1., -0.005\n"
             "*Element, type=C3D8, elset=BLOCK\n101, 101, 102, 103, 104, 105, 106, 107, 108\n"
             "*Solid Section, elset=BLOCK, material=M\n*Surface, name=BS, type=ELEMENT\nBLOCK, S2\n")
    body, _, _ = convert_str(deck + block + "*Surface Interaction, name=SI\n*Contact Pair, interaction=SI, "
                             "tied\nMS, BS\n" + QM_STEP)
    assert _card_at(body, "*SURFACE, NAME=MS_NODES, TYPE=NODE") == ["1", "3", "13", "11", "2", "8", "12", "6"]
    assert _card_at(body, "*TIE, NAME=ABQ2CCX_TIED") == ["MS_NODES, BS"]
    body, _, _ = convert_str(deck + "*Coupling, constraint name=C, ref node=100, surface=MS\n*Kinematic\n" + QM_STEP)
    assert "*COUPLING, CONSTRAINT NAME=C, REF NODE=100, SURFACE=MS_NODES" in body
    body, _, _ = convert_str(deck + "*Coupling, constraint name=C, ref node=100, surface=MS\n*Distributing\n"
                             + QM_STEP)       # its surface nodes stay independent: the faces, area-weighted
    assert "*COUPLING, CONSTRAINT NAME=C, REF NODE=100, SURFACE=MS\n" in body
    body, conv, rep = convert_str(deck + "*Elset, elset=E2\n2\n*Rigid Body, ref node=100, elset=E2\n" + QM_STEP)
    assert _card_at(body, "*NSET, NSET=E2_NODES") == ["3, 5, 15, 13, 4, 10, 14, 8"]
    assert "*RIGID BODY, REF NODE=100, NSET=E2_NODES" in body and not conv.reduced_physics


def test_quadratic_membrane_output_distributions_and_shared_supports():
    # a whole-model .frd request prints the membrane nodes, which are in no ccx element
    body, conv, _ = convert_str(QM8_STRIP + "*Membrane Section, elset=SKIN, material=M\n0.01\n" + QM_STEP)
    assert _card_at(body, "*NODE PRINT, NSET=ABQ2CCX_MEMBRANE_NODES") == ["U, RF"]
    assert conv.geom.nsets["ABQ2CCX_MEMBRANE_NODES"] == sorted(range(1, 16)[:5]) + [6, 8, 10] + list(range(11, 16))
    # a MEMBRANE THICKNESS distribution (and its table) is in the solids' geometry: no card,
    # no reduced physics — also per instance of a part
    dist = ("*Distribution Table, name=THT\nLENGTH\n*Distribution, name=TH, location=ELEMENT, table=THT\n"
            ", 0.02\n1, 0.04\n*Membrane Section, elset=SKIN, material=M, membrane thickness=TH\n")
    body, conv, _ = convert_str(QM8_STRIP + dist + QM_STEP)
    g = reparse(body)
    assert g.nodes[g.elements[1][1][0]] == (0.0, 0.0, -0.02) and g.nodes[g.elements[2][1][0]] == (1.0, 0.0, -0.01)
    assert "*DISTRIBUTION" not in body.split("*HEADING")[-1] and not conv.reduced_physics
    part = QM8_STRIP.split("*Material")[0].replace("*Nset, nset=LEFT\n1, 6, 11\n*Nset, nset=RIGHT\n5, 10, 15\n", "")
    asm = ("*Part, name=P\n" + part + dist + "*End Part\n*Assembly, name=A\n*Instance, name=I1, part=P\n"
           "*End Instance\n*End Assembly\n*Material, name=M\n*Elastic\n100000., 0.3\n")
    body, conv, rep = convert_str(asm)
    assert "C3D20R" in body and "no positive thickness" not in rep.text() and not conv.reduced_physics
    # a held node a truss shares: ccx's RF there leaves out the membrane's share (warned)
    body, conv, rep = convert_str(QM8_STRIP + "*Element, type=T3D2, elset=CABLE\n50, 1, 11\n"
                                  "*Solid Section, elset=CABLE, material=M\n0.01\n"
                                  "*Membrane Section, elset=SKIN, material=M\n0.01\n" + QM_STEP)
    assert "2 node(s) held by a *BOUNDARY belong to quadratic membranes" in rep.text()
    assert not conv.reduced_physics


def test_nine_node_membranes_lose_their_centre_node():
    nine = (QM8_STRIP.replace("6, 0., 0.5, 0.\n", "6, 0., 0.5, 0.\n7, 0.5, 0.5, 0.\n")
            .replace("10, 2., 0.5, 0.\n", "9, 1.5, 0.5, 0.\n10, 2., 0.5, 0.\n")
            .replace("M3D8R, elset=SKIN\n1, 1, 3, 13, 11, 2, 8, 12, 6\n2, 3, 5, 15, 13, 4, 10, 14, 8",
                     "M3D9R, elset=SKIN\n1, 1, 3, 13, 11, 2, 8, 12, 6, 7\n2, 3, 5, 15, 13, 4, 10, 14, 8, 9"))
    body, conv, rep = convert_str(nine + "*Membrane Section, elset=SKIN, material=M\n0.01\n")
    g = reparse(body)
    assert g.elements[1][0] == "C3D20R" and 7 not in g.elements[1][1] and not dangling_refs(g)
    centre = [eq for eq in _all_equations(body) if eq[0][0] == 7]
    assert len(centre) == 3 and len(centre[0]) == 17
    assert "M3D9R (9-node membrane) -> the 8-node serendipity solid" in rep.text()
    assert any("M3D9R" in r for r in conv.reduced_physics)


def test_composite_examples_match_the_validation_decks():
    import validate_with_ccx as V
    for name, text in (("composite_plate_s4r", V.composite_plate_deck("s4r")),
                       ("composite_plate_sc8r", V.composite_plate_deck("sc8r")),
                       ("composite_inplane_s4r", V.composite_inplane_deck("s4r")),
                       ("composite_inplane_sc8r", V.composite_inplane_deck("sc8r"))):
        with open(os.path.join(EXAMPLES, name + ".inp"), encoding="utf-8") as fh:
            assert fh.read() == text, f"examples/{name}.inp differs from validate_with_ccx.py's deck"


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
