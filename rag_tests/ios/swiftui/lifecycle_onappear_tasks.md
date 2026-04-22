# SwiftUI view lifecycle with onAppear, onDisappear and .task

Platform: iOS
Framework: SwiftUI
MinOS: iOS 15
Difficulty: intermediate
Concept Mode: all
RAG Strict: true

## Question

You have a SwiftUI screen that needs to load data when it appears and cancel
work when it disappears. Explain:

- when to use `onAppear` / `onDisappear` versus `.task(id:)` for starting async work;
- how cancellation works for `.task` modifiers when the view goes off-screen;
- where to update view state to avoid glitches or double-fetching;
- common pitfalls (starting work in `init`, relying on body evaluation order, ignoring cancellation).

## Expected Concepts

- onAppear
- onDisappear
- .task
- cancellation
- SwiftUI lifecycle

## RAG Requirement

The answer must reference SwiftUI documentation on lifecycle and task modifiers
and correctly describe their behavior.

## Notes

Checks knowledge of modern SwiftUI lifecycle patterns with async work.

