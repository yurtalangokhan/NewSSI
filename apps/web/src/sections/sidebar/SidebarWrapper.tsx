import React, { useCallback } from "react";
import { cn } from "@/lib/utils";
import { Button } from "@opal/components";
import { SvgSidebar } from "@opal/icons";
import Logo from "@/refresh-components/Logo";

interface LogoSectionProps {
  folded?: boolean;
  onFoldClick?: () => void;
}

function LogoSection({ folded, onFoldClick }: LogoSectionProps) {
  const closeButton = useCallback(
    () => (
      <Button
        icon={SvgSidebar}
        prominence="tertiary"
        tooltip="Close Sidebar"
        onClick={onFoldClick}
      />
    ),
    [onFoldClick]
  );

  return (
    <div
      className={cn(
        "flex items-center px-2.5 py-2 h-[3.25rem] min-h-[3.25rem]",
        folded ? "justify-center" : "justify-between"
      )}
    >
      {!folded && <Logo />}
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
    // This extra `div` wrapping needs to be present (for some reason).
    // Without, the widths of the sidebars don't properly get set to the explicitly declared widths (i.e., `4rem` folded and `15rem` unfolded).
    <div>
      <div
        className={cn(
          "h-screen flex flex-col bg-background-tint-02 py-2 gap-4 group/SidebarWrapper transition-width duration-200 ease-in-out",
          folded ? "w-[3.25rem]" : "w-[15rem]"
        )}
      >
        <LogoSection folded={folded} onFoldClick={onFoldClick} />
        {children}
      </div>
    </div>
  );
}
