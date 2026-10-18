"""Produce synthetic expression oracle vectors from an explicitly supplied engine.

Usage: python generate_vm_vectors.py ENGINE_MODULE --output vm-vectors.json
Requires the optional analysis dependency `unicorn`; the native runtime does not.
The module must contain the verified original-release-compatible main evaluator
at file offset 0x24090, corresponding to RAM 0x800e4090. No ROM bytes are emitted.
"""
import argparse
import hashlib
import json
from pathlib import Path
import random
import struct

import unicorn
from unicorn import Uc, UC_ARCH_MIPS, UC_MODE_MIPS32, UC_MODE_LITTLE_ENDIAN
from unicorn.mips_const import UC_MIPS_REG_SP, UC_MIPS_REG_RA, UC_MIPS_REG_PC, UC_MIPS_REG_V0

RANGES = [
    (0x14e4, 0x15d0, "242d67a3c84d536e7443d583703e155b02558293220e54473ad94bc3c72bf515"),
    (0x24090, 0x245a4, "de23f62aab3ee49d31324e5ef8fd40562d4bfcecbb8de4e3a357820a053bb784"),
]
CODE = 0x80180000
POINTER = 0x11b3cc


def i32(v):
    return (v + 0x80000000) % 0x100000000 - 0x80000000


def constant(v):
    return bytes([0x4e]) + struct.pack("<h", v)


def variable_address(slot):
    if not 0 <= slot < 16:
        raise ValueError("Only ordinary variable slots 0..15 are supported")
    return 0x11b550 + slot * 4 if slot < 8 else 0x11b588 + (slot - 8) * 4


class Oracle:
    def __init__(self, module):
        for lo, hi, digest in RANGES:
            if hashlib.sha256(module[lo:hi]).hexdigest() != digest:
                raise ValueError(f"Unsupported module: range {lo:x}..{hi:x} differs")
        if len(module) > 0xc0000:
            raise ValueError("Supply the extracted engine module, not a complete image")
        self.mu = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 | UC_MODE_LITTLE_ENDIAN)
        self.mu.mem_map(0, 0x200000)
        self.mu.mem_write(0xc0000, module)

    def word(self, at, value):
        self.mu.mem_write(at, struct.pack("<I", value & 0xffffffff))

    def read(self, at):
        return struct.unpack("<I", self.mu.mem_read(at, 4))[0]

    def vector(self, name, expression, variables, expected):
        self.mu.mem_write(0x11b550, bytes(0x80))
        for slot, value in enumerate(variables):
            self.word(variable_address(slot), value)
        self.mu.mem_write(CODE & 0x1fffffff, expression)
        self.word(POINTER, CODE)
        self.mu.reg_write(UC_MIPS_REG_SP, 0x801ff000)
        self.mu.reg_write(UC_MIPS_REG_RA, 0x80000000)
        self.mu.emu_start(0x800e4090, 0x80000000, count=10000)
        if self.mu.reg_read(UC_MIPS_REG_PC) != 0x80000000:
            raise RuntimeError("Evaluator exceeded instruction budget")
        value = i32(self.mu.reg_read(UC_MIPS_REG_V0))
        consumed = self.read(POINTER) - CODE
        if value != expected or consumed != len(expression):
            raise AssertionError((name, value, expected, consumed))
        return {
            "name": name,
            "expressionHex": expression.hex(),
            "initialVariables": variables,
            "expectedValue": value,
            "expectedBytesConsumed": consumed,
            "finalVariables": [i32(self.read(variable_address(s))) for s in range(16)],
        }


def quotient(a, b):
    if b == 0:
        raise ValueError("Division by zero is deliberately excluded")
    return abs(a) // abs(b) * (-1 if (a < 0) != (b < 0) else 1)


def make_vectors(oracle):
    operations = {
        0x41: lambda a, b: i32(a + b), 0x42: lambda a, b: i32(a - b),
        0x43: lambda a, b: i32(a * b), 0x44: lambda a, b: i32(quotient(a, b)),
        0x45: lambda a, b: a - quotient(a, b) * b,
        0x47: lambda a, b: int(a < b), 0x48: lambda a, b: int(a > b),
        0x49: lambda a, b: int(a <= b), 0x4a: lambda a, b: int(a >= b),
        0x4b: lambda a, b: int(a == b), 0x4c: lambda a, b: int(a != b),
        0x58: lambda a, b: int(bool(a) or bool(b)),
        0x59: lambda a, b: int(bool(a) and bool(b)), 0x5b: lambda a, b: 0,
    }
    rng = random.Random(84090)
    vectors = []
    for op, function in operations.items():
        pairs = [(-7, 3), (7, -3), (0, 1), (1, 1), (-1, -1),
                 (2147483647, 2), (-2147483648, 2), (-2147483648, -1)]
        pairs += [(rng.randint(-0x80000000, 0x7fffffff),
                   rng.randint(-0x7fffffff, 0x7fffffff) or 1) for _ in range(16)]
        for index, (left, right) in enumerate(pairs):
            slots = [left, right] + [0] * 14
            vectors.append(oracle.vector(f"binary-{op:02x}-{index}",
                bytes([op, 0x4f, 0, 0x4f, 1]), slots, function(left, right)))
    for op, function in [(0x46, lambda v: i32(-v)), (0x5a, lambda v: int(v == 0)),
                         (0x40, lambda v: v)]:
        for value in [-2147483648, -32768, -1, 0, 1, 32767, 2147483647]:
            vectors.append(oracle.vector(f"unary-{op:02x}-{value}",
                bytes([op, 0x4f, 0]), [value] + [0] * 15, function(value)))
    for value in [-32768, -1, 0, 1, 32767]:
        vectors.append(oracle.vector(f"constant-{value}", constant(value), [0] * 16, value))
    for slot in range(16):
        before = [100 + n for n in range(16)]
        expression = bytes([0x4d, slot]) + constant(-1234)
        vector = oracle.vector(f"assign-slot-{slot}", expression, before, -1234)
        expected_slots = before.copy()
        expected_slots[slot] = -1234
        assert vector["finalVariables"] == expected_slots
        vectors.append(vector)
    for op, left, expected in [(0x58, 1, 1), (0x59, 0, 0), (0x5b, 7, 0)]:
        expression = bytes([op]) + constant(left) + bytes([0x4d, 2]) + constant(31)
        vector = oracle.vector(f"eager-{op:02x}", expression, [0] * 16, expected)
        assert vector["finalVariables"][2] == 31
        vectors.append(vector)
    # The right operand reads the side effect of the left assignment.
    expression = bytes([0x42, 0x4d, 15]) + constant(42) + bytes([0x4f, 15])
    vector = oracle.vector("left-to-right-assignment", expression, [0] * 16, 0)
    assert vector["finalVariables"][15] == 42
    vectors.append(vector)
    # Nested assignments and arithmetic; both assignment expressions return values.
    expression = bytes([0x41, 0x4d, 3, 0x43]) + constant(-12) + constant(7)
    expression += bytes([0x4d, 4, 0x46]) + constant(-5)
    vector = oracle.vector("nested-assignments", expression, [0] * 16, -79)
    assert vector["finalVariables"][3:5] == [-84, 5]
    vectors.append(vector)
    return vectors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("module", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.module.resolve() == args.output.resolve():
        parser.error("Output must differ from input module")
    module = args.module.read_bytes()
    oracle = Oracle(module)
    vectors = make_vectors(oracle)
    result = {
        "schemaVersion": 1,
        "description": "Synthetic expression inputs; expected values and final state from actual evaluator instructions in Unicorn",
        "moduleSha256": hashlib.sha256(module).hexdigest(),
        "unicornVersion": unicorn.__version__,
        "loadAddress": "0x800c0000", "evaluatorAddress": "0x800e4090",
        "verifiedRanges": [{"offsetStart": lo, "offsetEndExclusive": hi, "sha256": h}
                           for lo, hi, h in RANGES],
        "limitations": ["Offline routine oracle, not hardware or complete gameplay validation",
                        "Division by zero excluded; do not infer its behavior",
                        "Only ordinary variable IDs 0..15; game-state query opcodes excluded"],
        "vectors": vectors,
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(vectors)} verified vectors")


if __name__ == "__main__":
    main()
