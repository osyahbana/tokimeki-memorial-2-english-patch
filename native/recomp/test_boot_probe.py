from pathlib import Path
import tempfile
import unittest

from boot_probe import checkpoint_slot


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


if __name__ == "__main__":
    unittest.main()
