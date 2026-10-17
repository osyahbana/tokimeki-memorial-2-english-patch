# Validation

Checked on 17 October 2026, against upstream base `401c95498289c8d6796ea13da05742c3126a6b0a`.

## Automated checks

- **17 synthetic regression tests pass** with Python 3.11 on Windows. They cover failed-output preservation, disc-set failure, filename/CUE handling, original-file aliases, translation coverage, `--no-exe`, relocated packed scenes, live-pointer verification, sector corruption and compression round trips.
- Translation checker: **0 errors, 2 warnings, 169,995 / 169,995 entries translated** across the mixed original/Rev 1 library. The two warnings are recorded in [translation-check.json](translation-check.json), not suppressed.
- A complete five-disc original-release build passed through the public `patch.py` command with automatic verification enabled. Disc 3 was then rebuilt after adding its missing `Year 3` marker label.
- Final outputs verify **140,559 translated string instances across 5,839 scene instances**, with no missing dialogue or literal speaker labels.
- All **12,341 changed/appended sectors** pass EDC/ECC checks. Source hashes remain identical to the pre-build hashes.
- The first complete rebuild matched the previously repaired images byte-for-byte. The subsequent Disc 3 label change is reflected in the final report/hash.
- The source folder retains the full seven-commit upstream history. It contains no game images, BIOS files, saves or local credentials.

Exact source/output hashes, counts, warnings and changed graphics are in [integration-results.json](integration-results.json). The reports omit local absolute paths. CI is configured for Windows and Linux; see the [GitHub Actions runs](https://github.com/osyahbana/tokimeki-memorial-2-english-patch/actions) for results on each published commit.

## Earlier code-level checks retained by this adaptation

The original-release glyph implementation was emulated over all 65,536 character codes for lookup and both renderers, including 5,184 English letter pairs. Load-delay and write-bound checks passed. Name entry was checked with 24,182 keystrokes; EVS conversion with 20,013 strings; the EVS grid preserved selection across 17 rows / 84 labels. String-table guards were checked against all five original images.

The ROM-dependent packed-scene regression can also be run locally:

```sh
python tools/verify_relocated_packed.py "Disc 2.bin" G336000-e2a95a3e translations
python tools/verify_relocated_packed.py "Disc 3.bin" G315000-8fc4b5a3 translations
```

## Runtime scope

An earlier build of these original-release adaptations booted Disc 1 in DuckStation 0.1-11752, reached the Konami/KCET screens, opening movie and title screen at normal speed. Testing used separate settings and memory cards. Automated game-button input was unreliable, so English menus and normal gameplay were not visually confirmed in that session.

The current changes are backed by image/code checks, not a new full gameplay test. No complete route playthrough, five-disc progression test, real-hardware test or universal save compatibility is claimed. A fresh Rev 1 integration run remains outstanding. See [patch-review.md](patch-review.md) for remaining content/layout issues.
