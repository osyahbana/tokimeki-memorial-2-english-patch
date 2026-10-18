# Tokimeki Memorial 2 — native PC port development

This `native-port` branch contains an early C#/.NET engine reimplementation.
**It is not a playable full-game port yet.** See [native engine instructions](native/README.md)
for the executable, importer, tests, evidence and remaining work.

The [static recompilation assessment](native/recomp/README.md) now recommends
PSXRecomp as the next gameplay experiment. Disc 1 code generation and Windows
object compilation passed; runtime boot, overlays and automatic disc changes
remain unverified. The existing C# client remains useful for research.

The playable English patch remains on the fork's `improvements` branch. Its source
and documentation are retained below because the native importer reuses its
format parsers and translations.

## English patch — improved edition

A compatibility and reliability fork of [jonny-anime's English patch](https://github.com/jonny-anime/tokimeki-memorial-2-english-patch) for the five-disc Japanese PlayStation game.

The original translation, font, graphics and tools come from that project. See [attribution](ATTRIBUTION.md), the archived [upstream README](README.upstream.md), and the [review of problems and fixes](docs/patch-review.md).

## Improvements

- Original Japan / v1.0 layouts and 709 additional scene variants, with byte guards.
- Packed translations survive relocation of their scene groups.
- Missing dialogue or literal speaker labels fail the build by default; partial builds require explicit opt-in.
- Failed builds preserve previous outputs. Every requested disc is staged and verified before publication.
- Live dialogue bytes and changed-sector EDC/ECC are checked automatically; each disc receives a JSON report.
- Corrected CUE handling, Windows console output, `--no-exe`, six overflowing lines and one menu label.
- Repeated texture compression is cached, with decompression round-trip checks.

## Supported images

Supply your own **single-track BIN/CUE, MODE2/2352** images, serials **SLPM-86355 through SLPM-86359**.

| Release | Status |
|---|---|
| Original Japan / v1.0, all five discs | Locally built and verified; source hashes in [supported-images.json](docs/supported-images.json) |
| Japan Rev 1 | Inherited support retained; no new five-disc Rev 1 integration run |
| Other revisions, CHD/PBP/ISO, multi-track layouts | Not supported by this build flow |

Do not apply upstream Rev 1 xdelta files to original-release discs. This source patcher selects guarded layouts and translations from the supplied images.

## Build and play

Install Python 3.10 or newer and run from this folder:

```sh
python -m pip install -r requirements.txt
python patch.py "path/to/original discs" -o "path/to/English discs"
```

On Windows, `py` can replace `python`; on other systems you may need `python3`.

Keep the generated BIN, CUE, report and M3U files together. Open **Tokimeki Memorial 2 English.m3u** in DuckStation. Use its Change Disc menu when the game requests another disc. The original images are not modified.

| Option | Behavior |
|---|---|
| `-o FOLDER` | Output location; defaults to a separate sibling folder |
| `-f` | Replace previous outputs after validation succeeds |
| `--tl DIR` | Translation directory; repeat for later overrides |
| `--allow-partial` | Permit missing dialogue/speaker labels and record incomplete coverage in reports |

Allow room for new images alongside existing outputs. Every requested disc must pass before publication. Replacement is atomic per file, not across the whole set during a storage failure or power loss.

**Start with a fresh boot.** Old Japanese save states restore old code/data. Memory-card saves are separate, but compatibility at every point in the game is not established.

## Verify and contribute

```sh
python tools/verify_output.py "original.bin" "English.bin" --json verification.json
python -X utf8 tools/check_translations.py translations
python -m unittest discover -s tests -v
```

The verifier follows live container pointers and checks translated bytes and changed sectors. It does not prove translation quality or complete gameplay compatibility. The unit tests use synthetic data and need no ROMs.

Edit only `en` values in `translations/`, keeping line counts and control codes. Original-release mappings are in `translations/v10-mapped-scenes.json`; the library retains Rev 1 variants too. Report visual problems with a screenshot, disc, game date, scene and reproduction steps. See [translation tools](docs/translating.md) and [internals](docs/game-internals.md); inherited addresses may describe Rev 1.

`tools/build_patch.py --no-exe` is a developer diagnostic: it skips glyph, name-entry, EVS and date code patches. Such output is not a playable English build.

## Remaining limitations

The inherited script is machine-translated and has not had a complete human edit. Wording, tone and pronouns may need correction. English still uses fixed-width letter pairs.

Sports-day instruction boards, childhood date graphics, some still pictures and movie text remain Japanese. Voices, lyrics, logo and staff roll are unchanged. Two conditional-layout warnings remain.

Testing includes full image/translation checks and a Disc 1 boot/title/intro smoke test. English menus and normal gameplay were not visually confirmed in that runtime session. No full playthrough, all-disc progression, real-hardware test or complete save-compatibility claim is made. See [validation](docs/validation.md) and the [review](docs/patch-review.md).

## Credits and publication

This is an unofficial fan project, not affiliated with or endorsed by Konami. The game, names, characters, Japanese text, audio and artwork belong to their respective rights holders.

[ATTRIBUTION.md](ATTRIBUTION.md) preserves upstream and prior-work credit. Upstream supplied no license file at the base revision; this fork does not assign a new license to inherited material.

This source repository contains **no ROMs, BIOS files or saves**. See [publishing instructions](docs/publishing.md) for pushing this folder to your own GitHub repository.
