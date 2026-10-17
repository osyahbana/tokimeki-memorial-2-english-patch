"""Check the patched glyph block against the original, in a MIPS emulator.

    python tools/verify_glyphpatch.py <SLPM_863.5x>

Runs the original and the patched EXE code side by side (Unicorn; the BIOS
font call is replaced by a stub that returns either -1 or a pointer into
random data) and compares, for every one of the 65,536 two-byte codes:

  * the glyph lookup's return value (0x8001C5C0);
  * renderer A's (0x8001C874) return value and its output buffer, including
    a guard area after it; also with the input at an odd address;
  * renderer B's (0x8001CAE8, not patched, but it calls the lookup).

Everything must match, except letter-pair codes, whose results must equal
the reference model in tools/font_en.py. It also checks that callee-saved
registers survive, that the patched code writes nothing outside its output
buffer, the stack and its own glyph buffer, and that no instruction uses a
register loaded by the instruction just before it (the R3000 load delay
slot, which the emulator does not model).

Renderer B's scratch area (0x800A1FB0) is an allowed write target too: B
is the game's own code.

Needs: pip install unicorn capstone keystone-engine
"""
import random
import struct
import sys

import capstone
from unicorn import Uc, UC_ARCH_MIPS, UC_MODE_MIPS32, UC_MODE_LITTLE_ENDIAN, UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.mips_const import (UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2, UC_MIPS_REG_A3,
                                UC_MIPS_REG_V0, UC_MIPS_REG_SP, UC_MIPS_REG_RA, UC_MIPS_REG_GP,
                                UC_MIPS_REG_PC, UC_MIPS_REG_S0, UC_MIPS_REG_FP)

import font_en
import glyphpatch as gp

STOP = 0x80001000
FONT_BASE = 0x80400000        # stub "BIOS font": 32 bytes per code, random
IN, OUT, GUARD = 0x80300000, 0x80300100, 64
SREGS = [UC_MIPS_REG_S0 + i for i in range(8)] + [UC_MIPS_REG_FP, UC_MIPS_REG_GP]
LOOKUP, RENDER_A, RENDER_B = gp.BLOCK_LO, gp.RENDER_A, gp.BLOCK_HI


class Machine:
    def __init__(self, exe, revision="rev1"):
        mu = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 + UC_MODE_LITTLE_ENDIAN)
        mu.mem_map(0, 0x800000)
        size = struct.unpack_from("<I", exe, 0x1C)[0]        # t_size: what the BIOS loads
        mu.mem_write(gp.EXE_BASE & 0x1FFFFFFF, exe[0x800:0x800 + size])
        rnd = random.Random(1)
        mu.mem_write(FONT_BASE & 0x1FFFFFFF, rnd.randbytes(0x10000 * 32))
        self.krom = 0

        def stub(uc, addr, size, _):
            a0 = uc.reg_read(UC_MIPS_REG_A0)
            self.krom += 1
            v = 0xFFFFFFFF if (a0 * 7) % 13 == 0 else FONT_BASE + (a0 & 0xFFFF) * 32
            uc.reg_write(UC_MIPS_REG_V0, v)
            uc.reg_write(UC_MIPS_REG_PC, uc.reg_read(UC_MIPS_REG_RA))
        krom = gp.REVISIONS[revision]["krom2rawadd"]
        mu.hook_add(UC_HOOK_CODE, stub, begin=krom, end=krom)
        self.writes = []

        def on_write(uc, access, addr, size, value, _):
            self.writes.append((addr & 0xFFFFFFFF, size))
        mu.hook_add(UC_HOOK_MEM_WRITE, on_write)
        self.mu = mu

    def call(self, fn, a0=0, a1=0):
        mu = self.mu
        for i, r in enumerate(SREGS):
            mu.reg_write(r, 0x5A5A0000 + i)
        mu.reg_write(UC_MIPS_REG_A0, a0)
        mu.reg_write(UC_MIPS_REG_A1, a1)
        mu.reg_write(UC_MIPS_REG_A2, 0xDEAD0002)
        mu.reg_write(UC_MIPS_REG_A3, 0xDEAD0003)
        mu.reg_write(UC_MIPS_REG_SP, 0x801FFF00)
        mu.reg_write(UC_MIPS_REG_RA, STOP)
        self.writes = []
        mu.emu_start(fn, STOP, count=100000)
        assert mu.reg_read(UC_MIPS_REG_PC) == STOP, "did not return"
        assert mu.reg_read(UC_MIPS_REG_SP) == 0x801FFF00, "sp not restored"
        for i, r in enumerate(SREGS):
            assert mu.reg_read(r) == 0x5A5A0000 + i, "callee-saved register changed"
        return mu.reg_read(UC_MIPS_REG_V0)

    def read(self, addr, n):
        return bytes(self.mu.mem_read(addr & 0x1FFFFFFF, n))

    def write(self, addr, data):
        self.mu.mem_write(addr & 0x1FFFFFFF, data)


def expand(glyph30):
    """Python model of renderer A's output for a 30-byte 1-bit glyph."""
    out = bytearray()
    for r in range(15):
        h = glyph30[2 * r] | glyph30[2 * r + 1] << 8
        for lo in (0, 8):
            w = 0
            for px in range(8):
                if h >> (lo + 7 - px) & 1:
                    w |= 0xF << (4 * px)
            out += struct.pack("<I", w)
    return bytes(out) + bytes(8)


WRITES_FIRST = {"addu", "addiu", "subu", "and", "andi", "or", "ori", "xor", "xori", "nor",
                "slt", "slti", "sltu", "sltiu", "sll", "srl", "sra", "sllv", "srlv", "srav",
                "lui", "lb", "lbu", "lh", "lhu", "lw", "move", "mfhi", "mflo", "negu", "not"}
LOADS = {"lb", "lbu", "lh", "lhu", "lw"}


def _regs(text):
    import re
    return re.findall(r"\$\w+", text)


def check_load_delays(blk):
    """List every instruction that reads the register loaded by the
    instruction before it (on the R3000 it would still see the old value)."""
    md = capstone.Cs(capstone.CS_ARCH_MIPS, capstone.CS_MODE_MIPS32 + capstone.CS_MODE_LITTLE_ENDIAN)
    bad = []
    for start, end in ((gp.BLOCK_LO, gp.BLOCK_LO + 8), (gp.RENDER_A, gp.BLOCK_HI)):
        code = blk[start - gp.BLOCK_LO:end - gp.BLOCK_LO]
        ins = list(md.disasm(code, start))
        assert ins[-1].address + 4 >= end - 0x40, "disassembly stopped early"
        for a, b in zip(ins, ins[1:]):
            if (a.mnemonic.startswith("b") or a.mnemonic.startswith("j")) and b.mnemonic in LOADS:
                bad.append(f"{b.address:#x} load in a delay slot (not checked against the target)")
            if a.mnemonic not in LOADS:
                continue
            dst = _regs(a.op_str)[0]
            ops = b.op_str.split(", ", 1)
            reads = _regs(ops[1] if b.mnemonic in WRITES_FIRST and len(ops) > 1 else b.op_str)
            if dst in reads:
                bad.append(f"{a.address:#x} {a.mnemonic} {a.op_str} -> {b.mnemonic} {b.op_str}")
    return bad


def main(path):
    exe = open(path, "rb").read()
    revision = gp.detect_revision(exe)
    print("revision:", revision, flush=True)
    new_exe = gp.patch_exe(exe)
    blk, syms = gp.build(revision)
    bad = check_load_delays(blk)
    assert not bad, "load-delay hazards:\n" + "\n".join(bad)
    print("load delay slots: ok")
    old, new = Machine(exe, revision), Machine(new_exe, revision)
    buf = syms["buf"]
    scratch = gp.REVISIONS[revision]["renderer_b_scratch"]
    stack = (0x801FFF00 - 0x40, 0x801FFF00)

    def writes_ok(ranges):
        # the write hook reports physical addresses
        ph = [(s & 0x1FFFFFFF, e & 0x1FFFFFFF) for s, e in ranges]
        return all(any(s <= a & 0x1FFFFFFF and (a & 0x1FFFFFFF) + n <= e for s, e in ph)
                   for a, n in new.writes)
    pairs = {c: font_en.compose(c) for c in range(0x10000) if font_en.decode_pair(c)}
    print("pair codes:", len(pairs))

    # 1. lookup
    rnd = random.Random(2)
    n_custom = 0
    for c in range(0x10000):
        for a0 in (c, c | rnd.getrandbits(16) << 16):
            vo, vn = old.call(LOOKUP, a0), new.call(LOOKUP, a0)
            assert writes_ok([stack, (buf, buf + 30)] if c in pairs else []), hex(a0)
            if c in pairs:
                assert vo == 0 and vn == buf, hex(c)
                assert new.read(buf, 30) == pairs[c], hex(c)
            else:
                assert vo == vn, (hex(a0), hex(vo), hex(vn))
                n_custom += vo != 0
    print("lookup: all 65,536 codes match (%d with a game glyph)" % (n_custom // 2))

    # 2. renderer A and B
    guard = b"\xA5" * (128 + GUARD)
    for fn, name in ((RENDER_A, "renderer A"), (RENDER_B, "renderer B")):
        for c in range(0x10000):
            src = IN + (c & 1)                       # odd and even input addresses
            for m in (old, new):
                m.write(src, bytes((c >> 8, c & 0xFF)))
                m.write(OUT, guard)
            ko, kn = old.krom, new.krom
            vo, vn = old.call(fn, src, OUT), new.call(fn, src, OUT)
            assert writes_ok([stack, (OUT, OUT + 128), (buf, buf + 30), (scratch, scratch + 64)]), (name, hex(c))
            oo, on = old.read(OUT, 128 + GUARD), new.read(OUT, 128 + GUARD)
            assert vo == vn == 1, (name, hex(c))
            if c in pairs:
                assert new.krom == kn, "pair code reached the BIOS font"
                if fn == RENDER_A:
                    assert on == expand(pairs[c]) + guard[128:], (name, hex(c))
                else:
                    assert on[128:] == oo[128:], (name, hex(c))
            else:
                assert oo == on, (name, hex(c))
                assert old.krom - ko == new.krom - kn, (name, hex(c))
        print(f"{name}: all 65,536 codes match")
    print("writes: only the stack, the output buffer and the pair buffer (lookup: none")
    print("        except the pair buffer for pair codes)")

    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main(sys.argv[1])
