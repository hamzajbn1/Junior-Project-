"""Research Trend Explorer - Overview backend.
"""
from flask import Flask, jsonify, request
from flask_cors import CORS
import os
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

def fetch_openalex_works(ids):
    """Retrieve one shared collection for all four charts, in batches of 50."""
    works, failed = {}, set()
    ordered = sorted(ids)
    for start in range (0, len(ordered), 50):
        batch = ordered[start:start + 50]
        params = {
            "filter": "ids.openalex:" + "|".join(batch),
            "select": "id,publication_year,display_name,cited_by_count,primary_location,authorships",
            "per_page": 50,
        }
        if os.environ.get("OPENALEX_API_KEY"):
            params["api_key"] = os.environ["OPENALEX_API_KEY"]
        try:
            response = requests.get(
                OPENALEX_BASE,
                params=params,
                headers=OPENALEX_HEADERS,
                timeout=(10, 45),
            )
            response.raise_for_status()
            results = response.json()["results"]
            if not isinstance(results, list):
                raise ValueError("Invalid OpenAlex results")

            for work in results:
                if not isinstance(work, dict) or not isinstance(work.get("id"), str):
                    continue
                identifier = local_name(work["id"])
                if identifier in batch:
                    works.setdefault(identifier, work)
        except (requests.RequestException, ValueError, KeyError, TypeError):
            failed.update(batch)

    if ordered and len(failed) == len(ordered):
        raise ServiceError(
            "Publication details could not be retrieved from OpenAlex. Check the internet connection and try again.",
            502,
        )
    return works, failed

def publication_year(work):
    year = work.get("publication_year")
    return year if type(year) is int and 1000 <= year <= datetime.now().year else None

def supporting_insights(references, works, failed, unusable=0):
    venues, countries, cited = {}, collections.Counter(), []

    coverage = {
        "requested_papers": len(references),
        "retrieved_papers": len(references & works.keys()),
        "unretrieved_papers": len(references - works.keys()),
        "unusable_references": unusable,
        "failed_papers": len(failed),
        "missing_venue_papers": 0,
        "missing_country_papers": 0,
        "partial_country_papers": 0,
        "possibly_truncated_authorship_papers": 0,
        "missing_citation_papers": 0,
        "missing_year_papers": 0,
    }

    for identifier in sorted(references):
        work = works.get(identifier, {})
        if publication_year(work) is None:
            coverage["missing_year_papers"] +=1

        location = work.get("primary_location")
        source = location.get("source") if isinstance(location, dict) else None
        source = source if isinstance(source, dict) else {}
        source_id, label = source.get("id"), source.get("display_name")

        if(isinstance(source_id, str)
           and re.fullmatch(r"https://openalex\.org/S\d+", source_id)
           and isinstance(label, str) and label.strip()
           and source.get("type") != "repository"):
           venue = venues.setdefault(source_id, {
               "id": source_id, "label": label.strip(), "papers": 0, "is_other": False,
           })
           venue["papers"] +=1
        else:
            coverage["missing_venue_papers"] += 1

        paper_countries = set()
        authorships = work.get("authorships")
        authorships = authorships if isinstance(authorships, list) else []
        incomplete = False

        for authorship in authorships:
            if not isinstance(authorship, dict):
                incomplete = True
                continue
            codes = authorship.get("countries")
            codes = list(codes) if isinstance(codes, list) else []
            institutions = authorship.get("institutions")

            if isinstance(institutions, list):
                codes.extend(item.get("country_code") for item in institutions if isinstance(item, dict))
            author_countries = {code.upper() for code in codes
                                if isinstance(code, str) and re.fullmatch(r"[A-Za-z]{2}", code)}
            if not author_countries:
                incomplete = True
            paper_countries.update(author_countries)

        countries.update(paper_countries)
        if not paper_countries:
            coverage["missing_country_papers"] += 1
        elif incomplete:
            coverage["partial_country_papers"] += 1

        if len(authorships) >= 100:
            coverage["possibly_truncated_authorship_papers"] += 1

        citations = work.get("cited_by_count")
        if type(citations) is int and citations >= 0:
            title = work.get("display_name")
            title = title.strip() if isinstance(title, str) else ""
            url = "https://openalex.org/" + identifier
            cited.append({"id": url, "title": title or f"Untitled paper ({identifier})",
                          "publication_year": publication_year(work),
                          "cited_by_count": citations, "url": url})
        else:
            coverage["missing_citation_papers"] += 1

    venue_rows = sorted(venues.values(), key=lambda row: (-row["papers"], normalize(row["label"]), row["id"]))
    venue_data = venue_rows[:5]
    if len(venue_rows) > 5:
        venue_data.append({"id": None, "label": "Other venues", "is_other": True,
                    "papers": sum(row["papers"] for row in venue_rows[5:])})
    country_rows = sorted(countries.items(), key=lambda row: (-row[1], row[0]))
    country_data = [{"country_code": code, "papers": count, "is_other": False}
                for code, count in country_rows[:5]]
    if len(country_rows) > 5:
        country_data.append({"country_code": None, "label": "Other countries", "is_other": True,
                    "papers": sum(count for _, count in country_rows[5:])})
    cited.sort(key=lambda row: (-row["cited_by_count"], normalize(row["title"]), row["id"]))
    partial = any(value for key, value in coverage.items()
            if key not in {"requested_papers", "retrieved_papers"})
    return {"venue_data": venue_data, "country_data": country_data,
            "top_cited_papers": cited[:5], "coverage": coverage,
            "metadata_status": "partial" if partial else "complete"}                                                               


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
        return {"status": "no_years" if unusable else "no_relationship", "data": [],
                "total_papers": unusable,
                "notes": [f"{unusable} paper references could not be matched to OpenAlex."] if unusable else [],
                **supporting_insights(set(), {}, set(), unusable)}

    works, failed = fetch_openalex_works(references)
    insights = supporting_insights(references, works, failed, unusable)

    counts = collections.Counter()
    undated = 0
    current_year = datetime.now().year
    for identifier in references:
        year = publication_year(works.get(identifier, {}))
        if year is not None:
            counts[year] += 1
        else:
            undated += 1

    notes = []
    if undated:
        notes.append(f"{undated} of {len(references)} papers have no publication year available in the retrieved metadata and are not on the yearly chart.")
    if unusable:
        notes.append(f"{unusable} paper references could not be matched to OpenAlex.")
    if failed:
        notes.append("Some OpenAlex requests failed, so the counts shown are a lower bound.")

    if not counts:
        return {"status": "no_years", "data": [], "total_papers": len(references) + unusable,
                "notes": notes, **insights}

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
        **insights,
    }

#--------------------------------------------------------------------------
# Endpointes
#--------------------------------------------------------------------------

@app.get("/api/connections")
def api_connections():
    return jsonify({"connections": CONNECTIONS})

@app.get("/api/entities")
def api_entities():
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
