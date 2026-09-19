"""All Notion reads/writes. Schema: Name (title), Amount (number),
Date (date), Category (relation -> a separate Category database, one page
per category, e.g. "Utilities" with Spent This Month / Total Spent rollups)."""
from functools import lru_cache

from notion_client import Client

import config

notion = Client(auth=config.NOTION_API_KEY)


@lru_cache(maxsize=1)
def _data_source_id() -> str:
    """Resolve the Expenses database's data source id.

    Notion API version 2025-09-03 (the notion-client default) split each
    database into a container plus one or more "data sources" - the schema
    and rows now live on the data source, not the database object. This
    project assumes a single-source database (the normal case), so we just
    take the first one and cache it alongside NOTION_DATABASE_ID.
    """
    db = notion.databases.retrieve(database_id=config.NOTION_DATABASE_ID)
    sources = db["data_sources"]
    if not sources:
        raise RuntimeError("Notion database has no data sources.")
    return sources[0]["id"]


@lru_cache(maxsize=1)
def _category_data_source_id() -> str:
    """Resolve the id of the *other* database the Category relation points
    to, straight from the Category property's own config - no separate env
    var needed."""
    ds = notion.data_sources.retrieve(data_source_id=_data_source_id())
    prop = ds["properties"].get("Category")
    if prop is None:
        raise RuntimeError("No 'Category' property found in the Notion database.")
    if prop["type"] != "relation":
        raise RuntimeError(
            f"'Category' must be a Relation property, but it is '{prop['type']}'."
        )
    return prop["relation"]["data_source_id"]


@lru_cache(maxsize=1)
def _category_pages() -> dict[str, str]:
    """Category name -> page id, read from the linked Category database.

    Cached for the life of the process, same tradeoff get_category_options
    always had: adding a category in Notion needs a restart to be picked up.
    """
    category_ds_id = _category_data_source_id()
    pages: dict[str, str] = {}
    cursor = None
    while True:
        kwargs = {"data_source_id": category_ds_id, "page_size": 100}
        if cursor:
            kwargs["start_cursor"] = cursor
        result = notion.data_sources.query(**kwargs)
        for row in result["results"]:
            title_prop = next(
                p for p in row["properties"].values() if p["type"] == "title"
            )
            name = "".join(t["plain_text"] for t in title_prop["title"])
            if name:
                pages[name] = row["id"]
        if not result.get("has_more"):
            break
        cursor = result["next_cursor"]
    if not pages:
        raise RuntimeError(
            "The Category database has no rows yet. Add a few "
            "(Food, Transport, Groceries, Bills, Shopping, Other)."
        )
    return pages


@lru_cache(maxsize=1)
def get_category_options() -> tuple[str, ...]:
    """Read category names straight from the linked Category database.

    Fetched at runtime rather than hardcoded so that adding a category page
    in Notion is enough - no code change, and the LLM can never invent a
    near-miss like 'Grocery' that _snap_to_allowed() wouldn't catch.
    """
    return tuple(_category_pages().keys())


def describe_database() -> dict:
    """Property name -> type. Used by scripts/check_notion.py."""
    ds = notion.data_sources.retrieve(data_source_id=_data_source_id())
    return {name: prop["type"] for name, prop in ds["properties"].items()}


def _resolve_category_page_id(category: str) -> str:
    """Map a category name to its page id in the Category database.

    By the time create_expense() calls this, extractor._snap_to_allowed()
    has already forced `category` onto one of the names get_category_options()
    returned - so normally this is a guaranteed hit against _category_pages().

    TODO(human): decide what to do on a lookup miss. It's rare but possible:
    _category_pages() is cached for the whole process lifetime (same
    restart-to-refresh tradeoff as get_category_options), so a category page
    renamed or deleted in Notion after the cache was built would cause a miss
    right here, mid-request. Pick one policy and implement it, for example:
      - raise a clear RuntimeError (lose this expense, but fail loudly)
      - clear the cache once (_category_pages.cache_clear()) and retry before
        giving up, in case a category was added and the cache is just stale
      - fall back to a specific default category page name, if one exists
    """
    pages = _category_pages()
    raise NotImplementedError


def create_expense(name: str, amount: float, category: str, on_date: str) -> str:
    """Create one row. `on_date` must be ISO YYYY-MM-DD. Returns the page URL."""
    category_page_id = _resolve_category_page_id(category)
    page = notion.pages.create(
        parent={"data_source_id": _data_source_id()},
        properties={
            "Name": {"title": [{"text": {"content": name[:200]}}]},
            "Amount": {"number": float(amount)},
            "Date": {"date": {"start": on_date}},
            "Category": {"relation": [{"id": category_page_id}]},
        },
    )
    return page["url"]
