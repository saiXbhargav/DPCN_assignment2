"""Downloads for the comparison with other NITs (17 Nov 2026). Finished files are skipped.

  python fetch_peers.py   Papers 2016-2026 of the six South Indian NITs: our two + NIT Warangal + NIT Calicut (17 Nov),
                          then NIT Puducherry + NIT Andhra Pradesh (18 Nov). Same filter for all, so the comparison is
                          fair. Compact records only (no reference lists) -> data/raw/peers/<NIT>_works.jsonl
  python fetch_peers.py refs   For the same papers, the references that point to another paper of the same NIT
                          (for the own-paper / self-citation share) -> data/raw/peers/<NIT>_internal_refs.jsonl

Same source as the rest of the project (OpenAlex), same request helper as fetch_works.py. The faculty numbers for
the comparison come from each NIT's NIRF 2025 data file instead (see phase2_growth.py nirf).
"""
import json
import os

from fetch_works import RAW, TYPES, get

PEERS = {
    "NIT Trichy": "I122964287",      # ror.org/047x65e68
    "NIT Surathkal": "I11880225",    # ror.org/01hz4v948
    "NIT Warangal": "I121750182",    # ror.org/017ebfz38
    "NIT Calicut": "I114845381",     # ror.org/03yyd7552
    "NIT Puducherry": "I4400573194",       # ror.org/02tare285, Karaikal
    "NIT Andhra Pradesh": "I4210153924",   # ror.org/0456pcg54, Tadepalligudem
}
FIELDS = ",".join(["id", "doi", "publication_year", "type", "primary_location", "authorships", "cited_by_count",
                   "fwci", "primary_topic"])
OUT = os.path.join(RAW, "peers")


def compact(w):
    """Keep what the comparison needs: year, type, venue, citations, FWCI, field, and who wrote it from where."""
    src = ((w.get("primary_location") or {}).get("source") or {})
    topic = w.get("primary_topic") or {}
    return {
        "id": w["id"].rsplit("/", 1)[-1], "doi": w.get("doi"), "year": w.get("publication_year"), "type": w.get("type"),
        "cited_by_count": w.get("cited_by_count"), "fwci": w.get("fwci"),
        "source_id": (src.get("id") or "").rsplit("/", 1)[-1] or None, "source": src.get("display_name"),
        "source_type": src.get("type"),
        "field": (topic.get("field") or {}).get("display_name"), "subfield": (topic.get("subfield") or {}).get("display_name"),
        "authors": [{"id": ((a.get("author") or {}).get("id") or "").rsplit("/", 1)[-1] or None,
                     "name": (a.get("author") or {}).get("display_name"),
                     "inst": [i["id"].rsplit("/", 1)[-1] for i in a.get("institutions", []) if i.get("id")],
                     "countries": a.get("countries", [])}
                    for a in w.get("authorships", [])],
        "inst_types": sorted({i.get("type") for a in w.get("authorships", []) for i in a.get("institutions", [])
                              if i.get("type")}),
        "inst_countries": sorted({i.get("country_code") for a in w.get("authorships", [])
                                  for i in a.get("institutions", []) if i.get("country_code")}),
    }


def works():
    os.makedirs(OUT, exist_ok=True)
    for name, inst in PEERS.items():
        out = os.path.join(OUT, name.replace(" ", "_") + "_works.jsonl")
        if os.path.exists(out):
            print(f"{name}: already downloaded -> {out}")
            continue
        params = {"filter": f"authorships.institutions.id:{inst},publication_year:2016-2026,type:{TYPES}",
                  "select": FIELDS, "per_page": 200, "cursor": "*"}
        n, tmp = 0, out + ".part"
        with open(tmp, "w", encoding="utf-8") as f:
            while params["cursor"]:
                data, remaining = get(params)
                for w in data["results"]:
                    f.write(json.dumps(compact(w), ensure_ascii=False) + "\n")
                n += len(data["results"])
                print(f"{name}: {n}/{data['meta']['count']}  (requests left today: {remaining})", flush=True)
                params["cursor"] = data["meta"].get("next_cursor")
        os.replace(tmp, out)


def refs():
    """Reference lists of the same papers, keeping only references to another paper of the same NIT (2016-2026),
    for the own-paper citation (self-citation) share in south_nits.py -> data/raw/peers/<NIT>_internal_refs.jsonl"""
    for name, inst in PEERS.items():
        out = os.path.join(OUT, name.replace(" ", "_") + "_internal_refs.jsonl")
        if os.path.exists(out):
            print(f"{name}: already downloaded -> {out}")
            continue
        with open(os.path.join(OUT, name.replace(" ", "_") + "_works.jsonl"), encoding="utf-8") as f:
            ids = {json.loads(line)["id"] for line in f}
        params = {"filter": f"authorships.institutions.id:{inst},publication_year:2016-2026,type:{TYPES}",
                  "select": "id,referenced_works", "per_page": 200, "cursor": "*"}
        n, tmp = 0, out + ".part"
        with open(tmp, "w", encoding="utf-8") as f:
            while params["cursor"]:
                data, remaining = get(params)
                for w in data["results"]:
                    wid = w["id"].rsplit("/", 1)[-1]
                    inside = [r.rsplit("/", 1)[-1] for r in (w.get("referenced_works") or [])
                              if r.rsplit("/", 1)[-1] in ids]
                    f.write(json.dumps({"id": wid, "n_refs": len(w.get("referenced_works") or []),
                                        "internal_refs": inside}) + "\n")
                n += len(data["results"])
                print(f"{name} refs: {n}/{data['meta']['count']}  (requests left today: {remaining})", flush=True)
                params["cursor"] = data["meta"].get("next_cursor")
        os.replace(tmp, out)


if __name__ == "__main__":
    import sys
    refs() if sys.argv[1:] == ["refs"] else works()
