"""Phase II, deeper questions inspired by published science-of-science papers -> data/analysis/papers/

  python phase2_papers.py citers        A. Who cites us, and why? Every Indian citation of our papers classified by how
                                           far the citing and cited authors are in the co-authorship network
                                           (Singh, Vasques Filho, Jolad & O'Neale 2020)
  python phase2_papers.py selfcite      The internal citation network without self-citations: PageRank again, and how
                                           citations flow between departments and between the two NITs
  python phase2_papers.py adjusted      Fair institute comparison: per year on the faculty list and within rank;
                                           faculty-clustered errors; recent-year sensitivity; false-discovery control
  python phase2_papers.py core          C. Core and periphery of the faculty network, and which new links would help
                                           most (edge interventions, Barnes et al. 2026)
  python phase2_papers.py productivity  B. Year-to-year productivity as a random walk; lognormal total output
                                           (Zhang, LaBerge, Way, Larremore & Clauset 2026)
  python phase2_papers.py turnover      D. Hiring vs leaving: how the faculty body changed 2016-2026 and what each
                                           group contributes (after LaBerge, Wapman, Clauset & Larremore 2024)
  python phase2_papers.py teams         E. Team size in finer bands, and its trend
  python phase2_papers.py assort        F. Assortative mixing in the faculty and institute networks, against
                                           degree-preserving random networks

`python phase2_papers.py` runs all parts. Scope follows the team rule: questions about papers use all papers where
noted; faculty networks and faculty comparisons use faculty only (data/faculty.csv, 743 people after the roster fix).
Every random step uses a fixed seed, so each run gives the same numbers.
"""
import collections
import itertools
import json
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import networkx as nx  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import stats  # noqa: E402

from analysis import AXIS, INK, MUTED, style_axes  # noqa: E402
from questions import (COLOR, DATA, NAME_TO_ID, NITS, PARTIAL_YEAR, RANKS, faculty_graph, faculty_paper_table,  # noqa: E402
                       gini, load_links, ols, raw_works, short)

OUT = os.path.join(DATA, "analysis", "papers")
SEED = 42
MAX_TEAM = 50            # papers with more authors are left out of the co-authorship index (a 50-person clique
                         # says little about who knows whom); they are 2 of 21,260 papers


# ================================================================ helpers
def save(df, name, index=False):
    df.to_csv(os.path.join(OUT, name), index=index)


def conv(o):
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        return None if np.isnan(o) else float(o)
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, (set, tuple)):
        return list(o)
    raise TypeError(type(o))


def save_json(obj, name):
    with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, default=conv)


def savefig(fig, name):
    fig.savefig(os.path.join(OUT, name), dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def unique_works():
    """{paper id: work} for all papers of both NITs (a paper of both NITs once)."""
    return {wid: w for (_, wid), w in raw_works().items()}


def authors(w):
    return {short(a["author"]["id"]) for a in w["authorships"] if a["author"].get("id")}


def bh(p):
    """Benjamini-Hochberg adjusted p-values (false discovery rate)."""
    p = np.asarray(p, dtype=float)
    n = len(p)
    order = np.argsort(p)
    adj = np.empty(n)
    run = 1.0
    for rank, i in reversed(list(enumerate(order, 1))):
        run = min(run, p[i] * n / rank)
        adj[i] = run
    return adj


def boot_ci(x, fn=np.mean, n=2000, seed=SEED):
    x = np.asarray(x, dtype=float)
    x = x[~np.isnan(x)]
    if len(x) < 3:
        return np.nan, np.nan
    rng = np.random.default_rng(seed)
    v = [fn(rng.choice(x, len(x))) for _ in range(n)]
    return float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))


def rewired_null(G, n, measure, seed=SEED):
    """Values of `measure` on n degree-preserving rewirings of G (double edge swaps, 10 swaps per edge)."""
    vals = []
    for s in range(n):
        R = nx.Graph(G)
        if R.number_of_edges() >= 2:
            nx.double_edge_swap(R, nswap=10 * R.number_of_edges(), max_tries=100 * R.number_of_edges(), seed=seed + s)
        vals.append(measure(R))
    return np.array(vals, dtype=float)


# ================================================================ A. who cites us, and why
CLASSES = ["same author on both papers", "direct co-authors before the citation", "direct co-authors only later",
           "2 steps (a shared co-author)", "3 steps", "farther / not connected",
           "citing authors never wrote with NIT authors"]
SHORT = {"same author on both papers": "self", "direct co-authors before the citation": "co-author (before)",
         "direct co-authors only later": "co-author (later)", "2 steps (a shared co-author)": "2 steps",
         "3 steps": "3 steps", "farther / not connected": "farther", "citing authors never wrote with NIT authors":
         "no link"}


def coauthor_index(works):
    """Co-authorship among every author on our papers (faculty, students, outside co-authors): neighbours and the
    first year each pair wrote together."""
    adj, first = collections.defaultdict(set), {}
    for w in works.values():
        ids = sorted(authors(w))
        if len(ids) > MAX_TEAM:
            continue
        y = w["publication_year"]
        for a, b in itertools.combinations(ids, 2):
            adj[a].add(b)
            adj[b].add(a)
            if first.get((a, b), 9999) > y:
                first[(a, b)] = y
    return adj, first


def distance_class(S, T, year, adj, first, nbr_cache, key):
    if S & T:
        return CLASSES[0], 0
    if not any(x in adj for x in S):
        return CLASSES[6], None
    NS = set().union(*(adj.get(x, set()) for x in S))
    if NS & T:
        # years since the earliest joint paper of any citing-cited author pair (negative: they only wrote together later)
        lag = max(year - first[tuple(sorted((x, y)))] for x in S for y in T if y in adj.get(x, ()))
        return (CLASSES[1], lag) if lag >= 0 else (CLASSES[2], lag)
    if key not in nbr_cache:
        nbr_cache[key] = set().union(*(adj.get(y, set()) for y in T))
    NT = nbr_cache[key]
    if NS & NT:
        return CLASSES[3], None
    small, other = (NS, NT) if len(NS) <= len(NT) else (NT, NS)
    if any(adj[u] & other for u in small):
        return CLASSES[4], None
    return CLASSES[5], None


def citers_part():
    from phase2 import CITER_LABELS
    works = unique_works()
    adj, first = coauthor_index(works)
    cit = load_links("citers")
    edges = pd.read_csv(os.path.join(DATA, "citation_network.csv"), usecols=["source_id", "target_id", "year",
                                                                             "edge_type", "target_inst"],
                        low_memory=False)
    label = {x: t for x, (_, t) in CITER_LABELS.items()}
    rows, nbr = [], {}
    for r in edges.itertuples(index=False):
        if r.edge_type == "in_indian":
            d = cit.get(r.source_id)
            if d is None:
                continue
            S, year, kinds = d["authors"], d["year"] or r.year, {label[i] for i in d["insts"] if i in label}
            scope = "Indian citations"
        elif r.edge_type == "internal":
            S, year, kinds = authors(works[r.source_id]), works[r.source_id]["publication_year"], set()
            scope = "internal (our papers citing our papers)"
        else:
            continue
        T = authors(works[r.target_id])
        cls, lag = distance_class(S, T, year, adj, first, nbr, r.target_id)
        rows.append({"scope": scope, "source": r.source_id, "target": r.target_id, "cited_nit": r.target_inst,
                     "year": year, "class": cls, "lag": lag,
                     "citer_type": "private" if "private" in kinds else ("public" if "public" in kinds else "other")})
    d = pd.DataFrame(rows)

    def shares(x):
        s = x["class"].value_counts(normalize=True).reindex(CLASSES).fillna(0) * 100
        return pd.Series({**{SHORT[c]: s[c] for c in CLASSES}, "citations": len(x),
                          "within_3_steps_pct": s[CLASSES[:5]].sum()})
    groups = [("all Indian citations", d[d.scope == "Indian citations"]),
              ("from top private citers", d[(d.scope == "Indian citations") & (d.citer_type == "private")]),
              ("from top public citers", d[(d.scope == "Indian citations") & (d.citer_type == "public")]),
              ("other Indian citers", d[(d.scope == "Indian citations") & (d.citer_type == "other")]),
              ("internal citations", d[d.scope.str.startswith("internal")])]
    for n in NITS:
        groups.append((f"Indian citations of {n}", d[(d.scope == "Indian citations") & (d.cited_nit == n)]))
    tab = pd.DataFrame({g: shares(x) for g, x in groups}).T
    tab.index.name = "group"
    save(tab.round(2).reset_index(), "a_citation_distance.csv")
    ind = d[d.scope == "Indian citations"]
    by_year = ind.groupby("year").apply(shares).reset_index()
    save(by_year[by_year.year.between(2016, PARTIAL_YEAR)].round(2), "a_citation_distance_by_year.csv")
    # private vs public: chi-square on the classes
    pp = ind[ind.citer_type.isin(["private", "public"])]
    ct = pd.crosstab(pp.citer_type, pp["class"])
    chi = stats.chi2_contingency(ct)
    within = pp.assign(w=pp["class"].isin(CLASSES[:5])).groupby("citer_type").w.mean()
    # aging: citations between direct co-authors by years since their first joint paper
    co = d[d["class"] == CLASSES[1]]
    lag = co.lag.value_counts().sort_index()
    save(lag.rename_axis("years_since_first_joint_paper").reset_index(name="citations"), "a_coauthor_citation_lag.csv")
    summary = {"indian_citations": int(len(ind)), "internal_citations": int((d.scope != "Indian citations").sum()),
               "table": tab.round(2).reset_index().to_dict("records"),
               "private_within_3_steps_pct": 100 * within.get("private", np.nan),
               "public_within_3_steps_pct": 100 * within.get("public", np.nan),
               "private_vs_public_chi2": chi.statistic, "private_vs_public_p": chi.pvalue,
               "coauthor_citations_by_lag": lag.to_dict(),
               "share_of_coauthor_citations_within_2_years": float(lag[lag.index <= 2].sum() / lag.sum()),
               "coauthor_index": {"authors": len(adj), "pairs": len(first), "max_team": MAX_TEAM}}
    save_json(summary, "a_summary.json")

    fig, ax = plt.subplots(figsize=(11, 4.8))
    show = tab.loc[[g for g, _ in groups if g in tab.index]]
    left = np.zeros(len(show))
    colors = ["#1f2a44", "#3c6e9f", "#8fb3d9", "#c98a2b", "#e8c27a", "#d6d6d6", "#f1f1f1"]
    for c, col in zip(CLASSES, colors):
        v = show[SHORT[c]].values
        ax.barh(show.index, v, left=left, color=col, edgecolor="white", label=SHORT[c])
        left += v
    ax.invert_yaxis()
    ax.set_xlabel("share of citations (%)")
    ax.set_title("How close are the citing and cited authors in the co-authorship network?", loc="left", color=INK)
    ax.legend(ncol=4, frameon=False, fontsize=8.5, loc="upper center", bbox_to_anchor=(0.5, -0.15))
    style_axes(ax)
    savefig(fig, "a_citation_distance.png")
    print(tab.round(1).to_string())
    print(json.dumps({k: v for k, v in summary.items() if k != "table"}, indent=1, default=conv))


# ================================================================ self-citation-free citation network
def selfcite_part():
    works = unique_works()
    g = pd.read_csv(os.path.join(DATA, "group12_data.csv"), low_memory=False)
    pp = faculty_paper_table(g)
    branch = pp.drop_duplicates("openalex_id").set_index("openalex_id").branch
    nit = g.groupby("openalex_id").institution.agg(lambda s: "both NITs" if s.nunique() > 1 else s.iat[0])
    fac = g.groupby("openalex_id").faculty_id.apply(set)
    e = pd.read_csv(os.path.join(DATA, "citation_network.csv"), low_memory=False)
    e = e[e.edge_type == "internal"][["source_id", "target_id", "year"]]
    e["shared_author"] = [bool(authors(works[s]) & authors(works[t])) for s, t in zip(e.source_id, e.target_id)]
    e["shared_faculty"] = [bool(fac.get(s, set()) & fac.get(t, set())) for s, t in zip(e.source_id, e.target_id)]
    nodes = sorted(set(g.openalex_id))

    def pagerank(edges):
        G = nx.DiGraph()
        G.add_nodes_from(nodes)
        G.add_edges_from(zip(edges.source_id, edges.target_id))
        return nx.pagerank(G, alpha=0.85), dict(G.in_degree())
    pr_all, in_all = pagerank(e)
    clean = e[~e.shared_author]
    pr_c, in_c = pagerank(clean)
    meta = g.drop_duplicates("openalex_id").set_index("openalex_id")
    top = []
    for which, pr, ind in (("all internal citations", pr_all, in_all), ("without self-citations", pr_c, in_c)):
        for rank, (p, v) in enumerate(sorted(pr.items(), key=lambda kv: (-kv[1], kv[0]))[:10], 1):
            top.append({"network": which, "rank": rank, "openalex_id": p, "title": meta.title.get(p, ""),
                        "year": meta.year.get(p), "institution": nit.get(p), "department": branch.get(p, ""),
                        "pagerank": v, "in_degree": ind.get(p, 0), "citations_total": meta.citations.get(p)})
    top = pd.DataFrame(top)
    save(top, "s_pagerank_top10.csv")
    r_all = pd.Series(pr_all)
    r_c = pd.Series(pr_c)[r_all.index]
    rho = stats.spearmanr(r_all, r_c).statistic
    t10a = set(top[top.network == "all internal citations"].openalex_id)
    t10c = set(top[top.network == "without self-citations"].openalex_id)
    # flows between departments and between the two NITs, without self-citations
    fl = clean.assign(src_dept=clean.source_id.map(branch), dst_dept=clean.target_id.map(branch),
                      src_nit=clean.source_id.map(nit), dst_nit=clean.target_id.map(nit))
    mat = pd.crosstab(fl.src_dept, fl.dst_dept)
    save(mat.reset_index(), "s_department_flow_matrix.csv")
    same_dept = (fl.src_dept == fl.dst_dept).mean()
    nf = pd.crosstab(fl.src_nit, fl.dst_nit)
    save(nf.reset_index(), "s_nit_flow.csv")
    allf = e.assign(src_nit=e.source_id.map(nit), dst_nit=e.target_id.map(nit))
    nf_all = pd.crosstab(allf.src_nit, allf.dst_nit)
    pairs = (fl[fl.src_dept != fl.dst_dept].groupby(["src_dept", "dst_dept"]).size().sort_values(ascending=False)
             .head(12).rename("citations").reset_index())
    save(pairs, "s_top_department_flows.csv")
    summary = {"internal_edges": int(len(e)), "self_citation_share_shared_author": float(e.shared_author.mean()),
               "self_citation_share_shared_faculty": float(e.shared_faculty.mean()), "clean_edges": int(len(clean)),
               "spearman_pagerank_all_vs_clean": rho, "top10_overlap": len(t10a & t10c),
               "top10_2016_papers_all": int((top[top.network == "all internal citations"].year == 2016).sum()),
               "top10_2016_papers_clean": int((top[top.network == "without self-citations"].year == 2016).sum()),
               "clean_same_department_share": float(same_dept),
               "nit_flow_clean": {f"{a} -> {b}": int(nf.loc[a, b]) for a in nf.index for b in nf.columns},
               "nit_flow_all": {f"{a} -> {b}": int(nf_all.loc[a, b]) for a in nf_all.index for b in nf_all.columns},
               "top_cross_department_flows": pairs.to_dict("records")}
    save_json(summary, "s_summary.json")
    print(top[["network", "rank", "year", "department", "in_degree", "title"]].to_string())
    print(json.dumps({k: v for k, v in summary.items() if k != "top_cross_department_flows"}, indent=1, default=conv))


# ================================================================ fair institute comparison
def cluster_ols(df, y, x_cols, cat, cluster):
    """OLS with errors clustered by `cluster` (CR1), for the institute term; same design as questions.ols."""
    cols = [pd.Series(1.0, index=df.index, name="Intercept")]
    for c in cat:
        dm = pd.get_dummies(df[c].astype(str), dtype=float)
        cols.append(dm[sorted(dm.columns)].iloc[:, 1:].add_prefix(f"{c}="))
    for c in x_cols:
        cols.append(df[c].astype(float).rename(c))
    X = pd.concat(cols, axis=1)
    X = X.loc[:, (X != 0).any()]
    Xv, yv = X.values, df[y].astype(float).values
    inv = np.linalg.pinv(Xv.T @ Xv)
    b = inv @ Xv.T @ yv
    u = yv - Xv @ b
    gidx = pd.factorize(df[cluster])[0]
    G = gidx.max() + 1
    S = np.zeros((Xv.shape[1], Xv.shape[1]))
    for gi in range(G):
        m = gidx == gi
        s = Xv[m].T @ u[m]
        S += np.outer(s, s)
    n, k = Xv.shape
    cov = inv @ S @ inv * (G / (G - 1)) * ((n - 1) / (n - k))
    se = np.sqrt(np.diag(cov))
    return pd.DataFrame({"coef": b, "se": se, "p": 2 * stats.norm.sf(np.abs(b / se))}, index=X.columns), G


def adjusted_part():
    fac = pd.read_csv(os.path.join(DATA, "faculty.csv"))
    g = pd.read_csv(os.path.join(DATA, "group12_data.csv"), low_memory=False)
    fp = g[g.year < PARTIAL_YEAR].drop_duplicates(["faculty_id", "openalex_id"])
    n10 = fp.groupby("faculty_id").openalex_id.nunique()
    f = fac.copy()
    f["start"] = f.first_seen.clip(lower=2016)
    f["end"] = f.last_seen.clip(upper=PARTIAL_YEAR - 1)
    f["years_on_list"] = (f.end - f.start + 1).clip(lower=1)
    f["papers_2016_2025"] = f.faculty_id.map(n10).fillna(0)
    f["papers_per_year"] = f.papers_2016_2025 / f.years_on_list
    f["rank"] = f.designation.where(f.designation.isin(RANKS), "Other")
    f["log_ppy"] = np.log1p(f.papers_per_year)
    f["surathkal"] = (f.institution == "NIT Surathkal").astype(int)
    rows = []
    for rk in RANKS + ["All ranks"]:
        x = f if rk == "All ranks" else f[f["rank"] == rk]
        a, b = x[x.institution == "NIT Trichy"].papers_per_year, x[x.institution == "NIT Surathkal"].papers_per_year
        fa, fb = (x[(x.institution == n) & x.mean_fwci.notna()].mean_fwci for n in NITS)
        rows.append({"rank": rk, "faculty_trichy": len(a), "faculty_surathkal": len(b),
                     "share_of_trichy_faculty": len(a) / (f.institution == "NIT Trichy").sum(),
                     "share_of_surathkal_faculty": len(b) / (f.institution == "NIT Surathkal").sum(),
                     "median_papers_per_year_trichy": a.median(), "median_papers_per_year_surathkal": b.median(),
                     "p_papers_per_year": stats.mannwhitneyu(a, b).pvalue if len(a) > 2 and len(b) > 2 else np.nan,
                     "median_fwci_trichy": fa.median(), "median_fwci_surathkal": fb.median(),
                     "p_fwci": stats.mannwhitneyu(fa, fb).pvalue if len(fa) > 2 and len(fb) > 2 else np.nan})
    by_rank = pd.DataFrame(rows)
    save(by_rank.round(4), "r_institutes_within_rank.csv")
    t0, n0, _ = ols(f, "log_ppy", dummies=["surathkal"])
    t1, n1, _ = ols(f, "log_ppy", cat=["rank"], dummies=["surathkal"])
    t2, n2, _ = ols(f, "log_ppy", cat=["rank", "department"], dummies=["surathkal"])
    models = pd.DataFrame([{"model": m, "surathkal_effect_pct": t.loc["surathkal", "effect_pct"],
                            "ci_low_pct": t.loc["surathkal", "effect_ci_low_pct"],
                            "ci_high_pct": t.loc["surathkal", "effect_ci_high_pct"],
                            "p_value": t.loc["surathkal", "p_value"], "faculty": n}
                           for m, (t, n) in {"no controls": (t0, n0), "+ rank": (t1, n1),
                                             "+ rank + department": (t2, n2)}.items()])
    save(models.round(4), "r_papers_per_year_models.csv")

    # paper-level FWCI model with errors clustered by faculty member; recent-year sensitivity
    p = faculty_paper_table(g)
    lead = g.sort_values("author_position").drop_duplicates(["institution", "openalex_id"]).set_index(
        ["institution", "openalex_id"]).faculty_id
    p["lead_faculty"] = [lead.get((i, w)) for i, w in zip(p.institution, p.openalex_id)]
    xs = ["surathkal", "foreign", "indian_collab", "conference", "log_authors"]
    sens = []
    for lab, q in (("all years", p), ("published up to 2024", p[p.year <= 2024]),
                   ("published up to 2023", p[p.year <= 2023])):
        th, nh, _ = ols(q, "log_fwci", num=["log_authors"], cat=["year", "branch"],
                        dummies=["surathkal", "foreign", "indian_collab", "conference"])
        tc, G = cluster_ols(q, "log_fwci", xs, ["year", "branch"], "lead_faculty")
        sens.append({"papers": lab, "n": nh, "surathkal_effect_pct": th.loc["surathkal", "effect_pct"],
                     "p_robust": th.loc["surathkal", "p_value"], "se_robust": th.loc["surathkal", "se"],
                     "se_clustered_by_faculty": tc.loc["surathkal", "se"], "p_clustered": tc.loc["surathkal", "p"],
                     "faculty_clusters": G,
                     "foreign_effect_pct": th.loc["foreign", "effect_pct"],
                     "foreign_p_clustered": tc.loc["foreign", "p"],
                     "conference_effect_pct": th.loc["conference", "effect_pct"],
                     "conference_p_clustered": tc.loc["conference", "p"]})
    sens = pd.DataFrame(sens)
    save(sens.round(4), "r_fwci_model_sensitivity.csv")

    # false-discovery control over the families of tests we report
    fam = []
    bb = pd.read_csv(os.path.join(DATA, "analysis", "ns_branch_fwci_bootstrap.csv"))
    se = (bb.ci_high - bb.ci_low) / 3.92
    for b_, pv in zip(bb.branch, 2 * stats.norm.sf(np.abs(bb.difference_T_minus_S / se))):
        fam.append(("branch FWCI, Trichy vs Surathkal", b_, pv))
    for fn, fam_name, key in (("questions/q16_partner_types.csv", "partner types (Q16)", "partner_type"),
                              ("questions/q15_countries.csv", "partner countries (Q15)", "country"),
                              ("phase2/citers_private_vs_public.csv", "private vs public citers", "measure"),
                              ("questions/q18_former_vs_current.csv", "former vs current faculty (Q18)", None),
                              ("institute_tests.csv", "per-faculty institute tests", None)):
        t = pd.read_csv(os.path.join(DATA, "analysis", fn))
        pcol = next(c for c in t.columns if c in ("p_value", "mann_whitney_p"))
        t = t[t[pcol].notna()]
        names = t[key] if key else t.iloc[:, 0].astype(str) + " / " + t.iloc[:, 1].astype(str)
        for nm, pv in zip(names, t[pcol]):
            fam.append((fam_name, nm, pv))
    fd = pd.DataFrame(fam, columns=["family", "test", "p_value"])
    fd["p_adjusted_bh"] = fd.groupby("family").p_value.transform(bh)
    fd["significant_raw"] = fd.p_value < 0.05
    fd["significant_after_fdr"] = fd.p_adjusted_bh < 0.05
    save(fd.round(5), "r_false_discovery.csv")
    fsum = fd.groupby("family").agg(tests=("test", "size"), significant_raw=("significant_raw", "sum"),
                                    significant_after_fdr=("significant_after_fdr", "sum")).reset_index()
    lost = fd[fd.significant_raw & ~fd.significant_after_fdr][["family", "test", "p_value", "p_adjusted_bh"]]
    summary = {"within_rank": by_rank.to_dict("records"), "papers_per_year_models": models.to_dict("records"),
               "fwci_sensitivity": sens.to_dict("records"), "fdr_by_family": fsum.to_dict("records"),
               "lost_after_fdr": lost.to_dict("records")}
    save_json(summary, "r_summary.json")
    print(by_rank.round(3).to_string()); print(models.round(3).to_string()); print(sens.round(4).to_string())
    print(fsum.to_string()); print(lost.round(4).to_string())


# ================================================================ C. core, periphery and edge interventions
def apsp(G, order):
    """All-pairs shortest-path lengths as a matrix (inf = not connected)."""
    idx = {v: i for i, v in enumerate(order)}
    D = np.full((len(order), len(order)), np.inf)
    for s, lengths in nx.all_pairs_shortest_path_length(G):
        i = idx[s]
        for t, l in lengths.items():
            D[i, idx[t]] = l
    return D


def efficiency(D):
    n = len(D)
    with np.errstate(divide="ignore"):
        inv = 1.0 / D
    np.fill_diagonal(inv, 0)
    return inv.sum() / (n * (n - 1))


def with_edge(D, i, j):
    return np.minimum(D, np.minimum(D[:, [i]] + 1 + D[[j], :], D[:, [j]] + 1 + D[[i], :]))


def greedy_links(G, order, candidates, k):
    D = apsp(G, order)
    idx = {v: i for i, v in enumerate(order)}
    e0 = efficiency(D)
    chosen, curve = [], [e0]
    cand = [(idx[a], idx[b]) for a, b in candidates]
    for _ in range(k):
        best, best_e = None, -1
        for (i, j) in cand:
            if D[i, j] <= 2:        # already linked, or one shared colleague away: a new link barely helps
                continue
            e = efficiency(with_edge(D, i, j))
            if e > best_e:
                best, best_e = (i, j), e
        if best is None:
            break
        D = with_edge(D, *best)
        chosen.append((order[best[0]], order[best[1]], best_e))
        curve.append(best_e)
        cand = [c for c in cand if c != best]
    return chosen, curve


def core_part():
    G = faculty_graph()
    fac = pd.read_csv(os.path.join(DATA, "faculty.csv")).set_index("faculty_id")
    order = sorted(G.nodes)
    core = nx.core_number(G)
    harm = nx.harmonic_centrality(G)
    btw = nx.betweenness_centrality(G)
    nd = pd.DataFrame({"faculty_id": order, "institution": [G.nodes[v]["institution"] for v in order],
                       "department": [G.nodes[v]["department"] for v in order],
                       "rank": [G.nodes[v]["designation"] for v in order],
                       "degree": [G.degree(v) for v in order], "core": [core[v] for v in order],
                       "harmonic": [harm[v] for v in order], "betweenness": [btw[v] for v in order]})
    nd["h_index"] = nd.faculty_id.map(fac.h_index_2016_2026)
    nd["mean_fwci"] = nd.faculty_id.map(fac.mean_fwci)
    rows = []
    for view, x in [("Both", nd)] + [(n, nd[nd.institution == n]) for n in NITS]:
        rows.append({"view": view, "faculty": len(x), "isolated_pct": 100 * (x.degree == 0).mean(),
                     "in_core_3plus_pct": 100 * (x.core >= 3).mean(), "max_core": int(x.core.max()),
                     "gini_degree": gini(x.degree), "gini_betweenness": gini(x.betweenness),
                     "gini_harmonic": gini(x.harmonic)})
    ineq = pd.DataFrame(rows)
    save(ineq.round(4), "c_centrality_inequality.csv")
    rk = nd[nd["rank"].isin(RANKS)].groupby("rank").agg(faculty=("faculty_id", "size"), mean_degree=("degree", "mean"),
                                                          median_harmonic=("harmonic", "median"),
                                                          in_core_3plus_pct=("core", lambda s: 100 * (s >= 3).mean()))
    rk = rk.reindex(RANKS).reset_index()
    save(rk.round(3), "c_core_by_rank.csv")
    rho_h = stats.spearmanr(nd.core, nd.h_index, nan_policy="omit")
    rho_f = stats.spearmanr(nd.core, nd.mean_fwci, nan_policy="omit")

    # edge interventions: which new collaborations make the network most connected (global efficiency)?
    def same_dept_pairs(cross_nit):
        out = []
        by = collections.defaultdict(list)
        for v in order:
            by[G.nodes[v]["department"]].append(v)
        for dep, vs in by.items():
            if not dep:
                continue
            for a, b in itertools.combinations(sorted(vs), 2):
                diff = G.nodes[a]["institution"] != G.nodes[b]["institution"]
                if diff == cross_nit and not G.has_edge(a, b):
                    out.append((a, b))
        return out
    K = 10
    res = {}
    for name, cands in (("same department, same NIT", same_dept_pairs(False)),
                        ("same department, across the two NITs", same_dept_pairs(True))):
        chosen, curve = greedy_links(G, order, cands, K)
        rng = np.random.default_rng(SEED)
        D0 = apsp(G, order)
        idx = {v: i for i, v in enumerate(order)}
        rand = []
        for s in range(30):
            D = D0.copy()
            for t in rng.choice(len(cands), K, replace=False):
                a, b = cands[t]
                D = with_edge(D, idx[a], idx[b])
            rand.append(efficiency(D))
        res[name] = {"candidates": len(cands), "efficiency_before": curve[0], "after_best_10": curve[-1],
                     "gain_pct_best_10": 100 * (curve[-1] / curve[0] - 1),
                     "gain_pct_random_10_mean": 100 * (np.mean(rand) / curve[0] - 1),
                     "links": [{"a": fac.author.get(a, a), "a_nit": G.nodes[a]["institution"], "b": fac.author.get(b, b),
                                "b_nit": G.nodes[b]["institution"], "department": G.nodes[a]["department"],
                                "efficiency_after": e} for a, b, e in chosen]}
    links = pd.DataFrame([{"set": k, **l} for k, v in res.items() for l in v["links"]])
    save(links, "c_best_new_links.csv")
    # targeted intervention (as in Barnes et al.): link each peripheral member of the largest group to one core
    # member of their own department, vs to a random member of their department
    gc = max(nx.connected_components(G), key=len)
    H = G.subgraph(gc).copy()
    hh = nx.harmonic_centrality(H)
    hc = nx.core_number(H)
    per = sorted([v for v in H if H.degree(v) == 1], key=lambda v: (hh[v], v))
    rng = np.random.default_rng(SEED)
    gains = {"to a core member": [], "to a random colleague": []}
    for v in per:
        dep = H.nodes[v]["department"]
        mates = [u for u in H if u != v and H.nodes[u]["department"] == dep and not H.has_edge(u, v)]
        if not mates:
            continue
        top = max(mates, key=lambda u: (hc[u], hh[u], u))
        for lab, u in (("to a core member", top), ("to a random colleague", mates[rng.integers(len(mates))])):
            R = H.copy()
            R.add_edge(v, u)
            gains[lab].append(nx.harmonic_centrality(R, nbunch=[v])[v] / hh[v] - 1)
    targeted = {k: {"faculty": len(x), "median_gain_pct": 100 * float(np.median(x)), "mean_gain_pct": 100 * float(np.mean(x))}
                for k, x in gains.items()}
    summary = {"inequality": ineq.to_dict("records"), "by_rank": rk.to_dict("records"),
               "spearman_core_vs_h_index": [rho_h.statistic, rho_h.pvalue],
               "spearman_core_vs_fwci": [rho_f.statistic, rho_f.pvalue],
               "interventions": {k: {kk: vv for kk, vv in v.items() if kk != "links"} for k, v in res.items()},
               "targeted_peripheral": targeted, "peripheral_faculty_tested": len(gains["to a core member"])}
    save_json(summary, "c_summary.json")
    print(ineq.round(3).to_string()); print(rk.round(2).to_string()); print(links.to_string())
    print(json.dumps({k: v for k, v in summary.items() if k not in ("inequality", "by_rank")}, indent=1, default=conv))


# ================================================================ B. productivity as a random walk
def lognormal_vs_powerlaw(x):
    """Continuous fits from x_min = 1: log-likelihood ratio (Vuong) of lognormal vs power law (Pareto)."""
    x = np.asarray(x, dtype=float)
    x = x[x >= 1]
    a = 1 + len(x) / np.log(x).sum()
    ll_pl = np.log(a - 1) - a * np.log(x)
    shape, loc, scale = stats.lognorm.fit(x, floc=0)
    ll_ln = stats.lognorm.logpdf(x, shape, loc, scale) - np.log(stats.lognorm.sf(1, shape, loc, scale))
    d = ll_ln - ll_pl
    z = d.sum() / (np.sqrt(len(d)) * d.std())
    ks = stats.kstest(x, lambda v: (stats.lognorm.cdf(v, shape, loc, scale) - stats.lognorm.cdf(1, shape, loc, scale))
                      / stats.lognorm.sf(1, shape, loc, scale))
    return {"n": len(x), "powerlaw_alpha": a, "lognormal_mu": np.log(scale), "lognormal_sigma": shape,
            "loglik_ratio_lognormal_minus_powerlaw": d.sum(), "vuong_z": z, "vuong_p": 2 * stats.norm.sf(abs(z)),
            "lognormal_ks_stat": ks.statistic, "lognormal_ks_p": ks.pvalue}


def shape_of(y):
    """'rising', 'falling', 'peak in the middle', 'dip in the middle' or 'flat', from a quadratic fit."""
    t = np.arange(len(y))
    if y.sum() == 0:
        return "flat"
    c2, c1, c0 = np.polyfit(t, y, 2)
    fit = np.polyval([c2, c1, c0], t)
    vertex = -c1 / (2 * c2) if c2 != 0 else np.inf
    lin = np.polyfit(t, y, 1)[0]
    rel = (fit.max() - fit.min()) / max(y.mean(), 1e-9)
    if rel < 0.5:
        return "flat"
    if 1.5 <= vertex <= len(y) - 2.5:
        return "peak in the middle" if c2 < 0 else "dip in the middle"
    return "rising" if lin > 0 else "falling"


def productivity_part():
    fac = pd.read_csv(os.path.join(DATA, "faculty.csv")).set_index("faculty_id")
    g = pd.read_csv(os.path.join(DATA, "group12_data.csv"), low_memory=False)
    fp = g[g.year < PARTIAL_YEAR].drop_duplicates(["faculty_id", "openalex_id"])
    years = list(range(2016, PARTIAL_YEAR))
    m = fp.groupby(["faculty_id", "year"]).size().unstack(fill_value=0).reindex(columns=years, fill_value=0)
    keep = fac[(fac.first_seen <= 2017) & (fac.last_seen >= PARTIAL_YEAR - 1)].index
    m = m[m.index.isin(keep) & (m.sum(axis=1) >= 10)]
    d = m.diff(axis=1).iloc[:, 1:]
    dv = d.values.ravel()
    ac = []
    for row in d.values:
        if row.std() > 0:
            ac.append(np.corrcoef(row[:-1], row[1:])[0, 1])
    rng = np.random.default_rng(SEED)
    null = []
    for row in m.values:
        perm = rng.permutation(row)
        dd = np.diff(perm)
        if dd.std() > 0:
            null.append(np.corrcoef(dd[:-1], dd[1:])[0, 1])
    lvl = m.values[:, :-1].ravel()
    absd = np.abs(d.values.ravel())
    ok = lvl > 0
    beta = np.polyfit(np.log(lvl[ok]), np.log(absd[ok] + 0.5), 1)[0]
    shapes = pd.Series({f: shape_of(row) for f, row in zip(m.index, m.values)})
    sh = shapes.value_counts(normalize=True).mul(100).rename("share_pct").rename_axis("shape").reset_index()
    sh_n = shapes.groupby(fac.institution.reindex(shapes.index)).value_counts(normalize=True).mul(100).unstack()
    mean_traj = m.mean()
    avg_shape = shape_of(mean_traj.values)
    by_rank = m.groupby(fac.designation.reindex(m.index)).mean().reindex(RANKS)
    save(sh, "b_trajectory_shapes.csv")
    save(sh_n.round(2).reset_index(), "b_trajectory_shapes_by_nit.csv")
    save(by_rank.round(3).reset_index(), "b_mean_trajectory_by_rank.csv")
    tot = fp.groupby("faculty_id").openalex_id.nunique()
    fit = lognormal_vs_powerlaw(tot.values)
    summary = {"faculty": len(m), "rule": "on the list 2016/17 to 2025 and 10+ papers in 2016-2025",
               "mean_change_per_year": float(dv.mean()), "sd_change_per_year": float(dv.std()),
               "kurtosis_of_changes": float(stats.kurtosis(dv)),
               "lag1_autocorrelation_of_changes_median": float(np.median(ac)),
               "lag1_autocorrelation_null_median": float(np.median(null)),
               "change_size_grows_with_level_exponent": float(beta),
               "average_trajectory_shape": avg_shape, "shapes": sh.to_dict("records"),
               "total_output_fit": fit}
    save_json(summary, "b_summary.json")
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.6))
    ax = axes[0]
    for row in m.sample(min(40, len(m)), random_state=SEED).values:
        ax.plot(years, row, color=AXIS, lw=0.8, alpha=0.7)
    ax.plot(years, mean_traj.values, color=INK, lw=3, label="average of all faculty")
    ax.set_title("Individual paths are noisy; the average is smooth", loc="left", color=INK)
    ax.set_ylabel("papers in the year"); ax.legend(frameon=False); style_axes(ax)
    ax = axes[1]
    ax.hist(dv, bins=np.arange(dv.min() - 0.5, dv.max() + 1.5), color=MUTED)
    ax.set_title("Change from one year to the next", loc="left", color=INK)
    ax.set_xlabel("papers this year minus papers last year"); style_axes(ax)
    savefig(fig, "b_productivity.png")
    print(sh.round(1).to_string()); print(sh_n.round(1).to_string()); print(by_rank.round(2).to_string())
    print(json.dumps({k: v for k, v in summary.items() if k != "shapes"}, indent=1, default=conv))


# ================================================================ D. hiring vs leaving
def turnover_part():
    fac = pd.read_csv(os.path.join(DATA, "faculty.csv"))
    g = pd.read_csv(os.path.join(DATA, "group12_data.csv"), low_memory=False)
    fp = g[g.year < PARTIAL_YEAR].drop_duplicates(["faculty_id", "openalex_id"])
    years = list(range(2016, PARTIAL_YEAR + 1))
    rows = []
    for n in NITS:
        f = fac[fac.institution == n]
        for y in years:
            act = f[(f.first_seen <= y) & (f.last_seen >= y)]
            rows.append({"institution": n, "year": y, "faculty_listed": len(act),
                         "joined": int(((f.first_seen == y) & (y > 2016)).sum()),
                         "left_after_previous_year": int((f.last_seen == y - 1).sum()) if y > 2016 else 0})
    yr = pd.DataFrame(rows)
    save(yr, "d_headcount_by_year.csv")
    fac["group"] = np.where(fac.first_seen > 2016, "joined after 2016",
                            np.where(fac.last_seen < PARTIAL_YEAR, "left before 2026", "stayed 2016-2026"))
    both = (fac.first_seen > 2016) & (fac.last_seen < PARTIAL_YEAR)
    fac.loc[both, "group"] = "joined and left"
    fac["years_on_list"] = (fac.last_seen.clip(upper=PARTIAL_YEAR - 1) - fac.first_seen.clip(lower=2016) + 1).clip(lower=1)
    inwin = fp.merge(fac[["faculty_id", "first_seen", "last_seen"]], on="faculty_id")
    inwin = inwin[(inwin.year >= inwin.first_seen.clip(lower=2016)) & (inwin.year <= inwin.last_seen)]
    p_in = inwin.groupby("faculty_id").openalex_id.nunique()
    fw = inwin.groupby("faculty_id").fwci.mean()
    fac["papers_while_listed"] = fac.faculty_id.map(p_in).fillna(0)
    fac["papers_per_year_listed"] = fac.papers_while_listed / fac.years_on_list
    fac["fwci_while_listed"] = fac.faculty_id.map(fw)
    grp = fac.groupby(["institution", "group"]).agg(
        faculty=("faculty_id", "size"), median_papers_per_year=("papers_per_year_listed", "median"),
        mean_papers_per_year=("papers_per_year_listed", "mean"), median_fwci=("fwci_while_listed", "median"),
        asst_prof_share=("designation", lambda s: (s == "Assistant Professor").mean())).reset_index()
    save(grp.round(3), "d_groups.csv")
    # where the 2025 output came from, and a simple counterfactual: what if no one had left?
    out = []
    for n in NITS:
        f = fac[fac.institution == n].set_index("faculty_id")
        y25 = fp[(fp.year == PARTIAL_YEAR - 1) & fp.faculty_id.isin(f.index)]
        act25 = f[(f.first_seen <= PARTIAL_YEAR - 1) & (f.last_seen >= PARTIAL_YEAR - 1)]
        by = y25[y25.faculty_id.isin(act25.index)].groupby(y25.faculty_id.map(f.group)).openalex_id.nunique()
        left = f[f.group.isin(["left before 2026", "joined and left"])]
        lost = left.papers_per_year_listed.sum()
        total25 = y25[y25.faculty_id.isin(act25.index)].openalex_id.nunique()
        out.append({"institution": n, "faculty_2016": int(((f.first_seen <= 2016) & (f.last_seen >= 2016)).sum()),
                    "faculty_2026": int((f.last_seen >= PARTIAL_YEAR).sum()), "joined": int((f.first_seen > 2016).sum()),
                    "left": int((f.last_seen < PARTIAL_YEAR).sum()), "papers_2025_by_listed_faculty": total25,
                    "share_2025_from_joiners_pct": 100 * by.get("joined after 2016", 0) / max(total25, 1),
                    "papers_per_year_lost_with_leavers": lost,
                    "counterfactual_2025_output_if_none_had_left_pct": 100 * lost / max(total25, 1)})
    decomp = pd.DataFrame(out)
    save(decomp.round(2), "d_decomposition.csv")
    dep = []
    for (n, dname), f in fac.groupby(["institution", "department"]):
        dep.append({"institution": n, "department": dname,
                    "listed_2016": int(((f.first_seen <= 2016) & (f.last_seen >= 2016)).sum()),
                    "listed_2026": int((f.last_seen >= PARTIAL_YEAR).sum()), "joined": int((f.first_seen > 2016).sum()),
                    "left": int((f.last_seen < PARTIAL_YEAR).sum())})
    dep = pd.DataFrame(dep)
    dep["change"] = dep.listed_2026 - dep.listed_2016
    save(dep.sort_values("change"), "d_departments.csv")
    summary = {"groups": grp.to_dict("records"), "decomposition": decomp.to_dict("records"),
               "largest_growth": dep.sort_values("change", ascending=False).head(4).to_dict("records"),
               "largest_shrink": dep.sort_values("change").head(4).to_dict("records"),
               "caveat": "years come from yearly snapshots of faculty pages; the rank is the latest one only, "
                         "so promotions cannot be separated from hiring"}
    save_json(summary, "d_summary.json")
    print(yr.to_string()); print(grp.round(2).to_string()); print(decomp.round(2).to_string())


# ================================================================ E. team size
BANDS = [(1, 1, "1"), (2, 3, "2-3"), (4, 5, "4-5"), (6, 9, "6-9"), (10, 19, "10-19"), (20, 49, "20-49"),
         (50, 10**6, "50+")]


def band(n):
    return next(lab for lo, hi, lab in BANDS if lo <= n <= hi)


def teams_part():
    ap = pd.read_csv(os.path.join(DATA, "all_papers.csv"), low_memory=False)
    rows = []
    for scope, d in (("faculty papers", ap[ap.has_faculty_author == True]), ("all papers (incl. students)", ap)):  # noqa: E712
        for view in ["Both"] + NITS:
            x = d.drop_duplicates("openalex_id") if view == "Both" else d[d.institution == view]
            x = x.assign(band=x.n_authors.map(band))
            for lo, hi, lab in BANDS:
                y = x[x.band == lab]
                if not len(y):
                    rows.append({"scope": scope, "view": view, "authors": lab, "papers": 0})
                    continue
                lo_ci, hi_ci = boot_ci(y.fwci.values)
                rows.append({"scope": scope, "view": view, "authors": lab, "papers": len(y),
                             "share_pct": 100 * len(y) / len(x), "citations_per_paper": y.citations.mean(),
                             "mean_fwci": y.fwci.mean(), "mean_fwci_ci_low": lo_ci, "mean_fwci_ci_high": hi_ci,
                             "median_fwci": y.fwci.median(), "top10_share_pct": 100 * y.top10pct.mean()})
    t = pd.DataFrame(rows)
    save(t.round(3), "e_team_size_bands.csv")
    u = ap[ap.has_faculty_author == True].drop_duplicates("openalex_id")  # noqa: E712
    yr = u.groupby("year").agg(papers=("openalex_id", "size"), mean_authors=("n_authors", "mean"),
                               median_authors=("n_authors", "median"),
                               single_author_pct=("n_authors", lambda s: 100 * (s == 1).mean()),
                               ten_plus_pct=("n_authors", lambda s: 100 * (s >= 10).mean())).reset_index()
    save(yr.round(3), "e_team_size_by_year.csv")
    full = yr[yr.year < PARTIAL_YEAR]
    sl = stats.linregress(full.year, full.mean_authors)
    p = faculty_paper_table()
    tt, n, _ = ols(p, "log_fwci", num=["log_authors"], cat=["year", "branch"],
                   dummies=["surathkal", "foreign", "indian_collab", "conference"])
    b = tt.loc["log_authors"]
    summary = {"bands_faculty_both": t[(t.scope == "faculty papers") & (t.view == "Both")].to_dict("records"),
               "faculty_papers_20plus": int((u.n_authors >= 20).sum()),
               "all_papers_20plus": int((ap.drop_duplicates("openalex_id").n_authors >= 20).sum()),
               "mean_authors_2016": float(full.mean_authors.iloc[0]), "mean_authors_2025": float(full.mean_authors.iloc[-1]),
               "trend_authors_per_year": sl.slope, "trend_p": sl.pvalue,
               "regression_log_authors_coef": b.coef, "regression_log_authors_p": b.p_value,
               "fwci_effect_of_doubling_team_pct": 100 * (np.exp(b.coef * np.log(2)) - 1), "regression_papers": n}
    save_json(summary, "e_summary.json")
    fig, ax = plt.subplots(figsize=(9, 4.4))
    for view in NITS:
        x = t[(t.scope == "faculty papers") & (t.view == view) & (t.papers >= 20)]
        ax.errorbar(x.authors, x.mean_fwci, yerr=[x.mean_fwci - x.mean_fwci_ci_low, x.mean_fwci_ci_high - x.mean_fwci],
                    marker="o", capsize=3, color=COLOR[view], label=view)
    ax.axhline(1, color=AXIS, lw=1, ls="--")
    ax.set_xlabel("authors on the paper"); ax.set_ylabel("mean FWCI (95% CI)")
    ax.set_title("Bigger teams, higher impact (faculty papers)", loc="left", color=INK)
    ax.legend(frameon=False); style_axes(ax)
    savefig(fig, "e_team_size.png")
    print(t[t.view == "Both"].round(2).to_string()); print(yr.round(2).to_string())
    print(json.dumps({k: v for k, v in summary.items() if k != "bands_faculty_both"}, indent=1, default=conv))


# ================================================================ F. assortativity
def assort_part():
    G = faculty_graph()
    fac = pd.read_csv(os.path.join(DATA, "faculty.csv")).set_index("faculty_id")
    for v in G:
        G.nodes[v]["h"] = float(fac.h_index_2016_2026.get(v, 0) or 0)
        f = fac.mean_fwci.get(v)
        G.nodes[v]["fwci"] = float(f) if pd.notna(f) else 0.0
        G.nodes[v]["papers"] = float(fac.papers.get(v, 0) or 0)
    H = G.subgraph([v for v in G if G.degree(v) > 0]).copy()
    rows = []

    def add(name, graph, fn, n=100):
        obs = fn(graph)
        null = rewired_null(graph, n, fn)
        rows.append({"network": name, "measure": fn.__name__, "observed": obs, "null_mean": null.mean(),
                     "null_sd": null.std(), "z": (obs - null.mean()) / null.std() if null.std() > 0 else np.nan,
                     "nodes": graph.number_of_nodes(), "links": graph.number_of_edges()})

    def degree(g):
        return nx.degree_assortativity_coefficient(g)

    def h_index(g):
        return nx.numeric_assortativity_coefficient(g, "h")

    def fwci(g):
        return nx.numeric_assortativity_coefficient(g, "fwci")

    def department(g):
        return nx.attribute_assortativity_coefficient(g, "department")

    def rank(g):
        return nx.attribute_assortativity_coefficient(g, "designation")

    def institution(g):
        return nx.attribute_assortativity_coefficient(g, "institution")
    for fn in (degree, h_index, fwci, department, rank, institution):
        add("faculty (both NITs)", H, fn)
    for n in NITS:
        S = H.subgraph([v for v in H if H.nodes[v]["institution"] == n]).copy()
        S.remove_nodes_from([v for v in list(S) if S.degree(v) == 0])
        for fn in (degree, h_index, department):
            add(f"faculty ({n})", S, fn)
    # the same over time: the network up to each year
    au = pd.read_csv(os.path.join(DATA, "authorship_network.csv"), low_memory=False)
    au = au[au.edge_category.isin(["same_nit", "nit_nit"])]
    fy = au.groupby(["author_a_id", "author_b_id"]).year.min()
    over = []
    for y in range(2016, PARTIAL_YEAR + 1):
        T = nx.Graph()
        T.add_edges_from(k for k, v in fy.items() if v <= y)
        null = rewired_null(T, 40, degree)
        r = degree(T)
        over.append({"year": y, "faculty_with_links": T.number_of_nodes(), "links": T.number_of_edges(),
                     "degree_assortativity": r, "null_mean": null.mean(), "z": (r - null.mean()) / null.std()})
    over = pd.DataFrame(over)
    save(over.round(4), "f_assortativity_by_year.csv")
    # mixing: which ranks work with which (observed share of links vs share expected at random)
    ranks = [r for r in RANKS if any(H.nodes[v]["designation"] == r for v in H)]
    M = nx.attribute_mixing_matrix(H, "designation", nodes=None, mapping={r: i for i, r in enumerate(ranks)},
                                   normalized=True) if all(H.nodes[v]["designation"] in ranks for v in H) else None
    if M is None:
        sub = H.subgraph([v for v in H if H.nodes[v]["designation"] in ranks])
        M = nx.attribute_mixing_matrix(sub, "designation", mapping={r: i for i, r in enumerate(ranks)}, normalized=True)
    a = M.sum(axis=1)
    mix = pd.DataFrame([{"rank_a": ranks[i], "rank_b": ranks[j], "observed_share": M[i, j] + (M[j, i] if i != j else 0),
                         "expected_share": a[i] * a[j] * (2 if i != j else 1)}
                        for i in range(len(ranks)) for j in range(i, len(ranks))])
    mix["observed_vs_expected"] = mix.observed_share / mix.expected_share
    save(mix.round(4), "f_rank_mixing.csv")
    dep = []
    for d_, vs in pd.Series({v: H.nodes[v]["department"] for v in H}).groupby(lambda v: H.nodes[v]["department"]):
        vs = set(vs.index)
        ends = sum(H.degree(v) for v in vs)
        inside = sum(1 for u, w in H.edges() if u in vs and w in vs)
        if ends >= 20:
            dep.append({"department": d_, "faculty_with_links": len(vs), "link_ends": ends,
                        "share_of_links_inside_department": 2 * inside / ends})
    dep = pd.DataFrame(dep).sort_values("share_of_links_inside_department")
    save(dep.round(4), "f_department_homophily.csv")
    # institute-level network: hub-and-spoke around our two NITs
    I = nx.read_gexf(os.path.join(DATA, "analysis", "phase2", "institute_coauthorship.gexf"))
    nodes = pd.read_csv(os.path.join(DATA, "analysis", "phase2", "institute_coauthorship_nodes.csv")).set_index("institution_id")
    for v in I:
        I.nodes[v]["cluster"] = str(nodes.cluster.get(v, "unknown"))

    def cluster_type(g):
        return nx.attribute_assortativity_coefficient(g, "cluster")
    # (degree assortativity of the institute network is in phase2.py assort; here only the mixing by institute type)
    I2 = I.copy()
    I2.remove_nodes_from(list(nodes[nodes.cluster == "NIT (ours)"].index))
    I2.remove_nodes_from([v for v in list(I2) if I2.degree(v) == 0])
    add("institutes without our two NITs", I2, cluster_type, n=30)
    t = pd.DataFrame(rows)
    save(t.round(4), "f_assortativity.csv")
    summary = {"table": t.to_dict("records"), "same_rank_link_share": float(mix[mix.rank_a == mix.rank_b].observed_share.sum()),
               "by_year": over.to_dict("records"), "rank_mixing": mix.to_dict("records"),
               "least_inward_departments": dep.head(4).to_dict("records")}
    save_json(summary, "f_assortativity_summary.json")
    fig, ax = plt.subplots(figsize=(8.5, 4.2))
    ax.plot(over.year, over.degree_assortativity, marker="o", color=INK, label="faculty network up to the year")
    ax.plot(over.year, over.null_mean, ls="--", color=MUTED, label="degree-preserving random networks")
    ax.axhline(0, color=AXIS, lw=1)
    ax.set_ylabel("degree assortativity r"); ax.legend(frameon=False)
    ax.set_title("Well-connected faculty work with each other more than chance", loc="left", color=INK)
    style_axes(ax)
    savefig(fig, "f_assortativity_by_year.png")
    print(t.round(3).to_string()); print(over.round(3).to_string()); print(mix.round(3).to_string()); print(dep.round(3).to_string())


PARTS = {"citers": citers_part, "selfcite": selfcite_part, "adjusted": adjusted_part, "core": core_part,
         "productivity": productivity_part, "turnover": turnover_part, "teams": teams_part, "assort": assort_part}


def main():
    os.makedirs(OUT, exist_ok=True)
    todo = sys.argv[1:] or list(PARTS)
    for name in todo:
        print(f"===== {name}")
        PARTS[name]()


if __name__ == "__main__":
    main()
