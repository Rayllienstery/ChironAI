export default function ChironaiLogo({ size = 32, className, ...props }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 512 512"
      width={size}
      height={size}
      role="img"
      aria-label="ChironAI"
      className={className}
      {...props}
    >
      <line
        x1="108"
        y1="256"
        x2="404"
        y2="256"
        stroke="#2D3436"
        strokeWidth="10"
        strokeLinecap="round"
      />
      <path
        d="M 306 132 A 124 124 0 1 0 306 380"
        fill="none"
        stroke="#2D3436"
        strokeWidth="52"
        strokeLinecap="round"
      />
      <circle cx="108" cy="256" r="28" fill="#D35400" />
      <circle cx="404" cy="256" r="28" fill="#0B7285" />
      <circle cx="268" cy="256" r="40" fill="#F59F00" />
    </svg>
  );
}
