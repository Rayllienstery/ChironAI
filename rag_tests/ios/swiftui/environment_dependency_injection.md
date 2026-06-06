# Using Environment and EnvironmentObject for dependency injection in SwiftUI

Platform: iOS
Framework: SwiftUI
MinOS: iOS 16
Difficulty: intermediate
Concept Mode: all
RAG Strict: false

## Question

You structure a SwiftUI app using dependency injection for services (networking, analytics, feature flags).
Explain:

- when to use `@EnvironmentObject` versus custom `@Environment` keys;
- how to inject dependencies at the root of the view tree and access them in children;
- how to keep dependencies testable and override them in previews and tests;
- common mistakes (creating services inside views, overusing singletons).

## Expected Concepts

- @Environment
- @EnvironmentObject
- dependency injection
- previews
- testability

## RAG Requirement

The answer should align with SwiftUI documentation on environment values and environment objects.

## Notes

Focuses on architectural SwiftUI patterns expected of a Senior iOS Dev.

