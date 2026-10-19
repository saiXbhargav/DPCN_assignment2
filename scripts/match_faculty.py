"""Faculty roster, step 3: link every faculty member to their OpenAlex author ID(s).

Inputs:  data/reference/faculty_roster.csv, research_scholars.csv (build_roster.py), data/raw/*_works.jsonl,
         data/raw/authors.jsonl, and optionally data/reference/faculty_match_overrides.csv (team decisions).
Outputs: data/reference/faculty_openalex_map.csv   accepted links: faculty_id -> author_id
         data/reference/faculty_match_review.csv    links a person should check by hand
         data/reference/unmatched_prolific_authors.csv  NIT authors with many papers but no faculty match

How a link is decided (for one faculty member and one OpenAlex author with papers at the same NIT):
  * name score 0-3 (names.name_score): 3 = same words, 2 = same words with some initials, 1 = only through
    initials, a typo or glued words ("DWARAKISHG.S."), 0 = different names
  * branch score: +2 if the author's own NIT affiliation text on their papers names the faculty member's
    department, -3 if it names a different department, 0 if it never names one
  * ORCID: the same ORCID on the faculty profile and in OpenAlex is accepted directly
  * accepted: ORCID, or name >= 2 with branch >= 0, or name 1 with branch +2
  * everything else that has name >= 1 goes to the review file
One person may have several OpenAlex IDs (OpenAlex sometimes splits a person). One ID belongs to at most
one person: if two people claim it, the better score wins; a tie goes to review.
"""
import collections
import json
import os

import pandas as pd

from fetch_works import INSTITUTIONS, RAW, ROOT
from names import affiliation_branch, block_keys, name_detail, tokens

REF = os.path.join(ROOT, "data", "reference")
OWN = {v: k for k, v in INSTITUTIONS.items()}
REVIEW_MIN_PAPERS = 3  # uncertain links with fewer papers than this are rejected instead of reviewed


def short(url):
    return (url or "").rsplit("/", 1)[-1]


def nit_department(a, inst_id):
    """Department text from the affiliation string that belongs to this NIT on this authorship."""
    for aff in a.get("affiliations") or []:
        if any(short(i) == inst_id for i in aff.get("institution_ids") or []):
            return aff.get("raw_affiliation_string") or ""
    return ""


def load_authorships():
    """Every NIT-affiliated authorship: (institution, author_id, display name, raw name, branch, paper id)."""
    out = []
    for inst_name, inst_id in INSTITUTIONS.items():
        for line in open(os.path.join(RAW, inst_name.replace(" ", "_") + "_works.jsonl"), encoding="utf-8"):
            w = json.loads(line)
            for pos, a in enumerate(w["authorships"]):
                if not any(short(i["id"]) == inst_id for i in a["institutions"]):
                    continue
                out.append({"institution": inst_name, "author_id": short(a["author"]["id"]),
                            "name": a["author"].get("display_name") or "", "raw_name": a.get("raw_author_name") or "",
                            "orcid": short(a["author"].get("orcid") or ""),
                            "branch": affiliation_branch(nit_department(a, inst_id)), "paper": short(w["id"]),
                            "position": pos, "year": w["publication_year"]})
    return out


def candidates(authorships, profiles, author_ids):
    cand = {}
    for r in authorships:
        if not r["author_id"]:
            continue
        key = (r["institution"], r["author_id"])
        c = cand.setdefault(key, {"names": collections.Counter(), "branches": collections.Counter(),
                                  "papers": set(), "orcid": "", "years": []})
        c["names"][r["name"]] += 1  # OpenAlex display names only: raw bylines are often just "M. Kumar"
        if r["branch"]:
            c["branches"][r["branch"]] += 1
        c["papers"].add(r["paper"])
        c["years"].append(r["year"])
        c["orcid"] = c["orcid"] or r["orcid"] or short((profiles.get(r["author_id"]) or {}).get("orcid") or "")             or (author_ids.get(r["author_id"]) or {}).get("orcid", "")
    return cand


def name_strength(roster_name, oa_name):
    """(name score, safe). A score-1 match is 'safe' when its one weak point is a typo or glued words, or an
    extra word when the roster gives a one-word name ("Annappa" = "Basava Annappa")."""
    score, weak = name_detail(roster_name, oa_name)
    r, o = tokens(roster_name), tokens(oa_name)
    one_word = len([t for t in r if len(t) > 1]) == 1 and len(r) == 1
    # "N Samsudeen" = "Samsudeen Naina Mohamed": the extra word is on the OpenAlex side and every full word of
    # the roster name appears unchanged (unlike "Sreejith Mohan" vs "S. Mohan Kumar")
    contained = len(o) == len(r) + 1 and {t for t in r if len(t) > 1} <= {t for t in o if len(t) > 1}
    return score, score >= 2 or weak in ("typo", "glued") or (weak == "extra_word" and (one_word or contained))


def branch_score(c, branch):
    if not branch or not c["branches"]:
        return 0
    share = c["branches"][branch] / sum(c["branches"].values())
    return 2 if share >= 0.5 else (0 if share > 0.1 else -3)


def main():
    roster = pd.read_csv(os.path.join(REF, "faculty_roster.csv"), dtype=str).fillna("")
    roster = roster[roster.regular == "True"]
    scholars = pd.read_csv(os.path.join(REF, "research_scholars.csv"), dtype=str).fillna("")
    profiles = {short(a["id"]): a for a in map(json.loads, open(os.path.join(RAW, "authors.jsonl"), encoding="utf-8"))}
    authorships = load_authorships()
    path = os.path.join(RAW, "author_ids.jsonl")  # ORCIDs from OpenAlex author records (fetch_impact.py authorids)
    author_ids = {r["id"]: r for r in map(json.loads, open(path, encoding="utf-8"))} if os.path.exists(path) else {}
    cand = candidates(authorships, profiles, author_ids)

    index = collections.defaultdict(set)  # (institution, word) -> candidate keys
    for (inst, aid), c in cand.items():
        for n in c["names"]:
            for k in block_keys(n):
                index[(inst, k)].add((inst, aid))
    scholar_names = collections.defaultdict(list)
    for s in scholars.itertuples(index=False):
        scholar_names[(s.institution, s.branch)].append(s.name)

    links = []
    for p in roster.itertuples(index=False):
        variants = [v for v in p.name_variants.split(";") if v] or [p.name]
        keys = set()
        for v in variants:
            for k in block_keys(v):
                keys |= index.get((p.institution, k), set())
        if p.orcid:
            keys |= {k for k, c in cand.items() if k[0] == p.institution and c["orcid"] == p.orcid}
        for key in keys:
            c = cand[key]
            ns, safe = max(name_strength(v, n) for v in variants for n in c["names"])
            orcid = bool(p.orcid) and c["orcid"] == p.orcid
            if ns == 0 and not orcid:
                continue
            bs = branch_score(c, p.branch)
            best_oa_name = c["names"].most_common(1)[0][0]
            student_like = any(name_detail(s, best_oa_name)[0] == 3 for s in scholar_names[(p.institution, p.branch)])
            if orcid:
                decision, method = "accepted", "orcid"
            elif (ns >= 2 and bs >= 0) or (ns == 1 and safe and bs == 2):
                decision, method = "accepted", "name"
            elif ns == 1 and bs < 0:
                continue  # weak name match and a different department: not the same person
            elif len(c["papers"]) < REVIEW_MIN_PAPERS:
                decision, method = "rejected_small", "name"  # too few papers to be worth a manual check
            else:
                decision, method = "review", "name"
            if decision == "accepted" and method == "name" and student_like and ns < 3:
                decision = "review"  # a research scholar of the same department has this exact name
            links.append({"faculty_id": p.faculty_id, "author_id": key[1], "institution": p.institution,
                          "faculty_name": p.name, "openalex_name": best_oa_name,
                          "faculty_branch": p.branch, "openalex_branches": dict(c["branches"].most_common(3)),
                          "name_score": ns, "branch_score": bs, "orcid_match": orcid,
                          "papers_at_nit": len(c["papers"]), "first_year": min(c["years"]), "last_year": max(c["years"]),
                          "student_name_clash": student_like, "method": method, "decision": decision,
                          "score": (10 if orcid else 0) + ns + bs})
    links = pd.DataFrame(links)

    # one OpenAlex ID belongs to at most one person per institute (faculty who moved between the two NITs, like
    # V. Vignesh Kumar or I. Jeyaraman, keep the same ID at both)
    acc = links[links.decision == "accepted"]
    for aid, grp in acc.groupby(["institution", "author_id"]):
        if grp.faculty_id.nunique() < 2:
            continue
        top = grp.score.max()
        winners = grp[grp.score == top]
        losers = grp.index.difference(winners.index)
        links.loc[losers, "decision"] = "lost_to_better_match"
        if len(winners) > 1:
            links.loc[winners.index, "decision"] = "review"
    # an uncertain link is moot when another faculty member already has that ID
    taken = set(zip(links.institution[links.decision == "accepted"], links.author_id[links.decision == "accepted"]))
    is_taken = pd.Series([k in taken for k in zip(links.institution, links.author_id)], index=links.index)
    links.loc[(links.decision == "review") & is_taken, "decision"] = "lost_to_better_match"

    # team decisions from the review file override the rules
    ov_path = os.path.join(REF, "faculty_match_overrides.csv")
    if os.path.exists(ov_path):
        ov = pd.read_csv(ov_path, dtype=str)
        applied = 0
        for o in ov.itertuples(index=False):
            # by name + OpenAlex ID: faculty_id numbers can shift when the roster is rebuilt
            hit = (links.faculty_name == o.faculty_name) & (links.author_id == o.author_id)
            links.loc[hit, "decision"] = "accepted" if o.decision.strip().lower() == "accept" else "rejected"
            links.loc[hit, "method"] = "override"
            applied += int(hit.any())
        print(f"team decisions applied: {applied} of {len(ov)}")
        # the team accepted one ID for two people of the same institute: we cannot tell whose it is
        acc = links[links.decision == "accepted"]
        clash = acc[acc.duplicated(["institution", "author_id"], keep=False)]
        links.loc[clash.index, "decision"] = "conflict"
        for r in clash.itertuples(index=False):
            print(f"  conflict, left out: {r.author_id} accepted for both people named {r.faculty_name!r} "
                  f"({r.faculty_branch})")

    links = links.sort_values(["institution", "faculty_id", "score", "papers_at_nit", "author_id"],
                          ascending=[True, True, False, False, True])  # fixed order, so reruns match exactly
    links[links.decision == "accepted"].to_csv(os.path.join(REF, "faculty_openalex_map.csv"), index=False)
    review = links[links.decision == "review"]
    review.to_csv(os.path.join(REF, "faculty_match_review.csv"), index=False)

    # prolific NIT authors with no accepted faculty link (missing from the roster, or a name we could not match)
    linked = set(links[links.decision == "accepted"].author_id)
    unm = [{"institution": k[0], "author_id": k[1], "openalex_name": c["names"].most_common(1)[0][0],
            "papers_at_nit": len(c["papers"]), "branches": dict(c["branches"].most_common(2)),
            "years": f"{min(c['years'])}-{max(c['years'])}"}
           for k, c in cand.items() if k[1] not in linked and len(c["papers"]) >= 15]
    pd.DataFrame(unm).sort_values("papers_at_nit", ascending=False).to_csv(
        os.path.join(REF, "unmatched_prolific_authors.csv"), index=False)

    matched_people = links[links.decision == "accepted"].faculty_id.nunique()
    print(f"faculty: {len(roster)}   with at least one accepted OpenAlex ID: {matched_people} "
          f"({matched_people / len(roster):.0%})")
    print("links by decision:", links.decision.value_counts().to_dict())
    print("accepted by method:", links[links.decision == "accepted"].method.value_counts().to_dict())
    ids_per_person = links[links.decision == "accepted"].groupby("faculty_id").size()
    print("people with 2+ OpenAlex IDs:", int((ids_per_person > 1).sum()))
    papers = {}
    for r in authorships:
        papers.setdefault(r["paper"], False)
        if r["author_id"] in linked:
            papers[r["paper"]] = True
    print(f"papers with at least one matched faculty author: {sum(papers.values())} of {len(papers)}")
    print("prolific authors (15+ papers) without a faculty match:", len(unm))
    for inst in INSTITUTIONS:
        r = roster[roster.institution == inst]
        m = links[(links.decision == "accepted") & (links.institution == inst)].faculty_id.nunique()
        print(f"  {inst}: {m}/{len(r)} faculty matched")


if __name__ == "__main__":
    main()
