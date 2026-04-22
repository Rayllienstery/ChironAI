# Using @Observable with UIKit and UIObservationTrackingEnabled

Platform: iOS
Framework: UIKit
MinOS: iOS 18
Difficulty: advanced
Concept Mode: all
RAG Strict: true

## Question

You have a `UIViewController` that uses an `@Observable` model to drive its UI
on iOS 18 with `UIObservationTrackingEnabled` turned on.
Explain:

- how UIKit automatically tracks reads of observable properties in lifecycle methods
  like `viewWillLayoutSubviews()` and `updateProperties()`;
- why all writes to the observable model must happen on the main actor;
- what happens if you mutate the model from `Task.detached` or a background queue;
- how to structure the controller so that observation-based updates are reliable.

## Expected Concepts

- @Observable
- UIObservationTrackingEnabled
- viewWillLayoutSubviews()
- updateProperties()
- MainActor
- Task.detached
- data race

## RAG Requirement

The answer must reference Apple documentation about Observation tracking in UIKit
(`UIObservationTrackingEnabled`, `viewWillLayoutSubviews`, `updateProperties`)
and explain the main-actor requirement for mutations.

## Notes

Tests understanding of modern Observation + UIKit integration and concurrency rules.

