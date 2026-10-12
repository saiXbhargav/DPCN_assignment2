# DPCN Research Mapping Project: Team 12

**Our institutions:** NIT Trichy and NIT Surathkal
**Period:** 2016–2026
**Instructor:** Chittaranjan Hens

The full list of assignment tasks is in [assignment.md](assignment.md). This file explains **what we have done so far and exactly how we got the data**, so anyone on the team can understand it, defend it in the report and reproduce it.

---

## Status at a glance

| Task | Status |
|---|---|
| 1. Data collection (`group12_data.csv`) | ✅ Done. Every column is filled. |
| 2. Network files (`citation_network.csv`, `authorship_network.csv`, `indian_connections.csv`) | ✅ Done. All 35 automated checks pass. |
| 3. Indian connectivity analysis | ⏳ Not started |
| 4. Statistics report | ⏳ Not started |
| 5. Interactive dashboard | ⏳ Not started |

---

## The big picture: where the data came from

| What we needed | Source | How we got it |
|---|---|---|
| Papers, authors, citations, references, topics | **OpenAlex** (openalex.org), a free, open database of about 250 million research papers | Its REST API, called from Python scripts |
| Author h-index | OpenAlex author profiles | The same API |
| Journal quartiles (Q1–Q4) | **SCImago Journal Rank (SJR)** data | A public GitHub mirror, because scimagojr.com blocks automated downloads |
| Conference ranks (A\*/A/B/C) | **CORE** conference portal (ICORE2026 list) | The portal's CSV export |
| Departments | The affiliation text printed on each paper, as stored in OpenAlex | Text matching in Python |

We chose OpenAlex because the assignment recommends it, it's free, and it has an API. It also links every paper to its **institutions**, its **references** (`referenced_works`) and the **papers that cite it**, which the network tasks need.

The work is split into four scripts in [scripts/](scripts/), run in order:

```
fetch_works.py   →  fetch_authors.py  →  fetch_links.py  →  build_dataset.py
(papers)            (h-index)            (Indian citation     (builds the CSV
                                          links)               files)
```

The three `fetch_*` scripts download from the internet and save **raw** files to `data/raw/`. `build_dataset.py` uses only those saved files, so we can rebuild the CSVs as often as we like without downloading again.

---

## Step-by-step: what we did

### Step 0: Understood the assignment
- Read the instruction note (`DPCN_Instruction_Note (1).docx`) and the slides (`DPCN Research Mapping Project_n4.pptx`).
- Slide 5 assigns **Group 12 → "Top NITs" → NIT Trichy and NIT Surathkal**.
- Wrote [assignment.md](assignment.md), our checklist of everything to submit.

### Step 1: Found our institutions in OpenAlex
Searching for an institution by name is unreliable, because "National Institute of Technology" matches more than 30 NITs. So we looked up each institution once and then used its **unique OpenAlex ID** everywhere:

```
https://api.openalex.org/institutions?search=National Institute of Technology Tiruchirappalli
https://api.openalex.org/institutions?search=National Institute of Technology Karnataka
```

| Institution | OpenAlex ID | ROR ID (global institution ID) |
|---|---|---|
| NIT Trichy | `I122964287` | ror.org/047x65e68 |
| NIT Surathkal | `I11880225` | ror.org/01hz4v948 |

NIT Surathkal's official name is "National Institute of Technology Karnataka" (NITK).

### Step 2: Downloaded every paper (`scripts/fetch_works.py`)

**The query.** One query per institution:

```
https://api.openalex.org/works
    ?filter=authorships.institutions.id:I122964287,
            publication_year:2016-2026,
            type:article|review|conference-paper
    &per_page=200
    &cursor=*
```

In plain English: *"give me every paper where at least one author lists NIT Trichy as their affiliation, published 2016–2026, and that is a journal article, review or conference paper."*

**Why only these three types?** The assignment's `type` column allows only `journal` or `conference`. We first checked what OpenAlex holds for each NIT, grouped by type:

| OpenAlex type | NIT Trichy | NIT Surathkal | Kept? |
|---|---|---|---|
| article | 9,286 | 7,300 | ✅ (journal) |
| review | 26 | 22 | ✅ (journal) |
| conference-paper | 2,366 | 3,485 | ✅ (conference) |
| book-chapter | 932 | 739 | ❌ |
| preprint | 527 | 278 | ❌ not peer-reviewed; often duplicates a published paper |
| erratum, retraction, editorial, paratext, dataset, … | ~250 | ~240 | ❌ not research papers |

**Paging.** OpenAlex returns at most 200 results per request, so the script uses **cursor paging**. Each response includes a `next_cursor`, which we pass back to get the next 200, until there are none left. That took about 115 requests in total.

**Fields we kept** (using `select=` to keep downloads small): `id, doi, title, publication_year, type, primary_location` (journal or conference and its ISSN), `authorships` (every author and their institutions), `cited_by_count`, `referenced_works` (the papers it cites) and `primary_topic` (research field).

**Result:**

| | Papers |
|---|---|
| NIT Trichy | 11,678 |
| NIT Surathkal | 10,807 |
| **Unique total** | **22,416** (69 papers have authors from both NITs and appear under each) |

**Saved to:** `data/raw/NIT_Trichy_works.jsonl` and `data/raw/NIT_Surathkal_works.jsonl`, with one paper per line in JSON.

### Step 3: Downloaded author h-indexes (`scripts/fetch_authors.py`)
- We went through every paper's author list. An author counts as **an NIT author** if, *on that paper*, their affiliation is our NIT.
- That gave **11,377 distinct NIT authors**. OpenAlex can't tell faculty from PhD students, so both are included.
- Most of these appear on only one or two papers; they're mostly students and visitors. We downloaded full author profiles only for the **3,363 authors with 3 or more papers**.
- Query: up to 100 authors per request, using an OR filter:
  ```
  https://api.openalex.org/authors?filter=openalex_id:A123|A456|...   (100 IDs)
  ```
- From each profile we kept the **h-index** (`summary_stats.h_index`), the total papers over the author's career and the total citations.
- **Saved to:** `data/raw/authors.jsonl`. This took about 34 requests.

### Step 4: Got journal quartiles (Q1–Q4)
**Problem:** the SCImago website (scimagojr.com) sits behind a Cloudflare "are you human?" check, so a script can't download its ranking file.

**Solution:** we used a public GitHub repository, [Michael-E-Rose/SCImagoJournalRankIndicators](https://git.tdem.in/Michael-E-Rose/SCImagoJournalRankIndicators). It republishes all SCImago data from 1999 to 2025 as one CSV, saved here as `data/reference/scimago_all.csv` (1 million rows). Each row is *journal × subject area × year*, with its SJR score and ISSNs.

That file has SJR **scores** but no quartile column, so we computed quartiles the same way SCImago does:
1. Within each **subject area and year**, rank all journals by SJR score.
2. Top 25% → **Q1**, 25–50% → **Q2**, 50–75% → **Q3**, bottom 25% → **Q4**.
3. A journal can belong to several subject areas, so we take its **best** quartile, as SCImago's "best quartile" does.
4. Match each paper to its journal by **ISSN**, using **the paper's publication year**. For 2026, which has no SJR data yet, we use the nearest year, 2025.

**Caveat (mention in the report):** the mirror groups journals into **27 broad subject areas**, for example "Engineering". SCImago's official quartiles use about **300 narrower categories**, for example "Mechanical Engineering". Our quartiles are therefore a close approximation, and a few journals may be one quartile off.

### Step 5: Got conference ranks (CORE A\*/A/B/C)
- Downloaded the **ICORE2026** list (986 ranked conferences) from the CORE portal's CSV export: `portal.core.edu.au/conf-ranks/?source=ICORE2026&do=Export`. It's saved as `data/reference/core_conf.csv`.
- Matched each conference paper's venue name to the list.

**Problem we found:** our first approach matched on **acronyms**, and it gave wrong ranks. When we checked by hand, we found:
- "International Conference on **Devices, Circuits** and Systems (**ICDCS**)" had been matched to the A-ranked ICDCS, which is *Distributed Computing* Systems.
- "Computer Vision and **Machine Intelligence** (CVMI)" had been given A\*, as if it were ICCV.
- "International Test Conference **India**" and "**InGARSS**" (India) had inherited the ranks of the main international conferences.
- **Workshops** such as CVPRW and the INFOCOM workshops had inherited the main conference's rank.

**Fix:** a venue now gets a CORE rank only if:
- its **title words** (ignoring filler words like "IEEE", "International", "Conference") overlap with the CORE title by **at least 75%**, or
- the acronym matches **and** the titles also overlap by at least 50%.

Venues containing "India", "Workshop" or a "…W)" acronym are never ranked, because CORE doesn't rank regional editions or workshops.

**Result:** 175 conference papers are ranked (A\* 13, A 10, B 29, C 123). Most of our 5,855 conference papers are at Indian or regional IEEE conferences that **CORE does not rank**, so their `quartile` cell is blank. That's expected, not an error.

### Step 6: Found citation links to other Indian institutes (`scripts/fetch_links.py`)
The assignment needs two True/False columns:
- `cites_indian_inst`: *does this paper cite a paper from another Indian institution?*
- `cited_by_indian_inst`: *is this paper cited by a paper from another Indian institution?*

Checking each of our 22,416 papers one at a time would take about 45,000 requests. Instead we checked **100 papers per request** with OpenAlex's OR filter, and asked only for **Indian** papers:

```
# Indian papers that OUR papers cite (their references)
/works?filter=cited_by:W1|W2|...|W100,institutions.country_code:IN

# Indian papers that CITE our papers
/works?filter=cites:W1|W2|...|W100,institutions.country_code:IN
```

225 batches were needed in each direction. For each paper returned, we saved:
- its ID, DOI and year
- its authors and their institutions (with country)
- for citing papers, which of our papers it cites

| File | Records | Meaning |
|---|---|---|
| `data/raw/links_refs.jsonl` | 133,571 | Indian papers that our papers cite |
| `data/raw/links_citers.jsonl` | 116,150 | Indian papers that cite our papers |

**Problem: request limits.** OpenAlex without an account allows only about **1,000 requests per day**, and this step needed about **1,600**. We made the script **resumable**: it records each finished batch in a `.done` file, so a rerun continues where it stopped. We then created a **free OpenAlex API key** (openalex.org → sign up → Settings → API), which raises the limit to **10,000 requests per day**, and finished the run. The key is passed through the `OPENALEX_API_KEY` environment variable and is **not stored in any file**.

These two files are also the raw material for the **citation network (Task 2)** and the **citation flow analysis (Task 3)**.

### Step 7: Built the final CSV files (`scripts/build_dataset.py`)
This script reads only the saved files from Steps 2–6 and writes:

**`data/group12_data.csv`**: **49,704 rows**, one per *(paper, NIT author)* pair. A paper with 3 NIT authors appears in 3 rows. This matches the assignment's "author" column, and per-faculty statistics become a simple group-by.

How each **required** column was filled:

| Column | Where it comes from |
|---|---|
| `group` | Always `12` |
| `institution` | `NIT Trichy` or `NIT Surathkal`, depending on which download the paper came from |
| `author` | The author's name in OpenAlex (only authors affiliated with that NIT on that paper) |
| `title` | Paper title |
| `year` | Publication year |
| `type` | `conference` if OpenAlex calls it a conference paper or its venue is a conference; otherwise `journal` |
| `journal_name` | Name of the journal or conference (`primary_location.source`) |
| `issn` | The journal's ISSNs, separated by `;` (blank for conferences) |
| `doi` | DOI link |
| `citations` | OpenAlex `cited_by_count` on **7 October 2026** |
| `quartile` | Q1–Q4 for journals (Step 4) or `CORE A*/A/B/C` for conferences (Step 5); blank if unranked |
| `coauthor_institutes` | Every **Indian** institution on the paper's author list **other than our two NITs**, separated by `;` |
| `cites_indian_inst` | `True` if any reference in `links_refs.jsonl` has an author from an Indian institution other than our two NITs |
| `cited_by_indian_inst` | `True` if any citing paper in `links_citers.jsonl` has an author from an Indian institution other than our two NITs |

**Extra columns** we added because later tasks need them:

| Column | Purpose |
|---|---|
| `author_id` | The author's OpenAlex ID. Two people can share a name, so use this for counting and networks. |
| `department` | Parsed from the affiliation text, e.g. "Department of Mechanical Engineering, National Institute of Technology, Tiruchirappalli". We take the "Department of / School of / Centre for …" part and expand abbreviations: ECE → Electronics and Communication Engineering, CSE, EEE, ICE, MME, IT, ME, CE. About **83%** of rows have one. |
| `openalex_id` | The paper's OpenAlex ID, used to join with the raw files |
| `field`, `domain` | Research area from OpenAlex's topic classification, for the research-area breakdown |
| `n_authors` | Number of authors on the paper |
| `both_nits` | `True` if the paper has authors from both NITs |

**`data/faculty.csv`**: one row per NIT author, with name, institution, most common department, papers from 2016 to 2026, citations, **h-index** and total papers over their career.

### Step 8: Checked the results

| | Unique papers |
|---|---|
| Type | 16,630 journal · 5,855 conference |
| Journal quartile | Q1 5,543 · Q2 5,669 · Q3 2,989 · Q4 894 · about 1,500 journal papers whose journal isn't in SCImago |
| CORE rank | A\* 13 · A 10 · B 29 · C 123 · the rest unranked |
| `cites_indian_inst` | True 17,436 · False 5,049 |
| `cited_by_indian_inst` | True 13,517 · False 8,968 (4,612 papers have 0 citations at all) |
| Missing in OpenAlex | 759 papers have no venue name and 205 have no DOI |

Checks that passed:
- All years are between 2016 and 2026.
- No paper with 0 citations is marked `cited_by_indian_inst = True`.
- No blanks in group, institution, author, title, year, type or citations.
- Every CORE match was reviewed by hand, which is how the wrong matches in Step 5 were found and fixed.
- **Fix found during Task 2:** a few OpenAlex records list **a paper as citing itself**. Originally 8 papers were wrongly marked `cites_indian_inst = True` and 10 `cited_by_indian_inst = True` just because they cite themselves and have a co-author from another Indian institute. Self-citations are now ignored, and the numbers above are the corrected ones.

---

## Task 2: Network files (`scripts/build_networks.py`)

### Decisions we agreed on as a team
| Question | Decision |
|---|---|
| Which papers? | All 22,416 papers in `group12_data.csv`, with no subject filter |
| Citation network edges | Edges between our own papers, plus edges to and from papers of **other Indian institutes**. References to foreign papers are left out because we have no institution data for them. |
| Authorship network nodes | Every pair on one of our papers where **at least one author is from our NITs**; the co-author can be from anywhere |
| Very large papers | Papers with **more than 50 authors** are left out of the authorship network only (3 papers), as is standard practice in co-authorship studies |
| `total_citations` in `indian_connections.csv` | Summed citations of the co-authored papers, plus extra columns for citation in-flow and out-flow |
| Where metrics are computed | PageRank, in-degree, centrality and communities are computed on the network **within our two NITs**, as the brief requires. Cross-institute edges stay in the CSV files. |

### 2a. `data/citation_network.csv`: 220,027 directed edges ("source cites target")
Required columns: `source_doi, target_doi, source_inst, target_inst, year`. Extra columns: `edge_type, cross_institute, source_id, target_id`.

| `edge_type` | Edges | Meaning | Built from |
|---|---|---|---|
| `internal` | 27,680 | Our paper cites another of our papers | `referenced_works` of each paper (Step 2) |
| `out_indian` | 103,252 | Our paper cites a paper from another Indian institute | `links_refs.jsonl` (Step 6) |
| `in_indian` | 89,095 | A paper from another Indian institute cites ours | `links_citers.jsonl` (Step 6) |

- `year` is the year of the **citing** paper, which is when the citation happened.
- `source_inst` and `target_inst`:
  - **Our papers:** `NIT Trichy`, `NIT Surathkal`, or both separated by `;`.
  - **Outside papers:** all of their Indian institutions, separated by `;`.
- Some papers have no DOI in OpenAlex: 205 of ours and about 400 outside ones. For these the DOI cell is blank, but `source_id`/`target_id` (OpenAlex IDs) are always filled, so use the IDs as node keys.
- **Dropped edges:**
  - **Self-citations** (a paper citing itself).
  - **5,379 references to older or non-research papers by our own NITs.** These are outside the 2016–2026 corpus, so they are neither internal nor "another Indian institute".
  - **1,092 citations from such papers.**

**Metrics** are computed on the internal network: 22,416 papers and 27,680 edges. 8,793 papers are cited at least once by another of our papers.
- **In-degree** = how many of our papers cite this paper.
- **PageRank** uses damping 0.85.
- Saved to `data/network_metrics/citation_paper_metrics.csv`, with one row per paper, sorted by PageRank. It also has counts of Indian papers citing and cited.

### 2b. `data/authorship_network.csv`: 79,338 co-authorship rows
Required columns: `author_a, author_b, paper_doi, inst_a, inst_b, year`. Extra columns: `edge_category, cross_institution, author_a_id, author_b_id, paper_id`.

- **One row per (pair of authors, paper).** If two people wrote 5 papers together, there are 5 rows, so the edge weight is the number of rows.
- **Pairs are undirected.** They're stored with the smaller author ID first, so each pair appears only once per paper.
- `inst` is the author's institution **on that paper**. For NIT authors it's `NIT Trichy` or `NIT Surathkal`; otherwise it's their institution names, or `Unknown`.

| `edge_category` | Rows | Meaning |
|---|---|---|
| `same_nit` | 37,572 | Both authors from the same NIT |
| `nit_nit` | 157 | NIT Trichy author with a NIT Surathkal author |
| `nit_indian` | 22,418 | NIT author with an author at **another Indian institute** (the "Indian connections") |
| `nit_foreign` | 12,080 | NIT author with a foreign co-author |
| `nit_unknown` | 7,111 | Co-author has no institution in OpenAlex |

- **Left out:**
  - 5,230 authorships that have no OpenAlex author ID and so can't be identified
  - the 3 papers with more than 50 authors
- If OpenAlex lists the same author twice on a paper, their NIT affiliation is kept.

**Metrics** are computed on the NIT-only network: 11,373 authors and 20,584 weighted edges.
- **Degree centrality:** number of distinct NIT co-authors ÷ (number of authors − 1).
- **Betweenness centrality:** exact (not sampled), using unweighted shortest paths.
- **Louvain communities:** NetworkX, weighted by number of joint papers, random seed 42 so the result is reproducible. The algorithm found 1,531 communities, 87 of them with 10 or more members. **Modularity 0.934** (very strong group structure, typical of department-based collaboration).
- The network has 1,464 separate pieces. The largest connected piece contains 8,909 authors (78%).
- Saved to `data/network_metrics/author_metrics.csv`. It also has each author's number of partner Indian institutes.

### 2c. `data/indian_connections.csv`: 4,452 rows (our NIT × partner Indian institute)
Required columns: `your_inst, partner_inst, shared_papers, total_citations`. Extra columns: `cites_from_partner, cites_to_partner, partner_id`.

| Column | Meaning |
|---|---|
| `shared_papers` | Our papers co-authored with someone from the partner |
| `total_citations` | Total citations of those shared papers |
| `cites_from_partner` | Citation in-flow: citations from partner papers to our papers |
| `cites_to_partner` | Citation out-flow: citations from our papers to partner papers |
| `partner_id` | OpenAlex ID, because different institutes can share a display name |

- The other NIT counts as a partner. For example, NIT Surathkal is one of NIT Trichy's partners.
- 1,213 rows have co-authored papers. The rest are linked only by citations.
- **Citation flow rule:** a citing paper that **also** has authors from our institution is a self-institution citation and is **not** counted as flow from a partner. Every Indian institute on the other paper gets one count per citation.

**Top partners by shared papers:**
| NIT Trichy | | NIT Surathkal | |
|---|---|---|---|
| VIT University | 275 | Manipal Academy of Higher Education | 555 |
| SRM Institute of Science & Technology | 231 | VIT University | 210 |
| IIT Madras | 191 | IISc Bangalore | 184 |
| Anna University | 156 | Nitte University | 134 |
| Bharathidasan University | 156 | Siddaganga Institute of Technology | 116 |

### Files for visualisation (Gephi)
- `data/network_metrics/citation_internal.gexf`: internal citation network
- `data/network_metrics/authorship_nit.gexf`: NIT co-authorship network, with author names and community labels

Open either file in Gephi with File → Open.
- `data/network_metrics/network_summary.json`: all the counts above in one file

### How we checked for mistakes (`scripts/verify_networks.py`)
A separate script recomputes the results **by a different route**, mostly from `group12_data.csv` and the raw files, and compares. All **35 checks pass**, including:
- Internal edges exactly equal the set of "our paper → our paper" references (27,680 = 27,680).
- Every `out_indian` target really is in its source paper's reference list.
- `year` and DOIs match the dataset.
- Every paper with `cites_indian_inst` or `cited_by_indian_inst` = True is explained by an edge in the network, and every such edge's paper is marked True. This check found the self-citation error described above.
- PageRank sums to 1, and in-degree matches the edge list.
- Number of pairs per paper = C(k,2) − C(outside co-authors,2), for every paper.
- No self-pairs, no duplicates, and every pair contains a NIT author. This check found the duplicate-author issue, which is now fixed.
- Degree centrality = degree / (n − 1) for every author.
- `shared_papers` and `total_citations` match the `coauthor_institutes` column of the dataset.
- `cites_from_partner` and `cites_to_partner` match a fresh edge-by-edge recount for every row.

Run it with: `python verify_networks.py`. The last line prints `ALL CHECKS PASSED`.

---

## Folder layout

```
assignment_2/
├── README.md                ← this file
├── assignment.md            ← what the assignment asks for
├── scripts/
│   ├── fetch_works.py       ← Step 2: papers
│   ├── fetch_authors.py     ← Step 3: author h-index
│   ├── fetch_links.py       ← Step 6: Indian citation links (resumable)
│   ├── build_dataset.py     ← Steps 4, 5, 7: quartiles, CORE ranks, final CSVs
│   ├── build_networks.py    ← Task 2: three network CSVs + metrics
│   └── verify_networks.py   ← Task 2: 35 independent checks
└── data/
    ├── README.md            ← short data dictionary
    ├── group12_data.csv     ← MAIN SUBMISSION FILE
    ├── citation_network.csv     ← Task 2 submission
    ├── authorship_network.csv   ← Task 2 submission
    ├── indian_connections.csv   ← Task 2 submission
    ├── faculty.csv          ← faculty list with h-index
    ├── network_metrics/     ← PageRank, centralities, communities, Gephi files, summary
    ├── raw/                 ← raw OpenAlex downloads (JSON lines)
    │   ├── NIT_Trichy_works.jsonl
    │   ├── NIT_Surathkal_works.jsonl
    │   ├── authors.jsonl
    │   ├── links_refs.jsonl     (+ .done progress file)
    │   └── links_citers.jsonl   (+ .done progress file)
    └── reference/
        ├── scimago_all.csv  ← SJR data (mirror)
        └── core_conf.csv    ← ICORE2026 conference ranks
```

## How to re-run Task 1

You only need this to refresh the data, for example for newer citation counts. Run it in PowerShell from the `scripts/` folder:

```powershell
$env:OPENALEX_API_KEY = "your-key"   # free key from openalex.org/settings/api
python fetch_works.py     # papers (about 115 requests)
python fetch_authors.py   # h-index (about 34 requests)
python fetch_links.py     # Indian citation links (about 1,600 requests, resumable)
python build_dataset.py   # writes group12_data.csv and faculty.csv
python build_networks.py  # Task 2 files (about 15 minutes, mostly exact betweenness)
python verify_networks.py # should end with ALL CHECKS PASSED
```

Each download step skips anything already saved in `data/raw/`. To download fresh data, delete those files first. It needs Python 3 with `requests` and `pandas`.

---

## Known limitations (mention these in the report)

1. **Faculty vs. students.** OpenAlex lists everyone affiliated with the NIT, including PhD students and project staff. Authors with 5 or more papers (about 2,000) are a reasonable stand-in for faculty. For an exact list, cross-check with the faculty pages on the NIT websites.
2. **Approximate quartiles.** They're computed from 27 broad SCImago subject areas, not SCImago's roughly 300 official categories (Step 4).
3. **CORE covers mainly computing conferences.** Most engineering conferences at our NITs are unranked, so this column is mostly blank for conferences.
4. **OpenAlex coverage.** A few papers may be missing or have wrong affiliations, and 759 have no venue name and 205 no DOI.
5. **Name variants.** OpenAlex sometimes splits one person into two author IDs, for example "R. Kumar" and "Rajesh Kumar". This slightly undercounts some people's papers.
6. **Snapshot date.** Citation counts are as of **7 October 2026**.

---

## What to do next

1. **Task 3:** Indian connectivity analysis (citation in-flow and out-flow, partner institutes, Jaccard similarity of research topics).
2. **Tasks 4–5:** statistics report (at most 10 slides) and interactive dashboard.
