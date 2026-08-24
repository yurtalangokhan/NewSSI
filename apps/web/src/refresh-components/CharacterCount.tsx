import { useTranslation } from "react-i18next";
import Text from "@/refresh-components/texts/Text";
export interface CharacterCountProps {
  value: string;
  limit: number;
}
export default function CharacterCount({ value, limit }: CharacterCountProps) {
  const { t } = useTranslation();
  const length = value?.length || 0;
  return (
    <Text text03 secondaryBody>
      {t("common.characterCount", { length, limit })}
    </Text>
  );
}
