# UIScrollView, content insets and keyboard avoiding

Platform: iOS
Framework: UIKit
MinOS: iOS 15
Difficulty: intermediate
Concept Mode: all
RAG Strict: false

## Question

You have a form inside a `UIScrollView` that should remain visible when the keyboard appears.
Explain:

- how to adjust content insets / scroll indicators in response to keyboard notifications;
- how to coordinate with Auto Layout and safe area insets;
- how to avoid layout glitches when rotating the device or dismissing the keyboard;
- alternatives using `UIScrollView.keyboardDismissMode` and input accessory views.

## Expected Concepts

- UIScrollView
- contentInset
- keyboard notifications
- safe area
- Auto Layout

## RAG Requirement

The answer should align with UIKit documentation around scroll views, safe area and keyboard handling.

## Notes

Checks more applied UIKit knowledge beyond basic view controllers.

