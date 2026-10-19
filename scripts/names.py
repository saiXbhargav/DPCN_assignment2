"""Shared helpers for faculty names and branches (used by build_roster.py and match_faculty.py)."""
import itertools
import re
import unicodedata

TITLES = {"dr", "prof", "professor", "mr", "mrs", "ms", "miss", "shri", "sri", "smt", "er", "ar", "late",
          "ing"}  # "Dr.-Ing." is a German doctorate title

# ---------------------------------------------------------------- branches
# One canonical branch per department. Patterns are tried in order on the lower-cased department text.
BRANCH_PATTERNS = [
    ("Computer Applications", r"computer applications?|^c\.?a\.?$|^mca$|facultymca"),
    ("Information Technology", r"information technology|^i\.?t\.?$|infotech"),
    ("CSE", r"computer science|comp\.? ?sc|^c\.?s\.?e\.?$|\bcse\b"),
    ("ICE", r"instrumentation|^i\.?c\.?e\.?$"),
    ("EEE", r"electrical|^e\.?e\.?e\.?$|^eee|^e ?& ?e$"),  # before ECE: "Electrical and Electronics" is EEE
    ("ECE", r"electronics|communication|^e\.?c\.?e\.?$|^e ?& ?c$"),
    ("Physical Education", r"phy\.? ?edu|physical education"),
    ("Training & Placement", r"placement"),
    ("Production", r"production|industrial engineering|^prod"),
    ("MME", r"metallurg|materials engineering|^m\.? ?m\.? ?e\.?$|^meta"),
    ("Chemical", r"chemical"),
    ("Chemistry", r"chemistry"),
    ("Civil", r"civil"),
    ("Mechanical", r"mechanical|^mech"),
    ("Mining", r"mining"),
    ("Water Resources & Ocean", r"water resources|ocean|applied mechanics|appmech|hydraulics"),
    ("Mathematics", r"mathemat|^maths?$|macs"),
    ("Physics", r"physics"),
    ("Energy & Environment", r"energy|environment|ceesat|^dee$"),
    ("Architecture", r"architecture|planning"),
    ("Management", r"management|^som$|business"),
    ("Humanities", r"humanities|social sciences|^hss$|english|economics"),
]
# not science / engineering / technology departments (or not academic departments at all)
EXCLUDED_BRANCHES = {"Management", "Humanities", "Physical Education", "Training & Placement"}


DEPT_TEXT = re.compile(r"((?:Department|Dept\.?|School|Centre|Center)\s+(?:of|for)\s+[^,;]+)", re.I)


def affiliation_branch(raw_affiliation):
    """Branch named in a raw affiliation string ("Department of Civil Engineering, NIT ..." -> "Civil")."""
    m = DEPT_TEXT.search(raw_affiliation or "")
    return branch_of(m.group(1)) if m else branch_of(raw_affiliation)


def branch_of(dept):
    d = re.sub(r"\s+", " ", (dept or "").lower()).strip()
    if not d:
        return ""
    for name, pat in BRANCH_PATTERNS:
        if re.search(pat, d):
            return name
    return ""


# ---------------------------------------------------------------- designations
def designation_of(text):
    """Normalised rank, or '' when the text is not a teaching-faculty designation."""
    t = re.sub(r"[^a-z() ]", " ", (text or "").lower())
    t = re.sub(r"\s+", " ", t).strip()
    if not t:
        return ""
    if re.search(r"adjunct|visiting|guest|temporary|contract|adhoc|ad hoc|emerit|inspire|women scientist|"
                 r"post ?doc|lecturer|teaching assistant|research (associate|scholar|fellow)", t):
        return "Non-regular"
    if re.search(r"\bdirector\b", t) and "deputy" not in t and "assistant" not in t:
        return "Director"
    if re.search(r"\bhag\b|higher administrative", t):
        return "Professor (HAG)"
    if re.search(r"\bass(o|oc|ociate)\b.*prof|associate prof", t):
        return "Associate Professor"
    if re.search(r"\bas(st|sistant)\b.*prof|assistant prof", t):
        return "Assistant Professor"
    if re.search(r"\bprof", t) or "deputy director" in t:
        return "Professor"
    return ""


# ---------------------------------------------------------------- names
def ascii_fold(s):
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()


def tokens(name):
    """'Dr.S.R.BALASUNDARAM' -> ['s', 'r', 'balasundaram'] (titles removed, dots split initials)."""
    s = ascii_fold(name).lower()
    s = re.sub(r"\(.*?\)", " ", s)          # '(on lien)', '(former)'
    s = re.sub(r"[^a-z]+", " ", s)
    toks = [t for t in s.split() if t]
    while toks and toks[0] in TITLES:
        toks = toks[1:]
    return [t for t in toks if t not in TITLES]


def clean_display(name):
    toks = tokens(name)
    return " ".join(t.upper() if len(t) == 1 else t.capitalize() for t in toks)


def _close(t, u):
    """Same word up to one typo ('banu' / 'bannu'), for words of 4+ letters with the same first letter."""
    if t[0] != u[0] or min(len(t), len(u)) < 4 or abs(len(t) - len(u)) > 1:
        return False
    if len(t) == len(u):
        return sum(x != y for x, y in zip(t, u)) == 1
    s, l = (t, u) if len(t) < len(u) else (u, t)
    return any(l[:i] + l[i + 1:] == s for i in range(len(l)))


def _align(a, b):
    """Try to pair every token of a with a distinct token of b (full = same word, initial = first letter).
    Returns (full-word matches, number of unmatched tokens in b, typo matches) or None."""
    fulls_a = [t for t in a if len(t) > 1]
    inits_a = [t for t in a if len(t) == 1]
    used = set()
    full_hits = typos = 0
    for t in fulls_a:  # full words must match a full word (or a near-identical one), or an initial in b
        j = next((j for j, u in enumerate(b) if j not in used and u == t), None)
        if j is not None:
            full_hits += 1
        else:
            j = next((j for j, u in enumerate(b) if j not in used and len(u) > 1 and _close(t, u)), None)
            if j is not None:
                full_hits += 1
                typos += 1
            else:
                j = next((j for j, u in enumerate(b) if j not in used and len(u) == 1 and u == t[0]), None)
        if j is None:
            return None
        used.add(j)
    for t in inits_a:
        j = next((j for j, u in enumerate(b) if j not in used and u[0] == t), None)
        if j is None:
            return None
        used.add(j)
    return full_hits, len(b) - len(used), typos


def _squash_match(a, b):
    """Glued names from old directories: 'dwarakishgs' == some ordering of b's words or their initials."""
    target = "".join(a)
    if len(b) > 5 or len(target) < 5:
        return False
    choices = [(u, u[0]) if len(u) > 1 else (u,) for u in b]
    for perm in itertools.permutations(range(len(b))):
        for pick in itertools.product(*(choices[i] for i in perm)):
            if "".join(pick) == target:
                return True
    return False


def _glued(a, b):
    """'Senthilkumar' = 'Senthil Kumar', also when one side has one extra initial ('Ravikumar M')."""
    if _squash_match(a, b) or _squash_match(b, a):
        return True
    fa, fb = [t for t in a if len(t) > 1], [t for t in b if len(t) > 1]
    if len(a) - len(fa) + len(b) - len(fb) > 1 or not fa or not fb:
        return False
    return "".join(fa) in ("".join(p) for p in itertools.permutations(fb)) or \
           "".join(fb) in ("".join(p) for p in itertools.permutations(fa))


def name_detail(roster_name, other_name):
    """(score, weakness). score: 0 = incompatible; 1 = compatible only with one weak point; 2 = all words agree
    with at least one full word in common; 3 = the same words (initials only where both have initials).
    weakness for score 1: 'extra_word' (one word the other name does not explain), 'typo' or 'glued'."""
    a, b = tokens(roster_name), tokens(other_name)
    if not a or not b:
        return 0, ""
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    al = _align(short, long_)
    if al is None:
        al2 = _align(long_, short)
        if al2 is None:
            return (1, "glued") if _glued(a, b) else (0, "")
        al = al2
    full_hits, extra, typos = al
    if full_hits == 0:
        return (1, "glued") if _glued(a, b) else (0, "")
    if extra + typos > 1:
        return 0, ""  # two weak points (an unexplained word, a typo) together: treat as different people
    if extra == 1:
        return 1, "extra_word"
    if typos:
        return 1, "typo"
    fa = sorted(t for t in a if len(t) > 1)
    fb = sorted(t for t in b if len(t) > 1)
    return (3, "") if fa == fb else (2, "")


def name_score(roster_name, other_name):
    return name_detail(roster_name, other_name)[0]


def block_keys(name):
    """Words used to find candidate matches quickly: every word of 3+ letters ("Das", "Rao"), plus shortened
    forms that catch glued names ("DWARAKISHG", "Santhanavijayan" vs "Santhana Vijayan")."""
    keys = set()
    for t in tokens(name):
        if len(t) >= 3:
            keys.add(t)
        if len(t) >= 6:
            keys.update({t[:-1], t[:-2], t[:5]})
    return keys
