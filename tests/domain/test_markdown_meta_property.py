"""Property-based tests for the markdown meta block parser."""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from domain.services.markdown_meta import parse_and_strip_meta_block


class TestParseAndStripMetaBlockProperties:
    """High-level invariants that must hold for arbitrary inputs."""

    @given(st.text())
    def test_idempotent_strip(self, md: str) -> None:
        """Stripping a meta block twice yields the same body as stripping once."""
        _, body_once = parse_and_strip_meta_block(md)
        _, body_twice = parse_and_strip_meta_block(body_once)
        assert body_once == body_twice

    @given(st.text())
    def test_reparse_after_strip_is_empty(self, md: str) -> None:
        """After the first parse+strip, a second parse finds no meta block."""
        _, body = parse_and_strip_meta_block(md)
        meta2, body2 = parse_and_strip_meta_block(body)
        assert meta2 == {}
        assert body == body2

    @given(st.text(alphabet=st.characters(blacklist_characters="<"), min_size=0, max_size=200))
    def test_no_leading_comment_means_empty_meta(self, md: str) -> None:
        """Any text that does not start with '<!--' produces empty meta."""
        meta, body = parse_and_strip_meta_block(md)
        assert meta == {}
        assert body == md

    @given(st.text(alphabet=st.characters(), min_size=0, max_size=50))
    def test_unclosed_comment_returns_original(self, prefix: str) -> None:
        """A leading '<!--' without a closing '-->' is not treated as a block."""
        md = f"<!--{prefix}"
        meta, body = parse_and_strip_meta_block(md)
        assert meta == {}
        assert body == md

    @given(
        st.dictionaries(
            st.sampled_from(["url", "framework", "doc_kind", "doc_scope"]),
            st.text(min_size=1, max_size=30)
            .filter(lambda s: ":" not in s and s.strip() == s and len(s.splitlines()) == 1),
            min_size=1,
            max_size=4,
        )
    )
    def test_round_trip_simple_meta(self, fields: dict[str, str]) -> None:
        """A generated simple meta block is parsed and stripped correctly."""
        lines = "\n".join(f"{key}: {value}" for key, value in fields.items())
        md = f"<!--\n{lines}\n-->\n\nbody"
        meta, body = parse_and_strip_meta_block(md)
        for key, value in fields.items():
            assert meta.get(key) == value
        assert body == "body"

    @given(st.text())
    def test_output_body_is_suffix_of_input(self, md: str) -> None:
        """The returned body is always a substring of the original input."""
        _, body = parse_and_strip_meta_block(md)
        assert body in md or body == md

    @given(st.text())
    def test_meta_is_dict(self, md: str) -> None:
        """The parser always returns a dict for meta, never None."""
        meta, _ = parse_and_strip_meta_block(md)
        assert isinstance(meta, dict)
