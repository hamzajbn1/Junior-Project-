"""Pure extraction, deduplication, aggregation and validation. No network calls."""
import collections
import re
from datetime import datetime, timezone
from . import ServiceError
from .cskg_service import normalize

def publication_year(work):
    year = work.get("publication_year")
    return year if type(year) is int and 1000 <= year <= datetime.now().year else None


def supporting_insights(references, works, failed, unusable=0):
    """Aggregate only requested, deduplicated works; never perform network I/O."""
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
            coverage["missing_year_papers"] += 1
        location = work.get("primary_location")
        source = location.get("source") if isinstance(location, dict) else None
        source = source if isinstance(source, dict) else {}
        source_id, label = source.get("id"), source.get("display_name")
        # A repository/hosting platform is not a publication venue. Do not
        # substitute the publisher, another location, or the author's institution.
        if (isinstance(source_id, str)
                and re.fullmatch(r"https://openalex\.org/S\d+", source_id)
                and isinstance(label, str) and label.strip()
                and source.get("type") != "repository"):
            venue = venues.setdefault(source_id, {
                "id": source_id, "label": label.strip(), "papers": 0, "is_other": False,
            })
            venue["papers"] += 1
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
        # OpenAlex caps inline authorships at 100. Conservatively flag records
        # at the cap without fetching them again or claiming full coverage.
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
    """Group years so a wide span stays readable.

      <= 15 years  -> one point per year
      16-30 years  -> one point per 2 years
      over 30      -> one point per 5 years
    """
    years = sorted(counts)
    span = years[-1] - years[0] + 1
    size = 1 if span <= 15 else 2 if span <= 30 else 5

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

def overview_result(references, works, failed, unusable=0):
    insights = supporting_insights(references, works, failed, unusable)

    normalized = extract_records(works, references)
    counts = year_counts(normalized["records"])
    undated = len(references) - sum(counts.values())
    current_year = datetime.now().year

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


def extract_records(works, requested_ids):
    """Extract a small normalized record per requested work; never fetch data."""
    records, rejected = {}, []
    for identifier, work in works.items():
        if identifier not in requested_ids or not isinstance(work, dict):
            rejected.append(identifier)
            continue
        records[identifier] = {
            "id": identifier, "publication_year": publication_year(work),
        }
    return {"records": records, "rejected_ids": rejected}


def in_range(year, start_year=None, end_year=None):
    return year is not None and (start_year is None or year >= start_year) and (end_year is None or year <= end_year)


def year_counts(records, start_year=None, end_year=None):
    return collections.Counter(record["publication_year"] for record in records.values()
                               if in_range(record["publication_year"], start_year, end_year))


def aggregate_research(records, evidence, metadata, *, start_year=None, end_year=None):
    requested = set(evidence["work_ids"])
    missing = requested - records.keys()
    undated = {identifier for identifier, record in records.items() if record["publication_year"] is None}
    eligible = {identifier: record for identifier, record in records.items()
                if in_range(record["publication_year"], start_year, end_year)}
    outside = len(records) - len(undated) - len(eligible)
    incomplete = bool(missing or undated or evidence["unmapped_references"] or metadata["failed_ids"])
    counts = year_counts(records, start_year, end_year)
    # Match Overview's observed span when years are blank. Never pad to today's
    # year or imply coverage outside retrieved records; partial gaps are unknown.
    rows = [{"year": year, "papers": counts.get(year, None if incomplete else 0)}
            for year in range(min(counts), max(counts) + 1)] if counts else []
    warnings = []
    if missing:
        warnings.append(f"{len(missing)} supporting works have unavailable metadata; counts may be incomplete.")
    if undated:
        warnings.append(f"{len(undated)} retrieved works have no usable publication year; their inclusion in the requested range is unknown.")
    if evidence["unmapped_references"]:
        warnings.append(f"{len(evidence['unmapped_references'])} graph references could not be mapped to OpenAlex.")
    if metadata["failed_ids"]:
        warnings.append("Some OpenAlex batches failed after their allowed attempts. Available counts are lower bounds.")
    if datetime.now().year in counts:
        warnings.append(f"{datetime.now().year} is a partial calendar year.")
    if metadata["ignored_records"]:
        warnings.append(f"{metadata['ignored_records']} malformed or unrequested OpenAlex records were ignored.")
    observed = [record["publication_year"] for record in records.values() if record["publication_year"] is not None]
    return {
        "yearly_counts": rows, "counted_papers": len(eligible),
        "total_supporting_papers": len(requested),
        "coverage": {"requested_work_ids": len(requested), "retrieved_works": len(records),
                     "missing_metadata": len(missing), "missing_year": len(undated),
                     "outside_requested_years": outside, "counted_papers": len(eligible),
                     "unmapped_references": len(evidence["unmapped_references"]),
                     "failed_work_ids": len(metadata["failed_ids"]),
                     "observed_start_year": min(observed) if observed else None,
                     "observed_end_year": max(observed) if observed else None,
                     "evidence_retrieval_complete": evidence["complete"],
                     "year_counts_complete": not incomplete},
        "counted_paper_ids": sorted(eligible),
        "warnings": warnings,
        "status": "partial" if incomplete else "complete" if eligible else "empty",
        "empty_reason": "No dated supporting papers fall in the requested years." if not eligible else None,
        "filters": {"start_year": start_year, "end_year": end_year},
    }


def validate_result(request, relation, evidence, metadata, records, aggregate):
    """Independent consistency checks; this does not prove scientific claims."""
    errors = []
    requested = set(evidence["work_ids"])
    for field in ("subject", "predicate", "object"):
        if relation[field] != evidence[field]:
            errors.append({"code": "relationship_changed", "repair": None,
                           "message": "Evidence does not match the selected directed relationship."})
    if relation["predicate"] != request["connection"]:
        errors.append({"code": "predicate_changed", "repair": None, "message": "The requested predicate changed."})
    if not evidence["complete"]:
        errors.append({"code": "incomplete_evidence", "repair": None, "message": "Graph evidence retrieval is incomplete."})
    if set(records) - requested or set(metadata["works"]) - requested:
        errors.append({"code": "unrequested_records", "repair": "metadata", "message": "An unrequested paper reached processing."})
    if set(metadata["failed_ids"]) - requested or set(metadata["failed_ids"]) & records.keys():
        errors.append({"code": "metadata_membership", "repair": "metadata", "message": "Failed metadata IDs do not match this task's evidence."})
    for identifier, record in records.items():
        source = metadata["works"].get(identifier)
        if (record["id"] != identifier or not isinstance(source, dict)
                or record["publication_year"] != publication_year(source)):
            errors.append({"code": "extraction", "repair": "metadata", "message": "Extracted work identity or publication year does not match its source."})
            break
    if metadata["conflicting_ids"]:
        errors.append({"code": "conflicting_records", "repair": "metadata", "message": "Conflicting duplicate OpenAlex records require repair."})
    expected = year_counts(records, request["start_year"], request["end_year"])
    rows = aggregate["yearly_counts"]
    row_years = [row["year"] for row in rows]
    actual = {row["year"]: row["papers"] for row in rows if row["papers"] is not None and row["papers"] != 0}
    if row_years != sorted(set(row_years)) or actual != dict(expected):
        errors.append({"code": "year_counts", "repair": "aggregate", "message": "Yearly values do not match the filtered records."})
    if aggregate["counted_papers"] != sum(expected.values()):
        errors.append({"code": "totals", "repair": "aggregate", "message": "The yearly total is inconsistent."})
    if aggregate["filters"] != {"start_year": request["start_year"], "end_year": request["end_year"]}:
        errors.append({"code": "filters", "repair": "aggregate", "message": "The result filters changed."})
    if any(not in_range(year, request["start_year"], request["end_year"]) for year in row_years):
        errors.append({"code": "range", "repair": "aggregate", "message": "A result year is outside the requested filters."})
    coverage = aggregate["coverage"]
    expected_complete = not bool(requested - records.keys()
                                 or any(row["publication_year"] is None for row in records.values())
                                 or evidence["unmapped_references"] or metadata["failed_ids"])
    if (coverage["requested_work_ids"] != len(requested)
            or coverage["retrieved_works"] != len(records)
            or coverage["missing_metadata"] != len(requested - records.keys())
            or coverage["missing_year"] != sum(row["publication_year"] is None for row in records.values())
            or coverage["counted_papers"] != sum(expected.values())
            or coverage["retrieved_works"] != coverage["outside_requested_years"] + coverage["missing_year"] + coverage["counted_papers"]
            or coverage["unmapped_references"] != len(evidence["unmapped_references"])
            or coverage["failed_work_ids"] != len(metadata["failed_ids"])):
        errors.append({"code": "coverage", "repair": "aggregate", "message": "Coverage does not match the retrieved evidence."})
    if coverage["year_counts_complete"] != expected_complete:
        errors.append({"code": "completeness", "repair": "aggregate", "message": "The completeness flag does not match evidence coverage."})
    if not coverage["year_counts_complete"] and any(row["papers"] == 0 for row in rows):
        errors.append({"code": "unknown_zero", "repair": "aggregate", "message": "Incomplete coverage cannot establish zero papers."})
    expected_ids = {identifier for identifier, record in records.items()
                    if in_range(record["publication_year"], request["start_year"], request["end_year"])}
    if sorted(expected_ids) != aggregate["counted_paper_ids"]:
        errors.append({"code": "counted_ids", "repair": "aggregate", "message": "The counted-paper IDs do not match the requested years."})
    return {"passed": not errors, "errors": errors,
            "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
