import React, { useCallback } from "react";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import { Button } from "@opal/components";
import { SvgSidebar } from "@opal/icons";
import Logo from "@/refresh-components/Logo";

interface LogoSectionProps {
  folded?: boolean;
  onFoldClick?: () => void;
}

function LogoSection({ folded, onFoldClick }: LogoSectionProps) {
  const { t } = useTranslation("common", { keyPrefix: "sidebar" });
  const closeButton = useCallback(
    () => (
      <Button
        icon={SvgSidebar}
        prominence="tertiary"
        tooltip={folded ? t("openSidebar") : t("closeSidebar")}
        onClick={onFoldClick}
      />
    ),
    [folded, onFoldClick, t]
  );

  return (
    <div
      className={cn(
        "flex items-center px-2.5 py-2 h-[3.25rem] min-h-[3.25rem] overflow-hidden",
        folded ? "justify-center" : "justify-between"
      )}
    >
      {!folded && (
        <div className="overflow-hidden whitespace-nowrap">
          <Logo />
        </div>
      )}
      {folded !== undefined && closeButton()}
    </div>
  );
}

export interface SidebarWrapperProps {
  folded?: boolean;
  onFoldClick?: () => void;
  children?: React.ReactNode;
}

export default function SidebarWrapper({
  folded,
  onFoldClick,
  children,
}: SidebarWrapperProps) {
  return (
    <aside
      className={cn(
        "h-screen flex flex-col bg-background-tint-02 py-2 gap-4 group/SidebarWrapper shrink-0 overflow-hidden select-none transition-[width] duration-300 ease-in-out",
        folded ? "w-[3.25rem]" : "w-[15rem]"
      )}
    >
      <LogoSection folded={folded} onFoldClick={onFoldClick} />
      <div className="flex-1 min-h-0 overflow-hidden w-full">
        {children}
      </div>
    </aside>
  );
}
