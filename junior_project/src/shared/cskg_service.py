"""Shared live CS-KG resolver and exact directed evidence retrieval."""
import json
import os
import re
import unicodedata
from difflib import SequenceMatcher
import requests
import urllib3
from . import ServiceError

SPARQL_ENDPOINT = "https://192.167.149.12:9001/sparql/"
GRAPH = "https://w3id.org/cskg"
RESOURCE = "https://w3id.org/cskg/resource/"
ONTOLOGY = "https://w3id.org/cskg/ontology#"
SEARCH_TIMEOUT = 25       # seconds; a slow search is abandoned, not left hanging
RELATION_TIMEOUT = 30
NARROW_LIMIT = 60         # all-words search: few matches expected
WIDE_LIMIT = 300          # any-word fallback: needs room before local ranking
MAX_CANDIDATES = 8

# The seven approved connections. Fixed list, server-enforced: the researcher
# picks a friendly name and can never send an arbitrary predicate.
CONNECTIONS = [
    {"id": "usesMethod", "label": "Uses a technique"},
    {"id": "includesMethod", "label": "Includes a technique"},
    {"id": "adaptsMethod", "label": "Customizes a technique"},
    {"id": "improvesMethod", "label": "Improves a technique"},
    {"id": "analyzesMethod", "label": "Studies a technique"},
    {"id": "usesMaterial", "label": "Uses a resource"},
    {"id": "usesMetric", "label": "Uses a measurement criterion"},
]
ALLOWED_PREDICATES = {item["id"] for item in CONNECTIONS}

PREFIXES = """
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX prov: <http://www.w3.org/ns/prov#>
"""
def run_query(query, timeout):
    """One network attempt. Agent 2's RunContext owns the retry budget."""
    try:
        verify = os.environ.get("CSKG_CA_BUNDLE") or False
        if not verify:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        response = requests.post(
            os.environ.get("CSKG_ENDPOINT", SPARQL_ENDPOINT),
            data={"query": PREFIXES + query},
            headers={"Accept": "application/sparql-results+json"},
            verify=verify, timeout=(min(10, timeout), timeout),
        )
        response.raise_for_status()
        rows = response.json()["results"]["bindings"]
        if not isinstance(rows, list):
            raise ValueError("Invalid graph response")
        return [{key: value["value"] for key, value in row.items()} for row in rows]
    except requests.exceptions.Timeout as exc:
        raise ServiceError("__TIMEOUT__", 504, code="graph_timeout") from exc
    except requests.RequestException as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        raise ServiceError("The knowledge graph is unavailable. Check the connection and try again.",
                           503, retryable=status is None or status == 429 or status >= 500,
                           code="graph_unavailable") from exc
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise ServiceError("The knowledge graph returned an unreadable response.",
                           502, code="graph_response") from exc


def local_name(uri):
    """https://w3id.org/cskg/resource/random_forest -> random_forest"""
    return uri.rsplit("/", 1)[-1]


def normalize(text):
    """Lowercase, split camelCase, and treat _ - and space as the same thing."""
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)
    text = re.sub(r"[_\-]+", " ", text)
    return " ".join(text.casefold().split())


def safe_tokens(text):
    """Strip everything that is not a letter, digit, or space.

    This is what makes string interpolation into SPARQL safe below: after
    this, a token cannot contain a quote, brace, or angle bracket.
    """
    cleaned = re.sub(r"[^a-z0-9 ]+", " ", normalize(text))
    return [token for token in cleaned.split() if token]


def search_query(tokens, joiner, limit):
    """Build a search over the entity's local name only.

    STRAFTER strips the namespace, so searching for 'resource' or 'cskg'
    does not match every entity in the graph.
    """
    name = 'LCASE(STRAFTER(STR(?e), "/resource/"))'
    tests = joiner.join(f'CONTAINS({name}, "{token}")' for token in tokens)
    return f"""
SELECT DISTINCT ?e FROM <{GRAPH}> WHERE {{
  {{ ?st rdf:subject ?e }} UNION {{ ?st rdf:object ?e }}
  FILTER({tests})
}} LIMIT {limit}"""


def fetch_entities(tokens, joiner, limit, query_fn=None):
    rows = (query_fn or run_query)(search_query(tokens, joiner, limit), SEARCH_TIMEOUT)
    names = []
    for row in rows:
        if not isinstance(row.get("e"), str) or not row["e"].startswith(RESOURCE):
            continue
        name = local_name(row["e"])
        # Paper references should not reach this query, but never offer one
        # as a concept if the graph shape ever changes.
        if name and not re.fullmatch(r"W\d+", name):
            names.append(name)
    return names


def rank(names, text):
    """Score graph-supplied names against the researcher's words.

    Nothing here invents an entity: every name scored came from CS-KG.
    """
    needle = normalize(text)
    wanted = set(needle.split())
    scored = []
    for name in set(names):
        readable = normalize(name)
        if readable == needle:
            score = 1.0
        else:
            score = SequenceMatcher(None, needle, readable).ratio()
            present = wanted & set(readable.split())
            if present:
                # Reward covering the researcher's words; prefer the shorter
                # name so machine_learning beats machine_learning_based_model.
                score = max(score, 0.55 + 0.35 * (len(present) / len(wanted)))
                score -= min(0.12, 0.012 * max(0, len(readable.split()) - len(wanted)))
        scored.append((score, readable, name))
    scored.sort(key=lambda item: (-item[0], len(item[2]), item[2]))
    return scored


def resolve_entities(text, query_fn=None):
    """Find CS-KG concepts matching the researcher's words.

    Three tiers, each only reached when the one before found nothing:
      1. every word must appear   - precise, and the usual case
      2. any word may appear      - one word was mistyped
      3. prefix of the longest word - most words were mistyped
    """
    tokens = safe_tokens(text)
    if not tokens:
        raise ServiceError("Enter a concept to search for.", 400)

    names = fetch_entities(tokens, " && ", NARROW_LIMIT, query_fn)
    match = "exact"

    if not names and len(tokens) > 1:
        names = fetch_entities(tokens, " || ", WIDE_LIMIT, query_fn)
        match = "suggestion"

    if not names:
        longest = max(tokens, key=len)
        if len(longest) >= 5:
            names = fetch_entities([longest[:4]], " && ", WIDE_LIMIT, query_fn)
            match = "suggestion"

    if not names:
        return {"candidates": [], "selected": None}

    scored = rank(names, text)
    candidates = [
        {
            "id": RESOURCE + name,
            "label": readable,
            "name": name,
            "match": "exact" if score == 1.0 else match,
        }
        for score, readable, name in scored[:MAX_CANDIDATES]
    ]
    # Select automatically only when the graph gave exactly one perfect match.
    perfect = [item for item, (score, _, _) in zip(candidates, scored) if score == 1.0]
    return {"candidates": candidates, "selected": perfect[0] if len(perfect) == 1 else None}


# ---------------------------------------------------------------------------
# Relationship evidence
# ---------------------------------------------------------------------------

def validate_concept(value, side):
    if not isinstance(value, str) or not value.startswith(RESOURCE):
        raise ServiceError(f"Select a verified {side} concept.", 400)
    if not re.fullmatch(r"[A-Za-z0-9_.\-%]+", local_name(value)):
        raise ServiceError(f"The {side} concept identifier is not valid.", 400)
    return value

def paper_ids(subject, predicate, obj, query_fn=None):
    """Overview compatibility adapter over the same evidence function."""
    evidence = get_evidence(subject, predicate, obj, query_fn=query_fn, paginate=False)
    return set(evidence["work_ids"]), len(evidence["unmapped_references"])


def validate_connection(value):
    """Accept the controlled ID, its exact IRI, or its friendly label."""
    if isinstance(value, str):
        for item in CONNECTIONS:
            if value == item["id"] or value == ONTOLOGY + item["id"] or value.casefold().strip() == item["label"].casefold():
                return item["id"]
    raise ServiceError("Select an approved connection.", 400, code="invalid_connection")


def query_for_task(context, step):
    from hashlib import sha256

    def query(text, timeout):
        key = "cskg:" + sha256(text.encode()).hexdigest()[:16]
        return context.execute(key, step, lambda: run_query(text, min(timeout, context.remaining())))
    return query


def find_relations(subject, predicate, obj, *, query_fn=None):
    """Check exact direction and approved predicate; never silently broaden it."""
    validate_concept(subject, "first")
    validate_concept(obj, "second")
    predicate = validate_connection(predicate)
    rows = (query_fn or run_query)(f"""
SELECT ?statement FROM <{GRAPH}> WHERE {{
  ?statement rdf:subject <{subject}> ;
             rdf:predicate <{ONTOLOGY}{predicate}> ;
             rdf:object <{obj}> .
}} LIMIT 1""", RELATION_TIMEOUT)
    return {"found": bool(rows), "subject": subject, "predicate": predicate, "object": obj,
            "warnings": ["Entity type compatibility is unavailable from the current resolver; the exact directed graph statement is checked instead."]}


def get_evidence(subject, predicate, obj, *, query_fn=None, page_size=2000, paginate=True):
    """Keyset pagination avoids silently treating a truncated query as complete."""
    validate_concept(subject, "first")
    validate_concept(obj, "second")
    predicate = validate_connection(predicate)
    query = query_fn or run_query
    references, cursor = set(), ""
    for _ in range(100):
        paging = f"FILTER(STR(?paperID) > {json.dumps(cursor)})" if paginate else ""
        tail = f"ORDER BY STR(?paperID) LIMIT {page_size}" if paginate else ""
        rows = query(f"""
SELECT DISTINCT ?paperID FROM <{GRAPH}> WHERE {{
  ?statement rdf:subject   <{subject}> ; rdf:predicate <{ONTOLOGY}{predicate}> ;
             rdf:object    <{obj}> ; prov:wasDerivedFrom ?paperID .
  {paging}
}} {tail}""", RELATION_TIMEOUT)
        if not rows:
            break
        values = [row.get("paperID") for row in rows]
        if any(not isinstance(value, str) for value in values):
            raise ServiceError("The graph returned unreadable paper references.", 502, code="evidence_response")
        next_cursor = max(values)
        if next_cursor <= cursor:
            raise ServiceError("Evidence pagination did not advance; completeness could not be established.",
                               502, retryable=False, code="pagination_stalled")
        references.update(values)
        cursor = next_cursor
        if not paginate:
            break
    else:
        raise ServiceError("The evidence exceeded this run's retrieval limit.", 502,
                           retryable=False, code="evidence_limit")
    ids, unmapped = set(), []
    for reference in sorted(references):
        # Only verified source namespaces may be converted, never arbitrary URLs.
        match = re.fullmatch(r"(?:https://w3id\.org/cskg/resource/|https?://openalex\.org/)(W\d+)", reference)
        if match:
            ids.add(match.group(1))
        else:
            unmapped.append(reference)
    return {"work_ids": sorted(ids), "references": sorted(references), "unmapped_references": unmapped,
            "subject": subject, "predicate": predicate, "object": obj, "complete": True}
