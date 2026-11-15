# Shopping List

A Thompson hub module for the family shopping list, separated by store.

- One collapsible list per store.
- Drag a store by its handle to reorder the lists (arrow keys work too).
- Rename or delete a store and its whole list.
- Click an item to draw a strikethrough and let it disappear.
- An undo bar restores the last item crossed off, so a mis-tap is harmless.

The module is a plain Flask Blueprint running inside the Thompson hub. It
reads and writes the central SQLite database and adds no login, server, port or
separate database file.

## Install

Copy this folder into a Thompson hub checkout as
`applications/shopping-list-module/`, then let the hub reload. It appears on the
homepage at `/shopping-list`.

To customise the card, add an entry to `config/apps.json`:

```json
{
  "id": "shopping_list_module",
  "name": "Shopping List",
  "enabled": true,
  "route": "/shopping-list",
  "icon": "shopping-cart",
  "description": "What to pick up, sorted by store.",
  "accent": "#B58A45",
  "order": 2
}
```

`app.json` holds the same metadata for reference.

## Tables

Both tables live in `data/thompson.db` and are created by `init_app`:

- `shopping_list_stores` — name, drag position and collapsed state.
- `shopping_list_items` — item name, store, position and `checked_at`.
  Crossed-off items keep their row so undo can restore them; they are never
  rendered.

## Routes

All routes sit under the module prefix, `/shopping-list` by default.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/` | The page |
| `POST` | `/stores` | Create a store |
| `POST` | `/stores/<id>/rename` | Change the store name |
| `POST` | `/stores/<id>/delete` | Delete a store and its items |
| `POST` | `/stores/<id>/collapsed` | Persist the collapsed state |
| `POST` | `/stores/order` | Save a dragged order |
| `POST` | `/stores/<id>/items` | Add an item |
| `POST` | `/items/<id>/check` | Cross an item off |
| `POST` | `/items/<id>/undo` | Put a crossed-off item back |

Forms handle creating and renaming without JavaScript; collapsing, dragging,
checking off and undo use same-origin JSON.

## Contract notes

- No users, sessions, roles, CSRF tokens or per-user filtering.
- Widget-free and dependency-free: one CSS file and one script, no CDN or
  remote fonts, so the hub's Content Security Policy stays strict.
- Full-screen layout with the shared `hub_back()` control in the top-left.
