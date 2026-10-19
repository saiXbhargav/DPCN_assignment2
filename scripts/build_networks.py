"""Task 2: build citation_network.csv, authorship_network.csv and indian_connections.csv,
plus network metrics (in-degree, PageRank, degree/betweenness centrality, Louvain communities).

Uses only local files: data/group12_data.csv (defines our corpus and which authors are faculty) and
data/raw/*.jsonl.

Design decisions (agreed with the team):
  * Corpus = every paper in group12_data.csv: science/engineering papers with at least one NIT faculty author.
  * Citation network = edges between our own papers ("internal") plus edges to/from papers by
    other Indian institutions ("out_indian" / "in_indian"). References to foreign papers are
    not included (we have no institution data for them). When the outside paper shares an institute with
    ours through co-authorship (e.g. a NIT Trichy paper citing a NIT Trichy + IIT Madras paper), the edge is
    kept as "out_shared_inst" / "in_shared_inst" and is not counted as flow between institutes (flow.py).
  * Authorship network = every pair on one of our papers where at least one author is NIT faculty; co-authors
    can be NIT faculty or from another institution. PhD students and other NIT staff are not nodes. NIT faculty
    are identified by their faculty_id (one node per person, even when OpenAlex splits them into several IDs).
    Papers with more than --max-authors authors (default 50) are skipped.
  * Centrality and communities are computed on the NIT-only part of each network.
  * indian_connections.total_citations = summed citation counts of the co-authored papers;
    extra columns give citation in-flow and out-flow for each partner.

  python build_networks.py                                  # the submitted files
  python build_networks.py --max-authors 0 --authorship-only --out ../data/analysis/sensitivity/no_cap
"""
import argparse
import collections
import itertools
import json
import os

import networkx as nx
import pandas as pd

from fetch_works import INSTITUTIONS, RAW, ROOT
from clusters import OUR_CLUSTER, cluster_of, load_institutions
from flow import flow_partners, other_indian_partners

OWN = {v: k for k, v in INSTITUTIONS.items()}       # OpenAlex id -> "NIT Trichy"
MAX_AUTHORS = 50
DATA = os.path.join(ROOT, "data")
SEED = 42


def short(url):
    return (url or "").rsplit("/", 1)[-1]


def join(names):
    return ";".join(sorted(names))


# ---------------------------------------------------------------- load data
def load_corpus():
    df = pd.read_csv(os.path.join(DATA, "group12_data.csv"),
                     usecols=["institution", "openalex_id", "author_position", "faculty_id", "author"])
    corpus = set(df.openalex_id)
    faculty = {(r.openalex_id, int(r.author_position)): (r.faculty_id, r.author) for r in df.itertuples(index=False)}
    # our institutions on a paper = the NITs with a faculty author on it (not NITs with only students on it)
    nid = {v: k for k, v in OWN.items()}
    own = df.groupby("openalex_id").institution.agg(lambda s: {nid[i] for i in s}).to_dict()
    works = {}
    for name in INSTITUTIONS:
        path = os.path.join(RAW, name.replace(" ", "_") + "_works.jsonl")
        for line in open(path, encoding="utf-8"):
            w = json.loads(line)
            wid = short(w["id"])
            if wid in corpus:
                works[wid] = w
    assert set(works) == corpus, "raw files and group12_data.csv disagree"
    return works, faculty, own


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
def citation_network(works, refs, citers, own, out, metrics):
    paper = {}  # id -> dict(doi, year, own NIT ids, all Indian insts)
    for wid, w in works.items():
        ind = indian_insts_work(w)
        paper[wid] = {"doi": w.get("doi") or "", "year": w["publication_year"],
                      "own": own[wid], "indian": ind}
        assert paper[wid]["own"], f"{wid} has no NIT affiliation"
    for src in (refs, citers):
        for rid, r in src.items():
            if rid not in paper:
                paper[rid] = {"doi": r.get("doi") or "", "year": r.get("year"), "own": set(),
                              "indian": indian_insts_link(r)}

    def inst_label(pid):
        p = paper[pid]
        if pid in works:
            return join(OWN[i] for i in p["own"])
        return join(name_of(i, n) for i, n in p["indian"].items())

    def other_indian(pid):
        return any(i not in OWN for i in paper[pid]["indian"])

    def credited(ours, other):
        """Some outside Indian institute gets credit from at least one of our NITs on `ours` (flow.py)."""
        a, b = set(paper[ours]["indian"]), set(paper[other]["indian"])
        return any(other_indian_partners(n, a, b) for n in paper[ours]["own"])

    edges = set()
    stats = collections.Counter()
    for wid, w in works.items():
        for r in map(short, w["referenced_works"]):
            if r == wid:
                continue
            if r in works:
                edges.add((wid, r, "internal"))
            elif r in refs:
                if not other_indian(r):
                    stats["dropped_ref_own_nit_outside_corpus"] += 1
                else:
                    edges.add((wid, r, "out_indian" if credited(wid, r) else "out_shared_inst"))
    for cid, c in citers.items():
        if cid in works:
            continue  # already covered as an internal edge from its own reference list
        if not other_indian(cid):
            stats["dropped_citer_own_nit_outside_corpus"] += len(c["cites_ours"])
            continue
        for t in c["cites_ours"]:
            if t in works:
                edges.add((cid, t, "in_indian" if credited(t, cid) else "in_shared_inst"))

    rows = []
    for s, t, kind in sorted(edges):
        rows.append({
            "source_doi": paper[s]["doi"], "target_doi": paper[t]["doi"],
            "source_inst": inst_label(s), "target_inst": inst_label(t),
            "year": paper[s]["year"],
            "edge_type": kind,
            "cross_institute": (inst_label(s) != inst_label(t)) if kind == "internal" else kind.endswith("_indian"),
            "source_id": s, "target_id": t,
        })
    cit = pd.DataFrame(rows)
    cit.to_csv(os.path.join(out, "citation_network.csv"), index=False)

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
    m.to_csv(os.path.join(metrics, "citation_paper_metrics.csv"), index=False)
    nx.write_gexf(G, os.path.join(metrics, "citation_internal.gexf"))
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


def people_on(wid, w, faculty, stats):
    """{node id: (name, institution label, is NIT faculty, country)} for one paper."""
    people = {}
    for pos, a in enumerate(w["authorships"]):
        inst, is_nit, country = author_inst(a)
        fac = faculty.get((wid, pos))
        if fac:
            people[fac[0]] = (fac[1], inst, True, "IN")
        elif is_nit:
            stats["nit_authorships_not_faculty"] += 1  # PhD students, staff, out-of-scope departments
        else:
            aid = short(a["author"]["id"])
            if not aid:
                stats["authorships_without_id"] += 1
                continue
            if aid not in people:
                people[aid] = (a["author"]["display_name"], inst, False, country)
    return people


def authorship_network(works, faculty, out, metrics, max_authors):
    rows = []
    stats = collections.Counter()
    too_big = lambda w: max_authors and len(w["authorships"]) > max_authors
    for wid, w in works.items():
        if too_big(w):
            stats["papers_skipped_over_max_authors"] += 1
            continue
        people = people_on(wid, w, faculty, stats)
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
    au.to_csv(os.path.join(out, "authorship_network.csv"), index=False)

    # NIT-faculty-only weighted graph (weight = number of joint papers)
    nit = au[au.edge_category.isin(["same_nit", "nit_nit"])]
    G = nx.Graph()
    names, insts = {}, collections.defaultdict(collections.Counter)
    for (wid, pos), (fid, name) in faculty.items():  # every faculty member with a paper inside the cap is a node
        w = works[wid]
        if too_big(w):
            continue
        names[fid] = name
        insts[fid][author_inst(w["authorships"][pos])[0]] += 1
    G.add_nodes_from(names)
    for (a, b), n in nit.groupby(["author_a_id", "author_b_id"]).paper_id.nunique().items():
        G.add_edge(a, b, weight=int(n))

    deg = nx.degree_centrality(G)
    btw = nx.betweenness_centrality(G, normalized=True)  # exact, unweighted shortest paths
    comms = nx.community.louvain_communities(G, weight="weight", seed=SEED)
    modularity = nx.community.modularity(G, comms, weight="weight")
    comm_of = {n: i for i, c in enumerate(sorted(comms, key=len, reverse=True)) for n in c}

    papers_per_author = collections.Counter()
    for fid, wid in {(fid, wid) for (wid, _), (fid, _) in faculty.items()}:
        papers_per_author[fid] += 1
    partners = collections.defaultdict(set)  # NIT faculty -> Indian partner institutions
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
    m.to_csv(os.path.join(metrics, "author_metrics.csv"), index=False)
    nx.set_node_attributes(G, names, "label")
    nx.set_node_attributes(G, comm_of, "community")
    nx.write_gexf(G, os.path.join(metrics, "authorship_nit.gexf"))
    return au, G, comms, modularity, stats


# ---------------------------------------------------------------- indian connections
def indian_connections(works, cit, paper, out):
    rows = collections.defaultdict(lambda: {"shared_papers": set(), "cites_from_partner": 0,
                                            "cites_to_partner": 0, "name": ""})
    for wid, w in works.items():
        ind = paper[wid]["indian"]
        for mine in paper[wid]["own"]:
            for pid, pname in ind.items():
                if pid == mine:
                    continue
                rows[(OWN[mine], pid)]["shared_papers"].add(wid)
                rows[(OWN[mine], pid)]["name"] = name_of(pid, pname)
    # citation flow between institutions follows flow.py: no credit when the other paper also has authors from
    # our institution, and none for institutes that are co-authors on our own paper
    for s, t in zip(cit.source_id, cit.target_id):
        i_s, i_t = set(paper[s]["indian"]), set(paper[t]["indian"])
        for mine in paper[t]["own"]:
            for pid in flow_partners(mine, i_t, i_s):
                rows[(OWN[mine], pid)]["cites_from_partner"] += 1
                rows[(OWN[mine], pid)]["name"] = rows[(OWN[mine], pid)]["name"] or name_of(pid, paper[s]["indian"][pid])
        for mine in paper[s]["own"]:
            for pid in flow_partners(mine, i_s, i_t):
                rows[(OWN[mine], pid)]["cites_to_partner"] += 1
                rows[(OWN[mine], pid)]["name"] = rows[(OWN[mine], pid)]["name"] or name_of(pid, paper[t]["indian"][pid])

    institutions = load_institutions()
    res = []
    for (mine, pid), v in rows.items():
        shared = v["shared_papers"]
        res.append({
            "your_inst": mine, "partner_inst": v["name"],
            "shared_papers": len(shared),
            "total_citations": sum(works[p]["cited_by_count"] for p in shared),
            "cites_from_partner": v["cites_from_partner"],
            "cites_to_partner": v["cites_to_partner"],
            "partner_id": pid,
            # cluster flags for Task 3 (NIT <-> IIT, CSIR, IISER, ...); our own cluster is NIT
            "partner_type": institutions.get(pid, {}).get("type", ""),
            "partner_cluster": cluster_of(pid, v["name"], institutions),
            "cross_cluster": cluster_of(pid, v["name"], institutions) != OUR_CLUSTER,
        })
    ic = pd.DataFrame(res).sort_values(["your_inst", "shared_papers", "cites_from_partner", "partner_id"],
                                       ascending=[True, False, False, True])
    ic.to_csv(os.path.join(out, "indian_connections.csv"), index=False)
    return ic


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-authors", type=int, default=MAX_AUTHORS, help="skip bigger papers; 0 = no limit")
    ap.add_argument("--out", default=DATA, help="folder for the CSV files (metrics go to <out>/network_metrics)")
    ap.add_argument("--authorship-only", action="store_true", help="only the authorship network (sensitivity runs)")
    args = ap.parse_args()
    out = os.path.abspath(args.out)
    metrics = os.path.join(out, "network_metrics")
    os.makedirs(metrics, exist_ok=True)
    works, faculty, own = load_corpus()

    au, AG, comms, modularity, astats = authorship_network(works, faculty, out, metrics, args.max_authors)
    summary = {"corpus_papers": len(works), "max_authors": args.max_authors or None}
    if not args.authorship_only:
        refs, citers = load_links("refs"), load_links("citers")
        cit, CG, paper, cstats = citation_network(works, refs, citers, own, out, metrics)
        ic = indian_connections(works, cit, paper, out)
        summary["citation_network"] = {
            "edges_total": len(cit),
            "edges_by_type": cit.edge_type.value_counts().to_dict(),
            "internal_graph_nodes": CG.number_of_nodes(),
            "internal_graph_edges": CG.number_of_edges(),
            "papers_with_internal_citations": int(sum(1 for n in CG if CG.in_degree(n) > 0)),
            **cstats,
        }
    summary["authorship_network"] = {
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
    }
    if not args.authorship_only:
        summary["indian_connections"] = {
            "rows": len(ic),
            "partners_with_shared_papers": int((ic.shared_papers > 0).sum()),
        }
    with open(os.path.join(metrics, "network_summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
