# URLSession + UIKit — updating UI on the main thread

Platform: iOS
Framework: UIKit
MinOS: iOS 15
Difficulty: intermediate
Concept Mode: all
RAG Strict: true

## Question

In a `UIViewController`, you start a network request using `URLSession` or async-await
to load data and update labels and table views. Explain:

- why UI updates must happen on the main thread;
- how to correctly dispatch back to the main thread when using completion handlers;
- how to correctly use `@MainActor` / `Task` with async-await to keep UI code safe;
- typical bugs when updating UIKit views from background queues.

## Expected Concepts

- main thread
- DispatchQueue.main
- @MainActor
- URLSession
- completion handler
- async-await
- data race

## RAG Requirement

The answer must reference Apple documentation about UIKit thread-safety and
updating views on the main thread.

## Notes

Verifies that the model consistently enforces main-thread UI updates with both
callbacks and async-await.

