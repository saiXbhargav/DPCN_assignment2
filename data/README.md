# Team 12: data (NIT Trichy and NIT Surathkal, 2016–2026)

The files cover **only regular faculty of science / engineering / technology departments** and **only science / engineering papers**. The main [README](../README.md) explains how every file was made.

## Submission files

| File | What it contains |
|---|---|
| `group12_data.csv` | **The main submission file.** 21,932 rows, one per (paper, NIT faculty member), covering 18,343 papers. It has all 14 required columns plus extra columns. |
| `citation_network.csv` | **Task 2.** 181,189 directed citation edges: internal, out to other Indian institutes, in from them, and the co-authored ("shared institute") ones that are not counted as flow |
| `authorship_network.csv` | **Task 2.** 25,691 co-author pairs on our papers; every pair has at least one NIT faculty member |
| `indian_connections.csv` | **Task 2.** 4,053 rows of our NIT × partner Indian institute: shared papers, their citations, citation in-flow and out-flow, and the partner's type, cluster (IIT, CSIR, DAE, …) and `cross_cluster` flag |

## Other outputs

| File | What it contains |
|---|---|
| `faculty.csv` | One row per science / engineering faculty member (811): department, designation, current/former, OpenAlex IDs, papers and citations 2016–2026, h-index (career and 2016–2026), mean FWCI, top journal |
| `network_metrics/` | PageRank and in-degree per paper; degree, betweenness and Louvain community per faculty member; Gephi `.gexf` files; `network_summary.json` |
| `analysis/` | `ANALYSIS.md` and its tables and charts: large-paper bias check, institute and branch comparison, IF > 5 / IF > 10, impact ratio, partners, and Task 3 (`task3_*`) |

## Raw and reference files

| File | What it contains |
|---|---|
| `raw/NIT_Trichy_works.jsonl`, `raw/NIT_Surathkal_works.jsonl` | Raw OpenAlex records for every paper with an NIT author (22,416), kept so nothing has to be downloaded again |
| `raw/authors.jsonl`, `raw/authors_extra.jsonl` | OpenAlex author profiles (h-index) |
| `raw/author_ids.jsonl` | ORCID (and Scopus, if any) of NIT authors with 2+ papers |
| `raw/links_refs.jsonl` | Papers by Indian institutes that **our papers cite** |
| `raw/links_citers.jsonl` | Papers by Indian institutes that **cite our papers** |
| `raw/works_impact.jsonl` | FWCI and the top-10% flag for every paper (fetched 19 Oct 2026) |
| `raw/sources.jsonl` | Journal 2-year mean citedness, used as the impact factor (fetched 19 Oct 2026) |
| `raw/partner_subfields.jsonl` | Papers per research subfield for 129 partner institutes |
| `raw/institutions.jsonl` | Type and parent organisations of every partner institute (for the cluster flags) |
| `raw/citers_info.jsonl` | Title, year, venue and citation count of the Indian papers that cite us |
| `raw/faculty_pages/` | The institutes' faculty pages, current and one archived copy per year, with `manifest.csv` |
| `reference/scimago_all.csv` | SCImago SJR scores for each journal and year, used to work out quartiles |
| `reference/core_conf.csv` | ICORE2026 conference ranks |
| `reference/faculty_roster.csv` | Everyone listed as faculty on the institutes' pages, 2016–2026, with branch, designation and `regular` / `science_engineering` flags |
| `reference/faculty_openalex_map.csv` | Accepted links from faculty to OpenAlex author IDs |
| `reference/faculty_match_overrides.csv` | The team's accept/reject decisions on uncertain links |
| `reference/faculty_match_review.csv` | Uncertain links still waiting for a decision (currently none) |
| `reference/research_scholars.csv`, `reference/unmatched_prolific_authors.csv` | PhD scholar names, and prolific NIT authors with no faculty link (for checking) |

## How the data was collected

- **Source:** the OpenAlex API, using the institution IDs below:
  - NIT Trichy: `I122964287` (ror.org/047x65e68)
  - NIT Surathkal: `I11880225` (ror.org/01hz4v948)
- **Included:** OpenAlex types `article`, `review` and `conference-paper`, published 2016 to 2026.
- **Excluded:** book chapters, preprints, errata, datasets and similar items.
- **Faculty only:** authors are kept only if they are regular faculty on the institutes' own faculty pages, matched to their OpenAlex IDs.
- **Science / engineering only:**
  - papers in the OpenAlex fields Business/Management/Accounting, Economics, Social Sciences, Psychology and Arts & Humanities are dropped;
  - Management and Humanities faculty are left out.

## How each column was filled

| Column | How it was filled |
|---|---|
| `institution` | The faculty member's NIT on that paper |
| `author` | The faculty member's name as on the institute website |
| `type` | `conference` if OpenAlex lists it as a conference paper or its venue is a conference; otherwise `journal` |
| `quartile` (journals) | SCImago SJR rank within the journal's subject area for the paper's year (the nearest year for 2026). Q1 is the top 25%. Each journal gets its best quartile across its subject areas. This is an approximation, because SCImago's own quartiles use finer categories. |
| `quartile` (conferences) | Taken from ICORE2026 when the venue title closely matches a ranked conference. Regional editions and workshops aren't ranked. Most Indian IEEE conferences are unranked, so this column is blank for them. |
| `coauthor_institutes` | Indian institutions, other than our two NITs, on the paper's author list |
| `cites_indian_inst` | `True` if the paper cites a paper of another Indian institute. A cited paper that our NIT co-wrote (e.g. with IIT Madras) does not count (`scripts/flow.py`). |
| `cited_by_indian_inst` | `True` if a paper of another Indian institute cites it, under the same rule |
| `citations` | OpenAlex `cited_by_count` on 7 Oct 2026 |

**Extra columns:**
- `faculty_id` (roster ID; use it to count per person) and `author_id` (OpenAlex ID on that paper)
- `department`: the faculty member's branch, from the roster
- `designation`, `faculty_status`: rank, and current or former
- `openalex_id`, `author_position`: to join with the raw files
- `field`, `domain`, `subfield`: OpenAlex primary topic
- `n_authors`, `both_nits`
- `fwci`, `top10pct`: field-weighted citation impact and the top-10% flag
- `journal_if_2yr`: the journal's 2-year mean citedness (blank for conferences)

## Re-running

See "How to re-run everything" in the main [README](../README.md). The downloads need a free OpenAlex API key in the `OPENALEX_API_KEY` environment variable. Without one, OpenAlex allows only about 1,000 requests a day, shared by everyone on the same network.
