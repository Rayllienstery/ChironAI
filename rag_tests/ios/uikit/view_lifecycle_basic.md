# UIViewController lifecycle — configuring UI safely

Platform: iOS
Framework: UIKit
MinOS: iOS 15
Difficulty: intermediate
Concept Mode: all
RAG Strict: true

## Question

You have a `UIViewController` that configures its subviews and loads data from the network.
Explain which lifecycle methods (`viewDidLoad`, `viewWillAppear`, `viewDidAppear`, `viewWillLayoutSubviews`)
are appropriate for:
- creating and configuring subviews,
- starting network requests,
- triggering one‑time analytics events,
- adjusting layout‑dependent properties.

Point out common mistakes when accessing `view` or layout‑dependent properties too early.

## Expected Concepts

- viewDidLoad
- viewWillAppear
- viewDidAppear
- viewWillLayoutSubviews
- creating subviews
- layout-dependent configuration
- avoid early access to view

## RAG Requirement

The answer must reference UIKit documentation about the view controller lifecycle and clearly map
each lifecycle method to its recommended responsibilities.

## Notes

Checks that the model understands the basic UIViewController lifecycle and does not recommend
doing layout or network work in inappropriate places (like init or before the view is loaded).

