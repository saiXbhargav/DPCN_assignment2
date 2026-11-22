# Checking the Group 13 and Group 14 data (18 Nov 2026)

For the South Indian NIT comparison, two other teams shared their assignment files with us:
- **Group 13:** NIT Warangal, with NIT Rourkela.
- **Group 14:** NIT Calicut, with NIT Kurukshetra and NIT Durgapur.

We did not use these files blindly. We checked them the same way we checked our own data after the roster fix.

- **Where they are:** `data/raw/second_dataset/group13/` and `group14/`, git-ignored.
- **Their files are never edited.** Every fix is one row in `data/reference/second_dataset_corrections/warangal.csv` or `calicut.csv`, with its reason, and `scripts/check_second_dataset.py` applies it.
- **Outputs:** the cleaned tables are `second_dataset_warangal_*.csv` and `second_dataset_calicut_*.csv` in this folder, and the numbers below are in `k_checks_summary.json`.

## What the files are

Both files follow the assignment template:
- `groupNN_data.csv`;
- `authorship_network.csv`;
- `citation_network.csv`;
- `indian_connections.csv`.

They are not faculty lists:
- **One row per paper and author:** every author with the NIT's affiliation gets a row, so students and project staff are included (Group 13's DECISIONS.md says so).
- **No IDs or roster details:** there is no OpenAlex author ID, department, rank or joining date.
- **Names differ by group:** Group 13 writes each author's OpenAlex name. Group 14 writes faculty by the names on their scraped roster (for example "G. Unnikrishnan") and everyone else by the OpenAlex name.

So, just as on 17 Nov, we find the faculty through each NIT's NIRF 2025 list.

We checked the files against two sources of our own:
1. **Our OpenAlex download of the same NIT** (`fetch_peers.py`), joined on DOI.
2. **The NIT's NIRF 2025 faculty list.**

## The seven checks

| Check | NIT Warangal (Group 13) | NIT Calicut (Group 14) |
|---|---|---|
| **1. Split** | 22,584 of 58,317 rows (Rourkela is the rest). 10,317 papers, 5,487 names | 15,917 of 43,264 rows (Durgapur and Kurukshetra are the rest). 7,058 papers, 4,753 names. Written as "National Institute of Technology Calicut", renamed to NIT Calicut |
| **2. People vs NIRF 2025** | 278 of 327 current faculty (85%) found by name. 270 found through OpenAlex IDs as well. 49 not found (mostly few or no papers) | 327 of 375 (87%) found by name, 317 through IDs. 48 not found |
| Names that are not people | 5 strings like "G.Sunil3, V.Pranathi1, Md.Sallauddin2," (copied affiliation text). Dropped | 1 address string ("…Choolur(PO), N.I.T.(VIA),673601 Kozhikode,"). Dropped |
| **3. Papers vs OpenAlex** | 9,939 in both. Year agrees for 99.9%, journal/conference type for 100%. Median citation difference 0 | 6,944 in both. Year agrees for 99.8%, type for 97.6%. Median citation difference 0 |
| Only in their file | 378: 285 book chapters, 7 editorials, 3 retractions, 1 abstract (all outside the article/review/conference scope we use for every NIT); 52 where OpenAlex does not list Warangal; 5 second DOIs of papers already in the file; 1 DOI not in OpenAlex. **24 are real papers our download missed (kept).** 19 old DOIs were updated to OpenAlex's main DOI | 114: 60 second DOIs of papers already in the file; 35 outside our scope (chapters, editorials, abstracts, letters, data papers); 6 without Calicut; 2 not in OpenAlex. **11 real papers kept.** 9 DOIs updated |
| Only in our download | 314, of which 183 are 2026 papers that appeared after their build (12 Oct) | **1,040, of which 881 are conference papers.** 257 are 2026 papers |
| **Faculty papers they cover** | **97.2%** (187 of 6,721 missing) | **86.5%** (789 of 5,830 missing, mostly conference papers) |
| **4. Names vs OpenAlex IDs** | 20,386 of 21,725 checkable rows match an author with Warangal's affiliation. 1,215 match an author OpenAlex has not given an ID yet (kept). 35 rows name someone who is not on the paper (dropped) | 14,213 match directly. 389 more match a short or long form of the same name ("G. Unnikrishnan" = "Gopalakrishna Panicker Unnikrishnan"). 938 have no OpenAlex ID yet (kept). 81 rows name someone who is not on the paper (dropped; e.g. "Karthik Kumar" on a paper by Kondapaka Kishor Kumar) |
| Same person, several spellings | 159 OpenAlex IDs written 2–3 ways ("Mallaiah Manjaiah", "Manjaiah Mallaiah", "M. Manjaiah"). Joined into one name (167 renames) | 114 IDs ("Veni T." / "Thangaraj Veni"). 127 renames |
| Same name, several IDs | 101 names, mostly common ones ("Amit Kumar" ×7). These are different people, kept apart | 109 names ("Anil Kumar" ×6). Kept apart |
| One ID that may be two people | 9 faculty IDs whose two main fields share no co-author. Listed in `k_ids_that_look_like_two_people.csv` for a manual look, not changed | 13 such IDs, same treatment |
| **5. Duplicates and ranges** | 6 rows with the same paper and author twice (dropped). No titles under two DOIs. All years 2016–2026 | **61 papers listed under two DOIs with the same title and year** (mostly Inderscience early-access DOIs). The less-cited copy dropped. 383 CORE ranks written as plain "A", "B", "C", renamed to "CORE A" etc. |
| **6. Networks** | 13,230 of 31,385 co-author rows join a Warangal author to someone outside. Their rule keeps outside co-authors; we keep only faculty–faculty pairs inside the NIT. No self-loops or duplicate rows. 94 rows point to papers not in their data. Faculty pairs: 180 by name in their network, 299 by ID in ours, 173 in both | 6,830 of 19,206 rows have an outside partner. No self-loops or duplicate rows. Faculty pairs: 276 by name, 333 by ID, 254 in both |
| Citation file and partner counts | 17 of 108,601 citation rows have neither paper in their data. Recounting `shared_papers` for the top 30 partners gives the same number for 77% (median difference 0) | All citation rows fine. Partner recount the same for 93% |
| **7. Big teams and spot check** | No paper with 100+ authors, 1 with 50+. 20 faculty picked at random for a by-hand check (`k_spot_check.csv`) | 1 paper with 100+ authors. 20 faculty in the spot-check list |
| **After the fixes** | 22,584 → **21,858 rows**, 10,317 → **9,957 papers** | 15,917 → **15,572 rows**, 7,058 → **6,919 papers** |

## Which data each NIT uses

**Neither file is bad.** Group 13's Warangal data is very close to our own download. Group 14's Calicut data has the duplicate DOIs and misses about one in seven faculty papers, mostly conference papers.

**For the six-NIT numbers (`south_nits.py`, SOUTH.md), all six NITs use our own OpenAlex download plus the NIRF 2025 list.** The cleaned data of Groups 13 and 14 is a second, independent check for Warangal and Calicut. The reasons:

1. **No new papers.** Both files come from OpenAlex, like ours. Once their extra book chapters and duplicates are taken out, they add only 24 and 11 papers that our download missed.
2. **We need NIRF anyway.** Their files carry names only (no IDs, ranks or joining years), so faculty can only be found through NIRF either way.
3. **Calicut's file would be unfair.** Its missing conference papers would make Calicut look less productive for a data reason, not a real one.
4. **Same filter for all six.** The same download filter for all six NITs keeps the comparison fair. Our download is about a month newer than theirs (12 Oct and late Oct), and the six NITs were fetched within a day of each other (17–18 Nov).

**The cross-check agrees.** With the cleaned data of Groups 13 and 14, the faculty densification exponent comes out about 0.1 lower: Warangal 1.30 vs 1.44, Calicut 1.31 vs 1.39 (`s_second_dataset_vs_ours.csv`). Both are inside the 1.2–1.75 band of all six NITs, so no conclusion changes. Their journal quartiles give Q1 shares of 38.6% (Warangal) and 44.0% (Calicut). Our own quartile rule gives 36.6% and 44.2%.

## How to rerun

```bash
python scripts/fetch_peers.py          # papers of the six NITs (skips finished files)
python scripts/fetch_peers.py refs     # references between each NIT's own papers
python scripts/check_second_dataset.py        # these checks (needs pymupdf for the NIRF files)
python scripts/south_nits.py           # the six-NIT comparison
```
