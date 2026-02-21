"""
Agent tools for Picnic grocery delivery management.

Provides tools to search products, manage the cart, view delivery slots,
place orders, and bridge the shopping list from the todo system into
the Picnic cart.  All tools return ``{"status": "success", ...}`` or
``{"status": "error", "message": ...}`` per project convention.
"""

import logging
import traceback
from typing import Any, Dict, List, Optional

from google.adk.tools import FunctionTool

from .picnic_client import get_picnic_client

logger = logging.getLogger(__name__)

_MAX_SEARCH_RESULTS = 10


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _client_or_error():
    """Return (client, None) or (None, error_dict)."""
    client = get_picnic_client()
    if client is None:
        return None, {
            "status": "error",
            "message": (
                "Picnic is not configured. Set picnic_username and picnic_password "
                "in the admin UI or PICNIC_USERNAME/PICNIC_PASSWORD env vars."
            ),
        }
    return client, None


def _unwrap_search_results(raw_results: list) -> List[Dict[str, Any]]:
    """Unwrap the [{"items": [...]}] structure returned by PicnicAPI.search()."""
    products = []
    for group in raw_results:
        if isinstance(group, dict) and "items" in group:
            products.extend(group["items"])
        else:
            products.append(group)
    return products


def _format_product(item: Dict[str, Any]) -> Dict[str, Any]:
    """Normalise a Picnic search result into a compact dict."""
    return {
        "product_id": item.get("id", ""),
        "name": item.get("name", ""),
        "price": item.get("price", 0),
        "unit_quantity": item.get("unit_quantity", ""),
        "image_url": (item.get("image_ids", [None]) or [None])[0],
    }


def _format_cart_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """Normalise a cart item into a compact dict."""
    items = item.get("items", [])
    result = {
        "name": item.get("name", ""),
        "id": item.get("id", ""),
    }
    if items:
        result["products"] = []
        for sub in items:
            sub_items = sub.get("items", [])
            for product in sub_items:
                result["products"].append({
                    "product_id": product.get("id", ""),
                    "name": product.get("name", ""),
                    "price": product.get("price", 0),
                    "quantity": product.get("decorators", [{}])[0].get("quantity", 1)
                    if product.get("decorators")
                    else 1,
                })
    return result


# ---------------------------------------------------------------------------
# Tool functions
# ---------------------------------------------------------------------------


def search_picnic_product(
    query: str,
) -> Dict[str, Any]:
    """
    Search the Picnic grocery catalog for products.

    Args:
        query: Search term (e.g. "milk", "bananas", "olive oil").

    Returns:
        On success: {"status": "success", "results": [...], "count": N}
        On failure: {"status": "error", "message": "..."}
    """
    client, err = _client_or_error()
    if err:
        return err

    try:
        raw_results = client.search(query)
        products = _unwrap_search_results(raw_results)
        results = []
        for item in products[:_MAX_SEARCH_RESULTS]:
            formatted = _format_product(item)
            if formatted.get("product_id"):
                results.append(formatted)
        return {
            "status": "success",
            "results": results,
            "count": len(results),
        }
    except Exception as e:
        msg = f"Picnic search failed: {e}"
        logger.error(msg)
        logger.debug(traceback.format_exc())
        return {"status": "error", "message": msg[:300]}


def get_picnic_cart() -> Dict[str, Any]:
    """
    View the current Picnic shopping cart contents and total.

    Returns:
        On success: {"status": "success", "items": [...], "total_price": N, "item_count": N}
        On failure: {"status": "error", "message": "..."}
    """
    client, err = _client_or_error()
    if err:
        return err

    try:
        cart = client.get_cart()
        items = []
        total_price = cart.get("total_price", 0)
        order_items = cart.get("items", [])

        for group in order_items:
            formatted = _format_cart_item(group)
            if formatted.get("products"):
                items.extend(formatted["products"])

        return {
            "status": "success",
            "items": items,
            "total_price": total_price,
            "item_count": len(items),
        }
    except Exception as e:
        msg = f"Failed to get Picnic cart: {e}"
        logger.error(msg)
        logger.debug(traceback.format_exc())
        return {"status": "error", "message": msg[:300]}


def add_to_picnic_cart(
    product_id: str,
    count: int = 1,
) -> Dict[str, Any]:
    """
    Add a product to the Picnic cart.

    Args:
        product_id: The product ID from search results.
        count: Number of units to add (default 1).

    Returns:
        On success: {"status": "success", "message": "..."}
        On failure: {"status": "error", "message": "..."}
    """
    client, err = _client_or_error()
    if err:
        return err

    if not product_id or not product_id.strip():
        return {"status": "error", "message": "product_id is required"}

    try:
        result = client.add_product(product_id, count=max(1, count))
        logger.debug("Picnic add_product response: %s", result)
        return {
            "status": "success",
            "message": f"Added {count}x product {product_id} to cart",
        }
    except Exception as e:
        msg = f"Failed to add product to cart: {e}"
        logger.error(msg)
        logger.debug(traceback.format_exc())
        return {"status": "error", "message": msg[:300]}


def remove_from_picnic_cart(
    product_id: str,
    count: int = 1,
) -> Dict[str, Any]:
    """
    Remove a product from the Picnic cart.

    Args:
        product_id: The product ID to remove.
        count: Number of units to remove (default 1).

    Returns:
        On success: {"status": "success", "message": "..."}
        On failure: {"status": "error", "message": "..."}
    """
    client, err = _client_or_error()
    if err:
        return err

    try:
        client.remove_product(product_id, count=max(1, count))
        return {
            "status": "success",
            "message": f"Removed {count}x product {product_id} from cart",
        }
    except Exception as e:
        msg = f"Failed to remove product from cart: {e}"
        logger.error(msg)
        logger.debug(traceback.format_exc())
        return {"status": "error", "message": msg[:300]}


def clear_picnic_cart() -> Dict[str, Any]:
    """
    Clear all items from the Picnic cart.

    Returns:
        On success: {"status": "success", "message": "Cart cleared"}
        On failure: {"status": "error", "message": "..."}
    """
    client, err = _client_or_error()
    if err:
        return err

    try:
        client.clear_cart()
        return {"status": "success", "message": "Cart cleared"}
    except Exception as e:
        msg = f"Failed to clear Picnic cart: {e}"
        logger.error(msg)
        logger.debug(traceback.format_exc())
        return {"status": "error", "message": msg[:300]}


def get_picnic_delivery_slots() -> Dict[str, Any]:
    """
    List available Picnic delivery time slots.

    Returns:
        On success: {"status": "success", "slots": [...], "count": N}
        On failure: {"status": "error", "message": "..."}
    """
    client, err = _client_or_error()
    if err:
        return err

    try:
        raw_slots = client.get_delivery_slots()
        slots = []
        for day in raw_slots:
            for slot in day.get("slot_list", []):
                slots.append({
                    "slot_id": slot.get("slot_id", ""),
                    "window_start": slot.get("window_start", ""),
                    "window_end": slot.get("window_end", ""),
                    "is_available": slot.get("is_available", False),
                    "minimum_order_value": slot.get("minimum_order_value", 0),
                })
        return {
            "status": "success",
            "slots": slots,
            "count": len(slots),
        }
    except Exception as e:
        msg = f"Failed to get Picnic delivery slots: {e}"
        logger.error(msg)
        logger.debug(traceback.format_exc())
        return {"status": "error", "message": msg[:300]}


def set_picnic_delivery_slot(
    slot_id: str,
) -> Dict[str, Any]:
    """
    Select a delivery slot and place the Picnic order.

    IMPORTANT: This commits the order. The agent MUST confirm with the user
    before calling this tool. This is an irreversible action.

    Args:
        slot_id: The delivery slot ID from get_picnic_delivery_slots results.

    Returns:
        On success: {"status": "success", "message": "Order placed for slot ..."}
        On failure: {"status": "error", "message": "..."}
    """
    client, err = _client_or_error()
    if err:
        return err

    try:
        result = client.set_delivery_slot(slot_id)
        logger.info("Picnic order placed with slot_id=%s", slot_id)
        return {
            "status": "success",
            "message": f"Order placed with delivery slot {slot_id}",
            "details": result,
        }
    except Exception as e:
        msg = f"Failed to set delivery slot: {e}"
        logger.error(msg)
        logger.debug(traceback.format_exc())
        return {"status": "error", "message": msg[:300]}


def submit_shopping_list_to_picnic(
    project_name: str = "Groceries",
) -> Dict[str, Any]:
    """
    Read the shopping list from the todo system and add matching items to the Picnic cart.

    Reads all backlog tasks from the specified project, searches Picnic for each item,
    and adds the best match to the cart. Reports which items were matched and which
    were not found. Does NOT automatically checkout — use get_picnic_delivery_slots
    and set_picnic_delivery_slot to complete the order.

    Args:
        project_name: The todo project name containing shopping list items (default "Groceries").

    Returns:
        On success: {"status": "success", "matched": [...], "unmatched": [...], "cart_total": N}
        On failure: {"status": "error", "message": "..."}
    """
    client, err = _client_or_error()
    if err:
        return err

    # Read items from the todo system
    try:
        from radbot.tools.todo.api.list_tools import list_project_tasks

        result = list_project_tasks(project_name, status_filter="backlog")
        if result.get("status") != "success":
            return {
                "status": "error",
                "message": f"Failed to read shopping list: {result.get('message', 'Unknown error')}",
            }
        tasks = result.get("tasks", [])
        if not tasks:
            return {
                "status": "error",
                "message": f"No items found in project '{project_name}' with status 'backlog'",
            }
    except Exception as e:
        msg = f"Failed to read shopping list from todo system: {e}"
        logger.error(msg)
        return {"status": "error", "message": msg[:300]}

    matched: List[Dict[str, Any]] = []
    unmatched: List[str] = []

    for task in tasks:
        title = task.get("title", "")
        related_info = task.get("related_info", {}) or {}
        quantity = related_info.get("quantity", 1) if isinstance(related_info, dict) else 1

        if not title:
            continue

        try:
            search_results = _unwrap_search_results(client.search(title))
            if search_results:
                # Pick the first (best) match
                best = search_results[0]
                product_id = best.get("id", "")
                if product_id:
                    client.add_product(product_id, count=max(1, int(quantity)))
                    matched.append({
                        "task": title,
                        "product_name": best.get("name", ""),
                        "product_id": product_id,
                        "price": best.get("price", 0),
                        "quantity": quantity,
                    })
                else:
                    unmatched.append(title)
            else:
                unmatched.append(title)
        except Exception as e:
            logger.warning(f"Failed to search/add '{title}': {e}")
            unmatched.append(title)

    # Get updated cart total
    cart_total = 0
    try:
        cart = client.get_cart()
        cart_total = cart.get("total_price", 0)
    except Exception:
        pass

    return {
        "status": "success",
        "matched": matched,
        "unmatched": unmatched,
        "matched_count": len(matched),
        "unmatched_count": len(unmatched),
        "cart_total": cart_total,
    }


def get_picnic_lists() -> Dict[str, Any]:
    """
    Get all Picnic user lists (favorites, last ordered, etc.).

    Returns the user's saved lists which typically include favorites,
    frequently bought items, and other curated product lists.

    Returns:
        On success: {"status": "success", "lists": [...], "count": N}
        On failure: {"status": "error", "message": "..."}
    """
    client, err = _client_or_error()
    if err:
        return err

    try:
        raw_lists = client.get_lists()
        logger.debug("Picnic /lists raw response: %s", repr(raw_lists)[:2000])
        # Normalise into a consistent shape
        lists = _flatten_lists_response(raw_lists)
        return {
            "status": "success",
            "lists": lists,
            "count": len(lists),
        }
    except Exception as e:
        msg = f"Failed to get Picnic lists: {e}"
        logger.error(msg)
        logger.debug(traceback.format_exc())
        return {"status": "error", "message": msg[:300]}


def get_picnic_list_details(
    list_id: str,
) -> Dict[str, Any]:
    """
    Get details and products for a specific Picnic list.

    Args:
        list_id: The list ID from get_picnic_lists results.

    Returns:
        On success: {"status": "success", "list": {...}, "items": [...]}
        On failure: {"status": "error", "message": "..."}
    """
    client, err = _client_or_error()
    if err:
        return err

    if not list_id or not list_id.strip():
        return {"status": "error", "message": "list_id is required"}

    try:
        raw_list = client.get_list(list_id)
        logger.debug("Picnic /lists/%s raw response: %s", list_id, repr(raw_list)[:2000])
        items = _extract_list_items(raw_list)
        return {
            "status": "success",
            "list": _format_list_summary(raw_list),
            "items": items,
            "item_count": len(items),
        }
    except Exception as e:
        msg = f"Failed to get Picnic list details: {e}"
        logger.error(msg)
        logger.debug(traceback.format_exc())
        return {"status": "error", "message": msg[:300]}


def get_picnic_order_history() -> Dict[str, Any]:
    """
    Get recent Picnic delivery/order history summaries.

    Returns a list of past deliveries with dates and totals.
    Use get_picnic_delivery_details with a delivery_id for the full item list.

    Returns:
        On success: {"status": "success", "deliveries": [...], "count": N}
        On failure: {"status": "error", "message": "..."}
    """
    client, err = _client_or_error()
    if err:
        return err

    try:
        raw = client.get_deliveries()
        logger.debug("Picnic /deliveries/summary raw response: %s", repr(raw)[:3000])
        deliveries = []
        if isinstance(raw, list):
            for d in raw[:20]:  # Limit to last 20
                deliveries.append(_format_delivery_summary(d))
        return {
            "status": "success",
            "deliveries": deliveries,
            "count": len(deliveries),
        }
    except Exception as e:
        msg = f"Failed to get Picnic order history: {e}"
        logger.error(msg)
        logger.debug(traceback.format_exc())
        return {"status": "error", "message": msg[:300]}


def get_picnic_delivery_details(
    delivery_id: str,
) -> Dict[str, Any]:
    """
    Get full details for a specific past Picnic delivery, including ordered items.

    Args:
        delivery_id: The delivery ID from get_picnic_order_history results.

    Returns:
        On success: {"status": "success", "delivery": {...}, "items": [...]}
        On failure: {"status": "error", "message": "..."}
    """
    client, err = _client_or_error()
    if err:
        return err

    if not delivery_id or not delivery_id.strip():
        return {"status": "error", "message": "delivery_id is required"}

    try:
        raw = client.get_delivery(delivery_id)
        logger.debug("Picnic /deliveries/%s raw response: %s", delivery_id, repr(raw)[:3000])

        summary = _format_delivery_summary(raw)
        items = _extract_delivery_items(raw)

        return {
            "status": "success",
            "delivery": summary,
            "items": items,
            "item_count": len(items),
        }
    except Exception as e:
        msg = f"Failed to get Picnic delivery details: {e}"
        logger.error(msg)
        logger.debug(traceback.format_exc())
        return {"status": "error", "message": msg[:300]}


def _flatten_lists_response(raw: Any) -> List[Dict[str, Any]]:
    """Recursively extract list-like objects from the /lists response.

    The Picnic API format is not well-documented, so we try several
    common shapes: bare list, dict with ``id``, or dict wrapping a list
    under an arbitrary key.
    """
    lists: List[Dict[str, Any]] = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                lists.append(_format_list_summary(item))
    elif isinstance(raw, dict):
        if "id" in raw:
            lists.append(_format_list_summary(raw))
        else:
            # Walk all values looking for list-shaped data
            for val in raw.values():
                if isinstance(val, list):
                    for item in val:
                        if isinstance(item, dict):
                            lists.append(_format_list_summary(item))
    return lists


def _format_list_summary(lst: Dict[str, Any]) -> Dict[str, Any]:
    """Normalise a Picnic list into a compact summary dict."""
    return {
        "list_id": lst.get("id", ""),
        "name": lst.get("name", lst.get("title", "")),
        "item_count": lst.get("item_count", lst.get("items_count", 0)),
    }


def _extract_list_items(raw_list: Any) -> List[Dict[str, Any]]:
    """Extract product items from a raw list response.

    Handles nested structures: items may be at top level or nested
    inside category groups (similar to cart structure).
    """
    items: List[Dict[str, Any]] = []
    if not isinstance(raw_list, dict):
        return items

    # Try common top-level keys
    for key in ("items", "products", "decorators"):
        entries = raw_list.get(key, [])
        if isinstance(entries, list):
            _collect_products(entries, items)
    return items


def _collect_products(entries: list, out: List[Dict[str, Any]]) -> None:
    """Recursively collect products from nested item lists."""
    for item in entries:
        if not isinstance(item, dict):
            continue
        # If this item has a name + (id or price), treat it as a product
        if item.get("name") and (item.get("id") or "price" in item):
            price_cents = item.get("price", 0)
            out.append({
                "product_id": item.get("id", ""),
                "name": item.get("name", ""),
                "price_euros": _cents_to_euros(price_cents),
                "unit_quantity": item.get("unit_quantity", ""),
            })
        # Recurse into nested item lists (cart-style grouping)
        for sub_key in ("items", "products"):
            sub = item.get(sub_key)
            if isinstance(sub, list):
                _collect_products(sub, out)


def _format_delivery_summary(d: Dict[str, Any]) -> Dict[str, Any]:
    """Normalise a delivery object into a compact summary dict."""
    # Price: try multiple field names and convert from cents
    price_cents = d.get("total_price", d.get("price", d.get("total", 0)))
    # Delivery time: try nested and flat structures
    dt = d.get("delivery_time") or d.get("slot") or {}
    if isinstance(dt, dict):
        delivery_start = dt.get("start", dt.get("window_start", ""))
        delivery_end = dt.get("end", dt.get("window_end", ""))
    else:
        delivery_start = str(dt) if dt else ""
        delivery_end = ""

    return {
        "delivery_id": d.get("id", d.get("delivery_id", "")),
        "status": d.get("status", ""),
        "delivery_time_start": delivery_start,
        "delivery_time_end": delivery_end,
        "total_price_euros": _cents_to_euros(price_cents),
        "creation_time": d.get("creation_time", d.get("created_at", "")),
    }


def _extract_delivery_items(raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract ordered items from a delivery detail response."""
    items: List[Dict[str, Any]] = []
    # Try common structures for delivery items
    for key in ("orders", "items", "products", "order_lines"):
        entries = raw.get(key, [])
        if isinstance(entries, list):
            _collect_delivery_products(entries, items)
    return items


def _collect_delivery_products(entries: list, out: List[Dict[str, Any]]) -> None:
    """Recursively collect products from delivery item lists."""
    for item in entries:
        if not isinstance(item, dict):
            continue
        if item.get("name") and (item.get("id") or "price" in item):
            price_cents = item.get("price", 0)
            quantity = 1
            # Try to find quantity in decorators or directly
            if item.get("quantity"):
                quantity = item["quantity"]
            elif isinstance(item.get("decorators"), list):
                for dec in item["decorators"]:
                    if isinstance(dec, dict) and "quantity" in dec:
                        quantity = dec["quantity"]
                        break
            out.append({
                "product_id": item.get("id", ""),
                "name": item.get("name", ""),
                "price_euros": _cents_to_euros(price_cents),
                "quantity": quantity,
            })
        # Recurse into nested structures
        for sub_key in ("items", "products", "articles"):
            sub = item.get(sub_key)
            if isinstance(sub, list):
                _collect_delivery_products(sub, out)


def _cents_to_euros(cents: Any) -> str:
    """Convert an integer price in cents to a formatted euro string."""
    try:
        c = int(cents)
        return f"{c / 100:.2f}"
    except (ValueError, TypeError):
        return str(cents)


# ---------------------------------------------------------------------------
# Wrap as ADK FunctionTools
# ---------------------------------------------------------------------------

search_picnic_product_tool = FunctionTool(search_picnic_product)
get_picnic_cart_tool = FunctionTool(get_picnic_cart)
add_to_picnic_cart_tool = FunctionTool(add_to_picnic_cart)
remove_from_picnic_cart_tool = FunctionTool(remove_from_picnic_cart)
clear_picnic_cart_tool = FunctionTool(clear_picnic_cart)
get_picnic_delivery_slots_tool = FunctionTool(get_picnic_delivery_slots)
set_picnic_delivery_slot_tool = FunctionTool(set_picnic_delivery_slot)
submit_shopping_list_to_picnic_tool = FunctionTool(submit_shopping_list_to_picnic)
get_picnic_lists_tool = FunctionTool(get_picnic_lists)
get_picnic_list_details_tool = FunctionTool(get_picnic_list_details)
get_picnic_order_history_tool = FunctionTool(get_picnic_order_history)
get_picnic_delivery_details_tool = FunctionTool(get_picnic_delivery_details)

PICNIC_TOOLS = [
    search_picnic_product_tool,
    get_picnic_cart_tool,
    add_to_picnic_cart_tool,
    remove_from_picnic_cart_tool,
    clear_picnic_cart_tool,
    get_picnic_delivery_slots_tool,
    set_picnic_delivery_slot_tool,
    submit_shopping_list_to_picnic_tool,
    get_picnic_lists_tool,
    get_picnic_list_details_tool,
    get_picnic_order_history_tool,
    get_picnic_delivery_details_tool,
]
