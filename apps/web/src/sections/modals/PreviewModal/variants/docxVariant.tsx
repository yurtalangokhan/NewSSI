import DocxPreview from "@/app/app/components/files/DocxPreview";
import ScrollIndicatorDiv from "@/refresh-components/ScrollIndicatorDiv";
import { Section } from "@/layouts/general-layouts";
import { PreviewVariant } from "@/sections/modals/PreviewModal/interfaces";
import {
  DownloadButton,
  ZoomControls,
} from "@/sections/modals/PreviewModal/variants/shared";

const WORD_MIMES = [
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/msword",
];

export const docxVariant: PreviewVariant = {
  matches: (_name, mime) => WORD_MIMES.some((m) => mime.startsWith(m)),
  width: "lg",
  height: "full",
  needsTextContent: false,
  headerDescription: () => "",

  renderContent: (ctx) =>
    ctx.fileBlob ? (
      <div
        className="flex flex-col flex-1 min-h-0 min-w-0 w-full transition-transform duration-300 ease-in-out"
        style={{
          transform: `scale(${ctx.zoom / 100})`,
          transformOrigin: "top center",
        }}
      >
        <ScrollIndicatorDiv className="flex-1 min-h-0" variant="shadow">
          <DocxPreview blob={ctx.fileBlob} className="w-full" />
        </ScrollIndicatorDiv>
      </div>
    ) : null,

  renderFooterLeft: (ctx) => (
    <ZoomControls
      zoom={ctx.zoom}
      onZoomIn={ctx.onZoomIn}
      onZoomOut={ctx.onZoomOut}
    />
  ),

  renderFooterRight: (ctx) => (
    <Section flexDirection="row" width="fit">
      <DownloadButton fileUrl={ctx.fileUrl} fileName={ctx.fileName} />
    </Section>
  ),
};
