"""
CSKG → OpenAlex Automatic Pipeline (Week 3)

GOAL (what this script demonstrates):
- How to query a Knowledge Graph (CSKG) via a SPARQL endpoint
- How to parse structured SPARQL JSON results (bindings)
- How to extract OpenAlex Work IDs from CSKG provenance paper URIs
- How to enrich those IDs by calling OpenAlex API (authors, venue, year, title)
- How to save results (JSON for website/backend use, CSV for quick inspection)

WHY THIS MATTERS:
This is exactly the pipeline our website will use:
User selects an entity/material → backend queries CSKG → backend fetches metadata from OpenAlex → website visualizes trends.
"""

# ---------------------------
# Imports
# ---------------------------

import time        # used for time.sleep(...) to pause between API calls
import csv         # used to write outputs in CSV format
import json        # used to write outputs in JSON format
import requests    # used to send HTTP requests to SPARQL endpoint and OpenAlex API
import urllib3     # used to suppress warnings when SSL verification is disabled


# ==========================================================
# CONFIGURATION
# ==========================================================

SPARQL_ENDPOINT = "https://192.167.149.12:9001/sparql/"  # the CSKG SPARQL endpoint URL (internal)
GRAPH_IRI = "https://w3id.org/cskg"                      # graph/dataset identifier inside the triple store

MATERIAL_SLUG = "twitter"  # the CSKG entity slug to query: cskg:twitter (change this to test other entities)
LIMIT = 50                 # how many rows to return from CSKG (use moderate values to test)

OPENALEX_BASE = "https://api.openalex.org/works/"  # OpenAlex endpoint for retrieving a "Work" by ID
SLEEP_SECONDS = 0.25                               # pause between OpenAlex requests to reduce API pressure
OPENALEX_MAILTO = ""                               # optional email for OpenAlex polite usage (can be blank)


# ==========================================================
# SSL / CERTIFICATE HANDLING
# ==========================================================

DISABLE_SSL_VERIFY = True
# True  → allow connecting even if endpoint uses self-signed certificate (common in university/internal servers)
# False → normal secure verification (what you would use in production)

if DISABLE_SSL_VERIFY:
    # When verify=False, requests prints an "InsecureRequestWarning"
    # This line suppresses that warning so output stays clean
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# ==========================================================
# SPARQL QUERY TEMPLATE
# ==========================================================

"""
SPARQL QUICK EXPLANATION:
- SPARQL is like SQL but for RDF knowledge graphs.
- RDF knowledge graphs store information as triples:
    subject  predicate  object

In our case we want:
- Tasks (?sub) that usesMaterial the chosen material (e.g., twitter)
- And the paper provenance (?paperID) that this statement was derived from

IMPORTANT IMPLEMENTATION DETAIL:
We do NOT use Python .format() here because SPARQL uses braces { } which causes conflicts.
Instead, we use placeholder tokens __MATERIAL__ and __LIMIT__ and replace them safely.
"""

SPARQL_QUERY_TEMPLATE = f"""
PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>        # RDF vocabulary
PREFIX cskg: <https://w3id.org/cskg/resource/>                   # CSKG resources namespace
PREFIX cskg-ont: <https://w3id.org/cskg/ontology#>               # CSKG ontology namespace
PREFIX provo: <http://www.w3.org/ns/prov#>                       # provenance vocabulary

SELECT ?sub (cskg-ont:usesMaterial as ?prop) ?obj ?paperID        # return task, relation, material, and paper id
FROM <{GRAPH_IRI}>                                               # which RDF graph/dataset to query
WHERE {{
    ?t rdf:subject ?sub ;                                        # ?sub is the subject of an RDF statement
       rdf:predicate cskg-ont:usesMaterial ;                     # the predicate is usesMaterial
       rdf:object cskg:__MATERIAL__ ;                            # the object is the chosen material entity
       provo:wasDerivedFrom ?paperID .                           # provenance: which paper this statement came from

    ?sub a cskg-ont:Task .                                       # ensure subject is a Task entity
    BIND(cskg:__MATERIAL__ as ?obj)                              # bind the chosen material into variable ?obj
}}
LIMIT __LIMIT__                                                  # limit results to avoid huge responses
""".strip()


# ==========================================================
# HELPER FUNCTIONS (small reusable pieces)
# ==========================================================

def uri_to_slug(uri: str) -> str:
    """
    PURPOSE:
    - Convert a full URI into a short readable "slug" (last part after the last /)

    EXAMPLE:
    - "https://w3id.org/cskg/resource/image_annotation" → "image_annotation"
    - "https://w3id.org/cskg/resource/W2089518936"      → "W2089518936"

    WHY:
    URIs are long and not nice for display or matching.
    We usually want just the final identifier.
    """
    # If uri is empty/None → return empty string
    if not uri:
        return ""

    # rsplit("/", 1) splits from the right side only once:
    # "a/b/c".rsplit("/", 1) = ["a/b", "c"]
    # [-1] picks the last element "c"
    return uri.rsplit("/", 1)[-1]


def paper_uri_to_work_id(paper_uri: str) -> str:
    """
    PURPOSE:
    - Extract OpenAlex Work ID from CSKG paper URI (provenance field)

    EXAMPLE:
    - "https://w3id.org/cskg/resource/W2089518936" → "W2089518936"

    VALIDATION:
    - OpenAlex Work IDs start with 'W' followed by digits.
    """
    wid = uri_to_slug(paper_uri)  # extract last part of URI

    # validate pattern: starts with W and rest are digits
    if wid.startswith("W") and wid[1:].isdigit():
        return wid

    # return empty string if not a valid Work ID
    return ""


# ==========================================================
# SPARQL QUERY EXECUTION (CSKG)
# ==========================================================

def run_sparql_query(material_slug: str, limit: int) -> list[dict]:
    """
    PURPOSE:
    - Build a SPARQL query for a chosen material and limit
    - Send it to the SPARQL endpoint
    - Parse SPARQL JSON response
    - Return list of rows ("bindings")

    PARAMETERS:
    material_slug: str
        e.g., "twitter" (means cskg:twitter)
    limit: int
        e.g., 50 (maximum number of rows)

    RETURNS:
    list of dict rows in SPARQL JSON "bindings" format
    """

    # Replace placeholder tokens with actual values
    query = (SPARQL_QUERY_TEMPLATE
             .replace("__MATERIAL__", material_slug)  # insert material entity slug
             .replace("__LIMIT__", str(limit)))       # insert numeric limit as string

    # Print the query for transparency/debugging
    # (Useful to show supervisor exactly what was executed)
    print("\n--- SPARQL QUERY SENT ---")
    print(query)
    print("--- END QUERY ---\n")

    # HTTP headers tell the server what response format we accept
    headers = {
        "Accept": "application/sparql-results+json"  # request SPARQL results as JSON
    }

    # URL query parameters sent to the endpoint
    # requests will encode these into: ?query=...&format=json
    params = {
        "query": query,    # the SPARQL query text
        "format": "json"   # request JSON output
    }

    # Send HTTP GET request to endpoint
    resp = requests.get(
        SPARQL_ENDPOINT,              # endpoint URL
        params=params,                # query parameters
        headers=headers,              # headers with Accept type
        timeout=60,                   # stop if it takes more than 60 seconds
        verify=not DISABLE_SSL_VERIFY # verify SSL cert unless disabled
    )

    # If status code is not 200 OK, raise an exception (good for debugging)
    resp.raise_for_status()

    # Convert response JSON string → Python dictionary
    data = resp.json()

    # SPARQL JSON structure looks like:
    # {
    #   "head": {"vars": [...]},
    #   "results": {"bindings": [ {...}, {...} ]}
    # }
    bindings = data.get("results", {}).get("bindings", [])

    return bindings  # list of result rows


# ==========================================================
# OPENALEX REQUESTS (Metadata Enrichment)
# ==========================================================

def openalex_get_work(work_id: str) -> dict:
    """
    PURPOSE:
    - Retrieve OpenAlex "work" metadata using Work ID (W...)
    - Example URL: https://api.openalex.org/works/W2089518936

    PARAMETERS:
    work_id: str
        OpenAlex Work ID starting with W

    RETURNS:
    dict (parsed JSON) containing OpenAlex metadata
    """
    url = OPENALEX_BASE + work_id  # build full endpoint URL

    # Additional optional parameters to OpenAlex
    # mailto is recommended for polite use
    params = {}
    if OPENALEX_MAILTO:
        params["mailto"] = OPENALEX_MAILTO

    # Send the API request
    resp = requests.get(
        url,           # OpenAlex endpoint URL
        params=params, # query parameters (optional)
        timeout=30     # stop if OpenAlex doesn't respond within 30 seconds
    )

    # Raise error for non-success responses (e.g., 404, 429)
    resp.raise_for_status()

    # Return JSON response as Python dict
    return resp.json()


def extract_authors(oa_json: dict) -> list[str]:
    """
    PURPOSE:
    - Extract list of author names from OpenAlex JSON response

    FORMAT EXPLANATION:
    oa_json: dict
        This is a Python dictionary that represents a JSON object.
        requests.get(...).json() returns Python dict/list equivalents:
          JSON object  → dict
          JSON array   → list

    OpenAlex structure:
    oa_json["authorships"] is a list (array) like:
    [
      {
        "author": {"display_name": "Philip J. McParlane", ...},
        ...
      },
      ...
    ]
    """
    authors = []  # will store author display_name strings

    # oa_json.get("authorships", []) returns list if exists, otherwise empty list
    for authorship in oa_json.get("authorships", []):
        # authorship is a dict for each author contribution

        author_obj = authorship.get("author") or {}
        # some entries might be missing "author", so we use {} if None

        name = author_obj.get("display_name")
        # display_name is the human-readable author name

        if name:
            authors.append(name)  # store name

    return authors


# ==========================================================
# MAIN PIPELINE (CSKG → OpenAlex → Outputs)
# ==========================================================

def main() -> None:
    """
    The main function orchestrates the full workflow.

    Steps:
    1) Query CSKG for tasks that use MATERIAL_SLUG
    2) Extract Work IDs from the provenance paper URIs
    3) Call OpenAlex for each Work ID and enrich metadata
    4) Save results to JSON and CSV
    """

    # Step 1: Query CSKG
    print(f"Querying CSKG for material '{MATERIAL_SLUG}' (LIMIT={LIMIT})")
    bindings = run_sparql_query(MATERIAL_SLUG, LIMIT)

    # If SPARQL returned nothing, stop early
    if not bindings:
        print("No results returned from CSKG endpoint.")
        return

    print(f"Retrieved {len(bindings)} SPARQL rows.")

    # Step 2: Extract task + Work ID from SPARQL bindings
    items = []  # list of dicts: each dict contains task, work_id, paper_uri, etc.

    for row in bindings:
        # Each row is a dict in SPARQL binding format, like:
        # row["sub"]["value"] = "https://w3id.org/cskg/resource/image_annotation"
        # row["paperID"]["value"] = "https://w3id.org/cskg/resource/W2089518936"

        sub_uri = row.get("sub", {}).get("value", "")          # task URI
        paper_uri = row.get("paperID", {}).get("value", "")    # provenance paper URI

        task_slug = uri_to_slug(sub_uri)                       # shorten the task URI into a readable name
        work_id = paper_uri_to_work_id(paper_uri)              # extract OpenAlex Work ID

        # skip rows that do not contain a valid work id
        if not work_id:
            continue

        # store clean structured item
        items.append({
            "material": MATERIAL_SLUG,  # the material used as filter
            "task": task_slug,          # task label
            "work_id": work_id,         # OpenAlex identifier
            "paper_uri": paper_uri      # original URI (useful for traceability)
        })

    # If no items were extracted, stop
    if not items:
        print("No valid Work IDs extracted from SPARQL results.")
        return

    print(f"Extracted {len(items)} OpenAlex Work IDs. Fetching OpenAlex metadata...")

    # Step 3: Enrich each Work ID via OpenAlex
    results = []  # final enriched output list

    for i, item in enumerate(items, start=1):
        wid = item["work_id"]  # OpenAlex ID for this paper

        try:
            # call OpenAlex API
            oa = openalex_get_work(wid)

            # extract a list of authors
            authors = extract_authors(oa)

            # build a record (these are likely fields for visualization later)
            record = {
                "material": item["material"],  # material the task uses
                "task": item["task"],          # task name
                "work_id": wid,                # OpenAlex id
                "title": oa.get("title"),      # paper title
                "year": oa.get("publication_year"),  # publication year (key for trend charts)
                "venue": (oa.get("host_venue") or {}).get("display_name"),  # journal/conference name
                "authors": authors,            # list of author names
                "openalex_url": oa.get("id")   # OpenAlex canonical URL
            }

            results.append(record)  # store record in the final results list

            # print progress so user sees it's working
            first_author = authors[0] if authors else "No authors"
            print(f"[{i}/{len(items)}] OK {wid} → {first_author}")

        except Exception as e:
            # catch any issues (network issues, 404, parsing errors, etc.)
            print(f"[{i}/{len(items)}] ERROR {wid}: {e}")

        # pause between calls (polite usage and avoids rate limiting)
        time.sleep(SLEEP_SECONDS)

    # Step 4: Save outputs for inspection and future integration
    # JSON is best for websites/backends; CSV is best for quick Excel viewing.

    json_file = "openalex_results.json"
    with open(json_file, "w", encoding="utf-8") as f:
        # json.dump converts Python list/dict -> JSON text
        json.dump(results, f, ensure_ascii=False, indent=2)

    csv_file = "openalex_results.csv"
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)  # creates a CSV writer object

        # first row in CSV is the header row (column names)
        writer.writerow([
            "material", "task", "work_id", "year", "venue", "title", "authors", "openalex_url"
        ])

        # each record becomes one CSV row
        for r in results:
            writer.writerow([
                r["material"],
                r["task"],
                r["work_id"],
                r["year"],
                r["venue"],
                r["title"],
                "; ".join(r["authors"]),  # convert authors list into single string separated by '; '
                r["openalex_url"]
            ])

    print("\nPipeline finished successfully.")
    print(f"Saved JSON: {json_file}")
    print(f"Saved CSV:  {csv_file}")


# ==========================================================
# ENTRY POINT (when you run the file)
# ==========================================================

if __name__ == "__main__":
    # This block runs only when you execute the script directly:
    # python cskg_to_openalex_authors.py
    # It does NOT run if the file is imported as a module.
    main()