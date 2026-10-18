"""Prepare private Disc 1 inputs for a PSXRecomp runtime build.

Uses all five discs for identification; only Disc 1 is enabled for execution.
Does not modify images, download tools, build code, or publish game data.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys


def quoted(value):
    return json.dumps(str(value), ensure_ascii=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--framework", required=True, type=Path)
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("cues", nargs=5, type=Path, help="Disc 1 through Disc 5 in order")
    args = ap.parse_args()
    framework = args.framework.resolve()
    output = args.output.resolve()
    source_repo = Path(__file__).resolve().parents[2]
    if output.is_relative_to(source_repo) or source_repo.is_relative_to(output):
        ap.error("Private runtime output must be outside the source repository and its parents")
    if not (framework / "bios/OpenBIOS.toml").is_file():
        ap.error("Framework checkout is missing bios/OpenBIOS.toml")
    subprocess.run(
        [sys.executable, str(Path(__file__).with_name("probe_set.py")),
         "--framework", str(framework), "--output", str(output), "--prepare-disc1",
         *[str(p.resolve()) for p in args.cues]], check=True,
    )
    first = json.loads((output / "assessment.json").read_text(encoding="utf-8"))["discs"][0]
    # Absolute paths are machine-local and never committed. The complete source
    # disc remains mounted; only the emitter uses the bounded executable view.
    sections = {
        "game": {
            "name": "Tokimeki Memorial 2 English - Disc 1 Research",
            "id": first["serial"], "players": 1,
            "exe": (output / "boot-loaded.exe").as_posix(),
            "disc": args.cues[0].resolve().as_posix(),
            **{key: first[key] for key in ("load_address", "entry_pc", "text_size", "stack_base")},
        },
        "recompiler": {
            "bios_config": (framework / "bios/OpenBIOS.toml").as_posix(),
            "seeds": (output / "seeds.txt").as_posix(),
            "out_dir": (output / "generated").as_posix(), "strict": True,
        },
        "runtime": {
            "window_title": "Tokimeki Memorial 2 - Recompilation Research",
            "memcard_dir": (output / "saves").as_posix(), "overlay_cache": False,
        },
        "video": {"renderer": "software", "aspect_ratio": "4:3"},
        "controller": {"default_mode": "digital"},
    }
    lines = ["# Local research inputs; generated from verified disc probes."]
    for name, fields in sections.items():
        lines.extend(["", f"[{name}]"])
        for key, value in fields.items():
            encoded = (str(value).lower() if isinstance(value, bool) else
                       str(value) if isinstance(value, int) else quoted(value))
            lines.append(f"{key} = {encoded}")
    (output / "game.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(output / "game.toml")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
