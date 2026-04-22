# BGTaskScheduler and app lifecycle integration (UIKit app)

Platform: iOS
Framework: UIKit
MinOS: iOS 15
Difficulty: advanced
Concept Mode: all
RAG Strict: false

## Question

You want to schedule periodic background refresh for a UIKit-based app using `BGTaskScheduler`.
Explain:

- how to register background tasks and request them from the app;
- how app lifecycle events (foreground/background, termination) affect scheduling;
- how to design the update pipeline so it is safe to run in the background (no UI work, only model updates);
- common pitfalls (doing too much work, missing expiration handlers, relying on exact timing).

## Expected Concepts

- BGTaskScheduler
- background refresh
- app lifecycle
- expiration handler
- background-safe work

## RAG Requirement

The answer should align with Apple documentation on background tasks in iOS.

## Notes

Targets more advanced UIKit/app lifecycle concerns for Senior-level understanding.

