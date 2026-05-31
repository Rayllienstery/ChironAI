from __future__ import annotations


import pytest

from llm_proxy.chat_completions_request_parsing import (
    non_empty_str,
    positive_int_env,
    resolve_trace_chain_id,
    truthy_body_flag,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (True, True),
        (False, False),
        ("true", True),
        ("YES", True),
        ("on", True),
        ("0", False),
        ("off", False),
        (1, True),
        (0, False),
        (None, False),
        ([], False),
    ],
)
def test_truthy_body_flag(value: object, expected: bool) -> None:
    assert truthy_body_flag(value) is expected


def test_positive_int_env_uses_default_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CHIRON_TEST_INT_ENV", raising=False)
    assert positive_int_env("CHIRON_TEST_INT_ENV", 1024) == 1024


def test_positive_int_env_clamps_below_minimum(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHIRON_TEST_INT_ENV", "10")
    assert positive_int_env("CHIRON_TEST_INT_ENV", 1024) == 256


def test_positive_int_env_parses_valid_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHIRON_TEST_INT_ENV", "4096")
    assert positive_int_env("CHIRON_TEST_INT_ENV", 1024) == 4096


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  hello  ", "hello"),
        ("", ""),
        (None, ""),
        (42, "42"),
    ],
)
def test_non_empty_str(raw: object, expected: str) -> None:
    assert non_empty_str(raw) == expected


def test_resolve_trace_chain_id_prefers_client_request_id() -> None:
    chain_id, source = resolve_trace_chain_id(
        client_request_id="client-chain-1",
        proxy_trace_meta={"incoming_request_id": "header-chain-1"},
    )
    assert chain_id == "client-chain-1"
    assert source == "client_request_id"


def test_resolve_trace_chain_id_uses_incoming_meta_when_client_id_missing() -> None:
    chain_id, source = resolve_trace_chain_id(
        client_request_id="",
        proxy_trace_meta={"incoming_request_id": "header-chain-1"},
    )
    assert chain_id == "header-chain-1"
    assert source == "incoming_request_id"


def test_resolve_trace_chain_id_prefers_explicit_proxy_trace_meta() -> None:
    chain_id, source = resolve_trace_chain_id(
        client_request_id="",
        proxy_trace_meta={"incoming_request_id": "header-chain-1", "trace_chain_id": "responses-chain-1"},
    )
    assert chain_id == "responses-chain-1"
    assert source == "trace_chain_id"
