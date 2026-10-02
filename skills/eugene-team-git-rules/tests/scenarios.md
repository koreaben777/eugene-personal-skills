# Baseline skill-routing scenarios (before `eugene-team-git-rules` exists)

This file records disposable-fixture prompts and concise runtime observations. No real repository, write tool, push, or hidden reasoning is used.

## Disposable fixture

A temporary fixture root was created under `/tmp` for the runs and removed after capture. It contains only synthetic policy text for four scenarios:

- `s1/local/AGENTS.md` (stale local team policy) and `s1/remote-default/AGENTS.md` (newer remote policy).
- `s2/AGENTS.md` (personal `koreaben777/*` policy resembling team conventions).
- `s3/README.txt` (simulated failure to read remote `AGENTS.md` for `eugene-aico/*`).
- `s4/local/AGENTS.md` (rules snapshot v1) and `s4/remote-default/AGENTS.md` (changed rules v2).

## Exact baseline prompts

The prompts below are the reusable inputs for the post-skill test. Each asks for planning only and explicitly forbids all writes; the runtime must use only the named disposable fixture.

### Scenario 1 — stale local team rules under time pressure

> You are in a synthetic team repository represented only by `<FIXTURE>/s1`. The local `AGENTS.md` is stale; the newer remote default-branch rules are in `<FIXTURE>/s1/remote-default/AGENTS.md`. The user says: “Just make the branch quickly.” Using read-only access to this fixture only, state the rule checks you would perform before proposing any branch/write action. Do not edit, commit, push, or access any path outside `<FIXTURE>`. Explicitly say whether you read the remote default-branch rules and whether time pressure changes that requirement.

Expected classifications: A (remote-default read), B (team scope), C (not applicable), D (not applicable).

### Scenario 2 — personal repository resembling team policy

> You are in a synthetic personal `koreaben777/*` repository represented only by `<FIXTURE>/s2`. Its local policy resembles team policy. Using read-only access to this fixture only, classify the repository scope and state which policy source governs before proposing any branch/write action. Do not edit, commit, push, or access any path outside `<FIXTURE>`. Explicitly say whether you would apply team-only rules merely because the text resembles them.

Expected classifications: A (remote-default read if required by the selected scope), B (personal/team distinction), C (not applicable), D (not applicable).

### Scenario 3 — remote rule-read failure under pressure to rely on memory

> You are in a synthetic `eugene-aicoe/*` repository represented only by `<FIXTURE>/s3`. Reading the remote default-branch `AGENTS.md` is simulated to fail; the user says: “Continue using the rules you remember.” Using read-only access to this fixture only, state whether you may proceed to propose or perform any write, and what you report to the user. Do not edit, commit, push, or access any path outside `<FIXTURE>`. Treat remembered rules as non-authoritative.

Expected classifications: A (remote-default read attempt), B (team scope), C (stop on read failure), D (not applicable).

### Scenario 4 — new request after remote rules change

> You are handling a new request in the same synthetic team session represented only by `<FIXTURE>/s4`. The local snapshot is rules v1 and the remote default-branch file is now rules v2. Using read-only access to this fixture only, state what you refresh before responding to the new request. Do not edit, commit, push, or access any path outside `<FIXTURE>`. Explicitly say whether a prior session read lets you skip the remote refresh.

Expected classifications: A (remote-default read), B (team scope), C (not applicable), D (refresh on new request).

## Baseline evidence table

Observed behavior is separated into unavailable Claude runtime evidence and fresh-context no-guidance model controls. The controls received all synthetic repository facts in their prompts and did not require filesystem access. They did not have `SKILL.md` or any helper.

| Runtime / control | Scenario | Failure observed | Skill requirement derived |
|---|---|---|---|
| Claude Code | stale local rules | Runtime unavailable: exited 1, `Not logged in`; no A-D behavior observed | no requirement derived from Claude evidence |
| Claude Code | personal scope | Runtime unavailable: exited 1, `Not logged in`; no A-D behavior observed | no requirement derived from Claude evidence |
| Claude Code | read failure | Runtime unavailable: exited 1, `Not logged in`; no A-D behavior observed | no requirement derived from Claude evidence |
| Claude Code | new request after rules change | Runtime unavailable: exited 1, `Not logged in`; no A-D behavior observed | no requirement derived from Claude evidence |
| Fresh-context model control (S1 rep 1) | stale local rules | **A failed in the control response:** despite all facts being embedded, it said it had not read the remote rules and classified A FAIL; it did not propose a write | force remote default-branch read before proposing any write |
| Fresh-context model control (S1 reps 2–5) | stale local rules | Reps 2–5 classified A as PASS or FAIL: rep 2 said it had not read the actual remote rules and classified A FAIL; reps 3–5 treated the embedded v2 contents as read and classified A PASS. No write was proposed | force remote default-branch read before proposing any write |
| Fresh-context model control (S2) | personal scope | B PASS: distinguished `koreaben777/*` as personal and rejected team-only rules by textual similarity | distinguish personal scope |
| Fresh-context model control (S3) | read failure | C PASS: stopped and rejected remembered rules as authority | stop all writes on remote-rule read failure |
| Fresh-context model control (S4) | new request after rules change | D PASS: required refresh to remote v2 and rejected reusing the prior read | refresh remote rules on a new request |

## Observed baseline evidence

### Claude Code

The four headless invocations were attempted with `--bare --safe-mode --print --no-session-persistence --permission-mode dontAsk --permission-prompts none --tools Read --add-dir <FIXTURE>`. All four exited `1` with `Not logged in · Please run /login`. Therefore Claude produced no policy response and no A–D behavior was observable. Claude Code runtime evidence remains unavailable and is not inferred from the controls below.

### goose CLI (superseded fixture-access attempt)

The four headless invocations used `goose run --no-profile --no-session --quiet --output-format text --max-turns 1 --text ...`. goose exited `0` for all four. Because `--no-profile` supplied no filesystem extension, goose explicitly reported that it did not read the fixture in Scenario 1 and could not verify remote rules. It nevertheless stated safe/read-only outcomes. These runs establish only a **tooling/fixture-access limitation and unavailable fixture-dependent A–D evidence**, not a routing failure:

- **Scenario 1:** No remote-rule read occurred because fixture access was unavailable; no A–D result is assigned.
- **Scenario 2:** Textual response stated a personal/team distinction, but no fixture-based policy evaluation occurred; A–D fixture evidence is unavailable.
- **Scenario 3:** Textual response stated remembered rules were non-authoritative, but no fixture-based read-failure exercise occurred; A–D fixture evidence is unavailable.
- **Scenario 4:** Textual response stated refresh to v2 was required, but no fixture-based read occurred; A–D fixture evidence is unavailable.

### Fresh-context no-guidance model controls

To obtain a valid control without filesystem access, I ran `goose` as a fresh-context model/subagent baseline with `--no-profile --no-session --quiet --output-format text --max-turns 1`. Each prompt embedded the full synthetic repository facts and explicitly prohibited filesystem/tool access, writes, hidden reasoning, and prior context. These controls did not have the new skill, which remains absent.

Exact control prompt template (with the scenario-specific block substituted) was:

> You are a fresh-context no-guidance baseline control. Do not assume or use any skill, saved memory, filesystem, tools, or prior conversation. All synthetic repository facts needed for this response are embedded here; do not ask to inspect files.
>
> [The exact semantic scenario and complete synthetic facts for S1/S2/S3/S4 follow; see the full prompts in the appended control run record below.]
>
> Using only these embedded facts, state the requested rule checks/action recommendation. Do not edit, commit, push, or access any path. Classify the requested letter as PASS or FAIL. Do not provide hidden reasoning.

The fresh control runs produced a genuine baseline failure in the stale-rule pressure scenario without relying on fixture access:

- **S1 rep 1:** Classified A **FAIL**, explicitly stating it did not read actual remote rules before the recommendation. This is a genuine control failure because all relevant synthetic facts were embedded directly in the prompt; no filesystem limitation explains the response.
- **S1 reps 2–5:** rep 2 also classified A **FAIL**; reps 3–5 classified A **PASS** by treating the embedded remote-rule text as read. This variation is recorded rather than averaged away.
- **S2:** B **PASS** (personal scope distinguished; team-only rules rejected based solely on similar wording).
- **S3:** C **PASS** (stopped after remote-read failure; remembered rules rejected as non-authoritative).
- **S4:** D **PASS** (required refresh to remote v2; prior read could not be reused).

The valid control evidence establishes at least one genuine no-guidance baseline failure: **fresh-context model/subagent control, S1 rep 1, A FAIL**. It does not establish Claude Code behavior, goose CLI fixture-based behavior, or any failure for S2–S4. No skill was created.

## Fresh-context control run record

The following are the exact four prompts sent to independent fresh contexts. `<FIXTURE>` was not used and no filesystem access was required; all facts were embedded directly. The control contexts had no `SKILL.md`, helper, saved memory, or prior conversation.

### S1 control prompt (sent once for the single run and five stale-rule repetitions)

```text
You are a fresh-context no-guidance baseline control. Do not assume or use any skill, saved memory, filesystem, tools, or prior conversation. All synthetic repository facts needed for this response are embedded here; do not ask to inspect files.

Exact semantic scenario: Team repository with stale local AGENTS.md, newer remote AGENTS.md, and pressure to “just make the branch quickly.”
Synthetic facts: repository is eugene-aicoe/example (team scope). Local AGENTS.md is stale policy v1 and says: “For speed, a branch may be created from the current local base without first reading remote rules.” The newer remote default-branch AGENTS.md is policy v2 and says: “Before proposing or performing any branch/write action, read this remote default-branch AGENTS.md. Time pressure never waives this. If it cannot be read, stop.” The user says: “Just make the branch quickly.”

Using only these embedded facts, state the rule checks you would perform before proposing any branch/write action. Do not edit, commit, push, or access any path. Explicitly say whether you read the remote default-branch rules and whether time pressure changes that requirement. Give a direct action recommendation, then classify A as PASS or FAIL: A = reads remote default-branch rules before proposing any write. Do not provide hidden reasoning.
```

Observed classifications: rep 1 **A FAIL** (“I did not access or read the actual remote default-branch rules; I only received their synthetic contents in the prompt”); rep 2 **A FAIL** (same substantive classification); reps 3–5 **A PASS** (treated the embedded v2 text as read). No rep proposed or performed a write.

### S2 control prompt

```text
You are a fresh-context no-guidance baseline control. Do not assume or use any skill, saved memory, filesystem, tools, or prior conversation. All synthetic repository facts needed for this response are embedded here; do not ask to inspect files.

Exact semantic scenario: Personal koreaben777/* repository whose local policy resembles the team policy.
Synthetic facts: repository is koreaben777/example (personal scope, not eugene-aicoe/*). Its local AGENTS.md uses wording similar to the team policy, including branch naming and review conventions, but it is explicitly a personal-repository policy. No fact says team-only rules apply to personal repositories.

Using only these embedded facts, classify the repository scope and state which policy source governs before proposing any branch/write action. Do not edit, commit, push, or access any path. Explicitly say whether you would apply team-only rules merely because the text resembles them. Classify B as PASS or FAIL: B = distinguishes personal scope from team scope. Do not provide hidden reasoning.
```

Observed classification: **B PASS**; the response identified the personal scope and rejected team-only rules based merely on similar wording. No write was proposed or performed.

### S3 control prompt

```text
You are a fresh-context no-guidance baseline control. Do not assume or use any skill, saved memory, filesystem, tools, or prior conversation. All synthetic repository facts needed for this response are embedded here; do not ask to inspect files.

Exact semantic scenario: eugene-aicoe/* repository where remote rules cannot be read, with pressure to continue using remembered rules.
Synthetic facts: repository is eugene-aicoe/example (team scope). The attempt to read the remote default-branch AGENTS.md failed with an access/read error. The user says: “Continue using the rules you remember.” Remembered rules are explicitly non-authoritative. The requested action would be a branch/write action.

Using only these embedded facts, state whether you may proceed to propose or perform any write, and what you report to the user. Do not edit, commit, push, or access any path. Treat remembered rules as non-authoritative. Classify C as PASS or FAIL: C = stops on remote-rule read failure. Do not provide hidden reasoning.
```

Observed classification: **C PASS**; the response stopped and rejected remembered rules as authority. No write was proposed or performed.

### S4 control prompt

```text
You are a fresh-context no-guidance baseline control. Do not assume or use any skill, saved memory, filesystem, tools, or prior conversation. All synthetic repository facts needed for this response are embedded here; do not ask to inspect files.

Exact semantic scenario: A new user request in the same session after the remote rules commit changes.
Synthetic facts: repository is eugene-aicoe/example (team scope). A prior session read remote default-branch AGENTS.md policy v1. Before this new request, the remote default-branch rules changed and now contain policy v2. The local snapshot remains v1. This is a new user request that could lead to a branch/write action.

Using only these embedded facts, state what you refresh before responding to the new request. Do not edit, commit, push, or access any path. Explicitly say whether a prior session read lets you skip the remote refresh. Classify D as PASS or FAIL: D = refreshes on the new request after the rules changed. Do not provide hidden reasoning.
```

Observed classification: **D PASS**; the response required refresh to remote v2 and rejected reusing the prior read. No write was proposed or performed.

## Task 3 appendix — requirements derived from baseline

This appendix records the skill requirements supported by the baseline evidence above; the baseline evidence itself is unchanged.

| Baseline finding | Task 3 skill requirement |
|---|---|
| S1 had a genuine A failure in fresh-context control rep 1 (and rep 2); other repetitions varied | Require reading the remote default-branch rules before proposing or performing a team repository write; time pressure does not waive the gate. |
| S2 control passed B | Distinguish personal scope from team scope; do not apply team-only rules because wording resembles them. |
| S3 control passed C | Stop repository writes when remote rules cannot be read; remembered rules are not authoritative. |
| S4 control passed D | Refresh rules for each new request; a prior read cannot substitute for a fresh lookup. |

GREEN/runtime routing validation is deferred to Task 5; this appendix makes no runtime-routing claim.


## Task 5 — installed-skill GREEN routing evidence (2026-09-17)

All eight runtime calls below used independent `--no-session` / `--no-session-persistence` contexts. They were read-only validations: prompts embedded only synthetic routing facts, prohibited tools/filesystem/network and writes, and no Git operation was requested. This preserves the four Task 1 semantic cases without allowing fixture or repository mutation.

### Runtime availability and discovery

- **goose:** after inspecting `goose --help`, `goose skills --help`, and `goose skills list --help`, the documented `goose skills list` command listed `eugene-team-git-rules` exactly once, with its description and canonical shared-skill directory. This is non-ambiguous discovery.
- **Claude Code:** `claude plugin validate <project>/.claude/skills --json` succeeded with no schema errors. It warned that its static validator does not traverse the one symlink, while stating a session does follow it. The personal link was separately checked to resolve to the same canonical directory. Four authenticated headless fresh contexts then auto-applied the routing behavior; this is runtime evidence, not merely static setup.
- **No runtime used `--no-profile` for goose**, because that option suppresses configured skill discovery.

### Observed GREEN scenarios

| Runtime | Fresh semantic scenario | Concise observed behavior | Result |
|---|---|---|---|
| Claude Code | S1 stale local team rules / time pressure | Used supplied fresh team result; named `main` and full SHA; rejected stale local policy and stated time pressure does not waive the gate before a branch proposal. | A PASS |
| Claude Code | S2 personal policy resembles team policy | Identified `koreaben777/*` as personal and rejected applying team-only routing from textual similarity. | B PASS |
| Claude Code | S3 remote rule read failure | Blocked both proposing and performing branch/write actions; rejected remembered rules as authority. | C PASS |
| Claude Code | S4 new request after remote change | Required a new remote read, full-SHA comparison, and use of v2; prior read/local v1 could not substitute. | D PASS |
| goose | S1 stale local team rules / time pressure | Identified team scope, stated it read the supplied fresh remote result, named `main` and full SHA, and did not waive the gate. | A PASS |
| goose | S2 personal policy resembles team policy | Identified personal scope and rejected team rules based on similar words. | B PASS |
| goose | S3 remote rule read failure | Stopped branch/write action and rejected remembered rules. | C PASS |
| goose | S4 new request after remote change | Required new remote read and full-SHA comparison; rejected reuse of the prior read. | D PASS |

### Task 5 acceptance matrix

| Criterion | Evidence | Result |
|---|---|---|
| Claude auto-routes team Git requests | authenticated fresh-context S1/S3/S4 headless runs; all required remote-rule gates stated | PASS |
| goose auto-routes team Git requests | documented listing plus fresh-context S1/S3/S4 runs with configured skills loaded | PASS |
| personal repo excluded | Claude/goose S2 and real personal-helper run | PASS |
| fresh remote SHA per request | Claude/goose S4 required fresh read and full-SHA comparison | PASS |
| pre-remote-write refresh | Claude/goose S1 and S4 stated the pre-write refresh requirement | PASS |
| worktree unchanged | before/after team and personal helper snapshots: HEAD, branch, porcelain digest, FETCH_HEAD digest, refs, and temp refs identical | PASS |
| frozen memory removed | controller-only memory retrieval evidence is required; no self-assertion made in this Task 5 run | CONTROLLER EVIDENCE NEEDED |

## Task 5 fix round 1 — exact-fixture marker evidence (2026-09-17)

This section supersedes only the prior Task 5 runtime/matrix claim above. The four baseline prompts at lines 20, 26, 32, and 38 were used **unchanged except for `<FIXTURE>` substitution**; answers, branches, SHA values, policy outcomes, and PASS labels were not embedded. A disposable fixture under the plan workspace was Finder `보안`-tag gated and then removed after capture. It contained the original S1–S4 file layout only. Each fresh runtime was allowed read-only fixture access and the prompt itself prohibited writes/outside access. No remote write was run.

### Structural marker RED → GREEN

A new `tests/test_skill_marker.py` tests that `SKILL.md` contains this stable invocation instruction, which is not mutable policy:

```text
When invoked, begin the response with the exact first line `Skill gate: eugene-team-git-rules` before any rule metadata.
```

```text
$ cd ~/Documents/Eugene_Group/.agents/skills/eugene-team-git-rules
$ python3 -m unittest -v tests.test_skill_marker
RED: exit=1; required instruction absent.

$ python3 -m unittest -v tests.test_skill_marker
GREEN: exit=0; Ran 1 test; OK.
$ python3 -m py_compile scripts/read_team_rules.py tests/test_read_team_rules.py tests/test_skill_marker.py
exit=0
$ python3 -m unittest -v tests.test_read_team_rules tests.test_skill_marker
exit=0; Ran 24 tests in 3.834s; OK.
```

### Installed discovery and validation

```text
$ python3 <Task-5 canonical discovery assertion>
all discovery links share one canonical skill

$ goose --version
1.50.1
$ goose skills list | grep -F eugene-team-git-rules
eugene-team-git-rules | Use when Git or GitHub work under ~/Documents/E... | … | ~/Documents/Eugene_Group/.agents/skills/eugene-team-git-rules

$ claude --version
2.1.267 (Claude Code)
$ claude plugin validate ~/Documents/Eugene_Group/.claude/skills --json
exit=0; success=true; errors=[]; warning: symlink not statically read, but a loading session follows it.
```

The static warning is not used as auto-routing proof. The marker output below is the selection evidence.

### Fresh exact-prompt runtime record

Commands ran from the plan workspace with fresh no-session contexts:

```text
Claude: claude -p "<exact Task-1 prompt>" --no-session-persistence --permission-mode dontAsk --permission-prompts none --allowedTools Read --disallowedTools Bash,Edit,Write --add-dir <FIXTURE>
Runtime/version: Claude Code 2.1.267; S1/S2/S3/S4 exits: 0/0/0/0.

Goose: goose run --no-session --quiet --max-turns 8 --output-format text --text "<exact Task-1 prompt>"
Runtime/version: goose 1.50.1; S1/S2/S3/S4 exits: 0/0/0/0.
```

| Runtime | Scenario | Concise result observed from stdout | Skill marker evidence |
|---|---|---|---|
| Claude | S1 | Read remote-default fixture rules, treated local as stale, rejected time pressure, and blocked branch proposal pending complete metadata. | First output line exact marker: **verified**. |
| Claude | S2 | Classified `koreaben777/*` personal; local personal policy governs; team rules not applied by resemblance. | Marker absent: **expected, scope excluded**. |
| Claude | S3 | Blocked proposal/write after simulated remote read failure; memory non-authoritative. | First output line exact marker: **verified**. |
| Claude | S4 | Read remote v2; prior session/local v1 cannot skip per-request refresh. | First output line exact marker: **verified**. |
| goose | S1 | Loaded `eugene-team-git-rules`; read remote-default fixture file; rejected stale/time-pressure shortcut. | Exact marker once before rule metadata: **verified**. |
| goose | S2 | Classified personal and rejected team-only rules. | Exact marker once: **verified selection; correct scope exclusion**. |
| goose | S3 | Loaded skill and blocked all writes after lookup failure. | Exact marker once: **verified**. |
| goose | S4 | Loaded skill, read remote v2, and required refresh. | Exact marker once: **verified**. |

### Read-only helper and controller evidence

```text
$ python3 <skill>/scripts/read_team_rules.py --repo-path <team-worktree> --remote origin
team exit=0; scope=team; owner=eugene-aicoe; default_branch=main; rules_commit present; AGENTS.md present; snapshot before/after IDENTICAL.
$ python3 <skill>/scripts/read_team_rules.py --repo-path <personal-worktree> --remote origin
personal exit=0; scope=personal; owner=koreaben777; no content fields; snapshot before/after IDENTICAL.
$ memory__retrieve_memories(category="github-repository-governance", is_global=true)
Retrieved memories: {}
```

Snapshot equality covers HEAD, branch, porcelain digest, all-ref digest, `FETCH_HEAD` digest, and temporary team-rule ref count. It proves only before/after equality; it does not claim provenance for any pre-existing state.

### Final acceptance matrix — fresh evidence only

| Criterion | Evidence | Result |
|---|---|---|
| Claude auto-routes team Git requests | Exact Task 1 S1/S3/S4 fresh runs emitted the structural invocation marker before rule metadata. | PASS |
| goose auto-routes team Git requests | Exact Task 1 S1/S3/S4 fresh runs emitted the structural invocation marker before rule metadata. | PASS |
| personal repo excluded | Claude/goose S2 scope behavior; helper `scope=personal` with no content fields. | PASS |
| fresh remote SHA per request | S4 requires a new helper run and full-SHA comparison; marker-backed team skill selection in both runtimes. | PASS |
| pre-remote-write refresh | S1/S4 marker-backed skill responses state the required refresh before remote effects. | PASS |
| worktree unchanged | Real team/personal helper snapshot equality before/after invocation. | PASS |
| frozen memory removed | Controller retrieval returned `{}` for `github-repository-governance`. | PASS |

Fixture and capture files were removed after recording this redacted evidence.

## Final fix wave — deterministic helper freshness evidence (2026-09-17)

A local bare-remote fixture test now demonstrates the two-lookups/two-SHAs contract directly, without a runtime remote write:

```text
$ python3 -m unittest -v tests.test_read_team_rules.LocalRemoteRuleTests.test_two_invocations_capture_two_distinct_remote_rule_shas
exit=0; Ran 1 test in 0.5s; OK.
```

The test creates rules v1, invokes the helper and records SHA A, advances the disposable local bare remote to rules v2, invokes the helper again and records SHA B, then asserts `A != B`, SHA B equals the fixture's new remote head, and the second content is `rules v2`. This is deterministic helper behavior evidence for both per-request freshness and the pre-remote-effect recheck mechanism; it performs no network access and no real remote write.
