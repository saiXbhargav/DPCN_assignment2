"""The six South Indian NITs side by side (18 Nov 2026) -> data/analysis/south/

  python south_nits.py

NIT Trichy and NIT Surathkal (ours), NIT Warangal and NIT Calicut (also checked against Groups 13 and 14, see
check_friends.py), and the two young NITs, NIT Puducherry (2010) and NIT Andhra Pradesh (2015).
Every number uses the same sources for all six, so the comparison is fair:
  - papers: our OpenAlex download (fetch_peers.py, same filter for all six), plus the references that point to
    another paper of the same NIT (fetch_peers.py refs) for the self-citation share;
  - faculty: each NIT's NIRF 2025 list (rank, joining year), matched by name to OpenAlex author IDs as on 17 Nov.
The faculty network is built exactly like the one behind our 1.66: faculty only, papers with up to 50 authors,
cumulative from 2016. Average degree uses two N's: connected faculty (at least one faculty co-author) and the plain
number of faculty in post that year ("pure number": NIRF faculty who had joined by then).
The founding-years test asks whether hiring waves (a young NIT still hiring its first faculty, or a big recruitment
drive) lower the densification exponent.
Needs: fetch_peers.py (works + refs), the six NIRF files in data/raw/nirf/, check_friends.py run first. pymupdf.
"""
import collections
import json
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import stats  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_friends as K  # noqa: E402  (also registers the two new NIRF files)
import phase2_prof as P  # noqa: E402

DATA, RAW, OUT = K.DATA, K.RAW, K.OUT
FIRST, PARTIAL_YEAR = P.FIRST, P.PARTIAL_YEAR
YEARS = list(range(FIRST, PARTIAL_YEAR + 1))
SOUTH = K.SOUTH
# founding year: as a Regional Engineering College for the four old ones (all became NITs in 2002-03)
FOUNDED = {"NIT Warangal": (1959, "general knowledge (first REC)"), "NIT Surathkal": (1960, "general knowledge"),
           "NIT Calicut": (1961, "general knowledge"), "NIT Trichy": (1964, "general knowledge"),
           "NIT Puducherry": (2010, "general knowledge (the NIT's site says only 'established under MHRD')"),
           "NIT Andhra Pradesh": (2015, "NIT Andhra Pradesh website: 'established in the year 2015'")}
COLOR = {"NIT Trichy": "#2f6fdf", "NIT Surathkal": "#e8743b", "NIT Warangal": "#2a9d8f", "NIT Calicut": "#9b5de5",
         "NIT Puducherry": "#c99a1e", "NIT Andhra Pradesh": "#d1477a"}
RANKS = ["Professor", "Associate Professor", "Assistant Professor"]


def fit(n, e):
    n, e = np.asarray(n, float), np.asarray(e, float)
    ok = (n > 0) & (e > 0)
    if ok.sum() < 3 or np.ptp(np.log(n[ok])) == 0:
        return np.nan, np.nan
    r = stats.linregress(np.log(n[ok]), np.log(e[ok]))
    return r.slope, r.rvalue ** 2


def q1_lookup():
    """Journal + year -> quartile from our own all_papers.csv (the quartile rule of our project)."""
    ap = pd.read_csv(os.path.join(DATA, "all_papers.csv"), usecols=["journal_name", "year", "quartile", "type"])
    ap = ap[ap.type == "journal"].dropna(subset=["journal_name", "quartile"])
    ap["j"] = ap.journal_name.map(K.ntitle)
    return ap.groupby(["j", "year"]).quartile.agg(lambda s: s.mode().iloc[0]).to_dict()


def faculty_network(W, owner, iid, people):
    """Year by year faculty co-authorship network (cumulative) + single-year co-authors."""
    first_seen, links, year_pairs = {}, {}, collections.defaultdict(set)
    fac_papers = collections.Counter()
    for w in sorted(W, key=lambda w: w["year"]):
        fs = sorted({owner[a["id"]] for a in w["authors"] if a["id"] in owner and iid in a["inst"]})
        if fs:
            fac_papers[w["year"]] += 1
        if len(w["authors"]) > P.MAX_TEAM:
            continue
        for f in fs:
            first_seen.setdefault(f, w["year"])
        for i in range(len(fs)):
            for j in range(i + 1, len(fs)):
                links.setdefault((fs[i], fs[j]), w["year"])
                year_pairs[w["year"]].add((fs[i], fs[j]))
    joined = people.joining_year.values
    rows = []
    for y in YEARS:
        E = [k for k, v in links.items() if v <= y]
        conn = len({x for k in E for x in k})
        pure = int((joined <= y).sum())                      # NIRF faculty in post by year y (2025 list)
        deg = collections.Counter(x for k in year_pairs[y] for x in k)
        rows.append({"year": y, "faculty_in_post_pure_n": pure, "faculty_with_papers": sum(v <= y for v in first_seen.values()),
                     "connected_faculty": conn, "links": len(E), "new_links": sum(1 for k in E if links[k] == y),
                     "avg_degree_connected": 2 * len(E) / conn if conn else np.nan,
                     "avg_degree_pure_n": 2 * len(E) / pure if pure else np.nan,
                     "single_year_coauthors": np.mean(list(deg.values())) if deg else np.nan,
                     "faculty_papers": fac_papers[y],
                     "hired": int((joined == y).sum())})
    return pd.DataFrame(rows), links


def all_author_network(W, iid):
    first_seen, links = {}, {}
    for w in sorted(W, key=lambda w: w["year"]):
        if len(w["authors"]) > P.MAX_TEAM:
            continue
        ours = sorted({a["id"] for a in w["authors"] if a["id"] and iid in a["inst"]})
        for a in ours:
            first_seen.setdefault(a, w["year"])
        for i in range(len(ours)):
            for j in range(i + 1, len(ours)):
                links.setdefault((ours[i], ours[j]), w["year"])
    return pd.DataFrame([{"year": y, "authors": sum(v <= y for v in first_seen.values()),
                          "connected_authors": len({x for k, v in links.items() if v <= y for x in k}),
                          "author_links": sum(v <= y for v in links.values())} for y in YEARS])


def self_citation(nit, W):
    """Citations between two papers of the same NIT (2016-2026): share where the two papers share an author."""
    path = os.path.join(RAW, "peers", nit.replace(" ", "_") + "_internal_refs.jsonl")
    if not os.path.exists(path):
        return {}
    auth = {w["id"]: {a["id"] for a in w["authors"] if a["id"]} for w in W}
    n_int = n_self = n_refs = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r["id"] not in auth:
                continue
            n_refs += r["n_refs"]
            for t in r["internal_refs"]:
                if t in auth:
                    n_int += 1
                    n_self += bool(auth[r["id"]] & auth[t])
    return {"internal_citations": n_int, "internal_citations_sharing_an_author": n_self,
            "self_citation_share_pct": 100 * n_self / n_int if n_int else np.nan,
            "internal_share_of_all_references_pct": 100 * n_int / n_refs if n_refs else np.nan}


def nirf_reference(nf):
    """Counts only (the NIRF files themselves list age and gender and stay out of the repo): the same columns as
    data/reference/nirf_2025_faculty_counts.csv, now for all six NITs."""
    rows = []
    for nit in SOUTH:
        c = nf[(nf.institution == nit) & nf.current]
        rows.append({"institution": nit, "faculty_currently_working": len(c),
                     "regular": int((c.association == "Regular").sum()),
                     "adhoc_or_contractual": int((c.association == "Adhoc / Contractual").sum()),
                     "other_or_visiting": int((~c.association.isin(["Regular", "Adhoc / Contractual"])).sum()),
                     "professors": int((c["rank"] == "Professor").sum()),
                     "associate_professors": int((c["rank"] == "Associate Professor").sum()),
                     "assistant_professors": int((c["rank"] == "Assistant Professor").sum()),
                     "other_designation": int((~c["rank"].isin(RANKS)).sum()),
                     "assistant_share_pct": round(100 * (c["rank"] == "Assistant Professor").mean(), 2),
                     "median_joining_year": c.joining_year.median(),
                     "listed_but_left": int(((nf.institution == nit) & ~nf.current).sum()),
                     "source": "NIRF 2025 Overall data file: " + P.NIRF[nit][1]})
    ref = os.path.join(DATA, "reference")
    pd.DataFrame(rows).to_csv(os.path.join(ref, "nirf_2025_faculty_counts_six_nits.csv"), index=False)
    cur = nf[nf.institution.isin(list(SOUTH)) & nf.current]
    years = cur.groupby(["joining_year", "institution"]).size().unstack(1).fillna(0).astype(int)
    years = years.reindex(range(int(cur.joining_year.min()), 2026), fill_value=0)[list(SOUTH)]
    years.reset_index().to_csv(os.path.join(ref, "nirf_2025_joining_years_six_nits.csv"), index=False)


def main():
    nf = K.nirf()
    nirf_reference(nf)
    lookup = q1_lookup()
    table, by_year, dens, rolling = [], [], [], []
    for nit, iid in SOUTH.items():
        W = K.our_works(nit)
        people = nf[(nf.institution == nit) & nf.current].reset_index(drop=True)
        owner, _ = K.nirf_owner(nit, W, people)
        net, _ = faculty_network(W, owner, iid, people)
        aan = all_author_network(W, iid)
        net = net.merge(aan, on="year")
        papers = collections.Counter(w["year"] for w in W)
        net["papers"] = net.year.map(papers)
        net.insert(0, "institution", nit)
        by_year.append(net)
        full = [w for w in W if w["year"] < PARTIAL_YEAR]
        fw = np.array([w["fwci"] for w in full if w["fwci"] is not None], float)
        jour = [w for w in full if not (w["type"] == "conference-paper" or w["source_type"] == "conference")]
        qs = [lookup.get((K.ntitle(w["source"]), w["year"])) for w in jour if w["source"]]
        qs_known = [q for q in qs if q]
        c = people
        cur_n = len(c)
        regular = int((c.association == "Regular").sum())
        p24 = int(net.set_index("year").papers[2024])
        fp24 = int(net.set_index("year").faculty_papers[2024])
        hired5 = int(c.joining_year.between(2021, 2025).sum())
        row = {"institution": nit, "founded": FOUNDED[nit][0], "papers_2016_2025": len(full),
               "papers_2025": int(papers[2025]), "papers_2024": p24,
               "faculty_papers_2024": fp24,
               "citations_per_paper": np.mean([w["cited_by_count"] or 0 for w in full]),
               "median_fwci": float(np.median(fw)), "mean_fwci": float(fw.mean()),
               "conference_share_pct": 100 * (1 - len(jour) / len(full)),
               "foreign_coauthor_share_pct": 100 * np.mean([any(x != "IN" for x in w["inst_countries"]) for w in full]),
               "q1_share_of_journal_papers_pct": 100 * np.mean([q == "Q1" for q in qs_known]) if qs_known else np.nan,
               "quartile_known_pct": 100 * len(qs_known) / max(1, len(jour)),
               "nirf_faculty_current": cur_n, "nirf_regular": regular,
               "nirf_adhoc_contract_visiting": cur_n - regular,
               "professor_pct": 100 * (c["rank"] == "Professor").mean(),
               "associate_pct": 100 * (c["rank"] == "Associate Professor").mean(),
               "assistant_pct": 100 * (c["rank"] == "Assistant Professor").mean(),
               "median_joining_year": float(c.joining_year.median()),
               "hired_2021_2025": hired5, "hired_2021_2025_pct": 100 * hired5 / cur_n,
               "hired_since_2016_pct": 100 * (c.joining_year >= 2016).mean(),
               "faculty_matched_to_openalex": len(set(owner.values())),
               "faculty_matched_pct": 100 * len(set(owner.values())) / cur_n,
               "papers_2024_per_faculty": p24 / cur_n, "faculty_papers_2024_per_faculty": fp24 / cur_n,
               "papers_2024_per_regular_faculty": p24 / regular if regular else np.nan}
        n25 = net.set_index("year").loc[2025]
        row.update({"faculty_links_2025": int(n25.links), "connected_faculty_2025": int(n25.connected_faculty),
                    "avg_degree_connected_2025": n25.avg_degree_connected, "avg_degree_pure_n_2025": n25.avg_degree_pure_n,
                    "single_year_coauthors_2025": n25.single_year_coauthors})
        row.update(self_citation(nit, W))
        for label_, ys in (("2016-2026", YEARS), ("2019-2025", range(2019, PARTIAL_YEAR))):
            d = net[net.year.isin(ys)]
            for nlab, ncol, ecol in (("connected faculty", "connected_faculty", "links"),
                                     ("all faculty in post (pure N)", "faculty_in_post_pure_n", "links"),
                                     ("all authors incl. students", "connected_authors", "author_links")):
                a, r2 = fit(d[ncol], d[ecol])
                dens.append({"institution": nit, "years": label_, "n_definition": nlab, "exponent_a": a, "r_squared": r2})
        for end in range(2019, PARTIAL_YEAR):
            d = net[net.year.between(end - 3, end)]
            a, _ = fit(d.connected_faculty, d.links)
            end_head = int(net.set_index("year").faculty_in_post_pure_n[end])
            rolling.append({"institution": nit, "window": f"{end - 3}-{end}", "window_end": end, "exponent_a": a,
                            "hired_in_window": int(d.hired.sum()), "faculty_in_post_at_end": end_head,
                            "hired_in_window_pct": 100 * d.hired.sum() / end_head if end_head else np.nan})
        table.append(row)
    table = pd.DataFrame(table)
    by_year = pd.concat(by_year, ignore_index=True)
    dens = pd.DataFrame(dens)
    rolling = pd.DataFrame(rolling)
    pick = lambda yrs, nd: dens[(dens.years == yrs) & (dens.n_definition == nd)].set_index("institution").exponent_a  # noqa
    for yrs in ("2016-2026", "2019-2025"):
        table[f"a_connected_{yrs}"] = table.institution.map(pick(yrs, "connected faculty"))
        table[f"a_pure_n_{yrs}"] = table.institution.map(pick(yrs, "all faculty in post (pure N)"))
        table[f"a_all_authors_{yrs}"] = table.institution.map(pick(yrs, "all authors incl. students"))

    # ---- founding-years test (six points: exact permutation p-value, all 720 orderings)
    import itertools

    def spearman_exact(x, y):
        rx, ry = stats.rankdata(x), stats.rankdata(y)
        obs = stats.spearmanr(rx, ry)[0]
        perms = [stats.spearmanr(rx, np.array(p_))[0] for p_ in itertools.permutations(ry)]
        return obs, float(np.mean([abs(r) >= abs(obs) - 1e-12 for r in perms]))

    tests = {}
    for col in ("hired_2021_2025_pct", "hired_since_2016_pct", "assistant_pct", "founded"):
        for a_col in ("a_connected_2016-2026", "a_connected_2019-2025"):
            rho, p = spearman_exact(table[col].values, table[a_col].values)
            tests[f"{col} vs {a_col}"] = {"spearman_rho": rho, "p_exact": p, "n": len(table)}
    rr = rolling.dropna(subset=["exponent_a", "hired_in_window_pct"])
    rho, p = stats.spearmanr(rr.hired_in_window_pct, rr.exponent_a)
    tests["rolling 4-year windows: share of faculty hired in the window vs exponent"] = {
        "spearman_rho": rho, "p": p, "n": len(rr)}

    # ---- friends' data as a second source for Warangal and Calicut
    fvo = []
    for nit in K.FRIENDS:
        iid = SOUTH[nit]
        fr = pd.read_csv(os.path.join(OUT, f"friends_{K.slug(nit)}_faculty_rows.csv"))
        pp = pd.read_csv(os.path.join(OUT, f"friends_{K.slug(nit)}_papers.csv"))
        small = set(pp[pp.n_authors_openalex.fillna(0) <= P.MAX_TEAM].doi)
        people = nf[(nf.institution == nit) & nf.current].reset_index(drop=True)
        links = {}
        for d, g in fr[fr.doi.isin(small)].sort_values("year").groupby("doi", sort=False):
            fs = sorted(set(g.openalex_author_id))
            y = int(g.year.iloc[0])
            for i in range(len(fs)):
                for j in range(i + 1, len(fs)):
                    k = (fs[i], fs[j])
                    links[k] = min(links.get(k, y), y)
        rows = []
        for y in YEARS:
            E = [k for k, v in links.items() if v <= y]
            rows.append({"year": y, "links": len(E), "conn": len({x for k in E for x in k})})
        r = pd.DataFrame(rows)
        ours = by_year[by_year.institution == nit].set_index("year")
        for label_, ys in (("2016-2026", YEARS), ("2019-2025", list(range(2019, PARTIAL_YEAR)))):
            d = r[r.year.isin(ys)]
            a_f, _ = fit(d.conn, d.links)
            fvo.append({"institution": nit, "years": label_,
                        "a_connected_their_cleaned_data": a_f,
                        "a_connected_our_download": pick(label_, "connected faculty")[nit],
                        "links_2025_their_data": int(r.set_index("year").links[2025]),
                        "links_2025_our_download": int(ours.links[2025]),
                        "papers_2024_their_data": int((pp.year == 2024).sum()),
                        "papers_2024_our_download": int(ours.papers[2024]),
                        "q1_share_their_quartiles_pct": 100 * float((pp[pp.type == "journal"].quartile == "Q1").sum()
                                                                    / max(1, pp[(pp.type == "journal")
                                                                                & pp.quartile.fillna("").str.startswith("Q")].shape[0]))})
    fvo = pd.DataFrame(fvo)

    K.save(table.round(4), "s_six_nits.csv")
    K.save(by_year.round(4), "s_by_year.csv")
    K.save(dens.round(4), "s_densification.csv")
    K.save(rolling.round(4), "s_rolling_exponent.csv")
    K.save(fvo.round(4), "s_friends_vs_ours.csv")
    hires = by_year.pivot(index="year", columns="institution", values="hired")
    summary = {
        "nits": [{"institution": n, "founded": FOUNDED[n][0], "founded_source": FOUNDED[n][1], "color": COLOR[n],
                  "openalex_id": SOUTH[n]} for n in SOUTH],
        "data_sources": {n: ("our OpenAlex download + NIRF 2025 (friends' cleaned data used as a cross-check)"
                             if n in K.FRIENDS else "our OpenAlex download + NIRF 2025") for n in SOUTH},
        "table": table.round(4).to_dict("records"),
        "by_year": by_year.round(4).to_dict("records"),
        "densification": dens.round(4).to_dict("records"),
        "rolling_exponent": rolling.round(4).to_dict("records"),
        "founding_test": {k: {kk: (round(vv, 4) if isinstance(vv, float) else vv) for kk, vv in v.items()}
                          for k, v in tests.items()},
        "friends_vs_ours": fvo.round(4).to_dict("records"),
        "hires_by_year_2016_2025": hires.loc[FIRST:2025].to_dict("list"),
        "caveats": ["NIRF lists only people working in 2025 (and recent leavers), so the pure-N headcount of earlier "
                    "years misses people who left before ~2022",
                    "faculty are matched to OpenAlex by name (see faculty_matched_pct)",
                    "Puducherry and Andhra Pradesh were downloaded on 18 Nov, the other four on 17 Nov",
                    "Q1 share uses our own journal quartiles; journals we never published in have no quartile "
                    "(see quartile_known_pct)"]}
    K.save_json(summary, "south_summary.json")

    # ---- figure
    fig, ax = plt.subplots(2, 3, figsize=(17, 9))
    for nit in SOUTH:
        d = by_year[(by_year.institution == nit) & (by_year.year < PARTIAL_YEAR)]
        ax[0, 0].plot(d.year, d.papers, "-o", ms=3, color=COLOR[nit], label=nit)
        ax[0, 1].plot(d.year, d.avg_degree_connected, "-o", ms=3, color=COLOR[nit], label=nit)
        ax[0, 2].plot(d.year, d.avg_degree_pure_n, "-o", ms=3, color=COLOR[nit], label=nit)
        a = pick("2016-2026", "connected faculty")[nit]
        ax[1, 0].loglog(d.connected_faculty.replace(0, np.nan), d.links.replace(0, np.nan), "o-", ms=3,
                        color=COLOR[nit], label=f"{nit}: a = {a:.2f}")
        ax[1, 1].bar(np.array(d.year) + 0.13 * (list(SOUTH).index(nit) - 2.5), d.hired, width=0.13, color=COLOR[nit],
                     label=nit)
    t = table.set_index("institution")
    for nit in SOUTH:
        ax[1, 2].scatter(t.hired_2021_2025_pct[nit], t["a_connected_2019-2025"][nit], s=80, color=COLOR[nit])
        ax[1, 2].annotate(nit.replace("NIT ", ""), (t.hired_2021_2025_pct[nit], t["a_connected_2019-2025"][nit]),
                          fontsize=8, xytext=(4, 4), textcoords="offset points")
    ax[0, 0].set_title("Papers per year (OpenAlex)")
    ax[0, 1].set_title("Faculty co-authors per connected faculty member")
    ax[0, 2].set_title("Faculty co-authors per faculty member in post (pure N)")
    ax[1, 0].set_title("Densification: links vs connected faculty")
    ax[1, 1].set_title("Hires per year (current faculty, NIRF 2025)")
    ax[1, 2].set_title("Hired 2021-2025 (% of faculty) vs exponent a (2019-2025)")
    for a_ in ax.flat:
        a_.grid(alpha=0.3)
    for a_ in (ax[0, 0], ax[0, 1], ax[1, 0]):
        a_.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "s_six_nits.png"), dpi=140)
    plt.close(fig)
    pd.set_option("display.width", 260)
    print(table.round(2).T.to_string())
    print(dens.pivot_table(index="institution", columns=["years", "n_definition"], values="exponent_a").round(2).to_string())
    print(json.dumps(summary["founding_test"], indent=1))
    print(fvo.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
