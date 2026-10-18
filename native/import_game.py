"""Import a local, hash-identified five-disc set for native engine research.

This exports scanned script control flow, not a reachable-gameplay catalog.
originalText is decoded text in the supplied image (already English for a
patched image). No copyrighted content is downloaded or bundled here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import extract_scripts as extract
import scenes
import script
import translations


class ImportFailure(ValueError):
    """An input failed identity, structure, or publication validation."""


def normalized_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_verified_user_data(path, expected_sha256):
    """Hash the same bytes that produce the exported data, closing identity races.

    This uses the upstream MODE2/2352 sector layout. A second independent hash
    before or after extraction would not bind the extracted bytes themselves.
    """
    digest = hashlib.sha256()
    data = bytearray()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(2352 * 4096), b""):
            if len(chunk) % 2352:
                raise ImportFailure("Disc became truncated during import")
            digest.update(chunk)
            for offset in range(0, len(chunk), 2352):
                data.extend(chunk[offset + 24:offset + 2072])
    if digest.hexdigest() != expected_sha256:
        raise ImportFailure("Disc changed after identification; extracted bytes have a different SHA-256")
    return bytes(data)


def supported_images():
    originals = json.loads((ROOT / "docs/supported-images.json").read_text(encoding="utf-8-sig"))
    builds = json.loads((ROOT / "docs/integration-results.json").read_text(encoding="utf-8-sig"))
    known = {}
    for entry in originals["images"]:
        known[entry["sha256"]] = {"number": entry["disc"], "revision": "original", "serial": entry["exe"]}
    for result in builds["images"]:
        if not result["passed"]:
            continue
        source = known[result["sectors"]["source_sha256"]]
        known[result["sectors"]["output_sha256"]] = dict(source, revision="english-patched")
    return known


def identify_discs(paths, allow_subset=False, known=None):
    """Identify by full-file hash, never filename or a guessed scene name."""
    known = supported_images() if known is None else known
    found = {}
    for path in paths:
        path = Path(path).resolve(strict=True)
        if not path.is_file() or path.stat().st_size % 2352:
            raise ImportFailure(f"Expected a complete MODE2/2352 BIN: {path.name}")
        digest = sha256_file(path)
        if digest not in known:
            raise ImportFailure(f"Unsupported image SHA-256 {digest}: {path.name}")
        identity = dict(known[digest], sha256=digest)
        number = identity["number"]
        if number not in range(1, 6):
            raise ImportFailure("Invalid supported disc number")
        if number in found:
            raise ImportFailure(f"Duplicate Disc {number}; provide exactly one version of each disc")
        found[number] = (path, identity)
    if not found:
        raise ImportFailure("No BIN images found")
    if not allow_subset and set(found) != set(range(1, 6)):
        raise ImportFailure("All five discs are required (use --allow-subset only for research)")
    return [found[number] for number in sorted(found)]


def decode_scene(raw, *, disc, key, scene_id, source_offset, revision, tl, names):
    """Preserve original local addresses and CFG, validating every edge and span."""
    try:
        header = script.parse_block(raw)
        entry = header["code"]
        if not 0x20 <= entry < len(raw) or len(raw) > 0x10000:
            raise ImportFailure("Invalid scene entry or extent")
        code = script.walk(raw, entry, lo=entry, hi=len(raw))
        occupied = set()
        for at, (_, _, nxt) in sorted(code.items()):
            if not entry <= at < nxt <= len(raw):
                raise ImportFailure("Instruction extends outside scene")
            span = set(range(at, nxt))
            if occupied.intersection(span):
                raise ImportFailure("Control flow enters an instruction operand")
            occupied.update(span)
        instructions = []
        for at, (op, tokens, nxt) in sorted(code.items()):
            target = None
            if op in (0x30, 0x31):
                target = nxt + struct.unpack_from("<h", raw, nxt - 2)[0]
                if target not in code:
                    raise ImportFailure("Branch target outside decoded instructions")
            if op not in (0x31, 0xFF) and nxt not in code:
                raise ImportFailure("Fallthrough outside decoded instructions")
            original = extract.fmt_tokens(tokens) if tokens is not None else None
            text = original
            if original is not None and revision == "original":
                text = names.get(original, original) if op == 0x18 else tl.get(key, {}).get(str(at), original)
            instructions.append({"offset": at, "opcode": op, "next": nxt,
                                 "operands": raw[at + 1:nxt].hex(), "text": text,
                                 "originalText": original, "target": target})
    except (script.ScriptError, IndexError, struct.error, UnicodeError) as error:
        raise ImportFailure(f"Malformed bytecode in {key}: {error}") from error
    return {"formatVersion": 1, "discovery": "bytecode-scan",
            "resourceId": f"disc{disc}/{key}@{source_offset:x}", "disc": disc,
            "key": key, "sceneId": scene_id, "sourceOffset": source_offset,
            "entry": entry, "byteLength": len(raw), "instructions": instructions}


def export_disc(path, identity, stage, tl, names):
    data = read_verified_user_data(path, identity["sha256"])
    catalog = []
    number = identity["number"]
    blocks = sorted(scenes.scan(data), key=lambda block: block.off)
    if not blocks:
        raise ImportFailure(f"No scene bytecode discovered on Disc {number}")
    for block in blocks:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", block.key):
            raise ImportFailure("Unsafe scene key")
        # Upstream's scan records end at the final instruction's opcode. All
        # accepted scene spans must include its entire operands as well.
        window = data[block.off:block.off + 0x10000]
        try:
            entry = script.parse_block(window)["code"]
            code = script.walk(window, entry, lo=entry, hi=len(window))
            extent = max(nxt for _, _, nxt in code.values())
        except (script.ScriptError, IndexError, struct.error, UnicodeError) as error:
            raise ImportFailure(f"Invalid scanned scene {block.key}: {error}") from error
        document = decode_scene(window[:extent], disc=number, key=block.key,
                                scene_id=block.sid, source_offset=block.off,
                                revision=identity["revision"], tl=tl, names=names)
        relative = f"scenes/disc{number}/{block.key}@{block.off:x}.json"
        destination = stage / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            raise ImportFailure("Duplicate scene resource identifier")
        encoded = normalized_json(document) + b"\n"
        destination.write_bytes(encoded)
        instructions = document["instructions"]
        catalog.append({"resourceId": document["resourceId"], "disc": number,
                        "key": block.key, "sceneId": block.sid, "path": relative,
                        "sha256": hashlib.sha256(encoded).hexdigest(), "entry": entry,
                        "instructionCount": len(instructions),
                        "lineCount": sum(x["opcode"] in (0x10, 0x11) for x in instructions),
                        "sourceOffset": block.off})
    print(f"Disc {number}: {len(catalog)} scanned scenes; {sum(s['lineCount'] for s in catalog)} dialogue lines", flush=True)
    return catalog


def import_game(paths, output, allow_subset=False):
    """Publish one complete new directory; a failed import leaves no result."""
    output = Path(output).resolve()
    if output.exists():
        raise ImportFailure("Output already exists; choose a new directory")
    identified = identify_discs(paths, allow_subset)
    problems = []
    tl, names = translations.load([str(ROOT / "translations")], problems=problems)
    if problems:
        raise ImportFailure("Translation structure is invalid: " + problems[0])
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".tm2-import-", dir=output.parent))
    try:
        manifest = {"formatVersion": 1, "discovery": "bytecode-scan",
                    "reachability": "unresolved; relocated stale copies may be present",
                    "discs": [], "scenes": []}
        for path, identity in identified:
            manifest["discs"].append(identity)
            manifest["scenes"].extend(export_disc(path, identity, stage, tl, names))
        manifest["corpusId"] = hashlib.sha256(normalized_json(manifest)).hexdigest()
        (stage / "manifest.json").write_bytes(normalized_json(manifest) + b"\n")
        if output.exists():
            raise ImportFailure("Output was created during import; refusing to replace it")
        os.rename(stage, output)
    finally:
        # stage is the unique directory created above, never a supplied path.
        if stage.exists():
            shutil.rmtree(stage)
    print(f"Imported {len(manifest['discs'])} discs, {len(manifest['scenes'])} scenes. Corpus {manifest['corpusId']}")
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--disc-dir", type=Path, help="Folder containing all five supported BIN images")
    source.add_argument("--discs", type=Path, nargs="+", help="Explicit BIN images")
    parser.add_argument("--output", type=Path, required=True, help="New local content directory")
    parser.add_argument("--allow-subset", action="store_true", help="Research only: permit fewer than five discs")
    args = parser.parse_args(argv)
    try:
        if args.disc_dir:
            paths = sorted(p for p in args.disc_dir.iterdir() if p.is_file() and p.suffix.lower() == ".bin")
        else:
            paths = args.discs
        import_game(paths, args.output, args.allow_subset)
    except (ImportFailure, OSError) as error:
        parser.exit(1, f"Import failed: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
