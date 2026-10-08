"use client";

import { useTranslation } from "react-i18next";
import * as DialogPrimitive from "@radix-ui/react-dialog";

interface SearchPreviewDrawerProps {
  open: boolean;
  onClose: () => void;
  children: React.ReactNode;
}

/**
 * Right-hand side panel for a result preview. Radix Dialog traps focus,
 * closes on Escape and overlay click, and restores focus to the opener.
 */
export default function SearchPreviewDrawer({
  open,
  onClose,
  children,
}: SearchPreviewDrawerProps) {
  const { t } = useTranslation();
  return (
    <DialogPrimitive.Root
      open={open}
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
    >
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-modal-overlay bg-mask-03" />
        <DialogPrimitive.Content
          aria-describedby={undefined}
          className="fixed inset-y-0 right-0 z-modal flex w-full max-w-[29rem] flex-col border-l border-border-01 bg-background-neutral-00 shadow-2xl focus:outline-none"
        >
          <DialogPrimitive.Title className="sr-only">
            {t("knowledgeSearch.preview.label")}
          </DialogPrimitive.Title>
          {children}
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
