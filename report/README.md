# DPCN Assignment 2 report (Group 12)

The statistics report for Task 4 and the Phase II analyses, written in LaTeX. The limit is **at most 10 pages**; the report is 8 pages (20 figures, 12 tables, a Methods section with the formulas).

```text
report/
├── main.tex                                   # the report text (edit this)
├── numbers.tex                                # every number used in the text, as LaTeX macros (generated)
├── figures/                                   # 19 figures (generated, vector PDF; the pipeline diagram is drawn in main.tex)
├── tables/                                    # booktabs tables (generated)
├── Group12_NITTrichy_NITSurathkal_Report.pdf  # the compiled report
└── Group12_NITTrichy_NITSurathkal.pptx        # the first 10-slide version (Phase I, 20 Oct 2026)
```

`numbers.tex`, `figures/` and `tables/` are written by `scripts/build_report.py` from the analysis outputs, so the report always
matches the dashboard and `data/analysis/FINDINGS.md`. Do not edit them by hand; re-run the script after changing an analysis.

## Build

```
cd scripts
python build_report.py            # writes the generated files and compiles with Tectonic (TECTONIC=path\to\tectonic.exe or on PATH)
python build_report.py --no-pdf   # only the generated files
```

**Overleaf:** upload the whole `report/` folder and set *Menu → Compiler → XeLaTeX* (the report uses `fontspec` with TeX Gyre Termes).
