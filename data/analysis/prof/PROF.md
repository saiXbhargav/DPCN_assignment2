# Follow-ups from the Phase II meeting with the professor (17 Nov 2026)

Made by `scripts/phase2_prof.py`, which writes to this folder. On the dashboard, these are the last four panels of the **Phase II** tab, plus a "Scholar ↗" link next to every name in the **Faculty** tab.

```
python scripts/fetch_peers.py                 # papers of four NITs from OpenAlex (data/raw/peers/)
python scripts/phase2_prof.py growth predict  # average degree and 1.66; rolling link prediction
python scripts/phase2_prof.py nirf nitfaculty # needs pymupdf: NIRF faculty lists, joining years, faculty-only networks
python scripts/phase2_prof.py nits scholar    # four NITs side by side; Google Scholar checklist
```

| Professor's note | What we did | Section |
|---|---|---|
| "Nodes – plot the average degree; check how it changes across the years" | Average co-authors per year, counted two ways, per NIT | [1](#1-average-degree-over-the-years-and-why-166) |
| "Network – why 1.66?" | What the exponent means, and the same number at three other NITs | [1](#1-average-degree-over-the-years-and-why-166) |
| "2016–2022 → 2023, 2024 & 2025; give 2023 as input when predicting 2024, and the same for 2025"; "machine will predict and check" | Rolling link prediction, checked against the links that really appeared | [2](#2-predict-and-check-rolling-link-prediction) |
| "Actual comparisons – two more NITs"; "number of faculty, pure number" | NIT Warangal and NIT Calicut next to our two NITs, with official faculty numbers | [3](#3-four-nits-side-by-side) |
| "Check if more faculty were recruited then – 2002/2003" | The joining year of every current faculty member, from NIRF 2025 | [4](#4-when-did-todays-faculty-join) |
| "Physics guy – physics reality"; "link it to Google Scholar" | Scholar links on the dashboard, and a checklist for the most-cited faculty | [5](#5-google-scholar-reality-check) |

**New sources.** Both were approved by the user on 17 Nov.
- **OpenAlex:** papers of NIT Warangal (`I121750182`) and NIT Calicut (`I114845381`), plus a fresh copy of our two NITs. All four use the same filter and the same day.
- **NIRF 2025 data files:** each NIT's own copy of its "Overall" NIRF 2025 submission.
  - Trichy: [nitt.edu](https://www.nitt.edu/home/academics/nirf/1.%20NIRF%202025_IR-O-U-0467_Overall.pdf)
  - Surathkal: [nitk.ac.in](https://www.nitk.ac.in/document/attachments/8178/Overall.pdf)
  - Warangal: [nitw.ac.in](https://nitw.ac.in/api/static/files/20250627_NIRF_2025_Submitted_data_Overall_2025-7-1-15-41-37.pdf)
  - Calicut: [nitc.ac.in](https://nitc.ac.in/imgserver/uploads/attachments/overall_f0a48d77-126f-477d-84d6-fbd669ab6061_0.pdf)

  Each file lists every faculty member with designation, joining date and whether they still work there. The files also list age and gender, so they are kept out of the repo (`data/raw/nirf/` is git-ignored). Only counts are saved, in `data/reference/nirf_2025_faculty_counts.csv` and `nirf_2025_joining_years.csv`.

---

## 1. Average degree over the years, and why 1.66

**What 1.66 is.**
- It is the **densification exponent** of the faculty co-authorship network (INSIGHTS.md section 1): links E grow as N^a, where N is the number of faculty with at least one faculty co-author.
- a = 1.66 (R² = 0.998). Since average degree = 2E/N, the **average number of co-authors grows as N^0.66**.
- a = 1 would mean a constant average degree. a = 2 would mean everyone eventually links to a fixed share of everyone.
- Our 1.66 sits in between, near the top of the range Leskovec, Kleinberg & Faloutsos (2005) found for growing real networks.

**Average degree year by year** (`g_average_degree_by_year.csv`):

| | 2016 | 2018 | 2020 | 2022 | 2025 |
|---|---|---|---|---|---|
| Co-authors per connected faculty member, all links up to that year | 1.67 | 2.22 | 2.83 | 3.05 | **3.48** |
| Co-authors per faculty member who wrote with a colleague, that year only | 1.67 | 1.74 | 2.00 | 1.70 | **1.69** |

**Why the number is 1.66 and not 1.**
- In any single year, a faculty member who writes with NIT colleagues writes with about **1.7** of them, and that hasn't changed from 2016 to 2025.
- Collaboration intensity is flat. The cumulative average rises only because each year adds a few new partners while the old links stay, and the set of people is almost fixed (faculty roster).
- Links keep growing at about 90 new pairs a year, while the number of connected faculty grows more slowly and levels off as almost everyone gets connected. So a comes out above 1.

**Per NIT** (`g_densification_by_nit.csv`):
- Trichy 1.61, Surathkal 1.70.
- Without the start-up years 2016–2018 (when collaborations from before 2016 are invisible): 1.45 and 1.60.

**Is 1.66 normal? The same measure at four NITs** (faculty only; `f_faculty_densification_four_nits.csv`):

| | Trichy | Surathkal | Warangal | Calicut |
|---|---|---|---|---|
| Exponent a, 2016–2026 | 1.41 | **1.74** | 1.44 | 1.39 |
| Co-authors per connected faculty member, 2025 | 2.53 | **3.28** | 2.89 | 2.65 |

- **Method:** faculty = each NIT's NIRF 2025 list, matched by name to OpenAlex authors who used that NIT's affiliation. 83–91% of faculty were matched. An author ID that fits two people equally well is dropped.
- **Every NIT densifies** (a between 1.4 and 1.75), so 1.66 is not unusual.
- **Surathkal densifies fastest.** Trichy and Calicut, which hired the most new people recently, are lowest: new hires arrive with few links, so they add people faster than links.
- This list covers only *current* faculty. Our roster also keeps people who left, which is why Trichy is 1.61 there and 1.41 here.
- **Counting every author with the NIT's affiliation** (students and staff too), all four NITs give a = 1.18–1.24. In that open population, new students keep arriving, so the exponent is lower. The 1.66 belongs to the *closed* faculty network.

---

## 2. Predict and check: rolling link prediction

**Question.** Which pairs of faculty write their first paper together in a given year?

**Method:**
- The same features and model as INSIGHTS.md section 6: common co-authors, Adamic–Adar, resource allocation, Jaccard, the pair's papers, same department, same NIT, and a logistic regression.
- **Rolling:** the model learns from one-year windows (2018→2019 … 2021→2022) and predicts 2023 from the 2022 network. For 2024, the real 2023 network is given as input and the model is refitted with the 2022→2023 window too. The same for 2025.
- **Fixed:** the 2022 network and the 2022 model predict every later year.

**Results** (`p_rolling_link_prediction.csv`):

| Target year | Real new links | AUC (rolling) | Real links in the top 5% of pairs: rolling | fixed 2022 | Out of reach for the fixed model |
|---|---|---|---|---|---|
| 2023 | 85 | 0.90 | 68% | 68% (same model) | 0% |
| 2024 | 75 | 0.90 | 64% | 53% | 9% |
| 2025 | 78 | 0.92 | **79%** | **60%** | **22%** |

- **Giving the latest year as input matters.** The fixed model gets steadily worse, mainly because new people join. By 2025, 22% of the new links involve faculty who had no paper in 2022, and a model stuck on 2022 can never predict them.
- **The model ranks the real pairs high:** AUC 0.90–0.92 every year, and about 4 in 5 real new pairs are in its top 5%. Network scores alone (Adamic–Adar) reach only AUC ≈ 0.6, because most pairs have no common co-author.
- **Exact hits are rare.** Each year only about 1 pair in 2,000 starts working together (base rate 0.04–0.05%). The top 100 predictions contain 1–3 real pairs, still 25–75× better than random.
- **The checklist** (`p_predict_and_check_top20.csv`) lists the 20 most likely pairs each year and what happened. For 2025, Dharavath Kishan – Udaykumar R Yaragatti (Surathkal EEE) did write together. Most of the others are same-department pairs with 2–4 common co-authors who have not written together yet.

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
- **Scholar columns are filled in by hand.** Google Scholar blocks automated access (it showed a robot check), so the Scholar columns must be filled in from a browser. Re-running `phase2_prof.py scholar` keeps whatever was typed in.
- **Already suspicious from OpenAlex alone:** Kunwar Singh (1.3% of career citations from NIT papers), Aditya Kumar (0.2%), Sandeep Kumar (3%) and S Selvakumar (7%). These look like one OpenAlex profile merging several people of the same name. Their Scholar profiles should settle it.

---

## Files

| File | Contents |
|---|---|
| `g_average_degree_by_year.csv`, `g_densification_by_nit.csv`, `g_average_degree.png`, `g_summary.json` | Section 1, our faculty network |
| `f_faculty_network_four_nits.csv`, `f_faculty_densification_four_nits.csv`, `f_nirf_name_matching.csv`, `f_faculty_network_four_nits.png` | Section 1, four NITs (faculty only) |
| `p_rolling_link_prediction.csv`, `p_predict_and_check_top20.csv`, `p_rolling_link_prediction.png`, `p_summary.json` | Section 2 |
| `c_four_nits.csv`, `c_four_nits_by_year.csv`, `c_four_nits_network_by_year.csv`, `c_four_nits_densification.csv`, `c_four_nits.png` | Section 3 |
| `n_joining_bands.csv`, `n_cohort_output.csv`, `n_roster_vs_nirf.csv`, `n_joining_years.png`, `n_summary.json` | Section 4 |
| `s_scholar_check.csv` | Section 5 |
