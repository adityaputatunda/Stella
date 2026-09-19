# Stella — an accent-guessing game

A browser game built on the [Speech Accent Archive](https://accent.gmu.edu/).
Every speaker in the archive reads the same elicitation paragraph, which begins
"Please call Stella" — so the text is held constant and the only thing varying
between clips is the accent. You hear one, you name their first language, then
you guess where they were born.

Ear training dressed up as GeoGuessr.

## Running it

Two files:

```
index.html      the game
speakers.js     harvested speaker metadata — window.SPEAKERS
```

Open `index.html` in a browser, or serve the directory over HTTP. No build, no
dependencies. `speakers.js` is loaded with a `<script>` tag rather than
`fetch()`, deliberately — script tags aren't subject to CORS, so the game still
works from `file://`.

Don't paste it into a web app or chat artifact. Those apply a Content Security
Policy that blocks media from external domains, and the clips stream from
`accent.gmu.edu` at play time.

## Where everything comes from

Audio streams live, one clip per round:

```
https://accent.gmu.edu/audio/<slug>.mp3
```

where `<slug>` is a language stem plus a speaker number — `hindi1`, `french5`,
`russian12`. The matching archive page, linked from every reveal, is:

```
https://accent.gmu.edu/samples/<slug>/
```

Speaker biographies and IPA transcriptions come from those pages, but they are
read **once, offline, by `harvest.py`** — never at play time. See below.

Two consequences:

- **You need to be online** for audio. Metadata works offline.
- **You're a guest on someone's bandwidth.** `preload="none"` is set and exactly
  one clip loads per round. Don't change that to prefetch.

### If audio stops working

The archive was rebuilt in 2026; the old `/soundtracks/` path and the `.php`
browse pages are gone. If the path moves again: open any sample page, DevTools →
Network → filter Media → press play → copy the request URL. Update `AUDIO_URL`
at the top of the script block.

## Harvesting the metadata

`accent.gmu.edu` does not send `Access-Control-Allow-Origin`. This is confirmed,
not hypothetical — a browser cannot read the sample pages from any origin, local
file or hosted site alike. Media elements are exempt from CORS, which is the only
reason audio works at all. So the metadata has to be pulled out of band.

```bash
python3 harvest.py browse.html      # slug list from a saved index page
python3 harvest.py                  # fallback: probe stem1, stem2, ... per stem
```

Give it a saved copy of one of the archive's browse pages and it reads every
`/samples/<stem><n>/` link out of the markup. That's the authoritative slug
list — real speaker counts, no guessing, no runtime 404s. Without one it probes
upward per stem until three consecutive misses, which works but is slower and
hammers the server for nothing.

It writes `speakers.json` (data) and `speakers.js` (the same thing as a global),
one second between requests, resumable — re-running skips what's already held.
It ends by printing verified per-stem counts; paste those into `SPEC`'s `n`
column and delete any row that came back zero.

Set `CONTACT` at the top to a real address before running it. It costs nothing
and it's the difference between a polite client and an anonymous one.

## The two questions

**Stage one — language.** Up to six buttons, language names only. Graded by
genealogy rather than right/wrong, so a near miss is worth something:

| Outcome                                           | Points |
| ------------------------------------------------- | ------ |
| Exact language                                     | 100    |
| Same branch (Telugu for Tamil)                     | 60     |
| Same family, different branch (Hindi for Persian)  | 30     |
| Different family entirely                          | 0      |

Answering without replaying multiplies a scoring guess by 1.25, so stage one
caps at 125.

Distractors are seeded deliberately: up to two options per round are
genealogical neighbours of the answer. Guessing Bengali when it's Marathi should
be cheap. Guessing Bengali when it's Korean shouldn't be.

**Stage two — birthplace.** This exists because the archive keys on *native
language*, and native language is a lousy proxy for accent. A French speaker
born in Douala and one born in Lyon share a label and almost nothing else about
their English. So after you name the language, the game reveals it and asks
where the speaker was actually born, four options:

| Outcome                          | Points |
| -------------------------------- | ------ |
| Exact country                     | 50     |
| Right continent, wrong country    | 20     |
| Neither                           | 0      |

175 a round, 1750 over a run. Grades are a percentage of what was actually
available, so a partial `speakers.js` still grades fairly.

Distractors come from `HOMELANDS`, a per-language list of countries where that
language is plausibly a first language, padded from a global fallback. The true
country is always inserted, even if it isn't in the list — which is how Cameroon
shows up under French.

The reveal then shows the full biography: birthplace, age and sex, other
languages, age of English onset, how they learned it, where they've lived and
for how long. That last group is the interesting part. Someone who started
English at 11 in a classroom sounds nothing like a childhood bilingual, and the
data tells you which you just heard. The IPA transcription is behind a
disclosure.

## Regions

The region filter looks like IDEA's continent menu but means something
different. IDEA indexes by where the speaker is from; this game's region chips
map each *language* to where it's natively spoken, and a language can sit in more
than one — Arabic in Middle East and Africa, Spanish in Europe and the Americas.

That behaves as you'd expect everywhere except **Americas**, which is thin,
because the languages spoken there are mostly shared with Europe and the
archive's indigenous coverage is sparse.

Note the chips filter by *language* region while stage two asks about *speaker*
birthplace, so the two can disagree — a French speaker from Cameroon appears
under both Europe and Africa. That's a feature: it's exactly the gap the second
question exists to expose.

## Hosting it

It's a static page; GitHub Pages serves it as-is.

```bash
git init && git add -A && git commit -m "Stella"
gh repo create stella --public --source=. --push
gh api -X POST repos/:owner/stella/pages \
  -f 'source[branch]=main' -f 'source[path]=/'
```

Pages serves over HTTPS and the archive is HTTPS, so there's no mixed-content
block. Pages' soft limits — 1 GB repo, 100 GB/month bandwidth — are far above
anything this will use. Its terms bar sites that are primarily commercial, which
the archive's licence bars anyway, so the two agree.

**What changes when it's public** is only the audio. Every visitor's clip
request goes to `accent.gmu.edu` carrying `Referer: <you>.github.io`. One local
user is invisible; a link that circulates is not, and it's their bandwidth being
spent. For a toy nobody links to, hotlinking is fine. If it gets traffic, mirror.

**If you mirror**, take the files from the archive's own bulk channel rather than
walking `/audio/`: `accent.gmu.edu/download/` links two OSF repositories, one
with MP3s for every entry plus plain-text transcriptions, one with lossless
FLAC. Pull the archive, copy across only the slugs in `speakers.json`, commit
them plainly — **not** Git LFS, which makes Pages serve the pointer file instead
of the audio — and point `AUDIO_URL` at a relative path. Keep the footer
attribution, and add a `NOTICE` in the audio directory naming the source and
licence.

## Licence and attribution

Archive contents — audio, transcriptions and speaker data alike — are licensed
[CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/), and the
archive publishes them for bulk download itself. Redistributing the clips is
therefore permitted outright, not merely tolerated. Three conditions actually
bind:

- **Attribution** — the citation and licence link sit in the footer. Leave them
  there, and repeat them alongside any bundled files.
- **NonCommercial** — permanently. No ads, no sponsorship, no tip jar, no
  bundling it into anything sold. This constrains the project's whole future,
  not just today's deployment.
- **ShareAlike** — unmodified clips played from a separate host make the game a
  *collection*, so your code stays yours under whatever licence you pick.
  `speakers.json` and `speakers.js` are different: they reformat the archive's
  data, which makes them an adaptation, and they carry BY-NC-SA. Say so in the
  file header — `harvest.py` writes that header for you.

A sane repo layout is MIT (or similar) on `index.html` and `harvest.py`, a
`LICENSE-ARCHIVE` naming BY-NC-SA, and a line in this README pointing each at
the other.

Cite as: Weinberger, Steven H. (2015). *Speech Accent Archive*. George Mason
University. Retrieved from https://accent.gmu.edu

One thing the licence doesn't settle: copyright terms and site conduct are
separate layers. Check `robots.txt` before running any harvester, keep the delay
in, and if you end up mirroring at scale, an email to the archive costs one
minute and removes the question entirely.

### Why not IDEA

The [International Dialects of English Archive](https://www.dialectsarchive.com/)
is the better corpus for prosody — roughly four minutes per speaker including
unscripted speech, versus one read paragraph — and it indexes by region, which
would solve the native-language problem outright. But it's all-rights-reserved.
Its terms permit streaming a recording from the site during a lecture or
workshop; embedding its files in a third-party app is distribution, needing
written consent and a fee. For anything you'd share, email
`director@dialectsarchive.com` first. For a private tool only you open, you're
within their "free for personal research" allowance.

## Extending it

`SPEC`, one row per language:

```js
["french", "French", ["Indo-European","Romance"], 5, ["Europe","Africa"]],
//  stem     label     genealogy path                n   regions
```

- **stem** — must match archive filenames; resolves as `<stem><1..n>.mp3`.
- **genealogy path** — root-to-branch, ordered. Scoring compares shared prefix
  length, so a third level gives finer partial credit within that family.
- **n** — speakers. Only a fallback now: the pool is built from `speakers.js`
  where that covers a stem, and `n` is used only for stems it doesn't. Take the
  real numbers from `harvest.py`'s closing report.
- **regions** — any subset of `REGIONS`.

`HOMELANDS[stem]` controls stage-two distractors. `CONTINENT` drives the
partial-credit check; unlisted countries score 0 for near misses, so add any you
see turn up.

Other knobs: `ROUND_TOTAL`, `MAX_OPTIONS`, `PLACE_OPTIONS`,
`FIRST_LISTEN_BONUS`, `PLACE_EXACT`, `PLACE_NEAR`.

To add a language the archive has but the game doesn't: add its stem to `STEMS`
in `harvest.py`, re-run (it resumes, so only the new stem is fetched), then add
the `SPEC` row.

## Keyboard

| Key      | Action                              |
| -------- | ----------------------------------- |
| `1`–`6`  | Answer — routes to whichever stage is live |
| `Space`  | Play / pause                        |
| `Enter`  | Next clip (once the round resolves) |

Clicking the tick track scrubs.

## Known limitations

- No persistence — scores reset on reload, deliberately, to keep it storage-free.
- `plays` counts play events, so pausing and resuming mid-clip forfeits the
  first-listen bonus.
- `speakers.js` is a snapshot. The archive grows; re-run `harvest.py` when you
  want the new entries. Nothing breaks if you don't.
- Stage two is only as good as the archive's `birth place` field, which is
  free text. Country extraction takes the last comma-separated part, so an
  unpunctuated entry lands wrong. Spot-check the JSON.
- The metadata parser slices flattened page text between known field labels. If
  the archive's markup changes again, `parse()` in `harvest.py` is the thing to
  fix — and the game no longer has a parser of its own to keep in sync.
- Six options is easier than free recall. If it gets too easy, drop
  `MAX_OPTIONS` to 4 and pick a single region.
