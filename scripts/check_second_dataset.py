"""Check two other teams' datasets before we use them in the South Indian NIT comparison (18 Nov 2026).

  python check_second_dataset.py      -> data/analysis/south/k_* tables, data/reference/second_dataset_corrections/<nit>.csv,
                                  cleaned tables data/analysis/south/second_dataset_<nit>_*.csv  (CHECKS.md explains them)

Group 13 (NIT Warangal, with NIT Rourkela) and Group 14 (NIT Calicut, with NIT Kurukshetra and NIT Durgapur) shared
their assignment files with us. They sit in data/raw/second_dataset/group13|group14/ (git-ignored) and are never edited.
Every check compares them with two sources of our own:
  - our OpenAlex download of the same NIT (fetch_peers.py -> data/raw/peers/), joined on DOI, and
  - the NIT's NIRF 2025 faculty list (each NIT's self-hosted data file, read by phase2_growth.nirf_faculty).
The seven checks: 1 split, 2 people vs NIRF, 3 papers vs OpenAlex, 4 names vs OpenAlex author IDs, 5 duplicates and
ranges, 6 networks, 7 big teams + a manual spot-check list. Every fix is one row in second_dataset_corrections/<nit>.csv
with its reason, and is applied here. DOIs missing from our download are looked up once in OpenAlex (cached in
data/raw/second_dataset/openalex_lookup.jsonl; needs OPENALEX_API_KEY only for that first lookup).
"""
import collections
import json
import os
import re
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import phase2_growth as P  # noqa: E402
from names import ascii_fold, block_keys, name_score  # noqa: E402

DATA, RAW = P.DATA, P.RAW
FR = os.path.join(RAW, "second_dataset")
OUT = os.path.join(DATA, "analysis", "south")
CORR = os.path.join(DATA, "reference", "second_dataset_corrections")
SEED = 42
FIRST, PARTIAL_YEAR = P.FIRST, P.PARTIAL_YEAR

# the two young NITs' NIRF 2025 files: the same kind of file as the other four, from each NIT's own website
P.NIRF.setdefault("NIT Puducherry", (
    "nitpy_overall_2025.pdf", "https://nitpy.ac.in/assets/docs/academics/nirf/2025/Overall.pdf"))
P.NIRF.setdefault("NIT Andhra Pradesh", (
    "nitap_overall_2025.pdf", "https://nitandhra.ac.in/main/nirf/NATIONAL%20INSTITUTE%20OF%20TECHNOLOGY,%20ANDHRA%20"
                              "PRADESH20250214-%20OVERALL.pdf"))
SOUTH = {"NIT Trichy": "I122964287", "NIT Surathkal": "I11880225", "NIT Warangal": "I121750182",
         "NIT Calicut": "I114845381", "NIT Puducherry": "I4400573194", "NIT Andhra Pradesh": "I4210153924"}
SECOND_DATASET = {"NIT Warangal": {"group": "group13", "label": "NIT Warangal"},
           "NIT Calicut": {"group": "group14", "label": "National Institute of Technology Calicut"}}
CORE = {"A*": "CORE A*", "A": "CORE A", "B": "CORE B", "C": "CORE C"}


# ---------------------------------------------------------------- shared helpers (south_nits.py uses them too)
def ndoi(x):
    x = (x or "").strip().lower()
    x = re.sub(r"^(https?://)?(dx\.)?doi\.org/", "", x)
    return x or None


def ntitle(t):
    return re.sub(r"[^a-z0-9]+", " ", ascii_fold(t or "").lower()).strip()


def nname(s):
    return " ".join(re.sub(r"[^a-z ]+", " ", ascii_fold(s or "").lower()).split())


def slug(nit):
    return nit.replace("NIT ", "").lower().replace(" ", "_")


def save(df, name):
    os.makedirs(OUT, exist_ok=True)
    df.to_csv(os.path.join(OUT, name), index=False)


def save_json(obj, name):
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, default=P.conv, ensure_ascii=False)


_NIRF = []


def nirf():
    """All six NIRF 2025 faculty tables (parsed once)."""
    if not _NIRF:
        _NIRF.append(P.nirf_faculty())
    return _NIRF[0]


def our_works(nit):
    return [w for w in P.peer_works(nit) if w["year"] and w["year"] >= FIRST]


def nirf_owner(nit, W, people):
    """The 17 Nov matching (phase2_growth nitfaculty): NIRF names -> OpenAlex author IDs that used this NIT's
    affiliation; an ID that fits two people equally well is dropped. Returns {author_id: row index in people}."""
    iid = SOUTH[nit]
    names_ = {}
    for w in W:
        for a in w["authors"]:
            if a["id"] and iid in a["inst"]:
                names_.setdefault(a["id"], a["name"] or "")
    index = collections.defaultdict(set)
    for aid, nm in names_.items():
        for k in block_keys(nm):
            index[k].add(aid)
    cand = collections.defaultdict(list)
    for pi, nm in enumerate(people["name"]):
        for aid in set().union(set(), *(index.get(k, set()) for k in block_keys(nm))):
            s = name_score(nm, names_[aid])
            if s >= 2:
                cand[aid].append((s, pi))
    owner = {}
    for aid, lst in cand.items():
        best = max(s for s, _ in lst)
        who = {pi for s, pi in lst if s == best}
        if len(who) == 1:
            owner[aid] = who.pop()
    return owner, names_


def openalex_lookup(dois):
    """DOIs missing from our download, looked up once (cached). Returns {doi: compact record or None}."""
    path = os.path.join(FR, "openalex_lookup.jsonl")
    cache = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                r = json.loads(line)
                if r.get("single") or r["work"] is not None:
                    cache[r["query"]] = r["work"]

    def compact_hit(w):
        return {"id": w["id"].rsplit("/", 1)[-1], "doi": ndoi(w.get("doi")), "year": w.get("publication_year"),
                "type": w.get("type"),
                "insts": sorted({i["id"].rsplit("/", 1)[-1] for a in w.get("authorships", [])
                                 for i in a.get("institutions", []) if i.get("id")}),
                "authors": [((a.get("author") or {}).get("display_name") or "") for a in w.get("authorships", [])]}

    todo = sorted(d for d in dois if d not in cache and "," not in d and "|" not in d)
    if todo:
        from fetch_works import get_url
        sel = "id,doi,publication_year,type,authorships"
        with open(path, "a", encoding="utf-8") as f:
            for i in range(0, len(todo), 40):
                batch = todo[i:i + 40]
                data, _ = get_url("https://api.openalex.org/works", {
                    "filter": "doi:" + "|".join(batch), "per_page": 50, "select": sel})
                found = {ndoi(w.get("doi")): compact_hit(w) for w in data["results"]}
                for d in batch:
                    hit = found.get(d)
                    if hit is None:
                        # OpenAlex merged this DOI into a work whose main DOI is another one: ask for it alone
                        one, _ = get_url("https://api.openalex.org/works", {"filter": "doi:" + d, "select": sel})
                        hit = compact_hit(one["results"][0]) if one["results"] else None
                    cache[d] = hit
                    f.write(json.dumps({"query": d, "work": hit, "single": True}, ensure_ascii=False) + "\n")
                print(f"  OpenAlex lookup {min(i + 40, len(todo))}/{len(todo)}", flush=True)
    return {d: cache.get(d) for d in dois}


FIELD_DOMAIN = {f: "Life Sciences" for f in [
    "Agricultural and Biological Sciences", "Biochemistry, Genetics and Molecular Biology",
    "Immunology and Microbiology", "Neuroscience", "Pharmacology, Toxicology and Pharmaceutics"]}
FIELD_DOMAIN.update({f: "Health Sciences" for f in ["Dentistry", "Health Professions", "Medicine", "Nursing",
                                                     "Veterinary"]})
FIELD_DOMAIN.update({f: "Social Sciences" for f in [
    "Arts and Humanities", "Business, Management and Accounting", "Decision Sciences",
    "Economics, Econometrics and Finance", "Psychology", "Social Sciences"]})


# ---------------------------------------------------------------- the checks for one NIT
def check_nit(nit):
    cfg = SECOND_DATASET[nit]
    iid = SOUTH[nit]
    g = cfg["group"]
    corr = []                                   # one dict per fix

    def fix(action, key, reason, check, value=""):
        corr.append({"institution": nit, "action": action, "key": key, "value": value, "reason": reason,
                     "check": check, "source": "rule"})

    # ---- 1. split and normalise
    raw = pd.read_csv(os.path.join(FR, g, f"{g}_data.csv"), dtype=str, keep_default_na=False)
    inst_counts = raw.institution.value_counts().to_dict()
    x = raw[raw.institution == cfg["label"]].copy().reset_index(drop=True)
    x["institution"] = nit
    x["doi_n"] = x.doi.map(ndoi)
    x["year"] = pd.to_numeric(x.year, errors="coerce")
    x["citations"] = pd.to_numeric(x.citations, errors="coerce")
    x["row"] = np.arange(len(x))
    group_dois = set(filter(None, map(ndoi, raw.doi)))
    k1 = {"rows_in_file": len(raw), "institutes_in_file": inst_counts, "rows_for_this_nit": len(x),
          "papers_for_this_nit": int(x.doi_n.nunique()), "rows_without_doi": int(x.doi_n.isna().sum()),
          "distinct_author_names": int(x.author.nunique())}

    # ---- 5. duplicates and ranges (done first: the other checks use the de-duplicated rows)
    dup = x[x.doi_n.notna() & x.duplicated(["doi_n", "author"])]
    for r in dup.itertuples():
        fix("drop_row", f"{r.doi_n}|{r.author}", "the same paper and author are listed twice", 5)
    x["nt"] = x.title.map(ntitle)
    papers = x[x.doi_n.notna()].drop_duplicates("doi_n")
    tdup = papers.groupby(["nt", "year"]).doi_n.nunique()
    tdup = tdup[(tdup > 1) & (tdup.index.get_level_values(0).str.len() > 20)]
    title_dup_examples = []
    for (nt, y) in tdup.index:
        grp = papers[(papers.nt == nt) & (papers.year == y)].sort_values(["citations", "doi_n"], ascending=[False, True])
        keep = grp.doi_n.iloc[0]
        for d in grp.doi_n.iloc[1:]:
            fix("drop_paper", d, "same title and year as another DOI (one paper with two DOIs); kept the more-cited "
                                 "one (in 'value')", 5, value=keep)
        if len(title_dup_examples) < 5:
            title_dup_examples.append(grp[["doi_n", "journal_name", "citations"]].values.tolist())
    bad_year = x[(x.year < FIRST) | (x.year > PARTIAL_YEAR) | x.year.isna()]
    for d in set(bad_year.doi_n.dropna()):
        fix("drop_paper", d, "publication year outside 2016-2026", 5)
    q = x.quartile.str.strip()
    q_norm = q.map(lambda v: v if v in ("Q1", "Q2", "Q3", "Q4") or v.startswith("CORE ") else CORE.get(v, ""))
    k5 = {"duplicate_paper_author_rows": len(dup), "papers_with_two_dois_same_title": int(len(tdup)),
          "title_duplicate_examples": title_dup_examples, "rows_outside_2016_2026": len(bad_year),
          "quartile_values": q.value_counts().to_dict(),
          "core_ranks_written_without_CORE_prefix": int(q.isin(list(CORE)).sum())}
    x["quartile_norm"] = q_norm

    # ---- 3. papers vs our OpenAlex download
    W = our_works(nit)
    ours = {}
    for w in W:
        d = ndoi(w.get("doi"))
        if d:
            ours.setdefault(d, w)
    theirs = set(x.doi_n.dropna())
    only_theirs = sorted(theirs - set(ours))
    look = openalex_lookup(only_theirs)
    reasons = collections.Counter()
    kept_extra = {}
    redoi_n = 0
    for d in only_theirs:
        w = look.get(d)
        main = (w or {}).get("doi")
        if w is not None and main and main != d and main in theirs:
            fix("drop_paper", d, "second DOI of a paper already in their file (OpenAlex keeps one work for both)", 3,
                value=main)
            reasons["second DOI of a paper already in their file"] += 1
            continue
        if w is not None and main and main != d:
            fix("redoi", d, "OpenAlex lists this paper under another DOI (in 'value')", 3, value=main)
            redoi_n += 1
        if w is None:
            fix("drop_paper", d, "DOI not found in OpenAlex", 3)
            reasons["DOI not found in OpenAlex"] += 1
        elif iid not in w["insts"]:
            fix("drop_paper", d, f"OpenAlex does not list {nit} on this paper", 3)
            reasons["OpenAlex does not list this NIT on the paper"] += 1
        elif w["type"] not in ("article", "review", "conference-paper"):
            fix("drop_paper", d, f"OpenAlex type '{w['type']}' is outside the article/review/conference-paper scope "
                                 "used for every NIT", 3)
            reasons[f"type outside our scope ({w['type']})"] += 1
        elif not (w["year"] and FIRST <= w["year"] <= PARTIAL_YEAR):
            fix("drop_paper", d, f"OpenAlex year {w['year']} is outside 2016-2026", 3)
            reasons["OpenAlex year outside 2016-2026"] += 1
        else:
            reasons["real paper of this NIT that our download missed (kept)"] += 1
            kept_extra[main or d] = w
    both = theirs & set(ours)
    pp = x[x.doi_n.isin(both)].drop_duplicates("doi_n")
    oy = pp.doi_n.map(lambda d: ours[d]["year"])
    otype = pp.doi_n.map(lambda d: "conference" if (ours[d]["type"] == "conference-paper"
                                                    or ours[d]["source_type"] == "conference") else "journal")
    oc = pp.doi_n.map(lambda d: ours[d]["cited_by_count"] or 0)
    drift = (pp.citations - oc)
    only_ours = [ours[d] for d in sorted(set(ours) - theirs)]
    k3 = {"their_papers": len(theirs), "our_papers_with_doi": len(ours), "in_both": len(both),
          "only_in_theirs": len(only_theirs), "only_in_theirs_why": dict(reasons),
          "only_in_theirs_doi_updated_to_openalex_main_doi": redoi_n,
          "only_in_ours": len(only_ours),
          "only_in_ours_by_year": dict(collections.Counter(w["year"] for w in only_ours)),
          "only_in_ours_by_type": dict(collections.Counter(w["type"] for w in only_ours)),
          "year_agrees_pct": 100 * float((pp.year.values == oy.values).mean()),
          "type_agrees_pct": 100 * float((pp.type.values == otype.values).mean()),
          "citations_theirs_minus_ours_median": float(drift.median()),
          "citations_theirs_higher_pct": 100 * float((drift > 0).mean()),
          "citations_off_by_more_than_10_pct": 100 * float(((drift.abs() > 10)).mean())}

    # ---- 4. names vs OpenAlex author IDs (through each paper's authorships in our download)
    def resolve(r):
        w = ours.get(r.doi_n) if r.doi_n else None
        if w is None:
            return None, "not_checkable", 0
        # authorships without an author ID (OpenAlex has not processed them yet) still count as "on the paper"
        auth = [(a["id"], a["name"] or "", iid in a["inst"]) for a in w["authors"]]
        nm = nname(r.author)
        exact = [a for a in auth if nname(a[1]) == nm]
        weak = False
        if not exact:
            sc = [(name_score(r.author, a[1]), a) for a in auth]
            best = max([s for s, _ in sc], default=0)
            exact = [a for s, a in sc if s == best and s >= 2]
            if not exact and best == 1:
                # one weak point only ('G. Unnikrishnan' vs 'Gopalakrishna Panicker Unnikrishnan', 'Rohinikumar'),
                # accepted when exactly one author on the paper fits that well
                ones = [a for s, a in sc if s == 1]
                if len(ones) == 1:
                    exact, weak = ones, True
        if len({a[0] for a in exact}) == 1:
            a = exact[0]
            if a[0] is None:
                return None, "on_paper_no_author_id", len(w["authors"])
            return a[0], ("this_nit" if a[2] else "other_affiliation") + ("_weak_name" if weak else ""), \
                len(w["authors"])
        if len(exact) > 1:
            nit_ones = [a for a in exact if a[2]]
            if len({a[0] for a in nit_ones}) == 1:
                return nit_ones[0][0], "this_nit", len(w["authors"])
            return None, "ambiguous_on_paper", len(w["authors"])
        return None, "not_on_paper", len(w["authors"])

    res = [resolve(r) for r in x.itertuples()]
    x["author_id"] = [a for a, _, _ in res]
    x["id_status"] = [s for _, s, _ in res]
    x["n_authors_oa"] = [n for _, _, n in res]
    for r in x[(x.id_status == "not_on_paper") & (x.n_authors_oa < 100)].itertuples():
        fix("drop_row", f"{r.doi_n}|{r.author}", "OpenAlex does not list this author on the paper", 4)
    ok = x[x.author_id.notna() & x.id_status.isin(["this_nit", "this_nit_weak_name"])]
    name_ids = ok.groupby("author").author_id.nunique()
    id_names = ok.groupby("author_id").author.agg(lambda s: s.value_counts().index.tolist())
    canon = {}
    for aid, names_ in id_names.items():
        if len(names_) > 1:
            for nm in names_[1:]:
                fix("rename", f"{aid}|{nm}", "another spelling of the same OpenAlex author ID", 4, value=names_[0])
        canon[aid] = names_[0]

    # NIRF faculty -> OpenAlex IDs (same matching as 17 Nov) and the "two people in one ID" signal
    nf = nirf()
    people = nf[(nf.institution == nit) & nf.current].reset_index(drop=True)
    owner, oa_names = nirf_owner(nit, W, people)
    by_aid = collections.defaultdict(list)
    for w in W:
        for a in w["authors"]:
            if a["id"] in owner and iid in a["inst"]:
                by_aid[a["id"]].append(w)
    two_people = []
    for aid, ws in by_aid.items():
        if len(ws) < 10:
            continue
        fc = collections.Counter(w["field"] for w in ws if w["field"])
        if len(fc) < 2:
            continue
        (f1, n1), (f2, n2) = fc.most_common(2)
        if min(n1, n2) / len(ws) < 0.25:
            continue
        co = {f: {b["id"] for w in ws if w["field"] == f for b in w["authors"] if b["id"] and b["id"] != aid}
              for f in (f1, f2)}
        if not (co[f1] & co[f2]):
            two_people.append({"institution": nit, "openalex_author_id": aid, "openalex_name": oa_names.get(aid),
                               "nirf_name": people["name"][owner[aid]], "papers": len(ws),
                               "field_1": f1, "papers_1": n1, "field_2": f2, "papers_2": n2,
                               "shared_coauthors": 0})
    k4 = {"rows_checkable": int((x.id_status != "not_checkable").sum()),
          "id_status": x.id_status.value_counts().to_dict(),
          "names_with_several_ids": int((name_ids > 1).sum()),
          "names_with_several_ids_examples": name_ids[name_ids > 1].sort_values(ascending=False).head(8).to_dict(),
          "ids_with_several_names": int((id_names.map(len) > 1).sum()),
          "ids_with_several_names_examples": [v for v in id_names[id_names.map(len) > 1].head(8)],
          "nirf_ids_that_look_like_two_people": len(two_people)}

    # ---- 2. people vs the NIRF 2025 list
    fnames = sorted(set(x.author) - {""})
    index = collections.defaultdict(set)
    for nm in fnames:
        for k in block_keys(nm):
            index[k].add(nm)
    matched, missing = {}, []
    for pi, nm in enumerate(people["name"]):
        cands = set().union(set(), *(index.get(k, set()) for k in block_keys(nm)))
        sc = [(name_score(nm, c), c) for c in cands]
        best = max([s for s, _ in sc], default=0)
        if best >= 2:
            matched[pi] = [c for s, c in sc if s == best]
        else:
            missing.append(nm)
    ids_in_theirs = set(ok.author_id)
    found_by_id = {owner[a] for a in ids_in_theirs if a in owner}
    junk_re = re.compile(r"^(dr|prof|mr|mrs|ms|sri|smt)\.?$|\d|department|institute|university|college|national",
                         re.I)
    junk = [nm for nm in fnames if junk_re.search(nm.strip()) or len(nm.split()) == 1]
    for nm in junk:
        if junk_re.search(nm.strip()):
            fix("drop_name", nm, "not a person's name (title, number or organisation)", 2)
    k2 = {"nirf_current_faculty": len(people), "nirf_matched_by_name_in_their_file": len(matched),
          "nirf_matched_pct": 100 * len(matched) / len(people),
          "nirf_found_through_openalex_ids": len(found_by_id),
          "nirf_matched_to_openalex_ids_in_our_download": len(set(owner.values())),
          "nirf_missing_from_their_file": len(missing),
          "their_names_not_on_nirf_list": len(fnames) - len({c for v in matched.values() for c in v}),
          "names_in_capitals_only": int(sum(nm.isupper() for nm in fnames)),
          "single_word_or_non_person_names": len(junk), "junk_examples": junk[:12]}

    # ---- apply the fixes
    corr_df = pd.DataFrame(corr)
    path = os.path.join(CORR, f"{slug(nit)}.csv")
    if os.path.exists(path):                    # keep any fixes typed in by hand
        old = pd.read_csv(path, dtype=str, keep_default_na=False)
        corr_df = pd.concat([corr_df, old[old.source == "manual"]], ignore_index=True)
    os.makedirs(CORR, exist_ok=True)
    corr_df.to_csv(path, index=False)
    twice = "the same paper and author are listed twice"
    drop_rows = set(corr_df[(corr_df.action == "drop_row") & (corr_df.reason != twice)].key)
    drop_papers = set(corr_df[corr_df.action == "drop_paper"].key)
    drop_names = set(corr_df[corr_df.action == "drop_name"].key)
    first_copy = ~(x.doi_n.notna() & x.duplicated(["doi_n", "author"]))     # the 'listed twice' fix keeps one copy
    keep = (first_copy & ~x.doi_n.isin(drop_papers) & ~x.author.isin(drop_names)
            & ~(x.doi_n.fillna("") + "|" + x.author).isin(drop_rows))
    clean = x[keep].copy()
    redoi = dict(zip(corr_df[corr_df.action == "redoi"].key, corr_df[corr_df.action == "redoi"].value))
    clean["doi_n"] = clean.doi_n.map(lambda d: redoi.get(d, d))
    clean = clean[~(clean.doi_n.notna() & clean.duplicated(["doi_n", "author"]))]
    clean["author_clean"] = [canon.get(a, n) for a, n in zip(clean.author_id, clean.author)]
    owner_name = {aid: people["name"][pi] for aid, pi in owner.items()}
    clean["nirf_faculty"] = clean.author_id.isin(set(owner))

    # ---- 6. networks
    an = pd.read_csv(os.path.join(FR, g, "authorship_network.csv"), dtype=str, keep_default_na=False)
    lab = cfg["label"]
    mine = an[(an.inst_a == lab) | (an.inst_b == lab)]
    same = mine[(mine.inst_a == lab) & (mine.inst_b == lab)]
    an_doi = mine.paper_doi.map(ndoi)
    name_to_fac = {}
    for pi, cands in matched.items():
        for c in cands:
            name_to_fac.setdefault(c, set()).add(pi)
    fac_pairs_theirs = set()
    for r in same.itertuples():
        fa, fb = name_to_fac.get(r.author_a, set()), name_to_fac.get(r.author_b, set())
        if len(fa) == 1 and len(fb) == 1 and fa != fb:
            fac_pairs_theirs.add(tuple(sorted((next(iter(fa)), next(iter(fb))))))
    fac_pairs_ours = set()
    for w in W:
        if len(w["authors"]) > P.MAX_TEAM:
            continue
        fs = sorted({owner[a["id"]] for a in w["authors"] if a["id"] in owner and iid in a["inst"]})
        fac_pairs_ours.update((fs[i], fs[j]) for i in range(len(fs)) for j in range(i + 1, len(fs)))
    cn = pd.read_csv(os.path.join(FR, g, "citation_network.csv"), dtype=str, keep_default_na=False)
    cmine = cn[cn.source_inst.str.contains(lab, regex=False) | cn.target_inst.str.contains(lab, regex=False)]
    neither = ~(cmine.source_doi.map(ndoi).isin(group_dois) | cmine.target_doi.map(ndoi).isin(group_dois))
    ic = pd.read_csv(os.path.join(FR, g, "indian_connections.csv"), dtype=str, keep_default_na=False)
    ic = ic[ic.your_inst == lab].copy()
    ic["shared_papers"] = pd.to_numeric(ic.shared_papers)
    per_partner = collections.Counter()
    for d, insts in x.drop_duplicates("doi_n")[["doi_n", "coauthor_institutes"]].itertuples(index=False):
        for p in {s.strip() for s in insts.split(";") if s.strip()}:
            per_partner[p] += 1
    top = ic.nlargest(30, "shared_papers")
    recount = top.partner_inst.map(lambda p: per_partner.get(p, 0))
    k6 = {"coauthor_rows_touching_nit": len(mine), "coauthor_rows_both_this_nit": len(same),
          "coauthor_rows_with_outside_partner": len(mine) - len(same),
          "coauthor_self_loops": int((mine.author_a == mine.author_b).sum()),
          "coauthor_duplicate_rows": int(mine.duplicated().sum()),
          "coauthor_rows_paper_not_in_their_data": int((~an_doi.isin(group_dois)).sum()),
          "faculty_pairs_theirs_by_name": len(fac_pairs_theirs), "faculty_pairs_ours_by_id": len(fac_pairs_ours),
          "faculty_pairs_in_both": len(fac_pairs_theirs & fac_pairs_ours),
          "citation_rows_touching_nit": len(cmine), "citation_rows_with_no_dataset_paper": int(neither.sum()),
          "citation_self_loops": int((cmine.source_doi == cmine.target_doi).sum()),
          "partners_listed": len(ic),
          "top30_partners_shared_papers_recount_equal_pct": 100 * float((recount.values == top.shared_papers.values).mean()),
          "top30_partners_median_abs_difference": float(np.median(np.abs(recount.values - top.shared_papers.values)))}

    # ---- 7. big teams and a manual spot-check list
    na = pd.Series({d: len(ours[d]["authors"]) for d in theirs & set(ours)})
    rng = np.random.default_rng(SEED)
    fac_aids = sorted(set(owner) & ids_in_theirs)
    pick = rng.choice(len(fac_aids), size=min(20, len(fac_aids)), replace=False)
    word = {"NIT Warangal": "Warangal", "NIT Calicut": "Calicut"}[nit]
    spot = []
    for i in sorted(pick):
        aid = fac_aids[i]
        spot.append({"institution": nit, "nirf_name": owner_name[aid], "nirf_rank": people["rank"][owner[aid]],
                     "openalex_author_id": aid, "openalex_name": oa_names.get(aid, ""),
                     "names_in_their_file": "; ".join(sorted(set(ok[ok.author_id == aid].author))),
                     "papers_in_their_file": int(ok[ok.author_id == aid].doi_n.nunique()),
                     "papers_in_our_download": len(by_aid.get(aid, [])),
                     "google_scholar_search": "https://scholar.google.com/citations?view_op=search_authors&mauthors="
                                              + owner_name[aid].replace(" ", "+") + "+NIT+" + word,
                     "checked_by_hand": "", "note": ""})
    k7 = {"papers_with_100_plus_authors": int((na >= 100).sum()), "papers_with_50_plus_authors": int((na >= 50).sum()),
          "spot_check_people": len(spot)}

    # faculty papers they miss (coverage of the people that matter for the faculty network)
    fac_dois = {ndoi(w["doi"]) for aid in owner for w in by_aid.get(aid, []) if w.get("doi")}
    k3["faculty_papers_in_our_download"] = len(fac_dois)
    k3["faculty_papers_missing_from_theirs"] = len(fac_dois - theirs)
    k3["faculty_paper_coverage_pct"] = 100 * (1 - len(fac_dois - theirs) / max(1, len(fac_dois)))

    # ---- cleaned tables
    papers_c = clean[clean.doi_n.notna()].drop_duplicates("doi_n")
    pc = pd.DataFrame({
        "doi": papers_c.doi_n, "year": papers_c.year.astype(int), "type": papers_c.type,
        "journal_name": papers_c.journal_name, "quartile": papers_c.quartile_norm,
        "citations_their_file": papers_c.citations,
        "citations_openalex_our_download": papers_c.doi_n.map(lambda d: (ours.get(d) or {}).get("cited_by_count")),
        "fwci": papers_c.doi_n.map(lambda d: (ours.get(d) or {}).get("fwci")),
        "field": papers_c.doi_n.map(lambda d: (ours.get(d) or {}).get("field")),
        "n_authors_openalex": papers_c.doi_n.map(lambda d: len((ours.get(d) or {}).get("authors", [])) or None),
        "verified_in_openalex": papers_c.doi_n.map(lambda d: d in ours or d in kept_extra)})
    fr = clean[clean.nirf_faculty].drop_duplicates(["doi_n", "author_id"])
    fac_rows = pd.DataFrame({"doi": fr.doi_n, "year": fr.year.astype(int), "author": fr.author_clean,
                             "openalex_author_id": fr.author_id,
                             "nirf_name": fr.author_id.map(owner_name)})
    save(pc, f"second_dataset_{slug(nit)}_papers.csv")
    save(fac_rows, f"second_dataset_{slug(nit)}_faculty_rows.csv")
    kept = {"rows_before": len(x), "rows_after": len(clean), "papers_before": len(theirs),
            "papers_after": int(papers_c.doi_n.nunique()),
            "fixes": corr_df.groupby(["action", "check"]).size().reset_index(name="n").to_dict("records")}
    print(f"== {nit}: {kept['rows_before']} -> {kept['rows_after']} rows, "
          f"{kept['papers_before']} -> {kept['papers_after']} papers")
    return ({"institution": nit, "group": g, "split": k1, "people_vs_nirf": k2, "papers_vs_openalex": k3,
             "names_vs_ids": k4, "duplicates_ranges": k5, "networks": k6, "big_teams_spot_check": k7,
             "after_fixes": kept}, spot, two_people)


def main():
    out, spots, twos = [], [], []
    for nit in SECOND_DATASET:
        k, spot, two = check_nit(nit)
        out.append(k)
        spots += spot
        twos += two
    save(pd.DataFrame(spots), "k_spot_check.csv")
    save(pd.DataFrame(twos), "k_ids_that_look_like_two_people.csv")
    corr = pd.concat([pd.read_csv(os.path.join(CORR, f"{slug(n)}.csv"), dtype=str, keep_default_na=False)
                      for n in SECOND_DATASET])
    save(corr.groupby(["institution", "check", "action", "reason"]).size().reset_index(name="rows")
         .sort_values(["institution", "check", "rows"], ascending=[True, True, False]), "k_fixes_summary.csv")
    save_json(out, "k_checks_summary.json")
    print(json.dumps(out, indent=1, default=P.conv, ensure_ascii=False)[:12000])


if __name__ == "__main__":
    main()
