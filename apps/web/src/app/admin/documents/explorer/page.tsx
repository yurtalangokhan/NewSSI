import { notFound } from "next/navigation";
import { fetchConnectorsSS } from "@/lib/api/domains/datasources/server";
import { fetchDocumentSetsSS } from "@/lib/api/domains/knowledge/server";
import type { Connector } from "@/lib/connectors/connectors";
import type { DocumentSetSummary } from "@/lib/types";
import DocumentExplorerPage from "./DocumentExplorerPage";

async function fetchValidFilterInfo() {
  const [connectorsResponse, documentSetsResponse] = await Promise.all([
    fetchConnectorsSS(),
    fetchDocumentSetsSS(),
  ]);

  const connectors = connectorsResponse.ok
    ? ((await connectorsResponse.json()) as Connector<any>[])
    : [];
  const documentSets = documentSetsResponse.ok
    ? ((await documentSetsResponse.json()) as DocumentSetSummary[])
    : [];

  if (!connectorsResponse.ok) {
    console.log(
      `Failed to fetch connectors - ${connectorsResponse.status} - ${connectorsResponse.statusText}`
    );
  }
  if (!documentSetsResponse.ok) {
    console.log(
      `Failed to fetch document sets - ${documentSetsResponse.status} - ${documentSetsResponse.statusText}`
    );
  }

  return { connectors, documentSets };
}

export default async function Page(props: {
  searchParams: Promise<{ [key: string]: string }>;
}) {
  notFound();

  const searchParams = await props.searchParams;
  const { connectors, documentSets } = await fetchValidFilterInfo();

  return (
    <DocumentExplorerPage
      initialSearchValue={searchParams.query}
      connectors={connectors}
      documentSets={documentSets}
    />
  );
}
