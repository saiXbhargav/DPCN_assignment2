"""Task 5: build the interactive dashboard -> dashboard/index.html (one self-contained file).

Reads only our own data files (group12_data.csv, faculty.csv, the network files and data/analysis/), packs the
numbers each panel needs into one JSON block, computes the two network layouts here (so the graphs open at once),
and fills them into scripts/dashboard_template.html. Run after analysis.py and network_science.py:

  python build_dashboard.py

Open dashboard/index.html in any browser (the chart libraries load from cdnjs, so it needs internet).
"""
import json
import os

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
    G = nx.Graph()
    G.add_weighted_edges_from((a, b, int(n)) for (a, b), n in w.items())
    pos = nx.spring_layout(G, seed=42, k=1.4 / np.sqrt(len(G)), iterations=300, weight=None)
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
    return {"nodes": nodes, "edges": [[a, b, d["weight"]] for a, b, d in G.edges(data=True)],
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
    t["small_world"] = records(sw, list(sw.columns))
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
    # geography (friend's section 5)
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
                        r.partner_cluster, int(round(r.distance_km))])
    t["geo_points"] = pts
    t["geo_home"] = {"NIT Trichy": geo.get("I122964287", (10.76, 78.81)), "NIT Surathkal": geo.get("I11880225", (13.01, 74.79))}
    t["geo_bands"] = records(csv(INS, "geo_distance_bands.csv"),
                             ["your_inst", "band", "linked_partners", "coauthor_partners", "shared_papers",
                              "pct_partners_coauthored", "pct_of_all_shared_papers", "pct_of_all_citations_exchanged"], 2)
    t["geo_gravity"] = records(csv(INS, "geo_gravity_model.csv"), ["outcome", "term", "coef", "p_value"], 4)
    t["geo_summary"] = jload(INS, "geo_summary.json")
    return t


def insight_tables():
    """The friend's extra insights (scripts/insights.py): AI, recency, growth, triadic closure, link prediction, ranking."""
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
    data = {"papers": papers(), "faculty": faculty(), "citation_graph": citation_graph(),
            "coauthor_graph": coauthor_graph(), "analysis": analysis_tables(), "net": network_tables(),
            "conn": connection_tables(), "ins": insight_tables(), "fair": fairness_tables(), "methods": methods_facts(),
            "meta": {"citations_date": "7 October 2026", "fwci_date": "19 October 2026", "years": "2016–2026"}}
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
