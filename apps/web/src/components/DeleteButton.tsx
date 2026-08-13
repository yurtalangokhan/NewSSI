"use client";

import { SvgTrash } from "@opal/icons";
import { Button } from "@opal/components";
import { useTranslation } from "react-i18next";

export interface DeleteButtonProps {
  onClick?: (event: React.MouseEvent<HTMLElement>) => void | Promise<void>;
  disabled?: boolean;
}

export function DeleteButton({ onClick, disabled }: DeleteButtonProps) {
  const { t } = useTranslation();
  return (
    <Button
      onClick={onClick}
      icon={SvgTrash}
      tooltip={t("common.delete")}
      disabled={disabled}
      prominence="tertiary"
      size="sm"
    />
  );
}
