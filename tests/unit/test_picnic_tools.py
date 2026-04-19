"""Tests for Picnic agent tools."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Reset the Picnic client singleton before each test."""
    from radbot.tools.picnic import picnic_client

    picnic_client._client = None
    picnic_client._initialized = False
    yield
    picnic_client._client = None
    picnic_client._initialized = False


@pytest.fixture
def mock_client():
    """Return a mock PicnicClientWrapper."""
    client = MagicMock()
    return client


def _patch_client(mock_client):
    """Patch get_picnic_client to return the mock."""
    return patch(
        "radbot.tools.picnic.picnic_tools.get_picnic_client",
        return_value=mock_client,
    )


class TestSearchPicnicProduct:
    def test_returns_results(self, mock_client):
        from radbot.tools.picnic.picnic_tools import search_picnic_product

        mock_client.search.return_value = [
            {"id": "p1", "name": "Whole Milk 1L", "price": 129, "unit_quantity": "1L"},
            {"id": "p2", "name": "Skim Milk 1L", "price": 109, "unit_quantity": "1L"},
        ]

        with _patch_client(mock_client):
            result = search_picnic_product("milk")

        assert result["status"] == "success"
        assert result["count"] == 2
        assert result["results"][0]["product_id"] == "p1"
        assert result["results"][0]["name"] == "Whole Milk 1L"

    def test_returns_error_when_unconfigured(self):
        from radbot.tools.picnic.picnic_tools import search_picnic_product

        with patch(
            "radbot.tools.picnic.picnic_tools.get_picnic_client",
            return_value=None,
        ):
            result = search_picnic_product("milk")
        assert result["status"] == "error"
        assert "not configured" in result["message"]

    def test_handles_search_exception(self, mock_client):
        from radbot.tools.picnic.picnic_tools import search_picnic_product

        mock_client.search.side_effect = Exception("timeout")

        with _patch_client(mock_client):
            result = search_picnic_product("milk")
        assert result["status"] == "error"
        assert "timeout" in result["message"]


class TestGetPicnicCart:
    def test_returns_cart_contents(self, mock_client):
        from radbot.tools.picnic.picnic_tools import get_picnic_cart

        mock_client.get_cart.return_value = {
            "total_price": 599,
            "items": [
                {
                    "name": "Dairy",
                    "id": "cat1",
                    "items": [
                        {
                            "items": [
                                {
                                    "id": "p1",
                                    "name": "Milk",
                                    "price": 129,
                                    "decorators": [{"quantity": 2}],
                                }
                            ]
                        }
                    ],
                }
            ],
        }

        with _patch_client(mock_client):
            result = get_picnic_cart()

        assert result["status"] == "success"
        assert result["total_price"] == 599
        assert result["item_count"] == 1
        assert result["items"][0]["name"] == "Milk"
        assert result["items"][0]["quantity"] == 2


class TestAddToCart:
    def test_adds_product(self, mock_client):
        from radbot.tools.picnic.picnic_tools import add_to_picnic_cart

        mock_client.add_product.return_value = {}

        with _patch_client(mock_client):
            result = add_to_picnic_cart("p1", count=3)

        assert result["status"] == "success"
        mock_client.add_product.assert_called_once_with("p1", count=3)

    def test_minimum_count_is_one(self, mock_client):
        from radbot.tools.picnic.picnic_tools import add_to_picnic_cart

        mock_client.add_product.return_value = {}

        with _patch_client(mock_client):
            add_to_picnic_cart("p1", count=0)

        mock_client.add_product.assert_called_once_with("p1", count=1)


class TestRemoveFromCart:
    def test_removes_product(self, mock_client):
        from radbot.tools.picnic.picnic_tools import remove_from_picnic_cart

        mock_client.remove_product.return_value = {}

        with _patch_client(mock_client):
            result = remove_from_picnic_cart("p1", count=2)

        assert result["status"] == "success"
        mock_client.remove_product.assert_called_once_with("p1", count=2)


class TestClearCart:
    def test_clears_cart(self, mock_client):
        from radbot.tools.picnic.picnic_tools import clear_picnic_cart

        mock_client.clear_cart.return_value = {}

        with _patch_client(mock_client):
            result = clear_picnic_cart()

        assert result["status"] == "success"
        mock_client.clear_cart.assert_called_once()


class TestGetDeliverySlots:
    def test_returns_slots(self, mock_client):
        from radbot.tools.picnic.picnic_tools import get_picnic_delivery_slots

        mock_client.get_delivery_slots.return_value = [
            {
                "slot_list": [
                    {
                        "slot_id": "s1",
                        "window_start": "2026-02-18T10:00:00",
                        "window_end": "2026-02-18T12:00:00",
                        "is_available": True,
                        "minimum_order_value": 3500,
                    },
                    {
                        "slot_id": "s2",
                        "window_start": "2026-02-18T14:00:00",
                        "window_end": "2026-02-18T16:00:00",
                        "is_available": False,
                        "minimum_order_value": 3500,
                    },
                ]
            }
        ]

        with _patch_client(mock_client):
            result = get_picnic_delivery_slots()

        assert result["status"] == "success"
        assert result["count"] == 2
        assert result["slots"][0]["slot_id"] == "s1"
        assert result["slots"][0]["is_available"] is True
        assert result["slots"][1]["is_available"] is False


class TestSetDeliverySlot:
    def test_places_order(self, mock_client):
        from radbot.tools.picnic.picnic_tools import set_picnic_delivery_slot

        mock_client.set_delivery_slot.return_value = {"status": "ok"}

        with _patch_client(mock_client):
            result = set_picnic_delivery_slot("s1")

        assert result["status"] == "success"
        mock_client.set_delivery_slot.assert_called_once_with("s1")

    def test_handles_failure(self, mock_client):
        from radbot.tools.picnic.picnic_tools import set_picnic_delivery_slot

        mock_client.set_delivery_slot.side_effect = Exception("slot unavailable")

        with _patch_client(mock_client):
            result = set_picnic_delivery_slot("s1")

        assert result["status"] == "error"
        assert "slot unavailable" in result["message"]


class TestSubmitShoppingList:
    """The Picnic shopping-list bridge now reads from Telos `project_tasks`
    under the named Telos `projects` entry."""

    @staticmethod
    def _telos_project(ref_code="PRJ9", name="Groceries"):
        from radbot.tools.telos.models import Entry, Section

        return Entry(
            entry_id="pg-id",
            section=Section.PROJECTS,
            ref_code=ref_code,
            content=name,
            metadata={},
            status="active",
        )

    @staticmethod
    def _telos_task(title, parent="PRJ9", quantity=None, status="backlog"):
        from radbot.tools.telos.models import Entry, Section

        meta = {"parent_project": parent, "task_status": status, "title": title}
        if quantity is not None:
            meta["quantity"] = quantity
        return Entry(
            entry_id=f"t-{title}",
            section=Section.PROJECT_TASKS,
            ref_code=None,
            content=title,
            metadata=meta,
            status="active",
        )

    def _patch_telos(self, project, tasks):
        """Patch telos_db.get_entry + list_section to serve a fake project + tasks."""
        from radbot.tools.telos.models import Section

        def _get_entry(section, ref_code):
            if section == Section.PROJECTS and project and ref_code == project.ref_code:
                return project
            return None

        def _list_section(section, status="active"):
            if section == Section.PROJECTS:
                return [project] if project else []
            if section == Section.PROJECT_TASKS:
                return tasks
            return []

        return (
            patch("radbot.tools.telos.db.get_entry", side_effect=_get_entry),
            patch("radbot.tools.telos.db.list_section", side_effect=_list_section),
        )

    def test_bridge_matches_and_adds(self, mock_client):
        from radbot.tools.picnic.picnic_tools import submit_shopping_list_to_picnic

        mock_client.search.side_effect = [
            [{"id": "p1", "name": "Whole Milk 1L", "price": 129}],
            [{"id": "p2", "name": "Fresh Bananas", "price": 169}],
        ]
        mock_client.add_product.return_value = {}
        mock_client.get_cart.return_value = {"total_price": 298}

        project = self._telos_project()
        tasks = [
            self._telos_task("Milk", quantity=2),
            self._telos_task("Bananas", quantity=1),
        ]
        p1, p2 = self._patch_telos(project, tasks)
        with _patch_client(mock_client), p1, p2:
            result = submit_shopping_list_to_picnic("Groceries")

        assert result["status"] == "success"
        assert result["matched_count"] == 2
        assert result["unmatched_count"] == 0
        assert result["cart_total"] == 298

        calls = mock_client.add_product.call_args_list
        assert calls[0].args == ("p1",)
        assert calls[0].kwargs == {"count": 2}

    def test_bridge_reports_unmatched(self, mock_client):
        from radbot.tools.picnic.picnic_tools import submit_shopping_list_to_picnic

        mock_client.search.side_effect = [
            [{"id": "p1", "name": "Milk", "price": 129}],
            [],
        ]
        mock_client.add_product.return_value = {}
        mock_client.get_cart.return_value = {"total_price": 129}

        project = self._telos_project()
        tasks = [
            self._telos_task("Milk", quantity=1),
            self._telos_task("Dragon Fruit"),
        ]
        p1, p2 = self._patch_telos(project, tasks)
        with _patch_client(mock_client), p1, p2:
            result = submit_shopping_list_to_picnic("Groceries")

        assert result["status"] == "success"
        assert result["matched_count"] == 1
        assert result["unmatched_count"] == 1
        assert "Dragon Fruit" in result["unmatched"]

    def test_bridge_empty_list(self, mock_client):
        from radbot.tools.picnic.picnic_tools import submit_shopping_list_to_picnic

        project = self._telos_project()
        p1, p2 = self._patch_telos(project, tasks=[])
        with _patch_client(mock_client), p1, p2:
            result = submit_shopping_list_to_picnic("Groceries")

        assert result["status"] == "error"
        assert "No backlog tasks" in result["message"]

    def test_bridge_project_missing(self, mock_client):
        from radbot.tools.picnic.picnic_tools import submit_shopping_list_to_picnic

        p1, p2 = self._patch_telos(project=None, tasks=[])
        with _patch_client(mock_client), p1, p2:
            result = submit_shopping_list_to_picnic("Groceries")

        assert result["status"] == "error"
        assert "No Telos project" in result["message"]

    def test_bridge_default_quantity(self, mock_client):
        from radbot.tools.picnic.picnic_tools import submit_shopping_list_to_picnic

        mock_client.search.return_value = [{"id": "p1", "name": "Eggs", "price": 299}]
        mock_client.add_product.return_value = {}
        mock_client.get_cart.return_value = {"total_price": 299}

        project = self._telos_project()
        tasks = [self._telos_task("Eggs")]  # no quantity
        p1, p2 = self._patch_telos(project, tasks)
        with _patch_client(mock_client), p1, p2:
            result = submit_shopping_list_to_picnic()

        assert result["status"] == "success"
        mock_client.add_product.assert_called_once_with("p1", count=1)


class TestToolCount:
    def test_picnic_tools_has_ten_tools(self):
        from radbot.tools.picnic.picnic_tools import PICNIC_TOOLS

        assert len(PICNIC_TOOLS) == 10
