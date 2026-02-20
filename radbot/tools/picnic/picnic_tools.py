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

PICNIC_TOOLS = [
    search_picnic_product_tool,
    get_picnic_cart_tool,
    add_to_picnic_cart_tool,
    remove_from_picnic_cart_tool,
    clear_picnic_cart_tool,
    get_picnic_delivery_slots_tool,
    set_picnic_delivery_slot_tool,
    submit_shopping_list_to_picnic_tool,
]
