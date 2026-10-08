import { MethodSpec } from "@/lib/tools/interfaces";

const SUPPORTED_HTTP_METHODS = new Set([
  "get",
  "post",
  "put",
  "patch",
  "delete",
  "options",
  "head",
]);

const isPlainRecord = (value: unknown): value is Record<string, any> =>
  Boolean(value) && typeof value === "object" && !Array.isArray(value);

export function extractMethodSpecsFromDefinition(
  definition?: Record<string, any> | null
): MethodSpec[] {
  if (!isPlainRecord(definition) || !isPlainRecord(definition.paths)) {
    return [];
  }

  const pathEntries = Object.entries(definition.paths as Record<string, any>);
  const methods: MethodSpec[] = [];

  for (const [path, operations] of pathEntries) {
    if (!isPlainRecord(operations)) {
      continue;
    }

    for (const [methodName, spec] of Object.entries(operations)) {
      if (!isPlainRecord(spec)) {
        continue;
      }

      if (!SUPPORTED_HTTP_METHODS.has(methodName.toLowerCase())) {
        continue;
      }

      const name = spec.operationId ?? spec.operationID;
      const summary = spec.summary ?? spec.description;

      if (!name || !summary) {
        continue;
      }

      methods.push({
        name,
        summary,
        path,
        method: methodName.toUpperCase(),
        spec,
        custom_headers: [],
      });
    }
  }

  return methods;
}
