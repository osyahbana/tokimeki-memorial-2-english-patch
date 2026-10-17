"""Name tables that English needs more room in (docs/game-internals.md 13.3).

Some short strings are reached only through pointers or lui + addiu pairs,
so they need not stay where they are: the names the scene codes insert
({char:NN}: surname, given name, nickname of every girl), the girls' given
names in the EXE, and the surname lists. The Japanese fields are 3-7 bytes,
too small for "Minazuki" or "Ichimonji", but the block as a whole has room:
each BLOCK is rewritten with the English strings packed one after another
(identical ones shared), and every pointer / addiu that pointed at a string
is pointed at its new place.

The English comes from translations/_ui.json (the strings keep their usual
ids); "{none}" means an empty string (e.g. to drop an honorific). A block is
only touched when its strings and references are exactly as expected.
"""
import struct

# (module, first address, end address, the strings expected there, in order)
BLOCKS = [
    ("ENGINE", 0x800C132C, 0x800C1424,       # {char:NN}: table at 0x80111588 (surname, given, nickname)
     "メイ様 メイ 伊集院 マネージャー 楓子 佐倉 花桜梨 八重 会長 ほむら 赤井 みほぴょん 美帆 白雪 "
     "茜ちん 茜 一文字 ゆっきー 美幸 寿 琴子 水無月 光 陽ノ下 華澄 麻生 匠 純 麻生先生 華澄先生".split()),
    ("ENGINE", 0x800C04D4, 0x800C0538,       # surnames, table at 0x80110640
     "穂刈 坂城 伊集院 佐倉 八重 赤井 白雪 一文字 寿 水無月 陽ノ下 麻生".split()),
    ("EXE", 0x8006C994, 0x8006C9FC,          # given names, table at 0x80063048
     "すみれ 真帆 メイ 楓子 花桜梨 ほむら 美帆 茜 美幸 琴子 光 華澄".split()),
    ("OV1", 0x8013DE38, 0x8013DE9C,          # phone book surnames, lui + addiu in the code
     "陽ノ下 水無月 寿 一文字 白雪 赤井 八重 佐倉 伊集院 麻生 坂城 穂刈".split()),
]
NONE = "{none}"
ORIGINAL_SHIFTS = {"ENGINE": -0x20, "EXE": -0x6C, "OV1": 0x10}


def resolve_block(M, B, block):
    """Select a known revision only when the entire ordered string list matches."""
    mod, lo, hi, expect = block
    matches = []
    for shift in (0, ORIGINAL_SHIFTS.get(mod, 0)):
        candidate = (mod, lo + shift, hi + shift, expect)
        try:
            texts = [s.decode('cp932') for _, s in _strings(M, B, lo + shift, hi + shift)]
        except (ValueError, IndexError, UnicodeError):
            continue
        if texts == expect and candidate not in matches:
            matches.append(candidate)
    return matches[0] if len(matches) == 1 else block


def _strings(M, B, lo, hi):
    """[(address, bytes)] of the non-empty NUL-terminated strings in [lo, hi)."""
    out, a = [], lo
    while a < hi:
        if M[a - B] == 0:
            a += 1
            continue
        e = M.index(b"\0", a - B) + B
        out.append((a, bytes(M[a - B:e - B])))
        a = e + 1
    return out


def _refs(M, B, lo, hi):
    """(pointer word offsets, [(addiu offset, hi part)]) aiming into [lo, hi)."""
    n = len(M) // 4
    W = struct.unpack_from("<%dI" % n, M, 0)
    ptrs = [i * 4 for i, w in enumerate(W) if lo <= w < hi]
    code, last = [], {}
    for i, w in enumerate(W):
        op, rs, rt, imm = w >> 26, (w >> 21) & 31, (w >> 16) & 31, w & 0xFFFF
        if op == 0xF:
            last[rt] = (imm << 16, i)
        elif op == 9 and rs in last and i - last[rs][1] <= 24:
            v = (last[rs][0] + (imm - 0x10000 if imm & 0x8000 else imm)) & 0xFFFFFFFF
            if lo <= v < hi:
                code.append((i * 4, last[rs][0]))
    return ptrs, code


def plan(M, B, block, en):
    """New block bytes and reference fixes for module bytes M at B, or a
    reason string. en(ja) -> English (str), or None to keep the Japanese."""
    import uitext
    mod, lo, hi, expect = block
    S = _strings(M, B, lo, hi)
    texts = [s.decode("cp932", "replace") for _, s in S]
    if texts != expect:
        return "strings differ (%s)" % repr(" ".join(texts[:4])[:80])
    ptrs, code = _refs(M, B, lo, hi)
    starts = {a for a, _ in S}

    targets = [struct.unpack_from("<I", M, p)[0] for p in ptrs]
    for off, hipart in code:
        imm = struct.unpack_from("<I", M, off)[0] & 0xFFFF
        targets.append((hipart + (imm - 0x10000 if imm & 0x8000 else imm)) & 0xFFFFFFFF)
    reserve = set()
    for t in targets:
        if t not in starts:
            if M[t - B] != 0:
                return "a reference points inside a string (%#x)" % t
            reserve.add(t)                  # an empty string: keep it where it is
    # new strings, packed
    body, where, seen = bytearray(), {}, {}
    for (a, s), t in zip(S, texts):
        e = en(t)
        b = s if e is None else (b"" if e == NONE else uitext.encode(e, t))
        if b in seen:
            where[a] = seen[b]
            continue
        pos = lo + len(body)
        while any(pos <= r < pos + len(b) for r in reserve):    # step over the empty string
            body += b"\0"
            pos = lo + len(body)
        where[a] = seen[b] = pos
        body += b + b"\0"
    if lo + len(body) > hi:
        return "English needs %d bytes, the block has %d" % (len(body), hi - lo)
    new = bytes(body) + b"\0" * (hi - lo - len(body))
    if any(new[r - lo] for r in reserve):
        return "empty string overwritten"
    fixes = []
    for p in ptrs:
        t = struct.unpack_from("<I", M, p)[0]
        if t in where:
            fixes.append((p, struct.pack("<I", where[t])))
    for off, hipart in code:
        w = struct.unpack_from("<I", M, off)[0]
        imm = w & 0xFFFF
        t = (hipart + (imm - 0x10000 if imm & 0x8000 else imm)) & 0xFFFFFFFF
        if t not in where:
            continue
        d = where[t] - hipart
        if not -0x8000 <= d < 0x8000:
            return "new address out of addiu range"
        fixes.append((off, struct.pack("<I", (w & 0xFFFF0000) | (d & 0xFFFF))))
    return new, fixes


def resolved_blocks(data, path):
    import uitext
    mods = {name: (off, B, size) for name, off, B, size in uitext.modules(data, path)}
    out = []
    for block in BLOCKS:
        if block[0] not in mods:
            continue
        off, B, size = mods[block[0]]
        M = data[off:off + size]
        candidate = resolve_block(M, B, block)
        if not isinstance(plan(M, B, candidate, lambda ja: None), str):
            out.append(candidate)
    return out


def covers(module, addr, blocks=None):
    return any(m == module and lo <= addr < hi
               for m, lo, hi, _ in (BLOCKS if blocks is None else blocks))


def apply(data, path, ui, pre):
    """Rewrite every block in the disc data. ui: {id: English}; pre(offset,
    bytes) writes into the image (the builder's pre-edit). Returns
    ([done], [notes])."""
    import uitext
    import hashlib
    mods = {name: (off, B, size) for name, off, B, size in uitext.modules(data, path)}

    def en(ja):
        return ui.get("ui-" + hashlib.sha1(ja.encode("utf-8")).hexdigest()[:10])
    done, notes = [], []
    for block in BLOCKS:
        mod, lo, hi, _ = block
        if mod not in mods:
            notes.append("%s %#x: module not on this disc" % (mod, lo))
            continue
        off, B, size = mods[mod]
        M = data[off:off + size]
        block = resolve_block(M, B, block)
        mod, lo, hi, _ = block
        r = plan(M, B, block, en)
        if isinstance(r, str):
            notes.append("%s %#x: left alone, %s" % (mod, lo, r))
            continue
        new, fixes = r
        pre(off + lo - B, new)
        for o, b in fixes:
            pre(off + o, b)
        done.append("%s@%08x (%d refs)" % (mod, lo, len(fixes)))
    return done, notes
