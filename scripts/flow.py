"""The one rule for citation flow between institutions (used by build_dataset, build_networks and verify_networks).

A citation between paper A (which has our institute N) and paper B gives credit to an outside institute Y only
when the two papers do not share that link through co-authorship:
  * if N is also on B, it is an institutional self-citation (for example NIT Trichy citing a paper NIT Trichy
    wrote with IIT Madras), so no institute gets credit;
  * otherwise every Indian institute Y on B counts, except N itself and except institutes that are also on A
    (A's own co-authors citing their own work is not a link between N and Y).
"""
from fetch_works import INSTITUTIONS

OWN_IDS = set(INSTITUTIONS.values())


def flow_partners(n, a_insts, b_insts):
    """Indian institution ids on paper B that are credited for a citation between A and B, from N's point of view."""
    if n in b_insts:
        return set()
    return {y for y in b_insts if y != n and y not in a_insts}


def other_indian_partners(n, a_insts, b_insts):
    """The same, limited to institutes other than our two NITs (used for cites_indian_inst / cited_by_indian_inst)."""
    return flow_partners(n, a_insts, b_insts) - OWN_IDS
