#!/usr/bin/env python3
"""Download the corpus of real-world Abaqus decks listed in manifest.py.

    python corpus/fetch.py               # the decks and the files they read
    python corpus/fetch.py --companions  # only the files the decks already here read
    python corpus/fetch.py --umat        # only the UMAT tier's sources (manifest.UMAT_SOURCES)

Files land in ``corpus/files/`` (gitignored). Re-run any time; existing files are
overwritten. Any other argument (``--help`` too) prints this usage and downloads nothing. Requires network access (uses urllib from the standard library).

A deck's companions, the files its cards read with ``INPUT=`` (``*INCLUDE`` and data cards
such as ``*NODE`` or ``*DISTRIBUTION``, nested ones too), are fetched from next to it and
saved at the relative path the card names, where Abaqus (and abq2ccx) look for them.  A
path two decks need with different contents is left out, so no deck reads another's.

The UMAT tier's sources come from the commit the manifest pins, each checked against its
sha256 (a file that differs is not saved), into ``corpus/files/umat/<owner>__<repository>/``
at their paths in the repository; tests/test_corpus.py compiles them only when asked to
(ABQ2CCX_CCX_SRC, docs/testing.md).
"""

import hashlib
import os
import re
import sys
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from manifest import CORPUS, UMAT_SOURCES  # noqa: E402

DEST = os.path.join(HERE, "files")
UMAT_DEST = os.path.join(DEST, "umat")
MAX_BYTES = 64 << 20                      # a companion larger than this is not fetched
_INPUT = re.compile(r'(?i)\binput\s*=\s*("[^"]*"|[^,]*)')


def download(url):
    req = urllib.request.Request(url, headers={"User-Agent": "abq2ccx-corpus"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError(f"larger than {MAX_BYTES >> 20} MB")
    return data


def input_names(text):
    """The relative file names the keyword lines of ``text`` read with INPUT=, in order
    (a keyword line ending in a comma continues on the next line)."""
    names, lines, i = [], text.splitlines(), 0
    while i < len(lines):
        line = lines[i].lstrip()
        if line.startswith("*") and not line.startswith("**"):
            while line.rstrip().endswith(",") and i + 1 < len(lines) and \
                    not lines[i + 1].lstrip().startswith("*"):
                i += 1
                line = line.rstrip() + lines[i]
            for m in _INPUT.finditer(line):
                name = m.group(1).strip().strip('"').strip().replace("\\", "/")
                if name and name not in names:
                    names.append(name)
        i += 1
    return names


def companions(entry, text, dest, written, reserved):
    """Fetch the files deck ``entry`` (its text ``text``) reads with INPUT=, recursively, into
    ``dest``: a name resolves against the deck's directory (Abaqus' job directory), else the
    including file's, and lands at that relative path.  ``written``: local path -> (bytes,
    deck) of this run; ``reserved``: deck file paths no companion may replace.  Returns
    (fetched, missing, conflicts) lists of messages / paths."""
    fetched, missing, conflicts = [], [], []
    todo = [(name, "") for name in input_names(text)]
    seen = set()
    while todo:
        name, sub = todo.pop(0)
        if (name, sub) in seen:
            continue
        seen.add((name, sub))
        if os.path.isabs(name) or re.match(r"[A-Za-z]:", name):
            missing.append(f"{name} (an absolute path)")
            continue
        data = local = None
        why = "outside the corpus directory"
        for rel in dict.fromkeys(os.path.normpath(r) for r in (name, os.path.join(sub, name))):
            if rel.startswith(".."):
                continue
            try:
                data = download(urllib.parse.urljoin(entry["url"], urllib.parse.quote(rel)))
                local = os.path.join(dest, rel)
                break
            except Exception as exc:  # noqa: BLE001
                why = str(exc)
        if data is None:
            missing.append(f"{name} ({why})")
            continue
        if local in reserved or (local in written and written[local][0] != data):
            conflicts.append(local)
            continue
        if local not in written:
            os.makedirs(os.path.dirname(local), exist_ok=True)
            with open(local, "wb") as fh:            # bytes as fetched
                fh.write(data)
            written[local] = (data, entry["name"])
        fetched.append(os.path.relpath(local, dest))
        nested = os.path.dirname(os.path.relpath(local, dest))
        todo += [(n, nested) for n in input_names(data.decode("utf-8", "replace"))]
    return fetched, missing, conflicts


def umat_files(repo, src, dest):
    """Fetch the files of UMAT source repository ``repo`` (``src``: manifest.UMAT_SOURCES[repo],
    the commit and each file's sha256) into ``dest``/<owner>__<repository>/ at their paths; a
    file already there with the pinned contents is kept.  Returns (fetched, failed) lists."""
    root = os.path.join(dest, repo.replace("/", "__"))
    fetched, failed = [], []
    for path, sha in sorted(src["files"].items()):
        parts = path.split("/")
        if path.startswith("/") or ".." in parts or ":" in path:
            failed.append(f"{path}: not a path inside the repository")
            continue
        local = os.path.join(root, *parts)
        if os.path.exists(local):
            with open(local, "rb") as fh:
                if hashlib.sha256(fh.read()).hexdigest() == sha:
                    continue
        url = f"https://raw.githubusercontent.com/{repo}/{src['sha']}/{urllib.parse.quote(path)}"
        try:
            data = download(url)
            if hashlib.sha256(data).hexdigest() != sha:
                raise ValueError("its sha256 is not the manifest's")
        except Exception as exc:  # noqa: BLE001
            failed.append(f"{path}: {exc}")
            continue
        os.makedirs(os.path.dirname(local), exist_ok=True)
        with open(local, "wb") as fh:
            fh.write(data)
        fetched.append(path)
    return fetched, failed


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if args not in ([], ["--companions"], ["--umat"]):  # --help or a typo: no full download
        print("usage:\n" + __doc__.split("\n\n")[1], file=sys.stderr)
        return 2
    if args == ["--umat"]:
        fail = 0
        for repo, src in sorted(UMAT_SOURCES.items()):
            got, failed = umat_files(repo, src, UMAT_DEST)
            print(f"  {'FAIL' if failed else 'ok  '} {repo} @ {src['sha'][:12]}  [{src['license']}]")
            for path in got:
                print(f"       + {path}")
            for msg in failed:
                print(f"       - {msg}")
            fail += bool(failed)
        print(f"\n{len(UMAT_SOURCES) - fail} repositories ok, {fail} failed -> {UMAT_DEST}")
        return 1 if fail else 0
    only = args == ["--companions"]
    os.makedirs(DEST, exist_ok=True)
    ok = fail = 0
    written, conflicts = {}, set()
    reserved = {os.path.join(DEST, e["name"] + ".inp") for e in CORPUS}
    for entry in CORPUS:
        path = os.path.join(DEST, entry["name"] + ".inp")
        try:
            if only:
                if not os.path.exists(path):
                    continue
                with open(path, encoding="utf-8", errors="replace", newline="") as fh:
                    data = fh.read()
            else:
                data = download(entry["url"]).decode("utf-8", "replace")
                if "*" not in data:
                    raise ValueError("downloaded content does not look like an .inp deck")
                with open(path, "w", encoding="utf-8", newline="") as fh:  # line ends as fetched
                    fh.write(data)
                print(f"  ok   {entry['name']:28s} ({len(data.splitlines())} lines)  [{entry['license']}]")
                ok += 1
        except Exception as exc:  # noqa: BLE001
            print(f"  FAIL {entry['name']:28s} {exc}")
            fail += 1
            continue
        got, miss, clash = companions(entry, data, DEST, written, reserved)
        for name in got:
            print(f"       + {name}")
        for name in miss:
            print(f"       - {name}: not found next to the deck")
        conflicts.update(clash)
    for local in sorted(conflicts):           # needed with other contents by another deck
        if local not in reserved and os.path.exists(local):
            os.remove(local)
        print(f"  CONFLICT {os.path.relpath(local, DEST)}: decks need different files of this "
              f"name; left out")
    if not only:
        print(f"\n{ok} downloaded, {fail} failed -> {DEST}")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
