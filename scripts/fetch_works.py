"""Step 1: download all OpenAlex works (2016-2026) for Team 12's institutions.

Saves raw JSON pages to data/raw/<inst>_works.jsonl so later steps never re-hit the API.
"""
import json
import os
import sys
import time

import requests

API = "https://api.openalex.org/works"
API_KEY = os.environ.get("OPENALEX_API_KEY")  # optional: free key raises the daily limit

INSTITUTIONS = {
    "NIT Trichy": "I122964287",     # ror.org/047x65e68
    "NIT Surathkal": "I11880225",   # ror.org/01hz4v948
}
# journal articles, reviews and conference papers only
TYPES = "article|review|conference-paper"
FIELDS = ",".join([
    "id", "doi", "title", "publication_year", "type", "primary_location",
    "authorships", "cited_by_count", "referenced_works", "primary_topic",
])

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")


class LimitReached(Exception):
    pass


def get(params):
    return get_url(API, params)


def get_url(url, params):
    if API_KEY:
        params["api_key"] = API_KEY
    for attempt in range(5):
        r = requests.get(url, params=params, timeout=60)
        if r.status_code == 200:
            return r.json(), r.headers.get("X-RateLimit-Remaining")
        print("  HTTP", r.status_code, r.text[:200], file=sys.stderr)
        if r.status_code == 429 and "Retry-After" not in r.headers:
            raise LimitReached("Daily OpenAlex limit reached - rerun tomorrow or set OPENALEX_API_KEY")
        time.sleep(2 ** attempt)
    sys.exit("giving up")


def fetch(name, inst_id):
    out = os.path.join(RAW, name.replace(" ", "_") + "_works.jsonl")
    if os.path.exists(out):
        print(f"{name}: already downloaded -> {out}")
        return
    params = {
        "filter": f"authorships.institutions.id:{inst_id},publication_year:2016-2026,type:{TYPES}",
        "select": FIELDS,
        "per_page": 200,
        "cursor": "*",
    }
    n = 0
    tmp = out + ".part"
    with open(tmp, "w", encoding="utf-8") as f:
        while params["cursor"]:
            data, remaining = get(params)
            for w in data["results"]:
                f.write(json.dumps(w) + "\n")
            n += len(data["results"])
            print(f"{name}: {n}/{data['meta']['count']}  (requests left today: {remaining})")
            params["cursor"] = data["meta"].get("next_cursor")
    os.replace(tmp, out)


if __name__ == "__main__":
    os.makedirs(RAW, exist_ok=True)
    for name, inst_id in INSTITUTIONS.items():
        fetch(name, inst_id)
