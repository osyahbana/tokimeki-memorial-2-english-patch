import base64
import copy
import json
from pathlib import Path
import tempfile
import unittest

from prepare_overlays import read_records, contextualize_entries


class EntryContextTests(unittest.TestCase):
    def pair(self):
        data = bytes(range(32))
        big = {"schema": "psxrecomp overlay capture v3", "load_addr": "0x800C0000",
               "size": 32, "guard_bytes": 4, "bytes_b64": base64.b64encode(data).decode(),
               "dispatch_entry_pcs": ["0x800C0000"]}
        small = {"schema": big["schema"], "load_addr": "0x800C0008", "size": 12,
                 "guard_bytes": 4, "bytes_b64": base64.b64encode(data[8:20]).decode(),
                 "dispatch_entry_pcs": ["0x800c0008"],
                 "dispatch_entry_segments": {"kuseg": ["0x000c0008"]}}
        return [big, small]

    def test_matching_context_preserves_raw_evidence_and_observed_segments(self):
        records = self.pair()
        before = copy.deepcopy(records)
        contextual, links = contextualize_entries(records)
        self.assertEqual(records, before)
        self.assertEqual(contextual[0]["dispatch_entry_pcs"], ["0x800C0000", "0x800C0008"])
        self.assertEqual(contextual[0]["dispatch_entry_segments"],
                         {"kseg0": ["0x800C0000"], "kuseg": ["0x000C0008"]})
        self.assertEqual(len(links), 1)
        self.assertNotIn("function_entry_pcs", contextual[0])

    def test_mismatch_in_code_or_guard_prevents_transfer(self):
        for offset in (0, 11):
            records = self.pair()
            data = bytearray(base64.b64decode(records[1]["bytes_b64"]))
            data[offset] ^= 255
            records[1]["bytes_b64"] = base64.b64encode(data).decode()
            with self.subTest(offset=offset):
                self.assertEqual(contextualize_entries(records)[1], [])

    def test_uncontained_or_guard_entry_is_not_transferred(self):
        records = self.pair()
        records[1]["load_addr"] = "0x800D0008"
        records[1]["dispatch_entry_pcs"] = ["0x800D0008"]
        records[1]["dispatch_entry_segments"] = {"kuseg": ["0x000D0008"]}
        self.assertEqual(contextualize_entries(records)[1], [])
        records = self.pair()
        records[1]["dispatch_entry_pcs"] = ["0x800C0010"]
        self.assertEqual(contextualize_entries(records)[1], [])

    def test_existing_implicit_kseg0_is_not_lost_when_adding_kuseg(self):
        records = self.pair()
        records[0]["dispatch_entry_pcs"].append("0x800C0008")
        contextual, _ = contextualize_entries(records)
        self.assertIn("0x800C0008", contextual[0]["dispatch_entry_segments"]["kseg0"])
        self.assertIn("0x000C0008", contextual[0]["dispatch_entry_segments"]["kuseg"])

    def test_full_variants_remain_distinct_when_only_fragment_matches(self):
        records = self.pair()
        variant = copy.deepcopy(records[0])
        data = bytearray(base64.b64decode(variant["bytes_b64"]))
        data[24] ^= 255
        variant["bytes_b64"] = base64.b64encode(data).decode()
        records.append(variant)
        contextual, links = contextualize_entries(records)
        self.assertEqual(len(contextual), 3)
        self.assertNotEqual(contextual[0]["bytes_b64"], contextual[2]["bytes_b64"])
        self.assertEqual(len(links), 2)


class CaptureIdentityTests(unittest.TestCase):
    def record(self):
        return {"schema": "psxrecomp overlay capture v3", "load_addr": "0x800C0000",
                "size": 8, "guard_bytes": 0, "bytes_b64": base64.b64encode(b"\0"*8).decode(),
                "dispatch_entry_pcs": ["0x800C0000"], "function_entry_pcs": [],
                "dispatch_entry_segments": {"kseg0": ["0x800C0000"]}}

    def read(self, records):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "captures.json"
            path.write_text(json.dumps(records), encoding="utf-8")
            return read_records([path])

    def test_identical_image_unions_entry_and_segment_evidence(self):
        first = self.record()
        second = copy.deepcopy(first)
        second["dispatch_entry_pcs"] = ["0x800C0004"]
        second["dispatch_entry_segments"] = {"kuseg": ["0x000C0004"]}
        merged = self.read([first, second])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["dispatch_entry_pcs"], ["0x800C0000", "0x800C0004"])
        self.assertEqual(merged[0]["dispatch_entry_segments"],
                         {"kseg0": ["0x800C0000"], "kuseg": ["0x000C0004"]})

    def test_same_address_different_bytes_remain_separate(self):
        first, second = self.record(), self.record()
        second["bytes_b64"] = base64.b64encode(b"\1"*8).decode()
        self.assertEqual(len(self.read([first, second])), 2)

    def test_conflicting_guard_rejected(self):
        first, second = self.record(), self.record()
        second["guard_bytes"] = 4
        with self.assertRaises(ValueError):
            self.read([first, second])

    def test_truncated_image_rejected(self):
        record = self.record()
        record["size"] = 12
        with self.assertRaises(ValueError):
            self.read([record])

    def test_unrecognized_evidence_is_not_silently_lost(self):
        record = self.record()
        record["future_proof"] = [1]
        with self.assertRaises(ValueError):
            self.read([record])

    def test_invalid_segment_on_first_record_rejected(self):
        record = self.record()
        record["dispatch_entry_segments"] = {"unknown": []}
        with self.assertRaises(ValueError):
            self.read([record])

    def test_only_declared_guard_can_extend_past_ram(self):
        record = self.record()
        record["load_addr"] = "0x801FFFFC"
        with self.assertRaises(ValueError):
            self.read([record])
        record["guard_bytes"] = 4
        self.assertEqual(len(self.read([record])), 1)


if __name__ == "__main__":
    unittest.main()
