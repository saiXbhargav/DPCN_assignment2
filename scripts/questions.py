"""Research questions for Phase II (items 15-28 of the team list) -> data/analysis/questions/

  python questions.py collab    15 which countries we work with and whether it helps; 16 which partner types help
  python questions.py network   17 key-person risk: how the faculty network breaks when hub faculty leave
  python questions.py people    18 former vs current faculty; 19 how unequal output is (Gini, Lotka);
                                20 who leads the papers (first / last / corresponding author by rank);
                                21 specialists vs generalists
  python questions.py venues    22-23 where to publish (conference vs journal, high-volume venues); 24 open access
  python questions.py richer    25 "rich get richer": preferential attachment in citations
  python questions.py robust    27 how much the main results change without doubtful name matches
  python questions.py inward    26 how much departments cite (and are cited by) their own institute
  python questions.py manipulation  28 citation-manipulation check: heavy citing papers, self-citation, one-person
                                citation sources, and the 40 institutes that cite us most

`python questions.py` runs all parts. Needs data/all_papers.csv (phase2.py papers) and, for venues and richer,
data/raw/works_yearly.jsonl (fetch_insights.py yearly).

Scope (same rule as phase2.py): questions about papers (15, 16, 22-25) use all_papers.csv, which also counts papers
by students and other NIT staff; questions about faculty (17-21, 27) use the faculty data only.

Regressions: ordinary least squares on log(1 + FWCI) with heteroscedasticity-robust (HC1) standard errors, the same
model as network_science.py. It is written here with numpy (no statsmodels needed); `check_regression()` re-fits the
team's model and must give the same coefficients as data/analysis/ns_regression_full.txt.
"""
import collections
import itertools
import json
import math
import os
import re
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import networkx as nx  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import optimize, special, stats  # noqa: E402

from analysis import AXIS, BLUE, GRID, INK, MUTED, ORANGE, SURFACE, h_index, style_axes  # noqa: E402
from fetch_works import INSTITUTIONS, RAW, ROOT  # noqa: E402

DATA = os.path.join(ROOT, "data")
OUT = os.path.join(DATA, "analysis", "questions")
NAME_TO_ID = dict(INSTITUTIONS)
NITS = list(INSTITUTIONS)
COLOR = {"NIT Trichy": BLUE, "NIT Surathkal": ORANGE, "Both": "#6250d6"}
PARTIAL_YEAR = 2026          # data collected in October-November 2026
SEED = 42
RNG = np.random.default_rng(SEED)

COUNTRY = {
    "US": "United States", "GB": "United Kingdom", "KR": "South Korea", "SA": "Saudi Arabia", "MY": "Malaysia",
    "CN": "China", "AU": "Australia", "DE": "Germany", "JP": "Japan", "TW": "Taiwan", "FR": "France",
    "CA": "Canada", "VN": "Vietnam", "IT": "Italy", "AE": "United Arab Emirates", "ET": "Ethiopia",
    "EG": "Egypt", "TH": "Thailand", "SG": "Singapore", "NL": "Netherlands", "IQ": "Iraq", "ES": "Spain",
    "SE": "Sweden", "PL": "Poland", "PT": "Portugal", "IE": "Ireland", "NZ": "New Zealand", "ZA": "South Africa",
    "BD": "Bangladesh", "PK": "Pakistan", "IR": "Iran", "TR": "Turkey", "QA": "Qatar", "OM": "Oman",
    "RU": "Russia", "CH": "Switzerland", "NO": "Norway", "FI": "Finland", "DK": "Denmark", "BE": "Belgium",
    "AT": "Austria", "IL": "Israel", "BR": "Brazil", "MX": "Mexico", "CL": "Chile", "NG": "Nigeria",
    "KE": "Kenya", "LK": "Sri Lanka", "NP": "Nepal", "ID": "Indonesia", "PH": "Philippines", "HK": "Hong Kong",
    "CZ": "Czechia", "HU": "Hungary", "GR": "Greece", "RO": "Romania", "UA": "Ukraine", "KZ": "Kazakhstan",
    "JO": "Jordan", "KW": "Kuwait", "BH": "Bahrain", "MA": "Morocco", "DZ": "Algeria", "TN": "Tunisia",
    "LY": "Libya", "SD": "Sudan", "YE": "Yemen", "LB": "Lebanon", "UZ": "Uzbekistan", "BT": "Bhutan",
    "MV": "Maldives", "MU": "Mauritius", "CO": "Colombia", "AR": "Argentina", "PE": "Peru", "SK": "Slovakia",
    "SI": "Slovenia", "HR": "Croatia", "RS": "Serbia", "LT": "Lithuania", "EE": "Estonia", "LU": "Luxembourg",
    "CY": "Cyprus", "MT": "Malta", "IS": "Iceland", "GH": "Ghana", "TZ": "Tanzania", "UG": "Uganda",
    "RW": "Rwanda", "ZW": "Zimbabwe", "BW": "Botswana", "CM": "Cameroon", "MO": "Macao", "BN": "Brunei",
    "KH": "Cambodia", "MM": "Myanmar", "AF": "Afghanistan", "SY": "Syria", "PS": "Palestine",
}
PARTNER_TYPES = ["IIT", "Other NIT", "IISER / IISc", "IIIT", "Government R&D lab", "Indian university / college",
                 "Indian hospital / medical", "Industry", "Foreign university", "Foreign other"]
GOVT = {"CSIR", "DAE", "ISRO", "DRDO", "ICAR", "ICMR", "Other government R&D"}
RANKS = ["Assistant Professor", "Associate Professor", "Professor", "Professor (HAG)"]


# ================================================================ shared helpers
def short(url):
    return (url or "").rsplit("/", 1)[-1]


def save(df, name, index=False):
    df.to_csv(os.path.join(OUT, name), index=index)


def save_json(obj, name):
    def conv(o):
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            return None if np.isnan(o) else float(o)
        if isinstance(o, (np.bool_,)):
            return bool(o)
        raise TypeError(type(o))
    with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, default=conv)


def savefig(fig, name):
    fig.savefig(os.path.join(OUT, name), dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def raw_works():
    """{(institution name, paper id): work} for every paper in the raw downloads."""
    out = {}
    for name in INSTITUTIONS:
        for line in open(os.path.join(RAW, name.replace(" ", "_") + "_works.jsonl"), encoding="utf-8"):
            w = json.loads(line)
            out[(name, short(w["id"]))] = w
    return out


def ols(df, y, num=(), cat=(), dummies=()):
    """OLS with HC1 robust errors (statsmodels: fit(cov_type="HC1")). `cat` columns become 0/1 dummies with the
    first level (sorted) as the base, like patsy's C(); `dummies` are 0/1 columns used as they are.
    Returns (table with one row per term, number of observations, R2)."""
    cols = [pd.Series(1.0, index=df.index, name="Intercept")]
    for c in cat:
        d = pd.get_dummies(df[c].astype(str), dtype=float)
        d = d[sorted(d.columns)].iloc[:, 1:]
        d.columns = [f"C({c})[T.{v}]" for v in d.columns]
        cols.append(d)
    for c in list(num) + list(dummies):
        cols.append(df[c].astype(float).rename(c))
    X = pd.concat(cols, axis=1)
    keep = X.columns[(X != 0).any()]            # drop dummies that are always 0 in this sample
    X = X[keep]
    Xv, yv = X.values, df[y].astype(float).values
    xtx_inv = np.linalg.pinv(Xv.T @ Xv)
    b = xtx_inv @ Xv.T @ yv
    e = yv - Xv @ b
    n, k = Xv.shape
    meat = (Xv * (e ** 2)[:, None]).T @ Xv
    cov = xtx_inv @ meat @ xtx_inv * n / (n - k)
    se = np.sqrt(np.diag(cov))
    z = b / se
    r2 = 1 - (e ** 2).sum() / ((yv - yv.mean()) ** 2).sum()
    t = pd.DataFrame({"term": X.columns, "coef": b, "se": se, "p_value": 2 * stats.norm.sf(np.abs(z)),
                      "ci_low": b - 1.96 * se, "ci_high": b + 1.96 * se})
    for c in ("coef", "ci_low", "ci_high"):
        t[c.replace("coef", "effect") + "_pct"] = 100 * (np.exp(t[c]) - 1)
    t = t.rename(columns={"effect_pct": "effect_pct", "ci_low_pct": "effect_ci_low_pct",
                          "ci_high_pct": "effect_ci_high_pct"})
    return t.set_index("term"), n, r2


def foreign_flags(ids):
    flags = {}
    for (inst, wid), w in raw_works().items():
        if wid in ids:
            flags[wid] = any(i.get("country_code") not in (None, "IN") for a in w["authorships"]
                             for i in a["institutions"])
    return flags


def faculty_paper_table(g=None):
    """One row per (NIT, faculty paper), with the paper's branch = the department of most of that NIT's faculty
    on it (as in network_science.fair_comparison), and the controls of the team's FWCI model."""
    if g is None:
        g = pd.read_csv(os.path.join(DATA, "group12_data.csv"), low_memory=False)
    d = g.assign(department=g.department.fillna("No branch"))
    br = d.groupby(["institution", "openalex_id"]).department.agg(lambda s: s.mode().iat[0])
    p = g.drop_duplicates(["institution", "openalex_id"]).set_index(["institution", "openalex_id"])
    p["branch"] = br
    p = p.reset_index()
    p["foreign"] = p.openalex_id.map(foreign_flags(set(p.openalex_id))).astype(int)
    p["indian_collab"] = (p.coauthor_institutes.fillna("") != "").astype(int)
    p["conference"] = (p.type == "conference").astype(int)
    p["log_authors"] = np.log(p.n_authors)
    p["surathkal"] = (p.institution == "NIT Surathkal").astype(int)
    p = p[p.fwci.notna()].copy()
    p["log_fwci"] = np.log1p(p.fwci)
    return p


def check_regression():
    """Our numpy OLS must reproduce the team's statsmodels model (ns_regression_full.txt)."""
    p = faculty_paper_table()
    t, n, r2 = ols(p, "log_fwci", num=["log_authors"], cat=["year", "branch"],
                   dummies=["surathkal", "foreign", "indian_collab", "conference"])
    ref = {}
    for line in open(os.path.join(DATA, "analysis", "ns_regression_full.txt"), encoding="utf-8"):
        m = re.match(r"^(surathkal|foreign|indian_collab|conference|log_authors)\s+(-?[\d.]+)\s+([\d.]+)", line)
        if m:
            ref[m.group(1)] = (float(m.group(2)), float(m.group(3)))
    assert len(ref) == 5, ref
    for v, (coef, se) in ref.items():
        assert abs(t.loc[v, "coef"] - coef) < 6e-4 and abs(t.loc[v, "se"] - se) < 6e-4, (v, t.loc[v], coef, se)
    assert n == 18342, n
    print(f"  regression check passed: {n} papers, coefficients and robust errors match ns_regression_full.txt")


def load_insts(works):
    """Institution records for clusters.cluster_of: data/raw/institutions.jsonl, plus every institution seen in
    the raw works (name, OpenAlex type and parents) for those not in that file."""
    from clusters import load_institutions
    insts = load_institutions()
    for w in works.values():
        for a in w["authorships"]:
            for i in a["institutions"]:
                iid = short(i["id"])
                if iid not in insts:
                    insts[iid] = {"id": iid, "name": i.get("display_name") or "", "type": i.get("type"),
                                  "country": i.get("country_code"),
                                  "lineage": [short(x) for x in i.get("lineage") or []]}
    return insts


def partner_type(iid, rec, insts):
    from clusters import cluster_of
    cc = rec.get("country_code")
    typ = rec.get("type")
    if typ == "company":
        return "Industry"
    if cc and cc != "IN":
        return "Foreign university" if typ == "education" else "Foreign other"
    name = rec.get("display_name") or insts.get(iid, {}).get("name", "")
    if iid in NAME_TO_ID.values() or re.search(r"National Institute of Technology", name, re.I):  # also "Of"
        return "Other NIT"
    c = cluster_of(iid, name, insts)
    return {"IIT": "IIT", "NIT": "Other NIT", "IISER / IISc": "IISER / IISc", "IIIT": "IIIT",
            "University / college": "Indian university / college", "Hospital / medical": "Indian hospital / medical",
            "Industry": "Industry"}.get(c, "Government R&D lab" if c in GOVT else "Indian university / college")


_PAPERS = None


def papers():
    """all_papers.csv (one row per NIT and paper) plus, from the raw works: foreign countries, partner types,
    Indian partners; and from works_yearly.jsonl (if downloaded): open-access status and citations per year."""
    global _PAPERS
    if _PAPERS is not None:
        return _PAPERS
    ap = pd.read_csv(os.path.join(DATA, "all_papers.csv"), low_memory=False)
    works = raw_works()
    insts = load_insts(works)
    countries, types = [], []
    for r in ap.itertuples(index=False):
        w = works[(r.institution, r.openalex_id)]
        own = NAME_TO_ID[r.institution]
        cs, ts = set(), set()
        for a in w["authorships"]:
            for i in a["institutions"]:
                iid = short(i["id"])
                if iid == own:
                    continue
                cc = i.get("country_code")
                if cc and cc != "IN":
                    cs.add(cc)
                if cc or i.get("type") == "company":
                    ts.add(partner_type(iid, i, insts))
        countries.append(sorted(cs))
        types.append(sorted(ts))
    ap["countries"] = countries
    ap["partner_types"] = types
    ap["foreign"] = ap.countries.str.len().gt(0).astype(int)
    assert (ap.foreign == (ap.n_foreign_partners > 0)).all(), "foreign flag differs from all_papers.csv"
    ap["indian_collab"] = (ap.n_indian_partners > 0).astype(int)
    ap["conference"] = (ap.type == "conference").astype(int)
    ap["log_authors"] = np.log(ap.n_authors)
    ap["surathkal"] = (ap.institution == "NIT Surathkal").astype(int)
    ap["log_fwci"] = np.log1p(ap.fwci)
    ap["field"] = ap.field.fillna("Unknown")
    yp = os.path.join(RAW, "works_yearly.jsonl")
    if os.path.exists(yp):
        y = {r["id"]: r for r in map(json.loads, open(yp, encoding="utf-8"))}
        ap["oa_status"] = ap.openalex_id.map(lambda i: (y.get(i) or {}).get("oa_status"))
        ap["cites_now"] = ap.openalex_id.map(lambda i: (y.get(i) or {}).get("cited_by_count"))
        ap["counts_by_year"] = ap.openalex_id.map(lambda i: (y.get(i) or {}).get("counts_by_year") or {})
    _PAPERS = ap
    return ap


def controls_fit(df, extra_dummies, cat_extra=()):
    """Team model for all papers: log(1+FWCI) ~ year + field + NIT + venue type + team size + the given 0/1 terms."""
    d = df[df.fwci.notna()]
    return ols(d, "log_fwci", num=["log_authors"], cat=["year", "field", *cat_extra],
               dummies=["surathkal", "conference", *extra_dummies])


def term_rows(t, terms, labels=None):
    rows = []
    for v in terms:
        if v not in t.index:
            continue
        r = t.loc[v]
        rows.append({"term": (labels or {}).get(v, v), "coefficient": r.coef, "effect_pct": r.effect_pct,
                     "ci_low_pct": r.effect_ci_low_pct, "ci_high_pct": r.effect_ci_high_pct, "p_value": r.p_value})
    return pd.DataFrame(rows)


def unique(p):
    """One row per paper (both NITs together): papers with authors from both NITs are counted once."""
    return p.drop_duplicates("openalex_id")


# ================================================================ part "collab": questions 15 and 16
def collab_part():
    check_regression()
    p = papers()
    summary = {}

    # ---- 15. countries
    u = unique(p)
    ex = u[["openalex_id", "year", "fwci", "top10pct", "countries"]].explode("countries").dropna(subset=["countries"])
    per_nit = p[["institution", "openalex_id", "countries"]].explode("countries").dropna(subset=["countries"])
    full = range(2016, PARTIAL_YEAR)
    tab = ex.groupby("countries").agg(papers=("openalex_id", "nunique"), mean_fwci=("fwci", "mean"),
                                      top10_share=("top10pct", lambda s: s.astype(float).mean()))
    for nit in NITS:
        tab[f"papers_{nit.split()[1].lower()}"] = per_nit[per_nit.institution == nit].groupby("countries").size()
    early = ex[ex.year.between(2016, 2020)].groupby("countries").size()
    late = ex[ex.year.between(2021, 2025)].groupby("countries").size()
    tab["papers_2016_2020"], tab["papers_2021_2025"] = early, late
    tab = tab.fillna(0).sort_values("papers", ascending=False)
    # is a country link one research group? the NIT faculty member on most of that country's papers
    g = pd.read_csv(os.path.join(DATA, "group12_data.csv"), usecols=["institution", "openalex_id", "author"])
    fx = per_nit.merge(g, on=["institution", "openalex_id"]).drop_duplicates(["countries", "openalex_id", "author"])
    top = fx.groupby(["countries", "author"]).openalex_id.nunique().reset_index().sort_values(
        "openalex_id", ascending=False).drop_duplicates("countries").set_index("countries")
    tab["top_faculty"] = top.author
    tab["top_faculty_share"] = top.openalex_id / tab.papers
    tab.insert(0, "country", [COUNTRY.get(c, c) for c in tab.index])
    n_foreign = int(u.foreign.sum())
    tab["share_of_foreign_papers"] = tab.papers / n_foreign

    big = [c for c in tab.index if tab.loc[c, "papers"] >= 100]
    d = p.copy()
    for c in big:
        d[f"cc_{c}"] = d.countries.apply(lambda cs, c=c: int(c in cs))
    d["cc_other"] = d.countries.apply(lambda cs: int(bool(set(cs) - set(big))))
    t_base, n_base, _ = controls_fit(d, ["foreign", "indian_collab"])
    t_cty, n_cty, _ = controls_fit(d, [f"cc_{c}" for c in big] + ["cc_other", "indian_collab"])
    eff = term_rows(t_cty, [f"cc_{c}" for c in big])
    eff["country_code"] = [c.split("_")[1] for c in eff.term]
    tab = tab.join(eff.set_index("country_code")[["effect_pct", "ci_low_pct", "ci_high_pct", "p_value"]])
    tab.index.name = "country_code"
    save(tab.reset_index().round(4), "q15_countries.csv")

    by_year = p.groupby(["institution", "year"]).agg(papers=("openalex_id", "size"), foreign_share=("foreign", "mean"),
                                                     countries=("countries", lambda s: len(set().union(*map(set, s)))))
    by_year = by_year.reset_index()
    ub = u.groupby("year").agg(papers=("openalex_id", "size"), foreign_share=("foreign", "mean"),
                               countries=("countries", lambda s: len(set().union(*map(set, s))))).reset_index()
    ub.insert(0, "institution", "Both")
    by_year = pd.concat([by_year, ub])
    top8 = list(tab.index[:8])
    for c in top8:
        cnt = ex[ex.countries == c].groupby("year").size()
        by_year[f"papers_with_{c}"] = np.where(by_year.institution == "Both", by_year.year.map(cnt).fillna(0), np.nan)
    save(by_year.round(4), "q15_foreign_by_year.csv")

    # with vs without a foreign co-author, raw and adjusted, all papers and faculty papers
    rows = []
    for scope, s in (("all papers", p), ("faculty papers", p[p.has_faculty_author])):
        t, n, _ = controls_fit(s, ["foreign", "indian_collab"])
        f = s[s.fwci.notna()]
        rows.append({"scope": scope, "papers": len(f), "foreign_share": f.foreign.mean(),
                     "mean_fwci_with": f[f.foreign == 1].fwci.mean(), "mean_fwci_without": f[f.foreign == 0].fwci.mean(),
                     "top10_with": f[f.foreign == 1].top10pct.astype(float).mean(),
                     "top10_without": f[f.foreign == 0].top10pct.astype(float).mean(),
                     "adjusted_effect_pct": t.loc["foreign", "effect_pct"],
                     "ci_low_pct": t.loc["foreign", "effect_ci_low_pct"],
                     "ci_high_pct": t.loc["foreign", "effect_ci_high_pct"], "p_value": t.loc["foreign", "p_value"]})
    # more countries on the paper
    d["n_countries"] = d.countries.str.len()
    d["one_country"] = (d.n_countries == 1).astype(int)
    d["two_plus_countries"] = (d.n_countries >= 2).astype(int)
    t_n, _, _ = controls_fit(d, ["one_country", "two_plus_countries", "indian_collab"])
    wf = pd.DataFrame(rows)
    save(wf.round(4), "q15_foreign_effect.csv")
    save(term_rows(t_n, ["one_country", "two_plus_countries", "indian_collab"]).round(4),
         "q15_effect_by_number_of_countries.csv")
    summary["q15"] = {
        "papers_all": len(u), "papers_with_foreign_coauthor": n_foreign, "foreign_share": n_foreign / len(u),
        "countries": int(len(tab)), "countries_with_100_plus_papers": big,
        "top5": tab.head(5)[["country", "papers"]].reset_index().to_dict("records"),
        "foreign_effect_all_papers_pct": wf.iloc[0].adjusted_effect_pct,
        "foreign_effect_faculty_papers_pct": wf.iloc[1].adjusted_effect_pct,
        "foreign_share_2016": ub.set_index("year").foreign_share.get(2016),
        "foreign_share_2025": ub.set_index("year").foreign_share.get(2025),
        "regression_papers": n_base,
        "best_country": eff.sort_values("effect_pct", ascending=False).head(3)[["term", "effect_pct"]].to_dict("records"),
        "worst_country": eff.sort_values("effect_pct").head(3)[["term", "effect_pct"]].to_dict("records"),
    }

    # chart: top 15 countries (papers) and the adjusted FWCI effect of the countries with 100+ papers
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.6))
    t15 = tab.head(15).iloc[::-1]
    ax = axes[0]
    ax.barh(t15.country, t15.papers_trichy, color=BLUE, label="NIT Trichy", height=0.7)
    ax.barh(t15.country, t15.papers_surathkal, left=t15.papers_trichy, color=ORANGE, label="NIT Surathkal", height=0.7)
    ax.set_xlabel("papers with a co-author from this country"); ax.legend(frameon=False, fontsize=9)
    ax.set_title("Top 15 partner countries, 2016-2026", fontsize=11, loc="left", color=INK)
    style_axes(ax); ax.grid(axis="x", color=GRID); ax.grid(axis="y", visible=False)
    ax = axes[1]
    e = tab.loc[big].sort_values("effect_pct")
    ax.errorbar(e.effect_pct, e.country, xerr=[e.effect_pct - e.ci_low_pct, e.ci_high_pct - e.effect_pct],
                fmt="o", color=INK, ecolor=MUTED, capsize=3, ms=6)
    ax.axvline(0, color=AXIS, lw=1)
    ax.set_xlabel("FWCI difference vs papers without that country (%, adjusted)")
    ax.set_title("Does the partner country matter? (95% CI)", fontsize=11, loc="left", color=INK)
    style_axes(ax); ax.grid(axis="x", color=GRID); ax.grid(axis="y", visible=False)
    savefig(fig, "q15_countries.png")

    # ---- 16. partner types
    for ty in PARTNER_TYPES:
        p[f"pt_{ty}"] = p.partner_types.apply(lambda ts, ty=ty: int(ty in ts))
    p["no_partner"] = p.partner_types.str.len().eq(0).astype(int)
    terms = [f"pt_{ty}" for ty in PARTNER_TYPES]
    t16, n16, _ = controls_fit(p, terms)
    eff16 = term_rows(t16, terms, {f"pt_{ty}": ty for ty in PARTNER_TYPES}).set_index("term")
    rows = []
    u = unique(p)
    for ty in PARTNER_TYPES + ["no_partner"]:
        col = f"pt_{ty}" if ty != "no_partner" else "no_partner"
        s = u[u[col] == 1]
        r = {"partner_type": ty if ty != "no_partner" else "No outside partner", "papers": len(s),
             "share_of_papers": len(s) / len(u), "mean_fwci": s.fwci.mean(), "median_fwci": s.fwci.median(),
             "top10_share": s.top10pct.astype(float).mean()}
        for nit in NITS:
            r[f"papers_{nit.split()[1].lower()}"] = int(p[(p.institution == nit) & (p[col] == 1)].shape[0])
        if ty in eff16.index:
            r.update(eff16.loc[ty, ["effect_pct", "ci_low_pct", "ci_high_pct", "p_value"]].to_dict())
        rows.append(r)
    pt = pd.DataFrame(rows)
    save(pt.round(4), "q16_partner_types.csv")
    # trend: share of papers with each partner type, by year (both NITs)
    tr = u.groupby("year")[[f"pt_{ty}" for ty in PARTNER_TYPES] + ["no_partner"]].mean()
    tr.columns = PARTNER_TYPES + ["No outside partner"]
    save(tr.reset_index().round(4), "q16_partner_types_by_year.csv")
    summary["q16"] = {"regression_papers": n16,
                      "effects": pt.dropna(subset=["effect_pct"])[["partner_type", "papers", "effect_pct",
                                                                    "ci_low_pct", "ci_high_pct", "p_value"]]
                      .to_dict("records"),
                      "no_partner_share": float(pt.set_index("partner_type").loc["No outside partner", "share_of_papers"])}

    fig, ax = plt.subplots(figsize=(9, 5.2))
    e = pt.dropna(subset=["effect_pct"]).sort_values("effect_pct")
    ax.errorbar(e.effect_pct, [f"{a} ({b:,})" for a, b in zip(e.partner_type, e.papers)],
                xerr=[e.effect_pct - e.ci_low_pct, e.ci_high_pct - e.effect_pct], fmt="o", color=INK,
                ecolor=MUTED, capsize=3, ms=6)
    ax.axvline(0, color=AXIS, lw=1)
    ax.set_xlabel("FWCI difference when this partner type is on the paper (%, adjusted; papers in brackets)")
    ax.set_title("Which partners go with higher impact? (95% CI)", fontsize=11, loc="left", color=INK)
    style_axes(ax); ax.grid(axis="x", color=GRID); ax.grid(axis="y", visible=False)
    savefig(fig, "q16_partner_types.png")
    save_json(summary, "collab_summary.json")
    print(json.dumps(summary, indent=1, default=str)[:3000])


# ================================================================ part "network": question 17
def faculty_graph():
    """The faculty co-authorship graph (same as network_science.faculty_graph): every faculty member with papers,
    linked when they share a paper (same-NIT and NIT-NIT links), weight = joint papers."""
    am = pd.read_csv(os.path.join(DATA, "network_metrics", "author_metrics.csv"))
    fac = pd.read_csv(os.path.join(DATA, "faculty.csv")).set_index("faculty_id")
    fac[["department", "designation"]] = fac[["department", "designation"]].fillna("")
    au = pd.read_csv(os.path.join(DATA, "authorship_network.csv"), low_memory=False)
    nit = au[au.edge_category.isin(["same_nit", "nit_nit"])]
    G = nx.Graph()
    for r in am.itertuples(index=False):
        G.add_node(r.author_id, institution=r.institution.split(";")[0], name=r.author,
                   department=fac.department.get(r.author_id, ""), designation=fac.designation.get(r.author_id, ""),
                   status=fac.status.get(r.author_id, ""))
    for (a, b), n in nit.groupby(["author_a_id", "author_b_id"]).paper_id.nunique().items():
        G.add_edge(a, b, weight=int(n))
    return G


def connected_pairs(G):
    return sum(len(c) * (len(c) - 1) // 2 for c in nx.connected_components(G))


def giant(G):
    return max((len(c) for c in nx.connected_components(G)), default=0)


def attack(G, how, steps, seed=None):
    """Remove `steps` nodes one by one; return giant-component size and connected pairs after each removal.
    'betweenness' and 'degree' are recomputed after every removal (adaptive attack)."""
    H = G.copy()
    rng = np.random.default_rng(seed)
    order = list(rng.permutation(sorted(H.nodes))) if how == "random" else None   # sorted: same order every run
    gc, cp, removed = [giant(H)], [connected_pairs(H)], []
    for k in range(steps):
        if how == "random":
            v = order[k]
        elif how == "degree":
            v = max(H.degree, key=lambda x: (x[1], str(x[0])))[0]
        else:
            b = nx.betweenness_centrality(H)
            v = max(b, key=lambda x: (b[x], str(x)))
        H.remove_node(v)
        removed.append(v)
        gc.append(giant(H))
        cp.append(connected_pairs(H))
    return gc, cp, removed


def network_part():
    G = faculty_graph()
    au = pd.read_csv(os.path.join(DATA, "network_metrics", "author_metrics.csv"))
    assert G.number_of_nodes() == len(au)
    summary, curves, key_rows = {}, [], []
    for view in NITS + ["Both"]:
        H = G if view == "Both" else G.subgraph([n for n, d in G.nodes(data=True) if d["institution"] == view]).copy()
        N = H.number_of_nodes()
        steps = int(round(0.10 * N))
        gc0, cp0 = giant(H), connected_pairs(H)
        res = {}
        for how in ("betweenness", "degree"):
            gc, cp, removed = attack(H, how, steps)
            res[how] = (gc, cp)
            if how == "betweenness":
                first = removed[:10]
        assert res["betweenness"][0][0] == gc0
        rgc, rcp = np.zeros(steps + 1), np.zeros(steps + 1)
        for s in range(100):
            gc, cp, _ = attack(H, "random", steps, seed=SEED + s)
            rgc += np.array(gc) / 100
            rcp += np.array(cp) / 100
        res["random (mean of 100)"] = (rgc, rcp)
        for how, (gc, cp) in res.items():
            for k in range(steps + 1):
                curves.append({"institution": view, "strategy": how, "removed": k, "removed_share": k / N,
                               "giant_component": gc[k], "giant_share": gc[k] / N, "connected_pairs": cp[k],
                               "connected_pairs_share": cp[k] / cp0 if cp0 else np.nan})
        def at(how, k):
            return 1 - res[how][1][k] / cp0
        summary[view] = {"faculty": N, "links": H.number_of_edges(), "giant_component": gc0, "giant_share": gc0 / N,
                         "connected_pairs": cp0,
                         "pairs_lost_top5_bridges": at("betweenness", 5), "pairs_lost_top10_bridges": at("betweenness", 10),
                         "pairs_lost_top20_bridges": at("betweenness", min(20, steps)),
                         "pairs_lost_10_random": at("random (mean of 100)", 10),
                         "pairs_lost_20_random": at("random (mean of 100)", min(20, steps)),
                         "pairs_lost_top10_degree": at("degree", 10),
                         "first_10_bridges_removed": [G.nodes[v]["name"] for v in first]}
    curves = pd.DataFrame(curves)
    save(curves.round(5), "q17_robustness_curves.csv")

    # single-person removal: how many pairs of faculty can no longer reach each other?
    base = connected_pairs(G)
    btw = nx.betweenness_centrality(G)
    for v, d in G.nodes(data=True):
        if G.degree(v) == 0:
            continue
        H = G.copy(); H.remove_node(v)
        lost = base - connected_pairs(H) - (len(nx.node_connected_component(G, v)) - 1)  # pairs among the others
        key_rows.append({"faculty_id": v, "name": d["name"], "institution": d["institution"],
                         "department": d["department"], "designation": d["designation"], "status": d["status"],
                         "co_authors": G.degree(v), "betweenness": btw[v],
                         "pairs_cut_between_others": lost, "pairs_cut_share": lost / base,
                         "components_after": nx.number_connected_components(H) - (nx.number_connected_components(G) - 1)})
    key = pd.DataFrame(key_rows).sort_values("pairs_cut_between_others", ascending=False)
    save(key.head(40).round(5), "q17_key_people_overall.csv")

    # per department: inside the department's own collaboration network, who holds it together?
    dep_rows = []
    for (inst, dep), nodes in pd.Series({n: (d["institution"], d["department"]) for n, d in G.nodes(data=True)}) \
            .groupby(lambda n: (G.nodes[n]["institution"], G.nodes[n]["department"])):
        nodes = list(nodes.index)
        if len(nodes) < 6 or not dep:
            continue
        D = G.subgraph(nodes).copy()
        cp0 = connected_pairs(D)
        if cp0 == 0:
            continue
        best = None
        for v in sorted(D.nodes):          # sorted, so ties are broken the same way every run
            H = D.copy(); H.remove_node(v)
            lost = cp0 - connected_pairs(H) - (len(nx.node_connected_component(D, v)) - 1)
            if best is None or lost > best[1]:
                best = (v, lost)
        v, lost = best
        dep_rows.append({"institution": inst, "department": dep, "faculty_with_papers": len(nodes),
                         "links_inside_department": D.number_of_edges(), "isolated_faculty": sum(1 for n in D if D.degree(n) == 0),
                         "largest_group_share": giant(D) / len(nodes), "connected_pairs": cp0,
                         "key_person": G.nodes[v]["name"], "key_person_designation": G.nodes[v]["designation"],
                         "key_person_status": G.nodes[v]["status"], "key_person_links": D.degree(v),
                         "pairs_cut_if_key_person_leaves": lost, "pairs_cut_share": lost / cp0,
                         "articulation_points": len(list(nx.articulation_points(D)))})
    dep = pd.DataFrame(dep_rows).sort_values("pairs_cut_share", ascending=False)
    save(dep.round(4), "q17_key_people_by_department.csv")
    top20 = key.head(20)
    summary["top20_key_people_by_designation"] = top20.designation.value_counts().to_dict()
    summary["top20_key_people_by_status"] = top20.status.value_counts().to_dict()
    summary["top5_key_people"] = top20.head(5)[["name", "institution", "department", "designation",
                                                "pairs_cut_share"]].to_dict("records")
    summary["departments"] = len(dep)
    summary["departments_where_one_person_cuts_over_25pct"] = int((dep.pairs_cut_share > 0.25).sum())
    save_json(summary, "network_summary.json")

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.4), sharey=True)
    styles = {"betweenness": (INK, "-"), "degree": (MUTED, "--"), "random (mean of 100)": (AXIS, "-")}
    for ax, view in zip(axes, NITS + ["Both"]):
        c = curves[curves.institution == view]
        for how, (col, ls) in styles.items():
            s = c[c.strategy == how]
            ax.plot(100 * s.removed_share, 100 * s.connected_pairs_share, color=col if how != "betweenness" else COLOR[view],
                    ls=ls, lw=2, label=f"remove by {how}" if how != "random (mean of 100)" else "remove at random")
        ax.set_title(view, fontsize=11, loc="left", color=INK)
        ax.set_xlabel("faculty removed (%)")
        style_axes(ax)
    axes[0].set_ylabel("pairs of faculty still connected (%)")
    axes[0].legend(frameon=False, fontsize=9)
    savefig(fig, "q17_robustness.png")
    print(json.dumps(summary, indent=1, default=str)[:3000])
    print(dep.head(10).to_string())


# ================================================================ part "people": questions 18-21
def gini(x):
    x = np.sort(np.asarray(x, dtype=float))
    n = len(x)
    if n == 0 or x.sum() == 0:
        return np.nan
    return (2 * np.sum(np.arange(1, n + 1) * x)) / (n * x.sum()) - (n + 1) / n


def top_share(x, q):
    x = np.sort(np.asarray(x, dtype=float))[::-1]
    k = max(1, int(round(q * len(x))))
    return x[:k].sum() / x.sum() if x.sum() else np.nan


def lotka(counts):
    """Lotka's law: the number of authors with n papers ~ n^-a. Maximum-likelihood fit of a discrete power law
    from n = 1 (zeta distribution), and the classic least-squares fit on log-log counts."""
    x = np.asarray(counts, dtype=float)
    x = x[x >= 1]
    sl = np.log(x).sum()
    res = optimize.minimize_scalar(lambda a: len(x) * np.log(special.zeta(a, 1)) + a * sl, bounds=(1.01, 6),
                                   method="bounded")
    vc = pd.Series(x).value_counts().sort_index()
    vc = vc[vc.index <= 30]
    slope = np.polyfit(np.log(vc.index.values), np.log(vc.values), 1)[0]
    return {"authors": len(x), "exponent_mle": res.x, "exponent_least_squares": -slope,
            "share_with_one_paper": (x == 1).mean(),
            "lotka_predicted_share_one_paper": 1 / special.zeta(res.x, 1)}


def faculty_paper_rows():
    g = pd.read_csv(os.path.join(DATA, "group12_data.csv"), low_memory=False)
    return g, g.drop_duplicates(["faculty_id", "openalex_id"]).copy()


def people_part():
    g, fp = faculty_paper_rows()
    fac = pd.read_csv(os.path.join(DATA, "faculty.csv")).drop_duplicates("faculty_id").set_index("faculty_id")
    am = pd.read_csv(os.path.join(DATA, "network_metrics", "author_metrics.csv")).set_index("author_id")
    summary = {}
    fflag = foreign_flags(set(fp.openalex_id))
    fp["foreign"] = fp.openalex_id.map(fflag)
    per = fp.groupby("faculty_id").agg(papers=("openalex_id", "size"), citations=("citations", "sum"),
                                       h_index=("citations", h_index), mean_fwci=("fwci", "mean"),
                                       median_fwci=("fwci", "median"),
                                       q1_share=("quartile", lambda s: (s == "Q1").mean()),
                                       foreign_share=("foreign", "mean"),
                                       conference_share=("type", lambda s: (s == "conference").mean()))
    assert (per.papers == fac.papers.reindex(per.index)).all(), "paper counts differ from faculty.csv"
    per = per.join(fac[["author", "institution", "department", "designation", "status", "first_seen", "last_seen",
                        "openalex_ids"]])
    per = per.join(am[["degree", "betweenness_centrality", "indian_partner_institutes"]])
    per["years_on_roster"] = per.last_seen.clip(upper=PARTIAL_YEAR) - per.first_seen.clip(lower=2016) + 1
    per["papers_per_year"] = per.papers / per.years_on_roster
    per["citations_per_paper"] = per.citations / per.papers

    # ---- 18. former vs current
    measures = {"papers_per_year": "papers per year on the faculty list", "citations_per_paper": "citations per paper",
                "mean_fwci": "mean FWCI", "h_index": "h-index (2016-2026)", "q1_share": "share of papers in Q1",
                "foreign_share": "share with a foreign co-author", "degree": "NIT faculty co-authors",
                "betweenness_centrality": "betweenness", "indian_partner_institutes": "Indian partner institutes",
                "years_on_roster": "years on the faculty list"}
    rows = []
    for grp, d in [("all ranks", per)] + [(r, per[per.designation == r]) for r in RANKS]:
        cur, form = d[d.status == "current"], d[d.status == "former"]
        if len(form) < 5:
            continue
        for m, label in measures.items():
            a, b = cur[m].dropna(), form[m].dropna()
            rows.append({"group": grp, "measure": label, "current_n": len(a), "former_n": len(b),
                         "current_median": a.median(), "former_median": b.median(),
                         "current_mean": a.mean(), "former_mean": b.mean(),
                         "p_value": stats.mannwhitneyu(a, b).pvalue if len(a) and len(b) else np.nan})
    cmp_ = pd.DataFrame(rows)
    save(cmp_.round(4), "q18_former_vs_current.csv")
    # where did former faculty go? (OpenAlex last known institution of their profile with most papers)
    profiles = {}
    for fn in ("authors.jsonl", "authors_extra.jsonl"):
        path = os.path.join(RAW, fn)
        if os.path.exists(path):
            for line in open(path, encoding="utf-8"):
                r = json.loads(line)
                profiles[short(r["id"])] = r
    works = raw_works()
    insts = load_insts(works)
    where = []
    for fid, r in per[per.status == "former"].iterrows():
        cands = [profiles[i] for i in str(r.openalex_ids).split(";") if i in profiles]
        if not cands:
            where.append({"faculty_id": fid, "author": r.author, "institution": r.institution,
                          "department": r.department, "designation": r.designation, "last_seen": r.last_seen,
                          "now_at": "", "now_type": "No OpenAlex profile"})
            continue
        best = max(cands, key=lambda c: c.get("works_count") or 0)
        lki = best.get("last_known_institutions") or []
        if not lki:
            now, typ = "", "No current institution listed"
        else:
            i = lki[0]
            iid = short(i["id"])
            now = i.get("display_name")
            if iid == NAME_TO_ID[r.institution]:
                typ = "Still listed at the same NIT"
            else:
                typ = partner_type(iid, i, insts)
                typ = {"Other NIT": "Another NIT", "Foreign other": "Abroad (other)", "Foreign university": "Abroad (university)"}.get(typ, typ)
        where.append({"faculty_id": fid, "author": r.author, "institution": r.institution, "department": r.department,
                      "designation": r.designation, "last_seen": r.last_seen, "now_at": now, "now_type": typ})
    where = pd.DataFrame(where)
    save(where, "q18_where_former_faculty_went.csv")
    summary["q18"] = {"current_with_papers": int((per.status == "current").sum()),
                      "former_with_papers": int((per.status == "former").sum()),
                      "where_former_went": where.now_type.value_counts().to_dict(),
                      "former_by_rank": per[per.status == "former"].designation.value_counts().to_dict(),
                      "headline": cmp_[cmp_.group == "all ranks"][["measure", "current_median", "former_median",
                                                                    "p_value"]].to_dict("records")}

    # ---- 19. inequality
    allfac = fac[["institution", "department", "papers"]].copy()     # all 767, including faculty with no papers
    allfac["citations"] = per.citations.reindex(allfac.index).fillna(0)
    rows = []
    for scope, d in (("faculty with papers", per), ("all faculty (including 0 papers)", allfac)):
        for view in NITS + ["Both"]:
            s = d if view == "Both" else d[d.institution == view]
            for m in ("papers", "citations"):
                rows.append({"scope": scope, "institution": view, "measure": m, "faculty": len(s), "gini": gini(s[m]),
                             "top10pct_share": top_share(s[m], 0.10), "top20pct_share": top_share(s[m], 0.20),
                             "bottom50pct_share": 1 - top_share(s[m], 0.50)})
    ineq = pd.DataFrame(rows)
    # manual check of the Gini formula on one series
    x = per.papers.values.astype(float)
    pair = np.abs(x[:, None] - x[None, :]).sum() / (2 * len(x) ** 2 * x.mean())
    assert abs(pair - gini(x)) < 1e-9
    save(ineq.round(4), "q19_inequality.csv")
    drows = []
    for (inst, dep), s in per.groupby(["institution", "department"]):
        if len(s) < 8:
            continue
        drows.append({"institution": inst, "department": dep, "faculty_with_papers": len(s),
                      "gini_papers": gini(s.papers), "gini_citations": gini(s.citations),
                      "top10pct_share_citations": top_share(s.citations, 0.10),
                      "top_person": s.loc[s.citations.idxmax(), "author"],
                      "top_person_share_citations": s.citations.max() / s.citations.sum()})
    dineq = pd.DataFrame(drows).sort_values("gini_citations", ascending=False)
    save(dineq.round(4), "q19_inequality_by_department.csv")
    lor = []
    for view in NITS + ["Both"]:
        s = per if view == "Both" else per[per.institution == view]
        for m in ("papers", "citations"):
            v = np.sort(s[m].values.astype(float))
            cum = np.concatenate([[0], np.cumsum(v) / v.sum()])
            for q in np.linspace(0, 1, 51):
                lor.append({"institution": view, "measure": m, "faculty_share": q,
                            "output_share": float(np.interp(q, np.linspace(0, 1, len(cum)), cum))})
    save(pd.DataFrame(lor).round(4), "q19_lorenz.csv")
    # Lotka's law: faculty, and every author with an NIT affiliation on our papers (students included)
    ap = pd.read_csv(os.path.join(DATA, "all_papers.csv"), usecols=["institution", "openalex_id"])
    keep = set(zip(ap.institution, ap.openalex_id))
    # count each author once per paper (an author on a joint Trichy-Surathkal paper counts once)
    seen = collections.defaultdict(set)
    for (inst, wid), w in works.items():
        if (inst, wid) not in keep:
            continue
        for a in w["authorships"]:
            if any(short(i["id"]) == NAME_TO_ID[inst] for i in a["institutions"]) and a["author"].get("id"):
                seen[short(a["author"]["id"])].add(wid)
    lot = pd.DataFrame([{"group": "faculty (2016-2026 papers)", **lotka(per.papers)},
                        {"group": "all NIT-affiliated authors incl. students (OpenAlex author IDs)",
                         **lotka([len(v) for v in seen.values()])}])
    save(lot.round(4), "q19_lotka.csv")
    b = ineq[(ineq.scope == "faculty with papers") & (ineq.institution == "Both")].set_index("measure")
    summary["q19"] = {"gini_papers": b.loc["papers", "gini"], "gini_citations": b.loc["citations", "gini"],
                      "top10_share_papers": b.loc["papers", "top10pct_share"],
                      "top10_share_citations": b.loc["citations", "top10pct_share"],
                      "bottom50_share_citations": b.loc["citations", "bottom50pct_share"],
                      "by_nit": ineq[(ineq.scope == "faculty with papers") & (ineq.institution != "Both")]
                      [["institution", "measure", "gini", "top10pct_share"]].to_dict("records"),
                      "lotka": lot.to_dict("records"),
                      "most_unequal_departments": dineq.head(5)[["institution", "department", "gini_citations",
                                                                 "top_person", "top_person_share_citations"]]
                      .to_dict("records"),
                      "most_equal_departments": dineq.tail(5)[["institution", "department", "gini_citations"]]
                      .to_dict("records")}

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    L = pd.DataFrame(lor)
    for ax, m in zip(axes, ("papers", "citations")):
        for view in NITS:
            s = L[(L.institution == view) & (L.measure == m)]
            ax.plot(100 * s.faculty_share, 100 * s.output_share, color=COLOR[view], lw=2, label=view)
        ax.plot([0, 100], [0, 100], color=AXIS, lw=1, ls="--", label="perfect equality")
        ax.set_xlabel("faculty, from least to most productive (%)")
        ax.set_ylabel(f"share of all {m} (%)")
        g_ = ineq[(ineq.scope == "faculty with papers") & (ineq.measure == m)].set_index("institution").gini
        ax.set_title(f"{m.capitalize()}: Gini {g_['NIT Trichy']:.2f} (Trichy), {g_['NIT Surathkal']:.2f} (Surathkal)",
                     fontsize=11, loc="left", color=INK)
        style_axes(ax)
    axes[0].legend(frameon=False, fontsize=9)
    savefig(fig, "q19_lorenz.png")

    # ---- 20. who leads the papers?
    roles = []
    for r in fp.itertuples(index=False):
        w = works.get((r.institution, r.openalex_id))
        # group12_data.author_position is the index of this faculty member in the paper's author list
        au = w["authorships"][int(r.author_position)] if w and 0 <= r.author_position < len(w["authorships"]) else None
        if au is not None and isinstance(r.author_id, str) and short(au["author"].get("id")) != r.author_id:
            au = None
        if au is None:
            roles.append((None, None, None))
            continue
        any_corr = any(a.get("is_corresponding") for a in w["authorships"])
        pos = au.get("author_position")
        role = "sole" if r.n_authors == 1 else {"first": "first", "last": "last"}.get(pos, "middle")
        roles.append((role, bool(au.get("is_corresponding")), any_corr))
    fp[["role", "corresponding", "paper_has_corresponding"]] = pd.DataFrame(roles, index=fp.index)
    matched = fp.role.notna().mean()
    assert matched > 0.99, f"only {matched:.3f} of faculty-paper rows found in the raw authorships"
    fp["rank"] = np.where(fp.designation.isin(RANKS), fp.designation, "Other (Director, Faculty)")
    rk = fp[fp.role.notna()]
    rows = []
    for rnk in RANKS + ["All"]:
        s = rk if rnk == "All" else rk[rk["rank"] == rnk]
        c = s[s.paper_has_corresponding == True]  # noqa: E712
        rows.append({"rank": rnk, "faculty_paper_rows": len(s), "faculty": s.faculty_id.nunique(),
                     "first_author": (s.role == "first").mean(), "last_author": (s.role == "last").mean(),
                     "middle_author": (s.role == "middle").mean(), "sole_author": (s.role == "sole").mean(),
                     "corresponding_author": c.corresponding.mean(),
                     "rows_with_corresponding_info": len(c), "median_authors": s.n_authors.median()})
    lead = pd.DataFrame(rows)
    ct = pd.crosstab(rk[rk["rank"].isin(RANKS)]["rank"], rk[rk["rank"].isin(RANKS)].role)
    chi = stats.chi2_contingency(ct)
    save(lead.round(4), "q20_author_role_by_rank.csv")
    trend = rk[rk["rank"].isin(RANKS)].groupby(["rank", "year"]).agg(
        rows=("role", "size"), first_author=("role", lambda s: (s == "first").mean()),
        last_author=("role", lambda s: (s == "last").mean())).reset_index()
    save(trend.round(4), "q20_author_role_by_rank_and_year.csv")
    # paper level: is impact higher when an NIT faculty member leads (first, last or corresponding author)?
    pl = rk.assign(lead=(rk.role.isin(["first", "last", "sole"]) | (rk.corresponding == True)))  # noqa: E712
    pp = faculty_paper_table(g)
    lead_paper = pl.groupby(["institution", "openalex_id"]).lead.any()
    pp["faculty_leads"] = pd.MultiIndex.from_frame(pp[["institution", "openalex_id"]]).map(lead_paper) \
        .fillna(False).astype(int)
    t20, n20, _ = ols(pp, "log_fwci", num=["log_authors"], cat=["year", "branch"],
                      dummies=["surathkal", "foreign", "indian_collab", "conference", "faculty_leads"])
    outside = pp[(pp.foreign == 1) | (pp.indian_collab == 1)]
    summary["q20"] = {"roles": lead.to_dict("records"), "chi2": chi.statistic, "chi2_p": chi.pvalue,
                      "papers_led_by_nit_faculty_share": pp.faculty_leads.mean(),
                      "papers_with_outside_partners_led_by_nit_faculty_share": outside.faculty_leads.mean(),
                      "fwci_effect_when_faculty_leads_pct": t20.loc["faculty_leads", "effect_pct"],
                      "fwci_effect_ci": [t20.loc["faculty_leads", "effect_ci_low_pct"],
                                         t20.loc["faculty_leads", "effect_ci_high_pct"]],
                      "fwci_effect_p": t20.loc["faculty_leads", "p_value"],
                      "corresponding_info_share": rk.paper_has_corresponding.mean()}
    fig, ax = plt.subplots(figsize=(9, 4.6))
    lf = lead[lead["rank"].isin(RANKS)]
    left = np.zeros(len(lf))
    cols = {"first_author": ("first author", BLUE), "middle_author": ("middle", AXIS),
            "last_author": ("last author (senior)", ORANGE), "sole_author": ("sole author", INK)}
    for c, (lab, col) in cols.items():
        ax.barh(lf["rank"], 100 * lf[c], left=left, color=col, label=lab, height=0.6, edgecolor="white", lw=2)
        left += 100 * lf[c].values
    ax.set_xlabel("share of the rank's faculty-paper rows (%)"); ax.invert_yaxis()
    ax.legend(frameon=False, fontsize=9, ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.15))
    ax.set_title("Where in the author list each rank appears", fontsize=11, loc="left", color=INK)
    style_axes(ax); ax.grid(axis="y", visible=False)
    savefig(fig, "q20_author_roles.png")

    # ---- 21. specialists vs generalists
    rows = []
    for fid, s in fp.groupby("faculty_id"):
        if len(s) < 10:
            continue
        sub = s.subfield.fillna("Unknown").values
        ent = []
        for _ in range(200):
            pick = RNG.choice(sub, 10, replace=False)
            _, c = np.unique(pick, return_counts=True)
            q = c / c.sum()
            ent.append(-(q * np.log(q)).sum())
        _, c = np.unique(sub, return_counts=True)
        q = c / c.sum()
        rows.append({"faculty_id": fid, "papers": len(s), "subfields": len(c),
                     "entropy_all_papers": -(q * np.log(q)).sum(), "entropy_10_papers": np.mean(ent),
                     "main_subfield_share": q.max(), "fields": s.field.nunique()})
    br = pd.DataFrame(rows).set_index("faculty_id").join(per[["author", "institution", "department", "designation",
                                                              "status", "mean_fwci", "median_fwci", "h_index",
                                                              "citations_per_paper"]])
    # breadth relative to the department (CSE and Mathematics differ in how many subfields exist)
    br["breadth_pct_in_department"] = br.groupby(["institution", "department"]).entropy_10_papers.rank(pct=True)
    br["breadth_group"] = pd.qcut(br.entropy_10_papers, 4, labels=["most specialised", "specialised",
                                                                     "broad", "broadest"])

    def partial_spearman(a, b, c):
        d_ = br[[a, b, c]].dropna()
        ra, rb, rc = (d_[x].rank() for x in (a, b, c))
        res_a = ra - np.polyval(np.polyfit(rc, ra, 1), rc)
        res_b = rb - np.polyval(np.polyfit(rc, rb, 1), rc)
        return stats.pearsonr(res_a, res_b)
    rows = []
    for m in ("mean_fwci", "median_fwci", "h_index", "citations_per_paper", "papers"):
        r1 = stats.spearmanr(br.entropy_10_papers, br[m], nan_policy="omit")
        r2 = stats.spearmanr(br.breadth_pct_in_department, br[m], nan_policy="omit")
        rows.append({"measure": m, "spearman_breadth": r1.statistic, "p": r1.pvalue,
                     "spearman_breadth_within_department": r2.statistic, "p_within": r2.pvalue,
                     **({"partial_spearman_controlling_papers": partial_spearman("entropy_10_papers", m, "papers")[0],
                         "p_partial": partial_spearman("entropy_10_papers", m, "papers")[1]} if m != "papers" else {})})
    corr = pd.DataFrame(rows)
    grp = br.groupby("breadth_group", observed=True).agg(faculty=("papers", "size"), median_papers=("papers", "median"),
                                                         mean_fwci=("mean_fwci", "mean"), median_fwci=("mean_fwci", "median"),
                                                         median_h=("h_index", "median"),
                                                         median_breadth=("entropy_10_papers", "median"),
                                                         median_subfields=("subfields", "median")).reset_index()
    save(br.reset_index().round(4), "q21_research_breadth_by_faculty.csv")
    save(corr.round(4), "q21_breadth_vs_impact.csv")
    save(grp.round(4), "q21_breadth_groups.csv")
    summary["q21"] = {"faculty": len(br), "correlations": corr.to_dict("records"), "groups": grp.to_dict("records"),
                      "most_specialised_examples": br.nsmallest(3, "entropy_10_papers")[["author", "department"]]
                      .to_dict("records"),
                      "broadest_examples": br.nlargest(3, "entropy_10_papers")[["author", "department"]].to_dict("records")}
    fig, ax = plt.subplots(figsize=(8, 5))
    for view in NITS:
        s = br[br.institution == view]
        ax.scatter(s.entropy_10_papers, s.mean_fwci, s=14, alpha=0.6, color=COLOR[view], label=view,
                   edgecolors="white", linewidths=0.5)
    ax.set_yscale("log")
    ax.set_xlabel("research breadth (subfield entropy of 10 random papers)")
    ax.set_ylabel("mean FWCI (log)")
    c0 = corr.set_index("measure").loc["mean_fwci"]
    ax.set_title(f"Specialists vs generalists: Spearman ρ = {c0.spearman_breadth:.2f} (p = {c0.p:.2g})",
                 fontsize=11, loc="left", color=INK)
    ax.legend(frameon=False, fontsize=9); style_axes(ax)
    savefig(fig, "q21_breadth_vs_fwci.png")
    save_json(summary, "people_summary.json")
    print(json.dumps(summary, indent=1, default=str)[:6000])


# ================================================================ part "venues": questions 22-24
def venue_class(r):
    if r.type == "conference":
        return "Conference, CORE-ranked" if str(r.quartile).startswith("CORE") else "Conference, not ranked"
    q = str(r.quartile)
    if q == "Q1":
        return "Journal Q1"
    if q == "Q2":
        return "Journal Q2"
    if q in ("Q3", "Q4"):
        return "Journal Q3-Q4"
    return "Journal, not ranked"


VCLASSES = ["Journal Q1", "Journal Q2", "Journal Q3-Q4", "Journal, not ranked", "Conference, CORE-ranked",
            "Conference, not ranked"]


def venues_part():
    p = papers()
    summary = {}
    p["venue_class"] = p.apply(venue_class, axis=1)
    for c in VCLASSES[1:]:
        p[f"vc_{c}"] = (p.venue_class == c).astype(int)
    d = p[p.fwci.notna()]
    t, n, _ = ols(d, "log_fwci", num=["log_authors"], cat=["year", "field"],
                  dummies=["surathkal", "foreign", "indian_collab", *[f"vc_{c}" for c in VCLASSES[1:]]])
    u = unique(p)
    rows = []
    for c in VCLASSES:
        s = u[u.venue_class == c]
        r = {"venue_class": c, "papers": len(s), "share": len(s) / len(u), "mean_fwci": s.fwci.mean(),
             "median_fwci": s.fwci.median(), "top10_share": s.top10pct.astype(float).mean(),
             "citations_per_paper": s.citations.mean()}
        if f"vc_{c}" in t.index:
            r.update({"effect_vs_q1_journal_pct": t.loc[f"vc_{c}", "effect_pct"],
                      "ci_low_pct": t.loc[f"vc_{c}", "effect_ci_low_pct"],
                      "ci_high_pct": t.loc[f"vc_{c}", "effect_ci_high_pct"]})
        rows.append(r)
    vc = pd.DataFrame(rows)
    save(vc.round(4), "q22_venue_classes.csv")
    # conference share per year
    cy = p.groupby(["institution", "year"]).conference.mean().unstack(0)
    cy["Both"] = u.groupby("year").conference.mean()
    save(cy.reset_index().round(4), "q22_conference_share_by_year.csv")
    # by department (faculty papers, branch of most of the NIT's faculty on the paper)
    fpt = faculty_paper_table()
    drows = []
    for (inst, b), s in fpt.groupby(["institution", "branch"]):
        j, c = s[s.type == "journal"].fwci, s[s.type == "conference"].fwci
        if len(s) < 50:
            continue
        drows.append({"institution": inst, "department": b, "papers": len(s), "conference_share": len(c) / len(s),
                      "mean_fwci_journal": j.mean(), "mean_fwci_conference": c.mean(),
                      "conference_vs_journal": c.mean() / j.mean() if len(c) and len(j) else np.nan,
                      "p_value": stats.mannwhitneyu(j, c).pvalue if len(c) >= 10 and len(j) >= 10 else np.nan})
    dep = pd.DataFrame(drows).sort_values("conference_share", ascending=False)
    save(dep.round(4), "q22_conference_by_department.csv")
    # 23. the most-used venues: each compared with papers of the same venue class, field and year
    vol = u.groupby("journal_name").size()
    big = [v for v in vol[vol >= 100].index]
    for i, v in enumerate(big):
        d = d.assign(**{f"venue_{i}": (d.journal_name == v).astype(int)})
    t2, n2, _ = ols(d, "log_fwci", num=["log_authors"], cat=["year", "field"],
                    dummies=["surathkal", "foreign", "indian_collab", *[f"vc_{c}" for c in VCLASSES[1:]],
                             *[f"venue_{i}" for i in range(len(big))]])
    # the same venues against all other papers of the same field and year (no venue-class control)
    t3, _, _ = ols(d, "log_fwci", num=["log_authors"], cat=["year", "field"],
                   dummies=["surathkal", "foreign", "indian_collab", *[f"venue_{i}" for i in range(len(big))]])
    rows = []
    for i, v in enumerate(big):
        s = u[u.journal_name == v]
        rows.append({"venue": v, "papers": len(s), "trichy": int((p[p.journal_name == v].institution == "NIT Trichy").sum()),
                     "surathkal": int((p[p.journal_name == v].institution == "NIT Surathkal").sum()),
                     "venue_class": s.venue_class.mode().iat[0], "mean_fwci": s.fwci.mean(),
                     "median_fwci": s.fwci.median(), "top10_share": s.top10pct.astype(float).mean(),
                     "citations_per_paper": s.citations.mean(),
                     "effect_vs_all_other_papers_pct": t3.loc[f"venue_{i}", "effect_pct"],
                     "ci_low_all_pct": t3.loc[f"venue_{i}", "effect_ci_low_pct"],
                     "ci_high_all_pct": t3.loc[f"venue_{i}", "effect_ci_high_pct"],
                     "effect_vs_similar_papers_pct": t2.loc[f"venue_{i}", "effect_pct"],
                     "ci_low_pct": t2.loc[f"venue_{i}", "effect_ci_low_pct"],
                     "ci_high_pct": t2.loc[f"venue_{i}", "effect_ci_high_pct"],
                     "p_value": t2.loc[f"venue_{i}", "p_value"]})
    hv = pd.DataFrame(rows).sort_values("papers", ascending=False)
    save(hv.round(4), "q23_high_volume_venues.csv")
    hv_share = u.journal_name.isin(big).mean()
    summary["q22"] = {"papers": len(u), "regression_papers": n, "classes": vc.to_dict("records"),
                      "conference_share_2016": cy.loc[2016].to_dict(), "conference_share_2025": cy.loc[2025].to_dict(),
                      "departments_most_conference": dep.head(5)[["institution", "department", "conference_share",
                                                                  "conference_vs_journal"]].to_dict("records")}
    summary["q23"] = {"venues_with_100_plus_papers": len(big), "share_of_all_papers": hv_share,
                      "venues": hv[["venue", "papers", "venue_class", "mean_fwci", "effect_vs_all_other_papers_pct",
                                    "effect_vs_similar_papers_pct", "p_value"]].to_dict("records")}

    fig, axes = plt.subplots(1, 2, figsize=(14, 5.2))
    ax = axes[0]
    e = vc.dropna(subset=["effect_vs_q1_journal_pct"]).iloc[::-1]
    ax.errorbar(e.effect_vs_q1_journal_pct, [f"{a} ({b:,})" for a, b in zip(e.venue_class, e.papers)],
                xerr=[e.effect_vs_q1_journal_pct - e.ci_low_pct, e.ci_high_pct - e.effect_vs_q1_journal_pct],
                fmt="o", color=INK, ecolor=MUTED, capsize=3, ms=6)
    ax.axvline(0, color=AXIS, lw=1)
    ax.set_xlabel("FWCI vs a Q1 journal paper (%, adjusted)")
    ax.set_title("Venue type and impact (95% CI)", fontsize=11, loc="left", color=INK)
    style_axes(ax); ax.grid(axis="x", color=GRID); ax.grid(axis="y", visible=False)
    ax = axes[1]
    for view in NITS:
        ax.plot(cy.index, 100 * cy[view], color=COLOR[view], lw=2, marker="o", ms=4, label=view)
    ax.set_ylabel("conference papers (% of papers)"); ax.set_title("Conference share by year", fontsize=11,
                                                                     loc="left", color=INK)
    ax.legend(frameon=False, fontsize=9); style_axes(ax)
    savefig(fig, "q22_venues.png")

    # ---- 24. open access
    if "oa_status" in p:
        p["oa"] = p.oa_status.fillna("unknown")
        order = ["closed", "gold", "diamond", "hybrid", "bronze", "green"]
        for s_ in order[1:]:
            p[f"oa_{s_}"] = (p.oa == s_).astype(int)
        d = p[p.fwci.notna() & (p.oa != "unknown")]
        t_a, n_a, _ = ols(d, "log_fwci", num=["log_authors"], cat=["year", "field"],
                          dummies=["surathkal", "conference", "foreign", "indian_collab", *[f"oa_{s}" for s in order[1:]]])
        t_b, n_b, _ = ols(d.assign(venue_class=d.apply(venue_class, axis=1)), "log_fwci", num=["log_authors"],
                          cat=["year", "field", "venue_class"],
                          dummies=["surathkal", "foreign", "indian_collab", *[f"oa_{s}" for s in order[1:]]])
        u = unique(p)
        rows = []
        for s_ in order + ["unknown"]:
            s = u[u.oa == s_]
            r = {"oa_status": s_, "papers": len(s), "share": len(s) / len(u), "mean_fwci": s.fwci.mean(),
                 "median_fwci": s.fwci.median(), "citations_per_paper": s.citations.mean(),
                 "top10_share": s.top10pct.astype(float).mean(),
                 "journal_share_q1": (s.quartile == "Q1").mean()}
            if f"oa_{s_}" in t_a.index:
                r.update({"effect_vs_closed_pct": t_a.loc[f"oa_{s_}", "effect_pct"],
                          "ci_low_pct": t_a.loc[f"oa_{s_}", "effect_ci_low_pct"],
                          "ci_high_pct": t_a.loc[f"oa_{s_}", "effect_ci_high_pct"],
                          "effect_same_venue_class_pct": t_b.loc[f"oa_{s_}", "effect_pct"],
                          "ci_low_same_venue_class_pct": t_b.loc[f"oa_{s_}", "effect_ci_low_pct"],
                          "ci_high_same_venue_class_pct": t_b.loc[f"oa_{s_}", "effect_ci_high_pct"]})
            rows.append(r)
        oa = pd.DataFrame(rows)
        save(oa.round(4), "q24_open_access.csv")
        p["is_open"] = p.oa.isin(order[1:]).astype(int)
        oy = p[p.oa != "unknown"].groupby(["institution", "year"]).is_open.mean().unstack(0)
        oy["Both"] = u[u.oa != "unknown"].groupby("year").oa.apply(lambda s: s.isin(order[1:]).mean())
        save(oy.reset_index().round(4), "q24_open_access_by_year.csv")
        dd = d.assign(is_open=d.oa.isin(order[1:]).astype(int))
        t_c, _, _ = ols(dd, "log_fwci", num=["log_authors"], cat=["year", "field"],
                        dummies=["surathkal", "conference", "foreign", "indian_collab", "is_open"])
        summary["q24"] = {"papers_with_status": int((u.oa != "unknown").sum()),
                          "open_share": float(u[u.oa != "unknown"].oa.isin(order[1:]).mean()),
                          "statuses": oa.to_dict("records"), "regression_papers": n_a,
                          "any_open_effect_pct": t_c.loc["is_open", "effect_pct"],
                          "any_open_ci": [t_c.loc["is_open", "effect_ci_low_pct"], t_c.loc["is_open", "effect_ci_high_pct"]],
                          "open_share_2016": oy.loc[2016].to_dict(), "open_share_2025": oy.loc[2025].to_dict()}
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))
        ax = axes[0]
        e = oa.dropna(subset=["effect_vs_closed_pct"]).iloc[::-1]
        y = np.arange(len(e))
        ax.errorbar(e.effect_vs_closed_pct, y + 0.15, xerr=[e.effect_vs_closed_pct - e.ci_low_pct,
                                                            e.ci_high_pct - e.effect_vs_closed_pct],
                    fmt="o", color=INK, ecolor=MUTED, capsize=3, ms=6, label="same field, year, team")
        ax.errorbar(e.effect_same_venue_class_pct, y - 0.15,
                    xerr=[e.effect_same_venue_class_pct - e.ci_low_same_venue_class_pct,
                          e.ci_high_same_venue_class_pct - e.effect_same_venue_class_pct],
                    fmt="s", color=MUTED, ecolor=AXIS, capsize=3, ms=5, label="... and same venue class")
        ax.set_yticks(y, [f"{a} ({b:,})" for a, b in zip(e.oa_status, e.papers)])
        ax.axvline(0, color=AXIS, lw=1)
        ax.set_xlabel("FWCI vs closed-access papers (%, adjusted)")
        ax.set_title("Open access and impact (95% CI)", fontsize=11, loc="left", color=INK)
        ax.legend(frameon=False, fontsize=9); style_axes(ax); ax.grid(axis="x", color=GRID); ax.grid(axis="y", visible=False)
        ax = axes[1]
        for view in NITS:
            ax.plot(oy.index, 100 * oy[view], color=COLOR[view], lw=2, marker="o", ms=4, label=view)
        ax.set_ylabel("open-access papers (%)"); ax.set_title("Open-access share by year", fontsize=11, loc="left", color=INK)
        ax.legend(frameon=False, fontsize=9); style_axes(ax)
        savefig(fig, "q24_open_access.png")
    save_json(summary, "venues_summary.json")
    print(json.dumps(summary, indent=1, default=str)[:5000])


# ================================================================ part "richer": question 25
def richer_part():
    p = papers()
    u = unique(p)
    u = u[u.cites_now.notna()].copy()
    # citations up to the end of year t = today's total - citations received after t
    years = list(range(2012, PARTIAL_YEAR + 1))
    cum = {}
    exact = 0
    for r in u.itertuples(index=False):
        cy = {int(k): v for k, v in r.counts_by_year.items()}
        total = int(r.cites_now)
        exact += sum(cy.values()) == total
        after = 0
        c = {}
        for t in sorted(years, reverse=True):
            c[t] = total - after
            after += cy.get(t, 0)
        cum[r.openalex_id] = (c, cy, r.year)
    exact_share = exact / len(u)
    assert all(v[0][PARTIAL_YEAR] == int(t) for v, t in zip(cum.values(), u.cites_now)), "reconstruction failed"
    rows = []
    for wid, (c, cy, py) in cum.items():
        for t in range(max(py, 2016), PARTIAL_YEAR - 1):      # t+1 must be a complete year (up to 2025)
            rows.append((wid, t, t - py, c[t], cy.get(t + 1, 0)))
    tr = pd.DataFrame(rows, columns=["paper", "year", "age", "k", "new"])
    tr = tr[tr.age >= 1]                                       # skip the publication year itself
    # relative attachment rate: new citations / mean new citations of papers of the same year and age
    tr["rel"] = tr.new / tr.groupby(["year", "age"]).new.transform("mean")
    bins = [0, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377, 10 ** 6]
    tr["bin"] = pd.cut(tr.k, bins, right=False, labels=[f"{a}-{b - 1}" for a, b in zip(bins[:-1], bins[1:])])
    kern = tr.groupby("bin", observed=True).agg(transitions=("rel", "size"), mean_k=("k", "mean"),
                                                 mean_new=("new", "mean"), relative_rate=("rel", "mean")).reset_index()
    fit = kern[(kern.mean_k >= 1) & (kern.transitions >= 50)]
    alpha, logc = np.polyfit(np.log(fit.mean_k), np.log(fit.relative_rate), 1)
    # by age group
    arows = []
    for lab, s in (("age 1-2", tr[tr.age <= 2]), ("age 3-5", tr[tr.age.between(3, 5)]), ("age 6+", tr[tr.age >= 6])):
        kk = s.groupby("bin", observed=True).agg(n=("rel", "size"), mean_k=("k", "mean"), rel=("rel", "mean"))
        kk = kk[(kk.mean_k >= 1) & (kk.n >= 50)]
        a_, _ = np.polyfit(np.log(kk.mean_k), np.log(kk.rel), 1)
        arows.append({"papers_age": lab, "transitions": len(s), "alpha": a_})
    ages = pd.DataFrame(arows)
    save(kern.round(4), "q25_attachment_kernel.csv")
    save(ages.round(4), "q25_alpha_by_age.csv")
    # do top papers stay on top? cohorts 2016-2020: top 10% by citations after 2 full years vs after 5
    srows = []
    for py in range(2016, 2021):
        coh = {w: v for w, v in cum.items() if v[2] == py}
        a = pd.Series({w: v[0][py + 2] for w, v in coh.items()})
        b = pd.Series({w: v[0][min(py + 5, 2025)] for w, v in coh.items()})
        topa = set(a.rank(ascending=False, method="first").loc[lambda s: s <= max(1, round(0.1 * len(s)))].index)
        topb = set(b.rank(ascending=False, method="first").loc[lambda s: s <= max(1, round(0.1 * len(s)))].index)
        srows.append({"cohort": py, "papers": len(coh), "top10_after_2y_still_top10_after_5y": len(topa & topb) / len(topa),
                      "spearman_2y_vs_5y": stats.spearmanr(a, b.reindex(a.index)).statistic,
                      "share_of_cites_to_top10_after_2y": a.nlargest(len(topa)).sum() / a.sum(),
                      "share_of_cites_to_top10_after_5y": b.nlargest(len(topb)).sum() / b.sum(),
                      "gini_after_2y": gini(a), "gini_after_5y": gini(b)})
    stay = pd.DataFrame(srows)
    save(stay.round(4), "q25_top_papers_stay_on_top.csv")
    summary = {"papers": len(u), "transitions": len(tr), "yearly_counts_sum_to_total_share": exact_share,
               "alpha": alpha, "alpha_by_age": ages.to_dict("records"),
               "uncited_share_after_2y_cohort_2020": float((pd.Series({w: v[0][2022] for w, v in cum.items()
                                                                      if v[2] == 2020}) == 0).mean()),
               "rate_k0": float(kern.iloc[0].relative_rate), "rate_k_55_88": float(kern.set_index("bin").loc["55-88", "relative_rate"])
               if "55-88" in set(kern.bin.astype(str)) else None,
               "stay_on_top": stay.to_dict("records")}
    save_json(summary, "richer_summary.json")
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    ax = axes[0]
    k = kern[kern.mean_k >= 1]
    ax.scatter(k.mean_k, k.relative_rate, color=INK, s=30, zorder=3, label="papers grouped by citations so far")
    xs = np.linspace(k.mean_k.min(), k.mean_k.max(), 100)
    ax.plot(xs, np.exp(logc) * xs ** alpha, color=ORANGE, lw=2, label=f"fit: rate ∝ k^{alpha:.2f}")
    ax.plot(xs, np.exp(logc) * xs ** 1.0 * (fit.relative_rate.iloc[0] / (np.exp(logc) * fit.mean_k.iloc[0] ** 1.0)),
            color=AXIS, lw=1, ls="--", label="linear (α = 1)")
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xlabel("citations a paper already has (k)"); ax.set_ylabel("new citations next year (relative to peers)")
    ax.set_title("Rich get richer? (attachment kernel)", fontsize=11, loc="left", color=INK)
    ax.legend(frameon=False, fontsize=9); style_axes(ax)
    ax = axes[1]
    ax.bar(stay.cohort.astype(str), 100 * stay.top10_after_2y_still_top10_after_5y, color=BLUE, width=0.6)
    ax.set_ylabel("top-10% papers after 2 years still top-10% after 5 (%)")
    ax.set_title("Early winners stay winners", fontsize=11, loc="left", color=INK)
    style_axes(ax)
    savefig(fig, "q25_rich_get_richer.png")
    print(json.dumps(summary, indent=1, default=str)[:3000])


# ================================================================ part "robust": question 27
def robust_part():
    from insights import MEASURES, MIN_PAPERS
    g = pd.read_csv(os.path.join(DATA, "group12_data.csv"), low_memory=False)
    m = pd.read_csv(os.path.join(DATA, "reference", "faculty_openalex_map.csv"))
    single = m[(m.method == "name") & (m.papers_at_nit <= 1)]
    strict = single[(single.branch_score <= 0) | (single.student_name_clash == True)]  # noqa: E712
    fac = pd.read_csv(os.path.join(DATA, "faculty.csv")).drop_duplicates("faculty_id").set_index("faculty_id")

    def measures(gg):
        papers_ = gg.drop_duplicates(["institution", "openalex_id"])
        out = {}
        for view in NITS + ["Both"]:
            s = papers_ if view == "Both" else papers_[papers_.institution == view]
            if view == "Both":
                s = s.drop_duplicates("openalex_id")
            j = s[s.type == "journal"]
            ranked = j[j.quartile.fillna("").str.startswith("Q")]
            fp_ = gg if view == "Both" else gg[gg.institution == view]
            per_ = fp_.drop_duplicates(["faculty_id", "openalex_id"]).groupby("faculty_id").citations.apply(h_index)
            out[view] = {"papers": len(s), "citations": int(s.citations.sum()), "q1_share": (ranked.quartile == "Q1").mean(),
                         "mean_fwci": s.fwci.mean(), "faculty_with_papers": fp_.faculty_id.nunique(),
                         "median_h_index": per_.median()}
        return out

    def ranking(gg):
        return ranking_scores(gg, fac)

    def graph(gg):
        Gx = nx.Graph()
        Gx.add_nodes_from(gg.faculty_id.unique())
        small = gg[gg.n_authors <= 50]
        # one faculty member per author slot, as in build_networks.py (a person on both NITs' rosters fills one
        # slot, and the later row wins)
        slot = {(r.openalex_id, int(r.author_position)): r.faculty_id for r in small.itertuples(index=False)}
        per_paper = collections.defaultdict(set)
        for (wid, _), fid in slot.items():
            per_paper[wid].add(fid)
        for fids in per_paper.values():
            for a, b in itertools.combinations(sorted(fids), 2):
                Gx.add_edge(a, b)
        return Gx

    def regression(gg):
        t, n, _ = ols(faculty_paper_table(gg), "log_fwci", num=["log_authors"], cat=["year", "branch"],
                      dummies=["surathkal", "foreign", "indian_collab", "conference"])
        return t.loc["surathkal"], t.loc["foreign"], t.loc["conference"]

    G0 = graph(g)
    ref = faculty_graph()
    assert G0.number_of_edges() == ref.number_of_edges(), (G0.number_of_edges(), ref.number_of_edges())
    base = {"measures": measures(g), "rank": ranking(g), "btw": nx.betweenness_centrality(G0), "reg": regression(g),
            "edges": G0.number_of_edges(), "deg": dict(G0.degree())}
    rows, summary = [], {"doubtful_links": {"single_paper_name_only": len(single), "strict": len(strict)}}
    for label, drop in (("drop single-paper name-only links", single), ("drop only those with a branch mismatch or "
                                                                         "student name clash", strict)):
        bad = set(zip(drop.faculty_id, drop.author_id))
        gg = g[[k not in bad for k in zip(g.faculty_id, g.author_id)]]
        removed_rows = len(g) - len(gg)
        mm = measures(gg)
        for view in NITS + ["Both"]:
            for k_, v0 in base["measures"][view].items():
                v1 = mm[view][k_]
                rows.append({"variant": label, "institution": view, "measure": k_, "with_all_links": v0,
                             "without_doubtful_links": v1, "change_pct": 100 * (v1 - v0) / v0 if v0 else np.nan})
        r0, r1 = base["rank"], ranking(gg)
        common = r0.index.intersection(r1.index)
        top0, top1 = set(r0.nlargest(20).index), set(r1.nlargest(20).index)
        Gx = graph(gg)
        b1 = nx.betweenness_centrality(Gx)
        bt0 = set(sorted(base["btw"], key=base["btw"].get, reverse=True)[:10])
        bt1 = set(sorted(b1, key=b1.get, reverse=True)[:10])
        reg1 = regression(gg)
        extra = [("faculty-paper rows removed", removed_rows), ("faculty ranked", len(r1)),
                 ("ranking Spearman with the original", stats.spearmanr(r0[common], r1[common]).statistic),
                 ("top-20 ranking overlap (of 20)", len(top0 & top1)),
                 ("faculty links in the network", Gx.number_of_edges()),
                 ("top-10 betweenness overlap (of 10)", len(bt0 & bt1)),
                 ("degree Spearman with the original",
                  stats.spearmanr([base["deg"][n] for n in G0], [Gx.degree(n) if n in Gx else 0 for n in G0]).statistic),
                 ("NIT Surathkal FWCI effect (%)", 100 * (math.exp(reg1[0].coef) - 1)),
                 ("NIT Surathkal effect p-value", reg1[0].p_value),
                 ("foreign co-author effect (%)", 100 * (math.exp(reg1[1].coef) - 1)),
                 ("conference effect (%)", 100 * (math.exp(reg1[2].coef) - 1))]
        orig = {"faculty-paper rows removed": 0, "faculty ranked": len(r0), "ranking Spearman with the original": 1.0,
                "top-20 ranking overlap (of 20)": 20, "faculty links in the network": base["edges"],
                "top-10 betweenness overlap (of 10)": 10, "degree Spearman with the original": 1.0,
                "NIT Surathkal FWCI effect (%)": 100 * (math.exp(base["reg"][0].coef) - 1),
                "NIT Surathkal effect p-value": base["reg"][0].p_value,
                "foreign co-author effect (%)": 100 * (math.exp(base["reg"][1].coef) - 1),
                "conference effect (%)": 100 * (math.exp(base["reg"][2].coef) - 1)}
        for k_, v in extra:
            rows.append({"variant": label, "institution": "Both", "measure": k_, "with_all_links": orig[k_],
                         "without_doubtful_links": v,
                         "change_pct": 100 * (v - orig[k_]) / orig[k_] if orig[k_] not in (0, None) else np.nan})
    res = pd.DataFrame(rows)
    save(res.round(5), "q27_name_matching_sensitivity.csv")
    s = res[res.variant.str.startswith("drop single")]
    summary["main"] = s[s.institution == "Both"].drop(columns="variant").to_dict("records")
    summary["largest_change_pct"] = float(s.change_pct.abs().replace(np.inf, np.nan).dropna()
                                          [~s.measure.str.contains("removed|p-value|overlap|Spearman|links", regex=True)].max())
    save_json(summary, "robust_summary.json")
    print(res.to_string())



# ================================================================ shared: citation links with Indian works
def ranking_scores(gg, fac, cites="citations"):
    """The team's composite faculty score (insights.py ranking: mean percentile of 7 measures, current faculty with
    10+ papers). `cites` names the per-row citation column, so a version without self-citations can be scored."""
    from insights import MEASURES, MIN_PAPERS
    p = gg.drop_duplicates(["faculty_id", "openalex_id"]).copy()
    p["top_venue"] = p.quartile.isin(["Q1", "CORE A*", "CORE A"])
    p["if5"] = p.journal_if_2yr > 5
    p["top10"] = p.top10pct == True  # noqa: E712
    t = p.groupby("faculty_id").agg(papers=("openalex_id", "size"), citations=(cites, "sum"),
                                    h_index=(cites, h_index), mean_fwci=("fwci", "mean"),
                                    top10_papers=("top10", "sum"), top_venue_papers=("top_venue", "sum"),
                                    if5_papers=("if5", "sum"))
    t = t.join(fac[["status"]])
    t = t[(t.status == "current") & (t.papers >= MIN_PAPERS)]
    return pd.DataFrame({c: 100 * t[c].rank(pct=True) for c in MEASURES}).mean(axis=1)


def top1(counter, default=("", 0)):
    """The most common item of a Counter; ties go to the alphabetically first item, so every run is the same."""
    if not counter:
        return default
    return sorted(counter.items(), key=lambda kv: (-kv[1], str(kv[0])))[0]


def load_links(direction):
    """Indian works that cite our papers ("citers") or that our papers cite ("refs"), from fetch_links.py, merged
    by work id: Indian institutions, authors (and each author's Indian institutions), year, and which of our
    papers they cite."""
    out = {}
    for line in open(os.path.join(RAW, f"links_{direction}.jsonl"), encoding="utf-8"):
        r = json.loads(line)
        d = out.setdefault(r["id"], {"insts": set(), "authors": set(), "auth_insts": {}, "names": {}, "author_names": {},
                                     "year": r.get("year"), "cites": set()})
        for a in r["authors"]:
            ins = {i[0] for i in a["inst"] if i[2] == "IN"}
            for i in a["inst"]:
                if i[2] == "IN":
                    d["names"][i[0]] = i[1]
            d["insts"] |= ins
            if a["id"]:
                d["authors"].add(a["id"])
                d["auth_insts"].setdefault(a["id"], set()).update(ins)
                d["author_names"][a["id"]] = a["name"]
        d["cites"].update(r.get("cites_ours") or [])
    return out


def authors_of(w):
    return {short(a["author"]["id"]) for a in w["authorships"] if a["author"].get("id")}


# ================================================================ part "inward": question 26
def link_kind(d, auth, own, other):
    """One citation link seen from our paper: 'self' if the two papers share an author, else 'colleague' if the
    other paper has an author from the same NIT, 'other NIT' (Trichy <-> Surathkal) or 'other Indian'."""
    if d["authors"] & auth:
        return "self"
    if own in d["insts"]:
        return "colleague"
    if other in d["insts"]:
        return "other NIT"
    return "other Indian"


KINDS = ["self", "colleague", "other NIT", "other Indian"]


def inward_part():
    pp = faculty_paper_table()
    works = raw_works()
    refs, cit = load_links("refs"), load_links("citers")
    by_target = collections.defaultdict(list)
    for c, d in cit.items():
        for t in d["cites"]:
            by_target[t].append(c)
    other_of = {NAME_TO_ID[a]: NAME_TO_ID[b] for a, b in (NITS, NITS[::-1])}
    rows = []
    for r in pp.itertuples(index=False):
        w = works[(r.institution, r.openalex_id)]
        own = NAME_TO_ID[r.institution]
        auth = authors_of(w)
        rr = {short(x) for x in w["referenced_works"]}
        kr = collections.Counter(link_kind(refs[x], auth, own, other_of[own]) for x in rr if x in refs)
        kc = collections.Counter(link_kind(cit[c], auth, own, other_of[own]) for c in by_target.get(r.openalex_id, []))
        rows.append({"institution": r.institution, "openalex_id": r.openalex_id, "year": r.year, "branch": r.branch,
                     "refs": len(rr), "citations": w["cited_by_count"],
                     **{f"ref_{k}": kr[k] for k in KINDS}, **{f"cit_{k}": kc[k] for k in KINDS}})
    d = pd.DataFrame(rows).merge(pp[["institution", "openalex_id", "fwci", "log_fwci", "log_authors", "surathkal",
                                     "foreign", "indian_collab", "conference"]], on=["institution", "openalex_id"])
    assert len(d) == len(pp)
    d["ref_home"] = d.ref_self + d.ref_colleague
    d["cit_home"] = d.cit_self + d.cit_colleague

    def agg(x):
        R, C, n = x.refs.sum(), x.citations.sum(), len(x)
        out = {"papers": n, "references": R, "references_per_paper": R / n}
        for k in KINDS:
            out[f"ref_{k.replace(' ', '_')}_share"] = x[f"ref_{k}"].sum() / R
        out["ref_home_share"] = x.ref_home.sum() / R
        out["ref_outside_india_share"] = 1 - sum(x[f"ref_{k}"].sum() for k in KINDS) / R
        out["citations"] = C
        for k in KINDS:
            out[f"cit_{k.replace(' ', '_')}_share"] = x[f"cit_{k}"].sum() / C if C else np.nan
        out["cit_home_share"] = x.cit_home.sum() / C if C else np.nan
        out["cit_outside_india_share"] = 1 - sum(x[f"cit_{k}"].sum() for k in KINDS) / C if C else np.nan
        out["citations_per_paper"] = C / n
        out["citations_per_paper_without_home"] = (C - x.cit_home.sum()) / n
        out["mean_fwci"] = x.fwci.mean()
        return pd.Series(out)
    nit = d.groupby("institution").apply(agg).reset_index()
    both = agg(d.drop_duplicates("openalex_id")).to_frame().T.assign(institution="Both")
    overall = pd.concat([nit, both[nit.columns]])
    save(overall.round(4), "q26_inward_overall.csv")
    dep = d.groupby(["institution", "branch"]).apply(agg).reset_index().rename(columns={"branch": "department"})
    dep = dep[dep.papers >= 50].copy()
    dep["rank_citations_per_paper"] = dep.citations_per_paper.rank(ascending=False, method="min").astype(int)
    dep["rank_without_home"] = dep.citations_per_paper_without_home.rank(ascending=False, method="min").astype(int)
    dep = dep.sort_values("cit_home_share", ascending=False)
    save(dep.round(4), "q26_inward_by_department.csv")
    yr = d.groupby(["institution", "year"]).apply(agg).reset_index()[
        ["institution", "year", "papers", "ref_home_share", "ref_self_share", "cit_home_share", "cit_self_share"]]
    save(yr.round(4), "q26_inward_by_year.csv")
    # does citing your own group more go with lower impact? (papers with 10+ references)
    e = d[d.refs >= 10].copy()
    e["home_refs_x10"] = 10 * e.ref_home / e.refs          # effect of +10 percentage points
    e["self_refs_x10"] = 10 * e.ref_self / e.refs
    t, n, _ = ols(e, "log_fwci", num=["log_authors"], cat=["year", "branch"],
                  dummies=["surathkal", "foreign", "indian_collab", "conference", "home_refs_x10"])
    t2, _, _ = ols(e, "log_fwci", num=["log_authors"], cat=["year", "branch"],
                   dummies=["surathkal", "foreign", "indian_collab", "conference", "self_refs_x10"])
    rho = stats.spearmanr(dep.cit_home_share, dep.mean_fwci)
    rho_r = stats.spearmanr(dep.ref_home_share, dep.cit_home_share)
    o = overall.set_index("institution")
    summary = {"papers": len(d), "references": int(d.refs.sum()), "overall": overall.to_dict("records"),
               "fwci_effect_10pt_more_home_refs_pct": t.loc["home_refs_x10", "effect_pct"],
               "fwci_effect_10pt_more_home_refs_ci": [t.loc["home_refs_x10", "effect_ci_low_pct"],
                                                     t.loc["home_refs_x10", "effect_ci_high_pct"]],
               "fwci_effect_10pt_more_home_refs_p": t.loc["home_refs_x10", "p_value"],
               "fwci_effect_10pt_more_self_refs_pct": t2.loc["self_refs_x10", "effect_pct"],
               "fwci_effect_10pt_more_self_refs_p": t2.loc["self_refs_x10", "p_value"],
               "regression_papers": n,
               "spearman_departments_home_citations_vs_fwci": [rho.statistic, rho.pvalue],
               "spearman_departments_home_refs_vs_home_citations": [rho_r.statistic, rho_r.pvalue],
               "most_inward_departments": dep.head(5)[["institution", "department", "cit_home_share",
                                                       "cit_self_share", "ref_home_share"]].to_dict("records"),
               "least_inward_departments": dep.tail(5)[["institution", "department", "cit_home_share"]]
               .to_dict("records"),
               "biggest_rank_changes": dep.assign(change=dep.rank_without_home - dep.rank_citations_per_paper)
               .sort_values("change", key=abs, ascending=False).head(6)[
                   ["institution", "department", "rank_citations_per_paper", "rank_without_home"]].to_dict("records"),
               "home_citation_share_both": o.loc["Both", "cit_home_share"],
               "self_citation_share_both": o.loc["Both", "cit_self_share"]}
    save_json(summary, "inward_summary.json")

    fig, axes = plt.subplots(1, 2, figsize=(14, 6.5))
    dd = dep.sort_values("cit_home_share")
    lab = [f"{a} ({'Tr' if i == 'NIT Trichy' else 'Su'})" for a, i in zip(dd.department, dd.institution)]
    ax = axes[0]
    ax.barh(lab, 100 * dd.cit_self_share, color=INK, label="self-citations (a shared author)")
    ax.barh(lab, 100 * dd.cit_colleague_share, left=100 * dd.cit_self_share, color=AXIS,
            label="colleagues at the same NIT")
    ax.set_xlabel("citations received that come from home (%)")
    ax.set_title("How much of each department's citations come from home?", fontsize=11, loc="left", color=INK)
    ax.legend(frameon=False, fontsize=8.5, loc="lower right"); style_axes(ax); ax.grid(axis="y", visible=False)
    ax.tick_params(axis="y", labelsize=8)
    ax = axes[1]
    for view in NITS:
        y_ = yr[(yr.institution == view) & (yr.year < PARTIAL_YEAR)]       # 2026 is partial
        ax.plot(y_.year, 100 * y_.ref_home_share, color=COLOR[view], lw=2, marker="o", ms=4, label=f"{view}: references")
        ax.plot(y_.year, 100 * y_.cit_home_share, color=COLOR[view], lw=1.5, ls="--", label=f"{view}: citations received")
    ax.set_ylabel("share that is self or own-NIT (%)")
    ax.set_title("Home references and citations, by publication year (2016-2025)", fontsize=11, loc="left", color=INK)
    ax.legend(frameon=False, fontsize=8.5); style_axes(ax)
    savefig(fig, "q26_inward.png")
    print(overall.round(3).T.to_string())
    print(dep.round(3).to_string())
    print(json.dumps({k: v for k, v in summary.items() if k not in ("overall",)}, indent=1, default=str))


# ================================================================ part "manipulation": question 28
HEAVY = 10          # a citing paper that cites 10 or more of our papers is a "heavy" citing paper
MIN_CITES = 100     # faculty need at least this many citations (2016-2026 papers) to be flagged
FLAGS = {"self_share": 0.25, "heavy_share": 0.05, "top_outside_author_share": 0.10}   # shares of ALL citations


def manipulation_part():
    from flow import flow_partners
    from phase2 import CITER_LABELS
    g = pd.read_csv(os.path.join(DATA, "group12_data.csv"), low_memory=False)
    fac = pd.read_csv(os.path.join(DATA, "faculty.csv")).drop_duplicates("faculty_id").set_index("faculty_id")
    works = raw_works()
    wk = {wid: w for (_, wid), w in works.items()}
    ours = set(wk)
    cit = load_links("citers")
    info = {r["id"]: r for r in map(json.loads, open(os.path.join(RAW, "citers_info.jsonl"), encoding="utf-8"))}
    own_ids = set(NAME_TO_ID.values())
    id_name = {v: k for k, v in NAME_TO_ID.items()}
    paper_auth = {wid: authors_of(w) for wid, w in wk.items()}
    # former NIT members: everyone who published with an NIT affiliation, with the first year (as in phase2.py)
    member_since = {}
    for w in wk.values():
        for a in w["authorships"]:
            aid = short(a["author"].get("id"))
            if aid and any(short(i["id"]) in own_ids for i in a["institutions"]):
                member_since[aid] = min(member_since.get(aid, 9999), w["publication_year"])
    by_target = collections.defaultdict(list)
    for c, d in cit.items():
        d["n_ours"] = len(d["cites"] & ours)
        d["outside"] = not (d["insts"] & own_ids)
        d["former_member"] = any(member_since.get(a, 9999) <= (d["year"] or 9999) for a in d["authors"])
        for t in d["cites"]:
            by_target[t].append(c)
    summary = {}

    # ---- (a) citing papers that cite many of our papers
    cp = pd.DataFrame([{"citing_paper": c, "year": d["year"], "our_papers_cited": d["n_ours"],
                        "outside": d["outside"], "former_nit_member_on_it": d["former_member"]} for c, d in cit.items()])
    links = cp.our_papers_cited.sum()
    dist = []
    for k in (1, 2, 5, 10, 20):
        s_ = cp[cp.our_papers_cited >= k]
        o = s_[s_.outside]
        dist.append({"cites_at_least": k, "citing_papers": len(s_), "citation_links": int(s_.our_papers_cited.sum()),
                     "share_of_links": s_.our_papers_cited.sum() / links, "outside_papers": len(o),
                     "outside_links": int(o.our_papers_cited.sum()),
                     "outside_with_former_nit_member": float(o.former_nit_member_on_it.mean()) if len(o) else np.nan})
    dist = pd.DataFrame(dist)
    save(dist.round(4), "q28_heavy_citing_papers_distribution.csv")
    heavy = [c for c, d in cit.items() if d["outside"] and d["n_ours"] >= HEAVY]
    fac_of = g.groupby("openalex_id").author.apply(lambda x: sorted(set(x))).to_dict()
    hrows = []
    for c in sorted(heavy, key=lambda c: -cit[c]["n_ours"]):
        d = cit[c]
        cnt = collections.Counter(a for t in d["cites"] for a in fac_of.get(t, []))
        top, n = top1(cnt)
        i = info.get(c, {})
        hrows.append({"citing_paper": c, "title": i.get("title", ""), "venue": i.get("venue", ""), "year": d["year"],
                      "our_papers_cited": d["n_ours"], "most_cited_faculty": top, "papers_of_that_faculty_cited": n,
                      "former_nit_member_on_it": d["former_member"],
                      "indian_institutes": "; ".join(sorted(d["names"].values()))})
    hv = pd.DataFrame(hrows)
    save(hv, "q28_heavy_outside_citing_papers.csv")
    venues = hv.venue.value_counts().head(8)
    authors_cnt = collections.Counter()
    for c in heavy:
        for a in cit[c]["authors"]:
            authors_cnt[(a, cit[c]["author_names"].get(a, a))] += 1
    top_auth = pd.DataFrame([{"author": nm, "heavy_citing_papers": n, "former_nit_member": a in member_since,
                              "first_year_at_nit": member_since.get(a)} for (a, nm), n in sorted(authors_cnt.items(), key=lambda kv: (-kv[1], kv[0][1]))[:10]])
    save(top_auth, "q28_authors_of_heavy_citing_papers.csv")

    # ---- (b) per faculty: where do their citations come from? (shares of ALL citations of their 2016-26 papers)
    fids = collections.defaultdict(set)
    for f, a in zip(g.faculty_id, g.author_id):
        if isinstance(a, str):
            fids[f].add(a)
    for f, ids in fac.openalex_ids.dropna().items():
        fids[f].update(ids.split(";"))
    fp = g.drop_duplicates(["faculty_id", "openalex_id"])
    papers_of = fp.groupby("faculty_id").openalex_id.apply(list)
    cites_of = fp.groupby("faculty_id").citations.sum()
    frows, self_by_row, heavy_by_row = [], {}, {}
    for f, plist in papers_of.items():
        own = NAME_TO_ID.get(fac.institution.get(f))
        tot = int(cites_of[f])
        n_ind = n_self = n_co = n_own = n_heavy = n_heavy_alum = 0
        outside_auth = collections.Counter()
        for t in plist:
            ns_ = nh_ = 0
            for c in by_target.get(t, []):
                d = cit[c]
                n_ind += 1
                if d["authors"] & fids[f]:
                    n_self += 1; ns_ += 1
                elif d["authors"] & paper_auth.get(t, set()):
                    n_co += 1
                elif own in d["insts"]:
                    n_own += 1
                else:
                    if d["n_ours"] >= HEAVY and d["outside"]:
                        n_heavy += 1; nh_ += 1
                        n_heavy_alum += d["former_member"]
                    for a in d["authors"]:
                        if not (d["auth_insts"].get(a, set()) & own_ids):
                            outside_auth[(a, d["author_names"].get(a, a))] += 1
            self_by_row[(f, t)], heavy_by_row[(f, t)] = ns_, nh_
        (top_a, top_name), top_n = top1(outside_auth, ((None, ""), 0))
        sh = (lambda x: x / tot if tot else np.nan)
        frows.append({"faculty_id": f, "author": fac.author.get(f), "institution": fac.institution.get(f),
                      "department": fac.department.get(f), "designation": fac.designation.get(f),
                      "status": fac.status.get(f), "papers": len(plist), "citations": tot, "indian_citations": n_ind,
                      "self_share": sh(n_self), "coauthor_self_share": sh(n_co), "own_nit_share": sh(n_own),
                      "heavy_share": sh(n_heavy), "heavy_with_former_nit_member": n_heavy_alum / n_heavy if n_heavy else np.nan,
                      "top_outside_author": top_name, "top_outside_author_share": sh(top_n)})
    fr = pd.DataFrame(frows)
    elig = fr.citations >= MIN_CITES
    for m, thr in FLAGS.items():
        fr[f"flag_{m}"] = elig & (fr[m] > thr)
    fr["n_flags"] = fr[[f"flag_{m}" for m in FLAGS]].sum(axis=1)
    save(fr.sort_values("self_share", ascending=False).round(4), "q28_faculty_citation_sources.csv")
    e = fr[elig]
    spread = []
    for m in ("self_share", "coauthor_self_share", "own_nit_share", "heavy_share", "top_outside_author_share"):
        q = e[m].quantile([0.5, 0.9, 0.99])
        spread.append({"measure": m, "faculty": len(e), "median": q[0.5], "p90": q[0.9], "p99": q[0.99],
                       "max": e[m].max(), "flag_above": FLAGS.get(m), "flagged": int((e[m] > FLAGS[m]).sum()) if m in FLAGS else None})
    spread = pd.DataFrame(spread)
    save(spread.round(4), "q28_faculty_citation_source_spread.csv")

    # does the faculty ranking change without self-citations, or without heavy citing papers?
    gg = g.copy()
    gg["cites_no_self"] = [r.citations - self_by_row.get((r.faculty_id, r.openalex_id), 0) for r in gg.itertuples(index=False)]
    gg["cites_no_heavy"] = [r.citations - heavy_by_row.get((r.faculty_id, r.openalex_id), 0) for r in gg.itertuples(index=False)]
    r0 = ranking_scores(gg, fac)
    rk = pd.DataFrame({"author": fac.author.reindex(r0.index), "institution": fac.institution.reindex(r0.index),
                       "rank": r0.rank(ascending=False, method="min")})
    rsum = {}
    for col, lab in (("cites_no_self", "without self-citations"), ("cites_no_heavy", "without heavy citing papers")):
        r1 = ranking_scores(gg, fac, col).reindex(r0.index)
        rk[f"rank_{col}"] = r1.rank(ascending=False, method="min")
        t20a, t20b = set(r0.nlargest(20).index), set(r1.nlargest(20).index)
        rsum[lab] = {"spearman": stats.spearmanr(r0, r1).statistic, "top20_overlap": len(t20a & t20b),
                     "left_top20": sorted(fac.author.reindex(list(t20a - t20b))),
                     "entered_top20": sorted(fac.author.reindex(list(t20b - t20a))),
                     "largest_drop": rk.assign(ch=rk[f"rank_{col}"] - rk["rank"]).nlargest(3, "ch")[
                         ["author", "rank", f"rank_{col}"]].to_dict("records")}
    save(rk.sort_values("rank").reset_index().round(1), "q28_ranking_without_self_or_heavy_citations.csv")

    # ---- (c) the 40 institutes that cite us most (phase2.py citers)
    cn = pd.read_csv(os.path.join(DATA, "citation_network.csv"), usecols=["source_id", "target_id"], low_memory=False)
    corpus = set(g.openalex_id)
    cn = cn[cn.target_id.isin(corpus)]
    own_of = g.groupby("openalex_id").institution.apply(lambda x: {NAME_TO_ID[v] for v in x}).to_dict()
    fac_on = g.groupby(["institution", "openalex_id"]).author.apply(list).to_dict()

    def ind(w):
        return {short(i["id"]) for a in w["authorships"] for i in a["institutions"] if i.get("country_code") == "IN"}
    rec = []
    for s_, t in zip(cn.source_id, cn.target_id):
        if s_ in wk:
            s_ind = ind(wk[s_])
            s_auth_inst = collections.defaultdict(set)
            for a in wk[s_]["authorships"]:
                if a["author"].get("id"):
                    s_auth_inst[short(a["author"]["id"])] |= {short(i["id"]) for i in a["institutions"]}
            n_ours_s = len({short(x) for x in wk[s_]["referenced_works"]} & ours)
        elif s_ in cit:
            s_ind, s_auth_inst, n_ours_s = cit[s_]["insts"], cit[s_]["auth_insts"], cit[s_]["n_ours"]
        else:
            continue
        t_ind = ind(wk[t])
        for n in own_of[t]:
            for x in flow_partners(n, t_ind, s_ind) - own_ids:
                if x in CITER_LABELS:
                    rec.append((x, s_, n_ours_s, [a for a, ins in s_auth_inst.items() if x in ins],
                                fac_on.get((id_name[n], t), [])))
    ed = pd.DataFrame(rec, columns=["partner_id", "source", "n_ours", "authors_at_partner", "faculty"])
    ref = pd.read_csv(os.path.join(DATA, "analysis", "phase2", "citers_by_institute.csv")).set_index("partner_id")
    irows = []
    for x, (name, label) in CITER_LABELS.items():
        e_ = ed[ed.partner_id == x]
        assert len(e_) == ref.citations_to_us.get(x), (x, len(e_), ref.citations_to_us.get(x))
        auth_cnt = collections.Counter(a for lst in e_.authors_at_partner for a in set(lst))
        fac_cnt = collections.Counter()
        for lst in e_.faculty:
            for f in lst:
                fac_cnt[f] += 1 / len(lst)
        n = len(e_)
        ta, tn = top1(auth_cnt)
        tf, tfn = top1(fac_cnt)
        aname = next((cit[s_]["author_names"][ta] for s_ in e_.source if s_ in cit and ta in cit[s_]["author_names"]), ta)
        irows.append({"institute": name, "type": label, "citations_to_us": n,
                      "from_heavy_citing_papers": (e_.n_ours >= HEAVY).mean(),
                      "top_author_at_institute": aname, "top_author_share": tn / n,
                      "top_author_is_former_nit_member": ta in member_since,
                      "top_cited_faculty": tf, "top_faculty_share": tfn / n})
    ir = pd.DataFrame(irows).sort_values("citations_to_us", ascending=False)
    save(ir.round(4), "q28_citing_institutes.csv")
    mw = {m: stats.mannwhitneyu(ir[ir.type == "private"][m], ir[ir.type == "public"][m]).pvalue
          for m in ("from_heavy_citing_papers", "top_author_share", "top_faculty_share")}
    pv = ir.groupby("type")[["from_heavy_citing_papers", "top_author_share", "top_faculty_share"]].median()

    summary = {"indian_citing_papers": len(cp), "indian_citation_links": int(links), "heavy_threshold": HEAVY,
               "min_citations": MIN_CITES, "flags": FLAGS, "distribution": dist.to_dict("records"),
               "heavy_outside_papers": len(heavy), "heavy_outside_with_former_nit_member": float(hv.former_nit_member_on_it.mean()),
               "heavy_outside_years": hv.year.value_counts().sort_index().to_dict(),
               "heavy_outside_top_venues": venues.to_dict(),
               "heavy_outside_by_faculty": hv.most_cited_faculty.value_counts().head(6).to_dict(),
               "top_authors_of_heavy_papers": top_auth.to_dict("records"),
               "faculty_eligible": int(elig.sum()), "spread": spread.to_dict("records"),
               "flagged_faculty": fr[fr.n_flags > 0][["author", "institution", "department", "citations", "self_share",
                                                     "heavy_share", "heavy_with_former_nit_member", "top_outside_author",
                                                     "top_outside_author_share"]].to_dict("records"),
               "ranking": rsum, "institutes": {"median_by_type": pv.to_dict(), "private_vs_public_p": mw,
                                               "most_heavy": ir.nlargest(5, "from_heavy_citing_papers")[
                                                   ["institute", "type", "from_heavy_citing_papers"]].to_dict("records"),
                                               "most_one_author": ir.nlargest(5, "top_author_share")[
                                                   ["institute", "type", "top_author_at_institute", "top_author_share",
                                                    "top_author_is_former_nit_member"]].to_dict("records")}}
    save_json(summary, "manipulation_summary.json")

    fig, axes = plt.subplots(1, 2, figsize=(14, 5.4))
    ax = axes[0]
    for m, lab, col in (("self_share", "own self-citations", INK), ("heavy_share", f"papers citing {HEAVY}+ of ours", ORANGE),
                        ("top_outside_author_share", "the single biggest outside citing author", BLUE)):
        v = np.sort(100 * e[m].dropna().values)
        ax.plot(v, 100 * (1 - np.arange(len(v)) / len(v)), color=col, lw=2, label=lab)
    ax.set_xlabel("share of the faculty member's citations (%)"); ax.set_ylabel("faculty with at least this share (%)")
    ax.set_yscale("log")
    ax.set_title(f"Where do faculty citations come from? ({len(e)} faculty with {MIN_CITES}+ citations)",
                 fontsize=11, loc="left", color=INK)
    ax.legend(frameon=False, fontsize=9); style_axes(ax)
    ax = axes[1]
    yrs = sorted(hv.year.dropna().unique())
    ax.bar([str(int(y)) for y in yrs], [int((hv.year == y).sum()) for y in yrs], color=MUTED, width=0.6)
    ax.set_ylabel(f"outside papers citing {HEAVY}+ of our papers")
    ax.set_title("Heavy citing papers by year", fontsize=11, loc="left", color=INK)
    style_axes(ax)
    savefig(fig, "q28_citation_checks.png")
    print(dist.round(3).to_string()); print(spread.round(3).to_string()); print(top_auth.to_string())
    print(ir.round(3).head(15).to_string())
    print(json.dumps({k: v for k, v in summary.items() if k in ("flagged_faculty", "ranking", "institutes",
                                                                "heavy_outside_by_faculty", "heavy_outside_top_venues",
                                                                "heavy_outside_with_former_nit_member")}, indent=1, default=str))


PARTS = {"collab": collab_part, "network": network_part, "people": people_part, "venues": venues_part,
         "richer": richer_part, "robust": robust_part, "inward": inward_part, "manipulation": manipulation_part}


def main():
    os.makedirs(OUT, exist_ok=True)
    for part in sys.argv[1:] or list(PARTS):
        print(f"=== {part}")
        PARTS[part]()


if __name__ == "__main__":
    main()
