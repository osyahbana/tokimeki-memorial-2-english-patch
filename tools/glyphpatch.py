"""Replacement glyph block for the TM2 executable (letter-pair support).

The EXE's glyph code at 0x8001C5C0-0x8001CAE8 is rewritten compactly:

  0x8001C5C0  glyph lookup     code -> 30-byte 1-bit glyph, or 0
  0x8001C874  renderer A       2-byte char -> 16 x 16 4-bit cell
  0x8001CAE8  renderer B       (not touched)

Both entry points keep their address and their exact behaviour for every
code the original handles (checked in an emulator over all 65,536 codes,
see tools/verify_glyphpatch.py). One thing is new: the lookup recognises
letter-pair codes (tools/font_en.py) and builds their cell bitmap from the
English font into a 32-byte buffer inside the block.

The block was found and measured in docs/game-internals.md section 9. The
five discs' EXEs are identical here within each supported revision. Exact
block hashes select Japan original or Rev 1 font and BIOS addresses.

Assembling needs keystone (pip install keystone-engine).
"""
import hashlib
import struct
import font_en

EXE_BASE = 0x80015800          # RAM address of EXE file offset 0x800
BLOCK_LO, BLOCK_HI = 0x8001C5C0, 0x8001CAE8
RENDER_A = 0x8001C874          # must stay here (called from the EXE and modules)
KROM2RAWADD = 0x8005A504       # BIOS B(51h) stub: Shift-JIS code -> BIOS font glyph
CUSTOM_BASE = 0x80061874       # the game's own glyphs, 30 bytes each
# Codes with a game-supplied glyph, in slot order (slot k at CUSTOM_BASE + 30k).
# Codes 0xF000-0xFFFF use slot 30 + (code & 0xF). Read from the original
# lookup by running it on every code (see verify_glyphpatch.py).
CUSTOM_CODES = [
    0xE36B, 0x9C9B, 0x9952, 0xE6D2, 0xE6CE, 0xE0F8, 0x98A5, 0xE34F, 0x9F7E, 0x9B8C,
    0x9E42, 0xE359, 0x9A6B, 0xE569, 0xE587, 0xE8C6, 0xE8CC, 0x9BDE, 0xE5B6, 0x9AF8,
    0x997A, 0xE785, 0x9DF3, 0xE056, 0x9EBC, 0xE05F, 0x99E7, 0xE0D1, 0xE97D, 0xE1BF,
]
ORIGINAL_SHA1 = "1681a326cf5ac85792b9404a03dbf45b4b683796"   # of the original block

# Exact measured block identities. Japan v1.0 has the same entry points,
# instructions and custom-code ordering; only the font/BIOS addresses differ.
# Relocating its 31 font immediates and single BIOS jal by +0x6C reproduces
# the Rev 1 block's exact SHA1, independently confirming that equivalence.
# Keeping revision data explicit prevents applying Rev 1 pointers to v1.0.
REVISIONS = {
    "rev1": dict(block_sha1=ORIGINAL_SHA1, custom_base=CUSTOM_BASE,
                 krom2rawadd=KROM2RAWADD, renderer_b_scratch=0x800A1FB0),
    "original": dict(block_sha1="af30bdcb864accac4d75cfb2e0d759f8494193cf",
                     custom_base=0x80061808, krom2rawadd=0x8005A498,
                     renderer_b_scratch=0x800A1F48),
}


def detect_revision(exe):
    """Identify a supported, unpatched glyph block; reject every other block."""
    if exe[:8] != b"PS-X EXE" or struct.unpack_from("<I", exe, 0x18)[0] != EXE_BASE:
        raise ValueError("unexpected PS-X executable header or load address")
    o = 0x800 + BLOCK_LO - EXE_BASE
    digest = hashlib.sha1(exe[o:o + BLOCK_HI - BLOCK_LO]).hexdigest()
    for name, revision in REVISIONS.items():
        if digest == revision["block_sha1"]:
            return name
    raise ValueError("glyph block differs from supported originals (already patched?)")


def _hilo(addr):
    lo = addr & 0xFFFF
    return (addr + 0x8000) >> 16 & 0xFFFF, lo - 0x10000 if lo & 0x8000 else lo


def _la(reg, addr):
    hi, lo = _hilo(addr)
    return f"lui {reg}, {hi:#x}\naddiu {reg}, {reg}, {lo}\n"


def _mul(rd, rs, k, tmp, tmp2):
    """rd = rs * k (constant k > 1) with shifts and adds/subtracts
    (canonical signed digits). Clobbers tmp and tmp2; rd may equal rs."""
    digits, i = [], 0
    while k:
        if k & 1:
            d = 2 - (k & 3)          # +1 or -1
            digits.append((i, d))
            k -= d
        k >>= 1
        i += 1
    (i0, d0), rest = digits[-1], digits[:-1]
    assert d0 == 1
    if not rest:
        return [f"sll {rd}, {rs}, {i0}"]
    out = [f"sll {tmp}, {rs}, {i0}"]
    for n, (i, d) in enumerate(rest):
        dst = rd if n == len(rest) - 1 else tmp
        src = rs
        if i:
            out.append(f"sll {tmp2}, {rs}, {i}")
            src = tmp2
        out.append(f"{'addu' if d > 0 else 'subu'} {dst}, {tmp}, {src}")
    return out


def _field(rd, rs, shift_to):
    """rd = W-bit field at the top of the 16-bit value (rs << s) - already
    shifted - moved to bit position shift_to of a u16 glyph row."""
    w = font_en.W
    d = 16 - w - shift_to
    op = f"srl {rd}, {rs}, {d}" if d >= 0 else f"sll {rd}, {rs}, {-d}"
    return f"{op}\nandi {rd}, {rd}, {((1 << w) - 1) << shift_to:#x}\n"


def layout():
    """Addresses of the data tables (region before RENDER_A)."""
    a = BLOCK_LO + 8                       # after the entry jump
    codes = a; a += 2 * len(CUSTOM_CODES)
    nib = a; a += 32
    a = (a + 3) & ~3
    buf = a; a += 32
    font = a; a += len(font_en.font_blob())
    assert a <= RENDER_A, "data does not fit before renderer A (%#x)" % a
    return dict(codes=codes, nib=nib, buf=buf, font=font, data_end=a)


def source(L, lk_body=RENDER_A, revision="rev1"):
    """Assembly for the code at RENDER_A (renderer A, then the lookup)."""
    W, H, top = font_en.W, font_en.H, font_en.CELL_TOP
    assert font_en.LEFT_X + W <= 8 and font_en.RIGHT_X >= 8 and font_en.RIGHT_X + W <= 16
    assert W + 7 <= 16 and top + H <= 15
    assert font_en.LEAD == [0xA0 + i for i in range(64)] + [0x85, 0x86, 0x87] + [0xEB + i for i in range(5)]
    sl = 8 - W - font_en.LEFT_X            # left letter: byte 0 of the row
    sr = 24 - W - font_en.RIGHT_X          # right letter: byte 1 of the row
    zero_rows = "".join(f"    sh    $zero, {2 * r}($a1)\n" for r in range(15) if not top <= r < top + H)
    bpg = W * H                            # bits per glyph
    mul_l = _mul("$a3", "$a3", bpg, "$v0", "$t0")
    mul_r = _mul("$t1", "$t1", bpg, "$v0", "$t0")
    ind = lambda lines: "".join("    " + l + "\n" for l in lines)
    hi_b, lo_b = _hilo(L["buf"])
    hi_c, lo_c = _hilo(L["codes"])
    rev = REVISIONS[revision]
    hi_g, lo_g = _hilo(rev["custom_base"])
    hi_f, lo_f = _hilo(rev["custom_base"] + 30 * 30)
    return f"""
.set noreorder
# ---------------- renderer A (0x8001C874): a0 = 2-byte char, a1 = out (128 B)
render_a:
    addiu $sp, $sp, -0x20
    sw    $ra, 0x18($sp)
    sw    $s1, 0x14($sp)
    sw    $s0, 0x10($sp)
    lbu   $v0, 0($a0)
    lbu   $v1, 1($a0)
    move  $s1, $a1
    sll   $t0, $v0, 24
    bgez  $t0, ra_done           # first byte < 0x80: draw nothing
    sll   $v0, $v0, 8
    or    $v1, $v1, $v0          # v1 = code
    jal   {lk_body:#x}            # lk_body: glyph lookup past its entry jump
    move  $s0, $v1
    bnez  $v0, ra_have
    move  $a2, $v0
    jal   {rev["krom2rawadd"]:#x}        # BIOS font
    move  $a0, $s0
    move  $a2, $v0
ra_have:
    addiu $v0, $zero, -1
    beq   $a2, $v0, ra_blank
    move  $a1, $s1
{_la("$t2", L["nib"])}    addiu $a0, $zero, 15
ra_row:                          # 15 rows: u16 -> two words of 4-bit pixels
    lhu   $v1, 0($a2)
    addiu $a2, $a2, 2
    srl   $v0, $v1, 3            # bits 7-4 -> pixels 0-3
    andi  $v0, $v0, 0x1e
    addu  $v0, $v0, $t2
    lhu   $t0, 0($v0)
    sll   $v0, $v1, 1            # bits 3-0 -> pixels 4-7
    andi  $v0, $v0, 0x1e
    addu  $v0, $v0, $t2
    lhu   $t1, 0($v0)
    srl   $v0, $v1, 11           # bits 15-12 -> pixels 8-11
    sll   $t1, $t1, 16
    or    $t0, $t0, $t1
    sw    $t0, 0($a1)
    andi  $v0, $v0, 0x1e
    addu  $v0, $v0, $t2
    lhu   $t0, 0($v0)
    srl   $v0, $v1, 7            # bits 11-8 -> pixels 12-15
    andi  $v0, $v0, 0x1e
    addu  $v0, $v0, $t2
    lhu   $t1, 0($v0)
    addiu $a0, $a0, -1
    sll   $t1, $t1, 16
    or    $t0, $t0, $t1
    sw    $t0, 4($a1)
    bgtz  $a0, ra_row
    addiu $a1, $a1, 8
    sw    $zero, 0($a1)          # row 16 is empty
    b     ra_done
    sw    $zero, 4($a1)
ra_blank:                        # no glyph: 32 empty words
    addiu $a0, $zero, 32
ra_clear:
    sw    $zero, 0($a1)
    addiu $a0, $a0, -1
    bgtz  $a0, ra_clear
    addiu $a1, $a1, 4
ra_done:
    addiu $v0, $zero, 1
    lw    $ra, 0x18($sp)
    lw    $s1, 0x14($sp)
    lw    $s0, 0x10($sp)
    jr    $ra
    addiu $sp, $sp, 0x20

# ---------------- glyph lookup, continued from 0x8001C5C0 (v1 = code & 0xFFFF)
lk_body:
    srl   $v0, $v1, 12
    xori  $v0, $v0, 0xf
    bnez  $v0, lk_table
    andi  $a3, $v1, 0xf
    sll   $v0, $a3, 5            # 0xFxxx: slot 30 + low nibble
    sll   $a3, $a3, 1
    subu  $v0, $v0, $a3          # 30 * nibble
    lui   $a3, {hi_f:#x}
    addiu $a3, $a3, {lo_f}
    jr    $ra
    addu  $v0, $v0, $a3
lk_table:                        # codes with a glyph of the game's own
    lui   $a1, {hi_c:#x}
    addiu $a1, $a1, {lo_c}
    lui   $a0, {hi_g:#x}
    addiu $a0, $a0, {lo_g}
    addiu $a2, $a1, {2 * len(CUSTOM_CODES)}
lk_next:
    lhu   $v0, 0($a1)
    addiu $a1, $a1, 2
    beq   $v0, $v1, lk_ret
    sltu  $a3, $a1, $a2
    bnez  $a3, lk_next
    addiu $a0, $a0, 30
    srl   $t0, $v1, 8            # letter pair? t0 = lead byte
    andi  $t1, $v1, 0xff
    addiu $t1, $t1, -{font_en.TRAIL0:#x}   # t1 = right letter
    addiu $a3, $t0, -0xa0        # a3 = left letter
    sltiu $v0, $a3, 64
    bnez  $v0, lk_pair
    addiu $a2, $t0, -0x85
    sltiu $v0, $a2, 3
    bnez  $v0, lk_pair
    addiu $a3, $a2, 64
    addiu $a2, $t0, -0xeb
    sltiu $v0, $a2, 5
    beqz  $v0, lk_none
    addiu $a3, $a2, 67
lk_pair:
    sltiu $v0, $t1, {len(font_en.CHARSET)}
    beqz  $v0, lk_none
    {mul_l[0]}
{ind(mul_l[1:])}{ind(mul_r)}    lui   $a1, {hi_b:#x}
    addiu $a1, $a1, {lo_b}
{zero_rows}    addiu $t2, $a1, {L["font"] - L["buf"]}
    addiu $a2, $a1, {2 * (top + H)}
    addiu $a1, $a1, {2 * top}
lk_row:                          # one glyph row of each letter per pass
    srl   $v0, $a3, 3
    addu  $v0, $v0, $t2
    lbu   $t0, 0($v0)
    lbu   $v0, 1($v0)
    andi  $v1, $a3, 7
    sll   $t0, $t0, 8
    or    $t0, $t0, $v0
    sllv  $t0, $t0, $v1
{_field("$t0", "$t0", sl)}    srl   $v0, $t1, 3
    addu  $v0, $v0, $t2
    lbu   $v1, 0($v0)
    lbu   $v0, 1($v0)
    sll   $v1, $v1, 8
    or    $v1, $v1, $v0
    andi  $v0, $t1, 7
    sllv  $v1, $v1, $v0
{_field("$v1", "$v1", sr)}    or    $v1, $v1, $t0
    sh    $v1, 0($a1)
    addiu $a1, $a1, 2
    addiu $a3, $a3, {W}
    bne   $a1, $a2, lk_row
    addiu $t1, $t1, {W}
    jr    $ra
    addiu $v0, $a1, -{2 * (top + H)}
lk_none:
    addiu $a0, $zero, 0
lk_ret:
    jr    $ra
    move  $v0, $a0
"""


def _asm(src, addr):
    from keystone import Ks, KS_ARCH_MIPS, KS_MODE_MIPS32, KS_MODE_LITTLE_ENDIAN
    ks = Ks(KS_ARCH_MIPS, KS_MODE_MIPS32 + KS_MODE_LITTLE_ENDIAN)
    enc, _ = ks.asm(src, addr)
    return bytes(enc)


def _count_instructions(src):
    n = 0
    for line in src.split("\n"):
        line = line.split("#")[0].strip()
        if not line or line.endswith(":") or line.startswith("."):
            continue
        n += 1
    return n


def build(revision="rev1"):
    """Return (block bytes for BLOCK_LO..BLOCK_HI, symbol dict)."""
    L = layout()
    # pass 1 finds lk_body (keystone turns "jal label" into a PIC call, so
    # jal targets are given as numbers)
    head = source(L, revision=revision).split("\nlk_body:")[0]
    lk_body = RENDER_A + len(_asm(head, RENDER_A))
    src = source(L, lk_body, revision=revision)
    code = _asm(src, RENDER_A)
    # keystone must not have added or dropped instructions (delay slots)
    assert len(code) == 4 * _count_instructions(src), (len(code), _count_instructions(src))
    syms = dict(L, lk_body=lk_body)
    syms["code_end"] = RENDER_A + len(code)
    assert syms["code_end"] <= BLOCK_HI, "code too long: ends at %#x" % syms["code_end"]
    entry = _asm(f".set noreorder\nj {syms['lk_body']:#x}\nandi $v1, $a0, 0xffff\n", BLOCK_LO)
    assert syms["font"] - syms["buf"] < 0x8000
    assert len(entry) == 8
    nib = b"".join(struct.pack("<H", sum(0xF << 4 * (3 - k) for k in range(4) if n >> k & 1))
                   for n in range(16))
    blk = bytearray(BLOCK_HI - BLOCK_LO)
    def put(addr, data):
        blk[addr - BLOCK_LO:addr - BLOCK_LO + len(data)] = data
    put(BLOCK_LO, entry)
    put(L["codes"], b"".join(struct.pack("<H", c) for c in CUSTOM_CODES))
    put(L["nib"], nib)
    put(L["font"], font_en.font_blob())
    put(RENDER_A, code)
    return bytes(blk), syms


def patch_exe(exe):
    """exe: bytes of SLPM_863.5x (any disc). Returns the patched EXE."""
    o = 0x800 + BLOCK_LO - EXE_BASE
    revision = detect_revision(exe)
    blk, _ = build(revision)
    return exe[:o] + blk + exe[o + len(blk):]


def find_exe(f):
    """(name, lba, size) of the game's executable in a disc image."""
    import cdimage
    exes = [(n, l, s) for n, (l, s) in cdimage.root_files(f).items() if n.startswith("SLPM_863")]
    assert len(exes) == 1, exes
    return exes[0]


def patch_image(path):
    """Patch the EXE inside a BIN (MODE2/2352) disc image in place."""
    import cdimage
    with open(path, "r+b") as f:
        name, lba, size = find_exe(f)
        n = (size + 2047) // 2048
        old = cdimage.read_user_data(f, lba, n)
        new = patch_exe(old)
        return name, cdimage.write_changed(f, lba, old, new)


if __name__ == "__main__":
    blk, syms = build()
    for k, v in syms.items():
        print(f"{k:10s} {v:#x}")
    print("free bytes:", (RENDER_A - syms["data_end"]) + (BLOCK_HI - syms["code_end"]))
