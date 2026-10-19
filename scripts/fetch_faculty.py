"""Faculty roster, step 1: download the official faculty lists of both NITs (current and archived).

OpenAlex cannot tell faculty from PhD students, so the faculty list comes from the institutes' own websites.
To cover faculty who retired or left between 2016 and 2026, we also take one snapshot per year from the
Internet Archive (Wayback Machine). Every page is saved as raw HTML in data/raw/faculty_pages/ and listed in
manifest.csv, so build_roster.py can be re-run without downloading again. Re-running this script skips
pages that are already saved.

Sources
- NIT Trichy:    the institute-wide faculty table (name, designation, department, email), 2016-2026.
- NIT Surathkal: the teaching-staff directory (2016-2018), the telephone directory (2024-2026) and each
                 department's /people page (2016-2026, faculty plus research scholars). Current faculty
                 profile pages are also saved because some list ORCID / Scopus IDs.
"""
import csv
import os
import re
import sys
import time
import warnings

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "raw", "faculty_pages")
MANIFEST = os.path.join(OUT, "manifest.csv")
YEARS = (2016, 2026)
DELAY = 1.5  # seconds between requests, to be polite to both sites and the Internet Archive
HEADERS = {"User-Agent": "Mozilla/5.0 (DPCN course project, Team 12; faculty list collection)"}

NITK_DEPTS = ["appmech", "chemical", "chemistry", "civil", "cse", "ece", "eee", "infotech", "macs", "mech",
              "mining", "mme", "physics", "som"]
# NIT Trichy department faculty pages (the central table misses some faculty), as {code: page path}
NITT_DEPTS = {"architecture": "people", "ca": "facultymca", "chem": "chemfaculty", "chemistry": "faculty",
              "civil": "faculty", "cse": "faculty", "dee": "people/faculty", "eee": "people/faculty",
              "ece": "faculty", "humanities": "faculty", "ice": "faculty", "management": "people/faculty",
              "maths": "faculty", "mech": "faculty", "meta": "faculty", "physics": "faculty", "prod": "faculty"}

# (institution, source label, archive URL key, live URL or None)
SOURCES = [
    ("NIT Trichy", "nitt_table", "nitt.edu/home/academics/faculty/", "https://www.nitt.edu/home/academics/faculty/"),
    ("NIT Trichy", "nitt_table2", "nitt.edu/home/academics/departments/faculty/", None),
    ("NIT Surathkal", "nitk_directory", "nitk.ac.in/directory/teaching", None),
    ("NIT Surathkal", "nitk_telephone", "telephone.nitk.ac.in/", "https://telephone.nitk.ac.in/"),
] + [("NIT Surathkal", f"nitk_{d}", f"{d}.nitk.ac.in/people", f"https://{d}.nitk.ac.in/people") for d in NITK_DEPTS] \
  + [("NIT Surathkal", "nitk_appmech_faculty", "appmech.nitk.ac.in/faculty", "https://appmech.nitk.ac.in/faculty")] \
  + [("NIT Trichy", f"nittdept_{d}", f"nitt.edu/home/academics/departments/{d}/{p}/",
      f"https://www.nitt.edu/home/academics/departments/{d}/{p}/") for d, p in NITT_DEPTS.items()]


def fetch(url):
    # nitt.edu serves an incomplete TLS certificate chain, so verification fails there. These are public,
    # read-only pages, so for that one host we skip verification instead of failing.
    verify = "nitt.edu" not in url
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for attempt in range(4):
            try:
                r = requests.get(url, headers=HEADERS, timeout=90, verify=verify)
                if r.status_code == 200:
                    return r.text
                print(f"  HTTP {r.status_code} {url}", file=sys.stderr)
                if r.status_code == 404:
                    return None
            except requests.RequestException as e:
                print(f"  {type(e).__name__} {url}", file=sys.stderr)
            time.sleep(5 * (attempt + 1))
    return None


def snapshots(key):
    """First good capture of each year, from the Wayback Machine's index (CDX API)."""
    url = ("https://web.archive.org/cdx/search/cdx?url=" + key + "&fl=timestamp,original"
           f"&filter=statuscode:200&filter=mimetype:text/html&collapse=timestamp:4&from={YEARS[0]}&to={YEARS[1]}")
    text = fetch(url) or ""
    return [line.split(" ", 1) for line in text.splitlines() if " " in line]


def load_manifest():
    if not os.path.exists(MANIFEST):
        return {}
    with open(MANIFEST, encoding="utf-8") as f:
        return {row["file"]: row for row in csv.DictReader(f)}


def save(manifest, inst, source, year, kind, url, html):
    name = f"{source}_{year}_{kind}.html" if kind != "profile" else f"{source}_{kind}_{re.sub(r'[^a-z0-9-]', '', url.rsplit('/', 1)[-1])}.html"
    with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
        f.write(html)
    manifest[name] = {"file": name, "institution": inst, "source": source, "year": year, "kind": kind, "url": url}
    with open(MANIFEST, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["file", "institution", "source", "year", "kind", "url"])
        w.writeheader()
        w.writerows(sorted(manifest.values(), key=lambda r: r["file"]))


def main():
    os.makedirs(OUT, exist_ok=True)
    manifest = load_manifest()
    have = {(r["source"], r["year"], r["kind"]) for r in manifest.values()}
    for inst, source, key, live in SOURCES:
        print(f"{inst} / {source}")
        for ts, original in snapshots(key):
            year = ts[:4]
            if (source, year, "archive") in have:
                continue
            time.sleep(DELAY)
            html = fetch(f"https://web.archive.org/web/{ts}id_/{original}")
            if html:
                save(manifest, inst, source, year, "archive", original, html)
                have.add((source, year, "archive"))
                print(f"  {year} archived ({len(html):,} chars)")
        if live and (source, "2026", "live") not in have:
            time.sleep(DELAY)
            html = fetch(live)
            if html:
                save(manifest, inst, source, "2026", "live", live, html)
                have.add((source, "2026", "live"))
                print(f"  live ({len(html):,} chars)")

    # current NITK faculty profiles (some list ORCID / Scopus IDs)
    for row in list(manifest.values()):
        if row["kind"] != "live" or not row["source"].startswith("nitk_") or row["source"] == "nitk_telephone":
            continue
        dept = row["url"].split("//", 1)[1].split(".", 1)[0]
        html = open(os.path.join(OUT, row["file"]), encoding="utf-8").read()
        for slug in sorted(set(re.findall(r'href="(?:https?://[a-z]+\.nitk\.ac\.in)?/faculty/([a-z0-9-]+)"', html))):
            url = f"https://{dept}.nitk.ac.in/faculty/{slug}"
            name = f"nitk_{dept}_profile_{slug}.html"
            if name in manifest:
                continue
            time.sleep(DELAY)
            page = fetch(url)
            if page:
                save(manifest, row["institution"], f"nitk_{dept}", "2026", "profile", url, page)
    print(f"done: {len(manifest)} pages in {OUT}")


if __name__ == "__main__":
    main()
