"use client";

import type React from "react";
import { useState } from "react";
import {
  DocumentsCard,
  DocumentsCardLoading,
} from "./components/documents-card";
import {
  CollectionsCard,
  CollectionsCardLoading,
} from "./components/collections-card";
import { useRagContext } from "./providers/RAG";
import EmptyCollectionsState from "./components/empty-collections";
import { DataSourcePanel } from "@/features/datasource/components/datasource-panel";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Database, FolderOpen } from "lucide-react";

export default function RAGInterface() {
  const {
    selectedCollection,
    setSelectedCollection,
    collections,
    initialSearchExecuted,
  } = useRagContext();
  const [currentPage, setCurrentPage] = useState(1);
  const [activeTab, setActiveTab] = useState<"collections" | "datasources">("collections");

  return (
    <div className="w-full px-4 py-4">
      <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as any)} className="w-full">
        <TabsList className="grid w-full max-w-lg grid-cols-2 mb-6">
          <TabsTrigger value="collections" className="flex items-center gap-2">
            <FolderOpen className="h-4 w-4" />
            Collections
          </TabsTrigger>
          <TabsTrigger value="datasources" className="flex items-center gap-2">
            <Database className="h-4 w-4" />
            Data Sources
          </TabsTrigger>
        </TabsList>

        {/* Collections Tab - Full width with list + documents */}
        <TabsContent value="collections" className="mt-0">
          <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
            <div className="md:col-span-1">
              {initialSearchExecuted ? (
                collections.length > 0 ? (
                  <CollectionsCard
                    collections={collections}
                    selectedCollection={selectedCollection}
                    setSelectedCollection={setSelectedCollection}
                    setCurrentPage={setCurrentPage}
                  />
                ) : (
                  <EmptyCollectionsState />
                )
              ) : (
                <CollectionsCardLoading />
              )}
            </div>
            <div className="md:col-span-2">
              {initialSearchExecuted ? (
                <DocumentsCard
                  selectedCollection={selectedCollection}
                  currentPage={currentPage}
                  setCurrentPage={setCurrentPage}
                />
              ) : (
                <DocumentsCardLoading />
              )}
            </div>
          </div>
        </TabsContent>

        {/* Data Sources Tab - Full width with list + inline details */}
        <TabsContent value="datasources" className="mt-0">
          <DataSourcePanel />
        </TabsContent>
      </Tabs>
    </div>
  );
}
