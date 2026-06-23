from __future__ import annotations

from modules.md_indexer.application import steps


class TestStepWrapIndentedCode:
    def test_wraps_simple_indented_block_with_language(self) -> None:
        md = (
            "Text before.\n"
            "\n"
            "    line1\n"
            "    line2\n"
            "\n"
            "Text after.\n"
        )
        out = steps.step_wrap_indented_code(
            md,
            {"language": "swift", "min_block_lines": 2},
        )
        expected = (
            "Text before.\n"
            "\n"
            "```swift\n"
            "    line1\n"
            "    line2\n"
            "```\n"
            "\n"
            "Text after.\n"
        )
        assert out == expected

    def test_does_not_touch_existing_fenced_blocks(self) -> None:
        md = (
            "```swift\n"
            "    inside\n"
            "```\n"
            "\n"
            "    outside\n"
        )
        out = steps.step_wrap_indented_code(
            md,
            {"language": "swift", "min_block_lines": 1},
        )
        expected = (
            "```swift\n"
            "    inside\n"
            "```\n"
            "\n"
            "```swift\n"
            "    outside\n"
            "```\n"
        )
        assert out == expected

    def test_respects_min_block_lines(self) -> None:
        md = (
            "Text.\n"
            "    only one line\n"
        )
        out = steps.step_wrap_indented_code(
            md,
            {"language": "swift", "min_block_lines": 2},
        )
        assert out == md

