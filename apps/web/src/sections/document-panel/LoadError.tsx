"use client";

import { useTranslation } from "react-i18next";
import { Button } from "@opal/components";
import Text from "@/refresh-components/texts/Text";

interface LoadErrorProps {
  onRetry: () => void;
}

export function LoadError({ onRetry }: LoadErrorProps) {
  const { t } = useTranslation();
  return (
    <div
      role="alert"
      className="flex flex-col items-center gap-2 p-8"
      data-testid="load-error"
    >
      <Text as="p" mainUiBody text03>
        {t("documentPanel.loadError")}
      </Text>
      <Button prominence="secondary" size="sm" onClick={onRetry}>
        {t("documentPanel.retry")}
      </Button>
    </div>
  );
}
