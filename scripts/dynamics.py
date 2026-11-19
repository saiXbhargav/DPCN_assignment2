"""Network dynamics on the faculty co-authorship network (team decisions in brackets).

  python dynamics.py [spread] [triangles] [superties] [newcomers] [brokers] [sync] [ties] [groups]   (no argument = all)

  spread     How far can an idea spread through co-authorship? Epidemic threshold 1/lambda_1 and how concentrated
             the leading eigenvector is (IPR), against degree-preserving rewired networks; SIR simulations from
             5 seeds (top hubs, top brokers, random) per NIT. [SIR + threshold]
  triangles  Higher-order structure: is each faculty triangle a single three-person paper (a team), or was it built
             from separate pairwise papers? And were team triangles born as a team or sealed later?
  superties  How much joint output comes from a few durable pairs? [super-tie = top 10% of pairs by joint papers]
  newcomers  How do new faculty join the network: how fast, with whom, and how many are still isolated after
             3 years? [newcomer = first listed on the faculty pages in 2017 or later]
  brokers    Burt's structural holes: who bridges otherwise separate groups (low constraint, high effective size),
             and are they the same people as the hubs?
  sync       Kuramoto synchronisation: how easily each NIT's network can fall into a common rhythm. Laplacian
             eigenratio, theoretical K_c = 2/(pi g(0) lambda_1), simulated order parameter r(K) against connected
             degree-preserving rewired copies, and which faculty lock first. [omega ~ N(0,1); unweighted, largest group]
  ties       Do collaborations last? Renewal of faculty pairs, the renewal rate by years already together, gaps
             between active years, burstiness (Goh-Barabasi B against a shuffled null), and what predicts renewal.
             Yearly resolution (OpenAlex gives publication years only).
  groups     Research groups over time: Louvain communities in 3-year sliding windows, matched by Jaccard >= 0.3;
             births, deaths, merges, splits, lifetimes, and Palla et al.'s (2007) stability test. [3-year windows]

Uses data/authorship_network.csv (faculty-faculty links: same_nit and nit_nit; papers with more than 50 authors are
already excluded there), data/faculty.csv and data/group12_data.csv. Outputs: data/analysis/dynamics/.
"""
import collections
import itertools
import json
import os
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
OUT = os.path.join(DATA, "analysis", "dynamics")
NITS = ["NIT Trichy", "NIT Surathkal"]
SEED = 42
PARTIAL_YEAR = 2026


def save(df, name):
    df.to_csv(os.path.join(OUT, name), index=False)


def dump(obj, name):
    with open(os.path.join(OUT, name), "w") as f:
        json.dump(obj, f, indent=2, default=float)


def load():
    au = pd.read_csv(os.path.join(DATA, "authorship_network.csv"), low_memory=False)
    fe = au[au.edge_category.isin(["same_nit", "nit_nit"])][["author_a_id", "author_b_id", "paper_id", "year"]]
    fac = pd.read_csv(os.path.join(DATA, "faculty.csv")).drop_duplicates("faculty_id").set_index("faculty_id")
    pairs = (fe.groupby(["author_a_id", "author_b_id"])
               .agg(joint_papers=("paper_id", "nunique"), first_year=("year", "min"), last_year=("year", "max"))
               .reset_index())
    return fe, fac, pairs


def graph(pairs, fac, nit=None):
    """Unweighted faculty graph; nodes = faculty with papers (of one NIT, or both)."""
    nodes = fac.index[(fac.papers > 0) & ((fac.institution == nit) if nit else True)]
    G = nx.Graph()
    G.add_nodes_from(nodes)
    for a, b, w in zip(pairs.author_a_id, pairs.author_b_id, pairs.joint_papers):
        if a in G and b in G:
            G.add_edge(a, b, weight=int(w))
    return G


def rewire(G, seed):
    H = nx.Graph(G)
    m = H.number_of_edges()
    nx.double_edge_swap(H, nswap=10 * m, max_tries=200 * m, seed=int(seed))
    return H


# ================================================================ spread
BETAS = [0.05, 0.1, 0.2, 0.3, 0.5]
N_SEEDS, N_RUNS, N_NULL = 5, 500, 20


def leading(G):
    A = nx.to_numpy_array(G, nodelist=list(G), weight=None)   # unweighted: links, not joint-paper counts
    w, v = np.linalg.eigh(A)
    x = np.abs(v[:, -1])
    x = x / np.linalg.norm(x)
    return float(w[-1]), float(np.sum(x ** 4)), dict(zip(G, x))


def sir(adj, seeds, beta, rng):
    """Independent-cascade SIR: each newly infected node gets one chance to pass the idea to each neighbour."""
    infected, frontier = set(seeds), list(seeds)
    while frontier:
        nxt = []
        for u in frontier:
            for v in adj[u]:
                if v not in infected and rng.random() < beta:
                    infected.add(v)
                    nxt.append(v)
        frontier = nxt
    return len(infected)


def spread_part():
    fe, fac, pairs = load()
    rng = np.random.default_rng(SEED)
    rows, sims = [], []
    for nit in NITS + [None]:
        name = nit or "Both NITs"
        G = graph(pairs, fac, nit)
        lam, ipr, ev = leading(G)
        null = [leading(rewire(G, s))[:2] for s in range(N_NULL)]
        n = G.number_of_nodes()
        top_ev = sorted(ev, key=ev.get, reverse=True)[:5]
        rows.append({"network": name, "faculty": n, "links": G.number_of_edges(),
                     "mean_degree": 2 * G.number_of_edges() / n, "lambda_1": lam, "threshold_1_over_lambda": 1 / lam,
                     "rewired_lambda_1": np.mean([x[0] for x in null]), "ipr": ipr,
                     "rewired_ipr": np.mean([x[1] for x in null]), "ipr_if_fully_spread": 1 / n,
                     "top_eigenvector_faculty": "; ".join(fac.author.get(f, f) for f in top_ev)})
        adj = {u: list(G[u]) for u in G}
        deg = dict(G.degree())
        btw = nx.betweenness_centrality(G)
        seed_sets = {"top hubs (degree)": sorted(G, key=lambda u: (-deg[u], u))[:N_SEEDS],
                     "top brokers (betweenness)": sorted(G, key=lambda u: (-btw[u], u))[:N_SEEDS]}
        nodes = list(G)
        for beta in BETAS:
            for label, seeds in seed_sets.items():
                reach = [sir(adj, seeds, beta, rng) for _ in range(N_RUNS)]
                sims.append({"network": name, "beta": beta, "seeds": label, "mean_reach_pct": 100 * np.mean(reach) / n,
                             "p90_reach_pct": 100 * np.percentile(reach, 90) / n,
                             "seed_names": "; ".join(fac.author.get(f, f) for f in seeds)})
            reach = [sir(adj, list(rng.choice(nodes, N_SEEDS, replace=False)), beta, rng) for _ in range(N_RUNS)]
            sims.append({"network": name, "beta": beta, "seeds": "random 5", "mean_reach_pct": 100 * np.mean(reach) / n,
                         "p90_reach_pct": 100 * np.percentile(reach, 90) / n, "seed_names": ""})
    th, sm = pd.DataFrame(rows), pd.DataFrame(sims)
    save(th.round(4), "spread_threshold.csv")
    save(sm.round(3), "spread_simulations.csv")

    fig, ax = plt.subplots(1, 3, figsize=(15, 4.3), sharey=True)
    for a, name in zip(ax, NITS + ["Both NITs"]):
        for label, col in [("top hubs (degree)", "C3"), ("top brokers (betweenness)", "C2"), ("random 5", "C7")]:
            d = sm[(sm.network == name) & (sm.seeds == label)]
            a.plot(d.beta, d.mean_reach_pct, "o-", color=col, label=label)
        t = th[th.network == name].iloc[0]
        a.axvline(t.threshold_1_over_lambda, color="k", ls=":", lw=1)
        a.text(t.threshold_1_over_lambda, 2, f" 1/λ₁ = {t.threshold_1_over_lambda:.2f}", fontsize=8)
        a.set_title(f"{name} ({t.faculty} faculty)"); a.set_xlabel("β (chance a co-author passes the idea on)")
        a.grid(alpha=0.3)
    ax[0].set_ylabel("faculty reached (%)"); ax[0].legend(fontsize=8)
    fig.suptitle("SIR spreading from 5 seeds on the faculty co-authorship network (mean of 500 runs)")
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "spread.png"), dpi=150); plt.close(fig)
    print(th.round(3).to_string(index=False))
    print(sm[sm.beta.isin([0.1, 0.2, 0.3])].drop(columns="seed_names").round(1).to_string(index=False))


# ================================================================ triangles
def triangles_part():
    fe, fac, pairs = load()
    papers_of = fe.groupby(["author_a_id", "author_b_id"]).paper_id.apply(set).to_dict()
    year_of = fe.drop_duplicates("paper_id").set_index("paper_id").year.to_dict()
    pp = lambda a, b: papers_of.get((a, b) if a < b else (b, a), set())
    G = graph(pairs, fac)
    dept, inst = fac.department.to_dict(), fac.institution.to_dict()
    rows = []
    for a, b, c in (t for t in (tuple(sorted(x)) for x in nx.enumerate_all_cliques(G) if len(x) == 3)):
        ab, bc, ac = pp(a, b), pp(b, c), pp(a, c)
        team = ab & bc & ac                              # papers with all three faculty on them
        first_pair_year = min(min(year_of[p] for p in s) for s in (ab, bc, ac))
        if not team:
            kind = "pairwise only (never a three-person paper)"
        else:
            first_team = min(year_of[p] for p in team)
            kind = "born as a team" if first_team <= first_pair_year else "built pair by pair, sealed later"
        n_dept = len({dept.get(x) for x in (a, b, c)})
        rows.append({"a": a, "b": b, "c": c, "kind": kind, "team_papers": len(team),
                     "departments": n_dept, "mix": "same department" if n_dept == 1 else "cross-department",
                     "institutes": len({inst.get(x) for x in (a, b, c)}),
                     "names": "; ".join(fac.author.get(x, x) for x in (a, b, c))})
    t = pd.DataFrame(rows)
    assert len(t) == sum(nx.triangles(G).values()) // 3, "triangle count mismatch"
    save(t, "triangles_all.csv")
    by_mix = (t.groupby(["mix", "kind"]).size().unstack(fill_value=0))
    by_mix["triangles"] = by_mix.sum(axis=1)
    save(by_mix.reset_index(), "triangles_by_mix.csv")
    # how many faculty papers are 'team' papers (3+ faculty)?
    per_paper = pd.concat([fe[["paper_id", "author_a_id"]].rename(columns={"author_a_id": "f"}),
                           fe[["paper_id", "author_b_id"]].rename(columns={"author_b_id": "f"})]).drop_duplicates()
    size = per_paper.groupby("paper_id").size()
    summary = {"triangles": len(t), "kind_counts": t.kind.value_counts().to_dict(),
               "filled_share_pct": 100 * (t.kind != "pairwise only (never a three-person paper)").mean(),
               "born_as_team_share_of_filled_pct": 100 * (t.kind == "born as a team").sum()
               / max((t.kind != "pairwise only (never a three-person paper)").sum(), 1),
               "faculty_joint_papers": int(len(size)), "papers_with_3plus_faculty": int((size >= 3).sum()),
               "papers_with_3plus_faculty_pct": 100 * (size >= 3).mean(),
               "global_clustering": nx.transitivity(G)}
    dump(summary, "triangles_summary.json")
    print(json.dumps(summary, indent=2, default=float)); print(by_mix.to_string())


# ================================================================ superties
def superties_part():
    fe, fac, pairs = load()
    g = pd.read_csv(os.path.join(DATA, "group12_data.csv"), usecols=["openalex_id", "fwci"], low_memory=False) \
        .drop_duplicates("openalex_id").set_index("openalex_id").fwci
    cut = np.percentile(pairs.joint_papers, 90)
    pairs = pairs.assign(super_tie=pairs.joint_papers >= cut).sort_values("joint_papers", ascending=False)
    dept, inst = fac.department.to_dict(), fac.institution.to_dict()
    pairs["faculty_a"] = pairs.author_a_id.map(fac.author)
    pairs["faculty_b"] = pairs.author_b_id.map(fac.author)
    pairs["same_department"] = [dept.get(a) == dept.get(b) for a, b in zip(pairs.author_a_id, pairs.author_b_id)]
    pairs["institutes"] = [" & ".join(sorted({inst.get(a), inst.get(b)})) for a, b in zip(pairs.author_a_id, pairs.author_b_id)]
    pairs["years_active"] = pairs.last_year - pairs.first_year + 1
    save(pairs, "superties_pairs.csv")
    st = set(zip(pairs.author_a_id[pairs.super_tie], pairs.author_b_id[pairs.super_tie]))
    fe2 = fe.assign(super_tie=[(a, b) in st for a, b in zip(fe.author_a_id, fe.author_b_id)])
    paper_has_st = fe2.groupby("paper_id").super_tie.any()
    fw = g.reindex(paper_has_st.index)
    a, b = fw[paper_has_st].dropna(), fw[~paper_has_st].dropna()
    dist = pairs.joint_papers.clip(upper=10).value_counts().sort_index()
    summary = {"pairs": len(pairs), "cutoff_joint_papers": float(cut), "super_tie_pairs": int(pairs.super_tie.sum()),
               "super_tie_pairs_pct": 100 * pairs.super_tie.mean(),
               "pair_paper_events_from_super_ties_pct": 100 * pairs.joint_papers[pairs.super_tie].sum() / pairs.joint_papers.sum(),
               "joint_papers_with_a_super_tie_pct": 100 * paper_has_st.mean(), "joint_papers": int(len(paper_has_st)),
               "one_paper_pairs_pct": 100 * (pairs.joint_papers == 1).mean(),
               "super_ties_same_department_pct": 100 * pairs.same_department[pairs.super_tie].mean(),
               "other_pairs_same_department_pct": 100 * pairs.same_department[~pairs.super_tie].mean(),
               "super_tie_median_years_active": float(pairs.years_active[pairs.super_tie].median()),
               "fwci_median_super_tie_papers": float(a.median()), "fwci_median_other_joint_papers": float(b.median()),
               "fwci_mean_super_tie_papers": float(a.mean()), "fwci_mean_other_joint_papers": float(b.mean()),
               "fwci_mann_whitney_p": float(stats.mannwhitneyu(a, b).pvalue),
               "distribution_joint_papers_per_pair": {("10+" if k == 10 else str(k)): int(v) for k, v in dist.items()}}
    dump(summary, "superties_summary.json")
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar([("10+" if k == 10 else str(k)) for k in dist.index], dist.values,
           color=["C7" if k < cut else "C3" for k in dist.index])
    ax.set_xlabel("joint papers per faculty pair"); ax.set_ylabel("faculty pairs")
    ax.set_title(f"Most pairs write once; the top 10% (≥{cut:.0f} papers, red) write {summary['joint_papers_with_a_super_tie_pct']:.0f}% of joint papers")
    ax.grid(alpha=0.3, axis="y")
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "superties.png"), dpi=150); plt.close(fig)
    print(json.dumps(summary, indent=2, default=float))
    print(pairs.head(12)[["faculty_a", "faculty_b", "joint_papers", "first_year", "last_year", "same_department",
                          "institutes"]].to_string(index=False))


# ================================================================ newcomers
NEW_FROM = 2017


def newcomers_part():
    fe, fac, pairs = load()
    own = fe.merge(fac[["institution"]], left_on="author_a_id", right_index=True) \
            .merge(fac[["institution"]].rename(columns={"institution": "inst_b"}), left_on="author_b_id", right_index=True)
    own = own[own.institution == own.inst_b]                     # links inside the same NIT
    first_link = {}
    for a, b, y in zip(own.author_a_id, own.author_b_id, own.year):
        for x, other in ((a, b), (b, a)):
            if x not in first_link or y < first_link[x][0]:
                first_link[x] = (y, [other])
            elif y == first_link[x][0]:
                first_link[x][1].append(other)
    # each faculty member's internal degree at the end of every year (to see whom newcomers attach to)
    deg_at = collections.defaultdict(lambda: collections.Counter())
    for a, b, y in pairs[["author_a_id", "author_b_id", "first_year"]].itertuples(index=False):
        if fac.institution.get(a) == fac.institution.get(b):
            for yy in range(int(y), PARTIAL_YEAR + 1):
                deg_at[yy][a] += 1
                deg_at[yy][b] += 1
    new = fac[(fac.first_seen >= NEW_FROM) & (fac.papers > 0)]
    rows = []
    for f, r in new.iterrows():
        J = int(r.first_seen)
        fl = first_link.get(f)
        y = fl[0] if fl else None
        partners = fl[1] if fl else []
        colleagues = fac.index[(fac.institution == r.institution) & (fac.first_seen <= (y or J)) & (fac.papers > 0)]
        avg_deg = np.mean([deg_at[(y or J) - 1][c] for c in colleagues]) if len(colleagues) else np.nan
        p_deg = np.mean([deg_at[y - 1][p] for p in partners]) if fl else np.nan
        rows.append({"faculty_id": f, "author": r.author, "institution": r.institution, "department": r.department,
                     "first_listed": J, "first_internal_link_year": y,
                     "years_to_first_link": (max(y - J, 0) if y else np.nan),
                     "linked_before_listed": bool(y is not None and y < J),
                     "isolated_after_3_years": (y is None or y > J + 3) if J + 3 <= PARTIAL_YEAR - 1 else np.nan,
                     "first_partner": "; ".join(fac.author.get(p, p) for p in partners),
                     "first_partner_same_department": (np.mean([fac.department.get(p) == r.department for p in partners])
                                                       if partners else np.nan),
                     "first_partner_is_newcomer": (np.mean([fac.first_seen.get(p, 0) >= NEW_FROM for p in partners])
                                                   if partners else np.nan),
                     "first_partner_degree": p_deg, "colleagues_mean_degree": avg_deg})
    nd = pd.DataFrame(rows)
    save(nd.round(3), "newcomers.csv")
    full = nd[nd.isolated_after_3_years.notna()]
    linked = nd[nd.first_internal_link_year.notna()]
    by_inst = nd.groupby("institution").agg(
        newcomers=("faculty_id", "size"), with_internal_link_by_2026_pct=("first_internal_link_year", lambda s: 100 * s.notna().mean()),
        median_years_to_first_link=("years_to_first_link", "median")).reset_index()
    by_inst["isolated_after_3_years_pct"] = by_inst.institution.map(
        full.groupby("institution").isolated_after_3_years.apply(lambda s: 100 * s.astype(bool).mean()))
    save(by_inst.round(2), "newcomers_by_institute.csv")
    summary = {"newcomers": len(nd), "newcomers_with_internal_link_by_2026": int(linked.shape[0]),
               "with_internal_link_pct": 100 * len(linked) / len(nd),
               "linked_before_first_listed_pct": 100 * nd.linked_before_listed.mean(),
               "newcomers_with_3_full_years": len(full),
               "isolated_after_3_years_pct": 100 * full.isolated_after_3_years.astype(bool).mean(),
               "median_years_to_first_link": float(linked.years_to_first_link.median()),
               "first_partner_same_department_pct": 100 * linked.first_partner_same_department.mean(),
               "first_partner_is_newcomer_pct": 100 * linked.first_partner_is_newcomer.mean(),
               "first_partner_degree_vs_colleagues_ratio": float((linked.first_partner_degree / linked.colleagues_mean_degree)
                                                                 .replace([np.inf], np.nan).median()),
               "first_partner_degree_mean": float(linked.first_partner_degree.mean()),
               "colleagues_degree_mean": float(linked.colleagues_mean_degree.mean())}
    dump(summary, "newcomers_summary.json")
    yt = linked.years_to_first_link.clip(upper=6).value_counts().sort_index()
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar([("6+" if k == 6 else str(int(k))) for k in yt.index], yt.values, color="C0")
    ax.set_xlabel("years from first listed to first co-author inside the NIT (0 = same year or earlier)")
    ax.set_ylabel("newcomers"); ax.grid(alpha=0.3, axis="y")
    ax.set_title(f"{len(linked)} of {len(nd)} newcomers (since {NEW_FROM}) have an internal co-author by 2026")
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "newcomers.png"), dpi=150); plt.close(fig)
    print(json.dumps(summary, indent=2, default=float)); print(by_inst.round(1).to_string(index=False))


# ================================================================ brokers
def brokers_part():
    fe, fac, pairs = load()
    G = graph(pairs, fac)
    G.remove_nodes_from([n for n in list(G) if G.degree(n) == 0])
    con = nx.constraint(G)
    eff = nx.effective_size(G)
    btw = nx.betweenness_centrality(G)
    dept = fac.department.to_dict()
    rows = [{"faculty_id": n, "author": fac.author.get(n), "institution": fac.institution.get(n),
             "department": dept.get(n), "degree": G.degree(n), "constraint": con[n], "effective_size": eff[n],
             "efficiency": eff[n] / G.degree(n), "betweenness": btw[n],
             "coauthor_departments": len({dept.get(m) for m in G[n]}),
             "other_department_coauthors_pct": 100 * np.mean([dept.get(m) != dept.get(n) for m in G[n]])}
            for n in G]
    b = pd.DataFrame(rows)
    b["degree_rank"] = b.degree.rank(ascending=False, method="min").astype(int)
    b["broker_rank"] = b.constraint.rank(method="min").astype(int)          # low constraint = strong broker
    b = b.sort_values(["constraint", "degree"], ascending=[True, False])
    save(b.round(4), "brokers.csv")
    elig = b[b.degree >= 3]
    hidden = elig[(elig.broker_rank <= 30) & (elig.degree_rank > 50)]
    summary = {"faculty_with_links": len(b), "spearman_constraint_vs_degree": float(stats.spearmanr(b.constraint, b.degree).statistic),
               "spearman_effective_size_vs_betweenness": float(stats.spearmanr(b.effective_size, b.betweenness).statistic),
               "top20_brokers_also_top20_degree": int(len(set(elig.nsmallest(20, "constraint").faculty_id)
                                                          & set(b.nsmallest(20, "degree_rank").faculty_id))),
               "hidden_brokers": hidden.author.tolist(),
               "brokers_median_other_department_pct": float(elig.nsmallest(20, "constraint").other_department_coauthors_pct.median()),
               "all_median_other_department_pct": float(b.other_department_coauthors_pct.median())}
    dump(summary, "brokers_summary.json")
    fig, ax = plt.subplots(figsize=(7, 4.6))
    for inst, col in [("NIT Trichy", "C0"), ("NIT Surathkal", "C1")]:
        d = b[b.institution == inst]
        ax.scatter(d.degree, d.constraint, s=12, alpha=0.6, color=col, label=inst)
    for _, r in elig.nsmallest(6, "constraint").iterrows():
        ax.annotate(r.author, (r.degree, r.constraint), fontsize=7, xytext=(3, 3), textcoords="offset points")
    ax.set_xscale("log"); ax.set_xlabel("faculty co-authors (degree, log)"); ax.set_ylabel("Burt constraint (low = broker)")
    ax.set_title("Brokers sit at the bottom: many groups, few of them connected to each other"); ax.legend(); ax.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "brokers.png"), dpi=150); plt.close(fig)
    print(json.dumps(summary, indent=2, default=float))
    print(elig.head(15)[["author", "institution", "department", "degree", "degree_rank", "constraint", "effective_size",
                         "coauthor_departments", "other_department_coauthors_pct"]].round(3).to_string(index=False))


# ================================================================ sync (Kuramoto)
K_GRID = [round(k, 2) for k in np.arange(0, 2.01, 0.1)]
N_DRAWS, N_SYNC_NULL = 8, 3          # frequency draws (integrated together), rewired copies
DT, T_TRANS, T_AVG = 0.05, 100.0, 100.0
LOCK_TOL = 0.05                      # |effective frequency - mean frequency| below this = locked to the group


def lcc(G):
    return G.subgraph(max(nx.connected_components(G), key=len)).copy()


def kuramoto(A, omega, K, rng):
    """dθ_i/dt = ω_i + K Σ_j A_ij sin(θ_j − θ_i), Heun steps, one column per frequency draw.
    Returns the time-averaged order parameter r per draw and every node's effective frequency."""
    def f(th):
        s, c = np.sin(th), np.cos(th)
        return omega + K * (c * (A @ s) - s * (A @ c))
    th = rng.uniform(0, 2 * np.pi, omega.shape)
    for _ in range(int(T_TRANS / DT)):
        k1 = f(th); th = th + DT / 2 * (k1 + f(th + DT * k1))
    th0, rs = th.copy(), []
    for _ in range(int(T_AVG / DT)):
        k1 = f(th); th = th + DT / 2 * (k1 + f(th + DT * k1))
        rs.append(np.abs(np.exp(1j * th).mean(axis=0)))
    return np.mean(rs, axis=0), (th - th0) / T_AVG


def sync_part():
    import scipy.sparse as sps
    fe, fac, pairs = load()
    rows, curves, locked = [], [], []
    for nit in NITS + [None]:
        name = nit or "Both NITs"
        G = lcc(graph(pairs, fac, nit))
        nodes = list(G)
        rng = np.random.default_rng(SEED)
        omega = rng.standard_normal((len(nodes), N_DRAWS))           # same frequencies for real and rewired
        nulls = []
        for s in range(N_SYNC_NULL):
            H = nx.Graph(G)
            nx.connected_double_edge_swap(H, nswap=10 * H.number_of_edges(), seed=s)
            nulls.append(H)
        lam1 = leading(G)[0]
        lap = lambda H: np.linalg.eigvalsh(nx.laplacian_matrix(H, nodelist=nodes, weight=None).toarray().astype(float))
        ev, ev_null = lap(G), [lap(H) for H in nulls]
        deg = np.array([G.degree(u) for u in nodes])
        dclass = pd.cut(deg, [0, 1, 3, 9, 1000], labels=["1", "2–3", "4–9", "10+"])
        r_real = {}
        for kind, graphs in (("real", [G]), ("rewired", nulls)):
            for K in K_GRID:
                rs = []
                for H in graphs:
                    A = sps.csr_matrix(nx.to_scipy_sparse_array(H, nodelist=nodes, weight=None, format="csr"))
                    r, eff = kuramoto(A, omega, K, np.random.default_rng(SEED + 1))
                    rs.append(r)
                    if kind == "real":
                        lk = np.abs(eff - omega.mean(axis=0)) < LOCK_TOL
                        for c in ["1", "2–3", "4–9", "10+"]:
                            m = np.asarray(dclass == c)
                            if m.any():
                                locked.append({"network": name, "K": K, "degree_class": c, "faculty": int(m.sum()),
                                               "locked_pct": 100 * lk[m].mean()})
                rs = np.concatenate(rs)
                curves.append({"network": name, "graph": kind, "K": K, "r_mean": rs.mean(), "r_sd": rs.std()})
                if kind == "real":
                    r_real[K] = rs.mean()
        cr = pd.DataFrame([c for c in curves if c["network"] == name])
        k_half = lambda kind: next((r.K for r in cr[cr.graph == kind].itertuples() if r.r_mean >= 0.5), np.nan)
        rows.append({"network": name, "faculty_in_largest_group": len(nodes), "links": G.number_of_edges(),
                     "lambda_1": lam1, "Kc_theory": 2 * np.sqrt(2 * np.pi) / (np.pi * lam1),
                     "lambda_2": ev[1], "eigenratio": ev[-1] / ev[1],
                     "rewired_lambda_2": np.mean([e[1] for e in ev_null]),
                     "rewired_eigenratio": np.mean([e[-1] / e[1] for e in ev_null]),
                     "K_half_real": k_half("real"), "K_half_rewired": k_half("rewired"),
                     "r_at_K1_real": r_real.get(1.0), "r_at_K1_rewired": float(cr[(cr.graph == "rewired") & (cr.K == 1.0)].r_mean.iloc[0])})
        print(rows[-1])
    summ, cur, lck = pd.DataFrame(rows), pd.DataFrame(curves), pd.DataFrame(locked)
    save(summ, "sync_summary.csv"); save(cur, "sync_curves.csv"); save(lck, "sync_locked.csv")
    fig, axs = plt.subplots(1, 2, figsize=(12, 4.2))
    for i, nit in enumerate(NITS):
        for kind, ls in (("real", "-"), ("rewired", "--")):
            d = cur[(cur.network == nit) & (cur.graph == kind)]
            axs[0].plot(d.K, d.r_mean, ls, color=f"C{i}", label=f"{nit} ({kind})")
        axs[0].axvline(summ.set_index("network").Kc_theory[nit], color=f"C{i}", lw=0.8, alpha=0.6)
    axs[0].set_xlabel("coupling K"); axs[0].set_ylabel("order parameter r"); axs[0].legend(fontsize=8); axs[0].grid(alpha=0.3)
    axs[0].set_title("Kuramoto: synchrony rises with coupling (thin lines: theory K_c)")
    kref = 1.0
    d = lck[(lck.network == "Both NITs") & (lck.K == kref)]
    axs[1].bar(d.degree_class, d.locked_pct, color="C2")
    axs[1].set_xlabel("faculty co-authors (degree)"); axs[1].set_ylabel("% locked to the group rhythm")
    axs[1].set_title(f"Both NITs, K = {kref}: the core locks first"); axs[1].grid(alpha=0.3, axis="y")
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "sync.png"), dpi=150); plt.close(fig)
    print(summ.round(3).to_string(index=False))
    print(lck[lck.K.isin([0.5, 1.0, 1.5])].round(1).to_string(index=False))


# ================================================================ ties (do collaborations last?)
LAST_FULL = 2025
N_BURST_NULL = 200


def burstiness(times):
    tau = np.diff(np.sort(times))
    mu, sd = tau.mean(), tau.std()
    return (sd - mu) / (sd + mu) if sd + mu > 0 else np.nan


def ties_part():
    fe, fac, pairs = load()
    g = pd.read_csv(os.path.join(DATA, "group12_data.csv"), usecols=["openalex_id", "fwci", "n_authors"], low_memory=False) \
        .drop_duplicates("openalex_id").set_index("openalex_id")
    dept, inst = fac.department.to_dict(), fac.institution.to_dict()
    rng = np.random.default_rng(SEED)
    rows, events, gaps = [], [], []
    for (a, b), grp in fe.groupby(["author_a_id", "author_b_id"]):
        papers = grp.drop_duplicates("paper_id")
        yrs = sorted(papers.year.unique())
        first = yrs[0]
        fp = g.reindex(papers.paper_id[papers.year == first])
        r = {"author_a_id": a, "author_b_id": b, "faculty_a": fac.author.get(a), "faculty_b": fac.author.get(b),
             "joint_papers": len(papers), "first_year": first, "last_year": yrs[-1], "active_years": len(yrs),
             "same_department": dept.get(a) == dept.get(b), "same_nit": inst.get(a) == inst.get(b),
             "first_year_fwci": fp.fwci.mean(), "first_year_team_size": fp.n_authors.median()}
        for h in (1, 2, 3):
            r[f"renewed_within_{h}"] = any(first < y <= first + h for y in yrs) if first + h <= LAST_FULL else np.nan
        r["renewed_by_2026"] = len(yrs) > 1
        for j, y in enumerate(yrs):                      # renewal hazard after j+1 active years together
            if y + 2 <= LAST_FULL:
                events.append({"years_together": j + 1, "renewed_within_2": j + 1 < len(yrs) and yrs[j + 1] <= y + 2})
        gaps += list(np.diff(yrs))
        if len(papers) >= 5:                             # burstiness on paper times (same-year papers: gap 0)
            t = papers.year.values.astype(float)
            r["burstiness"] = burstiness(t)
            inner = np.arange(first, yrs[-1] + 1)
            null = [burstiness(np.r_[first, yrs[-1], rng.choice(inner, len(t) - 2)]) for _ in range(N_BURST_NULL)]
            r["burstiness_null"] = np.nanmean(null)
            r["busiest_year_share"] = papers.year.value_counts().max() / len(papers)
            r["active_share_of_span"] = len(yrs) / (yrs[-1] - first + 1)
        rows.append(r)
    P = pd.DataFrame(rows).sort_values("joint_papers", ascending=False)
    save(P, "ties_pairs.csv")
    E = pd.DataFrame(events)
    E["years_together"] = E.years_together.clip(upper=5)
    hz = E.groupby("years_together").renewed_within_2.agg(["mean", "size"]).reset_index()
    hz = hz.rename(columns={"mean": "renewed_within_2_pct", "size": "cases"}).assign(renewed_within_2_pct=lambda d: 100 * d.renewed_within_2_pct)
    hz["years_together"] = hz.years_together.map(lambda k: "5+" if k == 5 else str(k))
    save(hz, "ties_renewal_by_experience.csv")
    gp = pd.Series(gaps).clip(upper=6).value_counts().sort_index()
    gdf = pd.DataFrame({"gap_years": ["6+" if k == 6 else str(k) for k in gp.index], "gaps": gp.values})
    save(gdf, "ties_gaps.csv")
    old = P[P.first_year <= LAST_FULL - 3].copy()        # pairs with 3 full years of follow-up
    old["fwci_class"] = np.where(old.first_year_fwci >= 1, "first papers FWCI ≥ 1", "first papers FWCI < 1")
    old.loc[old.first_year_fwci.isna(), "fwci_class"] = np.nan
    old["team_class"] = pd.cut(old.first_year_team_size, [0, 3, 6, 1000], labels=["first papers ≤3 authors", "4–6 authors", "7+ authors"])
    by = []
    for col, lab in (("same_department", {True: "same department", False: "different departments"}),
                     ("same_nit", {True: "same NIT", False: "Trichy–Surathkal"}),
                     ("fwci_class", None), ("team_class", None)):
        for k, d in old.groupby(col, observed=True):
            by.append({"factor": col, "group": lab[k] if lab else str(k), "pairs": len(d),
                       "renewed_within_3_pct": 100 * d.renewed_within_3.mean()})
    by = pd.DataFrame(by)
    save(by, "ties_renewal_by_group.csv")
    import statsmodels.formula.api as smf
    m = old.dropna(subset=["first_year_fwci", "first_year_team_size"]).assign(
        y=lambda d: d.renewed_within_3.astype(float), sd=lambda d: d.same_department.astype(int), sn=lambda d: d.same_nit.astype(int),
        hi=lambda d: (d.first_year_fwci >= 1).astype(int), lt=lambda d: np.log(d.first_year_team_size))
    fit = smf.logit("y ~ sd + sn + hi + lt + C(first_year)", data=m).fit(disp=0)
    odds = {k: {"odds_ratio": float(np.exp(fit.params[k])), "p": float(fit.pvalues[k])} for k in ["sd", "sn", "hi", "lt"]}
    early = set(zip(P.author_a_id[P.first_year <= 2018], P.author_b_id[P.first_year <= 2018]))
    late = fe[(fe.year >= 2023) & (fe.year <= LAST_FULL)]
    still = len(early & set(zip(late.author_a_id, late.author_b_id)))
    B = P.dropna(subset=["burstiness"])
    summary = {"pairs": len(P), "pairs_with_3_years_followup": len(old),
               "renewed_within_1_pct": 100 * P.renewed_within_1.dropna().mean(),
               "renewed_within_3_pct": 100 * old.renewed_within_3.mean(),
               "renewed_by_2026_pct_of_followup_pairs": 100 * old.renewed_by_2026.mean(),
               "gaps": int(len(gaps)), "consecutive_year_gaps_pct": 100 * np.mean(np.array(gaps) == 1),
               "comeback_gaps_3plus_pct": 100 * np.mean(np.array(gaps) >= 3),
               "pairs_started_2016_2018": len(early), "of_those_active_2023_2025_pct": 100 * still / len(early),
               "pairs_5plus_papers": len(B), "burstiness_median": float(B.burstiness.median()),
               "burstiness_null_median": float(B.burstiness_null.median()),
               "bursty_pairs_pct": 100 * float((B.burstiness > B.burstiness_null).mean()),
               "burstiness_wilcoxon_p": float(stats.wilcoxon(B.burstiness, B.burstiness_null).pvalue),
               "busiest_year_share_median": float(B.busiest_year_share.median()),
               "active_share_of_span_median": float(B.active_share_of_span.median()),
               "logit_renewed_within_3": {"same_department": odds["sd"], "same_nit": odds["sn"],
                                          "first_papers_fwci_ge_1": odds["hi"], "log_team_size": odds["lt"],
                                          "pairs": int(fit.nobs), "controls": "first-year fixed effects"}}
    dump(summary, "ties_summary.json")
    fig, axs = plt.subplots(1, 2, figsize=(12, 4))
    axs[0].bar(hz.years_together, hz.renewed_within_2_pct, color="C0")
    axs[0].set_xlabel("years the pair has already written together"); axs[0].set_ylabel("% writing again within 2 years")
    axs[0].set_title("The longer a pair lasts, the more likely it continues"); axs[0].grid(alpha=0.3, axis="y")
    axs[1].bar(gdf.gap_years, gdf.gaps, color="C1")
    axs[1].set_xlabel("years between a pair's active years"); axs[1].set_ylabel("gaps")
    axs[1].set_title("Gaps between joint papers"); axs[1].grid(alpha=0.3, axis="y")
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "ties.png"), dpi=150); plt.close(fig)
    print(json.dumps(summary, indent=2, default=float)); print(hz.round(1).to_string(index=False)); print(by.round(1).to_string(index=False))


# ================================================================ groups (research groups over time)
WINDOWS = [(y, y + 2) for y in range(2016, 2025)]      # 3-year sliding windows; the last one includes 2026 (partial)
MIN_GROUP, JACCARD = 3, 0.3


def groups_part():
    fe, fac, pairs = load()
    unit = (fac.institution.str.replace("NIT ", "") + " " + fac.department.fillna("?")).to_dict()
    snaps, graphs = [], []
    for a, b in WINDOWS:
        w = fe[(fe.year >= a) & (fe.year <= b)].groupby(["author_a_id", "author_b_id"]).paper_id.nunique()
        G = nx.Graph()
        G.add_weighted_edges_from((x, y, int(n)) for (x, y), n in w.items())
        comms = [frozenset(c) for c in nx.community.louvain_communities(G, weight="weight", seed=SEED) if len(c) >= MIN_GROUP]
        snaps.append(sorted(comms, key=len, reverse=True)); graphs.append(G)
    jac = lambda c, d: len(c & d) / len(c | d)
    # match consecutive windows; a group inherits the identity of its best predecessor if it is that one's best successor
    dyn, next_id, links, ev_rows = [], 0, [], []
    ids = [[None] * len(s) for s in snaps]
    for i in range(len(snaps[0])):
        ids[0][i] = next_id; next_id += 1
    for t in range(1, len(snaps)):
        prev, cur = snaps[t - 1], snaps[t]
        J = np.array([[jac(c, d) for d in cur] for c in prev])
        M = J >= JACCARD
        for i, c in enumerate(prev):
            for j, d in enumerate(cur):
                if len(c & d) >= 2:
                    links.append({"from_window": t - 1, "from_group": i, "to_window": t, "to_group": j,
                                  "shared_faculty": len(c & d), "jaccard": J[i, j]})
        for j in range(len(cur)):
            preds = np.where(M[:, j])[0]
            if len(preds):
                p = preds[np.argmax(J[preds, j])]
                if np.argmax(np.where(M[p], J[p], -1)) == j:
                    ids[t][j] = ids[t - 1][p]
            if ids[t][j] is None:
                ids[t][j] = next_id; next_id += 1
        a, b = WINDOWS[t]
        ev_rows.append({"window": f"{a}–{b}", "groups": len(cur),
                        "births": int((M.sum(axis=0) == 0).sum()), "deaths": int((M.sum(axis=1) == 0).sum()),
                        "merges": int((M.sum(axis=0) >= 2).sum()), "splits": int((M.sum(axis=1) >= 2).sum()),
                        "continued": int(((M.sum(axis=0) == 1) & (M.T.astype(int) @ (M.sum(axis=1) == 1).astype(int) == 1)).sum())})
    # per-window description
    gl = []
    for t, (comms, G) in enumerate(zip(snaps, graphs)):
        a, b = WINDOWS[t]
        for j, c in enumerate(comms):
            units = pd.Series([unit.get(f, "?") for f in sorted(c)]).value_counts().sort_index().sort_values(ascending=False, kind="stable")
            insts = {fac.institution.get(f) for f in c}
            top = sorted(c, key=lambda f: (-G.degree(f), f))[:3]
            gl.append({"window": f"{a}–{b}", "window_index": t, "group_index": j, "dynamic_group": ids[t][j], "size": len(c),
                       "main_unit": units.index[0], "main_unit_share_pct": 100 * units.iloc[0] / len(c),
                       "departments": len(units), "cross_nit": len(insts) > 1,
                       "key_members": "; ".join(fac.author.get(f, f) for f in top)})
    GL = pd.DataFrame(gl)
    save(GL, "groups_by_window.csv"); save(pd.DataFrame(links), "groups_links.csv")
    per = GL.groupby("window", sort=False).agg(groups=("size", "size"), faculty_in_groups=("size", "sum"),
                                               largest=("size", "max"), mean_size=("size", "mean"),
                                               main_unit_share_pct=("main_unit_share_pct", "mean"),
                                               multi_department_groups_pct=("departments", lambda s: 100 * (s > 1).mean()),
                                               cross_nit_groups=("cross_nit", "sum")).reset_index()
    EV = pd.DataFrame(ev_rows)
    per = per.merge(EV.drop(columns="groups"), on="window", how="left")
    save(per, "groups_per_window.csv")
    # dynamic groups: lifetime, size, stationarity (mean Jaccard between consecutive windows) — Palla et al. (2007)
    life = []
    for gid, d in GL.groupby("dynamic_group"):
        d = d.sort_values("window_index")
        mem = [snaps[t][j] for t, j in zip(d.window_index, d.group_index)]
        zeta = np.mean([jac(x, y) for x, y in zip(mem, mem[1:])]) if len(mem) > 1 else np.nan
        life.append({"dynamic_group": gid, "first_window": d.window.iloc[0], "last_window": d.window.iloc[-1],
                     "lifetime_windows": len(d), "size_first": int(d["size"].iloc[0]), "size_last": int(d["size"].iloc[-1]),
                     "size_mean": d["size"].mean(), "stationarity": zeta, "ever_members": len(frozenset().union(*mem)),
                     "main_unit_first": d.main_unit.iloc[0], "main_unit_last": d.main_unit.iloc[-1],
                     "key_members_first": d.key_members.iloc[0], "key_members_last": d.key_members.iloc[-1],
                     "drifted": d.main_unit.iloc[0] != d.main_unit.iloc[-1],
                     "alive_in_last_window": d.window_index.iloc[-1] == len(WINDOWS) - 1})
    L = pd.DataFrame(life).sort_values(["lifetime_windows", "size_mean"], ascending=False)
    save(L, "groups_lifetimes.csv")
    L2 = L[L.lifetime_windows >= 2].copy()
    med = L2.size_mean.median()
    palla = {}
    for lab, d in (("small", L2[L2.size_mean <= med]), ("large", L2[L2.size_mean > med])):
        rho, p = stats.spearmanr(d.stationarity, d.lifetime_windows)
        palla[lab] = {"groups": len(d), "spearman_stationarity_vs_lifetime": float(rho), "p": float(p),
                      "median_stationarity": float(d.stationarity.median())}
    summary = {"windows": [f"{a}–{b}" for a, b in WINDOWS], "min_group_size": MIN_GROUP, "jaccard_match": JACCARD,
               "dynamic_groups": len(L), "groups_lasting_all_windows": int((L.lifetime_windows == len(WINDOWS)).sum()),
               "groups_lasting_5plus_windows": int((L.lifetime_windows >= 5).sum()),
               "one_window_groups_pct": 100 * float((L.lifetime_windows == 1).mean()),
               "median_lifetime_windows_of_multiwindow_groups": float(L2.lifetime_windows.median()),
               "long_lived_5plus_that_changed_main_department": int(L[L.lifetime_windows >= 5].drifted.sum()),
               "size_split_mean_members": float(med), "palla": palla,
               "first_window": per.iloc[0].to_dict(), "last_window": per.iloc[-1].to_dict()}
    dump(summary, "groups_summary.json")
    fig, axs = plt.subplots(1, 2, figsize=(12, 4))
    x = np.arange(len(EV))
    for k, (col, c) in enumerate([("births", "C2"), ("deaths", "C3"), ("merges", "C0"), ("splits", "C1")]):
        axs[0].bar(x + (k - 1.5) * 0.2, EV[col], 0.2, label=col, color=c)
    axs[0].set_xticks(x, EV.window, rotation=45, fontsize=8); axs[0].legend(fontsize=8); axs[0].grid(alpha=0.3, axis="y")
    axs[0].set_title("Research-group events between consecutive 3-year windows")
    axs[1].plot(per.window, per.main_unit_share_pct, "o-", label="members from the main department (%)")
    axs[1].plot(per.window, per.multi_department_groups_pct, "s-", label="groups with 2+ departments (%)")
    axs[1].tick_params(axis="x", rotation=45, labelsize=8); axs[1].legend(fontsize=8); axs[1].grid(alpha=0.3)
    axs[1].set_title("How mixed the groups are")
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "groups.png"), dpi=150); plt.close(fig)
    print(json.dumps(summary, indent=2, default=float)); print(per.round(1).to_string(index=False))
    print(L.head(12)[["first_window", "last_window", "lifetime_windows", "size_first", "size_last", "stationarity",
                      "main_unit_first", "main_unit_last", "key_members_last"]].round(2).to_string(index=False))


PARTS = {"spread": spread_part, "triangles": triangles_part, "superties": superties_part,
         "newcomers": newcomers_part, "brokers": brokers_part, "sync": sync_part, "ties": ties_part, "groups": groups_part}

if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    for part in sys.argv[1:] or list(PARTS):
        if part not in PARTS:
            sys.exit(__doc__)
        print(f"\n===== {part} =====")
        PARTS[part]()
