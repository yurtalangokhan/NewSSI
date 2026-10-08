"use client";

import { MinimalAtlasDocument } from "@/lib/search/interfaces";
import Modal from "@/refresh-components/Modal";
import { DocumentPreviewSkeleton } from "@/refresh-components/skeletons";
import Text from "@/refresh-components/texts/Text";
import { cn } from "@/lib/utils";
import { Section } from "@/layouts/general-layouts";
import { usePreviewFile } from "@/sections/modals/PreviewModal/usePreviewFile";

interface PreviewModalProps {
  presentingDocument: MinimalAtlasDocument;
  onClose: () => void;
}

export default function PreviewModal({
  presentingDocument,
  onClose,
}: PreviewModalProps) {
  const { variant, ctx, isLoading, loadError } =
    usePreviewFile(presentingDocument);
  const effectiveFileName = ctx.fileName;

  return (
    <Modal
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <Modal.Content
        width={variant.width}
        height={variant.height}
        preventAccidentalClose={false}
        onOpenAutoFocus={(e) => e.preventDefault()}
      >
        <Modal.Header
          title={effectiveFileName || "Document"}
          description={variant.headerDescription(ctx)}
          onClose={onClose}
        />

        {/* Body + floating footer wrapper. `twoTone={false}` keeps the viewer
            on one surface: the modal card's `tint-00` (pure black in dark mode)
            instead of repainting the scroll area with `Modal.Body`'s default
            `tint-01`, which left a black/gray seam under the header. */}
        <Modal.Body padding={0} gap={0} twoTone={false}>
          <Section padding={0} gap={0}>
            {isLoading ? (
              <div className="p-6 w-full">
                {/* The viewer renders the document on the modal surface, so the
                    placeholder is the page shape without a paper. */}
                <DocumentPreviewSkeleton paper={false} />
              </div>
            ) : loadError ? (
              <Section padding={1}>
                <Text text03 mainUiBody>
                  {loadError}
                </Text>
              </Section>
            ) : (
              variant.renderContent(ctx)
            )}
          </Section>
        </Modal.Body>

        {/* Floating footer */}
        {!isLoading && !loadError && (
          <div
            className={cn(
              "absolute bottom-0 left-0 right-0",
              "flex items-center justify-between",
              "p-4 pointer-events-none w-full"
            )}
            style={{
              background:
                "linear-gradient(to top, var(--background-tint-01) 40%, transparent)",
            }}
          >
            {/* Left slot */}
            <div className="pointer-events-auto">
              {variant.renderFooterLeft(ctx)}
            </div>

            {/* Right slot */}
            <div className="pointer-events-auto rounded-12 bg-background-tint-00 p-1 shadow-lg">
              {variant.renderFooterRight(ctx)}
            </div>
          </div>
        )}
      </Modal.Content>
    </Modal>
  );
}
