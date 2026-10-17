"""Build a verified Tokimeki Memorial 2 English disc set (Japan original or Rev 1)."""
import argparse
import os
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))


def cue_files(cue):
    """Accept the supported single-file, single-track MODE2/2352 layout."""
    cue = Path(cue)
    text = cue.read_text(encoding="utf-8-sig")
    files = re.findall(r'^\s*FILE\s+(?:"([^"\r\n]+)"|(\S+))\s+(\S+)\s*$', text, re.M | re.I)
    tracks = re.findall(r'^\s*TRACK\s+(\d+)\s+(\S+)\s*$', text, re.M | re.I)
    indexes = re.findall(r'^\s*INDEX\s+(\d+)\s+(\S+)\s*$', text, re.M | re.I)
    if len(files) != 1 or files[0][2].upper() != "BINARY" or len(tracks) != 1 or tracks[0][1].upper() != "MODE2/2352":
        raise ValueError(f"{cue.name}: only one BINARY file and one MODE2/2352 track are supported")
    if int(tracks[0][0]) != 1 or indexes != [("01", "00:00:00")] or re.search(r'^\s*(PREGAP|POSTGAP)\b', text, re.M | re.I):
        raise ValueError(f"{cue.name}: expected track 01 with INDEX 01 00:00:00 and no pregap")
    return [(cue.parent / (files[0][0] or files[0][1])).resolve()]


def same_path(a, b):
    a, b = Path(a), Path(b)
    return a.resolve() == b.resolve() or (a.exists() and b.exists() and os.path.samefile(a, b))


def find_discs(paths):
    import glyphpatch
    found, seen, candidates = [], set(), []
    for value in paths:
        path = Path(value)
        if path.is_dir():
            cues = sorted(p for p in path.iterdir() if p.suffix.lower() == ".cue")
            referenced = {p for cue in cues for p in cue_files(cue)}
            candidates.extend(cues)
            candidates.extend(sorted(p for p in path.iterdir() if p.suffix.lower() == ".bin" and p.resolve() not in referenced))
        else:
            candidates.append(path)
    for path in candidates:
        cue = path if path.suffix.lower() == ".cue" else None
        if path.suffix.lower() not in (".cue", ".bin"):
            raise ValueError(f"{path.name}: use single-track BIN/CUE images")
        binary = cue_files(cue)[0] if cue else path.resolve()
        if not binary.is_file():
            raise ValueError(f"Missing input image: {binary}")
        if binary in seen:
            continue
        seen.add(binary)
        with binary.open("rb") as f:
            name, _, _ = glyphpatch.find_exe(f)
        if name not in [f"SLPM_863.{n}" for n in range(55, 60)]:
            raise ValueError(f"{binary.name}: unexpected game serial {name}")
        found.append((int(name[-1]) - 4, binary, cue))
    return sorted(found, key=lambda row: row[0])


def main(argv=None):
    import build_patch
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", help="folder, CUE or BIN files")
    parser.add_argument("-o", "--output", type=Path)
    parser.add_argument("-f", "--force", action="store_true", help="replace previously built output files after validation")
    parser.add_argument("--tl", action="append", help="translation directories; later directories override earlier ones")
    parser.add_argument("--allow-partial", action="store_true", help="permit missing dialogue translations and record them in reports")
    args = parser.parse_args(argv)
    try:
        discs = find_discs(args.paths)
        if not discs:
            raise ValueError("No supported BIN/CUE disc images found")
        nums = [n for n, _, _ in discs]
        if len(nums) != len(set(nums)):
            raise ValueError("More than one input for the same disc; specify the intended files")
        first = discs[0][1]
        game = re.sub(r"\s*\(Disc \d\)", "", first.stem) or "Tokimeki Memorial 2"
        out = args.output or first.parent / (game + " [English]")
        playlist = "Tokimeki Memorial 2 English.m3u"
        protected = [p for _, b, c in discs for p in (b, c, b.with_suffix('.cue')) if p is not None]
        targets = [out / p.name for _, b, _ in discs for p in (b, b.with_suffix('.cue'), b.with_suffix('.report.json'))]
        targets.append(out / playlist)
        if any(same_path(a, b) for a in protected for b in targets):
            raise ValueError("Output would overwrite an original image or CUE; choose a separate folder")
        if len({str(p.resolve()).casefold() for p in targets}) != len(targets):
            raise ValueError("Output filenames collide; rename the input images first")
        if not args.force and any(p.exists() for p in targets):
            raise ValueError("Output files already exist; use -f to replace verified outputs")
        out.mkdir(parents=True, exist_ok=True)
        # Keep all requested outputs private until every disc validates. A
        # failed later disc must not replace earlier outputs or the playlist.
        with tempfile.TemporaryDirectory(prefix=".tm2-set-", dir=out) as tmp:
            stage = Path(tmp)
            cues = []
            for number, binary, _ in discs:
                print(f"=== Disc {number} ===", flush=True)
                options = [str(binary), str(stage / binary.name)]
                for directory in args.tl or []:
                    options += ["--tl", directory]
                if args.allow_partial:
                    options.append("--allow-partial")
                if build_patch.main(options):
                    print("Disc set failed validation; previous output files were preserved.")
                    return 1
                cues.append(binary.with_suffix('.cue').name)
            (stage / playlist).write_text("\n".join(cues) + "\n", encoding="utf-8")
            # Publish the playlist last. os.replace is atomic per file; this
            # is not a cross-file transaction against a power/storage failure.
            for item in sorted(stage.iterdir(), key=lambda p: p.name == playlist):
                os.replace(item, out / item.name)
        print(f"Done. Open {out / playlist}")
        return 0
    except (OSError, ValueError, AssertionError) as error:
        print(f"Cannot build patch: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    raise SystemExit(main())
