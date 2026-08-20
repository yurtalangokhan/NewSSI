"use client";

import PreviewModal from "@/sections/modals/PreviewModal";

interface FullImageModalProps {
  fileId: string;
  fileName?: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function FullImageModal({
  fileId,
  fileName,
  open,
  onOpenChange,
}: FullImageModalProps) {
  if (!open) return null;

  return (
    <PreviewModal
      presentingDocument={{
        document_id: fileId,
        semantic_identifier: fileName || null,
      }}
      onClose={() => onOpenChange(false)}
    />
  );
}
