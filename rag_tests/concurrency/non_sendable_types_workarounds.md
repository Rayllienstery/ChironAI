# Working with non-Sendable types in concurrent Swift code

Platform: iOS
Framework: Swift
MinOS: iOS 15
Difficulty: advanced
Concept Mode: all
RAG Strict: false

## Question

You have legacy reference types that are not Sendable (e.g. UIKit, Core Data objects),
but you need to use them in async code.
Explain:

- why directly sharing non-Sendable reference types across actors or threads is unsafe;
- patterns for wrapping non-Sendable types behind actors or MainActor-isolated APIs;
- when `@unchecked Sendable` is acceptable and how to document its invariants;
- common pitfalls (data races, crashes due to unsafely shared mutable state).

## Expected Concepts

- non-Sendable
- MainActor
- actor wrapper
- @unchecked Sendable
- data race

## RAG Requirement

The answer should align with Swift concurrency and Sendable guidelines.

## Notes

Checks practical strategies for dealing with legacy non-Sendable APIs.

