"""Unit tests for worker package components.

Tests the Nomad job template generator, idle watchdog, history loader,
and worker DB operations — all without external service dependencies.
"""

import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Nomad Job Template
# ---------------------------------------------------------------------------
class TestNomadJobTemplate:
    """Tests for radbot.worker.nomad_template.build_worker_job_spec."""

    def test_basic_structure(self):
        from radbot.worker.nomad_template import build_worker_job_spec

        spec = build_worker_job_spec(
            session_id="550e8400-e29b-41d4-a716-446655440000",
            image_tag="v0.14",
            credential_key="test-key",
            admin_token="test-token",
            postgres_pass="test-pass",
        )

        assert "Job" in spec
        job = spec["Job"]
        assert job["Type"] == "service"
        assert job["ID"] == "radbot-session-550e8400"
        assert job["Name"] == "radbot-session-550e8400"
        assert job["Datacenters"] == ["dc1"]

    def test_session_id_in_meta(self):
        from radbot.worker.nomad_template import build_worker_job_spec

        spec = build_worker_job_spec(
            session_id="abcdef12-3456-7890-abcd-ef1234567890",
            image_tag="v1.0",
            credential_key="k",
            admin_token="t",
            postgres_pass="p",
        )

        meta = spec["Job"]["Meta"]
        assert meta["session_id"] == "abcdef12-3456-7890-abcd-ef1234567890"
        assert meta["job_type"] == "radbot-session-worker"

    def test_docker_args(self):
        from radbot.worker.nomad_template import build_worker_job_spec

        spec = build_worker_job_spec(
            session_id="test-sid",
            image_tag="v0.14",
            credential_key="k",
            admin_token="t",
            postgres_pass="p",
        )

        task = spec["Job"]["TaskGroups"][0]["Tasks"][0]
        assert task["Config"]["command"] == "python"
        args = task["Config"]["args"]
        assert "-m" in args
        assert "radbot.worker" in args
        assert "--session-id" in args
        assert "test-sid" in args
        assert "--idle-timeout" not in args
        assert "7200" in args

    def test_image_tag(self):
        from radbot.worker.nomad_template import build_worker_job_spec

        spec = build_worker_job_spec(
            session_id="sid",
            image_tag="v0.99",
            credential_key="k",
            admin_token="t",
            postgres_pass="p",
        )

        image = spec["Job"]["TaskGroups"][0]["Tasks"][0]["Config"]["image"]
        assert image == "ghcr.io/perrymanuk/radbot:v0.99"

    def test_env_vars(self):
        from radbot.worker.nomad_template import build_worker_job_spec

        spec = build_worker_job_spec(
            session_id="sid",
            image_tag="v1",
            credential_key="my-cred-key",
            admin_token="my-admin-token",
            postgres_pass="p",
        )

        env = spec["Job"]["TaskGroups"][0]["Tasks"][0]["Env"]
        assert env["RADBOT_CREDENTIAL_KEY"] == "my-cred-key"
        assert env["RADBOT_ADMIN_TOKEN"] == "my-admin-token"
        assert env["RADBOT_CONFIG_FILE"] == "/app/config.yaml"

    def test_extra_env(self):
        from radbot.worker.nomad_template import build_worker_job_spec

        spec = build_worker_job_spec(
            session_id="sid",
            image_tag="v1",
            credential_key="k",
            admin_token="t",
            postgres_pass="p",
            extra_env={"RADBOT_ENV": "dev", "DEBUG": "1"},
        )

        env = spec["Job"]["TaskGroups"][0]["Tasks"][0]["Env"]
        assert env["RADBOT_ENV"] == "dev"
        assert env["DEBUG"] == "1"

    def test_service_registration(self):
        from radbot.worker.nomad_template import build_worker_job_spec

        sid = "550e8400-e29b-41d4-a716-446655440000"
        spec = build_worker_job_spec(
            session_id=sid,
            image_tag="v1",
            credential_key="k",
            admin_token="t",
            postgres_pass="p",
        )

        service = spec["Job"]["TaskGroups"][0]["Tasks"][0]["Services"][0]
        assert service["Name"] == "radbot-session"
        assert f"session_id={sid}" in service["Tags"]
        assert service["Checks"][0]["Path"] == "/health"

    def test_custom_resources(self):
        from radbot.worker.nomad_template import build_worker_job_spec

        spec = build_worker_job_spec(
            session_id="sid",
            image_tag="v1",
            credential_key="k",
            admin_token="t",
            postgres_pass="p",
            cpu=1000,
            memory=2048,
        )

        resources = spec["Job"]["TaskGroups"][0]["Tasks"][0]["Resources"]
        assert resources["CPU"] == 1000
        assert resources["MemoryMB"] == 2048

    def test_shared_mount_constraint(self):
        from radbot.worker.nomad_template import build_worker_job_spec

        spec = build_worker_job_spec(
            session_id="sid",
            image_tag="v1",
            credential_key="k",
            admin_token="t",
            postgres_pass="p",
        )

        constraints = spec["Job"]["Constraints"]
        assert len(constraints) == 1
        assert constraints[0]["LTarget"] == "${meta.shared_mount}"
        assert constraints[0]["RTarget"] == "true"

    def test_restart_policy_fail_mode(self):
        from radbot.worker.nomad_template import build_worker_job_spec

        spec = build_worker_job_spec(
            session_id="sid",
            image_tag="v1",
            credential_key="k",
            admin_token="t",
            postgres_pass="p",
        )

        restart = spec["Job"]["TaskGroups"][0]["RestartPolicy"]
        assert restart["Mode"] == "delay"
        assert restart["Attempts"] == 3

    def test_config_yaml_template(self):
        from radbot.worker.nomad_template import build_worker_job_spec

        spec = build_worker_job_spec(
            session_id="sid",
            image_tag="v1",
            credential_key="k",
            admin_token="t",
            postgres_pass="my-db-pass",
            postgres_host="db.example.com",
            postgres_db="radbot_prod",
        )

        template = spec["Job"]["TaskGroups"][0]["Tasks"][0]["Templates"][0]
        assert "db.example.com" in template["EmbeddedTmpl"]
        assert "my-db-pass" in template["EmbeddedTmpl"]
        assert "radbot_prod" in template["EmbeddedTmpl"]

    def test_dns_server_option(self):
        from radbot.worker.nomad_template import build_worker_job_spec

        spec = build_worker_job_spec(
            session_id="sid",
            image_tag="v1",
            credential_key="k",
            admin_token="t",
            postgres_pass="p",
            dns_server="10.0.0.1",
        )

        docker = spec["Job"]["TaskGroups"][0]["Tasks"][0]["Config"]
        assert docker["dns_servers"] == ["10.0.0.1"]

    def test_no_dns_server_by_default(self):
        from radbot.worker.nomad_template import build_worker_job_spec

        spec = build_worker_job_spec(
            session_id="sid",
            image_tag="v1",
            credential_key="k",
            admin_token="t",
            postgres_pass="p",
        )

        docker = spec["Job"]["TaskGroups"][0]["Tasks"][0]["Config"]
        assert "dns_servers" not in docker

    def test_job_spec_is_json_serializable(self):
        from radbot.worker.nomad_template import build_worker_job_spec

        spec = build_worker_job_spec(
            session_id="sid",
            image_tag="v1",
            credential_key="k",
            admin_token="t",
            postgres_pass="p",
        )

        # Must be serializable for the Nomad HTTP API
        serialized = json.dumps(spec)
        assert len(serialized) > 0
        roundtrip = json.loads(serialized)
        assert roundtrip["Job"]["ID"] == spec["Job"]["ID"]


# ---------------------------------------------------------------------------
# Idle Watchdog
# ---------------------------------------------------------------------------
class TestActivityWatchdog:
    """Tests for radbot.worker.idle_watchdog.ActivityWatchdog."""

    def test_initial_activity(self):
        from radbot.worker.idle_watchdog import ActivityWatchdog

        w = ActivityWatchdog()
        assert w.idle_seconds < 1.0

    def test_touch_resets_idle(self):
        from radbot.worker.idle_watchdog import ActivityWatchdog

        w = ActivityWatchdog()
        # Simulate some passage of time
        w.last_activity = time.monotonic() - 30
        assert w.idle_seconds >= 29
        w.touch()
        assert w.idle_seconds < 1.0

    def test_uptime_increases(self):
        from radbot.worker.idle_watchdog import ActivityWatchdog

        w = ActivityWatchdog()
        w._start_time = time.monotonic() - 60
        assert w.uptime_seconds >= 59


# ---------------------------------------------------------------------------
# History Loader
# ---------------------------------------------------------------------------
class TestHistoryLoader:
    """Tests for radbot.worker.history_loader.load_history_into_session."""

    @pytest.mark.asyncio
    async def test_loads_messages_from_db(self):
        from radbot.worker.history_loader import load_history_into_session

        mock_session = MagicMock()
        mock_service = AsyncMock()

        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
            {"role": "user", "content": "How are you?"},
            {"role": "assistant", "content": "I'm good!"},
        ]

        with patch(
            "radbot.worker.history_loader.chat_operations"
        ) as mock_ops:
            mock_ops.get_messages_by_session_id.return_value = messages

            await load_history_into_session(
                session=mock_session,
                session_id="test-session",
                session_service=mock_service,
                agent_name="beto",
            )

            assert mock_service.append_event.call_count == 4
            mock_ops.get_messages_by_session_id.assert_called_once_with(
                "test-session", limit=30
            )

    @pytest.mark.asyncio
    async def test_skips_empty_messages(self):
        from radbot.worker.history_loader import load_history_into_session

        mock_session = MagicMock()
        mock_service = AsyncMock()

        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": ""},  # Empty
            {"role": "user", "content": "Test"},
        ]

        with patch(
            "radbot.worker.history_loader.chat_operations"
        ) as mock_ops:
            mock_ops.get_messages_by_session_id.return_value = messages

            await load_history_into_session(
                session=mock_session,
                session_id="test-session",
                session_service=mock_service,
            )

            # Only 2 events (user Hello + user Test), assistant was empty
            assert mock_service.append_event.call_count == 2

    @pytest.mark.asyncio
    async def test_no_messages_is_noop(self):
        from radbot.worker.history_loader import load_history_into_session

        mock_session = MagicMock()
        mock_service = AsyncMock()

        with patch(
            "radbot.worker.history_loader.chat_operations"
        ) as mock_ops:
            mock_ops.get_messages_by_session_id.return_value = []

            await load_history_into_session(
                session=mock_session,
                session_id="test-session",
                session_service=mock_service,
            )

            mock_service.append_event.assert_not_called()

    @pytest.mark.asyncio
    async def test_max_history_limit(self):
        from radbot.worker.history_loader import load_history_into_session

        mock_session = MagicMock()
        mock_service = AsyncMock()

        # Create 20 messages, but max_history=5
        messages = [
            {"role": "user", "content": f"msg {i}"}
            for i in range(20)
        ]

        with patch(
            "radbot.worker.history_loader.chat_operations"
        ) as mock_ops:
            mock_ops.get_messages_by_session_id.return_value = messages

            await load_history_into_session(
                session=mock_session,
                session_id="test-session",
                session_service=mock_service,
                max_history=5,
            )

            assert mock_service.append_event.call_count == 5

    @pytest.mark.asyncio
    async def test_handles_db_error_gracefully(self):
        from radbot.worker.history_loader import load_history_into_session

        mock_session = MagicMock()
        mock_service = AsyncMock()

        with patch(
            "radbot.worker.history_loader.chat_operations"
        ) as mock_ops:
            mock_ops.get_messages_by_session_id.side_effect = Exception("DB down")

            # Should not raise
            await load_history_into_session(
                session=mock_session,
                session_id="test-session",
                session_service=mock_service,
            )

            mock_service.append_event.assert_not_called()

    @pytest.mark.asyncio
    async def test_user_assistant_invocation_ids(self):
        from radbot.worker.history_loader import load_history_into_session

        mock_session = MagicMock()
        mock_service = AsyncMock()

        messages = [
            {"role": "user", "content": "Q1"},
            {"role": "assistant", "content": "A1"},
            {"role": "user", "content": "Q2"},
            {"role": "assistant", "content": "A2"},
        ]

        with patch(
            "radbot.worker.history_loader.chat_operations"
        ) as mock_ops:
            mock_ops.get_messages_by_session_id.return_value = messages

            await load_history_into_session(
                session=mock_session,
                session_id="test-session",
                session_service=mock_service,
            )

            events = [
                call.args[1] for call in mock_service.append_event.call_args_list
            ]
            # User/assistant pairs share invocation_id
            assert events[0].invocation_id == events[1].invocation_id
            assert events[2].invocation_id == events[3].invocation_id
            # Different turns have different invocation_ids
            assert events[0].invocation_id != events[2].invocation_id


# ---------------------------------------------------------------------------
# Session Manager Mode
# ---------------------------------------------------------------------------
class TestSessionManagerMode:
    """Tests for local/remote mode switching in SessionManager."""

    def test_default_mode_is_local(self):
        with patch(
            "radbot.web.api.session.session_manager._get_session_mode",
            return_value="local",
        ):
            from radbot.web.api.session.session_manager import SessionManager

            mgr = SessionManager()
            assert mgr.mode == "local"

    def test_remote_mode_from_config(self):
        with patch(
            "radbot.web.api.session.session_manager._get_session_mode",
            return_value="remote",
        ):
            from radbot.web.api.session.session_manager import SessionManager

            mgr = SessionManager()
            mgr._mode = None  # Reset cached mode
            with patch(
                "radbot.web.api.session.session_manager._get_session_mode",
                return_value="remote",
            ):
                assert mgr.mode == "remote"

    @pytest.mark.asyncio
    async def test_set_and_get_runner(self):
        from radbot.web.api.session.session_manager import SessionManager

        mgr = SessionManager()
        mock_runner = MagicMock()
        await mgr.set_runner("session-1", mock_runner)

        result = await mgr.get_runner("session-1")
        assert result is mock_runner

    @pytest.mark.asyncio
    async def test_get_nonexistent_runner(self):
        from radbot.web.api.session.session_manager import SessionManager

        mgr = SessionManager()
        result = await mgr.get_runner("does-not-exist")
        assert result is None

    @pytest.mark.asyncio
    async def test_remove_session(self):
        from radbot.web.api.session.session_manager import SessionManager

        mgr = SessionManager()
        mock_runner = MagicMock()
        await mgr.set_runner("session-1", mock_runner)
        await mgr.remove_session("session-1")

        result = await mgr.get_runner("session-1")
        assert result is None


# ---------------------------------------------------------------------------
# Session Proxy (unit-level, mocked externals)
# ---------------------------------------------------------------------------
class TestSessionProxyUnit:
    """Unit tests for SessionProxy with mocked Nomad/A2A."""

    def test_initialization(self):
        from radbot.web.api.session.session_proxy import SessionProxy

        proxy = SessionProxy(user_id="web_user", session_id="test-session")
        assert proxy.user_id == "web_user"
        assert proxy.session_id == "test-session"
        assert proxy._worker_url is None

    @pytest.mark.asyncio
    async def test_check_health_returns_false_on_unreachable(self):
        from radbot.web.api.session.session_proxy import SessionProxy

        proxy = SessionProxy(user_id="u", session_id="s")
        result = await proxy._check_health("http://127.0.0.1:99999")
        assert result is False

    @pytest.mark.asyncio
    async def test_fallback_local_creates_session_runner(self):
        from radbot.web.api.session.session_proxy import SessionProxy

        proxy = SessionProxy(user_id="web_user", session_id="test-session")

        mock_result = {"response": "hello", "events": []}
        with patch(
            "radbot.web.api.session.session_proxy.SessionRunner"
        ) as MockRunner:
            mock_runner = AsyncMock()
            mock_runner.process_message.return_value = mock_result
            MockRunner.return_value = mock_runner

            result = await proxy._fallback_local("test message")
            assert result["response"] == "hello"
            assert result["source"] == "local_fallback"
            MockRunner.assert_called_once_with(
                user_id="web_user", session_id="test-session"
            )

    @pytest.mark.asyncio
    async def test_process_message_falls_back_when_no_nomad(self):
        from radbot.web.api.session.session_proxy import SessionProxy

        proxy = SessionProxy(user_id="web_user", session_id="test-session")

        mock_result = {"response": "fallback response", "events": []}
        with (
            patch.object(proxy, "_ensure_worker", return_value=None),
            patch.object(proxy, "_fallback_local", return_value={**mock_result, "source": "local_fallback"}) as mock_fb,
        ):
            result = await proxy.process_message("hello")
            mock_fb.assert_called_once()
            assert result["source"] == "local_fallback"

    @pytest.mark.asyncio
    async def test_process_message_uses_worker_when_available(self):
        from radbot.web.api.session.session_proxy import SessionProxy

        proxy = SessionProxy(user_id="web_user", session_id="test-session")

        with (
            patch.object(proxy, "_ensure_worker", return_value="http://worker:8000"),
            patch.object(proxy, "_send_a2a_message", return_value="worker response"),
            patch("radbot.web.api.session.session_proxy.touch_worker"),
        ):
            result = await proxy.process_message("hello")
            assert result["response"] == "worker response"
            assert result["source"] == "remote_worker"

    @pytest.mark.asyncio
    async def test_process_message_falls_back_on_a2a_failure(self):
        from radbot.web.api.session.session_proxy import SessionProxy

        proxy = SessionProxy(user_id="web_user", session_id="test-session")

        mock_result = {"response": "local", "events": [], "source": "local_fallback"}
        with (
            patch.object(proxy, "_ensure_worker", return_value="http://worker:8000"),
            patch.object(proxy, "_send_a2a_message", return_value=None),
            patch.object(proxy, "_fallback_local", return_value=mock_result),
        ):
            result = await proxy.process_message("hello")
            assert result["source"] == "local_fallback"

    def test_get_max_workers_default(self):
        from radbot.web.api.session.session_proxy import SessionProxy

        proxy = SessionProxy(user_id="u", session_id="s")
        with patch(
            "radbot.web.api.session.session_proxy.config_loader"
        ) as mock_cfg:
            mock_cfg.config = {}
            assert proxy._get_max_workers() == 10

    def test_get_max_workers_from_config(self):
        from radbot.web.api.session.session_proxy import SessionProxy

        proxy = SessionProxy(user_id="u", session_id="s")
        with patch(
            "radbot.web.api.session.session_proxy.config_loader"
        ) as mock_cfg:
            mock_cfg.config = {"agent": {"max_session_workers": 5}}
            assert proxy._get_max_workers() == 5

    @pytest.mark.asyncio
    async def test_spawn_worker_respects_limit(self):
        from radbot.web.api.session.session_proxy import SessionProxy

        proxy = SessionProxy(user_id="u", session_id="s")

        with (
            patch("radbot.web.api.session.session_proxy.get_nomad_client") as mock_get,
            patch("radbot.web.api.session.session_proxy.count_active_workers", return_value=10),
            patch.object(proxy, "_get_max_workers", return_value=10),
            patch.object(proxy, "_get_bootstrap_secrets", return_value={"credential_key": "k", "admin_token": "t", "postgres_pass": "p"}),
        ):
            mock_get.return_value = MagicMock()
            result = await proxy._spawn_worker()
            assert result is None  # Should refuse due to limit
