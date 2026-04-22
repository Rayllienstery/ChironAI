# SwiftUI accessibility drag and drop points

Platform: iOS
Framework: SwiftUI
MinOS: iOS 18
Difficulty: advanced
Rag Required: no
Concept Mode: all
RAG Strict: true

## Question

In the \"Catch up on accessibility in SwiftUI\" WWDC session Apple shows how to make drag and drop interactions accessible.  
Explain:

- what accessibility drag and drop points are and why they are needed when a view has multiple logical drop locations;
- how to define accessibility drag points and drop points on a view so that VoiceOver can target them individually;
- how this was used in the example where sounds are dragged to create a custom alert for a contact (multiple drop points with labels like \"set sound 3\");
- when you might want to supplement drag-and-drop with custom actions for accessibility.

Provide a short SwiftUI-oriented explanation (no need for full code) of how you would apply these APIs to a view that has three independent drop targets.

## Expected Concepts

- accessibility drag point
- accessibility drop point
- VoiceOver
- multiple drop locations
- custom actions
- drag and drop

## RAG Requirement

The answer should be grounded in the WWDC SwiftUI accessibility session’s drag-and-drop example.

## Notes

This test aims to pull WWDC content about accessible drag and drop in SwiftUI.*** End Patch
