import requests

work_id = "W2089518936"  # replace with any W... you got from CS-KG
url = f"https://api.openalex.org/works/{work_id}"

r = requests.get(url, timeout=30)
r.raise_for_status()
data = r.json()

print("Title:", data.get("title"))
print("Year:", data.get("publication_year"))
print("Venue:", (data.get("host_venue") or {}).get("display_name"))

print("\nAuthors:")
for a in data.get("authorships", []):
    author = a.get("author", {})
    name = author.get("display_name")
    if name:
        print("-", name)