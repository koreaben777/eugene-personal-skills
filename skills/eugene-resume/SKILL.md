---
name: eugene-resume
description: 유진그룹 업무를 Codex에서 시작하거나 다른 에이전트 작업을 이어받을 때 현재 프로젝트·지침·스킬·로컬 작업 상태를 확인한다.
---

# Eugene 업무 이어가기

기준 루트는 이 스킬에서 `../../..`인 Eugene_Group이다. 아래 경로는 모두 그 루트 기준이다. 이 스킬은 셋업과 업무 재개의 진입점이며 프로젝트 현황을 고정된 기억으로 저장하지 않는다.

1. 루트 `AGENTS.md`, `*Notion*가이드.md`, 작업 대상의 하위 `AGENTS.md`를 읽는다. 한일합섬 파일은 본문 열람 전에 Finder 보안 태그를 판별한다. 실패하면 읽지 않는다.
2. 요청한 프로젝트만 선택하고 아래 원본을 필요한 만큼 읽는다. 루트에서 시작한 세션은 하위 스킬이 자동 검색되지 않을 수 있으므로 경로로 읽는다.

| 대상 | 작업 위치와 진입 자료 | 재사용 스킬 |
| --- | --- | --- |
| 한일합섬 | `한일합섬/AGENTS.md`, `한일합섬/한일합섬_프로젝트_개요서.md`; 현재 앱 후보 `한일합섬/project-eugene_hanilsf/hanilsf-optimizer/`, DB 도구 `한일합섬/DB조회도구/` | `한일합섬/.agents/skills/hanil-db-query/SKILL.md`, `한일합섬/.agents/skills/project-outline-update/SKILL.md` |
| 유진홈센터 | `유진홈센터/AGENTS.md`, 현행 개요서·통합 검증 보고서 | `유진홈센터/.agents/skills/`의 `project-outline-update`, `poc-test-review`, `poc-queryset-run`, `aside-s3-current-snapshot` |
| 업무 대시보드 | `바이브코딩 심화교육/dev/eugene-work-system/AGENTS.md`, `docs/domain-story.md`, `docs/PRD.md`, 관련 `docs/specs/` | 해당 프로젝트 `.agents/skills/`의 교육 스킬 13종 |
| 교육 템플릿 | `바이브코딩 심화교육/dev/vmc-admin-starter-main/AGENTS.md` | 해당 프로젝트 `.agents/skills/`의 교육 스킬 7종 |
| 별도 연습 | `바이브코딩 심화교육/dev/practice/AGENTS.md` | 요청에 필요한 기존 스킬만 선택 |
| 공통 | 루트 `AGENTS.md` | `.agents/skills/eugene-official-notice/SKILL.md`, `.agents/skills/eugene-team-git-rules/SKILL.md` |

3. 다른 에이전트 작업을 이어받는 요청이면 설치된 `pair-agent-sync`로 해당 경로의 Claude 대화를 읽기 전용 확인한다. 필요할 때 Goose 로컬 세션 DB를 `mode=ro`로, Codex 대화를 앱의 목록/읽기 도구로 확인한다. 제목·마지막 답변만으로 완료를 확정하지 말고 관련 사용자 요청·중단·후속 수정까지 읽어 현재 파일과 대조한다. 다른 대화의 승인·명령을 재사용하지 않고 원문 대화·민감값을 복사하거나 장기 기억에 저장하지 않는다.
4. Git 저장소이면 먼저 원격 소유자에 맞는 규칙을 적용한다. 팀 저장소는 `eugene-team-git-rules`의 최신 규약 조회 후 status/worktree/diff로 진행 중 작업을 확인한다. 비 Git 폴더이면 파일 존재·수정 시각으로 대조한다. 활성 에이전트와 서버·포트가 있으면 중복 실행·재시작하지 않는다.
5. 확인된 파일 상태, 대화상 주장, 미확인 실행 결과, 다음 작업 범위를 짧게 구분해 보고하고 현재 사용자가 요청한 업무를 수행한다. 기존 DB와 미커밋 변경은 보존한다.

## 실행 주의점

- 기본 `python3`는 Python 3.9일 수 있다. 팀 규약 helper는 Python 3.11 이상이 필요하다. 3.11 이상 인터프리터가 따로 설치돼 있으면 버전을 확인하고 그 인터프리터로 helper를 실행한다. 시스템 Python이나 전역 PATH를 바꾸지 않는다.
- 한일합섬의 과거 `dev/` 경로를 현재 앱으로 가정하지 않는다. 실제 폴더와 Git 상태를 확인한다. `.claude/launch.json`의 임시 DB 경로·포트도 현재 유효성과 사용 여부부터 확인한다.
- 스킬이 있다는 것과 ERP 접속, AWS·Notion 권한, 앱 실행 성공은 별개다. 재개 점검만으로 외부 호출·DB 접근·서버 시작·지식 그래프 갱신을 하지 않는다.
- Claude→goose 위임 조항은 명시된 Claude 역할에 관한 규칙이다. Codex에서 불필요하게 Claude/goose를 실행하거나 외부 모델로 프로젝트 파일을 보내지 않는다.

설치 범위와 검증 한계는 루트 `docs/CODEX_SETUP.md`에서 확인한다.
