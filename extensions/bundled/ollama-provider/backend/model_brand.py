"""Ollama model brand resolution for the ollama-provider extension.

Self-contained: no imports from infrastructure.* or domain.*.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

PRIMARY_BRAND_RULES: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"deepseek", re.IGNORECASE), "deepseek"),
    (re.compile(r"mixtral|mistral|devstral|codestral|magistral", re.IGNORECASE), "mistral"),
    (re.compile(r"qwen", re.IGNORECASE), "qwen"),
    (re.compile(r"gemma", re.IGNORECASE), "gemma"),
    (re.compile(r"command[-_]?r|\bcohere\b", re.IGNORECASE), "cohere"),
    (re.compile(r"\baya\b", re.IGNORECASE), "aya"),
    (re.compile(r"granite|ibm/", re.IGNORECASE), "ibm"),
    (re.compile(r"phi[-_]?[34]|(^|[-_/])orca\b|wizardlm", re.IGNORECASE), "microsoft"),
    (re.compile(r"gpt-oss|openai|gpt-4|gpt-3", re.IGNORECASE), "openai"),
    (re.compile(r"nous|hermes", re.IGNORECASE), "nousresearch"),
    (re.compile(r"chatglm|glm[-._]?[0-9]|zhipu", re.IGNORECASE), "zhipu"),
    (re.compile(r"baichuan", re.IGNORECASE), "baichuan"),
    (re.compile(r"yi[-._]|01-ai|zeroone", re.IGNORECASE), "yi"),
    (re.compile(r"internlm|internvl", re.IGNORECASE), "internlm"),
    (re.compile(r"moonshot|kimi", re.IGNORECASE), "moonshot"),
    (re.compile(r"minimax", re.IGNORECASE), "minimax"),
    (re.compile(r"dolphin", re.IGNORECASE), "dolphin"),
    (re.compile(r"falcon|tii/", re.IGNORECASE), "tii"),
    (re.compile(r"rwkv", re.IGNORECASE), "rwkv"),
    (re.compile(r"stablelm|stability", re.IGNORECASE), "stability"),
    (re.compile(r"nemotron|nvidia", re.IGNORECASE), "nvidia"),
    (re.compile(r"solar[-._]|upstage", re.IGNORECASE), "upstage"),
    (re.compile(r"voyage", re.IGNORECASE), "voyage"),
    (re.compile(r"perplexity", re.IGNORECASE), "perplexity"),
    (re.compile(r"phind", re.IGNORECASE), "phind"),
    (re.compile(r"arctic|snowflake", re.IGNORECASE), "snowflake"),
    (re.compile(r"gemini|/google/", re.IGNORECASE), "google"),
    (re.compile(r"meta-llama|codellama|tinyllama|vicuna|(^|[-_/])llama\b", re.IGNORECASE), "meta"),
]

FALLBACK_BRAND_RULES: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"hf\.co/|huggingface", re.IGNORECASE), "huggingface"),
]

FAMILY_TO_BRAND_RULES: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"qwen", re.IGNORECASE), "qwen"),
    (re.compile(r"mistral|mixtral", re.IGNORECASE), "mistral"),
    (re.compile(r"llama|meta\.?llama", re.IGNORECASE), "meta"),
    (re.compile(r"gemma", re.IGNORECASE), "gemma"),
    (re.compile(r"phi", re.IGNORECASE), "microsoft"),
    (re.compile(r"deepseek", re.IGNORECASE), "deepseek"),
    (re.compile(r"granite|ibm", re.IGNORECASE), "ibm"),
    (re.compile(r"cohere", re.IGNORECASE), "cohere"),
    (re.compile(r"falcon|tii", re.IGNORECASE), "tii"),
    (re.compile(r"internlm", re.IGNORECASE), "internlm"),
    (re.compile(r"baichuan", re.IGNORECASE), "baichuan"),
    (re.compile(r"\byi\b|zeroone|01-ai", re.IGNORECASE), "yi"),
    (re.compile(r"moonshot", re.IGNORECASE), "moonshot"),
    (re.compile(r"minimax", re.IGNORECASE), "minimax"),
    (re.compile(r"dolphin", re.IGNORECASE), "dolphin"),
    (re.compile(r"rwkv", re.IGNORECASE), "rwkv"),
    (re.compile(r"stablelm|stable[-_]diffusion", re.IGNORECASE), "stability"),
    (re.compile(r"nemotron|nvidia", re.IGNORECASE), "nvidia"),
    (re.compile(r"gpt-oss|gpt2|gptneo|openai", re.IGNORECASE), "openai"),
    (re.compile(r"nous", re.IGNORECASE), "nousresearch"),
    (re.compile(r"chatglm|glm", re.IGNORECASE), "zhipu"),
    (re.compile(r"bert|roberta|distilbert", re.IGNORECASE), "huggingface"),
]


def _get_brand_key(full_id: Optional[str]) -> Optional[str]:
    if not full_id:
        return None
    s = full_id.strip()
    if not s:
        return None
    for pattern, key in PRIMARY_BRAND_RULES:
        if pattern.search(s):
            return key
    for pattern, key in FALLBACK_BRAND_RULES:
        if pattern.search(s):
            return key
    return None


def _extract_family(payload: Any) -> Optional[str]:
    if not isinstance(payload, dict):
        return None
    details = payload.get("details")
    if isinstance(details, dict):
        family = details.get("family")
        if isinstance(family, str) and family.strip():
            return family.strip()
        families = details.get("families")
        if isinstance(families, list) and families and isinstance(families[0], str) and families[0].strip():
            return families[0].strip()
    family = payload.get("family")
    if isinstance(family, str) and family.strip():
        return family.strip()
    families = payload.get("families")
    if isinstance(families, list) and families and isinstance(families[0], str) and families[0].strip():
        return families[0].strip()
    model_info = payload.get("model_info")
    if isinstance(model_info, dict):
        arch = model_info.get("general.architecture")
        if isinstance(arch, str) and arch.strip():
            return arch.strip()
        for k, v in model_info.items():
            if k.endswith(".architecture") and isinstance(v, str) and v.strip():
                return v.strip()
    return None


def _brand_key_from_family(family: Optional[str]) -> Optional[str]:
    if not family:
        return None
    s = family.strip()
    if not s:
        return None
    for pattern, key in FAMILY_TO_BRAND_RULES:
        if pattern.search(s):
            return key
    return None


def resolve_brand_key(model_id: str, show_payload: Optional[Dict[str, Any]] = None) -> Optional[str]:
    brand_key = _get_brand_key(model_id)
    if brand_key:
        return brand_key
    if show_payload:
        family = _extract_family(show_payload)
        if family:
            return _brand_key_from_family(family)
    return None


__all__ = ["resolve_brand_key"]
