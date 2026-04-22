# Actor isolation and Sendable basics

Platform: iOS
Framework: Swift
MinOS: iOS 17
Difficulty: advanced
Concept Mode: all
RAG Strict: true

## Question

Explain:

- what “actor isolation” means in Swift;
- how `Sendable` and `@unchecked Sendable` relate to crossing isolation boundaries;
- when you need to mark types or closures as `Sendable`;
- why accessing non-Sendable reference types (including `@Observable` classes) from `Task.detached` can be unsafe.

Provide a small example with an actor that safely isolates its mutable state.

## Expected Concepts

- actor isolation
- Sendable
- @unchecked Sendable
- Task.detached
- MainActor
- data race

## RAG Requirement

The answer must rely on Swift concurrency / Sendable / actor documentation from Apple
and use correct terminology.

## Notes

Checks deep understanding of Swift 5.10/6 concurrency model and isolation rules.

