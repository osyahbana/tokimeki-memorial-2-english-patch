"""Export bounded childhood sprite-tile candidates from a supported local Disc 1.

This is an asset research utility, not a scene renderer. PNG previews use RGB
only: per-tile palette selection and PS1 transparency are not established.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import import_game as importer
import compression

SAMPLES = {"YG_02506": 35550, "YG_04502": 49278, "YG_01503": 44747}


def span(blob, start, size):
    if start < 0 or size < 0 or start > len(blob) or size > len(blob) - start:
        raise importer.ImportFailure("Graphics field extends outside its container")
    return blob[start:start + size]


def words(blob, offset, count):
    return struct.unpack("<" + "I" * count, span(blob, offset, count * 4))


def decode_container(blob):
    """Return texture bytes and all same-container palette candidates.

    These containers put descriptors *after* their data: descriptor +8 is a
    backward pointer to the preceding compressed texture, not the next one.
    The decompressor receives only that bounded payload and cannot spill into
    the next packet or bundle part.
    """
    header = words(blob, 0, 12)
    palette_count, palette_table = header[:2]
    tile_count, tile_table = header[10:12]
    if not 1 <= palette_count <= 16 or not 1 <= tile_count <= 128:
        raise importer.ImportFailure("Unsupported palette or texture count")
    palette_ends = words(blob, palette_table, palette_count)
    tile_ends = words(blob, tile_table, tile_count)
    if list(palette_ends) != sorted(set(palette_ends)) or list(tile_ends) != sorted(set(tile_ends)):
        raise importer.ImportFailure("Descriptor offsets must be unique and increasing")
    palettes = []
    for end in palette_ends:
        descriptor = words(blob, end, 5)
        start = descriptor[1]
        if descriptor[0] != 0x100 or start + 512 != end:
            raise importer.ImportFailure("Unsupported palette descriptor")
        raw = span(blob, start, 512)
        values = struct.unpack("<256H", raw)
        colors = bytes(channel for value in values for channel in
                       ((value & 31) * 255 // 31,
                        ((value >> 5) & 31) * 255 // 31,
                        ((value >> 10) & 31) * 255 // 31))
        palettes.append({"offset": start, "descriptorOffset": end,
                         "sha256": hashlib.sha256(raw).hexdigest(),
                         "raw555": raw, "rgb": colors})
    tiles = []
    previous_end = palette_ends[-1] + 20
    for end in tile_ends:
        descriptor = words(blob, end, 8)
        start = descriptor[2]
        if descriptor[0] != 0x204 or start != previous_end or start >= end:
            raise importer.ImportFailure("Unsupported or overlapping texture descriptor")
        payload = span(blob, start, end - start)
        try:
            decoded, consumed = compression.lz2(payload, limit=16384)
        except (ValueError, IndexError) as error:
            raise importer.ImportFailure("Invalid bounded LZ2 texture") from error
        # Observed containers pad individual compressed streams to eight bytes.
        if (len(decoded) != 16384 or not 0 <= len(payload) - consumed <= 7
                or any(payload[consumed:])):
            raise importer.ImportFailure("Unexpected texture extent or padding")
        tiles.append({"offset": start, "descriptorOffset": end,
                      "compressedBytes": consumed,
                      "compressedSha256": hashlib.sha256(payload[:consumed]).hexdigest(),
                      "sha256": hashlib.sha256(decoded).hexdigest(), "indices": decoded})
        previous_end = end + 32
    if previous_end != len(blob):
        raise importer.ImportFailure("Unexpected bytes after final texture descriptor")
    return palettes, tiles


def bundle_parts(data, lba, scene_id):
    base = lba * 2048
    count = words(data, base, 1)[0]
    if count != 4:
        raise importer.ImportFailure("Expected a four-part childhood scene bundle")
    sizes = words(data, base + 4, count)
    if any(size <= 0 or size > 2 * 1024 * 1024 for size in sizes):
        raise importer.ImportFailure("Invalid bundle part size")
    start = base + 4 + count * 4
    parts = []
    for size in sizes:
        parts.append((start, span(data, start, size)))
        start += size
    script_blob = parts[0][1]
    if script_blob[:4] != b"\x38\x35\x00\x00" or script_blob[24:32].rstrip(b"\0") != scene_id.encode("ascii"):
        raise importer.ImportFailure("Scene identity differs at the expected bundle")
    return parts


def export_tiles(source, output):
    from PIL import Image
    output = Path(output).resolve()
    if output.exists():
        raise importer.ImportFailure("Output already exists; choose a new folder")
    if output == importer.ROOT or importer.ROOT in output.parents:
        raise importer.ImportFailure("Extracted game content must stay outside the source tree")
    identified = importer.identify_discs([source], allow_subset=True)
    path, identity = identified[0]
    if identity["number"] != 1:
        raise importer.ImportFailure("Only supported Disc 1 images contain these samples")
    data = importer.read_verified_user_data(path, identity["sha256"])
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".tm2-tiles-", dir=output.parent))
    manifest = {"formatVersion": 1, "disc": identity, "samples": [],
                "limitations": ["Texture tiles only; sprite composition and background linkage unresolved.",
                                "Every same-container palette is exported as a candidate; actual selection unresolved.",
                                "Previews are opaque RGB; PS1 transparency and semitransparency are not reproduced."]}
    try:
        for scene_id, lba in SAMPLES.items():
            sample = {"sceneId": scene_id, "bundleLba": lba, "parts": []}
            for index, (start, blob) in enumerate(bundle_parts(data, lba, scene_id)):
                if index < 2:
                    continue
                palettes, tiles = decode_container(blob)
                part = {"part": index, "sourceUserDataOffset": start, "byteLength": len(blob),
                        "sha256": hashlib.sha256(blob).hexdigest(), "palettes": [], "tiles": []}
                for palette_index, palette in enumerate(palettes):
                    entry = {k: v for k, v in palette.items() if k not in ("rgb", "raw555")}
                    entry.update(index=palette_index, sourceUserDataOffset=start + palette["offset"])
                    part["palettes"].append(entry)
                for tile_index, tile in enumerate(tiles):
                    entry = {k: v for k, v in tile.items() if k != "indices"}
                    entry.update(index=tile_index, sourceUserDataOffset=start + tile["offset"],
                                 width=128, height=128, layout="inferred-8bpp-tile", paletteCandidates=[])
                    for palette_index, palette in enumerate(palettes):
                        filename = f"{scene_id}-part{index}-tile{tile_index}-palette{palette_index}.png"
                        image = Image.frombytes("P", (128, 128), tile["indices"])
                        image.putpalette(palette["rgb"])
                        image.convert("RGB").save(stage / filename)
                        entry["paletteCandidates"].append({"palette": palette_index, "path": filename})
                    part["tiles"].append(entry)
                sample["parts"].append(part)
            manifest["samples"].append(sample)
        (stage / "sprite-tiles.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        if output.exists():
            raise importer.ImportFailure("Output appeared during extraction; refusing to replace it")
        os.rename(stage, output)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--disc", required=True, type=Path, help="Supported original or English-patched Disc 1 BIN")
    parser.add_argument("--output", required=True, type=Path, help="New private folder outside the source tree")
    args = parser.parse_args(argv)
    try:
        result = export_tiles(args.disc, args.output)
    except (importer.ImportFailure, OSError) as error:
        parser.exit(1, f"Extraction failed: {error}\n")
    print(f"Exported texture candidates from {len(result['samples'])} scene bundles")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
