"""Unit tests for worker package components.

Tests the Nomad job template generator and SessionManager — all without
external service dependencies.
"""

import json
from unittest.mock import MagicMock

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
        # Workers no longer self-terminate (idle watchdog removed in 393c173)
        assert "--idle-timeout" not in args
        # Worker must bind a port for the PTY/A2A server
        assert "--port" in args

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
# Session Manager Mode
# ---------------------------------------------------------------------------
class TestSessionManagerMode:
    """Tests for SessionManager (always local for chat sessions)."""

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
