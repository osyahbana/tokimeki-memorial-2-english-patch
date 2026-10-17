# Tokimeki Memorial 2: PS1 English patch

<img src="translated_screenshots/Screenshot%202026-10-14%20215828.png" width="800" alt="Hikari in the classroom: &quot;Ehehe, I'm so glad we're in the same class!&quot;">

Patches the Japanese PlayStation version of *Tokimeki Memorial 2* (Konami,
1999, five discs) into English. The game's own engine draws the English:
the patch adds a narrow English font, Latin name entry and translated menus
and pictures, and rewrites every scene's text on the disc.

The whole script is translated, but by machine: Gemini
4 Argon translated it, scene by scene, with notes on each character, and
Claude Opus 5.5 rewrote the lines Argon couldn't make fit. Only part of
it has been read in the game. Expect awkward lines, wrong speakers or
genders now and then, and a few scenes that look off. Corrections are very
welcome: see [Helping improve the translation](#helping-improve-the-translation).

The tools were written with Claude Opus 5.5.

## Disclaimer

This is an unofficial fan project, not affiliated with, endorsed by or
sponsored by Konami. *Tokimeki Memorial 2* and all related names,
characters and artwork are trademarks and copyrights of Konami Digital
Entertainment.

This repository contains no disc images, BIOS files or executables: you
need your own copy of the game. The translation files carry the Japanese
text next to the English, for translators to work from. The patcher only
writes a new copy of your disc images and never changes the originals.
Don't distribute patched images.

## Which discs you need

*Tokimeki Memorial 2* for PlayStation, Japan, **Rev 1**, serials
**SLPM-86355** to **SLPM-86359** (Discs 1 to 5), as BIN/CUE images (one
`.bin` per disc, MODE2/2352). The usual names are:

```text
Tokimeki Memorial 2 (Japan) (Disc 1) (Rev 1).cue
Tokimeki Memorial 2 (Japan) (Disc 1) (Rev 1).bin
...
Tokimeki Memorial 2 (Japan) (Disc 5) (Rev 1).cue
Tokimeki Memorial 2 (Japan) (Disc 5) (Rev 1).bin
```

Other releases (the first pressing, reprints) and other formats (`.chd`, `.pbp`, `.iso`) haven't been tried. Every scene is
identified by a checksum of its original bytes, so on a different version
the patcher reports what it couldn't patch instead of writing garbage.

## Quick install: xdelta patches

The easiest way, with no Python and no terminal.

1. **Download the patches** from the
   [Releases](https://github.com/jonny-anime/tokimeki-memorial-2-english-patch/releases)
   page: one `.xdelta` file per disc, plus `checksums.txt`.
2. **Check your discs.** Each patch fits one exact disc image: the CRC32 of
   your original `.bin` must match the "original" line for that disc in
   `checksums.txt` (on Windows, 7-Zip shows it: right-click the file →
   *7-Zip → CRC SHA → CRC-32*). If a disc doesn't match, use the Python
   patcher below instead: it works by what's inside the disc, not by
   checksum.
3. **Apply each patch to its disc's `.bin`** with any xdelta tool:
   - [Delta Patcher](https://github.com/marco-calautti/DeltaPatcher) on
     Windows, macOS or Linux;
   - or xdelta3 on the command line:
     `xdelta3 -d -s "original.bin" "patch.xdelta" "English.bin"`.
4. **Keep the file name.** Put each patched `.bin` in a new folder under
   **the same name as the original**, and copy the original `.cue` next to
   it: the `.cue` then works as it is. To play with disc switching, make a
   text file `Tokimeki Memorial 2.m3u` in that folder listing the five
   `.cue` file names, one per line, and open it in your emulator.

A patched disc should have the CRC32 of the "English" line in
`checksums.txt`. If you apply a patch to the wrong image, xdelta tools
stop with a checksum error rather than writing a broken disc.

## How to patch the game with Python

For translators, for testing changes to `translations/`, or if your discs
don't match the checksums.


1. **Install Python 3.10 or newer.**
   - Windows: from [python.org](https://www.python.org/downloads/); in the
     installer, tick **"Add python.exe to PATH"**.
   - macOS: from [python.org](https://www.python.org/downloads/).
   - Linux: it's almost certainly installed already (`python3 --version`).
2. **Download this project:** on GitHub, **Code → Download ZIP**, and unzip
   it anywhere (or `git clone` it).
3. **Open a terminal in the project folder** (the one with this README).
   - Windows: open the folder in Explorer, click the address bar, type
     `cmd` and press Enter.
   - macOS: right-click the folder in Finder → **New Terminal at Folder**.
   - Linux: right-click in the folder → **Open in Terminal**.
4. **Install the packages the patcher uses** (once):

   ```bash
   py -m pip install -r requirements.txt
   ```

   On macOS and Linux, use `python3` wherever this README says `py`.
5. **Run the patcher on the folder that holds your discs:**

   ```bash
   py patch.py "path/to/your/Tokimeki Memorial 2 folder"
   ```

   Tip: type `py patch.py ` (with a space at the end), drag the folder onto
   the terminal window to paste its path, and press Enter. You can also
   give the `.cue` files themselves, e.g. to patch only one disc.
6. **Wait for `Done`.** The English discs go
   into a new folder next to your disc files, named after the game with
   ` [English]` added:

   ```text
   Tokimeki Memorial 2 (Japan) (Rev 1) [English]/
     Tokimeki Memorial 2 (Japan) (Disc 1) (Rev 1).cue / .bin
     ...
     Tokimeki Memorial 2 (Japan) (Rev 1).m3u
   ```

7. **Play.** Open the `.m3u` file in your emulator to play all five discs
   with disc switching (or open one disc's `.cue`). All testing was done in
   [DuckStation](https://www.duckstation.org/); real hardware hasn't been
   tried.

| Option | What it does |
|---|---|
| `-o FOLDER` | Write the English discs to `FOLDER` |
| `-f` | Replace English discs that are already there (re-patching after an update) |
| `--tl DIR` | Use other translation files than `translations/`; repeatable |

**Your saves:** the patch doesn't change the memory-card save format, so
saves from the Japanese game should carry over. A save *state* made with a Japanese disc brings the Japanese disc
back when loaded: load it, switch to the English disc
(*System → Change Disc*), and make a new state.

## What's still in Japanese

**On purpose**

- The title logo, the copyright line and the staff roll.
- Song lyrics and voice acting.
- Lines that are only punctuation (a pause like `……`).

**Not done**

- The sports-day minigame instruction boards.
- The date box of the childhood prologue on Disc 1.
- Full-screen still pictures and movies.
- Some pictures with Japanese text that haven't been found on the disc
  yet. If you see one, please report it with a screenshot.

**Known issues**

- English is drawn at a fixed width (two letters per Japanese character
  cell), so spacing is even rather than proportional.
- Some lines are a little too long for the box and wrap mid-word (the
  checker lists them).

## Helping improve the translation

The whole game is translated, but by machine, so much of it can read
better. Corrections, better wording, consistent character voices and bug
reports from playing are all welcome.

### Reporting a problem

Open an issue with a screenshot, what was happening (the date in the game,
which girl, which disc) and, if you can, what the line should say. Text
that runs off the box, a wrong speaker or gender, or a line that's still
Japanese are all worth reporting. If the game hangs or behaves differently
from the Japanese version, say so.

### Where the English lives

Everything is in [`translations/`](translations/), sorted by character and
disc:

| File | What's in it |
|---|---|
| `hikari/disc2.json` … `kasumi/disc5.json` | scenes where that girl talks most, by the first disc they're on (`miho/` includes her twin Maho) |
| `others/disc2.json` … | scenes no single girl leads (the player and his friends, teachers, narration) |
| `childhood.json` | the childhood prologue (Disc 1) |
| `phone_calls.json` | phone calls |
| `endings.json` | graduation-day endings |
| `misc.json` | dates, exams and other system scenes |
| `menus.json` | menus, system text, names and place names |
| `speaker_names.json` | the speaker labels (`"陽ノ下": "Hikari"`) |

A scene file holds scenes; a scene holds messages, and **one message is
one text box**:

```json
{"key": "G014000-b6f2d9d6", "location": "Festival Fair", "kind": "file", "room": 7532, "found": {"2": [207328]},
 "messages": [
  {"at": [484, 504, 512], "speaker": "Miyuki", "speaker_ja": "寿",
   "ja": "そうなんだー……。\n……。\n美幸、用を思い出したから帰るね。",
   "en": "Oh, I see~…\n…\nMiyuki remembered an errand, so bye!"}]}
```

**Only change `en`.** The other fields tell the patcher where the text is.
`\n` separates the lines of the box: **the English needs exactly as many
lines as the Japanese** (one per number in `at`). To find a line, search
the `translations/` folder for the English you saw on screen.

In `menus.json` each entry is one Japanese string, replaced everywhere it
appears; its English must fit in `max_bytes` (1 per letter, rounded up to
an even number, 2 per other character).

### Steps for a change

1. **Edit `en`** in the file.
2. **Check it:**

   ```bash
   py tools/check_translations.py translations/miyuki/disc2.json
   ```

   It lists problems by scene key and `at` number (`G014000-b6f2d9d6/484`).
   Fix every `ERROR`; `WARN` lines are worth fixing when it's easy.
   Without a file name it checks everything. It doesn't need your discs.
3. **Build and look at it** in an emulator, a little past the changed
   screen: `py patch.py "path/to/your/discs" -f` (or just the disc you
   changed: give its `.cue`). A clean check doesn't prove it looks right.
4. **Send a pull request** saying what you changed and what you checked on
   screen. Screenshots go in the pull request, not in the repo.

A scene that is on several discs is stored once, so one fix changes it on
all of them.

### Rules for the English

The game was never built for English; the checker enforces most of this.

- **Keep the line structure:** same number of lines as the Japanese, each
  line's `{codes}` on the same line. Moving words between the lines of a
  box is fine.
- **About 40 letters per row** (20 cells, two letters each). A name code
  counts as about 6 letters, `{char:NN}` as 10. Longer rows wrap, often
  mid-word. A box shows 4 rows; a message with more lines scrolls.
- **Space on the disc is limited.** `room` says how many bytes the
  scene's English may add to the Japanese, all lines together (1 letter =
  1 byte; a Japanese character is 2). Scenes with `"kind": "packed"` can't
  grow at all: there the English must not be longer than the Japanese. If
  something doesn't fit, shorten it.
- **Allowed characters:** `A–Z a–z 0–9`, space and `. , ! ? ' " - ~ …`.
  `…` is one character (not `...`); straight quotes only; no accents, no
  `: ; ( ) / &`. `♪` and `♥` can stay where the Japanese has them. Anything
  else is drawn as a wide Japanese-size character.
- **Thoughts:** the Japanese ends a thought with `）`; end that English line
  with `)`. Don't type the opening `(`, the speaker name or 「: the game
  draws them.
- **`{nobreak}`** at the end of a line joins it to the next line on the
  same row; keep it there.
- **Codes** in curly braces are replaced by the game; keep each one, on
  its line:

  | Code | What it inserts |
  |---|---|
  | `{name1}` | the player's given name |
  | `{name2}` | the player's nickname |
  | `{name3}` | another of the player's names (rare) |
  | `{you:1N}` | how girl N addresses the player: his name, nickname or "you". Use it as a form of address ("Thanks, {you:12}!"), not as the subject or object of a verb |
  | `{char:2N}` | the name of character N, as the game chooses: surname, given name or nickname |
  | `{numX:YY}` | a number: a date, a count, a score |
  | `{cXX}` | a control code: leave it where it is |

  N: 1 Kasumi, 2 Hikari, 3 Kotoko, 4 Miyuki, 5 Akane, 6 Miho, 7 Homura,
  8 Kaori, 9 Kaedeko, A Mei, B Miho, C Sumire.
- **Names:** given name first, no honorifics (-san, -chan, -kun), teachers
  as Ms./Mr. + surname. Family words stay family words ("big brother").
- **Keep each character's voice:** Miyuki and Mei speak of themselves in
  the third person ("Miyuki's fine!", "Mei is displeased."), Kotoko is
  crisp and formal, Homura blunt, Mei imperious. The notes in
  [`mt/characters.json`](mt/characters.json) and the brief in
  [`mt/prompt.md`](mt/prompt.md) describe every character, the names and
  the recurring terms.

Pictures with text (titles, buttons, stat names) are PNGs in
[`pictures/`](pictures/); see [docs/translating.md](docs/translating.md#pictures).

## For developers

| | |
|---|---|
| [docs/translating.md](docs/translating.md) | The translation tools in detail: checks, menus, pictures, machine translation |
| [docs/game-internals.md](docs/game-internals.md) | Discs, compression, text encoding, script bytecode, containers, the code patches, with addresses |
| [docs/README.md](docs/README.md) | What each tool in `tools/` does |

| Path | What it is |
|---|---|
| `patch.py` | Patches every disc in a folder (calls `tools/build_patch.py` per disc) |
| `tools/make_xdelta.py` | Makes the xdelta patches and `checksums.txt` for a release |
| `translations/` | The translation (Japanese and English) |
| `pictures/` | Translated pictures and their manifest |
| `tools/` | Disc and text tools, the builder, the checker, machine translation (`mt.py`) |
| `mt/` | The machine-translation brief, character notes and model settings |

How it works, in brief:

- Text is Shift-JIS with each byte's nibbles swapped, inside script blocks
  of the game's bytecode. Every block is found on the disc, decoded,
  re-encoded with the English and written back into its container: scenes
  may grow into the spare bytes of their sectors, and a main-game scene
  group that needs more room is moved to the end of the disc with its
  offset table rewritten.
- The game can't draw ASCII. A small patch to its text renderer draws
  English as letter pairs: each 2-byte code in a range Japanese never uses
  becomes a cell with two narrow letters.
- Menus and names are rewritten in place in the executable and its code
  modules; the name tables are repacked so English names fit.

## Prior work

- [gothamor/tokimeki-memorial-english-patch](https://github.com/gothamor/tokimeki-memorial-english-patch):
  the English patch for the first *Tokimeki Memorial* (PS1), whose layout,
  methods and tooling this project follows.

## External Human Translation
For those who don't like AI assissted translations and are willing to wait, a separate team is working on a 100% human edited patch to Tokimeki Memorial 2. We're not affiliated with each others projects. So reach out to them for any questions regarding theirs.
[Link](https://bsky.app/profile/xct.bsky.social/post/3mxseyu3vis2r)
