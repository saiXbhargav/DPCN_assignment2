"""Builds dashboard/docs/threshold_calculations.pdf: how the spreading (SIR) and Kuramoto thresholds are calculated,
with every number computed here from the faculty co-authorship network.

  python threshold_note.py

Needs the outputs of dynamics.py (spread and sync parts) and Google Chrome or Microsoft Edge to print the PDF.
The formulas are typeset with KaTeX (loaded from cdn.jsdelivr.net), so printing needs an internet connection.
"""
import base64
import io
import os
import shutil
import subprocess
import tempfile
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dynamics as d   # noqa: E402

DY = os.path.join(d.DATA, "analysis", "dynamics")
OUT_DIR = os.path.join(d.ROOT, "dashboard", "docs")
HTML = os.path.join(tempfile.gettempdir(), "threshold_note.html")   # build step only; the PDF is the output
PDF = os.path.join(OUT_DIR, "threshold_calculations.pdf")
NAMES = {"NIT Trichy": "Trichy", "NIT Surathkal": "Surathkal", None: "Both NITs"}


def numbers(X):
    k = np.array([X.degree(u) for u in X], dtype=float)
    n = X.number_of_nodes()
    A = nx.to_numpy_array(X, weight=None)
    lam = float(np.linalg.eigvalsh(A)[-1])
    B = np.block([[A, np.eye(n) - np.diag(k)], [np.eye(n), np.zeros((n, n))]])   # Ihara-Bass
    lnb = float(max(abs(np.linalg.eigvals(B))))
    k1, k2 = k.mean(), np.mean(k ** 2)
    return {"n": n, "m": X.number_of_edges(), "k1": k1, "k2": k2, "kmax": int(k.max()), "lam": lam, "lnb": lnb,
            "b_lam": 1 / lam, "b_nb": 1 / lnb, "b_hmf": k1 / (k2 - k1), "excess": k2 / k1 - 1}


def png(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=170, bbox_inches="tight")
    plt.close(fig)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def main():
    fe, fac, pairs = d.load()
    S, L = {}, {}
    for nit in d.NITS + [None]:
        G = d.graph(pairs, fac, nit)
        S[nit] = numbers(G.subgraph([u for u in G if G.degree(u) > 0]))   # spreading: every linked faculty member
        L[nit] = numbers(d.lcc(G))                                         # Kuramoto: largest connected group
    g0 = 1 / np.sqrt(2 * np.pi)
    K0 = 2 / (np.pi * g0)
    sync = pd.read_csv(os.path.join(DY, "sync_summary.csv")).set_index("network")
    sims = pd.read_csv(os.path.join(DY, "spread_simulations.csv"))
    curves = pd.read_csv(os.path.join(DY, "sync_curves.csv"))
    T, U = S["NIT Trichy"], S["NIT Surathkal"]
    LT, LU, LB = L["NIT Trichy"], L["NIT Surathkal"], L[None]

    # figure 1: simulated reach against the three thresholds
    fig, axs = plt.subplots(1, 2, figsize=(10, 3.3), sharey=True)
    for ax, nit, c in ((axs[0], "NIT Trichy", "#2f6fdb"), (axs[1], "NIT Surathkal", "#e8692f")):
        x = sims[(sims.network == nit) & (sims.seeds == "random 5")].sort_values("beta")
        ax.plot(x.beta, x.mean_reach_pct, "o-", color=c, lw=2, label="simulation (5 random seeds, 500 runs)")
        for v, ls, lab in ((S[nit]["b_lam"], ":", r"$1/\lambda_1$ (SIS bound)"), (S[nit]["b_nb"], "-", r"$1/\lambda_{NB}$ (SIR)"),
                           (S[nit]["b_hmf"], "--", r"mean-field $\langle k\rangle/(\langle k^2\rangle-\langle k\rangle)$")):
            ax.axvline(v, color="#444", ls=ls, lw=1.2, label=f"{lab} = {v:.3f}")
        ax.set_title(nit); ax.set_xlabel(r"transmission probability $\beta$"); ax.grid(alpha=0.3); ax.legend(fontsize=7.5, loc="upper left")
    axs[0].set_ylabel("faculty reached (%)")
    fig1 = png(fig)

    # figure 2: Kuramoto order parameter against the predicted onset
    fig, ax = plt.subplots(figsize=(10, 3.6))
    for nit, c in (("NIT Trichy", "#2f6fdb"), ("NIT Surathkal", "#e8692f")):
        x = curves[(curves.network == nit) & (curves.graph == "real")].sort_values("K")
        ax.plot(x.K, x.r_mean, "o-", color=c, ms=3.5, lw=2, label=f"{nit}: simulation")
        ax.axvline(K0 / L[nit]["lam"], color=c, ls="--", lw=1.2, label=fr"{nit}: $K_c = K_0/\lambda_1$ = {K0 / L[nit]['lam']:.3f}")
        ax.axhline(1 / np.sqrt(L[nit]["n"]), color=c, ls=":", lw=1, label=fr"{nit}: noise level $1/\sqrt{{n}}$ = {1 / np.sqrt(L[nit]['n']):.3f}")
    ax.set_xlim(0, 1.2); ax.set_ylim(0, 0.6); ax.set_xlabel("coupling $K$"); ax.set_ylabel("order parameter $r$")
    ax.grid(alpha=0.3); ax.legend(fontsize=7.5, loc="upper left")
    fig2 = png(fig)

    reach = lambda nit, b: float(sims[(sims.network == nit) & (sims.seeds == "random 5") & (sims.beta == b)].mean_reach_pct.iloc[0])
    rK = lambda nit, K: float(curves[(curves.network == nit) & (curves.graph == "real") & (curves.K.round(2) == K)].r_mean.iloc[0])
    f = lambda x, p=3: f"{x:.{p}f}"

    def srow(nit):
        s = S[nit]
        return (f"<tr><td>{NAMES[nit]}</td><td>{s['n']}</td><td>{s['m']}</td><td>{f(s['k1'], 2)}</td><td>{f(s['k2'], 2)}</td>"
                f"<td>{s['kmax']}</td><td>{f(s['lam'])}</td><td>{f(s['lnb'])}</td></tr>")

    def trow(nit):
        s = S[nit]
        return (f"<tr><td>{NAMES[nit]}</td><td>{f(s['b_lam'])}</td><td class='key'>{f(s['b_nb'])}</td><td>{f(s['b_hmf'])}</td></tr>")

    def krow(nit):
        s, y = L[nit], sync.loc[NAMES[nit] if nit is None else nit]
        return (f"<tr><td>{NAMES[nit]}</td><td>{s['n']}</td><td>{f(s['lam'])}</td><td class='key'>{f(K0 / s['lam'])}</td>"
                f"<td>{f(s['k1'], 2)}</td><td>{f(s['k2'], 2)}</td><td>{f(K0 * s['k1'] / s['k2'])}</td></tr>")

    def erow(nit):
        y = sync.loc[NAMES[nit] if nit is None else nit]
        return (f"<tr><td>{NAMES[nit]}</td><td>{f(y.lambda_2)}</td><td>{f(y.rewired_lambda_2)}</td>"
                f"<td class='key'>{y.eigenratio:.0f}</td><td>{y.rewired_eigenratio:.0f}</td></tr>")

    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Spreading and synchronisation thresholds</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css">
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"></script>
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/contrib/auto-render.min.js"
  onload="renderMathInElement(document.body,{{delimiters:[{{left:'$$',right:'$$',display:true}},{{left:'$',right:'$',display:false}}]}});document.body.dataset.ready=1"></script>
<style>
@page {{ size: A4; margin: 12mm 14mm 12mm 14mm; }}
body {{ font-family: "Segoe UI", Arial, sans-serif; font-size: 10.5pt; line-height: 1.45; color: #1d2433; }}
h1 {{ font-size: 19pt; margin: 0 0 2px; color: #14213d; }}
.sub {{ color: #5b6475; margin: 0 0 14px; }}
h2 {{ font-size: 14pt; color: #fff; background: #14213d; padding: 5px 10px; border-radius: 4px; margin: 20px 0 8px; break-after: avoid; }}
h3 {{ font-size: 11.5pt; color: #14213d; margin: 14px 0 4px; border-bottom: 1px solid #d5dae3; padding-bottom: 2px; break-after: avoid; }}
p {{ margin: 4px 0 6px; }}
.eq {{ background: #fff6dc; border: 1.5px solid #e0a800; border-left: 6px solid #e0a800; border-radius: 5px;
       padding: 4px 14px; margin: 8px 0; break-inside: avoid; position: relative; }}
.eq .tag {{ position: absolute; top: 4px; right: 10px; font-size: 8.5pt; font-weight: 700; color: #a77b00; }}
.eq .katex-display {{ margin: 6px 0; }}
.work {{ background: #eef4ff; border-left: 6px solid #2f6fdb; border-radius: 5px; padding: 6px 14px; margin: 8px 0; break-inside: avoid; }}
.work b {{ color: #1f4fa8; }}
.result {{ background: #e9f7ef; border: 1.5px solid #2e9e5b; border-left: 6px solid #2e9e5b; border-radius: 5px; padding: 6px 14px; margin: 10px 0; break-inside: avoid; }}
.warn {{ background: #fdecec; border-left: 6px solid #d64545; border-radius: 5px; padding: 6px 14px; margin: 8px 0; break-inside: avoid; }}
table {{ border-collapse: collapse; margin: 6px 0 8px; font-size: 9.5pt; break-inside: avoid; }}
th, td {{ border: 1px solid #cdd3de; padding: 3px 8px; text-align: right; }}
th {{ background: #f0f2f6; }} td:first-child, th:first-child {{ text-align: left; }}
td.key {{ background: #fff6dc; font-weight: 700; }}
ol, ul {{ margin: 4px 0 6px 18px; padding: 0; }} li {{ margin: 2px 0; }}
img {{ width: 100%; break-inside: avoid; }}
.small {{ font-size: 8.8pt; color: #5b6475; }}
.pb {{ break-before: page; }}
</style></head><body>

<h1>How the spreading and synchronisation thresholds are calculated</h1>
<p class="sub">DPCN Team 12 · Faculty co-authorship network of NIT Trichy and NIT Surathkal, 2016–2026 ·
every number below is computed from the network by <code>scripts/threshold_note.py</code>
(simulations: <code>scripts/dynamics.py</code>)</p>

<p><b>The network.</b> Nodes are faculty members; two faculty are linked if they wrote at least one paper together
(papers with more than 50 authors are excluded). Links are unweighted:</p>
<div class="eq"><span class="tag">(0)</span>$$A_{{ij}} = \\begin{{cases}} 1 & \\text{{if faculty }} i \\text{{ and }} j \\text{{ co-authored a paper}}\\\\ 0 & \\text{{otherwise}} \\end{{cases}}
\\qquad k_i=\\sum_j A_{{ij}},\\quad \\langle k\\rangle=\\tfrac1n\\sum_i k_i,\\quad \\langle k^2\\rangle=\\tfrac1n\\sum_i k_i^2$$</div>
<table><tr><th>Network (faculty with ≥ 1 faculty co-author)</th><th>$n$</th><th>links</th><th>$\\langle k\\rangle$</th><th>$\\langle k^2\\rangle$</th><th>$k_{{max}}$</th><th>$\\lambda_1$</th><th>$\\lambda_{{NB}}$</th></tr>
{srow("NIT Trichy")}{srow("NIT Surathkal")}{srow(None)}</table>
<p class="small">$\\lambda_1$ = largest eigenvalue of $A$; $\\lambda_{{NB}}$ = largest eigenvalue of the non-backtracking matrix (formula A4).</p>

<h2>Part A · Spreading of an idea (SIR model)</h2>

<h3>A.1 The simulation</h3>
<p>Every faculty member is <b>S</b> (has not heard the idea), <b>I</b> (has just heard it) or <b>R</b> (has passed it on and is done).</p>
<ol>
<li>Start with 5 faculty in state I (the 5 best-connected, the 5 best bridges, or 5 random faculty).</li>
<li>Each I person gets <b>one chance</b> to pass the idea to each S co-author, succeeding with probability $\\beta$; then becomes R.</li>
<li>Repeat with the newly infected until nobody new is infected; record the share of faculty reached.</li>
<li>Average over 500 runs, for $\\beta$ = 0.05, 0.1, 0.2, 0.3, 0.5.</li>
</ol>
<p>Because nobody can be infected twice, this is SIR with transmissibility $\\beta$ (the independent-cascade form).
The question is: <b>above which $\\beta$ does the idea take off?</b> Three ways to estimate it follow.</p>

<h3>A.2 Estimate 1 — counting co-authors (heterogeneous mean-field)</h3>
<p>A person who receives the idea was reached through a link. People reached through a link have, on average,
$\\langle k^2\\rangle/\\langle k\\rangle$ co-authors (well-connected people are reached more often). One of those co-authors
infected them, so they can pass it to $\\langle k^2\\rangle/\\langle k\\rangle-1$ new people. Each infection therefore makes</p>
<div class="eq"><span class="tag">(A1)</span>$$R \\;=\\; \\beta\\left(\\frac{{\\langle k^2\\rangle}}{{\\langle k\\rangle}}-1\\right)
\\qquad\\text{{new infections; the idea takes off when }} R>1:\\qquad
\\boxed{{\\;\\beta_c^{{\\,MF}} = \\frac{{\\langle k\\rangle}}{{\\langle k^2\\rangle-\\langle k\\rangle}}\\;}}$$</div>
<div class="work"><b>NIT Trichy:</b> $\\langle k^2\\rangle/\\langle k\\rangle = {f(T['k2'])}/{f(T['k1'])} = {f(T['k2'] / T['k1'], 2)}$,
so each new case has ${f(T['excess'], 2)}$ new people to reach and $\\beta_c^{{MF}} = 1/{f(T['excess'], 2)} = \\mathbf{{{f(T['b_hmf'])}}}$.<br>
<b>NIT Surathkal:</b> ${f(U['k2'])}/{f(U['k1'])} = {f(U['k2'] / U['k1'], 2)}$, so $\\beta_c^{{MF}} = 1/{f(U['excess'], 2)} = \\mathbf{{{f(U['b_hmf'])}}}$.<br>
Surathkal's threshold is lower because its co-author counts are more unequal (bigger hubs, larger $\\langle k^2\\rangle$).</div>

<h3>A.3 Estimate 2 — the real wiring (largest eigenvalue)</h3>
<p>Estimate 1 keeps only the co-author counts. To use who is linked to whom: the number of walks of length $\\ell$ in the network
grows like $\\lambda_1^{{\\ell}}$, and an infection survives a walk of length $\\ell$ with probability $\\beta^{{\\ell}}$. The expected
spread grows like $(\\beta\\lambda_1)^{{\\ell}}$, so</p>
<div class="eq"><span class="tag">(A2)</span>$$\\sum_j A_{{ij}}\\,x_j=\\lambda_1 x_i \\qquad\\Longrightarrow\\qquad
\\text{{spread}}\\;\\propto\\;(\\beta\\lambda_1)^{{\\ell}} \\qquad\\Longrightarrow\\qquad \\boxed{{\\;\\beta_c^{{\\,\\lambda}} = \\frac{{1}}{{\\lambda_1}}\\;}}$$</div>
<div class="work"><b>Trichy:</b> $\\lambda_1 = {f(T['lam'])}$, so $1/\\lambda_1 = \\mathbf{{{f(T['b_lam'])}}}$.
&nbsp;&nbsp;<b>Surathkal:</b> $\\lambda_1 = {f(U['lam'])}$, so $1/\\lambda_1 = \\mathbf{{{f(U['b_lam'])}}}$.<br>
<b>Intuition (a star):</b> one hub with $k$ co-authors who do not know each other has $\\lambda_1=\\sqrt{{k}}$. Surathkal's biggest hub
($k={U['kmax']}$) alone would give $\\sqrt{{{U['kmax']}}}={f(np.sqrt(U['kmax']), 2)}$; the real $\\lambda_1={f(U['lam'], 2)}$ is larger, so a connected
core of hubs drives spreading, not one person.</div>

<div class="warn"><b>Why $1/\\lambda_1$ is too low for our model.</b> A walk may step back along the link it just used
($i\\to j\\to i$). In SIS (people can be reinfected) that is allowed, and $1/\\lambda_1$ is the right threshold. In our SIR model
the person who infected you is already done, so those walks cannot carry the infection: $1/\\lambda_1$ is only a
<b>lower bound</b>. <i>Toy check:</i> if everyone had exactly $k=4$ co-authors, $\\lambda_1=4$ gives $1/4=0.25$, but each infected
person really has only $k-1=3$ new people to reach, so the SIR threshold is $1/3\\approx0.33$.</div>

<h3>A.4 Estimate 3 — the real wiring without stepping back (non-backtracking matrix)</h3>
<p>Count only walks that never go straight back along the link they arrived by. The matrix $B$ of such steps (one row and column
per direction of each link, $2m\\times2m$) has the same leading eigenvalue as a $2n\\times2n$ matrix (Ihara–Bass), which is how we compute it:</p>
<div class="eq"><span class="tag">(A3)</span>$$B_{{(i\\to j),(k\\to l)}} = \\delta_{{jk}}\\,(1-\\delta_{{il}})
\\qquad\\qquad \\lambda_{{NB}} = \\text{{largest }}|\\text{{eigenvalue}}| \\text{{ of }}
\\begin{{pmatrix}} A & I-D \\\\ I & 0 \\end{{pmatrix}},\\quad D=\\operatorname{{diag}}(k_i)$$</div>
<div class="eq"><span class="tag">(A4)</span>$$\\boxed{{\\;\\beta_c^{{\\,SIR}} = \\frac{{1}}{{\\lambda_{{NB}}}}\\;}}
\\qquad\\text{{(Karrer, Newman \\& Zdeborová 2014)}}$$</div>
<div class="work"><b>Trichy:</b> $\\lambda_{{NB}} = {f(T['lnb'])}$, so $\\beta_c = 1/{f(T['lnb'])} = \\mathbf{{{f(T['b_nb'])}}}$.
&nbsp;&nbsp;<b>Surathkal:</b> $\\lambda_{{NB}} = {f(U['lnb'])}$, so $\\beta_c = 1/{f(U['lnb'])} = \\mathbf{{{f(U['b_nb'])}}}$.</div>

<h3>A.5 The three estimates against the simulation</h3>
<table><tr><th>Network</th><th>$1/\\lambda_1$ (SIS, lower bound)</th><th>$1/\\lambda_{{NB}}$ (SIR)</th><th>mean-field (A1)</th></tr>
{trow("NIT Trichy")}{trow("NIT Surathkal")}{trow(None)}</table>
<img src="{fig1}" alt="Simulated reach against the thresholds">
<div class="result"><b>Result.</b> With 5 random starters, NIT Trichy reaches {reach("NIT Trichy", 0.1):.1f}% → {reach("NIT Trichy", 0.2):.1f}% → {reach("NIT Trichy", 0.3):.1f}%
of its faculty at $\\beta$ = 0.1, 0.2, 0.3: it takes off between 0.2 and 0.3, as $1/\\lambda_{{NB}}={f(T['b_nb'])}$ and the mean-field ${f(T['b_hmf'])}$ predict.
NIT Surathkal ({reach("NIT Surathkal", 0.1):.1f}% → {reach("NIT Surathkal", 0.2):.1f}% → {reach("NIT Surathkal", 0.3):.1f}%) takes off earlier, around 0.15–0.2
($1/\\lambda_{{NB}}={f(U['b_nb'])}$). Theory and simulation agree that <b>ideas spread more easily at Surathkal</b>. In a finite network the take-off
is gradual, not a sharp jump.</div>

<h2 class="pb">Part B · Synchronisation (Kuramoto model)</h2>

<h3>B.1 The model</h3>
<p>Every faculty member is an oscillator with phase $\\theta_i$ and natural frequency $\\omega_i$, pulled towards their co-authors:</p>
<div class="eq"><span class="tag">(B1)</span>$$\\frac{{d\\theta_i}}{{dt}} \\;=\\; \\omega_i \\;+\\; K\\sum_{{j}} A_{{ij}}\\,\\sin(\\theta_j-\\theta_i),
\\qquad \\omega_i \\sim \\mathcal N(0,1)$$</div>
<p>$K$ is the coupling strength. The network is the <b>largest connected group</b> of each NIT (isolated groups can never join a common
rhythm). How synchronised everyone is, is measured by the order parameter</p>
<div class="eq"><span class="tag">(B2)</span>$$r\\,e^{{i\\psi}} \\;=\\; \\frac1n\\sum_{{j=1}}^{{n}} e^{{i\\theta_j}},\\qquad
0\\le r\\le 1$$</div>
<p>$r=0$: everyone on their own beat; $r=1$: one common rhythm.</p>
<p><b>Simulation:</b> Heun (improved Euler) steps with $dt=0.05$; 100 time units to settle, then $r$ averaged over the next 100;
8 frequency draws for every $K=0,0.1,\\dots,2.0$; compared with 3 connected degree-preserving rewired copies.</p>

<h3>B.2 Where synchrony starts — theory</h3>
<p><b>All-to-all (classic Kuramoto):</b> with a frequency distribution $g(\\omega)$, synchrony starts at</p>
<div class="eq"><span class="tag">(B3)</span>$$K_0 = \\frac{{2}}{{\\pi\\,g(0)}},\\qquad g(0)=\\frac{{1}}{{\\sqrt{{2\\pi}}}}={f(g0, 4)}\\ \\text{{for }}\\mathcal N(0,1)
\\quad\\Longrightarrow\\quad K_0=\\frac{{2}}{{\\pi\\times{f(g0, 4)}}}=\\mathbf{{{f(K0, 3)}}}$$</div>
<p><b>On a network</b> (Restrepo, Ott &amp; Hunt 2005): each node feels a local field from its own co-authors,
$u_i=\\sum_j A_{{ij}}\\langle e^{{i\\theta_j}}\\rangle$. Just above the onset this field is small and obeys the linear equation</p>
<div class="eq"><span class="tag">(B4)</span>$$u_i = \\frac{{K}}{{K_0}}\\sum_j A_{{ij}}\\,u_j
\\qquad\\text{{which first has a non-zero solution when }}\\ \\frac{{K\\lambda_1}}{{K_0}}=1:\\qquad
\\boxed{{\\;K_c=\\frac{{K_0}}{{\\lambda_1}}\\;}}$$</div>
<p>(The same $\\lambda_1$ as in the spreading threshold A2.) A cruder version uses only the co-author counts (Ichinomiya 2004):</p>
<div class="eq"><span class="tag">(B5)</span>$$K_c^{{\\,MF}} = K_0\\,\\frac{{\\langle k\\rangle}}{{\\langle k^2\\rangle}}$$</div>
<div class="work"><b>Trichy:</b> $K_c = {f(K0)}/{f(LT['lam'])} = \\mathbf{{{f(K0 / LT['lam'])}}}$;
mean-field $K_c = {f(K0)}\\times{f(LT['k1'])}/{f(LT['k2'])} = {f(K0 * LT['k1'] / LT['k2'])}$.<br>
<b>Surathkal:</b> $K_c = {f(K0)}/{f(LU['lam'])} = \\mathbf{{{f(K0 / LU['lam'])}}}$;
mean-field $K_c = {f(K0)}\\times{f(LU['k1'])}/{f(LU['k2'])} = {f(K0 * LU['k1'] / LU['k2'])}$.<br>
<b>Consistency check:</b> all-to-all coupling $A_{{ij}}=1/n$ has $\\lambda_1=1$, and B4 gives back $K_c=K_0$.</div>
<table><tr><th>Largest connected group</th><th>$n$</th><th>$\\lambda_1$</th><th>$K_c=K_0/\\lambda_1$</th><th>$\\langle k\\rangle$</th><th>$\\langle k^2\\rangle$</th><th>$K_0\\langle k\\rangle/\\langle k^2\\rangle$</th></tr>
{krow("NIT Trichy")}{krow("NIT Surathkal")}{krow(None)}</table>

<h3>B.3 Checking against the simulation</h3>
<p>In a finite network $r$ is not zero even without coupling: $n$ random phases give $r\\approx1/\\sqrt n$
(Trichy: $1/\\sqrt{{{LT['n']}}}={f(1 / np.sqrt(LT['n']))}$, simulated {f(rK("NIT Trichy", 0.0))} at $K=0$;
Surathkal: $1/\\sqrt{{{LU['n']}}}={f(1 / np.sqrt(LU['n']))}$, simulated {f(rK("NIT Surathkal", 0.0))}).</p>
<img src="{fig2}" alt="Kuramoto order parameter against the predicted onset">
<div class="result"><b>Result.</b> $r$ leaves its noise level around $K\\approx0.3$–$0.4$ at Trichy
($r$ = {f(rK("NIT Trichy", 0.2))}, {f(rK("NIT Trichy", 0.3))}, {f(rK("NIT Trichy", 0.4))} at $K$ = 0.2, 0.3, 0.4) and around $K\\approx0.2$–$0.3$ at Surathkal
({f(rK("NIT Surathkal", 0.2))}, {f(rK("NIT Surathkal", 0.3))}, {f(rK("NIT Surathkal", 0.4))}), matching $K_c={f(K0 / LT['lam'])}$ and ${f(K0 / LU['lam'])}$.
Surathkal starts first, as predicted, because its hubs give it a larger $\\lambda_1$.</div>

<h3>B.4 Full synchrony — the Laplacian eigenratio</h3>
<p>$K_c$ says where <i>partial</i> synchrony starts. How easily the whole network can be brought into step depends on the Laplacian
(Barahona &amp; Pecora 2002):</p>
<div class="eq"><span class="tag">(B6)</span>$$L = D - A,\\qquad 0=\\mu_1<\\mu_2\\le\\dots\\le\\mu_n,\\qquad
\\boxed{{\\;\\text{{eigenratio}}=\\frac{{\\mu_n}}{{\\mu_2}}\\;}}$$</div>
<p>A lower eigenratio means the network is easier to synchronise fully.</p>
<table><tr><th>Largest connected group</th><th>$\\mu_2$ real</th><th>$\\mu_2$ rewired</th><th>$\\mu_n/\\mu_2$ real</th><th>$\\mu_n/\\mu_2$ rewired</th></tr>
{erow("NIT Trichy")}{erow("NIT Surathkal")}{erow(None)}</table>
<div class="result"><b>Result.</b> $\\mu_2$ (algebraic connectivity) is small when the network has a weak cut. Ours is about 5 times smaller than in
random networks with the same degrees, so the eigenratio is about 5 times larger: departments synchronise inside but are joined by
thin bridges. NIT Trichy has the lower eigenratio (easier full synchrony), while NIT Surathkal starts synchronising earlier (larger $\\lambda_1$).</div>

<h3>References</h3>
<ul class="small">
<li>Newman, M. E. J. (2002). Spread of epidemic disease on networks. <i>Phys. Rev. E</i> 66, 016128.</li>
<li>Karrer, B., Newman, M. E. J. &amp; Zdeborová, L. (2014). Percolation on sparse networks. <i>Phys. Rev. Lett.</i> 113, 208702.</li>
<li>Pastor-Satorras, R., Castellano, C., Van Mieghem, P. &amp; Vespignani, A. (2015). Epidemic processes in complex networks. <i>Rev. Mod. Phys.</i> 87, 925.</li>
<li>Kuramoto, Y. (1984). <i>Chemical Oscillations, Waves, and Turbulence</i>. Springer.</li>
<li>Restrepo, J. G., Ott, E. &amp; Hunt, B. R. (2005). Onset of synchronization in large networks of coupled oscillators. <i>Phys. Rev. E</i> 71, 036151.</li>
<li>Ichinomiya, T. (2004). Frequency synchronization in a random oscillator network. <i>Phys. Rev. E</i> 70, 026116.</li>
<li>Barahona, M. &amp; Pecora, L. M. (2002). Synchronization in small-world systems. <i>Phys. Rev. Lett.</i> 89, 054101.</li>
</ul>
</body></html>"""
    with open(HTML, "w", encoding="utf-8") as fh:
        fh.write(html)
    os.makedirs(OUT_DIR, exist_ok=True)
    browser = next((p for p in [shutil.which("chrome"), shutil.which("msedge"),
                                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                                r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                                "/usr/bin/google-chrome", "/usr/bin/chromium"] if p and os.path.exists(p)), None)
    if not browser:
        sys.exit(f"HTML written to {HTML}; no Chrome/Edge found to print the PDF")
    subprocess.run([browser, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", "--virtual-time-budget=20000",
                    f"--print-to-pdf={PDF}", "file:///" + HTML.replace("\\", "/")], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=180)
    print(f"written {PDF} ({os.path.getsize(PDF) / 1e3:.0f} kB)")


if __name__ == "__main__":
    main()
