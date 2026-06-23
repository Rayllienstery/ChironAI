# Migrating from ObservableObject to @Observable in SwiftUI

Platform: iOS
Framework: SwiftUI
MinOS: iOS 17
Difficulty: intermediate
Concept Mode: all
RAG Strict: true

## Question

You have a SwiftUI screen that currently uses `ObservableObject` + `@Published` +
`@StateObject` / `@ObservedObject`. Explain how to migrate this screen to the
Observation framework with `@Observable` and `@State` / `@Bindable`:

- how to change the model type and remove `ObservableObject` / `@Published`;
- how to replace `@StateObject` / `@ObservedObject` with `@State` / `@Bindable`;
- how SwiftUI now tracks dependencies in `body` and when it re-renders the view;
- common migration pitfalls.

## Expected Concepts

- Observation framework
- @Observable
- ObservableObject
- @Published
- @State
- @Bindable
- dependency tracking

## RAG Requirement

The answer must reference Apple documentation on migrating from ObservableObject
to the Observable macro and highlight changes in dependency tracking.

## Notes

Validates that the model understands modern Observation-based SwiftUI state patterns.

