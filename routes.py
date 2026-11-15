"""Shopping List routes, mounted at /shopping-list by the hub app manager.

Every handler stays relative to the blueprint prefix. There is no login, no
``current_user`` and no CSRF token: the hub is open inside the tailnet.

Plain forms create and rename stores, so the list keeps working without
JavaScript. Dragging, collapsing and crossing items off use same-origin JSON.
"""

from __future__ import annotations

from flask import (
    Blueprint,
    abort,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

from shared.utilities import clean_text

from .logic import (
    MAX_ITEM_NAME,
    MAX_STORE_NAME,
    add_item,
    check_item,
    create_store,
    delete_store,
    list_stores,
    rename_store,
    reorder_stores,
    set_collapsed,
    store_exists,
    undo_item,
)

blueprint = Blueprint(
    "shopping_list",
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/static",
)


# --- helpers ----------------------------------------------------------------


def _json_error(message: str, status: int):
    return jsonify({"ok": False, "error": message}), status


def _payload() -> dict:
    data = request.get_json(silent=True)
    if isinstance(data, dict):
        return data
    return request.form


def _render_index(*, error: str | None = None, focus_store: int | None = None, status: int = 200):
    return (
        render_template(
            "shopping_list/shopping_list.html",
            stores=list_stores(),
            error=error,
            focus_store=focus_store,
        ),
        status,
    )


# --- page -------------------------------------------------------------------


@blueprint.get("/", strict_slashes=False)
def index():
    return _render_index(focus_store=request.args.get("focus", type=int))


# --- stores -----------------------------------------------------------------


@blueprint.post("/stores")
def store_create():
    name = clean_text(request.form.get("name"), MAX_STORE_NAME)
    if not name:
        return _render_index(error="Give the store a name.", status=400)

    store_id, error = create_store(name)
    if error:
        return _render_index(error=error, status=400)

    return redirect(
        url_for("shopping_list.index", focus=store_id, _anchor=f"store-{store_id}")
    )


@blueprint.post("/stores/<int:store_id>/rename")
def store_rename(store_id: int):
    name = clean_text(_payload().get("name"), MAX_STORE_NAME)
    if not name:
        if request.is_json:
            return _json_error("Give the store a name.", 400)
        return _render_index(error="Give the store a name.", status=400)

    ok, error = rename_store(store_id, name)
    if request.is_json:
        if not ok:
            return _json_error(error or "That store could not be renamed.", 404)
        return jsonify({"ok": True, "name": clean_text(name, MAX_STORE_NAME)})

    if not ok:
        return _render_index(error=error, status=404)
    return redirect(url_for("shopping_list.index", _anchor=f"store-{store_id}"))


@blueprint.post("/stores/<int:store_id>/delete")
def store_delete(store_id: int):
    if not delete_store(store_id):
        abort(404)
    return redirect(url_for("shopping_list.index"))


@blueprint.post("/stores/<int:store_id>/collapsed")
def store_collapsed(store_id: int):
    value = _payload().get("collapsed")
    if not isinstance(value, bool):
        return _json_error("Send collapsed as true or false.", 400)
    if not set_collapsed(store_id, value):
        return _json_error("That store is no longer on the list.", 404)
    return jsonify({"ok": True, "collapsed": value})


@blueprint.post("/stores/order")
def store_order():
    ids = _payload().get("ids")
    if not isinstance(ids, list) or not all(
        isinstance(value, int) and not isinstance(value, bool) for value in ids
    ):
        return _json_error("Send the store ids in their new order.", 400)
    reorder_stores(ids)
    return jsonify({"ok": True})


# --- items ------------------------------------------------------------------


@blueprint.post("/stores/<int:store_id>/items")
def item_create(store_id: int):
    name = clean_text(_payload().get("name"), MAX_ITEM_NAME)
    if not name:
        if request.is_json:
            return _json_error("Give the item a name.", 400)
        return _render_index(error="Give the item a name.", focus_store=store_id, status=400)

    if not store_exists(store_id):
        if request.is_json:
            return _json_error("That store is no longer on the list.", 404)
        return _render_index(error="That store is no longer on the list.", status=404)

    item, error = add_item(store_id, name)
    if request.is_json:
        if error:
            return _json_error(error, 400)
        return jsonify({"ok": True, "item": item})

    if error:
        return _render_index(error=error, focus_store=store_id, status=400)
    return redirect(
        url_for("shopping_list.index", focus=store_id, _anchor=f"store-{store_id}")
    )


@blueprint.post("/items/<int:item_id>/check")
def item_check(item_id: int):
    item = check_item(item_id)
    if not item:
        return _json_error("That item is no longer on the list.", 404)
    return jsonify({"ok": True, "item": item})


@blueprint.post("/items/<int:item_id>/undo")
def item_undo(item_id: int):
    item = undo_item(item_id)
    if not item:
        return _json_error("That item is no longer on the list.", 404)
    return jsonify({"ok": True, "item": item})
