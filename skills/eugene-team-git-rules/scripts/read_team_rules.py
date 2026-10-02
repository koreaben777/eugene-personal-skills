#!/usr/bin/env python3
"""Read team rules from a remote default branch without changing a worktree."""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

PROJECT_ROOT = Path(os.environ.get("EUGENE_GROUP_ROOT") or Path.home() / "Documents" / "Eugene_Group")
RULE_PATHS = (
    "AGENTS.md",
    "CLAUDE.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    ".github/PULL_REQUEST_TEMPLATE.md",
)
REFERENCE_RE = re.compile(r"^@([^\s]+\.md)$")
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
MAX_REFERENCE_DEPTH = 16


class GhUnavailable(RuntimeError):
    """The gh executable is unavailable or cannot authenticate."""


class RuleReadError(RuntimeError):
    """A safe, concise expected failure while inspecting rule files."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


class ArgumentFailure(RuntimeError):
    """An expected command-line usage failure."""


class JsonArgumentParser(argparse.ArgumentParser):
    """Avoid argparse's non-JSON stdout/stderr usage output."""

    def error(self, message: str) -> None:
        raise ArgumentFailure(message)


def has_control(value: str) -> bool:
    return any(ord(char) < 32 or ord(char) == 127 for char in value)


def valid_owner_repo(owner: str, repo: str) -> bool:
    return bool(NAME_RE.fullmatch(owner) and NAME_RE.fullmatch(repo) and repo != ".git")


def parse_github_remote(url: str) -> dict[str, str] | None:
    """Parse one strict GitHub remote URL; reject untrusted URL components."""
    if not url or has_control(url) or any(char.isspace() for char in url):
        return None
    owner: str
    repo: str
    scp = re.fullmatch(r"(?:(?P<user>[^@/:]+)@)?github\.com:(?P<owner>[^/]+)/(?P<repo>[^/]+)", url)
    if scp:
        owner, repo = scp.group("owner"), scp.group("repo")
    else:
        try:
            parsed = urlsplit(url)
            hostname = parsed.hostname
        except ValueError:
            return None
        if (
            parsed.scheme not in {"https", "http", "ssh"}
            or hostname != "github.com"
            or parsed.query
            or parsed.fragment
        ):
            return None
        parts = parsed.path.split("/")
        if len(parts) != 3 or not parts[1] or not parts[2]:
            return None
        owner, repo = parts[1], parts[2]
    repo = repo.removesuffix(".git")
    if not valid_owner_repo(owner, repo):
        return None
    return {"owner": owner.lower(), "repo": repo}


def parse_github_target(target: str) -> dict[str, str] | None:
    """Parse only the documented OWNER/REPO shorthand or strict GitHub URL."""
    if not target or has_control(target) or any(char.isspace() for char in target):
        return None
    if "://" not in target and "@github.com:" not in target and not target.startswith("github.com:"):
        parts = target.split("/")
        if len(parts) != 2 or not valid_owner_repo(parts[0], parts[1]):
            return None
        return {"owner": parts[0].lower(), "repo": parts[1]}
    return parse_github_remote(target)


def redact_remote(url: str) -> str:
    """Render only non-secret transport/host/path identity for diagnostics."""
    if has_control(url):
        return "<invalid remote>"
    scp = re.fullmatch(r"(?:(?P<user>[^@/:]+)@)?(?P<host>github\.com):(?P<path>.+)", url)
    if scp:
        user = scp.group("user")
        prefix = "git@" if user == "git" else ""
        return f"{prefix}{scp.group('host')}:{scp.group('path')}"
    try:
        parsed = urlsplit(url)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        return "<invalid remote>"
    if not parsed.scheme or not hostname:
        return "<invalid remote>"
    host = hostname if port is None else f"{hostname}:{port}"
    if parsed.scheme == "ssh" and parsed.username == "git":
        host = f"git@{host}"
    return urlunsplit((parsed.scheme, host, parsed.path, "", ""))


def classify_scope(*, work_path: Path, owner: str) -> str:
    """Classify canonical GitHub owner identity and the permitted project location."""
    canonical_owner = owner.lower()
    if canonical_owner == "koreaben777":
        return "personal"
    try:
        work_path.resolve().relative_to(PROJECT_ROOT)
    except ValueError:
        return "out_of_scope"
    return "team" if canonical_owner == "eugene-aicoe" else "out_of_scope"


def run_git(repo: Path, *args: str) -> str:
    """Run a Git read command and return stripped stdout."""
    try:
        result = subprocess.run(
            ("git", "-C", str(repo), *args), text=True, capture_output=True, check=False
        )
    except OSError as error:
        raise RuleReadError("git_unavailable", "Git executable is unavailable") from error
    except UnicodeDecodeError as error:
        raise RuleReadError("decode_error", "Git output was not valid UTF-8") from error
    if result.returncode:
        raise RuleReadError("git_error", result.stderr.strip() or "Git command failed")
    return result.stdout.strip()


def find_repo_root(path: Path) -> Path:
    target = path.resolve()
    if target.is_file():
        target = target.parent
    try:
        return Path(run_git(target, "rev-parse", "--show-toplevel"))
    except RuleReadError as error:
        raise RuleReadError("repository_not_found", "Repository path is not a worktree") from error


def choose_remote(repo: Path, requested: str | None) -> tuple[str, str]:
    """Select an explicit remote, otherwise the sole team or sole configured remote."""
    remotes = run_git(repo, "remote").splitlines()
    if requested is not None:
        if requested not in remotes:
            raise RuleReadError("remote_not_found", "Requested remote is unavailable")
        return requested, run_git(repo, "remote", "get-url", requested)
    if not remotes:
        raise RuleReadError("remote_not_found", "No configured remote is available")
    configured = [(name, run_git(repo, "remote", "get-url", name)) for name in remotes]
    team = []
    for name, url in configured:
        parsed = parse_github_remote(url)
        if parsed is not None and classify_scope(work_path=repo, owner=parsed["owner"]) == "team":
            team.append((name, url))
    if len(team) == 1:
        return team[0]
    if len(team) > 1:
        raise RuleReadError("ambiguous_remote", "Multiple team remotes require explicit --remote")
    if len(configured) == 1:
        return configured[0]
    raise RuleReadError("ambiguous_remote", "Multiple remotes require explicit --remote")


def remote_default_branch(repo: Path, remote: str) -> str:
    try:
        symbolic = run_git(repo, "ls-remote", "--symref", remote, "HEAD")
    except RuleReadError as error:
        raise RuleReadError("default_branch_unavailable", "Cannot determine remote default branch") from error
    for line in symbolic.splitlines():
        if line.startswith("ref: ") and line.endswith("\tHEAD"):
            ref = line.split()[1]
            if ref.startswith("refs/heads/"):
                return ref.removeprefix("refs/heads/")
    raise RuleReadError("default_branch_unavailable", "Remote did not advertise a default branch")


def run_git_cleanup(repo: Path, temp_ref: str) -> None:
    try:
        result = subprocess.run(
            ("git", "-C", str(repo), "update-ref", "-d", temp_ref),
            text=True, capture_output=True, check=False,
        )
    except (OSError, UnicodeDecodeError) as error:
        raise RuleReadError(
            "cleanup_failed", "Temporary rule ref cleanup could not be verified"
        ) from error
    if result.returncode:
        raise RuleReadError("cleanup_failed", "Temporary rule ref cleanup could not be verified")


def fetch_rules_commit(repo: Path, remote: str, branch: str) -> str:
    temp_ref = f"refs/eugene-team-rules/{uuid.uuid4().hex}"
    primary: RuleReadError | None = None
    commit: str | None = None
    try:
        run_git(repo, "fetch", "--no-tags", "--no-write-fetch-head", remote, f"{branch}:{temp_ref}")
        commit = run_git(repo, "rev-parse", temp_ref)
    except RuleReadError as error:
        primary = RuleReadError("fetch_failed", "Cannot fetch remote rule branch")
        primary.__cause__ = error
    try:
        run_git_cleanup(repo, temp_ref)
    except RuleReadError as cleanup_error:
        if primary is not None:
            raise RuleReadError(
                primary.code,
                f"{primary.message}; temporary rule ref cleanup could not be verified",
            ) from primary
        raise cleanup_error
    if primary is not None:
        raise primary
    if commit is None:  # Defensive: all expected paths above either set it or raise.
        raise RuleReadError("fetch_failed", "Cannot fetch remote rule branch")
    return commit


def show_file(repo: Path, commit: str, path: str) -> str | None:
    try:
        result = subprocess.run(
            ("git", "-C", str(repo), "show", f"{commit}:{path}"),
            text=True, capture_output=True, check=False,
        )
    except OSError as error:
        raise RuleReadError("git_unavailable", "Git executable is unavailable") from error
    except UnicodeDecodeError as error:
        raise RuleReadError("decode_error", "Rule file was not valid UTF-8") from error
    return result.stdout if result.returncode == 0 else None


def list_directory(repo: Path, commit: str, path: str) -> list[str]:
    try:
        result = subprocess.run(
            ("git", "-C", str(repo), "ls-tree", "-r", "--name-only", commit, "--", path),
            text=True, capture_output=True, check=False,
        )
    except OSError as error:
        raise RuleReadError("git_unavailable", "Git executable is unavailable") from error
    except UnicodeDecodeError as error:
        raise RuleReadError("decode_error", "Git tree output was not valid UTF-8") from error
    return result.stdout.splitlines() if result.returncode == 0 else []


def normalize_reference(source: str, target: str) -> str:
    candidate = PurePosixPath(source).parent / PurePosixPath(target)
    if PurePosixPath(target).is_absolute() or ".." in candidate.parts:
        raise RuleReadError("invalid_reference", "Rule reference escapes the repository")
    normalized = candidate.as_posix()
    if not normalized.endswith(".md"):
        raise RuleReadError("invalid_reference", "Rule reference must name a Markdown file")
    return normalized


def read_rule_files(repo: Path, commit: str, operation: str | None = None) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    paths = list(RULE_PATHS)
    paths.extend(list_directory(repo, commit, ".github/PULL_REQUEST_TEMPLATE"))
    if operation == "issue":
        paths.extend(list_directory(repo, commit, ".github/ISSUE_TEMPLATE"))
    files: list[dict[str, str]] = []
    references: list[dict[str, str]] = []
    seen: set[str] = set()
    active: set[str] = set()

    def visit(path: str, depth: int, *, required: bool = False) -> None:
        if depth > MAX_REFERENCE_DEPTH:
            raise RuleReadError("reference_depth", "Rule reference depth exceeds the limit")
        if path in active:
            raise RuleReadError("reference_cycle", "Rule references form a cycle")
        if path in seen:
            return
        content = show_file(repo, commit, path)
        if content is None:
            if required:
                raise RuleReadError(
                    "required_reference_missing", "Required internal rule reference is unavailable"
                )
            return
        active.add(path)
        seen.add(path)
        files.append({"path": path, "content": content})
        for line in content.splitlines():
            match = REFERENCE_RE.fullmatch(line)
            if match:
                target = normalize_reference(path, match.group(1))
                references.append({"from": path, "to": target})
                visit(target, depth + 1, required=True)
        active.remove(path)

    for candidate in paths:
        visit(candidate, 0)
    if not files:
        raise RuleReadError("rules_not_found", "No remote rule files were found")
    return files, references


def _inspect_local_team_repo(path: Path, remote: str | None = None, operation: str | None = None) -> dict[str, Any]:
    """Scoped-internal local retrieval; no worktree, index, ref, or FETCH_HEAD persistence."""
    repo = find_repo_root(path)
    remote_name, remote_url = choose_remote(repo, remote)
    branch = remote_default_branch(repo, remote_name)
    commit = fetch_rules_commit(repo, remote_name, branch)
    files, references = read_rule_files(repo, commit, operation)
    parsed = parse_github_remote(remote_url)
    return {
        "owner": parsed["owner"] if parsed else None,
        "repo": parsed["repo"] if parsed else None,
        "default_branch": branch,
        "rules_commit": commit,
        "files": files,
        "references": references,
    }


def inspect_local_repo(path: Path, remote: str | None = None, operation: str | None = None) -> dict[str, Any]:
    """Public scope-enforcing local inspection API; never reads personal/out-of-scope content."""
    repo = find_repo_root(path)
    _, remote_url = choose_remote(repo, remote)
    parsed = parse_github_remote(remote_url)
    if parsed is None:
        return {"scope": "out_of_scope", "remote": redact_remote(remote_url)}
    scope = classify_scope(work_path=repo, owner=parsed["owner"])
    if scope != "team":
        return {"scope": scope, **parsed}
    return {"scope": "team", **_inspect_local_team_repo(repo, remote, operation)}


def run_gh_api(endpoint: str) -> Any:
    """Use gh only for read-only API calls; unavailable/unauthorized callers may fall back."""
    try:
        result = subprocess.run(("gh", "api", endpoint), text=True, capture_output=True, check=False)
    except FileNotFoundError as error:
        raise GhUnavailable("missing") from error
    except OSError as error:
        raise RuleReadError("gh_error", "GitHub CLI cannot run") from error
    if result.returncode:
        detail = result.stderr.lower()
        if any(marker in detail for marker in ("not logged", "authentication", "unauthorized", "http 401", "http 403")):
            raise GhUnavailable("unauthorized")
        if re.search(r"\b404\b", detail):
            raise RuleReadError("gh_not_found", "GitHub API resource was not found")
        raise RuleReadError("gh_error", "GitHub API lookup failed")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuleReadError("gh_error", "GitHub API returned invalid JSON") from error


def gh_contents_endpoint(owner: str, repo: str, ref: str, path: str) -> str:
    return (
        f"repos/{quote(owner, safe='')}/{quote(repo, safe='')}/contents/"
        f"{quote(path, safe='/')}?ref={quote(ref, safe='')}"
    )


def gh_file(owner: str, repo: str, ref: str, path: str) -> tuple[str, str] | None:
    try:
        data = run_gh_api(gh_contents_endpoint(owner, repo, ref, path))
    except RuleReadError as error:
        if error.code == "gh_not_found":
            return None
        raise
    if not isinstance(data, dict) or data.get("type") != "file" or data.get("encoding") != "base64":
        raise RuleReadError("gh_error", "GitHub API returned an unexpected file response")
    try:
        encoded = data["content"]
        if not isinstance(encoded, str):
            raise ValueError("content is not text")
        compact = re.sub(r"[ \t\r\n\f\v]", "", encoded)
        content = base64.b64decode(compact, validate=True).decode("utf-8")
    except (KeyError, ValueError, UnicodeDecodeError) as error:
        raise RuleReadError("gh_error", "GitHub API returned invalid file content") from error
    sha = data.get("sha")
    if not isinstance(sha, str):
        raise RuleReadError("gh_error", "GitHub API did not provide file identity")
    return content, sha


def gh_directory(owner: str, repo: str, ref: str, path: str) -> list[str]:
    try:
        data = run_gh_api(gh_contents_endpoint(owner, repo, ref, path))
    except RuleReadError as error:
        if error.code == "gh_not_found":
            return []
        raise
    if not isinstance(data, list):
        raise RuleReadError("gh_error", "GitHub API returned an unexpected directory response")
    paths: list[str] = []
    for item in data:
        if not isinstance(item, dict) or item.get("type") != "file" or not isinstance(item.get("path"), str):
            raise RuleReadError("gh_error", "GitHub API returned an invalid directory entry")
        paths.append(item["path"])
    return paths


def inspect_target_via_gh(info: dict[str, str], operation: str | None = None) -> dict[str, Any]:
    owner, repo = info["owner"], info["repo"]
    metadata = run_gh_api(f"repos/{owner}/{repo}")
    if not isinstance(metadata, dict) or not isinstance(metadata.get("default_branch"), str):
        raise RuleReadError("gh_error", "GitHub API did not provide default branch")
    branch = metadata["default_branch"]
    head = run_gh_api(
        f"repos/{quote(owner, safe='')}/{quote(repo, safe='')}/commits/{quote(branch, safe='')}"
    )
    if not isinstance(head, dict) or not isinstance(head.get("sha"), str):
        raise RuleReadError("gh_error", "GitHub API did not provide default-branch head commit")
    rules_commit = head["sha"]
    candidates = list(RULE_PATHS)
    candidates.extend(gh_directory(owner, repo, rules_commit, ".github/PULL_REQUEST_TEMPLATE"))
    if operation == "issue":
        candidates.extend(gh_directory(owner, repo, rules_commit, ".github/ISSUE_TEMPLATE"))
    files: list[dict[str, str]] = []
    references: list[dict[str, str]] = []
    seen: set[str] = set()
    active: set[str] = set()
    def visit(path: str, depth: int, *, required: bool = False) -> None:
        if depth > MAX_REFERENCE_DEPTH:
            raise RuleReadError("reference_depth", "Rule reference depth exceeds the limit")
        if path in active:
            raise RuleReadError("reference_cycle", "Rule references form a cycle")
        if path in seen:
            return
        entry = gh_file(owner, repo, rules_commit, path)
        if entry is None:
            if required:
                raise RuleReadError(
                    "required_reference_missing", "Required internal rule reference is unavailable"
                )
            return
        content, _ = entry
        active.add(path)
        seen.add(path)
        files.append({"path": path, "content": content})
        for line in content.splitlines():
            match = REFERENCE_RE.fullmatch(line)
            if match:
                target = normalize_reference(path, match.group(1))
                references.append({"from": path, "to": target})
                visit(target, depth + 1, required=True)
        active.remove(path)

    for candidate in candidates:
        visit(candidate, 0)
    if not files:
        raise RuleReadError("rules_not_found", "No remote rule files were found")
    return {"owner": owner, "repo": repo, "default_branch": branch, "rules_commit": rules_commit, "files": files, "references": references}


def inspect_target_git_fallback(info: dict[str, str], operation: str | None = None) -> dict[str, Any]:
    """Disposable fallback when gh is missing or unauthorized; never uses a user clone path."""
    clone_url = f"https://github.com/{info['owner']}/{info['repo']}.git"
    with tempfile.TemporaryDirectory(prefix="eugene-team-rules-") as temp:
        repo = Path(temp)
        try:
            initialized = subprocess.run(("git", "init", "--quiet", str(repo)), text=True, capture_output=True, check=False)
            configured = subprocess.run(("git", "-C", str(repo), "remote", "add", "origin", clone_url), text=True, capture_output=True, check=False)
        except OSError as error:
            raise RuleReadError("target_unavailable", "Cannot initialize disposable inspection") from error
        if initialized.returncode or configured.returncode:
            raise RuleReadError("target_unavailable", "Cannot initialize disposable inspection")
        branch = remote_default_branch(repo, "origin")
        commit = fetch_rules_commit(repo, "origin", branch)
        files, references = read_rule_files(repo, commit, operation)
    return {"owner": info["owner"], "repo": info["repo"], "default_branch": branch, "rules_commit": commit, "files": files, "references": references}


def inspect_target(target: str, work_path: Path = PROJECT_ROOT, operation: str | None = None) -> dict[str, Any]:
    """Public scope-enforcing target API; gh first, fallback only if gh unavailable/unauthorized."""
    info = parse_github_target(target)
    if info is None:
        raise RuleReadError("invalid_target", "Target is not a strict GitHub owner/repository")
    scope = classify_scope(work_path=work_path, owner=info["owner"])
    if scope != "team":
        return {"scope": scope, **info}
    try:
        return inspect_target_via_gh(info, operation)
    except GhUnavailable:
        return inspect_target_git_fallback(info, operation)


def error_payload(scope: str, error: RuleReadError | ArgumentFailure) -> dict[str, Any]:
    code = error.code if isinstance(error, RuleReadError) else "invalid_arguments"
    message = error.message if isinstance(error, RuleReadError) else "Invalid command arguments"
    return {"scope": scope, "error": {"code": code, "message": message}, "write_allowed": False}


def main(argv: list[str] | None = None) -> int:
    parser = JsonArgumentParser(add_help=False)
    parser.add_argument("--repo-path", required=True)
    parser.add_argument("--remote")
    parser.add_argument("--target")
    parser.add_argument("--operation", choices=("issue",))
    scope = "unknown"
    try:
        args = parser.parse_args(argv)
        work_path = Path(args.repo_path)
        if args.target:
            info = parse_github_target(args.target)
            if info is None:
                raise RuleReadError("invalid_target", "Target is not a strict GitHub owner/repository")
            scope = classify_scope(work_path=work_path, owner=info["owner"])
            if scope != "team":
                print(json.dumps({"scope": scope, **info}, ensure_ascii=False))
                return 0
            inspected = inspect_target(args.target, work_path=work_path, operation=args.operation)
        else:
            repo = find_repo_root(work_path)
            _, remote_url = choose_remote(repo, args.remote)
            info = parse_github_remote(remote_url)
            if info is None:
                print(json.dumps({"scope": "out_of_scope", "remote": redact_remote(remote_url)}, ensure_ascii=False))
                return 0
            scope = classify_scope(work_path=repo, owner=info["owner"])
            if scope != "team":
                print(json.dumps({"scope": scope, **info}, ensure_ascii=False))
                return 0
            inspected = _inspect_local_team_repo(repo, args.remote, operation=args.operation)
        payload = {
            "scope": "team", "owner": info["owner"], "repo": info["repo"],
            "default_branch": inspected["default_branch"], "rules_commit": inspected["rules_commit"],
            "checked_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "files": inspected["files"], "references": inspected["references"],
        }
        print(json.dumps(payload, ensure_ascii=False))
        return 0
    except UnicodeDecodeError as error:
        error = RuleReadError("decode_error", "Repository data was not valid UTF-8")
        print(json.dumps(error_payload(scope, error), ensure_ascii=False))
        print(error.message, file=sys.stderr)
        return 1
    except (RuleReadError, ArgumentFailure) as error:
        print(json.dumps(error_payload(scope, error), ensure_ascii=False))
        print(error_payload(scope, error)["error"]["message"], file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
