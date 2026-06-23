# Task vs Task.detached usage patterns in Swift concurrency

Platform: iOS
Framework: Swift
MinOS: iOS 15
Difficulty: advanced
Concept Mode: all
RAG Strict: false

## Question

You need to launch asynchronous work from a view model and from low-level utility code.
Explain:

- the difference between `Task {}` and `Task.detached {}` in terms of inheritance of priority, actor context and cancellation;
- when it is appropriate to use `Task.detached` versus avoiding it;
- how to structure code so that cancellation and lifetime of tasks are well-defined;
- common mistakes (leaking detached tasks, accessing UI state from detached tasks).

## Expected Concepts

- Task
- Task.detached
- priority
- actor context
- cancellation
- lifetime management

## RAG Requirement

The answer should align with Swift concurrency documentation on tasks.

## Notes

Tests deeper understanding of structured vs unstructured concurrency patterns.

