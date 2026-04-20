import re


def normalize_query(query: str) -> str:
    query = query.strip()
    query = re.sub(r"\s+", " ", query)
    return query
