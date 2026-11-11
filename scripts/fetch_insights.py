"""Extra OpenAlex data for scripts/insights.py (resumable).

  python fetch_insights.py refyears   publication year of every paper our faculty papers cite
                                      (~438k works, ~4,400 requests) -> data/raw/ref_years.jsonl
  python fetch_insights.py geo        coordinates and size of our two NITs and every Indian partner institute
                                      (~25 requests) -> data/raw/institutions_geo.jsonl
  python fetch_insights.py citerout   2016-2026 paper count of the 40 institutes that cite us most
                                      (40 requests) -> data/raw/citer_output.jsonl
  python fetch_insights.py yearly     citations per year (counts_by_year) and open-access status of every paper
                                      in data/all_papers.csv (~215 requests) -> data/raw/works_yearly.jsonl

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


def citerout():
    """Papers (articles, reviews, conference papers) 2016-2026 of the institutes that cite us most, so their
    citations to us can be compared with their size (phase2.py citers). One count request per institute."""
    from phase2 import CITER_LABELS
    path = os.path.join(RAW, "citer_output.jsonl")
    have = {json.loads(l)["id"] for l in open(path, encoding="utf-8")} if os.path.exists(path) else set()
    todo = [i for i in CITER_LABELS if i not in have]
    print(f"citing-institute output: {len(have)} saved, {len(todo)} to fetch")
    with open(path, "a", encoding="utf-8") as f:
        for i in todo:
            data, left = get({"filter": f"authorships.institutions.id:{i},publication_year:2016-2026,"
                                        "type:article|review|conference-paper", "per_page": 1, "select": "id"})
            f.write(json.dumps({"id": i, "papers_2016_2026": data["meta"]["count"], "fetched": TODAY}) + "\n")
            print(f"  {i}: {data['meta']['count']}  (requests left today: {left})")


def yearly():
    """Citations received in each year and open-access status of every paper in all_papers.csv, for
    questions.py (richer, venues). OpenAlex gives counts_by_year for the last ten years only, so the total
    cited_by_count is saved too: citations up to year t = total - citations after t."""
    ids = sorted(set(pd.read_csv(os.path.join(DATA, "all_papers.csv"), usecols=["openalex_id"]).openalex_id))
    path = os.path.join(RAW, "works_yearly.jsonl")
    todo, have = batches(ids, path)
    print(f"citations per year: {have} saved, {sum(map(len, todo))} to fetch in {len(todo)} requests")

    def one(b):
        data, left = get({"filter": "openalex_id:" + "|".join(b), "per_page": BATCH,
                          "select": "id,cited_by_count,counts_by_year,open_access"})
        got = {w["id"].rsplit("/", 1)[-1]: w for w in data["results"]}
        out = []
        for i in b:
            w = got.get(i) or {}
            oa = w.get("open_access") or {}
            out.append(json.dumps({
                "id": i, "found": i in got, "cited_by_count": w.get("cited_by_count"),
                "counts_by_year": {str(c["year"]): c["cited_by_count"] for c in w.get("counts_by_year") or []},
                "is_oa": oa.get("is_oa"), "oa_status": oa.get("oa_status"),
                "any_repository_has_fulltext": oa.get("any_repository_has_fulltext"), "fetched": TODAY}) + "\n")
        return "".join(out), left

    with open(path, "a", encoding="utf-8") as f, ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for k, (lines, left) in enumerate(pool.map(one, todo)):
            f.write(lines)
            if k % 50 == 0 or k == len(todo) - 1:
                f.flush()
                print(f"  batch {k + 1}/{len(todo)}  (requests left today: {left})", flush=True)


if __name__ == "__main__":
    step = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        {"refyears": refyears, "geo": geo, "citerout": citerout, "yearly": yearly}[step]()
    except KeyError:
        sys.exit(__doc__)
    except LimitReached as e:
        sys.exit(str(e))
