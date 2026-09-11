const CHAT_FILE_PREFIX = "/api/chat/file";

/**
 * Fetch a chat file by its ID, returning the raw Response.
 *
 * The caller is responsible for consuming the body (e.g. `.blob()`,
 * `.text()`) since different consumers need different formats.
 */
export async function fetchChatFile(fileId: string): Promise<Response> {
  const response = await fetch(
    `${CHAT_FILE_PREFIX}/${encodeURIComponent(fileId)}`,
    {
      method: "GET",
    }
  );

  if (!response.ok) {
    throw new Error("Failed to load document.");
  }

  return response;
}

/**
 * The URL that serves a chat file's *original* bytes.
 *
 * The plain endpoint is a preview endpoint: it deliberately transcodes an
 * XLSX to CSV text so the table preview can render it without extra parsing.
 * Saving that response under the original `.xlsx` name hands the user a file
 * Excel refuses to open ("file format or extension is not valid"), so
 * anything that downloads has to ask for the original bytes explicitly.
 */
export function chatFileDownloadUrl(fileId: string): string {
  return `${CHAT_FILE_PREFIX}/${encodeURIComponent(fileId)}?download=1`;
}

/**
 * Where a download button should point.
 *
 * A file that has not been sent yet has no backend copy — it is previewed
 * straight from a `data:`/`blob:` URL, and that URL is also the only thing
 * there is to save. Anything stored server-side must come from the backend,
 * never from the blob the preview was built out of.
 */
export function resolveDownloadHref(
  fileId: string,
  previewUrl: string,
  isInlinePreview: boolean
): string {
  return isInlinePreview ? previewUrl : chatFileDownloadUrl(fileId);
}
