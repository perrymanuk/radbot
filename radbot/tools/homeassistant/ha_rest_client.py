"""
Home Assistant REST API client for radbot.

This module provides a client for interacting with the Home Assistant REST API,
enabling entity state retrieval and control.
"""

import logging
from typing import Any, Dict, List, Optional, Union

import requests
from requests.exceptions import ConnectionError, HTTPError, RequestException, Timeout

# Set up logging
logger = logging.getLogger(__name__)


class HomeAssistantRESTClient:
    """
    A client for interacting with the Home Assistant REST API.
    """

    def __init__(self, base_url: str, token: str):
        """
        Initializes the Home Assistant client.

        Args:
            base_url: The base URL of the Home Assistant instance (e.g., http://homeassistant.local:8123).
            token: The Long-Lived Access Token.
        """
        if not base_url.endswith("/"):
            base_url += "/"
        self.base_url = base_url
        self.api_url = f"{self.base_url}api/"
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        self._session = requests.Session()
        self._session.headers.update(self._headers)
        logger.info(f"HomeAssistantClient initialized for URL: {self.base_url}")

    def _request(self, method: str, endpoint: str, **kwargs) -> Optional[Any]:
        """
        Makes a request to the Home Assistant API.

        Args:
            method: HTTP method (GET, POST, etc.).
            endpoint: API endpoint path (e.g., 'states', 'services/light/toggle').
            **kwargs: Additional arguments passed to requests.request.

        Returns:
            Parsed JSON response, or None if an error occurs or response is empty.
        """
        url = f"{self.api_url}{endpoint}"
        try:
            response = self._session.request(
                method, url, **kwargs, timeout=10
            )  # Add timeout
            logger.debug(
                f"Request to {url} ({method}) - Status: {response.status_code}"
            )

            if response.status_code == 401:
                logger.error(
                    "Authentication failed (401). Check your Long-Lived Access Token."
                )
                return None
            if response.status_code == 404:
                logger.warning(f"Resource not found (404) at endpoint: {endpoint}")
                return None  # Consistent handling for not found

            response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)

            # Handle potential empty responses for certain successful calls (e.g., 200 OK with no body)
            if response.content:
                return response.json()
            else:
                return {}  # Return empty dict for successful calls with no content

        except Timeout:
            logger.error(f"Request timed out: {method} {url}")
            return None
        except ConnectionError as e:
            logger.error(f"Connection error: {method} {url} - {e}")
            return None
        except HTTPError as e:
            logger.error(
                f"HTTP error: {method} {url} - Status: {e.response.status_code} - Response: {e.response.text}"
            )
            return None
        except RequestException as e:
            logger.error(
                f"An unexpected error occurred during request: {method} {url} - {e}"
            )
            return None
        except ValueError:  # JSONDecodeError inherits from ValueError
            logger.error(f"Failed to decode JSON response from {url}")
            return None

    def get_api_status(self) -> bool:
        """
        Checks if the Home Assistant API is running.

        Returns:
            True if API is running, False otherwise.
        """
        response_data = self._request("GET", "")
        return (
            response_data is not None and response_data.get("message") == "API running."
        )

    def list_entities(self) -> Optional[List[Dict[str, Any]]]:
        """
        Lists all entities and their states.

        Returns:
            List of entity state objects or None if an error occurred.
        """
        return self._request("GET", "states")

    def get_state(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """
        Gets the state of a specific entity.

        Args:
            entity_id: The entity ID to get state for.

        Returns:
            Entity state object or None if not found or an error occurred.
        """
        if not entity_id:
            logger.warning("get_state called with empty entity_id.")
            return None
        return self._request("GET", f"states/{entity_id}")

    def call_service(
        self,
        domain: str,
        service: str,
        entity_id: Union[str, List[str]],
        additional_data: Optional[Dict[str, Any]] = None,
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Calls a service in Home Assistant.

        Args:
            domain: The domain of the service (e.g., 'light', 'switch').
            service: The service to call (e.g., 'turn_on', 'toggle').
            entity_id: The entity ID or list of entity IDs to target.
            additional_data: Optional additional data for the service call.

        Returns:
            List of states that changed or None if an error occurred.
        """
        if not domain or not service or not entity_id:
            logger.warning(
                "call_service called with missing domain, service, or entity_id."
            )
            return None

        payload = {"entity_id": entity_id}

        # Add any additional data to the payload
        if additional_data:
            payload.update(additional_data)

        endpoint = f"services/{domain}/{service}"
        response = self._request("POST", endpoint, json=payload)
        # The response is a list of states that changed
        return response if isinstance(response, list) else None

    def turn_on_entity(
        self, entity_id: str, **kwargs
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Turns on an entity.

        Args:
            entity_id: The entity ID to turn on.
            **kwargs: Optional additional parameters for the turn_on service.

        Returns:
            List of states that changed or None if an error occurred.
        """
        if not entity_id:
            logger.warning("turn_on_entity called with empty entity_id.")
            return None

        # Determine domain from entity_id (e.g., 'light.living_room' -> 'light')
        parts = entity_id.split(".")
        if not parts or len(parts) < 2:
            logger.error(f"Could not determine domain for entity_id: {entity_id}")
            return None

        domain = parts[0]
        logger.info(f"Turning on entity: {entity_id} (domain: {domain})")
        return self.call_service(
            domain, "turn_on", entity_id, kwargs if kwargs else None
        )

    def turn_off_entity(self, entity_id: str) -> Optional[List[Dict[str, Any]]]:
        """
        Turns off an entity.

        Args:
            entity_id: The entity ID to turn off.

        Returns:
            List of states that changed or None if an error occurred.
        """
        if not entity_id:
            logger.warning("turn_off_entity called with empty entity_id.")
            return None

        # Determine domain from entity_id (e.g., 'light.living_room' -> 'light')
        parts = entity_id.split(".")
        if not parts or len(parts) < 2:
            logger.error(f"Could not determine domain for entity_id: {entity_id}")
            return None

        domain = parts[0]
        logger.info(f"Turning off entity: {entity_id} (domain: {domain})")
        return self.call_service(domain, "turn_off", entity_id)

    def toggle_entity(self, entity_id: str) -> Optional[List[Dict[str, Any]]]:
        """
        Toggles an entity (assuming it supports the 'toggle' service).

        Args:
            entity_id: The entity ID to toggle.

        Returns:
            List of states that changed or None if an error occurred.
        """
        if not entity_id:
            logger.warning("toggle_entity called with empty entity_id.")
            return None

        # Determine domain from entity_id (e.g., 'light.living_room' -> 'light')
        parts = entity_id.split(".")
        if not parts or len(parts) < 2:
            logger.error(f"Could not determine domain for entity_id: {entity_id}")
            return None

        domain = parts[0]
        logger.info(f"Toggling entity: {entity_id} (domain: {domain})")
        return self.call_service(domain, "toggle", entity_id)
