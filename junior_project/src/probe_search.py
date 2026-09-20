"""a stopwatch. Sends three test searches to CS-KG and prints how long each took. Run once, read the numbers, done.
"""
import time

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

ENDPOINT = "https://192.167.149.12:9001/sparql/"
GRAPH = "https://w3id.org/cskg"
RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
NEEDLE = "random"

TESTS = {
    "plain CONTAINS": f'''
SELECT DISTINCT ?e FROM <{GRAPH}> WHERE {{
  ?st <{RDF}subject> ?e .
  FILTER(CONTAINS(LCASE(STR(?e)), "{NEEDLE}"))
}} LIMIT 50''',

    "full-text bif:contains": f'''
SELECT DISTINCT ?e FROM <{GRAPH}> WHERE {{
  ?st <{RDF}subject> ?e .
  ?e bif:contains "{NEEDLE}"
}} LIMIT 50''',

    "objects too (CONTAINS)": f'''
SELECT DISTINCT ?e FROM <{GRAPH}> WHERE {{
  {{ ?st <{RDF}subject> ?e }} UNION {{ ?st <{RDF}object> ?e }}
  FILTER(CONTAINS(LCASE(STR(?e)), "{NEEDLE}"))
}} LIMIT 50''',
}

def run(name, query):
    started = time.time()
    try:
        response = requests.post(ENDPOINT, data={"query": query},
                                 headers={"Accept": "application/sparql-results+json"},
                                 verify=False, timeout=180)
        response.raise_for_status()
        rows = response.json()["results"]["bindings"]
    except Exception as exc:
        print(f"  {name:26} FAILED after {time.time() - started:.1f}s")
        print(f"     {str(exc)[:200]}")
        return
    elapsed = time.time() - started
    print(f"  {name:26} OK  {len(rows):>3} rows in {elapsed:>5.1f}s")
    for row in rows[:6]:
        print(f"       - {row['e']['value'].rsplit('/', 1)[-1]}")

def main():
    print(f"\nSearching CS-KG for entity names containing '{NEEDLE}'")
    print(f"Endpoint: {ENDPOINT}\n")
    for name, query in TESTS.items():
        run(name, query)
    print("\nSend these timings back.\n")


if __name__ == "__main__":
    main()














