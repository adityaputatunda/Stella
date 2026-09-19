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
    python3 harvest.py browse.html      # slug list read from a saved index page
    python3 harvest.py                  # fallback: probe stem1, stem2, ... per stem
    python3 harvest.py --clean          # re-trim an existing speakers.json, no network

Resumable: re-running skips slugs already in speakers.json.
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

OUT_JSON = Path("speakers.json")
OUT_JS = Path("speakers.js")

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

# Per-field shape enforcement, applied after the generic trim.
SHAPES = {
    "length of english residence": re.compile(
        r"^\s*([\d.]+\s*(?:years?|months?|weeks?|days?))", re.I),
    "age of english onset": re.compile(r"^\s*([\d.]+)"),
    "age, sex": re.compile(r"^\s*(\d+\s*,\s*[a-z]+)", re.I),
}

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
    # No shape rule: drop anything after a run of 3+ spaces, which is where the
    # flattened markup usually joins two unrelated blocks.
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
    if rec.get("ipa"):
        out["ipa"] = STOP.sub("", rec["ipa"]).strip()
    if out.get("birth place"):
        out["country"] = out["birth place"].split(",")[-1].strip().lower()
    return out


# ---------------------------------------------------------------- slugs

SLUG_RE = re.compile(r"/samples/([a-z]+)(\d+)/")


def slugs_from_index(path):
    """Pull every /samples/<stem><n>/ link out of a saved archive page."""
    html = Path(path).read_text("utf-8", errors="replace")
    stems = set(STEMS)
    found = {
        (stem, int(num))
        for stem, num in SLUG_RE.findall(html)
        if stem in stems
    }
    if not found:
        sys.exit(f"No /samples/ links matching SPEC stems found in {path}. "
                 "Wrong page, or the markup changed — check by hand.")
    return [f"{s}{n}" for s, n in sorted(found)]


def probe_slugs():
    """Fallback when there's no index page: walk upward until misses pile up."""
    out = []
    for stem in STEMS:
        misses = 0
        for i in range(1, PROBE_CEILING):
            slug = f"{stem}{i}"
            if head_ok(slug):
                out.append(slug)
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
    flat = re.sub(r"<[^>]+>", "   ", html)          # 3 spaces: block boundary marker
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

    ipa = re.search(r"\[([^\]]{60,})\]", flat)
    if ipa:
        raw["ipa"] = re.sub(r"\s+", " ", ipa.group(1)).strip()

    rec = clean_record(raw)
    return rec if rec.get("birth place") else None


def fetch(slug):
    req = u.Request(SAMPLE_URL.format(slug), headers=HEADERS)
    try:
        with u.urlopen(req, timeout=TIMEOUT) as r:
            return parse(r.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        print(f"  ! {slug}: HTTP {e.code}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"  ! {slug}: {e}", file=sys.stderr)
        return None


# ---------------------------------------------------------------- main

def main():
    if "--clean" in sys.argv:
        if not OUT_JSON.exists():
            sys.exit("No speakers.json to clean.")
        db = json.loads(OUT_JSON.read_text("utf-8"))
        before = sum(len(json.dumps(v)) for v in db.values())
        db = {k: clean_record(v) for k, v in db.items()}
        write(db)
        after = sum(len(json.dumps(v)) for v in db.values())
        print(f"Cleaned {len(db)} records, {before - after} chars of junk removed.")
        report(db)
        return

    db = json.loads(OUT_JSON.read_text("utf-8")) if OUT_JSON.exists() else {}
    if db:
        print(f"Resuming — {len(db)} slugs already held.")

    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if args:
        slugs = slugs_from_index(args[0])
        print(f"{len(slugs)} slugs from {args[0]}")
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
                write(db)
    except KeyboardInterrupt:
        print("\nInterrupted — saving what's held.")

    write(db)
    report(db)


def write(db):
    OUT_JSON.write_text(json.dumps(db, ensure_ascii=False, indent=1), "utf-8")
    OUT_JS.write_text(
        "/* Derived from the Speech Accent Archive (Weinberger 2015, "
        "accent.gmu.edu), CC BY-NC-SA 4.0. This file is an adaptation of that "
        "data and carries the same licence. */\n"
        "window.SPEAKERS = " + json.dumps(db, ensure_ascii=False) + ";\n",
        "utf-8",
    )


def report(db):
    print(f"\n{len(db)} speakers written to {OUT_JSON} and {OUT_JS}")
    print(f"  {sum(1 for d in db.values() if d.get('ipa'))} with IPA")
    scored = sum(1 for d in db.values() if d.get("age of english onset"))
    print(f"  {scored} with an onset age (these get a difficulty multiplier)")
    print("\nVerified speaker counts — paste into SPEC's n column:\n")
    for stem in STEMS:
        n = sum(1 for k in db if re.fullmatch(rf"{stem}\d+", k))
        print(f"  {stem:14s} {n}" + ("   <- drop this row" if not n else ""))


if __name__ == "__main__":
    main()
