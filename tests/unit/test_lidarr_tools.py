"""Tests for Lidarr agent tools."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Reset the Lidarr client singleton before each test."""
    from radbot.tools.lidarr import lidarr_client

    lidarr_client._client = None
    lidarr_client._initialized = False
    yield
    lidarr_client._client = None
    lidarr_client._initialized = False


@pytest.fixture
def mock_client():
    """Return a mock LidarrClient."""
    return MagicMock()


def _patch_client(mock_client):
    """Patch get_lidarr_client to return the mock."""
    return patch(
        "radbot.tools.lidarr.lidarr_tools.get_lidarr_client",
        return_value=mock_client,
    )


class TestSearchLidarrArtist:
    def test_returns_results(self, mock_client):
        from radbot.tools.lidarr.lidarr_tools import search_lidarr_artist

        mock_client.lookup_artist.return_value = [
            {
                "artistName": "Metallica",
                "foreignArtistId": "65f4f0c5-ef9e-490c-aee3-909e7ae6b2ab",
                "overview": "Metallica is an American heavy metal band.",
                "status": "continuing",
                "artistType": "Group",
                "disambiguation": "",
                "id": 0,
            },
            {
                "artistName": "Metallica Tribute",
                "foreignArtistId": "abc-123",
                "overview": "A tribute band.",
                "status": "ended",
                "artistType": "Group",
                "disambiguation": "tribute",
                "id": 0,
            },
        ]

        with _patch_client(mock_client):
            result = search_lidarr_artist("Metallica")

        assert result["status"] == "success"
        assert result["total"] == 2
        assert result["results"][0]["artist_name"] == "Metallica"
        assert (
            result["results"][0]["foreign_artist_id"]
            == "65f4f0c5-ef9e-490c-aee3-909e7ae6b2ab"
        )
        assert result["results"][0]["already_in_library"] is False

    def test_returns_error_when_unconfigured(self):
        from radbot.tools.lidarr.lidarr_tools import search_lidarr_artist

        with patch(
            "radbot.tools.lidarr.lidarr_tools.get_lidarr_client",
            return_value=None,
        ):
            result = search_lidarr_artist("Metallica")
        assert result["status"] == "error"
        assert "not configured" in result["message"]

    def test_handles_search_exception(self, mock_client):
        from radbot.tools.lidarr.lidarr_tools import search_lidarr_artist

        mock_client.lookup_artist.side_effect = Exception("timeout")

        with _patch_client(mock_client):
            result = search_lidarr_artist("Metallica")
        assert result["status"] == "error"
        assert "timeout" in result["message"]


class TestSearchLidarrAlbum:
    def test_returns_results(self, mock_client):
        from radbot.tools.lidarr.lidarr_tools import search_lidarr_album

        mock_client.lookup_album.return_value = [
            {
                "title": "Master of Puppets",
                "foreignAlbumId": "album-id-1",
                "artist": {
                    "artistName": "Metallica",
                    "foreignArtistId": "artist-id-1",
                },
                "releaseDate": "1986-03-03T00:00:00Z",
                "albumType": "Album",
                "overview": "Third studio album.",
                "id": 0,
            },
        ]

        with _patch_client(mock_client):
            result = search_lidarr_album("Master of Puppets")

        assert result["status"] == "success"
        assert result["total"] == 1
        assert result["results"][0]["album_title"] == "Master of Puppets"
        assert result["results"][0]["artist_name"] == "Metallica"
        assert result["results"][0]["already_in_library"] is False

    def test_returns_error_when_unconfigured(self):
        from radbot.tools.lidarr.lidarr_tools import search_lidarr_album

        with patch(
            "radbot.tools.lidarr.lidarr_tools.get_lidarr_client",
            return_value=None,
        ):
            result = search_lidarr_album("album")
        assert result["status"] == "error"

    def test_handles_search_exception(self, mock_client):
        from radbot.tools.lidarr.lidarr_tools import search_lidarr_album

        mock_client.lookup_album.side_effect = Exception("connection error")

        with _patch_client(mock_client):
            result = search_lidarr_album("album")
        assert result["status"] == "error"
        assert "connection error" in result["message"]


class TestAddLidarrArtist:
    def test_adds_artist_with_defaults(self, mock_client):
        from radbot.tools.lidarr.lidarr_tools import add_lidarr_artist

        mock_client.get_root_folders.return_value = [{"path": "/music"}]
        mock_client.get_quality_profiles.return_value = [{"id": 1, "name": "Lossless"}]
        mock_client.get_metadata_profiles.return_value = [{"id": 1, "name": "Standard"}]
        mock_client.add_artist.return_value = {
            "id": 42,
            "artistName": "Metallica",
            "path": "/music/Metallica",
        }

        with _patch_client(mock_client):
            result = add_lidarr_artist("artist-id-1", "Metallica")

        assert result["status"] == "success"
        assert result["artist_id"] == 42
        assert result["artist_name"] == "Metallica"
        assert result["path"] == "/music/Metallica"

        # Verify the POST body
        call_args = mock_client.add_artist.call_args[0][0]
        assert call_args["foreignArtistId"] == "artist-id-1"
        assert call_args["qualityProfileId"] == 1
        assert call_args["metadataProfileId"] == 1
        assert call_args["rootFolderPath"] == "/music"
        assert call_args["monitored"] is True

    def test_returns_error_no_root_folders(self, mock_client):
        from radbot.tools.lidarr.lidarr_tools import add_lidarr_artist

        mock_client.get_root_folders.return_value = []

        with _patch_client(mock_client):
            result = add_lidarr_artist("artist-id-1", "Test")

        assert result["status"] == "error"
        assert "root folder" in result["message"].lower()

    def test_returns_error_no_quality_profiles(self, mock_client):
        from radbot.tools.lidarr.lidarr_tools import add_lidarr_artist

        mock_client.get_root_folders.return_value = [{"path": "/music"}]
        mock_client.get_quality_profiles.return_value = []

        with _patch_client(mock_client):
            result = add_lidarr_artist("artist-id-1", "Test")

        assert result["status"] == "error"
        assert "quality profile" in result["message"].lower()

    def test_returns_error_no_metadata_profiles(self, mock_client):
        from radbot.tools.lidarr.lidarr_tools import add_lidarr_artist

        mock_client.get_root_folders.return_value = [{"path": "/music"}]
        mock_client.get_quality_profiles.return_value = [{"id": 1, "name": "Any"}]
        mock_client.get_metadata_profiles.return_value = []

        with _patch_client(mock_client):
            result = add_lidarr_artist("artist-id-1", "Test")

        assert result["status"] == "error"
        assert "metadata profile" in result["message"].lower()

    def test_returns_error_when_unconfigured(self):
        from radbot.tools.lidarr.lidarr_tools import add_lidarr_artist

        with patch(
            "radbot.tools.lidarr.lidarr_tools.get_lidarr_client",
            return_value=None,
        ):
            result = add_lidarr_artist("id", "Test")
        assert result["status"] == "error"

    def test_handles_api_exception(self, mock_client):
        from radbot.tools.lidarr.lidarr_tools import add_lidarr_artist

        mock_client.get_root_folders.return_value = [{"path": "/music"}]
        mock_client.get_quality_profiles.return_value = [{"id": 1, "name": "Any"}]
        mock_client.get_metadata_profiles.return_value = [{"id": 1, "name": "Std"}]
        mock_client.add_artist.side_effect = Exception("artist already exists")

        with _patch_client(mock_client):
            result = add_lidarr_artist("id", "Test")

        assert result["status"] == "error"
        assert "already exists" in result["message"]


class TestAddLidarrAlbum:
    def test_adds_album_via_artist(self, mock_client):
        from radbot.tools.lidarr.lidarr_tools import add_lidarr_album

        mock_client.get_root_folders.return_value = [{"path": "/music"}]
        mock_client.get_quality_profiles.return_value = [{"id": 1, "name": "Lossless"}]
        mock_client.get_metadata_profiles.return_value = [{"id": 1, "name": "Standard"}]
        mock_client.add_artist.return_value = {
            "id": 42,
            "artistName": "Metallica",
        }

        with _patch_client(mock_client):
            result = add_lidarr_album(
                "album-id-1", "Master of Puppets", "artist-id-1", "Metallica"
            )

        assert result["status"] == "success"
        assert result["album_title"] == "Master of Puppets"
        assert result["artist_id"] == 42

        # Verify the POST body monitors only the specific album
        call_args = mock_client.add_artist.call_args[0][0]
        assert call_args["addOptions"]["monitor"] == "none"
        assert call_args["addOptions"]["albumsToMonitor"] == ["album-id-1"]

    def test_returns_error_when_unconfigured(self):
        from radbot.tools.lidarr.lidarr_tools import add_lidarr_album

        with patch(
            "radbot.tools.lidarr.lidarr_tools.get_lidarr_client",
            return_value=None,
        ):
            result = add_lidarr_album("a", "b", "c", "d")
        assert result["status"] == "error"


class TestListLidarrQualityProfiles:
    def test_returns_profiles(self, mock_client):
        from radbot.tools.lidarr.lidarr_tools import list_lidarr_quality_profiles

        mock_client.get_quality_profiles.return_value = [
            {"id": 1, "name": "Any"},
            {"id": 2, "name": "Lossless"},
            {"id": 3, "name": "Standard"},
        ]

        with _patch_client(mock_client):
            result = list_lidarr_quality_profiles()

        assert result["status"] == "success"
        assert len(result["profiles"]) == 3
        assert result["profiles"][0] == {"id": 1, "name": "Any"}

    def test_returns_error_when_unconfigured(self):
        from radbot.tools.lidarr.lidarr_tools import list_lidarr_quality_profiles

        with patch(
            "radbot.tools.lidarr.lidarr_tools.get_lidarr_client",
            return_value=None,
        ):
            result = list_lidarr_quality_profiles()
        assert result["status"] == "error"


class TestToolCount:
    def test_lidarr_tools_has_five_tools(self):
        from radbot.tools.lidarr.lidarr_tools import LIDARR_TOOLS

        assert len(LIDARR_TOOLS) == 5
