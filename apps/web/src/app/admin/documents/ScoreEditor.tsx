import { errorMessageFromUnknown } from "@/lib/api/errors";
import { useTranslation } from "react-i18next";
import { toast } from "@/hooks/useToast";
import { updateBoost } from "@/lib/api/domains/knowledge/api";
import { EditableValue } from "@/components/EditableValue";

export const ScoreSection = ({
  documentId,
  initialScore,
  refresh,
  consistentWidth = true,
}: {
  documentId: string;
  initialScore: number;
  refresh: () => void;
  consistentWidth?: boolean;
}) => {
  const { t } = useTranslation("common", { keyPrefix: "admin.scoreEditor" });
  const onSubmit = async (value: string) => {
    const numericScore = Number(value);
    if (isNaN(numericScore)) {
      toast.error(t("scoreMustBeNumber"));
      return false;
    }

    try {
      const errorMsg = await updateBoost(documentId, numericScore);
      if (errorMsg) {
        toast.error(errorMsg);
        return false;
      }
      toast.success(t("updatedScore"));
      refresh();
      return true;
    } catch (error) {
      toast.error(errorMessageFromUnknown(error));
      return false;
    }
  };

  return (
    <EditableValue
      initialValue={initialScore.toString()}
      onSubmit={onSubmit}
      consistentWidth={consistentWidth}
    />
  );
};
