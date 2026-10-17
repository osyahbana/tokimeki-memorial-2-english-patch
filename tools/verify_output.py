"""Read-only validation of translated live scenes and changed CD sectors."""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path

import cdimage
import extract_scripts as X
import glyphpatch
import groups
import overlays
import rebuild
import scenes
import script
import translations


def edits_for(block, tl, names):
    edits = {int(k): v for k, v in tl.get(block.key, {}).items()}
    for msg in block.messages:
        if msg.get('speaker'):
            label = X.fmt_tokens(msg['speaker'])
            if label in names:
                edits.setdefault(msg['offset'], names[label])
    return edits


def missing_dialogue(blocks, tl):
    return [{'scene': b.key, 'offset': line['offset']}
            for b in blocks for msg in b.messages for line in msg['lines']
            if not tl.get(b.key, {}).get(str(line['offset']), '').strip()]


def read_exe(path):
    with open(path, 'rb') as f:
        _, lba, size = glyphpatch.find_exe(f)
        return cdimage.read_user_data(f, lba, (size + 2047) // 2048)


def missing_speakers(blocks, tl, names):
    out = []
    for block in blocks:
        edits = edits_for(block, tl, names)
        for msg in block.messages:
            if not msg.get('speaker'):
                continue
            label = X.fmt_tokens(msg['speaker'])
            # Dynamic name codes need no translation; literal labels do.
            if re.sub(r'\{[^}]*\}|\s', '', label) and not edits.get(msg['offset'], '').strip():
                out.append({'scene': block.key, 'offset': msg['offset'], 'label': label})
    return out


def verify_dialogue(before, after, blocks, old_exe, new_exe, tl, names):
    """Follow live container pointers, rather than checking abandoned copies."""
    old_groups = groups.find_groups(before)
    new_groups = groups.find_groups(after)
    variants = groups.variant_of(old_groups)
    old_overlays = overlays.block_map(overlays.find(before, old_exe))
    new_overlays = {ov.index: ov for ov in overlays.find(after, new_exe)}
    verified, instances, errors = 0, 0, []
    for block in blocks:
        edits = edits_for(block, tl, names)
        if not edits:
            continue
        pos = block.off
        # Packed blocks can be group variants too: their trailing data stops
        # scenes.scan classifying them as a growable file.
        if pos % 2048 == 0 and pos // 2048 in variants:
            group, i, _ = variants[pos // 2048]
            group = new_groups[group.sector]
            pos = (group.sector + group.e[i]) * 2048
        elif block.kind in ('bundle', 'pack'):
            sector, i = block.bundle
            _, sizes, starts = scenes.read_bundle(after, sector * 2048)
            pos = starts[i]
            if block.pack is not None:
                pos += scenes.read_pack(after, pos, sizes[i])[block.pack]
        elif block.off in old_overlays:
            ov, pack, i = old_overlays[block.off]
            ov = new_overlays[ov.index]
            pos = ov.start + pack + ov.packs[pack][i]
        current = script.messages(after, pos)['messages']
        if len(current) != len(block.messages):
            errors.append(f'{block.key}: message count changed')
            continue
        instances += 1
        for old, new in zip(block.messages, current):
            if bool(old['speaker']) != bool(new['speaker']) or len(old['lines']) != len(new['lines']):
                errors.append(f'{block.key}: message structure changed')
                continue
            pairs = [(old['offset'], new['offset'])] if old['speaker'] else []
            pairs.extend((a['offset'], b['offset']) for a, b in zip(old['lines'], new['lines']))
            for old_at, new_at in pairs:
                if old_at not in edits:
                    continue
                expected = rebuild.encode_en(edits[old_at])
                actual = after[pos + new_at + 1:pos + new_at + 1 + len(expected)]
                if actual != expected:
                    errors.append(f'{block.key}/{old_at}: translated bytes differ at live location')
                else:
                    verified += 1
    return {'scene_instances': instances, 'verified_strings': verified, 'errors': errors}


def verify_sectors(source, output):
    """Hash both files and regenerate EDC/ECC for every differing sector."""
    hashes = [hashlib.sha256(), hashlib.sha256()]
    changed = appended = count = 0
    errors = []
    with open(source, 'rb') as src, open(output, 'rb') as dst:
        while True:
            old, new = src.read(2352), dst.read(2352)
            if not old and not new:
                break
            hashes[0].update(old)
            hashes[1].update(new)
            if old != new:
                changed += 1
                appended += not bool(old)
                if len(new) != 2352 or not cdimage.is_form1(new):
                    errors.append(f'sector {count}: missing or invalid Mode 2 Form 1 sector')
                else:
                    fixed = bytearray(new)
                    cdimage.fix_form1(fixed)
                    if fixed != new:
                        errors.append(f'sector {count}: invalid EDC/ECC')
            count += 1
    return {'source_sha256': hashes[0].hexdigest(), 'output_sha256': hashes[1].hexdigest(),
            'changed_sectors': changed, 'appended_sectors': appended, 'errors': errors}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source')
    parser.add_argument('output')
    parser.add_argument('--tl', action='append')
    parser.add_argument('--json', dest='report')
    args = parser.parse_args(argv)
    if args.report:
        target = Path(args.report)
        if any(target.resolve() == Path(p).resolve() or
               (target.exists() and Path(p).exists() and os.path.samefile(target, p))
               for p in (args.source, args.output)):
            parser.error('report must not overwrite an image')
    tl, names = translations.load(args.tl or [translations.DEFAULT])
    before, after = X.read_user_data(args.source), X.read_user_data(args.output)
    blocks = scenes.scan(before)
    report = {'dialogue': verify_dialogue(before, after, blocks, read_exe(args.source),
                                         read_exe(args.output), tl, names),
              'missing_dialogue': missing_dialogue(blocks, tl),
              'missing_speakers': missing_speakers(blocks, tl, names),
              'sectors': verify_sectors(args.source, args.output)}
    passed = not (report['dialogue']['errors'] or report['missing_dialogue'] or report['missing_speakers'] or report['sectors']['errors'])
    report['passed'] = passed
    if args.report:
        target = Path(args.report)
        target.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
