import type { IconProps } from "@opal/types";

/** The square grid the rail and toolbar icons are drawn on. */
const SQUARE_GRID = "0 0 24 24";
/** The taller page grid shared by every file-type icon. */
const PAGE_GRID = "0 0 16 20";
/** A document page with a folded corner, in the page grid. */
const PAGE_OUTLINE =
  "M9.66634 1.6665H2.99967C2.55765 1.6665 2.13372 1.8421 1.82116 2.15466C1.5086 2.46722 1.33301 2.89114 1.33301 3.33317V16.6665C1.33301 17.1085 1.5086 17.5325 1.82116 17.845C2.13372 18.1576 2.55765 18.3332 2.99967 18.3332H12.9997C13.4417 18.3332 13.8656 18.1576 14.1782 17.845C14.4907 17.5325 14.6663 17.1085 14.6663 16.6665V6.6665M9.66634 1.6665L14.6663 6.6665M9.66634 1.6665L9.66634 6.6665L14.6663 6.6665";

interface StrokeIconProps extends IconProps {
  children: React.ReactNode;
}

function StrokeIcon({
  size = 16,
  viewBox = SQUARE_GRID,
  children,
  ...props
}: StrokeIconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox={viewBox}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      {...props}
    >
      {children}
    </svg>
  );
}

/** Stacked layers: hybrid search over documents and the knowledge graph. */
export function SvgLayers(props: IconProps) {
  return (
    <StrokeIcon {...props}>
      <path d="m12 3 9 5-9 5-9-5z" />
      <path d="m3 13 9 5 9-5" />
    </StrokeIcon>
  );
}

/** Bulleted rows: a list view. */
export function SvgListRows(props: IconProps) {
  return (
    <StrokeIcon {...props}>
      <path d="M8 6h13M8 12h13M8 18h13" />
      <path d="M3.5 6h.01M3.5 12h.01M3.5 18h.01" strokeWidth="2.5" />
    </StrokeIcon>
  );
}

/** A document page alone: the tile shown when no file type is known. */
export function SvgFile(props: IconProps) {
  return (
    <StrokeIcon viewBox={PAGE_GRID} {...props}>
      <path d={PAGE_OUTLINE} />
    </StrokeIcon>
  );
}

/** A PDF: a page carrying a type badge. */
export function SvgFilePdf(props: IconProps) {
  return (
    <StrokeIcon viewBox={PAGE_GRID} {...props}>
      <path d={PAGE_OUTLINE} />
      <rect x="4.667" y="10.5" width="6.666" height="4" rx="1" />
    </StrokeIcon>
  );
}

/** A word-processor file: a page of paragraphs. */
export function SvgFileDoc(props: IconProps) {
  return (
    <StrokeIcon viewBox={PAGE_GRID} {...props}>
      <path d={PAGE_OUTLINE} />
      <path d="M4.667 9.833h6.666M4.667 12.5h6.666M4.667 15.167h3.333" />
    </StrokeIcon>
  );
}

/** A workbook: a page of cells. */
export function SvgFileXls(props: IconProps) {
  return (
    <StrokeIcon viewBox={PAGE_GRID} {...props}>
      <path d={PAGE_OUTLINE} />
      <rect x="4.667" y="9.833" width="6.666" height="5.334" rx="1" />
      <path d="M8 9.833v5.334M4.667 12.5h6.666" />
    </StrokeIcon>
  );
}

/** A delimited data file: a page holding a single row of columns. */
export function SvgFileCsv(props: IconProps) {
  return (
    <StrokeIcon viewBox={PAGE_GRID} {...props}>
      <path d={PAGE_OUTLINE} />
      <rect x="4.667" y="11" width="6.666" height="3.334" rx="1" />
      <path d="M6.889 11v3.334M9.111 11v3.334" />
    </StrokeIcon>
  );
}

/** A slide deck: a page showing a screen above its stand. */
export function SvgFilePpt(props: IconProps) {
  return (
    <StrokeIcon viewBox={PAGE_GRID} {...props}>
      <path d={PAGE_OUTLINE} />
      <rect x="4.667" y="9.833" width="6.666" height="4.334" rx="1" />
      <path d="M8 14.167V15.5M6.667 15.5h2.666" />
    </StrokeIcon>
  );
}

/** Plain text: a page of running lines. */
export function SvgFileTxt(props: IconProps) {
  return (
    <StrokeIcon viewBox={PAGE_GRID} {...props}>
      <path d={PAGE_OUTLINE} />
      <path d="M4.667 10.5h6.666M4.667 13.5h3.333" />
    </StrokeIcon>
  );
}
