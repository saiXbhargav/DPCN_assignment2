# Phase II: deeper questions from published studies

Ten papers came with the Phase II note. Five come from the same "science of science" group (Clauset, Larremore and co-authors). We used them to choose **better questions and fairer methods**, not to copy them. The gender and race parts need data we don't have, so we left them out; their methods carry over.

Everything here is made by `scripts/phase2_papers.py`, which writes to this folder:

```
python scripts/phase2_papers.py            # all parts
python scripts/phase2_papers.py citers     # or one part: citers, selfcite, adjusted, core, productivity, turnover, teams, assort
```

**Scope:**
- Paper questions use all papers where noted.
- Faculty networks and faculty comparisons use faculty only: 743 people after the roster fix, 657 of them with papers.
- Every random step has a fixed seed, so each run gives the same numbers.

| Part | Question | Idea from |
|---|---|---|
| [A](#a-who-cites-us-and-why) | Who cites us, and why? | Singh, Vasques Filho, Jolad & O'Neale, *Scientometrics* 2020; Bhowmick, Singhal & Wang |
| [S](#s-the-citation-network-without-self-citations) | What is left of the citation network without self-citations? | (our own check) |
| [R](#r-a-fair-comparison-of-the-two-nits) | Is the Trichy vs Surathkal comparison fair? | Spoon et al., *PNAS Nexus* 2026 (careful, non-causal wording) |
| [C](#c-core-periphery-and-which-new-links-would-help) | Who is in the core, and which new links would help most? | Barnes et al., ACM FAccT 2026 |
| [B](#b-is-productivity-a-random-walk) | Do careers follow a rise-and-fall curve? | Zhang, LaBerge, Way, Larremore & Clauset, *npj Complexity* 2026 |
| [D](#d-hiring-vs-leaving) | How much of the change comes from hiring, how much from leaving? | LaBerge, Wapman, Clauset & Larremore, *eLife* 2024 |
| [E](#e-team-size-in-finer-bands) | Team size beyond "<10 vs ≥10 authors" | (the Phase II note on 10–100-author papers) |
| [F](#f-assortative-or-disassortative) | Assortative or disassortative, and on what? | Newman 2002/2003; Li et al., *Nat Comput Sci* 2025 (null models) |

---

## A. Who cites us, and why?

**Question.** Private universities cite us a lot. Is that because they are big, or because the citing authors know our authors?

**Method** (following Singh et al. 2020, who found most citations come from co-authors and people within three steps in the co-authorship network):
1. Built a co-authorship index from every author of our 21,260 papers: 24,646 authors and 77,923 author pairs. Papers with more than 50 authors are left out, so a single big-team paper does not link everyone.
2. Took every Indian citation of our papers (67,114) and every internal citation (23,822). For each one, we found the closest pair of citing and cited authors. Each citation then falls into one class:
   - **self**: an author cites their own paper;
   - **co-author (before)**: the two had a joint paper before the citation;
   - **co-author (later)**: a joint paper only after it;
   - **2 steps** or **3 steps** in the co-authorship network;
   - **farther** (more than 3 steps, or not connected);
   - **no link** (none of the citing authors appears in our co-authorship data).
3. Compared the top 40 citing institutes, private (18) against public (22), with a χ² test.

**Results** (`a_citation_distance.csv`):

| Citations | Self | Co-author before | 2–3 steps | Within 3 steps | No link |
|---|---|---|---|---|---|
| All Indian citations (67,114) | 10.0% | 4.2% | 6.9% | **21.7%** | 67.1% |
| From the top private citers (18,352) | 12.9% | 6.8% | 10.6% | **31.0%** | 55.1% |
| From the top public citers (14,410) | 10.2% | 4.0% | 6.0% | **20.7%** | 67.0% |
| Internal (our papers citing our papers) | **86.3%** | 5.0% | 4.5% | 96.5% | 0.6% |

- **About one Indian citation in five comes from someone at most three co-authorship steps away.**
- **Private universities' citations are more personal:** 31% within three steps vs 21% for public ones (χ² p = 7.6 × 10⁻¹²²). They have more self-citations (12.9% vs 10.2%) and more citations from earlier co-authors (6.8% vs 4.0%).
- Together with the size result in PHASE2.md task 2, the answer to the private-citer question is:
  - private citers cite us no more *per paper* than public ones;
  - their citations come more often from people who already work with our authors, such as former students, former faculty and co-authors.
- **Co-author citations follow the first joint paper:** 40% come within 2 years of it, and longer lags are rarer, partly because our 2016–2026 window cuts them off (`a_coauthor_citation_lag.csv`). Singh et al. report a similar pattern.
- **Internal citations are almost all self-citations** (86%). That is why we redo the citation network without them in part S.

**Caveats:**
- OpenAlex author IDs are sometimes split or merged. A split hides a self-citation, so the "self" share is a lower bound.
- Co-authorship is only what is visible on *our* papers. Citing authors may also be linked through papers we don't have, so "no link" is an upper bound.

**Files:**
- `a_citation_distance.csv`: classes by group.
- `a_citation_distance_by_year.csv`.
- `a_coauthor_citation_lag.csv`.
- `a_citation_distance.png`.
- `a_summary.json`.

---

## S. The citation network without self-citations

**Question.** The internal citation network (our papers citing our papers) drives the "most influential papers" ranking. How much of it is authors citing themselves?

**Method:**
- An internal citation is a **self-citation** when the citing and cited papers share at least one author (OpenAlex author IDs).
- We dropped those and computed PageRank again on what is left.
- We also counted how citations flow between departments and between the two NITs.

**Results** (`s_summary.json`):
- **86.3% of the 23,822 internal citations are self-citations** (88% if only faculty authors count). Only **3,263** citations are left.
- **The PageRank ranking changes completely:**
  - Spearman correlation of 0.45 between the full and clean scores;
  - **none** of the top 10 papers are the same;
  - in the full network, 6 of the top 10 are 2016 papers (old papers have had more time to collect self-citations); in the clean network, only 2 are.
- **Between the two NITs:** Trichy → Surathkal 267 and Surathkal → Trichy 283 clean citations (315 and 319 with self-citations). The flow is balanced.
- **Knowledge stays inside departments:** 73.8% of clean citations stay in the same department. The largest cross-department flows are:
  - Mechanical → MME 97;
  - MME → Mechanical 62;
  - Mechanical → Production 57.
- The self-citation-free network is also not assortative. See PHASE2.md task 12: in-in r = 0.13 against 0.13 for rewired networks.

**Caveat.** Some self-citations are fair: building on your own earlier work is normal. The point is that the full network measures **research-group chains**, not influence on other people.

**Files:**
- `s_pagerank_top10.csv`: both rankings.
- `s_nit_flow.csv`.
- `s_department_flow_matrix.csv`.
- `s_top_department_flows.csv`.
- `s_summary.json`.

---

## R. A fair comparison of the two NITs

**Question.** "Surathkal publishes more per person" and "the two NITs have the same impact". Do these headlines survive a fairer comparison?

**Method:**
1. **Within rank.** NIT Trichy has many more Assistant Professors (48% of its faculty vs 31% at Surathkal), and new Assistant Professors publish less. So we compared papers per year *on the faculty list*, rank by rank, with Mann–Whitney tests. We also ran a regression with rank and department controls.
2. **Clustered errors.** Papers by the same faculty member are not independent. We re-ran the FWCI regression with errors clustered by faculty member (CR1), next to the robust (HC1) errors used before.
3. **Recent years.** FWCI for 2025–26 papers is still settling, so we re-ran the regression on papers up to 2024 and up to 2023.
4. **Many tests.** We applied the Benjamini–Hochberg false-discovery-rate correction (5%) within each family of tests: branches, partner countries, partner types, former vs current faculty, private vs public citers.

**Results:**

| Rank | Trichy faculty | Surathkal faculty | Papers/year, Trichy | Papers/year, Surathkal | p |
|---|---|---|---|---|---|
| Assistant Professor | 198 | 102 | 1.05 | **2.50** | 0.0004 |
| Associate Professor | 45 | 82 | 2.60 | **3.45** | 0.010 |
| Professor | 111 | 107 | 4.10 | 3.70 | 0.71 |
| Professor (HAG) | 46 | 34 | 4.35 | 4.11 | 0.81 |
| All ranks | 415 | 328 | 2.40 | 3.40 | <0.001 |

- **"Surathkal publishes more per person" is partly about who is on the list.**
  - The gap shrinks from +33% to +24% after controlling for rank (95% CI 11–39%). It stays at +24% with department added.
  - It exists **only among Assistant and Associate Professors**. Senior faculty publish the same at both NITs.
  - Trichy hired far more new Assistant Professors (part D).
- **"Same impact" holds, and more clearly:**
  - the Surathkal effect on FWCI is +1.2% with p = 0.22 (robust errors) and **p = 0.63** with clustered errors (650 faculty clusters);
  - with papers up to 2023 it is −0.05%.
- **The foreign co-author effect survives clustering:** +15%, p = 0.0001 clustered. It holds for every year cut.
- **What does not survive the false-discovery correction** (`r_false_discovery.csv`):
  - the Mechanical and ECE branch gaps (adjusted p 0.06);
  - "Other NIT" and "Foreign other" as partner types (0.06, 0.07);
  - Taiwan as a partner country (0.07);
  - private citers being nearer (0.049 → 0.12);
  - several former-vs-current faculty differences.
  
  We now present these as *weak* evidence, not findings.

**Caveat.** Rank is the latest one on the faculty pages, so promotions during 2016–2026 are not visible.

**Files:**
- `r_institutes_within_rank.csv`.
- `r_papers_per_year_models.csv`.
- `r_fwci_model_sensitivity.csv`.
- `r_false_discovery.csv`: every test with raw and adjusted p.
- `r_summary.json`.

---

## C. Core, periphery and which new links would help

**Question.** Barnes et al. (2026) show that in the US computer-science co-authorship network, central positions follow prestige, and that a few well-chosen new links help peripheral faculty most. Is our faculty network the same? Which links would help?

**Method:**
- **Structure:** k-core number of each faculty member, Gini coefficient of degree, betweenness and harmonic centrality, by NIT and by rank.
- **Edge interventions:** we measured the network's global efficiency, which is the average of 1 / distance over all pairs. Then we added the 10 new links that raise it the most (greedy search over possible pairs in the same department, using an all-pairs distance matrix that is updated after each link). We compared this with 10 random links. Two settings:
  - pairs inside the same NIT;
  - pairs across the two NITs.
- **Peripheral faculty:** for the 119 faculty in the largest connected group who have only one co-author link, we compared two ways of giving each one new link:
  - a link to a core member of their own department;
  - a link to a random colleague in their department.

**Results** (`c_summary.json`):

| | Faculty with papers | Isolated | In the 3+ core | Max core | Gini of harmonic centrality |
|---|---|---|---|---|---|
| NIT Trichy | 357 | **23%** | 27% | 3 | 0.41 |
| NIT Surathkal | 300 | 11% | 37% | 4 | 0.23 |

- **Surathkal's faculty network is more cohesive.** It has fewer isolated people, a deeper core and less unequal centrality. Trichy has more people outside the network (many new Assistant Professors).
- **The core is senior:** 14% of Assistant Professors are in the 3+ core, against 49% of Professors (HAG).
- **Core position goes with standing:**
  - k-core number vs h-index: Spearman ρ = 0.62;
  - k-core number vs FWCI: ρ = 0.28.
  
  This is the same pattern Barnes et al. found with prestige.
- **A few links help a lot:**
  - the best 10 new links raise global efficiency by **+9.8%** inside the NITs and **+10.3%** across them;
  - 10 random links give +1.6% and +2.5%;
  - example cross-NIT pairs: Gangadharan K V (Surathkal) – S Suresh (Trichy) in Mechanical; A Senthil Thilak – V Ravichandran in Mathematics.
- **Linking peripheral faculty to their department's core** raises their harmonic centrality by a median **+27.5%**, against +11.0% for a random colleague.

**Caveat.** These are *what-if* calculations on the network structure. They don't say the pairs would want to work together. Topic fit (the link-prediction scores in the Research questions tab) should be checked too.

**Files:**
- `c_centrality_inequality.csv`.
- `c_core_by_rank.csv`.
- `c_best_new_links.csv`.
- `c_summary.json`.

---

## B. Is productivity a random walk?

**Question.** Zhang et al. (2026) found that only about one career in five follows the "rise, peak, decline" curve. Yearly output looks more like a random walk, and total output follows a lognormal distribution. Does that hold here?

**Method:**
- 320 faculty on the list from 2016/17 to 2025 with at least 10 papers in 2016–2025.
- For each person:
  - papers per year;
  - a simple shape label: rising, falling, flat, peak in the middle, dip in the middle;
  - the year-to-year changes and their lag-1 autocorrelation, compared with the same changes shuffled in time.
- Total 2016–2025 output of all 644 faculty with at least one paper in those years was fitted by maximum likelihood with a power law and with a lognormal, and compared with a Vuong likelihood-ratio test (as in `network_science.py`).

**Results** (`b_summary.json`):
- **There is no common career curve.**
  - Shapes: 45% peak in the middle, 18% rising, 17% dip in the middle, 13% flat, the rest falling.
  - The *average* trajectory is flat.
  - The two NITs have almost the same mix (`b_trajectory_shapes_by_nit.csv`).
- **Year-to-year changes are large and noisy:**
  - SD 4.0 papers;
  - heavy tails (kurtosis 3.1);
  - lag-1 autocorrelation −0.37, against −0.47 when shuffled. A good year is often followed by a weaker one, as in a noisy random walk.
- **Bigger producers change more:** the size of the change grows with the level (exponent 0.34).
- **Total output is closer to lognormal than to a power law** (Vuong z = 12.2, p < 0.001). An exact lognormal is still rejected (KS p < 0.001). So it is "lognormal-like", not exactly lognormal. This fits the Lotka result in the Research questions tab.
- **By rank:** senior faculty's output peaks around 2020, while Assistant Professors keep rising (`b_mean_trajectory_by_rank.csv`).

**Caveat.** We have 10 years, not whole careers, so "peak in the middle" means a peak within 2016–2025 only.

**Files:**
- `b_trajectory_shapes.csv`.
- `b_trajectory_shapes_by_nit.csv`.
- `b_mean_trajectory_by_rank.csv`.
- `b_productivity.png`.
- `b_summary.json`.

---

## D. Hiring vs leaving

**Question.** LaBerge et al. (2024) split the change in a faculty body into who was hired and who left. How did each NIT's faculty change from 2016 to 2026, and what does each group contribute?

**Method:**
- From each person's first and last year on the faculty pages, we put each person in one group: stayed 2016–2026, joined after 2016, left before 2026, or joined and left.
- For each group: size, papers per year on the list, FWCI and rank mix.
- A simple counterfactual: how much bigger 2025 output would be if nobody had left.

**Results** (`d_summary.json`):

| | Faculty 2016 | Faculty 2026 | Joined | Left | 2025 papers from joiners | +2025 output if none had left |
|---|---|---|---|---|---|---|
| NIT Trichy | 209 | **342** | 206 | 73 | 37% | +12% |
| NIT Surathkal | 221 | 269 | 107 | 59 | 45% | +13% |

- **Trichy grew much faster**, by hiring about twice as many people.
  - 94% of its joiners still on the list are Assistant Professors, against 70% at Surathkal.
  - Its joiners publish a median of **1.0 paper per year**, against **2.67** at Surathkal.
  - This is the main reason for Trichy's lower per-person output in part R.
- **The people who stayed publish the same at both NITs:** 4.15 (Trichy) vs 3.60 (Surathkal) papers per year.
- **The joiners already matter:** they wrote 37% (Trichy) and 45% (Surathkal) of 2025 output by listed faculty.
- **Growth is concentrated:** at Trichy, Civil (+16), EEE (+14), CSE (+12) and ECE (+12).

**Caveats:**
- The years come from yearly snapshots of the faculty pages, so a page that was not updated shifts a year.
- The rank is the latest one only, so promotions cannot be told apart from hiring.

**Files:**
- `d_groups.csv`.
- `d_decomposition.csv`.
- `d_departments.csv`.
- `d_headcount_by_year.csv`.
- `d_summary.json`.

---

## E. Team size in finer bands

**Question.** The Phase II note asks about papers with 10 to 100 authors. Beyond "<10 vs ≥10 authors", how does impact change with team size, and is there any "big science" here?

**Method:**
- Faculty papers were put into bands by number of authors.
- For each band: mean FWCI with a 2,000-sample bootstrap 95% CI, median FWCI, and the share of papers in the top 10% by FWCI.
- The yearly trend of team size.
- The regression of log(1 + FWCI) on log(authors) with the usual controls.

**Results** (`e_team_size_bands.csv`):

| Authors | Faculty papers | Share | Mean FWCI (95% CI) | Median FWCI |
|---|---|---|---|---|
| 1 | 138 | 0.8% | 0.72 (0.53–0.94) | 0.26 |
| 2–3 | 11,037 | 60.2% | 1.27 (1.22–1.32) | 0.58 |
| 4–5 | 5,215 | 28.4% | 1.40 (1.33–1.47) | 0.68 |
| 6–9 | 1,812 | 9.9% | 1.67 (1.56–1.79) | 0.90 |
| 10–19 | 140 | 0.8% | 2.09 (1.59–2.66) | 1.25 |
| 20+ | 1 | 0.01% | – | – |

- **Impact rises steadily with team size**, and the confidence intervals of neighbouring bands barely overlap. With controls, doubling a team goes with **+7.8%** FWCI (p < 0.001, 18,342 papers).
- **There is essentially no big science:** only 1 faculty paper has 20 or more authors, and none has 50 or more. Counting students' papers, there are 6 with 20+ authors.
- **Teams are slowly growing:** from 3.30 authors per paper in 2016 to 3.70 in 2025 (+0.05 per year, p < 0.001).

**Caveat.** This is an association. Bigger teams may also mean better-funded or more established groups.

**Files:**
- `e_team_size_bands.csv`.
- `e_team_size_by_year.csv`.
- `e_team_size.png`.
- `e_summary.json`.

---

## F. Assortative or disassortative?

**Question.** Do faculty link to people like themselves? We check this for degree (as in PHASE2.md task 12), and also for h-index, FWCI, department, rank and institution. Does it change over time?

**Method:**
- The assortativity coefficient r (Newman 2002, 2003): numeric for degree, h-index and FWCI; categorical for department, rank and institution.
- Each r is compared with 100 **degree-preserving rewired** networks (40 for each yearly network) (`double_edge_swap`). A plain random graph would not keep the hubs, so it is not the right comparison.
- The same is done per NIT, and for the network built up to each year from 2016 to 2026.

**Results** (`f_assortativity.csv`):

| Network | Measure | r | Rewired r | z |
|---|---|---|---|---|
| Faculty, both NITs | degree | **0.20** | −0.02 | 7.5 |
| | h-index | **0.26** | −0.01 | 8.3 |
| | FWCI | 0.17 | 0.00 | 6.1 |
| | department | **0.66** | 0.00 | 71 |
| | rank | 0.07 | 0.00 | 4.2 |
| | institution | 0.94 | 0.00 | 28 |
| Faculty, NIT Trichy | degree | 0.11 | −0.02 | 2.5 |
| Faculty, NIT Surathkal | degree | **0.23** | −0.02 | 6.1 |
| Partner institutes (our NITs removed) | institute type | 0.15 | −0.01 | 17 |

- **The faculty network is assortative on degree, as social networks usually are**, and more so at Surathkal (0.23) than at Trichy (0.11). This matches Surathkal's denser core in part C.
- **Prestige homophily:** high-h-index faculty work with other high-h-index faculty (r = 0.26). This is the "core follows prestige" pattern from Barnes et al.
- **Rank mixing is weak but not random** (r = 0.07). Only 35% of links join people of the same rank, so mentoring crosses ranks. Assistant–Assistant links are 1.6× what chance would give (`f_rank_mixing.csv`), so young faculty also team up with each other.
- **Departments are strong walls** (r = 0.66). The most outward-looking departments are Energy & Environment (30% of links inside the department) and Chemistry (34%) (`f_department_homophily.csv`).
- **Over time:**
  - degree assortativity dipped to near random in 2017–2018 (r = 0.06 and 0.01, z ≈ 1) after 0.20 in the small 2016 network, and has been 0.17–0.20 since 2022;
  - it has risen to about 0.20 since 2022 (z ≈ 5–7; `f_assortativity_by_year.csv`);
  - as the network grew, well-connected people connected with each other more.
- **Partner institutes of the same type link with each other** on our papers (r = 0.15 against −0.01): IITs with IITs, private with private.
- **The citation network** (PHASE2.md task 12) looks strongly assortative (in-in 0.48). Without self-citations, it is what rewiring gives (0.13 vs 0.13). So that pattern comes from self-citation chains.

**Caveat.** r is one number per network. The k_nn(k) chart in PHASE2.md shows that the degree pattern is not driven by a single point.

**Files:**
- `f_assortativity.csv`.
- `f_assortativity_by_year.csv`.
- `f_assortativity_by_year.png`.
- `f_rank_mixing.csv`.
- `f_department_homophily.csv`.
- `f_assortativity_summary.json`.

---

## What the papers taught us about method

- **Compare with a null model before calling something special.** Papers 4 and 5 call co-authorship networks "small world" or "scale-free" without one. We test small world against degree-preserving rewired networks (σ = 16.1). We fit a lognormal against a power law with a likelihood-ratio test. Every assortativity value here has a rewired null.
- **Say "goes with", not "causes".** Spoon et al. and LaBerge et al. word survey and regression results as associations. We now do the same: for example, "foreign co-authors *go with* higher impact".
- **Check for many tests.** With dozens of comparisons, some p < 0.05 results are chance. The false-discovery-rate correction in part R removes 15 of them.
