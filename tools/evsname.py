"""The EVS nickname in romaji (Disc 1 name-entry module, with namepatch.py).

The nickname the girls call you ("ふぃあくん") is the text part of the EVS
file on the memory card (docs/game-internals.md section 14). At the start
of a new game the name-entry module copies it into the game state with
strcpy (0x8005A074) at 0x800CA678 and 0x800CA694. This patch sends both
copies through a converter that writes it as romaji letter pairs instead
("Fia-kun"); the voice data is untouched. Anything that isn't kana is
copied as before.

Romaji (Hepburn, simplified): table below; きゃ -> kya, しゃ -> sha,
ちゃ -> cha, じゃ -> ja; ふぃ -> fi, てぃ -> ti, ウィ (at the start) -> wi;
っ doubles the next consonant (っち -> tchi); ー repeats the vowel; 　 is a
space. The first letter is capitalised, and a final くん / ちゃん / さん
gets a hyphen ("Fia-kun"). At most 14 letters (7 cells) are kept: the
state's nickname fields are 15 bytes.

The converter (and its table and buffer) live where the kanji page's rows
for ま...わ readings were (0x800C088C-0x800C0F04); those rows are emptied.
"""
import struct

HOOKS = (0x800CA678, 0x800CA694)          # jal strcpy -> jal k2r
STRCPY = 0x8005A074
KANJI_PTRS, KANJI_N = 0x800CDA18, 46
REGION, REGION_END = 0x800C088C, 0x800C0F04
EMPTY = REGION                            # an empty string for the emptied rows
TABLE = REGION + 4
BUF = TABLE + 86 * 4                      # 32-byte letter buffer
CODE = BUF + 32
MAX_LETTERS = 14

HIRA = ("ぁあぃいぅうぇえぉおかがきぎくぐけげこごさざしじすずせぜそぞただちぢっつづてでとどなにぬねの"
        "はばぱひびぴふぶぷへべぺほぼぽまみむめもゃやゅゆょよらりるれろゎわゐゑをん")
ROMA = ("~a a ~i i ~u u ~e e ~o o ka ga ki gi ku gu ke ge ko go sa za shi ji su zu se ze so zo "
        "ta da chi ji ! tsu zu te de to do na ni nu ne no ha ba pa hi bi pi fu bu pu he be pe ho bo po "
        "ma mi mu me mo ^a ya ^u yu ^o yo ra ri ru re ro wa wa i e o n vu ka ke").split()
assert len(HIRA) == 83 and len(ROMA) == 86


def table():
    """86 entries of 4 bytes: letters (NUL-padded), or a marker: 1 = small
    ya/yu/yo (byte 1 = vowel), 2 = small vowel, 3 = small tsu."""
    out = bytearray()
    for r in ROMA:
        if r[0] == "^":
            e = bytes((1, ord(r[1])))
        elif r[0] == "~":
            e = bytes((2, ord(r[1])))
        elif r == "!":
            e = bytes((3,))
        else:
            e = r.encode()
        out += e.ljust(4, b"\0")
    return bytes(out)


def kana_index(code):
    """Index into the table for a 2-byte code, or None."""
    if 0x829F <= code < 0x829F + 83:
        return code - 0x829F
    if 0x8340 <= code < 0x8340 + 63:
        return code - 0x8340
    if 0x8341 + 63 <= code < 0x8341 + 86:       # 0x8380.. (0x837F is not a character)
        return code - 0x8341
    if code == 0x837F:
        return 62                               # what the routine does with it
    return None


VOWELS = "aeiou"


def model(src):
    """Python reference: kana bytes -> the bytes the routine writes (or None
    when it falls back to strcpy)."""
    if not src or not 0x81 <= src[0] <= 0x83:
        return None
    out, sok, i = [], False, 0
    while src[i] and len(out) < 24:
        code = src[i] << 8 | src[i + 1]
        i += 2
        if code == 0x8140:
            out.append(" ")
            continue
        if code == 0x815B:
            if out and out[-1] in VOWELS:
                out.append(out[-1])
            continue
        k = kana_index(code)
        if k is None:
            continue
        r = ROMA[k]
        if r == "!":
            sok = True
            continue
        if r[0] == "^":
            v = r[1]
            if out and out[-1] == "i":
                out.pop()
                if out and (out[-1] == "j" or (out[-1] == "h" and len(out) >= 2 and out[-2] in "sc")):
                    out.append(v)
                    continue
            out += ["y", v]
            continue
        if r[0] == "~":
            v = r[1]
            if out and out[-1] in VOWELS:
                last = out.pop()
                if not out and last == "u":
                    out.append("w")
            out.append(v)
            continue
        if sok:
            out.append("t" if r[0] == "c" else r[0])
            sok = False
        out += list(r)
    s = "".join(out)
    if s and "a" <= s[0] <= "z":
        s = s[0].upper() + s[1:]
    n = len(s)
    if n >= 5 and s.endswith("chan"):
        s = s[:-4] + "-chan"
    elif n >= 4 and (s.endswith("kun") or s.endswith("san")):
        s = s[:-3] + "-" + s[-3:]
    import font_en
    s = s[:MAX_LETTERS]
    b = b"".join(font_en.pair_code(s[j], s[j + 1] if j + 1 < len(s) else " ")
                 for j in range(0, len(s), 2))
    return b + b"\0"


def _idx(ch, out, lab):
    """asm: font_en index of ASCII letter in register ch -> out (other -> 0)."""
    return f"""
    addiu $v0, {ch}, -0x41
    sltiu {out}, $v0, 26
    beqz  {out}, {lab}_lc
    nop
    j     {lab}_e
    addiu {out}, $v0, 1
{lab}_lc:
    addiu $v0, {ch}, -0x61
    sltiu {out}, $v0, 26
    beqz  {out}, {lab}_p
    nop
    j     {lab}_e
    addiu {out}, $v0, 27
{lab}_p:
    ori   $v0, $zero, 0x2d
    bne   {ch}, $v0, {lab}_q
    ori   {out}, $zero, 69
    j     {lab}_e
    nop
{lab}_q:
    ori   $v0, $zero, 0x27
    bne   {ch}, $v0, {lab}_s
    ori   {out}, $zero, 67
    j     {lab}_e
    nop
{lab}_s:
    ori   {out}, $zero, 0
{lab}_e:"""


def _isvowel(reg, no, tmp="$a2"):
    """asm: branch to `no` unless reg holds a, e, i, o or u (clobbers v0, tmp)."""
    return f"""
    addiu {tmp}, {reg}, -0x61
    sltiu $v0, {tmp}, 21
    beqz  $v0, {no}
    lui   $v0, 0x10
    ori   $v0, $v0, 0x4111
    srlv  $v0, $v0, {tmp}
    andi  $v0, $v0, 1
    beqz  $v0, {no}
    nop"""


def source(strcpy=STRCPY):
    hi = lambda a: (a + 0x8000) >> 16 & 0xFFFF
    lo = lambda a: a & 0xFFFF
    return f"""
.set noreorder
k2r:                              # a0 = destination, a1 = source
    lbu   $t0, 0($a1)
    nop
    addiu $v0, $t0, -0x81
    sltiu $v0, $v0, 3
    bnez  $v0, k_go
    nop
    j     {strcpy:#x}             # not kana: plain strcpy
    nop
k_go:
    lui   $t8, {hi(BUF):#x}
    addiu $t8, $t8, {lo(BUF) - (0x10000 if lo(BUF) & 0x8000 else 0)}
    lui   $t5, {hi(TABLE):#x}
    addiu $t5, $t5, {lo(TABLE) - (0x10000 if lo(TABLE) & 0x8000 else 0)}
    move  $t7, $t8                # out
    move  $t6, $zero              # small tsu pending
    move  $t9, $a1
k_loop:
    lbu   $t0, 0($t9)
    lbu   $t1, 1($t9)
    beqz  $t0, k_done
    addiu $t9, $t9, 2
    sll   $t2, $t0, 8
    or    $t2, $t2, $t1
    subu  $v0, $t7, $t8
    sltiu $v0, $v0, 24            # buffer guard
    beqz  $v0, k_done
    ori   $v1, $zero, 0x8140
    bne   $t2, $v1, k_notsp
    ori   $v1, $zero, 0x20
    sb    $v1, 0($t7)
    j     k_loop
    addiu $t7, $t7, 1
k_notsp:
    ori   $v1, $zero, 0x815b
    bne   $t2, $v1, k_notlong
    nop
    beq   $t7, $t8, k_loop
    nop
    lbu   $v1, -1($t7)
    nop
{_isvowel("$v1", "k_loop")}
    sb    $v1, 0($t7)
    j     k_loop
    addiu $t7, $t7, 1
k_notlong:
    ori   $v1, $zero, 0x829f
    subu  $t3, $t2, $v1
    sltiu $v0, $t3, 83
    bnez  $v0, k_idx
    ori   $v1, $zero, 0x8340
    subu  $t3, $t2, $v1
    sltiu $v0, $t3, 63
    bnez  $v0, k_idx
    nop
    addiu $t3, $t3, -1            # 0x8380.. -> code - 0x8341
    sltiu $v0, $t3, 86
    beqz  $v0, k_loop             # not kana: skip it
    nop
k_idx:
    sll   $v0, $t3, 2
    addu  $v0, $v0, $t5
    lbu   $a2, 0($v0)
    lbu   $a3, 1($v0)
    ori   $v1, $zero, 3
    bne   $a2, $v1, k_nsok
    nop
    j     k_loop
    ori   $t6, $zero, 1
k_nsok:
    ori   $v1, $zero, 1
    beq   $a2, $v1, k_yoon
    ori   $v1, $zero, 2
    beq   $a2, $v1, k_small
    nop
    beqz  $t6, k_copy
    move  $t4, $a2
    ori   $v1, $zero, 0x63
    bne   $a2, $v1, k_dbl
    nop
    ori   $t4, $zero, 0x74
k_dbl:
    sb    $t4, 0($t7)
    addiu $t7, $t7, 1
    move  $t6, $zero
k_copy:
    lbu   $a2, 0($v0)
    nop
    beqz  $a2, k_loop
    addiu $v0, $v0, 1
    sb    $a2, 0($t7)
    j     k_copy
    addiu $t7, $t7, 1
k_yoon:                           # a3 = vowel of small ya/yu/yo
    beq   $t7, $t8, k_ya
    nop
    lbu   $v1, -1($t7)
    ori   $a2, $zero, 0x69
    bne   $v1, $a2, k_ya
    nop
    addiu $t7, $t7, -1            # drop the i
    beq   $t7, $t8, k_ya
    nop
    lbu   $v1, -1($t7)
    ori   $a2, $zero, 0x6a
    beq   $v1, $a2, k_vowel       # j + vowel
    ori   $a2, $zero, 0x68
    bne   $v1, $a2, k_ya
    addiu $a2, $t7, -2
    sltu  $a2, $a2, $t8
    bnez  $a2, k_ya               # h at the start: hya
    nop
    lbu   $v1, -2($t7)
    ori   $a2, $zero, 0x73
    beq   $v1, $a2, k_vowel       # sh + vowel
    ori   $a2, $zero, 0x63
    beq   $v1, $a2, k_vowel       # ch + vowel
    nop
k_ya:
    ori   $v1, $zero, 0x79
    sb    $v1, 0($t7)
    addiu $t7, $t7, 1
k_vowel:
    sb    $a3, 0($t7)
    j     k_loop
    addiu $t7, $t7, 1
k_small:                          # a3 = small vowel
    beq   $t7, $t8, k_vowel
    nop
    lbu   $v1, -1($t7)
    nop
{_isvowel("$v1", "k_vowel")}
    addiu $t7, $t7, -1            # drop the vowel
    bne   $t7, $t8, k_vowel
    ori   $a2, $zero, 0x75
    bne   $v1, $a2, k_vowel
    ori   $a2, $zero, 0x77        # u at the start -> w
    sb    $a2, 0($t7)
    j     k_vowel
    addiu $t7, $t7, 1
k_done:
    beq   $t7, $t8, pack
    nop
    lbu   $v1, 0($t8)             # capitalise
    nop
    addiu $a2, $v1, -0x61
    sltiu $a2, $a2, 26
    beqz  $a2, k_hon
    addiu $v1, $v1, -0x20
    sb    $v1, 0($t8)
k_hon:
    subu  $t0, $t7, $t8
    slti  $v0, $t0, 4
    bnez  $v0, pack
    nop
    lwl   $v1, -1($t7)            # the last 4 letters, little-endian
    lwr   $v1, -4($t7)
    slti  $v0, $t0, 5
    bnez  $v0, k_three
    lui   $a2, 0x6e61
    ori   $a2, $a2, 0x6863        # "chan"
    bne   $v1, $a2, k_three
    nop
    j     k_ins
    addiu $a3, $t7, -4
k_three:
    srl   $v1, $v1, 8
    addiu $a3, $t7, -3
    lui   $a2, 0x6e
    ori   $a2, $a2, 0x756b        # "kun"
    beq   $v1, $a2, k_ins
    lui   $a2, 0x6e
    ori   $a2, $a2, 0x6173        # "san"
    bne   $v1, $a2, pack
    nop
k_ins:                            # insert '-' at a3
    move  $v1, $t7
k_shift:
    lbu   $v0, -1($v1)
    nop
    sb    $v0, 0($v1)
    addiu $v1, $v1, -1
    bne   $v1, $a3, k_shift
    nop
    ori   $v0, $zero, 0x2d
    sb    $v0, 0($a3)
    addiu $t7, $t7, 1
pack:                             # letters t8..t7 -> pairs at a0, at most 7 cells
    move  $t0, $t8
    move  $t1, $a0
    addiu $t2, $a0, {2 * (MAX_LETTERS // 2)}
p_loop:
    sltu  $v0, $t0, $t7
    beqz  $v0, p_end
    sltu  $v0, $t1, $t2
    beqz  $v0, p_end
    nop
    lbu   $v1, 0($t0)
    addiu $t0, $t0, 1
    sltu  $v0, $t0, $t7
    beqz  $v0, p_r
    ori   $a3, $zero, 0x20
    lbu   $a3, 0($t0)
    addiu $t0, $t0, 1
p_r:
    nop
{_idx("$v1", "$a2", "il")}
    sltiu $v0, $a2, 64
    bnez  $v0, p_lead
    addiu $v1, $a2, 0xa0
    addiu $v1, $a2, 0xa8
p_lead:
    sb    $v1, 0($t1)
{_idx("$a3", "$a2", "ir")}
    addiu $a2, $a2, 0x40
    sb    $a2, 1($t1)
    j     p_loop
    addiu $t1, $t1, 2
p_end:
    jr    $ra
    sb    $zero, 0($t1)
"""


def _count(src):
    return sum(1 for l in src.split("\n")
               if l.split("#")[0].strip() and not l.split("#")[0].strip().endswith(":")
               and not l.strip().startswith("."))


def build(strcpy=STRCPY):
    from keystone import Ks, KS_ARCH_MIPS, KS_MODE_MIPS32, KS_MODE_LITTLE_ENDIAN
    ks = Ks(KS_ARCH_MIPS, KS_MODE_MIPS32 + KS_MODE_LITTLE_ENDIAN)
    src = source(strcpy)
    code = bytes(ks.asm(src, CODE)[0])
    assert len(code) == 4 * _count(src), (len(code), 4 * _count(src))
    assert CODE + len(code) <= REGION_END, "converter too long: %#x" % (CODE + len(code))
    return code


def apply(m, base):
    """Patch module bytes m (bytearray loaded at base) in place."""
    def w(a):
        return struct.unpack_from("<I", m, a - base)[0]
    # The original release's libc is 0x6c earlier; both call sites must
    # agree before installing a converter with the matching fallback.
    matches = [a for a in (STRCPY, STRCPY - 0x6C)
               if all(w(h) == 0x0C000000 | ((a & 0x0FFFFFFF) >> 2) for h in HOOKS)]
    if len(matches) != 1:
        raise ValueError("unexpected EVS strcpy calls")
    ptrs = list(struct.unpack_from("<%dI" % KANJI_N, m, KANJI_PTRS - base))
    ptrs = [EMPTY if REGION <= p < REGION_END else p for p in ptrs]
    struct.pack_into("<%dI" % KANJI_N, m, KANJI_PTRS - base, *ptrs)
    code = build(matches[0])
    blob = b"\0\0\0\0" + table() + b"\0" * 32 + code
    m[REGION - base:REGION_END - base] = blob + b"\0" * (REGION_END - REGION - len(blob))
    for h in HOOKS:
        struct.pack_into("<I", m, h - base, 0x0C000000 | ((CODE & 0x0FFFFFFF) >> 2))
