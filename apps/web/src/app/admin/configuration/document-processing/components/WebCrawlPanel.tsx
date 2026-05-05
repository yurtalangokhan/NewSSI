"use client";

import { useState, useCallback } from "react";
import CardSection from "@/components/admin/CardSection";
import Button from "@/refresh-components/buttons/Button";
import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
import Text from "@/refresh-components/texts/Text";
import { ThreeDotsLoader } from "@/components/Loading";
import { toast } from "@/hooks/useToast";
import { uploadDocuments, useDocuments } from "@/lib/langconnect";
import {
  SvgArrowRightCircle,
  SvgGlobe,
  SvgLoader,
  SvgUploadCloud,
} from "@opal/icons";
import { cn } from "@/lib/utils";
import { useTranslation } from "react-i18next";

interface CrawlResult {
  title: string;
  content: string;
  scrape_successful: boolean;
  failure_reason?: string | null;
}

interface WebCrawlPanelProps {
  collectionId: string;
  onDocumentAdded: () => void;
}

export default function WebCrawlPanel({
  collectionId,
  onDocumentAdded,
}: WebCrawlPanelProps) {
  const { t } = useTranslation();
  const [url, setUrl] = useState("");
  const [crawling, setCrawling] = useState(false);
  const [crawlResult, setCrawlResult] = useState<CrawlResult | null>(null);
  const [crawlError, setCrawlError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);

  const handleCrawl = useCallback(async () => {
    const trimmed = url.trim();
    if (!trimmed) return;
    setCrawling(true);
    setCrawlResult(null);
    setCrawlError(null);
    try {
      const res = await fetch(
        "/api/admin/web-search/content-providers/crawl",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url: trimmed }),
        }
      );
      const data = await res.json();
      if (!res.ok) {
        setCrawlError(
          typeof data?.detail === "string" ? data.detail : "Crawl failed."
        );
      } else {
        setCrawlResult(data as CrawlResult);
      }
    } catch {
      setCrawlError("Network error while crawling.");
    } finally {
      setCrawling(false);
    }
  }, [url]);

  const handleAddToCollection = useCallback(async () => {
    if (!crawlResult?.scrape_successful || !crawlResult.content) return;
    setAdding(true);
    try {
      const fileName =
        (crawlResult.title || url.trim().replace(/[^a-zA-Z0-9]/g, "_")) +
        ".txt";
      const blob = new Blob([crawlResult.content], { type: "text/plain" });
      const file = new File([blob], fileName, { type: "text/plain" });
      const result = await uploadDocuments(collectionId, [file], [
        { source: url.trim(), title: crawlResult.title || url.trim() },
      ]);
      toast.success(
        result.message ||
          t("admin.documentProcessing.webCrawl.addedSuccess", {
            defaultValue: "Web content added to collection.",
          })
      );
      if (result.warnings) {
        toast.warning(result.warnings);
      }
      onDocumentAdded();
      // Reset after success
      setUrl("");
      setCrawlResult(null);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to add document.");
    } finally {
      setAdding(false);
    }
  }, [collectionId, crawlResult, url, onDocumentAdded, t]);

  return (
    <div className="flex w-full flex-col gap-4">
      <CardSection className="flex w-full flex-col gap-3">
        <Text
          as="p"
          headingH3
          text05
          className="border-b border-border-01 pb-2"
        >
          {t("admin.documentProcessing.webCrawl.title", {
            defaultValue: "Web'den İçerik Ekle",
          })}
        </Text>
        <Text as="p" mainContentBody text04 className="leading-relaxed">
          {t("admin.documentProcessing.webCrawl.description", {
            defaultValue:
              "Bir URL girin, sayfa içeriğini önizleyin ve koleksiyona ekleyin.",
          })}
        </Text>

        <div className="flex w-full flex-col gap-2 md:flex-row md:items-center">
          <div className="w-full flex-1 min-w-0">
            <InputTypeIn
              placeholder="https://example.com"
              value={url}
              onChange={(e) => {
                setUrl(e.target.value);
                setCrawlResult(null);
                setCrawlError(null);
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter") void handleCrawl();
              }}
            />
          </div>
          <Button
            action={false}
            tertiary
            disabled={!url.trim() || crawling}
            onClick={() => void handleCrawl()}
            rightIcon={crawling ? SvgLoader : SvgArrowRightCircle}
            className="w-full md:w-auto md:shrink-0"
          >
            {crawling
              ? t("admin.documentProcessing.webCrawl.crawling", {
                  defaultValue: "Crawl Ediliyor…",
                })
              : t("admin.documentProcessing.webCrawl.crawl", {
                  defaultValue: "Crawl Et",
                })}
          </Button>
        </div>

        {crawlError && (
          <div className="rounded-08 border border-status-danger-02 bg-status-danger-00 px-3 py-2">
            <Text as="p" mainContentBody className="text-status-error-05">
              {crawlError}
            </Text>
          </div>
        )}
      </CardSection>

      {crawlResult && (
        <CardSection className="flex w-full flex-col gap-3">
          <div className="flex flex-col gap-3 border-b border-border-01 pb-2 md:flex-row md:items-center md:justify-between">
            <div className="flex min-w-0 items-center gap-2">
              <SvgGlobe className="h-4 w-4 shrink-0 stroke-text-03" aria-hidden />
              <Text as="p" headingH3 text05>
                {t("admin.documentProcessing.webCrawl.previewTitle", {
                  defaultValue: "Önizleme",
                })}
              </Text>
            </div>
            {crawlResult.scrape_successful && (
              <Button
                action
                leftIcon={adding ? SvgLoader : SvgUploadCloud}
                disabled={adding}
                onClick={() => void handleAddToCollection()}
                className="w-full md:w-auto"
              >
                {adding
                  ? t("admin.documentProcessing.webCrawl.adding", {
                      defaultValue: "Ekleniyor…",
                    })
                  : t("admin.documentProcessing.webCrawl.addToCollection", {
                      defaultValue: "Koleksiyona Ekle",
                    })}
              </Button>
            )}
          </div>

          {crawlResult.scrape_successful ? (
            <>
              {crawlResult.title && (
                <Text
                  as="p"
                  mainUiAction
                  text05
                  className="font-semibold"
                >
                  {crawlResult.title}
                </Text>
              )}
              <div
                className={cn(
                  "rounded-08 border border-border-01 bg-background-neutral-01 px-4 py-3",
                  "max-h-96 overflow-y-auto"
                )}
              >
                <Text
                  as="p"
                  mainContentBody
                  text04
                  className="whitespace-pre-wrap break-words text-sm leading-relaxed"
                >
                  {crawlResult.content || "(no content extracted)"}
                </Text>
              </div>
            </>
          ) : (
            <div className="rounded-08 border border-status-danger-02 bg-status-danger-00 px-3 py-2">
              <Text as="p" mainContentBody className="text-status-error-05">
                {crawlResult.failure_reason ||
                  t("admin.documentProcessing.webCrawl.crawlFailed", {
                    defaultValue: "Crawl başarısız.",
                  })}
              </Text>
            </div>
          )}
        </CardSection>
      )}
    </div>
  );
}
