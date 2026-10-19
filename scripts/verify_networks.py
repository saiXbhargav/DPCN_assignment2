"""Independent checks for the dataset and the Task 2 files. Recomputes key numbers by a different route
than build_dataset.py / build_networks.py (mostly from group12_data.csv and the raw files) and compares.
Prints PASS/FAIL per check; exits with status 1 if anything fails.
"""
import collections
import json
import math
import os
import sys

import pandas as pd

from fetch_works import INSTITUTIONS, RAW, ROOT

DATA = os.path.join(ROOT, "data")
REF = os.path.join(DATA, "reference")
OWN = {v: k for k, v in INSTITUTIONS.items()}
IIT_MADRAS = "I24676775"
EXCLUDED_FIELDS = {"Business, Management and Accounting", "Economics, Econometrics and Finance",
                   "Social Sciences", "Psychology", "Arts and Humanities"}
failures = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""))
    if not ok:
        failures.append(name)


def short(u):
    return (u or "").rsplit("/", 1)[-1]


ds = pd.read_csv(os.path.join(DATA, "group12_data.csv"), low_memory=False)
papers = ds.drop_duplicates("openalex_id").set_index("openalex_id")
corpus = set(papers.index)
works = {}
for name in INSTITUTIONS:
    for line in open(os.path.join(RAW, name.replace(" ", "_") + "_works.jsonl"), encoding="utf-8"):
        w = json.loads(line)
        works[short(w["id"])] = w
summary = json.load(open(os.path.join(DATA, "network_metrics", "network_summary.json")))

# ------------------------------------------------------------------ dataset scope (faculty, subjects)
roster = pd.read_csv(os.path.join(REF, "faculty_roster.csv"), dtype=str).set_index("faculty_id")
in_scope = set(roster.index[(roster.regular == "True") & (roster.science_engineering == "True")])
check("dataset: every row is a regular science/engineering faculty member", ds.faculty_id.isin(in_scope).all(),
      f"{(~ds.faculty_id.isin(in_scope)).sum()} rows outside")
check("dataset: no paper from an excluded field", not papers.field.isin(EXCLUDED_FIELDS).any())
check("dataset: one row per (paper, institution, faculty member)",
      not ds.duplicated(["openalex_id", "institution", "faculty_id"]).any())
pos_ok = all(any(short(i["id"]) == next(k for k, v in OWN.items() if v == inst) for i in
                 works[p]["authorships"][int(pos)]["institutions"])
             for p, inst, pos in zip(ds.openalex_id, ds.institution, ds.author_position))
check("dataset: each row's author is affiliated with that NIT on that paper", pos_ok)

# ------------------------------------------------------------------ citation network
cit = pd.read_csv(os.path.join(DATA, "citation_network.csv"), low_memory=False)
req = ["source_doi", "target_doi", "source_inst", "target_inst", "year"]
check("citation: required columns first", list(cit.columns[:5]) == req)
check("citation: no duplicate edges", not cit.duplicated(["source_id", "target_id"]).any())
check("citation: no self-loops", (cit.source_id != cit.target_id).all())

internal = cit[cit.edge_type == "internal"]
expected_internal = {(w, short(r)) for w in corpus for r in works[w]["referenced_works"]
                     if short(r) in corpus and short(r) != w}
check("citation: internal edges = our papers' references to our papers",
      set(zip(internal.source_id, internal.target_id)) == expected_internal,
      f"{len(internal)} vs {len(expected_internal)}")

outs = cit[cit.edge_type.isin(["out_indian", "out_shared_inst"])]
ins = cit[cit.edge_type.isin(["in_indian", "in_shared_inst"])]
outi, ini = cit[cit.edge_type == "out_indian"], cit[cit.edge_type == "in_indian"]
check("citation: out_* = ours -> outside", outs.source_id.isin(corpus).all() and not outs.target_id.isin(corpus).any())
check("citation: in_* = outside -> ours", ins.target_id.isin(corpus).all() and not ins.source_id.isin(corpus).any())
check("citation: every out_* target is a real reference of its source",
      all(f"https://openalex.org/{t}" in works[s]["referenced_works"] for s, t in zip(outs.source_id, outs.target_id)))

src_ours = cit[cit.source_id.isin(corpus)]
check("citation: year = citing paper's year",
      (src_ours.year.values == papers.loc[src_ours.source_id, "year"].values).all())
check("citation: source DOI matches dataset",
      (src_ours.source_doi.fillna("").values == papers.loc[src_ours.source_id, "doi"].fillna("").values).all())

# Indian institutions of every paper we know about (ours from the raw works, outside ones from the link files)
insts = {w: {short(i["id"]) for a in x["authorships"] for i in a["institutions"] if i.get("country_code") == "IN"}
         for w, x in works.items()}
citer_of = collections.defaultdict(set)
for fname in ("links_refs.jsonl", "links_citers.jsonl"):
    for line in open(os.path.join(RAW, fname), encoding="utf-8"):
        r = json.loads(line)
        insts.setdefault(r["id"], {i[0] for a in r["authors"] for i in a["inst"] if i[2] == "IN"})
        for t in r.get("cites_ours", []):
            if t != r["id"]:
                citer_of[t].add(r["id"])


def outside_credit(n, mine, other):
    """Written separately from flow.py on purpose: institutes other than the two NITs that get credit."""
    if n in other:
        return set()
    return {y for y in other if y not in OWN and y not in mine}


# the two flags, recomputed row by row from the raw link files
nid = {v: k for k, v in OWN.items()}
exp_cites, exp_cited = [], []
for p, inst in zip(ds.openalex_id, ds.institution):
    n = nid[inst]
    exp_cites.append(any(outside_credit(n, insts[p], insts.get(short(r), set()))
                         for r in works[p]["referenced_works"] if short(r) != p and short(r) in insts))
    exp_cited.append(any(outside_credit(n, insts[p], insts[c]) for c in citer_of.get(p, ())))
check("dataset: cites_indian_inst matches the co-authorship rule on every row",
      (ds.cites_indian_inst.astype(bool).values == exp_cites).all(),
      f"{(ds.cites_indian_inst.astype(bool).values != exp_cites).sum()} rows differ")
check("dataset: cited_by_indian_inst matches the co-authorship rule on every row",
      (ds.cited_by_indian_inst.astype(bool).values == exp_cited).all(),
      f"{(ds.cited_by_indian_inst.astype(bool).values != exp_cited).sum()} rows differ")

cites_true = set(ds.openalex_id[ds.cites_indian_inst == True])
cited_true = set(ds.openalex_id[ds.cited_by_indian_inst == True])
check("citation: papers with out_indian edges have cites_indian_inst=True", set(outi.source_id) <= cites_true,
      f"{len(set(outi.source_id) - cites_true)} violations")
check("citation: papers with in_indian edges have cited_by_indian_inst=True", set(ini.target_id) <= cited_true,
      f"{len(set(ini.target_id) - cited_true)} violations")


own_on = ds.groupby("openalex_id").institution.agg(lambda s: {nid[i] for i in s}).to_dict()


def own_ids(p):
    return own_on.get(p, set())


def credited(ours, other):
    return any(outside_credit(n, insts[ours], insts[other]) for n in own_ids(ours))


check("citation: out_indian edges give credit to an outside institute, out_shared_inst edges give none",
      all(credited(s, t) for s, t in zip(outi.source_id, outi.target_id)) and
      not any(credited(s, t) for s, t in zip(cit.source_id[cit.edge_type == "out_shared_inst"],
                                              cit.target_id[cit.edge_type == "out_shared_inst"])))
check("citation: in_indian edges give credit to an outside institute, in_shared_inst edges give none",
      all(credited(t, s) for s, t in zip(ini.source_id, ini.target_id)) and
      not any(credited(t, s) for s, t in zip(cit.source_id[cit.edge_type == "in_shared_inst"],
                                              cit.target_id[cit.edge_type == "in_shared_inst"])))

pm = pd.read_csv(os.path.join(DATA, "network_metrics", "citation_paper_metrics.csv"))
check("citation metrics: one row per paper", len(pm) == len(corpus) and set(pm.openalex_id) == corpus)
check("citation metrics: PageRank sums to 1", math.isclose(pm.pagerank.sum(), 1.0, rel_tol=1e-6), f"{pm.pagerank.sum():.8f}")
indeg = internal.target_id.value_counts()
check("citation metrics: in-degree matches edge list",
      (pm.set_index("openalex_id").in_degree_internal == indeg.reindex(pm.openalex_id).fillna(0).values).all())
check("citation metrics: internal in-degree <= total citations", (pm.in_degree_internal <= pm.citations_total).all(),
      f"{(pm.in_degree_internal > pm.citations_total).sum()} papers exceed")

# ------------------------------------------------------------------ authorship network
au = pd.read_csv(os.path.join(DATA, "authorship_network.csv"), low_memory=False)
req = ["author_a", "author_b", "paper_doi", "inst_a", "inst_b", "year"]
check("authorship: required columns first", list(au.columns[:6]) == req)
check("authorship: no self pairs", (au.author_a_id != au.author_b_id).all())
check("authorship: pairs stored in sorted order (undirected)", (au.author_a_id < au.author_b_id).all())
check("authorship: no duplicate (pair, paper)", not au.duplicated(["author_a_id", "author_b_id", "paper_id"]).any())
nit_side = lambda s: s.str.split(";").apply(lambda xs: all(x in OWN.values() for x in xs))
check("authorship: every pair has a NIT author", (nit_side(au.inst_a) | nit_side(au.inst_b)).all())
nit_ids = set(au.author_a_id[nit_side(au.inst_a)]) | set(au.author_b_id[nit_side(au.inst_b)])
check("authorship: every NIT node is a faculty member", nit_ids <= in_scope, f"{len(nit_ids - in_scope)} not faculty")
cap = summary.get("max_authors") or 0
big = {w for w in corpus if cap and len(works[w]["authorships"]) > cap}
check(f"authorship: papers with >{cap} authors excluded", not au.paper_id.isin(big).any(), f"{len(big)} such papers")

# expected pair count per paper: C(k,2) - C(outside,2), k = NIT faculty + distinct outside authors with an id
fac_on = collections.defaultdict(set)
for p, pos in zip(ds.openalex_id, ds.author_position):
    fac_on[p].add(pos)  # by author position: a faculty member listed with both NITs is still one person
exp = {}
for wid in corpus - big:
    ext = set()
    for a in works[wid]["authorships"]:
        aid = short(a["author"]["id"])
        if aid and not any(short(i["id"]) in OWN for i in a["institutions"]):
            ext.add(aid)
    k = len(fac_on[wid]) + len(ext)
    n = k * (k - 1) // 2 - len(ext) * (len(ext) - 1) // 2
    if n:
        exp[wid] = n
got = au.paper_id.value_counts().to_dict()
check("authorship: pair count per paper = C(k,2) - C(outside,2)", got == exp,
      f"{sum(1 for p in exp if got.get(p) != exp[p])} papers differ")
check("authorship: year matches paper", (au.year.values == papers.loc[au.paper_id, "year"].values).all())

am_path = os.path.join(DATA, "network_metrics", "author_metrics.csv")
if os.path.exists(am_path):
    am = pd.read_csv(am_path)
    check("author metrics: centralities within [0,1]",
          am.degree_centrality.between(0, 1).all() and am.betweenness_centrality.between(0, 1).all())
    nit_pairs = au[au.edge_category.isin(["same_nit", "nit_nit"])]
    nbrs = collections.defaultdict(set)
    for a, b in zip(nit_pairs.author_a_id, nit_pairs.author_b_id):
        nbrs[a].add(b)
        nbrs[b].add(a)
    check("author metrics: degree = distinct NIT co-authors",
          all(len(nbrs[r.author_id]) == r.degree for r in am.itertuples()))
    n = len(am)
    check("author metrics: degree_centrality = degree/(n-1)",
          all(math.isclose(r.degree_centrality, r.degree / (n - 1)) for r in am.itertuples()))
    check("author metrics: nodes are faculty ids", set(am.author_id) <= in_scope)

# ------------------------------------------------------------------ indian connections
ic = pd.read_csv(os.path.join(DATA, "indian_connections.csv"))
req = ["your_inst", "partner_inst", "shared_papers", "total_citations"]
check("connections: required columns first", list(ic.columns[:4]) == req)
check("connections: no duplicate (your_inst, partner_id)", not ic.duplicated(["your_inst", "partner_id"]).any())
check("connections: partner is never the same institution", (ic.your_inst != ic.partner_inst).all())

# shared papers from the coauthor_institutes column of group12_data.csv (names, other NIT excluded there)
pp = ds.drop_duplicates(["institution", "openalex_id"])
exp_sh, exp_cit = collections.Counter(), collections.Counter()
for inst, co, c in zip(pp.institution, pp.coauthor_institutes.fillna(""), pp.citations):
    for partner in set(filter(None, co.split(";"))):
        exp_sh[(inst, partner)] += 1
        exp_cit[(inst, partner)] += c
non_nit = ic[~ic.partner_inst.isin(OWN.values())].groupby(["your_inst", "partner_inst"])
# name-level comparison; where two institutions share a display name the file has 2 rows -> compare sums of papers
got_sh = non_nit.shared_papers.sum()
mism = [k for k, v in exp_sh.items() if got_sh.get(k, 0) < v]
check("connections: shared_papers matches coauthor_institutes column", not mism, f"{len(mism)} mismatches")
got_cit = non_nit.total_citations.sum()
same_name_ids = ic.groupby(["your_inst", "partner_inst"]).partner_id.nunique()
mism = [k for k, v in exp_cit.items() if same_name_ids.get(k, 1) == 1 and got_cit.get(k, 0) != v]
check("connections: total_citations = summed citations of shared papers", not mism, f"{len(mism)} mismatches")

# in/out-flow recomputed edge by edge with the co-authorship rule: no credit when the other paper also has
# authors from our institution, and none for institutes that are already co-authors on our paper
flow_in, flow_out = collections.Counter(), collections.Counter()
for s, t in zip(cit.source_id, cit.target_id):
    for mine_id, mine in OWN.items():
        if mine_id in own_ids(t) and mine_id not in insts[s]:
            for p in insts[s] - insts[t]:
                flow_in[(mine, p)] += 1
        if mine_id in own_ids(s) and mine_id not in insts[t]:
            for p in insts[t] - insts[s]:
                flow_out[(mine, p)] += 1
g = ic.set_index(["your_inst", "partner_id"])
check("connections: cites_from_partner matches recomputed in-flow (every row)",
      all(g.cites_from_partner.get(k, 0) == v for k, v in flow_in.items()) and g.cites_from_partner.sum() == sum(flow_in.values()),
      f"file {g.cites_from_partner.sum()} vs recomputed {sum(flow_in.values())}")
check("connections: cites_to_partner matches recomputed out-flow (every row)",
      all(g.cites_to_partner.get(k, 0) == v for k, v in flow_out.items()) and g.cites_to_partner.sum() == sum(flow_out.values()),
      f"file {g.cites_to_partner.sum()} vs recomputed {sum(flow_out.values())}")

# the case raised by the team: NIT Trichy paper Q cites paper P that NIT Trichy wrote with IIT Madras
trichy = nid["NIT Trichy"]
case = [(s, t) for s, t in zip(cit.source_id, cit.target_id)
        if trichy in own_ids(s) and IIT_MADRAS not in insts[s] and trichy in insts[t] and IIT_MADRAS in insts[t]]
counted = sum(1 for s, t in zip(cit.source_id, cit.target_id)
              if trichy in own_ids(s) and trichy not in insts[t] and IIT_MADRAS in insts[t] and IIT_MADRAS not in insts[s])
row = ic[(ic.your_inst == "NIT Trichy") & (ic.partner_id == IIT_MADRAS)]
check("co-authorship rule: NIT Trichy citing a NIT Trichy + IIT Madras paper gives no flow to IIT Madras",
      bool(case) and not any(IIT_MADRAS in outside_credit(trichy, insts[s], insts[t]) for s, t in case)
      and int(row.cites_to_partner.iat[0]) == counted,
      f"{len(case)} such citations excluded; {counted} genuine NIT Trichy -> IIT Madras citations counted")

print()
print("ALL CHECKS PASSED" if not failures else f"{len(failures)} CHECK(S) FAILED")
sys.exit(1 if failures else 0)
