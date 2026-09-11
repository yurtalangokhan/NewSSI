"use client";

import { useState, useCallback } from "react";
import { useTranslation } from "react-i18next";
import CardSection from "@/components/admin/CardSection";
import Button from "@/refresh-components/buttons/Button";
import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
import InputTextArea from "@/refresh-components/inputs/InputTextArea";
import Text from "@/refresh-components/texts/Text";
import SimpleLoader from "@/refresh-components/loaders/SimpleLoader";
import { toast } from "@/hooks/useToast";
import { uploadDocuments } from "@/lib/langconnect";

interface TextInputPanelProps {
  collectionId: string;
  onDocumentAdded: () => void;
}

export default function TextInputPanel({
  collectionId,
  onDocumentAdded,
}: TextInputPanelProps) {
  const { t } = useTranslation();
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [isAdding, setIsAdding] = useState(false);

  const handleAdd = useCallback(async () => {
    const trimmedContent = content.trim();
    if (!trimmedContent) return;

    const filename = title.trim()
      ? `${title.trim()}.txt`
      : `document-${Date.now()}.txt`;

    setIsAdding(true);
    try {
      const file = new File([trimmedContent], filename, { type: "text/plain" });
      await uploadDocuments(
        collectionId,
        [file],
        [{ filename, ...(title.trim() ? { title: title.trim() } : {}) }]
      );
      toast.success(
        t("admin.documentProcessing.textInput.addSuccess", {
          defaultValue: "Belge başarıyla eklendi.",
        })
      );
      setTitle("");
      setContent("");
      onDocumentAdded();
    } catch (e) {
      toast.error(
        e instanceof Error
          ? e.message
          : t("admin.documentProcessing.uploadFailed", {
              defaultValue: "Yükleme başarısız oldu",
            })
      );
    } finally {
      setIsAdding(false);
    }
  }, [collectionId, title, content, onDocumentAdded, t]);

  return (
    <CardSection className="w-full flex flex-col gap-4">
      <Text as="p" mainContentBody text04 className="leading-relaxed">
        {t("admin.documentProcessing.textInput.description", {
          defaultValue: "Metni doğrudan girerek koleksiyona belge ekleyin.",
        })}
      </Text>

      <div className="flex flex-col gap-3">
        <InputTypeIn
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder={t(
            "admin.documentProcessing.textInput.titlePlaceholder",
            {
              defaultValue: "Belge başlığı (isteğe bağlı)",
            }
          )}
          variant={isAdding ? "disabled" : "primary"}
        />

        <InputTextArea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          placeholder={t(
            "admin.documentProcessing.textInput.contentPlaceholder",
            {
              defaultValue: "Belge içeriğini buraya girin...",
            }
          )}
          rows={10}
          variant={isAdding ? "disabled" : "primary"}
        />
      </div>

      <div className="flex justify-end">
        <Button
          action
          primary
          size="lg"
          onClick={handleAdd}
          disabled={isAdding || !content.trim()}
        >
          {isAdding ? (
            <span className="flex items-center gap-2">
              <SimpleLoader className="h-4 w-4" />
              {t("admin.documentProcessing.textInput.adding", {
                defaultValue: "Ekleniyor...",
              })}
            </span>
          ) : (
            t("admin.documentProcessing.textInput.add", {
              defaultValue: "Belge Ekle",
            })
          )}
        </Button>
      </div>
    </CardSection>
  );
}
