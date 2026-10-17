"""English name entry (Disc 1): Latin letters on the first page, and names
stored as letter pairs.

The name-entry module (Disc 1, sector 2038, loaded at 0x800C0000; see
docs/game-internals.md section 14) keeps the surname and the given name in
two 7-byte fields (3 full-width characters + NUL) of its state at
0x800F97B0. One full-width character per cell would allow 3 letters per
name, drawn wide. This patch makes the input routine store letters two to a
cell, as the letter-pair codes of tools/font_en.py, so a name holds 6
letters and looks like the rest of the English text everywhere it is shown.

Changes inside the module (all checked against the original bytes first):

  * append (0x800C8804, fields 0 and 1): a Latin letter (Ａ-Ｚ, ａ-ｚ, or
    －ー．’　 as - . ' space) goes into the right half of the last cell if
    that cell is a pair with an empty right half, otherwise into a new cell
    "X "; anything else is stored as before.
  * backspace (0x800C8644): a full pair loses its right letter; anything
    else is deleted as before.
  * the routine lives in the tail of the symbol page's character list
    (0x800C0500), which is cut after ｚ (the page counts its characters
    with strlen, so it just gets shorter: kana, Greek and Cyrillic go).
  * the EVS nickname is copied in as romaji (tools/evsname.py; the kanji
    page loses its rows for ma-wa readings to make room).
  * the hiragana page shows A-Z, a-z and - . ' instead (rows are in place;
    the "ー～" row is shared with the katakana page, so the hiragana page's
    pointer to it is moved to a blank row). The katakana page is unchanged.
"""
import hashlib
import struct

MODULE_SECTOR = 2038          # Disc 1
BASE = 0x800C0000
SIZE = 0xE000                 # bytes checked and patched (code + tables)
ORIG_SHA1 = None              # filled in by check(); see _ORIG below

APPEND_AT, APPEND_EXIT = 0x800C8804, 0x800C896C
BS_AT, BS_EXIT = 0x800C8644, 0x800C86D8
SOUND = 0x8001FB70
SYMS = 0x800C0500             # symbol page character list
SYMS_CUT = 0x800C0654         # after ｚ
CODE_AT = 0x800C0658
CODE_END = 0x800C088A         # end of the old list (its NUL)
HIRA_PTRS = 0x800CD984        # 18 row pointers of the hiragana page

# expected original words at the hook sites
_ORIG = {
    APPEND_AT: 0x8603_01FC,   # lh v1, 0x1fc(s0)
    BS_AT: 0x84C3_01FC,       # lh v1, 0x1fc(a2)
}

ROWS = ["ＡＢＣＤＥ", "ＦＧＨＩＪ", "ＫＬＭＮＯ", "ＰＱＲＳＴ", "ＵＶＷＸＹ",
        "ａｂｃｄｅ", "ｆｇｈｉｊ", "ｋｌｍｎｏ", "ｐｑｒｓｔ", "ｕｖｗｘｙ",
        "Ｚｚ", "－．’", "　", "　", "　", "　", "　", None]   # None: point at row 16

# letter index in font_en.CHARSET for the full-width codes the hook accepts
SPECIAL = {0x8144: 63, 0x8166: 67, 0x817C: 69, 0x815B: 69, 0x8140: 0}


def source(sound=SOUND):
    sp = "\n".join("    ori   $v1, $zero, %#x\n    beq   $t5, $v1, letter\n    ori   $t6, $zero, %d"
                   % (code, idx) for code, idx in SPECIAL.items())
    return f"""
.set noreorder
hook_append:                      # s0 = state, a1 = name field, a2 = grid cell
    lh    $t0, 0x1fc($s0)         # pos: next cell (0..2; stays 2 when full)
    lw    $t1, 4($a2)             # row string
    lh    $t2, 0x10($a2)          # column
    nop
    sll   $t2, $t2, 1
    addu  $t1, $t1, $t2
    lbu   $t3, 0($t1)
    lbu   $t4, 1($t1)
    sll   $t5, $t3, 8
    or    $t5, $t5, $t4           # the character picked
    ori   $v1, $zero, 0x8260
    subu  $t6, $t5, $v1           # A-Z (full-width) -> 1..26
    sltiu $v1, $t6, 26
    bnez  $v1, letter
    addiu $t6, $t6, 1
    ori   $v1, $zero, 0x8281
    subu  $t6, $t5, $v1           # a-z (full-width) -> 27..52
    sltiu $v1, $t6, 26
    bnez  $v1, letter
    addiu $t6, $t6, 27
{sp}
    j     append                  # not a letter: store it as it is
    nop
letter:                           # t6 = letter index
    sll   $t7, $t0, 1
    addu  $t7, $t7, $a1           # &field[pos]
    lbu   $t8, 0($t7)
    nop
    bnez  $t8, havelast           # cell pos is filled (pos 2, full): last = pos
    nop
    beqz  $t0, newpair            # empty field
    nop
    addiu $t7, $t7, -2            # last = pos - 1
havelast:
    lbu   $t8, 0($t7)             # lead
    lbu   $t9, 1($t7)             # trail
    addiu $v1, $t8, -0xa0
    sltiu $v1, $v1, 0x40
    bnez  $v1, ispair
    addiu $v1, $t8, -0xeb
    sltiu $v1, $v1, 5
    beqz  $v1, newpair
    nop
ispair:
    ori   $v1, $zero, 0x40
    bne   $t9, $v1, newpair       # right half taken
    addiu $t9, $t6, 0x40
    j     {APPEND_EXIT:#x}
    sb    $t9, 1($t7)             # fill the right half; pos unchanged
newpair:
    sltiu $v1, $t6, 64
    bnez  $v1, lead_ok
    addiu $t3, $t6, 0xa0          # lead = LEAD[index]
    addiu $t3, $t6, 0xa8          # indexes 67..71 -> 0xEB..0xEF
lead_ok:
    ori   $t4, $zero, 0x40        # right half empty
append:                           # the original append, with t3/t4
    sll   $t7, $t0, 1
    addu  $t7, $t7, $a1
    sb    $t3, 0($t7)
    sb    $t4, 1($t7)
    sb    $zero, 2($t7)
    ori   $v1, $zero, 2
    bne   $t0, $v1, inc
    addiu $t0, $t0, 1
    jal   {sound:#x}
    ori   $a0, $zero, 5
    j     {APPEND_EXIT:#x}
    nop
inc:
    j     {APPEND_EXIT:#x}
    sh    $t0, 0x1fc($s0)

hook_bs:                          # a2 = state, a0 = name field
    lh    $t0, 0x1fc($a2)
    nop
    beqz  $t0, kset               # k = cell to delete from
    move  $t1, $zero
    ori   $v1, $zero, 2
    bne   $t0, $v1, km1
    nop
    lbu   $v1, 4($a0)
    nop
    bnez  $v1, kset
    ori   $t1, $zero, 2
km1:
    addiu $t1, $t0, -1
kset:
    sll   $t2, $t1, 1
    addu  $t2, $t2, $a0
    lbu   $t3, 0($t2)
    lbu   $t4, 1($t2)
    addiu $v1, $t3, -0xa0
    sltiu $v1, $v1, 0x40
    bnez  $v1, bs_pair
    addiu $v1, $t3, -0xeb
    sltiu $v1, $v1, 5
    beqz  $v1, bs_del
    nop
bs_pair:
    ori   $v1, $zero, 0x40
    beq   $t4, $v1, bs_del        # one letter: delete the cell
    nop
    j     {BS_EXIT:#x}
    sb    $v1, 1($t2)             # two letters: drop the right one
bs_del:
    sh    $t1, 0x1fc($a2)         # as the original: pos = k, cell k = NUL
    j     {BS_EXIT:#x}
    sb    $zero, 0($t2)
"""


def _count(src):
    return sum(1 for l in src.split("\n")
               if (l.split("#")[0].strip() and not l.split("#")[0].strip().endswith(":")
                   and not l.strip().startswith(".")))


def build(sound=SOUND):
    """(code bytes at CODE_AT, {label: address})."""
    from keystone import Ks, KS_ARCH_MIPS, KS_MODE_MIPS32, KS_MODE_LITTLE_ENDIAN
    ks = Ks(KS_ARCH_MIPS, KS_MODE_MIPS32 + KS_MODE_LITTLE_ENDIAN)
    src = source(sound)
    code = bytes(ks.asm(src, CODE_AT)[0])
    assert len(code) == 4 * _count(src), (len(code), 4 * _count(src))
    head = src.split("\nhook_bs:")[0]
    syms = {"hook_append": CODE_AT, "hook_bs": CODE_AT + len(bytes(ks.asm(head, CODE_AT)[0]))}
    assert CODE_AT + len(code) <= CODE_END, "routine too long"
    return code, syms


def _j(target):
    return struct.pack("<I", 0x08000000 | ((target & 0x0FFFFFFF) >> 2))


def patch_module(mod):
    """mod: the module's bytes from BASE (at least SIZE). Returns new bytes."""
    m = bytearray(mod)

    def put(addr, b):
        m[addr - BASE:addr - BASE + len(b)] = b

    def word(addr):
        return struct.unpack_from("<I", m, addr - BASE)[0]

    for a, w in _ORIG.items():
        if word(a) != w:
            raise ValueError("not the expected name-entry module (word at %#x)" % a)
    syms_text = bytes(m[SYMS - BASE:CODE_END - BASE])
    if not syms_text.startswith("　、。".encode("cp932")) or syms_text[SYMS_CUT - SYMS - 2:SYMS_CUT - SYMS] != "ｚ".encode("cp932"):
        raise ValueError("not the expected symbol list")
    sound_word = word(0x800C8870)
    sounds = [a for a in (SOUND, SOUND - 4)
              if sound_word == 0x0C000000 | ((a & 0x0FFFFFFF) >> 2)]
    if len(sounds) != 1:
        raise ValueError("unrecognized name-entry sound call")
    code, syms = build(sounds[0])
    put(SYMS_CUT, b"\0\0\0\0")
    put(CODE_AT, code + b"\0" * (CODE_END - CODE_AT - len(code)))
    put(APPEND_AT, _j(syms["hook_append"]) + b"\0\0\0\0")
    put(BS_AT, _j(syms["hook_bs"]) + b"\0\0\0\0")
    ptrs = list(struct.unpack_from("<18I", m, HIRA_PTRS - BASE))
    for i, row in enumerate(ROWS):
        p = ptrs[i]
        if row is None:
            ptrs[i] = ptrs[16]
            continue
        old = bytes(m[p - BASE:p - BASE + 12]).split(b"\0")[0]
        new = row.encode("cp932")
        assert len(new) <= len(old) or p == ptrs[16], (row, old)
        put(p, new + b"\0" * (len(old) + 1 - len(new)))
    struct.pack_into("<18I", m, HIRA_PTRS - BASE, *ptrs)
    import evsname
    evsname.apply(m, BASE)                 # the EVS nickname in romaji
    return bytes(m)


def patch_image(path):
    """Patch the name-entry module of a Disc 1 image in place. Returns the
    sectors written, or [] if the image has no such module."""
    import cdimage
    with open(path, "r+b") as f:
        n = -(-SIZE // 2048)
        old = cdimage.read_user_data(f, MODULE_SECTOR, n)
        try:
            new = patch_module(old)
        except (ValueError, struct.error):
            return []
        return cdimage.write_changed(f, MODULE_SECTOR, old, new)


if __name__ == "__main__":
    code, syms = build()
    print({k: hex(v) for k, v in syms.items()}, "code bytes:", len(code), "room:", CODE_END - CODE_AT)
