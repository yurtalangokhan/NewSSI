"use client";

import { useState } from "react";
import CardSection from "@/components/admin/CardSection";
import Button from "@/refresh-components/buttons/Button";
import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
import SimpleTabs from "@/refresh-components/SimpleTabs";
import useSWR from "swr";
import { ThreeDotsLoader } from "@/components/Loading";
import * as SettingsLayouts from "@/layouts/settings-layouts";
import Text from "@/refresh-components/texts/Text";
import { cn } from "@/lib/utils";
import { SvgLock, SvgFiles, SvgSearch, SvgHardDrive } from "@opal/icons";
import { ADMIN_ROUTE_CONFIG, ADMIN_PATHS } from "@/lib/admin-routes";
import CollectionsPanel from "./components/CollectionsPanel";
import DocumentsPanel from "./components/DocumentsPanel";
import SearchPanel from "./components/SearchPanel";

const route = ADMIN_ROUTE_CONFIG[ADMIN_PATHS.DOCUMENT_PROCESSING]!;

// ---------------------------------------------------------------------------
// Unstructured API key section (unchanged from original)
// ---------------------------------------------------------------------------

function UnstructuredApiKeySection() {
  const {
    data: isApiKeySet,
    mutate,
    isLoading,
  } = useSWR<{
    unstructured_api_key: string | null;
  }>("/api/search-settings/unstructured-api-key-set", (url: string) =>
    fetch(url).then((res) => res.json())
  );

  const [apiKey, setApiKey] = useState("");

  const handleSave = async () => {
    try {
      await fetch(
        `/api/search-settings/upsert-unstructured-api-key?unstructured_api_key=${apiKey}`,
        { method: "PUT" }
      );
    } catch (error) {
      console.error("Failed to save API key:", error);
    }
    mutate();
  };

  const handleDelete = async () => {
    try {
      await fetch("/api/search-settings/delete-unstructured-api-key", {
        method: "DELETE",
      });
      setApiKey("");
    } catch (error) {
      console.error("Failed to delete API key:", error);
    }
    mutate();
  };

  if (isLoading) {
    return (
      <div className="w-full max-w-2xl">
        <CardSection>
          <ThreeDotsLoader />
        </CardSection>
      </div>
    );
  }

  return (
    <div className="w-full max-w-2xl">
      <CardSection className="flex flex-col gap-2">
        <Text
          as="p"
          headingH3
          text05
          className="border-b border-border-01 pb-2"
        >
          Process with Unstructured API
        </Text>

        <div className="flex flex-col gap-2">
          <Text as="p" mainContentBody text04 className="leading-relaxed">
            Unstructured extracts and transforms complex data from formats like
            .pdf, .docx, .png, .pptx, etc. into clean text for Onyx to ingest.
            Provide an API key to enable Unstructured document processing.
          </Text>
          <Text as="p" mainContentMuted text03>
            <span className="font-main-ui-action text-text-03">Note:</span>{" "}
            this will send documents to Unstructured servers for processing.
          </Text>
          <Text as="p" mainContentBody text04 className="leading-relaxed">
            Learn more about Unstructured{" "}
            <a
              href="https://docs.unstructured.io/welcome"
              target="_blank"
              rel="noopener noreferrer"
              className="text-action-link-05 underline-offset-4 hover:underline"
            >
              here
            </a>
            .
          </Text>
          <div className="pt-1.5">
            {isApiKeySet ? (
              <div
                className={cn(
                  "flex items-center gap-0.5 rounded-08 border border-border-01",
                  "bg-background-neutral-01 px-2 py-1.5"
                )}
              >
                <Text
                  as="p"
                  mainUiMuted
                  text03
                  className="flex-1 tracking-[0.3em] text-text-03"
                >
                  ••••••••••••••••
                </Text>
                <SvgLock className="h-4 w-4 stroke-text-03" aria-hidden />
              </div>
            ) : (
              <InputTypeIn
                placeholder="Enter API Key"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
              />
            )}
          </div>
          <div className="flex flex-col gap-2 desktop:flex-row desktop:items-center desktop:gap-2">
            {isApiKeySet ? (
              <>
                <Button onClick={handleDelete} danger>
                  Delete API Key
                </Button>
                <Text
                  as="p"
                  mainContentBody
                  text04
                  className="desktop:mt-0"
                >
                  Delete the current API key before updating.
                </Text>
              </>
            ) : (
              <Button onClick={handleSave} action>
                Save API Key
              </Button>
            )}
          </div>
        </div>
      </CardSection>
    </div>
  );
}

// ---------------------------------------------------------------------------
// RAG management section
// ---------------------------------------------------------------------------

function RagManagementSection() {
  const [selectedCollectionId, setSelectedCollectionId] = useState<
    string | null
  >(null);

  const tabs = SimpleTabs.generateTabs({
    documents: {
      name: "Documents",
      icon: SvgFiles,
      content: <DocumentsPanel collectionId={selectedCollectionId} />,
    },
    search: {
      name: "Search",
      icon: SvgSearch,
      content: <SearchPanel collectionId={selectedCollectionId} />,
    },
  });

  return (
    <div className="flex flex-col gap-4">
      <CollectionsPanel
        selectedCollectionId={selectedCollectionId}
        onCollectionSelect={setSelectedCollectionId}
      />

      {selectedCollectionId ? (
        <SimpleTabs tabs={tabs} defaultValue="documents" />
      ) : (
        <CardSection>
          <div className="flex flex-col items-center gap-2 py-8 text-center">
            <SvgHardDrive
              className="h-8 w-8 stroke-text-03 opacity-40"
              aria-hidden
            />
            <Text as="p" mainContentMuted text03>
              Select or create a collection above to manage documents and run
              searches.
            </Text>
          </div>
        </CardSection>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function Page() {
  return (
    <SettingsLayouts.Root>
      <SettingsLayouts.Header
        icon={route.icon}
        title={route.title}
        separator
      />
      <SettingsLayouts.Body>
        <div className="flex flex-col gap-8 pb-36">
          <UnstructuredApiKeySection />

          <div className="flex flex-col gap-2">
            <Text as="p" headingH3 text05>
              LangConnect RAG
            </Text>
            <Text as="p" mainContentBody text04 className="leading-relaxed">
              Manage vector collections, upload documents for indexing, and run
              semantic search powered by LangConnect and PGVector.
            </Text>
          </div>

          <RagManagementSection />
        </div>
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}
