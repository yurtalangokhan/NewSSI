import { OnyxDocument } from "@/lib/search/interfaces";
import { ValidSources } from "@/lib/types";
import {
  FetchToolDocuments,
  Packet,
  PacketType,
  SearchToolDocumentsDelta,
} from "@/app/app/services/streamingModels";

export interface DomainGroup {
  domain: string;
  documents: OnyxDocument[];
}

export interface SplitWebSources {
  readDocuments: OnyxDocument[];
  searchDocuments: OnyxDocument[];
  internalDocuments: OnyxDocument[];
}

/** True once every document in a non-empty set is a web result. */
export function isAllWebSources(documents: OnyxDocument[]): boolean {
  if (documents.length === 0) return false;
  return documents.every(
    (doc) => doc.is_internet || doc.source_type === ValidSources.Web
  );
}

function hostnameOf(link: string): string {
  try {
    return new URL(link).hostname;
  } catch {
    return "";
  }
}

/** Groups documents by hostname, preserving the order each domain first
 * appears in. Always groups — including domains with only one document —
 * so the caller decides how a group of size 1 renders versus one of size
 * 2+, rather than baking that presentation choice into the grouping
 * logic itself. */
export function groupSourcesByDomain(documents: OnyxDocument[]): DomainGroup[] {
  const groups: DomainGroup[] = [];
  const indexByDomain = new Map<string, number>();

  for (const doc of documents) {
    const domain = hostnameOf(doc.link);
    const existingIndex = indexByDomain.get(domain);
    if (existingIndex === undefined) {
      indexByDomain.set(domain, groups.length);
      groups.push({ domain, documents: [doc] });
    } else {
      groups[existingIndex]?.documents.push(doc);
    }
  }

  return groups;
}

/**
 * Splits sources into:
 * 1. readDocuments: Web pages explicitly opened/fetched via fetch_webpage (FETCH_TOOL_DOCUMENTS / open_url_documents)
 * 2. searchDocuments: Web pages returned in web search query results (SEARCH_TOOL_DOCUMENTS_DELTA) that were not read
 * 3. internalDocuments: Persisted connector documents from internal search
 */
export function splitMessageSources(
  packets: Packet[] = [],
  persistedDocuments: OnyxDocument[] = []
): SplitWebSources {
  const readMap = new Map<string, OnyxDocument>();
  const searchMap = new Map<string, OnyxDocument>();
  const readDocIds = new Set<string>();
  const readLinks = new Set<string>();

  for (const packet of packets) {
    const type = packet.obj.type;
    if (type === PacketType.FETCH_TOOL_DOCUMENTS) {
      const docs = (packet.obj as FetchToolDocuments).documents || [];
      for (const doc of docs) {
        if (doc.document_id) {
          readMap.set(doc.document_id, doc);
          readDocIds.add(doc.document_id);
        }
        if (doc.link) {
          readLinks.add(doc.link);
        }
      }
    } else if (type === PacketType.SEARCH_TOOL_DOCUMENTS_DELTA) {
      const docs = (packet.obj as SearchToolDocumentsDelta).documents || [];
      for (const doc of docs) {
        if (doc.document_id) {
          searchMap.set(doc.document_id, doc);
        }
      }
    }
  }

  // Remove any documents from searchMap that are already in readMap
  // so that read pages stand out in their own dedicated section without duplication
  for (const [searchId, doc] of Array.from(searchMap.entries())) {
    if (readDocIds.has(searchId) || (doc.link && readLinks.has(doc.link))) {
      searchMap.delete(searchId);
    }
  }

  // Filter internal documents: persisted documents that are not web results
  const internalDocuments = persistedDocuments.filter(
    (doc) => !doc.is_internet && doc.source_type !== ValidSources.Web
  );

  return {
    readDocuments: Array.from(readMap.values()),
    searchDocuments: Array.from(searchMap.values()),
    internalDocuments,
  };
}
