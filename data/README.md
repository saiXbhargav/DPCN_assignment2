# Team 12: Task 1 data (NIT Trichy and NIT Surathkal, 2016–2026)

## Files

| File | What it contains |
|---|---|
| `group12_data.csv` | **The submission file.** One row per (paper, NIT author) pair. It has all 14 required columns plus some extra columns. |
| `citation_network.csv` | **Task 2.** Directed citation edges: internal, out to other Indian institutes, and in from them |
| `authorship_network.csv` | **Task 2.** Co-author pairs on our papers (at least one NIT author) |
| `indian_connections.csv` | **Task 2.** Our NIT × partner Indian institute: shared papers, citations, in-flow and out-flow |
| `network_metrics/` | PageRank and in-degree per paper; degree, betweenness and Louvain community per author; Gephi `.gexf` files; `network_summary.json` |
| `faculty.csv` | One row per NIT author: department, papers from 2016 to 2026, citations, and h-index |
| `raw/*_works.jsonl` | Raw OpenAlex records for every paper, kept so later tasks never have to download them again |
| `raw/authors.jsonl` | OpenAlex author profiles (with h-index) for authors with 3 or more papers |
| `raw/links_refs.jsonl` | Papers by Indian institutes that **our papers cite** (used later for the citation network) |
| `raw/links_citers.jsonl` | Papers by Indian institutes that **cite our papers** (used later for citation in-flow) |
| `reference/scimago_all.csv` | SCImago SJR scores for each journal and year, used to work out quartiles |
| `reference/core_conf.csv` | ICORE2026 conference ranks |

## How the data was collected

- **Source:** the OpenAlex API, using the institution IDs below:
  - NIT Trichy: `I122964287` (ror.org/047x65e68)
  - NIT Surathkal: `I11880225` (ror.org/01hz4v948)
- **Included:** OpenAlex types `article`, `review` and `conference-paper`, published 2016 to 2026.
- **Excluded:** book chapters, preprints, errata, datasets and similar items.
- **Paper counts:** 11,678 for NIT Trichy and 10,807 for NIT Surathkal. Of these, 69 papers involve both NITs and appear under each.
- **Unique papers:** 22,416.

## How each column was filled

| Column | How it was filled |
|---|---|
| `author` | Every author whose affiliation on that paper is the NIT. OpenAlex can't tell faculty from PhD students. Use `faculty.csv`, for example authors with 5 or more papers, to approximate the faculty. |
| `type` | `conference` if OpenAlex lists it as a conference paper or its venue is a conference; otherwise `journal` |
| `quartile` (journals) | SCImago SJR rank within the journal's subject area for the paper's year (the nearest year for 2026). Q1 is the top 25%. Each journal gets its best quartile across its subject areas. It's an approximation because SCImago's own quartiles use finer categories. |
| `quartile` (conferences) | Taken from ICORE2026 when the venue title closely matches a ranked conference. Regional editions and workshops aren't ranked. Most Indian IEEE conferences are unranked, so this column is blank for them. |
| `coauthor_institutes` | Indian institutions, other than our two NITs, on the paper's author list |
| `cites_indian_inst` | `True` if at least one reference has an author from another Indian institution |
| `cited_by_indian_inst` | `True` if at least one citing paper has an author from another Indian institution |
| `citations` | OpenAlex `cited_by_count` on 7 Oct 2026 |

**Extra columns:**
- `author_id`
- `department`: parsed from the raw affiliation text; about 83% of rows have it
- `openalex_id`
- `field` and `domain`: the OpenAlex primary topic
- `n_authors`
- `both_nits`

## Re-running the collection

Run these from the `scripts/` folder:

```
python fetch_works.py      # papers (about 115 API requests)
python fetch_authors.py    # h-index (about 34 requests)
python fetch_links.py      # Indian citation links (about 1,600 requests, resumable)
python build_dataset.py    # rebuilds group12_data.csv and faculty.csv
```

Without an API key, OpenAlex allows about 1,000 requests per day. `fetch_links.py` saves progress after each batch, so if it stops at the limit, run it again the next day. Alternatively, get a free API key at openalex.org and run `set OPENALEX_API_KEY=...` first.

All link batches are now downloaded, so both `cites_indian_inst` and `cited_by_indian_inst` are filled for every paper. If `fetch_links.py` is ever re-run and stops partway, those two columns stay blank for papers that haven't been processed until it finishes and `build_dataset.py` is run again.
