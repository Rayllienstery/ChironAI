# ARC and object lifetimes in async Swift code

Platform: iOS
Framework: Swift
MinOS: iOS 15
Difficulty: advanced
Concept Mode: all
RAG Strict: false

## Question

You capture objects in async closures and tasks that may outlive the original scope.
Explain:

- how ARC manages object lifetimes when closures are stored and executed later;
- how to avoid retain cycles when capturing `self` in async closures and tasks;
- how cancellation interacts with object lifetimes and deinitialization;
- common pitfalls (dangling references, early deallocation, strong cycles).

## Expected Concepts

- ARC
- retain cycle
- weak / unowned
- async closure
- deinit

## RAG Requirement

The answer should align with Swift ARC and concurrency documentation.

## Notes

Combines memory management and concurrency, typical Senior-level concern.

