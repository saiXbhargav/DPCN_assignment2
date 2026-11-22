"""Task 5: build the interactive dashboard -> dashboard/index.html (one self-contained file).

Reads only our own data files (group12_data.csv, faculty.csv, the network files and data/analysis/), packs the
numbers each panel needs into one JSON block, computes the two network layouts here (so the graphs open at once),
and fills them into scripts/dashboard_template.html. Run after analysis.py and network_science.py:

  python build_dashboard.py

Open dashboard/index.html in any browser (the chart libraries load from cdnjs, so it needs internet).
"""
import json
import os
import re

import networkx as nx
import numpy as np
import pandas as pd

from fetch_works import ROOT

DATA = os.path.join(ROOT, "data")
AN = os.path.join(DATA, "analysis")
OUT = os.path.join(ROOT, "dashboard")
TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard_template.html")
INSTS = ["NIT Trichy", "NIT Surathkal"]
CITATION_HUBS = 30  # most influential papers (PageRank) shown in the citation graph, with the papers linked to them


def rnd(x, n=3):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), n)


def records(df, cols, n=3):
    out = []
    for r in df[cols].itertuples(index=False):
        out.append({c: (rnd(v, n) if isinstance(v, (float, np.floating)) else
                        (int(v) if isinstance(v, (np.integer,)) else (None if pd.isna(v) else v)))
                    for c, v in zip(cols, r)})
    return out


def papers():
    ds = pd.read_csv(os.path.join(DATA, "group12_data.csv"), low_memory=False)
    pp = ds.drop_duplicates(["institution", "openalex_id"])
    uniq = ds.drop_duplicates("openalex_id").copy()
    uniq["institution"] = ds.groupby("openalex_id").institution.agg(lambda s: " & ".join(sorted(set(s)))).reindex(
        uniq.openalex_id).values
    views = {inst: pp[pp.institution == inst] for inst in INSTS}
    views["Both"] = uniq
    out = {}
    for name, p in views.items():
        j = p[p.type == "journal"]
        c = p[p.type == "conference"]
        fields = p.field.fillna("Unknown").value_counts()
        top_fields = fields.head(11)
        cited = p.nlargest(10, "citations")
        out[name] = {
            "trend": {int(y): int(n) for y, n in p.year.value_counts().sort_index().items()},
            "trend_type": {t: {int(y): int(n) for y, n in g.year.value_counts().sort_index().items()}
                           for t, g in p.groupby("type")},
            "quartiles": {q: int((j.quartile == q).sum()) for q in ["Q1", "Q2", "Q3", "Q4"]} |
                         {"Not in SCImago": int((~j.quartile.fillna("").str.startswith("Q")).sum())},
            "quartile_trend": {q: {int(y): int(n) for y, n in j[j.quartile == q].year.value_counts().sort_index().items()}
                               for q in ["Q1", "Q2", "Q3", "Q4"]},
            "core": {r: int((c.quartile == f"CORE {r}").sum()) for r in ["A*", "A", "B", "C"]} |
                    {"Not ranked by CORE": int((~c.quartile.fillna("").str.startswith("CORE")).sum())},
            "top_journals": [{"journal": k, "papers": int(v),
                              "quartile": j[j.journal_name == k].quartile.mode().iat[0] if j[j.journal_name == k].quartile.notna().any() else ""}
                             for k, v in j.journal_name.value_counts().head(5).items()],
            "fields": [{"field": k, "papers": int(v)} for k, v in top_fields.items()] +
                      ([{"field": "Other fields", "papers": int(fields.iloc[11:].sum())}] if len(fields) > 11 else []),
            "top_cited": [{"title": r.title, "journal": r.journal_name if isinstance(r.journal_name, str) else "",
                           "year": int(r.year), "citations": int(r.citations), "doi": r.doi if isinstance(r.doi, str) else "",
                           "fwci": rnd(r.fwci, 2), "institution": r.institution} for r in cited.itertuples()],
            "totals": {"papers": len(p), "journal": len(j), "conference": len(c), "citations": int(p.citations.sum()),
                       "mean_fwci": rnd(p.fwci.mean(), 2), "top10": rnd(p.top10pct.astype(float).mean(), 3),
                       "q1_share": rnd((j.quartile == "Q1").sum() / max(1, j.quartile.fillna("").str.startswith("Q").sum()), 3),
                       "q1": int((j.quartile == "Q1").sum()), "if5": int((j.journal_if_2yr > 5).sum()), "if10": int((j.journal_if_2yr > 10).sum())},
        }
    return out


def faculty():
    f = pd.read_csv(os.path.join(DATA, "faculty.csv"))
    f = f.rename(columns={"author": "name", "department": "branch", "citations_in_period": "citations",
                          "h_index_2016_2026": "h", "h_index": "h_career"})
    f["branch"] = f.branch.fillna("")
    return records(f.sort_values(["papers", "citations"], ascending=False),
                   ["faculty_id", "name", "institution", "branch", "designation", "status", "first_seen", "last_seen",
                    "papers", "citations", "h", "h_career", "mean_fwci", "top_journal"], 2)


def packed_layout(G):
    """Spring layout per connected component, the components packed in rows (largest first), so separate
    clusters sit side by side instead of being pushed to the edges. Returns positions roughly in [-1, 1]."""
    comps = sorted((sorted(c) for c in nx.connected_components(G)), key=lambda c: (-len(c), c[0]))
    radius = [0.5 * np.sqrt(len(c)) for c in comps]  # grows with the square root of the size: similar density
    width = max(2 * radius[0], 1.2 * np.sqrt(sum((2 * r + 0.4) ** 2 for r in radius)))  # about a square overall
    pos, x0, y0, row_h = {}, 0.0, 0.0, 0.0
    for c, r in zip(comps, radius):
        sub = nx.spring_layout(G.subgraph(c), seed=42, iterations=200, center=(0, 0), scale=r) if len(c) > 1 else {c[0]: np.zeros(2)}
        if x0 > 0 and x0 + 2 * r > width:
            x0, y0, row_h = 0.0, y0 + row_h + 0.4, 0.0
        for n, (x, y) in sub.items():
            pos[n] = (x0 + r + x, y0 + r + y)
        x0 += 2 * r + 0.4
        row_h = max(row_h, 2 * r)
    xs, ys = np.array([p[0] for p in pos.values()]), np.array([p[1] for p in pos.values()])
    cx, cy, half = (xs.min() + xs.max()) / 2, (ys.min() + ys.max()) / 2, max(np.ptp(xs), np.ptp(ys)) / 2 or 1
    return {n: ((x - cx) / half, (y - cy) / half) for n, (x, y) in pos.items()}


def citation_graph():
    """The most influential papers by PageRank plus every paper of ours that cites them or that they cite.
    (The top papers by PageRank rarely cite each other, so the top papers alone fall apart into dots.)"""
    pm = pd.read_csv(os.path.join(DATA, "network_metrics", "citation_paper_metrics.csv"))
    pm = pm.sort_values(["pagerank", "openalex_id"], ascending=[False, True]).reset_index(drop=True)
    pm["rank"] = pm.index + 1
    cit = pd.read_csv(os.path.join(DATA, "citation_network.csv"), usecols=["source_id", "target_id", "edge_type"],
                      low_memory=False)
    internal = cit[cit.edge_type == "internal"]
    hubs = set(pm.openalex_id[:CITATION_HUBS])
    linked = internal[internal.source_id.isin(hubs) | internal.target_id.isin(hubs)]
    keep = hubs | set(linked.source_id) | set(linked.target_id)
    e = internal[internal.source_id.isin(keep) & internal.target_id.isin(keep)]
    e = e[e.source_id != e.target_id].drop_duplicates(["source_id", "target_id"]).sort_values(["source_id", "target_id"])
    G = nx.Graph()
    G.add_nodes_from(sorted(keep))
    G.add_edges_from(zip(e.source_id, e.target_id))
    pos = packed_layout(G)
    nodes = []
    for r in pm[pm.openalex_id.isin(keep)].itertuples(index=False):
        x, y = pos[r.openalex_id]
        nodes.append({"id": r.openalex_id, "title": r.title if isinstance(r.title, str) else "", "inst": r.institution,
                      "year": int(r.year), "citations": int(r.citations_total), "indeg": int(r.in_degree_internal),
                      "pr": float(r.pagerank), "rank": int(r.rank), "hub": r.openalex_id in hubs,
                      "doi": r.doi if isinstance(r.doi, str) else "",
                      "x": round(float(x) * 1000, 1), "y": round(float(y) * 1000, 1)})
    return {"nodes": nodes, "edges": [[s, t] for s, t in zip(e.source_id, e.target_id)],
            "hubs": CITATION_HUBS, "total_papers": int(len(pm)), "total_internal_edges": int(len(internal))}


def coauthor_graph():
    am = pd.read_csv(os.path.join(DATA, "network_metrics", "author_metrics.csv"))
    fac = pd.read_csv(os.path.join(DATA, "faculty.csv")).set_index("faculty_id")
    au = pd.read_csv(os.path.join(DATA, "authorship_network.csv"), low_memory=False)
    nit = au[au.edge_category.isin(["same_nit", "nit_nit"])]
    w = nit.groupby(["author_a_id", "author_b_id"]).paper_id.nunique()
    first = {}                         # year of each pair's first joint paper (for the growth player)
    for (a, b), y in nit.groupby(["author_a_id", "author_b_id"]).year.min().items():
        k = tuple(sorted((a, b)))
        first[k] = min(first.get(k, 9999), int(y))
    G = nx.Graph()
    G.add_weighted_edges_from((a, b, int(n)) for (a, b), n in w.items())
    pos = packed_layout(G)   # components packed side by side, so the small groups do not shrink the main one
    comm_sizes = am[am.author_id.isin(G.nodes)].community.value_counts()
    big = list(comm_sizes.index[:7])  # the 7 largest communities get their own colour, the rest share one
    nodes = []
    for r in am[am.author_id.isin(G.nodes)].itertuples(index=False):
        x, y = pos[r.author_id]
        nodes.append({"id": r.author_id, "name": r.author, "inst": r.institution.split(";")[0],
                      "branch": fac.department.get(r.author_id, "") if isinstance(fac.department.get(r.author_id, ""), str) else "",
                      "community": int(r.community), "comm_rank": big.index(r.community) if r.community in big else 7,
                      "degree": int(r.degree), "btw": round(float(r.betweenness_centrality), 5), "papers": int(r.papers),
                      "partners": int(r.indian_partner_institutes),
                      "x": round(float(x) * 1000, 1), "y": round(float(y) * 1000, 1)})
    return {"nodes": nodes, "edges": [[a, b, d["weight"], first[tuple(sorted((a, b)))]] for a, b, d in G.edges(data=True)],
            "communities": [{"rank": i, "community": int(c), "size": int(comm_sizes[c])} for i, c in enumerate(big)],
            "isolated_faculty": int(len(am) - G.number_of_nodes())}


def analysis_tables():
    t = {}
    inst = pd.read_csv(os.path.join(AN, "institute_comparison.csv"))
    t["institutes"] = records(inst, ["institution", "papers", "citations", "cites_per_paper", "median_cites", "mean_fwci",
                                     "top10pct_share", "q1_share_of_ranked_journals", "conference_share",
                                     "indian_collab_share", "foreign_collab_share", "faculty", "papers_per_faculty",
                                     "faculty_in_roster", "current_faculty", "median_h_index_2016_2026"])
    tests = pd.read_csv(os.path.join(AN, "institute_tests.csv"))
    t["tests"] = records(tests, list(tests.columns))
    ir = pd.read_csv(os.path.join(AN, "impact_ratio_by_year.csv"))
    t["impact_ratio_year"] = records(ir, ["institution", "year", "received", "made", "impact_ratio"])
    tot = ir.groupby("institution")[["received", "made"]].sum()
    t["impact_ratio"] = {k: rnd(v.received / v.made) for k, v in tot.iterrows()}
    fl = pd.read_csv(os.path.join(AN, "task3_flow_by_year.csv"))
    t["flow_year"] = records(fl, ["institution", "year", "received", "given"])
    ftot = fl.groupby("institution")[["received", "given"]].sum()
    t["indian_ratio"] = {k: rnd(v.received / v.given) for k, v in ftot.iterrows()}
    t["indian_flow"] = {k: {"received": int(v.received), "given": int(v.given)} for k, v in ftot.iterrows()}
    br = pd.read_csv(os.path.join(AN, "branch_comparison.csv"))
    t["branches"] = records(br, ["institution", "branch", "faculty", "papers", "papers_per_faculty", "cites_per_paper",
                                 "mean_fwci", "top10pct_share", "q1_share_of_ranked_journals", "foreign_collab_share",
                                 "small_branch"])
    bt = pd.read_csv(os.path.join(AN, "ns_branch_fwci_bootstrap.csv"))
    t["branch_bootstrap"] = records(bt, list(bt.columns))
    tc = pd.read_csv(os.path.join(AN, "task3_top_citing_institutes.csv"))
    t["top_citing"] = records(tc, list(tc.columns))
    pc = pd.read_csv(os.path.join(AN, "task3_partner_clusters.csv"))
    t["clusters"] = records(pc, ["your_inst", "partner_cluster", "partners", "co_author_partners", "shared_papers",
                                 "cites_from_partner", "cites_to_partner"])
    ic = pd.read_csv(os.path.join(DATA, "indian_connections.csv"))
    ic = ic[~ic.partner_id.isin(["I122964287", "I11880225"])]
    # mean FWCI of the joint papers with each partner (partners.csv), to see whether collaborating pays off
    jf = pd.read_csv(os.path.join(AN, "partners.csv"))[["institution", "partner_id", "joint_mean_fwci"]]
    ic = ic.merge(jf, left_on=["your_inst", "partner_id"], right_on=["institution", "partner_id"], how="left")
    t["top_partners"] = records(ic.sort_values(["your_inst", "shared_papers"], ascending=[True, False])
                                .groupby("your_inst").head(10),
                                ["your_inst", "partner_inst", "partner_cluster", "shared_papers", "total_citations",
                                 "cites_from_partner", "cites_to_partner", "joint_mean_fwci"])
    pa = pd.read_csv(os.path.join(AN, "partners.csv"))
    opp = pa[(pa.shared_papers <= 5) & pa.opportunity_score.notna()].sort_values("opportunity_score", ascending=False)
    t["opportunities"] = records(opp.groupby("institution").head(8),
                                 ["institution", "partner", "shared_papers", "cites_from_partner", "cites_to_partner",
                                  "topic_weighted_jaccard", "opportunity_score"])
    hubs = pd.read_csv(os.path.join(AN, "task3_hub_authors.csv"))
    t["hubs"] = records(hubs, list(hubs.columns), 4)
    sw = pd.read_csv(os.path.join(AN, "ns_small_world.csv"))
    t["small_world"] = records(sw, list(sw.columns), 4)
    t["sigma"] = rnd((sw.avg_clustering[0] / sw.avg_clustering[1]) / (sw.avg_path_length[0] / sw.avg_path_length[1]), 1)
    ass = pd.read_csv(os.path.join(AN, "ns_assortativity.csv"))
    t["assortativity"] = records(ass, list(ass.columns))
    nmi = pd.read_csv(os.path.join(AN, "ns_communities_vs_departments.csv"))
    t["nmi"] = records(nmi, list(nmi.columns))
    reg = pd.read_csv(os.path.join(AN, "ns_regression_institute_effect.csv"))
    t["regression"] = records(reg, ["model", "approx_%_difference", "p_value", "papers"])
    fits = pd.read_csv(os.path.join(AN, "ns_degree_fits.csv"))
    t["degree_fits"] = records(fits, ["distribution", "n", "xmin", "alpha", "p_vs_lognormal", "verdict"])
    big = pd.read_csv(os.path.join(AN, "large_papers_faculty_rankings.csv"))
    t["large_papers"] = records(big, list(big.columns), 4)
    summ = json.load(open(os.path.join(DATA, "network_metrics", "network_summary.json")))
    t["network_summary"] = summ
    return t


INS = os.path.join(AN, "insights")


def csv(*parts):
    return pd.read_csv(os.path.join(*parts), low_memory=False)


def jload(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as f:
        return json.load(f)


def network_tables():
    """Citation and co-authorship network summaries (Task 4 items, network science)."""
    t = {}
    pm = csv(DATA, "network_metrics", "citation_paper_metrics.csv").sort_values(["pagerank", "openalex_id"], ascending=[False, True])
    t["top_pagerank"] = records(pm.head(10), ["title", "institution", "year", "pagerank", "in_degree_internal",
                                              "citations_total", "doi"], 6)
    indeg = pm.in_degree_internal.value_counts().sort_index()
    t["indegree_dist"] = [[int(k), int(v)] for k, v in indeg.items() if k > 0]
    t["indegree_zero"] = int(indeg.get(0, 0))
    am = csv(DATA, "network_metrics", "author_metrics.csv")
    fac = csv(DATA, "faculty.csv").set_index("faculty_id")
    am["branch"] = am.author_id.map(fac.department).fillna("")
    am["inst"] = am.institution.str.split(";").str[0]
    cols = ["author", "inst", "branch", "degree", "betweenness_centrality", "papers", "community"]
    t["top_degree"] = records(am.sort_values(["degree", "author"], ascending=[False, True]).head(10), cols, 4)
    t["top_betweenness"] = records(am.sort_values(["betweenness_centrality", "author"], ascending=[False, True]).head(10), cols, 4)
    dd = am[am.degree > 0].degree.value_counts().sort_index()
    t["degree_dist"] = [[int(k), int(v)] for k, v in dd.items()]
    t["degree_fits"] = records(csv(AN, "ns_degree_fits.csv"), ["distribution", "n", "mean", "max", "xmin", "alpha",
                                                               "R_vs_lognormal", "p_vs_lognormal", "verdict"], 4)
    t["rich_club"] = records(csv(AN, "ns_rich_club.csv"), ["k", "rho", "nodes_with_degree_gt_k"])
    cc = csv(AN, "ns_community_composition.csv")
    lead = am.sort_values(["degree", "betweenness_centrality", "author"], ascending=[False, False, True]).drop_duplicates("community")
    lead = lead.set_index("community")
    cc["leader"] = cc.community.map(lead.author)
    cc["leader_degree"] = cc.community.map(lead.degree)
    cc["leader_inst"] = cc.community.map(lead.inst)
    t["communities"] = records(cc, ["community", "faculty", "main_department", "share_of_main_department", "departments", "mix",
                                    "leader", "leader_degree", "leader_inst"])
    t["inner_core"] = records(csv(AN, "ns_inner_core.csv"), ["faculty", "institution", "branch", "degree"])
    fl = csv(AN, "ns_institute_flow.csv")
    g = fl.groupby("cluster")[["they_cite_us", "we_cite_them"]].sum().reset_index()
    g["ratio"] = g.they_cite_us / g.we_cite_them
    t["cluster_flow"] = records(g.sort_values("ratio"), ["cluster", "they_cite_us", "we_cite_them", "ratio"])
    tot = fl[["they_cite_us", "we_cite_them"]].sum()
    t["flow_reciprocity"] = 0.64  # weighted reciprocity of the institute network (NETWORK_SCIENCE.md, section 4)
    t["flow_totals"] = {"they_cite_us": int(tot.they_cite_us), "we_cite_them": int(tot.we_cite_them),
                        "partners": int(fl.partner.nunique())}
    return t


def connection_tables():
    t = {}
    t["top_citing_papers"] = records(csv(AN, "task3_top_citing_papers.csv"),
                                     ["institution", "citing_paper", "year", "venue", "its_citations", "citing_institutes",
                                      "our_papers_it_cites"])
    t["topic_similarity"] = records(csv(AN, "task3_topic_similarity.csv"),
                                    ["institution", "partner", "partner_cluster", "topic_weighted_jaccard", "shared_papers", "exchange"])
    # geography (insights.py section 5)
    geo = {}
    with open(os.path.join(DATA, "raw", "institutions_geo.jsonl"), encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r.get("lat") is not None:
                geo[r["id"]] = (round(r["lat"], 3), round(r["lon"], 3))
    gp = csv(INS, "geo_partners.csv")
    gp = gp[(gp.shared_papers > 0) | (gp.citations_exchanged >= 30)]
    pts = []
    for r in gp.itertuples(index=False):
        if r.partner_id in geo:
            la, lo = geo[r.partner_id]
            pts.append([r.your_inst, r.partner_inst, la, lo, int(r.shared_papers), int(r.citations_exchanged),
                        r.partner_cluster, int(round(r.distance_km)), r.city if isinstance(r.city, str) else "",
                        int(r.cites_from_partner), int(r.cites_to_partner)])
    t["geo_points"] = pts
    t["geo_home"] = {"NIT Trichy": geo.get("I122964287", (10.76, 78.81)), "NIT Surathkal": geo.get("I11880225", (13.01, 74.79))}
    t["geo_bands"] = records(csv(INS, "geo_distance_bands.csv"),
                             ["your_inst", "band", "linked_partners", "coauthor_partners", "shared_papers",
                              "pct_partners_coauthored", "pct_of_all_shared_papers", "pct_of_all_citations_exchanged"], 2)
    t["geo_gravity"] = records(csv(INS, "geo_gravity_model.csv"), ["outcome", "term", "coef", "p_value"], 4)
    t["geo_summary"] = jload(INS, "geo_summary.json")
    return t


def insight_tables():
    """The extra insights (scripts/insights.py): AI, recency, growth, triadic closure, link prediction, ranking."""
    t = {}
    t["ai_year"] = records(csv(INS, "ai_share_by_year.csv"), ["year", "computing", "papers", "ai_papers", "ai_share_pct",
                                                              "partial_year"], 2)
    t["ai_dept"] = records(csv(INS, "ai_by_department.csv"),
                           ["department", "computing_department", "papers", "ai_papers", "ai_share_pct",
                            "ai_share_2016_2018_pct", "ai_share_2023_2025_pct", "change_pct_points", "first_ai_year",
                            "ai_mean_fwci", "other_mean_fwci", "ai_median_fwci", "other_median_fwci",
                            "fwci_difference_p_value"], 3)
    t["ai_methods"] = records(csv(INS, "ai_methods_outside_computing.csv"), ["method", "2016-2020", "2021-2026"])
    t["ai_dept_year"] = records(csv(INS, "ai_share_by_department_year.csv"), ["department", "year", "papers", "ai_papers",
                                                                              "ai_share_pct", "partial_year"], 2)
    ap = csv(INS, "ai_papers.csv")
    comp = set(csv(INS, "ai_by_department.csv").query("computing_department").department)
    other = csv(INS, "ai_share_by_year.csv").query("computing == 'other departments'").set_index("year").papers
    tool = {}
    for label, (a, b) in {"2016-18": (2016, 2018), "2023-25": (2023, 2025)}.items():
        x = ap[~ap.department.isin(comp) & ap.year.between(a, b)]
        n = other.loc[a:b].sum()
        tool[label] = {"topic_pct": rnd(100 * x.ai_by_topic.sum() / n, 1), "title_pct": rnd(100 * x.ai_by_title.sum() / n, 1)}
    t["ai_tool"] = tool
    t["ai_summary"] = jload(INS, "ai_summary.json")
    t["recency_year"] = records(csv(INS, "recency_by_institute_year.csv"),
                                ["institution", "year", "papers", "price_index_pct", "mean_reference_age", "partial_year"], 2)
    t["recency_dept"] = records(csv(INS, "recency_by_department.csv"),
                                ["department", "papers", "price_index_pct", "mean_reference_age", "refs_over_20_years_pct",
                                 "price_index_2016_2018_pct", "price_index_2023_2025_pct"], 2)
    t["recency_impact"] = records(csv(INS, "recency_vs_impact.csv"),
                                  ["price_quintile", "papers", "price_index_range", "mean_fwci", "median_fwci"])
    t["recency_summary"] = jload(INS, "recency_summary.json")
    t["growth"] = records(csv(INS, "growth_by_year.csv"),
                          ["year", "partial_year", "faculty_nodes", "connected_faculty", "links", "new_links_this_year",
                           "avg_degree", "largest_component_share", "effective_diameter_90pct", "avg_clustering",
                           "modularity_louvain", "cross_nit_links", "cross_department_link_share"])
    t["densification"] = jload(INS, "insights_summary.json")["densification"]
    nl = csv(INS, "new_link_sources_by_year.csv")
    t["new_links"] = {"columns": list(nl.columns[2:]), "rows": records(nl, list(nl.columns))}
    t["closure_common"] = records(csv(INS, "triadic_closure_by_common_coauthors.csv"),
                                  ["bucket", "pairs", "linked_next_year", "p_next_year_pct", "p_within_3_years_pct",
                                   "times_more_likely_than_far_pairs"], 4)
    t["closure_dept"] = records(csv(INS, "triadic_closure_by_department.csv"),
                                ["friend_of_friend", "same_department", "pairs", "p_next_year_pct", "p_within_3_years_pct"], 4)
    t["closure_inst"] = records(csv(INS, "triadic_closure_by_institute.csv"),
                                ["friend_of_friend", "same_institute", "pairs", "p_next_year_pct", "p_within_3_years_pct"], 4)
    t["closure_year"] = records(csv(INS, "triadic_closure_by_year.csv"), ["year", "friend_of_friend", "p_next_year_pct"], 4)
    t["lp_eval"] = records(csv(INS, "link_prediction_evaluation.csv"),
                           ["method", "auc", "average_precision", "precision_at_50_pct", "precision_at_100_pct",
                            "lift_at_100", "candidates", "true_new_links"], 4)
    pc = csv(INS, "link_prediction_precision_curve.csv")
    t["lp_curve"] = {"k": [int(k) for k in pc.k], "series": {c: [rnd(v, 2) for v in pc[c]] for c in pc.columns[1:]}}
    t["lp_coef"] = records(csv(INS, "link_prediction_model_coefficients.csv"), ["feature", "standardised_coefficient"])
    t["lp_pairs"] = records(csv(INS, "link_prediction_top50_future_pairs.csv"),
                            ["rank", "faculty_a", "department_a", "institute_a", "faculty_b", "department_b", "institute_b",
                             "n_common_coauthors", "common_coauthors", "model_score"])
    t["ranking"] = records(csv(INS, "faculty_ranking_overall.csv"),
                           ["overall_rank", "author", "institution", "department", "designation", "overall_score",
                            "department_rank", "department_size_ranked", "papers", "citations", "h_index", "mean_fwci",
                            "top10_papers", "top_venue_papers", "if5_papers"], 2)
    mc = csv(INS, "faculty_ranking_measure_correlation.csv")
    t["ranking_corr"] = {"measures": list(mc.measure), "matrix": [[rnd(v, 2) for v in row] for row in mc.iloc[:, 1:].values]}
    t["ranking_summary"] = jload(INS, "faculty_ranking_summary.json")
    return t


def fairness_tables():
    t = {}
    h2h = csv(AN, "branch_head_to_head.csv")
    t["head_to_head"] = records(h2h, list(h2h.columns))
    t["board_branch"] = records(csv(AN, "board_branch.csv"),
                                ["institution", "department", "publications", "journal_papers", "Q1", "IF>5", "IF>10",
                                 "share_IF>5", "share_IF>10"])
    t["large_paper_level"] = records(csv(AN, "large_papers_paper_level.csv"),
                                     ["max_authors", "institution", "papers_removed", "papers", "citations",
                                      "cites_per_paper", "mean_fwci"])
    t["large_network"] = records(csv(AN, "large_papers_network.csv"),
                                 ["max_authors", "papers_skipped", "faculty_edges", "communities", "modularity",
                                  "spearman_degree", "spearman_betweenness", "top20_betweenness_overlap"], 4)
    tr = csv(AN, "institute_trend.csv")
    t["growth_pct"] = {i: rnd(100 * (tr.loc[tr.year == 2025, i].iat[0] / tr.loc[tr.year == 2016, i].iat[0] - 1), 1)
                       for i in INSTS}
    return t


P2 = os.path.join(AN, "phase2")
QS = os.path.join(AN, "questions")


def phase2_tables():
    """Phase II additions (scripts/phase2.py -> data/analysis/phase2/)."""
    t = {}
    ps = csv(P2, "publication_statistics_both_scopes.csv")
    t["stats"] = records(ps, list(ps.columns), 3)
    tr = pd.read_csv(os.path.join(P2, "publication_trend_both_scopes.csv"), header=[0, 1], index_col=0)
    name = {"Both NITs": "Both", "NIT Trichy": "NIT Trichy", "NIT Surathkal": "NIT Surathkal"}
    t["trend"] = {"all": {}, "faculty": {}}
    for sc, inst in tr.columns:
        t["trend"]["all" if sc.startswith("all") else "faculty"][name[inst]] = {
            int(y): int(v) for y, v in tr[(sc, inst)].items()}
    t["students"] = records(csv(P2, "student_only_papers_profile.csv"),
                           ["institution", "student_only_papers", "mean_fwci", "citations_per_paper",
                            "conference_share_pct", "with_outside_coauthor_pct"], 2)
    ac = csv(P2, "author_count_classes.csv")
    t["authors"] = records(ac, list(ac.columns), 2)
    t["q1_if_branch"] = records(csv(P2, "q1_if_by_branch.csv"),
                               ["institution", "department", "journal_papers", "Q1", "IF_gt_5", "IF_gt_10",
                                "Q1_and_IF_gt_5", "Q1_and_IF_gt_10", "Q1_and_IF_gt_5_pct"], 1)
    cy = csv(P2, "collaborating_institutions_by_year.csv")
    t["collab_year"] = records(cy, ["scope", "institution", "year", "papers", "collaborating_institutions",
                                    "indian_institutions", "foreign_institutions", "countries",
                                    "papers_with_outside_coauthor_pct", "partial_year"], 2)
    t["collab_total"] = records(csv(P2, "collaborating_institutions_total.csv"),
                                ["scope", "institution", "collaborating_institutions", "indian_institutions",
                                 "foreign_institutions", "countries"])
    t["papers_summary"] = jload(P2, "phase2_papers_summary.json")
    fl = csv(P2, "flag_faculty_citations_and_large_teams.csv")
    flagged = fl[fl.flag_possible_openalex_name_merge | fl.flag_mostly_large_team | fl.flag_career_citations_1_lakh]
    t["flagged_faculty"] = records(flagged, ["author", "institution", "department", "papers", "papers_10plus_authors",
                                             "share_citations_from_10plus_pct", "career_citations_openalex",
                                             "nit_share_of_career_citations_pct", "flag_mostly_large_team",
                                             "flag_possible_openalex_name_merge"], 1)
    t["top_career"] = records(fl.nlargest(10, "career_citations_openalex"),
                              ["author", "institution", "department", "career_citations_openalex",
                               "citations_2016_2026", "nit_share_of_career_citations_pct", "max_authors"], 1)
    lt = csv(P2, "flag_large_team_papers.csv").sort_values("n_authors", ascending=False)
    t["large_papers"] = records(lt.head(12), ["institution", "title", "year", "n_authors", "field", "citations",
                                              "has_faculty_author", "faculty_on_paper", "doi"], 2)
    t["large_count"] = {"10+": int(len(lt)), "faculty": int(lt.has_faculty_author.sum()),
                        "20+": int((lt.n_authors >= 20).sum())}
    t["citers_cmp"] = records(csv(P2, "citers_private_vs_public.csv"),
                              ["measure", "private_median", "public_median", "mann_whitney_p"], 4)
    ci = csv(P2, "citers_by_institute.csv")
    want = ["institute", "type", "citations_to_us", "their_papers_2016_2026", "citations_per_1000_of_their_papers",
            "distance_km", "personal_tie_pct", "alumni_pct", "pct_citations_from_papers_citing_5plus_of_ours",
            "citing_papers_in_proceedings_pct", "pct_citations_2023_2026", "top_cited_faculty"]
    t["citers"] = records(ci, [c for c in want if c in ci.columns], 1)
    t["citers_summary"] = jload(P2, "citers_summary.json")
    cols30 = ["rank", "title", "journal_name", "journal_if_2yr", "quartile", "year", "citations", "fwci", "nits",
              "has_faculty_author", "faculty_on_paper", "doi"]
    t["top30_all"] = records(csv(P2, "top30_papers_by_journal_if_all_papers.csv"), cols30, 2)
    t["top30_fac"] = records(csv(P2, "top30_papers_by_journal_if_faculty_papers.csv"), cols30, 2)
    ft = csv(P2, "faculty_top10_papers_by_journal_if.csv")
    journals = sorted(ft.journal_name.fillna("").unique())
    jix = {j: k for k, j in enumerate(journals)}
    fac = {}
    for fid, g in ft.groupby("faculty_id", sort=False):
        r0 = g.iloc[0]
        fac[fid] = {"n": r0.author, "i": r0.institution, "d": "" if pd.isna(r0.department) else r0.department,
                    "p": [[(r.title if isinstance(r.title, str) else "")[:140],
                           jix[r.journal_name if isinstance(r.journal_name, str) else ""],
                           rnd(r.journal_if_2yr, 1), r.quartile if isinstance(r.quartile, str) else "", int(r.year),
                           int(r.citations), (r.doi if isinstance(r.doi, str) else "").replace("https://doi.org/", "")]
                          for r in g.sort_values("rank_in_faculty").itertuples(index=False)]}
    t["fac_top10"] = {"journals": journals, "faculty": fac}
    mu = csv(P2, "most_used_journals_and_conferences.csv")
    t["venues"] = records(mu, ["scope", "institution", "venue_type", "rank", "journal_name", "papers",
                               "quartile_or_rank", "journal_if_2yr", "citations_per_paper", "mean_fwci",
                               "share_of_venue_type_pct"], 2)
    fr = csv(P2, "faculty_research_and_collaboration.csv")
    t["collab_faculty"] = records(fr, ["research_rank", "collaboration_rank", "author", "institution", "department",
                                       "research_score", "collaboration_score", "papers", "h_index", "mean_fwci",
                                       "faculty_coauthors", "indian_partner_institutes", "foreign_partner_institutes",
                                       "foreign_countries", "profile"], 2)
    t["collab_corr"] = jload(P2, "faculty_collaboration_summary.json")
    t["instnet"] = jload(P2, "institute_network_summary.json")
    nodes = csv(P2, "institute_coauthorship_nodes.csv")
    nodes = nodes[~nodes.cluster.eq("NIT (ours)")]
    t["inst_nodes"] = records(nodes.nlargest(25, "betweenness"),
                              ["institution", "cluster", "papers_with_us", "degree", "joint_papers_weighted_degree",
                               "linked_to_nit_trichy", "linked_to_nit_surathkal", "betweenness"], 4)
    t["inst_clusters"] = records(csv(P2, "institute_network_by_cluster.csv"),
                                 ["cluster", "institutes", "joint_papers", "mean_degree", "mean_betweenness"], 4)
    # task 12: degree assortativity of three networks vs degree-preserving rewiring, and k_nn(k)
    if os.path.exists(os.path.join(P2, "assortativity_degree.csv")):
        t["assort"] = records(csv(P2, "assortativity_degree.csv"),
                              ["network", "variant", "directed_pair", "nodes", "links", "r", "null_mean", "null_sd", "z",
                               "p_value", "sign", "vs_degree_preserving_random", "null_samples"], 4)
        t["assort_knn"] = records(csv(P2, "assortativity_knn.csv"),
                                  ["network", "variant", "k", "knn", "knn_null_mean", "nodes_with_k"], 3)
    return t


def questions_tables():
    """Research questions 15-27 (scripts/questions.py -> data/analysis/questions/)."""
    def allcols(f, n=4):
        d = csv(QS, f)
        return records(d, list(d.columns), n)
    t = {}
    t["countries"] = records(csv(QS, "q15_countries.csv").head(25),
                             ["country", "papers", "papers_trichy", "papers_surathkal", "mean_fwci", "top10_share",
                              "papers_2016_2020", "papers_2021_2025", "effect_pct", "ci_low_pct", "ci_high_pct",
                              "p_value", "top_faculty", "top_faculty_share"], 3)
    t["foreign_effect"] = allcols("q15_foreign_effect.csv")
    t["n_countries"] = allcols("q15_effect_by_number_of_countries.csv")
    t["foreign_year"] = records(csv(QS, "q15_foreign_by_year.csv"),
                                ["institution", "year", "papers", "foreign_share", "countries"], 4)
    t["partners"] = allcols("q16_partner_types.csv")
    t["collab_summary"] = jload(QS, "collab_summary.json")
    t["robust_curves"] = records(csv(QS, "q17_robustness_curves.csv"),
                                 ["institution", "strategy", "removed", "removed_share", "connected_pairs_share",
                                  "giant_share"], 4)
    t["key_overall"] = records(csv(QS, "q17_key_people_overall.csv").head(15),
                               ["name", "institution", "department", "designation", "status", "co_authors",
                                "pairs_cut_share", "components_after"], 4)
    t["key_dept"] = allcols("q17_key_people_by_department.csv")
    t["network_summary"] = jload(QS, "network_summary.json")
    t["former"] = allcols("q18_former_vs_current.csv")
    t["former_where"] = records(csv(QS, "q18_where_former_faculty_went.csv"),
                                ["author", "institution", "department", "designation", "last_seen", "now_at",
                                 "now_type"])
    t["inequality"] = allcols("q19_inequality.csv")
    t["inequality_dept"] = allcols("q19_inequality_by_department.csv")
    t["lorenz"] = allcols("q19_lorenz.csv")
    t["lotka"] = allcols("q19_lotka.csv")
    t["roles"] = allcols("q20_author_role_by_rank.csv")
    t["roles_year"] = allcols("q20_author_role_by_rank_and_year.csv")
    t["breadth_groups"] = allcols("q21_breadth_groups.csv")
    t["breadth_corr"] = allcols("q21_breadth_vs_impact.csv")
    t["people_summary"] = jload(QS, "people_summary.json")
    t["venue_classes"] = allcols("q22_venue_classes.csv")
    t["conf_year"] = allcols("q22_conference_share_by_year.csv")
    t["conf_dept"] = allcols("q22_conference_by_department.csv")
    t["high_volume"] = allcols("q23_high_volume_venues.csv")
    t["oa"] = allcols("q24_open_access.csv")
    t["oa_year"] = allcols("q24_open_access_by_year.csv")
    t["venues_summary"] = jload(QS, "venues_summary.json")
    t["kernel"] = allcols("q25_attachment_kernel.csv")
    t["alpha_age"] = allcols("q25_alpha_by_age.csv")
    t["stay"] = allcols("q25_top_papers_stay_on_top.csv")
    t["richer_summary"] = jload(QS, "richer_summary.json")
    t["sensitivity"] = allcols("q27_name_matching_sensitivity.csv")
    t["inward_overall"] = allcols("q26_inward_overall.csv")
    t["inward_dept"] = allcols("q26_inward_by_department.csv")
    t["inward_year"] = allcols("q26_inward_by_year.csv")
    t["inward_summary"] = jload(QS, "inward_summary.json")
    t["heavy_dist"] = allcols("q28_heavy_citing_papers_distribution.csv")
    hv = csv(QS, "q28_heavy_outside_citing_papers.csv").head(15)
    t["heavy_papers"] = records(hv, ["title", "venue", "year", "our_papers_cited", "most_cited_faculty",
                                     "papers_of_that_faculty_cited", "former_nit_member_on_it", "indian_institutes"])
    t["fac_spread"] = allcols("q28_faculty_citation_source_spread.csv")
    t["citing_inst"] = allcols("q28_citing_institutes.csv")
    ms = jload(QS, "manipulation_summary.json")
    t["manip_summary"] = {k: ms[k] for k in ("indian_citing_papers", "indian_citation_links", "heavy_threshold",
                                             "min_citations", "flags", "heavy_outside_papers",
                                             "heavy_outside_with_former_nit_member", "heavy_outside_years",
                                             "heavy_outside_top_venues", "heavy_outside_by_faculty",
                                             "faculty_eligible", "ranking", "institutes")}
    return t


PP = os.path.join(AN, "papers")


def depth_tables():
    """Deeper Phase II questions (scripts/phase2_papers.py -> data/analysis/papers/), when they have been run:
    the summaries, and every test with its false-discovery-rate adjusted p-value."""
    t = {}
    if not os.path.isdir(PP):
        return t
    for key, name in (("a", "a_summary.json"), ("s", "s_summary.json"), ("r", "r_summary.json"),
                      ("b", "b_summary.json"), ("c", "c_summary.json"), ("d", "d_summary.json"),
                      ("e", "e_summary.json")):
        if os.path.exists(os.path.join(PP, name)):
            t[key] = jload(PP, name)
    if os.path.exists(os.path.join(PP, "r_false_discovery.csv")):
        fd = csv(PP, "r_false_discovery.csv")
        t["fdr"] = records(fd, list(fd.columns), n=5)
    # tables for the Phase II "deeper questions" panels
    if os.path.exists(os.path.join(PP, "s_pagerank_top10.csv")):
        top = csv(PP, "s_pagerank_top10.csv")
        top = top[top.network == "without self-citations"]
        t["s_top10"] = records(top, ["rank", "openalex_id", "title", "year", "institution", "department", "in_degree",
                                     "citations_total"])
    if os.path.exists(os.path.join(PP, "c_best_new_links.csv")):
        t["c_links"] = records(csv(PP, "c_best_new_links.csv"), ["set", "a", "a_nit", "b", "b_nit", "department",
                                                                 "efficiency_after"], n=5)
    if os.path.exists(os.path.join(PP, "d_headcount_by_year.csv")):
        hc = csv(PP, "d_headcount_by_year.csv")
        t["d_headcount"] = records(hc, list(hc.columns))
    return t


PF = os.path.join(AN, "prof")


def prof_tables():
    """Network growth, link prediction and other NITs (scripts/phase2_prof.py -> data/analysis/prof/), when run."""
    t = {}
    if not os.path.isdir(PF):
        return t
    tabs = {"growth": "g_average_degree_by_year.csv", "dens": "g_densification_by_nit.csv",
            "pred": "p_link_prediction.csv", "check": "p_predict_and_check_top20.csv", "matches": "p_fixed_correct_matches.csv",
            "four": "c_four_nits.csv", "four_year": "c_four_nits_by_year.csv",
            "fac_net": "f_faculty_network_four_nits.csv", "fac_dens": "f_faculty_densification_four_nits.csv",
            "match": "f_nirf_name_matching.csv", "bands": "n_joining_bands.csv", "cohort": "n_cohort_output.csv",
            "roster": "n_roster_vs_nirf.csv"}
    for key, name in tabs.items():
        if os.path.exists(os.path.join(PF, name)):
            df = csv(PF, name)
            t[key] = records(df, list(df.columns))
    if os.path.exists(os.path.join(PF, "n_summary.json")):
        t["nirf"] = jload(PF, "n_summary.json")
    # "number of faculty, pure number" and "do the rich get richer?" (parts puren and kernel)
    for key, name in (("u", "u_pure_n_by_year.csv"), ("u_fits", "u_pure_n_densification.csv"), ("k", "k_kernel.csv")):
        if os.path.exists(os.path.join(PF, name)):
            df = csv(PF, name)
            t[key] = records(df, list(df.columns))
    if os.path.exists(os.path.join(PF, "k_summary.json")):
        t["k_fits"] = jload(PF, "k_summary.json")["fits"]
    return t


# proceedings series (books of many conferences) vs named conferences
SERIES = re.compile(r"lecture notes|conference series|conference proceedings|communications in computer|^advances in |procedia|"
                    r"journal of physics|springer proceedings|smart innovation|algorithms for intelligent|materials today|"
                    r"ifac-papersonline|web of conferences|engineering proceedings|^studies in |transactions on|^lecture", re.I)
SHORT_INST = {"NIT Trichy": "T", "NIT Surathkal": "S"}


def extra_tables():
    """Data for the panels added on 18 Nov 2026: field bubbles, conferences by department, partner details for the map,
    faculty profiles, a larger citation network with self-citation flags, and self-citation share by year."""
    t = {}
    g = pd.read_csv(os.path.join(DATA, "group12_data.csv"), low_memory=False)

    # 1. which fields get the most citations (all papers incl. students' own, the paper-question rule)
    ap = pd.read_csv(os.path.join(DATA, "all_papers.csv"), low_memory=False)
    views = {i: ap[ap.institution == i] for i in INSTS}
    views["Both"] = ap.drop_duplicates("openalex_id")
    fields = {}
    for v, p in views.items():
        out = []
        for f, q in p.groupby(p.field.fillna("Unknown")):
            if len(q) < 5:
                continue
            top = q.nlargest(6, "citations")
            out.append({"f": f, "n": int(len(q)), "c": rnd(q.citations.mean(), 1), "fw": rnd(q.fwci.median(), 2),
                        "top": [[(r.title if isinstance(r.title, str) else "")[:150], int(r.year), int(r.citations),
                                 (r.doi if isinstance(r.doi, str) else "").replace("https://doi.org/", ""),
                                 SHORT_INST.get(r.institution, "")] for r in top.itertuples(index=False)]})
        fields[v] = sorted(out, key=lambda x: -x["n"])
    t["fields"] = fields

    # 2. conferences by department (faculty papers): named conferences vs proceedings series
    c = g[g.type == "conference"].drop_duplicates(["institution", "department", "openalex_id"]).copy()
    c["series"] = c.journal_name.fillna("").str.contains(SERIES)
    ven = {}
    for inst in INSTS:
        ci = c[c.institution == inst]
        groups = {"All departments": ci.drop_duplicates("openalex_id")}
        groups.update({d: q for d, q in ci.groupby("department") if len(q) >= 10})
        ven[inst] = {}
        for d, q in groups.items():
            ven[inst][d] = {}
            for kind, qq in (("named", q[~q.series]), ("series", q[q.series])):
                rows = []
                for name, z in qq.groupby("journal_name"):
                    core = z.quartile.dropna()
                    core = core[core.str.startswith("CORE")]
                    rows.append([name, int(len(z)), int(z.citations.sum()), core.mode().iat[0].replace("CORE ", "") if len(core) else ""])
                ven[inst][d][kind] = sorted(rows, key=lambda r: (-r[1], -r[2]))[:10]
            ven[inst][d]["total"] = int(len(q))
    t["venues_dept"] = ven

    # 3. partner details for the map's side panel (faculty papers, as in indian_connections.csv)
    gp = csv(INS, "geo_partners.csv")
    want = set(zip(gp[gp.shared_papers > 0].your_inst, gp[gp.shared_papers > 0].partner_inst))
    pp = g.dropna(subset=["coauthor_institutes"]).copy()
    pp["partner"] = pp.coauthor_institutes.str.split(";")
    x = pp.explode("partner")
    x["partner"] = x.partner.str.strip()
    x = x[[(i, p) in want for i, p in zip(x.institution, x.partner)]]
    det = {}
    for (inst, part), q in x.groupby(["institution", "partner"]):
        papers = q.drop_duplicates("openalex_id")
        top = papers.nlargest(3, "citations")
        det[f"{inst}|{part}"] = {
            "y": {int(y): int(n) for y, n in papers.year.value_counts().sort_index().items()},
            "f": [[a, int(n)] for a, n in q.drop_duplicates(["openalex_id", "faculty_id"]).author.value_counts().head(6).items()],
            "p": [[(r.title if isinstance(r.title, str) else "")[:140], int(r.year), int(r.citations),
                   (r.doi if isinstance(r.doi, str) else "").replace("https://doi.org/", "")] for r in top.itertuples(index=False)]}
    t["partner_detail"] = det

    # 4. partner heat map: the top partners of each NIT, as a share of the NIT's papers
    ic = pd.read_csv(os.path.join(DATA, "indian_connections.csv"))
    ic = ic[~ic.partner_inst.isin(INSTS)]
    tot = {i: int(g[g.institution == i].openalex_id.nunique()) for i in INSTS}
    top = set()
    for i in INSTS:
        top |= set(ic[ic.your_inst == i].nlargest(8, "shared_papers").partner_inst)
    heat = []
    for p in sorted(top, key=lambda p: -ic[ic.partner_inst == p].shared_papers.sum()):
        row = {"partner": p, "type": ic[ic.partner_inst == p].partner_cluster.iat[0]}
        for i in INSTS:
            s = ic[(ic.your_inst == i) & (ic.partner_inst == p)].shared_papers.sum()
            row[i] = [int(s), rnd(100 * s / tot[i], 2)]
        heat.append(row)
    t["partner_heat"] = heat
    t["partner_count"] = {i: int((ic[(ic.your_inst == i)].shared_papers > 0).sum()) for i in INSTS}

    # 5. faculty profiles: papers per year, journal quartiles, lead-author share, big-team citations
    yrs = list(range(2016, 2027))
    prof = {}
    for fid, q in g.groupby("faculty_id"):
        p = q.drop_duplicates("openalex_id")
        j = p[p.type == "journal"]
        cites = p.citations.sum()
        prof[fid] = {"y": [int((p.year == y).sum()) for y in yrs],
                     "q": [int((j.quartile == k).sum()) for k in ("Q1", "Q2", "Q3", "Q4")] +
                          [int((~j.quartile.fillna("").str.startswith("Q")).sum()), int((p.type == "conference").sum())],
                     "fw": rnd(p.fwci.median(), 2),
                     "lead": rnd((q.author_position == 1).mean(), 2) if "author_position" in q else None,
                     "big": rnd(p[p.n_authors >= 10].citations.sum() / cites, 2) if cites else 0}
    t["profiles"] = prof

    # 6. a larger citation network (top papers by PageRank) with self-citation flags, and self-citation share by year
    from phase2_papers import authors, unique_works
    works = unique_works()
    au = {wid: authors(w) for wid, w in works.items()}
    pm = pd.read_csv(os.path.join(DATA, "network_metrics", "citation_paper_metrics.csv"))
    pm = pm.sort_values(["pagerank", "openalex_id"], ascending=[False, True]).reset_index(drop=True)
    pm["rank"] = pm.index + 1
    cit = pd.read_csv(os.path.join(DATA, "citation_network.csv"), usecols=["source_id", "target_id", "edge_type", "year"],
                      low_memory=False)
    internal = cit[(cit.edge_type == "internal") & (cit.source_id != cit.target_id)].drop_duplicates(["source_id", "target_id"])
    internal = internal.assign(selfcite=[bool(au.get(s, set()) & au.get(t_, set())) for s, t_ in zip(internal.source_id, internal.target_id)])
    nit_of = g.groupby("openalex_id").institution.agg(lambda s: "Both" if s.nunique() > 1 else s.iat[0])
    by = internal.assign(inst=internal.source_id.map(nit_of))
    sy = []
    for (inst, y), q in by.groupby(["inst", "year"]):
        if inst in INSTS and 2016 <= y <= 2026:
            sy.append({"institution": inst, "year": int(y), "citations": int(len(q)), "self_pct": rnd(100 * q.selfcite.mean(), 1)})
    t["selfcite_year"] = sy
    # the 100 most influential papers (PageRank) and every paper of ours that cites them or that they cite
    H = 100
    hubs = list(pm.openalex_id[:H])
    lk = internal[internal.source_id.isin(hubs) | internal.target_id.isin(hubs)]
    keepset = set(hubs) | set(lk.source_id) | set(lk.target_id)
    keep = [p_ for p_ in pm.openalex_id if p_ in keepset]          # in PageRank order
    ix = {p: k for k, p in enumerate(keep)}
    hub_rank = {p_: k + 1 for k, p_ in enumerate(hubs)}
    e = internal[internal.source_id.isin(ix) & internal.target_id.isin(ix)]
    G = nx.Graph()
    G.add_nodes_from(keep)
    G.add_edges_from(zip(e.source_id, e.target_id))
    pos = packed_layout(G)
    meta = g.drop_duplicates("openalex_id").set_index("openalex_id")
    fl = sorted(meta.field.fillna("Unknown").unique())
    fix = {f: k for k, f in enumerate(fl)}
    nodes = []
    for r in pm[pm.openalex_id.isin(keepset)].itertuples(index=False):
        m = meta.loc[r.openalex_id] if r.openalex_id in meta.index else None
        x_, y_ = pos[r.openalex_id]
        nodes.append([SHORT_INST.get(nit_of.get(r.openalex_id), "B"), int(r.year),
                      fix.get(m.field if m is not None and isinstance(m.field, str) else "Unknown", fix.get("Unknown", 0)),
                      int(m.n_authors) if m is not None and not pd.isna(m.n_authors) else 0,
                      float(f"{r.pagerank:.3g}"), int(r.citations_total), int(r.in_degree_internal),
                      (r.title if isinstance(r.title, str) else "")[:150],
                      (r.doi if isinstance(r.doi, str) else "").replace("https://doi.org/", ""),
                      round(float(x_) * 1000, 1), round(float(y_) * 1000, 1), hub_rank.get(r.openalex_id, 0), int(r.rank)])
    t["cit_big"] = {"cols": ["inst", "year", "field", "n_authors", "pr", "citations", "indeg", "title", "doi", "x", "y", "hub", "rank"],
                    "fields": fl, "nodes": nodes,
                    "edges": [[ix[s], ix[t_], int(f)] for s, t_, f in zip(e.source_id, e.target_id, e.selfcite)],
                    "total_papers": int(len(pm)), "total_edges": int(len(internal)),
                    "self_share_all": rnd(internal.selfcite.mean(), 4)}
    # India's outer border for the map (DataMeet, official boundary; simplified in data/reference/india_outline.json)
    ol = os.path.join(DATA, "reference", "india_outline.json")
    if os.path.exists(ol):
        t["india_outline"] = jload(DATA, "reference", "india_outline.json")["rings"]
    return t


DY = os.path.join(AN, "dynamics")


def dynamics_tables():
    """Network dynamics (scripts/dynamics.py -> data/analysis/dynamics/): spreading, triangles, super-ties,
    newcomers and brokers."""
    if not os.path.exists(os.path.join(DY, "spread_threshold.csv")):
        return {}
    t = {}
    t["spread_threshold"] = records(csv(DY, "spread_threshold.csv"),
                                    ["network", "faculty", "links", "mean_degree", "lambda_1", "threshold_1_over_lambda",
                                     "rewired_lambda_1", "ipr", "rewired_ipr", "ipr_if_fully_spread",
                                     "top_eigenvector_faculty"], 4)
    t["spread_sims"] = records(csv(DY, "spread_simulations.csv"),
                               ["network", "beta", "seeds", "mean_reach_pct", "p90_reach_pct"], 2)
    t["triangles"] = jload(DY, "triangles_summary.json")
    t["triangles_mix"] = records(csv(DY, "triangles_by_mix.csv"),
                                 ["mix", "born as a team", "built pair by pair, sealed later",
                                  "pairwise only (never a three-person paper)", "triangles"], 0)
    t["superties"] = jload(DY, "superties_summary.json")
    sp = csv(DY, "superties_pairs.csv").head(15).copy()
    sp["same_department"] = np.where(sp.same_department, "yes", "no")
    t["superties_top"] = records(sp, ["faculty_a", "faculty_b", "joint_papers", "first_year", "last_year",
                                      "same_department", "institutes"], 0)
    t["newcomers"] = jload(DY, "newcomers_summary.json")
    t["newcomers_inst"] = records(csv(DY, "newcomers_by_institute.csv"),
                                  ["institution", "newcomers", "with_internal_link_by_2026_pct",
                                   "median_years_to_first_link", "isolated_after_3_years_pct"], 1)
    nd = csv(DY, "newcomers.csv")
    yt = nd.years_to_first_link.dropna().clip(upper=6).astype(int).value_counts().sort_index()
    t["newcomers_years"] = [{"years": ("6+" if k == 6 else str(k)), "newcomers": int(v)} for k, v in yt.items()]
    t["brokers"] = jload(DY, "brokers_summary.json")
    b = csv(DY, "brokers.csv")
    b = b[b.degree >= 3].nsmallest(15, "constraint")
    t["brokers_top"] = records(b, ["author", "institution", "department", "degree", "degree_rank", "constraint",
                                   "effective_size", "coauthor_departments", "other_department_coauthors_pct"], 3)
    if os.path.exists(os.path.join(DY, "sync_summary.csv")):
        t["sync"] = records(csv(DY, "sync_summary.csv"), ["network", "faculty_in_largest_group", "links", "lambda_1",
                            "Kc_theory", "lambda_2", "eigenratio", "rewired_lambda_2", "rewired_eigenratio",
                            "K_half_real", "K_half_rewired", "r_at_K1_real", "r_at_K1_rewired"], 4)
        t["sync_curves"] = records(csv(DY, "sync_curves.csv"), ["network", "graph", "K", "r_mean", "r_sd"], 3)
        t["sync_locked"] = records(csv(DY, "sync_locked.csv"), ["network", "K", "degree_class", "faculty", "locked_pct"], 1)
    if os.path.exists(os.path.join(DY, "ties_summary.json")):
        t["ties"] = jload(DY, "ties_summary.json")
        t["ties_experience"] = records(csv(DY, "ties_renewal_by_experience.csv"),
                                       ["years_together", "renewed_within_2_pct", "cases"], 1)
        t["ties_gaps"] = records(csv(DY, "ties_gaps.csv"), ["gap_years", "gaps"], 0)
        t["ties_groups"] = records(csv(DY, "ties_renewal_by_group.csv"), ["factor", "group", "pairs", "renewed_within_3_pct"], 1)
    if os.path.exists(os.path.join(DY, "groups_summary.json")):
        t["groups"] = jload(DY, "groups_summary.json")
        t["groups_windows"] = records(csv(DY, "groups_per_window.csv"), ["window", "groups", "faculty_in_groups", "largest",
                                      "mean_size", "main_unit_share_pct", "multi_department_groups_pct", "cross_nit_groups",
                                      "births", "deaths", "merges", "splits", "continued"], 1)
        t["groups_nodes"] = records(csv(DY, "groups_by_window.csv"), ["window_index", "group_index", "dynamic_group", "size",
                                    "main_unit", "main_unit_share_pct", "cross_nit", "key_members"], 0)
        t["groups_links"] = records(csv(DY, "groups_links.csv"), ["from_window", "from_group", "to_window", "to_group",
                                    "shared_faculty"], 0)
        lt = csv(DY, "groups_lifetimes.csv")
        t["groups_long"] = records(lt[lt.lifetime_windows >= 5].copy().assign(drifted=lambda d: np.where(d.drifted, "yes", "no")),
                                   ["first_window", "last_window", "lifetime_windows", "size_first", "size_last",
                                    "stationarity", "main_unit_first", "main_unit_last", "drifted", "key_members_last"], 2)
    return t


def south_tables():
    """The six South Indian NITs (scripts/south_nits.py -> data/analysis/south/south_summary.json), when built."""
    path = os.path.join(AN, "south", "south_summary.json")
    return jload(path) if os.path.exists(path) else None


def methods_facts():
    """Numbers for the 'How we built it' tab, counted from the reference files."""
    r = csv(DATA, "reference", "faculty_roster.csv")
    reg = r[r.regular.astype(str) == "True"]
    se = reg[reg.science_engineering.astype(str) == "True"]
    m = csv(DATA, "reference", "faculty_openalex_map.csv")
    acc = m[m.decision == "accepted"]
    ov = csv(DATA, "reference", "faculty_match_overrides.csv")
    return {"pages": int(len(csv(DATA, "raw", "faculty_pages", "manifest.csv"))), "roster_rows": int(len(r)),
            "roster": {i: {"regular": int((reg.institution == i).sum()),
                           "science_engineering": int((se.institution == i).sum()),
                           "current": int(((se.institution == i) & (se.status == "current")).sum()),
                           "former": int(((se.institution == i) & (se.status == "former")).sum())} for i in INSTS},
            "scholars": int(len(csv(DATA, "reference", "research_scholars.csv"))),
            "overrides": int(len(ov)), "overrides_by_decision": {k: int(v) for k, v in ov.decision.value_counts().items()},
            "map_methods": {k: int(v) for k, v in acc.method.value_counts().items()},
            "linked_faculty": int(acc.faculty_id.nunique()), "links": int(len(acc)),
            "unmatched_prolific": int(len(csv(DATA, "reference", "unmatched_prolific_authors.csv"))),
            "rows": int(len(csv(DATA, "group12_data.csv"))), "checks": 44}


def main():
    os.makedirs(OUT, exist_ok=True)
    # the citation graph on the dashboard now comes from extra_tables() (100 hub papers, with self-citation flags)
    data = {"papers": papers(), "faculty": faculty(),
            "coauthor_graph": coauthor_graph(), "analysis": analysis_tables(), "net": network_tables(),
            "conn": connection_tables(), "ins": insight_tables(), "fair": fairness_tables(), "methods": methods_facts(),
            "p2": phase2_tables(), "q": questions_tables(), "pp": depth_tables(), "pf": prof_tables(), "x": extra_tables(), "south": south_tables(), "dyn": dynamics_tables(),
            "findings": (json.load(open(os.path.join(AN, "findings.json"), encoding="utf-8"))
                         if os.path.exists(os.path.join(AN, "findings.json")) else {}),   # scripts/findings.py
            "meta": {"citations_date": "7 October 2026", "fwci_date": "19 October 2026", "years": "2016–2026",
                     "yearly_date": "11 November 2026"}}
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    page = open(TEMPLATE, encoding="utf-8").read().replace("/*__DATA__*/null", blob)
    # the template is a page body (as the online version needs); the repo file gets a full document around it
    full = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n</head>\n<body>\n'
            + page + "\n</body>\n</html>\n")
    with open(os.path.join(OUT, "index.html"), "w", encoding="utf-8") as f:
        f.write(full)
    print(f"dashboard/index.html: {len(full) / 1e6:.2f} MB, data {len(blob) / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
