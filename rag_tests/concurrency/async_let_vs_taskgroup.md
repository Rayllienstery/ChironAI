# async let vs task groups in Swift concurrency

Platform: iOS
Framework: Swift
MinOS: iOS 15
Difficulty: intermediate
Concept Mode: all
RAG Strict: false

## Question

You need to run several async operations in parallel and aggregate their results.
Explain:

- when to use `async let` bindings versus `withTaskGroup` / `withThrowingTaskGroup`;
- how cancellation and error propagation differ between these approaches;
- how structured concurrency ensures that child tasks complete before the parent function returns;
- common pitfalls (starting too many tasks, mixing patterns incorrectly).

## Expected Concepts

- async let
- withTaskGroup
- withThrowingTaskGroup
- structured concurrency
- cancellation
- error propagation

## RAG Requirement

The answer should align with Swift concurrency documentation on async let and task groups.

## Notes

Helps distinguish two core patterns for parallel work in Swift.

