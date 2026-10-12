"""Step 3: find Indian-institution works linked to our papers by citation (resumable).

  refs   - Indian works that our papers cite      (filter cited_by:<our ids>)
  citers - Indian works that cite our papers      (filter cites:<our ids>)

Each batch covers 100 of our papers. Works are stored trimmed (id, year, authors with
institutions, and for citers which of our papers they cite) in
data/raw/links_<direction>.jsonl. Rerun until it reports all batches done; the free
daily OpenAlex quota usually needs two runs.
"""
import json
import os
import sys

from fetch_works import INSTITUTIONS, RAW, LimitReached, get

BATCH = 100


def our_ids():
    ids = set()
    for name in INSTITUTIONS:
        path = os.path.join(RAW, name.replace(" ", "_") + "_works.jsonl")
        ids.update(json.loads(l)["id"].rsplit("/", 1)[-1] for l in open(path, encoding="utf-8"))
    return sorted(ids)


def trim(w, ours):
    rec = {
        "id": w["id"].rsplit("/", 1)[-1],
        "doi": w.get("doi"),
        "year": w.get("publication_year"),
        "authors": [
            {
                "id": (a["author"]["id"] or "").rsplit("/", 1)[-1],
                "name": a["author"]["display_name"],
                "inst": [[i["id"].rsplit("/", 1)[-1], i["display_name"], i.get("country_code"), i.get("type")]
                         for i in a["institutions"]],
            }
            for a in w["authorships"]
        ],
    }
    if "referenced_works" in w:
        rec["cites_ours"] = [r.rsplit("/", 1)[-1] for r in w["referenced_works"]
                             if r.rsplit("/", 1)[-1] in ours]
    if w.get("primary_topic"):
        rec["field"] = w["primary_topic"]["field"]["display_name"]
    return rec


def run(direction, ids, ours):
    flt, fields = {
        "refs": ("cited_by", "id,doi,publication_year,authorships,primary_topic"),
        "citers": ("cites", "id,doi,publication_year,authorships,primary_topic,referenced_works"),
    }[direction]
    out = os.path.join(RAW, f"links_{direction}.jsonl")
    progress = os.path.join(RAW, f"links_{direction}.done")
    done = set(open(progress).read().split()) if os.path.exists(progress) else set()
    batches = [ids[i:i + BATCH] for i in range(0, len(ids), BATCH)]
    for b, batch in enumerate(batches):
        if str(b) in done:
            continue
        params = {
            "filter": f"{flt}:{'|'.join(batch)},institutions.country_code:IN",
            "select": fields, "per_page": 200, "cursor": "*",
        }
        rows = []
        while params["cursor"]:
            data, remaining = get(params)
            rows += [trim(w, ours) for w in data["results"]]
            params["cursor"] = data["meta"].get("next_cursor")
        # write the batch only once it is complete, so a quota stop never leaves half a batch
        with open(out, "a", encoding="utf-8") as f:
            f.writelines(json.dumps(r) + "\n" for r in rows)
        with open(progress, "a") as f:
            f.write(f"{b}\n")
        print(f"{direction}: batch {b + 1}/{len(batches)}  +{len(rows)} works  (requests left: {remaining})")
    print(f"{direction}: all {len(batches)} batches done")


if __name__ == "__main__":
    ids = our_ids()
    ours = set(ids)
    try:
        for direction in ("refs", "citers"):
            run(direction, ids, ours)
    except LimitReached as e:
        sys.exit(f"Stopped: {e}. Progress is saved; rerun later to continue.")
