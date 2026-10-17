# Patch review and improvements

Reviewed upstream revision: `401c95498289c8d6796ea13da05742c3126a6b0a`.

| Problem | Impact | Resolution |
|---|---|---|
| Rev 1 code/data addresses were assumed | Original Japan discs failed guards or missed UI/script data | Added measured, guarded original-release layouts for glyphs, names, EVS, overlays, string tables, dates and group loading |
| Scene checksums differ between releases | 709 original-release variants did not match upstream translation keys | Added mappings using original offsets/Japanese text, with 132 differing lines reviewed |
| Unknown translation keys could be skipped silently | A build could report success while retaining Japanese dialogue | Missing dialogue is an error by default; partial work requires `--allow-partial` and is identified in reports |
| Packed edits did not update the data copied by later group relocation | Two translated original-release scenes were copied back into live groups in Japanese | Keep packed edits in the relocation source buffer; verify live locations and add regression tests |
| Failed builds wrote final filenames and playlists | Partial builds looked playable; `-f` could destroy a previous good output before failure | Stage each requested set, validate every disc, then publish files and publish the playlist last |
| `exe` flag was overwritten by executable bytes | `--no-exe` still ran name, EVS and date code patches | Separate the code-patch flag from executable data; regression-test all four entry points |
| Shifted string table ranges were combined | Two adjacent Japanese honorific fields were skipped | Resolve the actual revision's tables before excluding ranges from UI rewriting |
| CUE handling mixed copied references with flattened paths | Differently named or nested image references could break; unsupported track layouts were not explicit | Validate the supported single-track layout and generate normalized CUE references |
| Windows console encoding could fail on diagnostic text | A build aborted with `UnicodeEncodeError` | Use UTF-8 at CLI entry points and bound/escape mismatched table diagnostics |
| Explicit compressed graphic locations went through a heuristic scan | Overlapping false positives could hide the requested graphic | Decode explicit locations directly and still require the expected decompressed content hash |
| Several English lines and one menu label exceeded available space | Mid-word wrapping or failed insertion | Shortened six dialogue lines and the tea-ceremony club label while retaining controls/line structure |
| An original-release script marker had no English speaker label | The corpus checker counted one untranslated string | Translate `三年目` as `Year 3`; require coverage for literal speaker labels while allowing dynamic name codes |
| Identical textures were compressed repeatedly | Five-disc builds repeated expensive work | Cache compression by format and complete raw texture bytes; verify decompression round trips and each destination's size limit |
| Checks established parsing, not translated content at live locations | A structurally valid Japanese copy escaped detection | Follow relocated groups/overlays/bundles and compare all expected encoded dialogue/speaker strings; verify changed-sector EDC/ECC |

## Remaining issues

- The inherited script is machine-translated and has not had a complete human edit. Coverage does not establish correct tone, speaker, gender or meaning.
- The fixed-width English letter-pair renderer remains. A proportional font would require changes to layout and name-entry assumptions, not just different glyphs.
- Sports-day instruction boards, childhood date graphics, some still images and movie text remain Japanese. Voice acting, song lyrics, logo and staff roll are unchanged.
- Two conditional-layout warnings remain (`DEFAULT-4bc5b52c` and `G_BOMB-a1d9e649`). The checker joins potentially conditional text rows conservatively; this review does not claim those screens have been visually validated.
- Group capacity is still inferred conservatively from known loads by the same event module. It is not a general proof of free RAM.
- Publication uses atomic replacement per file, not one cross-file transaction. A storage failure or power loss during publication can still interrupt the set; rebuild after resolving it.
- Full route progression, real hardware and all existing saves have not been tested. Fresh boots are required to avoid restoring old code from Japanese save states.

## Test boundaries

The unit suite uses synthetic data and temporary files; it needs no ROMs. Local integration builds use original Japan discs with hashes recorded in [supported-images.json](supported-images.json). Rev 1 support is inherited and its original branches remain, but a fresh five-disc Rev 1 integration build was not available for this review.
