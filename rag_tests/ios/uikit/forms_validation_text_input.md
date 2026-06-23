# UIKit forms and text input validation

Platform: iOS
Framework: UIKit
MinOS: iOS 15
Difficulty: intermediate
Concept Mode: all
RAG Strict: false

## Question

You build a multi-field form using `UITextField` and `UITextView` inside a `UIViewController`.
Explain:

- how to use delegates (e.g. `UITextFieldDelegate`) to validate input as the user types;
- how to manage the first responder chain (Next/Done) and the keyboard;
- where to perform final form validation before submitting;
- common pitfalls (force-unwrapping text, relying on invalid states, not updating UI error states).

## Expected Concepts

- UITextField
- UITextFieldDelegate
- first responder
- keyboard
- validation
- error state

## RAG Requirement

The answer should align with UIKit documentation on text input and delegates.

## Notes

Checks that the model can reason about practical patterns for building forms in UIKit.

