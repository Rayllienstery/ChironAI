# SwiftUI macOS window placement and behavior

Platform: macOS
Framework: SwiftUI
MinOS: macOS 15
Difficulty: intermediate
Rag Required: no
Concept Mode: all
RAG Strict: true

## Question

In the WWDC session \"Tailor macOS windows with SwiftUI\" Apple shows how to customize macOS windows using new SwiftUI scene APIs.  
Explain:

- how to use `defaultWindowPlacement` to choose the initial size and position of a window based on the content and display visible rect;
- how `windowIdealPlacement` differs from `defaultWindowPlacement` and how it affects the Zoom behavior;
- how to customize window behaviors such as minimize and state restoration (for example for a custom About window);
- how to remove or restyle the toolbar background while preserving the window title for accessibility and menus.

Provide a SwiftUI example that configures:

1. A main window with a custom toolbar appearance.  
2. An About window that has a fixed size, custom material background, disabled minimize control and disabled state restoration.  
3. A video player window that uses `defaultWindowPlacement` and `windowIdealPlacement` to respect video size and screen bounds.

## Expected Concepts

- defaultWindowPlacement
- windowIdealPlacement
- containerBackground
- windowMinimizeBehavior
- restorationBehavior
- toolbar background

## RAG Requirement

The answer should rely on details from the WWDC macOS windows SwiftUI session, not just on generic SwiftUI documentation.

## Notes

This test is aimed at WWDC content that explains new window customization APIs on macOS (Sequoia) using SwiftUI scenes.*** End Patch
