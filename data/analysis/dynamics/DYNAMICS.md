# Network dynamics

`scripts/dynamics.py` → this folder. It covers how things move through the **faculty co-authorship network** of both NITs, using faculty-to-faculty links only (`same_nit` and `nit_nit` rows of `data/authorship_network.csv`, where papers with more than 50 authors are already excluded). The network has 657 faculty with at least one faculty co-author and 961 links.

The team agreed on these choices:
- spreading is studied with SIR simulations plus the epidemic threshold;
- a super-tie is a pair in the top 10% of pairs by number of joint papers;
- a newcomer is a faculty member first listed on the faculty pages in 2017 or later;
- Kuramoto: natural frequencies drawn from a standard normal distribution, on the unweighted largest connected group;
- research groups: Louvain communities in 3-year sliding windows.

| Section | Files |
|---|---|
| 1. Spreading | `spread_threshold.csv`, `spread_simulations.csv`, `spread.png` |
| 2. Triangles (higher-order structure) | `triangles_all.csv`, `triangles_by_mix.csv`, `triangles_summary.json` |
| 3. Super-ties | `superties_pairs.csv`, `superties_summary.json`, `superties.png` |
| 4. Newcomers | `newcomers.csv`, `newcomers_by_institute.csv`, `newcomers_summary.json`, `newcomers.png` |
| 5. Brokers | `brokers.csv`, `brokers_summary.json`, `brokers.png` |
| 6. Kuramoto synchronisation | `sync_summary.csv`, `sync_curves.csv`, `sync_locked.csv`, `sync.png` |
| 7. Do collaborations last? | `ties_pairs.csv`, `ties_renewal_by_experience.csv`, `ties_renewal_by_group.csv`, `ties_gaps.csv`, `ties_summary.json`, `ties.png` |
| 8. Research groups over time | `groups_by_window.csv`, `groups_per_window.csv`, `groups_links.csv`, `groups_lifetimes.csv`, `groups_summary.json`, `groups.png` |

The dashboard shows all eight in the **Network dynamics** tab.

## 1. How far can an idea spread?

**Method:**
- **SIR model:** an idea starts with 5 faculty. Each person who has it gets one chance to pass it to each co-author, with probability β. Each value is the mean of 500 runs.
- **Seeds:** the 5 best-connected faculty (hubs), the 5 with the highest betweenness (brokers), or 5 random faculty.
- **Epidemic threshold:** 1/λ₁, where λ₁ is the largest eigenvalue of the unweighted adjacency matrix. Above this β, spreading can take off.
- **IPR:** the inverse participation ratio of the leading eigenvector. A high IPR means spreading depends on a small core.
- **Null model:** 20 degree-preserving rewired copies of each network.

| Network | Faculty | Links | λ₁ | Rewired λ₁ | Threshold 1/λ₁ | IPR | Rewired IPR |
|---|---:|---:|---:|---:|---:|---:|---:|
| NIT Trichy | 357 | 429 | 6.05 | 5.41 | 0.165 | 0.033 | 0.026 |
| NIT Surathkal | 300 | 504 | 7.88 | 6.48 | 0.127 | 0.051 | 0.025 |
| Both NITs | 657 | 961 | 8.0 | 6.3 | 0.125 | 0.053 | 0.021 |

Mean share of faculty reached (%):

| Network | Seeds | β = 0.05 | 0.1 | 0.2 | 0.3 | 0.5 |
|---|---|---:|---:|---:|---:|---:|
| NIT Trichy | hubs | 2.3 | 3.6 | 8.6 | 18.0 | 39.3 |
| NIT Trichy | brokers | 1.9 | 2.8 | 6.3 | 15.6 | 39.7 |
| NIT Trichy | random | 1.6 | 1.9 | 3.9 | 10.1 | 36.0 |
| NIT Surathkal | hubs | 3.0 | 5.1 | 13.6 | 28.9 | 56.9 |
| NIT Surathkal | brokers | 2.9 | 5.1 | 14.9 | 30.5 | 56.9 |
| NIT Surathkal | random | 2.0 | 2.8 | 8.4 | 24.8 | 57.3 |

**Findings:**
- **Ideas take off more easily at NIT Surathkal.** Its threshold is lower (0.127 vs 0.165), and at every β it reaches a larger share of its faculty.
- **The real networks spread more easily than random ones.** λ₁ is 12–22% higher than in the rewired copies, and the IPR is higher too: spreading leans on a connected core (Ramesh M R and the Mechanical / MME group at Surathkal; Samsudeen, Sivakumaran and Suresh at Trichy).
- **Who starts it matters only when ideas pass weakly.** At β = 0.2, five hubs reach 8.6% of NIT Trichy against 3.9% for five random faculty, more than twice as far. At β = 0.5 the seeds no longer matter (about 57% at Surathkal for every seed type).
- **The two NITs barely help each other spread.** λ₁ for both NITs together (8.0) is hardly above Surathkal alone (7.9), because only a few dozen links cross between the NITs.

## 2. Teams or pairs? Higher-order triangles

**Method:**
- A **faculty triangle** is three faculty who have all co-authored with each other.
- It is **filled** if at least one paper has all three faculty on it.
- A filled triangle is **born as a team** if that three-person paper came no later than the first pairwise papers, and **sealed later** otherwise.

**Findings:**
- **There are 314 triangles, and 58% are filled** by a three-person paper. The other 42% (132) never had all three on one paper: they are pure pairwise closure.
- **Most filled triangles were built pair by pair:** 117 were sealed later and only 65 (36%) were born as a team.
- **Teams of three or more faculty are rare.** Only 8.8% of joint faculty papers (288 of 3,278) have 3 or more faculty, yet those papers fill most of the triangles.
- **Cross-department triangles are more often real teams.** 67% of them are filled (85 of 126), against 52% of same-department triangles (97 of 188).
  - Same-department triangles are mostly pairs who share colleagues.
  - Cross-department triangles usually come from one joint project.

## 3. Super-ties: a few durable pairs

**Method:**
- A **super-tie** is a faculty pair in the top 10% of the 961 pairs by number of joint papers. That means 9 or more joint papers, which gives 110 pairs once ties are included.
- **Impact test:** the FWCI of papers by super-tie pairs is compared with other joint faculty papers using a Mann–Whitney test.

**Findings:**
- **Joint output is concentrated in a few pairs.**
  - 11% of pairs (the super-ties) write **52% of all joint faculty papers**.
  - 40% of pairs wrote only one paper together.
- **Super-ties are durable.** They stay active for a median of 7 years.
  - The strongest pair, G Uma and M Umapathy (Trichy, ICE), has 69 joint papers across 2016–2026.
- **Super-ties are within-department:** 89% are in the same department, against 66% of other pairs.
- **Their papers have slightly higher impact.** Median FWCI is 0.80 against 0.70 for other joint papers (p = 0.003). The means are nearly equal (1.50 vs 1.47), so durable pairs do well consistently rather than producing more top papers.

## 4. How newcomers join

**Method:**
- 257 newcomers: faculty first listed in 2017 or later, according to the archived faculty pages.
- For each newcomer we find the year of their first co-author inside their own NIT.
- The archived pages are yearly and some years are missing, so joining years are approximate.

| NIT | Newcomers | Linked by 2026 | Isolated after 3 years | Median years to first link |
|---|---:|---:|---:|---:|
| NIT Surathkal | 93 | 74.2% | 30.0% | 0.0 |
| NIT Trichy | 164 | 57.3% | 52.0% | 1.5 |

**Findings:**
- **Many newcomers stay outside the network.**
  - 63% (163 of 257) have a faculty co-author in their NIT by 2026.
  - Of the 140 newcomers with 3 full years, **46% still have none** after those 3 years.
- **NIT Trichy integrates newcomers more slowly.** Half its newcomers are still isolated after 3 years, against 30% at NIT Surathkal.
- **Newcomers join through their own department and their own cohort, not the hubs.**
  - 76% of first partners are in the newcomer's department.
  - 37% of first partners are newcomers themselves.
  - The first partner has 2.0 faculty co-authors on average, close to the average colleague's 1.8.
- **18% were linked before they were first listed.** For example, people who did their PhD at the NIT, or who joined before their name reached the archived pages.

## 5. Brokers (Burt's structural holes)

**Method:**
- **Constraint** is low when a person's co-authors are not connected to each other, so the person bridges separate groups.
- **Effective size** counts a person's non-redundant contacts.
- Computed for faculty with at least 3 faculty co-authors (`networkx`).

**Findings:**
- **In this network the brokers are mostly the hubs.**
  - Constraint and number of co-authors are almost perfectly opposite (Spearman ρ = −0.97).
  - 14 of the top 20 brokers are also among the 20 best-connected faculty.
- **Brokers bridge departments.** The median top broker has 43% of co-authors in other departments, against 14% for everyone.
- **There are 5 hidden brokers** who rank in the top 30 for brokerage but not in the top 50 by co-authors: B Venkatesa Perumal, Pathipati Srihari, C Sathiya Narayanan, S Nickolas and Jayabalan P. Their few links connect groups that are otherwise apart.
- **This is the same small group as in the key-person-risk result.** The people who carry spreading (section 1) and the brokers here are largely the same few faculty, so losing them would both split the network and slow how ideas move.

## 6. Can the network fall into one rhythm? (Kuramoto synchronisation)

**Method:**
- **Model:** each faculty member is an oscillator with their own natural frequency ω, drawn from a standard normal distribution: dθᵢ/dt = ωᵢ + K Σⱼ Aᵢⱼ sin(θⱼ − θᵢ).
- **Network:** the largest connected group of each network, with unweighted links.
- **Order parameter:** r = |⟨e^{iθ}⟩|, averaged over 100 time units after a 100-unit transient (Heun steps, dt = 0.05). It runs from 0 (everyone on their own beat) to 1 (one common rhythm).
- **Runs:** 8 frequency draws for each K = 0, 0.1, …, 2.0.
- **Null model:** 3 connected degree-preserving rewired copies, using the same frequencies.
- **Theory:**
  - the onset of synchrony is K_c = 2/(π g(0) λ₁) (Restrepo, Ott & Hunt 2005);
  - full synchrony is easier when the Laplacian eigenratio λ_N/λ₂ is lower.
- **Locked:** a faculty member is locked when their effective frequency is within 0.05 of the mean frequency.
- **How to read it:** this is a model of how easily the network could align (for example, on a shared agenda), not a measurement.

| Network | Faculty | Links | λ₁ | K_c theory | λ₂ | Rewired λ₂ | Eigenratio | Rewired eigenratio | K for r = 0.5 | Rewired | r at K = 1 | Rewired |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| NIT Trichy | 232 | 402 | 6.05 | 0.26 | 0.059 | 0.157 | 259 | 100 | 1.5 | 0.7 | 0.40 | 0.67 |
| NIT Surathkal | 253 | 499 | 7.88 | 0.20 | 0.036 | 0.165 | 565 | 124 | 0.9 | 0.6 | 0.54 | 0.72 |
| Both NITs | 491 | 929 | 8.02 | 0.20 | 0.035 | 0.188 | 670 | 130 | 1.2 | 0.7 | 0.46 | 0.71 |

Share of faculty locked to the common rhythm at K = 1, both NITs, by number of faculty co-authors:

| Co-authors | 1 | 2–3 | 4–9 | 10+ |
|---|---:|---:|---:|---:|
| Locked | 46.5% | 64.4% | 79.9% | 87.5% |

**Findings:**
- **Synchrony starts where theory says.** r begins to rise at K ≈ 0.2–0.3, matching K_c = 0.26 (Trichy) and 0.20 (Surathkal). The onset is set by the hubs through λ₁, like the epidemic threshold in section 1.
- **But the real networks are much harder to bring into one rhythm than random ones.**
  - The eigenratio is 5 times the rewired value (670 vs 130), and λ₂ is 5 times smaller.
  - In the simulations, r reaches 0.5 only at K ≈ 1.2, against 0.7 in rewired copies.
  - Departments synchronise inside but are joined by thin bridges, so they drift apart from each other. This is the same modular structure as in sections 2 and 8.
- **The two NITs differ in opposite ways.**
  - NIT Surathkal reaches partial synchrony sooner (r = 0.5 at K ≈ 0.9 vs 1.5) because of its larger hubs.
  - NIT Trichy has the lower eigenratio (259 vs 565), so full synchrony is easier there. Its groups are less separated, but it has no strong hubs.
- **The core locks first.** At K = 1, 88% of faculty with 10 or more faculty co-authors run at the common rhythm, against 47% of faculty with one.

## 7. Do collaborations last?

**Method:**
- A faculty pair **renews** when it writes together again in a later year.
- OpenAlex gives publication years only, so everything is measured in years.
- Renewal within *h* years uses only pairs that started early enough to be followed for *h* full years (up to 2025). For example, renewal within 3 years uses the 656 pairs that started by 2022.
- **Burstiness** uses the Goh–Barabási measure B = (σ − μ)/(σ + μ) of the gaps between a pair's papers.
  - It is computed for the 232 pairs with 5 or more joint papers.
  - The comparison is the same number of papers placed at random years between the pair's first and last year, 200 times.
- **What predicts renewal:** a logistic regression on renewal within 3 years. The factors are same department, same NIT, first joint papers with FWCI ≥ 1, and the log of the first team's size, with start-year fixed effects.

| Years already active together | Write again within 2 years | Cases |
|---|---:|---:|
| 1 | 50.7% | 751 |
| 2 | 60.8% | 372 |
| 3 | 62.5% | 224 |
| 4 | 62.0% | 137 |
| 5+ | 80.8% | 125 |

| Pairs that started by 2022 | Pairs | Write again within 3 years |
|---|---:|---:|
| Same department | 460 | 63.3% |
| Different departments | 196 | 40.8% |
| First joint papers FWCI ≥ 1 | 328 | 66.5% |
| First joint papers FWCI < 1 | 326 | 46.9% |
| First papers with ≤ 3 authors | 237 | 65.0% |
| 4–6 authors | 371 | 51.8% |
| 7+ authors | 48 | 52.1% |
| Trichy–Surathkal pairs | 16 | 43.8% |

**Findings:**
- **Collaborations usually renew, but the network turns over.**
  - 57% of pairs write together again within 3 years, and 40% the very next year.
  - Of the 313 pairs that started in 2016–2018, only 27% still wrote together in 2023–2025.
- **The longer a pair lasts, the more likely it continues.** A pair after its first year renews within 2 years 51% of the time; after 5 or more active years, 81% of the time. This is how super-ties (section 3) form.
- **Good first papers make pairs stick.**
  - Same-department pairs have 2.6 times the odds of renewing (p < 0.001).
  - Pairs whose first joint papers beat the world average (FWCI ≥ 1) have 2.4 times the odds (p < 0.001), even with department and team size held fixed.
  - A pair first met in a bigger team renews less: the odds fall by about a third (×0.58) each time the first team doubles in size (p = 0.008).
  - Trichy–Surathkal pairs are too few (16) to test.
- **Pairs write steadily, not in bursts.**
  - 74% of the gaps between a pair's active years are a single year; only 11% are comebacks after 3 or more years.
  - Burstiness is no higher than random timing: B = 0.09 against 0.07, p = 0.47.
  - Within a pair's span, they are active in a median of 83% of the years.

## 8. Research groups over time

**Method:**
- **Groups:** Louvain communities with weights and a fixed seed, as in `build_networks.py`. They are found in nine 3-year sliding windows (2016–18, 2017–19, …, 2024–26) of the faculty co-authorship network of both NITs, keeping groups of 3 or more faculty.
- **Matching:** a group continues into the next window when the members overlap by Jaccard ≥ 0.3. It inherits the identity of its best-matching predecessor.
- **Events:** a group with no match is born or dies; one that matches two groups merges or splits.
- **Stability** of a group is the mean Jaccard overlap from one window to the next, as in Palla, Barabási & Vicsek (2007, *Nature*).
- **Label:** a group's main department is simply its largest department, and can change as the members change.

| Window | Groups | Faculty in groups | Largest | Members from the main department | Groups with 2+ departments | Births | Deaths | Merges | Splits |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2016–2018 | 31 | 242 | 26 | 74.5% | 61.3% | | | | |
| 2017–2019 | 29 | 273 | 29 | 77.3% | 65.5% | 5 | 8 | 1 | 2 |
| 2018–2020 | 35 | 304 | 25 | 73.4% | 65.7% | 9 | 5 | 1 | 3 |
| 2019–2021 | 36 | 322 | 25 | 76.8% | 72.2% | 7 | 2 | 4 | 0 |
| 2020–2022 | 42 | 331 | 31 | 81.9% | 54.8% | 10 | 5 | 2 | 3 |
| 2021–2023 | 36 | 338 | 29 | 76.2% | 58.3% | 7 | 13 | 0 | 0 |
| 2022–2024 | 39 | 363 | 35 | 74.6% | 56.4% | 10 | 7 | 2 | 2 |
| 2023–2025 | 37 | 350 | 34 | 74.0% | 59.5% | 8 | 10 | 0 | 0 |
| 2024–2026 | 40 | 321 | 31 | 74.2% | 67.5% | 14 | 11 | 1 | 1 |

**The four groups present in all nine windows:**
- two NIT Trichy EEE groups:
  - P Raja and M P Selvan;
  - K Sundareswaran and Josephine R L;
- a NIT Trichy computing group (S Nickolas, S Mary Saira Bhanu, S Sangeetha);
- a NIT Surathkal civil / mining group (B R Jayalekshmi, Katta Venkataramana, R Shivashankar).

All 22 groups that lasted 5 or more windows are in `groups_lifetimes.csv`.

**Findings:**
- **Groups are many and short-lived.**
  - 112 groups were tracked; 36% exist in only one window.
  - 22 last 5 or more windows (7+ years), and 4 last all nine.
  - Every window has 5–14 births and 2–13 deaths, but at most 4 merges or splits. Groups mostly appear and fade rather than combine.
  - 3–6 groups in each window include faculty from both NITs (for example P Palanisamy of Trichy ECE with Jeny Rajan of Surathkal in 2016–18).
- **Long-lived groups can change identity.** 9 of the 22 groups that lasted 5+ windows changed their main department along the way.
  - The largest example began in 2017–19 as a Surathkal Water Resources group (Amba Shetty, S Shrihari).
  - With Gangadharan K V (Mechanical) as a link in the middle windows, it became a 31-member ECE–CSE group by 2024–26 (Shyam Lal, Raghavendra B S).
- **Groups did not become more mixed.**
  - About 74% of a group's members come from its main department in both the first and the last window.
  - The share of groups with 2 or more departments moves between 55% and 72% with no trend.
  - So the 2018 fusion of the faculty network came from links between groups, not from groups mixing.
- **Large groups survive by keeping their members, the opposite of Palla et al.**
  - Large groups (more than 6.3 members on average) change more from window to window: median stability 0.53, against 0.78 for small groups.
  - But among large groups, the more stable ones live longer (Spearman ρ = 0.45, p = 0.006).
  - For small groups there is no relation (ρ = 0.14, p = 0.43).
  - Palla et al. found that large scientific groups last when they keep changing members. In these two NITs, the lasting large groups are the ones with a stable core.

## What this suggests

| Finding | What to do | Who acts |
|---|---|---|
| Hubs spread ideas twice as far when ideas pass weakly | Start new initiatives (a method, a shared facility, a grant call) with the core faculty, not by circulars | Research office |
| Cross-NIT links barely help spreading | A joint NIT Trichy–NIT Surathkal workshop and seed grants | Deans of research of both NITs |
| Cross-department triangles come from real team projects | Fund three-person cross-department projects rather than pairs | Research office; heads of department |
| 52% of joint output from 11% of pairs | Support durable pairs, and pair each with a newcomer so the knowledge spreads | Heads of department; principal investigators |
| 46% of newcomers isolated after 3 years (52% at Trichy) | Mentoring with a senior co-author and a start-up grant that requires an internal collaborator | Directors; heads of department |
| The network synchronises inside departments but not across them (eigenratio 5× random) | Cross-department seminars and shared facilities, so that departments align rather than only their hubs | Deans of research; heads of department |
| Renewal doubles with a strong first paper and the same department; only 27% of 2016–18 pairs still active | Follow-up seed grants for new pairs whose first joint paper did well, especially across departments | Research office |
| Lasting large groups keep a stable core; groups rarely merge | Fund groups for 5+ years around a stable core, and plan for it before a core member leaves | Directors; heads of department |
| Brokers are the hubs; 5 hidden brokers | Recognise bridging work and plan succession for the key people | Directors; promotion committees |
