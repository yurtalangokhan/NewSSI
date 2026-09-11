"use client";

import DropzoneInput from "@/refresh-components/inputs/DropzoneInput";
import React, { useState, useMemo, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { useDropzone } from "react-dropzone";
import { cn, formatBytes } from "@/lib/utils";
import Modal from "@/refresh-components/Modal";
import Tabs from "@/refresh-components/Tabs";
import Button from "@/refresh-components/buttons/Button";
import IconButton from "@/refresh-components/buttons/IconButton";
import {
  SvgImport,
  SvgUploadCloud,
  SvgFiles,
  SvgCheckCircle,
  SvgXCircle,
  SvgEdit,
  SvgTrash,
} from "@opal/icons";
import {
  parseFlowJson,
  getJsonSyntaxErrorDetails,
  SAMPLE_FLOW_JSON,
  type ImportFlowResult,
} from "../utils/importFlow";
import { JsonCodeEditor } from "./JsonCodeEditor";
import Text from "@/refresh-components/texts/Text";

export interface ImportFlowModalProps {
  open: boolean;
  onClose: () => void;
  onImport: (
    graph: Extract<ImportFlowResult, { success: true }>["graph"],
    nodeCount: number,
    edgeCount: number
  ) => void;
  initialJson?: string;
}

export function ImportFlowModal({
  open,
  onClose,
  onImport,
  initialJson = "",
}: ImportFlowModalProps) {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<"upload" | "paste">("upload");
  const [jsonText, setJsonText] = useState<string>(initialJson);
  const [selectedFile, setSelectedFile] = useState<{
    name: string;
    size: number;
  } | null>(null);

  // Compute validation results
  const syntaxError = useMemo(() => {
    return getJsonSyntaxErrorDetails(jsonText);
  }, [jsonText]);

  const flowValidation = useMemo<ImportFlowResult | null>(() => {
    if (!jsonText.trim()) return null;
    return parseFlowJson(jsonText);
  }, [jsonText]);

  const isValid = flowValidation?.success === true;

  // Handle loading file content
  const handleLoadFile = useCallback((file: File) => {
    const reader = new FileReader();
    reader.onload = (event) => {
      const content = event.target?.result;
      if (typeof content === "string") {
        setJsonText(content);
        setSelectedFile({
          name: file.name,
          size: file.size,
        });
      }
    };
    reader.readAsText(file);
  }, []);

  // Dropzone setup
  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    accept: {
      "application/json": [".json"],
    },
    maxFiles: 1,
    multiple: false,
    onDrop: (acceptedFiles) => {
      if (acceptedFiles.length > 0 && acceptedFiles[0]) {
        handleLoadFile(acceptedFiles[0]);
      }
    },
  });

  // Handle import execution
  const handleExecuteImport = () => {
    if (flowValidation && flowValidation.success) {
      onImport(
        flowValidation.graph,
        flowValidation.nodeCount,
        flowValidation.edgeCount
      );
      handleReset();
      onClose();
    }
  };

  // Reset modal state
  const handleReset = () => {
    setJsonText("");
    setSelectedFile(null);
    setActiveTab("upload");
  };

  const handleClose = () => {
    handleReset();
    onClose();
  };

  const handleClearFile = () => {
    setSelectedFile(null);
    setJsonText("");
  };

  const handleLoadSample = () => {
    setJsonText(SAMPLE_FLOW_JSON);
    setSelectedFile(null);
  };

  return (
    <Modal open={open} onOpenChange={(isOpen) => !isOpen && handleClose()}>
      <Modal.Content width="md" height="fit">
        {/* Modal Header */}
        <Modal.Header
          icon={SvgImport}
          title={t("flowCanvas.importModalTitle", "Akış İçe Aktar (JSON)")}
          description={t(
            "flowCanvas.importModalDescription",
            "JSON dosyası yükleyerek veya JSON metnini doğrudan yapıştırarak akışı içe aktarın."
          )}
          onClose={handleClose}
        />

        {/* Modal Body with Tabs */}
        <Modal.Body padding={1}>
          <div className="w-full flex flex-col gap-4">
            <Tabs
              value={activeTab}
              defaultValue="upload"
              onValueChange={(val) => setActiveTab(val as "upload" | "paste")}
            >
              <Tabs.List className="w-full">
                <Tabs.Trigger
                  value="upload"
                  icon={SvgUploadCloud}
                  onClick={() => setActiveTab("upload")}
                  data-testid="import-modal-tab-upload"
                >
                  {t("flowCanvas.uploadTab", "Dosya Yükle")}
                </Tabs.Trigger>
                <Tabs.Trigger
                  value="paste"
                  icon={SvgEdit}
                  onClick={() => setActiveTab("paste")}
                  data-testid="import-modal-tab-paste"
                >
                  {t("flowCanvas.pasteTab", "JSON Metni")}
                </Tabs.Trigger>
              </Tabs.List>

              {/* TAB 1: FILE UPLOAD (DRAG & DROP) */}
              <Tabs.Content value="upload">
                <div className="pt-3 w-full">
                  {!selectedFile ? (
                    <div
                      {...getRootProps()}
                      data-testid="import-dropzone"
                      className={cn(
                        "flex flex-col items-center justify-center p-8 border-2 border-dashed rounded-xl cursor-pointer transition-all duration-200 text-center gap-3",
                        isDragActive
                          ? "border-accent bg-action-link-01 scale-[0.99]"
                          : "border-border-01 hover:border-border-02 hover:bg-background-tint-01/50 bg-background-tint-00"
                      )}
                    >
                      <DropzoneInput
                        {...getInputProps()}
                        data-testid="import-dropzone-input"
                      />
                      <div
                        className={cn(
                          "p-3 rounded-full transition-transform duration-200",
                          isDragActive
                            ? "bg-action-link-01 text-action-link-05 scale-110"
                            : "bg-background-neutral-01 text-text-03"
                        )}
                      >
                        <SvgUploadCloud className="w-7 h-7" />
                      </div>
                      <div className="flex flex-col gap-1">
                        <Text
                          as="p"
                          className="text-sm font-semibold text-text-05"
                        >
                          {isDragActive
                            ? t(
                                "flowCanvas.dragDropActive",
                                "Dosyayı buraya bırakın..."
                              )
                            : t(
                                "flowCanvas.dragDropTitle",
                                "JSON dosyasını buraya sürükleyip bırakın"
                              )}
                        </Text>
                        <Text as="p" className="text-xs text-text-03">
                          {t(
                            "flowCanvas.dragDropSubtitle",
                            "veya dosya seçmek için tıklayın (.json dosyaları desteklenir)"
                          )}
                        </Text>
                      </div>
                    </div>
                  ) : (
                    /* Selected File Summary Card */
                    <div
                      data-testid="import-file-card"
                      className="flex flex-col gap-3 p-4 rounded-xl border border-border-01 bg-background-tint-00 shadow-xs"
                    >
                      <div className="flex items-center justify-between gap-3">
                        <div className="flex items-center gap-3 min-w-0">
                          <div className="p-2.5 rounded-lg bg-background-neutral-01 text-text-04 border border-border-01">
                            <SvgFiles className="w-5 h-5" />
                          </div>
                          <div className="flex flex-col min-w-0">
                            <span className="text-sm font-semibold text-text-05 truncate">
                              {selectedFile.name}
                            </span>
                            <span className="text-xs text-text-03">
                              {formatBytes(selectedFile.size)}
                            </span>
                          </div>
                        </div>

                        <div className="flex items-center gap-1.5 shrink-0">
                          <Button
                            tertiary
                            size="md"
                            leftIcon={SvgEdit}
                            onClick={() => setActiveTab("paste")}
                            title={t(
                              "flowCanvas.editInCodeEditor",
                              "Editörde Düzenle"
                            )}
                          >
                            {t(
                              "flowCanvas.editInCodeEditor",
                              "Editörde Düzenle"
                            )}
                          </Button>
                          <IconButton
                            tertiary
                            small
                            icon={SvgTrash}
                            onClick={handleClearFile}
                            tooltip={t("flowCanvas.removeFile", "Kaldır")}
                            aria-label={t("flowCanvas.removeFile", "Kaldır")}
                          />
                        </div>
                      </div>

                      {/* File Validation Status */}
                      <div className="pt-2 border-t border-border-01">
                        {isValid && flowValidation?.success ? (
                          <div className="flex items-center gap-2 text-xs text-theme-green-05 font-medium">
                            <SvgCheckCircle className="w-4 h-4 shrink-0 text-theme-green-05" />
                            <span>
                              {t(
                                "flowCanvas.validFlow",
                                "Geçerli Akış ({{nodes}} düğüm, {{edges}} bağlantı)",
                                {
                                  nodes: flowValidation.nodeCount,
                                  edges: flowValidation.edgeCount,
                                }
                              )}
                            </span>
                          </div>
                        ) : (
                          <div className="flex items-center gap-2 text-xs text-theme-red-05 font-medium">
                            <SvgXCircle className="w-4 h-4 shrink-0 text-theme-red-05" />
                            <span>
                              {flowValidation && !flowValidation.success
                                ? t(
                                    `flowCanvas.importErrors.${flowValidation.errorCode}`
                                  )
                                : t(
                                    "flowCanvas.invalidJson",
                                    "Geçersiz dosya içeriği"
                                  )}
                            </span>
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              </Tabs.Content>

              {/* TAB 2: CODE EDITOR (PASTE JSON) */}
              <Tabs.Content value="paste">
                <div className="pt-3 w-full">
                  <JsonCodeEditor
                    value={jsonText}
                    onChange={(val) => {
                      setJsonText(val);
                      if (selectedFile) setSelectedFile(null);
                    }}
                    errorDetails={syntaxError}
                    isValidFlow={isValid}
                    validStats={
                      flowValidation?.success
                        ? {
                            nodeCount: flowValidation.nodeCount,
                            edgeCount: flowValidation.edgeCount,
                          }
                        : null
                    }
                    onLoadSample={handleLoadSample}
                    height="320px"
                  />
                </div>
              </Tabs.Content>
            </Tabs>
          </div>
        </Modal.Body>

        {/* Modal Footer */}
        <Modal.Footer padding={1}>
          <div className="flex w-full items-center justify-between gap-3">
            <div className="text-xs text-text-03">
              {isValid && flowValidation?.success ? (
                <span className="inline-flex items-center gap-1.5 text-theme-green-05 font-medium">
                  <SvgCheckCircle className="w-3.5 h-3.5" />
                  {t(
                    "flowCanvas.validFlow",
                    "Geçerli Akış ({{nodes}} düğüm, {{edges}} bağlantı)",
                    {
                      nodes: flowValidation.nodeCount,
                      edges: flowValidation.edgeCount,
                    }
                  )}
                </span>
              ) : null}
            </div>

            <div className="flex items-center gap-2 shrink-0">
              <Button
                secondary
                size="md"
                onClick={handleClose}
                data-testid="import-modal-cancel"
              >
                {t("flowCanvas.cancel", "İptal")}
              </Button>
              <Button
                action
                size="md"
                leftIcon={SvgImport}
                onClick={handleExecuteImport}
                disabled={!isValid}
                data-testid="import-modal-submit"
              >
                {t("flowCanvas.importAction", "Akışı İçe Aktar")}
              </Button>
            </div>
          </div>
        </Modal.Footer>
      </Modal.Content>
    </Modal>
  );
}

export default ImportFlowModal;
