"use client";

import { useMemo, useState } from "react";
import { ChatFileType, FileDescriptor } from "@/app/app/interfaces";
import Attachment from "@/refresh-components/Attachment";
import { InMessageImage } from "@/app/app/components/files/images/InMessageImage";
import CsvContent from "@/components/tools/CSVContent";
import TextViewModal from "@/sections/modals/TextViewModal";
import { MinimalOnyxDocument } from "@/lib/search/interfaces";
import { cn } from "@/lib/utils";
import ExpandableContentWrapper from "@/components/tools/ExpandableContentWrapper";

interface FileDisplayProps {
  files: FileDescriptor[];
  alignBubble?: boolean;
}

export default function FileDisplay({ files, alignBubble }: FileDisplayProps) {
  const [close, setClose] = useState(true);
  const [previewingFile, setPreviewingFile] = useState<FileDescriptor | null>(
    null
  );
  // Deduplicate by id as a last-resort safety net before rendering.
  const uniqueFiles = Array.from(new Map(files.map((f) => [f.id, f])).values());
  const textFiles = uniqueFiles.filter(
    (file) =>
      file.type === ChatFileType.PLAIN_TEXT ||
      file.type === ChatFileType.DOCUMENT
  );
  const imageFiles = uniqueFiles.filter((file) => file.type === ChatFileType.IMAGE);
  const csvFiles = uniqueFiles.filter((file) => file.type === ChatFileType.CSV);

  // A just-sent message's FileDescriptor still carries the inline base64
  // payload client-side — preview from that directly instead of fetching
  // `/api/chat/file/{id}`, which can race with the backend's MinIO/DB persist
  // for a file attached to the message that triggered this very request.
  // Historical messages (loaded from server) never carry `data`, so they
  // fall back to the existing backend-fetch path in TextViewModal.
  const previewUrl = useMemo(
    () =>
      previewingFile?.data && previewingFile?.mime_type
        ? `data:${previewingFile.mime_type};base64,${previewingFile.data}`
        : undefined,
    [previewingFile?.data, previewingFile?.mime_type]
  );

  const presentingDocument: MinimalOnyxDocument = useMemo(
    () => ({
      document_id: previewingFile?.id ?? "",
      semantic_identifier: previewingFile?.name ?? "",
      preview_url: previewUrl,
      preview_mime_type: previewingFile?.mime_type ?? undefined,
    }),
    [
      previewingFile?.id,
      previewingFile?.name,
      previewUrl,
      previewingFile?.mime_type,
    ]
  );

  return (
    <>
      {previewingFile && (
        <TextViewModal
          presentingDocument={presentingDocument}
          onClose={() => setPreviewingFile(null)}
        />
      )}

      {textFiles.length > 0 && (
        <div
          id="onyx-file"
          className={cn("m-2 auto", alignBubble && "ml-auto")}
        >
          <div className="flex flex-col items-end gap-2">
            {textFiles.map((file) => (
              <Attachment
                key={file.id}
                fileName={file.name || file.id}
                open={() => setPreviewingFile(file)}
              />
            ))}
          </div>
        </div>
      )}

      {imageFiles.length > 0 && (
        <div
          id="onyx-image"
          className={cn("m-2 auto", alignBubble && "ml-auto")}
        >
          <div className="flex flex-col items-end gap-2">
            {imageFiles.map((file) => (
              <InMessageImage
                key={file.id}
                fileId={file.id}
                fileName={file.name}
              />
            ))}
          </div>
        </div>
      )}

      {csvFiles.length > 0 && (
        <div className={cn("m-2 auto", alignBubble && "ml-auto")}>
          <div className="flex flex-col items-end gap-2">
            {csvFiles.map((file) => {
              return (
                <div key={file.id} className="w-fit">
                  {close ? (
                    <>
                      <ExpandableContentWrapper
                        fileDescriptor={file}
                        close={() => setClose(false)}
                        ContentComponent={CsvContent}
                      />
                    </>
                  ) : (
                    <Attachment
                      open={() => setClose(true)}
                      fileName={file.name || file.id}
                    />
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </>
  );
}
