import { proxyToBackend } from "@/lib/api/proxy";
import { NextRequest } from "next/server";

function ollamaModelPath(modelName: string[]) {
  return `/api/admin/ollama/models/${modelName.join("/")}`;
}

export async function DELETE(
  request: NextRequest,
  props: { params: Promise<{ modelName: string[] }> }
) {
  return proxyToBackend(
    request,
    ollamaModelPath((await props.params).modelName),
    { method: "DELETE" }
  );
}
