# Error handling best practices in Swift

Platform: iOS
Framework: Swift
MinOS: iOS 15
Difficulty: advanced
Concept Mode: all
RAG Strict: false

## Question

You design an API layer for an iOS app and need to expose failures to callers.
Explain:

- when to use `throws` versus returning a `Result` type;
- how to structure error enums to be expressive but not leak low-level details;
- how to propagate errors through async call chains without losing context;
- common anti-patterns (overusing `try!`, swallowing errors, mixing error codes and thrown errors).

## Expected Concepts

- throws
- Result
- Error enum
- error propagation
- try!
- error handling

## RAG Requirement

The answer should align with Swift error handling guidelines and avoid unsafe patterns.

## Notes

Tests deeper understanding of Swift error handling design and best practices.

