# Migrating to strict concurrency in Swift 6

Platform: iOS
Framework: Swift
MinOS: iOS 17
Difficulty: advanced
Concept Mode: all
RAG Strict: false

## Question

You migrate an existing iOS module to Swift 6 with strict concurrency checking enabled.
Explain:

- how the compiler enforces Sendable and actor isolation rules;
- how to address common concurrency warnings (non-Sendable types, shared mutable state);
- when to use `@preconcurrency` and `@unchecked Sendable` as escape hatches, and what risks they carry;
- a safe step-by-step strategy for enabling strict concurrency in a codebase.

## Expected Concepts

- strict concurrency
- Sendable diagnostics
- @preconcurrency
- @unchecked Sendable
- migration strategy

## RAG Requirement

The answer should align with Swift 6 concurrency guidelines and migration docs.

## Notes

Checks Senior-level understanding of evolving Swift concurrency model and practical migration.

