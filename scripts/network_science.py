"""Network-science analyses on top of the submitted files -> data/analysis/ns_* and NETWORK_SCIENCE.md

  1. Degree distributions: power-law vs log-normal fits (co-authorship and citation networks)
  2. Is the faculty network special? Small-world and rich-club tests against degree-preserving random graphs,
     assortativity (by branch, institute, rank) and k-cores
  3. Do the Louvain communities follow the departments? (NMI / ARI against branches)
  4. The institute-level citation-flow network: PageRank, reciprocity, who learns from whom
  5. A fair institute comparison: regression of FWCI on institute, branch, year and collaboration, plus
     bootstrap confidence intervals for every branch comparison

Run after analysis.py:  python network_science.py
"""
import collections
import os
import warnings

import matplotlib
import matplotlib.ticker
import networkx as nx
import numpy as np
import pandas as pd
import powerlaw
import statsmodels.formula.api as smf
from sklearn.metrics import adjusted_rand_score, normalized_mutual_info_score

import analysis as an
from analysis import AXIS, BLUE, GRID, INK, INSTS, MUTED, ORANGE, SURFACE, md, style_axes

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

DATA, OUT = an.DATA, an.OUT
RNG = np.random.default_rng(42)
N_NULL = 20      # random graphs per null model
N_BOOT = 2000    # bootstrap resamples
NEUTRAL = "#b9b8b0"  # diverging midpoint gray
warnings.filterwarnings("ignore", category=RuntimeWarning)


def save(fig, name):
    fig.savefig(os.path.join(OUT, name), dpi=160, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)


def faculty_graph():
    am = pd.read_csv(os.path.join(DATA, "network_metrics", "author_metrics.csv"))
    fac = pd.read_csv(os.path.join(DATA, "faculty.csv")).set_index("faculty_id")
    fac[["department", "designation"]] = fac[["department", "designation"]].fillna("")  # e.g. a Director
    au = pd.read_csv(os.path.join(DATA, "authorship_network.csv"), low_memory=False)
    nit = au[au.edge_category.isin(["same_nit", "nit_nit"])]
    G = nx.Graph()
    for r in am.itertuples(index=False):
        G.add_node(r.author_id, institution=r.institution.split(";")[0], community=int(r.community),
                   branch=fac.department.get(r.author_id, ""), designation=fac.designation.get(r.author_id, ""),
                   name=r.author)
    for (a, b), n in nit.groupby(["author_a_id", "author_b_id"]).paper_id.nunique().items():
        G.add_edge(a, b, weight=int(n))
    return G, au


# ---------------------------------------------------------------- 1. degree distributions
def degree_distributions(G, au, report):
    fac_nodes = set(G.nodes)
    partners = collections.defaultdict(set)
    for a, b in zip(au.author_a_id, au.author_b_id):
        if a in fac_nodes:
            partners[a].add(b)
        if b in fac_nodes:
            partners[b].add(a)
    pm = pd.read_csv(os.path.join(DATA, "network_metrics", "citation_paper_metrics.csv"))
    series = {
        "Faculty co-authorship degree\n(distinct NIT faculty co-authors)": [d for _, d in G.degree() if d > 0],
        "All co-authors per faculty member\n(NIT and outside, distinct)": [len(v) for v in partners.values() if v],
        "Citation network in-degree\n(citations from our own papers)": pm.in_degree_internal[pm.in_degree_internal > 0].tolist(),
        "Total citations per paper\n(OpenAlex, all citing papers)": pm.citations_total[pm.citations_total > 0].tolist(),
    }
    rows = []
    fig, axes = plt.subplots(2, 2, figsize=(10, 8), facecolor=SURFACE)
    for ax, (label, x) in zip(axes.flat, series.items()):
        fit = powerlaw.Fit(np.array(x), discrete=True, verbose=False)
        R_ln, p_ln = fit.distribution_compare("power_law", "lognormal", normalized_ratio=True)
        R_ex, p_ex = fit.distribution_compare("power_law", "exponential", normalized_ratio=True)
        R_tp, p_tp = fit.distribution_compare("power_law", "truncated_power_law", normalized_ratio=True)
        if p_ln < 0.1 and R_ln < 0:
            verdict = "log-normal fits better than a power law"
        elif p_ln < 0.1 and R_ln > 0:
            verdict = "power law fits better than log-normal"
        else:
            verdict = "power law and log-normal fit about equally well (heavy-tailed)"
        rows.append({"distribution": label.split("\n")[0], "n": len(x), "mean": np.mean(x), "max": max(x),
                     "xmin": fit.power_law.xmin, "alpha": fit.power_law.alpha, "alpha_se": fit.power_law.sigma,
                     "tail_size": int((np.array(x) >= fit.power_law.xmin).sum()),
                     "R_vs_lognormal": R_ln, "p_vs_lognormal": p_ln, "R_vs_exponential": R_ex, "p_vs_exponential": p_ex,
                     "R_vs_truncated_pl": R_tp, "p_vs_truncated_pl": p_tp, "verdict": verdict})
        style_axes(ax)
        ax.grid(axis="x", color=GRID, linewidth=0.6)
        fit.plot_ccdf(ax=ax, color=INK, linestyle="none", marker="o", markersize=3,
                      label=f"data, k ≥ xmin = {fit.power_law.xmin:.0f}")  # tail only, same scale as the fits
        fit.power_law.plot_ccdf(ax=ax, color=BLUE, linewidth=2, label=f"power law, α = {fit.power_law.alpha:.2f}")
        fit.lognormal.plot_ccdf(ax=ax, color=ORANGE, linewidth=2, linestyle="--", label="log-normal")
        ax.set_title(label, color=INK, fontsize=9.5, loc="left")
        ax.xaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())  # only label the powers of ten
        ax.set_xlabel("k (log scale)", color=MUTED, fontsize=8)
        ax.set_ylabel("P(X ≥ k)", color=MUTED, fontsize=8)
        ax.legend(frameon=False, fontsize=7.5, labelcolor=INK)
    fig.suptitle("Heavy tails: P(X ≥ k) for k ≥ xmin, with the fitted power law and log-normal", color=INK,
                 fontsize=11, x=0.01, ha="left")
    fig.tight_layout()
    save(fig, "ns_degree_distributions.png")
    t = pd.DataFrame(rows)
    t.to_csv(os.path.join(OUT, "ns_degree_fits.csv"), index=False)
    report.append("## 1. Degree distributions: power law or log-normal?\n")
    report.append("Fitted with the `powerlaw` package (Clauset-Shalizi-Newman method: maximum likelihood, xmin chosen "
                  "by the Kolmogorov-Smirnov distance). `R` > 0 favours the power law and `R` < 0 the other "
                  "distribution; `p` < 0.1 means the difference is significant.\n\n![degree distributions]"
                  "(ns_degree_distributions.png)\n\n"
                  + md(t[["distribution", "n", "mean", "max", "xmin", "alpha", "alpha_se", "tail_size",
                          "R_vs_lognormal", "p_vs_lognormal", "R_vs_exponential", "p_vs_exponential", "verdict"]],
                       "{:.3f}") + "\n")
    return t


# ---------------------------------------------------------------- 2. small world, rich club, assortativity, cores
def rewired(G, seed):
    H = G.copy()
    m = H.number_of_edges()
    nx.double_edge_swap(H, nswap=10 * m, max_tries=200 * m, seed=int(seed))
    return H


def lcc(G):
    return G.subgraph(max(nx.connected_components(G), key=len)).copy()


def null_models(G, report):
    L0 = lcc(nx.Graph(G.edges()))  # unweighted largest connected component
    C, L = nx.average_clustering(L0), nx.average_shortest_path_length(L0)
    T = nx.transitivity(L0)
    conf, er = [], []
    for s in range(N_NULL):
        H = lcc(rewired(L0, s))
        conf.append((nx.average_clustering(H), nx.average_shortest_path_length(H), nx.transitivity(H)))
        E = lcc(nx.gnm_random_graph(L0.number_of_nodes(), L0.number_of_edges(), seed=s))
        er.append((nx.average_clustering(E), nx.average_shortest_path_length(E), nx.transitivity(E)))
    conf, er = np.array(conf), np.array(er)
    sigma = (C / conf[:, 0].mean()) / (L / conf[:, 1].mean())
    sw = pd.DataFrame([
        {"graph": "Faculty network (largest component)", "nodes": L0.number_of_nodes(), "edges": L0.number_of_edges(),
         "avg_clustering": C, "transitivity": T, "avg_path_length": L},
        {"graph": f"Same degrees, rewired (mean of {N_NULL})", "nodes": L0.number_of_nodes(), "edges": L0.number_of_edges(),
         "avg_clustering": conf[:, 0].mean(), "transitivity": conf[:, 2].mean(), "avg_path_length": conf[:, 1].mean()},
        {"graph": f"Random (Erdos-Renyi, mean of {N_NULL})", "nodes": L0.number_of_nodes(), "edges": L0.number_of_edges(),
         "avg_clustering": er[:, 0].mean(), "transitivity": er[:, 2].mean(), "avg_path_length": er[:, 1].mean()},
    ])
    sw.to_csv(os.path.join(OUT, "ns_small_world.csv"), index=False)

    # rich club, normalised by degree-preserving random graphs
    rc = nx.rich_club_coefficient(L0, normalized=False)
    rand = collections.defaultdict(list)
    for s in range(N_NULL):
        for k, v in nx.rich_club_coefficient(rewired(L0, 100 + s), normalized=False).items():
            rand[k].append(v)
    rho = pd.DataFrame([{"k": k, "phi": rc[k], "phi_random": np.mean(rand[k]), "rho": rc[k] / np.mean(rand[k]),
                         "nodes_with_degree_gt_k": sum(1 for _, d in L0.degree() if d > k)}
                        for k in sorted(rc) if k in rand and np.mean(rand[k]) > 0])
    rho = rho[rho.nodes_with_degree_gt_k >= 5]
    rho.to_csv(os.path.join(OUT, "ns_rich_club.csv"), index=False)
    fig, ax = plt.subplots(figsize=(6.5, 3.6), facecolor=SURFACE)
    style_axes(ax)
    ax.axhline(1, color=AXIS, linewidth=1)
    ax.plot(rho.k, rho.rho, color=BLUE, linewidth=2, marker="o", markersize=4)
    ax.set_xlabel("degree k", color=INK, fontsize=9)
    ax.set_ylabel("rich-club ratio ρ(k)", color=INK, fontsize=9)
    ax.set_title("Rich club: do well-connected faculty work with each other?\n(ρ > 1: more than in degree-preserving "
                 "random graphs)", color=INK, fontsize=10, loc="left")
    save(fig, "ns_rich_club.png")

    # assortativity, with a shuffled-label null model
    ass = [{"attribute": "degree", "assortativity": nx.degree_assortativity_coefficient(G), "null_mean": np.nan,
            "z_score": np.nan}]
    for attr in ("branch", "institution", "designation"):
        H = G.subgraph([n for n in G if G.nodes[n][attr]]).copy()
        r = nx.attribute_assortativity_coefficient(H, attr)
        order = sorted(H.nodes)  # fixed order, so the shuffles are the same on every run
        labels = [H.nodes[n][attr] for n in order]
        null = []
        for _ in range(200):
            nx.set_node_attributes(H, dict(zip(order, RNG.permutation(labels))), "shuf")
            null.append(nx.attribute_assortativity_coefficient(H, "shuf"))
        ass.append({"attribute": attr, "assortativity": r, "null_mean": np.mean(null),
                    "z_score": (r - np.mean(null)) / np.std(null)})
    ass = pd.DataFrame(ass)
    same_branch = np.mean([G.nodes[a]["branch"] == G.nodes[b]["branch"] for a, b in G.edges()])
    ass = ass.round(6)  # last-digit float noise from summation order otherwise changes the file between runs
    ass.to_csv(os.path.join(OUT, "ns_assortativity.csv"), index=False)

    # k-cores
    core = nx.core_number(nx.Graph(G.edges()))
    kmax = max(core.values())
    inner = [n for n, k in core.items() if k == kmax]
    inner_t = pd.DataFrame([{"faculty": G.nodes[n]["name"], "institution": G.nodes[n]["institution"],
                             "branch": G.nodes[n]["branch"], "degree": G.degree(n)} for n in inner]).sort_values(
        ["institution", "branch", "faculty"])
    core_counts = pd.Series(core).value_counts().sort_index()
    inner_t.to_csv(os.path.join(OUT, "ns_inner_core.csv"), index=False)

    report.append("## 2. Is the faculty network a small world, and who works with whom?\n")
    report.append(f"Null models: {N_NULL} degree-preserving rewirings (double-edge swaps) and {N_NULL} Erdos-Renyi "
                  f"graphs of the same size. Small-world index σ = (C / C_rand) / (L / L_rand) with the rewired graphs "
                  f"= **{sigma:.1f}** (σ > 1 means small world): clustering is "
                  f"{C / conf[:, 0].mean():.1f}× the rewired value while paths are only "
                  f"{L / conf[:, 1].mean():.2f}× as long.\n\n" + md(sw, "{:.3f}") + "\n")
    top = rho.loc[rho.rho.idxmax()]
    report.append(f"**Rich club:** the normalised coefficient peaks at ρ = {top.rho:.2f} for k > {int(top.k)} "
                  f"({int(top.nodes_with_degree_gt_k)} faculty). Values above 1 mean the best-connected faculty "
                  "co-author with each other more than chance predicts.\n\n![rich club](ns_rich_club.png)\n")
    report.append(f"**Assortativity:** {same_branch:.0%} of faculty-faculty links join two people of the same branch. "
                  "The z-score compares each value with 200 random relabellings.\n\n" + md(ass, "{:.3f}") + "\n")
    report.append(f"**k-cores:** the innermost core is the {kmax}-core, with {len(inner)} faculty:\n\n"
                  + md(inner_t) + "\n\nFaculty per core number: "
                  + ", ".join(f"k={k}: {v}" for k, v in core_counts.items()) + "\n")
    return sigma


# ---------------------------------------------------------------- 3. communities vs departments
def communities(G, report):
    nodes = [n for n in G if G.degree(n) > 0 and G.nodes[n]["branch"]]
    comm = [G.nodes[n]["community"] for n in nodes]
    br = [G.nodes[n]["institution"] + " · " + G.nodes[n]["branch"] for n in nodes]
    inst = [G.nodes[n]["institution"] for n in nodes]
    nmi, ari = normalized_mutual_info_score(br, comm), adjusted_rand_score(br, comm)
    null = [normalized_mutual_info_score(RNG.permutation(br), comm) for _ in range(200)]
    res = pd.DataFrame([
        {"comparison": "Louvain communities vs department (institute + branch)", "NMI": nmi, "ARI": ari,
         "NMI_if_random": np.mean(null)},
        {"comparison": "Louvain communities vs institute", "NMI": normalized_mutual_info_score(inst, comm),
         "ARI": adjusted_rand_score(inst, comm), "NMI_if_random": np.nan},
    ])
    res.to_csv(os.path.join(OUT, "ns_communities_vs_departments.csv"), index=False)
    df = pd.DataFrame({"community": comm, "department": br})
    sizes = df.community.value_counts()
    big = sizes[sizes >= 8].index
    comp = []
    for c in big:
        d = df[df.community == c].department.value_counts()
        comp.append({"community": c, "faculty": int(sizes[c]), "main_department": d.index[0],
                     "share_of_main_department": d.iloc[0] / d.sum(), "departments": len(d),
                     "mix": "; ".join(f"{k} ({v})" for k, v in d.head(4).items())})
    comp = pd.DataFrame(comp).sort_values("faculty", ascending=False)
    comp.to_csv(os.path.join(OUT, "ns_community_composition.csv"), index=False)
    mixed = comp[comp.share_of_main_department < 0.6]

    # heatmap: share of each large community coming from each department (sequential, one hue)
    mat = pd.crosstab(df.community, df.department, normalize="index").reindex(index=comp.community).fillna(0)
    mat = mat.loc[:, mat.max() >= 0.05]
    order = sorted(mat.columns, key=lambda c: (list(mat.index).index(mat[c].idxmax()), -mat[c].max()))
    mat, deps = mat[order], order
    from matplotlib.colors import LinearSegmentedColormap
    cmap = LinearSegmentedColormap.from_list("seq_blue", ["#f4f8fd", "#9ec5f4", "#3987e5", "#1c5cab", "#0d366b"])
    fig, ax = plt.subplots(figsize=(0.42 * len(deps) + 3, 0.42 * len(mat) + 2.5), facecolor=SURFACE)
    im = ax.imshow(mat.values, cmap=cmap, vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(range(len(deps)), [d.replace("NIT ", "") for d in deps], rotation=55, ha="right", fontsize=8,
                  color=INK)
    ax.set_yticks(range(len(mat)), [f"community {c} ({sizes[c]})" for c in mat.index], fontsize=8, color=INK)
    for s in ax.spines.values():
        s.set_visible(False)
    cb = fig.colorbar(im, ax=ax, fraction=0.025)
    cb.ax.tick_params(labelsize=8, colors=MUTED)
    cb.set_label("share of the community's faculty", fontsize=8, color=INK)
    ax.set_title("Louvain communities (rows) by department (columns)", color=INK, fontsize=10, loc="left")
    save(fig, "ns_communities_vs_departments.png")

    report.append("## 3. Do the collaboration communities follow the departments?\n")
    report.append(f"NMI = 1 would mean every Louvain community is exactly one department; 0 means no relation. "
                  f"Here **NMI = {nmi:.2f}** (a random assignment would give {np.mean(null):.2f}) and ARI = {ari:.2f}: "
                  "communities are strongly shaped by department, but not identical to them.\n\n"
                  + md(res, "{:.3f}") + "\n\n![communities vs departments](ns_communities_vs_departments.png)\n\n"
                  f"Communities with 8+ faculty ({len(comp)}); **{len(mixed)}** of them draw less than 60% of their "
                  "members from one department. These are the cross-department groups:\n\n"
                  + md(comp, "{:.2f}") + "\n")
    return nmi


# ---------------------------------------------------------------- 4. institute-level citation flow network
def institute_network(report):
    ic = pd.read_csv(os.path.join(DATA, "indian_connections.csv"))
    W = nx.DiGraph()  # edge u -> v with weight = citations from u's papers to v's papers
    for r in ic.itertuples(index=False):
        if r.cites_from_partner:
            W.add_edge(r.partner_inst, r.your_inst, weight=int(r.cites_from_partner))
        if r.cites_to_partner:
            W.add_edge(r.your_inst, r.partner_inst, weight=int(r.cites_to_partner))
    cluster = dict(zip(ic.partner_inst, ic.partner_cluster))
    cluster.update({i: "NIT" for i in INSTS})
    pr = nx.pagerank(W, weight="weight")
    both = sum(min(d["weight"], W[v][u]["weight"]) for u, v, d in W.edges(data=True) if W.has_edge(v, u))
    weighted_reciprocity = both / sum(d["weight"] for _, _, d in W.edges(data=True))
    rows = []
    for r in ic[~ic.partner_inst.isin(INSTS)].itertuples(index=False):
        a, b = r.cites_from_partner, r.cites_to_partner
        if a + b < 50:
            continue
        rows.append({"institution": r.your_inst, "partner": r.partner_inst, "cluster": r.partner_cluster,
                     "they_cite_us": a, "we_cite_them": b, "reciprocity": min(a, b) / max(a, b),
                     "balance": "they mostly cite us" if a > 2 * b else ("we mostly cite them" if b > 2 * a else "balanced"),
                     "pagerank": pr.get(r.partner_inst, 0)})
    t = pd.DataFrame(rows)
    t.to_csv(os.path.join(OUT, "ns_institute_flow.csv"), index=False)
    by_cluster = (t.groupby(["institution", "cluster"])
                  .agg(partners=("partner", "size"), they_cite_us=("they_cite_us", "sum"),
                       we_cite_them=("we_cite_them", "sum")).reset_index())
    by_cluster["received_per_given"] = by_cluster.they_cite_us / by_cluster.we_cite_them
    balance = t.groupby(["institution", "balance"]).size().unstack(fill_value=0)
    top_pr = pd.DataFrame([{"institute": k, "cluster": cluster.get(k, ""), "pagerank": v}
                           for k, v in sorted(pr.items(), key=lambda kv: -kv[1])[:15]])

    # figure: one ego panel per NIT. Partners on a circle, sorted by the direction of the flow, one straight
    # line per partner (width = citations exchanged, colour = direction), so nothing overlaps.
    from matplotlib.colors import LinearSegmentedColormap
    div = LinearSegmentedColormap.from_list("div", [ORANGE, NEUTRAL, BLUE])
    names = {"Vellore Institute of Technology University": "VIT", "Council of Scientific and Industrial Research": "CSIR",
             "Manipal Academy of Higher Education": "Manipal (MAHE)", "Visvesvaraya Technological University": "VTU",
             "SRM Institute of Science and Technology": "SRM IST", "Indian Institute of Science Bangalore": "IISc",
             "Anna University, Chennai": "Anna Univ.", "Amrita Vishwa Vidyapeetham": "Amrita",
             "Academy of Scientific and Innovative Research": "AcSIR", "Banaras Hindu University": "BHU",
             "Vel Tech Rangarajan Dr. Sagunthala R&D Institute of Science and Technology": "Vel Tech",
             "Thapar Institute of Engineering & Technology": "Thapar", "Lovely Professional University": "LPU",
             "Indian Institute of Technology Dhanbad": "IIT (ISM) Dhanbad"}
    short = lambda s: names.get(s, s.replace("Indian Institute of Technology", "IIT")
                                 .replace("National Institute of Technology", "NIT").replace("University", "Univ.")
                                 .replace("Institute of Science and Technology", "IST")[:26])
    fig, axes = plt.subplots(1, 2, figsize=(14, 6.8), facecolor=SURFACE)
    fig.subplots_adjust(left=0.01, right=0.99, top=0.88, bottom=0.14, wspace=0.05)
    for ax, inst in zip(axes, INSTS):
        d = t[t.institution == inst].assign(ex=lambda x: x.they_cite_us + x.we_cite_them).nlargest(25, "ex")
        d = d.assign(lr=np.log2(d.they_cite_us / d.we_cite_them).clip(-3, 3)).sort_values("lr")
        ang = np.linspace(np.pi * 0.95, -np.pi * 0.95, len(d))  # left (orange) to right (blue), round the circle
        ax.set_facecolor(SURFACE)
        ax.set_aspect("equal")
        ax.axis("off")
        exmax = d.ex.max()
        for (_, r), a in zip(d.iterrows(), ang):
            x, y = np.cos(a), np.sin(a)
            c = div((r.lr + 3) / 6)
            ax.plot([0, x * 0.92], [0, y * 0.92], color=c, linewidth=0.8 + 9 * r.ex / exmax, solid_capstyle="round",
                    zorder=1)
            ax.scatter([x], [y], s=40 + 260 * r.ex / exmax, color=c, edgecolors=SURFACE, linewidths=1.5, zorder=2)
            ha = "left" if x > 0.15 else ("right" if x < -0.15 else "center")
            ax.text(x * 1.12, y * 1.12, short(r.partner), fontsize=7.5, color=INK, ha=ha, va="center")
        ax.scatter([0], [0], s=2600, color=INK, zorder=3)
        ax.text(0, 0, inst.replace("NIT ", "NIT\n"), color=SURFACE, fontsize=9, ha="center", va="center",
                fontweight="bold", zorder=4)
        ax.set_xlim(-1.8, 1.8)
        ax.set_ylim(-1.25, 1.25)
        ax.set_title(f"{inst}: 25 largest citation-exchange partners", color=INK, fontsize=10, loc="left")
    sm = plt.cm.ScalarMappable(cmap=div, norm=plt.Normalize(-3, 3))
    cax = fig.add_axes([0.35, 0.07, 0.3, 0.025])
    cb = fig.colorbar(sm, cax=cax, orientation="horizontal")
    cb.set_label("log2(citations they give us / citations we give them):  orange = we cite them more,  "
                 "blue = they cite us more", fontsize=8, color=INK)
    cb.ax.tick_params(labelsize=8, colors=MUTED)
    fig.suptitle("Who learns from whom: line width = citations exchanged, colour = direction of the flow",
                 color=INK, fontsize=11, x=0.01, y=0.97, ha="left")
    fig.savefig(os.path.join(OUT, "ns_institute_flow_network.png"), dpi=160, facecolor=SURFACE)
    plt.close(fig)


    report.append("## 4. The institute-level citation-flow network\n")
    report.append("Nodes are institutes. An arrow A → B weighted w means A's papers cite B's papers w times (with the "
                  "co-authorship rule). This is the part of the Indian citation network that touches our two NITs, "
                  "so the two NITs are the hubs by design; the interesting part is the direction and balance of "
                  f"each partner's exchange. Weighted reciprocity of the whole network = **{weighted_reciprocity:.2f}** "
                  "(1 = every citation is returned in equal measure).\n\n![institute flow network]"
                  "(ns_institute_flow_network.png)\n\nPartners with 50+ citations exchanged, by direction of the flow "
                  "('they mostly cite us' = more than twice as many citations from them as to them):\n\n"
                  + md(balance.reset_index()) + "\n\nBy cluster (`received_per_given` > 1: that cluster draws on our "
                  "work more than we draw on theirs):\n\n" + md(by_cluster, "{:.2f}") + "\n\nWeighted PageRank "
                  "(top 15):\n\n" + md(top_pr, "{:.4f}") + "\n")
    return weighted_reciprocity


# ---------------------------------------------------------------- 5. fair institute comparison
def fair_comparison(report):
    ds, fac, ic = an.load()
    p = ds.assign(department=ds.department.fillna("No branch"))  # e.g. papers by a Director only
    # branch of a paper for one institute: the branch of most of that institute's faculty on it
    br = p.groupby(["institution", "openalex_id"]).department.agg(lambda s: s.mode().iat[0])
    p = an.paper_table(ds).set_index(["institution", "openalex_id"])
    p["branch"] = br
    p = p.reset_index()
    p = p[p.fwci.notna()].copy()
    p["log_fwci"] = np.log1p(p.fwci)
    p["indian_collab"] = (p.coauthor_institutes.fillna("") != "").astype(int)
    p["foreign"] = p.foreign_coauthor.astype(int)
    p["conference"] = (p.type == "conference").astype(int)
    p["log_authors"] = np.log(p.n_authors)
    p["surathkal"] = (p.institution == "NIT Surathkal").astype(int)
    m0 = smf.ols("log_fwci ~ surathkal + C(year)", data=p).fit(cov_type="HC1")
    m1 = smf.ols("log_fwci ~ surathkal + C(year) + C(branch)", data=p).fit(cov_type="HC1")
    m2 = smf.ols("log_fwci ~ surathkal + C(year) + C(branch) + foreign + indian_collab + conference + log_authors",
                 data=p).fit(cov_type="HC1")
    rows = []
    for name, m in (("year only", m0), ("+ branch", m1), ("+ branch, collaboration, venue, team size", m2)):
        b, (lo, hi) = m.params["surathkal"], m.conf_int().loc["surathkal"]
        rows.append({"model": name, "NIT Surathkal effect on log(1+FWCI)": b, "95% CI": f"{lo:.3f} to {hi:.3f}",
                     "p_value": m.pvalues["surathkal"], "approx_%_difference": 100 * (np.exp(b) - 1),
                     "R2": m.rsquared, "papers": int(m.nobs)})
    eff = pd.DataFrame(rows)
    eff.to_csv(os.path.join(OUT, "ns_regression_institute_effect.csv"), index=False)
    other = pd.DataFrame([{"variable": v, "coefficient": m2.params[v], "p_value": m2.pvalues[v],
                           "approx_%_difference": 100 * (np.exp(m2.params[v]) - 1)}
                          for v in ("foreign", "indian_collab", "conference", "log_authors")])
    with open(os.path.join(OUT, "ns_regression_full.txt"), "w") as f:
        # drop the date and time lines statsmodels adds, so reruns give the same file
        lines = m2.summary().as_text().splitlines()
        f.write("\n".join(l for l in lines if not l.startswith(("Date:", "Time:"))) + "\n")

    # bootstrap the NIT Trichy - NIT Surathkal FWCI difference within every shared branch
    rows = []
    for b, g in p.groupby("branch"):
        x = g[g.institution == "NIT Trichy"].fwci.values
        y = g[g.institution == "NIT Surathkal"].fwci.values
        if len(x) < 30 or len(y) < 30:
            continue
        diff = [RNG.choice(x, len(x)).mean() - RNG.choice(y, len(y)).mean() for _ in range(N_BOOT)]
        lo, hi = np.percentile(diff, [2.5, 97.5])
        rows.append({"branch": b, "papers_T": len(x), "papers_S": len(y), "fwci_T": x.mean(), "fwci_S": y.mean(),
                     "difference_T_minus_S": x.mean() - y.mean(), "ci_low": lo, "ci_high": hi,
                     "verdict": "NIT Trichy higher" if lo > 0 else ("NIT Surathkal higher" if hi < 0 else
                                                                   "no clear difference")})
    bt = pd.DataFrame(rows).sort_values("difference_T_minus_S")
    bt.to_csv(os.path.join(OUT, "ns_branch_fwci_bootstrap.csv"), index=False)
    fig, ax = plt.subplots(figsize=(7.5, 0.45 * len(bt) + 1.5), facecolor=SURFACE)
    style_axes(ax)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color=GRID, linewidth=0.6)
    ax.axvline(0, color=AXIS, linewidth=1)
    y = np.arange(len(bt))
    colors = [BLUE if v == "NIT Trichy higher" else ORANGE if v == "NIT Surathkal higher" else MUTED for v in bt.verdict]
    ax.hlines(y, bt.ci_low, bt.ci_high, colors=colors, linewidth=2)
    ax.scatter(bt.difference_T_minus_S, y, color=colors, s=36, zorder=3, edgecolors=SURFACE)
    ax.set_yticks(y, bt.branch, fontsize=9, color=INK)
    ax.set_xlabel("mean FWCI, NIT Trichy minus NIT Surathkal (95% bootstrap interval)", color=INK, fontsize=9)
    ax.set_title("Which NIT is stronger in each branch?\nblue: NIT Trichy higher · orange: NIT Surathkal higher · "
                 "gray: no clear difference", color=INK, fontsize=10, loc="left")
    save(fig, "ns_branch_fwci_bootstrap.png")

    raw = p.groupby("institution").fwci.mean()
    report.append("## 5. A fair comparison of the two institutes\n")
    report.append(f"Raw mean FWCI: NIT Trichy {raw['NIT Trichy']:.2f}, NIT Surathkal {raw['NIT Surathkal']:.2f}. "
                  "But the two NITs publish in different branches, years and collaboration patterns, so the raw gap "
                  "can mislead. We regress log(1 + FWCI) of each paper on an NIT Surathkal indicator, adding controls "
                  "step by step (OLS with robust standard errors, one row per institute and paper):\n\n"
                  + md(eff, "{:.3f}") + "\n\nOther effects in the full model:\n\n" + md(other, "{:.3f}") + "\n")
    report.append("Branch by branch, with a 95% bootstrap interval for the difference in mean FWCI "
                  f"({N_BOOT} resamples; branches with at least 30 papers at each NIT):\n\n"
                  "![branch FWCI bootstrap](ns_branch_fwci_bootstrap.png)\n\n" + md(bt, "{:.3f}") + "\n")
    return eff, bt


def main():
    os.makedirs(OUT, exist_ok=True)
    G, au = faculty_graph()
    report = ["# Team 12: network-science analyses\n",
              f"Faculty co-authorship network: {G.number_of_nodes()} faculty, {G.number_of_edges()} links. "
              "Generated by `scripts/network_science.py`.\n"]
    degree_distributions(G, au, report)
    null_models(G, report)
    communities(G, report)
    institute_network(report)
    fair_comparison(report)
    with open(os.path.join(OUT, "NETWORK_SCIENCE.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(report))
    print("\n".join(report)[:4000])


if __name__ == "__main__":
    main()
