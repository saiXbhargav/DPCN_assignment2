"""Network growth, link prediction and other NITs (17 Nov 2026) -> data/analysis/prof/

  python phase2_prof.py growth    Average degree of the faculty co-authorship network year by year (cumulative and
                                    single-year), per NIT, and what the densification exponent 1.65 means
  python phase2_prof.py predict   Link prediction, two models kept apart. Fixed: trained once on 2016-2022 and given
                                    only the 2022 network, it predicts 2023, 2024 and 2025 (correct matches in its top
                                    1% are saved). Updated: re-trained every year with the network of the year before
  python phase2_prof.py joining   When did today's faculty join? First year each person published with the NIT
                                    (OpenAlex affiliation history), checked against NITK's own "Date of Joining"
  python phase2_prof.py nits      Our two NITs next to NIT Warangal and NIT Calicut: papers, citations, impact,
                                    collaboration, faculty numbers (NIRF), and the same network-growth measures
  python phase2_prof.py scholar   Most-cited faculty: OpenAlex numbers next to their Google Scholar profiles

Needs fetch_peers.py (works, affiliations) for the joining and nits parts. Fixed seeds: each run gives the same numbers.
"""
import json
import os
import re
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import networkx as nx  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import stats  # noqa: E402

from insights import (expected_precision_at_k, graph_at, label, link_features, load,  # noqa: E402
                      model_features)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
RAW = os.path.join(DATA, "raw")
OUT = os.path.join(DATA, "analysis", "prof")
FIRST, PARTIAL_YEAR = 2016, 2026
SEED = 42
NITS = ["NIT Trichy", "NIT Surathkal"]
COLOR = {"NIT Trichy": "#2f6fdf", "NIT Surathkal": "#e8743b", "NIT Warangal": "#2a9d8f", "NIT Calicut": "#9b5de5",
         "Both NITs": "#5b5bd6"}


def conv(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if np.isnan(o) else float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(type(o))


def save(df, name):
    os.makedirs(OUT, exist_ok=True)
    df.to_csv(os.path.join(OUT, name), index=False)


def save_json(obj, name):
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, default=conv, ensure_ascii=False)


def savefig(fig, name):
    os.makedirs(OUT, exist_ok=True)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, name), dpi=150)
    plt.close(fig)


def densification(nodes, links):
    """Fit links = c * nodes^a on log-log axes; returns a and R^2."""
    r = stats.linregress(np.log(nodes), np.log(links))
    return r.slope, r.rvalue ** 2


# ================================================================ 1. average degree and the exponent 1.65
def growth_part():
    pairs, first_pub, info, _ = load()
    au = pd.read_csv(os.path.join(DATA, "authorship_network.csv"), low_memory=False)
    au = au[au.edge_category.isin(["same_nit", "nit_nit"])]
    g12 = pd.read_csv(os.path.join(DATA, "group12_data.csv"), usecols=["faculty_id", "year", "institution"])
    inst = info.institution.to_dict()
    rows = []
    for view in ["Both NITs"] + NITS:
        keep = (lambda v: True) if view == "Both NITs" else (lambda v, i=view: inst.get(v) == i)
        for t in range(FIRST, PARTIAL_YEAR + 1):
            # cumulative network: everyone who has published by t, every link formed by t
            G = graph_at(t, pairs, first_pub)
            G = G.subgraph([v for v in G if keep(v)])
            n, e = G.number_of_nodes(), G.number_of_edges()
            conn = sum(1 for v in G if G.degree(v) > 0)
            # single-year network: only that year's papers and the faculty who published that year
            act = set(g12[(g12.year == t)].faculty_id)
            act = {v for v in act if keep(v)}
            yr = au[au.year == t]
            ye = {tuple(sorted(p)) for p in zip(yr.author_a_id, yr.author_b_id) if keep(p[0]) and keep(p[1])}
            yconn = len({v for p in ye for v in p})
            rows.append({"view": view, "year": t, "partial_year": t == PARTIAL_YEAR,
                         "faculty_nodes": n, "connected_faculty": conn, "links": e,
                         "avg_degree_all_faculty": 2 * e / n if n else np.nan,
                         "avg_degree_connected_faculty": 2 * e / conn if conn else np.nan,
                         "year_active_faculty": len(act), "year_links": len(ye),
                         "year_avg_degree_active": 2 * len(ye) / len(act) if act else np.nan,
                         "year_avg_degree_connected": 2 * len(ye) / yconn if yconn else np.nan})
    g = pd.DataFrame(rows)
    both = g[g.view == "Both NITs"]
    # the same check as INSIGHTS.md: the team's 1.65 (exact 1.6545) must come out again
    a_conn, r2_conn = densification(both.connected_faculty, both.links)
    assert abs(a_conn - 1.65) < 0.01, a_conn
    fits = []
    for view in ["Both NITs"] + NITS:
        d = g[g.view == view]
        for label_, years in (("2016-2026", range(FIRST, PARTIAL_YEAR + 1)), ("2019-2025", range(2019, PARTIAL_YEAR))):
            dd = d[d.year.isin(years)]
            for x in ("connected_faculty", "faculty_nodes"):
                a, r2 = densification(dd[x], dd.links)
                fits.append({"view": view, "years": label_, "nodes_counted": x, "exponent_a": a, "r_squared": r2,
                             "avg_degree_grows_as_nodes_power": a - 1})
    fits = pd.DataFrame(fits)
    save(g.round(4), "g_average_degree_by_year.csv")
    save(fits.round(4), "g_densification_by_nit.csv")

    first, last = both.iloc[0], both[both.year == PARTIAL_YEAR - 1].iloc[0]
    summary = {
        "exponent_connected_both": a_conn, "r_squared": r2_conn,
        "meaning": "links grow as (connected faculty)^a; average degree = 2*links/nodes grows as nodes^(a-1)",
        "avg_degree_connected_2016": first.avg_degree_connected_faculty,
        "avg_degree_connected_2025": last.avg_degree_connected_faculty,
        "avg_degree_all_2016": first.avg_degree_all_faculty, "avg_degree_all_2025": last.avg_degree_all_faculty,
        "connected_2016": first.connected_faculty, "connected_2025": last.connected_faculty,
        "links_2016": first.links, "links_2025": last.links,
        "year_avg_degree_active": both.set_index("year").year_avg_degree_active.round(3).to_dict(),
        "fits": fits.round(4).to_dict("records"),
    }
    save_json(summary, "g_summary.json")

    fig, ax = plt.subplots(1, 3, figsize=(16, 4.6))
    for view in ["Both NITs"] + NITS:
        d = g[(g.view == view) & ~g.partial_year]
        ax[0].plot(d.year, d.avg_degree_connected_faculty, "-o", color=COLOR[view], label=view, ms=4)
        ax[1].plot(d.year, d.year_avg_degree_active, "-o", color=COLOR[view], label=view, ms=4)
        ax[2].loglog(d.connected_faculty, d.links, "o", color=COLOR[view], label=view, ms=5)
    for view in ["Both NITs"] + NITS:
        f = fits[(fits.view == view) & (fits.years == "2016-2026") & (fits.nodes_counted == "connected_faculty")].iloc[0]
        d = g[g.view == view]
        x = np.linspace(d.connected_faculty.min(), d.connected_faculty.max(), 50)
        c = np.exp(np.mean(np.log(d.links) - f.exponent_a * np.log(d.connected_faculty)))
        ax[2].loglog(x, c * x ** f.exponent_a, "-", color=COLOR[view], lw=1, label=f"{view}: a = {f.exponent_a:.2f}")
    ax[0].set_title("Average co-authors per connected faculty member\n(network up to each year)")
    ax[1].set_title("Average co-authors within one year\n(that year's papers, faculty who published that year)")
    ax[2].set_title("Densification: links vs connected faculty (log-log)")
    ax[0].set_xlabel("year"); ax[1].set_xlabel("year"); ax[2].set_xlabel("connected faculty N"); ax[2].set_ylabel("links E")
    for a_ in ax:
        a_.grid(alpha=0.3); a_.legend(fontsize=7)
    savefig(fig, "g_average_degree.png")
    pd.set_option("display.width", 250)
    print(fits.round(3).to_string(index=False))
    print(g[g.view == "Both NITs"].round(2).to_string(index=False))


# ================================================================ 2. link prediction: fixed model and updated model
TARGETS = [2023, 2024, 2025]
TRAIN_FROM = 2016          # first feature year: training windows 2016 -> 2017, ..., 2021 -> 2022
TOP_PCT = 1                # the fixed model's predictions for the correct-matches list: its top 1% of pairs
FIXED = "fixed: trained once on 2016-2022, input = 2022 network"
UPDATED = "updated: re-trained every year, input = network up to the year before"
BASE = "Adamic-Adar only (no learning), input = 2022 network"


def predict_part():
    """Which faculty pairs will write their first paper together? Two models, kept apart:
    A. fixed: trained once on 2016-2022 (windows t -> t+1) and given only the 2022 network; it predicts the new
       pairs of 2023, 2024 and 2025 without ever seeing later data. Its top 1% of pairs is its prediction list, and
       every real new pair in that list is saved as a correct match.
    B. updated: re-trained every year and given the real network of the year before (2022 for 2023, 2023 for 2024...).
    Both are scored on the same real new pairs: AUC, average precision, correct pairs in the top 100 / 1% / 5% / 10%."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import average_precision_score, roc_auc_score
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    pairs, first_pub, info, _ = load()
    rows = pd.read_csv(os.path.join(DATA, "group12_data.csv"), usecols=["faculty_id", "year", "openalex_id"])
    name = info.author.to_dict()
    feats = {t: link_features(t, pairs, first_pub, info, rows) for t in range(TRAIN_FROM, max(TARGETS))}
    first_year = {tuple(sorted(k)): y for k, y in zip(zip(pairs.author_a_id, pairs.author_b_id), pairs.first_year)}
    all_new = {Y: sum(v == Y for v in first_year.values()) for Y in TARGETS}
    # a joint paper of each pair from its first year, so every correct match can be checked by its DOI
    au = pd.read_csv(os.path.join(DATA, "authorship_network.csv"),
                     usecols=["author_a_id", "author_b_id", "year", "edge_category", "paper_doi"], low_memory=False)
    au = au[au.edge_category.isin(["same_nit", "nit_nit"])].sort_values(["year", "paper_doi"])
    first_doi = {}
    for a, b, y, doi in zip(au.author_a_id, au.author_b_id, au.year, au.paper_doi):
        k = tuple(sorted((a, b)))
        if first_year.get(k) == y and k not in first_doi:
            first_doi[k] = doi

    def model_until(last_label_year):
        """Logistic regression on every one-year window t -> t+1 whose label year is <= last_label_year."""
        X = pd.concat([model_features(feats[t]) for t in range(TRAIN_FROM, last_label_year)])
        y = np.concatenate([label(feats[t], pairs, t + 1, t + 1) for t in range(TRAIN_FROM, last_label_year)])
        return make_pipeline(StandardScaler(), LogisticRegression(max_iter=3000)).fit(X, y), int(y.sum()), len(y)

    def evaluate(scores, y, Y):
        P, n = int(y.sum()), len(y)
        out = {"candidate_pairs": n, "all_new_pairs": all_new[Y], "reachable_new_pairs": P,
               "out_of_reach_pct": 100 * (1 - P / all_new[Y]),
               "auc": roc_auc_score(y, scores), "average_precision": average_precision_score(y, scores),
               "base_rate_pct": 100 * P / n, "correct_in_top_100": 100 * expected_precision_at_k(scores, y, 100)}
        for q in (1, 5, 10):
            k = int(q / 100 * n)
            hits = expected_precision_at_k(scores, y, k) * k
            out.update({f"top_{q}pct_size": k, f"correct_in_top_{q}pct": hits, f"precision_top_{q}pct": 100 * hits / k,
                        f"lift_top_{q}pct": (hits / k) / (P / n), f"found_top_{q}pct": 100 * hits / P,
                        f"found_of_all_new_top_{q}pct": 100 * hits / all_new[Y]})
        return out

    def pair_info(a, b):
        return {"faculty_a": name.get(a, a), "institute_a": info.institution.get(a), "department_a": info.department.get(a),
                "faculty_b": name.get(b, b), "institute_b": info.institution.get(b), "department_b": info.department.get(b)}

    res, checks, matches = [], [], []
    fixed_model, fixed_pos, _ = model_until(2022)            # data up to 2022 only, never refitted
    d22 = feats[2022]
    s22 = fixed_model.predict_proba(model_features(d22))[:, 1]
    fy22 = np.array([first_year.get(tuple(sorted(k)), 9999) for k in zip(d22.a, d22.b)])
    for Y in TARGETS:
        # A. fixed model: pairs that wrote together between 2023 and Y-1 are dropped, the rest keep their 2022 scores
        keep = fy22 >= Y
        d, s, y = d22[keep].reset_index(drop=True), s22[keep], (fy22[keep] == Y).astype(int)
        res.append({"target_year": Y, "model": FIXED, "input_network_year": 2022,
                    "training_windows": f"{TRAIN_FROM}->{TRAIN_FROM + 1} ... 2021->2022", "training_positives": fixed_pos,
                    **evaluate(s, y, Y)})
        res.append({"target_year": Y, "model": BASE, "input_network_year": 2022, "training_windows": "-",
                    "training_positives": 0, **evaluate(d.adamic_adar.values.astype(float), y, Y)})
        k = int(TOP_PCT / 100 * len(y))
        for rank, i in enumerate(np.argsort(-s, kind="stable")[:k], 1):
            if y[i]:
                a, b = d.a.iloc[i], d.b.iloc[i]
                matches.append({"target_year": Y, "rank": rank, "list_size": k, **pair_info(a, b),
                                "common_coauthors_2022": int(d.common_neighbours.iloc[i]), "model_score": s[i],
                                "first_joint_paper_doi": first_doi.get(tuple(sorted((a, b))))})
        assert sum(m["target_year"] == Y for m in matches) == round(res[-2]["correct_in_top_1pct"]), "ties at the cut-off"
        # B. updated model: the real network up to Y-1 is the input, the model is refitted with every window up to Y-1
        upd_model, pos, _ = model_until(Y - 1)
        df = feats[Y - 1]
        yu = label(df, pairs, Y, Y)
        su = upd_model.predict_proba(model_features(df))[:, 1]
        res.append({"target_year": Y, "model": UPDATED, "input_network_year": Y - 1,
                    "training_windows": f"{TRAIN_FROM}->{TRAIN_FROM + 1} ... {Y - 2}->{Y - 1}", "training_positives": pos,
                    **evaluate(su, yu, Y)})
        # the updated model's 20 most likely pairs, and what really happened
        top = df.assign(score=su).nlargest(20, "score")
        for rank, (a, b, sc, cn) in enumerate(zip(top.a, top.b, top.score, top.common_neighbours), 1):
            fy = first_year.get(tuple(sorted((a, b))))
            checks.append({"target_year": Y, "rank": rank, **pair_info(a, b), "common_coauthors": int(cn), "model_score": sc,
                           "wrote_together_in_target_year": fy == Y, "first_joint_paper_year": fy})
    res, checks, matches = pd.DataFrame(res), pd.DataFrame(checks), pd.DataFrame(matches)
    old = os.path.join(OUT, "p_rolling_link_prediction.csv")          # replaced by p_link_prediction.csv
    for f in (old, old.replace(".csv", ".png")):
        if os.path.exists(f):
            os.remove(f)
    save(res.round(4), "p_link_prediction.csv")
    save(checks.round(4), "p_predict_and_check_top20.csv")
    save(matches.round(4), "p_fixed_correct_matches.csv")
    fx = res[res.model == FIXED].set_index("target_year")
    summary = {"targets": TARGETS, "train_from": TRAIN_FROM, "top_pct": TOP_PCT, "models": [FIXED, UPDATED, BASE],
               "table": res.round(4).to_dict("records"),
               "fixed_correct_matches": {int(k): int(v) for k, v in
                                         matches.groupby("target_year").size().reindex(TARGETS, fill_value=0).items()},
               "fixed_auc": {int(k): float(v) for k, v in fx.auc.round(3).items()},
               "updated_top20_hits": {int(k): int(v) for k, v in
                                      checks.groupby("target_year").wrote_together_in_target_year.sum().items()}}
    save_json(summary, "p_summary.json")

    fig, ax = plt.subplots(1, 2, figsize=(12, 4.4))
    for m, col in ((FIXED, "#e8743b"), (UPDATED, "#2f6fdf"), (BASE, "#888888")):
        d = res[res.model == m]
        ax[0].plot(d.target_year, d.auc, "-o", color=col, label=m)
        ax[1].plot(d.target_year, d.correct_in_top_1pct, "-o", color=col, label=m)
    ax[0].set_title("AUC (0.5 = random)"); ax[1].set_title("Real new pairs in the top 1% of predicted pairs")
    for a_ in ax:
        a_.set_xticks(TARGETS); a_.grid(alpha=0.3); a_.legend(fontsize=7)
    savefig(fig, "p_link_prediction.png")
    pd.set_option("display.width", 250)
    print(res[["target_year", "model", "all_new_pairs", "reachable_new_pairs", "auc", "correct_in_top_100",
               "correct_in_top_1pct", "lift_top_1pct", "correct_in_top_5pct"]].round(3).to_string(index=False))
    print(matches.head(10).round(3).to_string(index=False))


# ================================================================ 3. NIRF 2025: faculty numbers and joining years
# Each NIT's own copy of its NIRF 2025 'Overall' data file (nirfindia.org refuses scripted downloads). The files list
# every faculty member with designation, joining date and whether they still work there. They also list age and
# gender, so they stay out of the repo (data/raw/nirf/ is git-ignored) and only counts are saved.
NIRF = {
    "NIT Trichy": ("nitt_overall_2025.pdf", "https://www.nitt.edu/home/academics/nirf/1.%20NIRF%202025_IR-O-U-0467_Overall.pdf"),
    "NIT Surathkal": ("nitk_overall_2025.pdf", "https://www.nitk.ac.in/document/attachments/8178/Overall.pdf"),
    "NIT Warangal": ("nitw_overall_2025.pdf", "https://nitw.ac.in/api/static/files/20250627_NIRF_2025_Submitted_data_Overall_2025-7-1-15-41-37.pdf"),
    "NIT Calicut": ("nitc_overall_2025.pdf", "https://nitc.ac.in/imgserver/uploads/attachments/overall_f0a48d77-126f-477d-84d6-fbd669ab6061_0.pdf"),
}
NIRF_COLS = ["srno", "name", "age", "designation", "gender", "qualification", "experience_months", "currently_working",
             "joining_date", "leaving_date", "association"]
BANDS = [1970, 1995, 2000, 2002, 2004, 2006, 2010, 2014, 2018, 2022, 2026]


def nirf_faculty():
    """Every row of the 'Faculty Details' table of the four NIRF files (needs pymupdf)."""
    import pymupdf
    rows = []
    for nit, (f, _) in NIRF.items():
        doc = pymupdf.open(os.path.join(RAW, "nirf", f))
        started = False
        for page in doc:
            for t in page.find_tables().tables:
                for r in t.extract():
                    cells = [(c or "").replace("\n", " ").strip() for c in r]
                    if len(cells) != len(NIRF_COLS):
                        continue
                    if cells[0] == "Srno":
                        started = True
                    elif started and re.fullmatch(r"\d+", cells[0]):
                        rows.append({"institution": nit, **dict(zip(NIRF_COLS, cells))})
    d = pd.DataFrame(rows)
    for nit, g in d.groupby("institution"):      # serial numbers 1..N, none missing: the whole table was read
        s = g.srno.astype(int)
        assert s.is_unique and s.min() == 1 and s.max() == len(s), nit
    d["joining_year"] = pd.to_datetime(d.joining_date, format="%d-%m-%Y").dt.year
    d["current"] = d.currently_working.eq("Yes")
    d["rank"] = d.designation.where(d.designation.isin(["Professor", "Associate Professor", "Assistant Professor"]),
                                    "other (dean, head, lecturer, not given)")
    return d


def nirf_part():
    from names import name_score
    d = nirf_faculty()
    cur = d[d.current]
    counts = []
    for nit, g in d.groupby("institution", sort=False):
        c = g[g.current]
        counts.append({"institution": nit, "faculty_currently_working": len(c),
                       "regular": int((c.association == "Regular").sum()),
                       "adhoc_or_contractual": int((c.association == "Adhoc / Contractual").sum()),
                       "other_or_visiting": int((~c.association.isin(["Regular", "Adhoc / Contractual"])).sum()),
                       "professors": int((c["rank"] == "Professor").sum()),
                       "associate_professors": int((c["rank"] == "Associate Professor").sum()),
                       "assistant_professors": int((c["rank"] == "Assistant Professor").sum()),
                       "other_designation": int((~c["rank"].isin(["Professor", "Associate Professor", "Assistant Professor"])).sum()),
                       "assistant_share_pct": 100 * (c["rank"] == "Assistant Professor").mean(),
                       "median_joining_year": c.joining_year.median(),
                       "listed_but_left": int((~g.current).sum()),
                       "source": "NIRF 2025 Overall data file: " + NIRF[nit][1]})
    counts = pd.DataFrame(counts)
    os.makedirs(os.path.join(DATA, "reference"), exist_ok=True)
    counts.round(2).to_csv(os.path.join(DATA, "reference", "nirf_2025_faculty_counts.csv"), index=False)
    years = cur.groupby(["institution", "joining_year"]).size().unstack(0).fillna(0).astype(int)
    years = years.reindex(range(int(cur.joining_year.min()), 2026), fill_value=0)[list(NIRF)]
    years.reset_index().to_csv(os.path.join(DATA, "reference", "nirf_2025_joining_years.csv"), index=False)
    bands = pd.cut(cur.joining_year, BANDS, right=False,
                   labels=[f"{a}-{b - 1}" for a, b in zip(BANDS[:-1], BANDS[1:])])
    bt = pd.crosstab(bands, cur.institution)[list(NIRF)]
    save(bt.reset_index().rename(columns={"joining_year": "joined"}), "n_joining_bands.csv")

    # our roster against the official count, and joining year -> output for our two NITs
    fac = pd.read_csv(os.path.join(DATA, "faculty.csv"))
    g12 = pd.read_csv(os.path.join(DATA, "group12_data.csv"), usecols=["faculty_id", "year", "openalex_id"])
    by_year = (g12[g12.year < PARTIAL_YEAR].drop_duplicates(["faculty_id", "openalex_id"])
               .groupby(["faculty_id", "year"]).size())

    def papers_per_year(fid, joined):
        """Papers a year from the later of 2016 and the joining year, to 2025 (recent joiners are not diluted)."""
        start = max(FIRST, int(joined))
        if start > PARTIAL_YEAR - 1:
            return np.nan
        s = by_year.get(fid, pd.Series(dtype=float))
        return s[s.index >= start].sum() / (PARTIAL_YEAR - start)

    match_rows, check = [], []
    for nit in NITS:
        ours = fac[(fac.institution == nit) & (fac.status == "current")]
        check.append({"institution": nit, "our_roster_current_2026": len(ours),
                      "nirf_2025_currently_working": int(counts.set_index("institution").faculty_currently_working[nit])})
        for _, p in cur[cur.institution == nit].iterrows():
            sc = [(name_score(r.author, p["name"]), r.faculty_id) for r in ours.itertuples()]
            best = max(s for s, _ in sc)
            hits = [f for s, f in sc if s == best]
            if best >= 2 and len(hits) == 1:
                match_rows.append({"institution": nit, "faculty_id": hits[0], "joining_year": p.joining_year,
                                   "nirf_rank": p["rank"]})
    m = pd.DataFrame(match_rows).drop_duplicates("faculty_id")
    m["papers_per_year_2016_2025"] = [papers_per_year(f, j) for f, j in zip(m.faculty_id, m.joining_year)]
    m["joined"] = pd.cut(m.joining_year, BANDS, right=False, labels=[f"{a}-{b - 1}" for a, b in zip(BANDS[:-1], BANDS[1:])])
    cohort = (m.groupby(["institution", "joined"], observed=True)
               .agg(faculty=("faculty_id", "size"), median_papers_per_year=("papers_per_year_2016_2025", "median"),
                    professors_pct=("nirf_rank", lambda s: 100 * (s == "Professor").mean()))
               .reset_index())
    save(cohort.round(2), "n_cohort_output.csv")
    check = pd.DataFrame(check)
    check["matched_by_name"] = check.institution.map(m.groupby("institution").size())
    save(check, "n_roster_vs_nirf.csv")

    in_02_03 = cur[cur.joining_year.isin([2002, 2003])].groupby("institution").size().reindex(list(NIRF), fill_value=0)
    peak = {nit: {"year": int(years[nit].idxmax()), "joined": int(years[nit].max())} for nit in NIRF}
    summary = {"counts": counts.drop(columns="source").round(2).to_dict("records"),
               "joined_2002_or_2003": in_02_03.to_dict(), "biggest_hiring_year": peak,
               "roster_check": check.to_dict("records"),
               "caveat": "only people still working in 2025 (and recent leavers) are listed, so early hires who "
                         "left or retired before ~2022 are not visible"}
    save_json(summary, "n_summary.json")

    fig, ax = plt.subplots(4, 1, figsize=(12, 9), sharex=True)
    for a_, nit in zip(ax, NIRF):
        a_.bar(years.index, years[nit], color=COLOR[nit])
        a_.axvspan(2001.5, 2003.5, color="grey", alpha=0.15)
        a_.set_ylabel("joined"); a_.set_title(f"{nit}: year each current faculty member joined (NIRF 2025)", fontsize=9)
        a_.grid(alpha=0.3, axis="y")
    ax[-1].set_xlabel("joining year (grey: 2002-2003)")
    savefig(fig, "n_joining_years.png")
    pd.set_option("display.width", 250)
    print(counts.drop(columns="source").round(1).to_string(index=False))
    print(bt.to_string())
    print(check.to_string(index=False))
    print(cohort.round(2).to_string(index=False))


# ================================================================ 4. four NITs side by side
PEER_IDS = {"NIT Trichy": "I122964287", "NIT Surathkal": "I11880225", "NIT Warangal": "I121750182",
            "NIT Calicut": "I114845381"}
MAX_TEAM = 50


def peer_works(nit):
    with open(os.path.join(RAW, "peers", nit.replace(" ", "_") + "_works.jsonl"), encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def nits_part():
    counts = pd.read_csv(os.path.join(DATA, "reference", "nirf_2025_faculty_counts.csv")).set_index("institution")
    stats_rows, year_rows, net_rows = [], [], []
    for nit, iid in PEER_IDS.items():
        W = [w for w in peer_works(nit) if w["year"] and w["year"] >= FIRST]
        full = [w for w in W if w["year"] < PARTIAL_YEAR]
        fw = np.array([w["fwci"] for w in full if w["fwci"] is not None], dtype=float)
        partners = {i for w in full for a in w["authors"] for i in a["inst"] if i != iid}
        foreign = np.mean([any(c != "IN" for c in w["inst_countries"]) for w in full])
        regular = counts.regular[nit]
        p2024 = sum(w["year"] == 2024 for w in full)
        stats_rows.append({
            "institution": nit, "papers_2016_2025": len(full),
            "conference_share_pct": 100 * np.mean([w["type"] == "conference-paper" or w["source_type"] == "conference"
                                                   for w in full]),
            "citations": sum(w["cited_by_count"] or 0 for w in full),
            "citations_per_paper": np.mean([w["cited_by_count"] or 0 for w in full]),
            "mean_fwci": fw.mean(), "median_fwci": np.median(fw), "papers_with_fwci": len(fw),
            "foreign_coauthor_share_pct": 100 * foreign,
            "industry_coauthor_share_pct": 100 * np.mean(["company" in w["inst_types"] for w in full]),
            "partner_institutions": len(partners),
            "faculty_nirf_2025_regular": regular, "faculty_nirf_2025_all_current": counts.faculty_currently_working[nit],
            "papers_2024": p2024, "papers_2024_per_regular_faculty": p2024 / regular,
            "assistant_professor_share_pct": counts.assistant_share_pct[nit],
            "top_field": pd.Series([w["field"] for w in full if w["field"]]).value_counts().index[0]})
        for y in range(FIRST, PARTIAL_YEAR + 1):
            yw = [w for w in W if w["year"] == y]
            yf = np.array([w["fwci"] for w in yw if w["fwci"] is not None], dtype=float)
            year_rows.append({"institution": nit, "year": y, "papers": len(yw),
                              "mean_fwci": yf.mean() if len(yf) else np.nan})
        # co-authorship network of everyone with this NIT's affiliation on a paper (faculty, students, staff),
        # built the same way for all four NITs, cumulative from 2016
        first_seen, links, prev = {}, {}, set()
        for w in sorted(W, key=lambda w: w["year"]):
            if len(w["authors"]) > MAX_TEAM:
                continue
            ours = sorted({a["id"] for a in w["authors"] if a["id"] and iid in a["inst"]})
            for a in ours:
                first_seen.setdefault(a, w["year"])
            for i in range(len(ours)):
                for j in range(i + 1, len(ours)):
                    links.setdefault((ours[i], ours[j]), w["year"])
        for y in range(FIRST, PARTIAL_YEAR + 1):
            n = sum(1 for v in first_seen.values() if v <= y)
            E = [k for k, v in links.items() if v <= y]
            conn = len({x for k in E for x in k})
            yl = {k for k in E if links[k] == y}
            net_rows.append({"institution": nit, "year": y, "authors": n, "connected_authors": conn, "links": len(E),
                             "new_links": len(yl), "avg_degree_connected": 2 * len(E) / conn if conn else np.nan})
    st = pd.DataFrame(stats_rows)
    yr = pd.DataFrame(year_rows)
    net = pd.DataFrame(net_rows)
    fits = []
    for nit in PEER_IDS:
        d = net[net.institution == nit]
        for label_, ys in (("2016-2026", range(FIRST, PARTIAL_YEAR + 1)), ("2019-2025", range(2019, PARTIAL_YEAR))):
            dd = d[d.year.isin(ys)]
            a, r2 = densification(dd.connected_authors, dd.links)
            fits.append({"institution": nit, "years": label_, "exponent_a": a, "r_squared": r2})
    fits = pd.DataFrame(fits)
    st = st.merge(fits[fits.years == "2016-2026"][["institution", "exponent_a"]]
                  .rename(columns={"exponent_a": "densification_all_authors"}), on="institution")
    save(st.round(3), "c_four_nits.csv")
    save(yr.round(3), "c_four_nits_by_year.csv")
    save(net.round(3), "c_four_nits_network_by_year.csv")
    save(fits.round(4), "c_four_nits_densification.csv")
    save_json({"table": st.round(3).to_dict("records"), "densification": fits.round(4).to_dict("records")},
              "c_summary.json")

    fig, ax = plt.subplots(1, 3, figsize=(16, 4.6))
    for nit in PEER_IDS:
        d = yr[(yr.institution == nit) & (yr.year < PARTIAL_YEAR)]
        ax[0].plot(d.year, d.papers, "-o", color=COLOR[nit], label=nit, ms=4)
        n_ = net[(net.institution == nit) & (net.year < PARTIAL_YEAR)]
        ax[1].plot(n_.year, n_.avg_degree_connected, "-o", color=COLOR[nit], label=nit, ms=4)
        f = fits[(fits.institution == nit) & (fits.years == "2016-2026")].exponent_a.iloc[0]
        ax[2].loglog(n_.connected_authors, n_.links, "o-", color=COLOR[nit], label=f"{nit}: a = {f:.2f}", ms=4)
    ax[0].set_title("Papers per year (OpenAlex, same filter for all four)")
    ax[1].set_title("Average co-authors among the NIT's own authors\n(network up to each year)")
    ax[2].set_title("Densification: links vs connected authors (log-log)")
    for a_ in ax:
        a_.grid(alpha=0.3); a_.legend(fontsize=7)
    savefig(fig, "c_four_nits.png")
    pd.set_option("display.width", 250)
    print(st.round(2).T.to_string())
    print(fits.round(3).to_string(index=False))


def nitfaculty_part():
    """The faculty-only co-authorship network (as behind the 1.65) for all four NITs. Faculty = the people in each
    NIT's NIRF 2025 list, matched by name to OpenAlex authors who used that NIT's affiliation (an author ID that
    fits two people equally well is dropped). Needs pymupdf (reads the NIRF files)."""
    import collections

    from names import block_keys, name_score
    nf = nirf_faculty()
    net_rows, fits, match = [], [], []
    for nit, iid in PEER_IDS.items():
        W = [w for w in peer_works(nit) if w["year"] and w["year"] >= FIRST]
        names_ = {}
        for w in W:
            for a in w["authors"]:
                if a["id"] and iid in a["inst"]:
                    names_.setdefault(a["id"], a["name"] or "")
        index = collections.defaultdict(set)
        for aid, nm in names_.items():
            for k in block_keys(nm):
                index[k].add(aid)
        people = nf[(nf.institution == nit) & nf.current].reset_index(drop=True)
        cand = collections.defaultdict(list)
        for pi, nm in enumerate(people["name"]):
            for aid in set().union(set(), *(index.get(k, set()) for k in block_keys(nm))):
                s = name_score(nm, names_[aid])
                if s >= 2:
                    cand[aid].append((s, pi))
        owner = {}
        for aid, lst in cand.items():
            best = max(s for s, _ in lst)
            who = {pi for s, pi in lst if s == best}
            if len(who) == 1:
                owner[aid] = who.pop()
        first_seen, links = {}, {}
        for w in sorted(W, key=lambda w: w["year"]):
            if len(w["authors"]) > MAX_TEAM:
                continue
            fs = sorted({owner[a["id"]] for a in w["authors"] if a["id"] in owner and iid in a["inst"]})
            for f in fs:
                first_seen.setdefault(f, w["year"])
            for i in range(len(fs)):
                for j in range(i + 1, len(fs)):
                    links.setdefault((fs[i], fs[j]), w["year"])
        match.append({"institution": nit, "nirf_current_faculty": len(people),
                      "matched_to_openalex": len(set(owner.values())),
                      "matched_pct": 100 * len(set(owner.values())) / len(people), "openalex_ids_used": len(owner)})
        for y in range(FIRST, PARTIAL_YEAR + 1):
            n = sum(1 for v in first_seen.values() if v <= y)
            E = [k for k, v in links.items() if v <= y]
            conn = len({x for k in E for x in k})
            net_rows.append({"institution": nit, "year": y, "faculty_with_papers": n, "connected_faculty": conn,
                             "links": len(E), "new_links": sum(1 for k in E if links[k] == y),
                             "avg_degree_connected": 2 * len(E) / conn if conn else np.nan,
                             "avg_degree_all": 2 * len(E) / n if n else np.nan})
        d = pd.DataFrame([r for r in net_rows if r["institution"] == nit])
        for label_, ys in (("2016-2026", range(FIRST, PARTIAL_YEAR + 1)), ("2019-2025", range(2019, PARTIAL_YEAR))):
            dd = d[d.year.isin(ys) & (d.connected_faculty > 0)]
            a, r2 = densification(dd.connected_faculty, dd.links)
            fits.append({"institution": nit, "years": label_, "exponent_a": a, "r_squared": r2})
    net, fits, match = pd.DataFrame(net_rows), pd.DataFrame(fits), pd.DataFrame(match)
    save(net.round(3), "f_faculty_network_four_nits.csv")
    save(fits.round(4), "f_faculty_densification_four_nits.csv")
    save(match.round(1), "f_nirf_name_matching.csv")
    save_json({"matching": match.round(1).to_dict("records"), "densification": fits.round(4).to_dict("records")},
              "f_summary.json")
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.6))
    for nit in PEER_IDS:
        n_ = net[(net.institution == nit) & (net.year < PARTIAL_YEAR)]
        a = fits[(fits.institution == nit) & (fits.years == "2016-2026")].exponent_a.iloc[0]
        ax[0].plot(n_.year, n_.avg_degree_connected, "-o", color=COLOR[nit], label=nit, ms=4)
        ax[1].loglog(n_.connected_faculty, n_.links, "o-", color=COLOR[nit], label=f"{nit}: a = {a:.2f}", ms=4)
    ax[0].set_title("Faculty only: average co-authors per connected faculty member")
    ax[1].set_title("Faculty only: links vs connected faculty (log-log)")
    for a_ in ax:
        a_.grid(alpha=0.3); a_.legend(fontsize=7)
    savefig(fig, "f_faculty_network_four_nits.png")
    pd.set_option("display.width", 250)
    print(match.round(1).to_string(index=False))
    print(fits.round(3).to_string(index=False))
    print(net.pivot(index="year", columns="institution", values="avg_degree_connected").round(2).to_string())


# ================================================================ 5. Google Scholar reality check
def scholar_part():
    """A checklist: the 15 faculty with the highest OpenAlex career citations, plus the three most-cited physicists,
    with a Google Scholar search link each. Google Scholar blocks scripted access, so the Scholar columns are filled
    in by hand from a browser."""
    from urllib.parse import quote
    fl = pd.read_csv(os.path.join(DATA, "analysis", "phase2", "flag_faculty_citations_and_large_teams.csv"))
    fac = pd.read_csv(os.path.join(DATA, "faculty.csv")).drop_duplicates("faculty_id")
    fl = fl.merge(fac[["author", "institution", "h_index", "designation"]], on=["author", "institution"], how="left")
    top = fl.nlargest(15, "career_citations_openalex")
    phys = fl[fl.department == "Physics"].nlargest(3, "citations_2016_2026")
    chk = pd.concat([top, phys]).drop_duplicates(["author", "institution"])
    word = {"NIT Trichy": "Tiruchirappalli", "NIT Surathkal": "Karnataka"}
    out = pd.DataFrame({
        "faculty": chk.author, "institution": chk.institution, "department": chk.department,
        "designation": chk.designation, "openalex_career_citations": chk.career_citations_openalex,
        "openalex_career_h_index": chk.h_index, "citations_of_2016_2026_nit_papers": chk.citations_2016_2026,
        "nit_share_of_career_citations_pct": chk.nit_share_of_career_citations_pct,
        "flag_possible_openalex_name_merge": chk.flag_possible_openalex_name_merge,
        "google_scholar_search": ["https://scholar.google.com/citations?view_op=search_authors&mauthors="
                                  + quote(f"{a} {word[i]}") for a, i in zip(chk.author, chk.institution)],
        "scholar_citations_all": "", "scholar_h_index": "", "scholar_checked_on": "", "note": ""})
    path = os.path.join(OUT, "s_scholar_check.csv")
    if os.path.exists(path):          # keep anything already typed in by hand
        old = pd.read_csv(path, dtype=str).set_index(["faculty", "institution"])
        for c in ("scholar_citations_all", "scholar_h_index", "scholar_checked_on", "note"):
            out[c] = [old[c].get((a, i), "") if (a, i) in old.index else "" for a, i in zip(out.faculty, out.institution)]
    save(out, "s_scholar_check.csv")
    print(out.drop(columns="google_scholar_search").to_string(index=False))


# ================================================================ 7. "number of faculty, pure number"
def puren_part():
    """Average degree and the densification exponent with N = the plain number of faculty (every person on the
    yearly faculty pages, with or without a co-author), next to N = connected faculty. Two versions of "plain":
    everyone listed at least once up to year t (cumulative, like the links), and everyone listed in year t itself
    (then only links between people who are both still listed count)."""
    pairs, first_pub, info, _ = load()
    fac = pd.read_csv(os.path.join(DATA, "faculty.csv")).drop_duplicates("faculty_id").set_index("faculty_id")
    first = fac.first_seen.clip(lower=FIRST)
    rows = []
    for view in ["Both NITs"] + NITS:
        ids = fac.index if view == "Both NITs" else fac.index[fac.institution == view]
        for t in range(FIRST, PARTIAL_YEAR + 1):
            G = graph_at(t, pairs, first_pub)
            G = G.subgraph([v for v in G if v in ids])
            e = G.number_of_edges()
            conn = sum(1 for v in G if G.degree(v) > 0)
            ever = int((first[ids] <= t).sum())
            post = [v for v in ids if fac.first_seen[v] <= t <= fac.last_seen[v]]
            e_post = G.subgraph([v for v in post if v in G]).number_of_edges()
            rows.append({"view": view, "year": t, "partial_year": t == PARTIAL_YEAR, "links": e,
                         "connected_faculty": conn, "faculty_listed_so_far": ever, "faculty_in_post": len(post),
                         "links_between_faculty_in_post": e_post,
                         "avg_degree_connected": 2 * e / conn if conn else np.nan,
                         "avg_degree_all_listed_so_far": 2 * e / ever if ever else np.nan,
                         "avg_degree_in_post": 2 * e_post / len(post) if post else np.nan})
    g = pd.DataFrame(rows)
    fits = []
    for view in ["Both NITs"] + NITS:
        d = g[g.view == view]
        for lab, years in (("2016-2026", range(FIRST, PARTIAL_YEAR + 1)), ("2019-2025", range(2019, PARTIAL_YEAR))):
            dd = d[d.year.isin(years)]
            for n_col, e_col in (("connected_faculty", "links"), ("faculty_listed_so_far", "links"),
                                 ("faculty_in_post", "links_between_faculty_in_post")):
                a, r2 = densification(dd[n_col], dd[e_col])
                fits.append({"view": view, "years": lab, "nodes_counted": n_col, "exponent_a": a, "r_squared": r2})
    fits = pd.DataFrame(fits)
    save(g.round(4), "u_pure_n_by_year.csv")
    save(fits.round(4), "u_pure_n_densification.csv")
    b = g[(g.view == "Both NITs") & ~g.partial_year]
    save_json({"meaning": "N = every faculty member on the yearly pages (with or without a faculty co-author)",
               "fits": fits.round(4).to_dict("records"),
               "both_2016": b.iloc[0].to_dict(), "both_2025": b.iloc[-1].to_dict()}, "u_summary.json")
    print(fits.round(3).to_string(index=False))
    print(b.round(2).to_string(index=False))


# ================================================================ 8. do the rich get richer? (co-authorship)
def kernel_part():
    """Preferential attachment in the faculty network: how many NEW faculty co-authors a person gains in year t+1,
    against how many they already have at the end of year t (t = 2016..2024), pooled over years."""
    pairs, first_pub, info, _ = load()
    inst = info.institution.to_dict()
    bins = [(0, 0), (1, 1), (2, 2), (3, 4), (5, 8), (9, 16), (17, 999)]
    rows, fits = [], []
    for view in ["Both NITs"] + NITS:
        keep = (lambda v: True) if view == "Both NITs" else (lambda v, i=view: inst.get(v) == i)
        obs = []
        for t in range(FIRST, PARTIAL_YEAR - 1):
            G0, G1 = graph_at(t, pairs, first_pub), graph_at(t + 1, pairs, first_pub)
            for v in G0:
                if keep(v):
                    obs.append((G0.degree(v), G1.degree(v) - G0.degree(v)))
        o = pd.DataFrame(obs, columns=["k", "new"])
        for lo, hi in bins:
            s = o[(o.k >= lo) & (o.k <= hi)]
            if len(s):
                rows.append({"view": view, "co_authors_now": f"{lo}" if lo == hi else (f"{lo}+" if hi > 100 else f"{lo}-{hi}"),
                             "k_mean": s.k.mean(), "person_years": len(s), "mean_new_next_year": s.new.mean(),
                             "share_gaining_any_pct": 100 * (s.new > 0).mean()})
        pos = o[o.k > 0].groupby("k").new.mean()
        pos = pos[pos > 0]
        r = stats.linregress(np.log(pos.index), np.log(pos.values))
        fits.append({"view": view, "kernel_exponent": r.slope, "r_squared": r.rvalue ** 2, "person_years": len(o),
                     "mean_new_k0": o[o.k == 0].new.mean(), "mean_new_k1": o[o.k == 1].new.mean(),
                     "mean_new_k9plus": o[o.k >= 9].new.mean()})
    save(pd.DataFrame(rows).round(4), "k_kernel.csv")
    save_json({"meaning": "new faculty co-authors in year t+1 ~ k^alpha, k = faculty co-authors at the end of year t; "
                          "alpha = 1 is linear preferential attachment", "fits": pd.DataFrame(fits).round(4).to_dict("records")},
              "k_summary.json")
    print(pd.DataFrame(rows).round(3).to_string(index=False))
    print(pd.DataFrame(fits).round(3).to_string(index=False))


PARTS = {"growth": growth_part, "predict": predict_part, "nirf": nirf_part, "nits": nits_part,
         "nitfaculty": nitfaculty_part, "scholar": scholar_part, "puren": puren_part, "kernel": kernel_part}


def main():
    todo = sys.argv[1:] or list(PARTS)
    for p in todo:
        print(f"===== {p}")
        PARTS[p]()


if __name__ == "__main__":
    main()
