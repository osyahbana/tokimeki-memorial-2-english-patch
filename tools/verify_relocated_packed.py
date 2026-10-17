"""Regression: an in-place packed scene must follow a relocated group.

Usage: python tools/verify_relocated_packed.py DISC.bin SCENE-KEY TRANSLATIONS
Only reads the source image; constructs the moved group in memory.
"""
import sys
import build_patch
import extract_scripts as X
import groups
import rebuild
import scenes
import translations


def main(path, key, tl_dir):
    data = X.read_user_data(path)
    block = next(b for b in scenes.scan(data) if b.key == key)
    assert block.kind == "packed" and block.off % 2048 == 0
    gs = groups.find_groups(data)
    group, index, length = groups.variant_of(gs)[block.off // 2048]
    tl, names = translations.load([tl_dir])
    edits = build_patch.edits_for(block, tl, names)
    expected = rebuild.rebuild(data[block.off:block.off + block.end], edits, english=True)
    assert len(expected) <= block.end
    builder = build_patch.Builder(data, gs)
    builder.build([block], tl, names)
    assert not builder.errors, builder.errors
    builder.force_move.add(group.sector)
    builder.rebuild_group(group, {})
    assert not builder.errors and builder.moved
    variant_offset = sum(n for i, s, n in group.variants() if i < index)
    copied = b"".join(builder.append[variant_offset:variant_offset + length])
    assert copied[:len(expected)] == expected
    assert copied[block.end:] == data[block.off + block.end:block.off + length * 2048]
    print("PASS:", key, "translated bytes and trailing data survive group relocation")


if __name__ == "__main__":
    main(*sys.argv[1:])
