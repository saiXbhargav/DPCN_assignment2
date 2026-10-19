"""Extra OpenAlex data for scripts/insights.py (resumable).

  python fetch_insights.py refyears   publication year of every paper our faculty papers cite
                                      (~438k works, ~4,400 requests) -> data/raw/ref_years.jsonl
  python fetch_insights.py geo        coordinates and size of our two NITs and every Indian partner institute
                                      (~25 requests) -> data/raw/institutions_geo.jsonl

Needs the OPENALEX_API_KEY environment variable for refyears (the free key allows 10,000 requests a day).
"""
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from fetch_impact import BATCH, TODAY, batches
from fetch_works import INSTITUTIONS, RAW, ROOT, LimitReached, get, get_url

DATA = os.path.join(ROOT, "data")
WORKERS = 5


def faculty_paper_ids():
    return set(pd.read_csv(os.path.join(DATA, "group12_data.csv"), usecols=["openalex_id"]).openalex_id)


def refyears():
    ours = faculty_paper_ids()
    refs = set()
    for name in INSTITUTIONS:
        for line in open(os.path.join(RAW, name.replace(" ", "_") + "_works.jsonl"), encoding="utf-8"):
            w = json.loads(line)
            if w["id"].rsplit("/", 1)[-1] in ours:
                refs.update(r.rsplit("/", 1)[-1] for r in w["referenced_works"])
    path = os.path.join(RAW, "ref_years.jsonl")
    todo, have = batches(sorted(refs), path)
    print(f"reference years: {have} saved, {sum(map(len, todo))} to fetch in {len(todo)} requests")

    def one(b):
        data, left = get({"filter": "openalex_id:" + "|".join(b), "per_page": BATCH,
                          "select": "id,publication_year"})
        got = {w["id"].rsplit("/", 1)[-1]: w.get("publication_year") for w in data["results"]}
        # works OpenAlex no longer has (merged / deleted) are saved with year null, so they aren't re-asked
        return "".join(json.dumps({"id": i, "year": got.get(i), "found": i in got, "fetched": TODAY}) + "\n"
                       for i in b), left

    # requests wait on the server, so a few run in parallel (well under OpenAlex's 10 requests/second)
    with open(path, "a", encoding="utf-8") as f, ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for k, (lines, left) in enumerate(pool.map(one, todo)):
            f.write(lines)           # one whole batch per write, from the main thread only
            if k % 200 == 0 or k == len(todo) - 1:
                f.flush()
                print(f"  batch {k + 1}/{len(todo)}  (requests left today: {left})", flush=True)


def geo():
    ic = pd.read_csv(os.path.join(DATA, "indian_connections.csv"))
    wanted = sorted(set(ic.partner_id) | set(INSTITUTIONS.values()))
    path = os.path.join(RAW, "institutions_geo.jsonl")
    todo, have = batches(wanted, path)
    print(f"institution coordinates: {have} saved, {sum(map(len, todo))} to fetch in {len(todo)} requests")
    with open(path, "a", encoding="utf-8") as f:
        for b in todo:
            data, left = get_url("https://api.openalex.org/institutions", {
                "filter": "openalex_id:" + "|".join(b), "per_page": BATCH,
                "select": "id,display_name,geo,works_count,country_code,type"})
            got = {r["id"].rsplit("/", 1)[-1]: r for r in data["results"]}
            for i in b:
                r = got.get(i) or {}
                g = r.get("geo") or {}
                f.write(json.dumps({"id": i, "name": r.get("display_name"), "lat": g.get("latitude"),
                                    "lon": g.get("longitude"), "city": g.get("city"), "region": g.get("region"),
                                    "country": r.get("country_code"), "works_count": r.get("works_count"),
                                    "type": r.get("type"), "found": i in got, "fetched": TODAY}) + "\n")
            print(f"  +{len(got)}  (requests left today: {left})")


if __name__ == "__main__":
    step = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        {"refyears": refyears, "geo": geo}[step]()
    except KeyError:
        sys.exit(__doc__)
    except LimitReached as e:
        sys.exit(str(e))
