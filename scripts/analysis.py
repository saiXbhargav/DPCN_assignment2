"""New analyses on the faculty-only, science/engineering dataset -> data/analysis/ (CSV tables + ANALYSIS.md).

  1. Large papers (> 50 authors): what changes when they are kept or removed (with other cut-offs too)
  2. Which institute performs better (NIT Trichy vs NIT Surathkal)
  3. Which branch performs better (per institute, and head-to-head for branches both NITs have)
  4. Collaboration: existing partners, partners worth approaching, and branches to improve

Run after build_dataset.py and build_networks.py (and fetch_impact.py for FWCI and partner topics):
  python analysis.py
All statistics stay within our two NITs; partner institutes appear only through connection data.
"""
import collections
import io
import json
import os
import subprocess

import networkx as nx
import numpy as np
import pandas as pd
from scipy import stats

import build_networks as bn
from fetch_works import RAW, ROOT

DATA = os.path.join(ROOT, "data")
OUT = os.path.join(DATA, "analysis")
BASELINE = "b3bf5ba"  # commit with the first version of the data (all authors, all subjects)
CAPS = [0, 20, 30, 50, 100]  # 0 = keep every paper
SMALL_BRANCH = 8  # branches with fewer faculty than this are flagged as small
RNG = np.random.default_rng(42)
INSTS = ["NIT Trichy", "NIT Surathkal"]


def md(df, floatfmt="{:.2f}"):
    """Small markdown table writer (no extra packages)."""
    df = df.reset_index() if df.index.name or isinstance(df.index, pd.MultiIndex) else df
    def fmt(v):
        if isinstance(v, (float, np.floating)) and not pd.isna(v):
            return f"{int(v):,}" if float(v).is_integer() and abs(v) >= 10 else floatfmt.format(v)
        return "" if pd.isna(v) else str(v)
    cells = [[fmt(v) for v in row] for row in df.itertuples(index=False)]
    head = "| " + " | ".join(map(str, df.columns)) + " |\n|" + "---|" * len(df.columns) + "\n"
    return head + "".join("| " + " | ".join(r) + " |\n" for r in cells)


def boot_ci(x, f=np.mean, n=2000):
    x = np.asarray(x, dtype=float)
    x = x[~np.isnan(x)]
    if len(x) < 2:
        return np.nan, np.nan
    b = [f(RNG.choice(x, len(x))) for _ in range(n)]
    return np.percentile(b, 2.5), np.percentile(b, 97.5)


def h_index(c):
    c = sorted(c, reverse=True)
    return sum(1 for i, x in enumerate(c, 1) if x >= i)


def load():
    ds = pd.read_csv(os.path.join(DATA, "group12_data.csv"), low_memory=False)
    fac = pd.read_csv(os.path.join(DATA, "faculty.csv"))
    ic = pd.read_csv(os.path.join(DATA, "indian_connections.csv"))
    # foreign co-authors per paper, from the raw works
    foreign = {}
    corpus = set(ds.openalex_id)
    for name in INSTS:
        for line in open(os.path.join(RAW, name.replace(" ", "_") + "_works.jsonl"), encoding="utf-8"):
            w = json.loads(line)
            wid = w["id"].rsplit("/", 1)[-1]
            if wid in corpus:
                foreign[wid] = any(i.get("country_code") not in (None, "IN")
                                   for a in w["authorships"] for i in a["institutions"])
    ds["foreign_coauthor"] = ds.openalex_id.map(foreign)
    return ds, fac, ic


def paper_table(ds):
    """One row per (institution, paper)."""
    return ds.drop_duplicates(["institution", "openalex_id"]).copy()


def summarise(p, faculty_count=None):
    """Output and impact measures for a set of (institution, paper) rows."""
    journals = p[p.type == "journal"]
    ranked = journals[journals.quartile.fillna("").str.startswith("Q")]
    lo, hi = boot_ci(p.citations)
    out = {
        "papers": len(p),
        "citations": int(p.citations.sum()),
        "cites_per_paper": p.citations.mean(),
        "cites_per_paper_ci": f"{lo:.2f}-{hi:.2f}",
        "median_cites": p.citations.median(),
        "mean_fwci": p.fwci.mean() if p.fwci.notna().any() else np.nan,
        "top10pct_share": p.top10pct.astype(float).mean() if p.top10pct.notna().any() else np.nan,
        "q1_share_of_ranked_journals": (ranked.quartile == "Q1").mean() if len(ranked) else np.nan,
        "conference_share": (p.type == "conference").mean(),
        "indian_collab_share": (p.coauthor_institutes.fillna("") != "").mean(),
        "foreign_collab_share": p.foreign_coauthor.mean(),
    }
    if faculty_count:
        out["faculty"] = faculty_count
        out["papers_per_faculty"] = len(p) / faculty_count
    return out


# ---------------------------------------------------------------- 1. large papers
def large_paper_bias(ds, fac, report):
    p = paper_table(ds)
    rows = []
    for cap in CAPS:
        keep = p if not cap else p[p.n_authors <= cap]
        for inst in INSTS:
            s = summarise(keep[keep.institution == inst])
            rows.append({"max_authors": cap or "none", "institution": inst, "papers_removed":
                         int(((p.institution == inst) & (p.n_authors > cap)).sum()) if cap else 0, **s})
    paper_level = pd.DataFrame(rows)
    paper_level.to_csv(os.path.join(OUT, "large_papers_paper_level.csv"), index=False)

    # faculty rankings with and without the big papers
    def per_faculty(d):
        g = d.drop_duplicates(["faculty_id", "openalex_id"]).groupby("faculty_id")
        return pd.DataFrame({"papers": g.size(), "citations": g.citations.sum(),
                             "h_index": g.citations.apply(h_index)})
    full = per_faculty(ds)
    rank_rows = []
    for cap in CAPS[1:]:
        cut = per_faculty(ds[ds.n_authors <= cap]).reindex(full.index).fillna(0)
        for col in full.columns:
            rho = stats.spearmanr(full[col], cut[col]).statistic
            changed = int((full[col] != cut[col]).sum())
            rank_rows.append({"max_authors": cap, "measure": col, "spearman_vs_all_papers": rho,
                              "faculty_whose_value_changes": changed})
    # fractional counting: each paper shared equally among its authors
    frac = ds.assign(w=1 / ds.n_authors).groupby("faculty_id").w.sum().reindex(full.index)
    rank_rows.append({"max_authors": "fractional", "measure": "papers",
                      "spearman_vs_all_papers": stats.spearmanr(full.papers, frac).statistic,
                      "faculty_whose_value_changes": len(full)})
    ranks = pd.DataFrame(rank_rows)
    ranks.to_csv(os.path.join(OUT, "large_papers_faculty_rankings.csv"), index=False)

    # authorship network with each cut-off (same code as the submitted network)
    works, faculty, _ = bn.load_corpus()
    net_rows, central = [], {}
    for cap in CAPS:
        d = os.path.join(OUT, "sensitivity", f"cap_{cap or 'none'}")
        os.makedirs(os.path.join(d, "network_metrics"), exist_ok=True)
        au, G, comms, mod, st = bn.authorship_network(works, faculty, d, os.path.join(d, "network_metrics"), cap)
        am = pd.read_csv(os.path.join(d, "network_metrics", "author_metrics.csv"))
        central[cap] = am
        # keep only the metrics of each variant; the edge lists and Gephi files are large and easy to rebuild
        for big_file in ("authorship_network.csv", os.path.join("network_metrics", "authorship_nit.gexf")):
            os.remove(os.path.join(d, big_file))
        net_rows.append({"max_authors": cap or "none", "papers_skipped": st.get("papers_skipped_over_max_authors", 0),
                         "pair_rows": len(au), "faculty_nodes": G.number_of_nodes(),
                         "faculty_edges": G.number_of_edges(), "communities": len(comms), "modularity": mod,
                         "largest_component": len(max(nx.connected_components(G), key=len))})
    nets = pd.DataFrame(net_rows)
    base = central[0].set_index("author_id")
    for r, cap in zip(net_rows, CAPS):
        am = central[cap].set_index("author_id").reindex(base.index).fillna(0)
        r["spearman_degree"] = stats.spearmanr(base.degree, am.degree).statistic
        r["spearman_betweenness"] = stats.spearmanr(base.betweenness_centrality, am.betweenness_centrality).statistic
        top_a = set(base.nlargest(20, "betweenness_centrality").index)
        top_b = set(am.nlargest(20, "betweenness_centrality").index)
        r["top20_betweenness_overlap"] = len(top_a & top_b)
    nets = pd.DataFrame(net_rows)
    nets.to_csv(os.path.join(OUT, "large_papers_network.csv"), index=False)

    big = p[p.n_authors > 50][["institution", "title", "year", "n_authors", "citations", "field"]]
    # the same question on the first version of the data (all authors and all subjects), from git
    old = None
    try:
        raw = subprocess.run(["git", "show", f"{BASELINE}:data/group12_data.csv"], cwd=ROOT, capture_output=True,
                             check=True).stdout
        old = pd.read_csv(io.BytesIO(raw), low_memory=False).drop_duplicates(["institution", "openalex_id"])
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    report.append("## 1. Papers with more than 50 authors: is there a big bias?\n")
    if old is not None:
        ob = old[old.n_authors > 50]
        share = ob.groupby("institution").citations.sum() / old.groupby("institution").citations.sum()
        report.append(
            f"**Before the new filters** (first version of the data, all authors and subjects) there were "
            f"{ob.openalex_id.nunique()} such papers. They held "
            + ", ".join(f"{share.get(i, 0):.1%} of {i}'s citations" for i in INSTS)
            + ". The largest one, *" + ob.nlargest(1, "citations").title.iat[0][:90] + "...* ("
            + f"{int(ob.citations.max()):,} citations), was the most-cited paper of the whole dataset. "
            "It is a Social Sciences paper, so the subject filter now removes it.\n")
    report.append(f"**Now** (faculty only, science/engineering only) there are {len(big)} (institution, paper) rows "
                  "with more than 50 authors:\n\n" + (md(big) if len(big) else "none\n") + "\n")
    report.append("Institute totals with each cut-off:\n\n" + md(paper_level[[
        "max_authors", "institution", "papers_removed", "papers", "citations", "cites_per_paper", "median_cites",
        "mean_fwci"]]) + "\n")
    report.append("Faculty rankings compared with keeping every paper (Spearman correlation; 1 = identical order):\n\n"
                  + md(ranks, "{:.4f}") + "\n")
    report.append("Faculty co-authorship network with each cut-off:\n\n" + md(nets, "{:.4f}") + "\n")
    worst = ranks[ranks.max_authors == 50].spearman_vs_all_papers.min()
    report.append(f"**Verdict:** with the 50-author cut-off the faculty rankings keep a rank correlation of at least "
                  f"{worst:.3f} with the full data, and institute totals change by "
                  + ", ".join(f"{1 - paper_level[(paper_level.max_authors == 50) & (paper_level.institution == i)].citations.iat[0] / paper_level[(paper_level.max_authors == 'none') & (paper_level.institution == i)].citations.iat[0]:.1%}"
                              f" of {i}'s citations" for i in INSTS)
                  + ". After the faculty and subject filters, large papers no longer bias the results much; the "
                    "50-author rule is kept for the authorship network as standard practice.\n")


# ---------------------------------------------------------------- 2. institutes
def institutes(ds, fac, report):
    p = paper_table(ds)
    rows = []
    for inst in INSTS:
        f = fac[fac.institution == inst]
        rows.append({"institution": inst, **summarise(p[p.institution == inst], int((f.papers > 0).sum())),
                     "faculty_in_roster": len(f), "current_faculty": int((f.status == "current").sum()),
                     "median_h_index_2016_2026": f[f.papers > 0].h_index_2016_2026.median(),
                     "median_h_index_openalex": f.h_index.median()})
    t = pd.DataFrame(rows).set_index("institution")
    t.to_csv(os.path.join(OUT, "institute_comparison.csv"))

    tests = []
    a, b = fac[(fac.institution == INSTS[0]) & (fac.papers > 0)], fac[(fac.institution == INSTS[1]) & (fac.papers > 0)]
    for col in ["papers", "citations_in_period", "h_index_2016_2026", "mean_fwci"]:
        x, y = a[col].dropna(), b[col].dropna()
        if len(x) > 5 and len(y) > 5:
            u = stats.mannwhitneyu(x, y)
            tests.append({"per_faculty_measure": col, f"median_{INSTS[0]}": x.median(), f"median_{INSTS[1]}": y.median(),
                          "mann_whitney_p": u.pvalue, "difference_is_significant_5pct": u.pvalue < 0.05})
    tests = pd.DataFrame(tests)
    tests.to_csv(os.path.join(OUT, "institute_tests.csv"), index=False)

    trend = p.pivot_table(index="year", columns="institution", values="openalex_id", aggfunc="count").fillna(0).astype(int)
    trend.to_csv(os.path.join(OUT, "institute_trend.csv"))

    report.append("## 2. Which institute performs better?\n")
    report.append("Counted per institute: a paper written by faculty of both NITs counts for each. "
                  "`cites_per_paper_ci` is a 95% bootstrap interval. FWCI = OpenAlex field-weighted citation impact "
                  "(1.0 = world average for that field and year).\n\n" + md(t.T.reset_index().rename(columns={"index": "measure"})) + "\n")
    report.append("Per-faculty comparison (Mann-Whitney U test, faculty with at least one paper):\n\n" + md(tests, "{:.3f}") + "\n")
    report.append("Papers per year:\n\n" + md(trend.reset_index()) + "\n")


# ---------------------------------------------------------------- 2b. the measures asked for in class
def board_metrics(ds, report):
    """Total publications, Q1, IF > 5, IF > 10 (per institute and branch) and the impact ratio per year."""
    def counts(g):
        j = g[g.type == "journal"]
        return pd.Series({"publications": len(g), "journal_papers": len(j), "Q1": int((j.quartile == "Q1").sum()),
                          "IF>5": int((j.journal_if_2yr > 5).sum()), "IF>10": int((j.journal_if_2yr > 10).sum()),
                          "share_IF>5": (j.journal_if_2yr > 5).mean(), "share_IF>10": (j.journal_if_2yr > 10).mean()})
    p = paper_table(ds)
    inst = p.groupby("institution").apply(counts, include_groups=False)
    br = ds.drop_duplicates(["institution", "department", "openalex_id"]).groupby(
        ["institution", "department"]).apply(counts, include_groups=False).reset_index()
    inst.to_csv(os.path.join(OUT, "board_institute.csv"))
    br.to_csv(os.path.join(OUT, "board_branch.csv"), index=False)

    # impact ratio = citations received / citations made, by publication year of our papers
    refs = {}
    for name in INSTS:
        for line in open(os.path.join(RAW, name.replace(" ", "_") + "_works.jsonl"), encoding="utf-8"):
            w = json.loads(line)
            refs[w["id"].rsplit("/", 1)[-1]] = len(w["referenced_works"])
    p["refs_made"] = p.openalex_id.map(refs)
    yr = p.groupby(["institution", "year"]).agg(received=("citations", "sum"), made=("refs_made", "sum"))
    # Indian flow: citations from / to other Indian institutes, under the co-authorship rule (flow.py)
    cit = pd.read_csv(os.path.join(DATA, "citation_network.csv"), low_memory=False,
                      usecols=["source_id", "target_id", "edge_type", "source_inst", "target_inst", "year"])
    flow = collections.Counter()
    for kind, ours_col, key in (("in_indian", "target_inst", "indian_received"), ("out_indian", "source_inst", "indian_made")):
        e = cit[cit.edge_type == kind]
        for inst_label, y in zip(e[ours_col], e.year):
            for n in inst_label.split(";"):
                flow[(n, int(y), key)] += 1
    for (n, y, key), v in flow.items():
        if (n, y) in yr.index:
            yr.loc[(n, y), key] = v
    yr = yr.fillna(0)
    yr["impact_ratio"] = yr.received / yr.made
    yr["indian_impact_ratio"] = yr.indian_received / yr.indian_made
    yr.to_csv(os.path.join(OUT, "impact_ratio_by_year.csv"))
    tot = yr.groupby("institution")[["received", "made", "indian_received", "indian_made"]].sum()
    tot["impact_ratio"] = tot.received / tot.made
    tot["indian_impact_ratio"] = tot.indian_received / tot.indian_made

    report.append("## 2b. Measures asked for in class\n")
    report.append("**IF** here is OpenAlex's *2-year mean citedness* of the journal: citations in a year to the "
                  "journal's papers of the two previous years, divided by the number of those papers. That is the "
                  "impact-factor formula on OpenAlex data, because Clarivate's JCR impact factor is not open. "
                  "Conference papers have no IF.\n\n" + md(inst, "{:.3f}") + "\n")
    report.append("By branch:\n\n" + md(br, "{:.3f}") + "\n")
    report.append("**Impact ratio** = citations received / citations made (references), for papers published "
                  "2016-2026. The Indian version counts only citations from / to other Indian institutes, with the "
                  "co-authorship rule (in_indian / out_indian edges, by the citing paper's year).\n\n"
                  + md(tot, "{:.3f}") + "\n\nBy year:\n\n" + md(yr.reset_index(), "{:.3f}") + "\n")


# ---------------------------------------------------------------- 3. branches
def branches(ds, fac, report):
    p = paper_table(ds.assign(branch=ds.department))
    # a paper counts once for each branch that has a faculty author on it
    pb = ds.drop_duplicates(["institution", "department", "openalex_id"])
    rows = []
    for (inst, br), g in pb.groupby(["institution", "department"]):
        f = fac[(fac.institution == inst) & (fac.department == br)]
        active = int((f.papers > 0).sum())
        rows.append({"institution": inst, "branch": br, **summarise(g, active or None),
                     "faculty_in_roster": len(f), "median_h_index_2016_2026": f[f.papers > 0].h_index_2016_2026.median(),
                     "small_branch": active < SMALL_BRANCH})
    t = pd.DataFrame(rows)
    t.to_csv(os.path.join(OUT, "branch_comparison.csv"), index=False)

    cols = ["papers", "papers_per_faculty", "cites_per_paper", "mean_fwci", "top10pct_share", "q1_share_of_ranked_journals"]
    both = t.pivot(index="branch", columns="institution", values=cols)
    shared = [br for br in both.index if both.loc[br, ("papers", INSTS[0])] == both.loc[br, ("papers", INSTS[0])]
              and both.loc[br, ("papers", INSTS[1])] == both.loc[br, ("papers", INSTS[1])]]
    h2h = []
    for br in shared:
        r = {"branch": br}
        for c in cols:
            r[f"{c} T"] = both.loc[br, (c, INSTS[0])]
            r[f"{c} S"] = both.loc[br, (c, INSTS[1])]
        key = "mean_fwci" if not pd.isna(r["mean_fwci T"]) else "cites_per_paper"
        r["stronger_on_" + ("fwci" if key == "mean_fwci" else "cites_per_paper")] = \
            INSTS[0] if r[f"{key} T"] > r[f"{key} S"] else INSTS[1]
        h2h.append(r)
    h2h = pd.DataFrame(h2h)
    h2h.to_csv(os.path.join(OUT, "branch_head_to_head.csv"), index=False)

    rank_key = "mean_fwci" if t.mean_fwci.notna().any() else "cites_per_paper"
    ranked = t[~t.small_branch].sort_values(rank_key, ascending=False)
    report.append("## 3. Which branch performs better?\n")
    report.append(f"Branches ranked by {rank_key} (branches with fewer than {SMALL_BRANCH} publishing faculty left out):\n\n"
                  + md(ranked[["institution", "branch", "faculty", "papers", "papers_per_faculty", "cites_per_paper",
                               "mean_fwci", "top10pct_share", "q1_share_of_ranked_journals"]]) + "\n")
    report.append("Head-to-head for branches both NITs have (T = NIT Trichy, S = NIT Surathkal):\n\n"
                  + md(h2h[["branch"] + [c for c in h2h.columns if c.startswith(("papers_per_faculty", "cites_per_paper",
                                                                                   "mean_fwci", "stronger"))]]) + "\n")
    return t, h2h


# ---------------------------------------------------------------- 4. collaboration
def subfield_profile(counts):
    s = pd.Series(counts, dtype=float)
    return s / s.sum() if s.sum() else s


def collaboration(ds, ic, report, branch_table):
    p = paper_table(ds)
    ours = {inst: subfield_profile(p[p.institution == inst].subfield.value_counts()) for inst in INSTS}
    # partner topic profiles (fetch_impact.py partners) are by subfield id; ours are by name -> map via raw works
    names = {}
    for name in INSTS:
        for line in open(os.path.join(RAW, name.replace(" ", "_") + "_works.jsonl"), encoding="utf-8"):
            t = (json.loads(line).get("primary_topic") or {}).get("subfield") or {}
            if t:
                names[t["id"].rsplit("/", 1)[-1]] = t["display_name"]
    partner_topics = {}
    path = os.path.join(RAW, "partner_subfields.jsonl")
    if os.path.exists(path):
        for r in map(json.loads, open(path, encoding="utf-8")):
            partner_topics[r["id"]] = subfield_profile({names.get(k, k): v for k, v in r["subfields"].items()})

    def jaccard(a, b, top=40):
        sa, sb = set(a.nlargest(top).index), set(b.nlargest(top).index)
        return len(sa & sb) / len(sa | sb) if sa | sb else np.nan

    def weighted_jaccard(a, b):
        idx = a.index.union(b.index)
        x, y = a.reindex(idx, fill_value=0), b.reindex(idx, fill_value=0)
        return np.minimum(x, y).sum() / np.maximum(x, y).sum()

    # joint papers: is their impact higher than the NIT's other papers?
    p_has = {inst: p[p.institution == inst] for inst in INSTS}
    rows = []
    for r in ic[~ic.partner_id.isin(["I122964287", "I11880225"])].itertuples(index=False):
        joint = p_has[r.your_inst][p_has[r.your_inst].coauthor_institutes.fillna("").str.split(";").apply(
            lambda xs: r.partner_inst in xs)]
        prof = partner_topics.get(r.partner_id)
        rows.append({
            "institution": r.your_inst, "partner": r.partner_inst, "partner_id": r.partner_id,
            "shared_papers": r.shared_papers, "cites_from_partner": r.cites_from_partner,
            "cites_to_partner": r.cites_to_partner, "exchange": r.cites_from_partner + r.cites_to_partner,
            "joint_mean_fwci": joint.fwci.mean() if len(joint) and joint.fwci.notna().any() else np.nan,
            "joint_cites_per_paper": joint.citations.mean() if len(joint) else np.nan,
            "topic_jaccard_top40": jaccard(ours[r.your_inst], prof) if prof is not None else np.nan,
            "topic_weighted_jaccard": weighted_jaccard(ours[r.your_inst], prof) if prof is not None else np.nan,
        })
    t = pd.DataFrame(rows)
    # opportunity: partners that already exchange many citations with us and work on similar topics,
    # but have few joint papers yet
    t["opportunity_score"] = t.topic_weighted_jaccard * np.log1p(t.exchange) / np.log1p(1 + t.shared_papers)
    t.to_csv(os.path.join(OUT, "partners.csv"), index=False)

    base = {inst: {"fwci": p_has[inst].fwci.mean(), "cpp": p_has[inst].citations.mean()} for inst in INSTS}
    report.append("## 4. Collaborate with whom, and what to improve\n")
    for inst in INSTS:
        ti = t[t.institution == inst]
        top = ti.nlargest(10, "shared_papers")[["partner", "shared_papers", "joint_cites_per_paper", "joint_mean_fwci",
                                                "exchange", "topic_weighted_jaccard"]]
        opp = ti[(ti.shared_papers <= 5) & ti.opportunity_score.notna()].nlargest(10, "opportunity_score")[
            ["partner", "shared_papers", "cites_from_partner", "cites_to_partner", "topic_weighted_jaccard",
             "topic_jaccard_top40", "opportunity_score"]]
        report.append(f"### {inst}\n\nStrongest current partners (all of {inst}'s papers: {base[inst]['cpp']:.1f} citations "
                      f"per paper, mean FWCI {base[inst]['fwci']:.2f}):\n\n" + md(top) + "\n")
        report.append("**Partners worth approaching**: strong citation exchange and similar research topics, but at most "
                      "5 joint papers so far (score = topic similarity x log(citation exchange) / log(joint papers + 2)):"
                      "\n\n" + md(opp, "{:.3f}") + "\n")

    nn = int((ds.groupby("openalex_id").institution.nunique() == 2).sum())
    report.append(f"### NIT Trichy and NIT Surathkal together\n\nOnly {nn} papers have faculty authors from both NITs. "
                  "Branches where one NIT is clearly stronger are natural places to start joint work:\n\n")
    bt = branch_table
    key = "mean_fwci" if bt.mean_fwci.notna().any() else "cites_per_paper"
    piv = bt[~bt.small_branch].pivot(index="branch", columns="institution", values=key).dropna()
    piv["gap"] = piv[INSTS[0]] - piv[INSTS[1]]
    piv["learn_from"] = np.where(piv.gap > 0, INSTS[0], INSTS[1])
    report.append(md(piv.sort_values("gap", key=abs, ascending=False).reset_index()) + "\n")
    improve = []
    for inst in INSTS:
        bi = bt[(bt.institution == inst) & ~bt.small_branch]
        for c in ["mean_fwci", "q1_share_of_ranked_journals", "foreign_collab_share"]:
            if bi[c].notna().any():
                w = bi.nsmallest(2, c)
                improve += [{"institution": inst, "measure": c, "branch": r.branch, "value": getattr(r, c),
                             "institute_value": summarise(p_has[inst])[c]} for r in w.itertuples()]
    report.append("**Areas to improve** (the two weakest regular-size branches on each measure):\n\n"
                  + md(pd.DataFrame(improve), "{:.3f}") + "\n")


# ---------------------------------------------------------------- 5. Task 3: Indian connectivity
BLUE, ORANGE = "#2a78d6", "#eb6834"  # categorical slots 1-2 (validated light palette)
INK, MUTED, GRID, AXIS, SURFACE = "#0b0b0b", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"


def style_axes(ax):
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(AXIS)
    ax.tick_params(colors=MUTED, labelsize=9)
    ax.grid(axis="y", color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)


def flow_chart(yearly, path):
    """Small multiples, one panel per NIT, same y-axis: citations received from and given to other Indian
    institutes per year."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8), sharey=True, facecolor=SURFACE)
    for ax, inst in zip(axes, INSTS):
        d = yearly[yearly.institution == inst].set_index("year")
        style_axes(ax)
        for col, color, label in (("received", BLUE, "Received (in-flow)"), ("given", ORANGE, "Given (out-flow)")):
            ax.plot(d.index, d[col], color=color, linewidth=2, marker="o", markersize=4, label=label)
            ax.annotate(label.split(" ")[0], (d.index[-1], d[col].iloc[-1]), xytext=(4, 0),
                        textcoords="offset points", color=INK, fontsize=8, va="center")
        ax.set_title(inst, color=INK, fontsize=11, loc="left")
        ax.set_xticks(range(2016, 2027, 2))
    axes[0].set_ylabel("Citations per year", color=INK, fontsize=9)
    axes[0].legend(frameon=False, fontsize=8, labelcolor=INK, loc="upper left")
    fig.suptitle("Citation flow with other Indian institutes, by year of the citing paper", color=INK,
                 fontsize=11, x=0.01, ha="left")
    fig.text(0.01, 0.01, "2026 is a partial year (data collected October 2026). Co-authored papers are not counted.",
             color=MUTED, fontsize=8)
    fig.tight_layout(rect=(0, 0.04, 1, 0.95))
    fig.savefig(path, dpi=160, facecolor=SURFACE)
    plt.close(fig)


def cluster_chart(clusters, path):
    """Shared (co-authored) papers with each cluster of partner institutes, one bar per NIT."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    piv = clusters.pivot(index="partner_cluster", columns="your_inst", values="shared_papers").fillna(0)
    piv = piv.loc[piv.sum(axis=1).sort_values().index]
    fig, ax = plt.subplots(figsize=(8, 5), facecolor=SURFACE)
    style_axes(ax)
    ax.grid(axis="x", color=GRID, linewidth=0.6)
    ax.grid(axis="y", visible=False)
    y = np.arange(len(piv))
    h = 0.38
    for k, (inst, color) in enumerate(zip(INSTS, (BLUE, ORANGE))):
        vals = piv.get(inst, pd.Series(0, index=piv.index))
        ax.barh(y + (0.5 - k) * (h + 0.04), vals, height=h, color=color, label=inst)
    ax.set_yticks(y, piv.index, color=INK, fontsize=9)
    ax.set_xlabel("Co-authored papers (a paper counts once for each partner on it)", color=INK, fontsize=9)
    ax.legend(frameon=False, fontsize=9, labelcolor=INK, loc="lower right")
    ax.set_title("Co-authored papers by type of partner institute", color=INK, fontsize=11, loc="left")
    fig.tight_layout()
    fig.savefig(path, dpi=160, facecolor=SURFACE)
    plt.close(fig)


def task3(ds, ic, report):
    from clusters import OUR_CLUSTER
    cit = pd.read_csv(os.path.join(DATA, "citation_network.csv"), low_memory=False)
    info_path = os.path.join(RAW, "citers_info.jsonl")
    citers = {r["id"]: r for r in map(json.loads, open(info_path, encoding="utf-8"))} if os.path.exists(info_path) else {}

    # a) in-flow / out-flow by year (year of the citing paper)
    rows = []
    for kind, col, key in (("in_indian", "target_inst", "received"), ("out_indian", "source_inst", "given")):
        e = cit[cit.edge_type == kind]
        for label, y in zip(e[col], e.year):
            for inst in label.split(";"):
                rows.append({"institution": inst, "year": int(y), "kind": key})
    yearly = pd.DataFrame(rows).pivot_table(index=["institution", "year"], columns="kind", aggfunc="size",
                                            fill_value=0).reset_index()
    yearly = yearly[yearly.year.between(2016, 2026)]
    yearly["ratio_received_to_given"] = yearly.received / yearly.given
    yearly.to_csv(os.path.join(OUT, "task3_flow_by_year.csv"), index=False)
    flow_chart(yearly, os.path.join(OUT, "task3_citation_flow_by_year.png"))
    totals = yearly.groupby("institution")[["received", "given"]].sum()
    totals["ratio_received_to_given"] = totals.received / totals.given

    # b) top 10 Indian institutes citing each NIT, and c) top 10 most-cited papers citing each NIT
    p = ic[~ic.partner_id.isin(["I122964287", "I11880225"])]
    top_citing = (p.sort_values(["your_inst", "cites_from_partner"], ascending=[False, False]).groupby("your_inst").head(10)
                  [["your_inst", "partner_inst", "partner_cluster", "cites_from_partner", "cites_to_partner",
                    "shared_papers"]])
    top_citing.to_csv(os.path.join(OUT, "task3_top_citing_institutes.csv"), index=False)
    e = cit[cit.edge_type == "in_indian"]
    paper_rows = []
    for inst in INSTS:
        mine = e[e.target_inst.str.split(";").apply(lambda xs: inst in xs)]
        n_ours = mine.groupby("source_id").target_id.nunique()
        for sid, k in n_ours.items():
            c = citers.get(sid)
            if c:
                paper_rows.append({"institution": inst, "citing_paper": c["title"], "year": c["year"],
                                   "venue": c["venue"], "its_citations": c["cited_by_count"],
                                   "citing_institutes": mine.source_inst[mine.source_id == sid].iat[0],
                                   "our_papers_it_cites": k, "openalex_id": sid})
    paper_df = pd.DataFrame(paper_rows)
    paper_df = paper_df[~paper_df.citing_paper.fillna("").str.match(r"(?i)retracted")]  # leave out retracted papers
    top_papers = (paper_df.sort_values(["institution", "its_citations"], ascending=[False, False])
                  .groupby("institution").head(10))
    top_papers.to_csv(os.path.join(OUT, "task3_top_citing_papers.csv"), index=False)

    # d) connectivity map: co-authorship partners, by cluster, with cross-cluster flags
    partners = p[p.shared_papers > 0]
    clusters = (p.groupby(["your_inst", "partner_cluster"])
                .agg(partners=("partner_id", "size"), co_author_partners=("shared_papers", lambda s: int((s > 0).sum())),
                     shared_papers=("shared_papers", "sum"), cites_from_partner=("cites_from_partner", "sum"),
                     cites_to_partner=("cites_to_partner", "sum")).reset_index())
    clusters["cross_cluster"] = clusters.partner_cluster != OUR_CLUSTER
    clusters.to_csv(os.path.join(OUT, "task3_partner_clusters.csv"), index=False)
    cluster_chart(clusters, os.path.join(OUT, "task3_partner_clusters.png"))
    top_partners = (partners.sort_values(["your_inst", "shared_papers"], ascending=[False, False]).groupby("your_inst").head(15)
                    [["your_inst", "partner_inst", "partner_cluster", "cross_cluster", "shared_papers",
                      "total_citations"]])
    top_partners.to_csv(os.path.join(OUT, "task3_top_coauthor_partners.csv"), index=False)

    # e) research-topic similarity (Jaccard) with the main partners
    sim = pd.read_csv(os.path.join(OUT, "partners.csv")).dropna(subset=["topic_jaccard_top40"])
    sim = sim.merge(ic[["your_inst", "partner_id", "partner_cluster"]], left_on=["institution", "partner_id"],
                    right_on=["your_inst", "partner_id"], how="left")
    top_sim = (sim.sort_values(["institution", "topic_weighted_jaccard"], ascending=[False, False]).groupby("institution").head(10)
               [["institution", "partner", "partner_cluster", "topic_jaccard_top40", "topic_weighted_jaccard",
                 "shared_papers"]])
    sim[["institution", "partner", "partner_cluster", "topic_jaccard_top40", "topic_weighted_jaccard", "shared_papers",
         "exchange"]].to_csv(os.path.join(OUT, "task3_topic_similarity.csv"), index=False)

    # f) hub authors: faculty who connect the most other institutes
    am = pd.read_csv(os.path.join(DATA, "network_metrics", "author_metrics.csv"))
    branch = ds.drop_duplicates("faculty_id").set_index("faculty_id").department
    am["branch"] = am.author_id.map(branch)
    am = am[am.institution.isin(INSTS)]  # (a few people are listed with both NITs on one paper)
    hubs = (am.sort_values(["institution", "indian_partner_institutes", "betweenness_centrality"], ascending=False)
            .groupby("institution").head(10)
            [["institution", "author", "branch", "indian_partner_institutes", "degree", "betweenness_centrality",
              "papers"]])
    hubs.to_csv(os.path.join(OUT, "task3_hub_authors.csv"), index=False)

    report.append("## 5. Task 3: Indian connectivity\n")
    report.append("All counts follow the co-authorship rule (`scripts/flow.py`): a citation between papers that share "
                  "an institute through co-authorship is not counted as flow between institutes.\n")
    report.append("### Citation flow\n\nCitations **received from** and **given to** other Indian institutes "
                  "(2016–2026, by year of the citing paper), and the citation impact ratio (received / given):\n\n"
                  + md(totals.reset_index(), "{:.3f}") + "\n\nThe yearly ratio rises from about 0.02 in 2016 to "
                  "above 1 from 2023. Part of this is timing: our papers are from 2016 onwards, so in the early years "
                  "they had little time to be cited, while they cite older work at once. The ratio above 1 in recent "
                  "years means both NITs now receive more citations from other Indian institutes than they give.\n")
    report.append("![Citation flow by year](task3_citation_flow_by_year.png)\n\nBy year "
                  "(`task3_flow_by_year.csv`):\n\n" + md(yearly, "{:.2f}") + "\n")
    report.append("### Top 10 Indian institutes citing each NIT\n\nThe other NIT is left out of this list.\n\n"
                  + md(top_citing) + "\n")
    report.append("### Top 10 most-cited papers that cite each NIT\n\nPapers by other Indian institutes that cite our "
                  "work, ranked by their own citation count (retracted papers left out):\n\n"
                  + md(top_papers.drop(columns=["openalex_id"]).assign(
                      citing_paper=top_papers.citing_paper.str.slice(0, 90),
                      citing_institutes=top_papers.citing_institutes.str.slice(0, 60))) + "\n")
    report.append("### Connectivity map\n\n"
                  + " ".join(f"{inst}'s faculty co-authored with **{int((partners.your_inst == inst).sum())} Indian "
                             f"institutes**." for inst in INSTS)
                  + f" Every partner has a cluster (from its name, its OpenAlex type and its parent organisation); "
                    f"a link is **cross-cluster** when the partner is not an {OUR_CLUSTER}.\n\n"
                  "![Co-authored papers by partner cluster](task3_partner_clusters.png)\n\n"
                  + md(clusters) + "\n\nStrongest co-authorship partners (top 15 per NIT):\n\n" + md(top_partners) + "\n")
    report.append("### Research-topic similarity (Jaccard)\n\nJaccard similarity of research subfields between each "
                  "NIT and its main partners: `topic_jaccard_top40` compares the 40 largest subfields of each side; "
                  "`topic_weighted_jaccard` compares their full subfield shares (1 = identical mix).\n\n"
                  + md(top_sim, "{:.3f}") + "\n")
    report.append("### Hub authors\n\nFaculty who link their NIT with the most other Indian institutes "
                  "(`indian_partner_institutes`), with their betweenness in the faculty co-authorship network:\n\n"
                  + md(hubs, "{:.4f}") + "\n")


def main():
    os.makedirs(OUT, exist_ok=True)
    ds, fac, ic = load()
    report = ["# Team 12: new analyses (faculty only, science / engineering papers)\n",
              f"Dataset: {ds.openalex_id.nunique():,} papers, {len(ds):,} (paper, faculty) rows, "
              f"{ds.faculty_id.nunique()} faculty with papers. "
              + ("" if ds.fwci.notna().any() else "FWCI is not available yet (run `fetch_impact.py works`), so "
                 "rankings use citations per paper. ") + "Generated by `scripts/analysis.py`.\n"]
    large_paper_bias(ds, fac, report)
    institutes(ds, fac, report)
    board_metrics(ds, report)
    bt, _ = branches(ds, fac, report)
    collaboration(ds, ic, report, bt)
    task3(ds, ic, report)
    with open(os.path.join(OUT, "ANALYSIS.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(report))
    print("\n".join(report)[:6000])


if __name__ == "__main__":
    main()
