"""Faculty roster, step 2: turn the saved faculty pages into data/reference/faculty_roster.csv.

Reads only data/raw/faculty_pages/ (saved by fetch_faculty.py). One row per person per institution:
  faculty_id, name, institution, branch, department_raw, designation, regular, email, orcid, scopus_id,
  first_seen, last_seen, status, sources
Also writes data/reference/research_scholars.csv (names listed as research scholars on NITK department pages),
which match_faculty.py uses to avoid matching a student to a faculty member.

Who counts as faculty: regular teaching faculty of every rank (Assistant / Associate / Professor / Professor
HAG / Director). Adjunct, visiting, temporary, contract, emeritus, post-doc and DST-INSPIRE positions are kept
with regular=False and are not used later.
"""
import collections
import csv
import html as htmllib
import os
import re

import pandas as pd

from names import EXCLUDED_BRANCHES, branch_of, clean_display, designation_of, name_detail, name_score, tokens

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGES = os.path.join(ROOT, "data", "raw", "faculty_pages")
REF = os.path.join(ROOT, "data", "reference")
RANK = {"Director": 5, "Professor (HAG)": 4, "Professor": 3, "Associate Professor": 2, "Assistant Professor": 1,
        "Faculty": 0.5, "Non-regular": 0, "": -1}  # "Faculty" = listed as faculty, rank not shown


def text(fragment):
    t = re.sub(r"<br\s*/?>", " ", fragment, flags=re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", htmllib.unescape(t)).strip()


def strip_noise(h):
    return re.sub(r"<script.*?</script>|<style.*?</style>|<!--.*?-->", " ", h, flags=re.S | re.I)


# ---------------------------------------------------------------- table pages (NITT table, NITK directories)
def parse_tables(h):
    """Rows of any table whose header names NAME and DESIGNATION columns."""
    out = []
    for table in re.findall(r"<table.*?</table>", h, re.S | re.I):
        current_dept = ""
        cols = None
        for tr in re.findall(r"<tr.*?</tr>", table, re.S | re.I):
            cells = [text(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S | re.I)]
            up = [c.upper() for c in cells]
            if cols is None:
                if any(c.startswith("NAME") for c in up) and any("DESIG" in c for c in up):
                    cols = {"name": next(i for i, c in enumerate(up) if c.startswith("NAME")),
                            "designation": next(i for i, c in enumerate(up) if "DESIG" in c),
                            "department": next((i for i, c in enumerate(up) if c.startswith("DEPART")), None),
                            "email": next((i for i, c in enumerate(up) if "EMAIL" in c), None)}
                continue
            if len(cells) == 1 or "department-heading" in tr:  # NITK telephone directory: a heading row per unit
                current_dept = cells[0] if cells else current_dept
                continue
            if len(cells) <= cols["designation"]:
                continue
            get = lambda k: cells[cols[k]] if cols.get(k) is not None and cols[k] < len(cells) else ""
            out.append({"name": get("name"), "designation_raw": get("designation"),
                        "department_raw": get("department") or current_dept, "email": get("email")})
    return out


# ---------------------------------------------------------------- NITK department /people pages (Drupal)
SECTION_RE = re.compile(r"research scholar|student|scholar|project staff|^staff|non.?teaching|technical|"
                        r"adjunct|temporary|contract|visiting|post ?doc|former|emerit", re.I)


def parse_drupal_people(h):
    """(name, designation text, section) for every person on a department people page. The page is split into
    tabs (quicktabs) or sections (h2/h3 headings); faculty sections give regular faculty, the others give
    adjunct / temporary staff or research scholars."""
    h = strip_noise(h)
    labels = {m.group(1): text(m.group(2)) for m in
              re.finditer(r'id="quicktabs-tab-[\w-]+?-(\d+)"[^>]*>(.*?)</a>', h, re.S)}
    parts = re.split(r'(<div[^>]+id="quicktabs-tabpage-[\w-]+?-\d+")', h)
    segments = []  # (tab label, html)
    if len(parts) > 1:
        segments.append(("", parts[0]))
        for marker, body in zip(parts[1::2], parts[2::2]):
            n = re.search(r"-(\d+)\"", marker).group(1)
            segments.append((labels.get(n, ""), body))
    else:
        segments.append(("", h))
    people = []
    for tab, body in segments:
        # walk headings and person links in document order
        section = tab
        events = re.finditer(r"<h[1-4][^>]*>(.*?)</h[1-4]>|<a[^>]+href=\"([^\"]*/(faculty|researchscholars?|people|"
                             r"staff|students?)/[^\"#?]+)\"[^>]*>(.*?)</a>", body, re.S | re.I)
        pending = None
        last_end = 0
        for m in events:
            if pending is not None:
                pending["after"] = text(body[last_end:m.start()])[:120]
                people.append(pending)
                pending = None
            if m.group(1) is not None:
                head = text(m.group(1))
                if head and len(head) < 60:
                    section = (tab + " / " + head) if tab else head
            else:
                name = text(m.group(4))
                if name and len(name) < 60 and not re.search(r"read more|more|profile|click", name, re.I):
                    pending = {"name": name, "kind": m.group(3).lower(), "section": section, "after": "",
                               "href": m.group(2)}
            last_end = m.end()
        if pending is not None:
            pending["after"] = text(body[last_end:last_end + 400])[:120]
            people.append(pending)
    # a name usually appears twice (photo link + title link); keep one
    seen, out = set(), []
    for p in people:
        key = (p["name"].lower(), p["section"])
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


def classify_drupal(p):
    """-> ('faculty', designation) | ('nonregular', designation) | ('scholar', '') | (None, '')"""
    sec, kind, after = p["section"], p["kind"], p["after"]
    if kind.startswith("researchscholar") or re.search(r"research scholar|scholars|students?$", sec, re.I):
        return "scholar", ""
    if kind != "faculty" and kind != "people":
        return None, ""
    desig = designation_of(after) or designation_of(sec)
    if SECTION_RE.search(sec) or desig == "Non-regular":
        return "nonregular", desig or "Non-regular"
    return "faculty", desig


# ---------------------------------------------------------------- NIT Trichy department faculty pages
NITT_BRANCH = {"architecture": "Architecture", "ca": "Computer Applications", "chem": "Chemical",
               "chemistry": "Chemistry", "civil": "Civil", "cse": "CSE", "dee": "Energy & Environment",
               "eee": "EEE", "ece": "ECE", "humanities": "Humanities", "ice": "ICE", "management": "Management",
               "maths": "Mathematics", "mech": "Mechanical", "meta": "MME", "physics": "Physics", "prod": "Production"}
RANK_HEAD = re.compile(r"^(professors?|associate professors?|assistant professors?|head of the department|hod|"
                       r"faculty|faculty members)\b", re.I)
STOP_HEAD = re.compile(r"^(former|past|previous|retired|emerit|adjunct|visiting|guest|staff|technical|supporting|"
                       r"non.?teaching|research scholars?|scholars|students|ph\.? ?d|alumni|heads of|dst|inspire|"
                       r"women scientist|post.?doc)|previous|former", re.I)
YEARS_RE = re.compile(r"\b(19|20)\d\d\b|onwards", re.I)


def looks_like_name(s):
    """'Dr. P. Asokan', 'Vimal K E K', 'ANAND R.B.' -> True; menu items and research areas -> False."""
    if len(s) > 60 or re.search(r"[:@\d]", s):
        return False
    if re.match(r"^(dr|prof|mr|mrs|ms|ar|er|shri|smt)\b", s, re.I):
        return True
    words = [w for w in re.split(r"[\s.]+", s) if w]
    if not 2 <= len(words) <= 6 or not all(re.fullmatch(r"[A-Za-z'\-]+", w) for w in words):
        return False
    return any(len(w) == 1 for w in words) or s.isupper()


def parse_nitt_dept(h):
    """(name, designation) pairs from a NIT Trichy department faculty page, read under its rank headings."""
    chunks = [c for c in (htmllib.unescape(re.sub(r"\s+", " ", x)).strip()
                          for x in re.split(r"<[^>]+>", strip_noise(h))) if c and c != "|"]
    out, rank = [], None
    for i, c in enumerate(chunks):
        low = c.lower().strip(" :")
        if len(low) < 45 and STOP_HEAD.search(low) and not looks_like_name(c):
            rank = None
            continue
        if len(low) < 45 and RANK_HEAD.match(low):
            rank = designation_of(c) or ("Professor" if "head" in low or low == "hod" else "Faculty")
            continue
        if rank and looks_like_name(c):
            if any(YEARS_RE.search(x) for x in chunks[i + 1:i + 3]):
                continue  # a table of former heads (name followed by their years), not current faculty
            out.append((c, rank))
            if rank == "Professor" and "head" in (chunks[i - 1].lower() if i else ""):
                rank = None
    return out


def profile_ids(h):
    """ORCID / Scopus ID from a NITK faculty profile page, when listed."""
    orcid = re.search(r"orcid\.org/(\d{4}-\d{4}-\d{4}-\d{3}[\dX])", h)
    scopus = re.search(r"scopus\.com/[^\"']*authorId=(\d+)", h) or \
             re.search(r"Scopus(?:\s*ID)?\s*[:\-]?\s*(?:</[^>]+>\s*<[^>]+>\s*)*(\d{8,12})", h, re.I)
    return (orcid.group(1) if orcid else ""), (scopus.group(1) if scopus else "")


# ---------------------------------------------------------------- merge yearly records into people
def merge(records):
    """Group records of the same person (same institution and branch, compatible names; NITT also by email)."""
    people = []
    by_key = {}
    for r in sorted(records, key=lambda r: (r["institution"], r["year"])):
        key = (r["institution"], r["email"].lower()) if r["email"] else None
        p = by_key.get(key) if key else None
        if p is None:
            cands = [q for q in people if q["institution"] == r["institution"]
                     and (q["branch"] == r["branch"] or not q["branch"] or not r["branch"])]
            scored = [(max(name_score(n, r["name"]) for n in q["names"]), q) for q in cands]
            scored = [s for s in scored if s[0] >= 2 or (s[0] == 1 and q_branch_equal(s[1], r))]
            if scored:
                p = max(scored, key=lambda s: s[0])[1]
        if p is None:
            p = {"institution": r["institution"], "branch": r["branch"], "names": [], "years": set(),
                 "designations": [], "departments": collections.Counter(), "emails": set(), "sources": set(),
                 "orcid": "", "scopus_id": "", "regular_years": set(), "pages": set()}
            people.append(p)
        if key:
            by_key[key] = p
        p["names"].append(r["name"])
        p["years"].add(r["year"])
        p["designations"].append((r["year"], r["designation"]))
        p["departments"][r["department_raw"]] += 1
        p["branch"] = p["branch"] or r["branch"]
        if r["email"]:
            p["emails"].add(r["email"].lower())
        p["sources"].add(r["source"])
        p["pages"].add((r["source"], r["year"]))  # two entries on the same page and year are two people
        if r["designation"] not in ("Non-regular", ""):
            p["regular_years"].add(r["year"])
        p["orcid"] = p["orcid"] or r.get("orcid", "")
        p["scopus_id"] = p["scopus_id"] or r.get("scopus_id", "")
    return people


def consolidate(people):
    """Second pass: merge entries of one person that the year-by-year pass kept apart (e.g. a department page
    listed before the central table). Two entries in the same institution and branch are merged when their names
    agree (score 2-3, or a typo / glued-words match); never when both have different email IDs."""
    parent = list(range(len(people)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    groups = collections.defaultdict(list)
    for i, p in enumerate(people):
        groups[(p["institution"], p["branch"])].append(i)
    for idx in groups.values():
        spellings = {i: set(people[i]["names"]) for i in idx}
        for x, i in enumerate(idx):
            for j in idx[x + 1:]:
                if find(i) == find(j):
                    continue
                ei, ej = people[i]["emails"], people[j]["emails"]
                if ei and ej and not (ei & ej):
                    continue
                best = max((name_detail(a, b) for a in spellings[i] for b in spellings[j]), key=lambda t: t[0])
                same_letters = {"".join(tokens(a)) for a in spellings[i]} & {"".join(tokens(b)) for b in spellings[j]}
                if best[0] >= 2 or best[1] in ("typo", "glued") or same_letters:  # "NARENDRANATHS" = "Narendranath S"
                    parent[find(j)] = find(i)
        # an entry listed by one word only ("SHRIKANTHA", "Dr. Krishnan") is the one person in the same branch whose
        # fuller name contains that word ("Shrikantha S Rao"), if there is exactly one such person and the two are
        # never listed on the same page in the same year
        for i in idx:
            words = {tuple(tokens(n)) for n in spellings[i]}
            if len(words) != 1 or len(next(iter(words))) != 1 or len(next(iter(words))[0]) < 4:
                continue
            w = next(iter(words))[0]
            cands = [j for j in idx if j != i and any(w in tokens(n) and len(tokens(n)) > 1 for n in spellings[j])]
            if len(cands) != 1:
                continue
            j = cands[0]
            ei, ej = people[i]["emails"], people[j]["emails"]
            if not (people[i]["pages"] & people[j]["pages"]) and not (ei and ej and not (ei & ej)):
                parent[find(i)] = find(j)
    merged = {}
    for i, p in enumerate(people):
        root = find(i)
        if root not in merged:
            merged[root] = p
            continue
        m = merged[root]
        for k in ("years", "emails", "sources", "regular_years", "pages"):
            m[k] |= p[k]
        m["names"] += p["names"]
        m["designations"] += p["designations"]
        m["departments"] += p["departments"]
        m["orcid"] = m["orcid"] or p["orcid"]
        m["scopus_id"] = m["scopus_id"] or p["scopus_id"]
    return list(merged.values())


def q_branch_equal(q, r):
    return bool(q["branch"]) and q["branch"] == r["branch"]


def best_name(names):
    """The fullest spelling: most full words, then longest."""
    return max(names, key=lambda n: (sum(len(t) > 1 for t in tokens(n)), len(n)))


def main():
    manifest = pd.read_csv(os.path.join(PAGES, "manifest.csv"), dtype=str)
    records, scholars = [], []
    ids_by_slug = {}
    for row in manifest.itertuples(index=False):
        if row.kind == "profile":
            h = open(os.path.join(PAGES, row.file), encoding="utf-8", errors="ignore").read()
            ids_by_slug[row.url.rstrip("/").rsplit("/", 1)[-1]] = profile_ids(h)
    for row in manifest.itertuples(index=False):
        if row.kind == "profile":
            continue
        h = open(os.path.join(PAGES, row.file), encoding="utf-8", errors="ignore").read()
        year = int(row.year)
        if row.source.startswith("nittdept_"):
            code = row.source.split("_", 1)[1]
            for name, desig in parse_nitt_dept(h):
                records.append({"institution": row.institution, "year": year, "source": row.source, "name": name,
                                "designation": desig, "department_raw": code, "branch": NITT_BRANCH[code],
                                "email": ""})
        elif row.source.startswith("nitt_table") or row.source in ("nitk_directory", "nitk_telephone"):
            for r in parse_tables(strip_noise(h)):
                desig = designation_of(r["designation_raw"])
                if not desig or not tokens(r["name"]):
                    continue  # administrative / technical staff in the telephone directory
                records.append({"institution": row.institution, "year": year, "source": row.source,
                                "name": r["name"], "designation": desig, "department_raw": r["department_raw"],
                                "branch": branch_of(r["department_raw"]), "email": r["email"].strip()})
        else:  # NITK department people page
            dept = row.url.split("//", 1)[1].split(".", 1)[0]
            for p in parse_drupal_people(h):
                kind, desig = classify_drupal(p)
                if kind == "scholar":
                    scholars.append({"institution": row.institution, "branch": branch_of(dept), "name": p["name"],
                                     "year": year})
                elif kind in ("faculty", "nonregular"):
                    m = re.search(r"/faculty/([a-z0-9-]+)", p.get("href", ""))
                    orcid, scopus = ids_by_slug.get(m.group(1) if m else "", ("", ""))
                    records.append({"institution": row.institution, "year": year, "source": row.source,
                                    "name": p["name"], "designation": desig if kind == "faculty" else "Non-regular",
                                    "department_raw": dept, "branch": branch_of(dept), "email": "",
                                    "orcid": orcid, "scopus_id": scopus})
    people = consolidate(merge(records))
    rows = []
    for i, p in enumerate(sorted(people, key=lambda p: (p["institution"], p["branch"], best_name(p["names"])))):
        latest = max(p["designations"], key=lambda d: (d[0], RANK.get(d[1], -1)))[1]
        top = max((d for _, d in p["designations"]), key=lambda d: RANK.get(d, -1))
        regular = bool(p["regular_years"])
        rows.append({
            "faculty_id": f"{'T' if p['institution'] == 'NIT Trichy' else 'S'}{i + 1:04d}",
            "name": clean_display(best_name(p["names"])),
            "institution": p["institution"],
            "branch": p["branch"],
            "department_raw": p["departments"].most_common(1)[0][0],
            "designation": latest if latest not in ("", "Non-regular") or not regular else top,
            "regular": regular,
            "science_engineering": p["branch"] not in EXCLUDED_BRANCHES,
            "email": ";".join(sorted(p["emails"])),
            "orcid": p["orcid"], "scopus_id": p["scopus_id"],
            "first_seen": min(p["years"]), "last_seen": max(p["years"]),
            "status": "current" if max(p["years"]) == 2026 else "former",
            "name_variants": ";".join(sorted(set(p["names"]))),
            "sources": ";".join(sorted(p["sources"])),
        })
    roster = pd.DataFrame(rows)
    os.makedirs(REF, exist_ok=True)
    roster.to_csv(os.path.join(REF, "faculty_roster.csv"), index=False)
    pd.DataFrame(scholars).drop_duplicates(["institution", "name"]).to_csv(
        os.path.join(REF, "research_scholars.csv"), index=False)

    reg = roster[roster.regular]
    print(f"people: {len(roster)}   regular faculty: {len(reg)}   science/engineering regular: "
          f"{int(reg.science_engineering.sum())}   research scholars listed: {len(scholars)}")
    print(reg.groupby(["institution", "status"]).size().to_string())
    print(reg.groupby(["institution", "branch"]).size().to_string())
    print("no branch:", reg[reg.branch == ""][["institution", "name", "department_raw"]].head(20).to_string())


if __name__ == "__main__":
    main()
