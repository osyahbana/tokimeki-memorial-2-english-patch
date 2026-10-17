"""Menu and system text in the game's code (not in scene scripts).

Plain Shift-JIS, NUL-terminated strings in the EXE, the main engine and the
8 code overlays (docs/game-internals.md section 13). A string is taken when

  * it starts on a 4-byte boundary and its NUL is followed by zero padding
    to the next one (strings in these files always are; code and data that
    happen to look like text usually are not), and
  * the code points at it: a u32 pointer, or a lui + addiu/ori pair, or it
    is one of a run of 4 or more such strings at a constant stride (tables
    indexed by number: the phone book, the date places in the phone module).
    When every entry of such a table is padded to the same width, the game
    draws exactly that many cells (verified, experiment 11: the phone book
    showed garbage after a shorter name and cut a longer one), so English
    is padded to it and may not exceed it.

Place names in scene scripts (the label shown when you're somewhere) are
records in the script's data area: scene_places().

Verified on screen (experiments 9, 10): such strings are drawn by the normal
text routine, so English letter pairs work in them. They are replaced in
place: the English must fit the string's field (its bytes, NUL and padding).
"""
import collections
import hashlib
import itertools
import re
import struct

import cdimage
import glyphpatch
import overlays as OV

SJ = rb"(?:[\x81-\x9f\xe0-\xea][\x40-\x7e\x80-\xfc])"
STR = re.compile(rb"(?:" + SJ + rb"|[\x20-\x7e]|\n){1,160}\x00")
ENGINE_ADDR, ENGINE_SIZE = 0x800C0000, 0x60000
ENGINE_SECTOR = {"SLPM_863.55": 2252}            # Disc 1; the others: 1559
EXE_BASE = 0x80015800
# The name-entry screen's module (Disc 1, tools/namepatch.py): only its
# prompts and messages. The kana rows, symbol list and kanji rows between
# them are the input grids, which namepatch / evsname rewrite.
NAME_MODULE = {"SLPM_863.55": (2038 * 2048, 0x800C0000, 0xE000)}
NAME_TEXT = [(0x800C0188, 0x800C0248),      # name, birthday and blood-type prompts
             (0x800C2170, 0x800C2908)]      # memory card, E.V.S. and girl-name messages
# The E.V.S. ("SOUND ROOM") module (Disc 1, tools/evsgrid.py): stored with
# every byte +0x64 and the first byte dropped. Only its messages: it also
# holds the reading grid, the kana pieces it builds voiced nicknames from
# and a list of words refused as names, which must stay as they are.
# The childhood engine (Disc 1, the prologue's scenes; also loaded at
# 0x800C0000): only its speech mark 「, the rest is digit tiles and data.
CHILD_MODULE = {"SLPM_863.55": (35248 * 2048, 0x800C0000, 0x2BC00)}
CHILD_TEXT = [(0x800C021C, 0x800C0220)]
EVS_MODULE = {"SLPM_863.55": (1505 * 2048, 0x800C0000, 96 * 2048 - 1)}
EVS_TEXT = [(0x800C02E0, 0x800C03BC),       # button patterns, names
            (0x800C0488, 0x800C0B00),       # labels, memory card messages, girl names
            (0x800C17A0, 0x800C1DBC),       # E.V.S. data messages
            (0x800E6900, 0x800E6910)]       # "の読み方" after the name


class UIString:
    def __init__(self, module, off, addr, ja, size, field):
        self.module, self.off, self.addr = module, off, addr
        self.ja, self.size, self.field = ja, size, field   # bytes of text; bytes available incl. NUL
        self.count_off = None      # scene place records: disc offset of the character count
        self.cells = None          # fixed-width tables: the game draws exactly this many cells
        self.obf = 0               # added to every byte written (the EVS module is stored +0x64)

    @property
    def max_bytes(self):
        n = self.field - 1
        return min(n, 2 * self.cells) if self.cells else n

    @property
    def text(self):
        """The Japanese without its full-width-space padding (what translators see)."""
        return self.ja.rstrip("\u3000")

    @property
    def id(self):
        """Same text, same id, whatever its padding or place."""
        return "ui-" + hashlib.sha1(self.text.encode("utf-8")).hexdigest()[:10]

    @property
    def where(self):
        return "%s@%08x" % (self.module, self.addr)


def modules(data, path):
    """[(name, byte offset in disc data, RAM address, size)]."""
    with open(path, "rb") as f:
        name, lba, size = glyphpatch.find_exe(f)
        exe = cdimage.read_user_data(f, lba, -(-size // 2048))
    tsize = struct.unpack_from("<I", exe, 0x1C)[0]
    mods = [("EXE", lba * 2048 + 0x800, EXE_BASE, tsize)]
    mods.append(("ENGINE", ENGINE_SECTOR.get(name, 1559) * 2048, ENGINE_ADDR, ENGINE_SIZE))
    for ov in OV.find(data, exe):
        mods.append(("OV%d" % ov.index, ov.start, ov.slot_addr, ov.size))
    if name in NAME_MODULE:
        mods.append(("NAME",) + NAME_MODULE[name])
    if name in EVS_MODULE:
        mods.append(("EVS",) + EVS_MODULE[name])
    if name in CHILD_MODULE:
        mods.append(("CHILD",) + CHILD_MODULE[name])
    return mods


def _refs(D, B):
    n = len(D) // 4
    W = struct.unpack_from("<%dI" % n, D, 0)
    out = collections.Counter(w for w in W if B <= w < B + len(D))
    hi = {}
    for i, w in enumerate(W):
        op, rs, rt, imm = w >> 26, (w >> 21) & 31, (w >> 16) & 31, w & 0xFFFF
        if op == 0xF:
            hi[rt] = (imm << 16, i)
        elif op in (9, 0xD) and rs in hi and i - hi[rs][1] <= 24:
            v = (hi[rs][0] + ((imm - 0x10000) if op == 9 and imm & 0x8000 else imm)) & 0xFFFFFFFF
            if B <= v < B + len(D):
                out[v] += 1
    return out


def _candidates(D, B, refs=None):
    """Aligned, zero-padded Shift-JIS strings in module bytes D loaded at B;
    with refs, also packed ones (any alignment, right after another string's
    NUL) that the code points at directly: their field is just text + NUL
    (the file-select prompts, "ロードを実行\nしますか？", are such)."""
    for m in STR.finditer(D):
        s, st = m.group()[:-1], m.start()
        e = m.end()
        field_end = (e + 3) & ~3
        if st % 4 or D[e:field_end].strip(b"\0"):
            if refs is None or not refs.get(B + st) or (st and D[st - 1] != 0):
                continue
            field_end = e                  # packed: no padding to use
        elif st and D[st - 1] != 0 and not B <= struct.unpack_from("<I", D, st - 4)[0] < B + len(D):
            continue                       # not after zero padding or a pointer: inside other data
        try:
            t = s.decode("cp932")
        except UnicodeDecodeError:
            continue
        if not any(ord(c) > 0x3000 for c in t) or any(c.isascii() and c not in " \n" for c in t):
            continue                       # no Japanese, or printf-style ASCII inside
        yield st, t, len(s), field_end - st


def scan(data, path):
    """Strings the code points at, plus tables: runs of 4 or more strings at a
    constant stride (name lists indexed by number, e.g. the phone book)."""
    out = []
    for name, off, B, size in modules(data, path):
        shift, obf = 0, 0
        if name == "EVS":                  # module byte i is disc byte i + 1, stored + 0x64
            D = bytes((b - 0x64) & 0xFF for b in data[off + 1:off + 1 + size])
            shift, obf = 1, 0x64
        else:
            D = data[off:off + size]
        refs = _refs(D[:len(D) // 4 * 4], B)
        cand = list(_candidates(D, B, refs))
        if name == "EVS":
            import evsgrid
            rows, rows_end, _, _ = evsgrid.layout(D)
            ranges = EVS_TEXT
            if rows == evsgrid.ROWS - 0x18:
                ranges = [(0x800C02E0, rows), (rows_end, 0x800C0B00),
                          (0x800C1724, 0x800C1D40), (0x800E69C4, 0x800E69D4)]
            cand = [c for c in cand if any(lo <= B + c[0] < hi for lo, hi in ranges)]
        if name == "CHILD":
            cand = [c for c in cand if any(lo <= B + c[0] < hi for lo, hi in CHILD_TEXT)]
        if name == "NAME":
            cand = [c for c in cand if any(lo <= B + c[0] < hi for lo, hi in NAME_TEXT)]
        take = {st for st, t, n, f in cand if refs.get(B + st)}
        starts = [st for st, t, n, f in cand]
        texts = {st: t for st, t, n, f in cand}
        fixed = {}
        i = 0
        while i < len(starts) - 3:          # constant-stride runs
            d = starts[i + 1] - starts[i]
            j = i + 1
            while j + 1 < len(starts) and starts[j + 1] - starts[j] == d:
                j += 1
            if j - i + 1 >= 4 and d <= 64:
                take.update(starts[i:j + 1])
                # consecutive entries padded with full-width spaces to the same
                # width (3 or more; a run can take in the first entry of the next
                # table): the game draws that many cells
                for _, grp in itertools.groupby(starts[i:j + 1], key=lambda st: len(texts[st])):
                    grp = list(grp)
                    if len(grp) >= 3 and any("\u3000" in texts[st] for st in grp) and \
                            all(len(texts[st].encode("cp932")) == 2 * len(texts[st]) for st in grp):
                        for st in grp:
                            fixed[st] = len(texts[st])
            i = j if j > i + 1 else i + 1
        for st, t, n, f in cand:
            if st not in take:
                continue
            if name == "EXE" and B + st < 0x80016000:
                continue                   # memory-card file titles: leave alone
            u = UIString(name, off + shift + st, B + st, t, n, f)
            u.cells = fixed.get(st)
            u.obf = obf
            out.append(u)
    return out


def scene_places(data, blocks):
    """Place names in scene-script data (docs/game-internals.md section 13.2).
    The third u16 at +0x22 of the block header is the offset of a table of
    32-byte records (2-byte aligned) ending with u16 0xFFFF:

        u16 id, u8 background, u8 number of characters, 28-byte Shift-JIS name

    Records whose character count doesn't match their name are skipped.
    Returns UIStrings whose module is "SCENE:<block key>"; .count_off is the
    disc offset of the character count (rewritten with the number of cells
    drawn)."""
    out = []
    for b in blocks:
        code = struct.unpack_from("<H", data, b.off + 4)[0]
        r = struct.unpack_from("<H", data, b.off + 0x26)[0]
        if not 0x30 <= r < code:
            continue
        while r + 32 <= code and data[b.off + r:b.off + r + 2] != b"\xff\xff":
            p = b.off + r
            t = data[p + 4:p + 32].rstrip(b"\0")
            ok = len(t) >= 2 and b"\0" not in t and len(t) % 2 == 0 and data[p + 3] == len(t) // 2
            if ok:
                try:
                    txt = t.decode("cp932")
                except UnicodeDecodeError:
                    ok = False
            if ok and len(txt) == len(t) // 2 and all(ord(c) > 0x3000 for c in txt) and txt.strip("\u3000"):
                u = UIString("SCENE:" + b.key, p + 4, r + 4, txt, len(t), 28)
                u.count_off = p + 3
                out.append(u)
            r += 32
    return out


def encode(text, ja, cells=None):
    """English (font_en charset; other characters full-width) -> bytes, no NUL.
    Padded with blank cells to `cells` cells (fixed-width tables: the game
    draws that many cells whatever the NUL), or, for a Japanese field padded
    with full-width spaces, to its width."""
    import font_en
    if text == "{none}":                 # an empty string (e.g. a dropped honorific)
        return b""
    out, pend = bytearray(), []

    def flush():
        if pend:
            out.extend(font_en.pair_code(pend[0], pend[1] if len(pend) > 1 else " "))
            pend.clear()
    for ch in text:
        if ch == "\n":                    # line break: the menu text routine's 0x0A
            flush()
            out += b"\n"
            continue
        if font_en.is_supported(ch):
            pend.append(ch)
            if len(pend) == 2:
                flush()
        else:
            flush()
            out += font_en.wide(ch)
    flush()
    width = cells or (len(ja) if ja.endswith("　") else 0)
    if width:
        while len(out) < 2 * width:
            out += font_en.pair_code(" ", " ")
    return bytes(out)
