"use client";

import { useRouter } from "next/navigation";
import type { Route } from "next";
import { Button } from "@opal/components";
import { SvgArrowLeft } from "@opal/icons";
import { useTranslation } from "react-i18next";

export interface BackButtonProps {
  behaviorOverride?: () => void;
  routerOverride?: string;
}

export default function BackButton({
  behaviorOverride,
  routerOverride,
}: BackButtonProps) {
  const router = useRouter();
  const { t } = useTranslation();

  return (
    <Button
      icon={SvgArrowLeft}
      prominence="tertiary"
      onClick={() => {
        if (behaviorOverride) {
          behaviorOverride();
        } else if (routerOverride) {
          router.push(routerOverride as Route);
        } else {
          router.back();
        }
      }}
    >
      {t("common.back")}
    </Button>
  );
}
