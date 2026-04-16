"use client";

import CardSection from "@/components/admin/CardSection";
import Text from "@/refresh-components/texts/Text";
import { useGraphStats } from "@/lib/langconnect";
import { ThreeDotsLoader } from "@/components/Loading";

function StatBadge({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-center gap-1.5 rounded-full border border-border-01 px-3 py-1">
      <Text as="span" mainContentMuted text03 className="text-xs">
        {label}
      </Text>
      <Text
        as="span"
        mainUiAction
        text04
        className="text-xs font-semibold tabular-nums"
      >
        {value.toLocaleString()}
      </Text>
    </div>
  );
}

function CountTable({
  title,
  data,
}: {
  title: string;
  data: Record<string, number>;
}) {
  const entries = Object.entries(data).sort((a, b) => b[1] - a[1]);
  if (entries.length === 0) return null;

  return (
    <div className="flex flex-col gap-2 flex-1">
      <Text as="p" mainUiAction text04 className="text-sm font-medium">
        {title}
      </Text>
      <div className="rounded-08 border border-border-01 overflow-hidden">
        <div className="grid grid-cols-2 bg-background-tint-00 px-3 py-1.5 border-b border-border-01">
          <Text as="p" mainContentMuted text03 className="text-xs font-medium">
            Type
          </Text>
          <Text
            as="p"
            mainContentMuted
            text03
            className="text-xs font-medium text-right"
          >
            Count
          </Text>
        </div>
        {entries.map(([key, count]) => (
          <div
            key={key}
            className="grid grid-cols-2 px-3 py-2 border-b border-border-01 last:border-b-0 hover:bg-background-neutral-01 transition-colors"
          >
            <Text as="p" mainContentBody text04 className="text-sm capitalize">
              {key.replace(/_/g, " ")}
            </Text>
            <Text
              as="p"
              mainUiAction
              text04
              className="text-sm font-semibold tabular-nums text-right"
            >
              {count.toLocaleString()}
            </Text>
          </div>
        ))}
      </div>
    </div>
  );
}

interface GraphStatsPanelProps {
  collectionId: string | null;
}

export default function GraphStatsPanel({
  collectionId,
}: GraphStatsPanelProps) {
  const { stats, isLoading } = useGraphStats(collectionId);

  if (!collectionId) return null;

  if (isLoading) {
    return (
      <CardSection>
        <ThreeDotsLoader />
      </CardSection>
    );
  }

  if (!stats) return null;

  const hasLabelCounts = Object.keys(stats.label_counts).length > 0;
  const hasRelCounts =
    Object.keys(stats.relationship_type_counts).length > 0;

  return (
    <CardSection className="flex flex-col gap-4">
      <Text as="p" headingH3 text05>
        Graph Statistics
      </Text>

      <div className="flex flex-wrap gap-3">
        <StatBadge label="Nodes" value={stats.node_count} />
        <StatBadge label="Edges" value={stats.edge_count} />
      </div>

      {(hasLabelCounts || hasRelCounts) && (
        <div className="flex flex-col gap-4 desktop:flex-row desktop:gap-6">
          {hasLabelCounts && (
            <CountTable
              title="Entity Types"
              data={stats.label_counts}
            />
          )}
          {hasRelCounts && (
            <CountTable
              title="Relationship Types"
              data={stats.relationship_type_counts}
            />
          )}
        </div>
      )}
    </CardSection>
  );
}
