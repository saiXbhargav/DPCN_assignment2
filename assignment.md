# DPCN Research Mapping Project: Team 12

**Instructor:** Chittaranjan Hens
**Cluster:** Top NITs
**Our institutions:**
- **NIT Trichy** (Tiruchirappalli, Tamil Nadu)
- **NIT Surathkal** (NITK, Karnataka)

**Period covered:** publications from 2016 to 2026

> **Rules**
> - We work independently. Don't share data with other groups.
> - If we want to collaborate with another group, we must tell the instructor first.
> - All analysis stays within NIT Trichy and NIT Surathkal. Links to other institutes appear only in the raw data files.

---

## Deadlines

| When | What we submit |
|---|---|
| **Week 1–2** | `group12_data.csv`, `citation_network.csv`, `authorship_network.csv`, `indian_connections.csv` |
| **Week 3** | Statistics report (at most 10 slides or 5 pages) and the interactive dashboard |

---

## Task 1: Data collection (Week 1–2)

Collect every faculty publication from 2016 to 2026 for both NITs.

**Sources**
- **OpenAlex:** the main source. Query by the institution's ROR ID rather than its name.
- **IRINS** and **Scopus:** for cross-checking coverage, citations and quartiles.
- **Scimago or JCR:** journal quartiles (Q1 to Q4).
- **CORE portal:** conference ranks (A*, A, B, C).

**Output file:** `group12_data.csv`

| Column | What goes in it |
|---|---|
| `group` | `12` |
| `institution` | `NIT Trichy` or `NIT Surathkal` |
| `author` | Faculty member's full name |
| `title` | Paper title |
| `year` | Publication year (2016 to 2026) |
| `type` | `journal` or `conference` |
| `journal_name` | Journal or conference name |
| `issn` | ISSN (journals only) |
| `doi` | DOI URL |
| `citations` | Citation count on the date we collect the data |
| `quartile` | Q1 to Q4, or CORE A*/A/B/C |
| `coauthor_institutes` | Co-authors' institutions, separated by semicolons |
| `cites_indian_inst` | `TRUE` if the paper cites a paper from another Indian institute |
| `cited_by_indian_inst` | `TRUE` if a paper from another Indian institute cites this one |

---

## Task 2: Network files (Week 1–2)

### 2a. Citation network: `citation_network.csv`
A **directed** network: each node is a paper, and each edge means "paper A cites paper B".
- **Columns:** `source_doi, target_doi, source_inst, target_inst, year`
- Get the citation pairs from OpenAlex's `referenced_works` field, or from Scopus.
- Compute **in-degree** for each paper (how many papers in our own data cite it).
- Compute **PageRank** to find the most influential papers.
- Map how citations flow in and out of our two NITs from other Indian institutes.
- Mark citations that cross institutes using the `cites_indian_inst` column in the main CSV.

### 2b. Authorship network: `authorship_network.csv`
An **undirected** network: each node is an author, and each edge means "these two authors wrote a paper together".
- **Columns:** `author_a, author_b, paper_doi, inst_a, inst_b, year`
- Take every pair of co-authors from every paper.
- Compute **degree centrality** to find the faculty who collaborate the most.
- Compute **betweenness centrality** to find the faculty who connect groups that would otherwise be separate.
- Run **Louvain** or **Leiden** community detection to find collaboration clusters.
- Mark edges where the two authors are at different institutions.

### 2c. Indian connections: `indian_connections.csv`
- **Columns:** `your_inst, partner_inst, shared_papers, total_citations`
- One row for each partner institute, with totals summed across papers.

---

## Task 3: Indian connectivity analysis (feeds Tasks 4 and 5)

**Citation flow**
- Count citations our institutes **receive** from other Indian institutes (in-flow).
- Count citations our institutes **give** to other Indian institutes (out-flow).
- List the top 10 Indian institutes that cite our work.
- Compute the **citation impact ratio** (in-flow ÷ out-flow) for each institute.
- Make a chart of citation flow by year, 2016 to 2026.

**Connectivity map**
- List every Indian institute our faculty have co-authored with.
- Rank partner institutes by the number of shared papers.
- Mark links to a different type of institute, for example NIT with IIT, CSIR or IISER.
- Compute the **Jaccard similarity** of research topics between our institutes and each partner.
- Identify "hub" authors who connect several institutes.

---

## Task 4: Statistics report (Week 3)

The report is **at most 10 slides or 5 pages**. It covers faculty, departments and both institutions, and must include:

- [ ] Publication trend from 2016 to 2026: the total and the count for each year
- [ ] Share of papers in Q1 journals, for each institution
- [ ] Distribution of faculty h-index values
- [ ] Top 5 journals for each institution
- [ ] Top 10 most-cited papers
- [ ] Breakdown by research area
- [ ] **Citation network summary:** top 10 papers by PageRank, the in-degree distribution, and citation flow between institutes
- [ ] **Authorship network summary:** degree and betweenness centrality, and the communities found

---

## Task 5: Interactive dashboard (Week 3)

The dashboard needs these panels for **each institution**:

- [ ] **Publication trend:** line or bar chart of papers per year, 2016 to 2026
- [ ] **Faculty list:** name, department, h-index and total papers
- [ ] **Journal quartiles:** stacked bar or pie chart of the Q1, Q2, Q3 and Q4 shares
- [ ] **Faculty performance table:** sortable by papers, citations, top journal and h-index
- [ ] **Top journals:** the 5 journals with the most papers
- [ ] **h-index distribution:** histogram of faculty h-index values
- [ ] **Research areas:** share of publications in each field
- [ ] **Most-cited papers:** top 10, showing title, journal, year, citations and DOI
- [ ] **Conference ranks:** breakdown by CORE A*, A, B and C
- [ ] **Citation network:** interactive directed graph
- [ ] **Authorship network:** interactive co-authorship graph

**Suggested tools:** Python (pandas, NetworkX), Gephi, and D3.js or Cytoscape.js for the interactive graphs.

---

## Submission checklist

- [ ] `group12_data.csv` is named correctly and has all 14 columns
- [ ] It contains only papers from 2016 to 2026
- [ ] It includes both NIT Trichy and NIT Surathkal
- [ ] `citation_network.csv` is submitted
- [ ] `authorship_network.csv` is submitted
- [ ] `indian_connections.csv` is submitted
- [ ] The report is at most 10 slides or 5 pages and covers every required metric and both network summaries
- [ ] The dashboard includes both network graphs
- [ ] Everything has been submitted to the professor, and nothing has been shared with other groups

---

## Suggested work split (adjust to team size)

| Member | Responsibility |
|---|---|
| A | OpenAlex data collection for NIT Trichy, plus the faculty list |
| B | OpenAlex data collection for NIT Surathkal, plus the faculty list |
| C | Quartiles and CORE ranks, data cleaning, building `group12_data.csv` |
| D | Citation and authorship networks, plus `indian_connections.csv` |
| E | Dashboard and report |
