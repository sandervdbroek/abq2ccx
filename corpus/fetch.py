#!/usr/bin/env python3
"""Download the corpus of real-world Abaqus decks listed in manifest.py.

    python corpus/fetch.py

Files land in ``corpus/files/`` (gitignored). Re-run any time; existing files are
overwritten. Requires network access (uses urllib from the standard library).
"""

import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from manifest import CORPUS  # noqa: E402

DEST = os.path.join(HERE, "files")


def main():
    os.makedirs(DEST, exist_ok=True)
    ok = fail = 0
    for entry in CORPUS:
        path = os.path.join(DEST, entry["name"] + ".inp")
        try:
            req = urllib.request.Request(entry["url"], headers={"User-Agent": "abq2ccx-corpus"})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read().decode("utf-8", "replace")
            if "*" not in data:
                raise ValueError("downloaded content does not look like an .inp deck")
            with open(path, "w") as fh:
                fh.write(data)
            print(f"  ok   {entry['name']:28s} ({len(data.splitlines())} lines)  [{entry['license']}]")
            ok += 1
        except Exception as exc:  # noqa: BLE001
            print(f"  FAIL {entry['name']:28s} {exc}")
            fail += 1
    print(f"\n{ok} downloaded, {fail} failed -> {DEST}")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
