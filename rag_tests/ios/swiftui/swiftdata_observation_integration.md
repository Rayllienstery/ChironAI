# Integrating SwiftData with Observation in SwiftUI

Platform: iOS
Framework: SwiftUI
MinOS: iOS 17
Difficulty: advanced
Concept Mode: all
RAG Strict: true

## Question

You migrate a screen from Core Data + `NSFetchedResultsController` to SwiftData.
Explain:

- how to declare a SwiftData model with `@Model` and use it with `ModelContainer` / `ModelContext`;
- how SwiftData integrates with the Observation framework so that SwiftUI views update when data changes;
- how to perform inserts/updates/deletes in a way that keeps UI and storage in sync;
- how to scope `ModelContext` correctly for a SwiftUI view hierarchy.

## Expected Concepts

- SwiftData
- @Model
- ModelContainer
- ModelContext
- Observation
- SwiftUI integration

## RAG Requirement

The answer must reference SwiftData documentation and the SwiftUI integration
section (how model changes propagate to views).

## Notes

Verifies understanding of modern persistence + state flow in SwiftUI.

