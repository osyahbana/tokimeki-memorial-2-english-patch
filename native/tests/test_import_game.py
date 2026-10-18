import hashlib
import io
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

NATIVE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(NATIVE))
import import_game as importer


def scene(code):
    header = bytearray(32)
    header[:4] = b"\x38\x35\0\0"
    struct.pack_into("<HH", header, 4, 32, 1)
    header[24:32] = b"TEST000\0"
    return bytes(header) + code


def decode(raw, **kwargs):
    defaults = dict(disc=1, key="TEST000-12345678", scene_id="TEST000", source_offset=4096,
                    revision="original", tl={}, names={})
    defaults.update(kwargs)
    return importer.decode_scene(raw, **defaults)


class BytecodeTests(unittest.TestCase):
    def test_cfg_keeps_relative_jumps_and_reachable_offsets(self):
        # goto skips an invalid opcode and reaches FF, rather than a linear list.
        result = decode(scene(b"\x31\x01\x00\x77\xff"))
        self.assertEqual([x["offset"] for x in result["instructions"]], [32, 36])
        branch = result["instructions"][0]
        self.assertEqual((branch["next"], branch["target"], branch["operands"]), (35, 36, "0100"))
        self.assertEqual(result["resourceId"], "disc1/TEST000-12345678@1000")

    def test_conditional_preserves_both_successors(self):
        result = decode(scene(b"\x30\x4e\x01\x00\x01\x00\xff\xff"))
        self.assertEqual([x["offset"] for x in result["instructions"]], [32, 38, 39])
        self.assertEqual(result["instructions"][0]["target"], 39)

    def test_backward_branch_is_not_rewritten(self):
        result = decode(scene(b"\x31\xfd\xff"))
        self.assertEqual(result["instructions"][0]["target"], 32)

    def test_malformed_boundaries_and_operand_targets_rejected(self):
        for code in [b"\x17", b"\x10\x81", b"\x31\x7f\x00", b"\x31\xff\xff", b"\x00"]:
            with self.subTest(code=code), self.assertRaises(importer.ImportFailure):
                decode(scene(code))
        with self.assertRaises(importer.ImportFailure):
            decode(b"short")

    def test_text_is_overlaid_without_moving_instructions(self):
        japanese = "あ".encode("cp932").translate(importer.script.SWAP)
        raw = scene(b"\x10" + japanese + b"\0\xff")
        result = decode(raw, tl={"TEST000-12345678": {"32": "Hello"}})
        instruction = result["instructions"][0]
        self.assertEqual(instruction["text"], "Hello")
        self.assertEqual(instruction["originalText"], "あ")
        self.assertEqual((instruction["offset"], instruction["next"]), (32, 36))
        patched = decode(raw, revision="english-patched", tl={"TEST000-12345678": {"32": "Wrong overlay"}})
        self.assertEqual(patched["instructions"][0]["text"], "あ")


class IdentityTests(unittest.TestCase):
    def test_extraction_verifies_exact_bytes_even_if_size_and_timestamp_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "disc.bin"
            original = bytes(24) + b"x" * 2048 + bytes(280)
            path.write_bytes(original)
            digest = hashlib.sha256(original).hexdigest()
            self.assertEqual(importer.read_verified_user_data(path, digest), b"x" * 2048)
            stamp = path.stat()
            changed = bytearray(original)
            changed[24] = ord("y")
            path.write_bytes(changed)
            os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
            with self.assertRaisesRegex(importer.ImportFailure, "changed after identification"):
                importer.read_verified_user_data(path, digest)
            path.write_bytes(b"truncated")
            with self.assertRaisesRegex(importer.ImportFailure, "truncated"):
                importer.read_verified_user_data(path, digest)

    def test_known_catalog_has_all_original_and_patched_discs(self):
        known = importer.supported_images()
        self.assertEqual(len(known), 10)
        for revision in ["original", "english-patched"]:
            self.assertEqual({x["number"] for x in known.values() if x["revision"] == revision}, set(range(1, 6)))

    def test_unknown_hash_wrong_sector_size_and_duplicate_discs_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Disc 5.bin"
            path.write_bytes(bytes(2352))
            known = {hashlib.sha256(path.read_bytes()).hexdigest():
                     {"number": 1, "revision": "original", "serial": "SLPM_863.55"}}
            with self.assertRaisesRegex(importer.ImportFailure, "Unsupported image"):
                importer.identify_discs([path], True, {})
            found = importer.identify_discs([path], True, known)
            self.assertEqual(found[0][1]["number"], 1)  # filename must not decide identity
            with self.assertRaisesRegex(importer.ImportFailure, "Duplicate Disc"):
                importer.identify_discs([path, path], True, known)
            with self.assertRaisesRegex(importer.ImportFailure, "five discs"):
                importer.identify_discs([path], False, known)
            path.write_bytes(b"truncated")
            with self.assertRaisesRegex(importer.ImportFailure, "MODE2/2352"):
                importer.identify_discs([path], True, known)


class PublicationTests(unittest.TestCase):
    def test_late_failure_leaves_no_partial_catalog(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "content"
            identified = [(Path("one.bin"), {"number": 1}), (Path("two.bin"), {"number": 2})]
            def export(path, identity, stage, tl, names):
                if identity["number"] == 2:
                    raise importer.ImportFailure("second disc failed")
                (stage / "first.json").write_text("private game data")
                return []
            with patch.object(importer, "identify_discs", return_value=identified), \
                    patch.object(importer.translations, "load", return_value=({}, {})), \
                    patch.object(importer, "export_disc", side_effect=export), \
                    self.assertRaisesRegex(importer.ImportFailure, "second disc"):
                importer.import_game([], output)
            self.assertFalse(output.exists())
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_existing_output_is_never_modified(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "content"
            output.mkdir()
            (output / "keep").write_text("saved data")
            with self.assertRaisesRegex(importer.ImportFailure, "already exists"):
                importer.import_game([], output)
            self.assertEqual((output / "keep").read_text(), "saved data")

    def test_manifest_hash_is_deterministic_and_excludes_itself(self):
        with tempfile.TemporaryDirectory() as tmp:
            identity = {"number": 1, "revision": "original", "serial": "SLPM_863.55", "sha256": "a" * 64}
            with patch.object(importer, "identify_discs", return_value=[(Path("private/path.bin"), identity)]), \
                    patch.object(importer.translations, "load", return_value=({}, {})), \
                    patch.object(importer, "export_disc", return_value=[]), \
                    patch("sys.stdout", new=io.StringIO()):
                first = importer.import_game([], Path(tmp) / "a", True)
                second = importer.import_game([], Path(tmp) / "b", True)
            self.assertEqual(first, second)
            digest = first.pop("corpusId")
            self.assertEqual(digest, hashlib.sha256(importer.normalized_json(first)).hexdigest())
            self.assertNotIn("private", json.dumps(first))

    def test_scanned_instances_are_never_deduplicated_by_scene_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage = Path(tmp)
            image = stage / "image.bin"
            image.write_bytes(bytes(2352))
            data = scene(b"\xff").ljust(64, b"\0") + scene(b"\xff")
            blocks = [SimpleNamespace(off=off, key="TEST000-12345678", sid="TEST000") for off in (0, 64)]
            identity = {"number": 2, "revision": "original", "sha256": "a" * 64}
            with patch.object(importer, "read_verified_user_data", return_value=data), \
                    patch.object(importer.scenes, "scan", return_value=blocks), \
                    patch("sys.stdout", new=io.StringIO()):
                catalog = importer.export_disc(image, identity, stage, {}, {})
            self.assertEqual(len(catalog), 2)
            self.assertNotEqual(catalog[0]["resourceId"], catalog[1]["resourceId"])
            for record in catalog:
                self.assertEqual(record["sha256"], hashlib.sha256((stage / record["path"]).read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
