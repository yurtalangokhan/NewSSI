"use client";

import { memo } from "react";
import { useTranslation } from "react-i18next";
import Text from "@/refresh-components/texts/Text";

interface EnabledCountProps {
  name?: string;
  enabledCount: number;
  totalCount: number;
}

const EnabledCount = memo(
  ({ name, enabledCount, totalCount }: EnabledCountProps) => {
    const { t } = useTranslation();
    const suffix = name
      ? t("tools.enabledOfTotal", { count: totalCount })
      : t("common.enabledOfTotal", { totalCount });

    return (
      <Text text03 mainUiBody>
        <Text mainUiBody className="text-action-link-05">
          {enabledCount}
        </Text>
        {suffix}
      </Text>
    );
  }
);
EnabledCount.displayName = "EnabledCount";

export default EnabledCount;
