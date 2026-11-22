"""Builds the LaTeX report (Task 4 statistics + Phase II findings) in report/.

  python build_report.py            # figures, tables and numbers from the data, then compile with Tectonic if found
  python build_report.py --no-pdf   # only write the generated files (to compile in Overleaf)

report/main.tex is written by hand. This script writes everything it reads from the data:
  report/figures/*.pdf     the figures (matplotlib, vector)
  report/tables/*.tex      the tables (booktabs)
  report/numbers.tex       one LaTeX macro per number used in the text (e.g. \\nPapers)
so every number in the report comes from the analysis outputs and stays in step with the dashboard and FINDINGS.md.
Compiling: Tectonic (set TECTONIC=path\\to\\tectonic.exe or put it on PATH), or upload report/ to Overleaf (XeLaTeX).
The report must stay within 10 pages; the script prints the page count.
"""
import json
import os
import re
import shutil
import subprocess
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
AN = os.path.join(DATA, "analysis")
REP = os.path.join(ROOT, "report")
FIG, TAB = os.path.join(REP, "figures"), os.path.join(REP, "tables")
PDF_NAME = "Group12_NITTrichy_NITSurathkal_Report.pdf"
T, S = "NIT Trichy", "NIT Surathkal"
CT, CS, CB, INK, GREY = "#2a78d6", "#eb6834", "#6250d6", "#1e293b", "#94a3b8"
MAX_PAGES = 10
COLW = 3.3          # inches: one column of the two-column layout

plt.rcParams.update({"font.family": "serif", "font.serif": ["STIXGeneral", "Times New Roman", "DejaVu Serif"], "mathtext.fontset": "stix",
                     "font.size": 7.5, "axes.spines.top": False, "axes.spines.right": False, "axes.edgecolor": GREY,
                     "axes.labelcolor": INK, "xtick.color": INK, "ytick.color": INK, "legend.frameon": False, "legend.fontsize": 7,
                     "pdf.fonttype": 42})

UNI = {"−": "$-$", "–": "--", "—": "---", "’": "'", "‘": "`", "“": "``", "”": "''", "×": "$\\times$", "→": "$\\to$", "∝": "$\\propto$",
       "≈": "$\\approx$", "≥": "$\\geq$", "≤": "$\\leq$", "²": "$^2$", "₀": "$_0$", "₁": "$_1$", "β": "$\\beta$", "λ": "$\\lambda$",
       "ρ": "$\\rho$", "σ": "$\\sigma$", "α": "$\\alpha$", "μ": "$\\mu$", "χ": "$\\chi$", "η": "$\\eta$", "…": "\\ldots{}", "·": "$\\cdot$",
       "é": "\\'e", "á": "\\'a", "ö": "\\\"o", "ü": "\\\"u", "Δ": "$\\Delta$", "π": "$\\pi$", "°": "$^\\circ$"}


MATH = {"1/λ_NB": "$1/\\lambda_{NB}$", "λ_NB": "$\\lambda_{NB}$", "β_c": "$\\beta_c$", "K₀/λ₁": "$K_0/\\lambda_1$", "K_c": "$K_c$"}


def tx(s):
    """Plain text -> safe LaTeX (special characters escaped, symbols turned into math)."""
    s = str(s)
    keep = {}
    for i, (a, b) in enumerate(MATH.items()):
        if a in s:
            s = s.replace(a, f"@@{i}@@"); keep[f"@@{i}@@"] = b
    s = s.replace("\\", "\\textbackslash{}")
    for a, b in (("&", "\\&"), ("%", "\\%"), ("$", "\\$"), ("#", "\\#"), ("_", "\\_"), ("{", "\\{"), ("}", "\\}"), ("~", "\\textasciitilde{}")):
        s = s.replace(a, b)
    s = re.sub(r"\^([0-9a-zA-Z.]+)", r"$^{\1}$", s)
    for a, b in UNI.items():
        s = s.replace(a, b)
    for a, b in keep.items():
        s = s.replace(a, b)
    return s.replace("$$", "")


def n(x, d=0):
    """Number with thousands separators for LaTeX."""
    return f"{x:,.{d}f}".replace(",", "{,}")


def pc(x, d=0):
    return f"{100 * x:.{d}f}\\%"


def rd(*p):
    return pd.read_csv(os.path.join(*p), low_memory=False)


def js(*p):
    return json.load(open(os.path.join(*p), encoding="utf-8"))


def short(t, k):
    t = str(t)
    return t if len(t) <= k else t[: k - 1].rstrip() + "…"


def save_fig(fig, name):
    fig.savefig(os.path.join(FIG, name), bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)


def write_table(name, body):
    open(os.path.join(TAB, name), "w", encoding="utf-8").write(body.strip() + "\n")


def nit(i):
    return {T: "T", S: "S"}.get(i, "Both")


def build():
    os.makedirs(FIG, exist_ok=True)
    os.makedirs(TAB, exist_ok=True)
    M = {}                     # macro name -> LaTeX text
    g = rd(DATA, "group12_data.csv")
    fac = rd(DATA, "faculty.csv").drop_duplicates("faculty_id")
    papers = g.drop_duplicates(["institution", "openalex_id"])
    uniq = g.drop_duplicates("openalex_id")
    per = papers.groupby("institution").openalex_id.nunique()
    joint = int(per.sum() - uniq.openalex_id.nunique())
    nfac = fac.groupby("institution").size()
    big = rd(AN, "large_papers_paper_level.csv")
    b0 = big[big.max_authors.astype(str) == "none"].set_index("institution")
    tests = rd(AN, "institute_tests.csv").set_index("per_faculty_measure")
    sens = rd(AN, "papers", "r_fwci_model_sensitivity.csv").iloc[0]
    rmod = rd(AN, "papers", "r_papers_per_year_models.csv").set_index("model")
    wr = {r["rank"]: r for r in js(AN, "papers", "r_summary.json")["within_rank"]}
    fd = rd(AN, "papers", "r_false_discovery.csv")
    bb = rd(AN, "ns_branch_fwci_bootstrap.csv").set_index("branch")
    keep = fd[fd.family.str.startswith("branch FWCI") & fd.significant_after_fdr].test.tolist()
    medfw = papers.groupby("institution").fwci.median()
    nsum = js(DATA, "network_metrics", "network_summary.json")["authorship_network"]
    sc = js(AN, "papers", "s_summary.json")
    M.update(nFaculty=n(nfac.sum()), nFacT=n(nfac[T]), nFacS=n(nfac[S]), nPapers=n(uniq.openalex_id.nunique()), nPapT=n(per[T]), nPapS=n(per[S]),
             nJoint=n(joint), nLinks=n(nsum["nit_graph_edges"]), nInternal=n(sc["internal_edges"]))

    # ---------------------------------------------------------------- publication trend
    yrs = list(range(2016, 2027))
    tr = papers.groupby(["institution", "year"]).size().unstack(0).reindex(yrs).fillna(0)
    fig, ax = plt.subplots(figsize=(COLW, 1.45))
    x = np.arange(len(yrs))
    ax.bar(x - 0.2, tr[T], 0.4, color=CT, label="NIT Trichy")
    ax.bar(x + 0.2, tr[S], 0.4, color=CS, label="NIT Surathkal")
    ax.set_xticks(x, [str(y) if y < 2026 else "2026*" for y in yrs], fontsize=6.3)
    ax.set_ylabel("faculty papers"); ax.set_ylim(0, tr.values.max() * 1.25); ax.legend(loc="upper left", ncol=2); ax.grid(axis="y", alpha=0.25)
    save_fig(fig, "fig_trend.pdf")
    y16, y25 = int((uniq.year == 2016).sum()), int((uniq.year == 2025).sum())
    M.update(yrA=n(y16), yrB=n(y25), growth=f"{y25 / y16:.1f}")

    # ---------------------------------------------------------------- head to head
    jr = papers[papers.type == "journal"]
    jshare = jr.groupby("institution").size() / per
    if5 = jr.assign(h=jr.journal_if_2yr > 5).groupby("institution").h.mean()
    rows = [("Faculty (regular, S\\&E, incl.\\ former)", n(nfac[T]), n(nfac[S])),
            ("Papers 2016--2026", n(per[T]), n(per[S])),
            ("Share in journals", pc(jshare[T]), pc(jshare[S])),
            ("Citations per paper (raw)", n(b0.loc[T, "cites_per_paper"], 1), n(b0.loc[S, "cites_per_paper"], 1)),
            ("Mean / median FWCI", f"{b0.loc[T, 'mean_fwci']:.2f} / {medfw[T]:.2f}", f"{b0.loc[S, 'mean_fwci']:.2f} / {medfw[S]:.2f}"),
            ("Top 10\\% cited (world)", pc(b0.loc[T, "top10pct_share"], 1), pc(b0.loc[S, "top10pct_share"], 1)),
            ("Q1 share of ranked journal papers", pc(b0.loc[T, "q1_share_of_ranked_journals"], 1), "\\textbf{" + pc(b0.loc[S, "q1_share_of_ranked_journals"], 1) + "}"),
            ("Share in IF $>$ 5 journals", pc(if5[T], 1), pc(if5[S], 1)),
            ("Median papers per faculty", n(tests.loc["papers", "median_NIT Trichy"]), "\\textbf{" + n(tests.loc["papers", "median_NIT Surathkal"]) + "}"),
            ("Median h-index (2016--2026)", n(tests.loc["h_index_2016_2026", "median_NIT Trichy"]), "\\textbf{" + n(tests.loc["h_index_2016_2026", "median_NIT Surathkal"]) + "}")]
    write_table("tab_h2h.tex", "\\begin{tabular}{@{}lrr@{}}\n\\toprule\n & Trichy & Surathkal \\\\\n\\midrule\n" +
                "\n".join(f"{a} & {b} & {c} \\\\" for a, b, c in rows) + "\n\\bottomrule\n\\end{tabular}")
    M.update(fwciEffect=f"{sens.surathkal_effect_pct:+.1f}", pRobust=f"{sens.p_robust:.2f}", pClust=f"{sens.p_clustered:.2f}",
             asstT=pc(wr["Assistant Professor"]["share_of_trichy_faculty"]), asstS=pc(wr["Assistant Professor"]["share_of_surathkal_faculty"]),
             gapRaw=f"{rmod.loc['no controls', 'surathkal_effect_pct']:+.0f}\\%", gapRank=f"{rmod.loc['+ rank', 'surathkal_effect_pct']:+.0f}\\%",
             pProf=f"{wr['Professor']['p_papers_per_year']:.2f}",
             brS=" and ".join(b for b in keep if bb.loc[b, "difference_T_minus_S"] < 0), brT=" and ".join(b for b in keep if bb.loc[b, "difference_T_minus_S"] > 0),
             qOneT=pc(b0.loc[T, "q1_share_of_ranked_journals"], 1), qOneS=pc(b0.loc[S, "q1_share_of_ranked_journals"], 1),
             ifFiveT=pc(if5[T], 1), ifFiveS=pc(if5[S], 1), citT=n(b0.loc[T, "cites_per_paper"], 1), citS=n(b0.loc[S, "cites_per_paper"], 1))

    # ---------------------------------------------------------------- top 5 journals
    blocks = []
    for inst in (T, S):
        sub = jr[jr.institution == inst]
        top = sub.groupby("journal_name").agg(k=("openalex_id", "nunique"), q=("quartile", lambda s: s.mode().iat[0] if s.notna().any() else "--"),
                                              IF=("journal_if_2yr", "median")).sort_values("k", ascending=False).head(5)
        blocks.append(f"\\multicolumn{{4}}{{@{{}}l}}{{\\textit{{{inst}}}}} \\\\\n" +
                      "\n".join(f"{tx(short(j, 44))} & {n(r.k)} & {tx(r.q)} & {r.IF:.1f} \\\\" for j, r in top.iterrows()))
    write_table("tab_journals.tex", "\\begin{tabular}{@{}lrcr@{}}\n\\toprule\nJournal & Papers & Q & IF \\\\\n\\midrule\n" +
                "\n\\midrule\n".join(blocks) + "\n\\bottomrule\n\\end{tabular}")

    # ---------------------------------------------------------------- h-index
    fp = fac[fac.papers > 0]
    bins, labels = [0, 5, 10, 15, 20, 25, 30, 1000], ["0–4", "5–9", "10–14", "15–19", "20–24", "25–29", "30+"]
    hc = fp.assign(b=pd.cut(fp.h_index_2016_2026, bins, right=False, labels=labels)).groupby(["institution", "b"], observed=False).size().unstack(0)
    fig, ax = plt.subplots(figsize=(COLW, 1.35))
    x = np.arange(len(labels))
    for off, inst, c in ((-0.2, T, CT), (0.2, S, CS)):
        ax.bar(x + off, hc[inst], 0.4, color=c, label=f"{inst} ({int((fp.institution == inst).sum())} faculty)")
    ax.set_xticks(x, labels); ax.set_xlabel("h-index from 2016–2026 papers"); ax.set_ylabel("faculty"); ax.legend(); ax.grid(axis="y", alpha=0.25)
    save_fig(fig, "fig_hindex.pdf")
    M.update(hT=n(tests.loc["h_index_2016_2026", "median_NIT Trichy"]), hS=n(tests.loc["h_index_2016_2026", "median_NIT Surathkal"]),
             pH=f"{tests.loc['h_index_2016_2026', 'mann_whitney_p']:.3f}", papMedT=n(tests.loc["papers", "median_NIT Trichy"]),
             papMedS=n(tests.loc["papers", "median_NIT Surathkal"]), pFwciPers=f"{tests.loc['mean_fwci', 'mann_whitney_p']:.2f}")

    # ---------------------------------------------------------------- research areas + AI
    fl = papers.groupby(["field", "institution"]).size().unstack(1).fillna(0)
    fl = fl.assign(all=fl.sum(1)).sort_values("all", ascending=False)
    rows = [(tx(i), n(r[T]), pc(r[T] / per[T]), n(r[S]), pc(r[S] / per[S])) for i, r in fl.head(7).iterrows()]
    o = fl.iloc[7:][[T, S]].sum()
    rows.append(("All other fields", n(o[T]), pc(o[T] / per[T]), n(o[S]), pc(o[S] / per[S])))
    write_table("tab_fields.tex", "\\begin{tabular}{@{}lrrrr@{}}\n\\toprule\nField (OpenAlex) & \\multicolumn{2}{c}{Trichy} & \\multicolumn{2}{c}{Surathkal} \\\\\n\\midrule\n" +
                "\n".join(" & ".join(r) + " \\\\" for r in rows) + "\n\\bottomrule\n\\end{tabular}")
    ai = rd(AN, "insights", "ai_share_by_year.csv")
    aa, ao = (ai[ai.computing == k].set_index("year").ai_share_pct for k in ("all papers", "other departments"))
    ais = js(AN, "insights", "ai_summary.json")
    M.update(aiA=f"{aa[2016]:.1f}", aiB=f"{aa[2025]:.1f}", aiOA=f"{ao[2016]:.1f}", aiOB=f"{ao[2025]:.1f}",
             aiDeptA=str(ais["departments_with_ai_share_ge_5pct_2016_2018"]), aiDeptB=str(ais["departments_with_ai_share_ge_5pct_2023_2025"]),
             aiDeptN=str(ais["departments"]))

    # ---------------------------------------------------------------- department level: FWCI by branch (bootstrap + FDR)
    fdb = fd[fd.family.str.startswith("branch FWCI")].set_index("test")
    rows = []
    for b_, r in bb.sort_values("difference_T_minus_S").iterrows():
        pa = fdb.loc[b_, "p_adjusted_bh"] if b_ in fdb.index else float("nan")
        if b_ in fdb.index and fdb.loc[b_, "significant_after_fdr"]:
            v = "\\textbf{" + ("Surathkal" if r.difference_T_minus_S < 0 else "Trichy") + "}"
        elif b_ in fdb.index and fdb.loc[b_, "significant_raw"]:
            v = ("Surathkal" if r.difference_T_minus_S < 0 else "Trichy") + "$^\\dagger$"
        else:
            v = "level"
        rows.append(f"{tx(b_)} & {n(r.papers_T)} & {n(r.papers_S)} & {r.fwci_T:.2f} & {r.fwci_S:.2f} & {pa:.3f} & {v} \\\\")
    write_table("tab_branches.tex", "\\begin{tabular}{@{}lrrrrrl@{}}\n\\toprule\nBranch & \\multicolumn{2}{c}{Papers} & \\multicolumn{2}{c}{Mean FWCI} & $p_{adj}$ & Stronger \\\\\n"
                "\\cmidrule(lr){2-3}\\cmidrule(lr){4-5}\n & T & S & T & S & & \\\\\n\\midrule\n" + "\n".join(rows) + "\n\\bottomrule\n\\end{tabular}")
    M.update(nBranch=str(len(bb)))

    # ---------------------------------------------------------------- top 10 cited
    both = set(g[g.both_nits.astype(str).str.lower() == "true"].openalex_id)
    tc = uniq.sort_values(["citations", "openalex_id"], ascending=[False, True]).head(10)
    write_table("tab_cited.tex", "\\begin{tabular}{@{}rp{8.6cm}p{3.7cm}rrrc@{}}\n\\toprule\n\\# & Title & Journal & Year & Citations & FWCI & NIT \\\\\n\\midrule\n" +
                "\n".join(f"{k + 1} & {tx(short(r.title, 82))} & {tx(short(r.journal_name, 33))} & {r.year} & {n(r.citations)} & {r.fwci:.1f} & "
                          f"{'Both' if r.openalex_id in both else nit(r.institution)} \\\\" for k, (_, r) in enumerate(tc.iterrows())) +
                "\n\\bottomrule\n\\end{tabular}")
    M.update(topTrichy=str(sum(r.institution == T for _, r in tc.iterrows())), topReview=str(sum("review" in str(t).lower() for t in tc.title)))

    # ---------------------------------------------------------------- citation network
    cpm = rd(DATA, "network_metrics", "citation_paper_metrics.csv").sort_values(["pagerank", "openalex_id"], ascending=[False, True])
    write_table("tab_pagerank.tex", "\\begin{tabular}{@{}rp{5.15cm}crr@{}}\n\\toprule\n\\# & Title & NIT & Year & $k_{in}$ \\\\\n\\midrule\n" +
                "\n".join(f"{k + 1} & {tx(short(r.title, 44))} & {nit(r.institution)} & {r.year} & {n(r.in_degree_internal)} \\\\"
                          for k, (_, r) in enumerate(cpm.head(10).iterrows())) + "\n\\bottomrule\n\\end{tabular}")
    indeg = cpm.in_degree_internal
    vc = indeg[indeg > 0].value_counts().sort_index()
    fig, ax = plt.subplots(figsize=(COLW * 0.62, 1.35))
    ax.loglog(vc.index, vc.values, "o", ms=2.4, color=CB, alpha=0.85)
    ax.set_xlabel("in-degree $k_{in}$"); ax.set_ylabel("papers"); ax.grid(alpha=0.2)
    plt.close(fig)   # (the in-degree plot is now panel b of fig_degrees.pdf)
    fits = rd(AN, "ns_degree_fits.csv").set_index("distribution")
    flow = rd(AN, "task3_flow_by_year.csv").groupby("institution")[["given", "received"]].sum()
    nf = sc["nit_flow_all"]
    cl, DD = {}, {}
    for line in open(os.path.join(ROOT, "dashboard", "index.html"), encoding="utf-8"):
        if line.startswith("const D = "):
            DD = json.loads(line[len("const D = "):].rstrip().rstrip(";"))
            cl = {r["cluster"]: r["ratio"] for r in DD["net"]["cluster_flow"]}
            break
    cg = DD["coauthor_graph"]
    import networkx as nx
    Gc = nx.Graph(); Gc.add_edges_from((e_[0], e_[1]) for e_ in cg["edges"])
    lcc = max(nx.connected_components(Gc), key=len)
    pos = nx.spring_layout(Gc.subgraph(lcc), seed=42, k=1.6 / np.sqrt(len(lcc)), iterations=300)
    cg = {"nodes": [v for v in cg["nodes"] if v["id"] in lcc], "edges": [e_ for e_ in cg["edges"] if e_[0] in lcc and e_[1] in lcc]}
    pal = ["#2a78d6", "#eb6834", "#2e9e6b", "#c0392b", "#8e44ad", "#d4a017", "#16a3b8", "#7f8c8d", "#e84393", "#5d6d7e"]
    fig, ax = plt.subplots(figsize=(COLW, 2.75))
    for a_, b_, *_ in cg["edges"]:
        if a_ in pos and b_ in pos:
            ax.plot([pos[a_][0], pos[b_][0]], [pos[a_][1], pos[b_][1]], color="#94a3b8", lw=0.25, alpha=0.6, zorder=1)
    xs_ = [pos[v["id"]][0] for v in cg["nodes"]]; ys_ = [pos[v["id"]][1] for v in cg["nodes"]]
    cs_ = [pal[v["comm_rank"]] if v["comm_rank"] < len(pal) else "#cbd5e1" for v in cg["nodes"]]
    ss_ = [3 + 1.6 * v["degree"] for v in cg["nodes"]]
    ec_ = [CT if v["inst"] == T else CS for v in cg["nodes"]]
    ax.scatter(xs_, ys_, s=ss_, c=cs_, edgecolors=ec_, linewidths=0.35, zorder=2)
    ax.set_aspect("equal"); ax.axis("off")
    save_fig(fig, "fig_coauthor.pdf")
    M.update(zeroIndeg=pc((indeg == 0).mean()), maxIndeg=n(indeg.max()), alphaIn=f"{fits.loc['Citation network in-degree', 'alpha']:.1f}",
             selfShare=pc(sc["self_citation_share_shared_author"]), flowRT=n(flow.loc[T, "received"]), flowGT=n(flow.loc[T, "given"]),
             ratioT=f"{flow.loc[T, 'received'] / flow.loc[T, 'given']:.2f}", flowRS=n(flow.loc[S, "received"]), flowGS=n(flow.loc[S, "given"]),
             ratioS=f"{flow.loc[S, 'received'] / flow.loc[S, 'given']:.2f}", cIIT=f"{cl['IIT']:.2f}", cCSIR=f"{cl['CSIR']:.2f}",
             cUni=f"{cl['University / college']:.2f}", citeTS=n(nf["NIT Trichy -> NIT Surathkal"]), citeST=n(nf["NIT Surathkal -> NIT Trichy"]))

    # ---------------------------------------------------------------- Indian connections: co-authorship partners
    ic = rd(DATA, "indian_connections.csv")
    icp = ic[ic.shared_papers > 0]
    prow = []
    for inst in (T, S):
        for _, r in icp[icp.your_inst == inst].nlargest(4, "shared_papers").iterrows():
            ptype = r.partner_cluster.replace("University / college", "University")
            prow.append(f"{nit(inst)} & {tx(short(r.partner_inst, 30))} & {tx(ptype)} &{n(r.shared_papers)} & {n(r.cites_from_partner)} \\\\")
    write_table("tab_partners.tex", "\\begin{tabular}{@{}clp{1.65cm}rr@{}}\n\\toprule\nNIT & Partner institute & Type & Joint & Cites us \\\\\n\\midrule\n" +
                "\n".join(prow) + "\n\\bottomrule\n\\end{tabular}")
    clu = icp.groupby(["your_inst", "partner_cluster"]).shared_papers.sum()
    geo = js(AN, "insights", "geo_summary.json")
    M.update(partT=n((icp.your_inst == T).sum()), partS=n((icp.your_inst == S).sum()),
             indCollT=pc(b0.loc[T, "indian_collab_share"]), indCollS=pc(b0.loc[S, "indian_collab_share"]),
             forCollT=pc(b0.loc[T, "foreign_collab_share"]), forCollS=pc(b0.loc[S, "foreign_collab_share"]),
             uniShare=pc(clu.xs("University / college", level=1).sum() / icp.shared_papers.sum()),
             geoJoint=f"{geo['share_joint_papers_within_300km_pct']:.0f}", geoCite=f"{geo['share_citations_within_300km_pct']:.0f}",
             geoElJ=f"{100 * (1 - 2 ** geo['distance_elasticity_joint_papers']):.0f}", geoElC=f"{100 * (1 - 2 ** geo['distance_elasticity_citations']):.0f}")

    # ---------------------------------------------------------------- authorship network
    am = rd(DATA, "network_metrics", "author_metrics.csv")
    gr = rd(AN, "insights", "growth_by_year.csv").set_index("year")
    last = gr.index.max()
    conn = int(gr.loc[last, "connected_faculty"])
    sw = rd(AN, "ns_small_world.csv")
    na = rd(AN, "ns_assortativity.csv").set_index("attribute")
    nmi = rd(AN, "ns_communities_vs_departments.csv").iloc[0]
    rc = rd(AN, "ns_rich_club.csv")
    ns = js(AN, "questions", "network_summary.json")
    dept = fac.set_index("faculty_id").department
    tb = am.sort_values(["betweenness_centrality", "author"], ascending=[False, True]).head(6)
    write_table("tab_central.tex", "\\begin{tabular}{@{}llcrr@{}}\n\\toprule\nFaculty member & Dept. & NIT & $k$ & $C_B$ \\\\\n\\midrule\n" +
                "\n".join(f"{tx(r.author)} & {tx(dept.get(r.author_id, '--'))} & {nit(r.institution)} & {n(r.degree)} & {r.betweenness_centrality:.3f} \\\\"
                          for _, r in tb.iterrows()) + "\n\\bottomrule\n\\end{tabular}")
    cr = sw.avg_clustering[0] / sw.avg_clustering[1]
    M.update(nConn=n(conn), nNodes=n(nsum["nit_graph_nodes"]), nLCC=n(nsum["largest_component"]), nCross=n(gr.loc[last, "cross_nit_links"]),
             crossPct=pc(gr.loc[last, "cross_nit_links"] / gr.loc[last, "links"], 1), maxDeg=n(am.degree.max()),
             bridgeT=pc(ns[T]["pairs_lost_top10_bridges"]), bridgeS=pc(ns[S]["pairs_lost_top10_bridges"]),
             randT=pc(ns[T]["pairs_lost_10_random"]), randS=pc(ns[S]["pairs_lost_10_random"]),
             nComm=str(nsum["louvain_communities"] - (nsum["nit_graph_nodes"] - conn)), modQ=f"{nsum['modularity']:.2f}",
             commTen=str(nsum["communities_size_ge_10"]), nmi=f"{nmi.NMI:.2f}", nmiRand=f"{nmi.NMI_if_random:.2f}",
             assortBranch=f"{na.loc['branch', 'assortativity']:.2f}", assortRank=f"{na.loc['designation', 'assortativity']:.2f}",
             zRank=f"{na.loc['designation', 'z_score']:.1f}", apl=f"{sw.avg_path_length[0]:.1f}", aplR=f"{sw.avg_path_length[1]:.1f}",
             clust=f"{sw.avg_clustering[0]:.2f}", clustR=f"{sw.avg_clustering[1]:.3f}", clustRatio=f"{cr:.0f}",
             swSigma=f"{cr / (sw.avg_path_length[0] / sw.avg_path_length[1]):.1f}", assortDeg=f"{na.loc['degree', 'assortativity']:.2f}",
             rcRho=f"{rc.rho.max():.1f}", trans=f"{sw.transitivity[0]:.2f}")

    # ---------------------------------------------------------------- densification
    dens = js(AN, "insights", "insights_summary.json")["densification"]["connected_faculty_2016_2026"]
    six = rd(AN, "south", "s_six_nits.csv")
    order = six.sort_values("a_connected_2016-2026", ascending=False)
    fig, ax = plt.subplots(figsize=(COLW, 1.45))
    ax.axhspan(1.08, 1.68, color=INK, alpha=0.08, lw=0)
    ax.axhline(1.0, color=GREY, lw=0.8)
    nm = [i.replace("NIT ", "").replace("Andhra Pradesh", "Andhra P.").replace("Puducherry", "Puduch.") for i in order.institution]
    ax.bar(nm, order["a_connected_2016-2026"], color=[CT if i == T else CS if i == S else GREY for i in order.institution], width=0.6)
    ax.text(len(nm) - 0.55, 1.70, "real growing networks: 1.08–1.68", ha="right", va="bottom", fontsize=6.5, color="#475569")
    ax.set_ylim(0, 1.98); ax.set_ylabel("densification exponent $a$")
    plt.close(fig)   # (now panel a of fig_six.pdf)
    gd = rd(AN, "prof", "g_average_degree_by_year.csv")
    gd = gd[(gd.view == "Both NITs") & ~gd.partial_year].set_index("year")
    gdn = rd(AN, "prof", "g_densification_by_nit.csv")
    gdn = gdn[(gdn.years == "2016-2026") & (gdn.nodes_counted == "connected_faculty")].set_index("view").exponent_a
    peak = gr.loc[gr.index < last, "effective_diameter_90pct"].idxmax()
    M.update(aExp=f"{dens['exponent_a']:.2f}", aRsq=f"{dens['r_squared']:.3f}", degA=f"{gd.loc[2016, 'avg_degree_connected_faculty']:.2f}",
             degB=f"{gd.loc[2025, 'avg_degree_connected_faculty']:.2f}", yrDegMin=f"{gd.year_avg_degree_connected.min():.1f}",
             yrDegMax=f"{gd.year_avg_degree_connected.max():.1f}", diamPeak=f"{gr.loc[peak, 'effective_diameter_90pct']:.0f}", diamYear=str(peak),
             diamNow=f"{gr.loc[last, 'effective_diameter_90pct']:.0f}", aplPeak=f"{gr.loc[peak, 'avg_path_largest_component']:.1f}",
             aSixMin=f"{six['a_connected_2016-2026'].min():.2f}", aSixMax=f"{six['a_connected_2016-2026'].max():.2f}",
             aTrOwn=f"{gdn[T]:.2f}", aSuOwn=f"{gdn[S]:.2f}")

    # ---------------------------------------------------------------- link prediction
    lp = rd(AN, "prof", "p_link_prediction.csv")
    fx = lp[lp.model.str.startswith("fixed")].set_index("target_year")
    up = lp[lp.model.str.startswith("updated")].set_index("target_year")
    mt = rd(AN, "prof", "p_fixed_correct_matches.csv")
    ys = list(fx.index)
    rows = [("Real new faculty pairs (reachable in 2022)", [f"{n(fx.loc[y, 'all_new_pairs'])} ({n(fx.loc[y, 'reachable_new_pairs'])})" for y in ys]),
            ("\\textbf{Fixed model}: AUC", [f"\\textbf{{{fx.loc[y, 'auc']:.2f}}}" for y in ys]),
            ("\\quad correct pairs in top 100", [n(fx.loc[y, "correct_in_top_100"]) for y in ys]),
            ("\\quad correct pairs in top 1\\% ($\\approx$1{,}570)", [f"\\textbf{{{n(fx.loc[y, 'correct_in_top_1pct'])}}} ({fx.loc[y, 'lift_top_1pct']:.0f}$\\times$)" for y in ys]),
            ("Updated model: correct in top 1\\%", [n(up.loc[y, "correct_in_top_1pct"]) for y in ys])]
    write_table("tab_linkpred.tex", "\\begin{tabular}{@{}lrrr@{}}\n\\toprule\n & " + " & ".join(map(str, ys)) + " \\\\\n\\midrule\n" +
                "\n".join(f"{a} & " + " & ".join(b) + " \\\\" for a, b in rows) + "\n\\bottomrule\n\\end{tabular}")
    M.update(lpAUC=", ".join(f"{fx.loc[y, 'auc']:.2f}" for y in ys), lpTop=", ".join(n(fx.loc[y, "correct_in_top_1pct"]) for y in ys),
             lpLiftMin=f"{fx.lift_top_1pct.min():.0f}", lpLiftMax=f"{fx.lift_top_1pct.max():.0f}", lpMatches=str(len(mt)),
             lpOut=f"{fx.loc[ys[-1], 'out_of_reach_pct']:.0f}", lpBase=f"{fx.base_rate_pct.mean():.2f}")

    # ---------------------------------------------------------------- six South Indian NITs
    sx = six.set_index("institution")
    write_table("tab_six.tex", "\\begin{tabular}{@{}lrrrrrrr@{}}\n\\toprule\nNIT & Founded & Faculty & Asst.\\ Prof. & Hired 21--25 & Papers/fac.\\ 2024 & Self-cit. & $a$ \\\\\n\\midrule\n" +
                "\n".join(f"{tx(i.replace('NIT ', ''))} & {int(r.founded)} & {n(r.nirf_faculty_current)} & {r.assistant_pct:.0f}\\% & {r.hired_2021_2025_pct:.0f}\\% & "
                          f"{r.papers_2024_per_faculty:.1f} & {r.self_citation_share_pct:.0f}\\% & \\textbf{{{r['a_connected_2016-2026']:.2f}}} \\\\" for i, r in sx.iterrows()) +
                "\n\\bottomrule\n\\end{tabular}")
    ft = js(AN, "south", "south_summary.json")["founding_test"]["hired_2021_2025_pct vs a_connected_2016-2026"]
    M.update(rhoSix=f"{ft['spearman_rho']:.2f}", pSix=f"{ft['p_exact']:.3f}", selfMin=f"{sx.self_citation_share_pct.min():.0f}",
             selfMax=f"{sx.self_citation_share_pct.max():.0f}")

    # ---------------------------------------------------------------- spreading and synchronisation
    sp = rd(AN, "dynamics", "spread_simulations.csv")
    sp = sp[sp.seeds == "random 5"].pivot(index="beta", columns="network", values="mean_reach_pct")
    sy = rd(AN, "dynamics", "sync_summary.csv").set_index("network")
    sys.path.insert(0, HERE)
    import dynamics as dy           # noqa: E402
    import threshold_note as tn     # noqa: E402
    _, facd, pairs_ = dy.load()
    lam = {}
    for inst in (T, S):
        Gx = dy.graph(pairs_, facd, inst)
        lam[inst] = tn.numbers(Gx.subgraph([u for u in Gx if Gx.degree(u) > 0]))
    M.update(lamOneT=f"{lam[T]['lam']:.3f}", lamOneS=f"{lam[S]['lam']:.3f}", lamNBT=f"{lam[T]['lnb']:.3f}", lamNBS=f"{lam[S]['lnb']:.3f}",
             bcT=f"{1 / lam[T]['lnb']:.3f}", bcS=f"{1 / lam[S]['lnb']:.3f}",
             reachT=" / ".join(f"{sp.loc[b, T]:.1f}" for b in (0.1, 0.2, 0.3)), reachS=" / ".join(f"{sp.loc[b, S]:.1f}" for b in (0.1, 0.2, 0.3)),
             KcT=f"{sy.loc[T, 'Kc_theory']:.3f}", KcS=f"{sy.loc[S, 'Kc_theory']:.3f}", eigR=f"{sy.loc['Both NITs', 'eigenratio']:.0f}",
             eigRw=f"{sy.loc['Both NITs', 'rewired_eigenratio']:.0f}")

    # ---------------------------------------------------------------- other Phase II questions
    allp = rd(DATA, "all_papers.csv")
    with_fac = set(allp[allp.has_faculty_author].openalex_id)
    stu = allp[~allp.openalex_id.isin(with_fac)].drop_duplicates("openalex_id")
    smed = allp.groupby(["institution", "has_faculty_author"]).fwci.median()
    cp = rd(AN, "phase2", "citers_private_vs_public.csv").set_index("measure")
    aa2 = {r["group"]: r for r in js(AN, "papers", "a_summary.json")["table"]}
    q15 = rd(AN, "questions", "q15_foreign_effect.csv").iloc[0]
    q16 = rd(AN, "questions", "q16_partner_types.csv").set_index("partner_type")
    eb = {b_["authors"]: b_ for b_ in js(AN, "papers", "e_summary.json")["bands_faculty_both"]}
    mn = js(AN, "questions", "manipulation_summary.json")
    h10 = [r for r in mn["distribution"] if r["cites_at_least"] == 10][0]
    M.update(stuN=n(len(stu)), stuAll=n(allp.openalex_id.nunique()), stuPct=pc(len(stu) / (allp.openalex_id.nunique() - len(stu))),
             stuMedT=f"{smed[(T, False)]:.2f}", facMedT=f"{smed[(T, True)]:.2f}", stuMedS=f"{smed[(S, False)]:.2f}", facMedS=f"{smed[(S, True)]:.2f}",
             privPer=f"{cp.loc['citations_per_1000_of_their_papers', 'private_median']:.0f}", pubPer=f"{cp.loc['citations_per_1000_of_their_papers', 'public_median']:.0f}",
             privP=f"{cp.loc['citations_per_1000_of_their_papers', 'mann_whitney_p']:.2f}",
             privNear=f"{aa2['from top private citers']['within_3_steps_pct']:.0f}", pubNear=f"{aa2['from top public citers']['within_3_steps_pct']:.0f}",
             forEff=f"{q15.adjusted_effect_pct:+.0f}", forUni=f"{q16.loc['Foreign university', 'effect_pct']:+.0f}", iitEff=f"{q16.loc['IIT', 'effect_pct']:+.0f}",
             teamA=f"{eb['1']['mean_fwci']:.2f}", teamB=f"{eb['10-19']['mean_fwci']:.2f}", teamBig=str(eb["20-49"]["papers"] + (eb["50+"]["papers"] or 0)),
             manipShare=pc(h10["share_of_links"], 1), manipRho=f"{mn['ranking']['without self-citations']['spearman']:.3f}",
             manipN=n(mn["indian_citation_links"]))

    # ---------------------------------------------------------------- findings table (real-world comparisons)
    FD = js(AN, "findings.json")["findings"]
    pick = ["A small world", "Well-connected faculty", "No clean power law", "The network densifies", "Distances shrink", "Rich get richer",
            "New collaborations can be predicted", "Ideas spread more easily", "Synchrony starts", "Most citations between our own", "Every South Indian NIT"]
    rows = []
    for p in pick:
        xx = next(y for y in FD if y["title"].startswith(p))
        real = xx["real_world"] if xx["real_world"] != "–" else xx["caveat"]
        rows.append(f"\\textbf{{{tx(xx['title'])}}} & {tx(xx['numbers'])} & {tx(xx['meaning'])} & {tx(real)} \\\\")
    write_table("tab_findings.tex", "\\begin{tabular}{@{}p{2.5cm}p{4.4cm}p{4.5cm}p{5.4cm}@{}}\n\\toprule\nFinding & Our numbers & What it means & "
                "Compared with real networks or theory \\\\\n\\midrule\n" + "\n\\addlinespace[1.5pt]\n".join(rows) + "\n\\bottomrule\n\\end{tabular}")
    M.update(nFindings=str(len(FD)), nPicked=str(len(pick)))

    # ================================================================ more figures (10-page version)
    # journal quartiles
    q = jr[jr.quartile.isin(["Q1", "Q2", "Q3", "Q4"])].groupby(["institution", "quartile"]).size().unstack(1)
    q = q.div(q.sum(1), axis=0)
    fig, ax = plt.subplots(figsize=(COLW, 0.85))
    qc = {"Q1": "#1e3a8a", "Q2": "#3b82f6", "Q3": "#93c5fd", "Q4": "#dbeafe"}
    for k_, inst in enumerate([S, T]):
        left = 0
        for qq in ["Q1", "Q2", "Q3", "Q4"]:
            v = q.loc[inst, qq]
            ax.barh(k_, v, left=left, color=qc[qq], edgecolor="white", height=0.62)
            if v > 0.06:
                ax.text(left + v / 2, k_, f"{qq} {100 * v:.0f}%", ha="center", va="center", fontsize=6.5, color="white" if qq in ("Q1", "Q2") else INK)
            left += v
    ax.set_yticks([0, 1], ["Surathkal", "Trichy"]); ax.set_xlim(0, 1); ax.set_xticks([]); ax.spines["bottom"].set_visible(False)
    save_fig(fig, "fig_quartiles.pdf")

    # AI share by year
    fig, ax = plt.subplots(figsize=(COLW, 1.3))
    for k_, lab, c in (("computing departments", "computing departments", CB), ("all papers", "all papers", INK), ("other departments", "other departments", "#16a34a")):
        s_ = ai[(ai.computing == k_) & (ai.year < 2026)].set_index("year").ai_share_pct
        ax.plot(s_.index, s_.values, "-o", ms=2.5, lw=1.4, color=c, label=lab)
    ax.set_ylabel("AI papers (%)"); ax.legend(ncol=3, loc="upper left", fontsize=6.3); ax.set_ylim(0, None); ax.grid(alpha=0.25)
    ax.set_ylim(0, ai[ai.computing == "computing departments"].ai_share_pct.max() * 1.3)
    save_fig(fig, "fig_ai.pdf")

    # department level: forest plot of the FWCI difference T - S
    bf = bb.sort_values("difference_T_minus_S")
    fdb_ = fd[fd.family.str.startswith("branch FWCI")].set_index("test")
    fig, ax = plt.subplots(figsize=(COLW, 1.8))
    for k_, (b_, r) in enumerate(bf.iterrows()):
        sig = b_ in fdb_.index and bool(fdb_.loc[b_, "significant_after_fdr"])
        c = (CS if r.difference_T_minus_S < 0 else CT) if sig else GREY
        ax.plot([r.ci_low, r.ci_high], [k_, k_], color=c, lw=1.6)
        ax.plot(r.difference_T_minus_S, k_, "o", color=c, ms=4)
    ax.axvline(0, color=INK, lw=0.8)
    ax.set_yticks(range(len(bf)), bf.index); ax.set_xlabel("mean FWCI, Trichy minus Surathkal (95% bootstrap CI)")
    ax.text(0.02, 0.98, "Surathkal higher", transform=ax.transAxes, va="top", fontsize=6.5, color=CS)
    ax.text(0.98, 0.02, "Trichy higher", transform=ax.transAxes, ha="right", fontsize=6.5, color=CT)
    save_fig(fig, "fig_branches.pdf")

    # degree distributions: co-authorship degree (CCDF) and citation in-degree
    fig, axs = plt.subplots(1, 2, figsize=(COLW, 1.4))
    for inst, c in ((T, CT), (S, CS)):
        d_ = np.sort(am[(am.institution == inst) & (am.degree > 0)].degree.values)
        ks_ = np.unique(d_)
        axs[0].loglog(ks_, [(d_ >= k_).mean() for k_ in ks_], "o-", ms=2.2, lw=0.8, color=c, label=inst.replace("NIT ", ""))
    axs[0].set_xlabel("degree $k$"); axs[0].set_ylabel("$P(K\\geq k)$"); axs[0].legend(fontsize=6); axs[0].set_title("(a) co-authorship", fontsize=7)
    axs[1].loglog(vc.index, vc.values, "o", ms=2.2, color=CB, alpha=0.85)
    axs[1].set_xlabel("in-degree $k_{in}$"); axs[1].set_ylabel("papers"); axs[1].set_title("(b) citations", fontsize=7)
    for a_ in axs:
        a_.grid(alpha=0.2)
    fig.tight_layout(w_pad=0.6)
    save_fig(fig, "fig_degrees.pdf")

    # citation flow with other Indian institutes by year
    fy_ = rd(AN, "task3_flow_by_year.csv")
    fig, ax = plt.subplots(figsize=(COLW, 1.25))
    for inst, c in ((T, CT), (S, CS)):
        s_ = fy_[fy_.institution == inst].set_index("year")
        ax.plot(s_.index, s_.ratio_received_to_given, "-o", ms=2.5, lw=1.4, color=c, label=inst)
    ax.axhline(1, color=INK, lw=0.8, ls="--"); ax.set_ylabel("received / given"); ax.legend(fontsize=6.3, loc="lower right"); ax.grid(alpha=0.25)
    save_fig(fig, "fig_flow.pdf")
    late = fy_[fy_.year >= 2023]
    M.update(flowLateMin=f"{late.ratio_received_to_given.min():.2f}", flowLateMax=f"{late.ratio_received_to_given.max():.2f}")

    # assortativity: k_nn(k) against degree-preserving rewired copies
    kn = rd(AN, "phase2", "assortativity_knn.csv")
    kn = kn[(kn.network == "Faculty co-authorship") & (kn.variant == "all faculty links")]
    fig, ax = plt.subplots(figsize=(COLW * 0.62, 1.3))
    ax.semilogx(kn.k, kn.knn, "o", ms=2.6, color=CB, label="real")
    ax.semilogx(kn.k, kn.knn_null_mean, "-", lw=1, color=GREY, label="rewired")
    ax.set_xlabel("degree $k$"); ax.set_ylabel("$k_{nn}(k)$"); ax.legend(fontsize=6); ax.grid(alpha=0.2)
    save_fig(fig, "fig_knn.pdf")
    adg = rd(AN, "phase2", "assortativity_degree.csv").iloc[0]
    M.update(assortNull=f"{adg.null_mean:.2f}".replace("-", "$-$"), assortZ=f"{adg.z:.1f}")

    # network growth: densification log-log, average degree, distances
    gg = gr[gr.index < last]
    fig, axs = plt.subplots(1, 3, figsize=(6.9, 1.7))
    xN, yE = gg.connected_faculty.values, gg.links.values
    sl, ic_ = np.polyfit(np.log(xN), np.log(yE), 1)
    axs[0].loglog(xN, yE, "o", ms=3, color=CB)
    xx = np.linspace(xN.min(), xN.max(), 50)
    axs[0].loglog(xx, np.exp(ic_) * xx ** sl, "-", lw=1, color=INK, label=f"slope $a$ = {sl:.2f}")
    axs[0].set_xlabel("connected faculty $N$"); axs[0].set_ylabel("links $E$"); axs[0].legend(fontsize=6.3); axs[0].set_title("(a) densification", fontsize=7)
    axs[1].plot(gd.index, gd.avg_degree_connected_faculty, "-o", ms=2.5, color=CB, label="up to each year")
    axs[1].plot(gd.index, gd.year_avg_degree_connected, "-o", ms=2.5, color="#16a34a", label="within one year")
    axs[1].set_ylabel("co-authors per faculty"); axs[1].legend(fontsize=6.3); axs[1].set_title("(b) average degree", fontsize=7); axs[1].set_ylim(0, None)
    axs[2].plot(gg.index, gg.effective_diameter_90pct, "-o", ms=2.5, color=CS, label="effective diameter")
    axs[2].plot(gg.index, gg.avg_path_largest_component, "-o", ms=2.5, color=CT, label="average path")
    axs[2].set_ylabel("steps"); axs[2].legend(fontsize=6.3); axs[2].set_title("(c) distances shrink", fontsize=7)
    for a_ in axs:
        a_.grid(alpha=0.25)
    fig.tight_layout(w_pad=1.0)
    save_fig(fig, "fig_growth.pdf")

    # six NITs: exponent with the real-network band, and hiring against the exponent
    fig, axs = plt.subplots(1, 2, figsize=(COLW, 1.55), gridspec_kw={"width_ratios": [1.15, 1]})
    axs[0].axhspan(1.08, 1.68, color=INK, alpha=0.08, lw=0); axs[0].axhline(1.0, color=GREY, lw=0.8)
    nm2 = [i.replace("NIT ", "").replace("Andhra Pradesh", "AP").replace("Puducherry", "Pud.").replace("Surathkal", "Sur.").replace("Warangal", "War.").replace("Calicut", "Cal.").replace("Trichy", "Tri.") for i in order.institution]
    axs[0].bar(nm2, order["a_connected_2016-2026"], color=[CT if i == T else CS if i == S else GREY for i in order.institution], width=0.62)
    axs[0].set_ylim(0, 1.95); axs[0].set_ylabel("exponent $a$"); axs[0].tick_params(axis="x", labelsize=6); axs[0].set_title("(a) shaded: real networks", fontsize=7)
    axs[1].scatter(six.hired_2021_2025_pct, six["a_connected_2016-2026"], s=14, color=[CT if i == T else CS if i == S else GREY for i in six.institution])
    for _, r in six.iterrows():
        axs[1].annotate(r.institution.replace("NIT ", "").replace("Andhra Pradesh", "AP").replace("Puducherry", "Pud."), (r.hired_2021_2025_pct, r["a_connected_2016-2026"]),
                        fontsize=5.6, xytext=(2, 2), textcoords="offset points")
    axs[1].set_xlabel("hired 2021–25 (%)"); axs[1].set_title("(b) recent hiring", fontsize=7); axs[1].grid(alpha=0.25)
    fig.tight_layout(w_pad=0.5)
    save_fig(fig, "fig_six.pdf")

    # rich get richer (attachment kernel) and team size
    kk = rd(AN, "prof", "k_kernel.csv")
    kk = kk[(kk.view == "Both NITs") & (kk.k_mean > 0)]
    tb_ = rd(AN, "papers", "e_team_size_bands.csv")
    tb_ = tb_[(tb_.scope == "faculty papers") & (tb_.view == "Both") & (tb_.papers >= 20)]
    fig, axs = plt.subplots(1, 2, figsize=(COLW, 1.4))
    axs[0].loglog(kk.k_mean, kk.mean_new_next_year, "o", ms=3, color=CB)
    sk, ik = np.polyfit(np.log(kk.k_mean), np.log(kk.mean_new_next_year), 1)
    xx = np.linspace(kk.k_mean.min(), kk.k_mean.max(), 30)
    axs[0].loglog(xx, np.exp(ik) * xx ** sk, "-", lw=1, color=INK)
    axs[0].set_xlabel("co-authors now $k$"); axs[0].set_ylabel("new next year"); axs[0].set_title("(a) attachment kernel", fontsize=7)
    xs_ = np.arange(len(tb_))
    axs[1].bar(xs_, tb_.mean_fwci, color=CB, width=0.6)
    axs[1].errorbar(xs_, tb_.mean_fwci, yerr=[tb_.mean_fwci - tb_.mean_fwci_ci_low, tb_.mean_fwci_ci_high - tb_.mean_fwci], fmt="none", ecolor=INK, lw=0.8, capsize=2)
    axs[1].set_xticks(xs_, tb_.authors, fontsize=6.3); axs[1].set_xlabel("authors"); axs[1].set_ylabel("mean FWCI"); axs[1].set_title("(b) team size", fontsize=7)
    for a_ in axs:
        a_.grid(alpha=0.2)
    fig.tight_layout(w_pad=0.6)
    save_fig(fig, "fig_kernel_team.pdf")
    ksm = {r["view"]: r for r in js(AN, "prof", "k_summary.json")["fits"]}
    rich = js(AN, "questions", "richer_summary.json")
    M.update(kerA=f"{ksm['Both NITs']['kernel_exponent']:.2f}", kerT=f"{ksm[T]['kernel_exponent']:.2f}", kerS=f"{ksm[S]['kernel_exponent']:.2f}",
             kerOne=f"{ksm['Both NITs']['mean_new_k1']:.2f}", kerNine=f"{ksm['Both NITs']['mean_new_k9plus']:.2f}", richA=f"{rich['alpha']:.2f}")

    # link prediction: correct matches in the top 1 % against a random list of the same size
    fig, ax = plt.subplots(figsize=(COLW, 1.3))
    xs_ = np.arange(len(ys))
    rnd = [fx.loc[y, "top_1pct_size"] * fx.loc[y, "base_rate_pct"] / 100 for y in ys]
    ax.bar(xs_ - 0.27, [fx.loc[y, "correct_in_top_1pct"] for y in ys], 0.27, color=CB, label="fixed model (2016–2022)")
    ax.bar(xs_, [up.loc[y, "correct_in_top_1pct"] for y in ys], 0.27, color="#93c5fd", label="re-trained every year")
    ax.bar(xs_ + 0.27, rnd, 0.27, color=GREY, label="random list")
    ax.set_xticks(xs_, ys); ax.set_ylabel("correct pairs in top 1%"); ax.legend(fontsize=6, loc="upper right"); ax.grid(axis="y", alpha=0.25)
    ax.set_ylim(0, max(up.correct_in_top_1pct.max(), fx.correct_in_top_1pct.max()) * 1.45)
    save_fig(fig, "fig_linkpred.pdf")

    # dynamics: SIR reach against beta, Kuramoto order parameter against K
    spa = rd(AN, "dynamics", "spread_simulations.csv")
    cu = rd(AN, "dynamics", "sync_curves.csv")
    fig, axs = plt.subplots(1, 3, figsize=(6.9, 1.75))
    for a_, inst in zip(axs[:2], (T, S)):
        for seeds, c, lab in (("random 5", GREY, "5 random"), ("top hubs (degree)", CB, "5 hubs")):
            s_ = spa[(spa.network == inst) & (spa.seeds == seeds)]
            a_.plot(s_.beta, s_.mean_reach_pct, "-o", ms=2.5, color=c, label=lab)
        a_.axvline(lam[inst]["b_nb"], color=CS, lw=1, label=r"$1/\lambda_{NB}$")
        a_.axvline(lam[inst]["b_lam"], color=CS, lw=1, ls=":", label=r"$1/\lambda_1$")
        a_.set_xlabel(r"transmission $\beta$"); a_.set_ylabel("faculty reached (%)"); a_.set_title(f"({'a' if inst == T else 'b'}) SIR, {inst}", fontsize=7)
        a_.legend(fontsize=5.8); a_.grid(alpha=0.25)
    for inst, c in ((T, CT), (S, CS)):
        for gname, ls in (("real", "-"), ("rewired", "--")):
            s_ = cu[(cu.network == inst) & (cu.graph == gname)]
            if len(s_):
                axs[2].plot(s_.K, s_.r_mean, ls, lw=1.2, color=c, label=f"{inst.replace('NIT ', '')}, {gname}")
        axs[2].axvline(sy.loc[inst, "Kc_theory"], color=c, lw=0.8, ls=":")
    axs[2].set_xlabel("coupling $K$"); axs[2].set_ylabel("order parameter $r$"); axs[2].set_title("(c) Kuramoto (dotted: $K_c$)", fontsize=7)
    axs[2].legend(fontsize=5.8); axs[2].grid(alpha=0.25)
    fig.tight_layout(w_pad=0.8)
    save_fig(fig, "fig_dynamics.pdf")
    M.update(bmfT=f"{lam[T]['b_hmf']:.3f}", bmfS=f"{lam[S]['b_hmf']:.3f}", bLamT=f"{lam[T]['b_lam']:.3f}", bLamS=f"{lam[S]['b_lam']:.3f}", kOneT=f"{lam[T]['k1']:.2f}", kTwoT=f"{lam[T]['k2']:.2f}",
             kOneS=f"{lam[S]['k1']:.2f}", kTwoS=f"{lam[S]['k2']:.2f}")

    # geography: joint papers vs citations by distance band
    gb = rd(AN, "insights", "geo_distance_bands.csv").groupby("band", sort=False)[["shared_papers", "citations_exchanged"]].sum()
    gb = gb.div(gb.sum(0), axis=1) * 100
    fig, ax = plt.subplots(figsize=(COLW, 1.3))
    xs_ = np.arange(len(gb))
    ax.bar(xs_ - 0.2, gb.shared_papers, 0.4, color=CB, label="joint papers")
    ax.bar(xs_ + 0.2, gb.citations_exchanged, 0.4, color=GREY, label="citations exchanged")
    ax.set_xticks(xs_, gb.index, fontsize=6.3); ax.set_ylabel("share (%)"); ax.legend(fontsize=6.3); ax.grid(axis="y", alpha=0.25)
    save_fig(fig, "fig_geo.pdf")
    gm = rd(AN, "insights", "geo_gravity_model.csv")
    gj = gm[(gm.outcome == "joint papers") & (gm.term == "log distance (km)")].iloc[0]
    gc_ = gm[(gm.outcome == "citations exchanged") & (gm.term == "log distance (km)")].iloc[0]
    M.update(gravJ=f"{-gj.coef:.2f}", gravC=f"{-gc_.coef:.2f}")

    # collaboration dynamics (dynamics.py): renewal of pairs and joint papers per pair
    DY_ = os.path.join(AN, "dynamics")
    ren = rd(DY_, "ties_renewal_by_experience.csv")
    stj = js(DY_, "superties_summary.json")
    fig, axs = plt.subplots(1, 2, figsize=(COLW, 1.35))
    axs[0].bar(ren.years_together.astype(str), ren.renewed_within_2_pct, color=CB, width=0.6)
    axs[0].set_xlabel("years active together"); axs[0].set_ylabel("renew within 2 y (%)"); axs[0].set_ylim(0, 100); axs[0].set_title("(a) renewal", fontsize=7)
    dist = stj["distribution_joint_papers_per_pair"]
    axs[1].bar(list(dist.keys()), list(dist.values()), color=GREY, width=0.65)
    axs[1].set_xlabel("joint papers per pair"); axs[1].set_ylabel("pairs"); axs[1].set_title("(b) few super-ties", fontsize=7); axs[1].tick_params(axis="x", labelsize=6)
    for a_ in axs:
        a_.grid(axis="y", alpha=0.25)
    fig.tight_layout(w_pad=0.6)
    save_fig(fig, "fig_ties.pdf")
    tis, nws = js(DY_, "ties_summary.json"), js(DY_, "newcomers_summary.json")
    nwi = rd(DY_, "newcomers_by_institute.csv").set_index("institution")
    tri, grp, brk = js(DY_, "triangles_summary.json"), js(DY_, "groups_summary.json"), js(DY_, "brokers_summary.json")
    M.update(superPct=f"{stj['super_tie_pairs_pct']:.0f}", superCut=f"{stj['cutoff_joint_papers']:.0f}", superShare=f"{stj['joint_papers_with_a_super_tie_pct']:.0f}",
             superDept=f"{stj['super_ties_same_department_pct']:.0f}", otherDept=f"{stj['other_pairs_same_department_pct']:.0f}",
             onePaper=f"{stj['one_paper_pairs_pct']:.0f}", renewThree=f"{tis['renewed_within_3_pct']:.0f}",
             stillActive=f"{tis['of_those_active_2023_2025_pct']:.0f}", renewOne=f"{ren.renewed_within_2_pct.iloc[0]:.0f}", renewFive=f"{ren.renewed_within_2_pct.iloc[-1]:.0f}",
             nNew=str(nws["newcomers"]), newIso=f"{nws['isolated_after_3_years_pct']:.0f}", newIsoT=f"{nwi.loc[T, 'isolated_after_3_years_pct']:.0f}",
             newIsoS=f"{nwi.loc[S, 'isolated_after_3_years_pct']:.0f}", newDept=f"{nws['first_partner_same_department_pct']:.0f}",
             nTri=str(tri["triangles"]), triFilled=f"{tri['filled_share_pct']:.0f}", triTeam=f"{tri['born_as_team_share_of_filled_pct']:.0f}",
             triPapers=f"{tri['papers_with_3plus_faculty_pct']:.1f}", nGroups=str(grp["dynamic_groups"]), groupsFive=str(grp["groups_lasting_5plus_windows"]),
             groupsAll=str(grp["groups_lasting_all_windows"]), groupsOne=f"{grp['one_window_groups_pct']:.0f}",
             brokerOther=f"{brk['brokers_median_other_department_pct']:.0f}", allOther=f"{brk['all_median_other_department_pct']:.0f}",
             brokerTop=str(brk["top20_brokers_also_top20_degree"]))

    # partner countries: FWCI difference with 95% CI (countries with 100+ joint papers)
    qc_ = rd(AN, "questions", "q15_countries.csv")
    qc_ = qc_[qc_.papers >= 100].sort_values("effect_pct")
    fig, ax = plt.subplots(figsize=(COLW, 1.9))
    for k_, (_, r) in enumerate(qc_.iterrows()):
        c = CB if r.p_value < 0.05 else GREY
        ax.plot([r.ci_low_pct, r.ci_high_pct], [k_, k_], color=c, lw=1.5)
        ax.plot(r.effect_pct, k_, "o", color=c, ms=3.5)
    ax.axvline(0, color=INK, lw=0.8)
    ax.set_yticks(range(len(qc_)), [f"{c} ({p})" for c, p in zip(qc_.country, qc_.papers)], fontsize=6.3)
    ax.set_xlabel("FWCI difference with a co-author from the country (%, 95% CI)")
    save_fig(fig, "fig_countries.pdf")

    # faculty level: top 5 of each NIT by the composite research score (insights.py ranking)
    fr_ = rd(AN, "insights", "faculty_ranking_overall.csv")
    frs = js(AN, "insights", "faculty_ranking_summary.json")
    rows_ = []
    for inst in (T, S):
        rows_.append(f"\\multicolumn{{8}}{{@{{}}l}}{{\\textit{{{inst}}}}} \\\\")
        for _, r in fr_[fr_.institution == inst].nsmallest(5, "overall_rank").iterrows():
            rows_.append(f"{int(r.overall_rank)} & {tx(r.author)} & {tx(r.department)} & {n(r.papers)} & {n(r.citations)} & {int(r.h_index)} & {r.mean_fwci:.2f} & {r.overall_score:.1f} \\\\")
    write_table("tab_faculty.tex", "\\begin{tabular}{@{}rllrrrrr@{}}\n\\toprule\nRank & Faculty member & Dept. & Papers & Cites & $h$ & FWCI & Score \\\\\n\\midrule\n" +
                "\n".join(rows_) + "\n\\bottomrule\n\\end{tabular}")
    M.update(nRanked=str(frs["ranked_faculty"]), rankMin=str(frs["min_papers"]),
             rankRho=f"{frs['robustness_quality_weighted']['spearman_with_equal_weights']:.3f}")

    # research questions (questions.py): inequality, former faculty, author roles, venues, open access, home citations, robustness
    QD = os.path.join(AN, "questions")
    ps_, vs_, iw_, rb_ = (js(QD, f) for f in ("people_summary.json", "venues_summary.json", "inward_summary.json", "robust_summary.json"))
    q19, q18 = ps_["q19"], ps_["q18"]
    roles = {r["rank"]: r for r in ps_["q20"]["roles"]}
    vcl = {c["venue_class"]: c for c in vs_["q22"]["classes"]}
    oas = {s["oa_status"]: s for s in vs_["q24"]["statuses"]}
    rbm = {(r["institution"], r["measure"]): r for r in rb_["main"]}
    M.update(giniC=f"{q19['gini_citations']:.2f}", giniP=f"{q19['gini_papers']:.2f}", topTenC=pc(q19["top10_share_citations"]),
             botHalfC=pc(q19["bottom50_share_citations"]), nFormer=str(q18["former_with_papers"]),
             movedIIT=str(q18["where_former_went"].get("IIT", 0)), movedNIT=str(q18["where_former_went"].get("Another NIT", 0)),
             asstFirst=pc(roles["Assistant Professor"]["first_author"]), asstLast=pc(roles["Assistant Professor"]["last_author"]),
             profLast=pc(roles["Professor"]["last_author"]), confEff=f"{vcl['Conference, not ranked']['effect_vs_q1_journal_pct']:.0f}",
             qThreeEff=f"{vcl['Journal Q3-Q4']['effect_vs_q1_journal_pct']:.0f}", qTwoEff=f"{vcl['Journal Q2']['effect_vs_q1_journal_pct']:.0f}",
             oaShare=pc(vs_["q24"]["open_share"]), oaGold=f"{oas['gold']['effect_vs_closed_pct']:+.0f}", oaGreen=f"{oas['green']['effect_vs_closed_pct']:+.0f}",
             oaDiamond=f"{oas['diamond']['effect_vs_closed_pct']:+.0f}", homeShare=pc(iw_["home_citation_share_both"], 1),
             homeEff=f"{iw_['fwci_effect_10pt_more_home_refs_pct']:+.1f}", nDoubt=str(rb_["doubtful_links"]["single_paper_name_only"]),
             doubtPap=f"{rbm[('Both', 'papers')]['change_pct']:.1f}", doubtCit=f"{rbm[('Both', 'citations')]['change_pct']:.1f}")

    # how recent is the work we build on (Price index) and who cites us (co-authorship distance of citers)
    rec = rd(AN, "insights", "recency_by_institute_year.csv")
    rsm = js(AN, "insights", "recency_summary.json")
    fig, ax = plt.subplots(figsize=(COLW, 1.25))
    for inst, c in ((T, CT), (S, CS)):
        s_ = rec[(rec.institution == inst) & ~rec.partial_year.astype(bool)].set_index("year")
        ax.plot(s_.index, s_.price_index_pct, "-o", ms=2.5, lw=1.4, color=c, label=inst)
    ax.set_ylabel("Price index (%)"); ax.legend(fontsize=6.3); ax.grid(alpha=0.25)
    save_fig(fig, "fig_recency.pdf")
    r_ = rec[~rec.partial_year.astype(bool)]
    M.update(priceAll=f"{rsm['overall_price_index_pct']:.0f}", priceRho=f"{rsm['spearman_price_index_vs_fwci_mean_within_department']:.2f}",
             priceA=f"{r_[r_.year == r_.year.min()].price_index_pct.mean():.0f}", priceB=f"{r_[r_.year == r_.year.max()].price_index_pct.mean():.0f}",
             priceYA=str(int(r_.year.min())), priceYB=str(int(r_.year.max())))
    at_ = {r["group"]: r for r in js(AN, "papers", "a_summary.json")["table"]}
    cats = ["self", "co-author (before)", "co-author (later)", "2 steps", "3 steps", "farther", "no link"]
    ccol = ["#1e3a8a", "#2563eb", "#60a5fa", "#93c5fd", "#bfdbfe", "#cbd5e1", "#f1f5f9"]
    grp = [("from top private citers", "private citers"), ("from top public citers", "public citers"), ("all Indian citations", "all Indian"), ("internal citations", "our own papers")]
    fig, ax = plt.subplots(figsize=(COLW, 1.35))
    for k_, (g_, lab) in enumerate(grp[::-1]):
        left = 0
        for cat, c in zip(cats, ccol):
            v = at_[g_][cat]
            ax.barh(k_, v, left=left, color=c, edgecolor="white", height=0.62, label=cat if k_ == 0 else None)
            left += v
    ax.set_yticks(range(len(grp)), [lab for _, lab in grp[::-1]]); ax.set_xlim(0, 100); ax.set_xlabel("share of citations (%)")
    ax.legend(ncol=4, fontsize=5.6, loc="upper center", bbox_to_anchor=(0.45, -0.42), frameon=False)
    save_fig(fig, "fig_citers.pdf")
    M.update(internalSelf=f"{at_['internal citations']['self']:.0f}")

    M = {k: (v if not re.fullmatch(r"[-+]?\d[\d.]*", v) else v.replace("-", "−")) for k, v in M.items()}   # proper minus signs
    open(os.path.join(REP, "numbers.tex"), "w", encoding="utf-8").write(
        "% Generated by scripts/build_report.py from the analysis outputs. Do not edit by hand; re-run the script.\n" +
        "\n".join(f"\\newcommand{{\\{k}}}{{{v}}}" for k, v in M.items()) + "\n")
    print(f"wrote {len(M)} numbers, figures and tables to report/")


def compile_pdf():
    tect = os.environ.get("TECTONIC") or shutil.which("tectonic")
    if not tect or not os.path.exists(tect):
        print("Tectonic not found: upload report/ to Overleaf (compiler XeLaTeX), or set TECTONIC=path to tectonic.exe")
        return
    r = subprocess.run([tect, "--keep-logs", "--outdir", REP, os.path.join(REP, "main.tex")], capture_output=True, text=True)
    if r.returncode:
        print(r.stdout[-3000:], r.stderr[-3000:])
        raise SystemExit("LaTeX failed")
    out = os.path.join(REP, PDF_NAME)
    shutil.move(os.path.join(REP, "main.pdf"), out)
    log = open(os.path.join(REP, "main.log"), encoding="utf-8", errors="replace").read() if os.path.exists(os.path.join(REP, "main.log")) else ""
    for ext in ("log", "aux", "out"):
        f = os.path.join(REP, "main." + ext)
        if os.path.exists(f):
            os.remove(f)
    data = open(out, "rb").read()
    from pypdf import PdfReader
    pages = len(PdfReader(out).pages)
    over = re.findall(r"Overfull \\hbox \((\d+\.?\d*)pt too wide\)", log)
    print(f"{out}: {pages} pages (limit {MAX_PAGES}); overfull boxes: {len(over)} (max {max(map(float, over)) if over else 0:.1f}pt)")
    if pages > MAX_PAGES:
        print("TOO LONG")


if __name__ == "__main__":
    build()
    if "--no-pdf" not in sys.argv:
        compile_pdf()
