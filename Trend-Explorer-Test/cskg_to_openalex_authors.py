import re
import time
import csv
import requests
from pathlib import Path
#  THis is a test
SPARQL_FILE = "sparql_2026-02-25_19-25-59Z.txt"
OPENALEX_BASE = "https://api.openalex.org/works/"
SLEEP_SECONDS = 0.25  # gentle rate-limit

def extract_work_ids_from_sparql_xml(text: str) -> list[str]:
    """
    Extracts OpenAlex Work IDs (W##########) from SPARQL XML results.
    Works with paperID URIs like:
    https://w3id.org/cskg/resource/W2089518936
    """
    # Capture W followed by digits
    work_ids = re.findall(r"\bW\d+\b", text)
    # Deduplicate while preserving order
    seen = set()
    unique = []
    for w in work_ids:
        if w not in seen:
            seen.add(w)
            unique.append(w)
    return unique

def get_authors_from_openalex(work_id: str) -> dict:
    """
    Calls OpenAlex and extracts title, year, venue, and author names.
    """
    url = OPENALEX_BASE + work_id
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    data = r.json()

    authors = []
    for a in data.get("authorships", []):
        author = a.get("author", {})
        name = author.get("display_name")
        if name:
            authors.append(name)

    return {
        "work_id": work_id,
        "title": data.get("title"),
        "year": data.get("publication_year"),
        "venue": (data.get("host_venue") or {}).get("display_name"),
        "authors": "; ".join(authors),
        "openalex_url": data.get("id"),
    }

def main():
    path = Path(SPARQL_FILE)
    if not path.exists():
        raise FileNotFoundError(
            f"Could not find '{SPARQL_FILE}'. Put it in the same folder as this script."
        )

    text = path.read_text(encoding="utf-8", errors="ignore")
    work_ids = extract_work_ids_from_sparql_xml(text)

    if not work_ids:
        print("No Work IDs found. Check the SPARQL file format.")
        return

    print(f"Found {len(work_ids)} OpenAlex Work IDs. Example: {work_ids[:5]}")

    results = []
    for i, wid in enumerate(work_ids, start=1):
        try:
            info = get_authors_from_openalex(wid)
            results.append(info)
            print(f"[{i}/{len(work_ids)}] OK {wid} -> {info['authors'][:60]}...")
        except requests.HTTPError as e:
            print(f"[{i}/{len(work_ids)}] ERROR {wid}: {e}")
        except Exception as e:
            print(f"[{i}/{len(work_ids)}] ERROR {wid}: {e}")

        time.sleep(SLEEP_SECONDS)

    # Save CSV
    out_file = "openalex_authors_output.csv"
    with open(out_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["work_id", "title", "year", "venue", "authors", "openalex_url"],
        )
        writer.writeheader()
        writer.writerows(results)

    print(f"\nDone. Saved: {out_file}")

if __name__ == "__main__":

    main()
