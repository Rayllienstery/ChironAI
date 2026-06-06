# Modal presentations and adaptive presentation styles in UIKit

Platform: iOS
Framework: UIKit
MinOS: iOS 15
Difficulty: intermediate
Concept Mode: all
RAG Strict: false

## Question

You present view controllers modally over a `UINavigationController` using different
presentation styles (page sheet, full screen, form sheet, overCurrentContext).
Explain:

- how modal presentation styles affect the underlying view controller hierarchy;
- how adaptive presentation works on iPhone vs iPad;
- how to correctly dismiss modals and notify coordinators or delegates;
- common mistakes (presenting from the wrong controller, stacking multiple modals, broken dismissal logic).

## Expected Concepts

- modal presentation
- UIModalPresentationStyle
- adaptive presentation
- dismiss
- presentingViewController
- presentedViewController

## RAG Requirement

The answer should align with UIKit documentation on modal presentations and adaptive behaviors.

## Notes

Covers more subtle aspects of modal navigation that a Senior iOS Dev should know.

