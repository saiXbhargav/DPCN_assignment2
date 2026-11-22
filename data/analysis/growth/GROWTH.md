# Network growth, link prediction and other NITs (17 Nov 2026)

Made by `scripts/phase2_growth.py`, which writes to this folder. On the dashboard, these are the last four panels of the **Phase II** tab ("Growth and other NITs"), plus a "Scholar ↗" link next to every name in the **Faculty** tab.

```
python scripts/fetch_peers.py                 # papers of four NITs from OpenAlex (data/raw/peers/)
python scripts/phase2_growth.py growth predict  # average degree and 1.65; link prediction (fixed and updated models)
python scripts/phase2_growth.py nirf nitfaculty # needs pymupdf: NIRF faculty lists, joining years, faculty-only networks
python scripts/phase2_growth.py nits scholar    # four NITs side by side; Google Scholar checklist
```

| Question | What we did | Section |
|---|---|---|
| How does the average degree change across the years? | Average co-authors per year, counted two ways, per NIT | [1](#1-average-degree-over-the-years-and-why-165) |
| Why is the exponent 1.65? | What the exponent means, and the same number at three other NITs | [1](#1-average-degree-over-the-years-and-why-165) |
| Train once on 2016–2022 and predict 2023, 2024 and 2025 without new data. How good is it, and which predictions came true? | A fixed model scored every year, with all its correct matches; an updated model kept separate for comparison | [2](#2-predict-and-check-link-prediction-with-a-fixed-model) |
| How do two more NITs compare, and how many faculty does each have? | NIT Warangal and NIT Calicut next to our two NITs, with official faculty numbers | [3](#3-four-nits-side-by-side) |
| Were many faculty hired in 2002–03, when the RECs became NITs? | The joining year of every current faculty member, from NIRF 2025 | [4](#4-when-did-todays-faculty-join) |
| Do the citation numbers match reality? Link every faculty member to Google Scholar | Scholar links on the dashboard, and a checklist for the most-cited faculty | [5](#5-google-scholar-reality-check) |

**New sources.** Both were added on 17 Nov.
- **OpenAlex:** papers of NIT Warangal (`I121750182`) and NIT Calicut (`I114845381`), plus a fresh copy of our two NITs. All four use the same filter and the same day.
- **NIRF 2025 data files:** each NIT's own copy of its "Overall" NIRF 2025 submission.
  - Trichy: [nitt.edu](https://www.nitt.edu/home/academics/nirf/1.%20NIRF%202025_IR-O-U-0467_Overall.pdf)
  - Surathkal: [nitk.ac.in](https://www.nitk.ac.in/document/attachments/8178/Overall.pdf)
  - Warangal: [nitw.ac.in](https://nitw.ac.in/api/static/files/20250627_NIRF_2025_Submitted_data_Overall_2025-7-1-15-41-37.pdf)
  - Calicut: [nitc.ac.in](https://nitc.ac.in/imgserver/uploads/attachments/overall_f0a48d77-126f-477d-84d6-fbd669ab6061_0.pdf)

  Each file lists every faculty member with designation, joining date and whether they still work there. The files also list age and gender, so they are kept out of the repo (`data/raw/nirf/` is git-ignored). Only counts are saved, in `data/reference/nirf_2025_faculty_counts.csv` and `nirf_2025_joining_years.csv`.

---

## 1. Average degree over the years, and why 1.65

**What 1.65 is.**
- It is the **densification exponent** of the faculty co-authorship network (INSIGHTS.md section 1): links E grow as N^a, where N is the number of faculty with at least one faculty co-author.
- a = 1.65 (R² = 0.998). Since average degree = 2E/N, the **average number of co-authors grows as N^0.65**.
- a = 1 would mean a constant average degree. a = 2 would mean everyone eventually links to a fixed share of everyone.
- Our 1.65 sits in between, near the top of the range Leskovec, Kleinberg & Faloutsos (2005, https://doi.org/10.1145/1081870.1081893) found for growing real networks: 1.56 and 1.68 for arXiv citation graphs, 1.66 for US patents, 1.18 for internet routers and 1.08–1.15 for author–paper graphs.

**Average degree year by year** (`g_average_degree_by_year.csv`):

| | 2016 | 2018 | 2020 | 2022 | 2025 |
|---|---|---|---|---|---|
| Co-authors per connected faculty member, all links up to that year | 1.67 | 2.22 | 2.83 | 3.05 | **3.48** |
| Co-authors per faculty member who wrote with a colleague, that year only | 1.67 | 1.74 | 2.00 | 1.70 | **1.69** |

**Why the number is 1.65 and not 1.**
- In any single year, a faculty member who writes with NIT colleagues writes with about **1.7** of them, and that hasn't changed from 2016 to 2025.
- Collaboration intensity is flat. The cumulative average rises only because each year adds a few new partners while the old links stay, and the number of people grows much more slowly than the links (the faculty body grew about 1.6× while links grew 6.8×).
- Links keep growing at about 90 new pairs a year, while the number of connected faculty grows more slowly and levels off as almost everyone gets connected. So a comes out above 1.

**Per NIT** (`g_densification_by_nit.csv`):
- Trichy 1.61, Surathkal 1.70.
- Without the start-up years 2016–2018 (when collaborations from before 2016 are invisible): 1.45 and 1.60.

**Is 1.65 normal? The same measure at four NITs** (faculty only; `f_faculty_densification_four_nits.csv`):

| | Trichy | Surathkal | Warangal | Calicut |
|---|---|---|---|---|
| Exponent a, 2016–2026 | 1.41 | **1.74** | 1.44 | 1.39 |
| Co-authors per connected faculty member, 2025 | 2.53 | **3.28** | 2.89 | 2.65 |

- **Method:** faculty = each NIT's NIRF 2025 list, matched by name to OpenAlex authors who used that NIT's affiliation. 83–91% of faculty were matched. An author ID that fits two people equally well is dropped.
- **Every NIT densifies** (a between 1.4 and 1.75), so 1.65 is not unusual.
- **Surathkal densifies fastest.** Trichy and Calicut, which hired the most new people recently, are lowest: new hires arrive with few links, so they add people faster than links.
- This list covers only *current* faculty. Our roster also keeps people who left, and the author matching differs (automatic here, hand-checked there), so Trichy is 1.61 there and 1.41 here; we have not tested which difference matters more.
- **Counting every author with the NIT's affiliation** (students and staff too), all four NITs give a = 1.18–1.24. In that open population, new students keep arriving, so the exponent is lower. The 1.65 belongs to the *closed* faculty network.

---

## 2. Predict and check: link prediction with a fixed model

**Question.** Which pairs of faculty write their first paper together in a given year?

**Method:**
- Features and model are the same as INSIGHTS.md section 6: common co-authors, Adamic–Adar, resource allocation, Jaccard, the pair's papers, same department and same NIT, fed to a logistic regression.
- **Two models, kept apart:**
  - **A. Fixed model (the main result).** Trained once on 2016–2022, using one-year windows 2016→2017 … 2021→2022. It is then given only the 2022 network and predicts the new pairs of 2023, 2024 and 2025. It never sees any data after 2022. For each year, pairs that already wrote together in an earlier year are dropped and the rest keep their 2022 scores.
  - **B. Updated model (for comparison only).** Re-trained every year and given the real network of the year before: 2022 for 2023, 2023 for 2024, 2024 for 2025.
- **Prediction list:** the fixed model's top 1% of candidate pairs, about 1,570 pairs a year. Every real new pair in that list is a **correct match**; all of them are in `p_fixed_correct_matches.csv`, each with the DOI of the pair's first joint paper.

**Results** (`p_link_prediction.csv`):

| | 2023 | 2024 | 2025 |
|---|---|---|---|
| Real new faculty pairs | 95 | 88 | 84 |
| …that the fixed model can reach (both people had a paper by 2022) | 85 | 68 | 61 |
| **A. Fixed model: AUC** | **0.90** | **0.87** | **0.90** |
| Correct matches in its top 100 | 3 | 2 | 0 |
| **Correct matches in its top 1% (~1,570 pairs)** | **19** | **14** | **9** |
| …times better than a random list of the same size | 22× | 21× | 15× |
| Reachable new pairs in its top 5% | 71% | 62% | 77% |
| B. Updated model: AUC | 0.90 | 0.90 | 0.92 |
| B. Updated model: correct matches in its top 1% | 19 | 15 | 16 |
| Adamic–Adar alone (2022 network): AUC | 0.59 | 0.59 | 0.54 |

- **The fixed model ranks real pairs well, but exact hits are rare.**
  - AUC stays at 0.87–0.90 for all three years without any new data.
  - Each year only about 1 candidate pair in 2,000 starts working together, so precision is low: 1.2%, 0.9% and 0.6% of the top 1%. That is still 15–22× better than random.
- **It weakens over time because people join.**
  - New pairs the 2022 model cannot see at all: 11% of 2023's, 23% of 2024's and 27% of 2025's. These involve faculty with no paper by 2022.
  - In 2025 the fixed model finds 9 correct pairs in its top 1%; the updated model, which sees the newer network, finds 16.
- **The 42 correct matches** are all same-department, same-NIT pairs. 18 of them had no common co-author in 2022, so the model's department and output features matter, not only the network.
- **The updated model's checklist** (`p_predict_and_check_top20.csv`) lists its 20 most likely pairs each year and what happened. Two of them did write together in that year:
  - Jeny Rajan – Chandrasekaran K (Surathkal CSE) in 2024;
  - Dharavath Kishan – Udaykumar R Yaragatti (Surathkal EEE) in 2025.
- **Comparison with other co-authorship networks:** see FINDINGS.md.

---

## 3. Four NITs side by side

`c_four_nits.csv`. Papers come from OpenAlex, the same filter for all four (articles, reviews, conference papers with an author from that NIT, 2016–2025). Faculty numbers come from NIRF 2025.

| | Trichy | Surathkal | Warangal | Calicut |
|---|---|---|---|---|
| Papers 2016–2025 | **10,654** | 9,996 | 9,230 | 7,093 |
| Papers in 2024 | 1,188 | 1,312 | **1,380** | 916 |
| Faculty, NIRF 2025 (regular) | 345 | 279 | 309 | **370** |
| Papers in 2024 per faculty member | 3.44 | **4.70** | 4.47 | 2.48 |
| Assistant Professors | 47% | **30%** | 35% | 65% |
| Citations per paper | **19.3** | 15.5 | 16.3 | 13.4 |
| FWCI, median / mean | 0.70 / 1.54 | 0.69 / 1.39 | 0.69 / 1.43 | 0.60 / 1.18 |
| With a foreign co-author | **19.0%** | 15.2% | 15.7% | 11.9% |
| Partner institutions | **1,745** | 1,486 | 1,530 | 1,270 |
| Conference papers | 21% | 33% | 26% | 33% |

- **Papers per faculty member follow the share of Assistant Professors.** The order is Surathkal > Warangal > Trichy > Calicut for papers per head, and exactly the reverse for the share of Assistant Professors. This is the same explanation as PAPERS.md parts R and D, now seen across four NITs.
- **Warangal grew fastest:** 436 → 1,390 papers a year (×3.2), passing Trichy in 2024. Trichy has been flat at about 1,200 a year since 2020.
- **Impact is about the same at Trichy, Surathkal and Warangal** (median FWCI 0.69–0.70). Calicut is lower (0.60). The higher *mean* at Trichy comes from a few very highly cited papers.
- **Trichy is the most connected:** the most foreign co-authors and the most partner institutions.

**Caveat.** These are institution-level counts with students' papers included, so they are not the same as our faculty-only numbers.

---

## 4. When did today's faculty join?

Joining dates of everyone listed as currently working in the NIRF 2025 files (`n_joining_bands.csv`, `data/reference/nirf_2025_joining_years.csv`):

| Joined | Trichy | Surathkal | Warangal | Calicut |
|---|---|---|---|---|
| before 2000 | 61 | 59 | 59 | 36 |
| 2000–2001 | 4 | 12 | 0 | 15 |
| **2002–2003** | **0** | **4** | **0** | **0** |
| 2004–2005 | 2 | 0 | 0 | 15 |
| 2006–2009 | **118** | 51 | 44 | 55 |
| 2010–2013 | 0 | 50 | 63 | 27 |
| 2014–2017 | 0 | 24 | 6 | 0 |
| 2018–2021 | 91 | 56 | **115** | 99 |
| 2022–2025 | 72 | 23 | 40 | **128** |

- **There was no 2002/2003 hiring wave** among today's faculty at any of the four NITs: 4 people at Surathkal, none elsewhere.
- The waves came in **2006–2009** (Trichy alone hired 118 people still there today) and again from **2018**.
- Each NIT has its own rhythm:
  - Trichy hired almost nobody in 2010–2017;
  - Surathkal hired steadily through 2008–2015;
  - Calicut's faculty is the youngest (median joining year 2018, 65% Assistant Professors).
- **Our roster agrees with the official count:** current faculty 342 vs 348 at Trichy and 269 vs 279 at Surathkal (our roster 2026 vs NIRF 2025).

**Joining cohort and output, our two NITs** (`n_cohort_output.csv`):
- Faculty matched by name: 273 of 348 at Trichy, 241 of 279 at Surathkal.
- Papers a year are counted from the later of 2016 and the joining year.
- The 2006–2009 cohorts publish the most (median 4.2 at Trichy, 4.45 at Surathkal).
- Among those who joined in 2018–2021, Surathkal's publish more (2.36 vs 1.83 a year). That is the junior-faculty gap again.

**Caveat.** NIRF lists only people working there in 2025 (plus recent leavers). Anyone who joined in 2002–2003 and left or retired before about 2022 is missing, so an early wave could look smaller than it was.

---

## 5. Google Scholar reality check

- **Dashboard:** every name in the Faculty tab, and in Phase II's "highest career citations" table, now has a **Scholar ↗** link. It opens a Google Scholar author search for that name and the NIT's city or state.
- **Checklist** (`s_scholar_check.csv`): the 15 faculty with the highest OpenAlex career citations, plus the three most-cited physicists (A Chandra Bose, B Karthikeyan, Nagaraja H S). For each it gives the OpenAlex citations and h-index, and how much of those citations come from their NIT papers.
- **Scholar columns are filled in by hand.** Google Scholar blocks automated access (it showed a robot check), so the Scholar columns must be filled in from a browser. Re-running `phase2_growth.py scholar` keeps whatever was typed in.
- **Already suspicious from OpenAlex alone:** Kunwar Singh (1.3% of career citations from NIT papers), Aditya Kumar (0.2%), Sandeep Kumar (3%) and S Selvakumar (7%). These look like one OpenAlex profile merging several people of the same name. Their Scholar profiles should settle it.

---

## Files

| File | Contents |
|---|---|
| `g_average_degree_by_year.csv`, `g_densification_by_nit.csv`, `g_average_degree.png`, `g_summary.json` | Section 1, our faculty network |
| `f_faculty_network_four_nits.csv`, `f_faculty_densification_four_nits.csv`, `f_nirf_name_matching.csv`, `f_faculty_network_four_nits.png` | Section 1, four NITs (faculty only) |
| `p_link_prediction.csv`, `p_fixed_correct_matches.csv`, `p_predict_and_check_top20.csv`, `p_link_prediction.png`, `p_summary.json` | Section 2 |
| `c_four_nits.csv`, `c_four_nits_by_year.csv`, `c_four_nits_network_by_year.csv`, `c_four_nits_densification.csv`, `c_four_nits.png` | Section 3 |
| `n_joining_bands.csv`, `n_cohort_output.csv`, `n_roster_vs_nirf.csv`, `n_joining_years.png`, `n_summary.json` | Section 4 |
| `s_scholar_check.csv` | Section 5 |
