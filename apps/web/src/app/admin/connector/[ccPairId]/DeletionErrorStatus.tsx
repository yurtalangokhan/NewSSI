import { FiInfo } from "react-icons/fi";
import { useTranslation } from "react-i18next";
import Text from "@/refresh-components/texts/Text";

export default function DeletionErrorStatus({
  deletion_failure_message,
}: {
  deletion_failure_message: string;
}) {
  const { t } = useTranslation("common", { keyPrefix: "admin.deletionError" });
  return (
    <div className="mt-2 rounded-md border border-error-300 bg-error-50 p-4 text-error-600 max-w-3xl">
      <div className="flex items-center">
        <Text as="h3" className="text-base font-medium">
          {t("title")}
        </Text>
        <div className="ml-2 relative group">
          <FiInfo className="h-4 w-4 text-error-600 cursor-help" />
          <div className="absolute z-10 w-64 p-2 mt-2 text-sm bg-white rounded-md shadow-lg opacity-0 group-hover:opacity-100 transition-opacity duration-300 border border-background-200">
            {t("tooltip")}
          </div>
        </div>
      </div>
      <div className="mt-2 text-sm">
        <Text as="p">{deletion_failure_message}</Text>
      </div>
    </div>
  );
}
