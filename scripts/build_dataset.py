"""Step 4: build data/group12_data.csv (one row per paper x NIT faculty member) and data/faculty.csv.

Uses only local files from steps 1-3 plus data/reference/{scimago_all.csv, core_conf.csv} and the faculty
roster and matches (fetch_faculty.py -> build_roster.py -> match_faculty.py).

Scope (agreed with the team):
  * Only faculty: a row exists for a regular faculty member (any rank) of a science / engineering / technology
    department whose affiliation on that paper is the NIT. PhD students and other staff are not rows.
  * Only science / engineering / technology papers: papers whose OpenAlex field is in EXCLUDED_FIELDS are left
    out, and so are papers without any such faculty author.
  * cites_indian_inst / cited_by_indian_inst follow flow.py: a paper that shares the institute through
    co-authorship (e.g. NIT Trichy + IIT Madras) does not count as a link to that other institute.
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
from flow import other_indian_partners
from names import affiliation_branch, block_keys, name_detail

GROUP = 12
OWN = {v: k for k, v in INSTITUTIONS.items()}
REF = os.path.join(ROOT, "data", "reference")
OUT = os.path.join(ROOT, "data")
# OpenAlex fields that are not science, engineering or technology (Decision Sciences, i.e. operations research,
# and the Health / Life Sciences fields are kept: at our NITs those papers are mostly engineering work)
EXCLUDED_FIELDS = {"Business, Management and Accounting", "Economics, Econometrics and Finance",
                   "Social Sciences", "Psychology", "Arts and Humanities"}


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

    # Indian works our papers reference, keyed by id -> set of Indian institution ids
    ref_insts = {}
    path = os.path.join(RAW, "links_refs.jsonl")
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            r = json.loads(line)
            ref_insts[r["id"]] = {i[0] for a in r["authors"] for i in a["inst"] if i[2] == "IN"}
    # our paper id -> Indian inst ids of each citing work (one set per citing work, so the flow rule can be
    # applied citation by citation)
    citer_insts = collections.defaultdict(dict)
    path = os.path.join(RAW, "links_citers.jsonl")
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            r = json.loads(line)
            insts = {i[0] for a in r["authors"] for i in a["inst"] if i[2] == "IN"}
            for w in r.get("cites_ours", []):
                if w != r["id"]:  # some OpenAlex records list the paper itself as a reference
                    citer_insts[w][r["id"]] = insts
    return fetched, ref_insts, citer_insts


# ---------- faculty (roster + OpenAlex matches) ----------
def load_faculty():
    """Regular science/engineering faculty, their accepted OpenAlex IDs, and a name index for authorships
    that have no OpenAlex ID."""
    roster = pd.read_csv(os.path.join(REF, "faculty_roster.csv"), dtype=str).fillna("")
    roster = roster[(roster.regular == "True") & (roster.science_engineering == "True")].set_index("faculty_id")
    links = pd.read_csv(os.path.join(REF, "faculty_openalex_map.csv"), dtype=str)
    by_author = {(r.institution, r.author_id): r.faculty_id for r in links.itertuples(index=False)
                 if r.faculty_id in roster.index}
    index = collections.defaultdict(set)
    for fid, p in roster.iterrows():
        for v in p.name_variants.split(";") + [p["name"]]:
            for k in block_keys(v):
                index[(p.institution, k)].add(fid)
    return roster, by_author, index


def faculty_by_name(name, inst, branch, roster, index):
    """Faculty id for an authorship without an OpenAlex ID: one clear name match in the same department."""
    cands = set()
    for k in block_keys(name):
        cands |= index.get((inst, k), set())
    hits = []
    for fid in cands:
        p = roster.loc[fid]
        if branch and p.branch != branch:
            continue
        score = max(name_detail(v, name)[0] for v in p.name_variants.split(";") + [p["name"]] if v)
        if score >= 2:
            hits.append(fid)
    return hits[0] if len(hits) == 1 else None


def nit_affiliation(a, inst_id):
    for aff in a.get("affiliations") or []:
        if any(short(i) == inst_id for i in aff.get("institution_ids") or []):
            return aff.get("raw_affiliation_string") or ""
    return ""


def load_journal_if():
    """OpenAlex 2-year mean citedness of each journal (the open stand-in for the impact factor)."""
    path = os.path.join(RAW, "sources.jsonl")
    if not os.path.exists(path):
        return {}
    return {r["id"]: r["if_2yr"] for r in map(json.loads, open(path, encoding="utf-8"))}


def load_impact():
    path = os.path.join(RAW, "works_impact.jsonl")
    if not os.path.exists(path):
        return {}
    return {r["id"]: r for r in map(json.loads, open(path, encoding="utf-8"))}


def h_index(citations):
    c = sorted(citations, reverse=True)
    return sum(1 for i, x in enumerate(c, 1) if x >= i)


def main():
    qtab = load_quartiles()
    core = load_core()
    fetched, ref_insts, citer_insts = load_links()
    roster, by_author, index = load_faculty()
    impact = load_impact()
    journal_if = load_journal_if()
    authors = {short(a["id"]): a for a in map(json.loads, open(os.path.join(RAW, "authors.jsonl"), encoding="utf-8"))}
    extra = os.path.join(RAW, "authors_extra.jsonl")
    if os.path.exists(extra):
        authors.update({a["id"]: a for a in map(json.loads, open(extra, encoding="utf-8"))})

    rows = []
    stats = collections.Counter()
    excluded_field, no_faculty, all_papers = set(), set(), set()
    for inst_name, inst_id in INSTITUTIONS.items():
        path = os.path.join(RAW, inst_name.replace(" ", "_") + "_works.jsonl")
        for line in open(path, encoding="utf-8"):
            w = json.loads(line)
            wid = short(w["id"])
            all_papers.add(wid)
            topic = w.get("primary_topic") or {}
            field = (topic.get("field") or {}).get("display_name", "")
            if field in EXCLUDED_FIELDS:
                excluded_field.add(wid)
                continue
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
            indian = {short(i["id"]) for a in w["authorships"] for i in a["institutions"]
                      if i.get("country_code") == "IN"}
            coinst = sorted({i["display_name"] for a in w["authorships"] for i in a["institutions"]
                             if i.get("country_code") == "IN" and short(i["id"]) not in OWN})
            # flags from this NIT's point of view; a linked paper that shares an institute with ours through
            # co-authorship is not a link to another institute (flow.py)
            if wid in fetched["refs"]:
                cites = any(other_indian_partners(inst_id, indian, ref_insts.get(short(r), set()))
                            for r in w["referenced_works"] if short(r) != wid)
            else:
                cites = None
            if wid in fetched["citers"]:
                cited_by = any(other_indian_partners(inst_id, indian, s) for s in citer_insts.get(wid, {}).values())
            else:
                cited_by = None
            imp = impact.get(wid, {})

            seen = set()
            for pos, a in enumerate(w["authorships"]):
                if not any(short(i["id"]) == inst_id for i in a["institutions"]):
                    continue
                aid = short(a["author"]["id"])
                fid = by_author.get((inst_name, aid)) if aid else None
                if fid is None and not aid:
                    # no OpenAlex author ID: accept one clear name match within the same department
                    name = a["author"].get("display_name") or a.get("raw_author_name") or ""
                    fid = faculty_by_name(name, inst_name, affiliation_branch(nit_affiliation(a, inst_id)),
                                          roster, index)
                    stats["rows_matched_by_name_without_openalex_id"] += fid is not None
                if fid is None:
                    stats["nit_authorships_not_faculty"] += 1
                    continue
                if fid in seen:
                    continue  # the same person listed twice on one paper
                seen.add(fid)
                p = roster.loc[fid]
                rows.append({
                    "group": GROUP,
                    "institution": inst_name,
                    "author": p["name"],
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
                    "department": p.branch,
                    "openalex_id": wid,
                    "field": field,
                    "domain": (topic.get("domain") or {}).get("display_name", ""),
                    "n_authors": len(w["authorships"]),
                    "both_nits": len(own_on_paper) == 2,
                    "faculty_id": fid,
                    "designation": p.designation,
                    "faculty_status": p.status,
                    "author_position": pos,
                    "subfield": (topic.get("subfield") or {}).get("display_name", ""),
                    "fwci": imp.get("fwci"),
                    "top10pct": imp.get("top_10pct"),
                    "journal_if_2yr": None if is_conf else journal_if.get(short(src.get("id"))),
                })
            if not seen:
                no_faculty.add((inst_name, wid))
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(OUT, f"group{GROUP}_data.csv"), index=False)

    # faculty table: one row per science/engineering faculty member, including those with no papers here
    links = pd.read_csv(os.path.join(REF, "faculty_openalex_map.csv"), dtype={"papers_at_nit": int})
    links = links[links.faculty_id.isin(roster.index)].sort_values(["papers_at_nit", "author_id"],
                                                                ascending=[False, True])
    ids = links.groupby("faculty_id").author_id.apply(list)
    papers = df.drop_duplicates(["faculty_id", "openalex_id"])
    g = papers.groupby("faculty_id")
    fac = pd.DataFrame({
        "papers": g.openalex_id.nunique(),
        "citations_in_period": g.citations.sum(),
        "h_index_2016_2026": g.citations.apply(h_index),
        "mean_fwci": g.fwci.mean(),
        "top_journal": g.journal_name.agg(lambda s: s[s != ""].mode().iat[0] if (s != "").any() else ""),
    }).reindex(roster.index)
    counts = ["papers", "citations_in_period", "h_index_2016_2026"]
    fac[counts] = fac[counts].fillna(0).astype(int)
    main_id = ids.map(lambda l: l[0]).reindex(roster.index)
    out = pd.DataFrame({
        "institution": roster.institution, "faculty_id": roster.index, "author_id": main_id,
        "author": roster["name"], "department": roster.branch, "designation": roster.designation,
        "status": roster.status, "first_seen": roster.first_seen, "last_seen": roster.last_seen,
        "papers": fac.papers, "citations_in_period": fac.citations_in_period,
        "h_index": main_id.map(lambda a: (authors.get(a) or {}).get("summary_stats", {}).get("h_index")),
        "h_index_2016_2026": fac.h_index_2016_2026,
        "total_works_career": main_id.map(lambda a: (authors.get(a) or {}).get("works_count")),
        "mean_fwci": pd.to_numeric(fac.mean_fwci).round(3), "top_journal": fac.top_journal.fillna(""),
        "openalex_ids": ids.reindex(roster.index).map(lambda l: ";".join(l) if isinstance(l, list) else ""),
    })
    out.sort_values(["institution", "papers"], ascending=[True, False]).to_csv(
        os.path.join(OUT, "faculty.csv"), index=False)

    paper_rows = df.drop_duplicates(["institution", "openalex_id"])
    print(f"raw papers: {len(all_papers)}   excluded by field: {len(excluded_field)}   "
          f"kept: {df.openalex_id.nunique()}")
    print(f"rows: {len(df)}   faculty with papers: {df.faculty_id.nunique()} of {len(roster)}   "
          f"(paper, NIT) pairs without a faculty author: {len(no_faculty)}")
    print(dict(stats))
    print(paper_rows.groupby("institution").size().rename("papers").to_string())
    print("type:", paper_rows["type"].value_counts().to_dict())
    print("quartile:", paper_rows["quartile"].replace("", "none").value_counts().to_dict())
    print("cites_indian_inst:", paper_rows.cites_indian_inst.value_counts(dropna=False).to_dict())
    print("cited_by_indian_inst:", paper_rows.cited_by_indian_inst.value_counts(dropna=False).to_dict())
    print("fwci available:", f"{paper_rows.fwci.notna().mean():.0%}")


if __name__ == "__main__":
    main()
