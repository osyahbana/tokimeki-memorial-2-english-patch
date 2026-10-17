"""English date box on the main screen (Discs 2-5): "1999 5/16 (Su)".

The box (docs/game-internals.md section 15.1) is drawn from tiles of the
main-screen texture (pictures/main_stats_hands.png): the year, month and
day digits and the weekday are placed by code (main-screen module, the
function at 0x800E9E5C), and the fixed tiles 年 月 日 ( ) come from a table
of 12-byte entries (s16 x, s16 y, u8 u, v, w, h, u32 flags; x relative to
the box) at 0x80116A50. 月 and 日 are also the Monday and Sunday tiles, so
the weekday tiles (row 0) become Su Mo Tu We Th Fr Sa and the markers are
repointed:

  年  -> an empty 8x8 patch of the texture (u 64, v 72): nothing drawn
  月  -> the old 年 tile (u 32, v 16), redrawn as "/", moved 1 px left
  日  -> nothing (as 年)
  ( ) -> moved left to close the gap the 日 marker leaves
  weekday x (code, addiu v0, zero, -75 at 0x800EA0B8) -> -88
  day tens (code, slti v0, s4, 10 at 0x800EA3E4: skip the tens digit
    below 10) -> slti v0, s4, 0, so days get a leading zero ("5/03");
    the month can't (its tens tile is fixed to "1"), so it is left as is

A table copy is patched only when the module's weekday code sits at the
same distance before it (the main-screen module; Disc 2 sectors 1643 and
1732). Other copies of the table (Disc 2 sector 12418, a module without
this code) are left alone and reported.
"""
import struct

ORIG = bytes.fromhex(
    "c4001600" "78000810" "00000000"     # )  x 196
    "ad001600" "70000810" "00000000"     # (  x 173
    "9d001600" "00001010" "00000000"     # 日 x 157
    "75001600" "10001010" "00000000"     # 月 x 117
    "4e001600" "20101010" "00008000")    # 年 x 78 (last entry)
BLANK = (64, 72, 8, 8)


def _entry(x, y, u, v, w, h, flags):
    return struct.pack("<hhBBBBI", x, y, u, v, w, h, flags)


NEW = (_entry(181, 0x16, 120, 0, 8, 16, 0)          # )
       + _entry(161, 0x16, 112, 0, 8, 16, 0)        # (
       + _entry(157, 0x16, *BLANK, 0)               # 日: nothing
       + _entry(116, 0x16, 32, 16, 16, 16, 0)       # 月: "/" (old 年 tile)
       + _entry(78, 0x16, *BLANK, 0x800000))        # 年: nothing
assert len(NEW) == len(ORIG)

CODE_BACK = 0x2C998                                  # table - weekday-x instruction
CODE_ORIG = struct.pack("<I", 0x2402FFB5)            # addiu v0, zero, -75
CODE_NEW = struct.pack("<I", 0x24020000 | (-88 & 0xFFFF))
DAY_AT = 0x32C                                       # after the weekday-x instruction
DAY_ORIG = struct.pack("<I", 0x2A82000A)             # slti v0, s4, 10
DAY_NEW = struct.pack("<I", 0x2A820000)              # slti v0, s4, 0


def find(data):
    """([(table offset, code offset)], [table offsets left alone])."""
    ok, skipped = [], []
    p = data.find(ORIG)
    while p >= 0:
        matches = [p - back for back in (CODE_BACK, CODE_BACK - 0x10)
                   if p >= back and data[p-back:p-back+4] == CODE_ORIG
                   and data[p-back+DAY_AT:p-back+DAY_AT+4] == DAY_ORIG]
        if len(matches) == 1:
            c = matches[0]
            ok.append((p, c))
        else:
            skipped.append(p)
        p = data.find(ORIG, p + 1)
    return ok, skipped


def patch_image(path):
    """Patch a disc image in place. Returns (sectors written, notes)."""
    import cdimage
    import extract_scripts as X
    data = X.read_user_data(path)
    ok, skipped = find(data)
    written = []
    with open(path, "r+b") as f:
        for off, new in [(t, NEW) for t, _ in ok] + [(c, CODE_NEW) for _, c in ok] + [(c + DAY_AT, DAY_NEW) for _, c in ok]:
            s0 = off // 2048
            n = (off % 2048 + len(new) + 2047) // 2048
            old = cdimage.read_user_data(f, s0, n)
            buf = bytearray(old)
            o = off - s0 * 2048
            buf[o:o + len(new)] = new
            written += cdimage.write_changed(f, s0, old, bytes(buf))
    notes = ["date table at %d:%d left alone (no weekday code before it)" % (p // 2048, p % 2048)
             for p in skipped]
    return written, notes
