import argparse
from contextlib import ExitStack
import io
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
import patch as cli
import build_patch
import cdimage
import groups
import pictures
import rebuild
import scenes
import script
import verify_output


class InputTests(unittest.TestCase):
    def test_unicode_relative_cue(self):
        with tempfile.TemporaryDirectory() as tmp:
            cue = Path(tmp) / '日本語.cue'
            cue.write_text('\ufeffFILE "sub folder/disc.bin" BINARY\n TRACK 01 MODE2/2352\n INDEX 01 00:00:00\n', encoding='utf-8')
            self.assertEqual(cli.cue_files(cue), [(cue.parent / 'sub folder/disc.bin').resolve()])

    def test_unsupported_cues_are_rejected(self):
        cases = ['FILE "a.bin" BINARY\nTRACK 01 AUDIO\nINDEX 01 00:00:00',
                 'FILE "a.bin" BINARY\nTRACK 01 MODE2/2352\nINDEX 01 00:02:00',
                 'FILE "a.bin" BINARY\nTRACK 01 MODE2/2352\nINDEX 01 00:00:00\nTRACK 02 AUDIO']
        with tempfile.TemporaryDirectory() as tmp:
            cue = Path(tmp) / 'bad.cue'
            for text in cases:
                cue.write_text(text)
                with self.subTest(text=text), self.assertRaises(ValueError):
                    cli.cue_files(cue)

    def test_missing_option_value_has_usage_error(self):
        with patch('sys.stderr', new=io.StringIO()), self.assertRaises(SystemExit) as error:
            cli.main(['game', '-o'])
        self.assertEqual(error.exception.code, 2)


class PublicationTests(unittest.TestCase):
    def test_hard_link_to_original_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / 'source.bin'; src.write_bytes(b'original')
            alias = Path(tmp) / 'alias.bin'
            try:
                os.link(src, alias)
            except OSError:
                self.skipTest('hard links not supported on this filesystem')
            with patch('sys.stderr', new=io.StringIO()), self.assertRaises(SystemExit):
                build_patch.main([str(src), str(alias)])
            self.assertEqual(src.read_bytes(), b'original')

    def test_success_generates_cue_for_output_filename(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / 'source.bin'; src.write_bytes(b'original')
            out = Path(tmp) / 'English name.bin'
            def succeed(args):
                p = Path(args.output); p.write_bytes(b'verified')
                p.with_suffix('.report.json').write_text('{"passed": true}')
                return 0
            with patch.object(build_patch, '_build', side_effect=succeed):
                self.assertEqual(build_patch.main([str(src), str(out)]), 0)
            self.assertEqual(out.read_bytes(), b'verified')
            self.assertEqual(cli.cue_files(out.with_suffix('.cue')), [out.resolve()])

    def test_failed_build_preserves_previous_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / 'source.bin'; src.write_bytes(b'original')
            out = Path(tmp) / 'out.bin'; out.write_bytes(b'previous')
            out.with_suffix('.cue').write_text('previous cue')
            def fail(args):
                Path(args.output).write_bytes(b'partial')
                return 1
            with patch.object(build_patch, '_build', side_effect=fail):
                self.assertEqual(build_patch.main([str(src), str(out)]), 1)
            self.assertEqual(src.read_bytes(), b'original')
            self.assertEqual(out.read_bytes(), b'previous')
            self.assertEqual(out.with_suffix('.cue').read_text(), 'previous cue')
            self.assertFalse(list(Path(tmp).glob('.tm2-build-*')))

    def test_exception_cleans_temporary_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / 'source.bin'; src.write_bytes(b'original')
            out = Path(tmp) / 'out.bin'
            with patch.object(build_patch, '_build', side_effect=ValueError('bad revision')):
                self.assertEqual(build_patch.main([str(src), str(out)]), 1)
            self.assertFalse(out.exists())
            self.assertFalse(list(Path(tmp).glob('.tm2-build-*')))

    def test_later_disc_failure_preserves_whole_previous_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp); out = base / 'output'; out.mkdir()
            inputs = []
            for n in (1, 2):
                src = base / f'Disc {n}.bin'; src.write_bytes(b'original')
                inputs.append((n, src, None)); (out / src.name).write_bytes(b'previous')
            playlist = out / 'Tokimeki Memorial 2 English.m3u'; playlist.write_text('previous playlist')
            def fake_build(args):
                p = Path(args[1]); p.write_bytes(b'new')
                p.with_suffix('.cue').write_text('new cue')
                p.with_suffix('.report.json').write_text('{}')
                return int('Disc 2' in args[0])
            with patch.object(cli, 'find_discs', return_value=inputs), patch.object(build_patch, 'main', side_effect=fake_build):
                self.assertEqual(cli.main(['unused', '-o', str(out), '-f']), 1)
            self.assertEqual(playlist.read_text(), 'previous playlist')
            self.assertTrue(all((out / src.name).read_bytes() == b'previous' for _, src, _ in inputs))
            self.assertFalse(list(out.glob('.tm2-set-*')))

    def test_uppercase_original_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / 'Original.BIN'; src.write_bytes(b'original')
            with patch.object(cli, 'find_discs', return_value=[(1, src, None)]), patch.object(build_patch, 'main') as builder:
                self.assertEqual(cli.main(['unused', '-o', tmp, '-f']), 1)
                builder.assert_not_called()
            self.assertEqual(src.read_bytes(), b'original')


class CoverageTests(unittest.TestCase):
    def test_literal_speaker_requires_translation_but_name_code_does_not(self):
        block = SimpleNamespace(key='scene', messages=[
            {'offset': 20, 'speaker': [('text', '三年目')], 'lines': []},
            {'offset': 30, 'speaker': [('code', 'name1')], 'lines': []}])
        self.assertEqual(len(verify_output.missing_speakers([block], {}, {})), 1)
        self.assertEqual(verify_output.missing_speakers([block], {}, {'三年目': 'Year 3'}), [])

    def test_missing_key_and_missing_line_are_reported(self):
        block = SimpleNamespace(key='scene-key', messages=[{'lines': [{'offset': 42}, {'offset': 50}]}])
        self.assertEqual(len(verify_output.missing_dialogue([block], {})), 2)
        self.assertEqual(verify_output.missing_dialogue([block], {'scene-key': {'42': 'hello'}}),
                         [{'scene': 'scene-key', 'offset': 50}])

    def test_incomplete_translation_fails_before_copy(self):
        block = SimpleNamespace(key='unknown', messages=[{'lines': [{'offset': 42}]}])
        args = SimpleNamespace(source='source.bin', output='out.bin', pictures=None, no_exe=False, tl=['tl'], allow_partial=False)
        with patch.object(build_patch.translations, 'load', return_value=({}, {}, {})), \
             patch.object(build_patch.X, 'read_user_data', return_value=b''), \
             patch.object(build_patch.scenes, 'scan', return_value=[block]), \
             patch.object(build_patch.shutil, 'copyfile') as copy:
            self.assertEqual(build_patch._build(args), 1)
            copy.assert_not_called()

    def test_no_exe_does_not_call_any_code_patch(self):
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            src = Path(tmp) / 'source.bin'; src.write_bytes(cdimage.make_form1(0, bytes(2048)))
            args = SimpleNamespace(source=str(src), output=str(Path(tmp) / 'out.bin'), pictures=None,
                                   no_exe=True, tl=[], allow_partial=False, move_group=[])
            for module, name, result in [(build_patch.translations, 'load', ({}, {}, {})),
                                         (build_patch.X, 'read_user_data', bytes(2048)),
                                         (build_patch.scenes, 'scan', []),
                                         (build_patch.glyphpatch, 'find_exe', ('SLPM_863.55', 0, 2048)),
                                         (build_patch.glyphpatch, 'detect_revision', 'original'),
                                         (build_patch.GR, 'find_groups', {}), (build_patch.OV, 'find', []),
                                         (verify_output, 'read_exe', b''),
                                         (verify_output, 'verify_dialogue', {'errors': [], 'verified_strings': 0})]:
                stack.enter_context(patch.object(module, name, return_value=result))
            guards = [stack.enter_context(patch.object(module, 'patch_image')) for module in
                      (build_patch.glyphpatch, build_patch.namepatch, build_patch.evsgrid, build_patch.datepatch)]
            self.assertEqual(build_patch._build(args), 0)
            for guard in guards:
                guard.assert_not_called()


class BinaryTests(unittest.TestCase):
    def test_verifier_checks_live_copy_not_abandoned_translation(self):
        header = bytearray(64); header[:4] = b'\x38\x35\0\0'
        struct.pack_into('<H', header, 4, 64); header[24:32] = b'TEST000\0'
        raw = bytes(header) + b'\x10' + rebuild.encode('あいうえおかきくけこ') + b'\x80\xff'
        before = bytearray(3 * 2048); before[4096:4096 + len(raw)] = raw
        block = scenes.Block('TEST000', 4096, script.messages(before, 4096)); block.sha1 = '12345678'
        english = rebuild.rebuild(raw, {64: 'Hello'}, english=True)
        after = before + bytearray(2048)
        after[4096:4096 + len(raw)] = english + bytes(len(raw) - len(english))
        after[6144:6144 + len(raw)] = raw
        old = groups.Group(1, 1, [1, 2]); new = groups.Group(1, 1, [2, 3])
        with patch.object(groups, 'find_groups', side_effect=[{1: old}, {1: new}]), \
             patch.object(verify_output.overlays, 'find', return_value=[]):
            result = verify_output.verify_dialogue(before, after, [block], b'', b'',
                                                   {block.key: {'64': 'Hello'}}, {})
        self.assertTrue(result['errors'])
        self.assertEqual(result['verified_strings'], 0)

    def test_packed_translation_survives_group_move(self):
        header = bytearray(64); header[:4] = b'\x38\x35\0\0'
        struct.pack_into('<H', header, 4, 64); header[24:32] = b'TEST000\0'
        raw = bytes(header) + b'\x10' + rebuild.encode('あいうえおかきくけこ') + b'\x80\xff'
        data = bytearray(3 * 2048); data[4096:4096 + len(raw)] = raw
        data[4096 + len(raw):4096 + len(raw) + 4] = b'tail'
        block = scenes.Block('TEST000', 4096, script.messages(data, 4096)); block.sha1 = '12345678'
        group = groups.Group(1, 1, [1, 2]); group.cap = 1
        builder = build_patch.Builder(data, {1: group})
        builder.build([block], {block.key: {'64': 'Hello world'}}, {})
        builder.force_move.add(1); builder.rebuild_group(group, {})
        self.assertEqual(builder.errors, [])
        self.assertIn(rebuild.encode_en('Hello world'), builder.append[0])
        self.assertEqual(builder.append[0][len(raw):len(raw) + 4], b'tail')

    def test_sector_corruption_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / 'a.bin'; dst = Path(tmp) / 'b.bin'
            src.write_bytes(cdimage.make_form1(0, bytes(2048)))
            dst.write_bytes(cdimage.make_form1(0, b'x' + bytes(2047)))
            self.assertEqual(verify_output.verify_sectors(src, dst)['errors'], [])
            bad = bytearray(dst.read_bytes()); bad[100] ^= 1; dst.write_bytes(bad)
            self.assertTrue(verify_output.verify_sectors(src, dst)['errors'])

    def test_picture_compression_roundtrips_and_caches(self):
        raw = bytes(range(256)) * 2
        for kind in ('lz1', 'lz2'):
            with self.subTest(kind=kind):
                pictures._compress_picture.cache_clear()
                a = pictures._compress_picture(kind, raw)
                self.assertEqual(a, pictures._compress_picture(kind, raw))
                self.assertEqual(pictures._compress_picture.cache_info().hits, 1)


if __name__ == '__main__':
    unittest.main()
