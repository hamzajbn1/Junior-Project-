from flask import Flask, jsonify, request
from flask_cors import CORS
import requests
import urllib3
import time
import collections
import ssl

# ---------------------------------------------------------------------------
# Suppress SSL warnings for the self-signed university certificate
# ---------------------------------------------------------------------------
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
ssl._create_default_https_context = ssl._create_unverified_context

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SPARQL_ENDPOINT  = "https://192.167.149.12:9001/sparql/"
OPENALEX_BASE    = "https://api.openalex.org/works"

OPENALEX_HEADERS = {"User-Agent": "hamza.jbn123@gmail.com"}

app = Flask(__name__)
CORS(app)   # Allow React (localhost:3000) to call Flask (localhost:5000)


# ===========================================================================
# Section 1 – Core SPARQL helper
# ===========================================================================

def run_query(sparql_query):
    """
    POST a SPARQL SELECT query to the remote endpoint and return the
    results as a list of plain dicts  {varName: value, ...}.

    The endpoint must return  application/sparql-results+json.
    """
    response = requests.post(
        SPARQL_ENDPOINT,
        data={"query": sparql_query},
        headers={"Accept": "application/sparql-results+json"},
        verify=False,          # ignore SSL – local university IP
        timeout=60
    )
    response.raise_for_status()

    data   = response.json().get("results", {}).get("bindings", [])

    batch_ids = []
    for binding in data:
        new_row = {} 
        for k, v in binding.items():
            new_row[k] = v["value"]
        batch_ids.append(new_row)
        
    return batch_ids


# ===========================================================================
# Section 2 – Hybrid OpenAlex pipeline
# ===========================================================================

def sparql_paper_ids(entity_S, entity_P, entity_O):
    """
    Will create the SPARQL query that get the data from the endpoint, then it will send the data to the
    "run_query" function to get the id's that inside the json file.
    """
    query = f"""
    PREFIX cskg: <https://w3id.org/cskg/resource/>
    PREFIX cskgo: <https://w3id.org/cskg/ontology#>
    PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    PREFIX provo: <http://www.w3.org/ns/prov#>

    SELECT DISTINCT ?paperID
    FROM <https://w3id.org/cskg>
    WHERE {{
        ?statement rdf:subject   ?subject ;
                   rdf:predicate ?predicate ;
                   rdf:object    ?object ;
                   provo:wasDerivedFrom ?paperID .
        
        VALUES ?subject {{cskg:{entity_S}}}
        VALUES ?predicate {{cskgo:{entity_P}}}
        VALUES ?object    {{cskg:{entity_O}}}
    }}
    """
    raw_results = run_query(query)
    print(f"[DEBUG] Raw SPARQL results for {entity_S}/{entity_P}/{entity_O}: {raw_results}")

    # Do the specific ID extraction here!
    batch_ids = []
    for row in raw_results:
        if "paperID" in row:
            paper_id = row["paperID"].split("/")[-1]
            if paper_id.startswith("W"):
                batch_ids.append(paper_id)
                
    print(f"[DEBUG] Final batch_ids: {batch_ids}")

    return list(set(batch_ids))



# ===========================================================================
# Section 3 – Fetching from openAlex
# ===========================================================================

def fetch_openalex_works(paper_ids):
    # Will get the result of openalex.
    BATCH_SIZE = 100
    all_works  = []

    for start in range(0, len(paper_ids), BATCH_SIZE):
        batch = paper_ids[start : start + BATCH_SIZE]
        id_filter = "|".join(batch)           # "W111|W222|W333|..."

        url    = OPENALEX_BASE

        try:
            params = {
                "filter":   f"ids.openalex:{id_filter}",
                "select":   "id,publication_year,cited_by_count",
                "per_page": 100,
            }

            response = requests.get(url, params=params, headers=OPENALEX_HEADERS)
            response.raise_for_status()

            works = response.json().get("results", [])

            all_works.extend(works)
        except Exception as e:
            print(f"Failed batch lookup {e}")

        time.sleep(0.1)

    return all_works

# ===========================================================================
# Section 4 – return lists
# ===========================================================================

def aggregate_by_year(works):
    """
    Group a flat list of OpenAlex work objects by publication_year,
    count publications, and sum cited_by_count per year.

    Works missing a publication_year are silently skipped.

    Returns a list of dicts sorted chronologically:
        [{"year": 2018, "publications": 12, "citations": 450}, ...]
    """
    pub_counts  = collections.defaultdict(int)
    cite_sums   = collections.defaultdict(int)

    for work in works:
        year = work.get("publication_year")
        if year is None:
            continue                          
        
        # It counts the paper per year, pub_counts = {2020: 2, 2021: 1, ...}.
        pub_counts[year]  += 1
        cite_sums[year]   += work.get("cited_by_count", 0)

    rows = []
    for year in pub_counts:
        new_row = {
            "year": year,
            "publications": pub_counts[year],
            "citations": cite_sums[year]
        }
        rows.append(new_row)

    rows.sort(key=lambda r: r["year"])
    return rows


# ===========================================================================
# Section 5 – Main publications/citations function (now hybrid)
# ===========================================================================

def sparql_publications_citations(entity_S, entity_P, entity_O):
    """
    It will link the functon in one function and send it.

    Returns:
        [{"year": 2018, "publications": 12, "citations": 450}, ...]
    """
    paper_ids = sparql_paper_ids(entity_S, entity_P, entity_O)

    if not paper_ids:
        return []  

    works = fetch_openalex_works(paper_ids)

    return aggregate_by_year(works)

# ===========================================================================
# Section: Dynamic Relationship Endpoint
# ===========================================================================
@app.route("/api/relationship")
def api_relationship():
    """
    React calls this endpoint with S, P, O variables in the URL.
    Example: /api/relationship?s=MachineLearning&p=uses&o=RandomForest
    """
    subject = request.args.get("s")
    predicate = request.args.get("p")
    obj = request.args.get("o")

    trend_data = sparql_publications_citations(subject, predicate, obj)
    
    return jsonify({"data": trend_data})


def get_top_authors_via_openalex(entity_S, entity_P, entity_O):
    """
    1. Uses your existing SPARQL function to get the Paper IDs.
    2. Asks OpenAlex who wrote those specific papers.
    3. Counts them up and returns the top 5.
    """
    # Step 1: Get the IDs from the KG (This function already works perfectly!)
    paper_ids = sparql_paper_ids(entity_S, entity_P, entity_O)

    if not paper_ids:
        print(f"[DEBUG] No paper IDs found for {entity_S} -> {entity_P} -> {entity_O}")
        return []

    print(f"[DEBUG] Found {len(paper_ids)} papers. Querying OpenAlex for authors...")

    # Step 2: Fetch author data from OpenAlex
    BATCH_SIZE = 50
    author_counts = collections.defaultdict(int)

    for start in range(0, len(paper_ids), BATCH_SIZE):
        batch = paper_ids[start : start + BATCH_SIZE]
        id_filter = "|".join(batch)

        try:
            params = {
                "filter": f"ids.openalex:{id_filter}",
                "select": "authorships", # We ONLY want the authors, making it lightning fast
                "per_page": 50
            }

            response = requests.get(OPENALEX_BASE, params=params, headers=OPENALEX_HEADERS)
            response.raise_for_status()

            works = response.json().get("results", [])

            for work in works:
                for authorship in work.get("authorships", []):
                    author_name = authorship.get("author", {}).get("display_name")
                    if author_name:
                        author_counts[author_name] += 1

        except Exception as e:
            print(f"[ERROR] Failed author batch lookup: {e}")

        time.sleep(0.1) 

    # Step 4: Convert our dictionary counts into the exact format React wants
    author_list = []
    for name, count in author_counts.items():
        author_list.append({
            "name": name,
            "papers": count
        })

    # Sort the list from highest papers to lowest
    author_list.sort(key=lambda x: x["papers"], reverse=True)

    # Return only the top 5
    return author_list[:5]

@app.route("/api/authors/top")
def api_top_authors():
    """
    React calls this endpoint with S, P, O variables in the URL.
    """
    subject = request.args.get("s")
    predicate = request.args.get("p")
    obj = request.args.get("o")

    # Run the hybrid pipeline
    top_data = get_top_authors_via_openalex(subject, predicate, obj)
    
    return jsonify({"data": top_data})

if __name__ == "__main__":
    app.run(debug=True, port=5000)

