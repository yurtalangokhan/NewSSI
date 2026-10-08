import { chatEndpoints } from "@/lib/api/domains/chat/endpoints";
import { transformLinkUri } from "@/lib/utils";

const ATTACHMENT_PREFIX = "attachment:";
// Ids are generated (uuid / hex); refusing anything else keeps a crafted
// reference from steering the request to another path.
const FILE_ID = /^[A-Za-z0-9_-]+$/;

/**
 * `urlTransform` for authored documents. An agent embeds a chat attachment as
 * `![alt](attachment:<file_id>)`; the panel serves it from the caller's own
 * chat file endpoint. Every other URL follows the shared link rules.
 */
export function documentUrlTransform(url: string): string | null {
  const trimmed = url.trim();
  if (!trimmed.toLowerCase().startsWith(ATTACHMENT_PREFIX)) {
    return transformLinkUri(url);
  }
  const fileId = trimmed.slice(ATTACHMENT_PREFIX.length);
  if (!FILE_ID.test(fileId)) return null;
  return chatEndpoints.file(fileId).browserPath;
}
