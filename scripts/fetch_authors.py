"""Step 2: fetch h-index and total works for every NIT author with >= 3 papers in our data.

Output: data/raw/authors.jsonl (one OpenAlex author record per line).
"""
import collections
import json
import os

from fetch_works import INSTITUTIONS, RAW, get_url

MIN_PAPERS = 3
OWN = set(INSTITUTIONS.values())
OUT = os.path.join(RAW, "authors.jsonl")


def own_author_ids():
    counts = collections.Counter()
    for name in INSTITUTIONS:
        path = os.path.join(RAW, name.replace(" ", "_") + "_works.jsonl")
        for line in open(path, encoding="utf-8"):
            for a in json.loads(line)["authorships"]:
                if a["author"]["id"] and any(i["id"].rsplit("/", 1)[-1] in OWN for i in a["institutions"]):
                    counts[a["author"]["id"].rsplit("/", 1)[-1]] += 1
    return sorted(a for a, n in counts.items() if n >= MIN_PAPERS)


if __name__ == "__main__":
    done = set()
    if os.path.exists(OUT):
        done = {json.loads(l)["id"].rsplit("/", 1)[-1] for l in open(OUT, encoding="utf-8")}
    todo = [a for a in own_author_ids() if a not in done]
    print(f"{len(done)} authors already fetched, {len(todo)} to go")
    with open(OUT, "a", encoding="utf-8") as f:
        for i in range(0, len(todo), 100):
            batch = todo[i:i + 100]
            data, remaining = get_url("https://api.openalex.org/authors", {
                "filter": "openalex_id:" + "|".join(batch),
                "select": "id,display_name,orcid,works_count,cited_by_count,summary_stats,last_known_institutions",
                "per_page": 200,
            })
            for a in data["results"]:
                f.write(json.dumps(a) + "\n")
            print(f"  {i + len(batch)}/{len(todo)}  (requests left today: {remaining})")
