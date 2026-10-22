#!/usr/bin/env python3
"""Build CalculiX 2.23 with an Abaqus deck's UMAT, for abq2ccx --abaqus-umat.

    python3 tools/build_ccx_umat.py --src CalculiX/ccx_2.23/src -o ccx_umat umat.for [more.f ...]

Run it where the compilers and libraries are: the conda environment of the user guide
(docs/user-guide.md, "--abaqus-umat"), or name another installation of SPOOLES, ARPACK and
LAPACK with --prefix (CC, FC and AR from the environment; cc, gfortran and ar by default).

1. Once per source tree, in a cache folder (~/.cache/abq2ccx; the source tree is copied, never
   edited): sets U0 in umat_abaqusnl.f, which ccx 2.23 never does (ccx issue #225), builds
   ``make CalculiX.o CalculiX.a`` with the user guide's flags, takes ccx's example UMAT out of
   the archive, and builds the Abaqus utility routines ccx lacks: XIT, GETOUTDIR, GETJOBNAME,
   STDB_ABQERR, SINV, SPRINC, SPRIND, ROTSIG, the mutexes and thread queries (one thread),
   the SMA allocatable arrays, with ABA_PARAM.INC and the SMA headers; GETVRM and the table
   collections stop ccx with an error.
2. Compiles the UMAT's files as Abaqus does (fixed form to column 132, preprocessed; .f90 and
   .f95 free form; .c with the C compiler), large local arrays static (ccx calls the UMAT in
   threads with the system's default stack, 512 KB on macOS: run with OMP_NUM_THREADS=1), and
   links them ahead of ccx's archive, with the utility routines they call.

--uexternaldb calls the deck's UEXTERNALDB as Abaqus does (LOP 0 before the first increment,
then 2 and 1 between increments), which ccx never does.  --stretch hands the UMAT the right
stretch tensors U (F = R U) in place of DFGRD0 and DFGRD1: under ABAQUSNL ccx's strain and
stress axes turn with the material while the deformation gradients are global, so a UMAT that
builds its stress from them must see U.  --patch 'REGEX=>REPLACEMENT' edits a copy of each file
before it is compiled (for Intel Fortran extensions gfortran rejects); --fflags adds compiler
flags (--fflags=-ffree-form for free-form source in a .f file).
"""

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile

VERSION = "1"      # part of the cache key: change it with the library or the base build

# docs/user-guide.md, "--abaqus-umat", step 2
CCX_FFLAGS = "-O2 -cpp -fallow-argument-mismatch -w"
CCX_CFLAGS = ('-O2 -w -DARCH="Linux" -DSPOOLES -DARPACK -DMATRIXSTORAGE -DNETWORKOUT '
              "-Wno-int-conversion -Wno-incompatible-pointer-types "
              "-Wno-implicit-function-declaration -Wno-implicit-int -Wno-return-mismatch")
# as Abaqus compiles a UMAT; -fmax-stack-var-size: large local arrays static (ccx's threads)
UMAT_FFLAGS = ["-O2", "-cpp", "-fallow-argument-mismatch", "-fcray-pointer", "-std=legacy",
               "-fmax-stack-var-size=4096", "-w"]

# ccx issue #225: umat_abaqusnl.f never sets U0, the right stretch tensor at the start of the
# increment (docs/user-guide.md, step 1)
U0_ANCHOR = "      um1(3,2)=um1(2,3)\n"
U0_FIX = ("      do jj=1,6\n"
          "        u0(kal(1,jj),kal(2,jj))=xm1(jj)/wum1(1)+xm2(jj)/wum1(2)\n"
          "     &       +xm3(jj)/wum1(3)\n"
          "        u0(kal(2,jj),kal(1,jj))=u0(kal(1,jj),kal(2,jj))\n"
          "      enddo\n")

ABA_PARAM = "      implicit real*8(a-h,o-z)\n      parameter (nprecd=2)\n"
SMA_ARRAYS_HDR = """\
C     Declarations of the SMA array functions
      INTEGER*8 SMAIntArrayCreate, SMAIntArrayAccess
      INTEGER*8 SMAFloatArrayCreateDP, SMAFloatArrayCreate
      INTEGER*8 SMAFloatArrayAccess
      INTEGER SMAIntArraySize, SMAFloatArraySize
      EXTERNAL SMAIntArrayCreate, SMAIntArrayAccess, SMAIntArraySize
      EXTERNAL SMAFloatArrayCreateDP, SMAFloatArrayCreate
      EXTERNAL SMAFloatArrayAccess, SMAFloatArraySize
"""
SMA_UTILITIES_HDR = """\
C     Abaqus thread utilities: one thread in ccx
      INTEGER GET_THREAD_ID, GETNUMTHREADS
      EXTERNAL GET_THREAD_ID, GETNUMTHREADS
"""
HEADERS = {"ABA_PARAM.INC": ABA_PARAM, "aba_param.inc": ABA_PARAM,
           "SMAAspUserArrays.hdr": SMA_ARRAYS_HDR, "SMAAspUserUtilities.hdr": SMA_UTILITIES_HDR,
           "SMAAspUserSubroutines.hdr": SMA_UTILITIES_HDR + SMA_ARRAYS_HDR}

# The Abaqus utility routines, each as the Abaqus documentation describes it; one object per
# routine in the library, so a UMAT that has its own copy of one still links.
UTILITIES = """\
      SUBROUTINE XIT
      WRITE(*,*) '*ERROR in the UMAT: XIT called, the analysis stops'
      CALL EXIT(201)
      END
      SUBROUTINE GETOUTDIR(OUTDIR,LENOUTDIR)
      CHARACTER*(*) OUTDIR
      INTEGER LENOUTDIR,ISTAT
      CALL GETCWD(OUTDIR,ISTAT)
      LENOUTDIR=LEN_TRIM(OUTDIR)
      END
      SUBROUTINE GETJOBNAME(JOBNAME,LENJOBNAME)
C     ccx's job: "ccx job" or "ccx -i job"
      CHARACTER*(*) JOBNAME
      CHARACTER*256 ARG
      INTEGER LENJOBNAME,I,N
      JOBNAME=' '
      N=COMMAND_ARGUMENT_COUNT()
      I=1
 10   IF (I.LE.N) THEN
        CALL GET_COMMAND_ARGUMENT(I,ARG)
        IF (ARG.EQ.'-i' .AND. I.LT.N) THEN
          CALL GET_COMMAND_ARGUMENT(I+1,ARG)
          JOBNAME=ARG
          GOTO 20
        ELSE IF (ARG(1:1).NE.'-') THEN
          JOBNAME=ARG
          GOTO 20
        END IF
        I=I+1
        GOTO 10
      END IF
 20   LENJOBNAME=LEN_TRIM(JOBNAME)
      END
      SUBROUTINE STDB_ABQERR(LOP,STRING,INTV,REALV,CHARV)
C     LOP 1 information, -1 warning, -2 error, -3 error and stop
      INTEGER LOP
      CHARACTER*(*) STRING
      WRITE(*,*) 'UMAT message (',LOP,'): ',TRIM(STRING)
      IF (LOP.EQ.-3) CALL EXIT(201)
      END
      SUBROUTINE MUTEXINIT(ID)
      INTEGER ID
      END
      SUBROUTINE MUTEXLOCK(ID)
      INTEGER ID
      END
      SUBROUTINE MUTEXUNLOCK(ID)
      INTEGER ID
      END
      SUBROUTINE GETNUMCPUS(NUMCPUS)
      INTEGER NUMCPUS
      NUMCPUS=1
      END
      INTEGER FUNCTION GET_THREAD_ID()
      GET_THREAD_ID=0
      END
      INTEGER FUNCTION GETNUMTHREADS()
      GETNUMTHREADS=1
      END
      SUBROUTINE GETRANK(KPROCESSNUM)
      INTEGER KPROCESSNUM
      KPROCESSNUM=0
      END
      SUBROUTINE SINV(STRESS,SINV1,SINV2,NDI,NSHR)
C     SINV1 = trace / 3, SINV2 = Mises equivalent stress
      IMPLICIT REAL*8(A-H,O-Z)
      DIMENSION STRESS(*),S(6)
      DO I=1,6
        S(I)=0.D0
      END DO
      DO I=1,NDI
        S(I)=STRESS(I)
      END DO
      DO I=1,NSHR
        S(3+I)=STRESS(NDI+I)
      END DO
      SINV1=(S(1)+S(2)+S(3))/3.D0
      SINV2=SQRT(1.5D0*((S(1)-SINV1)**2+(S(2)-SINV1)**2
     1  +(S(3)-SINV1)**2+2.D0*(S(4)**2+S(5)**2+S(6)**2)))
      END
      SUBROUTINE ABQ_TENS(S,LSTR,NDI,NSHR,A)
C     the symmetric 3x3 tensor of an Abaqus component array
      IMPLICIT REAL*8(A-H,O-Z)
      DIMENSION S(*),A(3,3),X(6)
      F=1.D0
      IF (LSTR.EQ.2) F=0.5D0
      DO I=1,6
        X(I)=0.D0
      END DO
      DO I=1,NDI
        X(I)=S(I)
      END DO
      DO I=1,NSHR
        X(3+I)=F*S(NDI+I)
      END DO
      A(1,1)=X(1)
      A(2,2)=X(2)
      A(3,3)=X(3)
      A(1,2)=X(4)
      A(2,1)=X(4)
      A(1,3)=X(5)
      A(3,1)=X(5)
      A(2,3)=X(6)
      A(3,2)=X(6)
      END
      SUBROUTINE SPRIND(S,PS,AN,LSTR,NDI,NSHR)
C     principal values PS and directions AN(K,1..3) of PS(K)
      IMPLICIT REAL*8(A-H,O-Z)
      DIMENSION S(*),PS(3),AN(3,3),A(3,3),W(3),WORK(20)
      CALL ABQ_TENS(S,LSTR,NDI,NSHR,A)
      CALL DSYEV('V','U',3,A,3,W,WORK,20,INFO)
      DO K=1,3
        PS(K)=W(K)
        DO I=1,3
          AN(K,I)=A(I,K)
        END DO
      END DO
      END
      SUBROUTINE SPRINC(S,PS,LSTR,NDI,NSHR)
      IMPLICIT REAL*8(A-H,O-Z)
      DIMENSION S(*),PS(3),AN(3,3)
      CALL SPRIND(S,PS,AN,LSTR,NDI,NSHR)
      END
      SUBROUTINE ROTSIG(S,R,SPRIME,LSTR,NDI,NSHR)
C     SPRIME = R S R^T, components as S (LSTR 2: engineering shears)
      IMPLICIT REAL*8(A-H,O-Z)
      DIMENSION S(*),R(3,3),SPRIME(*),A(3,3),B(3,3)
      CALL ABQ_TENS(S,LSTR,NDI,NSHR,A)
      DO I=1,3
        DO J=1,3
          B(I,J)=0.D0
          DO K=1,3
            DO L=1,3
              B(I,J)=B(I,J)+R(I,K)*A(K,L)*R(J,L)
            END DO
          END DO
        END DO
      END DO
      F=1.D0
      IF (LSTR.EQ.2) F=2.D0
      DO I=1,NDI
        SPRIME(I)=B(I,I)
      END DO
      IF (NSHR.GE.1) SPRIME(NDI+1)=F*B(1,2)
      IF (NSHR.GE.2) SPRIME(NDI+2)=F*B(1,3)
      IF (NSHR.GE.3) SPRIME(NDI+3)=F*B(2,3)
      END
      SUBROUTINE GETPROPERTYTABLE(A,B,C,D,E,F)
      WRITE(*,*) '*ERROR in the UMAT: GETPROPERTYTABLE (no table',
     1 ' collections in ccx)'
      CALL EXIT(201)
      END
      SUBROUTINE SETTABLECOLLECTION(A,B)
      WRITE(*,*) '*ERROR in the UMAT: SETTABLECOLLECTION (no table',
     1 ' collections in ccx)'
      CALL EXIT(201)
      END
      SUBROUTINE GETVRM(VAR,ARRAY,JARRAY,FLGRAY,JRCD,JMAC,JMATYP,
     1 MATLAYO,LACCFLA)
      WRITE(*,*) '*ERROR in the UMAT: GETVRM (not available in ccx)'
      CALL EXIT(201)
      END
"""

# Abaqus' allocatable global arrays: a registry from an ID to a block on the heap
SMA_ARRAYS = r"""
#include <stdlib.h>
#include <stdio.h>
#include <stdint.h>
#define NMAX 4096
static struct { int id, kind, size; void *p; } reg[NMAX];
static int nreg = 0;
static int find(int id, int kind) {
  for (int i = 0; i < nreg; i++) if (reg[i].id == id && reg[i].kind == kind) return i;
  return -1;
}
static void *create(int id, int kind, int size, size_t elem) {
  int i = find(id, kind);
  if (i >= 0) return reg[i].p;
  if (nreg == NMAX) { fprintf(stderr, "*ERROR in the UMAT: too many SMA arrays\n"); exit(201); }
  void *p = calloc(size > 0 ? (size_t)size : 1, elem);
  reg[nreg].id = id; reg[nreg].kind = kind; reg[nreg].size = size; reg[nreg].p = p; nreg++;
  return p;
}
int64_t smaintarraycreate_(int *id, int *size, int *init) {
  int *p = create(*id, 0, *size, sizeof(int));
  for (int k = 0; k < *size; k++) p[k] = *init;
  return (int64_t)(intptr_t)p;
}
int64_t smaintarrayaccess_(int *id) {
  int i = find(*id, 0); return i < 0 ? 0 : (int64_t)(intptr_t)reg[i].p;
}
int smaintarraysize_(int *id) { int i = find(*id, 0); return i < 0 ? 0 : reg[i].size; }
int64_t smafloatarraycreatedp_(int *id, int *size, double *init) {
  double *p = create(*id, 1, *size, sizeof(double));
  for (int k = 0; k < *size; k++) p[k] = *init;
  return (int64_t)(intptr_t)p;
}
int64_t smafloatarraycreate_(int *id, int *size, double *init) {
  return smafloatarraycreatedp_(id, size, init);
}
int64_t smafloatarrayaccess_(int *id) {
  int i = find(*id, 1); return i < 0 ? 0 : (int64_t)(intptr_t)reg[i].p;
}
int smafloatarraysize_(int *id) { int i = find(*id, 1); return i < 0 ? 0 : reg[i].size; }
void smaintarraydelete_(int *id) { }
void smafloatarraydelete_(int *id) { }
"""

# ccx's umat_abaqus.f and umat_abaqusnl.f call this in place of the deck's UMAT (copies of
# them, linked ahead of the archive) when --uexternaldb or --stretch asks for it
SHIM = """\
      SUBROUTINE ABQ2CCX_UMAT(STRESS,STATEV,DDSDDE,SSE,SPD,SCD,RPL,
     1 DDSDDT,DRPLDE,DRPLDT,STRAN,DSTRAN,TIME,DTIME,TEMP,DTEMP,PREDEF,
     2 DPRED,CMNAME,NDI,NSHR,NTENS,NSTATV,PROPS,NPROPS,COORDS,DROT,
     3 PNEWDT,CELENT,DFGRD0,DFGRD1,NOEL,NPT,LAYER,KSPT,KSTEP,KINC)
      IMPLICIT REAL*8(A-H,O-Z)
      CHARACTER*80 CMNAME
      DIMENSION STRESS(*),STATEV(*),DDSDDE(*),DDSDDT(*),DRPLDE(*),
     1 STRAN(*),DSTRAN(*),TIME(2),PREDEF(*),DPRED(*),PROPS(*),
     2 COORDS(3),DROT(3,3),DFGRD0(3,3),DFGRD1(3,3),T0(2),
     3 F0(3,3),F1(3,3)
      INTEGER LSTEP,LINC
      LOGICAL FIRST
      SAVE FIRST,LSTEP,LINC
      DATA FIRST /.TRUE./, LSTEP /0/, LINC /0/
#ifdef ABQ_UEXTERNALDB
      IF (FIRST) THEN
        T0(1)=0.D0
        T0(2)=0.D0
        CALL UEXTERNALDB(0,0,T0,0.D0,0,0)
      END IF
      IF (KSTEP.NE.LSTEP .OR. KINC.NE.LINC) THEN
        IF (LSTEP.NE.0) CALL UEXTERNALDB(2,0,TIME,DTIME,LSTEP,LINC)
        LSTEP=KSTEP
        LINC=KINC
        CALL UEXTERNALDB(1,0,TIME,DTIME,LSTEP,LINC)
      END IF
#endif
      FIRST=.FALSE.
      DO J=1,3
        DO I=1,3
          F0(I,J)=DFGRD0(I,J)
          F1(I,J)=DFGRD1(I,J)
        END DO
      END DO
#ifdef ABQ_STRETCH
      CALL ABQ2CCX_STRETCH(DFGRD0,F0)
      CALL ABQ2CCX_STRETCH(DFGRD1,F1)
#endif
      CALL UMAT(STRESS,STATEV,DDSDDE,SSE,SPD,SCD,RPL,DDSDDT,
     1 DRPLDE,DRPLDT,STRAN,DSTRAN,TIME,DTIME,TEMP,DTEMP,PREDEF,DPRED,
     2 CMNAME,NDI,NSHR,NTENS,NSTATV,PROPS,NPROPS,COORDS,DROT,PNEWDT,
     3 CELENT,F0,F1,NOEL,NPT,LAYER,KSPT,KSTEP,KINC)
      END
      SUBROUTINE ABQ2CCX_STRETCH(F,U)
C     U = (F^T F)^(1/2), from the eigenvectors of F^T F
      IMPLICIT REAL*8(A-H,O-Z)
      DIMENSION F(3,3),U(3,3),C(3,3),W(3),WORK(20)
      DO I=1,3
        DO J=1,3
          C(I,J)=F(1,I)*F(1,J)+F(2,I)*F(2,J)+F(3,I)*F(3,J)
        END DO
      END DO
      CALL DSYEV('V','U',3,C,3,W,WORK,20,INFO)
      DO I=1,3
        DO J=1,3
          U(I,J)=0.D0
          DO K=1,3
            U(I,J)=U(I,J)+C(I,K)*SQRT(MAX(W(K),0.D0))*C(J,K)
          END DO
        END DO
      END DO
      END
"""
SHIM_CALLERS = ("umat_abaqus.f", "umat_abaqusnl.f")


class BuildError(Exception):
    pass


def tools():
    """The C compiler, the Fortran compiler and the archiver."""
    return os.environ.get("CC", "cc"), os.environ.get("FC", "gfortran"), os.environ.get("AR", "ar")


def run(cmd, cwd, log):
    """Run ``cmd`` in ``cwd``, its output appended to the file ``log``; BuildError on failure,
    with the output's last lines."""
    with open(log, "ab") as fh:
        fh.write(("$ " + " ".join(cmd) + "\n").encode())
        fh.flush()
        try:
            rc = subprocess.call(cmd, cwd=cwd, stdin=subprocess.DEVNULL, stdout=fh,
                                 stderr=subprocess.STDOUT)
        except OSError as exc:
            raise BuildError(f"cannot run {cmd[0]}: {exc}") from None
    if rc:
        with open(log, "rb") as fh:
            fh.seek(max(0, os.path.getsize(log) - 4000))
            tail = fh.read().decode("utf-8", "replace").splitlines()[-25:]
        raise BuildError(f"{os.path.basename(cmd[0])} failed (exit {rc}); the end of {log}:\n"
                         + "\n".join(tail))


def _ccx_sources(src):
    """The relative paths of the ccx source tree's sources and Makefiles, sorted."""
    names = sorted(f for f in os.listdir(src) if os.path.isfile(os.path.join(src, f)) and
                   (f.endswith((".c", ".h", ".f", ".inc")) or f.startswith("Makefile")))
    if "umat_abaqusnl.f" not in names or "Makefile" not in names:
        raise BuildError(f"{src} is not ccx's source folder (CalculiX/ccx_2.23/src)")
    return names


def _libs(prefix):
    """The link arguments for SPOOLES, ARPACK and LAPACK under ``prefix``."""
    lib = os.path.join(prefix, "lib")
    spooles = os.path.join(lib, "spooles.a")
    return ([spooles] if os.path.exists(spooles) else ["-lspooles"]) + [
        "-L" + lib, "-larpack", "-llapack", "-lblas", "-lpthread", "-lm", "-Wl,-rpath," + lib]


def build_base(src, prefix, cache=None, jobs=4, echo=print):
    """The folder with ccx's objects (CalculiX.o, CalculiX.a without the example UMAT), the
    utility library libabq.a, the shim's callers and the include folder, built from the ccx
    2.23 source folder ``src`` once per source tree, compilers and ``prefix``."""
    cc, fc, ar = tools()
    names = _ccx_sources(src)
    h = hashlib.sha256("\0".join((VERSION, cc, fc, os.path.abspath(prefix))).encode())
    for f in names:
        h.update(f.encode() + b"\0")
        with open(os.path.join(src, f), "rb") as fh:
            h.update(hashlib.sha256(fh.read()).digest())
    cache = cache or os.path.join(os.path.expanduser("~"), ".cache", "abq2ccx")
    base = os.path.join(cache, "ccx-2.23-" + h.hexdigest()[:16])
    if os.path.exists(os.path.join(base, "CalculiX.a")):
        return base
    os.makedirs(cache, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="ccx-build-", dir=cache)
    log = os.path.join(tmp, "build.log")
    echo(f"building ccx's objects once, in {base} (a few minutes; log: {log})")
    try:
        work = os.path.join(tmp, "src")
        os.makedirs(work)
        for f in names:
            shutil.copy2(os.path.join(src, f), os.path.join(work, f))
        p = os.path.join(work, "umat_abaqusnl.f")
        with open(p, newline="") as fh:
            s = fh.read()
        if "u0(kal(1,jj),kal(2,jj))" not in s:
            if U0_ANCHOR not in s:
                raise BuildError(f"{src}/umat_abaqusnl.f is not ccx 2.23's: no place for the U0 fix")
            with open(p, "w", newline="") as fh:
                fh.write(s.replace(U0_ANCHOR, U0_ANCHOR + U0_FIX, 1))
        cflags = CCX_CFLAGS + " -I" + os.path.join(prefix, "include", "spooles")
        run(["make", f"-j{jobs}", "CalculiX.o", "CalculiX.a", "CC=" + cc, "FC=" + fc,
             "FFLAGS=" + CCX_FFLAGS, "CFLAGS=" + cflags], work, log)
        for f in ("CalculiX.o", "CalculiX.a"):
            shutil.move(os.path.join(work, f), os.path.join(tmp, f))
        run([ar, "d", "CalculiX.a", "umat.o"], tmp, log)      # ccx's example UMAT
        # the callers of the deck's UMAT, calling the shim instead (a continuation line keeps
        # them within column 72)
        for f in SHIM_CALLERS:
            with open(os.path.join(work, f), newline="") as fh:
                s, n = re.subn(r"(?i)\bcall umat\(", "call abq2ccx_umat(\n     &", fh.read())
            if n != 1:
                raise BuildError(f"{src}/{f}: {n} UMAT calls, not 1")
            with open(os.path.join(tmp, "shim_" + f), "w", newline="") as fh:
                fh.write(s)
            run([fc, "-c"] + CCX_FFLAGS.split() + ["shim_" + f, "-o", "shim_" + f[:-2] + ".o"],
                tmp, log)
        inc = os.path.join(tmp, "include")
        os.makedirs(inc)
        for f, text in HEADERS.items():                 # one file on a case-blind file system
            with open(os.path.join(inc, f), "w") as fh:
                fh.write(text)
        lib = os.path.join(tmp, "libabq")
        os.makedirs(lib)
        objs = []
        for unit in re.findall(r"(?ms)^ {6}(?:SUBROUTINE|INTEGER FUNCTION) .*?^ {6}END\n", UTILITIES):
            name = re.match(r" {6}(?:SUBROUTINE|INTEGER FUNCTION) (\w+)", unit).group(1).lower()
            with open(os.path.join(lib, name + ".f"), "w") as fh:
                fh.write(unit)
            run([fc, "-c", "-O2", "-w", name + ".f", "-o", name + ".o"], lib, log)
            objs.append(name + ".o")
        with open(os.path.join(lib, "sma_arrays.c"), "w") as fh:
            fh.write(SMA_ARRAYS)
        run([cc, "-c", "-O2", "-w", "sma_arrays.c", "-o", "sma_arrays.o"], lib, log)
        run([ar, "rc", os.path.join(tmp, "libabq.a")] + objs + ["sma_arrays.o"], lib, log)
        shutil.rmtree(work)
        try:
            os.rename(tmp, base)
        except OSError:                                  # built meanwhile by another run
            if not os.path.exists(os.path.join(base, "CalculiX.a")):
                raise
            shutil.rmtree(tmp, ignore_errors=True)
    except BaseException:
        if os.path.exists(tmp):
            kept = tmp + ".failed"
            shutil.rmtree(kept, ignore_errors=True)
            os.rename(tmp, kept)
            echo(f"the failed build is kept in {kept}")
        raise
    return base


def build(files, out, src, prefix, cache=None, fflags=(), patches=(), uexternaldb=False,
          stretch=False, jobs=4, echo=print):
    """Build ccx with the UMAT of the source ``files`` as the executable ``out``; returns
    ``out``.  ``patches``: (regex, replacement) pairs applied to a copy of each file."""
    if not files:
        raise BuildError("no UMAT source files")
    for f in files:
        if not os.path.isfile(f):
            raise BuildError(f"{f}: no such file")
    base = build_base(src, prefix, cache, jobs, echo)
    cc, fc, _ = tools()
    out = os.path.abspath(out)
    with tempfile.TemporaryDirectory(prefix="ccx-umat-") as w:
        log = os.path.join(w, "build.log")
        try:
            objs = []
            for i, f in enumerate(files):
                path, here = os.path.abspath(f), os.path.dirname(os.path.abspath(f))
                if patches:
                    with open(path, encoding="latin-1", newline="") as fh:
                        s = fh.read()
                    for a, b in patches:
                        s, n = re.subn(a, b, s)
                        echo(f"{f}: {a!r} -> {b!r} at {n} place(s)")
                    os.makedirs(os.path.join(w, str(i)))
                    path = os.path.join(w, str(i), os.path.basename(f))
                    with open(path, "w", encoding="latin-1", newline="") as fh:
                        fh.write(s)
                obj = f"{i}_{os.path.splitext(os.path.basename(f))[0]}.o"
                ext = os.path.splitext(f)[1].lower()
                if ext == ".c":
                    cmd = [cc, "-c", "-O2", "-w", "-I" + here, path, "-o", obj]
                else:
                    form = (["-ffree-line-length-none"] if ext in (".f90", ".f95")
                            else ["-ffixed-line-length-132"])
                    cmd = ([fc, "-c"] + UMAT_FFLAGS + form + ["-I" + here, "-I" +
                           os.path.join(base, "include")] + list(fflags) + [path, "-o", obj])
                run(cmd, w, log)
                objs.append(obj)
            if uexternaldb or stretch:
                with open(os.path.join(w, "shim.f"), "w") as fh:
                    fh.write(SHIM)
                run([fc, "-c", "-O2", "-w", "-cpp"] + ["-DABQ_UEXTERNALDB"] * uexternaldb +
                    ["-DABQ_STRETCH"] * stretch + ["shim.f", "-o", "shim.o"], w, log)
                objs += ["shim.o"] + [os.path.join(base, "shim_" + f[:-2] + ".o")
                                      for f in SHIM_CALLERS]
            tmp = os.path.join(w, "ccx")
            run([fc, "-o", tmp] + objs + [os.path.join(base, "CalculiX.o"),
                os.path.join(base, "CalculiX.a"), os.path.join(base, "libabq.a")] +
                _libs(prefix), w, log)
        except BuildError as exc:
            raise BuildError(str(exc).replace(log, "the build log")) from None
        os.makedirs(os.path.dirname(out), exist_ok=True)
        shutil.move(tmp, out + ".tmp")
        os.replace(out + ".tmp", out)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="build_ccx_umat.py", description=__doc__.split("\n\n")[0],
        epilog="Then: OMP_NUM_THREADS=1 abq2ccx --abaqus-umat --run --ccx ./ccx_umat deck.inp")
    ap.add_argument("files", nargs="+", metavar="FILE",
                    help="the UMAT's source files (.f, .for: fixed form; .f90: free form; .c)")
    ap.add_argument("--src", required=True, help="ccx 2.23's source folder (CalculiX/ccx_2.23/src)")
    ap.add_argument("-o", "--output", default="ccx_umat", help="the executable (default ccx_umat)")
    ap.add_argument("--prefix", default=os.environ.get("CONDA_PREFIX"),
                    help="where SPOOLES, ARPACK and LAPACK are (include/spooles, lib); "
                         "default: the active conda environment")
    ap.add_argument("--cache", help="the folder for ccx's objects (default ~/.cache/abq2ccx)")
    ap.add_argument("--fflags", default="",
                    help="more Fortran compiler flags (--fflags=-ffree-form)")
    ap.add_argument("--patch", action="append", default=[], metavar="REGEX=>REPLACEMENT",
                    help="edit a copy of each file before it is compiled (repeatable)")
    ap.add_argument("--uexternaldb", action="store_true", help="call the deck's UEXTERNALDB")
    ap.add_argument("--stretch", action="store_true",
                    help="hand the UMAT the stretch tensors U in place of DFGRD0, DFGRD1")
    ap.add_argument("-j", "--jobs", type=int, default=4, help="parallel compiles (default 4)")
    a = ap.parse_args(argv)
    if not a.prefix:
        ap.error("--prefix: name the folder of SPOOLES, ARPACK and LAPACK (no conda environment "
                 "is active)")
    patches = []
    for p in a.patch:
        if "=>" not in p:
            ap.error(f"--patch {p!r}: REGEX=>REPLACEMENT")
        patches.append(tuple(p.split("=>", 1)))
    try:
        out = build(a.files, a.output, a.src, a.prefix, a.cache, a.fflags.split(), patches,
                    a.uexternaldb, a.stretch, a.jobs)
    except BuildError as exc:
        print(f"build_ccx_umat: {exc}", file=sys.stderr)
        return 1
    print(f"built {out}\nrun: OMP_NUM_THREADS=1 abq2ccx --abaqus-umat --run --ccx {out} deck.inp")
    return 0


if __name__ == "__main__":
    sys.exit(main())
