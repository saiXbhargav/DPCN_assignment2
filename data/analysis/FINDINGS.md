# Main findings, what they mean, and how they compare with real networks

Every number about our NITs is computed by `scripts/findings.py` from the analysis outputs listed under each finding. The numbers about other networks are quoted from the papers listed at the end. **Phase I** = the original assignment tasks; **Phase II** = the later questions and checks. The dashboard shows the same table at the top of the **Key findings** tab.

## Output and impact

### 1. The two NITs publish the same amount, and output grew fast (Phase I)

- **Numbers:** 9,184 vs 9,206 faculty papers 2016–2026 (47 written together); 1,071 papers in 2016 → 1,924 in 2025 (1.8×).
- **What it means:** Neither NIT is ahead on volume; both grew strongly over the decade.
- **Read with care:** Faculty papers only (science and engineering); students' own papers are counted separately (see below).
- **Evidence:** `data/group12_data.csv`

### 2. No significant difference in impact per paper (Phase I + II)

- **Numbers:** Surathkal vs Trichy, same field, year and venue type: +1.2% FWCI (p = 0.22; p = 0.63 with errors grouped by faculty member); median FWCI 0.63 vs 0.65.
- **What it means:** Once field and year are taken into account, the two NITs' papers have the same impact. Raw citations per paper are higher at Trichy (15.2 vs 13.6) only because raw counts ignore field.
- **Read with care:** Not significant is not the same as proven equal: the clustered 95% interval allows a few per cent either way.
- **Evidence:** `data/analysis/papers/r_fwci_model_sensitivity.csv`

### 3. Surathkal faculty publish more each, mostly because of rank mix (Phase II)

- **Numbers:** median 31 vs 19 papers per faculty member (p = 0.0004); the gap falls from +33% to +24% for people of the same rank; 48% of Trichy's faculty are Assistant Professors vs 31%.
- **What it means:** Trichy has hired many young faculty, who publish less at first. Among Professors the two NITs publish the same (p = 0.71); the gap is only among Assistant and Associate Professors.
- **Read with care:** Rank is today's rank; papers per year use each person's years on the faculty list.
- **Evidence:** `data/analysis/papers/r_papers_per_year_models.csv, r_summary.json`

### 4. The real differences are branch by branch (Phase I + II)

- **Numbers:** after correcting for testing 10 branches, Surathkal is stronger in CSE and EEE, Trichy in Chemical and Mathematics; Q1 share of ranked journal papers 38.3% (Surathkal) vs 35.2%.
- **What it means:** Each NIT has its own strong departments; an institute-level 'winner' hides this.
- **Read with care:** Mechanical (Surathkal) and ECE (Trichy) differ at 5% alone but not after the correction.
- **Evidence:** `data/analysis/ns_branch_fwci_bootstrap.csv, papers/r_false_discovery.csv`

### 5. Foreign collaboration goes with higher impact (Phase II)

- **Numbers:** a foreign co-author goes with +18% FWCI (all papers, same field, year and team size); +15% in the faculty model with clustered errors (p = 0.0001); foreign universities +17% (significant after correction), IITs +3% (not significant).
- **What it means:** International partnerships are where the impact gain is; Indian partners such as IITs and other NITs show no clear gain in impact per paper.
- **Read with care:** An association: stronger groups may be the ones that find foreign partners.
- **Evidence:** `data/analysis/questions/q15_foreign_effect.csv, q16_partner_types.csv`

### 6. Bigger teams, higher impact, but no 'big science' (Phase II)

- **Numbers:** mean FWCI 0.72 (single author) → 1.27 (2–3) → 1.67 (6–9) → 2.09 (10–19 authors); only 1 faculty paper has 20+ authors.
- **What it means:** Impact rises steadily with team size, so large-team papers needed no special correction here.
- **Read with care:** Mean FWCI is pulled up by a few highly cited papers.
- **Evidence:** `data/analysis/papers/e_summary.json`

### 7. AI is spreading to every department, mostly as a method (Phase I)

- **Numbers:** AI papers 9.1% of all in 2016 → 20.3% in 2025; departments with 5%+ AI papers: 10 → 15 of 18.
- **What it means:** AI is becoming a common tool in engineering research at both NITs, not only in computing.
- **Read with care:** AI is found from OpenAlex topics and title words, so some papers are missed or wrongly included.
- **Evidence:** `data/analysis/insights/ai_share_by_year.csv, ai_summary.json`

### 8. Students' own papers add a sixth more output (Phase II)

- **Numbers:** 2,917 papers with no faculty author (21,260 in all, +16%); median FWCI at Trichy 0.63 (students) vs 0.63 (faculty), at Surathkal 0.48 vs 0.65.
- **What it means:** Students publish a lot on their own, at about the faculty level at Trichy and a little lower at Surathkal.
- **Read with care:** Counted only in the publication statistics; networks and rankings stay faculty-only.
- **Evidence:** `data/all_papers.csv`

## The faculty collaboration network

### 9. A small world: short paths and strong clustering (Phase I)

- **Numbers:** average path 6.1 steps (random networks with the same degrees 4.5); average clustering 0.21 vs 0.011 (20× higher); transitivity 0.21.
- **What it means:** Faculty sit in tight groups, yet a few links between groups keep everyone within a few steps.
- **Compared with real networks:** Typical of co-authorship networks: in seven large ones the average distance is 4.0–9.7 and the clustering (transitivity) 0.072–0.726 (Newman 2001). Ours (6.1 and 0.21) falls inside both ranges.
- **Read with care:** Measured in the largest connected group (491 faculty); our network is small and faculty-only, Newman's had thousands of authors.
- **Evidence:** `data/analysis/ns_small_world.csv`

### 10. A giant connected group holds three quarters of the faculty (Phase I)

- **Numbers:** 75% of the 657 faculty are in one connected group (540 have at least one faculty co-author).
- **What it means:** Most faculty are linked, directly or through colleagues, across departments and the two NITs.
- **Compared with real networks:** Real co-authorship networks have giant components of 57–89% (Newman 2001).
- **Read with care:** Faculty with no faculty co-author still have outside co-authors.
- **Evidence:** `data/analysis/insights/growth_by_year.csv`

### 11. No clean power law in the degree distributions (Phase I)

- **Numbers:** a log-normal fits better than a power law for 4 of 4 degree and citation distributions (heavy tails, α ≈ 2.5–2.9).
- **What it means:** A few people have many co-authors, but the network is not 'scale-free'.
- **Compared with real networks:** Newman (2001) also found that collaboration networks are not pure power laws: their degree distributions have a cut-off.
- **Read with care:** Fits use the powerlaw package (Clauset, Shalizi & Newman method).
- **Evidence:** `data/analysis/ns_degree_fits.csv`

### 12. Well-connected faculty work with each other (assortative) (Phase I + II)

- **Numbers:** degree assortativity r = 0.20 vs −0.02 in rewired networks (z = 6.9); by branch r = 0.66, by NIT r = 0.94, by rank only 0.07.
- **What it means:** Hubs link to hubs, people stay in their branch and NIT, and rank matters little.
- **Compared with real networks:** This is the usual pattern of social networks: co-authorship networks have r = 0.12–0.36, while technological and biological networks are disassortative (Newman 2002).
- **Read with care:** Rank assortativity is weak but above chance (z ≈ 4).
- **Evidence:** `data/analysis/phase2/assortativity_degree.csv, ns_assortativity.csv`

### 13. The two NITs barely collaborate (Phase I)

- **Numbers:** 28 of 961 faculty links (2.9%) join Trichy and Surathkal; 47 joint papers in ten years.
- **What it means:** Two similar NITs work almost entirely apart; there is room for joint projects.
- **Evidence:** `data/analysis/insights/growth_by_year.csv`

### 14. A few people hold the network together (Phase II)

- **Numbers:** removing the 10 main bridge faculty disconnects 54% (Trichy) and 44% (Surathkal) of connected faculty pairs, against 8% and 10% for 10 random departures.
- **What it means:** Robust to random loss, fragile to losing its bridges: when key people retire or move, groups can split.
- **Read with care:** A what-if on the 2016–2026 network; real people are replaced over time.
- **Evidence:** `data/analysis/questions/network_summary.json`

## How the network grows, and predicting it

### 15. The network densifies: links grow faster than people (Phase I + II)

- **Numbers:** links ∝ (connected faculty)^a with a = 1.65 (R² = 0.998); the same exponent at the six South Indian NITs is 1.19–1.74.
- **What it means:** Each faculty member gains co-authors over time, so the average number of co-authors keeps rising.
- **Compared with real networks:** Real growing networks densify the same way, with a = 1.08–1.68 (citation graphs 1.56 and 1.68, US patents 1.66, internet routers 1.18, author–paper graphs 1.08–1.15; Leskovec et al. 2005). Ours and five of the six NITs are inside this range; Surathkal is just above it.
- **Read with care:** With every author counted (students too) a falls to about 1.2, so strong densification is a property of the closed faculty group.
- **Evidence:** `data/analysis/insights/insights_summary.json, south/s_six_nits.csv`

### 16. Distances shrink as the network grows (Phase I + II)

- **Numbers:** effective diameter 19 steps in 2018 → 9; average path in the largest group 11.2 → 6.1; co-authors per connected faculty member 1.67 → 3.48, but within any one year only 1.7–2.0.
- **What it means:** The giant group formed in 2018 through thin bridges (long paths); new links then acted as shortcuts. People do not write with more colleagues each year; the totals rise because old links stay.
- **Compared with real networks:** Leskovec et al. (2005) found shrinking diameters in real growing networks, largest when the giant component first appears; Barabási et al. (2002) found that in co-authorship networks the separation falls and the average degree rises over time.
- **Read with care:** Counts are cumulative from 2016, so early years are short of history.
- **Evidence:** `data/analysis/insights/growth_by_year.csv, growth/g_average_degree_by_year.csv`

### 17. Rich get richer: weak for collaborators, stronger for citations (Phase II)

- **Numbers:** new faculty co-authors ∝ (current co-authors)^0.35 (Trichy 0.26, Surathkal 0.32); new citations ∝ (current citations)^0.75.
- **What it means:** Well-connected faculty gain new collaborators only a little faster than others; highly cited papers gain citations much faster.
- **Compared with real networks:** Barabási et al. (2002) measured a stronger attachment for co-authorship, k^0.8 (mathematics) and k^0.75 (neuroscience). Our collaborator effect is weaker; our citation effect is close to theirs.
- **Read with care:** Busier people may simply write more papers; the fits are pooled over years.
- **Evidence:** `data/analysis/growth/k_summary.json, questions/richer_summary.json`

### 18. Friends of friends become co-authors, but most new links are new contacts (Phase I)

- **Numbers:** pairs with one common co-author start working together 19× more often than distant pairs; yet only 104 of 788 new links (13%) closed a triangle (2017–2025).
- **What it means:** Common colleagues matter, but most new collaborations start between people with no shared co-author, usually in the same department.
- **Read with care:** Observational: we did not test introductions.
- **Evidence:** `data/analysis/insights/triadic_closure_by_common_coauthors.csv`

### 19. New collaborations can be predicted, but exact hits are rare (Phase II)

- **Numbers:** a model trained once on 2016–2022 and given only the 2022 network: AUC 0.90 / 0.87 / 0.90 for 2023, 2024, 2025; its top 1% of pairs (about 1,569) holds 19 / 14 / 9 of the real new pairs, 15–22× better than random (42 correct matches listed).
- **What it means:** Who will work together next is fairly predictable (same department, active people, common colleagues), but only about 1 candidate pair in 2,000 starts each year, so most predicted pairs do not happen yet.
- **Compared with real networks:** Real co-authorship networks behave the same: a random prediction is right 0.15–0.48% of the time and the best methods do up to about 55× better than random, with low raw precision (Liben-Nowell & Kleinberg 2007).
- **Read with care:** Their task used only well-connected authors; ours scores all faculty pairs. New faculty (27% of 2025's new pairs) are invisible to a 2022 model.
- **Evidence:** `data/analysis/growth/p_link_prediction.csv, p_fixed_correct_matches.csv`

## How things move through the network: theory vs simulation

### 20. Ideas spread more easily at Surathkal, as the theory predicts (Phase II)

- **Numbers:** SIR epidemic threshold β_c = 1/λ_NB = 0.211 (Trichy) and 0.156 (Surathkal); simulated reach from 5 random starters at β = 0.1 / 0.2 / 0.3: Trichy 1.9 / 3.9 / 10.1%, Surathkal 2.8 / 8.4 / 24.8%.
- **What it means:** Spreading takes off between β = 0.2 and 0.3 at Trichy and around 0.15–0.2 at Surathkal, where the theory puts the thresholds; Surathkal's bigger, connected hubs raise λ and so lower its threshold.
- **Compared with real networks:** The threshold formula for SIR on real networks is the non-backtracking one (Karrer, Newman & Zdeborová 2014); worked out step by step in our PDF.
- **Read with care:** In a small network the take-off is gradual, not a sharp jump.
- **Evidence:** `data/analysis/dynamics/spread_simulations.csv, dashboard/docs/threshold_calculations.pdf`

### 21. Synchrony starts where theory says, but full synchrony is hard (Phase II)

- **Numbers:** onset K_c = K₀/λ₁ = 0.264 (Trichy) and 0.203 (Surathkal); simulated order parameter r at K = 0.2 / 0.3 / 0.4: Trichy 0.08 / 0.11 / 0.16, Surathkal 0.11 / 0.15 / 0.24 (noise level about 0.06); Laplacian eigenratio 670 vs 130 in rewired networks.
- **What it means:** Partial synchrony begins as predicted, but groups are joined by thin bridges, so the whole network is about 5× harder to bring into one rhythm than a random one.
- **Compared with real networks:** The onset formula is Restrepo, Ott & Hunt (2005); details in our PDF.
- **Read with care:** Unweighted network, normal frequencies; synchrony inside departments was not measured.
- **Evidence:** `data/analysis/dynamics/sync_summary.csv, dashboard/docs/threshold_calculations.pdf`

### 22. Many collaborations renew, but few last the whole decade (Phase II)

- **Numbers:** 57% of faculty pairs write together again within 3 years; only 27% of the pairs that started in 2016–2018 were still active in 2023–2025.
- **What it means:** Partnerships are durable in the short run but turn over across a decade; same-department pairs and pairs with a strong first paper renew more.
- **Read with care:** Observational.
- **Evidence:** `data/analysis/dynamics/ties_summary.json`

## Citations

### 23. Most citations between our own papers are self-citations, at every NIT (Phase II)

- **Numbers:** 86% of the 23,822 citations between our papers share an author; without them none of the old top-10 PageRank papers stays in the top 10; the share is 85–92% at all six South Indian NITs.
- **What it means:** The internal citation network mainly shows groups building on their own work, so PageRank inside it is not a measure of influence.
- **Read with care:** Compared across our six NITs only (no published benchmark). Citing your own earlier work is normal when it is relevant.
- **Evidence:** `data/analysis/papers/s_summary.json, south/s_six_nits.csv`

### 24. Private universities cite us as much as their size predicts, more often through people close to us (Phase II)

- **Numbers:** 43 vs 37 citations per 1,000 of their papers (p = 0.28); 31% vs 21% of their citations come from people within 3 co-authorship steps.
- **What it means:** High citation counts from private universities mainly reflect their size; a somewhat larger share comes from people close to the cited authors (former students and co-authors).
- **Read with care:** At the level of the 40 institutes only the 'earlier co-author' share stays different after correction.
- **Evidence:** `data/analysis/phase2/citers_private_vs_public.csv, papers/a_summary.json`

### 25. No sign that citation manipulation changes the ranking (Phase II)

- **Numbers:** 5.0% of 117,909 Indian citations come from papers citing 10+ of ours; the top-20 faculty ranking is unchanged without self-citations (Spearman 0.999).
- **What it means:** One local cluster (around one Surathkal Mechanical group, 2023–24, mostly former NIT members) exists, but it does not move the ranking.
- **Read with care:** A statistical signal for follow-up, not a judgement about anyone.
- **Evidence:** `data/analysis/questions/manipulation_summary.json`

### 26. People collaborate locally, but knowledge travels far (Phase I)

- **Numbers:** 37% of joint papers but 16% of citations are within 300 km; doubling the distance cuts joint papers by 38% and citations by 11% (partner size held fixed).
- **What it means:** Working together needs closeness; reading each other's work does not.
- **Read with care:** Indian partners only; distances between cities.
- **Evidence:** `data/analysis/insights/geo_summary.json`

## The six South Indian NITs

### 27. Every South Indian NIT densifies; recent hiring goes with a lower exponent, but the evidence is thin (Phase II)

- **Numbers:** a = 1.19–1.74 at the six NITs; share hired in 2021–25 against a: ρ = −1.00 (exact p = 0.003, n = 6); with a second, independently cleaned dataset for Warangal and Calicut ρ = −0.60 (p = 0.24).
- **What it means:** Every NIT's faculty network densifies like a real growing network. NITs that hired more recently tend to have lower exponents, but with six NITs this is a pattern, not a law.
- **Compared with real networks:** All exponents lie near the 1.08–1.68 range of real growing networks (Leskovec et al. 2005).
- **Read with care:** Recent hiring, a young NIT and many Assistant Professors go together; inside single NITs the link is not consistent.
- **Evidence:** `data/analysis/south/south_summary.json, s_six_nits.csv, s_second_dataset_vs_ours.csv`

### 28. Papers per head follow the rank mix at every NIT (Phase II)

- **Numbers:** papers in 2024 per faculty member (all current staff): Trichy 3.4, Surathkal 4.7, Warangal 4.2, Calicut 2.4, Puducherry 4.4, Andhra Pradesh 2.0; share of Assistant Professors: 47%, 30%, 35%, 65%, 70%, 98%.
- **What it means:** Senior-heavy NITs publish more per head; young NITs and NITs that hired recently publish less per head.
- **Read with care:** Andhra Pradesh has many ad hoc and contract staff; per regular faculty member it is the highest.
- **Evidence:** `data/analysis/south/s_six_nits.csv`

## Sources for the comparisons

- Leskovec, Kleinberg & Faloutsos 2005: https://doi.org/10.1145/1081870.1081893
- Newman 2001 (PNAS): https://doi.org/10.1073/pnas.98.2.404
- Barabási et al. 2002: https://doi.org/10.1016/S0378-4371(02)00736-7
- Newman 2002 (PRL): https://doi.org/10.1103/PhysRevLett.89.208701
- Liben-Nowell & Kleinberg 2007: https://doi.org/10.1002/asi.20591
- Karrer, Newman & Zdeborová 2014: https://doi.org/10.1103/PhysRevLett.113.208702
- Restrepo, Ott & Hunt 2005: https://doi.org/10.1103/PhysRevE.71.036151
- our threshold calculations (PDF): dashboard/docs/threshold_calculations.pdf
