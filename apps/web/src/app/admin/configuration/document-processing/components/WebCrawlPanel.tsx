"use client";

import { useState, useCallback } from "react";
import CardSection from "@/components/admin/CardSection";
import Button from "@/refresh-components/buttons/Button";
import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
import Text from "@/refresh-components/texts/Text";
import { toast } from "@/hooks/useToast";
import { uploadDocuments } from "@/lib/langconnect";
import {
  SvgArrowRightCircle,
  SvgGlobe,
  SvgLoader,
  SvgMinus,
  SvgPlus,
  SvgUploadCloud,
} from "@opal/icons";
import { cn } from "@/lib/utils";
import { useTranslation } from "react-i18next";

// Wraps SvgLoader with animate-spin while preserving the Button's icon styling.
const SpinningLoader = ({
  className,
  ...props
}: React.ComponentProps<typeof SvgLoader>) => (
  <SvgLoader {...props} className={cn("animate-spin", className)} />
);

interface CrawlResult {
  title: string;
  content: string;
  scrape_successful: boolean;
  failure_reason?: string | null;
}

interface UrlEntry {
  id: string;
  url: string;
  crawling: boolean;
  /** Validation error shown inline under the input (e.g. duplicate URL). Prevents crawling. */
  validationError: string | null;
  /** Crawl error shown in the result card after a crawl attempt. */
  error: string | null;
  result: {
    title: string;
    editedContent: string;
    scrape_successful: boolean;
    failure_reason?: string | null;
  } | null;
  adding: boolean;
}

interface WebCrawlPanelProps {
  collectionId: string;
  onDocumentAdded: () => void;
}

let _seq = 0;
const nextId = () => String(++_seq);

export default function WebCrawlPanel({
  collectionId,
  onDocumentAdded,
}: WebCrawlPanelProps) {
  const { t } = useTranslation();

  const [entries, setEntries] = useState<UrlEntry[]>([
    {
      id: nextId(),
      url: "",
      crawling: false,
      validationError: null,
      error: null,
      result: null,
      adding: false,
    },
  ]);

  const patchEntry = useCallback((id: string, patch: Partial<UrlEntry>) => {
    setEntries((prev) =>
      prev.map((e) => (e.id === id ? { ...e, ...patch } : e))
    );
  }, []);

  const addUrl = useCallback(() => {
    setEntries((prev) => [
      ...prev,
      {
        id: nextId(),
        url: "",
        crawling: false,
        validationError: null,
        error: null,
        result: null,
        adding: false,
      },
    ]);
  }, []);

  const removeUrl = useCallback((id: string) => {
    setEntries((prev) => prev.filter((e) => e.id !== id));
  }, []);

  const handleUrlChange = useCallback(
    (id: string, value: string) => {
      const trimmed = value.trim();
      const isDuplicate =
        trimmed.length > 0 &&
        entries.some((e) => e.id !== id && e.url.trim() === trimmed);
      patchEntry(id, {
        url: value,
        result: null,
        error: null,
        validationError: isDuplicate
          ? t("admin.documentProcessing.webCrawl.duplicateUrl", {
              defaultValue: "Bu URL zaten listede mevcut.",
            })
          : null,
      });
    },
    [entries, patchEntry, t]
  );

  const crawlEntry = useCallback(
    async (id: string, url: string) => {
      const trimmed = url.trim();
      if (!trimmed) return;
      patchEntry(id, { crawling: true, error: null, validationError: null, result: null });
      try {
        const res = await fetch(
          "/api/admin/web-search/content-providers/crawl",
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ url: trimmed }),
          }
        );
        const data = (await res.json()) as CrawlResult & { detail?: string };
        if (!res.ok) {
          patchEntry(id, {
            crawling: false,
            error:
              typeof data?.detail === "string"
                ? data.detail
                : t("admin.documentProcessing.webCrawl.crawlFailed", {
                    defaultValue: "Crawl failed.",
                  }),
          });
        } else {
          patchEntry(id, {
            crawling: false,
            result: {
              title: data.title,
              editedContent: data.content,
              scrape_successful: data.scrape_successful,
              failure_reason: data.failure_reason,
            },
          });
        }
      } catch {
        patchEntry(id, {
          crawling: false,
          error: t("admin.documentProcessing.webCrawl.networkError", {
            defaultValue: "Network error while crawling.",
          }),
        });
      }
    },
    [patchEntry, t]
  );

  const crawlAll = useCallback(async () => {
    const eligible = entries.filter((e) => e.url.trim() && !e.validationError);
    await Promise.all(eligible.map((e) => crawlEntry(e.id, e.url)));
  }, [entries, crawlEntry]);

  const addToCollection = useCallback(
    async (
      id: string,
      url: string,
      result: NonNullable<UrlEntry["result"]>
    ) => {
      if (!result.scrape_successful || !result.editedContent) return;
      patchEntry(id, { adding: true });
      try {
        const fileName =
          (result.title || url.replace(/[^a-zA-Z0-9]/g, "_")) + ".txt";
        const blob = new Blob([result.editedContent], { type: "text/plain" });
        const file = new File([blob], fileName, { type: "text/plain" });
        const res = await uploadDocuments(collectionId, [file], [
          { source: url, title: result.title || url },
        ]);
        toast.success(
          res.message ||
            t("admin.documentProcessing.webCrawl.addedSuccess", {
              defaultValue: "Web content added to collection.",
            })
        );
        if (res.warnings) toast.warning(res.warnings);
        // Clear result and URL so the preview card collapses
        patchEntry(id, { adding: false, result: null, url: "", error: null, validationError: null });
        onDocumentAdded();
      } catch (e) {
        toast.error(
          e instanceof Error
            ? e.message
            : t("admin.documentProcessing.webCrawl.addFailed", {
                defaultValue: "Failed to add document.",
              })
        );
        patchEntry(id, { adding: false });
      }
    },
    [patchEntry, collectionId, onDocumentAdded, t]
  );

  return (
    <div className="flex w-full flex-col gap-4">
      {/* URL input section */}
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
              "URL ekleyin, sayfa içeriklerini önizleyin ve koleksiyona ekleyin.",
          })}
        </Text>

        <div className="flex flex-col gap-2">
          {entries.map((entry) => (
            <div key={entry.id} className="flex w-full flex-col gap-1">
              <div className="flex w-full items-center gap-2">
                <div className="min-w-0 flex-1">
                  <InputTypeIn
                    placeholder={t(
                      "admin.documentProcessing.webCrawl.urlPlaceholder",
                      { defaultValue: "https://example.com" }
                    )}
                    value={entry.url}
                    onChange={(e) => handleUrlChange(entry.id, e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") void crawlAll();
                    }}
                  />
                </div>
                {entries.length > 1 && (
                  <Button
                    action={false}
                    tertiary
                    size="md"
                    onClick={() => removeUrl(entry.id)}
                    leftIcon={SvgMinus}
                  >
                    {""}
                  </Button>
                )}
              </div>
              {entry.validationError && (
                <Text as="p" mainContentMuted className="text-status-error-05 text-xs px-1">
                  {entry.validationError}
                </Text>
              )}
            </div>
          ))}
        </div>

        <div className="flex items-center gap-2">
          <Button
            action={false}
            tertiary
            size="md"
            onClick={addUrl}
            leftIcon={SvgPlus}
          >
            {t("admin.documentProcessing.webCrawl.addUrl", {
              defaultValue: "URL Ekle",
            })}
          </Button>
          <Button
            action={false}
            tertiary
            disabled={
              entries.every((e) => !e.url.trim() || !!e.validationError) ||
              entries.some((e) => e.crawling)
            }
            onClick={() => void crawlAll()}
            rightIcon={
              entries.some((e) => e.crawling)
                ? SpinningLoader
                : SvgArrowRightCircle
            }
          >
            {entries.some((e) => e.crawling)
              ? t("admin.documentProcessing.webCrawl.crawling", {
                  defaultValue: "Crawling…",
                })
              : t("admin.documentProcessing.webCrawl.crawl", {
                  defaultValue: "Crawl Et",
                })}
          </Button>
        </div>
      </CardSection>

      {/* Result cards – one per URL that has been crawled */}
      {entries.some((e) => e.error ?? e.result) && (
        <div className="flex flex-col gap-4">
          {entries.map((entry) => {
            if (!entry.error && !entry.result) return null;
            const charCount = entry.result?.editedContent.length ?? 0;

            return (
              <CardSection
                key={entry.id}
                className="flex w-full flex-col gap-3"
              >
                {/* Card header */}
                <div className="flex flex-col gap-3 border-b border-border-01 pb-2 md:flex-row md:items-center md:justify-between">
                  <div className="flex min-w-0 items-center gap-2">
                    <SvgGlobe
                      className="h-4 w-4 shrink-0 stroke-text-03"
                      aria-hidden
                    />
                    <Text as="p" headingH3 text05 className="truncate">
                      {entry.result?.title || entry.url}
                    </Text>
                    {entry.result?.scrape_successful && (
                      <span className="ml-1 shrink-0 rounded-full bg-background-neutral-02 px-2 py-0.5 text-xs text-text-03">
                        {charCount.toLocaleString()}{" "}
                        {t("admin.documentProcessing.webCrawl.chars", {
                          defaultValue: "karakter",
                        })}
                      </span>
                    )}
                  </div>
                  {entry.result?.scrape_successful && (
                    <Button
                      action
                      leftIcon={entry.adding ? SpinningLoader : SvgUploadCloud}
                      disabled={entry.adding}
                      onClick={() =>
                        void addToCollection(
                          entry.id,
                          entry.url,
                          entry.result!
                        )
                      }
                      className="w-full md:w-auto"
                    >
                      {entry.adding
                        ? t("admin.documentProcessing.webCrawl.adding", {
                            defaultValue: "Ekleniyor…",
                          })
                        : t(
                            "admin.documentProcessing.webCrawl.addToCollection",
                            { defaultValue: "Koleksiyona Ekle" }
                          )}
                    </Button>
                  )}
                </div>

                {/* Crawl error */}
                {entry.error && (
                  <div className="rounded-08 border border-status-danger-02 bg-status-danger-00 px-3 py-2">
                    <Text
                      as="p"
                      mainContentBody
                      className="text-status-error-05"
                    >
                      {entry.error}
                    </Text>
                  </div>
                )}

                {/* Scrape failure reason */}
                {entry.result && !entry.result.scrape_successful && (
                  <div className="rounded-08 border border-status-danger-02 bg-status-danger-00 px-3 py-2">
                    <Text
                      as="p"
                      mainContentBody
                      className="text-status-error-05"
                    >
                      {entry.result.failure_reason ||
                        t("admin.documentProcessing.webCrawl.crawlFailed", {
                          defaultValue: "Crawl başarısız.",
                        })}
                    </Text>
                  </div>
                )}

                {/* Editable content preview */}
                {entry.result?.scrape_successful && (
                  <textarea
                    className={cn(
                      "w-full rounded-08 border border-border-01 bg-background-neutral-01",
                      "min-h-48 max-h-96 resize-y px-4 py-3",
                      "whitespace-pre-wrap break-words text-sm leading-relaxed text-text-04",
                      "focus:outline-none focus:ring-1 focus:ring-border-focus-01"
                    )}
                    value={entry.result.editedContent}
                    onChange={(e) =>
                      patchEntry(entry.id, {
                        result: {
                          ...entry.result!,
                          editedContent: e.target.value,
                        },
                      })
                    }
                  />
                )}
              </CardSection>
            );
          })}
        </div>
      )}
    </div>
  );
}
