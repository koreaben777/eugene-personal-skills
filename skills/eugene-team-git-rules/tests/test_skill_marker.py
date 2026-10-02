"""Structural contract for the installed skill's invocation marker."""

from pathlib import Path
import unittest


class SkillInvocationMarkerTests(unittest.TestCase):
    def test_invoked_response_requires_stable_first_line_marker(self) -> None:
        skill = (Path(__file__).resolve().parents[1] / "SKILL.md").read_text(
            encoding="utf-8"
        )
        required_instruction = (
            "When invoked, begin the response with the exact first line "
            "`Skill gate: eugene-team-git-rules` before any rule metadata."
        )
        self.assertIn(required_instruction, skill)


if __name__ == "__main__":
    unittest.main()
