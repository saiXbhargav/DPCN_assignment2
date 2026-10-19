# DPCN Research Mapping Project: Team 12

**Our institutions:** NIT Trichy and NIT Surathkal
**Period:** 2016–2026
**Instructor:** Chittaranjan Hens

The full list of assignment tasks is in [assignment.md](assignment.md). This file explains **what we have done and exactly how we got the data**, so anyone on the team can understand it, defend it in the report and reproduce it.

---

## Status at a glance

| Task | Status |
|---|---|
| 1. Data collection (`group12_data.csv`) | ✅ Done. Faculty only, science / engineering papers only. Every required column is filled. |
| 2. Network files (`citation_network.csv`, `authorship_network.csv`, `indian_connections.csv`) | ✅ Done. All 44 automated checks pass. |
| Analyses asked for by the team and in class (large-paper bias, institute and branch comparison, IF > 5 / IF > 10, impact ratio, collaboration) | ✅ Done: [data/analysis/ANALYSIS.md](data/analysis/ANALYSIS.md) |
| 3. Indian connectivity analysis | ✅ Done: citation in/out-flow by year with a chart, impact ratio, top 10 citing institutes and papers, partner ranking, cross-cluster flags (NIT ↔ IIT / CSIR / IISER / DAE / ISRO / DRDO …), Jaccard topic similarity, hub authors ([ANALYSIS.md](data/analysis/ANALYSIS.md), section 5) |
| 4. Statistics report | ⏳ Not started |
| 5. Interactive dashboard | ⏳ Not started |

## The data in one minute

| | |
|---|---|
| Papers | **18,343**: 9,184 for NIT Trichy and 9,206 for NIT Surathkal. 47 have faculty from both NITs and count for each. |
| Rows in `group12_data.csv` | **21,932**, one per (paper, NIT faculty member) |
| Faculty | **811** regular faculty in science / engineering branches (current and former, 2016–2026); 663 of them have papers |
| Who is left out | PhD students and other non-faculty authors; Management and Humanities faculty; papers on business, economics, social sciences, psychology or arts |
| Citation network | 181,189 edges |
| Authorship network | 25,691 co-author rows; faculty graph of 663 people |

---

## Where the data came from

| What we needed | Source | How we got it |
|---|---|---|
| Papers, authors, citations, references, topics | **OpenAlex** (openalex.org), a free, open database of about 250 million research papers | Its REST API, called from Python scripts |
| Who is faculty (not a PhD student), their department and rank | **The institutes' own faculty pages**, current and archived (one copy per year, 2016–2026) | nitt.edu, nitk.ac.in and the Internet Archive (Wayback Machine) |
| Author h-index, ORCID | OpenAlex author profiles | The same API |
| Field-weighted citation impact (FWCI), top-10% flag | OpenAlex | The same API |
| Journal impact (for IF > 5 / IF > 10) | OpenAlex journal statistics (2-year mean citedness) | The same API |
| Journal quartiles (Q1–Q4) | **SCImago Journal Rank (SJR)** data | A public GitHub mirror, because scimagojr.com blocks automated downloads |
| Conference ranks (A\*/A/B/C) | **CORE** conference portal (ICORE2026 list) | The portal's CSV export |

We chose OpenAlex because the assignment recommends it, it's free, and it has an API. It also links every paper to its **institutions**, its **references** (`referenced_works`) and the **papers that cite it**, which the network tasks need.

The scripts in [scripts/](scripts/) run in this order:

```
fetch_works → fetch_authors → fetch_links → fetch_faculty → build_roster → match_faculty
   → fetch_impact (works, authors, sources, authorids) → build_dataset → build_networks
   → verify_networks → fetch_impact partners → analysis
```

The `fetch_*` scripts download from the internet and save **raw** files to `data/raw/`. Every `build_*` script uses only those saved files, so we can rebuild everything as often as we like without downloading again.

---

## Step-by-step: what we did

### Step 0: Understood the assignment
- Read the instruction note (`DPCN_Instruction_Note (1).docx`) and the slides (`DPCN Research Mapping Project_n4.pptx`).
- Slide 5 assigns **Group 12 → "Top NITs" → NIT Trichy and NIT Surathkal**.
- Wrote [assignment.md](assignment.md), our checklist of everything to submit.
- Agreed as a team on the changes the professor asked for:
  - faculty only;
  - science / engineering only;
  - check the bias from very large papers;
  - co-authored papers are not citation links;
  - compare institutes and branches, and find collaboration partners;
  - the measures from class (IF > 5, IF > 10, impact ratio, matching names by ORCID / Scopus / OpenAlex / affiliation).

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

**Fields we kept** (using `select=` to keep downloads small): `id, doi, title, publication_year, type, primary_location` (journal or conference and its ISSN), `authorships` (every author, their institutions and the raw affiliation text), `cited_by_count`, `referenced_works` (the papers it cites) and `primary_topic` (domain, field and subfield).

**Result:** 11,678 papers for NIT Trichy and 10,807 for NIT Surathkal, **22,416 unique**. This is everything with any NIT author. Steps 7–10 narrow it down to faculty and to science / engineering.

**Saved to:** `data/raw/NIT_Trichy_works.jsonl` and `data/raw/NIT_Surathkal_works.jsonl`, with one paper per line in JSON.

### Step 3: Downloaded author h-indexes (`scripts/fetch_authors.py`)
- An author counts as **an NIT author** if, *on that paper*, their affiliation is our NIT. There are 11,377 of them, including students.
- We downloaded OpenAlex profiles for the **3,363 authors with 3 or more papers** (100 per request, about 34 requests), saved in `data/raw/authors.jsonl`.
- After faculty matching (Step 8), `fetch_impact.py authors` added the profiles of **521 more faculty IDs** (`data/raw/authors_extra.jsonl`).
- From each profile we keep the **h-index** (`summary_stats.h_index`), the total papers over the author's career and the ORCID.

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

Venues containing "India", "Workshop" or a "…W)" acronym are never ranked, because CORE doesn't rank regional editions or workshops. Most of our conference papers are at Indian or regional IEEE conferences that **CORE does not rank**, so their `quartile` cell is blank. That's expected, not an error.

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

225 batches were needed in each direction. For each paper returned, we saved its ID, DOI, year, its authors and their institutions (with country), and, for citing papers, which of our papers it cites.

| File | Records | Meaning |
|---|---|---|
| `data/raw/links_refs.jsonl` | 133,571 | Indian papers that our papers cite |
| `data/raw/links_citers.jsonl` | 116,150 | Indian papers that cite our papers |

**Request limits.** OpenAlex without an account allows only about **1,000 requests per day**, and the free budget is shared by everyone on the same network. The script is **resumable**: it records each finished batch in a `.done` file, so a rerun continues where it stopped. With a **free OpenAlex API key** (openalex.org → sign in → Settings → API) the limit is **10,000 requests per day**. The key is read from the `OPENALEX_API_KEY` environment variable and is **not stored in any file**.

### Step 7: Built the faculty roster (`fetch_faculty.py`, `build_roster.py`)
OpenAlex can't tell faculty from PhD students, so the faculty list comes from the institutes themselves.

**Pages downloaded** (501 pages, saved in `data/raw/faculty_pages/` with `manifest.csv`):
- **NIT Trichy:**
  - the institute-wide faculty table (name, designation, department, email ID);
  - each department's faculty page, which lists some faculty the central table misses.
- **NIT Surathkal:**
  - the teaching-staff directory (2016–2018);
  - the telephone directory (2024–2026, with designations);
  - each department's `/people` page, which also lists research scholars;
  - the current faculty profile pages, some with ORCID / Scopus IDs.
- To include faculty who **retired or left** during 2016–2026, we took **one archived copy per year (2016–2026)** of each page from the Internet Archive.
- `nitt.edu` has a broken certificate chain, so certificate checks are skipped for that one site only (public, read-only pages).

**Turning the pages into a roster** (`data/reference/faculty_roster.csv`):
- Names are cleaned. Titles are removed and initials split, so "Dr.S.R.BALASUNDARAM" becomes "S R Balasundaram".
- Records are merged across years and sources into one row per person:
  - NIT Trichy records by email ID;
  - otherwise by a compatible name in the same department, including the glued names of the old directory such as "DWARAKISHG.S.".
- **Who counts as faculty:** regular faculty of every rank (Assistant, Associate, Professor, Professor HAG, Director).
- **Who doesn't:** adjunct, visiting, temporary or contract staff, post-docs and DST-INSPIRE fellows. They are kept with `regular = False`.
- Each person gets one canonical **branch** (CSE, ECE, EEE, Mechanical, Civil, Chemical, MME, Chemistry, Physics, Mathematics, ICE, Production, IT, Mining, Water Resources & Ocean, Computer Applications, Energy & Environment, Architecture).
- Management, Humanities, Physical Education and Training & Placement are marked `science_engineering = False`.

**Result:**

| | Regular faculty | Science / engineering | Current | Former |
|---|---|---|---|---|
| NIT Trichy | 467 | 431 | 344 | 87 |
| NIT Surathkal | 411 | 380 | 269 | 111 |

`research_scholars.csv` holds 1,365 names listed as research scholars. They are used to avoid matching a student with a faculty member.

### Step 8: Matched faculty to OpenAlex authors (`match_faculty.py`)
A faculty member is linked to an OpenAlex author ID who has papers at the same NIT when either:
- **the ORCID is the same** (from the faculty profile, or from the OpenAlex author record via `fetch_impact.py authorids`), or
- **the names agree and the department agrees.** Initials, word order, one typo or glued words are allowed, for example "M R Ramesh" = "Ramesh M R" and "N Samsudeen" = "Samsudeen Naina Mohamed". The department named in the author's own NIT affiliation text must be the faculty member's department.

Other rules:
- One person can have **several OpenAlex IDs**. OpenAlex often splits people; **382 faculty have 2 or more IDs**, which are merged.
- One ID belongs to at most one person per institute. Faculty who moved between the two NITs (V. Vignesh Kumar, I. Jeyaraman, Ruben Sudhakar D) keep the same ID at both.
- Authorships with **no OpenAlex author ID** are assigned by a clear name match within the same department.
- **Team review.** 59 uncertain links were checked by hand: 21 accepted, 34 rejected.
  - The decisions are in `faculty_match_overrides.csv` (`faculty_id, author_id, decision, faculty_name, openalex_name`) and are applied on every run.
  - Two 1-paper IDs that were accepted for two different people with the same name are left out.
- **Accuracy.** A random check of 50 automatic links found about 95% correct; the doubtful ones are single-paper links with very common surnames.
- **Scopus.** 61 NIT Surathkal profiles list a Scopus ID, but OpenAlex no longer stores Scopus author IDs (0 of 4,948 NIT authors). Linking them would need an Elsevier Scopus API key.

**Result:** **701 of 878 faculty are linked** (NIT Trichy 379, NIT Surathkal 322), with 1,486 links: 1,403 by name, 62 by ORCID and 21 by team decision.

`unmatched_prolific_authors.csv` lists 119 NIT authors with 15+ papers and no faculty link. Most are PhD scholars or post-docs; a few are faculty missing from every list we could download.

### Step 9: Extra OpenAlex measures (`fetch_impact.py`, about 500 requests with the API key, 19 October 2026)

| Step | What | Saved to |
|---|---|---|
| `works` | **FWCI** (citations relative to the world average for the same field, type and year; 1.0 = average) and the **top 10% cited** flag, for all 22,416 papers | `raw/works_impact.jsonl` |
| `authors` | Profiles (h-index) of 521 faculty IDs not in `authors.jsonl` | `raw/authors_extra.jsonl` |
| `sources` | **Journal impact** for 3,966 venues (details below) | `raw/sources.jsonl` |
| `authorids` | ORCID (and Scopus, where OpenAlex has one) of 4,948 NIT authors with 2+ papers | `raw/author_ids.jsonl` |
| `partners` | Papers per research subfield, 2016–2026, for 129 partner institutes: the top partners plus the strongest collaboration candidates | `raw/partner_subfields.jsonl` |
| `institutions` | Type (education, company, healthcare, …) and parent organisations of all 2,350 partner institutes, plus the parents themselves, so a lab under CSIR or DAE is recognised | `raw/institutions.jsonl` |
| `citers` | Title, year, venue and citation count of the 51,195 outside Indian papers that cite us (50,871 still exist in OpenAlex) | `raw/citers_info.jsonl` |

The journal impact is OpenAlex's **2-year mean citedness**. This is the impact-factor formula (citations in a year to the journal's papers of the previous two years ÷ number of those papers) applied to OpenAlex data. We use it for **IF > 5 / IF > 10** because Clarivate's JCR impact factor is not open.

The citation counts in `group12_data.csv` stay as collected on **7 October 2026**; these files only add the normalised measures.

### Step 10: Built the final CSV files (`build_dataset.py`)
**Scope:**
- **Faculty only.** A row exists only for a regular science / engineering faculty member (Step 7) whose affiliation **on that paper** is that NIT.
- **Science / engineering papers only.** Papers whose OpenAlex field is Business/Management/Accounting, Economics, Social Sciences, Psychology or Arts & Humanities are dropped (1,156 papers; constant `EXCLUDED_FIELDS`).
  - Decision Sciences (operations research) and the Health / Life Sciences fields are kept. At our NITs those are mostly engineering papers, for example CNNs on retinal images or ECG classification.
  - A further 2,917 papers are dropped because no faculty member of our scope is an author; most are written by PhD students with outside co-authors.
- The rule in Step 11 decides `cites_indian_inst` / `cited_by_indian_inst`.

**`data/group12_data.csv`**: **21,932 rows**, one per *(paper, NIT faculty member)*, and **18,343 papers**:
- Type: 13,571 journal, 4,772 conference
- Journal quartile: Q1 4,599 · Q2 4,825 · Q3 2,485 · Q4 652 · 1,010 journal papers whose journal isn't in SCImago
- CORE rank: A\* 3 · A 6 · B 16 · C 98 · the rest unranked
- `cites_indian_inst` (per institution and paper): True 14,160 · False 4,230
- `cited_by_indian_inst`: True 10,409 · False 7,981
- Missing in OpenAlex: 595 papers have no venue name and 68 no DOI

How each **required** column is filled:

| Column | Where it comes from |
|---|---|
| `group` | Always `12` |
| `institution` | `NIT Trichy` or `NIT Surathkal`: the faculty member's institute on that paper |
| `author` | The faculty member's name as on the institute website |
| `title` | Paper title |
| `year` | Publication year |
| `type` | `conference` if OpenAlex calls it a conference paper or its venue is a conference; otherwise `journal` |
| `journal_name` | Name of the journal or conference (`primary_location.source`) |
| `issn` | The journal's ISSNs, separated by `;` (blank for conferences) |
| `doi` | DOI link |
| `citations` | OpenAlex `cited_by_count` on **7 October 2026** |
| `quartile` | Q1–Q4 for journals (Step 4) or `CORE A*/A/B/C` for conferences (Step 5); blank if unranked |
| `coauthor_institutes` | Every **Indian** institution on the paper's author list **other than our two NITs**, separated by `;` |
| `cites_indian_inst` | `True` if the paper cites a paper of another Indian institute, under the co-authorship rule (Step 11) |
| `cited_by_indian_inst` | `True` if a paper of another Indian institute cites it, under the same rule |

**Extra columns:**

| Column | Purpose |
|---|---|
| `faculty_id` | Roster ID (`T…` NIT Trichy, `S…` NIT Surathkal); use this to count per person |
| `author_id` | The OpenAlex author ID on that paper (a person can have several) |
| `department` | The faculty member's branch, from the roster |
| `designation`, `faculty_status` | Rank, and current or former faculty |
| `openalex_id`, `author_position` | The paper's OpenAlex ID and the author's position on it (used to join with the raw files) |
| `field`, `domain`, `subfield` | Research area from OpenAlex's topic classification |
| `n_authors`, `both_nits` | Number of authors; `True` if the paper has authors affiliated with both NITs |
| `fwci`, `top10pct` | Field-weighted citation impact and the top-10% flag (Step 9) |
| `journal_if_2yr` | The journal's 2-year mean citedness (Step 9); blank for conferences |

**`data/faculty.csv`**: one row per science / engineering faculty member (811 rows, 663 with papers). Columns:
- institution, `faculty_id`, main OpenAlex ID and all IDs, name, department, designation, current/former, years seen on the website;
- papers and citations in 2016–2026, mean FWCI and top journal;
- `h_index`: OpenAlex career h-index of the main ID;
- `h_index_2016_2026`: computed from our papers over all of the person's IDs.

### Step 11: Co-authored papers are not citation links (`flow.py`)
**The case raised by the team:** a NIT Trichy paper Q cites paper P, which NIT Trichy wrote **together with IIT Madras**. That is NIT Trichy citing its own work. It must not count as NIT Trichy citing IIT Madras, nor as IIT Madras receiving a citation from NIT Trichy.

**The rule** (one function, used by every script). A citation between our paper A (institute N) and paper B gives credit to an outside institute Y only if:
- **N is not on B.** If it is, it's an institutional self-citation and nobody gets credit.
- **Y is not on A.** A's own co-authors citing their own institute is not a link between N and Y.

Applied to:
- `cites_indian_inst` and `cited_by_indian_inst` (decided for each row's own NIT);
- the in-flow and out-flow columns of `indian_connections.csv`;
- the citation network's edge types (below).

Self-citations (a paper citing itself, which some OpenAlex records contain) are also ignored.

---

## Task 2: Network files (`scripts/build_networks.py`)

### Decisions we agreed on as a team
| Question | Decision |
|---|---|
| Which papers? | All 18,343 papers in `group12_data.csv` |
| Citation network edges | Edges between our own papers, plus edges to and from papers of **other Indian institutes**. References to foreign papers are left out because we have no institution data for them. |
| Authorship network nodes | NIT **faculty** (one node per person, even when OpenAlex splits them) and their co-authors from other institutions. PhD students and other NIT staff are not nodes. |
| Very large papers | Papers with **more than 50 authors** are left out of the authorship network, as is standard practice in co-authorship studies. After the faculty and subject filters there are none left (see Analyses). |
| `total_citations` in `indian_connections.csv` | Summed citations of the co-authored papers, plus extra columns for citation in-flow and out-flow |
| Where metrics are computed | PageRank, in-degree, centrality and communities are computed on the network **within our two NITs**, as the brief requires. Cross-institute edges stay in the CSV files. |

### 2a. `data/citation_network.csv`: 181,189 directed edges ("source cites target")
Required columns: `source_doi, target_doi, source_inst, target_inst, year`. Extra columns: `edge_type, cross_institute, source_id, target_id`.

| `edge_type` | Edges | Meaning |
|---|---|---|
| `internal` | 23,822 | Our paper cites another of our papers |
| `out_indian` | 80,066 | Our paper cites a paper from another Indian institute |
| `in_indian` | 67,114 | A paper from another Indian institute cites ours |
| `out_shared_inst` | 5,856 | Our paper cites an outside paper that shares an institute with it through co-authorship: kept, but **not** counted as flow (Step 11) |
| `in_shared_inst` | 4,331 | The same in the other direction |

- `year` is the year of the **citing** paper, which is when the citation happened.
- `source_inst` and `target_inst`:
  - **Our papers:** the NIT(s) with a faculty author on them.
  - **Outside papers:** all of their Indian institutions, separated by `;`.
- `cross_institute` is `True` for citations between the two NITs and for `out_indian` / `in_indian`.
- Some papers have no DOI in OpenAlex. Their DOI cell is blank, but `source_id` / `target_id` (OpenAlex IDs) are always filled, so use the IDs as node keys.
- **Dropped edges:**
  - 5,450 references to papers by our own NITs that are outside the corpus (older papers, students' papers, other subjects) and have no other Indian institute;
  - 2,220 citations from such papers.

**Metrics** are computed on the internal network: 18,343 papers and 23,822 edges. 7,656 papers are cited at least once by another of our papers.
- **In-degree** = how many of our papers cite this paper.
- **PageRank** uses damping 0.85.
- Saved to `data/network_metrics/citation_paper_metrics.csv`, one row per paper, sorted by PageRank, with counts of Indian papers citing and cited.

### 2b. `data/authorship_network.csv`: 25,691 co-authorship rows
Required columns: `author_a, author_b, paper_doi, inst_a, inst_b, year`. Extra columns: `edge_category, cross_institution, author_a_id, author_b_id, paper_id`.

- **One row per (pair of authors, paper).** If two people wrote 5 papers together, there are 5 rows, so the edge weight is the number of rows.
- **Pairs are undirected.** They're stored with the smaller ID first.
- Node IDs:
  - NIT faculty use their `faculty_id` (e.g. `T0379`);
  - outside co-authors use their OpenAlex ID.
- `inst` is the author's institution **on that paper**: `NIT Trichy` / `NIT Surathkal` for faculty; otherwise their institution names, or `Unknown`.

| `edge_category` | Rows | Meaning |
|---|---|---|
| `same_nit` | 3,861 | Two faculty of the same NIT |
| `nit_nit` | 55 | A NIT Trichy and a NIT Surathkal faculty member |
| `nit_indian` | 12,038 | Faculty with an author at **another Indian institute** (the "Indian connections") |
| `nit_foreign` | 6,028 | Faculty with a foreign co-author |
| `nit_unknown` | 3,709 | Co-author has no institution in OpenAlex |

Left out: 21,360 authorships by NIT people who are not faculty in our scope, and 1,238 outside authorships with no OpenAlex author ID.

**Metrics** are computed on the faculty-only graph: **663 faculty, 967 weighted edges**.
- **Degree centrality:** distinct faculty co-authors ÷ (number of faculty − 1).
- **Betweenness centrality:** exact (not sampled), using unweighted shortest paths.
- **Louvain communities:** NetworkX, weighted by number of joint papers, random seed 42 so the result is reproducible.
  - 162 communities, 18 of them with 10 or more members.
  - **Modularity 0.844** (strong group structure, typical of department-based collaboration).
- The graph has 139 separate pieces; the largest contains 496 faculty.
- Saved to `data/network_metrics/author_metrics.csv`, including each faculty member's number of partner Indian institutes.

### 2c. `data/indian_connections.csv`: 4,053 rows (our NIT × partner Indian institute)
Required columns: `your_inst, partner_inst, shared_papers, total_citations`. Extra columns: `cites_from_partner, cites_to_partner, partner_id, partner_type, partner_cluster, cross_cluster`.

| Column | Meaning |
|---|---|
| `shared_papers` | Our papers co-authored with someone from the partner |
| `total_citations` | Total citations of those shared papers |
| `cites_from_partner` | Citation in-flow: citations from partner papers to our papers (Step 11 rule) |
| `cites_to_partner` | Citation out-flow: citations from our papers to partner papers (Step 11 rule) |
| `partner_id` | OpenAlex ID, because different institutes can share a display name |
| `partner_type` | OpenAlex institution type (education, facility, government, company, healthcare, …) |
| `partner_cluster` | IIT, NIT, IIIT, IISER / IISc, CSIR, DAE, ISRO, DRDO, ICAR, ICMR, Other government R&D, University / college, Hospital / medical, Industry or Other (`scripts/clusters.py`: from the name, the OpenAlex type and the parent organisation) |
| `cross_cluster` | `True` when the partner is not an NIT: a cross-cluster link |

- The other NIT counts as a partner. For example, NIT Surathkal is one of NIT Trichy's partners.
- 937 rows have co-authored papers; the rest are linked only by citations.

**Top partners by shared papers:**

| NIT Trichy | | NIT Surathkal | |
|---|---|---|---|
| VIT University | 216 | Manipal Academy of Higher Education | 461 |
| SRM Institute of Science & Technology | 155 | VIT University | 158 |
| IIT Madras | 119 | IISc Bangalore | 126 |
| Bharathidasan University | 109 | Nitte University | 114 |
| Anna University | 108 | Siddaganga Institute of Technology | 100 |

### Files for visualisation (Gephi)
- `data/network_metrics/citation_internal.gexf`: internal citation network
- `data/network_metrics/authorship_nit.gexf`: faculty co-authorship network, with names and community labels
- `data/network_metrics/network_summary.json`: all the counts above in one file

Open either `.gexf` file in Gephi with File → Open.

`python build_networks.py --max-authors N --authorship-only --out <folder>` rebuilds only the authorship network with another large-paper cut-off (0 = no cut-off). The bias check uses it.

---

## How we checked for mistakes (`scripts/verify_networks.py`)
A separate script recomputes the results **by a different route**, mostly from `group12_data.csv` and the raw files, and compares. All **44 checks pass**. They include:

**Scope**
- Every row is a regular science / engineering faculty member, affiliated with that NIT on that paper.
- No paper from an excluded field, and no duplicate (paper, institution, faculty) rows.

**Co-authorship rule**
- `cites_indian_inst` and `cited_by_indian_inst` are recomputed **for every row** straight from the raw link files, with an independent copy of the rule (0 rows differ).
- `out_indian` / `in_indian` edges give credit to an outside institute; `*_shared_inst` edges give none.
- **The IIT Madras case, checked directly:** 164 NIT Trichy citations of NIT Trichy + IIT Madras papers give no credit to IIT Madras, while the 1,825 genuine NIT Trichy → IIT Madras citations are counted.

**Citation network**
- Internal edges exactly equal the set of "our paper → our paper" references (23,822 = 23,822).
- Every outgoing edge's target really is in its source paper's reference list.
- `year` and DOIs match the dataset.
- PageRank sums to 1, and in-degree matches the edge list.

**Authorship network**
- Number of pairs per paper = C(k,2) − C(outside co-authors,2), for every paper. A faculty member listed with both NITs on one paper counts once.
- No self-pairs and no duplicates. Every pair contains a faculty member, and every NIT node is a faculty member.
- Degree centrality = degree / (n − 1) for every person.

**Indian connections**
- `shared_papers` and `total_citations` match the `coauthor_institutes` column of the dataset.
- `cites_from_partner` and `cites_to_partner` match a fresh edge-by-edge recount for every row.

Run it with `python verify_networks.py`. The last line prints `ALL CHECKS PASSED`.

---

## Analyses (`scripts/analysis.py` → `data/analysis/`)
Every table is saved as CSV, and [ANALYSIS.md](data/analysis/ANALYSIS.md) collects them with short explanations. All statistics stay within our two NITs; partner institutes appear only through connection data.

### 1. Papers with more than 50 authors: is there a big bias?
- **Before** the faculty and subject filters, there were 3 such papers. The ChatGPT opinion paper (73 authors, 4,455 citations) alone held **2.4% of NIT Trichy's citations** and was the most-cited paper of the whole dataset. That is a real bias in the totals and in the most-cited list, and it is a Social Sciences paper.
- **Now** no paper with more than 50 authors is left.
  - Faculty rankings, institute totals and the co-authorship network are **identical** with cut-offs of 20, 30, 50, 100 or none (rank correlation 1.000).
  - With fractional counting (each author gets 1/n of a paper) the correlation is 0.98.
- **Verdict:** no meaningful bias any more. The 50-author rule is kept as standard practice.

### 2. Which institute performs better?

| | NIT Trichy | NIT Surathkal |
|---|---|---|
| Papers | 9,184 | 9,206 |
| Faculty with papers | 357 | 306 |
| Papers per faculty member | 25.7 | 30.1 |
| Citations per paper | 15.2 | 13.6 |
| Mean FWCI | 1.31 | 1.39 |
| Share in the world's top 10% cited | 13.6% | 14.3% |
| Q1 share of ranked journal papers | 35.2% | 38.3% |
| Median faculty h-index (2016–2026) | 7 | 8 |
| Papers with a foreign co-author | 17.1% | 14.4% |

Per faculty member (Mann–Whitney test):
- NIT Surathkal faculty publish more (median 31 vs 19 papers), get more citations and have a higher h-index. All three differences are **significant**.
- The FWCI difference is **not** significant (p = 0.16).

In short: similar quality, higher output per person at NIT Surathkal, and more citations per paper at NIT Trichy.

### 2b. Measures asked for in class

| | NIT Trichy | NIT Surathkal |
|---|---|---|
| Total publications | 9,184 | 9,206 |
| Q1 papers | 2,391 | 2,222 |
| Papers in journals with IF > 5 | 2,413 (33.0% of journal papers) | 2,124 (33.8%) |
| Papers in journals with IF > 10 | 352 (4.8%) | 280 (4.5%) |
| Impact ratio = citations received ÷ citations made | 0.44 | 0.40 |
| Indian impact ratio (from / to other Indian institutes) | 0.86 | 0.82 |

- IF is the journal's 2-year mean citedness (Step 9).
- The same counts per branch, and the impact ratio by year, are in ANALYSIS.md.

### 3. Which branch performs better?
Ranked by mean FWCI, so branches with different citation habits can be compared:
- **Top:** NIT Surathkal Civil (1.92), NIT Surathkal Mechanical (1.67), NIT Trichy Computer Applications and Civil (1.66).
- **Weakest regular-size branches:** NIT Surathkal Mathematics (0.60), NIT Trichy EEE (0.97), Architecture (0.99) and CSE (1.00).

Head to head:

| Branch | NIT Trichy FWCI | NIT Surathkal FWCI | Stronger |
|---|---|---|---|
| CSE | 1.00 | 1.54 | NIT Surathkal |
| Civil | 1.66 | 1.92 | NIT Surathkal |
| Mechanical | 1.42 | 1.67 | NIT Surathkal |
| EEE | 0.97 | 1.22 | NIT Surathkal |
| Chemistry | 1.34 | 1.53 | NIT Surathkal |
| Physics | 1.04 | 1.05 | about equal |
| Mathematics | 1.47 | 0.60 | NIT Trichy |
| Chemical | 1.59 | 1.26 | NIT Trichy |
| ECE | 1.18 | 1.00 | NIT Trichy |
| MME | 1.13 | 1.01 | NIT Trichy |

### 4. Collaborate with whom, and what to improve
- **Between our two NITs:** only **47 papers** have faculty from both. The head-to-head table shows where each can learn from the other:
  - NIT Trichy from NIT Surathkal in CSE, Civil and Mechanical;
  - NIT Surathkal from NIT Trichy in Mathematics and Chemical.
- **Current partners:** for each partner, the tables give joint papers and whether those joint papers have higher impact than the NIT's other papers.
- **Partners worth approaching:** institutes with similar research topics (weighted Jaccard similarity of subfields) and heavy citation exchange, but at most 5 joint papers.
  - NIT Trichy: NSUT Delhi, GLA University, New Horizon College of Engineering, Savitribai Phule Pune University, SLIET Longowal.
  - NIT Surathkal: SLIET Longowal, Chitkara University, Sri Sairam Engineering College, IIITDM Jabalpur, NIT Kurukshetra.
- **Areas to improve:** the weakest branches on FWCI, Q1 share and foreign collaboration. For example, NIT Trichy CSE has almost no foreign co-authors.

### 5. Task 3: Indian connectivity
Everything follows the co-authorship rule (Step 11). Tables are `data/analysis/task3_*.csv`; charts are `task3_citation_flow_by_year.png` and `task3_partner_clusters.png`.

**Citation flow** with other Indian institutes, 2016–2026:

| | NIT Trichy | NIT Surathkal |
|---|---|---|
| Citations received (in-flow) | 36,970 | 30,349 |
| Citations given (out-flow) | 43,057 | 37,191 |
| Impact ratio (received / given) | 0.86 | 0.82 |

- **By year**, both NITs gave more than they received until 2022. Since 2023 they receive more than they give (ratio 1.1–1.35). Part of the early gap is timing: new papers need a few years to collect citations.
- **Top 10 citing institutes:**
  - NIT Trichy: VIT, Saveetha University, SRM, Anna University, Chandigarh University, …, IIT Roorkee and IIT Delhi.
  - NIT Surathkal: VIT, SRM, Manipal, Saveetha, VTU, …, IISc and IIT Roorkee.
- **Top 10 most-cited papers citing each NIT** come from other Indian institutes. Example topics: a review of microneedles (1,264 citations, NIT Trichy) and a review of heavy-metal pollution (1,611, NIT Surathkal). Retracted papers are left out.

**Connectivity map:**
- NIT Trichy faculty co-authored with **464** Indian institutes and NIT Surathkal faculty with **471**.
- Every partner has a **cluster**, and links to non-NIT clusters are flagged `cross_cluster = True`. Co-authored papers by partner cluster (a paper counts once per partner on it):

  | | IIT | NIT | CSIR | IISER / IISc | DAE | ISRO | DRDO | Industry | Universities / colleges |
  |---|---|---|---|---|---|---|---|---|---|
  | NIT Trichy | 411 | 323 | 180 | 71 | 114 | 145 | 128 | 181 | 2,492 |
  | NIT Surathkal | 583 | 277 | 172 | 149 | 69 | 63 | 69 | 77 | 2,347 |

- NIT Surathkal works more with IITs and IISc. NIT Trichy works more with the strategic labs (DAE, ISRO, DRDO) and with industry, for example BHEL with 94 joint papers.

**Research-topic similarity:**
- **Jaccard** similarity of research subfields with the 129 main partners, in two forms: top-40 subfield sets, and weighted by each subfield's share of papers.
- The most similar partners and the "partners worth approaching" are listed in section 4.

**Hub authors:** the faculty who connect their NIT with the most Indian institutes, with their betweenness:
- NIT Trichy: S. Anandan (Chemistry, 42 institutes), R. Karvembu (Chemistry, 41), S. Suresh (Mechanical, 37).
- NIT Surathkal: M. R. Ramesh (Mechanical, 53), Shashi Bhushan Arya (MME, 37), Mohammad Rizwanur Rahman (MME, 36).

---

## Folder layout

```
DPCN_assignment2/
├── README.md                ← this file
├── assignment.md            ← what the assignment asks for
├── scripts/
│   ├── fetch_works.py       ← Step 2: papers
│   ├── fetch_authors.py     ← Step 3: author h-index
│   ├── fetch_links.py       ← Step 6: Indian citation links (resumable)
│   ├── fetch_faculty.py     ← Step 7: faculty pages, current + one archived copy per year (resumable)
│   ├── build_roster.py      ← Step 7: faculty roster from those pages
│   ├── names.py             ← name, branch and designation helpers
│   ├── match_faculty.py     ← Step 8: roster ↔ OpenAlex author IDs
│   ├── fetch_impact.py      ← Step 9: FWCI, h-index, journal impact, ORCIDs, partner topics and types, citing papers
│   ├── build_dataset.py     ← Steps 4, 5, 10: quartiles, CORE ranks, group12_data.csv, faculty.csv
│   ├── flow.py              ← Step 11: the one citation-flow rule
│   ├── clusters.py          ← Task 3: which cluster a partner institute belongs to (IIT, CSIR, DAE, …)
│   ├── build_networks.py    ← Task 2: three network CSVs + metrics
│   ├── verify_networks.py   ← 44 independent checks
│   └── analysis.py          ← analyses → data/analysis/
└── data/
    ├── README.md            ← short data dictionary
    ├── group12_data.csv     ← MAIN SUBMISSION FILE
    ├── citation_network.csv     ← Task 2 submission
    ├── authorship_network.csv   ← Task 2 submission
    ├── indian_connections.csv   ← Task 2 submission
    ├── faculty.csv          ← faculty list with h-index
    ├── network_metrics/     ← PageRank, centralities, communities, Gephi files, summary
    ├── analysis/            ← ANALYSIS.md, comparison tables, large-paper sensitivity runs
    ├── raw/                 ← raw downloads
    │   ├── NIT_Trichy_works.jsonl, NIT_Surathkal_works.jsonl
    │   ├── authors.jsonl, authors_extra.jsonl, author_ids.jsonl
    │   ├── links_refs.jsonl, links_citers.jsonl   (+ .done progress files)
    │   ├── works_impact.jsonl, sources.jsonl, partner_subfields.jsonl
    │   ├── institutions.jsonl, citers_info.jsonl
    │   └── faculty_pages/   ← saved faculty pages + manifest.csv
    └── reference/
        ├── scimago_all.csv  ← SJR data (mirror)
        ├── core_conf.csv    ← ICORE2026 conference ranks
        ├── faculty_roster.csv, research_scholars.csv
        ├── faculty_openalex_map.csv, faculty_match_review.csv, faculty_match_overrides.csv
        └── unmatched_prolific_authors.csv
```

## How to re-run everything

You only need this to refresh the data, for example for newer citation counts. Run it in PowerShell from the `scripts/` folder:

```powershell
$env:OPENALEX_API_KEY = "your-key"   # free key from openalex.org (Settings -> API); never put it in a file
python fetch_works.py               # papers (about 115 requests)
python fetch_authors.py             # h-index (about 34 requests)
python fetch_links.py               # Indian citation links (about 1,600 requests, resumable)
python fetch_faculty.py             # faculty pages, current + archived (about 500 pages, slow, resumable)
python build_roster.py              # faculty roster
python fetch_impact.py authorids    # ORCIDs of NIT authors (used for matching)
python match_faculty.py             # roster -> OpenAlex IDs; check faculty_match_review.csv
python fetch_impact.py works        # FWCI and top-10% flags
python fetch_impact.py authors      # h-index of the remaining faculty IDs
python fetch_impact.py sources      # journal impact (IF > 5 / IF > 10)
python build_dataset.py             # group12_data.csv and faculty.csv
python build_networks.py            # Task 2 files (under a minute)
python verify_networks.py           # should end with ALL CHECKS PASSED
python fetch_impact.py institutions # partner types and parents (uses indian_connections.csv)
python fetch_impact.py citers       # details of the papers that cite us (uses citation_network.csv)
python build_networks.py            # again, so indian_connections.csv gets the cluster columns
python fetch_impact.py partners     # partner research topics (uses indian_connections.csv)
python analysis.py                  # data/analysis/
```

- Each download step skips anything already saved in `data/raw/`. To download fresh data, delete those files first.
- If `match_faculty.py` lists new uncertain links, a team member adds their decisions to `faculty_match_overrides.csv` and re-runs it.
- It needs Python 3 with `requests`, `pandas`, `networkx` and `scipy`.

---

## Known limitations (mention these in the report)

1. **Faculty coverage.**
   - 177 of the 878 regular faculty have no OpenAlex link, mostly new or low-output faculty.
   - A few faculty appear on no page we could download (see `unmatched_prolific_authors.csv`).
   - The archived pages are yearly, so join and leave years are approximate.
   - A faculty member's papers from before they joined (for example their PhD at the same NIT) count if they carry the NIT affiliation.
2. **Name matching.**
   - About 95% accurate on a random sample of 50 automatic links; the 59 uncertain links were checked by hand.
   - Scopus IDs could not be used, because OpenAlex no longer stores them and the Scopus API needs a key.
3. **Approximate quartiles.** They're computed from 27 broad SCImago subject areas, not SCImago's roughly 300 official categories (Step 4).
4. **IF is not the JCR impact factor.** It is OpenAlex's 2-year mean citedness: the same formula, on OpenAlex's citation data.
5. **CORE covers mainly computing conferences.** Most engineering conferences at our NITs are unranked, so this column is mostly blank for conferences.
6. **OpenAlex coverage.** A few papers may be missing or have wrong affiliations; 595 of our papers have no venue name and 68 no DOI.
7. **Snapshot dates.** Citation counts are as of **7 October 2026**; FWCI and journal impact are as of **19 October 2026**.

---

## What to do next

1. **Task 4:** statistics report (at most 10 slides or 5 pages), using the tables and charts in `data/analysis/`.
2. **Task 5:** interactive dashboard with all required panels, including the citation and co-authorship network graphs.
