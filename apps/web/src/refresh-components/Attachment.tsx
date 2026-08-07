import Text from "@/refresh-components/texts/Text";
import { Button } from "@opal/components";
import { SvgFileText, SvgMaximize2 } from "@opal/icons";
import { useTranslation } from "react-i18next";
export interface AttachmentsProps {
  fileName: string;
  open?: () => void;
}

export default function Attachments({ fileName, open }: AttachmentsProps) {
  const { t } = useTranslation("common", { keyPrefix: "common" });
  return (
    <div className="flex items-center border bg-background-tint-00 rounded-12 p-1 gap-1">
      <div className="p-2 bg-background-tint-01 rounded-08">
        <SvgFileText className="w-[1.25rem] h-[1.25rem] stroke-text-02" />
      </div>
      <div className="flex flex-col px-2">
        <Text as="p" secondaryAction>
          {fileName}
        </Text>
        <Text as="p" secondaryBody text03>
          {t("document")}
        </Text>
      </div>

      {open && (
        <Button
          aria-label={t("attachment.expandDocumentAriaLabel")}
          onClick={open}
          icon={SvgMaximize2}
          prominence="tertiary"
          size="sm"
        />
      )}
    </div>
  );
}
