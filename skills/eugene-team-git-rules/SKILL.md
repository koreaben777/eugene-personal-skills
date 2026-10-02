---
name: eugene-team-git-rules
description: Use when Git or GitHub work under ~/Documents/Eugene_Group may target a GitHub eugene-aicoe repository, including clone, branch, code changes, commit, fetch, pull, push, PR, review, merge, revert, repository settings, or status checks
---

# Eugene team repository gate

When invoked, begin the response with the exact first line `Skill gate: eugene-team-git-rules` before any rule metadata.

Apply this skill only when the work path is under `~/Documents/Eugene_Group` **and** the GitHub owner is exactly `eugene-aicoe`. Do not infer team scope from similar policy text. If either condition is false, stop this skill and follow applicable local instructions.

## Required sequence

1. At the start of every triggered Git/GitHub request, and before any repository write, resolve and invoke the read-only helper. It accepts a local repository/work path or an explicit target:

   ```bash
   SKILL_DIR="$(cd -- "${EUGENE_GROUP_ROOT:-$HOME/Documents/Eugene_Group}/.agents/skills/eugene-team-git-rules" && pwd -P)"
   HELPER="$SKILL_DIR/scripts/read_team_rules.py"
   # Local repository, using its selected remote:
   python3 "$HELPER" --repo-path "$REPO_PATH"
   # Local repository, with an explicit remote:
   python3 "$HELPER" --repo-path "$REPO_PATH" --remote "$REMOTE"
   # Without a local repository:
   python3 "$HELPER" --repo-path "$WORK_PATH" --target "$OWNER/$REPO"
   # For issue work, include issue templates (the only validated operation value):
   python3 "$HELPER" --repo-path "$REPO_PATH" --operation issue
   ```

   Parse stdout as JSON; do not treat remembered text, a parent-rule copy, or a prior request as a result. The explicit target must be a strict `OWNER/REPO` or accepted GitHub URL. An explicit `--remote` always wins. Without it, the helper selects the sole team remote, or—when no team remote exists—the sole configured remote; ambiguous multi-remote layouts fail closed and require `--remote`.
2. Use the quick reference below. For `team`, read every returned `files[*].content` and every returned internal `references` target. Do not dump full policy text. The complete supported internal-reference contract is an otherwise-empty line exactly matching `@relative/path.md`; that target is required, recursively followed, and missing/unreadable targets are errors. Other prose or inline link forms are not reference directives.
3. State the checked `default_branch`, a short display of the exact `rules_commit` SHA, `checked_at`, and returned file paths. Apply the freshly returned rules only within system/developer instructions, the current user request and approval, Eugene_Group security/Finder-tag/data-protection limits, and any stricter applicable local instruction.
4. Immediately before a remote-affecting operation (including push, PR changes, merge, remote branch/tag changes, or repository settings), rerun the helper. Compare the new full `rules_commit` to the earlier full SHA. If it differs, reread all returned rules and revalidate the planned operation; if the check errors or is incomplete, do not write.
5. A new user request requires a new helper run. Never substitute memory or stale local reasoning.

| JSON `scope` / result | Action |
|---|---|
| `team` with complete metadata and `files` | Read returned rules and references; continue only after the gates above. |
| `personal` | Stop this skill; use applicable personal/local instructions. |
| `out_of_scope` | Stop this skill; do not apply team rules. |
| error, missing, malformed, or incomplete result | No repository or remote write. Report the blocked stage, target/remote, unavailable lookup, and minimum remedy without credentials or full policy. |

## Rationalization counters

- “I read this repository’s rules earlier.” → Refresh now for this request; refresh again before remote effects.
- “The local `AGENTS.md` is probably current.” → Refresh the remote default branch now; local text cannot replace it.
- “It is only a branch/status check.” → Refresh now; status and branch work are still in scope.
- “The fetch failed, but I remember the convention.” → Stop all writes and report the helper error; memory is not authority.
- “The user already approved the code change, so rule lookup is unnecessary.” → Approval does not waive the helper or freshness gate; refresh now, and stop writes on failure.
