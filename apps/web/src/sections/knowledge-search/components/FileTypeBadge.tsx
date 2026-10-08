import type { IconProps } from "@opal/types";
import {
  SvgFile,
  SvgFileCsv,
  SvgFileDoc,
  SvgFilePdf,
  SvgFilePpt,
  SvgFileText,
  SvgFileTxt,
  SvgFileXls,
} from "@/icons";
import { cn } from "@/lib/utils";

const FILE_TYPE_TONES: Record<string, string> = {
  pdf: "bg-theme-orange-01 text-theme-orange-05",
  doc: "bg-theme-blue-01 text-theme-blue-05",
  docx: "bg-theme-blue-01 text-theme-blue-05",
  xls: "bg-theme-green-01 text-theme-green-05",
  xlsx: "bg-theme-green-01 text-theme-green-05",
  csv: "bg-theme-green-01 text-theme-green-05",
  tsv: "bg-theme-green-01 text-theme-green-05",
  ppt: "bg-theme-amber-01 text-theme-amber-05",
  pptx: "bg-theme-amber-01 text-theme-amber-05",
};

/** The file's own type icon, so the badge reads as a logo, not initials. */
const FILE_TYPE_ICONS: Record<string, React.ComponentType<IconProps>> = {
  pdf: SvgFilePdf,
  doc: SvgFileDoc,
  docx: SvgFileDoc,
  xls: SvgFileXls,
  xlsx: SvgFileXls,
  csv: SvgFileCsv,
  tsv: SvgFileCsv,
  ppt: SvgFilePpt,
  pptx: SvgFilePpt,
  txt: SvgFileTxt,
  md: SvgFileText,
};

const NEUTRAL_TONE = "bg-background-tint-03 text-text-03";

interface FileTypeBadgeProps {
  fileType: string | null;
}

/** A document's file type as a small tinted tile with its type icon. */
export default function FileTypeBadge({ fileType }: FileTypeBadgeProps) {
  const tone = (fileType && FILE_TYPE_TONES[fileType]) || NEUTRAL_TONE;
  const Icon = (fileType && FILE_TYPE_ICONS[fileType]) || SvgFile;
  return (
    <span
      title={(fileType ?? "doc").toUpperCase()}
      className={cn(
        "flex h-[1.625rem] w-[1.625rem] shrink-0 items-center justify-center rounded-08",
        tone
      )}
      aria-hidden
    >
      <Icon className="h-4 w-4" />
    </span>
  );
}
