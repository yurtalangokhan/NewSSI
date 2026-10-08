import type { IconProps } from "@opal/types";

interface LayoutTreeProps extends IconProps {
  horizontal?: boolean;
}

function LayoutTree({ horizontal, size = 16, ...props }: LayoutTreeProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      {...props}
    >
      <g transform={horizontal ? "rotate(-90 12 12)" : undefined}>
        <rect x="9" y="2" width="6" height="5" rx="1" />
        <path d="M12 7v5M5 17v-5h14v5" />
        <rect x="2" y="17" width="6" height="5" rx="1" />
        <rect x="16" y="17" width="6" height="5" rx="1" />
      </g>
    </svg>
  );
}
export function SvgLayoutVertical(props: IconProps) {
  return <LayoutTree {...props} />;
}
export function SvgLayoutHorizontal(props: IconProps) {
  return <LayoutTree {...props} horizontal />;
}
