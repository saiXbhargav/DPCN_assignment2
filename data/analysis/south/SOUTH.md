# The six South Indian NITs (18 Nov 2026)

This file asks two questions:
1. Do the other South Indian NITs give results like Trichy and Surathkal?
2. Does hiring change the network, for example when an NIT is new and recruits many faculty at once?

This file compares all six South Indian NITs:

| NIT | Founded | Data |
|---|---|---|
| Warangal | 1959 (first REC) | our OpenAlex download + NIRF 2025; Group 13's data as a cross-check |
| Surathkal | 1960 | ours |
| Calicut | 1961 | our OpenAlex download + NIRF 2025; Group 14's data as a cross-check |
| Trichy | 1964 | ours |
| Puducherry | 2010 | our OpenAlex download + NIRF 2025 (no team did it) |
| Andhra Pradesh | 2015 (its website) | our OpenAlex download + NIRF 2025 (no team did it) |

**Founding years:**
- The four old NITs started as Regional Engineering Colleges and became NITs in 2002–03.
- NIT Andhra Pradesh's founding year is from its own website. The other five years are from general knowledge.
- NIT Goa is on the west coast, so it is not included.

**How the data was built** (all six built the same way, from `scripts/south_nits.py`):
- **Papers:** OpenAlex, with the same filter for all six (articles, reviews and conference papers, 2016–2026).
- **Faculty:** each NIT's own NIRF 2025 data file, which gives rank and joining date. Faculty are matched to OpenAlex authors by name, as on 17 Nov.
- **The faculty network:** built exactly like the one behind our 1.65. It uses faculty only and papers with up to 50 authors, and adds up year by year from 2016.

How we checked the other teams' files is in CHECKS.md.

## 1. Output and people

| | Trichy | Surathkal | Warangal | Calicut | Puducherry | Andhra Pradesh |
|---|---|---|---|---|---|---|
| Papers 2016–2025 | 10,654 | 9,996 | 9,230 | 7,093 | 1,611 | 1,565 |
| Papers in 2025 | 1,208 | 1,151 | **1,390** | 1,006 | 378 | 363 |
| Faculty (NIRF 2025, current) | 348 | 279 | 327 | 375 | 76 | 139 |
| …of them regular (not ad hoc or contract) | 345 | 279 | 309 | 370 | 64 | **43** |
| Assistant Professors | 47% | 30% | 35% | 65% | 70% | **98%** |
| Median joining year | 2008 | 2012 | 2013 | 2018 | 2021 | 2022 |
| Hired 2021–2025 (share of today's faculty) | 21% | 9% | 13% | 35% | 62% | 68% |
| Papers in 2024 per faculty member | 3.4 | **4.7** | 4.2 | 2.4 | 4.4 | 2.0 |
| Faculty papers in 2024 per faculty member | 2.4 | **3.7** | 2.9 | 1.9 | 3.3 | 1.5 |
| Median FWCI 2016–2025 | 0.70 | 0.69 | 0.69 | 0.60 | **0.77** | 0.71 |
| Q1 share of journal papers (our quartile rule) | 36% | 38% | 37% | 44% | 41% | 41% |
| Faculty matched to OpenAlex | 86% | 91% | 83% | 86% | 86% | **51%** |

- **The two young NITs are small but growing fast.** Puducherry went from 35 papers in 2016 to 378 in 2025, and Andhra Pradesh from 19 to 363. Their median impact is as high as the old NITs': Puducherry has the highest median FWCI of the six.
- **Andhra Pradesh is almost all young staff.** It has 139 faculty, 98% of them Assistant Professors, and 96 of the 139 are ad hoc or on contract. Many contract teachers have no papers, so only 51% of its faculty could be found in OpenAlex.
- **Papers per head mostly follows the rank mix again,** as on 17 Nov. Surathkal is the most senior and the most productive. Counting all current staff, Calicut (2.4) and Andhra Pradesh (2.0) are lowest. Counting regular faculty only, Andhra Pradesh is the highest (6.6), because 96 of its 139 staff are ad hoc or on contract.
- **Puducherry is the exception.** 70% of its faculty are Assistant Professors, yet it has 4.4 papers per head. It is the smallest NIT (76 faculty), so a few very active groups count for a lot.
- **The Q1 shares need care.** For the four other NITs, quartiles are known for only 50–63% of journal papers, because we only have quartiles for journals our own two NITs also used. Group 13's and Group 14's own quartiles give almost the same Q1 shares: 38.6% for Warangal and 44.0% for Calicut.

## 2. Average degree over the years (connected faculty and the "pure number" of faculty)

| Co-authors per faculty member in 2025 | Trichy | Surathkal | Warangal | Calicut | Puducherry | Andhra Pradesh |
|---|---|---|---|---|---|---|
| per **connected** faculty member (at least one faculty co-author) | 2.53 | 3.28 | 2.89 | 2.65 | 2.00 | 1.91 |
| per faculty member **in post** (pure N: everyone on the NIRF list who had joined by then) | 1.43 | 2.37 | 1.63 | 1.43 | 0.97 | 0.59 |
| in that **single year** only | 1.53 | 1.62 | 1.61 | 1.50 | 1.24 | 1.76 |

- **Both versions rise from 2016 to 2025 at every NIT**, with small dips in some hiring years (`s_by_year.csv`, figure `s_six_nits.png`).
- **Within a single year, a faculty member writes with about 1.2–1.8 faculty colleagues at all six NITs.** This number is flat since 2016. The averages grow only because old links stay while new ones are added. This is the same explanation as for our 1.65 (PROF.md §1), now seen at six NITs.

## 3. The densification exponent a (links ∝ N^a)

| a | Trichy | Surathkal | Warangal | Calicut | Puducherry | Andhra Pradesh |
|---|---|---|---|---|---|---|
| N = connected faculty, 2016–2026 | 1.41 | **1.74** | 1.44 | 1.39 | 1.31 | 1.19 |
| N = connected faculty, 2019–2025 | 1.30 | **1.64** | 1.58 | 1.42 | 1.26 | 1.17 |
| N = faculty in post (pure N), 2016–2026 | 2.24 | 4.99 | 3.37 | 2.03 | 1.68 | 2.25 |
| N = all authors incl. students, 2016–2026 | 1.18 | 1.19 | 1.24 | 1.22 | 1.25 | 0.99 |

- **Every NIT's faculty network densifies (a > 1).** The values run from 1.19 to 1.74, so our 1.65 for Trichy and Surathkal together is normal.
- **Real growing networks densify in the same range.** Leskovec, Kleinberg & Faloutsos (2005, KDD, https://doi.org/10.1145/1081870.1081893) found exponents of 1.56 and 1.68 (arXiv citation graphs), 1.66 (US patents), 1.18 (internet routers) and 1.08–1.15 (author–paper graphs). All six NITs lie inside this 1.08–1.68 range, except Surathkal, which is just above it (1.74).
- **With N = faculty in post, a becomes very large and unstable** (up to 5–7 in the shorter window). The headcount hardly changes while links keep growing. That simply says links grow much faster than people, not that a clean law holds. Also, the NIRF list misses people who left, so the early headcounts are too low.
- **With students included, a falls to about 1.0–1.25 everywhere,** as on 17 Nov. Densifying at 1.4–1.7 is a property of the closed faculty group.

## 4. Founding years and hiring: does hiring lower the exponent?

**Across the six NITs, yes; inside a NIT, not clearly.** The more of an NIT's faculty were hired recently, the lower its exponent, but this rests on six NITs and is fragile (see the caveats and §6):

| Across the six NITs (Spearman, exact p from all 720 orderings) | ρ | p |
|---|---|---|
| Hired 2021–2025 vs a (2016–2026) | −1.00 | 0.003 |
| Hired 2021–2025 vs a (2019–2025) | −0.94 | 0.017 |
| Founding year vs a (2019–2025) | −0.94 | 0.017 |
| Share of Assistant Professors vs a (2016–2026) | −1.00 | 0.003 |
| 4-year windows pooled over the six NITs: more hiring vs that window's a (39 overlapping windows) | −0.53 | 0.0006 (optimistic) |
| The same windows after removing each NIT's own average (the within-NIT part) | −0.17 | 0.29 |

- **The order is exact.** Surathkal hired the least recently (9%) and has the highest a. Andhra Pradesh hired the most (68%) and has the lowest. The two young NITs, Puducherry and Andhra Pradesh, are the bottom two.
- **Inside each NIT the link is not consistent.** The pooled ρ = −0.53 comes from differences between NITs. Within single NITs the window correlation is negative at Warangal (−0.89) and Puducherry (−0.71) but positive at Trichy (+0.69) and Calicut (+0.75). After removing each NIT's average it is −0.17 (p = 0.29). So we do not claim that hiring waves lower the exponent within a NIT.
- **A likely reason (not tested):** N counts only faculty with at least one faculty co-author, so newly connected faculty arrive with only one or two links each and add people about as fast as links.
- **Hires come in waves.** There were almost no hires in 2016–2017 (2 people, both at Surathkal). Big rounds came in 2018 (Warangal, Calicut, Trichy) and 2022–2023 (Calicut 69 and 58, Andhra Pradesh 53). Andhra Pradesh's first regular faculty on the list joined in 2018.

**Caveats:**
- **We can't separate the reasons.** With six NITs, "hired recently", "young NIT" and "many Assistant Professors" go together.
- **The windowed test is optimistic.** The 39 windows overlap, so they are not independent and its p-value is too small.
- **Early hires are missing.** The NIRF list shows only today's staff, so people who joined early and then left are not counted.

## 5. Citing your own papers

Between two papers of the same NIT, **85–92% of citations share at least one author** at every NIT (`fetch_peers.py refs`):

| | Trichy | Surathkal | Warangal | Calicut | Puducherry | Andhra Pradesh |
|---|---|---|---|---|---|---|
| Share of own-NIT citations that share an author | 85.3% | 89.3% | 86.6% | 87.4% | 91.6% | 92.0% |
| Own-NIT papers among all references | 3.3% | 4.0% | 3.5% | 2.5% | 3.5% | 2.6% |

- **This matches our 86% for Trichy and Surathkal** (PAPERS.md part S). So "the internal citation network is mostly self-citation" is true of every NIT, not a quirk of ours.
- **The young NITs are slightly higher,** since they have fewer groups to cite.

## 6. Second source: the other teams' cleaned data (Warangal, Calicut)

- **Warangal:** using Group 13's cleaned data instead of our download, a = 1.30 instead of 1.44 (2016–2026).
- **Calicut:** using Group 14's cleaned data, a = 1.31 instead of 1.39.
- **Paper counts:** Warangal's 2024 count is about the same (1,362 vs 1,380). Calicut's is lower (781 vs 916), because Group 14's file misses many conference papers (CHECKS.md).
- **Paper counts and "every NIT densifies" do not change. The hiring result does weaken:** with Group 13's and Group 14's values for Warangal (1.30) and Calicut (1.31), the rank correlation between recent hiring and a falls from −1.00 (p = 0.003) to −0.60 (exact p = 0.24).

## Files (in this folder)

| File | What |
|---|---|
| `s_six_nits.csv` | One row per NIT: everything in §1–§5 |
| `s_by_year.csv` | NIT × year: papers, faculty network (connected and pure N), single-year co-authors, hires, all-author network |
| `s_densification.csv` | a and R² per NIT, for three N's and two windows |
| `s_rolling_exponent.csv` | 4-year windows: a and the share of faculty hired in the window |
| `s_friends_vs_ours.csv` | §6 |
| `south_summary.json` | All of the above in one file for the dashboard |
| `s_six_nits.png` | The figure |
| `CHECKS.md`, `k_*`, `friends_*` | The checks of Group 13's and Group 14's data and the cleaned tables (`friends_*.csv` stay on the laptop only, git-ignored) |

New downloads:
- the OpenAlex works of NIT Puducherry (`I4400573194`) and NIT Andhra Pradesh (`I4210153924`);
- the own-NIT references of all six NITs;
- the two NITs' NIRF 2025 files from their own websites (nitpy.ac.in, nitandhra.ac.in) into `data/raw/nirf/`, which is git-ignored because the files list age and gender.
