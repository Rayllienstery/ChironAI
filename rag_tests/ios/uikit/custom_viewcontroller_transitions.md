# Custom view controller transitions in UIKit

Platform: iOS
Framework: UIKit
MinOS: iOS 15
Difficulty: advanced
Concept Mode: all
RAG Strict: false

## Question

You want to implement a custom transition animation between two view controllers
using `UIViewControllerAnimatedTransitioning` and `UIViewControllerTransitioningDelegate`.
Explain:

- how to set up a custom transitioning delegate and animator object;
- how to animate presentation and dismissal using the transition context;
- how to handle interactive transitions (e.g. pan-to-dismiss) safely;
- common pitfalls (not calling `completeTransition`, inconsistent final states, memory leaks).

## Expected Concepts

- UIViewControllerAnimatedTransitioning
- UIViewControllerTransitioningDelegate
- transitionContext
- interactive transition
- completeTransition

## RAG Requirement

The answer should align with UIKit documentation on custom transitions.

## Notes

Tests more advanced UIKit animation and navigation customization knowledge.

