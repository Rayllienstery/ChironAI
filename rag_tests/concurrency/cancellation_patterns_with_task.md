# Cancellation patterns with Task in Swift concurrency

Platform: iOS
Framework: Swift
MinOS: iOS 15
Difficulty: intermediate
Concept Mode: all
RAG Strict: false

## Question

You start long-running async operations from a view model and need to cancel them
when the user navigates away or triggers a new request.
Explain:

- how task cancellation works in Swift concurrency;
- how to cooperatively check for cancellation inside async functions;
- patterns for storing and cancelling tasks from view models;
- common mistakes (ignoring cancellation, leaking tasks, cancelling from the wrong context).

## Expected Concepts

- Task
- cancellation
- Task.isCancelled
- cooperative cancellation
- lifetime management

## RAG Requirement

The answer should align with Swift concurrency documentation on task cancellation.

## Notes

Tests practical knowledge of cancellation patterns critical for responsive apps.

