import { useTranslation } from "react-i18next";
import { BasicClickable } from "@/components/BasicClickable";
import { OnyxDocument } from "@/lib/search/interfaces";
import { FiBook } from "react-icons/fi";

export function SelectedDocuments({
  selectedDocuments,
}: {
  selectedDocuments: OnyxDocument[];
}) {
  const { t } = useTranslation("common", { keyPrefix: "selectedDocuments" });
  if (selectedDocuments.length === 0) {
    return null;
  }

  return (
    <BasicClickable>
      <div className="flex text-xs max-w-md overflow-hidden">
        <FiBook className="my-auto mr-1" />{" "}
        <div className="w-fit whitespace-nowrap">
          {t("chattingWith", { count: selectedDocuments.length })}
        </div>
      </div>
    </BasicClickable>
  );
}
