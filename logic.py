"""Shopping List domain logic: stores, their items, and list ordering.

Every list belongs to a store. Stores carry the order the family dragged them
into and whether the card is collapsed. Items are checked off (soft-deleted)
so the undo button can bring one back; checked rows never render.

Everything is family-shared: no owner column, no user table and no per-user
filtering. The hub is open and the tailnet is the access boundary.

Tables:

``shopping_list_stores``  one row per shop, in display order
``shopping_list_items``   items in a store; ``checked_at`` hides a row
"""

from __future__ import annotations

from shared.database import get_db
from shared.utilities import clean_text, utc_now

MAX_STORE_NAME = 80
MAX_ITEM_NAME = 120
MAX_STORES = 40
MAX_ITEMS_PER_STORE = 300

SCHEMA = """
CREATE TABLE IF NOT EXISTS shopping_list_stores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    collapsed INTEGER NOT NULL DEFAULT 0 CHECK (collapsed IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS shopping_list_stores_name
    ON shopping_list_stores (name COLLATE NOCASE);

CREATE INDEX IF NOT EXISTS shopping_list_stores_position
    ON shopping_list_stores (position, id);

CREATE TABLE IF NOT EXISTS shopping_list_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    store_id INTEGER NOT NULL
        REFERENCES shopping_list_stores (id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    checked_at TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS shopping_list_items_store
    ON shopping_list_items (store_id, checked_at, position);
"""


def ensure_schema() -> None:
    """Create the app's tables. Safe to run on every startup."""

    db = get_db()
    db.executescript(SCHEMA)
    db.commit()


# --- reading ----------------------------------------------------------------


def list_stores() -> list[dict]:
    """Every store with its unchecked items, in display order."""

    db = get_db()
    stores = db.execute(
        """
        SELECT id, name, collapsed
        FROM shopping_list_stores
        ORDER BY position ASC, id ASC
        """
    ).fetchall()
    item_rows = db.execute(
        """
        SELECT id, store_id, name
        FROM shopping_list_items
        WHERE checked_at IS NULL
        ORDER BY position ASC, id ASC
        """
    ).fetchall()

    grouped: dict[int, list[dict]] = {}
    for item in item_rows:
        grouped.setdefault(item["store_id"], []).append(
            {"id": item["id"], "name": item["name"]}
        )

    result: list[dict] = []
    for store in stores:
        entries = grouped.get(store["id"], [])
        result.append(
            {
                "id": store["id"],
                "name": store["name"],
                "collapsed": bool(store["collapsed"]),
                "entries": entries,
                "item_count": len(entries),
            }
        )
    return result


def store_exists(store_id: int) -> bool:
    row = get_db().execute(
        "SELECT 1 FROM shopping_list_stores WHERE id = ?", (store_id,)
    ).fetchone()
    return row is not None


def _store_name_taken(name: str, *, exclude_id: int | None = None) -> bool:
    sql = "SELECT 1 FROM shopping_list_stores WHERE name = ? COLLATE NOCASE"
    params: list = [name]
    if exclude_id is not None:
        sql += " AND id <> ?"
        params.append(exclude_id)
    return get_db().execute(sql + " LIMIT 1", tuple(params)).fetchone() is not None


# --- writing: stores --------------------------------------------------------


def create_store(name: str) -> tuple[int | None, str | None]:
    """Add a store at the end of the list. Returns ``(id, error)``."""

    db = get_db()
    name = clean_text(name, MAX_STORE_NAME)
    if not name:
        return None, "Give the store a name."
    if _store_name_taken(name):
        return None, f'"{name}" is already on the list.'
    count = db.execute("SELECT COUNT(*) AS total FROM shopping_list_stores").fetchone()[
        "total"
    ]
    if count >= MAX_STORES:
        return None, "There are already as many stores as one list can hold."

    position = db.execute(
        "SELECT COALESCE(MAX(position), -1) + 1 AS next FROM shopping_list_stores"
    ).fetchone()["next"]
    now = utc_now()
    cursor = db.execute(
        """
        INSERT INTO shopping_list_stores
            (name, position, collapsed, created_at, updated_at)
        VALUES (?, ?, 0, ?, ?)
        """,
        (name, position, now, now),
    )
    db.commit()
    return int(cursor.lastrowid), None


def rename_store(store_id: int, name: str) -> tuple[bool, str | None]:
    """Change a store's name, keeping its items and position."""

    db = get_db()
    if not store_exists(store_id):
        return False, "That store is no longer on the list."
    name = clean_text(name, MAX_STORE_NAME)
    if not name:
        return False, "Give the store a name."
    if _store_name_taken(name, exclude_id=store_id):
        return False, f'Another store is already called "{name}".'

    db.execute(
        "UPDATE shopping_list_stores SET name = ?, updated_at = ? WHERE id = ?",
        (name, utc_now(), store_id),
    )
    db.commit()
    return True, None


def delete_store(store_id: int) -> bool:
    """Remove a store and every item on it."""

    db = get_db()
    cursor = db.execute("DELETE FROM shopping_list_stores WHERE id = ?", (store_id,))
    db.commit()
    return cursor.rowcount > 0


def set_collapsed(store_id: int, collapsed: bool) -> bool:
    db = get_db()
    cursor = db.execute(
        "UPDATE shopping_list_stores SET collapsed = ?, updated_at = ? WHERE id = ?",
        (1 if collapsed else 0, utc_now(), store_id),
    )
    db.commit()
    return cursor.rowcount > 0


def reorder_stores(store_ids: list[int]) -> None:
    """Apply a dragged order, keeping any store the client did not name."""

    db = get_db()
    existing = [
        row["id"]
        for row in db.execute(
            "SELECT id FROM shopping_list_stores ORDER BY position ASC, id ASC"
        ).fetchall()
    ]
    ordered: list[int] = []
    for store_id in store_ids:
        if store_id in existing and store_id not in ordered:
            ordered.append(store_id)
    ordered.extend(store_id for store_id in existing if store_id not in ordered)

    now = utc_now()
    for position, store_id in enumerate(ordered):
        db.execute(
            "UPDATE shopping_list_stores SET position = ?, updated_at = ? WHERE id = ?",
            (position, now, store_id),
        )
    db.commit()


# --- writing: items ---------------------------------------------------------


def add_item(store_id: int, name: str) -> tuple[dict | None, str | None]:
    """Add one item to the end of a store's list."""

    db = get_db()
    name = clean_text(name, MAX_ITEM_NAME)
    if not name:
        return None, "Give the item a name."
    if not store_exists(store_id):
        return None, "That store is no longer on the list."

    count = db.execute(
        """
        SELECT COUNT(*) AS total FROM shopping_list_items
        WHERE store_id = ? AND checked_at IS NULL
        """,
        (store_id,),
    ).fetchone()["total"]
    if count >= MAX_ITEMS_PER_STORE:
        return None, "That list is as full as one store can hold."

    position = db.execute(
        """
        SELECT COALESCE(MAX(position), -1) + 1 AS next FROM shopping_list_items
        WHERE store_id = ?
        """,
        (store_id,),
    ).fetchone()["next"]
    cursor = db.execute(
        """
        INSERT INTO shopping_list_items
            (store_id, name, position, checked_at, created_at)
        VALUES (?, ?, ?, NULL, ?)
        """,
        (store_id, name, position, utc_now()),
    )
    db.commit()
    return {"id": int(cursor.lastrowid), "name": name, "store_id": store_id}, None


def check_item(item_id: int) -> dict | None:
    """Mark an item off. It stays in the table so undo can restore it."""

    db = get_db()
    row = db.execute(
        "SELECT id, store_id, name, checked_at FROM shopping_list_items WHERE id = ?",
        (item_id,),
    ).fetchone()
    if not row:
        return None
    if not row["checked_at"]:
        db.execute(
            "UPDATE shopping_list_items SET checked_at = ? WHERE id = ?",
            (utc_now(), item_id),
        )
        db.commit()
    return {"id": row["id"], "name": row["name"], "store_id": row["store_id"]}


def undo_item(item_id: int) -> dict | None:
    """Put a checked-off item back on its store's list."""

    db = get_db()
    row = db.execute(
        "SELECT id, store_id, name, checked_at FROM shopping_list_items WHERE id = ?",
        (item_id,),
    ).fetchone()
    if not row:
        return None
    if row["checked_at"]:
        db.execute(
            "UPDATE shopping_list_items SET checked_at = NULL WHERE id = ?",
            (item_id,),
        )
        db.commit()
    return {"id": row["id"], "name": row["name"], "store_id": row["store_id"]}
