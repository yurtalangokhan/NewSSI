import { SvgAlertTriangle } from "@opal/icons";
import Text from "@/refresh-components/texts/Text";

interface SearchNoticeProps {
  children: React.ReactNode;
}

/** A warning above the results, such as a collection that failed. */
export default function SearchNotice({ children }: SearchNoticeProps) {
  return (
    <div className="flex items-center gap-2 rounded-12 bg-status-warning-01 px-3 py-2">
      <SvgAlertTriangle className="h-4 w-4 shrink-0 stroke-status-text-warning-05" />
      <Text as="p" secondaryBody text04>
        {children}
      </Text>
    </div>
  );
}
