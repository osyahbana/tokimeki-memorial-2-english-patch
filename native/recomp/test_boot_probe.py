from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import Mock

from boot_probe import checkpoint_slot, check_fallback_budget, read_input_route, start_input_route


class CheckpointIdentityTests(unittest.TestCase):
    def check(self, name, entry="0x800175C8", bios="OpenBIOS", present=True):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game = root / "game.toml"
            game.write_text(f'[game]\nentry_pc = "{entry}"\n'
                            f'[recompiler]\nbios_config = "bios/{bios}.toml"\n')
            state = root / name
            if present:
                state.write_bytes(b"synthetic checkpoint identity fixture")
            result = checkpoint_slot(state, game)
            self.assertEqual(state.read_bytes(), b"synthetic checkpoint identity fixture")
            return result

    def test_matching_slot_identity_is_read_only(self):
        self.assertEqual(self.check("state_800175C8_slot08.pst"), 8)

    def test_another_game_or_bios_is_rejected(self):
        with self.assertRaises(ValueError):
            self.check("state_80010000_slot08.pst")
        with self.assertRaises(ValueError):
            self.check("state_800175C8_slot08.pst", bios="OtherBIOS")

    def test_invalid_slot_or_name_is_rejected(self):
        for name in ("state_800175C8_slot12.pst", "state_800175C8_slot-1.pst", "arbitrary.pst"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.check(name)

    def test_missing_state_is_rejected_before_launch(self):
        with self.assertRaises(ValueError):
            self.check("state_800175C8_slot08.pst", present=False)


class ReplayTests(unittest.TestCase):
    def read_route(self, steps):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "route.json"
            path.write_text(json.dumps(steps))
            return read_input_route(path)

    def test_pad_route_rejects_commands_and_invalid_durations(self):
        for step in ({"cmd": "quit"}, {"buttons": 65535, "frames": 0},
                     {"buttons": 65536, "frames": 1}, {"buttons": True, "frames": 1}):
            with self.subTest(step=step), self.assertRaises(ValueError):
                self.read_route([step])

    def test_route_releases_buttons_and_has_bounded_total_duration(self):
        neutral = {"buttons": 65535, "frames": 1000000}
        self.assertEqual(self.read_route([neutral]), [neutral])
        for route in ([], [neutral, neutral], [{"buttons": 57343, "frames": 3}]):
            with self.subTest(route=route), self.assertRaises(ValueError):
                self.read_route(route)

    def test_rejected_or_uncertain_mutation_is_not_replayed(self):
        for result in ({"ok": False}, OSError("connection lost")):
            client = Mock()
            client.query.side_effect = [{"ok": True}, result]
            with self.subTest(result=result), self.assertRaises(RuntimeError):
                start_input_route(client, 44362, [{"buttons": 65535, "frames": 1}])
            self.assertEqual(client.query.call_count, 2)


class FallbackBudgetTests(unittest.TestCase):
    def test_counts_only_after_checkpoint_baseline(self):
        baseline = {"ok": True, "insns_run": 900}
        self.assertTrue(check_fallback_budget(baseline, baseline, 0)["passed"])
        result = check_fallback_budget(baseline, {"ok": True, "insns_run": 901}, 0)
        self.assertFalse(result["passed"])
        self.assertEqual(result["additional_instructions"], 1)

    def test_missing_failed_or_reset_counters_fail_closed(self):
        baseline = {"ok": True, "insns_run": 900}
        for final in ({}, {"ok": False, "insns_run": 900},
                      {"ok": True, "insns_run": 899}, {"ok": True, "insns_run": True}):
            with self.subTest(final=final):
                result = check_fallback_budget(baseline, final, 1000)
                self.assertFalse(result["passed"])
                self.assertIsNone(result["additional_instructions"])


if __name__ == "__main__":
    unittest.main()
