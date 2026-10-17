# Publish this source folder

The working branch is `improvements`. All seven original commits are retained. The remote `upstream` points to jonny-anime's project; `origin` points to [osyahbana's fork](https://github.com/osyahbana/tokimeki-memorial-2-english-patch).

For future updates, open a terminal in this source folder and review/test the changes:

```sh
git status --short
git diff --stat
python -m unittest discover -s tests -v
python -X utf8 tools/check_translations.py translations
```

Commit under your normal Git identity and push to the fork:

```sh
git add .
git commit -m "Describe your changes"
git push -u origin improvements
```

Keep `ATTRIBUTION.md`, `README.upstream.md`, existing credits and original history. The license status is recorded in `ATTRIBUTION.md`; no new license is assigned to inherited content.

Keep ROMs, BIOS, extracted executables, memory cards, save states and credentials outside the repository. `.gitignore` covers common formats. CI uses synthetic data and needs no game files or API keys. Never upload complete patched game images.
