import Text from "@/refresh-components/texts/Text";

interface KeyValueListProps {
  entries: Record<string, unknown>;
}

function formatValue(value: unknown): string {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return JSON.stringify(value);
}

/** Metadata or properties as a two-column list. */
export default function KeyValueList({ entries }: KeyValueListProps) {
  const rows = Object.entries(entries).filter(
    ([, value]) => value !== null && value !== undefined && value !== ""
  );
  return (
    <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1.5">
      {rows.map(([key, value]) => (
        <div key={key} className="contents">
          <dt>
            <Text as="span" secondaryBody text03>
              {key}
            </Text>
          </dt>
          <dd className="min-w-0">
            <Text as="span" secondaryMono text04 className="break-words">
              {formatValue(value)}
            </Text>
          </dd>
        </div>
      ))}
    </dl>
  );
}
