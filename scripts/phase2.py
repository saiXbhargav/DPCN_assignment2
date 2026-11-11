"""Phase II additions asked for by the professor.

  python phase2.py [papers] [citers]          (no argument = both)

  papers  1. Publication statistics that also count papers by students / other NIT staff (no faculty author),
             science / engineering fields only, side by side with the faculty-only numbers. Writes
             data/all_papers.csv (one row per NIT and paper); group12_data.csv, the networks and the faculty
             rankings stay faculty-only.
          3. Flags: papers with 10+ (50+, 100+) authors, and faculty with very high career citations or whose
             citations come mostly from large-team papers.
          4. Papers by number of authors: fewer than 10 vs 10 or more.
          5. Q1 papers in journals with IF > 5 and IF > 10 (both conditions together).
          6. Number of collaborating institutions per year (all, Indian, foreign; countries).
  citers  2. Why do private institutes cite us so much? The 40 institutes that cite us most, labelled private or
             public by hand (CITER_LABELS), compared on size, distance, personal ties, citation packing,
             concentration on a few of our faculty, timing and the impact of the citing papers.
             Needs fetch_insights.py citerout (paper counts) and geo (coordinates).

Uses the same rules as build_dataset.py (quartiles, IF, FWCI, excluded fields) and flow.py (citation credit).
Outputs: data/all_papers.csv and data/analysis/phase2/.
"""
import collections
import itertools
import json
import os
import re
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

from fetch_works import INSTITUTIONS, RAW, ROOT

DATA = os.path.join(ROOT, "data")
OUT = os.path.join(DATA, "analysis", "phase2")
OWN = {v: k for k, v in INSTITUTIONS.items()}          # id -> "NIT Trichy"
NAME_TO_ID = dict(INSTITUTIONS)
LARGE = 10                                             # "large team" = 10 or more authors
PARTIAL_YEAR = 2026
HIGH_CITATIONS = 100_000                               # "1 lakh"

# The 40 institutes that cite our faculty papers most (indian_connections.csv, both NITs), labelled by hand from
# their official status: private = private / deemed-to-be private universities and self-financing colleges;
# public = central or state government institutions.
CITER_LABELS = {
    "I876193797": ("Vellore Institute of Technology (VIT)", "private"),
    "I85461943": ("Saveetha University", "private"),
    "I145286018": ("SRM Institute of Science and Technology", "private"),
    "I164861460": ("Manipal Academy of Higher Education", "private"),
    "I33585257": ("Anna University", "public"),
    "I65674248": ("Visvesvaraya Technological University", "public"),
    "I101407740": ("Chandigarh University", "private"),
    "I154851008": ("IIT Roorkee", "public"),
    "I110360157": ("Lovely Professional University", "private"),
    "I81556334": ("Amrita Vishwa Vidyapeetham", "private"),
    "I24676775": ("IIT Madras", "public"),
    "I68891433": ("IIT Delhi", "public"),
    "I1330855593": ("Vel Tech R&D Institute of Science and Technology", "private"),
    "I145894827": ("IIT Kharagpur", "public"),
    "I99364266": ("Academy of Scientific and Innovative Research (CSIR)", "public"),
    "I59270414": ("IISc Bangalore", "public"),
    "I106826634": ("Jain University", "private"),
    "I74319210": ("Chitkara University", "private"),
    "I151903974": ("NIT Silchar", "public"),
    "I875944469": ("Koneru Lakshmaiah Education Foundation", "private"),
    "I60054993": ("Graphic Era University", "private"),
    "I16292982": ("NIT Rourkela", "public"),
    "I189109744": ("IIT (ISM) Dhanbad", "public"),
    "I56404289": ("IIT (BHU) Varanasi", "public"),
    "I65220239": ("Karpagam Academy of Higher Education", "private"),
    "I121750182": ("NIT Warangal", "public"),
    "I170979836": ("Jadavpur University", "public"),
    "I1317621060": ("IIT Guwahati", "public"),
    "I162827531": ("IIT Bombay", "public"),
    "I191972202": ("Amity University", "private"),
    "I110166357": ("University of Delhi", "public"),
    "I83205935": ("MNIT Jaipur", "public"),
    "I863896202": ("Delhi Technological University", "public"),
    "I878213199": ("Savitribai Phule Pune University", "public"),
    "I43814544": ("Sathyabama Institute of Science and Technology", "private"),
    "I4405268608": ("Nitte Meenakshi Institute of Technology", "private"),
    "I916357946": ("SSN College of Engineering", "private"),
    "I11793825": ("NIT Patna", "public"),
    "I74796645": ("BITS Pilani", "private"),
    "I91357014": ("Banaras Hindu University", "public"),
}
PROCEEDINGS = re.compile(r"proceedings|conference|lecture notes|symposium|workshop|congress", re.I)


def short(url):
    return (url or "").rsplit("/", 1)[-1]


def save(df, name, index=False):
    df.to_csv(os.path.join(OUT, name), index=index)


def raw_works():
    """{(institution name, paper id): work} for every paper in the raw downloads."""
    out = {}
    for name in INSTITUTIONS:
        for line in open(os.path.join(RAW, name.replace(" ", "_") + "_works.jsonl"), encoding="utf-8"):
            w = json.loads(line)
            out[(name, short(w["id"]))] = w
    return out


# ================================================================ part "papers": tasks 1, 3, 4, 5, 6
def build_all_papers(works):
    from build_dataset import (EXCLUDED_FIELDS, core_rank, load_core, load_impact, load_journal_if,
                               load_quartiles, quartile)
    qtab, core, impact, jif = load_quartiles(), load_core(), load_impact(), load_journal_if()
    fac = pd.read_csv(os.path.join(DATA, "group12_data.csv"), usecols=["institution", "openalex_id"])
    fac_set = set(zip(fac.institution, fac.openalex_id))

    rows, partners, excluded = [], {}, collections.Counter()
    for (inst, wid), w in works.items():
        inst_id = NAME_TO_ID[inst]
        topic = w.get("primary_topic") or {}
        field = (topic.get("field") or {}).get("display_name", "")
        if field in EXCLUDED_FIELDS:
            excluded["excluded field"] += 1
            continue
        if not any(short(i["id"]) == inst_id for a in w["authorships"] for i in a["institutions"]):
            excluded["no author with this NIT's affiliation"] += 1
            continue
        src = (w.get("primary_location") or {}).get("source") or {}
        venue = src.get("display_name") or ""
        is_conf = w["type"] == "conference-paper" or src.get("type") == "conference"
        issns = src.get("issn") or []
        year = w["publication_year"]
        q = core_rank(venue, core) if is_conf else quartile(issns, year, qtab)
        others = {(short(i["id"]), i.get("country_code") or "") for a in w["authorships"] for i in a["institutions"]
                  if short(i["id"]) != inst_id}
        partners[(inst, wid)] = others
        imp = impact.get(wid, {})
        rows.append({
            "institution": inst, "openalex_id": wid, "doi": w.get("doi") or "", "title": w["title"], "year": year,
            "type": "conference" if is_conf else "journal", "journal_name": venue,
            "issn": ";".join(issns) if not is_conf else "", "quartile": q,
            "journal_if_2yr": None if is_conf else jif.get(short(src.get("id"))),
            "citations": w["cited_by_count"], "fwci": imp.get("fwci"), "top10pct": imp.get("top_10pct"),
            "n_authors": len(w["authorships"]), "field": field,
            "subfield": (topic.get("subfield") or {}).get("display_name", ""),
            "has_faculty_author": (inst, wid) in fac_set,
            "n_partner_institutions": len({i for i, _ in others}),
            "n_indian_partners": len({i for i, c in others if c == "IN"}),
            "n_foreign_partners": len({i for i, c in others if c and c != "IN"}),
        })
    ap = pd.DataFrame(rows)
    ap["large_team_10plus"] = ap.n_authors >= LARGE
    ap["large_team_50plus"] = ap.n_authors >= 50
    ap["large_team_100plus"] = ap.n_authors >= 100
    ap.to_csv(os.path.join(DATA, "all_papers.csv"), index=False)

    # checks: the faculty part must be exactly group12_data.csv, with the same quartile / IF / type
    g = pd.read_csv(os.path.join(DATA, "group12_data.csv"), low_memory=False) \
        .drop_duplicates(["institution", "openalex_id"]).set_index(["institution", "openalex_id"])
    f = ap[ap.has_faculty_author].set_index(["institution", "openalex_id"])
    assert set(f.index) == set(g.index), "faculty papers differ from group12_data.csv"
    for c in ["quartile", "journal_if_2yr", "type", "citations"]:
        a, b = f[c].reindex(g.index).replace("", np.nan), g[c].replace("", np.nan)   # blank = missing
        same = (a.fillna("NA").astype(str) == b.fillna("NA").astype(str)) | (
            pd.to_numeric(a, errors="coerce").round(6) == pd.to_numeric(b, errors="coerce").round(6))
        assert same.all(), f"column {c} differs from group12_data.csv for {(~same).sum()} papers"
    return ap, partners, excluded


def pub_stats(d):
    j = d[d.type == "journal"]
    ranked = j[j.quartile.isin(["Q1", "Q2", "Q3", "Q4"])]
    q1 = j.quartile == "Q1"
    return pd.Series({
        "papers": len(d), "journal_papers": len(j), "conference_papers": int((d.type == "conference").sum()),
        "Q1": int(q1.sum()), "Q2": int((j.quartile == "Q2").sum()), "Q3": int((j.quartile == "Q3").sum()),
        "Q4": int((j.quartile == "Q4").sum()),
        "Q1_share_of_ranked_pct": 100 * q1.sum() / max(len(ranked), 1),
        "IF_gt_5": int((j.journal_if_2yr > 5).sum()), "IF_gt_10": int((j.journal_if_2yr > 10).sum()),
        "Q1_and_IF_gt_5": int((q1 & (j.journal_if_2yr > 5)).sum()),
        "Q1_and_IF_gt_10": int((q1 & (j.journal_if_2yr > 10)).sum()),
        "Q1_and_IF_gt_5_pct_of_journal": 100 * (q1 & (j.journal_if_2yr > 5)).sum() / max(len(j), 1),
        "Q1_and_IF_gt_10_pct_of_journal": 100 * (q1 & (j.journal_if_2yr > 10)).sum() / max(len(j), 1),
        "citations": int(d.citations.sum()), "citations_per_paper": d.citations.mean(),
        "mean_fwci": d.fwci.mean(), "top10pct_share_pct": 100 * (d.top10pct == True).mean(),  # noqa: E712
        "papers_lt10_authors": int((d.n_authors < LARGE).sum()),
        "papers_10plus_authors": int((d.n_authors >= LARGE).sum()),
        "share_10plus_authors_pct": 100 * (d.n_authors >= LARGE).mean(),
    })


def scopes(ap):
    """(scope label, data) pairs; 'Both NITs' counts a paper once even if both NITs are on it."""
    for scope, d in [("faculty papers", ap[ap.has_faculty_author]), ("all papers (incl. students)", ap)]:
        for inst in [*INSTITUTIONS, "Both NITs"]:
            sub = d.drop_duplicates("openalex_id") if inst == "Both NITs" else d[d.institution == inst]
            yield scope, inst, sub


def papers_part():
    works = raw_works()
    ap, partners, excluded = build_all_papers(works)

    # ---- task 1: publication statistics, both scopes
    st = pd.DataFrame([{"scope": s, "institution": i, **pub_stats(d)} for s, i, d in scopes(ap)])
    save(st.round(2), "publication_statistics_both_scopes.csv")
    trend = pd.concat([d.groupby("year").size().rename("papers").reset_index().assign(scope=s, institution=i)
                       for s, i, d in scopes(ap)])
    save(trend.pivot_table(index="year", columns=["scope", "institution"], values="papers").reset_index(),
         "publication_trend_both_scopes.csv")
    only_students = ap[~ap.has_faculty_author]
    tj = []
    for s, i, d in scopes(ap):
        if i == "Both NITs":
            continue
        t = (d[d.type == "journal"].groupby("journal_name")
             .agg(papers=("openalex_id", "size"), quartile=("quartile", lambda x: x.mode().iat[0] if len(x.mode()) else ""),
                  journal_if_2yr=("journal_if_2yr", "first")).sort_values("papers", ascending=False).head(15)
             .reset_index().assign(scope=s, institution=i))
        tj.append(t)
    save(pd.concat(tj).round(2), "top_journals_both_scopes.csv")
    s_only = only_students.drop_duplicates(["institution", "openalex_id"])
    student_profile = pd.DataFrame({
        "student_only_papers": s_only.groupby("institution").size(),
        "mean_fwci": s_only.groupby("institution").fwci.mean(),
        "citations_per_paper": s_only.groupby("institution").citations.mean(),
        "conference_share_pct": s_only.groupby("institution").type.apply(lambda x: 100 * (x == "conference").mean()),
        "with_outside_coauthor_pct": s_only.groupby("institution").n_partner_institutions.apply(
            lambda x: 100 * (x > 0).mean()),
    }).reset_index()
    save(student_profile.round(2), "student_only_papers_profile.csv")

    # ---- task 4: author-count classes
    rows = []
    for s, i, d in scopes(ap):
        for label, m in [("fewer than 10 authors", d.n_authors < LARGE), ("10 or more authors", d.n_authors >= LARGE)]:
            x = d[m]
            rows.append({"scope": s, "institution": i, "authors": label, "papers": len(x),
                         "share_of_papers_pct": 100 * len(x) / max(len(d), 1),
                         "citations": int(x.citations.sum()),
                         "share_of_citations_pct": 100 * x.citations.sum() / max(d.citations.sum(), 1),
                         "citations_per_paper": x.citations.mean(), "mean_fwci": x.fwci.mean(),
                         "median_authors": x.n_authors.median()})
    ac = pd.DataFrame(rows)
    save(ac.round(2), "author_count_classes.csv")
    acy = (ap.assign(cls=np.where(ap.n_authors >= LARGE, "10 or more authors", "fewer than 10 authors"))
             .drop_duplicates("openalex_id").groupby(["year", "cls"]).size().unstack(fill_value=0).reset_index())
    save(acy, "author_count_classes_by_year.csv")

    # ---- task 5: Q1 x IF by branch (faculty papers; a paper counts once per branch)
    g = pd.read_csv(os.path.join(DATA, "group12_data.csv"), low_memory=False)
    gb = g.drop_duplicates(["institution", "openalex_id", "department"])
    j = gb[gb.type == "journal"]
    br = j.groupby(["institution", "department"]).apply(lambda x: pd.Series({
        "journal_papers": len(x), "Q1": int((x.quartile == "Q1").sum()),
        "IF_gt_5": int((x.journal_if_2yr > 5).sum()), "IF_gt_10": int((x.journal_if_2yr > 10).sum()),
        "Q1_and_IF_gt_5": int(((x.quartile == "Q1") & (x.journal_if_2yr > 5)).sum()),
        "Q1_and_IF_gt_10": int(((x.quartile == "Q1") & (x.journal_if_2yr > 10)).sum()),
        "Q1_and_IF_gt_5_pct": 100 * ((x.quartile == "Q1") & (x.journal_if_2yr > 5)).mean(),
    }), include_groups=False).reset_index().sort_values(["institution", "Q1_and_IF_gt_5"], ascending=[True, False])
    save(br.round(2), "q1_if_by_branch.csv")
    q1y = (ap[ap.type == "journal"].assign(q1_if5=lambda x: (x.quartile == "Q1") & (x.journal_if_2yr > 5),
                                           q1_if10=lambda x: (x.quartile == "Q1") & (x.journal_if_2yr > 10))
           .groupby(["has_faculty_author", "institution", "year"])[["q1_if5", "q1_if10"]].sum().reset_index())
    save(q1y, "q1_if_by_year.csv")

    # ---- task 6: collaborating institutions per year
    rows = []
    for scope, d in [("faculty papers", ap[ap.has_faculty_author]), ("all papers (incl. students)", ap)]:
        for inst in [*INSTITUTIONS, "Both NITs"]:
            sub = d if inst == "Both NITs" else d[d.institution == inst]
            for y, dy in sub.groupby("year"):
                ps = set().union(*[partners[k] for k in zip(dy.institution, dy.openalex_id)])
                if inst == "Both NITs":
                    ps = {(i, c) for i, c in ps if i not in OWN}   # the other NIT is not a partner of "both"
                rows.append({"scope": scope, "institution": inst, "year": y, "papers": dy.openalex_id.nunique(),
                             "collaborating_institutions": len({i for i, _ in ps}),
                             "indian_institutions": len({i for i, c in ps if c == "IN"}),
                             "foreign_institutions": len({i for i, c in ps if c and c != "IN"}),
                             "countries": len({c for _, c in ps if c and c != "IN"}),
                             "papers_with_outside_coauthor_pct": 100 * (dy.drop_duplicates("openalex_id")
                                                                        .n_partner_institutions > 0).mean(),
                             "partial_year": y == PARTIAL_YEAR})
    cy = pd.DataFrame(rows)
    save(cy.round(2), "collaborating_institutions_by_year.csv")
    tot = []
    for scope, d in [("faculty papers", ap[ap.has_faculty_author]), ("all papers (incl. students)", ap)]:
        for inst in INSTITUTIONS:
            ps = set().union(*[partners[k] for k in zip(d.institution, d.openalex_id) if k[0] == inst])
            tot.append({"scope": scope, "institution": inst, "collaborating_institutions": len({i for i, _ in ps}),
                        "indian_institutions": len({i for i, c in ps if c == "IN"}),
                        "foreign_institutions": len({i for i, c in ps if c and c != "IN"}),
                        "countries": len({c for _, c in ps if c and c != "IN"})})
    save(pd.DataFrame(tot), "collaborating_institutions_total.csv")

    # ---- task 3: large-team papers and high-citation faculty
    big = ap[ap.large_team_10plus].copy()
    names = g.groupby(["institution", "openalex_id"]).author.apply(lambda s: "; ".join(sorted(set(s))))
    big["faculty_on_paper"] = [names.get((i, w), "") for i, w in zip(big.institution, big.openalex_id)]
    save(big.sort_values("n_authors", ascending=False)[
        ["institution", "openalex_id", "doi", "title", "year", "n_authors", "field", "journal_name", "citations",
         "fwci", "has_faculty_author", "faculty_on_paper", "large_team_50plus", "large_team_100plus"]],
         "flag_large_team_papers.csv")

    fac = pd.read_csv(os.path.join(DATA, "faculty.csv"))
    profiles = {}
    for fn in ("authors.jsonl", "authors_extra.jsonl"):
        p = os.path.join(RAW, fn)
        if os.path.exists(p):
            for line in open(p, encoding="utf-8"):
                r = json.loads(line)
                profiles[short(r["id"])] = r
    fp = g.drop_duplicates(["faculty_id", "openalex_id"])
    by_f = fp.groupby("faculty_id")
    exp = pd.DataFrame({
        "papers": by_f.size(), "papers_10plus_authors": by_f.n_authors.apply(lambda s: int((s >= LARGE).sum())),
        "max_authors": by_f.n_authors.max(), "citations_2016_2026": by_f.citations.sum(),
        "citations_from_10plus_author_papers": by_f.apply(lambda x: x.citations[x.n_authors >= LARGE].sum(),
                                                         include_groups=False)})
    exp["share_citations_from_10plus_pct"] = 100 * exp.citations_from_10plus_author_papers / \
        exp.citations_2016_2026.replace(0, np.nan)
    info = fac.set_index("faculty_id")
    # career citations: sum over all of the person's OpenAlex IDs (OpenAlex splits people; IDs hold different works)
    exp["career_citations_openalex"] = [sum((profiles.get(a) or {}).get("cited_by_count") or 0
                                            for a in str(info.loc[f, "openalex_ids"]).split(";"))
                                        if f in info.index else np.nan for f in exp.index]
    exp = exp.join(info[["author", "institution", "department", "status"]])
    exp["flag_career_citations_1_lakh"] = exp.career_citations_openalex >= HIGH_CITATIONS
    exp["flag_mostly_large_team"] = exp.share_citations_from_10plus_pct >= 50
    # a huge career total of which almost nothing comes from the NIT papers usually means OpenAlex merged several
    # people with the same name into one profile
    exp["nit_share_of_career_citations_pct"] = 100 * exp.citations_2016_2026 / exp.career_citations_openalex
    exp["flag_possible_openalex_name_merge"] = (exp.career_citations_openalex >= 10_000) & \
        (exp.nit_share_of_career_citations_pct < 5)
    save(exp.reset_index().sort_values("career_citations_openalex", ascending=False).round(1),
         "flag_faculty_citations_and_large_teams.csv")
    # every NIT author with a downloaded profile (students included): anyone near 1 lakh?
    allp = sorted(((r.get("cited_by_count") or 0, r.get("display_name"), short(r["id"])) for r in profiles.values()),
                  reverse=True)[:15]
    save(pd.DataFrame(allp, columns=["career_citations_openalex", "name", "openalex_author_id"]),
         "flag_top_career_citations_any_nit_author.csv")

    # ---- chart: publication trend in both scopes + collaborating institutions per year
    fig, ax = plt.subplots(1, 2, figsize=(13, 4.8))
    t = trend[trend.institution != "Both NITs"]
    for (s, i), d in t.groupby(["scope", "institution"]):
        ax[0].plot(d.year, d.papers, "o-" if s.startswith("all") else "s--",
                   color="C0" if i == "NIT Trichy" else "C1", label=f"{i}, {s}")
    ax[0].set_title("Papers per year: faculty papers vs all papers (2026 partial)"); ax[0].legend(fontsize=7)
    ax[0].grid(alpha=0.3)
    c = cy[(cy.scope.str.startswith("all")) & (cy.institution != "Both NITs") & ~cy.partial_year]
    for i, d in c.groupby("institution"):
        col = "C0" if i == "NIT Trichy" else "C1"
        ax[1].plot(d.year, d.indian_institutions, "o-", color=col, label=f"{i}: Indian")
        ax[1].plot(d.year, d.foreign_institutions, "s--", color=col, label=f"{i}: foreign")
    ax[1].set_title("Distinct collaborating institutions per year (all papers)"); ax[1].legend(fontsize=7)
    ax[1].grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "phase2_trend_and_collaborators.png"), dpi=150)
    plt.close(fig)

    summary = {
        "rows_all_papers_csv": len(ap), "faculty_rows": int(ap.has_faculty_author.sum()),
        "student_or_staff_only_rows": int((~ap.has_faculty_author).sum()),
        "unique_papers_all": ap.openalex_id.nunique(),
        "unique_papers_faculty": ap[ap.has_faculty_author].openalex_id.nunique(),
        "excluded": dict(excluded),
        "large_team_papers_all": {k: int(ap.drop_duplicates("openalex_id")[c].sum()) for k, c in
                                  [("10+", "large_team_10plus"), ("50+", "large_team_50plus"),
                                   ("100+", "large_team_100plus")]},
        "faculty_flagged_1_lakh": int(exp.flag_career_citations_1_lakh.sum()),
        "faculty_flagged_mostly_large_team": int(exp.flag_mostly_large_team.sum()),
        "faculty_flagged_possible_name_merge": exp.index[exp.flag_possible_openalex_name_merge].tolist(),
        "max_career_citations_faculty": float(exp.career_citations_openalex.max()),
        "max_career_citations_any_nit_author": allp[0][0],
    }
    with open(os.path.join(OUT, "phase2_papers_summary.json"), "w") as f:
        json.dump(summary, f, indent=2, default=float)
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40)
    print(json.dumps(summary, indent=2))
    print(st.round(2).T.to_string())
    print(ac.round(2).to_string(index=False))
    print(br.round(1).head(12).to_string(index=False))
    print(cy[cy.scope.str.startswith("all")].round(1).to_string(index=False))
    print(pd.DataFrame(tot).to_string(index=False))
    print(student_profile.round(2).to_string(index=False))
    print(exp.sort_values("career_citations_openalex", ascending=False).head(8)[
        ["author", "department", "career_citations_openalex", "papers_10plus_authors", "max_authors",
         "share_citations_from_10plus_pct"]].round(1).to_string())
    print(exp.sort_values("share_citations_from_10plus_pct", ascending=False).head(8)[
        ["author", "department", "papers", "papers_10plus_authors", "share_citations_from_10plus_pct"]]
          .round(1).to_string())
    print(allp[:5])


# ================================================================ part "citers": task 2
def citers_part():
    from flow import flow_partners
    from insights import haversine_km

    g = pd.read_csv(os.path.join(DATA, "group12_data.csv"), low_memory=False)
    corpus = set(g.openalex_id)
    works = {wid: w for (_, wid), w in raw_works().items()}
    own = g.groupby("openalex_id").institution.apply(lambda s: {NAME_TO_ID[x] for x in s}).to_dict()
    fac_on = g.groupby(["institution", "openalex_id"]).faculty_id.apply(set).to_dict()
    year_of = {wid: w["publication_year"] for wid, w in works.items()}

    def indian(w_auth):
        return {short(i["id"]) for a in w_auth for i in a["institutions"] if i.get("country_code") == "IN"}

    def authors_of(w_auth):
        return {short(a["author"]["id"]) for a in w_auth if a["author"]["id"]}

    citers = {}
    for line in open(os.path.join(RAW, "links_citers.jsonl"), encoding="utf-8"):
        r = json.loads(line)
        if r["id"] in citers:
            citers[r["id"]]["cites_ours"] = sorted(set(citers[r["id"]]["cites_ours"]) | set(r["cites_ours"]))
        else:
            citers[r["id"]] = r
    info = {}
    for line in open(os.path.join(RAW, "citers_info.jsonl"), encoding="utf-8"):
        r = json.loads(line)
        info[r["id"]] = r

    def src_meta(s):
        if s in works:
            w = works[s]
            return (indian(w["authorships"]), authors_of(w["authorships"]), w["publication_year"],
                    ((w.get("primary_location") or {}).get("source") or {}).get("display_name") or "",
                    w["cited_by_count"])
        r = citers[s]
        i = info.get(s, {})
        return ({x[0] for a in r["authors"] for x in a["inst"] if x[2] == "IN"}, {a["id"] for a in r["authors"] if a["id"]},
                r.get("year") or i.get("year"), i.get("venue") or "", i.get("cited_by_count"))

    # personal ties: who has ever published with each NIT's affiliation (students, staff, post-docs, faculty),
    # and who co-authored with each faculty member, with the first year
    nit_member = collections.defaultdict(lambda: 9999)        # (author id, nit id) -> first year
    for wid, w in works.items():
        y = w["publication_year"]
        for a in w["authorships"]:
            aid = short(a["author"]["id"])
            for i in a["institutions"]:
                if short(i["id"]) in OWN and aid:
                    nit_member[(aid, short(i["id"]))] = min(nit_member[(aid, short(i["id"]))], y)
    fac_ids = collections.defaultdict(set)                     # faculty id -> their OpenAlex ids
    for f, a in zip(g.faculty_id, g.author_id):
        if isinstance(a, str) and a:
            fac_ids[f].add(a)
    fac_aids_by_nit = {n: set(g.author_id[(g.institution == n) & g.author_id.notna()]) for n in INSTITUTIONS}
    coauth = collections.defaultdict(lambda: collections.defaultdict(lambda: 9999))   # faculty -> author -> year
    for (inst, wid), fs in fac_on.items():
        w = works[wid]
        ids = authors_of(w["authorships"])
        for f in fs:
            for a in ids - fac_ids[f]:
                coauth[f][a] = min(coauth[f][a], w["publication_year"])

    cit = pd.read_csv(os.path.join(DATA, "citation_network.csv"), usecols=["source_id", "target_id", "edge_type"],
                      low_memory=False)
    cit = cit[cit.target_id.isin(corpus)]
    meta_cache = {}
    rec = []
    for s, t in zip(cit.source_id, cit.target_id):
        if s not in meta_cache:
            meta_cache[s] = src_meta(s)
        s_ind, s_auth, s_year, s_venue, s_cbc = meta_cache[s]
        t_ind = indian(works[t]["authorships"])
        t_auth = authors_of(works[t]["authorships"])
        for n in own[t]:
            credited = flow_partners(n, t_ind, s_ind) - set(OWN)
            if not credited:
                continue
            nname = OWN[n]
            fs = fac_on.get((nname, t), set())
            yr = s_year or 9999
            if s_auth & t_auth:
                tie = "same person on both papers"
            elif s_auth & fac_aids_by_nit[nname]:
                tie = "cited NIT's faculty on citing paper"
            elif any(nit_member.get((a, n), 9999) <= yr for a in s_auth):
                tie = "former NIT member (alumnus)"
            elif any(coauth[f].get(a, 9999) <= yr for f in fs for a in s_auth):
                tie = "earlier co-author of the cited faculty"
            else:
                tie = "no personal tie found"
            for x in credited:
                rec.append((nname, x, s, t, s_year, s_venue, s_cbc, tie, ";".join(sorted(fs))))
    ed = pd.DataFrame(rec, columns=["nit", "partner_id", "source", "target", "citing_year", "citing_venue",
                                    "citing_paper_citations", "tie", "cited_faculty"])

    # check: our recount equals cites_from_partner in indian_connections.csv for every labelled institute
    ic = pd.read_csv(os.path.join(DATA, "indian_connections.csv"))
    mine = ed.groupby(["nit", "partner_id"]).size()
    ref = ic.set_index(["your_inst", "partner_id"]).cites_from_partner
    for x in CITER_LABELS:
        for nname in INSTITUTIONS:
            assert mine.get((nname, x), 0) == ref.get((nname, x), 0), (nname, x, mine.get((nname, x), 0),
                                                                        ref.get((nname, x), 0))

    geo = pd.DataFrame([json.loads(l) for l in open(os.path.join(RAW, "institutions_geo.jsonl"), encoding="utf-8")]
                       ).drop_duplicates("id").set_index("id")
    size_path = os.path.join(RAW, "citer_output.jsonl")
    size = {r["id"]: r["papers_2016_2026"] for r in map(json.loads, open(size_path, encoding="utf-8"))} \
        if os.path.exists(size_path) else {}
    total_by_nit = ed.groupby("nit").size()

    rows = []
    for x, (name, label) in CITER_LABELS.items():
        e = ed[ed.partner_id == x]
        per_paper = e.groupby("source").size()
        fac_credit = collections.Counter()
        for fs, n in zip(e.cited_faculty, [1] * len(e)):
            lst = [f for f in fs.split(";") if f]
            for f in lst:
                fac_credit[f] += 1 / len(lst)
        top3 = sum(v for _, v in fac_credit.most_common(3)) / max(sum(fac_credit.values()), 1)
        dist = np.average([haversine_km(geo.loc[x, "lat"], geo.loc[x, "lon"], geo.loc[NAME_TO_ID[n], "lat"],
                                        geo.loc[NAME_TO_ID[n], "lon"]) for n in e.nit]) if len(e) else np.nan
        cp = e.drop_duplicates("source")
        age = (PARTIAL_YEAR + 0.8 - cp.citing_year).clip(lower=1)
        rows.append({
            "institute": name, "type": label, "partner_id": x,
            "citations_to_us": len(e), "citing_papers": len(per_paper),
            "their_papers_2016_2026": size.get(x),
            "citations_per_1000_of_their_papers": 1000 * len(e) / size[x] if size.get(x) else np.nan,
            "distance_km": dist,
            "personal_tie_pct": 100 * (e.tie != "no personal tie found").mean(),
            "same_person_pct": 100 * (e.tie == "same person on both papers").mean(),
            "alumni_pct": 100 * (e.tie == "former NIT member (alumnus)").mean(),
            "earlier_coauthor_pct": 100 * (e.tie == "earlier co-author of the cited faculty").mean(),
            "our_papers_per_citing_paper": per_paper.mean(),
            "pct_citations_from_papers_citing_5plus_of_ours": 100 * per_paper[per_paper >= 5].sum() / max(len(e), 1),
            "max_of_our_papers_in_one_citing_paper": per_paper.max(),
            "top3_faculty_share_pct": 100 * top3,
            "citing_papers_in_proceedings_pct": 100 * cp.citing_venue.fillna("").str.contains(PROCEEDINGS).mean(),
            "median_citations_of_citing_papers": cp.citing_paper_citations.median(),
            "median_citations_per_year_of_citing_papers": (cp.citing_paper_citations / age).median(),
            "pct_citations_2023_2026": 100 * (e.citing_year >= 2023).mean(),
            "pct_citations_2016_2019": 100 * (e.citing_year <= 2019).mean(),
            "top_cited_faculty": ", ".join(f for f, _ in fac_credit.most_common(3)),
        })
    inst = pd.DataFrame(rows).sort_values("citations_to_us", ascending=False)
    fac = pd.read_csv(os.path.join(DATA, "faculty.csv")).set_index("faculty_id").author
    inst["top_cited_faculty"] = inst.top_cited_faculty.apply(lambda s: ", ".join(fac.get(f, f) for f in s.split(", ") if f))
    save(inst.round(2), "citers_by_institute.csv")

    metrics = ["citations_to_us", "their_papers_2016_2026", "citations_per_1000_of_their_papers", "distance_km",
               "personal_tie_pct", "same_person_pct", "alumni_pct", "earlier_coauthor_pct",
               "our_papers_per_citing_paper", "pct_citations_from_papers_citing_5plus_of_ours",
               "top3_faculty_share_pct", "citing_papers_in_proceedings_pct", "median_citations_of_citing_papers",
               "median_citations_per_year_of_citing_papers", "pct_citations_2023_2026"]
    comp = []
    for m in metrics:
        a, b = inst[inst.type == "private"][m].dropna(), inst[inst.type == "public"][m].dropna()
        comp.append({"measure": m, "private_median": a.median(), "public_median": b.median(),
                     "mann_whitney_p": stats.mannwhitneyu(a, b).pvalue if len(a) > 2 and len(b) > 2 else np.nan})
    comp = pd.DataFrame(comp)
    save(comp.round(4), "citers_private_vs_public.csv")

    # pooled, citation level: ties and packing, private vs public
    lab = {x: l for x, (_, l) in CITER_LABELS.items()}
    sel = ed[ed.partner_id.isin(lab)].assign(type=lambda d: d.partner_id.map(lab))
    tie_tab = pd.crosstab(sel.type, sel.tie, normalize="index").mul(100)
    save(tie_tab.round(2).reset_index(), "citers_ties_private_vs_public.csv")
    chi = stats.chi2_contingency(pd.crosstab(sel.type, sel.tie != "no personal tie found"))
    pk = sel.groupby(["type", "partner_id", "source"]).size().reset_index(name="n")
    pk_p = stats.mannwhitneyu(pk[pk.type == "private"].n, pk[pk.type == "public"].n).pvalue
    yearly = (sel.groupby(["citing_year", "type"]).size().unstack(fill_value=0).reset_index())
    save(yearly, "citers_by_year_private_vs_public.csv")

    # charts
    fig, ax = plt.subplots(1, 2, figsize=(14, 7.5))
    b = inst.sort_values("citations_per_1000_of_their_papers")
    ax[0].barh(b.institute, b.citations_per_1000_of_their_papers,
               color=["C3" if t == "private" else "C0" for t in b.type])
    ax[0].set_xlabel("citations to our faculty papers per 1,000 of their own papers (2016-2026)")
    ax[0].set_title("Top 40 citing institutes, size-adjusted (red = private, blue = public)")
    ax[0].tick_params(axis="y", labelsize=7); ax[0].grid(alpha=0.3, axis="x")
    show = ["personal_tie_pct", "alumni_pct", "pct_citations_from_papers_citing_5plus_of_ours",
            "top3_faculty_share_pct", "citing_papers_in_proceedings_pct", "pct_citations_2023_2026"]
    labels = ["personal\ntie", "alumni", "from papers\nciting 5+\nof ours", "to our\ntop-3\nfaculty",
              "citing paper\nin\nproceedings", "since\n2023"]
    c = comp.set_index("measure").loc[show]
    xx = np.arange(len(show))
    ax[1].bar(xx - 0.2, c.private_median, 0.4, color="C3", label="private (median of 18)")
    ax[1].bar(xx + 0.2, c.public_median, 0.4, color="C0", label="public (median of 22)")
    for k, p in enumerate(c.mann_whitney_p):
        ax[1].text(k, max(c.private_median.iloc[k], c.public_median.iloc[k]) + 1, f"p={p:.3f}", ha="center",
                   fontsize=7)
    ax[1].set_xticks(xx, labels, fontsize=7); ax[1].set_ylabel("% of the institute's citations to us")
    ax[1].set_title("Why they cite us: private vs public citers"); ax[1].legend(); ax[1].grid(alpha=0.3, axis="y")
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "citers_private_vs_public.png"), dpi=150); plt.close(fig)

    summary = {"edges_credited_to_labelled_institutes": len(sel),
               "share_of_all_indian_inflow_pct": {n: 100 * len(sel[sel.nit == n]) / total_by_nit[n]
                                                  for n in INSTITUTIONS},
               "private_share_of_top40_citations_pct": 100 * (sel.type == "private").mean(),
               "personal_tie_chi2_p": chi.pvalue, "packing_mann_whitney_p": pk_p,
               "check": "recount equals indian_connections.cites_from_partner for all 40 institutes"}
    with open(os.path.join(OUT, "citers_summary.json"), "w") as f:
        json.dump(summary, f, indent=2, default=float)
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40)
    print(json.dumps(summary, indent=2))
    print(comp.round(4).to_string(index=False))
    print(tie_tab.round(1).to_string())
    print(inst[["institute", "type", "citations_to_us", "their_papers_2016_2026", "citations_per_1000_of_their_papers",
                "distance_km", "personal_tie_pct", "alumni_pct", "our_papers_per_citing_paper",
                "pct_citations_from_papers_citing_5plus_of_ours", "top3_faculty_share_pct",
                "citing_papers_in_proceedings_pct", "median_citations_per_year_of_citing_papers",
                "pct_citations_2023_2026"]].round(1).to_string(index=False))
    print(inst[["institute", "top_cited_faculty"]].head(12).to_string(index=False))


# ================================================================ part "journals": tasks 7 and 9
RANKED = ["Q1", "Q2", "Q3", "Q4"]


def venue_types(works):
    """{paper id: (venue OpenAlex id, venue type)}; type from sources.jsonl ('journal', 'book series', ...)."""
    src = {r["id"]: r for r in map(json.loads, open(os.path.join(RAW, "sources.jsonl"), encoding="utf-8"))}
    out = {}
    for (_, wid), w in works.items():
        s = short(((w.get("primary_location") or {}).get("source") or {}).get("id"))
        out[wid] = (s, (src.get(s) or {}).get("type") or "")
    return out


def paper_table():
    """One row per unique paper (all papers incl. students), with the NITs and faculty on it and IF eligibility."""
    ap = pd.read_csv(os.path.join(DATA, "all_papers.csv"), low_memory=False)
    g = pd.read_csv(os.path.join(DATA, "group12_data.csv"), low_memory=False)
    vt = venue_types(raw_works())
    nits = ap.groupby("openalex_id").institution.apply(lambda s: " & ".join(sorted(set(s))))
    fac = g.groupby("openalex_id").author.apply(lambda s: "; ".join(sorted(set(s))))
    p = ap.sort_values("has_faculty_author", ascending=False).drop_duplicates("openalex_id").copy()
    p["nits"] = p.openalex_id.map(nits)
    p["has_faculty_author"] = p.openalex_id.isin(set(g.openalex_id))
    p["faculty_on_paper"] = p.openalex_id.map(fac).fillna("")
    p["venue_type"] = p.openalex_id.map(lambda w: vt.get(w, ("", ""))[1])
    # eligible for "by journal IF" lists: a journal that SCImago ranks, with an IF (team decision)
    p["if_eligible"] = (p.type == "journal") & (p.venue_type == "journal") & p.quartile.isin(RANKED) & \
        p.journal_if_2yr.notna()
    p["flag_high_if_not_q1"] = (p.journal_if_2yr > 10) & (p.quartile != "Q1")
    return p, g


def journals_part():
    p, g = paper_table()
    cols = ["rank", "title", "journal_name", "journal_if_2yr", "quartile", "year", "citations", "fwci", "nits",
            "has_faculty_author", "faculty_on_paper", "flag_high_if_not_q1", "doi"]

    def top30(d):
        t = d[d.if_eligible].sort_values(["journal_if_2yr", "citations"], ascending=[False, False]).head(30).copy()
        t.insert(0, "rank", range(1, len(t) + 1))
        return t[cols]

    t_all, t_fac = top30(p), top30(p[p.has_faculty_author])
    save(t_all.round(2), "top30_papers_by_journal_if_all_papers.csv")
    save(t_fac.round(2), "top30_papers_by_journal_if_faculty_papers.csv")
    # transparency: high-IF venues that the rule left out
    ex = (p[(p.type == "journal") & ~p.if_eligible & (p.journal_if_2yr >= 10)]
          .groupby(["journal_name", "venue_type"], dropna=False)
          .agg(journal_if_2yr=("journal_if_2yr", "first"), quartile=("quartile", "first"), papers=("openalex_id", "size"))
          .reset_index().sort_values("journal_if_2yr", ascending=False))
    ex["why_left_out"] = np.where(ex.venue_type != "journal", "not a journal (" + ex.venue_type.astype(str) + ")",
                                  "not ranked by SCImago")
    save(ex.round(2), "top30_excluded_high_if_venues.csv")

    # task 9: most-used journals (top 25) and conference venues (top 15), per NIT and scope
    ap = pd.read_csv(os.path.join(DATA, "all_papers.csv"), low_memory=False)
    ap["venue_type"] = ap.openalex_id.map(p.set_index("openalex_id").venue_type)
    # "journal" papers whose venue is really a repository (Zenodo, DOAJ, ...) or book series: listed, not ranked
    nonj = p[(p.type == "journal") & (p.venue_type != "journal")]
    save(nonj[["openalex_id", "title", "journal_name", "venue_type", "year", "nits", "has_faculty_author",
               "faculty_on_paper", "doi"]], "flag_journal_papers_in_non_journal_venues.csv")
    rows = []
    for scope, d in [("faculty papers", ap[ap.has_faculty_author]), ("all papers (incl. students)", ap)]:
        for inst in [*INSTITUTIONS, "Both NITs"]:
            sub = d.drop_duplicates("openalex_id") if inst == "Both NITs" else d[d.institution == inst]
            for kind, top_n in [("journal", 25), ("conference", 15)]:
                x = sub[(sub.type == kind) & ((sub.venue_type == "journal") if kind == "journal" else True)]
                t = (x.groupby("journal_name").agg(
                        papers=("openalex_id", "size"),
                        quartile_or_rank=("quartile", lambda s: s.dropna().mode().iat[0] if s.notna().any() else ""),
                        journal_if_2yr=("journal_if_2yr", "first"), citations=("citations", "sum"),
                        citations_per_paper=("citations", "mean"), mean_fwci=("fwci", "mean"))
                     .sort_values("papers", ascending=False).head(top_n).reset_index())
                t["share_of_venue_type_pct"] = 100 * t.papers / max(len(x), 1)
                t.insert(0, "rank", range(1, len(t) + 1))
                rows.append(t.assign(scope=scope, institution=inst, venue_type=kind))
    mj = pd.concat(rows)
    save(mj.round(2), "most_used_journals_and_conferences.csv")

    pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 60)
    print(t_all.drop(columns=["doi", "faculty_on_paper"]).round(2).to_string(index=False))
    print(t_fac[["rank", "title", "journal_name", "journal_if_2yr", "citations", "nits", "faculty_on_paper"]]
          .head(12).round(2).to_string(index=False))
    print(ex.round(2).to_string(index=False))
    show = mj[(mj.scope.str.startswith("all")) & (mj.institution != "Both NITs") & (mj.venue_type == "journal")]
    print(show.groupby("institution").head(12)[["institution", "rank", "journal_name", "papers", "quartile_or_rank",
                                                "journal_if_2yr", "citations_per_paper", "mean_fwci"]]
          .round(2).to_string(index=False))


# ================================================================ part "faculty": tasks 8 and 10
COLLAB = {"faculty_coauthors": "NIT faculty co-authors (network degree)",
          "indian_partner_institutes": "Indian partner institutes", "foreign_partner_institutes": "foreign partner institutes"}


def faculty_part():
    p, g = paper_table()
    elig = p.set_index("openalex_id").if_eligible

    # task 8: each faculty member's top 10 papers by journal IF (same eligibility as the top 30; ties by citations)
    fp = g.drop_duplicates(["faculty_id", "openalex_id"]).copy()
    fp = fp[fp.openalex_id.map(elig).fillna(False).astype(bool)]
    fp = fp.sort_values(["faculty_id", "journal_if_2yr", "citations"], ascending=[True, False, False])
    fp["rank_in_faculty"] = fp.groupby("faculty_id").cumcount() + 1
    top10 = fp[fp.rank_in_faculty <= 10][["faculty_id", "author", "institution", "department", "rank_in_faculty",
                                          "title", "journal_name", "journal_if_2yr", "quartile", "year", "citations",
                                          "fwci", "doi"]]
    save(top10.round(2), "faculty_top10_papers_by_journal_if.csv")

    # task 10: collaboration measures and score, next to the agreed 7-measure research score
    works = {wid: w for (_, wid), w in raw_works().items()}
    am = pd.read_csv(os.path.join(DATA, "network_metrics", "author_metrics.csv")).set_index("author_id")
    part = collections.defaultdict(lambda: (set(), set()))
    for f, inst, wid in g.drop_duplicates(["faculty_id", "openalex_id"])[["faculty_id", "institution",
                                                                          "openalex_id"]].itertuples(index=False):
        ind, frn = part[f]
        for a in works[wid]["authorships"]:
            for i in a["institutions"]:
                iid, cc = short(i["id"]), i.get("country_code") or ""
                if iid == NAME_TO_ID[inst]:
                    continue
                (ind if cc == "IN" else frn if cc else set()).add(iid)
    rank = pd.read_csv(os.path.join(DATA, "analysis", "insights", "faculty_ranking_overall.csv")).set_index("faculty_id")
    r = rank[["overall_rank", "author", "institution", "department", "designation", "overall_score", "papers",
              "citations", "h_index", "mean_fwci"]].rename(columns={"overall_score": "research_score",
                                                                    "overall_rank": "research_rank"})
    r["faculty_coauthors"] = am.degree.reindex(r.index).fillna(0).astype(int)
    r["indian_partner_institutes"] = [len(part[f][0]) for f in r.index]
    r["foreign_partner_institutes"] = [len(part[f][1]) for f in r.index]
    countries = collections.defaultdict(set)
    for f, wid in g.drop_duplicates(["faculty_id", "openalex_id"])[["faculty_id", "openalex_id"]].itertuples(index=False):
        for a in works[wid]["authorships"]:
            for i in a["institutions"]:
                if (i.get("country_code") or "IN") != "IN":
                    countries[f].add(i["country_code"])
    r["foreign_countries"] = [len(countries[f]) for f in r.index]
    pct = pd.DataFrame({c: 100 * r[c].rank(pct=True, method="average") for c in COLLAB}, index=r.index)
    r["collaboration_score"] = pct.mean(axis=1)
    r["collaboration_rank"] = r.collaboration_score.rank(ascending=False, method="min").astype(int)
    hi_r, hi_c = r.research_score >= r.research_score.median(), r.collaboration_score >= r.collaboration_score.median()
    r["profile"] = np.select([hi_r & hi_c, hi_r & ~hi_c, ~hi_r & hi_c],
                             ["strong research, strong collaboration", "strong research, few collaborators",
                              "collaborates widely, lower research score"], "both below median")
    # cross-check: our Indian-partner count vs the network file's (that one excludes the other NIT)
    rho_check = stats.spearmanr(r.indian_partner_institutes, am.indian_partner_institutes.reindex(r.index).fillna(0))
    out = r.reset_index().sort_values("collaboration_rank")
    save(out.round(2), "faculty_research_and_collaboration.csv")
    rho = stats.spearmanr(r.research_score, r.collaboration_score).statistic
    corr = r[["research_score", "papers", "citations", "mean_fwci", *COLLAB]].corr(method="spearman")
    save(corr.round(3).reset_index().rename(columns={"index": "measure"}), "faculty_collaboration_correlations.csv")
    prof = r.groupby(["profile", "institution"]).size().unstack(fill_value=0)
    save(prof.reset_index(), "faculty_profiles_by_institute.csv")

    fig, ax = plt.subplots(figsize=(9, 7))
    for inst, col in [("NIT Trichy", "C0"), ("NIT Surathkal", "C1")]:
        d = r[r.institution == inst]
        ax.scatter(d.collaboration_score, d.research_score, s=14, alpha=0.6, color=col, label=inst)
    for f, d in r[(r.research_rank <= 3) | (r.collaboration_rank <= 3)].iterrows():
        ax.annotate(d.author, (d.collaboration_score, d.research_score), fontsize=7, xytext=(3, 3),
                    textcoords="offset points")
    ax.axvline(r.collaboration_score.median(), color="grey", ls=":"); ax.axhline(r.research_score.median(), color="grey", ls=":")
    ax.set_xlabel("collaboration score (mean percentile: faculty co-authors, Indian and foreign partner institutes)")
    ax.set_ylabel("research score (mean percentile of the 7 research measures)")
    ax.set_title(f"Research vs collaboration, {len(r)} current faculty (Spearman ρ = {rho:.2f})")
    ax.legend(); ax.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "faculty_research_vs_collaboration.png"), dpi=150); plt.close(fig)

    summary = {"faculty_with_top10_list": int(top10.faculty_id.nunique()),
               "faculty_with_papers_but_no_eligible_journal_paper": int(g.faculty_id.nunique() - top10.faculty_id.nunique()),
               "ranked_faculty": len(r), "spearman_research_vs_collaboration": rho,
               "check_spearman_indian_partners_vs_author_metrics": rho_check.statistic}
    with open(os.path.join(OUT, "faculty_collaboration_summary.json"), "w") as f:
        json.dump(summary, f, indent=2, default=float)
    pd.set_option("display.width", 250)
    print(json.dumps(summary, indent=2))
    print(out.head(20)[["collaboration_rank", "author", "institution", "department", "collaboration_score",
                        *COLLAB, "foreign_countries", "research_rank"]].round(1).to_string(index=False))
    print(corr.round(2).to_string())
    print(prof.to_string())
    print(top10[top10.author == top10.author.iloc[0]].drop(columns=["doi"]).round(2).to_string(index=False))


# ================================================================ part "instnet": task 11
def instnet_part():
    import networkx as nx
    from clusters import cluster_of, load_institutions

    ap = pd.read_csv(os.path.join(DATA, "all_papers.csv"), low_memory=False)
    keep = set(ap[ap.n_authors <= 50].openalex_id)      # same large-paper rule as the authorship network
    works = {wid: w for (_, wid), w in raw_works().items() if wid in keep}
    insts = load_institutions()
    name, weight = {}, collections.Counter()
    papers_of = collections.Counter()
    for wid, w in works.items():
        ind = {}
        for a in w["authorships"]:
            for i in a["institutions"]:
                if i.get("country_code") == "IN":
                    ind[short(i["id"])] = i["display_name"]
        name.update(ind)
        for i in ind:
            papers_of[i] += 1
        for a, b in itertools.combinations(sorted(ind), 2):
            weight[(a, b)] += 1

    def cluster(i):
        if i in OWN:
            return "NIT (ours)"
        if re.search(r"National Institute of Technology", name[i], re.I):   # also "Institute Of Technology"
            return "NIT"
        return cluster_of(i, name[i], insts)

    G = nx.Graph()
    for i in papers_of:
        G.add_node(i, label=name[i], cluster=cluster(i), papers=papers_of[i])
    for (a, b), w in weight.items():
        G.add_edge(a, b, weight=w)
    btw = nx.betweenness_centrality(G)
    comms = nx.community.louvain_communities(G, weight="weight", seed=42)
    comm_of = {n: k for k, c in enumerate(sorted(comms, key=len, reverse=True)) for n in c}
    mod = nx.community.modularity(G, comms, weight="weight")
    nodes = pd.DataFrame({
        "institution_id": list(G), "institution": [name[n] for n in G], "cluster": [G.nodes[n]["cluster"] for n in G],
        "papers_with_us": [papers_of[n] for n in G], "degree": [G.degree(n) for n in G],
        "joint_papers_weighted_degree": [G.degree(n, weight="weight") for n in G],
        "linked_to_nit_trichy": [G.has_edge(n, NAME_TO_ID["NIT Trichy"]) for n in G],
        "linked_to_nit_surathkal": [G.has_edge(n, NAME_TO_ID["NIT Surathkal"]) for n in G],
        "betweenness": [btw[n] for n in G], "community": [comm_of[n] for n in G]})
    nodes = nodes.sort_values("joint_papers_weighted_degree", ascending=False)
    save(nodes.round(5), "institute_coauthorship_nodes.csv")
    edges = pd.DataFrame([(a, b, name[a], name[b], G.nodes[a]["cluster"], G.nodes[b]["cluster"], w,
                           a in OWN or b in OWN) for (a, b), w in weight.items()],
                         columns=["inst_a", "inst_b", "name_a", "name_b", "cluster_a", "cluster_b", "joint_papers",
                                  "involves_our_nit"]).sort_values("joint_papers", ascending=False)
    save(edges, "institute_coauthorship_edges.csv")
    nx.write_gexf(G, os.path.join(OUT, "institute_coauthorship.gexf"))

    # partner-partner links (neither end is our NIT): mixing between clusters
    pp = edges[~edges.involves_our_nit]
    mix = pp.assign(pair=[" – ".join(sorted([a, b])) for a, b in zip(pp.cluster_a, pp.cluster_b)]) \
        .groupby("pair").joint_papers.sum().sort_values(ascending=False).reset_index()
    save(mix, "institute_cluster_mixing_partner_links.csv")
    H = G.copy(); H.remove_nodes_from(OWN)
    lcc_with = len(max(nx.connected_components(G), key=len)) / G.number_of_nodes()
    lcc_without = len(max(nx.connected_components(H), key=len)) / H.number_of_nodes()
    both = nodes[nodes.linked_to_nit_trichy & nodes.linked_to_nit_surathkal & ~nodes.institution_id.isin(OWN)]
    cl = nodes[~nodes.institution_id.isin(OWN)].groupby("cluster").agg(
        institutes=("institution_id", "size"), joint_papers=("papers_with_us", "sum"),
        mean_degree=("degree", "mean"), mean_betweenness=("betweenness", "mean")).sort_values("joint_papers",
                                                                                              ascending=False)
    save(cl.round(5).reset_index(), "institute_network_by_cluster.csv")

    # chart: the 70 institutes with most joint papers
    top = list(nodes.institution_id.head(70))
    S = G.subgraph(top)
    pos = nx.spring_layout(S, weight="weight", seed=42, k=0.6)
    cl_list = sorted({S.nodes[n]["cluster"] for n in S})
    cmap = {c: plt.cm.tab20(k) for k, c in enumerate(cl_list)}

    def short_name(n):
        if n in OWN:
            return OWN[n].upper()
        x = re.sub(r"^Indian Institute of Technology\b", "IIT", name[n])
        x = re.sub(r"^National Institute [Oo]f Technology\b", "NIT", x)
        x = re.sub(r"^Indian Institute of Science\b.*", "IISc Bangalore", x)
        return x[:30]
    fig, ax = plt.subplots(figsize=(13, 11))
    ws = [S[a][b]["weight"] for a, b in S.edges]
    nx.draw_networkx_edges(S, pos, ax=ax, width=[0.3 + 2.5 * w / max(ws) for w in ws], alpha=0.25)
    for c in cl_list:
        ns = [n for n in S if S.nodes[n]["cluster"] == c]
        nx.draw_networkx_nodes(S, pos, nodelist=ns, ax=ax, node_color=cmap[c], label=c,
                               node_size=[30 + 1.2 * papers_of[n] ** 0.85 for n in ns], alpha=0.85)
    nx.draw_networkx_labels(S, pos, {n: (short_name(n) if papers_of[n] >= 40 or n in OWN else "") for n in S},
                            font_size=6.5, ax=ax)
    leg = ax.legend(fontsize=8, loc="lower left")
    for h in leg.legend_handles:
        h.set_sizes([40])
    ax.axis("off")
    ax.set_title("Institute co-authorship network on our papers (70 institutes with most joint papers; "
                 "size = papers with us, colour = cluster)")
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "institute_coauthorship_network.png"), dpi=150); plt.close(fig)

    summary = {"papers_used": len(works), "institutes": G.number_of_nodes(), "links": G.number_of_edges(),
               "partner_partner_links": len(pp), "density": nx.density(G),
               "avg_clustering": nx.average_clustering(G), "louvain_communities": len(comms), "modularity": mod,
               "largest_component_share_with_our_nits": lcc_with,
               "largest_component_share_without_our_nits": lcc_without,
               "institutes_linked_to_both_nits": len(both),
               "joint_papers_nit_trichy_surathkal": int(weight.get(tuple(sorted(OWN)), 0))}
    with open(os.path.join(OUT, "institute_network_summary.json"), "w") as f:
        json.dump(summary, f, indent=2, default=float)
    pd.set_option("display.width", 250)
    print(json.dumps(summary, indent=2))
    print(nodes[~nodes.institution_id.isin(OWN)].head(12)[["institution", "cluster", "papers_with_us", "degree",
                                                           "betweenness", "community"]].round(4).to_string(index=False))
    print(nodes[~nodes.institution_id.isin(OWN)].sort_values("betweenness", ascending=False).head(10)[
        ["institution", "cluster", "papers_with_us", "degree", "betweenness"]].round(4).to_string(index=False))
    print(pp.head(12)[["name_a", "name_b", "joint_papers"]].to_string(index=False))
    print(mix.head(12).to_string(index=False))
    print(cl.round(4).to_string())


PARTS = {"papers": papers_part, "citers": citers_part, "journals": journals_part, "faculty": faculty_part,
         "instnet": instnet_part}


def main():
    os.makedirs(OUT, exist_ok=True)
    for part in sys.argv[1:] or list(PARTS):
        if part not in PARTS:
            sys.exit(__doc__)
        print(f"\n===== {part} =====")
        PARTS[part]()


if __name__ == "__main__":
    main()
