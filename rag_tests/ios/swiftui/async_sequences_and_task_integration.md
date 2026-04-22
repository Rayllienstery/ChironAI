# Async sequences and Task integration in SwiftUI views

Platform: iOS
Framework: SwiftUI
MinOS: iOS 16
Difficulty: advanced
Concept Mode: all
RAG Strict: true

## Question

You expose updates from a data source as an `AsyncSequence` and want to consume them in a SwiftUI view.
Explain:

- how to use `.task` or `Task` to iterate over an `AsyncSequence` in a view;
- how to cancel the work when the view disappears;
- how to safely update SwiftUI state from the async loop;
- how this compares to using Combine publishers with `.onReceive`.

## Expected Concepts

- AsyncSequence
- .task
- cancellation
- @State
- onReceive
- Combine

## RAG Requirement

The answer must reference Swift and SwiftUI documentation for async sequences, tasks and Combine bridging.

## Notes

Tests deep understanding of async data streams in SwiftUI.

