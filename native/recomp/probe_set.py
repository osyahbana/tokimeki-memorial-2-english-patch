"""Reproduce the pinned PSXRecomp disc assessment without changing game images.

Requires Python 3.11+. Reports contain identities/counts, not game code.
--prepare-disc1 writes private analysis inputs; keep its output outside Git.
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import sys

REVISION = "53a057f548cd1f93f1b4d8300caaeded72f4160d"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--framework", required=True, type=Path)
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--prepare-disc1", action="store_true")
    ap.add_argument("cues", nargs=5, type=Path, help="Disc 1 through Disc 5, in order")
    args = ap.parse_args()
    root = args.framework.resolve()
    revision = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
    ).strip()
    if revision != REVISION:
        ap.error(f"Expected PSXRecomp {REVISION}; found {revision}. Review before repinning.")
    module_path = root / "tools/new_project_layout/probe_disc.py"
    changes = subprocess.check_output(
        ["git", "-C", str(root), "diff", "HEAD", "--", "tools/new_project_layout/probe_disc.py"],
        text=True,
    )
    if changes.strip():
        ap.error("Probe source has local modifications; use the pinned version.")
    if args.output.exists():
        ap.error("Output already exists; choose a new directory to preserve evidence.")
    probe = load_module("tm2_upstream_probe", module_path)
    results = [probe.probe(p.resolve()) for p in args.cues]
    expected = [f"SLPM-{n}" for n in range(86355, 86360)]
    if [p.serial for p in results] != expected:
        ap.error("Expected SLPM-86355 through SLPM-86359 in disc order.")
    loaded = []
    for p in results:
        data = p.boot_exe_bytes
        if data[:8] != b"PS-X EXE" or len(data) < 0x800:
            ap.error(f"Invalid executable: {p.serial}")
        size = struct.unpack_from("<I", data, 0x1C)[0]
        if size == 0 or 0x800 + size > len(data):
            ap.error(f"Invalid loaded image bounds: {p.serial}")
        loaded.append(data[0x800:0x800 + size])
    records = []
    for p, payload in zip(results, loaded):
        record = dataclasses.asdict(p)
        for key in ("cue_path", "boot_exe_bytes", "seed_addrs"):
            record.pop(key, None)
        base = loaded[0]
        record.update(
            exe_file_bytes=len(p.boot_exe_bytes),
            loaded_bytes=len(payload),
            loaded_sha256=hashlib.sha256(payload).hexdigest(),
            trailing_bytes=len(p.boot_exe_bytes) - 0x800 - len(payload),
            loaded_byte_differences_from_disc1=(
                sum(a != b for a, b in zip(base, payload)) + abs(len(base) - len(payload))
            ),
            loaded_difference_offsets_from_disc1=[
                f"0x{i:X}" for i, (a, b) in enumerate(zip(base, payload)) if a != b
            ],
        )
        records.append(record)
    args.output.mkdir(parents=True)
    report = {"framework_revision": revision, "discs": records}
    (args.output / "assessment.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if args.prepare_disc1:
        p = results[0]
        # Only an analysis view: trailing bytes may hold game data and are not
        # discarded from the original disc or any runtime resource provider.
        (args.output / "boot-loaded.exe").write_bytes(p.boot_exe_bytes[:0x800] + loaded[0])
        seeds = probe.render_seeds_file(
            [int(a, 16) for a in p.seed_addrs], boot_exe=p.boot_exe,
            entry=int(p.entry_pc, 16), load=int(p.load_address, 16), text=len(loaded[0]),
        )
        (args.output / "seeds.txt").write_text(seeds, encoding="utf-8")
    print(json.dumps({"disc_count": len(records), "loaded_differences": [r["loaded_byte_differences_from_disc1"] for r in records]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
