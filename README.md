# Stella — an accent-guessing game

Built on the [Speech Accent Archive](https://accent.gmu.edu/). Every speaker in
the archive reads the same paragraph, which begins "Please call Stella", so the
text is constant and the only thing varying between clips is the accent. Name
the speaker's first language, then guess where they were born.

Ear training dressed up as GeoGuessr.

## Running it

```
index.html      the game
speakers.js     harvested speaker metadata — window.SPEAKERS
harvest.py      builds speakers.js / speakers.json
```

Open `index.html`, or serve the directory. No build, no dependencies. The game
looks for `speakers.js` in `./`, `metadata/`, `fetch/` and `data/`, so it doesn't
matter which of those it lives in. It's loaded with a `<script>` tag rather than
`fetch()` on purpose — script tags aren't subject to CORS, so it works from
`file://` too. Without it you get language-only rounds and a banner saying so.

Audio streams live from `https://accent.gmu.edu/audio/<slug>.mp3`, one clip per
round, `preload="none"`. If the path ever moves again: open a sample page,
DevTools → Network → Media → play → copy the URL, update `AUDIO_URL`.

## Harvesting the metadata

`accent.gmu.edu` sends no `Access-Control-Allow-Origin`, so no browser can read
the sample pages — the bios have to be pulled out of band.

```bash
python3 harvest.py browse.html    # slug list from a saved archive browse page
python3 harvest.py                # fallback: probe stem1, stem2, ... per stem
python3 harvest.py --clean        # re-trim existing data, no network
python3 harvest.py --out metadata # choose the output directory
```

Give it a saved browse page and it reads every `/samples/<stem><n>/` link out of
the markup — the authoritative slug list, real speaker counts, no runtime 404s.
One second between requests, resumable, and it prints per-stem counts at the end
for `SPEC`'s `n` column. Set `CONTACT` at the top to a real address first.

Run it from the repo root: it resolves its search paths against the working
directory, not the script location.

## Hosting

Static, so GitHub Pages serves it as-is.

```bash
git init && git add -A && git commit -m "Stella"
gh repo create stella --public --source=. --push
gh api -X POST repos/:owner/stella/pages -f 'source[branch]=main' -f 'source[path]=/'
```

`browse.html` is gitignored — it's 2.5 MB of GMU's markup and `speakers.json` is
the artifact worth keeping.

One thing changes when it's public: every visitor's clip request hits
`accent.gmu.edu` with your `github.io` referrer. Fine for a toy nobody links to.
If it gets traffic, mirror the audio from the archive's own OSF repositories
(linked from `accent.gmu.edu/download/`) rather than walking `/audio/`, commit it
plainly — **not** Git LFS, which makes Pages serve the pointer file — and point
`AUDIO_URL` at a relative path.

## Scoring

Full tables are in the game under "How scoring works". In short: stage one grades
by genealogy, so a near miss still pays; answering without replaying multiplies
by 1.25; and a difficulty multiplier of 1.0–1.8 scales both your score and the
round's ceiling based on how much accent the speaker has left — age of English
onset, how they learned it, how long they've lived in an English-speaking
country. An early onset only counts for much if immersion backed it up. Stage
two asks for the birthplace, because native language is a poor proxy for accent:
a French speaker born in Douala and one born in Lyon share a label and nothing
else.

To retune, edit `DIFF_TIERS` and the three `+=` lines in `difficulty()`.

## Extending it

`SPEC`, one row per language:

```js
["french", "French", ["Indo-European","Romance"], 5, ["Europe","Africa"]],
//  stem     label     genealogy path                n   regions
```

- **stem** — must match archive filenames; resolves as `<stem><1..n>.mp3`
- **genealogy path** — root-to-branch. Scoring compares shared prefix length, so
  a third level gives finer partial credit within a family
- **n** — fallback only; the pool comes from `speakers.js` wherever it covers a stem
- **regions** — any subset of `REGIONS`

`HOMELANDS[stem]` supplies stage-two distractors; `CONTINENT` drives the
partial-credit check, so add any country you see score 0 unfairly. Other knobs:
`ROUND_TOTAL`, `MAX_OPTIONS`, `PLACE_OPTIONS`, `FIRST_LISTEN_BONUS`,
`PLACE_EXACT`, `PLACE_NEAR`, `STREAK_RAIL`, `SEEK_STEP`.

To add a language: add its stem to `STEMS` in `harvest.py`, re-run (it resumes,
so only the new stem is fetched), then add the `SPEC` row.

## Keyboard

| Key       | Action                                      |
| --------- | ------------------------------------------- |
| `1`–`6`   | Answer — routes to whichever stage is live  |
| `Space`   | Play / pause                                |
| `←` / `→` | Seek 5s                                     |
| `Enter`   | Next clip, once the round resolves          |

## Licence

Archive contents are [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/),
and the archive publishes them for bulk download itself, so redistributing clips
is permitted outright. Three conditions bind:

- **Attribution** — citation and licence link are in the footer. Leave them, and
  repeat them alongside any bundled files.
- **NonCommercial** — permanently. No ads, no sponsorship, no tip jar.
- **ShareAlike** — `speakers.json` and `speakers.js` reformat the archive's data,
  which makes them adaptations, so they carry BY-NC-SA. `harvest.py` writes that
  header for you. Clips played unmodified from a separate host make the game a
  *collection*, so your own code stays under whatever licence you pick.

Cite as: Weinberger, Steven H. (2015). *Speech Accent Archive*. George Mason
University. https://accent.gmu.edu

Copyright terms and site conduct are separate layers — check `robots.txt` before
running any harvester and keep the delay in.

[IDEA](https://www.dialectsarchive.com/) is the better corpus for prosody, but
it's all-rights-reserved: embedding its files in an app needs written consent and
a fee. Fine for a private tool, not for anything you'd share.

## Known limitations

- `speakers.js` is a snapshot; re-run `harvest.py` for new entries. Nothing breaks if you don't.
- Stage two reads the archive's free-text `birth place` field and takes the last comma-separated part, so unpunctuated entries land wrong. Spot-check the JSON.
- Scores reset on reload, deliberately — no storage.
- If the archive's markup changes again, `parse()` in `harvest.py` is the thing to fix; the game no longer has a parser of its own to keep in sync.
