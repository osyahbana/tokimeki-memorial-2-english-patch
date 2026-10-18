# Attribution

The `native-port` branch adds a C#/.NET engine reconstruction, local content importer,
synthetic regression tests and machine-code-derived research maintained in
[osyahbana's fork](https://github.com/osyahbana/tokimeki-memorial-2-english-patch).
Its importer reuses the upstream format parsers and the translation data credited
below. Original game assets are imported locally and are not part of the native
engine distribution. Offline research used Capstone and Unicorn; neither is
embedded in the native application.

This is a derivative of **jonny-anime's Tokimeki Memorial 2 English patch**:

- Original project: <https://github.com/jonny-anime/tokimeki-memorial-2-english-patch>
- Base revision: [`401c95498289c8d6796ea13da05742c3126a6b0a`](https://github.com/jonny-anime/tokimeki-memorial-2-english-patch/commit/401c95498289c8d6796ea13da05742c3126a6b0a)
- Original patch architecture, translation corpus, English font, translated graphics, reverse-engineering documentation and tools come from that project, except where the change log identifies subsequent changes.
- The upstream Git history is retained. Existing upstream screenshots are examples from that project, not evidence of new runtime tests.
- The original README is retained in [README.upstream.md](README.upstream.md), including its translation provenance and credits. Its installation and compatibility instructions describe the upstream version; use this fork's root README for current instructions.

Upstream credits [gothamor/tokimeki-memorial-english-patch](https://github.com/gothamor/tokimeki-memorial-english-patch), the first game's PS1 English patch, for the layout, methods and tooling it follows. That credit is retained here.

*Tokimeki Memorial 2*, its characters, Japanese text, audio and artwork belong to Konami and their respective rights holders. This is an unofficial fan project and is not affiliated with or endorsed by Konami.

No license file was present in the upstream repository at the base revision. This fork does not assign a new license to upstream material or claim ownership of it. Attribution records provenance; it does not add a license grant. See the upstream project for licensing questions.

This source repository must not contain game images, extracted game executables, BIOS files, personal saves or credentials. Users supply their own disc images locally.
