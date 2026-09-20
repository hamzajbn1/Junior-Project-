"""Research Trend Explorer - Overview backend.
"""
from flask import Flask, jsonify, request
from flask_cors import CORS
import requests
import urllib3
import collections
import re
import unicodedata
from datetime import datetime
from difflib import SequenceMatcher

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
app = Flask(__name__)
CORS(app)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SPARQL_ENDPOINT  = "https://192.167.149.12:9001/sparql/"
GRAPH = "https://w3id.org/cskg"
RESOURCE = "https://w3id.org/cskg/resource/"
ONTOLOGY = "https://w3id.org/cskg/ontology#"

OPENALEX_BASE    = "https://api.openalex.org/works"
OPENALEX_HEADERS = {"User-Agent": "hamza.jbn123@gmail.com"}

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

# Error that meant for the researcher to read.
class ServiceError(Exception):
    def __init__(self, message, status=503):
        super().__init__(message)
        self.status = status

@app.errorhandler(ServiceError)
def handle_service_error(error):
    return jsonify({"error": str(error)}), error.status

#----------------------------------------------------------------------
# SPARQL
#----------------------------------------------------------------------
def run_query(query, timeout):
    """
    POST a SELECT query and return its rows as plain dicts.
    """
    try:
      response = requests.post(
        SPARQL_ENDPOINT,
        data={"query": PREFIXES + query},
        headers={"Accept": "application/sparql-results+json"},
        verify=False,          # ignore SSL – local university IP
        timeout = (10, timeout),
      )
      response.raise_for_status()
      rows = response.json()["results"]["bindings"]

    except requests.exceptions.Timeout as exc:
        raise ServiceError("__TIMEOUT__", 504) from exc
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        raise ServiceError(
            "The knowledge graph is unavailable. Check the connection and try again."
        ) from exc
    return [{key: value["value"] for key, value in row.items()} for row in rows]


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
    """Strip everything that is not a letter, digit, or space."""
    cleaned = re.sub(r"[^a-z0-9 ]+", " ", normalize(text))
    return [token for token in cleaned.split() if token]

def search_query(tokens, joiner, limit):
    """Build a search over the entity's local name only.

    STRAFTER strips the namespace, so searching for 'resource' or 'cskg'
    does not match every entity in the graph.
    """
    name='LCASE(STRAFTER(STR(?e), "/resource/"))'
    tests = joiner.join(f'CONTAINS({name}, "{token}")' for token in tokens)
    return f"""
            SELECT DISTINCT ?e FROM <{GRAPH}> WHERE {{
            {{ ?st rdf:subject ?e }} UNION {{ ?st rdf:object ?e }}
            FILTER({tests})
            }} LIMIT {limit}"""

def fetch_entities(tokens, joiner, limit):
    rows = run_query(search_query(tokens, joiner, limit), SEARCH_TIMEOUT)
    names = []
    for row in rows:
        name = local_name(row["e"])
        if name and not re.fullmatch(r"W\d+", name):
            names.append(name)
    return names

def rank(names, text):
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
                score = max(score, 0.55 + 0.35 * (len(present) / len(wanted)))
                score -= min(0.12, 0.012 * max(0, len(readable.split()) - len(wanted)))
        scored.append((score, readable, name))
    scored.sort(key=lambda item: (-item[0], len(item[2]), item[2]))
    return scored


def resolve_entities(text):
    """Find CS-KG concepts matching the researcher's words.

    Three tiers, each only reached when the one before found nothing:
      1. every word must appear   - precise, and the usual case
      2. any word may appear      - one word was mistyped
      3. prefix of the longest word - most words were mistyped
    """
    tokens = safe_tokens(text)
    if not tokens:
        raise ServiceError("Enter a concept to search for.", 400)

    names = fetch_entities(tokens, " && ", NARROW_LIMIT)
    match = "exact"

    if not names and len(tokens) > 1:
        names = fetch_entities(tokens, " || ", WIDE_LIMIT)
        match = "suggestion"

    if not names:
        longest = max(tokens, key=len)
        if  len(longest) >=5:
            names = fetch_entities([longest[:4]], " && ", WIDE_LIMIT)
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
    # It will select automatically when the graph only give one perfect match.
    perfect = [item for item, (score, _, _) in zip(candidates, scored) if score == 1.0]
    return {"candidates": candidates, "selected": perfect[0] if len(perfect) == 1 else None}

def validate_concept(value, side):
    if not isinstance(value, str) or not value.startswith(RESOURCE):
        raise ServiceError(f"Select a verified {side} concept.", 400)
    if not re.fullmatch(r"[A-Za-z0-9_.\-%]+", local_name(value)):
        raise ServiceError(f"The {side} concept identifier is not valid.", 400)
    return value

def paper_ids(subject, predicate, obj):
    rows = run_query(f"""
      SELECT DISTINCT ?paperID FROM <{GRAPH}> WHERE {{
      ?statement rdf:subject    <{subject}>;
                 rdf:predicate  <{ONTOLOGY}{predicate}>;
                 rdf:object     <{obj}>;
                 prov:wasDerivedFrom ?paperID . 
      }}""", RELATION_TIMEOUT)

    ids, unusable = set(), 0
    for row in rows:
        name = local_name(row["paperID"])
        if re.fullmatch(r"W\d+", name):
            ids.add(name)
        else:
            unusable += 1
    return ids, unusable

def fetch_openalex_years(ids):
    """Ask OpenAlex for each paper's publication year."""
    years, failed = {}, set()
    ordered = sorted(ids)
    for start in range (0, len(ordered), 50):
        batch = ordered[start:start + 50]
        try:
            response = requests.get(
                OPENALEX_BASE,
                params={
                    "filter": "ids.openalex:" + "|".join(batch),
                    "select": "id,publication_year", 
                    "per_page": 50,
                },
                headers=OPENALEX_HEADERS,
                timeout=(10, 45),
            )
            response.raise_for_status()
            for work in response.json().get("results", []):
                identifier = local_name(work.get("id", ""))
                if identifier in batch:
                    years[identifier] = work.get("publication_year")
        except (requests.RequestException, ValueError, KeyError, TypeError):
            failed.update(batch)
    if ordered and len(failed) == len(ordered):
        raise ServiceError(
            "Publication details could not be retrieved from OpenAlex. Check the internet connection and try again.",
            502,
        )
    return years, failed

def bucket(counts):
    years = sorted(counts)
    span = years[-1] - years[0] + 1
    size = 1 if span <= 15 else 2 if span <=30 else 5 

    rows, edge = [], years[0]
    while edge <= years[-1]:
        last = min(edge + size - 1, years[-1])
        rows.append({
            "label": str(edge) if size == 1 else f"{edge}–{last}",
            "start": edge,
            "end": last,
            "papers": sum(counts.get(year, 0) for year in range(edge, last + 1)),
        })
        edge += size
    return rows, size

def relationship_trend(subject, predicate, obj):
    if predicate not in ALLOWED_PREDICATES:
        raise ServiceError("Select an approved connection.", 400)
    validate_concept(subject, "first")
    validate_concept(obj, "second")

    references, unusable = paper_ids(subject, predicate, obj)
    if not references:
        return {"status": "no_relationship", "data": [], "total_papers": 0, "notes": []}

    years, failed = fetch_openalex_years(references)

    counts = collections.Counter()
    undated = 0
    current_year = datetime.now().year
    for identifier in references:
        year = years.get(identifier)
        if isinstance(year, int) and not isinstance(year, bool) and 1000 <= year <= current_year:
            counts[year] += 1
        else:
            undated += 1

    notes = []
    if undated:
        notes.append(f"{undated} of {len(references)} papers have no publication year on record and are not on the chart.")
    if unusable:
        notes.append(f"{unusable} paper references could not be matched to OpenAlex.")
    if failed:
        notes.append("Some OpenAlex requests failed, so the counts shown are a lower bound.")

    if not counts:
        return {"status": "no_years", "data": [], "total_papers": len(references) + unusable, "notes": notes}

    rows, size = bucket(counts)
    if size > 1:
        notes.append(f"Papers are grouped into {size}-year periods because the results span {max(counts) - min(counts) + 1} years.")
    if current_year in counts:
        notes.append(f"{current_year} is still in progress, so its count is partial.")

    return {
        "status": "ok",
        "data": rows,
        "bucket_size": size,
        "total_papers": len(references) + unusable,
        "charted_papers": sum(counts.values()),
        "notes": notes,
        "retrieved_at": datetime.now().isoformat(timespec="seconds"),
    }

#--------------------------------------------------------------------------
# Endpointes
#--------------------------------------------------------------------------

@app.get("/api/connections")
def api_connections():
    return jsonify({"connections": CONNECTIONS})

@app.get("/api/entities")
def api_etities():
    text = (request.args.get("q") or "").strip()
    if not 2 <= len(text) <=200:
        raise ServiceError("Enter between 2 and 200 characters.", 400)
    try: 
        return jsonify(resolve_entities(text))
    except ServiceError as error:
        if str(error) == "__TIMEOUT__":
            raise ServiceError(
                f"The search took longer than {SEARCH_TIMEOUT} seconds and was stopped. Try a longer or more specific word.",
                504,
            ) from error
        raise

@app.get("/api/relationship")
def api_relationship():
    try: 
        return jsonify(relationship_trend(
            request.args.get("s"),
            request.args.get("p"),
            request.args.get("o"),
        ))
    except ServiceError as error:
        if str(error) == "__TIMEOUT__":
            raise ServiceError(
                f"The knowledge graph took longer than {RELATION_TIMEOUT} seconds to answer and was stopped. Please try again.",
                504,
            ) from error
        raise

# Kept from the original project. No page uses it yet.
@app.get("/api/authors/top")
def api_top_authors():
    subject = validate_concept(request.args.get("s"), "first")
    obj = validate_concept(request.args.get("o"), "second")
    predicate = request.args.get("p")
    if predicate not in ALLOWED_PREDICATES:
        raise ServiceError("Select an approved connection.", 400)

    references, _ = paper_ids(subject, predicate, obj)
    counts = collections.Counter()
    ordered = sorted(references)
    for start in range(0, len(ordered), 50):
        batch = ordered[start:start + 50]
        try:
            response = requests.get(
                OPENALEX_BASE,
                params={"filter": "ids.openalex:" + "|".join(batch),
                        "select": "authorships", "per_page": 50},
                headers=OPENALEX_HEADERS, timeout=(10, 45))
            response.raise_for_status()
            for work in response.json().get("results", []):
                for authorship in work.get("authorships", []):
                    name = (authorship.get("author") or {}).get("display_name")
                    if name:
                        counts[name] += 1
        except (requests.RequestException, ValueError, KeyError, TypeError):
            continue
    return jsonify({"data": [{"name": name, "papers": total}
                             for name, total in counts.most_common(5)]})


if __name__ == "__main__":
    # threaded=True so one slow graph query does not block the next request.
    app.run(host="127.0.0.1", port=5000, threaded=True)
