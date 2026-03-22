"""Nomad job template for session worker service jobs.

Generates a JSON job specification compatible with the Nomad HTTP API.
Workers are persistent service jobs — they restart on crash and run
until explicitly stopped.
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Default resource limits for worker containers
DEFAULT_CPU = 500
DEFAULT_MEMORY = 1024


def build_worker_job_spec(
    session_id: str,
    image_tag: str,
    credential_key: str,
    admin_token: str,
    postgres_pass: str,
    *,
    postgres_host: str = "postgres.service.consul",
    postgres_port: int = 5432,
    postgres_user: str = "postgres",
    postgres_db: str = "radbot_todos",
    dns_server: Optional[str] = None,
    cpu: int = DEFAULT_CPU,
    memory: int = DEFAULT_MEMORY,
    datacenters: Optional[list] = None,
    region: str = "global",
    namespace: str = "default",
    extra_env: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Build a Nomad JSON job spec for a session worker.

    Args:
        session_id: Full UUID of the chat session.
        image_tag: Docker image tag (e.g. "v0.14").
        credential_key: RADBOT_CREDENTIAL_KEY value.
        admin_token: RADBOT_ADMIN_TOKEN value.
        postgres_pass: PostgreSQL password.
        postgres_host: PostgreSQL host (default: Consul DNS).
        postgres_port: PostgreSQL port.
        postgres_user: PostgreSQL user.
        postgres_db: PostgreSQL database name.
        dns_server: DNS server IP for Docker container.
        cpu: CPU MHz allocation.
        memory: Memory MB allocation.
        datacenters: List of datacenters (default: ["dc1"]).
        region: Nomad region.
        namespace: Nomad namespace.
        extra_env: Additional environment variables.

    Returns:
        Dict suitable for Nomad API ``POST /v1/jobs``.
    """
    if datacenters is None:
        datacenters = ["dc1"]

    job_id = f"radbot-session-{session_id[:8]}"

    # Build config.yaml content for the template stanza
    config_yaml = (
        f"database:\n"
        f"  host: {postgres_host}\n"
        f"  port: {postgres_port}\n"
        f"  user: {postgres_user}\n"
        f"  password: {postgres_pass}\n"
        f"  db_name: {postgres_db}\n"
    )

    # Environment variables
    env = {
        "RADBOT_CREDENTIAL_KEY": credential_key,
        "RADBOT_ADMIN_TOKEN": admin_token,
        "RADBOT_CONFIG_FILE": "/app/config.yaml",
    }
    if extra_env:
        env.update(extra_env)

    # Docker config
    docker_config: Dict[str, Any] = {
        "image": f"ghcr.io/perrymanuk/radbot:{image_tag}",
        "command": "python",
        "args": [
            "-m",
            "radbot.worker",
            "--session-id",
            session_id,
            "--port",
            "8000",
        ],
        "ports": ["a2a"],
        "volumes": ["local/config.yaml:/app/config.yaml"],
    }
    if dns_server:
        docker_config["dns_servers"] = [dns_server]

    job_spec = {
        "ID": job_id,
        "Name": job_id,
        "Type": "service",
        "Region": region,
        "Datacenters": datacenters,
        "Namespace": namespace,
        "Meta": {
            "session_id": session_id,
            "job_type": "radbot-session-worker",
        },
        "Constraints": [
            {
                "LTarget": "${meta.shared_mount}",
                "Operand": "=",
                "RTarget": "true",
            }
        ],
        "TaskGroups": [
            {
                "Name": "session",
                "Count": 1,
                "Networks": [
                    {
                        "DynamicPorts": [
                            {
                                "Label": "a2a",
                                "To": 8000,
                                "HostNetwork": "lan",
                            }
                        ],
                    }
                ],
                "RestartPolicy": {
                    "Attempts": 3,
                    "Delay": 15_000_000_000,  # 15s in nanoseconds
                    "Interval": 600_000_000_000,  # 10m in nanoseconds
                    "Mode": "delay",
                },
                "Tasks": [
                    {
                        "Name": "agent",
                        "Driver": "docker",
                        "Config": docker_config,
                        "Env": env,
                        "Templates": [
                            {
                                "DestPath": "local/config.yaml",
                                "EmbeddedTmpl": config_yaml,
                                "ChangeMode": "noop",
                            }
                        ],
                        "Services": [
                            {
                                "Name": "radbot-session",
                                "PortLabel": "a2a",
                                "Tags": [
                                    f"session_id={session_id}",
                                ],
                                "Checks": [
                                    {
                                        "Type": "http",
                                        "Path": "/health",
                                        "Interval": 30_000_000_000,  # 30s
                                        "Timeout": 5_000_000_000,  # 5s
                                    }
                                ],
                            }
                        ],
                        "Resources": {
                            "CPU": cpu,
                            "MemoryMB": memory,
                        },
                    }
                ],
            }
        ],
    }

    return {"Job": job_spec}


def build_workspace_worker_spec(
    workspace_id: str,
    image_tag: str,
    credential_key: str,
    admin_token: str,
    postgres_pass: str,
    *,
    postgres_host: str = "postgres.service.consul",
    postgres_port: int = 5432,
    postgres_user: str = "postgres",
    postgres_db: str = "radbot_todos",
    dns_server: Optional[str] = None,
    cpu: int = DEFAULT_CPU,
    memory: int = DEFAULT_MEMORY,
    datacenters: Optional[list] = None,
    region: str = "global",
    namespace: str = "default",
    extra_env: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Build a Nomad JSON job spec for a workspace worker.

    Workspace workers host terminal PTY sessions and run the full agent.
    Keyed by workspace_id rather than session_id.

    Args:
        workspace_id: Full UUID of the workspace.
        image_tag: Docker image tag (e.g. "v0.14").
        credential_key: RADBOT_CREDENTIAL_KEY value.
        admin_token: RADBOT_ADMIN_TOKEN value.
        postgres_pass: PostgreSQL password.
        postgres_host: PostgreSQL host (default: Consul DNS).
        postgres_port: PostgreSQL port.
        postgres_user: PostgreSQL user.
        postgres_db: PostgreSQL database name.
        dns_server: DNS server IP for Docker container.
        cpu: CPU MHz allocation.
        memory: Memory MB allocation.
        datacenters: List of datacenters (default: ["dc1"]).
        region: Nomad region.
        namespace: Nomad namespace.
        extra_env: Additional environment variables.

    Returns:
        Dict suitable for Nomad API ``POST /v1/jobs``.
    """
    if datacenters is None:
        datacenters = ["dc1"]

    job_id = f"radbot-worker-{workspace_id[:8]}"

    config_yaml = (
        f"database:\n"
        f"  host: {postgres_host}\n"
        f"  port: {postgres_port}\n"
        f"  user: {postgres_user}\n"
        f"  password: {postgres_pass}\n"
        f"  db_name: {postgres_db}\n"
    )

    env = {
        "RADBOT_CREDENTIAL_KEY": credential_key,
        "RADBOT_ADMIN_TOKEN": admin_token,
        "RADBOT_CONFIG_FILE": "/app/config.yaml",
    }
    if extra_env:
        env.update(extra_env)

    docker_config: Dict[str, Any] = {
        "image": f"ghcr.io/perrymanuk/radbot-worker:{image_tag}",
        "command": "python",
        "args": [
            "-m",
            "radbot.worker",
            "--workspace-id",
            workspace_id,
            "--port",
            "8000",
        ],
        "ports": ["a2a"],
        "volumes": ["local/config.yaml:/app/config.yaml"],
    }
    if dns_server:
        docker_config["dns_servers"] = [dns_server]

    job_spec = {
        "ID": job_id,
        "Name": job_id,
        "Type": "service",
        "Region": region,
        "Datacenters": datacenters,
        "Namespace": namespace,
        "Meta": {
            "workspace_id": workspace_id,
            "job_type": "radbot-workspace-worker",
        },
        "Constraints": [
            {
                "LTarget": "${meta.shared_mount}",
                "Operand": "=",
                "RTarget": "true",
            }
        ],
        "TaskGroups": [
            {
                "Name": "session",
                "Count": 1,
                "Networks": [
                    {
                        "DynamicPorts": [
                            {
                                "Label": "a2a",
                                "To": 8000,
                                "HostNetwork": "lan",
                            }
                        ],
                    }
                ],
                "RestartPolicy": {
                    "Attempts": 3,
                    "Delay": 15_000_000_000,
                    "Interval": 600_000_000_000,
                    "Mode": "delay",
                },
                "Tasks": [
                    {
                        "Name": "agent",
                        "Driver": "docker",
                        "Config": docker_config,
                        "Env": env,
                        "Templates": [
                            {
                                "DestPath": "local/config.yaml",
                                "EmbeddedTmpl": config_yaml,
                                "ChangeMode": "noop",
                            }
                        ],
                        "Services": [
                            {
                                "Name": "radbot-workspace",
                                "PortLabel": "a2a",
                                "Tags": [
                                    f"workspace_id={workspace_id}",
                                ],
                                "Checks": [
                                    {
                                        "Type": "http",
                                        "Path": "/health",
                                        "Interval": 30_000_000_000,
                                        "Timeout": 5_000_000_000,
                                    }
                                ],
                            }
                        ],
                        "Resources": {
                            "CPU": cpu,
                            "MemoryMB": memory,
                        },
                    }
                ],
            }
        ],
    }

    return {"Job": job_spec}
