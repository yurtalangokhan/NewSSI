import HttpErrorPage, {
  type HttpErrorCode,
} from "@/components/errorPages/HttpErrorPage";
import { notFound } from "next/navigation";

export interface PageProps {
  params: Promise<{ code: string }>;
}

const HTTP_ERROR_CODES = new Set([400, 401, 403, 404, 500]);

export default async function Page({ params }: PageProps) {
  const { code } = await params;
  const parsedCode = Number(code);

  if (!HTTP_ERROR_CODES.has(parsedCode)) {
    notFound();
  }

  return <HttpErrorPage code={parsedCode as HttpErrorCode} />;
}
