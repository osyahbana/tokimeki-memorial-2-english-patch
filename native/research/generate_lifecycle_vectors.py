"""Generate F0 reset/event and direct-completion vectors from a supplied module.

Usage: python generate_lifecycle_vectors.py ENGINE_MODULE --output lifecycle-vectors.json
Uses Unicorn only for research; outputs synthetic state, not game bytes.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

import unicorn
from unicorn import Uc, UC_ARCH_MIPS, UC_MODE_MIPS32, UC_MODE_LITTLE_ENDIAN
from unicorn.mips_const import UC_MIPS_REG_S2, UC_MIPS_REG_S6, UC_MIPS_REG_PC

RESET_FIELDS = [(0x8011b574, 4), (0x80111550, 4), (0x8011b5b0, 4),
                (0x80111554, 4), (0x8011b3c0, 4), (0x8011b570, 4),
                (0x8011b5ac, 1), (0x8011b534, 4)]


def variable_address(slot):
    return 0x11b550 + slot * 4 if slot < 8 else 0x11b588 + (slot - 8) * 4


def create(module):
    mu = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 | UC_MODE_LITTLE_ENDIAN)
    mu.mem_map(0, 0x200000)
    mu.mem_write(0xc0000, module)
    return mu


def write(mu, address, value, width=4):
    mu.mem_write(address & 0x1fffffff, (value & ((1 << (8 * width)) - 1)).to_bytes(width, "little"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("module", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.module.resolve() == args.output.resolve():
        parser.error("Output must differ from input module")
    module = args.module.read_bytes()
    # Verify against the module already used by the expression oracle. Accept no
    # alternate code in this lifecycle reproduction without a new investigation.
    digest = hashlib.sha256(module).hexdigest()
    if digest != "13267eac4b5f31bf8d07facd29faecd890d74368a5180d483b95a9a4c8d0c548":
        raise ValueError("This lifecycle oracle requires the documented prior extracted module hash")
    reset_vectors = []
    for initial in [list(range(1, 17)), [-2147483648, -1, 0, 1] * 4, [2147483647] * 16]:
        mu = create(module)
        for slot, value in enumerate(initial):
            write(mu, variable_address(slot), value)
        for address, width in RESET_FIELDS:
            write(mu, address, 0x5a if width == 1 else 0x12345678, width)
        write(mu, 0x8011b3cc, 0x80181235)
        mu.mem_write(0x190000, bytes([0xa5] * 8))
        mu.reg_write(UC_MIPS_REG_S2, 0x80190000)
        mu.reg_write(UC_MIPS_REG_S6, 0x80120000)
        mu.emu_start(0x800e61a4, 0x800e63f8, count=500)
        if mu.reg_read(UC_MIPS_REG_PC) != 0x800e63f8:
            raise RuntimeError("F0 did not return via its documented epilogue")
        final = [struct.unpack("<i", mu.mem_read(variable_address(i), 4))[0] for i in range(16)]
        fields = [{"address": f"0x{a:08x}", "width": w,
                   "initialValue": 0x5a if w == 1 else 0x12345678,
                   "expectedValue": int.from_bytes(mu.mem_read(a & 0x1fffffff, w), "little")}
                  for a, w in RESET_FIELDS]
        event = bytes(mu.mem_read(0x190000, 8)).hex()
        pointer = int.from_bytes(mu.mem_read(0x11b3cc, 4), "little")
        assert final == [0] * 8 + initial[8:]
        assert all(f["expectedValue"] == 0 for f in fields)
        assert event == "010c000000000000" and pointer == 0x80181235
        reset_vectors.append({"initialVariables": initial, "finalVariables": final,
                              "resetFields": fields, "expectedEventHex": event,
                              "initialPc": 0x80181235, "expectedPc": pointer})
    host_vectors = []
    # Stop at the caller return or first unimplemented executable service.
    for scene_tag, current_tag, resource_byte in [(0, 0, 1), (5, 5, 11), (255, 255, 251),
                                                  (2, 3, 1), (255, 0, 21), (7, 7, 2)]:
        # Both return branches leave the VM resume gate unchanged. The other
        # branch clears it before invoking an external service. Do not infer
        # pending/completed from return address alone.
        from unicorn import UC_HOOK_CODE
        observed = []
        mu = create(module)
        write(mu, 0x8011c104, 0)
        write(mu, 0x8011c10c, 1)
        write(mu, 0x8011c2c4, 0x80160000)
        write(mu, 0x8016003c, scene_tag, 1)
        write(mu, 0x8016003d, resource_byte, 1)
        write(mu, 0x80076bee, current_tag, 1)
        def hook(uc, address, size, data):
            if address in (0x800f6b0c, 0x800f6b10, 0x8003caa0):
                observed.append(address)
                uc.emu_stop()
        mu.hook_add(UC_HOOK_CODE, hook)
        mu.emu_start(0x800f4028, 0, count=100)
        transition = scene_tag == current_tag and resource_byte % 10 != 1
        gate = int.from_bytes(mu.mem_read(0x11c10c, 4), "little")
        expected_stop = 0x8003caa0 if transition else (0x800f6b0c if scene_tag == current_tag else 0x800f6b10)
        assert observed == [expected_stop]
        assert gate == (0 if transition else 1)
        host_vectors.append({"hostPhase": 0, "sceneContextByte3c": scene_tag,
                             "currentTag": current_tag, "sceneContextByte3d": resource_byte,
                             "initialResumeGate": 1, "expectedResumeGate": gate,
                             "expectedExternalTransition": transition,
                             "observedStopAddress": f"0x{observed[0]:08x}"})
    result = {"schemaVersion": 1, "moduleSha256": digest, "unicornVersion": unicorn.__version__,
              "resetVectors": reset_vectors, "hostDirectCompletionVectors": host_vectors,
              "limitations": ["F0 is not a no-op: it resets state and returns a pending host event",
                              "The context-byte meaning and nontrivial resource transition are not reconstructed",
                              "External service behavior is not tested; no helper returns are fabricated"]}
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Verified {len(reset_vectors)} reset vectors and {len(host_vectors)} host condition vectors")


if __name__ == "__main__":
    main()
