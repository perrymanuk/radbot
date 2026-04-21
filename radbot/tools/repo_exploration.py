"""Read-only code exploration tools for Scout (EX9).

Scout uses these to pre-flight features against public repos and emit exact
file manifests for Claude Code. All operations are jailed to ``REPO_ROOT``
(``/data/repos`` by default) and only read-only primitives are exposed to
the agent — we deliberately avoid LSPs because they execute workspace code
(see ``wiki/concepts/lsp-dependency-trap.md``).

Tools:
- ``repo_sync`` / ``repo_search`` — PT34 (clone + ripgrep neighborhood matches).
- ``repo_map`` — PT35 (universal-ctags structural skeleton per file).
- ``repo_references`` — PT35 (ctags-for-defs + rg-word-boundary for usages).
- ``repo_read`` — PT36 (jailed file-slice read so Scout can quote a specific range).

EX9 originally specified GitHub's ``stack-graphs`` for cross-file references.
That project is archived/source-only — no prebuilt binaries — so we use
**universal-ctags + rg** instead. Same security story (parsers only, no code
execution), prebuilt in apt, multi-language. ast-grep is also in the image
for future advanced structural queries.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from google.adk.tools import FunctionTool

logger = logging.getLogger(__name__)


REPO_ROOT = Path(os.environ.get("RADBOT_REPO_ROOT", "/data/repos")).resolve()

# Local directory name: alnum + dot/dash/underscore, no slashes.
_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")

# Public-host allowlist. V1 of EX9 explicitly defers PAT/secret injection,
# so we only accept hosts that serve public repos over anonymous https.
_PUBLIC_GIT_HOSTS = frozenset(
    {"github.com", "gitlab.com", "bitbucket.org", "codeberg.org", "git.sr.ht"}
)

_GIT_TIMEOUT_S = 300
_RG_TIMEOUT_S = 60
_CTAGS_TIMEOUT_S = 60

# Directories we never descend into — noise and/or big.
_CTAGS_EXCLUDES = (
    ".git",
    "node_modules",
    "dist",
    "build",
    "target",
    ".venv",
    "venv",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".tox",
    ".next",
    ".cache",
)


def _ensure_root() -> Path:
    REPO_ROOT.mkdir(parents=True, exist_ok=True)
    return REPO_ROOT


def _validate_repo_name(repo_name: str) -> Path:
    """Resolve ``repo_name`` to a direct child of REPO_ROOT, refusing traversal."""
    if not repo_name or not _SAFE_NAME_RE.match(repo_name):
        raise ValueError(
            f"invalid repo_name {repo_name!r}: must match {_SAFE_NAME_RE.pattern}"
        )
    root = _ensure_root()
    target = (root / repo_name).resolve()
    if target.parent != root:
        raise ValueError(f"repo_name {repo_name!r} escapes the repo root")
    return target


def _validate_subpath(repo_dir: Path, subpath: Optional[str]) -> Path:
    """Resolve ``subpath`` inside ``repo_dir``, refusing traversal."""
    if not subpath:
        return repo_dir
    candidate = (repo_dir / subpath).resolve()
    try:
        candidate.relative_to(repo_dir)
    except ValueError as e:
        raise ValueError(f"subpath {subpath!r} escapes repo {repo_dir.name!r}") from e
    return candidate


def _validate_public_url(repo_url: str) -> str:
    parsed = urlparse(repo_url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"repo_url scheme {parsed.scheme!r} not allowed (use https)")
    if not parsed.hostname:
        raise ValueError("repo_url has no hostname")
    if "@" in (parsed.netloc or ""):
        raise ValueError("repo_url must not embed credentials")
    host = parsed.hostname.lower()
    if host not in _PUBLIC_GIT_HOSTS:
        raise ValueError(
            f"host {host!r} not in public-host allowlist {sorted(_PUBLIC_GIT_HOSTS)}"
        )
    return repo_url


def _git_env() -> Dict[str, str]:
    # Pass through PATH only; explicitly disable any interactive prompts so a
    # private/missing repo fails fast instead of hanging on credentials.
    return {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_ASKPASS": "/bin/true",
        "HOME": os.environ.get("HOME", "/tmp"),
    }


def _authenticate_github_url(url: str) -> str:
    """Rewrite a github.com URL to use a GitHub App installation token.

    Non-github hosts pass through unchanged. For github.com, the GitHub App
    MUST be configured — we don't silently fall back to anonymous clones,
    because that hides config drift and fails confusingly on private repos.
    Raises RuntimeError if the App can't mint a token.
    """
    parsed = urlparse(url)
    if (parsed.hostname or "").lower() != "github.com":
        return url

    from radbot.config.config_loader import config_loader

    config_loader.load_db_config()
    from radbot.tools.github.github_app_client import get_github_client

    client = get_github_client()
    if client is None:
        raise RuntimeError(
            "GitHub App not configured — set integrations.github via the admin UI "
            "(/admin/) or GITHUB_APP_ID/GITHUB_INSTALLATION_ID/GITHUB_APP_PRIVATE_KEY env vars"
        )
    token = client._get_installation_token()
    return f"https://x-access-token:{token}@github.com{parsed.path}"


def repo_sync(repo_url: str, repo_name: str) -> Dict[str, Any]:
    """Clone or fast-forward-pull a git repo into ``/data/repos/<repo_name>``.

    Args:
        repo_url: Full https URL. Allowlisted hosts: github.com, gitlab.com,
            bitbucket.org, codeberg.org, git.sr.ht. Credentials embedded in
            the URL are rejected. github.com URLs are transparently rewritten
            to use the configured GitHub App installation token, which enables
            cloning private repos the App has access to.
        repo_name: Local directory name (alnum, dot, dash, underscore — no slashes).

    Returns:
        ``{status, repo_name, path, action, commit, output}`` on success
        (``action`` is ``"clone"`` or ``"pull"``), or ``{status: "error", error}``.
    """
    try:
        url = _validate_public_url(repo_url)
        target = _validate_repo_name(repo_name)
    except ValueError as e:
        return {"status": "error", "error": str(e)}

    git = shutil.which("git")
    if not git:
        return {"status": "error", "error": "git binary not found on PATH"}

    try:
        auth_url = _authenticate_github_url(url)
    except RuntimeError as e:
        return {"status": "error", "error": str(e)}

    if (target / ".git").exists():
        action = "pull"
        # Refresh the remote URL so a previously-minted (now-expired) token is
        # replaced with a fresh one before pulling.
        subprocess.run(
            [git, "-C", str(target), "remote", "set-url", "origin", auth_url],
            check=False,
            capture_output=True,
            timeout=10,
            env=_git_env(),
        )
        cmd = [git, "-C", str(target), "pull", "--ff-only", "--depth=1", "origin"]
    else:
        action = "clone"
        cmd = [git, "clone", "--depth=1", "--single-branch", auth_url, str(target)]

    try:
        proc = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_S,
            env=_git_env(),
        )
    except subprocess.TimeoutExpired:
        return {
            "status": "error",
            "error": f"{action} timed out after {_GIT_TIMEOUT_S}s",
        }

    # Strip any leaked installation token from git's output before returning.
    def _redact(s: str) -> str:
        return re.sub(r"x-access-token:[A-Za-z0-9_]+@", "x-access-token:***@", s)

    if proc.returncode != 0:
        return {
            "status": "error",
            "action": action,
            "error": _redact((proc.stderr or proc.stdout or "").strip())[:2000],
        }

    head = subprocess.run(
        [git, "-C", str(target), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        timeout=10,
        env=_git_env(),
    )
    return {
        "status": "success",
        "repo_name": repo_name,
        "path": str(target),
        "action": action,
        "commit": head.stdout.strip(),
        "output": _redact((proc.stdout + proc.stderr).strip())[:2000],
    }


def repo_search(
    query: str,
    repo_name: str,
    subpath: Optional[str] = None,
    file_glob: Optional[str] = None,
    max_matches: int = 50,
    context_lines: int = 3,
) -> Dict[str, Any]:
    """Search a synced repo with ripgrep, returning structured neighborhood matches.

    Args:
        query: Pattern passed to rg (regex by default).
        repo_name: Name of a previously-synced repo under ``/data/repos``.
        subpath: Optional sub-directory inside the repo to limit the search.
        file_glob: Optional rg glob (e.g. ``"*.py"``) to filter files.
        max_matches: Cap on returned matches (1..500). Default 50.
        context_lines: Lines of context above/below each match (0..10). Default 3.

    Returns:
        ``{status, repo_name, count, truncated, matches}`` where each match is
        ``{path, line, text, before: [{line, text}...], after: [...]}``.
    """
    if not query:
        return {"status": "error", "error": "query is required"}

    try:
        repo_dir = _validate_repo_name(repo_name)
        if not repo_dir.exists():
            return {
                "status": "error",
                "error": f"repo {repo_name!r} not synced; call repo_sync first",
            }
        search_dir = _validate_subpath(repo_dir, subpath)
    except ValueError as e:
        return {"status": "error", "error": str(e)}

    max_matches = max(1, min(500, int(max_matches)))
    context_lines = max(0, min(10, int(context_lines)))

    rg = shutil.which("rg")
    if not rg:
        return {"status": "error", "error": "ripgrep (rg) binary not found"}

    cmd = [rg, "--json", "-C", str(context_lines), "--max-count", str(max_matches)]
    if file_glob:
        cmd += ["-g", file_glob]
    cmd += ["--", query, str(search_dir)]

    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=_RG_TIMEOUT_S
        )
    except subprocess.TimeoutExpired:
        return {"status": "error", "error": f"ripgrep timed out after {_RG_TIMEOUT_S}s"}

    # rg exits 0 = matches, 1 = no matches, 2 = error.
    if proc.returncode not in (0, 1):
        return {"status": "error", "error": (proc.stderr or "").strip()[:2000]}

    matches = _parse_rg_json(proc.stdout, repo_dir, max_matches)
    return {
        "status": "success",
        "repo_name": repo_name,
        "count": len(matches),
        "truncated": len(matches) >= max_matches,
        "matches": matches,
    }


def _parse_rg_json(stdout: str, repo_dir: Path, cap: int) -> List[Dict[str, Any]]:
    """Convert rg --json event stream into compact match records."""
    matches: List[Dict[str, Any]] = []
    before_buf: List[Dict[str, Any]] = []
    pending_match: Optional[Dict[str, Any]] = None

    def rel(p: str) -> str:
        try:
            return str(Path(p).resolve().relative_to(repo_dir))
        except Exception:
            return p

    for line in stdout.splitlines():
        if not line:
            continue
        try:
            evt = json.loads(line)
        except json.JSONDecodeError:
            continue
        et = evt.get("type")
        data = evt.get("data") or {}
        if et == "begin":
            before_buf = []
            pending_match = None
        elif et == "context":
            text = (data.get("lines") or {}).get("text", "").rstrip("\n")
            ln = data.get("line_number")
            entry = {"line": ln, "text": text}
            if pending_match is not None and len(pending_match["after"]) < 10:
                pending_match["after"].append(entry)
            else:
                before_buf.append(entry)
                before_buf = before_buf[-10:]
        elif et == "match":
            if len(matches) >= cap:
                break
            text = (data.get("lines") or {}).get("text", "").rstrip("\n")
            m = {
                "path": rel(((data.get("path") or {}).get("text")) or ""),
                "line": data.get("line_number"),
                "text": text,
                "before": before_buf,
                "after": [],
            }
            matches.append(m)
            pending_match = m
            before_buf = []
        elif et == "end":
            pending_match = None
            before_buf = []
    return matches


def _run_ctags(target: Path, languages: Optional[List[str]] = None) -> Dict[str, Any]:
    """Run universal-ctags --output-format=json over a path.

    Returns ``{status, tags: [...]}``. Each tag dict has at least
    ``{name, path, line, kind, scope?, signature?}``.
    """
    ctags = shutil.which("ctags")
    if not ctags:
        return {"status": "error", "error": "universal-ctags binary not found"}

    cmd = [
        ctags,
        "--output-format=json",
        "--fields=+nKzs",  # +n=line, +K=kindLong, +z=kind w/ tag, +s=scope
        "-R",
    ]
    for excl in _CTAGS_EXCLUDES:
        cmd.append(f"--exclude={excl}")
    if languages:
        cleaned = ",".join(
            lang.strip()
            for lang in languages
            if lang and re.match(r"^[A-Za-z0-9+#-]+$", lang.strip())
        )
        if cleaned:
            cmd.append(f"--languages={cleaned}")
    cmd += ["-f", "-", str(target)]

    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=_CTAGS_TIMEOUT_S
        )
    except subprocess.TimeoutExpired:
        return {
            "status": "error",
            "error": f"ctags timed out after {_CTAGS_TIMEOUT_S}s",
        }

    if proc.returncode != 0:
        return {"status": "error", "error": (proc.stderr or "").strip()[:2000]}

    tags: List[Dict[str, Any]] = []
    for line in proc.stdout.splitlines():
        if not line:
            continue
        try:
            t = json.loads(line)
        except json.JSONDecodeError:
            continue
        if t.get("_type") != "tag":
            continue
        tags.append(t)
    return {"status": "success", "tags": tags}


def repo_map(
    repo_name: str,
    subpath: Optional[str] = None,
    languages: Optional[List[str]] = None,
    max_files: int = 200,
    max_symbols_per_file: int = 50,
) -> Dict[str, Any]:
    """Return a structural skeleton of a synced repo: definitions grouped by file.

    Uses universal-ctags to extract every top-level/scoped definition (function,
    class, method, struct, etc.) per file, then groups them and applies caps.
    Lets Scout build a Claude-Code-ready file manifest without reading bodies.

    Args:
        repo_name: Name of a previously-synced repo under ``/data/repos``.
        subpath: Optional sub-directory inside the repo to limit the map.
        languages: Optional list of ctags language names (e.g. ``["Python", "Go"]``)
            to restrict the parse. Each must match ``^[A-Za-z0-9+#-]+$``.
        max_files: Cap on returned files (1..1000). Default 200.
        max_symbols_per_file: Cap on symbols per file (1..500). Default 50.

    Returns:
        ``{status, repo_name, file_count, files: [{path, symbols: [{name, kind,
        line, scope?, signature?}]}], truncated_files, truncated_files_omitted}``.
    """
    try:
        repo_dir = _validate_repo_name(repo_name)
        if not repo_dir.exists():
            return {
                "status": "error",
                "error": f"repo {repo_name!r} not synced; call repo_sync first",
            }
        target = _validate_subpath(repo_dir, subpath)
    except ValueError as e:
        return {"status": "error", "error": str(e)}

    max_files = max(1, min(1000, int(max_files)))
    max_symbols_per_file = max(1, min(500, int(max_symbols_per_file)))

    res = _run_ctags(target, languages=languages)
    if res["status"] != "success":
        return res

    by_file: Dict[str, List[Dict[str, Any]]] = {}
    for t in res["tags"]:
        raw_path = t.get("path") or ""
        try:
            rel = str(Path(raw_path).resolve().relative_to(repo_dir))
        except Exception:
            rel = raw_path
        sym = {
            "name": t.get("name"),
            "kind": t.get("kind"),
            "line": t.get("line"),
        }
        scope = t.get("scope")
        if scope:
            sym["scope"] = scope
        sig = t.get("signature")
        if sig:
            sym["signature"] = sig
        by_file.setdefault(rel, []).append(sym)

    # Sort symbols within a file by line; stable file ordering by path.
    files_sorted = sorted(by_file.items(), key=lambda kv: kv[0])
    truncated_files_omitted = max(0, len(files_sorted) - max_files)
    files_sorted = files_sorted[:max_files]

    files_out: List[Dict[str, Any]] = []
    for path, syms in files_sorted:
        syms.sort(key=lambda s: (s.get("line") or 0, s.get("name") or ""))
        truncated = len(syms) > max_symbols_per_file
        files_out.append(
            {
                "path": path,
                "symbols": syms[:max_symbols_per_file],
                "truncated_symbols": truncated,
            }
        )

    return {
        "status": "success",
        "repo_name": repo_name,
        "file_count": len(files_out),
        "files": files_out,
        "truncated_files": truncated_files_omitted > 0,
        "truncated_files_omitted": truncated_files_omitted,
    }


def repo_references(
    symbol: str,
    repo_name: str,
    subpath: Optional[str] = None,
    file_glob: Optional[str] = None,
    max_results: int = 200,
) -> Dict[str, Any]:
    """Find every definition + reference of ``symbol`` in a synced repo.

    Stateless replacement for the LSP/stack-graphs flow:
    - **Definitions** come from universal-ctags filtered by exact name.
    - **References** come from ripgrep with word boundaries (``-w``) over
      the same path. Definitions are also present in the references list;
      consumers that want only "callers" can subtract by ``(path, line)``.

    Args:
        symbol: Identifier to look up. Must match ``^[A-Za-z_][A-Za-z0-9_]*$``
            (most languages' identifier shape; refuses regex / shell metachars).
        repo_name: Name of a previously-synced repo under ``/data/repos``.
        subpath: Optional sub-directory inside the repo to scope the lookup.
        file_glob: Optional rg glob (e.g. ``"*.py"``) applied to the rg pass.
        max_results: Cap on returned references (1..1000). Default 200.
            Definitions are always included and don't count against the cap.

    Returns:
        ``{status, symbol, repo_name, definitions: [{path, line, kind, scope?,
        signature?}], references: [{path, line, text}], truncated_references}``.
    """
    if not symbol or not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", symbol):
        return {
            "status": "error",
            "error": "symbol must match ^[A-Za-z_][A-Za-z0-9_]*$",
        }

    try:
        repo_dir = _validate_repo_name(repo_name)
        if not repo_dir.exists():
            return {
                "status": "error",
                "error": f"repo {repo_name!r} not synced; call repo_sync first",
            }
        target = _validate_subpath(repo_dir, subpath)
    except ValueError as e:
        return {"status": "error", "error": str(e)}

    max_results = max(1, min(1000, int(max_results)))

    # Definitions via ctags.
    ctags_res = _run_ctags(target)
    if ctags_res["status"] != "success":
        return ctags_res
    definitions: List[Dict[str, Any]] = []
    for t in ctags_res["tags"]:
        if t.get("name") != symbol:
            continue
        raw_path = t.get("path") or ""
        try:
            rel = str(Path(raw_path).resolve().relative_to(repo_dir))
        except Exception:
            rel = raw_path
        d = {"path": rel, "line": t.get("line"), "kind": t.get("kind")}
        if t.get("scope"):
            d["scope"] = t["scope"]
        if t.get("signature"):
            d["signature"] = t["signature"]
        definitions.append(d)

    # References via rg word-boundary search.
    rg = shutil.which("rg")
    if not rg:
        return {"status": "error", "error": "ripgrep (rg) binary not found"}

    cmd = [rg, "--json", "-w", "--max-count", str(max_results)]
    if file_glob:
        cmd += ["-g", file_glob]
    cmd += ["--", symbol, str(target)]

    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=_RG_TIMEOUT_S
        )
    except subprocess.TimeoutExpired:
        return {"status": "error", "error": f"ripgrep timed out after {_RG_TIMEOUT_S}s"}

    if proc.returncode not in (0, 1):
        return {"status": "error", "error": (proc.stderr or "").strip()[:2000]}

    references: List[Dict[str, Any]] = []
    for line in proc.stdout.splitlines():
        if not line:
            continue
        try:
            evt = json.loads(line)
        except json.JSONDecodeError:
            continue
        if evt.get("type") != "match":
            continue
        data = evt.get("data") or {}
        text = (data.get("lines") or {}).get("text", "").rstrip("\n")
        raw_path = (data.get("path") or {}).get("text") or ""
        try:
            rel = str(Path(raw_path).resolve().relative_to(repo_dir))
        except Exception:
            rel = raw_path
        references.append({"path": rel, "line": data.get("line_number"), "text": text})
        if len(references) >= max_results:
            break

    return {
        "status": "success",
        "symbol": symbol,
        "repo_name": repo_name,
        "definitions": definitions,
        "references": references,
        "truncated_references": len(references) >= max_results,
    }


_READ_MAX_LINES = 2000  # absolute hard cap per call
_READ_DEFAULT_LINES = 500  # default slice when caller doesn't specify
_READ_LINE_TRUNC = 4096  # individual line cap (chars)
_READ_BINARY_PROBE_BYTES = 8192  # how much we sniff for binary detection


def _looks_binary(path: Path) -> bool:
    """Return True if the first ``_READ_BINARY_PROBE_BYTES`` contain a NUL byte."""
    try:
        with path.open("rb") as fh:
            chunk = fh.read(_READ_BINARY_PROBE_BYTES)
    except OSError:
        return False
    return b"\x00" in chunk


def repo_read(
    repo_name: str,
    path: str,
    start_line: int = 1,
    end_line: Optional[int] = None,
    max_lines: int = _READ_DEFAULT_LINES,
) -> Dict[str, Any]:
    """Read a slice of a text file from a synced repo.

    Use this after ``repo_map`` / ``repo_search`` / ``repo_references`` give
    you a ``(path, line)`` of interest, when you want to actually quote the
    surrounding code.

    Args:
        repo_name: Name of a previously-synced repo under ``/data/repos``.
        path: Repo-relative path to a text file.
        start_line: 1-indexed first line to return. Default 1.
        end_line: 1-indexed last line (inclusive). If omitted, reads
            ``min(max_lines, _READ_MAX_LINES)`` lines from ``start_line``.
        max_lines: Cap when ``end_line`` is omitted (1..2000). Default 500.

    Returns:
        ``{status, repo_name, path, total_lines, start, end, lines:
        [{n, text, truncated?}], truncated_range, eof}``. Long individual
        lines are truncated to 4096 chars and marked with ``truncated: true``.
        Refuses binary files (NUL byte in the first 8KB).
    """
    try:
        repo_dir = _validate_repo_name(repo_name)
        if not repo_dir.exists():
            return {
                "status": "error",
                "error": f"repo {repo_name!r} not synced; call repo_sync first",
            }
        target = _validate_subpath(repo_dir, path)
    except ValueError as e:
        return {"status": "error", "error": str(e)}

    if not target.exists():
        return {"status": "error", "error": f"path {path!r} does not exist"}
    if not target.is_file():
        return {"status": "error", "error": f"path {path!r} is not a regular file"}
    if _looks_binary(target):
        return {"status": "error", "error": f"path {path!r} appears to be binary"}

    try:
        start_line = max(1, int(start_line))
    except (TypeError, ValueError):
        return {"status": "error", "error": "start_line must be an integer ≥ 1"}
    max_lines = max(1, min(_READ_MAX_LINES, int(max_lines)))

    if end_line is None:
        end_line_eff = start_line + max_lines - 1
    else:
        try:
            end_line_eff = max(start_line, int(end_line))
        except (TypeError, ValueError):
            return {
                "status": "error",
                "error": "end_line must be an integer ≥ start_line",
            }
        # Even when end_line is given, refuse to ship more than the absolute cap.
        end_line_eff = min(end_line_eff, start_line + _READ_MAX_LINES - 1)

    lines_out: List[Dict[str, Any]] = []
    total_lines = 0
    eof = False
    try:
        with target.open("r", encoding="utf-8", errors="replace") as fh:
            for n, raw in enumerate(fh, start=1):
                total_lines = n
                if n < start_line:
                    continue
                if n > end_line_eff:
                    # Keep counting so total_lines is accurate, but stop collecting.
                    continue
                text = raw.rstrip("\n")
                if len(text) > _READ_LINE_TRUNC:
                    lines_out.append(
                        {"n": n, "text": text[:_READ_LINE_TRUNC], "truncated": True}
                    )
                else:
                    lines_out.append({"n": n, "text": text})
            eof = total_lines <= end_line_eff
    except OSError as e:
        return {"status": "error", "error": f"read failed: {e}"}

    return {
        "status": "success",
        "repo_name": repo_name,
        "path": str(target.relative_to(repo_dir)),
        "total_lines": total_lines,
        "start": start_line,
        "end": min(end_line_eff, total_lines),
        "lines": lines_out,
        "truncated_range": (end_line_eff - start_line + 1) >= _READ_MAX_LINES
        and not eof,
        "eof": eof,
    }


repo_sync_tool = FunctionTool(repo_sync)
repo_search_tool = FunctionTool(repo_search)
repo_map_tool = FunctionTool(repo_map)
repo_references_tool = FunctionTool(repo_references)
repo_read_tool = FunctionTool(repo_read)

REPO_EXPLORATION_TOOLS: List[Any] = [
    repo_sync_tool,
    repo_search_tool,
    repo_map_tool,
    repo_references_tool,
    repo_read_tool,
]
