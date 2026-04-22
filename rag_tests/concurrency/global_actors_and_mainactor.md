# Global actors and @MainActor in Swift concurrency

Platform: iOS
Framework: Swift
MinOS: iOS 15
Difficulty: advanced
Concept Mode: all
RAG Strict: true

## Question

You design an API that must always execute on the main thread and expose it to async callers.
Explain:

- how to use `@MainActor` on types and functions to guarantee main-thread isolation;
- how global actors work and how they differ from regular actors;
- how to call `@MainActor` APIs from background tasks safely;
- common pitfalls (unintentional cross-actor calls, blocking the main thread).

## Expected Concepts

- @MainActor
- global actor
- actor isolation
- cross-actor call
- main thread

## RAG Requirement

The answer must reference Swift concurrency documentation on global actors and MainActor.

## Notes

Tests nuanced understanding of UI-related concurrency guarantees in Swift.

