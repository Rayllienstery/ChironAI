# SwiftUI widgets and AppIntents accessibility actions

Platform: iOS
Framework: SwiftUI
MinOS: iOS 18
Difficulty: intermediate
Rag Required: no
Concept Mode: all
RAG Strict: true

## Question

The SwiftUI accessibility WWDC session briefly touches on using **AppIntents** and accessibility actions inside widgets.  
Explain:

- how widgets can use AppIntents to create interactive controls like buttons and toggles;
- when you might want to add extra custom accessibility actions on top of the default intent-driven behavior;
- how this relates to the recommendation that some interactions (like \"magic tap\") should perform the most important action in the widget;
- any specific guidance given in the session about keeping widget accessibility simple and predictable.

You do not need to show complete widget code, but outline how you would design a widget that lets the user rate a beach and mark it as a favorite, including accessibility considerations.

## Expected Concepts

- AppIntents
- widget
- accessibility actions
- magic tap
- most important action
- SwiftUI

## RAG Requirement

The answer should be grounded in the WWDC SwiftUI accessibility session’s widget/AppIntents discussion.

## Notes

This test is meant to trigger WWDC content about combining AppIntents and accessibility actions in widgets.*** End Patch
