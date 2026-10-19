"""Extra OpenAlex data for the comparisons (resumable; about 300 requests in total).

  python fetch_impact.py works     field-normalised impact of every paper in our raw files:
                                   fwci and citation_normalized_percentile -> data/raw/works_impact.jsonl
  python fetch_impact.py authors   OpenAlex profiles (h-index) of matched faculty IDs not in authors.jsonl
                                   -> data/raw/authors_extra.jsonl
  python fetch_impact.py partners  research-topic profile (papers per subfield, 2016-2026) of the main partner
                                   institutes in data/indian_connections.csv -> data/raw/partner_subfields.jsonl

Citation counts in group12_data.csv stay as collected on 7 October 2026; these files only add the
normalised measures, with the date they were fetched.
"""
import datetime
import json
import os
import sys

import pandas as pd

from fetch_links import our_ids
from fetch_works import RAW, ROOT, TYPES, LimitReached, get, get_url

BATCH = 100
TODAY = datetime.date.today().isoformat()
TOP_PARTNERS = 40  # per NIT, by shared papers and by citation exchange


def batches(ids, path):
    done = set()
    if os.path.exists(path):
        done = {json.loads(l)["id"] for l in open(path, encoding="utf-8")}
    todo = [i for i in ids if i not in done]
    return [todo[i:i + BATCH] for i in range(0, len(todo), BATCH)], len(done)


def works():
    path = os.path.join(RAW, "works_impact.jsonl")
    todo, have = batches(our_ids(), path)
    print(f"works: {have} saved, {sum(map(len, todo))} to fetch in {len(todo)} requests")
    with open(path, "a", encoding="utf-8") as f:
        for b in todo:
            data, left = get({"filter": "openalex_id:" + "|".join(b), "per_page": BATCH,
                              "select": "id,fwci,citation_normalized_percentile,cited_by_percentile_year"})
            for w in data["results"]:
                pct = w.get("citation_normalized_percentile") or {}
                f.write(json.dumps({"id": w["id"].rsplit("/", 1)[-1], "fwci": w.get("fwci"),
                                    "percentile": pct.get("value"), "top_10pct": pct.get("is_in_top_10_percent"),
                                    "top_1pct": pct.get("is_in_top_1_percent"), "fetched": TODAY}) + "\n")
            print(f"  +{len(data['results'])}  (requests left today: {left})")


def authors():
    have = {json.loads(l)["id"].rsplit("/", 1)[-1] for l in open(os.path.join(RAW, "authors.jsonl"), encoding="utf-8")}
    m = pd.read_csv(os.path.join(ROOT, "data", "reference", "faculty_openalex_map.csv"), dtype=str)
    path = os.path.join(RAW, "authors_extra.jsonl")
    todo, saved = batches(sorted(set(m.author_id) - have), path)
    print(f"authors: {saved} saved, {sum(map(len, todo))} to fetch in {len(todo)} requests")
    with open(path, "a", encoding="utf-8") as f:
        for b in todo:
            data, left = get_url("https://api.openalex.org/authors", {
                "filter": "openalex_id:" + "|".join(b), "per_page": BATCH,
                "select": "id,display_name,orcid,works_count,cited_by_count,summary_stats,last_known_institutions"})
            for a in data["results"]:
                a["id"] = a["id"].rsplit("/", 1)[-1]
                a["fetched"] = TODAY
                f.write(json.dumps(a) + "\n")
            print(f"  +{len(data['results'])}  (requests left today: {left})")


def partners():
    ic = pd.read_csv(os.path.join(ROOT, "data", "indian_connections.csv"))
    ic = ic[~ic.partner_id.isin(["I122964287", "I11880225"])]
    ic["exchange"] = ic.cites_from_partner + ic.cites_to_partner
    pick = set()
    for _, g in ic.groupby("your_inst"):
        pick |= set(g.nlargest(TOP_PARTNERS, "shared_papers").partner_id)
        pick |= set(g.nlargest(TOP_PARTNERS, "exchange").partner_id)
        # candidates for new collaborations: much citation exchange, few joint papers so far
        pick |= set(g[g.shared_papers <= 5].nlargest(TOP_PARTNERS, "exchange").partner_id)
    path = os.path.join(RAW, "partner_subfields.jsonl")
    have = {json.loads(l)["id"] for l in open(path, encoding="utf-8")} if os.path.exists(path) else set()
    todo = sorted(pick - have)
    print(f"partners: {len(have)} saved, {len(todo)} to fetch")
    with open(path, "a", encoding="utf-8") as f:
        for iid in todo:
            data, left = get({"filter": f"authorships.institutions.id:{iid},publication_year:2016-2026,type:{TYPES}",
                              "group_by": "primary_topic.subfield.id"})
            groups = {g["key"].rsplit("/", 1)[-1]: g["count"] for g in data["group_by"]}
            name = ic.loc[ic.partner_id == iid, "partner_inst"].iat[0]
            f.write(json.dumps({"id": iid, "name": name, "subfields": groups,
                                "papers": data["meta"]["count"], "fetched": TODAY}) + "\n")
            print(f"  {name}: {data['meta']['count']} papers, {len(groups)} subfields  (left: {left})")


def sources():
    """Journal impact for the "IF > 5 / IF > 10" counts. Clarivate's Journal Impact Factor is not open, so we use
    OpenAlex's 2-year mean citedness: citations this year to the journal's papers of the previous two years,
    divided by the number of those papers - the same formula as the impact factor, on OpenAlex data."""
    ids = set()
    for name in ("NIT_Trichy", "NIT_Surathkal"):
        for line in open(os.path.join(RAW, f"{name}_works.jsonl"), encoding="utf-8"):
            src = ((json.loads(line).get("primary_location") or {}).get("source") or {})
            if src.get("id"):
                ids.add(src["id"].rsplit("/", 1)[-1])
    path = os.path.join(RAW, "sources.jsonl")
    todo, have = batches(sorted(ids), path)
    print(f"sources: {have} saved, {sum(map(len, todo))} to fetch in {len(todo)} requests")
    with open(path, "a", encoding="utf-8") as f:
        for b in todo:
            data, left = get_url("https://api.openalex.org/sources", {
                "filter": "openalex_id:" + "|".join(b), "per_page": BATCH,
                "select": "id,display_name,type,issn_l,summary_stats"})
            for s in data["results"]:
                f.write(json.dumps({"id": s["id"].rsplit("/", 1)[-1], "name": s["display_name"], "type": s["type"],
                                    "issn_l": s.get("issn_l"),
                                    "if_2yr": (s.get("summary_stats") or {}).get("2yr_mean_citedness"),
                                    "fetched": TODAY}) + "\n")
            print(f"  +{len(data['results'])}  (requests left today: {left})")


def authorids():
    """ORCID and Scopus IDs that OpenAlex holds for every NIT author with 2+ papers (used by match_faculty.py)."""
    counts = {}
    for name in ("NIT_Trichy", "NIT_Surathkal"):
        for line in open(os.path.join(RAW, f"{name}_works.jsonl"), encoding="utf-8"):
            for a in json.loads(line)["authorships"]:
                if a["author"]["id"] and any(i["id"].rsplit("/", 1)[-1] in ("I122964287", "I11880225")
                                             for i in a["institutions"]):
                    aid = a["author"]["id"].rsplit("/", 1)[-1]
                    counts[aid] = counts.get(aid, 0) + 1
    path = os.path.join(RAW, "author_ids.jsonl")
    todo, have = batches(sorted(a for a, n in counts.items() if n >= 2), path)
    print(f"author ids: {have} saved, {sum(map(len, todo))} to fetch in {len(todo)} requests")
    with open(path, "a", encoding="utf-8") as f:
        for b in todo:
            data, left = get_url("https://api.openalex.org/authors", {
                "filter": "openalex_id:" + "|".join(b), "per_page": BATCH, "select": "id,ids"})
            for a in data["results"]:
                ids = a.get("ids") or {}
                f.write(json.dumps({"id": a["id"].rsplit("/", 1)[-1],
                                    "orcid": (ids.get("orcid") or "").rsplit("/", 1)[-1],
                                    "scopus": (ids.get("scopus") or "").rsplit("=", 1)[-1], "fetched": TODAY}) + "\n")
            print(f"  +{len(data['results'])}  (requests left today: {left})")


def institutions():
    """Type and parent organisations of every partner institute (e.g. a lab whose parent is CSIR or DAE), used to
    flag cross-cluster links (NIT <-> IIT, CSIR, IISER, ...). Parents are fetched too, so their names are known."""
    ic = pd.read_csv(os.path.join(ROOT, "data", "indian_connections.csv"))
    path = os.path.join(RAW, "institutions.jsonl")
    for round_ in (1, 2):
        have = {json.loads(l)["id"]: json.loads(l) for l in open(path, encoding="utf-8")} if os.path.exists(path) else {}
        wanted = set(ic.partner_id) if round_ == 1 else {p for r in have.values() for p in r["lineage"]}
        todo, saved = batches(sorted(wanted), path)
        print(f"institutions (round {round_}): {saved} saved, {sum(map(len, todo))} to fetch in {len(todo)} requests")
        with open(path, "a", encoding="utf-8") as f:
            for b in todo:
                data, left = get_url("https://api.openalex.org/institutions", {
                    "filter": "openalex_id:" + "|".join(b), "per_page": BATCH,
                    "select": "id,display_name,type,lineage,country_code"})
                for r in data["results"]:
                    f.write(json.dumps({"id": r["id"].rsplit("/", 1)[-1], "name": r["display_name"], "type": r["type"],
                                        "country": r.get("country_code"),
                                        "lineage": [x.rsplit("/", 1)[-1] for x in r.get("lineage") or []],
                                        "fetched": TODAY}) + "\n")
                print(f"  +{len(data['results'])}  (requests left today: {left})")


def citers():
    """Title and citation count of every outside Indian paper that cites us (in_indian edges), for the list of the
    most-cited papers citing each NIT."""
    cit = pd.read_csv(os.path.join(ROOT, "data", "citation_network.csv"), usecols=["source_id", "edge_type"],
                      low_memory=False)
    path = os.path.join(RAW, "citers_info.jsonl")
    todo, have = batches(sorted(set(cit.source_id[cit.edge_type == "in_indian"])), path)
    print(f"citing papers: {have} saved, {sum(map(len, todo))} to fetch in {len(todo)} requests")
    with open(path, "a", encoding="utf-8") as f:
        for b in todo:
            data, left = get({"filter": "openalex_id:" + "|".join(b), "per_page": BATCH,
                              "select": "id,title,publication_year,cited_by_count,primary_location"})
            for w in data["results"]:
                src = ((w.get("primary_location") or {}).get("source") or {})
                f.write(json.dumps({"id": w["id"].rsplit("/", 1)[-1], "title": w.get("title"),
                                    "year": w.get("publication_year"), "cited_by_count": w.get("cited_by_count"),
                                    "venue": src.get("display_name"), "fetched": TODAY}) + "\n")
            if len(todo) < 50 or todo.index(b) % 25 == 0:
                print(f"  +{len(data['results'])}  (requests left today: {left})")


if __name__ == "__main__":
    step = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        {"works": works, "authors": authors, "partners": partners, "sources": sources, "authorids": authorids,
         "institutions": institutions, "citers": citers}[step]()
    except KeyError:
        sys.exit(__doc__)
    except LimitReached as e:
        sys.exit(str(e))
