"use client";

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@opal/components";
import { SvgDownload, SvgFileText } from "@/icons";
import { toast } from "@/hooks/useToast";
import { exportRevision } from "@/lib/api/domains/documents/api";
import type {
  DocumentKind,
  ExportFormat,
  SourceFormat,
} from "@/lib/api/domains/documents/types";
import { FetchError } from "@/lib/api/http/errors";
import { exportFormatsFor } from "@/lib/documents/documentContent";
import Popover, { PopoverMenu } from "@/refresh-components/Popover";
import LineItem from "@/refresh-components/buttons/LineItem";

interface ExportMenuProps {
  documentId: string;
  revisionNo: number;
  kind: DocumentKind;
  sourceFormat: SourceFormat;
}

function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.rel = "noopener";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export function ExportMenu({
  documentId,
  revisionNo,
  kind,
  sourceFormat,
}: ExportMenuProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const formats: ExportFormat[] = exportFormatsFor(kind, sourceFormat);

  const download = async (format: ExportFormat) => {
    setOpen(false);
    setBusy(true);
    try {
      const { blob, filename } = await exportRevision(
        documentId,
        revisionNo,
        format
      );
      saveBlob(blob, filename);
    } catch (error) {
      toast.error(
        error instanceof FetchError && error.message
          ? error.message
          : t("documentPanel.exportFailed")
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <Popover.Trigger asChild>
        <Button
          icon={SvgDownload}
          prominence="secondary"
          size="sm"
          disabled={busy}
          aria-busy={busy}
        >
          {t(busy ? "documentPanel.exporting" : "documentPanel.export")}
        </Button>
      </Popover.Trigger>
      <Popover.Content side="bottom" align="end" width="md">
        <PopoverMenu>
          {formats.map((format) => (
            <LineItem
              key={format}
              icon={SvgFileText}
              onClick={() => void download(format)}
            >
              {t("documentPanel.exportAs", { format: format.toUpperCase() })}
            </LineItem>
          ))}
        </PopoverMenu>
      </Popover.Content>
    </Popover>
  );
}
