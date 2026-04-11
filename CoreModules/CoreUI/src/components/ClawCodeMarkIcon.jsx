import React from 'react';

/**
 * Theme-aware Claw Code mark (Material 3 tokens). Replaces a static PNG so light/dark/accent track the app.
 */
export default function ClawCodeMarkIcon({ className = '', title, ...rest }) {
  return (
    <svg
      className={`notification-center-claw-svg ${className}`.trim()}
      viewBox="0 0 48 48"
      width={26}
      height={26}
      aria-hidden={title ? undefined : true}
      role={title ? 'img' : undefined}
      {...rest}
    >
      {title ? <title>{title}</title> : null}
      {/* Top rail — neutral rail + primary accent (M3 emphasis) */}
      <path className="claw-svg-rail-end" d="M6 8h14v4H6z" />
      <path className="claw-svg-rail-accent" d="M20 8h8v4h-8z" />
      <path className="claw-svg-rail-end" d="M28 8h14v4H28z" />
      {/* Stem */}
      <path className="claw-svg-stem" d="M21 12h6v7h-6z" />
      {/* Housing — tonal surface (M3 container) */}
      <rect className="claw-svg-housing" x="14" y="18.5" width="20" height="12.5" rx="3" />
      {/* Central joint */}
      <circle className="claw-svg-pivot" cx="24" cy="32" r="5.5" />
      {/* Arms — tertiary accent */}
      <path
        className="claw-svg-arm claw-svg-arm--left"
        d="M24 32 L13 40 l-2 6h4l2.5-4.5L24 35.5z"
      />
      <path
        className="claw-svg-arm claw-svg-arm--right"
        d="M24 32 L35 40 l2 6h-4l-2.5-4.5L24 35.5z"
      />
    </svg>
  );
}
