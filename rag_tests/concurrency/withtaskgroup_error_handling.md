# withTaskGroup and error handling in Swift concurrency

Platform: iOS
Framework: Swift
MinOS: iOS 15
Difficulty: advanced
Concept Mode: all
RAG Strict: true

## Question

You need to run several independent async operations in parallel and aggregate their results.
Explain:

- how to use `withTaskGroup` and `withThrowingTaskGroup` to run child tasks concurrently;
- in what order results are produced by the group's iterator;
- how errors from child tasks are propagated and how remaining tasks are cancelled;
- when to choose `withTaskGroup` vs `withThrowingTaskGroup`.

## Expected Concepts

- withTaskGroup
- withThrowingTaskGroup
- TaskGroup iterator
- cancellation
- error propagation

## RAG Requirement

The answer must reference Swift concurrency documentation on task groups and iterators.

## Notes

Verifies understanding of structured concurrency and task groups in Swift.

