"""Tests for the read-only team remote-rule helper."""
from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.read_team_rules import (
    GhUnavailable,
    RuleReadError,
    classify_scope,
    choose_remote,
    fetch_rules_commit,
    gh_directory,
    gh_file,
    inspect_target_via_gh,
    run_gh_api,
    _inspect_local_team_repo,
    inspect_local_repo,
    inspect_target,
    main,
    parse_github_remote,
    parse_github_target,
    redact_remote,
)


SKILL_ROOT = Path(__file__).resolve().parents[1]
HELPER = SKILL_ROOT / "scripts" / "read_team_rules.py"
PROJECT_ROOT = Path(os.environ.get("EUGENE_GROUP_ROOT") or Path.home() / "Documents" / "Eugene_Group")


class RemoteParsingTests(unittest.TestCase):
    def test_supported_github_forms_are_normalized_and_redacted(self) -> None:
        cases = {
            "https://github.com/eugene-aicoe/project.git": "https://github.com/eugene-aicoe/project.git",
            "git@github.com:eugene-aicoe/project.git": "git@github.com:eugene-aicoe/project.git",
            "ssh://git@github.com/eugene-aicoe/project.git": "ssh://git@github.com/eugene-aicoe/project.git",
            "https://token@github.com/eugene-aicoe/project.git": "https://github.com/eugene-aicoe/project.git",
        }
        for url, display_url in cases.items():
            with self.subTest(url=url):
                parsed = parse_github_remote(url)
                self.assertEqual(parsed, {"owner": "eugene-aicoe", "repo": "project"})
                self.assertEqual(redact_remote(url), display_url)
                self.assertEqual(classify_scope(work_path=PROJECT_ROOT, owner=parsed["owner"]), "team")

    def test_exact_owner_matching_and_invalid_remotes(self) -> None:
        for url, owner, scope in (
            ("https://github.com/koreaben777/project.git", "koreaben777", "personal"),
            ("https://github.com/eugene-aicoe-fake/project.git", "eugene-aicoe-fake", "out_of_scope"),
        ):
            with self.subTest(url=url):
                parsed = parse_github_remote(url)
                self.assertEqual(parsed, {"owner": owner, "repo": "project"})
                self.assertEqual(classify_scope(work_path=PROJECT_ROOT, owner=parsed["owner"]), scope)
        for url in (
            "https://gitlab.com/eugene-aicoe/project.git",
            "https://github.com/eugene-aicoe",
            "not a remote",
            "https://github.com/eugene-aicoe/project/extra",
        ):
            with self.subTest(url=url):
                self.assertIsNone(parse_github_remote(url))

    def test_team_scope_requires_project_root_ancestry(self) -> None:
        self.assertEqual(
            classify_scope(work_path=Path("/tmp/not-eugene"), owner="eugene-aicoe"),
            "out_of_scope",
        )

    def test_github_owner_is_canonicalized_case_insensitively_without_accepting_lookalikes(self) -> None:
        parsed = parse_github_remote("https://github.com/Eugene-AICoE/project.git")
        self.assertEqual(parsed, {"owner": "eugene-aicoe", "repo": "project"})
        self.assertEqual(classify_scope(work_path=PROJECT_ROOT, owner="EUGENE-AICOE"), "team")
        self.assertEqual(
            classify_scope(work_path=PROJECT_ROOT, owner="Eugene-AICoE-fake"),
            "out_of_scope",
        )


class RemoteSelectionTests(unittest.TestCase):
    @staticmethod
    def remote_side_effect(_repo: Path, *args: str) -> str:
        if args == ("remote",):
            return "origin\nupstream"
        if args == ("remote", "get-url", "origin"):
            return "https://github.com/koreaben777/project.git"
        if args == ("remote", "get-url", "upstream"):
            return "https://github.com/eugene-aicoe/project.git"
        raise AssertionError(args)

    def test_explicit_remote_wins_even_when_another_remote_is_team(self) -> None:
        with mock.patch("scripts.read_team_rules.run_git", side_effect=self.remote_side_effect):
            self.assertEqual(
                choose_remote(PROJECT_ROOT, "origin"),
                ("origin", "https://github.com/koreaben777/project.git"),
            )

    def test_fork_origin_personal_and_upstream_team_selects_team(self) -> None:
        with mock.patch("scripts.read_team_rules.run_git", side_effect=self.remote_side_effect):
            self.assertEqual(
                choose_remote(PROJECT_ROOT, None),
                ("upstream", "https://github.com/eugene-aicoe/project.git"),
            )

    def test_single_non_team_remote_is_selected_for_scope_classification(self) -> None:
        def only_remote(_repo: Path, *args: str) -> str:
            if args == ("remote",):
                return "mirror"
            if args == ("remote", "get-url", "mirror"):
                return "https://github.com/koreaben777/project.git"
            raise AssertionError(args)

        with mock.patch("scripts.read_team_rules.run_git", side_effect=only_remote):
            self.assertEqual(
                choose_remote(PROJECT_ROOT, None),
                ("mirror", "https://github.com/koreaben777/project.git"),
            )

    def test_multiple_team_remotes_are_structurally_ambiguous(self) -> None:
        def team_remotes(_repo: Path, *args: str) -> str:
            if args == ("remote",):
                return "origin\nupstream"
            if args[:2] == ("remote", "get-url"):
                return f"https://github.com/eugene-aicoe/{args[2]}.git"
            raise AssertionError(args)

        with mock.patch("scripts.read_team_rules.run_git", side_effect=team_remotes):
            with self.assertRaises(RuleReadError) as captured:
                choose_remote(PROJECT_ROOT, None)
        self.assertEqual(captured.exception.code, "ambiguous_remote")

    def test_multiple_non_team_remotes_are_structurally_ambiguous(self) -> None:
        def personal_remotes(_repo: Path, *args: str) -> str:
            if args == ("remote",):
                return "origin\nmirror"
            if args[:2] == ("remote", "get-url"):
                return f"https://github.com/koreaben777/{args[2]}.git"
            raise AssertionError(args)

        with mock.patch("scripts.read_team_rules.run_git", side_effect=personal_remotes):
            with self.assertRaises(RuleReadError) as captured:
                choose_remote(PROJECT_ROOT, None)
        self.assertEqual(captured.exception.code, "ambiguous_remote")


class TargetSyntaxTests(unittest.TestCase):
    """B1: documented target forms must parse before any retrieval subprocess."""

    def test_strict_short_and_url_targets_normalize_identically(self) -> None:
        self.assertEqual(
            parse_github_target("eugene-aicoe/project"),
            {"owner": "eugene-aicoe", "repo": "project"},
        )
        self.assertEqual(
            parse_github_target("https://github.com/eugene-aicoe/project.git"),
            {"owner": "eugene-aicoe", "repo": "project"},
        )

    def test_target_rejects_extra_segments_queries_fragments_controls_and_bad_names(self) -> None:
        for target in (
            "eugene-aicoe/project/extra",
            "eugene-aicoe/project?token=secret",
            "eugene-aicoe/project#secret",
            "https://github.com/eugene-aicoe/project?token=secret",
            "https://github.com/eugene-aicoe/project#secret",
            "https://github.com/[",
            "eugene-aicoe/proj\x00ect",
            "eugene-aicoe/proj\nect",
            "eugene aicoe/project",
            "eugene-aicoe/.git",
        ):
            with self.subTest(target=repr(target)):
                self.assertIsNone(parse_github_target(target))

    def test_cli_short_and_url_targets_reach_the_same_team_target_path(self) -> None:
        fake = {
            "owner": "eugene-aicoe",
            "repo": "project",
            "default_branch": "trunk",
            "rules_commit": "abc123",
            "files": [{"path": "AGENTS.md", "content": "rules\n"}],
            "references": [],
        }
        for target in ("eugene-aicoe/project", "https://github.com/eugene-aicoe/project.git"):
            with self.subTest(target=target), mock.patch(
                "scripts.read_team_rules.inspect_target", return_value=fake
            ) as inspect:
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    self.assertEqual(main(["--repo-path", str(PROJECT_ROOT), "--target", target]), 0)
                self.assertEqual(json.loads(stdout.getvalue())["scope"], "team")
                inspect.assert_called_once()


class InputFailureTests(unittest.TestCase):
    """B2: expected invocation/input failures are JSON, programmer failures are not masked."""

    def invoke_main(self, argv: list[str]) -> tuple[int, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            status = main(argv)
        return status, stdout.getvalue(), stderr.getvalue()

    def assert_json_failure(self, argv: list[str]) -> None:
        status, stdout, _ = self.invoke_main(argv)
        self.assertNotEqual(status, 0)
        payload = json.loads(stdout)
        self.assertIn(payload["scope"], {"unknown", "team"})
        self.assertFalse(payload["write_allowed"])
        self.assertIn("code", payload["error"])

    def test_missing_required_argument_is_json_failure(self) -> None:
        self.assert_json_failure(["--target", "eugene-aicoe/project"])

    def test_controls_and_malformed_short_targets_are_json_failure_before_subprocess(self) -> None:
        for target in ("eugene-aicoe/proj\x00ect", "eugene-aicoe/project/extra"):
            with self.subTest(target=repr(target)), mock.patch(
                "scripts.read_team_rules.subprocess.run"
            ) as run:
                self.assert_json_failure(["--repo-path", str(PROJECT_ROOT), "--target", target])
                run.assert_not_called()

    def test_programmer_fault_is_not_converted_to_json_operational_failure(self) -> None:
        with mock.patch("scripts.read_team_rules.inspect_target", side_effect=AssertionError("programmer bug")):
            with self.assertRaisesRegex(AssertionError, "programmer bug"):
                main(["--repo-path", str(PROJECT_ROOT), "--target", "eugene-aicoe/project"])

    def test_operation_issue_is_passed_and_unknown_choice_is_json_failure(self) -> None:
        fake = {
            "scope": "team", "owner": "eugene-aicoe", "repo": "project",
            "default_branch": "trunk", "rules_commit": "abc123", "files": [], "references": [],
        }
        with mock.patch("scripts.read_team_rules.inspect_target", return_value=fake) as inspect:
            status, stdout, _ = self.invoke_main([
                "--repo-path", str(PROJECT_ROOT), "--target", "eugene-aicoe/project",
                "--operation", "issue",
            ])
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(stdout)["scope"], "team")
        inspect.assert_called_once_with(
            "eugene-aicoe/project", work_path=PROJECT_ROOT, operation="issue"
        )
        self.assert_json_failure([
            "--repo-path", str(PROJECT_ROOT), "--target", "eugene-aicoe/project",
            "--operation", "invalid",
        ])

    def test_unicode_decode_failure_is_structured_json(self) -> None:
        with mock.patch(
            "scripts.read_team_rules.find_repo_root",
            side_effect=UnicodeDecodeError("utf-8", b"x", 0, 1, "invalid"),
        ):
            status, stdout, _ = self.invoke_main(["--repo-path", str(PROJECT_ROOT)])
        self.assertNotEqual(status, 0)
        payload = json.loads(stdout)
        self.assertEqual(payload["error"]["code"], "decode_error")
        self.assertFalse(payload["write_allowed"])


class RedactionSafetyTests(unittest.TestCase):
    """N1: stdout-safe remote rendering never retains credential-like components."""

    def test_scp_userinfo_and_url_query_fragment_are_removed(self) -> None:
        self.assertEqual(
            redact_remote("secret-user@github.com:eugene-aicoe/project.git"),
            "github.com:eugene-aicoe/project.git",
        )
        self.assertEqual(
            redact_remote("git@github.com:eugene-aicoe/project.git"),
            "git@github.com:eugene-aicoe/project.git",
        )
        self.assertEqual(
            redact_remote("https://token@github.com/eugene-aicoe/project.git?token=query#fragment"),
            "https://github.com/eugene-aicoe/project.git",
        )


class PublicScopeTests(unittest.TestCase):
    """N2: direct public inspection entry points gate content retrieval by scope."""

    def test_personal_target_returns_metadata_without_running_retrieval(self) -> None:
        with mock.patch("scripts.read_team_rules.run_gh_api") as gh, mock.patch(
            "scripts.read_team_rules.inspect_target_git_fallback"
        ) as fallback:
            result = inspect_target("koreaben777/personal", work_path=PROJECT_ROOT)
        self.assertEqual(result, {"scope": "personal", "owner": "koreaben777", "repo": "personal"})
        gh.assert_not_called()
        fallback.assert_not_called()

    def test_out_of_scope_local_remote_does_not_read_rule_content(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "personal"
            subprocess.run(("git", "init", str(repo)), check=True, capture_output=True)
            subprocess.run(
                ("git", "-C", str(repo), "remote", "add", "origin", "https://github.com/koreaben777/demo.git"),
                check=True,
                capture_output=True,
            )
            with mock.patch("scripts.read_team_rules.remote_default_branch") as branch:
                result = inspect_local_repo(repo)
        self.assertEqual(result, {"scope": "personal", "owner": "koreaben777", "repo": "demo"})
        branch.assert_not_called()

    def test_team_result_from_public_local_api_includes_scope(self) -> None:
        fake = {
            "owner": "eugene-aicoe", "repo": "project", "default_branch": "trunk",
            "rules_commit": "abc123", "files": [], "references": [],
        }
        with mock.patch("scripts.read_team_rules.find_repo_root", return_value=PROJECT_ROOT), mock.patch(
            "scripts.read_team_rules.choose_remote",
            return_value=("origin", "https://github.com/eugene-aicoe/project.git"),
        ), mock.patch("scripts.read_team_rules._inspect_local_team_repo", return_value=fake):
            result = inspect_local_repo(PROJECT_ROOT)
        self.assertEqual(result["scope"], "team")


class GhPreferredTests(unittest.TestCase):
    """N3: deterministic gh response handling and strictly limited fallback."""

    @staticmethod
    def gh_response(endpoint: str) -> object:
        commit = "a" * 40
        if endpoint == "repos/eugene-aicoe/project":
            return {"default_branch": "trunk"}
        if endpoint == "repos/eugene-aicoe/project/commits/trunk":
            return {"sha": commit}
        if endpoint == f"repos/eugene-aicoe/project/contents/AGENTS.md?ref={commit}":
            return {"type": "file", "content": "cnVsZXMK", "encoding": "base64", "sha": "b" * 40}
        if endpoint.endswith(f"?ref={commit}"):
            raise RuleReadError("gh_not_found", "Not found")
        raise AssertionError(f"unexpected gh endpoint: {endpoint}")

    def test_genuine_404_is_an_absent_candidate_but_other_api_errors_remain_errors(self) -> None:
        not_found = subprocess.CompletedProcess(("gh",), 1, "", "HTTP 404: Not Found")
        server_error = subprocess.CompletedProcess(("gh",), 1, "", "HTTP 500: Server Error")
        with mock.patch("scripts.read_team_rules.subprocess.run", return_value=not_found):
            self.assertIsNone(gh_file("eugene-aicoe", "project", "trunk", "CLAUDE.md"))
        with mock.patch("scripts.read_team_rules.subprocess.run", return_value=server_error):
            with self.assertRaisesRegex(RuleReadError, "gh_error") as captured:
                run_gh_api("repos/eugene-aicoe/project")
        self.assertEqual(captured.exception.code, "gh_error")

    def test_only_missing_or_unauthorized_gh_triggers_git_fallback(self) -> None:
        fallback_result = {
            "owner": "eugene-aicoe", "repo": "project", "default_branch": "trunk",
            "rules_commit": "fallback", "files": [], "references": [],
        }
        for error in (GhUnavailable("missing"), GhUnavailable("unauthorized")):
            with self.subTest(error=str(error)), mock.patch(
                "scripts.read_team_rules.inspect_target_via_gh", side_effect=error
            ), mock.patch(
                "scripts.read_team_rules.inspect_target_git_fallback", return_value=fallback_result
            ) as fallback:
                self.assertEqual(inspect_target("eugene-aicoe/project", work_path=PROJECT_ROOT), fallback_result)
                fallback.assert_called_once()
        for error in (
            RuleReadError("gh_not_found", "Not found"),
            RuleReadError("gh_error", "Server error"),
        ):
            with self.subTest(error=error.code), mock.patch(
                "scripts.read_team_rules.inspect_target_via_gh", side_effect=error
            ), mock.patch("scripts.read_team_rules.inspect_target_git_fallback") as fallback:
                with self.assertRaises(RuleReadError) as captured:
                    inspect_target("eugene-aicoe/project", work_path=PROJECT_ROOT)
                self.assertEqual(captured.exception.code, error.code)
                fallback.assert_not_called()

    def test_line_wrapped_base64_allows_only_ascii_formatting_whitespace(self) -> None:
        wrapped = {"type": "file", "content": "cnVs\nZXMK", "encoding": "base64", "sha": "b" * 40}
        with mock.patch("scripts.read_team_rules.run_gh_api", return_value=wrapped):
            self.assertEqual(gh_file("eugene-aicoe", "project", "trunk", "AGENTS.md"), ("rules\n", "b" * 40))
        invalid = {"type": "file", "content": "cnVs$\nZXMK", "encoding": "base64", "sha": "b" * 40}
        with mock.patch("scripts.read_team_rules.run_gh_api", return_value=invalid):
            with self.assertRaises(RuleReadError) as captured:
                gh_file("eugene-aicoe", "project", "trunk", "AGENTS.md")
        self.assertEqual(captured.exception.code, "gh_error")

    def test_gh_api_is_preferred_and_uses_default_branch_head_commit_not_blob_sha(self) -> None:
        with mock.patch(
            "scripts.read_team_rules.run_gh_api", side_effect=self.gh_response
        ) as gh, mock.patch("scripts.read_team_rules.inspect_target_git_fallback") as fallback:
            result = inspect_target("eugene-aicoe/project", work_path=PROJECT_ROOT)
        self.assertEqual(result["rules_commit"], "a" * 40)
        self.assertNotEqual(result["rules_commit"], "b" * 40)
        self.assertEqual(result["files"], [{"path": "AGENTS.md", "content": "rules\n"}])
        self.assertEqual(
            gh.call_args_list[1].args,
            ("repos/eugene-aicoe/project/commits/trunk",),
        )
        content_calls = [call.args[0] for call in gh.call_args_list if "/contents/" in call.args[0]]
        self.assertTrue(content_calls)
        self.assertTrue(all(call.endswith(f"?ref={'a' * 40}") for call in content_calls))
        fallback.assert_not_called()

    def test_branch_movement_cannot_mix_content_after_head_sha_capture(self) -> None:
        commit_a, commit_b = "a" * 40, "c" * 40
        observed: list[str] = []

        def moving_branch(endpoint: str) -> object:
            observed.append(endpoint)
            if endpoint == "repos/eugene-aicoe/project":
                return {"default_branch": "trunk"}
            if endpoint == "repos/eugene-aicoe/project/commits/trunk":
                return {"sha": commit_a}
            if endpoint == f"repos/eugene-aicoe/project/contents/AGENTS.md?ref={commit_a}":
                return {"type": "file", "content": "ZnJvbS1hCg==", "encoding": "base64", "sha": "b" * 40}
            if endpoint.endswith(f"?ref={commit_a}"):
                raise RuleReadError("gh_not_found", "Not found")
            if endpoint.endswith("?ref=trunk") or endpoint.endswith(f"?ref={commit_b}"):
                raise AssertionError("mutable branch/new head used for content")
            raise AssertionError(endpoint)

        with mock.patch("scripts.read_team_rules.run_gh_api", side_effect=moving_branch):
            result = inspect_target_via_gh({"owner": "eugene-aicoe", "repo": "project"})
        self.assertEqual(result["rules_commit"], commit_a)
        self.assertEqual(result["files"][0]["content"], "from-a\n")
        self.assertNotIn(f"?ref={commit_b}", "\n".join(observed))

    def test_default_branch_name_is_encoded_as_one_commit_path_component(self) -> None:
        commit = "a" * 40

        def response(endpoint: str) -> object:
            if endpoint == "repos/eugene-aicoe/project":
                return {"default_branch": "release/v1"}
            if endpoint == "repos/eugene-aicoe/project/commits/release%2Fv1":
                return {"sha": commit}
            if endpoint == f"repos/eugene-aicoe/project/contents/AGENTS.md?ref={commit}":
                return {"type": "file", "content": "cnVsZXMK", "encoding": "base64", "sha": "b" * 40}
            if endpoint.endswith(f"?ref={commit}"):
                raise RuleReadError("gh_not_found", "Not found")
            raise AssertionError(endpoint)

        with mock.patch("scripts.read_team_rules.run_gh_api", side_effect=response):
            result = inspect_target_via_gh({"owner": "eugene-aicoe", "repo": "project"})
        self.assertEqual(result["rules_commit"], commit)

    def test_gh_content_urls_encode_owner_repo_path_and_ref(self) -> None:
        response = {"type": "file", "content": "cnVsZXMK", "encoding": "base64", "sha": "b" * 40}
        with mock.patch("scripts.read_team_rules.run_gh_api", return_value=response) as gh:
            gh_file("owner name", "repo/name", "refs/heads/x y", "dir/a b#c.md")
        self.assertEqual(
            gh.call_args.args[0],
            "repos/owner%20name/repo%2Fname/contents/dir/a%20b%23c.md?ref=refs%2Fheads%2Fx%20y",
        )

    def test_unexpected_existing_file_and_directory_shapes_fail_closed(self) -> None:
        malformed_files = (
            [],
            {"type": "dir", "content": "", "encoding": "base64", "sha": "x"},
            {"type": "file", "content": "rules", "encoding": "utf-8", "sha": "x"},
        )
        for data in malformed_files:
            with self.subTest(data=data), mock.patch("scripts.read_team_rules.run_gh_api", return_value=data):
                with self.assertRaises(RuleReadError) as captured:
                    gh_file("eugene-aicoe", "project", "a" * 40, "AGENTS.md")
                self.assertEqual(captured.exception.code, "gh_error")
        for data in ({"type": "dir"}, [{"type": "symlink", "path": "x.md"}], [{"type": "file"}]):
            with self.subTest(data=data), mock.patch("scripts.read_team_rules.run_gh_api", return_value=data):
                with self.assertRaises(RuleReadError) as captured:
                    gh_directory("eugene-aicoe", "project", "a" * 40, ".github/X")
                self.assertEqual(captured.exception.code, "gh_error")

    def test_missing_required_reference_fails_in_gh_path(self) -> None:
        commit = "a" * 40

        def response(endpoint: str) -> object:
            if endpoint == "repos/eugene-aicoe/project":
                return {"default_branch": "trunk"}
            if endpoint == "repos/eugene-aicoe/project/commits/trunk":
                return {"sha": commit}
            if endpoint == f"repos/eugene-aicoe/project/contents/CLAUDE.md?ref={commit}":
                return {"type": "file", "content": "QFBPTElDWS5tZAo=", "encoding": "base64", "sha": "b" * 40}
            if endpoint.endswith(f"?ref={commit}"):
                raise RuleReadError("gh_not_found", "Not found")
            raise AssertionError(endpoint)

        with mock.patch("scripts.read_team_rules.run_gh_api", side_effect=response):
            with self.assertRaises(RuleReadError) as captured:
                inspect_target_via_gh({"owner": "eugene-aicoe", "repo": "project"})
        self.assertEqual(captured.exception.code, "required_reference_missing")


class CleanupFailureTests(unittest.TestCase):
    def test_successful_retrieval_with_cleanup_failure_is_an_error(self) -> None:
        with mock.patch("scripts.read_team_rules.run_git", side_effect=["", "a" * 40]), mock.patch(
            "scripts.read_team_rules.run_git_cleanup",
            side_effect=RuleReadError("cleanup_failed", "Temporary rule ref cleanup could not be verified"),
        ):
            with self.assertRaises(RuleReadError) as captured:
                fetch_rules_commit(PROJECT_ROOT, "origin", "trunk")
        self.assertEqual(captured.exception.code, "cleanup_failed")

    def test_retrieval_and_cleanup_failure_preserve_primary_and_add_safe_cleanup_detail(self) -> None:
        with mock.patch(
            "scripts.read_team_rules.run_git",
            side_effect=RuleReadError("git_error", "credential=secret"),
        ), mock.patch(
            "scripts.read_team_rules.run_git_cleanup",
            side_effect=RuleReadError("cleanup_failed", "Temporary rule ref cleanup could not be verified"),
        ):
            with self.assertRaises(RuleReadError) as captured:
                fetch_rules_commit(PROJECT_ROOT, "origin", "trunk")
        self.assertEqual(captured.exception.code, "fetch_failed")
        self.assertIn("cleanup could not be verified", captured.exception.message.lower())
        self.assertNotIn("secret", captured.exception.message)


class LocalRemoteRuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory(dir=PROJECT_ROOT)
        self.root = Path(self.tempdir.name)
        self.remote = self.root / "remote.git"
        self.seed = self.root / "seed"
        self.local = self.root / "local"
        self.git("init", "--bare", "--initial-branch=trunk", str(self.remote))
        self.git("init", "--initial-branch=trunk", str(self.seed))
        self.git("-C", str(self.seed), "config", "user.email", "tests@example.invalid")
        self.git("-C", str(self.seed), "config", "user.name", "Rule Tests")

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    @staticmethod
    def git(*args: str, cwd: Path | None = None) -> str:
        return subprocess.run(
            ("git", *args), cwd=cwd, text=True, capture_output=True, check=True
        ).stdout.strip()

    def write_seed(self, files: dict[str, str | bytes]) -> None:
        for name, content in files.items():
            path = self.seed / name
            path.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, bytes):
                path.write_bytes(content)
            else:
                path.write_text(content, encoding="utf-8")
        self.git("-C", str(self.seed), "add", ".")
        self.git("-C", str(self.seed), "commit", "-m", "test: seed rules")
        self.git("-C", str(self.seed), "remote", "add", "origin", str(self.remote))
        self.git("-C", str(self.seed), "push", "-u", "origin", "trunk")
        self.git("clone", str(self.remote), str(self.local))
        self.git("-C", str(self.local), "config", "user.email", "tests@example.invalid")
        self.git("-C", str(self.local), "config", "user.name", "Rule Tests")

    def push_remote_update(self, files: dict[str, str]) -> str:
        for name, content in files.items():
            path = self.seed / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        self.git("-C", str(self.seed), "add", ".")
        self.git("-C", str(self.seed), "commit", "-m", "docs: update remote rules")
        self.git("-C", str(self.seed), "push", "origin", "trunk")
        return self.git("-C", str(self.seed), "rev-parse", "HEAD")

    def before(self) -> dict[str, str]:
        return {
            "head": self.git("-C", str(self.local), "rev-parse", "HEAD"),
            "branch": self.git("-C", str(self.local), "branch", "--show-current"),
            "status": self.git("-C", str(self.local), "status", "--porcelain=v1"),
            "refs": self.git("-C", str(self.local), "for-each-ref", "refs/eugene-team-rules"),
            "fetch_head": (self.local / ".git" / "FETCH_HEAD").read_text(encoding="utf-8") if (self.local / ".git" / "FETCH_HEAD").exists() else "",
        }

    def assert_invariant(self, before: dict[str, str]) -> None:
        self.assertEqual(self.before(), before)

    def test_reads_newer_default_trunk_without_worktree_changes(self) -> None:
        self.write_seed({"AGENTS.md": "stale local rules\n", "CLAUDE.md": "@AGENTS.md\n", "tracked.txt": "base\n"})
        remote_commit = self.push_remote_update({"AGENTS.md": "fresh remote rules\n"})
        (self.local / "tracked.txt").write_text("dirty\n", encoding="utf-8")
        self.git("-C", str(self.local), "add", "tracked.txt")
        before = self.before()
        result = _inspect_local_team_repo(self.local)
        self.assertEqual(result["default_branch"], "trunk")
        self.assertEqual(result["rules_commit"], remote_commit)
        self.assertEqual(result["files"], [
            {"path": "AGENTS.md", "content": "fresh remote rules\n"},
            {"path": "CLAUDE.md", "content": "@AGENTS.md\n"},
        ])
        self.assertEqual(result["references"], [{"from": "CLAUDE.md", "to": "AGENTS.md"}])
        self.assert_invariant(before)

    def test_no_rules_is_clean_failure_and_missing_remote_is_clean_failure(self) -> None:
        self.write_seed({"README.md": "no policy\n"})
        before = self.before()
        with self.assertRaisesRegex(RuleReadError, "rules_not_found"):
            _inspect_local_team_repo(self.local)
        self.assert_invariant(before)
        self.git("-C", str(self.local), "remote", "remove", "origin")
        before = self.before()
        with self.assertRaisesRegex(RuleReadError, "remote_not_found"):
            _inspect_local_team_repo(self.local)
        self.assert_invariant(before)

    def test_reference_cycle_and_outside_reference_are_rejected_and_cleaned(self) -> None:
        self.write_seed({"AGENTS.md": "@CLAUDE.md\n", "CLAUDE.md": "@AGENTS.md\n"})
        before = self.before()
        with self.assertRaisesRegex(RuleReadError, "reference_cycle"):
            _inspect_local_team_repo(self.local)
        self.assert_invariant(before)
        self.tempdir.cleanup()
        self.setUp()
        self.write_seed({"AGENTS.md": "@../outside.md\n"})
        before = self.before()
        with self.assertRaisesRegex(RuleReadError, "invalid_reference"):
            _inspect_local_team_repo(self.local)
        self.assert_invariant(before)

    def test_missing_required_reference_fails_and_cleans_temp_ref(self) -> None:
        self.write_seed({"AGENTS.md": "base rules\n", "CLAUDE.md": "@POLICY.md\n"})
        before = self.before()
        with self.assertRaises(RuleReadError) as captured:
            _inspect_local_team_repo(self.local)
        self.assertEqual(captured.exception.code, "required_reference_missing")
        self.assert_invariant(before)

    def test_two_invocations_capture_two_distinct_remote_rule_shas(self) -> None:
        self.write_seed({"AGENTS.md": "rules v1\n"})
        first = _inspect_local_team_repo(self.local)
        second_sha = self.push_remote_update({"AGENTS.md": "rules v2\n"})
        second = _inspect_local_team_repo(self.local)
        self.assertNotEqual(first["rules_commit"], second["rules_commit"])
        self.assertEqual(second["rules_commit"], second_sha)
        self.assertEqual(second["files"], [{"path": "AGENTS.md", "content": "rules v2\n"}])

    def test_discovers_pull_request_and_issue_templates_when_requested(self) -> None:
        self.write_seed({
            ".github/PULL_REQUEST_TEMPLATE.md": "default template\n",
            ".github/PULL_REQUEST_TEMPLATE/feature.md": "feature template\n",
            ".github/ISSUE_TEMPLATE/bug.md": "issue template\n",
        })
        pull_result = _inspect_local_team_repo(self.local)
        self.assertEqual([item["path"] for item in pull_result["files"]], [
            ".github/PULL_REQUEST_TEMPLATE.md", ".github/PULL_REQUEST_TEMPLATE/feature.md",
        ])
        issue_result = _inspect_local_team_repo(self.local, operation="issue")
        self.assertEqual([item["path"] for item in issue_result["files"]], [
            ".github/PULL_REQUEST_TEMPLATE.md", ".github/PULL_REQUEST_TEMPLATE/feature.md",
            ".github/ISSUE_TEMPLATE/bug.md",
        ])


class CliContractTests(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run((sys.executable, str(HELPER), *args), text=True, capture_output=True, check=False)

    def test_errors_are_json_and_do_not_leak_credentials(self) -> None:
        result = self.run_cli("--repo-path", "/definitely/not/a/repository", "--target", "https://secret@example.invalid/x")
        self.assertNotEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["scope"], "unknown")
        self.assertFalse(payload["write_allowed"])
        self.assertNotIn("secret", result.stdout + result.stderr)

    def test_personal_scope_omits_rule_content(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "personal"
            subprocess.run(("git", "init", str(repo)), check=True, capture_output=True)
            subprocess.run(("git", "-C", str(repo), "remote", "add", "origin", "https://github.com/koreaben777/demo.git"), check=True, capture_output=True)
            result = self.run_cli("--repo-path", str(repo))
        self.assertEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["scope"], "personal")
        self.assertNotIn("content", json.dumps(payload))

    def test_team_lookup_failure_is_team_json_with_write_prohibited(self) -> None:
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT) as temp:
            repo = Path(temp) / "team"
            subprocess.run(("git", "init", str(repo)), check=True, capture_output=True)
            subprocess.run(("git", "-C", str(repo), "remote", "add", "origin", "https://token@github.com/eugene-aicoe/demo.git"), check=True, capture_output=True)
            result = self.run_cli("--repo-path", str(repo))
        self.assertNotEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["scope"], "team")
        self.assertFalse(payload["write_allowed"])
        self.assertNotIn("token", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
