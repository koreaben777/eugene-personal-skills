# Eugene Personal Skills

유진그룹 AI CoE 업무에서 쓰는 개인 에이전트 스킬 4종입니다. Codex와 Claude Code에서 같은 `SKILL.md`를 씁니다.

| 스킬 | 용도 | 추가로 필요한 것 |
| --- | --- | --- |
| `eugene-next-tasks` | 개요서·로컬 문서·Git·Notion에서 현황을 모아 내 역할 기준 다음 할 일을 정리 (읽기 전용) | Notion 연결(없으면 로컬 근거만 사용) |
| `eugene-official-notice` | "업무연락" 공문 서식의 `.docx` 생성 | Python 3, `python-docx` |
| `eugene-resume` | 업무를 시작하거나 다른 에이전트 작업을 이어받을 때 프로젝트·지침·작업 상태 확인 | — |
| `eugene-team-git-rules` | `eugene-aicoe` 팀 저장소 작업 전에 원격 기본 브랜치의 최신 규약을 읽어 적용 | Python 3.11+, 인증된 `gh` CLI |

## 설치

스킬은 `Eugene_Group` 작업 폴더의 `.agents/skills/` 아래에 있다고 가정합니다(`eugene-resume`은 자신의 위치에서 `../../..`를 기준 루트로 씁니다).

```bash
git clone https://github.com/koreaben777/eugene-personal-skills.git
```

```bash
cp -R eugene-personal-skills/skills/* "${EUGENE_GROUP_ROOT:-$HOME/Documents/Eugene_Group}/.agents/skills/"
```

작업 폴더가 `~/Documents/Eugene_Group`이 아니면 `EUGENE_GROUP_ROOT` 환경변수로 지정합니다. `eugene-team-git-rules`의 helper와 테스트가 이 값을 읽습니다. 문서 안의 `~/Documents/Eugene_Group` 표기도 자신의 경로로 읽으면 됩니다.

## 전제

- 스킬은 작업 폴더의 `AGENTS.md`, Notion 사용 가이드, 프로젝트별 지침이 있다고 가정하고 그것을 먼저 읽습니다. 그 문서들은 이 저장소에 없습니다.
- 내부 자료, 접속 정보, Notion 식별자는 포함하지 않습니다.
- `eugene-official-notice/assets/logo.jpg`는 유진그룹의 상표이며, 사내 문서 작성 용도로만 씁니다.

## 검증

```bash
cd skills/eugene-team-git-rules && python3 -m unittest discover -s tests -t .
```
