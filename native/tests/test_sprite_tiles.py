"""Synthetic graphics structures only; no game bytes are bundled."""
import importlib.util
from pathlib import Path
import struct
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "research/export_sprite_tiles.py"
spec = importlib.util.spec_from_file_location("export_sprite_tiles", SOURCE)
tiles = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tiles)


def sample_container():
    raw = bytes(range(256)) * 64
    # Eight literal bytes per zero flag byte, then the LZ2 end marker.
    payload = b"".join(b"\0" + raw[i:i + 8] for i in range(0, len(raw), 8)) + b"\1\0\0"
    palette_start, palette_end, payload_start = 72, 584, 604
    endpoint = (payload_start + len(payload) + 3) & ~3
    blob = bytearray(endpoint + 32)
    struct.pack_into("<II", blob, 0, 1, 64)
    struct.pack_into("<II", blob, 40, 1, 68)
    struct.pack_into("<II", blob, 64, palette_end, endpoint)
    struct.pack_into("<256H", blob, palette_start, *range(256))
    struct.pack_into("<II", blob, palette_end, 0x100, palette_start)
    blob[payload_start:payload_start + len(payload)] = payload
    struct.pack_into("<III", blob, endpoint, 0x204, len(payload), payload_start)
    return blob, raw, endpoint


class SpriteTileTests(unittest.TestCase):
    def test_backward_descriptor_decodes_exact_pixels_and_palette(self):
        blob, raw, endpoint = sample_container()
        palettes, images = tiles.decode_container(blob)
        self.assertEqual(images[0]["indices"], raw)
        self.assertEqual(images[0]["offset"], 604)
        self.assertEqual(images[0]["descriptorOffset"], endpoint)
        self.assertEqual(palettes[0]["rgb"][31 * 3:32 * 3], bytes((255, 0, 0)))

    def test_payload_cannot_borrow_end_marker_from_next_descriptor(self):
        blob, _, endpoint = sample_container()
        # Remove the final end marker and padding without changing descriptors.
        blob[endpoint - 4:endpoint] = b"\0" * 4
        with self.assertRaises(tiles.importer.ImportFailure):
            tiles.decode_container(blob)

    def test_out_of_bounds_palette_and_payload_pointers_fail(self):
        for offset in (64,):
            blob, _, _ = sample_container()
            struct.pack_into("<I", blob, offset, len(blob) + 100)
            with self.assertRaises(tiles.importer.ImportFailure):
                tiles.decode_container(blob)
        blob, _, endpoint = sample_container()
        struct.pack_into("<I", blob, endpoint + 8, 0)
        with self.assertRaises(tiles.importer.ImportFailure):
            tiles.decode_container(blob)

    def test_trailing_data_is_not_silently_accepted(self):
        blob, _, _ = sample_container()
        with self.assertRaises(tiles.importer.ImportFailure):
            tiles.decode_container(blob + b"unexpected")


if __name__ == "__main__":
    unittest.main()
