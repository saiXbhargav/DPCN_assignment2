"""Which cluster an Indian institute belongs to (NIT, IIT, IIIT, IISER / IISc, CSIR, DAE, ...), for the
"flag cross-cluster links" part of Task 3. Uses data/raw/institutions.jsonl (fetch_impact.py institutions):
the institute's name, its OpenAlex type and its parent organisations (lineage), so a lab whose parent is CSIR
counts as CSIR even when "CSIR" is not in its name.
"""
import json
import os
import re

from fetch_works import RAW

OUR_CLUSTER = "NIT"
NAME_RULES = [  # checked first, in order
    ("IIIT", r"Indian Institute of Information Technology|International Institute of Information Technology|IIITDM"),
    ("NIT", r"National Institute of Technology\b"),
    ("IIT", r"^Indian Institute of Technology\b|^IIT\b"),
    ("IISER / IISc", r"Indian Institute of Science Education and Research|^Indian Institute of Science\b"),
]
PARENT_RULES = [  # names of parent organisations (lineage)
    ("CSIR", r"Council of Scientific and Industrial Research"),
    # names are also checked here (the institute's own name is part of `family`), because OpenAlex does not list
    # the parent of every ISRO or DAE centre
    ("DAE", r"Department of Atomic Energy|Atomic Research|Bhabha|UGC.DAE|Raja Ramanna|Variable Energy Cyclotron|"
            r"Tata Institute of Fundamental Research"),
    ("ISRO", r"Indian Space Research Organisation|Department of Space|Space Centre|Space Applications Centre|"
             r"Satellite Centre|Remote Sensing Centre|Propulsion Complex|^ISRO"),
    ("DRDO", r"Defence Research and Development Organisation"),
    ("ICAR", r"Indian Council of Agricultural Research"),
    ("ICMR", r"Indian Council of Medical Research"),
    ("Other government R&D", r"Department of Science and Technology|Department of Biotechnology|"
                             r"Ministry of Earth Sciences|Indian Council of Forestry|Ministry of Defence"),
]
TYPE_RULES = {"education": "University / college", "healthcare": "Hospital / medical", "company": "Industry",
              "facility": "Other government R&D", "government": "Other government R&D"}


def load_institutions():
    path = os.path.join(RAW, "institutions.jsonl")
    if not os.path.exists(path):
        return {}
    return {r["id"]: r for r in map(json.loads, open(path, encoding="utf-8"))}


def cluster_of(iid, name, insts):
    rec = insts.get(iid, {})
    name = rec.get("name") or name or ""
    for cluster, pat in NAME_RULES:
        if re.search(pat, name):
            return cluster
    family = [insts.get(p, {}).get("name", "") for p in rec.get("lineage", []) if p != iid] + [name]
    for cluster, pat in PARENT_RULES:
        if any(re.search(pat, n) for n in family):
            return cluster
    return TYPE_RULES.get(rec.get("type"), "Other")
