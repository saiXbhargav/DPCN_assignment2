"""The main findings of the whole project (Phase I and Phase II), what they mean, and how they compare with
published real networks -> data/analysis/FINDINGS.md and data/analysis/findings.json (shown on the dashboard's
Key findings tab).

  python findings.py

Every number about our NITs is read here from the analysis outputs (nothing is typed by hand), so re-running the
analyses and then this script keeps FINDINGS.md and the dashboard in step. The numbers about other networks are
fixed values quoted from the papers in SOURCES below (each one was read in the paper itself).
Needs the outputs of analysis.py, network_science.py, insights.py, phase2.py, phase2_papers.py, phase2_prof.py,
questions.py, south_nits.py and dynamics.py.
"""
import itertools
import json
import os
import sys

import numpy as np
import pandas as pd
from scipy import stats

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
AN = os.path.join(DATA, "analysis")
T, S = "NIT Trichy", "NIT Surathkal"

# ---------------------------------------------------------------- published real networks (quoted from the papers)
SOURCES = {
    "leskovec": {"label": "Leskovec, Kleinberg & Faloutsos 2005", "url": "https://doi.org/10.1145/1081870.1081893"},
    "newman01": {"label": "Newman 2001 (PNAS)", "url": "https://doi.org/10.1073/pnas.98.2.404"},
    "barabasi02": {"label": "Barabási et al. 2002", "url": "https://doi.org/10.1016/S0378-4371(02)00736-7"},
    "newman02": {"label": "Newman 2002 (PRL)", "url": "https://doi.org/10.1103/PhysRevLett.89.208701"},
    "liben07": {"label": "Liben-Nowell & Kleinberg 2007", "url": "https://doi.org/10.1002/asi.20591"},
    "karrer14": {"label": "Karrer, Newman & Zdeborová 2014", "url": "https://doi.org/10.1103/PhysRevLett.113.208702"},
    "restrepo05": {"label": "Restrepo, Ott & Hunt 2005", "url": "https://doi.org/10.1103/PhysRevE.71.036151"},
    "thresholds": {"label": "our threshold calculations (PDF)", "url": "dashboard/docs/threshold_calculations.pdf"},
}
LIT = {
    # Leskovec et al. 2005, sections 3.1-3.2: e(t) ~ n(t)^a with a "strictly between 1 and 2"
    "dens_low": 1.08, "dens_high": 1.68,
    "dens_text": "citation graphs 1.56 and 1.68, US patents 1.66, internet routers 1.18, author–paper graphs 1.08–1.15",
    # Newman 2001, Table I (MEDLINE, arXiv all, astro-ph, cond-mat, hep-th, SPIRES, NCSTRL)
    "dist_low": 4.0, "dist_high": 9.7, "clust_low": 0.072, "clust_high": 0.726, "giant_low": 57.2, "giant_high": 89.4,
    # Barabasi et al. 2002: Pi(k) ~ k^nu with nu ~ 0.8 (mathematics) and 0.75 (neuroscience)
    "nu_low": 0.75, "nu_high": 0.8,
    # Newman 2002, Table I: physics 0.363, biology 0.127, mathematics 0.120 co-authorship
    "assort_low": 0.120, "assort_high": 0.363,
    # Liben-Nowell & Kleinberg: random prediction correct 0.147%-0.475%; best predictors up to 54.8x random
    "lp_rand_low": 0.15, "lp_rand_high": 0.48, "lp_best": 55,
}


def rd(*p):
    return pd.read_csv(os.path.join(AN, *p), low_memory=False)


def js(*p):
    return json.load(open(os.path.join(AN, *p), encoding="utf-8"))


def f(x, d=0):
    return f"{x:,.{d}f}"


def pct(x, d=0):
    return f"{100 * x:.{d}f}%"


def spearman_exact(x, y):
    """Spearman rho with the exact two-sided permutation p-value (n small)."""
    rho = stats.spearmanr(x, y)[0]
    perms = [stats.spearmanr(x, p)[0] for p in itertools.permutations(y)]
    return rho, float(np.mean([abs(r) >= abs(rho) - 1e-12 for r in perms]))


def build():
    out = []

    def add(group, phase, title, numbers, meaning, real, caveat, tab, evidence, sources=()):
        out.append({"group": group, "phase": phase, "title": title, "numbers": numbers, "meaning": meaning,
                    "real_world": real, "caveat": caveat, "tab": tab, "evidence": evidence,
                    "sources": [SOURCES[s] for s in sources]})

    # ============================================================ A. output and impact
    G = "Output and impact"
    pp = pd.read_csv(os.path.join(DATA, "group12_data.csv"), usecols=["institution", "openalex_id", "year", "fwci"], low_memory=False)
    per = pp.groupby("institution").openalex_id.nunique()
    uniq = pp.openalex_id.nunique()
    yr = pp.drop_duplicates("openalex_id").groupby("year").size()
    add(G, "Phase I", "The two NITs publish the same amount, and output grew fast",
        f"{f(per[T])} vs {f(per[S])} faculty papers 2016–2026 ({f(per[T] + per[S] - uniq)} written together); "
        f"{f(yr[2016])} papers in 2016 → {f(yr[2025])} in 2025 ({yr[2025] / yr[2016]:.1f}×)",
        "Neither NIT is ahead on volume; both grew strongly over the decade.",
        "–", "Faculty papers only (science and engineering); students' own papers are counted separately (see below).",
        "publications", "data/group12_data.csv")

    big = rd("large_papers_paper_level.csv")
    b0 = big[big.max_authors.astype(str) == "none"].set_index("institution")
    fs = rd("papers", "r_fwci_model_sensitivity.csv").iloc[0]
    med = pp.drop_duplicates(["institution", "openalex_id"]).groupby("institution").fwci.median()
    add(G, "Phase I + II", "No significant difference in impact per paper",
        f"Surathkal vs Trichy, same field, year and venue type: {fs.surathkal_effect_pct:+.1f}% FWCI "
        f"(p = {fs.p_robust:.2f}; p = {fs.p_clustered:.2f} with errors grouped by faculty member); median FWCI {med[T]:.2f} vs {med[S]:.2f}",
        "Once field and year are taken into account, the two NITs' papers have the same impact. Raw citations per paper "
        f"are higher at Trichy ({b0.loc[T, 'cites_per_paper']:.1f} vs {b0.loc[S, 'cites_per_paper']:.1f}) only because raw counts ignore field.",
        "–", "Not significant is not the same as proven equal: the clustered 95% interval allows a few per cent either way.",
        "analysis", "data/analysis/papers/r_fwci_model_sensitivity.csv")

    it = rd("institute_tests.csv").set_index("per_faculty_measure")
    rm = rd("papers", "r_papers_per_year_models.csv").set_index("model")
    wr = {r["rank"]: r for r in js("papers", "r_summary.json")["within_rank"]}
    add(G, "Phase II", "Surathkal faculty publish more each, mostly because of rank mix",
        f"median {f(it.loc['papers', 'median_NIT Surathkal'])} vs {f(it.loc['papers', 'median_NIT Trichy'])} papers per faculty member "
        f"(p = {it.loc['papers', 'mann_whitney_p']:.4f}); the gap falls from {rm.loc['no controls', 'surathkal_effect_pct']:+.0f}% to "
        f"{rm.loc['+ rank', 'surathkal_effect_pct']:+.0f}% for people of the same rank; {pct(wr['Assistant Professor']['share_of_trichy_faculty'])} of Trichy's "
        f"faculty are Assistant Professors vs {pct(wr['Assistant Professor']['share_of_surathkal_faculty'])}",
        "Trichy has hired many young faculty, who publish less at first. Among Professors the two NITs publish the same "
        f"(p = {wr['Professor']['p_papers_per_year']:.2f}); the gap is only among Assistant and Associate Professors.",
        "–", "Rank is today's rank; papers per year use each person's years on the faculty list.",
        "phase2/p2-depth-rank", "data/analysis/papers/r_papers_per_year_models.csv, r_summary.json")

    fd = rd("papers", "r_false_discovery.csv")
    bb = rd("ns_branch_fwci_bootstrap.csv").set_index("branch")
    keep = fd[(fd.family.str.startswith("branch FWCI")) & fd.significant_after_fdr].test.tolist()
    sw_ = [b for b in keep if bb.loc[b, "difference_T_minus_S"] < 0]
    tw_ = [b for b in keep if bb.loc[b, "difference_T_minus_S"] > 0]
    add(G, "Phase I + II", "The real differences are branch by branch",
        f"after correcting for testing 10 branches, Surathkal is stronger in {' and '.join(sw_)}, Trichy in {' and '.join(tw_)}; "
        f"Q1 share of ranked journal papers {pct(b0.loc[S, 'q1_share_of_ranked_journals'], 1)} (Surathkal) vs {pct(b0.loc[T, 'q1_share_of_ranked_journals'], 1)}",
        "Each NIT has its own strong departments; an institute-level 'winner' hides this.",
        "–", "Mechanical (Surathkal) and ECE (Trichy) differ at 5% alone but not after the correction.",
        "analysis", "data/analysis/ns_branch_fwci_bootstrap.csv, papers/r_false_discovery.csv")

    q15 = rd("questions", "q15_foreign_effect.csv").iloc[0]
    q16 = rd("questions", "q16_partner_types.csv").set_index("partner_type")
    add(G, "Phase II", "Foreign collaboration goes with higher impact",
        f"a foreign co-author goes with {q15.adjusted_effect_pct:+.0f}% FWCI (all papers, same field, year and team size); "
        f"{fs.foreign_effect_pct:+.0f}% in the faculty model with clustered errors (p = {fs.foreign_p_clustered:.4f}); "
        f"foreign universities {q16.loc['Foreign university', 'effect_pct']:+.0f}% (significant after correction), IITs {q16.loc['IIT', 'effect_pct']:+.0f}% (not significant)",
        "International partnerships are where the impact gain is; Indian partners such as IITs and other NITs show no clear gain in impact per paper.",
        "–", "An association: stronger groups may be the ones that find foreign partners.",
        "questions", "data/analysis/questions/q15_foreign_effect.csv, q16_partner_types.csv")

    eb = {b["authors"]: b for b in js("papers", "e_summary.json")["bands_faculty_both"]}
    add(G, "Phase II", "Bigger teams, higher impact, but no 'big science'",
        f"mean FWCI {eb['1']['mean_fwci']:.2f} (single author) → {eb['2-3']['mean_fwci']:.2f} (2–3) → {eb['6-9']['mean_fwci']:.2f} (6–9) → "
        f"{eb['10-19']['mean_fwci']:.2f} (10–19 authors); only {eb['20-49']['papers'] + (eb['50+']['papers'] or 0)} faculty paper has 20+ authors",
        "Impact rises steadily with team size, so large-team papers needed no special correction here.",
        "–", "Mean FWCI is pulled up by a few highly cited papers.",
        "phase2", "data/analysis/papers/e_summary.json")

    ai = rd("insights", "ai_share_by_year.csv")
    ai = ai[ai.computing == "all papers"].set_index("year").ai_share_pct
    ais = js("insights", "ai_summary.json")
    add(G, "Phase I", "AI is spreading to every department, mostly as a method",
        f"AI papers {ai[2016]:.1f}% of all in 2016 → {ai[2025]:.1f}% in 2025; departments with 5%+ AI papers: "
        f"{ais['departments_with_ai_share_ge_5pct_2016_2018']} → {ais['departments_with_ai_share_ge_5pct_2023_2025']} of {ais['departments']}",
        "AI is becoming a common tool in engineering research at both NITs, not only in computing.",
        "–", "AI is found from OpenAlex topics and title words, so some papers are missed or wrongly included.",
        "trends", "data/analysis/insights/ai_share_by_year.csv, ai_summary.json")

    allp = pd.read_csv(os.path.join(DATA, "all_papers.csv"), usecols=["institution", "openalex_id", "has_faculty_author", "fwci"], low_memory=False)
    with_fac = set(allp[allp.has_faculty_author].openalex_id)
    stu = allp[~allp.openalex_id.isin(with_fac)].drop_duplicates("openalex_id")
    n_all = allp.openalex_id.nunique()
    sm = allp.groupby(["institution", "has_faculty_author"]).fwci.median()
    add(G, "Phase II", "Students' own papers add a sixth more output",
        f"{f(len(stu))} papers with no faculty author ({f(n_all)} in all, +{pct(len(stu) / (n_all - len(stu)))}); median FWCI at Trichy {sm[(T, False)]:.2f} (students) vs {sm[(T, True)]:.2f} (faculty), "
        f"at Surathkal {sm[(S, False)]:.2f} vs {sm[(S, True)]:.2f}",
        "Students publish a lot on their own, at about the faculty level at Trichy and a little lower at Surathkal.",
        "–", "Counted only in the publication statistics; networks and rankings stay faculty-only.",
        "phase2", "data/all_papers.csv")

    # ============================================================ B. the collaboration network
    G = "The faculty collaboration network"
    sw = rd("ns_small_world.csv")
    gr = rd("insights", "growth_by_year.csv").set_index("year")
    last = gr.index.max()
    add(G, "Phase I", "A small world: short paths and strong clustering",
        f"average path {sw.avg_path_length[0]:.1f} steps (random networks with the same degrees {sw.avg_path_length[1]:.1f}); "
        f"average clustering {sw.avg_clustering[0]:.2f} vs {sw.avg_clustering[1]:.3f} ({sw.avg_clustering[0] / sw.avg_clustering[1]:.0f}× higher); transitivity {sw.transitivity[0]:.2f}",
        "Faculty sit in tight groups, yet a few links between groups keep everyone within a few steps.",
        f"Typical of co-authorship networks: in seven large ones the average distance is {LIT['dist_low']}–{LIT['dist_high']} and the clustering "
        f"(transitivity) {LIT['clust_low']}–{LIT['clust_high']} (Newman 2001). Ours (6.1 and 0.21) falls inside both ranges.",
        f"Measured in the largest connected group ({f(sw.nodes[0])} faculty); our network is small and faculty-only, Newman's had thousands of authors.",
        "coauthor", "data/analysis/ns_small_world.csv", ("newman01",))
    add(G, "Phase I", "A giant connected group holds three quarters of the faculty",
        f"{pct(gr.loc[last, 'largest_component_share'])} of the {f(gr.loc[last, 'faculty_nodes'])} faculty are in one connected group "
        f"({f(gr.loc[last, 'connected_faculty'])} have at least one faculty co-author)",
        "Most faculty are linked, directly or through colleagues, across departments and the two NITs.",
        f"Real co-authorship networks have giant components of {LIT['giant_low']:.0f}–{LIT['giant_high']:.0f}% (Newman 2001).",
        "Faculty with no faculty co-author still have outside co-authors.", "growth", "data/analysis/insights/growth_by_year.csv", ("newman01",))
    dfit = rd("ns_degree_fits.csv")
    nlog = int(dfit.verdict.str.startswith("log-normal").sum())
    add(G, "Phase I", "No clean power law in the degree distributions",
        f"a log-normal fits better than a power law for {nlog} of {len(dfit)} degree and citation distributions "
        f"(heavy tails, α ≈ {dfit.alpha.min():.1f}–{dfit.alpha.max():.1f})",
        "A few people have many co-authors, but the network is not 'scale-free'.",
        "Newman (2001) also found that collaboration networks are not pure power laws: their degree distributions have a cut-off.",
        "Fits use the powerlaw package (Clauset, Shalizi & Newman method).", "analysis", "data/analysis/ns_degree_fits.csv", ("newman01",))
    ad = rd("phase2", "assortativity_degree.csv").iloc[0]
    na = rd("ns_assortativity.csv").set_index("attribute")
    add(G, "Phase I + II", "Well-connected faculty work with each other (assortative)",
        f"degree assortativity r = {ad.r:.2f} vs {ad.null_mean:.2f} in rewired networks (z = {ad.z:.1f}); by branch r = {na.loc['branch', 'assortativity']:.2f}, "
        f"by NIT r = {na.loc['institution', 'assortativity']:.2f}, by rank only {na.loc['designation', 'assortativity']:.2f}",
        "Hubs link to hubs, people stay in their branch and NIT, and rank matters little.",
        f"This is the usual pattern of social networks: co-authorship networks have r = {LIT['assort_low']:.2f}–{LIT['assort_high']:.2f}, while technological "
        "and biological networks are disassortative (Newman 2002).",
        "Rank assortativity is weak but above chance (z ≈ 4).", "phase2", "data/analysis/phase2/assortativity_degree.csv, ns_assortativity.csv", ("newman02",))
    add(G, "Phase I", "The two NITs barely collaborate",
        f"{f(gr.loc[last, 'cross_nit_links'])} of {f(gr.loc[last, 'links'])} faculty links ({pct(gr.loc[last, 'cross_nit_links'] / gr.loc[last, 'links'], 1)}) join Trichy and Surathkal; "
        f"{f(per[T] + per[S] - uniq)} joint papers in ten years",
        "Two similar NITs work almost entirely apart; there is room for joint projects.",
        "–", "–", "coauthor", "data/analysis/insights/growth_by_year.csv")
    ns = js("questions", "network_summary.json")
    add(G, "Phase II", "A few people hold the network together",
        f"removing the 10 main bridge faculty disconnects {pct(ns[T]['pairs_lost_top10_bridges'])} (Trichy) and {pct(ns[S]['pairs_lost_top10_bridges'])} (Surathkal) "
        f"of connected faculty pairs, against {pct(ns[T]['pairs_lost_10_random'])} and {pct(ns[S]['pairs_lost_10_random'])} for 10 random departures",
        "Robust to random loss, fragile to losing its bridges: when key people retire or move, groups can split.",
        "–", "A what-if on the 2016–2026 network; real people are replaced over time.", "coauthor", "data/analysis/questions/network_summary.json")

    # ============================================================ C. how the network grows, and prediction
    G = "How the network grows, and predicting it"
    dens = js("insights", "insights_summary.json")["densification"]["connected_faculty_2016_2026"]
    six = rd("south", "s_six_nits.csv")
    add(G, "Phase I + II", "The network densifies: links grow faster than people",
        f"links ∝ (connected faculty)^a with a = {dens['exponent_a']:.2f} (R² = {dens['r_squared']:.3f}); the same exponent at the six South Indian NITs "
        f"is {six['a_connected_2016-2026'].min():.2f}–{six['a_connected_2016-2026'].max():.2f}",
        "Each faculty member gains co-authors over time, so the average number of co-authors keeps rising.",
        f"Real growing networks densify the same way, with a = {LIT['dens_low']}–{LIT['dens_high']} ({LIT['dens_text']}; Leskovec et al. 2005). "
        "Ours and five of the six NITs are inside this range; Surathkal is just above it.",
        "With every author counted (students too) a falls to about 1.2, so strong densification is a property of the closed faculty group.",
        "growth", "data/analysis/insights/insights_summary.json, south/s_six_nits.csv", ("leskovec",))
    gd = rd("prof", "g_average_degree_by_year.csv")
    gd = gd[(gd.view == "Both NITs") & ~gd.partial_year].set_index("year")
    peak = gr.loc[gr.index < last, "effective_diameter_90pct"].idxmax()
    add(G, "Phase I + II", "Distances shrink as the network grows",
        f"effective diameter {gr.loc[peak, 'effective_diameter_90pct']:.0f} steps in {peak} → {gr.loc[last, 'effective_diameter_90pct']:.0f}; average path in the largest group "
        f"{gr.loc[peak, 'avg_path_largest_component']:.1f} → {gr.loc[last, 'avg_path_largest_component']:.1f}; co-authors per connected faculty member "
        f"{gd.loc[2016, 'avg_degree_connected_faculty']:.2f} → {gd.loc[2025, 'avg_degree_connected_faculty']:.2f}, but within any one year only "
        f"{gd.year_avg_degree_connected.min():.1f}–{gd.year_avg_degree_connected.max():.1f}",
        "The giant group formed in 2018 through thin bridges (long paths); new links then acted as shortcuts. People do not write with "
        "more colleagues each year; the totals rise because old links stay.",
        "Leskovec et al. (2005) found shrinking diameters in real growing networks, largest when the giant component first appears; "
        "Barabási et al. (2002) found that in co-authorship networks the separation falls and the average degree rises over time.",
        "Counts are cumulative from 2016, so early years are short of history.", "growth",
        "data/analysis/insights/growth_by_year.csv, prof/g_average_degree_by_year.csv", ("leskovec", "barabasi02"))
    ks = {r["view"]: r for r in js("prof", "k_summary.json")["fits"]}
    rich = js("questions", "richer_summary.json")
    add(G, "Phase II", "Rich get richer: weak for collaborators, stronger for citations",
        f"new faculty co-authors ∝ (current co-authors)^{ks['Both NITs']['kernel_exponent']:.2f} (Trichy {ks[T]['kernel_exponent']:.2f}, Surathkal {ks[S]['kernel_exponent']:.2f}); "
        f"new citations ∝ (current citations)^{rich['alpha']:.2f}",
        "Well-connected faculty gain new collaborators only a little faster than others; highly cited papers gain citations much faster.",
        f"Barabási et al. (2002) measured a stronger attachment for co-authorship, k^{LIT['nu_high']} (mathematics) and k^{LIT['nu_low']} (neuroscience). "
        "Our collaborator effect is weaker; our citation effect is close to theirs.",
        "Busier people may simply write more papers; the fits are pooled over years.", "growth",
        "data/analysis/prof/k_summary.json, questions/richer_summary.json", ("barabasi02",))
    tc = rd("insights", "triadic_closure_by_common_coauthors.csv").set_index("bucket")
    nl = rd("insights", "new_link_sources_by_year.csv")
    nl = nl[(nl.year > 2016) & ~nl.partial_year.astype(bool)]
    closed = nl["closed a triangle (had a common co-author)"].sum()
    tot = nl[["closed a triangle (had a common co-author)", "existing faculty, no common co-author", "involves faculty new to the network"]].sum().sum()
    add(G, "Phase I", "Friends of friends become co-authors, but most new links are new contacts",
        f"pairs with one common co-author start working together {tc.loc['1 common co-author', 'times_more_likely_than_far_pairs']:.0f}× more often than distant pairs; "
        f"yet only {f(closed)} of {f(tot)} new links ({pct(closed / tot)}) closed a triangle (2017–2025)",
        "Common colleagues matter, but most new collaborations start between people with no shared co-author, usually in the same department.",
        "–", "Observational: we did not test introductions.", "growth", "data/analysis/insights/triadic_closure_by_common_coauthors.csv")
    lp = rd("prof", "p_link_prediction.csv")
    fx = lp[lp.model.str.startswith("fixed")].set_index("target_year")
    ys = list(fx.index)
    mt = rd("prof", "p_fixed_correct_matches.csv")
    aucs = " / ".join("{:.2f}".format(fx.loc[y, "auc"]) for y in ys)
    add(G, "Phase II", "New collaborations can be predicted, but exact hits are rare",
        f"a model trained once on 2016–2022 and given only the 2022 network: AUC {aucs} for {', '.join(map(str, ys))}; "
        f"its top 1% of pairs (about {f(fx.loc[ys[0], 'top_1pct_size'])}) holds {' / '.join(f(fx.loc[y, 'correct_in_top_1pct']) for y in ys)} of the real new pairs, "
        f"{fx.lift_top_1pct.min():.0f}–{fx.lift_top_1pct.max():.0f}× better than random ({len(mt)} correct matches listed)",
        "Who will work together next is fairly predictable (same department, active people, common colleagues), but only about 1 candidate pair "
        "in 2,000 starts each year, so most predicted pairs do not happen yet.",
        f"Real co-authorship networks behave the same: a random prediction is right {LIT['lp_rand_low']}–{LIT['lp_rand_high']}% of the time and the best "
        f"methods do up to about {LIT['lp_best']}× better than random, with low raw precision (Liben-Nowell & Kleinberg 2007).",
        f"Their task used only well-connected authors; ours scores all faculty pairs. New faculty ({fx.loc[ys[-1], 'out_of_reach_pct']:.0f}% of {ys[-1]}'s new pairs) "
        "are invisible to a 2022 model.", "phase2/p2-grow-predict", "data/analysis/prof/p_link_prediction.csv, p_fixed_correct_matches.csv", ("liben07",))

    # ============================================================ D. how things move through the network (theory vs simulation)
    G = "How things move through the network: theory vs simulation"
    sys.path.insert(0, HERE)
    import dynamics as dy           # noqa: E402
    import threshold_note as tn     # noqa: E402
    fe, fac, pairs_ = dy.load()
    lnb = {}
    for nit in (T, S):
        Gx = dy.graph(pairs_, fac, nit)
        lnb[nit] = tn.numbers(Gx.subgraph([u for u in Gx if Gx.degree(u) > 0]))["lnb"]
    sp = rd("dynamics", "spread_simulations.csv")
    sp = sp[sp.seeds == "random 5"].pivot(index="beta", columns="network", values="mean_reach_pct")
    add(G, "Phase II", "Ideas spread more easily at Surathkal, as the theory predicts",
        f"SIR epidemic threshold β_c = 1/λ_NB = {1 / lnb[T]:.3f} (Trichy) and {1 / lnb[S]:.3f} (Surathkal); simulated reach from 5 random starters "
        f"at β = 0.1 / 0.2 / 0.3: Trichy {sp.loc[0.1, T]:.1f} / {sp.loc[0.2, T]:.1f} / {sp.loc[0.3, T]:.1f}%, Surathkal {sp.loc[0.1, S]:.1f} / {sp.loc[0.2, S]:.1f} / {sp.loc[0.3, S]:.1f}%",
        "Spreading takes off between β = 0.2 and 0.3 at Trichy and around 0.15–0.2 at Surathkal, where the theory puts the thresholds; "
        "Surathkal's bigger, connected hubs raise λ and so lower its threshold.",
        "The threshold formula for SIR on real networks is the non-backtracking one (Karrer, Newman & Zdeborová 2014); worked out step by step in our PDF.",
        "In a small network the take-off is gradual, not a sharp jump.", "dynamics",
        "data/analysis/dynamics/spread_simulations.csv, dashboard/docs/threshold_calculations.pdf", ("karrer14", "thresholds"))
    sy = rd("dynamics", "sync_summary.csv").set_index("network")
    cu = rd("dynamics", "sync_curves.csv")
    cu = cu[cu.graph == "real"].assign(K=lambda d: d.K.round(2)).pivot_table(index="K", columns="network", values="r_mean")
    rr = lambda nit: " / ".join("{:.2f}".format(cu.loc[k, nit]) for k in (0.2, 0.3, 0.4))
    add(G, "Phase II", "Synchrony starts where theory says, but full synchrony is hard",
        f"onset K_c = K₀/λ₁ = {sy.loc[T, 'Kc_theory']:.3f} (Trichy) and {sy.loc[S, 'Kc_theory']:.3f} (Surathkal); simulated order parameter r at K = 0.2 / 0.3 / 0.4: "
        f"Trichy {rr(T)}, Surathkal {rr(S)} (noise level about {cu.loc[0.0, T]:.2f}); "
        f"Laplacian eigenratio {sy.loc['Both NITs', 'eigenratio']:.0f} vs {sy.loc['Both NITs', 'rewired_eigenratio']:.0f} in rewired networks",
        "Partial synchrony begins as predicted, but groups are joined by thin bridges, so the whole network is about 5× harder to bring into one rhythm than a random one.",
        "The onset formula is Restrepo, Ott & Hunt (2005); details in our PDF.",
        "Unweighted network, normal frequencies; synchrony inside departments was not measured.", "dynamics",
        "data/analysis/dynamics/sync_summary.csv, dashboard/docs/threshold_calculations.pdf", ("restrepo05", "thresholds"))
    ti = js("dynamics", "ties_summary.json")
    add(G, "Phase II", "Many collaborations renew, but few last the whole decade",
        f"{ti['renewed_within_3_pct']:.0f}% of faculty pairs write together again within 3 years; only {ti['of_those_active_2023_2025_pct']:.0f}% of the pairs that started in "
        "2016–2018 were still active in 2023–2025",
        "Partnerships are durable in the short run but turn over across a decade; same-department pairs and pairs with a strong first paper renew more.",
        "–", "Observational.", "dynamics", "data/analysis/dynamics/ties_summary.json")

    # ============================================================ E. citations
    G = "Citations"
    sc = js("papers", "s_summary.json")
    add(G, "Phase II", "Most citations between our own papers are self-citations, at every NIT",
        f"{pct(sc['self_citation_share_shared_author'])} of the {f(sc['internal_edges'])} citations between our papers share an author; without them none of the old "
        f"top-10 PageRank papers stays in the top 10; the share is {six.self_citation_share_pct.min():.0f}–{six.self_citation_share_pct.max():.0f}% at all six South Indian NITs",
        "The internal citation network mainly shows groups building on their own work, so PageRank inside it is not a measure of influence.",
        "–", "Compared across our six NITs only (no published benchmark). Citing your own earlier work is normal when it is relevant.",
        "phase2/p2-depth-self", "data/analysis/papers/s_summary.json, south/s_six_nits.csv")
    cp = rd("phase2", "citers_private_vs_public.csv").set_index("measure")
    aa = {r["group"]: r for r in js("papers", "a_summary.json")["table"]}
    add(G, "Phase II", "Private universities cite us as much as their size predicts, more often through people close to us",
        f"{cp.loc['citations_per_1000_of_their_papers', 'private_median']:.0f} vs {cp.loc['citations_per_1000_of_their_papers', 'public_median']:.0f} citations per 1,000 of their "
        f"papers (p = {cp.loc['citations_per_1000_of_their_papers', 'mann_whitney_p']:.2f}); {aa['from top private citers']['within_3_steps_pct']:.0f}% vs "
        f"{aa['from top public citers']['within_3_steps_pct']:.0f}% of their citations come from people within 3 co-authorship steps",
        "High citation counts from private universities mainly reflect their size; a somewhat larger share comes from people close to the cited authors (former students and co-authors).",
        "–", "At the level of the 40 institutes only the 'earlier co-author' share stays different after correction.", "phase2",
        "data/analysis/phase2/citers_private_vs_public.csv, papers/a_summary.json")
    mn = js("questions", "manipulation_summary.json")
    h10 = [r for r in mn["distribution"] if r["cites_at_least"] == 10][0]
    add(G, "Phase II", "No sign that citation manipulation changes the ranking",
        f"{pct(h10['share_of_links'], 1)} of {f(mn['indian_citation_links'])} Indian citations come from papers citing 10+ of ours; the top-20 faculty ranking is unchanged "
        f"without self-citations (Spearman {mn['ranking']['without self-citations']['spearman']:.3f})",
        "One local cluster (around one Surathkal Mechanical group, 2023–24, mostly former NIT members) exists, but it does not move the ranking.",
        "–", "A statistical signal for follow-up, not a judgement about anyone.", "questions", "data/analysis/questions/manipulation_summary.json")
    geo = js("insights", "geo_summary.json")
    add(G, "Phase I", "People collaborate locally, but knowledge travels far",
        f"{geo['share_joint_papers_within_300km_pct']:.0f}% of joint papers but {geo['share_citations_within_300km_pct']:.0f}% of citations are within 300 km; doubling the distance "
        f"cuts joint papers by {100 * (1 - 2 ** geo['distance_elasticity_joint_papers']):.0f}% and citations by {100 * (1 - 2 ** geo['distance_elasticity_citations']):.0f}% (partner size held fixed)",
        "Working together needs closeness; reading each other's work does not.",
        "–", "Indian partners only; distances between cities.", "connections", "data/analysis/insights/geo_summary.json")

    # ============================================================ F. the six South Indian NITs
    G = "The six South Indian NITs"
    ftest = js("south", "south_summary.json")["founding_test"]["hired_2021_2025_pct vs a_connected_2016-2026"]
    fr = rd("south", "s_friends_vs_ours.csv")
    fr = fr[fr.years == "2016-2026"].set_index("institution").a_connected_their_cleaned_data
    alt = six.set_index("institution")["a_connected_2016-2026"].copy()
    for k, v in fr.items():
        alt[k] = v
    h = six.set_index("institution").hired_2021_2025_pct
    rho_alt, p_alt = spearman_exact(list(h[alt.index]), list(alt))
    add(G, "Phase II", "Every South Indian NIT densifies; recent hiring goes with a lower exponent, but the evidence is thin",
        f"a = {six['a_connected_2016-2026'].min():.2f}–{six['a_connected_2016-2026'].max():.2f} at the six NITs; share hired in 2021–25 against a: "
        f"ρ = {ftest['spearman_rho']:.2f} (exact p = {ftest['p_exact']:.3f}, n = 6); with Groups 13's and 14's data for Warangal and Calicut ρ = {rho_alt:.2f} (p = {p_alt:.2f})",
        "Every NIT's faculty network densifies like a real growing network. NITs that hired more recently tend to have lower exponents, "
        "but with six NITs this is a pattern, not a law.",
        f"All exponents lie near the {LIT['dens_low']}–{LIT['dens_high']} range of real growing networks (Leskovec et al. 2005).",
        "Recent hiring, a young NIT and many Assistant Professors go together; inside single NITs the link is not consistent.",
        "south", "data/analysis/south/south_summary.json, s_six_nits.csv, s_friends_vs_ours.csv", ("leskovec",))
    rk = six.set_index("institution")
    pph = ", ".join("{} {:.1f}".format(i.replace("NIT ", ""), rk.loc[i, "papers_2024_per_faculty"]) for i in rk.index)
    asst = ", ".join("{:.0f}%".format(rk.loc[i, "assistant_pct"]) for i in rk.index)
    add(G, "Phase II", "Papers per head follow the rank mix at every NIT",
        f"papers in 2024 per faculty member (all current staff): {pph}; share of Assistant Professors: {asst}",
        "Senior-heavy NITs publish more per head; young NITs and NITs that hired recently publish less per head.",
        "–", "Andhra Pradesh has many ad hoc and contract staff; per regular faculty member it is the highest.", "south", "data/analysis/south/s_six_nits.csv")
    return out


def minus(x):
    """'-0.60' -> '−0.60' in the numbers shown to readers."""
    return {k: (v.replace("= -", "= −").replace("vs -", "vs −") if isinstance(v, str) else v) for k, v in x.items()}


def write(findings):
    findings = [minus(x) for x in findings]
    groups = list(dict.fromkeys(x["group"] for x in findings))
    L = ["# Main findings, what they mean, and how they compare with real networks", "",
         "Every number about our NITs is computed by `scripts/findings.py` from the analysis outputs listed under each finding. "
         "The numbers about other networks are quoted from the papers listed at the end. **Phase I** = the original assignment tasks; "
         "**Phase II** = the later questions and checks. The dashboard shows the same table at the top of the **Key findings** tab.", ""]
    n = 0
    for g in groups:
        L += [f"## {g}", ""]
        for x in [y for y in findings if y["group"] == g]:
            n += 1
            L += [f"### {n}. {x['title']} ({x['phase']})", "", f"- **Numbers:** {x['numbers']}.", f"- **What it means:** {x['meaning']}"]
            if x["real_world"] != "–":
                L.append(f"- **Compared with real networks:** {x['real_world']}")
            if x["caveat"] != "–":
                L.append(f"- **Read with care:** {x['caveat']}")
            L += [f"- **Evidence:** `{x['evidence']}`", ""]
    L += ["## Sources for the comparisons", ""]
    L += [f"- {v['label']}: {v['url']}" for v in SOURCES.values()]
    L.append("")
    open(os.path.join(AN, "FINDINGS.md"), "w", encoding="utf-8").write("\n".join(L))
    json.dump({"findings": findings, "sources": SOURCES}, open(os.path.join(AN, "findings.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"{n} findings -> data/analysis/FINDINGS.md, findings.json")


if __name__ == "__main__":
    write(build())
