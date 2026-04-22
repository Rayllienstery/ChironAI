# Child view controllers and view controller containment

Platform: iOS
Framework: UIKit
MinOS: iOS 15
Difficulty: intermediate
Concept Mode: all
RAG Strict: true

## Question

You build a composite screen that embeds several child view controllers inside a container
view controller. Explain:

- how to correctly add and remove child view controllers (`addChild`, `willMove`, `didMove`);
- where to set up child views and constraints;
- how containment affects the lifecycle of child controllers;
- common mistakes (forgetting `didMove(toParent:)`, leaking children, breaking layout).

## Expected Concepts

- child view controller
- addChild
- didMove(toParent:)
- willMove(toParent:)
- containment
- lifecycle
- Auto Layout

## RAG Requirement

The answer must reference Apple documentation on view controller containment
and show the correct sequence of containment calls.

## Notes

Checks understanding of advanced UIKit composition patterns.

