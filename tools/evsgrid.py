"""Romaji labels on the EVS reading screen (Disc 1, "SOUND ROOM").

The EVS setup asks how to pronounce your name ("Kabay の読み方") and offers
a kana grid; the voice is built from those kana, so the value picked must
stay kana. This patch only changes what the cells show.

The module is obfuscated on the disc (Disc 1 sector 1505; every byte +0x64,
first byte dropped; loaded at 0x800C0000; docs/game-internals.md section
14.1). Its grid is 17 row strings at 0x800C03BC (one 2-byte character per
cell) listed in a table of 24-byte entries at 0x800E6DA0 (string pointer
first). When a cell is picked, 0x800CB924 reads the character from the
entry's string at 0x800CBA00 / 0x800CBA18 (`lbu v0, 0(v0)` / `lbu v0, 1(v1)`).

The patch writes a copy of the rows with every kana replaced by a letter
pair of the same size, at 0x800C0170 (over unused developer file paths,
"\\t2\\data\\..."), points the table at the copy, and adds the distance back
in the two reads (their offsets become 0x24C / 0x24D), so the cell you pick
still yields the kana. Two letters per cell: し ち つ ふ じ ぢ づ show as
si ti tu fu ji di du. The small kana, which change the cell before them,
show as -a -i -u -e -o ("fu" + "-i" = fi), -t (っ, doubles the next
consonant) and Ya Yu Yo ("ki" + "Ya" = kya; capitals tell them from the
ordinary ya yu yo).
"""
import struct

SECTOR = 1505
N_SECTORS = 96
BASE = 0x800C0000
ROWS = 0x800C03BC
ROWS_END = 0x800C0488
COPY = 0x800C0170
DEV_PATHS = 0x800C016C        # "\t2\data\battle\fasc.bin" ... (unused)
DEV_PATHS_END = 0x800C02E0
TABLE, N_ROWS, STRIDE = 0x800E6DA0, 17, 24
READS = {0x800CBA00: 0x90420000, 0x800CBA18: 0x90620001}   # lbu v0,0(v0) / lbu v0,1(v1)
DELTA = ROWS - COPY

ROMAJI = {
    "あ": "a", "い": "i", "う": "u", "え": "e", "お": "o",
    "か": "ka", "き": "ki", "く": "ku", "け": "ke", "こ": "ko",
    "さ": "sa", "し": "si", "す": "su", "せ": "se", "そ": "so",
    "た": "ta", "ち": "ti", "つ": "tu", "て": "te", "と": "to",
    "な": "na", "に": "ni", "ぬ": "nu", "ね": "ne", "の": "no",
    "は": "ha", "ひ": "hi", "ふ": "fu", "へ": "he", "ほ": "ho",
    "ま": "ma", "み": "mi", "む": "mu", "め": "me", "も": "mo",
    "や": "ya", "ゆ": "yu", "よ": "yo", "ー": "-", "～": "~",
    "ら": "ra", "り": "ri", "る": "ru", "れ": "re", "ろ": "ro",
    "わ": "wa", "ゐ": "wi", "ゑ": "we", "を": "wo", "ん": "n",
    "が": "ga", "ぎ": "gi", "ぐ": "gu", "げ": "ge", "ご": "go",
    "ざ": "za", "じ": "ji", "ず": "zu", "ぜ": "ze", "ぞ": "zo",
    "だ": "da", "ぢ": "di", "づ": "du", "で": "de", "ど": "do",
    "ば": "ba", "び": "bi", "ぶ": "bu", "べ": "be", "ぼ": "bo",
    "ぱ": "pa", "ぴ": "pi", "ぷ": "pu", "ぺ": "pe", "ぽ": "po",
    # small kana change the cell before: fu + -i = fi, ki + Ya = kya, -t doubles
    "ぁ": "-a", "ぃ": "-i", "ぅ": "-u", "ぇ": "-e", "ぉ": "-o",
    "っ": "-t", "ゃ": "Ya", "ゅ": "Yu", "ょ": "Yo",
}


def deobfuscate(raw):
    return bytes((b - 0x64) & 0xFF for b in raw[1:])


def obfuscate_into(raw, mod):
    out = bytearray(raw)
    out[1:1 + len(mod)] = bytes((b + 0x64) & 0xFF for b in mod)
    return bytes(out)


def label(ch):
    import font_en
    r = ROMAJI[ch]
    return font_en.pair_code(r[0], r[1] if len(r) > 1 else " ")


def layout(mod):
    """Guarded (rows, rows_end, table, reads) for Rev 1 or original Japan."""
    variants = [(ROWS, ROWS_END, TABLE, READS),
                (ROWS - 0x18, ROWS_END - 0x18, TABLE + 0x108,
                 {a + 0xC4: w for a, w in READS.items()})]
    matches = []
    for rows, end, table, reads in variants:
        if len(mod) < table - BASE + STRIDE * N_ROWS:
            continue
        if not all(struct.unpack_from('<I', mod, a - BASE)[0] == w for a, w in reads.items()):
            continue
        ptrs = [struct.unpack_from('<I', mod, table - BASE + STRIDE*k)[0] for k in range(N_ROWS)]
        if len(set(ptrs)) == N_ROWS and all(rows <= p < end for p in ptrs):
            matches.append((rows, end, table, reads))
    if len(matches) != 1:
        raise ValueError('unrecognized EVS grid layout')
    return matches[0]


def patch_module(mod):
    m = bytearray(mod)

    def at(a, n=4):
        return bytes(m[a - BASE:a - BASE + n])

    if not at(DEV_PATHS, 16).startswith(b"\\t2\\data\\battle"):
        raise ValueError("not the EVS module (developer paths)")
    rows_addr, rows_end, table_addr, reads = layout(mod)
    delta = rows_addr - COPY
    for a, w in reads.items():
        if struct.unpack("<I", at(a))[0] != w:
            raise ValueError("not the EVS module (word at %#x)" % a)
    rows = at(rows_addr, rows_end - rows_addr)
    ptrs = [struct.unpack_from("<I", m, table_addr - BASE + STRIDE * k)[0] for k in range(N_ROWS)]
    if sorted(ptrs) != sorted(set(ptrs)) or not all(rows_addr <= p < rows_end for p in ptrs):
        raise ValueError("unexpected row table")
    copy = bytearray(rows)
    i = 0
    while i < len(rows):
        if rows[i] == 0:
            i += 1
            continue
        ch = rows[i:i + 2].decode("cp932")
        copy[i:i + 2] = label(ch)
        i += 2
    assert COPY + len(copy) <= DEV_PATHS_END
    m[COPY - BASE:COPY - BASE + len(copy)] = copy
    for k, p in enumerate(ptrs):
        struct.pack_into("<I", m, table_addr - BASE + STRIDE * k, p - delta)
    for a, w in reads.items():
        struct.pack_into("<I", m, a - BASE, (w & 0xFFFF0000) | ((w + delta) & 0xFFFF))
    return bytes(m)


def patch_image(path):
    """Patch a Disc 1 image in place; returns the sectors written ([] if the
    image has no such module)."""
    import cdimage
    with open(path, "r+b") as f:
        raw = cdimage.read_user_data(f, SECTOR, N_SECTORS)
        try:
            new = obfuscate_into(raw, patch_module(deobfuscate(raw)))
        except (ValueError, struct.error, UnicodeDecodeError, KeyError):
            return []
        return cdimage.write_changed(f, SECTOR, raw, new)


if __name__ == "__main__":
    import sys
    raw = open(sys.argv[1], "rb").read()
    mod = deobfuscate(raw)
    new = patch_module(mod)
    import font_en
    for k in range(N_ROWS):
        p = struct.unpack_from("<I", new, TABLE - BASE + STRIDE * k)[0]
        s = new[p - BASE:p - BASE + 12].split(b"\0")[0] if False else None
        o = p - BASE
        cells, kana = [], []
        while new[o]:
            cells.append("".join(font_en.decode_pair(new[o] << 8 | new[o + 1])))
            kana.append(new[o + DELTA:o + DELTA + 2].decode("cp932"))
            o += 2
        print(" ".join("%s=%s" % (c.strip(), k2) for c, k2 in zip(cells, kana)))
