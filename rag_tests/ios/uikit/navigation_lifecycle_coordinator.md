# UINavigationController + Coordinator — lifecycle and state

Platform: iOS
Framework: UIKit
MinOS: iOS 15
Difficulty: intermediate
Concept Mode: all
RAG Strict: true

## Question

You use a coordinator pattern on top of `UINavigationController` to manage screen flow.
Explain:

- how `UIViewController` lifecycle (`viewDidLoad`, `viewWillAppear`, `viewDidAppear`) interacts with push/pop operations;
- where to trigger one-time setup, where to refresh data when returning to a screen;
- how a coordinator should create and wire view controllers without leaking them;
- common mistakes (e.g. retaining the coordinator strongly from view controllers, double-pushing the same view controller).

## Expected Concepts

- UINavigationController
- coordinator
- viewDidLoad
- viewWillAppear
- viewDidAppear
- retain cycle
- strong reference
- weak reference

## RAG Requirement

The answer must reference UIKit documentation about navigation controllers
and view controller containment / lifecycle, and clearly separate responsibilities
between view controllers and the coordinator.

## Notes

Checks deeper understanding of UIKit navigation + coordinator patterns and lifecycle.

