from flask import Flask, jsonify, request
from flask_cors import CORS
import requests
import urllib3
import time
import collections

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SPARQL_ENDPOINT  = "https://192.167.149.12:9001/sparql/"
OPENALEX_BASE    = "https://api.openalex.org/works"

OPENALEX_HEADERS = {"User-Agent": "hamza.jbn123@gmail.com"}

app = Flask(__name__)
CORS(app)   # Allow React (localhost:3000) to call Flask (localhost:5000)

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

def sparql_paper_ids(entity_S, entity_P, entity_O):
    """
    Will create the SPARQL query that get the data from the endpoint, then it will send the data to the
    "run_query" function to get the id's that inside the json file.
    """
    query = f"""
    PREFIX cskg: <https://w3id.org/cskg/resource/>
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
        VALUES ?predicate {{cskg:{entity_P}}}
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


def aggregate_by_year(works):
    """
    Group a flat list of OpenAlex work objects by publication_year,
    count publications, and sum cited_by_count per year.

    Works missing a publication_year are silently skipped.

    Returns a list of dicts sorted chronologically:
        [{"year": 2018, "publications": 12, "citations": 450}, ...]
    """
    # "defaultdict": This dictionary will automatically gives 0 if the key does not exist.
    pub_counts  = collections.defaultdict(int)
    cite_sums   = collections.defaultdict(int)

    for work in works:
        year = work.get("publication_year")
        if year is None:
            continue                          # skip works with no year
        
        # It counts the paper per year, pub_counts = {2020: 2, 2021: 1, ...}.
        pub_counts[year]  += 1
        cite_sums[year]   += work.get("cited_by_count", 0) # calculate the citations for the specific year.

    rows = []
    for year in pub_counts:
        new_row = {
            "year": year,
            "publications": pub_counts[year],
            "citations": cite_sums[year]
        }
        rows.append(new_row)

    # The code means: For every row you check, grab the number inside the 'year' bucket, and use THAT
    # number to do the sorting.
    rows.sort(key=lambda r: r["year"])
    return rows

def sparql_publications_citations(entity_S, entity_P, entity_O):
    """
    It will link the functon in one function and send it.

    Returns:
        [{"year": 2018, "publications": 12, "citations": 450}, ...]
    """
    # Step 1 – SPARQL: get raw OpenAlex Paper IDs from the KG
    paper_ids = sparql_paper_ids(entity_S, entity_P, entity_O)

    if not paper_ids:
        return []   # No IDs found; nothing to query

    # Step 2 – OpenAlex: fetch work metadata in batches
    works = fetch_openalex_works(paper_ids)

    # Step 3 – Python: aggregate into year-level buckets
    return aggregate_by_year(works)

@app.route("/api/relationship")
def api_relationship():
    """
    React calls this endpoint with S, P, O variables in the URL.
    Example: /api/relationship?s=MachineLearning&p=uses&o=RandomForest
    """
    # Grab the variables from the URL
    subject = request.args.get("s")
    predicate = request.args.get("p")
    obj = request.args.get("o")

    # Run your hybrid pipeline
    trend_data = sparql_publications_citations(subject, predicate, obj)
    
    # Send just this specific timeline back to React
    return jsonify({"data": trend_data})


if __name__ == "__main__":
    app.run(debug=True, port=5000)

