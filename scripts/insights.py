"""Extra insights (team agreed: faculty-only network; faculty science / engineering papers).

  python insights.py [network] [ai] [recency] [geo] [links] [ranking]      (no argument = all six)

  network  1. Growth over time - cumulative network 2016..t for every year t: size, degree, components,
              clustering, diameter; densification law E(t) ~ N(t)^a (Leskovec et al. 2005).
           2. Triadic closure - do "friends of friends" become co-authors? For every year t, every pair of
              faculty who are not yet co-authors is checked: did they write their first joint paper in t+1?
  ai       3. Is AI spreading into every department? A paper is AI if its OpenAlex subfield is Artificial
              Intelligence / Computer Vision, OR its title names an AI / machine-learning method.
  recency  4. How recent is the work each department cites? Price index (share of references at most 4
              years older than the citing paper) and median reference age. Needs fetch_insights.py refyears.
  geo      5. Does geography limit collaboration? Joint papers and citation exchange with Indian partners
              against distance, plus a gravity model. Needs fetch_insights.py geo.
  links    6. Link prediction - rank all not-yet-linked faculty pairs with network scores (common neighbours,
              Adamic-Adar, Jaccard, resource allocation, preferential attachment) and a logistic model; test on
              2022 -> 2023-2026, then list the 50 most likely future pairs among current faculty.
  ranking  7. Faculty ranking - current faculty with >= 10 papers, scored by the mean percentile of 7 measures
              (papers, citations, h-index, mean FWCI, top-10% papers, Q1 / CORE A*/A papers, IF > 5 papers),
              overall and within each department.

Uses data/authorship_network.csv, group12_data.csv, faculty.csv, indian_connections.csv and data/raw/.
Outputs go to data/analysis/insights/.
"""
import json
import math
import os
import re
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pandas as pd
from scipy import stats

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(DATA, "analysis", "insights")
FIRST, LAST = 2016, 2026
PARTIAL_YEAR = 2026            # data collected in October 2026
SEED = 42


# ---------------------------------------------------------------- load
def load():
    au = pd.read_csv(os.path.join(DATA, "authorship_network.csv"), low_memory=False)
    fac = au[au.edge_category.isin(["same_nit", "nit_nit"])]
    pairs = (fac.groupby(["author_a_id", "author_b_id"])
                .agg(first_year=("year", "min"), papers=("paper_id", "nunique"))
                .reset_index())
    rows = pd.read_csv(os.path.join(DATA, "group12_data.csv"), usecols=["faculty_id", "year", "institution"])
    first_pub = rows.groupby("faculty_id").year.min()
    info = pd.read_csv(os.path.join(DATA, "faculty.csv")).drop_duplicates("faculty_id").set_index("faculty_id")
    nodes = sorted(first_pub.index)
    assert set(pairs.author_a_id) | set(pairs.author_b_id) <= set(nodes), "edge with a non-faculty node"
    # every link starts no earlier than both people's first paper
    assert (pairs.first_year >= np.maximum(first_pub[pairs.author_a_id].values,
                                           first_pub[pairs.author_b_id].values)).all()
    return pairs, first_pub, info, nodes


def graph_at(t, pairs, first_pub):
    G = nx.Graph()
    G.add_nodes_from(first_pub.index[first_pub <= t])
    p = pairs[pairs.first_year <= t]
    G.add_weighted_edges_from(zip(p.author_a_id, p.author_b_id, p.papers))
    return G


# ---------------------------------------------------------------- 1. growth
def growth(pairs, first_pub, info):
    dept = info.department.to_dict()
    inst = info.institution.to_dict()
    rows = []
    prev_edges = set()
    for t in range(FIRST, LAST + 1):
        G = graph_at(t, pairs, first_pub)
        n, e = G.number_of_nodes(), G.number_of_edges()
        comps = sorted(nx.connected_components(G), key=len, reverse=True)
        lcc = G.subgraph(comps[0])
        # distances between all connected pairs (whole graph, as in Leskovec et al.)
        dists = [d for _, dd in nx.all_pairs_shortest_path_length(G) for d in dd.values() if d > 0]
        edges = {tuple(sorted(x)) for x in G.edges}
        new = edges - prev_edges
        prev_edges = edges
        rows.append({
            "year": t,
            "partial_year": t == PARTIAL_YEAR,
            "faculty_nodes": n,
            "connected_faculty": sum(1 for v in G if G.degree(v) > 0),
            "links": e,
            "new_links_this_year": len(new),
            "avg_degree": 2 * e / n,
            "density": nx.density(G),
            "components": len(comps),
            "largest_component": len(comps[0]),
            "largest_component_share": len(comps[0]) / n,
            "diameter_largest_component": nx.diameter(lcc),
            "avg_path_largest_component": nx.average_shortest_path_length(lcc),
            "effective_diameter_90pct": float(np.percentile(dists, 90)),
            "avg_clustering": nx.average_clustering(G),
            "transitivity": nx.transitivity(G),
            "modularity_louvain": nx.community.modularity(
                G, nx.community.louvain_communities(G, weight="weight", seed=SEED), weight="weight"),
            "cross_nit_links": sum(inst[a] != inst[b] for a, b in edges),
            "cross_department_link_share": np.mean([dept[a] != dept[b] for a, b in edges]) if edges else 0,
        })
    g = pd.DataFrame(rows)
    assert g.links.iloc[-1] == len(pairs) and g.new_links_this_year.sum() == len(pairs)
    assert g.faculty_nodes.iloc[-1] == len(first_pub)

    def fit(x_col, years):
        d = g[g.year.isin(years)]
        r = stats.linregress(np.log(d[x_col]), np.log(d.links))
        return {"exponent_a": r.slope, "r_squared": r.rvalue ** 2, "years": f"{min(years)}-{max(years)}",
                "x": x_col}

    dens = {
        "all_faculty_2016_2026": fit("faculty_nodes", range(FIRST, LAST + 1)),
        "all_faculty_2016_2025": fit("faculty_nodes", range(FIRST, LAST)),
        "connected_faculty_2016_2026": fit("connected_faculty", range(FIRST, LAST + 1)),
        # robustness: skip the start-up years, when pre-2016 collaborations are still invisible
        "all_faculty_2019_2025": fit("faculty_nodes", range(2019, LAST)),
        "connected_faculty_2019_2025": fit("connected_faculty", range(2019, LAST)),
    }
    return g, dens


# ---------------------------------------------------------------- 2. triadic closure
def bucket(cn, dist3):
    if cn >= 3:
        return "3+ common co-authors"
    if cn == 2:
        return "2 common co-authors"
    if cn == 1:
        return "1 common co-author"
    return "distance 3 (friend of a friend of a friend)" if dist3 else "farther apart / not connected"


ORDER = ["3+ common co-authors", "2 common co-authors", "1 common co-author",
         "distance 3 (friend of a friend of a friend)", "farther apart / not connected"]


def triadic_closure(pairs, first_pub, info):
    nodes = list(first_pub.index)
    idx = {v: i for i, v in enumerate(nodes)}
    dept = info.department.reindex(nodes).values
    inst = info.institution.reindex(nodes).values
    first_link = {}
    for a, b, y in zip(pairs.author_a_id, pairs.author_b_id, pairs.first_year):
        first_link[(idx[a], idx[b])] = first_link[(idx[b], idx[a])] = y
    joined = first_pub.reindex(nodes).values
    iu, ju = np.triu_indices(len(nodes), k=1)
    link_year = np.array([first_link.get((i, j), 9999) for i, j in zip(iu, ju)])

    records = []   # one row per (t, bucket, same_dept, same_inst) with counts
    sources = []   # where the new links of year t+1 come from
    for t in range(FIRST, LAST):
        A = np.zeros((len(nodes), len(nodes)), dtype=np.int32)
        p = pairs[pairs.first_year <= t]
        for a, b in zip(p.author_a_id, p.author_b_id):
            A[idx[a], idx[b]] = A[idx[b], idx[a]] = 1
        CN = A @ A
        reach3 = (CN @ A) > 0
        present = joined <= t
        cand = present[iu] & present[ju] & (A[iu, ju] == 0)          # not yet co-authors, both active
        cn = CN[iu, ju][cand]
        d3 = reach3[iu, ju][cand]
        ly = link_year[cand]
        df = pd.DataFrame({
            "bucket": [bucket(c, d) for c, d in zip(cn, d3)],
            "same_department": dept[iu][cand] == dept[ju][cand],
            "same_institute": inst[iu][cand] == inst[ju][cand],
            "linked_next_year": ly == t + 1,
            "linked_within_3_years": (ly > t) & (ly <= t + 3),
        })
        df["year"] = t
        df["window_3y_complete"] = t + 3 <= LAST - 1   # 2026 is partial
        records.append(df.groupby(["year", "bucket", "same_department", "same_institute", "window_3y_complete"])
                         .agg(pairs=("linked_next_year", "size"),
                              linked_next_year=("linked_next_year", "sum"),
                              linked_within_3_years=("linked_within_3_years", "sum"))
                         .reset_index())

        # new links formed in t+1: closing a triangle, between existing faculty without a common
        # co-author, or involving someone whose first paper is in t+1
        new = pairs[pairs.first_year == t + 1]
        kinds = {"closed a triangle (had a common co-author)": 0,
                 "existing faculty, no common co-author": 0,
                 "involves faculty new to the network": 0}
        for a, b in zip(new.author_a_id, new.author_b_id):
            i, j = idx[a], idx[b]
            if not (present[i] and present[j]):
                kinds["involves faculty new to the network"] += 1
            elif CN[i, j] > 0:
                kinds["closed a triangle (had a common co-author)"] += 1
            else:
                kinds["existing faculty, no common co-author"] += 1
        sources.append({"year": t + 1, "partial_year": t + 1 == PARTIAL_YEAR, **kinds})

    rec = pd.concat(records, ignore_index=True)
    src = pd.DataFrame(sources)
    # consistency: every link formed in 2017..2026 is classified exactly once
    assert src.drop(columns=["year", "partial_year"]).values.sum() == (pairs.first_year > FIRST).sum()
    assert rec.linked_next_year.sum() == src["closed a triangle (had a common co-author)"].sum() \
        + src["existing faculty, no common co-author"].sum()
    return rec, src


def summarise_closure(rec):
    def table(d, by):
        s = d.groupby(by).agg(pairs=("pairs", "sum"), linked_next_year=("linked_next_year", "sum"),
                              linked_within_3_years=("linked_within_3_years", "sum")).reset_index()
        s["p_next_year_pct"] = 100 * s.linked_next_year / s.pairs
        s["p_within_3_years_pct"] = 100 * s.linked_within_3_years / s.pairs
        return s

    main = table(rec, ["bucket"])
    main3 = table(rec[rec.window_3y_complete], ["bucket"])[["bucket", "p_within_3_years_pct"]]
    main = main.drop(columns=["linked_within_3_years", "p_within_3_years_pct"]).merge(main3, on="bucket")
    base = main.set_index("bucket").loc["farther apart / not connected", "p_next_year_pct"]
    main["times_more_likely_than_far_pairs"] = main.p_next_year_pct / base
    main = main.set_index("bucket").loc[ORDER].reset_index()

    rec = rec.assign(friend_of_friend=rec.bucket.str.contains("common"))
    by_dept = table(rec, ["friend_of_friend", "same_department"])
    by_inst = table(rec, ["friend_of_friend", "same_institute"])
    by_year = table(rec, ["year", "friend_of_friend"])
    return main, by_dept, by_inst, by_year


# ---------------------------------------------------------------- charts
def charts(g, dens, main, src):
    full = g[~g.partial_year]
    fig, ax = plt.subplots(2, 2, figsize=(12, 8))
    a = ax[0, 0]
    a.plot(g.year, g.faculty_nodes, "o-", label="faculty (nodes)")
    a.plot(g.year, g.links, "s-", label="co-author links (edges)")
    a.set_title("Network size (cumulative)"); a.legend(); a.set_xlabel("year")
    a = ax[0, 1]
    a.plot(g.year, g.avg_degree, "o-", color="C2")
    a.set_title("Average number of faculty co-authors"); a.set_xlabel("year")
    a = ax[1, 0]
    a.plot(g.year, 100 * g.largest_component_share, "o-", color="C3", label="largest group (% of faculty)")
    a.plot(g.year, 100 * g.connected_faculty / g.faculty_nodes, "s--", color="C4", label="faculty with ≥1 faculty co-author (%)")
    a.set_ylim(0, 100); a.set_title("Connectedness"); a.legend(); a.set_xlabel("year")
    a = ax[1, 1]
    a.plot(g.year, g.effective_diameter_90pct, "o-", label="effective diameter (90%)")
    a.plot(g.year, g.diameter_largest_component, "s--", label="diameter (largest group)")
    a.plot(g.year, g.avg_path_largest_component, "^-", label="average path (largest group)")
    a.set_title("Distances (steps between faculty)"); a.legend(); a.set_xlabel("year")
    for a in ax.flat:
        a.axvspan(PARTIAL_YEAR - 0.5, PARTIAL_YEAR + 0.5, color="grey", alpha=0.12)
        a.grid(alpha=0.3)
    fig.suptitle("Growth of the NIT Trichy + NIT Surathkal faculty co-authorship network (cumulative from 2016; 2026 partial, shaded)")
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "growth_over_time.png"), dpi=150); plt.close(fig)

    fig, a = plt.subplots(figsize=(6, 5))
    a.loglog(g.faculty_nodes, g.links, "o")
    for x, y, t in zip(g.faculty_nodes, g.links, g.year):
        a.annotate(str(t), (x, y), fontsize=7, xytext=(3, -8), textcoords="offset points")
    f = dens["all_faculty_2016_2026"]
    xs = np.linspace(g.faculty_nodes.min(), g.faculty_nodes.max(), 50)
    c = np.exp(np.mean(np.log(g.links) - f["exponent_a"] * np.log(g.faculty_nodes)))
    a.loglog(xs, c * xs ** f["exponent_a"], "-", label=f"fit: E ∝ N^{f['exponent_a']:.2f} (R²={f['r_squared']:.3f})")
    a.loglog(xs, g.links.iloc[0] / g.faculty_nodes.iloc[0] * xs, ":", color="grey", label="E ∝ N (no densification)")
    a.set_xlabel("faculty in network N(t)"); a.set_ylabel("co-author links E(t)")
    a.set_title("Densification law"); a.legend(fontsize=8); a.grid(alpha=0.3, which="both")
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "densification_loglog.png"), dpi=150); plt.close(fig)

    fig, ax = plt.subplots(1, 2, figsize=(13, 4.8))
    a = ax[0]
    labels = ["3+ common", "2 common", "1 common", "distance 3", "farther /\nnot connected"]
    bars = a.bar(labels, main.p_next_year_pct, color=["C3", "C1", "C0", "C7", "C7"])
    for b, v in zip(bars, main.p_next_year_pct):
        a.text(b.get_x() + b.get_width() / 2, v, f"{v:.2f}%", ha="center", va="bottom", fontsize=8)
    a.set_yscale("log"); a.set_ylabel("chance of first joint paper next year (%, log scale)")
    a.set_title("Do friends of friends become co-authors?"); a.grid(alpha=0.3, axis="y")
    a = ax[1]
    s = src[~src.partial_year].set_index("year").drop(columns="partial_year")
    s.plot(kind="bar", stacked=True, ax=a, color=["C3", "C0", "C2"])
    a.set_title("Where each year's new faculty–faculty links come from"); a.set_ylabel("new links")
    a.legend(fontsize=8); a.grid(alpha=0.3, axis="y")
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "triadic_closure.png"), dpi=150); plt.close(fig)


# ---------------------------------------------------------------- network parts (1 + 2)
def network_part():
    pairs, first_pub, info, nodes = load()

    g, dens = growth(pairs, first_pub, info)
    g.to_csv(os.path.join(OUT, "growth_by_year.csv"), index=False)

    rec, src = triadic_closure(pairs, first_pub, info)
    main_t, by_dept, by_inst, by_year = summarise_closure(rec)
    main_t.to_csv(os.path.join(OUT, "triadic_closure_by_common_coauthors.csv"), index=False)
    by_dept.to_csv(os.path.join(OUT, "triadic_closure_by_department.csv"), index=False)
    by_inst.to_csv(os.path.join(OUT, "triadic_closure_by_institute.csv"), index=False)
    by_year.to_csv(os.path.join(OUT, "triadic_closure_by_year.csv"), index=False)
    src.to_csv(os.path.join(OUT, "new_link_sources_by_year.csv"), index=False)
    rec.to_csv(os.path.join(OUT, "triadic_closure_raw_counts.csv"), index=False)

    charts(g, dens, main_t, src)

    full_src = src[~src.partial_year]
    tot = full_src.drop(columns=["year", "partial_year"]).sum()
    summary = {
        "network": "faculty-only co-authorship (NIT Trichy + NIT Surathkal), cumulative from 2016",
        "faculty": len(nodes), "links_2026": int(len(pairs)),
        "densification": dens,
        "growth_first_last": g.iloc[[0, -2, -1]].to_dict(orient="records"),
        "triadic_closure_next_year": main_t.to_dict(orient="records"),
        "new_links_2017_2025_by_source": tot.to_dict(),
        "new_links_2017_2025_closing_triangle_pct": 100 * tot.iloc[0] / tot.sum(),
    }
    with open(os.path.join(OUT, "insights_summary.json"), "w") as f:
        json.dump(summary, f, indent=2, default=float)
    pd.set_option("display.width", 200)
    print(g.round(3).to_string(index=False))
    print(json.dumps(dens, indent=2))
    print(main_t.round(3).to_string(index=False))
    print(by_dept.round(3).to_string(index=False))
    print(by_inst.round(3).to_string(index=False))
    print(src.to_string(index=False))


# ---------------------------------------------------------------- shared helpers for parts 3-5
RAW = os.path.join(DATA, "raw")
FULL_YEARS = range(FIRST, PARTIAL_YEAR)          # 2016-2025, complete years only
NITS = {"NIT Trichy": "I122964287", "NIT Surathkal": "I11880225"}
COMPUTING = {"CSE", "Information Technology", "Computer Applications"}


def dept_papers():
    """One row per (paper, department): a paper with faculty from two departments counts for both."""
    g = pd.read_csv(os.path.join(DATA, "group12_data.csv"), low_memory=False)
    return g.drop_duplicates(["openalex_id", "department"])[
        ["openalex_id", "department", "institution", "year", "title", "subfield", "fwci"]]


def raw_works(ids):
    out = {}
    for name in NITS:
        for line in open(os.path.join(RAW, name.replace(" ", "_") + "_works.jsonl"), encoding="utf-8"):
            w = json.loads(line)
            wid = w["id"].rsplit("/", 1)[-1]
            if wid in ids:
                out[wid] = w
    return out


def save(df, name):
    df.to_csv(os.path.join(OUT, name), index=False)


# ---------------------------------------------------------------- 3. AI across departments
AI_SUBFIELDS = {"Artificial Intelligence", "Computer Vision and Pattern Recognition"}
# case-insensitive phrases; "transformer" alone is avoided (power transformers in EEE), as is "GAN" (GaN = gallium nitride)
AI_PHRASES = (r"machine[- ]learning|deep[- ]learning|neural[- ]network|artificial intelligence|convolutional|"
              r"recurrent neural|long short[- ]term memory|random forest|support vector|xgboost|gradient boost|"
              r"k-nearest|reinforcement learning|federated learning|transfer learning|generative adversarial|"
              r"autoencoder|large language model|natural language processing|decision tree|ensemble learning|"
              r"graph neural|vision transformer|explainable ai|attention[- ]based|self-supervised|semi-supervised|"
              r"unsupervised learning|supervised learning|learning[- ]based|data[- ]driven model|chatgpt|yolo|u-net")
# case-sensitive acronyms (so "Al" for aluminium or "Hilbert" never match)
AI_ACRONYMS = r"\b(?:AI|ANNs?|CNNs?|LSTMs?|SVMs?|KNN|NLP|LLMs?|GPT|RNNs?|DNNs?|GNNs?|XAI)\b|\b\w*BERT\b"
AI_METHODS = [  # first match wins, in this order
    ("language models / NLP", r"(?i:large language model|natural language processing|chatgpt)|\bLLMs?\b|\bNLP\b|\bGPT\b|\b\w*BERT\b"),
    ("deep learning", r"(?i:deep[- ]learning|convolutional|recurrent neural|long short[- ]term memory|autoencoder|"
                      r"generative adversarial|vision transformer|graph neural|yolo|u-net|attention[- ]based)"
                      r"|\b(?:CNNs?|LSTMs?|RNNs?|DNNs?|GNNs?)\b"),
    ("neural networks (ANN)", r"(?i:neural[- ]network)|\bANNs?\b"),
    ("classical machine learning", r"(?i:random forest|support vector|xgboost|gradient boost|k-nearest|decision tree|"
                                   r"ensemble learning|reinforcement learning|supervised learning|transfer learning|"
                                   r"federated learning|self-supervised|semi-supervised)|\b(?:SVMs?|KNN)\b"),
    ("AI / machine learning (general)", r"(?i:machine[- ]learning|artificial intelligence|explainable ai|"
                                        r"learning[- ]based|data[- ]driven model)|\b(?:AI|XAI)\b"),
]


def ai_method(title):
    for name, pat in AI_METHODS:
        if re.search(pat, title):
            return name
    return ""


def ai_part():
    dp = dept_papers()
    titles = dp.title.fillna("")
    dp["ai_by_topic"] = dp.subfield.isin(AI_SUBFIELDS)
    dp["ai_by_title"] = titles.str.contains(AI_PHRASES, case=False, regex=True) | \
        titles.str.contains(AI_ACRONYMS, case=True, regex=True)
    dp["ai"] = dp.ai_by_topic | dp.ai_by_title
    dp["method"] = [ai_method(t) if a else "" for t, a in zip(titles, dp.ai_by_title)]
    dp.loc[dp.ai & (dp.method == ""), "method"] = "AI topic (no method in title)"
    dp["computing"] = dp.department.isin(COMPUTING)

    papers = dp.drop_duplicates("openalex_id")
    save(dp[dp.ai][["openalex_id", "year", "department", "institution", "title", "subfield", "ai_by_topic",
                    "ai_by_title", "method", "fwci"]].sort_values(["department", "year"]), "ai_papers.csv")

    by_dy = dp.groupby(["department", "year"]).agg(papers=("ai", "size"), ai_papers=("ai", "sum")).reset_index()
    by_dy["ai_share_pct"] = 100 * by_dy.ai_papers / by_dy.papers
    by_dy["partial_year"] = by_dy.year == PARTIAL_YEAR
    save(by_dy, "ai_share_by_department_year.csv")

    def share(d):
        return 100 * d.ai.mean() if len(d) else np.nan

    rows = []
    for dept, d in dp.groupby("department"):
        early, late = d[d.year.between(2016, 2018)], d[d.year.between(2023, 2025)]
        ai_f, non_f = d.fwci[d.ai].dropna(), d.fwci[~d.ai].dropna()
        p = stats.mannwhitneyu(ai_f, non_f).pvalue if len(ai_f) >= 5 and len(non_f) >= 5 else np.nan
        rows.append({
            "department": dept, "computing_department": dept in COMPUTING,
            "papers": len(d), "ai_papers": int(d.ai.sum()), "ai_share_pct": share(d),
            "papers_2016_2018": len(early), "ai_share_2016_2018_pct": share(early),
            "papers_2023_2025": len(late), "ai_share_2023_2025_pct": share(late),
            "change_pct_points": share(late) - share(early),
            "first_ai_year": int(d.year[d.ai].min()) if d.ai.any() else None,
            "ai_mean_fwci": ai_f.mean(), "other_mean_fwci": non_f.mean(),
            "ai_median_fwci": ai_f.median(), "other_median_fwci": non_f.median(),
            "fwci_difference_p_value": p,
        })
    by_d = pd.DataFrame(rows).sort_values("ai_share_2023_2025_pct", ascending=False)
    save(by_d, "ai_by_department.csv")

    by_y = (dp.groupby(["year", "computing"]).agg(papers=("ai", "size"), ai_papers=("ai", "sum")).reset_index())
    by_y["ai_share_pct"] = 100 * by_y.ai_papers / by_y.papers
    allp = papers.groupby("year").agg(papers=("ai", "size"), ai_papers=("ai", "sum")).reset_index()
    allp["computing"] = "all papers"
    allp["ai_share_pct"] = 100 * allp.ai_papers / allp.papers
    by_y = pd.concat([by_y.assign(computing=by_y.computing.map({True: "computing departments",
                                                                False: "other departments"})), allp])
    by_y["partial_year"] = by_y.year == PARTIAL_YEAR
    save(by_y, "ai_share_by_year.csv")

    non = dp[~dp.computing & dp.ai]
    meth = (non.assign(period=np.where(non.year <= 2020, "2016-2020", "2021-2026"))
               .groupby(["period", "method"]).size().unstack(0, fill_value=0))
    meth = meth.reset_index()
    save(meth, "ai_methods_outside_computing.csv")

    # charts: heatmap department x year, and trend lines
    order = by_d.sort_values("ai_share_2023_2025_pct", ascending=False).department.tolist()
    heat = by_dy.pivot(index="department", columns="year", values="ai_share_pct").reindex(order)
    fig, ax = plt.subplots(figsize=(11, 7))
    im = ax.imshow(heat.values, aspect="auto", cmap="viridis")
    ax.set_xticks(range(len(heat.columns)), [f"{y}*" if y == PARTIAL_YEAR else str(y) for y in heat.columns])
    ax.set_yticks(range(len(heat.index)), heat.index)
    for i in range(heat.shape[0]):
        for j in range(heat.shape[1]):
            v = heat.values[i, j]
            if not np.isnan(v):
                ax.text(j, i, f"{v:.0f}", ha="center", va="center", fontsize=7,
                        color="white" if v < heat.values[~np.isnan(heat.values)].max() * 0.6 else "black")
    fig.colorbar(im, label="AI papers (% of the department's papers)")
    ax.set_title("Share of AI / machine-learning papers by department and year (*2026 partial)")
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "ai_heatmap.png"), dpi=150); plt.close(fig)

    fig, ax = plt.subplots(1, 2, figsize=(13, 4.8))
    for label, d in by_y[by_y.year.isin(FULL_YEARS)].groupby("computing"):
        ax[0].plot(d.year, d.ai_share_pct, "o-", label=label)
    ax[0].set_title("AI share of papers, 2016-2025"); ax[0].set_ylabel("% of papers"); ax[0].legend()
    ax[0].grid(alpha=0.3)
    b = by_d[~by_d.computing_department & (by_d.papers_2016_2018 >= 30) & (by_d.papers_2023_2025 >= 30)] \
        .sort_values("ai_share_2023_2025_pct")
    yy = np.arange(len(b))
    ax[1].barh(yy - 0.2, b.ai_share_2016_2018_pct, 0.4, color="C7", label="2016-2018")
    ax[1].barh(yy + 0.2, b.ai_share_2023_2025_pct, 0.4, color="C1", label="2023-2025")
    ax[1].set_yticks(yy, b.department)
    ax[1].set_xlabel("AI share of papers (%)")
    ax[1].set_title("Non-computing departments (≥30 papers in both periods)")
    ax[1].legend(); ax[1].grid(alpha=0.3, axis="x")
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "ai_trend.png"), dpi=150); plt.close(fig)

    summary = {
        "definition": "AI if OpenAlex subfield in AI_SUBFIELDS, or the title matches AI_PHRASES / AI_ACRONYMS",
        "ai_papers": int(papers.ai.sum()), "papers": len(papers),
        "ai_by_topic_only": int((papers.ai_by_topic & ~papers.ai_by_title).sum()),
        "ai_by_title_only": int((papers.ai_by_title & ~papers.ai_by_topic).sum()),
        "ai_by_both": int((papers.ai_by_title & papers.ai_by_topic).sum()),
        "departments_with_ai_share_ge_5pct_2016_2018": int((by_d.ai_share_2016_2018_pct >= 5).sum()),
        "departments_with_ai_share_ge_5pct_2023_2025": int((by_d.ai_share_2023_2025_pct >= 5).sum()),
        "departments": len(by_d),
    }
    with open(os.path.join(OUT, "ai_summary.json"), "w") as f:
        json.dump(summary, f, indent=2, default=float)
    pd.set_option("display.width", 250)
    print(json.dumps(summary, indent=2))
    print(by_d.round(2).to_string(index=False))
    print(by_y[by_y.computing == "all papers"].round(1).to_string(index=False))
    print(meth.to_string(index=False))


# ---------------------------------------------------------------- 4. how recent is the cited work
PRICE_MAX_AGE = 4   # Price index: references from the citing year and the 4 years before (the last 5 years)


def recency_part():
    path = os.path.join(RAW, "ref_years.jsonl")
    if not os.path.exists(path):
        sys.exit("run `python fetch_insights.py refyears` first")
    ref_year = {}
    for line in open(path, encoding="utf-8"):
        r = json.loads(line)
        ref_year[r["id"]] = r["year"]
    dp = dept_papers()
    works = raw_works(set(dp.openalex_id))

    per_paper, ages_all, missing, negative = [], [], 0, 0
    for wid, w in works.items():
        y = w["publication_year"]
        ages = []
        for r in w["referenced_works"]:
            ry = ref_year.get(r.rsplit("/", 1)[-1])
            if ry is None:
                missing += 1
            elif y - ry < 0:
                negative += 1   # cited work dated after the citing paper (preprint / version issues)
            else:
                ages.append(y - ry)
        ages = np.array(ages)
        per_paper.append({"openalex_id": wid, "refs_with_year": len(ages),
                          "recent_refs": int((ages <= PRICE_MAX_AGE).sum()),
                          "old_refs_over_20y": int((ages > 20).sum()),
                          "age_sum": int(ages.sum()) if len(ages) else 0,
                          "median_age": float(np.median(ages)) if len(ages) else np.nan})
        ages_all.append(ages)
    pp = pd.DataFrame(per_paper)
    pp["price_index_pct"] = 100 * pp.recent_refs / pp.refs_with_year.replace(0, np.nan)
    total_refs = sum(len(w["referenced_works"]) for w in works.values())
    all_ages = np.concatenate(ages_all)
    assert len(all_ages) + missing + negative == total_refs

    dpp = dp.merge(pp, on="openalex_id")

    def pooled(d):
        n = d.refs_with_year.sum()
        return pd.Series({"papers": d.openalex_id.nunique(), "references_with_year": int(n),
                          "price_index_pct": 100 * d.recent_refs.sum() / n,
                          "mean_reference_age": d.age_sum.sum() / n,
                          "median_of_paper_median_age": d.median_age.median(),
                          "refs_over_20_years_pct": 100 * d.old_refs_over_20y.sum() / n})

    by_d = dpp[dpp.refs_with_year > 0].groupby("department").apply(pooled, include_groups=False).reset_index()
    early = dpp[dpp.year.between(2016, 2018) & (dpp.refs_with_year > 0)].groupby("department") \
        .apply(pooled, include_groups=False).price_index_pct
    late = dpp[dpp.year.between(2023, 2025) & (dpp.refs_with_year > 0)].groupby("department") \
        .apply(pooled, include_groups=False).price_index_pct
    by_d["price_index_2016_2018_pct"] = by_d.department.map(early)
    by_d["price_index_2023_2025_pct"] = by_d.department.map(late)
    by_d = by_d.sort_values("price_index_pct", ascending=False)
    save(by_d, "recency_by_department.csv")

    papers = dpp.drop_duplicates("openalex_id")
    by_y = papers[papers.refs_with_year > 0].groupby("year").apply(pooled, include_groups=False).reset_index()
    by_i = dpp.drop_duplicates(["openalex_id", "institution"])
    by_iy = by_i[by_i.refs_with_year > 0].groupby(["institution", "year"]).apply(pooled, include_groups=False) \
        .reset_index()
    by_y["partial_year"] = by_y.year == PARTIAL_YEAR
    by_iy["partial_year"] = by_iy.year == PARTIAL_YEAR
    save(by_y, "recency_by_year.csv")
    save(by_iy, "recency_by_institute_year.csv")

    hist = pd.Series(all_ages).clip(upper=40).value_counts().sort_index()
    save(pd.DataFrame({"reference_age_years (40 = 40+)": hist.index, "references": hist.values}),
         "reference_age_distribution.csv")

    # does citing recent work go with higher impact? papers with >= 10 dated references and an FWCI
    q = papers[(papers.refs_with_year >= 10) & papers.fwci.notna()].copy()
    q["price_quintile"] = pd.qcut(q.price_index_pct.rank(method="first"), 5,
                                  labels=["Q1 (oldest refs)", "Q2", "Q3", "Q4", "Q5 (newest refs)"])
    rvi = q.groupby("price_quintile", observed=True).agg(
        papers=("fwci", "size"), price_index_range=("price_index_pct", lambda s: f"{s.min():.0f}-{s.max():.0f}%"),
        mean_fwci=("fwci", "mean"), median_fwci=("fwci", "median")).reset_index()
    save(rvi, "recency_vs_impact.csv")
    rho_all = stats.spearmanr(q.price_index_pct, q.fwci).statistic
    within = [stats.spearmanr(d.price_index_pct, d.fwci).statistic
              for _, d in dpp[dpp.openalex_id.isin(q.openalex_id)].groupby("department") if len(d) >= 50]

    fig, ax = plt.subplots(1, 2, figsize=(14, 6))
    b = by_d.sort_values("price_index_pct")
    ax[0].barh(b.department, b.price_index_pct, color=["C1" if d in COMPUTING else "C0" for d in b.department])
    for y_, (v, m) in enumerate(zip(b.price_index_pct, b.mean_reference_age)):
        ax[0].text(v + 0.5, y_, f"{v:.0f}%  (mean age {m:.1f} y)", va="center", fontsize=8)
    ax[0].set_xlabel("Price index: % of references at most 4 years older than the paper")
    ax[0].set_title("How recent is the work each department cites? (orange = computing)")
    ax[0].set_xlim(0, b.price_index_pct.max() * 1.35); ax[0].grid(alpha=0.3, axis="x")
    for inst, d in by_iy[by_iy.year.isin(FULL_YEARS)].groupby("institution"):
        ax[1].plot(d.year, d.price_index_pct, "o-", label=inst)
    ax[1].set_title("Price index by year"); ax[1].set_ylabel("% recent references"); ax[1].legend()
    ax[1].grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "recency_by_department.png"), dpi=150); plt.close(fig)

    summary = {
        "price_index_definition": f"share of references at most {PRICE_MAX_AGE} years older than the citing paper",
        "references_total": total_refs, "references_with_year": int(len(all_ages)),
        "references_year_unknown": missing, "references_dated_after_citing_paper_excluded": negative,
        "overall_price_index_pct": 100 * float((all_ages <= PRICE_MAX_AGE).mean()),
        "overall_mean_reference_age": float(all_ages.mean()),
        "overall_median_reference_age": float(np.median(all_ages)),
        "spearman_price_index_vs_fwci_all_papers": rho_all,
        "spearman_price_index_vs_fwci_mean_within_department": float(np.mean(within)),
        "papers_in_impact_test": len(q),
    }
    with open(os.path.join(OUT, "recency_summary.json"), "w") as f:
        json.dump(summary, f, indent=2, default=float)
    pd.set_option("display.width", 250)
    print(json.dumps(summary, indent=2))
    print(by_d.round(2).to_string(index=False))
    print(by_y.round(2).to_string(index=False))
    print(rvi.round(3).to_string(index=False))


# ---------------------------------------------------------------- 5. geography
BANDS = [0, 100, 300, 600, 1000, 1500, 4000]
BAND_LABELS = ["<100 km", "100-300 km", "300-600 km", "600-1000 km", "1000-1500 km", ">1500 km"]


def haversine_km(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi, dlmb = p2 - p1, np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlmb / 2) ** 2
    return 2 * 6371.0 * np.arcsin(np.sqrt(a))


def poisson_fit(y, X, names):
    """Poisson regression by Newton-Raphson, with robust (sandwich) standard errors."""
    beta = np.zeros(X.shape[1])
    beta[0] = math.log(y.mean() + 1e-9)
    for _ in range(100):
        mu = np.exp(X @ beta)
        H = X.T @ (X * mu[:, None])
        step = np.linalg.solve(H, X.T @ (y - mu))
        beta += step
        if np.abs(step).max() < 1e-10:
            break
    mu = np.exp(X @ beta)
    Hinv = np.linalg.inv(X.T @ (X * mu[:, None]))
    meat = X.T @ (X * ((y - mu) ** 2)[:, None])
    se = np.sqrt(np.diag(Hinv @ meat @ Hinv))
    z = beta / se
    return pd.DataFrame({"term": names, "coef": beta, "robust_se": se, "z": z,
                         "p_value": 2 * stats.norm.sf(np.abs(z))})


def geo_part():
    path = os.path.join(RAW, "institutions_geo.jsonl")
    if not os.path.exists(path):
        sys.exit("run `python fetch_insights.py geo` first")
    geo = pd.DataFrame([json.loads(l) for l in open(path, encoding="utf-8")]).drop_duplicates("id").set_index("id")
    ic = pd.read_csv(os.path.join(DATA, "indian_connections.csv"))
    ic = ic.join(geo[["lat", "lon", "works_count", "city"]], on="partner_id")
    n_all = len(ic)
    ic = ic[ic.lat.notna() & (ic.works_count.fillna(0) > 0)].copy()
    home = {k: geo.loc[v, ["lat", "lon"]].astype(float).values for k, v in NITS.items()}
    ic["distance_km"] = [haversine_km(*home[i], la, lo) for i, la, lo in zip(ic.your_inst, ic.lat, ic.lon)]
    ic["citations_exchanged"] = ic.cites_from_partner + ic.cites_to_partner
    ic["coauthored"] = ic.shared_papers > 0
    ic["band"] = pd.cut(ic.distance_km, BANDS, labels=BAND_LABELS, right=False)
    save(ic[["your_inst", "partner_inst", "partner_id", "city", "partner_cluster", "distance_km", "shared_papers",
             "total_citations", "cites_from_partner", "cites_to_partner", "citations_exchanged", "works_count"]]
         .sort_values(["your_inst", "shared_papers"], ascending=[True, False]), "geo_partners.csv")

    def bands(d):
        t = d.groupby("band", observed=False).agg(
            linked_partners=("partner_id", "size"), coauthor_partners=("coauthored", "sum"),
            shared_papers=("shared_papers", "sum"), citations_exchanged=("citations_exchanged", "sum")).reset_index()
        t["pct_partners_coauthored"] = 100 * t.coauthor_partners / t.linked_partners
        t["pct_of_all_shared_papers"] = 100 * t.shared_papers / t.shared_papers.sum()
        t["pct_of_all_citations_exchanged"] = 100 * t.citations_exchanged / t.citations_exchanged.sum()
        t["shared_papers_per_100_citations"] = 100 * t.shared_papers / t.citations_exchanged.replace(0, np.nan)
        return t

    tb = pd.concat([bands(d).assign(your_inst=i) for i, d in ic.groupby("your_inst")] +
                   [bands(ic).assign(your_inst="both NITs")])
    save(tb, "geo_distance_bands.csv")

    # gravity model: E[y] = exp(b0 + b1 log(partner size) + b2 log(distance) + b3 Surathkal)
    d = ic.copy()
    X = np.column_stack([np.ones(len(d)), np.log(d.works_count), np.log(d.distance_km.clip(lower=10)),
                         (d.your_inst == "NIT Surathkal").astype(float)])
    names = ["intercept", "log partner size (works)", "log distance (km)", "NIT Surathkal"]
    grav = pd.concat([poisson_fit(d.shared_papers.values.astype(float), X, names).assign(outcome="joint papers"),
                      poisson_fit(d.citations_exchanged.values.astype(float), X, names)
                      .assign(outcome="citations exchanged")])
    save(grav, "geo_gravity_model.csv")

    # chart 1: distance bands, collaboration vs citation share
    both = tb[tb.your_inst == "both NITs"]
    fig, ax = plt.subplots(1, 2, figsize=(13, 4.8))
    x = np.arange(len(both))
    ax[0].bar(x - 0.2, both.pct_of_all_shared_papers, 0.4, label="joint papers")
    ax[0].bar(x + 0.2, both.pct_of_all_citations_exchanged, 0.4, label="citations exchanged")
    ax[0].set_xticks(x, both.band, rotation=20); ax[0].set_ylabel("% of all links with Indian partners")
    ax[0].set_title("Distance from our NIT: collaboration vs citation"); ax[0].legend(); ax[0].grid(alpha=0.3, axis="y")
    ax[1].plot(x, both.pct_partners_coauthored, "o-", color="C2")
    ax[1].set_xticks(x, both.band, rotation=20)
    ax[1].set_ylabel("% of linked institutes we co-author with")
    ax[1].set_title("Chance a citation partner is also a co-author"); ax[1].grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "geo_distance_decay.png"), dpi=150); plt.close(fig)

    # chart 2: map-like scatter of partners (lon/lat), size = joint papers
    fig, ax = plt.subplots(1, 2, figsize=(13, 7.5))
    for a, (inst, dd) in zip(ax, ic.groupby("your_inst")):
        c = dd[~dd.coauthored]
        a.scatter(c.lon, c.lat, s=4, color="lightgrey", label="citation link only")
        k = dd[dd.coauthored]
        a.scatter(k.lon, k.lat, s=8 + 3 * k.shared_papers, alpha=0.6, color="C0" if inst == "NIT Trichy" else "C1",
                  label="co-author partner (size = joint papers)")
        a.scatter(*home[inst][::-1], marker="*", s=400, color="red", edgecolor="black", label=inst, zorder=5)
        top = k.nlargest(8, "shared_papers")
        a.text(0.98, 0.02, "Top co-author partners\n" + "\n".join(
            f"{r.partner_inst[:34]}: {r.shared_papers} papers, "
            + ("same city" if r.distance_km < 5 else f"{r.distance_km:.0f} km") for _, r in top.iterrows()),
            transform=a.transAxes, ha="right", va="bottom", fontsize=6.5,
            bbox=dict(boxstyle="round", facecolor="white", alpha=0.9))
        a.set_xlim(67, 98); a.set_ylim(6, 36); a.set_aspect("equal")
        a.set_title(f"{inst}: Indian partner institutes"); a.set_xlabel("longitude"); a.set_ylabel("latitude")
        leg = a.legend(fontsize=7, loc="upper right")
        for h in leg.legend_handles:
            h.set_sizes([30])
        a.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "geo_partner_map.png"), dpi=150); plt.close(fig)

    w = lambda s, v: np.average(s, weights=v)
    summary = {
        "partners_with_coordinates": len(ic), "partners_dropped_no_coordinates_or_size": n_all - len(ic),
        "median_distance_km_weighted_by_joint_papers": {i: float(d.loc[d.shared_papers > 0].distance_km
                                                                 .repeat(d.loc[d.shared_papers > 0].shared_papers)
                                                                 .median()) for i, d in ic.groupby("your_inst")},
        "median_distance_km_weighted_by_citations": {i: float(d.loc[d.citations_exchanged > 0].distance_km
                                                              .repeat(d.loc[d.citations_exchanged > 0].citations_exchanged)
                                                              .median()) for i, d in ic.groupby("your_inst")},
        "share_joint_papers_within_300km_pct": float(100 * ic.shared_papers[ic.distance_km < 300].sum()
                                                     / ic.shared_papers.sum()),
        "share_citations_within_300km_pct": float(100 * ic.citations_exchanged[ic.distance_km < 300].sum()
                                                  / ic.citations_exchanged.sum()),
        "distance_elasticity_joint_papers": float(grav[(grav.outcome == "joint papers")
                                                       & (grav.term == "log distance (km)")].coef.iloc[0]),
        "distance_elasticity_citations": float(grav[(grav.outcome == "citations exchanged")
                                                    & (grav.term == "log distance (km)")].coef.iloc[0]),
    }
    with open(os.path.join(OUT, "geo_summary.json"), "w") as f:
        json.dump(summary, f, indent=2, default=float)
    pd.set_option("display.width", 250)
    print(json.dumps(summary, indent=2))
    print(tb.round(1).to_string(index=False))
    print(grav.round(4).to_string(index=False))


# ---------------------------------------------------------------- 6. link prediction
TRAIN_END, FIT_END = 2022, 2019     # test: features at 2022 -> links 2023-2026; model fit: 2019 -> 2020-2022
SCORES = ["common_neighbours", "adamic_adar", "jaccard", "resource_allocation", "preferential_attachment"]


def link_features(t, pairs, first_pub, info, rows):
    """Every pair of faculty active by year t who are not yet co-authors, with network scores at end of t."""
    nodes = sorted(first_pub.index[first_pub <= t])
    idx = {v: i for i, v in enumerate(nodes)}
    n = len(nodes)
    A = np.zeros((n, n))
    for a, b in zip(*[pairs[pairs.first_year <= t][c] for c in ("author_a_id", "author_b_id")]):
        A[idx[a], idx[b]] = A[idx[b], idx[a]] = 1
    deg = A.sum(1)
    CN = A @ A
    AA = A @ np.diag(np.where(deg > 1, 1 / np.log(np.maximum(deg, 2)), 0)) @ A
    RA = A @ np.diag(np.where(deg > 0, 1 / np.maximum(deg, 1), 0)) @ A
    iu, ju = np.triu_indices(n, k=1)
    keep = A[iu, ju] == 0
    iu, ju = iu[keep], ju[keep]
    cn = CN[iu, ju]
    union = deg[iu] + deg[ju] - cn
    papers = rows[rows.year <= t].groupby("faculty_id").openalex_id.nunique().reindex(nodes).fillna(0).values
    node = np.array(nodes)
    dept = info.department.reindex(nodes).values
    inst = info.institution.reindex(nodes).values
    return pd.DataFrame({
        "a": node[iu], "b": node[ju],
        "common_neighbours": cn, "adamic_adar": AA[iu, ju], "resource_allocation": RA[iu, ju],
        "jaccard": np.where(union > 0, cn / np.maximum(union, 1), 0),
        "preferential_attachment": deg[iu] * deg[ju],
        "log_papers_sum": np.log1p(papers[iu] + papers[ju]), "log_papers_min": np.log1p(np.minimum(papers[iu], papers[ju])),
        "same_department": (dept[iu] == dept[ju]).astype(float),
        "same_institute": (inst[iu] == inst[ju]).astype(float),
    })


def label(df, pairs, start, end):
    first = {tuple(sorted(k)): y for k, y in zip(zip(pairs.author_a_id, pairs.author_b_id), pairs.first_year)}
    ys = np.array([first.get(tuple(sorted(k)), 9999) for k in zip(df.a, df.b)])
    return ((ys >= start) & (ys <= end)).astype(int)


def model_features(df):
    X = df[["common_neighbours", "adamic_adar", "resource_allocation", "jaccard", "log_papers_sum",
            "log_papers_min", "same_department", "same_institute"]].copy()
    X["log_preferential_attachment"] = np.log1p(df.preferential_attachment)
    return X


def expected_precision_at_k(score, y, k):
    """Precision of the top k, with ties at the cut-off broken at random (exact expectation)."""
    order = np.sort(score)[::-1]
    s = order[k - 1]
    above = score > s
    tie = score == s
    hits = y[above].sum() + (k - above.sum()) * y[tie].sum() / tie.sum()
    return hits / k


def links_part():
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import average_precision_score, roc_auc_score
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    pairs, first_pub, info, nodes = load()
    rows = pd.read_csv(os.path.join(DATA, "group12_data.csv"), usecols=["faculty_id", "year", "openalex_id"])

    fit_df = link_features(FIT_END, pairs, first_pub, info, rows)
    fit_y = label(fit_df, pairs, FIT_END + 1, TRAIN_END)
    test_df = link_features(TRAIN_END, pairs, first_pub, info, rows)
    test_y = label(test_df, pairs, TRAIN_END + 1, LAST)
    # every new 2023-2026 link between faculty active by 2022 is a positive exactly once
    new = pairs[pairs.first_year > TRAIN_END]
    active = set(first_pub.index[first_pub <= TRAIN_END])
    assert test_y.sum() == sum(a in active and b in active for a, b in zip(new.author_a_id, new.author_b_id))

    def make_model():
        return make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, C=1.0))

    model = make_model().fit(model_features(fit_df), fit_y)
    test_scores = {s: test_df[s].values.astype(float) for s in SCORES}
    test_scores["learned model (scores + department + institute)"] = \
        model.predict_proba(model_features(test_df))[:, 1]
    rng = np.random.default_rng(SEED)
    test_scores["random"] = rng.random(len(test_df))

    P = int(test_y.sum())
    ks = [50, 100, P]
    res = []
    for name, sc in test_scores.items():
        r = {"method": name, "candidates": len(sc), "true_new_links": P, "base_rate_pct": 100 * P / len(sc),
             "auc": roc_auc_score(test_y, sc), "average_precision": average_precision_score(test_y, sc),
             "reachable_new_links_pct": 100 * test_y[sc > 0].sum() / P if name != "random" else 100.0}
        for k in ks:
            r[f"precision_at_{k}_pct" if k != P else "precision_at_P_pct"] = 100 * expected_precision_at_k(sc, test_y, k)
        r["lift_at_100"] = r["precision_at_100_pct"] / r["base_rate_pct"]
        res.append(r)
    res = pd.DataFrame(res)
    save(res, "link_prediction_evaluation.csv")

    coefs = pd.DataFrame({"feature": model_features(fit_df).columns,
                          "standardised_coefficient": model[-1].coef_[0]}).sort_values(
        "standardised_coefficient", key=abs, ascending=False)
    save(coefs, "link_prediction_model_coefficients.csv")

    # precision-at-k curve
    kgrid = np.unique(np.logspace(1, np.log10(5000), 40).astype(int))
    curve = pd.DataFrame({"k": kgrid, **{n: [100 * expected_precision_at_k(sc, test_y, k) for k in kgrid]
                                         for n, sc in test_scores.items()}})
    save(curve, "link_prediction_precision_curve.csv")

    # recommendations: refit on the latest period (2022 -> 2023-2026), apply to the full 2026 network
    final = make_model().fit(model_features(test_df), test_y)
    now = link_features(LAST, pairs, first_pub, info, rows)
    now["model_score"] = final.predict_proba(model_features(now))[:, 1]
    current = set(info.index[info.status == "current"])
    now = now[now.a.isin(current) & now.b.isin(current)]
    top = now.nlargest(50, "model_score").copy()
    G = graph_at(LAST, pairs, first_pub)
    name = info.author.to_dict()
    top.insert(0, "rank", range(1, len(top) + 1))
    for side in ("a", "b"):
        top[f"faculty_{side}"] = top[side].map(name)
        top[f"department_{side}"] = top[side].map(info.department)
        top[f"institute_{side}"] = top[side].map(info.institution)
    top["common_coauthors"] = [", ".join(sorted(name[z] for z in set(G[a]) & set(G[b]))[:4])
                               for a, b in zip(top.a, top.b)]
    top = top[["rank", "faculty_a", "department_a", "institute_a", "faculty_b", "department_b", "institute_b",
               "common_neighbours", "common_coauthors", "adamic_adar", "model_score", "a", "b"]] \
        .rename(columns={"common_neighbours": "n_common_coauthors", "a": "faculty_id_a", "b": "faculty_id_b"})
    save(top, "link_prediction_top50_future_pairs.csv")

    # chart
    fig, ax = plt.subplots(1, 2, figsize=(13, 4.8))
    for n_, col in zip(test_scores, ["C0", "C1", "C2", "C3", "C4", "C5", "C7"]):
        ax[0].semilogx(curve.k, curve[n_], "-", color=col, label=n_, lw=2.5 if n_.startswith("learned") else 1.5)
    ax[0].axhline(100 * P / len(test_df), color="grey", ls=":")
    ax[0].set_xlabel("top-k predicted pairs"); ax[0].set_ylabel("precision (% that really collaborated 2023-26)")
    ax[0].set_title("Link prediction: train to 2022, test 2023-2026"); ax[0].legend(fontsize=7); ax[0].grid(alpha=0.3)
    r = res.set_index("method")
    ax[1].barh(r.index, r.auc, color=["C0", "C1", "C2", "C3", "C4", "C5", "C7"])
    for y_, v in enumerate(r.auc):
        ax[1].text(v + 0.005, y_, f"{v:.3f}", va="center", fontsize=8)
    ax[1].axvline(0.5, color="grey", ls=":"); ax[1].set_xlim(0.4, 1.0); ax[1].set_xlabel("AUC (0.5 = random)")
    ax[1].set_title("Ranking quality over all pairs"); ax[1].grid(alpha=0.3, axis="x")
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "link_prediction.png"), dpi=150); plt.close(fig)

    summary = {"fit": f"features {FIT_END} -> links {FIT_END + 1}-{TRAIN_END}",
               "test": f"features {TRAIN_END} -> links {TRAIN_END + 1}-{LAST}",
               "test_candidates": len(test_df), "test_true_new_links": P,
               "fit_candidates": len(fit_df), "fit_true_new_links": int(fit_y.sum()),
               "recommendation_candidates_current_faculty": len(now)}
    with open(os.path.join(OUT, "link_prediction_summary.json"), "w") as f:
        json.dump(summary, f, indent=2, default=float)
    pd.set_option("display.width", 250)
    print(json.dumps(summary, indent=2))
    print(res.round(3).to_string(index=False))
    print(coefs.round(3).to_string(index=False))
    print(top.head(15).drop(columns=["faculty_id_a", "faculty_id_b"]).round(3).to_string(index=False))


# ---------------------------------------------------------------- 7. faculty ranking
MIN_PAPERS = 10
MEASURES = {   # column -> label; all 2016-2026, faculty's own papers (each paper once per person)
    "papers": "papers",
    "citations": "citations",
    "h_index": "h-index (2016-2026)",
    "mean_fwci": "mean FWCI",
    "top10_papers": "top-10%-cited papers",
    "top_venue_papers": "Q1 journal or CORE A*/A papers",
    "if5_papers": "papers in journals with IF > 5",
}


def h_index(cites):
    c = np.sort(np.asarray(cites))[::-1]
    return int((c >= np.arange(1, len(c) + 1)).sum())


def ranking_part():
    g = pd.read_csv(os.path.join(DATA, "group12_data.csv"), low_memory=False)
    info = pd.read_csv(os.path.join(DATA, "faculty.csv")).drop_duplicates("faculty_id").set_index("faculty_id")
    p = g.drop_duplicates(["faculty_id", "openalex_id"]).copy()
    p["top_venue"] = p.quartile.isin(["Q1", "CORE A*", "CORE A"])
    p["if5"] = p.journal_if_2yr > 5
    p["top10"] = p.top10pct == True  # noqa: E712  (column holds True / False / missing)
    m = p.groupby("faculty_id").agg(
        papers=("openalex_id", "size"), citations=("citations", "sum"), h_index=("citations", h_index),
        mean_fwci=("fwci", "mean"), median_fwci=("fwci", "median"), top10_papers=("top10", "sum"),
        top_venue_papers=("top_venue", "sum"), if5_papers=("if5", "sum"),
        q1_papers=("quartile", lambda s: (s == "Q1").sum()),
        core_astar_a_papers=("quartile", lambda s: s.isin(["CORE A*", "CORE A"]).sum()),
        first_year=("year", "min"), last_year=("year", "max"))
    m = m.join(info[["author", "institution", "department", "designation", "status", "h_index"]]
               .rename(columns={"h_index": "career_h_index_openalex"}))
    # cross-check with faculty.csv's own 2016-2026 h-index
    hi = info.h_index_2016_2026.reindex(m.index)
    assert (hi.isna() | (hi == m.h_index)).mean() > 0.99, "h-index differs from faculty.csv"

    ranked = m[(m.status == "current") & (m.papers >= MIN_PAPERS)].copy()
    not_ranked = m.drop(ranked.index).assign(
        reason=lambda d: np.where(d.status != "current", "former faculty", f"fewer than {MIN_PAPERS} papers"))

    def score(d):
        pct = pd.DataFrame({c: 100 * d[c].rank(pct=True, method="average") for c in MEASURES}, index=d.index)
        return pct.mean(axis=1), pct

    ranked["overall_score"], pct = score(ranked)
    for c in MEASURES:
        ranked[f"pct_{c}"] = pct[c]
    ranked["overall_rank"] = ranked.overall_score.rank(ascending=False, method="min").astype(int)
    dep_score = pd.Series(index=ranked.index, dtype=float)
    for _, d in ranked.groupby("department"):
        dep_score.loc[d.index] = score(d)[0]
    ranked["department_score"] = dep_score
    ranked["department_rank"] = ranked.groupby("department").department_score.rank(ascending=False, method="min") \
        .astype(int)
    ranked["department_size_ranked"] = ranked.groupby("department").department_score.transform("size")

    cols = ["overall_rank", "author", "institution", "department", "designation", "overall_score",
            "department_rank", "department_size_ranked", "department_score", *MEASURES, "median_fwci", "q1_papers",
            "core_astar_a_papers", "career_h_index_openalex", "first_year", "last_year",
            *[f"pct_{c}" for c in MEASURES]]
    out = ranked.reset_index()[["faculty_id", *cols]].sort_values("overall_rank")
    save(out.round(2), "faculty_ranking_overall.csv")
    save(out.sort_values(["department", "department_rank"]).round(2), "faculty_ranking_by_department.csv")
    save(not_ranked.reset_index()[["faculty_id", "author", "institution", "department", "status", "reason",
                                   *MEASURES]].round(2), "faculty_not_ranked.csv")

    # how much do the measures agree? (Spearman between measures, ranked faculty)
    corr = ranked[list(MEASURES)].corr(method="spearman")
    save(corr.round(3).reset_index().rename(columns={"index": "measure"}), "faculty_ranking_measure_correlation.csv")
    # robustness: does the top 20 change with quality-weighted scoring?
    w = {c: (2 if c in ("mean_fwci", "top10_papers", "top_venue_papers") else 1) for c in MEASURES}
    wscore = sum(w[c] * pct[c] for c in MEASURES) / sum(w.values())
    top20 = set(ranked.overall_score.nlargest(20).index)
    overlap_w = len(top20 & set(wscore.nlargest(20).index))
    rho_w = stats.spearmanr(ranked.overall_score, wscore).statistic

    # chart: top 20 overall, stacked percentile contributions
    t = ranked.nlargest(20, "overall_score").iloc[::-1]
    fig, ax = plt.subplots(figsize=(11, 8))
    left = np.zeros(len(t))
    for i, c in enumerate(MEASURES):
        v = t[f"pct_{c}"] / len(MEASURES)
        ax.barh([f"{a} ({d}, {'Tr' if i_ == 'NIT Trichy' else 'Su'})" for a, d, i_ in
                 zip(t.author, t.department, t.institution)], v, left=left, label=MEASURES[c], color=f"C{i}")
        left += v
    ax.set_xlabel("overall score (mean percentile of the 7 measures, 0-100)")
    ax.set_title(f"Top 20 current faculty, both NITs ({len(ranked)} ranked, ≥{MIN_PAPERS} papers 2016-2026)")
    ax.legend(fontsize=8, loc="upper center", bbox_to_anchor=(0.4, -0.07), ncol=4)
    ax.set_xlim(0, 100); ax.grid(alpha=0.3, axis="x")
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "faculty_ranking_top20.png"), dpi=150); plt.close(fig)

    summary = {"ranked_faculty": len(ranked), "not_ranked": len(not_ranked),
               "not_ranked_reasons": not_ranked.reason.value_counts().to_dict(),
               "measures": MEASURES, "min_papers": MIN_PAPERS,
               "robustness_quality_weighted": {"spearman_with_equal_weights": rho_w,
                                               "top20_overlap": overlap_w}}
    with open(os.path.join(OUT, "faculty_ranking_summary.json"), "w") as f:
        json.dump(summary, f, indent=2, default=float)
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)
    print(json.dumps(summary, indent=2))
    show = ["overall_rank", "author", "institution", "department", "designation", "overall_score", *MEASURES,
            "median_fwci"]
    print(out[show].head(25).round(2).to_string(index=False))
    print(corr.round(2).to_string())
    print(out[out.department_rank == 1].sort_values("department")[
        ["department", "institution", "author", "department_score", "department_size_ranked", "papers",
         "h_index", "mean_fwci"]].round(2).to_string(index=False))


PARTS = {"network": network_part, "ai": ai_part, "recency": recency_part, "geo": geo_part, "links": links_part,
         "ranking": ranking_part}


def main():
    os.makedirs(OUT, exist_ok=True)
    for part in sys.argv[1:] or list(PARTS):
        if part not in PARTS:
            sys.exit(__doc__)
        print(f"\n===== {part} =====")
        PARTS[part]()


if __name__ == "__main__":
    main()
