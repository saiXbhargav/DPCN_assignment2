"""Step 4: build data/group12_data.csv (one row per paper x NIT author) and data/faculty.csv.

Uses only local files from steps 1-3 plus data/reference/{scimago_all.csv, core_conf.csv}.
If step 3 (fetch_links.py) has not finished, the two cites/cited_by columns are left
blank for papers whose batch is not yet fetched.
"""
import collections
import json
import os
import re

import pandas as pd

from fetch_links import BATCH, our_ids
from fetch_works import INSTITUTIONS, RAW, ROOT

GROUP = 12
OWN = {v: k for k, v in INSTITUTIONS.items()}
REF = os.path.join(ROOT, "data", "reference")
OUT = os.path.join(ROOT, "data")


def short(url):
    return (url or "").rsplit("/", 1)[-1]


# ---------- journal quartiles (SJR rank within subject area & year) ----------
def load_quartiles():
    sj = pd.read_csv(os.path.join(REF, "scimago_all.csv"), dtype={"Issn": str})
    sj = sj.dropna(subset=["SJR", "Issn"])
    pct = sj.groupby(["field", "year"])["SJR"].rank(ascending=False, pct=True)
    sj["q"] = pd.cut(pct, [0, .25, .5, .75, 1], labels=[1, 2, 3, 4]).astype(int)
    best = sj.groupby(["Sourceid", "year"])["q"].min().reset_index()
    issn = sj[["Sourceid", "Issn"]].drop_duplicates("Sourceid")
    by_issn, by_issn_year = {}, {}
    for sid, issns in issn.itertuples(index=False):
        for i in str(issns).split(","):
            by_issn[i.strip().upper()] = sid
    for sid, year, q in best.itertuples(index=False):
        by_issn_year[(sid, int(year))] = q
    years = sorted({y for _, y in by_issn_year})
    return by_issn, by_issn_year, years


def quartile(issns, year, qtab):
    by_issn, by_issn_year, years = qtab
    for i in issns or []:
        sid = by_issn.get(i.replace("-", "").upper())
        if sid is None:
            continue
        # use the paper's year, else nearest available SJR year
        for y in sorted(years, key=lambda y: abs(y - year)):
            if (sid, y) in by_issn_year:
                return f"Q{by_issn_year[(sid, y)]}"
    return ""


# ---------- CORE conference ranks ----------
def load_core():
    core = pd.read_csv(os.path.join(REF, "core_conf.csv"), header=None,
                       usecols=[1, 2, 4], names=["title", "acronym", "rank"])
    core = core[core["rank"].isin(["A*", "A", "B", "C"])]
    acr = {}
    for a, t, r in zip(core.acronym, core.title, core["rank"]):
        if isinstance(a, str) and len(a) >= 3:
            acr[a.upper()] = (words(t), r)
    titles = [(words(t), r) for t, r in zip(core.title, core["rank"])]
    return acr, titles


STOP = {"ieee", "acm", "international", "conference", "on", "of", "and", "the", "in", "for",
        "annual", "symposium", "proceedings", "workshop", "joint", "a", "an", "to"}


def norm(s):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z ]", " ", s.lower())).strip()


def words(s):
    return set(norm(s).split()) - STOP


def core_rank(venue, core):
    """Match a venue to CORE when its title words nearly equal a CORE title (acronyms help only if titles agree)."""
    # regional editions and workshops are not ranked by CORE, even if the parent conference is
    if not venue or re.search(r"india|workshop|wkshp|\b\w+W\)", venue, re.I):
        return ""
    acr, titles = core
    tokens = re.findall(r"\b[A-Z][A-Za-z]*[A-Z]\b", venue)
    vw = words(venue) - {t.lower() for t in tokens}
    best = max(((len(t & vw) / len(t | vw), r) for t, r in titles if len(t) >= 2 and vw), default=(0, ""))
    if best[0] >= 0.75:
        return f"CORE {best[1]}"
    for token in tokens:
        hit = acr.get(token.upper())
        if hit and vw and len(hit[0] & vw) / len(hit[0] | vw) >= 0.5:
            return f"CORE {hit[1]}"
    return ""


# ---------- departments from raw affiliation strings ----------
DEPT_RE = re.compile(r"((?:Department|Dept\.?|School|Centre|Center)\s+(?:of|for)\s+[^,;]+)", re.I)
DEPT_ABBR = {
    "ECE": "Electronics and Communication Engineering",
    "EEE": "Electrical and Electronics Engineering",
    "CSE": "Computer Science and Engineering",
    "IT": "Information Technology",
    "ICE": "Instrumentation and Control Engineering",
    "MME": "Metallurgical and Materials Engineering",
    "ME": "Mechanical Engineering",
    "CE": "Civil Engineering",
}


def department(raw_affs):
    for s in raw_affs or []:
        m = DEPT_RE.search(s)
        if m:
            d = re.sub(r"\s+", " ", m.group(1).strip())
            d = re.sub(r"^(Dept\.?|Department)\s+of\s+", "Department of ", d, flags=re.I)
            rest = d.split(" of ", 1)[-1] if d.startswith("Department of ") else ""
            if rest.upper() in DEPT_ABBR:
                d = "Department of " + DEPT_ABBR[rest.upper()]
            return d
    return ""


# ---------- Indian links from step 3 ----------
def load_links():
    """Return (fetched paper ids, papers citing other-Indian work, papers cited by other-Indian work)."""
    ids = our_ids()
    fetched = {}
    for direction in ("refs", "citers"):
        done_file = os.path.join(RAW, f"links_{direction}.done")
        done = set(open(done_file).read().split()) if os.path.exists(done_file) else set()
        fetched[direction] = {w for b in done for w in ids[int(b) * BATCH:(int(b) + 1) * BATCH]}

    def other_indian(rec, own_insts):
        insts = {i[0] for a in rec["authors"] for i in a["inst"] if i[2] == "IN"}
        return bool(insts - own_insts)

    # Indian works our papers reference, keyed by id -> set of Indian institution ids
    ref_insts = {}
    path = os.path.join(RAW, "links_refs.jsonl")
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            r = json.loads(line)
            ref_insts[r["id"]] = {i[0] for a in r["authors"] for i in a["inst"] if i[2] == "IN"}
    citer_insts = collections.defaultdict(set)  # our paper id -> Indian inst ids of citing works
    path = os.path.join(RAW, "links_citers.jsonl")
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            r = json.loads(line)
            insts = {i[0] for a in r["authors"] for i in a["inst"] if i[2] == "IN"}
            for w in r.get("cites_ours", []):
                if w != r["id"]:  # some OpenAlex records list the paper itself as a reference
                    citer_insts[w] |= insts
    return fetched, ref_insts, citer_insts


def main():
    qtab = load_quartiles()
    core = load_core()
    fetched, ref_insts, citer_insts = load_links()
    authors = {short(a["id"]): a for a in map(json.loads, open(os.path.join(RAW, "authors.jsonl"), encoding="utf-8"))}

    rows = []
    for inst_name, inst_id in INSTITUTIONS.items():
        path = os.path.join(RAW, inst_name.replace(" ", "_") + "_works.jsonl")
        for line in open(path, encoding="utf-8"):
            w = json.loads(line)
            wid = short(w["id"])
            loc = w.get("primary_location") or {}
            src = loc.get("source") or {}
            venue = src.get("display_name") or ""
            is_conf = w["type"] == "conference-paper" or src.get("type") == "conference"
            issns = src.get("issn") or []
            year = w["publication_year"]
            q = "" if is_conf else quartile(issns, year, qtab)
            if is_conf:
                q = core_rank(venue, core)
            paper_insts = {short(i["id"]) for a in w["authorships"] for i in a["institutions"]}
            own_on_paper = {i for i in paper_insts if i in OWN}
            coinst = sorted({i["display_name"] for a in w["authorships"] for i in a["institutions"]
                             if i.get("country_code") == "IN" and short(i["id"]) not in OWN})
            if wid in fetched["refs"]:
                cites = any(ref_insts.get(short(r), set()) - set(OWN)
                            for r in w["referenced_works"] if short(r) != wid)
            else:
                cites = None
            cited_by = bool(citer_insts.get(wid, set()) - set(OWN)) if wid in fetched["citers"] else None
            topic = w.get("primary_topic") or {}

            for a in w["authorships"]:
                if not any(short(i["id"]) == inst_id for i in a["institutions"]):
                    continue
                aid = short(a["author"]["id"])
                rows.append({
                    "group": GROUP,
                    "institution": inst_name,
                    "author": a["author"]["display_name"],
                    "title": w["title"],
                    "year": year,
                    "type": "conference" if is_conf else "journal",
                    "journal_name": venue,
                    "issn": ";".join(issns) if not is_conf else "",
                    "doi": w.get("doi") or "",
                    "citations": w["cited_by_count"],
                    "quartile": q,
                    "coauthor_institutes": ";".join(coinst),
                    "cites_indian_inst": cites,
                    "cited_by_indian_inst": cited_by,
                    # extra columns used by later tasks
                    "author_id": aid,
                    "department": department(a.get("raw_affiliation_strings")),
                    "openalex_id": wid,
                    "field": (topic.get("field") or {}).get("display_name", ""),
                    "domain": (topic.get("domain") or {}).get("display_name", ""),
                    "n_authors": len(w["authorships"]),
                    "both_nits": len(own_on_paper) == 2,
                })
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(OUT, f"group{GROUP}_data.csv"), index=False)

    # faculty table: most frequent department per author, h-index from OpenAlex
    fac = (df.groupby(["institution", "author_id"])
             .agg(author=("author", "first"), papers=("openalex_id", "nunique"),
                  citations_in_period=("citations", "sum"),
                  department=("department", lambda s: s[s != ""].mode().iat[0] if (s != "").any() else ""))
             .reset_index())
    fac["h_index"] = fac["author_id"].map(lambda a: authors.get(a, {}).get("summary_stats", {}).get("h_index"))
    fac["total_works_career"] = fac["author_id"].map(lambda a: authors.get(a, {}).get("works_count"))
    fac.sort_values(["institution", "papers"], ascending=[True, False]).to_csv(
        os.path.join(OUT, "faculty.csv"), index=False)

    papers = df.drop_duplicates(["institution", "openalex_id"])
    print(f"rows: {len(df)}   unique papers: {df.openalex_id.nunique()}   authors: {df.author_id.nunique()}")
    print(papers.groupby("institution").size().rename("papers").to_string())
    print("type:", papers["type"].value_counts().to_dict())
    print("quartile:", papers["quartile"].replace("", "none").value_counts().to_dict())
    print("department filled:", round((df.department != "").mean() * 100, 1), "%")
    print("cites_indian_inst:", papers.cites_indian_inst.value_counts(dropna=False).to_dict())
    print("cited_by_indian_inst:", papers.cited_by_indian_inst.value_counts(dropna=False).to_dict())


if __name__ == "__main__":
    main()
