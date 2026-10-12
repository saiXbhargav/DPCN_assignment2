"""Task 2: build citation_network.csv, authorship_network.csv and indian_connections.csv,
plus network metrics (in-degree, PageRank, degree/betweenness centrality, Louvain communities).

Uses only local files: data/group12_data.csv (defines our corpus) and data/raw/*.jsonl.

Design decisions (agreed with the team):
  * Corpus = every paper in group12_data.csv (no subject filter).
  * Citation network = edges between our own papers ("internal") plus edges to/from papers by
    other Indian institutions ("out_indian" / "in_indian"). References to foreign papers are
    not included (we have no institution data for them).
  * Authorship network = every pair on one of our papers where at least one author is a NIT
    author; co-authors can be from anywhere. Papers with more than 50 authors are skipped.
  * Centrality and communities are computed on the NIT-only part of each network.
  * indian_connections.total_citations = summed citation counts of the co-authored papers;
    extra columns give citation in-flow and out-flow for each partner.
"""
import collections
import itertools
import json
import os

import networkx as nx
import pandas as pd

from fetch_works import INSTITUTIONS, RAW, ROOT

OWN = {v: k for k, v in INSTITUTIONS.items()}       # OpenAlex id -> "NIT Trichy"
MAX_AUTHORS = 50
OUT = os.path.join(ROOT, "data")
METRICS = os.path.join(OUT, "network_metrics")
SEED = 42


def short(url):
    return (url or "").rsplit("/", 1)[-1]


def join(names):
    return ";".join(sorted(names))


# ---------------------------------------------------------------- load data
def load_corpus():
    df = pd.read_csv(os.path.join(OUT, "group12_data.csv"), usecols=["institution", "openalex_id"])
    corpus = set(df.openalex_id)
    works = {}
    for name in INSTITUTIONS:
        path = os.path.join(RAW, name.replace(" ", "_") + "_works.jsonl")
        for line in open(path, encoding="utf-8"):
            w = json.loads(line)
            wid = short(w["id"])
            if wid in corpus:
                works[wid] = w
    assert set(works) == corpus, "raw files and group12_data.csv disagree"
    return works


def load_links(direction):
    """Deduplicated Indian works from fetch_links.py, keyed by id."""
    recs = {}
    for line in open(os.path.join(RAW, f"links_{direction}.jsonl"), encoding="utf-8"):
        r = json.loads(line)
        if direction == "citers" and r["id"] in recs:
            # same citing work can come back in several batches; merge its cited lists
            recs[r["id"]]["cites_ours"] = sorted(set(recs[r["id"]]["cites_ours"]) | set(r["cites_ours"]))
        else:
            recs[r["id"]] = r
    return recs


# Indian institutions on a paper, as {institution id: display name}
def indian_insts_work(w):
    return {short(i["id"]): i["display_name"] for a in w["authorships"] for i in a["institutions"]
            if i.get("country_code") == "IN"}


def indian_insts_link(r):
    return {i[0]: i[1] for a in r["authors"] for i in a["inst"] if i[2] == "IN"}


def name_of(iid, name):
    return OWN.get(iid, name)


def is_nit_label(inst):
    """True for 'NIT Trichy', 'NIT Surathkal' or both joined by ';'."""
    return all(p in OWN.values() for p in inst.split(";"))


# ---------------------------------------------------------------- citation network
def citation_network(works, refs, citers):
    paper = {}  # id -> dict(doi, year, own NITs, all Indian insts)
    for wid, w in works.items():
        ind = indian_insts_work(w)
        paper[wid] = {"doi": w.get("doi") or "", "year": w["publication_year"],
                      "own": {OWN[i] for i in ind if i in OWN}, "indian": ind}
        assert paper[wid]["own"], f"{wid} has no NIT affiliation"
    for src in (refs, citers):
        for rid, r in src.items():
            if rid not in paper:
                paper[rid] = {"doi": r.get("doi") or "", "year": r.get("year"), "own": set(),
                              "indian": indian_insts_link(r)}

    def inst_label(pid):
        p = paper[pid]
        if pid in works:
            return join(p["own"])
        return join(name_of(i, n) for i, n in p["indian"].items())

    def other_indian(pid):
        return any(i not in OWN for i in paper[pid]["indian"])

    edges = set()
    stats = collections.Counter()
    for wid, w in works.items():
        for r in map(short, w["referenced_works"]):
            if r == wid:
                continue
            if r in works:
                edges.add((wid, r, "internal"))
            elif r in refs:
                if other_indian(r):
                    edges.add((wid, r, "out_indian"))
                else:
                    stats["dropped_ref_own_nit_outside_corpus"] += 1
    for cid, c in citers.items():
        if cid in works:
            continue  # already covered as an internal edge from its own reference list
        if not other_indian(cid):
            stats["dropped_citer_own_nit_outside_corpus"] += len(c["cites_ours"])
            continue
        for t in c["cites_ours"]:
            if t in works:
                edges.add((cid, t, "in_indian"))

    rows = []
    for s, t, kind in sorted(edges):
        rows.append({
            "source_doi": paper[s]["doi"], "target_doi": paper[t]["doi"],
            "source_inst": inst_label(s), "target_inst": inst_label(t),
            "year": paper[s]["year"],
            "edge_type": kind,
            "cross_institute": inst_label(s) != inst_label(t),
            "source_id": s, "target_id": t,
        })
    cit = pd.DataFrame(rows)
    cit.to_csv(os.path.join(OUT, "citation_network.csv"), index=False)

    # metrics on the internal (within our institutions) graph
    G = nx.DiGraph()
    G.add_nodes_from(works)
    G.add_edges_from((s, t) for s, t, k in edges if k == "internal")
    pr = nx.pagerank(G, alpha=0.85)
    ind_in = collections.Counter(t for s, t, k in edges if k == "in_indian")
    ind_out = collections.Counter(s for s, t, k in edges if k == "out_indian")
    m = pd.DataFrame({
        "openalex_id": list(works),
        "doi": [paper[w]["doi"] for w in works],
        "title": [works[w]["title"] for w in works],
        "institution": [inst_label(w) for w in works],
        "year": [paper[w]["year"] for w in works],
        "citations_total": [works[w]["cited_by_count"] for w in works],
        "in_degree_internal": [G.in_degree(w) for w in works],
        "out_degree_internal": [G.out_degree(w) for w in works],
        "pagerank": [pr[w] for w in works],
        "cited_by_indian_papers": [ind_in[w] for w in works],
        "cites_indian_papers": [ind_out[w] for w in works],
    }).sort_values("pagerank", ascending=False)
    m.to_csv(os.path.join(METRICS, "citation_paper_metrics.csv"), index=False)
    nx.write_gexf(G, os.path.join(METRICS, "citation_internal.gexf"))
    return cit, G, paper, stats


# ---------------------------------------------------------------- authorship network
def author_inst(a):
    """Institution label for one authorship: our NIT name(s) if NIT-affiliated, else their institutions."""
    own = {OWN[short(i["id"])] for i in a["institutions"] if short(i["id"]) in OWN}
    if own:
        return join(own), True, "IN"
    names = {i["display_name"] for i in a["institutions"]}
    countries = {i.get("country_code") for i in a["institutions"] if i.get("country_code")}
    country = "IN" if "IN" in countries else (join(countries) if countries else "")
    return (join(names) if names else "Unknown"), False, country


def authorship_network(works):
    rows = []
    stats = collections.Counter()
    for wid, w in works.items():
        if len(w["authorships"]) > MAX_AUTHORS:
            stats["papers_skipped_over_50_authors"] += 1
            continue
        people = {}
        for a in w["authorships"]:
            aid = short(a["author"]["id"])
            if not aid:
                stats["authorships_without_id"] += 1
                continue
            inst, is_nit, country = author_inst(a)
            if aid in people and people[aid][2] and not is_nit:
                continue  # same person listed twice: keep the NIT authorship
            people[aid] = (a["author"]["display_name"], inst, is_nit, country)
        for x, y in itertools.combinations(sorted(people), 2):
            nx_, ny_ = people[x], people[y]
            if not (nx_[2] or ny_[2]):
                continue  # pair of two outside co-authors: out of scope
            if nx_[2] and ny_[2]:
                cat = "same_nit" if nx_[1] == ny_[1] else "nit_nit"
            else:
                other = ny_ if nx_[2] else nx_
                cat = "nit_indian" if other[3] == "IN" else ("nit_foreign" if other[3] else "nit_unknown")
            rows.append({
                "author_a": nx_[0], "author_b": ny_[0],
                "paper_doi": w.get("doi") or "",
                "inst_a": nx_[1], "inst_b": ny_[1],
                "year": w["publication_year"],
                "edge_category": cat,
                "cross_institution": nx_[1] != ny_[1],
                "author_a_id": x, "author_b_id": y, "paper_id": wid,
            })
    au = pd.DataFrame(rows)
    au.to_csv(os.path.join(OUT, "authorship_network.csv"), index=False)

    # NIT-only weighted graph (weight = number of joint papers)
    nit = au[au.edge_category.isin(["same_nit", "nit_nit"])]
    G = nx.Graph()
    names, insts = {}, collections.defaultdict(collections.Counter)
    for r in au.itertuples(index=False):
        for aid, nm, inst in ((r.author_a_id, r.author_a, r.inst_a), (r.author_b_id, r.author_b, r.inst_b)):
            if is_nit_label(inst):
                names[aid] = nm
                insts[aid][inst] += 1
    # NIT authors whose papers have no co-author with an ID are isolated nodes
    for w in works.values():
        if len(w["authorships"]) > MAX_AUTHORS:
            continue
        for a in w["authorships"]:
            aid = short(a["author"]["id"])
            inst, is_nit, _ = author_inst(a)
            if aid and is_nit and aid not in names:
                names[aid] = a["author"]["display_name"]
                insts[aid][inst] += 1
    G.add_nodes_from(names)
    for (a, b), n in nit.groupby(["author_a_id", "author_b_id"]).paper_id.nunique().items():
        G.add_edge(a, b, weight=int(n))

    deg = nx.degree_centrality(G)
    btw = nx.betweenness_centrality(G, normalized=True)  # exact, unweighted shortest paths
    comms = nx.community.louvain_communities(G, weight="weight", seed=SEED)
    modularity = nx.community.modularity(G, comms, weight="weight")
    comm_of = {n: i for i, c in enumerate(sorted(comms, key=len, reverse=True)) for n in c}

    papers_per_author = collections.Counter()
    for wid, w in works.items():
        for aid in {short(a["author"]["id"]) for a in w["authorships"]
                    if a["author"]["id"] and any(short(i["id"]) in OWN for i in a["institutions"])}:
            papers_per_author[aid] += 1
    partners = collections.defaultdict(set)  # NIT author -> Indian partner institutions
    for r in au[au.edge_category == "nit_indian"].itertuples(index=False):
        if is_nit_label(r.inst_a):
            partners[r.author_a_id].update(r.inst_b.split(";"))
        else:
            partners[r.author_b_id].update(r.inst_a.split(";"))

    m = pd.DataFrame({
        "author_id": list(G.nodes),
        "author": [names[n] for n in G.nodes],
        "institution": [insts[n].most_common(1)[0][0] for n in G.nodes],
        "papers": [papers_per_author[n] for n in G.nodes],
        "degree": [G.degree(n) for n in G.nodes],
        "weighted_degree": [G.degree(n, weight="weight") for n in G.nodes],
        "degree_centrality": [deg[n] for n in G.nodes],
        "betweenness_centrality": [btw[n] for n in G.nodes],
        "community": [comm_of[n] for n in G.nodes],
        "indian_partner_institutes": [len(partners[n]) for n in G.nodes],
    }).sort_values("degree_centrality", ascending=False)
    m.to_csv(os.path.join(METRICS, "author_metrics.csv"), index=False)
    nx.set_node_attributes(G, names, "label")
    nx.set_node_attributes(G, comm_of, "community")
    nx.write_gexf(G, os.path.join(METRICS, "authorship_nit.gexf"))
    return au, G, comms, modularity, stats


# ---------------------------------------------------------------- indian connections
def indian_connections(works, cit, paper):
    rows = collections.defaultdict(lambda: {"shared_papers": set(), "cites_from_partner": 0,
                                            "cites_to_partner": 0, "name": ""})
    for wid, w in works.items():
        ind = paper[wid]["indian"]
        for mine in paper[wid]["own"]:
            for pid, pname in ind.items():
                if OWN.get(pid) == mine:
                    continue
                rows[(mine, pid)]["shared_papers"].add(wid)
                rows[(mine, pid)]["name"] = name_of(pid, pname)
    # citation flow between institutions: a citing paper that already includes `mine`
    # is a self-institution citation and is not counted as flow from a partner
    def labels(pid):
        return {name_of(i, n) for i, n in paper[pid]["indian"].items()}

    for s, t in zip(cit.source_id, cit.target_id):
        for mine, other, key in ((paper[t]["own"], s, "cites_from_partner"),
                                 (paper[s]["own"], t, "cites_to_partner")):
            for m in mine:
                if m in labels(other):
                    continue  # the other paper also has authors from `m`
                for pid, pname in paper[other]["indian"].items():
                    rows[(m, pid)][key] += 1
                    rows[(m, pid)]["name"] = name_of(pid, pname)

    out = []
    for (mine, pid), v in rows.items():
        shared = v["shared_papers"]
        out.append({
            "your_inst": mine, "partner_inst": v["name"],
            "shared_papers": len(shared),
            "total_citations": sum(works[p]["cited_by_count"] for p in shared),
            "cites_from_partner": v["cites_from_partner"],
            "cites_to_partner": v["cites_to_partner"],
            "partner_id": pid,
        })
    ic = pd.DataFrame(out).sort_values(["your_inst", "shared_papers", "cites_from_partner"],
                                       ascending=[True, False, False])
    ic.to_csv(os.path.join(OUT, "indian_connections.csv"), index=False)
    return ic


# ---------------------------------------------------------------- main
def main():
    os.makedirs(METRICS, exist_ok=True)
    works = load_corpus()
    refs, citers = load_links("refs"), load_links("citers")

    cit, CG, paper, cstats = citation_network(works, refs, citers)
    au, AG, comms, modularity, astats = authorship_network(works)
    ic = indian_connections(works, cit, paper)

    summary = {
        "corpus_papers": len(works),
        "citation_network": {
            "edges_total": len(cit),
            "edges_by_type": cit.edge_type.value_counts().to_dict(),
            "internal_graph_nodes": CG.number_of_nodes(),
            "internal_graph_edges": CG.number_of_edges(),
            "papers_with_internal_citations": int(sum(1 for n in CG if CG.in_degree(n) > 0)),
            **cstats,
        },
        "authorship_network": {
            "edges_total": len(au),
            "edges_by_category": au.edge_category.value_counts().to_dict(),
            "nit_graph_nodes": AG.number_of_nodes(),
            "nit_graph_edges": AG.number_of_edges(),
            "nit_graph_components": nx.number_connected_components(AG),
            "largest_component": len(max(nx.connected_components(AG), key=len)),
            "louvain_communities": len(comms),
            "communities_size_ge_10": sum(len(c) >= 10 for c in comms),
            "modularity": round(modularity, 4),
            **astats,
        },
        "indian_connections": {
            "rows": len(ic),
            "partners_with_shared_papers": int((ic.shared_papers > 0).sum()),
        },
    }
    with open(os.path.join(METRICS, "network_summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
