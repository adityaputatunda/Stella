#!/usr/bin/env python3
"""
harvest.py — one-time speaker-metadata pull from the Speech Accent Archive.

Writes two files with identical content:
    speakers.json   data, for anything that wants to read it
    speakers.js     window.SPEAKERS = {...}  — loadable from file:// via <script>

Audio is NOT touched. If you want the clips, take them from the archive's own
OSF repositories (see accent.gmu.edu/download/), not from this script.

Usage
-----
    python3 harvest.py browse.html          # slug list from a saved index page
    python3 harvest.py                      # fallback: probe stem1, stem2, ...
    python3 harvest.py --clean              # re-trim existing data, no network
    python3 harvest.py --out metadata ...   # write into ./metadata/

Without --out it writes beside an existing speakers.json if it finds one in
./, ./metadata, ./fetch or ./data, and otherwise in the current directory.
Resumable: re-running skips slugs already held.
"""

import json
import re
import sys
import time
import urllib.error
import urllib.request as u
from pathlib import Path

# ---------------------------------------------------------------- config

CONTACT = "you@example.com"          # put a real address here
DELAY = 1.0                          # seconds between requests
TIMEOUT = 20
PROBE_MISS_LIMIT = 3                 # consecutive 404s before giving up on a stem
PROBE_CEILING = 250
TAIL_CHARS = 60                      # how far past the last label to read

SEARCH_DIRS = [Path("."), Path("metadata"), Path("fetch"), Path("data")]

# column 0 of SPEC, in the same order
STEMS = [
    "english", "german", "dutch", "swedish", "norwegian", "danish", "icelandic",
    "afrikaans", "spanish", "french", "portuguese", "italian", "romanian",
    "catalan", "russian", "polish", "ukrainian", "bulgarian", "serbian", "czech",
    "greek", "albanian", "lithuanian", "latvian", "armenian", "hindi", "urdu",
    "bengali", "gujarati", "punjabi", "marathi", "nepali", "sinhalese", "farsi",
    "pashto", "kurdish", "tamil", "telugu", "malayalam", "kannada", "mandarin",
    "cantonese", "tibetan", "burmese", "arabic", "hebrew", "amharic", "somali",
    "hausa", "swahili", "zulu", "xhosa", "yoruba", "igbo", "wolof", "turkish",
    "azerbaijani", "kazakh", "uzbek", "finnish", "hungarian", "estonian",
    "tagalog", "indonesian", "malay", "vietnamese", "khmer", "thai", "lao",
    "japanese", "korean", "georgian", "mongolian", "hmong", "quechua", "basque",
]

FIELDS = [
    "birth place", "native language", "other language(s)", "age, sex",
    "age of english onset", "english learning method", "english residence",
    "length of english residence",
]

SAMPLE_URL = "https://accent.gmu.edu/samples/{}/"
HEADERS = {"User-Agent": f"stella-eartrainer/1.0 (+{CONTACT})"}

# Text that marks the end of the bio block. The last field has no following
# label to bound it, so without these it swallows page furniture.
STOP = re.compile(
    r"\s*(steven h\.? weinberger|george mason|speech accent archive|"
    r"creative commons|cc by|copyright|all rights|browse|search|"
    r"citation|about|contact|privacy)\b.*$",
    re.I,
)

SHAPES = {
    "length of english residence": re.compile(
        r"^\s*([\d.]+\s*(?:years?|months?|weeks?|days?))", re.I),
    "age of english onset": re.compile(r"^\s*([\d.]+)"),
    "age, sex": re.compile(r"^\s*(\d+\s*,\s*[a-z]+)", re.I),
}

# A real transcription carries IPA characters and no JSON punctuation. The
# archive embeds JSON-LD breadcrumbs in brackets, which used to slip through.
IPA_HINT = re.compile(r"[ɑɐɒæɛɜɪɨɔøœʊʉʌəɚɝʃʒθðŋɹɾʁʀʎɲɸβɣχħʕʔˈˌːʲʷ]")
IPA_JUNK = re.compile(r'["{}@]|https?:')

# ---------------------------------------------------------------- cleaning

def tidy(field, value):
    """Cut page furniture off a bio value and enforce the field's shape."""
    if not value:
        return None
    v = STOP.sub("", value).strip(" :\u2013-,\t")
    shape = SHAPES.get(field)
    if shape:
        m = shape.match(v)
        if m:
            return m.group(1).strip()
    v = re.split(r"\s{3,}", v)[0].strip()
    return v or None


def clean_record(rec):
    out = {}
    for k, v in rec.items():
        if k in ("ipa", "country"):
            continue
        t = tidy(k, v)
        if t:
            out[k] = t
    ipa = rec.get("ipa")
    if ipa and IPA_HINT.search(ipa) and not IPA_JUNK.search(ipa):
        out["ipa"] = STOP.sub("", ipa).strip()
    if out.get("birth place"):
        out["country"] = out["birth place"].split(",")[-1].strip().lower()
    return out


# ---------------------------------------------------------------- slugs

SLUG_RE = re.compile(r"/samples/([a-z]+)(\d+)/")


def slugs_from_index(path):
    html = Path(path).read_text("utf-8", errors="replace")
    stems = set(STEMS)
    found = {(s, int(n)) for s, n in SLUG_RE.findall(html) if s in stems}
    if not found:
        sys.exit(f"No /samples/ links matching SPEC stems found in {path}. "
                 "Wrong page, or the markup changed — check by hand.")
    return [f"{s}{n}" for s, n in sorted(found)]


def probe_slugs():
    out = []
    for stem in STEMS:
        misses = 0
        for i in range(1, PROBE_CEILING):
            if head_ok(f"{stem}{i}"):
                out.append(f"{stem}{i}")
                misses = 0
            else:
                misses += 1
                if misses >= PROBE_MISS_LIMIT:
                    break
            time.sleep(DELAY)
        print(f"  {stem}: {sum(s.startswith(stem) for s in out)}", flush=True)
    return out


def head_ok(slug):
    req = u.Request(SAMPLE_URL.format(slug), headers=HEADERS, method="HEAD")
    try:
        with u.urlopen(req, timeout=TIMEOUT) as r:
            return r.status == 200
    except Exception:
        return False


# ---------------------------------------------------------------- parse

def parse(html):
    """Flatten the page and slice the bio block between known field labels."""
    html = re.sub(r"(?is)<(script|style|noscript)\b.*?</\1>", " ", html)
    flat = re.sub(r"<[^>]+>", "   ", html)          # 3 spaces: block boundary
    flat = re.sub(r"[ \t]+", " ", flat)
    flat = re.sub(r"\n+", " ", flat).strip()
    low = flat.lower()

    hits = sorted((low.find(f), f) for f in FIELDS if low.find(f) >= 0)
    if not hits:
        return None

    raw = {}
    for n, (i, f) in enumerate(hits):
        start = i + len(f)
        end = hits[n + 1][0] if n + 1 < len(hits) else min(len(flat), start + TAIL_CHARS)
        raw[f] = flat[start:end]

    for m in re.finditer(r"\[([^\]]{40,})\]", flat):
        cand = re.sub(r"\s+", " ", m.group(1)).strip()
        if IPA_HINT.search(cand) and not IPA_JUNK.search(cand):
            raw["ipa"] = cand
            break

    rec = clean_record(raw)
    return rec if rec.get("birth place") else None


def fetch(slug):
    req = u.Request(SAMPLE_URL.format(slug), headers=HEADERS)
    try:
        with u.urlopen(req, timeout=TIMEOUT) as r:
            return parse(r.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as e:
        if e.code != 404:
            print(f"  ! {slug}: HTTP {e.code}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"  ! {slug}: {e}", file=sys.stderr)
        return None


# ---------------------------------------------------------------- paths

def resolve_dir(argv):
    if "--out" in argv:
        d = Path(argv[argv.index("--out") + 1])
        d.mkdir(parents=True, exist_ok=True)
        return d
    for d in SEARCH_DIRS:
        if (d / "speakers.json").exists():
            if d != Path("."):
                print(f"Found existing data in {d}/ — writing there.")
            return d
    return Path(".")


# ---------------------------------------------------------------- main

def main():
    argv = sys.argv[1:]
    out_dir = resolve_dir(argv)
    out_json = out_dir / "speakers.json"
    out_js = out_dir / "speakers.js"

    if "--clean" in argv:
        if not out_json.exists():
            looked = ", ".join(str(d / "speakers.json") for d in SEARCH_DIRS)
            sys.exit(f"No speakers.json found. Looked in: {looked}\n"
                     f"Point me at it with --out <dir>.")
        db = json.loads(out_json.read_text("utf-8"))
        before = sum(len(json.dumps(v, ensure_ascii=False)) for v in db.values())
        db = {k: clean_record(v) for k, v in db.items()}
        write(db, out_json, out_js)
        after = sum(len(json.dumps(v, ensure_ascii=False)) for v in db.values())
        print(f"Cleaned {len(db)} records in {out_dir}/, {before - after} chars of junk removed.")
        report(db)
        return

    db = json.loads(out_json.read_text("utf-8")) if out_json.exists() else {}
    if db:
        print(f"Resuming — {len(db)} slugs already held in {out_json}.")

    files = [a for a in argv if not a.startswith("-")]
    if "--out" in argv:
        files = [f for f in files if f != argv[argv.index("--out") + 1]]

    if files:
        slugs = slugs_from_index(files[0])
        print(f"{len(slugs)} slugs from {files[0]}")
    else:
        print("No index page given — probing. This is slower and noisier.")
        slugs = probe_slugs()

    todo = [s for s in slugs if s not in db]
    print(f"{len(todo)} to fetch, ~{len(todo) * DELAY / 60:.0f} min at {DELAY}s each.\n")

    try:
        for n, slug in enumerate(todo, 1):
            d = fetch(slug)
            if d:
                db[slug] = d
            print(f"[{n}/{len(todo)}] {slug} {'ok' if d else 'skip'}", flush=True)
            time.sleep(DELAY)
            if n % 50 == 0:
                write(db, out_json, out_js)
    except KeyboardInterrupt:
        print("\nInterrupted — saving what's held.")

    write(db, out_json, out_js)
    report(db)


def write(db, out_json, out_js):
    out_json.write_text(json.dumps(db, ensure_ascii=False, indent=1), "utf-8")
    out_js.write_text(
        "/* Derived from the Speech Accent Archive (Weinberger 2015, "
        "accent.gmu.edu), CC BY-NC-SA 4.0. This file is an adaptation of that "
        "data and carries the same licence. */\n"
        "window.SPEAKERS = " + json.dumps(db, ensure_ascii=False) + ";\n",
        "utf-8",
    )


def report(db):
    print(f"\n{len(db)} speakers held")
    print(f"  {sum(1 for d in db.values() if d.get('ipa'))} with a usable IPA line")
    print(f"  {sum(1 for d in db.values() if d.get('age of english onset'))} with an onset age")
    print("\nVerified speaker counts — paste into SPEC's n column:\n")
    for stem in STEMS:
        n = sum(1 for k in db if re.fullmatch(rf"{stem}\d+", k))
        print(f"  {stem:14s} {n}" + ("   <- drop this row" if not n else ""))


if __name__ == "__main__":
    main()
