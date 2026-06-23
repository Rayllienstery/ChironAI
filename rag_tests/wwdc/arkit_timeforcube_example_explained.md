# ARKit + RealityKit \"TimeForCube\" example explained

Platform: visionOS
Framework: RealityKit
MinOS: visionOS 1.0
Difficulty: advanced
Rag Required: no
Concept Mode: all
RAG Strict: true

## Question

The \"Meet ARKit for spatial computing\" WWDC session walks through a sample app sometimes called \"TimeForCube\" that combines ARKit data providers with RealityKit.  
Explain the overall architecture of this example:

- how the ARKit session is configured (which providers are used and for what: world tracking, scene reconstruction, hand tracking);
- how scene reconstruction meshes are converted into colliders that RealityKit can use for physics and gestures;
- how fingertip colliders from `HandTrackingProvider` are created and used to push cubes around;
- how spatial tap gestures are used to spawn cubes above the tapped location in the scene.

Provide a concise outline (pseudo-code is fine) that shows:

1. Creating the ARKit session and providers.  
2. Creating RealityKit entities for scene mesh colliders and fingertip colliders.  
3. Handling a spatial tap gesture to add a cube entity into the scene.

## Expected Concepts

- ARKit session
- data providers
- scene colliders
- fingertip colliders
- RealityKit entities
- spatial tap gesture

## RAG Requirement

The answer should reflect the specific structure and data flow of the WWDC \"TimeForCube\" ARKit + RealityKit example, not a generic ARKit app.

## Notes

This test is intended to retrieve detailed WWDC content describing the immersive cube example.*** End Patch
