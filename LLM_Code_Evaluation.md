# LLM Code Evaluation

This document defines how the project evaluates or reviews generated Swift code.

## Quality checks
- Code must compile (no placeholders like TODO / <#...#> / dummy).
- No force unwrap/force try unless explicitly allowed.
- Correct use of concurrency primitives and isolation boundaries.
- UI updates happen on the main thread (@MainActor / DispatchQueue.main).
- DocC is provided (///) for functions and methods.
- Inline comments are in English.

## RAG-grounding checks
- Facts derived from RAG must be cited via chunk number or URL.
- Unverified details must be explicitly marked as interpretation.
- If RAG has no relevant fragments, the answer must reflect that.
